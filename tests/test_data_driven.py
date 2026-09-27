"""Changing data changes behaviour; the engine has no per-level branches.

Covers the collaboration supplement's regression list for shared work:
one chef, two chefs throughout, mid-way join, mid-way leave, lock/progress
consistency and recipe base-duration overrides.
"""
import re
import unittest
from pathlib import Path

import config_contract as cc
from kitchen import Food
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient

ROOT = Path(cc.__file__).resolve().parent
ENGINE_FILES = ('kitchen.py', 'spatial_kitchen.py', 'rules.py', 'jev.py', 'whitebox_server.py', 'web_server.py',
                'player_api.py', 'cocos_server.py', 'hosted_server.py', 'levels.py')


def level1(chop_ms=None, multiplier=None, price=None):
    bundle = cc.level_bundle('level-1', embed=True)
    bundle['level']['seeds'] = {'orders': 0, 'spawn': 0}
    bundle['level']['round_limit_game_ms'] = 500000
    bundle['order_policy']['patience_default_game_ms'] = 450000
    if chop_ms is not None:
        for t in bundle['recipe_catalog']['transforms']:
            if t['operation'] == 'chop':
                t['work_game_ms'] = chop_ms
    if multiplier is not None:
        bundle['equipment_catalog']['types']['board']['shared_work']['chop']['rate_multiplier'] = multiplier
    if price is not None:
        bundle['recipe_catalog']['recipes']['steak']['price'] = price
    return SpatialKitchen(cc.freeze_bundle(bundle))


class NoLevelBranchTests(unittest.TestCase):
    def test_runtime_code_has_no_level_number_branches(self):
        pattern = re.compile(r"""(get\(['"]level['"]\)|\[['"]level['"]\]|\blevel\b)\s*(==|!=|in\s*\(|not in)""")
        for name in ENGINE_FILES:
            with self.subTest(file=name):
                self.assertEqual(pattern.findall((ROOT / name).read_text()), [])


class SharedWorkDataTests(unittest.TestCase):
    """Level-1 board b1 has a second, perpendicular operation side."""

    def pair(self, k):
        k.stations['b1'].food = Food('shared-food')
        k.positions.update(human=(4, 2.49), jeff=(3.3, 3.3))

    def start(self, k, *chefs):
        for who in chefs:
            ok, message = k.command(who, 'chop b1')
            self.assertTrue(ok, message)
        k.advance(.01)

    def test_single_chef_uses_recipe_base_duration(self):
        for chop_ms in (6000, 10000):
            with self.subTest(chop_ms=chop_ms):
                k = level1(chop_ms=chop_ms);self.pair(k);self.start(k, 'human')
                k.advance(chop_ms / 1000 - .06)
                self.assertEqual(k.stations['b1'].food.stage, 'raw')
                k.advance(.1)
                self.assertEqual(k.stations['b1'].food.stage, 'chopped')
                k.assert_invariants()

    def test_supplement_baseline_ten_seconds_alone_five_together_is_pure_data(self):
        k = level1(chop_ms=10000);self.pair(k);self.start(k, 'human', 'jeff')
        k.advance(5 - .06)
        self.assertEqual(k.stations['b1'].food.stage, 'raw')
        k.advance(.1)
        self.assertEqual(k.stations['b1'].food.stage, 'chopped')
        self.assertTrue(all(c.job is None for c in k.chefs.values()))
        self.assertIsNone(k.stations['b1'].lock)
        k.assert_invariants()

    def test_non_linear_multiplier_join_and_leave(self):
        k = level1(chop_ms=6000, multiplier={'1': 1.0, '2': 1.5});self.pair(k)
        self.start(k, 'human')
        before = k.stations['b1'].food.chopped;k.advance(1)
        self.assertAlmostEqual(k.stations['b1'].food.chopped - before, 1)
        self.start(k, 'jeff')  # joins mid-way: the remaining work speeds up at once
        before = k.stations['b1'].food.chopped;k.advance(1)
        self.assertAlmostEqual(k.stations['b1'].food.chopped - before, 1.5)
        k.stop('human')  # leaves: single rate again, progress kept, lock handed over
        self.assertEqual(k.stations['b1'].lock, 'jeff')
        before = k.stations['b1'].food.chopped;k.advance(1)
        self.assertAlmostEqual(k.stations['b1'].food.chopped - before, 1)
        k.assert_invariants()

    def test_shared_rule_must_define_every_allowed_worker_count(self):
        bundle = cc.level_bundle('level-1', embed=True)
        bundle['equipment_catalog']['types']['board']['shared_work']['chop']['rate_multiplier'] = {'1': 1.0}
        _, diagnostics = cc.resolve_config(bundle)
        self.assertIn('SHARED_WORK_RATE_MISSING', {d['code'] for d in diagnostics})


class RecipeDataTests(unittest.TestCase):
    def test_price_change_reaches_engine_and_agent_rules(self):
        k = level1(price=45)
        payload = SpatialJevClient(k.c, key='t').payload(k.snapshot(), k.actions('jeff'))
        self.assertIn('steak 45 yuan', payload['state']['rules']['score'])
        k.advance(1.)
        k.chefs['human'].hand = Food('X', 'ready', plate_id='D1', ingredient='dish', components=('beef',))
        k.stations['plates'].food = None
        self.assertTrue(k.command('human', 'serve')[0])
        k.advance(20.)
        self.assertEqual(k.money, 45)


if __name__ == '__main__':
    unittest.main()
