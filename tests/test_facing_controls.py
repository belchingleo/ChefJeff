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
    def test_space_takes_from_a_board_and_e_chops(self):
        k = kitchen()
        k.positions['human'] = (4., 6.); k.facing['human'] = 'down'
        k.stations['b1'].food = Food('L', 'raw', ingredient='lettuce')
        self.assertEqual(k.facing_interaction('human', 'hands')[1].kind, 'take_board')
        self.assertEqual(k.facing_interaction('human', 'use')[1].kind, 'chop')

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
