"""Ask ahead (ask_ahead.py, trial ask_ahead): an isolated prediction, guarded answers, and nothing changed with it off."""
import json
import unittest
from unittest.mock import patch

import ask_ahead
import ask_ahead_sim as sim
import fingerprint
import payload_fingerprint as pf
import reference_policy
from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen


# A prediction forks the kitchen and plays the fork to the end of Jeff's step, so one before every tick of every
# fingerprint round took 200 s, a third of the whole test run. One round is still predicted at every tick; the others
# every SPARSE-th tick (a prime, so over a round the predictions fall on every phase of the 10-tick decision period).
SPARSE = 7
EVERY_TICK = 'level2-reference'


def predicting_everywhere(kitchen_class, every=1):
    """The kitchen class's advance, predicting Jeff's step end before every ``every``-th tick he has a step (and
    throwing the prediction away)."""
    advance, inside, ticks = kitchen_class.advance, [], [0]

    def predict_then_advance(self, seconds):
        if self.chefs['jeff'].job is not None and not inside:      # not again inside the fork's own advance
            ticks[0] += 1
            if ticks[0] % every == 0:
                inside.append(True)
                try:
                    ask_ahead.predict(self)
                finally:
                    inside.clear()
        return advance(self, seconds)
    return patch.object(kitchen_class, 'advance', predict_then_advance)


class IsolationTests(unittest.TestCase):
    def test_predicting_through_every_round_changes_no_behaviour_fingerprint(self):
        self.assertIn(EVERY_TICK, fingerprint.SCENARIOS)
        for name in fingerprint.SCENARIOS:
            with self.subTest(name):
                golden = json.loads((fingerprint.GOLDEN / f'{name}.json').read_text())
                with predicting_everywhere(SpatialKitchen, 1 if name == EVERY_TICK else SPARSE):
                    actual = fingerprint.run(name)
                self.assertEqual(golden, json.loads(json.dumps(actual)))

    def test_predicting_through_a_round_changes_no_payload_fingerprint(self):
        for name in ('level2', 'level3'):
            with self.subTest(name):
                golden = json.loads((pf.GOLDEN / f'{name}.json').read_text())
                with predicting_everywhere(SpatialKitchen, SPARSE):
                    actual = pf.run(name)
                self.assertEqual(golden['requests'], actual['requests'])

    def test_the_prediction_leaves_the_kitchen_and_its_record_hooks_untouched(self):
        k = SpatialKitchen(level_config(load_config(), 'level-2'))
        seen = []

        class Observer:
            capture_observations = True
            def observe_input(self, record): seen.append(('input', record))
            def observe_event(self, event): seen.append(('event', event))
            def item_transform(self, *a): seen.append(('transform', a))
            def arrival(self, *a): seen.append(('arrival', a))
        step = 0
        while k.time < 40:
            if step % 10 == 0:
                for who, role in (('human', 'assembler'), ('jeff', 'cook')):
                    action = reference_policy.choose(k, who, role)
                    if action:
                        k.start(who, action)
            k.advance(.05)
            step += 1
        while k.chefs['jeff'].job is None:
            action = reference_policy.choose(k, 'jeff', 'cook')
            if action:
                k.start('jeff', action)
            k.advance(.05)
        k._record_observer, k._research_state_ref = Observer(), 'state-ref'
        caches = (k.nav._cached_shortest_path.cache_info(), k.nav._visible_corners.cache_info())
        before = (k.event_seq, len(k.events), len(k.inputs), k.revision, k.time, json.dumps(k.snapshot(), sort_keys=True))
        twin = ask_ahead.predict(k)
        self.assertIsNotNone(twin)
        self.assertGreater(twin.time, k.time)
        self.assertEqual((k.nav._cached_shortest_path.cache_info(), k.nav._visible_corners.cache_info()), caches)
        self.assertEqual((k.event_seq, len(k.events), len(k.inputs), k.revision, k.time, json.dumps(k.snapshot(), sort_keys=True)), before)
        self.assertEqual(seen, [])                                       # the record hooks heard nothing
        self.assertFalse(hasattr(twin, '_record_observer') or hasattr(twin, '_research_state_ref'))
        self.assertIsNot(twin.nav._cached_shortest_path, k.nav._cached_shortest_path)
        self.assertIs(k._record_observer.__class__, Observer)           # still attached to the real kitchen

    def test_a_step_that_does_not_end_as_planned_gives_no_prediction(self):
        k = SpatialKitchen(level_config(load_config(), 'level-2'))
        self.assertIsNone(ask_ahead.predict(k))                          # no step
        k.start('jeff', next(a for a in k.actions('jeff') if a.key.startswith('go ')))
        with patch.object(ask_ahead, 'GRACE', -100.0):                   # no time to finish
            self.assertIsNone(ask_ahead.predict(k))
        self.assertIsNotNone(ask_ahead.predict(k))


class SimulationTests(unittest.TestCase):
    def test_it_shortens_the_wait_without_refusals_and_says_what_it_dropped(self):
        for latency in (1.2, 3.5):
            with self.subTest(latency=latency):
                off, on = sim.simulate(latency, False), sim.simulate(latency, True)
                self.assertEqual(off['asked_ahead'], 0)
                self.assertGreater(on['asked_ahead'], 10)
                self.assertLess(on['wait_median'], off['wait_median'] - .3)
                self.assertLessEqual(on['refused_by_engine'], off['refused_by_engine'])
                self.assertIn(on['asked_ahead'] - sum(on['ahead_results'].values()), (0, 1))   # the last may be on its way at closing
                self.assertGreaterEqual(on['ahead_results'].get('applied', 0), .7 * on['asked_ahead'])
                self.assertEqual(sum(on['ahead_discarded_why'].values()), on['ahead_results'].get('discarded', 0))

    def test_off_by_default_and_the_switch_is_recorded(self):
        import features
        self.assertEqual(features.current()['ask_ahead'], {'stage': 'trial', 'on': False, 'player_switch': False,
                                                           'version': ask_ahead.VERSION})



class StepGapTests(unittest.TestCase):
    def test_an_answer_asked_ahead_has_a_negative_wait_to_ask_in_its_own_group(self):
        from scripts import decision_stats
        at = lambda seconds: {'game_time_ms': round(seconds * 1000), 'elapsed_wall_ms': round(seconds * 1000)}
        rows = [{'kind': 'start', 'game_time_ms': 0, 'elapsed_wall_ms': 0, 'features': {'ask_ahead': {'on': True, 'version': ask_ahead.VERSION}}},
                {'kind': 'action_start', 'actor': 'jeff', 'action_id': 1, 'action': 'go b1', **at(1.0)},
                {'kind': 'ai_request', 'request_id': 1, 'ask_ahead': {'job_id': 1, 'predicted_end_t': 4.0}, **at(2.8)},
                {'kind': 'action_done', 'actor': 'jeff', 'action_id': 1, 'action': 'go b1', **at(4.0)},
                {'kind': 'ai_response', 'request_id': 1, 'model': 'm', 'choice': 'chop b1', 'applied': True, 'fresh': True,
                 'action_id': 2, 'ask_ahead': {'result': 'applied', 'reason': None}, **at(4.05)},
                {'kind': 'action_start', 'actor': 'jeff', 'action_id': 2, 'action': 'chop b1', **at(4.05)},
                {'kind': 'action_done', 'actor': 'jeff', 'action_id': 2, 'action': 'chop b1', **at(6.3)},
                {'kind': 'end', 'game_time_ms': 7000, 'elapsed_wall_ms': 7000}]
        models = decision_stats.defaultdict(decision_stats.new_model)
        decision_stats.add_round(rows, models)
        gaps = decision_stats.summary(models['m'])['step_gaps']
        self.assertEqual(list(gaps), ['ask_ahead'])
        self.assertEqual((gaps['ask_ahead']['asked_ahead'], gaps['ask_ahead']['split_unknown']), (1, 0))
        self.assertEqual(gaps['ask_ahead']['waiting_to_ask']['median'], -1.2)       # sent 1.2 s before the step ended
        self.assertEqual(gaps['ask_ahead']['total']['median'], .05)

if __name__ == '__main__':
    unittest.main()
