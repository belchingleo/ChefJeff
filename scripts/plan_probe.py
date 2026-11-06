#!/usr/bin/env python3
"""Does Jeff's plan hold him back from an emergency? A controlled check with the real model, run locally.

    python3 scripts/plan_probe.py [--mode choice|rolling] [--repeats 3] [--dry-run] [--out report.json]

It builds two fixed emergencies on level 2 from a scripted round (no player data): cooked beef in a
pan a few seconds from burning, and a stove on fire, each with Jeff idle and empty-handed. Each is
asked in three arms with the same kitchen: plan mode off, plan mode on with no plan yet (the request
asks for one), and plan mode on while a plan of unrelated steps holds. For each arm it reports how
often the model chose an action that deals with the emergency (lift that pan, take a clean plate to
plate its food, or plate it; take the extinguisher), the mean probability it gave those actions, and
how often it chose wait.
Acceptance: in every emergency, the arm with a plan held chooses the emergency at least as often as
the arm with plan mode off.

A third kitchen checks that Jeff drops a plan the kitchen has left behind: level 1 played by the
reference policy for both chefs until every order is served and none is still to come, while Jeff
holds a plan to fetch, chop, cook and plate beef. It reports how often the model answered drop to
plan_keep. Acceptance: drop in more than half of the answers.

--mode rolling checks the two-step rolling intent instead (harness ROLLING_RULE). Every arm carries the
same previous decision in recent_decisions, one that agrees with the kitchen: wait, accepted, 3 game
seconds earlier (Jeff is idle and empty-handed). In the held arm and the stale kitchen that decision
carries the intent of the first two steps of those plans, as his previous request would have left it,
so the arms differ only in the intent; every rolling request asks for a new one. (An earlier version
gave the rolling arms a started fetch he never finished, a history at odds with the kitchen that pulled
Jeff to fetch on its own.) Since rolling-v3 a pan about to burn leaves the intent out of the request, so in
that kitchen the held arm checks that it does. The emergencies have the same acceptance. In the
stale kitchen there is no keep or drop: it reports how often his new intent repeated the stale one
(the same steps, or the same first step), and accepts at most half of the answers doing so.

The key is read the way the game reads it (jev.load_key) and is never printed. It calls the model,
so run it on your own machine. --dry-run builds the requests and prints their size only.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from statistics import mean
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from harness import Plan, work_item, work_items  # noqa: E402
from jev import NO_MEMORY, compose_payload  # noqa: E402
from kitchen import load_config  # noqa: E402
from levels import level_config  # noqa: E402
from spatial_kitchen import SpatialKitchen  # noqa: E402
from whitebox_server import SpatialJevClient  # noqa: E402

LEVEL = 'level-2'
UNRELATED = ('fetch:lettuce', 'chop:lettuce', 'plate:lettuce', 'serve')
STALE_PLAN = ('fetch:beef', 'chop:beef', 'cook:beef', 'plate:beef')
ARMS = ('plan_off', 'plan_asking', 'plan_held')
BURN_MARGIN = 4.0       # game seconds left before the cooked food burns
PRICE_PER_M = 0.042     # USD per million input tokens, for the estimate only


def pan(k):
    """The stove whose pan holds food, and that food, or (None, None)."""
    return next(((key, s.food) for key, s in k.stations.items() if key in k.pots and s.food), (None, None))


def reach(condition, limit=150.0):
    """Play level 2 with the human cooking until food is in a pan, then nobody acts, until condition(k) holds."""
    import reference_policy
    k = SpatialKitchen(level_config(load_config(), LEVEL))
    step = 0
    while k.time < limit:
        if condition(k) and k.chefs['jeff'].job is None and k.chefs['jeff'].hand is None:
            return k
        if step % 10 == 0 and pan(k)[1] is None and k.chefs['human'].job is None:
            action = reference_policy.choose(k, 'human', 'cook')
            if action:
                k.start('human', action)
        k.advance(.05)
        step += 1
    raise RuntimeError('the scripted round did not reach the emergency')


def about_to_burn(k):
    stove, food = pan(k)
    if food is None:
        return False
    ready, burn, _ = k.rules.heat_thresholds(food.ingredient)
    return ready <= food.heated and burn - food.heated <= BURN_MARGIN


def on_fire(k):
    return any(s.fire for s in k.stations.values())


def emergencies():
    """[(name, kitchen, keys of the actions that deal with it)] for each fixed emergency."""
    burn = reach(about_to_burn)
    stove, food = pan(burn)
    state = burn.snapshot()
    # Empty-handed, Jeff saves the food by lifting the pan, or by taking a clean plate to plate it from the pan.
    clean_plate = lambda a: ((state['stations'].get(a.target) or {}).get('food') or {}).get('stage') == 'clean_plate'
    saving = [a.key for a in burn.actions('jeff')
              if (a.kind == 'lift_pot' and a.target == stove) or work_item(a, state) in ('take_plate', f'plate:{food.ingredient}')
              or (a.kind == 'take_counter' and clean_plate(a))]
    fire = reach(on_fire)
    extinguish = [a.key for a in fire.actions('jeff') if a.kind == 'take_tool' and a.target == 'extinguisher'
                  or 'extinguish' in a.kind]
    return [('pan_about_to_burn', burn, saving), ('stove_on_fire', fire, extinguish)]


def nothing_left(limit=180.0):
    """Level 1 played by the reference policy for both chefs until every order is served and none is still to come.
    Level 1's orders come as Overcooked 2's do, without end, so this round keeps the plan's fixed times instead."""
    import reference_policy
    import config_contract as cc
    bundle = cc.level_bundle('level-1', embed=True)
    for key in ('keep_open', 'max_open', 'on_expire'):
        bundle['order_policy'].pop(key, None)
    k = SpatialKitchen(cc.freeze_bundle(bundle))
    step = 0
    while not k.ended and k.time < limit:
        if (all(o['status'] not in ('pending', 'future') for o in k.orders)
                and k.chefs['jeff'].job is None and k.chefs['jeff'].hand is None):
            return k
        if step % 10 == 0:
            for who, role in (('human', 'assembler'), ('jeff', 'cook')):
                action = reference_policy.choose(k, who, role)
                if action and k.chefs[who].job is None:
                    k.start(who, action)
        k.advance(.05)
        step += 1
    raise RuntimeError('the scripted round did not serve every order')


def previous_decision(at):
    """Jeff's previous decision as recent_decisions keeps it, agreeing with an idle, empty-handed Jeff: wait, accepted."""
    return {'t': round(at, 2), 'choice': 'wait', 'accepted': True, 'result': '等待', 'sprint_applied': False}


def stale_payload(client, k, mode='choice'):
    """The request while Jeff holds a plan for beef that no order needs any more (set 5 game seconds earlier)."""
    state = k.snapshot()
    held = Plan(mode=mode)
    at = max(0.0, k.time - 5)
    assert held.accept({'steps': list(STALE_PLAN)[:held.steps]}, at, work_items(state), None)
    recent = [previous_decision(at)] if mode == 'rolling' else []
    return compose_payload(client, k, deepcopy(state), k.actions('jeff'), recent, None, NO_MEMORY, held.input(state))


def arm_payload(client, k, arm, mode='choice'):
    """The request Jeff would send in this arm, from the same kitchen."""
    state, actions = k.snapshot(), k.actions('jeff')
    at = max(0.0, k.time - 3)
    # In rolling mode every arm has the same previous decision; only the held arm's carries the intent.
    recent = [previous_decision(at)] if mode == 'rolling' else []
    plan = None
    if arm != 'plan_off':
        held = Plan(mode=mode)
        if arm == 'plan_held':
            offered = work_items(state)
            steps = [s for s in UNRELATED if s in offered][:held.steps]
            assert held.accept({'steps': steps}, at, offered, None)
        plan = held.input(state)
    return compose_payload(client, k, deepcopy(state), actions, recent, None, NO_MEMORY, plan)


def summary(answers, urgent):
    ok = [a for a in answers if 'choice' in a]
    if not ok:
        return {'asked': len(answers), 'answered': 0}
    mass = [sum(v for key, v in (a.get('probabilities') or {}).items() if key in urgent) for a in ok if a.get('probabilities')]
    return {'asked': len(answers), 'answered': len(ok),
            'chose_emergency_action': round(sum(a['choice'] in urgent for a in ok) / len(ok), 3),
            'mean_probability_on_emergency_actions': round(mean(mass), 3) if mass else None,
            'chose_wait': round(sum(a['choice'] == 'wait' for a in ok) / len(ok), 3),
            'choices': dict(Counter(a['choice'] for a in ok).most_common())}


def run(client, repeats=3, ask=None, mode='choice'):
    """The report; ask(payload) answers one request (the model by default)."""
    ask = ask or client.ask
    steps = Plan(mode=mode).steps
    report = {'level': LEVEL, 'mode': mode, 'repeats': repeats, 'unrelated_plan': list(UNRELATED)[:steps], 'emergencies': {}}
    for name, k, urgent in emergencies():
        arms = {}
        for arm in ARMS:
            payload = arm_payload(client, k, arm, mode)
            answers = []
            for _ in range(repeats):
                try:
                    answers.append(ask(deepcopy(payload)))
                except RuntimeError as error:   # the client's own sanitized message, never the key
                    answers.append({'error': str(error)})
            arms[arm] = summary(answers, urgent)
        held, off = arms['plan_held'].get('chose_emergency_action'), arms['plan_off'].get('chose_emergency_action')
        report['emergencies'][name] = {'emergency_actions': urgent, 'game_time': round(k.time, 2), 'arms': arms,
                                       'plan_held_not_below_plan_off': None if held is None or off is None else held >= off}
    k = nothing_left()
    payload = stale_payload(client, k, mode)
    answers = []
    for _ in range(repeats):
        try:
            answers.append(ask(deepcopy(payload)))
        except RuntimeError as error:
            answers.append({'error': str(error)})
    if mode == 'rolling':
        stale = list(STALE_PLAN)[:steps]
        intents = [(a.get('plan') or {}).get('steps') or [] for a in answers if 'choice' in a]
        same = [i == stale or (i[:1] == stale[:1]) for i in intents]
        repeated = round(sum(same) / len(same), 3) if same else None
        report['stale_plan'] = {'level': 'level-1', 'game_time': round(k.time, 2), 'intent': stale,
                                'asked': len(answers), 'answered': len(intents), 'repeated_stale_intent': repeated,
                                'gave_no_intent': round(sum(not i for i in intents) / len(intents), 3) if intents else None,
                                'choices': dict(Counter(a['choice'] for a in answers if 'choice' in a).most_common()),
                                'left_it_in_most_answers': None if repeated is None else repeated <= .5}
        return report
    keeps = [(a.get('plan') or {}).get('keep') for a in answers if 'choice' in a]
    dropped = round(sum(v is False for v in keeps) / len(keeps), 3) if keeps else None
    report['stale_plan'] = {'level': 'level-1', 'game_time': round(k.time, 2), 'plan': list(STALE_PLAN),
                            'asked': len(answers), 'answered': len(keeps), 'chose_drop': dropped,
                            'chose_keep': round(sum(v is True for v in keeps) / len(keeps), 3) if keeps else None,
                            'choices': dict(Counter(a['choice'] for a in answers if 'choice' in a).most_common()),
                            'dropped_in_most_answers': None if dropped is None else dropped > .5}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--mode', choices=('choice', 'rolling'), default='choice', help='the plan mode to check')
    parser.add_argument('--repeats', type=int, default=3, help='requests per arm and emergency')
    parser.add_argument('--dry-run', action='store_true', help='build the requests and print their size only')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    config = level_config(load_config(), LEVEL)
    if args.dry_run:
        client = SpatialJevClient(config, key='dry-run-not-sent')
        sizes = [len(json.dumps(arm_payload(client, k, arm, args.mode), ensure_ascii=False))
                 for _, k, _ in emergencies() for arm in ARMS]
        sizes.append(len(json.dumps(stale_payload(client, nothing_left(), args.mode), ensure_ascii=False)))
        sends = len(sizes) * args.repeats
        tokens = sum(sizes) * args.repeats / 4
        print(f'{sends} requests, about {tokens / 1e6:.2f}M input tokens, about ${tokens / 1e6 * PRICE_PER_M:.2f}')
        return 0
    from scripts.jev_replay_check import client
    report = run(client(config), args.repeats, mode=args.mode)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
