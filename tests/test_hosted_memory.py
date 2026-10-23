"""Browser-owned memory: authoritative summaries, strict relay input and kitchen isolation."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock, patch

from cooperation_memory import (memory_context, portable_episode, validate_browser_context,
                                DESCRIPTION, PAST_EPISODES_RULE, CONTEXT_CHARACTERS)
from hosted_server import HostedSession
from hosted_jev import JevForwarder, CONSENT_VERSION

ROOT=Path(__file__).resolve().parents[1]
KEY='memory-test-jev-key-not-a-real-secret'


class HostedMemoryTests(unittest.TestCase):
    def game(self):
        game=HostedSession();self.addCleanup(game.close)
        return game

    def start(self,game):
        game.connected=True
        self.assertEqual(game._command('/api/start',{})[0],200)

    def finish(self,game):
        game.k.advance(game.k.rules.round_limit-game.k.time+1)
        game.phase='ended';game._finish()

    def test_summaries_are_engine_facts_exposed_only_by_the_own_kitchen(self):
        game=self.game();other=self.game();self.start(game)
        self.assertIsNone(game.public_state()['memory']['episode'])
        game.k.command('human','fetch');game.k.advance(15)
        game._command('/api/communicate',{'code':'prep'})
        game.k.emit(KEY,kind='caught',actor='world',action='debug '+KEY)
        self.finish(game)
        memory=game.public_state()['memory'];record=memory['episode']
        self.assertTrue(memory['enabled']);self.assertTrue(memory['editable'])
        self.assertEqual(record['work']['human']['fetch'],1)
        self.assertEqual(record['communication']['last_preference'],'prep')
        self.assertNotIn(KEY,json.dumps(memory))
        self.assertNotIn('model',record);self.assertNotIn('message',record['events'][0])
        self.assertIsNone(other.public_state()['memory']['episode'])
        self.assertEqual(game.public_state()['memory']['episode'],record)

    def test_abort_has_no_episode_and_every_start_has_neutral_memory_rules(self):
        game=self.game();self.start(game)
        self.assertFalse(game.ai.cooperation_memory['enabled'])
        with patch('jev.threading.Thread'):
            game.ai.poll()
        request=next(r for r in game.session_log.records if r['type']=='ai_request')
        self.assertIsNotNone(request)
        game._command('/api/end',{})
        self.assertIsNone(game.public_state()['memory']['episode'])

    def test_browser_and_server_share_the_portable_contract(self):
        fixture=json.loads((ROOT/'tests/fixtures/cooperation-memory-v2.json').read_text())
        self.assertEqual(fixture['memory']['description'],DESCRIPTION)
        self.assertEqual(fixture['memory']['max_characters'],CONTEXT_CHARACTERS)
        context=memory_context(True,[fixture['episode']])
        self.assertEqual(validate_browser_context(context,'level-1'),context)

    def forward(self,context):
        game=self.game();self.start(game)
        payload=game.relay.payload(game.k.snapshot(),game.k.actions('jeff'))
        game.relay.pending={'id':'pending-memory-task','payload':payload,'event':threading.Event(),
                            'result':None,'sent':time.monotonic()}
        forwarder=JevForwarder();forwarder.send=Mock(return_value={'choice':'wait','sprint':False,'usage':{}})
        body={'game_id':game.game_id,'id':'pending-memory-task','test':False,'consent':True,
              'consent_version':CONSENT_VERSION,'api_key':KEY,'memory':context}
        result=forwarder.handle(game,body)
        return result,forwarder.send,game,payload

    def context(self):
        fixture=json.loads((ROOT/'tests/fixtures/cooperation-memory-v2.json').read_text())
        return memory_context(True,[fixture['episode']])

    def test_jev_receives_the_validated_memory_without_mutating_or_retaining_it(self):
        context=self.context();before=deepcopy(context)
        (status,_),send,game,original=self.forward(context)
        self.assertEqual(status,200);send.assert_called_once()
        forwarded=send.call_args.args[1]
        self.assertEqual(forwarded['state']['past_episodes'],context)
        self.assertEqual(forwarded['state']['rules']['past_episodes'],PAST_EPISODES_RULE)
        self.assertNotIn('past_episodes',original['state'])
        self.assertEqual(context,before)
        self.assertNotIn(KEY,str(game.jev_receipts));self.assertNotIn(KEY,str(game.public_state()))
        self.assertEqual(game.public_state()['memory']['saved_rounds'],0,'Persistent history belongs to the browser')

    def test_wrong_level_unknown_fields_credentials_and_unbounded_values_are_rejected(self):
        cases=[]
        context=self.context();context['episodes'][0]['level_id']='level-2';cases.append(context)
        context=self.context();context['episodes'][0]['api_key']=KEY;cases.append(context)
        context=self.context();context['episodes'][0]['events'][0]['message']=KEY;cases.append(context)
        context=self.context();context['episodes'][0]['work']['human']['fetch']=True;cases.append(context)
        context=self.context();context['episodes'][0]['duration']=float('nan');cases.append(context)
        context=self.context();context['description']=KEY;cases.append(context)
        context=self.context();context['episodes']*=4;cases.append(context)
        for context in cases:
            with self.subTest(context=context):
                (status,body),send,game,_=self.forward(context)
                self.assertEqual(status,400);send.assert_not_called()
                self.assertNotIn(KEY,str(body));self.assertNotIn(KEY,str(game.jev_receipts))


if __name__=='__main__':unittest.main()
