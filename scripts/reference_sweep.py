#!/usr/bin/env python3
"""Calibrate order pacing with the deterministic reference policy.

For each level and candidate (interval, per-dish countdown), run the scripted
reference pairs (tests/reference_policy.py) and report net income, served,
expired and open-at-closing orders. Each run takes the better of the two pairs
('classic': assembler + cook; 'zoned': a runner and a maker working either side
of a counter row and passing across it) and of the two role assignments. The
target money suggestion is 50% of the median net income, rounded down to a
multiple of 10 (owner decision, 2026-09-27).

Levels use fixed seeds (owner decision B), so --fixed runs exactly the configured
round; --seeds N instead samples order seeds 1..N as a robustness check.

This is a calibration reference, not a statement about human + AI play: the
reference pair is two scripted chefs. The 'latency' variant lets Jeff decide
only every 3 game seconds to approximate model response time.

    python scripts/reference_sweep.py --fixed --variants fast --out docs/architecture/reports/pacing-sweep-fixed.json

--ladder runs each level's configured round with a baseline ladder (owner decision
2026-09-28) and the collaboration analysis of every rung:

- solo: one scripted chef (tests/reference_policy.choose_solo), the other idle;
- solo + random: the same chef with a partner choosing uniformly among its legal
  actions (seeded);
- pair: the best scripted reference pair (the calibration above).

A model-controlled Jeff is the fourth rung; it needs a paid model and is measured
from real rounds (collaboration_analyzer.py on a session bundle). The level design
constraint "one chef cannot reach the target" is checked against the solo rung.

    python scripts/reference_sweep.py --ladder --out docs/architecture/reports/baseline-ladder.json
"""
import argparse
import itertools
import json
from multiprocessing import Pool
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

import config_contract as cc  # noqa: E402

INTERVALS = (20000, 25000, 30000, 35000, 40000, 45000)
COUNTDOWNS = {'steak': (60000, 75000, 90000), 'burger': (75000, 90000, 105000, 120000, 135000)}
MENUS = {1: ('steak',), 2: ('burger',), 3: ('steak', 'burger')}
VARIANTS = {'fast': 10, 'latency': 60}  # jeff decision period in 0.05 s ticks (0.5 s / 3 s)


def candidates(level):
    for interval in INTERVALS:
        for combo in itertools.product(*(COUNTDOWNS[d] for d in MENUS[level])):
            countdowns = dict(zip(MENUS[level], combo))
            # At most 5 tickets can wait at once: floor(p / I) + 1 <= 5.
            if all(p // interval + 1 <= 5 for p in countdowns.values()):
                yield interval, countdowns


def bundle(level, interval, countdowns, seed):
    b = cc.level_bundle(f'level-{level}', embed=True)
    if seed is not None:
        b['level']['seeds'] = {'orders': seed, 'spawn': seed % 2}
    b['order_policy']['interval_game_ms'] = interval
    b['order_policy']['patience_by_recipe'] = dict(countdowns)
    b['level']['goal']['min_money'] = 0
    return b


def drive(k, roles, policy, period):
    """Run one round to closing. Stalled routes are the engine's job (movement.stall_replan)."""
    step = 0
    while not k.ended:
        for who, role in roles:
            if step % period[who] == 0:
                action = policy(k, who, role)
                if action:
                    k.start(who, action)
        k.advance(.05)
        step += 1


def play(level, interval, countdowns, seed, variant, pair, swap):
    import reference_policy
    from spatial_kitchen import SpatialKitchen
    policy, roles = {'classic': (reference_policy.choose, ('assembler', 'cook')),
                     'zoned': (reference_policy.choose_zoned, ('maker', 'runner'))}[pair]
    if swap:
        roles = roles[::-1]
    k = SpatialKitchen(cc.freeze_bundle(bundle(level, interval, countdowns, seed)))
    drive(k, (('human', roles[0]), ('jeff', roles[1])), policy, {'human': 10, 'jeff': VARIANTS[variant]})
    return k


def random_partner(seed):
    import random
    rng = random.Random(seed)

    def choose(k, who, role):
        if k.chefs[who].job is not None:
            return None
        actions = [a for a in k.actions(who) if a.kind != 'stop']
        return rng.choice(actions) if actions else None
    return choose


def rung(level, name, seed=0):
    """One ladder rung on the level's configured (frozen) round."""
    import reference_policy
    from spatial_kitchen import SpatialKitchen
    from collaboration_analyzer import analyze_collaboration
    policy = cc.load_level(f'level-{level}')['order_policy']
    if name == 'pair':
        best = max(((pair, swap) for pair in ('classic', 'zoned') for swap in (False, True)),
                   key=lambda ps: play(level, policy['interval_game_ms'], policy['patience_by_recipe'], None, 'fast', *ps).money)
        k = play(level, policy['interval_game_ms'], policy['patience_by_recipe'], None, 'fast', *best)
        label = best[0] + (' swapped' if best[1] else '')
    else:
        k = SpatialKitchen(cc.load_level(f'level-{level}'))
        partner = random_partner(seed)

        def choose(k, who, role):
            return reference_policy.choose_solo(k, who) if role == 'solo' else partner(k, who, role)
        roles = (('human', 'solo'),) + ((('jeff', 'random'),) if name == 'solo+random' else ())
        drive(k, roles, choose, {'human': 10, 'jeff': 10})
        label = name
    report = analyze_collaboration(k)
    return {'level': level, 'rung': name, 'policy': label, 'money': k.money, 'served': k.served,
            'expired': sum(o['status'] == 'expired' for o in k.orders),
            'contribution_rate': report['contribution_rate'], 'harmful': report['harmful']['by_reason'],
            'wasted': report['wasted']['by_label'], 'dishes_with_both_chefs': report['dishes_with_both_chefs'],
            'cross_chef_handoffs': report['cross_chef_handoffs'],
            'chefs': {w: {x: c[x] for x in ('actions', 'contributing', 'share_of_contributing')} for w, c in report['chefs'].items()}}


def ladder(levels):
    rows = []
    for level in levels:
        target = cc.load_level(f'level-{level}')['level']['goal']['min_money']
        for name in ('solo', 'solo+random', 'pair'):
            row = rung(level, name)
            row['target'] = target
            row['reaches_target'] = row['money'] >= target
            rows.append(row)
    return rows


def run(job):
    level, interval, countdowns, seed, variant = job
    best = None
    for pair in ('classic', 'zoned'):
        for swap in (False, True):
            k = play(level, interval, countdowns, seed, variant, pair, swap)
            if best is None or k.money > best[0].money:
                best = (k, pair, swap)
    k, pair, swap = best
    kinds = [e['kind'] for e in k.events]
    return {'level': level, 'interval': interval, 'countdowns': countdowns, 'seed': seed, 'variant': variant,
            'pair': pair + (' swapped' if swap else ''),
            'money': k.money, 'served': k.served, 'orders': len(k.orders),
            'expired': sum(o['status'] == 'expired' for o in k.orders),
            'open_at_close': sum(o['status'] == 'unresolved_at_close' for o in k.orders),
            'refused': kinds.count('dish_rejected'), 'wrong_dish': kinds.count('wrong_dish'),
            'burnt_accepted': sum(1 for e in k.events if e['kind'] == 'served' and e.get('adjustment')),
            'passes': kinds.count('thrown'), 'fires': k.fires}


def summarize(rows):
    groups = {}
    for row in rows:
        key = (row['level'], row['variant'], row['interval'], json.dumps(row['countdowns'], sort_keys=True))
        groups.setdefault(key, []).append(row)
    out = []
    for (level, variant, interval, countdowns), group in sorted(groups.items()):
        money = sorted(r['money'] for r in group)
        median = statistics.median(money)
        out.append({'level': level, 'variant': variant, 'interval_s': interval / 1000,
                    'countdowns_s': {k: v / 1000 for k, v in json.loads(countdowns).items()},
                    'orders': group[0]['orders'], 'runs': len(group),
                    'money_median': median, 'money_min': money[0], 'money_max': money[-1],
                    'served_median': statistics.median(r['served'] for r in group),
                    'expired_median': statistics.median(r['expired'] for r in group),
                    'open_at_close_median': statistics.median(r['open_at_close'] for r in group),
                    'refused_total': sum(r['refused'] for r in group), 'fires_total': sum(r['fires'] for r in group),
                    'pairs': sorted({r['pair'] for r in group}), 'passes_median': statistics.median(r['passes'] for r in group),
                    'target_50pct': max(0, int(median * .5) // 10 * 10)})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, default=8)
    parser.add_argument('--fixed', action='store_true', help="use each level's configured seeds (one run per candidate)")
    parser.add_argument('--levels', default='1,2,3')
    parser.add_argument('--variants', default='fast,latency')
    parser.add_argument('--only', help='JSON {level: [[interval_ms, {dish: countdown_ms}], ...]} to restrict candidates')
    parser.add_argument('--ladder', action='store_true', help="baseline ladder on each level's configured round")
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'architecture' / 'reports' / 'pacing-sweep.json'))
    args = parser.parse_args()
    if args.ladder:
        rows = ladder([int(x) for x in args.levels.split(',')])
        Path(args.out).write_text(json.dumps({'ladder': rows}, ensure_ascii=False, indent=1) + '\n')
        for row in rows:
            print(row['level'], row['rung'], row['money'], '/', row['target'], row['served'], row['contribution_rate'], row['harmful'], row['wasted'])
        return
    levels = [int(x) for x in args.levels.split(',')]
    only = json.loads(args.only) if args.only else None
    jobs = []
    for level in levels:
        pool = only[str(level)] if only else list(candidates(level))
        for interval, countdowns in pool:
            for variant in args.variants.split(','):
                for seed in ([None] if args.fixed else range(1, args.seeds + 1)):
                    jobs.append((level, interval, countdowns, seed, variant))
    with Pool() as workers:
        rows = workers.map(run, jobs, chunksize=4)
    summary = summarize(rows)
    Path(args.out).write_text(json.dumps({'seeds': 'fixed' if args.fixed else args.seeds, 'summary': summary}, ensure_ascii=False, indent=1) + '\n')
    for row in summary:
        print(row['level'], row['variant'], row['interval_s'], row['countdowns_s'], row['orders'], row['money_median'],
              row['served_median'], row['expired_median'], row['target_50pct'])


if __name__ == '__main__':
    main()
