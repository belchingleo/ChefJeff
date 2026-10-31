"""Isolated filesystem and mocked service-manager lifecycle; no live root operations."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ops' / 'research_admin'))

import upgrade_admin as up

ADMIN='''[Service]
User=chefjeff
ExecStart=/usr/bin/python3 /opt/chefjeff-admin/releases/old-example/admin_server.py --config /etc/chefjeff-admin/config.json
WorkingDirectory=/opt/chefjeff-admin/releases/old-example
ProtectSystem=strict
ReadOnlyPaths=/var/lib/chefjeff-data
'''
DATA='''[Service]
User=chefjeff
WorkingDirectory=/opt/chefjeff/current
ExecStart=/usr/bin/python3 /opt/chefjeff/current/shared_server.py --port 8790 --data-dir /var/lib/chefjeff-data --credentials /etc/chefjeff/data-server.json
ProtectSystem=strict
ReadWritePaths=/var/lib/chefjeff-data
'''


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        def mapped(value='.'):
            value=str(value)
            return self.root/value.lstrip('/') if value.startswith(('/root/','/etc/','/var/','/opt/')) else Path(value)
        self.path=mapped
        self.work=mapped('/root/chefjeff-admin-v2-upgrade');self.work.mkdir(parents=True)
        self.bundle=self.root/'bundle';self.bundle.mkdir()
        for name in (*up.APP_FILES,'upgrade_admin.py'):(self.bundle/name).write_bytes((ROOT/'ops'/'research_admin'/name).read_bytes())
        manifest={'bundle_id':'a'*16,'files':{name:hashlib.sha256((self.bundle/name).read_bytes()).hexdigest() for name in (*up.APP_FILES,'upgrade_admin.py')}}
        (self.bundle/'manifest.json').write_text(json.dumps(manifest))
        self.admin=mapped('/etc/systemd/system/chefjeff-admin.service');self.admin.parent.mkdir(parents=True);self.admin.write_text(ADMIN)
        self.data=mapped('/etc/systemd/system/chefjeff-data.service');self.data.write_text(DATA)
        self.config=mapped('/etc/chefjeff-admin/config.json');self.config.parent.mkdir(parents=True)
        self.auth=self.config.parent/'auth.json';self.auth.write_text('synthetic account file; never parsed by upgrade')
        self.auth_before=self.auth.read_bytes()
        self.config.write_text(json.dumps({'origin':'https://chefjeff.belchingleo.online','database':'/var/lib/chefjeff-data/contributions.sqlite3','auth':str(self.auth)}))
        self.site=mapped('/etc/nginx/sites-available/chefjeff');self.site.parent.mkdir(parents=True);self.site.write_text('synthetic unchanged nginx config')
        review=mapped('/root/chefjeff-admin-review/state.json');review.parent.mkdir(parents=True);review.write_text(json.dumps({'site_file':str(self.site)}))
        release=mapped('/opt/chefjeff/releases/china-en-v4-269d7af296be/chefjeff-web-demo');release.mkdir(parents=True)
        mapped('/opt/chefjeff/current').symlink_to(release,target_is_directory=True)
        self.pids={'chefjeff.service':'100','chefjeff-data.service':'200','chefjeff-admin.service':'300'}
        self.calls=[]
        def prop(unit,key):
            if key=='MainPID':return self.pids[unit]
            if key=='FragmentPath':return str(self.admin if unit=='chefjeff-admin.service' else self.data)
            if key=='DropInPaths':return ''
            if key=='ActiveState':return 'active'
            raise AssertionError(key)
        def run(*args):
            self.calls.append(args)
            if args[:2]==('systemctl','restart'):
                self.pids[args[2]]=str(int(self.pids[args[2]])+1)
                if args[2]=='chefjeff-data.service':
                    marker=mapped('/var/lib/chefjeff-data/record-sources.sqlite3');marker.parent.mkdir(parents=True,exist_ok=True);marker.touch()
        self.patchers=[patch.object(up,'Path',mapped),patch.object(up,'HERE',self.bundle),patch.object(up,'WORK',self.work),
            patch.object(up,'STATE',self.work/'state.json'),patch.object(up,'ADMIN_UNIT',self.admin),patch.object(up,'DATA_UNIT',self.data),
            patch.object(up,'CONFIG',self.config),patch.object(up.socket,'gethostname',return_value='VM-0-5-ubuntu'),
            patch.object(up,'property_value',side_effect=prop),patch.object(up,'run',side_effect=run),
            patch.object(up,'backend_health',return_value=True),patch.object(up,'data_ready',return_value=True),
            patch.object(up,'protected_https'),patch.object(up.time,'sleep')]
        for p in self.patchers:p.start()

    def tearDown(self):
        for p in reversed(self.patchers):p.stop()
        self.temp.cleanup()

    def test_prepare_activate_idempotence_rollback_and_preserved_account_game_nginx(self):
        up.prepare();self.assertEqual(self.admin.read_text(),ADMIN);self.assertEqual(self.data.read_text(),DATA);self.assertEqual(self.calls,[])
        up.activate();self.assertIn('authority_runner.py',self.data.read_text());self.assertEqual(self.pids['chefjeff.service'],'100')
        self.assertEqual(self.auth.read_bytes(),self.auth_before);self.assertEqual(self.site.read_text(),'synthetic unchanged nginx config')
        count=len(self.calls);up.activate();self.assertEqual(len(self.calls),count)
        up.rollback();self.assertEqual(self.admin.read_text(),ADMIN);self.assertEqual(self.data.read_text(),DATA)
        self.assertEqual(self.auth.read_bytes(),self.auth_before)
        for call in self.calls:
            self.assertNotIn('nginx',call);self.assertNotIn('nginx.service',call)
            if call[:2]==('systemctl','restart'):self.assertNotEqual(call[-1],'chefjeff.service')

    def test_failed_https_rolls_back_both_units_and_keeps_account(self):
        up.prepare()
        with patch.object(up,'protected_https',side_effect=ValueError('synthetic failed probe')):
            with self.assertRaises(ValueError):up.activate()
        self.assertEqual(self.admin.read_text(),ADMIN);self.assertEqual(self.data.read_text(),DATA)
        self.assertEqual(json.loads((self.work/'state.json').read_text())['phase'],'rolled-back')
        self.assertEqual(self.auth.read_bytes(),self.auth_before)

    def test_refuse_changed_unit_before_restarting_any_service(self):
        up.prepare();self.data.write_text(DATA+'# newer edit\n')
        with self.assertRaises(ValueError):up.activate()
        self.assertEqual(self.calls,[]);self.assertIn('newer edit',self.data.read_text())

    def test_unit_transform_preserves_hardening_and_rejects_unknown_arguments(self):
        admin,data,_=up.replacement_units(ADMIN,DATA,Path('/opt/chefjeff-admin/releases/new'))
        self.assertIn('ReadOnlyPaths=/var/lib/chefjeff-data',admin)
        self.assertIn('ReadWritePaths=/var/lib/chefjeff-data',data)
        self.assertIn('--credentials /etc/chefjeff/data-server.json',data)
        with self.assertRaises(ValueError):up.replacement_units(ADMIN,DATA.replace('--port 8790','--port 9999'),Path('/new'))


if __name__=='__main__':unittest.main(verbosity=2)
