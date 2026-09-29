"""Either chef can walk into the other on purpose ("go partner"); contact pushes."""
import math
import unittest

import config_contract as cc
from kitchen import Food
from spatial_kitchen import SpatialKitchen
from whitebox_server import model_candidates


class ApproachPartnerTests(unittest.TestCase):
    def test_either_chef_can_walk_into_the_other_and_push(self):
        for level in ('level-1', 'level-3'):
            for who, other in (('jeff', 'human'), ('human', 'jeff')):
                for sprint, least in ((True, .2), (False, .01)):
                    with self.subTest(level=level, who=who, sprint=sprint):
                        k = SpatialKitchen(cc.load_level(level))
                        a = next(a for a in k.actions(who) if a.key == 'go partner')
                        self.assertTrue(k.start(who, a)[0])
                        start, sprinted, steps = k.positions[other], False, 0
                        while k.chefs[who].job and steps < 200:
                            if sprint and not sprinted and math.dist(k.positions[who], k.positions[other]) < 1:
                                sprinted = k.sprint(who)
                            k.advance(.05)
                            steps += 1
                        self.assertIsNone(k.chefs[who].job)
                        self.assertGreaterEqual(math.dist(start, k.positions[other]), least)
                        self.assertLessEqual(math.dist(start, k.positions[other]), k.rules.sprint_push + .1)
                        k.assert_invariants()

    def test_legacy_rules_have_no_approach_and_the_model_always_sees_it(self):
        legacy = SpatialKitchen(cc.load_level('legacy-level-1'))
        self.assertNotIn('go partner', {a.key for a in legacy.actions('jeff')})
        k = SpatialKitchen(cc.load_level('level-3'))
        listed = {a.key for a in model_candidates(k.snapshot(), k.actions('jeff'), 2)}
        self.assertIn('go partner', listed)

    def test_a_working_chef_is_not_pushed(self):
        k = SpatialKitchen(cc.load_level('level-1'))
        board = k.boards[0]
        k.stations[board].food = Food('F80', 'raw', ingredient='beef')
        chop = next(a for a in k.actions('human') if a.key == f'chop {board}')
        k.positions['human'] = k.path('human', chop.target)[-1]
        self.assertTrue(k.start('human', chop)[0])
        k.advance(.1)
        self.assertTrue(k.chefs['human'].job.working)
        before = k.positions['human']
        a = next(a for a in k.actions('jeff') if a.key == 'go partner')
        k.start('jeff', a)
        for _ in range(60):
            k.advance(.05)
        self.assertEqual(k.positions['human'], before)


if __name__ == '__main__':
    unittest.main()
