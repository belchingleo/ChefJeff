"""Ingredient pack v1: cucumber, onion, cheese, chicken, fish, flatbread, scallion and noodles in the current food style,
plus the frying pan and the vessels with food cooking in them (scripts/art/pan_noodles.py).

The current food art (burger-food, kitchen-modules-v2 source icons, action-feedback layers, beef stages) is
painterly pixel art: soft dome shading lit from the top left, a warm highlight, about a thousand colours per
sheet, hard alpha and a one-pixel near-black outline around every separate piece. This script draws each item
as shaded shapes at 4x supersampling, reduces to the target size, then outlines every piece on its own so piles
read as separate pieces, as the chopped tomato and lettuce do.

Frames follow the conventions of the current four ingredients:
  food/<item>_raw, food/<item>_chopped      64x64, content about 48 px, drawn at 30x30 on a counter or board
  modular/source_<item>                     64x96 source-box icon, alpha_bbox x 12..52, anchor (0.5, 1/3)
  feedback/<item>                           about 46x30 plated layer, drawn at 34x22 in an assembled dish
  ingredients/<item>/<stage>                32x32 heat stages for chicken and fish, drawn at 20x20 inside a pot
  dishes/<item>/{ready,burnt}               32x32 plated heated dish, like dishes/steak

Run: python3 scripts/art/ingredient_pack.py  (needs Pillow and numpy)
"""
import json, math, sys, uuid
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'cocos-kitchen/assets/resources/art/ingredient-pack-v1'
SS = 4                                            # supersampling factor
INK = (18, 4, 3)                                  # outline colour of the current food art
PLATE_INK = (12, 20, 42)                          # plate rim outline, as dishes/steak
LIGHT = np.array([-0.45, -0.62, 0.64]); LIGHT = LIGHT / np.linalg.norm(LIGHT)
ITEMS = ['cucumber', 'onion', 'cheese', 'chicken', 'fish', 'flatbread', 'scallion']
HEATED = ['chicken', 'fish']

# ---------------------------------------------------------------- colour helpers

RAMPS = {
    'cuke_skin': [(16, 52, 24), (30, 88, 34), (52, 128, 46), (98, 168, 72), (170, 214, 128)],
    'cuke_flesh': [(150, 196, 96), (196, 226, 150), (222, 240, 186), (240, 250, 214)],
    'onion_skin': [(54, 14, 48), (98, 28, 84), (146, 52, 124), (192, 100, 168), (236, 182, 222)],
    'onion_flesh': [(196, 160, 198), (228, 208, 230), (246, 236, 246), (255, 250, 255)],
    'onion_paper': [(120, 84, 52), (172, 128, 82), (214, 178, 128), (240, 214, 170)],
    'cheese': [(168, 98, 8), (224, 150, 26), (246, 194, 54), (255, 222, 106), (255, 244, 178)],
    'cheese_rind': [(150, 82, 10), (204, 124, 24), (232, 160, 40), (248, 196, 84)],
    'chick_raw': [(168, 92, 92), (214, 134, 128), (238, 170, 158), (250, 202, 188), (255, 230, 220)],
    'golden': [(108, 52, 14), (168, 96, 30), (216, 146, 58), (242, 192, 104), (255, 228, 164)],
    'burnt': [(14, 10, 8), (36, 26, 20), (62, 44, 32), (94, 68, 48), (130, 100, 74)],
    'fish_back': [(28, 44, 70), (52, 78, 112), (92, 124, 160), (150, 180, 208), (214, 230, 242)],
    'fish_belly': [(150, 160, 170), (196, 206, 214), (226, 232, 236), (246, 248, 250)],
    'fish_flesh': [(206, 150, 138), (234, 190, 176), (248, 218, 206), (255, 238, 230)],
    'fish_skin': [(70, 84, 104), (118, 134, 154), (170, 184, 198), (214, 224, 232)],
    'bread': [(150, 96, 44), (206, 156, 92), (236, 200, 140), (248, 226, 180), (255, 244, 214)],
    'toast': [(96, 48, 16), (146, 84, 34), (196, 132, 62)],
    'scal_dark': [(18, 70, 24), (34, 108, 34), (62, 148, 48), (110, 186, 78), (172, 222, 130)],
    'scal_white': [(170, 182, 150), (214, 224, 196), (238, 244, 226), (252, 255, 244)],
    'root': [(120, 96, 60), (176, 150, 104), (220, 200, 156)],
    'plate': [(150, 160, 178), (206, 212, 222), (236, 238, 242), (252, 252, 254)],
    'band': [(120, 20, 24), (190, 44, 44), (232, 92, 84)],
    'stem': [(64, 74, 30), (104, 116, 46), (150, 160, 80)],
}


def ramp(name, t):
    """Interpolate a dark-to-light ramp at t in 0..1 (array)."""
    stops = np.array(RAMPS[name], float) / 255
    if np.ndim(t) == 0: return Flat(ramp(name, np.array([t]))[0])
    t = np.clip(t, 0, 1) * (len(stops) - 1)
    i = np.clip(np.floor(t).astype(int), 0, len(stops) - 2); f = (t - i)[..., None]
    return stops[i] * (1 - f) + stops[i + 1] * f


class Flat(np.ndarray):
    """A single colour that can be indexed by any mask, so ramp(name, 0.5)[mask] reads like the array case."""
    def __new__(cls, rgb): return np.asarray(rgb, float).view(cls)
    def __getitem__(self, k):
        if isinstance(k, np.ndarray) and k.dtype == bool: return np.asarray(self)
        return np.asarray(self)[k]
    def __array_wrap__(self, out, context=None, return_scalar=False):
        return out.view(Flat) if out.shape == (3,) else np.asarray(out)


def mix(a, b, f):
    f = np.asarray(f, float)
    if f.ndim and f.shape[-1:] != (1,): f = f[..., None]
    return a * (1 - f) + b * f


class Noise:
    """Smooth deterministic noise in design pixels: a sum of random plane waves."""
    def __init__(self, seed, freq=0.35, octaves=7):
        r = np.random.default_rng(seed)
        self.w = [(r.normal(0, freq * (1.6 ** (k % 3))), r.normal(0, freq * (1.6 ** (k % 3))), r.uniform(0, 6.3)) for k in range(octaves)]
    def __call__(self, X, Y):
        return sum(np.sin(a * X + b * Y + p) for a, b, p in self.w) / math.sqrt(len(self.w))


def grain(X, Y, seed=0):
    """Per-design-pixel hash grain in -1..1, the slight painterly speckle of the current art."""
    h = np.sin(np.floor(X * 1.0) * 12.9898 + np.floor(Y * 1.0) * 78.233 + seed * 3.7) * 43758.5453
    return (h - np.floor(h)) * 2 - 1


# ---------------------------------------------------------------- shapes (design pixel coordinates)

def local(X, Y, cx, cy, rx, ry, rot=0.0):
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    dx, dy = X - cx, Y - cy
    return (dx * c + dy * s) / rx, (-dx * s + dy * c) / ry


def dome(u, v, rot=0.0):
    """Lambert term for an ellipsoid cap, normal from local (u, v) rotated back to screen."""
    r2 = np.clip(u * u + v * v, 0, 1); nz = np.sqrt(1 - r2)
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    nx, ny = u * c - v * s, u * s + v * c
    return np.clip(nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2], 0, 1)


def spec(u, v, at=(-0.38, -0.45), size=0.05):
    return np.exp(-((u - at[0]) ** 2 + (v - at[1]) ** 2) / size)


def poly_mask(X, Y, pts):
    """Polygon coverage on the supersampled grid (design coordinates mapped back through the grid)."""
    x0, y0 = X[0, 0], Y[0, 0]; dx = X[0, 1] - X[0, 0]; dy = Y[1, 0] - Y[0, 0]
    img = Image.new('L', (X.shape[1], X.shape[0]), 0)
    ImageDraw.Draw(img).polygon([((px - x0) / dx, (py - y0) / dy) for px, py in pts], fill=255)
    return np.array(img) > 127


def capsule(X, Y, a, b, r0, r1=None):
    """Distance field for a tapered capsule from a (radius r0) to b (radius r1); returns (inside, t, d, n)."""
    r1 = r0 if r1 is None else r1
    ax, ay = a; bx, by = b; vx, vy = bx - ax, by - ay; L2 = vx * vx + vy * vy
    t = np.clip(((X - ax) * vx + (Y - ay) * vy) / L2, 0, 1)
    px, py = ax + vx * t, ay + vy * t; r = r0 + (r1 - r0) * t
    dx, dy = (X - px) / r, (Y - py) / r
    d2 = dx * dx + dy * dy
    nz = np.sqrt(np.clip(1 - d2, 0, 1))
    lam = np.clip(dx * LIGHT[0] + dy * LIGHT[1] + nz * LIGHT[2], 0, 1)
    side = (-(X - ax) * vy + (Y - ay) * vx) / math.sqrt(L2) / r   # signed across-axis coordinate
    return d2 <= 1, t, side, lam


# ---------------------------------------------------------------- piece rendering

class Piece:
    """A separately outlined piece: fn(X, Y) -> (rgb float HxWx3, mask bool)."""
    def __init__(self, fn, ink=INK):
        self.fn, self.ink = fn, ink


def render(pieces, size, scale=1.0, centre=None, design_centre=(32, 32), outer=None):
    """Render pieces back to front; each piece is reduced from SS, then outlined over what lies beneath."""
    W, H = size; centre = centre or (W / 2, H / 2)
    ys, xs = np.mgrid[0:H * SS, 0:W * SS]
    X = ((xs + 0.5) / SS - centre[0]) / scale + design_centre[0]
    Y = ((ys + 0.5) / SS - centre[1]) / scale + design_centre[1]
    out = np.zeros((H, W, 4), np.uint8)
    for p in pieces:
        rgb, m = p.fn(X, Y)
        m = m.astype(float)
        cov = m.reshape(H, SS, W, SS).mean((1, 3))
        col = (rgb * m[..., None]).reshape(H, SS, W, SS, 3).sum((1, 3)) / np.maximum(m.reshape(H, SS, W, SS).sum((1, 3)), 1e-6)[..., None]
        M = cov >= 0.5
        if p.ink is not None:
            ring = dilate(M) & ~M
            out[ring] = (*p.ink, 255)
        out[M, :3] = np.clip(col[M] * 255 + 0.5, 0, 255).astype(np.uint8); out[M, 3] = 255
    if outer is not None:
        A = out[..., 3] > 0; ring = dilate(A) & ~A; out[ring] = (*outer, 255)
    return out


def dilate(M):
    P = np.pad(M, 1)
    return M | P[:-2, 1:-1] | P[2:, 1:-1] | P[1:-1, :-2] | P[1:-1, 2:]


# ---------------------------------------------------------------- generic pieces

def disc_piece(cx, cy, rx, ry, thick, top, side, rot=0.0, hole=None, shape=None, ink=INK):
    """A flat slab seen from above at an angle: top face drawn by top(u, v, X, Y), side band by side(t, X, Y).

    shape(u, v) -> bool overrides the elliptic outline (e.g. a rounded square); hole=(hx, hy) cuts an inner
    ellipse of those relative radii (onion rings)."""
    def inside(u, v):
        m = (u * u + v * v <= 1) if shape is None else shape(u, v)
        if hole is not None: m &= (u / hole[0]) ** 2 + (v / hole[1]) ** 2 > 1
        return m
    def fn(X, Y):
        u, v = local(X, Y, cx, cy, rx, ry, rot)
        mt = inside(u, v)
        ms = np.zeros_like(mt); depth = np.zeros(X.shape)
        n = max(2, int(thick * SS * 2))
        for k in range(1, n + 1):
            dy = thick * k / n
            us, vs = local(X, Y - dy, cx, cy, rx, ry, rot)
            hit = inside(us, vs) & ~ms
            depth[hit] = k / n; ms |= hit
        ms &= ~mt
        rgb = np.zeros(X.shape + (3,))
        rgb[ms] = side(depth, X, Y)[ms]
        rgb[mt] = top(u, v, X, Y)[mt]
        return rgb, mt | ms
    return Piece(fn, ink)


def block_piece(cx, cy, w, d, h, faces, rot=0.0, ink=INK, squash=0.55):
    """A small box in 3/4 view, turned by rot on the ground plane: faces(name, u, v, X, Y, lit) -> rgb.

    name is 'top' or 'side'; lit is 0..1 for how much a side faces the light (left front is lit)."""
    c, s_ = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    def P(x, y): return (cx + x * c - y * s_, cy + (x * s_ + y * c) * squash)
    corners = [P(-w / 2, -d / 2), P(w / 2, -d / 2), P(w / 2, d / 2), P(-w / 2, d / 2)]
    def fn(X, Y):
        rgb = np.zeros(X.shape + (3,)); allm = np.zeros(X.shape, bool)
        u = (X - cx) / max(w, 1); v = (Y - cy) / max(d * squash, 1)
        for i in range(4):
            p0, p1 = corners[i], corners[(i + 1) % 4]
            ex, ey = p1[0] - p0[0], (p1[1] - p0[1]) / squash
            nx, ny = ey, -ex                           # outward normal on the ground plane (corners run clockwise)
            n = math.hypot(nx, ny); nx, ny = nx / n, ny / n
            if ny <= 0.05: continue                    # faces away from the viewer
            m = poly_mask(X, Y, [p0, p1, (p1[0], p1[1] + h), (p0[0], p0[1] + h)]) & ~allm
            lit = float(np.clip(0.5 - 0.5 * nx, 0, 1))
            rgb[m] = faces('side', u, v, X, Y, lit)[m]; allm |= m
        top = poly_mask(X, Y, corners)
        rgb[top] = faces('top', u, v, X, Y, 1.0)[top]
        return rgb, allm | top
    return Piece(fn, ink)


def tone(name, lam, X, Y, seed=0, n=0.06, g=0.025, lo=0.12, hi=0.92):
    t = lo + (hi - lo) * lam + n * Noise(seed)(X, Y) + g * grain(X, Y, seed)
    return ramp(name, t)


# ---------------------------------------------------------------- cucumber

def cucumber_raw():
    a, b = (13, 44), (51, 21)
    ns = Noise(11, 0.5)
    def body(X, Y):
        m, t, side, lam = capsule(X, Y, a, b, 8.6, 7.6)
        stripe = 0.5 + 0.5 * np.sin(side * 7.5 + ns(X, Y) * 0.6)
        col = tone('cuke_skin', lam, X, Y, 3, 0.05, 0.03, 0.1, 0.86)
        col = mix(col, ramp('cuke_skin', 0.25 + 0.55 * lam), 0.35 * (stripe > 0.72))
        # bumps: small lighter dots with a darker lower edge
        bx = np.floor(X / 4.2 + np.floor(Y / 3.6) * 0.5); by = np.floor(Y / 3.6)
        h = np.sin(bx * 91.7 + by * 47.3) * 1e4; h -= np.floor(h)
        fx = X / 4.2 + np.floor(Y / 3.6) * 0.5 - bx - 0.5; fy = Y / 3.6 - by - 0.5
        dot = (fx * fx + fy * fy < 0.05) & (h > 0.55)
        col[dot] = mix(col, ramp('cuke_skin', 0.95), 0.55)[dot]
        col = col + 0.18 * spec(-side, (t - 0.35) * 3, (0.55, 0), 0.08)[..., None] * (lam[..., None] > 0.6)
        return np.clip(col, 0, 1), m
    def stem(X, Y):
        u, v = local(X, Y, 52.5, 19.6, 2.6, 2.1, -30)
        m = u * u + v * v <= 1
        return tone('stem', dome(u, v, -30), X, Y, 4, 0.03, 0.02, 0.05, 0.95), m
    def blossom(X, Y):
        u, v = local(X, Y, 11.6, 45.2, 2.2, 1.9, -30)
        return tone('cuke_flesh', dome(u, v), X, Y, 5, 0.02, 0.02, 0.25, 0.9), u * u + v * v <= 1
    return [Piece(body), Piece(stem), Piece(blossom, None)]


def cuke_slice(cx, cy, r=8.4, rot=0.0, tilt=0.62, seed=0):
    ns = Noise(seed, 0.9)
    def top(u, v, X, Y):
        rr = np.sqrt(u * u + v * v)
        col = ramp('cuke_flesh', 0.55 + 0.35 * (1 - rr) + 0.05 * ns(X, Y) - 0.18 * (v > 0) * v)
        rim = rr > 0.82
        col[rim] = ramp('cuke_skin', 0.2 + 0.35 * (1 - v[rim]) * 0.5)
        mid = (rr > 0.72) & ~rim
        col[mid] = mix(col, ramp('cuke_flesh', 0.15), 0.6)[mid]
        # seed bed: three lobes with pale seeds
        ang = np.arctan2(v, u)
        lobe = (rr < 0.48 + 0.08 * np.cos(3 * ang)) & (rr > 0.08)
        col[lobe] = mix(col, ramp('cuke_flesh', 0.95), 0.5)[lobe]
        seeds = (np.abs(np.sin(3 * ang)) > 0.86) & (np.abs(rr - 0.3) < 0.09)
        col[seeds] = ramp('cuke_flesh', 1.0)[seeds] * 0.97
        col[seeds & (v > 0)] *= 0.93
        return col
    def side(dep, X, Y): return ramp('cuke_skin', 0.38 - 0.25 * dep)
    return disc_piece(cx, cy, r, r * tilt, 1.8, top, side, rot)


def cucumber_chopped():
    spots = [(22, 30, -12), (39, 26, 8), (31, 38, 4), (16, 43, -6), (46, 40, 14), (30, 48, -3)]
    return [cuke_slice(x, y, 8.6, r, 0.6, k + 20) for k, (x, y, r) in enumerate(sorted(spots, key=lambda s: s[1]))]


def cucumber_layer():
    xs = [9, 18.5, 28, 37.5]
    return [cuke_slice(x, 15 - abs(x - 23) * 0.06, 8.6, (x - 23) * 0.8, 0.5, 40 + i) for i, x in enumerate(xs)]


# ---------------------------------------------------------------- onion

def onion_raw():
    ns = Noise(21, 0.6)
    def bulb(X, Y):
        u, v = local(X, Y, 32, 37, 19, 16.5)
        # taper the top into a neck
        w = np.where(v < -0.15, 1 - 0.55 * (np.clip(-v - 0.15, 0, None) / 0.85) ** 1.3, 1.0)
        uu = u / np.maximum(w, 0.2)
        m = (uu * uu + v * v <= 1)
        neck = poly_mask(X, Y, [(29.4, 22.5), (34.6, 22.5), (33.2, 15.5), (32, 12), (30.8, 15.5)])
        lam = np.where(m, dome(uu * 0.92, v), 0.6 + 0.3 * ((32 - X) / 3))
        col = tone('onion_skin', lam, X, Y, 22, 0.05, 0.03, 0.12, 0.9)
        mer = uu / np.sqrt(np.clip(1 - np.clip(v, -0.95, 0.95) ** 2, 0.05, 1))
        stripes = np.abs(np.sin(mer * 5.4 + ns(X, Y) * 0.4)) > 0.9
        col[stripes] = mix(col, ramp('onion_skin', 0.12 + 0.4 * lam), 0.55)[stripes]
        hl = spec(uu, v, (-0.42, -0.35), 0.035)
        col = col + 0.35 * hl[..., None] * np.array([1, 0.9, 1])
        return np.clip(col, 0, 1), m | neck
    def tip(X, Y):
        m = poly_mask(X, Y, [(30.6, 15.6), (33.4, 15.6), (33.6, 10.5), (34.6, 7.6), (32.3, 9.4), (31.0, 11)])
        return tone('onion_paper', 0.45 + 0.4 * (33 - X) / 3, X, Y, 23, 0.05, 0.05), m
    def roots(X, Y):
        m = np.zeros(X.shape, bool)
        for k, ang in enumerate((-50, -25, -5, 15, 35, 55)):      # root hairs fanning out under the bulb
            L = 4.5 + (k % 2) * 1.5
            mk, *_ = capsule(X, Y, (32 + ang * 0.05, 52.0), (32 + ang * 0.13, 52 + L), 0.75)
            m |= mk
        return tone('root', 0.6 + 0.3 * (34 - X) / 6, X, Y, 24, 0.05, 0.05), m
    return [Piece(roots), Piece(bulb), Piece(tip)]


def onion_ring(cx, cy, r=8.0, rot=0.0, tilt=0.6, seed=0, thick=1.6):
    def top(u, v, X, Y):
        rr = np.sqrt(u * u + v * v)
        col = ramp('onion_flesh', 0.55 + 0.4 * (rr - 0.62) / 0.38 - 0.2 * (v > 0) * v + 0.04 * grain(X, Y, seed))
        edge = rr > 0.84
        col[edge] = ramp('onion_skin', 0.45 + 0.3 * (0 - v[edge]))
        inner = rr < 0.69
        col[inner] = mix(col, ramp('onion_skin', 0.85), 0.45)[inner]
        return col
    def side(dep, X, Y): return ramp('onion_flesh', 0.5 - 0.35 * dep)
    return disc_piece(cx, cy, r, r * tilt, thick, top, side, rot, hole=(0.6, 0.6))


def onion_chunk(cx, cy, s=4.6, rot=0.0, seed=0):
    def faces(name, u, v, X, Y, lit):
        g = 0.03 * grain(X, Y, seed)
        if name == 'top':
            col = ramp('onion_flesh', 0.82 + g - 0.2 * v)
            band = v < -0.25
            col[band] = ramp('onion_skin', 0.55 + g)[band]
            return col
        return ramp('onion_flesh', 0.25 + 0.25 * lit + g)
    return block_piece(cx, cy, s, s * 1.3, 2.6, faces, rot)


def onion_chopped():
    ps = [onion_ring(24, 27, 9.0, -8, 0.6, 1), onion_ring(40, 31, 8.2, 10, 0.62, 2),
          onion_chunk(14, 38, 5, -10, 3), onion_ring(29, 39, 8.6, 4, 0.58, 4),
          onion_chunk(46, 42, 5.2, 12, 5), onion_chunk(21, 47, 5, 6, 6), onion_chunk(36, 48, 5.2, -14, 7)]
    return ps


def onion_layer():
    return [onion_ring(12, 15, 9.6, -6, 0.48, 11, 1.4), onion_ring(34, 15, 9.6, 6, 0.48, 12, 1.4),
            onion_ring(23, 16.5, 9.8, 0, 0.5, 13, 1.4)]


# ---------------------------------------------------------------- cheese

def holes(X, Y, spots):
    m = np.zeros(X.shape, bool); lip = np.zeros(X.shape, bool)
    for hx, hy, rx, ry in spots:
        u, v = local(X, Y, hx, hy, rx, ry)
        h = u * u + v * v <= 1; m |= h
        lip |= h & (v > 0.25)
    return m, lip


def cheese_raw():
    A, B, C, h = (8.5, 37.5), (44.5, 16.5), (56, 27.5), 13.5
    def body(X, Y):
        top = poly_mask(X, Y, [A, B, C])
        front = poly_mask(X, Y, [A, C, (C[0], C[1] + h), (A[0], A[1] + h)])
        end = poly_mask(X, Y, [C, B, (B[0], B[1] + h), (C[0], C[1] + h)]) & ~front
        rgb = np.zeros(X.shape + (3,))
        g = 0.02 * grain(X, Y, 31) + 0.04 * Noise(31, 0.4)(X, Y)
        rgb[top] = ramp('cheese', 0.82 + g - 0.12 * (X - 8) / 48)[top]
        rgb[front] = ramp('cheese', 0.56 + g - 0.16 * (Y - (A[1] + (X - A[0]) * (C[1] - A[1]) / (C[0] - A[0]))) / h)[front]
        rgb[end] = ramp('cheese_rind', 0.45 + g - 0.1 * (Y - 20) / 20)[end]
        rind = end & (X > C[0] - 1.6)
        rgb[rind] = ramp('cheese_rind', 0.25 + g)[rind]
        # bright top edge where top meets front
        edge = top & (np.abs((Y - A[1]) - (X - A[0]) * (C[1] - A[1]) / (C[0] - A[0])) < 0.9)
        rgb[edge] = ramp('cheese', 1.0)[edge]
        ht, lt = holes(X, Y, [(27, 27.5, 3.2, 1.6), (39.5, 24.5, 2.2, 1.1), (18, 33, 1.7, 0.9), (47, 25.5, 1.4, 0.8)])
        hf, lf = holes(X, Y, [(20, 42, 2.4, 2.6), (35, 39.5, 3.1, 3.0), (48.5, 36, 1.8, 2.0), (27, 46, 1.4, 1.5), (13, 44, 1.2, 1.4)])
        for hm, lm, base in ((ht & top, lt & top, 0.42), (hf & front, lf & front, 0.3)):
            rgb[hm] = ramp('cheese', base + 0.02 * grain(X, Y, 3))[hm]
            rgb[lm] = ramp('cheese', base + 0.3)[lm]
        return rgb, top | front | end
    return [Piece(body)]


def rsquare(k=0.32):
    def shape(u, v):
        return (np.maximum(np.abs(u) - (1 - k), 0) ** 2 + np.maximum(np.abs(v) - (1 - k), 0) ** 2 <= k * k) & (np.abs(u) <= 1) & (np.abs(v) <= 1)
    return shape


def cheese_slice(cx, cy, r=10.5, rot=0.0, tilt=0.6, seed=0, droop=False):
    sh = rsquare(0.22)
    def top(u, v, X, Y):
        g = 0.02 * grain(X, Y, seed) + 0.035 * Noise(seed, 0.5)(X, Y)
        col = ramp('cheese', 0.78 + g - 0.16 * (u + v) * 0.5)
        hm, lm = holes(X, Y, [(cx - r * 0.35, cy - r * 0.15, 1.6, 0.9), (cx + r * 0.4, cy + r * 0.12, 1.3, 0.8), (cx + r * 0.05, cy + r * 0.32, 1.0, 0.6)])
        col[hm] = ramp('cheese', 0.45)[hm]; col[lm] = ramp('cheese', 0.7)[lm]
        if droop:
            corner = (np.abs(u) > 0.62) & (v > 0.2)
            col[corner] = mix(col, ramp('cheese', 0.5), 0.6)[corner]
        return col
    def side(dep, X, Y): return ramp('cheese', 0.42 - 0.2 * dep)
    return disc_piece(cx, cy, r, r * tilt, 1.4, top, side, rot, shape=sh)


def cheese_chopped():
    """Three slices fanned like cards."""
    return [cheese_slice(24, 27, 11.5, -6, 0.56, 1), cheese_slice(32, 34, 11.5, 4, 0.56, 2), cheese_slice(40, 41, 11.5, 12, 0.56, 3)]


def cheese_layer():
    """A slice laid diamond-wise on a patty, its left, right and front corners folded down over the edge."""
    top_pts = [(23, 1.5), (43.5, 9.5), (23, 17.5), (2.5, 9.5)]
    flaps = [[(2.5, 9.5), (7.5, 11.4), (5.5, 16.6), (1.2, 15.4), (0.6, 11.5)],
             [(43.5, 9.5), (38.5, 11.4), (40.5, 16.6), (44.8, 15.4), (45.4, 11.5)],
             [(17.5, 15.4), (28.5, 15.4), (27, 22.6), (23, 24.4), (19, 22.6)]]
    def fn(X, Y):
        top = poly_mask(X, Y, top_pts)
        flap = np.zeros(X.shape, bool)
        for f in flaps: flap |= poly_mask(X, Y, f)
        flap &= ~top
        g = 0.02 * grain(X, Y, 51) + 0.03 * Noise(51, 0.5)(X, Y)
        col = ramp('cheese', 0.84 + g - 0.16 * ((X - 23) / 22 + (Y - 9.5) / 8) * 0.5)
        col[flap] = ramp('cheese', 0.5 + g - 0.04 * (Y - 14))[flap]
        fold = top & ~poly_mask(X, Y, [(23, 2.6), (41.8, 9.5), (23, 16.4), (4.2, 9.5)])
        col[fold & (Y > 9.5)] = ramp('cheese', 0.98)[fold & (Y > 9.5)]
        hm, lm = holes(X, Y, [(15, 8.5, 1.7, 0.9), (30, 10.5, 1.5, 0.8), (22, 5.5, 1.1, 0.6), (24, 13, 1.0, 0.6)])
        col[hm & top] = ramp('cheese', 0.45)[hm & top]; col[lm & top] = ramp('cheese', 0.7)[lm & top]
        return col, top | flap
    return [Piece(fn)]


# ---------------------------------------------------------------- chicken

def chicken_raw():
    ns = Noise(41, 0.5)
    def fillet(X, Y):
        u, v = local(X, Y, 31, 33, 22, 13.2, -16)
        vv = v / (1 - 0.32 * np.clip(u, -1, 1)) - 0.12 * u * u
        m = (u * u + vv * vv <= 1)
        lam = dome(u, vv, -16)
        col = tone('chick_raw', lam, X, Y, 42, 0.05, 0.025, 0.14, 0.88)
        fib = np.abs(np.sin(vv * 9 + u * 2.2 + ns(X, Y) * 0.8)) > 0.93
        col[fib] = mix(col, ramp('chick_raw', 0.95), 0.4)[fib]
        fat = (np.abs(vv - 0.62) < 0.1) & (u > -0.7) & (u < 0.6)
        col[fat] = mix(col, np.array([1, 0.95, 0.88]), 0.45)[fat]
        col = col + 0.22 * spec(u, vv, (-0.35, -0.42), 0.04)[..., None]
        return np.clip(col, 0, 1), m
    return [Piece(fillet)]


def meat_cube(cx, cy, s, state, rot=0.0, seed=0, kind='chicken'):
    """A chopped chunk at a heat state (raw, cooking, ready, burnt): chicken is a cube, fish a flaky slab with skin."""
    fish = kind == 'fish'
    def faces(name, u, v, X, Y, lit):
        g = 0.03 * grain(X, Y, seed) + 0.04 * Noise(seed, 0.6)(X, Y)
        lvl = 0.8 - 0.12 * (u + v) if name == 'top' else 0.3 + 0.28 * lit - 0.12 * np.clip((Y - cy) / s, 0, 1)
        if fish:
            flesh = 'fish_flesh' if state in ('raw',) else 'fish_belly'
            if state == 'burnt':
                return ramp('burnt', lvl * 0.85 + g)
            if name == 'side':
                if state == 'raw':
                    col = ramp('fish_flesh', lvl * 0.9 + g)
                    skin = Y > cy + s * 0.18
                    col[skin] = ramp('fish_skin', 0.45 + g)[skin]
                    return col
                return ramp('golden', lvl * 0.9 + g + (0.08 if state == 'cooking' else 0))
            if state == 'raw': col = ramp('fish_flesh', lvl + 0.06 + g); fl = ramp('fish_flesh', 0.3)
            elif state == 'cooking': col = ramp('fish_belly', lvl + g); fl = ramp('golden', 0.7)
            else: col = ramp('golden', lvl + 0.1 + g); fl = ramp('golden', 0.42)
            flake = np.abs(np.sin((X - cx) * 1.1 - np.abs(Y - cy) * 2.0 + seed)) > 0.84
            col[flake] = mix(col, fl, 0.55)[flake]
            return col
        if state == 'raw':
            col = ramp('chick_raw', lvl + g)
            if name == 'top':
                fib = np.abs(np.sin((X - cx) * 1.1 + (Y - cy) * 2.0 + seed)) > 0.9
                col[fib] = mix(col, ramp('chick_raw', 1.0), 0.45)[fib]
            return col
        if state == 'cooking':
            if name == 'side': return ramp('golden', lvl * 0.95 + 0.1 + g)
            col = ramp('chick_raw', lvl + g)
            seared = (np.abs(u) > 0.3) | (np.abs(v) > 0.3)
            col[seared] = ramp('golden', 0.72 + g)[seared]
            return col
        if state == 'ready':
            col = ramp('golden', lvl + 0.02 + g)
            if name == 'top':
                sear = np.abs(np.sin((X - cx - (Y - cy) * 0.6) * 0.9 + seed)) > 0.95
                col[sear] = ramp('golden', 0.22)[sear]
            return col
        col = ramp('burnt', lvl * 0.85 + g)
        if name == 'top':
            ember = np.sin((X * 3.1 + Y * 2.3) + seed) > 0.97
            col[ember] = np.array([0.42, 0.16, 0.08])
        return col
    if fish: return block_piece(cx, cy, s * 1.25, s * 1.05, s * 0.32, faces, rot, squash=0.68)
    return block_piece(cx, cy, s, s, s * 0.62, faces, rot)


CUBES64 = [(22, 27, 11, 20), (39, 25, 10.5, -15), (46, 37, 10, 30), (29, 37, 11.5, 8), (16, 42, 10, -25), (37, 47, 11, 15), (22, 51, 9.5, 40)]
CUBES32 = [(11, 12, 9.5, 20), (22, 11, 9, -15), (14, 20, 10, -8), (24, 21, 9.5, 30)]
SLABS64 = [(23, 27, 12, 15), (41, 27, 11.5, -20), (31, 38, 12.5, 5), (17, 44, 11, -30), (44, 43, 11, 25), (30, 51, 11.5, -5)]
SLABS32 = [(11, 12, 10, 15), (22, 12, 9.5, -20), (13, 21, 10, -8), (23, 22, 10, 25)]


def cubes(state, kind, layout, seed=0):
    return [meat_cube(x, y, s, state, r, seed + k, kind) for k, (x, y, s, r) in enumerate(sorted(layout, key=lambda c: c[1]))]


def fillet_layer(kind, state='ready'):
    """A cooked fillet lying flat in an assembled dish: chicken with grill marks, fish with white flakes."""
    ns = Noise(61 if kind == 'chicken' else 71, 0.5)
    def top(u, v, X, Y):
        lam = dome(u, v * 0.7)
        g = 0.05 * ns(X, Y) + 0.02 * grain(X, Y, 3)
        if kind == 'fish':
            rr = np.sqrt(u * u + v * v)
            col = ramp('fish_belly', 0.45 + 0.5 * lam + g)
            flake = np.abs(np.sin(u * 8 - np.abs(v) * 3.2 + ns(X, Y) * 0.4)) > 0.82
            col[flake] = mix(col, ramp('fish_belly', 0.15), 0.6)[flake]
            crust = rr > 0.74
            col[crust] = ramp('golden', 0.45 + 0.4 * lam + g)[crust]
            return col
        col = ramp('golden', 0.32 + 0.58 * lam + g)
        for off in (-0.45, 0.0, 0.45):
            line = np.abs((u - off) * 1.0 + v * 0.55) < 0.075
            col[line] = ramp('golden', 0.12 + g)[line]
        return col
    def side(dep, X, Y): return ramp('golden', 0.32 - 0.18 * dep)
    shape = (lambda u, v: u * u + (v / (1 - 0.28 * u)) ** 2 <= 1) if kind == 'fish' else None
    return [disc_piece(23, 12.5, 21.5, 9.5, 3.5, top, side, 0, shape=shape)]


# ---------------------------------------------------------------- fish

def fish_raw():
    ns = Noise(81, 0.6)
    rot = -8
    def body(X, Y):
        u, v = local(X, Y, 28, 33, 20.5, 11.5, rot)
        vv = v / (1 - 0.18 * u)
        m = (u * u + vv * vv <= 1) & (u > -1.05)
        lam = dome(u, vv, rot)
        back = tone('fish_back', lam, X, Y, 82, 0.04, 0.03, 0.1, 0.95)
        belly = tone('fish_belly', lam, X, Y, 83, 0.03, 0.02, 0.2, 1.0)
        col = mix(back, belly, np.clip((vv + 0.05) * 2.4, 0, 1))
        # lateral line and scale arcs
        line = np.abs(vv + 0.02 - 0.08 * np.sin(u * 3)) < 0.05
        col[line] = mix(col, ramp('fish_back', 0.25), 0.5)[line]
        sc = (np.abs(np.sin(u * 14 + np.abs(vv) * 6)) > 0.93) & (vv < 0.35) & (u > -0.45)
        col[sc] = mix(col, ramp('fish_back', 0.95), 0.35)[sc]
        # gill arc and eye
        gu, gv = u + 0.5, vv
        gill = (np.abs(np.sqrt(gu * gu * 4 + gv * gv) - 0.62) < 0.06) & (gu > -0.1)
        col[gill] = ramp('fish_back', 0.15)[gill]
        eu, ev = local(X, Y, 14.4, 31.2, 2.4, 2.4)
        e = eu * eu + ev * ev
        col[e <= 1] = np.array([0.96, 0.95, 0.88])
        col[e <= 0.36] = np.array([0.06, 0.05, 0.06])
        pu, pv = eu + 0.25, ev + 0.3
        col[(pu * pu + pv * pv) < 0.05] = 1
        col = col + 0.25 * spec(u, vv, (-0.25, -0.5), 0.05)[..., None]
        mouth = (np.abs(vv - 0.18) < 0.05) & (u < -0.88)
        col[mouth] = ramp('fish_back', 0.1)[mouth]
        return np.clip(col, 0, 1), m
    def tail(X, Y):
        m = poly_mask(X, Y, [(45, 30.0), (57.5, 20.5), (54.5, 29.5), (57.8, 38.5), (45.5, 34.5)])
        col = tone('fish_back', 0.45 + 0.4 * (57 - X) / 13, X, Y, 84, 0.05, 0.03)
        rays = np.abs(np.sin(np.arctan2(Y - 32, X - 45) * 14)) > 0.85
        col[rays] = mix(col, ramp('fish_back', 0.2), 0.4)[rays]
        return col, m
    def dorsal(X, Y):
        m = poly_mask(X, Y, [(22, 23.5), (27, 16.5), (37, 18.5), (40, 24.5)])
        col = tone('fish_back', 0.42 + 0.35 * (Y - 16) / 9, X, Y, 85, 0.04, 0.03)
        rays = np.abs(np.sin(X * 1.4)) > 0.85
        col[rays] = mix(col, ramp('fish_back', 0.15), 0.45)[rays]
        return col, m
    def fin(X, Y):
        m = poly_mask(X, Y, [(22.5, 35.5), (29.5, 36.5), (24.5, 40.5)])
        return tone('fish_back', 0.62 + 0.25 * (30 - X) / 8, X, Y, 86, 0.04, 0.03), m
    def belly_fin(X, Y):
        m = poly_mask(X, Y, [(33, 41.0), (40, 39.0), (37, 45.5)])
        return tone('fish_belly', 0.35, X, Y, 87, 0.04, 0.03), m
    return [Piece(dorsal), Piece(tail), Piece(belly_fin), Piece(body), Piece(fin)]


# ---------------------------------------------------------------- flatbread

def flatbread(cx=32, cy=33, rx=24, ry=13.5, thick=3.0, seed=91):
    ns = Noise(seed, 0.35); rng = np.random.default_rng(seed)
    spots = []
    while len(spots) < 16:
        u, v = rng.uniform(-0.85, 0.85, 2)
        if u * u + v * v < 0.72: spots.append((u, v, rng.uniform(0.07, 0.13)))
    def top(u, v, X, Y):
        rr = np.sqrt(u * u + v * v)
        lam = dome(u * 0.5, v * 0.5)
        col = ramp('bread', 0.62 + 0.3 * lam + 0.045 * ns(X, Y) + 0.02 * grain(X, Y, seed))
        rim = rr > 0.8
        col[rim] = ramp('bread', 0.5 + 0.4 * (-v[rim]) + 0.1)        # puffed rim: lit at the back, shaded at the front
        for su, sv, sr in spots:
            d = np.sqrt(((u - su) / sr) ** 2 + ((v - sv) / (sr * 1.3)) ** 2)
            col[d < 1] = ramp('toast', 0.75)[d < 1]
            col[d < 0.55] = ramp('toast', 0.25)[d < 0.55]
            hl = (d < 1) & (d > 0.6) & (v - sv < -0.03)
            col[hl] = ramp('bread', 0.95)[hl]
        return col
    def side(dep, X, Y): return ramp('bread', 0.36 - 0.22 * dep + 0.02 * grain(X, Y, seed))
    wob = Noise(seed + 3, 0.9)
    shape = lambda u, v: (u * u + v * v) <= 1 + 0.025 * wob(u * 20, v * 20)
    return [disc_piece(cx, cy - thick / 2, rx, ry, thick, top, side, 0, shape=shape)]


# ---------------------------------------------------------------- scallion

def scallion_raw():
    stalks = [((13, 51), (49, 13), 0), ((15, 53), (54, 22), 1), ((11, 47), (42, 10.5), 2)]
    pieces = []
    def stalk_fn(a, b, k):
        def fn(X, Y):
            m, t, side, lam = capsule(X, Y, a, b, 3.1, 2.2)
            bulb, *_ = capsule(X, Y, a, (a[0] + (b[0] - a[0]) * 0.12, a[1] + (b[1] - a[1]) * 0.12), 3.7, 3.0)
            m = m | bulb
            # split the leaf near the tip into two blades
            split = (t > 0.72) & (np.abs(side) < 0.22)
            m &= ~split
            white = tone('scal_white', lam, X, Y, 100 + k, 0.03, 0.03, 0.2, 1.0)
            green = tone('scal_dark', lam, X, Y, 110 + k, 0.04, 0.03, 0.12, 0.92)
            light = ramp('scal_dark', 0.55 + 0.4 * lam)
            f1 = np.clip((t - 0.26) / 0.1, 0, 1); f2 = np.clip((t - 0.38) / 0.12, 0, 1)
            col = mix(mix(white, light, f1), green, f2)
            vein = (np.abs(side - 0.15) < 0.12) & (t > 0.4)
            col[vein] = mix(col, ramp('scal_dark', 0.85), 0.35)[vein]
            return np.clip(col, 0, 1), m
        return fn
    def roots(X, Y):
        m = np.zeros(X.shape, bool)
        for k, (dx, dy) in enumerate(((-4.5, 1.5), (-3.5, 4), (-1.5, 5), (-5, -1), (0.5, 5.2))):
            mk, *_ = capsule(X, Y, (12.6, 51.2), (12.6 + dx, 51.2 + dy), 0.7); m |= mk
        return tone('root', 0.65, X, Y, 120, 0.05, 0.05), m
    pieces.append(Piece(roots))
    for a, b, k in stalks: pieces.append(Piece(stalk_fn(a, b, k)))
    def band(X, Y):
        m, t, side, lam = capsule(X, Y, (19.5, 37.5), (23.8, 45.4), 1.5)
        return tone('band', lam, X, Y, 121, 0.03, 0.02, 0.2, 0.95), m
    pieces.append(Piece(band))
    return pieces


def scallion_ring(cx, cy, r=3.3, seed=0, white=False):
    def top(u, v, X, Y):
        rr = np.sqrt(u * u + v * v)
        col = ramp('scal_white' if white else 'scal_dark', 0.62 + 0.2 * (-v) + 0.25 * (rr > 0.78) * (v < 0) + 0.03 * grain(X, Y, seed))
        return col
    def side(dep, X, Y): return ramp('scal_dark', 0.35 - 0.2 * dep)
    return disc_piece(cx, cy, r, r * 0.72, 1.1, top, side, 0, hole=(0.45, 0.45), ink=(14, 50, 16) if not white else (60, 76, 44))


def scallion_rings(area, n, seed, r=3.3):
    rng = np.random.default_rng(seed)
    (x0, y0, x1, y1) = area; pts = []
    while len(pts) < n:
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        u, v = (x - (x0 + x1) / 2) / ((x1 - x0) / 2), (y - (y0 + y1) / 2) / ((y1 - y0) / 2)
        if u * u + v * v <= 1 and all((x - a) ** 2 + ((y - b) * 1.3) ** 2 > (r * 1.25) ** 2 for a, b in pts): pts.append((x, y))
    pts.sort(key=lambda p: p[1])
    return [scallion_ring(x, y, r * rng.uniform(0.9, 1.1), seed + k, white=(k % 5 == 2)) for k, (x, y) in enumerate(pts)]


def scallion_chopped():
    """A mound of rings: dense in the middle, back rings drawn first."""
    rng = np.random.default_rng(130); pts = []
    while len(pts) < 27:
        u, v = rng.uniform(-1, 1, 2)
        if u * u + v * v > 1: continue
        x, y = 32 + u * 20, 38 + v * 12
        y -= 6 * (1 - u * u - v * v)                    # mound: middle rings sit higher
        if all((x - a_) ** 2 + ((y - b_) * 1.35) ** 2 > 3.9 ** 2 for a_, b_ in pts): pts.append((x, y))
    pts.sort(key=lambda p: p[1])
    return [scallion_ring(x, y, 3.7 * rng.uniform(0.9, 1.1), 130 + k, white=(k % 4 == 1)) for k, (x, y) in enumerate(pts)]


def scallion_layer():
    return scallion_rings((3, 4, 43, 26), 13, 140, 3.0)


# ---------------------------------------------------------------- plates

def plate(cx=16, cy=17.5, rx=14.8, ry=9.4):
    def top(u, v, X, Y):
        rr = np.sqrt(u * u + v * v)
        col = ramp('plate', 0.8 - 0.25 * v * (rr > 0.72) + 0.02 * grain(X, Y, 5))
        well = rr < 0.68
        col[well] = ramp('plate', 0.62 + 0.2 * v[well])
        rim = (rr > 0.86)
        col[rim] = ramp('plate', 0.92)[rim]
        return col
    def side(dep, X, Y): return ramp('plate', 0.25)
    return disc_piece(cx, cy, rx, ry, 1.2, top, side, 0, ink=PLATE_INK)


# ---------------------------------------------------------------- atlas

def bbox(a):
    ys, xs = np.nonzero(a[..., 3])
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def crop_to_content(a, pad=0):
    x0, y0, x1, y1 = bbox(a)
    return a[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]


def frames():
    """Every frame of the pack: key -> (RGBA array, anchor)."""
    F = {}
    raw = {'cucumber': cucumber_raw, 'onion': onion_raw, 'cheese': cheese_raw, 'chicken': chicken_raw,
           'fish': fish_raw, 'flatbread': flatbread, 'scallion': scallion_raw}
    chopped = {'cucumber': cucumber_chopped, 'onion': onion_chopped, 'cheese': cheese_chopped,
               'chicken': lambda: cubes('raw', 'chicken', CUBES64, 200), 'fish': lambda: cubes('raw', 'fish', SLABS64, 300),
               'scallion': scallion_chopped}
    layer = {'cucumber': cucumber_layer, 'onion': onion_layer, 'cheese': cheese_layer,
             'chicken': lambda: fillet_layer('chicken'), 'fish': lambda: fillet_layer('fish'),
             'flatbread': lambda: flatbread(23, 15, 22.5, 11.0, 3.5, 95), 'scallion': scallion_layer}
    for item in ITEMS:
        a = render(raw[item](), (64, 64))
        F[f'food/{item}_raw'] = (a, [0.5, 0.5])
        # source icon: the raw art redrawn (not resampled) inside the source boxes' 40 px icon area
        x0, y0, x1, y1 = bbox(a); s = min(40 / (x1 - x0), 37 / (y1 - y0))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        F[f'modular/source_{item}'] = (render(raw[item](), (64, 96), s, (32, 41.5), (cx, cy)), [0.5, 1 / 3])
        if item in chopped:
            F[f'food/{item}_chopped'] = (render(chopped[item](), (64, 64)), [0.5, 0.5])
        L = render(layer[item](), (48, 32), 1.0, (24, 16), (23, 15))
        F[f'feedback/{item}'] = (crop_to_content(L), [0.5, 0.5])
    for item in HEATED:
        lay = CUBES64 if item == 'chicken' else SLABS64; small = CUBES32 if item == 'chicken' else SLABS32
        k = 200 if item == 'chicken' else 300
        F[f'food/{item}_ready'] = (render(cubes('ready', item, lay, k), (64, 64)), [0.5, 0.5])
        F[f'food/{item}_burnt'] = (render(cubes('burnt', item, lay, k), (64, 64)), [0.5, 0.5])
        # 32 px stages, the beef pipeline's ingredients/<item>/<stage>; cooking frames also fill the pot at 20x20
        a = render(raw[item](), (32, 32), 0.56, (16, 16.5), (32, 32))
        F[f'ingredients/{item}/raw'] = (a, [0.5, 0.5])
        F[f'ingredients/{item}/processing'] = (add_cuts(a), [0.5, 0.5])
        for st in ('raw', 'cooking', 'ready', 'burnt'):
            key = 'prepared' if st == 'raw' else st
            F[f'ingredients/{item}/{key}'] = (render(cubes(st, item, small, k + 50), (32, 32), design_centre=(16, 16)), [0.5, 0.5])
        for st in ('ready', 'burnt'):
            dish = [plate()] + cubes(st, item, [(12, 15, 8, 20), (20.5, 14.5, 7.5, -15), (16, 19.5, 8, 5)], k + 70)
            F[f'dishes/{item}/{st}'] = (render(dish, (32, 32), design_centre=(16, 16)), [0.5, 0.5])
    F = {k: (a, anchor, {}) for k, (a, anchor) in F.items()}
    import pan_noodles                                     # noodles, the frying pan, vessels with contents
    F.update(pan_noodles.frames(F))
    return F


def add_cuts(a):
    """Processing stage: two knife cuts across the raw piece, like ingredients/beef/processing."""
    b = a.copy(); x0, y0, x1, y1 = bbox(a)
    for fx in (0.38, 0.62):
        x = int(x0 + (x1 - x0) * fx)
        for y in range(y0 + 2, y1 - 2):
            if b[y, x, 3] and b[y, x, :3].sum() > 120: b[y, x, :3] = (b[y, x, :3] * 0.55).astype(np.uint8)
            if b[y, x + 1, 3] and b[y, x + 1, :3].sum() > 120: b[y, x + 1, :3] = np.minimum(255, b[y, x + 1, :3].astype(int) + 30)
    return b


def pack(F):
    """Shelf packing with 2 px gutters; identical images (aliases) share one rect."""
    cell = 2; x = y = cell; row = 0; W = 512; placed = {}; seen = {}
    for k, (a, *_) in F.items():
        digest = a.tobytes() + bytes(str(a.shape), 'ascii')
        if digest in seen: placed[k] = seen[digest]; continue
        h, w = a.shape[:2]
        if x + w + cell > W: x = cell; y += row + cell * 2; row = 0
        placed[k] = seen[digest] = (x, y); x += w + cell * 2; row = max(row, h)
    H = y + row + cell; H = int(2 ** math.ceil(math.log2(H)))
    atlas = np.zeros((H, W, 4), np.uint8); man = {}
    for k, (a, anchor, extra) in F.items():
        (x, y) = placed[k]; h, w = a.shape[:2]
        atlas[y:y + h, x:x + w] = a
        man[k] = {'rect': [x, y, w, h], 'canvasSize': [w, h], 'anchor': anchor, 'alpha_bbox': bbox(a), **extra}
    return atlas, man


def write_meta(path, kind):
    if path.exists(): return                      # keep uuids stable across regenerations
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


def main():
    import pan_noodles
    F = frames(); atlas, man = pack(F)
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(atlas, 'RGBA').save(OUT / 'atlas.png', optimize=True)
    manifest = {'version': 'ingredient-pack-v1', 'items': ITEMS + ['noodles'], 'heated': HEATED, 'boiled': ['noodles'],
                'vessels': {'pan': {'items': list(pan_noodles.PAN_ITEMS), 'stages': list(pan_noodles.PAN_STAGES)},
                            'pot': {'items': ['noodles'], 'stages': list(pan_noodles.NOODLE_STAGES)}},
                'notes': 'Current food style. Load without a prefix after burger-food and grid-foundation-v1; keys follow '
                         'food/<item>_<state>, modular/source_<item>, feedback/<item>, ingredients/<item>/<stage>, dishes/<dish>/<state>; '
                         'vessels: objects/pan, modular/pan_<axis>, and <vessel frame>/<item>/<stage> with the food cooking inside '
                         '(contentAnchor = centre of the inside, canvas px).',
                'frames': man}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    write_meta(OUT / 'atlas.png.meta', 'image'); write_meta(OUT / 'manifest.json.meta', 'json')
    print(f'{len(man)} frames, atlas {atlas.shape[1]}x{atlas.shape[0]}')
    return F


if __name__ == '__main__':
    main()
