#!/usr/bin/env python3
"""Where does Jeff put things down before a one-press step, and does the floor's label pull him there? Run locally; it sends to the game's model.

    python3 scripts/put_where_check.py logs/ --since 2026-11-06 [--sample 20] [--arms as_logged,plain_drop] [--dry-run]

From local round journals this picks requests of Jev rounds that asked questions.put_where (Jeff held something
and a one-press option was listed) and whose logged answer was a one-press option, and sends each to the current
Jev, re-asking the logged request instead of playing new rounds:

- as_logged: exactly as it was sent;
- plain_drop: the same, with the floor option's label (drop, in next_action and in put_where) stripped of the
  note "(recoverable, no charge)" that earlier labels carried and the other put places did not; it changes
  nothing else, and matches the label from 2026-11-06 on.

For each arm it reports how often the answer was the logged one, a one-press option, and where put_where put
the held item, by kind of place (counter, board, supply top, floor, none), with the logged answers' places for
comparison. The report holds counts and shares only (no request, state or model text). It reads the journals
and changes nothing. It asks through the connection saved in the game (jev_replay_check.client), else the local Jev
key; the key is read the way the game reads it and is never printed. --dry-run picks the
moments and prints their number and size.
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
from scripts.decision_stats import PLACE_KINDS, read_rounds  # noqa: E402
from scripts.jev_replay_check import client, estimate, journals, pick, share  # noqa: E402
from scripts import reask  # noqa: E402

ARMS = ('as_logged', 'plain_drop')
NOTES = (' (recoverable, no charge)', '（可捡回、不扣钱）', '（可捡回，不扣钱）')
ONE_PRESS_PREFIXES = ('put then ', 'wash from ')


def moments(paths, since=None, until=None, model_prefix='jev'):
    """[{payload, logged_choice, logged_put_where, round}] for answered put_where requests whose answer was one-press."""
    found, number = [], 0
    for path in journals(paths):
        for rows in read_rounds(path)[0]:
            start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
            day = str(start.get('wall_time') or '')[:10]
            if (since and (not day or day < since)) or (until and (not day or day > until)):
                continue
            number += 1
            requests = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_request' and isinstance(r.get('payload'), dict)}
            for answer in rows:
                request = requests.get(answer.get('request_id')) if answer.get('kind') == 'ai_response' else None
                if (request is None or not str(answer.get('model') or '').startswith(model_prefix)
                        or 'put_where' not in request['payload'].get('questions', {})
                        or not str(answer.get('choice') or '').startswith(ONE_PRESS_PREFIXES)):
                    continue
                found.append({'payload': request['payload'], 'logged_choice': answer['choice'],
                              'logged_put_where': answer.get('put_where'), 'round': number})
    return found


def plain(label):
    for note in NOTES:
        label = label.replace(note, '')
    return label


def arm(payload, name):
    payload = deepcopy(payload)
    if name == 'plain_drop':
        for question in ('next_action', 'put_where'):
            criteria = payload['questions'].get(question, {}).get('criteria', {})
            if 'drop' in criteria:
                criteria['drop'] = plain(criteria['drop'])
    return payload


def place(key, payload):
    """The kind of place a put_where answer names: floor, a station kind, or none."""
    if key == 'drop':
        return 'floor'
    if not isinstance(key, str) or not key.startswith('put '):
        return 'none'
    stations = ((payload.get('state') or {}).get('kitchen') or {}).get('stations') or {}
    kind = (stations.get(key[4:]) or {}).get('type')
    return PLACE_KINDS.get(kind, kind or 'unknown')


def ask_once(ask, payload):
    try:
        answer = ask(deepcopy(payload))
        return {'choice': answer['choice'], 'put_where': answer.get('put_where')}
    except RuntimeError as error:    # the client's own sanitized message, never the key
        return {'error': str(error)}


def arm_report(answers):
    ok = [(i, p, a) for i, p, a in answers if 'choice' in a]
    pressed = [(i, p, a) for i, p, a in ok if str(a['choice']).startswith(ONE_PRESS_PREFIXES)]
    places = Counter(place(a.get('put_where'), p) for _, p, a in pressed)
    return {'asked': len(answers), 'answered': len(ok),
            'same_as_logged': share(sum(a['choice'] == i['logged_choice'] for i, _, a in ok), len(ok)),
            'chose_one_press': share(len(pressed), len(ok)),
            'put_where_places': dict(places.most_common()),
            'floor_share': share(places['floor'], len(pressed)),
            'errors': dict(Counter(a['error'] for _, _, a in answers if 'error' in a).most_common())}


def pressed(answer):
    return str(answer['choice']).startswith(ONE_PRESS_PREFIXES)


# Outcomes with intervals and paired differences (reask.stats); floor applies only to one-press answers.
OUTCOMES = {
    'same_as_logged': lambda i, p, a: a['choice'] == i['logged_choice'],
    'chose_one_press': lambda i, p, a: pressed(a),
    'put_on_the_floor': lambda i, p, a: place(a.get('put_where'), p) == 'floor' if pressed(a) else None,
}


def run(items, ask, arms_asked=ARMS):
    logged = Counter(place(i['logged_put_where'], i['payload']) for i in items)
    out = {'moments': len(items), 'rounds': len({i['round'] for i in items}),
           'logged': {'put_where_places': dict(logged.most_common()), 'floor_share': share(logged['floor'], len(items))},
           'arms': {}}
    asked = reask.ask_arms(items, arms_asked, lambda item, name: arm(item['payload'], name), ask, ask_once)
    for name, rows in asked['arms'].items():
        out['arms'][name] = arm_report([(item, payload, replies[0]) for item, payload, replies in rows])
    out['stats'] = reask.stats(asked, OUTCOMES)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+', help='local round journals (logs/) or files')
    parser.add_argument('--since', help='first day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--until', help='last day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--sample', type=int, default=20, help='one-press moments to pick')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--arms', default=','.join(ARMS), help='comma-separated arms to send: ' + ', '.join(ARMS))
    parser.add_argument('--dry-run', action='store_true', help='pick the moments and print their number and size only')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    arms_asked = tuple(a for a in args.arms.split(',') if a)
    if not arms_asked or set(arms_asked) - set(ARMS):
        parser.error('--arms takes ' + ', '.join(ARMS))
    items = pick(moments(args.paths, args.since, args.until), args.sample, args.seed)
    if not items:
        print('no one-press answers to a put_where request in Jev rounds of those journals and days')
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
