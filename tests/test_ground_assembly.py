import unittest

import config_contract as cc
from kitchen import Food, GroundItem
from spatial_kitchen import SpatialKitchen, tile_key


class GroundAssemblyTests(unittest.TestCase):
    """Service rules: assemble with a plate or ingredient on the floor, as on a counter."""

    def kitchen(self, level='level-2'):
        k = SpatialKitchen(cc.load_level(level))
        k.ground.clear()
        return k

    def plate(self, k):
        """Lift a real clean plate off its counter so the plate inventory stays whole."""
        station = next(s for s in k.stations.values() if s.food and s.food.stage == 'clean_plate')
        plate, station.food = station.food, None
        return plate

    def place(self, k, who, food):
        cell = sorted(k.floor)[len(k.floor) // 2]
        k.ground[food.id] = GroundItem(food, tile_key(cell))
        k.positions[who] = cell
        k.chefs[who].location = tile_key(cell)
        return tile_key(cell)

    def finish(self, k, who, action):
        k.positions[who] = k.path(who, action.target)[-1]
        self.assertTrue(k.start(who, action)[0])
        k.advance(.4)
        k.assert_invariants()

    def test_held_ingredient_goes_onto_floor_plate_both_chefs(self):
        for who in ('human', 'jeff'):
            k = self.kitchen()
            plate = k.merge_plate(self.plate(k), Food('bun', ingredient='bread'))
            location = self.place(k, who, plate)
            k.chefs[who].hand = Food('leaf', 'chopped', ingredient='lettuce')
            action = k.quick_interaction(who, preferred='item:bun')
            self.assertEqual(action.kind, 'assemble_ground')
            self.finish(k, who, action)
            self.assertIsNone(k.chefs[who].hand)
            self.assertEqual(set(k.ground['bun'].food.components), {'bread', 'lettuce'})
            self.assertEqual(k.ground['bun'].location, location)

    def test_floor_ingredient_goes_onto_held_plate(self):
        for who in ('human', 'jeff'):
            k = self.kitchen()
            self.place(k, who, Food('bun', ingredient='bread'))
            k.chefs[who].hand = self.plate(k)
            action = k.quick_interaction(who, preferred='item:bun')
            self.assertEqual(action.kind, 'assemble_ground')
            self.finish(k, who, action)
            self.assertEqual(k.chefs[who].hand.components, ('bread',))
            self.assertNotIn('bun', k.ground)

    def test_clean_floor_plate_takes_the_ingredient(self):
        k = self.kitchen()
        plate = self.plate(k)
        location = self.place(k, 'human', plate)
        k.chefs['human'].hand = Food('bun', ingredient='bread')
        self.finish(k, 'human', next(a for a in k.actions('human') if a.key == 'assemble ground '+plate.id))
        self.assertNotIn(plate.id, k.ground)
        self.assertEqual((k.ground['bun'].food.plate_id, k.ground['bun'].location), (plate.id, location))

    def test_duplicates_and_swap_remain(self):
        k = self.kitchen()
        self.place(k, 'human', k.merge_plate(self.plate(k), Food('bun', ingredient='bread')))
        k.chefs['human'].hand = Food('bun2', ingredient='bread')
        keys = [a.key for a in k.actions('human')]
        self.assertNotIn('assemble ground bun', keys)
        self.assertIn('pickup bun', keys)

    def test_stale_floor_plate_is_rejected(self):
        k = self.kitchen()
        self.place(k, 'human', k.merge_plate(self.plate(k), Food('bun', ingredient='bread')))
        k.chefs['human'].hand = Food('leaf', 'chopped', ingredient='lettuce')
        action = next(a for a in k.actions('human') if a.key == 'assemble ground bun')
        k.ground['bun'].food = k.merge_plate(k.ground['bun'].food, Food('leaf2', 'chopped', ingredient='lettuce'))
        k.start('human', action)
        k.advance(1)
        self.assertEqual(k.chefs['human'].hand.id, 'leaf')
        k.assert_invariants()

    def test_single_dish_menu_has_no_ground_assembly(self):
        k = self.kitchen('level-1')
        self.place(k, 'human', self.plate(k))
        k.chefs['human'].hand = Food('beef', 'ready')
        self.assertNotIn('assemble_ground', {a.kind for a in k.actions('human')})
        self.assertNotIn('ground_assembly', k.snapshot())


if __name__ == '__main__':
    unittest.main()
