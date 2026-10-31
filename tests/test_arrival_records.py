"""Arrival and throw-aim rows: recorded for both chefs, outside the engine event stream.

Jeff's input must not change, so neither row may touch kitchen events, sequence numbers or
revisions. Synthetic rounds only; no model is called.
"""
import json
import math
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from kitchen import Food, load_config
from session_record import SessionLog, read_bundle
from spatial_kitchen import SpatialKitchen
from test_jev import NoKeyClient
from test_session_record import Clock
from test_web import FakeJournal
import test_research_save_paths as paths


def local_round(record_rows=True):
    """A fixed-seed local round with both chefs acting; returns the session and its bundle."""
    from web_server import GameSession
    tmp = tempfile.TemporaryDirectory()
    g = GameSession(config=load_config() | {'order_seed': 1, 'spawn_seed': 0},
                    client_factory=lambda c: NoKeyClient(c, 'fetch'), journal_factory=FakeJournal,
                    kitchen_factory=SpatialKitchen)
    g.bundle_root = Path(tmp.name)
    clock = Clock()
    cmd = lambda path, **body: g.command('/api/' + path, {'game_id': g.game_id, 'request_id': uuid.uuid4().hex, **body})
    off = {} if record_rows else {'arrival': lambda *a: None, 'throw_aim': lambda *a: None}
    with patch('jev.time.monotonic', clock), patch('web_server.time.monotonic', clock), \
            patch.multiple(SessionLog, **off) if off else patch.object(SessionLog, 'closed', False, create=True):
        assert cmd('start', speed=.75)[0] == 200
        for step in range(300):
            clock.now += .1
            g.last_seen = clock.now
            g.tick(clock.now)
            deadline = time.monotonic() + .5
            while g.ai.inflight and g.ai.q.empty() and time.monotonic() < deadline:
                time.sleep(.0005)
            if step % 25 == 5 and not g.k.chefs['human'].job:
                action = next(x for x in g.k.actions('human') if x.kind not in ('wait', 'continue', 'stop'))
                cmd('action', action=action.key, expected=list(action.expected))
        assert cmd('end')[0] == 200
    bundle = read_bundle(g.bundle_root / g.game_id)
    return g, bundle, tmp


class LocalArrivalTests(unittest.TestCase):
    def test_both_chefs_arrive_and_jeff_receives_exactly_the_same_requests(self):
        g, bundle, tmp = local_round()
        self.addCleanup(tmp.cleanup)
        arrivals = [e for e in bundle['events'] if e['type'] == 'arrival']
        self.assertTrue({'human', 'jeff'} <= {e['actor_id'] for e in arrivals}, arrivals)
        starts = {e['action_id']: e for e in bundle['events'] if e['type'] == 'action_start'}
        for row in arrivals:
            self.assertGreaterEqual(row['game_time_ms'], starts[row['action_id']]['game_time_ms'])
        self.assertFalse([e for e in g.k.events if e.get('kind') in ('arrival', 'throw_aim')])
        g2, bundle2, tmp2 = local_round(record_rows=False)
        self.addCleanup(tmp2.cleanup)
        self.assertFalse([e for e in bundle2['events'] if e['type'] == 'arrival'])
        requests = lambda b: [e['payload']['payload_sha256'] for e in b['events'] if e['type'] == 'ai_request']
        self.assertGreater(len(requests(bundle)), 5)
        self.assertEqual(requests(bundle), requests(bundle2))
        if 'model_requests' in bundle:
            self.assertEqual(json.dumps(bundle['model_requests'], sort_keys=True), json.dumps(bundle2['model_requests'], sort_keys=True))
        self.assertEqual([(e['seq'], e['message']) for e in g.k.events], [(e['seq'], e['message']) for e in g2.k.events])


class HostedArrivalTests(paths.SavePathTests):
    def test_research_rows_link_arrivals_and_mark_throws_at_the_partner_alike(self):
        receipt = self.play()
        with self.game.lock:
            k = self.game.k
            k.chefs['human'].job = None
            k.chefs['human'].hand = Food('human-throw', 'raw', ingredient='beef')
            human, jeff = k.positions['human'], k.positions['jeff']
        direction = [jeff[0] - human[0], jeff[1] - human[1]]
        status, _ = self.command('throw', direction=direction, expected_item='human-throw', at=list(human), base=0)
        with self.game.lock:
            k.advance(2.0)
            k.chefs['jeff'].job = None
            k.chefs['jeff'].hand = Food('jeff-throw', 'raw', ingredient='beef')
            # The record does not depend on who chose it; the engine starts Jeff's partner throw directly.
            self.assertTrue(k.command('jeff', 'throw partner')[0])
            k.advance(2.0)
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        rows = record['events']
        arrivals = [r for r in rows if r['type'] == 'arrival']
        self.assertTrue({'human', 'jeff'} <= {r['actor_id'] for r in arrivals})
        aims = {r['actor_id']: r['payload']['receiver'] for r in rows if r['type'] == 'throw_aim'}
        self.assertEqual(status, 200)
        self.assertEqual(aims.get('human'), 'jeff')
        self.assertEqual(aims.get('jeff'), 'human')
        for r in arrivals:
            self.assertIsNotNone(r['action_id'])
            self.assertEqual(r['source'], 'engine')
        self.assertFalse([e for e in self.game.k.events if e.get('kind') in ('arrival', 'throw_aim')])

    def test_a_throw_in_open_floor_names_no_receiver(self):
        self.play()
        with self.game.lock:
            k = self.game.k
            k.chefs['human'].job = None
            k.chefs['human'].hand = Food('away', 'raw', ingredient='beef')
            human, jeff = k.positions['human'], k.positions['jeff']
        away = [human[0] - jeff[0], human[1] - jeff[1]]
        norm = math.hypot(*away) or 1
        status, _ = self.command('throw', direction=[away[0] / norm, away[1] / norm], expected_item='away', at=list(human), base=0)
        self.assertEqual(status, 200)
        rows = [r for r in self.game.session_log.records if r['type'] == 'throw_aim' and r.get('actor_id') == 'human']
        self.assertEqual(len(rows), 1)
        for row in rows:
            self.assertIsNone(row['payload']['receiver'])


for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(HostedArrivalTests, _name, None)
