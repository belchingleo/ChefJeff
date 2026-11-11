"""An agent on the environment's plain interface plays whole rounds in the game's session (env-v1)."""
import ast
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import environment
from collaboration_analyzer import analyze_bundle
from example_agent import PriorityAgent
from jev import DecisionLoop
from scripts import model_rounds
from test_decision_stats import Inline
from test_model_rounds import Clock

ROOT = Path(__file__).resolve().parents[1]


class ExampleAgentTests(unittest.TestCase):
    def play(self, folder, agent, level='level-1', human='assembler'):
        clock = Clock()
        with patch.dict(os.environ, {'CHEFJEFF_LOG_DIR': folder}), patch('jev.time.monotonic', clock), \
                patch('agent_loop.time.monotonic', clock), patch('jev.threading.Thread', Inline):
            return model_rounds.play_round(level, lambda config: agent, human, clock=clock, wait=clock.wait)

    def test_it_plays_a_whole_round_that_replays_exactly(self):
        agent = PriorityAgent(think=.8)
        with tempfile.TemporaryDirectory() as folder:
            result = self.play(folder, agent)
            self.assertEqual(result['phase'], 'ended')
            self.assertGreater(agent.acted, 10)
            replay = analyze_bundle(Path(folder, result['bundle']))['replay']
            self.assertTrue(replay['matches_recording'], replay)
        self.assertIsNone(agent.pending)                       # closed at the end of the round

    def test_alone_it_still_serves(self):
        # Level 1: at 4 cells a second this simple agent alone lets level 3's stoves catch fire after one dish.
        agent = PriorityAgent(think=.8)
        with tempfile.TemporaryDirectory() as folder:
            result = self.play(folder, agent, level='level-1', human='idle')
        self.assertGreater(result['money'], 0)

    def test_it_uses_only_the_environment(self):
        tree = ast.parse((ROOT / 'example_agent.py').read_text(encoding='utf-8'))
        imported = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or '')])}
        self.assertEqual(imported - {'__future__'}, {'environment'})


class JeffOnThePortTests(unittest.TestCase):
    def test_jeffs_loop_reads_through_the_view_and_acts_through_the_port(self):
        from kitchen import load_config
        from levels import level_config
        from spatial_kitchen import SpatialKitchen
        k = SpatialKitchen(level_config(load_config(), 'level-2'))
        loop = DecisionLoop(k, None, lambda *_: None, lambda *_: None)
        self.assertIsInstance(loop.k, environment.ReadOnlyKitchen)
        self.assertIs(loop.port.view, loop.k)
        with self.assertRaises(PermissionError):
            loop.k.start('jeff', k.actions('jeff')[0])
        port = environment.AgentPort(k)
        self.assertIs(DecisionLoop(port, None, lambda *_: None, lambda *_: None).port, port)


if __name__ == '__main__':
    unittest.main()
