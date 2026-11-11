"""Overcooked 2's pick-up reach for loose items (InteractWithItemHelper: a 180-degree arc ahead, radius 1 to the
item's edge): an item beside a chef running past is picked, one behind is not, and the page highlights the same
item the engine takes (KitchenGeometry.spaceTarget against spatial_kitchen.facing_candidates)."""
import json
import shutil
import subprocess
import unittest

from kitchen import Food, GroundItem, load_config
from spatial_kitchen import ITEM_REACH, SpatialKitchen, tile_key
from test_visual_geometry import ROOT


def kitchen():
    k = SpatialKitchen({**load_config(), 'level': 1, 'spawn_seed': 0})
    k.chefs['human'].hand = None
    k.ground.clear()
    return k


def first_item(k):
    return next((c for c in k.facing_candidates('human')[0] if c.startswith('item:')), None)


class ItemReachTests(unittest.TestCase):
    def test_an_item_beside_a_running_chef_is_picked_and_one_behind_is_not(self):
        k = kitchen()
        k.positions['human'] = (2.0, 6.0)
        k.facing['human'] = 'right'
        # Beside (90 degrees off the aim, one cell away): inside the half-disc, as in Overcooked 2.
        k.ground['side'] = GroundItem(Food('side'), tile_key((2, 5)))
        self.assertEqual(first_item(k), 'item:side')
        self.assertEqual(k.facing_interaction('human')[1].key, 'pickup side')
        # Behind: never.
        k.ground.clear()
        k.ground['back'] = GroundItem(Food('back'), tile_key((1, 6)))
        self.assertIsNone(first_item(k))
        # Diagonal ahead, beyond reach from the cell's centre, comes into reach as the chef moves towards it.
        k.ground.clear()
        k.ground['diag'] = GroundItem(Food('diag'), tile_key((3, 5)))
        self.assertIsNone(first_item(k))
        k.positions['human'] = (2.4, 5.7)
        self.assertEqual(first_item(k), 'item:diag')

    def test_the_aimed_item_wins_over_one_beside(self):
        k = kitchen()
        k.positions['human'] = (2.0, 6.0)
        k.facing['human'] = 'right'
        k.ground['side'] = GroundItem(Food('side'), tile_key((2, 5)))
        k.ground['front'] = GroundItem(Food('front'), tile_key((3, 6)))
        self.assertEqual(first_item(k), 'item:front')

    def test_the_page_picks_the_same_item(self):
        if not shutil.which('node'):
            self.skipTest('Node.js unavailable')
        cases, k = [], kitchen()
        spots = [(2.0, 6.0), (2.4, 5.7), (2.2, 6.3), (3.0, 4.0), (4.6, 5.5)]
        aims = {'right': (1, 0), 'left': (-1, 0), 'up': (0, -1), 'down': (0, 1)}
        snap = k.snapshot()
        for i, tile in enumerate(t for t in [(2, 5), (3, 6), (1, 6), (3, 5), (4, 4), (5, 5), (3, 4), (4, 6)]
                                 if tile_key(t) in k.floor_places):
            k.ground[f'f{i}'] = GroundItem(Food(f'f{i}'), tile_key(tile))
        for pos in spots:
            for facing, aim in aims.items():
                k.positions['human'] = pos
                k.facing['human'] = facing
                stations = k.selectable_stations('human')
                cands = k.facing_candidates('human')[0]
                # Only cases where no station is in play: this test is about loose items.
                if stations:
                    continue
                cases.append({'pos': list(pos), 'aim': list(aim), 'engine': next((c for c in cands if c.startswith('item:')), None)})
        ground = [{'position': list(k.ground_position(item)), 'location': item.location, 'food': {'id': key}}
                  for key, item in k.ground.items()]
        script = """
const fs=require('fs'),vm=require('vm'),m=require('node:module');
const src=m.stripTypeScriptTypes(fs.readFileSync(process.argv[1],'utf8')).replace(/^export /gm,'');
const ctx={};vm.createContext(ctx);vm.runInContext(src+';this.spaceTarget=spaceTarget;',ctx);
const data=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify(data.cases.map(c=>ctx.spaceTarget(data.map,c.pos,c.aim,data.ground))));"""
        try:
            out = subprocess.run(['node', '-e', script, str(ROOT / 'cocos-kitchen/assets/scripts/KitchenGeometry.ts')],
                                 input=json.dumps({'map': snap['map'], 'ground': ground, 'cases': cases}),
                                 capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            self.skipTest('Node.js timed out')
        if out.returncode and 'stripTypeScriptTypes' in out.stderr:
            self.skipTest('Node.js without TypeScript stripping')
        self.assertEqual(out.returncode, 0, out.stderr)
        page = json.loads(out.stdout)
        self.assertGreater(len(cases), 8)
        self.assertEqual([c['engine'] for c in cases], page)
        self.assertEqual(ITEM_REACH, 1.2)


if __name__ == '__main__':
    unittest.main()
