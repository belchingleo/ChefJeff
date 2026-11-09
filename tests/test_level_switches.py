import json
import os
import tempfile
import unittest
from unittest.mock import patch

import levels
from kitchen import load_config
from test_web import FakeJournal
from spatial_kitchen import SpatialKitchen
from web_server import GameSession


class LevelSwitchTests(unittest.TestCase):
    """level_switches.json keeps a level out of the page's list and out of /api/level; the engine still has it."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.override = os.path.join(self.folder.name, 'levels.override.json')
        env = patch.dict(os.environ, {levels.OVERRIDE_ENV: self.override})
        env.start()
        self.addCleanup(env.stop)

    def write(self, value):
        with open(self.override, 'w', encoding='utf-8') as f:
            f.write(value if isinstance(value, str) else json.dumps(value))
        os.utime(self.override, ns=(1, os.stat(self.override).st_mtime_ns + 10 ** 9))   # read again

    def session(self):
        g = GameSession(levels.level_config(load_config(), 'level-1'), journal_factory=FakeJournal,
                        kitchen_factory=SpatialKitchen)
        self.addCleanup(g.close)
        return g

    def test_level_four_is_off_in_the_release(self):
        self.assertEqual(json.loads(levels.SWITCHES.read_text(encoding='utf-8')), {'level-4': {'on': False}})
        self.assertEqual([l['id'] for l in levels.shown_levels()], ['level-1', 'level-2', 'level-3'])
        self.assertIn('level-4', [l['id'] for l in levels.available_levels()])         # the engine still has it
        self.assertEqual(levels.level_config(load_config(), 'level-4')['level'], 4)
        g = self.session()
        self.assertNotIn('level-4', [l['id'] for l in g.public_state()['levels']])
        self.assertEqual(g._command('/api/level', {'level': 'level-4'})[0], 400)
        self.assertEqual(g._command('/api/level', {'level': 4})[0], 400)
        self.assertEqual(g._command('/api/level', {'level': 'level-3'})[0], 200)

    def test_an_override_shows_it_without_a_new_release(self):
        self.write({'level-4': {'on': True}})
        self.assertEqual([l['id'] for l in levels.shown_levels()][-1], 'level-4')
        g = self.session()
        self.assertIn('level-4', [l['id'] for l in g.public_state()['levels']])
        self.assertEqual(g._command('/api/level', {'level': 'level-4'})[0], 200)
        self.write({'level-4': {'on': False}})
        self.assertNotIn('level-4', [l['id'] for l in levels.shown_levels()])

    def test_a_wrong_override_is_not_used(self):
        for wrong in ('not json', {'level-9': {'on': True}}, {'level-4': {'on': 'yes'}}, {'level-4': {'on': True, 'x': 1}}):
            with self.subTest(wrong=wrong):
                self.write(wrong)
                with patch('sys.stderr'):
                    self.assertNotIn('level-4', [l['id'] for l in levels.shown_levels()])

    def test_the_command_line_sets_the_override(self):
        with patch('sys.stdout'):
            self.assertEqual(levels.main(['set', 'level-4', 'on']), 0)
        self.assertEqual(json.loads(open(self.override, encoding='utf-8').read()), {'level-4': {'on': True}})
        with patch('sys.stdout'):
            self.assertEqual(levels.main(['set', 'level-4', 'off']), 0)
        self.assertNotIn('level-4', [l['id'] for l in levels.shown_levels()])


if __name__ == '__main__':
    unittest.main()
