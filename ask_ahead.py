"""Ask ahead (features.json ask_ahead, a trial, ask-ahead-v1): ask Jeff for his next step before this one ends.

Today Jeff is asked when a step ends, at T, and acts when the answer comes, at T+L: he stands for L. When a request
sent now could not be answered before his step ends (jev.DecisionLoop.outlasts_reply, the moment today's loop
chooses not to ask), the loop instead plays a fork of the kitchen forward to the end of that step and asks with the
state at T, in exactly the format of any request. The answer is held until the step ends and carried out only if the
step ended as predicted (action_done), what Jeff holds matches the prediction, no order or pan crossed a countdown
band since, the chosen action is still listed, and the answer is not too old; otherwise it is dropped and Jeff is
asked at once as today. What Jeff knows of the other chef is as old either way; the kitchen's clocks (pans, orders)
are more accurate, played forward to T. Research replay redoes the same prediction (predict) to rebuild the request.
"""
from __future__ import annotations

VERSION = 'ask-ahead-v1'
STEP = .05                      # the engine substep the fork advances by
GRACE = 1.0                     # game seconds past the step's own time before the prediction gives up


def predict(kitchen, who='jeff'):
    """A fork of the kitchen played forward until the chef's current step ends, the other chef keeping what it does
    with no new input (a walk by hand stops where it is); None when that step does not end with action_done."""
    job = kitchen.chefs[who].job
    if job is None:
        return None
    twin = kitchen.fork()
    other = 'human' if who == 'jeff' else 'jeff'
    if any(getattr(twin, 'manual', {}).get(other, (0.0, 0.0))):
        twin.set_manual(other, 0, 0)
    limit = max(0.0, job.travel) + max(0.0, job.work) + GRACE
    cursor, waited = len(twin.events), 0.0
    while not twin.ended and waited < limit:
        current = twin.chefs[who].job
        if current is None or current.id != job.id:
            break
        twin.advance(STEP)
        waited += STEP
    done = any(e.get('actor') == who and e.get('action_id') == job.id and e.get('kind') == 'action_done'
               for e in twin.events[cursor:])
    return twin if done and twin.chefs[who].job is None else None


def hand(kitchen, who='jeff'):
    """What the chef holds, as the check after the step compares it: the item's id and stage, or None."""
    item = kitchen.chefs[who].hand
    return [item.id, item.stage] if item else None
