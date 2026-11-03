"""Jeff's plan, multiple-choice tier: asked with the action, held for a while, never changes the menu."""
from copy import deepcopy
import io
import json
import unittest
from unittest.mock import patch
import config_contract as cc
import harness
import jev
import model_output
from harness import Plan, action_part, plan_parts, PLAN_CHAT_RULE
from jev import DecisionLoop, NO_MEMORY, compose_payload
from kitchen import Action, load_config
from levels import level_config
from player_api import CompatibleClient
from spatial_kitchen import SpatialKitchen
from test_web import FakeJournal
from web_server import GameSession
from whitebox_server import SpatialJevClient


def kitchen():
    return SpatialKitchen(level_config(load_config(), 'level-2'))


class Scripted(SpatialJevClient):
    """Answers wait (or the first offered action) and, when asked, the next queued plan answer."""

    def __init__(self, config, plans=()):
        super().__init__(config, key='unit-test-not-a-real-key')
        self.plans, self.asked = list(plans), []

    def ask(self, payload):
        self.asked.append(payload)
        criteria = payload['questions']['next_action']['criteria']
        answer = {'choice': 'wait' if 'wait' in criteria else next(iter(criteria)), 'sprint': False, 'confidence': None,
                  'probabilities': {}, 'model': 'test-only', 'usage': {}, 'latency': 0.0}
        if 'plan_role' in payload['questions']:
            answer['plan_role'] = self.plans.pop(0) if self.plans else None
        return answer


class Inline:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


class PlanLoopTests(unittest.TestCase):
    def setUp(self):
        self.k = kitchen()
        self.client = Scripted(self.k.c)
        self.records = []
        self.ai = DecisionLoop(self.k, self.client, lambda kind, data: self.records.append((kind, data)), lambda _: None)
        self.ai.plan = Plan(12)
        self.ai.player_messages = []
        self.clock = 1000.

    def cycle(self, game_seconds=1., wall=3.):
        """Let game time pass, then poll once: the previous reply is applied and a new request goes out."""
        for _ in range(round(game_seconds / .05)):
            self.k.advance(.05)
        self.clock += wall
        self.ai.last_revision = -1
        with patch('jev.time.monotonic', lambda: self.clock), patch('jev.threading.Thread', Inline):
            self.ai.poll()
        return [d for kind, d in self.records if kind == 'ai_request'][-1]

    def rows(self, kind):
        return [d for k, d in self.records if k == kind]

    def test_asked_with_the_action_then_held_from_the_next_request(self):
        self.client.plans = ['prep']
        first = self.cycle()['payload']
        self.assertEqual(list(first['questions']['plan_role']['criteria']), ['prep', 'cook', 'serve', 'plates', 'flexible'])
        self.assertNotIn('jeff_plan', first['state'])
        self.assertIn('jeff_plan', first['state']['rules'])
        self.assertEqual(first['state']['plan_rules_version'], 'plan-v1')
        second = self.cycle()['payload']
        self.assertTrue(self.rows('ai_response')[-1]['plan_set'])
        self.assertEqual(second['state']['jeff_plan']['role'], 'prep')
        self.assertEqual(second['state']['jeff_plan']['expires_at'] - second['state']['jeff_plan']['set_at'], 12)
        self.assertNotIn('plan_role', second['questions'])

    def test_ends_after_its_time_and_is_asked_again(self):
        self.client.plans = ['prep', 'serve']
        self.cycle(), self.cycle()
        held = self.cycle(game_seconds=6)
        self.assertEqual(held['payload']['state']['jeff_plan']['role'], 'prep')
        ended = self.cycle(game_seconds=7)
        self.assertEqual(ended['plan_ended'], 'expired')
        self.assertIn('plan_role', ended['payload']['questions'])

    def test_a_new_preference_ends_it_but_a_correction_does_not(self):
        self.client.plans = ['prep']
        self.cycle(), self.cycle()

        def message(n, kind, code):
            return {'id': f'M{n}', 'kind': kind, 'code': code, 'text': code, 'game_time': self.k.time,
                    'wall_time': '2026-11-03T12:00:00+08:00', 'first_request_id': None, 'context': {}}
        self.ai.player_messages.append(message(1, 'correction', 'mistake'))
        self.assertEqual(self.cycle()['payload']['state']['jeff_plan']['role'], 'prep')
        self.ai.player_messages.append(message(2, 'preference', 'wash'))
        ended = self.cycle()
        self.assertEqual(ended['plan_ended'], 'new_preference')
        self.assertIn('plan_role', ended['payload']['questions'])

    def test_a_part_with_nothing_to_do_ends_and_is_asked_in_the_same_request(self):
        self.client.plans = ['plates', 'flexible']
        self.cycle(), self.cycle()
        ended = self.rows('ai_request')[-1]
        self.assertEqual(ended['plan_ended'], 'nothing_to_do')      # no dirty plate anywhere at the start
        self.assertIn('plan_role', ended['payload']['questions'])
        held = self.cycle()
        self.assertEqual(held['payload']['state']['jeff_plan']['role'], 'flexible')   # flexible has no part to run out of
        self.assertIsNone(held['plan_ended'])

    def test_an_unknown_or_missing_answer_leaves_no_plan_and_the_action_stands(self):
        self.client.plans = ['dance', None]
        self.cycle(), self.cycle()
        self.assertFalse(self.rows('ai_response')[-1]['plan_set'])
        self.assertTrue(self.rows('ai_response')[-1]['applied'])
        self.assertIn('plan_role', self.rows('ai_request')[-1]['payload']['questions'])
        self.cycle()
        self.assertFalse(self.rows('ai_response')[-1]['plan_set'])

    def test_a_stale_reply_sets_no_plan(self):
        self.client.plans = ['prep']
        self.cycle()
        self.cycle(wall=7)          # older than ai_max_response_age
        self.assertFalse(self.rows('ai_response')[-1]['fresh'])
        self.assertFalse(self.rows('ai_response')[-1]['plan_set'])

    def test_the_listed_actions_are_the_same_with_and_without_a_plan(self):
        state, actions = self.k.snapshot(), self.k.actions('jeff')
        plain = compose_payload(self.client, self.k, deepcopy(state), actions, [], None, NO_MEMORY)
        plan = Plan(12)
        asking = compose_payload(self.client, self.k, deepcopy(state), actions, [], None, NO_MEMORY, plan.input(state))
        plan.accept('cook', self.k.time, plan_parts(state), None)
        holding = compose_payload(self.client, self.k, deepcopy(state), actions, [], None, NO_MEMORY, plan.input(state))
        for payload in (asking, holding):
            self.assertEqual(payload['questions']['next_action'], plain['questions']['next_action'])
            self.assertEqual(payload['questions']['sprint'], plain['questions']['sprint'])
            self.assertEqual(payload['state']['kitchen'], plain['state']['kitchen'])
        self.assertEqual(compose_payload(self.client, self.k, deepcopy(state), actions, [], None, NO_MEMORY, None), plain)

    def test_the_logged_plan_input_rebuilds_the_request(self):
        self.client.plans = ['prep']
        for _ in range(3):
            row = self.cycle()
            rebuilt = compose_payload(SpatialJevClient(self.k.c, key='rebuild'), self.k, self.k.snapshot(), self.k.actions('jeff'),
                                      row['payload']['state']['recent_decisions'], None, NO_MEMORY, row['jeff_plan'])
            self.assertEqual(cc.sha256(rebuilt), cc.sha256(row['payload']))


class PartTests(unittest.TestCase):
    def test_parts_follow_the_level_equipment_and_recipes(self):
        state = kitchen().snapshot()
        self.assertEqual(list(plan_parts(state)), ['prep', 'cook', 'serve', 'plates', 'flexible'])
        no_sink = deepcopy(state)
        no_sink['map']['equipment'] = {k: e for k, e in state['map']['equipment'].items() if e['type'] != 'sink'}
        self.assertEqual(list(plan_parts(no_sink)), ['prep', 'cook', 'serve', 'flexible'])
        raw_only = deepcopy(state)
        for dish in raw_only['dishes']:
            for c in dish['components']:
                c['state'] = 'chopped'
        self.assertNotIn('cook', plan_parts(raw_only))

    def test_each_action_kind_has_one_part_and_a_throw_follows_its_item(self):
        state = kitchen().snapshot()
        seen = [kind for kinds in harness.PLAN_PARTS.values() for kind in kinds]
        self.assertEqual(len(seen), len(set(seen)))
        part = lambda kind, held=None: action_part(Action(kind, 'x', kind, 'x'), {'chefs': {'jeff': {'holding': held}}} if held is not None or kind == 'throw' else state)
        self.assertEqual([part(k) for k in ('fetch', 'wash', 'serve', 'put_pot', 'go', 'wait', 'extinguish')],
                         ['prep', 'plates', 'serve', 'cook', None, None, None])
        self.assertEqual([part('throw', h) for h in ({'stage': 'raw'}, {'stage': 'pot'}, {'stage': 'clean_plate'},
                                                     {'stage': 'assembled', 'plate_id': 'D1'}, {'stage': 'dirty_plate'},
                                                     {'stage': 'extinguisher'})],
                         ['prep', 'cook', 'serve', 'serve', 'plates', None])

    def test_the_action_jeff_is_doing_counts_as_work_in_its_part(self):
        # Walking to the only fridge: that fetch is no longer listed, but the prep plan still has work.
        state = kitchen().snapshot()
        listed = [Action('continue', 'x', 'continue', None), Action('stop', 'x', 'stop', None)]
        plan = Plan(12)
        plan.accept('prep', 0., plan_parts(state), None)
        self.assertIsNone(plan.check(1., state, listed, None, Action('fetch', 'x', 'fetch', 'fridge')))
        self.assertEqual(plan.check(1., state, listed, None), 'nothing_to_do')


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class ClientTests(unittest.TestCase):
    def setUp(self):
        k = kitchen()
        state, actions = k.snapshot(), k.actions('jeff')
        self.plan = Plan(12).input(state)
        self.asked = compose_payload(SpatialJevClient(k.c, key='x'), k, state, actions, [], None, NO_MEMORY, self.plan)
        self.plain = compose_payload(SpatialJevClient(k.c, key='x'), k, k.snapshot(), actions, [], None, NO_MEMORY)
        self.k = k

    def decision(self, payload, plan_answer):
        answers = {'next_action': {'type': 'choice', 'choice': 'wait'}, 'sprint': {'type': 'choice', 'choice': 'no'}}
        if plan_answer:
            answers['plan_role'] = plan_answer
        reply = Reply(json.dumps({'answers': answers, 'model': 'test'}).encode())
        with patch('urllib.request.urlopen', lambda *a, **k: reply):
            return SpatialJevClient(self.k.c, key='x').ask(payload)

    def test_decision_models_answer_plan_role_like_sprint(self):
        self.assertEqual(self.decision(self.asked, {'type': 'choice', 'choice': 'cook'})['plan_role'], 'cook')
        self.assertIsNone(self.decision(self.asked, {'type': 'choice', 'choice': 'dance'})['plan_role'])
        self.assertIsNone(self.decision(self.asked, None)['plan_role'])
        self.assertNotIn('plan_role', self.decision(self.plain, {'type': 'choice', 'choice': 'cook'}))

    def chat(self, payload, content, provider='deepseek'):
        sent = []

        class Opener:
            def open(self, request, timeout=None):
                sent.append(json.loads(request.data))
                return Reply(json.dumps({'choices': [{'message': {'content': json.dumps(content)}}]}).encode())
        setting = {'provider': provider, 'base_url': 'https://example.invalid/v1', 'model': 'm', 'api_key': 'x'}
        with patch('urllib.request.build_opener', lambda *a, **k: Opener()):
            return CompatibleClient(self.k.c, setting).ask(payload), sent[0]['messages'][0]['content']

    def test_chat_models_add_plan_role_to_their_json_only_when_asked(self):
        answer, system = self.chat(self.asked, {'choice': 'wait', 'sprint': False, 'plan_role': 'serve'})
        self.assertEqual(answer['plan_role'], 'serve')
        self.assertTrue(system.endswith(PLAN_CHAT_RULE))
        self.assertIsNone(self.chat(self.asked, {'choice': 'wait', 'sprint': False, 'plan_role': 'Serve!'})[0]['plan_role'])
        self.assertIsNone(self.chat(self.asked, {'choice': 'wait', 'sprint': False})[0]['plan_role'])
        answer, system = self.chat(self.plain, {'choice': 'wait', 'sprint': False, 'plan_role': 'serve'})
        self.assertNotIn('plan_role', answer)
        self.assertNotIn('plan_role', system)

    def test_the_zhipu_contract_lists_the_parts_only_when_asked(self):
        system = model_output.zhipu_system(self.asked)
        self.assertIn('"plan_role":{"type":"string","enum":["prep","cook","serve","plates","flexible"]}', system)
        self.assertIn('"required":["choice","sprint","plan_role"]', system)
        self.assertNotIn('plan_role', model_output.zhipu_system(self.plain))
        self.assertEqual(self.chat(self.asked, {'choice': 'wait', 'sprint': False, 'plan_role': 'prep'}, 'zhipu')[1], system)


class OnlineTests(unittest.TestCase):
    """The online server's decision, chat and browser paths read plan_role the same way."""

    def setUp(self):
        k = kitchen()
        self.k = k
        self.asked = compose_payload(SpatialJevClient(k.c, key='x'), k, k.snapshot(), k.actions('jeff'), [], None, NO_MEMORY,
                                     Plan(12).input(k.snapshot()))
        self.plain = compose_payload(SpatialJevClient(k.c, key='x'), k, k.snapshot(), k.actions('jeff'), [], None, NO_MEMORY)

    def test_jev_and_startlux_replies(self):
        from hosted_jev import parse_answer
        def reply(plan):
            answers = {'next_action': {'type': 'choice', 'choice': 'wait'}, 'sprint': {'type': 'choice', 'choice': 'no'}}
            if plan is not None:
                answers['plan_role'] = plan
            return json.dumps({'answers': answers, 'usage': {}})
        self.assertEqual(parse_answer(reply({'type': 'choice', 'choice': 'serve'}), self.asked)['plan_role'], 'serve')
        for plan in ({'type': 'choice', 'choice': 'dance'}, 'serve', None):
            self.assertIsNone(parse_answer(reply(plan), self.asked)['plan_role'])
        self.assertNotIn('plan_role', parse_answer(reply({'type': 'choice', 'choice': 'serve'}), self.plain))

    def test_free_chat_replies_and_diagnostics(self):
        from hosted_free_models import ForwardError, chat_answer
        from model_status import response_issue
        def raw(answer):
            return json.dumps({'model': 'glm-4.7-flash', 'choices': [{'message': {'content': json.dumps(answer)}}],
                               'usage': {'prompt_tokens': 1, 'completion_tokens': 1}})
        self.assertEqual(chat_answer(raw({'choice': 'wait', 'sprint': False, 'plan_role': 'plates'}), self.asked)['plan_role'], 'plates')
        self.assertIsNone(chat_answer(raw({'choice': 'wait', 'sprint': False, 'plan_role': 'dishes'}), self.asked)['plan_role'])
        self.assertNotIn('plan_role', chat_answer(raw({'choice': 'wait', 'sprint': False}), self.plain))
        with self.assertRaises(ForwardError):
            chat_answer(raw({'choice': 'wait', 'sprint': False, 'note': 'other fields stay refused'}), self.asked)
        self.assertNotEqual(response_issue(raw({'choice': 'wait', 'plan_role': 'prep'}), self.asked, 'zhipu'), 'invalid_json')

    def test_browser_results(self):
        import threading
        from hosted_server import BrowserRelay, FIELDS
        self.assertIn('plan_role', FIELDS['/api/model/result'])
        self.assertEqual(FIELDS['/api/plan'], {'mode'})
        relay = BrowserRelay(self.k.c)
        def resolve(payload, **extra):
            relay.pending = {'id': 'task', 'payload': payload, 'event': threading.Event(), 'result': None, 'failure': None, 'sent': 0}
            self.assertTrue(relay.resolve({'id': 'task', 'choice': 'wait', 'sprint': False, **extra}))
            return relay.pending['result']
        self.assertEqual(resolve(self.asked, plan_role='cook')['plan_role'], 'cook')
        self.assertIsNone(resolve(self.asked, plan_role='dance')['plan_role'])
        self.assertIsNone(resolve(self.asked)['plan_role'])
        self.assertNotIn('plan_role', resolve(self.plain, plan_role='cook'))

    def test_plan_wording_is_factual(self):
        from test_agent_rules_neutral import VALUE_WORDING
        text = (harness.PLAN_RULE + PLAN_CHAT_RULE + json.dumps(harness.PLAN_OPTIONS)
                + self.asked['questions']['plan_role']['instructions'])
        self.assertIsNone(VALUE_WORDING.search(text))


class SessionTests(unittest.TestCase):
    def session(self):
        g = GameSession(level_config(load_config(), 'level-2'), client_factory=lambda c: Scripted(c, ['prep']),
                        journal_factory=FakeJournal, kitchen_factory=SpatialKitchen)
        self.addCleanup(g.close)
        return g

    def test_the_switch_is_set_between_rounds_and_installs_the_plan(self):
        g = self.session()
        self.assertEqual(g.communication_state()['jeff_plan'], {'mode': 'off', 'editable': True, 'current': None})
        self.assertEqual(g._command('/api/plan', {'mode': 'deep'})[0], 400)
        self.assertEqual(g._command('/api/plan', {'mode': 'choice'})[0], 200)
        self.assertEqual(g._command('/api/start', {})[0], 200)
        self.assertIsInstance(g.ai.plan, Plan)
        start = next(d for kind, d in g.journal.journal.rows if kind == 'start')
        self.assertEqual(start['jeff_plan'], {'mode': 'choice', 'seconds': 12, 'rules_version': 'plan-v1'})
        self.assertEqual(g._command('/api/plan', {'mode': 'off'})[0], 409)
        g.ai.plan.accept('prep', g.k.time, plan_parts(g.k.snapshot()), None)
        self.assertEqual(g.communication_state()['jeff_plan']['current'], {'role': 'prep', 'remaining': 12.0})
        g._command('/api/end', {})
        self.assertIsNone(g.communication_state()['jeff_plan']['current'])
        self.assertEqual(g._command('/api/plan', {'mode': 'off'})[0], 200)
        g._command('/api/reset', {}); g._command('/api/start', {})
        self.assertIsNone(g.ai.plan)
        self.assertNotIn('jeff_plan', next(d for kind, d in g.journal.journal.rows if kind == 'start'))


if __name__ == '__main__':
    unittest.main()
