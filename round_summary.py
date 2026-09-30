"""Round record: who did which kind of work, generated from the round itself.

    round_summary(kitchen) -> summary (JSON-safe)

Nothing here names a level, dish or ingredient. Categories follow the engine's
action semantics (fetch, chop, heat, assemble, serve, wash, pass, fire, discard),
which every level shares. Each category is broken down by the recipe items or
dishes that actually occurred, with display names from the level's recipe
catalog, so a new level with new ingredients or dishes needs no change here.
Categories and details with no activity are omitted.

Counts are completed actions (owner decision 2026-09-28); a shared chop counts
once for each chef who worked on it.
"""
from __future__ import annotations

from collaboration_analyzer import analyze_collaboration

SUMMARY_VERSION = 'round-summary-1'
CHEFS = ('human', 'jeff')

# Engine action kinds per category. Only engine semantics live here, never content.
CATEGORIES = (
    ('fetch', ('fetch',)),
    ('chop', ('chop',)),
    ('heat', ()),            # food entering a pot: provenance.containers
    ('assemble', ('assemble', 'assemble_ground', 'plate_pot', 'plate_counter', 'plate_from_counter',
                  'plate_ground', 'plate_partner', 'merge_plates')),
    ('serve', ('serve',)),
    ('wash', ('wash',)),
    ('collect_plates', ('take_return',)),
    ('pass', ('throw',)),
    ('extinguish', ('extinguish',)),
    ('discard', ('discard', 'clear', 'empty_pot')),
)


def _blank():
    return {who: 0 for who in CHEFS}


def round_summary(k):
    p = k.provenance
    names = dict(k.rules.item_names)
    dishes = dict(k.rules.recipe_names)
    # The items each completed action touched, from the provenance record.
    touched = {}
    shared = {}
    for item, touches in p.history.items():
        for t in touches:
            for aid in t.action_ids:
                touched.setdefault(aid, set()).add(item)
                shared[aid] = len(set(t.actors)) > 1

    def item_of(aid):
        """The recipe item an action worked on (the one ingredient it touched)."""
        kinds = {p.ingredients[i] for i in touched.get(aid, ()) if i in p.ingredients}
        return next(iter(kinds)) if len(kinds) == 1 else None

    rows = []
    for category, kinds in CATEGORIES:
        total, details = _blank(), {}

        def count(who, detail=None, extra=None):
            total[who] += 1
            if detail:
                row = details.setdefault(detail, {'id': detail, 'counts': _blank(), **(extra or {})})
                row['counts'][who] += 1

        if category == 'heat':
            steps = {a['seq']: (aid, a) for aid, a in p.actions.items()}
            cooked = {e.get('item') for e in k.events if e.get('kind') == 'ready'}
            burnt = {e.get('item') for e in k.events if e.get('kind') == 'burn'}
            for m in p.containers:
                aid, action = steps.get(m.seq, (None, None))
                if not action or action['actor'] not in total:
                    continue
                item = p.ingredients.get(m.dish)
                count(action['actor'], item, {'name': names.get(item, item)})
                outcome = 'burnt' if m.dish in burnt else 'cooked' if m.dish in cooked else None
                if outcome:
                    row = details[item].setdefault(outcome, _blank())
                    row[action['actor']] += 1
        elif category == 'serve':
            for s in p.serves:
                if s['actor'] not in total:
                    continue
                count(s['actor'], f"{s['outcome']}:{s['dish']}",
                      {'outcome': s['outcome'], 'dish': s['dish'], 'name': dishes.get(s['dish'], s['dish'])})
        elif category == 'pass':
            for aid, a in p.actions.items():
                if a['kind'] in kinds and a['actor'] in total:
                    count(a['actor'], 'thrown')
            for e in k.events:
                if e.get('kind') == 'caught' and e.get('actor') in total:
                    details.setdefault('caught', {'id': 'caught', 'counts': _blank()})['counts'][e['actor']] += 1
        else:
            for aid, a in sorted(p.actions.items()):
                if a['kind'] not in kinds or a['actor'] not in total:
                    continue
                item = item_of(aid) if category in ('fetch', 'chop') else None
                detail = item if item else (a['kind'] if category == 'discard' else None)
                extra = {'name': names.get(item, item)} if item else {}
                count(a['actor'], detail, extra)
                if category == 'chop' and shared.get(aid):
                    details[item].setdefault('shared', _blank())[a['actor']] += 1
        if any(total.values()) or any(any(d['counts'].values()) for d in details.values()):
            rows.append({'category': category, 'counts': total, 'details': list(details.values())})

    analysis = analyze_collaboration(k)
    goal = k.goal_status() if hasattr(k, 'goal_status') else {}
    return {
        'version': SUMMARY_VERSION,
        'level_id': k.c.get('level_id'),
        'result': {'served': k.served, 'money': k.money, 'target_money': goal.get('target_money'),
                   'reached_target': bool(k.won())},
        'chefs': list(CHEFS),
        'rows': rows,
        # Owner decision 2026-09-30: contribution by time, not by action count. Effort = game seconds of
        # each chef's contributing actions; critical path = each chef's time on the chains that decided
        # when each dish could be served (waiting between steps belongs to nobody).
        'contribution': {
            'effort': {'seconds': analysis['effort_seconds'], 'share': analysis['effort_share']},
            'critical_path': analysis['critical_path'],
        },
        # Data interface only; the settlement page does not show these (owner decisions 2026-09-29/30).
        'not_displayed': {
            'action_share': {who: analysis['chefs'][who]['share_of_contributing'] for who in CHEFS},
            'wasted': {who: analysis['chefs'][who]['wasted'] for who in CHEFS},
            'harmful': {who: {reason: sum(1 for a in analysis['harmful']['actions'] if a['actor'] == who and a['reason'] == reason)
                              for reason in analysis['harmful']['by_reason']} for who in CHEFS},
        },
    }
