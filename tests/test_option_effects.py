"""option_effects (option-effects-v1): each option says what carrying it out directly does, as the engine computes it.

No model is called: requests are composed locally, and the round is a loopback relay round.
"""
import json
import unittest
import uuid
from unittest.mock import patch

import features
import option_effects
import research_replay
from research_record import validate_record
from jev import compose_payload
from kitchen import load_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
import test_research_save_paths as paths


def kitchen(level):
    config = load_config()
    config.update(level=level)
    return SpatialKitchen(config)


def do(k, key):
    k.start('jeff', next(a for a in k.actions('jeff') if a.key == key))
    while k.chefs['jeff'].job is not None:
        k.advance(0.05)


def cooked_pan():
    """Level 1, Jeff alone: beef fetched, chopped, put in the pan on Stove 1 and left until it is cooked."""
    k = kitchen(1)
    for key in ('fetch beef', 'put b1', 'chop b1', 'take b1', 'put p1'):
        do(k, key)
    while k.stations['p1'].food.stage != 'ready':
        k.advance(0.1)
    return k


def request(k, effects=True):
    options = {**features.compose_options(features.current()), 'effects': effects}
    client = SpatialJevClient(k.c, key='test-no-credential')
    return compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, **options)


def labels(payload):
    return payload['questions']['next_action']['criteria']


def finished(k, key):
    """An independent fork with the option carried out to its end (Kitchen.fork, no shared parts)."""
    twin = k.fork()
    do(twin, key)
    return twin


class OptionEffectsTests(unittest.TestCase):
    def test_putting_a_held_pan_of_cooked_food_back_says_when_it_burns_and_the_stove_catches_fire(self):
        k = cooked_pan()
        k.advance(1.0)
        do(k, 'take pot p1')
        k.advance(1.0)
        on, off = request(k), request(k, False)
        twin = finished(k, 'put pot p1')
        ready, burn, fire = k.rules.heat_thresholds('beef')
        self.assertEqual(burn, fire)
        left = burn - twin.stations['p1'].food.heated
        self.assertEqual(labels(on)['put pot p1'], labels(off)['put pot p1'] +
                         f' (Result: beef (cooked) heats again on Stove 1: it burns and Stove 1 catches fire in {left:.1f} s)')
        self.assertEqual(labels(on)['discard'], labels(off)['discard'] + ' (Result: throws away beef (cooked): -2)')

    def test_lifting_the_pan_says_its_food_stops_heating(self):
        k = cooked_pan()
        on, off = request(k), request(k, False)
        self.assertEqual(labels(on)['take pot p1'], labels(off)['take pot p1'] + ' (Result: beef (cooked) stops heating)')

    def test_serving_names_the_order_and_what_it_pays_and_passing_it_says_nothing(self):
        k = cooked_pan()
        do(k, 'take plates')
        do(k, 'plate p1')
        on, off = request(k), request(k, False)
        twin = finished(k, 'serve')
        served = next(e for e in twin.events if e.get('kind') == 'served')
        self.assertEqual(labels(on)['serve'], labels(off)['serve'] +
                         f" (Result: serves {served['order_id']} (Steak): +{served['price'] + served['adjustment']})")
        self.assertEqual(labels(on)['discard'],
                         labels(off)['discard'] + ' (Result: throws away Steak, the plate stays in hand, dirty: -2)')
        self.assertEqual(labels(on)['throw partner'], labels(off)['throw partner'])

    def test_putting_food_on_a_supply_says_it_gives_nothing_and_taking_it_off_says_it_gives_again(self):
        k = kitchen(4)
        do(k, 'fetch beef')
        on, off = request(k), request(k, False)
        name = on['state']['kitchen']['stations']['lettuce']['name']
        self.assertEqual(labels(on)['put lettuce'], labels(off)['put lettuce'] +
                         f' (Result: {name} gives no lettuce while beef (as fetched) lies on it)')
        do(k, 'put lettuce')
        on, off = request(k), request(k, False)
        self.assertEqual(labels(on)['take lettuce'], labels(off)['take lettuce'] + f' (Result: {name} gives lettuce again)')

    def test_options_without_a_result_are_unchanged_and_the_round_is_untouched(self):
        for k in (kitchen(1), kitchen(4), cooked_pan()):
            before = json.dumps(k.snapshot(), sort_keys=True, default=str)
            on, off = request(k), request(k, False)
            self.assertEqual(json.dumps(k.snapshot(), sort_keys=True, default=str), before)
            self.assertEqual(on['state'].pop('option_effects_version'), option_effects.VERSION)
            self.assertEqual(on['state']['rules'].pop('effects'), option_effects.RULE)
            for key, label in labels(on).items():
                plain = labels(off)[key]
                self.assertTrue(label == plain or (label.startswith(plain + ' (Result: ') and label.endswith(')')), label)
            labels(on).update(labels(off))
            self.assertEqual(json.dumps(on), json.dumps(off))
        self.assertEqual(sum(label != labels(request(kitchen(1), False))[key]
                             for key, label in labels(request(kitchen(1))).items()), 0)

    def test_the_switch_is_a_trial_off_by_default(self):
        self.assertEqual(features.current()['option_effects'],
                         {'stage': 'trial', 'on': False, 'player_switch': False, 'version': option_effects.VERSION})
        self.assertFalse(features.compose_options(features.current())['effects'])
        on = {**features.current(), 'option_effects': {**features.current()['option_effects'], 'on': True}}
        self.assertTrue(features.compose_options(on)['effects'])


class OptionEffectsReplayTests(paths.SavePathTests):
    def test_a_round_with_the_notes_replays_exactly(self):
        # The decision loop computes the notes in its links thread on a fork; research replay in compose_payload.
        with self.game.lock:
            self.game.features = {**self.game.features,
                                  'option_effects': {**self.game.features['option_effects'], 'on': True}}
        import levels
        with patch.object(levels, 'switches', lambda: {'level-4': True}):
            status, data = self.request('/api/level', {'game_id': self.game.game_id, 'request_id': uuid.uuid4().hex, 'level': 4}, self.token)
        self.assertEqual(status, 200, data)
        receipt = self.play()
        self.natural_end()
        self.assertEqual(self.contribute()[0], 200)
        record = self.game.store.download(receipt['id'], receipt['deletion_token'])
        validate_record(record)
        self.assertEqual(record['conditions']['features']['option_effects'], {'on': True, 'version': option_effects.VERSION})
        rows = list(research_replay.rebuild_requests(record))
        self.assertTrue(rows)
        self.assertEqual({row['status'] for row in rows}, {'verified'})
        self.assertTrue(all(row['rebuilt']['state']['option_effects_version'] == option_effects.VERSION for row in rows))
        record['conditions']['features']['option_effects']['on'] = False
        self.assertEqual({row['status'] for row in research_replay.rebuild_requests(record)}, {'diverged'})


# Only the case above; the inherited ones already run in their own module.
for _name in dir(paths.SavePathTests):
    if _name.startswith('test_'):
        setattr(OptionEffectsReplayTests, _name, None)


if __name__ == '__main__':
    unittest.main()
