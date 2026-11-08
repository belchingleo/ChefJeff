#!/usr/bin/env python3
"""Why does Jeff walk back and forth with full hands? Real stuck moments, three ways. Run locally; it sends to the game's model.

    python3 scripts/hands_full_check.py logs/ --since 2026-11-04 [--sample 20] [--one-press on|off] [--dry-run | --groups-only]

From local round journals it picks requests of Jev rounds where Jeff's hands were full and the logged
answer was a walk or wait: the moments he got stuck. Each is sent to the current Jev in three arms:

- as_logged: exactly as it was sent;
- no_recent: the same with recent_decisions and recent_events emptied, to see whether his own recent
  walks keep him walking;
- no_supply_walks: the same with the walks to ingredient supplies (go fridge, go lettuce, ...) left out
  of the options, the menu change that would stop him walking to a supply he cannot take from.

For each arm it reports how often the answer was the logged one, a walk to a supply, another walk, wait,
an action that uses or puts down what he holds (put, drop, throw, assemble, plate, ...), and of those the
ones that are a step of the dish (plate, assemble, load, a pan, the sink, a board for an ingredient still to
chop) rather than parking it (a counter, a supply top, the floor, a throw, the bin).

The moments themselves are grouped, from the logged request alone, so a wait that had something to wait
for can be told from one that was stuck: what he held (plate, ingredient, dirty plate, pan or pot,
extinguisher), whether a step of the dish was among his options, whether only parking was, and whether
food was heating on a stove. `waits` crosses the logged waits with those, and `walks` gives the kinds of
station the logged walks went to (board, counter, stove, ...; partner for go partner), what was on that
station (empty, plate, ingredient, dirty plate, pan or pot, ...) and, as held -> on station, both
together: a walk with full hands to a station holding something is a walk to an item he cannot take. With --groups-only the report
also gives, for every request with full hands (stuck or not), the logged answer kinds and options offered.

The report holds counts and shares only (no request, state or model text). It reads the journals and
changes nothing; the key is read the way the game reads it and is never printed. --dry-run picks the moments and prints their
number and size; --groups-only groups every such moment (no sample) and sends nothing, so it costs nothing.
--one-press on (or off) keeps only rounds with a one-press switch on (or both off), so the two can be
grouped apart; by default every round is used.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.jev_replay_check import (ask_once, client, estimate, hands_full, jeff, journal_requests, kind,  # noqa: E402
                                      moves_forward, pick, share, stations, supplies)
from scripts import reask  # noqa: E402

ARMS = ('as_logged', 'no_recent', 'no_supply_walks')
STUCK = ('supply_walk', 'walk', 'wait')


def stuck(item):
    return hands_full(item['payload']) and kind(item['logged_choice'], item['payload']) in STUCK


def arm(payload, name):
    """The request for one arm; the options and kitchen are untouched except as the arm says."""
    payload = deepcopy(payload)
    if name == 'no_recent':
        payload['state']['recent_decisions'] = []
        payload['state']['recent_events'] = []
    elif name == 'no_supply_walks':
        criteria = payload['questions']['next_action']['criteria']
        payload['questions']['next_action']['criteria'] = {
            key: label for key, label in criteria.items() if not (key.startswith('go ') and key[3:] in supplies(payload))}
    return payload


def food_kind(food):
    """A food or item as a kind: plate (clean or with food), dirty_plate, ingredient, pan_or_pot, extinguisher, empty."""
    if not food:
        return 'empty'
    stage = food.get('stage')
    if stage == 'clean_plate' or food.get('plate_id'):
        return 'plate'
    if stage in ('dirty_plate', 'extinguisher'):
        return stage
    if stage == 'pot':
        return 'pan_or_pot'
    return 'ingredient' if stage in ('raw', 'chopped') else 'other'


def on_station(key, payload):
    """What lies on the station a walk goes to, as a kind; partner for go partner."""
    target = key[3:]
    if target == 'partner':
        return 'partner'
    station = stations(payload).get(target)
    if station is None:
        return 'other'
    if station.get('pot_id'):      # a stove: its pan or pot, and what is in it
        return 'empty_pan' if not station.get('food') else 'pan_with_food'
    return food_kind(station.get('food'))


def held(payload):
    """What Jeff holds, as a kind: plate (clean or with food), dirty_plate, ingredient, pan_or_pot, extinguisher."""
    food = jeff(payload).get('holding') or {}
    stage = food.get('stage')
    if stage == 'clean_plate' or food.get('plate_id'):
        return 'plate'
    if stage in ('dirty_plate', 'extinguisher'):
        return stage
    if stage == 'pot':
        return 'pan_or_pot'
    return 'ingredient' if stage in ('raw', 'chopped') else 'other'


def offered(payload):
    """forward: a step of the dish was offered; parking: only ways to put it aside; none: neither."""
    criteria = payload['questions']['next_action']['criteria']
    if any(moves_forward(k, payload) for k in criteria):
        return 'forward'
    return 'parking' if any(kind(k, payload) == 'use_or_put_down' for k in criteria) else 'none'


def cooking(payload):
    """Food heating on a stove: something a wait can be for."""
    return any(s.get('stove') and s.get('heating') and s.get('food') for s in stations(payload).values())


def walk_target(key, payload):
    """The kind of station a walk goes to: its station type, partner, or other."""
    target = key[3:]
    if target == 'partner':
        return 'partner'
    return (stations(payload).get(target) or {}).get('type') or 'other'


def groups(items):
    waits = [i for i in items if kind(i['logged_choice'], i['payload']) == 'wait']
    walks = [i for i in items if kind(i['logged_choice'], i['payload']) in ('walk', 'supply_walk')]
    return {'held': dict(Counter(held(i['payload']) for i in items).most_common()),
            'options': dict(Counter(offered(i['payload']) for i in items).most_common()),
            'food_heating': sum(cooking(i['payload']) for i in items),
            'waits': {'count': len(waits),
                      'with_a_forward_option': sum(offered(i['payload']) == 'forward' for i in waits),
                      'with_only_parking': sum(offered(i['payload']) == 'parking' for i in waits),
                      'while_food_heating': sum(cooking(i['payload']) for i in waits),
                      'holding_a_plate_while_food_heating': sum(held(i['payload']) == 'plate' and cooking(i['payload']) for i in waits),
                      'by_held': dict(Counter(held(i['payload']) for i in waits).most_common())},
            'walks': {'count': len(walks),
                      'to': dict(Counter(walk_target(i['logged_choice'], i['payload']) for i in walks).most_common()),
                      'by_held': dict(Counter(held(i['payload']) for i in walks).most_common()),
                      'on_station': dict(Counter(on_station(i['logged_choice'], i['payload']) for i in walks).most_common()),
                      'held_and_on_station': dict(Counter(f"{held(i['payload'])} -> {on_station(i['logged_choice'], i['payload'])}"
                                                          for i in walks).most_common(10))}}


# Outcomes with intervals and paired differences (reask.stats); the shares below stay as they were.
OUTCOMES = {
    'same_as_logged': lambda i, p, a: a['choice'] == i['logged_choice'],
    'chose_supply_walk': lambda i, p, a: kind(a['choice'], p) == 'supply_walk',
    'chose_walk': lambda i, p, a: kind(a['choice'], p) == 'walk',
    'chose_wait': lambda i, p, a: kind(a['choice'], p) == 'wait',
    'chose_a_step_of_the_dish': lambda i, p, a: moves_forward(a['choice'], p),
}


def run(items, ask):
    asked = reask.ask_arms(items, ARMS, lambda item, name: arm(item['payload'], name), ask, ask_once)
    arms = {}
    for name, rows in asked['arms'].items():
        answers = [(item, payload, replies[0]) for item, payload, replies in rows]
        ok = [(i, p, a) for i, p, a in answers if 'choice' in a]
        kinds = Counter(kind(a['choice'], p) for _, p, a in ok)
        arms[name] = {'asked': len(answers), 'answered': len(ok),
                      'same_as_logged': share(sum(a['choice'] == i['logged_choice'] for i, _, a in ok), len(ok)),
                      **{f'chose_{k}': share(kinds[k], len(ok)) for k in ('supply_walk', 'walk', 'wait', 'use_or_put_down')},
                      'chose_a_step_of_the_dish': share(sum(moves_forward(a['choice'], p) for _, p, a in ok), len(ok)),
                      'kinds': dict(kinds.most_common()),
                      'errors': dict(Counter(a['error'] for _, _, a in answers if 'error' in a).most_common())}
    logged = Counter(kind(i['logged_choice'], i['payload']) for i in items)
    return {'moments': len(items), 'rounds': len({i['round'] for i in items}),
            'logged_kinds': dict(logged.most_common()),
            'with_supply_walks_offered': sum(any(k.startswith('go ') and k[3:] in supplies(i['payload'])
                                                 for k in i['payload']['questions']['next_action']['criteria']) for i in items),
            'groups': groups(items), 'arms': arms, 'stats': reask.stats(asked, OUTCOMES)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+', help='local round journals (logs/) or files')
    parser.add_argument('--since', help='first day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--until', help='last day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--sample', type=int, default=20, help='stuck moments to pick')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--dry-run', action='store_true', help='pick the moments and print their number and size only')
    parser.add_argument('--groups-only', action='store_true', help='group every stuck moment from the journals and send nothing')
    parser.add_argument('--one-press', choices=('on', 'off'), help='only rounds with a one-press switch on, or with both off')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    found = journal_requests(args.paths, args.since, args.until)
    if args.one_press:
        found = [i for i in found if i['one_press'] == (args.one_press == 'on')]
    items = [i for i in found if stuck(i)]
    if not args.groups_only:     # grouping sends nothing, so it uses every moment
        items = pick(items, args.sample, args.seed)
    if not items:
        print('no stuck moments with full hands in Jev rounds of those journals and days')
        return 1
    if args.groups_only:
        full = [i for i in found if hands_full(i['payload'])]
        report = {'moments': len(items), 'rounds': len({i['round'] for i in items}), 'groups': groups(items),
                  'all_hands_full': {'requests': len(full), 'rounds': len({i['round'] for i in full}),
                                     'logged_kinds': dict(Counter(kind(i['logged_choice'], i['payload']) for i in full).most_common()),
                                     'logged_a_step_of_the_dish': sum(moves_forward(i['logged_choice'], i['payload']) for i in full),
                                     'options': dict(Counter(offered(i['payload']) for i in full).most_common())}}
    else:
        print(estimate(items, len(ARMS)), file=sys.stderr)
        if args.dry_run:
            return 0
        report = run(items, client().ask)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
