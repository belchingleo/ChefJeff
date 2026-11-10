"""The intent layer (intent_layer.py, features.json intent_layer): options are pieces of work, run as the engine's own steps."""
import unittest
from unittest.mock import patch

import features
import harness
import intent_layer
import jev
from jev import DecisionLoop
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from test_jeff_plan import Inline
from whitebox_server import SpatialJevClient


def idle(k, who):
    while k.chefs[who].job:
        k.advance(.05)


def start(k, who, key):
    k.start(who, next(a for a in k.actions(who) if a.key == key))
    idle(k, who)


def level2():
    return SpatialKitchen(level_config(load_config(), 'level-2'))


def holding_beef():
    k = level2()
    start(k, 'jeff', 'fetch beef')
    return k


class Answering(SpatialJevClient):
    """Answers the queued replies (choice and put_where); else continue when listed, else wait."""

    def __init__(self, config, replies=()):
        super().__init__(config, key='unit-test-not-a-real-key')
        self.replies, self.asked = list(replies), []

    def ask(self, payload):
        self.asked.append(payload)
        criteria = payload['questions']['next_action']['criteria']
        reply = self.replies.pop(0) if self.replies else {}
        choice = reply.get('choice') if reply.get('choice') in criteria else ('continue' if 'continue' in criteria else 'wait')
        answer = {'choice': choice, 'sprint': False, 'confidence': None, 'probabilities': {}, 'model': 'test-only',
                  'usage': {}, 'latency': 0.0}
        if intent_layer.PUT_WHERE in payload['questions']:
            answer[intent_layer.PUT_WHERE] = reply.get(intent_layer.PUT_WHERE)
        return answer


class OptionTests(unittest.TestCase):
    def test_holding_raw_beef_each_board_is_its_own_chop_intent(self):
        k = holding_beef()
        intents, places = intent_layer.build(k, 'jeff', 2, True)
        keys = [o.key for o in intents]
        self.assertIn('chop held b1', keys)
        self.assertIn('chop held b2', keys)
        chop = next(o for o in intents if o.key == 'chop held b1')
        first, rest = intent_layer.steps_of(chop)
        self.assertEqual((first.key, rest), ('put b1', ((('chop',), 'b1'),)))
        # Put places and directional throws are not options of their own; put_where lists the places.
        self.assertFalse(any(o.key.startswith('put ') and o.key != 'put down' for o in intents if o.expected[0] != intent_layer.PUT))
        self.assertNotIn('throw up', keys)
        self.assertIn('throw partner', keys)
        self.assertIn('put down', keys)
        self.assertIn('put b1', [p.key for p in places])
        self.assertTrue(all(p.kind == intent_layer.PLACE for p in places))

    def test_walking_to_a_station_stays_where_another_option_works_there(self):
        k = level2()
        listed_today = {a.key for a in harness.model_candidates(k.snapshot(), k.actions('jeff'), 2)}
        intents, _ = intent_layer.build(k, 'jeff', 2, True)
        keys = {o.key for o in intents}
        self.assertNotIn('go p1', listed_today)       # today: "take pot p1" walks there, so "go p1" is dropped
        self.assertIn('take pot p1', keys)
        self.assertIn('go p1', keys)                  # the intent layer keeps it: walk there and wait

    def test_request_has_intents_put_where_and_the_rule(self):
        k = holding_beef()
        client = SpatialJevClient(k.c, key='unit-test-not-a-real-key')
        intents, places = intent_layer.build(k, 'jeff', 2, True)
        payload = jev.compose_payload(client, k, k.snapshot(), intents + places, [], None,
                                      intent={'current': None, 'last': None, 'since': 0})
        criteria = payload['questions']['next_action']['criteria']
        self.assertEqual(list(criteria), [o.key for o in intents])
        self.assertEqual(set(payload['questions'][intent_layer.PUT_WHERE]['criteria']), {p.key for p in places})
        self.assertIn('intent_layer', payload['state']['rules'])
        self.assertNotIn('one_press', payload['state']['rules'])
        self.assertEqual(payload['state']['intent_layer_version'], intent_layer.VERSION)
        self.assertEqual(payload['state']['intent'], {'current': None, 'last': None})
        self.assertTrue(criteria['chop held b1'].startswith('Chop the held'))

    def test_switch_is_a_trial_and_off(self):
        loaded = features.load()
        self.assertEqual(loaded['intent_layer'], {'stage': 'trial', 'on': False, 'player_switch': False, 'version': 'intent-v1'})
        self.assertFalse(features.intents_on(loaded))


class LoopTests(unittest.TestCase):
    def loop(self, k, replies):
        self.records = []
        self.client = Answering(k.c, replies)
        self.ai = DecisionLoop(k, self.client, lambda kind, data: self.records.append((kind, data)), lambda _: None)
        self.ai.intents = True
        self.ai.ask_ahead = True
        self.ai.player_messages = []
        self.clock = 1000.

    def poll(self, wall=3.):
        self.clock += wall
        with patch('jev.time.monotonic', lambda: self.clock), patch('jev.threading.Thread', Inline):
            self.ai.poll()

    def ask(self):
        """One request and its reply carried out (the reply comes back on the next poll)."""
        self.poll()
        self.poll(.1)

    def run_for(self, k, polls=40, wall=3.):
        for _ in range(polls):
            for _ in range(4):
                k.advance(.05)
            self.poll(wall)

    def rows(self, kind):
        return [d for kd, d in self.records if kd == kind]

    def done(self, k):
        return [e.get('action') for e in k.events if e.get('actor') == 'jeff' and e.get('kind') == 'action_done']

    def test_chop_held_puts_on_the_board_then_chops_without_asking_in_between(self):
        k = holding_beef()
        self.loop(k, [{'choice': 'chop held b2'}])
        self.ask()
        self.assertEqual(len(self.rows('ai_request')), 1)
        self.run_for(k, polls=60)
        self.assertEqual(self.done(k)[-2:], ['put b2', 'chop b2'])
        self.assertEqual(k.stations['b2'].food.stage, 'chopped')
        ends = self.rows('intent_end')
        self.assertEqual([(e['choice'], e['reason'], e['steps_done'], e['steps'], e['executed']) for e in ends],
                         [('chop held b2', 'finished', 2, 2, ['put b2', 'chop b2'])])
        # Asked again only once the intent was under its last step or over, never between its two steps.
        requests = self.rows('ai_request')
        chop_start = next(e['seq'] for e in k.events if e.get('actor') == 'jeff' and e.get('kind') == 'action_start'
                          and e.get('action') == 'chop b2')
        self.assertTrue(all(r['observed_state_seq'] >= chop_start for r in requests[1:]),
                        ([r['observed_state_seq'] for r in requests], chop_start))
        first_after = requests[1]['payload']['state']['intent'] if len(requests) > 1 else None
        self.assertIsNotNone(first_after)
        self.assertEqual(first_after['last']['intent'][:14], 'Chop the held ')

    def test_put_down_goes_where_put_where_says(self):
        k = holding_beef()
        self.loop(k, [{'choice': 'put down', 'put_where': 'put counter5'}])
        self.run_for(k, polls=40)
        self.assertEqual(k.stations['counter5'].food.ingredient, 'beef')
        self.assertEqual(self.rows('ai_response')[0]['intent_start'], {'first': 'put counter5', 'fallback': False})
        self.assertEqual(self.rows('intent_end')[0]['put_where'], 'put counter5')

    def test_no_refresh_or_kitchen_change_asks_during_an_intent(self):
        k = level2()
        self.loop(k, [{'choice': 'go returns'}])
        self.ask()
        k.c['ai_refresh_seconds'] = 1
        job = k.chefs['jeff'].job
        self.assertIsNotNone(job)
        start(k, 'human', 'fetch bread')       # the kitchen changes while Jeff walks
        before = len(self.rows('ai_request'))
        self.ai.reply_times = [99.]            # a reply would come after the walk ends: only ask-ahead could ask
        self.ai.ahead_job = job.id             # and it already did
        self.poll()
        self.assertEqual(len(self.rows('ai_request')), before)

    def test_a_sprint_knock_ends_the_intent_and_says_so(self):
        k = holding_beef()
        self.loop(k, [{'choice': 'go returns'}])
        self.ask()
        self.assertIsNotNone(self.ai.chain)
        k.emit('Jeff被推开', kind='knocked', actor='jeff')
        self.poll()
        self.assertEqual([e['reason'] for e in self.rows('intent_end')], ['knocked'])
        last = self.rows('ai_request')[-1]['payload']['state']['intent']['last']
        self.assertIn('knocked you away', last['result'])

    def test_off_the_request_is_as_before(self):
        k = holding_beef()
        client = SpatialJevClient(k.c, key='unit-test-not-a-real-key')
        payload = jev.compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None)
        self.assertNotIn('intent', payload['state'])
        self.assertNotIn('intent_layer', payload['state']['rules'])


if __name__ == '__main__':
    unittest.main()
