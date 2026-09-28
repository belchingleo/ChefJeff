"""Feet stay south of a cabinet's front panel, for both chefs and every kind of movement."""
import unittest

from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen, WALK_CLEARANCE


class CabinetFrontClearanceTests(unittest.TestCase):
    def make(self, level):
        return SpatialKitchen(level_config(load_config() | {'spawn_seed': 0, 'order_seed': 1}, level))

    def test_service_ruleset_keeps_feet_below_the_front_panel(self):
        k = self.make('level-2')
        front = k.rules.cabinet_front_clearance
        self.assertGreater(front, WALK_CLEARANCE)
        # counter14 at (5,4) has open floor to its south; the wall row keeps the ordinary clearance.
        self.assertFalse(k.nav.walkable_point((5, 4.5+front-.01)))
        self.assertTrue(k.nav.walkable_point((5, 4.5+front)))
        wall = next(b for b, cell in zip(k.nav.walk_boxes, sorted(k.nav.blocked)) if cell == (5, 0))
        self.assertAlmostEqual(wall[3], .5+WALK_CLEARANCE)
        # The published walk boxes carry the same edge, so the client prediction agrees.
        boxes = k.snapshot()['map']['walk_boxes']
        side = k.rules.cabinet_clearance[1]
        self.assertIn([5-.5-side, 3.3, 5+.5+side, 4.5+front], [[round(v, 9) for v in b] for b in boxes])

    def test_both_chefs_walking_north_stop_below_the_panel(self):
        for who in ('human', 'jeff'):
            with self.subTest(who=who):
                k = self.make('level-2')
                other = 'jeff' if who == 'human' else 'human'
                k.positions[other] = (10., 6.)
                k.positions[who] = (5., 6.)
                k.set_manual(who, 0, -1)
                k.advance(1)
                self.assertAlmostEqual(k.positions[who][1], 4.5+k.rules.cabinet_front_clearance, places=4)
                k.assert_invariants()

    def test_board_sides_keep_the_body_width_too(self):
        # Level 1's board column used to let feet touch its sides (half the body on the board).
        k = self.make('level-1')
        side = k.rules.cabinet_clearance[1]
        k.positions['jeff'] = (10., 4.)
        k.positions['human'] = (2., 4.)
        k.set_manual('human', 1, 0)
        k.advance(1)
        self.assertAlmostEqual(k.positions['human'][0], 3.5 - side, places=4)
        self.assertAlmostEqual(k.operation_point('b2', (3, 4))[0], 3.5 - side)

    def test_every_operation_point_remains_reachable(self):
        for level in ('level-1', 'level-2', 'level-3'):
            k = self.make(level)
            for key, e in k.equipment.items():
                with self.subTest(level=level, station=key):
                    point = k.operation_point(key, tuple(e['access']))
                    self.assertTrue(k.nav.walkable_point(point))
                    k.nav.shortest_path(tuple(map(float, k.positions['human'])), point)

    def test_legacy_rules_keep_the_accepted_clearance(self):
        config = {key: value for key, value in load_config().items() if key != 'level_id'}
        k = SpatialKitchen(config | {'level': 2, 'spawn_seed': 0, 'order_seed': 1})
        self.assertEqual(k.resolved['level']['id'], 'legacy-level-2')
        self.assertIsNone(k.rules.cabinet_front_clearance)
        self.assertTrue(k.nav.walkable_point((5, 4.5+WALK_CLEARANCE)))


if __name__ == '__main__':
    unittest.main()
