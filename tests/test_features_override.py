"""A server's override of features.json: switches changed from the command line, taken as each round starts.

The override lives outside the release (features.OVERRIDE_ENV here points it at a temporary file), may set only
"on" and "off_for", must still pass features.check, and is recorded as "source": "server".
"""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import uuid

import features
import research_replay
from research_record import validate_record
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from test_web import FakeJournal
from loop_helpers import Scripted
from web_server import GameSession
import test_research_save_paths as paths


class OverrideFile:
    """A temporary override path for one test, with the features cache following it."""

    def __init__(self, case):
        folder = tempfile.TemporaryDirectory()
        case.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'features.override.json'
        env = patch.dict(os.environ, {features.OVERRIDE_ENV: str(self.path)})
        env.start()
        case.addCleanup(env.stop)

    def write(self, value):
        text = value if isinstance(value, str) else json.dumps(value)
        before = self.path.stat().st_mtime_ns if self.path.exists() else 0
        self.path.write_text(text, encoding='utf-8')
        os.utime(self.path, ns=(before + 10**9, before + 10**9))   # a new mtime even within one clock tick


def quietly(function, *args):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        value = function(*args)
    return value, err.getvalue()


class OverrideTests(unittest.TestCase):
    def setUp(self):
        self.file = OverrideFile(self)
        self.release = features.load()

    def test_without_a_file_the_release_holds_and_nothing_is_marked(self):
        self.assertEqual(features.current(), self.release)
        self.assertNotIn('source', json.dumps(features.snapshot(features.current())))

    def test_an_override_applies_without_a_restart_and_is_marked(self):
        self.file.write({'walk_note': {'on': True}})
        value = features.current()
        self.assertEqual((value['walk_note']['on'], value['walk_note']['source']), (True, 'server'))
        self.assertTrue(features.compose_options(value)['walk'])
        self.assertEqual(features.snapshot(value)['walk_note'], {'on': True, 'version': 'walk-note-v1', 'source': 'server'})
        self.assertEqual(features.snapshot(value)['one_press'], {'on': True, 'version': self.release['one_press']['version']})
        self.file.write({'walk_note': {'on': True}, 'step_check': {'on': True, 'off_for': ['perplexity']}})
        value = features.current()
        self.assertEqual((value['step_check']['on'], value['step_check']['off_for']), (True, ['perplexity']))
        self.file.path.unlink()
        self.assertEqual(features.current(), self.release)

    def test_a_wrong_override_is_not_used_and_says_why(self):
        for wrong in ({'dance': {'on': True}},                                   # not in this release
                      {'walk_note': {'version': 'walk-note-v9'}},               # versions belong to the code
                      {'option_links': {'player_switch': True}},                # no player switches since 2026-11-20
                      {'jeff_plan': {'on': True}},                              # removed 2026-11-20
                      {'reach_note': {'on': 'yes'}},
                      {'reach_note': {}},
                      [],
                      '{not json'):
            with self.subTest(wrong=wrong):
                self.file.write(wrong)
                value, said = quietly(features.current)
                self.assertEqual(value, self.release)
                self.assertIn('not used', said)

    def test_the_command_line_sets_checks_and_unsets(self):
        value, _ = quietly(features.main, ['set', 'walk_note', 'on'])
        self.assertEqual(value, 0)
        self.assertEqual(json.loads(self.file.path.read_text()), {'walk_note': {'on': True}})
        self.assertEqual(stat.S_IMODE(self.file.path.stat().st_mode), 0o644)     # readable by the game's account
        self.assertEqual(quietly(features.main, ['set', 'step_check', 'on'])[0], 0)
        before = self.file.path.read_text()
        self.assertEqual(quietly(features.main, ['set', 'rolling_intent', 'on'])[0], 1)   # not in this release
        with self.assertRaises(SystemExit):                                       # no --switch option any more
            quietly(features.main, ['set', 'one_press', 'on', '--switch', 'on'])
        self.assertEqual(self.file.path.read_text(), before)                     # a refused change writes nothing
        self.assertEqual(quietly(features.main, ['unset', 'step_check'])[0], 0)
        self.assertEqual(json.loads(self.file.path.read_text()), {'walk_note': {'on': True}})
        bad = self.file.path.with_name('bad.json')
        bad.write_text(json.dumps({'walk_note': {'on': 'yes'}}))
        self.assertEqual(quietly(features.main, ['check', str(bad)])[0], 1)
        self.assertEqual(quietly(features.main, ['check'])[0], 0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            features.main(['show'])
        self.assertRegex(out.getvalue(), r'walk_note\s+on\s+trial\s+walk-note-v1\s+server')


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.file = OverrideFile(self)
        self.g = GameSession(level_config(load_config(), 'level-2'), client_factory=lambda c: Scripted(c),
                             journal_factory=FakeJournal, kitchen_factory=SpatialKitchen)
        self.addCleanup(self.g.close)

    def starts(self):
        return [d for kind, d in self.g.journal.journal.rows if kind == 'start']

    def test_a_round_keeps_its_switches_and_the_next_takes_the_new_ones(self):
        self.file.write({'walk_note': {'on': True}})                          # off in the repository; the server turns it on
        self.assertEqual(self.g._command('/api/start', {})[0], 200)
        self.assertTrue(self.g.ai.walk)
        self.file.write({'walk_note': {'on': False}})                         # changed during the round
        self.assertEqual(self.g.features['walk_note']['on'], True)
        first = self.starts()[-1]                                              # each round writes its own log
        self.assertEqual(self.g._command('/api/end', {})[0], 200)
        self.assertEqual(self.g._command('/api/reset', {})[0], 200)
        self.assertEqual(self.g._command('/api/start', {})[0], 200)
        self.assertFalse(self.g.ai.walk)
        second = self.starts()[-1]
        self.assertEqual(first['features']['walk_note'], {'on': True, 'version': 'walk-note-v1', 'source': 'server'})
        self.assertEqual(second['features']['walk_note'], {'on': False, 'version': 'walk-note-v1', 'source': 'server'})
        self.assertNotIn('jeff_plan', second)


class OverrideRecordTests(paths.SavePathTests):
    def setUp(self):
        self.file = OverrideFile(self)
        self.file.write({'walk_note': {'on': False}, 'reach_note': {'on': True}})
        super().setUp()

    def test_a_round_under_an_override_is_recorded_with_its_source_and_replays_exactly(self):
        import levels
        with patch.object(levels, 'switches', lambda: {'level-4': True}):    # level 4 is switched off for players
            status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 4}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        kept = record['conditions']['features']
        self.assertEqual(kept['walk_note'], {'on': False, 'version': 'walk-note-v1', 'source': 'server'})
        self.assertEqual(kept['reach_note'], {'on': True, 'version': 'reach-v1', 'source': 'server'})
        self.assertNotIn('source', kept['one_press'])
        self.assertNotIn('jeff_plan', record['conditions'])                      # plan modes are gone
        self.assertEqual(research_replay.check(record)['replay'], 'verified')


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(OverrideRecordTests, _name, None)


if __name__ == '__main__':
    unittest.main()
