#!/usr/bin/env python3
"""Does wording a one-press pan lift as the engine's own lift change how often Jev lifts a pan still cooking? Asks a model.

    python3 scripts/lift_label_check.py PATH [PATH ...] [--per-group 40] [--repeats 3] [--dry-run]
        [--connection PATH] [--out FILE]

From logged requests answered by Jev (journals or folders of them) this keeps those where Jeff held something and
next_action offered "put then take <stove>" while the food in that pan or pot was still cooking, and picks up to
--per-group of them where Jev chose that option and as many where it did not. Each is asked again in two arms,
next_action only:

- A: exactly as it was sent (one-press-v4: "... then take <its food> from Stove N");
- B: the same request with only that option's text as one-press-v5 writes it ("... then lift the frying pan from
  Stove N (stops heating off the stove; occupies your hands)") and one_press_version one-press-v5.

The outcomes are whether the answer lifted the cooking pan (chose that option), and whether it waited; the report
also counts the kinds of option chosen. Counts and shares only (no request, state or model text). --dry-run picks
and prints how many requests it would send. Run it in your own terminal: it asks through the game's saved connection
(--connection names the .player-api.json to use, for a worktree that has none).
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import one_press  # noqa: E402
from scripts import reask  # noqa: E402
from scripts import reach_note_check as clients  # noqa: E402
from scripts.jev_replay_check import estimate  # noqa: E402


def patient(ask, tries=3, waits=(5, 15), sleep=None):
    """ask, tried again after a refusal or a failed connection (the client's RuntimeError), at most tries times: a slow
    stretch of the service should not leave one arm with no answers."""
    import time
    sleep = sleep or time.sleep

    def again(payload):
        for n in range(tries):
            try:
                return ask(payload)
            except RuntimeError:
                if n == tries - 1:
                    raise
                sleep(waits[min(n, len(waits) - 1)])
    return again


ARMS = ('A', 'B')
LIFT = ' then lift the {vessel} from {station} (stops heating off the stove; occupies your hands)'


def journals(paths):
    out = []
    for p in paths:
        p = Path(p)
        out += sorted(p.glob('**/*.jsonl')) if p.is_dir() else [p]
    return out


def new_text(old, vessel, station):
    """The v5 text of a v4 "put then take <stove>" option: its own put half, then the engine's lift."""
    head = old.split(' then take ', 1)[0]
    return head + LIFT.format(vessel=vessel, station=station)


def moments(paths):
    found, counts, seen = [], Counter(), set()
    for path in journals(paths):
        try:
            rows = [json.loads(line) for line in open(path, encoding='utf-8')]
        except (OSError, ValueError):
            continue
        answers = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_response'}
        for row in rows:
            payload = row.get('payload')
            if row.get('kind') != 'ai_request' or not isinstance(payload, dict):
                continue
            answer = answers.get(row.get('request_id'))
            if not answer or not str(answer.get('model') or '').startswith('jev') or not answer.get('choice'):
                continue
            k = payload['state']['kitchen']
            criteria = payload['questions']['next_action']['criteria']
            for key, text in criteria.items():
                sid = key.split()[-1]
                station = k['stations'].get(sid) or {}
                food = station.get('food') or {}
                if not (key.startswith(one_press.PUT_THEN_TAKE) and station.get('stove') and food.get('stage') == 'cooking'
                        and ' then take ' in text):
                    continue
                mark = (str(path), row.get('request_id'))
                if mark in seen:
                    continue
                seen.add(mark)
                vessel = (k.get('vessels') or {}).get(station.get('vessel'), {}).get('name') or 'pot'
                b = deepcopy(payload)
                b['questions']['next_action']['criteria'][key] = new_text(text, vessel, station['name'])
                b['state']['one_press_version'] = one_press.VERSION
                lifted = answer['choice'] == key
                counts['lifted' if lifted else 'other'] += 1
                found.append({'payload': payload, 'B': b, 'lift': key, 'logged_lifted': lifted,
                              'logged_choice': answer['choice'], 'ready_in': station.get('ready_in')})
                break
    return found, dict(counts)


def pick(found, per_group, seed):
    rng = random.Random(seed)
    lifted = [m for m in found if m['logged_lifted']]
    other = [m for m in found if not m['logged_lifted']]
    return rng.sample(lifted, min(per_group, len(lifted))) + rng.sample(other, min(per_group, len(other)))


def arm(item, name):
    return item['payload'] if name == 'A' else item['B']


OUTCOMES = {
    'lifted_the_cooking_pan': lambda i, p, a: a['choice'] == i['lift'],
    'waited': lambda i, p, a: a['choice'] == 'wait',
    'same_as_logged': lambda i, p, a: a['choice'] == i['logged_choice'],
}


def kind(item, choice):
    if choice == item['lift']:
        return 'lift_cooking_pan'
    for prefix, name in (('wait', 'wait'), ('continue', 'continue'), ('put then', 'other_put_then'), ('plate', 'plate'),
                         ('assemble', 'add_to_held_plate'), ('merge', 'merge_plates'), ('put', 'put'), ('drop', 'put'),
                         ('throw', 'throw'), ('chop', 'chop'), ('take', 'take'), ('fetch', 'fetch'), ('go', 'walk'),
                         ('serve', 'serve')):
        if choice.startswith(prefix):
            return name
    return 'other'


def run(items, ask, repeats, progress=None):
    asked = {'arms': {name: [] for name in ARMS}, 'models': Counter()}
    for n, item in enumerate(items, 1):
        one = reask.ask_arms([item], ARMS, arm, ask, clients.ask_once, repeats)
        for name in ARMS:
            asked['arms'][name] += one['arms'][name]
        asked['models'].update(one['models'])
        if progress and (n % 10 == 0 or n == len(items)):
            failed = sum('error' in a for rows in asked['arms'].values() for _, _, rs in rows for a in rs)
            progress(f'{n}/{len(items)} moments asked, {failed} failed requests so far')
    asked['models'] = dict(asked['models'].most_common())
    out = {'moments': len(items), 'repeats': repeats, 'questions_asked': ['next_action'], 'groups': {}}
    for group, keep in (('all', lambda i: True), ('logged_lifted', lambda i: i['logged_lifted']),
                        ('logged_other', lambda i: not i['logged_lifted'])):
        part = {'arms': {name: [r for r in rows if keep(r[0])] for name, rows in asked['arms'].items()}, 'models': asked['models']}
        chosen = {name: dict(Counter(kind(i, a['choice']) for i, _, rs in rows for a in rs if 'choice' in a).most_common())
                  for name, rows in part['arms'].items()}
        errors = {name: dict(Counter(a['error'][:160] for _, _, rs in rows for a in rs if 'error' in a)) for name, rows in part['arms'].items()}
        out['groups'][group] = {'moments': len(part['arms']['A']), 'chosen': chosen, 'errors': errors,
                                'stats': reask.stats(part, OUTCOMES)}
    out['models'] = asked['models']
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--per-group', type=int, default=40)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--connection', help="the game's saved connection to use (.player-api.json; never printed)")
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    found, counts = moments(args.paths)
    items = pick(found, args.per_group, args.seed)
    print(f'found {counts}; asking {Counter("lifted" if i["logged_lifted"] else "other" for i in items)}', file=sys.stderr)
    print(estimate([{'payload': i['B']} for i in items], len(ARMS) * args.repeats), file=sys.stderr)
    if args.dry_run or not items:
        return 0
    from scripts import jev_replay_check
    if args.connection:
        jev_replay_check.CONNECTION = Path(args.connection).expanduser().resolve()
    client = jev_replay_check.client()
    client.timeout = args.timeout
    report = run(items, patient(client.ask), args.repeats, lambda text: print(text, file=sys.stderr, flush=True))
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
