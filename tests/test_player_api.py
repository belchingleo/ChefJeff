import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
import uuid

from kitchen import load_config
from player_api import PlayerGameSession, CompatibleClient, DecisionClient, NoRedirect, settings_from, create_client
from kitchen import ROOT
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
    def test_zhipu_preset_turns_thinking_off_and_asks_for_json(self):
        setting=settings_from({'provider':'zhipu','api_key':KEY})
        self.assertEqual((setting['base_url'],setting['model']),('https://open.bigmodel.cn/api/paas/v4','glm-4.7-flash'))
        self.client=CompatibleClient(load_config(),setting)
        _,req=self.ask('{"choice":"wait"}')
        self.assertEqual(req.full_url,'https://open.bigmodel.cn/api/paas/v4/chat/completions')
        body=json.loads(req.data)
        self.assertEqual((body['thinking'],body['response_format']),({'type':'disabled'},{'type':'json_object'}))
    def test_other_compatible_services_get_no_vendor_fields(self):
        self.client=CompatibleClient(load_config(),settings_from({'provider':'compatible','base_url':'https://api.example.com/v1','model':'m','api_key':KEY}))
        body=json.loads(self.ask('{"choice":"wait"}')[1].data)
        self.assertNotIn('thinking',body);self.assertNotIn('response_format',body)
    def test_gemini_uses_the_open_35_model_with_minimal_reasoning(self):
        self.client=CompatibleClient(load_config(),settings_from({'provider':'gemini','api_key':KEY}))
        _,req=self.ask('{"choice":"wait"}')
        body=json.loads(req.data)
        self.assertEqual(req.full_url,'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions')
        self.assertEqual((body['model'],body['reasoning_effort']),('gemini-3.5-flash-lite','minimal'))
    def test_cloudflare_needs_the_account_id_and_gemma_alone_turns_thinking_off(self):
        account='0123456789abcdef0123456789abcdef'
        for bad in (None,'',account.upper(),account[:-1],'../'+account):
            with self.subTest(account=bad),self.assertRaises(ValueError):
                settings_from({'provider':'cloudflare','api_key':KEY,**({'account_id':bad} if bad is not None else {})})
        for model,thinking in (('@cf/google/gemma-4-26b-a4b-it',True),('@cf/meta/llama-3.1-8b-instruct-fp8',False)):
            setting=settings_from({'provider':'cloudflare','api_key':KEY,'account_id':account,'model':model})
            self.assertEqual(setting['account_id'],account)
            self.assertEqual(settings_from(json.loads(json.dumps(setting))),setting)  # a remembered setting reloads unchanged
            self.client=CompatibleClient(load_config(),setting)
            _,req=self.ask('{"choice":"wait"}')
            self.assertEqual(req.full_url,f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions')
            body=json.loads(req.data)
            self.assertEqual((body['model'],body['response_format']),(model,{'type':'json_object'}))
            self.assertEqual('chat_template_kwargs' in body,thinking)
    def test_missing_sprint_means_no_sprint_and_is_logged(self):
        self.payload['questions']['sprint']={}
        result,_=self.ask('{"choice":"wait"}')
        self.assertEqual((result['choice'],result['sprint'],result['sprint_missing']),('wait',False,True))
        self.assertNotIn('sprint_missing',self.ask('{"choice":"wait","sprint":true}')[0])
        with self.assertRaises(RuntimeError):self.ask('{"choice":"wait","sprint":"yes"}')
    def test_every_listed_service_validates_with_its_own_address_and_vendor_fields(self):
        catalog=json.loads((ROOT/'model-providers.json').read_text())
        groups={g['id'] for g in catalog['groups']}
        for preset in catalog['providers']:
            with self.subTest(provider=preset['id']):
                self.assertIn(preset['group'],groups)
                if preset.get('disabled'):
                    with self.assertRaises(ValueError):settings_from({'provider':preset['id'],'api_key':KEY})
                    continue
                body={'provider':preset['id'],'api_key':KEY}
                if preset.get('custom'):body.update(base_url='https://api.example.com/v1',model='m')
                elif not preset.get('model'):body['model']='vendor/model'
                if preset.get('account_id'):body['account_id']='0'*32
                setting=settings_from(body)
                self.assertEqual(setting['base_url'],'https://api.example.com/v1' if preset.get('custom') else
                                 (preset.get('endpoint') or preset['base_url']).replace('{account_id}','0'*32))
                client=create_client(load_config(),setting)
                self.assertIsInstance(client,DecisionClient if preset['group']=='decision' and preset['id']!='jev' else (CompatibleClient if preset['group']=='chat' else object))
    def test_decision_service_posts_state_and_questions_to_its_endpoint(self):
        setting=settings_from({'provider':'openrouter-decision','api_key':KEY})
        client=DecisionClient(load_config(),setting)
        answer={'answers':{'next_action':{'type':'choice','choice':'wait','probabilities':{'wait':.9}},'sprint':{'type':'choice','choice':'no'}},
                'model':'microsoft/microsoft-decision-1','usage':{'input_tokens':5,'output_tokens':0}}
        payload={'model':setting['model'],'state':{'kitchen':{}},'questions':{'next_action':{'type':'choice','criteria':{'wait':'等待'}},'sprint':{'type':'choice','criteria':{'yes':'','no':''}}}}
        with patch('jev.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(answer).encode())) as opened:
            result=client.ask(payload)
        req=opened.call_args.args[0]
        self.assertEqual(req.full_url,'https://openrouter.ai/api/alpha/decisions')
        self.assertEqual(set(json.loads(req.data)),{'model','state','questions'})
        self.assertEqual(json.loads(req.data)['model'],'microsoft/microsoft-decision-1')
        self.assertEqual((result['choice'],result['sprint']),('wait',False))
    def test_refused_request_reports_status_and_provider_message_without_the_key(self):
        client=DecisionClient(load_config(),settings_from({'provider':'openrouter-decision','api_key':KEY}))
        body=json.dumps({'error':{'message':f'questions.next_action: too many options for key {KEY}'}}).encode()
        error=urllib.error.HTTPError('https://openrouter.ai/api/alpha/decisions',400,'Bad Request',{},io.BytesIO(body))
        with patch('jev.urllib.request.urlopen',side_effect=error),self.assertRaises(RuntimeError) as raised:
            client.ask({'model':'m','state':{},'questions':{'next_action':{'type':'choice','criteria':{'a':'','b':''}}}})
        text=str(raised.exception)
        self.assertIn('HTTP 400',text);self.assertIn('too many options',text);self.assertNotIn(KEY,text);self.assertIn('***',text)
    def test_startlux_connection_and_gameplay_disable_thinking(self):
        provider='startlux'
        extra={'allow_none':False,'think_mode':'never'}
        from spatial_kitchen import SpatialKitchen
        setting=settings_from({'provider':provider,'api_key':KEY})
        client=create_client(load_config(),setting)
        self.assertIsInstance(client,DecisionClient)
        self.assertEqual(setting['model'],'startlux-decision-27b-autothink')
        self.assertEqual(settings_from({'provider':provider,'api_key':KEY,'model':'another-model'})['model'],'another-model')
        answer={'answers':{'next_action':{'type':'choice','choice':'ready'},'sprint':{'type':'choice','choice':'no'}},
                'usage':{'input_tokens':5,'output_tokens':7}}
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        probe=PlayerGameSession(credential_path=Path(tmp.name)/'.player-api.json',
                                connector=create_client,journal_factory=FakeJournal)
        self.addCleanup(probe.close)
        with patch('jev.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(answer).encode())) as opened:
            status,_=probe.command('/api/connection',{'game_id':probe.game_id,'request_id':uuid.uuid4().hex,
                                                     'provider':provider,'api_key':KEY})
        self.assertEqual(status,200)
        req=opened.call_args.args[0]
        self.assertEqual((req.full_url,req.method),('https://api.bamboonode.dev/v1/decisions','POST'))
        self.assertEqual(req.get_header('Authorization'),'Bearer '+KEY)
        sent=json.loads(req.data)
        self.assertEqual(set(sent),{'model','state','questions'}|set(extra))
        self.assertEqual({k:sent[k] for k in extra},extra)
        self.assertEqual(sent['model'],'startlux-decision-27b-autothink')
        self.assertEqual(sent['questions']['next_action']['type'],'choice')
        self.assertEqual(set(sent['questions']['next_action']['criteria']),{'ready','wait'})
        kitchen=SpatialKitchen(load_config())
        payload=client.payload(kitchen.snapshot(),kitchen.actions('jeff'))
        answer['answers']['next_action']['choice']=next(iter(payload['questions']['next_action']['criteria']))
        with patch('jev.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(answer).encode())) as opened:
            result=client.ask(payload)
        sent=json.loads(opened.call_args.args[0].data)
        self.assertEqual(set(sent),{'model','state','questions'}|set(extra))
        self.assertEqual({k:sent[k] for k in extra},extra)
        self.assertEqual(sent['model'],'startlux-decision-27b-autothink')
        self.assertIn('kitchen',sent['state'])
        self.assertIn('sprint',sent['questions'])
        self.assertEqual((result['choice'],result['sprint'],result['usage']),
                         (answer['answers']['next_action']['choice'],False,answer['usage']))
        self.assertNotIn('allow_none',payload,'Applying preset fields must not mutate the shared payload')
        self.assertNotIn('think_mode',payload)
        self.assertEqual((probe.c['ai_timeout_seconds'],probe.c['ai_max_response_age']),(8,6))
        for question in ('next_action','sprint'):
            with self.subTest(null_answer=question):
                invalid=json.loads(json.dumps(answer))
                invalid['answers'][question]['choice']=None
                with patch('jev.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(invalid).encode())):
                    with self.assertRaises(RuntimeError):client.ask(payload)
    def test_listed_service_names_and_notes_have_english(self):
        catalog=json.loads((ROOT/'model-providers.json').read_text())
        messages=json.loads((ROOT/'cocos-kitchen/i18n.json').read_text())['messages']
        for text in [g['label'] for g in catalog['groups']]+[p[k] for p in catalog['providers'] for k in ('label','note') if k in p]:
            if any('\u3400'<=c<='\u9fff' for c in text):self.assertIn(text,messages)
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
