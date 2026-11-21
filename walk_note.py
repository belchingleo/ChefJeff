"""walk-note-v1: every option that walks somewhere says how many seconds of walking that is, as the engine routes it.

A trial (features.json walk_note, off by default, no page switch). A person sees at a glance that the lettuce on the
floor beside them is nearer than the lettuce supply; Jeff reads coordinates ("floor (5,3)", position [6.0, 3.49]) and
the labels say nothing about distance, though the engine works out the walk of every step it starts (travel_time, the
"travel 1s" of its own messages). With this switch on, each next_action option with a place to walk to gets the
seconds from where Jeff stands: " (0.5 s walk)"; a one-press option (put first, then go on) gets the walk from where
Jeff stands to the place it ends at, since put_where is not chosen yet: " (Lettuce supply: 2.0 s walk from you)".
Options that do not walk (wait, continue, throws) are left as they are. Computed on a private fork of the kitchen
with its own route cache, so nothing in the round changes. walk_note_version goes with the static part.
"""
from __future__ import annotations

VERSION = 'walk-note-v1'
NO_WALK = ('wait', 'continue', 'stop', 'throw', 'aim', 'sprint')


def _place(twin, target):
    if target in twin.stations:
        from model_language import english_text
        return english_text(twin.stations[target].name)
    if str(target).startswith('floor_'):
        _, x, y = target.split('_')
        return f'floor ({x},{y})'
    return str(target)


def apply(payload, kitchen, actions):
    """What the walk_note switch adds to an English request (jev.compose_payload): the walks and the version."""
    import links
    import one_press
    criteria = payload.get('questions', {}).get('next_action', {}).get('criteria', {})
    by_key = {a.key: a for a in actions}
    twin = None
    for key in criteria:
        a = by_key.get(key)
        if a is None or a.kind in NO_WALK or not a.target:
            continue
        if twin is None:
            twin = links._fork(kitchen)
        try:
            # throw_to walks to its throw spot, not to the station it throws onto.
            seconds = twin.travel_time(twin.chefs['jeff'], a.expected[1] if a.kind == one_press.THROW_TO else a.target)
        except Exception:      # no route the engine would walk: say nothing
            continue
        if a.kind == one_press.THROW_TO:
            criteria[key] += f' ({seconds:.1f} s walk)'
        elif a.kind in one_press.KINDS:
            criteria[key] += f' ({_place(twin, a.target)}: {seconds:.1f} s walk from you)'
        else:
            criteria[key] += f' ({seconds:.1f} s walk)'
    payload['state']['walk_note_version'] = VERSION
    return payload
