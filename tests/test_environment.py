"""environment.py: what an agent sees and does through its AgentPort (env-v1)."""
import json
import re
import unittest

import environment
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen


def kitchen(level='level-2'):
    return SpatialKitchen(level_config(load_config(), level))


class ObserveTests(unittest.TestCase):
    def test_observation_is_plain_english_data_with_every_listed_action(self):
        k = kitchen()
        port = environment.AgentPort(k)
        seen = port.observe()
        self.assertEqual(seen['env_api_version'], 'env-v1')
        self.assertEqual(seen['who'], 'jeff')
        text = json.dumps(seen, ensure_ascii=False)
        self.assertIsNone(re.search(r'[㐀-鿿]', text), 'observations are in English')
        self.assertEqual([a['key'] for a in seen['actions']], [a.key for a in k.actions('jeff')])   # unpruned, in order
        self.assertEqual(set(seen['actions'][0]), {'key', 'kind', 'target', 'label'})
        self.assertNotIn('items', seen['kitchen'])
        self.assertNotIn('route_slide', seen['kitchen']['chefs']['jeff'])
        json.dumps(seen)                                                       # plain data throughout

    def test_events_since_a_sequence_number(self):
        k = kitchen()
        port = environment.AgentPort(k)
        start = port.observe()['event_seq']
        port.act('fetch bread')
        events = port.events_since(start)
        self.assertTrue(events)
        self.assertTrue(all(e['seq'] > start for e in events))
        self.assertEqual(port.events_since(k.event_seq), [])


class ActTests(unittest.TestCase):
    def test_an_action_is_checked_when_it_arrives(self):
        k = kitchen()
        port = environment.AgentPort(k)
        done = port.act('fetch bread')
        self.assertTrue(done['applied'])
        self.assertIsNotNone(done['job_id'])
        self.assertEqual(k.inputs[-1]['call'], 'start')                       # recorded as an engine input
        self.assertEqual(port.act('no such action'), {'applied': False, 'reason': 'not_listed', 'job_id': done['job_id']})

    def test_the_job_guard(self):
        k = kitchen()
        port = environment.AgentPort(k)
        job = port.act('fetch bread')['job_id']
        self.assertEqual(port.act('fetch lettuce', expect_job=None)['reason'], 'job_changed')   # not idle any more
        self.assertTrue(port.act('fetch lettuce', expect_job=job)['applied'])                  # still that job
        self.assertEqual(port.act('wait', expect_job=job)['reason'], 'job_changed')

    def test_sprint_rides_on_an_applied_action(self):
        k = kitchen()
        port = environment.AgentPort(k)
        self.assertTrue(port.can_sprint)
        self.assertTrue(port.act('go serve', sprint=True)['sprinted'])

    def test_a_port_is_for_one_chef(self):
        with self.assertRaises(ValueError):
            environment.AgentPort(kitchen(), who='nobody')
        port = environment.AgentPort(kitchen(), who='human')
        self.assertEqual(port.observe()['who'], 'human')


class ViewTests(unittest.TestCase):
    def test_the_view_reads_and_refuses_every_engine_input(self):
        k = kitchen()
        view = environment.AgentPort(k).view
        self.assertIs(view.chefs, k.chefs)
        self.assertEqual(view.snapshot(), k.snapshot())
        self.assertEqual([a.key for a in view.actions('jeff')], [a.key for a in k.actions('jeff')])
        inputs = [name for name in dir(type(k)) if getattr(getattr(type(k), name), '__engine_input__', False)]
        self.assertTrue({'start', 'stop', 'advance', 'sprint', 'set_manual', 'report_position'} <= set(inputs))
        for name in inputs:
            with self.subTest(name), self.assertRaises(PermissionError):
                getattr(view, name)
        with self.assertRaises(PermissionError):
            view.time = 5

    def test_a_fork_plays_the_step_out_without_touching_the_kitchen(self):
        k = kitchen()
        port = environment.AgentPort(k)
        port.act('fetch bread')
        before = (k.time, len(k.events), len(k.inputs), json.dumps(k.snapshot(), sort_keys=True, default=str))
        twin = port.fork_until_step_end()
        self.assertIsNotNone(twin)
        self.assertIsNone(twin.chefs['jeff'].job)
        self.assertEqual(twin.chefs['jeff'].hand.ingredient, 'bread')
        self.assertEqual((k.time, len(k.events), len(k.inputs), json.dumps(k.snapshot(), sort_keys=True, default=str)), before)


if __name__ == '__main__':
    unittest.main()
