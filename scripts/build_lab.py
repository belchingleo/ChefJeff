"""Build the lab's data (lab/data/): logged moments of real rounds, the exact request Jeff would be sent there under
each condition, rebuilt by the current code, and the answers models gave to exactly that request in recorded
re-asks. No model is called.

    python3 scripts/build_lab.py RUNS_DIR [--out lab/data]

RUNS_DIR holds re-ask runs: <name>.requests.json (moments with their requests per arm) and <name>.answers.jsonl
(one answer per line). A recorded answer is attached to a rebuilt request only when the request it was given is
byte-identical (sha256 of the canonical JSON) to the rebuilt one, so every answer the lab shows was given to the
request it shows. Conditions:

- today: today's request (every request part and the go note off);
- restructured: four request parts (place_names, timeline, links_on_options, rules_by_action) and the go note on;
- with_kitchen_view: the same with kitchen_view too, the local play set (with it Jev took a plate first at every
  level-5 opening and repeated undone steps far more often, but the user's level-4 rounds made more money).

Each service gets its own requests (its local play set: the features override with off_for read for it).
Writes data/index.json (moments, conditions, switches, results) and data/moments/<id>.json (requests and answers).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FOUR = {'place': True, 'timeline': True, 'links_on': True, 'rules': True}
FIVE = {**FOUR, 'view': True}
CONDITIONS = {'today': (None, False), 'restructured': (FOUR, True), 'with_kitchen_view': (FIVE, True)}
MODELS = {'jev': 'jev-latest', 'perplexity': 'pplx-decider-v1.3'}
# Recorded runs: file stem -> (service, {arm in that run: condition}, how its arm request is derived from the store).
RUNS = {
    'v4-jev': ('jev', {'A': 'today', 'V4G-K': 'restructured'}),
    'v4-perplexity': ('perplexity', {'A': 'today', 'V4G-K': 'restructured'}),
    'dishes-jev': ('jev', {'NODISH': 'with_kitchen_view'}), 'dishes-perplexity': ('perplexity', {'NODISH': 'with_kitchen_view'}),
    'loop': ('jev', {'A': 'today', 'V5G': 'with_kitchen_view'}), 'loopab': ('jev', {'A': 'today'}),
    'go': ('jev', {'A': 'today'}), 'fire-open': ('jev', {'A': 'today'}),
}


def measure(choice, moment, criteria):
    """What one answer counts toward: the step the moment calls for, a walk to the serving window, a plate first at
    the opening, the undo chosen in play."""
    label = criteria.get(choice, '').lower()
    out = {}
    if moment['steps']:
        out['step'] = choice in moment['steps']
    if 'go' in moment['labels']:
        out['go_serve'] = choice == 'go serve'
    if 'open' in moment['labels']:
        out['plate_first'] = label.startswith('take') and 'plate' in label
    if moment['played']:
        out['back_repeated'] = choice == moment['played']
    return out


def total(groups):
    """Sum of per-answer measures over the moments' answer lists: {measure: [hits, answers]} and the answer count."""
    out = {'answers': 0}
    for answers in groups:
        for m in answers:
            out['answers'] += 1
            for key, hit in m.items():
                hits, asked = out.get(key, [0, 0])
                out[key] = [hits + int(hit), asked + 1]
    return out


def canonical(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def run_requests(runs, stem):
    """{(journal, request_id): {arm: request}} for one recorded run, with the run's derived arms rebuilt."""
    if stem.startswith('dishes-'):
        store = json.loads((runs / f"v4-{stem.split('-', 1)[1]}.requests.json").read_text(encoding='utf-8'))['requests']
        out = {}
        for key, e in store.items():
            body = deepcopy(e['arms']['V4G'])
            body['state']['kitchen'].pop('dishes', None)
            out[key] = {'NODISH': body}
        return store, out
    store = json.loads((runs / f'{stem}.requests.json').read_text(encoding='utf-8'))['requests']
    return store, {key: e['arms'] for key, e in store.items()}


def run_answers(runs, stem):
    answers = defaultdict(list)
    path = runs / f'{stem}.answers.jsonl'
    if not path.exists():
        return answers
    for line in path.read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        if 'choice' in r['answer']:
            answers[(r['key'], r['arm'])].append(r['answer'])
    return answers


def moment_key(key):
    """'study#journal#rid' or 'journal#rid' -> (journal, rid)."""
    parts = key.split('#')
    return parts[-2], int(parts[-1])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('runs')
    parser.add_argument('--out', default=str(ROOT / 'lab' / 'data'))
    args = parser.parse_args()
    runs, out = Path(args.runs).resolve(), Path(args.out)
    os.chdir(ROOT)
    import ask_ahead, features, harness, one_press, request_parts, session_record  # noqa: E401,F401
    from kitchen import apply_input
    from research_replay import factory
    from jev import compose_payload, NO_MEMORY
    from whitebox_server import SpatialJevClient
    override = Path(os.environ.get('CHEFJEFF_FEATURES_OVERRIDE', Path.home() / '.config/chefjeff/features.override.json'))
    logs = ROOT / 'logs'

    def play_set(service):
        raw = json.loads((ROOT / 'features.json').read_text(encoding='utf-8'))
        value = features.model_defaults(features.with_override(raw, json.loads(override.read_text(encoding='utf-8'))), service)
        for name in list(request_parts.SWITCHES) + ['go_note']:
            value[name] = {**value[name], 'on': False}
        return value, features.compose_options(value)

    def bundle_for(journal):
        stem = journal.split('-')[1]
        return next((p for p in sorted((logs / 'sessions').iterdir())
                     if p.name.startswith(stem) and (p / 'engine-inputs.jsonl').exists()), None)

    def build(source, row, opts, parts, go, model):
        acts = source.actions('jeff')
        if opts['one_press']:
            acts = acts + one_press.options(source, 'jeff', acts, opts['one_press'])
        undo = None
        if opts['undo'] is not None:
            undo = row.get('undo_note') or opts['undo']
            if isinstance(undo, dict) and 'history' in undo:
                kept = [{**h, 'layout': {p: v for p, v in h['layout'].items() if p != 'at'}} for h in undo['history']
                        if h.get('places') != ['at']]
                undo = {**undo, 'history': kept[-4:]}
        st = row['payload']['state']
        decisions = row.get('recent_decisions', st.get('recent_decisions', []))
        body = compose_payload(SpatialJevClient(source.c, key='x'), source, source.snapshot(), acts, deepcopy(decisions),
                               st.get('player_communication'), st['past_episodes'] if 'past_episodes' in st else NO_MEMORY,
                               opts['one_press'], deepcopy(undo), opts['reach'], opts['names'], links=opts['links'],
                               split=opts['split'], burn=opts['burn'], serve_note=opts['serve_note'], steps=opts['steps'],
                               clear=opts['clear'], walk=opts['walk'], english=opts['english'], plate=opts['plate'],
                               parts=parts, go=go)
        body['model'] = model
        return harness.for_model(body)

    # 1. Recorded answers by (service, sha of the request they were given), and what each moment was picked for.
    recorded = defaultdict(list)
    labels = defaultdict(set)
    steps = {}
    wanted = defaultdict(set)
    for stem, (service, arms) in RUNS.items():
        if not (runs / f"{stem if not stem.startswith('dishes-') else 'v4-' + service}.requests.json").exists():
            print(f'{stem}: no requests file, left out', file=sys.stderr)
            continue
        store, by_key = run_requests(runs, stem)
        answers = run_answers(runs, stem)
        for key, arm_bodies in by_key.items():
            journal, rid = moment_key(key)
            wanted[journal].add(rid)
            meta = store.get(key, {})
            labels[(journal, rid)].add(meta.get('category') or meta.get('study') or stem.split('-')[0])
            if meta.get('steps'):
                steps[(journal, rid)] = meta['steps']
            if meta.get('played'):
                steps.setdefault((journal, rid, 'played'), meta['played'])
            for arm, condition in arms.items():
                if arm in arm_bodies:
                    sha = canonical(arm_bodies[arm])
                    for a in answers.get((key, arm), []):
                        recorded[(service, sha)].append({'choice': a['choice'], 'probabilities': a.get('probabilities') or {}})
    # 2. Rebuild every moment under every condition for every service, and attach what matches.
    (out / 'moments').mkdir(parents=True, exist_ok=True)
    sets = {service: play_set(service) for service in MODELS}
    index, scored = [], defaultdict(dict)       # (service, moment id) -> {condition: [per-answer measures]}
    for journal, rids in sorted(wanted.items()):
        path = logs / journal
        bundle = bundle_for(journal) if path.exists() else None
        if bundle is None:
            print(f'{journal}: no session bundle, left out', file=sys.stderr)
            continue
        data = session_record.read_bundle(str(bundle))
        k = factory(data['session']['runtime_versions']['engine'])(deepcopy(data['resolved']))
        n = 0
        with open(path, encoding='utf-8') as journal_file:
            for row in (json.loads(line) for line in journal_file):
                if row.get('kind') != 'ai_request' or not isinstance(row.get('payload'), dict) or row.get('engine_input_n') is None:
                    continue
                while n < row['engine_input_n']:
                    apply_input(k, data['inputs'][n]); n += 1
                rid = row['request_id']
                if rid not in rids:
                    continue
                source = k
                if row.get('ask_ahead'):
                    job = k.chefs['jeff'].job
                    source = ask_ahead.predict(k) if job and job.id == row['ask_ahead']['job_id'] else None
                    if source is None:
                        continue
                mid = f"{journal.split('-')[1]}-{rid}"
                moment = {'id': mid, 'round': journal.split('-')[1], 'request_id': rid, 'level': source.c.get('level'),
                          't': round(source.time, 1), 'labels': sorted(labels[(journal, rid)]),
                          'steps': steps.get((journal, rid)), 'played': steps.get((journal, rid, 'played')),
                          'holding': (source.snapshot()['chefs']['jeff'].get('holding') or {}).get('meaning'), 'services': {}}
                for service, (_, opts) in sets.items():
                    moment['services'][service] = {}
                    for condition, (parts, go) in CONDITIONS.items():
                        body = build(source, row, opts, parts, go, MODELS[service])
                        answers = recorded.get((service, canonical(body)), [])
                        moment['services'][service][condition] = {'request': body, 'answers': answers,
                                                                  'chars': len(json.dumps(body, ensure_ascii=False))}
                        if answers:
                            criteria = body['questions']['next_action']['criteria']
                            scored[(service, mid)][condition] = [measure(a['choice'], moment, criteria) for a in answers]
                (out / 'moments' / f'{mid}.json').write_text(json.dumps(moment, ensure_ascii=False), encoding='utf-8')
                summary = {key: value for key, value in moment.items() if key != 'services'}
                summary['answered'] = {s: {c: len(v['answers']) for c, v in conds.items()} for s, conds in moment['services'].items()}
                summary['chars'] = {s: {c: v['chars'] for c, v in conds.items()} for s, conds in moment['services'].items()}
                index.append(summary)
        print(f'{journal}: {sum(1 for m in index if m["round"] == journal.split("-")[1])} moments', file=sys.stderr)
    # Paired: each condition against today's request over the moments where both have recorded answers.
    results = defaultdict(dict)
    for service in MODELS:
        for condition in CONDITIONS:
            if condition == 'today':
                continue
            pair = [(v['today'], v[condition]) for (s, _), v in scored.items() if s == service and 'today' in v and condition in v]
            if pair:
                results[service][condition] = {'moments': len(pair), 'today': total([a for a, _ in pair]),
                                               'this': total([b for _, b in pair])}
    value, _ = sets['jev']
    switches = {name: {'on_today': bool(v.get('on')), 'version': v.get('version'), 'stage': v.get('stage')}
                for name, v in features.with_override(json.loads((ROOT / 'features.json').read_text(encoding='utf-8')), {}).items()}
    (out / 'index.json').write_text(json.dumps({
        'built_with': {'features_versions': {n: v['version'] for n, v in switches.items()}},
        'conditions': list(CONDITIONS), 'models': MODELS, 'moments': index,
        'results': results}, ensure_ascii=False), encoding='utf-8')
    attached = sum(sum(sum(v.values()) for v in m["answered"].values()) for m in index)
    print(f'{len(index)} moments, {attached} recorded answers attached -> {out}')


if __name__ == '__main__':
    main()
