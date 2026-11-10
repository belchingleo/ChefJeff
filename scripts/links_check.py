#!/usr/bin/env python3
"""Does telling Jeff which work each option leads to change what he chooses? Run locally; it asks a model.

    python3 scripts/links_check.py DIR [DIR ...] [--per-kind 10] [--repeats 3] [--bamboo] [--examples FILE] [--dry-run]

From round journals and their session bundles (a model_rounds --out folder, or logs/) this replays each round
and picks the requests at which Jeff had nothing under way, in four kinds:

- pan_ready: a pan or pot holds cooked food and Jeff's hands are empty;
- raw_to_chop: Jeff holds a raw ingredient that needs chopping and a board is free;
- dirty_only: no clean plate anywhere, a dirty plate on the return or in the sink, and an order waiting;
- control: none of these (nothing for a link to point at, so the arms should agree).

Each moment is asked again in two arms, next_action only:

- A: exactly as it was sent (rebuilt from the bundle; a moment that does not rebuild byte for byte is left out);
- B: the same request with links.py's line on the options that lead to new work, its rule and its version.

The outcome of a kind is whether the answer chose an option whose link (computed for B, counted the same in both
arms) leads to that kind's work: plating from the pan, chopping, or putting a dirty plate in the sink and washing it;
and whether it was wait. Reports hold counts and shares only (no request, state or model text). --examples writes,
for a few moments, the options of both arms side by side, to check the links by eye before asking anything.
--dry-run picks the moments and prints their number and size only. The clients are reach_note_check's: --bamboo
(StartLux on Bamboo Relay), --local URL, or the connection saved in the game (run that one in your own terminal).
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
from scripts.decision_stats import read_rounds  # noqa: E402
from scripts.jev_replay_check import estimate, journals, share  # noqa: E402
from scripts.food_names_check import bundle_for, rebuild  # noqa: E402
from scripts import reask  # noqa: E402
from scripts import reach_note_check as clients  # noqa: E402
import links  # noqa: E402

ARMS = ('A', 'B')
KINDS = ('pan_ready', 'raw_to_chop', 'dirty_only', 'control')
TARGET = {'pan_ready': ('plate_pot', 'plate_counter', 'plate_from_counter', 'plate_ground', 'plate_partner'),
          'raw_to_chop': ('chop',), 'dirty_only': ('put_sink', 'wash'), 'control': ()}


def kind_of(k):
    """Which kind of moment this is for Jeff (he has nothing under way), or None when he is busy."""
    me = k.chefs['jeff']
    if me.job is not None:
        return None
    if me.hand is None and any(k.stations[p].food and k.stations[p].food.stage == 'ready' for p in k.pots):
        return 'pan_ready'
    if (me.hand is not None and not me.hand.plate_id and me.hand.stage == 'raw' and k.rules.choppable(me.hand)
            and any(k.stations[b].food is None for b in k.boards)):
        return 'raw_to_chop'
    foods = [c.hand for c in k.chefs.values()] + [s.food for s in k.stations.values()] + [g.food for g in k.ground.values()]
    clean = any(f is not None and (f.stage == 'clean_plate' or f.plate_id) for f in foods)
    dirty = any(k.stations[s].food is not None and k.stations[s].food.stage == 'dirty_plate' for s in (k.returns, k.sink))
    if not clean and dirty and any(o['status'] == 'pending' for o in k.orders):
        return 'dirty_only'
    return 'control'


def listed(k, row):
    """The actions the request listed (the engine's, and the one-press options when the round had them)."""
    import one_press
    actions = k.actions('jeff')
    if row.get('one_press'):
        actions = actions + one_press.options(k, 'jeff', actions, row['one_press'])
    return actions


def moments(paths):
    """(found, counts): every picked-kind moment with both arms' requests and the options whose link leads to its work."""
    from session_record import read_bundle
    from kitchen import apply_input
    from research_replay import factory
    found, counts, number = [], Counter(), 0
    for path in journals(paths):
        for rows in read_rounds(path)[0]:
            start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
            features = start.get('features') or {}
            bundle = bundle_for(path)
            if bundle is None:
                counts['rounds_without_bundle'] += 1
                continue
            number += 1
            data = read_bundle(bundle)
            k = factory(data['session']['runtime_versions']['engine'])(deepcopy(data['resolved']))
            inputs, n = data['inputs'], 0
            reach = bool((features.get('reach_note') or {}).get('on'))
            names = bool((features.get('food_names') or {}).get('on'))
            answers = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_response'}
            for row in rows:
                payload = row.get('payload')
                if row.get('kind') != 'ai_request' or not isinstance(payload, dict) or row.get('ask_ahead'):
                    continue
                at = row.get('game_time_ms')
                while n < len(inputs) and inputs[n]['game_time_ms'] < at:
                    apply_input(k, inputs[n])
                    n += 1
                answer = answers.get(row.get('request_id'))
                kind = kind_of(k)
                if answer is None or kind is None:
                    continue
                plain = rebuild(k, row, reach, names)
                while plain != payload and n < len(inputs) and inputs[n]['game_time_ms'] == at:
                    apply_input(k, inputs[n])
                    n += 1
                    plain = rebuild(k, row, reach, names)
                    kind = kind_of(k)
                if plain != payload or kind is None:
                    counts['not_rebuilt'] += 1
                    continue
                b, linked = links.annotate(deepcopy(plain), k, 'jeff', listed(k, row), names)
                held = k.chefs['jeff'].hand.id if kind == 'raw_to_chop' else None
                target = sorted(key for key, pairs in linked.items() if _leads_to(k, pairs, TARGET[kind], held))
                counts[kind] += 1
                found.append({'kind': kind, 'payload': payload, 'linked': b, 'links': linked, 'target': target,
                              'logged_choice': answer.get('choice'), 'round': number, 't': round(at / 1000, 2)})
    counts['rounds'] = number
    return found, dict(counts)


def _leads_to(k, pairs, kinds, held=None):
    """Whether linked actions include work of these kinds (the key's verb names the kind's action); for chopping, only
    chopping the item Jeff holds (its id is in the engine's chop label)."""
    verbs = {'plate_pot': 'plate', 'plate_counter': 'plate', 'plate_from_counter': 'plate', 'plate_ground': 'plate ground',
             'plate_partner': 'plate partner', 'chop': 'chop', 'put_sink': 'put', 'wash': 'wash'}
    sink = getattr(k, 'sink', None)
    for key, label in pairs:
        for kind in kinds:
            verb = verbs.get(kind, kind)
            if kind == 'chop' and held is not None:
                if key.startswith('chop ') and f' {held}' in label:
                    return True
            elif kind == 'put_sink':
                if key == f'put {sink}':
                    return True
            elif key == verb or key.startswith(verb + ' '):
                return True
    return False


def arm(item, name):
    payload = deepcopy(item['linked'] if name == 'B' else item['payload'])
    payload['questions'] = {'next_action': payload['questions']['next_action']}
    return payload


OUTCOMES = {
    'chose_linked_work': lambda i, p, a: a['choice'] in i['target'],
    'waited': lambda i, p, a: a['choice'] == 'wait',
    'same_as_logged': lambda i, p, a: a['choice'] == i['logged_choice'],
}


def pick(found, per_kind, seed):
    rng = random.Random(seed)
    out = []
    for kind in KINDS:
        pool = [i for i in found if i['kind'] == kind and (kind == 'control' or i['target'])]
        out += rng.sample(pool, min(per_kind, len(pool)))
    return out


def examples(items, path, most=2):
    """For a few moments per kind, the options of both arms side by side (the request text, for checking by eye)."""
    out = []
    for kind in KINDS:
        for item in [i for i in items if i['kind'] == kind][:most]:
            a = item['payload']['questions']['next_action']['criteria']
            b = item['linked']['questions']['next_action']['criteria']
            out.append({'kind': kind, 't': item['t'], 'logged_choice': item['logged_choice'], 'target': item['target'],
                        'options_with_links': {key: b[key] for key in item['links']},
                        'options': len(a)})
    Path(path).write_text(json.dumps(out, ensure_ascii=False, indent=1))


def run(items, ask, repeats=1):
    out = {'moments': len(items), 'repeats': repeats, 'questions_asked': ['next_action'], 'by_kind': {}}
    asked = {'arms': {name: [] for name in ARMS}, 'models': Counter()}
    for item in items:
        one = reask.ask_arms([item], ARMS, arm, ask, clients.ask_once, repeats)
        for name in ARMS:
            asked['arms'][name] += one['arms'][name]
        asked['models'].update(one['models'])
    asked['models'] = dict(asked['models'].most_common())
    for kind in KINDS:
        part = {'arms': {name: [r for r in rows if r[0]['kind'] == kind] for name, rows in asked['arms'].items()},
                'models': asked['models']}
        if not part['arms']['A']:
            continue
        summary = {}
        for name, rows in part['arms'].items():
            replies = [(i, a) for i, _, rs in rows for a in rs if 'error' not in a]
            summary[name] = {'answered': len(replies),
                             'chose_linked_work': share(sum(a['choice'] in i['target'] for i, a in replies), len(replies)),
                             'waited': share(sum(a['choice'] == 'wait' for i, a in replies), len(replies)),
                             'errors': sum(1 for i, _, rs in rows for a in rs if 'error' in a)}
        out['by_kind'][kind] = {'moments': len(part['arms']['A']), 'arms': summary, 'stats': reask.stats(part, OUTCOMES)}
    out['models'] = asked['models']
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--per-kind', type=int, default=10)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--local', metavar='URL')
    parser.add_argument('--model', default='startlux-local-2b-instant-q4')
    parser.add_argument('--bamboo', action='store_true', help='StartLux on Bamboo Relay, key from ' + str(clients.BAMBOO_KEY))
    parser.add_argument('--examples', help='write both arms of a few moments here, for checking the links by eye')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    found, counts = moments(args.paths)
    items = pick(found, args.per_kind, args.seed)
    print(f'moments found: {counts}; picked {Counter(i["kind"] for i in items)}', file=sys.stderr)
    with_links = [i for i in found if i['kind'] != 'control']
    print(f'non-control moments whose B has a link to their work: {sum(bool(i["target"]) for i in with_links)} of {len(with_links)}',
          file=sys.stderr)
    if args.examples:
        examples(items, args.examples)
    if not items:
        return 1
    print(estimate([{'payload': arm(i, 'B')} for i in items], len(ARMS) * args.repeats), file=sys.stderr)
    if args.dry_run:
        return 0
    if args.local:
        ask = clients.local_client(args.local, args.model).ask
    elif args.bamboo:
        ask = clients.bamboo_client().ask
    else:
        from scripts.jev_replay_check import client
        ask = client().ask
    report = run(items, ask, args.repeats)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
