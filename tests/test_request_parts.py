"""request_parts.py: the parts of the restructured request, each a server-only trial switch, off by default.

Each part changes only its own part of the request; with every part off nothing changes; the decision loop (links
thread included) and research replay build the same requests. No model is called.
"""
from copy import deepcopy
import json
import unittest
import uuid
from unittest.mock import patch

import features
import links
import request_parts
import research_replay
from jev import DecisionLoop, compose_payload
from kitchen import load_config
from levels import level_config
from loop_helpers import Inline, Scripted
from research_record import validate_record
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
import test_research_save_paths as paths

PLAY = {'reach': True, 'split': True, 'burn': True, 'serve_note': True, 'steps': True, 'walk': True,
        'links': 'partner'}
ALL = {'place': True, 'timeline': True, 'links_on': True, 'rules': True, 'view': True}


def level(name):
    return SpatialKitchen(level_config(load_config(), name))


def do(k, key, who='jeff'):
    k.start(who, next(a for a in k.actions(who) if a.key == key))
    while k.chefs[who].job is not None:
        k.advance(0.05)


def request(k, parts=None, decisions=(), **switches):
    options = {**features.compose_options(features.current()), **PLAY, **switches}
    return compose_payload(SpatialJevClient(k.c, key='test-no-credential'), k, k.snapshot(), k.actions('jeff'),
                           list(deepcopy(decisions)), None, parts=parts, **options)


def without(payload, *keys):
    return {k: v for k, v in payload['state'].items() if k not in keys}


class SwitchTests(unittest.TestCase):
    def test_the_parts_are_server_trials_off_by_default(self):
        current = features.current()
        for name, (_, version) in request_parts.SWITCHES.items():
            self.assertEqual(current[name], {'stage': 'trial', 'on': False, 'version': version})
        self.assertNotIn('parts', features.compose_options(current))
        self.assertIsNone(request_parts.parts(current))
        on = {**current, 'timeline': {**current['timeline'], 'on': True}, 'kitchen_view': {**current['kitchen_view'], 'on': True}}
        self.assertEqual(features.compose_options(on)['parts'], {'timeline': True, 'view': True})

    def test_with_every_part_off_the_request_is_unchanged(self):
        k = level('level-4')
        do(k, 'fetch tomato')
        self.assertEqual(json.dumps(request(k)), json.dumps(request(k, parts={})))
        self.assertEqual(json.dumps(request(k)), json.dumps(request(k, parts={name: False for name in ALL})))


class PartTests(unittest.TestCase):
    def setUp(self):
        self.k = level('level-4')
        do(self.k, 'fetch tomato')
        do(self.k, next(a.key for a in self.k.actions('human') if a.kind == 'go'), 'human')
        self.decisions = [{'t': 1.0, 'choice': 'fetch tomato', 'accepted': True, 'result': 'Started', 'sprint_applied': False},
                          {'t': 1.2, 'choice': 'put counter5', 'accepted': False, 'result': 'Not allowed now',
                           'sprint_applied': False}]
        self.base = request(self.k, decisions=self.decisions)

    def part(self, **on):
        return request(self.k, parts=on, decisions=self.decisions)

    def test_place_names_names_the_stations_in_the_reach_rules_and_decisions(self):
        out = self.part(place=True)
        rules = out['state']['rules']
        self.assertIn('Stations only you can reach: Fridge (fridge), Lettuce supply (lettuce)', rules['reach'])
        self.assertIn('Board 1 (b1), Board 2 (b2)', rules['reach'])
        self.assertNotIn('((', rules['reach'])
        self.assertIn('chopping (Board 1, Board 2)', rules['split_floor'])
        self.assertIn('(Counters 2–13)', rules['split_floor'])
        self.assertEqual([d.get('place') for d in out['state']['recent_decisions']], ['Tomato supply', 'Counter 5'])
        self.assertEqual(out['state'].pop('place_names_version'), request_parts.PLACE_NAMES_VERSION)
        # Nothing else: the two rules and the decisions' place aside, the request is the same.
        out['state']['rules']['reach'], out['state']['rules']['split_floor'] = (self.base['state']['rules']['reach'],
                                                                               self.base['state']['rules']['split_floor'])
        for d in out['state']['recent_decisions']:
            d.pop('place', None)
        self.assertEqual(json.dumps(out), json.dumps(self.base))

    def test_the_timeline_keeps_jeffs_own_steps_and_his_refused_choices_in_time_order(self):
        out = self.part(timeline=True)
        state = out['state']
        self.assertNotIn('recent_events', state)
        self.assertNotIn('recent_decisions', state)
        self.assertEqual(state['rules']['continuity'], request_parts.TIMELINE_RULE)
        lines = state['timeline']
        self.assertTrue(any(line.endswith('you: Fetch tomato (as fetched) (you chose fetch tomato)') for line in lines), lines)
        self.assertTrue(any('you chose put counter5: not done (Not allowed now)' in line for line in lines), lines)
        self.assertFalse(any('other chef' in line or 'human' in line for line in lines), lines)   # their steps left out
        times = [float(line.split(' s ', 1)[0]) for line in lines]
        self.assertEqual(times, sorted(times))
        self.assertEqual(state.pop('timeline_version'), request_parts.TIMELINE_VERSION)
        self.assertEqual(without(out, 'timeline', 'rules'), without(self.base, 'recent_events', 'recent_decisions', 'rules'))

    def test_the_timeline_says_where_jeffs_throw_came_down_and_what_went_wrong(self):
        k = level('level-4')
        do(k, 'fetch tomato')
        do(k, 'throw down')
        decisions = [{'t': k.time, 'choice': 'throw down', 'accepted': True, 'result': 'Throw started', 'sprint_applied': False}]
        k.advance(2.0)
        k.orders[0]['deadline'] = k.time + 0.1            # an order runs out: an event of the kitchen, not of a chef
        k.advance(0.5)
        lines = request(k, parts={'timeline': True}, decisions=decisions)['state']['timeline']
        self.assertTrue(any(line.endswith('(you chose throw down)') and 'you threw' in line for line in lines), lines)
        self.assertTrue(any('landed' in line or 'caught' in line for line in lines), lines)
        self.assertTrue(any('O1' in line for line in lines), lines)
        self.assertFalse(any(line.split(' s ', 1)[1].startswith('you: Throw') for line in lines), lines)

    def test_with_place_names_the_timeline_names_the_stations_of_each_choice(self):
        lines = self.part(place=True, timeline=True)['state']['timeline']
        self.assertTrue(any(line.endswith('(you chose fetch tomato at Tomato supply)') for line in lines), lines)
        self.assertTrue(any('you chose put counter5 at Counter 5: not done (Not allowed now)' in line for line in lines), lines)
        alone = self.part(timeline=True)['state']['timeline']
        self.assertTrue(any(line.endswith('(you chose fetch tomato)') for line in alone), alone)

    def test_no_history_sends_neither_list_nor_their_rule(self):
        out = self.part(no_history=True, timeline=True)
        state = out['state']
        for key in ('recent_events', 'recent_decisions', 'timeline'):
            self.assertNotIn(key, state)
        self.assertNotIn('continuity', state['rules'])
        self.assertEqual(state.pop('no_history_version'), request_parts.NO_HISTORY_VERSION)
        rules = dict(self.base['state']['rules'])
        rules.pop('continuity')
        self.assertEqual(state['rules'], rules)

    def test_links_on_options_puts_each_options_lines_after_it(self):
        table = self.base['state']['option_links']
        self.assertTrue(table)
        out = self.part(links_on=True)
        state, criteria = out['state'], out['questions']['next_action']['criteria']
        self.assertNotIn('option_links', state)
        self.assertEqual(state['rules']['links'], links.RULE + request_parts.PARTNER_OPTION_RULE)
        before = self.base['questions']['next_action']['criteria']
        for key, label in criteria.items():
            if key not in table:
                self.assertEqual(label, before[key])
                continue
            self.assertTrue(label.startswith(links._end(before[key])), key)
            for line in table[key]:
                self.assertIn(line, label)
        partner = next(key for key, lines in table.items() if all(line.startswith(links.THEN) for line in lines))
        self.assertIn('. If nothing else changes first, then the other chef could: ', criteria[partner])
        self.assertEqual(state.pop('links_on_options_version'), request_parts.LINKS_ON_OPTIONS_VERSION)
        self.assertEqual(without(out, 'rules'), without(self.base, 'option_links', 'rules'))

    def test_rules_by_action_leaves_out_only_rules_about_actions_not_listed(self):
        out = self.part(rules=True)
        rules, before = out['state']['rules'], self.base['state']['rules']
        self.assertLess(set(rules), set(before))
        for name, text in rules.items():
            self.assertEqual(text, before[name])
        for name in set(before) - set(rules):
            self.assertIn(name, request_parts.RULE_KINDS)
        for name in ('role', 'objective', 'flow', 'score', 'visibility', 'movement', 'sprint', 'reach', 'split_floor', 'links',
                     'vessels'):
            self.assertIn(name, rules)
        self.assertIn('throw', rules)            # Jeff holds the tomato: the throws are listed
        self.assertNotIn('pot_swap', rules)      # no pan in hand
        empty = level('level-4')
        self.assertNotIn('throw', request(empty, parts={'rules': True})['state']['rules'])   # nothing to throw
        self.assertEqual(out['state'].pop('rules_by_action_version'), request_parts.RULES_BY_ACTION_VERSION)
        self.assertEqual(without(out, 'rules'), without(self.base, 'rules'))

    def test_held_raw_beef_says_it_is_not_chopped_and_which_vessel_cooks_it(self):
        # v2: with rules_by_action and kitchen_view v1 together, nothing in the request said raw beef needs chopping
        # before a pan takes it, and Perplexity and Jev walked it between the stoves (user play, 2026-11-20).
        k = level('level-4')
        do(k, 'fetch beef')
        with patch.object(request_parts, 'listed_kinds', lambda payload, kitchen: set()):
            out = request(k, parts={'rules': True, 'view': True})
        held = out['state']['kitchen']['chefs']['you']['holding']
        self.assertEqual(held, f'beef (as fetched) {k.chefs["jeff"].hand.id} (not chopped yet (2.2 s of chopping); '
                               'a frying pan cooks it only once it is chopped)')
        self.assertIn('vessels', out['state']['rules'])
        do(k, 'throw down')
        k.advance(2.0)
        floor = request(k, parts={'view': True})['state']['kitchen'].get('floor') or {}
        self.assertTrue(any('only once it is chopped' in text for text in floor.values()) or k.chefs['human'].hand, floor)

    def test_the_timeline_rule_keeps_the_continuity_checks(self):
        import harness
        checks = harness.CONTINUITY_RULE.split('Use them to ', 1)[1]
        self.assertIn(checks.split('check for ', 1)[1], request_parts.TIMELINE_RULE)

    def test_the_fire_rule_stays_while_food_is_on_a_stove(self):
        # The extinguisher is listed nearly always; with no fire option listed at all, food on a stove keeps the rule.
        k = level('level-1')
        with patch.object(request_parts, 'listed_kinds', lambda payload, kitchen: set()):
            self.assertNotIn('fire', request(k, parts={'rules': True})['state']['rules'])
            for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
                do(k, key)
            self.assertIn('fire', request(k, parts={'rules': True})['state']['rules'])

    def test_the_kitchen_view_writes_out_the_kitchen_without_the_map(self):
        out = self.part(view=True)
        view = out['state']['kitchen']
        self.assertEqual(set(view), {'clock', 'money', 'dishes', 'vessels', 'orders_waiting', 'orders_served', 'chefs',
                                     'stations', 'plates'} | ({'floor'} if self.k.ground else set()))
        self.assertEqual(view['vessels'], {'frying pan': 'cooks beef (chopped)'})
        self.assertEqual(view['chefs']['you']['holding'],
                         f'tomato (as fetched) {self.k.chefs["jeff"].hand.id} (not chopped yet (2.2 s of chopping))')
        self.assertEqual(set(view['stations']), set(request_parts.SIDES))
        named, empty = set(), set()
        for side in view['stations'].values():
            for key, text in side.items():
                if key == 'empty counters':
                    for part in text.split(', '):
                        first, _, last = part.partition('–')
                        start, end = int(first[7:]), int((last or first)[7:])
                        empty |= {f'counter{n}' for n in range(start, end + 1)}
                else:
                    named.add(key.rsplit('(', 1)[1].rstrip(')'))
        self.assertEqual(named | empty, set(self.k.stations))     # every station once: by name and id, or as empty
        self.assertFalse(named & empty)
        for sid in empty:
            self.assertIsNone(self.k.stations[sid].food)
        self.assertIn('Stove 1 (p1)', view['stations']['your side'])
        self.assertIn('Board 1 (b1)', view['stations']["other chef's side"])
        self.assertLess(len(json.dumps(view)), len(json.dumps(self.base['state']['kitchen'])) / 4)
        for word in ('walls', 'collision', 'config_hash', 'order_seed', 'menu'):
            self.assertNotIn(word, json.dumps(view))
        self.assertEqual(out['state'].pop('kitchen_view_version'), request_parts.KITCHEN_VIEW_VERSION)
        self.assertEqual(without(out, 'kitchen'), without(self.base, 'kitchen'))

    def test_a_stove_says_when_its_food_is_cooked_and_burns(self):
        k = level('level-1')
        for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
            do(k, key)
        k.advance(2.0)
        stove = k.snapshot()['stations']['p1']
        text = request(k, parts={'view': True})['state']['kitchen']['stations']['Stove 1 (p1)']
        self.assertEqual(text, f"frying pan P1 with beef (cooking) {stove['food']['id']}: cooked in {stove['ready_in']:.1f} s")
        while k.stations['p1'].food.stage != 'ready':      # v3: the burn and the fire only once it is cooked
            k.advance(0.1)
        k.advance(1.0)
        stove = k.snapshot()['stations']['p1']
        text = request(k, parts={'view': True})['state']['kitchen']['stations']['Stove 1 (p1)']
        self.assertTrue(text.startswith('frying pan P1 with beef (cooked) '), text)
        self.assertIn(f"burns in {stove['burn_in']:.1f} s", text)
        self.assertNotIn('cooked in', text)

    def test_all_parts_together(self):
        out = request(self.k, parts=ALL, decisions=self.decisions)
        state = out['state']
        for key in ('recent_events', 'recent_decisions', 'option_links'):
            self.assertNotIn(key, state)
        for _, version in request_parts.SWITCHES.values():
            if version != request_parts.NO_HISTORY_VERSION:
                self.assertIn(version, state.values())
        self.assertLess(len(json.dumps(out)), len(json.dumps(self.base)) * 0.6)


class LoopTests(unittest.TestCase):
    def test_the_loop_finishes_the_request_after_the_links_thread_as_compose_does(self):
        for mode in (True, False):
            k = level('level-4')
            do(k, 'fetch tomato')
            rows = []
            client = Scripted(k.c)
            loop = DecisionLoop(k, client, lambda kind, data: rows.append((kind, data)), lambda *_: None)
            loop.links, loop.parts, loop.reach, loop.split = (mode and 'partner'), dict(ALL), True, True
            loop.names = loop.clear = loop.english = loop.plate = True
            with patch('jev.threading.Thread', Inline):
                loop.poll()
                loop.poll()
            logged = next(d for kind, d in rows if kind == 'ai_request')['payload']
            self.assertIn('timeline', logged['state'])
            self.assertIn('kitchen_view_version', logged['state'])
            self.assertEqual(('links_on_options_version' in logged['state']), bool(mode))
            self.assertNotIn('option_links', logged['state'])


class PartsReplayTests(paths.SavePathTests):
    def test_a_round_with_every_part_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features, **{name: {**self.game.features[name], 'on': True}
                                                           for name in ('place_names', 'timeline', 'links_on_options',
                                                                        'rules_by_action', 'kitchen_view')}}
        import levels
        with patch.object(levels, 'switches', lambda: {'level-4': True}):
            status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 4}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['timeline'], {'on': True, 'version': request_parts.TIMELINE_VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        self.assertTrue(all('timeline' in row['rebuilt']['state'] for row in rows))
        record['conditions']['features']['kitchen_view']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(record)}, {'diverged'})


for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(PartsReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
