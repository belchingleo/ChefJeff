"""Cooking vessels: a soup pot boils, a frying pan fries; one vessel per stove."""
import unittest

import config_contract as cc
from kitchen import Food
from spatial_kitchen import SpatialKitchen


def noodle_kitchen():
    """Level 3's map with a soup pot on stove 1, a pan on stove 2, and noodle ingredients."""
    bundle = cc.level_bundle('level-3', embed=True)
    for e in bundle['map']['equipment']:
        if e['id'] == 'lettuce':
            e['params']['item'] = 'scallion'
        elif e['id'] == 'tomato':
            e['params']['item'] = 'noodles'
    for e in bundle['level']['initial_inventory']:
        if e['id'] == 'P1':
            e['object'] = 'pot'
    bundle['order_policy']['menu'] = [{'recipe_ref': 'beef_noodles', 'weight': 1}]
    bundle['order_policy']['patience_by_recipe'] = {'beef_noodles': 75000}
    bundle['level']['goal']['min_money'] = 70
    return SpatialKitchen(cc.freeze_bundle(bundle))


class VesselTests(unittest.TestCase):
    def setUp(self):
        self.k = noodle_kitchen()

    def keys(self, food):
        self.k.chefs['human'].hand = food
        return {a.key for a in self.k.actions('human')}

    def test_each_ingredient_goes_only_into_its_vessel(self):
        noodles, beef = Food('F90', ingredient='noodles'), Food('F91', 'chopped', ingredient='beef')
        self.assertEqual(self.k.snapshot()['vessels'],
                         {'pan': {'name': '平底锅', 'cooks': [{'item': 'beef', 'from': 'chopped'}]},
                          'pot': {'name': '汤锅', 'cooks': [{'item': 'noodles', 'from': 'raw'}]}})
        self.assertEqual(self.k.snapshot()['stations']['p1']['vessel'], 'pot')
        self.assertIn('put p1', self.keys(noodles))
        self.assertNotIn('put p2', self.keys(noodles))
        self.assertIn('put p2', self.keys(beef))
        self.assertNotIn('put p1', self.keys(beef))
        self.assertNotIn('put p1', self.keys(Food('F92', ingredient='beef')))  # raw beef fries only once chopped

    def test_noodles_boil_then_boil_dry_and_catch_fire(self):
        k = self.k
        s = k.stations['p1']
        k.chefs['human'].hand = Food('F90', ingredient='noodles')
        k.positions['human'] = k.path('human', 'p1')[-1]
        self.assertTrue(k.command('human', 'put p1')[0])
        k.advance(1)
        self.assertEqual(s.food.stage, 'cooking')
        ready, burn, fire = k.rules.heat_thresholds('noodles')
        k.advance(ready)
        self.assertEqual(s.food.stage, 'ready')
        k.advance(burn - ready)
        self.assertEqual(s.food.stage, 'burnt')
        k.advance(fire - burn)
        self.assertTrue(s.fire)

    def test_one_vessel_per_stove(self):
        k = self.k
        k.chefs['human'].hand = Food('P3', 'pot')
        keys = {a.key for a in k.actions('human')}
        self.assertNotIn('put pot p1', keys)  # both stoves already hold a vessel
        self.assertIn('swap pot p1', keys)

    def test_beef_noodles_are_plated_and_served(self):
        k = self.k
        plate = k.stations['plates'].food
        k.stations['plates'].food = None
        plate = Food(plate.id, 'ready', ingredient='noodles', plate_id=plate.id, components=('noodles', 'beef', 'scallion'))
        self.assertEqual(k.dish(plate), 'beef_noodles')
        k.advance(1)
        k.chefs['human'].hand = plate
        k.positions['human'] = k.path('human', 'serve')[-1]
        self.assertTrue(k.command('human', 'serve')[0])
        k.advance(2)
        self.assertEqual((k.served, k.money), (1, 70))

    def test_only_a_passed_vessel_is_marked_as_one_in_flight(self):
        k = self.k
        base = {'target': 'counter4', 'from': (2, 2), 'to': (3, 3), 'started': 0, 'lands_at': 1}
        k.projectiles['F95'] = dict(base, food=Food('F95', ingredient='bread'))
        k.projectiles['P3'] = dict(base, food=Food('P3', 'pot', contents=Food('F96', 'ready', ingredient='beef')))
        flying = {p['id']: p for p in k.snapshot()['projectiles']}
        self.assertNotIn('vessel', flying['F95'])
        self.assertIsNone(flying['F95']['contents'])
        self.assertEqual(flying['P3']['vessel'], 'pan')
        self.assertEqual(flying['P3']['contents'], {'stage': 'ready', 'ingredient': 'beef'})

    def test_model_input_for_a_noodle_kitchen_is_plain_english(self):
        import json, re
        from whitebox_server import SpatialJevClient
        k = self.k
        for hand in (None, Food('F90', ingredient='noodles'), Food('F91', 'chopped', ingredient='beef'), Food('P3', 'pot')):
            k.chefs['jeff'].hand = hand
            payload = SpatialJevClient(k.c, key='test').payload(k.snapshot(), k.actions('jeff'))
            text = json.dumps(payload, ensure_ascii=False)
            self.assertIsNone(re.search(r'[\u3400-\u9fff]', text), re.findall(r'[^"]*[\u3400-\u9fff][^"]*', text)[:5])

    def test_a_vessel_kind_missing_from_the_map_breaks_the_production_chain(self):
        bundle = cc.level_bundle('level-3', embed=True)
        bundle['order_policy']['menu'] = [{'recipe_ref': 'beef_noodles', 'weight': 1}]
        bundle['order_policy']['patience_by_recipe'] = {}
        for e in bundle['map']['equipment']:
            if e['id'] == 'tomato':
                e['params']['item'] = 'noodles'
            elif e['id'] == 'lettuce':
                e['params']['item'] = 'scallion'
        _, diagnostics = cc.resolve_config(bundle)  # only pans: noodles cannot boil
        self.assertIn('NO_PRODUCTION_CHAIN', {d['code'] for d in diagnostics})


if __name__ == '__main__':
    unittest.main()
