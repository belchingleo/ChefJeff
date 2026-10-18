"""Overcooked-style local movement: the browser walks the player's chef and reports where it is."""
import math
import time
import unittest

from kitchen import Food, load_config, replay
from levels import level_config
from spatial_kitchen import SpatialKitchen, REPORT_MAX_LEAD, REPORT_SPEED_MARGIN, REPORT_STALL
from web_server import GameSession
from test_web import Client, FakeJournal


def kitchen(level=1):
    return SpatialKitchen(level_config(load_config() | {'spawn_seed': 0, 'order_seed': 1, 'round_seconds': 500}, level))


def free_run(k, who='human', shortest=False):
    """A straight direction with clear floor from the spawn (the longest, or the shortest to a wall)."""
    start, runs = k.positions[who], []
    for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        n = 0
        while n < 60 and k.nav.clear_walk_line(start, (start[0]+d[0]*(n+1)*.1, start[1]+d[1]*(n+1)*.1)):
            n += 1
        runs.append((n, d))
    n, d = min(r for r in runs if r[0] > 2) if shortest else max(runs)
    return d, n*.1-.05


class EngineTests(unittest.TestCase):
    def test_late_reports_are_followed_to_the_same_point_and_replay(self):
        k = kitchen(); start = k.positions['human']; d, length = free_run(k)
        walk, sent = k.rules.walk_speed, []
        for i in range(80):
            t = i*.05; s = min(t*walk, length); here = (start[0]+d[0]*s, start[1]+d[1]*s)
            if i % 2 == 0:
                sent.append((t+.3, here))  # 0.3 s late
            while sent and sent[0][0] <= t+1e-9:
                self.assertTrue(k.report_position('human', *sent.pop(0)[1], k.resync['human']))
            k.advance(.05)
        self.assertLess(math.dist(k.positions['human'], here), 1e-6)
        self.assertEqual(k.resync['human'], 0)
        again = replay(SpatialKitchen, k.resolved, k.inputs)
        self.assertEqual(again.positions, k.positions)
        self.assertEqual(again.resync, k.resync)

    def test_held_direction_turns_but_does_not_walk_a_reporting_chef(self):
        k = kitchen(); start = k.positions['human']; d, _ = free_run(k)
        k.report_position('human', *start, 0)
        k.set_manual('human', *d)
        for _ in range(10):
            k.advance(.05)
        self.assertEqual(k.positions['human'], start)
        self.assertEqual(k.facing['human'], {(1, 0): 'right', (-1, 0): 'left', (0, 1): 'down', (0, -1): 'up'}[d])

    def test_speed_is_bounded_and_far_reports_resync(self):
        k = kitchen(); start = k.positions['human']; d, length = free_run(k)
        far = (start[0]+d[0]*(REPORT_MAX_LEAD+.1), start[1]+d[1]*(REPORT_MAX_LEAD+.1))
        self.assertFalse(k.report_position('human', *far, 0))
        self.assertEqual((k.resync['human'], k.positions['human']), (1, start))
        self.assertFalse(k.report_position('human', *start, 0), 'a report from before the resync is ignored')
        walked = 0.
        for _ in range(int(length/.4)):
            here = k.positions['human']
            k.report_position('human', here[0]+d[0]*2, here[1]+d[1]*2, 1)
            k.advance(.1)
            walked = math.dist(start, k.positions['human'])
        seconds = int(length/.4)*.1
        self.assertLessEqual(walked, k.rules.walk_speed*REPORT_SPEED_MARGIN*seconds+2.+1e-6)

    def test_a_blocked_report_resyncs_after_a_short_stall(self):
        k = kitchen(); spawn = k.positions['human']; d, length = free_run(k, shortest=True)
        start = k.positions['human'] = (spawn[0]+d[0]*(length-.3), spawn[1]+d[1]*(length-.3))
        wall = (start[0]+d[0]*.9, start[1]+d[1]*.9)  # beyond the wall
        self.assertFalse(k.nav.clear_walk_line(start, wall))
        self.assertTrue(k.report_position('human', *wall, 0))
        for _ in range(int(REPORT_STALL/.05)+12):
            k.advance(.05)
        self.assertEqual(k.resync['human'], 1)
        self.assertTrue(k.nav.walkable_point(k.positions['human']))
        self.assertTrue(any(e['kind'] == 'position_resync' and e['reason'] == 'blocked' for e in k.events))

    def test_a_push_resyncs_the_reporting_chef(self):
        k = kitchen(); h = k.positions['human']
        k.report_position('human', *h, 0)
        k.positions['jeff'] = (h[0], h[1]-.6)
        k._move_with_chef_contact('jeff', (h[0], h[1]+.2))
        self.assertGreater(k.resync['human'], 0)


class WebTests(unittest.TestCase):
    def make(self):
        g = GameSession(kitchen_factory=SpatialKitchen, client_factory=Client, journal_factory=FakeJournal)
        self.addCleanup(g.close)
        self.assertEqual(self.command(g, 'start')[0], 200)
        return g

    def command(self, g, path, **extra):
        return g.command('/api/'+path, {'game_id': g.game_id, 'request_id': str(time.monotonic_ns()), **extra})

    def test_position_requests_are_validated_and_ordered(self):
        g = self.make(); here = list(g.k.positions['human'])
        for bad in ({'seq': 1, 'base': 0}, {'seq': 1, 'base': 0, 'at': [1]}, {'seq': 1, 'base': True, 'at': here},
                    {'seq': -1, 'base': 0, 'at': here}, {'seq': 1, 'base': 0, 'at': [float('nan'), 1]}):
            with self.subTest(body=bad):
                self.assertEqual(g.command('/api/position', {'game_id': g.game_id, **bad})[0], 400)
        status, body = g.command('/api/position', {'game_id': g.game_id, 'seq': 5, 'base': 0, 'at': here})
        self.assertEqual((status, body['accepted'], body['resync']), (200, True, 0))
        self.assertTrue(g.command('/api/position', {'game_id': g.game_id, 'seq': 4, 'base': 0, 'at': here})[1]['ignored'])
        self.assertIn('resync', g.public_state()['kitchen']['chefs']['human'])

    def test_an_interaction_targets_from_where_the_browser_drew_the_chef(self):
        g = self.make(); k = g.k
        # Level 1 boards b1 (4,3), b2 (4,4): the engine still has the chef in front of b1,
        # the browser has already walked it to b2's row.
        k.positions.update(human=(3.15, 3.55), jeff=(10., 6.)); k.facing['human'] = 'right'
        k.stations['b2'].food = Food('B', 'raw', ingredient='beef')
        status, _ = self.command(g, 'interact', expected_item=None, at=[3.15, 4.], base=0)
        self.assertEqual(status, 200)
        self.assertEqual(k.chefs['human'].job.action.key, 'chop b2')
        self.assertEqual(self.command(g, 'interact', expected_item=None, at=[3.15], base=0)[0], 400)


class StateReplyTests(unittest.TestCase):
    """Gameplay replies carry the resulting state, numbered so a late poll cannot replace it."""
    def make(self):
        g = GameSession(kitchen_factory=SpatialKitchen, client_factory=Client, journal_factory=FakeJournal)
        self.addCleanup(g.close)
        return g

    def command(self, g, path, **extra):
        return g.command('/api/'+path, {'game_id': g.game_id, 'request_id': str(time.monotonic_ns()), **extra})

    def test_actions_reply_with_the_new_state_and_a_newer_sequence(self):
        g = self.make(); self.assertEqual(self.command(g, 'start')[0], 200)
        first = g.public_state()['state_seq']
        fetch = next(a for a in g.k.actions('human') if a.kind == 'fetch')
        status, body = self.command(g, 'action', action=fetch.key, expected=list(fetch.expected))
        self.assertEqual(status, 200)
        self.assertGreater(body['state']['state_seq'], first)
        self.assertEqual(body['state']['kitchen']['chefs']['human']['action_kind'], 'fetch')
        self.assertGreater(g.public_state()['state_seq'], body['state']['state_seq'])
        # Refused interactions still say why and carry no state (the page then polls).
        status, body = self.command(g, 'interact', expected_item='not-held')
        self.assertEqual(status, 409); self.assertNotIn('state', body)
        # Other commands keep their short replies.
        self.assertNotIn('state', self.command(g, 'pause')[1])


if __name__ == '__main__':
    unittest.main()
