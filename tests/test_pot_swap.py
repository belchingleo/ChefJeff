import json
import re
import unittest

from kitchen import Food, GroundItem, load_config
from spatial_kitchen import SpatialKitchen, tile_key
from whitebox_server import SpatialJevClient


class PotSwapTests(unittest.TestCase):
    def make(self):
        return SpatialKitchen({**load_config(), 'level': 3, 'spawn_seed': 0})

    def finish(self,k,who,key):
        action=next(a for a in k.actions(who) if a.key==key)
        k.positions[who]=k.path(who,action.target)[-1]
        self.assertTrue(k.start(who,action)[0])
        k.advance(.3)
        k.assert_invariants()

    def held_spare(self,k,who):
        spare=k.stations['counter4'].food
        self.assertEqual(spare.stage,'pot')
        k.stations['counter4'].food=None
        k.chefs[who].hand=spare
        return spare

    def test_loaded_pot_starts_cooking_then_ready_burnt_fire(self):
        for who in ('human','jeff'):
            for place in ('ground','counter'):
                k=self.make();pot=k.stations['counter4'].food
                k.chefs[who].hand=Food('beef','chopped',chopped=6)
                if place=='ground':
                    k.stations['counter4'].food=None
                    k.ground[pot.id]=GroundItem(pot,tile_key((9,4)))
                    self.finish(k,who,'load ground '+pot.id)
                    self.finish(k,who,'pickup '+pot.id)
                else:
                    self.finish(k,who,'load counter4')
                    self.finish(k,who,'take counter4')
                # Stash the existing burner pot without destroying it.
                s=k.stations['p1'];k.stations['counter4'].food=Food(s.pot_id,'pot');s.pot_id=None
                self.finish(k,who,'put pot p1')
                self.assertEqual(s.food.stage,'cooking')
                k.advance(k.c['cook_seconds']);self.assertEqual(s.food.stage,'ready')
                k.advance(k.c['burn_after_ready']);self.assertEqual(s.food.stage,'burnt')
                k.advance(k.c['fire_after_burn']);self.assertTrue(s.fire)
                k.assert_invariants()

    def test_stove_swaps_preserve_contents_and_heat_only_on_stove(self):
        for who in ('human','jeff'):
            k=self.make();spare=self.held_spare(k,who);spare.contents=Food('in','chopped',chopped=6)
            s=k.stations['p1'];s.food=Food('out','ready',heated=12);s.heating=True
            k.positions[who]=(9,2)
            self.assertEqual(k.quick_interaction(who,preferred='p1').kind,'swap_pot')
            self.finish(k,who,'swap pot p1')
            self.assertEqual(s.pot_id,spare.id);self.assertEqual(s.food.id,'in')
            self.assertEqual(s.food.stage,'cooking')
            held=k.chefs[who].hand;self.assertEqual(held.id,'P1');self.assertEqual(held.contents.id,'out')
            before=held.contents.heated;k.advance(1);self.assertEqual(held.contents.heated,before)
            self.assertGreater(s.food.heated,0);self.assertEqual(k.money,0)

    def test_counter_and_ground_exchange_in_place(self):
        for who in ('human','jeff'):
            for place in ('counter','ground'):
                k=self.make();spare=self.held_spare(k,who);spare.contents=Food('in','chopped',heated=3)
                s=k.stations['p1'];other=Food(s.pot_id,'pot',contents=Food('out','ready',heated=12));s.pot_id=None
                if place=='counter':
                    k.stations['counter4'].food=other;target='counter4';key='swap pot counter4'
                else:
                    k.ground[other.id]=GroundItem(other,tile_key((9,4)));target='item:'+other.id;key='swap pot ground '+other.id
                k.positions[who]=k.path(who,'counter4' if place=='counter' else tile_key((9,4)))[-1]
                self.assertEqual(k.quick_interaction(who,preferred=target).key,key)
                self.finish(k,who,key)
                stored=k.stations['counter4'].food if place=='counter' else k.ground[spare.id].food
                self.assertIs(stored,spare);self.assertIs(k.chefs[who].hand,other)
                k.advance(1);self.assertEqual(stored.contents.heated,3);self.assertEqual(other.contents.heated,12)

    def test_empty_incoming_pot_does_not_heat_and_fire_blocks_swap(self):
        k=self.make();self.held_spare(k,'human');s=k.stations['p1'];s.food=Food('beef','burnt',heated=22);s.fire=True
        self.assertNotIn('swap pot p1',[a.key for a in k.actions('human')])
        s.fire=False
        self.finish(k,'human','swap pot p1');self.assertIsNone(s.food);self.assertFalse(s.heating)
        self.assertEqual(k.chefs['human'].hand.contents.stage,'burnt')

    def test_stale_ground_swap_and_lock_protect_both_pots(self):
        k=self.make();spare=self.held_spare(k,'human')
        s=k.stations['p1'];other=Food(s.pot_id,'pot');s.pot_id=None
        k.ground[other.id]=GroundItem(other,tile_key((9,4)));k.positions['human']=(9,4)
        a=next(a for a in k.actions('human') if a.key=='swap pot ground P1')
        self.assertTrue(k.start('human',a)[0]);k.advance(.05)
        self.assertNotIn('pickup P1',[a.key for a in k.actions('jeff')])
        # A changed contained item invalidates completion without exchanging pots.
        other.contents=Food('changed','chopped');k.advance(.2)
        self.assertIs(k.chefs['human'].hand,spare);self.assertIs(k.ground['P1'].food,other)
        self.assertIsNone(k.ground['P1'].lock);k.assert_invariants()

    def test_model_receives_swap_options_and_english_rules(self):
        k=self.make();self.held_spare(k,'jeff')
        payload=SpatialJevClient(k.c,key='test').payload(k.snapshot(),k.actions('jeff'))
        self.assertIn('swap pot p1',payload['questions']['next_action']['criteria'])
        self.assertFalse(re.search('[\u3400-\u9fff]',json.dumps(payload,ensure_ascii=False)))


if __name__=='__main__':unittest.main()
