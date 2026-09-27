import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import uuid

from kitchen import load_config
from player_api import PlayerGameSession, CompatibleClient, NoRedirect, settings_from
from test_web import FakeJournal

KEY = 'test-player-secret-never-real'


class PlayerApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'.player-api.json'
        self.client = Mock()
        self.client.ask.return_value = {'choice': 'ready'}
        self.connector = Mock(return_value=self.client)
        self.g = self.make()
    def make(self):
        g = PlayerGameSession(credential_path=self.path, connector=self.connector, journal_factory=FakeJournal)
        self.addCleanup(g.close)
        return g
    def command(self, path='connection', **extra):
        return self.g.command('/api/'+path, {'game_id': self.g.game_id, 'request_id': uuid.uuid4().hex, **extra})
    def connect(self, **extra):
        return self.command(provider='jev', api_key=KEY, **extra)
    def test_missing_player_key_never_uses_owner_environment(self):
        with patch.dict('os.environ', {'TYPESAFE_API_KEY': 'owner-secret'}), patch('jev.load_key') as owner:
            self.assertEqual(self.command('start')[0], 428)
            owner.assert_not_called()
            self.connector.assert_not_called()
        self.assertEqual(self.g.phase, 'ready')
    def test_restart_uses_player_memory_and_budget_initialization(self):
        self.connect();self.command('start');self.command('pause')
        old=self.g.game_id
        self.assertEqual(self.command('restart')[0],200)
        self.assertEqual(self.g.phase,'running');self.assertNotEqual(old,self.g.game_id)
        self.assertIs(self.g.ai.cooperation_memory,self.g.round_memory)
        self.assertEqual(self.g.ai.calls,0)
        kinds=[kind for kind,_ in self.g.journal.rows]
        self.assertIn('memory_context',kinds);self.assertIn('release',kinds)
    def test_restart_without_credentials_preserves_paused_round(self):
        self.connect();self.command('start');self.command('pause')
        old=self.g.game_id;self.g.setting=None
        self.assertEqual(self.command('restart')[0],428)
        self.assertEqual(self.g.game_id,old);self.assertEqual(self.g.phase,'paused')

    def test_connection_is_memory_only_and_public_data_has_no_secret(self):
        self.assertEqual(self.connect()[0], 200)
        self.assertFalse(self.path.exists())
        self.assertNotIn(KEY, json.dumps(self.g.public_state()))
        self.assertNotIn(KEY, str(self.g.receipts))
        self.assertEqual(self.command('start')[0], 200)
        self.assertEqual(self.connector.call_args.args[1]['api_key'], KEY)
        self.assertNotIn(KEY, str(self.g.journal.rows))
    def test_remember_permissions_reload_and_clear(self):
        self.assertEqual(self.connect(remember=True)[0], 200)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        loaded=self.make()
        self.assertEqual(loaded.setting['api_key'], KEY)
        self.assertTrue(loaded.public_state()['connection']['remembered'])
        self.assertEqual(self.command(clear=True)[0], 200)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.command('start')[0], 428)
    def test_memory_selection_removes_previous_saved_key(self):
        self.connect(remember=True)
        self.connect(remember=False)
        self.assertFalse(self.path.exists())
    def test_failed_connection_is_sanitized_and_preserves_previous_setting(self):
        self.connect()
        self.client.ask.side_effect=RuntimeError('HTTP 401 '+KEY)
        status, body=self.command(provider='compatible',base_url='https://api.example.com/v1',model='test',api_key='other-test-key')
        self.assertEqual(status,502)
        self.assertNotIn(KEY,str(body))
        self.assertEqual(self.g.setting['api_key'],KEY)
        self.assertEqual(self.g.setting['provider'],'jev')
    def test_only_before_or_after_game_can_change_key(self):
        self.connect();self.command('start')
        self.assertEqual(self.command(clear=True)[0],409)
        self.command('pause')
        self.assertEqual(self.connect()[0],409)
    def test_probe_blocks_start_and_duplicate_receipts(self):
        self.g.connecting=True
        self.assertEqual(self.command('start')[0],409)
        self.g.connecting=False
        body={'game_id':self.g.game_id,'request_id':'same','provider':'jev','api_key':KEY}
        first=self.g.command('/api/connection',body)
        self.assertEqual(self.g.command('/api/connection',body),first)
        self.client.ask.assert_called_once()
    def test_invalid_settings_and_stale_game_never_call_provider(self):
        self.assertEqual(self.command(provider='wrong',api_key=KEY)[0],400)
        self.assertEqual(self.g.command('/api/connection',{'game_id':'old','request_id':'old'})[0],409)
        self.connector.assert_not_called()
    def test_compatible_age_and_canonical_endpoint(self):
        status,_=self.command(provider='compatible',base_url='https://api.example.com/v1/chat/completions',model='fast',api_key=KEY,remember=True)
        self.assertEqual(status,200)
        self.assertEqual(self.g.setting['base_url'],'https://api.example.com/v1')
        self.assertEqual(self.g.c['ai_max_response_age'],15)
        self.assertEqual(self.make().c['ai_max_response_age'],15)
    def test_reject_unsafe_urls(self):
        for url in ['http://api.example.com','https://127.0.0.1/v1','https://localhost','https://[::1]','https://user:pass@example.com','https://example.com?key=secret']:
            with self.subTest(url=url),self.assertRaises(ValueError):
                settings_from({'provider':'compatible','base_url':url,'model':'fast','api_key':KEY})


class CompatibleTests(unittest.TestCase):
    def setUp(self):
        self.client=CompatibleClient(load_config(),settings_from({'provider':'deepseek','api_key':KEY}))
        self.payload={'state':{'kitchen':{}},'questions':{'next_action':{'criteria':{'wait':'等待'}}}}
    def ask(self,content):
        response=io.BytesIO(json.dumps({'choices':[{'message':{'content':content}}],'usage':{'prompt_tokens':4,'completion_tokens':2}}).encode())
        opener=Mock();opener.open.return_value=response
        with patch('player_api.urllib.request.build_opener',return_value=opener):
            result=self.client.ask(self.payload)
        return result,opener.open.call_args.args[0]
    def test_request_uses_player_key_and_normalizes_real_action(self):
        result,req=self.ask('{"choice":"wait"}')
        self.assertEqual(result['choice'],'wait')
        self.assertEqual(result['usage']['input_tokens'],4)
        self.assertEqual(req.get_header('Authorization'),'Bearer '+KEY)
        self.assertEqual(req.full_url,'https://api.deepseek.com/chat/completions')
        body=json.loads(req.data)
        self.assertEqual(body['thinking'],{'type':'disabled'})
        self.assertEqual(body['model'],'deepseek-flash')
    def test_invalid_model_output_is_not_replaced_by_script(self):
        for content in ['{"choice":"invented"}','not json',None]:
            with self.subTest(content=content),self.assertRaises(RuntimeError):self.ask(content)
    def test_markdown_wrapped_json_is_accepted(self):
        self.assertEqual(self.ask('```json\n{"choice":"wait"}\n```')[0]['choice'],'wait')
    def test_redirect_does_not_forward_key(self):
        req=__import__('urllib.request',fromlist=['Request']).Request('https://example.com',headers={'Authorization':'Bearer '+KEY})
        with self.assertRaises(urllib.error.HTTPError):
            NoRedirect().redirect_request(req,None,302,'redirect',{},'https://other.example.com')

if __name__=='__main__':unittest.main()
