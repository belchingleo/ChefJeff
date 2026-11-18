"""burn-note-v1: an option on a stove whose food is cooked says, with the time, when that food burns.

A trial (features.json burn_note, off by default, no page switch). The request's state already gives each stove's
burn_in, and the fire rule says the stove catches fire when its food burns; the option labels do not. With this
switch on, every next_action option whose key names a stove holding cooked food (stage ready, burn_in in the state)
gets " (<food> on <stove> burns in <burn_in> s; <stove> catches fire then)" after its label, with the food and stove
named as the request names them. Facts from the request's own state only: nothing about what to do. Options on other
stations and requests with no cooked food on a stove are unchanged; burn_note_version is the only other addition.
"""
from __future__ import annotations

VERSION = 'burn-note-v1'
NOTE = ' ({food} on {stove} burns in {seconds:.1f} s; {stove} catches fire then)'


def notes(payload):
    """{stove id: the note} for each stove in this English request whose food is cooked."""
    out = {}
    for sid, station in payload['state']['kitchen']['stations'].items():
        food = station.get('food')
        if (station.get('stove') and isinstance(food, dict) and food.get('stage') == 'ready'
                and station.get('burn_in') is not None):
            out[sid] = NOTE.format(food=food.get('meaning'), stove=station.get('name', sid), seconds=station['burn_in'])
    return out


def apply(payload):
    """What the burn_note switch adds to an English request (harness.compose): the notes and the version."""
    question = payload.get('questions', {}).get('next_action')
    found = notes(payload)
    if question and found:
        criteria = question['criteria']
        for key in criteria:
            for sid, text in found.items():
                if sid in key.split():
                    criteria[key] = criteria[key] + text
    payload['state']['burn_note_version'] = VERSION
    return found
