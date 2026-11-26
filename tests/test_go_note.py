"""go_note (go-note-v1): a "go X" option says when, on arrival, nothing at X takes what Jeff holds. Facts only.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import unittest
import uuid
from unittest.mock import patch

import features
import go_note
import research_replay
from jev import compose_payload
from kitchen import load_config
from levels import level_config
from research_record import validate_record
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
import test_research_save_paths as paths


def level(name):
    return SpatialKitchen(level_config(load_config(), name))


def do(k, key):
    k.start('jeff', next(a for a in k.actions('jeff') if a.key == key))
    while k.chefs['jeff'].job is not None:
        k.advance(0.05)


def request(k, go):
    options = {**features.compose_options(features.current()), 'walk': True, 'go': go}
    return compose_payload(SpatialJevClient(k.c, key='test-no-credential'), k, k.snapshot(), k.actions('jeff'), [], None,
                           **options)


class GoNoteTests(unittest.TestCase):
    def test_walking_to_serve_with_an_empty_pan_says_nothing_there_takes_it(self):
        k = level('level-4')
        do(k, 'take pot p1')
        on, off = request(k, True), request(k, False)
        held = off['state']['kitchen']['chefs']['jeff']['holding']['meaning']
        self.assertIn('frying pan', held)
        before, after = off['questions']['next_action']['criteria'], on['questions']['next_action']['criteria']
        self.assertEqual(after['go serve'], before['go serve'] + f' (on arrival, nothing there takes the held {held})')
        changed = {key for key in after if after[key] != before[key]}
        self.assertTrue(changed)
        self.assertTrue(all(key.startswith('go ') for key in changed))
        self.assertEqual(on['state'].pop('go_note_version'), go_note.VERSION)
        on['questions']['next_action']['criteria'] = before
        self.assertEqual(json.dumps(on), json.dumps(off))         # nothing else, key order included
        for word in ('should', 'instead', 'better'):              # a fact, not advice
            self.assertNotIn(word, after['go serve'].lower())

    def test_empty_hands_say_nothing_to_do_there(self):
        k = level('level-4')
        criteria = request(k, True)['questions']['next_action']['criteria']
        noted = [key for key, label in criteria.items() if label.endswith(' (on arrival, nothing to do there with empty hands)')]
        self.assertIn('go serve', noted)
        self.assertTrue(all(key.startswith('go ') for key in noted))

    def test_a_walk_after_which_something_can_be_done_gets_no_note(self):
        k = level('level-4')
        do(k, 'take pot p1')
        go = next(a for a in k.actions('jeff') if a.kind == 'go' and a.target == 'serve')
        with patch.object(SpatialKitchen, 'actions', lambda self, who: [go.__class__('serve', 'Serve', 'serve', 'serve')]):
            self.assertIsNone(go_note.note(k, go, 'Steak'))

    def test_the_feature_is_released_and_on(self):
        self.assertEqual(features.current()['go_note'], {'stage': 'release', 'on': True, 'version': go_note.VERSION})
        self.assertTrue(features.compose_options(features.current())['go'])
        off = {**features.current(), 'go_note': {**features.current()['go_note'], 'on': False}}
        self.assertFalse(features.compose_options(off)['go'])


class GoNoteReplayTests(paths.SavePathTests):
    def test_a_round_with_the_notes_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features, 'go_note': {**self.game.features['go_note'], 'on': True}}
        import levels
        with patch.object(levels, 'switches', lambda: {'level-4': True}):
            status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 4}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['go_note'], {'on': True, 'version': go_note.VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        record['conditions']['features']['go_note']['on'] = False
        self.assertIn('diverged', {row['status'] for row in research_replay.rebuild_requests(record)})


for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(GoNoteReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
