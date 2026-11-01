#!/usr/bin/env python3
"""Review an existing private gateway upgrade; retain its config, budgets and old unit."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deploy.free_gateway_config import gateway_unit
from deploy.free_install_common import atomic, digest, load, property_of, public_release, run, save, work_path
from deploy.install_free_region import validate_import
from free_model_client import FreeGatewayClient
from shared_client import SharedClient
from shared_server import read_private_json

UNIT=Path('/etc/systemd/system/chefjeff-free.service')
PREVIOUS=Path('/opt/chefjeff/releases/china-free-22fd0d25aaad/chefjeff-web-demo')
PREVIOUS_MANIFEST='dc5bc390d6472e5fc0aa987afdd9f69ba5995790bf20fc9ad5dec248eaacc87b'
UNIT_NAME='chefjeff-free.service'


def other_pids():
    return {unit:property_of(unit,'MainPID') for unit in ('chefjeff.service','chefjeff-data.service','chefjeff-admin.service')}


def client():
    # Existing backend identity only. No model key or player database is opened here.
    shared=SharedClient(read_private_json('/etc/chefjeff/shared-client.json'))
    return FreeGatewayClient(shared,gateway_url='http://127.0.0.1:8798')


def prepare(release,manifest_sha,work):
    if (work/'state.json').exists():
        state=load(work)
        if state['release']!=str(release) or state['manifest_sha']!=manifest_sha:raise ValueError('Different prepared upgrade')
        print(json.dumps({'status':'gateway-upgrade-already-'+state['phase'],'review_directory':str(work)}));return
    public_release(PREVIOUS,PREVIOUS_MANIFEST)
    if UNIT.is_symlink() or UNIT.read_text()!=gateway_unit(PREVIOUS):raise ValueError('Existing gateway unit differs from audited release')
    if property_of(UNIT_NAME,'DropInPaths'):raise ValueError('Gateway has unreviewed drop-ins')
    if property_of(UNIT_NAME,'ActiveState')!='active':raise ValueError('Existing gateway is not active')
    _,manifest=public_release(release,manifest_sha)
    validate_import(release,manifest['release']['fingerprint'])
    atomic(work/'gateway.before.service',UNIT.read_bytes(),0o644)
    atomic(work/'gateway.candidate.service',gateway_unit(release).encode(),0o644)
    save(work,{'phase':'prepared','release':str(release),'manifest_sha':manifest_sha,
        'previous_unit_sha':digest(UNIT),'candidate_unit_sha':digest(work/'gateway.candidate.service')})
    print(json.dumps({'status':'gateway-upgrade-prepared','review_directory':str(work),
        'old_code':str(PREVIOUS),'new_code':str(release),'services_restarted':False,
        'credentials_changed':False,'budget_opened':False,'player_databases_opened':False,
        'api_requests_sent':0,'activation_restarts':[UNIT_NAME]},indent=2))


def verify(work):
    state=load(work);public_release(state['release'],state['manifest_sha'])
    if (UNIT.is_symlink() or digest(UNIT)!=state['candidate_unit_sha']
            or property_of(UNIT_NAME,'ActiveState')!='active'
            or property_of(UNIT_NAME,'DropInPaths')
            or int(property_of(UNIT_NAME,'ExecMainStartTimestampMonotonic'))<=state['switched_monotonic_us']):
        raise ValueError('Unexpected gateway unit or process')
    status=client().request('status',{})
    catalog=status['catalog']
    if catalog.get('enabled') is not True or catalog.get('diagnostics_version')!=1:
        raise ValueError('Gateway diagnostics unavailable')
    if set(catalog.get('global_capacity',{}))!={'zhipu','startlux'} or any(
            row.get('limit')!=1 for row in catalog['global_capacity'].values()):raise ValueError('Unexpected capacity')
    print(json.dumps({'status':'gateway-diagnostics-upgrade-verified','release':state['release'],
        'process_started_after_switch':True,'diagnostics_version':1,'both_global_seat_limits':1,
        'credentials_changed':False,'budget_reset':False,'nginx_changed':False,
        'api_requests_sent':0,'player_databases_opened':False},indent=2))


def activate(work,allow_round_end):
    state=load(work)
    if state['phase']=='active':return verify(work)
    if not allow_round_end:raise ValueError('Explicitly allow ending free-model rounds')
    if state['phase'] not in ('prepared','rolled-back') or UNIT.is_symlink() or digest(UNIT)!=state['previous_unit_sha']:
        raise ValueError('Gateway changed after review')
    if (digest(work/'gateway.candidate.service')!=state['candidate_unit_sha']
            or digest(work/'gateway.before.service')!=state['previous_unit_sha']):raise ValueError('Reviewed unit changed')
    release,manifest=public_release(state['release'],state['manifest_sha'])
    validate_import(release,manifest['release']['fingerprint'])
    before=other_pids();state['switched_monotonic_us']=int(time.monotonic()*1000000)
    state['phase']='activating';save(work,state)
    try:
        atomic(UNIT,(work/'gateway.candidate.service').read_bytes(),0o644)
        run('systemctl','daemon-reload');run('systemctl','restart',UNIT_NAME)
        for attempt in range(30):
            try:
                if client().request('catalog',{}).get('diagnostics_version')==1:break
            except Exception:pass
            if attempt==29:raise ValueError('Gateway did not become ready')
            time.sleep(.2)
        verify(work)
        if other_pids()!=before:raise ValueError('Game/data/admin process changed')
        state['phase']='active';save(work,state)
    except Exception as error:
        atomic(UNIT,(work/'gateway.before.service').read_bytes(),0o644)
        try:
            run('systemctl','daemon-reload');run('systemctl','restart',UNIT_NAME)
            if property_of(UNIT_NAME,'ActiveState')!='active':raise ValueError()
            state['phase']='rolled-back'
        except Exception:state['phase']='rollback-failed'
        save(work,state)
        print(json.dumps({'status':'gateway-upgrade-stopped','phase':state['phase'],'error_type':type(error).__name__,
            'credentials_printed':False,'api_requests_sent':0}))
        raise ValueError('Gateway upgrade did not complete') from None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('prepare','activate','verify','rollback'))
    parser.add_argument('--release',type=Path,required=True);parser.add_argument('--manifest-sha',required=True)
    parser.add_argument('--allow-round-end',action='store_true');args=parser.parse_args()
    if os.geteuid()!=0:parser.error('Run the reviewed command with sudo')
    release,_=public_release(args.release,args.manifest_sha);work=work_path('gateway-upgrade',args.manifest_sha)
    if args.operation=='prepare':prepare(release,args.manifest_sha,work)
    elif args.operation=='activate':activate(work,args.allow_round_end)
    elif args.operation=='verify':verify(work)
    else:
        state=load(work)
        if not args.allow_round_end or state['phase']!='active' or digest(UNIT)!=state['candidate_unit_sha']:
            raise ValueError('Different active gateway or missing round-end permission')
        if digest(work/'gateway.before.service')!=state['previous_unit_sha']:raise ValueError('Backup changed')
        atomic(UNIT,(work/'gateway.before.service').read_bytes(),0o644)
        run('systemctl','daemon-reload');run('systemctl','restart',UNIT_NAME)
        if property_of(UNIT_NAME,'ActiveState')!='active':raise ValueError('Previous gateway not active')
        state['phase']='rolled-back';save(work,state)
        print(json.dumps({'status':'previous-gateway-restored','budget_reset':False,'api_requests_sent':0}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'gateway-upgrade-stopped','error_type':type(error).__name__,
            'credentials_printed':False,'player_databases_opened':False}));raise SystemExit(1) from None
