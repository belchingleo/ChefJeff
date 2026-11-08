"""food_names (names-v1): every food Jeff is told about is named from its ingredient and state, for every ingredient
a level can use, and nothing changes with the switch off."""
import json
import re
import unittest
from unittest.mock import patch

import config_contract as cc
import features
import food_names
import harness
import level_calibration as lc
import level_design
import payload_fingerprint as pf
from jev import compose_payload
from kitchen import Food, load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient

# Every ingredient the release has, in four dishes a player could build (the editor allows four of up to four).
EVERY = {
    'format': level_design.FORMAT, 'name': '全部食材', 'size': [16, 10], 'walls': [],
    'stations': (
        [{'type': 'ingredient_source', 'x': x, 'y': 1, 'item': item} for x, item in enumerate(
            ('beef', 'lettuce', 'tomato', 'bread', 'chicken', 'cucumber', 'onion', 'cheese', 'fish', 'scallion', 'flatbread',
             'noodles'), 2)]
        + [{'type': 'stove', 'x': 1, 'y': 3, 'vessel': 'pan'}, {'type': 'stove', 'x': 1, 'y': 4, 'vessel': 'pot'},
           {'type': 'serving_window', 'x': 14, 'y': 4}, {'type': 'sink', 'x': 14, 'y': 6},
           {'type': 'plate_return', 'x': 14, 'y': 7}, {'type': 'tool_rack', 'x': 1, 'y': 8}, {'type': 'bin', 'x': 1, 'y': 6}]
        + [{'type': 'board', 'x': x, 'y': 8} for x in (3, 4)]
        + [{'type': 'counter', 'x': x, 'y': 5} for x in range(5, 11)]),
    'dishes': [{'name': '汉堡', 'price': 80, 'items': ['bread', 'lettuce', 'tomato', 'beef']},
               {'name': '鸡肉卷', 'price': 90, 'items': ['chicken', 'cucumber', 'onion', 'cheese']},
               {'name': '鱼饼', 'price': 80, 'items': ['fish', 'scallion', 'flatbread']},
               {'name': '面条', 'price': 60, 'items': ['noodles']}],
}
CJK = re.compile(r'[㐀-鿿]')
# Known before this switch and outside it: on a player level the extinguisher rack is not named 灭火器架, so its take
# label is not in the translation catalog and reaches Jeff half in Chinese. Any other Chinese fails these tests.
KNOWN_UNTRANSLATED = {'take extinguisher'}


def kitchen():
    level, problems = level_design.bundle(EVERY)
    assert not problems, problems
    return SpatialKitchen(lc.finalize(level, {'playable': True, 'target': 100}))


def ask(k, names=True):
    client = SpatialJevClient(k.c, key='food-names-test')
    return compose_payload(client, k, k.snapshot(), k.actions('jeff'), [], None, names=names)


class NamesTests(unittest.TestCase):
    def setUp(self):
        self.k = kitchen()
        self.items = {item: entry for item, entry in self.k.rules.items.items()}

    def check_payload(self, payload):
        criteria = payload['questions']['next_action']['criteria']
        text = json.dumps({**payload, 'questions': {**payload['questions'], 'next_action': {
            **payload['questions']['next_action'], 'criteria': {k: v for k, v in criteria.items() if k not in KNOWN_UNTRANSLATED}}}},
            ensure_ascii=False)
        self.assertIsNone(CJK.search(text), CJK.search(text) and text[CJK.search(text).start() - 80:][:160])
        self.assertNotIn(food_names.OPEN, text)
        self.assertNotIn(food_names.CLOSE, text)
        self.assertEqual(payload['state']['food_names_version'], food_names.VERSION)
        return payload

    def test_the_known_untranslated_label_is_still_the_only_one(self):
        # When the catalog learns it, drop it from KNOWN_UNTRANSLATED.
        criteria = ask(self.k)['questions']['next_action']['criteria']
        self.assertEqual({k for k, v in criteria.items() if CJK.search(v)}, KNOWN_UNTRANSLATED)

    def test_the_kitchen_uses_every_ingredient(self):
        self.assertEqual(set(self.k.ingredients.values()), set(cc.level_bundle('level-1', embed=True)['recipe_catalog']['items']))

    def test_every_source_says_what_it_supplies_and_its_fetch_names_it(self):
        payload = self.check_payload(ask(self.k))
        stations, criteria = payload['state']['kitchen']['stations'], payload['questions']['next_action']['criteria']
        for source, item in self.k.ingredients.items():
            self.assertEqual(stations[source]['supplies'], item)
            key = next(a.key for a in self.k.actions('jeff') if a.kind == 'fetch' and a.target == source)
            self.assertEqual(criteria[key], f'Fetch {item} (as fetched)')

    def test_every_ingredient_in_every_state_is_named_on_a_counter_and_in_hand(self):
        counter = self.k.counters[-1]
        for item, entry in self.items.items():
            for stage in entry['states']:
                with self.subTest(item=item, stage=stage):
                    name = f'{item} ({food_names.WORDS[stage]})'
                    self.k.stations[counter].food = Food('F900', stage, ingredient=item)
                    self.k.chefs['jeff'].hand = None
                    payload = self.check_payload(ask(self.k))
                    self.assertEqual(payload['state']['kitchen']['stations'][counter]['food']['meaning'], name)
                    labels = [label for key, label in payload['questions']['next_action']['criteria'].items()
                              if key.endswith(' ' + counter) or key.endswith(' F900')]
                    self.assertTrue(labels and all(name in label for label in labels if 'F900' in label or 'Take' in label), labels)
                    self.k.stations[counter].food = None
                    self.k.chefs['jeff'].hand = Food('F901', stage, ingredient=item)
                    payload = self.check_payload(ask(self.k))
                    self.assertEqual(payload['state']['kitchen']['chefs']['jeff']['holding']['meaning'], name)
                    for label in payload['questions']['next_action']['criteria'].values():
                        if 'held' in label and 'put_where' in label:
                            self.assertIn(f'Put the held {name} where', label)
        self.k.chefs['jeff'].hand = None

    def test_cooking_vessels_are_named_by_kind_and_contents(self):
        stoves = {self.k.rules.vessels[self.k.stations[s].pot_id]: s for s in self.k.pots}
        for item, step in self.k.rules.heat.items():
            vessel = step['container']
            for stage in ('cooking', 'ready', 'burnt'):
                if stage not in self.items[item]['states']:
                    continue
                with self.subTest(item=item, stage=stage):
                    stove = stoves[vessel]
                    self.k.stations[stove].food = Food('F902', stage, ingredient=item)
                    payload = self.check_payload(ask(self.k))
                    self.assertEqual(payload['state']['kitchen']['stations'][stove]['food']['meaning'],
                                     f'{item} ({food_names.WORDS[stage]})')
                    self.k.stations[stove].food = None
                    pot = Food(self.k.stations[stove].pot_id, 'pot', contents=Food('F903', stage, ingredient=item))
                    self.k.chefs['jeff'].hand = pot
                    held = self.check_payload(ask(self.k))['state']['kitchen']['chefs']['jeff']['holding']
                    kind = 'frying pan' if vessel == 'pan' else 'soup pot'
                    self.assertEqual(held['meaning'], f'{kind} with {item} ({food_names.WORDS[stage]})')
                    self.k.chefs['jeff'].hand = Food(pot.id, 'pot')
                    held = self.check_payload(ask(self.k))['state']['kitchen']['chefs']['jeff']['holding']
                    self.assertEqual(held['meaning'], f'empty {kind}')
                    self.k.chefs['jeff'].hand = None

    def test_plates_are_named_by_their_dish_or_their_components(self):
        counter = self.k.counters[-1]
        menu = {d['id']: d for d in self.k.snapshot()['menu']}
        for dish, parts in self.k.rules.recipe_parts.items():
            if dish not in menu:
                continue
            with self.subTest(dish=dish):
                parts = tuple(sorted(parts))
                self.k.stations[counter].food = Food('F904', 'ready', ingredient='dish', plate_id='D9', components=parts)
                payload = self.check_payload(ask(self.k))
                named = payload['state']['kitchen']['stations'][counter]['food']
                self.assertEqual(named['dish'], dish)
                self.assertEqual(named['meaning'], next(d['name'] for d in payload['state']['kitchen']['menu'] if d['id'] == dish))
                self.assertIn(f'Take {named["meaning"]} from', payload['questions']['next_action']['criteria'][f'take {counter}'])
                if len(parts) > 1:
                    self.k.stations[counter].food = Food('F905', 'assembled', ingredient='dish', plate_id='D9', components=parts[:1])
                    named = self.check_payload(ask(self.k))['state']['kitchen']['stations'][counter]['food']
                    self.assertEqual(named['meaning'], f'plate with {parts[0]}')
        self.k.stations[counter].food = None

    def test_the_words_are_the_recipes_words(self):
        self.assertEqual({k: v for k, v in food_names.WORDS.items() if k in harness.STATE_WORDS}, harness.STATE_WORDS)
        self.assertLessEqual({s for entry in self.items.values() for s in entry['states']}, set(food_names.WORDS))


class SwitchTests(unittest.TestCase):
    def test_off_by_default_and_off_changes_nothing(self):
        self.assertEqual(features.current()['food_names'], {'stage': 'trial', 'on': False, 'player_switch': False,
                                                            'version': food_names.VERSION})
        k = SpatialKitchen(level_config(load_config(), 'level-2'))
        k.stations['b1'].food = Food('F50', 'chopped', ingredient='beef')
        plain = ask(k, names=False)
        self.assertNotIn('food_names_version', plain['state'])
        self.assertEqual(plain['state']['kitchen']['stations']['b1']['food']['meaning'], 'Chopped')    # today's name
        self.assertEqual(plain['questions']['next_action']['criteria']['fetch'], 'Take raw meat from the fridge')
        named = ask(k)
        self.assertEqual(named['state']['kitchen']['stations']['b1']['food']['meaning'], 'beef (chopped)')
        self.assertEqual(set(named['questions']['next_action']['criteria']), set(plain['questions']['next_action']['criteria']))
        self.assertFalse(food_names.NAMING.get())                     # naming mode ends with the request
        self.assertEqual([a.label for a in k.actions('jeff')][:3], [a.label for a in k.actions('jeff')][:3])
        self.assertTrue(CJK.search(next(a.label for a in k.actions('jeff') if a.key == 'fetch')))   # the page keeps Chinese

    def test_the_fingerprint_round_with_the_switch_on_is_the_same_round(self):
        named = json.loads((pf.GOLDEN / 'level2-food-names.json').read_text())
        plain = json.loads((pf.GOLDEN / 'level2.json').read_text())
        self.assertEqual(named['result'], plain['result'])
        self.assertEqual(len(named['requests']), len(plain['requests']))

    def test_names_reach_the_compact_static_part(self):
        import wire_format
        k = kitchen()
        static, live = wire_format.split(ask(k)['state'])
        self.assertTrue(all('supplies' in static['kitchen']['stations'][s] for s in k.ingredients))
        self.assertEqual(static['food_names_version'], food_names.VERSION)
        self.assertEqual(json.dumps(wire_format.expand(static, live), sort_keys=True), json.dumps(ask(k)['state'], sort_keys=True))


if __name__ == '__main__':
    unittest.main()


class CheckTests(unittest.TestCase):
    """scripts/food_names_check.py on a real offline round: a stand-in Jeff that only waits, on level 2."""

    @classmethod
    def setUpClass(cls):
        import os
        import tempfile
        from scripts import model_rounds
        from test_decision_stats import Inline
        from test_model_rounds import Clock

        class Waiter(SpatialJevClient):
            def __init__(self, config):
                super().__init__(config, key='food-names-check-test')

            def ask(self, payload):
                return {'choice': 'wait', 'sprint': False, 'sprint_answer': {}, 'confidence': None, 'probabilities': {},
                        'model': 'stand-in', 'usage': {}, 'latency': .5}
        cls.folder = tempfile.TemporaryDirectory()
        clock = Clock()
        with patch.dict(os.environ, {'CHEFJEFF_LOG_DIR': cls.folder.name}), patch('jev.time.monotonic', clock), \
                patch('jev.threading.Thread', Inline):
            cls.result = model_rounds.play_round('level-2', Waiter, 'assembler', 40, clock=clock, wait=clock.wait)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_wait_moments_are_rebuilt_exactly_and_named_as_the_game_names_them(self):
        from scripts import food_names_check as check
        found, counts = check.moments([self.folder.name])
        self.assertEqual(counts.get('not_rebuilt', 0), 0)
        self.assertGreater(len(found), 3)
        for item in found:
            self.assertEqual(item['logged_choice'], 'wait')
            self.assertIn('fetch', item['fetching'])                     # beef is nowhere: the fridge is offered
            self.assertEqual(item['named']['state']['food_names_version'], food_names.VERSION)
            self.assertNotIn('food_names_version', item['payload']['state'])
            self.assertEqual(item['named']['questions']['next_action']['criteria']['fetch'], 'Fetch beef (as fetched)')
            self.assertEqual(set(item['named']['questions']['next_action']['criteria']),
                             set(item['payload']['questions']['next_action']['criteria']))

    def test_the_report_counts_fetches_and_the_probability_moved_onto_them(self):
        from scripts import food_names_check as check
        found, _ = check.moments([self.folder.name])
        items = found[:2]

        def ask(payload):
            named = 'food_names_version' in payload['state']
            return {'choice': 'fetch' if named else 'wait', 'model': 'm',
                    'probabilities': {'fetch': .7, 'wait': .3} if named else {'fetch': .2, 'wait': .8}}
        report = check.run(items, ask)
        self.assertEqual((report['arms']['as_logged']['fetched_missing'], report['arms']['food_names']['fetched_missing']), (0, 1))
        self.assertEqual(report['arms']['food_names']['fetch_probability_change']['mean'], .5)
        self.assertNotIn('payload', json.dumps(report))
