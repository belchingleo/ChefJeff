"""step-check-v3: for each kind of step the waiting orders need, whether the kitchen allows it now and, if not, what
stands in the way, from the engine's state and recipes.

A trial (features.json step_check, off by default, no page switch). Jeff reads the kitchen as some thirty stations of
fields, where a missing pan is only empty fields among many; he was told such things one note at a time. With this
switch on, a request on a floor where every board is on one chef's side gets one live field, state.step_check,
that says, in this order:

- what the waiting orders still need chopped (backlog below: needed, already fetched, still to fetch, within the
  reach of the chef on the boards' side to chop now: "the other chef's reach" on level 4, "your reach" when Jeff is on
  that side, as on level 5);
- (v2) fetching: from which supplies of what the waiting orders need fetching is possible now, and which give
  nothing while something lies on them (the engine lists no fetch from a supply that holds an item), and whose side
  they are on; in a 2026-11-19 play round a thrown bread landed on the fridge and no beef could be fetched for the
  rest of the round, while nothing in the request said why;
- chopping: which boards are free or hold something to chop, or that every board holds other food, and whose side
  they are on;
- cooking, for each vessel the waiting orders cook in: on which stoves it can start now; (v3) if none, but a stove has
  no vessel and a vessel of that kind that is empty or holds food still to cook is off the stoves, that it is
  possible once one is put on that stove, naming the stove and each vessel off the stoves with where it is and what
  it holds; only otherwise that it is not possible now (no
  vessel anywhere to put on a free stove, or no stove free);
- plating: where the clean plates and the plates with food are, or that there is no clean plate (where the dirty
  ones are, and how many are still with diners);
- serving: where it is done and whose side that is.

Level 5 (2026-11-19) swaps the chefs of level 4, so Jeff is the one on the boards' side: the field is given there too
(before, only while every board was on the other chef's side), its counts are of what is within his own reach to chop,
and the sides are named from his view as everywhere else. On level 4 nothing changes.
v3 (2026-11-19): v1 and v2 said "not possible now: every frying pan on a stove holds food or is on fire (Stove 2 holds
beef (burnt))" while Stove 1 had no pan and a pan of chopped beef stood on Counter 7; in that play round Jeff left the
pan there for 100 s and cooked nothing more. In the day's level-4 rounds 678 of the 739 requests that said cooking was
not possible had a stove without a pan and a pan elsewhere (in a hand, on a counter or on the floor).

Facts only, nothing about who should do what. It changes with every request (live part); step_check_version goes
with the static part. On any other floor nothing is added.
"""
from __future__ import annotations

from collections import Counter

VERSION = 'step-check-v3'


def _chopped_first(kitchen, item, state):
    heat = kitchen.rules.heat.get(item)
    return state == 'chopped' or (state == 'ready' and bool(heat) and heat.get('from') == 'chopped')


def chopper(kitchen):
    """The chef who alone reaches every board on a split floor ('human' or 'jeff'), else None."""
    boards = [s for s, e in kitchen.equipment.items() if e.get('type') == 'board']
    if not getattr(kitchen, 'split_floor', False) or not boards:
        return None
    for who, other in (('human', 'jeff'), ('jeff', 'human')):
        if all(kitchen.reaches(who, b) and not kitchen.reaches(other, b) for b in boards):
            return who
    return None


def applies(kitchen):
    """A split floor where every board is reached by one chef only: the other chef (level 4) or Jeff (level 5)."""
    return chopper(kitchen) is not None


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
    """(needed, fetched, to chop now within reach of the chef on the boards' side), each a Counter of ingredient ids."""
    cutter = chopper(kitchen) or 'human'
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
        if raw_to_chop(food) and kitchen.reaches(cutter, sid):
            ready[food['ingredient']] += 1
    for who, chef in k.get('chefs', {}).items():
        food = chef.get('holding')
        have.update(x for x in _items(food) if x in need)
        if who == cutter and raw_to_chop(food):
            ready[food['ingredient']] += 1
    for g in k.get('ground', []):
        food = g.get('food')
        have.update(x for x in _items(food) if x in need)
        if raw_to_chop(food) and kitchen.reaches(cutter, g.get('location')):
            ready[food['ingredient']] += 1
    for p in k.get('projectiles', []):
        have.update(x for x in _items(p) if x in need)
        cell = p.get('landing_cell') or [None, None]
        place = p.get('onto') or f'floor_{cell[0]}_{cell[1]}'
        try:
            reach = kitchen.reaches(cutter, place)
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
    reach = "the other chef's reach" if chopper(kitchen) == 'human' else 'your reach'
    order, need, have, ready = counts(kitchen, payload)

    def listed(counter):
        parts = [f'{item} {counter[item]}' for item in order if counter[item] > 0]
        return ', '.join(parts) if parts else 'none'
    if not any(need.values()):
        return 'The waiting orders need nothing that is chopped first.' + tail
    todo = Counter({item: max(0, need[item] - have[item]) for item in order})
    return (f'The waiting orders need, chopped first: {listed(need)}. Already fetched (in any state, plates included): '
            f'{listed(have)}. Still to fetch: {listed(todo)}. Within {reach} to chop now: {listed(ready)}.'
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


def _vessels_off(k, kind):
    """[(where, the vessel as the request names it)] for the vessels of a kind off the stoves: on a station, in a hand,
    on the floor."""
    found = []
    for sid, station in k.get('stations', {}).items():
        food = station.get('food')
        if isinstance(food, dict) and food.get('stage') == 'pot' and food.get('vessel') == kind and not station.get('stove'):
            found.append((station.get('name', sid), food))
    for who, chef in k.get('chefs', {}).items():
        food = chef.get('holding')
        if isinstance(food, dict) and food.get('stage') == 'pot' and food.get('vessel') == kind:
            found.append(('your hands' if who == 'jeff' else "the other chef's hands", food))
    for g in k.get('ground', []):
        food = g.get('food')
        if isinstance(food, dict) and food.get('stage') == 'pot' and food.get('vessel') == kind:
            found.append((g.get('near') or g.get('location'), food))
    return found


def _usable(vessel, items, cooks):
    """(v3) Whether a vessel off the stoves would cook on a stove: empty, or holding an item the orders cook in it, in the
    state it cooks from or still cooking."""
    contents = vessel.get('contents')
    if not isinstance(contents, dict):
        return not contents
    item = contents.get('ingredient')
    return item in items and contents.get('stage') in (cooks.get(item), 'cooking')


def _vessel_places(k, kind):
    """Where the vessels of a kind lie off the stoves: station names, hands, floor places."""
    return [where for where, _ in _vessels_off(k, kind)]


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
        free = [sid for sid in holding if not stations[sid].get('food') and not stations[sid].get('fire')]
        busy = []
        for sid in holding:
            if stations[sid].get('fire'):
                busy.append(f'{_name(stations, sid)} is on fire')
            elif stations[sid].get('food'):
                busy.append(f"{_name(stations, sid)} holds {_food(stations[sid]['food'])}")
        rest = f"; {'; '.join(busy)}" if busy else ''
        if free:
            lines.append(f"{what}: possible now on {', '.join(_name(stations, s) for s in free)}{rest}; the stoves are on "
                         f"{_side(kitchen, holding)}.")
            continue
        # (v3) A stove with no vessel, not on fire, and a vessel of this kind off the stoves: possible once it is put there.
        bare = [sid for sid in stoves if not stations[sid].get('pot_id') and not stations[sid].get('fire')]
        off = _vessels_off(k, kind)
        cooks = {c.get('item'): c.get('from') for c in ((k.get('vessels') or {}).get(kind) or {}).get('cooks', [])}
        if bare and any(_usable(food, items, cooks) for _, food in off):
            vessels = ', '.join(f'{where} ({_food(food)})' for where, food in off)
            lines.append(f"{what}: possible once a {name} is put on {' or '.join(_name(stations, s) for s in bare)} (no "
                         f"{name} there); {name}s off the stoves: {vessels}{rest}; the stoves are on {_side(kitchen, bare)}.")
        elif not holding:
            places = [where for where, _ in off]
            where = f" ({name}s: {', '.join(places)})" if places else ''
            fires = [f'{_name(stations, sid)} is on fire' for sid in stoves if stations[sid].get('fire')]
            lines.append(f"{what}: not possible now: no stove has a {name}{where}{('; ' + '; '.join(fires)) if fires else ''}.")
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
