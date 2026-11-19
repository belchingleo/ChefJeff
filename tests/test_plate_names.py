"""plate_names (plate-names-v1): a plating option says what the plate there, or in hand, holds.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import unittest

import features
import plate_names
import research_replay
from jev import compose_payload
from research_record import validate_record
from whitebox_server import SpatialJevClient
from test_clear_names import do, kitchen
import test_research_save_paths as paths


def request(k, plate):
    return compose_payload(SpatialJevClient(k.c, key='test-no-credential'), k, k.snapshot(), k.actions('jeff'), [],
                           None, names=True, clear=True, plate=plate)


def options(k, plate):
    return request(k, plate)['questions']['next_action']['criteria']


def cooked_beef_on_stove_1(k):
    for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
        do(k, 'jeff', key)
    while k.stations['p1'].food.stage != 'ready':
        k.advance(0.05)


class PlateNamesTests(unittest.TestCase):
    def test_a_put_onto_a_plate_names_the_plate_there(self):
        k = kitchen(2)
        for key in ('fetch lettuce', 'put b1', 'chop b1', 'take plates', 'assemble b1', 'put counter10', 'fetch bread'):
            do(k, 'jeff', key)
        off, on = options(k, False), options(k, True)
        self.assertEqual(off['assemble counter10'], 'Put the held bread (as fetched) onto the plate at Counter 10')
        self.assertEqual(on['assemble counter10'],
                         'Put the held bread (as fetched) onto the plate with lettuce at Counter 10')
        self.assertEqual(on['assemble counter2'], 'Put the held bread (as fetched) onto the clean plate at Counter 2')
        self.assertEqual({key for key in on if on[key] != off[key]}, {'assemble counter10', 'assemble counter2'})

    def test_the_held_plate_is_named(self):
        k = kitchen(2)
        for key in ('fetch lettuce', 'put b1', 'chop b1', 'take plates', 'assemble b1', 'put counter10',
                    'fetch tomato', 'put b1', 'chop b1', 'take counter10'):
            do(k, 'jeff', key)
        self.assertEqual(options(k, True)['assemble b1'],
                         'Add the tomato (chopped) from Board 1 to the held plate with lettuce')

    def test_plating_from_a_stove_says_which_plate_and_a_pan_in_hand_which_plate_it_fills(self):
        k = kitchen(3)
        cooked_beef_on_stove_1(k)
        do(k, 'jeff', 'take plates')
        self.assertEqual(options(k, False)['plate p1'], 'Plate food from Stove 1')
        self.assertEqual(options(k, True)['plate p1'], 'Plate food from Stove 1 onto the held clean plate')
        k = kitchen(3)
        cooked_beef_on_stove_1(k)
        do(k, 'jeff', 'take pot p1')
        on = options(k, True)
        self.assertEqual(on['plate counter2'],
                         'Fill the clean plate on Counter 2 from your frying pan (keep the empty frying pan)')

    def test_nothing_about_the_dish_or_the_order_and_twice_changes_nothing(self):
        k = kitchen(2)
        for key in ('fetch lettuce', 'put b1', 'chop b1', 'take plates', 'assemble b1', 'put counter10', 'fetch bread'):
            do(k, 'jeff', key)
        off, on = request(k, False), request(k, True)
        for label in on['questions']['next_action']['criteria'].values():
            self.assertNotIn('order', label)
            self.assertNotIn('Burger', label)
        on, off = json.loads(json.dumps(on)), json.loads(json.dumps(off))
        self.assertEqual(plate_names.apply(json.loads(json.dumps(on))), on)
        self.assertEqual(on['state'].pop('plate_names_version'), plate_names.VERSION)
        self.assertNotIn('plate_names_version', off['state'])
        on['questions'] = off['questions']
        self.assertEqual(on, off)       # the labels are all it changes

if __name__ == '__main__':
    unittest.main()
