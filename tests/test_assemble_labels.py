"""Assembly labels say which way the ingredient moves (service rules)."""
import unittest

import config_contract as cc
from kitchen import Food, GroundItem
from model_language import english_text
from spatial_kitchen import SpatialKitchen, tile_key


def kitchen(level='level-2'):
    k = SpatialKitchen(cc.load_level(level))
    k.ground.clear()
    station = next(s for s in k.stations.values() if s.food and s.food.stage == 'clean_plate')
    plate, station.food = station.food, None
    return k, plate


class AssembleLabelTests(unittest.TestCase):
    def test_floor_labels_follow_the_plate(self):
        k, plate = kitchen()
        cell = tile_key(sorted(k.floor)[len(k.floor) // 2])
        place = k.place(cell).name
        k.ground['F90'] = GroundItem(Food('F90', ingredient='bread'), cell)
        k.chefs['jeff'].hand = plate
        a = next(a for a in k.actions('jeff') if a.kind == 'assemble_ground')
        self.assertEqual(a.label, f'把{place}的面包加进手中的盘')
        self.assertTrue(english_text(a.label).startswith('Add the Bread from floor'))
        self.assertTrue(english_text(a.label).endswith('to the held plate'))
        k.ground.clear()
        k.ground[plate.id] = GroundItem(plate, cell)
        k.chefs['jeff'].hand = Food('F90', ingredient='bread')
        a = next(a for a in k.actions('jeff') if a.kind == 'assemble_ground')
        self.assertEqual(a.label, f'把手中的面包放进{place}的盘里')
        self.assertTrue(english_text(a.label).startswith('Put the held Bread onto the plate at floor'))

    def test_counter_labels_follow_the_plate(self):
        k, plate = kitchen()
        key = next(c for c in k.counters if not k.stations[c].food)
        name = k.stations[key].name
        k.stations[key].food = Food('F91', 'chopped', ingredient='lettuce')
        k.chefs['human'].hand = plate
        a = next(a for a in k.actions('human') if a.key == 'assemble ' + key)
        self.assertEqual(a.label, f'把{name}的生菜加进手中的盘')
        k.stations[key].food, k.chefs['human'].hand = plate, Food('F91', 'chopped', ingredient='lettuce')
        a = next(a for a in k.actions('human') if a.key == 'assemble ' + key)
        self.assertEqual(a.label, f'把手中的生菜放进{name}的盘里')
        self.assertEqual([c for c in english_text(a.label) if ord(c) > 127], [])

    def test_legacy_wording_is_kept(self):
        k, plate = kitchen('legacy-level-2')
        key = next(c for c in k.counters if not k.stations[c].food)
        k.stations[key].food = plate
        k.chefs['human'].hand = Food('F91', 'chopped', ingredient='lettuce')
        a = next(a for a in k.actions('human') if a.key == 'assemble ' + key)
        self.assertEqual(a.label, f'在{k.stations[key].name}向盘中加入食材')


if __name__ == '__main__':
    unittest.main()
