"""scripts/option_count_check.py and the no_aimed_throws arm of scripts/walk_label_check.py, on small journals."""
from copy import deepcopy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import jev_replay_check, option_count_check, walk_label_check
from test_jev_checks import journal, payloads


class OptionCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty, cls.full = payloads()

    def folder(self, journals):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for name, text in journals.items():
            Path(folder.name, name).write_text(text, encoding='utf-8')
        return folder.name

    def test_requests_are_grouped_by_rules_version_and_split_by_option_count(self):
        older = deepcopy(self.full)
        older['state']['rules_version'] = 'rules-v6'
        few = len(self.empty['questions']['next_action']['criteria'])
        many = len(self.full['questions']['next_action']['criteria'])
        self.assertLess(few, many)
        logs = self.folder({'old.jsonl': journal('2026-09-30', [(older, 'go serve')]),
                            'new.jsonl': journal('2026-11-04', [(self.full, 'go serve'), (self.full, 'assemble plates'),
                                                                (self.empty, 'wait')], model='jev-1.14.0'),
                            'chat.jsonl': journal('2026-11-04', [(self.full, 'go p1')], model='deepseek-flash')})
        report = option_count_check.report(jev_replay_check.journal_requests([logs]), split=few)
        versions = report['rules_versions']
        now = self.full['state']['rules_version']
        self.assertEqual(set(versions), {'rules-v6', now})
        self.assertEqual((versions['rules-v6']['requests'], versions[now]['requests'], versions[now]['rounds']), (1, 3, 1))
        group = versions[now]
        self.assertEqual((group['most_options'], group[f'share_above_{few}']), (many, round(2 / 3, 3)))
        self.assertEqual(group[f'at_most_{few}']['all']['chose_wait'], 1.0)
        above = group[f'above_{few}']['hands_full']
        self.assertEqual((above['requests'], above['chose_walk'], above['chose_a_step_of_the_dish']), (2, .5, .5))

    def test_the_command_line_reads_and_prints(self):
        logs = self.folder({'new.jsonl': journal('2026-11-04', [(self.full, 'go serve')], model='jev-1.14.0')})
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(option_count_check.main([logs]), 0)
            self.assertEqual(option_count_check.main([logs, '--since', '2026-12-01']), 1)
        self.assertEqual(json.loads(out.getvalue().split('\nno answered')[0])['split'], 25)


class NoAimedThrowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty, cls.full = payloads()

    def test_only_the_aimed_throws_go(self):
        before = self.full['questions']['next_action']['criteria']
        after = walk_label_check.without_aimed_throws(self.full)['questions']['next_action']['criteria']
        gone = set(before) - set(after)
        self.assertTrue(gone)
        self.assertTrue(all(k.startswith('throw ') for k in gone))
        self.assertIn('throw partner', after)
        self.assertEqual({k: before[k] for k in after}, after)
        self.assertEqual(walk_label_check.arm(self.full, 'as_logged'), self.full)

    def test_the_arms_flag_picks_what_is_sent(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        Path(folder.name, 'today.jsonl').write_text(journal('2026-11-04', [(self.full, 'go serve')], model='jev-1.14.0'))
        err = io.StringIO()
        with patch.object(walk_label_check, 'client', side_effect=AssertionError('no client in a dry run')), \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            self.assertEqual(walk_label_check.main([folder.name, '--arms', 'as_logged,no_aimed_throws', '--dry-run']), 0)
            with self.assertRaises(SystemExit):
                walk_label_check.main([folder.name, '--arms', 'as_logged,dance', '--dry-run'])
        self.assertIn('2 requests', err.getvalue())
        items = [i for i in jev_replay_check.journal_requests([folder.name]) if walk_label_check.picked(i)]
        report = walk_label_check.run(items, lambda p: {'choice': 'wait', 'model': 'jev-1.14.0'}, ('as_logged', 'no_aimed_throws'))
        self.assertEqual(set(report['arms']), {'as_logged', 'no_aimed_throws'})
        self.assertLess(report['arms']['no_aimed_throws']['all']['mean_options'], report['arms']['as_logged']['all']['mean_options'])


if __name__ == '__main__':
    unittest.main()
