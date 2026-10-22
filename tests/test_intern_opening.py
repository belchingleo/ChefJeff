import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

from kitchen import load_config
from levels import level_config
from player_api import PlayerGameSession, settings_from
from spatial_kitchen import SpatialKitchen
from scripts import probe_intern_opening as probe
from test_web import FakeJournal

KEY = 'opening-unit-test-not-a-real-key'


class InternOpeningTests(unittest.TestCase):
    def test_matches_normal_local_scheduler_and_makes_no_http_call(self):
        with patch('jev.urllib.request.urlopen') as network, patch('jev.threading.Thread') as worker:
            original = probe.opening_payload(1)
            worker.assert_not_called()
            network.assert_not_called()
            with tempfile.TemporaryDirectory() as folder:
                config = level_config(load_config(), 1)
                config.update(order_seed=1, spawn_seed=0, model=probe.MODEL)
                game = PlayerGameSession(config=config, kitchen_factory=SpatialKitchen,
                                         credential_path=Path(folder) / 'key.json',
                                         memory_path=Path(folder) / 'memory.json',
                                         journal_factory=FakeJournal)
                try:
                    game.setting = settings_from({'provider': 'intern-decision', 'api_key': KEY})
                    self.assertEqual(game._command('/api/start', {})[0], 200)
                    game.ai.poll()
                    actual = next(data['payload'] for kind, data in game.journal.journal.rows if kind == 'ai_request')
                    self.assertEqual(original, actual)
                    self.assertEqual(game.k.time, 0)
                    self.assertIsNone(game.k.chefs['jeff'].job)
                finally:
                    game.close()

    def test_all_levels_restore_every_rule_state_and_candidate(self):
        for level in (1, 2, 3):
            with self.subTest(level=level):
                original = probe.opening_payload(level)
                before = deepcopy(original)
                compact = probe.compact_payload(original)
                self.assertEqual(probe.restore_state(compact['state']), json.loads(json.dumps(original['state'])))
                self.assertEqual(compact['questions'], original['questions'])
                self.assertEqual(compact['model'], probe.MODEL)
                self.assertEqual(original, before)
                self.assertEqual(set(compact), {'state', 'questions', 'model'})
                self.assertLess(len(probe.compact_json(compact)), len(probe.compact_json(original)))

    def test_defaults_preserve_explicit_null_absence_and_different_value_types(self):
        original = probe.opening_payload()
        rows = original['state']['kitchen']['stations']
        for row in rows.values():
            row['evidence'] = {'temperature': 42, 'items': [None, False, 0, 0.0]}
            row['optional'] = None
        first = next(iter(rows))
        rows[first]['evidence'] = None
        del rows[first]['optional']
        rows[first]['fire_heat'] = True  # must not be mistaken for numeric 1
        restored = probe.restore_state(probe.compact_payload(original)['state'])
        self.assertEqual(restored, json.loads(json.dumps(original['state'])))
        self.assertNotIn('optional', restored['kitchen']['stations'][first])
        self.assertIs(restored['kitchen']['stations'][first]['fire_heat'], True)

    def send(self, raw, payload=None):
        payload = payload or probe.compact_payload(probe.opening_payload())
        opened = Mock()
        opened.open.return_value = io.BytesIO(raw)
        with patch.object(probe.urllib.request, 'build_opener', return_value=opened):
            result = probe.send_once(payload, KEY)
        return result, opened

    def test_single_fixed_request_validates_both_choices_and_usage(self):
        payload = probe.compact_payload(probe.opening_payload())
        choice = next(iter(payload['questions']['next_action']['criteria']))
        answer = {'answers': {'next_action': {'type': 'choice', 'choice': choice},
                              'sprint': {'type': 'choice', 'choice': 'no'}},
                  'usage': {'input_tokens': 7000, 'output_tokens': 2}, 'model': KEY}
        result, opened = self.send(json.dumps(answer).encode(), payload)
        opened.open.assert_called_once()
        request = opened.open.call_args.args[0]
        self.assertEqual(request.full_url, probe.ENDPOINT)
        self.assertEqual(request.method, 'POST')
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + KEY)
        self.assertEqual(json.loads(request.data), payload)
        self.assertEqual(opened.open.call_args.kwargs['timeout'], 20)
        self.assertEqual(result['choice'], choice)
        self.assertFalse(result['sprint'])
        self.assertEqual(result['input_tokens'], 7000)
        self.assertNotIn(KEY, str(result))
        self.assertNotIn('model', result)

    def test_refusal_is_one_attempt_with_no_credential_in_error(self):
        opened = Mock()
        opened.open.side_effect = urllib.error.HTTPError(probe.ENDPOINT, 400, 'Bad request', {},
            io.BytesIO(json.dumps({'error': {'message': 'estimated input tokens exceed context limit ' + KEY}}).encode()))
        with patch.object(probe.urllib.request, 'build_opener', return_value=opened):
            with self.assertRaises(RuntimeError) as error:
                probe.send_once(probe.compact_payload(probe.opening_payload()), KEY)
        opened.open.assert_called_once()
        self.assertIn('HTTP 400', str(error.exception))
        self.assertIn('context limit ***', str(error.exception))
        self.assertNotIn(KEY, str(error.exception))

    def test_invalid_reply_is_rejected_without_printing_provider_text(self):
        for answer in ({}, {'answers': {'next_action': {'type': 'choice', 'choice': KEY}}}):
            with self.subTest(answer=answer), self.assertRaises(RuntimeError) as error:
                self.send(json.dumps(answer).encode())
            self.assertNotIn(KEY, str(error.exception))

    def test_dry_run_never_prompts_or_calls_provider(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.object(probe.getpass, 'getpass') as prompt, patch.object(probe, 'send_once') as send:
            self.assertEqual(probe.main(['--dry-run']), 0)
        prompt.assert_not_called()
        send.assert_not_called()
        self.assertIn('"request_count": 0', out.getvalue())

    def test_interactive_run_prints_sanitized_error_and_never_retries(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.object(probe.sys.stdin, 'isatty', return_value=True), \
             patch.object(probe.getpass, 'getpass', return_value=KEY), \
             patch.object(probe, 'send_once', side_effect=RuntimeError('Refused ' + KEY)) as send:
            self.assertEqual(probe.main([]), 1)
        send.assert_called_once()
        self.assertNotIn(KEY, out.getvalue())
        self.assertIn('"request_count": 1', out.getvalue())

    def test_key_is_not_read_if_terminal_cannot_hide_input(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
             patch.object(probe.sys.stdin, 'isatty', return_value=True), \
             patch.object(probe.getpass, 'getpass', side_effect=probe.getpass.GetPassWarning()), \
             patch.object(probe, 'send_once') as send:
            self.assertEqual(probe.main([]), 2)
        send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
