"""scripts/reask.py: the shared ask loop, the statistics every re-ask check reports, and the one entry point."""
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import jev_replay_check, reask, walk_label_check
from test_jev_checks import journal, payloads


def item(n, logged='a'):
    return {'payload': {'n': n}, 'logged_choice': logged, 'round': 1}


def ask_once(ask, payload):
    try:
        return {'choice': ask(payload)['choice']}
    except RuntimeError as error:
        return {'error': str(error)}


class AskArmsTests(unittest.TestCase):
    def test_every_arm_asks_every_moment_in_one_order(self):
        seen = []

        def ask(payload):
            seen.append(payload['tag'])
            return {'choice': 'a', 'model': 'm1'}
        asked = reask.ask_arms([item(1), item(2)], ('x', 'y'), lambda i, arm: {'tag': f"{arm}{i['payload']['n']}"},
                               ask, ask_once, repeats=2)
        self.assertEqual(seen, ['x1', 'x1', 'x2', 'x2', 'y1', 'y1', 'y2', 'y2'])     # arm, then moment, then repeat
        self.assertEqual([len(replies) for _, _, replies in asked['arms']['y']], [2, 2])
        self.assertEqual(asked['models'], {'m1': 8})


class StatsTests(unittest.TestCase):
    def asked(self, first, second, repeats=1, models=None):
        """Two arms over the same moments; first/second are each moment's choices (None: the client refused)."""
        def rows(choices):
            return [(item(n), {'n': n}, [{'error': 'HTTP 429'} if c is None else {'choice': c}] * repeats)
                    for n, c in enumerate(choices)]
        return {'arms': {'as_logged': rows(first), 'changed': rows(second)}, 'models': models or {'jev-1': 10}}

    def test_shares_intervals_and_paired_differences(self):
        out = reask.stats(self.asked(['a', 'b', 'b', 'b', None], ['a', 'a', 'a', 'b', 'a']),
                          {'chose_a': lambda i, p, a: a['choice'] == 'a'})
        self.assertEqual(out['outcomes']['chose_a']['as_logged'], {'k': 1, 'n': 4, 'share': .25, 'ci95': [0.046, 0.699]})
        self.assertEqual(out['outcomes']['chose_a']['changed']['k'], 4)
        self.assertEqual(out['paired_with'], 'as_logged')
        self.assertEqual(out['paired']['chose_a']['changed'],          # the refused moment is left out of the pairs
                         {'moments': 4, 'only_second': 2, 'only_first': 0, 'difference': .5, 'mcnemar_p': .5})
        self.assertEqual(out['repeat_agreement'], {})                  # asked once each: no spread to report

    def test_an_outcome_that_does_not_apply_is_left_out(self):
        out = reask.stats(self.asked(['a', 'b'], ['a', 'b']), {'a_only': lambda i, p, a: True if a['choice'] == 'a' else None})
        self.assertEqual(out['outcomes']['a_only']['as_logged'], {'k': 1, 'n': 1, 'share': 1.0, 'ci95': [0.207, 1.0]})

    def test_repeats_give_the_models_own_spread(self):
        def rows(pairs):
            return [(item(n), {'n': n}, [{'choice': x}, {'choice': y}]) for n, (x, y) in enumerate(pairs)]
        out = reask.stats({'arms': {'as_logged': rows([('a', 'a'), ('a', 'b')]), 'changed': rows([('b', 'b')])},
                           'models': {'jev-1': 6}}, {})
        self.assertEqual(out['repeat_agreement']['as_logged']['share'], .5)
        self.assertEqual(out['repeat_agreement']['changed']['share'], 1.0)

    def test_a_single_model_is_named_as_a_limit(self):
        self.assertIn('one model', reask.stats(self.asked(['a'], ['a']), {})['note'])
        self.assertNotIn('note', reask.stats(self.asked(['a'], ['a'], models={'jev-1': 1, 'deepseek': 1}), {}))


class ChecksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.empty, cls.full = payloads()

    def test_a_check_reports_stats_beside_its_own_shares(self):
        items = [i for i in jev_replay_check.journal_requests(
            [self.logs([(self.full, 'go serve'), (self.empty, 'go p1')])]) if walk_label_check.picked(i)]
        report = walk_label_check.run(items, lambda payload: {'choice': 'wait', 'model': 'jev-1'})
        self.assertEqual(report['arms']['as_logged']['all']['chose_wait'], 1.0)             # the check's own share, as before
        self.assertEqual(report['stats']['outcomes']['chose_wait']['walks_labeled'], {'k': 2, 'n': 2, 'share': 1.0,
                                                                                       'ci95': [0.342, 1.0]})
        self.assertEqual(report['stats']['paired']['chose_wait']['walks_labeled']['mcnemar_p'], 1.0)

    def logs(self, pairs):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        Path(folder.name, 'today.jsonl').write_text(journal('2026-11-04', pairs), encoding='utf-8')
        return folder.name

    def test_one_entry_point_lists_and_runs_the_checks(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(reask.main(['list']), 0)
        for name in reask.CHECKS:
            self.assertIn(name, out.getvalue())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(reask.main(['no_such_check']), 2)
        logs = self.logs([(self.full, 'go serve')])
        err = io.StringIO()
        with patch.object(jev_replay_check, 'client', side_effect=AssertionError('no client in a dry run')), \
                patch.object(walk_label_check, 'client', side_effect=AssertionError('no client in a dry run')), \
                redirect_stdout(io.StringIO()), redirect_stderr(err):
            self.assertEqual(reask.main(['walk_labels', logs, '--dry-run']), 0)
        self.assertIn('2 requests', err.getvalue())                                         # one moment, two arms

    def test_every_listed_check_has_a_main(self):
        import importlib
        for name, (module, _) in reask.CHECKS.items():
            self.assertTrue(callable(getattr(importlib.import_module(module), 'main', None)), name)


if __name__ == '__main__':
    unittest.main()
