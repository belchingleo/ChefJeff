"""Links between an option and the work it makes possible (links-v1): condition B of the links check.

Condition A is Jeff's request as the game sends it. Condition B is the same request with one fact added to some
options: the work Jeff could do after it that he cannot do now, as the engine computes it. For each listed option,
a fork of the kitchen (Kitchen.fork, as ask_ahead.py uses) carries the option out to its end, the other chef
keeping what it does with no new input; the work actions Jeff has then and not now are the option's link. Only
work counts (chop, put in a pan or pot, plate or assemble, serve, put a dirty plate in the sink, wash), never
walking, putting down, throwing, fetching or taking, so the line names where an option leads and nothing else.
An option that leads to no new work gets no line.

It says what becomes possible, never what Jeff should do, and the same rule holds for every level and ingredient
(nothing is written by hand). Built offline for re-asking logged moments; the game does not use it.
"""
from __future__ import annotations

from model_language import english_text

VERSION = 'links-v1'
# The work an option can lead to: harness.WORK_KINDS without fetching and taking, plus putting a dirty plate in the sink.
WORK = ('chop', 'put_pot', 'load_counter', 'load_ground', 'assemble', 'assemble_ground', 'plate_pot', 'plate_counter',
        'plate_from_counter', 'plate_ground', 'plate_partner', 'serve', 'put_sink', 'wash')
STEP = .05
GRACE = 1.0
MOST = 5                        # work actions named per option, in the engine's order
LEAD = ' If nothing else changes first, afterwards you can: '
RULE = ('Some options of next_action end with "If nothing else changes first, afterwards you can: ...". It names the '
        'work (chop, put in a pan or pot, plate or assemble, serve, put a dirty plate in the sink, wash) you could do '
        'after that option and cannot do now, as the game computes it with the other chef going on with what they are '
        'doing. It does not say whether you should choose that option.')


def _carry_out(twin, who, first, rest, place):
    """Start the option in the fork and run it, step after step, until its last step ends; False if a step cannot start."""
    import one_press
    steps = [first] + list(rest)
    for n, step in enumerate(steps):
        if n == 0 and step == 'put':
            action, _ = one_press.place(twin.actions(who), place)
        elif n == 0:
            action = step
        else:
            action = one_press.find(twin, who, step)
        if action is None:
            return n > 0
        started = twin.start(who, action)
        if isinstance(started, tuple):
            started = started[0]
        if not started:
            return n > 0
        job = twin.chefs[who].job
        if job is None:
            continue
        limit = max(0.0, job.travel) + max(0.0, job.work) + GRACE
        waited = 0.0
        while not twin.ended and waited < limit and twin.chefs[who].job is not None and twin.chefs[who].job.id == job.id:
            twin.advance(STEP)
            waited += STEP
        if twin.chefs[who].job is not None and twin.chefs[who].job.id == job.id:
            return False
    return True


def _work(actions):
    return {(a.kind, a.target): a for a in actions if a.kind in WORK}


def link(kitchen, who, option, now, place=None):
    """The work actions (engine Actions) the option leads to: listed after it, not listed now. [] when none or when the
    option cannot be carried out to its end in the fork."""
    import one_press
    twin = kitchen.fork()
    other = 'human' if who == 'jeff' else 'jeff'
    if any(getattr(twin, 'manual', {}).get(other, (0.0, 0.0))):
        twin.set_manual(other, 0, 0)
    if option.kind in ('wait', 'stop'):
        return []
    if option.kind in one_press.KINDS:
        rest = one_press.steps(option, twin)
        first = 'put' if twin.chefs[who].hand is not None else one_press.find(twin, who, rest[0])
        if first != 'put':
            rest = rest[1:]
    elif option.kind == 'continue':
        job = twin.chefs[who].job
        if job is None:
            return []
        first, rest = None, []
    else:
        first, rest = option, []
    if first is None and option.kind == 'continue':
        job = twin.chefs[who].job
        limit, waited = max(0.0, job.travel) + max(0.0, job.work) + GRACE, 0.0
        while not twin.ended and waited < limit and twin.chefs[who].job is not None:
            twin.advance(STEP)
            waited += STEP
        if twin.chefs[who].job is not None:
            return []
    elif first is None or not _carry_out(twin, who, first, rest, place):
        return []
    before = _work(now)
    after = _work(twin.actions(who))
    return [a for key, a in after.items() if key not in before][:MOST]


def sentence(actions):
    """The line added to an option, in the request's English, or '' for no new work."""
    if not actions:
        return ''
    return LEAD + '; '.join(english_text(a.label) for a in actions)


def annotate(payload, kitchen, who, actions, names=False):
    """Condition B of a request (a translated payload, as sent): the same request with each option's link added to its
    label, the rule, and the version. actions are the request's listed actions (the engine's and one-press options),
    in the kitchen the request describes. Returns (payload, {option key: [(linked key, engine label)]})."""
    import contextlib
    import food_names
    criteria = payload['questions']['next_action']['criteria']
    by_key = {a.key: a for a in actions}
    found = {}
    with (food_names.naming() if names else contextlib.nullcontext()):
        now = kitchen.actions(who)
        for key in list(criteria):
            option = by_key.get(key)
            if option is None:
                continue
            linked = link(kitchen, who, option, now)
            if linked:
                found[key] = [(a.key, a.label) for a in linked]
                line = sentence(linked)
                criteria[key] = criteria[key] + ('' if criteria[key].endswith('.') else '.') + (
                    food_names.unmark(line) if names else line)
    payload['state']['rules']['links'] = RULE
    payload['state']['links_version'] = VERSION
    return payload, found
