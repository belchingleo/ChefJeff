"""option_notes (option-notes-v3 = serve-note-v2): options that serve or pick up a finished dish name the order it goes to.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import unittest
import uuid

import features
import option_notes
import research_replay
from research_record import validate_record
from jev import compose_payload
from kitchen import load_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
import test_research_save_paths as paths


def kitchen(level=1):
    config = load_config()
    config.update(level=level)
    return SpatialKitchen(config)


def do(k, key):
    k.start('jeff', next(a for a in k.actions('jeff') if a.key == key))
    while k.chefs['jeff'].job is not None:
        k.advance(0.05)


def plated_steak():
    """Level 1, Jeff alone: a steak cooked and plated, in his hands."""
    k = kitchen(1)
    for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
        do(k, key)
    while k.stations['p1'].food is None or k.stations['p1'].food.stage != 'ready':
        k.advance(0.1)
    do(k, 'take plates')
    do(k, 'plate p1')
    return k


def request(k, serve=False, links=False):
    client = SpatialJevClient(k.c, key='test-no-credential')
    return compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, names=True, serve_note=serve, links=links)


def without(payload, *versions):
    out = json.loads(json.dumps(payload))
    for v in versions:
        out['state'].pop(v)
    return out


class OptionNoteTests(unittest.TestCase):
    def test_serve_names_the_waiting_order_the_held_dish_goes_to(self):
        k = plated_steak()
        on, off = request(k, serve=True), request(k)
        orders = [o for o in off['state']['kitchen']['orders'] if o['dish'] == 'steak']
        first = min(orders, key=lambda o: (o['deadline'], o['id']))
        note = f" (the held Steak goes to order {first['id']}, which waits for Steak: {first['remaining']:.0f} s left)"
        self.assertEqual(on['questions']['next_action']['criteria']['serve'], off['questions']['next_action']['criteria']['serve'] + note)
        self.assertEqual(on['state']['serve_note_version'], option_notes.SERVE_VERSION)
        on['questions']['next_action']['criteria']['serve'] = off['questions']['next_action']['criteria']['serve']
        self.assertEqual(json.dumps(without(on, 'serve_note_version')), json.dumps(off))
        for word in ('should', 'hurry', 'now'):                # a fact, not advice
            self.assertNotIn(word, note.lower())

    def test_taking_a_finished_dish_names_the_order_it_goes_to_and_so_does_its_serve_line(self):
        # serve-note-v2: in a 2026-11-19 play round a Steak lay on Counter 6 for 97 s while an order waited for it.
        k = plated_steak()
        do(k, 'put counter3')
        on, off = request(k, serve=True, links=True), request(k, links=True)
        orders = [o for o in off['state']['kitchen']['orders'] if o['dish'] == 'steak']
        first = min(orders, key=lambda o: (o['deadline'], o['id']))
        tail = f"goes to order {first['id']}, which waits for Steak: {first['remaining']:.0f} s left)"
        self.assertEqual(on['questions']['next_action']['criteria']['take counter3'],
                         off['questions']['next_action']['criteria']['take counter3'] + ' (the Steak there ' + tail)
        serve = [line for line in off['state']['option_links']['take counter3'] if line.startswith('Serve the plated dish')]
        self.assertEqual(len(serve), 1)
        self.assertIn(serve[0] + ' (the Steak ' + tail, on['state']['option_links']['take counter3'])
        changed = {key for key, label in on['questions']['next_action']['criteria'].items()
                   if label != off['questions']['next_action']['criteria'][key]}
        self.assertEqual(changed, {'take counter3'})

    def test_picking_a_finished_dish_up_from_the_floor_names_its_order(self):
        k = plated_steak()
        do(k, 'drop')
        item = next(iter(k.ground))
        on, off = request(k, serve=True), request(k)
        key = f'pickup {item}'
        self.assertTrue(on['questions']['next_action']['criteria'][key].startswith(off['questions']['next_action']['criteria'][key]
                                                                                   + ' (the Steak there goes to order O'))

    def test_serve_says_when_no_order_waits_for_the_dish(self):
        k = plated_steak()
        payload = request(k)
        payload['state']['kitchen']['orders'] = []
        self.assertEqual(option_notes.serve_note(payload), ' (no order is waiting for Steak now)')

    def test_the_wait_and_continue_options_are_left_as_they_are(self):
        # wait-note-v2 went with option-notes-v3 (2026-11-20): no effect on Jev's waiting in a re-ask.
        k = kitchen(1)
        do(k, 'fetch beef')
        on, off = request(k, serve=True), request(k)
        self.assertEqual(on['questions']['next_action']['criteria']['wait'], off['questions']['next_action']['criteria']['wait'])
        self.assertNotIn('wait_note_version', on['state'])
        k.start('jeff', next(a for a in k.actions('jeff') if a.key.startswith('go ')))
        k.advance(0.2)
        on, off = request(k, serve=True), request(k)
        self.assertEqual(on['questions']['next_action']['criteria']['continue'], off['questions']['next_action']['criteria']['continue'])

    def test_empty_hands_and_no_dish_leave_the_labels_as_they_were(self):
        for level in (1, 4):
            k = kitchen(level)
            on, off = request(k, serve=True), request(k)
            self.assertEqual(json.dumps(without(on, 'serve_note_version')), json.dumps(off))


    def test_one_switch_a_trial_off_by_default_without_a_page_switch(self):
        self.assertEqual(features.current()['option_notes'],
                         {'stage': 'trial', 'on': False, 'version': option_notes.VERSION})
        self.assertEqual((option_notes.VERSION, option_notes.SERVE_VERSION),
                         ('option-notes-v3', 'serve-note-v2'))     # a new part needs a new VERSION
        for name in ('serve_note', 'wait_note'):
            self.assertNotIn(name, features.current())
        self.assertNotIn('wait_note', features.compose_options(features.current()))
        on = {**features.current(), 'option_notes': {**features.current()['option_notes'], 'on': True}}
        self.assertTrue(features.compose_options(on)['serve_note'])
        self.assertFalse(features.compose_options(features.current())['serve_note'])


class OptionNoteReplayTests(paths.SavePathTests):
    def test_a_round_with_the_notes_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features, 'option_notes': {**self.game.features['option_notes'], 'on': True}}
        status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 1}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['option_notes'], {'on': True, 'version': option_notes.VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        # A record from before the merge names serve_note (and wait_note, which is no longer rebuilt).
        old = json.loads(json.dumps(record))
        del old['conditions']['features']['option_notes']
        old['conditions']['features'].update(serve_note={'on': True, 'version': 'v'})
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(old)}, {'verified'})
        record['conditions']['features']['option_notes']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(record)}, {'diverged'})


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(OptionNoteReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
