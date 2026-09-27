"""Continuous service semantics (new ruleset only): seeded fixed-interval orders,
minimum-deliveries goal and fixed-round closing."""
import copy
import unittest

import config_contract as cc
from kitchen import Food, Kitchen
from levels import available_levels
from spatial_kitchen import SpatialKitchen


def pilot(**changes):
    bundle = cc.level_bundle('pilot-draft-mixed', embed=True)
    bundle['level']['seeds'] = {'orders': 3, 'spawn': 0}
    for kind, edit in changes.items():
        edit(bundle[kind])
    return cc.freeze_bundle(bundle)


class PilotIsolationTests(unittest.TestCase):
    def test_pilot_is_unlisted_and_uses_its_own_ruleset(self):
        self.assertNotIn('pilot-draft-mixed', [entry['id'] for entry in available_levels()])
        self.assertEqual([entry['id'] for entry in available_levels()], ['level-1', 'level-2', 'level-3'])
        resolved = pilot()
        self.assertEqual(resolved['ruleset']['engine_semantics'], 'continuous-2026-09')
        for n in (1, 2, 3):
            self.assertEqual(cc.load_level(f'level-{n}')['ruleset']['engine_semantics'], 'legacy-2026-09')


class ContinuousRoundTests(unittest.TestCase):
    def test_order_plan_boundaries(self):
        plan = pilot()['order_plan']['orders']
        self.assertEqual([o['arrival_game_ms'] for o in plan], [0, 25000, 50000, 75000, 100000, 125000, 150000])
        for o in plan:
            self.assertEqual(o['deadline_game_ms'], min(o['arrival_game_ms'] + o['patience_game_ms'], 240000))
        self.assertEqual(pilot()['config_hash'], pilot()['config_hash'])

    def test_orders_arrive_one_at_a_time_and_backlog(self):
        k = Kitchen(pilot())
        k.advance(60.)
        self.assertEqual([o['status'] for o in k.orders[:4]], ['pending', 'pending', 'pending', 'future'])
        self.assertEqual(k.snapshot()['future_orders'], 1)  # more will come; the count is not revealed

    def test_round_runs_to_closing_and_marks_unresolved_orders(self):
        k = Kitchen(pilot())
        k.advance(239.9)
        self.assertFalse(k.ended)
        k.advance(1.)
        self.assertTrue(k.ended)
        self.assertAlmostEqual(k.time, 240., places=6)
        statuses = {o['status'] for o in k.orders}
        self.assertLessEqual(statuses, {'expired', 'unresolved_at_close'})
        # An order whose clipped deadline is the closing time is unresolved, not expired.
        for o in k.orders:
            if o['deadline'] >= 240 - 1e-9:
                self.assertEqual(o['status'], 'unresolved_at_close')
        self.assertEqual(k.snapshot()['future_orders'], 0)
        self.assertIn('未达目标', k.result())

    def test_reaching_the_minimum_does_not_end_the_round(self):
        k = Kitchen(pilot(level=lambda d: d['goal'].update(min_deliveries=1)))
        k.advance(1.)
        order = k.orders[0]
        dish = order['dish']
        parts = tuple(sorted(k.rules.recipe_parts[dish]))
        k.chefs['human'].hand = Food('X1', 'ready', plate_id='D1', ingredient='dish', components=parts)
        k.stations['plates'].food = None
        self.assertTrue(k.command('human', 'serve')[0])
        k.advance(10.)
        self.assertEqual(k.served, 1)
        self.assertFalse(k.ended)
        self.assertEqual([e['kind'] for e in k.events].count('goal_reached'), 1)
        k.advance(300.)
        self.assertTrue(k.ended)
        self.assertEqual(k.time_bonus, 0)
        self.assertIn('目标达成', k.result())

    def test_impossible_goal_is_announced_once_and_play_continues(self):
        k = Kitchen(pilot())
        k.advance(200.)  # nothing served: most orders expire
        kinds = [e['kind'] for e in k.events]
        self.assertEqual(kinds.count('goal_unreachable'), 1)
        self.assertFalse(k.ended)
        status = k.snapshot()['goal_status']
        self.assertFalse(status['deliveries_reachable'])
        self.assertLess(status['max_possible_deliveries'], status['target_deliveries'])

    def test_one_large_step_equals_many_small_steps(self):
        a, b = Kitchen(pilot()), Kitchen(pilot())
        a.advance(180.)
        for _ in range(3600):
            b.advance(.05)
        self.assertEqual([(o['id'], o['status']) for o in a.orders], [(o['id'], o['status']) for o in b.orders])
        self.assertEqual([(e['kind'], e.get('order_id')) for e in a.events], [(e['kind'], e.get('order_id')) for e in b.events])

    def test_spatial_kitchen_runs_the_pilot(self):
        k = SpatialKitchen(pilot())
        k.advance(30.)
        k.assert_invariants()
        self.assertEqual(k.snapshot()['level_id'], 'pilot-draft-mixed')


class LegacyGoalStatusTests(unittest.TestCase):
    def test_legacy_rounds_report_reachability_without_changing_outcomes(self):
        k = SpatialKitchen(cc.load_level('level-2', seeds={'orders': 7, 'spawn': 0}))
        k.advance(185.)
        status = k.snapshot()['goal_status']
        self.assertFalse(status['deliveries_reachable'])
        self.assertFalse(k.ended)  # accepted legacy behaviour is unchanged (open decision O-4)
        self.assertNotIn('goal_unreachable', [e['kind'] for e in k.events])


if __name__ == '__main__':
    unittest.main()
