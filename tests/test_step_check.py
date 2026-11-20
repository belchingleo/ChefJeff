"""step_check (step-check-v3): whether each kind of step the waiting orders need is possible now, from the engine.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import unittest
import uuid
from unittest.mock import patch

import features
import research_replay
import step_check
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


def do(k, who, key):
    k.start(who, next(a for a in k.actions(who) if a.key == key))
    while k.chefs[who].job is not None:
        k.advance(0.05)


def request(k, steps):
    client = SpatialJevClient(k.c, key='test-no-credential')
    return compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, names=True, reach=True, steps=steps)


class StepCheckTests(unittest.TestCase):
    def test_at_the_start_every_step_is_possible_and_its_side_is_named(self):
        text = request(kitchen(4), True)['state']['step_check']
        self.assertIn('Chopping: possible now (Board 1, Board 2 free); the boards are on the other chef\'s side.', text)
        self.assertIn('Cooking beef in a frying pan: possible now on Stove 1, Stove 2; the stoves are on your side.', text)
        self.assertIn('Plating: possible now (clean plates:', text)
        self.assertIn('Serving: at Serve, on your side.', text)
        self.assertIn('Fetching: possible now from Fridge (beef), Bread supply (bread), Lettuce supply (lettuce), '
                      'Tomato supply (tomato); the supplies are on your side.', text)
        self.assertLess(text.index('Still to fetch:'), text.index('Fetching:'))     # the backlog counts come first
        self.assertLess(text.index('Fetching:'), text.index('Chopping:'))
        self.assertNotIn('Frying pans on stoves', text)                 # without the backlog's own pans sentence
        for word in ('should', 'next', 'please'):                       # facts, not advice
            self.assertNotIn(word, text.lower())

    def test_a_supply_with_something_on_it_gives_nothing_and_says_what_lies_there(self):
        # (v2) The engine lists no fetch from a supply that holds an item: in a 2026-11-19 round a thrown bread on the
        # fridge took beef away for the rest of the round.
        k = kitchen(4)
        do(k, 'jeff', 'fetch bread')
        do(k, 'jeff', 'put fridge')
        self.assertNotIn('fetch beef', [a.key for a in k.actions('jeff')])
        text = request(k, True)['state']['step_check']
        self.assertIn('Fetching: possible now from Bread supply (bread), Lettuce supply (lettuce), Tomato supply (tomato); '
                      'Fridge (beef) gives nothing while bread (as fetched) lies on it; the supplies are on your side.', text)

    def test_with_no_pan_on_a_stove_cooking_is_possible_once_one_is_put_there(self):
        # (v3) v1 and v2 said "not possible now: no stove has a frying pan" while the pans were in hand or on a counter.
        k = kitchen(4)
        do(k, 'jeff', 'take pot p1')
        put = next(a for a in k.actions('jeff') if a.kind == 'put_counter')
        do(k, 'jeff', put.key)
        do(k, 'jeff', 'take pot p2')
        payload = request(k, True)
        counter = payload['state']['kitchen']['stations'][put.target]['name']
        self.assertIn('Cooking beef in a frying pan: possible once a frying pan is put on Stove 1 or Stove 2 (no frying pan '
                      f'there); frying pans off the stoves: {counter} (empty frying pan), your hands (empty frying pan); '
                      'the stoves are on your side.', payload['state']['step_check'])

    def pan_on_a_counter_and_burnt_food_on_the_other_stove(self, stage):
        """Level 4: Stove 1's pan on a counter holding beef in this stage, Stove 2's pan holding burnt beef."""
        k = kitchen(4)
        do(k, 'jeff', 'take pot p1')
        put = next(a for a in k.actions('jeff') if a.kind == 'put_counter')
        do(k, 'jeff', put.key)
        payload = request(k, False)
        stations = payload['state']['kitchen']['stations']
        stations['p2']['food'] = {'id': 'F9', 'stage': 'burnt', 'meaning': 'beef (burnt)', 'ingredient': 'beef'}
        pan = stations[put.target]['food']
        pan['contents'] = {'id': 'F8', 'stage': stage, 'meaning': f'beef ({stage})', 'ingredient': 'beef'}
        pan['meaning'] = f'frying pan with beef ({stage})'
        return k, payload, stations[put.target]['name']

    def test_a_free_stove_and_a_pan_of_chopped_beef_on_a_counter_make_cooking_possible(self):
        # (v3) A 2026-11-19 play round: v2 said "not possible now: every frying pan on a stove holds food or is on fire
        # (Stove 2 holds beef (burnt))" for 100 s while this pan stood on Counter 7.
        k, payload, counter = self.pan_on_a_counter_and_burnt_food_on_the_other_stove('chopped')
        self.assertEqual(step_check.cooking(k, payload), [
            'Cooking beef in a frying pan: possible once a frying pan is put on Stove 1 (no frying pan there); frying '
            f'pans off the stoves: {counter} (frying pan with beef (chopped)); Stove 2 holds beef (burnt); the stoves are '
            'on your side.'])

    def test_a_pan_off_the_stove_holding_cooked_food_does_not_make_cooking_possible(self):
        k, payload, _ = self.pan_on_a_counter_and_burnt_food_on_the_other_stove('ready')
        self.assertEqual(step_check.cooking(k, payload), [
            'Cooking beef in a frying pan: not possible now: every frying pan on a stove holds food or is on fire '
            '(Stove 2 holds beef (burnt)).'])

    def test_a_pan_holding_food_is_named_and_the_free_one_offered(self):
        k = kitchen(4)
        payload = request(k, False)
        payload['state']['kitchen']['stations']['p1']['food'] = {'id': 'F9', 'stage': 'burnt', 'meaning': 'beef (burnt)', 'ingredient': 'beef'}
        lines = step_check.cooking(k, payload)
        self.assertEqual(lines, ['Cooking beef in a frying pan: possible now on Stove 2; Stove 1 holds beef (burnt); the stoves are on your side.'])

    def test_the_switch_adds_the_field_and_the_version_and_nothing_else(self):
        k = kitchen(4)
        on, off = request(k, True), request(k, False)
        self.assertEqual(on['state'].pop('step_check_version'), step_check.VERSION)
        on['state'].pop('step_check')
        self.assertEqual(json.dumps(on), json.dumps(off))

    def test_a_floor_where_jeff_can_chop_is_asked_exactly_as_before(self):
        for level in (1, 2, 3):
            k = kitchen(level)
            self.assertEqual(json.dumps(request(k, True)), json.dumps(request(k, False)))


    def test_the_feature_is_a_trial_off_by_default_without_a_page_switch(self):
        self.assertEqual(features.current()['step_check'],
                         {'stage': 'trial', 'on': False, 'version': step_check.VERSION})
        on = {**features.current(), 'step_check': {**features.current()['step_check'], 'on': True}}
        self.assertTrue(features.compose_options(on)['steps'])
        self.assertFalse(features.compose_options(features.current())['steps'])


class StepCheckReplayTests(paths.SavePathTests):
    def test_a_level_four_round_with_the_check_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features, 'step_check': {**self.game.features['step_check'], 'on': True}}
        import levels
        with patch.object(levels, 'switches', lambda: {'level-4': True}):
            status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 4}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['step_check'], {'on': True, 'version': step_check.VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        self.assertTrue(all('step_check' in row['rebuilt']['state'] for row in rows))
        record['conditions']['features']['step_check']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(record)}, {'diverged'})


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(StepCheckReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
