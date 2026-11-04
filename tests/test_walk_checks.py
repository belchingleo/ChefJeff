"""scripts/walk_label_check.py on a small journal, with a stand-in for Jev, and the walk groups of hands_full_check."""
from copy import deepcopy
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import hands_full_check, jev_replay_check, walk_label_check
from test_jev_checks import journal, payloads

SUFFIX = '; no other listed action is at {} now'


class WalkLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty, cls.full = payloads()

    def folder(self, journals):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for name, text in journals.items():
            Path(folder.name, name).write_text(text, encoding='utf-8')
        return folder.name

    def test_only_the_walk_labels_change(self):
        before = self.full['questions']['next_action']['criteria']
        after = walk_label_check.label(self.full)['questions']['next_action']['criteria']
        self.assertEqual(list(after), list(before))
        for key, text in after.items():
            with self.subTest(key):
                if walk_label_check.walk(key):
                    self.assertEqual(text, before[key] + SUFFIX.format(key[3:]))
                else:
                    self.assertEqual(text, before[key])
        self.assertIn('go partner', before)
        self.assertEqual(walk_label_check.label(self.full)['state'], self.full['state'])
        self.assertEqual(self.full['questions']['next_action']['criteria'], before)     # the logged request is untouched

    def test_a_station_another_key_names_keeps_its_label(self):
        payload = deepcopy(self.full)
        criteria = payload['questions']['next_action']['criteria']
        criteria['put serve'] = 'Put it at Serve'
        self.assertEqual(walk_label_check.label(payload)['questions']['next_action']['criteria']['go serve'], criteria['go serve'])

    def test_the_arms_compare_walks_and_steps(self):
        logs = self.folder({'today.jsonl': journal('2026-11-04', [(self.full, 'go serve'), (self.full, 'drop'),
                                                                   (self.empty, 'go p1'), (self.empty, 'go partner')],
                                                   model='jev-1.14.0')})
        items = [i for i in jev_replay_check.journal_requests([logs], '2026-11-04') if walk_label_check.picked(i)]
        self.assertEqual([i['logged_choice'] for i in items], ['go serve', 'go p1'])     # not drop, not go partner

        def ask(payload):
            criteria = payload['questions']['next_action']['criteria']
            labeled = any(text.endswith(' now') for text in criteria.values())
            if not labeled:
                return {'choice': 'go serve' if jev_replay_check.hands_full(payload) else 'go p1', 'model': 'jev-1.14.0'}
            return {'choice': 'assemble plates' if 'assemble plates' in criteria else 'fetch bread', 'model': 'jev-1.14.0'}
        report = walk_label_check.run(items, ask)
        self.assertEqual((report['moments'], report['hands_full']), (2, 1))
        logged, labeled = report['arms']['as_logged'], report['arms']['walks_labeled']
        self.assertEqual((logged['all']['same_as_logged'], logged['all']['chose_walk']), (1.0, 1.0))
        self.assertEqual((labeled['hands_full']['chose_a_step_of_the_dish'], labeled['hands_empty']['chose_take']), (1.0, 1.0))
        self.assertEqual(labeled['all']['chose_walk'], 0.0)

    def test_a_dry_run_sends_nothing(self):
        logs = self.folder({'today.jsonl': journal('2026-11-04', [(self.full, 'go serve')], model='jev-1.14.0')})
        out, err = io.StringIO(), io.StringIO()
        with patch.object(walk_label_check, 'client', side_effect=AssertionError('no client in a dry run')), \
                redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(walk_label_check.main([logs, '--dry-run']), 0)
            self.assertEqual(walk_label_check.main([logs, '--since', '2026-12-01', '--dry-run']), 1)
        self.assertIn('2 requests', err.getvalue())         # one moment, two arms

    def test_hands_full_groups_name_where_walks_went(self):
        moments = [{'payload': self.full, 'logged_choice': key, 'round': 1} for key in ('go serve', 'go p1', 'go partner', 'wait')]
        walks = hands_full_check.groups(moments)['walks']
        self.assertEqual(walks, {'count': 3, 'to': {'serving_window': 1, 'stove': 1, 'partner': 1}, 'by_held': {'ingredient': 3},
                                 'on_station': {'empty': 1, 'empty_pan': 1, 'partner': 1},
                                 'held_and_on_station': {'ingredient -> empty': 1, 'ingredient -> empty_pan': 1,
                                                         'ingredient -> partner': 1}})
        board = deepcopy(self.full)
        board['state']['kitchen']['stations']['b1']['food'] = {'id': 'F7', 'stage': 'chopped', 'ingredient': 'lettuce'}
        moment = [{'payload': board, 'logged_choice': 'go b1', 'round': 1}]
        self.assertEqual(hands_full_check.groups(moment)['walks']['held_and_on_station'], {'ingredient -> ingredient': 1})


if __name__ == '__main__':
    unittest.main()
