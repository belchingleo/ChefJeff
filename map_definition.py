"""Versioned map documents shared by the renderer and simulation.

The editor boundary is validate_map -> save_map -> load_map. No executable code
or arbitrary asset paths are accepted in a map document.
"""
import copy
import json
import os
from pathlib import Path
import tempfile

MAP_ROOT = Path(__file__).resolve().parent / 'maps'
DECOR_ASSETS = {'decoration_window', 'decoration_menu', 'decoration_rail',
                'decoration_flowerbox', 'decoration_lamp', 'decoration_plant'}


def validate_map(document):
    d = copy.deepcopy(document)
    if d.get('schema_version') != 1:
        raise ValueError('Unsupported map schema')
    size = d.get('size')
    if not isinstance(size, list) or len(size) != 2 or any(type(n) is not int or not 5 <= n <= 64 for n in size):
        raise ValueError('Invalid map size')
    width, height = size
    def cell(p):
        if not isinstance(p, (list, tuple)) or len(p) != 2 or any(type(n) is not int for n in p) or not (0 <= p[0] < width and 0 <= p[1] < height):
            raise ValueError('Invalid map cell')
        return tuple(p)
    walls = [cell(p) for p in d['walls']]
    if len(walls) != len(set(walls)):
        raise ValueError('Duplicate wall')
    boundary = {(x,y) for x in range(width) for y in range(height) if x in (0,width-1) or y in (0,height-1)}
    if not boundary <= set(walls):
        raise ValueError('Map boundary must be closed')
    occupied, ids = set(walls), set()
    for station in d['equipment']:
        key = station['id']
        if not isinstance(key,str) or not key or key in ids:
            raise ValueError('Duplicate or invalid station id')
        ids.add(key)
        p = cell(station['cell'])
        footprint=[cell(v) for v in station.get('cells',[station['cell']])]
        if not footprint or p not in footprint or len(set(footprint))!=len(footprint):
            raise ValueError('Invalid station footprint')
        reached={p}
        while True:
            grown=reached|{q for q in footprint if any(abs(q[0]-r[0])+abs(q[1]-r[1])==1 for r in reached)}
            if grown==reached:break
            reached=grown
        if len(reached)!=len(footprint):raise ValueError('Disconnected station footprint')
        if any(v in occupied for v in footprint):
            raise ValueError('Overlapping stations or wall')
        occupied.update(footprint)
        if station['facing'] not in ('north','south','east','west'):
            raise ValueError('Invalid station facing')
    floor = {(x,y) for x in range(width) for y in range(height)} - occupied
    surfaces = {tuple(p) for e in d['equipment'] for p in e.get('cells',[e['cell']])}
    for station in d['equipment']:
        p, access = cell(station['cell']), cell(station['access'])
        corner = station.get('reach') == 'corner'
        valid_corner = (station['id'].startswith('counter') and abs(p[0]-access[0]) == abs(p[1]-access[1]) == 1
                        and (p[0],access[1]) in surfaces and (access[0],p[1]) in surfaces
                        and not any(q in floor for q in ((p[0]+1,p[1]),(p[0]-1,p[1]),(p[0],p[1]+1),(p[0],p[1]-1))))
        if access not in floor or (not valid_corner if corner else not any(sum(abs(a-b) for a,b in zip(v,access)) == 1 for v in station.get('cells',[p]))):
            raise ValueError('Station needs adjacent reachable access')
    if floor:
        reached, todo = set(), [next(iter(floor))]
        while todo:
            p = todo.pop()
            if p in reached: continue
            reached.add(p)
            todo.extend(q for q in ((p[0]+1,p[1]),(p[0]-1,p[1]),(p[0],p[1]+1),(p[0],p[1]-1)) if q in floor and q not in reached)
        if reached != floor:
            raise ValueError('Disconnected walkable floor')
    presentation = d.get('presentation', {})
    if presentation.get('theme') not in ('courtyard','street','terrace'):
        raise ValueError('Unknown environment theme')
    station_views = presentation.get('station_views', {})
    if not isinstance(station_views, dict):
        raise ValueError('Invalid station views')
    axes = ('horizontal', 'vertical')
    for station_id, view in station_views.items():
        if station_id not in ids:
            raise ValueError('Unknown station view id')
        if (not isinstance(view, dict)
                or view.get('run_axis') not in axes
                or view.get('device_axis') not in axes):
            raise ValueError('Invalid station view axis')
    for p in presentation.get('corner_caps', []):
        if cell(p) not in walls:
            raise ValueError('Decorative corner caps must cover a blocked tile')
    for decor in presentation.get('decorations', []):
        if decor.get('asset') not in DECOR_ASSETS or decor.get('anchor') != 'north_wall':
            raise ValueError('Unsupported decoration')
        p = cell(decor['cell'])
        if p[1] != 0 or p not in walls or not .1 <= decor.get('scale',0) <= .6:
            raise ValueError('Decoration must fit the north wall')
    return d


def load_map(level):
    if type(level) is not int or level not in (1,2,3):
        raise ValueError('Unknown authored map')
    return validate_map(json.loads((MAP_ROOT / f'level-{level}.json').read_text()))


def save_map(document, path):
    """Atomic local editor save; caller chooses the destination, never map data."""
    d = validate_map(document)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, suffix='.json', delete=False) as f:
        json.dump(d,f,ensure_ascii=False,indent=2)
        f.write('\n')
        temp = Path(f.name)
    try:
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


def geometry(document):
    return ({e['id']:{k:tuple(e[k]) if k in ('cell','access') else tuple(tuple(v) for v in e[k]) if k=='cells' else e[k]
                        for k in ('cell','access','facing','reach','cells') if k in e} for e in document['equipment']},
            {tuple(p) for p in document['walls']})
