"""step-check-v1: for each kind of step the waiting orders need, whether the kitchen allows it now and, if not, what
stands in the way, from the engine's state and recipes.

A trial (features.json step_check, off by default, no page switch). Jeff reads the kitchen as some thirty stations of
fields, where a missing pan is only empty fields among many; he was told such things one note at a time (backlog_note,
the pans line). With this switch on, a request on a floor where every board is on the other chef's side gets one live
field, state.step_check, that says, in this order:

- what the waiting orders still need chopped (backlog_note's counts, without its pans sentence);
- chopping: which boards are free or hold something to chop, or that every board holds other food, and whose side
  they are on;
- cooking, for each vessel the waiting orders cook in: on which stoves it can start now, or that no stove has that
  vessel (and where the vessels are), or that every one holds food or is on fire;
- plating: where the clean plates and the plates with food are, or that there is no clean plate (where the dirty
  ones are, and how many are still with diners);
- serving: where it is done and whose side that is.

Facts only, nothing about who should do what. It changes with every request (live part); step_check_version goes
with the static part. On any other floor nothing is added.
"""
from __future__ import annotations

import backlog_note

VERSION = 'step-check-v1'


def _side(kitchen, sids):
    jeff = all(kitchen.reaches('jeff', s) for s in sids)
    human = all(kitchen.reaches('human', s) for s in sids)
    if jeff and human:
        return 'both sides'
    if jeff:
        return 'your side'
    if human:
        return "the other chef's side"
    return 'both sides, each its own'


def _name(stations, sid):
    return stations.get(sid, {}).get('name', sid)


def _food(food):
    return food.get('meaning') or food.get('stage') if isinstance(food, dict) else None


def _vessel_places(k, kind):
    """Where the vessels of a kind lie off the stoves: station names, hands, floor places."""
    places = []
    for sid, station in k.get('stations', {}).items():
        food = station.get('food')
        if isinstance(food, dict) and food.get('stage') == 'pot' and food.get('vessel') == kind and not station.get('stove'):
            places.append(station.get('name', sid))
    for who, chef in k.get('chefs', {}).items():
        food = chef.get('holding')
        if isinstance(food, dict) and food.get('stage') == 'pot' and food.get('vessel') == kind:
            places.append('your hands' if who == 'jeff' else "the other chef's hands")
    for g in k.get('ground', []):
        food = g.get('food')
        if isinstance(food, dict) and food.get('stage') == 'pot' and food.get('vessel') == kind:
            places.append(g.get('near') or g.get('location'))
    return places


def chopping(kitchen, payload, need):
    if not any(need.values()):
        return None
    stations = payload['state']['kitchen']['stations']
    boards = [sid for sid, e in kitchen.equipment.items() if e.get('type') == 'board']
    if not boards:
        return 'Chopping: not possible: no board.'
    free, to_chop, other = [], [], []
    for sid in boards:
        food = stations.get(sid, {}).get('food')
        if food is None:
            free.append(_name(stations, sid))
        elif isinstance(food, dict) and not food.get('plate_id') and food.get('stage') == 'raw' and food.get('ingredient') in need:
            to_chop.append(f'{_name(stations, sid)} holds {_food(food)}')
        else:
            other.append(f'{_name(stations, sid)}: {_food(food)}')
    side = _side(kitchen, boards)
    if free or to_chop:
        parts = ([f"{', '.join(free)} free"] if free else []) + to_chop + other
        return f"Chopping: possible now ({'; '.join(parts)}); the boards are on {side}."
    return f"Chopping: not possible now: every board holds other food ({'; '.join(other)}); the boards are on {side}."


def cooking(kitchen, payload):
    k = payload['state']['kitchen']
    stations = k.get('stations', {})
    names = {kind: v.get('name', kind) for kind, v in (k.get('vessels') or {}).items()}
    by_kind = {}
    for o in k.get('orders', []):
        if o.get('status') != 'pending' or o.get('dish') not in kitchen.rules.recipes:
            continue
        for c in kitchen.rules.recipes[o['dish']]['components']:
            heat = kitchen.rules.heat.get(c['item'])
            if c['state'] == 'ready' and heat and heat.get('container'):
                items = by_kind.setdefault(heat['container'], [])
                if c['item'] not in items:
                    items.append(c['item'])
    stoves = [sid for sid, station in stations.items() if station.get('stove')]
    lines = []
    for kind, items in by_kind.items():
        name = names.get(kind, kind)
        what = f"Cooking {', '.join(items)} in a {name}"
        holding = [sid for sid in stoves if stations[sid].get('pot_id') and stations[sid].get('vessel') == kind]
        if not holding:
            places = _vessel_places(k, kind)
            where = f" ({name}s: {', '.join(places)})" if places else ''
            lines.append(f'{what}: not possible now: no stove has a {name}{where}.')
            continue
        free = [sid for sid in holding if not stations[sid].get('food') and not stations[sid].get('fire')]
        busy = []
        for sid in holding:
            if stations[sid].get('fire'):
                busy.append(f'{_name(stations, sid)} is on fire')
            elif stations[sid].get('food'):
                busy.append(f"{_name(stations, sid)} holds {_food(stations[sid]['food'])}")
        side = _side(kitchen, holding)
        if free:
            rest = f"; {'; '.join(busy)}" if busy else ''
            lines.append(f"{what}: possible now on {', '.join(_name(stations, s) for s in free)}{rest}; the stoves are on {side}.")
        else:
            lines.append(f"{what}: not possible now: every {name} on a stove holds food or is on fire ({'; '.join(busy)}).")
    return lines


def plating(kitchen, payload):
    k = payload['state']['kitchen']
    if not any(o.get('status') == 'pending' for o in k.get('orders', [])):
        return None
    stations = k.get('stations', {})
    clean, used, dirty = {}, [], {}

    def count(where, food):
        if not isinstance(food, dict):
            return
        if food.get('stage') == 'clean_plate':
            clean[where] = clean.get(where, 0) + 1
        elif food.get('stage') == 'dirty_plate':
            dirty[where] = dirty.get(where, 0) + 1
        elif food.get('plate_id'):
            used.append(f'{where} ({_food(food)})')
    for sid, station in stations.items():
        where = station.get('name', sid)
        count(where, station.get('food'))
        for food in station.get('stack') or []:
            count(where, food)
    for who, chef in k.get('chefs', {}).items():
        count('your hands' if who == 'jeff' else "the other chef's hands", chef.get('holding'))
    for g in k.get('ground', []):
        count(g.get('near') or g.get('location'), g.get('food'))
    listed = lambda places: ', '.join(f'{p} {n}' if n > 1 else p for p, n in places.items())
    with_diners = len((k.get('tableware') or {}).get('customers') or [])
    if clean or used:
        parts = ([f'clean plates: {listed(clean)}'] if clean else ['no clean plate']) + ([f"plates with food: {', '.join(used)}"] if used else [])
        return f"Plating: possible now ({'; '.join(parts)})."
    extra = ([f'dirty plates: {listed(dirty)}'] if dirty else []) + ([f'with diners: {with_diners}'] if with_diners else [])
    return f"Plating: not possible now: no clean plate{(' (' + '; '.join(extra) + ')') if extra else ''}."


def serving(kitchen, payload):
    stations = payload['state']['kitchen'].get('stations', {})
    windows = [sid for sid, e in kitchen.equipment.items() if e.get('type') == 'serving_window']
    if not windows:
        return None
    return f"Serving: at {', '.join(_name(stations, s) for s in windows)}, on {_side(kitchen, windows)}."


def line(kitchen, payload):
    if not backlog_note.applies(kitchen):
        return None
    _, need, _, _ = backlog_note.counts(kitchen, payload)
    parts = [backlog_note.line(kitchen, payload, pans=False), chopping(kitchen, payload, need), *cooking(kitchen, payload),
             plating(kitchen, payload), serving(kitchen, payload)]
    return ' '.join(p for p in parts if p)


def apply(payload, kitchen):
    """What the step_check switch adds to an English request (harness.compose): state.step_check and the version."""
    found = line(kitchen, payload)
    if found is None:
        return None
    payload['state']['step_check'] = found
    payload['state']['step_check_version'] = VERSION
    return found
