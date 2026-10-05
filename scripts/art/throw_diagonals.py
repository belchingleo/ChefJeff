#!/usr/bin/env python3
"""Pack the painted diagonal throw bodies into art/throw-diagonal-v1 (see docs/art/throw-diagonal-spec.md).

Input: one folder of 68x88 RGBA PNGs, one per frame, named <chef>_<diagonal>_<phase>.png
  chef      player | jeff
  diagonal  down_right | down_left | up_left | up_right      (map y points down: down = toward the viewer)
  phase     windup | release
plus optional <chef>_<diagonal>_<phase>_hand.png fist overlays (drawn over the held item), and grips.json:
  {"player_down_right_windup": {"grip": [x, y], "arm_deg": 95}, ...}
grip is the centre of the throwing fist in canvas pixels (PNG top-left origin); arm_deg is the arm's screen
angle in degrees counter-clockwise from +x. The held item is drawn just beyond the fist along the arm.

    python3 scripts/art/throw_diagonals.py path/to/frames            # writes the pack
    python3 scripts/art/throw_diagonals.py --reference path/to/out   # guide sheets for the artist

The client loads the pack when it exists and uses a diagonal body whenever a throw aims within 22.5 degrees
of a diagonal; without it, throws keep the four-view bodies. Needs Pillow.
"""
import argparse
import json
from pathlib import Path
import sys
import uuid

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'cocos-kitchen/assets/resources/art/throw-diagonal-v1'
CHEFS = ('player', 'jeff')
DIAGONALS = ('down_right', 'down_left', 'up_left', 'up_right')
PHASES = ('windup', 'release')
CANVAS = (68, 88)
FOOT_Y = 83                      # feet line of every chef frame (chefs-v2 anchorPx)
ANCHOR = [0.5, (CANVAS[1] - FOOT_Y) / CANVAS[1]]
PAD = 2


def frame_names():
    return [f'{c}_{d}_{p}' for c in CHEFS for d in DIAGONALS for p in PHASES]


def alpha_bbox(image):
    box = image.getchannel('A').getbbox()
    return list(box) if box else [0, 0, 0, 0]


def write_meta(path, kind):
    """Cocos import metadata; existing files keep their uuids."""
    if path.exists():
        return
    uid = str(uuid.uuid4())
    if kind == 'json':
        meta = {"ver": "2.0.1", "importer": "json", "imported": True, "uuid": uid, "files": [".json"], "subMetas": {}, "userData": {}}
    else:
        meta = {"ver": "1.0.27", "importer": "image", "imported": True, "uuid": uid, "files": [".json", ".png"],
                "subMetas": {"6c48a": {"importer": "texture", "uuid": f"{uid}@6c48a", "displayName": "atlas", "id": "6c48a",
                                       "name": "texture", "userData": {"wrapModeS": "clamp-to-edge", "wrapModeT": "clamp-to-edge",
                                       "imageUuidOrDatabaseUri": uid, "isUuid": True, "visible": False, "minfilter": "nearest",
                                       "magfilter": "nearest", "mipfilter": "none", "anisotropy": 0},
                                       "ver": "1.0.22", "imported": True, "files": [".json"], "subMetas": {}}},
                "userData": {"type": "texture", "fixAlphaTransparencyArtifacts": False, "hasAlpha": True, "redirect": f"{uid}@6c48a"}}
    path.write_text(json.dumps(meta, indent=2) + '\n')


def load(folder):
    """Validated frames {key: (image, meta)}; raises ValueError listing every problem."""
    folder = Path(folder)
    problems, frames = [], {}
    grips_path = folder / 'grips.json'
    grips = json.loads(grips_path.read_text()) if grips_path.is_file() else {}
    if not grips:
        problems.append('grips.json is missing or empty')
    for name in frame_names():
        chef, rest = name.split('_', 1)
        diagonal, phase = rest.rsplit('_', 1)
        path = folder / f'{name}.png'
        if not path.is_file():
            problems.append(f'missing {path.name}')
            continue
        image = Image.open(path).convert('RGBA')
        if image.size != CANVAS:
            problems.append(f'{path.name}: canvas {image.size}, expected {CANVAS}')
            continue
        bottom = alpha_bbox(image)[3]
        if abs(bottom - (FOOT_Y + 1)) > 2:
            problems.append(f'{path.name}: feet end at y={bottom - 1}, expected about y={FOOT_Y}')
        grip = grips.get(name, {})
        g, arm = grip.get('grip'), grip.get('arm_deg')
        if not (isinstance(g, list) and len(g) == 2 and 0 <= g[0] < CANVAS[0] and 0 <= g[1] < CANVAS[1]) or not isinstance(arm, (int, float)):
            problems.append(f'{name}: grips.json needs "grip": [x, y] inside the canvas and a numeric "arm_deg"')
            continue
        key = f'throw/{chef}/{diagonal}/{phase}'
        meta = {'canvasSize': list(CANVAS), 'anchor': ANCHOR, 'anchorPx': [CANVAS[0] // 2, FOOT_Y], 'view': diagonal,
                'grip': list(g), 'grip_display': list(g), 'arm_deg': arm, 'alpha_bbox': alpha_bbox(image),
                'source': 'painted diagonal throw body, 64 px per tile'}
        frames[key] = (image, meta)
        hand = folder / f'{name}_hand.png'
        if hand.is_file():
            overlay = Image.open(hand).convert('RGBA')
            if overlay.size != CANVAS:
                problems.append(f'{hand.name}: canvas {overlay.size}, expected {CANVAS}')
            else:
                frames[key + '_hand'] = (overlay, {'canvasSize': list(CANVAS), 'anchor': ANCHOR, 'alpha_bbox': alpha_bbox(overlay)})
    if problems:
        raise ValueError('\n'.join(problems))
    return frames


def pack(frames, width=512):
    """Shelf-pack full 68x88 canvases (the anchor relies on the whole canvas) with padding."""
    x = y = PAD
    shelf = 0
    placed = {}
    for key in sorted(frames):
        image = frames[key][0]
        w, h = image.size
        if x + w + PAD > width:
            x, y, shelf = PAD, y + shelf + PAD, 0
        placed[key] = (x, y)
        x += w + PAD
        shelf = max(shelf, h)
    height = 1
    while height < y + shelf + PAD:
        height *= 2
    atlas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    manifest = {}
    for key, (px, py) in placed.items():
        image, meta = frames[key]
        atlas.paste(image, (px, py))
        manifest[key] = {**meta, 'rect': [px, py, *image.size]}
    return atlas, manifest


def write(frames, out=OUT):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    atlas, manifest = pack(frames)
    atlas.save(out / 'atlas.png', optimize=True)
    (out / 'manifest.json').write_text(json.dumps({
        'version': 'throw-diagonal-v1', 'px_per_tile': 64,
        'notes': 'Diagonal throw bodies, keys throw/<chef>/<diagonal>/<windup|release> (+ _hand fist overlay). '
                 'Canvas and feet anchor match chefs-v2; grip = fist centre in canvas px; arm_deg = arm angle, CCW from +x.',
        'frames': manifest}, indent=1) + '\n')
    write_meta(out / 'atlas.png.meta', 'image')
    write_meta(out / 'manifest.json.meta', 'json')
    return manifest


def reference(out):
    """Guide sheets: the current four-view throw poses on the 68x88 canvas with the feet line and centre."""
    chefs_dir = ROOT / 'cocos-kitchen/assets/resources/art/chefs-v2'
    frames = json.loads((chefs_dir / 'manifest.json').read_text())['frames']
    atlas = Image.open(chefs_dir / 'atlas.png').convert('RGBA')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    scale = 4
    for chef in CHEFS:
        sheet = Image.new('RGBA', (CANVAS[0] * scale * 4, CANVAS[1] * scale * 2), (235, 225, 200, 255))
        draw = ImageDraw.Draw(sheet)
        for col, view in enumerate(('down', 'right', 'up', 'left')):
            for row, frame in enumerate((0, 1)):          # wind-up, release (forward)
                key = f'knifeless/characters/{chef}/{view}/chop_{frame}'
                if key not in frames:
                    continue
                x, y, w, h = frames[key]['rect']
                tile = atlas.crop((x, y, x + w, y + h)).resize((w * scale, h * scale), Image.NEAREST)
                ox, oy = col * CANVAS[0] * scale, row * CANVAS[1] * scale
                sheet.alpha_composite(tile, (ox, oy))
                draw.line((ox, oy + FOOT_Y * scale, ox + CANVAS[0] * scale, oy + FOOT_Y * scale), fill=(42, 90, 158, 255))
                draw.line((ox + 34 * scale, oy, ox + 34 * scale, oy + CANVAS[1] * scale), fill=(42, 90, 158, 120))
        sheet.save(out / f'reference_{chef}.png')
    return [out / f'reference_{chef}.png' for chef in CHEFS]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('frames', nargs='?', help='folder with the 16 PNGs and grips.json')
    parser.add_argument('--out', default=str(OUT))
    parser.add_argument('--reference', metavar='DIR', help='write guide sheets of the current poses instead')
    args = parser.parse_args()
    if args.reference:
        for path in reference(args.reference):
            print(path)
        return 0
    if not args.frames:
        parser.error('give the frames folder, or --reference DIR')
    try:
        frames = load(args.frames)
    except ValueError as problems:
        print(problems, file=sys.stderr)
        return 1
    manifest = write(frames, args.out)
    print(f'{len(manifest)} frames written to {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
