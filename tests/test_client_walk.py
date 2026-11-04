"""Page-side geometry that must hold for any layout: the local walk (KitchenGeometry.predictWalk, stepped 60
times a game second) never leaves walkable floor and never traps the chef, and food on the floor draws in front
of the cabinets one row up (floorItemDepth). scripts/audit_map.py runs the same page checks on any new map."""
import sys
import unittest

from kitchen import load_config
import level_calibration as lc
import level_design
from levels import level_config
from spatial_kitchen import SpatialKitchen
from test_level_design import DESIGN
from test_split_kitchen import SPLIT
from test_visual_geometry import ROOT

sys.path.insert(0, str(ROOT / 'scripts'))
import audit_map  # noqa: E402


class ClientWalkTests(unittest.TestCase):
    def test_the_page_walk_stays_on_the_floor_and_never_traps(self):
        maps = {str(level): SpatialKitchen(level_config(load_config(), level)).snapshot()['map'] for level in (1, 2, 3)}
        found = audit_map.page_checks(maps)
        if found is None:
            self.skipTest('TypeScript compiler or Node.js unavailable')
        for level in maps:
            self.assertEqual((found[level]['off'], found[level]['stuck']), (0, 0), found[level])
            # Reported: a burger and a plate on the floor below a counter were half hidden by its front panel.
            self.assertEqual(found[level]['depthProblems'], 0, found[level]['depth'])

    def test_stations_set_into_the_outer_wall_keep_the_page_walk_on_the_floor(self):
        # Player kitchens: the serving window and plate return sit in the wall, one split by counters.
        maps = {}
        for name, design in (('noodles', DESIGN), ('split', SPLIT)):
            level, problems = level_design.bundle(design)
            self.assertEqual(problems, [])
            maps[name] = SpatialKitchen(lc.finalize(level, {'playable': True, 'target': 100})).snapshot()['map']
        found = audit_map.page_checks(maps)
        if found is None:
            self.skipTest('TypeScript compiler or Node.js unavailable')
        for name in maps:
            self.assertEqual((found[name]['off'], found[name]['stuck']), (0, 0), found[name])


if __name__ == '__main__':
    unittest.main()
