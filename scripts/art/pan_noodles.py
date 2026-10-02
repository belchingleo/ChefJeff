"""Frying pan, noodles and noodle dishes for the ingredient pack, in the current food style.

Drawn with the ingredient pack's tools (scripts/art/ingredient_pack.py), which calls frames() here and writes
everything into one atlas. Keys:

  objects/pan, modular/pan_horizontal, modular/pan_vertical    empty pan, same canvases as the soup pot frames
  objects/pan/<item>/<stage>, modular/pan_<axis>/<item>/<stage>
                                                               the pan with food frying in it, baked in, for
                                                               beef, chicken, fish at chopped/cooking/ready/burnt
  objects/pot/noodles/<stage>, modular/pot_<axis>/noodles/<stage>
                                                               the existing soup pot art with noodles boiling in
                                                               it: raw/cooking/ready/burnt (burnt = boiled dry)
  food/noodles_{raw,ready,burnt}, modular/source_noodles, feedback/noodles, ingredients/noodles/<stage>
  dishes/{beef,chicken}_noodles/{ready,burnt}, dishes/fish_steak/{ready,burnt}

Pan and pot frames carry contentAnchor, the centre of the vessel's inside in canvas pixels.
"""
import json, math
import numpy as np
from PIL import Image, ImageDraw
import ingredient_pack as ip
from ingredient_pack import (Piece, render, ramp, mix, grain, Noise, local, dome, capsule, disc_piece, tone, cubes,
                             scallion_ring, plate, bbox, crop_to_content, INK, SS)

ip.RAMPS.update({
    'steel': [(44, 52, 74), (70, 84, 112), (118, 132, 160), (186, 196, 214), (240, 242, 246)],
    'iron': [(12, 12, 18), (24, 25, 34), (38, 40, 52), (58, 62, 78), (92, 98, 118)],
    'grip': [(10, 10, 14), (24, 22, 26), (44, 40, 44), (78, 72, 74)],
    'noodle': [(150, 108, 48), (206, 168, 94), (234, 206, 140), (248, 230, 182), (255, 247, 222)],
    'noodle_cooked': [(176, 132, 62), (224, 188, 106), (242, 216, 144), (252, 236, 186), (255, 251, 232)],
    'noodle_burnt': [(30, 16, 8), (72, 40, 18), (122, 74, 32), (168, 114, 54), (204, 158, 92)],
    'water': [(64, 90, 116), (104, 134, 158), (146, 174, 192), (194, 214, 224), (234, 242, 246)],
    'starch': [(132, 142, 140), (176, 184, 178), (208, 212, 202), (232, 234, 226), (248, 248, 242)],
    'beef_raw': [(112, 26, 32), (162, 46, 52), (202, 80, 82), (230, 124, 120), (248, 178, 168)],
    'beef_cooked': [(56, 26, 14), (94, 46, 24), (132, 70, 38), (168, 102, 60), (204, 146, 98)],
    'paper': [(170, 160, 140), (214, 206, 188), (238, 232, 218), (252, 250, 244)],
})
PAN_INK = (10, 10, 22)
NOODLE_STAGES = ('raw', 'cooking', 'ready', 'burnt')
PAN_ITEMS = ('beef', 'chicken', 'fish')
PAN_STAGES = ('chopped', 'cooking', 'ready', 'burnt')
GRID = ip.ROOT / 'cocos-kitchen/assets/resources/art/grid-foundation-v1'
# frying pan geometry per frame: canvas, body (cx, cy, rx, ry, wall), handle (from, to, r0, r1)
PANS = {
    'objects/pan': ((32, 32), (13.0, 15.0, 11.0, 7.4, 3.0), ((23.0, 16.6), (31.2, 13.0), 1.7, 1.4)),
    'modular/pan_horizontal': ((50, 37), (19.5, 16.5, 17.5, 11.5, 4.0), ((35.5, 18.5), (49.2, 14.8), 2.5, 2.0)),
    'modular/pan_vertical': ((47, 50), (23.5, 16.5, 20.0, 13.0, 4.5), ((23.5, 33.0), (23.5, 49.0), 2.9, 2.6)),
}
# inside of the existing soup pot frames (grid-foundation-v1), measured: centre, radii
POTS = {'objects/pot': (16.5, 11.6, 9.4, 4.4), 'modular/pot_horizontal': (24.5, 12.6, 14.2, 9.2),
        'modular/pot_vertical': (23.0, 20.0, 20.2, 12.2)}


# ---------------------------------------------------------------- frying pan

def pan_pieces(body, handle):
    cx, cy, rx, ry, wall = body
    (a, b, r0, r1) = handle
    ins = inside(body)
    def top(u, v, X, Y):
        iu, iv = local(X, Y, *ins)
        rr = iu * iu + iv * iv
        col = ramp('steel', 0.72 - 0.35 * u + 0.02 * grain(X, Y, 7))            # rim, lit at the back left
        hl = (v < -0.55) & (u < 0.2)
        col[hl] = ramp('steel', 0.98)[hl]
        floor = rr <= 1
        # inside: dark non-stick floor; the far wall catches light, a soft sheen across the floor
        sheen = np.exp(-((iu + 0.3) * 0.9 + (iv + 0.15)) ** 2 / 0.05) * (iu < 0.4)
        wallband = np.clip((-iv - 0.35) / 0.65, 0, 1) * (rr > 0.45)
        t = 0.32 + 0.4 * wallband + 0.32 * sheen + 0.02 * grain(X, Y, 8)
        col[floor] = ramp('iron', t)[floor]
        lip = floor & (rr > 0.86) & (iv > 0)
        col[lip] = ramp('iron', 0.12)[lip]
        return col
    def side(dep, X, Y):
        u = (X - cx) / rx
        return ramp('steel', 0.62 - 0.42 * u - 0.12 * dep + 0.02 * grain(X, Y, 9))
    def grip(X, Y):
        m, t, sidec, lam = capsule(X, Y, a, b, r0, r1)
        col = ramp('grip', 0.2 + 0.75 * lam + 0.02 * grain(X, Y, 10))
        ln = np.abs(sidec + 0.35) < 0.18                                       # highlight along the top
        col[ln] = ramp('grip', 0.95)[ln]
        hole_c = (a[0] + (b[0] - a[0]) * 0.86, a[1] + (b[1] - a[1]) * 0.86)
        hu, hv = local(X, Y, *hole_c, max(0.7, r1 * 0.4), max(0.6, r1 * 0.33))
        hole = hu * hu + hv * hv <= 1
        col[hole] = np.array([0.03, 0.03, 0.05])
        return col, m & ~hole
    def bracket(X, Y):
        u, v = local(X, Y, a[0], a[1], r0 * 1.15, r0 * 1.0)
        m = u * u + v * v <= 1
        col = ramp('steel', 0.45 + 0.4 * dome(u, v))
        rv = (u * u + v * v) < 0.12
        col[rv] = ramp('steel', 1.0)[rv]
        return col, m
    return [disc_piece(cx, cy, rx, ry, wall, top, side, 0, ink=PAN_INK), Piece(grip, PAN_INK), Piece(bracket, PAN_INK)]


def inside(body):
    cx, cy, rx, ry, _ = body
    return (cx, cy + 0.4, rx - 2.1, ry - 1.7)


def ellipse_mask(size, ell, grow=0.0):
    W, H = size; cx, cy, rx, ry = ell
    ys, xs = np.mgrid[0:H * SS, 0:W * SS]
    u = ((xs + .5) / SS - cx) / (rx + grow); v = ((ys + .5) / SS - cy) / (ry + grow)
    return (u * u + v * v <= 1).reshape(H, SS, W, SS).mean((1, 3)) >= 0.5


def composite(base, layer, clip):
    out = base.copy(); m = (layer[..., 3] > 0) & clip
    out[m] = layer[m]
    return out


# ---------------------------------------------------------------- fried contents (64 design, radius ~22 x 14)

def steak_piece(state, cx=32, cy=31, rx=17, ry=11, rot=-6, seed=500, thick=3.0):
    ns = Noise(seed, 0.5)
    def top(u, v, X, Y):
        lam = dome(u, v * 0.8, rot)
        g = 0.05 * ns(X, Y) + 0.02 * grain(X, Y, seed)
        rr = np.sqrt(u * u + v * v)
        if state == 'chopped':
            col = ramp('beef_raw', 0.35 + 0.55 * lam + g)
            fat = np.abs(np.sin(u * 5 + v * 3 + ns(X, Y))) > 0.94
            col[fat] = mix(col, ramp('beef_raw', 1.0), 0.6)[fat]
        elif state == 'cooking':
            col = ramp('beef_raw', 0.3 + 0.5 * lam + g)
            edge = rr > 0.68
            col[edge] = ramp('beef_cooked', 0.45 + 0.4 * lam + g)[edge]
        elif state == 'ready':
            col = ramp('beef_cooked', 0.3 + 0.6 * lam + g)
            for off in (-0.5, 0.0, 0.5):
                line = np.abs((u - off) + v * 0.6) < 0.08
                col[line] = ramp('beef_cooked', 0.05)[line]
        else:
            col = ramp('burnt', 0.15 + 0.5 * lam + g)
            ember = np.sin(X * 2.9 + Y * 2.1) > 0.97
            col[ember] = np.array([0.42, 0.16, 0.08])
        return col
    def side(dep, X, Y):
        name = {'chopped': 'beef_raw', 'cooking': 'beef_cooked', 'ready': 'beef_cooked', 'burnt': 'burnt'}[state]
        return ramp(name, 0.3 - 0.18 * dep)
    return disc_piece(cx, cy, rx, ry, thick, top, side, rot)


PAN_CUBES = [(22, 26, 10, 20), (37, 24, 9.5, -15), (45, 33, 9, 30), (29, 35, 10, 8), (16, 35, 9, -25)]
PAN_SLABS = [(23, 27, 11, 15), (40, 27, 10.5, -20), (31, 37, 11, 5)]


def fried(item, stage):
    st = 'raw' if stage == 'chopped' else stage
    if item == 'beef': pieces = [steak_piece(stage)]
    elif item == 'chicken': pieces = cubes(st, 'chicken', PAN_CUBES, 600)
    else: pieces = cubes(st, 'fish', PAN_SLABS, 700)
    if stage in ('cooking', 'ready'):
        pieces.append(oil_piece(stage))
    return pieces


def oil_piece(stage, seed=800):
    """Sizzling oil: a few bright droplets on the pan floor around the food."""
    rng = np.random.default_rng(seed + (stage == 'ready'))
    drops = [(rng.uniform(8, 56), rng.uniform(18, 46), rng.uniform(0.9, 1.6)) for _ in range(9)]
    def fn(X, Y):
        m = np.zeros(X.shape, bool); col = np.zeros(X.shape + (3,))
        for x, y, r in drops:
            u, v = local(X, Y, x, y, r, r * 0.75)
            d = u * u + v * v <= 1; m |= d
        col[:] = np.array([1.0, 0.95, 0.72]); return col, m
    return Piece(fn, None)


def pan_frames():
    F = {}
    for key, (size, body, handle) in PANS.items():
        W, H = size
        ins = inside(body)
        empty = render(pan_pieces(body, handle), size, 1.0, (W / 2, H / 2), (W / 2, H / 2))
        anchor = [round(ins[0], 1), round(ins[1], 1)]
        F[key] = (empty, [0.5, 0.5], {'contentAnchor': anchor, 'vessel': 'pan'})
        clip = ellipse_mask(size, ins, -0.2)
        s = (ins[2]) / 22.0
        for item in PAN_ITEMS:
            for stage in PAN_STAGES:
                layer = render(fried(item, stage), size, s, (ins[0], ins[1] + 0.3), (32, 31))
                F[f'{key}/{item}/{stage}'] = (composite(empty, layer, clip), [0.5, 0.5], {'contentAnchor': anchor, 'vessel': 'pan'})
    return F


# ---------------------------------------------------------------- noodles

def strands(size, ell, n, seed, colour, shadow, width=1.15, amp=1.0, clip_grow=-0.3, lie=0.0):
    """Wavy noodle strands inside an ellipse, drawn at SS: returns RGBA (no outline)."""
    W, H = size; cx, cy, rx, ry = ell
    rng = np.random.default_rng(seed)
    img = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    for k in range(n):
        y0 = cy + rng.uniform(-0.75, 0.85) * ry * (1 - lie) + lie * ry * rng.uniform(0.1, 0.8)
        x0 = cx - rx * rng.uniform(0.7, 1.0); x1 = cx + rx * rng.uniform(0.7, 1.0)
        f = rng.uniform(0.35, 0.7) * 6 / max(rx, 6); ph = rng.uniform(0, 6.3); a = rng.uniform(0.8, 1.6) * amp * ry / 6
        tilt = rng.uniform(-0.25, 0.25)
        pts = [(x, y0 + tilt * (x - cx) + a * math.sin(f * x * 2.2 + ph) + 0.4 * a * math.sin(f * x * 5.1 + ph * 2)) for x in np.linspace(x0, x1, 60)]
        for dy, c in ((0.75, shadow), (0.0, colour)):
            d.line([((x) * SS, (y + dy) * SS) for x, y in pts], fill=c, width=max(1, int(width * SS)))
    a = np.array(img).reshape(H, SS, W, SS, 4)
    cov = (a[..., 3] > 0).mean((1, 3))
    rgb = a[..., :3].astype(float).sum((1, 3)) / np.maximum((a[..., 3] > 0).sum((1, 3)), 1)[..., None]
    out = np.zeros((H, W, 4), np.uint8)
    m = (cov >= 0.4) & ellipse_mask(size, ell, clip_grow)
    out[m, :3] = rgb[m].astype(np.uint8); out[m, 3] = 255
    return out


def c255(name, t): return tuple(int(v * 255) for v in ramp(name, np.array([t]))[0])


def pot_contents(size, ell, stage, seed=900):
    """Noodles in the soup pot: dry bundle (raw), boiling water (cooking), cloudy water (ready), boiled dry (burnt)."""
    W, H = size; cx, cy, rx, ry = ell
    out = np.zeros((H, W, 4), np.uint8)
    inside_m = ellipse_mask(size, ell, -0.15)
    ys, xs = np.mgrid[0:H, 0:W]; u = (xs + .5 - cx) / rx; v = (ys + .5 - cy) / ry
    if stage in ('cooking', 'ready'):
        name = 'water' if stage == 'cooking' else 'starch'
        t = 0.45 + 0.25 * (-v) - 0.2 * np.clip(u, 0, 1) + 0.03 * grain(xs, ys, 3)
        water = (ramp(name, t) * 255).astype(np.uint8)
        out[inside_m, :3] = water[inside_m]; out[inside_m, 3] = 255
        rim = inside_m & ~ellipse_mask(size, ell, -1.2) & (v < 0)
        out[rim, :3] = c255(name, 0.95)
        n = max(3, int(rx * (0.45 if stage == 'cooking' else 0.75)))
        s = strands(size, ell, n, seed, c255('noodle_cooked', 0.82), c255('noodle_cooked', 0.35), width=1.1 if rx > 12 else 0.9)
        out = composite(out, s, s[..., 3] > 0)
        rng = np.random.default_rng(seed + 1)
        for _ in range(max(2, int(rx / 3)) if stage == 'cooking' else 1):           # boiling bubbles
            bx, by = cx + rng.uniform(-0.7, 0.7) * rx, cy + rng.uniform(-0.5, 0.6) * ry
            r = rng.uniform(0.9, 1.6) if rx > 12 else 0.8
            bu = (xs + .5 - bx) / r; bv = (ys + .5 - by) / r; ring = (bu * bu + bv * bv <= 1.3) & inside_m
            out[ring, :3] = c255(name, 1.0)
            dot = (np.abs(bu) < 0.5) & (np.abs(bv) < 0.5) & inside_m
            out[dot, :3] = c255(name, 0.6)
    elif stage == 'raw':
        s = strands(size, (cx, cy + ry * 0.2, rx * 0.8, ry * 0.45), max(4, int(rx * 0.5)), seed, c255('noodle', 0.82),
                    c255('noodle', 0.3), width=0.95, amp=0.08)
        out = composite(out, s, s[..., 3] > 0)
    else:
        lower = (cx, cy + ry * 0.25, rx * 0.86, ry * 0.62)
        clump = ellipse_mask(size, lower, 0) & inside_m
        t = 0.3 + 0.3 * (-((ys + .5 - lower[1]) / lower[3])) + 0.12 * Noise(seed, 0.8)(xs, ys) + 0.03 * grain(xs, ys, 5)
        col = (ramp('noodle_burnt', t) * 255).astype(np.uint8)
        out[clump, :3] = col[clump]; out[clump, 3] = 255
        s = strands(size, lower, max(3, int(rx * 0.4)), seed, c255('noodle_burnt', 0.75), c255('noodle_burnt', 0.1), width=0.9, amp=0.6)
        out = composite(out, s, (s[..., 3] > 0) & clump)
        char = clump & (Noise(seed + 2, 1.1)(xs, ys) > 0.9)
        out[char, :3] = (14, 9, 6)
    return out


def pot_frames():
    man = json.loads((GRID / 'manifest.json').read_text())['frames']; atlas = Image.open(GRID / 'atlas.png').convert('RGBA')
    F = {}
    for key, ell in POTS.items():
        x, y, w, h = man[key]['rect']; base = np.array(atlas.crop((x, y, x + w, y + h)))
        clip = ellipse_mask((w, h), ell, 0.3) & (base[..., 3] > 0)
        for stage in NOODLE_STAGES:
            layer = pot_contents((w, h), ell, stage)
            F[f'{key}/noodles/{stage}'] = (composite(base, layer, clip), [0.5, 0.5],
                                           {'contentAnchor': [ell[0], ell[1]], 'vessel': 'pot', 'base': f'grid-foundation-v1/{key}'})
    return F


def noodle_bundle(a=(13, 47), b=(52, 19), sticks=9, r=0.9, seed=910):
    """Dry noodles tied in a bundle with a paper band: separate sticks with staggered ends."""
    vx, vy = b[0] - a[0], b[1] - a[1]; L = math.hypot(vx, vy); nx, ny = -vy / L, vx / L; ux, uy = vx / L, vy / L
    rng = np.random.default_rng(seed)
    pitch = r * 2.0
    offs = [(k - (sticks - 1) / 2) * pitch for k in range(sticks)]
    ends = [(rng.uniform(-2.5, 1.0), rng.uniform(-1.0, 2.5)) for _ in offs]
    half = offs[-1] + r
    def body(X, Y):
        m = np.zeros(X.shape, bool); col = np.zeros(X.shape + (3,))
        along = (X - a[0]) * ux + (Y - a[1]) * uy
        for k in np.argsort([-o for o in offs]):                 # back sticks first
            o = offs[k]; e0, e1 = ends[k]
            fan = 1 + 0.35 * np.clip(np.abs(along / L - 0.5) * 2 - 0.3, 0, 1)   # spread toward both ends
            p = (X - a[0]) * nx + (Y - a[1]) * ny
            d = (p - o * fan) / r
            mk = (np.abs(d) <= 1) & (along >= e0 * 1.0 - 0.0 + min(0, e0)) & (along <= L + e1)
            mk &= along >= e0
            across = o / half
            lam = np.clip(0.6 - 0.45 * across + 0.35 * (1 - d * d) - 0.25 * (d > 0.4), 0, 1)
            c = ramp('noodle', 0.15 + 0.78 * lam + 0.02 * grain(X, Y, seed + k))
            tip = mk & ((along - e0 < 1.1) | (L + e1 - along < 1.1))
            c[tip] = ramp('noodle', 0.95)[tip]                    # cut ends catch the light
            new = mk & ~m
            col[new] = c[new]; m |= mk
            edge = mk & (d > 0.55)
            col[edge] = ramp('noodle', 0.22)[edge]
        return col, m
    def band(X, Y):
        along = (X - a[0]) * ux + (Y - a[1]) * uy; p = (X - a[0]) * nx + (Y - a[1]) * ny
        w = half * 1.18 + 0.8
        mm = (np.abs(along - L * 0.5) < 3.4) & (np.abs(p) <= w)
        across = p / w
        col = ramp('paper', 0.3 + 0.6 * np.clip(0.65 - 0.55 * across, 0, 1) + 0.02 * grain(X, Y, 3))
        stripe = np.abs(along - L * 0.5) < 1.0
        col[stripe] = ramp('band', 0.35 + 0.45 * np.clip(0.6 - 0.5 * across, 0, 1))[stripe]
        return col, mm
    return [Piece(body), Piece(band)]


def coil_texture(X, Y, region, n, seed, width=1.6):
    """Curly noodle coils drawn one after another on the supersampled grid, each with a dark edge so the later
    strand reads on top. Returns a label map: 0 none, 1 strand edge, 2 strand, 3 strand highlight."""
    x0, y0 = X[0, 0], Y[0, 0]; dx = X[0, 1] - X[0, 0]; dy = Y[1, 0] - Y[0, 0]
    cx, cy, rx, ry = region; rng = np.random.default_rng(seed)
    img = Image.new('L', (X.shape[1], X.shape[0]), 0); d = ImageDraw.Draw(img)
    w = max(1, int(round(width / dx))); e = max(1, int(round(0.55 / dx)))
    for k in range(n):
        while True:
            u, v = rng.uniform(-1, 1, 2)
            if u * u + v * v < 0.9: break
        px, py = cx + u * rx, cy + v * ry
        ax = rng.uniform(4.0, 9.0); ay = ax * rng.uniform(0.45, 0.6)
        start = rng.uniform(0, 360); sweep = rng.uniform(160, 320)
        box = [((px - ax) - x0) / dx, ((py - ay) - y0) / dy, ((px + ax) - x0) / dx, ((py + ay) - y0) / dy]
        d.arc(box, start, start + sweep, fill=1, width=w + 2 * e)
        inner = [box[0] + e, box[1] + e, box[2] - e, box[3] - e]
        d.arc(inner, start + 4, start + sweep - 4, fill=2, width=w)
        hi = [inner[0] + w * 0.15, inner[1] - w * 0.1, inner[2] - w * 0.15, inner[3] - w * 0.1]
        d.arc(hi, start + 10, start + sweep - 10, fill=3, width=max(1, w // 3))
    return np.array(img)


def noodle_nest(cx=32, cy=35, rx=21, ry=12.5, height=7, state='ready', seed=920, n=None):
    """Cooked noodles heaped on a surface as curly strands; burnt = boiled dry, browned and stuck together."""
    name = 'noodle_cooked' if state == 'ready' else 'noodle_burnt'
    n = n or int(rx * ry / 5)
    def fn(X, Y):
        u, v = local(X, Y, cx, cy, rx, ry)
        rr = u * u + v * v
        core = rr <= 0.7 + 0.05 * Noise(seed + 1, 1.0)(X, Y)
        hgt = np.sqrt(np.clip(1 - rr, 0, 1))
        lam = dome(u * 0.85, v * 0.85 - 0.12 * hgt)
        lab = coil_texture(X, Y, (cx, cy - 0.5, rx * 0.88, ry * 0.84), n, seed)
        m = core | ((lab > 0) & (rr <= 1.15))                           # loops spill over the edge of the heap
        col = ramp(name, 0.05 + 0.15 * lam)                              # deep gaps between strands
        for lv, lo, hi in ((1, 0.12, 0.2), (2, 0.38, 0.55), (3, 0.72, 0.28)):
            sel = lab == lv
            col[sel] = ramp(name, lo + hi * lam + 0.02 * grain(X, Y, seed))[sel]
        if state != 'ready':
            char = (Noise(seed + 2, 0.7)(X, Y) > 0.5) & (lab != 3)
            col[char] = mix(col, ramp('burnt', 0.1 + 0.2 * lam), 0.65)[char]
        return col, m
    return [Piece(fn)]


def noodle_frames():
    F = {}
    raw = render(noodle_bundle(), (64, 64))
    F['food/noodles_raw'] = (raw, [0.5, 0.5], {})
    x0, y0, x1, y1 = bbox(raw); s = min(40 / (x1 - x0), 37 / (y1 - y0))
    F['modular/source_noodles'] = (render(noodle_bundle(), (64, 96), s, (32, 41.5), ((x0 + x1) / 2, (y0 + y1) / 2)), [0.5, 1 / 3], {})
    F['food/noodles_ready'] = (render(noodle_nest(), (64, 64)), [0.5, 0.5], {})
    F['food/noodles_burnt'] = (render(noodle_nest(32, 37, 21, 11, 5, 'burnt', 930), (64, 64)), [0.5, 0.5], {})
    lay = render(noodle_nest(23, 14, 21.5, 9.5, 4, 'ready', 940), (48, 32), 1.0, (24, 16), (23, 15))
    F['feedback/noodles'] = (crop_to_content(lay), [0.5, 0.5], {})
    # 32 px stages for the loose pot-contents path (drawn at 20x20 over the pot)
    F['ingredients/noodles/raw'] = (render(noodle_bundle(), (32, 32), 0.5, (16, 16), (32, 32.5)), [0.5, 0.5], {})
    for stage in ('cooking', 'ready', 'burnt'):
        ell = (16, 16.5, 13, 9)
        base = render([puddle(stage, ell)], (32, 32), 1.0, (16, 16), (16, 16))
        clip = ellipse_mask((32, 32), ell, -1.0)
        F[f'ingredients/noodles/{stage}'] = (composite(base, pot_contents((32, 32), (ell[0], ell[1], ell[2] - 1, ell[3] - 1), stage, 950), clip),
                                             [0.5, 0.5], {})
    return F


def puddle(stage, ell):
    """Outline and base for the loose 32 px noodle stages: water (cooking, ready) or a dry pan bottom (burnt)."""
    cx, cy, rx, ry = ell
    name = {'cooking': 'water', 'ready': 'starch', 'burnt': 'iron'}[stage]
    def fn(X, Y):
        u, v = local(X, Y, cx, cy, rx, ry)
        return ramp(name, 0.4 - 0.2 * v + 0.02 * grain(X, Y, 2)), u * u + v * v <= 1
    return Piece(fn)


# ---------------------------------------------------------------- noodle dishes

def beef_slices(state, spots, seed=960):
    out = []
    for k, (x, y, rot) in enumerate(spots):
        out.append(steak_piece('ready' if state == 'ready' else 'burnt', x, y, 5.8, 2.4, rot, seed + k, thick=1.2))
    return out


def noodle_dish(dish, state, seed=970, plated=True):
    """Plated beef or chicken noodles on a 48 px canvas: noodle heap, the meat on top, scallion rings.
    plated=False leaves the plate out (the v1 build puts the food on its own native plate)."""
    nest_state = 'ready' if state == 'ready' else 'burnt'
    pieces = ([plate(24, 27, 21.5, 13.8)] if plated else []) + noodle_nest(24, 25, 15.5, 9.2, 5, nest_state, seed)
    if dish == 'beef_noodles':
        pieces += beef_slices(state, [(27, 19, 18), (33, 22.5, -12), (27, 26, 24)])
    else:
        st = 'ready' if state == 'ready' else 'burnt'
        pieces += cubes(st, 'chicken', [(27, 19, 5.4, 20), (33, 22, 5.2, -15), (28, 25, 5.4, 25)], seed)
    rng = np.random.default_rng(seed + 3)
    for k, (x, y) in enumerate([(15, 25), (20, 29), (36, 27), (19, 19)]):
        ring = scallion_ring(x + rng.uniform(-0.6, 0.6), y, 1.9, seed + 10 + k, white=(k % 3 == 1))
        if state == 'burnt': ring.ink = (40, 30, 14)
        pieces.append(ring)
    return render(pieces, (48, 48), 1.0, (24, 24), (24, 24))


def dish_frames(existing):
    F = {}
    for dish in ('beef_noodles', 'chicken_noodles'):
        for state in ('ready', 'burnt'):
            F[f'dishes/{dish}/{state}'] = (noodle_dish(dish, state), [0.5, 0.5], {})
    for state in ('ready', 'burnt'):                      # the fried-fish dish is called fish_steak in the recipes
        F[f'dishes/fish_steak/{state}'] = (existing[f'dishes/fish/{state}'][0], [0.5, 0.5], {'alias': f'dishes/fish/{state}'})
    return F


def frames(existing):
    F = {}
    F.update(noodle_frames()); F.update(pan_frames()); F.update(pot_frames()); F.update(dish_frames(existing))
    return F
