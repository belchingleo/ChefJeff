"""Explicit player preferences and corrections remain model input, not a policy."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
from player_api import PlayerGameSession
from spatial_kitchen import SpatialKitchen
from test_jev import NoKeyClient
from test_web import FakeJournal

class CommunicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.g=PlayerGameSession(credential_path=Path(self.tmp.name)/'settings.json',
            kitchen_factory=SpatialKitchen,journal_factory=FakeJournal,connector=lambda c,s:NoKeyClient(c))
        self.addCleanup(self.g.close)
        self.g.setting={'provider':'compatible','api_key':'secret-test','model':'secret-test'}
    def cmd(self,path,**data):return self.g.command('/api/'+path,{'game_id':self.g.game_id,'request_id':uuid.uuid4().hex,**data})
    def send(self,code,now):
        with patch('web_server.time.monotonic',return_value=now):return self.cmd('communicate',code=code)
    def test_all_choices_and_shared_cooldown_are_server_enforced(self):
        self.assertEqual(self.send('prep',100)[0],409);self.cmd('start')
        self.assertEqual(self.send('invalid',100)[0],400)
        for i,code in enumerate(('prep','cook','plate','deliver','wash','mistake')):
            self.assertEqual(self.send(code,100+5*i)[0],200)
            self.assertEqual(self.send('prep',104.999+5*i)[0],429)
        self.assertEqual(len(self.g.player_messages),6)
        self.assertEqual(self.g.communication_state()['preference'],'wash')
        self.assertEqual(self.g.player_messages[-1]['kind'],'correction')
    def test_message_is_non_interrupting_and_records_context(self):
        self.cmd('start');g=self.g
        g.k.start('jeff',next(a for a in g.k.actions('jeff') if a.key=='fetch'))
        before=deepcopy(g.k.snapshot());events=deepcopy(g.k.events);epoch=g.ai.epoch
        with patch.object(g.ai,'poll') as poll,patch.object(g.ai,'invalidate') as invalidate:
            self.assertEqual(self.send('mistake',100)[0],200)
            poll.assert_not_called();invalidate.assert_not_called()
        self.assertEqual(before,g.k.snapshot());self.assertEqual(events,g.k.events);self.assertEqual(epoch,g.ai.epoch)
        message=g.player_messages[0];self.assertEqual(message['context']['current_action'],'fetch')
        record=next(data for kind,data in g.journal.rows if kind=='player_message')
        self.assertEqual(record['state'],before)
    def test_next_request_contains_english_messages_and_delivery_is_logged_once(self):
        self.cmd('start');g=self.g;self.send('prep',100);self.send('cook',105);self.send('mistake',110)
        with patch('jev.time.monotonic',return_value=111):g.ai.poll()
        request=next(data for kind,data in g.journal.rows if kind=='ai_request')
        ctx=request['payload']['state']['player_communication']
        self.assertEqual(ctx['current_preference']['code'],'cook');self.assertEqual(len(ctx['recent_messages']),3)
        self.assertNotRegex(json.dumps(ctx,ensure_ascii=False),r'[\u3400-\u9fff]')
        self.assertTrue(all(m['first_request_id']==1 for m in g.player_messages))
        deadline=time.monotonic()+1
        while g.ai.q.empty() and time.monotonic()<deadline:time.sleep(.001)
        with patch('jev.time.monotonic',return_value=120):g.ai.poll()
        deliveries=[d for kind,d in g.journal.rows if kind=='player_message_delivery'];self.assertEqual(len(deliveries),3)
        # The original request remains immutable when a later preference arrives.
        self.send('wash',125);self.assertEqual(ctx['current_preference']['code'],'cook')
    def test_pause_dedup_end_export_and_reset(self):
        self.cmd('start');self.cmd('pause')
        body={'game_id':self.g.game_id,'request_id':'same','code':'plate'}
        first=self.g.command('/api/communicate',body)
        self.assertEqual(first[0],200);self.assertEqual(self.g.command('/api/communicate',body),first)
        self.assertEqual(len(self.g.player_messages),1);self.assertEqual(self.g.phase,'paused')
        self.assertEqual(self.cmd('communicate',code='wash',game_id='stale')[0],409)
        log=self.g.journal;self.cmd('end');self.assertEqual(self.send('wash',1000)[0],409)
        report=self.cmd('export-run')[1]['report'];self.assertEqual(report['rounds'][-1]['player_messages'],self.g.player_messages)
        self.assertNotIn('secret-test',json.dumps(report))
        self.assertEqual(next(d for kind,d in log.rows if kind=='end')['player_messages'],self.g.player_messages)
        self.cmd('reset');self.assertEqual(self.g.player_messages,[]);self.assertIsNone(self.g.last_player_message_at)
