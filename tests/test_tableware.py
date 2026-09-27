"""Offline lifecycle tests: real rules/actions, no model/network fallback."""
import random
import unittest
from unittest.mock import patch
from kitchen import Kitchen, Food, load_config
from spatial_kitchen import SpatialKitchen, EQUIPMENT
from jev import JevClient
from web_server import GameSession


class TablewareTests(unittest.TestCase):
    def make(self, spatial=False, **overrides):
        config = load_config()
        config.update(round_seconds=500, order_patience=400, order_interval=10)
        config.update(overrides)
        return (SpatialKitchen if spatial else Kitchen)(config)

    def do(self, k, who, command):
        ok, reason = k.command(who, command)
        self.assertTrue(ok, (command, reason))
        job = k.chefs[who].job
        if job:
            k.advance(job.travel+job.work+1e-6)
        # Contact can delay arrival beyond the static map's initial ETA.
        for _ in range(100):
            if not k.chefs[who].job:break
            k.advance(.05)
        self.assertIsNone(k.chefs[who].job, 'Action did not finish after contact')
        k.assert_invariants()

    def ready(self, k, name='meal', who='human', stage='ready'):
        self.assertIsNone(k.chefs[who].hand)
        k.stations['p1'].food = Food(name, stage, 6, 12)
        k.stations['p1'].heating = False

    def plate(self, k, who='human'):
        key = next(a.key for a in k.actions(who) if a.kind == 'take_plate')
        self.do(k, who, key)
        self.do(k, who, 'plate p1')

    def serve(self, k, name, who='human', stage='ready'):
        self.ready(k, name, who, stage)
        self.plate(k, who)
        plate = k.chefs[who].hand.plate_id
        self.do(k, who, 'serve')
        return plate

    def test_three_meals_require_recycled_plate_both_kitchens(self):
        for spatial in (False, True):
            k = self.make(spatial)
            k.advance(20)  # Three real pending orders; fixtures omit the cooking time.
            first = self.serve(k, 'first')
            self.serve(k, 'second', 'jeff')
            self.assertFalse(k.stations['plates'].food)
            self.ready(k, 'third')
            self.assertNotIn('plate', [a.key for a in k.actions('human')])
            self.assertFalse(k.command('human', 'serve')[0])
            k.advance(8)
            for action in ('take returns', 'put sink', 'wash', 'take sink', 'put plates'):
                self.do(k, 'jeff', action)
            self.plate(k)
            self.assertEqual(k.chefs['human'].hand.plate_id, first)
            self.do(k, 'human', 'serve')
            self.assertTrue(k.won()); self.assertTrue(k.ended)
            self.assertEqual(k.served, 3)

    def test_complete_cooking_chain_with_clean_plate_at_pot(self):
        k = self.make(True)
        for key in ('fetch', 'put b1', 'chop b1', 'take b1', 'put p1', 'take plates'):
            self.do(k, 'human', key)
        k.advance(12)
        plate = k.chefs['human'].hand.id
        self.do(k, 'human', 'plate p1')
        self.assertEqual(k.chefs['human'].hand.plate_id, plate)
        self.assertFalse(k.stations['p1'].heating)
        self.assertFalse(k.stations['p1'].food)
        self.assertFalse(k.ground)
        self.do(k, 'human', 'serve')
        self.assertEqual(k.money, 30)

    def test_customer_queue_does_not_overwrite_full_return_tray(self):
        k = self.make()
        ids = [self.serve(k, 'first'), self.serve(k, 'second')]
        k.advance(10)
        self.assertEqual(k.stations['returns'].food.id, ids[0])
        self.assertEqual(len(k.dining), 1)
        self.assertTrue(k.snapshot()['tableware']['customers'][0]['waiting_for_space'])
        self.do(k, 'human', 'take returns'); k.advance(.05)
        self.assertEqual(k.chefs['human'].hand.id, ids[0])
        self.assertEqual(k.stations['returns'].food.id, ids[1])
        k.assert_invariants()

    def dirty_in_sink(self, k):
        plate = self.serve(k, 'first')
        k.advance(8)
        self.do(k, 'human', 'take returns'); self.do(k, 'human', 'put sink')
        return plate

    def test_wash_interruption_and_other_chef_continues(self):
        k = self.make()
        plate = self.dirty_in_sink(k)
        self.assertTrue(k.command('human', 'wash')[0]); k.advance(1.5)
        self.assertFalse(k.command('jeff', 'wash')[0])
        self.do(k, 'human', 'stop')
        self.assertAlmostEqual(k.stations['sink'].food.washed, 1.5)
        self.assertTrue(k.command('jeff', 'wash')[0])
        self.assertAlmostEqual(k.chefs['jeff'].job.work, 2.5)
        k.advance(k.chefs['jeff'].job.travel+2.5)
        self.assertEqual(k.stations['sink'].food.stage, 'clean_plate')
        self.do(k, 'jeff', 'take sink')
        self.assertEqual(k.chefs['jeff'].hand.id, plate)

    def test_full_hand_swap_preserves_plated_food_and_empty_plate(self):
        k = self.make(True)
        self.ready(k); self.plate(k)
        self.do(k, 'human', 'take counter2')
        self.assertEqual(k.chefs['human'].hand.stage, 'clean_plate')
        self.assertEqual(k.ground['meal'].food.plate_id, 'D1')
        self.do(k, 'jeff', 'pickup meal')
        self.assertEqual(k.chefs['jeff'].hand.plate_id, 'D1')
        k.assert_invariants()

    def test_plates_pass_at_short_range_and_can_drop_and_pickup_for_both_chefs(self):
        import math
        from spatial_kitchen import EQUIPMENT, PASS_RANGE
        from kitchen import Action
        for who in ('human','jeff'):
            for stage in ('clean_plate','dirty_plate','ready','burnt'):
                k=self.make(True)
                if stage in ('ready','burnt'):
                    self.ready(k);self.plate(k);k.chefs['human'].hand.stage=stage
                else:
                    self.do(k,'human','take plates');k.chefs['human'].hand.stage=stage
                if who=='jeff':k.chefs['jeff'].hand,k.chefs['human'].hand=k.chefs['human'].hand,None
                item=k.chefs[who].hand;k.positions[who]=(3.,4.);before=(item.stage,item.plate_id,item.components)
                snap=k.snapshot()['chefs'][who]
                self.assertTrue(snap['can_throw']);self.assertEqual(snap['throw_range'],PASS_RANGE)
                # Plates never land on boards or counters: that throw is refused, the plate stays in hand.
                forged=Action('throw','throw','throw','b1',(item.id,'b1',*EQUIPMENT['b1']['cell']))
                self.assertFalse(k.start(who,forged)[0]);self.assertIs(k.chefs[who].hand,item)
                # A long aim falls on the floor at the pass range, intact and pickable.
                self.assertTrue(k.start(who,k.throw_action(who,(12,4)))[0]);k.advance(1)
                self.assertIsNone(k.chefs[who].hand);self.assertFalse(k.projectiles)
                self.assertIs(k.ground[item.id].food,item);self.assertEqual((item.stage,item.plate_id,item.components),before)
                self.assertLessEqual(math.dist((3.,4.),k.cell(k.ground[item.id].location)),PASS_RANGE+1e-8)
                self.do(k,who,'pickup '+item.id);self.assertIs(k.chefs[who].hand,item)
                self.do(k,who,'drop');self.assertIs(k.ground[item.id].food,item)
                self.do(k,who,'pickup '+item.id)
                self.assertIs(k.chefs[who].hand,item);self.assertFalse(k.projectiles)
                k.assert_invariants()

    def test_discard_keeps_dirty_plate_and_empty_plates_cannot_be_trashed(self):
        k = self.make()
        self.ready(k); self.plate(k)
        self.do(k, 'human', 'discard')
        self.assertEqual(k.chefs['human'].hand.stage, 'dirty_plate')
        self.assertEqual(k.money, -2)
        for key in ('serve', 'discard', 'plate'):
            self.assertFalse(k.command('human', key)[0])
        self.do(k, 'human', 'put sink'); self.do(k, 'human', 'wash')
        self.do(k, 'human', 'take sink')
        for key in ('serve', 'discard', 'put sink'):
            self.assertFalse(k.command('human', key)[0])

    def test_bad_service_returns_plate_without_making_food_good(self):
        k = self.make()
        plate = self.serve(k, 'burnt', stage='burnt')
        self.assertEqual((k.money, k.bad_reviews), (-15, 1))
        k.advance(8)
        self.assertEqual(k.stations['returns'].food.id, plate)
        k.assert_invariants()

    def test_two_chefs_race_for_same_plate_only_one_wins(self):
        k = self.make()
        k.chefs['human'].location = k.chefs['jeff'].location = 'plates'
        for who in ('human', 'jeff'):
            self.assertTrue(k.command(who, 'take plates')[0])
        k.advance(.2)
        self.assertEqual(sum(c.hand is not None for c in k.chefs.values()), 1)
        self.assertEqual(k.stations['counter2'].food.stage, 'clean_plate')
        k.assert_invariants()

    def test_stale_plating_when_pot_is_moved_keeps_clean_plate(self):
        k = self.make()
        self.ready(k)
        self.do(k, 'human', 'take plates')
        action = next(a for a in k.actions('human') if a.key == 'plate p1')
        self.do(k, 'jeff', 'take pot p1')
        self.assertFalse(k.start('human', action)[0])
        self.assertEqual(k.chefs['human'].hand.stage, 'clean_plate')
        k.assert_invariants()

    def test_pause_disconnect_end_and_reset_freeze_or_restore_lifecycle(self):
        class AI:
            failures = 0
            def invalidate(self): pass
            def poll(self, enabled): pass
        config = load_config(); config.update(order_patience=400, round_seconds=500)
        g = GameSession(config=config, client_factory=lambda c:None, journal_factory=lambda *a:None)
        self.dirty_in_sink(g.k)
        g.k.command('human', 'wash'); g.k.advance(1)
        before = g.k.snapshot()
        g.ai = AI(); g.phase = 'paused'
        g.tick(g.last_tick+1)
        self.assertEqual(before, g.k.snapshot())
        g.phase = 'running'; g.last_seen = g.last_tick-9
        g.tick(g.last_tick+.1)
        self.assertEqual(g.phase, 'paused'); self.assertEqual(before, g.k.snapshot())
        g.k._end(); before = g.k.snapshot(); g.k.advance(100)
        self.assertEqual(before, g.k.snapshot())
        reset = Kitchen(config)
        self.assertEqual(sum(reset.stations[c].food is not None for c in reset.counters), 2)
        self.assertFalse(reset.dining); self.assertFalse(reset.stations['sink'].food)
        reset.assert_invariants()

    def test_ai_receives_rules_locations_progress_and_legal_actions(self):
        k = self.make(); self.dirty_in_sink(k)
        payload = JevClient(k.c, key='offline-test-only').payload(k.snapshot(), k.actions('jeff'))
        self.assertIn('wash', payload['questions']['next_action']['criteria'])
        self.assertIn('tableware', payload['state']['rules'])
        self.assertEqual(payload['state']['kitchen']['stations']['sink']['food']['wash_remaining'], 4)
        self.assertEqual(payload['state']['kitchen']['tableware']['total'], 2)

    def test_dirty_plates_rejected_for_all_plating_routes(self):
        for who in ('human', 'jeff'):
            for route in ('stove', 'counter_pot', 'counter_plate', 'partner'):
                with self.subTest(who=who, route=route):
                    k = self.make(spatial=True)
                    plate = k.stations['plates'].food
                    k.stations['plates'].food = None
                    plate.stage = 'dirty_plate'
                    meal = Food('meal', 'ready', 6, 12)
                    if route == 'stove':
                        k.chefs[who].hand = plate
                        k.stations['p1'].food = meal
                        command = 'plate p1'
                    else:
                        pot = Food(k.stations['p1'].pot_id, 'pot', contents=meal)
                        k.stations['p1'].pot_id = None
                        if route == 'counter_pot':
                            k.chefs[who].hand = plate
                            k.stations['plates'].food = pot
                        else:
                            k.chefs[who].hand = pot
                            if route == 'partner':
                                other = 'jeff' if who == 'human' else 'human'
                                k.chefs[other].hand = plate
                            else:
                                k.stations['plates'].food = plate
                        command = 'plate partner' if route == 'partner' else 'plate plates'
                    before = k.snapshot()
                    self.assertFalse(k.command(who, command)[0])
                    self.assertEqual(k.snapshot(), before)
                    k.assert_invariants()

    def test_no_bare_food_removal_for_either_chef_or_any_pot_stage(self):
        for who in ('human', 'jeff'):
            for stage in ('cooking', 'ready', 'burnt'):
                k = self.make()
                k.stations['p1'].food = Food('hot', stage, 6, 12)
                self.assertFalse(k.command(who, 'take p1')[0])
                self.assertFalse(k.command(who, 'plate p1')[0])
                self.assertFalse(k.command(who, 'plate')[0])
                self.do(k, who, 'take pot p1')
                self.assertEqual(k.chefs[who].hand.stage, 'pot')
                self.assertEqual(k.chefs[who].hand.contents.id, 'hot')
                self.assertFalse(k.command(who, 'serve')[0])

    def test_counter_capacity_one_and_plates_start_spread_out(self):
        k = self.make()
        self.assertEqual([k.stations[c].food.id for c in k.counters if k.stations[c].food], ['D1', 'D2'])
        self.do(k, 'human', 'take plates')
        self.assertFalse(k.command('human', 'put counter2')[0])
        self.do(k, 'human', 'put counter3')
        self.assertEqual(k.stations['counter3'].food.id, 'D1')
        self.assertIsNone(k.stations['plates'].food)

    def test_carry_hot_pot_to_counter_plate_then_return_empty_pot(self):
        k = self.make(True)
        self.ready(k, 'hot')
        self.do(k, 'human', 'take pot p1')
        self.assertFalse(k.stations['p1'].pot_id)
        self.do(k, 'human', 'plate counter2')
        self.assertEqual(k.stations['counter2'].food.plate_id, 'D2')
        self.assertIsNone(k.chefs['human'].hand.contents)
        self.do(k, 'human', 'put pot p1')
        self.do(k, 'jeff', 'take counter2'); self.do(k, 'jeff', 'serve')
        self.assertEqual(k.served, 1)
        self.assertEqual(k.stations['p1'].pot_id, 'P1')

    def test_carry_pot_stops_heat_and_return_resumes_without_reset(self):
        k = self.make(True)
        k.stations['p1'].food = Food('hot', 'cooking', 6, 1)
        k.stations['p1'].heating = True
        self.do(k, 'human', 'take pot p1')
        heated = k.chefs['human'].hand.contents.heated
        k.advance(5)
        self.assertEqual(k.chefs['human'].hand.contents.heated, heated)
        self.do(k, 'human', 'put pot p1')
        k.advance(1)
        self.assertAlmostEqual(k.stations['p1'].food.heated, heated+1, places=4)

    def test_plate_from_counter_pot_and_preserve_empty_pot(self):
        k = self.make()
        self.ready(k)
        self.do(k, 'human', 'take pot p1'); self.do(k, 'human', 'put counter3')
        self.do(k, 'jeff', 'take counter2'); self.do(k, 'jeff', 'plate counter3')
        self.assertEqual(k.chefs['jeff'].hand.plate_id, 'D2')
        self.assertEqual(k.stations['counter3'].food.id, 'P1')
        self.assertIsNone(k.stations['counter3'].food.contents)
        self.do(k, 'jeff', 'serve')

    def test_two_plates_race_for_counter_pot_cannot_duplicate_food(self):
        k = self.make()
        self.ready(k); self.do(k, 'human', 'take pot p1'); self.do(k, 'human', 'put counter3')
        self.do(k, 'human', 'take plates'); self.do(k, 'jeff', 'take counter2')
        # Both depart with a valid view of the same pot; its identity stays P1
        # when the first chef removes its contents.
        for who in ('human', 'jeff'):
            self.assertTrue(k.command(who, 'plate counter3')[0])
        k.advance(5); k.assert_invariants()
        self.assertEqual(sum(bool(c.hand.plate_id) for c in k.chefs.values()), 1)
        self.assertEqual(sum(c.hand.stage == 'clean_plate' for c in k.chefs.values()), 1)

    def test_discard_pot_contents_does_not_destroy_pot(self):
        k = self.make(True)
        self.ready(k)
        self.do(k, 'human', 'take pot p1'); self.do(k, 'human', 'discard')
        self.assertEqual(k.chefs['human'].hand.id, 'P1')
        self.assertIsNone(k.chefs['human'].hand.contents)
        self.assertFalse(k.command('human', 'discard')[0])
        self.do(k, 'human', 'drop'); self.do(k, 'jeff', 'pickup P1')
        self.do(k, 'jeff', 'put pot p1')
        self.assertEqual(k.money, -2)

    def test_random_interleaved_tableware_actions_preserve_all_plates(self):
        k = self.make(); self.dirty_in_sink(k)
        rng = random.Random(791)
        for _ in range(500):
            who = rng.choice(['human', 'jeff'])
            actions = k.actions(who)
            if actions and rng.random() < .3:
                k.start(who, rng.choice(actions))
            k.advance(.1); k.assert_invariants()


if __name__ == '__main__': unittest.main()
