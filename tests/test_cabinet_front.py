"""Feet stay south of a cabinet's front panel, for both chefs and every kind of movement."""
import unittest

from kitchen import Food, load_config
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

    def test_stand_points_are_where_walking_toward_the_face_stops(self):
        # South faces used to stand 0.27 cells back and step away when work began.
        for level in ('level-1', 'level-2', 'level-3'):
            k = self.make(level)
            self.assertTrue(k.at_walk_limit)
            for key, e in k.equipment.items():
                if e.get('reach') == 'corner':continue
                for n in k.nav.neighbors(tuple(e['cell'])):
                    with self.subTest(level=level, station=key, access=n):
                        dx, dy = e['cell'][0]-n[0], e['cell'][1]-n[1]
                        start = (float(n[0]), float(n[1]))
                        stop = k._wall_limited(start, (start[0]+dx, start[1]+dy))
                        spot = k.operation_point(key, n)
                        axis = 0 if dx else 1
                        self.assertLessEqual(abs(spot[axis]-stop[axis]), .011)

    def test_a_chef_already_at_a_face_works_in_place(self):
        for who in ('human', 'jeff'):
            with self.subTest(who=who):
                k = self.make('level-2')
                other = 'jeff' if who == 'human' else 'human'
                k.positions[other] = (10., 5.)
                # South of counter 14, walked up to it slightly off centre, facing it.
                k.positions[who] = (5.3, 4.5+k.rules.cabinet_front_clearance)
                k.facing[who] = 'up'
                k.stations['counter14'].food = Food('T', 'raw', ingredient='tomato')
                self.assertTrue(k.at_station_face(who, 'counter14'))
                action = k.facing_interaction(who)[1]
                self.assertEqual(action.kind, 'take_counter')
                before = k.positions[who]
                self.assertTrue(k.start(who, action)[0])
                self.assertEqual(k.chefs[who].job.travel, 0)
                k.advance(.5)
                self.assertEqual(k.positions[who], before)
                self.assertEqual(k.chefs[who].hand.id, 'T')


if __name__ == '__main__':
    unittest.main()
