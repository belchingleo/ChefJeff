"""ask-ahead-v2 (was the ahead_throw trial): a throw to the other chef asked ahead is not dropped because they took a step.

No model is called: the kitchen is a local level-4 round and the held answer is built by hand.
"""
import json
import unittest

import ask_ahead
import features
from jev import DecisionLoop
from kitchen import load_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient


def kitchen(level=4):
    config = load_config()
    config.update(level=level)
    return SpatialKitchen(config)


def do(k, who, key):
    k.start(who, next(a for a in k.actions(who) if a.key == key))
    while k.chefs[who].job is not None:
        k.advance(0.05)


def throw(k):
    return next(a for a in k.actions('jeff') if a.key == ask_ahead.PARTNER)


def step_aside(k, seconds=0.7):
    """The human walks a couple of cells by hand, as a player does while Jeff's step goes on (the throw's aim is the
    place and cell it lands on, which moves with them)."""
    k.set_manual('human', 1, 0)
    k.advance(seconds)
    k.set_manual('human', 0, 0)
    k.advance(0.05)


class StillListedTests(unittest.TestCase):
    def test_a_step_by_the_other_chef_keeps_the_throw_aimed_where_they_stand(self):
        k = kitchen()
        do(k, 'jeff', 'fetch beef')
        asked = throw(k)
        step_aside(k)
        listed = k.actions('jeff')
        now = next(a for a in listed if a.key == ask_ahead.PARTNER)
        self.assertNotEqual(now.expected, asked.expected)             # the aim follows the other chef
        self.assertIs(ask_ahead.still_listed(listed, asked), now)
        self.assertTrue(k.start('jeff', now)[0])

    def test_a_different_item_in_hand_is_still_dropped(self):
        k = kitchen()
        do(k, 'jeff', 'fetch beef')
        asked = throw(k)
        do(k, 'jeff', 'drop')
        do(k, 'jeff', 'fetch lettuce')
        self.assertIsNone(ask_ahead.still_listed(k.actions('jeff'), asked))

    def test_other_answers_are_matched_as_before(self):
        k = kitchen()
        do(k, 'jeff', 'fetch beef')
        listed = k.actions('jeff')
        for a in listed:
            self.assertIs(ask_ahead.still_listed(listed, a), a)       # the same key for the same object


class LoopTests(unittest.TestCase):
    def test_a_held_throw_is_carried_out_toward_where_the_other_chef_stands(self):
        """Jeff fetches beef; the loop holds a "throw partner" asked ahead; the human steps aside before it ends."""
        k = kitchen()
        loop = DecisionLoop(k, SpatialJevClient(k.c, key='test-no-credential'), lambda *a: None, lambda *a: None)
        loop.player_messages = []
        loop.ask_ahead = True
        k.start('jeff', next(a for a in k.actions('jeff') if a.key == 'fetch beef'))
        job = k.chefs['jeff'].job
        source = ask_ahead.predict(k)
        actions = {a.key: a for a in source.actions('jeff')}
        context = {'id': 1, 'sent': 0.0, 'epoch': loop.epoch, 'job_id': job.id, 'actions': actions,
                   'ahead': {'job_id': job.id, 'predicted_end_t': source.time, 'cursor': len(k.events),
                             'hand': ask_ahead.hand(source), 'urgency': loop.urgency(source)}}
        loop.held = (context, {'choice': ask_ahead.PARTNER}, None)
        step_aside(k)
        while k.chefs['jeff'].job is not None:
            k.advance(0.05)
        context = loop.release_held(0.5)[0]
        self.assertIsNone(context['ahead_check'])
        decision = context['decision']
        self.assertEqual(decision.key, ask_ahead.PARTNER)
        self.assertNotEqual(decision.expected, actions[ask_ahead.PARTNER].expected)
        self.assertEqual(decision.expected, throw(k).expected)


class FeatureTests(unittest.TestCase):
    def test_part_of_ask_ahead_with_no_switch_of_its_own(self):
        self.assertNotIn('ahead_throw', features.current())
        self.assertEqual(features.current()['ask_ahead']['version'], ask_ahead.VERSION)
        self.assertEqual(ask_ahead.VERSION, 'ask-ahead-v2')

    def test_it_changes_nothing_jeff_is_asked(self):
        # Only the loop reads it: no request option, rule or state field names it. (Since 0.11.0 the released throw_to
        # puts "throw" in the one-press options, so this compares with ask_ahead off instead of searching for the word.)
        current = features.current()
        off = {**current, 'ask_ahead': {**current['ask_ahead'], 'on': False}}
        self.assertEqual(json.dumps(features.compose_options(current)), json.dumps(features.compose_options(off)))


if __name__ == '__main__':
    unittest.main()
