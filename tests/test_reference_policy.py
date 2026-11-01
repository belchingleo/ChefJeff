"""The scripted reference chefs read what each dish needs from the level, so calibration can play any recipe."""
import unittest

import config_contract as cc
import reference_policy
from spatial_kitchen import SpatialKitchen
from test_vessels import noodle_kitchen

PAIR = (('human', 'assembler'), ('jeff', 'cook'))


def salad_kitchen():
    """Level 3's map with cucumbers instead of bread, serving salad: nothing to cook."""
    bundle = cc.level_bundle('level-3', embed=True)
    for e in bundle['map']['equipment']:
        if e['id'] == 'bread':
            e['params']['item'] = 'cucumber'
    bundle['order_policy']['menu'] = [{'recipe_ref': 'salad', 'weight': 1}]
    bundle['order_policy']['patience_by_recipe'] = {'salad': 105000}
    return SpatialKitchen(cc.freeze_bundle(bundle))


def play(k, roles, policy):
    """Run the round to closing, each chef deciding every half game second as in calibration."""
    step = 0
    while not k.ended:
        for who, role in roles:
            if step % 10 == 0:
                action = policy(k, who, role)
                if action:
                    k.start(who, action)
        k.advance(.05)
        step += 1
    return k


class RecipeFollowingTests(unittest.TestCase):
    def test_pair_cooks_one_dish_in_a_pot_and_a_pan(self):
        # Beef noodles: noodles boil from raw in the pot, beef is chopped and fried in the pan.
        k = play(noodle_kitchen(), PAIR, reference_policy.choose)
        self.assertGreaterEqual(k.served, 4)

    def test_pair_serves_a_dish_with_nothing_to_cook(self):
        k = play(salad_kitchen(), PAIR, reference_policy.choose)
        self.assertGreaterEqual(k.served, 3)

    def test_solo_chef_works_both_vessels(self):
        k = play(noodle_kitchen(), (('human', 'solo'),), lambda k, who, role: reference_policy.choose_solo(k, who))
        self.assertGreaterEqual(k.served, 1)


if __name__ == '__main__':
    unittest.main()
