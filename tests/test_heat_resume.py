"""Regression tests for cooking and burn timers across pot moves."""
import unittest

from kitchen import Food, load_config
from spatial_kitchen import SpatialKitchen


class HeatResumeTests(unittest.TestCase):
    def make(self):
        config = load_config()
        config.update(round_seconds=500, order_patience=400, order_interval=1000, target_money=0)
        config['level'] = 3
        return SpatialKitchen(config)

    def do(self, k, who, command):
        ok, reason = k.command(who, command)
        self.assertTrue(ok, (command, reason))
        job = k.chefs[who].job
        if job:
            k.advance(job.travel + job.work + 1e-6)
        k.assert_invariants()

    def load_partly_cooked_pot(self, k):
        # A valid put-pot action starts heating; the partial heat is then
        # established by the game's timer before using legal pot actions.
        k.chefs['human'].hand = Food('beef', 'chopped', chopped=6)
        self.do(k, 'human', 'put p1')
        k.advance(3)
        self.assertEqual(k.stations['p1'].food.stage, 'cooking')
        self.assertAlmostEqual(k.stations['p1'].food.heated, 3, places=4)

    def test_partly_cooked_pot_pauses_off_stove_and_resumes_on_either_stove(self):
        for destination in ('p1', 'p2'):
            with self.subTest(destination=destination):
                k = self.make()
                self.load_partly_cooked_pot(k)
                self.do(k, 'human', 'take pot p1')
                held = k.chefs['human'].hand.contents
                saved_heat = held.heated
                saved_stage = held.stage
                k.advance(5)
                self.assertEqual((held.heated, held.stage), (saved_heat, saved_stage))
                if destination == 'p1':
                    self.do(k, 'human', 'put pot p1')
                else:
                    # Swapping with the empty burner pot is the legal way to
                    # move this loaded pot to the second stove.
                    self.do(k, 'human', 'swap pot p2')
                    self.assertEqual(k.chefs['human'].hand.id, 'P2')
                remaining = k.c['cook_seconds'] - saved_heat
                k.advance(remaining - .5)
                active = k.stations[destination].food
                self.assertEqual(active.stage, 'cooking')
                self.assertAlmostEqual(active.heated, k.c['cook_seconds'] - .5, places=3)
                k.advance(.6)
                self.assertEqual(active.stage, 'ready')

    def test_ready_pot_burn_timer_pauses_on_counter_and_resumes_after_retrieval(self):
        k = self.make()
        self.load_partly_cooked_pot(k)
        k.advance(k.c['cook_seconds'] - k.stations['p1'].food.heated)
        self.assertEqual(k.stations['p1'].food.stage, 'ready')
        self.do(k, 'human', 'take pot p1')
        self.do(k, 'human', 'put counter7')
        stored = k.stations['counter7'].food
        stored_heat = stored.contents.heated
        k.advance(5)
        self.assertEqual(stored.contents.heated, stored_heat)
        self.do(k, 'human', 'take counter7')
        self.do(k, 'human', 'put pot p1')
        food = k.stations['p1'].food
        self.assertEqual(food.stage, 'ready')
        burn_remaining = k.c['cook_seconds'] + k.c['burn_after_ready'] - food.heated
        k.advance(burn_remaining - .5)
        self.assertEqual(food.stage, 'ready')
        self.assertAlmostEqual(food.heated, k.c['cook_seconds'] + k.c['burn_after_ready'] - .5, places=3)
        k.advance(.6)
        self.assertEqual(food.stage, 'burnt')


if __name__ == '__main__':
    unittest.main()
