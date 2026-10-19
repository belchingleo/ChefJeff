"""The page's Space station pick (KitchenGeometry.selectableStations) matches the engine's."""
import json
import math
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile
import unittest

from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
import test_visual_geometry as geometry_tests
from test_visual_geometry import ROOT, TYPESCRIPT


def cases():
    """Every level, positions all over the walkable floor, aims in sixteen directions."""
    rng, out = random.Random(7), []
    for level in (1, 2, 3):
        k = SpatialKitchen(level_config(load_config() | {'spawn_seed': 0, 'order_seed': 1}, level))
        rows = []
        while len(rows) < 600:
            cell = rng.choice(sorted(k.floor))
            pos = (cell[0] + rng.uniform(-.5, .5), cell[1] + rng.uniform(-.5, .5))
            if not k.nav.walkable_point(pos):
                continue
            angle = rng.randrange(16) * math.pi / 8
            aim = (round(math.cos(angle), 6), round(math.sin(angle), 6))
            k.positions['human'] = pos
            k.face('human', *aim)
            rows.append([list(pos), list(aim), k.selectable_stations('human')])
        out.append({'level': level, 'map': k.snapshot()['map'], 'rows': rows})
    return out


class SelectionParityTests(unittest.TestCase):
    def test_page_and_engine_pick_the_same_station(self):
        tsc = geometry_tests.KitchenGeometryExecutionTests.resolve_tsc(self)
        if not tsc or not shutil.which('node'):
            self.skipTest('TypeScript compiler or Node.js unavailable')
        with tempfile.TemporaryDirectory(prefix='selection-parity-') as temp:
            out = Path(temp) / 'compiled'
            compiled = subprocess.run([*tsc, str(TYPESCRIPT), '--target', 'ES2019', '--module', 'commonjs',
                                       '--outDir', str(out), '--skipLibCheck'], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            data = Path(temp) / 'cases.json'
            data.write_text(json.dumps(cases()))
            runner = Path(temp) / 'run.js'
            runner.write_text('''const g=require(process.argv[2]),fs=require('fs');let bad=[];
for(const {level,map,rows} of JSON.parse(fs.readFileSync(process.argv[3],'utf8')))
  for(const [pos,aim,want] of rows){const got=g.selectableStations(map,pos,aim);
    if(JSON.stringify(got)!==JSON.stringify(want))bad.push({level,pos,aim,want,got});}
console.log(JSON.stringify(bad.slice(0,5)));process.exit(bad.length?1:0);''')
            result = subprocess.run(['node', str(runner), str(out / 'KitchenGeometry.js'), str(data)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_release_build_does_not_drop_iterator_spreads(self):
        # Cocos's release Babel runs in loose mode: [...map.entries()] becomes
        # [].concat(iterator) and silently stops spreading, so use Array.from.
        scripts = TYPESCRIPT.parent
        spread = re.compile(r'\[\.\.\.(?!Object\.)[\w.]*(?:\.(?:entries|keys|values)\(\)|this\.seen)\]')
        for path in sorted(scripts.glob('*.ts')):
            self.assertIsNone(spread.search(path.read_text()), path.name)
        tsc = geometry_tests.KitchenGeometryExecutionTests.resolve_tsc(self)
        if not tsc:
            self.skipTest('TypeScript compiler unavailable')
        checked = subprocess.run([*tsc, str(TYPESCRIPT), '--target', 'ES5', '--lib', 'es2019,dom', '--noEmit',
                                  '--skipLibCheck'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)


if __name__ == '__main__':
    unittest.main()
