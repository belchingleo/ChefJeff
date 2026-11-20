"""A factual note on option labels that pick up or serve a finished dish (the option_notes switch, a trial).

serve-note-v1 (serve_note): the serve option says which waiting order the held dish goes to and how long that order
has left, as the score rule picks it (the waiting order of the same dish with the earliest deadline), or that no
order is waiting for it. The label alone says only that serving an unwanted dish costs money.
serve-note-v2: an option that picks up a finished dish (take, put then take, pickup, put then pickup) says the same of
that dish ("Take Steak from Counter 6 (the Steak there goes to order O4, which waits for Steak: 30 s left)"), and so
does the serve line the links table gives such an option. In a 2026-11-19 play round a Steak lay on Counter 6 for 97 s
while O4 waited for one and expired twice: its take option said only "Take Steak from Counter 6", and the links table's
serve line said that serving a dish no order waits for costs money.

wait-note-v2 (removed 2026-11-20 with option-notes-v3): the wait option said what Jeff keeps in hand while waiting
and the continue option which step it continues and how long is left. In a 2026-11-19 re-ask of 40 moments where Jev
waited, adding it left 39 of 40 still waiting, the same as without it.

It reads only the request's own state (after translation and food names) and says nothing about what to do.
"""
from __future__ import annotations

SERVE_VERSION = 'serve-note-v2'
# The option_notes switch (2026-11-19: was serve_note and wait_note). option-notes-v1: serve-note-v1 + wait-note-v2;
# option-notes-v2: serve-note-v2 + wait-note-v2; option-notes-v3: serve-note-v2 alone.
VERSION = 'option-notes-v3'
SERVE_FOR = ' (the held {food} goes to order {order}, which waits for {dish}: {seconds:.0f} s left)'
SERVE_NONE = ' (no order is waiting for {dish} now)'
TAKE_FOR = ' (the {food} there goes to order {order}, which waits for {dish}: {seconds:.0f} s left)'
LINK_FOR = ' (the {food} goes to order {order}, which waits for {dish}: {seconds:.0f} s left)'
SERVE_LINE = 'Serve the plated dish'


def _held(payload):
    held = payload['state']['kitchen']['chefs'].get('jeff', {}).get('holding')
    return held if isinstance(held, dict) else None


def _dish_note(payload, food, form):
    """The note for a finished dish (a food entry of the request) in this form, or None for any other food."""
    if not isinstance(food, dict) or not food.get('dish'):
        return None
    kitchen = payload['state']['kitchen']
    names = {d['id']: d.get('name', d['id']) for d in kitchen.get('dishes', [])}
    dish = names.get(food['dish'], food['dish'])
    waiting = [o for o in kitchen.get('orders', []) if o.get('dish') == food['dish'] and o.get('status', 'pending') == 'pending']
    if not waiting:
        return SERVE_NONE.format(dish=dish)
    first = min(waiting, key=lambda o: (o.get('deadline', float('inf')), o.get('id', '')))
    return form.format(food=food.get('meaning'), order=first.get('id'), dish=dish, seconds=max(0.0, first.get('remaining', 0)))


def serve_note(payload):
    """The note for the serve option, or None when Jeff holds no finished dish."""
    return _dish_note(payload, _held(payload), SERVE_FOR)


def picked_dish(payload, key):
    """(v2) The finished dish an option picks up (take, put then take, pickup, put then pickup), or None."""
    kitchen = payload['state']['kitchen']
    for prefix in ('put then take ', 'take '):
        if key.startswith(prefix):
            food = (kitchen.get('stations', {}).get(key[len(prefix):]) or {}).get('food')
            return food if isinstance(food, dict) and food.get('dish') else None
    for prefix in ('put then pickup ', 'pickup '):
        if key.startswith(prefix):
            item = key[len(prefix):]
            for g in kitchen.get('ground', []):
                food = g.get('food') if isinstance(g, dict) else None
                if isinstance(food, dict) and food.get('id') == item:
                    return food if food.get('dish') else None
    return None


def apply_links(payload):
    """(v2) After the links table: the serve line given to an option that picks up a finished dish names its order."""
    table = payload['state'].get('option_links')
    if not isinstance(table, dict):
        return
    for key, lines in table.items():
        food = picked_dish(payload, key)
        note = _dish_note(payload, food, LINK_FOR) if food else None
        if note:
            table[key] = [line + note if line.startswith(SERVE_LINE) else line for line in lines]


def apply_serve(payload):
    """What the serve_note switch adds to an English request (harness.compose): the note and the version."""
    criteria = payload.get('questions', {}).get('next_action', {}).get('criteria', {})
    note = serve_note(payload)
    if note and 'serve' in criteria:
        criteria['serve'] = criteria['serve'] + note
    for key in criteria:
        food = picked_dish(payload, key)
        if food:
            criteria[key] += _dish_note(payload, food, TAKE_FOR)
    payload['state']['serve_note_version'] = SERVE_VERSION
    return note

