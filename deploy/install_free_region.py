#!/usr/bin/env python3
"""Review then activate one immutable game release, retaining the previous link/drop-in."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shlex
import ssl
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deploy.free_install_common import atomic, digest, load, property_of, public_release, run, save, work_path

DOMAINS={'cn':'chefjeff.belchingleo.online','de':'global.belchingleo.online'}
# The release both regions run now (25e4931, checked on both servers 2026-11-01).
BASE_SERVER_SHA='a250e37dca88e503e3bb0b9348bac8900779e297663c96f521dee8c64fef2270'
BASE_MANIFEST_SHA='4d840d7a09f393034d1248bb79d70a0b3b70bf0bc1847fa1459c45ed97d26eb6'
OVERRIDE=Path('/etc/systemd/system/chefjeff.service.d/zzzzzzzz-chefjeff-free.conf')
CURRENT=Path('/opt/chefjeff/current')


class InstallError(Exception):
    def __init__(self,code,**details):
        self.code,self.details=code,details
        super().__init__(code)


def expect_status(actual,expected):
    if actual!=expected:raise InstallError('unexpected_http_status',http_status=actual,expected_status=expected)


def validate_import(release,expected):
    code='''import json,sys
sys.path.insert(0,sys.argv[1])
try:
 import hosted_server
 from release_info import release_info
 print(json.dumps({'ok':True,'fingerprint':release_info()['fingerprint']}))
except BaseException as error:
 print(json.dumps({'ok':False,'error_type':type(error).__name__}))
'''
    result=subprocess.run(['runuser','-u','chefjeff','--','/usr/bin/python3','-I','-B','-c',code,str(release)],
        cwd='/tmp',capture_output=True,text=True)
    try:value=json.loads(result.stdout)
    except ValueError:raise InstallError('service_user_import_failed',exit_status=result.returncode) from None
    if result.returncode or value.get('ok') is not True or value.get('fingerprint')!=expected:
        error=value.get('error_type')
        raise InstallError('service_user_import_failed',exit_status=result.returncode,
            import_error=error if isinstance(error,str) and re.fullmatch('[A-Za-z]{1,64}',error) else 'unknown')


def existing_arguments(value, domain):
    match=re.search(r'argv\[\]=(.*?)\s*;\s*ignore_errors=',value)
    if not match:raise ValueError('Cannot isolate existing ExecStart')
    args=shlex.split(match[1])
    if args[:2]!=['/usr/bin/python3','/opt/chefjeff/current/hosted_server.py']:
        raise ValueError('Unexpected existing game entrypoint')
    allowed={'--port','--origin','--data-dir','--shared-config','--max-sessions','--max-waiting','--max-per-network','--web-root'}
    values={}
    options=args[2:]
    if '--free-model-gateway' in options:
        if options.count('--free-model-gateway')!=1:raise ValueError('Duplicate free gateway flag')
        options.remove('--free-model-gateway')
    for i in range(0,len(options),2):
        if i+1>=len(options) or options[i] not in allowed or options[i] in values:
            raise ValueError('Unknown or duplicate existing startup option')
        values[options[i]]=options[i+1]
        if not re.fullmatch(r'[A-Za-z0-9_./:+-]+',options[i+1]):raise ValueError('Unexpected startup value')
    if (values.get('--port')!='8780' or values.get('--origin')!='https://'+domain
            or values.get('--shared-config')!='/etc/chefjeff/shared-client.json'
            or values.get('--data-dir')!='/var/lib/chefjeff'):
        raise ValueError('Existing region configuration does not match the audit')
    if '--web-root' in values and values['--web-root']!='/opt/chefjeff/current/cocos-kitchen/build/web':
        raise ValueError('An explicit old web directory requires separate review')
    return args


def switch(target):
    temporary=CURRENT.with_name('current.free-pending')
    if temporary.exists() or temporary.is_symlink():raise ValueError('Unexpected pending release link')
    temporary.symlink_to(target);temporary.replace(CURRENT)


def request(domain,path,method='GET',body=None,session=None):
    connection=http.client.HTTPSConnection(domain,timeout=8,context=ssl.create_default_context())
    headers={'Origin':'https://'+domain}
    if body is not None:headers['Content-Type']='application/json'
    if session:headers['X-ChefJeff-Session']=session
    try:
        connection.request(method,path,None if body is None else json.dumps(body),headers)
        response=connection.getresponse();raw=response.read(262145)
        return response.status,raw
    finally:connection.close()


def wait_local(site):
    for _ in range(30):
        connection=http.client.HTTPConnection('127.0.0.1',8780,timeout=2)
        try:
            connection.request('GET','/healthz',headers={'Host':DOMAINS[site]})
            response=connection.getresponse();raw=response.read(4096)
            if response.status==200 and json.loads(raw).get('ok') is True:return
        except (OSError,ValueError):pass
        finally:connection.close()
        time.sleep(.2)
    raise ValueError('New local backend did not become ready')


def verify(site,work,mark=lambda stage:None):
    state=load(work);mark('verify_release')
    release,manifest=public_release(state['release'],state['manifest_sha'])
    if CURRENT.resolve()!=release or property_of('chefjeff.service','ActiveState')!='active':raise InstallError('wrong_active_game_release')
    started=int(property_of('chefjeff.service','ExecMainStartTimestampMonotonic'))
    if started<=state['switched_monotonic_us']:raise InstallError('game_process_predates_switch')
    if not Path(state['previous']).is_dir():raise InstallError('previous_release_missing')
    for unit,pid in state['other_pids'].items():
        if property_of(unit,'MainPID')!=pid:raise InstallError('data_or_admin_process_changed')
    domain=DOMAINS[site];session=None;primary_failure=False
    try:
        mark('public_healthz')
        status,_=request(domain,'/healthz')
        expect_status(status,200)
        mark('public_page')
        page,html=request(domain,'/')
        expect_status(page,200)
        if b'id="free-model-picker"' not in html or b'<script src="/free-model-picker.js"></script>' in html:
            raise InstallError('free_picker_delivery_failed')
        mark('public_session')
        created,raw=request(domain,'/api/session','POST',{})
        expect_status(created,201)
        session=json.loads(raw)['session']
        mark('public_fingerprint')
        version,raw=request(domain,'/api/state',session=session)
        expect_status(version,200)
        if version!=200 or json.loads(raw)['release']['fingerprint']!=manifest['release']['fingerprint']:
            raise InstallError('public_fingerprint_mismatch')
        mark('public_free_gateway')
        catalog,raw=request(domain,'/api/model/free/catalog',session=session)
        expect_status(catalog,200)
        value=json.loads(raw)
        if value.get('gateway_available') is not True:raise InstallError('shared_free_gateway_unavailable')
        if value.get('diagnostics_version')!=1:raise InstallError('shared_free_gateway_requires_upgrade')
    except BaseException:
        primary_failure=True;raise
    finally:
        if session:
            try:
                closed,_=request(domain,'/api/session/close','POST',{},session=session)
                expect_status(closed,200)
            except Exception:
                if not primary_failure:raise InstallError('test_session_close_failed') from None
    mark('http_redirect')
    redirect_connection=http.client.HTTPConnection(domain,timeout=8)
    try:
        redirect_connection.request('GET','/');response=redirect_connection.getresponse();response.read()
        redirect=response.status in (301,308) and response.getheader('Location')=='https://'+domain+'/'
        if not redirect:raise InstallError('https_redirect_failed',http_status=response.status)
    finally:redirect_connection.close()
    print(json.dumps({'status':'free-model-region-verified','site':site,'domain':domain,
        'previous_release':state['previous'],'current_release':str(release),'previous_release_preserved':True,
        'fingerprint':manifest['release']['fingerprint'],'process_started_after_switch':True,
        'healthz':200,'page':200,'session_post':201,'tls_verified':True,'http_redirect_verified':True,
        'test_session_closed':True,'free_picker_inline':True,'free_gateway_available':True,'data_admin_processes_unchanged':True,
        'model_calls':0,'round_started':False,'research_consent_sent':False,'player_database_opened':False},indent=2))


def prepare(site,release,manifest_sha,work):
    if (work/'state.json').exists():
        state=load(work)
        if state['release']!=str(release):raise ValueError('Different prepared release')
        print(json.dumps({'status':'region-already-'+state['phase'],'review_directory':str(work)}));return
    if not CURRENT.is_symlink() or OVERRIDE.is_symlink():raise ValueError('Unexpected current or override link')
    previous=CURRENT.resolve(strict=True)
    public_release(previous, BASE_MANIFEST_SHA)
    if digest(previous/'hosted_server.py')!=BASE_SERVER_SHA:raise ValueError('Current code differs from the audited free-model baseline')
    args=existing_arguments(property_of('chefjeff.service','ExecStart'),DOMAINS[site])
    unit='[Service]\nExecStart=\nExecStart='+' '.join(args if '--free-model-gateway' in args else [*args,'--free-model-gateway'])+'\n'
    previous_override=OVERRIDE.read_bytes() if OVERRIDE.exists() else None
    if previous_override is not None:
        if previous_override!=unit.encode():raise ValueError('Existing free override differs from audited startup')
        atomic(work/'override.before.conf',previous_override,0o644)
    atomic(work/'free-region.conf',unit.encode(),0o644)
    state={'phase':'prepared','site':site,'release':str(release),'manifest_sha':manifest_sha,'previous':str(previous),
        'unit_sha':digest(work/'free-region.conf'),'previous_server_sha':digest(previous/'hosted_server.py'),
        'startup_arguments':args,'previous_override_sha':digest(OVERRIDE) if OVERRIDE.exists() else None,
        'other_pids':{n:property_of(n,'MainPID') for n in ('chefjeff-data.service','chefjeff-admin.service')}}
    state['startup_snapshot']=hashlib.sha256(property_of('chefjeff.service','ExecStart').encode()).hexdigest()
    save(work,state)
    print(json.dumps({'status':'free-region-prepared','site':site,'new_release':str(release),'previous_release':str(previous),
        'review_directory':str(work),'services_restarted':False,'current_changed':False,'credentials_modified':False,
        'player_database_opened':False,'activation_restarts':['chefjeff.service']},indent=2))


def previous_override_matches(state):
    if OVERRIDE.is_symlink():return False
    expected=state.get('previous_override_sha')
    return digest(OVERRIDE)==expected if expected and OVERRIDE.is_file() else expected is None and not OVERRIDE.exists()


def restore_override(work,state):
    expected=state.get('previous_override_sha')
    if expected:
        if digest(work/'override.before.conf')!=expected:raise ValueError('Previous override backup changed')
        atomic(OVERRIDE,(work/'override.before.conf').read_bytes(),0o644)
    else:OVERRIDE.unlink(missing_ok=True)


def activate(site,work,allow_round_end):
    state=load(work)
    if state['phase']=='active':return verify(site,work)
    if not allow_round_end:raise InstallError('round_end_permission_required')
    if state['phase'] not in ('prepared','rolled-back') or CURRENT.resolve()!=Path(state['previous']) or not previous_override_matches(state):
        raise InstallError('installation_changed_after_review')
    if digest(work/'free-region.conf')!=state['unit_sha']:raise InstallError('reviewed_startup_changed')
    live=existing_arguments(property_of('chefjeff.service','ExecStart'),DOMAINS[site])
    if live!=state['startup_arguments']:raise InstallError('startup_arguments_changed_after_review')
    public_release(state['previous'],BASE_MANIFEST_SHA)
    release,manifest=public_release(state['release'],state['manifest_sha'])
    validate_import(release,manifest['release']['fingerprint'])
    state['switched_monotonic_us']=int(time.monotonic()*1000000)
    state['phase']='activating'
    def mark(stage):
        state['last_stage']=stage;save(work,state)
    mark('install_override')
    try:
        atomic(OVERRIDE,(work/'free-region.conf').read_bytes(),0o644)
        mark('switch_current');switch(state['release'])
        mark('restart_game');run('systemctl','daemon-reload');run('systemctl','restart','chefjeff.service')
        mark('local_readiness');wait_local(site)
        verify(site,work,mark)
        state['phase']='active';mark('complete')
    except BaseException as error:
        failure={'stage':state.get('last_stage'),'error_type':type(error).__name__}
        if isinstance(error,InstallError):failure.update(code=error.code,**error.details)
        try:
            failure['game_before_rollback']={name:property_of('chefjeff.service',name)
                for name in ('ActiveState','SubState','Result','ExecMainStatus')}
        except Exception:failure['game_status_unavailable']=True
        state['last_failure']=failure
        try:
            switch(state['previous']);restore_override(work,state)
            run('systemctl','daemon-reload');run('systemctl','restart','chefjeff.service')
            wait_local(site)
            state['phase']='rolled-back'
        except Exception as rollback_error:
            state['phase']='rollback-failed';failure['rollback_error_type']=type(rollback_error).__name__
        save(work,state)
        print(json.dumps({'status':'free-region-activation-failed','phase':state['phase'],
            'failure':failure,'current_release':str(CURRENT.resolve()),'model_calls':0,
            'credentials_printed':False,'player_database_opened':False},indent=2))
        raise InstallError('activation_failed',stage=failure['stage'],rollback_state=state['phase']) from None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('prepare','activate','verify','rollback'))
    parser.add_argument('--site',choices=tuple(DOMAINS),required=True)
    parser.add_argument('--release',type=Path,required=True)
    parser.add_argument('--manifest-sha',required=True)
    parser.add_argument('--allow-round-end',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error('Run the reviewed command with sudo')
    release,_=public_release(args.release,args.manifest_sha)
    work=work_path('region',args.manifest_sha)
    if args.operation=='prepare':prepare(args.site,release,args.manifest_sha,work)
    elif args.operation=='activate':activate(args.site,work,args.allow_round_end)
    elif args.operation=='verify':verify(args.site,work)
    else:
        if not args.allow_round_end:parser.error('Explicitly allow ending current rounds')
        state=load(work)
        if state['phase']!='active' or CURRENT.resolve()!=release:raise ValueError('Different active release')
        if digest(OVERRIDE)!=state['unit_sha']:raise ValueError('Startup override changed')
        switch(state['previous']);restore_override(work,state);run('systemctl','daemon-reload');run('systemctl','restart','chefjeff.service')
        state['phase']='rolled-back';save(work,state)
        print(json.dumps({'status':'previous-game-restored','current_release':state['previous'],'data_admin_restarted':False}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        report={'status':'free-region-operation-stopped','error_type':type(error).__name__,'credentials_printed':False}
        if isinstance(error,InstallError):report.update(code=error.code,**error.details)
        print(json.dumps(report,indent=2));raise SystemExit(1) from None
