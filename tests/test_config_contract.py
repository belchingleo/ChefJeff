"""Configuration contract: schemas, resolver diagnostics and freezing."""
import copy
import json
import math
import random
import unittest
from pathlib import Path

import config_contract as cc
import schema_check
ROOT = Path(cc.__file__).resolve().parent


def variant(level_id='level-1', **changes):
    """In-memory copy of an authored level's documents with edits applied."""
    registry = cc.Registry()
    level = copy.deepcopy(registry.level(level_id))
    docs = {'level': level}
    for kind, field in cc.REF_FIELDS.items():
        docs[kind] = registry.get(kind, level[field])
    for kind, edit in changes.items():
        edit(docs[kind])
    bundle = {'schema_version': 1, 'level': docs['level']}
    for kind in cc.REF_FIELDS:
        bundle[kind] = docs[kind]
    return bundle


def codes(bundle):
    draft, diagnostics = cc.resolve_config(bundle)
    return draft, {d['code'] for d in diagnostics if d['severity'] == 'ERROR'}


class SchemaFileTests(unittest.TestCase):
    def test_schemas_use_only_the_supported_subset_and_resolve_refs(self):
        for path in sorted((ROOT / 'schemas').glob('*.schema.json')):
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text())
                self.assertEqual(schema['$schema'], 'https://json-schema.org/draft/2020-12/schema')
                self.assertLessEqual(schema_check.keywords_used(schema), schema_check.SUPPORTED_KEYWORDS)
                refs = []
                def walk(node):
                    if isinstance(node, dict):
                        if '$ref' in node:
                            refs.append(node['$ref'])
                        for v in node.values():
                            walk(v)
                    elif isinstance(node, list):
                        for v in node:
                            walk(v)
                walk(schema)
                for ref in refs:
                    schema_check._resolve(ref, path.name)

    def test_shipped_content_matches_its_schema(self):
        for kind, folder in cc.CONTENT_DIRS.items():
            for path in sorted(folder.glob('*.json')):
                with self.subTest(path=path.name):
                    self.assertEqual(schema_check.validate(json.loads(path.read_text()), cc.SCHEMAS[kind]), [])

    def test_validator_rejects_non_finite_booleans_and_unknown_fields(self):
        self.assertTrue(schema_check.validate({'id': 'x', 'version': True}, 'common.schema.json') == [])  # annotation-only root
        ref = {'$ref': 'common.schema.json#/$defs/ref'}
        self.assertTrue(list(schema_check.check({'id': 'x', 'version': True}, ref, 'common.schema.json')))
        self.assertTrue(list(schema_check.check({'id': 'x', 'version': 1, 'extra': 1}, ref, 'common.schema.json')))
        number = {'$ref': 'common.schema.json#/$defs/positive_number'}
        for bad in (math.nan, math.inf, 0, -1, '1'):
            self.assertTrue(list(schema_check.check(bad, number, 'common.schema.json')), bad)
        self.assertFalse(list(schema_check.check(1.5, number, 'common.schema.json')))


class MapInstanceTests(unittest.TestCase):
    def test_map_instances_keep_engine_station_order_names_and_areas(self):
        from kitchen import load_config
        from spatial_kitchen import SpatialKitchen
        areas = {'处理区': 'prep', '烹饪区': 'cook'}
        for n in (1, 2, 3):
            with self.subTest(level=n):
                resolved = cc.load_level(f'level-{n}', seeds={'orders': 1, 'spawn': 0})
                k = SpatialKitchen(load_config() | {'level_id': f'level-{n}', 'order_seed': 1, 'spawn_seed': 0})
                self.assertEqual([(s['id'], s['name'], s['area']) for s in resolved['stations']],
                                 [(key, s.name, areas[s.area]) for key, s in k.stations.items()])


class FreezeTests(unittest.TestCase):
    def test_same_inputs_same_hash_and_integrity(self):
        a = cc.load_level('level-2', seeds={'orders': 3, 'spawn': 4})
        b = cc.load_level('level-2', seeds={'orders': 3, 'spawn': 4})
        self.assertEqual(a['config_hash'], b['config_hash'])
        self.assertEqual(a['seeds']['source'], 'configured')
        self.assertEqual(cc.verify_frozen(a), [])
        tampered = copy.deepcopy(a)
        tampered['level']['round_limit_game_ms'] += 1
        self.assertIn('CONFIG_HASH_MISMATCH', {d['code'] for d in cc.verify_frozen(tampered)})
        self.assertNotEqual(a['config_hash'], cc.load_level('level-2', seeds={'orders': 5, 'spawn': 4})['config_hash'])

    def test_missing_seeds_are_drawn_and_recorded(self):
        draft, _ = cc.resolve_config(variant(level=lambda d: d.update(seeds={'orders': None, 'spawn': None})))
        frozen, _ = cc.freeze_config(draft, random.Random(9))
        self.assertEqual(frozen['seeds']['source'], 'drawn_at_freeze')
        self.assertIsInstance(frozen['seeds']['orders'], int)
        self.assertEqual(frozen['sources']['map'], {'id': 'level-1', 'version': 4, 'sha256': frozen['sources']['map']['sha256']})

    def test_freeze_does_not_change_the_draft(self):
        draft, _ = cc.resolve_config(cc.level_bundle('level-3'))
        before = copy.deepcopy(draft)
        cc.freeze_config(draft, random.Random(1))
        self.assertEqual(draft, before)
        with self.assertRaises(ValueError):
            cc.freeze_config(cc.freeze_config(draft, random.Random(1))[0])


class DiagnosticTests(unittest.TestCase):
    def test_shipped_levels_have_no_diagnostics(self):
        for n in (1, 2, 3):
            draft, diagnostics = cc.resolve_config(cc.level_bundle(f'level-{n}'))
            self.assertIsNotNone(draft)
            self.assertEqual(diagnostics, [])

    def test_every_diagnostic_has_the_required_fields(self):
        _, diagnostics = cc.resolve_config(variant(level=lambda d: d['goal'].update(min_money=10 ** 6)))
        self.assertTrue(diagnostics)
        for d in diagnostics:
            self.assertLessEqual({'code', 'severity', 'field_path', 'message'}, set(d))

    def test_reference_errors(self):
        bundle = cc.level_bundle('level-1')
        bundle['level']['map_ref'] = {'id': 'level-1', 'version': 99}
        self.assertEqual(codes(bundle)[1], {'REF_VERSION_MISMATCH'})
        bundle['level']['map_ref'] = {'id': 'no-such-map', 'version': 1}
        self.assertEqual(codes(bundle)[1], {'REF_MISSING'})
        bundle['level']['map_ref'] = {'id': '../secrets', 'version': 1}
        self.assertTrue(codes(bundle)[1])

    def test_format_errors_block_resolution(self):
        for edit in (lambda d: d.update(round_limit_game_ms=-1), lambda d: d.update(round_limit_game_ms=math.nan),
                     lambda d: d.update(surprise=True), lambda d: d['clock'].update(game_per_wall_default=0)):
            draft, found = codes(variant(level=edit))
            self.assertIsNone(draft)
            self.assertIn('SCHEMA_INVALID', found)

    def test_missing_equipment_breaks_the_production_chain(self):
        def no_boards(m):
            for e in m['equipment']:
                if e['type'] == 'board':
                    e['type'] = 'counter'
        self.assertIn('NO_PRODUCTION_CHAIN', codes(variant(map=no_boards))[1])
        def no_source(m):
            for e in m['equipment']:
                if e['id'] == 'fridge':
                    e['type'], e.pop('params')['item'] = 'counter', None
        self.assertIn('NO_PRODUCTION_CHAIN', codes(variant(map=no_source))[1])

    def test_unknown_or_unsupported_equipment(self):
        self.assertIn('MAP_UNKNOWN_EQUIPMENT_TYPE', codes(variant(map=lambda m: m['equipment'][9].update(type='microwave')))[1])
        catalog = lambda c: c['types'].update(microwave={'name': '微波炉', 'capabilities': ['heat'], 'slots': 1,
                                                         'worker_requirement': 'unattended', 'combustible': True})
        self.assertIn('UNSUPPORTED_EQUIPMENT_TYPE', codes(variant(equipment_catalog=catalog))[1])
        self.assertIn('MAP_UNKNOWN_ITEM', codes(variant(map=lambda m: m['equipment'][0]['params'].update(item='fish')))[1])

    def test_goal_that_exceeds_the_revenue_ceiling_is_an_error(self):
        _, found = codes(variant(level=lambda d: d['goal'].update(min_money=10 ** 6)))
        self.assertEqual(found, {'GOAL_EXCEEDS_REVENUE'})

    def test_inventory_rules(self):
        cases = {
            'INVENTORY_INCOMPATIBLE': lambda d: d['initial_inventory'][1].update(at='b1'),
            'INVENTORY_SLOT_CONFLICT': lambda d: d['initial_inventory'][2].update(at='plates'),
            'INVENTORY_UNKNOWN_STATION': lambda d: d['initial_inventory'][1].update(at='nowhere'),
            'INVENTORY_ID_SEQUENCE': lambda d: d['initial_inventory'][2].update(id='D7'),
            'INVENTORY_EXTINGUISHER': lambda d: d['initial_inventory'].pop(0),
        }
        for code, edit in cases.items():
            with self.subTest(code=code):
                self.assertIn(code, codes(variant(level=edit))[1])

    def test_unknown_recipe_and_mode_fields(self):
        self.assertIn('ORDER_UNKNOWN_RECIPE', codes(variant(order_policy=lambda o: o['menu'][0].update(recipe_ref='pizza')))[1])
        self.assertIn('ORDER_MODE_FIELD', codes(variant(order_policy=lambda o: o.pop('menu')))[1])

    def test_a_dish_has_at_most_the_ruleset_ingredient_limit(self):
        def fifth(r):
            r['items']['onion'] = {'name': 'Onion', 'states': ['raw'], 'initial_state': 'raw',
                                   'platable_states': ['raw'], 'throwable_states': ['raw']}
            r['recipes']['burger']['components'].append({'item': 'onion', 'state': 'raw', 'label': 'onion'})
        self.assertIn('RECIPE_TOO_MANY_COMPONENTS', codes(variant(recipe_catalog=fifth))[1])
        raised = lambda r: r['limits'].update(max_recipe_components=5)
        self.assertNotIn('RECIPE_TOO_MANY_COMPONENTS', codes(variant(recipe_catalog=fifth, ruleset=raised))[1])

    def test_burnt_service_tiers_must_ascend_and_end_open(self):
        closed = lambda r: r['burnt_service'][-1].update(max_overcook_game_ms=9000)
        self.assertIn('RULESET_BURNT_TIERS', codes(variant(ruleset=closed))[1])
        descending = lambda r: r['burnt_service'].insert(0, dict(r['burnt_service'][0], max_overcook_game_ms=10 ** 6))
        self.assertIn('RULESET_BURNT_TIERS', codes(variant(ruleset=descending))[1])


class OrderPlanTests(unittest.TestCase):
    policy = {'mode': 'fixed_interval_seeded', 'first_spawn_game_ms': 0, 'interval_game_ms': 25000,
              'stop_spawn_game_ms': 150000, 'patience_default_game_ms': 100000, 'patience_by_recipe': {'burger': 120000},
              'menu': [{'recipe_ref': 'steak', 'weight': 3}, {'recipe_ref': 'burger', 'weight': 4}]}

    def test_fixed_interval_boundaries_and_clipped_deadlines(self):
        plan = cc.order_plan(self.policy, 42, 240000, ['steak', 'burger'])
        arrivals = [o['arrival_game_ms'] for o in plan['orders']]
        self.assertEqual(arrivals, [0, 25000, 50000, 75000, 100000, 125000])  # t = stop_spawn is not generated
        for o in plan['orders']:
            self.assertEqual(o['deadline_game_ms'], min(o['arrival_game_ms'] + o['patience_game_ms'], 240000))
        self.assertEqual(plan, cc.order_plan(self.policy, 42, 240000, ['steak', 'burger']))
        self.assertEqual(plan['algorithm'], 'fixed_interval_seeded/weighted-cumulative-v1')

    def test_menu_order_in_the_document_does_not_change_sampling(self):
        swapped = dict(self.policy, menu=list(reversed(self.policy['menu'])))
        self.assertEqual(cc.order_plan(self.policy, 7, 240000, []), cc.order_plan(swapped, 7, 240000, []))

    def test_weights_shape_the_distribution(self):
        policy = dict(self.policy, stop_spawn_game_ms=25000 * 4000, interval_game_ms=25000)
        plan = cc.order_plan(policy, 1, 10 ** 9, [])
        share = sum(o['recipe_ref'] == 'burger' for o in plan['orders']) / len(plan['orders'])
        self.assertAlmostEqual(share, 4 / 7, delta=.03)


if __name__ == '__main__':
    unittest.main()


class ReleaseListTests(unittest.TestCase):
    def test_runtime_files_include_every_contract_and_content_document(self):
        from release_info import RUNTIME_FILES
        needed = {p.relative_to(ROOT).as_posix() for folder in ('schemas', 'content', 'rulesets')
                  for p in (ROOT / folder).rglob('*.json')}
        needed |= {'rules.py', 'config_contract.py', 'schema_check.py'}
        self.assertLessEqual(needed, set(RUNTIME_FILES))
