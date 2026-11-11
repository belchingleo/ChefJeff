"""Sink with its drying rack as one two-cell steel unit (Overcooked 2's washing station), in the grid-foundation-v1 style.

One continuous slab across two cells: a basin with its tap and drain in the sink's cell, and in the rack's cell a
ridged drainboard with a wire dish rack. Drawn in the style of modular/device_sink_* (navy-black outline, brushed
steel lit from the top left, dark recessed basin, chrome tap), at 4x supersampling with the ingredient pack's tools.

Frames, added to cocos-kitchen/assets/resources/art/grid-foundation-v1 (existing frames keep their rects):

  modular/sink_unit_<side>          side = where the rack lies from the basin: east, west (118x45), south, north (45x118).
                                    The outer frame matches the single-cell sink's margins; the anchor is the middle of
                                    the unit, on the edge between its two cells. The tap is device_sink_*'s own tap,
                                    cut out pixel for pixel, on the wall side: the top of a horizontal unit, the right
                                    of a vertical one.
  modular/sink_unit_horizontal      = sink_unit_east     (the two names the art request asked for)
  modular/sink_unit_vertical        = sink_unit_south
  modular/sink_unit_rack_front_<side>
                                    the rack's front wires, same canvas as the unit, drawn over the plates
  modular/rack_plate_horizontal     a clean plate standing in the rack, seen edge-on (east/west racks)
  modular/rack_plate_vertical       a clean plate standing in the rack, face toward the viewer (north/south racks)

Each unit frame carries, in canvas pixels: basinCell and rackCell (cell centres), basin (where the dirty plate
sits, clear of the tap), tap (the spout's mouth), rack = {axis, start, end, slots}: the line the plates stand on,
first plate centre to last, along x (east/west) or y (north/south, back to front); the code spaces n plates evenly
from start to end and closes them up past `slots` (4: a level has at most 3 plates). rackSlots lists the 4 drawn
slot centres; rackPlate and rackFront are the keys above.

Run: python3 scripts/art/sink_unit.py  (needs Pillow and numpy; scripts/art/ingredient_pack.py supplies the tools)
"""
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import ingredient_pack as ip
from ingredient_pack import Piece, render, ramp, mix, grain, Noise, local, capsule, dilate

ROOT = Path(__file__).resolve().parents[2]
GRID = ROOT / 'cocos-kitchen/assets/resources/art/grid-foundation-v1'
INK = (10, 16, 23)                    # outline of device_sink_*
PLATE_INK = (0, 8, 32)                # outline of objects/clean_plate
PREFIXES = ('modular/sink_unit_', 'modular/rack_plate_')
TAP_BODY_MID = 6.0                    # the vertical tap cut-out's body spans its rows 2-9
SLOTS = 4                             # at most 3 plates per level (rules.py plate_count 1-3); one spare

ip.RAMPS.update({
    'slab': [(70, 76, 86), (112, 118, 126), (150, 153, 157), (184, 185, 186), (226, 227, 224)],
    'rim': [(96, 102, 112), (150, 152, 156), (196, 196, 194), (232, 232, 228), (250, 250, 246)],
    'basin': [(24, 30, 38), (52, 58, 68), (84, 90, 99), (118, 123, 130), (152, 155, 160)],
    'chrome': [(54, 60, 70), (110, 116, 126), (170, 174, 180), (220, 222, 224), (252, 252, 250)],
    'wire': [(28, 32, 40), (58, 64, 74), (104, 110, 120), (160, 164, 170)],
    'plate': [(176, 160, 150), (214, 196, 180), (240, 220, 198), (248, 230, 208), (255, 244, 230)],
    'plate_rim': [(110, 118, 136), (144, 152, 168), (176, 182, 196), (214, 218, 228)],
})


# ---------------------------------------------------------------- shapes

def rbox(X, Y, x0, y0, x1, y1, r):
    """Rounded rectangle mask, plus the distance inside its edge (0 at the edge)."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2; hx, hy = (x1 - x0) / 2 - r, (y1 - y0) / 2 - r
    qx, qy = np.abs(X - cx) - hx, np.abs(Y - cy) - hy
    out = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    return out <= 0, -out


def lerp(a, b, t): return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


class Geo:
    """Where everything is in one unit frame. Horizontal units are 118x45, vertical ones 45x118: the outer frame of
    device_sink_* (54x45 / 45x54) stretched across two 64 px cells with the same 5 px margins."""
    def __init__(self, side):
        self.side = side; self.vertical = side in ('north', 'south')
        if self.vertical:
            self.size = (45, 118); self.slab = (1.5, 1.5, 36.5, 116.0); self.lip = 3.0
            top, bottom = (1.5, 59.0), (59.0, 116.0)
            basin_rows, rack_rows = (top, bottom) if side == 'south' else (bottom, top)
            self.basin_cell = (19.0, (basin_rows[0] + basin_rows[1]) / 2); self.rack_cell = (19.0, (rack_rows[0] + rack_rows[1]) / 2)
            by0 = basin_rows[0] + (3.0 if side == 'south' else 2.0); by1 = basin_rows[1] - (2.0 if side == 'south' else 6.0)
            self.basin = (4.5, by0, 31.5, by1)
            ry0 = rack_rows[0] + (2.0 if side == 'south' else 3.0); ry1 = rack_rows[1] - (6.0 if side == 'south' else 2.0)
            self.board = (4.5, ry0, 33.5, ry1)
            # The horizontal layout turned 90 degrees: the tap comes from the wall on the right at the middle of the
            # basin's long side; the drain is in the middle of the basin; the plate sits on the drain, level with the tap,
            # between the basin's left rim and the tap's mouth.
            mid = (self.basin[1] + self.basin[3]) / 2
            self.tap_at = (28, math.floor(mid - TAP_BODY_MID + 0.5))  # device_sink_vertical's tap: cols 28-44
            ty = self.tap_at[1] + TAP_BODY_MID
            self.tap = ((44.0, ty), (29.0, ty)); self.mouth = (29.0, ty)
            self.drain = ((self.basin[0] + self.basin[2]) / 2, mid)
            self.plate_at = (self.tap_at[0] - 11.5, ty)               # a 22 px plate ends half a pixel short of the mouth
            self.rack_line = ((18.5, self.board[1] + 8.0), (18.5, self.board[3] - 12.0))
            self.slots = [lerp(*self.rack_line, k / (SLOTS - 1)) for k in range(SLOTS)]
        else:
            self.size = (118, 45); self.slab = (1.5, 7.5, 116.5, 40.0); self.lip = 2.8
            left, right = (1.5, 59.0), (59.0, 116.5)
            basin_cols, rack_cols = (left, right) if side == 'east' else (right, left)
            self.basin_cell = ((basin_cols[0] + basin_cols[1]) / 2, 24.0); self.rack_cell = ((rack_cols[0] + rack_cols[1]) / 2, 24.0)
            bx0 = basin_cols[0] + (3.0 if side == 'east' else 2.0); bx1 = basin_cols[1] - (2.0 if side == 'east' else 3.0)
            self.basin = (bx0, 10.5, bx1, 38.5)
            rx0 = rack_cols[0] + (2.0 if side == 'east' else 3.0); rx1 = rack_cols[1] - (3.0 if side == 'east' else 2.0)
            self.board = (rx0, 10.5, rx1, 38.5)
            cx = (self.basin[0] + self.basin[2]) / 2
            self.tap_at = (round(cx - 4.5), 0)                       # device_sink_horizontal's tap: cols 22-31, rows 0-16
            self.tap = ((cx, 1.5), (cx, 13.0)); self.mouth = (cx, 15.0)
            self.plate_at = (cx, 29.5)
            self.drain = None                                          # where basin_piece has always put it
            self.rack_line = ((self.board[0] + 12.0, 22.0), (self.board[2] - 12.0, 22.0))
            self.slots = [lerp(*self.rack_line, k / (SLOTS - 1)) for k in range(SLOTS)]
        self.ridges_along_x = not self.vertical       # drainboard grooves run toward the basin


# ---------------------------------------------------------------- pieces

def slab_piece(g):
    x0, y0, x1, y1 = g.slab; lip = g.lip; streak = Noise(301, 0.9)
    def fn(X, Y):
        top, inside = rbox(X, Y, x0, y0, x1, y1, 3.2)
        front, _ = rbox(X, Y, x0, y0 + lip, x1, y1 + lip, 3.2)
        front &= ~top
        rgb = np.zeros(X.shape + (3,))
        # brushed steel: soft light from the top left, fine streaks along the long side
        u = (X - x0) / (x1 - x0); v = (Y - y0) / (y1 - y0)
        s = streak(X * (0.15 if not g.vertical else 1.0), Y * (1.0 if not g.vertical else 0.15))
        t = 0.62 - 0.18 * u - 0.14 * v + 0.05 * s + 0.02 * grain(X, Y, 3)
        rgb[top] = ramp('slab', t)[top]
        # bevelled rim round the outside only (no seam between the cells)
        rim = top & (inside < 2.6)
        lit = (X - x0 < 2.6) | (Y - y0 < 2.6)
        rgb[rim & lit] = ramp('rim', 0.86 + 0.06 * s)[rim & lit]
        rgb[rim & ~lit] = ramp('rim', 0.5 + 0.05 * s)[rim & ~lit]
        edge = top & (inside >= 2.6) & (inside < 3.6)
        rgb[edge] = ramp('slab', 0.34 + 0.03 * s)[edge]
        rgb[front] = ramp('slab', 0.24 - 0.12 * u + 0.03 * s)[front]
        hl = front & (Y < y1 + 0.9)
        rgb[hl] = ramp('slab', 0.5)[hl]
        return rgb, top | front
    return Piece(fn, INK)


def basin_piece(g):
    """A recessed basin as on device_sink_*: dark far wall, sloping side walls, a lighter inset floor with a soft
    light round the drain, and a bright bevel along the opening's far and right edges."""
    x0, y0, x1, y1 = g.basin
    def fn(X, Y):
        m, inside = rbox(X, Y, x0, y0, x1, y1, 3.0)
        rgb = np.zeros(X.shape + (3,))
        depth = (y1 - y0) * 0.34
        u = (X - x0) / (x1 - x0)
        rgb[:] = ramp('basin', 0.3 + 0.12 * (1 - u) + 0.02 * grain(X, Y, 5))          # side walls
        wall = Y < y0 + depth
        rgb[wall] = ramp('basin', 0.12 + 0.22 * (Y[wall] - y0) / depth + 0.08 * (1 - u[wall]))
        fx0, fy0, fx1, fy1 = x0 + 3.2, y0 + depth, x1 - 3.2, y1 - 2.2
        floor, finside = rbox(X, Y, fx0, fy0, fx1, fy1, 2.4)
        dx, dy = g.drain or ((x0 + x1) / 2 + 2.0, fy0 + (fy1 - fy0) * 0.62)
        glow = np.exp(-(((X - dx) / (fx1 - fx0) * 2.2) ** 2 + ((Y - dy) / (fy1 - fy0) * 2.0) ** 2))
        ft = 0.52 + 0.3 * glow + 0.08 * (1 - u) + 0.02 * grain(X, Y, 6)
        rgb[floor] = ramp('basin', ft)[floor]
        fedge = floor & (finside < 0.9)
        rgb[fedge] = ramp('basin', 0.34)[fedge]
        flit = floor & (finside < 0.9) & (Y > fy1 - 1.2)
        rgb[flit] = ramp('basin', 0.7)[flit]
        lip = inside < 1.0
        rgb[lip] = ramp('basin', 0.06)[lip]
        bevel = (inside >= 1.0) & (inside < 1.9) & ((Y - y0 < 2.4) | (x1 - X < 2.4))
        rgb[bevel] = ramp('rim', 0.9)[bevel]
        # drain: chrome ring, dark hole, a crossbar
        r = np.hypot(X - dx, (Y - dy) * 1.25)
        ring = r < 3.4
        rgb[ring] = ramp('chrome', 0.45 + 0.4 * np.clip(-(X - dx) - (Y - dy), -1, 1) / 2 + 0.2)[ring]
        hole = r < 2.3
        rgb[hole] = ramp('basin', 0.0)[hole]
        bar = hole & (np.abs(Y - dy) < 0.45)
        rgb[bar] = ramp('chrome', 0.5)[bar]
        return rgb, m
    return Piece(fn, None)


def board_piece(g):
    """The drainboard: a shallow ribbed tray whose grooves run toward the basin."""
    x0, y0, x1, y1 = g.board
    def fn(X, Y):
        m, inside = rbox(X, Y, x0, y0, x1, y1, 2.6)
        rgb = np.zeros(X.shape + (3,))
        u = (X - x0) / (x1 - x0); v = (Y - y0) / (y1 - y0)
        rgb[:] = ramp('slab', 0.46 - 0.12 * u - 0.1 * v + 0.02 * grain(X, Y, 7))
        across = (Y - y0) if g.ridges_along_x else (X - x0)
        span = (y1 - y0) if g.ridges_along_x else (x1 - x0)
        k = (across - 2.5) / 4.4
        ph = k - np.floor(k)
        inner = (inside > 1.6) & (across > 2.5) & (across < span - 2.5)
        groove = inner & (ph < 0.3)
        shine = inner & (ph >= 0.3) & (ph < 0.48)
        rgb[groove] = ramp('slab', 0.18 + 0.04 * u)[groove]
        rgb[shine] = ramp('rim', 0.82)[shine]
        lip = inside < 1.0
        rgb[lip] = ramp('slab', 0.22)[lip]
        top_lip = lip & ((Y - y0 < 1.2) | (X - x0 < 1.2))
        rgb[top_lip] = ramp('slab', 0.12)[top_lip]
        return rgb, m
    return Piece(fn, None)


def rack_base_piece(g):
    """The dish rack's back half on the drainboard: the far rail with a peg at every slot."""
    def fn(X, Y):
        m = np.zeros(X.shape, bool); t = np.zeros(X.shape)
        def add(a, b, r):
            nonlocal m, t
            mk, tt, side, lam = capsule(X, Y, a, b, r); new = mk & ~m; t[new] = lam[new]; m |= mk
        if g.vertical:
            ys = [s[1] for s in g.slots]
            for x in (6.5, 31.0): add((x, ys[0] - 7), (x, ys[-1] + 7), 0.75)
            for y in ys: add((6.5, y - 4.0), (31.0, y - 4.0), 0.5)
        else:
            xs = [s[0] for s in g.slots]
            add((xs[0] - 7, 17.0), (xs[-1] + 7, 17.0), 0.75)
            for x in xs:
                for dx in (-4.2, 4.2): add((x + dx, 17.0), (x + dx, 13.5), 0.55)
        return ramp('wire', 0.3 + 0.6 * t), m
    return Piece(fn, INK)


def rack_front_piece(g):
    """The rack's front wires, drawn over the plates."""
    def fn(X, Y):
        m = np.zeros(X.shape, bool); t = np.zeros(X.shape)
        if g.vertical:
            ys = [s[1] for s in g.slots]
            for x in (6.5, 31.0):
                for y in ys:
                    mk, tt, side, lam = capsule(X, Y, (x, y - 2.5), (x, y + 5.0), 0.8); m |= mk; t = np.where(mk, lam, t)
            mk, tt, side, lam = capsule(X, Y, (5.5, ys[-1] + 8.0), (32.0, ys[-1] + 8.0), 0.8); m |= mk; t = np.where(mk, lam, t)
        else:
            xs = [s[0] for s in g.slots]
            mk, tt, side, lam = capsule(X, Y, (xs[0] - 7.5, 33.5), (xs[-1] + 7.5, 33.5), 0.85); m |= mk; t = np.where(mk, lam, t)
            for x in xs:
                for dx in (-4.2, 4.2):
                    mk, tt, side, lam = capsule(X, Y, (x + dx, 33.5), (x + dx, 27.5), 0.6); m |= mk; t = np.where(mk & ~(t > 0), lam, t)
        return ramp('wire', 0.35 + 0.6 * t), m
    return Piece(fn, INK)


def knob_piece(g):
    """Hot and cold knobs either side of the tap."""
    a = g.tap[0]
    def knobs(X, Y):
        m = np.zeros(X.shape, bool); rgb = np.zeros(X.shape + (3,))
        pts = [(g.tap[0][0] - 8.5, 8.4), (g.tap[0][0] + 8.5, 8.4)] if not g.vertical else [(34.0, a[1] - 8.0), (34.0, a[1] + 8.0)]
        for k, (x, y) in enumerate(pts):
            u, v = local(X, Y, x, y, 2.3, 1.8)
            d = u * u + v * v <= 1; m |= d
            rgb[d] = ramp('chrome', 0.4 + 0.5 * np.clip(-u - v, 0, 1))[d]
            cap = d & (u * u + v * v < 0.3)
            rgb[cap] = np.array([0.80, 0.24, 0.20]) if k == 0 else np.array([0.24, 0.44, 0.80])
        return rgb, m
    return Piece(knobs, INK)


def original_tap(vertical):
    """device_sink_*'s tap, cut out along its own outline: rows (horizontal) or columns (vertical) from the first to
    the last outline pixel inside the tap's box. Returns the RGBA cut-out."""
    man = json.loads((GRID / 'manifest.json').read_text())['frames']
    atlas = np.array(Image.open(GRID / 'atlas.png').convert('RGBA'))
    key, box = ('modular/device_sink_vertical', (28, 19, 45, 31)) if vertical else ('modular/device_sink_horizontal', (21, 0, 33, 17))
    x, y, w, h = man[key]['rect']; frame = atlas[y:y + h, x:x + w]
    x0, y0, x1, y1 = box; cut = frame[y0:y1, x0:x1].copy()
    dark = (cut[..., :3].astype(int).sum(-1) < 120) & (cut[..., 3] > 0)
    keep = np.zeros(dark.shape, bool)
    if vertical:
        for c in range(cut.shape[1]):
            rows = np.nonzero(dark[:, c])[0]
            if len(rows): keep[rows.min():rows.max() + 1, c] = True
    else:
        for r in range(cut.shape[0]):
            cols = np.nonzero(dark[r])[0]
            if len(cols): keep[r, cols.min():cols.max() + 1] = True
    keep &= cut[..., 3] > 0
    cut[~keep] = 0
    return cut


def paste(base, sprite, at):
    x, y = at; h, w = sprite.shape[:2]
    region = base[y:y + h, x:x + w]; m = sprite[..., 3] > 0
    region[m] = sprite[m]
    return base


def unit_pieces(g):
    return [slab_piece(g), basin_piece(g), board_piece(g), rack_base_piece(g), knob_piece(g)]


# ---------------------------------------------------------------- plates in the rack

def rack_plate(vertical):
    """A clean plate standing in the rack: edge-on (narrow and tall) for east/west racks, face toward the viewer for
    north/south racks, in objects/clean_plate's colours."""
    if vertical:
        size, (cx, cy, rx, ry) = (28, 20), (14, 10, 12.6, 8.6)
    else:
        size, (cx, cy, rx, ry) = (12, 28), (6, 14, 4.2, 12.8)
    def fn(X, Y):
        u, v = local(X, Y, cx, cy, rx, ry)
        rr = u * u + v * v; m = rr <= 1
        rgb = ramp('plate', 0.62 + 0.25 * np.clip(-0.5 * u - 0.6 * v, -1, 1) + 0.02 * grain(X, Y, 13))
        rim = rr > (0.62 if vertical else 0.45)
        rgb[rim] = ramp('plate_rim', 0.55 + 0.35 * np.clip(-u - v, -1, 1))[rim]
        if vertical:
            well = (rr < 0.36) & (rr > 0.26)
            rgb[well] = ramp('plate', 0.4)[well]
            shine = (rr < 0.18) & (u < -0.1) & (v < -0.1)
            rgb[shine] = ramp('plate', 1.0)[shine]
        else:
            face = (u < 0.3) & (rr < 0.62)
            rgb[face] = ramp('plate', 0.78 - 0.2 * v[face])
            wu, wv = (u - 0.05) / 0.5, v / 0.62                      # the well's curve, seen at a slant
            well = (np.abs(wu * wu + wv * wv - 1) < 0.22) & (u > -0.2)
            rgb[well] = ramp('plate', 0.38)[well]
            shine = (u < -0.25) & (u > -0.6) & (v < -0.2) & (v > -0.7)
            rgb[shine] = ramp('plate', 1.0)[shine]
        return rgb, m
    return render([Piece(fn, PLATE_INK)], size, 1.0, (size[0] / 2, size[1] / 2), (size[0] / 2, size[1] / 2))


# ---------------------------------------------------------------- frames and atlas

def frames():
    F = {}
    plates = {'horizontal': rack_plate(False), 'vertical': rack_plate(True)}
    F['modular/rack_plate_horizontal'] = (plates['horizontal'], {'note': 'clean plate standing edge-on in an east/west rack'})
    F['modular/rack_plate_vertical'] = (plates['vertical'], {'note': 'clean plate standing face-on in a north/south rack'})
    for side in ('east', 'west', 'south', 'north'):
        g = Geo(side); W, H = g.size; c = (W / 2, H / 2)
        img = paste(render(unit_pieces(g), g.size, 1.0, c, c), original_tap(g.vertical), g.tap_at)
        front = render([rack_front_piece(g)], g.size, 1.0, c, c)
        r1 = lambda p: [round(p[0], 1), round(p[1], 1)]
        meta = {'side': side, 'cells': 2, 'basinCell': r1(g.basin_cell), 'rackCell': r1(g.rack_cell), 'basin': r1(g.plate_at),
                'tap': r1(g.mouth), 'rack': {'axis': 'y' if g.vertical else 'x', 'start': r1(g.rack_line[0]), 'end': r1(g.rack_line[1]),
                                             'slots': SLOTS},
                'rackSlots': [r1(s) for s in g.slots],
                'rackPlate': 'modular/rack_plate_' + ('vertical' if g.vertical else 'horizontal'),
                'rackFront': f'modular/sink_unit_rack_front_{side}'}
        F[f'modular/sink_unit_{side}'] = (img, meta)
        F[f'modular/sink_unit_rack_front_{side}'] = (front, {'side': side, 'over': f'modular/sink_unit_{side}'})
    F['modular/sink_unit_horizontal'] = (F['modular/sink_unit_east'][0], dict(F['modular/sink_unit_east'][1], alias='modular/sink_unit_east'))
    F['modular/sink_unit_vertical'] = (F['modular/sink_unit_south'][0], dict(F['modular/sink_unit_south'][1], alias='modular/sink_unit_south'))
    return F


def add_to_atlas(F):
    """Add the frames below the existing ones; existing rects stay put, earlier runs of this script are replaced."""
    man = json.loads((GRID / 'manifest.json').read_text())
    atlas = np.array(Image.open(GRID / 'atlas.png').convert('RGBA'))
    keep = {k: v for k, v in man['frames'].items() if not k.startswith(PREFIXES)}
    base = max(v['rect'][1] + v['rect'][3] for v in keep.values()) + 2
    W = atlas.shape[1]; x, y, row = 2, base + 2, 0; placed = {}; seen = {}
    for k, (img, _) in F.items():
        digest = img.tobytes() + bytes(str(img.shape), 'ascii')
        if digest in seen: placed[k] = seen[digest]; continue
        h, w = img.shape[:2]
        if x + w + 2 > W: x, y, row = 2, y + row + 4, 0
        placed[k] = seen[digest] = (x, y); x += w + 4; row = max(row, h)
    H = y + row + 2
    out = np.zeros((H, W, 4), np.uint8); out[:base] = atlas[:base]
    for k, (img, meta) in F.items():
        px, py = placed[k]; h, w = img.shape[:2]
        out[py:py + h, px:px + w] = img
        keep[k] = {'canvasSize': [w, h], 'anchor': [0.5, 0.5], 'alpha_bbox': [0, 0, w, h], 'sampling': 'nearest', 'fit': 'uniform',
                   'rect': [px, py, w, h], **meta}
    man['frames'] = keep
    Image.fromarray(out, 'RGBA').save(GRID / 'atlas.png', optimize=True)
    (GRID / 'manifest.json').write_text(json.dumps(man, indent=2) + '\n')
    update_meta(out)
    return out.shape


def update_meta(atlas):
    """Keep the atlas sprite-frame sub-meta's size, trim and vertices in step with the image."""
    path = GRID / 'atlas.png.meta'; meta = json.loads(path.read_text())
    sf = meta['subMetas'].get('f9941')
    if not sf: return
    H, W = atlas.shape[:2]; ys, xs = np.nonzero(atlas[..., 3])
    tx, ty, w, h = int(xs.min()), int(ys.min()), int(xs.max()) - int(xs.min()) + 1, int(ys.max()) - int(ys.min()) + 1
    u = sf['userData']
    u.update(rawWidth=W, rawHeight=H, trimX=tx, trimY=ty, width=w, height=h,
             offsetX=tx + w / 2 - W / 2, offsetY=H / 2 - (ty + h / 2))
    for k in ('offsetX', 'offsetY'):
        if float(u[k]).is_integer(): u[k] = int(u[k])
    hw, hh = w / 2, h / 2
    v = u['vertices']
    v['rawPosition'] = [-hw, -hh, 0, hw, -hh, 0, -hw, hh, 0, hw, hh, 0]
    v['rawPosition'] = [int(p) if float(p).is_integer() else p for p in v['rawPosition']]
    uv = [tx, H - ty, tx + w, H - ty, tx, H - ty - h, tx + w, H - ty - h]
    v['uv'] = uv; v['nuv'] = [p / W if i % 2 == 0 else (2 * H - 2 * ty - h - p) / H for i, p in enumerate(uv)]
    v['minPos'] = [v['rawPosition'][0], v['rawPosition'][1], 0]; v['maxPos'] = [v['rawPosition'][9], v['rawPosition'][10], 0]
    path.write_text(json.dumps(meta, indent=2) + '\n')


def main():
    F = frames(); shape = add_to_atlas(F)
    print(f'{len(F)} frames added, atlas {shape[1]}x{shape[0]}')


if __name__ == '__main__':
    main()
