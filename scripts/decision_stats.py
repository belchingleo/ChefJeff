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
  rules (plan-v1, parts held for a fixed time) count only as `older_rules_rounds`, and rounds with the
  two-step rolling intent (plan mode `rolling`) only as `rolling_rounds`: compare them with the
  undone counts of separate runs over those rounds' files.
  `unsure_with_plan` counts the decisions that were unsure (first margin) while a plan had held
  for more than --plan-age seconds: the trigger proposed for the third tier, here only counted.
- step_gaps: how long Jeff stood between steps, in wall seconds, from the end of a step (action_done)
  to the start of his next (action_start), grouped by the round's request policy (`ask_ahead` when that trial
  was on: an answer asked ahead was requested before the step ended, so its waiting_to_ask is negative, and
  `asked_ahead` counts those gaps):
  `ask_on_step_end` (ai_ask_on_step_end on) or `min_interval_only` (off, or a record from before the
  switch existed). Each gap is split into waiting_to_ask (until the first request after the step),
  answers_before_the_step (earlier answers that started nothing: a wait, a rejected or a discarded
  reply) and reply (the request whose answer started the next step, until that answer). The answer
  that starts a step is found by its action_id, since research records log the step's start before
  that answer and local journals after it. Gaps with a pause, and rounds without wall times, are left out.
- uncertainty (decision-stats-18): 95% intervals for what a comparison is read from: the shares of rounds that
  reached the target, of decisions that chose the top option and of steps replaced by Jeff's own next choice
  (Wilson), and the mean money, cooperation gain and Jeff's standard-time share per round and the median step gap
  per request policy (seeded bootstrap, research_stats.py). Every other field is as before.
- one_press: rounds with a one-press switch on (one_press.py) are counted apart, under the model's name
  followed by ` [one-press]`, so every count above compares them with the same model's rounds with both
  switches off; `one_press_rounds` at the top says how many there were. Their `one_press` section gives
  the switches the rounds had, the version (`one-press-v1`: put then take and wash from the plate return;
  `one-press-v2` adds put then chop and put then wash; `one-press-v3` gives those two the seconds of work
  left, as the engine's own labels do), how often each kind of one-press option was offered and chosen, how many choices
  started, how often put_where fell back to the first listed put place, and how the chains ended
  (finished, step_not_possible, replaced, ...; research records do not keep the end, so it reads
  `not_recorded` there). `swap_backs` counts put-then-take choices that, within --put-back game seconds of
  the one before, took from the station where that one had put the held item down (he takes back what he
  just set aside), and `full_swaps` those of them that also put it down where the one before had taken
  from, so the two items end up where they were. `take_or_chop` takes the answered requests that offered
  both put then take and put then chop on one board and counts whether Jeff took the item off it, chopped
  it, or chose something else.

- outcomes: the rounds' results as the game wrote them at the end (round_summary.py, the same numbers as
  the results page): how many reached the goal, net revenue per round in the order read and its mean,
  orders served, expired and left at closing, burns and fires, model errors (requests that failed) and
  model calls. `work` adds, per chef, the completed work of each kind (fetch, chop, heat, assemble,
  serve, wash, collect_plates, pass, extinguish, discard) with Jeff's share, and `contribution` the
  per-round means of each chef's share of standard time, delay seconds and idle seconds, and `wasted` each
  chef's wasted actions (loops, unused work, support that went unused) and harmful ones by reason, which
  the summary keeps but the results page does not show. Local journals
  carry the summary in their last row; a research record is replayed from its engine inputs to rebuild
  it (a record without them counts in `rounds_without_summary`). `cooperation_gain`, labelled "relative to
  the solo script baseline", is each round's net revenue minus the median income of the solo reference chef
  (one scripted chef, the other idle) over the calibration run set, taken from
  docs/architecture/reports/calibration.json for the entry made for the round's exact config hash; a round
  on a configuration the report has no entry for counts in `rounds_without_baseline`. It is measured
  against a script, not against the same player alone.
- puts: where each chef's finished put-downs went, by kind of place (counter, board, supply top, floor, ...;
  from the station types of the round's map), and how many items each picked up from the floor. Some are
  steps of the dish rather than setting an item aside: stove (food into a pan), pan_to_stove (the held pan
  put back), sink (a dirty plate in) and tool_rack (the extinguisher back). With
  one-press, `one_press.put_where_places` gives the same for the first step of the one-press choices that
  put something down (the place put_where chose), so the two show whether one-press changes where Jeff
  puts things.

With --by-round the report also lists every counted round on its own (`by_round`, ordered by start time):
its name (the journal file, or the record's round id), start time, level, group, one-press version, the
outcome numbers above, walk round trips, each chef's work by kind and, with one-press, the options chosen,
full swaps and take_or_chop, computed exactly as for the groups.

Each by_round row also names what tells rounds apart: the level, the config hash (`config`, its first 8
hex digits; it changes with any change of rules, timings or level), the game speed and the version of
Jeff's rule text. --split level,config,speed,rules counts the groups apart by those too (the group name
gains them, e.g. "jev-1.14.0 [one-press] · level-2 · cfg 1a2b3c4d"), so rounds before and after a
change of timings are not added together; by default groups are by model and one-press only.
--since and --until keep only rounds started on those days (YYYY-MM-DD, local time of the round).

Rates are per game minute. A round counts for the model that answered most of its requests.

The report names models: keep it private like logs/, and do not publish per-model results.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
import re
from pathlib import Path
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import PLAN_RULES_VERSION  # noqa: E402
import research_stats  # noqa: E402
from research_record import SCHEMA as RECORD_SCHEMA  # noqa: E402
from round_summary import CATEGORIES, CHEFS  # noqa: E402

WORK_CATEGORIES = tuple(name for name, _ in CATEGORIES)

VERSION = 'decision-stats-18'
# The solo baseline of the cooperation gain: the median income of the solo reference chef over the calibration
# run set (scripts/reference_sweep.py --calibrate), for the level configuration each entry was made for.
CALIBRATION_REPORT = Path(__file__).resolve().parents[1] / 'docs' / 'architecture' / 'reports' / 'calibration.json'
GAIN_BASELINE = 'relative to the solo script baseline'
_BASELINES = {}


def solo_baselines(path=None):
    """config hash -> median solo reference income, from the calibration report (entries with a hash only)."""
    path = Path(path or CALIBRATION_REPORT)
    if path not in _BASELINES:
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            report = {}
        _BASELINES[path] = {row['config_hash']: median(run['solo'] for run in row['runs'])
                            for row in report.get('levels', []) if row.get('config_hash') and row.get('runs')}
    return _BASELINES[path]
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
             'ask_on_step_end': policy.get('ai_ask_on_step_end') is True, 'wall_time': record.get('started_at'),
             'ask_ahead': policy.get('ask_ahead') is True,
             'config_hash': record.get('config_hash'), 'speed': record.get('speed'), 'rules_version': conditions.get('rules_version'),
             **({'one_press': conditions['one_press']} if conditions.get('one_press') else {})}]
    previous = None     # the plan the previous request carried
    for e in events:
        p, at = e.get('payload') or {}, {'game_time_ms': e.get('game_time_ms'), 'wall_ms': e.get('elapsed_wall_ms')}
        if e['type'] == 'ai_request':
            plan = p.get('jeff_plan')
            current = (plan or {}).get('current')
            ended = 'not_recorded' if previous and (not current or current['set_at'] != previous['set_at']) else None
            rows.append({'kind': 'ai_request', 'request_id': e.get('request_id'), 'candidates': p.get('candidates'),
                         'jeff_plan': plan, **({'plan_ended': ended} if ended else {}),
                         **({'one_press': p['one_press']} if p.get('one_press') else {}),
                         **({'ask_ahead': p['ask_ahead']} if p.get('ask_ahead') else {}), **at})
            previous = current
        elif e['type'] == 'ai_response':
            choice = p.get('choice') or {}
            chef = {'target': choice.get('target'), 'action_kind': choice.get('kind')}
            rows.append({'kind': 'ai_response', 'request_id': e.get('request_id'), 'model': model, 'choice': choice.get('key'),
                         'probabilities': p.get('probabilities'), 'applied': p.get('applied'), 'fresh': p.get('fresh'),
                         'action_id': e.get('action_id'), 'current_state': {'chefs': {'jeff': chef}},
                         **({'one_press': {'first': (p['one_press_start'].get('first') or {}).get('key'),
                                           'fallback': p['one_press_start'].get('fallback'), 'ends': 'not_recorded'}}
                            if p.get('one_press_start') else {}), **at})
        elif e['type'] in ('action_start', 'action_done', 'interrupted', 'knocked'):
            rows.append({'kind': e['type'], 'actor': e.get('actor_id'), 'action_id': e.get('action_id'),
                         'action': (p.get('action') or {}).get('key'), **at})
        elif e['type'] in ('pause', 'resume'):
            rows.append({'kind': e['type'], **at})
        elif e['type'] == 'ai_error':
            rows.append({'kind': 'ai_error', 'request_id': e.get('request_id'), **at})
    rows.append({'kind': 'end', 'game_time_ms': round((record.get('duration') or 0) * 1000), **rebuilt_summary(record)})
    return rows


def rebuilt_summary(record):
    """The round summary and result a local journal writes at the end, rebuilt by replaying the record; {} without inputs."""
    try:
        import research_replay
        from round_summary import round_summary
        k = research_replay.rebuild(record)
    except Exception:       # no engine inputs, or a record this checkout cannot replay
        return {}
    stations = k.snapshot().get('stations') or {}
    return {'round_summary': round_summary(k), 'result': k.result(),
            'stations': {key: {'type': value.get('type')} for key, value in stations.items() if isinstance(value, dict)}}


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
            'plan_rounds': 0, 'plan_older_rounds': 0, 'plan_rolling_rounds': 0, 'plans_set': 0, 'plan_ends': Counter(), 'holds': [], 'plan_steps': [],
            'held_decisions': 0, 'held_waits': 0, 'free_decisions': 0, 'free_waits': 0, 'unsure_with_plan': 0,
            'gaps': {}, 'done': 0, 'walks_done': 0, 'put_then_taken_back': 0, 'walk_round_trips': 0,
            'round_trip_routes': Counter(), 'walked_to': Counter(),
            'one_press_rounds': 0, 'one_press_switches': Counter(), 'one_press_offered': Counter(),
            'one_press_chosen': Counter(), 'one_press_started': 0, 'one_press_fallback': 0, 'one_press_ends': Counter(),
            'one_press_swap_backs': 0, 'one_press_full_swaps': 0, 'one_press_versions': Counter(),
            'one_press_take_or_chop': Counter(),
            'summary_rounds': 0, 'no_summary_rounds': 0, 'reached_target': 0, 'money': [], 'outcome': Counter(),
            'gains': [], 'no_baseline_rounds': 0,
            'model_errors': 0, 'model_calls': 0, 'work': defaultdict(Counter), 'shares': defaultdict(list),
            'wasted': defaultdict(Counter), 'puts': defaultdict(Counter), 'put_where_places': Counter()}


# Kinds of place for a put-down, by the station type of the map (anything else keeps its type).
PLACE_KINDS = {'counter': 'counter', 'board': 'board', 'ingredient_source': 'supply'}


def station_types(rows):
    """Station id -> type, from the round's start state (journals) or the replayed kitchen (records)."""
    start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
    end = next((r for r in reversed(rows) if r.get('kind') == 'end'), {})
    stations = (start.get('state') or {}).get('stations') or end.get('stations') or {}
    return {key: value.get('type') for key, value in stations.items() if isinstance(value, dict)}


def place_kind(key, types):
    """Where a put-down action puts the held item: floor for drop, else the kind of station; None for other actions."""
    if key == 'drop':
        return 'floor'
    if isinstance(key, str) and key.startswith('put pot '):
        return 'pan_to_stove'           # return_pot: the held pan put back on a stove
    if isinstance(key, str) and key.startswith('put ') and not key.startswith(('put then ',)):
        kind = types.get(key[4:])
        return PLACE_KINDS.get(kind, kind or 'unknown')
    return None


def puts(rows, m):
    """Each chef's finished put-downs by kind of place, and pick-ups from the floor."""
    types = station_types(rows)
    for r in rows:
        if r.get('kind') != 'action_done' or r.get('actor') not in CHEFS or not isinstance(r.get('action'), str):
            continue
        place = place_kind(r['action'], types)
        if place:
            m['puts'][r['actor']][place] += 1
        elif r['action'].startswith('pickup '):
            m['puts'][r['actor']]['picked_up_from_floor'] += 1


BURNS_AND_FIRES = re.compile(r'糊锅 (\d+)，着火 (\d+)')


def outcomes(rows, m):
    """Add the round's end-of-round summary (results, work per chef, contribution) and its model errors."""
    m['model_errors'] += sum(r.get('kind') == 'ai_error' for r in rows)
    end = next((r for r in reversed(rows) if r.get('kind') == 'end'), {})
    summary = end.get('round_summary')
    if not isinstance(summary, dict) or not isinstance(summary.get('result'), dict):
        m['no_summary_rounds'] += 1
        return
    m['summary_rounds'] += 1
    result = summary['result']
    m['reached_target'] += result.get('reached_target') is True
    if isinstance(result.get('money'), (int, float)):
        m['money'].append(result['money'])
        # Cooperation gain: net revenue minus the solo reference chef's median on this exact level configuration.
        start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
        baseline = solo_baselines().get(start.get('config_hash') or (start.get('state') or {}).get('config_hash'))
        if baseline is None:
            m['no_baseline_rounds'] += 1
        else:
            m['gains'].append(round(result['money'] - baseline, 1))
    m['outcome'].update({key: result.get(key) or 0 for key in ('served', 'expired', 'unresolved_at_close')})
    found = BURNS_AND_FIRES.search(str(end.get('result') or ''))
    if found:
        m['outcome'].update({'burns': int(found.group(1)), 'fires': int(found.group(2))})
    else:
        m['outcome']['burns_fires_unknown'] += 1
    calls = end.get('ai_calls')
    m['model_calls'] += calls if type(calls) is int else sum(r.get('kind') == 'ai_request' for r in rows)
    for row in summary.get('rows') or ():
        m['work'][row['category']].update({who: n for who, n in (row.get('counts') or {}).items() if who in CHEFS})
    contribution = summary.get('contribution') or {}
    for key, value in (('standard_share', (contribution.get('standard') or {}).get('share')),
                       ('delay_seconds', contribution.get('delay_seconds')), ('idle_seconds', contribution.get('idle_seconds'))):
        for who in CHEFS:
            if isinstance(value, dict) and isinstance(value.get(who), (int, float)):
                m['shares'][f'{key}:{who}'].append(value[who])
    hidden = summary.get('not_displayed') or {}
    for group in ('wasted', 'harmful'):
        for who, reasons in (hidden.get(group) or {}).items():
            if who in CHEFS and isinstance(reasons, dict):
                m['wasted'][who].update({(f'harmful:{r}' if group == 'harmful' else r): n for r, n in reasons.items()
                                         if type(n) is int})


# One-press option keys (one_press.py) by their kind, and the switches that offer them.
ONE_PRESS_KEYS = (('put_then_take', 'put then take '), ('put_then_chop', 'put then chop '), ('put_then_wash', 'put then wash '),
                  ('wash_from_returns', 'wash from '))
ONE_PRESS_SWITCHES = ('put_then_take', 'wash_from_returns')
ONE_PRESS_SUFFIX = ' [one-press]'


def one_press_kind(key):
    return next((name for name, prefix in ONE_PRESS_KEYS if isinstance(key, str) and key.startswith(prefix)), None)


def one_press_switches(rows):
    """The one-press switches a round had on (its start row, else any request's flags), or None with both off."""
    start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
    flags = start.get('one_press') or next((r['one_press'] for r in rows if r.get('kind') == 'ai_request'
                                            and isinstance(r.get('one_press'), dict)), None)
    on = tuple(name for name in ONE_PRESS_SWITCHES if isinstance(flags, dict) and flags.get(name) is True)
    return on or None


def put_place(key):
    """The station a put action puts on, 'floor' for drop, else None."""
    return key[4:] if isinstance(key, str) and key.startswith('put ') else 'floor' if key == 'drop' else None


def one_press_counts(rows, requests, responses, m, put_back=PUT_BACK):
    """What one-press options a round offered, chose and started, how the chains ended, and the swaps back."""
    types = station_types(rows)
    for request in requests.values():
        m['one_press_offered'].update({kind for kind in map(one_press_kind, offered(request) or ()) if kind})
    for response in responses:
        kind = one_press_kind(response.get('choice'))
        if kind:
            m['one_press_chosen'][kind] += 1
        pressed = response.get('one_press')
        if isinstance(pressed, dict):
            place = place_kind(pressed.get('first'), types)
            if place:
                m['put_where_places'][place] += 1
            m['one_press_started'] += 1
            m['one_press_fallback'] += pressed.get('fallback') is True
            if pressed.get('ends') == 'not_recorded':
                m['one_press_ends']['not_recorded'] += 1
    m['one_press_ends'].update(str(r.get('reason')) for r in rows if r.get('kind') == 'one_press_end')
    # Requests offering both put then take and put then chop on one board: what Jeff answered.
    take, chop = dict(ONE_PRESS_KEYS)['put_then_take'], dict(ONE_PRESS_KEYS)['put_then_chop']
    answers = {r.get('request_id'): r.get('choice') for r in responses if r.get('request_id') is not None}
    for request_id, request in requests.items():
        keys = set(offered(request) or ())
        boards = {k[len(chop):] for k in keys if k.startswith(chop) and take + k[len(chop):] in keys}
        if not boards or request_id not in answers:
            continue
        choice = answers[request_id]
        m['one_press_take_or_chop']['took' if choice in {take + b for b in boards} else
                                    'chopped' if choice in {chop + b for b in boards} else 'other'] += 1
    # Started put-then-take choices in order: (game time, where the held item went, the station taken from).
    prefix = dict(ONE_PRESS_KEYS)['put_then_take']
    chains = [(game_time(r), put_place(r['one_press'].get('first')), r['choice'][len(prefix):]) for r in responses
              if isinstance(r.get('one_press'), dict) and one_press_kind(r.get('choice')) == 'put_then_take']
    for (t0, put0, took0), (t1, put1, took1) in zip(chains, chains[1:]):
        if t0 is None or t1 is None or t1 - t0 > put_back or put0 is None or took1 != put0:
            continue
        m['one_press_swap_backs'] += 1
        m['one_press_full_swaps'] += put1 == took0


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


SPLITS = ('level', 'config', 'speed', 'rules')


def round_meta(rows):
    """What tells a round's conditions apart: level, config hash, speed, Jeff's rule text version and start day."""
    start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
    end = next((r for r in reversed(rows) if r.get('kind') == 'end'), {})
    state = start.get('state') or {}
    payload = next(((r.get('payload') or {}).get('state') or {} for r in rows
                    if r.get('kind') == 'ai_request' and isinstance(r.get('payload'), dict)), {})
    config = start.get('config_hash') or state.get('config_hash')
    return {'level': (end.get('round_summary') or {}).get('level_id') or state.get('level_id')
                     or (state.get('kitchen') or {}).get('level_id'),
            'config': str(config).removeprefix('sha256:')[:8] if config else None,
            'speed': start.get('speed'),
            'rules': start.get('rules_version') or payload.get('rules_version'),
            'day': str(start.get('wall_time') or '')[:10] or None}


def split_suffix(rows, split):
    """The group name's tail for --split: the chosen conditions of this round."""
    if not split:
        return ''
    meta = round_meta(rows)
    label = {'level': lambda v: v, 'config': lambda v: f'cfg {v}', 'speed': lambda v: f'speed {v:g}' if isinstance(v, (int, float)) else f'speed {v}',
             'rules': lambda v: v}
    return ''.join(f' · {label[key](meta[key]) if meta[key] is not None else key + " unknown"}' for key in split)


def add_round(rows, models, margins=MARGINS, plan_age=PLAN_AGE, put_back=PUT_BACK, split=()):
    responses = [r for r in rows if r.get('kind') == 'ai_response']
    if not responses:
        return None
    requests = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_request'}
    switches = one_press_switches(rows)
    tail = split_suffix(rows, split)
    name = lambda response: str(response.get('model') or 'unknown') + (ONE_PRESS_SUFFIX if switches else '') + tail
    main = Counter(map(name, responses)).most_common(1)[0][0]
    m = models[main]
    times = [t for t in map(game_time, rows) if t is not None]
    m['rounds'] += 1
    m['game_minutes'] += (max(times) if times else 0) / 60
    by_action = {}      # action_id -> (model, target)
    plan_on = bool(rows[0].get('jeff_plan')) or any(r.get('jeff_plan') for r in requests.values())
    condition = rows[0].get('jeff_plan') or {}
    rolling = plan_on and condition.get('mode') == 'rolling'
    older = plan_on and not rolling and condition.get('rules_version', PLAN_RULES_VERSION) != PLAN_RULES_VERSION
    plan_on = plan_on and not older and not rolling
    m['plan_older_rounds'] += older
    m['plan_rolling_rounds'] += rolling
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
        model = models[name(response)]
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
    if switches:
        m['one_press_rounds'] += 1
        m['one_press_switches']['+'.join(switches)] += 1
        start = rows[0] if rows[0].get('kind') == 'start' else {}
        m['one_press_versions'][str((start.get('one_press') or {}).get('version') or 'not_recorded')] += 1
        one_press_counts(rows, requests, responses, m, put_back)
    step_gaps(rows, m)
    undone(rows, m, put_back)
    outcomes(rows, m)
    puts(rows, m)
    return main


def wall(row):
    """Wall seconds since the round started: research records and journals both carry elapsed_wall_ms."""
    value = row.get('wall_ms', row.get('elapsed_wall_ms'))
    return value / 1000 if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def request_policy(rows):
    start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
    # ask_ahead (a trial on top of ask_on_step_end) is its own group: its requests may come before a step ends.
    if ((start.get('features') or {}).get('ask_ahead') or {}).get('on') is True or start.get('ask_ahead') is True:
        return 'ask_ahead'
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
                                                    'unexplained': 0, 'asked_ahead': 0})
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
        ahead = bool(request and request.get('ask_ahead'))       # asked ahead: sent before the step ended, by design
        if answer is None or request is None or wall(answer) is None or wall(request) is None or (before and not ahead):
            g['unexplained'] += 1
            continue
        sent = wall(request)
        g['asked_ahead'] += ahead
        if ahead:
            # Its wait to ask is negative: how long before the step ended it was sent.
            g['waiting_to_ask'].append(sent - t0)
            g['answers_before_the_step'].append(0.0)
            g['reply'].append(max(0.0, wall(answer) - sent))
            continue
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
    if m['plan_rounds'] or m['plan_older_rounds'] or m['plan_rolling_rounds']:
        out['plan'] = {'rounds': m['plan_rounds'], 'older_rules_rounds': m['plan_older_rounds'],
                       'rolling_rounds': m['plan_rolling_rounds'], 'set': m['plans_set'],
                       'ended': dict(m['plan_ends']),
                       'median_steps': median(m['plan_steps']) if m['plan_steps'] else None,
                       'median_hold_seconds': round(median(m['holds']), 2) if m['holds'] else None,
                       'decisions_with_plan': m['held_decisions'], 'wait_share_with_plan': share(m['held_waits'], m['held_decisions']),
                       'decisions_without_plan': m['free_decisions'], 'wait_share_without_plan': share(m['free_waits'], m['free_decisions']),
                       'unsure_with_plan': m['unsure_with_plan']}
    if m['one_press_rounds']:
        out['one_press'] = {'rounds': m['one_press_rounds'], 'switches': dict(m['one_press_switches']),
                            'versions': dict(m['one_press_versions']),
                            'offered_in_requests': dict(m['one_press_offered']), 'chosen': dict(m['one_press_chosen']),
                            'started': m['one_press_started'], 'put_where_fallback': m['one_press_fallback'],
                            'ended': dict(m['one_press_ends']), 'swap_backs': m['one_press_swap_backs'],
                            'full_swaps': m['one_press_full_swaps'],
                            'take_or_chop': {k: m['one_press_take_or_chop'][k] for k in ('took', 'chopped', 'other')},
                            'put_where_places': dict(m['put_where_places'].most_common())}
    if m['summary_rounds'] or m['no_summary_rounds']:
        n = m['summary_rounds']
        out['outcomes'] = {'rounds': n, 'rounds_without_summary': m['no_summary_rounds'],
                           'reached_target': m['reached_target'], 'money_per_round': m['money'],
                           'money_mean': round(sum(m['money']) / len(m['money']), 1) if m['money'] else None,
                           **{key: m['outcome'][key] for key in ('served', 'expired', 'unresolved_at_close', 'burns', 'fires')},
                           **({'burns_fires_unknown': m['outcome']['burns_fires_unknown']} if m['outcome']['burns_fires_unknown'] else {}),
                           'model_errors': m['model_errors'], 'model_calls': m['model_calls'],
                           'cooperation_gain': {'baseline': GAIN_BASELINE, 'rounds': len(m['gains']),
                                                'per_round': m['gains'],
                                                'mean': round(sum(m['gains']) / len(m['gains']), 1) if m['gains'] else None,
                                                'rounds_without_baseline': m['no_baseline_rounds']}}
        out['work'] = {category: {**{who: m['work'][category][who] for who in CHEFS},
                                  'jeff_share': share(m['work'][category]['jeff'], sum(m['work'][category].values()))}
                       for category in WORK_CATEGORIES if sum(m['work'][category].values())}
        out['contribution'] = {key: {who: round(sum(v) / len(v), 3) for who in CHEFS
                                     if (v := m['shares'].get(f'{key}:{who}'))}
                               for key in ('standard_share', 'delay_seconds', 'idle_seconds')
                               if any(m['shares'].get(f'{key}:{who}') for who in CHEFS)}
        out['wasted'] = {who: dict(sorted(m['wasted'][who].items())) for who in CHEFS if m['wasted'][who]}
    if any(m['puts'].values()):
        out['puts'] = {who: dict(m['puts'][who].most_common()) for who in CHEFS if m['puts'][who]}
    if m['gaps']:
        out['step_gaps'] = {policy: gap_summary(g) for policy, g in sorted(m['gaps'].items())}
    out['uncertainty'] = uncertainty(m)
    return out


def uncertainty(m):
    """95% intervals for the numbers a decision is read from: shares (Wilson) and per-round or per-gap means and
    medians (seeded bootstrap, research_stats). The fields above stay as they were; this only says how sure they are."""
    out = {'chose_the_top_option': research_stats.share(m['chose_top'], len(m['margins'])),
           'replaced_by_own_next_choice': research_stats.share(m['replaced'], m['started'])}
    if m['summary_rounds']:
        out['reached_target'] = research_stats.share(m['reached_target'], m['summary_rounds'])
        out['money_mean_ci95'] = research_stats.bootstrap(m['money'])
        out['cooperation_gain_mean_ci95'] = research_stats.bootstrap(m['gains'])
        jeff = m['shares'].get('standard_share:jeff')
        out['jeff_standard_share_mean_ci95'] = research_stats.bootstrap(jeff) if jeff else None
    if m['gaps']:
        out['step_gap_median_ci95'] = {policy: research_stats.bootstrap(g['total'], statistic=median)
                                       for policy, g in sorted(m['gaps'].items())}
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
            'reply': spread(g['reply']), 'split_unknown': g['unexplained'], 'asked_ahead': g.get('asked_ahead', 0),
            'with_discarded_reply_share': share(g['with_discarded'], n),
            'seconds_per_round': round(sum(g['total']) / g['rounds'], 1) if g['rounds'] else None,
            'share_of_round_wall_time': share(sum(g['total']), g['wall_seconds'])}


def round_row(label, rows, margins=MARGINS, plan_age=PLAN_AGE, put_back=PUT_BACK, split=()):
    """One round on its own: counted as a group of one, then the numbers that tell rounds apart."""
    alone = defaultdict(new_model)
    group = add_round(rows, alone, margins, plan_age, put_back, split)
    meta = round_meta(rows)
    s = summary(alone[group], margins)
    start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
    end = next((r for r in reversed(rows) if r.get('kind') == 'end'), {})
    outcome = s.get('outcomes') or {}
    pressed = s.get('one_press')
    return {'round': label, 'started': start.get('wall_time'), 'level': meta['level'], 'config': meta['config'],
            'speed': meta['speed'], 'rules': meta['rules'], 'group': group,
            'one_press': next(iter(pressed['versions']), None) if pressed else None,
            'game_minutes': s['game_minutes'],
            # Without an end-of-round summary (an unfinished journal, a record with no inputs) its numbers are unknown.
            'reached_target': bool(outcome['reached_target']) if outcome.get('rounds') else None,
            **{key: outcome.get(key) if outcome.get('rounds') else None
               for key in ('served', 'expired', 'unresolved_at_close', 'burns', 'fires', 'model_calls')},
            'model_errors': outcome.get('model_errors'),
            'money': (outcome.get('money_per_round') or [None])[0],
            'cooperation_gain': ((outcome.get('cooperation_gain') or {}).get('per_round') or [None])[0],
            'walk_round_trips': (s.get('undone') or {}).get('walk_round_trips'),
            'walks_share': (s.get('undone') or {}).get('walks_share'),
            'work': {category: {who: counts[who] for who in CHEFS} for category, counts in (s.get('work') or {}).items()},
            'puts': s.get('puts') or {},
            **({'one_press_chosen': pressed['chosen'], 'full_swaps': pressed['full_swaps'],
                'take_or_chop': pressed['take_or_chop'], 'put_where_places': pressed['put_where_places']} if pressed else {})}


def report(paths, margins=MARGINS, plan_age=PLAN_AGE, put_back=PUT_BACK, by_round=False, split=(), since=None, until=None):
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
        for index, rows in enumerate(rounds):
            identifier = rows[0].get('round_id') if rows else None
            if identifier is None:
                journals.append((path.stem if len(rounds) == 1 else f'{path.stem}#{index + 1}', rows))
            elif identifier in records:
                # Overlapping packages hold one round twice; count it once, from its fullest copy.
                duplicates += 1
                if len(rows) > len(records[identifier]):
                    records[identifier] = rows
            else:
                records[identifier] = rows
    detail, outside = [], 0
    for label, rows in journals + [(identifier, rows) for identifier, rows in records.items()]:
        day = round_meta(rows)['day']
        if (since and (not day or day < since)) or (until and (not day or day > until)):
            outside += 1
            continue
        if add_round(rows, models, margins, plan_age, put_back, split) is None:
            skipped += 1
            continue
        counted += 1
        if by_round:
            detail.append(round_row(label, rows, margins, plan_age, put_back, split))
    return {'version': VERSION, 'files': len(files), 'refused_files': refused, 'rounds': counted,
            'duplicate_rounds_dropped': duplicates,
            **({'rounds_outside_dates': outside, 'since': since, 'until': until} if since or until else {}),
            **({'split': list(split)} if split else {}),
            'rounds_without_model_answers': skipped, 'unsupported_records': unsupported,
            'unreadable_lines': unreadable, 'margins': list(margins), 'plan_age_seconds': plan_age, 'put_back_seconds': put_back,
            'one_press_rounds': sum(m['one_press_rounds'] for m in models.values()),
            'models': {name: summary(m, margins) for name, m in sorted(models.items()) if m['decisions']},
            **({'by_round': sorted(detail, key=lambda r: (str(r['started'] or ''), r['round']))} if by_round else {})}


def main(argv=None):
    parser = argparse.ArgumentParser(description="How Jeff decided, per model, from round logs or research data (record only).")
    parser.add_argument('paths', nargs='+', help='journals (logs/), research packages (*.cjresearch.zip), record files (*.json) or folders of them')
    parser.add_argument('--margins', type=float, nargs='+', default=list(MARGINS), help='unsure below these margins')
    parser.add_argument('--plan-age', type=float, default=PLAN_AGE, help='seconds a plan has held before unsure counts')
    parser.add_argument('--put-back', type=float, default=PUT_BACK, help='game seconds within which a take undoes a put')
    parser.add_argument('--by-round', action='store_true', help='also list every counted round on its own')
    parser.add_argument('--split', default='', help='also count groups apart by: ' + ', '.join(SPLITS) + ' (comma-separated)')
    parser.add_argument('--since', help='first day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--until', help='last day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    split = tuple(key for key in args.split.split(',') if key)
    if set(split) - set(SPLITS):
        parser.error('--split takes ' + ', '.join(SPLITS))
    result = report(args.paths, tuple(sorted(args.margins)), args.plan_age, args.put_back, args.by_round, split,
                    args.since, args.until)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
