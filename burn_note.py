"""burn-note-v2: an option on a stove whose food is cooking or cooked says, with the times, when it is cooked and burns.

A trial (features.json burn_note, off by default, no page switch). The request's state already gives each stove's
burn_in, and the fire rule says the stove catches fire when its food burns; the option labels do not. With this
switch on, every next_action option whose key names a stove holding cooked food (stage ready, burn_in in the state)
gets " (<food> on <stove> burns in <burn_in> s; <stove> catches fire then)" after its label, with the food and stove
named as the request names them. Facts from the request's own state only: nothing about what to do. Options on other
stations and requests with no cooked food on a stove are unchanged; burn_note_version is the only other addition.
v2: while the food is still cooking (stage cooking, ready_in in the state), the options on its stove get
" (<food> on <stove> is cooked in <ready_in> s and burns in <burn_in> s; <stove> catches fire then)": in v1 the
options said nothing until the food was cooked, and Jeff chose to go to the pan only well into the 10 s left.
v3: while Jeff holds a pan or pot whose food is cooking or cooked, each option that puts it on a stove ("put pot
<stove>", "swap pot <stove>", in next_action and put_where) gets " (<food> in the held <vessel> burns <s> s after it
is back on the heat; <stove> catches fire then)", the seconds from the engine's heat thresholds and the food's heat so
far (off the stove it does not heat). In a 2026-11-19 play round Jeff put a pan of beef cooked 8 s before back on its
stove; its label said only "resume heating if filled", and the beef burnt 1.5 s later.
"""
from __future__ import annotations

VERSION = 'burn-note-v3'
NOTE = ' ({food} on {stove} burns in {seconds:.1f} s; {stove} catches fire then)'
COOKING = ' ({food} on {stove} is cooked in {ready:.1f} s and burns in {seconds:.1f} s; {stove} catches fire then)'
HELD = ' ({food} in the held {vessel} burns {seconds:.1f} s after it is back on the heat; {stove} catches fire then)'
HELD_COOKING = (' ({food} in the held {vessel} is cooked {ready:.1f} s and burns {seconds:.1f} s after it is back on the '
                'heat; {stove} catches fire then)')
QUESTIONS = ('next_action', 'put_where')


def notes(payload):
    """{stove id: the note} for each stove in this English request whose food is cooking or cooked."""
    out = {}
    for sid, station in payload['state']['kitchen']['stations'].items():
        food = station.get('food')
        if not (station.get('stove') and isinstance(food, dict) and station.get('burn_in') is not None):
            continue
        if food.get('stage') == 'ready':
            out[sid] = NOTE.format(food=food.get('meaning'), stove=station.get('name', sid), seconds=station['burn_in'])
        elif food.get('stage') == 'cooking' and station.get('ready_in') is not None:
            out[sid] = COOKING.format(food=food.get('meaning'), stove=station.get('name', sid), ready=station['ready_in'],
                                      seconds=station['burn_in'])
    return out


def held_notes(payload, kitchen):
    """(v3) {option key: the note} for each option that would put the pan or pot Jeff holds, with food cooking or
    cooked in it, on a stove; {} when he holds none (or no kitchen is given)."""
    k = payload['state']['kitchen']
    held = (k.get('chefs', {}).get('jeff') or {}).get('holding')
    food = held.get('contents') if isinstance(held, dict) and held.get('stage') == 'pot' else None
    if kitchen is None or not isinstance(food, dict) or food.get('stage') not in ('ready', 'cooking'):
        return {}
    try:
        ready, burn, _ = kitchen.rules.heat_thresholds(food['ingredient'])
    except (KeyError, TypeError):
        return {}
    heated = float(food.get('heat_elapsed') or 0)
    if food['stage'] == 'ready':
        heated = max(heated, ready)        # cooked food has had at least its cooking time on the heat
    vessel = ((k.get('vessels') or {}).get(held.get('vessel')) or {}).get('name') or 'pot'
    out = {}
    for sid, station in k.get('stations', {}).items():
        if not station.get('stove'):
            continue
        stove = station.get('name', sid)
        if food['stage'] == 'ready':
            text = HELD.format(food=food.get('meaning'), vessel=vessel, seconds=max(0.0, burn - heated), stove=stove)
        else:
            text = HELD_COOKING.format(food=food.get('meaning'), vessel=vessel, ready=max(0.0, ready - heated),
                                       seconds=max(0.0, burn - heated), stove=stove)
        out[f'put pot {sid}'] = out[f'swap pot {sid}'] = text
    return out


def apply(payload, kitchen=None):
    """What the burn_note switch adds to an English request (harness.compose): the notes and the version."""
    question = payload.get('questions', {}).get('next_action')
    found = notes(payload)
    if question and found:
        criteria = question['criteria']
        for key in criteria:
            for sid, text in found.items():
                if sid in key.split():
                    criteria[key] = criteria[key] + text
    held = held_notes(payload, kitchen)
    for name in QUESTIONS:
        criteria = (payload.get('questions', {}).get(name) or {}).get('criteria') or {}
        for key in criteria:
            if key in held:
                criteria[key] = criteria[key] + held[key]
    payload['state']['burn_note_version'] = VERSION
    return found
