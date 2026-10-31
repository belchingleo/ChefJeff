"""Local TLS/Nginx/browser integration using only synthetic SQLite fixtures."""
import hashlib
import json
from pathlib import Path
import subprocess
import socket
import ssl
import os
import signal
import tempfile
import time
from unittest.mock import patch

import sys
import shutil
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'ops' / 'research_admin'))
from test_admin_console import AdminTests
from install_admin import LOCATION
import install_admin as installer
from scripts.research_export import verify_package
from admin_server import AdminHandler

ROOT=Path(os.environ.get('CHEFJEFF_ADMIN_ARTIFACTS_DIR', REPO / 'dist' / 'admin-browser-check'))
ROOT.mkdir(parents=True, exist_ok=True)
case=AdminTests();case.setUp()
from hosted_usage import UsageStats
from shared_data import SharedUsage, usage_payload
from hosted_records import RETENTION_SECONDS
from source_observer import SourceObserver
import source_observer
usage=SharedUsage(case.db.parent)
for site,views in [('cn',10),('global',20)]:
    stats=UsageStats()
    for _ in range(views):stats.increment('page_views')
    usage.apply(site,('a' if site=='cn' else 'b')*32,usage_payload(stats.snapshot()))
import sqlite3
with sqlite3.connect(usage.path) as db:db.execute('UPDATE totals SET page_views=page_views+12 WHERE id=1')
with patch.object(source_observer.time,'time',return_value=time.time()-300):
    observer=SourceObserver(case.db.parent,RETENTION_SECONDS)
observer.save_receipt('cn',case.full)
try:
    with tempfile.TemporaryDirectory() as temporary:
        folder=Path(temporary)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            port=listener.getsockname()[1]
        origin=f'https://127.0.0.1:{port}'
        case.server.config['origin']=origin
        original_same_origin=AdminHandler.same_origin
        def checked_origin(self):
            result=original_same_origin(self)
            if not result:
                print('Synthetic origin diagnostic:',{key:self.headers.get(key) for key in ('Origin','Host','Sec-Fetch-Site')},flush=True)
            return result
        AdminHandler.same_origin=checked_origin
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(folder/'key.pem'),
                        '-out',str(folder/'cert.pem'),'-days','1','-subj','/CN=localhost',
                        '-addext','subjectAltName=IP:127.0.0.1'],check=True,capture_output=True)
        # The fake loopback usage service expects the real regional Host. Test-only adapter.
        from test_admin_console import UsageHandler
        def usage_get(self):
            raw=json.dumps({'usage':{'shared':True,'scope':'global','synchronized':True,'page_views':42,
                'started_rounds':3,'completed_rounds':2,'estimated_player_browsers':2,
                'estimated_visitor_browsers':8,'running_sessions':0,'tracking_since':'2026-10-21T00:00:00Z',
                'levels':[{'level':1,'started_rounds':3,'completed_rounds':2}],
                'round_outcomes':{'completed':2,'manual_end':1},'durations':[]}}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        UsageHandler.do_GET=usage_get
        location=LOCATION.replace('127.0.0.1:8795',f'127.0.0.1:{case.server.server_port}').replace(
            'proxy_set_header Host chefjeff.belchingleo.online;',f'proxy_set_header Host 127.0.0.1:{port};')
        conf=f'''pid {folder}/nginx.pid;
error_log {folder}/error.log;
events {{ worker_connections 64; }}
http {{ access_log off;
client_body_temp_path {folder}/body;
proxy_temp_path {folder}/proxy;
fastcgi_temp_path {folder}/fastcgi;
uwsgi_temp_path {folder}/uwsgi;
scgi_temp_path {folder}/scgi;
server {{ listen 127.0.0.1:{port} ssl; server_name localhost;
ssl_certificate {folder}/cert.pem;
ssl_certificate_key {folder}/key.pem;
{location}
location / {{ return 200 "synthetic game"; }}
}} }}'''
        (folder/'nginx.conf').write_text(conf.replace(location,''))
        binary=os.environ.get('CHEFJEFF_NGINX_BIN') or shutil.which('nginx')
        if not binary: raise RuntimeError('Install Nginx or set CHEFJEFF_NGINX_BIN for the local proxy check.')
        validation=subprocess.run([binary,'-t','-p',str(folder),'-c',str(folder/'nginx.conf')],capture_output=True,text=True)
        if validation.returncode:
            raise RuntimeError(validation.stderr)
        server=subprocess.Popen([binary,'-p',str(folder),'-c',str(folder/'nginx.conf'),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            time.sleep(.3)
            context=ssl.create_default_context(cafile=str(folder/'cert.pem'))
            real_probe=installer.https_probe
            observed=[]
            def probe_with_reload(path):
                status=real_probe(path)
                observed.append(status)
                if len(observed)==1:
                    assert status==200  # Old game-only worker has not loaded the admin route.
                    (folder/'nginx.conf').write_text(conf)
                    os.kill(int((folder/'nginx.pid').read_text()),signal.SIGHUP)
                return status
            with patch.object(installer,'DOMAIN','127.0.0.1'), patch.object(installer,'HTTPS_PORT',port), \
                    patch.object(installer.ssl,'create_default_context',return_value=context):
                with patch.object(installer,'https_probe',side_effect=probe_with_reload):
                    installer.https_check('/research-admin/',303)
                assert len(observed)>=2 and observed[-1]==303
                installer.https_check('/research-admin/login',200)
                installer.https_check('/research-admin/api/records',401)
            subprocess.run(['node',str(REPO/'tests'/'admin_console_browser_test.cjs'),origin+'/research-admin/',str(ROOT)],check=True,timeout=90)
            for filename,count in [('browser-single.zip',1),('browser-selected.zip',1),('browser-multi.zip',2),('browser-preview.zip',1)]:
                manifest=verify_package(ROOT/filename,database=case.db)
                assert manifest['rounds']==count
            import xml.etree.ElementTree as ET
            ET.parse(ROOT/'browser-chart.svg')
            assert 'data:font/woff2;base64,' in (ROOT/'browser-chart.svg').read_text()
            assert hashlib.sha256(case.db.read_bytes()).hexdigest()==case.before
            print('Real Nginx asynchronous reload readiness + verified TLS + Chromium desktop/mobile/login/filter/download/logout passed; synthetic DB unchanged.')
        finally:
            server.terminate();server.wait(timeout=10)
finally:
    case.tearDown()
