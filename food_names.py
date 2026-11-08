"""names-v1: every food Jeff is told about is named from its ingredient and state, as the recipes are.

A trial (features.json food_names, off by default, no page switch). Today the names Jeff reads are the page's
display names, translated: beef has short state names of its own from when it was the only ingredient, so raw
beef reads "Raw meat", chopped beef "Chopped" and cooked beef "Cooked", while the recipes, the orders and a
plate's missing list say "beef (cooked)"; the fridge's fetch action says "raw meat", and no station says which
ingredient it supplies. Ingredients a player level uses get names of their own (chicken and fish both cook as
"Frying"), none of them checked against what Jeff reads.

With the switch on, a request names every loose ingredient "<item> (<state>)" with the recipes' own words
(beef (as fetched), beef (chopped), beef (cooking), beef (cooked), beef (burnt)), a plate by its dish or as
"plate with ..." its components, and a pot or pan by its kind and contents; every action label that names food
uses the same name (Fetch beef (as fetched), Take beef (cooked) from Counter 2, ...), and each ingredient source
says which ingredient it supplies. The names are built from the ingredient ids and states, so an ingredient or
level added later is named the same way with nothing to write by hand. Only Jeff's request changes: the page,
the engine's events and the records' engine inputs are as before, and with the switch off the request is
byte-identical.

How: while the request is built the engine is put in naming mode (Kitchen.food_names), in which every food name
it would write is a marked name; the request is translated as usual and the marks are then removed
(unmark), so a name is never run through the translation of display text.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace

VERSION = 'names-v1'
# A state as the recipes say it (harness.STATE_WORDS, extended to the states no recipe asks for).
WORDS = {'raw': 'as fetched', 'chopped': 'chopped', 'cooking': 'cooking', 'ready': 'cooked', 'burnt': 'burnt'}
OPEN, CLOSE = '\u27e6', '\u27e7'      # marks around a name until the request is translated
# Naming mode, read by the engine's name functions (Kitchen.food_names). A context variable, not a kitchen attribute:
# Jeff's harness reads the kitchen through a read-only view (environment.ReadOnlyKitchen), and nothing in the
# kitchen changes while a request is built.
NAMING = ContextVar('food_names', default=False)
RULE = ('Food is named by its ingredient and state as the recipes are: "beef (chopped)", "beef (cooked)"; the states are '
        'as fetched, chopped, cooking, cooked and burnt. A plate is named by its dish when the orders of this round can ask for that dish, else "plate with" its components; a '
        'cooking vessel by its kind (frying pan or soup pot; the rules say pot for either) and contents. An ingredient source '
        'gives its ingredient in supplies.')


def item_state(item, stage):
    return f'{item} ({WORDS.get(stage, stage)})'


def mark(text):
    return OPEN + text + CLOSE


def describe(kitchen, food):
    """The marked name of a food object in the engine (Food), or None for the objects named as before
    (plates without food, the extinguisher)."""
    if food is None or food.stage in ('extinguisher', 'clean_plate', 'dirty_plate'):
        return None
    if food.stage == 'pot':
        vessel = kitchen.vessel_name(food.id)
        return mark(f'{vessel} with {plain(kitchen, food.contents)}' if food.contents else f'empty {vessel}')
    return mark(plain(kitchen, food))


def plain(kitchen, food):
    if food.plate_id:
        dish = kitchen.dish(food)
        if food.stage == 'burnt':
            return 'burnt dish'
        if dish and dish in kitchen.rules.menu:      # a dish this round's orders can ask for
            return kitchen.recipe_name(dish)
        return 'plate with ' + ', '.join(food.components or (food.ingredient,))
    return item_state(food.ingredient, food.stage)


def state(snapshot):
    """The snapshot as a named request sees it: each food's meaning is its marked name, from the snapshot's own
    fields, and each ingredient source says what it supplies (the map's equipment knows; the model input leaves
    the map's item out as a display field)."""
    menu = {d['id'] for d in snapshot.get('menu', [])}
    dishes = {d['id']: d.get('name', d['id']) for d in snapshot.get('dishes', []) if d['id'] in menu}
    vessels = {kind: v.get('name', kind) for kind, v in (snapshot.get('vessels') or {}).items()}

    def food(f):
        if not isinstance(f, dict):
            return f
        f = dict(f)
        if f.get('stage') == 'pot':
            contents = food(f.get('contents'))
            vessel = vessels.get(f.get('vessel'), f.get('vessel') or 'pot')
            inner = contents['meaning'][1:-1] if contents else None
            f['contents'] = contents
            f['meaning'] = mark(f'{vessel} with {inner}' if inner else f'empty {vessel}')
        elif f.get('ingredient') and f.get('stage') not in ('extinguisher', 'clean_plate', 'dirty_plate'):
            if f.get('plate_id'):
                text = ('burnt dish' if f['stage'] == 'burnt' else dishes.get(f.get('dish'), f.get('dish')) if f.get('dish')
                        else 'plate with ' + ', '.join(f.get('components') or [f['ingredient']]))
            else:
                text = item_state(f['ingredient'], f['stage'])
            f['meaning'] = mark(text)
        return f

    out = dict(snapshot)
    supplies = {key: e['item'] for key, e in (snapshot.get('map') or {}).get('equipment', {}).items()
                if e.get('type') == 'ingredient_source' and e.get('item')}
    out['stations'] = {key: {**s, 'food': food(s.get('food')), **({'supplies': supplies[key]} if key in supplies else {})}
                       for key, s in snapshot.get('stations', {}).items()}
    out['ground'] = [{**g, 'food': food(g.get('food'))} if isinstance(g, dict) else g for g in snapshot.get('ground', [])]
    out['chefs'] = {who: {**c, 'holding': food(c.get('holding'))} for who, c in snapshot.get('chefs', {}).items()}
    return out


@contextmanager
def naming():
    """The engine's labels and names in naming mode for the duration (restored after)."""
    token = NAMING.set(True)
    try:
        yield
    finally:
        NAMING.reset(token)


def labels(kitchen, actions, one_press=None):
    """The listed actions with their labels as the engine writes them in naming mode (same keys, same order)."""
    with naming():
        fresh = kitchen.actions('jeff')
        if one_press:
            import one_press as presses
            fresh = fresh + presses.options(kitchen, 'jeff', fresh, one_press)
    named = {a.key: a.label for a in fresh}
    return [replace(a, label=named.get(a.key, a.label)) for a in actions]


def unmark(value):
    """The translated request with the marks taken off."""
    if isinstance(value, str):
        return value.replace(OPEN, '').replace(CLOSE, '') if OPEN in value or CLOSE in value else value
    if isinstance(value, dict):
        return {k: unmark(v) for k, v in value.items()}
    if isinstance(value, list):
        return [unmark(v) for v in value]
    return value


def apply(payload):
    """What the switch adds to a translated request: the marks off, the naming rule and the version."""
    payload = unmark(payload)
    rules = payload['state']['rules']
    rules['food_names'] = RULE
    if isinstance(rules.get('continuity'), str):      # it named fetched beef "raw meat"
        rules['continuity'] = rules['continuity'].replace('fetching more raw meat', 'fetching more of an ingredient')
    payload['state']['food_names_version'] = VERSION
    return payload
