"""scripts/audit_map.py: a map built from station coordinates is checked end to end before anyone plays it."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from map_definition import build_map
from test_visual_geometry import ROOT

sys.path.insert(0, str(ROOT / 'scripts'))
import audit_map  # noqa: E402

# Level 2's stations around four pillars of counters, one of them a two-cell vertical island (7,3)-(7,4).
PILLARS = {'name': 'pillars', 'size': [13, 9], 'stations': [
    ['fridge', 2, 1, 'south'], ['lettuce', 3, 1, 'south'], ['tomato', 4, 1, 'south'], ['bread', 5, 1, 'south'],
    ['p1', 8, 1, 'south'], ['c1', 9, 1, 'south'], ['c2', 11, 3, 'west'], ['serve', 11, 4, 'west'],
    ['sink', 11, 6, 'west'], ['b1', 3, 7, 'north'], ['b2', 5, 7, 'north'], ['plates', 7, 7, 'north'],
    ['bin', 9, 7, 'north'], ['extinguisher', 1, 3, 'east'], ['returns', 1, 5, 'east'], ['c3', 4, 4, 'south'],
    ['c4', 7, 3, 'west'], ['c5', 7, 4, 'east'], ['c6', 9, 5, 'north']]}


class MapAuditTests(unittest.TestCase):
    def test_a_coordinate_layout_is_playable_end_to_end(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'pillars.json'
            path.write_text(json.dumps(PILLARS))
            [document] = audit_map.load_maps(path)
        report = audit_map.audit(document, 'level-2', seeds=(1,))
        self.assertEqual((report['failures'], report['space_misses'], report['engine_stuck'], report['corridors']), ([], [], [], []))
        # The level places its inventory by type, so level 2 runs on a map with none of its counter IDs.
        self.assertTrue(report['config_hash'].startswith('sha256:'))
        if report['page'] is not None:
            self.assertEqual((report["page"]["off"], report["page"]["stuck"], report["page"]["depthProblems"]), (0, 0, 0))
        self.assertGreater(report['play'][0]['pair_served'], 0)
        self.assertIn('result   PASS', audit_map.summary(report))

    def test_a_too_narrow_corridor_that_is_the_only_route_is_a_warning(self):
        # A galley: counter rows at y=1 and y=3 leave one-cell lanes at y=2 and y=4, the only ways to the
        # fridge's end and to the last counter's front. y=2 runs behind the y=3 row, which is walked up to,
        # so two chefs pass there; y=4 runs between counter fronts and the wall, too narrow to pass.
        stations = [('fridge', 1, 1, 'south'), ('c1', 2, 1, 'south'), ('c2', 3, 1, 'south'), ('c3', 4, 1, 'south'),
                    ('c4', 1, 3, 'south'), ('c5', 2, 3, 'south'), ('c6', 3, 3, 'south'), ('c7', 4, 3, 'south'), ('c8', 6, 1, 'south')]
        found = audit_map.corridors(build_map('galley', [8, 6], stations))
        self.assertEqual(found, [{'cells': [[2, 4], [3, 4], [4, 4]], 'stations_each_side': [5, 1]}])
        # A room two cells wide has no such corridor.
        self.assertEqual(audit_map.corridors(build_map('room', [8, 6], stations[:4])), [])

    def test_maps_that_do_not_load_fail_with_the_reason(self):
        invalid = build_map('open', [8, 6], [('c1', 2, 1, 'south')])
        invalid['walls'].pop()
        self.assertIn('invalid map', audit_map.audit(invalid)['failures'][0])
        # Valid geometry, but level 2 needs a serving window, sink, ... and the counter has no plate room.
        report = audit_map.audit(build_map('bare', [8, 6], [('c1', 2, 1, 'south')]))
        self.assertIn('level-2 does not freeze on this map', report['failures'][0])
        self.assertIn('UNSUPPORTED_EQUIPMENT_COUNT', report['failures'][0])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'bare.json'
            path.write_text(json.dumps({'name': 'bare', 'size': [8, 6], 'stations': [['c1', 2, 1, 'south']]}))
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(audit_map.main([str(path)]), 1)
        self.assertIn('result   FAIL', printed.getvalue())


if __name__ == '__main__':
    unittest.main()
