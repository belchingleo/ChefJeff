"""Counters may split a kitchen in two (walls may not): one chef works each part and food is thrown across."""
import copy
import unittest

import config_contract as cc
import level_calibration as lc
import level_design
from level_calibration import drive
from map_definition import build_map
import reference_policy
from spatial_kitchen import SpatialKitchen

SPLIT = {
    'format': level_design.FORMAT, 'name': '隔开的厨房', 'size': [14, 9], 'walls': [],
    'stations': (
        [{'type': 'ingredient_source', 'x': x, 'y': 1, 'item': item} for x, item in ((2, 'beef'), (3, 'lettuce'), (4, 'tomato'), (5, 'bread'))]
        + [{'type': 'counter', 'x': 7, 'y': 1}, {'type': 'stove', 'x': 9, 'y': 1, 'vessel': 'pan'}, {'type': 'serving_window', 'x': 13, 'y': 2}]
        + [{'type': 'counter', 'x': x, 'y': 4} for x in range(1, 13)]
        + [{'type': 'board', 'x': 2, 'y': 7}, {'type': 'board', 'x': 3, 'y': 7}, {'type': 'sink', 'x': 5, 'y': 7},
           {'type': 'plate_return', 'x': 6, 'y': 8}, {'type': 'bin', 'x': 8, 'y': 7}, {'type': 'tool_rack', 'x': 10, 'y': 7},
           {'type': 'counter', 'x': 11, 'y': 7}]),
    'dishes': [{'name': '汉堡', 'price': 80, 'items': ['bread', 'lettuce', 'tomato', 'beef']}],
}


def kitchen(design=SPLIT):
    level, problems = level_design.bundle(design)
    assert not problems, problems
    return SpatialKitchen(lc.finalize(level, {'playable': True, 'target': 100}))


class MapRuleTests(unittest.TestCase):
    def test_counters_may_split_the_floor_but_walls_may_not(self):
        row = [('c%d' % x, x, 4, 'south') for x in range(1, 13)]
        build_map('split', [14, 9], row)  # counters across the room: two parts of floor
        with self.assertRaisesRegex(ValueError, 'Walls cut the kitchen in two'):
            build_map('walled', [14, 9], [], walls=[(x, 4) for x in range(1, 13)])
        with self.assertRaisesRegex(ValueError, 'more than two parts'):
            build_map('three', [14, 9], row + [('d%d' % y, 7, y, 'east') for y in (1, 2, 3)])

    def test_the_parts_must_be_close_enough_to_throw_across(self):
        # Every station needs floor in front of it, so a dividing row is at most two counters thick and the
        # release's 4-cell throw always reaches. A shorter throw shows the check.
        level = lc.paced(lc.normalize(level_design.bundle(SPLIT)[0])[0])
        self.assertEqual([d for d in cc.resolve_config(level)[1] if d['severity'] == 'ERROR'], [])
        level['ruleset']['throw']['range_cells'] = 1
        self.assertIn('FLOOR_PARTS_OUT_OF_REACH', [d['code'] for d in cc.resolve_config(level)[1]])


class EngineTests(unittest.TestCase):
    def test_one_chef_in_each_part_and_only_reachable_work_is_offered(self):
        k = kitchen()
        parts = {who: k.floor_part[k.anchor(who)] for who in k.chefs}
        self.assertEqual(len(set(parts.values())), 2)
        for who in k.chefs:
            for a in k.actions(who):
                if a.kind != 'throw':
                    self.assertTrue(k.reaches(who, a.target), (who, a.key))
        maker = next(w for w in k.chefs if k.positions[w][1] > 4)
        self.assertNotIn('serve', [a.kind for a in k.actions(maker)])
        self.assertIn('take counter2', [a.key for a in k.actions(maker)])  # a dividing counter, from below

    def test_the_scripted_pair_cooks_across_the_counters(self):
        k = kitchen()
        runner = next(w for w in k.chefs if k.positions[w][1] < 4)
        maker = 'human' if runner == 'jeff' else 'jeff'
        drive(k, ((runner, 'runner'), (maker, 'maker')), reference_policy.choose_zoned, {'human': 10, 'jeff': 10})
        self.assertGreaterEqual(k.served, 3)

    def test_the_serve_hint_points_at_the_nearest_window(self):
        design = copy.deepcopy(SPLIT)
        design['stations'].append({'type': 'serving_window', 'x': 6, 'y': 0})
        k = kitchen(design)
        runner = next(w for w in k.chefs if k.positions[w][1] < 4)
        k.positions[runner] = (6.0, 2.0)
        self.assertEqual(k.nearest_serve(runner), 'serve2')
        k.positions[runner] = (11.0, 2.0)
        self.assertEqual(k.nearest_serve(runner), 'serve')


if __name__ == '__main__':
    unittest.main()
