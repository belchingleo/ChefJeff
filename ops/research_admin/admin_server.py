#!/usr/bin/env python3
"""Private browser console; separate from the game, read-only production access."""
import argparse
from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import http.client
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import admin_data as data

PREFIX = '/research-admin/'
COOKIE = '__Secure-ChefJeffAdmin'
IDLE_SECONDS = 1800
MAX_SECONDS = 8 * 3600
MAX_EXPORT = 280_000_000
# The export token reaches only these read routes; it never logs in or changes the account.
TOKEN_SCOPE = {('GET', PREFIX+'api/records'): 'records', ('GET', PREFIX+'api/preview'): 'preview',
               ('GET', PREFIX+'download/research.cjresearch.zip'): 'download',
               ('POST', PREFIX+'download/selected.cjresearch.zip'): 'selected'}
TOKEN_FORMAT = 'chefjeff-export-token-v1'
TOKEN_PATTERN = re.compile(r'cjx1\.([a-f0-9]{8})\.([A-Za-z0-9_-]{43})')
TOKEN_FAILURES = 10


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def credentials(username, password):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,40}', username):
        raise ValueError('用户名只能用字母、数字、下划线、点或短横线。')
    if not 16 <= len(password) <= 256:
        raise ValueError('密码需要16至256个字符。')
    salt = secrets.token_hex(16)
    return dict(username=username, salt=salt, password_hash=password_hash(password, salt))


def export_token(days, now=None):
    """Return the token, shown once, and the record that stores only its scrypt hash."""
    if not 1 <= days <= 365:
        raise ValueError('有效天数需要在1至365之间。')
    now = int(time.time() if now is None else now)
    identifier, secret, salt = secrets.token_hex(4), secrets.token_urlsafe(32), secrets.token_hex(16)
    record = dict(format=TOKEN_FORMAT, id=identifier, salt=salt, token_hash=password_hash(secret, salt),
                  issued_at=now, expires_at=now+days*86400)
    return 'cjx1.'+identifier+'.'+secret, record


def token_path(config):
    return Path(config['auth']).with_name('export-token.json')


def filters(query):
    if set(query) - {'since', 'until', 'level', 'schema', 'site', 'page'}:
        raise ValueError('不支持的筛选条件。')
    if any(len(v) != 1 or len(v[0]) > 80 for v in query.values()):
        raise ValueError('筛选条件格式错误。')
    result = {}
    for key in ('since', 'until'):
        value = query.get(key, [''])[0]
        if value:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError('日期格式应为年-月-日。')
            date = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            if key == 'until':
                date += timedelta(days=1)  # UI end date is inclusive; exporter is exclusive.
            result[key] = date.isoformat()
    if result.get('since', '') >= result.get('until', '9999'):
        raise ValueError('开始日期不能晚于结束日期。')
    level = query.get('level', [''])[0]
    if level:
        if not re.fullmatch(r'[1-9][0-9]{0,5}', level):
            raise ValueError('不支持的关卡。')
        result['level'] = int(level)
    schema = query.get('schema', [''])[0]
    if schema:
        if schema not in ('chefjeff-pilot-session-v1', 'chefjeff-pilot-session-v2'):
            raise ValueError('不支持的记录版本。')
        result['schema'] = schema
    site=query.get('site',[''])[0]
    if site:
        if site not in data.SITES:
            raise ValueError('站点筛选不正确。')
        result['site']=site
    page = query.get('page', ['1'])[0]
    if not re.fullmatch(r'[1-9][0-9]{0,4}', page):
        raise ValueError('页码不正确。')
    return result, int(page)


def read_connection(database):
    connection = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True, timeout=2)
    connection.execute('PRAGMA query_only=ON')
    return connection


def record_index(database, selected, page):
    return data.index(database, selected, page)

class AdminServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, config, exporter, verifier):
        super().__init__(address, AdminHandler)
        self.config = config
        self.exporter, self.verifier = exporter, verifier
        self.auth = json.loads(Path(config['auth']).read_text())
        self.sessions = {}
        self.failures = deque()
        self.token_failures = deque()
        self.lock = threading.Lock()
        self.export_lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(6)

    def process_request(self, request, address):
        if not self.slots.acquire(False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        # Never include URLs, cookies, passwords, bodies, database rows or tracebacks.
        sys.stderr.write('Admin request failed.\n')


class AdminHandler(BaseHTTPRequestHandler):
    server_version = 'ChefJeffAdmin'
    sys_version = ''
    _audit = None
    _token = None

    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def headers_for(self, status, content_type, length, extra=None):
        self._sent = True
        if self._audit:
            # Fixed route name, status and token label only: no token, query, IP or record content.
            sys.stderr.write('export-token '+self._audit+' '+str(status)+' id='+(self._token or '-')+'\n')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store, private')
        self.send_header('X-Content-Type-Options', 'nosniff')
        # Preserve same-origin form Origin; no-referrer makes Chromium send Origin:null.
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header('Connection', 'close')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.close_connection = True

    def reply(self, status, value, content_type='application/json; charset=utf-8', extra=None):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, allow_nan=False)
        raw = value.encode() if isinstance(value, str) else value
        self.headers_for(status, content_type, len(raw), extra)
        self.wfile.write(raw)

    def session(self):
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookies[COOKIE].value if COOKIE in cookies else ''
        except CookieError:
            return None
        now = time.monotonic()
        with self.server.lock:
            self.server.sessions = {k: v for k, v in self.server.sessions.items()
                                    if now - v['seen'] < IDLE_SECONDS and now - v['created'] < MAX_SECONDS}
            found = self.server.sessions.get(token)
            if found:
                found['seen'] = now
                return token

    def bearer(self):
        """Return the active token's label, or None; cookies are never consulted here."""
        header = self.headers.get('Authorization', '')
        match = TOKEN_PATTERN.fullmatch(header[7:]) if header.startswith('Bearer ') else None
        if not match:
            return None
        try:
            stored = json.loads(token_path(self.server.config).read_text())
        except FileNotFoundError:
            return None  # Revoked or never issued.
        if (stored.get('format') != TOKEN_FORMAT or time.time() >= stored['expires_at']
                or not hmac.compare_digest(match[1], stored['id'])):
            return None
        if not hmac.compare_digest(password_hash(match[2], stored['salt']), stored['token_hash']):
            return None
        return stored['id']

    def token_allowed(self, method, path):
        """Authorization requests use only the export token and never touch login sessions."""
        self._audit = method+' '+TOKEN_SCOPE.get((method, path), 'other')
        if (method, path) not in TOKEN_SCOPE:
            self.reply(403, {'error': '导出令牌只能读取记录和下载研究包。'})
            return False
        now = time.monotonic()
        with self.server.lock:
            while self.server.token_failures and now - self.server.token_failures[0] > 60:
                self.server.token_failures.popleft()
            limited = len(self.server.token_failures) >= TOKEN_FAILURES
        if limited:  # Checked before hashing, so invalid tokens cannot spend scrypt time.
            self.reply(429, {'error': '令牌尝试过于频繁，请一分钟后重试。'})
            return False
        self._token = self.bearer()
        if not self._token:
            with self.server.lock:
                self.server.token_failures.append(now)
            self.reply(401, {'error': '导出令牌无效、已过期或已吊销。'})
            return False
        return True

    def same_origin(self):
        return (self.headers.get('Origin') == self.server.config['origin'] and
                self.headers.get('Sec-Fetch-Site') not in ('cross-site', 'none'))

    def valid_host(self):
        return self.headers.get('Host') == urlsplit(self.server.config['origin']).netloc

    def do_GET(self):
        try:
            self.get()
        except data.RecordGone:
            self.reply(410, {'error': '记录已到期、撤回或不在当前范围内，请刷新列表后重选。'})
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, http.client.HTTPException):
            if not getattr(self, '_sent', False):
                self.reply(503, {'error': '数据暂时不可用，请稍后重试；没有修改原始记录。'})
            self.close_connection = True

    def get(self):
        if not self.valid_host():
            return self.reply(403, {'error': '请求地址不正确。'})
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == '/healthz':
            return self.reply(200, {'ok': True, 'database_opened': False, 'admin_version': 2,
                                    'features': ['selected_download', 'record_preview', 'custom_charts', 'dynamic_levels', 'regional_usage', 'source_filter', 'export_token']})
        assets = {'app.css': 'text/css; charset=utf-8', 'app.js': 'application/javascript; charset=utf-8', 'charts.js':'application/javascript; charset=utf-8', 'dashboard.js':'application/javascript; charset=utf-8',
                  'chefjeff-pixel.woff2': 'font/woff2', 'OFL.txt': 'text/plain; charset=utf-8'}
        if path in [PREFIX+name for name in assets]:
            name = path.rsplit('/', 1)[1]
            return self.reply(200, (Path(__file__).parent/name).read_bytes(), assets[name])
        if path == PREFIX+'login':
            return self.reply(200, (Path(__file__).parent/'login.html').read_bytes(), 'text/html; charset=utf-8')
        if not path.startswith(PREFIX):
            return self.reply(404, {'error': '未找到页面。'})
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return self.reply(403, {'error': '请从管理页访问。'})
        if 'Authorization' in self.headers:
            if not self.token_allowed('GET', path):
                return
        elif not self.session():
            if path == PREFIX:
                return self.reply(303, b'', extra={'Location': PREFIX+'login'})
            return self.reply(401, {'error': '登录已过期，请重新登录。'})
        if path == PREFIX:
            return self.reply(200, (Path(__file__).parent/'index.html').read_bytes(), 'text/html; charset=utf-8')
        if path == PREFIX+'api/options':
            return self.reply(200, {'levels': data.available_levels(self.server.config['database']),
                'groups': data.GROUPS, 'metrics': {k: {'label':v[0], 'unit':v[1]} for k,v in data.METRICS.items()},
                'sites':data.SITES,'source_tracking_since':data.source_index(self.server.config['database'])['tracking_since']})
        if path == PREFIX+'api/regional-usage':
            return self.reply(200,data.regional_usage(self.server.config['database']))
        if path == PREFIX+'api/preview':
            try:
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=3)
                if set(query)-{'ref','offset','type'} or any(len(v)!=1 for v in query.values()):
                    raise ValueError('预览参数不正确。')
                ref = query.get('ref',[''])[0]
                data.references([ref])
                offset = query.get('offset',['0'])[0]
                event_type = query.get('type',[''])[0]
                if not re.fullmatch(r'0|[1-9][0-9]{0,5}',offset) or not re.fullmatch(r'[A-Za-z0-9_.:-]{0,80}',event_type):
                    raise ValueError('事件筛选或页码不正确。')
                result = data.preview(self.server.config['database'],ref,self.server.exporter,int(offset),event_type)
            except ValueError:
                return self.reply(400, {'error':'记录或预览参数未通过校验；请刷新，或核对数据版本。'})
            return self.reply(200, result)
        if path == PREFIX+'api/analysis':
            try:
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=10)
                if any(len(v)!=1 for v in query.values()):
                    raise ValueError('图表参数重复。')
                group = query.pop('group',['day'])[0]
                metric = query.pop('metric',['records'])[0]
                refs = query.pop('refs',[None])[0]
                if refs is not None:
                    refs = data.references(json.loads(refs))
                selected, _ = filters(query)
                result = data.analysis(self.server.config['database'],selected,group,metric,refs)
            except ValueError:
                return self.reply(400, {'error':'请核对图表分组、指标和筛选范围。'})
            return self.reply(200,result)
        if path in (PREFIX+'api/usage', PREFIX+'download/usage.json'):
            if parsed.query:
                return self.reply(400, {'error': '统计不接受筛选参数。'})
            connection = http.client.HTTPConnection('127.0.0.1', self.server.config.get('game_port', 8780), timeout=5)
            try:
                connection.request('GET', '/ops/usage', headers={'Host': urlsplit(self.server.config['origin']).netloc})
                response = connection.getresponse()
                raw = response.read(2_000_001)
                if response.status != 200 or len(raw) > 2_000_000:
                    raise ValueError('Usage unavailable')
                usage = json.loads(raw)['usage']
                if not isinstance(usage, dict):
                    raise ValueError('Invalid usage')
            finally:
                connection.close()
            extra = {'Content-Disposition': 'attachment; filename="chefjeff-usage.json"'} if '/download/' in path else None
            return self.reply(200, {'usage': usage, 'fetched_at': datetime.now(timezone.utc).isoformat()}, extra=extra)
        if path in (PREFIX+'api/records', PREFIX+'download/research.cjresearch.zip'):
            try:
                selected, page = filters(parse_qs(parsed.query, keep_blank_values=True, max_num_fields=8))
            except ValueError as error:
                return self.reply(400, {'error': str(error)})
            if path.endswith('api/records'):
                return self.reply(200, record_index(self.server.config['database'], selected, page))
            return self.download(selected)
        self.reply(404, {'error': '未找到页面。'})

    def download(self, selected, refs=None):
        if not self.server.export_lock.acquire(False):
            return self.reply(429, {'error': '另一份研究包正在生成，请稍后重试。'})
        source = None
        try:
            with tempfile.TemporaryDirectory(dir=self.server.config['temporary']) as folder:
                package = Path(folder)/'records.cjresearch.zip'
                try:
                    selected = dict(selected)
                    site = selected.pop('site',None)
                    exporter = self.server.exporter if refs is None and site is None else data.selected_exporter(self.server.exporter,refs,site)
                    manifest = exporter(self.server.config['database'], package, **selected)
                    manifest = data.add_source_artifact(package,self.server.config['database'],manifest)
                except ValueError:
                    return self.reply(422, {'error': '没有可导出的有效记录，或记录未通过格式校验。'})
                if package.stat().st_size > MAX_EXPORT:
                    return self.reply(413, {'error': '研究包较大，请缩短日期范围后下载。'})
                # Recheck withdrawal, expiry and updates immediately before serving.
                self.server.verifier(package, database=self.server.config['database'])
                if self._token and self.bearer() != self._token:
                    return self.reply(401, {'error': '导出令牌已过期或已吊销，研究包没有发送。'})
                if not self._token and not self.session():
                    return self.reply(401, {'error': '登录已过期，请重新登录。'})
                size, expires = package.stat().st_size, str(int(manifest['expires']))
                # Open it before the folder is removed: nothing stays on disk while the package is sent.
                source = package.open('rb')
            self.headers_for(200, 'application/zip', size, {
                'Content-Disposition': 'attachment; filename="chefjeff-research.cjresearch.zip"',
                'X-Research-Expires': expires})
            while chunk := source.read(65536):
                self.wfile.write(chunk)
        finally:
            if source is not None:
                source.close()
            self.server.export_lock.release()

    def do_POST(self):
        try:
            self.post()
        except data.RecordGone:
            self.reply(410, {'error':'所选记录已到期或撤回，请刷新后重新选择。'})
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, http.client.HTTPException):
            if not getattr(self,'_sent',False):
                self.reply(503, {'error':'数据暂时不可用，请稍后重试；没有修改原始记录。'})
            self.close_connection=True

    def post(self):
        if not self.valid_host():
            return self.reply(403, {'error': '请求来源不正确。'})
        if 'Authorization' in self.headers:
            # Browsers never attach this header on their own, so the cookie Origin check does not apply.
            if not self.token_allowed('POST', self.path):
                return
        elif not self.same_origin():
            return self.reply(403, {'error': '请求来源不正确。'})
        if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
            return self.reply(400, {'error': '请求格式不正确。'})
        if self.path == PREFIX+'download/selected.cjresearch.zip' and not self._token and not self.session():
            return self.reply(401, {'error':'请先登录。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError()
            body = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True, max_num_fields=2)
        except (ValueError, UnicodeError):
            return self.reply(400, {'error': '请求格式不正确。'})
        if self.path == PREFIX+'download/selected.cjresearch.zip':
            try:
                if set(body) != {'refs'} or len(body['refs'])!=1:
                    raise ValueError()
                refs = data.references(json.loads(body['refs'][0]))
            except (ValueError, TypeError):
                return self.reply(400, {'error':'请勾选1至50条不同的记录。'})
            return self.download({},refs)
        if self.path == PREFIX+'logout':
            token = self.session()
            with self.server.lock:
                self.server.sessions.pop(token, None)
            return self.reply(303, b'', extra={'Location': PREFIX+'login', 'Set-Cookie': COOKIE+'=; Path='+PREFIX+'; Secure; HttpOnly; SameSite=Strict; Max-Age=0'})
        if self.path != PREFIX+'login':
            return self.reply(404, {'error': '未找到页面。'})
        if set(body) != {'username', 'password'} or any(len(v) != 1 for v in body.values()):
            return self.reply(400, {'error': '请填写用户名和密码。'})
        now = time.monotonic()
        # A bounded global throttle also covers attempts routed through the loopback proxy.
        with self.server.lock:
            while self.server.failures and now - self.server.failures[0] > 60:
                self.server.failures.popleft()
            if len(self.server.failures) >= 10:
                return self.reply(429, {'error': '尝试过于频繁，请一分钟后重试。'})
            self.server.failures.append(now)
        username, password = body['username'][0], body['password'][0]
        if len(username) > 100 or len(password) > 256:
            return self.reply(403, {'error': '用户名或密码不正确。'})
        auth = self.server.auth
        matched = hmac.compare_digest(password_hash(password, auth['salt']), auth['password_hash'])
        if not matched or not hmac.compare_digest(username.encode(), auth['username'].encode()):
            return self.reply(403, {'error': '用户名或密码不正确。'})
        token = secrets.token_urlsafe(32)
        with self.server.lock:
            self.server.sessions = {token: {'seen': now, 'created': now}}  # A new login revokes older sessions.
        return self.reply(303, b'', extra={'Location': PREFIX, 'Set-Cookie': COOKIE+'='+token+'; Path='+PREFIX+'; Secure; HttpOnly; SameSite=Strict; Max-Age='+str(MAX_SECONDS)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if config['origin'] != 'https://chefjeff.belchingleo.online':
        raise SystemExit('This build is scoped to the registered Shanghai game host.')
    release = Path(config['release']).resolve()
    sys.path.insert(0, str(release))
    from scripts.research_export import export_package, verify_package
    server = AdminServer(('127.0.0.1', 8795), config, export_package, verify_package)
    server.serve_forever()


if __name__ == '__main__':
    main()
