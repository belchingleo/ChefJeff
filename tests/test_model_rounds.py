"""scripts/model_rounds.py: whole rounds of a scripted human and Jeff, with a stand-in model on a virtual clock."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts import decision_stats, model_rounds
from collaboration_analyzer import analyze_bundle
from session_record import replay_bundle
from test_decision_stats import Inline
from whitebox_server import SpatialJevClient

PRIORITY = ('serve', 'plate', 'assemble', 'put', 'chop', 'take', 'fetch')


class StandIn(SpatialJevClient):
    """Answers with the first offered key of a fixed priority, else wait; never calls a model."""

    def __init__(self, config):
        super().__init__(config, key='model-rounds-test-not-a-key')
        self.asked = 0

    def ask(self, payload):
        self.asked += 1
        keys = list(payload['questions']['next_action']['criteria'])
        choice = next((k for p in PRIORITY for k in keys if k.startswith(p)), 'wait' if 'wait' in keys else keys[0])
        return {'choice': choice, 'sprint': False, 'sprint_answer': {}, 'confidence': None, 'probabilities': {},
                'model': 'stand-in', 'usage': {'input_tokens': 10, 'output_tokens': 1}, 'latency': .5}


class Clock:
    def __init__(self):
        self.now = 1000.

    def __call__(self):
        return self.now

    def wait(self, seconds):
        self.now += seconds


class ModelRoundsTests(unittest.TestCase):
    def play(self, folder, human='assembler', max_calls=None):
        clock = Clock()
        with patch.dict(os.environ, {'CHEFJEFF_LOG_DIR': folder}), patch('jev.time.monotonic', clock), \
                patch('jev.threading.Thread', Inline):
            return model_rounds.play_round('level-1', StandIn, human, max_calls, clock=clock, wait=clock.wait)

    def test_a_whole_round_is_recorded_and_replays_exactly(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.play(folder)
            self.assertEqual(result['phase'], 'ended')
            self.assertGreater(result['ai_calls'], 10)
            self.assertTrue(Path(folder, result['journal']).is_file())
            bundle = Path(folder, result['bundle'])
            replay = analyze_bundle(bundle)['replay']                 # what collaboration_analyzer.py reports
            self.assertTrue(replay['matches_recording'], replay)
            self.assertGreater(replay['engine_events'], 50)
            self.assertEqual(replay_bundle(bundle).money, result['money'])
            stats = decision_stats.report([folder])
            self.assertEqual(stats['rounds'], 1)

    def test_the_call_limit_and_an_idle_human(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.play(folder, human='idle', max_calls=5)
            self.assertEqual(result['ai_calls'], 5)
            self.assertEqual(result['phase'], 'ended')

    def test_a_dry_run_calls_nothing_and_logs_is_refused(self):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, \
                patch('scripts.jev_replay_check.client', side_effect=AssertionError('no client in a dry run')), \
                redirect_stderr(err):
            out = Path(folder, 'runs')
            self.assertEqual(model_rounds.main(['--level', 'level-1', '--rounds', '3', '--out', str(out), '--dry-run']), 0)
            self.assertFalse(out.exists())
        cost = json.loads(err.getvalue())
        self.assertEqual((cost['rounds'], cost['max_requests']), (3, 600))
        self.assertGreater(cost['max_input_tokens_m'], 0)
        from play import ROOT
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            model_rounds.main(['--out', str(ROOT / 'logs'), '--dry-run'])


if __name__ == '__main__':
    unittest.main()
