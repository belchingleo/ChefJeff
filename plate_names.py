"""plate-names-v1: an option that puts food onto a plate says what that plate holds, as the state names it.

A trial (features.json plate_names, off by default, no page switch). The plating options name only the place: "Fill
the plate on Counter 2 from your frying pan" reads the same whether Counter 2 holds a clean plate or a plate with
bread, and "Plate food from Stove 2" does not say which plate the food goes onto. What lies on Counter 2 is in that
station's own entry, among some thirty. A player sees the plate on the counter. With this switch on, in the English
request, a label that names a plate by its place, or the plate a chef holds, names it as the request's own state
does ("Fill the plate with bread on Counter 2 from your frying pan", "Put the held bread (as fetched) onto the clean
plate at Counter 4", "Merge food from the plate with lettuce at Counter 3 into the held plate with bread", "Plate
food from Stove 2 onto the held plate with bread"). Nothing is said about the dish that would come of it or the
order it would serve. It applies to the options and to each chef's task, not to the links table, whose lines are
steps after an option (what lies there or in hand by then is not what the state shows now). Applying it twice
changes nothing more. plate_names_version goes with the static part.
"""
from __future__ import annotations

import re

from clear_names import _lower

VERSION = 'plate-names-v1'
AT = re.compile(r'\bthe plate (at|on) ')
HELD = re.compile(r'\bthe held plate\b(?! with)')
TEAMMATE = re.compile(r"\bteammate's held plate\b(?! with)")
FROM = re.compile(r'\bPlate food from [^();]+?(?= \(|;|$)')


def plate(food):
    """What a plate is as the state names it ("clean plate", "plate with bread", "Steak"), or None if not a plate."""
    if isinstance(food, dict) and food.get('meaning') and (food.get('stage') == 'clean_plate' or food.get('plate_id')):
        return _lower(food['meaning'])
    return None


def _places(kitchen):
    out = {}
    for s in (kitchen.get('stations') or {}).values():
        if s.get('name'):
            out[s['name']] = s.get('food')
    for g in kitchen.get('ground') or []:
        if g.get('near'):
            out[g['near']] = g.get('food')
    return out


def name(text, places, held=None, teammate=None):
    """A label with each plate it names by place, or as held, named as the state names it."""
    def at(m):
        rest = text[m.end():]
        place = next((p for p in sorted(places, key=len, reverse=True) if rest.startswith(p)), None)
        what = plate(places.get(place)) if place else None
        return f'the {what} {m.group(1)} ' if what else m.group(0)
    text = AT.sub(at, text)
    if held:
        text = HELD.sub(f'the held {held}', text)
        text = FROM.sub(lambda m: m.group(0) if ' onto ' in m.group(0) else f'{m.group(0)} onto the held {held}', text)
    if teammate:
        text = TEAMMATE.sub(f"teammate's held {teammate}", text)
    return text


def apply(payload):
    """What the plate_names switch does to an English request (jev.compose_payload): the labels and the version."""
    k = payload['state']['kitchen']
    places = _places(k)
    chefs = k.get('chefs') or {}
    held = {who: plate(c.get('holding')) for who, c in chefs.items()}
    for q in payload.get('questions', {}).values():
        criteria = q.get('criteria') if isinstance(q, dict) else None
        for key in criteria or {}:
            criteria[key] = name(criteria[key], places, held.get('jeff'), held.get('human'))
    for who, chef in chefs.items():
        if isinstance(chef.get('task'), str):
            other = next((w for w in chefs if w != who), None)
            chef['task'] = name(chef['task'], places, held.get(who), held.get(other))
    payload['state']['plate_names_version'] = VERSION
    return payload
