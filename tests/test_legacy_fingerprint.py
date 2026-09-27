"""Accepted legacy levels must behave identically through the data-driven migration."""
import json
import unittest
from pathlib import Path

from fingerprint import GOLDEN, SCENARIOS, run


class LegacyFingerprintTests(unittest.TestCase):
    maxDiff = 4000

    def test_golden_files_cover_every_scenario(self):
        self.assertEqual({p.stem for p in GOLDEN.glob('level*.json')}, set(SCENARIOS))

    def test_scenarios_match_golden_traces(self):
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                expected = json.loads((GOLDEN / f'{name}.json').read_text())
                actual = json.loads(json.dumps(run(name), ensure_ascii=False))
                self.assertEqual(actual['decisions'], expected['decisions'])
                self.assertEqual(actual['events'], expected['events'])
                self.assertEqual(actual['checkpoints'], expected['checkpoints'])
                self.assertEqual(actual['final'], expected['final'])
                self.assertEqual(actual['result'], expected['result'])


if __name__ == '__main__':
    unittest.main()
