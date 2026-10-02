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
import itertools
import json
import math
import sys

from provenance import NON_ACTIONS

ANALYZER_VERSION = 'collaboration-analyzer-0.3'


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


def _spans(k):
    """Game-time start and end of every completed action (start from its action_start event)."""
    starts = {e['action_id']: e['t'] for e in k.events if e.get('kind') == 'action_start' and e.get('action_id')}
    return {aid: (starts.get(aid, a['t']), a['t']) for aid, a in k.provenance.actions.items()}


def _critical_path(p, chain, serve, spans, ready=None):
    """Walk back from the serve: each step's predecessor is the earlier touch whose item arrived last.

    An item arrives when the touch before this step finishes, except food that cooks: it arrives
    when it is ready (``ready``: item -> game time), not when it went into the pan. Otherwise the
    plate fetched while the beef was still frying would look like the last input.

    Returns [(seconds, actors)] per step (overlap with the previous step removed), the time between
    steps credited to no one (cooking, unattended or waiting for the other chef), and the cooking
    part of that time.
    """
    ready = ready or {}
    by_item, steps = {}, {}
    for item, touch in chain:
        by_item.setdefault(item, []).append(touch)
        steps.setdefault(touch.seq, {'items': set(), 'ids': set(), 'actors': set()})
        steps[touch.seq]['items'].add(item)
        steps[touch.seq]['ids'] |= set(touch.action_ids)
        steps[touch.seq]['actors'] |= set(touch.actors)
    for touches in by_item.values():
        touches.sort(key=lambda t: t.seq)
    end = lambda seq: max(spans[a][1] for a in steps[seq]['ids'])
    begin = lambda seq: min(spans[a][0] for a in steps[seq]['ids'])
    current = p.actions[serve['action_id']]['seq']
    if current not in steps:
        return [], 0., 0.
    path, cooked = [current], {}
    while True:
        preds = {}
        for item in steps[current]['items']:
            earlier = [t.seq for t in by_item[item] if t.seq < current]
            if earlier:
                seq = max(earlier)
                done, r = end(seq), ready.get(item)
                at = r if r is not None and done < r <= end(current) else done
                preds[seq] = max(preds.get(seq, at), at)
        if not preds:
            break
        nxt = max(preds, key=lambda seq: (preds[seq], end(seq), seq))
        cooked[current] = preds[nxt] if preds[nxt] > end(nxt) else None
        current = nxt
        path.append(current)
    path.reverse()
    out, waiting, cooking, previous_end = [], 0., 0., None
    for seq in path:
        start, finish = begin(seq), end(seq)
        if previous_end is not None:
            done_cooking = cooked.get(seq)
            if done_cooking is not None:
                cooking += max(0., min(done_cooking, finish) - previous_end)
                previous_end = max(previous_end, min(done_cooking, finish))
            waiting += max(0., start - previous_end)
            start = max(start, previous_end)
        out.append((max(0., finish - start), sorted(steps[seq]['actors'])))
        previous_end = finish if previous_end is None else max(previous_end, finish)
    return out, waiting + cooking, cooking


def _walk_seconds(k, a, b):
    """Shortest walk between two finish points of a spatial kitchen; 0 elsewhere."""
    nav = getattr(k, 'nav', None)
    if a is None or b is None or nav is None:
        return 0.
    try:
        points = nav.shortest_path(a, b)
    except Exception:
        points = [a, b]
    return sum(math.dist(x, y) for x, y in zip(points, points[1:])) / k.rules.walk_speed


def _dish_metrics(k, p, serve, chain, spans, ready, order_t, useful):
    """Standard effort of each chef on one dish, and how much later than ideal it went out.

    Standard effort of a step: its work from the configuration (chopping or washing work,
    otherwise the handling time) plus the shortest walk its carried items needed from where
    their previous step finished. First touches count no walk. Cooking is nobody's work.

    Ideal: the same steps at standard effort, each starting as soon as its inputs are there and
    its chef has finished their earlier useful work; a first touch can start at the order. The
    delay (actual minus ideal serve time) is split over the chefs by their Shapley value: each
    chef's average saving when the chefs are made ideal one at a time, in every order; a chef
    left as they were keeps the lag they really had after their inputs arrived.
    """
    handling = k.c.get('handling_seconds', .15)
    steps, by_item = {}, {}
    for item, t in chain:
        s = steps.setdefault(t.seq, {'items': set(), 'ids': set(), 'actors': set(), 'kind': t.kind})
        s['items'].add(item)
        s['ids'] |= set(t.action_ids)
        s['actors'] |= set(t.actors)
        by_item.setdefault(item, []).append(t.seq)
    last = p.actions[serve['action_id']]['seq']
    if last not in steps:
        return None
    begin = {q: min(spans[a][0] for a in s['ids']) for q, s in steps.items()}
    end = {q: max(spans[a][1] for a in s['ids']) for q, s in steps.items()}
    at = {q: next((p.actions[a].get('at') for a in sorted(s['ids']) if p.actions[a].get('at')), None) for q, s in steps.items()}

    def inputs(q):
        """(previous step, its actual arrival, cooking seconds) for each item the step touched."""
        out = []
        for item in steps[q]['items']:
            earlier = [x for x in by_item[item] if x < q]
            if earlier:
                pred = max(earlier)
                r = ready.get(item)
                cook = r - end[pred] if r is not None and end[pred] < r <= end[q] else 0.
                out.append((pred, end[pred] + cook, cook))
        return out

    def work(q):
        kind = steps[q]['kind']
        if kind == 'chop':
            foods = [p.ingredients[i] for i in steps[q]['items'] if p.ingredients.get(i)]
            return max([k.rules.chop_work(f) for f in foods] or [handling])
        if kind == 'wash':
            return k.rules.wash_work
        return handling

    standard = {q: work(q) + max((_walk_seconds(k, at[pr], at[q]) for pr, _, _ in inputs(q)), default=0.) for q in steps}
    effort = {}
    for q, s in steps.items():
        for who in s['actors']:
            effort[who] = effort.get(who, 0.) + standard[q] / len(s['actors'])

    def free_at(who, before):
        return max((e for _, e in useful.get(who, ()) if e <= before + 1e-9), default=0.)

    def finish(fast):
        done = {}
        for q in sorted(steps):
            ins = inputs(q)
            arrive = max((done[pr] + cook for pr, _, cook in ins), default=None)
            if steps[q]['actors'] <= fast:
                if arrive is None:
                    start = begin[q] if order_t is None else min(begin[q], order_t)
                    start = max([start] + [free_at(w, begin[q]) for w in steps[q]['actors']])
                else:
                    start = arrive
                done[q] = start + standard[q]
            else:
                real = max((a for _, a, _ in ins), default=None)
                start = arrive + max(0., begin[q] - real) if arrive is not None else begin[q]
                done[q] = start + (end[q] - begin[q])
        return done[last]

    actual = end[last]
    chefs = sorted(set().union(*(s['actors'] for s in steps.values())))
    delay = max(0., actual - finish(set(chefs)))
    by = {w: 0. for w in chefs}
    orders = list(itertools.permutations(chefs))
    for order in orders:
        fast, before = set(), actual
        for w in order:
            fast.add(w)
            now = finish(set(fast))
            by[w] += (before - now) / len(orders)
            before = now
    return {'effort': effort, 'delay': delay, 'delay_by': by}


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
    spans = _spans(k)
    critical = {'human': 0., 'jeff': 0.}
    critical_waiting = 0.
    critical_cooking = 0.
    chains = []
    ready = {}
    for e in k.events:
        if e.get('kind') == 'ready' and e.get('item'):
            ready.setdefault(e['item'], e['t'])
    for serve in p.serves:
        if serve['outcome'] != 'served':
            continue
        chain = []
        _lineage(p, serve['item'], len(p.history.get(serve['item'], [])), chain)
        chains.append((serve, chain))
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
        steps, waiting, cooking = _critical_path(p, chain, serve, spans, ready)
        path = {'human': 0., 'jeff': 0.}
        for seconds, actors in steps:
            for actor in actors:
                if actor in path:
                    path[actor] += seconds / len(actors)
        for who in critical:
            critical[who] += path[who]
        critical_waiting += waiting
        critical_cooking += cooking
        dishes.append({'item': serve['item'], 'plate': serve['plate'], 't': serve['t'], 'served_by': serve['actor'],
                       'contributing_actions': len(ids & set(actions)), 'chefs': chefs, 'cross_chef_handoffs': handoffs,
                       'critical_path': {'steps': len(steps), 'seconds': {w: round(s, 3) for w, s in path.items()},
                                         'waiting_seconds': round(waiting, 3), 'cooking_seconds': round(cooking, 3)}})
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

    # Contribution by standard effort, delay and idle time (owner decision 2026-10-02; shown in the
    # round record for community feedback).
    orders = {e['order_id']: e['t'] for e in k.events if e.get('kind') == 'order' and e.get('order_id')}
    served_order = {e['action_id']: e.get('order_id') for e in k.events if e.get('kind') == 'served' and e.get('action_id')}
    useful = {}
    for aid in contributing:
        if aid in spans:
            useful.setdefault(actions[aid]['actor'], []).append(spans[aid])
    standard = {'human': 0., 'jeff': 0.}
    delay = {'human': 0., 'jeff': 0.}
    for dish, (serve, chain) in zip(dishes, chains):
        m = _dish_metrics(k, p, serve, chain, spans, ready, orders.get(served_order.get(serve['action_id'])), useful)
        if m is None:
            continue
        for w, v in m['effort'].items():
            if w in standard:
                standard[w] += v
        for w, v in m['delay_by'].items():
            if w in delay:
                delay[w] += v
        total = sum(m['effort'].values())
        dish['contribution'] = {w: round(v / total, 3) if total else None for w, v in sorted(m['effort'].items())}
        dish['delay'] = {'seconds': round(m['delay'], 2), 'by': {w: round(v, 2) for w, v in sorted(m['delay_by'].items())}}
    idle = {'human': 0., 'jeff': 0.}
    for aid, a in p.actions.items():
        if a['actor'] not in idle or aid not in spans:
            continue
        if a['kind'] == 'wait' or wasted.get(aid) in ('loop', 'unused'):
            idle[a['actor']] += spans[aid][1] - spans[aid][0]

    def share(ids, who=None):
        return sorted(aid for aid in ids if who is None or actions[aid]['actor'] == who)

    effort = {'human': 0., 'jeff': 0.}
    for aid in contributing:
        if actions[aid]['actor'] in effort:
            effort[actions[aid]['actor']] += spans[aid][1] - spans[aid][0]

    def shares(seconds):
        total = sum(seconds.values())
        return {w: round(s / total, 3) if total else None for w, s in seconds.items()}

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
        # Time-weighted views (owner decision 2026-09-30): the game seconds each chef spent on
        # contributing actions, and each chef's time on the dishes' critical paths.
        'effort_seconds': {w: round(s, 3) for w, s in effort.items()},
        'effort_share': shares(effort),
        'critical_path': {'seconds': {w: round(s, 3) for w, s in critical.items()}, 'share': shares(critical),
                          'waiting_seconds': round(critical_waiting, 3), 'cooking_seconds': round(critical_cooking, 3)},
        # Contribution: each chef's standard effort (configured work + shortest needed walk) on the
        # served dishes. Delay: seconds each chef added to the dishes' serve times beyond the ideal.
        # Idle: seconds on actions that reached no served dish (loops, unused work) or waiting.
        'contribution': {'seconds': {w: round(s, 3) for w, s in standard.items()}, 'share': shares(standard)},
        'delay_seconds': {w: round(s, 2) for w, s in delay.items()},
        'idle_seconds': {w: round(s, 2) for w, s in idle.items()},
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
