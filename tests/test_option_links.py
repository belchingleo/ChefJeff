"""The option_links switch (links.py, features.json option_links): each request lists the work each option leads to."""
import unittest
from unittest.mock import patch

import features
import jev
import links
from jev import DecisionLoop
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from test_jeff_plan import Inline
from links_test_client import Answering
from whitebox_server import SpatialJevClient


def run(k, who, key):
    k.start(who, next(a for a in k.actions(who) if a.key == key))
    while k.chefs[who].job:
        k.advance(.05)


def holding_beef():
    k = SpatialKitchen(level_config(load_config(), 'level-2'))
    run(k, 'jeff', 'fetch beef')
    return k


class RequestTests(unittest.TestCase):
    def payload(self, k, on):
        client = SpatialJevClient(k.c, key='unit-test-not-a-real-key')
        return jev.compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, links=on)

    def test_on_the_table_names_the_work_and_no_option_changes(self):
        k = holding_beef()
        off, on = self.payload(k, False), self.payload(k, True)
        self.assertEqual(on['questions'], off['questions'])
        self.assertIn('Chop', ' '.join(on['state']['option_links']['put b1']))
        self.assertNotIn('go serve', on['state']['option_links'])
        self.assertEqual(on['state']['links_version'], links.SWITCH_VERSION)
        self.assertIn('links', on['state']['rules'])
        on.pop('state'), off.pop('state')
        self.assertEqual(on, off)

    def test_off_the_request_is_as_before(self):
        k = holding_beef()
        off = self.payload(k, False)
        self.assertNotIn('option_links', off['state'])
        self.assertNotIn('links', off['state']['rules'])

    def test_the_same_kitchen_gives_the_same_table(self):
        k = holding_beef()
        self.assertEqual(self.payload(k, True), self.payload(k, True))
        self.assertEqual(k.chefs['jeff'].hand.ingredient, 'beef')

    def test_switch_is_a_trial_and_off(self):
        self.assertEqual(features.load()['option_links'],
                         {'stage': 'trial', 'on': False, 'player_switch': False, 'version': 'option-links-v1'})


class LoopTests(unittest.TestCase):
    def test_each_request_records_how_long_the_table_took(self):
        k = holding_beef()
        records, clock = [], [1000.]
        loop = DecisionLoop(k, Answering(k.c), lambda kind, data: records.append((kind, data)), lambda _: None)
        loop.links, loop.player_messages = True, []
        with patch('jev.time.monotonic', lambda: clock[0]), patch('jev.threading.Thread', Inline):
            loop.poll()
        request = next(d for kind, d in records if kind == 'ai_request')
        self.assertIn('links_ms', request)
        self.assertIn('option_links', request['payload']['state'])


if __name__ == '__main__':
    unittest.main()
