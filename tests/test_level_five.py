"""Level 5 (换位协作): level 4 with the chefs swapped. The same map, orders and order seed; spawn seed 1 puts the human on
the supplies, stoves and serving side and Jeff on the boards side. What Jeff is told is worked out from the engine's
reach, so the same switches serve both levels; step_check names the boards' side from Jeff's view."""
import json
import unittest
import uuid
from unittest.mock import patch

import config_contract as cc
import features
import levels
import reference_policy
import research_replay
import step_check
from jev import compose_payload
from kitchen import Food, load_config
from level_calibration import drive
from research_record import validate_record
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
import test_research_save_paths as paths

SUPPLY_SIDE = ('fridge', 'lettuce', 'tomato', 'bread', 'p1', 'p2', 'serve', 'bin', 'extinguisher')
BOARD_SIDE = ('b1', 'b2', 'sink', 'returns', 'bin2', 'dryer')


def kitchen(level):
    return SpatialKitchen(levels.level_config(load_config(), f'level-{level}'))


def do(k, who, key):
    k.start(who, next(a for a in k.actions(who) if a.key == key))
    while k.chefs[who].job is not None:
        k.advance(0.05)


def request(k, **switches):
    options = {**features.compose_options(features.current()), 'reach': True, **switches}
    return compose_payload(SpatialJevClient(k.c, key='test-no-credential'), k, k.snapshot(), k.actions('jeff'), [], None,
                           **options)


class LevelTests(unittest.TestCase):
    def test_level_five_is_level_four_with_the_spawn_sides_swapped(self):
        four, five = cc.Registry().level('level-4'), cc.Registry().level('level-5')
        self.assertEqual(five['menu_order'], 5)
        self.assertIs(five['requires_pair'], True)
        for field in ('map_ref', 'order_policy_ref', 'recipe_catalog_ref', 'ruleset_ref', 'spawns', 'initial_inventory',
                      'round_limit_game_ms', 'clock'):
            self.assertEqual(five[field], four[field], field)
        self.assertEqual(five['seeds'], {**four['seeds'], 'spawn': 1})
        self.assertEqual(levels.available_levels()[-1]['id'], 'level-5')

    def test_the_human_works_the_supplies_side_and_jeff_the_boards_side(self):
        for level, mine, theirs in ((4, SUPPLY_SIDE, BOARD_SIDE), (5, BOARD_SIDE, SUPPLY_SIDE)):
            k = kitchen(level)
            for station in mine:
                self.assertTrue(k.reaches('jeff', station) and not k.reaches('human', station), (level, station))
            for station in theirs:
                self.assertTrue(k.reaches('human', station) and not k.reaches('jeff', station), (level, station))
        self.assertEqual(step_check.chopper(kitchen(4)), 'human')
        self.assertEqual(step_check.chopper(kitchen(5)), 'jeff')

    def test_the_chef_on_the_boards_side_discards_at_its_own_bin(self):
        # bin2, the map's second bin, is the only one on the boards side: the player there on level 4 and Jeff there on
        # level 5 discard held food and empty a held pan at it (once neither had any discard listed: the second bin's
        # was built only when the first bin's was in the chef's reach).
        for level, who in ((4, 'human'), (5, 'jeff')):
            for held, kind in ((lambda: Food('F1', 'raw', ingredient='beef'), 'discard'),
                               (lambda: Food('P9', 'pot', contents=Food('F2', 'burnt', ingredient='beef', heated=99.)),
                                'empty_pot')):
                k = kitchen(level)
                k.chefs[who].hand = held()
                bins = [(a.key, a.kind) for a in k.actions(who) if a.kind in ('discard', 'empty_pot')]
                self.assertEqual(bins, [('discard bin2', kind)], (level, who))
                money = k.money
                do(k, who, 'discard bin2')
                hand = k.chefs[who].hand
                self.assertEqual(hand.contents if kind == 'empty_pot' else hand, None, (level, who))
                self.assertEqual(k.money - money, k.rules.penalty['discard'])

    def test_one_chef_alone_serves_nothing_on_the_configured_round(self):
        for who in ('human', 'jeff'):
            k = SpatialKitchen(cc.load_level('level-5'))
            drive(k, ((who, 'solo'),), lambda k, w, r: reference_policy.choose_solo(k, w), {'human': 10, 'jeff': 10})
            self.assertEqual(k.served, 0, who)

    def test_it_is_shown_in_the_release_and_a_switch_can_hide_it(self):
        self.assertEqual(json.loads(levels.SWITCHES.read_text(encoding='utf-8'))['level-5'], {'on': True})
        with patch.object(levels, 'switches', lambda: {'level-4': False, 'level-5': False}):
            self.assertNotIn('level-5', [l['id'] for l in levels.shown_levels()])
        with patch.object(levels, 'switches', lambda: {'level-4': True, 'level-5': True}):
            self.assertEqual([l['id'] for l in levels.shown_levels()][-1], 'level-5')


class RequestTests(unittest.TestCase):
    def test_reach_and_split_floor_name_the_sides_from_jeffs_view(self):
        payload = request(kitchen(5), split=True)
        rules = payload['state']['rules']
        self.assertIn('Stations only you can reach: b1, b2, sink, returns, bin2, counter14, dryer. Stations only the human can '
                      'reach: fridge, lettuce, tomato, bread, counter1, p1, p2, serve, bin, extinguisher.', rules['reach'])
        self.assertIn("the supplies (fridge, lettuce, tomato, bread), cooking (p1, p2) and serving (serve) are only on the "
                      "human's side; chopping (b1, b2) is only on your side", rules['split_floor'])

    def test_step_check_counts_what_is_within_jeffs_own_reach_to_chop(self):
        k = kitchen(5)
        text = request(k, steps=True)['state']['step_check']
        self.assertIn('Within your reach to chop now: nothing.', text)
        self.assertIn('the supplies are on the other chef\'s side.', text)
        self.assertIn('the boards are on your side.', text)
        self.assertIn('the stoves are on the other chef\'s side.', text)
        self.assertIn('Serving: at Serve, on the other chef\'s side.', text)
        do(k, 'human', 'fetch beef')
        shared = next(a for a in k.actions('human') if a.kind == 'put_counter' and k.reaches('jeff', a.target))
        do(k, 'human', shared.key)
        self.assertIn('Within your reach to chop now: beef 1.', request(k, steps=True)['state']['step_check'])

    def test_level_four_is_asked_as_before(self):
        text = request(kitchen(4), steps=True)['state']['step_check']
        self.assertIn("Within the other chef's reach to chop now: nothing.", text)
        self.assertIn('the boards are on the other chef\'s side.', text)


class LevelFiveReplayTests(paths.SavePathTests):
    def test_a_level_five_round_with_the_check_replays_exactly(self):
        with self.game.lock:
            self.game.features = {**self.game.features,
                                  'step_check': {**self.game.features['step_check'], 'on': True},
                                  'reach_note': {**self.game.features['reach_note'], 'on': True}}
        with patch.object(levels, 'switches', lambda: {'level-4': True, 'level-5': True}):
            status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 5}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        self.assertTrue(all('Within your reach to chop now' in row['rebuilt']['state']['step_check'] for row in rows))


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(LevelFiveReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
