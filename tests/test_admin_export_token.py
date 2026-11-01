"""Read-only export token: synthetic database, isolated services and files; no live server or real token."""
import contextlib
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ops'/'research_admin'))
sys.path.insert(0, str(ROOT))

import admin_server as app
import admin_update as update
import upgrade_admin as operator
from hosted_records import ContributionStore
from scripts import pull_research as pull
from scripts.research_export import export_package, verify_package

ORIGIN = 'https://chefjeff.belchingleo.online'
HOST = 'chefjeff.belchingleo.online'
PASSWORD = secrets.token_urlsafe(24)  # Generated per run; no password-like literal in the repository.
FORM = 'application/x-www-form-urlencoded'


class SyntheticAdmin(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        quiet = patch('sys.stderr', new=io.StringIO()); quiet.start(); self.addCleanup(quiet.stop)  # Audit lines.
        self.auth = self.root/'auth.json'
        self.auth.write_text(json.dumps(app.credentials('admin', PASSWORD)))
        store = ContributionStore(self.root/'data')
        self.db = store.path
        sample = json.loads((ROOT/'tests/fixtures/research-v2-short.json').read_text())
        self.saved = [store.save(sample), store.save(sample)]
        expired = store.save(sample)
        with sqlite3.connect(self.db) as c:
            c.execute('UPDATE records SET expires=? WHERE id=?', (time.time()-1, expired['id']))
        self.before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        config = dict(auth=str(self.auth), origin=ORIGIN, database=str(self.db), temporary=str(self.root), game_port=1)
        self.server = app.AdminServer(('127.0.0.1', 0), config, export_package, verify_package)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True); thread.start()
        def stop():
            self.server.shutdown(); self.server.server_close(); thread.join()
        self.addCleanup(stop)
        self.token = self.issue()

    def issue(self, days=90, now=None):
        token, record = app.export_token(days, now)
        app.token_path(self.server.config).write_text(json.dumps(record))
        return token

    def request(self, path, method='GET', body=None, token=None, cookie=None, origin=None, authorization=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        headers = {'Host': HOST}
        if token: headers['Authorization'] = 'Bearer '+token
        if authorization: headers['Authorization'] = authorization
        if cookie: headers['Cookie'] = cookie
        if origin: headers['Origin'] = origin
        if body is not None: headers['Content-Type'] = FORM; body = body.encode()
        c.request(method, path if path.startswith('/') else app.PREFIX+path, body=body, headers=headers)
        response = c.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        c.close()
        return result

    def login(self):
        status, headers, _ = self.request('login', 'POST', urlencode(dict(username='admin', password=PASSWORD)), origin=ORIGIN)
        self.assertEqual(status, 303)
        return headers['Set-Cookie'].split(';')[0]


class TokenServerTests(SyntheticAdmin):
    def test_token_reads_records_preview_and_both_downloads(self):
        status, _, raw = self.request('api/records', token=self.token)
        self.assertEqual(status, 200)
        records = json.loads(raw)['records']; self.assertEqual(len(records), 2)
        self.assertEqual(self.request('api/preview?ref='+records[0]['ref'], token=self.token)[0], 200)
        status, headers, raw = self.request('download/research.cjresearch.zip?level=1', token=self.token)
        self.assertEqual(status, 200); self.assertIn('X-Research-Expires', headers)
        package = self.root/'all.zip'; package.write_bytes(raw)
        self.assertEqual(verify_package(package, database=self.db)['rounds'], 2)
        # No Origin header: a script, not a browser form; the token replaces the cookie CSRF check.
        status, _, raw = self.request('download/selected.cjresearch.zip', 'POST',
                                      urlencode({'refs': json.dumps([records[1]['ref']])}), token=self.token)
        self.assertEqual(status, 200)
        package = self.root/'one.zip'; package.write_bytes(raw)
        self.assertEqual(verify_package(package, database=self.db)['rounds'], 1)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), self.before)
        self.assertIn('export_token', json.loads(self.request('/healthz')[2])['features'])

    def test_token_never_reaches_other_routes_or_login(self):
        with patch.object(app, 'password_hash', side_effect=AssertionError('scope check must not hash')):
            for path in ('', 'api/options', 'api/analysis', 'api/usage', 'api/regional-usage', 'download/usage.json'):
                self.assertEqual(self.request(path, token=self.token)[0], 403, path)
            for path in ('login', 'logout'):
                body = urlencode(dict(username='admin', password=PASSWORD))
                self.assertEqual(self.request(path, 'POST', body, token=self.token, origin=ORIGIN)[0], 403, path)
            self.assertEqual(self.request('download/selected.cjresearch.zip', token=self.token)[0], 403)
            self.assertEqual(self.request('api/records', 'POST', 'refs=1', token=self.token)[0], 403)
        self.assertEqual(self.server.sessions, {})

    def test_token_only_counts_as_bearer_header(self):
        secret = self.token
        self.assertEqual(self.request('api/records?token='+secret)[0], 401)
        self.assertEqual(self.request('api/records', cookie=app.COOKIE+'='+secret)[0], 401)
        self.assertEqual(self.request('api/records', authorization='bearer '+secret)[0], 401)
        self.assertEqual(self.request('api/records', authorization='Basic '+secret)[0], 401)
        self.assertEqual(self.request('api/records?token='+secret, token=secret)[0], 400)

    def test_expiry_reissue_and_revocation_take_effect_without_restart(self):
        expired = self.issue(days=90, now=time.time()-91*86400)
        self.assertEqual(self.request('api/records', token=expired)[0], 401)
        first = self.issue(); second = self.issue()
        self.assertEqual(self.request('api/records', token=first)[0], 401)
        self.assertEqual(self.request('api/records', token=second)[0], 200)
        tampered = second[:-1]+('A' if second[-1] != 'A' else 'B')
        self.assertEqual(self.request('api/records', token=tampered)[0], 401)
        app.token_path(self.server.config).unlink()
        self.assertEqual(self.request('api/records', token=second)[0], 401)

    def test_revocation_during_export_sends_no_package(self):
        verifier = self.server.verifier
        def revoke_then_verify(package, **kwargs):
            app.token_path(self.server.config).unlink()
            return verifier(package, **kwargs)
        with patch.object(self.server, 'verifier', side_effect=revoke_then_verify):
            status, headers, raw = self.request('download/research.cjresearch.zip', token=self.token)
        self.assertEqual(status, 401); self.assertNotIn('Content-Disposition', headers); self.assertNotIn(b'PK', raw)
        # The reply is sent before the handler's finally block releases the lock.
        self.assertTrue(self.server.export_lock.acquire(timeout=5)); self.server.export_lock.release()
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['auth.json', 'data'])

    def test_failed_tokens_throttle_separately_from_password_login(self):
        wrong = 'cjx1.00000000.'+'A'*43
        for _ in range(app.TOKEN_FAILURES):
            self.assertEqual(self.request('api/records', token=wrong)[0], 401)
        with patch.object(app, 'password_hash', side_effect=AssertionError('throttled requests must not hash')):
            self.assertEqual(self.request('api/records', token=self.token)[0], 429)
        self.assertTrue(self.login())
        with self.server.lock:
            self.server.token_failures = type(self.server.token_failures)(t-61 for t in self.server.token_failures)
        self.assertEqual(self.request('api/records', token=self.token)[0], 200)

    def test_token_and_cookie_logins_stay_independent(self):
        cookie = self.login()
        self.assertEqual(self.request('api/records', token=self.token)[0], 200)
        self.assertEqual(self.request('api/records', cookie=cookie)[0], 200)
        newer = self.login()
        self.assertEqual(self.request('api/records', cookie=cookie)[0], 401)
        self.assertEqual(self.request('api/records', token=self.token)[0], 200)
        # With a header present the cookie is ignored, so a bad token cannot fall back to the session.
        self.assertEqual(self.request('api/records', cookie=newer, authorization='Bearer wrong')[0], 401)
        self.assertEqual(self.request('api/records', cookie=newer)[0], 200)

    def test_audit_lines_hold_route_status_and_label_only(self):
        label = self.token.split('.')[1]
        ref = json.loads(self.request('api/records', token=self.token)[2])['records'][0]['ref']
        with patch('sys.stderr', new=io.StringIO()) as log:
            self.request('api/records?since=2026-10-01&level=1', token=self.token)
            self.request('api/preview?ref='+ref, token=self.token)
            self.request('api/records', token='cjx1.00000000.'+'B'*43)
            self.request('api/options', token=self.token)
            self.request('download/research.cjresearch.zip', token=self.token)
        lines = log.getvalue().splitlines()
        self.assertEqual(lines, ['export-token GET records 200 id='+label, 'export-token GET preview 200 id='+label,
                                 'export-token GET records 401 id=-', 'export-token GET other 403 id=-',
                                 'export-token GET download 200 id='+label])
        text = log.getvalue()
        for private in (self.token.split('.')[2], 'B'*43, 'since', '2026-10-01', ref, '127.0.0.1'):
            self.assertNotIn(private, text)


class PullScriptTests(SyntheticAdmin):
    def setUp(self):
        super().setUp()
        port = self.server.server_port
        connection = patch.object(pull, 'connection', lambda: http.client.HTTPConnection('127.0.0.1', port, timeout=10))
        connection.start(); self.addCleanup(connection.stop)
        self.token_file = self.root/'config/research-export.token'
        pull.save_token(self.token_file, prompt=lambda _: self.token)
        self.out = self.root/'downloads'

    def run_main(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            pull.main([*args, '--token-file', str(self.token_file)])
        self.assertNotIn(self.token.split('.')[2], stdout.getvalue()+stderr.getvalue())
        return stdout.getvalue()

    def test_pull_keeps_only_a_verified_private_package(self):
        result = json.loads(self.run_main('pull', '--out', str(self.out), '--level', '1'))
        files = list(self.out.iterdir())
        self.assertEqual([Path(result['path'])], files)
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(verify_package(files[0], database=self.db)['rounds'], result['rounds'])
        self.assertEqual(result['rounds'], 2)
        self.assertEqual(hashlib.sha256(files[0].read_bytes()).hexdigest(), result['sha256'])

    def test_list_then_pull_selected_refs(self):
        listed = json.loads(self.run_main('list'))
        self.assertEqual(listed['total'], 2)
        ref = listed['records'][0]['ref']
        result = json.loads(self.run_main('pull', '--out', str(self.out), '--refs', ref))
        with zipfile.ZipFile(result['path']) as archive:
            self.assertEqual([s['source_ref'] for s in json.loads(archive.read('manifest.json'))['sources']], [ref])

    def test_rejected_token_or_failed_manifest_leaves_no_file(self):
        app.token_path(self.server.config).unlink()
        with self.assertRaisesRegex(SystemExit, '401'):
            self.run_main('pull', '--out', str(self.out))
        self.assertEqual(list(self.out.iterdir()), [])
        self.issue_into_file()
        with patch.object(pull, 'verify_package', side_effect=ValueError('Artifact digest mismatch')):
            with self.assertRaisesRegex(SystemExit, 'manifest'):
                self.run_main('pull', '--out', str(self.out))
        self.assertEqual(list(self.out.iterdir()), [])

    def issue_into_file(self):
        self.token = self.issue()
        pull.save_token(self.token_file, replace=True, prompt=lambda _: self.token)

    def test_token_file_must_be_private_outside_the_repository(self):
        self.assertEqual(self.token_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(pull.read_token(self.token_file), self.token)
        with self.assertRaises(pull.PullError):
            pull.save_token(self.token_file, prompt=lambda _: self.token)
        self.token_file.chmod(0o644)
        with self.assertRaisesRegex(pull.PullError, 'chmod 600'):
            pull.read_token(self.token_file)
        with self.assertRaisesRegex(pull.PullError, '仓库'):
            pull.read_token(ROOT/'.research-export.token')
        with self.assertRaisesRegex(pull.PullError, '格式'):
            pull.save_token(self.root/'other.token', prompt=lambda _: 'not-a-token')
        self.assertFalse((self.root/'other.token').exists())


class TokenCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = root/'config.json'
        self.config.write_text(json.dumps({'origin': ORIGIN, 'auth': str(root/'auth.json')}))
        self.path = root/'export-token.json'
        for p in (patch.object(operator, 'CONFIG', self.config), patch.object(operator.shutil, 'chown'),
                  patch.object(operator.socket, 'gethostname', return_value='VM-0-5-ubuntu')):
            p.start(); self.addCleanup(p.stop)

    def output(self, function, *args):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            function(*args)
        return stdout.getvalue()

    def test_issue_shows_token_once_and_stores_only_its_hash(self):
        printed = self.output(operator.issue_token, 90)
        token = printed.strip().splitlines()[-1]
        self.assertRegex(token, pull.TOKEN_PATTERN)
        stored = self.path.read_text(); record = json.loads(stored)
        self.assertNotIn(token.split('.')[2], stored)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(app.password_hash(token.split('.')[2], record['salt']), record['token_hash'])
        self.assertEqual(record['expires_at']-record['issued_at'], 90*86400)
        status = self.output(operator.token_status)
        self.assertIn(record['id'], status)
        for private in ('salt', 'token_hash', token.split('.')[2]):
            self.assertNotIn(private, status)
        again = self.output(operator.issue_token, 30)
        self.assertTrue(json.loads(again[:again.index('}')+1])['previous_token_revoked'])
        self.assertNotEqual(json.loads(self.path.read_text())['id'], record['id'])

    def test_revoke_is_immediate_and_idempotent(self):
        self.output(operator.issue_token, 90)
        self.assertIn('"token_existed": true', self.output(operator.revoke_token))
        self.assertFalse(self.path.exists())
        self.assertIn('"token_existed": false', self.output(operator.revoke_token))
        self.assertIn('no-export-token', self.output(operator.token_status))

    def test_rejects_bad_lifetime_and_other_hosts(self):
        for days in (0, 366):
            with self.assertRaises(ValueError):
                self.output(operator.issue_token, days)
        self.assertFalse(self.path.exists())
        with patch.object(operator.socket, 'gethostname', return_value='other-host'):
            with self.assertRaises(ValueError):
                self.output(operator.issue_token, 90)


class AdminUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.game = root/'game/release'; self.game.mkdir(parents=True)
        self.current = root/'current'; self.current.symlink_to(self.game)
        names = ['scripts/research_export.py', 'research_record.py', 'hosted_records.py',
                 'schema_check.py', 'schemas/research-record.schema.json']
        for name in names:
            p = self.game/name; p.parent.mkdir(exist_ok=True); p.write_text('synthetic '+name)
        self.releases = root/'admin-releases'
        self.old = self.releases/'v2-old'; self.old.mkdir(parents=True)
        for name in (*operator.APP_FILES, *update.DATA_PROGRAMS):
            (self.old/name).write_text('synthetic previous '+name)
        self.bundle = root/'bundle'; self.bundle.mkdir()
        for name in update.BUNDLE_FILES:
            (self.bundle/name).write_text('synthetic new '+name)
        for name in update.DATA_PROGRAMS:
            (self.bundle/name).write_bytes((self.old/name).read_bytes())
        (self.bundle/'game-binding.json').write_text(json.dumps({'format': 'chefjeff-admin-game-binding-v1',
            'files': {n: operator.sha((self.game/n).read_bytes()) for n in names}}))
        files = {p.name: operator.sha(p.read_bytes()) for p in self.bundle.iterdir()}
        (self.bundle/'manifest.json').write_text(json.dumps({'bundle_id': 'c'*16, 'files': files}))
        self.config = root/'config.json'
        self.config.write_text(json.dumps({'release': str(self.game), 'origin': ORIGIN,
            'database': '/var/lib/chefjeff-data/contributions.sqlite3', 'auth': '/etc/chefjeff-admin/auth.json',
            'temporary': '/run/chefjeff-admin', 'game_port': 8780}))
        self.admin = root/'admin.service'; self.data = root/'data.service'
        self.admin.write_text('[Service]\nExecStart=/usr/bin/python3 '+str(self.old)+'/admin_server.py --config '+str(self.config)
                              +'\nWorkingDirectory='+str(self.old)+'\nProtectSystem=strict\n')
        self.data.write_text('[Service]\nExecStart=/usr/bin/python3 '+str(self.old)+'/authority_runner.py '
                             +' '.join(update.DATA_ARGUMENTS)+'\nReadWritePaths=/var/lib/chefjeff-data\n')
        self.original_admin, self.original_data = self.admin.read_bytes(), self.data.read_bytes()
        self.calls, self.probes, self.pids = [], [], {'chefjeff.service': '100', 'chefjeff-data.service': '200'}
        def prop(unit, key):
            return {'ActiveState': 'active', 'DropInPaths': '',
                    'FragmentPath': str(self.admin if unit == 'chefjeff-admin.service' else self.data)}[key]
        for p in (patch.object(update, 'WORK', root/'work'), patch.object(update, 'CONFIG', self.config),
                  patch.object(update, 'CURRENT', self.current), patch.object(update, 'ADMIN_RELEASES', self.releases),
                  patch.object(update, 'ADMIN_UNIT', self.admin), patch.object(update, 'DATA_UNIT', self.data),
                  patch.object(update, 'features', return_value=['export_token']),
                  patch.object(update, 'probe', side_effect=lambda *a: self.probes.append(a)),
                  patch.object(update.time, 'sleep'),
                  patch.object(operator, 'property_value', side_effect=prop),
                  patch.object(operator, 'auth_stat', return_value=[1, 2, 3]),
                  patch.object(operator, 'pid', side_effect=lambda unit: self.pids[unit]),
                  patch.object(operator, 'backend_health', return_value=True),
                  patch.object(operator, 'run', side_effect=lambda *a: self.calls.append(a))):
            p.start(); self.addCleanup(p.stop)

    def test_prepare_is_inert_then_activation_restarts_only_the_console_and_rollback_restores(self):
        with contextlib.redirect_stdout(io.StringIO()):
            update.prepare(self.bundle)
            self.assertEqual(self.calls, []); self.assertEqual(self.admin.read_bytes(), self.original_admin)
            update.activate(self.bundle)
            new = self.releases/('v2-'+'c'*16)
            self.assertIn(str(new)+'/admin_server.py', self.admin.read_text())
            self.assertNotIn(str(self.old), self.admin.read_text())
            self.assertEqual(self.data.read_bytes(), self.original_data)
            self.assertIn(('/research-admin/api/options', 403, update.PROBE), self.probes)
            update.activate(self.bundle)  # Idempotent once active.
            update.rollback(self.bundle)
        self.assertEqual(self.admin.read_bytes(), self.original_admin)
        self.assertTrue((self.old/'admin_server.py').exists() and (new/'admin_server.py').exists())
        restarts = [a for a in self.calls if a[1] in ('restart', 'start', 'stop', 'reload')]
        self.assertEqual(restarts, [('systemctl', 'restart', 'chefjeff-admin.service')]*2)

    def test_console_keeps_its_bound_game_while_current_runs_another_build(self):
        trial = self.game.parent/'trial'; trial.mkdir()
        (trial/'jev.py').write_text('trial build with different model code')
        self.current.unlink(); self.current.symlink_to(trial)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            update.prepare(self.bundle)
        printed = json.loads(out.getvalue())
        self.assertEqual(printed['console_game_release'], str(self.game.resolve()))
        self.assertEqual(printed['current_game_release'], str(trial.resolve()))
        self.current.unlink(); self.current.symlink_to(self.game)
        with self.assertRaisesRegex(ValueError, '当前游戏目录'):
            update.activate(self.bundle)
        self.assertEqual(self.calls, [])
        self.current.unlink(); self.current.symlink_to(trial)
        with contextlib.redirect_stdout(io.StringIO()):
            update.activate(self.bundle)
        self.assertIn(str(self.releases/('v2-'+'c'*16)), self.admin.read_text())
        self.assertEqual(json.loads(self.config.read_text())['release'], str(self.game))

    def test_refuses_a_package_for_another_game_or_changed_data_programs(self):
        (self.game/'research_record.py').write_text('changed game')
        with self.assertRaisesRegex(ValueError, 'binding'):
            update.prepare(self.bundle)
        (self.game/'research_record.py').write_text('synthetic research_record.py')
        (self.old/'source_observer.py').write_text('data service runs different code')
        with self.assertRaisesRegex(ValueError, '共享数据'):
            update.prepare(self.bundle)
        self.assertFalse((self.releases/('v2-'+'c'*16)).exists()); self.assertEqual(self.calls, [])

    def test_failed_activation_restores_the_previous_console(self):
        with contextlib.redirect_stdout(io.StringIO()):
            update.prepare(self.bundle)
        def changed_game(*args):
            self.pids['chefjeff.service'] = '101'
        with patch.object(update, 'probe', side_effect=changed_game):
            with self.assertRaisesRegex(ValueError, '进程'):
                update.activate(self.bundle)
        self.assertEqual(self.admin.read_bytes(), self.original_admin)
        self.assertEqual(self.data.read_bytes(), self.original_data)
        state = json.loads((update.WORK/('c'*16)/'state.json').read_text())
        self.assertEqual(state['phase'], 'rolled-back')
        self.assertEqual(self.calls[-2:], [('systemctl', 'daemon-reload'), ('systemctl', 'restart', 'chefjeff-admin.service')])

    def test_activation_refuses_changed_unit_or_config(self):
        with contextlib.redirect_stdout(io.StringIO()):
            update.prepare(self.bundle)
        self.config.write_text('{}')
        with self.assertRaises(ValueError):
            update.activate(self.bundle)
        self.assertEqual(self.calls, []); self.assertEqual(self.admin.read_bytes(), self.original_admin)


if __name__ == '__main__':
    unittest.main(verbosity=2)
