"""reach_note (reach-v1): on a split floor Jeff is told, as a fact, which stations each chef can reach.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import unittest
import uuid
from unittest.mock import patch

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


def holding_beef():
    """A level-4 kitchen with Jeff just back from the fridge with raw beef (the boards are on the human's side)."""
    k = kitchen(4)
    k.start('jeff', next(a for a in k.actions('jeff') if a.key == 'fetch beef'))
    while k.chefs['jeff'].job is not None:
        k.advance(0.1)
    return k


class ReachNoteCheckTests(unittest.TestCase):
    """scripts/reach_note_check.py: logged moments re-asked with and without the note, no model called."""

    def journal(self, rows):
        import tempfile
        from pathlib import Path
        folder = tempfile.mkdtemp()
        path = Path(folder) / 'round.jsonl'
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        return folder

    def rows(self, k, choice='wait', reach=False):
        payload = request(k, reach)
        return [{'kind': 'start', 'wall_time': '2026-11-08T06:00:00'},
                {'kind': 'ai_request', 'request_id': 'r1', 'payload': payload},
                {'kind': 'ai_response', 'request_id': 'r1', 'choice': choice, 'model': 'logged-model'}], payload

    def test_a_raw_ingredient_jeff_cannot_chop_is_a_moment_and_the_note_is_the_games_own(self):
        from scripts import reach_note_check as check
        k = holding_beef()
        rows, logged = self.rows(k, 'put counter4')
        found = check.moments([self.journal(rows)])
        self.assertEqual(len(found), 1)
        item = found[0]
        self.assertIn('put counter4', item['passing'])
        self.assertIn('throw partner', item['passing'])
        self.assertNotIn('put fridge', item['passing'])         # Jeff's side only
        self.assertNotIn('throw up', item['passing'])
        # Both arms ask next_action only; the note arm is exactly the game's request with the switch on.
        def same(a, b):     # as a journal holds it: JSON
            self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        game_on = request(k, True)
        same(check.arm(item, 'reach_note'), {**game_on, 'questions': {'next_action': game_on['questions']['next_action']}})
        same(check.arm(item, 'as_logged'), {**logged, 'questions': {'next_action': logged['questions']['next_action']}})
        self.assertIn('reach', check.arm(item, 'reach_note')['state']['rules'])
        self.assertNotIn('reach', check.arm(item, 'as_logged')['state']['rules'])

    def test_other_moments_are_left_out(self):
        from scripts import reach_note_check as check
        empty_handed = kitchen(4)
        self.assertEqual(check.moments([self.journal(self.rows(empty_handed)[0])]), [])
        rows, _ = self.rows(holding_beef(), reach=True)            # already asked with the note
        self.assertEqual(check.moments([self.journal(rows)]), [])
        rows, payload = self.rows(holding_beef())
        payload['state']['kitchen']['config_hash'] = 'sha256:another-map'   # a map this checkout builds differently
        self.assertEqual(check.moments([self.journal(rows)]), [])

    def test_the_report_counts_passes_and_the_probability_moved_onto_passing(self):
        from scripts import reach_note_check as check
        item = check.moments([self.journal(self.rows(holding_beef(), 'put counter1')[0])])[0]

        def ask(payload):
            noted = 'reach' in payload['state']['rules']
            self.assertEqual(list(payload['questions']), ['next_action'])
            return {'choice': 'put counter4' if noted else 'wait', 'model': 'fake',
                    'probabilities': {'wait': .4, 'put counter4': .5, 'throw partner': .1} if noted else
                                     {'wait': .8, 'put counter4': .15, 'throw partner': .05}}
        report = check.run([item], ask)
        self.assertEqual(report['logged']['passed'], 0.0)
        self.assertEqual((report['arms']['as_logged']['passed'], report['arms']['reach_note']['passed']), (0.0, 1.0))
        self.assertEqual(report['arms']['as_logged']['pass_probability_mean'], 0.2)
        self.assertEqual(report['arms']['reach_note']['pass_probability_change'],
                         {'moments': 1, 'per_moment': [0.4], 'mean': 0.4, 'up': 1, 'down': 0, 'same': 0})
        self.assertNotIn('payload', json.dumps(report))

    def test_each_moment_is_asked_in_both_arms_before_the_next(self):
        from scripts import reach_note_check as check
        item = check.moments([self.journal(self.rows(holding_beef(), 'put counter1')[0])])[0]
        order = []

        def ask(payload):
            order.append('reach_note' if 'reach' in payload['state']['rules'] else 'as_logged')
            if len(order) > 2:
                raise RuntimeError('quota')
            return {'choice': 'wait', 'probabilities': {'wait': 1.0}, 'model': 'fake'}
        report = check.run([item, item], ask)
        self.assertEqual(order, ['as_logged', 'reach_note', 'as_logged', 'reach_note'])
        self.assertEqual(report['arms']['reach_note']['pass_probability_change']['moments'], 1)   # the whole first pair

    def test_local_asks_this_computer_without_the_saved_connection(self):
        from unittest.mock import patch
        from scripts import reach_note_check as check
        from player_api import DecisionClient
        with patch('scripts.jev_replay_check.client', side_effect=AssertionError('the saved connection must not be read')), \
             patch('jev.load_key', side_effect=AssertionError('the Jev key must not be read')):
            client = check.local_client('http://127.0.0.1:8090/v1/systemone', 'startlux-local-2b-instant-q4')
        self.assertIsInstance(client, DecisionClient)
        self.assertEqual((client.key, client.endpoint), ('', 'http://127.0.0.1:8090/v1/systemone'))
        with self.assertRaises(ValueError):
            check.local_client('https://api.bamboonode.dev/v1/decisions', 'm')

class BambooKeyFileTests(unittest.TestCase):
    def test_the_key_file_must_be_private_and_the_key_only_goes_to_bamboo(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from scripts import reach_note_check as check
        from player_api import DecisionClient
        path = Path(tempfile.mkdtemp()) / 'bamboo.key'
        path.write_text('test-bamboo-key-never-real\n')
        os.chmod(path, 0o644)
        with self.assertRaises(SystemExit):
            check.bamboo_client(path)
        os.chmod(path, 0o600)
        with patch('jev.load_key', side_effect=AssertionError('the Jev key must not be read')):
            client = check.bamboo_client(path)
        self.assertIsInstance(client, DecisionClient)
        self.assertEqual((client.endpoint, client.key, client.timeout),
                         ('https://api.bamboonode.dev/v1/decisions', 'test-bamboo-key-never-real', 120))
        with self.assertRaises(SystemExit):
            check.bamboo_client(path.parent / 'missing.key')
        path.write_text('\x1b[Atest-bamboo-key-never-real')            # an arrow key pressed before pasting
        with self.assertRaises(SystemExit) as refused:
            check.bamboo_client(path)
        self.assertNotIn('test-bamboo-key', str(refused.exception))      # says what is wrong, never the key

class SpaceClientTests(unittest.TestCase):
    """--hf-space: the Gradio /decide call, read like the game's decision client; no network here."""

    def client(self, answer, event='complete'):
        import io
        from unittest.mock import Mock
        from scripts.reach_note_check import SpaceClient
        sent = []

        def open_(request, timeout=None):
            sent.append(request)
            if request.get_method() == 'POST':
                return io.BytesIO(b'{"event_id": "e1"}')
            return io.BytesIO(f'event: {event}\ndata: {json.dumps(["<html>", answer])}\n\n'.encode())
        return SpaceClient(opener=Mock(open=open_)), sent

    def payload(self):
        return {'model': 'm', 'state': {'kitchen': {}}, 'questions': {'next_action': {'type': 'choice', 'criteria': {'wait': '等待', 'throw partner': '扔给搭档'}}}}

    def test_it_sends_state_and_questions_as_the_decision_client_and_reads_the_answer(self):
        answer = {'answers': {'next_action': {'type': 'choice', 'choice': 'throw partner', 'confidence': .5,
                                              'probabilities': {'wait': .2, 'throw partner': .8}}}, 'usage': {'input_tokens': 9}}
        client, sent = self.client(answer)
        result = client.ask(self.payload())
        self.assertEqual(sent[0].full_url, 'https://startlux-models-startlux-decision-27b-autothink.hf.space/gradio_api/call/decide')
        data = json.loads(sent[0].data)['data']
        self.assertEqual(json.loads(data[0]), {'kitchen': {}})
        self.assertEqual(set(json.loads(data[1])['next_action']['criteria']), {'wait', 'throw partner'})
        self.assertEqual((data[3], data[8]), ('never', False))           # think_mode never, allow_none off
        self.assertEqual(sent[1].full_url, 'https://startlux-models-startlux-decision-27b-autothink.hf.space/gradio_api/call/decide/e1')
        self.assertEqual((result['choice'], result['probabilities']['throw partner'], result['model']),
                         ('throw partner', .8, 'hf-space:startlux-models/startlux-decision-27b-autothink'))
        self.assertIsNone(sent[0].get_header('Authorization'))

    def test_a_token_goes_to_the_space_on_both_calls(self):
        answer = {'answers': {'next_action': {'type': 'choice', 'choice': 'wait', 'probabilities': {'wait': 1.0}}}}
        client, sent = self.client(answer)
        client.headers = {'Authorization': 'Bearer hf_test_never_real'}
        client.ask(self.payload())
        self.assertEqual([r.get_header('Authorization') for r in sent], ['Bearer hf_test_never_real'] * 2)
        self.assertTrue(all(r.full_url.startswith('https://startlux-models-startlux-decision-27b-autothink.hf.space/') for r in sent))

    def test_an_answer_outside_the_options_or_an_error_is_refused(self):
        outside = {'answers': {'next_action': {'type': 'choice', 'choice': None, 'probabilities': {}}}}
        with self.assertRaises(RuntimeError):
            self.client(outside)[0].ask(self.payload())
        with self.assertRaises(RuntimeError):
            self.client(None, event='error')[0].ask(self.payload())

if __name__ == '__main__':
    unittest.main()
