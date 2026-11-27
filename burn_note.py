"""burn-note-v6: an option on a stove whose food is cooked says when it burns and that the stove then catches fire.

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
v4: the notes follow the stove's heating and fire as well (v3 gave the times of a stove that is not burning, which a
fire spreading to a stove made false once it stopped burning food, 2026-11-22). On a burning stove food that does not
heat gets " (<food> on <stove> waits until the fire on <stove> is out)", food still cooking there " (<food> on <stove>
is cooked in <ready_in> s, then waits until the fire on <stove> is out)"; a held pan's food that is not burnt, for a
burning stove, " (<food> in the held <vessel> waits there until the fire on <stove> is out)". No seconds for the wait:
it lasts until someone puts the fire out.
v5 (2026-11-27): while the food is still cooking, the options on its stove say only " (<food> on <stove> is cooked in
<ready_in> s)"; the burn and fire times come once it is cooked, as in v1. In the 2026-11-27 re-ask (scripts/
layer_reask.py steps, Jev, level 4) the facts step with v4 saved more cooked pans (10% to 53% of answers lifted or
plated food about to burn) but lifted still-cooking pans at moments where no Jev answer had before (half the answers):
the lift option of a cooking pan read "is cooked in 7.0 s and burns in 17.1 s; Stove 1 catches fire then".
v6 (2026-11-27): no note while the food is still cooking on a stove that is not burning, as in v1. The follow-up
re-ask showed it was the note itself, not its burn and fire times: at the same ten moments Jev left a still-cooking pan
alone in 30 of 30 answers without the burn note, 15 of 30 with v4 alone, and 3 of 13 with v5 (six level-4 moments with
the request-writing step on top: 2 of 18 with v4, 0 of 18 with v5). The note on cooked food, which made Jev lift or
plate food about to burn in 17 of 30 answers against 3 of 30 without it, stays.
"""
from __future__ import annotations

VERSION = 'burn-note-v6'
NOTE = ' ({food} on {stove} burns in {seconds:.1f} s; {stove} catches fire then)'
HELD = ' ({food} in the held {vessel} burns {seconds:.1f} s after it is back on the heat; {stove} catches fire then)'
HELD_COOKING = (' ({food} in the held {vessel} is cooked {ready:.1f} s and burns {seconds:.1f} s after it is back on the '
                'heat; {stove} catches fire then)')
WAIT = ' ({food} on {stove} waits until the fire on {stove} is out)'
COOKING_FIRE = ' ({food} on {stove} is cooked in {ready:.1f} s, then waits until the fire on {stove} is out)'
HELD_WAIT = ' ({food} in the held {vessel} waits there until the fire on {stove} is out)'
QUESTIONS = ('next_action', 'put_where')


def notes(payload):
    """{stove id: the note} for each stove in this English request whose food is cooking or cooked."""
    out = {}
    for sid, station in payload['state']['kitchen']['stations'].items():
        food = station.get('food')
        if not (station.get('stove') and isinstance(food, dict) and station.get('burn_in') is not None):
            continue
        stage, stove, meaning = food.get('stage'), station.get('name', sid), food.get('meaning')
        heating, burning = bool(station.get('heating')), bool(station.get('fire'))
        if stage not in ('ready', 'cooking'):
            continue
        if burning and not heating:             # v4: it waits on the burning stove
            out[sid] = WAIT.format(food=meaning, stove=stove)
        elif stage == 'ready' and heating:
            out[sid] = NOTE.format(food=meaning, stove=stove, seconds=station['burn_in'])
        elif stage == 'cooking' and heating and burning and station.get('ready_in') is not None:
            out[sid] = COOKING_FIRE.format(food=meaning, stove=stove, ready=station['ready_in'])
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
        if station.get('fire'):                 # v4: on a burning stove it waits (kitchen.stove_heats)
            text = HELD_WAIT.format(food=food.get('meaning'), vessel=vessel, stove=stove)
        elif food['stage'] == 'ready':
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
