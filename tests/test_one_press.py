"""One-press options: offered by fixed conditions on top of the engine's actions, run as the same ordinary steps."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
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



class Pressing(Answering):
    """Takes a one-press option whenever one is offered (put_where: the first listed place), else the recipe's cook move."""

    def __init__(self, config, game):
        super().__init__(config)
        self.game = game

    def ask(self, payload):
        import reference_policy
        criteria = payload['questions']['next_action']['criteria']
        pressed = next((key for key in criteria if key.startswith(('put then take ', 'wash from '))), None)
        move = reference_policy.choose(self.game().k, 'jeff', 'cook')
        choice = pressed or (move.key if move and move.key in criteria else 'wait')
        places = (payload['questions'].get(one_press.PUT_WHERE) or {}).get('criteria') or {}
        self.replies = [{'choice': choice, 'put_where': next(iter(places), None)}]
        return super().ask(payload)


class StatsTests(unittest.TestCase):
    """decision_stats and hands_full_check keep rounds with a one-press switch on apart from rounds with both off."""

    def play(self, folder, on):
        import play
        from test_decision_stats import Inline as Thread
        with patch('play.ROOT', Path(folder)):
            game = GameSession(level_config(load_config(), 'level-2'), client_factory=lambda c: Pressing(c, lambda: game),
                               journal_factory=play.Journal, kitchen_factory=SpatialKitchen, log_prefix='whitebox')
            for name in one_press.NAMES if on else ():
                self.assertEqual(game._command('/api/one-press', {'name': name, 'on': True})[0], 200)
            clock = [1000.0]
            with patch('jev.time.monotonic', lambda: clock[0]), patch('jev.threading.Thread', Thread):
                game.last_tick = game.last_seen = clock[0]
                self.assertEqual(game._command('/api/start', {'speed': 1})[0], 200)
                game.last_tick = game.last_seen = clock[0]
                while game.k.time < 40:
                    clock[0] += .05
                    game.last_seen = clock[0]
                    game.tick(clock[0])
                game._command('/api/end', {})
            game.close()

    def test_rounds_with_a_switch_on_are_counted_apart(self):
        from scripts import decision_stats, jev_replay_check
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.play(folder.name, on=False)
        self.play(folder.name, on=True)
        journals = sorted(Path(folder.name, 'logs').glob('*.jsonl'))
        self.assertEqual(len(journals), 2)
        rounds = [[json.loads(line) for line in path.read_text().splitlines()] for path in journals]
        rows = next(r for r in rounds if r[0].get('one_press'))                       # the round with the switches on
        result = decision_stats.report([Path(folder.name, 'logs')])
        self.assertEqual(result['one_press_rounds'], 1)
        self.assertEqual(sorted(result['models']), ['test-only', 'test-only [one-press]'])
        off, on = result['models']['test-only'], result['models']['test-only [one-press]']
        self.assertEqual((off['rounds'], on['rounds']), (1, 1))
        self.assertNotIn('one_press', off)
        pressed = on['one_press']
        self.assertEqual(pressed['switches'], {'put_then_take+wash_from_returns': 1})
        responses = [r for r in rows if r['kind'] == 'ai_response']
        chosen = Counter(decision_stats.one_press_kind(r['choice']) for r in responses if decision_stats.one_press_kind(r['choice']))
        self.assertGreater(sum(chosen.values()), 0)
        self.assertEqual(pressed['chosen'], dict(chosen))
        self.assertEqual(pressed['started'], sum('one_press' in r for r in responses))
        self.assertEqual(pressed['put_where_fallback'], sum(r['one_press']['fallback'] for r in responses if 'one_press' in r))
        self.assertEqual(pressed['ended'], dict(Counter(r['reason'] for r in rows if r['kind'] == 'one_press_end')))
        self.assertEqual(on['decisions']['answered'], len(responses))
        self.assertLessEqual(pressed['full_swaps'], pressed['swap_backs'])
        self.assertLessEqual(pressed['swap_backs'], pressed['chosen'].get('put_then_take', 0))
        # hands_full_check and the other journal checks can take either group alone.
        items = jev_replay_check.journal_requests([Path(folder.name, 'logs')], model_prefix='test')
        self.assertEqual({i['one_press'] for i in items}, {False, True})
        self.assertEqual(sum(i['one_press'] for i in items), len([r for r in responses if r.get('request_id') is not None
                                                                  and isinstance(r.get('choice'), str)]))

    def test_research_records_carry_the_switches_and_the_start(self):
        from scripts import decision_stats
        record = {'round_id': 'R1', 'duration': 60, 'conditions': {'one_press': {'put_then_take': True, 'wash_from_returns': False,
                                                                                 'version': one_press.VERSION}},
                  'events': [{'type': 'ai_request', 'request_id': 1, 'game_time_ms': 0,
                              'payload': {'candidates': ['wait', 'put then take b1', 'put counter16'],
                                          'one_press': {'put_then_take': True, 'wash_from_returns': False}}},
                             {'type': 'ai_response', 'request_id': 1, 'game_time_ms': 100,
                              'payload': {'choice': {'key': 'put then take b1'}, 'applied': True, 'fresh': True,
                                          'one_press_start': {'first': {'key': 'put counter16'}, 'fallback': True}}}]}
        models = decision_stats.defaultdict(decision_stats.new_model)
        self.assertEqual(decision_stats.add_round(decision_stats.record_rows(record), models), 'not reported [one-press]')
        summary = decision_stats.summary(models['not reported [one-press]'])['one_press']
        self.assertEqual(summary, {'rounds': 1, 'switches': {'put_then_take': 1}, 'offered_in_requests': {'put_then_take': 1},
                                   'chosen': {'put_then_take': 1}, 'started': 1, 'put_where_fallback': 1,
                                   'ended': {'not_recorded': 1}, 'swap_backs': 0, 'full_swaps': 0})

    def test_swaps_back_are_counted(self):
        from scripts import decision_stats

        def chain(n, seconds, put, take):
            return {'kind': 'ai_response', 'request_id': n, 'game_time_ms': seconds * 1000, 'model': 'm', 'applied': True,
                    'fresh': True, 'choice': 'put then take ' + take, 'one_press': {'first': put, 'fallback': False}}
        rows = [{'kind': 'start', 'game_time_ms': 0, 'one_press': {'put_then_take': True, 'wash_from_returns': True}},
                chain(1, 5, 'put counter16', 'b1'),        # bread to counter 16, lettuce from board 1
                chain(2, 9, 'put b1', 'counter16'),        # lettuce back on board 1, bread back: a full swap
                chain(3, 14, 'drop', 'counter16'),         # takes from counter 16, where the last one did not put
                chain(4, 30, 'put counter5', 'plates'),
                chain(5, 45, 'put plates', 'counter5'),    # takes back what it put, but 15 s later
                chain(6, 47, 'drop', 'counter9'),
                chain(7, 50, 'put b2', 'floor'),           # takes back from the floor where it dropped: a swap back
                {'kind': 'end', 'game_time_ms': 60000}]
        models = decision_stats.defaultdict(decision_stats.new_model)
        decision_stats.add_round(rows, models)
        summary = decision_stats.summary(models['m [one-press]'])['one_press']
        self.assertEqual((summary['swap_backs'], summary['full_swaps']), (2, 1))

if __name__ == '__main__':
    unittest.main()
