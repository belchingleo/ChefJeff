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

    def test_a_station_beside_is_used_when_nothing_is_ahead(self):
        k = kitchen()
        # Floor ahead; the empty counter 17 beside has nothing to do, the bread box diagonally ahead does.
        k.positions['human'] = (7., 2.); k.facing['human'] = 'left'
        self.assertEqual(k.facing_interaction('human', 'hands')[1].key, 'fetch bread')
        # Never behind the chef.
        k.facing['human'] = 'right'
        self.assertIsNone(k.facing_interaction('human', 'hands')[1])
        k.positions['human'] = (6., 2.); k.facing['human'] = 'down'
        self.assertNotEqual(k.facing_interaction('human', 'hands')[0], 'bread')

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
        k.stations['counter9'].food = Food('other', 'raw', ingredient='lettuce')
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
