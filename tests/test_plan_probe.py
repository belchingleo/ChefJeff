"""scripts/plan_probe.py builds its emergencies and arms offline; a stand-in answers instead of the model."""
import unittest
from unittest.mock import patch

from harness import PLAN_KEEP_QUESTION, PLAN_STEP_QUESTIONS
from kitchen import load_config
from levels import level_config
from scripts import plan_probe
from whitebox_server import SpatialJevClient


class PlanProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = SpatialJevClient(level_config(load_config(), plan_probe.LEVEL), key='unit-test-not-a-real-key')
        cls.emergencies = plan_probe.emergencies()

    def test_each_emergency_has_jeff_idle_and_an_action_that_deals_with_it(self):
        names = [name for name, _, _ in self.emergencies]
        self.assertEqual(names, ['pan_about_to_burn', 'stove_on_fire'])
        for name, k, urgent in self.emergencies:
            with self.subTest(name):
                self.assertIsNone(k.chefs['jeff'].job)
                self.assertIsNone(k.chefs['jeff'].hand)
                self.assertTrue(urgent)
                self.assertTrue(set(urgent) <= {a.key for a in k.actions('jeff')})

    def test_the_arms_differ_only_in_the_plan(self):
        _, k, _ = self.emergencies[0]
        off, asking, held = (plan_probe.arm_payload(self.client, k, arm) for arm in plan_probe.ARMS)
        self.assertFalse([q for q in off['questions'] if q.startswith('plan_')])
        self.assertEqual([q for q in asking['questions'] if q.startswith('plan_')], list(PLAN_STEP_QUESTIONS))
        self.assertEqual([q for q in held['questions'] if q.startswith('plan_')], [PLAN_KEEP_QUESTION])
        self.assertEqual([s['work'] for s in held['state']['jeff_plan']['steps']], list(plan_probe.UNRELATED))
        for payload in (asking, held):
            self.assertEqual(payload['questions']['next_action'], off['questions']['next_action'])
            self.assertEqual(payload['state']['kitchen'], off['state']['kitchen'])

    def probe(self, scenario, ask, repeats=1):
        with patch.object(plan_probe, 'emergencies', lambda: [scenario]):
            return plan_probe.run(self.client, repeats=repeats, ask=ask)['emergencies'][scenario[0]]

    def test_the_report_compares_the_arms(self):
        burn, fire = self.emergencies

        def steady(urgent):
            return lambda payload: {'choice': urgent[0], 'probabilities': {urgent[0]: .9, 'wait': .1}}

        def fenced(urgent):
            return lambda payload: ({'choice': 'wait', 'probabilities': {'wait': 1.0}} if 'jeff_plan' in payload['state']
                                    else steady(urgent)(payload))

        def failing(payload):
            raise RuntimeError('TypeSafe HTTP 429')
        report = self.probe(burn, steady(burn[2]), repeats=2)
        self.assertEqual(report['arms']['plan_held'], {'asked': 2, 'answered': 2, 'chose_emergency_action': 1.0,
                                                       'mean_probability_on_emergency_actions': .9, 'chose_wait': 0.0,
                                                       'choices': {burn[2][0]: 2}})
        self.assertTrue(report['plan_held_not_below_plan_off'])
        report = self.probe(fire, fenced(fire[2]))
        self.assertEqual((report['arms']['plan_held']['chose_wait'], report['plan_held_not_below_plan_off']), (1.0, False))
        self.assertEqual(report['arms']['plan_off']['chose_emergency_action'], 1.0)
        report = self.probe(fire, failing)
        self.assertEqual(report['arms']['plan_off'], {'asked': 1, 'answered': 0})
        self.assertIsNone(report['plan_held_not_below_plan_off'])


if __name__ == '__main__':
    unittest.main()
