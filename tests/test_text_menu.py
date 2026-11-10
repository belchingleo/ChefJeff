"""The text kitchen (play.py) can number every action it lists, on every level, for the whole round."""
import random
import unittest

import play
from kitchen import Kitchen, load_config
from levels import level_config


class Console:
    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)


class TextMenuTests(unittest.TestCase):
    def test_the_menu_opens_on_a_new_round_of_every_level(self):
        for level in ('level-1', 'level-2', 'level-3'):
            with self.subTest(level):
                k = Kitchen(level_config(load_config(), level))
                console = Console()
                menu = play.show_menu(k, console)
                actions = k.actions('human')
                self.assertEqual(sorted(a.key for a in menu.values()), sorted(a.key for a in actions))
                for source in k.ingredients:                       # every ingredient source can be fetched from by number
                    self.assertIn(f'[{k.fetch_key(source)}]', console.lines[-1])

    def test_every_listed_action_keeps_one_number_for_the_round(self):
        for level in ('level-1', 'level-2', 'level-3'):
            with self.subTest(level):
                rng, k, seen, step = random.Random(1), Kitchen(level_config(load_config(), level)), {}, 0
                while not k.ended:
                    if step % 10 == 0:
                        for who in ('human', 'jeff'):
                            actions = k.actions(who)
                            numbers = k.menu_numbers(a.key for a in actions)
                            self.assertEqual(len(set(numbers.values())), len(numbers))      # no number is shared
                            for a in actions:
                                self.assertEqual(seen.setdefault(a.key, numbers[a.key]), numbers[a.key], a.key)
                            choices = [a for a in actions if a.kind != 'wait']
                            if k.chefs[who].job is None and choices:
                                k.start(who, rng.choice(choices))
                    k.advance(.05)
                    step += 1
                # The round reached actions the fixed list never had (the cause of the crash this test guards).
                self.assertTrue({key.split(' ')[0] for key in k.menu_extra} & {'load', 'assemble', 'swap'}, k.menu_extra)


if __name__ == '__main__':
    unittest.main()
