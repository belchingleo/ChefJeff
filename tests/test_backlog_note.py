"""backlog_note (backlog-note-v1): where only the other chef can chop, Jeff is told what the waiting orders still need.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import unittest
import uuid
from unittest.mock import patch

import backlog_note
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


def request(k, backlog):
    client = SpatialJevClient(k.c, key='test-no-credential')
    return compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, names=True, reach=True, backlog=backlog)


def expected_need(payload, k):
    """The chopped-first ingredients the pending orders need, counted from the recipes."""
    need = {}
    for o in payload['state']['kitchen']['orders']:
        if o['status'] != 'pending':
            continue
        for c in k.rules.recipes[o['dish']]['components']:
            heat = k.rules.heat.get(c['item'])
            if c['state'] == 'chopped' or (c['state'] == 'ready' and heat and heat.get('from') == 'chopped'):
                need[c['item']] = need.get(c['item'], 0) + 1
    return need


class BacklogNoteTests(unittest.TestCase):
    def test_level_four_counts_what_the_waiting_orders_need_and_what_is_fetched(self):
        k = kitchen(4)
        self.assertTrue(backlog_note.applies(k))
        on = request(k, True)
        need = expected_need(on, k)
        self.assertTrue(need)
        order, counted, have, ready = backlog_note.counts(k, on)
        self.assertEqual(dict(counted), need)
        self.assertFalse(+have)
        self.assertFalse(+ready)
        self.assertIn('Within the other chef\'s reach to chop now: nothing.', on['state']['backlog'])
        for word in ('should', 'fetch next', 'throw', 'pass'):          # a count, not advice
            self.assertNotIn(word, on['state']['backlog'].lower())

    def test_a_raw_ingredient_on_a_dividing_counter_is_fetched_and_within_the_other_chefs_reach(self):
        k = kitchen(4)
        do(k, 'jeff', 'fetch beef')
        put = next(a for a in k.actions('jeff') if a.kind == 'put_counter' and k.reaches('human', a.target))
        do(k, 'jeff', put.key)
        on = request(k, True)
        _, _, have, ready = backlog_note.counts(k, on)
        self.assertEqual((have['beef'], ready['beef']), (1, 1))
        self.assertIn('Already fetched (in any state, plates included): beef 1.', on['state']['backlog'])
        self.assertIn('Within the other chef\'s reach to chop now: beef 1.', on['state']['backlog'])

    def test_it_says_how_many_stoves_have_a_pan_and_where_the_others_are(self):
        # v2: from the stoves' pot_id and the vessels lying elsewhere in the same request.
        k = kitchen(4)
        self.assertTrue(request(k, True)['state']['backlog'].endswith('Frying pans on stoves: 2 of 2.'))
        do(k, 'jeff', 'take pot p1')
        self.assertTrue(request(k, True)['state']['backlog'].endswith(
            'Frying pans on stoves: 1 of 2 (Stove 1 without one); elsewhere: your hands.'))

    def test_the_switch_adds_the_field_and_the_version_and_nothing_else(self):
        k = kitchen(4)
        on, off = request(k, True), request(k, False)
        self.assertEqual(on['state'].pop('backlog_note_version'), backlog_note.VERSION)
        on['state'].pop('backlog')
        self.assertEqual(json.dumps(on), json.dumps(off))

    def test_a_floor_where_jeff_can_chop_is_asked_exactly_as_before(self):
        for level in (1, 2, 3):
            k = kitchen(level)
            self.assertFalse(backlog_note.applies(k))
            self.assertEqual(json.dumps(request(k, True)), json.dumps(request(k, False)))

    def test_the_version_is_static_and_the_count_is_live(self):
        self.assertIn('backlog_note_version', wire_format.STATE_STATIC)
        self.assertNotIn('backlog', wire_format.STATE_STATIC)

    def test_the_feature_is_a_trial_off_by_default_without_a_page_switch(self):
        self.assertEqual(features.current()['backlog_note'],
                         {'stage': 'trial', 'on': False, 'player_switch': False, 'version': backlog_note.VERSION})
        on = {**features.current(), 'backlog_note': {**features.current()['backlog_note'], 'on': True}}
        self.assertTrue(features.compose_options(on)['backlog'])
        self.assertFalse(features.compose_options(features.current())['backlog'])


class BacklogReplayTests(paths.SavePathTests):
    def test_a_level_four_round_with_the_count_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features,
                                  'backlog_note': {**self.game.features['backlog_note'], 'on': True}}
        import levels
        with patch.object(levels, 'switches', lambda: {'level-4': True}):
            status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 4}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['backlog_note'], {'on': True, 'version': backlog_note.VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        self.assertTrue(all('backlog' in row['rebuilt']['state'] for row in rows))
        record['conditions']['features']['backlog_note']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(record)}, {'diverged'})


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(BacklogReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
