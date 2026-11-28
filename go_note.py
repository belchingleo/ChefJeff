"""go-note-v1: a "go X" option says when, on arrival, nothing at X takes what Jeff holds (or, with empty hands,
nothing there is to do).

A trial (features.json go_note, off by default, no page switch). "go X" is listed only when no other listed action
walks to X (harness.model_candidates), so by construction Jeff can do nothing at X with what he holds now; the label
says only "Walk to Serve (Cooking area)". In the user's level-4 rounds (2026-11-17..20) Jev walked to the serving
window about once a round, nearly always holding an empty frying pan or a half-made plate, right after plating from a
held pan onto a counter plate; at the window he could serve nothing and then put something down or waited.

With this switch on, each listed "go X" is carried out on a private fork of the kitchen (the other chef going on with
what they are doing), and when on arrival no action of Jeff's acts on X (other than walking there, waiting or
stopping), the label gets " (on arrival, nothing there takes the held <item>)" or " (on arrival, nothing to do
there with empty hands)". A fact about the place, worked out by the engine the same way on every level; it says
nothing about what to do instead. go_note_version goes with the static part.
"""
from __future__ import annotations

VERSION = 'go-note-v1'
IDLE = ('go', 'wait', 'continue', 'stop')


def _held(payload):
    chefs = payload.get('state', {}).get('kitchen', {}).get('chefs', {})
    holding = (chefs.get('jeff') or {}).get('holding')
    if isinstance(holding, dict):
        return holding.get('meaning') or holding.get('id')
    return None


def note(kitchen, action, held):
    """The note for one "go X" option, or None when something on arrival acts on X (or the walk cannot be made)."""
    import links
    from kitchen import throw_listing
    with links.throws_left_out():       # the walk there reads no throw
        twin = links._fork(kitchen)
        if not links._carry_out(twin, 'jeff', action, [], None):
            return None
    with throw_listing(True):           # a throw onto X is something to do there
        if any(a.target == action.target and a.kind not in IDLE for a in twin.actions('jeff')):
            return None
    return f' (on arrival, nothing there takes the held {held})' if held else ' (on arrival, nothing to do there with empty hands)'


def apply(payload, kitchen, actions):
    """What the go_note switch adds to an English request (jev.compose_payload): the notes and the version."""
    criteria = payload.get('questions', {}).get('next_action', {}).get('criteria', {})
    by_key = {a.key: a for a in actions}
    held = _held(payload)
    for key in criteria:
        a = by_key.get(key)
        if a is None or a.kind != 'go' or a.target not in kitchen.stations:
            continue
        try:
            text = note(kitchen, a, held)
        except Exception:      # a fork the engine cannot carry out: say nothing
            text = None
        if text:
            criteria[key] += text
    payload['state']['go_note_version'] = VERSION
    return payload
