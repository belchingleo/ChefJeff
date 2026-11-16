#!/usr/bin/env python3
"""Does the links table against waiting (option-links-v4) change what Jeff chooses? Run locally; it asks a model.

    python3 scripts/links_v4_check.py DIR [DIR ...] [--control 30] [--repeats 3] [--moments FILE] [--dry-run]
        [--connection PATH | --perplexity MODEL] [--out FILE]

From round journals and their session bundles (folders of a links trial) this replays each round and keeps the
requests whose logged table (option-links v2/v3) comes out the same when computed again, so the kitchen is the one
the request described. Each is asked again in two arms, next_action only:

- A: exactly as it was sent;
- B: the same request with the v4 table (links.apply with v4: a row for wait, rows without what waiting opens,
  option_links_shared, V4_RULE and links_version option-links-v4).

Moments are every request whose v4 table differs, in four kinds (the first that applies):

- pan_soon: waiting alone opens plating from a pan (food about to finish cooking);
- wait_other: waiting alone opens other work (the other chef finishing a step);
- moved: some work left an option's row and went nowhere else (rare);
- shared_only: only the shared row changed;

and --control requests whose table is the same in both arms (only the rule text and version differ).

The outcomes are whether the answer was wait; for pan_soon, whether it put the held item down to take the pan or pot
(the options "put then take ... from Stove"); whether it chose an option that lost a line in B; whether it chose one
of the options in B's shared row; and whether it agreed with the logged answer. Reports hold counts and shares only
(no request, state or model text). --dry-run replays and picks the moments and prints how many requests it would send.
Each moment is asked in both arms before the next, a failed request is tried again twice, and progress goes to stderr.
The clients: the connection saved in the game (--connection names the .player-api.json to use, for a worktree that
has none; run that in your own terminal) or --perplexity MODEL with the key in ~/.config/chefjeff/perplexity.key.
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
import links  # noqa: E402
from scripts.decision_stats import read_rounds  # noqa: E402
from scripts.jev_replay_check import estimate, journals  # noqa: E402
from scripts.food_names_check import bundle_for  # noqa: E402
from scripts.links_check import listed  # noqa: E402
from scripts import reask  # noqa: E402
from scripts import reach_note_check as clients  # noqa: E402

ARMS = ('A', 'B')
KINDS = ('pan_soon', 'wait_other', 'moved', 'shared_only', 'control')


def _kind(v3, v4, shared):
    wait = v4.get('wait') or []
    if any(line.startswith('Plate food from Stove') for line in wait):
        return 'pan_soon'
    if wait:
        return 'wait_other'
    shared_work = set(shared['work']) if shared else set()
    if any(x not in v4.get(key, []) and not (shared and key in shared['options'] and x in shared_work)
           for key, lines in v3.items() for x in lines):
        return 'moved'
    return 'shared_only' if shared else None


def moments(paths):
    """(changed, unchanged, counts): every rebuilt request whose v4 table differs (with its kind), and the others."""
    from session_record import read_bundle
    from kitchen import apply_input
    from research_replay import factory
    changed, unchanged, counts = [], [], Counter()
    for path in journals(paths):
        for rows in read_rounds(path)[0]:
            bundle = bundle_for(path)
            if bundle is None:
                counts['rounds_without_bundle'] += 1
                continue
            counts['rounds'] += 1
            data = read_bundle(bundle)
            k = factory(data['session']['runtime_versions']['engine'])(deepcopy(data['resolved']))
            inputs, n = data['inputs'], 0
            names = bool((((rows[0] if rows else {}).get('features') or {}).get('food_names') or {}).get('on'))
            answers = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_response'}
            for row in rows:
                payload = row.get('payload')
                if row.get('kind') != 'ai_request' or not isinstance(payload, dict) or row.get('ask_ahead'):
                    continue
                logged = payload['state'].get('option_links')
                answer = answers.get(row.get('request_id'))
                if logged is None or answer is None or not answer.get('choice'):
                    continue
                at = row['game_time_ms']
                while n < len(inputs) and inputs[n]['game_time_ms'] < at:
                    apply_input(k, inputs[n])
                    n += 1
                keys = list(payload['questions']['next_action']['criteria'])
                v3 = links.table(k, 'jeff', listed(k, row), keys, names)
                while v3 != logged and n < len(inputs) and inputs[n]['game_time_ms'] == at:
                    apply_input(k, inputs[n])
                    n += 1
                    v3 = links.table(k, 'jeff', listed(k, row), keys, names)
                if v3 != logged:
                    counts['not_rebuilt'] += 1
                    continue
                b = links.apply(deepcopy(payload), k, 'jeff', listed(k, row), names, v4=True)
                v4, shared = b['state']['option_links'], b['state'].get('option_links_shared')
                criteria = payload['questions']['next_action']['criteria']
                item = {'payload': payload, 'B': b, 'logged_choice': answer['choice'], 't': round(at / 1000, 2),
                        'abandon': sorted(key for key, text in criteria.items()
                                          if key.startswith('put then take') and 'from Stove' in text),
                        'moved_from': sorted(key for key, lines in v3.items()
                                             if any(x not in v4.get(key, []) and not (shared and key in shared['options']
                                                                                      and x in shared['work'])
                                                    for x in lines)),
                        'shared': (shared or {}).get('options', [])}
                kind = _kind(v3, v4, shared)
                if kind is None:
                    unchanged.append({**item, 'kind': 'control'})
                else:
                    changed.append({**item, 'kind': kind})
                counts[kind or 'unchanged'] += 1
    return changed, unchanged, dict(counts)


def arm(item, name):
    return item['payload'] if name == 'A' else item['B']


OUTCOMES = {
    'waited': lambda i, p, a: a['choice'] == 'wait',
    'put_item_down_for_pan': lambda i, p, a: a['choice'] in i['abandon'] if i['kind'] == 'pan_soon' and i['abandon'] else None,
    'chose_option_that_lost_a_line': lambda i, p, a: a['choice'] in i['moved_from'] if i['moved_from'] else None,
    'chose_a_shared_row_option': lambda i, p, a: a['choice'] in i['shared'] if i['shared'] else None,
    'same_as_logged': lambda i, p, a: a['choice'] == i['logged_choice'],
}


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


def run(items, ask, repeats, progress=None):
    """Each moment in both arms before the next (so a slow stretch of the service falls on both arms alike)."""
    out = {'moments': len(items), 'repeats': repeats, 'questions_asked': ['next_action'], 'by_kind': {}}
    asked = {'arms': {name: [] for name in ARMS}, 'models': Counter()}
    for n, item in enumerate(items, 1):
        one = reask.ask_arms([item], ARMS, arm, ask, clients.ask_once, repeats)
        for name in ARMS:
            asked['arms'][name] += one['arms'][name]
        asked['models'].update(one['models'])
        if progress and (n % 10 == 0 or n == len(items)):
            errors = sum('error' in a for rows in asked['arms'].values() for _, _, rs in rows for a in rs)
            progress(f'{n}/{len(items)} moments asked, {errors} failed requests so far')
    asked['models'] = dict(asked['models'].most_common())
    for kind in KINDS:
        part = {'arms': {name: [r for r in rows if r[0]['kind'] == kind] for name, rows in asked['arms'].items()},
                'models': asked['models']}
        if not part['arms']['A']:
            continue
        errors = {name: dict(Counter(a['error'][:160] for _, _, rs in rows for a in rs if 'error' in a)) for name, rows in part['arms'].items()}
        out['by_kind'][kind] = {'moments': len(part['arms']['A']), 'errors': errors, 'stats': reask.stats(part, OUTCOMES)}
    out['models'] = asked['models']
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--control', type=int, default=30, help='unchanged-table requests to ask as well')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--moments', help='a file of replayed moments: read it if it exists, else write it after replaying')
    parser.add_argument('--connection', help="the game's saved connection to use (.player-api.json; never printed)")
    parser.add_argument('--perplexity', metavar='MODEL', help='a Perplexity decision model (e.g. pplx-decider-v1.2)')
    parser.add_argument('--timeout', type=float, default=60, help='seconds one answer may take (saved connection)')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    if args.moments and Path(args.moments).exists():
        changed, unchanged, counts = json.loads(Path(args.moments).read_text())
    else:
        changed, unchanged, counts = moments(args.paths)
        if args.moments:
            Path(args.moments).write_text(json.dumps([changed, unchanged, counts], ensure_ascii=False))
    control = random.Random(args.seed).sample(unchanged, min(args.control, len(unchanged)))
    items = changed + control
    print(f'replayed: {counts}; asking {Counter(i["kind"] for i in items)}', file=sys.stderr)
    print(estimate([{'payload': arm(i, 'B')} for i in items], len(ARMS) * args.repeats), file=sys.stderr)
    if args.dry_run or not items:
        return 0
    if args.perplexity:
        from scripts.links_check import perplexity_client
        send, model = perplexity_client().ask, args.perplexity

        def ask(payload):
            return send({**payload, 'model': model})
    else:
        from scripts import jev_replay_check
        if args.connection:
            jev_replay_check.CONNECTION = Path(args.connection).expanduser().resolve()
        client = jev_replay_check.client()
        client.timeout = args.timeout          # the game's own limit (ai_timeout_seconds) is for play, not for a re-ask
        ask = client.ask
    report = run(items, patient(ask), args.repeats, lambda text: print(text, file=sys.stderr, flush=True))
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
