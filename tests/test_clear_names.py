"""clear_names (clear-names-v2): no bare item ids or "the held item" in what Jeff reads.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import copy
import json
import re
import unittest
import uuid

import clear_names
import features
import research_replay
import wire_format
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


def request(k, clear, links=False, wait_note=False):
    client = SpatialJevClient(k.c, key='test-no-credential')
    payload = compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, names=True, links=links, clear=clear,
                              wait_note=wait_note)
    payload['state']['recent_events'] = payload['state'].get('recent_events', [])
    return payload


def texts(payload):
    out = [label for q in payload['questions'].values() for label in (q.get('criteria') or {}).values()]
    out += [line for lines in (payload['state'].get('option_links') or {}).values() for line in lines]
    out += [e.get('message', '') for e in payload['state'].get('recent_events', [])]
    return out


class ClearNamesTests(unittest.TestCase):
    def test_puts_name_what_is_held(self):
        k = kitchen(4)
        do(k, 'jeff', 'fetch beef')
        on, off = request(k, True), request(k, False)
        self.assertTrue(any('the held item' in t for t in off['questions']['next_action']['criteria'].values()))
        for q in on['questions'].values():
            for label in (q.get('criteria') or {}).values():
                self.assertNotIn('the held item', label)
        put = next(key for key in on['questions']['next_action']['criteria'] if key.startswith('put counter'))
        self.assertTrue(on['questions']['next_action']['criteria'][put].startswith('Put the held beef (as fetched) on '))

    def test_a_pick_up_leads_with_the_food_and_says_what_a_full_hand_leaves(self):
        k = kitchen(4)
        do(k, 'jeff', 'fetch beef')
        do(k, 'jeff', 'drop')
        item = next(iter(k.ground))
        empty = request(k, True)['questions']['next_action']['criteria'][f'pickup {item}']
        self.assertRegex(empty, rf'^Pick up beef \(as fetched\) {item} at floor \(\d+,\d+\)$')
        do(k, 'jeff', 'fetch lettuce')
        full = request(k, True)['questions']['next_action']['criteria'][f'pickup {item}']
        self.assertTrue(full.endswith('(the held lettuce (as fetched) stays there)'), full)
        self.assertNotIn('auto-swap', full)

    def test_events_name_items_and_old_food_words_as_the_recipes_do(self):
        k = kitchen(4)
        do(k, 'jeff', 'fetch beef')
        do(k, 'jeff', 'throw partner')
        k.advance(1.0)
        events = [e['message'] for e in request(k, True)['state']['recent_events']]
        self.assertIn('jeff completed: Take beef (as fetched) from the fridge', events)
        self.assertTrue(any(re.match(r'jeff threw F\d+ \(beef, as fetched\) toward', m) for m in events), events)
        for m in events:
            self.assertNotIn('raw meat', m)
            self.assertNotIn('the held item', m)

    def test_no_id_stands_alone_and_applying_twice_changes_nothing(self):
        k = kitchen(4)
        do(k, 'jeff', 'fetch beef')
        do(k, 'jeff', 'throw partner')
        k.advance(1.0)
        on = request(k, True, links='partner')
        for text in texts(on):
            for m in clear_names.BARE.finditer(text):
                before = text[:m.start()]
                self.assertTrue(re.search(r'(beef|lettuce|tomato|bread|plate|pan|pot)[^,;]*$', before), text)
        again = clear_names.apply(copy.deepcopy(on), k)
        self.assertEqual(json.dumps(again), json.dumps(on))

    def test_a_chef_task_and_the_continue_label_that_quotes_it_name_the_item(self):
        k = kitchen(2)
        do(k, 'jeff', 'fetch lettuce')
        do(k, 'jeff', next(a for a in k.actions('jeff') if a.kind == 'put_board').key)
        k.start('jeff', next(a for a in k.actions('jeff') if a.kind == 'chop'))
        k.advance(0.3)
        off, on = request(k, False, wait_note=True), request(k, True, wait_note=True)
        self.assertRegex(off['state']['kitchen']['chefs']['jeff']['task'], r'^Chop F\d+ at Board 1 ')
        task = on['state']['kitchen']['chefs']['jeff']['task']
        self.assertRegex(task, r'^Chop lettuce \([^)]*\) F\d+ at Board 1 \(')
        self.assertTrue(on['questions']['next_action']['criteria']['continue'].startswith('Continue current task: ' + task), on)
        again = clear_names.apply(copy.deepcopy(on), k)
        self.assertEqual(json.dumps(again), json.dumps(on))

    def test_an_old_food_word_before_the_id_is_replaced_not_kept(self):
        text = 'Continue current task: Pick up raw meat F2 at floor (3,5); 0.9 s left'
        self.assertEqual(clear_names.name_ids(text, {'F2': 'beef (as fetched)'}),
                         'Continue current task: Pick up beef (as fetched) F2 at floor (3,5); 0.9 s left')

    def test_off_the_request_is_as_before(self):
        for level in (1, 4):
            k = kitchen(level)
            do(k, 'jeff', 'fetch beef')
            on, off = request(k, True), request(k, False)
            self.assertEqual(on['state'].pop('clear_names_version'), clear_names.VERSION)
            self.assertNotEqual(json.dumps(on), json.dumps(off))       # named
            self.assertNotIn('clear_names_version', off['state'])

    def test_the_version_is_static(self):
        self.assertIn('clear_names_version', wire_format.STATE_STATIC)

    def test_the_feature_is_a_trial_off_by_default_without_a_page_switch(self):
        self.assertEqual(features.current()['clear_names'],
                         {'stage': 'trial', 'on': False, 'player_switch': False, 'version': clear_names.VERSION})
        on = {**features.current(), 'clear_names': {**features.current()['clear_names'], 'on': True}}
        self.assertTrue(features.compose_options(on)['clear'])
        self.assertFalse(features.compose_options(features.current())['clear'])


class ClearNamesReplayTests(paths.SavePathTests):
    def test_a_round_with_clear_names_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features, 'clear_names': {**self.game.features['clear_names'], 'on': True}}
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['clear_names'], {'on': True, 'version': clear_names.VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        record['conditions']['features']['clear_names']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(record)}, {'diverged'})


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(ClearNamesReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
