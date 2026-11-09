"""A server's override of features.json: switches changed from the command line, taken as each round starts.

The override lives outside the release (features.OVERRIDE_ENV here points it at a temporary file), may set only
"on" and "player_switch", must still pass features.check, and is recorded as "source": "server".
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
from test_jeff_plan import Scripted
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
        self.file.write({'rolling_intent': {'on': False}})
        value = features.current()
        self.assertEqual((value['rolling_intent']['on'], value['rolling_intent']['source']), (False, 'server'))
        self.assertEqual(features.plan_default(value), 'off')
        self.assertEqual(features.snapshot(value)['rolling_intent'], {'on': False, 'version': 'rolling-v3', 'source': 'server'})
        self.assertEqual(features.snapshot(value)['one_press'], {'on': True, 'version': self.release['one_press']['version']})
        self.file.write({'rolling_intent': {'on': False}, 'jeff_plan': {'on': True, 'player_switch': True}})
        value = features.current()
        self.assertEqual((features.plan_default(value), features.plan_choices(value)), ('choice', ['choice']))
        self.file.path.unlink()
        self.assertEqual(features.current(), self.release)

    def test_a_wrong_override_is_not_used_and_says_why(self):
        for wrong in ({'dance': {'on': True}},                                   # not in this release
                      {'rolling_intent': {'version': 'rolling-v9'}},            # versions belong to the code
                      {'one_press': {'player_switch': True}},                   # released: no switch
                      {'jeff_plan': {'on': True}},                              # two plan modes at once
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
        value, _ = quietly(features.main, ['set', 'rolling_intent', 'off'])
        self.assertEqual(value, 0)
        self.assertEqual(json.loads(self.file.path.read_text()), {'rolling_intent': {'on': False}})
        self.assertEqual(stat.S_IMODE(self.file.path.stat().st_mode), 0o644)     # readable by the game's account
        self.assertEqual(quietly(features.main, ['set', 'jeff_plan', 'on', '--switch', 'on'])[0], 0)
        before = self.file.path.read_text()
        self.assertEqual(quietly(features.main, ['set', 'rolling_intent', 'on'])[0], 1)   # two plan modes: refused
        self.assertEqual(quietly(features.main, ['set', 'one_press', 'on', '--switch', 'on'])[0], 1)
        self.assertEqual(self.file.path.read_text(), before)                     # a refused change writes nothing
        self.assertEqual(quietly(features.main, ['unset', 'jeff_plan'])[0], 0)
        self.assertEqual(json.loads(self.file.path.read_text()), {'rolling_intent': {'on': False}})
        bad = self.file.path.with_name('bad.json')
        bad.write_text(json.dumps({'jeff_plan': {'on': True}}))
        self.assertEqual(quietly(features.main, ['check', str(bad)])[0], 1)
        self.assertEqual(quietly(features.main, ['check'])[0], 0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            features.main(['show'])
        self.assertIn('rolling_intent  off  release        rolling-v3     server', out.getvalue())


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.file = OverrideFile(self)
        self.g = GameSession(level_config(load_config(), 'level-2'), client_factory=lambda c: Scripted(c, [['fetch:lettuce']]),
                             journal_factory=FakeJournal, kitchen_factory=SpatialKitchen)
        self.addCleanup(self.g.close)

    def starts(self):
        return [d for kind, d in self.g.journal.journal.rows if kind == 'start']

    def test_a_round_keeps_its_switches_and_the_next_takes_the_new_ones(self):
        self.assertEqual(self.g._command('/api/start', {})[0], 200)
        self.assertEqual(self.g.ai.plan.mode, 'rolling')
        self.file.write({'rolling_intent': {'on': False}})                    # changed during the round
        self.assertEqual(self.g.features['rolling_intent']['on'], True)
        self.assertEqual(self.g.plan_state()['mode'], 'rolling')
        first = self.starts()[-1]                                              # each round writes its own log
        self.assertEqual(self.g._command('/api/end', {})[0], 200)
        self.assertEqual(self.g.plan_state()['mode'], 'off')                   # between rounds: what the next takes
        self.assertEqual(self.g._command('/api/reset', {})[0], 200)
        self.assertEqual(self.g._command('/api/start', {})[0], 200)
        self.assertIsNone(self.g.ai.plan)
        second = self.starts()[-1]
        self.assertEqual(first['features']['rolling_intent'], {'on': True, 'version': 'rolling-v3'})
        self.assertEqual(second['features']['rolling_intent'], {'on': False, 'version': 'rolling-v3', 'source': 'server'})
        self.assertNotIn('jeff_plan', second)

    def test_a_switch_the_server_offers_shows_between_rounds_and_is_taken(self):
        self.file.write({'rolling_intent': {'on': False}, 'jeff_plan': {'player_switch': True}})
        self.assertEqual(self.g.plan_state(), {'mode': 'off', 'available': ['choice'], 'editable': True, 'current': None})
        self.assertEqual(self.g._command('/api/plan', {'mode': 'choice'})[0], 200)
        self.assertEqual(self.g._command('/api/start', {})[0], 200)
        self.assertEqual(self.g.ai.plan.mode, 'choice')
        self.assertEqual(self.starts()[-1]['features']['jeff_plan'], {'on': False, 'version': 'plan-v2', 'source': 'server'})


class OverrideRecordTests(paths.SavePathTests):
    def setUp(self):
        self.file = OverrideFile(self)
        self.file.write({'rolling_intent': {'on': False}, 'reach_note': {'on': True}})
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
        self.assertEqual(kept['rolling_intent'], {'on': False, 'version': 'rolling-v3', 'source': 'server'})
        self.assertEqual(kept['reach_note'], {'on': True, 'version': 'reach-v1', 'source': 'server'})
        self.assertNotIn('source', kept['one_press'])
        self.assertFalse(record['conditions'].get('jeff_plan'))                  # no plan mode in this round
        self.assertEqual(research_replay.check(record)['replay'], 'verified')


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(OverrideRecordTests, _name, None)


if __name__ == '__main__':
    unittest.main()
