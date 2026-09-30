"""Unified event stream and Session bundle: linkage, clocks, replay and privacy."""
import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import config_contract as cc
import schema_check
from kitchen import Food, Kitchen, load_config, replay
from session_record import read_bundle, replay_bundle
from spatial_kitchen import SpatialKitchen, tile_key
from test_jev import NoKeyClient
from test_web import FakeJournal

SECRET = 'unit-test-not-a-real-key'


class Clock:
    def __init__(self):
        self.now = 1000.

    def __call__(self):
        return self.now


class BundleTests(unittest.TestCase):
    def play(self, reply='fetch', seconds=40):
        from web_server import GameSession
        tmp = tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        g = GameSession(config=load_config() | {'order_seed': 1, 'spawn_seed': 0},
                        client_factory=lambda c: NoKeyClient(c, reply), journal_factory=FakeJournal,
                        kitchen_factory=SpatialKitchen)
        g.bundle_root = Path(tmp.name)
        clock = Clock()
        cmd = lambda path, **body: g.command('/api/' + path, {'game_id': g.game_id, 'request_id': uuid.uuid4().hex, **body})
        with patch('jev.time.monotonic', clock), patch('web_server.time.monotonic', clock):
            self.assertEqual(cmd('start', speed=.75)[0], 200)
            for step in range(int(seconds / .1)):
                clock.now += .1
                g.last_seen = clock.now
                g.tick(clock.now)
                deadline = time.monotonic() + .5
                while g.ai.inflight and g.ai.q.empty() and time.monotonic() < deadline:
                    time.sleep(.0005)
                if step == 20:
                    cmd('communicate', code='cook')
                    cmd('bookmark')
                if step == 30:
                    self.assertEqual(cmd('pause')[0], 200)
                    self.assertEqual(cmd('resume')[0], 200)
            self.assertEqual(cmd('end')[0], 200)
        folder = g.bundle_root / g.game_id
        return g, folder

    def test_bundle_matches_schemas_and_is_replayable(self):
        g, folder = self.play()
        bundle = read_bundle(folder)
        session = bundle['session']
        self.assertEqual(schema_check.validate(session, 'session.schema.json'), [])
        for event in bundle['events']:
            self.assertEqual(schema_check.validate(event, 'event.schema.json'), [], event)
        self.assertEqual([e['seq'] for e in bundle['events']], list(range(1, len(bundle['events']) + 1)))
        self.assertEqual(cc.verify_frozen(bundle['resolved']), [])
        self.assertEqual(session['config_hash'], bundle['resolved']['config_hash'])
        self.assertEqual(session['recording_meta']['replay']['level'], 'engine_events_verified')
        again = replay_bundle(folder)
        self.assertEqual([(e['seq'], e['kind'], e['game_time_ms']) for e in again.events],
                         [(e['seq'], e['kind'], e['game_time_ms']) for e in g.k.events])
        self.assertEqual(session['outcome']['end_reason'], 'aborted')
        for artifact in session['artifacts']:
            import hashlib
            self.assertEqual(hashlib.sha256((folder / artifact['path']).read_bytes()).hexdigest(), artifact['sha256'])

    def test_request_choice_acceptance_and_execution_are_linked(self):
        g, folder = self.play()
        events = read_bundle(folder)['events']
        requests = {e['request_id']: e for e in events if e['type'] == 'ai_request'}
        responses = [e for e in events if e['type'] == 'ai_response']
        self.assertTrue(requests and responses)
        starts = {e['action_id']: e for e in events if e['type'] == 'action_start' and e.get('actor_id') == 'jeff'}
        linked = 0
        for response in responses:
            request = requests[response['request_id']]
            self.assertLess(request['seq'], response['seq'])
            self.assertIn(response['payload']['choice'], request['payload']['candidates'])
            self.assertLessEqual(request['payload']['observed_state_seq'], response['payload']['accepted_engine_seq'])
            if response.get('action_id'):
                self.assertIn(response['action_id'], starts)
                self.assertEqual(starts[response['action_id']]['payload']['action'], response['payload']['choice'])
                linked += 1
        self.assertGreater(linked, 0)
        payloads = read_bundle(folder)['model_requests']
        import hashlib
        for row in payloads:
            self.assertEqual(hashlib.sha256(cc.canonical(row['payload']).encode()).hexdigest(), row['sha256'])
            self.assertEqual(requests[row['request_id']]['payload']['payload_sha256'], row['sha256'])

    def test_session_level_facts_are_recorded_once_with_both_clocks(self):
        g, folder = self.play()
        events = read_bundle(folder)['events']
        types = [e['type'] for e in events]
        for kind in ('start', 'player_message', 'bookmark', 'pause', 'resume', 'end'):
            self.assertIn(kind, types)
        self.assertEqual(types.count('end'), 1)
        wall = [e['elapsed_wall_ms'] for e in events]
        self.assertEqual(wall, sorted(wall))
        self.assertTrue(all(e['clock_id'] == 'server_monotonic' for e in events))

    def test_no_credentials_or_scores_in_the_bundle(self):
        g, folder = self.play()
        for path in folder.iterdir():
            text = path.read_text()
            self.assertNotIn(SECRET, text, path.name)
            self.assertNotIn('Authorization', text, path.name)
        derived = read_bundle(folder)['session']['derived']
        self.assertFalse([k for k in derived if 'score' in k or 'quality' in k])

    def test_hosted_style_sessions_keep_no_bundle_and_no_payloads(self):
        from web_server import GameSession
        g = GameSession(config=load_config() | {'order_seed': 1, 'spawn_seed': 0},
                        client_factory=lambda c: NoKeyClient(c), journal_factory=FakeJournal, kitchen_factory=SpatialKitchen)
        self.assertIsNone(g.bundle_root)
        g.command('/api/start', {'game_id': g.game_id, 'request_id': 'r1', 'speed': .75})
        g.ai.poll()
        self.assertFalse(g.session_log.keep_payloads)
        self.assertEqual(g.session_log.payloads, [])


class CollaborationFactTests(unittest.TestCase):
    def kitchen(self):
        k = SpatialKitchen(load_config() | {'level': 1, 'order_seed': 1, 'spawn_seed': 0, 'round_seconds': 500,
                                            'order_patience': 450, 'order_interval': 100})
        k.stations['b1'].food = Food('shared-food')
        k.positions.update(human=(4, 2.49), jeff=(3.15,3.3))
        return k

    def test_shared_work_join_leave_and_overlap(self):
        k = self.kitchen()
        k.command('human', 'chop b1');k.advance(.01)
        k.command('jeff', 'chop b1');k.advance(.5)
        joins = [e for e in k.events if e['kind'] == 'shared_work_join']
        self.assertEqual(len(joins), 1);self.assertEqual(joins[0]['actor'], 'jeff');self.assertEqual(joins[0]['workers'], 2)
        k.stop('human')
        leaves = [e for e in k.events if e['kind'] == 'shared_work_leave']
        self.assertEqual(len(leaves), 1);self.assertEqual(leaves[0]['actor'], 'human')
        self.assertGreater(k.shared_overlap['b1'], .3)
        k.advance(10)
        self.assertEqual(k.stations['b1'].food.stage, 'chopped')

    def test_opportunity_is_distinguishable_from_choice(self):
        k = self.kitchen()
        k.command('human', 'chop b1');k.advance(.01)
        offered = [a for a in k.actions('jeff') if a.kind == 'chop' and a.target == 'b1']
        self.assertTrue(offered)  # the environment offers joining ...
        k.advance(1.)
        self.assertEqual([e for e in k.events if e['kind'] == 'shared_work_join'], [])  # ... nobody chose it

    def test_handoff_is_linked_from_throw_to_catch(self):
        k = SpatialKitchen(load_config() | {'level': 1, 'order_seed': 1, 'spawn_seed': 0})
        k.chefs['human'].hand = Food('F9', 'raw')
        k.positions.update(human=(4., 6.), jeff=(8., 6.))
        action = k.throw_action('human', k.positions['jeff'], 'throw partner')
        self.assertTrue(k.start('human', action)[0])
        k.advance(2.)
        thrown = next(e for e in k.events if e['kind'] == 'thrown')
        landing = next(e for e in k.events if e['kind'] in ('caught', 'landed') and e.get('item') == 'F9')
        self.assertEqual(landing['handoff_id'], thrown['handoff_id'])
        self.assertIn(landing.get('outcome'), ('caught', 'landed_floor', 'landed_station'))


class ReplayTests(unittest.TestCase):
    def test_same_rules_and_inputs_replay_key_results(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import fingerprint
        k = SpatialKitchen(cc.load_level('level-3', seeds={'orders': 7, 'spawn': 0}))
        import reference_policy
        for step in range(3000):
            if step % 10 == 0:
                for who, role in (('human', 'assembler'), ('jeff', 'cook')):
                    action = reference_policy.choose(k, who, role)
                    if action:
                        k.start(who, action)
            k.advance(.05)
            if k.ended:
                break
        again = replay(SpatialKitchen, k.resolved, json.loads(json.dumps(k.inputs)))
        self.assertEqual([(e['kind'], e['game_time_ms']) for e in again.events], [(e['kind'], e['game_time_ms']) for e in k.events])
        self.assertEqual((again.served, again.money), (k.served, k.money))
        self.assertGreater(k.served, 0)

    def test_state_edits_outside_inputs_are_reported_as_partial(self):
        from session_record import SessionLog

        class Session:
            game_id = uuid.uuid4().hex
        s = Session();s.k = Kitchen(cc.load_level('level-1', seeds={'orders': 1, 'spawn': 0}))
        log = SessionLog(s)
        s.k.advance(1.)
        self.assertEqual(log.replay_check()['level'], 'engine_events_verified')
        s.k.stations['b1'].food = Food('injected');s.k.ignite('b1')  # not an engine input
        s.k.advance(1.)
        self.assertEqual(log.replay_check()['level'], 'replay_partial')


if __name__ == '__main__':
    unittest.main()
