import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'cocos-kitchen/assets/resources/art/ingredient-pack-v1'
ITEMS = ['cucumber', 'onion', 'cheese', 'chicken', 'fish', 'flatbread', 'scallion']
CHOPPED = ['cucumber', 'onion', 'cheese', 'chicken', 'fish', 'scallion']
HEATED = ['chicken', 'fish']


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
        self.assertEqual(sorted(expected), sorted(self.frames))

    def test_frame_sizes_match_the_existing_conventions(self):
        for key, f in self.frames.items():
            w, h = f['canvasSize']
            self.assertEqual(f['rect'][2:], [w, h], key)
            if key.startswith('food/'): self.assertEqual((w, h), (64, 64), key)
            elif key.startswith('modular/source_'):
                self.assertEqual((w, h), (64, 96), key)
                x0, y0, x1, y1 = f['alpha_bbox']
                self.assertTrue(x0 >= 12 and x1 <= 52 and y0 >= 20 and y1 <= 62, key)
            elif key.startswith(('ingredients/', 'dishes/')): self.assertEqual((w, h), (32, 32), key)
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
