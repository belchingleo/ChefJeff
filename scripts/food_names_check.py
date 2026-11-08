#!/usr/bin/env python3
"""Does naming food by ingredient and state change whether Jeff fetches what no one has? Run locally; it asks a model.

    python3 scripts/food_names_check.py logs/ [--since 2026-11-08] [--sample 20] [--repeats 2] [--local URL] [--dry-run]

From local round journals and their session bundles (logs/sessions/, written when a round ends) this picks the
requests at which Jeff stood empty-handed with nothing under way, a dish of the menu needed an ingredient that was
nowhere in the kitchen (not in a hand, on a station, on the floor, in a pan or on a plate), and Jeff answered wait.
Each is sent again, re-asking instead of playing new rounds:

- as_logged: exactly as it was sent (these rounds ran with food_names off);
- food_names: the same request as the game builds it with the food_names switch on (food_names.py).

The second is not an edit of the first: the round is replayed from its bundle's engine inputs up to the request, the
request is built again with the switch off and must equal the logged one byte for byte (else the moment is left
out, counted in not_rebuilt), and then built with the switch on. Both arms ask next_action only.

For each arm it reports how often the answer fetched a missing ingredient, how often it was wait, and, when the
model gives option probabilities (a decision service), the probability it put on those fetches: the mean per arm
and the paired change per moment. The report holds counts, shares and probabilities only (no request, state or
model text). It reads the journals and changes nothing. The clients are reach_note_check's: --local, --bamboo,
--hf-space, or the connection saved in the game (run that one yourself, in your own terminal). --dry-run picks the
moments and prints their number and size without asking anything.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.decision_stats import read_rounds  # noqa: E402
from scripts.jev_replay_check import estimate, journals, pick, share  # noqa: E402
from scripts import reask  # noqa: E402
from scripts import reach_note_check as clients  # noqa: E402

ARMS = ('as_logged', 'food_names')


def bundle_for(journal):
    """The session bundle a journal's round wrote (sessions/<game id>, the journal names its first 8 digits)."""
    parts = Path(journal).stem.split('-')
    folder = Path(journal).parent / 'sessions'
    if len(parts) < 2 or not folder.is_dir():
        return None
    return next((p for p in sorted(folder.iterdir()) if p.name.startswith(parts[1]) and (p / 'engine-inputs.jsonl').exists()), None)


def items_present(k):
    """Every ingredient somewhere in the kitchen: in a hand, on a station, on the floor, in a vessel, on a plate."""
    seen = set()

    def add(food):
        if food is None:
            return
        if food.contents is not None:
            add(food.contents)
        if food.plate_id:
            seen.update(food.components or (food.ingredient,))
        elif food.stage not in ('pot', 'extinguisher', 'clean_plate', 'dirty_plate'):
            seen.add(food.ingredient)
    for chef in k.chefs.values():
        add(chef.hand)
    for station in k.stations.values():
        add(station.food)
    for item in k.ground.values():
        add(item.food)
    for p in getattr(k, 'projectiles', {}).values():
        add(p['food'])
    return seen


def missing_fetches(k, actions):
    """The fetch options for menu ingredients that are nowhere in the kitchen."""
    needed = {part for dish in k.rules.menu for part in k.rules.recipe_parts[dish]}
    missing = needed - items_present(k)
    return [a.key for a in actions if a.kind == 'fetch' and k.ingredients.get(a.target) in missing]


def rebuild(k, row, reach, names):
    """The request the game builds at this point of the replayed round (jev.compose_payload), as a journal holds it."""
    from jev import compose_payload, NO_MEMORY
    from whitebox_server import SpatialJevClient
    state = row['payload']['state']
    source = k
    if row.get('ask_ahead'):
        import ask_ahead
        source = ask_ahead.predict(k) if (k.chefs['jeff'].job and k.chefs['jeff'].job.id == row['ask_ahead']['job_id']) else None
        if source is None:
            return None
    payload = compose_payload(SpatialJevClient(k.c, key='food-names-check-no-credential'), source, source.snapshot(),
                              source.actions('jeff'), state.get('recent_decisions', []), state.get('player_communication'),
                              state['past_episodes'] if 'past_episodes' in state else NO_MEMORY, row.get('jeff_plan'),
                              row.get('one_press'), row.get('undo_note'), reach, names)
    return json.loads(json.dumps(payload, ensure_ascii=False))


def moments(paths, since=None, until=None):
    """(found, counts): the wait moments with a missing ingredient, each with both arms' requests."""
    from session_record import read_bundle
    from kitchen import apply_input
    from research_replay import factory
    found, counts, number = [], Counter(), 0
    for path in journals(paths):
        for rows in read_rounds(path)[0]:
            start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
            day = str(start.get('wall_time') or '')[:10]
            if (since and (not day or day < since)) or (until and (not day or day > until)):
                continue
            features = start.get('features') or {}
            if (features.get('food_names') or {}).get('on'):
                continue                      # already named: nothing to compare
            bundle = bundle_for(path)
            if bundle is None:
                counts['rounds_without_bundle'] += 1
                continue
            number += 1
            data = read_bundle(bundle)
            k = factory(data['session']['runtime_versions']['engine'])(deepcopy(data['resolved']))
            inputs, n = data['inputs'], 0
            reach = bool((features.get('reach_note') or {}).get('on'))
            answers = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_response'}
            for row in rows:
                payload = row.get('payload')
                if row.get('kind') != 'ai_request' or not isinstance(payload, dict):
                    continue
                at = row.get('game_time_ms')
                while n < len(inputs) and inputs[n]['game_time_ms'] < at:
                    apply_input(k, inputs[n])
                    n += 1
                answer = answers.get(row.get('request_id'))
                k_jeff = k.chefs['jeff']
                if (answer is None or answer.get('choice') != 'wait' or k_jeff.hand is not None or k_jeff.job is not None):
                    continue
                fetches = missing_fetches(k, k.actions('jeff'))
                if not fetches:
                    continue
                plain = rebuild(k, row, reach, False)
                while plain != payload and n < len(inputs) and inputs[n]['game_time_ms'] == at:
                    apply_input(k, inputs[n])      # an input of the same tick may come before the request
                    n += 1
                    plain = rebuild(k, row, reach, False)
                if plain != payload:
                    counts['not_rebuilt'] += 1
                    continue
                found.append({'payload': payload, 'named': rebuild(k, row, reach, True), 'fetching': fetches,
                              'logged_choice': answer['choice'], 'round': number})
    counts['rounds'] = number
    return found, dict(counts)


def arm(item, name):
    payload = deepcopy(item['named'] if name == 'food_names' else item['payload'])
    payload['questions'] = {'next_action': payload['questions']['next_action']}
    return payload


def fetch_mass(item, answer):
    p = answer.get('probabilities') or {}
    return round(sum(float(p.get(k, 0)) for k in item['fetching']), 4) if p else None


OUTCOMES = {
    'fetched_missing': lambda i, p, a: a['choice'] in i['fetching'],
    'waited': lambda i, p, a: a['choice'] == 'wait',
}


def run(items, ask, arms_asked=ARMS, repeats=1):
    out = {'moments': len(items), 'rounds': len({i['round'] for i in items}), 'repeats': repeats,
           'questions_asked': ['next_action'], 'arms': {}}
    asked = {'arms': {name: [] for name in arms_asked}, 'models': Counter()}
    for item in items:          # moment by moment, both arms back to back: a quota that runs out leaves whole pairs
        one = reask.ask_arms([item], arms_asked, arm, ask, clients.ask_once, repeats)
        for name in arms_asked:
            asked['arms'][name] += one['arms'][name]
        asked['models'].update(one['models'])
    asked['models'] = dict(asked['models'].most_common())
    masses = {}
    for name, rows in asked['arms'].items():
        errors, answered, mass = Counter(), [], []
        for item, _, replies in rows:
            for answer in replies:
                if 'error' in answer:
                    errors[answer['error']] += 1
                else:
                    answered.append((item, answer))
            first = replies[0] if replies and 'error' not in replies[0] else None
            mass.append(fetch_mass(item, first) if first else None)
        masses[name] = mass
        known = [m for m in mass if m is not None]
        out['arms'][name] = {'asked': len(items) * repeats, 'answered': len(answered),
                             'fetched_missing': share(sum(a['choice'] in i['fetching'] for i, a in answered), len(answered)),
                             'waited': share(sum(a['choice'] == 'wait' for i, a in answered), len(answered)),
                             'fetch_probability_mean': round(statistics.fmean(known), 4) if known else None,
                             'errors': dict(errors.most_common())}
    if len(arms_asked) > 1:
        base = masses[arms_asked[0]]
        for name in arms_asked[1:]:
            changes = [round(b - a, 4) for a, b in zip(base, masses[name]) if a is not None and b is not None]
            out['arms'][name]['fetch_probability_change'] = {
                'moments': len(changes), 'per_moment': changes,
                'mean': round(statistics.fmean(changes), 4) if changes else None,
                'up': sum(c > 0 for c in changes), 'down': sum(c < 0 for c in changes), 'same': sum(c == 0 for c in changes)}
    out['stats'] = reask.stats(asked, OUTCOMES)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+', help='local round journals (logs/, or a model_rounds --out folder) or files')
    parser.add_argument('--since', help='first day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--until', help='last day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--sample', type=int, default=20, help='moments to pick')
    parser.add_argument('--repeats', type=int, default=1, help='times each moment is asked in each arm')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--start', type=int, default=0, help='skip this many of the picked moments (to go on after a quota ran out)')
    parser.add_argument('--arms', default=','.join(ARMS), help='comma-separated arms to send: ' + ', '.join(ARMS))
    parser.add_argument('--local', metavar='URL', help='a decision service on this computer, e.g. http://127.0.0.1:8090/v1/systemone')
    parser.add_argument('--model', default='startlux-local-2b-instant-q4', help='with --local: the model name')
    parser.add_argument('--bamboo', action='store_true', help='StartLux on Bamboo Relay, key from ' + str(clients.BAMBOO_KEY))
    parser.add_argument('--hf-space', action='store_true', help="StartLux's demo Space on Hugging Face: " + clients.HF_SPACE)
    parser.add_argument('--dry-run', action='store_true', help='pick the moments and print their number and size only')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    arms_asked = tuple(a for a in args.arms.split(',') if a)
    if not arms_asked or set(arms_asked) - set(ARMS):
        parser.error('--arms takes ' + ', '.join(ARMS))
    if args.repeats < 1:
        parser.error('--repeats takes 1 or more')
    found, counts = moments(args.paths, args.since, args.until)
    items = pick(found, args.sample, args.seed)[max(0, args.start):]
    print(f"{len(found)} moments found in {counts.get('rounds', 0)} rounds ({counts.get('not_rebuilt', 0)} not rebuilt exactly, "
          f"{counts.get('rounds_without_bundle', 0)} rounds without a session bundle), {len(items)} picked", file=sys.stderr)
    if not items:
        print('no request in those journals and days had Jeff waiting empty-handed while a needed ingredient was nowhere')
        return 1
    print(estimate([{'payload': arm(i, 'food_names')} for i in items], len(arms_asked) * args.repeats), file=sys.stderr)
    if args.dry_run:
        return 0
    if sum(map(bool, (args.local, args.bamboo, args.hf_space))) > 1:
        parser.error('one of --local, --bamboo and --hf-space')
    if args.local:
        ask = clients.local_client(args.local, args.model).ask
    elif args.bamboo:
        ask = clients.bamboo_client().ask
    elif args.hf_space:
        token = clients.private_secret(clients.HF_TOKEN) if clients.HF_TOKEN.exists() else None
        ask = clients.SpaceClient(token=token).ask
    else:
        from scripts.jev_replay_check import client
        ask = client().ask
    report = {**run(items, ask, arms_asked, args.repeats), 'found': len(found), **counts}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
