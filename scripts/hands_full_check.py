#!/usr/bin/env python3
"""Why does Jeff walk back and forth with full hands? Real stuck moments, three ways. Run locally; it sends to Jev.

    python3 scripts/hands_full_check.py logs/ --since 2026-11-04 [--sample 20] [--dry-run]

From local round journals it picks requests of Jev rounds where Jeff's hands were full and the logged
answer was a walk or wait: the moments he got stuck. Each is sent to the current Jev in three arms:

- as_logged: exactly as it was sent;
- no_recent: the same with recent_decisions and recent_events emptied, to see whether his own recent
  walks keep him walking;
- no_supply_walks: the same with the walks to ingredient supplies (go fridge, go lettuce, ...) left out
  of the options, the menu change that would stop him walking to a supply he cannot take from.

For each arm it reports how often the answer was the logged one, a walk to a supply, another walk, wait,
or an action that uses or puts down what he holds (put, drop, throw, assemble, plate, ...). The report holds
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
from scripts.jev_replay_check import (ask_once, client, estimate, hands_full, journal_requests, kind, pick,  # noqa: E402
                                      share, supplies)

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


def run(items, ask):
    arms = {}
    for name in ARMS:
        answers = []
        for item in items:
            payload = arm(item['payload'], name)
            answers.append((item, payload, ask_once(ask, payload)))
        ok = [(i, p, a) for i, p, a in answers if 'choice' in a]
        kinds = Counter(kind(a['choice'], p) for _, p, a in ok)
        arms[name] = {'asked': len(answers), 'answered': len(ok),
                      'same_as_logged': share(sum(a['choice'] == i['logged_choice'] for i, _, a in ok), len(ok)),
                      **{f'chose_{k}': share(kinds[k], len(ok)) for k in ('supply_walk', 'walk', 'wait', 'use_or_put_down')},
                      'kinds': dict(kinds.most_common()),
                      'errors': dict(Counter(a['error'] for _, _, a in answers if 'error' in a).most_common())}
    logged = Counter(kind(i['logged_choice'], i['payload']) for i in items)
    return {'moments': len(items), 'rounds': len({i['round'] for i in items}),
            'logged_kinds': dict(logged.most_common()),
            'with_supply_walks_offered': sum(any(k.startswith('go ') and k[3:] in supplies(i['payload'])
                                                 for k in i['payload']['questions']['next_action']['criteria']) for i in items),
            'arms': arms}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+', help='local round journals (logs/) or files')
    parser.add_argument('--since', help='first day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--until', help='last day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--sample', type=int, default=20, help='stuck moments to pick')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--dry-run', action='store_true', help='pick the moments and print their number and size only')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    items = pick([i for i in journal_requests(args.paths, args.since, args.until) if stuck(i)], args.sample, args.seed)
    if not items:
        print('no stuck moments with full hands in Jev rounds of those journals and days')
        return 1
    print(estimate(items, len(ARMS)), file=sys.stderr)
    if args.dry_run:
        return 0
    text = json.dumps(run(items, client().ask), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
