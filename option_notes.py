"""Two factual notes on option labels, each its own trial switch (features.json, off by default, no page switch).

serve-note-v1 (serve_note): the serve option says which waiting order the held dish goes to and how long that order
has left, as the score rule picks it (the waiting order of the same dish with the earliest deadline), or that no
order is waiting for it. The label alone says only that serving an unwanted dish costs money.

wait-note-v1 (wait_note): the wait option says what Jeff keeps in hand while waiting ("Wait, keeping the held beef
(as fetched) in hand"); with empty hands it stays "Wait".

Both read only the request's own state (after translation and food names) and say nothing about what to do.
"""
from __future__ import annotations

SERVE_VERSION = 'serve-note-v1'
WAIT_VERSION = 'wait-note-v1'
SERVE_FOR = ' (the held {food} goes to order {order}, which waits for {dish}: {seconds:.0f} s left)'
SERVE_NONE = ' (no order is waiting for {dish} now)'
WAIT_HOLDING = 'Wait, keeping the held {food} in hand'


def _held(payload):
    held = payload['state']['kitchen']['chefs'].get('jeff', {}).get('holding')
    return held if isinstance(held, dict) else None


def serve_note(payload):
    """The note for the serve option, or None when Jeff holds no finished dish."""
    held = _held(payload)
    if not held or not held.get('dish'):
        return None
    kitchen = payload['state']['kitchen']
    names = {d['id']: d.get('name', d['id']) for d in kitchen.get('dishes', [])}
    dish = names.get(held['dish'], held['dish'])
    waiting = [o for o in kitchen.get('orders', []) if o.get('dish') == held['dish'] and o.get('status', 'pending') == 'pending']
    if not waiting:
        return SERVE_NONE.format(dish=dish)
    first = min(waiting, key=lambda o: (o.get('deadline', float('inf')), o.get('id', '')))
    return SERVE_FOR.format(food=held.get('meaning'), order=first.get('id'), dish=dish, seconds=max(0.0, first.get('remaining', 0)))


def apply_serve(payload):
    """What the serve_note switch adds to an English request (harness.compose): the note and the version."""
    criteria = payload.get('questions', {}).get('next_action', {}).get('criteria', {})
    note = serve_note(payload)
    if note and 'serve' in criteria:
        criteria['serve'] = criteria['serve'] + note
    payload['state']['serve_note_version'] = SERVE_VERSION
    return note


def apply_wait(payload):
    """What the wait_note switch adds to an English request (harness.compose): the label and the version."""
    criteria = payload.get('questions', {}).get('next_action', {}).get('criteria', {})
    held = _held(payload)
    if held and 'wait' in criteria:
        criteria['wait'] = WAIT_HOLDING.format(food=held.get('meaning'))
    payload['state']['wait_note_version'] = WAIT_VERSION
    return criteria.get('wait')
