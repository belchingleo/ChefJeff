"""New game binding and rollback are exercised on isolated files and synthetic units."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ops/research_admin'))
import release_binding as binding
import release_upgrade as up


class ReleaseUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.old=root/'game/old';self.old.mkdir(parents=True)
        self.target=root/'game/new';self.target.mkdir()
        self.current=root/'current';self.current.symlink_to(self.old)
        self.bundle=root/'bundle';self.bundle.mkdir()
        names=['scripts/research_export.py','research_record.py','hosted_records.py',
               'schema_check.py','schemas/research-record.schema.json']
        for name in names:
            p=self.target/name;p.parent.mkdir(exist_ok=True);p.write_text('synthetic '+name)
        self.binding={'format':'chefjeff-admin-game-binding-v1',
                      'files':{n:up.legacy.sha((self.target/n).read_bytes()) for n in names}}
        (self.bundle/'game-binding.json').write_text(json.dumps(self.binding))
        for name in (*up.legacy.APP_FILES,'release_binding.py','release_upgrade.py','upgrade_admin.py'):
            (self.bundle/name).write_text('synthetic public program '+name)
        self.manifest={'bundle_id':'b'*16,'files':{p.name:up.legacy.sha(p.read_bytes()) for p in self.bundle.iterdir()}}
        (self.bundle/'manifest.json').write_text(json.dumps(self.manifest))
        # As on the live server: the console and the shared-data service run from one program
        # folder, and the console is bound to the game the current link points at.
        self.old_admin=root/'admin/v2-old';self.old_admin.mkdir(parents=True)
        programs={}
        for name in up.LEGACY_PROGRAMS:
            p=self.old_admin/name;p.write_text('synthetic previous '+name);programs[name]=up.legacy.sha(p.read_bytes())
        self.config=root/'config.json'
        self.original=json.dumps({'release':str(self.old),'origin':'https://'+up.legacy.DOMAIN,
            'database':'/var/lib/chefjeff-data/contributions.sqlite3','auth':'/etc/chefjeff-admin/auth.json',
            'temporary':'/run/chefjeff-admin','game_port':8780}).encode()
        self.config.write_bytes(self.original)
        self.admin=root/'admin.service';self.data=root/'data.service'
        self.admin.write_text('[Service]\nExecStart=/usr/bin/python3 '+str(self.old_admin)+'/admin_server.py --config '+str(self.config)+'\nWorkingDirectory='+str(self.old_admin)+'\nProtectSystem=strict\n')
        self.data.write_text('[Service]\nWorkingDirectory=/opt/chefjeff/current\nExecStart=/usr/bin/python3 '+str(self.old_admin)+'/authority_runner.py --port 8790 --data-dir /var/lib/chefjeff-data --credentials /etc/chefjeff/data-server.json\nReadWritePaths=/var/lib/chefjeff-data\n')
        self.original_admin=self.admin.read_bytes();self.original_data=self.data.read_bytes()
        self.work=root/'review';self.work.mkdir()
        self.calls=[];self.game_state='active'
        def prop(unit,key):
            if key=='ActiveState':return self.game_state if unit=='chefjeff.service' else 'active'
            if key=='DropInPaths':return ''
            if key=='FragmentPath':return str(self.admin if unit=='chefjeff-admin.service' else self.data)
            raise AssertionError(key)
        for name,value in {'WORK':self.work,'CONFIG':self.config,'CURRENT':self.current,
                           'RELEASES':self.target.parent,'ADMIN_RELEASES':self.old_admin.parent,
                           'ADMIN_UNIT':self.admin,'DATA_UNIT':self.data,'LEGACY_GAME':self.old,
                           'LEGACY_ADMIN':self.old_admin,'LEGACY_PROGRAMS':programs}.items():
            p=patch.object(up,name,value);p.start();self.addCleanup(p.stop)
        for p in [patch.object(up.legacy,'property_value',side_effect=prop),
                  patch.object(up.legacy,'auth_stat',return_value=[1,2,3]),
                  patch.object(up.legacy,'run',side_effect=lambda *a:self.calls.append(a)),
                  patch.object(up.legacy,'backend_health',return_value=True),
                  patch.object(up.legacy,'data_ready',return_value=True),
                  patch.object(up.legacy,'protected_https')]:
            p.start();self.addCleanup(p.stop)

    def switch(self):
        self.current.unlink();self.current.symlink_to(self.target);self.game_state='inactive'

    def test_preparation_is_inert_and_activation_binds_new_validator_then_rollback_restores_config(self):
        up.prepare(self.target,self.bundle)
        self.assertEqual(self.config.read_bytes(),self.original);self.assertEqual(self.calls,[])
        self.switch();up.activate()
        self.assertEqual(json.loads(self.config.read_text())['release'],str(self.target))
        new=up.read_state()['new_admin']
        self.assertIn(new+'/admin_server.py',self.admin.read_text())
        self.assertIn(new+'/authority_runner.py',self.data.read_text())
        self.assertNotIn(str(self.old_admin),self.admin.read_text()+self.data.read_text())
        self.assertIn('WorkingDirectory=/opt/chefjeff/current',self.data.read_text())  # data still follows the game link
        self.assertIn('ProtectSystem=strict',self.admin.read_text())
        self.assertIn('ReadWritePaths=/var/lib/chefjeff-data',self.data.read_text())
        up.rollback()
        self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual(self.admin.read_bytes(),self.original_admin)
        self.assertEqual(self.data.read_bytes(),self.original_data)
        self.assertEqual(self.current.resolve(),self.target)  # The coordinated operator owns the game link.
        self.assertEqual(self.calls[-1],('systemctl','daemon-reload'))
        self.assertFalse(any(a[-1:] in [('chefjeff.service',),('nginx.service',)] for a in self.calls))

    def test_requires_game_stop_and_exact_prepared_config_before_restarting(self):
        up.prepare(self.target,self.bundle)
        with self.assertRaises(ValueError):up.activate()
        self.assertEqual(self.calls,[])
        self.switch();self.config.write_text('{}')
        with self.assertRaises(ValueError):up.activate()
        self.assertEqual(self.calls,[])

    def test_changed_schema_is_rejected_even_with_identical_exporter(self):
        (self.target/'schemas/research-record.schema.json').write_text('changed')
        with self.assertRaises(ValueError):up.prepare(self.target,self.bundle)
        self.assertFalse((self.work/'state.json').exists());self.assertEqual(self.calls,[])

    def test_failed_https_restores_old_config_and_leaves_authority_stopped_for_coordinated_rollback(self):
        up.prepare(self.target,self.bundle);self.switch()
        with patch.object(up.legacy,'protected_https',side_effect=ValueError('synthetic probe failure')):
            with self.assertRaises(ValueError):up.activate()
        self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual(self.admin.read_bytes(),self.original_admin)
        self.assertEqual(self.data.read_bytes(),self.original_data)
        self.assertEqual(up.read_state()['phase'],'rolled-back')
        self.assertEqual(self.calls[-3:],[('systemctl','stop','chefjeff-admin.service'),
            ('systemctl','stop','chefjeff-data.service'),('systemctl','daemon-reload')])

    def test_refuses_another_binding_or_changed_data_program(self):
        self.config.write_text(self.original.decode().replace(str(self.old),str(self.target)))
        with self.assertRaises(ValueError):up.prepare(self.target,self.bundle)
        self.config.write_bytes(self.original)
        (self.old_admin/'authority_runner.py').write_text('changed')
        with self.assertRaises(ValueError):up.prepare(self.target,self.bundle)
        self.assertFalse((self.work/'state.json').exists());self.assertEqual(self.calls,[])

    def test_refuses_changed_v2_arguments_and_target_outside_release_root(self):
        self.data.write_bytes(self.original_data.replace(b'--port 8790',b'--port 9999'))
        with self.assertRaises(ValueError):up.prepare(self.target,self.bundle)
        with self.assertRaises(ValueError):up.prepare(self.target.parent.parent,self.bundle)
        self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
