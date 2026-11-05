"""One-press options: offered by fixed conditions on top of the engine's actions, run as the same ordinary steps."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import harness
import model_output
import one_press
from jev import DecisionLoop, NO_MEMORY, compose_payload
from kitchen import Food, load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from test_jeff_plan import Inline, Reply
from test_web import FakeJournal
from web_server import GameSession
from whitebox_server import SpatialJevClient

BOTH = {'put_then_take': True, 'wash_from_returns': True}


def idle(k, who):
    while k.chefs[who].job:
        k.advance(.05)


def start(k, who, key):
    k.start(who, next(a for a in k.actions(who) if a.key == key))
    idle(k, who)


def bread_and_lettuce():
    """Level 2: Jeff holds bread; the human has put lettuce on board 1."""
    k = SpatialKitchen(level_config(load_config(), 'level-2'))
    start(k, 'jeff', 'fetch bread')
    start(k, 'human', 'fetch lettuce')
    start(k, 'human', 'put b1')
    return k


class Answering(SpatialJevClient):
    """Answers the queued replies (choice and put_where), else continue or wait."""

    def __init__(self, config, replies=()):
        super().__init__(config, key='unit-test-not-a-real-key')
        self.replies, self.asked = list(replies), []

    def ask(self, payload):
        self.asked.append(payload)
        criteria = payload['questions']['next_action']['criteria']
        reply = self.replies.pop(0) if self.replies else {}
        choice = reply.get('choice') if reply.get('choice') in criteria else ('continue' if 'continue' in criteria else 'wait')
        answer = {'choice': choice, 'sprint': False, 'confidence': None, 'probabilities': {}, 'model': 'test-only', 'usage': {},
                  'latency': 0.0}
        if one_press.PUT_WHERE in payload['questions']:
            answer[one_press.PUT_WHERE] = reply.get(one_press.PUT_WHERE)
        return answer


class OptionTests(unittest.TestCase):
    def test_put_then_take_names_what_he_takes(self):
        k = bread_and_lettuce()
        actions = k.actions('jeff')
        options = one_press.options(k, 'jeff', actions, BOTH)
        self.assertEqual([(o.key, o.kind, o.target) for o in options], [('put then take b1', 'put_then_take', 'b1')])
        self.assertEqual(options[0].label, '先把手中的面包放到 put_where 选的位置，再从案板 1拿起生菜')
        self.assertEqual(one_press.options(k, 'jeff', actions, None), [])                     # switches off
        self.assertEqual(one_press.options(k, 'jeff', actions, {'wash_from_returns': True}), [])
        self.assertEqual(k.chefs['jeff'].hand.ingredient, 'bread')                            # the hands are as they were

    def test_nothing_when_an_action_is_already_there_or_the_hands_are_empty(self):
        k = SpatialKitchen(level_config(load_config(), 'level-2'))
        self.assertEqual(one_press.options(k, 'jeff', k.actions('jeff'), BOTH), [])           # empty hands, no dirty plate
        k = bread_and_lettuce()
        k.stations['b1'].food.stage = 'chopped'                                              # chopped lettuce can be plated
        start(k, 'jeff', 'put counter16')
        start(k, 'jeff', 'take plates')                                                       # a clean plate: assemble b1 is listed
        self.assertTrue(any(a.key == 'assemble b1' for a in k.actions('jeff')))
        self.assertNotIn('put then take b1', [o.key for o in one_press.options(k, 'jeff', k.actions('jeff'), BOTH)])

    def test_wash_from_returns_with_and_without_something_in_hand(self):
        k = bread_and_lettuce()
        k.stations[k.returns].food = Food('D9', 'dirty_plate')
        full = [o for o in one_press.options(k, 'jeff', k.actions('jeff'), BOTH) if o.kind == 'wash_from_returns']
        self.assertEqual([o.key for o in full], [f'wash from {k.returns}'])
        self.assertTrue(full[0].label.startswith('先把手中的面包放到 put_where 选的位置，再从'))
        empty = SpatialKitchen(level_config(load_config(), 'level-2'))
        empty.stations[empty.returns].food = Food('D9', 'dirty_plate')
        wash = one_press.options(empty, 'jeff', empty.actions('jeff'), BOTH)
        self.assertEqual([o.label for o in wash], [f'从{empty.stations[empty.returns].name}拿起脏餐盘，放入{empty.stations[empty.sink].name}并洗碗'])
        empty.stations[empty.sink].food = Food('D8', 'dirty_plate')                           # the sink is taken: no wash
        self.assertEqual(one_press.options(empty, 'jeff', empty.actions('jeff'), BOTH), [])

    def test_the_request_asks_where_only_with_a_one_press_option_and_full_hands(self):
        k = bread_and_lettuce()
        client = SpatialJevClient(k.c, key='x')
        payload = compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, NO_MEMORY, None, BOTH)
        criteria = payload['questions']['next_action']['criteria']
        self.assertEqual(criteria['put then take b1'], 'Put the held Bread where put_where says, then take Lettuce from Board 1')
        self.assertNotIn('go b1', criteria)                    # the one-press option walks there, so the plain walk goes
        places = payload['questions']['put_where']['criteria']
        self.assertTrue(places and all(k2 == 'drop' or k2.startswith('put ') for k2 in places))
        self.assertTrue(all(places[k2] == criteria[k2] for k2 in places))                     # the menu's own put labels
        self.assertEqual(payload['state']['rules']['one_press'], one_press.RULE)
        self.assertEqual(payload['state']['one_press_version'], one_press.VERSION)
        plain = compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, NO_MEMORY)
        self.assertNotIn('put_where', plain['questions'])
        self.assertNotIn('one_press', plain['state']['rules'])
        self.assertIn('go b1', plain['questions']['next_action']['criteria'])

    def test_answers_are_read_alike_by_every_client(self):
        k = bread_and_lettuce()
        payload = compose_payload(SpatialJevClient(k.c, key='x'), k, k.snapshot(), k.actions('jeff'), [], None, NO_MEMORY, None, BOTH)
        place = next(iter(payload['questions']['put_where']['criteria']))
        self.assertEqual(harness.choice_questions(payload), ['put_where'])
        self.assertEqual(harness.choice_answer({'put_where': place}, payload), {'put_where': place})
        self.assertEqual(harness.choice_answer({'put_where': 'nowhere'}, payload), {'put_where': None})
        reply = Reply(json.dumps({'answers': {'next_action': {'type': 'choice', 'choice': 'put then take b1'},
                                              'sprint': {'type': 'choice', 'choice': 'no'},
                                              'put_where': {'type': 'choice', 'choice': place}}, 'model': 'test'}).encode())
        with patch('urllib.request.urlopen', lambda *a, **kw: reply):
            self.assertEqual(SpatialJevClient(k.c, key='x').ask(payload)['put_where'], place)
        system = model_output.zhipu_system(payload)
        self.assertIn('"put_where":{"type":"string","enum":[', system)
        self.assertIn('questions.put_where is a field whose value is one of its keys.', system)
        from player_api import CompatibleClient
        sent = []

        class Opener:
            def open(self, request, timeout=None):
                sent.append(json.loads(request.data))
                content = json.dumps({'choice': 'put then take b1', 'sprint': False, 'put_where': place})
                return Reply(json.dumps({'choices': [{'message': {'content': content}}]}).encode())
        setting = {'provider': 'deepseek', 'base_url': 'https://example.invalid/v1', 'model': 'm', 'api_key': 'x'}
        with patch('urllib.request.build_opener', lambda *a, **kw: Opener()):
            answer = CompatibleClient(k.c, setting).ask(payload)
        self.assertEqual(answer['put_where'], place)
        self.assertTrue(sent[0]['messages'][0]['content'].endswith(harness.PUT_WHERE_CHAT_RULE))
        self.assertNotIn(harness.PLAN_CHAT_RULE, sent[0]['messages'][0]['content'])


class ChainTests(unittest.TestCase):
    def loop(self, k, replies):
        self.records = []
        self.client = Answering(k.c, replies)
        self.ai = DecisionLoop(k, self.client, lambda kind, data: self.records.append((kind, data)), lambda _: None)
        self.ai.one_press = dict(BOTH)
        self.ai.player_messages = []
        self.clock = 1000.

    def run_for(self, k, polls=60):
        for _ in range(polls):
            for _ in range(4):
                k.advance(.05)
            self.ai.last_revision = -1
            self.clock += 3.
            with patch('jev.time.monotonic', lambda: self.clock), patch('jev.threading.Thread', Inline):
                self.ai.poll()

    def done(self, k):
        return [e.get('action') for e in k.events if e.get('actor') == 'jeff' and e.get('kind') == 'action_done']

    def rows(self, kind):
        return [d for kd, d in self.records if kd == kind]

    def test_put_then_take_puts_where_he_chose_then_takes(self):
        k = bread_and_lettuce()
        self.loop(k, [{'choice': 'put then take b1', 'put_where': 'put counter16'}])
        self.run_for(k)
        self.assertEqual(self.done(k)[-2:], ['put counter16', 'take b1'])
        self.assertEqual((k.stations['counter16'].food.ingredient, k.chefs['jeff'].hand.ingredient), ('bread', 'lettuce'))
        self.assertEqual(self.rows('ai_response')[0]['one_press'], {'first': 'put counter16', 'fallback': False})
        self.assertEqual([(r['choice'], r['reason']) for r in self.rows('one_press_end')], [('put then take b1', 'finished')])
        self.assertEqual(self.rows('ai_request')[0]['one_press'], BOTH)

    def test_a_missing_place_falls_back_to_the_first_listed_put_and_says_so(self):
        k = bread_and_lettuce()
        self.loop(k, [{'choice': 'put then take b1', 'put_where': None}])
        self.run_for(k)
        pressed = self.rows('ai_response')[0]['one_press']
        self.assertTrue(pressed['fallback'])
        self.assertEqual(self.done(k)[-2:], [pressed['first'], 'take b1'])

    def test_wash_from_returns_runs_every_step(self):
        k = SpatialKitchen(level_config(load_config(), 'level-2'))
        k.stations[k.returns].food = Food('D9', 'dirty_plate')
        self.loop(k, [{'choice': f'wash from {k.returns}'}])
        self.run_for(k, polls=120)
        self.assertEqual(self.done(k), [f'take {k.returns}', f'put {k.sink}', 'wash'])
        self.assertEqual(k.stations[k.sink].food.stage, 'clean_plate')
        self.assertEqual([r['reason'] for r in self.rows('one_press_end')], ['finished'])

    def test_a_step_that_cannot_be_done_ends_it(self):
        k = bread_and_lettuce()
        self.loop(k, [{'choice': 'put then take b1', 'put_where': 'put counter16'}])
        self.run_for(k, polls=1)                       # the put has started
        k.stations['b1'].food = None                   # the lettuce is gone before he can take it
        self.run_for(k)
        self.assertNotIn('take b1', self.done(k))
        self.assertEqual([r['reason'] for r in self.rows('one_press_end')], ['step_not_possible'])

    def test_another_choice_replaces_it(self):
        k = bread_and_lettuce()
        self.loop(k, [{'choice': 'put then take b1', 'put_where': 'put counter16'}, {'choice': 'go serve'}])
        self.ai.ask_on_step_end = False                # ask mid-step, so the second answer comes while the put runs
        self.run_for(k, polls=3)
        self.assertEqual([r['reason'] for r in self.rows('one_press_end')], ['replaced'])
        self.assertNotIn('take b1', self.done(k))


class SessionTests(unittest.TestCase):
    def test_each_switch_is_set_between_rounds_and_recorded(self):
        g = GameSession(level_config(load_config(), 'level-2'), client_factory=lambda c: Answering(c),
                        journal_factory=FakeJournal, kitchen_factory=SpatialKitchen)
        self.addCleanup(g.close)
        self.assertEqual(g.communication_state()['one_press'], {'put_then_take': False, 'wash_from_returns': False, 'editable': True})
        self.assertEqual(g._command('/api/one-press', {'name': 'dance', 'on': True})[0], 400)
        self.assertEqual(g._command('/api/one-press', {'name': 'put_then_take', 'on': 'yes'})[0], 400)
        self.assertEqual(g._command('/api/one-press', {'name': 'put_then_take', 'on': True})[0], 200)
        self.assertEqual(g._command('/api/start', {})[0], 200)
        self.assertEqual(g.ai.one_press, {'put_then_take': True, 'wash_from_returns': False})
        start_row = next(d for kind, d in g.journal.journal.rows if kind == 'start')
        self.assertEqual(start_row['one_press'], {'put_then_take': True, 'wash_from_returns': False, 'version': one_press.VERSION})
        self.assertEqual(g._command('/api/one-press', {'name': 'put_then_take', 'on': False})[0], 409)
        g._command('/api/end', {})
        self.assertEqual(g._command('/api/one-press', {'name': 'put_then_take', 'on': False})[0], 200)
        g._command('/api/reset', {}); g._command('/api/start', {})
        self.assertIsNone(g.ai.one_press)
        self.assertNotIn('one_press', next(d for kind, d in g.journal.journal.rows if kind == 'start'))


if __name__ == '__main__':
    unittest.main()
