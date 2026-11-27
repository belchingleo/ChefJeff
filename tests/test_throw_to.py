"""throw_to (trial, off): on a split floor, walk to a spot one of the player's aimed throws lands on an out-of-reach
work station from, then throw (one_press.py, SpatialKitchen.throw_spots / throw_spot_walk)."""
import unittest
from unittest.mock import patch

import features
import one_press
from jev import DecisionLoop, NO_MEMORY, compose_payload
from kitchen import Action, Food, load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from test_one_press import Answering, BOTH, Inline, start
from whitebox_server import SpatialJevClient

ON = {**BOTH, one_press.THROW_TO: True}


def level4_with_beef():
    """Level 4: Jeff fetched beef on his side; the boards are on the other chef's side."""
    k = SpatialKitchen(level_config(load_config(), 'level-4'))
    start(k, 'jeff', 'fetch beef')
    return k


class SpotTests(unittest.TestCase):
    def test_the_spots_are_where_an_aimed_throw_lands_on_a_board_he_cannot_reach(self):
        k = level4_with_beef()
        self.assertEqual(k.throw_spots('jeff'), {'b1': [('floor_2_3', 'down')], 'b2': [('floor_3_3', 'down')]})
        self.assertFalse(k.reaches('jeff', 'b1'))

    def test_no_spots_off_a_split_floor_with_empty_hands_or_for_chopped_food(self):
        k = SpatialKitchen(level_config(load_config(), 'level-2'))
        start(k, 'jeff', 'fetch beef')
        self.assertEqual(k.throw_spots('jeff'), {})                               # one floor: he walks there himself
        k = SpatialKitchen(level_config(load_config(), 'level-4'))
        self.assertEqual(k.throw_spots('jeff'), {})                               # empty hands
        k = level4_with_beef()
        k.chefs['jeff'].hand.stage = 'chopped'
        self.assertNotIn('b1', k.throw_spots('jeff'))                             # nothing left to chop on a board

    def test_the_engine_accepts_the_walk_to_a_spot_and_no_other_floor_walk(self):
        k = level4_with_beef()
        walk = Action('go floor_2_3', '走到地面(2,3)', 'go', 'floor_2_3')
        self.assertNotIn('go floor_2_3', [a.key for a in k.actions('jeff')])     # not listed for Jeff
        self.assertEqual(k.start('jeff', Action('go floor_5_2', '走到地面(5,2)', 'go', 'floor_5_2'))[0], False)
        self.assertEqual(k.start('jeff', walk)[0], True)
        while k.chefs['jeff'].job:
            k.advance(.05)
        self.assertEqual(k.positions['jeff'], (2.0, 3.0))
        self.assertEqual([a.key for a in k.actions('jeff') if a.kind == 'throw' and a.target == 'b1'], ['throw down'])


class OptionTests(unittest.TestCase):
    def test_options_only_with_the_flag(self):
        k = level4_with_beef()
        acts = k.actions('jeff')
        self.assertFalse(any(o.kind == one_press.THROW_TO for o in one_press.options(k, 'jeff', acts, BOTH)))
        options = [o for o in one_press.options(k, 'jeff', acts, ON) if o.kind == one_press.THROW_TO]
        self.assertEqual([(o.key, o.target, o.expected) for o in options],
                         [('throw to b1', 'b1', ('F1', 'floor_2_3', 'down')), ('throw to b2', 'b2', ('F1', 'floor_3_3', 'down'))])
        self.assertEqual(options[0].label, '走到地面(2,3)，向下方抛出手中物品（落到案板 1）')

    def test_the_request_says_where_he_walks_and_what_the_other_chef_could_do_and_asks_no_put_where(self):
        k = level4_with_beef()
        acts = k.actions('jeff')
        p = compose_payload(SpatialJevClient(k.c, key='x'), k, k.snapshot(), acts, [], None, NO_MEMORY, ON,
                            reach=True, names=True, links='partner', split=True, walk=True, clear=True, english=True,
                            plate=True, parts={'place': True, 'timeline': True, 'links_on': True, 'rules': True, 'view': True},
                            go=True)
        criteria = p['questions']['next_action']['criteria']
        self.assertEqual(criteria['throw to b1'], 'Walk to floor (2,3) and throw the held beef (as fetched) down onto Board 1 '
                         '(0.3 s walk). If nothing else changes first, then the other chef could: Chop beef (as fetched) F1 '
                         'at Board 1 (2.2s left)')
        self.assertFalse(any(key.startswith('throw to') for key in p['questions'][one_press.PUT_WHERE]['criteria']))

    def test_off_the_request_is_as_before(self):
        k = level4_with_beef()
        acts = k.actions('jeff')
        args = (SpatialJevClient(k.c, key='x'), k, k.snapshot(), acts, [], None, NO_MEMORY, BOTH)
        self.assertEqual(compose_payload(*args), compose_payload(*args[:-1], dict(BOTH)))
        self.assertFalse(any(key.startswith('throw to') for key in compose_payload(*args)['questions']['next_action']['criteria']))

    def test_the_switch_rides_on_the_one_press_flags_and_the_start_row(self):
        import json
        from pathlib import Path
        raw = json.loads((Path(features.__file__).parent / 'features.json').read_text())
        # Released with the 8775 play set as the defaults (0.11.0, 2026-11-27).
        self.assertEqual(raw['throw_to'], {'stage': 'release', 'on': True, 'version': 'throw-to-v1'})
        self.assertEqual(features.one_press_flags(raw), ON)
        off = features.with_override(raw, {'throw_to': {'on': False}})
        self.assertNotIn(one_press.THROW_TO, features.one_press_flags(off))
        self.assertEqual(one_press.condition(ON)['one_press'][one_press.THROW_TO], True)
        self.assertNotIn(one_press.THROW_TO, one_press.condition(BOTH)['one_press'])


class ChainTests(unittest.TestCase):
    def test_he_walks_to_the_spot_and_throws_onto_the_board(self):
        k = level4_with_beef()
        records = []
        ai = DecisionLoop(k, Answering(k.c, [{'choice': 'throw to b1'}]), lambda kind, data: records.append((kind, data)),
                          lambda _: None)
        ai.one_press = dict(ON)
        ai.player_messages = []
        clock = [1000.]
        for _ in range(60):
            for _ in range(4):
                k.advance(.05)
            ai.last_revision = -1
            clock[0] += 3.
            with patch('jev.time.monotonic', lambda: clock[0]), patch('jev.threading.Thread', Inline):
                ai.poll()
            if k.stations['b1'].food is not None:
                break
        done = [e.get('action') for e in k.events if e.get('actor') == 'jeff' and e.get('kind') == 'action_done']
        self.assertEqual(done[-2:], ['go floor_2_3', 'throw down'])
        self.assertEqual((k.stations['b1'].food.id, k.chefs['jeff'].hand), ('F1', None))
        self.assertEqual([(d['choice'], d['reason']) for kind, d in records if kind == 'one_press_end'], [('throw to b1', 'finished')])
        self.assertEqual(next(d for kind, d in records if kind == 'ai_response')['one_press'],
                         {'first': 'go floor_2_3', 'fallback': False})          # walked first, nothing put down


if __name__ == '__main__':
    unittest.main()
