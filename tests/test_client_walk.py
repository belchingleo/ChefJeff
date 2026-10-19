"""Page-side geometry that must hold for any layout: the local walk never starts inside a counter
(KitchenGeometry.walkStart), and food on the floor draws in front of the cabinets one row up (floorItemDepth).
scripts/audit_map.py runs the same page checks on any new map."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
from test_visual_geometry import ROOT

sys.path.insert(0, str(ROOT / 'scripts'))
import audit_map  # noqa: E402

# The reported spot: level 2, sliding left along the board-2 notch.
NOTCH = r'''const g=require(process.argv[2]),map=JSON.parse(require('fs').readFileSync(process.argv[3],'utf8'));
const drawn=[6.151,6.3025];
console.log(JSON.stringify({drawnWalkable:g.footWalkable(map,...drawn),
  fromDrawn:g.predictWalk(map,drawn,-.225,0,undefined,.225),
  fromStart:g.predictWalk(map,g.walkStart(map,drawn,[6.162,6.3]),-.225,0,undefined,.225)}));'''


class ClientWalkTests(unittest.TestCase):
    def test_a_walk_never_starts_inside_a_counter(self):
        maps = {str(level): SpatialKitchen(level_config(load_config(), level)).snapshot()['map'] for level in (1, 2, 3)}
        with tempfile.TemporaryDirectory(prefix='client-walk-') as temp:
            geometry = audit_map.compile_geometry(temp)
            if geometry is None:
                self.skipTest('TypeScript compiler or Node.js unavailable')
            data, runner = Path(temp) / 'map.json', Path(temp) / 'notch.js'
            data.write_text(json.dumps(maps['2']))
            runner.write_text(NOTCH)
            result = subprocess.run(['node', str(runner), str(geometry), str(data)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            notch = json.loads(result.stdout)
        found = audit_map.page_checks(maps)
        # Drawing between ticks does cut corners (that is how the chef got stuck), but a walk never starts there.
        self.assertGreater(found['2']['cut'], 0)
        for level in maps:
            self.assertEqual(found[level]['stuck'], 0, found[level])
            # Reported: a burger and a plate on the floor below a counter were half hidden by its front panel.
            self.assertEqual(found[level]['depthProblems'], 0, found[level]['depth'])
        self.assertFalse(notch['drawnWalkable'])
        self.assertEqual(notch['fromDrawn'], [6.151, 6.3025])
        self.assertLess(notch['fromStart'][0], 6.162 - .1)


if __name__ == '__main__':
    unittest.main()
