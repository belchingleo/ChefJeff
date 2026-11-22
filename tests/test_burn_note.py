"""burn_note (burn-note-v1 to v4): options on a stove whose food is cooked say, with the time, when it burns. Facts only.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import unittest
import uuid
from unittest.mock import patch

import burn_note
import features
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


def do(k, key):
    k.start('jeff', next(a for a in k.actions('jeff') if a.key == key))
    while k.chefs['jeff'].job is not None:
        k.advance(0.05)


def cooked_pan():
    """Level 1, Jeff alone: beef fetched, chopped and put in the pan on Stove 1, then left until it is cooked."""
    k = kitchen(1)
    for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
        do(k, key)
    while k.stations['p1'].food is None or k.stations['p1'].food.stage != 'ready':
        k.advance(0.1)
    k.advance(1.0)
    return k


def request(k, burn, names=True):
    client = SpatialJevClient(k.c, key='test-no-credential')
    return compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, names=names, burn=burn)


class BurnNoteTests(unittest.TestCase):
    def test_options_on_the_stove_say_when_its_cooked_food_burns(self):
        k = cooked_pan()
        on, off = request(k, True), request(k, False)
        stove = off['state']['kitchen']['stations']['p1']
        note = f" (beef (cooked) on {stove['name']} burns in {stove['burn_in']:.1f} s; {stove['name']} catches fire then)"
        changed = {key for key, label in on['questions']['next_action']['criteria'].items()
                   if label != off['questions']['next_action']['criteria'][key]}
        self.assertTrue(changed)
        self.assertEqual(changed, {key for key in off['questions']['next_action']['criteria'] if 'p1' in key.split()})
        for key in changed:
            self.assertEqual(on['questions']['next_action']['criteria'][key], off['questions']['next_action']['criteria'][key] + note)
        self.assertEqual(on['state'].pop('burn_note_version'), burn_note.VERSION)
        on['questions']['next_action']['criteria'] = off['questions']['next_action']['criteria']
        self.assertEqual(json.dumps(on), json.dumps(off))       # nothing else, key order included
        for word in ('should', 'hurry', 'lift', 'take', 'now'):    # a fact, not advice
            self.assertNotIn(word, note.lower())

    def test_while_it_cooks_the_options_on_the_stove_say_when_it_is_cooked_and_burns(self):
        # v2: before the food is cooked as well, from the stove's ready_in and burn_in in the same request.
        k = kitchen(1)
        for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
            do(k, key)
        k.advance(2.0)
        self.assertEqual(k.stations['p1'].food.stage, 'cooking')
        on, off = request(k, True), request(k, False)
        stove = off['state']['kitchen']['stations']['p1']
        note = (f" (beef (cooking) on {stove['name']} is cooked in {stove['ready_in']:.1f} s and burns in "
                f"{stove['burn_in']:.1f} s; {stove['name']} catches fire then)")
        changed = {key for key, label in on['questions']['next_action']['criteria'].items()
                   if label != off['questions']['next_action']['criteria'][key]}
        self.assertTrue(changed)
        for key in changed:
            self.assertIn('p1', key.split())
            self.assertEqual(on['questions']['next_action']['criteria'][key], off['questions']['next_action']['criteria'][key] + note)

    def test_putting_a_held_pan_of_cooked_food_back_on_a_stove_says_when_it_burns(self):
        # (v3) Off the stove the food does not heat; back on the heat it burns at the engine's threshold.
        k = cooked_pan()
        do(k, 'take pot p1')
        food = k.chefs['jeff'].hand.contents
        burn = k.rules.heat_thresholds(food.ingredient)[1]
        on, off = request(k, True), request(k, False)
        label = on['questions']['next_action']['criteria']['put pot p1']
        self.assertEqual(label, off['questions']['next_action']['criteria']['put pot p1']
                         + f' (beef (cooked) in the held frying pan burns {burn - food.heated:.1f} s after it is back on the heat;'
                           f' Stove 1 catches fire then)')
        changed = {key for key, text in on['questions']['next_action']['criteria'].items()
                   if text != off['questions']['next_action']['criteria'][key]}
        self.assertEqual(changed, {'put pot p1'})        # plating it, putting it on a counter: no note

    def test_on_a_burning_stove_the_notes_say_the_food_waits_until_the_fire_is_out(self):
        # (v4) A fire that reaches a stove burns no food: cooked food waits there until the fire is out, and food
        # still cooking is cooked first (kitchen.ignite). No seconds for the wait.
        k = cooked_pan()
        k.ignite('p1')
        self.assertFalse(k.stations['p1'].heating)
        on, off = request(k, True), request(k, False)
        note = ' (beef (cooked) on Stove 1 waits until the fire on Stove 1 is out)'
        criteria = off['questions']['next_action']['criteria']
        changed = {key for key, label in on['questions']['next_action']['criteria'].items() if label != criteria[key]}
        self.assertTrue(changed)
        for key in changed:
            self.assertEqual(on['questions']['next_action']['criteria'][key], criteria[key] + note)

        k = kitchen(1)
        for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
            do(k, key)
        k.advance(2.0)
        k.ignite('p1')
        self.assertTrue(k.stations['p1'].heating)
        on = request(k, True)
        stove = on['state']['kitchen']['stations']['p1']
        self.assertIn(f" (beef (cooking) on Stove 1 is cooked in {stove['ready_in']:.1f} s, then waits until the fire on "
                      'Stove 1 is out)', on['questions']['next_action']['criteria']['take pot p1'])

    def test_putting_a_held_pan_on_a_burning_stove_says_the_food_waits_there(self):
        k = cooked_pan()
        do(k, 'take pot p1')
        k.ignite('p1')
        on, off = request(k, True), request(k, False)
        self.assertEqual(on['questions']['next_action']['criteria']['put pot p1'],
                         off['questions']['next_action']['criteria']['put pot p1']
                         + ' (beef (cooked) in the held frying pan waits there until the fire on Stove 1 is out)')

    def test_without_cooked_food_only_the_version_is_added(self):
        for level in (1, 4):
            k = kitchen(level)
            on, off = request(k, True), request(k, False)
            self.assertEqual(on['state'].pop('burn_note_version'), burn_note.VERSION)
            self.assertEqual(json.dumps(on), json.dumps(off))


    def test_the_feature_is_a_trial_off_by_default_without_a_page_switch(self):
        self.assertEqual(features.current()['burn_note'],
                         {'stage': 'trial', 'on': False, 'version': burn_note.VERSION})
        on = {**features.current(), 'burn_note': {**features.current()['burn_note'], 'on': True}}
        self.assertTrue(features.compose_options(on)['burn'])
        self.assertFalse(features.compose_options(features.current())['burn'])


class BurnNoteReplayTests(paths.SavePathTests):
    def test_a_round_with_the_notes_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features, 'burn_note': {**self.game.features['burn_note'], 'on': True}}
        import levels
        with patch.object(levels, 'switches', lambda: {'level-4': True}):
            status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 1}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['burn_note'], {'on': True, 'version': burn_note.VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        self.assertTrue(all(row['rebuilt']['state']['burn_note_version'] == burn_note.VERSION for row in rows))
        # The same record read as if the switch had been off rebuilds requests that no longer match.
        record['conditions']['features']['burn_note']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(record)}, {'diverged'})


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(BurnNoteReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
