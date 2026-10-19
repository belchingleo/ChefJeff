"""The hosted load check runs locally without model calls and stays out of the runtime package."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from release_info import RUNTIME_FILES
from scripts.package_web import PUBLIC_FILES

ROOT = Path(__file__).resolve().parents[1]


class LoadTestScriptTests(unittest.TestCase):
    def test_small_run_checks_waiting_and_network_limits(self):
        result = subprocess.run([sys.executable, 'scripts/load_test_hosted.py', '--pages', '9', '--capacity', '3',
                                 '--max-waiting', '4', '--per-network', '1', '--seconds', '4'],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])
        report = json.loads(result.stdout)
        self.assertEqual(report['session_rejections'], 2)
        self.assertEqual(report['shared_network_started'], 1)
        self.assertGreater(report['waiting_reasons']['full'], 0)
        self.assertTrue(all(report['checks'].values()))

    def test_not_shipped(self):
        self.assertNotIn('scripts/load_test_hosted.py', RUNTIME_FILES + PUBLIC_FILES)


if __name__ == '__main__':
    unittest.main()
