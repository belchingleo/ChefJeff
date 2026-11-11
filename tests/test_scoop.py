"""An empty pan or pot held over a loose ingredient it can cook scoops it up and stays in the hands, as a held plate
takes an ingredient: one press for the player, one choice for Jeff (Overcooked 2 would set the pan down there). Off
the stove it does not heat. Both chefs have it, and Space picks it when facing the board."""
import unittest

from kitchen import Food, load_config
from levels import level_config
from model_language import english_text
from spatial_kitchen import SpatialKitchen


def chopped_beef(id_='T1'):
    f = Food(id_)
    f.ingredient, f.stage = 'beef', 'chopped'
    return f


class ScoopTests(unittest.TestCase):
    def kitchen(self, level=2):
        k = SpatialKitchen(level_config(load_config(), level))
        pot = next(p for p in k.pots if k.stations[p].pot_id)
        return k, pot

    def holding_empty_pan(self, k, who):
        lift = next(a for a in k.actions(who) if a.kind == 'lift_pot')
        k.positions[who] = k.path(who, lift.target)[-1]
        self.assertTrue(k.start(who, lift)[0])
        for _ in range(10):
            k.advance(.05)
        self.assertEqual(k.chefs[who].hand.stage, 'pot')

    def test_an_empty_pan_scoops_a_chopped_ingredient_off_a_board_and_stays_in_hand(self):
        for who in ('human', 'jeff'):
            k, _ = self.kitchen()
            self.holding_empty_pan(k, who)
            board = k.boards[0]
            k.stations[board].food = chopped_beef()
            scoop = [a for a in k.actions(who) if a.kind == 'scoop_counter' and a.target == board]
            self.assertEqual(len(scoop), 1, who)
            self.assertIn('盛起', scoop[0].label)
            self.assertTrue(english_text(scoop[0].label).startswith('Scoop '), english_text(scoop[0].label))
            pan = k.chefs[who].hand.id
            k.positions[who] = k.path(who, board)[-1]
            self.assertTrue(k.start(who, scoop[0])[0])
            for _ in range(10):
                k.advance(.05)
            held = k.chefs[who].hand
            self.assertEqual((held.id, held.contents.id), (pan, 'T1'))
            self.assertIsNone(k.stations[board].food)
            k.assert_invariants()

    def test_space_scoops_when_facing_the_board(self):
        k, _ = self.kitchen()
        self.holding_empty_pan(k, 'human')
        board = k.boards[0]
        k.stations[board].food = chopped_beef()
        cell = k.equipment[board]['cell']
        floor = next((cell[0] + dx, cell[1] + dy) for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))
                     if f'floor_{cell[0] + dx}_{cell[1] + dy}' in k.floor_places)
        k.positions['human'] = (float(floor[0]), float(floor[1]))
        k.facing['human'] = {(0, -1): 'up', (0, 1): 'down', (-1, 0): 'left', (1, 0): 'right'}[(cell[0] - floor[0], cell[1] - floor[1])]
        target, action = k.facing_interaction('human')
        self.assertEqual((target, action.kind), (board, 'scoop_counter'))

    def test_no_scoop_mid_chop_or_with_a_full_pan_or_food_it_cannot_cook(self):
        k, _ = self.kitchen()
        self.holding_empty_pan(k, 'human')
        board = k.boards[0]
        half = Food('T2'); half.ingredient, half.stage = 'beef', 'raw'; half.chopped = .5
        k.stations[board].food = half
        self.assertFalse([a for a in k.actions('human') if a.kind == 'scoop_counter'])
        k.stations[board].food = chopped_beef()
        k.chefs['human'].hand.contents = chopped_beef('T3')
        self.assertFalse([a for a in k.actions('human') if a.kind == 'scoop_counter'])


if __name__ == '__main__':
    unittest.main()
