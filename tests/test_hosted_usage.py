"""Usage counts survive releases without storing visitor identifiers or changing game admission."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import http.client
import json
from pathlib import Path
import sqlite3
import subprocess
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from hosted_server import HostedSession, Sessions, make_server
from hosted_capacity import NETWORK_FULL
from hosted_usage import COUNTERS, UsageStats


class UsageStoreTests(unittest.TestCase):
    def test_restart_preserves_only_aggregate_counters_and_start_time(self):
        with tempfile.TemporaryDirectory() as directory:
            stats = UsageStats(directory)
            for counter in COUNTERS:
                stats.increment(counter)
            snapshot = stats.snapshot()
            self.assertEqual(UsageStats(directory).snapshot(), snapshot)
            self.assertTrue(snapshot['persistent'])
            path = Path(directory) / 'usage.sqlite3'
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall(),
                                 [('durations',), ('levels',), ('totals',)])
                columns = [row[1] for row in db.execute('PRAGMA table_info(totals)')]
                self.assertEqual(columns, ['id', 'tracking_since', *COUNTERS])
                self.assertEqual(db.execute('SELECT count(*) FROM totals').fetchone()[0], 1)

    def test_level_and_duration_histograms_persist_without_per_round_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            stats = UsageStats(directory)
            stats.start_round(2, first=True)
            stats.start_round(2)
            stats.end_round(2, 'manual_end', 15, .5)
            stats.end_round(2, 'manual_end', 20, .5)
            stats.end_round(2, 'completed', 180, .75)
            data = UsageStats(directory).snapshot()
            self.assertEqual(data['started_sessions'], 1)
            self.assertEqual(data['started_rounds'], 2)
            self.assertEqual(data['manual_ends'], 2)
            self.assertEqual(data['levels'][1], {'level': 2, 'started_rounds': 2, 'completed_rounds': 1})
            manual = next(row for row in data['durations'] if row['outcome'] == 'manual_end')
            self.assertEqual(manual['bucket'], '30–60s')
            self.assertEqual(manual['rounds'], 2)
            self.assertEqual(manual['average_active_seconds'], 35)
            with closing(sqlite3.connect(Path(directory) / 'usage.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM durations').fetchone()[0], 2)

    def test_concurrent_requests_do_not_lose_increments(self):
        with tempfile.TemporaryDirectory() as directory:
            stats = UsageStats(directory)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda _: stats.increment('page_views'), range(40)))
            self.assertEqual(UsageStats(directory).snapshot()['page_views'], 40)

    def test_storage_failure_keeps_counters_in_memory_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            stats = UsageStats(directory)
            with patch('hosted_usage.sqlite3.connect', side_effect=sqlite3.OperationalError('private-path-placeholder')):
                stats.increment('page_views')
            stats.increment('started_sessions')
            snapshot = stats.snapshot()
            self.assertFalse(snapshot['persistent'])
            self.assertEqual(snapshot['storage_errors'], 1)
            self.assertEqual(snapshot['page_views'], 1)
            self.assertEqual(snapshot['started_sessions'], 1)
            self.assertNotIn('private-path-placeholder', json.dumps(snapshot))

    def test_startup_storage_failure_and_memory_only_mode_are_explicit(self):
        with patch('hosted_usage.sqlite3.connect', side_effect=sqlite3.DatabaseError):
            with tempfile.TemporaryDirectory() as directory:
                stats = UsageStats(directory)
                self.assertEqual(stats.snapshot()['storage_errors'], 1)
                stats.increment('completed_rounds')
                self.assertEqual(stats.snapshot()['completed_rounds'], 1)
        self.assertFalse(UsageStats().snapshot()['persistent'])


class UsageRoundTests(unittest.TestCase):
    def setUp(self):
        self.stats = UsageStats()
        self.game = HostedSession(release={})
        self.game.usage = self.stats
        self.game.connected = True
        self.addCleanup(self.game.close)

    def test_first_successful_start_only_once_across_resume_restart_and_next_level(self):
        game = self.game
        self.assertEqual(game._command('/api/start', {'speed': 10})[0], 400)
        self.assertEqual(self.stats.snapshot()['started_sessions'], 0)
        self.assertEqual(game._command('/api/start', {})[0], 200)
        self.assertEqual(game._command('/api/start', {})[0], 409)
        game._command('/api/pause', {})
        game._command('/api/resume', {})
        game._command('/api/pause', {})
        self.assertEqual(game._command('/api/restart', {})[0], 200)
        game._command('/api/end', {})
        self.assertEqual(game._command('/api/next', {'level': 2})[0], 200)
        self.assertEqual(self.stats.snapshot()['started_sessions'], 1)
        self.assertEqual(self.stats.snapshot()['started_rounds'], 3)
        self.assertEqual(self.stats.snapshot()['completed_rounds'], 0)

    def test_natural_closing_counts_even_a_lost_round_only_once(self):
        game = self.game
        game._command('/api/start', {})
        # Drive the real engine to closing without paid model requests.
        game.k.advance(game.k.rules.round_limit)
        game.tick(now=game.last_tick)
        self.assertEqual(game.phase, 'ended')
        self.assertFalse(game.k.aborted)
        self.assertFalse(game.k.won())
        self.assertEqual(self.stats.snapshot()['completed_rounds'], 1)
        game._finish()
        game.close()
        self.assertEqual(self.stats.snapshot()['completed_rounds'], 1)

    def test_manual_end_disconnect_and_reset_do_not_count_as_completion(self):
        game = self.game
        game._command('/api/start', {})
        game._command('/api/end', {})
        game._command('/api/reset', {})
        game._command('/api/start', {})
        game.close()
        self.assertEqual(self.stats.snapshot()['completed_rounds'], 0)

    def test_exit_duration_tracks_game_progress_and_excludes_pause_wait(self):
        game = self.game
        game._command('/api/start', {'speed': .5})
        game.k.advance(12)
        game._command('/api/pause', {})
        # Wall time while paused is irrelevant to effective gameplay duration.
        game._command('/api/end', {})
        row = self.stats.snapshot()['durations'][0]
        self.assertEqual(row['outcome'], 'manual_end')
        self.assertEqual(row['game_seconds'], 12)
        self.assertEqual(row['active_seconds'], 24)
        self.assertEqual(row['bucket'], '10–30s')
        game.close()
        self.assertEqual(self.stats.snapshot()['manual_ends'], 1)

    def test_page_close_disconnection_and_service_shutdown_are_separate(self):
        for reason in ('page_close', 'disconnected', 'shutdown'):
            with self.subTest(reason=reason):
                game = HostedSession(release={})
                game.usage = self.stats
                game.connected = True
                game._command('/api/start', {})
                game.k.advance(5)
                game.usage_close_reason = reason
                game.close()
                game.close()
                self.assertEqual(self.stats.snapshot()['round_outcomes'][reason], 1)

    def test_capacity_rejections_count_attempts_without_polling_or_failures(self):
        manager = Sessions(capacity=1, max_waiting=1, usage=self.stats, per_network=1)
        try:
            a = manager.create('192.0.2.0')
            b = manager.create('192.0.2.0')
            self.assertIsNone(manager.create())
            self.assertIs(manager.reserve(a), True)
            self.assertEqual(manager.reserve(b), NETWORK_FULL)
            for _ in range(3): manager.capacity_state(b)
            self.assertEqual(self.stats.snapshot()['page_full_rejections'], 1)
            self.assertEqual(self.stats.snapshot()['network_full_rejections'], 1)
            manager.get(b).network = '198.51.100.0'
            self.assertIsNone(manager.reserve(b))
            self.assertEqual(self.stats.snapshot()['full_rejections'], 2)
            self.assertIsNone(manager.reserve('invalid-session'))
            self.assertEqual(self.stats.snapshot()['full_rejections'], 2)
        finally: manager.close()


class UsageHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.server = make_server(0, 'https://chefjeff.online', data_dir=self.directory.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.sessions.close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, body=None, headers=None):
        request_headers = {'Host': 'chefjeff.online', **(headers or {})}
        if body is not None:
            request_headers.update({'Content-Type': 'application/json', 'Origin': 'https://chefjeff.online'})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request('GET' if body is None else 'POST', path,
                               json.dumps(body) if body is not None else None, request_headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if response.getheader('Content-Type').startswith('application/json') else raw
        finally:
            connection.close()

    def test_homepage_only_counts_successful_page_responses_not_assets_or_polling(self):
        for path in ('/', '/index.html'):
            self.assertEqual(self.request(path)[0], 200)
        for path in ('/healthz', '/hosted-agent.js', '/privacy.html', '/ops/capacity', '/absent.html'):
            self.request(path)
        self.assertEqual(self.request('/', headers={'Origin': 'https://other.example'})[0], 403)
        status, data = self.request('/ops/usage')
        self.assertEqual(status, 200)
        self.assertEqual(data['usage']['page_views'], 2)
        self.assertEqual(data['usage']['started_sessions'], 0)
        self.assertEqual(data['usage']['running_sessions'], 0)
        self.assertTrue(data['usage']['persistent'])

    def test_authenticated_start_retries_and_live_running_count(self):
        status, data = self.request('/api/session', {})
        self.assertEqual(status, 201)
        token = data['session']
        game = self.server.sessions.get(token)
        headers = {'X-ChefJeff-Session': token}
        base = {'game_id': game.game_id}
        start = {**base, 'request_id': 'start'}
        self.assertEqual(self.request('/api/start', start, headers)[0], 428)
        self.request('/api/browser-ready', {**base, 'request_id': 'connect', 'connected': True}, headers)
        start['request_id'] = 'successful-start'
        for _ in range(2):
            self.assertEqual(self.request('/api/start', start, headers)[0], 200)
        usage = self.request('/ops/usage')[1]['usage']
        self.assertEqual(usage['started_sessions'], 1)
        self.assertEqual(usage['running_sessions'], 1)
        self.assertEqual(usage['completed_rounds'], 0)
        self.request('/api/pause', {**base, 'request_id': 'pause'}, headers)
        self.assertEqual(self.request('/ops/usage')[1]['usage']['running_sessions'], 0)
        self.request('/api/session/close', {}, headers)
        self.assertEqual(self.request('/ops/usage')[1]['usage']['running_sessions'], 0)

    def test_new_page_sessions_count_separately_without_storing_their_ids(self):
        for _ in range(2):
            _, data = self.request('/api/session', {})
            game = self.server.sessions.get(data['session'])
            with game.lock:
                game.connected = True
                game._command('/api/start', {})
            self.request('/api/session/close', {}, {'X-ChefJeff-Session': data['session']})
        self.assertEqual(UsageStats(self.directory.name).snapshot()['started_sessions'], 2)
        self.assertEqual(self.request('/ops/usage')[1]['usage']['running_sessions'], 0)

    def test_proxy_client_header_and_cross_origin_cannot_read_operator_counts(self):
        for headers in ({'X-ChefJeff-Client': '192.0.2.1'}, {'X-ChefJeff-Client': ''},
                        {'Origin': 'https://other.example'}, {'Host': 'other.example'},
                        {'Sec-Fetch-Site': 'cross-site'}):
            self.assertIn(self.request('/ops/usage', headers=headers)[0], (403, 404))

    def test_browser_estimates_require_a_session_and_play_then_deduplicate_retries(self):
        report = {'first_visit': True, 'first_play': False}
        self.assertEqual(self.request('/api/usage', report)[0], 401)
        _, data = self.request('/api/session', {})
        headers = {'X-ChefJeff-Session': data['session']}
        game = self.server.sessions.get(data['session'])
        self.assertEqual(self.request('/api/usage', {**report, 'api_key': 'unit-test-placeholder'}, headers)[0], 400)
        self.assertEqual(self.request('/api/usage', {'first_visit': 'yes', 'first_play': False}, headers)[0], 400)
        self.assertEqual(self.request('/api/usage', {'first_visit': True, 'first_play': True}, headers)[0], 409)
        for _ in range(2): self.assertEqual(self.request('/api/usage', report, headers)[0], 200)
        with game.lock:
            game.connected = True
            game._command('/api/start', {})
        for _ in range(2):
            self.assertEqual(self.request('/api/usage', {'first_visit': True, 'first_play': True}, headers)[0], 200)
        usage = self.request('/ops/usage')[1]['usage']
        self.assertEqual(usage['estimated_visitor_browsers'], 1)
        self.assertEqual(usage['estimated_player_browsers'], 1)
        self.assertNotIn(data['session'], json.dumps(usage))
        self.assertNotIn(game.game_id, json.dumps(usage))

    def test_operator_cli_queries_loopback_without_credentials_or_database_access(self):
        self.request('/')
        script = Path(__file__).resolve().parents[1] / 'scripts/hosted_usage.py'
        result = subprocess.run([sys.executable, str(script), '--port', str(self.server.server_port)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('页面访问次数： 1', result.stdout)
        self.assertIn('当前游戏中的会话数： 0', result.stdout)
        self.assertNotIn('仅保存在内存中', result.stdout)


class UsageProcessTests(unittest.TestCase):
    def test_systemd_style_sigterm_records_shutdown_and_restart_retains_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            def start():
                with socket.socket() as probe:
                    probe.bind(('127.0.0.1', 0))
                    port = probe.getsockname()[1]
                process = subprocess.Popen([sys.executable, 'hosted_server.py', '--port', str(port),
                                            '--origin', 'https://chefjeff.online', '--data-dir', directory],
                                           cwd=Path(__file__).resolve().parents[1],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                def stop():
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
                self.addCleanup(stop)
                for _ in range(100):
                    try:
                        if request(port, '/healthz')[0] == 200: return process, port
                    except OSError: pass
                    time.sleep(.05)
                self.fail('Hosted subprocess failed to start')

            def request(port, path, body=None, token=None):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                headers = {'Host': 'chefjeff.online', 'Origin': 'https://chefjeff.online'}
                if token: headers['X-ChefJeff-Session'] = token
                if body is not None: headers['Content-Type'] = 'application/json'
                try:
                    connection.request('GET' if body is None else 'POST', path,
                                       json.dumps(body) if body is not None else None, headers)
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())
                finally: connection.close()

            process, port = start()
            token = request(port, '/api/session', {})[1]['session']
            base = {'game_id': request(port, '/api/state', token=token)[1]['game_id']}
            self.assertEqual(request(port, '/api/browser-ready', {**base, 'request_id': 'connect', 'connected': True}, token)[0], 200)
            self.assertEqual(request(port, '/api/start', {**base, 'request_id': 'start'}, token)[0], 200)
            process.terminate()
            self.assertEqual(process.wait(timeout=10), 0)
            before = UsageStats(directory).snapshot()
            self.assertEqual(before['started_rounds'], 1)
            self.assertEqual(before['round_outcomes']['shutdown'], 1)
            self.assertEqual(before['round_outcomes']['page_close'], 0)
            self.assertEqual(before['manual_ends'], 0)
            process, port = start()
            usage = request(port, '/ops/usage')[1]['usage']
            self.assertEqual(usage['tracking_since'], before['tracking_since'])
            self.assertEqual(usage['started_rounds'], 1)
            self.assertEqual(usage['round_outcomes']['shutdown'], 1)
            self.assertEqual(usage['running_sessions'], 0)
            process.terminate()
            self.assertEqual(process.wait(timeout=10), 0)
