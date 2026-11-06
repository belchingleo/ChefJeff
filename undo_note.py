"""Undo notes for Jeff (on trial: off unless features.json turns `undo_note` on): when a listed option would take
back what Jeff's last step put down, or put back what it took, the option's label says so, as a fact with the time.

Jeff's last step is his latest choice that the game carried out, a one-press choice counting as one step. Continue,
wait and walking keep the step before; any other carried-out choice replaces it. The step keeps where Jeff put an
item down and where he took one, with the items' ids, read from the kitchen as the choice started (the snapshot
the decision loop logs with each answer, so replay reads the same). At each request the notes are worked out
again from the kitchen: a note appears only while the same item is still where Jeff put it, or still in his hand.

- take back: an option that takes from the station where his last step put the item down ("take <station>",
  "put then take <station>") says "this takes back the <item> you put on <station> at <t> s".
- put back: an option that puts the held item on the station his last step took it from ("put <station>", in
  next_action and in questions.put_where) says "this puts the <item> back on <station>, where you took it at <t> s".

Nothing is forbidden or advised: the options, their keys and the engine are unchanged, and the player sees no note.
"""
from __future__ import annotations

VERSION = 'undo-note-v1'
KEEP = ('continue', 'wait')
QUESTIONS = ('next_action', 'put_where')


def _item(value):
    return value if isinstance(value, dict) and value.get('id') else None


def _food(kitchen, station):
    return _item(((kitchen.get('stations') or {}).get(station) or {}).get('food'))


def _held(kitchen):
    return _item(((kitchen.get('chefs') or {}).get('jeff') or {}).get('holding'))


def _put_target(key):
    """The station a plain put action names, or None."""
    if not isinstance(key, str) or not key.startswith('put ') or key.startswith(('put then ', 'put pot ')):
        return None
    return key[4:]


def _take_target(key):
    if not isinstance(key, str):
        return None
    if key.startswith('put then take '):
        return key[len('put then take '):]
    if key.startswith('take ') and not key.startswith('take pot '):
        return key[5:]
    return None


def step(kitchen, choice, first, t):
    """Jeff's step from a carried-out choice: {'t', 'put', 'take'} (each {'station', 'id'} or None), or None to keep
    the step before (continue, wait, walking). kitchen is the snapshot as the choice started; first is the put a
    one-press choice started with (its put_where place), when it started with one."""
    if not isinstance(choice, str) or choice in KEEP or choice.startswith('go '):
        return None
    held = _held(kitchen)
    put_at = _put_target(choice) or (_put_target(first) if choice.startswith(('put then ', 'wash from ')) else None)
    take_at = _take_target(choice)
    taken = _food(kitchen, take_at) if take_at else None
    return {'t': round(float(t), 2),
            'put': {'station': put_at, 'id': held['id']} if put_at and held else None,
            'take': {'station': take_at, 'id': taken['id']} if taken else None}


def notes(kitchen, last):
    """{'take_back': (station, text), 'put_back': (station, text)} for what still holds now; kitchen is the request's
    (English) snapshot."""
    out = {}
    if not last:
        return out
    t = f"{last['t']:.1f}"
    stations = kitchen.get('stations') or {}
    put, take = last.get('put'), last.get('take')
    if put:
        food = _food(kitchen, put['station'])
        if food and food['id'] == put['id']:
            out['take_back'] = (put['station'], f"this takes back the {food.get('meaning') or 'item'} you put on "
                                                 f"{stations[put['station']].get('name') or put['station']} at {t} s")
    if take:
        held = _held(kitchen)
        if held and held['id'] == take['id'] and take['station'] in stations:
            out['put_back'] = (take['station'], f"this puts the {held.get('meaning') or 'item'} back on "
                                                 f"{stations[take['station']].get('name') or take['station']}, where you took it at {t} s")
    return out


def annotate(payload, last):
    """Add the notes to the option labels of an English request, in place; returns the (question, key) pairs noted."""
    found = notes(payload['state']['kitchen'], last)
    noted = []
    for question in QUESTIONS:
        criteria = payload.get('questions', {}).get(question, {}).get('criteria')
        if not isinstance(criteria, dict):
            continue
        for key in criteria:
            texts = []
            if 'take_back' in found and _take_target(key) == found['take_back'][0]:
                texts.append(found['take_back'][1])
            if 'put_back' in found and _put_target(key) == found['put_back'][0]:
                texts.append(found['put_back'][1])
            if texts:
                criteria[key] += ' (Note: ' + '; '.join(texts) + '.)'
                noted.append((question, key))
    return noted


def apply(payload, undo):
    """What the undo_note switch adds to an English request (harness.compose): the notes and the version."""
    noted = annotate(payload, (undo or {}).get('step'))
    payload['state']['undo_note_version'] = VERSION
    return noted
