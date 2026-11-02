"""A level from the editor's design: room size, walls, stations and dishes become a level bundle.

The editor (web-shell) keeps a player's level as a small design and sends it as is; the server
builds the map, the starting inventory and the recipes here, so every check lives in one place.
level_calibration then puts the bundle on the release's rules and measures it.

    {"format": "chefjeff-player-level-1", "name": "拌面小馆", "size": [14, 9],
     "walls": [[6, 3]],
     "stations": [{"type": "stove", "x": 12, "y": 3, "vessel": "pan"},
                  {"type": "ingredient_source", "x": 2, "y": 1, "item": "beef"}, ...],
     "dishes": [{"name": "红烧牛肉面", "price": 90, "items": ["noodles", "beef", "scallion"]}]}

Rules the editor shows as it goes (owner decisions 2026-11-01/02): three room sizes; walls inside the
room may not cut it in two; stations may be set into the outer wall, except at its four corners, and
serving windows and the plate return must be; exactly one sink, plate return and extinguisher rack, one
or two serving windows; three plates at the start; at most four dishes of one to four ingredients. Station ids follow
the client's drawing conventions (serve, sink, returns, extinguisher, b1, p1...).
"""
import copy

import config_contract as cc
from map_definition import STEP, build_map

FORMAT = 'chefjeff-player-level-1'
SIZES = ((12, 8), (14, 9), (16, 10))
TYPES = ('counter', 'board', 'stove', 'ingredient_source', 'serving_window', 'sink', 'plate_return', 'bin', 'tool_rack')
EXACTLY_ONE = ('sink', 'plate_return', 'tool_rack')
IN_THE_WALL = ('serving_window', 'plate_return')  # food leaves and dirty plates come back through the wall
SERVING_WINDOWS = (1, 2)
VESSELS = ('pan', 'pot')
PLATES = 3
MAX_DISHES = 4
MAX_ITEMS = 4
NAME_LENGTH = 20
RELEASE_LEVEL = 'level-1'


def _problem(path, message, code='DESIGN_INVALID'):
    return cc.diag(code, 'ERROR', path, message)


def _ids(stations):
    """Station ids by the conventions the client draws by; a second one of a kind gets a number."""
    fixed = {'serving_window': 'serve', 'sink': 'sink', 'plate_return': 'returns', 'tool_rack': 'extinguisher', 'bin': 'bin'}
    prefix = {'board': 'b', 'stove': 'p', 'counter': 'counter'}
    seen, out = {}, []
    for s in stations:
        kind = s['type']
        n = seen[kind] = seen.get(kind, 0) + 1
        if kind in fixed:
            out.append(fixed[kind] if n == 1 else f'{fixed[kind]}{n}')
        elif kind in prefix:
            out.append(f'{prefix[kind]}{n}')
        else:  # ingredient sources by item; beef keeps its historical id
            item = 'fridge' if s['item'] == 'beef' else s['item']
            same = sum(1 for t in stations[:len(out)] if t['type'] == kind and t['item'] == s['item'])
            out.append(item if same == 0 else f'{item}{same + 1}')
    return out


def _facing(cell, open_cells, size):
    """Face a free floor neighbour, the one most towards the room's centre; None when there is none."""
    centre = ((size[0] - 1) / 2, (size[1] - 1) / 2)
    options = [(name, d) for name, d in STEP.items() if (cell[0] + d[0], cell[1] + d[1]) in open_cells]
    if not options:
        return None
    return max(options, key=lambda o: (o[1][0] * (centre[0] - cell[0]) + o[1][1] * (centre[1] - cell[1]), o[0]))[0]


def _wall_split(size, walls):
    """Whether walls inside the room cut its cells (stations included) into more than one part."""
    width, height = size
    cells = {(x, y) for x in range(1, width - 1) for y in range(1, height - 1)} - walls
    if not cells:
        return True
    todo, seen = [next(iter(cells))], set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        todo.extend(q for q in ((p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)) if q in cells)
    return seen != cells


def bundle(design, registry=None):
    """(level bundle, diagnostics) for a design; the bundle is None when anything is wrong."""
    if not isinstance(design, dict) or design.get('format') != FORMAT:
        return None, [_problem('/format', f'a design starts with "format": "{FORMAT}"')]
    problems = []
    name = design.get('name')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= NAME_LENGTH:
        problems.append(_problem('/name', f'a level name has 1-{NAME_LENGTH} characters'))
    size = tuple(design.get('size') or ())
    if size not in SIZES:
        return None, problems + [_problem('/size', 'the room is 12x8, 14x9 or 16x10')]
    width, height = size
    interior = lambda p: 0 < p[0] < width - 1 and 0 < p[1] < height - 1
    # The outer wall's cells but its corners, which face no floor.
    in_wall = lambda p: (0 <= p[0] < width and 0 <= p[1] < height and not interior(p)
                         and (0 < p[0] < width - 1 or 0 < p[1] < height - 1))

    def cell(value, path, wall=False):
        if (isinstance(value, (list, tuple)) and len(value) == 2 and all(type(v) is int for v in value)
                and (interior(value) or wall and in_wall(value))):
            return tuple(value)
        problems.append(_problem(path, 'a cell inside the room or in its outer wall, not a corner' if wall else 'a cell inside the room'))
        return None

    walls = set()
    for i, w in enumerate(design.get('walls') or []):
        c = cell(w, f'/walls/{i}')
        if c:
            walls.add(c)
    stations, taken = [], set()
    for i, s in enumerate(design.get('stations') or []):
        path = f'/stations/{i}'
        if not isinstance(s, dict) or s.get('type') not in TYPES:
            problems.append(_problem(path, 'a station type of ' + ', '.join(TYPES)))
            continue
        c = cell([s.get('x'), s.get('y')], path, wall=True)
        if c is None:
            continue
        if s['type'] in IN_THE_WALL and interior(c):
            problems.append(_problem(path, f'a {s["type"]} is set into the outer wall', 'STATION_NOT_IN_WALL'))
            continue
        if c in walls or c in taken:
            problems.append(_problem(path, 'two things on one cell'))
            continue
        if s['type'] == 'ingredient_source' and not isinstance(s.get('item'), str):
            problems.append(_problem(path + '/item', 'an ingredient source names its ingredient'))
            continue
        if s['type'] == 'stove' and s.get('vessel') not in VESSELS:
            problems.append(_problem(path + '/vessel', 'a stove holds a pan or a pot'))
            continue
        taken.add(c)
        stations.append({**s, 'cell': c})
    counts = {kind: sum(s['type'] == kind for s in stations) for kind in TYPES}
    for kind in EXACTLY_ONE:
        if counts[kind] != 1:
            problems.append(_problem('/stations', f'exactly one {kind} (found {counts[kind]})', 'UNSUPPORTED_EQUIPMENT_COUNT'))
    if not SERVING_WINDOWS[0] <= counts['serving_window'] <= SERVING_WINDOWS[1]:
        problems.append(_problem('/stations', f'one or two serving_window (found {counts["serving_window"]})',
                                 'UNSUPPORTED_EQUIPMENT_COUNT'))
    if counts['counter'] < PLATES:
        problems.append(_problem('/stations', f'at least {PLATES} counters, for the starting plates', 'INVENTORY_NO_FREE_STATION'))
    if _wall_split(size, walls):
        problems.append(_problem('/walls', 'walls may not cut the kitchen in two: nothing can be passed through a wall',
                                 'WALLS_SPLIT_KITCHEN'))

    release = cc.level_bundle(RELEASE_LEVEL, registry, embed=True)
    items, transforms = release['recipe_catalog']['items'], release['recipe_catalog']['transforms']
    dishes = design.get('dishes')
    if not isinstance(dishes, list) or not 1 <= len(dishes) <= MAX_DISHES:
        problems.append(_problem('/dishes', f'1-{MAX_DISHES} dishes'))
        dishes = []
    recipes = {}
    for n, d in enumerate(dishes, 1):
        path = f'/dishes/{n - 1}'
        parts = d.get('items') if isinstance(d, dict) else None
        if (not isinstance(parts, list) or not 1 <= len(parts) <= MAX_ITEMS or len(set(map(str, parts))) != len(parts)
                or any(p not in items for p in parts)):
            problems.append(_problem(path + '/items', f'1-{MAX_ITEMS} different ingredients of ' + ', '.join(items)))
            continue
        heated = {t['item'] for t in transforms if t['operation'] == 'heat'}
        chopped = {t['item'] for t in transforms if t['operation'] == 'chop'}
        state = lambda item: 'ready' if item in heated else 'chopped' if item in chopped else items[item]['initial_state']
        recipes[f'd{n}'] = {'name': d.get('name'), 'container': 'plate', 'price': d.get('price'),
                            'components': [{'item': p, 'state': state(p), 'label': p} for p in parts]}
    if problems:
        return None, problems

    # Each station faces free floor; a counter boxed in by counters may still reach round a corner.
    open_cells = {(x, y) for x in range(1, width - 1) for y in range(1, height - 1)} - walls - taken
    ids = _ids(stations)
    rows = []
    for s, sid in zip(stations, ids):
        facing = _facing(s['cell'], open_cells, size)
        if facing is None and s['type'] != 'counter':
            problems.append(_problem(f'/stations/{stations.index(s)}', f'{sid} has no floor to stand on in front of it',
                                     'STATION_UNREACHABLE'))
            continue
        row = {'id': sid, 'type': s['type'], 'cell': list(s['cell']), 'facing': facing or 'south'}
        if s['type'] == 'ingredient_source':
            row['params'] = {'item': s['item']}
        rows.append(row)
    if problems:
        return None, problems
    try:
        game_map = build_map('player', [width, height], rows, walls=sorted(walls))
    except ValueError as error:
        return None, [_problem('/stations', str(error), 'MAP_INVALID')]

    level = copy.deepcopy(release['level'])
    level.pop('extensions', None)
    level['name'] = name.strip()
    axis = 0 if width >= height else 1
    split = size[axis] // 2
    centre = (height - 1) / 2 if axis == 0 else (width - 1) / 2
    quarters = (size[axis] / 4, size[axis] * 3 / 4)
    level['spawns'] = {'rule': 'nearest_floor_to_center_shuffled',
                       'centers': [[q, centre] if axis == 0 else [centre, q] for q in quarters],
                       'partition': {'axis': 'xy'[axis], 'split': split}}
    stoves = [(row['id'], s['vessel']) for row, s in zip(rows, stations) if s['type'] == 'stove']
    level['initial_inventory'] = (
        [{'object': 'extinguisher', 'id': 'E1', 'at_type': 'tool_rack'}]
        + [{'object': 'plate', 'id': f'D{n}', 'state': 'clean', 'at_type': 'counter'} for n in range(1, PLATES + 1)]
        + [{'object': vessel, 'id': f'P{n}', 'at': sid} for n, (sid, vessel) in enumerate(stoves, 1)])
    level['goal'] = {'type': 'minimum_money', 'min_money': 0}
    policy = copy.deepcopy(release['order_policy'])
    policy.pop('extensions', None)
    policy['menu'] = [{'recipe_ref': key, 'weight': 1} for key in recipes]
    return {'schema_version': release['schema_version'], 'level': level, 'map': game_map,
            'order_policy': policy, 'recipe_catalog': {'recipes': recipes}}, []
