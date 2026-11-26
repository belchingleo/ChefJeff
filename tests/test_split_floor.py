"""split_floor (split-floor-v1): on a split floor where no dish can be made by one chef alone, Jeff is told so, as a fact.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import unittest
import uuid
from unittest.mock import patch

import features
import research_replay
import split_floor
from research_record import validate_record
from jev import compose_payload
from kitchen import load_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
import test_research_save_paths as paths

# The line as the 2026-11-17/18 re-asks sent it (dist/trial-l4-split-fact-20261117), for level 4.
LEVEL_4 = ("On this floor no dish can be made by one chef alone: chopping (b1, b2) is only on the human's side; "
           "the supplies (fridge, lettuce, tomato, bread), cooking (p1, p2) and serving (serve) are only on your side. "
           "Items cross between the two parts on the counters both of you reach (counter2–counter13) or by throwing.")


def kitchen(level):
    config = load_config()
    config.update(level=level)
    return SpatialKitchen(config)


def request(k, split, reach=False, links=False):
    client = SpatialJevClient(k.c, key='test-no-credential')
    return compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, reach=reach, links=links, split=split)


class SplitFloorTests(unittest.TestCase):
    def test_level_four_line_names_each_operation_by_the_side_that_reaches_it(self):
        k = kitchen(4)
        self.assertEqual(split_floor.line(k), LEVEL_4)
        for word in ('should', 'pass', 'hand', 'divide', 'first'):      # a fact, not advice
            self.assertNotIn(word, LEVEL_4.lower())

    def test_the_switch_adds_one_rule_after_reach_and_the_version_and_nothing_else(self):
        k = kitchen(4)
        for reach in (False, True):
            on, off = request(k, True, reach, links=True), request(k, False, reach, links=True)
            names = list(on['state']['rules'])
            if reach:
                self.assertEqual(names[names.index('reach') + 1], 'split_floor')
            self.assertEqual(on['state']['rules'].pop('split_floor'), LEVEL_4)
            self.assertEqual(on['state'].pop('split_floor_version'), split_floor.VERSION)
            self.assertEqual(json.dumps(on), json.dumps(off))       # the rest, key order included

    def test_a_floor_in_one_piece_is_asked_exactly_as_before(self):
        for level in (1, 2, 3):
            k = kitchen(level)
            self.assertFalse(k.split_floor)
            self.assertIsNone(split_floor.line(k))
            self.assertEqual(json.dumps(request(k, True, True)), json.dumps(request(k, False, True)))

    def test_nothing_is_added_when_one_chef_alone_could_make_a_dish(self):
        k = kitchen(4)
        with patch.object(k, 'reaches', lambda who, station: who == 'jeff' or k.equipment[station].get('type') == 'counter'):
            self.assertIsNone(split_floor.line(k))
            self.assertEqual(json.dumps(request(k, True, True)), json.dumps(request(k, False, True)))


    def test_the_feature_is_released_and_on_without_a_page_switch(self):
        self.assertEqual(features.current()['split_floor'],
                         {'stage': 'release', 'on': True, 'version': split_floor.VERSION})
        off = {**features.current(), 'split_floor': {**features.current()['split_floor'], 'on': False}}
        self.assertFalse(features.compose_options(off)['split'])
        self.assertTrue(features.compose_options(features.current())['split'])


class SplitFloorReplayTests(paths.SavePathTests):
    def test_a_level_four_round_with_the_line_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features,
                                  'reach_note': {**self.game.features['reach_note'], 'on': True},
                                  'split_floor': {**self.game.features['split_floor'], 'on': True}}
        import levels
        with patch.object(levels, 'switches', lambda: {'level-4': True}):    # level 4 is switched off for players
            status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 4}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['level'], 4)
        self.assertEqual(record['conditions']['features']['split_floor'], {'on': True, 'version': split_floor.VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        self.assertTrue(all(row['rebuilt']['state']['rules']['split_floor'] == LEVEL_4 for row in rows))
        # The same record read as if the switch had been off rebuilds requests that no longer match.
        record['conditions']['features']['split_floor']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(record)}, {'diverged'})


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(SplitFloorReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
