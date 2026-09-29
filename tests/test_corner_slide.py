"""Keyboard walking slides out of shallow notches (ruleset movement.corner_slide_cells)."""
import unittest

import config_contract as cc
from kitchen import Food
from spatial_kitchen import SpatialKitchen

NOTCH = (6.15, 6.5)  # level 2: in front of board 2, between counters 15 and 19


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
    def test_sideways_keys_leave_the_board_notch(self):
        # The 2026-09-29 playtest: holding chopped beef, the player could not walk right.
        right = walk('level-2', NOTCH, (1, 0), held=Food('F5', 'chopped', 6))
        left = walk('level-2', NOTCH, (-1, 0))
        self.assertGreater(right[0], 7.5)
        self.assertLess(left[0], 5)
        for x, y in (right, left):
            self.assertAlmostEqual(y, NOTCH[1] - .2, places=2)

    def test_legacy_rules_do_not_slide(self):
        self.assertLess(walk('legacy-level-2', NOTCH, (1, 0))[0], 6.4)

    def test_no_slide_into_a_solid_row(self):
        # Walking down into the counter row: no sideways shift within the limit gets past it.
        before = (7.0, 6.3)
        after = walk('level-2', before, (0, 1))
        self.assertAlmostEqual(after[0], before[0], places=6)
        self.assertLess(after[1], 6.51)

    def test_the_slide_never_exceeds_the_ruleset_limit(self):
        k = SpatialKitchen(cc.load_level('level-2'))
        limit = k.rules.corner_slide
        found = k.corner_offset(NOTCH, (1.0, 0.0))
        self.assertIsNotNone(found)
        self.assertLessEqual(abs(found[0]), limit + 1e-9)


if __name__ == '__main__':
    unittest.main()
