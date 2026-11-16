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

    def test_the_work_listed_follows_the_game_s_work_kinds(self):
        # Every chop, cook (a held pan scooping off a counter included), plate, serve and wash kind counts as work;
        # fetching and taking (a plate, a return) do not, and putting a dirty plate in the sink does.
        import harness
        kinds = harness.WORK_KINDS
        expected = {*kinds['chop'], *kinds['cook'], *kinds['plate'], *kinds['serve'], *kinds['wash_plates'], 'put_sink'}
        self.assertEqual(set(links.WORK), expected)
        self.assertIn('scoop_counter', links.WORK)

    def test_switch_is_a_trial_on_by_default_with_a_player_switch(self):
        self.assertEqual(features.load()['option_links'],
                         {'stage': 'trial', 'on': True, 'player_switch': True, 'version': links.SWITCH_VERSION})


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


class PartnerTests(unittest.TestCase):
    """option_links_partner (v2): on a split floor, a put on a shared counter carries the other chef's chain on the item
    in Jeff's own line, up to their first work on it."""

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

    def test_without_the_partner_switch_no_chain_is_sent(self):
        state = self.payload(True)['state']
        self.assertFalse(any(line.startswith(links.THEN) for lines in state['option_links'].values() for line in lines))
        self.assertNotIn('partner_links_version', state)

    def test_the_switch_is_a_trial_and_off_and_needs_option_links(self):
        loaded = features.load()
        self.assertFalse(loaded['option_links_partner']['on'])
        on = {name: dict(value) for name, value in loaded.items()}
        on['option_links_partner']['on'] = True
        on['option_links']['on'] = False
        self.assertIs(features.links_option(on), False)
        on['option_links']['on'] = True
        self.assertEqual(features.links_option(on), 'partner')


def pan_nearly_done(heated):
    """Level 2: chopped beef in the pan on Stove 1, Jeff holding a clean plate, the beef heated this long (of 10 s)."""
    k = SpatialKitchen(level_config(load_config(), 'level-2'))
    for step in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1', 'take plates'):
        run(k, 'jeff', step)
    while k.stations['p1'].food.heated < heated:
        k.advance(.05)
    return k


def with_presses(k):
    import one_press
    actions = k.actions('jeff')
    return actions + one_press.options(k, 'jeff', actions, one_press.flags({name: True for name in one_press.NAMES}))


class V4Tests(unittest.TestCase):
    """option_links_v4: the table against waiting (a wait row, and option rows without what waiting opens), and the work
    every single-step option that empties Jeff's hands opens written once."""

    def payload(self, k, value, actions=None):
        client = SpatialJevClient(k.c, key='unit-test-not-a-real-key')
        return jev.compose_payload(client, k, k.snapshot(), actions or k.actions('jeff'), [], None, links=value)

    def test_a_pan_finishing_is_listed_under_wait_and_under_no_other_option(self):
        k = pan_nearly_done(8.6)
        actions = with_presses(k)
        keys = [a.key for a in actions]
        self.assertNotIn('wait', links.table(k, 'jeff', actions, keys))
        rows, _ = links.table_v4(k, 'jeff', actions, keys)
        self.assertEqual(rows['wait'], ['Plate food from Stove 1'])
        self.assertFalse([key for key, lines in rows.items() if key != 'wait' and 'Plate food from Stove 1' in lines])

    def test_an_option_keeps_only_what_it_opens_beyond_waiting(self):
        # Taking the plate back after putting it down takes long enough for the beef to finish: v3 credits the plating
        # to that option, v4 leaves it to wait.
        k = pan_nearly_done(8.6)
        actions = with_presses(k)
        keys = [a.key for a in actions]
        v3 = links.table(k, 'jeff', actions, keys)
        rows, _ = links.table_v4(k, 'jeff', actions, keys)
        credited = [key for key, lines in v3.items() if 'Plate food from Stove 1' in lines]
        for key in credited:
            self.assertNotIn('Plate food from Stove 1', rows.get(key, []))
        for key, lines in rows.items():
            if key != 'wait':
                self.assertTrue(set(lines) <= set(v3.get(key, [])), key)

    def test_work_from_freed_hands_is_written_once(self):
        k = SpatialKitchen(level_config(load_config(), 'level-2'))
        run(k, 'human', 'fetch lettuce')
        run(k, 'human', 'put b1')
        run(k, 'jeff', 'fetch beef')
        state = self.payload(k, 'v4', with_presses(k))['state']
        shared = state['option_links_shared']
        self.assertEqual(shared['work'], ['Chop F1 at Board 1 (2.2s left)'])
        self.assertIn('put fridge', shared['options'])
        self.assertIn('throw partner', shared['options'])
        self.assertNotIn('put then chop b1', shared['options'])        # a later step uses the freed hands' work up
        self.assertNotIn('put fridge', state['option_links'])
        self.assertEqual(state['option_links']['put b2'], ['Chop F2 at Board 2 (2.2s left)'])
        for key in shared['options']:
            self.assertNotIn('Chop F1 at Board 1 (2.2s left)', state['option_links'].get(key, []))
        self.assertEqual(state['links_version'], links.V4_VERSION)
        self.assertEqual(state['rules']['links'], links.V4_RULE)

    def test_no_option_changes_and_the_kitchen_stays_as_it_was(self):
        k = pan_nearly_done(8.6)
        snapshot = k.snapshot()
        on, off = self.payload(k, 'v4'), self.payload(k, False)
        self.assertEqual(k.snapshot(), snapshot)
        self.assertEqual(on['questions'], off['questions'])
        self.assertEqual(on, self.payload(k, 'v4'))

    def test_with_a_step_under_way_there_is_no_wait_row(self):
        k = pan_nearly_done(8.6)
        k.start('jeff', next(a for a in k.actions('jeff') if a.key == 'go serve'))
        k.advance(.05)
        self.assertIsNotNone(k.chefs['jeff'].job)
        rows, _ = links.table_v4(k, 'jeff', k.actions('jeff'), [a.key for a in k.actions('jeff')])
        self.assertNotIn('wait', rows)

    def test_off_the_table_is_v3(self):
        k = pan_nearly_done(8.6)
        state = self.payload(k, True)['state']
        self.assertEqual(state['links_version'], links.SWITCH_VERSION)
        self.assertNotIn('option_links_shared', state)
        self.assertNotIn('wait', state['option_links'])

    def test_the_switch_is_a_trial_and_off_and_needs_option_links(self):
        loaded = features.load()
        self.assertEqual(loaded['option_links_v4'], {'stage': 'trial', 'on': False, 'player_switch': False,
                                                     'version': links.V4_VERSION})
        on = {name: dict(value) for name, value in loaded.items()}
        on['option_links_v4']['on'] = True
        on['option_links']['on'] = False
        self.assertIs(features.links_option(on), False)
        on['option_links']['on'] = True
        self.assertEqual(features.links_option(on), 'v4')
        on['option_links_partner']['on'] = True
        self.assertEqual(features.links_option(on), 'partner+v4')
        self.assertEqual(links.flags('partner+v4'), {'partner': True, 'v4': True})
        self.assertEqual(links.flags(True), {'partner': False, 'v4': False})


class V4CheckTests(unittest.TestCase):
    """scripts/links_v4_check.py: logged moments re-asked with the v3 and the v4 table, no model called."""

    def test_moments_are_sorted_by_what_changed(self):
        from scripts.links_v4_check import _kind
        plate, chop = 'Plate food from Stove 1', 'Chop F1 at Board 1 (2.2s left)'
        self.assertEqual(_kind({'take plates': [plate]}, {'wait': [plate]}, None), 'pan_soon')
        self.assertEqual(_kind({'chop b2': ['Wash dishes']}, {'wait': ['Wash dishes']}, None), 'wait_other')
        shared = {'options': ['put fridge', 'drop', 'discard'], 'work': [chop]}
        self.assertEqual(_kind({'put fridge': [chop], 'drop': [chop], 'discard': [chop]}, {}, shared), 'shared_only')
        self.assertEqual(_kind({'put fridge': [chop]}, {}, None), 'moved')
        self.assertIsNone(_kind({'put b1': [chop]}, {'put b1': [chop]}, None))

    def test_each_moment_is_asked_in_both_arms_and_the_outcomes_are_counted(self):
        from scripts import links_v4_check as check
        sent = []

        def ask(payload):
            sent.append(payload['state'].get('links_version'))
            return {'choice': 'wait' if payload['state'].get('links_version') == links.V4_VERSION else 'put then take p1',
                    'probabilities': {}, 'model': 'test-model'}
        a = {'state': {'links_version': links.SWITCH_VERSION}, 'questions': {}}
        b = {'state': {'links_version': links.V4_VERSION}, 'questions': {}}
        item = {'payload': a, 'B': b, 'kind': 'pan_soon', 'abandon': ['put then take p1'], 'moved_from': ['put then take plates'],
                'shared': [], 'logged_choice': 'put then take p1'}
        report = check.run([item], ask, repeats=2)
        self.assertEqual(sent, [links.SWITCH_VERSION] * 2 + [links.V4_VERSION] * 2)
        outcomes = report['by_kind']['pan_soon']['stats']['outcomes']
        self.assertEqual((outcomes['put_item_down_for_pan']['A']['k'], outcomes['put_item_down_for_pan']['B']['k']), (2, 0))
        self.assertEqual((outcomes['waited']['A']['k'], outcomes['waited']['B']['k']), (0, 2))
        self.assertEqual(report['by_kind']['pan_soon']['chosen'], {'A': {'put_item_down_for_pan': 2}, 'B': {'wait': 2}})
        self.assertNotIn('payload', json.dumps(report))

    def test_moments_are_asked_in_both_arms_before_the_next_and_failures_are_tried_again(self):
        from scripts import links_v4_check as check
        sent, fails = [], [2]

        def ask(payload):
            if fails[0]:
                fails[0] -= 1
                raise RuntimeError('network')
            sent.append((payload['state']['id'], payload['state']['links_version']))
            return {'choice': 'wait', 'probabilities': {}, 'model': 'test-model'}
        items = [{'payload': {'state': {'id': n, 'links_version': 'v3'}}, 'B': {'state': {'id': n, 'links_version': 'v4'}},
                  'kind': 'control', 'abandon': [], 'moved_from': [], 'shared': [], 'logged_choice': 'wait'} for n in (1, 2)]
        report = check.run(items, check.patient(ask, sleep=lambda s: None), repeats=1)
        self.assertEqual(sent, [(1, 'v3'), (1, 'v4'), (2, 'v3'), (2, 'v4')])
        self.assertEqual(report['by_kind']['control']['errors'], {'A': {}, 'B': {}})


if __name__ == '__main__':
    unittest.main()


class PlayerSwitchTests(unittest.TestCase):
    """步骤提示: option_links carries a player switch; the player's pick applies from the next round and is recorded."""

    def game(self, value=None):
        from test_one_press import Answering as Replying, with_features
        from test_web import FakeJournal
        from web_server import GameSession
        with patch.object(features, 'current', lambda: value or with_features()):
            g = GameSession(level_config(load_config(), 'level-2'), client_factory=lambda c: Replying(c),
                            journal_factory=FakeJournal, kitchen_factory=SpatialKitchen)
        self.addCleanup(g.close)
        return g

    def start_row(self, g):
        return [d for kind, d in g.journal.journal.rows if kind == 'start'][-1]

    def test_on_by_default_with_a_switch_the_player_can_turn_off_between_rounds(self):
        g = self.game()
        self.assertEqual(g.communication_state()['links'], {'on': True, 'available': True, 'editable': True})
        self.assertEqual(g._command('/api/links', {'on': 'no'})[0], 400)
        self.assertEqual(g._command('/api/links', {'on': False})[0], 200)
        self.assertEqual(g.communication_state()['links'], {'on': False, 'available': True, 'editable': True})
        self.assertEqual(g._command('/api/start', {})[0], 200)
        self.assertIs(g.ai.links, False)
        self.assertEqual(self.start_row(g)['features']['option_links'],
                         {'on': False, 'version': links.SWITCH_VERSION, 'source': 'player'})
        self.assertEqual(g.communication_state()['links']['editable'], False)        # fixed while the round runs
        self.assertEqual(g._command('/api/links', {'on': True})[0], 409)

    def test_the_default_needs_no_source_and_no_switch_means_no_change(self):
        from test_one_press import with_features
        g = self.game()
        self.assertEqual(g._command('/api/links', {'on': True})[0], 200)               # the same as the default
        self.assertEqual(g._command('/api/start', {})[0], 200)
        self.assertIs(g.ai.links, True)
        self.assertEqual(self.start_row(g)['features']['option_links'], {'on': True, 'version': links.SWITCH_VERSION})
        g = self.game(with_features(option_links={'player_switch': False}))
        self.assertEqual(g.communication_state()['links']['available'], False)
        self.assertEqual(g._command('/api/links', {'on': False})[0], 400)
