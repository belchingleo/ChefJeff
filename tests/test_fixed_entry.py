"""Offline validity checks for the authored missing-plate / urgent-pot entry."""
import unittest

from scenarios.fixed_entry_001.run import build_scene, run_reference


class FixedEntryTests(unittest.TestCase):
    def test_entry_is_repeatable_and_has_no_hidden_clean_plate(self):
        k = build_scene()
        self.assertEqual(k.snapshot(), build_scene().snapshot())
        self.assertEqual(k.time, 0)
        self.assertEqual(k.plate_count, 2)
        self.assertFalse(k.dining)
        self.assertFalse(k.ground)
        self.assertFalse(k.projectiles)
        self.assertTrue(all(c.hand is None for c in k.chefs.values()))
        self.assertEqual({s.food.id: s.food.stage for s in k.stations.values()
                          if s.food and s.food.id.startswith('D')},
                         {'D1': 'dirty_plate', 'D2': 'dirty_plate'})
        k.assert_invariants()

    def test_unattended_food_burns_before_player_finishes_chopping(self):
        k = build_scene()
        k.advance(2.9)
        self.assertEqual(k.stations['p1'].food.stage, 'ready')
        k.advance(.2)
        self.assertEqual(k.stations['p1'].food.stage, 'burnt')
        self.assertIsNotNone(k.chefs['human'].job)
        k.assert_invariants()

    def test_reference_routes_are_legal_and_deliver_the_same_target(self):
        for storage, plate in [('put counter2', 'plate counter2'),
                               ('drop', 'plate ground P1')]:
            result, _ = run_reference('rescue', ['take pot p1', storage, 'wash',
                                                'take sink', plate, 'serve'])
            self.assertTrue(result['success'])
            self.assertTrue(result['target_F1_served_unburnt'])
            self.assertEqual(result['money'], 30)
            self.assertEqual(result['burns'], 0)
            # Faster travel may deliver before the human's six-second chop ends.
            completed=[e['action'] for e in result['human_events'] if e['kind']=='action_done']
            self.assertIn(completed, ([], ['chop b1']))
            if not completed:
                actor=result['final_state']['chefs']['human']
                self.assertEqual(actor['action_kind'],'chop')
                self.assertTrue(actor['working'])
                self.assertGreater(actor['work_remaining'],0)

    def test_wash_first_is_legal_but_misses_the_thermal_deadline(self):
        self.assertIn('wash', [a.key for a in build_scene().actions('jev')])
        result, _ = run_reference('failure_control',
                                  ['wash', 'take sink', 'plate p1', 'serve'])
        self.assertFalse(result['success'])
        self.assertEqual(result['burns'], 1)
        self.assertEqual(result['served'], 0)

    def test_one_second_per_decision_still_leaves_a_feasible_reference(self):
        result, _ = run_reference('delayed', ['take pot p1', 'put counter2',
                                             'wash', 'take sink', 'plate counter2', 'serve'], 1)
        self.assertTrue(result['success'])
        self.assertLess(result['time'], 35)


if __name__ == '__main__':
    unittest.main()
