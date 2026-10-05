#!/usr/bin/env python3
"""Isolated, ephemeral kitchens. Model credentials and HTTP requests stay in the browser.
Run behind the supplied HTTPS reverse proxy, never expose the Python port directly.
"""
import argparse
from copy import deepcopy
import json
import math
import mimetypes
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit, unquote
from http.server import ThreadingHTTPServer
from kitchen import ROOT
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
from web_server import GameSession, Handler
from release_info import release_info
from feedback import play_export
from hosted_records import ContributionStore, pilot_record, CONSENT_VERSION


class NullJournal:
    """Never creates local journals, model payload logs, or memory files."""
    def __init__(self, *_): pass
    def __call__(self, *_): pass
    def close(self): pass


class BrowserRelay(SpatialJevClient):
    def __init__(self, config):
        # Payload construction only; never loads a machine credential or uses ask().
        super().__init__(config, key='browser-transport-no-server-credential')
        self.guard = threading.Lock()
        self.pending = None
        self.closed = False

    def ask(self, payload):
        task = {'id': secrets.token_urlsafe(24), 'payload': deepcopy(payload),
                'event': threading.Event(), 'result': None, 'sent': time.monotonic()}
        with self.guard:
            if self.closed: raise RuntimeError('Browser connection closed')
            self.pending = task
        try:
            if not task['event'].wait(24) or task['result'] is None:
                raise RuntimeError('Browser model request failed or expired')
            return task['result']
        finally:
            with self.guard:
                if self.pending is task: self.pending = None

    def request(self):
        with self.guard:
            task = self.pending
            if not task or task['event'].is_set(): return None
            return {'id': task['id'], 'payload': deepcopy(task['payload'])}

    def resolve(self, body):
        with self.guard:
            task = self.pending
            if not task or body.get('id') != task['id'] or task['event'].is_set(): return False
            if body.get('failed') is True:
                task['event'].set()
                return True
            choice = body.get('choice')
            criteria = task['payload']['questions']['next_action']['criteria']
            if not isinstance(choice, str) or choice not in criteria or type(body.get('sprint')) is not bool:
                return False
            usage = body.get('usage', {})
            if not isinstance(usage, dict) or set(usage) - {'input_tokens', 'output_tokens'}: return False
            if any(type(v) is not int or not 0 <= v <= 10000000 for v in usage.values()): return False
            task['result'] = {'choice': choice, 'sprint': body['sprint'], 'model': 'browser-model',
                              'usage': usage, 'latency': time.monotonic() - task['sent'],
                              'confidence': None, 'probabilities': {}}
            task['event'].set()
            return True

    def cancel(self):
        with self.guard:
            if self.pending: self.pending['event'].set()

    def close(self):
        with self.guard:
            self.closed = True
            if self.pending: self.pending['event'].set()


class HostedSession(GameSession):
    def __init__(self):
        self.relay = None
        self.positions = []
        self.position_round = None
        self.last_sample = -1
        self.receipt = None
        self.receipt_round = None
        self.store = None
        self.connected = False
        self.release = release_info()
        self.setting = None  # Export contains no provider URL/model text.
        super().__init__(client_factory=self._client, journal_factory=NullJournal,
                         kitchen_factory=SpatialKitchen, log_prefix='hosted')
        self.c['ai_max_response_age'] = 15
        self.base_config['ai_max_response_age'] = 15
        self.deployment_mode = 'hosted'

    def tick(self, now=None):
        with self.lock:
            super().tick(now)
            if self.position_round != self.game_id:
                self.positions = []
                self.last_sample = -1
                self.position_round = self.game_id
            sample = int(self.k.time)
            if self.phase == 'running' and sample != self.last_sample and len(self.positions) < 3600:
                self.last_sample = sample
                self.positions.append({'t':round(self.k.time,3),
                    'chefs':{who:[round(float(v),3) for v in self.k.positions[who]] for who in ('human','jeff')}})

    def _client(self, config):
        if self.relay: self.relay.close()
        self.relay = BrowserRelay(config)
        return self.relay

    def public_state(self):
        with self.lock:
            state = super().public_state()
            ai = self.ai
            limit = ai.call_limit if ai else self.c.get('ai_max_calls', 200)
            state['connection'] = {'configured': self.connected, 'editable': self.phase in ('ready', 'ended')}
            state['limits'] = {'max_calls': limit, 'next_max_calls': self.c.get('ai_max_calls', 200),
                'calls': ai.calls if ai else 0, 'remaining': max(0, limit - (ai.calls if ai else 0)),
                'reached': bool(ai and ai.calls >= limit), 'editable': self.phase in ('ready', 'ended'),
                'connection_checks': 0, 'usage': dict(ai.tokens) if ai else {'input_tokens': 0, 'output_tokens': 0}}
            state['memory'] = {'enabled': False, 'editable': False, 'saved_rounds': 0, 'limit': 0, 'used_rounds': 0}
            state['release'] = self.release
            state['hosted'] = {'retention': 'session-only', 'idle_minutes': 10, 'contribution_enabled': self.store is not None}
            return state

    def _command(self, path, body):
        if path == '/api/contribution/preview':
            return 200, {'record':pilot_record(self), 'consent_version':CONSENT_VERSION}
        if path == '/api/contribution/save':
            if self.phase != 'ended': return 409, {'error':'Finish the round before contributing.'}
            if not self.store: return 503, {'error':'Contributions are not enabled.'}
            if body.get('consent') is not True or body.get('consent_version') != CONSENT_VERSION:
                return 400, {'error':'Explicit consent is required.'}
            # round: agreed for this round; standing: the player turned on automatic upload after agreeing.
            mode = body.get('consent_mode', 'round')
            if mode not in ('round', 'standing'): return 400, {'error':'Explicit consent is required.'}
            if self.receipt_round != self.game_id:
                self.receipt = self.store.save({**pilot_record(self), 'consent_mode':mode})
                self.receipt_round = self.game_id
            return 200, {'receipt':self.receipt}
        if path == '/api/browser-ready':
            if self.phase not in ('ready', 'ended'): return 409, {'error': 'Finish this round first.'}
            if type(body.get('connected')) is not bool: return 400, {'error': 'Invalid connection state.'}
            self.connected = body['connected']
            return 200, {'ok': True}
        if path in ('/api/start', '/api/next') and not self.connected:
            return 428, {'error': 'Connect your model in this browser first.'}
        if path == '/api/limits':
            n = body.get('max_calls')
            if self.phase not in ('ready', 'ended'): return 409, {'error': 'Finish this round first.'}
            if type(n) is not int or not 1 <= n <= 2000: return 400, {'error': 'Use a limit from 1 to 2000.'}
            self.c['ai_max_calls'] = n
            return 200, {'ok': True, 'next_max_calls': n}
        if path in ('/api/export-run', '/api/feedback'):
            report = play_export(self)
            report['coverage'] = ('Every round since this page opened, each with its summary, work record, bookmarks, '
                                  'messages and every allowlisted game event. No persistent server journal exists.')
            report['bookmark_policy'].pop('log_join', None)
            return 200, {'ok': True, 'report': report}
        if path in ('/api/pause', '/api/end', '/api/reset', '/api/level', '/api/next') and self.relay:
            self.relay.cancel()
        return super()._command(path, body)

    def close(self):
        if self.relay: self.relay.close()
        super().close()


# Only game fields cross the same-origin boundary. Never echo invalid bodies.
FIELDS = {
    '/api/contribution/preview': set(),
    '/api/contribution/save': {'consent', 'consent_version', 'consent_mode'},
    '/api/browser-ready': {'connected'}, '/api/start': {'speed'}, '/api/pause': {'reason'},
    '/api/resume': set(), '/api/end': set(), '/api/reset': set(), '/api/restart': set(),
    '/api/level': {'level'}, '/api/next': {'level'}, '/api/limits': {'max_calls'}, '/api/export-run': set(),
    '/api/feedback': set(), '/api/bookmark': set(), '/api/communicate': {'code'},
    '/api/move': {'dx', 'dy', 'seq', 'sprint'}, '/api/select': {'target'},
    '/api/interact': {'expected_item', 'mode'}, '/api/throw': {'target', 'direction', 'expected_item'},
    '/api/action': {'action', 'expected'},
    '/api/model/result': {'id', 'choice', 'sprint', 'usage', 'failed'},
}


class Sessions:
    def __init__(self, capacity=8, ttl=600, factory=HostedSession, store=None):
        self.capacity, self.ttl, self.factory = capacity, ttl, factory
        self.store = store
        self.entries = {}
        self.lock = threading.RLock()

    def reap(self):
        with self.lock:
            cutoff = time.monotonic() - self.ttl
            for token, (session, seen) in list(self.entries.items()):
                if seen < cutoff:
                    session.close()
                    del self.entries[token]

    def create(self):
        with self.lock:
            self.reap()
            if len(self.entries) >= self.capacity: return None
            session = self.factory()
            session.store = self.store
            token = secrets.token_urlsafe(32)
            self.entries[token] = (session, time.monotonic())
            threading.Thread(target=session.run, daemon=True).start()
            return token

    def get(self, token):
        with self.lock:
            self.reap()
            found = self.entries.get(token)
            if not found: return None
            session, _ = found
            self.entries[token] = (session, time.monotonic())
            return session

    def close(self):
        with self.lock:
            for session, _ in self.entries.values(): session.close()
            self.entries.clear()


# Hosted-only copy swapped into the local web shell. Each anchor must stay verbatim in
# cocos-kitchen/web-shell.html (tests/test_hosted.py checks this).
SHELL_REPLACEMENTS = (
    ('默认只在本次服务运行期间使用。记住后以明文保存在这台电脑的本地配置文件；Key 不进入对局日志和试玩包。',
        '<span data-no-i18n>Online privacy: Key stays in page memory and is sent only to your model provider. Refresh clears it unless you choose Remember (browser localStorage, not encrypted). Game actions/state pass through our server; ordinary sessions create no disk journal. Optional contributions are described below.<br>在线版：Key 默认只在页面内存中，仅发送给所选模型服务，刷新即清除；主动记住才以明文保存在浏览器 localStorage。游戏动作与状态经过我们的服务器，普通会话不写磁盘对局日志。自愿贡献数据另见下方说明。</span>'),
    ('这间厨房是围绕 Jev 开发的；其他模型也可使用，响应速度和配合方式可能不同。',
        '在线版由浏览器直连模型；服务商必须允许跨域访问。跨域失败不会改由服务器代发 Key。'),
    ('建议优先选择 Jev', '浏览器直连模型'),
    ('仅保留到服务关闭', '仅保留到当前页面会话结束'),
    ('本次服务连接测试', '本页面连接测试'),
    ('可对应本地日志提取前后过程', '在线版没有可追溯的服务器对局日志'),
    ('从启动游戏起玩过的每一局', '从打开本页面起玩过的每一局'),
    ('<section aria-labelledby="memory-title"', '<section hidden aria-labelledby="memory-title"'),
)
CONTRIBUTION_SLOT = '<!-- hosted-contribution -->'
CONTRIBUTION_BADGE = ('<p id="contribution-badge" role="status" data-no-i18n hidden style="position:fixed;left:50%;bottom:8px;'
                      'transform:translateX(-50%);z-index:60;margin:0;padding:3px 10px;border-radius:10px;background:#2b1a12cc;'
                      'color:#fff;font:12px/16px system-ui,sans-serif;pointer-events:none"></p>')


def hosted_html(raw):
    page = raw.decode('utf-8')
    page = page.replace('<head>', '<head><script src="/hosted-agent.js"></script>', 1)
    for old, new in SHELL_REPLACEMENTS:
        page = page.replace(old, new)
    panel = (ROOT / 'hosted' / 'contribution.html').read_text()
    # Outside the dialogs, so the result card can show that automatic upload is on.
    page = page.replace('</body>', CONTRIBUTION_BADGE + '</body>', 1)
    # Newer shells mark a slot in the Export tab; older builds append to the settings dialog.
    page = page.replace(CONTRIBUTION_SLOT, panel, 1) if CONTRIBUTION_SLOT in page else page.replace('</dialog>', panel + '</dialog>', 1)
    return page.encode('utf-8')


class HostedHandler(Handler):
    def reply(self, status, data, content_type='application/json; charset=utf-8'):
        raw = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' https:; img-src 'self' data: blob:; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        super().end_headers()

    def valid_origin(self, post=False):
        origin = self.server.public_origin
        return (self.headers.get('Host') == urlsplit(origin).netloc
                and self.headers.get('Origin', origin if not post else '') == origin
                and self.headers.get('Sec-Fetch-Site') not in ('cross-site', 'same-site'))

    def session(self):
        return self.server.sessions.get(self.headers.get('X-ChefJeff-Session', ''))

    def do_GET(self):
        if not self.valid_origin(): return self.reply(403, {'error': 'Origin rejected.'})
        path = unquote(urlsplit(self.path).path)
        if path == '/healthz': return self.reply(200, {'ok': True})
        if path.startswith('/api/'):
            game = self.session()
            if not game: return self.reply(401, {'error': 'Session expired. Refresh to start a new kitchen.'})
            with game.lock:
                if path == '/api/state': return self.reply(200, game.public_state())
                if path == '/api/model/request':
                    return self.reply(200, {'request': game.relay.request() if game.relay and game.phase == 'running' else None})
            return self.reply(404, {'error': 'Unknown endpoint.'})
        root = self.server.web_root.resolve()
        file = (root / path.lstrip('/')).resolve()
        if file == root: file = root / 'index.html'
        if path == '/hosted-agent.js': file = ROOT / 'hosted' / 'browser-agent.js'
        elif not file.is_relative_to(root): return self.reply(404, {'error': 'Not found.'})
        if not file.is_file() or file.suffix not in ('.html','.js','.json','.css','.png','.jpg','.webp','.ico','.woff','.woff2','.ttf','.mp3','.wasm','.bin','.cconb'):
            return self.reply(404, {'error': 'Not found.'})
        data = file.read_bytes()
        if file.name == 'index.html': data = hosted_html(data)
        self.reply(200, data, mimetypes.guess_type(str(file))[0] or 'application/octet-stream')

    def do_POST(self):
        if not self.valid_origin(post=True): return self.reply(403, {'error': 'Origin rejected.'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(415, {'error': 'JSON required.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 8192: raise ValueError()
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError()
        except (ValueError, OSError): return self.reply(400, {'error': 'Invalid request.'})
        path = urlsplit(self.path).path
        if path == '/api/session':
            if body: return self.reply(400, {'error': 'Empty session request required.'})
            token = self.server.sessions.create()
            return self.reply(201 if token else 503, {'session': token} if token else {'error': 'Kitchens full. Please try again later.'})
        if path == '/api/contribution/delete':
            if set(body) != {'id','deletion_token'} or not self.server.sessions.store:
                return self.reply(400, {'error':'Invalid deletion receipt.'})
            ok = self.server.sessions.store.delete(body['id'],body['deletion_token'])
            return self.reply(200 if ok else 404, {'deleted':ok})
        if path not in FIELDS or set(body) - FIELDS[path] - {'game_id', 'request_id'}:
            return self.reply(400, {'error': 'Unsupported request fields.'})
        game = self.session()
        if not game: return self.reply(401, {'error': 'Session expired. Refresh this page.'})
        try:
            with game.lock:
                if path == '/api/model/result':
                    ok = bool(game.relay and game.relay.resolve(body))
                    return self.reply(200 if ok else 409, {'ok': ok})
                status, result = game.command(path, body)
        except (ValueError, TypeError, KeyError, OverflowError):
            return self.reply(400, {'error': 'Invalid game command.'})
        self.reply(status, result)


def make_server(port, origin, capacity=8, web_root=None, data_dir=None):
    server = ThreadingHTTPServer(('127.0.0.1', port), HostedHandler)
    server.public_origin = origin.rstrip('/')
    server.sessions = Sessions(capacity, store=ContributionStore(data_dir) if data_dir else None)
    server.web_root = Path(web_root or ROOT / 'cocos-kitchen' / 'build' / 'web')
    return server


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8780)
    p.add_argument('--origin', required=True)
    p.add_argument('--web-root', type=Path)
    p.add_argument('--data-dir', type=Path, help='Enable opt-in 30-day contributions in this private directory.')
    p.add_argument('--max-sessions', type=int, default=8)
    args = p.parse_args()
    url = urlsplit(args.origin)
    if url.scheme != 'https' and url.hostname not in ('127.0.0.1', 'localhost'):
        p.error('A public origin must use HTTPS.')
    if url.path not in ('', '/') or url.query or url.fragment or url.username or not url.netloc:
        p.error('Use an origin, without a path or credentials.')
    server = make_server(args.port, args.origin, args.max_sessions, web_root=args.web_root, data_dir=args.data_dir)
    def reap():
        while True:
            time.sleep(30)
            server.sessions.reap()
            if server.sessions.store: server.sessions.store.prune()
    threading.Thread(target=reap, daemon=True).start()
    print('ChefJeff hosted service ready; credentials and persistent journals disabled.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.sessions.close()
        server.server_close()


if __name__ == '__main__': main()
