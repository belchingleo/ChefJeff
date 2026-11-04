"""Jeff's plan: a few work items it writes with an action, ticked as it does them, with no clock and no fence."""
from copy import deepcopy
import io
import json
import unittest
from unittest.mock import patch
import config_contract as cc
import harness
import model_output
from harness import PLAN_CHAT_RULE, PLAN_KEEP_QUESTION, PLAN_STEP_QUESTIONS, Plan, plan_answer, work_item, work_items
from jev import DecisionLoop, NO_MEMORY, compose_payload
from kitchen import Action, load_config
from levels import level_config
from player_api import CompatibleClient
from spatial_kitchen import SpatialKitchen
from test_web import FakeJournal
from web_server import GameSession
from whitebox_server import SpatialJevClient


def kitchen(level='level-2'):
    return SpatialKitchen(level_config(load_config(), level))


class Scripted(SpatialJevClient):
    """Answers the next queued action (else wait) and, for each plan question asked, the next queued plan answer.

    A plan answer is a list of steps when steps are asked, and 'keep' or 'drop' while a plan holds.
    """

    def __init__(self, config, plans=(), moves=()):
        super().__init__(config, key='unit-test-not-a-real-key')
        self.plans, self.moves, self.asked = list(plans), list(moves), []

    def ask(self, payload):
        self.asked.append(payload)
        criteria = payload['questions']['next_action']['criteria']
        move = self.moves.pop(0) if self.moves else None
        answer = {'choice': move if move in criteria else 'wait' if 'wait' in criteria else next(iter(criteria)),
                  'sprint': False, 'confidence': None, 'probabilities': {}, 'model': 'test-only', 'usage': {}, 'latency': 0.0}
        asked = harness.plan_questions(payload)
        if asked:
            given = self.plans.pop(0) if self.plans else None
            raw = ({q: given[n] if isinstance(given, list) and n < len(given) else 'none' for n, q in enumerate(PLAN_STEP_QUESTIONS)}
                   if PLAN_STEP_QUESTIONS[0] in asked else {PLAN_KEEP_QUESTION: given})
            answer.update(plan_answer(raw, payload))
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
        self.ai.plan = Plan()
        self.ai.player_messages = []
        self.clock = 1000.

    def poll(self, wall=3.):
        self.clock += wall
        with patch('jev.time.monotonic', lambda: self.clock), patch('jev.threading.Thread', Inline):
            self.ai.poll()

    def cycle(self, game_seconds=1., wall=3.):
        """Let game time pass, then poll once: the previous reply is applied and a new request goes out."""
        for _ in range(round(game_seconds / .05)):
            self.k.advance(.05)
        self.ai.last_revision = -1
        self.poll(wall)
        return self.rows('ai_request')[-1]

    def rows(self, kind):
        return [d for k, d in self.records if k == kind]

    def steps(self, request):
        current = request['payload']['state'].get('jeff_plan')
        return [(s['work'], s['done']) for s in current['steps']] if current else None

    def test_asked_with_the_action_then_held_and_shown_from_the_next_request(self):
        self.client.plans = [['fetch:lettuce', 'chop:lettuce', 'plate:lettuce']]
        first = self.cycle()['payload']
        self.assertEqual([q for q in first['questions'] if q.startswith('plan_')], list(PLAN_STEP_QUESTIONS))
        self.assertEqual(first['questions']['plan_step_1']['criteria'], work_items(self.k.snapshot()))
        self.assertEqual(first['questions']['plan_step_2']['criteria'], {**work_items(self.k.snapshot()), 'none': 'No further step'})
        self.assertNotIn('jeff_plan', first['state'])
        self.assertIn('jeff_plan', first['state']['rules'])
        self.assertEqual(first['state']['plan_rules_version'], 'plan-v2')
        second = self.cycle()
        self.assertTrue(self.rows('ai_response')[-1]['plan_set'])
        self.assertEqual(self.steps(second), [('fetch:lettuce', False), ('chop:lettuce', False), ('plate:lettuce', False)])
        self.assertEqual(list(second['payload']['questions'][PLAN_KEEP_QUESTION]['criteria']), ['keep', 'drop'])
        self.assertFalse(set(PLAN_STEP_QUESTIONS) & set(second['payload']['questions']))

    def test_it_has_no_clock(self):
        self.client.plans = [['collect_plates']]         # no dirty plate anywhere at the start: nothing ticks
        self.cycle(), self.cycle()
        for _ in range(6):
            held = self.cycle(game_seconds=10)
        self.assertEqual(self.steps(held), [('collect_plates', False)])
        self.assertTrue(all(r['plan_ended'] is None for r in self.rows('ai_request')))

    def test_a_finished_action_ticks_its_step_in_any_order_and_the_last_one_asks_at_once(self):
        self.client.plans = [['chop:lettuce', 'fetch:lettuce']]
        self.client.moves = ['wait', 'fetch lettuce']
        self.cycle(), self.cycle(), self.cycle()      # the plan is answered, then Jeff is sent to fetch lettuce
        self.assertEqual(self.k.chefs['jeff'].job.action.key, 'fetch lettuce')
        while self.k.chefs['jeff'].job:
            self.k.advance(.05)
            self.poll(wall=.01)
        held = self.cycle(game_seconds=.05)
        self.assertEqual(self.steps(held), [('chop:lettuce', False), ('fetch:lettuce', True)])
        # The last open step: the plan ends, and the request for a new one does not wait out ai_min_interval.
        self.ai.plan_work[999] = 'chop:lettuce'
        self.k.emit('Jeff 完成动作：切菜', kind='action_done', actor='jeff', action='chop b1', action_id=999)
        before = len(self.rows('ai_request'))
        self.poll(wall=.1)
        self.assertEqual(len(self.rows('ai_request')), before + 1)
        ended = self.rows('ai_request')[-1]
        self.assertEqual(ended['plan_ended'], 'done')
        self.assertIn(PLAN_STEP_QUESTIONS[0], ended['payload']['questions'])

    def test_an_action_outside_the_plan_leaves_it_as_it_is(self):
        self.client.plans = [['plate:tomato']]
        self.client.moves = ['wait', 'fetch lettuce']
        self.cycle(), self.cycle()
        while self.k.chefs['jeff'].job:
            self.k.advance(.05)
            self.poll(wall=.01)
        held = self.cycle(game_seconds=.05)
        self.assertEqual(self.steps(held), [('plate:tomato', False)])
        self.assertIsNone(held['plan_ended'])

    def test_drop_ends_it_and_asks_for_a_new_one_at_once(self):
        self.client.plans = [['fetch:lettuce'], 'keep', 'drop']
        self.cycle(), self.cycle(), self.cycle()      # the third reply, waiting to be applied, drops the plan
        before = len(self.rows('ai_request'))
        self.poll(wall=.1)
        self.assertTrue(self.rows('ai_response')[-1]['plan_dropped'])
        self.assertEqual(len(self.rows('ai_request')), before + 1)
        ended = self.rows('ai_request')[-1]
        self.assertEqual(ended['plan_ended'], 'dropped')
        self.assertIn(PLAN_STEP_QUESTIONS[0], ended['payload']['questions'])

    def test_a_new_preference_ends_it_but_a_correction_does_not(self):
        self.client.plans = [['fetch:lettuce']]
        self.cycle(), self.cycle()

        def message(n, kind, code):
            return {'id': f'M{n}', 'kind': kind, 'code': code, 'text': code, 'game_time': self.k.time,
                    'wall_time': '2026-11-03T12:00:00+08:00', 'first_request_id': None, 'context': {}}
        self.ai.player_messages.append(message(1, 'correction', 'mistake'))
        self.assertEqual(self.steps(self.cycle()), [('fetch:lettuce', False)])
        self.ai.player_messages.append(message(2, 'preference', 'wash'))
        ended = self.cycle()
        self.assertEqual(ended['plan_ended'], 'new_preference')
        self.assertIn(PLAN_STEP_QUESTIONS[0], ended['payload']['questions'])

    def test_unknown_answers_leave_no_plan_and_the_action_stands(self):
        self.client.plans = [['dance'], None]
        self.cycle(), self.cycle()
        self.assertFalse(self.rows('ai_response')[-1]['plan_set'])
        self.assertTrue(self.rows('ai_response')[-1]['applied'])
        self.assertIn(PLAN_STEP_QUESTIONS[0], self.rows('ai_request')[-1]['payload']['questions'])
        self.cycle()
        self.assertFalse(self.rows('ai_response')[-1]['plan_set'])

    def test_steps_stop_at_none_or_an_unknown_one(self):
        payload = {'questions': {q: {'criteria': {'serve': 's', 'wash_plates': 'w', **({'none': 'n'} if n else {})}}
                                 for n, q in enumerate(PLAN_STEP_QUESTIONS)}}
        answer = lambda *steps: plan_answer(dict(zip(PLAN_STEP_QUESTIONS, steps)), payload)['plan']['steps']
        self.assertEqual(answer('serve', 'wash_plates', 'none', 'serve'), ['serve', 'wash_plates'])
        self.assertEqual(answer('serve', 'chop:lettuce', 'serve'), ['serve'])
        self.assertEqual(answer('none'), [])
        keep = {'questions': {PLAN_KEEP_QUESTION: {'criteria': {'keep': 'k', 'drop': 'd'}}}}
        self.assertEqual([plan_answer({PLAN_KEEP_QUESTION: v}, keep) for v in ('keep', 'drop', 'Drop', None)],
                         [{'plan': {'keep': True}}, {'plan': {'keep': False}}, {'plan': {'keep': None}}, {'plan': {'keep': None}}])
        self.assertEqual(plan_answer({'plan_step_1': 'serve'}, {'questions': {}}), {})

    def test_a_stale_reply_sets_no_plan_and_drops_none(self):
        self.client.plans = [['fetch:lettuce']]
        self.cycle()
        self.cycle(wall=7)          # older than ai_max_response_age
        self.assertFalse(self.rows('ai_response')[-1]['fresh'])
        self.assertFalse(self.rows('ai_response')[-1]['plan_set'])

    def test_the_listed_actions_are_the_same_with_and_without_a_plan(self):
        state, actions = self.k.snapshot(), self.k.actions('jeff')
        plain = compose_payload(self.client, self.k, deepcopy(state), actions, [], None, NO_MEMORY)
        plan = Plan()
        asking = compose_payload(self.client, self.k, deepcopy(state), actions, [], None, NO_MEMORY, plan.input(state))
        plan.accept({'steps': ['fetch:beef', 'chop:beef']}, self.k.time, work_items(state), None)
        holding = compose_payload(self.client, self.k, deepcopy(state), actions, [], None, NO_MEMORY, plan.input(state))
        for payload in (asking, holding):
            self.assertEqual(payload['questions']['next_action'], plain['questions']['next_action'])
            self.assertEqual(payload['questions']['sprint'], plain['questions']['sprint'])
            self.assertEqual(payload['state']['kitchen'], plain['state']['kitchen'])
        self.assertEqual(compose_payload(self.client, self.k, deepcopy(state), actions, [], None, NO_MEMORY, None), plain)

    def test_the_logged_plan_input_rebuilds_the_request(self):
        self.client.plans = [['fetch:lettuce', 'chop:lettuce']]
        for _ in range(3):
            row = self.cycle()
            rebuilt = compose_payload(SpatialJevClient(self.k.c, key='rebuild'), self.k, self.k.snapshot(), self.k.actions('jeff'),
                                      row['payload']['state']['recent_decisions'], None, NO_MEMORY, row['jeff_plan'])
            self.assertEqual(cc.sha256(rebuilt), cc.sha256(row['payload']))


class WorkItemTests(unittest.TestCase):
    def test_work_items_follow_the_level_menu_and_equipment(self):
        self.assertEqual(list(work_items(kitchen('level-1').snapshot())),
                         ['fetch:beef', 'chop:beef', 'cook:beef', 'plate:beef', 'take_plate', 'serve', 'collect_plates', 'wash_plates'])
        state = kitchen().snapshot()
        items = work_items(state)
        self.assertEqual([w for w in items if w.startswith('chop:')], ['chop:beef', 'chop:lettuce', 'chop:tomato'])
        self.assertNotIn('chop:bread', items)           # bread goes on the plate raw
        self.assertEqual([w for w in items if w.startswith('cook:')], ['cook:beef'])
        no_sink = deepcopy(state)
        no_sink['map']['equipment'] = {k: e for k, e in state['map']['equipment'].items() if e['type'] != 'sink'}
        self.assertNotIn('wash_plates', work_items(no_sink))

    def test_each_action_does_the_work_of_what_it_moves(self):
        k = kitchen()
        state = k.snapshot()
        jeff = lambda held: {**state, 'chefs': {**state['chefs'], 'jeff': {**state['chefs']['jeff'], 'holding': held}}}
        lettuce = {'id': 'F9', 'stage': 'raw', 'ingredient': 'lettuce', 'plate_id': None}
        pot = {'id': 'P1', 'stage': 'pot', 'contents': {'id': 'F2', 'stage': 'ready', 'ingredient': 'beef', 'plate_id': None}}
        plate = {'id': 'D1', 'stage': 'clean_plate'}
        on_board = {**state, 'stations': {**state['stations'], 'b1': {**state['stations']['b1'], 'food': lettuce}}}
        work = lambda kind, target='', held=None, at=None: work_item(Action('x', 'x', kind, target), at or jeff(held))
        self.assertEqual(work('fetch', 'tomato'), 'fetch:tomato')
        self.assertEqual(work('chop', 'b1', at=on_board), 'chop:lettuce')
        self.assertEqual(work('put_pot', 'p1', held={**lettuce, 'ingredient': 'beef', 'stage': 'chopped'}), 'cook:beef')
        self.assertEqual(work('plate_counter', 'counter2', held=pot), 'plate:beef')
        self.assertEqual(work('assemble', 'counter2', held=lettuce), 'plate:lettuce')
        self.assertEqual([work(kind) for kind in ('take_plate', 'take_sink', 'serve', 'take_return', 'wash')],
                         ['take_plate', 'take_plate', 'serve', 'collect_plates', 'wash_plates'])
        self.assertEqual([work(kind, held=plate) for kind in ('go', 'wait', 'put_board', 'take_board', 'merge_plates', 'throw')],
                         [None] * 6)
        self.assertIsNone(work('assemble', 'counter2', held=plate))     # nothing on that counter in this state

    def test_ticks_take_the_first_open_step_of_that_work(self):
        plan = Plan()
        self.assertTrue(plan.accept({'steps': ['fetch:beef', 'chop:beef', 'fetch:beef']}, 2., {'fetch:beef': 'f', 'chop:beef': 'c'}, None))
        self.assertFalse(plan.tick('serve'))
        self.assertFalse(plan.tick('fetch:beef'))
        self.assertEqual([s['done'] for s in plan.current['steps']], [True, False, False])
        self.assertFalse(plan.tick('fetch:beef'))
        self.assertTrue(plan.tick('chop:beef'))
        self.assertIsNone(plan.current)
        self.assertEqual(plan.check(None), 'done')
        self.assertIsNone(plan.check(None))
        self.assertFalse(plan.accept({'steps': ['serve']}, 3., {'fetch:beef': 'f'}, None))   # not offered


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def asking_and_holding(k):
    state, actions = k.snapshot(), k.actions('jeff')
    client = SpatialJevClient(k.c, key='x')
    plan = Plan()
    asking = compose_payload(client, k, deepcopy(state), actions, [], None, NO_MEMORY, plan.input(state))
    plan.accept({'steps': ['fetch:beef', 'chop:beef']}, k.time, work_items(state), None)
    holding = compose_payload(client, k, deepcopy(state), actions, [], None, NO_MEMORY, plan.input(state))
    plain = compose_payload(client, k, deepcopy(state), actions, [], None, NO_MEMORY)
    return asking, holding, plain


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.k = kitchen()
        self.asking, self.holding, self.plain = asking_and_holding(self.k)

    def decision(self, payload, plan_answers):
        answers = {'next_action': {'type': 'choice', 'choice': 'wait'}, 'sprint': {'type': 'choice', 'choice': 'no'}, **plan_answers}
        reply = Reply(json.dumps({'answers': answers, 'model': 'test'}).encode())
        with patch('urllib.request.urlopen', lambda *a, **k: reply):
            return SpatialJevClient(self.k.c, key='x').ask(payload)

    def test_decision_models_answer_the_plan_questions_like_sprint(self):
        choice = lambda value: {'type': 'choice', 'choice': value}
        steps = {'plan_step_1': choice('fetch:beef'), 'plan_step_2': choice('chop:beef'), 'plan_step_3': choice('none')}
        self.assertEqual(self.decision(self.asking, steps)['plan'], {'steps': ['fetch:beef', 'chop:beef']})
        self.assertEqual(self.decision(self.asking, {'plan_step_1': choice('dance')})['plan'], {'steps': []})
        self.assertEqual(self.decision(self.holding, {PLAN_KEEP_QUESTION: choice('drop')})['plan'], {'keep': False})
        self.assertEqual(self.decision(self.holding, {})['plan'], {'keep': None})
        self.assertNotIn('plan', self.decision(self.plain, steps))

    def chat(self, payload, content, provider='deepseek'):
        sent = []

        class Opener:
            def open(self, request, timeout=None):
                sent.append(json.loads(request.data))
                return Reply(json.dumps({'choices': [{'message': {'content': json.dumps(content)}}]}).encode())
        setting = {'provider': provider, 'base_url': 'https://example.invalid/v1', 'model': 'm', 'api_key': 'x'}
        with patch('urllib.request.build_opener', lambda *a, **k: Opener()):
            return CompatibleClient(self.k.c, setting).ask(payload), sent[0]['messages'][0]['content']

    def test_chat_models_add_the_plan_fields_to_their_json_only_when_asked(self):
        answer, system = self.chat(self.asking, {'choice': 'wait', 'sprint': False, 'plan_step_1': 'serve', 'plan_step_2': 'none'})
        self.assertEqual(answer['plan'], {'steps': ['serve']})
        self.assertTrue(system.endswith(PLAN_CHAT_RULE))
        self.assertEqual(self.chat(self.holding, {'choice': 'wait', 'sprint': False, 'plan_keep': 'drop'})[0]['plan'], {'keep': False})
        self.assertEqual(self.chat(self.asking, {'choice': 'wait', 'sprint': False})[0]['plan'], {'steps': []})
        answer, system = self.chat(self.plain, {'choice': 'wait', 'sprint': False, 'plan_step_1': 'serve'})
        self.assertNotIn('plan', answer)
        self.assertNotIn('plan_', system)

    def test_the_zhipu_contract_lists_the_plan_fields_only_when_asked(self):
        system = model_output.zhipu_system(self.asking)
        self.assertIn('"plan_step_1":{"type":"string","enum":["fetch:beef",', system)
        self.assertIn('"required":["choice","sprint","plan_step_1","plan_step_2","plan_step_3","plan_step_4"]', system)
        self.assertIn('"plan_keep":{"type":"string","enum":["keep","drop"]}', model_output.zhipu_system(self.holding))
        self.assertNotIn('plan_', model_output.zhipu_system(self.plain))
        self.assertEqual(self.chat(self.asking, {'choice': 'wait', 'sprint': False, 'plan_step_1': 'serve'}, 'zhipu')[1], system)


class OnlineTests(unittest.TestCase):
    """The online server's decision, chat and browser paths read the plan answers the same way."""

    def setUp(self):
        self.k = kitchen()
        self.asking, self.holding, self.plain = asking_and_holding(self.k)

    def test_jev_and_startlux_replies(self):
        from hosted_jev import parse_answer

        def reply(**plan):
            answers = {'next_action': {'type': 'choice', 'choice': 'wait'}, 'sprint': {'type': 'choice', 'choice': 'no'},
                       **{q: {'type': 'choice', 'choice': v} for q, v in plan.items()}}
            return json.dumps({'answers': answers, 'usage': {}})
        self.assertEqual(parse_answer(reply(plan_step_1='serve', plan_step_2='wash_plates'), self.asking)['plan'],
                         {'steps': ['serve', 'wash_plates']})
        self.assertEqual(parse_answer(reply(plan_keep='drop'), self.holding)['plan'], {'keep': False})
        self.assertEqual(parse_answer(reply(), self.asking)['plan'], {'steps': []})
        self.assertNotIn('plan', parse_answer(reply(plan_step_1='serve'), self.plain))

    def test_free_chat_replies_and_diagnostics(self):
        from hosted_free_models import ForwardError, chat_answer
        from model_status import response_issue

        def raw(answer):
            return json.dumps({'model': 'glm-4.7-flash', 'choices': [{'message': {'content': json.dumps(answer)}}],
                               'usage': {'prompt_tokens': 1, 'completion_tokens': 1}})
        self.assertEqual(chat_answer(raw({'choice': 'wait', 'sprint': False, 'plan_step_1': 'serve'}), self.asking)['plan'],
                         {'steps': ['serve']})
        self.assertEqual(chat_answer(raw({'choice': 'wait', 'sprint': False, 'plan_keep': 'keep'}), self.holding)['plan'],
                         {'keep': True})
        self.assertNotIn('plan', chat_answer(raw({'choice': 'wait', 'sprint': False}), self.plain))
        with self.assertRaises(ForwardError):
            chat_answer(raw({'choice': 'wait', 'sprint': False, 'plan_keep': 'keep'}), self.asking)   # not asked here
        self.assertNotEqual(response_issue(raw({'choice': 'wait', 'plan_step_1': 'serve'}), self.asking, 'zhipu'), 'invalid_json')
        self.assertEqual(response_issue(raw({'choice': 'wait', 'plan_step_1': 'serve'}), self.plain, 'zhipu'), 'invalid_json')

    def test_browser_results(self):
        import threading
        from hosted_server import BrowserRelay, FIELDS
        self.assertIn('plan', FIELDS['/api/model/result'])
        self.assertNotIn('plan_role', FIELDS['/api/model/result'])
        self.assertEqual(FIELDS['/api/plan'], {'mode'})
        relay = BrowserRelay(self.k.c)

        def resolve(payload, **extra):
            relay.pending = {'id': 'task', 'payload': payload, 'event': threading.Event(), 'result': None, 'failure': None, 'sent': 0}
            self.assertTrue(relay.resolve({'id': 'task', 'choice': 'wait', 'sprint': False, **extra}))
            return relay.pending['result']
        self.assertEqual(resolve(self.asking, plan={'plan_step_1': 'serve', 'plan_step_2': None})['plan'], {'steps': ['serve']})
        self.assertEqual(resolve(self.holding, plan={'plan_keep': 'drop'})['plan'], {'keep': False})
        self.assertEqual(resolve(self.asking, plan='serve')['plan'], {'steps': []})
        self.assertNotIn('plan', resolve(self.plain, plan={'plan_step_1': 'serve'}))

    def test_plan_wording_is_factual(self):
        from test_agent_rules_neutral import VALUE_WORDING
        text = (harness.PLAN_RULE + PLAN_CHAT_RULE + json.dumps(harness.PLAN_KEEP) + json.dumps(work_items(self.k.snapshot()))
                + json.dumps({q: self.asking['questions'][q]['instructions'] for q in PLAN_STEP_QUESTIONS})
                + self.holding['questions'][PLAN_KEEP_QUESTION]['instructions'])
        self.assertIsNone(VALUE_WORDING.search(text))


class SessionTests(unittest.TestCase):
    def session(self):
        g = GameSession(level_config(load_config(), 'level-2'), client_factory=lambda c: Scripted(c, [['fetch:lettuce']]),
                        journal_factory=FakeJournal, kitchen_factory=SpatialKitchen)
        self.addCleanup(g.close)
        return g

    def test_the_switch_is_set_between_rounds_and_the_player_sees_the_steps(self):
        g = self.session()
        # Plan mode is on by default.
        self.assertEqual(g.communication_state()['jeff_plan'], {'mode': 'choice', 'editable': True, 'current': None})
        self.assertEqual(g._command('/api/plan', {'mode': 'deep'})[0], 400)
        self.assertEqual(g._command('/api/start', {})[0], 200)
        self.assertIsInstance(g.ai.plan, Plan)
        start = next(d for kind, d in g.journal.journal.rows if kind == 'start')
        self.assertEqual(start['jeff_plan'], {'mode': 'choice', 'steps': 4, 'rules_version': 'plan-v2'})
        self.assertEqual(g._command('/api/plan', {'mode': 'off'})[0], 409)
        g.ai.plan.accept({'steps': ['fetch:lettuce', 'plate:lettuce', 'serve']}, g.k.time, work_items(g.k.snapshot()), None)
        g.ai.plan.tick('fetch:lettuce')
        self.assertEqual(g.communication_state()['jeff_plan']['current'], {'steps': [
            {'label': '取生菜', 'label_en': 'Fetch lettuce', 'done': True},
            {'label': '生菜装盘', 'label_en': 'Plate lettuce', 'done': False},
            {'label': '出餐', 'label_en': 'Serve', 'done': False}]})
        g._command('/api/end', {})
        self.assertIsNone(g.communication_state()['jeff_plan']['current'])
        self.assertEqual(g._command('/api/plan', {'mode': 'off'})[0], 200)
        g._command('/api/reset', {}); g._command('/api/start', {})
        self.assertIsNone(g.ai.plan)
        self.assertNotIn('jeff_plan', next(d for kind, d in g.journal.journal.rows if kind == 'start'))

    def test_every_work_item_of_every_ingredient_has_both_labels(self):
        from web_server import WORK_LABELS, work_label
        k = kitchen()
        names = {key: item.get('name') for key, item in k.rules.items.items()}
        for key, name in names.items():
            for kind in ('fetch', 'chop', 'cook', 'plate'):
                label = work_label(f'{kind}:{key}', k.rules.items)
                self.assertIn(name, label['label'])
                self.assertIn(key, label['label_en'])
        self.assertEqual(set(WORK_LABELS), set(harness.WORK_KINDS))


if __name__ == '__main__':
    unittest.main()
