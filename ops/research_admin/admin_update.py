"""Console-only code update paired with the configured game; game, data service and Nginx untouched."""
import fcntl
import http.client
import json
from pathlib import Path
import re
import shlex
import socket
import ssl
import time

import upgrade_admin as legacy
from release_binding import verify_game_release

WORK = Path('/root/chefjeff-admin-code-update')
CONFIG = Path('/etc/chefjeff-admin/config.json')
CURRENT = Path('/opt/chefjeff/current')
ADMIN_RELEASES = Path('/opt/chefjeff-admin/releases')
ADMIN_UNIT = Path('/etc/systemd/system/chefjeff-admin.service')
DATA_UNIT = Path('/etc/systemd/system/chefjeff-data.service')
BUNDLE_FILES = (*legacy.APP_FILES, 'release_binding.py', 'release_upgrade.py', 'upgrade_admin.py', 'admin_update.py', 'game-binding.json')
DATA_ARGUMENTS = ['--port', '8790', '--data-dir', '/var/lib/chefjeff-data', '--credentials', '/etc/chefjeff/data-server.json']
DATA_PROGRAMS = ('authority_runner.py', 'source_observer.py')
PROBE = 'Bearer invalid-probe'  # Not a token: proves Nginx forwards the header to the new code.


def unit_folder(text, program, arguments):
    starts = [line[10:] for line in text.splitlines() if line.startswith('ExecStart=')]
    argv = shlex.split(starts[0]) if len(starts) == 1 else []
    if (len(argv) != 2+len(arguments) or argv[0] != '/usr/bin/python3' or argv[2:] != arguments
            or not argv[1].endswith('/'+program) or Path(argv[1]).parent.parent != ADMIN_RELEASES):
        raise ValueError('服务入口与已核对的管理台布局不一致；不会覆盖。')
    return Path(argv[1]).parent


def state_of(bundle):
    manifest = json.loads((bundle/'manifest.json').read_text())
    if not re.fullmatch('[a-f0-9]{16}', manifest['bundle_id']):
        raise ValueError('管理包标识无效。')
    return manifest, WORK/manifest['bundle_id']


def save_state(work, state):
    legacy.write(work/'state.json', json.dumps(state, indent=2)+'\n')


def features():
    c = http.client.HTTPConnection('127.0.0.1', 8795, timeout=3)
    try:
        c.request('GET', '/healthz', headers={'Host': legacy.DOMAIN})
        r = c.getresponse(); body = json.loads(r.read(8192))
        return body.get('features', []) if r.status == 200 and body.get('admin_version') == 2 else []
    finally:
        c.close()


def wait(ready, message):
    for attempt in range(40):
        try:
            if ready():
                return
        except (OSError, ValueError, http.client.HTTPException):
            pass
        if attempt == 39:
            raise ValueError(message)
        time.sleep(.2)


def probe(path, expected, authorization=None):
    c = legacy.TLSConnection(legacy.DOMAIN, 443, timeout=5, context=ssl.create_default_context())
    headers = {'Host': legacy.DOMAIN}
    if authorization:
        headers['Authorization'] = authorization
    try:
        c.request('GET', path, headers=headers); r = c.getresponse(); r.read(4096)
        if r.status != expected:
            raise ValueError(f'HTTPS检查失败：{path}，HTTP {r.status}，预期{expected}。')
    finally:
        c.close()


def prepare(bundle):
    manifest, work = state_of(bundle)
    for name in BUNDLE_FILES:
        if legacy.sha((bundle/name).read_bytes()) != manifest['files'].get(name):
            raise ValueError('管理包校验失败：'+name)
    if work.exists():
        raise ValueError('这个管理包已经准备过；请核对 '+str(work)+'。')
    config_raw = CONFIG.read_bytes(); cfg = json.loads(config_raw)
    if (cfg.get('origin') != 'https://'+legacy.DOMAIN or cfg.get('database') != '/var/lib/chefjeff-data/contributions.sqlite3'
            or cfg.get('auth') != '/etc/chefjeff-admin/auth.json'):
        raise ValueError('管理配置与已核对实例不一致。')
    game = Path(cfg['release']).resolve(strict=True)
    current = CURRENT.resolve(strict=True)
    # Only the console changes and its game binding stays as configured, so the package must
    # pair with the game the console already imports. The data service follows `current`.
    verify_game_release(game, bundle)
    for unit, path in (('chefjeff-admin.service', ADMIN_UNIT), ('chefjeff-data.service', DATA_UNIT)):
        if (legacy.property_value(unit, 'FragmentPath') != str(path) or legacy.property_value(unit, 'DropInPaths')
                or legacy.property_value(unit, 'ActiveState') != 'active'):
            raise ValueError('管理或数据服务状态与预期不同。')
    admin = ADMIN_UNIT.read_text()
    previous = unit_folder(admin, 'admin_server.py', ['--config', str(CONFIG)])
    if admin.count(str(previous)) != 2:
        raise ValueError('管理服务工作目录配置已变化。')
    data_folder = unit_folder(DATA_UNIT.read_text(), 'authority_runner.py', DATA_ARGUMENTS)
    for name in DATA_PROGRAMS:
        if legacy.sha((data_folder/name).read_bytes()) != manifest['files'][name]:
            raise ValueError('共享数据程序有变化，需要走完整发布升级：'+name)
    destination = ADMIN_RELEASES/('v2-'+manifest['bundle_id'])
    if destination.exists():
        raise ValueError('候选管理目录已存在，请先核对。')
    candidate = admin.replace(str(previous), str(destination))
    destination.mkdir(mode=0o755)
    for name in legacy.APP_FILES:
        legacy.write(destination/name, (bundle/name).read_bytes(), 0o644)
    work.mkdir(parents=True, mode=0o700)
    sources = {'previous-admin.service': admin.encode(), 'candidate-admin.service': candidate.encode()}
    for name, raw in sources.items():
        legacy.write(work/name, raw)
    save_state(work, {'phase': 'prepared', 'previous_admin': str(previous), 'new_admin': str(destination),
                      'game_release': str(game), 'current_game': str(current),
                      'config_sha256': legacy.sha(config_raw), 'auth': legacy.auth_stat(cfg['auth']),
                      'hashes': {name: legacy.sha(raw) for name, raw in sources.items()},
                      'app_hashes': {name: manifest['files'][name] for name in legacy.APP_FILES}})
    print(json.dumps({'status': 'admin-code-prepared', 'new_admin': str(destination), 'previous_admin': str(previous),
                      'console_game_release': str(game), 'current_game_release': str(current),
                      'console_game_binding_changed': False, 'database_opened': False, 'services_restarted': False,
                      'live_config_changed': False, 'activation_restarts': ['chefjeff-admin.service']}, indent=2))


def check(work, state):
    for name, checksum in state['hashes'].items():
        if legacy.sha((work/name).read_bytes()) != checksum:
            raise ValueError('审核或回退文件发生变化。')
    for name, checksum in state['app_hashes'].items():
        if legacy.sha((Path(state['new_admin'])/name).read_bytes()) != checksum:
            raise ValueError('已暂存的管理代码发生变化。')
    if legacy.sha(CONFIG.read_bytes()) != state['config_sha256']:
        raise ValueError('管理配置发生变化。')
    if legacy.auth_stat('/etc/chefjeff-admin/auth.json') != state['auth']:
        raise ValueError('账号文件发生变化。')
    if str(CURRENT.resolve(strict=True)) != state['current_game']:
        raise ValueError('当前游戏目录在准备后发生变化。')


def restore(work, state):
    legacy.write(ADMIN_UNIT, (work/'previous-admin.service').read_bytes(), 0o644)
    legacy.run('systemctl', 'daemon-reload')
    legacy.run('systemctl', 'restart', 'chefjeff-admin.service')
    state['phase'] = 'rolled-back'; save_state(work, state)
    wait(lambda: legacy.backend_health(None), '已还原管理服务单元，但原管理台尚未就绪，请保留输出检查。')


def activate(bundle):
    _, work = state_of(bundle)
    state = json.loads((work/'state.json').read_text())
    if state['phase'] == 'active':
        if 'export_token' not in features():
            raise ValueError('管理服务没有返回导出令牌功能标识，请检查。')
        return print('管理台代码已更新，无需重复激活。')
    if state['phase'] not in ('prepared', 'rolled-back'):
        raise ValueError('请先prepare-admin。')
    check(work, state)
    if legacy.sha(ADMIN_UNIT.read_bytes()) != state['hashes']['previous-admin.service']:
        raise ValueError('管理服务配置在准备后发生变化，不会覆盖。')
    verify_game_release(Path(state['game_release']), bundle)
    before = {name: legacy.pid(name) for name in ('chefjeff.service', 'chefjeff-data.service')}
    try:
        legacy.write(ADMIN_UNIT, (work/'candidate-admin.service').read_bytes(), 0o644)
        legacy.run('systemctl', 'daemon-reload')
        legacy.run('systemctl', 'restart', 'chefjeff-admin.service')
        wait(lambda: 'export_token' in features(), '新版管理服务未就绪。')
        for path, status, header in (('/research-admin/login', 200, None), ('/research-admin/api/records', 401, None),
                                     ('/research-admin/api/options', 403, PROBE), ('/research-admin/api/records', 401, PROBE)):
            probe(path, status, header)
        check(work, state)
        if {name: legacy.pid(name) for name in before} != before:
            raise ValueError('游戏或共享数据服务进程发生变化，请检查。')
    except BaseException:
        restore(work, state)
        raise
    state['phase'] = 'active'; save_state(work, state)
    print(json.dumps({'status': 'admin-code-active', 'new_admin': state['new_admin'], 'previous_admin_preserved': True,
                      'restarted': ['chefjeff-admin.service'], 'game_and_data_unchanged': True, 'nginx_changed': False,
                      'account_preserved': True, 'login_again_required': True, 'player_records_read': False}, indent=2))


def rollback(bundle):
    _, work = state_of(bundle)
    state = json.loads((work/'state.json').read_text())
    if state['phase'] != 'active':
        raise ValueError('这个管理包没有处于启用状态。')
    if legacy.sha(ADMIN_UNIT.read_bytes()) != state['hashes']['candidate-admin.service']:
        raise ValueError('启用后管理服务配置又有变化，请先人工核对。')
    restore(work, state)
    print('已恢复原管理台程序目录；游戏、共享数据服务、Nginx、账号和导出令牌文件均未改动。')


def main(command, bundle):
    if socket.gethostname() != 'VM-0-5-ubuntu':
        raise ValueError('仅限已核对的上海实例。')
    WORK.mkdir(mode=0o700, exist_ok=True)
    with (WORK/'update.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return {'prepare-admin': prepare, 'activate-admin': activate, 'rollback-admin': rollback}[command](bundle)
