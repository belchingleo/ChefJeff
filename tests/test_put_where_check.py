"""scripts/put_where_check.py on a real one-press round, with a stand-in for Jev: re-asking, not replaying rounds."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import put_where_check
import test_one_press


class PutWhereCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        test_one_press.StatsTests('test_rounds_with_a_switch_on_are_counted_apart').play(cls.folder.name, on=True)
        cls.logs = str(Path(cls.folder.name, 'logs'))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_it_picks_one_press_answers_to_put_where_requests(self):
        items = put_where_check.moments([self.logs], model_prefix='test')
        self.assertTrue(items)
        for item in items:
            self.assertIn('put_where', item['payload']['questions'])
            self.assertTrue(item['logged_choice'].startswith(('put then ', 'wash from ')))
        rows = [json.loads(line) for path in Path(self.logs).glob('*.jsonl') for line in path.read_text().splitlines()]
        self.assertEqual(len(items), sum(r['kind'] == 'ai_response' and str(r.get('choice')).startswith(('put then ', 'wash from '))
                                         and r.get('put_where') is not None for r in rows))
        self.assertEqual(put_where_check.moments([self.logs]), [])                     # Jev rounds only by default

    def test_plain_drop_changes_only_the_floor_note(self):
        item = put_where_check.moments([self.logs], model_prefix='test')[0]
        payload = json.loads(json.dumps(item['payload']))
        payload['questions']['put_where']['criteria']['drop'] += ' (recoverable, no charge)'
        payload['questions']['next_action']['criteria']['drop'] += ' (recoverable, no charge)'
        plain = put_where_check.arm(payload, 'plain_drop')
        for question in ('next_action', 'put_where'):
            before, after = payload['questions'][question]['criteria'], plain['questions'][question]['criteria']
            self.assertEqual(list(after), list(before))
            self.assertEqual([k for k in after if after[k] != before[k]], ['drop'])
            self.assertNotIn('recoverable', after['drop'])
        self.assertEqual(put_where_check.arm(payload, 'as_logged'), payload)
        self.assertEqual(plain['state'], payload['state'])

    def test_the_arms_report_where_he_puts_things(self):
        items = put_where_check.moments([self.logs], model_prefix='test')
        for item in items:                       # the logged requests as they were sent before 2026-11-06
            for question in ('next_action', 'put_where'):
                item['payload']['questions'][question]['criteria']['drop'] += ' (recoverable, no charge)'

        def ask(payload):                        # takes the floor while its note is there, else the first counter
            places = payload['questions']['put_where']['criteria']
            choice = next(k for k in payload['questions']['next_action']['criteria'] if k.startswith(('put then ', 'wash from ')))
            floor = 'recoverable' in places['drop']
            return {'choice': choice, 'put_where': 'drop' if floor else next(k for k in places if k != 'drop')}
        report = put_where_check.run(items, ask)
        self.assertEqual(report['moments'], len(items))
        self.assertEqual(report['arms']['as_logged']['floor_share'], 1.0)
        self.assertEqual(report['arms']['plain_drop']['floor_share'], 0.0)
        self.assertEqual(report['arms']['plain_drop']['chose_one_press'], 1.0)
        self.assertTrue(set(report['arms']['plain_drop']['put_where_places']) <= {'counter', 'board', 'supply'})

    def test_a_dry_run_sends_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(put_where_check, 'client', side_effect=AssertionError('no client in a dry run')), \
                redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(put_where_check.main([self.logs, '--dry-run']), 1)        # no Jev rounds here
        real = put_where_check.moments
        with patch.object(put_where_check, 'client', side_effect=AssertionError('no client in a dry run')), \
                patch.object(put_where_check, 'moments', lambda paths, since=None, until=None: real(paths, since, until, 'test')), \
                redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(put_where_check.main([self.logs, '--dry-run', '--sample', '3']), 0)
        self.assertIn('6 requests', err.getvalue())                                     # three moments, two arms


if __name__ == '__main__':
    unittest.main()
