"""reach_note (reach-v1): on a split floor Jeff is told, as a fact, which stations each chef can reach.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import unittest
import uuid

import features
import reach_note
import research_replay
from research_record import validate_record
from jev import compose_payload
from kitchen import load_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
import test_research_save_paths as paths


def kitchen(level):
    config = load_config()
    config.update(level=level)
    return SpatialKitchen(config)


def request(k, reach):
    client = SpatialJevClient(k.c, key='test-no-credential')
    return compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, reach=reach)


class ReachNoteTests(unittest.TestCase):
    def test_level_four_lists_each_side_as_the_engine_reaches_it(self):
        k = kitchen(4)
        self.assertTrue(k.split_floor)
        found = reach_note.lists(k, list(k.snapshot()['stations']))
        self.assertIn('fridge', found['jeff'] + found['human'])
        jeff_side = 'jeff' if 'fridge' in found['jeff'] else 'human'
        human_side = 'human' if jeff_side == 'jeff' else 'jeff'
        self.assertTrue({'fridge', 'p1', 'p2', 'serve'} <= set(found[jeff_side]))
        self.assertTrue({'b1', 'b2', 'sink'} <= set(found[human_side]))
        self.assertTrue(found['both'])
        for side, ids in found.items():
            for station in ids:
                self.assertEqual((k.reaches('jeff', station), k.reaches('human', station)),
                                 {'jeff': (True, False), 'human': (False, True), 'both': (True, True)}[side])

    def test_the_switch_adds_one_rule_and_the_version_and_nothing_else(self):
        k = kitchen(4)
        on, off = request(k, True), request(k, False)
        rule = on['state']['rules'].pop('reach')
        self.assertEqual(on['state'].pop('reach_note_version'), reach_note.VERSION)
        self.assertEqual(json.dumps(on, sort_keys=True), json.dumps(off, sort_keys=True))
        found = reach_note.lists(k, list(off['state']['kitchen']['stations']))
        self.assertEqual(rule, reach_note.RULE.format(**{key: ', '.join(ids) or 'none' for key, ids in found.items()}))
        for word in ('pass', 'throw', 'hand', 'should', 'divide'):     # a fact, not advice
            self.assertNotIn(word, rule.lower())

    def test_a_floor_in_one_piece_is_asked_exactly_as_before(self):
        for level in (1, 2, 3):
            k = kitchen(level)
            self.assertFalse(k.split_floor)
            self.assertEqual(json.dumps(request(k, True), sort_keys=True), json.dumps(request(k, False), sort_keys=True))

    def test_the_feature_is_a_trial_off_by_default_without_a_page_switch(self):
        self.assertEqual(features.current()['reach_note'],
                         {'stage': 'trial', 'on': False, 'player_switch': False, 'version': reach_note.VERSION})


class ReachReplayTests(paths.SavePathTests):
    def test_a_level_four_round_with_the_note_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features, 'reach_note': {**self.game.features['reach_note'], 'on': True}}
        status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 4}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['level'], 4)
        self.assertEqual(record['conditions']['features']['reach_note'], {'on': True, 'version': reach_note.VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        self.assertEqual(research_replay.check(record)['replay'], 'verified')
        self.assertTrue(all('reach' in row['rebuilt']['state']['rules'] for row in rows))
        # The same record read as if the switch had been off rebuilds requests that no longer match.
        record['conditions']['features']['reach_note']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(record)}, {'diverged'})


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(ReachReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
