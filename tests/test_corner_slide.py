"""Keyboard walking slides past a corner it only just catches (ruleset movement.corner_slide_cells)."""
import unittest

import config_contract as cc
from kitchen import Food
from spatial_kitchen import SpatialKitchen

CORNER = (9.75, 5.5)  # level 2: just inside the east end of the central run (counter22, side edge x=9.85)


def walk(level, start, direction, seconds=.5, held=None):
    k = SpatialKitchen(cc.load_level(level))
    k.positions['jeff'] = (6.0, 2.22)
    k.positions['human'] = start
    if held:
        k.chefs['human'].hand = held
    k.set_manual('human', *direction)
    for _ in range(round(seconds / .05)):
        k.advance(.05)
    k.set_manual('human', 0, 0)
    k.assert_invariants()
    return k.positions['human']


class CornerSlideTests(unittest.TestCase):
    def test_walking_past_the_end_of_a_run(self):
        # Walking north 0.1 cells inside the run's east edge slides out and walks on, holding food or not.
        for held in (None, Food('F5', 'chopped', 6)):
            x, y = walk('level-2', CORNER, (0, -1), held=held)
            self.assertAlmostEqual(x, 9.85, places=2)
            self.assertLess(y, 4.5)

    def test_no_slide_into_a_solid_row(self):
        # Walking down into the counter row: no sideways shift within the limit gets past it.
        before = (7.0, 6.3)
        after = walk('level-2', before, (0, 1))
        self.assertAlmostEqual(after[0], before[0], places=6)
        self.assertLess(after[1], 6.51)

    def test_the_slide_never_exceeds_the_ruleset_limit(self):
        k = SpatialKitchen(cc.load_level('level-2'))
        limit = k.rules.corner_slide
        found = k.corner_offset((CORNER[0], 4.95), (0.0, -1.0))
        self.assertIsNotNone(found)
        self.assertLessEqual(abs(found[0]), limit + 1e-9)


if __name__ == '__main__':
    unittest.main()
