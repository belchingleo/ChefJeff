"""scripts/benchmark.py: the frozen manifest, a whole offline run, and what verify refuses."""
import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import benchmark, model_rounds
from test_decision_stats import Inline
from test_model_rounds import Clock


def play_offline(job):
    """One benchmark round on a virtual clock (a real run plays in real time, in its own process)."""
    spec, level, partner, out = job
    clock = Clock()
    with patch.dict(os.environ, {'CHEFJEFF_LOG_DIR': out}), patch('jev.time.monotonic', clock), \
            patch('agent_loop.time.monotonic', clock), patch('jev.threading.Thread', Inline):
        result = model_rounds.play_round(level, benchmark.agent_factory(spec), partner, clock=clock, wait=clock.wait)
    return benchmark.analyse(result, out)


class ManifestTests(unittest.TestCase):
    def test_the_current_version_is_frozen(self):
        """What the current version measures (interface, level configurations, engine traces, partner) is what this
        code does. If this fails, the change altered what its score means: make the next version rather than editing it."""
        self.assertEqual(benchmark.CURRENT, 'v3')
        manifest = benchmark.read_manifest(benchmark.CURRENT)
        self.assertEqual(benchmark.refreeze(manifest), manifest)
        self.assertEqual([level['id'] for level in manifest['levels']], ['level-1', 'level-2', 'level-3'])
        self.assertEqual((manifest['partner'], manifest['rounds_per_cell'], manifest['clock']), ('assembler', 12, 'real'))

    def test_v1_is_kept_and_retired(self):
        """v1 stays as it was frozen; the "fetch beef" key changed its reference traces, so it no longer matches."""
        v1, v2 = benchmark.read_manifest('v1'), benchmark.read_manifest('v2')
        self.assertNotEqual(benchmark.refreeze(v1), v1)
        self.assertEqual({k: v for k, v in v1.items() if k not in ('version', 'levels')},
                         {k: v for k, v in v2.items() if k not in ('version', 'levels')})
        self.assertEqual([(a['id'], a['config_hash']) for a in v1['levels']], [(a['id'], a['config_hash']) for a in v2['levels']])

    def test_v2_is_kept_and_retired(self):
        """v2 stays as it was frozen; the drying rack changed levels 1-3 and the reference traces, so it no longer matches."""
        v2, v3 = benchmark.read_manifest('v2'), benchmark.read_manifest('v3')
        self.assertNotEqual(benchmark.refreeze(v2), v2)
        self.assertEqual({k: v for k, v in v2.items() if k not in ('version', 'levels', 'partner_policy')},
                         {k: v for k, v in v3.items() if k not in ('version', 'levels', 'partner_policy')})
        self.assertEqual([a['id'] for a in v2['levels']], [a['id'] for a in v3['levels']])

    def test_a_change_to_what_is_frozen_shows(self):
        manifest = benchmark.read_manifest(benchmark.CURRENT)
        with patch.object(benchmark, 'sha', lambda path: 'sha256:changed'):
            self.assertNotEqual(benchmark.refreeze(manifest), manifest)


class RunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.manifest = benchmark.freeze(['level-3'], 'assembler', 2, 'test')
        cls.result = benchmark.run('example_agent:PriorityAgent', cls.folder.name, cls.manifest, play=play_offline,
                                   clock='virtual')

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_every_cell_is_played_kept_and_summarised(self):
        (cell,) = self.result['cells']
        self.assertEqual((cell['level'], cell['partner'], len(cell['rounds'])), ('level-3', 'assembler', 2))
        summary = cell['summary']
        self.assertEqual(summary['rounds'], 2)
        self.assertTrue(summary['replays_exactly'])
        self.assertEqual(len(summary['money_ci95']), 2)
        self.assertEqual(summary['goal']['n'], 2)
        self.assertIsNotNone(summary['gain_over_scripted_solo_mean'])
        self.assertTrue(Path(self.folder.name, 'result.json').is_file())
        self.assertEqual(self.result['agent']['models'], ['example-priority-agent'])

    def test_verify_counts_only_a_real_run_of_this_manifest(self):
        self.assertEqual(benchmark.verify(self.result, self.manifest), ['played on a virtual clock; the benchmark needs a real one'])
        real = {**copy.deepcopy(self.result), 'clock': 'real'}
        self.assertEqual(benchmark.verify(real, self.manifest), [])
        short = copy.deepcopy(real)
        short['cells'][0]['rounds'].pop()
        self.assertIn('level-3: 1 rounds, 2 needed', benchmark.verify(short, self.manifest))
        other = copy.deepcopy(real)
        other['cells'][0]['rounds'][0]['config_hash'] = 'sha256:other'
        self.assertIn('level-3: a round played another configuration', benchmark.verify(other, self.manifest))
        broken = copy.deepcopy(real)
        broken['cells'][0]['rounds'][0]['replay_matches'] = False
        self.assertIn('level-3: a round does not replay', benchmark.verify(broken, self.manifest))
        self.assertIn('made for another manifest than benchmark v1', benchmark.verify(real, benchmark.read_manifest('v1')))

    def test_report_compares_results(self):
        table = benchmark.report([self.result, self.result])
        self.assertEqual(len(table.splitlines()), 4)                 # header, rule, one row per result's cell
        self.assertIn('example_agent:PriorityAgent', table)


class CommandTests(unittest.TestCase):
    def test_a_dry_run_prices_the_current_version_and_plays_nothing(self):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, redirect_stderr(err), \
                patch.object(benchmark, 'run', side_effect=AssertionError('a dry run plays nothing')):
            self.assertEqual(benchmark.main(['run', '--agent', 'jeff', '--out', folder, '--dry-run']), 0)
        cost = json.loads(err.getvalue())
        self.assertEqual(cost['rounds'], 36)
        self.assertEqual(cost['minutes_of_play'], 108.0)

    def test_an_agent_is_jeff_or_module_and_class(self):
        with self.assertRaises(ValueError):
            benchmark.agent_factory('example_agent')
        from example_agent import PriorityAgent
        self.assertIsInstance(benchmark.agent_factory('example_agent:PriorityAgent')({}), PriorityAgent)

    def test_verify_on_the_command_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'result.json')
            path.write_text(json.dumps({'format': 'other', 'version': 'v1', 'cells': []}))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(benchmark.main(['verify', str(path)]), 1)
            self.assertFalse(json.loads(out.getvalue())['counts'])


if __name__ == '__main__':
    unittest.main()
