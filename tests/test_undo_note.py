"""Undo notes (undo_note.py, trial switch undo_note): a fact on the options that would take back Jeff's last step."""
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
from test_jeff_plan import Inline
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
        self.ai.undo = {'step': None} if undo else None
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
    def test_after_put_then_take_both_ways_back_carry_a_note(self):
        # Jeff holds bread, lettuce lies on board 1: he puts the bread on counter 16 and takes the lettuce.
        loop = Loop(bread_and_lettuce(), [{'choice': 'put then take b1', 'put_where': 'put counter16'}])
        first = loop.until_asked(1)
        self.assertEqual(noted(first), {})                                       # no step yet
        self.assertEqual(first['state']['undo_note_version'], undo_note.VERSION)
        second = loop.until_asked(2)
        self.assertEqual(loop.k.stations['counter16'].food.ingredient, 'bread')
        self.assertEqual(loop.k.chefs['jeff'].hand.ingredient, 'lettuce')
        notes = noted(second)
        t = f"{loop.rows('ai_request')[1]['undo_note']['step']['t']:.1f}"
        self.assertEqual(notes[('next_action', 'put then take counter16')],
                         second['questions']['next_action']['criteria']['put then take counter16'])
        self.assertIn(f'(Note: this takes back the Bread you put on Counter 16 at {t} s.)', notes[('next_action', 'put then take counter16')])
        self.assertIn(f'(Note: this puts the Lettuce back on Board 1, where you took it at {t} s.)', notes[('put_where', 'put b1')])
        self.assertIn(('next_action', 'put b1'), notes)
        self.assertEqual({key for _, key in notes}, {'put then take counter16', 'put b1'})
        # Only the labels change: same questions, same keys, same state apart from the version.
        plain = deepcopy(second)
        for (q, key) in notes:
            plain['questions'][q]['criteria'][key] = plain['questions'][q]['criteria'][key].split(' (Note: ')[0]
        self.assertEqual(noted(plain), {})
        step = loop.rows('ai_request')[1]['undo_note']['step']
        self.assertEqual((step['put']['station'], step['take']['station']), ('counter16', 'b1'))

    def test_the_note_needs_the_same_item_still_there(self):
        loop = Loop(bread_and_lettuce(), [{'choice': 'put then take b1', 'put_where': 'put counter16'}], undo=False)
        sent = loop.until_asked(2)
        step = undo_note.step(loop.rows('ai_response')[0]['current_state'], 'put then take b1', 'put counter16', 5.0)
        moved = deepcopy(sent)
        moved['state']['kitchen']['stations']['counter16']['food'] = None        # someone took the bread meanwhile
        undo_note.apply(moved, {'step': step})
        self.assertEqual({key for _, key in noted(moved)}, {'put b1'})           # only the lettuce can still go back
        other = deepcopy(sent)
        other['state']['kitchen']['chefs']['jeff']['holding']['id'] = 'F999'     # a different item in his hand
        undo_note.apply(other, {'step': step})
        self.assertEqual({key for _, key in noted(other)}, {'put then take counter16'})

    def test_walking_keeps_the_step_and_another_step_replaces_it(self):
        replies = [{'choice': 'put then take b1', 'put_where': 'put counter16'}, {'choice': 'go p1'}, {'choice': 'put counter14'}]
        loop = Loop(bread_and_lettuce(), replies)
        loop.until_asked(2)
        third = loop.until_asked(3)                                              # after walking to the stove
        self.assertIn('put then take counter16', {key for _, key in noted(third)})
        fourth = loop.until_asked(4)                                             # after putting the lettuce elsewhere
        self.assertEqual(loop.k.stations['counter14'].food.ingredient, 'lettuce')
        self.assertNotIn('put then take counter16', {key for _, key in noted(fourth)})
        self.assertEqual(loop.rows('ai_request')[3]['undo_note']['step']['put']['station'], 'counter14')

    def test_switch_off_changes_nothing(self):
        on, off = Loop(bread_and_lettuce(), [{'choice': 'put then take b1', 'put_where': 'put counter16'}]), \
            Loop(bread_and_lettuce(), [{'choice': 'put then take b1', 'put_where': 'put counter16'}], undo=False)
        a, b = on.until_asked(2), off.until_asked(2)
        self.assertEqual(noted(b), {})
        self.assertNotIn('undo_note_version', b['state'])
        self.assertTrue(all('undo_note' not in row for row in off.rows('ai_request')))
        undo_note.apply(b, on.rows('ai_request')[1]['undo_note'])
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))  # the switch adds exactly this

    def test_the_feature_is_a_trial_off_by_default(self):
        current = features.current()
        self.assertEqual(current['undo_note'], {'stage': 'trial', 'on': False, 'player_switch': False, 'version': undo_note.VERSION})
        self.assertIsNone(features.undo_start(current))
        self.assertEqual(features.undo_start({**current, 'undo_note': {**current['undo_note'], 'on': True}}), {'step': None})


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
            self.assertEqual(json.dumps(undo_note_check.arm(items[0], 'undo_note'), sort_keys=True),
                             json.dumps(on.client.asked[1], sort_keys=True))      # exactly what the switch sends
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
