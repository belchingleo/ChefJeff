import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from cooperation_memory import CooperationMemory, episode, sample_events, scope_for
from kitchen import load_config
from player_api import PlayerGameSession, CompatibleClient
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
from test_web import FakeJournal


class CooperationMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'.player-memory.json'
        self.setting = {'provider':'jev','base_url':'https://api.typesafe.ai/v1',
                        'model':'jev-latest','api_key':'test-secret-not-memory','remember':False}

    def test_legacy_actor_is_normalized_without_changing_provider_or_disk(self):
        scope=scope_for(self.setting)
        original={'version':1,'enabled':True,'scopes':{scope:[{
            'round_id':'old','model':'jev-latest','duration':1,'outcome':{},
            'events':[{'t':1,'kind':'action_done','actor':'jev','action':'wash'}]}]}}
        self.path.write_text(json.dumps(original))
        memory=CooperationMemory(self.path)
        episode=memory.context(scope)['episodes'][0]
        self.assertEqual(episode['events'][0]['actor'],'jeff')
        self.assertEqual(episode['model'],'jev-latest')
        self.assertEqual(json.loads(self.path.read_text()),original)

    def game(self):
        client = SpatialJevClient(load_config(), key=self.setting['api_key'])
        client.ask = Mock(return_value={'choice':'wait','confidence':.2,'probabilities':{},
                                       'model':'offline','usage':{},'latency':0})
        g = PlayerGameSession(credential_path=self.path.parent/'.player-api.json',
                              kitchen_factory=SpatialKitchen,connector=lambda *_:client,
                              journal_factory=FakeJournal)
        g.setting = self.setting.copy()
        self.addCleanup(g.close)
        return g

    def command(self,g,path,**extra):
        return g.command('/api/'+path,{'game_id':g.game_id,'request_id':uuid.uuid4().hex,**extra})

    def finish(self,g):
        g.k.emit('你完成动作：切菜',kind='action_done',actor='human',action='chop b1')
        g.k.emit('你抛出了食材',kind='thrown',actor='human',item='F1',target=(8,4))
        g.k.served=3;g.k.money=90;g.k.advance(.01)
        self.assertTrue(g.k.ended)
        g.phase='ended';g._finish()

    def test_finished_round_survives_reset_and_restart_without_credentials(self):
        g=self.game();self.assertEqual(self.command(g,'start')[0],200)
        self.finish(g)
        self.assertEqual(g.memory_state()['saved_rounds'],1)
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        self.assertNotIn(self.setting['api_key'],self.path.read_text())
        self.assertEqual(self.command(g,'reset')[0],200)
        self.assertEqual(self.command(g,'start')[0],200)
        self.assertEqual(len(g.ai.cooperation_memory['episodes']),1)
        restored=self.game()
        self.assertEqual(restored.memory_state()['saved_rounds'],1)

    def test_memory_is_in_actual_logged_request_for_model(self):
        g=self.game();self.command(g,'start');self.finish(g)
        self.command(g,'reset');self.command(g,'start')
        # Avoid a network/thread call while inspecting the real request assembly.
        with patch('jev.threading.Thread'):
            g.ai.poll()
        payload=next(data['payload'] for kind,data in g.journal.rows if kind=='ai_request')
        from model_language import english_data
        self.assertEqual(payload['state']['past_episodes'],english_data(g.round_memory))
        self.assertEqual(g.round_memory['episodes'][0]['events'][0]['message'],'你完成动作：切菜')
        self.assertEqual(payload['state']['past_episodes']['episodes'][0]['events'][1]['target'],[8,4])
        self.assertNotIn(self.setting['api_key'],json.dumps(payload))

    def test_disabled_neither_reads_nor_saves_current_round(self):
        g=self.game();self.command(g,'start');self.finish(g)
        self.command(g,'memory',enabled=False);self.command(g,'reset');self.command(g,'start')
        self.assertFalse(g.ai.cooperation_memory['enabled'])
        self.assertEqual(g.ai.cooperation_memory['episodes'],[])
        self.finish(g)
        self.assertEqual(g.memory_state()['saved_rounds'],1)
        self.assertFalse(self.game().memory_state()['enabled'])

    def test_clear_removes_all_scopes_but_keeps_settings_and_is_idempotent(self):
        g=self.game();self.command(g,'start');self.finish(g)
        body={'game_id':g.game_id,'request_id':'clear-once','clear':True}
        first=g.command('/api/memory',body)
        self.assertEqual(first[0],200)
        self.assertEqual(g.command('/api/memory',body),first)
        self.assertEqual(g.memory.data['scopes'],{})
        self.assertEqual(g.setting['api_key'],self.setting['api_key'])
        self.assertEqual(CooperationMemory(self.path).data['scopes'],{})

    def test_new_model_isolated_key_rotation_same_scope(self):
        scope=scope_for(self.setting)
        self.assertEqual(scope,scope_for({**self.setting,'api_key':'rotated-secret'}))
        self.assertNotEqual(scope,scope_for({**self.setting,'model':'other-model'}))
        g=self.game();self.command(g,'start');self.finish(g)
        g.setting['model']='other-model'
        self.assertEqual(g.memory_state()['saved_rounds'],0)

    def test_aborted_and_unstarted_games_do_not_save(self):
        g=self.game();g.close();self.assertFalse(self.path.exists())
        g=self.game();self.command(g,'start');self.command(g,'pause');self.command(g,'reset')
        self.assertEqual(g.memory_state()['saved_rounds'],0)
        self.assertFalse(self.path.exists())

    def test_immutable_during_play_and_old_game_rejected(self):
        g=self.game();self.command(g,'start')
        self.assertEqual(self.command(g,'memory',enabled=False)[0],409)
        self.command(g,'pause')
        self.assertEqual(self.command(g,'memory',clear=True)[0],409)
        self.assertEqual(g.command('/api/memory',{'game_id':'old','request_id':'x','clear':True})[0],409)

    def test_retention_and_sampling_are_bounded_deterministic(self):
        store=CooperationMemory(self.path);k=SpatialKitchen(load_config())
        for i in range(100):
            k.events.append({'t':i,'kind':'action_done','actor':'human' if i%2 else 'jeff',
                             'action':'chop b1','message':'完成切菜'})
        samples,count=sample_events(k.events)
        self.assertEqual(len(samples),18);self.assertEqual(count,100)
        self.assertEqual(sample_events(k.events)[0],samples)
        for i in range(5):store.remember('model',episode(k,str(i),'offline'))
        self.assertEqual([r['round_id'] for r in store.context('model')['episodes']],['2','3','4'])
        context=store.context('model');context['episodes'].clear()
        self.assertEqual(len(store.context('model')['episodes']),3)

    def test_bad_file_disables_memory_instead_of_breaking_game(self):
        self.path.write_text('{broken')
        g=self.game();self.assertFalse(g.memory_state()['enabled'])
        self.assertIsNotNone(g.memory_state()['error'])
        self.assertEqual(self.command(g,'memory',clear=True)[0],200)
        self.assertIsNone(g.memory_state()['error'])

    def test_write_failure_preserves_previous_setting(self):
        g=self.game()
        with patch('cooperation_memory.os.replace',side_effect=OSError()):
            self.assertEqual(self.command(g,'memory',enabled=False)[0],500)
        self.assertTrue(g.memory.data['enabled'])
        self.assertEqual(list(self.path.parent.glob('.player-memory-*')),[])

    def test_compatible_adapter_forwards_same_memory_without_extra_call(self):
        setting={**self.setting,'provider':'compatible','base_url':'https://example.com/v1'}
        c=CompatibleClient(load_config(),setting);k=SpatialKitchen(load_config())
        payload=c.payload(k.snapshot(),k.actions('jeff'))
        payload['state']['past_episodes']={'enabled':True,'episodes':[{'duration':10}]}
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock()
        response.read.return_value=json.dumps({'choices':[{'message':{'content':'{"choice":"wait","sprint":false}'}}]}).encode()
        opener=Mock();opener.open.return_value=response
        with patch('player_api.urllib.request.build_opener',return_value=opener):c.ask(payload)
        body=json.loads(opener.open.call_args.args[0].data)
        sent=json.loads(body['messages'][1]['content'])
        self.assertEqual(sent['state']['past_episodes'],payload['state']['past_episodes'])
        self.assertEqual(opener.open.call_count,1)
