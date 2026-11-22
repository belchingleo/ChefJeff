"""Work notes (three trials, features.json, off by default, no page switch): facts on options about the work they
lead to, worked out by the engine on forks of the request's kitchen, the same way on every level.

The 2026-11-21 diagnosis of level-5 loops: Jev picks its top-probability option almost every time, so once the
kitchen stops changing it repeats; with the request parts on, Jeff's boards jammed and the options that could have
moved the work on carried no line, while putting down and taking back did. These notes give the useful options the
facts the others already had.

- own_chain (own-chain-v1): an option after which Jeff holds an item (taking, fetching, picking up, lifting) gets
  Jeff's own shortest run of steps on that item that ends in work, at most OWN_DEPTH steps, or in handing it over
  (a throw to the other chef, or a put on a counter they reach) after which the other chef's chain on it ends in work:
  ". If nothing else changes first, then you could: Put the held tomato (as fetched) on Board 1, then Chop ...", or
  "... then you could: Throw to the other chef; then the other chef could: Put the held beef (chopped) in the frying
  pan on Stove 1". A run of one work step is left out: the links table already names the work an option makes
  possible. Nothing when no such run exists.
- plate_result (plate-result-v2): an option that puts food on a plate or fills one (assemble, plate from a pan or
  pot, add to the held plate) says what the plate is then and which waiting order asks for it: " (makes a Steak;
  order O4 waits for a Steak, 29.9 s left)", " (makes a Steak; no waiting order asks for a Steak)", or " (the plate
  then still needs tomato (chopped) for a Burger; order O3 waits for a Burger, 31.7 s left)". v2 (2026-11-22): a
  plate with burnt food says what serving it does, as the engine's serve step and burnt-food scoring give it once
  plated (servability.py): with a waiting order for the dish, its tier (" (makes a burnt Steak: order O4 accepts it
  at -10 yuan)", " (makes a burnt Steak: refused)"), and with none, the wrong-dish cost whatever the tier (" (makes a
  burnt Steak; no waiting order asks for a Steak, so serving it costs 20 yuan)"); a part-made plate that a waiting
  order's dish needs ends "; burnt food: refused)" or "; burnt food: accepted at -10 yuan)"; v1 said " (makes a
  burnt dish)" whatever the tier.
- board_taken (board-taken-v1): a put on a board of an item that is not chopped there (in next_action and in
  put_where) says " (Board 1 is then taken; 2 ingredients you can reach still need chopping)".

Each says what is, never what to do. The versions go with the static part.
"""
from __future__ import annotations

import contextlib

import servability

OWN_CHAIN_VERSION = 'own-chain-v1'
PLATE_RESULT_VERSION = 'plate-result-v2'
BOARD_TAKEN_VERSION = 'board-taken-v1'
SWITCHES = {'own_chain': ('own', OWN_CHAIN_VERSION), 'plate_result': ('plate', PLATE_RESULT_VERSION),
            'board_taken': ('board', BOARD_TAKEN_VERSION)}
HOLDS = ('fetch', 'take_board', 'take_counter', 'take_plate', 'take_return', 'take_sink', 'pickup', 'lift_pot')
PLATING = ('assemble', 'assemble_ground', 'merge_plates', 'plate_counter', 'plate_from_counter', 'plate_pot',
           'plate_ground', 'plate_partner')
OWN_DEPTH = 2
OWN = '. If nothing else changes first, then you could: '


def flags(features):
    """compose_payload's work switches for these features ({'own': bool, 'plate': bool, 'board': bool}), or None."""
    value = {short: bool((features.get(name) or {}).get('on')) for name, (short, _) in SWITCHES.items()}
    return value if any(value.values()) else None


def _texts(kitchen, actions, names):
    import engine_english
    import food_names
    unmark = food_names.unmark if names else (lambda text: text)
    with (food_names.naming() if names else contextlib.nullcontext()):
        return [unmark(engine_english.text(a)) for a in actions]


def _handover(state, after, item):
    """The other chef's chain on the item after a hand-over (links.partner_chain), when it ends in work."""
    import links
    chain = links.partner_chain(state, after, 'jeff', item)
    return chain if chain and chain[-1].kind in links.WORK else None


def own_chain(kitchen, twin, item, origin=None):
    """(Jeff's steps, the other chef's steps or []) on the item from the fork twin, or None (see the docstring).
    origin: where the option took the item from; a run that puts it back there is not one."""
    import links
    frontier = [(twin, [])]
    for _ in range(OWN_DEPTH):
        nxt = []
        for state, path in frontier:
            shared = None
            for a in state.actions('jeff'):
                if not links._names_item(a.expected, item) or (origin is not None and a.target == origin):
                    continue
                if a.kind in links.WORK:
                    return path + [a], []
                if a.kind == 'throw' and a.key == 'throw partner' or (
                        a.kind == 'put_counter' and shared is None and state.reaches('human', a.target)):
                    if a.kind == 'put_counter':
                        shared = a
                    fork = links._fork(state)
                    if links._run(fork, 'jeff', a):
                        other = _handover(state, fork, item)
                        if other:
                            return path + [a], other
                    continue
                if a.kind in ('put_board',):
                    fork = links._fork(state)
                    if links._run(fork, 'jeff', a):
                        nxt.append((fork, path + [a]))
        frontier = nxt[:4]
    return None


def _own_note(kitchen, option, names):
    import food_names
    if option.kind not in HOLDS:
        return None
    # Labels are written when actions are listed, so the forks list them in naming mode, as links.table does.
    with (food_names.naming() if names else contextlib.nullcontext()):
        return _own_note_named(kitchen, option, names)


def _own_note_named(kitchen, option, names):
    import links
    twin = links._fork(kitchen)
    if any(getattr(twin, 'manual', {}).get('human', (0.0, 0.0))):
        twin.set_manual('human', 0, 0)
    if not links._carry_out(twin, 'jeff', option, [], None):
        return None
    held = twin.chefs['jeff'].hand
    if held is None:
        return None
    found = own_chain(kitchen, twin, held.id, option.target)
    if not found:
        return None
    mine, theirs = found
    if len(mine) == 1 and not theirs:          # one work step: the links table names it already
        return None
    import food_names
    # The engine's put label says "the held item"; here it is the item Jeff would hold then.
    held_name = food_names.plain(twin, held) if held.stage not in ('clean_plate', 'dirty_plate', 'pot', 'extinguisher') \
        else None
    steps = [t.replace('the held item', f'the held {held_name}') if held_name else t for t in _texts(twin, mine, names)]
    text = OWN + ', then '.join(steps)
    if theirs:
        text += '; ' + links.THEN + ', then '.join(_texts(twin, theirs, names))
    return text


def _plate_food(twin, option):
    hand = twin.chefs['jeff'].hand
    if hand is not None and hand.plate_id:
        return hand
    station = twin.stations.get(option.target)
    if station is not None and station.food is not None and station.food.plate_id:
        return station.food
    for item in getattr(twin, 'ground', {}).values():
        if item.location == option.target and item.food is not None and item.food.plate_id:
            return item.food
    return None


def _english(name):
    from model_language import english_text
    return english_text(name)


def _waiting(snapshot, dish):
    orders = [o for o in snapshot.get('orders', []) if o.get('status') == 'pending' and o.get('dish') == dish]
    return min(orders, key=lambda o: o.get('remaining', 0)) if orders else None


def _plate_note(kitchen, option):
    import food_names
    import links
    if option.kind not in PLATING:
        return None
    twin = links._fork(kitchen)
    if any(getattr(twin, 'manual', {}).get('human', (0.0, 0.0))):
        twin.set_manual('human', 0, 0)
    if not links._carry_out(twin, 'jeff', option, [], None):
        return None
    food = _plate_food(twin, option)
    if food is None:
        return None
    snapshot = twin.snapshot()
    names = {d['id']: _english(d.get('name', d['id'])) for d in snapshot.get('menu', [])}
    # v2: burnt food's tier as the dish is once plated (off the stove its burnt time stands still), from the engine,
    # when a waiting order would take it; with none, serving it costs the wrong-dish penalty whatever the tier.
    status = twin.burnt_service(food)
    if food.stage == 'burnt' and status is None:        # rules without burnt tiers
        return ' (makes a burnt dish)'
    dish = twin.dish(food)
    if dish:
        order = _waiting(snapshot, dish)
        name = names.get(dish, dish)
        if status and not order:
            return (f" (makes a burnt {name}; no waiting order asks for a {name}, so serving it costs "
                    f"{-twin.rules.penalty['wrong_dish']} yuan)")
        if status and status['outcome'] == 'rejected':
            return f' (makes a burnt {name}: refused)'
        if status:
            return f" (makes a burnt {name}: order {order['id']} accepts it at -{-status['adjustment']} yuan)"
        if order:
            return f" (makes a {name}; order {order['id']} waits for a {name}, {order['remaining']:.1f} s left)"
        return f' (makes a {name}; no waiting order asks for a {name})'
    parts = twin.parts(food)
    best = None
    for recipe in snapshot.get('menu', []):
        need = {c['item']: c['state'] for c in recipe.get('components', [])}
        if not parts <= set(need):
            continue
        order = _waiting(snapshot, recipe['id'])
        rank = (order is None, order['remaining'] if order else 0)
        if best is None or rank < best[0]:
            best = (rank, recipe, order, need)
    if best is None:
        return ' (the plate then makes no dish on the menu)'
    _, recipe, order, need = best
    missing = ', '.join(food_names.item_state(item, state) for item, state in need.items() if item not in parts)
    name = names.get(recipe['id'], recipe['id'])
    tail = (f"order {order['id']} waits for a {name}, {order['remaining']:.1f} s left" if order
            else f'no waiting order asks for a {name}')
    if status and order:            # the tier only for an order that would take the dish
        tail += '; burnt food: ' + ('refused' if status['outcome'] == 'rejected' else servability.accepted(status))
    return f' (the plate then still needs {missing} for a {name}; {tail})'


def _board_note(kitchen, option):
    if option.kind != 'put_board' or option.target not in getattr(kitchen, 'boards', ()):
        return None
    held = kitchen.chefs['jeff'].hand
    if held is None or kitchen.rules.choppable(held):
        return None
    waiting = 0
    for sid, station in kitchen.stations.items():
        food = station.food
        if food is not None and food.id != held.id and kitchen.rules.choppable(food) and kitchen.reaches('jeff', sid):
            waiting += 1
    for item in getattr(kitchen, 'ground', {}).values():
        food = item.food
        if food is not None and kitchen.rules.choppable(food) and kitchen.reaches('jeff', item.location):
            waiting += 1
    name = _english(kitchen.stations[option.target].name)
    count = (f'{waiting} ingredient you can reach still needs chopping' if waiting == 1
             else f'{waiting} ingredients you can reach still need chopping')
    return f' ({name} is then taken; {count})'


def apply(payload, kitchen, actions, own=False, plate=False, board=False, names=False):
    """What the work switches add to an English request (jev.compose_payload): the notes and the versions."""
    questions = payload.get('questions', {})
    criteria = questions.get('next_action', {}).get('criteria', {})
    by_key = {a.key: a for a in actions}
    for key in list(criteria):
        a = by_key.get(key)
        if a is None:
            continue
        for on, note in ((plate, _plate_note), (board, _board_note)):
            if not on:
                continue
            try:
                text = note(kitchen, a)
            except Exception:      # a fork the engine cannot carry out: say nothing
                text = None
            if text:
                criteria[key] += text
        if own:
            try:
                text = _own_note(kitchen, a, names)
            except Exception:
                text = None
            if text:
                criteria[key] += text
    if board:
        places = (questions.get('put_where') or {}).get('criteria', {})
        listed = {a.key: a for a in kitchen.actions('jeff')}
        for key in list(places):
            a = listed.get(key)
            text = _board_note(kitchen, a) if a is not None else None
            if text:
                places[key] += text
    state = payload['state']
    for on, (name, (_, version)) in zip((own, plate, board), SWITCHES.items()):
        if on:
            state[f'{name}_version'] = version
    return payload
