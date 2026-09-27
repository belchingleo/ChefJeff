"""Deterministic behaviour fingerprints of the accepted legacy levels.

The data-driven migration must not change accepted gameplay. Each scenario
drives both chefs with a seeded, rule-agnostic policy through the public
``command``/``advance`` interface and records engine events plus a compact
state projection. ``python tests/fingerprint.py --update`` rewrites the golden
files; do that only for an intentional, reviewed rule change.
"""
from __future__ import annotations
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kitchen import load_config  # noqa: E402
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
            'load_ground', 'chop', 'wash', 'put_board', 'put_sink', 'take_board', 'take_return',
            'take_sink', 'take_plate', 'fetch', 'take_counter', 'pickup', 'lift_pot', 'swap_pot',
            'throw', 'put_counter', 'clear', 'take_tool', 'put_tool', 'discard', 'empty_pot', 'drop']

SCENARIOS = {
    # name: (level, order_seed, spawn_seed, policy seed, policy, game seconds)
    # reference: recipe-following cook + assembler; serves, washes, shares chopping.
    'level1-reference': (1, 7, 0, 0, 'reference', 180),
    'level2-reference': (2, 7, 1, 0, 'reference', 240),
    'level2-reference-expiry': (2, 7, 0, 0, 'reference', 240),  # an order expires; round continues
    'level3-reference': (3, 7, 0, 0, 'reference', 360),
    # greedy/random: fires, throws, drops, swaps, conflicts and penalties.
    'level1-greedy': (1, 11, 0, 1, 'greedy', 180),
    'level1-random': (1, 11, 1, 2, 'random', 120),
    'level2-greedy': (2, 5, 0, 3, 'greedy', 240),
    'level3-random': (3, 7, 1, 6, 'random', 120),
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
        't': round(k.time, 3), 'money': k.money, 'served': k.served, 'bad': k.bad_reviews,
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
    level, order_seed, spawn_seed, seed, policy, seconds = SCENARIOS[name]
    k = SpatialKitchen(load_config() | {'level': level, 'order_seed': order_seed, 'spawn_seed': spawn_seed})
    rng = random.Random(seed)
    decisions, checkpoints = [], []
    step = 0
    while not k.ended and k.time < seconds - 1e-9:
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
