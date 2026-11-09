import time
import unittest
from unittest.mock import patch
from kitchen import Kitchen, Food, load_config
from jev import DecisionLoop, JevClient


class NoKeyClient:
    def __init__(self,c,reply='wait',error=False):
        self.base=JevClient(c,key='unit-test-not-a-real-key')
        self.reply=reply
        self.error=error
        self.calls=0
    def payload(self,state,actions):
        return self.base.payload(state,actions)
    def ask(self,payload):
        self.calls+=1
        if self.error:
            raise RuntimeError('TypeSafe HTTP 429')
        choice=self.reply
        if choice not in payload['questions']['next_action']['criteria']:
            choice=next(iter(payload['questions']['next_action']['criteria']))
        return {'choice':choice,'confidence':.8,'probabilities':{choice:1},'model':'test-only','latency':.1,'usage':{'input_tokens':10,'output_tokens':1}}


class SchedulerTest(unittest.TestCase):
    def make(self,reply='wait',error=False):
        c=load_config()
        k=Kitchen(c)
        client=NoKeyClient(c,reply,error)
        records=[]
        ai=DecisionLoop(k,client,lambda kind,data:records.append((kind,data)),lambda text:None)
        return k,client,ai,records

    def ready(self,ai):
        end=time.monotonic()+1
        while ai.q.empty() and time.monotonic()<end:
            time.sleep(.001)
        self.assertFalse(ai.q.empty())

    def test_minimum_interval_event_coalescing_and_periodic_refresh(self):
        k,client,ai,records=self.make()
        with patch('jev.time.monotonic',return_value=100):
            ai.poll()
        self.ready(ai)
        with patch('jev.time.monotonic',return_value=100.1):
            ai.poll()
        k.emit('first event')
        k.emit('second event')
        with patch('jev.time.monotonic',return_value=101):
            ai.poll()
        self.assertEqual(ai.calls,1)
        with patch('jev.time.monotonic',return_value=102):
            ai.poll()
        self.ready(ai)
        with patch('jev.time.monotonic',return_value=102.1):
            ai.poll()
        request=[d for kind,d in records if kind=='ai_request'][-1]
        self.assertIn('first event',request['triggers'])
        self.assertIn('second event',request['triggers'])
        with patch('jev.time.monotonic',return_value=105):
            ai.poll()
        self.assertEqual(ai.calls,2)
        with patch('jev.time.monotonic',return_value=106):
            ai.poll()
        self.assertEqual(ai.calls,3)
        self.ready(ai)

    def finish_step(self,k):
        while k.chefs['jeff'].job:
            k.advance(.05)

    def test_a_finished_step_asks_at_once_instead_of_waiting_out_the_interval(self):
        for on,calls in ((True,2),(False,1)):
            with self.subTest(ai_ask_on_step_end=on):
                k,client,ai,records=self.make('fetch beef')
                ai.ask_on_step_end=on
                with patch('jev.time.monotonic',return_value=100):ai.poll()
                self.ready(ai)
                with patch('jev.time.monotonic',return_value=100.1):ai.poll()
                self.assertIsNotNone(k.chefs['jeff'].job)
                self.finish_step(k)
                # Half a second after the last request, well inside ai_min_interval.
                with patch('jev.time.monotonic',return_value=100.5):ai.poll()
                self.assertEqual(ai.calls,calls)
                if on:
                    self.ready(ai)
                    with patch('jev.time.monotonic',return_value=100.6):ai.poll()
                    self.assertFalse(ai.step_ended)
                    self.assertTrue([d for kind,d in records if kind=='ai_response'][-1]['fresh'])

    def test_no_request_the_current_step_will_outlast(self):
        k,client,ai,records=self.make('fetch beef')
        with patch('jev.time.monotonic',return_value=100):ai.poll()
        self.ready(ai)
        with patch('jev.time.monotonic',return_value=100.1):ai.poll()
        job=k.chefs['jeff'].job
        ai.reply_times=[job.travel+job.work+1]      # replies come after this step will have ended
        k.emit('the kitchen changed')
        with patch('jev.time.monotonic',return_value=103):ai.poll()
        self.assertEqual(ai.calls,1)
        self.finish_step(k)
        with patch('jev.time.monotonic',return_value=103.1):ai.poll()
        self.assertEqual(ai.calls,2)
        self.ready(ai)
        # A step that outlasts the reply time is still asked about while it runs.
        k,client,ai,records=self.make('fetch beef')
        with patch('jev.time.monotonic',return_value=100):ai.poll()
        self.ready(ai)
        with patch('jev.time.monotonic',return_value=100.1):ai.poll()
        ai.reply_times=[.01]
        k.emit('the kitchen changed')
        with patch('jev.time.monotonic',return_value=103):ai.poll()
        self.assertEqual(ai.calls,2)
        self.ready(ai)

    def test_the_step_left_is_counted_in_wall_seconds_at_the_round_speed(self):
        from types import SimpleNamespace
        k,client,ai,records=self.make()
        step=SimpleNamespace(travel=.6,work=.4)    # one game second left
        self.assertFalse(ai.outlasts_reply(step))  # no reply yet: nothing to compare with
        ai.reply_times=[1.4,1.5,1.6]
        self.assertTrue(ai.outlasts_reply(step))
        ai.game_speed=.5                           # two wall seconds left
        self.assertFalse(ai.outlasts_reply(step))

    def test_the_switch_is_on_by_config_and_can_be_turned_off(self):
        import json, tempfile
        from pathlib import Path
        from types import SimpleNamespace
        c=load_config()
        self.assertIs(c['ai_ask_on_step_end'],True)
        self.assertTrue(DecisionLoop(Kitchen(c),NoKeyClient(c),lambda *_:None,lambda *_:None).ask_on_step_end)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            path.write_text(json.dumps({**c,'ai_ask_on_step_end':False}))
            off=load_config(path)
            path.write_text(json.dumps({**c,'ai_ask_on_step_end':1}))
            with self.assertRaises(ValueError):load_config(path)
            path.write_text(json.dumps({**c,'ai_min_interval':True}))
            with self.assertRaises(ValueError):load_config(path)
        self.assertFalse(DecisionLoop(Kitchen(off),NoKeyClient(off),lambda *_:None,lambda *_:None).ask_on_step_end)
        # A configuration without the key (older settings) keeps the old timing.
        self.assertFalse(DecisionLoop(SimpleNamespace(c={}),None,lambda *_:None,lambda *_:None).ask_on_step_end)

    def test_no_overlapping_requests(self):
        k,client,ai,records=self.make()
        ai.inflight=True
        with patch('jev.time.monotonic',return_value=1000):
            ai.poll()
        self.assertEqual(ai.calls,0)

    def test_pause_discards_pending_choice(self):
        k,client,ai,records=self.make('fetch beef')
        ai.poll()
        self.ready(ai)
        ai.invalidate()
        ai.poll(enabled=False)
        self.assertIsNone(k.chefs['jeff'].job)
        self.assertFalse([d for kind,d in records if kind=='ai_response'][-1]['applied'])

    def test_old_response_cannot_interrupt_a_new_job(self):
        k,client,ai,records=self.make('fetch beef')
        ai.poll()
        self.ready(ai)
        k.command('jeff','go b1')
        job=k.chefs['jeff'].job.id
        ai.poll()
        self.assertEqual(k.chefs['jeff'].job.id,job)
        self.assertFalse([d for kind,d in records if kind=='ai_response'][-1]['applied'])

    def test_expired_response_rejected(self):
        k,client,ai,records=self.make('fetch beef')
        with patch('jev.time.monotonic',return_value=100):
            ai.poll()
        self.ready(ai)
        with patch('jev.time.monotonic',return_value=107):
            ai.poll(enabled=False)
        self.assertIsNone(k.chefs['jeff'].job)

    def test_api_failure_does_not_use_fallback_policy(self):
        k,client,ai,records=self.make(error=True)
        ai.poll()
        self.ready(ai)
        ai.poll()
        self.assertIsNone(k.chefs['jeff'].job)
        self.assertEqual(ai.failures,1)
        self.assertGreater(ai.next_allowed,time.monotonic())
        self.assertTrue(any(kind=='ai_error' for kind,d in records))

    def test_busy_chef_can_choose_to_continue_or_change(self):
        k,client,ai,records=self.make('continue')
        k.command('jeff','fetch beef')
        job=k.chefs['jeff'].job.id
        ai.poll()
        self.ready(ai)
        ai.poll()
        self.assertEqual(k.chefs['jeff'].job.id,job)
        options=[d for kind,d in records if kind=='ai_request'][0]['payload']['questions']['next_action']['criteria']
        self.assertIn('continue',options)
        self.assertIn('stop',options)
        self.assertIn('go b1',options)

    def test_recent_results_are_sent_on_next_request_without_growing_forever(self):
        k,client,ai,records=self.make('fetch beef')
        with patch('jev.time.monotonic',return_value=100):ai.poll()
        self.ready(ai)
        with patch('jev.time.monotonic',return_value=100.1):ai.poll()
        k.advance(4)
        for i in range(25):k.emit('实际结果 '+str(i),kind='arrival_conflict',actor='jeff')
        with patch('jev.time.monotonic',return_value=102):ai.poll()
        self.ready(ai)
        payload=[d for kind,d in records if kind=='ai_request'][-1]['payload']
        self.assertEqual(payload['state']['recent_decisions'][-1]['choice'],'fetch beef')
        self.assertTrue(payload['state']['recent_decisions'][-1]['accepted'])
        self.assertEqual(len(payload['state']['recent_events']),20)
        self.assertEqual(payload['state']['recent_events'][-1]['message'],'实际结果 24')
        self.assertIn('go b1',payload['questions']['next_action']['criteria'])
        self.assertEqual(set(payload['questions']['next_action']['criteria']),{a.key for a in k.actions('jeff')})

    def test_menu_ids_never_shift(self):
        k,client,ai,records=self.make()
        before=k.menu_numbers()
        k.chefs['human'].hand=Food('food')
        self.assertEqual(before,k.menu_numbers())

    def test_jev_receives_ground_state_and_can_choose_pickup(self):
        k,client,ai,records=self.make('pickup food')
        k.chefs['human'].hand=Food('food','ready',6,12)
        k.command('human','drop')
        k.advance(1)
        ai.poll()
        self.ready(ai)
        ai.poll()
        payload=[d for kind,d in records if kind=='ai_request'][0]['payload']
        self.assertIn('pickup food',payload['questions']['next_action']['criteria'])
        self.assertIn('food',str(payload['state']))
        self.assertEqual(k.chefs['jeff'].job.action.key,'pickup food')
        k.advance(4)
        self.assertEqual(k.chefs['jeff'].hand.id,'food')


if __name__=='__main__':
    unittest.main()
