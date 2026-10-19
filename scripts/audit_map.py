#!/usr/bin/env python3
"""Audit a map before anyone plays it: does it load, can every station be used, can chefs walk and serve?

    python3 scripts/audit_map.py maps/level-2.json
    python3 scripts/audit_map.py layouts.json --level level-2 --seeds 1 2 3 --json

The input is a map document (schema 1 or 2) or a coordinate layout, or a list of layouts:
``{"name": "island", "size": [14, 10], "stations": [["fridge", 2, 1, "south"], ...]}`` (stations may
also be objects with ``id``, ``cell``, ``facing`` and optional ``type``, ``name``, ``params``; see
map_definition.build_map). Each map runs with the rules, recipes, orders and inventory of ``--level``
(inventory placed by station type), spawns on either side of the map's floor-area split. Checks:

  valid      validate_map
  bundle     the level bundle with this map resolves and freezes
  space      Space from each station's access cell (and a step closer), facing it, selects that station
  walk       engine: no walkable point that no direction can leave
  page       KitchenGeometry.ts compiled with tsc: the page walk never starts stuck, floor items draw right
  corridors  warning: a 1-cell-wide corridor that is the only route between stations (chefs cannot pass)
  play       scripted solo chef and scripted pair (tests/reference_policy.py): dishes served per seed

Exit status 1 when a check fails; warnings alone pass. Model-free and local: no API calls.
"""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]

import config_contract as cc  # noqa: E402
from map_definition import build_map, upgrade_map, validate_map  # noqa: E402
from spatial_kitchen import SpatialKitchen  # noqa: E402

TYPESCRIPT = ROOT / 'cocos-kitchen/assets/scripts/KitchenGeometry.ts'
# For each map: every walkable point on a fine grid, every direction, drawn between this tick and the next.
PAGE_RUNNER = r'''const g=require(process.argv[2]),fs=require('fs');const out={};
for(const {name,map} of JSON.parse(fs.readFileSync(process.argv[3],'utf8'))){
  const tick=(map.walk_speed||4.5)*.05,dirs=[];
  for(let i=0;i<16;i++)dirs.push([Math.cos(i*Math.PI/8),Math.sin(i*Math.PI/8)]);
  let cut=0,stuck=0,checked=0;
  for(let x=0;x<map.width;x+=.05)for(let y=0;y<map.height;y+=.05){
    if(!g.footWalkable(map,x,y))continue;
    for(const [dx,dy] of dirs){
      const at=[x,y],next=g.predictWalk(map,at,dx*tick,dy*tick,undefined,tick);
      for(const f of [.25,.5,.75]){
        const drawn=[at[0]+(next[0]-at[0])*f,at[1]+(next[1]-at[1])*f];checked++;
        if(g.footWalkable(map,drawn[0],drawn[1]))continue;
        cut++;
        const from=g.walkStart(map,drawn,at);
        if(!g.footWalkable(map,from[0],from[1])||!dirs.some(([ex,ey])=>{const p=g.predictWalk(map,from,ex*tick,ey*tick,undefined,tick);return Math.hypot(p[0]-from[0],p[1]-from[1])>1e-6;}))stuck++;
      }
    }
  }
  // Food on the floor, anywhere on a floor tile, against every cabinet/wall around it and every chef that could overlap it.
  const solid=new Set((map.walls||[]).map(w=>w.join(','))),depth=[];
  for(const e of Object.values(map.equipment))for(const c of (e.cells||[e.cell]))solid.add(c.join(','));
  for(let x=0;x<map.width;x++)for(let y=0;y<map.height;y++){
    if(solid.has(x+','+y))continue;
    for(const oy of [-.4,-.2,0,.2,.4]){
      const d=g.floorItemDepth(y+oy);
      for(const dx of [-1,0,1]){
        // The row above hangs its front panel (and its contents, +.01) into this tile: draw in front.
        if(solid.has((x+dx)+','+(y-1))&&!(d>g.depthOrder(y-1,'solid')+.01))depth.push({x,y:y+oy,problem:'under the cabinet behind'});
        // Its own row and the rows below are in front of it.
        for(const ry of [y,y+1])if(solid.has((x+dx)+','+ry)&&!(d<g.depthOrder(ry,'solid')))depth.push({x,y:y+oy,problem:'over the cabinet in front'});
      }
      // A chef whose body could overlap it (feet less than 0.9 cells north of it, or anywhere south) stays on top.
      for(let cy=y+oy-.9;cy<=y+oy+1.5;cy+=.05)if(!(d<g.depthOrder(cy,'actor')))depth.push({x,y:y+oy,cy,problem:'over a chef'});
    }
  }
  out[name]={cut,stuck,checked,depthProblems:depth.length,depth:depth.slice(0,5)};
}
console.log(JSON.stringify(out));'''
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def load_maps(path):
    """Map documents from a map file, a layout or a list of layouts."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    layouts = data if isinstance(data, list) else [data]
    return [d if 'schema_version' in d else build_map(d['name'], d['size'], d['stations'], d.get('theme', 'street'))
            for d in layouts]


def kitchen(document, level='level-2', seed=1):
    """A frozen round of ``level`` played on ``document``; on another map than the level's own, the chefs
    spawn either side of the map's floor-area split."""
    bundle = cc.level_bundle(level, embed=True)
    game_map, own = upgrade_map(document), bundle['map']['id'] == document['id']
    bundle['map'] = game_map
    bundle['level'].update(map_ref={'id': game_map['id'], 'version': game_map['revision']}, seeds={'orders': seed, 'spawn': seed % 2})
    if not own:
        floor, size = game_map['floor_areas'], game_map['size']
        axis = 'xy'.index(floor['axis'])
        centers = [[floor['split'] / 2, size[1 - axis] / 2], [(floor['split'] + size[axis]) / 2, size[1 - axis] / 2]]
        bundle['level']['spawns'].update(centers=centers if axis == 0 else [c[::-1] for c in centers],
                                         partition={'axis': floor['axis'], 'split': floor['split']})
    return SpatialKitchen(cc.freeze_bundle(bundle))


def space_misses(k):
    """Stations Space does not select from their access cell (or a step closer), facing them."""
    misses = []
    for key, e in k.equipment.items():
        (ax, ay), (cx, cy) = e['access'], e['cell']
        for stand in ((ax, ay), (ax + (cx - ax) * .3, ay + (cy - ay) * .3)):
            if not k.nav.walkable_point(stand):
                continue
            k.positions['human'], k.positions['jeff'] = stand, (-50, -50)
            k.face('human', cx - ax, cy - ay)
            got = k.selected_station('human')
            if got != key:
                misses.append({'station': key, 'stand': [round(v, 2) for v in stand], 'selected': got})
    return misses


def stuck_points(k):
    """Walkable points (every 7th of a 0.1-cell grid) that a held key in no direction can leave."""
    width, height = k.map_document['size']
    points = [(x / 10, y / 10) for x in range(width * 10) for y in range(height * 10) if k.nav.walkable_point((x / 10, y / 10))][::7]
    stuck = []
    for p in points:
        for a in range(8):
            k.positions['human'], k.positions['jeff'] = p, (-50, -50)
            k.set_manual('human', math.cos(a * math.pi / 4), math.sin(a * math.pi / 4))
            k.advance(.1)
            k.set_manual('human', 0, 0)
            if math.dist(p, k.positions['human']) > 1e-3:
                break
        else:
            stuck.append(p)
    return stuck, len(points)


def compile_geometry(folder):
    """KitchenGeometry.ts compiled to CommonJS in ``folder``; None when tsc or node is unavailable."""
    from test_visual_geometry import KitchenGeometryExecutionTests
    tsc = KitchenGeometryExecutionTests.resolve_tsc(None)
    if not tsc or not shutil.which('node'):
        return None
    out = Path(folder) / 'compiled'
    compiled = subprocess.run([*tsc, str(TYPESCRIPT), '--target', 'ES2019', '--module', 'commonjs',
                               '--outDir', str(out), '--skipLibCheck'], cwd=ROOT, capture_output=True, text=True)
    if compiled.returncode:
        raise RuntimeError(compiled.stdout + compiled.stderr)
    return out / 'KitchenGeometry.js'


def page_checks(maps):
    """PAGE_RUNNER results for snapshot maps {name: map}; None when tsc or node is unavailable."""
    with tempfile.TemporaryDirectory(prefix='audit-map-') as temp:
        geometry = compile_geometry(temp)
        if geometry is None:
            return None
        data, runner = Path(temp) / 'maps.json', Path(temp) / 'run.js'
        data.write_text(json.dumps([{'name': name, 'map': m} for name, m in maps.items()]))
        runner.write_text(PAGE_RUNNER)
        result = subprocess.run(['node', str(runner), str(geometry), str(data)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return json.loads(result.stdout)


def corridors(document):
    """1-cell-wide corridors whose removal separates stations: two chefs cannot pass each other there."""
    width, height = document['size']
    blocked = {tuple(w) for w in document['walls']} | {tuple(c) for e in document['equipment'] for c in e.get('cells', [e['cell']])}
    floor = {(x, y) for x in range(width) for y in range(height)} - blocked

    def sides(removed):
        """Station counts of the floor regions left when ``removed`` is blocked too."""
        left, counts = floor - removed, []
        while left:
            todo, region = [left.pop()], set()
            while todo:
                p = todo.pop()
                region.add(p)
                for dx, dy in NEIGHBOURS:
                    q = (p[0] + dx, p[1] + dy)
                    if q in left:
                        left.remove(q)
                        todo.append(q)
            counts.append(sum(tuple(e['access']) in region for e in document['equipment']))
        return sorted((n for n in counts if n), reverse=True)

    narrow = {(x, y) for x, y in floor
              if {(x - 1, y), (x + 1, y)} <= blocked or {(x, y - 1), (x, y + 1)} <= blocked}
    cut = {p for p in narrow if len(sides({p})) > 1}
    found = []
    while cut:
        todo, group = [cut.pop()], []
        while todo:
            p = todo.pop()
            group.append(p)
            for dx, dy in NEIGHBOURS:
                q = (p[0] + dx, p[1] + dy)
                if q in cut:
                    cut.remove(q)
                    todo.append(q)
        found.append({'cells': sorted(list(p) for p in group), 'stations_each_side': sides(set(group))})
    return sorted(found, key=lambda c: c['cells'])


def play(document, level, seeds):
    """Dishes served by the scripted solo chef and the scripted assembler + cook pair, per seed."""
    import reference_policy
    sys.path.insert(0, str(ROOT / 'scripts'))
    from reference_sweep import drive
    rows = []
    for seed in seeds:
        solo = kitchen(document, level, seed)
        drive(solo, (('human', 'solo'),), lambda k, who, role: reference_policy.choose_solo(k, who), {'human': 10, 'jeff': 10})
        pair = kitchen(document, level, seed)
        drive(pair, (('human', 'assembler'), ('jeff', 'cook')), reference_policy.choose, {'human': 10, 'jeff': 10})
        rows.append({'seed': seed, 'solo_served': solo.served, 'pair_served': pair.served, 'pair_money': pair.money})
    return rows


def audit(document, level='level-2', seeds=(1,), page=None):
    """Every check for one map; ``failures`` and ``warnings`` list what needs attention."""
    report = {'map': document.get('id'), 'size': document.get('size'), 'failures': [], 'warnings': []}
    try:
        validate_map(document)
    except (ValueError, KeyError, TypeError) as exc:
        report['failures'].append(f'invalid map: {exc}')
        return report
    report['stations'] = len(document['equipment'])
    try:
        k = kitchen(document, level)
    except ValueError as exc:
        report['failures'].append(f'{level} does not freeze on this map: {exc}')
        return report
    report['config_hash'] = k.resolved['config_hash']
    report['space_misses'] = space_misses(k)
    report['engine_stuck'], report['engine_points'] = stuck_points(kitchen(document, level))
    report['corridors'] = corridors(upgrade_map(document))
    report['play'] = play(document, level, seeds)
    if page is None:
        page = page_checks({report['map']: k.snapshot()['map']})
    report['page'] = page and page[report['map']]
    if report['space_misses']:
        report['failures'].append(f'Space misses {len(report["space_misses"])} station(s) from their access cell')
    if report['engine_stuck']:
        report['failures'].append(f'engine walk stuck at {len(report["engine_stuck"])} point(s)')
    if report['page'] is None:
        report['warnings'].append('page checks skipped: TypeScript compiler or Node.js unavailable')
    elif report['page']['stuck'] or report['page']['depthProblems']:
        report['failures'].append(f'page walk stuck {report["page"]["stuck"]} time(s), {report["page"]["depthProblems"]} depth problem(s)')
    for c in report['corridors']:
        report['warnings'].append(f'1-cell-wide corridor {c["cells"][0]}..{c["cells"][-1]} ({len(c["cells"])} cells) is the only route '
                                  f'between stations {c["stations_each_side"]}: two chefs cannot pass each other there')
    if not any(r['pair_served'] for r in report['play']):
        report['failures'].append('the scripted pair served nothing')
    return report


def summary(r):
    lines = [f'{r["map"]} {r["size"][0]}x{r["size"][1]}' if r.get('size') else str(r['map'])]
    if 'space_misses' in r:
        page = r['page']
        lines += [f'  bundle   frozen ({r["config_hash"][:19]}), {r["stations"]} stations',
                  f'  space    {r["stations"] - len({m["station"] for m in r["space_misses"]})}/{r["stations"]} stations selected from their access cell',
                  f'  walk     engine {len(r["engine_stuck"])} stuck of {r["engine_points"]} points; '
                  + (f'page {page["stuck"]} stuck of {page["cut"]} cut corners, {page["depthProblems"]} depth problems' if page else 'page skipped'),
                  f'  corridor {len(r["corridors"])} one-wide bottleneck(s)']
        lines += [f'  play     seed {p["seed"]}: solo served {p["solo_served"]}, pair served {p["pair_served"]} (money {p["pair_money"]})'
                  for p in r['play']]
    lines += [f'  FAIL     {f}' for f in r['failures']] + [f'  WARN     {w}' for w in r['warnings']]
    lines.append('  result   ' + ('FAIL' if r['failures'] else 'PASS'))
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('path', help='map document, layout or list of layouts (JSON)')
    parser.add_argument('--level', default='level-2', help='level whose rules and inventory to play (default level-2)')
    parser.add_argument('--seeds', type=int, nargs='+', default=[1], help='order seeds for scripted play (default 1)')
    parser.add_argument('--json', action='store_true', help='print the full reports as JSON')
    args = parser.parse_args(argv)
    try:
        documents = load_maps(args.path)
    except (ValueError, KeyError, TypeError) as exc:
        print(f'cannot build a map from {args.path}: {exc}')
        return 1
    snapshots = {}  # one TypeScript compile for every map that loads; audit() reports the others
    for d in documents:
        try:
            snapshots[d['id']] = kitchen(d, args.level).snapshot()['map']
        except (ValueError, KeyError, TypeError):
            pass
    page = page_checks(snapshots) if snapshots else None
    reports = [audit(d, args.level, args.seeds, page) for d in documents]
    print(json.dumps(reports, ensure_ascii=False, indent=2) if args.json else '\n\n'.join(summary(r) for r in reports))
    return 1 if any(r['failures'] for r in reports) else 0


if __name__ == '__main__':
    raise SystemExit(main())
