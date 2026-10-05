import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'cocos-kitchen/assets/resources/art/ingredient-pack-v1'
ITEMS = ['cucumber', 'onion', 'cheese', 'chicken', 'fish', 'flatbread', 'scallion']
CHOPPED = ['cucumber', 'onion', 'cheese', 'chicken', 'fish', 'scallion']
HEATED = ['chicken', 'fish']
PAN_ITEMS = ['beef', 'chicken', 'fish']
PAN_STAGES = ['chopped', 'cooking', 'ready', 'burnt']
NOODLE_STAGES = ['raw', 'cooking', 'ready', 'burnt']
# Handle toward the chef: horizontal = east, vertical = south, plus west and north (behind the pan).
PANS = {'objects/pan': (32, 32), 'modular/pan_horizontal': (50, 37), 'modular/pan_vertical': (47, 50),
        'modular/pan_west': (50, 37), 'modular/pan_north': (47, 50)}
POTS = {'objects/pot': (32, 32), 'modular/pot_horizontal': (50, 37), 'modular/pot_vertical': (47, 50)}


class IngredientPackTest(unittest.TestCase):
    """Frame contract of the ingredient pack: the keys and sizes the current four ingredients use."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((PACK / 'manifest.json').read_text())
        cls.frames = cls.manifest['frames']

    def test_every_item_has_the_frames_of_the_current_ingredients(self):
        expected = []
        for item in ITEMS:
            expected += [f'food/{item}_raw', f'modular/source_{item}', f'feedback/{item}']
            if item in CHOPPED: expected.append(f'food/{item}_chopped')
        for item in HEATED:
            expected += [f'food/{item}_ready', f'food/{item}_burnt', f'dishes/{item}/ready', f'dishes/{item}/burnt']
            expected += [f'ingredients/{item}/{stage}' for stage in ('raw', 'processing', 'prepared', 'cooking', 'ready', 'burnt')]
        expected += ['food/noodles_raw', 'food/noodles_ready', 'food/noodles_burnt', 'modular/source_noodles', 'feedback/noodles']
        expected += [f'ingredients/noodles/{stage}' for stage in NOODLE_STAGES]
        expected += [f'dishes/{dish}/{state}' for dish in ('beef_noodles', 'chicken_noodles', 'fish_steak') for state in ('ready', 'burnt')]
        for pan in PANS:
            expected += [pan] + [f'{pan}/{item}/{stage}' for item in PAN_ITEMS for stage in PAN_STAGES]
        expected += [f'{pot}/noodles/{stage}' for pot in POTS for stage in NOODLE_STAGES]
        self.assertEqual(sorted(expected), sorted(self.frames))

    def test_vessel_frames_match_the_soup_pot_canvases(self):
        for key, f in self.frames.items():
            vessel = key.split('/')[0] + '/' + key.split('/')[1]
            if vessel in PANS or vessel in POTS:
                self.assertEqual(tuple(f['canvasSize']), {**PANS, **POTS}[vessel], key)
                self.assertEqual(f['vessel'], 'pan' if vessel in PANS else 'pot', key)
                x, y = f['contentAnchor']
                self.assertTrue(0 < x < f['canvasSize'][0] and 0 < y < f['canvasSize'][1], key)

    def test_fish_steak_dish_shares_the_fried_fish_art(self):
        for state in ('ready', 'burnt'):
            self.assertEqual(self.frames[f'dishes/fish_steak/{state}']['rect'], self.frames[f'dishes/fish/{state}']['rect'])

    def test_frame_sizes_match_the_existing_conventions(self):
        for key, f in self.frames.items():
            w, h = f['canvasSize']
            self.assertEqual(f['rect'][2:], [w, h], key)
            if key.startswith('food/'): self.assertEqual((w, h), (64, 64), key)
            elif key.startswith('modular/source_'):
                self.assertEqual((w, h), (64, 96), key)
                x0, y0, x1, y1 = f['alpha_bbox']
                self.assertTrue(x0 >= 12 and x1 <= 52 and y0 >= 20 and y1 <= 62, key)
            elif key.startswith('dishes/') and 'noodles' in key: self.assertEqual((w, h), (48, 48), key)
            elif key.startswith(('ingredients/', 'dishes/')): self.assertEqual((w, h), (32, 32), key)
            elif key.startswith(('objects/', 'modular/pan', 'modular/pot')): continue
            else: self.assertTrue(w <= 48 and h <= 32, key)

    def test_atlas_rects_fit_and_alpha_is_hard(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not installed')
        atlas = Image.open(PACK / 'atlas.png').convert('RGBA')
        for key, f in self.frames.items():
            x, y, w, h = f['rect']
            self.assertTrue(x >= 0 and y >= 0 and x + w <= atlas.width and y + h <= atlas.height, key)
            hist = atlas.crop((x, y, x + w, y + h)).getchannel('A').histogram()
            self.assertEqual(sum(hist[1:255]), 0, key)

    def test_client_loads_the_pack(self):
        source = (ROOT / 'cocos-kitchen/assets/scripts/LevelOneArt.ts').read_text()
        self.assertIn("loadAtlas('art/ingredient-pack-v1')", source)
        self.assertTrue((PACK / 'atlas.png.meta').exists() and (PACK / 'manifest.json.meta').exists())


if __name__ == '__main__':
    unittest.main()
