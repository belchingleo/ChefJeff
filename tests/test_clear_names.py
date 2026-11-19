"""clear_names (clear-names-v3): no bare item ids or "the held item" in what Jeff reads.

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

    def test_a_step_that_adds_food_to_a_plate_names_the_food_added(self):
        # (v3) The plate's food keeps its first ingredient's id (lettuce here); the event names what was added.
        k = kitchen(2)
        for key in ('fetch lettuce', 'put b1', 'chop b1', 'take plates', 'assemble b1', 'put counter10',
                    'fetch bread', 'assemble counter10'):
            do(k, 'jeff', key)
        events = [e['message'] for e in request(k, True)['state']['recent_events']]
        self.assertIn('jeff completed: Add the lettuce (chopped) from Board 1 to the held plate', events)
        self.assertIn('jeff completed: Put the held plate with lettuce on Counter 10 (one item per tile)', events)
        self.assertIn('jeff completed: Put the held bread (as fetched) onto the plate at Counter 10', events)

    def test_a_plated_dish_is_named_as_the_menu_names_it(self):
        k = kitchen(3)
        for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
            do(k, 'jeff', key)
        while k.stations['p1'].food.stage != 'ready':
            k.advance(0.05)
        for key in ('take plates', 'plate p1', 'put counter10'):
            do(k, 'jeff', key)
        events = [e['message'] for e in request(k, True)['state']['recent_events']]
        self.assertIn('jeff completed: Put the held Steak on Counter 10 (one item per tile)', events)

    def test_off_the_request_is_as_before(self):
        for level in (1, 4):
            k = kitchen(level)
            do(k, 'jeff', 'fetch beef')
            on, off = request(k, True), request(k, False)
            self.assertEqual(on['state'].pop('clear_names_version'), clear_names.VERSION)
            self.assertNotEqual(json.dumps(on), json.dumps(off))       # named
            self.assertNotIn('clear_names_version', off['state'])

    def test_the_dropped_ahead_note_reaches_jeff_in_english_as_the_loop_writes_it(self):
        # The loop writes it in Chinese; the catalog runs first and half-translates it ("提前问的回复作废 (已Pause或本局结束),
        # 马上重问)"), and v1 left the paused reason in Chinese and a stray ")" after every other reason.
        k = kitchen(4)
        client = SpatialJevClient(k.c, key='test-no-credential')
        notes = [{'t': 1.0, 'choice': 'wait', 'accepted': False, 'result': f'提前问的回复作废（{reason}），马上重问',
                  'sprint_applied': False} for reason in ('已暂停或本局结束', 'not_listed', 'too_old')]
        for clear in (False, True):
            payload = compose_payload(client, k, k.snapshot(), k.actions('jeff'), copy.deepcopy(notes), None,
                                      names=True, clear=clear)
            results = [d['result'] for d in payload['state']['recent_decisions']]
            if clear:
                self.assertEqual(results, [
                    'the answer asked ahead was dropped (paused, or the round ended); asked again at once',
                    'the answer asked ahead was dropped (not_listed); asked again at once',
                    'the answer asked ahead was dropped (too_old); asked again at once'])
                clear_names.apply(payload, k)          # a second pass (after the links table) changes nothing
                self.assertEqual([d['result'] for d in payload['state']['recent_decisions']], results)
            else:
                self.assertEqual(results[:2], ['提前问的回复作废 (已Pause或本局结束), 马上重问)',
                                               '提前问的回复作废 (not_listed), 马上重问)'])


if __name__ == '__main__':
    unittest.main()
