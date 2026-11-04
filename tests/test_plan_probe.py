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

    def test_the_stale_plan_has_nothing_left_to_serve(self):
        k = plan_probe.nothing_left()
        self.assertFalse([o for o in k.orders if o['status'] in ('pending', 'future')])
        self.assertIsNone(k.chefs['jeff'].job)
        payload = plan_probe.stale_payload(self.client, k)
        self.assertEqual([s['work'] for s in payload['state']['jeff_plan']['steps']], list(plan_probe.STALE_PLAN))
        self.assertEqual([q for q in payload['questions'] if q.startswith('plan_')], [PLAN_KEEP_QUESTION])

    def test_the_report_counts_drop_answers_for_the_stale_plan(self):
        def answer(keep):
            return lambda payload: {'choice': 'wait', 'plan': {'keep': keep}} if PLAN_KEEP_QUESTION in payload['questions'] \
                else {'choice': 'wait'}
        with patch.object(plan_probe, 'emergencies', lambda: []):
            dropping = plan_probe.run(self.client, repeats=2, ask=answer(False))['stale_plan']
            keeping = plan_probe.run(self.client, repeats=1, ask=answer(None))['stale_plan']
        self.assertEqual((dropping['answered'], dropping['chose_drop'], dropping['dropped_in_most_answers']), (2, 1.0, True))
        self.assertEqual((keeping['chose_drop'], keeping['chose_keep'], keeping['dropped_in_most_answers']), (0.0, 0.0, False))

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

    def test_the_rolling_arms_and_stale_intent(self):
        _, burn, _ = self.emergencies[0]
        burning = plan_probe.arm_payload(self.client, burn, 'plan_held', 'rolling')
        self.assertNotIn('intent', burning['state']['recent_decisions'][0])          # a pan about to burn hides it (rolling-v3)
        self.assertIn('plan_step_1', burning['questions'])                           # but it is still asked
        _, k, _ = self.emergencies[1]                                                # the stove on fire: no pan about to burn
        off, asking, held = (plan_probe.arm_payload(self.client, k, arm, 'rolling') for arm in plan_probe.ARMS)
        for payload in (asking, held):     # asked at every request, never keep or drop
            self.assertEqual([q for q in payload['questions'] if q.startswith('plan_')], ['plan_step_1', 'plan_step_2'])
            self.assertEqual(payload['questions']['next_action'], off['questions']['next_action'])
        self.assertNotIn('jeff_plan', held['state'])
        self.assertEqual([d.get('intent') is not None for d in held['state']['recent_decisions']], [True])
        self.assertEqual([s['work'] for s in held['state']['recent_decisions'][0]['intent']], list(plan_probe.UNRELATED[:2]))
        # Every arm has the same previous decision, one that agrees with an idle, empty-handed Jeff; only the held arm's has intent.
        self.assertEqual([d['choice'] for d in off['state']['recent_decisions']], ['wait'])
        self.assertEqual(off['state']['recent_decisions'], asking['state']['recent_decisions'])
        self.assertEqual({k: v for k, v in held['state']['recent_decisions'][0].items() if k != 'intent'},
                         off['state']['recent_decisions'][0])
        stale = plan_probe.STALE_PLAN[:2]

        def answer(steps):
            return lambda payload: {'choice': 'wait', 'plan': {'steps': list(steps)}}
        with patch.object(plan_probe, 'emergencies', lambda: []):
            again = plan_probe.run(self.client, repeats=2, ask=answer(stale), mode='rolling')['stale_plan']
            moved = plan_probe.run(self.client, repeats=1, ask=answer(['take_plate']), mode='rolling')['stale_plan']
            silent = plan_probe.run(self.client, repeats=1, ask=answer([]), mode='rolling')['stale_plan']
        self.assertEqual((again['intent'], again['repeated_stale_intent'], again['left_it_in_most_answers']), (list(stale), 1.0, False))
        self.assertEqual((moved['repeated_stale_intent'], moved['left_it_in_most_answers']), (0.0, True))
        self.assertEqual((silent['gave_no_intent'], silent['left_it_in_most_answers']), (1.0, True))


if __name__ == '__main__':
    unittest.main()
