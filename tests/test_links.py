"""links.py: an option's link names the work it makes possible and nothing else (condition B of the links check)."""
import unittest

import links
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen


def run(k, who, key):
    k.start(who, next(a for a in k.actions(who) if a.key == key))
    while k.chefs[who].job:
        k.advance(.05)


def linked(k, key):
    option = next(a for a in k.actions('jeff') if a.key == key)
    return [a.key for a in links.link(k, 'jeff', option, k.actions('jeff'))]


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.k = SpatialKitchen(level_config(load_config(), 'level-2'))

    def test_raw_beef_on_a_board_leads_to_chopping_it(self):
        run(self.k, 'jeff', 'fetch beef')
        self.assertEqual(linked(self.k, 'put b1'), ['chop b1'])
        self.assertEqual(linked(self.k, 'wait'), [])
        self.assertEqual(self.k.chefs['jeff'].hand.ingredient, 'beef')      # the kitchen itself is unchanged

    def test_a_clean_plate_leads_to_plating_the_cooked_beef(self):
        for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
            run(self.k, 'jeff', key)
        while self.k.stations['p1'].food.stage != 'ready':
            self.k.advance(.05)
        self.assertIn('plate p1', linked(self.k, 'take plates'))
        self.assertTrue(all(key.startswith('plate ') for key in linked(self.k, 'take pot p1')))

    def test_walking_leads_to_no_new_work_line(self):
        self.assertEqual(links.sentence([]), '')
        self.assertEqual(linked(self.k, 'go serve'), [])


if __name__ == '__main__':
    unittest.main()
