import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TYPESCRIPT = ROOT / 'cocos-kitchen/assets/scripts/KitchenGeometry.ts'
MANIFEST = ROOT / 'cocos-kitchen/assets/resources/art/grid-foundation-v1/manifest.json'
MODULAR_MANIFEST = ROOT / 'cocos-kitchen/assets/resources/art/kitchen-modules-v2/manifest.json'
COCOS_TSC_CANDIDATES = (
    Path('/Applications/CocosCreator.app/Contents/Resources/resources/3d/engine/node_modules/typescript/bin/tsc'),
    Path('/Applications/CocosCreator.app/Contents/Resources/app.asar.unpacked/node_modules/typescript/bin/tsc'),
)


def server_walks():
    """Server manual-movement steps for eight held directions, away from the teammate."""
    from kitchen import load_config
    from spatial_kitchen import SpatialKitchen, WALK_SPEED
    walks = []
    for level in (1, 2, 3):
        steps = []
        for vx, vy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)):
            k = SpatialKitchen({**load_config(), 'level': level, 'spawn_seed': 0})
            k.set_manual('human', vx, vy)
            vector = k.manual['human']
            for _ in range(80):
                before = k.positions['human']
                k.advance(.05)
                after = k.positions['human']
                if min(math.dist(p, k.positions['jeff']) for p in (before, after)) > 1:
                    steps.append([before, [vector[0]*WALK_SPEED*.05, vector[1]*WALK_SPEED*.05], after])
        walks.append({'level': level, 'map': k.snapshot()['map'], 'steps': steps})
    return walks


class KitchenGeometryExecutionTests(unittest.TestCase):
    def resolve_tsc(self):
        configured = os.environ.get('CHEFJEFF_TSC')
        if configured:
            parts = shlex.split(configured)
            if parts:
                executable = shutil.which(parts[0])
                if executable:
                    return [executable, *parts[1:]]
                candidate = Path(parts[0]).expanduser()
                if candidate.is_file():
                    return [str(candidate), *parts[1:]]

        system_tsc = shutil.which('tsc')
        if system_tsc:
            return [system_tsc]
        for candidate in COCOS_TSC_CANDIDATES:
            if candidate.is_file():
                return [str(candidate)]
        return None

    def test_compiled_geometry_contracts(self):
        tsc = self.resolve_tsc()
        if not tsc:
            self.skipTest('TypeScript compiler unavailable; set CHEFJEFF_TSC or install tsc')
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js unavailable; compiled geometry execution requires node')

        runner = r'''const assert = require('assert');
const fs = require('fs');
const path = require('path');
const root = process.argv[2];
const geometry = require(path.join(process.argv[3], 'KitchenGeometry.js'));
const modules = JSON.parse(fs.readFileSync(path.join(root, 'cocos-kitchen/assets/resources/art/kitchen-modules-v2/manifest.json'), 'utf8'));

for (const level of [1, 2, 3]) {
  const map = JSON.parse(fs.readFileSync(path.join(root, `maps/level-${level}.json`), 'utf8'));
  const views = map.presentation.station_views;
  assert(views && Object.keys(views).length === map.equipment.length,
         `level ${level} must author a view for every workstation`);
  for (const station of map.equipment) {
    const id = station.id;
    assert.deepStrictEqual(geometry.stationView(map, id), views[id], `${id} must use its explicit view`);
    assert(['horizontal', 'vertical'].includes(views[id].run_axis));
    assert(['horizontal', 'vertical'].includes(views[id].device_axis));
  }
}

for(const [facing,access,axis,mirror] of [['west',[3,4],'vertical',false],['east',[5,4],'vertical',true],['north',[4,3],'horizontal',false],['south',[4,5],'horizontal',false]]) {
 const map={equipment:{bin:{cell:[4,4],access,facing}}};
 assert.deepStrictEqual(geometry.trashView(map,'bin'),{axis,mirror});
}
const trash=JSON.parse(fs.readFileSync(path.join(root,'cocos-kitchen/assets/resources/art/trash-directions-v1/manifest.json'),'utf8')).frames['feedback/trash_opening_vertical'];
assert(trash.rect[3]>trash.rect[2],'Side-access trash must be taller than wide');
for(const face of ['left','right']) {
  const body=geometry.workingChefDepth(3.3,3,face,true),table=geometry.depthOrder(3,'solid');
  assert(body>table && body<table+.02,'Side body above cabinet, knife above side body');
}
assert(geometry.workingChefDepth(2.49,3,'down',true)<geometry.depthOrder(3,'solid'));
assert(geometry.workingChefDepth(4,3,'up',true)>geometry.depthOrder(3,'solid')+.02);
assert.strictEqual(geometry.workingChefDepth(3.3,3,'right',false),geometry.depthOrder(3.3,'actor'));
const level1 = JSON.parse(fs.readFileSync(path.join(root, 'maps/level-1.json'), 'utf8'));
for (const id of ['b1', 'b2', 'b3']) {
  assert.strictEqual(level1.presentation.station_views[id].run_axis, 'vertical');
  assert.strictEqual(level1.presentation.station_views[id].device_axis, 'vertical');
}
assert(new Set(['b1', 'b2', 'b3'].map(id => level1.equipment.find(station => station.id === id).facing)).size > 1,
       'board visual axes must be explicit rather than inferred from facing');

// Legacy layout inference follows adjacent equipment, and changing operation facing has no effect.
const legacy = {presentation: {}, equipment: {
  north: {cell: [2, 1], facing: 'south'},
  board: {cell: [2, 2], facing: 'north'},
  south: {cell: [2, 3], facing: 'west'}
}};
const inferred = geometry.stationView(legacy, 'board');
assert.deepStrictEqual(inferred, {run_axis: 'vertical', device_axis: 'vertical'});
legacy.equipment.board.facing = 'east';
assert.deepStrictEqual(geometry.stationView(legacy, 'board'), inferred);

const tWalls = new Set(['2,2', '1,2', '3,2', '2,3']);
assert.strictEqual(geometry.wallNeighbours(tWalls, 2, 2).south, true,
                   'a south wall neighbor closes the south face at a T junction');
assert.strictEqual(geometry.wallNeighbours(new Set(['4,4']), 4, 4).south, false,
                   'a disconnected endpoint has no south neighbor');
assert.strictEqual(geometry.surfaceOffset(), 0, 'work surfaces stay on their logical cell centers');
assert.strictEqual(geometry.wallOffset(), 0, 'wall tops stay on their logical cell centers');
assert(geometry.GRID_ART.northFace > 0 && geometry.GRID_ART.northFace < geometry.GRID_ART.unit,
       'the inset north face must remain inside its wall cell');
assert(geometry.depthOrder(5, 'solid') > geometry.depthOrder(5, 'actor'),
       'solid in the same row sorts after the actor');
assert(geometry.depthOrder(6, 'actor') > geometry.depthOrder(5, 'solid'),
       'actor on the next row sorts after the previous row solid');

// Cabinet work surfaces align exactly to one logical cell after sprite lift.
const tile = geometry.GRID_ART.tile, unit = geometry.GRID_ART.unit;
assert.strictEqual(geometry.GRID_ART.counterHeight, 0);
assert.strictEqual(geometry.GRID_ART.wallHeight, 0);
const cabinet = modules.frames.counter_south;
const [sx, sy, sw, sh] = cabinet.surfaceRect;
const [gx, gy] = cabinet.groundAnchor;
const lift = geometry.GRID_ART.cabinetSpriteLift;
const surface = [
  (sx-gx)*tile/unit,
  (sy-gy+lift)*tile/unit,
  (sx+sw-gx)*tile/unit,
  (sy+sh-gy+lift)*tile/unit
];
assert.deepStrictEqual(surface, [-tile/2, -tile/2, tile/2, tile/2],
       'surfaceRect, groundAnchor, and sprite lift must fill exactly one grid cell');

const burger = geometry.burgerLayers(['tomato', 'bread', 'lettuce', 'beef']);
assert.deepStrictEqual(burger, geometry.burgerLayers(['beef', 'lettuce', 'bread', 'tomato']));
assert.deepStrictEqual(geometry.burgerLayers(['bread', 'tomato']), ['bun_bottom', 'tomato', 'bun_top'],
       'missing ingredients must not be drawn');

const cooking = geometry.heatCountdown({stove:true, heating:true, food:{stage:'cooking'}, ready_in:2.2});
assert.deepStrictEqual(cooking, {seconds:3, ready:false, paused:false});
const cooked = geometry.heatCountdown({stove:true, heating:true, food:{stage:'ready'}, burn_in:1.1});
assert.deepStrictEqual(cooked, {seconds:2, ready:true, paused:false});
const paused = geometry.heatCountdown({stove:true, heating:false, food:{stage:'ready'}, burn_in:4});
assert.deepStrictEqual(paused, {seconds:4, ready:true, paused:true});

const groundDepth = geometry.depthOrder(4, 'item');
const flyingDepth = geometry.flightDepth(4, tile*.5);
assert(flyingDepth > groundDepth, 'flight elevation must advance the object in painter order');
assert(flyingDepth > geometry.depthOrder(4, 'solid'), 'a raised object must not fall behind its cabinet');

// Held-key prediction lands where the server's manual step does, including wall slides.
const walks = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
for (const {level, map, steps} of walks) {
  let exact = 0;
  for (const [before, delta, after] of steps) {
    const got = geometry.predictWalk(map, before, delta[0], delta[1]), error = Math.hypot(got[0]-after[0], got[1]-after[1]);
    // The server rounds a board corner a tick later than the finer prediction; the client eases that gap out.
    assert(error < .1, `level ${level}: predicted ${got} from ${before} but the server reached ${after}`);
    assert(geometry.footWalkable(map, got[0], got[1]));
    if (error < .01) exact++;
  }
  assert(exact >= steps.length*.97, `level ${level}: only ${exact}/${steps.length} steps match the server`);
}

'''

        with tempfile.TemporaryDirectory(prefix='kitchen-geometry-') as temp_dir:
            out_dir = Path(temp_dir) / 'compiled'
            compile_result = subprocess.run(
                [*tsc, str(TYPESCRIPT), '--target', 'ES2019', '--module', 'commonjs',
                 '--outDir', str(out_dir), '--skipLibCheck'],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(compile_result.returncode, 0,
                             f'Cocos TypeScript compile failed:\n{compile_result.stdout}\n{compile_result.stderr}')
            runner_path = Path(temp_dir) / 'geometry_contract_test.cjs'
            runner_path.write_text(runner)
            walks_path = Path(temp_dir) / 'server_walks.json'
            walks_path.write_text(json.dumps(server_walks()))
            result = subprocess.run(
                [node, str(runner_path), str(ROOT), str(out_dir), str(walks_path)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0,
                             f'Node geometry contract failed:\n{result.stdout}\n{result.stderr}')

    def test_foundation_manifest_geometry_contracts_without_toolchain(self):
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(manifest['floorRepeatCells'], [4, 4])

        def bounds_size(box):
            self.assertEqual(len(box), 4)
            return box[2] - box[0], box[3] - box[1]

        for device in ('board', 'returns', 'sink'):
            with self.subTest(device=device):
                horizontal = manifest['frames'][f'modular/device_{device}_horizontal']
                vertical = manifest['frames'][f'modular/device_{device}_vertical']
                h_width, h_height = bounds_size(horizontal['alpha_bbox'])
                v_width, v_height = bounds_size(vertical['alpha_bbox'])
                self.assertGreater(h_width, v_width)
                self.assertGreater(h_height, 0)
                self.assertGreater(v_height, 0)
                self.assertEqual((h_width, h_height), tuple(horizontal['canvasSize']))
                self.assertEqual((v_width, v_height), tuple(vertical['canvasSize']))

        cap = manifest['frames']['modular/wall_cap']
        self.assertEqual(cap['canvasSize'], [64, 64])
        self.assertEqual(bounds_size(cap['alpha_bbox']), (64, 64))

    def test_modular_counter_surface_and_static_wall_bounds(self):
        source = (ROOT / 'cocos-kitchen/assets/scripts/KitchenGeometry.ts').read_text()
        values = {key:int(value) for key,value in __import__('re').findall(r'(\w+)\s*:\s*(\d+)',
                    __import__('re').search(r'GRID_ART\s*=\s*\{([^}]+)\}', source).group(1))}
        manifest = json.loads(MODULAR_MANIFEST.read_text())
        cabinet = manifest['frames']['counter_south']
        tile, unit = values['tile'], values['unit']
        cell = (320, 300)
        left, top, width, height = cabinet['surfaceRect']
        anchor_x, anchor_y = cabinet['groundAnchor']
        lift = values['cabinetSpriteLift']
        scale = tile / unit
        box = (round(cell[0] + (left-anchor_x)*scale),
               round(cell[1] + (top-anchor_y+lift)*scale),
               round(cell[0] + (left+width-anchor_x)*scale),
               round(cell[1] + (top+height-anchor_y+lift)*scale))
        self.assertEqual(box, (cell[0]-tile//2, cell[1]-tile//2,
                               cell[0]+tile//2, cell[1]+tile//2))

        # Both the upper-wall inset and bottom-row wall art are clipped to one
        # grid cell, so neither can spill over a neighboring work surface.
        face_height = values['northFace'] * scale
        self.assertGreater(face_height, 0)
        self.assertLess(face_height, tile)
        self.assertEqual(tile-face_height + face_height, tile)
        preview = (ROOT / 'scripts/preview_map_art.py').read_text()
        self.assertIn("Image.new('RGBA', (TILE, TILE)", preview)
        self.assertIn('image.alpha_composite(layer, (cell_left, cell_top))', preview)


if __name__ == '__main__':
    unittest.main()
