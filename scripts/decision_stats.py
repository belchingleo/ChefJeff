#!/usr/bin/env python3
"""How Jeff decided in finished local rounds, per model. Record only.

    python3 scripts/decision_stats.py logs/            (or some logs/*.jsonl files)

It reads the local round journals (logs/*.jsonl) and changes nothing: no game, no model call.
For each model it counts:

- unsure: how far apart a decision model put its top two options (margin = first minus second
  probability, over the options that were offered). Chat models report no probabilities.
- replaced: Jeff's actions that its own next choice replaced before they were done (the engine's
  `interrupted` event followed at once by Jeff's next `action_start`). Being knocked off by a dash
  is counted apart; that was not Jeff's choice.
- back_and_forth: A -> B -> A, where Jeff replaced an action at target A with one at B and that
  one again with an action at A.
- plan (rounds with Jeff's plan on): plans set, how they ended, how long they held, and how many
  of the actions Jeff started while a plan held belong to its part (harness.action_part).
  `unsure_with_plan` counts the decisions that were unsure (first margin) while a plan had held
  for more than --plan-age seconds: the trigger proposed for the third tier, here only counted.

Rates are per game minute. A round counts for the model that answered most of its requests.

The report names models: keep it private like logs/, and do not publish per-model results.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import action_part  # noqa: E402
from kitchen import Action  # noqa: E402

VERSION = 'decision-stats-1'
MARGINS = (0.05, 0.1)
PLAN_AGE = 5.0
NON_ACTIONS = ('continue', 'wait', 'stop')


def read_rounds(path):
    """The rounds in one journal: a file normally holds one, each beginning with its start row."""
    rounds, rows, unreadable = [], [], 0
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                row = json.loads(line)
            except ValueError:
                unreadable += 1
                continue
            if not isinstance(row, dict):
                unreadable += 1
                continue
            if row.get('kind') == 'start' and rows:
                rounds.append(rows)
                rows = []
            rows.append(row)
    if rows:
        rounds.append(rows)
    return rounds, unreadable


def game_time(row):
    if isinstance(row.get('game_time_ms'), (int, float)):
        return row['game_time_ms'] / 1000
    return row.get('t') if isinstance(row.get('t'), (int, float)) else None


def offered(request):
    """Option keys of a request, from the full payload or the logged candidate list."""
    if not request:
        return None
    payload = request.get('payload')
    if isinstance(payload, dict):
        return list(payload.get('questions', {}).get('next_action', {}).get('criteria', {}))
    return request.get('candidates')


def jeff(state):
    return ((state or {}).get('chefs') or {}).get('jeff') or {}


def new_model():
    return {'rounds': 0, 'game_minutes': 0.0, 'decisions': 0, 'fresh': 0, 'applied': 0,
            'top': [], 'margins': [], 'chose_top': 0, 'single_probability': 0, 'pairs': Counter(),
            'started': 0, 'replaced': 0, 'knocked_off': 0, 'other_interruptions': 0, 'back_and_forth': 0,
            'plan_rounds': 0, 'plans_set': Counter(), 'plan_ends': Counter(), 'holds': [],
            'in_part': Counter(), 'off_part': Counter(), 'no_part': Counter(), 'unsure_with_plan': 0}


def add_round(rows, models, margins=MARGINS, plan_age=PLAN_AGE):
    responses = [r for r in rows if r.get('kind') == 'ai_response']
    if not responses:
        return None
    requests = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_request'}
    main = Counter(str(r.get('model') or 'unknown') for r in responses).most_common(1)[0][0]
    m = models[main]
    times = [t for t in map(game_time, rows) if t is not None]
    m['rounds'] += 1
    m['game_minutes'] += (max(times) if times else 0) / 60
    by_action = {}      # action_id -> (model, target)
    plan_on = bool(rows[0].get('jeff_plan')) or any(r.get('jeff_plan') for r in requests.values())
    if plan_on:
        m['plan_rounds'] += 1
    holding = None      # the plan the previous request carried; a plan still held at closing is not counted
    for request in sorted(requests.values(), key=lambda r: r.get('request_id') or 0):
        if request.get('plan_ended'):
            m['plan_ends'][request['plan_ended']] += 1
            if holding and game_time(request) is not None:
                m['holds'].append(round(game_time(request) - holding['set_at'], 3))
        holding = (request.get('jeff_plan') or {}).get('current')
    for response in responses:
        model = models[str(response.get('model') or 'unknown')]
        request = requests.get(response.get('request_id'))
        model['decisions'] += 1
        model['fresh'] += bool(response.get('fresh'))
        model['applied'] += bool(response.get('applied'))
        choice = response.get('choice')
        keys = offered(request)
        reported = response.get('probabilities')
        probabilities = {k: v for k, v in (reported if isinstance(reported, dict) else {}).items()
                         if isinstance(v, (int, float)) and not isinstance(v, bool) and (keys is None or k in keys)}
        current = (request or {}).get('jeff_plan', {}) or {}
        current = current.get('current')
        if probabilities:
            ranked = sorted(probabilities.items(), key=lambda kv: -kv[1])
            first = ranked[0][1]
            second = ranked[1][1] if len(ranked) > 1 else 0.0
            model['single_probability'] += len(ranked) == 1
            margin = round(first - second, 6)
            model['top'].append(first)
            model['margins'].append(margin)
            model['chose_top'] += choice == ranked[0][0]
            if len(ranked) > 1 and margin < max(margins):
                model['pairs']['/'.join(sorted(k.split(' ')[0] for k, _ in ranked[:2]))] += 1
            now = game_time(response)
            if current and now is not None and now - current['set_at'] > plan_age and margin < min(margins):
                model['unsure_with_plan'] += 1
        if response.get('plan_set'):
            model['plans_set'][response.get('plan_role')] += 1
        state = response.get('current_state')
        if response.get('applied') and response.get('action_id') is not None and choice not in NON_ACTIONS:
            target = jeff(state).get('target')
            by_action[response['action_id']] = (model, target if target is not None else choice)
            kind = jeff(state).get('action_kind')
            if current and current['role'] != 'flexible' and kind:
                part = action_part(Action(choice, '', kind, target), state)
                bucket = 'no_part' if part is None else 'in_part' if part == current['role'] else 'off_part'
                model[bucket][current['role']] += 1
    events = [r for r in rows if r.get('actor') == 'jeff' and r.get('kind') in ('action_start', 'interrupted', 'knocked')]
    starts = []         # (target, replaced by Jeff's next choice)
    for i, event in enumerate(events):
        if event['kind'] == 'action_start':
            owner, target = by_action.get(event.get('action_id'), (m, event.get('action')))
            owner['started'] += 1
            starts.append([owner, target, False])
            if len(starts) >= 3 and starts[-3][2] and starts[-2][2] and starts[-3][1] == target != starts[-2][1]:
                owner['back_and_forth'] += 1
        elif event['kind'] == 'interrupted':
            following = events[i + 1] if i + 1 < len(events) else None
            if following and following['kind'] == 'action_start' and game_time(following) == game_time(event):
                owner, _ = by_action.get(following.get('action_id'), (m, None))
                owner['replaced'] += 1
                if starts:
                    starts[-1][2] = True
            elif following and following['kind'] == 'knocked':
                m['knocked_off'] += 1
            else:
                m['other_interruptions'] += 1
    return main


def share(part, whole):
    return round(part / whole, 4) if whole else None


def per_minute(count, minutes):
    return round(count / minutes, 2) if minutes else None


def summary(m, margins=MARGINS):
    minutes = round(m['game_minutes'], 2)
    out = {'rounds': m['rounds'], 'game_minutes': minutes,
           'decisions': {'answered': m['decisions'], 'fresh': m['fresh'], 'applied': m['applied']}}
    n = len(m['margins'])
    out['unsure'] = None if not n else {
        'with_probabilities': n, 'only_one_probability': m['single_probability'],
        'median_top_probability': round(median(m['top']), 4), 'median_margin': round(median(m['margins']), 4),
        'chose_the_top_option': share(m['chose_top'], n),
        'below': {f'{t:g}': {'count': sum(x < t for x in m['margins']), 'share': share(sum(x < t for x in m['margins']), n),
                             'per_game_minute': per_minute(sum(x < t for x in m['margins']), minutes)} for t in margins},
        'closest_pairs': dict(m['pairs'].most_common(8))}
    out['actions'] = {'started': m['started'], 'replaced_by_own_next_choice': m['replaced'],
                      'replaced_share': share(m['replaced'], m['started']),
                      'replaced_per_game_minute': per_minute(m['replaced'], minutes),
                      'back_and_forth': m['back_and_forth'], 'back_and_forth_per_game_minute': per_minute(m['back_and_forth'], minutes),
                      'knocked_off': m['knocked_off'], 'other_interruptions': m['other_interruptions']}
    if m['plan_rounds']:
        roles = sorted(set(m['in_part']) | set(m['off_part']) | set(m['no_part']))
        out['plan'] = {'rounds': m['plan_rounds'], 'set': dict(m['plans_set']), 'ended': dict(m['plan_ends']),
                       'median_hold_seconds': round(median(m['holds']), 2) if m['holds'] else None,
                       'actions_while_held': {role: {'in_part': m['in_part'][role], 'other_part': m['off_part'][role],
                                                     'no_part': m['no_part'][role],
                                                     'in_part_share': share(m['in_part'][role], m['in_part'][role] + m['off_part'][role])}
                                              for role in roles},
                       'unsure_with_plan': m['unsure_with_plan']}
    return out


def report(paths, margins=MARGINS, plan_age=PLAN_AGE):
    files = []
    for path in map(Path, paths):
        files += sorted(path.glob('*.jsonl')) if path.is_dir() else [path]
    models = defaultdict(new_model)
    counted = skipped = unreadable = 0
    for path in files:
        rounds, bad = read_rounds(path)
        unreadable += bad
        for rows in rounds:
            if add_round(rows, models, margins, plan_age) is None:
                skipped += 1
            else:
                counted += 1
    return {'version': VERSION, 'files': len(files), 'rounds': counted, 'rounds_without_model_answers': skipped,
            'unreadable_lines': unreadable, 'margins': list(margins), 'plan_age_seconds': plan_age,
            'models': {name: summary(m, margins) for name, m in sorted(models.items()) if m['decisions']}}


def main(argv=None):
    parser = argparse.ArgumentParser(description="How Jeff decided in local round logs, per model (record only).")
    parser.add_argument('paths', nargs='+', help='journal files or folders of them (logs/)')
    parser.add_argument('--margins', type=float, nargs='+', default=list(MARGINS), help='unsure below these margins')
    parser.add_argument('--plan-age', type=float, default=PLAN_AGE, help='seconds a plan has held before unsure counts')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    result = report(args.paths, tuple(sorted(args.margins)), args.plan_age)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
