"""backlog-note-v2: on a floor where only the other chef can chop, Jeff is told what the waiting orders still need chopped.

A trial (features.json backlog_note, off by default, no page switch). Jeff is asked one step at a time, and the request
lists the orders, their recipes and every item in the kitchen, but nowhere the total: how many ingredients that are
chopped before use the waiting orders need, how many of those are already fetched, and whether the other chef has one
to chop. With this switch on, a request on a floor where every board is on the other chef's side gets one field,
state.backlog, saying exactly that, counted from the request's own state and the engine's reach:

  "The waiting orders need, chopped first: beef 3, lettuce 2, tomato 2. Already fetched (in any state, plates
   included): beef 1, lettuce 1. Still to fetch: beef 2, lettuce 1, tomato 2. Within the other chef's reach to chop
   now: nothing."

Facts only: nothing about who should fetch or when. It changes with every request, so it goes in the live part;
backlog_note_version goes with the static part. On any other floor nothing is added.
v2 adds where the cooking vessels are, for each kind the stoves take: "Frying pans on stoves: 0 of 2 (Stove 1, Stove 2
without one); elsewhere: your hands, Counter 12." In a 2026-11-18 play round both pans stood on counters for 40 s
after plating from a held pan and emptying a burnt one, and nothing in the request said no stove had a pan.
"""
from __future__ import annotations

from collections import Counter

VERSION = 'backlog-note-v2'


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


def vessels(kitchen, payload):
    """For each kind of cooking vessel in the kitchen (as the vessels say it, on a stove or elsewhere): how many stoves
    have one, which stoves have none, and where the others are."""
    k = payload['state']['kitchen']
    names = {kind: v.get('name', kind) for kind, v in (k.get('vessels') or {}).items()}
    stations = k.get('stations', {})
    stoves = [sid for sid, station in stations.items() if station.get('stove')]
    bare = [sid for sid in stoves if not stations[sid].get('pot_id')]
    elsewhere = []                      # (kind, place)
    for sid, station in stations.items():
        food = station.get('food')
        if isinstance(food, dict) and food.get('stage') == 'pot' and not station.get('stove'):
            elsewhere.append((food.get('vessel'), station.get('name', sid)))
    for who, chef in k.get('chefs', {}).items():
        food = chef.get('holding')
        if isinstance(food, dict) and food.get('stage') == 'pot':
            elsewhere.append((food.get('vessel'), 'your hands' if who == 'jeff' else "the other chef's hands"))
    for g in k.get('ground', []):
        food = g.get('food')
        if isinstance(food, dict) and food.get('stage') == 'pot':
            elsewhere.append((food.get('vessel'), g.get('near') or g.get('location')))
    kinds = []
    for kind in [stations[sid].get('vessel') for sid in stoves] + [kind for kind, _ in elsewhere]:
        if kind and kind not in kinds:
            kinds.append(kind)
    parts = []
    for kind in kinds:
        on = [sid for sid in stoves if stations[sid].get('pot_id') and stations[sid].get('vessel') == kind]
        name = names.get(kind, kind)
        text = f'{name[:1].upper()}{name[1:]}s on stoves: {len(on)} of {len(stoves)}'
        if bare:
            text += f" ({', '.join(stations[sid].get('name', sid) for sid in bare)} without one)"
        places = [place for vessel, place in elsewhere if vessel == kind]
        if places:
            text += f"; elsewhere: {', '.join(places)}"
        parts.append(text + '.')
    return ' '.join(parts)


def line(kitchen, payload, pans=True):
    """The field's text, or None on another floor. pans=False leaves the vessels sentence out (step_check says it)."""
    if not applies(kitchen):
        return None
    vessel_text = vessels(kitchen, payload) if pans else ''
    tail = (' ' + vessel_text) if vessel_text else ''
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


def apply(payload, kitchen):
    """What the backlog_note switch adds to an English request (harness.compose): state.backlog and the version."""
    found = line(kitchen, payload)
    if found is None:
        return None
    payload['state']['backlog'] = found
    payload['state']['backlog_note_version'] = VERSION
    return found
