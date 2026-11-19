"""step-check-v1: for each kind of step the waiting orders need, whether the kitchen allows it now and, if not, what
stands in the way, from the engine's state and recipes.

A trial (features.json step_check, off by default, no page switch). Jeff reads the kitchen as some thirty stations of
fields, where a missing pan is only empty fields among many; he was told such things one note at a time. With this
switch on, a request on a floor where every board is on the other chef's side gets one live field, state.step_check,
that says, in this order:

- what the waiting orders still need chopped (backlog below: needed, already fetched, still to fetch, within the
  other chef's reach to chop now);
- (v2) fetching: from which supplies of what the waiting orders need fetching is possible now, and which give
  nothing while something lies on them (the engine lists no fetch from a supply that holds an item), and whose side
  they are on; in a 2026-11-19 play round a thrown bread landed on the fridge and no beef could be fetched for the
  rest of the round, while nothing in the request said why;
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

from collections import Counter

VERSION = 'step-check-v2'


def _chopped_first(kitchen, item, state):
    heat = kitchen.rules.heat.get(item)
    return state == 'chopped' or (state == 'ready' and bool(heat) and heat.get('from') == 'chopped')


def applies(kitchen):
    """A split floor where every board is reached by the other chef only (Jeff cannot chop)."""
    boards = [s for s, e in kitchen.equipment.items() if e.get('type') == 'board']
    return (getattr(kitchen, 'split_floor', False) and bool(boards)
            and all(kitchen.reaches('human', b) and not kitchen.reaches('jeff', b) for b in boards))


def _items(food):
    """The ingredient ids in one food entry of the request: a loose ingredient, a plate's components, a pot's contents."""
    if not isinstance(food, dict) or food.get('stage') == 'burnt':
        return []
    if food.get('plate_id') or food.get('ingredient') == 'dish':
        return list(food.get('components') or [])
    contents = food.get('contents')
    if isinstance(contents, dict):
        return _items(contents)
    if isinstance(contents, list):
        return [x for c in contents for x in _items(c)]
    return [food['ingredient']] if food.get('ingredient') else []


def counts(kitchen, payload):
    """(needed, fetched, to chop now within the other chef's reach), each a Counter of ingredient ids."""
    k = payload['state']['kitchen']
    order = []
    need = Counter()
    for o in k.get('orders', []):
        if o.get('status') != 'pending' or o.get('dish') not in kitchen.rules.recipes:
            continue
        for c in kitchen.rules.recipes[o['dish']]['components']:
            if _chopped_first(kitchen, c['item'], c['state']):
                need[c['item']] += 1
                if c['item'] not in order:
                    order.append(c['item'])
    have, ready = Counter(), Counter()

    def raw_to_chop(food):
        return (isinstance(food, dict) and not food.get('plate_id') and food.get('stage') == 'raw'
                and food.get('ingredient') in need)

    for sid, station in k.get('stations', {}).items():
        food = station.get('food')
        have.update(x for x in _items(food) if x in need)
        if raw_to_chop(food) and kitchen.reaches('human', sid):
            ready[food['ingredient']] += 1
    for who, chef in k.get('chefs', {}).items():
        food = chef.get('holding')
        have.update(x for x in _items(food) if x in need)
        if who == 'human' and raw_to_chop(food):
            ready[food['ingredient']] += 1
    for g in k.get('ground', []):
        food = g.get('food')
        have.update(x for x in _items(food) if x in need)
        if raw_to_chop(food) and kitchen.reaches('human', g.get('location')):
            ready[food['ingredient']] += 1
    for p in k.get('projectiles', []):
        have.update(x for x in _items(p) if x in need)
        cell = p.get('landing_cell') or [None, None]
        place = p.get('onto') or f'floor_{cell[0]}_{cell[1]}'
        try:
            reach = kitchen.reaches('human', place)
        except (KeyError, ValueError, TypeError):
            reach = False
        if raw_to_chop(p) and reach:
            ready[p['ingredient']] += 1
    return order, need, have, ready


def backlog(kitchen, payload):
    """What the waiting orders still need chopped, or None on another floor."""
    if not applies(kitchen):
        return None
    tail = ''
    order, need, have, ready = counts(kitchen, payload)

    def listed(counter):
        parts = [f'{item} {counter[item]}' for item in order if counter[item] > 0]
        return ', '.join(parts) if parts else 'none'
    if not any(need.values()):
        return 'The waiting orders need nothing that is chopped first.' + tail
    todo = Counter({item: max(0, need[item] - have[item]) for item in order})
    return (f'The waiting orders need, chopped first: {listed(need)}. Already fetched (in any state, plates included): '
            f'{listed(have)}. Still to fetch: {listed(todo)}. Within the other chef\'s reach to chop now: {listed(ready)}.'
            .replace('chop now: none.', 'chop now: nothing.') + tail)


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


def fetching(kitchen, payload):
    """(v2) Fetching what the waiting orders need: possible now from which supplies, and which give nothing while
    something lies on them."""
    k = payload['state']['kitchen']
    stations = k.get('stations', {})
    needed = []
    for o in k.get('orders', []):
        if o.get('status') != 'pending' or o.get('dish') not in kitchen.rules.recipes:
            continue
        for c in kitchen.rules.recipes[o['dish']]['components']:
            if c['item'] not in needed:
                needed.append(c['item'])
    sources = sorted(((sid, item) for sid, item in kitchen.ingredients.items() if item in needed),
                     key=lambda s: needed.index(s[1]))
    if not sources:
        return None
    free, blocked = [], []
    for sid, item in sources:
        food = stations.get(sid, {}).get('food')
        if food is None:
            free.append(f'{_name(stations, sid)} ({item})')
        else:
            blocked.append(f'{_name(stations, sid)} ({item}) gives nothing while {_food(food)} lies on it')
    side = _side(kitchen, [sid for sid, _ in sources])
    parts = ([f"possible now from {', '.join(free)}"] if free else ['not possible now from any supply']) + blocked
    return f"Fetching: {'; '.join(parts)}; the supplies are on {side}."


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
    if not applies(kitchen):
        return None
    _, need, _, _ = counts(kitchen, payload)
    parts = [backlog(kitchen, payload), fetching(kitchen, payload), chopping(kitchen, payload, need), *cooking(kitchen, payload),
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
