#!/usr/bin/env python3
"""Static atlas composition check; NOT a Cocos screenshot or gameplay test."""
import json
import re
from pathlib import Path
import sys
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from map_definition import load_map


def read_grid_art():
    source = (ROOT / 'cocos-kitchen/assets/scripts/KitchenGeometry.ts').read_text()
    match = re.search(r'export\s+const\s+GRID_ART\s*=\s*\{([^}]+)\}', source)
    if not match:
        raise RuntimeError('Could not read GRID_ART from KitchenGeometry.ts')
    values = {key: int(value) for key, value in re.findall(r'(\w+)\s*:\s*(\d+)', match.group(1))}
    required = {'tile', 'originX', 'originY', 'unit', 'counterHeight', 'wallHeight', 'floorRepeat'}
    missing = required - values.keys()
    if missing:
        raise RuntimeError(f'GRID_ART is missing {sorted(missing)}')
    return values


GRID_ART = read_grid_art()
TILE = GRID_ART['tile']
MAPX = GRID_ART['originX']
MAPY = GRID_ART['originY']
UNIT = GRID_ART['unit']
SURFACE_OFFSET = GRID_ART['counterHeight'] * TILE / UNIT
WALL_OFFSET = GRID_ART['wallHeight'] * TILE / UNIT
FRONT_ROW_HEIGHT = GRID_ART['frontWallHeight'] * TILE / UNIT

frames = {}
ATLAS_ROOT = ROOT / 'cocos-kitchen/assets/resources/art'


def load_atlas(folder, prefix='', override=False):
    base = ATLAS_ROOT / folder
    if not (base / 'manifest.json').exists():
        return
    atlas = Image.open(base / 'atlas.png').convert('RGBA')
    manifest = json.loads((base / 'manifest.json').read_text())
    for name, metadata in manifest['frames'].items():
        x, y, width, height = metadata['rect']
        key = prefix + name
        if override or key not in frames:
            frames[key] = (atlas.crop((x, y, x + width, y + height)), metadata)


for folder, prefix in (
    ('level1', ''),
    ('level1-modular', 'modular/'),
    ('burger-food', 'food/'),
    ('kitchen-modules-v2', 'modular/'),
    ('serving-side-v1', 'modular/'),
):
    load_atlas(folder, prefix, override=True)
# The foundation atlas is authoritative for frames it defines, while preserving
# workstation and serving art supplied by the earlier atlases.
load_atlas('grid-foundation-v1', override=True)


def xy(cell):
    return MAPX + (cell[0] + .5) * TILE, MAPY + (cell[1] + .5) * TILE


def alpha_crop(source, metadata):
    bounds = metadata.get('alpha_bbox')
    if bounds and len(bounds) == 4:
        left, top, right, bottom = map(int, bounds)
        if right > left and bottom > top:
            return source.crop((left, top, right, bottom))
    bbox = source.getbbox()
    return source.crop(bbox) if bbox else source


def centered(target, key, cx, cy, max_width, max_height=None):
    frame = frames.get(key)
    if not frame:
        return
    source, metadata = frame
    source = alpha_crop(source, metadata)
    max_height = max_width if max_height is None else max_height
    scale = min(max_width / max(1, source.width), max_height / max(1, source.height))
    size = max(1, round(source.width * scale)), max(1, round(source.height * scale))
    source = source.resize(size, Image.Resampling.NEAREST)
    target.alpha_composite(source, (round(cx - source.width / 2), round(cy - source.height / 2)))


def anchored(target, key, x, y, surface=False, sprite_lift=0):
    frame = frames.get(key)
    if not frame:
        return
    source, metadata = frame
    scale = TILE / UNIT
    source = source.resize((max(1, round(source.width * scale)),
                            max(1, round(source.height * scale))), Image.Resampling.NEAREST)
    anchor = metadata.get('workSurfaceAnchor' if surface else 'groundAnchor')
    if not anchor:
        anchor = [frame[0].width / 2, frame[0].height / 2]
    # KitchenClient.cabinetArt lowers the sprite by cabinetSpriteLift in Cocos
    # coordinates (downward in this top-left-origin preview).
    y += sprite_lift * scale
    target.alpha_composite(source, (round(x - anchor[0] * scale), round(y - anchor[1] * scale)))


def work_surface_bounds(metadata, cell_center, tile=TILE, unit=UNIT, sprite_lift=0):
    """Return the cabinet worktop rectangle after Cocos ground-anchor placement."""
    left, top, width, height = metadata['surfaceRect']
    anchor_x, anchor_y = metadata['groundAnchor']
    scale = tile / unit
    cx, cy = cell_center
    lifted_y = cy + sprite_lift * scale
    return (round(cx + (left - anchor_x) * scale),
            round(lifted_y + (top - anchor_y) * scale),
            round(cx + (left + width - anchor_x) * scale),
            round(lifted_y + (top + height - anchor_y) * scale))


def station_view(document, station_id):
    authored = document.get('presentation', {}).get('station_views', {}).get(station_id)
    if authored:
        return authored
    equipment = document['equipment']
    station = next((entry for entry in equipment if entry['id'] == station_id), None)
    cell = station['cell'] if station else [0, 0]
    occupied = {tuple(part) for entry in equipment
                for part in entry.get('cells', [entry['cell']])}
    horizontal = int((cell[0] - 1, cell[1]) in occupied) + int((cell[0] + 1, cell[1]) in occupied)
    vertical = int((cell[0], cell[1] - 1) in occupied) + int((cell[0], cell[1] + 1) in occupied)
    axis = 'vertical' if vertical > horizontal else 'horizontal'
    return {'run_axis': axis, 'device_axis': axis}


def wall_layer(image, x, y, face_height=0, serving_slot=False, slot_center=None):
    floor_cx, floor_cy = xy((x, y))
    cell_left = round(MAPX + x * TILE)
    cell_top = round(floor_cy - TILE / 2)
    layer = Image.new('RGBA', (TILE, TILE), (0, 0, 0, 0))

    if face_height > 0:
        frame = frames.get('modular/wall_face')
        if frame:
            source, metadata = frame
            source = alpha_crop(source, metadata)
            source = source.crop((0, 0, source.width, min(source.height, round(face_height * UNIT / TILE))))
            source = source.resize((TILE, max(1, round(face_height))), Image.Resampling.NEAREST)
            layer.alpha_composite(source, (0, TILE - source.height))

    centered(layer, 'modular/wall_cap', TILE / 2, TILE / 2, TILE, TILE)

    if serving_slot and slot_center is not None:
        low, high = slot_center - TILE * .22, slot_center + TILE * .22
        local_low, local_high = max(0, round(low - cell_top)), min(layer.height, round(high - cell_top))
        if local_high > local_low:
            layer.paste((0, 0, 0, 0), (4, local_low, TILE - 4, local_high))

    image.alpha_composite(layer, (cell_left, cell_top))


def draw_serving_chevrons(image, station, cell):
    cx, cy = xy(cell)
    cy -= SURFACE_OFFSET
    direction = 1 if station['facing'] == 'west' else -1
    draw = ImageDraw.Draw(image)
    for offset in (-TILE * .11, TILE * .06):
        tip_x = cx + direction * (offset + TILE * .10)
        base_x = cx + direction * (offset - TILE * .08)
        half = TILE * .10
        notch = direction * TILE * .04
        points = [
            (round(tip_x), round(cy)),
            (round(base_x), round(cy - half)),
            (round(base_x + notch), round(cy)),
            (round(base_x), round(cy + half)),
        ]
        draw.polygon(points, fill='#344756')


def equipment_art(image, document, station):
    station_id = station['id']
    cell = station['cell']
    cx, floor_y = xy(cell)
    surface_y = floor_y - SURFACE_OFFSET
    view = station_view(document, station_id)
    axis = view['device_axis']

    if station_id.startswith('bin'):
        return
    if station_id.startswith('b') and station_id[1:].isdigit():
        centered(image, f'modular/device_board_{axis}', cx, surface_y, TILE * .84, TILE * .84)
    elif station_id in ('returns', 'sink'):
        centered(image, f'modular/device_{station_id}_{axis}', cx, surface_y, TILE * .84, TILE * .84)
    elif station_id.startswith('p') and station_id[1:].isdigit():
        centered(image, 'modular/top_stove', cx, surface_y, TILE * .82, TILE * .82)
        pot_width = TILE * (.6 if axis == 'vertical' else .73)
        centered(image, f'modular/pot_{axis}', cx, surface_y, pot_width, TILE * .73)
    elif station_id in ('fridge', 'lettuce', 'tomato', 'bread'):
        ingredient = 'beef' if station_id == 'fridge' else station_id
        centered(image, f'modular/source_{ingredient}', cx, surface_y, TILE * .6, TILE * .6)
    elif station_id == 'plates':
        centered(image, 'objects/clean_plate', cx, surface_y, TILE * .76, TILE * .76)
    elif station_id == 'extinguisher':
        centered(image, 'objects/extinguisher', cx, floor_y - TILE * .20, TILE * .55, TILE * .7)
    elif station_id == 'serve':
        draw_serving_chevrons(image, station, cell)


def render(level):
    document = load_map(level)
    width, height = document['size']
    walls = {tuple(cell) for cell in document['walls']}
    station_at = {tuple(cell): entry for entry in document['equipment']
                  for cell in entry.get('cells', [entry['cell']])}
    image = Image.new('RGBA', (1280, 720), '#e7d7b8')
    pen = ImageDraw.Draw(image)
    pen.text((24, 18), f'ChefJeff — STATIC ASSET COMPOSITION — level {level} / {document["presentation"]["theme"]}', fill='#382f29')
    pen.text((24, 38), 'Static atlas composition only; NOT a browser screenshot or gameplay verification.', fill='#786b59')

    # Tile the ground first, using the authored 4x4 repeat pattern beneath walls too.
    for y in range(height):
        for x in range(width):
            key = f'modular/floor_{(x - 1) % GRID_ART["floorRepeat"]}_{(y - 1) % GRID_ART["floorRepeat"]}'
            cx, cy = xy((x, y))
            centered(image, key, cx, cy, TILE, TILE)

    serve = next((entry for entry in document['equipment'] if entry['id'] == 'serve'), None)
    serving_boundary = width - 1 if serve and serve['facing'] == 'west' else 0 if serve and serve['facing'] == 'east' else -1
    serve_surface_y = xy(serve['cell'])[1] - SURFACE_OFFSET if serve else None

    # Painter order follows rows: finish this row's walls before adding its stations.
    for y in range(height):
        for x in range(width):
            if (x, y) not in walls:
                continue
            face_height = GRID_ART['northFace'] * TILE / UNIT if y == 0 and (x, y + 1) not in walls else 0
            wall_layer(image, x, y, face_height,
                       serving_slot=(x == serving_boundary), slot_center=serve_surface_y)

        for x in range(width):
            station = station_at.get((x, y))
            if station is None:
                continue
            cx, floor_y = xy((x, y))
            station_id = station['id']
            if station_id.startswith('bin'):
                anchored(image, 'modular/bin', cx, floor_y)
            else:
                axis = station_view(document, station_id)['run_axis']
                cabinet = 'modular/counter_south' if axis == 'horizontal' else 'modular/counter_east'
                anchored(image, cabinet, cx, floor_y,
                         sprite_lift=GRID_ART['cabinetSpriteLift'])
            if tuple(station['cell']) == (x, y):
                equipment_art(image, document, station)

    for decoration in document.get('presentation', {}).get('decorations', []):
        cx = MAPX + (decoration['cell'][0] + .5) * TILE
        cy = MAPY + TILE * .40
        centered(image, 'modular/' + decoration['asset'], cx, cy,
                 TILE * decoration['scale'] * 2, TILE * decoration['scale'])

    output = ROOT / 'docs/art/checks' / f'level{level}-static-grid-foundation-v1.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert('RGB').save(output)
    print(output)


if __name__ == '__main__':
    for level in (1, 2, 3):
        render(level)
