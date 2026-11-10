"""Links between an option and the work it makes possible (links-v1): condition B of the links check.

Condition A is Jeff's request as the game sends it. Condition B is the same request with one fact added to some
options: the work Jeff could do after it that he cannot do now, as the engine computes it. For each listed option,
a fork of the kitchen (Kitchen.fork, as ask_ahead.py uses) carries the option out to its end, the other chef
keeping what it does with no new input; the work actions Jeff has then and not now are the option's link. Only
work counts (chop, put in a pan or pot, plate or assemble, serve, put a dirty plate in the sink, wash), never
walking, putting down, throwing, fetching or taking, so the line names where an option leads and nothing else.
An option that leads to no new work gets no line.

It says what becomes possible, never what Jeff should do, and the same rule holds for every level and ingredient
(nothing is written by hand). The links check (scripts/links_check.py) re-asks logged moments in four arms; the
game uses arm D through the option_links switch (features.json, a trial, off by default, option-links-v2): each
request gets state.option_links, a table computed afresh for that request from the kitchen it describes, and
rules.links, while every option stays as it is (apply).
"""
from __future__ import annotations

from model_language import english_text

VERSION = 'links-v1'
SWITCH_VERSION = 'option-links-v2'     # the game's option_links switch: arm D
# v1 also carried out walks, waits and stops in the fork, so a walk could pick up work that only time made possible
# (a pan finishing while Jeff walked); v2 skips them, as they change no hand and no station, and forks share the
# kitchen's unchanging parts and a route cache (about 0.45 s -> 0.18 s per request on level 2).
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


# A kitchen's parts no step of play changes (config, rules, the map and what is derived from it). A fork for a link
# shares them instead of deep-copying them for every option, and the forks of one map share one route cache of
# their own (route results depend on the walls only), so a request's table is cheaper and comes out the same.
SHARED = ('rules', 'resolved', 'map_document', 'floor_places', 'equipment', 'floor_part', 'floor', 'operation_insets',
          'walls', '_fire_neighbors', 'c')      # not provenance: it records each food's history as play goes on
NO_EFFECT = ('go', 'wait', 'stop')     # change no hand and no station, so they never lead to new work
FAST = True                            # False: fork as Kitchen.fork does, every option (kept for the equivalence check)
_ROUTES = {}                           # id(map navigation) -> (that navigation, the links forks' isolated copy)


def _fork(kitchen):
    if not FAST:
        return kitchen.fork()
    state = kitchen.__dict__
    held = {name: state.pop(name) for name in SHARED if name in state}
    try:
        twin = kitchen.fork()
    finally:
        state.update(held)
    twin.__dict__.update(held)
    nav = state.get('nav')
    if nav is not None:
        if id(nav) not in _ROUTES:
            _ROUTES[id(nav)] = (nav, nav.isolated())
        twin.nav = _ROUTES[id(nav)][1]
    return twin


def _work(actions):
    return {(a.kind, a.target): a for a in actions if a.kind in WORK}


def link(kitchen, who, option, now, place=None):
    """The work actions (engine Actions) the option leads to: listed after it, not listed now. [] when none or when the
    option cannot be carried out to its end in the fork."""
    import one_press
    if FAST and option.kind in NO_EFFECT:
        return []
    twin = _fork(kitchen)
    other = 'human' if who == 'jeff' else 'jeff'
    if any(getattr(twin, 'manual', {}).get(other, (0.0, 0.0))):
        twin.set_manual(other, 0, 0)
    if option.kind == 'intent':
        # An intent (intent_layer.py) carries its own steps: its first step (an engine action, or a put where
        # put_where says) and the steps after it, as the decision loop runs them.
        first, rest = option.expected
        if first != 'put' and first.kind in ('wait', 'stop'):
            return []
        if FAST and first != 'put' and first.kind in NO_EFFECT and not rest:
            return []
        if first != 'put' and first.kind == 'continue':
            option = first
        elif not _carry_out(twin, who, first, rest, place):
            return []
        else:
            return [a for key, a in _work(twin.actions(who)).items() if key not in _work(now)][:MOST]
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


def _end(text):
    return text + ('' if text.endswith('.') else '.')


def arms(payload, kitchen, who, actions, names=False):
    """The request in the three arms that add to it (a translated payload, as sent), and the links found:

    - B: each option that leads to new work ends with that work (the link), with RULE and links_version links-v1;
    - C: the same options end instead with where their station is (LOCATION_LEAD), a fact about no work, with
      LOCATION_RULE and links_version location-v1, so B and C differ only in what the added line says;
    - D: no option changes; state.option_links lists each linked option's work, with SEPARATE_RULE and
      links_version separate-v1, so the links come without making any option longer.

    actions are the request's listed actions (the engine's and one-press options), in the kitchen the request
    describes. Returns ({'B': payload, 'C': payload, 'D': payload}, {option key: [(linked key, engine label)]})."""
    import contextlib
    import copy
    import food_names
    unmark = food_names.unmark if names else (lambda text: text)
    by_key = {a.key: a for a in actions}
    found, lines, places = {}, {}, {}
    with (food_names.naming() if names else contextlib.nullcontext()):
        now = kitchen.actions(who)
        for key in list(payload['questions']['next_action']['criteria']):
            option = by_key.get(key)
            if option is None:
                continue
            linked = link(kitchen, who, option, now)
            if linked:
                found[key] = [(a.key, a.label) for a in linked]
                lines[key] = [unmark(english_text(a.label)) for a in linked]
                places[key] = location(kitchen, option.target)
    out = {}
    b = copy.deepcopy(payload)
    for key, work in lines.items():
        b['questions']['next_action']['criteria'][key] = _end(b['questions']['next_action']['criteria'][key]) + LEAD + '; '.join(work)
    b['state']['rules']['links'] = RULE
    b['state']['links_version'] = VERSION
    out['B'] = b
    c = copy.deepcopy(payload)
    for key, where in places.items():
        c['questions']['next_action']['criteria'][key] = _end(c['questions']['next_action']['criteria'][key]) + LOCATION_LEAD + where
    c['state']['rules']['links'] = LOCATION_RULE
    c['state']['links_version'] = 'location-v1'
    out['C'] = c
    d = copy.deepcopy(payload)
    d['state']['option_links'] = {key: work for key, work in lines.items()}
    d['state']['rules']['links'] = SEPARATE_RULE
    d['state']['links_version'] = 'separate-v1'
    out['D'] = d
    return out, found


LOCATION_LEAD = ' Location: '
LOCATION_RULE = ('Some options of next_action end with "Location: ...". It gives where the station or floor tile that option '
                 'uses is: its name, its area, its map cell and the cell it is used from. It does not say whether you '
                 'should choose that option.')
SEPARATE_RULE = ('option_links lists, for some options of next_action (by key), the work (chop, put in a pan or pot, plate '
                 'or assemble, serve, put a dirty plate in the sink, wash) you could do after that option and cannot do now, '
                 'as the game computes it with the other chef going on with what they are doing, if nothing else changes '
                 'first. It does not say whether you should choose that option.')


def location(kitchen, target):
    """Where an option's station or floor tile is, in the request's English: name, area and map cell."""
    try:
        place = kitchen.place(target)
    except (KeyError, AttributeError):
        return 'not on the map'
    name = english_text(getattr(place, 'name', str(target)))
    area = getattr(place, 'area', None)
    cell = reach = ''
    equipment = getattr(kitchen, 'equipment', {}).get(target)
    try:
        if equipment is not None:
            x, y = equipment['cell']
            ax, ay = equipment['access']
            cell, reach = f'map cell ({x:g}, {y:g})', f'used from map cell ({ax:g}, {ay:g})'
        else:
            x, y = kitchen.cell(target)
            cell = reach = f'map cell ({x:g}, {y:g})'
            reach = 'used from that cell'
    except (ValueError, KeyError, AttributeError, TypeError):
        pass
    return ', '.join(part for part in (name, english_text(area) if area else '', cell, reach) if part)


def table(kitchen, who, actions, keys, names=False):
    """{option key: [the work it leads to, in the request's English]} for the listed options that lead to new work."""
    import contextlib
    import food_names
    unmark = food_names.unmark if names else (lambda text: text)
    by_key = {a.key: a for a in actions}
    out = {}
    with (food_names.naming() if names else contextlib.nullcontext()):
        now = kitchen.actions(who)
        for key in keys:
            option = by_key.get(key)
            linked = link(kitchen, who, option, now) if option is not None else []
            if linked:
                out[key] = [unmark(english_text(a.label)) for a in linked]
    return out


def apply(payload, kitchen, who, actions, names=False):
    """The option_links switch on a composed request (translated, as sent): state.option_links, rules.links and
    links_version; no option changes."""
    keys = list(payload['questions']['next_action']['criteria'])
    payload['state']['option_links'] = table(kitchen, who, actions, keys, names)
    payload['state']['rules']['links'] = SEPARATE_RULE
    payload['state']['links_version'] = SWITCH_VERSION
    return payload


def annotate(payload, kitchen, who, actions, names=False):
    """Condition B alone (see arms): (payload, links found)."""
    out, found = arms(payload, kitchen, who, actions, names)
    return out['B'], found
