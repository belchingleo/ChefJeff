"""Collaboration Analyzer v0.1: which completed actions made the served dishes.

    analyze_collaboration(kitchen) -> report
    python collaboration_analyzer.py logs/sessions/<id>   (replays the bundle; no model calls)

Deterministic counterpart of Causal Collaboration Effectiveness (AgentWorld,
arXiv 2609.31590): instead of an LLM judge, contribution is traced through item
provenance (provenance.py). Definitions (owner decisions 2026-09-28):

- An action is a completed job other than go / wait / stop / continue.
- Contributing: on the provenance of a dish that was accepted at the serving
  window: every effective touch of the dish, of the items merged into it (up to
  the merge) and of its plate since the plate's previous dish, plus the serve.
- Effective touches: a touch that returns an item to a place and state it already
  had cancels the touches in between (e.g. swapping two items back and forth).
  A pot's handling since it last held food counts for the food that enters it.
- Harmful (counted separately, never contributing): actions whose completion was
  penalised: a dish nobody waited for, a refused dish, discarding, clearing or
  emptying a pot.
- Wasted: every other action, labelled support (it touched only tools, pots or
  nothing), loop (all its touches were cancelled) or unused (its handling never
  reached an accepted dish, e.g. food still cooking at closing).

Expired orders and fires are outcomes of time, not of one action; they are
reported as round penalties.
"""
from __future__ import annotations
import json
import sys

from provenance import NON_ACTIONS

ANALYZER_VERSION = 'collaboration-analyzer-0.1'


def _effective(touches):
    """Indices of touches that survive loop cancellation."""
    stack = []  # (key, index)
    cancelled = set()
    for i, t in enumerate(touches):
        key = (t.place, t.state)
        earlier = next((j for j, (k, _) in enumerate(stack) if k == key), None)
        if earlier is not None and t.place:
            for _, index in stack[earlier + 1:]:
                cancelled.add(index)
            cancelled.add(i)
            del stack[earlier + 1:]
        else:
            stack.append((key, i))
    return [i for i in range(len(touches)) if i not in cancelled], cancelled


def _cuts(p, item):
    """History indices where a plate (or pot) begins a new life: after each dish (or food) it carried."""
    return sorted({m.upto for m in p.merges + p.containers if m.parent == item})


def _cancelled(p, item):
    """Loop-cancelled touch indices, found separately within each life of the item."""
    touches = p.history.get(item, [])
    bounds = [0] + [c for c in _cuts(p, item) if 0 < c < len(touches)] + [len(touches)]
    out = set()
    for start, end in zip(bounds, bounds[1:]):
        _, cancelled = _effective(touches[start:end])
        out |= {start + i for i in cancelled}
    return out


def _window_start(p, item, upto):
    """A plate's (or pot's) history restarts after it last carried an earlier dish (or food)."""
    return max((m.upto for m in p.merges + p.containers if m.parent == item and m.upto < upto), default=0)


def _lineage(p, item, upto, out, depth=0):
    """Collect (item, touch) pairs on the provenance of ``item`` up to history index ``upto``."""
    touches = p.history.get(item, [])
    start = _window_start(p, item, upto)
    window = touches[start:upto]
    keep, _ = _effective(window)
    for i in keep:
        out.append((item, window[i]))
    if not window or depth > 64:
        return
    first, last = window[0].seq, window[-1].seq
    for m in p.merges + p.containers:
        if m.dish == item and first <= m.seq <= last:
            _lineage(p, m.parent, m.upto, out, depth + 1)


def analyze_collaboration(k):
    p = k.provenance
    actions = {aid: a for aid, a in p.actions.items() if a['kind'] not in NON_ACTIONS}
    touches_by_action = {}
    for item, touches in p.history.items():
        cancelled = _cancelled(p, item)
        for i, t in enumerate(touches):
            for aid in t.action_ids:
                touches_by_action.setdefault(aid, []).append((item, i in cancelled))
    dishes = []
    contributing = set()
    for serve in p.serves:
        if serve['outcome'] != 'served':
            continue
        chain = []
        _lineage(p, serve['item'], len(p.history.get(serve['item'], [])), chain)
        ids = {aid for _, t in chain for aid in t.action_ids} | {serve['action_id']}
        contributing |= ids
        by_item = {}
        for item, t in chain:
            by_item.setdefault(item, []).append(t)
        handoffs = 0
        for item_touches in by_item.values():
            ordered = sorted(item_touches, key=lambda t: t.seq)
            handoffs += sum(1 for a, b in zip(ordered, ordered[1:]) if set(a.actors) != set(b.actors))
        chefs = sorted({actor for _, t in chain for actor in t.actors} | {serve['actor']})
        dishes.append({'item': serve['item'], 'plate': serve['plate'], 't': serve['t'], 'served_by': serve['actor'],
                       'contributing_actions': len(ids & set(actions)), 'chefs': chefs, 'cross_chef_handoffs': handoffs})
    harmful = {aid: reason for aid, reason in p.penalties.items() if aid in actions}
    contributing = (contributing & set(actions)) - set(harmful)
    wasted = {}
    for aid in actions:
        if aid in contributing or aid in harmful:
            continue
        touched = touches_by_action.get(aid, [])
        if not touched or all(item[0] in 'PE' for item, _ in touched):
            wasted[aid] = 'support'
        elif all(cancelled for _, cancelled in touched):
            wasted[aid] = 'loop'
        else:
            wasted[aid] = 'unused'

    def share(ids, who=None):
        return sorted(aid for aid in ids if who is None or actions[aid]['actor'] == who)

    chefs = {}
    for who in ('human', 'jeff'):
        mine = share(actions, who)
        c = share(contributing, who)
        chefs[who] = {'actions': len(mine), 'contributing': len(c),
                      'contribution_rate': round(len(c) / len(mine), 3) if mine else None,
                      'share_of_contributing': round(len(c) / len(contributing), 3) if contributing else None,
                      'harmful': len(share(harmful, who)),
                      'wasted': {label: sum(1 for aid in mine if wasted.get(aid) == label)
                                 for label in ('loop', 'unused', 'support')}}
    kinds = [e.get('kind') for e in k.events]
    return {
        'analyzer_version': ANALYZER_VERSION,
        'actions': len(actions),
        'contributing': len(contributing),
        'contribution_rate': round(len(contributing) / len(actions), 3) if actions else None,
        'harmful': {'count': len(harmful), 'by_reason': {r: sum(1 for x in harmful.values() if x == r) for r in sorted(set(harmful.values()))},
                    'actions': [{'action_id': aid, 'actor': actions[aid]['actor'], 'kind': actions[aid]['kind'], 'reason': r, 't': actions[aid]['t']}
                                for aid, r in sorted(harmful.items())]},
        'wasted': {'count': len(wasted), 'by_label': {label: sum(1 for x in wasted.values() if x == label)
                                                      for label in ('loop', 'unused', 'support')}},
        'chefs': chefs,
        'dishes': dishes,
        'dishes_with_both_chefs': sum(1 for d in dishes if len(d['chefs']) == 2),
        'cross_chef_handoffs': sum(d['cross_chef_handoffs'] for d in dishes),
        'round_penalties': {'expired_orders': kinds.count('expired'), 'fires': getattr(k, 'fires', 0)},
        'money': k.money,
    }


def analyze_bundle(folder):
    """Replay a session bundle and analyze it; says whether the replay matches the recording.

    A bundle recorded by an older engine may replay differently; then the analysis
    describes the replay, not the round that was played.
    """
    import session_record
    bundle = session_record.read_bundle(folder)
    k = session_record.replay_bundle(folder)
    # The log opens after the kitchen is built, so the first events may be missing: match by engine seq.
    recorded = [(e['engine_seq'], e['type'], e['game_time_ms']) for e in bundle['events'] if e.get('source') == 'engine']
    replayed = {e['seq']: (e['seq'], e.get('kind'), e['game_time_ms']) for e in k.events}
    first = next((seq for seq, kind, ms in recorded if replayed.get(seq) != (seq, kind, ms)), None)
    if first is None and recorded and max(replayed, default=0) > recorded[-1][0]:
        first = recorded[-1][0] + 1
    report = analyze_collaboration(k)
    report['replay'] = {'matches_recording': first is None, 'engine_events': len(recorded),
                        'first_divergent_engine_seq': first}
    return report


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit('usage: python collaboration_analyzer.py logs/sessions/<id>')
    print(json.dumps(analyze_bundle(argv[0]), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
