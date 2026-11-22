"""Undo notes for Jeff (on trial: off unless features.json turns `undo_note` on): when carrying out a listed option
would bring back how things were before one of Jeff's last steps, the option's label says so, as a fact with the time.

v4 (2026-11-19), the check the game uses: worked out by the engine, the same on every level and for every kind of
step. At each step Jeff starts, the decision loop keeps the kitchen's layout (what lies where, by the engine's id and
the request's name, at every place Jeff reaches and in his hands) and the places the step acts on; the last HISTORY steps are kept. For each
option, a fork of the kitchen carries it out to the end of its step (as the links table does); when the places Jeff
has touched since one of those steps (the option's own included) would be exactly as they were when that step
started, and are not so now, the label gets "(Note: this brings back how things were at <t> s, before your last <n>
steps: <what lay where>)". Taking back what he just put down, putting back what he took, returning a lifted pan to
its stove and moving the same food back and forth between plates are all this one case: in a 2026-11-19 level-5 round
Jeff moved half a burger between two plates on Counters 10 and 11 four times in 20 s, which no v1-v3 rule named
(merging from a plate was no take). Steps count together only while they are linked through the places they act on
(each shares a place with the rest, his hands left out), so two separate undos in a row do not join into one. A
one-press option that starts by putting the held item down is worked out for
each put_where place that held that item before; the note names the place. Items compare by id and name (food on a
plate by the plate's id), so a newly fetched lettuce is not the one passed on, and a station on fire, or chopping or
washing begun, is part of what lies there. Nothing is forbidden or advised; the player sees no note.

v1-v3 (below, kept for scripts/undo_note_check.py, which reads logged journals without an engine): when a listed
option would take back what Jeff's last step put down, or put back what it took, the option's label says so.

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

v2 (2026-11-19): ask_ahead no longer waits for this switch to be off. A request asked ahead describes the kitchen at
the end of the step under way; that step is kept as Jeff's last step when it starts, so it is his last step at the
moment asked about, and the notes are worked out from the kitchen as predicted then (the item put down is where he
put it). v1 rounds with this switch on never asked ahead.

v3 (2026-11-19): a pan or pot lifted from a stove ("take pot <stove>") is a take of that vessel, and one put on a
stove ("put pot <stove>") a put: putting a lifted pan straight back on its stove says "this puts the <pan> back on
<stove>, where you took it at <t> s", and lifting one just put there says it takes it back. In a 2026-11-19 play round
Jeff lifted a pan of cooked beef and put it back on its stove 2.5 s later, where it burnt; v2 left both steps out.
A pan returned after plating from it is no note: plating is the last step then.
"""
from __future__ import annotations

VERSION = 'undo-note-v4'
V3_VERSION = 'undo-note-v3'
HISTORY = 4
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
    if not isinstance(key, str) or not key.startswith('put ') or key.startswith('put then '):
        return None
    return key[len('put pot '):] if key.startswith('put pot ') else key[4:]


def _take_target(key):
    if not isinstance(key, str):
        return None
    if key.startswith('put then take '):
        return key[len('put then take '):]
    if key.startswith('take pot '):
        return key[len('take pot '):]
    if key.startswith('take '):
        return key[5:]
    return None


def _vessel(kitchen, station):
    """(v3) The pan or pot on a stove, as {'id', 'meaning'}, or None."""
    s = (kitchen.get('stations') or {}).get(station) or {}
    if not s.get('stove') or not s.get('pot_id'):
        return None
    name = ((kitchen.get('vessels') or {}).get(s.get('vessel')) or {}).get('name') or 'pot'
    food = _item(s.get('food'))
    return {'id': s['pot_id'], 'meaning': f"{name} with {food.get('meaning')}" if food and food.get('meaning') else f'empty {name}'}


def _at(kitchen, station):
    """What a take from this station takes: the vessel on a stove, else the station's item."""
    return _vessel(kitchen, station) or _food(kitchen, station)


def step(kitchen, choice, first, t):
    """Jeff's step from a carried-out choice: {'t', 'put', 'take'} (each {'station', 'id'} or None), or None to keep
    the step before (continue, wait, walking). kitchen is the snapshot as the choice started; first is the put a
    one-press choice started with (its put_where place), when it started with one."""
    if not isinstance(choice, str) or choice in KEEP or choice.startswith('go '):
        return None
    held = _held(kitchen)
    # One-press choices that start with a put (one_press.PUT_KINDS): put then ..., wash from, and empty (v8), which
    # puts down what is held before it takes the burnt pan. Its take is not recorded: the pan comes back emptied, so
    # putting it back where it was undoes nothing.
    put_at = _put_target(choice) or (_put_target(first) if choice.startswith(('put then ', 'wash from ', 'empty '))
                                     else None)
    take_at = _take_target(choice)
    taken = _at(kitchen, take_at) if take_at else None
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
        food = _at(kitchen, put['station'])
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


def apply_v3(payload, undo):
    """What undo-note-v3 added to an English request: the notes from {'step': ...} and its version."""
    noted = annotate(payload, (undo or {}).get('step'))
    payload['state']['undo_note_version'] = V3_VERSION
    return noted


# v4: the generic check, from the engine.
NO_STEP = ('continue', 'wait', 'stop', 'go', 'throw', 'aim')


def _name(kitchen, food):
    """A food object's English name as the request names it (food_names in naming mode); None for nothing."""
    import food_names
    from model_language import english_text
    if food is None:
        return None
    if food.stage == 'pot':
        vessel = english_text(kitchen.vessel_name(food.id))
        return f'{vessel} with {_name(kitchen, food.contents)}' if food.contents else f'empty {vessel}'
    if food.stage in ('clean_plate', 'dirty_plate'):
        return food.stage.replace('_', ' ')
    if food.stage == 'extinguisher':
        return 'extinguisher'
    with food_names.naming():
        return english_text(food_names.plain(kitchen, food))


def _reaches(kitchen, place):
    try:
        return kitchen.reaches('jeff', place)
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def _ident(food):
    """Which object it is: a plate's id for food on a plate, else the item's own id (a pan or pot: its id and its
    contents'). Items compare by id and name, so a new lettuce is not the one thrown away and a station that was put
    out is not as it was."""
    if food is None:
        return ''
    own = food.plate_id or food.id
    return f'{own}/{_ident(food.contents)}' if food.stage == 'pot' and food.contents else own


def _progress(food):
    if food is None or food.stage == 'pot':
        return ''
    if food.stage == 'raw' and food.chopped > 0:
        return ' (chopping begun)'
    if food.stage == 'dirty_plate' and food.washed > 0:
        return ' (washing begun)'
    return ''


def layout(kitchen):
    """{place: '<id>|<name>'} at every place Jeff reaches and in his hands ('hand'), empty places left out: what lies
    there, by the engine's id and the request's name. A stove names its pan or pot with what it holds; a stack names
    the plates under the top one; a station on fire says so; chopping or washing begun is part of the name."""
    from model_language import english_text
    out = {}
    for key, s in kitchen.stations.items():
        if not _reaches(kitchen, key):
            continue
        fire = ' (on fire)' if s.fire else ''
        if key in getattr(kitchen, 'pots', ()) and s.pot_id:
            vessel = english_text(kitchen.vessel_name(s.pot_id))
            name = f'{vessel} with {_name(kitchen, s.food)}' if s.food else f'empty {vessel}'
            out[key] = f'{s.pot_id}/{_ident(s.food)}|{name}{fire}'
        elif s.food is not None:
            more = f' (and {len(s.stack)} more under it)' if s.stack else ''
            out[key] = f'{_ident(s.food)}|{_name(kitchen, s.food)}{_progress(s.food)}{more}{fire}'
        elif fire:
            out[key] = '|nothing' + fire
    for item in getattr(kitchen, 'ground', {}).values():
        if _reaches(kitchen, item.location):
            out[item.location] = f'{_ident(item.food)}|{_name(kitchen, item.food)}{_progress(item.food)}'
    held = kitchen.chefs['jeff'].hand
    if held is not None:
        out['hand'] = f'{_ident(held)}|{_name(kitchen, held)}{_progress(held)}'
    return out


def record(kitchen, action, first=None, t=None):
    """Jeff's step as it starts, for the history: {'t', 'places' (what the step acts on, his hands included), 'layout'};
    None for what is no step (continue, wait, walking, throwing). first: the put a one-press choice started with."""
    if action is None or action.kind in NO_STEP or action.key.startswith('go '):
        return None
    places = {'hand', action.target} | ({first.target} if first is not None else set())
    return {'t': round(float(kitchen.time if t is None else t), 2), 'places': sorted(p for p in places if p),
            'layout': layout(kitchen)}


def remember(undo, entry):
    """The undo state with this step added (the oldest dropped past HISTORY)."""
    if entry is None:
        return undo
    return {'history': (list((undo or {}).get('history') or []) + [entry])[-HISTORY:]}


def _carried_out(kitchen, option, place):
    """(the fork after the option's step ends, where its first put lands or None), or None when it cannot end."""
    import links
    import one_press
    twin = links._fork(kitchen)
    if any(getattr(twin, 'manual', {}).get('human', (0.0, 0.0))):
        twin.set_manual('human', 0, 0)
    put_at = None
    if option.kind in one_press.KINDS:
        rest = one_press.steps(option, twin)
        first = ('put' if twin.chefs['jeff'].hand is not None and option.kind in one_press.PUT_KINDS
                 else one_press.find(twin, 'jeff', rest[0]))
        if first == 'put':
            action, _ = one_press.place(twin.actions('jeff'), place)
            if action is None:
                return None
            put_at = action.target
        else:
            rest = rest[1:]
    else:
        first, rest = option, []
    if first is None or not links._carry_out(twin, 'jeff', first, rest, place):
        return None
    return twin, put_at


def _where(kitchen, place):
    from model_language import english_text
    if place == 'hand':
        return 'in your hands'
    if place in kitchen.stations:
        return 'on ' + english_text(kitchen.stations[place].name)
    if isinstance(place, str) and place.startswith('floor_'):
        _, x, y = place.split('_')
        return f'on the floor at ({x},{y})'
    return 'at ' + str(place)


def _then(kitchen, past, touched):
    parts = [f"{past[p].split('|', 1)[1]} {_where(kitchen, p)}" for p in sorted(touched, key=lambda p: (p != 'hand', p))
             if past.get(p)]
    if not past.get('hand'):
        parts.append('your hands empty')
    return ', '.join(parts)


def _linked(groups):
    """Whether these steps' places (his hands left out) form one chain: each step shares a place with the rest."""
    groups = [set(g) - {'hand'} for g in groups]
    if not groups or not all(groups):
        return bool(groups) and all(groups)
    reached, todo = set(groups[0]), list(groups[1:])
    while todo:
        joined = [g for g in todo if g & reached]
        if not joined:
            return False
        for g in joined:
            reached |= g
            todo.remove(g)
    return True


def returns(kitchen, history, keys, put_places=()):
    """{option key: note text} for the options that would bring back how things were before one of the steps in
    history. kitchen is the engine's (the request's kitchen); keys are option keys of next_action or put_where."""
    import one_press
    if not history:
        return {}
    actions = {a.key: a for a in kitchen.actions('jeff')}
    held = kitchen.chefs['jeff'].hand
    if held is not None:
        actions.update({a.key: a for a in one_press.options(kitchen, 'jeff', list(actions.values()), one_press.flags(
            {name: True for name in one_press.NAMES}))})
    seen = set().union(*(set(h['places']) for h in history))
    now = layout(kitchen)
    # Where each put_where answer puts the held item; a place that never held that item cannot bring it back.
    listed = kitchen.actions('jeff')
    put_targets = {p: getattr(one_press.place(listed, p)[0], 'target', None) for p in put_places}
    held_before = {p for p, target in put_targets.items()
                   if target and any(h['layout'].get(target) == now.get('hand') for h in history)}
    out = {}
    for key in keys:
        option = actions.get(key)
        if option is None or option.kind in NO_STEP or key.startswith('go ') or option.target not in seen:
            continue
        places = [None]
        if option.kind in one_press.PUT_KINDS and held is not None:
            places = [p for p in put_places if p in held_before]
        for place in places:
            done = _carried_out(kitchen, option, place)
            if done is None:
                continue
            twin, put_at = done
            after = layout(twin)
            mine = {'hand', option.target} | ({put_at} if put_at else set())
            for j in range(len(history) - 1, -1, -1):
                if not _linked([h['places'] for h in history[j:]] + [mine]):
                    continue                # not one chain from here; an older step may still link them
                touched = mine.union(*(set(h['places']) for h in history[j:]))
                past = history[j]['layout']
                if all(after.get(p) == past.get(p) for p in touched) and any(now.get(p) != past.get(p) for p in touched):
                    n = len(history) - j
                    steps = 'before your last step' if n == 1 else f'before your last {n} steps'
                    lead = f'putting the held item {_where(kitchen, put_at)} first, ' if place and put_at else ''
                    out[key] = (f"{lead}this brings back how things were at {history[j]['t']:.1f} s, {steps}: "
                                f"{_then(kitchen, past, touched)}")
                    break
            if key in out:
                break
    return out


def apply(payload, undo, kitchen=None):
    """What the undo_note switch adds to an English request: v4's notes (from the engine kitchen) and the version."""
    history = (undo or {}).get('history') or []
    noted = []
    if kitchen is not None and history:
        put_places = list(((payload.get('questions') or {}).get('put_where') or {}).get('criteria') or {})
        for question in QUESTIONS:
            criteria = (payload.get('questions') or {}).get(question, {}).get('criteria')
            if not isinstance(criteria, dict):
                continue
            for key, text in returns(kitchen, history, list(criteria), put_places).items():
                criteria[key] += ' (Note: ' + text + '.)'
                noted.append((question, key))
    payload['state']['undo_note_version'] = VERSION
    return noted
