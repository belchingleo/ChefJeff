import unittest
from kitchen import load_config, Food
from spatial_kitchen import SpatialKitchen
from jev import JevClient
from model_language import english_data


class FireSpreadTests(unittest.TestCase):
    def make(self):
        c=load_config();c.update(level=2,spawn_seed=0,round_seconds=500,order_patience=450)
        return SpatialKitchen(c)

    def test_adjacent_counter_spreads_after_eight_game_seconds(self):
        k=self.make(); k.ignite('p1')
        adjacent=k.fire_neighbors('p1'); self.assertTrue(adjacent)
        k.advance(7.9);self.assertEqual(sum(s.fire for s in k.stations.values()),1)
        k.advance(.11);self.assertTrue(k.stations[adjacent[0]].fire)
        self.assertEqual(sum(s.fire for s in k.stations.values()),2)
        self.assertLess(k.stations[adjacent[0]].fire_elapsed,.02)
        k.assert_invariants()

    def test_no_diagonal_or_floor_jump(self):
        k=self.make()
        for key in k.stations:
            for n in k.fire_neighbors(key):
                a,b=k.equipment[key]['cell'],k.equipment[n]['cell']
                self.assertEqual(abs(a[0]-b[0])+abs(a[1]-b[1]),1)
        self.assertEqual(k.fire_neighbors('sink'),[])

    def test_counter_fire_blocks_use_and_both_chefs_can_extinguish(self):
        for who in ['human','jev']:
            k=self.make();target=k.counters[0];k.ignite(target)
            tool=k.stations['extinguisher'].food;k.stations['extinguisher'].food=None;k.chefs[who].hand=tool
            options=k.actions(who)
            self.assertTrue(any(a.key=='extinguish '+target for a in options))
            self.assertTrue(all(a.kind in ['go','extinguish'] for a in options if a.target==target))
            ok,_=k.command(who,'extinguish '+target);self.assertTrue(ok)
            j=k.chefs[who].job;k.advance(j.travel+j.work+.001)
            self.assertFalse(k.stations[target].fire);self.assertEqual(k.stations[target].fire_elapsed,0)
            k.assert_invariants()

    def test_fifth_active_fire_ends_without_success_bonus(self):
        k=self.make()
        for key in k.counters[:5]:k.ignite(key)
        k.advance(.05)
        self.assertTrue(k.ended);self.assertFalse(k.won());self.assertEqual(k.failure_reason,'fire_spread')
        self.assertEqual(k.time_bonus,0);self.assertEqual(k.actions('jev'),[])
        self.assertEqual(k.snapshot()['fire_safety']['burning_count'],5)

    def test_new_fire_cancels_chopping_and_blocks_throw(self):
        k=self.make();k.stations['b1'].food=Food('raw-test')
        k.positions['human']=k.equipment['b1']['access'];k.command('human','chop b1')
        k.advance(k.chefs['human'].job.travel+.1)
        self.assertTrue(k.chefs['human'].job.working)
        k.ignite('b1');self.assertIsNone(k.chefs['human'].job)
        k.stations['b1'].food=None;k.chefs['human'].hand=Food('throw-test')
        self.assertFalse(k.can_throw_to('human','b1'));k.assert_invariants()

    def test_fire_rule_and_state_reach_model_in_english(self):
        k=self.make();k.ignite('p1')
        payload=JevClient(k.c,key='offline-test').payload(k.snapshot(),k.actions('jev'))
        import json,re
        text=json.dumps(payload,ensure_ascii=False)
        self.assertNotRegex(text,r'[\u3400-\u9fff]')
        self.assertIn('Five simultaneously burning',text)
        self.assertIn('fire_spread_in',text)

if __name__=='__main__':unittest.main()
