import json
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
import zipfile

from kitchen import load_config
from jev import DecisionLoop
from spatial_kitchen import SpatialKitchen
from player_api import PlayerGameSession
from test_web import FakeJournal
from test_jev import NoKeyClient
from scripts.package_web import package, PUBLIC_FILES
from release_info import RUNTIME_FILES, release_info
from scripts.audit_release import markers


class BudgetTests(unittest.TestCase):
    def make(self,error=False):
        c=load_config();c['ai_max_calls']=1
        k=SpatialKitchen(c);client=NoKeyClient(c,reply='fetch',error=error);rows=[]
        ai=DecisionLoop(k,client,lambda kind,data:rows.append((kind,data)),lambda text:None)
        return k,ai,client,rows
    def finish_response(self,ai):
        deadline=time.monotonic()+2
        while ai.q.empty() and time.monotonic()<deadline:time.sleep(.001)
        self.assertFalse(ai.q.empty());ai.poll()
    def test_last_allowed_response_executes_and_no_extra_request(self):
        k,ai,c,rows=self.make();ai.poll();self.finish_response(ai)
        self.assertIsNotNone(k.chefs['jeff'].job)
        k.advance(6)
        with patch('jev.time.monotonic',return_value=time.monotonic()+100):
            for _ in range(3):ai.poll()
        self.assertEqual(ai.calls,1);self.assertEqual(c.calls,1)
        self.assertEqual(sum(kind=='call_limit' for kind,_ in rows),1)
        self.assertIsNotNone(k.chefs['jeff'].hand)
    def test_failed_calls_count_against_limit(self):
        k,ai,c,rows=self.make(error=True);ai.poll();self.finish_response(ai)
        with patch('jev.time.monotonic',return_value=time.monotonic()+100):ai.poll()
        self.assertEqual(c.calls,1);self.assertEqual(ai.failures,1)
        self.assertEqual(ai.error_count,1)
    def session(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        g=PlayerGameSession(credential_path=Path(tmp.name)/'.player-api.json',
                           journal_factory=FakeJournal,connector=lambda c,s:NoKeyClient(c),kitchen_factory=SpatialKitchen)
        self.addCleanup(g.close)
        return g
    def cmd(self,g,path,**extra):
        return g.command('/api/'+path,{'game_id':g.game_id,'request_id':uuid.uuid4().hex,**extra})
    def test_limits_validate_and_freeze_during_round(self):
        g=self.session()
        for v in [0,2001,1.5,True,'5',None]:self.assertEqual(self.cmd(g,'limits',max_calls=v)[0],400)
        self.assertEqual(self.cmd(g,'limits',max_calls=2)[0],200)
        g.setting={'provider':'jev','api_key':'offline-key','model':'unit-test'}
        self.assertEqual(self.cmd(g,'start')[0],200)
        self.assertEqual(g.ai.call_limit,2)
        self.assertEqual(self.cmd(g,'limits',max_calls=10)[0],409)
        self.cmd(g,'pause');self.assertEqual(self.cmd(g,'limits',max_calls=10)[0],409)
        self.cmd(g,'reset');self.assertEqual(self.cmd(g,'limits',max_calls=10)[0],200)
        self.cmd(g,'start');self.assertEqual(g.ai.call_limit,10);self.assertEqual(g.ai.calls,0)
    def test_feedback_is_allowlist_and_preview_calls_no_model(self):
        g=self.session();g.setting={'provider':'compatible','api_key':'PRIVATE_SENTINEL','model':'PRIVATE_SENTINEL','base_url':'https://private.example'}
        g.note('PRIVATE_SENTINEL');g.k.emit('PRIVATE_SENTINEL',kind='action_done',actor='human',action='fetch')
        g.k.emit('PRIVATE_SENTINEL',kind='invented',secret='PRIVATE_SENTINEL')
        status,data=self.cmd(g,'feedback');self.assertEqual(status,200)
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(data));self.assertNotIn('private.example',json.dumps(data))
        self.assertEqual(data['report']['recent_events'][-1]['action'],'fetch')
        self.assertIsNone(g.ai);self.assertEqual(g.connection_checks,0)
    def test_feedback_bounded_and_same_request_deduplicated(self):
        g=self.session()
        for _ in range(100):g.k.emit('ignored',kind='action_done',actor='jeff',action='fetch')
        body={'game_id':g.game_id,'request_id':'preview'}
        first=g.command('/api/feedback',body)
        self.assertEqual(len(first[1]['report']['recent_events']),80)
        g.k.emit('ignored',kind='action_done',actor='jeff',action='wash')
        self.assertEqual(g.command('/api/feedback',body),first)


class PackageTests(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        for name in RUNTIME_FILES+PUBLIC_FILES+('cocos-kitchen/build/web/index.html',):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
        return root
    def test_package_includes_untracked_runtime_excludes_local_data_and_records_hashes(self):
        root=self.fixture()
        for name in ['.env','.player-api.json','.player-memory.json','private.txt']:(root/name).write_text('PRIVATE_SENTINEL')
        (root/'logs').mkdir();(root/'logs/raw.jsonl').write_text('PRIVATE_SENTINEL')
        output,manifest=package(root)
        with zipfile.ZipFile(output) as z:
            self.assertIn('chefjeff-web-demo/cooperation_memory.py',z.namelist())
            self.assertNotIn(b'PRIVATE_SENTINEL',b''.join(z.read(n) for n in z.namelist()))
            self.assertTrue(z.getinfo('chefjeff-web-demo/start-web.command').external_attr>>16 & 0o111)
        self.assertEqual(manifest['release'],release_info(root))
    def test_missing_runtime_fails_without_replacing_old_zip(self):
        root=self.fixture();out,_=package(root);old=out.read_bytes();(root/'cooperation_memory.py').unlink()
        with self.assertRaises(ValueError):package(root)
        self.assertEqual(old,out.read_bytes())

    def test_real_package_keeps_client_dependencies_and_audio_for_creator_rebuild(self):
        root = Path(__file__).resolve().parents[1]
        scripts = root / 'cocos-kitchen/assets/scripts'
        client = scripts / 'KitchenClient.ts'
        dependencies = re.findall(r"from ['\"]\./([^'\"]+)['\"]", client.read_text())
        source_files = [client, *(scripts / (name + '.ts') for name in dependencies)]
        source_files += [file.with_suffix('.ts.meta') for file in source_files]
        audio = root / 'cocos-kitchen/assets/resources/audio'
        index = json.loads((audio / 'index.json').read_text())
        names = set(index['sounds']) | set(index['wash']) | set(index['chop'])
        source_files += [audio / (name + suffix) for name in names for suffix in ('.mp3', '.mp3.meta')]
        with tempfile.TemporaryDirectory() as tmp:
            output, _ = package(root, Path(tmp) / 'demo.zip')
            with zipfile.ZipFile(output) as archive:
                for file in source_files:
                    name = 'chefjeff-web-demo/' + file.relative_to(root).as_posix()
                    with self.subTest(source=name):
                        self.assertIn(name, archive.namelist())
                        self.assertEqual(archive.read(name), file.read_bytes())

    def test_real_package_keeps_touch_controls_and_matching_web_entries(self):
        root = Path(__file__).resolve().parents[1]
        source = root / 'cocos-kitchen/touch-controls.js'
        shipped = root / 'cocos-kitchen/build/web/touch-controls.js'
        self.assertEqual(source.read_bytes(), shipped.read_bytes(),
                         'a Creator rebuild and the prebuilt web app need the same controls')
        entries = [root / 'cocos-kitchen/web-shell.html',
                   root / 'cocos-kitchen/build/web/index.html']
        for entry in entries:
            with self.subTest(entry=entry):
                self.assertRegex(entry.read_text(), r'<script[^>]+src=["\'][^"\']*touch-controls\.js["\']')
        with tempfile.TemporaryDirectory() as tmp:
            output, _ = package(root, Path(tmp) / 'demo.zip')
            with zipfile.ZipFile(output) as archive:
                for file in [source, shipped, *entries]:
                    name = 'chefjeff-web-demo/' + file.relative_to(root).as_posix()
                    with self.subTest(source=name):
                        self.assertIn(name, archive.namelist())
                        self.assertEqual(archive.read(name), file.read_bytes())
    def test_symlink_and_local_paths_rejected(self):
        root=self.fixture();p=root/'cocos-kitchen/build/web/link.js';p.symlink_to(root/'config.json')
        with self.assertRaises(ValueError):package(root)
        p.unlink();p.write_text('source '+'/'+'Users/'+'private/code')
        with self.assertRaises(ValueError):package(root)
    def test_build_fingerprint_changes_when_runtime_changes(self):
        root=self.fixture();before=release_info(root);(root/'feedback.py').write_text('changed')
        self.assertNotEqual(before,release_info(root))
    def test_untracked_secret_in_public_file_rejected(self):
        root=self.fixture();(root/'README.md').write_text('sk-'+'x'*30)
        with self.assertRaises(ValueError):package(root)
    def test_audit_detects_markers_without_returning_values(self):
        secret=b'sk-'+b'x'*30
        self.assertEqual(markers(secret),['provider_key'])
        self.assertNotIn(secret.decode(),str(markers(secret)))

if __name__=='__main__':unittest.main()
