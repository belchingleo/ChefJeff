"""Decision-loop timing (2026-11-21): no mid-chain re-ask on an urgency change, the ask-ahead urgency check, and the
wake callback. No model."""
import unittest
from unittest.mock import patch

from jev import DecisionLoop, more_urgent
from kitchen import Food, load_config
from levels import level_config
from loop_helpers import Inline
from spatial_kitchen import SpatialKitchen
from test_one_press import Answering, BOTH


class MoreUrgentTests(unittest.TestCase):
    def test_only_an_order_or_pan_in_both_that_got_more_urgent_counts(self):
        before = (('O1', 1), ('p1', 0, 0))
        self.assertFalse(more_urgent(before, before))
        self.assertTrue(more_urgent(before, (('O1', 2), ('p1', 0, 0))))           # the order got more urgent
        self.assertTrue(more_urgent(before, (('O1', 1), ('p1', 0, 1))))           # the pan's fire band moved
        self.assertFalse(more_urgent(before, (('O1', 1), ('p1', 0, 0), ('O2', 3))))  # a new order
        self.assertFalse(more_urgent(before, (('p1', 0, 0),)))                     # an order served
        self.assertFalse(more_urgent(before, (('O1', 0), ('p1', 0, 0))))           # less urgent (a restart)
        self.assertFalse(more_urgent(None, before))


class LoopTimingTests(unittest.TestCase):
    def setUp(self):
        self.k = SpatialKitchen(level_config(load_config(), 'level-2'))
        self.records, self.clock, self.woken = [], [1000.], []
        self.ai = DecisionLoop(self.k, Answering(self.k.c, [{'choice': f'wash from {self.k.returns}'}]),
                               lambda kind, data: self.records.append((kind, data)), lambda _: None)
        self.ai.one_press, self.ai.player_messages = dict(BOTH), []
        self.ai.wake = lambda: self.woken.append(self.clock[0])

    def poll(self):
        with patch('jev.time.monotonic', lambda: self.clock[0]), patch('jev.threading.Thread', Inline):
            self.ai.poll()

    def requests(self):
        return [d for kind, d in self.records if kind == 'ai_request']

    def test_an_urgency_change_mid_chain_does_not_ask_now_when_the_reply_would_come_after_the_step(self):
        self.k.stations[self.k.returns].food = Food('D9', 'dirty_plate')
        self.poll()                                     # asks; the reply starts the wash-from-returns chain
        while not self.ai.chain:
            self.clock[0] += .1
            self.poll()
        self.ai.reply_times = [5.0] * 5                 # a reply would come long after this step ends
        self.ai.ahead_job = self.k.chefs['jeff'].job.id     # and this step was asked about ahead already
        before = len(self.requests())
        self.assertFalse(self.ai.inflight)              # nothing else stops it asking
        self.assertIsNone(self.ai.held)
        self.assertTrue(self.ai.outlasts_reply(self.k.chefs['jeff'].job))
        self.ai.last_urgency = ('changed',)             # an order or pan crossed a countdown band
        self.ai.last_revision = -1
        self.clock[0] += 3.
        self.poll()
        self.assertEqual(len(self.requests()), before)  # before 2026-11-21 it asked now, and the reply was dropped

    def test_the_loop_is_woken_when_a_reply_comes(self):
        self.poll()
        self.assertTrue(self.woken)                     # the reply came on the (inline) worker: the loop is woken


if __name__ == '__main__':
    unittest.main()
