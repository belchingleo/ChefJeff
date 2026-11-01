"""A player's level runs on the release's rules and gets its pacing and target from the scripted chefs."""
import unittest

import json
from pathlib import Path

import config_contract as cc
import level_calibration as lc
from levels import PLAYER_LEVEL, level_number
import schema_check
from spatial_kitchen import SpatialKitchen


def restock(sources, menu, vessels=None):
    """Level 3's layout as a player level: other ingredients in its crates, only the menu's dishes."""
    bundle = cc.level_bundle('level-3', embed=True)
    for e in bundle['map']['equipment']:
        if e.get('id') in sources:
            e['params'] = {'item': sources[e['id']]}
    for e in bundle['level']['initial_inventory']:
        if e['id'] in (vessels or {}):
            e['object'] = vessels[e['id']]
    bundle['order_policy']['menu'] = [{'recipe_ref': dish, 'weight': 1} for dish in menu]
    bundle['recipe_catalog']['recipes'] = {dish: bundle['recipe_catalog']['recipes'][dish] for dish in menu}
    return bundle


class PacingTests(unittest.TestCase):
    def test_rule_reproduces_the_authored_pacing(self):
        for level in ('level-1', 'level-3'):
            bundle = cc.level_bundle(level, embed=True)
            with self.subTest(level=level):
                self.assertEqual(lc.pacing(bundle), {'interval_game_ms': bundle['order_policy']['interval_game_ms'],
                                                     'patience_by_recipe': bundle['order_policy']['patience_by_recipe']})

    def test_patience_stays_between_one_minute_and_five_open_tickets(self):
        salad = restock({'bread': 'cucumber'}, ['salad'])
        noodles = restock({'lettuce': 'noodles', 'tomato': 'scallion', 'bread': 'chicken'}, ['beef_noodles'], {'P2': 'pot'})
        self.assertEqual(lc.pacing(salad)['patience_by_recipe'], {'salad': 60000})
        self.assertEqual(lc.pacing(noodles)['patience_by_recipe'], {'beef_noodles': 135000})


class NormalizeTests(unittest.TestCase):
    def test_rules_ingredients_and_cooking_steps_come_from_the_release(self):
        bundle = restock({}, ['steak'])
        bundle['ruleset']['movement']['walk_cells_per_game_s'] = 9
        for t in bundle['recipe_catalog']['transforms']:
            t['work_game_ms'] = 1
        bundle['level']['menu_order'] = 1
        level, problems = lc.normalize(bundle)
        release = cc.level_bundle('level-1', embed=True)
        self.assertEqual(problems, [])
        self.assertEqual(level['ruleset'], release['ruleset'])
        self.assertEqual(level['recipe_catalog']['transforms'], release['recipe_catalog']['transforms'])
        self.assertEqual(level['recipe_catalog']['recipes'], {'dish_1': {
            'name': 'cooked beef', 'container': 'plate', 'price': 50,
            'components': [{'item': 'beef', 'state': 'ready', 'label': 'cooked beef'}]}})
        self.assertEqual(level['order_policy']['menu'], [{'recipe_ref': 'dish_1', 'weight': 1}])
        self.assertEqual(level['level']['recipe_catalog_ref'], {'id': level['level']['id'], 'version': 1})
        self.assertNotIn('menu_order', level['level'])

    def test_a_design_is_named_by_its_content(self):
        level, _ = lc.normalize(restock({}, ['steak']))
        content_id = level['level']['id']
        self.assertRegex(content_id, r'^player-[0-9a-f]{12}$')
        self.assertEqual({level[kind]['id'] for kind in ('map', 'order_policy', 'recipe_catalog')}, {content_id})
        self.assertEqual({level['level'][ref]['id'] for ref in ('map_ref', 'order_policy_ref', 'recipe_catalog_ref')}, {content_id})
        self.assertEqual(lc.normalize(restock({}, ['steak']))[0]['level']['id'], content_id)
        dearer = restock({}, ['steak'])
        dearer['recipe_catalog']['recipes']['steak']['price'] = 60
        self.assertNotEqual(lc.normalize(dearer)[0]['level']['id'], content_id)

    def test_bad_price_or_missing_ingredient_is_refused_before_any_round(self):
        bundle = restock({}, ['steak'])
        bundle['recipe_catalog']['recipes']['steak']['price'] = 155
        self.assertEqual([d['code'] for d in lc.calibrate(bundle)['diagnostics']], ['PRICE_OUT_OF_RANGE'])
        report = lc.calibrate(restock({'fridge': 'fish'}, ['steak']))
        self.assertFalse(report['playable'])
        self.assertIn('NO_PRODUCTION_CHAIN', [d['code'] for d in report['diagnostics']])


class CalibrationTests(unittest.TestCase):
    def test_target_is_half_the_pair_median_and_the_level_plays_to_it(self):
        bundle = restock({'bread': 'cucumber'}, ['salad'])
        report = lc.calibrate(bundle, seeds=(1,))
        self.assertTrue(report['playable'])
        self.assertEqual(report['target'], int(report['pair_median'] * .5) // 10 * 10)
        k = SpatialKitchen(lc.finalize(bundle, report))
        self.assertEqual(k.snapshot()['goal_status']['target_money'], report['target'])
        self.assertEqual(k.rules.round_limit, 180)
        # Statistics and research records count it as level 0; its design is in the resolved configuration.
        self.assertEqual(level_number(k.c), PLAYER_LEVEL)
        self.assertTrue(k.resolved['level']['id'].startswith(lc.PLAYER_PREFIX))

    def test_research_records_accept_level_zero(self):
        record = json.loads((Path(__file__).parent / 'fixtures/research-v2-short.json').read_text())
        record['level'] = PLAYER_LEVEL
        self.assertEqual(schema_check.validate(record, 'research-record.schema.json'), [])


if __name__ == '__main__':
    unittest.main()
