"""Overcooked-style player controls: Space for the hands, E to use, both on what the chef faces."""
import math
import time
import unittest

from kitchen import Food, load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from web_server import GameSession
from test_web import Client, FakeJournal


def kitchen():
    return SpatialKitchen(level_config(load_config() | {'spawn_seed': 0, 'order_seed': 1}, 2))


class FacingControlTests(unittest.TestCase):
    def test_space_and_e_both_chop_and_wash(self):
        k = kitchen()
        k.positions['human'] = (4., 6.); k.facing['human'] = 'down'
        k.stations['b1'].food = Food('L', 'raw', ingredient='lettuce')
        self.assertEqual(k.facing_interaction('human', 'hands')[1].kind, 'chop')
        self.assertEqual(k.facing_interaction('human', 'use')[1].kind, 'chop')
        k.positions['human'] = (11., 3.); k.facing['human'] = 'right'
        k.stations['sink'].food = Food('D1', 'dirty_plate')
        self.assertEqual(k.facing_interaction('human', 'hands')[1].kind, 'wash')

    def test_a_station_diagonally_ahead_is_picked_never_one_beside(self):
        # Overcooked 2: the stations around the chef's cell that lie ahead are scored by the aim. Floor
        # straight ahead, the bread box diagonally ahead is picked; counter 17 beside (up) never is.
        k = kitchen()
        k.positions['human'] = (7., 2.3); k.face('human', -1, 0)
        self.assertEqual(k.selectable_stations('human'), ['bread'])
        self.assertEqual(k.facing_interaction('human', 'hands')[1].key, 'fetch bread')
        k.face('human', 1, 0)
        self.assertNotIn('counter17', k.selectable_stations('human'))

    def test_a_stick_leaning_toward_a_diagonal_keeps_the_station_straight_ahead(self):
        # Player report: under the tomato box (level 2), stick up but a little left, and the lettuce box
        # up-left was framed. Overcooked 2's raw offset score lets a diagonal win at any lean; here the
        # straight station holds until the aim is about 30 degrees off.
        k = kitchen()
        k.positions['human'] = (5., 2.)
        for degrees, want in ((0, 'tomato'), (15, 'tomato'), (28, 'tomato'), (32, 'lettuce'), (45, 'lettuce')):
            r = math.radians(degrees)
            k.face('human', -math.sin(r), -math.cos(r))
            self.assertEqual(k.selected_station('human'), want, degrees)

    def test_the_station_under_the_front_point_is_the_target(self):
        k = SpatialKitchen(level_config(load_config() | {'spawn_seed': 0, 'order_seed': 1}, 1))
        k.positions['jeff'] = (10., 6.)
        # Level 1 boards: b1 (4,3), b2 (4,4), b3 (4,5). Facing sideways the front point is at hand height
        # (SIDE_HAND_RISE above the feet): feet on b2's row centre, on the neighbouring tile's centre, or a
        # little below it target b2; feet high enough that the hands are level with b1 target b1.
        for x, y in ((3.15, 4.), (3., 4.), (3.15, 4.2), (3.15, 4.4)):
            k.positions['human'] = (x, y); k.facing['human'] = 'right'
            self.assertEqual(k.selected_station('human'), 'b2', (x, y))
        for y in (3.6, 3.4):
            k.positions['human'] = (3.15, y)
            self.assertEqual(k.selected_station('human'), 'b1', y)
        # Every side of b2 that has floor, pressed against it.
        k.positions['human'] = (3.15, 4.); k.facing['human'] = 'right'
        self.assertEqual(k.selected_station('human'), 'b2')
        k.positions['human'] = (4.85, 4.); k.facing['human'] = 'left'
        self.assertEqual(k.selected_station('human'), 'b2')
        # Too far back: nothing is targeted, and the held item is not dropped instead.
        k.positions['human'] = (2.55, 4.); k.facing['human'] = 'right'
        k.chefs['human'].hand = Food('held', 'raw', ingredient='beef')
        self.assertIsNone(k.selected_station('human'))
        self.assertIsNone(k.facing_interaction('human', 'hands')[1])

    def test_every_station_side_targets_its_station(self):
        # All levels, every station type and every floor side: pressed against it at the walk limit, or
        # on the neighbouring tile's centre, facing it, the front point picks that station.
        steps = {(0, 1): 'down', (0, -1): 'up', (1, 0): 'right', (-1, 0): 'left'}
        for level in (1, 2, 3):
            k = SpatialKitchen(level_config(load_config() | {'spawn_seed': 0, 'order_seed': 1}, level))
            k.positions['jeff'] = (-5., -5.)
            for key, e in k.equipment.items():
                if e.get('reach') == 'corner':
                    continue
                for cell in e.get('cells', [e['cell']]):
                    for access in k.nav.neighbors(cell):
                        facing = steps[(cell[0] - access[0], cell[1] - access[1])]
                        for spot in (k.operation_point(key, access), access):
                            with self.subTest(level=level, station=key, side=access, spot=spot):
                                k.positions['human'] = spot; k.facing['human'] = facing
                                self.assertEqual(k.selected_station('human'), key)

    def test_the_user_case_targets_b2_and_never_falls_back_to_b1(self):
        # Round bcb4a7e9: standing west of the column at b2's height with b2 empty and raw beef on b1,
        # Space chopped b1 (the beside fallback) and walked the chef there. Now b2 is the target, nothing
        # happens there, and the chef stays put.
        k = SpatialKitchen(level_config(load_config() | {'spawn_seed': 0, 'order_seed': 1}, 1))
        k.positions['jeff'] = (10., 6.)
        k.stations['b1'].food = Food('F1', 'raw', ingredient='beef')
        k.positions['human'] = (3.15, 4.); k.facing['human'] = 'right'
        focus, action = k.facing_interaction('human', 'hands')
        self.assertEqual(focus, 'b2')
        self.assertIsNone(action)
        self.assertIsNone(k.facing_interaction('human', 'use')[1])
        k.stations['b2'].food = Food('F2', 'raw', ingredient='beef')
        focus, action = k.facing_interaction('human', 'use')
        self.assertEqual((focus, action.key), ('b2', 'chop b2'))

    def test_the_knife_and_the_target_agree_at_the_users_spot(self):
        # User screenshot 2026-10-06: feet on the b1/b2 seam, slightly low, facing right. The knife is drawn
        # level with b1, so b1 is the target (it used to be b2 while the knife pointed at b1). With the feet
        # low enough the hands are level with b2, and b2 is the target. Work starts with a short sideways slide
        # onto that board's row centre, never toward the board.
        k = SpatialKitchen(level_config(load_config() | {'spawn_seed': 0, 'order_seed': 1}, 1))
        k.positions['jeff'] = (10., 6.)
        k.stations['b1'].food = Food('F1', 'raw', ingredient='beef')
        k.stations['b2'].food = Food('F2', 'raw', ingredient='beef')
        for here, board in (((3.15, 3.55), 'b1'), ((3.15, 4.), 'b2')):
            k.stop('human')
            k.positions['human'] = here; k.face('human', 1, 0)
            focus, action = k.facing_interaction('human', 'use')
            self.assertEqual((focus, action.key), (board, 'chop ' + board), here)
            self.assertTrue(k.start('human', action)[0])
            k.advance(.5)
            self.assertEqual(k.positions['human'], (here[0], k.equipment[board]['cell'][1]))
        # Jeff, routed to a side, stands on the row centre and his hands stay level with the same board.
        for board in ('b1', 'b2', 'b3'):
            k.stop('jeff')
            k.positions['jeff'] = (k.equipment[board]['cell'][0] - .85, k.equipment[board]['cell'][1]); k.facing['jeff'] = 'right'
            self.assertEqual(k.selected_station('jeff'), board)

    def test_the_player_works_where_they_stand_after_centring(self):
        # Work starts where the player stands, after a sideways slide of at most 0.6 cells (about 0.1 s) onto
        # the station's centre line; the distance to the station and the facing never change.
        k = SpatialKitchen(level_config(load_config() | {'spawn_seed': 0, 'order_seed': 1}, 1))
        k.positions['jeff'] = (10., 6.)
        k.stations['b2'].food = Food('F2', 'raw', ingredient='beef')
        for here in ((3., 4.), (3.15, 4.4)):
            k.stop('human')
            k.positions['human'] = here; k.facing['human'] = 'right'
            self.assertTrue(k.start('human', k.facing_interaction('human', 'use')[1])[0])
            k.advance(.15)
            self.assertEqual(k.positions['human'], (here[0], 4.))
            self.assertTrue(k.chefs['human'].job.working)
            self.assertEqual(k.facing['human'], 'right')
        # Too far off the line (or with the partner in the way) it works where it stands.
        k.stop('human');k.positions['human'] = (3.15, 4.4);k.positions['jeff'] = (3.15, 4.)
        self.assertIsNone(k._centred('human', 'b2'))

    def test_facing_a_busy_station_never_drops_the_held_item(self):
        k = kitchen()
        k.positions['human'] = (5., 5.); k.facing['human'] = 'up'
        k.chefs['human'].hand = Food('held', 'raw', ingredient='tomato')
        k.stations['counter14'].food = Food('other', 'raw', ingredient='lettuce')
        focus, action = k.facing_interaction('human', 'hands')
        self.assertEqual(focus, 'counter14')
        self.assertIsNone(action)
        k.facing['human'] = 'down'
        self.assertEqual(k.facing_interaction('human', 'hands')[1].kind, 'drop')

    def test_corner_counter_is_reached_by_facing_its_side(self):
        k = kitchen()
        k.positions['human'] = (2., 2.); k.facing['human'] = 'up'
        k.chefs['human'].hand = Food('held', 'raw', ingredient='tomato')
        self.assertEqual(k.facing_interaction('human', 'hands')[1].target, 'counter9')
        # A full counter9 does not hand Space to the corner: what is highlighted is what Space acts on.
        k.stations['counter9'].food = Food('other', 'raw', ingredient='lettuce')
        self.assertEqual(k.facing_interaction('human', 'hands')[0], 'counter9')
        # Aiming up-left picks the corner counter.
        k.face('human', -1, -1)
        self.assertEqual(k.facing_interaction('human', 'hands')[1].target, 'counter_corner1')
        k.facing['human'] = 'down'
        self.assertNotEqual(k.facing_interaction('human', 'hands')[0], 'counter_corner1')

    def test_e_throws_straight_ahead_or_to_the_partner_in_line(self):
        k = kitchen()
        k.positions['human'] = (3., 5.); k.facing['human'] = 'right'
        k.chefs['human'].hand = Food('T', 'raw', ingredient='tomato')
        k.positions['jeff'] = (6., 5.)
        action = k.forward_throw('human')
        self.assertEqual(action.kind, 'throw')
        self.assertLessEqual(math.dist(action.expected[2:4], k.positions['jeff']), k.rules.catch_radius)
        k.positions['jeff'] = (10., 2.)
        action = k.forward_throw('human')
        self.assertEqual(tuple(action.expected[2:4]), (3. + k.throw_range('human'), 5.))
        k.chefs['human'].hand = None
        self.assertIsNone(k.forward_throw('human'))


class ForwardThrowHttpTests(unittest.TestCase):
    def test_e_throws_through_the_web_session(self):
        g = GameSession(config=level_config(load_config(), 2), kitchen_factory=SpatialKitchen,
                        client_factory=Client, journal_factory=FakeJournal)
        self.addCleanup(g.close)
        self.assertEqual(g.command('/api/start', {'game_id': g.game_id, 'request_id': 's', 'speed': .75})[0], 200)
        k = g.k
        k.positions['human'] = (3., 5.); k.facing['human'] = 'right'
        k.chefs['human'].hand = Food('T', 'raw', ingredient='tomato')
        k.positions['jeff'] = (10., 2.)
        status, body = g.command('/api/interact', {'game_id': g.game_id, 'request_id': 'e', 'expected_item': 'T', 'mode': 'use'})
        self.assertEqual(status, 200, body)
        for _ in range(20):k.advance(.05)
        self.assertIsNone(k.chefs['human'].hand)
        self.assertTrue(any(item.food.id == 'T' for item in k.ground.values()))


class AimedThrowTests(unittest.TestCase):
    """Hold Space to aim: the throw follows the aimed direction, not the facing."""
    def test_an_aimed_throw_follows_its_direction_or_reaches_the_partner_that_way(self):
        k = kitchen()
        k.positions['human'] = (3., 5.); k.facing['human'] = 'right'
        k.chefs['human'].hand = Food('T', 'raw', ingredient='tomato')
        k.positions['jeff'] = (10., 2.)
        action = k.aimed_throw('human', (1, -1))
        x, y = action.expected[2:4]
        self.assertGreater(x, 3.)
        self.assertLess(y, 5.)
        self.assertAlmostEqual(x - 3., 5. - y, places=6)  # along the diagonal, clipped by walls or range
        k.positions['jeff'] = (3., 7.)
        action = k.aimed_throw('human', (0, 1))
        self.assertLessEqual(math.dist(action.expected[2:4], k.positions['jeff']), k.rules.catch_radius)
        self.assertIsNone(k.aimed_throw('human', (0, 0)))

    def test_the_web_session_throws_along_a_direction(self):
        g = GameSession(config=level_config(load_config(), 2), kitchen_factory=SpatialKitchen,
                        client_factory=Client, journal_factory=FakeJournal)
        self.addCleanup(g.close)
        self.assertEqual(g.command('/api/start', {'game_id': g.game_id, 'request_id': 's', 'speed': .75})[0], 200)
        k = g.k
        k.positions['human'] = (3., 5.); k.facing['human'] = 'right'
        k.chefs['human'].hand = Food('T', 'raw', ingredient='tomato')
        k.positions['jeff'] = (10., 2.)
        bad = g.command('/api/throw', {'game_id': g.game_id, 'request_id': 'b', 'expected_item': 'T', 'direction': [0, 0]})
        self.assertEqual(bad[0], 400)
        status, body = g.command('/api/throw', {'game_id': g.game_id, 'request_id': 'a', 'expected_item': 'T', 'direction': [0, 1]})
        self.assertEqual(status, 200, body)
        for _ in range(20):k.advance(.05)
        self.assertIsNone(k.chefs['human'].hand)
        landed = next(item.location for item in k.ground.values() if item.food.id == 'T')
        self.assertEqual(int(landed.split('_')[1]), 3)  # straight down from x = 3, not to the right
        self.assertGreater(int(landed.split('_')[2]), 5)


class ShortActionMoveTests(unittest.TestCase):
    def test_a_move_during_a_short_take_starts_after_it(self):
        g = GameSession(config=level_config(load_config(), 2), kitchen_factory=SpatialKitchen,
                        client_factory=Client, journal_factory=FakeJournal)
        self.addCleanup(g.close)
        def cmd(path, **kw):
            return g.command('/api/' + path, {'game_id': g.game_id, 'request_id': str(time.monotonic_ns()), **kw})
        self.assertEqual(cmd('start', speed=.75)[0], 200)
        k = g.k
        k.positions['human'] = (5., 5.); k.facing['human'] = 'up'
        k.stations['counter14'].food = Food('T', 'raw', ingredient='tomato')
        self.assertEqual(cmd('interact', expected_item=None)[0], 200)
        self.assertEqual(k.chefs['human'].job.action.kind, 'take_counter')
        status, body = g.command('/api/move', {'game_id': g.game_id, 'dx': 0, 'dy': 1, 'seq': 1})
        self.assertEqual((status, body.get('deferred')), (200, True))
        self.assertEqual(k.manual['human'], (0., 0.))
        g._advance_ticks(.4, time.monotonic())
        self.assertEqual(k.chefs['human'].hand.id, 'T')
        self.assertEqual(k.manual['human'], (0., 1.))

    def test_a_move_still_interrupts_chopping(self):
        g = GameSession(config=level_config(load_config(), 2), kitchen_factory=SpatialKitchen,
                        client_factory=Client, journal_factory=FakeJournal)
        self.addCleanup(g.close)
        def cmd(path, **kw):
            return g.command('/api/' + path, {'game_id': g.game_id, 'request_id': str(time.monotonic_ns()), **kw})
        cmd('start', speed=.75)
        k = g.k
        k.positions['human'] = (4., 6.); k.facing['human'] = 'down'
        k.stations['b1'].food = Food('L', 'raw', ingredient='lettuce')
        self.assertEqual(cmd('interact', expected_item=None, mode='use')[0], 200)
        g._advance_ticks(.5, time.monotonic())
        self.assertEqual(k.chefs['human'].job.action.kind, 'chop')
        status, body = g.command('/api/move', {'game_id': g.game_id, 'dx': 0, 'dy': -1, 'seq': 1})
        self.assertNotIn('deferred', body)
        self.assertIsNone(k.chefs['human'].job)


if __name__ == '__main__':
    unittest.main()
