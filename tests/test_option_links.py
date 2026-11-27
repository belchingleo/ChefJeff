"""The option_links switch (links.py, features.json option_links): each request lists the work each option leads to."""
import json
import unittest
from unittest.mock import patch

import features
import jev
import links
from jev import DecisionLoop
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from loop_helpers import Inline
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

    def test_the_work_listed_follows_the_game_s_work_kinds(self):
        # Every chop, cook (a held pan scooping off a counter included), plate, serve and wash kind counts as work;
        # fetching and taking (a plate, a return) do not, and putting a dirty plate in the sink does.
        import harness
        kinds = harness.WORK_KINDS
        expected = {*kinds['chop'], *kinds['cook'], *kinds['plate'], *kinds['serve'], *kinds['wash_plates'], 'put_sink'}
        self.assertEqual(set(links.WORK), expected)
        self.assertIn('scoop_counter', links.WORK)

    def test_switch_is_released_and_on_with_no_player_switch(self):
        # 步骤提示 had a Settings switch until 2026-11-20; per model service it is set by off_for, not by the player.
        self.assertEqual(features.load()['option_links'], {'stage': 'release', 'on': True, 'version': links.SWITCH_VERSION})


class LoopTests(unittest.TestCase):
    def test_each_request_records_how_long_the_table_took(self):
        k = holding_beef()
        records, clock = [], [1000.]
        loop = DecisionLoop(k, Answering(k.c), lambda kind, data: records.append((kind, data)), lambda _: None)
        loop.links, loop.player_messages = True, []
        with patch('jev.time.monotonic', lambda: clock[0]), patch('jev.threading.Thread', Inline):
            loop.poll()                       # builds the request; the table is filled off the game loop
            built_at = len(k.inputs)
            self.assertFalse([d for kind, d in records if kind == 'ai_request'])
            loop.poll()                       # and the request goes out at the next poll (its reply then moves Jeff)
        request = next(d for kind, d in records if kind == 'ai_request')
        self.assertEqual(request['engine_input_n'], built_at)
        self.assertIn('links_ms', request)
        self.assertIn('option_links', request['payload']['state'])


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


class PartnerTests(unittest.TestCase):
    """option_links_partner (v3): on a split floor, a put on a shared counter, or a throw across, carries the other
    chef's chain on the item in Jeff's own line, up to their first work on it; v5: only work at a place Jeff cannot
    reach counts."""

    def setUp(self):
        self.k = SpatialKitchen(level_config(load_config(), 'level-4'))
        run(self.k, 'jeff', 'fetch beef')

    def payload(self, links_value):
        client = SpatialJevClient(self.k.c, key='unit-test-not-a-real-key')
        return jev.compose_payload(client, self.k, self.k.snapshot(), self.k.actions('jeff'), [], None, links=links_value)

    def test_a_shared_counter_put_names_the_other_chefs_chain_up_to_chopping(self):
        state = self.payload('partner')['state']
        self.assertEqual(state['partner_links_version'], links.PARTNER_VERSION)
        self.assertIn('then the other chef could', state['rules']['links'])
        shared = [key for key in state['option_links'] if key.startswith('put counter')]
        self.assertTrue(shared)
        for key in shared:
            chain = [line for line in state['option_links'][key] if line.startswith(links.THEN)]
            self.assertEqual(len(chain), 1)
            self.assertIn('Chop', chain[0])
        self.assertNotIn('option_links_partner', state)

    def test_a_throw_to_the_other_chef_names_their_chain_once_it_has_landed_or_been_caught(self):
        # v3: the throw ends when the item leaves the hand; the fork runs on until it is down, then follows it.
        state = self.payload('partner')['state']
        chain = [line for line in state['option_links'].get('throw partner', []) if line.startswith(links.THEN)]
        self.assertEqual(len(chain), 1)
        self.assertIn('Chop', chain[0])
        self.assertFalse(self.k.projectiles)                     # the request's kitchen threw nothing

    def test_v4_a_throw_onto_a_board_while_the_other_chef_holds_something_names_their_put_down_first(self):
        # v3 found no chain here: chopping needs free hands and a put-down never names the thrown item.
        import one_press
        run(self.k, 'human', 'take counter2')                    # the player's hands are full
        self.assertIsNotNone(self.k.chefs['human'].hand)
        opts = features.compose_options(features.with_override(features.load(), {'one_press': {'on': True},
                                                                                   'throw_to': {'on': True}}))
        acts = self.k.actions('jeff')
        throw = next(a for a in one_press.options(self.k, 'jeff', acts, opts['one_press']) if a.key == 'throw to b1')
        seen = {}
        links.link(self.k, 'jeff', throw, acts, seen=seen)
        chain = links.partner_chain(self.k, seen['twin'], 'jeff', self.k.chefs['jeff'].hand.id)
        self.assertEqual([a.kind for a in chain], ['put_counter', 'chop'])
        self.assertEqual(chain[1].target, 'b1')

    def test_v5_bread_the_chef_can_plate_itself_gets_no_partner_line(self):
        # 2026-11-27, round 4012c0b3: Jeff held bread beside a clean plate he could fill himself, and his throw read
        # "then the other chef could: Pick up bread ..., then Put the held bread onto the plate at Counter 2".
        k = SpatialKitchen(level_config(load_config(), 'level-4'))
        run(k, 'jeff', 'fetch bread')
        self.assertTrue(any(a.kind == 'assemble' for a in k.actions('jeff')))
        client = SpatialJevClient(k.c, key='unit-test-not-a-real-key')
        state = jev.compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, links='partner')['state']
        self.assertFalse([key for key, lines in state['option_links'].items()
                          if any(line.startswith(links.THEN) for line in lines)])

    def test_v5_on_a_floor_both_chefs_share_no_option_has_a_partner_line(self):
        k = SpatialKitchen(level_config(load_config(), 'level-2'))
        self.assertFalse(k.split_floor)
        run(k, 'jeff', 'fetch beef')
        client = SpatialJevClient(k.c, key='unit-test-not-a-real-key')
        state = jev.compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, links='partner')['state']
        self.assertFalse(any(line.startswith(links.THEN) for lines in state['option_links'].values() for line in lines))

    def test_with_free_hands_no_put_down_is_added(self):
        state = self.payload('partner')['state']
        chain = [line for line in state['option_links'].get('throw partner', []) if line.startswith(links.THEN)]
        self.assertNotIn('Put the held', chain[0].split(links.THEN)[1].split(',')[0])

    def test_without_the_partner_switch_no_chain_is_sent(self):
        state = self.payload(True)['state']
        self.assertFalse(any(line.startswith(links.THEN) for lines in state['option_links'].values() for line in lines))
        self.assertNotIn('partner_links_version', state)

    def test_the_switch_is_released_and_on_and_needs_option_links(self):
        loaded = features.load()
        self.assertTrue(loaded['option_links_partner']['on'])
        on = {name: dict(value) for name, value in loaded.items()}
        on['option_links_partner']['on'] = True
        on['option_links']['on'] = False
        self.assertIs(features.links_option(on), False)
        on['option_links']['on'] = True
        self.assertEqual(features.links_option(on), 'partner')
