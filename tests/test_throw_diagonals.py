"""Packing contract for the painted diagonal throw bodies (scripts/art/throw_diagonals.py)."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
try:
    from PIL import Image
except ImportError:  # the packer is an art tool; CI without Pillow skips it
    Image = None
try:
    import numpy
except ImportError:
    numpy = None
PACK = ROOT / 'cocos-kitchen/assets/resources/art/throw-diagonal-v1'


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


class CommittedPackTests(unittest.TestCase):
    def test_pack_has_every_frame_with_a_grip_and_down_diagonal_fist_overlays(self):
        frames = json.loads((PACK / 'manifest.json').read_text())['frames']
        for chef in ('player', 'jeff'):
            for diagonal in ('down_right', 'down_left', 'up_left', 'up_right'):
                for phase in ('windup', 'release'):
                    key = f'throw/{chef}/{diagonal}/{phase}'
                    self.assertEqual(len(frames[key]['grip']), 2, key)
                    self.assertEqual(frames[key]['canvasSize'], [68, 88])
                    self.assertEqual(key + '_hand' in frames, diagonal.startswith('down'), key)
                    mirror = key.replace('left', 'RIGHT').replace('right', 'left').replace('RIGHT', 'right')
                    self.assertEqual(frames[key]['grip'], [68 - frames[mirror]['grip'][0], frames[mirror]['grip'][1]])

    @unittest.skipIf(Image is None or numpy is None, 'Pillow and numpy needed to redraw')
    def test_pack_is_what_the_generator_draws_from_the_masters(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = importlib.util.spec_from_file_location('gen', ROOT / 'scripts/art/throw_diagonal_bodies.py')
            sys.path.insert(0, str(ROOT / 'scripts/art'))
            try:
                gen = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(gen)
                manifest = gen.td.write(gen.td.load(gen.save(Path(tmp) / 'frames')), Path(tmp) / 'out')
            finally:
                sys.path.remove(str(ROOT / 'scripts/art'))
            committed = json.loads((PACK / 'manifest.json').read_text())['frames']
            self.assertEqual(manifest, committed)
            self.assertEqual(Image.open(Path(tmp) / 'out/atlas.png').tobytes(), Image.open(PACK / 'atlas.png').tobytes())


if __name__ == '__main__':
    unittest.main()
