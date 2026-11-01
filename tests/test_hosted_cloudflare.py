"""Opt-in Cloudflare forwarding: fixed host and models, the player's account ID, no credential retention."""
import http.client
import io
import json
import threading
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from hosted_cloudflare import CONSENT_VERSION, CloudflareForwarder
from hosted_jev import CONSENT_VERSION as JEV_CONSENT, ForwardError, NoRedirect, TEST_PAYLOAD
from hosted_server import make_server

KEY = 'unit-test-cloudflare-key-not-a-real-secret'
ACCOUNT = '0123456789abcdef0123456789abcdef'
GEMMA, LLAMA = '@cf/google/gemma-4-26b-a4b-it', '@cf/meta/llama-3.1-8b-instruct-fp8'


def body(**extra):
    return {'api_key': KEY, 'account_id': ACCOUNT, 'model': GEMMA, **extra}


class UpstreamTests(unittest.TestCase):
    def reply(self, model, content='{"choice":"wait"}'):
        upstream = MagicMock()
        upstream.open.return_value.__enter__.return_value.read.return_value = json.dumps(
            {'model': model, 'choices': [{'message': {'content': content}}], 'usage': {'prompt_tokens': 9, 'completion_tokens': 2},
             'debug': KEY}).encode()
        return upstream

    def test_fixed_host_account_path_probed_fields_and_filtered_answer(self):
        for model, field in ((GEMMA, 'chat_template_kwargs'), (LLAMA, None)):
            upstream = self.reply(model)
            with patch('hosted_cloudflare.urllib.request.build_opener', return_value=upstream) as build:
                answer = CloudflareForwarder().forward(body(model=model), TEST_PAYLOAD)
            self.assertIsInstance(build.call_args.args[0], NoRedirect)
            request = upstream.open.call_args.args[0]
            self.assertEqual(request.full_url, f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/v1/chat/completions')
            self.assertEqual(request.get_header('Authorization'), 'Bearer ' + KEY)
            sent = json.loads(request.data)
            self.assertEqual((sent['model'], sent['max_tokens'], sent['response_format']), (model, 128, {'type': 'json_object'}))
            self.assertEqual(field in sent, field is not None)
            self.assertEqual(answer, {'choice': 'wait', 'sprint': False, 'usage': {'input_tokens': 9, 'output_tokens': 2}})
            self.assertNotIn(KEY, json.dumps(answer))

    def test_another_model_errors_and_redirects_never_leak_the_key(self):
        with patch('hosted_cloudflare.urllib.request.build_opener', return_value=self.reply(LLAMA)):
            with self.assertRaises(ForwardError): CloudflareForwarder().forward(body(), TEST_PAYLOAD)  # asked Gemma, got Llama
        for status in (301, 401, 429):
            error = urllib.error.HTTPError('https://api.cloudflare.com', status, KEY, {'Location': 'https://x/' + KEY}, io.BytesIO(KEY.encode()))
            with self.subTest(status=status), patch('hosted_cloudflare.urllib.request.build_opener') as build:
                build.return_value.open.side_effect = error
                with self.assertRaises(ForwardError) as result: CloudflareForwarder().forward(body(), TEST_PAYLOAD)
                self.assertNotIn(KEY, str(result.exception)); self.assertIn(str(status), str(result.exception))
                self.assertEqual(build.return_value.open.call_count, 1)

    def test_account_and_model_are_checked_before_anything_else(self):
        check = CloudflareForwarder().check
        self.assertIsNone(check(body())); self.assertIsNone(check(body(model=LLAMA)))
        for bad in (body(account_id='x/../evil'), body(account_id=ACCOUNT.upper()), body(account_id=None),
                    body(model='@cf/other/model'), body(model=None)):
            self.assertTrue(check(bad))


class ForwardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(0, 'http://127.0.0.1', capacity=4)
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port); self.server.public_origin = self.origin
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.cleanup)
        self.calls = []
        def forward(value, payload):
            self.calls.append((value, payload)); return {'choice': 'wait', 'sprint': False, 'usage': {'input_tokens': 1, 'output_tokens': 1}}
        self.server.cloudflare_forwarder.forward = forward

    def cleanup(self):
        self.server.shutdown(); self.server.sessions.close(); self.server.server_close(); self.thread.join(2)

    def request(self, path, value, token):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            c.request('POST', path, json.dumps(value), {'Origin': self.origin, 'X-ChefJeff-Session': token, 'Content-Type': 'application/json'})
            r = c.getresponse(); return r.status, json.loads(r.read())
        finally: c.close()

    def test_consent_account_and_model_gate_the_relay_and_nothing_is_kept(self):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        c.request('POST', '/api/session', '{}', {'Origin': self.origin, 'Content-Type': 'application/json'})
        token = json.loads(c.getresponse().read())['session']; c.close()
        game = self.server.sessions.get(token)
        good = {'game_id': game.game_id, 'request_id': 'connection-test', 'test': True, 'consent': True,
                'consent_version': CONSENT_VERSION, **body()}
        for extra in ({'consent': False}, {'consent_version': JEV_CONSENT}, {'account_id': 'nope'},
                      {'model': '@cf/other/model'}, {'base_url': 'https://other.example'}):
            with self.subTest(extra=extra):
                self.assertEqual(self.request('/api/model/cloudflare', {**good, **extra}, token)[0], 400)
        self.assertEqual(self.calls, [])
        status, reply = self.request('/api/model/cloudflare', good, token)
        self.assertEqual((status, reply['answer']['choice']), (200, 'wait'))
        self.assertEqual(self.calls[0][0]['account_id'], ACCOUNT)
        for value in (game.public_state(), game.jev_receipts, game.receipts):
            self.assertNotIn(KEY, str(value)); self.assertNotIn(ACCOUNT, str(value))
        # A Cloudflare consent never opens the Jev relay, and the other way round.
        self.assertEqual(self.request('/api/model/jev', {**good, 'request_id': 'jev-test'}, token)[0], 400)


if __name__ == '__main__':
    unittest.main()
