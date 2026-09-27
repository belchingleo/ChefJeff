import json
import time
import unittest
from unittest.mock import patch
from kitchen import Food, load_config
from web_server import GameSession


class FakeJournal:
    def __init__(self, name):
        self.rows=[]
        self.closed=False
    def __call__(self,kind,data):
        assert not self.closed
        self.rows.append((kind,data))
    def close(self):
        self.closed=True


class Client:
    def __init__(self,c): pass
    def payload(self,state,actions):return {'state':state}
    def ask(self,payload):raise RuntimeError('test-only')


class WebSessionTests(unittest.TestCase):
    def make(self):
        g=GameSession(client_factory=Client,journal_factory=FakeJournal)
        self.addCleanup(g.close)
        return g
    def command(self,g,path,**extra):
        return g.command('/api/'+path,{'game_id':g.game_id,'request_id':str(time.monotonic_ns()),**extra})
    def start(self,g,speed=.75):
        self.assertEqual(self.command(g,'start',speed=speed)[0],200)
    def act(self,g,key):
        a=next(a for a in g.k.actions('human') if a.key==key)
        return self.command(g,'action',action=a.key,expected=list(a.expected))
    def test_no_clock_or_ai_before_start(self):
        g=self.make();g.tick(g.last_tick+10)
        self.assertEqual(g.k.time,0)
        self.assertIsNone(g.ai)
    def test_slow_speed_is_explicit_and_scales_kitchen_only(self):
        g=self.make();self.start(g,.5)
        with patch.object(g.ai,'poll'):
            g.tick(g.last_tick+2)
        self.assertAlmostEqual(g.k.time,1)
        self.assertEqual(g.public_state()['speed'],.5)
    def test_pause_blocks_actions_and_clock(self):
        g=self.make();self.start(g)
        self.act(g,'fetch')
        self.command(g,'pause')
        old=g.k.time
        with patch.object(g.ai,'poll'):
            g.tick(g.last_tick+5)
        self.assertEqual(g.k.time,old)
        self.assertEqual(self.act(g,'stop')[0],409)
    def test_restart_runs_new_round_preserving_speed_and_closing_old_journal(self):
        g=self.make();self.start(g,speed=.5);old=g.game_id;old_ai=g.ai;old_log=g.journal
        self.command(g,'pause')
        self.assertEqual(self.command(g,'restart')[0],200)
        self.assertEqual(g.phase,'running');self.assertNotEqual(g.game_id,old)
        self.assertEqual(g.speed,.5);self.assertEqual(g.k.time,0)
        self.assertTrue(old_ai.closed);self.assertTrue(old_log.closed)
        self.assertIsNot(g.ai,old_ai)
        self.assertEqual(self.command(g,'restart')[0],409)
    def test_restart_rejects_ready_round(self):
        g=self.make();self.assertEqual(self.command(g,'restart')[0],409)
        self.assertEqual(g.phase,'ready')

    def test_end_running_or_paused_round_stops_clock_ai_and_closes_log_once(self):
        for paused in (False,True):
            g=self.make();self.start(g);self.act(g,'fetch')
            if paused:self.command(g,'pause')
            log=g.journal;ai=g.ai;t=g.k.time
            self.assertEqual(self.command(g,'end')[0],200)
            self.assertEqual(g.phase,'ended');self.assertTrue(g.k.aborted);self.assertTrue(g.k.ended)
            self.assertTrue(ai.closed);self.assertTrue(log.closed)
            self.assertTrue(all(c.job is None for c in g.k.chefs.values()))
            self.assertEqual(g.k.time_bonus,0);self.assertFalse(g.public_state()['won'])
            g.tick(g.last_tick+5);self.assertEqual(g.k.time,t)
            self.assertEqual(self.command(g,'resume')[0],409)
            self.assertEqual(self.command(g,'end')[0],200)
            ends=[v for key,v in log.rows if key=='end'];self.assertEqual(len(ends),1);self.assertTrue(ends[0]['aborted'])
            self.assertEqual(self.command(g,'reset')[0],200);self.assertFalse(g.k.aborted)

    def test_end_rejects_ready_and_never_awards_completion_bonus(self):
        g=self.make();self.assertEqual(self.command(g,'end')[0],409)
        self.start(g);g.k.served=g.c['target_served'];g.k.money=g.c['target_money']
        self.assertEqual(self.command(g,'end')[0],200)
        self.assertFalse(g.public_state()['won']);self.assertEqual(g.k.time_bonus,0)

    def test_reset_invalidates_old_clicks(self):
        g=self.make();self.start(g)
        old=g.game_id
        self.command(g,'pause');self.command(g,'reset')
        result=g.command('/api/start',{'game_id':old,'request_id':'old-click'})
        self.assertEqual(result[0],409)
        self.assertEqual(g.phase,'ready')
    def test_repeated_click_id_cannot_restart_action(self):
        g=self.make();self.start(g)
        a=next(a for a in g.k.actions('human') if a.key=='fetch')
        body={'game_id':g.game_id,'request_id':'double-click','action':a.key,'expected':list(a.expected)}
        first=g.command('/api/action',body)
        job=g.k.chefs['human'].job.id
        self.assertEqual(g.command('/api/action',body),first)
        self.assertEqual(g.k.chefs['human'].job.id,job)
    def test_stale_food_selection_rejected(self):
        g=self.make();self.start(g)
        g.k.stations['b1'].food=Food('old','chopped',6)
        a=next(a for a in g.k.actions('human') if a.key=='take b1')
        g.k.stations['b1'].food=Food('new','chopped',6)
        result=self.command(g,'action',action=a.key,expected=list(a.expected))
        self.assertEqual(result[0],409)
        self.assertIsNone(g.k.chefs['human'].job)
    def test_disconnected_page_autopauses(self):
        g=self.make();self.start(g)
        with patch.object(g.ai,'poll'):
            g.tick(g.last_seen+9)
        self.assertEqual(g.phase,'paused')
        self.assertIn('自动暂停',g.notes[-1]['message'])

    def test_ground_actions_roundtrip_through_browser_api(self):
        g=self.make();self.start(g)
        g.k.chefs['human'].hand=Food('held','ready',6,12)
        self.assertEqual(self.act(g,'drop')[0],200)
        g.k.advance(1)
        state=g.public_state()
        self.assertEqual(state['kitchen']['ground'][0]['food']['id'],'held')
        self.assertTrue(any(a['key']=='pickup held' for a in state['actions']))
        self.assertEqual(self.act(g,'pickup held')[0],200)
        g.k.advance(1)
        self.assertFalse(g.public_state()['kitchen']['ground'])
        self.assertEqual(g.k.chefs['human'].hand.stage,'ready')
    def test_missing_key_leaves_game_ready(self):
        g=self.make()
        def broken(c):raise RuntimeError('no key')
        g.client_factory=broken
        self.assertEqual(self.command(g,'start')[0],503)
        self.assertEqual(g.phase,'ready')
        self.assertIsNone(g.journal)
    def test_round_end_closes_log_and_stops_ai(self):
        g=self.make();self.start(g)
        journal=g.journal
        g.k.time=g.c['round_seconds']-.1
        with patch.object(g.ai,'poll'):
            g.tick(g.last_tick+1)
        self.assertEqual(g.phase,'ended')
        self.assertTrue(journal.closed)
        self.assertTrue(g.ai.closed)
    def test_goal_completion_settles_immediately_and_stops_ai(self):
        g=self.make();self.start(g,1)
        g.k.advance(50);g.k.served=2;g.k.money=60
        for order in g.k.orders[:2]:order['status']='served'
        g.k.chefs['human'].location='serve'
        g.k.chefs['human'].hand=Food('last','ready',6,12,plate_id=g.k.stations['plates'].food.id)
        g.k.stations['plates'].food=None
        self.assertEqual(self.act(g,'serve')[0],200)
        journal=g.journal
        with patch.object(g.ai,'poll') as poll:
            g.tick(g.last_tick+1)
            poll.assert_not_called()
        state=g.public_state()
        self.assertEqual(state['phase'],'ended');self.assertTrue(state['won'])
        self.assertEqual(state['kitchen']['settlement']['time_bonus'],129)
        self.assertTrue(g.ai.closed);self.assertTrue(journal.closed)
        self.assertEqual(self.command(g,'resume')[0],409)
        self.assertEqual(self.command(g,'reset')[0],200)
        self.assertIsNone(g.public_state()['kitchen']['settlement'])
    def test_public_state_does_not_include_credentials(self):
        g=self.make();self.start(g)
        public=json.dumps(g.public_state())
        self.assertNotIn('TYPESAFE_API_KEY',public)
        self.assertNotIn('env_file',public)
        self.assertNotIn('Authorization',public)
        self.assertIn('expected',public)
    def test_reset_rejected_while_running(self):
        g=self.make();self.start(g)
        self.assertEqual(self.command(g,'reset')[0],409)


if __name__=='__main__':unittest.main()


class FixedTickTests(unittest.TestCase):
    def make(self):
        from kitchen import Kitchen
        g = GameSession(config=load_config() | {'order_seed': 1, 'spawn_seed': 0}, client_factory=lambda c: None,
                        journal_factory=lambda *a: (lambda *b: None), kitchen_factory=Kitchen)
        return g

    def test_polling_rate_does_not_change_game_steps(self):
        results = []
        for polls in (7, 50, 333):
            g = self.make();g.phase = 'running';g.ai = None
            g.last_tick = g.last_seen = 0.
            for i in range(1, polls + 1):
                g.last_seen = i * 3 / polls
                g.tick(i * 3 / polls)
            results.append((g.ticks, round(g.k.time, 9), [e['t'] for e in g.k.events]))
        self.assertEqual(results[0], results[1]);self.assertEqual(results[1], results[2])
        self.assertEqual(results[0][0], 45)  # 3 s wall x 0.75 / 0.05 s ticks
