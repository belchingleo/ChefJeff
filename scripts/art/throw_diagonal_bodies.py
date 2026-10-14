#!/usr/bin/env python3
"""Draw the 16 diagonal throw bodies (docs/art/throw-diagonal-spec.md) and pack them with throw_diagonals.py.

Sources are the committed master layers in scripts/art/chef_masters: for each chef and view the bare body
(head, torso, legs; no arms) and the base (shadow), exactly as the chefs-v2 idle frames are built, plus
masters.json with the palette, torso rows and shoulder joints. Every frame is drawn from those:

  3/4 turn   the down / up body turned toward screen-right: face and torso detail slides 2-3 px toward the
             aim (a lit column repeats, columns on the far side drop out), the far ear tucks away and the
             far shoulder pulls in 2 px. The silhouette otherwise stays the four-view body, so a diagonal
             throw never jumps in size against the straight ones.
  arms       drawn the chefs-v2 way (capsules, ink outline, shade on the bottom-right edges). The aim-side
             arm throws: wind-up cocked across the chest (facing the viewer) or beside the back of the head
             (facing away), release out along the throw. The other arm hangs at rest.
  left       down_left / up_left are plain mirrors of the right diagonals, as the chefs-v2 left views are
             mirrors of the right views (relighting every left view from the top left is a separate task).

Down diagonals get a _hand overlay (the throwing fist, drawn over the held item); up diagonals carry the
item behind the body and need none. grips.json holds each fist centre and arm angle.

    python3 scripts/art/throw_diagonal_bodies.py                  # draws and writes the pack
    python3 scripts/art/throw_diagonal_bodies.py --frames DIR     # also keeps the 16 PNGs + grips.json in DIR

Needs Pillow and numpy.
"""
import argparse, json, math, tempfile
from pathlib import Path
import numpy as np
from PIL import Image
import throw_diagonals as td

MASTERS = Path(__file__).resolve().parent / 'chef_masters'
W, H = td.CANVAS
INFO = json.loads((MASTERS / 'masters.json').read_text())
# Shoulder to fist. Jeff's chefs-v2 rest mitten sits about 8 px from the shoulder; his throw arms match it.
ARM_LEN = {'jeff': 8.0, 'player': 14.0}
REST_DEG = {'left': 255, 'right': 285}


def _shift(m, dy, dx):
    """out[y, x] = m[y - dy, x - dx] (zero outside)."""
    out = np.zeros_like(m); h, w = m.shape
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = m[ys, xs]; return out


def dilate8(m):
    out = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1): out |= _shift(m, dy, dx)
    return out


def over(dst, src):
    m = src[..., 3] > 0; dst[m] = src[m]; return dst


def mirror(a): return a[:, ::-1].copy()


def load(chef, view, part):
    return np.array(Image.open(MASTERS / f'{chef}_{view}_{part}.png').convert('RGBA'))


def colours(chef):
    return {k: np.array(v, np.uint8) for k, v in INFO[chef]['colours'].items()}


def lightness(rgb):
    """CIE L* of an sRGB colour."""
    c = np.asarray(rgb, float) / 255
    c = np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)
    y = c @ np.array([.2126, .7152, .0722])
    return 116 * np.cbrt(y) - 16 if y > .008856 else 903.3 * y


# ---------------------------------------------------------------- arms (as chefs-v2 draws them)
def disc(cx, cy, r):
    yy, xx = np.mgrid[0:H, 0:W].astype(float) + .5
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r


def capsule(p0, p1, r):
    yy, xx = np.mgrid[0:H, 0:W].astype(float) + .5
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0; L2 = dx * dx + dy * dy or 1
    t = np.clip(((xx - x0) * dx + (yy - y0) * dy) / L2, 0, 1)
    return (xx - x0 - t * dx) ** 2 + (yy - y0 - t * dy) ** 2 <= r * r


def bent(shoulder, hand, out):
    mx, my = (shoulder[0] + hand[0]) / 2, (shoulder[1] + hand[1]) / 2
    dx, dy = hand[0] - shoulder[0], hand[1] - shoulder[1]; n = math.hypot(dx, dy) or 1
    return (mx - dy / n * out, my + dx / n * out)


def draw_arm(chef, shoulder, elbow, hand, c):
    """The arm layer and the fist alone (with its outline)."""
    layer = np.zeros((H, W, 4), np.uint8); jeff = chef == 'jeff'
    upper = capsule(shoulder, elbow, 3.6 if jeff else 3.8) | disc(*shoulder, 3.9 if jeff else 4.0)
    fore = capsule(elbow, hand, 3.3)
    fist = disc(*hand, 4.0 if jeff else 3.9)
    shape = upper | fore | fist
    layer[dilate8(shape) & ~shape] = [*c['ink'], 255]
    shade = lambda m: m & (~_shift(m, -1, 0) | ~_shift(m, 0, -1))
    if jeff:
        arm = upper | fore
        layer[arm] = [*c['cream'], 255]; layer[shade(arm)] = [*c['cream_shade'], 255]
        layer[fist] = [*c['mitten'], 255]; layer[shade(fist)] = [*c['mitten_dark'], 255]
        hx, hy = int(hand[0]), int(hand[1]); layer[hy, hx:hx + 2] = [*c['orange'], 255]
    else:
        layer[fore & ~upper] = [*c['skin'], 255]; layer[shade(fore) & ~upper] = [*c['skin_shade'], 255]
        layer[upper] = [*c['white'], 255]; layer[shade(upper)] = [*c['white_shade'], 255]
        cuff = upper & dilate8(fore & ~upper); layer[cuff] = [*c['white_shade'], 255]
        layer[fist] = [*c['skin'], 255]; layer[shade(fist)] = [*c['skin_shade'], 255]
    hand_only = np.zeros_like(layer); hm = dilate8(fist); hand_only[hm] = layer[hm]
    return layer, hand_only


def arm_at(chef, shoulder, deg, c, out):
    """Arm from the shoulder at screen angle deg (CCW from +x), elbow bent `out` px off the line."""
    L = ARM_LEN[chef]; a = math.radians(deg)
    hand = (shoulder[0] + L * math.cos(a), shoulder[1] - L * math.sin(a))
    layer, fist = draw_arm(chef, shoulder, bent(shoulder, hand, out), hand, c)
    return layer, fist, hand


def no_spurs(a):
    """Peel single-pixel ends left where an arm outline meets the body outline."""
    a = a.copy()
    for _ in range(6):
        m = a[..., 3] > 0
        n4 = sum(_shift(m, dy, dx).astype(int) for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        end = m & (n4 <= 1)
        if not end.any(): break
        a[end] = 0
    return a


# ---------------------------------------------------------------- the 3/4 turn
def lit_column(img, y, lo, hi):
    """The brightest non-outline column of row y in lo..hi: one a slide can repeat without smearing a
    shadow or an outline across the face."""
    best, bl = lo, -1
    for x in range(lo, hi + 1):
        p = img[y, x]
        if p[3] == 0: continue
        L = lightness(p[:3])
        if L > 14 and L > bl: best, bl = x, L
    return best


def slide(img, y0, y1, ins, dels):
    """Rows y0..y1: repeat column `ins` (or, for a (lo, hi) range, that row's brightest column in it)
    len(dels) extra times, then drop the original columns `dels` (all right of `ins`). Detail between them
    slides right; the silhouette outside does not move."""
    out = img.copy(); n = len(dels)
    for y in range(y0, y1 + 1):
        at = lit_column(img, y, *ins) if isinstance(ins, tuple) else ins
        row = list(img[y]); row = row[:at] + [row[at]] * n + row[at:]
        for d in sorted(dels, reverse=True): del row[d + n]
        out[y] = np.array(row)
    return out


def slide_left(img, y0, y1, ins, dels):
    """The same slide toward -x (ins and dels in the image's own columns, dels left of ins)."""
    ins = (W - 1 - ins[1], W - 1 - ins[0]) if isinstance(ins, tuple) else W - 1 - ins
    return mirror(slide(mirror(img), y0, y1, ins, [W - 1 - d for d in dels]))


# Turn plans, facing right: (rows, repeated column, dropped columns, direction). Front views slide detail
# right (the far ear tucks away), back views slide it left.
TURN = {
    ('player', 'down'): [(28, 46, 23, [47, 48, 49], 'r'), (47, 66, 25, [43, 44], 'r')],
    ('player', 'up'): [(30, 46, 48, [21, 20, 19], 'l'), (47, 66, 44, [25, 24], 'l')],
    ('jeff', 'down'): [(32, 53, (17, 22), [53, 54, 55], 'r'), (54, 66, 25, [42, 43], 'r')],
    ('jeff', 'up'): [(32, 53, 48, [16, 15, 14], 'l'), (54, 66, 44, [25, 24], 'l')],
}
FAR_SHOULDER = 2      # px the far (screen-right) shoulder pulls in


def narrow_far_shoulder(img, top, n=FAR_SHOULDER):
    """Pull the screen-right edge of the shoulder rows in by n px (n-1 px on the next rows), keeping the outline."""
    out = img.copy()
    for y in range(top - 2, top + 7):
        k = n if y < top + 3 else n - 1
        if k <= 0: continue
        xs = np.nonzero(out[y, :, 3] > 0)[0]
        if len(xs) < 8: continue
        R = xs.max()
        out[y, R - k] = out[y, R]; out[y, R - k + 1:R + 1] = 0
    return out


def turned_body(chef, view):
    b = load(chef, view, 'body')
    for y0, y1, ins, dels, way in TURN[(chef, view)]:
        b = (slide if way == 'r' else slide_left)(b, y0, y1, ins, dels)
    return narrow_far_shoulder(b, INFO[chef][view]['torso_rows'][0])


# ---------------------------------------------------------------- frames
# Screen angle of the throwing (screen-right) arm in the right diagonals.
POSE = {
    ('player', 'down', 'windup'): 185, ('player', 'down', 'release'): -35,
    ('player', 'up', 'windup'): 95, ('player', 'up', 'release'): 40,
    ('jeff', 'down', 'windup'): 185, ('jeff', 'down', 'release'): -45,
    ('jeff', 'up', 'windup'): 80, ('jeff', 'up', 'release'): 40,
}


def frame_right(chef, view, phase):
    """down_right / up_right: (image, fist overlay or None, grip entry)."""
    c = colours(chef); sh = INFO[chef][view]['shoulders']
    near, far = tuple(sh['left']), (sh['right'][0] - FAR_SHOULDER, sh['right'][1])
    rest, _, _ = arm_at(chef, near, REST_DEG['left'], c, out=1.2)
    deg = POSE[(chef, view, phase)]
    arm, fist, hand = arm_at(chef, far, deg, c, out=-0.8)
    img = np.zeros((H, W, 4), np.uint8)
    for layer in (load(chef, view, 'base'), turned_body(chef, view), rest, arm): over(img, layer)
    grip = {'grip': [int(round(hand[0])), int(round(hand[1]))], 'arm_deg': deg}
    return no_spurs(img), (fist if view == 'down' else None), grip


def frame_left(right):
    """The mirror of a right diagonal, grip and arm angle mirrored with it. The grip is a point in canvas
    coordinates (the centre line is x = 34), so it mirrors to W - x; pixel columns mirror to W - 1 - x."""
    img, fist, g = right
    return mirror(img), (None if fist is None else mirror(fist)), {'grip': [W - g['grip'][0], g['grip'][1]],
                                                                  'arm_deg': 180 - g['arm_deg']}


def frames():
    """{name: (image, fist overlay or None, grip entry)} for all 16 frames."""
    out = {}
    for chef in td.CHEFS:
        for view in ('down', 'up'):
            for phase in td.PHASES:
                right = frame_right(chef, view, phase)
                out[f'{chef}_{view}_right_{phase}'] = right
                out[f'{chef}_{view}_left_{phase}'] = frame_left(right)
    return out


def save(folder):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    grips = {}
    for name, (img, fist, grip) in frames().items():
        Image.fromarray(img).save(folder / f'{name}.png')
        if fist is not None: Image.fromarray(fist).save(folder / f'{name}_hand.png')
        grips[name] = grip
    (folder / 'grips.json').write_text(json.dumps(grips, indent=1, sort_keys=True) + '\n')
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--frames', help='keep the drawn PNGs and grips.json in this folder')
    parser.add_argument('--out', default=str(td.OUT))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        folder = save(args.frames or tmp)
        manifest = td.write(td.load(folder), args.out)
    print(f'{len(manifest)} frames written to {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
