#!/usr/bin/env python3
"""Prepare, validate and install only the Shanghai private admin console."""
import argparse
import difflib
import fcntl
import getpass
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
DOMAIN = 'chefjeff.belchingleo.online'
HTTPS_PORT = 443
REVIEW = Path('/root/chefjeff-admin-review')
CONFIG = Path('/etc/chefjeff-admin')
UNIT = Path('/etc/systemd/system/chefjeff-admin.service')
APP_FILES = ('admin_server.py', 'admin_data.py', 'source_observer.py', 'authority_runner.py', 'app.js', 'dashboard.js', 'charts.js', 'app.css', 'index.html', 'login.html', 'chefjeff-pixel.woff2', 'OFL.txt')
STATE = REVIEW/'state.json'
SOURCE_EXPORTER_SHA = '7fc5deb54fe0ca068bb8836e92aa31a091cb571b0eb04f322eb15c0018bedcc9'

LOCATION = '''    # Private ChefJeff console; game and authority routes stay unchanged.
    location = /research-admin { return 301 /research-admin/; }
    location ^~ /research-admin/ {
        access_log off;
        error_log /dev/null;
        client_max_body_size 4k;
        client_body_buffer_size 8k;
        client_body_timeout 10s;
        proxy_http_version 1.1;
        proxy_set_header Host chefjeff.belchingleo.online;
        proxy_set_header Connection "";
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_cache off;
        proxy_max_temp_file_size 0;
        proxy_connect_timeout 3s;
        proxy_read_timeout 180s;
        proxy_pass http://127.0.0.1:8795;
    }
'''


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def write(path, raw, mode=0o600):
    path = Path(path)
    if isinstance(raw, str):
        raw = raw.encode()
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(raw)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_state(state):
    write(STATE, json.dumps(state, ensure_ascii=False, indent=2)+'\n')


def top_server_blocks(raw):
    """Tokenize quotes/comments as units so braces inside them cannot change nesting."""
    tokens = [(m.group(), m.start(), m.end()) for m in re.finditer(
        r'''\#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[{};]|[^\s{};\#]+''', raw)
        if not m.group().startswith('#')]
    stack = []
    for i, (token, start, end) in enumerate(tokens):
        if token == '{':
            stack.append((i, len(stack)))
        elif token == '}':
            if not stack:
                raise ValueError('Nginx括号不匹配。')
            opening, depth = stack.pop()
            if opening and tokens[opening-1][0] == 'server' and depth == 0:
                directives, statement, nesting = {}, [], 0
                for value, *_ in tokens[opening+1:i]:
                    if value == '{':
                        nesting += 1; statement = []
                    elif value == '}':
                        nesting -= 1; statement = []
                    elif value == ';' and nesting == 0:
                        if statement:
                            directives.setdefault(statement[0], []).append(statement[1:])
                        statement = []
                    elif nesting == 0:
                        statement.append(value.strip('"\''))
                yield tokens[opening][2], start, directives
    if stack:
        raise ValueError('Nginx括号不匹配。')


def patch_site(raw, include):
    candidates = []
    for opening, closing, directives in top_server_blocks(raw):
        names = sum(directives.get('server_name', []), [])
        tls = any(any(re.fullmatch(r'(?:\[.*\]:|[^: ]+:)?443', value) for value in line)
                  for line in directives.get('listen', []))
        if DOMAIN in names and tls:
            candidates.append(opening)
    if len(candidates) != 1 or '/research-admin' in raw or str(CONFIG/'nginx-location.conf') in raw:
        raise ValueError('未找到唯一的国内游戏HTTPS配置，或管理入口已存在；请保留输出核对。')
    at = candidates[0]
    return raw[:at]+'\n    include '+include+';'+raw[at:]


def service_unit(release):
    return f'''[Unit]
Description=ChefJeff private read-only browser console
After=network.target chefjeff.service

[Service]
Type=simple
User=chefjeff
Group=chefjeff
ExecStart=/usr/bin/python3 {release}/admin_server.py --config /etc/chefjeff-admin/config.json
WorkingDirectory={release}
Environment=PYTHONDONTWRITEBYTECODE=1
RuntimeDirectory=chefjeff-admin
RuntimeDirectoryMode=0700
UMask=0077
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
ReadOnlyPaths=/var/lib/chefjeff-data
ReadWritePaths=/run/chefjeff-admin
InaccessiblePaths=/etc/chefjeff /var/lib/chefjeff /etc/letsencrypt
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_UNIX
IPAddressDeny=any
IPAddressAllow=localhost
MemoryMax=384M
CPUQuota=30%
TasksMax=16

[Install]
WantedBy=multi-user.target
'''


def service_pid(name):
    return subprocess.check_output(['systemctl', 'show', name, '-p', 'MainPID', '--value'], text=True).strip()


def set_account():
    from admin_server import credentials
    username = input('管理用户名 [admin]：').strip() or 'admin'
    password = getpass.getpass('设置管理密码（至少16字符，不回显）：')
    confirmation = getpass.getpass('再次输入密码：')
    if password != confirmation:
        raise ValueError('两次密码不一致。')
    auth = credentials(username, password)
    write(CONFIG/'auth.json', json.dumps(auth)+'\n', 0o640)
    shutil.chown(CONFIG/'auth.json', user='root', group='chefjeff')


def prepare():
    if UNIT.exists():
        raise ValueError('管理服务单元已存在；本安装器不会覆盖已有服务。')
    if socket.gethostname() != 'VM-0-5-ubuntu':
        raise ValueError('只可在上海腾讯云服务器执行。')
    release = Path('/opt/chefjeff/current').resolve(strict=True)
    manifest = json.loads((HERE/'manifest.json').read_text())
    bound = 'game-binding.json' in manifest['files']
    if bound:
        from release_binding import verify_game_release
        verify_game_release(release, HERE)
    else:  # Compatibility with the already shipped, fixed-version v2 installer.
        if release != Path('/opt/chefjeff/releases/china-en-v4-269d7af296be/chefjeff-web-demo'):
            raise ValueError('当前游戏发布目录已变化，需要重新核对兼容性。')
        if digest((release/'scripts/research_export.py').read_bytes()) != SOURCE_EXPORTER_SHA:
            raise ValueError('研究导出程序与已核对版本不一致。')
    binding_files = ('release_binding.py','game-binding.json') if bound else ()
    for name in (*APP_FILES, 'install_admin.py', *binding_files):
        if digest((HERE/name).read_bytes()) != manifest['files'].get(name):
            raise ValueError('安装文件摘要不匹配：'+name)
    found = []
    for entry in sorted(Path('/etc/nginx/sites-enabled').iterdir()):
        path = entry.resolve(strict=True)
        try:
            raw = path.read_text()
            patched = patch_site(raw, str(CONFIG/'nginx-location.conf'))
            found.append((path, raw, patched))
        except ValueError:
            pass
    if len(found) != 1:
        raise ValueError('未找到唯一可添加管理入口的游戏配置；没有修改线上配置。')
    path, original, patched = found[0]
    app_release = Path('/opt/chefjeff-admin/releases')/manifest['bundle_id']
    app_release.mkdir(parents=True, exist_ok=True, mode=0o755)
    for name in APP_FILES:
        write(app_release/name, (HERE/name).read_bytes(), 0o644)
    CONFIG.mkdir(mode=0o750, exist_ok=True)
    shutil.chown(CONFIG, user='root', group='chefjeff')
    if not (CONFIG/'auth.json').exists():
        set_account()
    config = {'origin': 'https://'+DOMAIN, 'release': str(release), 'database': '/var/lib/chefjeff-data/contributions.sqlite3',
              'auth': str(CONFIG/'auth.json'), 'temporary': '/run/chefjeff-admin', 'game_port': 8780}
    write(REVIEW/'config.json', json.dumps(config, indent=2)+'\n')
    write(REVIEW/'original.nginx', original)
    write(REVIEW/'candidate.nginx', patched)
    write(REVIEW/'location.conf', LOCATION)
    write(REVIEW/'chefjeff-admin.service', service_unit(app_release))
    # Test the entire candidate Nginx config using a temporary include index.
    write(REVIEW/'validation-site.conf', patched.replace(str(CONFIG/'nginx-location.conf'), str(REVIEW/'location.conf')))
    includes = []
    for entry in sorted(Path('/etc/nginx/sites-enabled').iterdir()):
        target = REVIEW/'validation-site.conf' if entry.resolve() == path else entry
        includes.append('include "'+str(target)+'";')
    write(REVIEW/'validation-sites.conf', '\n'.join(includes)+'\n')
    master = Path('/etc/nginx/nginx.conf').read_text()
    master, count = re.subn(r'include\s+/etc/nginx/sites-enabled/\*\s*;', 'include '+str(REVIEW/'validation-sites.conf')+';', master)
    if count != 1:
        raise ValueError('主Nginx配置不是预期的站点引用形式，已停止准备。')
    write(REVIEW/'validation.conf', master)
    run('nginx', '-t', '-c', str(REVIEW/'validation.conf'))
    state = {'phase': 'prepared', 'site_file': str(path), 'original_sha256': digest(original.encode()),
             'candidate_sha256': digest(patched.encode()), 'site_mode': path.stat().st_mode & 0o777,
             'app_release': str(app_release), 'game_release': str(release)}
    save_state(state)
    print(''.join(difflib.unified_diff(original.splitlines(True), patched.splitlines(True), fromfile='现有游戏配置', tofile='候选游戏配置')))
    print(json.dumps({'status': 'admin-prepared', 'url': 'https://'+DOMAIN+'/research-admin/',
        'candidate_nginx_valid': True, 'services_restarted': False, 'nginx_changed': False,
        'database_opened': False, 'review_directory': str(REVIEW)}, ensure_ascii=False, indent=2))


def local_check(path, expected):
    c = http.client.HTTPConnection('127.0.0.1', 8795, timeout=5)
    try:
        c.request('GET', path, headers={'Host': DOMAIN})
        response = c.getresponse()
        response.read()
        if response.status != expected:
            raise ValueError('管理服务本机检查未通过。')
    finally:
        c.close()


class LoopbackHTTPSConnection(http.client.HTTPSConnection):
    """Verify the public host's certificate/SNI while connecting only to loopback."""
    def connect(self):
        raw = socket.create_connection(('127.0.0.1', HTTPS_PORT), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=DOMAIN)
        except BaseException:
            raw.close()
            raise


def https_probe(path):
    connection = LoopbackHTTPSConnection(DOMAIN, HTTPS_PORT, timeout=3,
                                        context=ssl.create_default_context())
    try:
        connection.request('GET', path, headers={'Host': DOMAIN, 'Connection': 'close'})
        response = connection.getresponse()
        response.read(4096)
        return response.status
    finally:
        connection.close()


def https_check(path, expected):
    # Reload is asynchronous: an old worker may accept the first fresh TLS connection.
    # Allow a bounded readiness period, preserving strict authentication expectations.
    last = '未收到响应'
    for attempt in range(12):
        try:
            status = https_probe(path)
            if status == expected:
                return
            last = 'HTTP '+str(status)
        except (OSError, http.client.HTTPException) as error:
            last = type(error).__name__
        if attempt < 11:
            time.sleep(.25)
    raise ValueError(f'HTTPS检查失败：{path}，预期HTTP {expected}，实际{last}；已尝试12次。')


def activate():
    state = json.loads(STATE.read_text())
    path = Path(state['site_file'])
    if state['phase'] == 'active':
        local_check('/research-admin/api/records', 401)
        https_check('/research-admin/', 303)
        print('管理入口已启用，无需重复激活。')
        return
    if state['phase'] not in ('prepared', 'rolled-back') or digest(path.read_bytes()) != state['original_sha256']:
        raise ValueError('准备后的站点配置已变化；不会覆盖，请先核对。')
    if str(Path('/opt/chefjeff/current').resolve()) != state['game_release']:
        raise ValueError('游戏发布目录已变化，请重新准备。')
    for name, field in [('original.nginx', 'original_sha256'), ('candidate.nginx', 'candidate_sha256')]:
        if digest((REVIEW/name).read_bytes()) != state[field]:
            raise ValueError('审核文件摘要变化。')
    before = {name: service_pid(name) for name in ('chefjeff.service', 'chefjeff-data.service')}
    try:
        for name in ('config.json',):
            write(CONFIG/name, (REVIEW/name).read_bytes(), 0o640)
            shutil.chown(CONFIG/name, user='root', group='chefjeff')
        write(CONFIG/'nginx-location.conf', LOCATION, 0o644)
        write(UNIT, (REVIEW/'chefjeff-admin.service').read_bytes(), 0o644)
        write(path, (REVIEW/'candidate.nginx').read_bytes(), state['site_mode'])
        run('nginx', '-t')
        run('systemctl', 'daemon-reload')
        run('systemctl', 'start', 'chefjeff-admin.service')
        # systemctl start may return before Python has bound its loopback socket.
        import time
        for attempt in range(30):
            try:
                local_check('/healthz', 200)
                break
            except (OSError, ValueError):
                if attempt == 29:
                    raise
                time.sleep(.2)
        local_check('/research-admin/api/records', 401)
        run('systemctl', 'reload', 'nginx.service')
        https_check('/research-admin/', 303)
        https_check('/research-admin/login', 200)
        https_check('/research-admin/api/records', 401)
        if before != {name: service_pid(name) for name in before}:
            raise ValueError('游戏或数据服务进程发生变化，请检查。')
        if str(Path('/opt/chefjeff/current').resolve()) != state['game_release']:
            raise ValueError('游戏发布软链接发生变化，请检查。')
        run('systemctl', 'enable', 'chefjeff-admin.service')
    except BaseException:
        write(path, (REVIEW/'original.nginx').read_bytes(), state['site_mode'])
        run('nginx', '-t')
        run('systemctl', 'reload', 'nginx.service')
        subprocess.run(['systemctl', 'disable', '--now', 'chefjeff-admin.service'], check=False)
        UNIT.unlink(missing_ok=True)
        run('systemctl', 'daemon-reload')
        raise
    state['phase'] = 'active'
    save_state(state)
    print(json.dumps({'status': 'admin-active', 'url': 'https://'+DOMAIN+'/research-admin/',
        'login_page': 200, 'unauthenticated_records': 401, 'tls_verified': True,
        'game_process_unchanged': True, 'shared_data_process_unchanged': True,
        'current_release_unchanged': True, 'database_opened_during_install': False,
        'account': '使用准备阶段设置的用户名与密码；请不要将密码发到聊天。'}, ensure_ascii=False, indent=2))


def rollback():
    state = json.loads(STATE.read_text())
    path = Path(state['site_file'])
    if digest(path.read_bytes()) != state['candidate_sha256']:
        raise ValueError('站点配置在安装后有变化，不能自动回退；请先核对。')
    write(path, (REVIEW/'original.nginx').read_bytes(), state['site_mode'])
    run('nginx', '-t')
    run('systemctl', 'reload', 'nginx.service')
    run('systemctl', 'disable', '--now', 'chefjeff-admin.service')
    UNIT.unlink(missing_ok=True)
    run('systemctl', 'daemon-reload')
    state['phase'] = 'rolled-back'; save_state(state)
    print('已移除管理入口；游戏、共享数据服务与数据库未改动，账号和代码保留。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'activate', 'rollback', 'password'))
    command = parser.parse_args().command
    if os.geteuid() != 0:
        raise SystemExit('请使用sudo执行；只在上海服务器操作。')
    REVIEW.mkdir(mode=0o700, exist_ok=True)
    with (REVIEW/'install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if command == 'password':
            set_account()
            run('systemctl', 'restart', 'chefjeff-admin.service')
        else:
            {'prepare': prepare, 'activate': activate, 'rollback': rollback}[command]()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit('管理台安装已暂停：'+str(error))
