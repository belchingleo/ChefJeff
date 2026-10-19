#!/usr/bin/env python3
"""Test-only load check: simulated pages against a local hosted_server.py, with no model calls.

Each page creates a kitchen from its network address, connects a stand-in browser model that always
answers "wait", and tries to start. Pages past one network's share must be told so (reason "network"),
pages past --capacity must wait ("等待空位": can_start false, reason "full") and pages past
--capacity + --max-waiting cannot open a kitchen at all. Started pages play: state 5 times a second,
model answers and moves. Halfway, half of the running pages leave, and waiting pages must take the
free slots. Never point this at a real server; it is not part of the runtime package.

    python3 scripts/load_test_hosted.py --pages 44 --capacity 8 --max-waiting 32 --seconds 30
"""
import argparse
import http.client
import json
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


class Page:
    def __init__(self, run, network):
        self.run, self.network = run, network
        self.token = self.game = None
        self.started_at = self.left_at = None
        self.rejections = []  # 'network' / 'full' reasons seen while trying to start

    def call(self, method, path, body=None):
        headers = {'Host': self.run.host, 'X-ChefJeff-Client': self.network}
        if self.token: headers['X-ChefJeff-Session'] = self.token
        raw = None
        if body is not None:
            raw = json.dumps(body).encode()
            headers.update({'Origin': self.run.origin, 'Content-Type': 'application/json'})
        started = time.monotonic()
        c = http.client.HTTPConnection('127.0.0.1', self.run.port, timeout=10)
        try:
            c.request(method, path, raw, headers)
            r = c.getresponse()
            data = json.loads(r.read() or b'{}')
        except (OSError, ValueError) as exc:
            self.run.record('error', 0, type(exc).__name__)
            return 0, {}
        finally:
            c.close()
        self.run.record(path, r.status, (time.monotonic()-started)*1000)
        return r.status, data

    def post(self, path, **body):
        return self.call('POST', path, {'game_id': self.game, 'request_id': f'{time.monotonic_ns()}', **body})

    def open(self):
        status, data = self.call('POST', '/api/session', {})
        if status != 201: return False
        self.token = data['session']
        self.game = self.call('GET', '/api/state')[1].get('game_id')
        return self.post('/api/browser-ready', connected=True)[0] == 200

    def try_start(self):
        status, _ = self.post('/api/start', speed=1)
        if status == 200:
            self.started_at = time.monotonic()
            return True
        capacity = self.call('GET', '/api/state')[1].get('capacity') or {}
        if capacity.get('can_start') is False: self.rejections.append(capacity.get('reason'))
        return False

    def play(self, until, leave_at=None):
        seq, step = 0, 0
        while time.monotonic() < until:
            if leave_at and time.monotonic() >= leave_at:
                self.call('POST', '/api/session/close', {})
                self.left_at = time.monotonic()
                return
            state = self.call('GET', '/api/state')[1]
            self.game = state.get('game_id', self.game)
            if self.started_at is None:
                # Waiting: the page's button comes back once can_start is true; the player presses it.
                if (state.get('capacity') or {}).get('can_start') and self.try_start(): continue
                time.sleep(1); continue
            request = self.call('GET', '/api/model/request')[1].get('request')
            if request:
                self.call('POST', '/api/model/result', {'id': request['id'], 'choice': 'wait', 'sprint': False, 'usage': {}})
            step += 1
            if step % 5 == 0:
                seq += 1
                dx, dy = [(1, 0), (0, 1), (-1, 0), (0, -1)][seq % 4]
                self.post('/api/move', dx=dx, dy=dy, seq=seq)
            time.sleep(.2)


class Run:
    def __init__(self, args):
        self.args = args
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); self.port = s.getsockname()[1]
        self.host = f'127.0.0.1:{self.port}'
        self.origin = 'http://' + self.host
        self.lock = threading.Lock()
        self.latencies, self.statuses, self.used = [], {}, []

    def record(self, path, status, ms):
        with self.lock:
            key = f'{path} {status}'
            self.statuses[key] = self.statuses.get(key, 0) + 1
            if status: self.latencies.append(ms)

    def ops(self):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            c.request('GET', '/ops/capacity', headers={'Host': self.host})
            return json.loads(c.getresponse().read())
        finally:
            c.close()

    def together(self, pages, method, *args):
        threads = [threading.Thread(target=getattr(p, method), args=args) for p in pages]
        for t in threads: t.start()
        for t in threads: t.join()

    def main(self):
        a = self.args
        server = subprocess.Popen([sys.executable, str(ROOT/'hosted_server.py'), '--port', str(self.port), '--origin', self.origin,
                                   '--max-sessions', str(a.capacity), '--max-waiting', str(a.max_waiting),
                                   '--max-per-network', str(a.per_network)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                try: self.ops(); break
                except OSError: time.sleep(.1)
            # One shared network (per-network limit) first, then everyone else at once.
            shared = [Page(self, '10.0.0.1') for _ in range(a.per_network + 2)]
            others = [Page(self, f'10.1.{i // 250}.{i % 250 + 1}') for i in range(a.pages - len(shared))]
            pages = shared + others
            for group in (shared, others):
                opened = {}
                threads = [threading.Thread(target=lambda p=p: opened.__setitem__(p, p.open())) for p in group]
                for t in threads: t.start()
                for t in threads: t.join()
                self.together([p for p in group if opened[p]], 'try_start')
            started = [p for p in pages if p.started_at]
            opened = [p for p in pages if p.token]
            waiting = [p for p in opened if not p.started_at]
            capacity_at_start = self.ops()['capacity']
            begin = time.monotonic()
            until, half = begin + a.seconds, begin + a.seconds / 2
            leaving = set([p for p in started if p not in shared][:len(started) // 2])
            sampler = threading.Thread(target=self.sample, args=(until,))
            sampler.start()
            threads = [threading.Thread(target=p.play, args=(until, half if p in leaving else None)) for p in opened]
            for t in threads: t.start()
            for t in threads: t.join()
            sampler.join()
            final = self.ops()
        finally:
            server.terminate()
            _, stderr = server.communicate(timeout=10)
        late = [p for p in waiting if p.started_at]
        rows = sorted(self.latencies)
        pct = lambda q: round(rows[min(len(rows)-1, int((len(rows)-1)*q))], 1) if rows else None
        server_errors = {k: v for k, v in self.statuses.items() if k.split()[-1] == '500' or k.startswith('error')}
        report = {
            'settings': {'pages': a.pages, 'capacity': a.capacity, 'max_waiting': a.max_waiting, 'per_network': a.per_network, 'seconds': a.seconds},
            'opened_pages': len(opened), 'session_rejections': a.pages - len(opened),
            'started_at_once': len(started), 'shared_network_started': sum(bool(p.started_at) for p in shared),
            'waiting_reasons': {r: sum(r in p.rejections for p in waiting) for r in ('network', 'full')},
            'left_at_half_time': len(leaving), 'waiting_pages_started_later': len(late),
            'seconds_from_free_slot_to_start': [round(p.started_at - half, 2) for p in late if p.started_at >= half],
            'max_active_kitchens_seen': max(self.used or [capacity_at_start['used']]),
            'requests': sum(self.statuses.values()), 'latency_ms': {'p50': pct(.5), 'p95': pct(.95), 'p99': pct(.99), 'max': rows[-1] if rows else None,
                                                                    'mean': round(statistics.fmean(rows), 1) if rows else None},
            'statuses': dict(sorted(self.statuses.items())), 'server_errors': server_errors,
            'server_runtime': final['runtime'], 'server_capacity': final['capacity']}
        checks = {
            'pool limit enforced': len(opened) == min(a.pages, a.capacity + a.max_waiting),
            'per-network limit enforced': report['shared_network_started'] == a.per_network and report['waiting_reasons']['network'] >= 2,
            'active kitchens within capacity': report['max_active_kitchens_seen'] <= a.capacity and len(started) == min(a.capacity, len(opened) - 2),
            'others wait for a slot': not waiting or report['waiting_reasons']['full'] > 0,
            'freed slots are taken': not waiting or not leaving or len(late) >= min(len(leaving), len(waiting) - 2),
            'no server errors': not server_errors and b'Traceback' not in stderr}
        report['checks'] = checks
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return all(checks.values())

    def sample(self, until):
        while time.monotonic() < until:
            try: self.used.append(self.ops()['capacity']['used'])
            except OSError: pass
            time.sleep(.5)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--pages', type=int, default=44)
    p.add_argument('--capacity', type=int, default=8)
    p.add_argument('--max-waiting', type=int, default=32)
    p.add_argument('--per-network', type=int, default=4)
    p.add_argument('--seconds', type=float, default=30)
    args = p.parse_args(argv)
    if args.pages < args.per_network + 3: p.error('Use more pages than one network may start, plus others.')
    return 0 if Run(args).main() else 1


if __name__ == '__main__':
    sys.exit(main())
