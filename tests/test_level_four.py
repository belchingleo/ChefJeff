"""Level 4 (隔台协作): a row of counters splits the floor, every dish needs both chefs, and the claim that one chef
alone cannot reach the target is checked against the committed calibration report, which must be current."""
import copy
import json
import unittest
from unittest.mock import patch

import config_contract as cc
import levels
import reference_policy
from kitchen import load_config
from level_calibration import drive
from spatial_kitchen import SpatialKitchen
from scripts import decision_stats, reference_sweep


def report():
    return json.loads(reference_sweep.REPORT.read_text(encoding='utf-8'))


class LevelTests(unittest.TestCase):
    def test_level_four_is_listed_and_needs_a_pair(self):
        listed = levels.available_levels()
        self.assertEqual([entry['id'] for entry in listed], ['level-1', 'level-2', 'level-3', 'level-4'])
        self.assertEqual(listed[3]['target'], 100)
        self.assertIs(cc.Registry().level('level-4')['requires_pair'], True)
        self.assertNotIn('requires_pair', cc.Registry().level('level-3'))         # levels 1-3 do not claim it

    def test_each_part_of_the_floor_lacks_something_every_dish_needs(self):
        k = SpatialKitchen(levels.level_config(load_config(), 'level-4'))
        self.assertTrue(k.split_floor)
        self.assertNotEqual(k.floor_part[k.anchor('human')], k.floor_part[k.anchor('jeff')])
        by_part = {}
        for key, e in k.equipment.items():
            for part in {k.floor_part.get(c) for c in k.nav.neighbors(tuple(e['cell']))} - {None}:
                by_part.setdefault(part, set()).add(e['type'])
        supplies = next(p for p, types in by_part.items() if 'ingredient_source' in types)
        boards = next(p for p, types in by_part.items() if 'board' in types)
        self.assertNotEqual(supplies, boards)
        # Every dish starts with chopping (beef is chopped before the pan), and is served from the supplies' side.
        self.assertNotIn('board', by_part[supplies])
        self.assertFalse({'ingredient_source', 'serving_window', 'stove'} & by_part[boards])
        self.assertTrue({'serving_window', 'stove'} <= by_part[supplies])

    def test_one_chef_alone_serves_nothing_on_the_configured_round(self):
        for who in ('human', 'jeff'):
            k = SpatialKitchen(cc.load_level('level-4'))
            drive(k, ((who, 'solo'),), lambda k, w, r: reference_policy.choose_solo(k, w), {'human': 10, 'jeff': 10})
            self.assertEqual(k.served, 0, who)
            self.assertLess(k.money, 100)


class CalibrationReportTests(unittest.TestCase):
    def test_the_committed_report_is_current_and_no_solo_run_reaches_the_target(self):
        self.assertEqual(reference_sweep.pair_check(report()), [])
        row = next(r for r in report()['levels'] if r['level'] == 4)
        self.assertEqual((row['solo_runs_reaching_current_target'], row['runs_reaching_current_target'], len(row['runs'])), (0, 21, 21))

    def test_a_stale_or_wrong_report_fails(self):
        def problems(change):
            data = report()
            change(next(r for r in data['levels'] if r['level'] == 4), data)
            return reference_sweep.pair_check(data)
        self.assertIn('another configuration', ' '.join(problems(lambda row, _: row.update(config_hash='sha256:0'))))
        self.assertIn('run set', ' '.join(problems(lambda _, data: data['run_set'].update(version='calibration-v1'))))
        self.assertIn('solo runs reach', ' '.join(problems(lambda row, _: row['runs'][0].update(solo=100))))
        self.assertIn('no calibration entry', ' '.join(problems(lambda row, _: row.update(level=40))))
        # The level changed after the report (here its target): its configuration hash no longer matches.
        load = cc.load_level

        def changed(level_id, registry=None, *a, **k):
            resolved = copy.deepcopy(load(level_id, registry, *a, **k))
            resolved['level']['goal']['min_money'] += 10
            return cc.freeze_config({**{key: v for key, v in resolved.items() if key != 'config_hash'}, 'status': 'draft'})[0]
        with patch.object(cc, 'load_level', changed):
            self.assertIn('another configuration', ' '.join(reference_sweep.pair_check(report())))


class CooperationGainTests(unittest.TestCase):
    def rows(self, config_hash, money):
        return [{'kind': 'start', 'game_time_ms': 0, 'config_hash': config_hash},
                {'kind': 'ai_request', 'request_id': 1, 'game_time_ms': 1000, 'candidates': ['wait']},
                {'kind': 'ai_response', 'request_id': 1, 'game_time_ms': 1500, 'model': 'm', 'choice': 'wait',
                 'applied': True, 'fresh': True},
                {'kind': 'end', 'game_time_ms': 180000,
                 'round_summary': {'level_id': 'level-4', 'result': {'money': money, 'reached_target': money >= 100}}}]

    def test_net_revenue_minus_the_solo_scripts_median_on_the_same_configuration(self):
        solo = next(r for r in report()['levels'] if r['level'] == 4)
        baseline = sorted(run['solo'] for run in solo['runs'])[10]
        models = decision_stats.defaultdict(decision_stats.new_model)
        decision_stats.add_round(self.rows(cc.load_level('level-4')['config_hash'], 150), models)
        decision_stats.add_round(self.rows('sha256:not-calibrated', 150), models)
        gain = decision_stats.summary(models['m'])['outcomes']['cooperation_gain']
        self.assertEqual(gain, {'baseline': 'relative to the solo script baseline', 'rounds': 1, 'per_round': [150 - baseline],
                                'mean': 150 - baseline, 'rounds_without_baseline': 1})


if __name__ == '__main__':
    unittest.main()
