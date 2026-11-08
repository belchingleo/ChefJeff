#!/usr/bin/env python3
"""Does a factual undo note keep Jeff from taking back his last step? Run locally; it sends to the game's model.

    python3 scripts/undo_note_check.py logs/ [--since 2026-11-06] [--kind take_back] [--sample 40] [--repeats 2] [--dry-run]

From local round journals this picks the requests of Jev rounds at which a next_action option would have taken
back what Jeff's last step put down (--kind take_back, the swap this check is about) or, with --kind put_back,
only put back what it took (undo_note.py, worked out from the journal exactly as the decision loop does with the
switch on), and sends each to the current model, re-asking the logged request instead of playing new rounds:

- as_logged: exactly as it was sent (these rounds ran with the switch off);
- undo_note: the same, with what the undo_note switch adds (undo_note.apply): the notes on those options and the
  version; nothing else changes.

For each arm it reports how often the answer took back the last step (chose a noted next_action option), how
often it was a full swap (also put the held item back where it was taken, through put_where), and how often it
was the logged answer, with the logged answers' shares for comparison. The report holds counts and shares only
(no request, state or model text). It reads the journals and changes nothing. It asks through the connection
saved in the game (jev_replay_check.client), else the local Jev key; the key is read the way the game reads it and
is never printed. --dry-run picks the moments and prints their number and size without asking anything.
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
import undo_note  # noqa: E402
from scripts.decision_stats import read_rounds  # noqa: E402
from scripts.jev_replay_check import client, estimate, journals, pick, share  # noqa: E402
from scripts import reask  # noqa: E402

ARMS = ('as_logged', 'undo_note')
KINDS = ('take_back', 'put_back')


def note_kind(payload, step):
    """take_back when a next_action option would take back the last step's put, put_back when one would only put
    back what it took, else None."""
    found = undo_note.notes(payload['state']['kitchen'], step)
    keys = payload['questions']['next_action']['criteria']
    if 'take_back' in found and any(undo_note._take_target(k) == found['take_back'][0] for k in keys):
        return 'take_back'
    if 'put_back' in found and any(undo_note._put_target(k) == found['put_back'][0] for k in keys):
        return 'put_back'
    return None


def moments(paths, since=None, until=None, model_prefix='jev', kind='take_back'):
    """[{payload, step, logged_choice, logged_put_where, round}] for answered Jev requests with a note of this kind."""
    found, number = [], 0
    for path in journals(paths):
        for rows in read_rounds(path)[0]:
            start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
            day = str(start.get('wall_time') or '')[:10]
            if (since and (not day or day < since)) or (until and (not day or day > until)):
                continue
            number += 1
            answers = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_response'}
            last = None
            for row in rows:
                if row.get('kind') == 'ai_response' and row.get('applied') and isinstance(row.get('current_state'), dict):
                    # The same step the decision loop keeps: from the snapshot logged as the choice started.
                    step = undo_note.step(row['current_state'], row.get('choice'), (row.get('one_press') or {}).get('first'),
                                          row['current_state'].get('time', 0))
                    last = step if step is not None else last
                    continue
                if row.get('kind') != 'ai_request' or not isinstance(row.get('payload'), dict):
                    continue
                answer = answers.get(row.get('request_id'))
                if (answer is None or not str(answer.get('model') or '').startswith(model_prefix)
                        or not isinstance(answer.get('choice'), str) or 'undo_note_version' in row['payload']['state']):
                    continue
                if note_kind(row['payload'], last) == kind:
                    found.append({'payload': row['payload'], 'step': deepcopy(last), 'logged_choice': answer['choice'],
                                  'logged_put_where': answer.get('put_where'), 'round': number})
    return found


def arm(item, name):
    payload = deepcopy(item['payload'])
    if name == 'undo_note':
        undo_note.apply(payload, {'step': item['step']})
    return payload


def took_back(item, choice, put_where):
    """(chose a noted next_action option, and also put the held item back through put_where)."""
    noted = set(undo_note.annotate(deepcopy(item['payload']), item['step']))
    back = ('next_action', choice) in noted
    return back, back and choice.startswith('put then ') and ('put_where', put_where) in noted


def ask_once(ask, payload):
    try:
        answer = ask(deepcopy(payload))
        return {'choice': answer['choice'], 'put_where': answer.get('put_where')}
    except RuntimeError as error:    # the client's own sanitized message, never the key
        return {'error': str(error)}


def shares(pairs):
    """pairs: [(item, choice, put_where)] answered."""
    marks = [took_back(i, c, p) for i, c, p in pairs]
    return {'answered': len(pairs),
            'took_back': share(sum(back for back, _ in marks), len(pairs)),
            'full_swap': share(sum(full for _, full in marks), len(pairs)),
            'same_as_logged': share(sum(c == i['logged_choice'] for i, c, _ in pairs), len(pairs))}


# Outcomes with intervals and paired differences (reask.stats); the shares above stay as they were.
OUTCOMES = {
    'took_back': lambda i, p, a: took_back(i, a['choice'], a['put_where'])[0],
    'full_swap': lambda i, p, a: took_back(i, a['choice'], a['put_where'])[1],
    'same_as_logged': lambda i, p, a: a['choice'] == i['logged_choice'],
}


def run(items, ask, arms_asked=ARMS, repeats=1):
    out = {'moments': len(items), 'rounds': len({i['round'] for i in items}), 'repeats': repeats,
           'logged': shares([(i, i['logged_choice'], i['logged_put_where']) for i in items]), 'arms': {}}
    asked = reask.ask_arms(items, arms_asked, arm, ask, ask_once, repeats)
    for name, rows in asked['arms'].items():
        pairs, errors = [], Counter()
        for item, _, replies in rows:
            for answer in replies:
                if 'error' in answer:
                    errors[answer['error']] += 1
                else:
                    pairs.append((item, answer['choice'], answer['put_where']))
        out['arms'][name] = {**shares(pairs), 'asked': len(items) * repeats, 'errors': dict(errors.most_common())}
    out['stats'] = reask.stats(asked, OUTCOMES)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+', help='local round journals (logs/) or files')
    parser.add_argument('--since', help='first day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--until', help='last day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--kind', default='take_back', choices=KINDS, help='which moments: take_back (default) or put_back only')
    parser.add_argument('--sample', type=int, default=40, help='moments to pick')
    parser.add_argument('--repeats', type=int, default=2, help='times each moment is asked in each arm')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--arms', default=','.join(ARMS), help='comma-separated arms to send: ' + ', '.join(ARMS))
    parser.add_argument('--dry-run', action='store_true', help='pick the moments and print their number and size only')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    arms_asked = tuple(a for a in args.arms.split(',') if a)
    if not arms_asked or set(arms_asked) - set(ARMS):
        parser.error('--arms takes ' + ', '.join(ARMS))
    if args.repeats < 1:
        parser.error('--repeats takes 1 or more')
    found = moments(args.paths, args.since, args.until, kind=args.kind)
    items = pick(found, args.sample, args.seed)
    if not items:
        print(f'no Jev request in those journals and days had a {args.kind} note')
        return 1
    logged = shares([(i, i['logged_choice'], i['logged_put_where']) for i in items])
    print(f"{len(found)} moments found, {len(items)} picked from {len({i['round'] for i in items})} rounds; "
          f"logged answers took back the last step {logged['took_back']}, full swap {logged['full_swap']}", file=sys.stderr)
    print(estimate(items, len(arms_asked) * args.repeats), file=sys.stderr)
    if args.dry_run:
        return 0
    text = json.dumps(run(items, client().ask, arms_asked, args.repeats), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
