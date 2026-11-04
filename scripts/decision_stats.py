#!/usr/bin/env python3
"""How Jeff decided in finished rounds, per model. Record only.

    python3 scripts/decision_stats.py logs/                          local round journals
    python3 scripts/decision_stats.py <folder>/*.cjresearch.zip      research packages (scripts/pull_research.py)

It reads, and changes nothing: no game, no model call. Inputs are local round journals
(logs/*.jsonl), research packages (*.cjresearch.zip, checked with research_export.verify_package,
so an expired package is refused) and single research records (*.json, a player's download).
Research records name the model only as the browser reported it (conditions.model_identity), and
do not keep how a plan ended, so their plan ends read `not_recorded`. Legacy v1 records are skipped.
A round found in several inputs (overlapping packages) is counted once, from its fullest copy.
For each model it counts:

- unsure: how far apart a decision model put its top two options (margin = first minus second
  probability, over the options that were offered). Chat models report no probabilities.
- replaced: Jeff's actions that its own next choice replaced before they were done (the engine's
  `interrupted` event followed at once by Jeff's next `action_start`). Being knocked off by a dash
  is counted apart; that was not Jeff's choice.
- back_and_forth: A -> B -> A, where Jeff replaced an action at target A with one at B and that
  one again with an action at A.
- undone: Jeff's finished steps that the next one undid: put_then_taken_back (he put an item on a station
  and his next finished step, within --put-back game seconds, took it back from there; or dropped it and
  his next step picked an item up from the floor) and walk_round_trips (three finished walks in a row,
  go A -> go B -> go A), with walks_share, the share of his finished steps that were only walks;
  round_trip_routes names the most common pairs of stations those round trips went between, and
  walked_to the stations his finished walks most often went to (station ids of the level map).
- plan (rounds with Jeff's plan on, plan-v2): plans set (a request carrying a plan it had not
  carried before), how they ended, how many steps they had and how long they held, and how often
  Jeff chose wait with a plan held and without one in the same rounds. Rounds under the earlier plan
  rules (plan-v1, parts held for a fixed time) count only as `older_rules_rounds`.
  `unsure_with_plan` counts the decisions that were unsure (first margin) while a plan had held
  for more than --plan-age seconds: the trigger proposed for the third tier, here only counted.
- step_gaps: how long Jeff stood between steps, in wall seconds, from the end of a step (action_done)
  to the start of his next (action_start), grouped by the round's request policy:
  `ask_on_step_end` (ai_ask_on_step_end on) or `min_interval_only` (off, or a record from before the
  switch existed). Each gap is split into waiting_to_ask (until the first request after the step),
  answers_before_the_step (earlier answers that started nothing: a wait, a rejected or a discarded
  reply) and reply (the request whose answer started the next step, until that answer). The answer
  that starts a step is found by its action_id, since research records log the step's start before
  that answer and local journals after it. Gaps with a pause, and rounds without wall times, are left out.

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
from harness import PLAN_RULES_VERSION  # noqa: E402
from research_record import SCHEMA as RECORD_SCHEMA  # noqa: E402

VERSION = 'decision-stats-6'
MARGINS = (0.05, 0.1)
PLAN_AGE = 5.0
PUT_BACK = 10.0
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


def record_rows(record):
    """One research record as journal rows, with the fields add_round reads."""
    conditions = record.get('conditions') or {}
    identity = conditions.get('model_identity') or {}
    model = identity.get('model_id') or identity.get('provider') or 'not reported'
    events = record.get('events') or []
    policy = conditions.get('request_policy') or {}
    rows = [{'kind': 'start', 'jeff_plan': conditions.get('jeff_plan'), 'game_time_ms': 0, 'round_id': record.get('round_id'),
             'ask_on_step_end': policy.get('ai_ask_on_step_end') is True}]
    previous = None     # the plan the previous request carried
    for e in events:
        p, at = e.get('payload') or {}, {'game_time_ms': e.get('game_time_ms'), 'wall_ms': e.get('elapsed_wall_ms')}
        if e['type'] == 'ai_request':
            plan = p.get('jeff_plan')
            current = (plan or {}).get('current')
            ended = 'not_recorded' if previous and (not current or current['set_at'] != previous['set_at']) else None
            rows.append({'kind': 'ai_request', 'request_id': e.get('request_id'), 'candidates': p.get('candidates'),
                         'jeff_plan': plan, **({'plan_ended': ended} if ended else {}), **at})
            previous = current
        elif e['type'] == 'ai_response':
            choice = p.get('choice') or {}
            chef = {'target': choice.get('target'), 'action_kind': choice.get('kind')}
            rows.append({'kind': 'ai_response', 'request_id': e.get('request_id'), 'model': model, 'choice': choice.get('key'),
                         'probabilities': p.get('probabilities'), 'applied': p.get('applied'), 'fresh': p.get('fresh'),
                         'action_id': e.get('action_id'), 'current_state': {'chefs': {'jeff': chef}}, **at})
        elif e['type'] in ('action_start', 'action_done', 'interrupted', 'knocked'):
            rows.append({'kind': e['type'], 'actor': e.get('actor_id'), 'action_id': e.get('action_id'),
                         'action': (p.get('action') or {}).get('key'), **at})
        elif e['type'] in ('pause', 'resume'):
            rows.append({'kind': e['type'], **at})
    rows.append({'kind': 'end', 'game_time_ms': round((record.get('duration') or 0) * 1000)})
    return rows


def sources(path):
    """(rounds as journal rows, unreadable journal lines, skipped records) from one input file."""
    path = Path(path)
    if path.suffix == '.zip':
        import zipfile
        from scripts.research_export import verify_package
        manifest = verify_package(path)
        rounds, skipped = [], 0
        with zipfile.ZipFile(path) as archive:
            for source in manifest['sources']:
                prefix = source['source_ref'] + '/'
                if prefix + 'metadata.json' not in archive.namelist():
                    skipped += 1        # legacy v1
                    continue
                record = json.loads(archive.read(prefix + 'metadata.json'))
                record['events'] = [json.loads(line) for line in archive.read(prefix + 'events.jsonl').splitlines() if line]
                rounds.append(record_rows(record))
        return rounds, 0, skipped
    if path.suffix == '.json':
        data = json.loads(path.read_text(encoding='utf-8'))
        record = data.get('record', data) if isinstance(data, dict) else None
        if not isinstance(record, dict) or record.get('schema') != RECORD_SCHEMA:
            return [], 0, 1
        return [record_rows(record)], 0, 0
    rounds, unreadable = read_rounds(path)
    return rounds, unreadable, 0


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
            'plan_rounds': 0, 'plan_older_rounds': 0, 'plans_set': 0, 'plan_ends': Counter(), 'holds': [], 'plan_steps': [],
            'held_decisions': 0, 'held_waits': 0, 'free_decisions': 0, 'free_waits': 0, 'unsure_with_plan': 0,
            'gaps': {}, 'done': 0, 'walks_done': 0, 'put_then_taken_back': 0, 'walk_round_trips': 0,
            'round_trip_routes': Counter(), 'walked_to': Counter()}


def undone(rows, m, put_back=PUT_BACK):
    """Jeff's finished steps that his next ones undid (see the module notes)."""
    done = [r for r in rows if r.get('actor') == 'jeff' and r.get('kind') == 'action_done' and isinstance(r.get('action'), str)]
    m['done'] += len(done)
    m['walks_done'] += sum(r['action'].startswith('go ') for r in done)
    m['walked_to'].update(r['action'][3:] for r in done if r['action'].startswith('go '))
    for a, b in zip(done, done[1:]):
        ta, tb = game_time(a), game_time(b)
        if ta is None or tb is None or tb - ta > put_back:
            continue
        put, take = a['action'], b['action']
        m['put_then_taken_back'] += ((put.startswith('put ') and take == 'take ' + put[4:])
                                     or (put == 'drop' and take.startswith('pickup ')))
    for a, b, c in zip(done, done[1:], done[2:]):
        if all(x['action'].startswith('go ') for x in (a, b, c)) and a['action'] == c['action'] != b['action']:
            m['walk_round_trips'] += 1
            m['round_trip_routes']['/'.join(sorted((a['action'][3:], b['action'][3:])))] += 1


def add_round(rows, models, margins=MARGINS, plan_age=PLAN_AGE, put_back=PUT_BACK):
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
    older = plan_on and (rows[0].get('jeff_plan') or {}).get('rules_version', PLAN_RULES_VERSION) != PLAN_RULES_VERSION
    plan_on = plan_on and not older
    m['plan_older_rounds'] += older
    if plan_on:
        m['plan_rounds'] += 1
    holding = None      # the plan the previous request carried; a plan still held at closing is not counted
    for request in sorted(requests.values(), key=lambda r: r.get('request_id') or 0) if plan_on else ():
        current = (request.get('jeff_plan') or {}).get('current')
        if request.get('plan_ended'):
            m['plan_ends'][request['plan_ended']] += 1
            if holding and game_time(request) is not None:
                m['holds'].append(round(game_time(request) - holding['set_at'], 3))
        if current and (not holding or current['set_at'] != holding['set_at']):
            m['plans_set'] += 1
            m['plan_steps'].append(len(current['steps']))
        holding = current
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
        current = ((request or {}).get('jeff_plan') or {}).get('current') if plan_on else None
        if plan_on and request is not None:
            held = 'held' if current else 'free'
            model[held + '_decisions'] += 1
            model[held + '_waits'] += choice == 'wait'
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
        state = response.get('current_state')
        if response.get('applied') and response.get('action_id') is not None and choice not in NON_ACTIONS:
            target = jeff(state).get('target')
            by_action[response['action_id']] = (model, target if target is not None else choice)
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
    step_gaps(rows, m)
    undone(rows, m, put_back)
    return main


def wall(row):
    """Wall seconds since the round started: research records and journals both carry elapsed_wall_ms."""
    value = row.get('wall_ms', row.get('elapsed_wall_ms'))
    return value / 1000 if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def request_policy(rows):
    start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
    on = start.get('ask_on_step_end')
    if on is None:
        on = (start.get('config') or {}).get('ai_ask_on_step_end')
    return 'ask_on_step_end' if on is True else 'min_interval_only'


def step_gaps(rows, m):
    """From the end of each of Jeff's steps to the start of his next, in wall seconds (see the module notes)."""
    timed = [wall(r) for r in rows if wall(r) is not None]
    if not timed:
        return
    g = m['gaps'].setdefault(request_policy(rows), {'rounds': 0, 'wall_seconds': 0.0, 'total': [], 'waiting_to_ask': [],
                                                    'answers_before_the_step': [], 'reply': [], 'with_discarded': 0,
                                                    'unexplained': 0})
    paused, since = 0.0, None
    for r in rows:
        if r.get('kind') == 'pause' and wall(r) is not None:
            since = wall(r)
        elif r.get('kind') == 'resume' and since is not None and wall(r) is not None:
            paused, since = paused + max(0.0, wall(r) - since), None
    if since is not None:       # the round closed while paused
        paused += max(0.0, max(timed) - since)
    g['rounds'] += 1
    g['wall_seconds'] += max(0.0, max(timed) - min(timed) - paused)
    requests = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_request' and r.get('request_id') is not None}
    starters = {r['action_id']: r for r in rows if r.get('kind') == 'ai_response' and r.get('applied')
                and r.get('action_id') is not None}
    for i, done in enumerate(rows):
        if done.get('kind') != 'action_done' or done.get('actor') != 'jeff' or wall(done) is None:
            continue
        # A local journal writes a tick's engine events after that tick's request and answers: the
        # request sent as the step ended sits just above its action_done, at a game time no earlier.
        ended, j = game_time(done), i
        while ended is not None and j > 0 and game_time(rows[j - 1]) is not None and game_time(rows[j - 1]) >= ended \
                and rows[j - 1].get('kind') in ('ai_request', 'ai_response'):
            j -= 1
        first, discarded, start = None, 0, None
        for later in rows[j:i] + rows[i + 1:]:
            kind = later.get('kind')
            if kind in ('pause', 'end', 'round_end', 'context_closed'):
                break
            if kind == 'action_start' and later.get('actor') == 'jeff':
                start = later
                break
            if kind == 'ai_request' and first is None:
                first = wall(later)
            elif kind == 'ai_response' and not later.get('fresh'):
                discarded += 1
        if start is None or wall(start) is None:
            continue
        t0 = wall(done)
        g['total'].append(wall(start) - t0)
        g['with_discarded'] += discarded > 0
        answer = starters.get(start.get('action_id'))
        request = requests.get((answer or {}).get('request_id'))
        # Sent before the step ended (by game time; wall times of one tick follow the journal's write order).
        before = (game_time(request) < ended if game_time(request) is not None and ended is not None
                  else wall(request) is not None and wall(request) < t0) if request else True
        if answer is None or request is None or wall(answer) is None or wall(request) is None or before:
            g['unexplained'] += 1
            continue
        sent = wall(request)
        first = sent if first is None else min(first, sent)
        g['waiting_to_ask'].append(max(0.0, first - t0))
        g['answers_before_the_step'].append(max(0.0, sent - first))
        g['reply'].append(max(0.0, wall(answer) - sent))


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
    if m['done']:
        out['undone'] = {'finished_steps': m['done'], 'walks_share': share(m['walks_done'], m['done']),
                         'put_then_taken_back': m['put_then_taken_back'],
                         'put_then_taken_back_per_game_minute': per_minute(m['put_then_taken_back'], minutes),
                         'walk_round_trips': m['walk_round_trips'],
                         'walk_round_trips_per_game_minute': per_minute(m['walk_round_trips'], minutes),
                         'round_trip_routes': dict(m['round_trip_routes'].most_common(8)),
                         'walked_to': dict(m['walked_to'].most_common(8))}
    if m['plan_rounds'] or m['plan_older_rounds']:
        out['plan'] = {'rounds': m['plan_rounds'], 'older_rules_rounds': m['plan_older_rounds'], 'set': m['plans_set'],
                       'ended': dict(m['plan_ends']),
                       'median_steps': median(m['plan_steps']) if m['plan_steps'] else None,
                       'median_hold_seconds': round(median(m['holds']), 2) if m['holds'] else None,
                       'decisions_with_plan': m['held_decisions'], 'wait_share_with_plan': share(m['held_waits'], m['held_decisions']),
                       'decisions_without_plan': m['free_decisions'], 'wait_share_without_plan': share(m['free_waits'], m['free_decisions']),
                       'unsure_with_plan': m['unsure_with_plan']}
    if m['gaps']:
        out['step_gaps'] = {policy: gap_summary(g) for policy, g in sorted(m['gaps'].items())}
    return out


def spread(values):
    if not values:
        return None
    values = sorted(values)
    pick = lambda f: values[min(len(values) - 1, int(f * len(values)))]
    return {'median': round(median(values), 2), 'mean': round(sum(values) / len(values), 2),
            'p75': round(pick(.75), 2), 'p90': round(pick(.9), 2)}


def gap_summary(g):
    n = len(g['total'])
    return {'rounds': g['rounds'], 'gaps': n, 'total': spread(g['total']),
            'waiting_to_ask': spread(g['waiting_to_ask']), 'answers_before_the_step': spread(g['answers_before_the_step']),
            'reply': spread(g['reply']), 'split_unknown': g['unexplained'],
            'with_discarded_reply_share': share(g['with_discarded'], n),
            'seconds_per_round': round(sum(g['total']) / g['rounds'], 1) if g['rounds'] else None,
            'share_of_round_wall_time': share(sum(g['total']), g['wall_seconds'])}


def report(paths, margins=MARGINS, plan_age=PLAN_AGE, put_back=PUT_BACK):
    files = []
    for path in map(Path, paths):
        files += (sorted(p for pattern in ('*.jsonl', '*.cjresearch.zip', '*.json') for p in path.glob(pattern))
                  if path.is_dir() else [path])
    models = defaultdict(new_model)
    counted = skipped = unreadable = unsupported = duplicates = 0
    refused, journals, records = {}, [], {}
    for path in files:
        try:
            rounds, bad, legacy = sources(path)
        except (ValueError, KeyError, OSError) as error:   # an expired or damaged package, an unreadable record
            refused[path.name] = str(error)   # the name only: folders can be private
            continue
        unreadable += bad
        unsupported += legacy
        for rows in rounds:
            identifier = rows[0].get('round_id') if rows else None
            if identifier is None:
                journals.append(rows)
            elif identifier in records:
                # Overlapping packages hold one round twice; count it once, from its fullest copy.
                duplicates += 1
                if len(rows) > len(records[identifier]):
                    records[identifier] = rows
            else:
                records[identifier] = rows
    for rows in journals + list(records.values()):
        if add_round(rows, models, margins, plan_age, put_back) is None:
            skipped += 1
        else:
            counted += 1
    return {'version': VERSION, 'files': len(files), 'refused_files': refused, 'rounds': counted,
            'duplicate_rounds_dropped': duplicates,
            'rounds_without_model_answers': skipped, 'unsupported_records': unsupported,
            'unreadable_lines': unreadable, 'margins': list(margins), 'plan_age_seconds': plan_age, 'put_back_seconds': put_back,
            'models': {name: summary(m, margins) for name, m in sorted(models.items()) if m['decisions']}}


def main(argv=None):
    parser = argparse.ArgumentParser(description="How Jeff decided, per model, from round logs or research data (record only).")
    parser.add_argument('paths', nargs='+', help='journals (logs/), research packages (*.cjresearch.zip), record files (*.json) or folders of them')
    parser.add_argument('--margins', type=float, nargs='+', default=list(MARGINS), help='unsure below these margins')
    parser.add_argument('--plan-age', type=float, default=PLAN_AGE, help='seconds a plan has held before unsure counts')
    parser.add_argument('--put-back', type=float, default=PUT_BACK, help='game seconds within which a take undoes a put')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    result = report(args.paths, tuple(sorted(args.margins)), args.plan_age, args.put_back)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
