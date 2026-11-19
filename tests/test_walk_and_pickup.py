"""walk_note (walk-note-v1), pickup_press (put-then-pickup-v1), and no Chinese in a request with every trial on.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import re
import unittest
import uuid
from unittest.mock import patch

import features
import one_press
import research_replay
import walk_note
from research_record import validate_record
from jev import compose_payload
from kitchen import load_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
import test_research_save_paths as paths

CJK = re.compile(r'[　-〿一-鿿＀-￯]')
PRESSES = {'put_then_take': True, 'wash_from_returns': True}


def kitchen(level):
    config = load_config()
    config.update(level=level)
    return SpatialKitchen(config)


def do(k, who, key):
    k.start(who, next(a for a in k.actions(who) if a.key == key))
    while k.chefs[who].job is not None:
        k.advance(0.05)


def floor_beef_and_lettuce_in_hand():
    """Level 4: Jeff left a raw beef on the floor and holds a lettuce."""
    k = kitchen(4)
    do(k, 'jeff', 'fetch beef')
    do(k, 'jeff', 'drop')
    do(k, 'jeff', 'fetch lettuce')
    return k


def request(k, presses=None, **switches):
    flags = one_press.flags(presses) if presses else None
    actions = k.actions('jeff')
    if flags:
        actions = actions + one_press.options(k, 'jeff', actions, flags)
    client = SpatialJevClient(k.c, key='test-no-credential')
    return compose_payload(client, k, k.snapshot(), actions, [], None, one_press=flags, names=True, **switches), actions


class WalkNoteTests(unittest.TestCase):
    def test_each_option_that_walks_says_the_seconds_the_engine_routes(self):
        k = floor_beef_and_lettuce_in_hand()
        before = json.dumps(k.snapshot(), sort_keys=True, default=str)
        on, actions = request(k, PRESSES, walk=True)
        off, _ = request(k, PRESSES)
        self.assertEqual(json.dumps(k.snapshot(), sort_keys=True, default=str), before)     # nothing in the round changed
        by_key = {a.key: a for a in actions}
        checked = 0
        for key, label in on['questions']['next_action']['criteria'].items():
            plain, a = off['questions']['next_action']['criteria'][key], by_key[key]
            if a.kind in walk_note.NO_WALK:
                self.assertEqual(label, plain)
                continue
            twin = k.fork()
            seconds = twin.travel_time(twin.chefs['jeff'], a.target)
            if a.kind in one_press.KINDS:
                self.assertTrue(label.startswith(plain) and label.endswith(f': {seconds:.1f} s walk from you)'), label)
            else:
                self.assertEqual(label, plain + f' ({seconds:.1f} s walk)')
            checked += 1
        self.assertGreater(checked, 5)
        self.assertEqual(on['state']['walk_note_version'], walk_note.VERSION)

    def test_the_switch_is_a_trial(self):
        self.assertEqual(features.current()['walk_note'],
                         {'stage': 'trial', 'on': False, 'player_switch': False, 'version': walk_note.VERSION})
        on = {**features.current(), 'walk_note': {**features.current()['walk_note'], 'on': True}}
        self.assertTrue(features.compose_options(on)['walk'])


class PickupPressTests(unittest.TestCase):
    def test_holding_something_a_floor_item_can_be_picked_up_after_putting_it_down(self):
        k = floor_beef_and_lettuce_in_hand()
        item = next(iter(k.ground))
        on, actions = request(k, {**PRESSES, 'put_then_pickup': True})
        label = on['questions']['next_action']['criteria'][f'put then pickup {item}']
        self.assertRegex(label, r'^Put the held lettuce \(as fetched\) where put_where says, then take beef \(as fetched\) '
                                r'from floor \(\d+,\d+\)$')
        self.assertIn('"put then pickup <item>"', on['state']['rules']['one_press'])
        option = next(a for a in actions if a.key == f'put then pickup {item}')
        put, _ = one_press.place(k.actions('jeff'), next(iter(on['questions']['put_where']['criteria'])))
        do(k, 'jeff', put.key)
        step = one_press.find(k, 'jeff', one_press.steps(option, k)[0])
        do(k, 'jeff', step.key)
        self.assertEqual(k.chefs['jeff'].hand.id, item)

    def test_off_the_released_one_press_options_and_records_are_unchanged(self):
        k = floor_beef_and_lettuce_in_hand()
        released, _ = request(k, PRESSES)
        self.assertFalse(any(key.startswith('put then pickup') for key in released['questions']['next_action']['criteria']))
        self.assertNotIn('put then pickup', released['state']['rules']['one_press'])
        self.assertEqual(one_press.flags(PRESSES), PRESSES)
        self.assertEqual(features.one_press_flags(features.current()), PRESSES)
        on = {**features.current(), 'pickup_press': {**features.current()['pickup_press'], 'on': True}}
        self.assertEqual(features.one_press_flags(on), {**PRESSES, 'put_then_pickup': True})


class NoChineseTests(unittest.TestCase):
    """With every trial addition on, nothing reaches Jeff in Chinese."""

    def test_no_chinese_in_requests_with_every_trial_on(self):
        switches = dict(reach=True, links='partner+burnt', split=True, burn=True, serve_note=True, wait_note=True,
                        steps=True, clear=True, walk=True, effects=True)
        for level in (1, 2, 3, 4):
            k = kitchen(level)
            for key in ('fetch beef', 'drop', 'fetch lettuce'):
                if any(a.key == key for a in k.actions('jeff')):
                    do(k, 'jeff', key)
                    payload, _ = request(k, {**PRESSES, 'put_then_pickup': True}, **switches)
                    text = json.dumps(payload, ensure_ascii=False)
                    self.assertIsNone(CJK.search(text), (level, key, CJK.findall(text)[:5]))

    def test_no_chinese_with_every_trial_on_and_engine_english_where_food_is_plated(self):
        import test_engine_english as ee
        switches = dict(reach=True, links='partner+burnt', split=True, burn=True, serve_note=True, wait_note=True,
                        steps=True, clear=True, walk=True, english=True, effects=True)
        decisions, _ = ee.loop_notes(True)
        for level in (1, 2, 3, 4):
            k = kitchen(level)
            for key in ('fetch beef', 'drop', 'fetch lettuce'):
                if any(a.key == key for a in k.actions('jeff')):
                    do(k, 'jeff', key)
                    payload, _ = request(k, {**PRESSES, 'put_then_pickup': True}, **switches)
                    text = json.dumps(payload, ensure_ascii=False)
                    self.assertIsNone(CJK.search(text), (level, key, CJK.findall(text)[:5]))
        for k in (ee.plating(), ee.played()):
            payload, _ = request(k, {**PRESSES, 'put_then_pickup': True}, **switches)
            payload['state']['recent_decisions'] = decisions
            text = json.dumps(payload, ensure_ascii=False)
            self.assertIsNone(CJK.search(text), CJK.findall(text)[:5])

    def test_no_chinese_with_the_released_switches_and_engine_english(self):
        # features.json as released (one_press, clear_text, option_links, ask_ahead): the plating labels, the events
        # that carry them (started, stopped, completed) and the loop's own notes, in English.
        import test_engine_english as ee
        options = features.compose_options(features.load())
        self.assertTrue(options['english'])
        decisions, _ = ee.loop_notes(True)
        self.assertEqual(len(decisions), 3)
        for k in (ee.plating(), ee.played()):
            k.advance(.2)
            client = SpatialJevClient(k.c, key='test-no-credential')
            payload = compose_payload(client, k, k.snapshot(), k.actions('jeff'), decisions, None, **options)
            text = json.dumps(payload, ensure_ascii=False)
            self.assertIsNone(CJK.search(text), CJK.findall(text)[:5])
        events = [e['message'] for e in payload['state']['recent_events']]
        for word in ('started', 'stopped', 'completed'):
            self.assertTrue(any(m.startswith(f'jeff {word}: Plate food from the frying pan') for m in events), word)
        self.assertEqual(payload['state']['kitchen']['chefs']['jeff']['task'],
                         'Plate food from the frying pan on the floor onto the held clean plate (empty frying pan stays in place)')

    def test_the_loops_note_about_a_dropped_ahead_answer_is_given_in_english(self):
        import clear_names
        k = kitchen(4)
        payload, _ = request(k, PRESSES, clear=True)
        payload['state']['recent_decisions'] = [{'t': 1.0, 'choice': 'wait', 'accepted': False,
                                                 'result': '提前问的回复作废 (not_listed), 马上重问'},
                                                {'t': 2.0, 'choice': 'wait', 'accepted': False,
                                                 'result': '提前问的回复作废（已暂停或本局结束），马上重问'}]
        clear_names.apply(payload, k)
        self.assertEqual([d['result'] for d in payload['state']['recent_decisions']],
                         ['the answer asked ahead was dropped (not_listed); asked again at once',
                          'the answer asked ahead was dropped (paused, or the round ended); asked again at once'])


class WalkPickupReplayTests(paths.SavePathTests):
    def test_a_level_four_round_with_both_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features,
                                  'walk_note': {**self.game.features['walk_note'], 'on': True},
                                  'pickup_press': {**self.game.features['pickup_press'], 'on': True}}
        import levels
        with patch.object(levels, 'switches', lambda: {'level-4': True}):
            status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 4}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['walk_note'], {'on': True, 'version': walk_note.VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        record['conditions']['features']['walk_note']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(record)}, {'diverged'})


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(WalkPickupReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
