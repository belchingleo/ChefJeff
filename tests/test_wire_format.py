"""compact-v1 (wire_format.py): lossless, one static part per round for every client, a small live part, and no
change at all with the switch off."""
import json
import re
import statistics
import unittest
from pathlib import Path
from unittest.mock import patch

import features
import model_output
import payload_fingerprint as pf
import player_api
import wire_format as w

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ('level1', 'level2', 'level3', 'level2-plan', 'level2-rolling', 'level2-messages-memory')
CANON = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True)
_RECORDED = {}


def requests(name):
    """Every payload one fingerprint scenario sends (one round each), recorded once per test run."""
    if name not in _RECORDED:
        rows, ask = [], pf.StandIn.ask

        def keep(self, payload):
            rows.append(json.loads(json.dumps(payload, ensure_ascii=False)))
            return ask(self, payload)
        with patch.object(pf.StandIn, 'ask', keep):
            pf.run(name)
        _RECORDED[name] = rows
    return _RECORDED[name]


def compact(on=True):
    value = {key: dict(v) for key, v in features.current().items()}
    value['compact_input']['on'] = on
    return patch.object(features, 'current', lambda: {key: dict(v) for key, v in value.items()})


def setting(provider):
    preset = player_api.PROVIDERS[provider]
    return {'provider': provider, 'base_url': preset.get('base_url') or 'https://example.invalid/v1',
            'model': next((m for m in preset.get('models') or [] if m), 'test-model'), 'api_key': 'unit-test-not-a-real-key'}


def sent_body(client, payload):
    """The body a client would post, captured before any network."""
    box = []

    class Stop(Exception):
        pass

    def grab(request, *_, **__):
        box.append(json.loads(request.data))
        raise Stop()

    class Opener:
        open = staticmethod(grab)
    with patch('urllib.request.urlopen', grab), patch('urllib.request.build_opener', lambda *_, **__: Opener()):
        try:
            client.ask(payload)
        except Exception:
            pass
    return box[0]


class WireFormatTests(unittest.TestCase):
    def test_expand_gives_back_every_request_of_every_scenario(self):
        for name in SCENARIOS:
            for n, payload in enumerate(requests(name)):
                static, live = w.split(payload['state'])
                self.assertEqual(CANON(w.expand(static, live)), CANON(payload['state']), f'{name} request {n}')

    def test_the_static_part_is_one_text_per_round_for_every_client(self):
        for name in SCENARIOS:
            with self.subTest(name), compact():
                chat = player_api.CompatibleClient(pf.load_config(), setting('deepseek'))
                parts = {'chat': set(), 'zhipu': set(), 'free': set(), 'decision': set()}
                for payload in requests(name):
                    parts['chat'].add(sent_body(chat, payload)['messages'][0]['content'])
                    parts['zhipu'].add(model_output.zhipu_body(payload)['messages'][0]['content'])
                    parts['free'].add(model_output.chat_body(payload, 'm')['messages'][0]['content'])
                    parts['decision'].add(w.dumps(w.decision_body(payload)['state']['static']))
                self.assertEqual({client: len(texts) for client, texts in parts.items()}, dict.fromkeys(parts, 1))
        messages = requests('level2-messages-memory')
        self.assertTrue(any('player_communication' in p['state'] for p in messages)
                        and not all('player_communication' in p['state'] for p in messages))     # messages arrive mid-round
        self.assertTrue(all('past_episodes' in p['state'] for p in messages))

    def test_the_live_part_is_under_30_percent_of_todays_message(self):
        for name in SCENARIOS:
            today = statistics.median(len(json.dumps({'state': p['state'], 'questions': p['questions']}, ensure_ascii=False))
                                      for p in requests(name))
            live = statistics.median(len(w.dumps({'live': w.split(p['state'])[1], 'questions': p['questions']}))
                                     for p in requests(name))
            self.assertLessEqual(live / today, 0.30, name)

    def test_defaults_match_by_type_so_nothing_changes_shape(self):
        state = {'kitchen': {'stations': {'s': {'name': 'S', 'type': 'counter', 'fire': 0, 'fire_heat': 0, 'workers': []}},
                             'chefs': {'jeff': {'working': 0, 'travel_remaining': 0.0, 'route': [], 'resync': False}}}}
        static, live = w.split(state)
        self.assertEqual(live['kitchen']['stations'], {'s': {'fire': 0, 'fire_heat': 0}})   # 0 is not False, nor 0.0
        self.assertEqual(live['kitchen']['chefs'], {'jeff': {'working': 0, 'travel_remaining': 0.0, 'resync': False}})
        self.assertEqual(CANON(w.expand(static, live)), CANON(state))

    def test_switch_off_sends_todays_bytes(self):
        payload = requests('level2')[5]
        with compact(False):
            self.assertNotIn('static', json.dumps(model_output.chat_body(payload, 'm')))
            body = sent_body(player_api.CompatibleClient(pf.load_config(), setting('deepseek')), payload)
            self.assertEqual(json.loads(body['messages'][1]['content']), {'state': payload['state'], 'questions': payload['questions']})
        self.assertFalse(features.current()['compact_input']['on'])                              # off in the repository

    def test_clients_put_static_first_and_the_changing_parts_last(self):
        payload = requests('level2-rolling')[20]
        with compact():
            chat = sent_body(player_api.CompatibleClient(pf.load_config(), setting('deepseek')), payload)['messages']
            self.assertIn(w.CHAT_STATIC_INTRO, chat[0]['content'])
            self.assertTrue(chat[0]['content'].startswith(player_api.CHAT_SYSTEM + player_api.PLAN_CHAT_RULE))   # the round can ask
            self.assertTrue(chat[1]['content'].startswith(w.CHAT_LIVE_NOTE))
            zhipu = model_output.zhipu_body(payload)['messages']
            self.assertNotIn('JSON Schema: {', zhipu[0]['content'])                                  # the enum changes
            self.assertIn('\nJSON Schema: ', zhipu[1]['content'])
            decision = sent_body(player_api.create_client(pf.load_config(), setting('jev')), payload)
            self.assertEqual(list(decision['state']), ['static', 'live'])
            self.assertEqual(decision['questions'], payload['questions'])
            self.assertEqual(CANON(w.expand(decision['state']['static'], decision['state']['live'])), CANON(payload['state']))

    def test_the_browser_places_the_parts_with_the_same_text(self):
        source = (ROOT / 'hosted' / 'browser-agent.js').read_text(encoding='utf-8')
        for name in ('CHAT_STATIC_INTRO', 'CHAT_LIVE_NOTE'):
            literal = re.search(rf"const {name} = '([^']*)';", source).group(1)
            self.assertEqual(literal, json.dumps(getattr(w, name))[1:-1], name)
        import hosted_server
        relay = hosted_server.BrowserRelay(pf.load_config())
        relay.pending = {'id': 'r1', 'payload': requests('level2')[3], 'event': __import__('threading').Event()}
        self.assertNotIn('wire', relay.request())
        with compact():
            sent = relay.request()
        self.assertEqual(sent['wire']['version'], w.VERSION)
        self.assertEqual(CANON(w.expand(sent['wire']['static'], sent['wire']['live'])), CANON(sent['payload']['state']))

    def test_cached_prompt_tokens_are_recorded_when_the_provider_reports_them(self):
        self.assertEqual(player_api.cached_tokens({'prompt_cache_hit_tokens': 8000}), {'cached_input_tokens': 8000})
        self.assertEqual(player_api.cached_tokens({'prompt_tokens_details': {'cached_tokens': 512}}), {'cached_input_tokens': 512})
        self.assertEqual(player_api.cached_tokens({'prompt_tokens': 9}), {})

    def test_the_fingerprint_with_the_switch_on_has_the_same_payload(self):
        compacted = json.loads((pf.GOLDEN / 'level2-compact.json').read_text())
        plain = json.loads((pf.GOLDEN / 'level2.json').read_text())
        self.assertEqual([(r['payload'], r['sections']) for r in compacted['requests']],
                         [(r['payload'], r['sections']) for r in plain['requests']])
        wired = [(a['wire'], b['wire']) for a, b in zip(compacted['requests'], plain['requests']) if 'wire' in a]
        self.assertTrue(wired and all(a[k] != b[k] for a, b in wired for k in a))               # every client sends it


if __name__ == '__main__':
    unittest.main()
