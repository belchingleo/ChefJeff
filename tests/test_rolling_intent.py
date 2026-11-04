"""The two-step rolling intent: asked with every action, shown back once, replaced by the next answer."""
import unittest
from unittest.mock import patch

from harness import PLAN_KEEP_QUESTION, ROLLING_RULE, ROLLING_YIELD_SECONDS, Plan, burning_soon, plan_condition, work_items
from jev import DecisionLoop
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from copy import deepcopy
import model_output
from jev import NO_MEMORY, compose_payload
import test_jeff_plan
from test_jeff_plan import Inline, Scripted, kitchen
from whitebox_server import SpatialJevClient
from test_web import FakeJournal
from web_server import GameSession
from scripts.decision_stats import add_round, new_model
from collections import defaultdict


class RollingLoopTests(unittest.TestCase):
    def setUp(self, mode='rolling'):
        self.k = kitchen()
        self.client = Scripted(self.k.c)
        self.records = []
        self.ai = DecisionLoop(self.k, self.client, lambda kind, data: self.records.append((kind, data)), lambda _: None)
        self.ai.plan = Plan(mode=mode)
        self.ai.player_messages = []
        self.clock = 1000.

    def poll(self, wall=3.):
        self.clock += wall
        with patch('jev.time.monotonic', lambda: self.clock), patch('jev.threading.Thread', Inline):
            self.ai.poll()

    def cycle(self, game_seconds=1., wall=3.):
        for _ in range(round(game_seconds / .05)):
            self.k.advance(.05)
        self.ai.last_revision = -1
        self.poll(wall)
        return self.rows('ai_request')[-1]

    def rows(self, kind):
        return [d for k, d in self.records if k == kind]

    def steps(self, request):
        """The intent shown to Jeff: on the decision it was noted with, in recent_decisions; never as a plan."""
        state = request['payload']['state']
        self.assertNotIn('jeff_plan', state)
        noted = [d for d in state['recent_decisions'] if 'intent' in d]
        self.assertLessEqual(len(noted), 1)              # only the newest is kept
        return [(s['work'], s['done']) for s in noted[0]['intent']] if noted else None

    def test_every_request_asks_two_steps_and_shows_the_last_answer(self):
        self.client.plans = [['fetch:lettuce', 'chop:lettuce'], None, ['take_plate']]
        first = self.cycle()['payload']
        self.assertEqual([q for q in first['questions'] if q.startswith('plan_')], ['plan_step_1', 'plan_step_2'])
        self.assertEqual(first['questions']['plan_step_1']['criteria'], work_items(self.k.snapshot()))
        self.assertIn('next_action', first['questions']['plan_step_1']['instructions'])
        self.assertEqual(first['state']['rules']['intent'], ROLLING_RULE.format(seconds=ROLLING_YIELD_SECONDS))
        self.assertNotIn('jeff_plan', first['state']['rules'])
        self.assertEqual(first['state']['plan_rules_version'], 'rolling-v3')
        self.assertNotIn('jeff_plan', first['state'])
        second = self.cycle()
        self.assertEqual(self.steps(second), [('fetch:lettuce', False), ('chop:lettuce', False)])
        decisions = second['payload']['state']['recent_decisions']
        self.assertEqual([('intent' in d, d['choice']) for d in decisions], [(True, self.rows('ai_response')[0]['choice'])])
        self.assertIn('plan_step_1', second['payload']['questions'])         # asked again, not keep or drop
        self.assertNotIn(PLAN_KEEP_QUESTION, second['payload']['questions'])
        third = self.cycle()                                                  # no answer: the last intent stays
        self.assertEqual(self.steps(third), [('fetch:lettuce', False), ('chop:lettuce', False)])
        fourth = self.cycle()                                                 # a new answer replaces it
        self.assertEqual(self.steps(fourth), [('take_plate', False)])
        self.assertEqual([r['jeff_plan']['mode'] for r in self.rows('ai_request')], ['rolling'] * 4)
        self.assertEqual([r['plan_set'] for r in self.rows('ai_response')], [True, False, True])

    def test_a_pan_about_to_burn_hides_the_intent_but_still_asks(self):
        from scripts import plan_probe
        _, k, _ = plan_probe.emergencies()[0]          # cooked food a few seconds from burning
        self.assertTrue(burning_soon(k))
        client = Scripted(k.c)
        held = Plan(mode='rolling')
        state = k.snapshot()
        self.assertTrue(held.accept({'steps': ['fetch:lettuce', 'chop:lettuce']}, k.time, work_items(state), None))
        recent = [{'t': round(k.time, 2), 'choice': 'wait', 'accepted': True, 'result': 'wait', 'sprint_applied': False}]
        payload = compose_payload(client, k, deepcopy(state), k.actions('jeff'), recent, None, NO_MEMORY, held.input(state))
        self.assertEqual(payload['state']['recent_decisions'], [{**recent[0], 'result': payload['state']['recent_decisions'][0]['result']}])
        self.assertIn('plan_step_1', payload['questions'])                       # still asked
        quiet = kitchen()                                                        # nothing on a stove: the intent shows
        self.assertFalse(burning_soon(quiet))
        recent = [{**recent[0], 't': round(quiet.time, 2)}]
        held = Plan(mode='rolling')
        held.accept({'steps': ['fetch:lettuce']}, quiet.time, work_items(quiet.snapshot()), None)
        shown = compose_payload(client, quiet, quiet.snapshot(), quiet.actions('jeff'), recent, None, NO_MEMORY,
                                held.input(quiet.snapshot()))
        self.assertEqual(shown['state']['recent_decisions'][0]['intent'], [{'work': 'fetch:lettuce', 'done': False}])

    def test_a_finished_action_ticks_its_step(self):
        self.client.plans = [['fetch:lettuce', 'chop:lettuce']]
        self.client.moves = ['fetch lettuce']
        self.cycle()
        shown = None
        for _ in range(12):
            shown = self.cycle()
            if self.steps(shown) and self.steps(shown)[0][1]:
                break
        self.assertEqual(self.steps(shown)[0], ('fetch:lettuce', True))

    def urgent_while_a_step_outlasts_the_reply(self):
        """A countdown band changes while Jeff's step will end before a reply could come back: is he asked?"""
        self.ai.ask_on_step_end = True
        self.client.moves = ['go serve']
        self.cycle()
        self.cycle()                                # 'go serve' starts
        self.assertIsNotNone(self.k.chefs['jeff'].job)
        self.ai.reply_times = [60.0]                # any step now ends before a reply
        self.ai.last_urgency = ('changed',)
        self.ai.last_revision = self.k.revision
        before = len(self.rows('ai_request'))
        self.poll()
        return len(self.rows('ai_request')) > before

    def test_a_change_of_urgency_asks_even_when_the_step_ends_first(self):
        self.assertTrue(self.urgent_while_a_step_outlasts_the_reply())

    def test_the_four_step_plan_still_waits_for_the_step_to_end(self):
        self.setUp(mode='choice')
        self.assertFalse(self.urgent_while_a_step_outlasts_the_reply())


class RollingConditionTests(unittest.TestCase):
    def test_the_condition_and_input_name_the_mode(self):
        self.assertEqual(plan_condition('rolling', 2), {'mode': 'rolling', 'steps': 2, 'rules_version': 'rolling-v3'})
        self.assertEqual(plan_condition('choice', 4), {'mode': 'choice', 'steps': 4, 'rules_version': 'plan-v2'})
        state = kitchen().snapshot()
        self.assertEqual(Plan(mode='rolling').input(state)['mode'], 'rolling')
        self.assertNotIn('mode', Plan().input(state))                 # the four-step plan's input is unchanged
        with self.assertRaises(ValueError):
            Plan(mode='deep')

    def test_the_session_switch_takes_rolling_between_rounds(self):
        g = GameSession(level_config(load_config(), 'level-2'), client_factory=lambda c: Scripted(c, [['fetch:lettuce']]),
                        journal_factory=FakeJournal, kitchen_factory=SpatialKitchen)
        self.addCleanup(g.close)
        self.assertEqual(g._command('/api/plan', {'mode': 'rolling'})[0], 200)
        self.assertEqual(g.communication_state()['jeff_plan']['mode'], 'rolling')
        self.assertEqual(g._command('/api/start', {})[0], 200)
        self.assertEqual((g.ai.plan.mode, g.ai.plan.steps), ('rolling', 2))
        start = next(d for kind, d in g.journal.journal.rows if kind == 'start')
        self.assertEqual(start['jeff_plan'], {'mode': 'rolling', 'steps': 2, 'rules_version': 'rolling-v3'})

    def test_decision_stats_counts_rolling_rounds_apart(self):
        rows = [{'kind': 'start', 'game_time_ms': 0, 'jeff_plan': plan_condition('rolling', 2)},
                {'kind': 'ai_request', 'game_time_ms': 0, 'request_id': 1, 'candidates': ['wait'],
                 'jeff_plan': {'mode': 'rolling', 'steps': 2, 'current': None, 'options': {}}},
                {'kind': 'ai_response', 'game_time_ms': 0, 'request_id': 1, 'choice': 'wait', 'model': 'm', 'applied': True},
                {'kind': 'end', 'game_time_ms': 60000}]
        models = defaultdict(new_model)
        add_round(rows, models)
        self.assertEqual((models['m']['plan_rolling_rounds'], models['m']['plan_rounds'], models['m']['plan_older_rounds']), (1, 0, 0))


class RollingClientTests(test_jeff_plan.ClientTests):
    """Decision, chat and Zhipu clients read the two rolling questions like the plan's, with no client change."""
    def setUp(self):
        self.k = kitchen()
        state, actions = self.k.snapshot(), self.k.actions('jeff')
        plan = Plan(mode='rolling')
        self.rolling = compose_payload(SpatialJevClient(self.k.c, key='x'), self.k, deepcopy(state), actions, [], None, NO_MEMORY,
                                       plan.input(state))

    def test_the_rolling_questions_are_read_by_every_client(self):
        choice = lambda value: {'type': 'choice', 'choice': value}
        self.assertEqual(self.decision(self.rolling, {'plan_step_1': choice('fetch:beef'), 'plan_step_2': choice('chop:beef')})['plan'],
                         {'steps': ['fetch:beef', 'chop:beef']})
        answer, _ = self.chat(self.rolling, {'choice': 'wait', 'sprint': False, 'plan_step_1': 'serve', 'plan_step_2': 'none'})
        self.assertEqual(answer['plan'], {'steps': ['serve']})
        self.assertIn('"required":["choice","sprint","plan_step_1","plan_step_2"]', model_output.zhipu_system(self.rolling))

    # The inherited four-step plan tests run in test_jeff_plan; here only the rolling one.
    test_decision_models_answer_the_plan_questions_like_sprint = None
    test_chat_models_add_the_plan_fields_to_their_json_only_when_asked = None
    test_the_zhipu_contract_lists_the_plan_fields_only_when_asked = None


if __name__ == '__main__':
    unittest.main()
