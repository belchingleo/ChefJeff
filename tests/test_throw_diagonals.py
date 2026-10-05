"""Packing contract for the painted diagonal throw bodies (scripts/art/throw_diagonals.py)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
try:
    from PIL import Image
except ImportError:  # the packer is an art tool; CI without Pillow skips it
    Image = None


def packer():
    spec = importlib.util.spec_from_file_location('throw_diagonals', ROOT / 'scripts/art/throw_diagonals.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(Image is None, 'Pillow unavailable')
class ThrowDiagonalPackTests(unittest.TestCase):
    def frames_dir(self, root, missing=(), bad_feet=()):
        tool = packer()
        grips = {}
        for i, name in enumerate(tool.frame_names()):
            if name in missing:
                continue
            image = Image.new('RGBA', tool.CANVAS, (0, 0, 0, 0))
            bottom = 70 if name in bad_feet else tool.FOOT_Y
            for y in range(20, bottom + 1):
                for x in range(24, 44):
                    image.putpixel((x, y), (i * 7 % 256, 90, 158, 255))
            image.save(root / f'{name}.png')
            grips[name] = {'grip': [40, 50], 'arm_deg': 30}
        Image.new('RGBA', tool.CANVAS, (255, 255, 255, 255)).save(root / 'player_down_right_release_hand.png')
        (root / 'grips.json').write_text(json.dumps(grips))
        return tool

    def test_sixteen_frames_pack_with_grips_and_the_chef_feet_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / 'in', Path(tmp) / 'out'
            source.mkdir()
            tool = self.frames_dir(source)
            manifest = tool.write(tool.load(source), out)
            keys = {f'throw/{c}/{d}/{p}' for c in tool.CHEFS for d in tool.DIAGONALS for p in tool.PHASES}
            self.assertEqual(set(manifest) - {'throw/player/down_right/release_hand'}, keys)
            atlas = Image.open(out / 'atlas.png').convert('RGBA')
            for key, frame in manifest.items():
                x, y, w, h = frame['rect']
                self.assertEqual((w, h), tool.CANVAS)
                self.assertEqual(frame['anchor'], [0.5, 5 / 88])
                if not key.endswith('_hand'):
                    self.assertEqual(frame['grip'], [40, 50])
                    self.assertIn('arm_deg', frame)
                    chef, diagonal, phase = key.split('/')[1:]
                    original = Image.open(source / f'{chef}_{diagonal}_{phase}.png').convert('RGBA')
                    self.assertEqual(atlas.crop((x, y, x + w, y + h)).tobytes(), original.tobytes())
            self.assertTrue((out / 'atlas.png.meta').is_file() and (out / 'manifest.json.meta').is_file())

    def test_missing_frames_wrong_feet_and_grips_are_reported_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            tool = self.frames_dir(source, missing=('jeff_up_left_windup',), bad_feet=('player_up_right_release',))
            with self.assertRaises(ValueError) as caught:
                tool.load(source)
            message = str(caught.exception)
            self.assertIn('missing jeff_up_left_windup.png', message)
            self.assertIn('player_up_right_release.png: feet end at y=70', message)


if __name__ == '__main__':
    unittest.main()
