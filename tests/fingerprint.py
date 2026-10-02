"""Deterministic behaviour fingerprints of the listed service levels.

Refactors must not change gameplay. Each scenario plays a level's frozen,
fixed-seed round and drives both chefs with a seeded, rule-agnostic policy
through the public ``start``/``advance`` interface, recording engine events plus
a compact state projection. ``python tests/fingerprint.py --update`` rewrites
the golden files; do that only for an intentional, reviewed rule change and say
why in the commit message.
"""
from __future__ import annotations
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config_contract as cc  # noqa: E402
from spatial_kitchen import SpatialKitchen  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_policy  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / 'golden'
STEP = .05          # multiple of the engine substep, so quantisation is fixed
DECIDE_EVERY = 10   # policy decision every 0.5 game seconds

# A progress-seeking preference order; it contains no recipe knowledge beyond
# action kinds and is only used to reach deep game states reproducibly.
PRIORITY = ['serve', 'extinguish', 'plate_pot', 'plate_counter', 'plate_from_counter', 'plate_ground',
            'plate_partner', 'assemble', 'merge_plates', 'put_pot', 'return_pot', 'load_counter',
            'load_ground', 'assemble_ground', 'chop', 'wash', 'put_board', 'put_sink', 'take_board', 'take_return',
            'take_sink', 'take_plate', 'fetch', 'take_counter', 'pickup', 'lift_pot', 'swap_pot',
            'throw', 'put_counter', 'clear', 'take_tool', 'put_tool', 'discard', 'empty_pot', 'drop']

SCENARIOS = {
    # name: (level id, policy seed, policy); each plays the level's whole fixed round (180 s).
    # reference: recipe-following cook + assembler; serves, washes, shares chopping, expiries.
    'level1-reference': ('level-1', 0, 'reference'),
    'level2-reference': ('level-2', 0, 'reference'),
    'level3-reference': ('level-3', 0, 'reference'),
    # greedy/random: fires, throws, passes, drops, swaps, floor assembly, conflicts and penalties.
    'level1-greedy': ('level-1', 1, 'greedy'),
    'level1-random': ('level-1', 2, 'random'),
    'level2-greedy': ('level-2', 3, 'greedy'),
    'level2-random': ('level-2', 4, 'random'),
    'level3-greedy': ('level-3', 5, 'greedy'),
    'level3-random': ('level-3', 6, 'random'),
}
ROLES = {'human': 'assembler', 'jeff': 'cook'}


def choose(k, who, rng, policy):
    if policy == 'reference':
        return reference_policy.choose(k, who, ROLES[who])
    chef = k.chefs[who]
    if chef.job:
        return None
    actions = [a for a in k.actions(who) if a.kind not in ('wait', 'continue', 'stop', 'go')]
    if not actions:
        return None
    if policy == 'greedy':
        ranked = {kind: i for i, kind in enumerate(PRIORITY)}
        best = min(ranked.get(a.kind, len(PRIORITY)) for a in actions)
        options = sorted((a for a in actions if ranked.get(a.kind, len(PRIORITY)) == best), key=lambda a: a.key)
        # Occasional exploration keeps greedy loops from dominating a trace.
        if rng.random() < .15:
            options = sorted(actions, key=lambda a: a.key)
        return rng.choice(options)
    kinds = sorted({a.kind for a in actions})
    kind = rng.choice(kinds)
    return rng.choice(sorted((a for a in actions if a.kind == kind), key=lambda a: a.key))


def food(f):
    if f is None:
        return None
    return [f.id, f.stage, round(f.chopped, 3), round(f.heated, 3), f.plate_id, round(f.washed, 3),
            f.ingredient, list(f.components), food(f.contents)]


def projection(k):
    return {
        't': round(k.time, 3), 'money': k.money, 'served': k.served,
        'ended': k.ended, 'failure': k.failure_reason,
        'chefs': {w: [[round(v, 3) for v in k.positions[w]], food(c.hand),
                      c.job.action.key if c.job else None, bool(c.job and c.job.working)]
                  for w, c in sorted(k.chefs.items())},
        'stations': {key: [food(s.food), s.lock, s.fire, s.heating, s.pot_id]
                     for key, s in sorted(k.stations.items())},
        'ground': {key: [g.location, food(g.food), g.lock] for key, g in sorted(k.ground.items())},
        'orders': [[o['id'], o['dish'], o['arrival'], o['deadline'], o['status']] for o in k.orders],
    }


def run(name):
    level, seed, policy = SCENARIOS[name]
    k = SpatialKitchen(cc.load_level(level))
    rng = random.Random(seed)
    decisions, checkpoints = [], []
    step = 0
    while not k.ended:
        if step % DECIDE_EVERY == 0:
            for who in ('human', 'jeff'):
                action = choose(k, who, rng, policy)
                if action:
                    ok, _ = k.start(who, action)
                    decisions.append([round(k.time, 3), who, action.key, ok])
        k.advance(STEP)
        k.assert_invariants()
        step += 1
        if step % 100 == 0:
            checkpoints.append(hashlib.sha256(json.dumps(projection(k), sort_keys=True).encode()).hexdigest()[:16])
    events = [[e['t'], e.get('kind'), e.get('actor'), e.get('action'), e['message']] for e in k.events]
    return {'scenario': name, 'decisions': decisions, 'events': events,
            'checkpoints': checkpoints, 'final': projection(k), 'result': k.result()}


def main():
    if '--update' not in sys.argv:
        print('usage: python tests/fingerprint.py --update')
        return
    GOLDEN.mkdir(exist_ok=True)
    for name in SCENARIOS:
        data = run(name)
        (GOLDEN / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n')
        print(name, len(data['events']), 'events', data['result'])


if __name__ == '__main__':
    main()
