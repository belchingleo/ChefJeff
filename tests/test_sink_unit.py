import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRID = ROOT / 'cocos-kitchen/assets/resources/art/grid-foundation-v1'
SIDES = {'east': (118, 45), 'west': (118, 45), 'south': (45, 118), 'north': (45, 118)}


class SinkUnitArtTest(unittest.TestCase):
    """The two-cell sink with its drying rack (scripts/art/sink_unit.py) in grid-foundation-v1."""

    @classmethod
    def setUpClass(cls):
        cls.frames = json.loads((GRID / 'manifest.json').read_text())['frames']

    def test_every_direction_has_a_unit_and_a_rack_front(self):
        for side, size in SIDES.items():
            unit, front = self.frames[f'modular/sink_unit_{side}'], self.frames[f'modular/sink_unit_rack_front_{side}']
            self.assertEqual(tuple(unit['canvasSize']), size, side)
            self.assertEqual(front['canvasSize'], unit['canvasSize'], side)
            self.assertEqual(unit['anchor'], [0.5, 0.5], side)
            self.assertEqual(unit['rackFront'], f'modular/sink_unit_rack_front_{side}')
            self.assertIn(unit['rackPlate'], self.frames)
        self.assertEqual(self.frames['modular/sink_unit_horizontal']['rect'], self.frames['modular/sink_unit_east']['rect'])
        self.assertEqual(self.frames['modular/sink_unit_vertical']['rect'], self.frames['modular/sink_unit_south']['rect'])

    def test_margins_match_the_single_cell_sink(self):
        single = {'horizontal': self.frames['modular/device_sink_horizontal']['canvasSize'],
                  'vertical': self.frames['modular/device_sink_vertical']['canvasSize']}
        self.assertEqual(SIDES['east'], (single['horizontal'][0] + 64, single['horizontal'][1]))
        self.assertEqual(SIDES['south'], (single['vertical'][0], single['vertical'][1] + 64))

    def test_layout_points_sit_in_their_cells(self):
        for side, (w, h) in SIDES.items():
            unit = self.frames[f'modular/sink_unit_{side}']
            axis = 1 if side in ('north', 'south') else 0
            mid = (w, h)[axis] / 2
            basin_half = unit['basinCell'][axis] < mid
            self.assertEqual(basin_half, side in ('east', 'south'), side)
            self.assertEqual(unit['basin'][axis] < mid, basin_half, side)
            self.assertEqual(unit['tap'][axis] < mid, basin_half, side)
            rack = unit['rack']; slots = unit['rackSlots']
            self.assertEqual(rack['axis'], 'xy'[axis], side)
            self.assertEqual(rack['slots'], len(slots), side)
            self.assertGreaterEqual(rack['slots'], 3, 'a level has at most 3 plates; the rack holds them all')
            self.assertEqual(slots[0], rack['start'], side); self.assertEqual(slots[-1], rack['end'], side)
            self.assertTrue(all((s[axis] < mid) != basin_half for s in slots), side)
            for x, y in [unit['basin'], unit['tap']] + slots: self.assertTrue(0 < x < w and 0 < y < h, side)

    def test_existing_frames_kept_their_rects(self):
        for key, rect in (('modular/device_sink_horizontal', [274, 2, 54, 45]), ('modular/device_sink_vertical', [342, 2, 45, 54]),
                          ('objects/dirty_plate', [138, 206, 32, 32]), ('modular/pot_vertical', [70, 410, 47, 50])):
            self.assertEqual(self.frames[key]['rect'], rect, key)

    def test_atlas_holds_every_rect(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not installed')
        w, h = Image.open(GRID / 'atlas.png').size
        for key, f in self.frames.items():
            x, y, fw, fh = f['rect']
            self.assertTrue(x >= 0 and y >= 0 and x + fw <= w and y + fh <= h, key)


if __name__ == '__main__':
    unittest.main()
