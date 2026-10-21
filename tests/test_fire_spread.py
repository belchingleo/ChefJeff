import unittest
from kitchen import load_config, Food
from spatial_kitchen import SpatialKitchen
from jev import JevClient
from model_language import english_data


class FireSpreadTests(unittest.TestCase):
    def make(self):
        c=load_config();c.update(level=2,spawn_seed=0,round_seconds=500,order_patience=450,order_interval=100)
        return SpatialKitchen(c)

    def burning(self,k):
        return {key for key,s in k.stations.items() if s.fire}

    def test_one_burning_neighbour_ignites_after_five_game_seconds(self):
        # Overcooked 2: every flammable neighbour heats at once; one fire next to it takes 5 s.
        k=self.make(); k.ignite('p1')
        adjacent=k.fire_neighbors('p1'); self.assertTrue(adjacent)
        k.advance(4.9);self.assertEqual(self.burning(k),{'p1'})
        self.assertAlmostEqual(k.stations[adjacent[0]].fire_heat,.98,places=2)
        k.advance(.15);self.assertTrue(set(adjacent)<=self.burning(k))
        k.assert_invariants()

    def test_several_burning_neighbours_add_up(self):
        k=self.make()
        target=next(key for key in k.stations if len(k.fire_neighbors(key))>=2)
        a,b=k.fire_neighbors(target)[:2];k.ignite(a);k.ignite(b)
        k.advance(2.4);self.assertFalse(k.stations[target].fire)
        k.advance(.15);self.assertTrue(k.stations[target].fire)

    def test_diagonals_spread_but_never_across_floor(self):
        k=self.make();diagonal=False
        for key in k.stations:
            for n in k.fire_neighbors(key):
                a,b=k.equipment[key]['cell'],k.equipment[n]['cell']
                self.assertEqual(max(abs(a[0]-b[0]),abs(a[1]-b[1])),1)
                diagonal|=abs(a[0]-b[0])==abs(a[1]-b[1])==1
        self.assertTrue(diagonal)
        self.assertEqual(k.fire_neighbors('sink'),[])

    def test_heat_holds_then_drains_without_a_burning_neighbour(self):
        k=self.make();k.ignite('p1');n=k.fire_neighbors('p1')[0]
        k.advance(3);self.assertAlmostEqual(k.stations[n].fire_heat,.6,places=2)
        k.stations['p1'].fire=False
        k.advance(1.9);self.assertAlmostEqual(k.stations[n].fire_heat,.6,places=2)
        k.advance(.6);self.assertAlmostEqual(k.stations[n].fire_heat,.1,places=1)
        k.advance(.2);self.assertEqual(k.stations[n].fire_heat,0)

    def test_counter_fire_blocks_use_and_both_chefs_can_extinguish(self):
        for who in ['human','jeff']:
            k=self.make();target=k.counters[0];k.ignite(target)
            tool=k.stations['extinguisher'].food;k.stations['extinguisher'].food=None;k.chefs[who].hand=tool
            options=k.actions(who)
            self.assertTrue(any(a.key=='extinguish '+target for a in options))
            self.assertTrue(all(a.kind in ['go','extinguish','put_counter'] for a in options if a.target==target))
            ok,_=k.command(who,'extinguish '+target);self.assertTrue(ok)
            j=k.chefs[who].job;k.advance(j.travel+j.work+.001)
            self.assertFalse(k.stations[target].fire);self.assertAlmostEqual(k.stations[target].sprayed,k.rules.relight_delay,places=1)
            k.assert_invariants()

    def test_a_station_just_put_out_takes_no_heat_for_two_seconds(self):
        k=self.make();k.ignite('p1');n=k.fire_neighbors('p1')[0];k.ignite(n)
        k.stations[n].fire=False;k.stations[n].sprayed=k.rules.relight_delay
        k.advance(1.9);self.assertEqual(k.stations[n].fire_heat,0)
        k.advance(.6);self.assertGreater(k.stations[n].fire_heat,0)

    def test_spraying_progress_stays_then_the_fire_grows_back_for_both_chefs(self):
        # Overcooked 2's FightFire: spraying lowers the fire's strength, which the station keeps; left alone
        # for 2 s it grows back to full over 5 s. Walking away mid-spray loses nothing straight away.
        seen=[]
        for who in ['human','jeff']:
            k=self.make();target=k.counters[0];k.ignite(target);s=k.stations[target]
            tool=k.stations['extinguisher'].food;k.stations['extinguisher'].food=None;k.chefs[who].hand=tool
            k.command(who,'extinguish '+target);j=k.chefs[who].job;k.advance(j.travel+2)
            self.assertAlmostEqual(s.fire_strength,.5,places=1);self.assertTrue(s.fire)
            self.assertIn('2s',next(a.label for a in k.actions(who) if a.key=='extinguish '+target))
            sprayed=s.fire_strength;k.stop(who);k.advance(1.9);self.assertAlmostEqual(s.fire_strength,.5,places=1)
            k.advance(1.1);self.assertAlmostEqual(s.fire_strength,.68,places=1);regrown=s.fire_strength
            # Spraying again only has what is left to put out.
            self.assertTrue(k.command(who,'extinguish '+target)[0]);self.assertAlmostEqual(k.chefs[who].job.work,s.fire_strength*4,places=2)
            k.advance(k.chefs[who].job.travel+k.chefs[who].job.work+.1);self.assertFalse(s.fire)
            seen.append((round(sprayed,3),round(regrown,3)));k.assert_invariants()
        self.assertEqual(seen[0],seen[1])

    def test_burning_surfaces_still_give_and_take_but_burning_stoves_and_chopping_wait(self):
        # Overcooked 2's fire turns off a station's use (Interactable, Workstation, PickupItemSpawner), not its
        # surface (AttachStation): the extinguisher put on a counter that catches fire can be taken back.
        for who in ['human','jeff']:
            k=self.make();tool=k.stations['extinguisher'].food;k.stations['extinguisher'].food=None
            spot=next(c for c in k.counters if k.stations[c].food is None)
            k.stations[spot].food=tool;k.ignite(spot)
            k.stations['b1'].food=Food('meat','raw',ingredient='beef');k.ignite('b1');k.ignite('p1')
            keys={a.key for a in k.actions(who)}
            self.assertIn('take '+spot,keys);self.assertIn('take b1',keys);self.assertNotIn('chop b1',keys)
            # A burning stove gives up its pan too (Overcooked 2, checked in the game): lift, return, refill when empty.
            self.assertEqual({a.kind for a in k.actions(who) if a.target=='p1'},{'go','lift_pot'})
            self.assertTrue(k.command(who,'take '+spot)[0]);j=k.chefs[who].job;k.advance(j.travel+j.work+.01)
            self.assertIs(k.chefs[who].hand,tool);k.assert_invariants()

    def test_a_pan_lifted_off_a_burning_stove_can_go_back_and_be_refilled_but_only_cooks_after_the_fire(self):
        for who in ['human','jeff']:
            k=self.make();s=k.stations['p1'];s.food=Food('F','cooking',6,0,ingredient='beef');s.heating=True;k.ignite('p1')
            k.positions[who]=tuple(map(float,k.equipment['p1']['access']))
            def do(key):
                self.assertTrue(k.command(who,key)[0],key);j=k.chefs[who].job;k.advance(j.travel+j.work+.01)
            do('take pot p1');pan=k.chefs[who].hand;self.assertEqual(pan.contents.stage,'burnt');self.assertTrue(s.fire)
            pan.contents=None;do('put pot p1');self.assertEqual(s.pot_id,pan.id)
            k.chefs[who].hand=Food('cut','chopped',6,ingredient='beef');do('put p1')
            heated=s.food.heated;k.advance(1);self.assertEqual(s.food.heated,heated)  # no heat while burning
            tool=k.stations['extinguisher'].food;k.stations['extinguisher'].food=None;k.chefs[who].hand=tool
            do('extinguish p1');self.assertFalse(s.fire);self.assertTrue(s.heating)
            k.advance(1);self.assertGreater(s.food.heated,heated);k.assert_invariants()

    def test_fifth_active_fire_ends_the_round_as_failed(self):
        k=self.make()
        for key in k.counters[:5]:k.ignite(key)
        k.advance(.05)
        self.assertTrue(k.ended);self.assertFalse(k.won());self.assertEqual(k.failure_reason,'fire_spread')
        self.assertEqual(k.actions('jeff'),[])
        self.assertEqual(k.snapshot()['fire_safety']['burning_count'],5)

    def test_new_fire_cancels_chopping_but_burning_stations_still_catch_a_throw(self):
        k=self.make();k.stations['b1'].food=Food('raw-test')
        k.positions['human']=k.equipment['b1']['access'];k.command('human','chop b1')
        k.advance(k.chefs['human'].job.travel+.1)
        self.assertTrue(k.chefs['human'].job.working)
        k.ignite('b1');self.assertIsNone(k.chefs['human'].job)
        # Overcooked 2: a burning board's surface and a burning stove's empty pan still catch a throw.
        food=Food('throw-test','raw',ingredient='beef');k.stations['b1'].food=None
        self.assertTrue(k.station_catches('b1',food,'human'))
        k.ignite('p1');k.stations['p1'].food=None
        self.assertTrue(k.station_catches('p1',Food('cut','chopped',ingredient='beef'),'human'));k.assert_invariants()

    def test_fire_rule_and_state_reach_model_in_english(self):
        k=self.make();k.ignite('p1')
        payload=JevClient(k.c,key='offline-test').payload(k.snapshot(),k.actions('jeff'))
        import json,re
        text=json.dumps(payload,ensure_ascii=False)
        self.assertNotRegex(text,r'[\u3400-\u9fff]')
        self.assertIn('5 simultaneously burning',text)
        self.assertIn('fire_heat',text)

if __name__=='__main__':unittest.main()
