"""Synthetic fixtures only; no production database, account or model access."""
from copy import deepcopy
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import zipfile

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ops' / 'research_admin'))

import admin_server as app
import install_admin as installer

RELEASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RELEASE))
from scripts.research_export import export_package, verify_package
from hosted_records import ContributionStore

ORIGIN = 'https://chefjeff.belchingleo.online'
HOST = 'chefjeff.belchingleo.online'
PASSWORD = 'synthetic-test-password-only'


class UsageHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        assert self.path == '/ops/usage'
        assert self.headers['Host'] == HOST
        raw = json.dumps({'usage': {'shared': True, 'scope': 'global', 'synchronized': True,
                                   'page_views': 42, 'started_rounds': 3}}).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.auth = self.root/'auth.json'
        self.auth.write_text(json.dumps(app.credentials('admin', PASSWORD)))
        store = ContributionStore(self.root/'data')
        self.db = store.path
        self.sample = json.loads((RELEASE/'tests/fixtures/research-v2-short.json').read_text())
        self.sample['conditions']['model_identity'] = None
        self.full = store.save(self.sample)
        incomplete = deepcopy(self.sample)
        incomplete['quality']['complete'] = False
        incomplete['ended_at'] = None
        store.save(incomplete)
        expired = store.save(self.sample)
        withdrawn = store.save(self.sample)
        store.delete(withdrawn['id'], withdrawn['deletion_token'])
        with sqlite3.connect(self.db) as c:
            c.execute('UPDATE records SET expires=? WHERE id=?', (time.time()-1, expired['id']))
        self.before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.usage = ThreadingHTTPServer(('127.0.0.1', 0), UsageHandler)
        self.usage_thread = threading.Thread(target=self.usage.serve_forever, daemon=True)
        self.usage_thread.start()
        config = dict(auth=str(self.auth), origin=ORIGIN, database=str(self.db), temporary=str(self.root),
                      game_port=self.usage.server_port)
        self.server = app.AdminServer(('127.0.0.1', 0), config, export_package, verify_package)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.usage.shutdown(); self.usage.server_close(); self.usage_thread.join()
        self.temp.cleanup()

    def request(self, path, method='GET', body=None, cookie=None, origin=None, host=HOST, content_type=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Host': host}
        if cookie: headers['Cookie'] = cookie
        if origin: headers['Origin'] = origin
        if content_type: headers['Content-Type'] = content_type
        if body is not None: body = body.encode()
        c.request(method, path, body=body, headers=headers)
        response = c.getresponse()
        status, headers, raw = response.status, dict(response.getheaders()), response.read()
        c.close()
        return status, headers, raw

    def login(self):
        status, headers, raw = self.request(app.PREFIX+'login', 'POST', urlencode(dict(username='admin', password=PASSWORD)),
                                          origin=ORIGIN, content_type='application/x-www-form-urlencoded')
        self.assertEqual(status, 303)
        self.assertIn('Secure', headers['Set-Cookie']); self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        return headers['Set-Cookie'].split(';')[0]

    def test_unauthenticated_never_opens_data(self):
        with patch.object(app, 'record_index', side_effect=AssertionError('unauthenticated read')):
            for path in ('api/records','api/usage','download/usage.json','download/research.cjresearch.zip'):
                self.assertEqual(self.request(app.PREFIX+path)[0],401)
        self.assertEqual(self.request(app.PREFIX)[0],303)
        self.assertEqual(self.request(app.PREFIX+'login')[0],200)

    def test_index_projection_and_original_database_unchanged(self):
        cookie = self.login()
        status, headers, raw = self.request(app.PREFIX+'api/records',cookie=cookie)
        self.assertEqual(status,200)
        data=json.loads(raw)
        self.assertEqual(data['total'],2)
        self.assertEqual(sorted(r['quality.complete'] for r in data['records']),[0,1])
        self.assertNotIn(b'events',raw); self.assertNotIn(b'deletion',raw)
        self.assertIn('no-store',headers['Cache-Control'])
        self.assertEqual(headers['Referrer-Policy'],'same-origin')
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),self.before)

    def test_model_metadata_names(self):
        with sqlite3.connect(self.db) as c:
            data=deepcopy(self.sample)
            data['conditions']['model_identity']={'provider':'custom','model_id':'synthetic-model'}
            c.execute('UPDATE records SET record=? WHERE id=?',(json.dumps(data),self.full['id']))
        indexed=app.record_index(self.db,{},1)
        self.assertTrue(any(r['conditions.model_identity.model_id']=='synthetic-model' for r in indexed['records']))

    def test_same_origin_and_host_enforced(self):
        body=urlencode(dict(username='admin',password=PASSWORD))
        for origin in ('https://attacker.invalid',None):
            self.assertEqual(self.request(app.PREFIX+'login','POST',body,origin=origin,content_type='application/x-www-form-urlencoded')[0],403)
        self.assertEqual(self.request(app.PREFIX+'login',host='attacker.invalid')[0],403)
        cookie=self.login()
        self.assertEqual(self.request(app.PREFIX+'logout','POST','logout=1',cookie=cookie,origin='https://attacker.invalid',content_type='application/x-www-form-urlencoded')[0],403)
        self.assertEqual(self.request(app.PREFIX+'api/records',cookie=cookie)[0],200)

    def test_login_rotation_expiry_and_logout(self):
        old=self.login(); current=self.login()
        self.assertEqual(self.request(app.PREFIX+'api/records',cookie=old)[0],401)
        self.assertEqual(self.request(app.PREFIX+'logout','POST','logout=1',cookie=current,origin=ORIGIN,content_type='application/x-www-form-urlencoded')[0],303)
        self.assertEqual(self.request(app.PREFIX+'api/records',cookie=current)[0],401)
        token=self.login()
        for session in self.server.sessions.values(): session['seen']-=app.IDLE_SECONDS+1
        self.assertEqual(self.request(app.PREFIX+'api/records',cookie=token)[0],401)

    def test_login_throttling(self):
        for i in range(10):
            status,*_=self.request(app.PREFIX+'login','POST',urlencode(dict(username='admin',password='wrong')),
                                  origin=ORIGIN,content_type='application/x-www-form-urlencoded')
            self.assertEqual(status,403)
        self.assertEqual(self.request(app.PREFIX+'login','POST',urlencode(dict(username='admin',password=PASSWORD)),
                                     origin=ORIGIN,content_type='application/x-www-form-urlencoded')[0],429)

    def test_exports_filter_expiry_and_withdrawal_and_cleanup(self):
        cookie=self.login()
        status,headers,raw=self.request(app.PREFIX+'download/research.cjresearch.zip?since=2026-10-23&until=2026-10-23&level=1',cookie=cookie)
        self.assertEqual(status,200)
        self.assertIn('attachment',headers['Content-Disposition'])
        self.assertIn('X-Research-Expires',headers)
        target=self.root/'download.zip';target.write_bytes(raw)
        manifest=verify_package(target,database=self.db)
        self.assertEqual(manifest['rounds'],2)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),self.before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),['auth.json','data','download.zip'])

    def test_export_recheck_failure_releases_lock_and_sends_no_zip(self):
        cookie=self.login()
        with patch.object(self.server,'verifier',side_effect=ValueError('withdrawn')):
            status,headers,raw=self.request(app.PREFIX+'download/research.cjresearch.zip',cookie=cookie)
            self.assertEqual(status,503);self.assertNotIn('Content-Disposition',headers)
        self.assertEqual(self.request(app.PREFIX+'download/research.cjresearch.zip',cookie=cookie)[0],200)

    def test_usage_read_and_download(self):
        cookie=self.login()
        for path in ('api/usage','download/usage.json'):
            status,headers,raw=self.request(app.PREFIX+path,cookie=cookie)
            self.assertEqual(status,200);self.assertEqual(json.loads(raw)['usage']['page_views'],42)
            self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),self.before)

    def test_filters_validation_and_empty_results(self):
        cookie=self.login()
        for query in ('level=1&level=2','since=not-a-date','since=2026-10-24&until=2026-10-23','database=/tmp/other','page=-1','level=1%20OR%201=1'):
            self.assertEqual(self.request(app.PREFIX+'api/records?'+query,cookie=cookie)[0],400)
        self.assertEqual(json.loads(self.request(app.PREFIX+'api/records?level=2',cookie=cookie)[2])['total'],0)
        self.assertEqual(self.request(app.PREFIX+'download/research.cjresearch.zip?level=2',cookie=cookie)[0],422)

    def test_database_missing_is_error_not_empty(self):
        self.server.config['database']=str(self.root/'missing.sqlite3')
        self.assertEqual(self.request(app.PREFIX+'api/records',cookie=self.login())[0],503)
        self.assertFalse((self.root/'missing.sqlite3').exists())

    def test_query_only_connection_rejects_writes(self):
        c=app.read_connection(self.db)
        try:
            with self.assertRaises(sqlite3.OperationalError): c.execute('DELETE FROM records')
        finally: c.close()


class InstallerTests(unittest.TestCase):
    def test_patch_exact_tls_site_only(self):
        original='''# server { ignored }
server { listen 80; server_name chefjeff.belchingleo.online; return 301 https://chefjeff.belchingleo.online; }
server { listen 443 ssl; server_name www.belchingleo.online; location / { return 200 "cv }"; } }
server { listen [::]:443 ssl; listen 443 ssl; server_name chefjeff.belchingleo.online; location / { return 200 "game {"; } }
server { listen 443 ssl; server_name chefjeff.online; return 444; }
'''
        result=installer.patch_site(original,'/etc/chefjeff-admin/nginx-location.conf')
        self.assertEqual(result.replace('\n    include /etc/chefjeff-admin/nginx-location.conf;',''),original)
        self.assertIn('server {\n    include /etc/chefjeff-admin/nginx-location.conf; listen [::]:443',result)
        with self.assertRaises(ValueError): installer.patch_site(result,'/anything')
        with self.assertRaises(ValueError): installer.patch_site(original+original,'/anything')

    def test_password_and_dates(self):
        with self.assertRaises(ValueError): app.credentials('admin','short')
        with self.assertRaises(ValueError): app.credentials('../root',PASSWORD)
        selected,page=app.filters({'since':['2026-10-23'],'until':['2026-10-23']})
        self.assertEqual(selected,{'since':'2026-10-23T00:00:00+00:00','until':'2026-10-24T00:00:00+00:00'})
        self.assertEqual(page,1)

    def test_https_readiness_retries_old_worker_response(self):
        with patch.object(installer,'https_probe',side_effect=[404,502,303]) as probe, patch.object(installer.time,'sleep'):
            installer.https_check('/research-admin/',303)
        self.assertEqual(probe.call_count,3)

    def test_https_readiness_never_accepts_unprotected_data(self):
        with patch.object(installer,'https_probe',return_value=200) as probe, patch.object(installer.time,'sleep'):
            with self.assertRaisesRegex(ValueError,r'/research-admin/api/records.*401.*HTTP 200'):
                installer.https_check('/research-admin/api/records',401)
        self.assertEqual(probe.call_count,12)


class InstallationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.real_path=Path
        def mapped(value='.'):
            value=str(value)
            if value.startswith(('/etc/','/opt/','/root/','/var/')):
                return self.root/value.lstrip('/')
            return self.real_path(value)
        self.mapped=mapped
        self.bundle=self.root/'bundle';self.bundle.mkdir()
        for name in (*installer.APP_FILES,'install_admin.py'):
            (self.bundle/name).write_bytes((ROOT/'ops'/'research_admin'/name).read_bytes())
        manifest={'bundle_id':'synthetic-build','files':{name:hashlib.sha256((self.bundle/name).read_bytes()).hexdigest() for name in (*installer.APP_FILES,'install_admin.py')}}
        (self.bundle/'manifest.json').write_text(json.dumps(manifest))
        self.release=mapped('/opt/chefjeff/releases/china-en-v4-269d7af296be/chefjeff-web-demo')
        (self.release/'scripts').mkdir(parents=True)
        (self.release/'scripts/research_export.py').write_bytes((RELEASE/'scripts/research_export.py').read_bytes())
        mapped('/opt/chefjeff/current').symlink_to(self.release,target_is_directory=True)
        self.site=mapped('/etc/nginx/sites-available/game');self.site.parent.mkdir(parents=True)
        self.original='server { listen 443 ssl; server_name chefjeff.belchingleo.online; location / { return 200 "game"; } }\n'
        self.site.write_text(self.original)
        enabled=mapped('/etc/nginx/sites-enabled');enabled.mkdir();(enabled/'game').symlink_to(self.site)
        mapped('/etc/nginx/nginx.conf').write_text('events {} http { include /etc/nginx/sites-enabled/*; }')
        self.review=mapped('/root/chefjeff-admin-review');self.review.mkdir(parents=True)
        self.config=mapped('/etc/chefjeff-admin');self.config.mkdir()
        (self.config/'auth.json').write_text(json.dumps(app.credentials('admin',PASSWORD)))
        self.unit=mapped('/etc/systemd/system/chefjeff-admin.service');self.unit.parent.mkdir(parents=True)
        self.patchers=[patch.object(installer,'Path',mapped),patch.object(installer,'HERE',self.bundle),
            patch.object(installer,'REVIEW',self.review),patch.object(installer,'CONFIG',self.config),
            patch.object(installer,'STATE',self.review/'state.json'),patch.object(installer,'UNIT',self.unit),
            patch.object(installer.socket,'gethostname',return_value='VM-0-5-ubuntu'),
            patch.object(installer.shutil,'chown'),patch.object(installer,'run'),
            patch.object(installer,'service_pid',return_value='123'),patch.object(installer,'local_check'),
            patch.object(installer,'https_check'),patch.object(installer.subprocess,'run')]
        self.mocks=[p.start() for p in self.patchers]
        self.commands=self.mocks[8]

    def tearDown(self):
        for p in reversed(self.patchers):p.stop()
        self.temp.cleanup()

    def test_prepare_activate_idempotence_and_rollback_no_game_restart(self):
        installer.prepare()
        self.assertEqual(self.site.read_text(),self.original)
        self.assertFalse(self.unit.exists())
        installer.activate()
        self.assertTrue(self.unit.exists())
        self.assertEqual(json.loads((self.review/'state.json').read_text())['phase'],'active')
        self.assertEqual(installer.Path('/opt/chefjeff/current').resolve(),self.release)
        installer.activate()
        installer.rollback()
        self.assertEqual(self.site.read_text(),self.original)
        self.assertFalse(self.unit.exists())
        for call in self.commands.call_args_list:
            args=call.args
            if args[0]=='systemctl' and any(v in args for v in ('start','stop','restart','disable','enable')):
                self.assertNotIn('chefjeff.service',args)
                self.assertNotIn('chefjeff-data.service',args)
        self.assertFalse(installer.Path('/var/lib/chefjeff-data/contributions.sqlite3').exists())

    def test_activation_failure_restores_only_candidate_site(self):
        installer.prepare()
        with patch.object(installer,'https_check',side_effect=ValueError('synthetic failed probe')):
            with self.assertRaises(ValueError):installer.activate()
        self.assertEqual(self.site.read_text(),self.original)
        self.assertFalse(self.unit.exists())
        self.assertEqual(installer.Path('/opt/chefjeff/current').resolve(),self.release)

    def test_refuse_overwriting_changed_nginx(self):
        installer.prepare()
        self.site.write_text(self.original+'# newer owner edit\n')
        with self.assertRaises(ValueError):installer.activate()
        self.assertIn('newer owner edit',self.site.read_text())
        self.assertFalse(self.unit.exists())


if __name__=='__main__': unittest.main(verbosity=2)
