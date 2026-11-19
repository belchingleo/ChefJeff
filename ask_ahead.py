"""Ask ahead (features.json ask_ahead, a trial, ask-ahead-v2): ask Jeff for his next step before this one ends.

Today Jeff is asked when a step ends, at T, and acts when the answer comes, at T+L: he stands for L. When a request
sent now could not be answered before his step ends (jev.DecisionLoop.outlasts_reply, the moment today's loop
chooses not to ask), the loop instead plays a fork of the kitchen forward to the end of that step and asks with the
state at T, in exactly the format of any request. The answer is held until the step ends and carried out only if the
step ended as predicted (action_done), what Jeff holds matches the prediction, no order or pan crossed a countdown
band since, the chosen action is still listed, and the answer is not too old; otherwise it is dropped and Jeff is
asked at once as today. What Jeff knows of the other chef is as old either way; the kitchen's clocks (pans, orders)
are more accurate, played forward to T. Research replay redoes the same prediction (predict) to rebuild the request.

v2 (2026-11-19, was the ahead_throw trial, ahead-throw-v1): "still listed" means the same key for the same object,
and a throw to the other chef aims at where they stand, so any step the other chef took before Jeff's step ended
dropped a held "throw partner" (in the five level-4 play rounds of 2026-11-18, 33 of the 38 answers dropped as not
listed; asked again, 31 came back as the same throw, about 2.5 s later). A held "throw partner" is now carried out
while Jeff still holds the same item and can still throw to the other chef, aimed at where they stand now (the throw
the engine lists then): in the three play rounds of 2026-11-19 no throw was dropped. Nothing in what Jeff is asked
changes.
"""
from __future__ import annotations

VERSION = 'ask-ahead-v2'
PARTNER = 'throw partner'
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


def still_listed(listed, chosen):
    """The listed action that carries out a held answer, or None: the same key for the same object; a throw to the
    other chef is the same throw while Jeff holds the same item, aimed where the other chef stands now."""
    same = next((a for a in listed if a.key == chosen.key and a.expected == chosen.expected), None)
    if same is not None or chosen.key != PARTNER or chosen.kind != 'throw':
        return same
    return next((a for a in listed if a.key == PARTNER and a.kind == 'throw' and a.expected[:1] == chosen.expected[:1]), None)
