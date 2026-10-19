"""Page-side geometry that must hold for any layout: the local walk never starts inside a counter
(KitchenGeometry.walkStart), and food on the floor draws in front of the cabinets one row up (floorItemDepth)."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from kitchen import load_config
from levels import level_config
from spatial_kitchen import SpatialKitchen
import test_visual_geometry as geometry_tests
from test_visual_geometry import ROOT, TYPESCRIPT

RUNNER = r'''const g=require(process.argv[2]),fs=require('fs');const out={};
for(const {level,map} of JSON.parse(fs.readFileSync(process.argv[3],'utf8'))){
  const tick=(map.walk_speed||4.5)*.05,dirs=[];
  for(let i=0;i<16;i++)dirs.push([Math.cos(i*Math.PI/8),Math.sin(i*Math.PI/8)]);
  let cut=0,stuck=0,checked=0;
  // Every walkable point on a fine grid, every direction: draw between this tick and the next one.
  for(let x=0;x<map.width;x+=.05)for(let y=0;y<map.height;y+=.05){
    if(!g.footWalkable(map,x,y))continue;
    for(const [dx,dy] of dirs){
      const at=[x,y],next=g.predictWalk(map,at,dx*tick,dy*tick,undefined,tick);
      for(const f of [.25,.5,.75]){
        const drawn=[at[0]+(next[0]-at[0])*f,at[1]+(next[1]-at[1])*f];checked++;
        if(g.footWalkable(map,drawn[0],drawn[1]))continue;
        cut++;
        const from=g.walkStart(map,drawn,at);
        if(!g.footWalkable(map,from[0],from[1])||!dirs.some(([ex,ey])=>{const p=g.predictWalk(map,from,ex*tick,ey*tick,undefined,tick);return Math.hypot(p[0]-from[0],p[1]-from[1])>1e-6;}))stuck++;
      }
    }
  }
  out[level]={cut,stuck,checked};
}
// The reported spot: level 2, sliding left along the board-2 notch.
const map2=JSON.parse(fs.readFileSync(process.argv[3],'utf8')).find(m=>m.level===2).map;
const drawn=[6.151,6.3025];
out.notch={drawnWalkable:g.footWalkable(map2,...drawn),
  fromDrawn:g.predictWalk(map2,drawn,-.225,0,undefined,.225),
  fromStart:g.predictWalk(map2,g.walkStart(map2,drawn,[6.162,6.3]),-.225,0,undefined,.225)};
// Food on the floor, anywhere on a floor tile, against every cabinet/wall around it and every chef that could overlap it.
const depth=[];
for(const {level,map} of JSON.parse(fs.readFileSync(process.argv[3],'utf8'))){
  const solid=new Set((map.walls||[]).map(w=>w.join(',')));
  for(const e of Object.values(map.equipment))for(const c of (e.cells||[e.cell]))solid.add(c.join(','));
  for(let x=0;x<map.width;x++)for(let y=0;y<map.height;y++){
    if(solid.has(x+','+y))continue;
    for(const oy of [-.4,-.2,0,.2,.4]){
      const d=g.floorItemDepth(y+oy);
      for(const dx of [-1,0,1]){
        // The row above hangs its front panel (and its contents, +.01) into this tile: draw in front.
        if(solid.has((x+dx)+','+(y-1))&&!(d>g.depthOrder(y-1,'solid')+.01))depth.push({level,x,y:y+oy,problem:'under the cabinet behind'});
        // Its own row and the rows below are in front of it.
        for(const ry of [y,y+1])if(solid.has((x+dx)+','+ry)&&!(d<g.depthOrder(ry,'solid')))depth.push({level,x,y:y+oy,problem:'over the cabinet in front'});
      }
      // A chef whose body could overlap it (feet less than 0.9 cells north of it, or anywhere south) stays on top.
      for(let cy=y+oy-.9;cy<=y+oy+1.5;cy+=.05)if(!(d<g.depthOrder(cy,'actor')))depth.push({level,x,y:y+oy,cy,problem:'over a chef'});
    }
  }
}
out.depth=depth.slice(0,5);out.depthProblems=depth.length;
console.log(JSON.stringify(out));'''


class ClientWalkTests(unittest.TestCase):
    def test_a_walk_never_starts_inside_a_counter(self):
        tsc = geometry_tests.KitchenGeometryExecutionTests.resolve_tsc(self)
        if not tsc or not shutil.which('node'):
            self.skipTest('TypeScript compiler or Node.js unavailable')
        with tempfile.TemporaryDirectory(prefix='client-walk-') as temp:
            out = Path(temp) / 'compiled'
            compiled = subprocess.run([*tsc, str(TYPESCRIPT), '--target', 'ES2019', '--module', 'commonjs',
                                       '--outDir', str(out), '--skipLibCheck'], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            maps = [{'level': level, 'map': SpatialKitchen(level_config(load_config(), level)).snapshot()['map']}
                    for level in (1, 2, 3)]
            data = Path(temp) / 'maps.json'
            data.write_text(json.dumps(maps))
            runner = Path(temp) / 'run.js'
            runner.write_text(RUNNER)
            result = subprocess.run(['node', str(runner), str(out / 'KitchenGeometry.js'), str(data)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            found = json.loads(result.stdout)
        # Drawing between ticks does cut corners (that is how the chef got stuck), but a walk never starts there.
        self.assertGreater(found['2']['cut'], 0)
        for level in ('1', '2', '3'):
            self.assertEqual(found[level]['stuck'], 0, found[level])
        notch = found['notch']
        self.assertFalse(notch['drawnWalkable'])
        self.assertEqual(notch['fromDrawn'], [6.151, 6.3025])
        self.assertLess(notch['fromStart'][0], 6.162 - .1)
        # Reported: a burger and a plate on the floor below a counter were half hidden by its front panel.
        self.assertEqual(found['depthProblems'], 0, found['depth'])


if __name__ == '__main__':
    unittest.main()
