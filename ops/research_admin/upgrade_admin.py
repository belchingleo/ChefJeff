#!/usr/bin/env python3
"""Operator-run upgrade; preserve account, game and Nginx. Restart admin/data only."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import tempfile
import time

HERE=Path(__file__).resolve().parent
WORK=Path('/root/chefjeff-admin-v2-upgrade')
STATE=WORK/'state.json'
ADMIN_UNIT=Path('/etc/systemd/system/chefjeff-admin.service')
DATA_UNIT=Path('/etc/systemd/system/chefjeff-data.service')
CONFIG=Path('/etc/chefjeff-admin/config.json')
DOMAIN='chefjeff.belchingleo.online'
APP_FILES=('admin_server.py','admin_data.py','source_observer.py','authority_runner.py','app.js','dashboard.js','charts.js','app.css','index.html','login.html','chefjeff-pixel.woff2','OFL.txt')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def run(*args):subprocess.run(args,check=True)


def write(path,raw,mode=0o600):
    if isinstance(raw,str):raw=raw.encode()
    fd,temporary=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw)
        os.chmod(temporary,mode);os.replace(temporary,path)
    finally:Path(temporary).unlink(missing_ok=True)


def property_value(unit,key):
    return subprocess.check_output(['systemctl','show',unit,'--value','-p',key],text=True).strip()


def pid(unit):return property_value(unit,'MainPID')


def auth_stat(path):
    stat=Path(path).stat()
    return [stat.st_ino,stat.st_size,stat.st_mtime_ns]


def replacement_units(admin_text,data_text,new_release):
    lines=admin_text.splitlines()
    starts=[line for line in lines if line.startswith('ExecStart=')]
    if len(starts)!=1:raise ValueError('管理服务启动配置不是预期形式。')
    argv=shlex.split(starts[0].split('=',1)[1])
    if (len(argv)!=4 or argv[0]!='/usr/bin/python3' or argv[2:]!=['--config','/etc/chefjeff-admin/config.json']
            or not argv[1].startswith('/opt/chefjeff-admin/releases/') or not argv[1].endswith('/admin_server.py')):
        raise ValueError('管理服务启动路径已变化，请先核对。')
    old_release=argv[1].rsplit('/',1)[0]
    if admin_text.count(old_release)!=2:raise ValueError('管理服务工作目录配置已变化。')
    new_admin=admin_text.replace(old_release,str(new_release))
    starts=[line for line in data_text.splitlines() if line.startswith('ExecStart=')]
    if len(starts)!=1:raise ValueError('共享数据服务启动配置不是预期形式。')
    argv=shlex.split(starts[0].split('=',1)[1])
    if (argv!=['/usr/bin/python3','/opt/chefjeff/current/shared_server.py','--port','8790',
               '--data-dir','/var/lib/chefjeff-data','--credentials','/etc/chefjeff/data-server.json']):
        raise ValueError('共享数据服务已有不同启动配置；不会覆盖，请先核对。')
    argv[1]=str(new_release/'authority_runner.py')
    new_data=data_text.replace(starts[0],'ExecStart='+shlex.join(argv))
    return new_admin,new_data,old_release


def prepare():
    if (HERE/'game-binding.json').exists():
        raise ValueError('此发布包请使用prepare-release并明确指定新游戏目录；不会套用旧版固定目录升级。')
    if socket.gethostname()!='VM-0-5-ubuntu':raise ValueError('仅限上海腾讯云服务器。')
    if STATE.exists() and json.loads(STATE.read_text()).get('phase')=='active':raise ValueError('v2已经启用；无需再次准备。')
    for name,path in [('chefjeff-admin.service',ADMIN_UNIT),('chefjeff-data.service',DATA_UNIT)]:
        if property_value(name,'FragmentPath')!=str(path) or property_value(name,'DropInPaths'):
            raise ValueError('服务单元位置或覆盖配置与预期不同。')
        if property_value(name,'ActiveState')!='active':raise ValueError('现有管理或数据服务未运行，请先核对。')
    manifest=json.loads((HERE/'manifest.json').read_text())
    if not re.fullmatch(r'[a-f0-9]{16}',manifest['bundle_id']):raise ValueError('安装包标识无效。')
    for name in (*APP_FILES,'upgrade_admin.py'):
        if sha((HERE/name).read_bytes())!=manifest['files'].get(name):raise ValueError('安装包文件摘要不一致：'+name)
    cfg=json.loads(CONFIG.read_text())
    if cfg.get('origin')!='https://'+DOMAIN or cfg.get('database')!='/var/lib/chefjeff-data/contributions.sqlite3':
        raise ValueError('管理台的数据源配置与预期不同。')
    auth=auth_stat(cfg['auth'])  # Metadata only: never read the password hash file.
    current=str(Path('/opt/chefjeff/current').resolve(strict=True))
    if Path(current)!=Path('/opt/chefjeff/releases/china-en-v4-269d7af296be/chefjeff-web-demo'):
        raise ValueError('游戏发布目录已变化，需要先核对来源适配器兼容性。')
    destination=Path('/opt/chefjeff-admin/releases')/('v2-'+manifest['bundle_id'])
    destination.mkdir(parents=True,exist_ok=True,mode=0o755)
    for name in APP_FILES:write(destination/name,(HERE/name).read_bytes(),0o644)
    original_admin=ADMIN_UNIT.read_text();original_data=DATA_UNIT.read_text()
    admin,data,previous=replacement_units(original_admin,original_data,destination)
    for name,raw in [('previous-admin.service',original_admin),('previous-data.service',original_data),
                     ('candidate-admin.service',admin),('candidate-data.service',data)]:write(WORK/name,raw)
    review=json.loads(Path('/root/chefjeff-admin-review/state.json').read_text())
    site=Path(review['site_file'])
    state={'phase':'prepared','bundle_id':manifest['bundle_id'],'new_release':str(destination),'previous_admin_release':previous,
           'previous_admin_sha256':sha(original_admin.encode()),'previous_data_sha256':sha(original_data.encode()),
           'candidate_admin_sha256':sha(admin.encode()),'candidate_data_sha256':sha(data.encode()),
           'auth_path':cfg['auth'],'auth_stat':auth,'game_release':current,'site_file':str(site),'site_sha256':sha(site.read_bytes())}
    write(STATE,json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'admin-v2-prepared','new_release':str(destination),'account_preserved':True,
        'nginx_unchanged':True,'database_opened':False,'services_restarted':False,
        'activation_restarts':['chefjeff-data.service','chefjeff-admin.service'],
        'game_service_will_not_restart':True},ensure_ascii=False,indent=2))


def backend_health(version=2):
    c=http.client.HTTPConnection('127.0.0.1',8795,timeout=3)
    try:
        c.request('GET','/healthz',headers={'Host':DOMAIN});r=c.getresponse();body=json.loads(r.read(8192))
        return r.status==200 and body.get('ok') is True and (version is None or body.get('admin_version')==version)
    finally:c.close()


def data_ready():
    c=http.client.HTTPConnection('127.0.0.1',8790,timeout=3)
    try:
        c.request('POST','/v1/health',body='{}',headers={'Content-Type':'application/json'})
        r=c.getresponse();r.read(4096)
        return r.status==401  # No credentials or record reads are needed for readiness.
    finally:c.close()


class TLSConnection(http.client.HTTPSConnection):
    def connect(self):
        raw=socket.create_connection(('127.0.0.1',443),self.timeout)
        try:self.sock=self._context.wrap_socket(raw,server_hostname=DOMAIN)
        except BaseException:raw.close();raise


def protected_https(path,expected):
    c=TLSConnection(DOMAIN,443,timeout=5,context=ssl.create_default_context())
    try:
        c.request('GET',path,headers={'Host':DOMAIN});r=c.getresponse();r.read(4096)
        if r.status!=expected:raise ValueError(f'HTTPS保护检查失败：{path}，HTTP {r.status}，预期{expected}。')
    finally:c.close()


def invariants(state,game_pid):
    if pid('chefjeff.service')!=game_pid:raise ValueError('游戏进程发生变化，请检查。')
    if str(Path('/opt/chefjeff/current').resolve())!=state['game_release']:raise ValueError('游戏目录发生变化。')
    if sha(Path(state['site_file']).read_bytes())!=state['site_sha256']:raise ValueError('Nginx配置发生变化。')
    if auth_stat(state['auth_path'])!=state['auth_stat']:raise ValueError('账号文件发生变化。')


def restore(state):
    for path,name,key in [(ADMIN_UNIT,'previous-admin.service','previous_admin_sha256'),(DATA_UNIT,'previous-data.service','previous_data_sha256')]:
        raw=(WORK/name).read_bytes()
        if sha(raw)!=state[key]:raise ValueError('原服务备份摘要变化，不能自动回退。')
        write(path,raw,0o644)
    run('systemctl','daemon-reload')
    run('systemctl','restart','chefjeff-data.service')
    run('systemctl','restart','chefjeff-admin.service')
    for attempt in range(40):
        try:
            if backend_health(None) and data_ready():return
        except (OSError,ValueError,http.client.HTTPException):pass
        if attempt==39:raise ValueError('已还原单元文件，但原管理/数据服务尚未就绪，请保留输出检查。')
        time.sleep(.2)


def activate():
    state=json.loads(STATE.read_text())
    if state['phase']=='active':
        if not backend_health():raise ValueError('管理服务未返回v2健康标识，请检查。')
        print('v2已启用，无需重复升级。');return
    if state['phase'] not in ('prepared','rolled-back'):raise ValueError('请先prepare。')
    for path,name,old,new in [(ADMIN_UNIT,'candidate-admin.service','previous_admin_sha256','candidate_admin_sha256'),
                              (DATA_UNIT,'candidate-data.service','previous_data_sha256','candidate_data_sha256')]:
        if sha(path.read_bytes())!=state[old] or sha((WORK/name).read_bytes())!=state[new]:
            raise ValueError('服务配置在准备后发生变化，不会覆盖。')
    before={name:pid(name) for name in ('chefjeff.service','chefjeff-data.service','chefjeff-admin.service')}
    invariants(state,before['chefjeff.service'])
    try:
        write(ADMIN_UNIT,(WORK/'candidate-admin.service').read_bytes(),0o644)
        write(DATA_UNIT,(WORK/'candidate-data.service').read_bytes(),0o644)
        run('systemctl','daemon-reload')
        run('systemctl','restart','chefjeff-data.service')
        run('systemctl','restart','chefjeff-admin.service')
        for attempt in range(40):
            try:
                if backend_health() and data_ready() and Path('/var/lib/chefjeff-data/record-sources.sqlite3').is_file():break
            except (OSError,ValueError,http.client.HTTPException):pass
            if attempt==39:raise ValueError('v2管理服务未就绪。')
            time.sleep(.2)
        if property_value('chefjeff-data.service','ActiveState')!='active':raise ValueError('共享数据服务未运行。')
        if not Path('/var/lib/chefjeff-data/record-sources.sqlite3').is_file():raise ValueError('来源索引未建立。')
        for path,status in [('/research-admin/login',200),('/research-admin/',303),('/research-admin/api/records',401),
                            ('/research-admin/api/options',401),('/research-admin/api/analysis',401),
                            ('/research-admin/api/preview?ref='+'0'*24,401)]:protected_https(path,status)
        invariants(state,before['chefjeff.service'])
        after={name:pid(name) for name in before}
        if any(after[name]=='0' or after[name]==before[name] for name in ('chefjeff-data.service','chefjeff-admin.service')):
            raise ValueError('管理或数据服务未切换到新进程。')
    except BaseException:
        restore(state)
        state['phase']='rolled-back';write(STATE,json.dumps(state,ensure_ascii=False,indent=2)+'\n')
        raise
    state['phase']='active';write(STATE,json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'admin-v2-active','url':'https://'+DOMAIN+'/research-admin/',
        'features':['selected_download','record_preview','custom_charts','dynamic_levels','regional_usage','new_authenticated_record_sources'],
        'account_preserved':True,'login_again_required':True,'game_process_unchanged':True,'game_current_unchanged':True,
        'nginx_unchanged':True,'data_and_admin_restarted':True,'historical_record_sources_backfilled':False,
        'existing_research_records_rewritten':False,'private_data_queried_during_install':False,
        'new_source_index_created':True,'previous_admin_release_preserved':True},ensure_ascii=False,indent=2))


def rollback():
    state=json.loads(STATE.read_text())
    if state['phase']!='active':raise ValueError('当前没有已启用的v2升级。')
    if sha(ADMIN_UNIT.read_bytes())!=state['candidate_admin_sha256'] or sha(DATA_UNIT.read_bytes())!=state['candidate_data_sha256']:
        raise ValueError('升级后服务配置又有变化，请先人工核对。')
    restore(state);state['phase']='rolled-back';write(STATE,json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    print('已恢复原管理台和共享服务入口；账号、游戏、研究记录和新来源索引均保留，没有回填或恢复数据库。')


def token_file():
    if socket.gethostname()!='VM-0-5-ubuntu':raise ValueError('仅限上海腾讯云服务器。')
    cfg=json.loads(CONFIG.read_text())
    if cfg.get('origin')!='https://'+DOMAIN:raise ValueError('管理台配置与预期不同。')
    from admin_server import token_path
    return token_path(cfg)


def day(stamp):return datetime.fromtimestamp(stamp,timezone.utc).isoformat(timespec='seconds')


def issue_token(days):
    from admin_server import export_token
    path=token_file();replaced=path.exists()
    token,record=export_token(days)
    # The service reads this file on every token request: no restart, and only root can change it.
    write(path,json.dumps(record)+'\n',0o640);shutil.chown(path,user='root',group='chefjeff')
    print(json.dumps({'status':'export-token-issued','id':record['id'],'issued_at':day(record['issued_at']),
        'expires_at':day(record['expires_at']),'previous_token_revoked':replaced,'service_restarted':False},ensure_ascii=False,indent=2))
    print('导出令牌只显示这一次。请复制到本机 pull_research.py save-token 的输入提示里，不要发进聊天或写进文件：')
    print(token)


def revoke_token():
    path=token_file();existed=path.exists()
    path.unlink(missing_ok=True)
    print(json.dumps({'status':'export-token-revoked','token_existed':existed,'effective':'immediately','service_restarted':False},ensure_ascii=False,indent=2))


def token_status():
    path=token_file()
    if not path.exists():
        return print(json.dumps({'status':'no-export-token'},indent=2))
    record=json.loads(path.read_text())
    print(json.dumps({'status':'export-token-present','id':record['id'],'issued_at':day(record['issued_at']),
        'expires_at':day(record['expires_at']),'expired':time.time()>=record['expires_at']},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','activate','rollback','prepare-release','activate-release','rollback-release',
                                           'prepare-admin','activate-admin','rollback-admin',
                                           'issue-export-token','revoke-export-token','export-token-status'))
    parser.add_argument('--game-release',type=Path)
    parser.add_argument('--days',type=int,default=90)
    args=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('请用sudo在上海服务器执行。')
    if args.command.endswith('-release'):
        import release_upgrade
        return release_upgrade.main(args.command, args.game_release, HERE)
    if args.command.endswith('-admin'):
        import admin_update
        return admin_update.main(args.command, HERE)
    WORK.mkdir(exist_ok=True,mode=0o700)
    with (WORK/'upgrade.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.command=='issue-export-token':return issue_token(args.days)
        {'prepare':prepare,'activate':activate,'rollback':rollback,
         'revoke-export-token':revoke_token,'export-token-status':token_status}[args.command]()


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:raise SystemExit('管理台v2升级已暂停：'+str(error))
