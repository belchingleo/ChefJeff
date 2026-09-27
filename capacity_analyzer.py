"""Capacity Analyzer v0.1: structural bounds and load risks of one configuration.

    analyze_capacity(resolved, profile=None) -> report

Reads a resolved configuration (draft or frozen) and never changes it, the
map, recipes, orders or any chef decision. It reports necessary conditions and
risks, not playability: no optimal two-chef schedule is solved, transport and
throws are excluded from bounds, and anything not modelled is listed under
``coverage``. Unknown values are ``None`` with a reason, never 0.
"""
from __future__ import annotations
import copy
import itertools
import json
import math
import random
from pathlib import Path

import config_contract as cc

ANALYZER_VERSION = 'capacity-analyzer-0.1'
DEFAULT_PROFILE = {'shared_work': True}
ASSUMPTIONS = [
    'Lower bounds exclude walking, throwing and handoff transport (optimistic).',
    'Chefs are interchangeable; each attended step needs one chef for its whole duration; heating is unattended.',
    'Shared work shortens a step only on stations whose map geometry offers a second, perpendicular operation side.',
    'Every served dish returns one dirty plate that must be washed before reuse.',
    'Model response latency, pausing and human reaction time are excluded.',
    'Spawn sides are assigned by the spawn seed; walking references are reported for every assignment.',
    'Averages are necessary conditions: bursts can be absorbed by patience and backlog, and prepared-ahead food is allowed.',
]
COVERAGE = {
    'production_chain': 'full',
    'shared_work': 'partial: geometry of second sides and rate multipliers; worker coordination not modelled',
    'transport': 'reference only: single-chef walking routes on the real navigation graph; not a bound',
    'throw_and_handoff': 'not modelled',
    'plate_cycle': 'partial: dining + washing occupancy per dish; return-station queueing not modelled',
    'fire_and_burning': 'not modelled',
    'scheduling': 'not solved: no optimal two-chef schedule',
}


def _ms(seconds):
    return None if seconds is None else int(round(seconds * 1000))


def _frozen_copy(resolved):
    """A frozen copy for geometry only; the caller's object is never touched."""
    work = copy.deepcopy(resolved)
    if work.get('status') == 'frozen':
        return work
    for name in ('orders', 'spawn'):
        if work['level']['seeds'][name] is None:
            work['level']['seeds'][name] = 0
    return cc.freeze_config(work, random.Random(0))[0]


class _Geometry:
    def __init__(self, kitchen):
        self.k = kitchen
        self.points = {}
        for key in kitchen.stations:
            station = kitchen.equipment[key]
            if station.get('reach') == 'corner':
                points = [station['access']]
            else:
                access = sorted({n for c in station.get('cells', [station['cell']]) for n in kitchen.nav.neighbors(c)})
                points = []
                for a in access:
                    try:
                        points.append(kitchen.operation_point(key, a))
                    except ValueError:
                        continue
            self.points[key] = [p for p in points if kitchen.nav.walkable_point(p)]
        self._cache = {}

    def walk(self, a, b):
        """Shortest walking distance in cells between two operation points or stations."""
        key = (a, b)
        if key not in self._cache:
            starts = [a] if isinstance(a, tuple) else self.points[a]
            ends = [b] if isinstance(b, tuple) else self.points[b]
            best = math.inf
            for p, q in itertools.product(starts, ends):
                try:
                    route = self.k.nav.shortest_path(p, q)
                except ValueError:
                    continue
                best = min(best, sum(math.dist(x, y) for x, y in zip(route, route[1:])))
            self._cache[key] = best
        return self._cache[key]

    def second_side(self, key):
        """Whether two chefs can work this station from perpendicular sides (as the engine requires)."""
        station = self.k.equipment[key]
        if station.get('reach') == 'corner':
            return False
        cell = station['cell']
        access = self.k.nav.neighbors(cell)
        return any((a[0] - cell[0]) * (b[0] - cell[0]) + (a[1] - cell[1]) * (b[1] - cell[1]) == 0
                   for a, b in itertools.combinations(access, 2))


def _mix(policy, plan):
    if policy['mode'] == 'fixed_interval_seeded':
        total = sum(e['weight'] for e in policy['menu'])
        return {e['recipe_ref']: e['weight'] / total for e in policy['menu']}
    counts = {}
    for order in plan:
        counts[order['recipe_ref']] = counts.get(order['recipe_ref'], 0) + 1
    return {r: n / len(plan) for r, n in counts.items()} if plan else {}


def analyze_capacity(resolved, profile=None):
    from spatial_kitchen import SpatialKitchen
    profile = {**DEFAULT_PROFILE, **(profile or {})}
    frozen = _frozen_copy(resolved)
    k = SpatialKitchen(frozen)
    r = k.rules
    geo = _Geometry(k)
    diagnostics = []
    chefs = len(frozen['level']['actors'])
    h = r.handling

    # ① Capabilities and reachability on the real navigation graph.
    unreachable = sorted(key for key, pts in geo.points.items() if not pts)
    for kind in {r.station_types[key] for key in unreachable}:
        same = r.of_type(kind)
        if all(key in unreachable for key in same):
            diagnostics.append(cc.diag('REQUIRED_STATION_UNREACHABLE', 'ERROR', '/map/equipment',
                                       f'no {kind} can be operated from walkable floor', sorted(same)))
        else:
            diagnostics.append(cc.diag('STATION_UNREACHABLE', 'WARNING', '/map/equipment',
                                       f'some {kind} stations have no walkable operation side', [s for s in same if s in unreachable]))

    def best_multiplier(station, capability):
        rule = r.shared(station, capability)
        if not rule or not profile['shared_work'] or not geo.second_side(station):
            return float(rule['rate_multiplier'].get('1', 1.)) if rule else 1.
        return max(float(v) for v in rule['rate_multiplier'].values())

    def chef_time_factor(station, capability):
        """Minimum chef-seconds per second of single-worker work (n / multiplier[n])."""
        rule = r.shared(station, capability)
        if not rule:
            return 1.
        return min(int(n) / float(m) for n, m in rule['rate_multiplier'].items() if float(m) > 0)

    boards, stoves, sinks = r.of_type('board'), r.of_type('stove'), r.of_type('sink')
    shared_capable = {'board': [b for b in boards if r.shared(b, 'chop') and geo.second_side(b)],
                      'sink': [s for s in sinks if r.shared(s, 'wash') and geo.second_side(s)]}
    board_rate = max((r.work_rate(b, 'chop') for b in boards), default=None)
    fastest_chop = max((r.work_rate(b, 'chop') * best_multiplier(b, 'chop') for b in boards), default=None)
    chop_factor = min((chef_time_factor(b, 'chop') / r.work_rate(b, 'chop') for b in boards), default=None)
    stove_rate = max((r.work_rate(s, 'heat') for s in stoves), default=None)
    sink = sinks[0]
    wash_duration = r.wash_work / (r.work_rate(sink, 'wash') * best_multiplier(sink, 'wash'))
    wash_chef = r.wash_work * chef_time_factor(sink, 'wash') / r.work_rate(sink, 'wash')

    # Spawn assignments: the seed decides which chef takes which side.
    spec = frozen['level']['spawns']
    axis = 0 if spec['partition']['axis'] == 'x' else 1
    split = spec['partition']['split']
    candidates = [min((c for c in k.floor if (c[axis] < split) == (center[axis] < split)),
                      key=lambda c: (math.dist(c, center), c[1 - axis], c[axis]))
                  for center in (tuple(center) for center in spec['centers'])]
    assignments = [dict(zip(('human', 'jeff'), order)) for order in (candidates, candidates[::-1])]
    configured = {who: tuple(round(v, 4) for v in k.positions[who]) for who in ('human', 'jeff')} if resolved.get('status') == 'frozen' else None

    # ② Per-dish production DAG, bounds and walking references.
    plate_homes = [e['at'] for e in frozen['level']['initial_inventory'] if e['object'] == 'plate']
    serves = r.of_type('serving_window')

    def chain(item, state):
        steps, current, stations = [('fetch', h, True)], r.items[item]['initial_state'], []
        work_units = {'chop': 0., 'heat': 0.}
        sources = [key for key, value in r.sources.items() if value == item]
        stations.append(sources)
        guard = 0
        while current != state and guard < 8:
            guard += 1
            t = next((t for t in list(r.chop.values()) + list(r.heat.values())
                      if t['item'] == item and t['from'] == current), None)
            if t is None:
                return None
            work = cc.seconds(t['work_game_ms'])
            work_units[t['operation']] += work
            if t['operation'] == 'chop':
                steps += [('put_board', h, True), ('chop', work / fastest_chop, True, work * chop_factor), ('take_board', h, True)]
                stations.append(boards)
            else:
                steps += [('put_pot', h, True), ('heat', work / stove_rate, False)]
                stations.append(stoves)
            current = t['to']
        steps.append(('plate', h, True))
        return steps, stations, work_units

    dishes = {}
    menu = r.menu
    for recipe in menu:
        components, longest, chef_time, routes = [], 0., 2 * h, {}  # take plate + serve
        feasible = True
        for comp in r.recipes[recipe]['components']:
            found = chain(comp['item'], comp['state'])
            if found is None:
                feasible = False
                continue
            steps, stations, work_units = found
            duration = sum(s[1] for s in steps)
            attended = sum((s[3] if len(s) > 3 else s[1]) for s in steps if s[2])
            longest = max(longest, duration)
            chef_time += attended
            components.append({'item': comp['item'], 'state': comp['state'], 'steps': [s[0] for s in steps],
                               'duration_game_ms': _ms(duration), 'chef_time_game_ms': _ms(attended),
                               'station_groups': stations, 'work_units': work_units})
        if not feasible:
            dishes[recipe] = {'components': components, 'first_dish_lower_bound_game_ms': None,
                              'reason': 'a component has no transform chain'}
            continue
        critical = longest + h  # serve after the last component is plated
        bound = max(critical, chef_time / chefs)
        # Single-chef walking reference for each spawn assignment (not a bound).
        for i, spawn in enumerate(assignments):
            for who, start in spawn.items():
                position, walked = tuple(start), 0.
                for comp in components:
                    for group in comp['station_groups']:
                        target = min(group, key=lambda s: geo.walk(position, s))
                        walked += geo.walk(position, target)
                        position = geo.points[target][0] if geo.points[target] else position
                plate = min(plate_homes, key=lambda s: geo.walk(position, s))
                walked += geo.walk(position, plate) + geo.walk(plate, min(serves, key=lambda s: geo.walk(plate, s)))
                processing = sum(c['duration_game_ms'] for c in components) / 1000 + 2 * h
                routes[f'assignment_{i}:{who}'] = _ms(walked / r.walk_speed + processing)
        dishes[recipe] = {
            'name': r.recipe_names[recipe], 'price': r.prices[recipe], 'components': components,
            'critical_path_game_ms': _ms(critical), 'chef_time_game_ms': _ms(chef_time),
            'first_dish_lower_bound_game_ms': _ms(bound),
            'first_dish_lower_bound_basis': 'max(critical path, chef time / chefs); transport excluded',
            'single_chef_walking_reference_game_ms': routes,
            'walking_reference_range_game_ms': [min(routes.values()), max(routes.values())] if routes else None,
        }
        for c in components:
            c.pop('station_groups')
            dishes[recipe].setdefault('_work', []).append(c.pop('work_units'))

    # ③ Steady-state resource load (per dish demand / parallel capacity).
    pots = r.pot_count
    capacity = {
        'chef': (chefs, 'chefs'),
        'board': (sum(r.work_rate(b, 'chop') * best_multiplier(b, 'chop') for b in boards), 'work-seconds per second'),
        'stove_with_pot': (min(len(stoves), pots), 'stoves holding a pot'),
        'sink': (sum(r.work_rate(s, 'wash') * best_multiplier(s, 'wash') for s in sinks), 'work-seconds per second'),
        'plate': (r.plate_count, 'plates'),
    }
    demand = {group: {} for group in capacity}
    for recipe in menu:
        dish = dishes[recipe]
        if dish.get('first_dish_lower_bound_game_ms') is None:
            continue
        work = dish.pop('_work')
        chop_work = sum(w['chop'] for w in work)
        heat_work = sum(w['heat'] for w in work) / stove_rate if stove_rate else 0.
        plate_cycle = r.dining + wash_duration + 2 * h
        demand['chef'][recipe] = dish['chef_time_game_ms'] / 1000 + wash_chef + 3 * h
        demand['board'][recipe] = chop_work
        demand['stove_with_pot'][recipe] = heat_work
        demand['sink'][recipe] = r.wash_work
        demand['plate'][recipe] = plate_cycle
    plan = frozen['order_plan']['orders']
    mix = _mix(frozen['order_policy'], plan)
    lb_by_group, loads = {}, {}
    policy = frozen['order_policy']
    interval = cc.seconds(policy['interval_game_ms']) if 'interval_game_ms' in policy else None
    for group, (cap, _) in capacity.items():
        per_order = sum(p * demand[group].get(recipe, 0.) for recipe, p in mix.items())
        lb_by_group[group] = None if cap <= 0 else per_order / cap
        loads[group] = None if (cap <= 0 or not interval) else per_order / (interval * cap)
        if cap <= 0 and per_order > 0:
            diagnostics.append(cc.diag('NO_CAPACITY', 'ERROR', f'/resources/{group}', f'dishes need {group} but none is available'))
    known = {g: v for g, v in lb_by_group.items() if v is not None}
    binding = max(known, key=known.get) if known else None
    I_lb = known[binding] if binding else None
    for group, load in loads.items():
        if load is not None and load > 1:
            diagnostics.append(cc.diag('AVERAGE_OVERLOAD', 'WARNING', f'/resources/{group}',
                                       f'average {group} load {load:.2f} exceeds 1 at the configured interval; '
                                       'this is a risk, not proof that the goal is impossible',
                                       {'interval_game_ms': _ms(interval), 'I_resource_lb_game_ms': _ms(lb_by_group[group])}))

    # ④ This round's plan: arrivals, deadlines, goal.
    goal = frozen['level']['goal']
    target = goal['min_served'] if goal['type'] == 'legacy_all_gates' else goal['min_deliveries']
    D = r.round_limit
    tight = []
    for order in plan:
        bound = dishes.get(order['recipe_ref'], {}).get('first_dish_lower_bound_game_ms')
        if bound is not None and order['deadline_game_ms'] - order['arrival_game_ms'] < bound:
            tight.append(order['order_id'])
    if tight:
        diagnostics.append(cc.diag('PATIENCE_BELOW_PROCESSING', 'WARNING', '/order_plan',
                                   'these orders cannot be produced from scratch within their window; food prepared ahead can still serve them', tight))
    cheapest = sorted((demand['chef'].get(o['recipe_ref'], math.inf) for o in plan))[:target]
    need = sum(cheapest)
    if target and len(cheapest) == target and need > chefs * D:
        diagnostics.append(cc.diag('GOAL_EXCEEDS_CAPACITY', 'ERROR', '/level/goal',
                                   'even the least demanding orders for the goal need more chef time than the round provides',
                                   {'chef_time_needed_game_ms': _ms(need), 'chef_time_available_game_ms': _ms(chefs * D)}))
    arrivals = sorted(o['arrival_game_ms'] for o in plan)
    min_bound = min((d['first_dish_lower_bound_game_ms'] for d in dishes.values() if d.get('first_dish_lower_bound_game_ms')), default=None)
    if target and len(arrivals) >= target and min_bound is not None and arrivals[target - 1] + min_bound > _ms(D):
        diagnostics.append(cc.diag('LATE_GOAL_ORDERS', 'WARNING', '/order_plan',
                                   'the goal needs orders that arrive too late to cook from scratch before closing; only prepared-ahead food can serve them',
                                   {'goal_order_arrival_game_ms': arrivals[target - 1], 'shortest_dish_bound_game_ms': min_bound}))

    status = 'partial'
    report = {
        'analyzer_version': ANALYZER_VERSION,
        'input_config_hash': resolved.get('config_hash') or 'sha256:' + cc.sha256(resolved),
        'input_status': resolved.get('status'),
        'level_id': frozen['level']['id'],
        'schema_valid': True, 'structurally_valid': not cc.errors(diagnostics), 'analysis_status': status,
        'profile': profile, 'assumptions': ASSUMPTIONS, 'coverage': COVERAGE,
        'spawns': {'rule': spec['rule'], 'candidates': [list(c) for c in candidates],
                   'assignments': [{w: list(p) for w, p in a.items()} for a in assignments],
                   'configured': {w: list(p) for w, p in configured.items()} if configured else None},
        'geometry': {'unreachable_stations': unreachable, 'shared_work_capable': shared_capable},
        'dishes': dishes,
        'mix': mix,
        'resources': {g: {'capacity': cap, 'unit': unit, 'demand_per_dish_game_ms': {k2: _ms(v) for k2, v in demand[g].items()}}
                      for g, (cap, unit) in capacity.items()},
        'resource_lower_bounds_game_ms': {g: _ms(v) for g, v in lb_by_group.items()},
        'resource_loads': {g: None if v is None else round(v, 4) for g, v in loads.items()},
        'I_resource_lb_game_ms': _ms(I_lb), 'binding_resource': binding,
        'plan': {'orders': len(plan), 'goal_deliveries': target, 'round_limit_game_ms': _ms(D),
                 'configured_interval_game_ms': _ms(interval), 'order_algorithm': frozen['order_plan']['algorithm']},
        'suggested_interval_game_ms': None,
        'suggestion_reason': 'no calibration reference (measured or reference-schedule runs) exists; I_resource_lb is a necessary lower bound, not a safe interval',
        'diagnostics': diagnostics,
    }
    if resolved.get('status') != 'frozen':
        report['plan']['note'] = 'draft input: the order plan was drawn with seed 0 for analysis only'
    return report


def main(argv=None):
    import sys
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print('usage: python capacity_analyzer.py <level-id | bundle.json> [--orders-seed N --spawn-seed N]')
        return 2
    target = args[0]
    bundle = json.loads(Path(target).read_text(encoding='utf-8')) if target.endswith('.json') else cc.level_bundle(target)
    for flag, name in (('--orders-seed', 'orders'), ('--spawn-seed', 'spawn')):
        if flag in args:
            bundle['level']['seeds'][name] = int(args[args.index(flag) + 1])
    draft, diagnostics = cc.resolve_config(bundle)
    if draft is None:
        print(json.dumps({'structurally_valid': False, 'diagnostics': diagnostics}, ensure_ascii=False, indent=2))
        return 1
    seeded = all(v is not None for v in bundle['level']['seeds'].values())
    report = analyze_capacity(cc.freeze_config(draft)[0] if seeded else draft)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
