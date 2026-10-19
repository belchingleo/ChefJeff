"""Page-side geometry that must hold for any layout: the local walk (KitchenGeometry.predictWalk, stepped 60
times a game second) never leaves walkable floor and never traps the chef, and food on the floor draws in front
of the cabinets one row up (floorItemDepth)."""
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
  const tick=(map.walk_speed||4.5)/60,dirs=[];
  for(let i=0;i<16;i++)dirs.push([Math.cos(i*Math.PI/8),Math.sin(i*Math.PI/8)]);
  let off=0,stuck=0,checked=0;
  // Every walkable point on a fine grid, every direction: one page step stays on walkable floor, and some
  // direction always leaves the point (the old interpolated drawing could start a walk inside a counter).
  for(let x=0;x<map.width;x+=.05)for(let y=0;y<map.height;y+=.05){
    if(!g.footWalkable(map,x,y))continue;
    let leaves=false;
    for(const [dx,dy] of dirs){
      const p=g.predictWalk(map,[x,y],dx*tick,dy*tick,undefined,tick);checked++;
      if(!g.footWalkable(map,p[0],p[1]))off++;
      if(Math.hypot(p[0]-x,p[1]-y)>1e-6)leaves=true;
    }
    if(!leaves)stuck++;
  }
  out[level]={off,stuck,checked};
}
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
    def test_the_page_walk_stays_on_the_floor_and_never_traps(self):
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
        for level in ('1', '2', '3'):
            self.assertEqual((found[level]['off'], found[level]['stuck']), (0, 0), found[level])
        # Reported: a burger and a plate on the floor below a counter were half hidden by its front panel.
        self.assertEqual(found['depthProblems'], 0, found['depth'])


if __name__ == '__main__':
    unittest.main()
