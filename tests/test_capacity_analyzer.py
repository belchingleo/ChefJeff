"""Capacity Analyzer v0.1: bounds, loads, coverage and boundaries."""
import copy
import json
import unittest
from pathlib import Path

import capacity_analyzer as ca
import config_contract as cc

REPORTS = Path(ca.__file__).resolve().parent / 'docs' / 'architecture' / 'reports'
SAMPLES = ('level-1', 'level-2', 'level-3')


def frozen(level_id='level-1', seeds=(1, 0), **edits):
    bundle = cc.level_bundle(level_id, embed=True)
    bundle['level']['seeds'] = {'orders': seeds[0], 'spawn': seeds[1]}
    for kind, edit in edits.items():
        edit(bundle[kind])
    return cc.freeze_bundle(bundle)


def codes(report, severity):
    return {d['code'] for d in report['diagnostics'] if d['severity'] == severity}


class ReportShapeTests(unittest.TestCase):
    def test_required_fields_and_honest_status(self):
        report = ca.analyze_capacity(frozen())
        for key in ('analyzer_version', 'input_config_hash', 'assumptions', 'coverage', 'dishes', 'resource_loads',
                    'I_resource_lb_game_ms', 'diagnostics', 'schema_valid', 'structurally_valid', 'analysis_status'):
            self.assertIn(key, report)
        self.assertEqual(report['analysis_status'], 'partial')
        self.assertEqual(report['coverage']['throw_and_handoff'], 'not modelled')
        self.assertIsNone(report['suggested_interval_game_ms'])
        self.assertTrue(report['suggestion_reason'])
        self.assertNotIn('playable', report)

    def test_analysis_never_changes_its_input(self):
        for value in (frozen(), cc.resolve_config(cc.level_bundle('level-3'))[0]):
            before = copy.deepcopy(value)
            ca.analyze_capacity(value)
            self.assertEqual(value, before)

    def test_deterministic_and_bound_to_the_input_hash(self):
        a, b = ca.analyze_capacity(frozen()), ca.analyze_capacity(frozen())
        self.assertEqual(a, b)
        self.assertEqual(a['input_config_hash'], frozen()['config_hash'])

    def test_sample_reports_are_current(self):
        for level in SAMPLES:
            with self.subTest(level=level):
                stored = json.loads((REPORTS / f'{level}.json').read_text())
                self.assertEqual(stored, json.loads(json.dumps(ca.analyze_capacity(frozen(level)), ensure_ascii=False)),
                                 'regenerate with: python scripts/capacity_reports.py')


class BoundTests(unittest.TestCase):
    def test_first_dish_bound_uses_shared_chopping_only_where_geometry_allows(self):
        level1 = ca.analyze_capacity(frozen('level-1'))
        self.assertEqual(level1['geometry']['shared_work_capable']['board'], ['b1', 'b3'])
        # 6 handling steps x 0.15 + chop 6 / 2 + heat 12
        self.assertEqual(level1['dishes']['steak']['first_dish_lower_bound_game_ms'], 15900)
        solo = ca.analyze_capacity(frozen('level-1'), {'shared_work': False})
        self.assertEqual(solo['dishes']['steak']['first_dish_lower_bound_game_ms'], 18900)
        level3 = ca.analyze_capacity(frozen('level-3'))
        self.assertEqual(level3['geometry']['shared_work_capable']['board'], [])  # not a defect
        self.assertEqual(level3['dishes']['steak']['first_dish_lower_bound_game_ms'], 18900)

    def test_parallel_branches_take_the_critical_path_not_the_sum(self):
        burger = ca.analyze_capacity(frozen('level-2'))['dishes']['burger']
        self.assertEqual(burger['critical_path_game_ms'], 18900)  # beef branch
        self.assertEqual(burger['chef_time_game_ms'], 20550)       # all attended work
        self.assertEqual(burger['first_dish_lower_bound_game_ms'], max(18900, 20550 // 2))

    def test_resource_loads_follow_data(self):
        base = ca.analyze_capacity(frozen('level-2'))
        self.assertEqual(base['resource_lower_bounds_game_ms']['board'], 9000)  # 3 x 6 s over 2 boards
        slower = ca.analyze_capacity(frozen('level-2', recipe_catalog=lambda r: [t.update(work_game_ms=8000)
                                                                               for t in r['transforms'] if t['operation'] == 'chop']))
        self.assertEqual(slower['resource_lower_bounds_game_ms']['board'], 12000)
        more_plates = ca.analyze_capacity(frozen('level-2', level=lambda d: d['initial_inventory'].append(
            {'object': 'plate', 'id': 'D3', 'state': 'clean', 'at': 'counter3'})))
        self.assertLess(more_plates['resource_lower_bounds_game_ms']['plate'], base['resource_lower_bounds_game_ms']['plate'])
        self.assertEqual(base['I_resource_lb_game_ms'], max(v for v in base['resource_lower_bounds_game_ms'].values()))

    def test_every_spawn_assignment_is_reported(self):
        report = ca.analyze_capacity(frozen('level-2'))
        self.assertEqual(len(report['spawns']['assignments']), 2)
        self.assertNotEqual(report['spawns']['assignments'][0], report['spawns']['assignments'][1])
        self.assertIn(report['spawns']['configured'], report['spawns']['assignments'])
        routes = report['dishes']['burger']['single_chef_walking_reference_game_ms']
        self.assertEqual(len(routes), 4)
        low, high = report['dishes']['burger']['walking_reference_range_game_ms']
        self.assertLessEqual(low, high)
        self.assertGreaterEqual(low, report['dishes']['burger']['first_dish_lower_bound_game_ms'])
        draft = cc.resolve_config(cc.level_bundle('level-2'))[0]
        self.assertIsNone(ca.analyze_capacity(draft)['spawns']['configured'])


class DiagnosticBoundaryTests(unittest.TestCase):
    def test_average_overload_is_only_a_warning(self):
        report = ca.analyze_capacity(frozen('legacy-level-3', order_policy=lambda o: o.update(interval_game_ms=3000)))
        self.assertIn('AVERAGE_OVERLOAD', codes(report, 'WARNING'))
        self.assertEqual(codes(report, 'ERROR'), set())
        self.assertTrue(report['structurally_valid'])

    def test_provably_insufficient_chef_time_is_an_error(self):
        edit_level = lambda d: (d.update(round_limit_game_ms=60000), d['goal'].update(min_money=3000))
        edit_orders = lambda o: (o.update(interval_game_ms=1000), o['patience_by_recipe'].update(burger=4000))
        report = ca.analyze_capacity(frozen('level-2', level=edit_level, order_policy=edit_orders))
        self.assertIn('GOAL_EXCEEDS_CAPACITY', codes(report, 'ERROR'))
        self.assertFalse(report['structurally_valid'])

    def test_tight_windows_warn_without_rejecting(self):
        report = ca.analyze_capacity(frozen('level-1', order_policy=lambda o: o['patience_by_recipe'].update(steak=12000)))
        self.assertIn('PATIENCE_BELOW_PROCESSING', codes(report, 'WARNING'))
        self.assertEqual(codes(report, 'ERROR'), set())


if __name__ == '__main__':
    unittest.main()
