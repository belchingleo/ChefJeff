"""Only loopback HTTP and mocked model providers; no production records or API calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error

from hosted_server import BrowserRelay, make_server
from hosted_free_models import FreeModels, MODELS, read_trial_keys
from hosted_jev import ForwardError, TEST_PAYLOAD

KEYS = {'zhipu': 'synthetic-zhipu-credential', 'startlux': 'synthetic-bamboo-credential'}
ANSWER = {'choice': 'wait', 'sprint': False, 'usage': {'input_tokens': 3, 'output_tokens': 0}}


class ConfigTests(unittest.TestCase):
    def test_only_explicit_root_import_accepts_a_different_private_file_owner(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'keys.json'
            path.write_text(json.dumps({'format':'chefjeff-private-api-keys-v1',
                'zhipu_api_key':KEYS['zhipu'],'bamboo_api_key':KEYS['startlux']}))
            path.chmod(0o600)
            original=os.fstat
            def other_owner(fd):
                values=list(original(fd));values[4]=1000
                return os.stat_result(values)
            with patch('hosted_free_models.os.fstat',side_effect=other_owner),patch('hosted_free_models.os.getuid',return_value=0):
                with self.assertRaises(ValueError):read_trial_keys(path)
                self.assertEqual(read_trial_keys(path,allow_root_import=True),KEYS)
            with patch('hosted_free_models.os.fstat',side_effect=other_owner),patch('hosted_free_models.os.getuid',return_value=999):
                with self.assertRaises(ValueError):read_trial_keys(path,allow_root_import=True)

    def test_both_services_must_be_verified_and_disabled_catalog_has_no_secrets(self):
        self.assertEqual(FreeModels().catalog(), {'enabled': False, 'models': []})
        with self.assertRaises(ValueError):
            FreeModels(KEYS)
        with self.assertRaises(ValueError):
            FreeModels({'zhipu': KEYS['zhipu']}, verified=True)
        catalog = FreeModels(KEYS, verified=True).catalog()
        self.assertEqual(len(catalog['models']), 2)
        self.assertTrue(catalog['enabled'])
        for key in KEYS.values():
            self.assertNotIn(key, json.dumps(catalog))

    def test_private_file_permissions_and_both_keys_are_required(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'keys.json'
            value = {'format': 'chefjeff-private-api-keys-v1', 'zhipu_api_key': KEYS['zhipu'], 'bamboo_api_key': KEYS['startlux']}
            path.write_text(json.dumps(value)); path.chmod(0o600)
            self.assertEqual(read_trial_keys(path), KEYS)
            path.chmod(0o640)
            self.assertEqual(read_trial_keys(path), KEYS)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                read_trial_keys(path)
            path.chmod(0o600)
            link = Path(d) / 'link.json'; link.symlink_to(path)
            with self.assertRaises(ValueError):
                read_trial_keys(link)
            value['bamboo_api_key'] = ''
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                read_trial_keys(path)

    def test_enable_flag_does_not_read_file_before_both_services_are_verified(self):
        with patch('hosted_server.read_trial_keys', side_effect=AssertionError('must not read')):
            with self.assertRaises(ValueError):
                make_server(0, 'http://localhost', free_model_keys='/nonexistent-private-file')
        with self.assertRaises(ValueError):
            make_server(0, 'http://localhost', free_model_keys=Path(__file__).resolve().parents[1] / 'keys.json', free_models_verified=True)

    def test_fixed_upstreams_no_redirect_retry_or_paid_fallback_and_sanitized_errors(self):
        models = FreeModels(KEYS, verified=True)
        for provider in MODELS:
            error = urllib.error.HTTPError('https://example.invalid', 429, KEYS[provider], {}, io.BytesIO(KEYS[provider].encode()))
            opener = unittest.mock.Mock()
            opener.open.side_effect = error
            with patch('hosted_free_models.urllib.request.build_opener', return_value=opener):
                with self.assertRaises(ForwardError) as result:
                    models.send(provider, deepcopy(TEST_PAYLOAD))
            self.assertEqual(opener.open.call_count, 1)
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, MODELS[provider]['endpoint'])
            self.assertEqual(json.loads(request.data)['model'], MODELS[provider]['model'])
            self.assertNotIn(KEYS[provider], request.data.decode())
            self.assertNotIn(KEYS[provider], str(result.exception))
            self.assertGreater(models.cooldown[provider], models.clock())


class FreeHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0, 'http://127.0.0.1', capacity=4)
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.server.public_origin = self.origin
        self.server.free_models = FreeModels(KEYS, verified=True)
        self.calls = []
        def send(provider, payload):
            self.calls.append((provider, deepcopy(payload)))
            return deepcopy(ANSWER)
        self.server.free_models.send = send
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown(); self.server.sessions.close(); self.server.server_close(); self.thread.join(2)

    def request(self, path, body=None, token=None, origin=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'Origin': origin or self.origin}
        if token: headers['X-ChefJeff-Session'] = token
        if body is not None: headers['Content-Type'] = 'application/json'
        try:
            connection.request('GET' if body is None else 'POST', path, None if body is None else json.dumps(body), headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def page(self, provider='startlux'):
        status, data = self.request('/api/session', {})
        self.assertEqual(status, 201)
        token = data['session']; game = self.server.sessions.get(token)
        self.assertEqual(self.select(token, game, provider)[0], 200)
        return token, game

    def select(self, token, game, provider):
        return self.request('/api/model/free/select', {'game_id': game.game_id, 'provider': provider}, token)

    def task(self, game, ident='synthetic-task'):
        game.phase = 'running'; game.relay = BrowserRelay(game.c)
        task = {'id': ident, 'payload': deepcopy(TEST_PAYLOAD), 'event': threading.Event(), 'result': None, 'sent': time.monotonic()}
        game.relay.pending = task
        return task

    def forward(self, token, game, **extra):
        return self.request('/api/model/free', {'game_id': game.game_id, 'provider': game.free_model_provider,
                            'id': 'synthetic-task', **extra}, token)

    def test_default_disabled_and_auth_origin_field_validation_block_calls(self):
        token, game = self.page()
        self.assertEqual(self.request('/api/model/free/catalog')[0], 401)
        self.assertEqual(self.request('/api/model/free/catalog', token=token, origin='https://other.invalid')[0], 403)
        for extra in ({'api_key': 'injected'}, {'model': 'paid-model'}, {'payload': TEST_PAYLOAD}, {'base_url': 'https://other.invalid'}):
            self.assertEqual(self.forward(token, game, **extra)[0], 400)
        self.server.free_models = FreeModels()
        self.assertFalse(self.request('/api/model/free/catalog', token=token)[1]['enabled'])
        self.assertEqual(self.select(token, game, 'zhipu')[0], 503)
        self.assertEqual(self.calls, [])

    def test_select_is_free_without_upstream_call_and_rejected_during_play_or_pause(self):
        token, game = self.page()
        self.assertEqual(self.select(token, game, 'zhipu')[0], 200)
        self.assertEqual(game.free_model_provider, 'zhipu')
        for phase in ('running', 'paused'):
            game.phase = phase
            self.assertEqual(self.select(token, game, 'startlux')[0], 409)
            self.assertEqual(game.free_model_provider, 'zhipu')
        game.phase = 'ended'
        self.assertEqual(self.select(token, game, 'startlux')[0], 200)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.request('/api/browser-ready', {'game_id': game.game_id, 'request_id': 'own-model', 'connected': True}, token)[0], 200)
        self.assertIsNone(game.free_model_provider)

    def test_only_current_selected_model_and_own_server_payload_can_consume_quota(self):
        one, game = self.page('zhipu'); two, other = self.page()
        task = self.task(game)
        other.phase = 'running'
        self.assertEqual(self.forward(two, other)[0], 409)
        self.assertEqual(self.forward(one, game, provider='startlux')[0], 409)
        self.assertEqual(self.calls, [])
        first = self.forward(one, game)
        self.assertEqual(first, (200, {'answer': ANSWER}))
        self.assertEqual(self.forward(one, game), first)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0], ('zhipu', task['payload']))
        for secret in KEYS.values():
            self.assertNotIn(secret, str((game.public_state(), game.free_model_receipts)))

    def test_free_budget_cannot_be_increased_by_the_player(self):
        token, game = self.page()
        self.assertEqual(self.request('/api/limits', {'game_id': game.game_id, 'request_id': 'limit', 'max_calls': 2000}, token)[0], 200)
        self.task(game)
        game.free_model_budget_round = game.game_id; game.free_model_calls = 200
        self.assertEqual(self.forward(token, game)[0], 429)
        self.assertEqual(self.calls, [])

    def test_global_hourly_budget_and_provider_cooldown(self):
        token, game = self.page(); self.task(game)
        models = self.server.free_models; now = models.clock()
        models.hour.extend([now] * 300)
        self.assertEqual(self.forward(token, game)[0], 429)
        models.hour.clear(); models.cooldown['startlux'] = now + 60
        self.assertEqual(self.forward(token, game)[0], 503)
        models.cooldown['startlux'] = 0
        self.assertEqual(self.forward(token, game)[0], 200)
        self.assertEqual(len(self.calls), 1)

    def test_slow_reply_is_discarded_after_end_and_no_game_lock_is_held(self):
        token, game = self.page(); self.task(game)
        entered = threading.Event(); release = threading.Event()
        def slow(*args):
            entered.set(); release.wait(2); return dict(ANSWER)
        self.server.free_models.send = slow
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(self.forward, token, game)
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(game.lock.acquire(timeout=.1))
                game.phase = 'ended'; game.lock.release()
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=1)[0], 409)
        self.assertTrue(game.free_model_gate.acquire(blocking=False)); game.free_model_gate.release()
        self.assertTrue(self.server.free_models.slots['startlux'].acquire(blocking=False))
        self.server.free_models.slots['startlux'].release()


if __name__ == '__main__':
    unittest.main()
