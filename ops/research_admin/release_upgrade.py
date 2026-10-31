"""Reviewed v2-to-new-release adapter update; no player database access or link switches."""
import json
import os
from pathlib import Path
import shlex
import socket
import time
import fcntl

import upgrade_admin as legacy
from release_binding import verify_game_release

WORK = Path('/root/chefjeff-admin-release-upgrade')
CONFIG = Path('/etc/chefjeff-admin/config.json')
CURRENT = Path('/opt/chefjeff/current')
RELEASES = Path('/opt/chefjeff/releases')
ADMIN_RELEASES = Path('/opt/chefjeff-admin/releases')
ADMIN_UNIT = Path('/etc/systemd/system/chefjeff-admin.service')
DATA_UNIT = Path('/etc/systemd/system/chefjeff-data.service')
LEGACY_GAME = Path('/opt/chefjeff/releases/china-en-v4-269d7af296be/chefjeff-web-demo')
LEGACY_ADMIN = Path('/opt/chefjeff-admin/releases/v2-21cdee2e28e3fcb9')
LEGACY_PROGRAMS = {
    'admin_server.py': 'd2116c6c9854d58aae6fbb27a154d5a26885c89602a922b352df980021e8ac62',
    'admin_data.py': '80d5ae4631fefe26c83a798024681bd50b0c1c286c2e5ea4ccdd661300e6c4a9',
    'source_observer.py': '291b3197fc5aeed3937a00a56d97da9905ab0f8784dbc265618d5ce3ebc1d88d',
    'authority_runner.py': '2b20dd59a2641ed6f482eaa5080b6ef8e6d46dad9d32ab5f899f409ec9239f36',
    'app.js': '1755af29a27df57b455eaa87a236f2c729ea0d766e8f2e683a5c0d5f0b103bdf',
    'dashboard.js': '9d37bd3cc59268e38494f1ea230c2084f702a0616bdc9644dacad387434d9580',
    'charts.js': '82ea010e0b7520515b97ff53b7e75c26806c641905a1dc2f20d95b9bad75abf9',
    'app.css': '5cb7301f321c604243344e3d5b5cbce39acc3bcf32d40430e3206df5ab66156d',
    'index.html': '42671cfe11da51d7ff5d3b524a6d52835a1a9f2693e037121dba58a3220c3699',
    'login.html': '93ecd860987f80c978b3eb72527977d2690504842aca1e6f87dd1e7eed7545f4',
    'chefjeff-pixel.woff2': '043eae5e616b0d1e75dc746d3d687b4413f9f1c70c1a09bc4ebb705ef1cc8e32',
    'OFL.txt': 'a0e37147ea540c0a2f46039aac2c8fa42b0457018cb49bcd6a5771619c46a7a7',
}


def read_state():
    return json.loads((WORK/'state.json').read_text())


def save_state(state):
    legacy.write(WORK/'state.json', json.dumps(state,indent=2)+'\n')


def unit_candidates(admin, data, destination):
    old = str(LEGACY_ADMIN)
    expected_admin = ['/usr/bin/python3', old+'/admin_server.py', '--config', str(CONFIG)]
    expected_data = ['/usr/bin/python3', old+'/authority_runner.py', '--port', '8790',
                     '--data-dir', '/var/lib/chefjeff-data', '--credentials', '/etc/chefjeff/data-server.json']
    for text, expected in ((admin,expected_admin),(data,expected_data)):
        starts=[line[10:] for line in text.splitlines() if line.startswith('ExecStart=')]
        if len(starts)!=1 or shlex.split(starts[0])!=expected:
            raise ValueError('服务入口与已核对的v2实例不一致；不会覆盖。')
    if admin.count(old)!=2 or data.count(old)!=1:
        raise ValueError('服务工作目录引用与已核对配置不一致。')
    return admin.replace(old,str(destination)), data.replace(old,str(destination))


def prepare(target, bundle):
    if target is None or not target.is_absolute() or not target.resolve().is_relative_to(RELEASES.resolve()):
        raise ValueError('必须明确指定已暂存的 --game-release 发布目录。')
    if (WORK/'state.json').exists():
        raise ValueError('已有发布升级状态；请先核对，不会覆盖回退资料。')
    target=verify_game_release(target,bundle)
    if CURRENT.resolve(strict=True)!=LEGACY_GAME:
        raise ValueError('当前游戏不是已核对的269d7af版本。')
    config_raw=CONFIG.read_bytes();cfg=json.loads(config_raw)
    if (Path(cfg['release']).resolve()!=LEGACY_GAME or cfg['origin']!='https://'+legacy.DOMAIN
            or cfg['database']!='/var/lib/chefjeff-data/contributions.sqlite3'
            or cfg['auth']!='/etc/chefjeff-admin/auth.json'):
        raise ValueError('管理配置与已核对实例不一致。')
    for unit,path in (('chefjeff-admin.service',ADMIN_UNIT),('chefjeff-data.service',DATA_UNIT)):
        if (legacy.property_value(unit,'FragmentPath')!=str(path)
                or legacy.property_value(unit,'DropInPaths')
                or legacy.property_value(unit,'ActiveState')!='active'):
            raise ValueError('管理或数据服务状态与已核对实例不一致。')
    for name,checksum in LEGACY_PROGRAMS.items():
        if legacy.sha((LEGACY_ADMIN/name).read_bytes())!=checksum:
            raise ValueError('已安装管理程序发生变化：'+name)
    manifest=json.loads((bundle/'manifest.json').read_text())
    names=(*legacy.APP_FILES,'release_binding.py','release_upgrade.py','upgrade_admin.py','game-binding.json')
    for name in names:
        if legacy.sha((bundle/name).read_bytes())!=manifest['files'][name]:
            raise ValueError('管理包校验失败：'+name)
    import re
    if not re.fullmatch('[a-f0-9]{16}',manifest['bundle_id']):raise ValueError('管理包标识无效。')
    destination=ADMIN_RELEASES/('v2-'+manifest['bundle_id'])
    if destination.exists():raise ValueError('候选管理目录已存在，请先核对。')
    old_admin=ADMIN_UNIT.read_bytes();old_data=DATA_UNIT.read_bytes()
    admin,data=unit_candidates(old_admin.decode(),old_data.decode(),destination)
    cfg['release']=str(target)
    candidate_config=(json.dumps(cfg,indent=2)+'\n').encode()
    auth=legacy.auth_stat(cfg['auth'])  # Metadata only, never read account contents.
    destination.mkdir(parents=True,mode=0o755)
    for name in legacy.APP_FILES:legacy.write(destination/name,(bundle/name).read_bytes(),0o644)
    sources={'game-binding.json':(bundle/'game-binding.json').read_bytes(),
             'previous-config.json':config_raw,'candidate-config.json':candidate_config,
             'previous-admin.service':old_admin,'candidate-admin.service':admin.encode(),
             'previous-data.service':old_data,'candidate-data.service':data.encode()}
    for name,raw in sources.items():legacy.write(WORK/name,raw)
    stat=CONFIG.stat()
    state={'phase':'prepared','target':str(target),'previous_game':str(LEGACY_GAME),
           'previous_admin':str(LEGACY_ADMIN),'new_admin':str(destination),'auth':auth,
           'config_owner':[stat.st_uid,stat.st_gid],'config_mode':stat.st_mode&0o777,
           'hashes':{name:legacy.sha(raw) for name,raw in sources.items()},
           'app_hashes':{name:manifest['files'][name] for name in legacy.APP_FILES}}
    save_state(state)
    print(json.dumps({'status':'admin-release-prepared','target':str(target),
                     'new_admin':str(destination),'database_opened':False,
                     'services_restarted':False,'live_config_changed':False},indent=2))


def check_backups(state):
    for name,checksum in state['hashes'].items():
        if legacy.sha((WORK/name).read_bytes())!=checksum:raise ValueError('审核或回退文件发生变化。')
    for name,checksum in state['app_hashes'].items():
        if legacy.sha((Path(state['new_admin'])/name).read_bytes())!=checksum:
            raise ValueError('已暂存的管理代码发生变化。')
    if legacy.auth_stat('/etc/chefjeff-admin/auth.json')!=state['auth']:
        raise ValueError('账号文件发生变化。')


def write_config(raw,state):
    legacy.write(CONFIG,raw,state['config_mode'])
    os.chown(CONFIG,*state['config_owner'])


def restore(state):
    check_backups(state)
    # Never switch the game link or start an authority of a different consent version.
    # The coordinated two-site operator flow owns game/data restarts after rollback.
    legacy.run('systemctl','stop','chefjeff-admin.service')
    legacy.run('systemctl','stop','chefjeff-data.service')
    write_config((WORK/'previous-config.json').read_bytes(),state)
    for path,name in ((ADMIN_UNIT,'previous-admin.service'),(DATA_UNIT,'previous-data.service')):
        legacy.write(path,(WORK/name).read_bytes(),0o644)
    legacy.run('systemctl','daemon-reload')
    state['phase']='rolled-back';save_state(state)


def activate():
    state=read_state();check_backups(state)
    if state['phase']!='prepared':raise ValueError('需要prepared状态，不能重复或跨阶段激活。')
    if str(CURRENT.resolve(strict=True))!=state['target']:
        raise ValueError('尚未切换到已审核的目标游戏目录。')
    # Both game services must be stopped in the same maintenance window. The remote
    # stop is verified by the operator, never inferred from a network timeout.
    if legacy.property_value('chefjeff.service','ActiveState')!='inactive':
        raise ValueError('请先在同一维护窗口停止两站游戏。')
    for path,name in ((CONFIG,'previous-config.json'),(ADMIN_UNIT,'previous-admin.service'),(DATA_UNIT,'previous-data.service')):
        if legacy.sha(path.read_bytes())!=state['hashes'][name]:raise ValueError('线上配置在准备后发生变化。')
    verify_game_release(Path(state['target']),WORK)
    try:
        legacy.run('systemctl','stop','chefjeff-admin.service')
        legacy.run('systemctl','stop','chefjeff-data.service')
        write_config((WORK/'candidate-config.json').read_bytes(),state)
        for path,name in ((ADMIN_UNIT,'candidate-admin.service'),(DATA_UNIT,'candidate-data.service')):
            legacy.write(path,(WORK/name).read_bytes(),0o644)
        legacy.run('systemctl','daemon-reload')
        legacy.run('systemctl','start','chefjeff-data.service')
        legacy.run('systemctl','start','chefjeff-admin.service')
        for attempt in range(40):
            try:
                if legacy.backend_health() and legacy.data_ready():break
            except (OSError,ValueError):pass
            if attempt==39:raise ValueError('新版管理或数据服务未就绪。')
            time.sleep(.2)
        for path,status in (('/research-admin/login',200),('/research-admin/api/records',401)):
            legacy.protected_https(path,status)
        if legacy.auth_stat('/etc/chefjeff-admin/auth.json')!=state['auth']:
            raise ValueError('账号文件发生变化。')
    except BaseException:
        restore(state)
        raise
    state['phase']='active';save_state(state)
    print(json.dumps({'status':'admin-release-active','game_release':state['target'],
                     'previous_admin_preserved':True,'account_preserved':True,
                     'player_records_read':False,'nginx_changed':False},indent=2))


def rollback():
    state=read_state()
    if state['phase']!='active':raise ValueError('当前没有已启用的发布升级。')
    for path,name in ((CONFIG,'candidate-config.json'),(ADMIN_UNIT,'candidate-admin.service'),(DATA_UNIT,'candidate-data.service')):
        if legacy.sha(path.read_bytes())!=state['hashes'][name]:raise ValueError('升级后的配置已变化，先核对。')
    restore(state)
    print('已恢复管理配置和单元，服务保持停止；请协调回退两站游戏目录后再启动。')


def main(command,target,bundle):
    if socket.gethostname()!='VM-0-5-ubuntu':raise ValueError('仅限已核对的上海实例。')
    WORK.mkdir(mode=0o700,exist_ok=True)
    with (WORK/'release.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if command=='prepare-release':return prepare(target,bundle)
        return {'activate-release':activate,'rollback-release':rollback}[command]()
