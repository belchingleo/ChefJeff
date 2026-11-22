"""Undo notes (undo_note.py, trial switch undo_note): a fact on the options that would bring back how things were
before one of Jeff's last steps (undo-note-v4, from the engine); scripts/undo_note_check.py keeps re-asking v3's."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import features
import undo_note
from jev import DecisionLoop
from scripts import undo_note_check
from loop_helpers import Inline
from test_one_press import BOTH, Answering, bread_and_lettuce


def noted(payload):
    """{(question, key): label} of the options that carry a note."""
    return {(q, key): label for q in undo_note.QUESTIONS
            for key, label in payload['questions'].get(q, {}).get('criteria', {}).items() if '(Note: ' in label}


class Loop:
    """Jeff's decision loop on a kitchen, answering the queued replies; the undo switch on or off."""

    def __init__(self, k, replies, undo=True):
        self.k, self.records = k, []
        self.client = Answering(k.c, replies)
        self.ai = DecisionLoop(k, self.client, lambda kind, data: self.records.append((kind, data)), lambda _: None)
        self.ai.one_press = dict(BOTH)
        self.ai.undo = {'history': []} if undo else None
        self.ai.player_messages = []
        self.clock = 1000.

    def run(self, polls=1):
        for _ in range(polls):
            for _ in range(4):
                self.k.advance(.05)
            self.ai.last_revision = -1
            self.clock += 3.
            with patch('jev.time.monotonic', lambda: self.clock), patch('jev.threading.Thread', Inline):
                self.ai.poll()

    def until_asked(self, n, limit=80):
        for _ in range(limit):
            if len(self.client.asked) >= n:
                return self.client.asked[n - 1]
            self.run()
        raise AssertionError(f'Jeff was not asked {n} times')

    def rows(self, kind):
        return [d for kd, d in self.records if kd == kind]


class NoteTests(unittest.TestCase):
    """undo-note-v4: the engine finds an option that brings back how things were before one of Jeff's last steps."""

    def test_after_put_then_take_the_swap_back_carries_a_note(self):
        # Jeff holds bread, lettuce lies on board 1: he puts the bread on counter 16 and takes the lettuce.
        loop = Loop(bread_and_lettuce(), [{'choice': 'put then take b1', 'put_where': 'put counter16'}])
        first = loop.until_asked(1)
        self.assertEqual(noted(first), {})                                       # no step yet
        self.assertEqual(loop.rows('ai_request')[0]['payload']['state']['undo_note_version'], undo_note.VERSION)   # in the record
        self.assertNotIn('undo_note_version', first['state'])                    # not sent to the model
        second = loop.until_asked(2)
        history = loop.rows('ai_request')[1]['undo_note']['history']
        self.assertEqual([h['places'] for h in history], [['b1', 'counter16', 'hand']])
        t = f"{history[0]['t']:.1f}"
        self.assertEqual(noted(second), {('next_action', 'put then take counter16'):
            second['questions']['next_action']['criteria']['put then take counter16']})
        self.assertIn(f'(Note: putting the held item on Board 1 first, this brings back how things were at {t} s, before '
                      f'your last step: bread (as fetched) in your hands, lettuce (as fetched) on Board 1.)',
                      noted(second)[('next_action', 'put then take counter16')])
        # Only the labels change: same questions, same keys, same state apart from the version.
        plain = deepcopy(second)
        for (q, key) in noted(second):
            plain['questions'][q]['criteria'][key] = plain['questions'][q]['criteria'][key].split(' (Note: ')[0]
        self.assertEqual(noted(plain), {})

    def test_a_return_over_linked_steps_is_noted_and_separate_undos_do_not_join(self):
        # Bread to counter 16 and the lettuce taken, then the lettuce back on board 1: taking the bread again brings back
        # the start, two steps linked through board 1.
        loop = Loop(bread_and_lettuce(), [{'choice': 'put then take b1', 'put_where': 'put counter16'}, {'choice': 'put b1'}])
        third = loop.until_asked(3)
        history = loop.rows('ai_request')[2]['undo_note']['history']
        self.assertEqual(len(history), 2)
        self.assertIn(f"(Note: this brings back how things were at {history[0]['t']:.1f} s, before your last 2 steps: bread "
                      f"(as fetched) in your hands, lettuce (as fetched) on Board 1.)",
                      third['questions']['next_action']['criteria']['take counter16'])
        # Bread put down, lettuce taken and put back: two separate undos, not one return of three steps.
        loop = Loop(bread_and_lettuce(), [{'choice': 'put counter16'}, {'choice': 'take b1'}, {'choice': 'put b1'}])
        fourth = loop.until_asked(4)
        self.assertEqual(len(loop.rows('ai_request')[3]['undo_note']['history']), 3)
        self.assertEqual({key for _, key in noted(fourth)}, {'take b1'})         # only the last step's own undo

    def test_an_empty_chain_that_puts_first_records_its_put(self):
        """one-press v8's "empty <stove>" puts down what Jeff holds first, as put then take does; its take is not a
        step to undo (the pan comes back emptied)."""
        k = bread_and_lettuce()
        snapshot = k.snapshot()
        held = snapshot['chefs']['jeff']['holding']
        step = undo_note.step(snapshot, 'empty p1', 'put counter16', 12.0)
        self.assertEqual(step, {'t': 12.0, 'put': {'station': 'counter16', 'id': held['id']}, 'take': None})
        self.assertEqual(undo_note.step(snapshot, 'put then take b1', 'put counter16', 12.0)['put'], step['put'])

    def test_the_note_needs_things_as_they_were(self):
        k = bread_and_lettuce()
        step = undo_note.record(k, next(a for a in k.actions('jeff') if a.key == 'put counter16'))
        k.start('jeff', next(a for a in k.actions('jeff') if a.key == 'put counter16'))
        while k.chefs['jeff'].job is not None:
            k.advance(0.05)
        self.assertIn('take counter16', undo_note.returns(k, [step], ['take counter16']))
        k.stations['counter16'].food.stage = 'chopped'                           # changed meanwhile: no return
        self.assertEqual(undo_note.returns(k, [step], ['take counter16']), {})

    def test_a_request_asked_ahead_carries_the_note_of_the_step_under_way(self):
        # (v2) ask_ahead asks with the switch on: the step under way is in the history as it starts.
        loop = Loop(bread_and_lettuce(), [{'choice': 'put counter16'}])
        loop.ai.ask_ahead = True
        loop.ai.reply_times = [5.0]           # replies slower than any step: each step is asked about ahead
        loop.until_asked(1)
        second = loop.until_asked(2)
        row = loop.rows('ai_request')[1]
        self.assertTrue(row.get('ask_ahead'))
        self.assertEqual(row['undo_note']['history'][-1]['places'], ['counter16', 'hand'])
        self.assertEqual({key for _, key in noted(second)}, {'take counter16'})

    def test_a_pan_lifted_and_put_straight_back_on_its_stove_carries_a_note_both_ways(self):
        from test_burn_note import cooked_pan, do
        k = cooked_pan()
        acts = {a.key: a for a in k.actions('jeff')}
        lift = undo_note.record(k, acts['take pot p1'])
        do(k, 'take pot p1')
        self.assertIn('this brings back how things were at', undo_note.returns(k, [lift], ['put pot p1'])['put pot p1'])
        self.assertIn('frying pan with beef (cooked) on Stove 1, your hands empty',
                      undo_note.returns(k, [lift], ['put pot p1'])['put pot p1'])
        put = undo_note.record(k, {a.key: a for a in k.actions('jeff')}['put pot p1'])
        do(k, 'put pot p1')
        self.assertIn('frying pan with beef (cooked) in your hands', undo_note.returns(k, [put], ['take pot p1'])['take pot p1'])

    def test_waiting_walking_and_throwing_are_no_step_and_the_history_keeps_four(self):
        k = bread_and_lettuce()
        acts = {a.key: a for a in k.actions('jeff')}
        for key in ('wait', 'go p1', 'throw partner'):
            if key in acts:
                self.assertIsNone(undo_note.record(k, acts[key]), key)
        state = {'history': []}
        for _ in range(6):
            state = undo_note.remember(state, undo_note.record(k, acts['put counter16']))
        self.assertEqual(len(state['history']), undo_note.HISTORY)
        self.assertEqual(undo_note.remember(state, None), state)

    def test_switch_off_changes_nothing(self):
        on, off = Loop(bread_and_lettuce(), [{'choice': 'put then take b1', 'put_where': 'put counter16'}]), \
            Loop(bread_and_lettuce(), [{'choice': 'put then take b1', 'put_where': 'put counter16'}], undo=False)
        on.until_asked(2), off.until_asked(2)
        a, b = on.rows('ai_request')[1]['payload'], off.rows('ai_request')[1]['payload']     # as recorded, tags included
        self.assertEqual(noted(b), {})
        self.assertNotIn('undo_note_version', b['state'])
        self.assertTrue(all('undo_note' not in row for row in off.rows('ai_request')))
        undo_note.apply(b, on.rows('ai_request')[1]['undo_note'], off.k)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))  # the switch adds exactly this

    def test_the_feature_is_a_trial_off_by_default(self):
        current = features.current()
        self.assertEqual(current['undo_note'], {'stage': 'trial', 'on': False, 'version': undo_note.VERSION})
        self.assertIsNone(features.undo_start(current))
        self.assertEqual(features.undo_start({**current, 'undo_note': {**current['undo_note'], 'on': True}}), {'history': []})


class CheckTests(unittest.TestCase):
    """scripts/undo_note_check.py finds the same notes from a round's journal as the loop showed."""

    def journal(self, folder, rows):
        path = Path(folder, 'round.jsonl')
        start = {'kind': 'start', 'wall_time': '2026-11-06T00:00:00+00:00'}
        path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in [start] + rows) + '\n', encoding='utf-8')
        return path

    def logged_round(self):
        """A switch-off round where Jeff swaps back: the requests and answers as the journal keeps them."""
        replies = [{'choice': 'put then take b1', 'put_where': 'put counter16'},
                   {'choice': 'put then take counter16', 'put_where': 'put b1'}, {'choice': 'wait'}]
        loop = Loop(bread_and_lettuce(), replies, undo=False)
        loop.until_asked(3)
        on = Loop(bread_and_lettuce(), replies)
        on.until_asked(3)
        rows = []
        for kind, data in loop.records:
            if kind in ('ai_request', 'ai_response'):
                rows.append({'kind': kind, **deepcopy(data), **({'model': 'jev-test'} if kind == 'ai_response' else {})})
        return rows, on

    def test_it_rebuilds_the_loops_notes_and_reports_the_arms(self):
        rows, on = self.logged_round()
        with tempfile.TemporaryDirectory() as folder:
            path = self.journal(folder, rows)
            items = undo_note_check.moments([str(path)])
            self.assertEqual(len(items), 1)                                       # the second request: the swap back is listed
            self.assertEqual(items[0]['logged_choice'], 'put then take counter16')
            v3 = deepcopy(items[0]['payload'])
            undo_note.apply_v3(v3, {'step': items[0]['step']})
            self.assertEqual(json.dumps(undo_note_check.arm(items[0], 'undo_note'), sort_keys=True),
                             json.dumps(v3, sort_keys=True))                      # exactly what undo-note-v3 added
            self.assertEqual(v3['state']['undo_note_version'], undo_note.V3_VERSION)
            self.assertEqual(undo_note_check.arm(items[0], 'as_logged'), items[0]['payload'])
            self.assertEqual(undo_note_check.took_back(items[0], 'put then take counter16', 'put b1'), (True, True))
            self.assertEqual(undo_note_check.took_back(items[0], 'put then take counter16', 'put counter17'), (True, False))

            def ask(payload):                       # takes the swap back unless a note is on it
                criteria = payload['questions']['next_action']['criteria']
                back = 'put then take counter16'
                return {'choice': 'wait' if '(Note: ' in criteria[back] else back, 'put_where': 'put b1'}
            report = undo_note_check.run(items, ask, repeats=2)
            self.assertEqual(report['logged']['full_swap'], 1.0)
            self.assertEqual(report['arms']['as_logged']['full_swap'], 1.0)
            self.assertEqual(report['arms']['undo_note']['took_back'], 0.0)
            self.assertEqual(report['arms']['undo_note']['asked'], 2)

            out, err = io.StringIO(), io.StringIO()
            with patch.object(undo_note_check, 'client', side_effect=AssertionError('no client in a dry run')), \
                    redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(undo_note_check.main([str(path), '--dry-run']), 0)
            self.assertIn('4 requests', err.getvalue())                            # one moment, two arms, twice each
            self.assertNotIn('Bread', out.getvalue() + err.getvalue())             # counts only


if __name__ == '__main__':
    unittest.main()
