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
                         {'stage': 'trial', 'on': False, 'player_switch': False, 'version': 'option-links-v2'})


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


class IntentTests(unittest.TestCase):
    """Both switches on: the table is computed for the intents (links.link carries an intent's own steps out)."""

    def test_an_intent_that_takes_a_plate_leads_to_plating_the_cooked_beef(self):
        import intent_layer
        k = SpatialKitchen(level_config(load_config(), 'level-2'))
        for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
            run(k, 'jeff', key)
        while k.stations['p1'].food.stage != 'ready':
            k.advance(.05)
        intents, places = intent_layer.build(k, 'jeff', 2, True)
        client = SpatialJevClient(k.c, key='unit-test-not-a-real-key')
        payload = jev.compose_payload(client, k, k.snapshot(), intents + places, [], None,
                                      intent={'current': None, 'last': None, 'since': 0}, links=True)
        table = payload['state']['option_links']
        self.assertIn('take plates', table)
        self.assertTrue(any('Stove 1' in line for line in table['take plates']))
        self.assertTrue(set(table) <= set(payload['questions']['next_action']['criteria']))

    def test_an_intent_that_puts_first_is_carried_out_with_its_steps(self):
        import intent_layer
        k = holding_beef()
        intents, places = intent_layer.build(k, 'jeff', 2, True)
        option = next(o for o in intents if o.key == 'put then fetch bread')
        work = links.link(k, 'jeff', option, k.actions('jeff'))
        self.assertTrue(work and all(a.kind in links.WORK for a in work))



class FastForkTests(unittest.TestCase):
    """v2: forks share the unchanging parts and a route cache; the kitchen itself is never changed."""

    def test_a_table_leaves_the_kitchen_as_it_was(self):
        import copy
        k = holding_beef()
        run(k, 'human', 'fetch lettuce')
        keep = {n: copy.deepcopy(vars(k.__dict__[n]) if hasattr(k.__dict__[n], '__dict__') else k.__dict__[n])
                for n in links.SHARED + ('provenance',) if n in k.__dict__}
        snapshot = k.snapshot()
        links.table(k, 'jeff', k.actions('jeff'), [a.key for a in k.actions('jeff')], True)
        self.assertEqual(k.snapshot(), snapshot)
        for n, v in keep.items():
            self.assertEqual(vars(k.__dict__[n]) if hasattr(k.__dict__[n], '__dict__') else k.__dict__[n], v, n)

    def test_walks_waits_and_stops_have_no_link(self):
        k = holding_beef()
        table = links.table(k, 'jeff', k.actions('jeff'), [a.key for a in k.actions('jeff')])
        self.assertFalse([key for key in table if key.split(' ')[0] in ('go', 'wait', 'stop')])
        self.assertIn('put b1', table)

    def test_fast_and_plain_forks_agree_on_every_option_but_walks(self):
        k = holding_beef()
        actions = [a for a in k.actions('jeff') if a.kind not in links.NO_EFFECT]
        keys = [a.key for a in actions]
        try:
            links.FAST = False
            plain = links.table(k, 'jeff', actions, keys)
        finally:
            links.FAST = True
        self.assertEqual(links.table(k, 'jeff', actions, keys), plain)


if __name__ == '__main__':
    unittest.main()
