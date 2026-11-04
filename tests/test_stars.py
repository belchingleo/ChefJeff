import unittest
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
import harness


class StarTests(unittest.TestCase):
    """As in Overcooked 2 a round is rated in stars: the target, 1.5 times it and twice it."""

    def make(self, level):
        return SpatialKitchen(level_config(load_config(), level))

    def test_star_scores_follow_the_target(self):
        for level, scores in (('level-1', [150, 225, 300]), ('level-2', [160, 240, 320]), ('level-3', [190, 285, 380])):
            k = self.make(level)
            self.assertEqual(k.star_scores(), scores)
            self.assertEqual(k.snapshot()['goals']['star_scores'], scores)
            self.assertEqual(k.snapshot()['goal_status']['star_scores'], scores)

    def test_stars_count_the_scores_reached(self):
        k = self.make('level-2')
        self.assertEqual([k.stars(m) for m in (0, 159, 160, 239, 240, 319, 320, 500)], [0, 0, 1, 1, 2, 2, 3, 3])
        k.money = 250
        status = k.goal_status()
        self.assertEqual((status['stars_now'], status['met_now'], status['target_money']), (2, True, 160))

    def test_an_odd_target_rounds_the_middle_score_down(self):
        k = self.make('level-2')
        k.rules.goal['min_money'] = 155
        self.assertEqual(k.star_scores(), [155, 232, 310])

    def test_jeff_is_told_to_earn_as_much_as_he_can_with_the_same_scores(self):
        k = self.make('level-2')
        text = harness.objective_text(k.snapshot())
        self.assertIn('as much net revenue as you can', text)
        self.assertIn('160 yuan or more earns one star and reaches the target, 240 two stars, 320 three stars', text)
        self.assertNotIn('at least', text)


if __name__ == '__main__':
    unittest.main()
