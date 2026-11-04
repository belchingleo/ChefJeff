#!/usr/bin/env python3
"""Does Jeff walk less when each walk says there is nothing listed to do there? Run locally; it sends to Jev.

    python3 scripts/walk_label_check.py logs/ --since 2026-11-04 [--sample 20] [--arms as_logged,walks_labeled] [--dry-run]

Each "go X" Jeff is offered is, by construction (harness.model_candidates), a walk to a station where
none of his other listed actions is: an action at X would already walk there, and "go X" is then left
out. The option does not say so. From local round journals this picks requests of Jev rounds whose
logged answer was such a walk (not go partner) and sends each to the current Jev in two arms:

- as_logged: exactly as it was sent;
- walks_labeled: the same, with that fact added to the label of every such walk ("; no other listed
  action is at <station> now"). Only the labels change, and only for walks where no other offered key
  names that station;
- walks_explained: the same, with every such walk's label stating what lies there and that, with what
  he holds, none of his listed actions is there ("; Board 1 holds Lettuce (raw); with what you hold, no
  other listed action is at b1 now"). Like walks_labeled it changes only labels, and only facts the
  request already holds;
- put_then_take: the same, with one more option next to every walk with full hands to a station that
  holds an item: "put then take <station>", labelled "Put the held <item> on <the first counter a put is
  offered for> (or down where you stand), then take <what lies there> from <station>". It is two legal
  steps the player can take with two presses; the check only asks whether Jeff picks it over the walk,
  and the game does not offer it;
- no_aimed_throws: the same with the eight aimed throws (throw up, throw down-left, ...) left out of
  the options and throw partner kept, so the request has fewer options. It tells whether the number of
  options changes his walks; it also takes the throws away, so read it with that in mind.

--arms picks the arms to send (default as_logged,walks_labeled); each arm sends every moment once.

For each arm it reports, split by whether Jeff's hands were full, how often the answer was the logged
one, a walk, wait, an action that uses or puts down what he holds and of those a step of the dish
(scripts/jev_replay_check.kind and moves_forward), and a take with empty hands. The report holds
counts and shares only (no request, state or model text). It reads the journals and changes nothing; the
key is read the way the game reads it and is never printed. --dry-run picks the moments and prints their
number and size.
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
from scripts.jev_replay_check import (ask_once, client, estimate, hands_full, journal_requests, kind,  # noqa: E402
                                      moves_forward, pick, share)

ARMS = ('as_logged', 'walks_labeled', 'walks_explained', 'put_then_take', 'no_aimed_throws')
PUT_THEN_TAKE = 'put then take '
DEFAULT_ARMS = ('as_logged', 'walks_labeled')
KINDS = ('walk', 'wait', 'use_or_put_down', 'take')


def walk(key):
    """Whether a key is a walk to a station (go X, not go partner)."""
    return key.startswith('go ') and key != 'go partner'


def nothing_else_there(key, criteria):
    """No other offered key, throws aside, names the station a walk goes to."""
    target = key[3:]
    return not any(target in other.split(' ') for other in criteria if other != key and not other.startswith('throw '))


def label(payload):
    """The request with the fact added to every walk it holds for that walk's station."""
    payload = deepcopy(payload)
    criteria = payload['questions']['next_action']['criteria']
    for key in list(criteria):
        if walk(key) and nothing_else_there(key, criteria):
            criteria[key] = f'{criteria[key]}; no other listed action is at {key[3:]} now'
    return payload


def lying_there(station):
    """What lies on a station, in the request's own words: an ingredient with its stage, else its meaning."""
    food = (station or {}).get('food')
    if not food:
        return None
    meaning = food.get('meaning') or food.get('ingredient') or 'an item'
    return f"{meaning} ({food['stage']})" if food.get('stage') in ('raw', 'chopped') else meaning


def explain(payload):
    """The request with every walk to a station stating what lies there and that nothing else listed is there."""
    payload = deepcopy(payload)
    criteria = payload['questions']['next_action']['criteria']
    stations = ((payload.get('state') or {}).get('kitchen') or {}).get('stations') or {}
    for key in list(criteria):
        if walk(key) and nothing_else_there(key, criteria):
            station = stations.get(key[3:]) or {}
            there = lying_there(station)
            held = f"{station.get('name', key[3:])} holds {there}; " if there else ''
            criteria[key] = f'{criteria[key]}; {held}with what you hold, no other listed action is at {key[3:]} now'
    return payload


def held_item(payload):
    food = (((payload.get('state') or {}).get('kitchen') or {}).get('chefs', {}).get('jeff') or {}).get('holding')
    return lying_there({'food': food}) if food else None


def with_put_then_take(payload):
    """The request with a put-then-take option next to every walk with full hands to a station holding an item."""
    payload = deepcopy(payload)
    criteria = payload['questions']['next_action']['criteria']
    stations = ((payload.get('state') or {}).get('kitchen') or {}).get('stations') or {}
    held = held_item(payload)
    if held is None:
        return payload
    spot = next((stations[k[4:]].get('name', k[4:]) for k in criteria
                 if k.startswith('put ') and (stations.get(k[4:]) or {}).get('counter')), None)
    where = f'on {spot}' if spot else ('down where you stand' if 'drop' in criteria else None)
    if where is None:
        return payload
    out = {}
    for key, text in criteria.items():
        out[key] = text
        station = stations.get(key[3:]) or {}
        there = lying_there(station)
        if walk(key) and nothing_else_there(key, criteria) and there:
            out[PUT_THEN_TAKE + key[3:]] = f"Put the held {held} {where}, then take {there} from {station.get('name', key[3:])}"
    payload['questions']['next_action']['criteria'] = out
    return payload


def without_aimed_throws(payload):
    """The request without the aimed throws; throw partner and every other option stay as they were."""
    payload = deepcopy(payload)
    criteria = payload['questions']['next_action']['criteria']
    payload['questions']['next_action']['criteria'] = {k: v for k, v in criteria.items()
                                                       if not (k.startswith('throw ') and k != 'throw partner')}
    return payload


def arm(payload, name):
    if name == 'walks_labeled':
        return label(payload)
    if name == 'walks_explained':
        return explain(payload)
    if name == 'put_then_take':
        return with_put_then_take(payload)
    if name == 'no_aimed_throws':
        return without_aimed_throws(payload)
    return payload


def picked(item):
    return walk(item['logged_choice'])


def arm_report(answers):
    ok = [(i, p, a) for i, p, a in answers if 'choice' in a]
    kinds = Counter(('walk' if k == 'supply_walk' else k) for k in (kind(a['choice'], p) for _, p, a in ok))
    return {'asked': len(answers), 'answered': len(ok),
            'same_as_logged': share(sum(a['choice'] == i['logged_choice'] for i, _, a in ok), len(ok)),
            **{f'chose_{k}': share(kinds[k], len(ok)) for k in KINDS},
            'chose_a_step_of_the_dish': share(sum(moves_forward(a['choice'], p) for _, p, a in ok), len(ok)),
            'chose_put_then_take': share(sum(a['choice'].startswith(PUT_THEN_TAKE) for _, _, a in ok), len(ok)),
            'offered_put_then_take': sum(any(k.startswith(PUT_THEN_TAKE) for k in p['questions']['next_action']['criteria'])
                                         for _, p, _ in answers),
            'mean_options': round(sum(len(p['questions']['next_action']['criteria']) for _, p, _ in answers) / len(answers), 2)
            if answers else None,
            'kinds': dict(kinds.most_common()),
            'errors': dict(Counter(a['error'] for _, _, a in answers if 'error' in a).most_common())}


def run(items, ask, arms_asked=DEFAULT_ARMS):
    arms = {}
    for name in arms_asked:
        answers = []
        for item in items:
            payload = arm(item['payload'], name)
            answers.append((item, payload, ask_once(ask, payload)))
        full = [x for x in answers if hands_full(x[0]['payload'])]
        empty = [x for x in answers if not hands_full(x[0]['payload'])]
        arms[name] = {'all': arm_report(answers), 'hands_full': arm_report(full), 'hands_empty': arm_report(empty)}
    labeled = [sum(walk(k) and nothing_else_there(k, i['payload']['questions']['next_action']['criteria'])
                   for k in i['payload']['questions']['next_action']['criteria']) for i in items]
    return {'moments': len(items), 'rounds': len({i['round'] for i in items}),
            'hands_full': sum(hands_full(i['payload']) for i in items),
            'walks_labeled_per_request': round(sum(labeled) / len(labeled), 2) if labeled else None,
            'arms': arms}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+', help='local round journals (logs/) or files')
    parser.add_argument('--since', help='first day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--until', help='last day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--sample', type=int, default=20, help='walk moments to pick')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--arms', default=','.join(DEFAULT_ARMS), help='comma-separated arms to send: ' + ', '.join(ARMS))
    parser.add_argument('--dry-run', action='store_true', help='pick the moments and print their number and size only')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    arms_asked = tuple(a for a in args.arms.split(',') if a)
    if not arms_asked or set(arms_asked) - set(ARMS):
        parser.error('--arms takes ' + ', '.join(ARMS))
    items = pick([i for i in journal_requests(args.paths, args.since, args.until) if picked(i)], args.sample, args.seed)
    if not items:
        print('no walks to a station in Jev rounds of those journals and days')
        return 1
    print(estimate(items, len(arms_asked)), file=sys.stderr)
    if args.dry_run:
        return 0
    text = json.dumps(run(items, client().ask, arms_asked), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
