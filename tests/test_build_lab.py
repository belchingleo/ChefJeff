"""scripts/build_lab.py: what an answer counts toward, the paired totals, and the request fingerprint. No model."""
import unittest

from scripts import build_lab


class BuildLabTests(unittest.TestCase):
    def test_an_answer_counts_toward_what_its_moment_was_picked_for(self):
        moment = {'steps': ['throw partner', 'put counter4'], 'labels': ['hand_over', 'open'], 'played': 'take counter5'}
        criteria = {'take counter2': 'Take Clean plate from Counter 2', 'throw partner': 'Throw to the other chef'}
        self.assertEqual(build_lab.measure('throw partner', moment, criteria),
                         {'step': True, 'plate_first': False, 'back_repeated': False})
        self.assertEqual(build_lab.measure('take counter2', moment, criteria),
                         {'step': False, 'plate_first': True, 'back_repeated': False})
        go = {'steps': None, 'labels': ['go'], 'played': None}
        self.assertEqual(build_lab.measure('go serve', go, {}), {'go_serve': True})

    def test_totals_add_hits_and_answers_per_measure(self):
        groups = [[{'step': True}, {'step': False}], [{'step': True, 'go_serve': False}]]
        self.assertEqual(build_lab.total(groups), {'answers': 3, 'step': [2, 3], 'go_serve': [0, 1]})

    def test_the_fingerprint_ignores_key_order_and_sees_any_change(self):
        a = {'model': 'm', 'state': {'x': 1, 'y': [1, 2]}}
        b = {'state': {'y': [1, 2], 'x': 1}, 'model': 'm'}
        self.assertEqual(build_lab.canonical(a), build_lab.canonical(b))
        self.assertNotEqual(build_lab.canonical(a), build_lab.canonical({**a, 'state': {'x': 1, 'y': [2, 1]}}))


if __name__ == '__main__':
    unittest.main()
