#!/usr/bin/env python3
"""Prepare/review then activate the independent gateway. Never restarts game/data/admin services."""
import argparse
import difflib
import grp
import http.client
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deploy.free_gateway_config import data_candidate, gateway_unit, nginx_location
from deploy.free_install_common import atomic, digest, load, property_of, public_release, run, save, work_path
from hosted_free_models import read_trial_keys
from free_model_client import FreeGatewayClient
from shared_client import SharedClient
from shared_server import read_private_json

DATA = Path('/etc/nginx/sites-available/chefjeff-data')
CONFIG = Path('/etc/chefjeff-free')
UNIT = Path('/etc/systemd/system/chefjeff-free.service')


def pids():
    return {name: property_of(name, 'MainPID') for name in ('chefjeff.service','chefjeff-data.service','chefjeff-admin.service')}


def ensure_account():
    try:
        account = pwd.getpwnam('chefjeff-free')
    except KeyError:
        run('useradd','--system','--user-group','--no-create-home','--home-dir','/nonexistent','--shell','/usr/sbin/nologin','chefjeff-free')
        account = pwd.getpwnam('chefjeff-free')
    if account.pw_uid >= 1000 or not account.pw_shell.endswith(('nologin','false')):
        raise ValueError('Unexpected existing service account')
    return account


def candidate_check(work):
    directory = work/'sites-enabled'
    directory.mkdir(mode=0o700, exist_ok=True)
    for file in Path('/etc/nginx/sites-enabled').iterdir():
        target = directory/file.name
        if target.exists() or target.is_symlink():target.unlink()
        target.symlink_to(work/'data.candidate.nginx' if file.resolve() == DATA.resolve() else file.resolve())
    nginx = Path('/etc/nginx/nginx.conf').read_text()
    anchor = 'include /etc/nginx/sites-enabled/*;'
    if nginx.count(anchor) != 1:
        raise ValueError('Unexpected Nginx include layout')
    candidate = nginx.replace(anchor, 'include '+str(directory)+'/*;', 1)
    atomic(work/'validation.conf', candidate.encode())
    run('nginx','-t','-c',str(work/'validation.conf'))


def prepare(release, work, args):
    if (work/'state.json').exists():
        state = load(work)
        if state['release'] != str(release):raise ValueError('Different staged source')
        print(json.dumps({'status':'gateway-already-'+state['phase'],'review_directory':str(work)}));return
    if UNIT.exists() or (CONFIG.exists() and any(CONFIG.iterdir())):
        raise ValueError('Existing gateway configuration requires separate review')
    if args.keys_file is None or args.keys_file.name != 'api-keys.json':
        raise ValueError('Provide the private test api-keys.json explicitly')
    # The reviewed root installer imports the operator-owned 0600 test file.
    # The unprivileged gateway still accepts only root/its own credential files.
    read_trial_keys(args.keys_file, allow_root_import=True)
    sites = read_private_json('/etc/chefjeff/data-server.json')
    if set(sites) != {'sites'} or set(sites['sites']) != {'cn','global'}:
        raise ValueError('Unexpected existing site credential map')
    old_nginx = DATA.read_bytes()
    candidate = data_candidate(old_nginx.decode())
    account = ensure_account()
    CONFIG.mkdir(mode=0o750, exist_ok=True)
    if CONFIG.is_symlink():raise ValueError('Unexpected private configuration directory')
    os.chown(CONFIG, 0, account.pw_gid);CONFIG.chmod(0o750)
    private = Path('/var/lib/chefjeff-free')
    if private.is_symlink():raise ValueError('Unexpected budget directory')
    private.mkdir(mode=0o700, exist_ok=True)
    os.chown(private, account.pw_uid, account.pw_gid);private.chmod(0o700)
    for name, raw in (('model-keys.json',args.keys_file.read_bytes()),
                      ('sites.json',(json.dumps(sites,separators=(',',':'))+'\n').encode())):
        atomic(CONFIG/name,raw,0o640);os.chown(CONFIG/name,0,account.pw_gid)
    atomic(CONFIG/'nginx-location.conf',nginx_location().encode(),0o644)
    atomic(work/'data.before.nginx',old_nginx)
    atomic(work/'data.candidate.nginx',candidate.encode())
    atomic(work/'chefjeff-free.service',gateway_unit(release).encode())
    atomic(work/'review.diff',''.join(difflib.unified_diff(old_nginx.decode().splitlines(True),candidate.splitlines(True),
        fromfile='existing data domain',tofile='candidate data domain')).encode())
    candidate_check(work)
    state = {'phase':'prepared','release':str(release),'manifest_sha':args.manifest_sha,
        'data_nginx_sha':digest(DATA),'pids':pids(),
        'unit_sha':digest(work/'chefjeff-free.service'),'candidate_sha':digest(work/'data.candidate.nginx')}
    save(work,state)
    print(json.dumps({'status':'gateway-prepared','review_directory':str(work),'candidate_nginx_valid':True,
        'new_private_service_account':'chefjeff-free','new_private_config_copied':True,
        'game_data_admin_restarted':False,'live_nginx_changed':False,'player_databases_opened':False,
        'api_requests_sent':0,'credentials_printed':False},ensure_ascii=False,indent=2))


def verify(work):
    state = load(work)
    if property_of('chefjeff-free.service','ActiveState') != 'active':raise ValueError('Gateway not active')
    shared = SharedClient(read_private_json('/etc/chefjeff/shared-client.json'))
    client = FreeGatewayClient(shared, gateway_url='http://127.0.0.1:8798')
    catalog = client.request('catalog',{})
    if catalog.get('enabled') is not True or set(catalog.get('global_capacity',{})) != {'zhipu','startlux'}:
        raise ValueError('Gateway catalog verification failed')  # a first install enables the original two only
    if any(catalog['global_capacity'][provider].get('limit') != 1 for provider in ('zhipu','startlux')):
        raise ValueError('Unexpected global model capacity')
    if pids() != state['pids']:raise ValueError('An existing game/data/admin process changed')
    print(json.dumps({'status':'gateway-active-private-only','both_global_seat_limits':1,
        'game_data_admin_processes_unchanged':True,'player_databases_opened':False,'api_requests_sent':0,
        'next':'bounded authenticated synthetic smoke test before enabling game clients'},indent=2))


def activate(work):
    state = load(work)
    if state['phase']=='active':return verify(work)
    if state['phase']!='prepared' or digest(DATA)!=state['data_nginx_sha']:
        raise ValueError('Live Nginx changed after preparation')
    if digest(work/'chefjeff-free.service')!=state['unit_sha'] or digest(work/'data.candidate.nginx')!=state['candidate_sha']:
        raise ValueError('Reviewed files changed')
    candidate_check(work)
    try:
        atomic(UNIT,(work/'chefjeff-free.service').read_bytes(),0o644)
        run('systemctl','daemon-reload');run('systemctl','enable','--now','chefjeff-free.service')
        # Readiness is private control traffic only, not a model invocation.
        import time
        shared = SharedClient(read_private_json('/etc/chefjeff/shared-client.json'))
        client = FreeGatewayClient(shared,gateway_url='http://127.0.0.1:8798')
        ready = False
        for _ in range(20):
            try:
                ready = client.request('catalog',{}).get('enabled') is True
                if ready:break
            except Exception:pass
            time.sleep(.2)
        if not ready:raise ValueError('Gateway did not become ready')
        atomic(DATA,(work/'data.candidate.nginx').read_bytes(),0o644)
        run('nginx','-t');run('systemctl','reload','nginx')
        state['phase']='active';save(work,state)
        verify(work)
    except Exception:
        atomic(DATA,(work/'data.before.nginx').read_bytes(),0o644)
        run('nginx','-t');run('systemctl','reload','nginx')
        subprocess.run(['systemctl','disable','--now','chefjeff-free.service'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        state['phase']='rolled-back';save(work,state)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('prepare','activate','verify'))
    parser.add_argument('--release',type=Path,required=True)
    parser.add_argument('--manifest-sha',required=True)
    parser.add_argument('--keys-file',type=Path)
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error('Run the reviewed command with sudo')
    release,_=public_release(args.release,args.manifest_sha)
    work=work_path('gateway',args.manifest_sha)
    if args.operation=='prepare':prepare(release,work,args)
    elif args.operation=='activate':activate(work)
    else:verify(work)


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('Gateway installation paused; inspect the private review directory. No credentials or player contents printed.') from None
