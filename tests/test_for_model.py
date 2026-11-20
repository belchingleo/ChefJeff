"""harness.for_model: a model is sent the request without its version tags; the round's record keeps them.

No model is called: the clients' HTTP calls are captured locally.
"""
import json
import unittest
from unittest.mock import patch

import features
import harness
from jev import DecisionLoop, compose_payload
from kitchen import load_config
from levels import level_config
from loop_helpers import Reply
from player_api import CompatibleClient
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient


def request():
    """A level-4 request with every switch of the play set on, so it carries many version tags."""
    k = SpatialKitchen(level_config(load_config(), 'level-4'))
    options = {**features.compose_options(features.current()), 'reach': True, 'split': True, 'burn': True,
               'serve_note': True, 'steps': True, 'walk': True, 'undo': {'history': []}}
    return k, compose_payload(SpatialJevClient(k.c, key='x'), k, k.snapshot(), k.actions('jeff'), [], None, **options)


def tags(payload):
    return sorted(key for key in payload['state'] if key.endswith('_version') or key == 'input_language')


class ForModelTests(unittest.TestCase):
    def test_it_leaves_out_the_version_tags_and_nothing_else(self):
        _, payload = request()
        self.assertGreaterEqual(len(tags(payload)), 8)
        self.assertIn('rules_version', tags(payload))
        sent = harness.for_model(payload)
        self.assertEqual(tags(sent), [])
        self.assertEqual({k: v for k, v in payload['state'].items() if k not in tags(payload)}, sent['state'])
        self.assertEqual({k: v for k, v in payload.items() if k != 'state'}, {k: v for k, v in sent.items() if k != 'state'})
        self.assertEqual(len(tags(payload)), len(tags(request()[1])))          # the payload itself is not changed
        self.assertIs(harness.for_model({'questions': {}}).get('state'), None)

    def test_a_decision_service_is_sent_it_without_the_tags(self):
        k, payload = request()
        sent = []

        def urlopen(req, timeout=None):
            sent.append(json.loads(req.data))
            return Reply(json.dumps({'answers': {'next_action': {'type': 'choice', 'choice': 'wait'},
                                                 'sprint': {'type': 'choice', 'choice': 'no'}}, 'model': 'test'}).encode())
        with patch('urllib.request.urlopen', urlopen):
            SpatialJevClient(k.c, key='x').ask(payload)
        self.assertEqual(tags(sent[0]), [])
        self.assertEqual(set(sent[0]['state']), set(payload['state']) - set(tags(payload)))

    def test_a_chat_model_is_sent_it_without_the_tags(self):
        k, payload = request()
        sent = []

        class Opener:
            def open(self, req, timeout=None):
                sent.append(json.loads(req.data))
                return Reply(json.dumps({'choices': [{'message': {'content': '{"choice":"wait","sprint":false}'}}]}).encode())
        setting = {'provider': 'deepseek', 'base_url': 'https://example.invalid/v1', 'model': 'm', 'api_key': 'x'}
        with patch('urllib.request.build_opener', lambda *a, **kw: Opener()):
            CompatibleClient(k.c, setting).ask(payload)
        user = json.loads(sent[0]['messages'][1]['content'])
        self.assertEqual(tags(user), [])
        self.assertIn('kitchen', user['state'])

    def test_the_loop_logs_the_tags_and_hands_the_client_the_request_without_them(self):
        k, payload = request()
        rows, given = [], []

        class Client:
            def ask(self, body):
                given.append(body)
                return {'choice': 'wait', 'sprint': False, 'probabilities': {}, 'model': 'test', 'usage': {}, 'latency': 0.0}

        class Inline:
            def __init__(self, target, daemon=None):
                self.target = target

            def start(self):
                self.target()
        loop = DecisionLoop(k, Client(), lambda kind, data: rows.append((kind, data)), lambda *_: None)
        with patch('jev.threading.Thread', Inline):
            loop.send({'id': 1}, payload, {'request_id': 1})
        logged = next(d for kind, d in rows if kind == 'ai_request')['payload']
        self.assertEqual(tags(logged), tags(payload))
        self.assertEqual(tags(given[0]), [])


if __name__ == '__main__':
    unittest.main()
