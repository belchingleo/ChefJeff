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
game uses arm D through the option_links switch (features.json, a trial with a player switch, on by default, option-links-v3): each
request gets state.option_links, a table computed afresh for that request from the kitchen it describes, and
rules.links, while every option stays as it is (apply).
"""
from __future__ import annotations

from model_language import english_text

VERSION = 'links-v1'
SWITCH_VERSION = 'option-links-v3'     # the game's option_links switch: arm D
# v3 counts a held pan scooping an ingredient off a counter (scoop_counter, rules-v14) as work, as putting it in a pan.
# v1 also carried out walks, waits and stops in the fork, so a walk could pick up work that only time made possible
# (a pan finishing while Jeff walked); v2 skips them, as they change no hand and no station, and forks share the
# kitchen's unchanging parts and a route cache (about 0.45 s -> 0.18 s per request on level 2).
# The work an option can lead to: harness.WORK_KINDS without fetching and taking, plus putting a dirty plate in the sink.
WORK = ('chop', 'put_pot', 'scoop_counter', 'load_counter', 'load_ground', 'assemble', 'assemble_ground', 'plate_pot', 'plate_counter',
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
        # Keyed by the map's walking graph, which every navigation of one map shares (Navigation.isolated copies the
        # object, not the graph), so each map has one cache however many forks or rounds there are.
        key = id(getattr(nav, 'graph', nav))
        if key not in _ROUTES:
            if len(_ROUTES) >= 16:
                _ROUTES.clear()
            _ROUTES[key] = (nav, nav.isolated())
        twin.nav = _ROUTES[key][1]
    return twin


def _work(actions):
    return {(a.kind, a.target): a for a in actions if a.kind in WORK}


def link(kitchen, who, option, now, place=None, seen=None):
    """The work actions (engine Actions) the option leads to: listed after it, not listed now. [] when none or when the
    option cannot be carried out to its end in the fork. seen, a dict, receives the fork as it is after the option
    ('twin'), for partner_link."""
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
            if seen is not None:
                seen['twin'] = twin
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
    if seen is not None:
        seen['twin'] = twin
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


# The partner's side (option_links_partner, partner-links-v1): after the option, what the other chef can newly do with
# the item the chef held, taking it or working on it, or that the item is in the other chef's hands. Only actions whose
# engine signature names that item count, so work the other chef gains only because time passed in the fork is left out.
# The partner's side (option_links_partner, partner-links-v2): for an option that leaves the held item where the other
# chef can take it or in their hands, Jeff's own line goes on with what the other chef could then do with the item,
# up to their first work on it ("then the other chef could: take it from Counter 4, then put it on Board 1, then chop
# it"). Re-asked on level 4, this wording in Jeff's own table moved the most choices; v1 listed only the first step, in a
# table of its own. The chain follows only the other chef's actions whose engine signature names the item, and never
# steps that move it to another counter, the floor, the bin or the extinguisher, so it follows the item towards work.
PARTNER_VERSION = 'partner-links-v2'
PARTNER_KINDS = WORK + ('take_counter', 'take_board', 'take_plate', 'take_return', 'take_sink', 'pickup', 'lift_pot')
CHAIN_SKIP = ('go', 'throw', 'drop', 'discard', 'wait', 'stop', 'put_counter', 'take_tool')
CHAIN_DEPTH = 3
THEN = 'then the other chef could: '
PARTNER_RULE = (' A line starting "then the other chef could" says what the other chef could do next with the item you '
                'hold after that option, up to their first work on it, as the game computes it if nothing else changes '
                'first.')


def _names_item(expected, item):
    return any(isinstance(x, str) and x.split(':')[0] == item for x in expected or ())


def _run(twin, who, action):
    started = twin.start(who, action)
    if not (started[0] if isinstance(started, tuple) else started):
        return False
    job = twin.chefs[who].job
    if job is None:
        return True
    waited, limit = 0.0, max(0.0, job.travel) + max(0.0, job.work) + GRACE
    while not twin.ended and waited < limit and twin.chefs[who].job is not None and twin.chefs[who].job.id == job.id:
        twin.advance(STEP)
        waited += STEP
    return twin.chefs[who].job is None or twin.chefs[who].job.id != job.id


def partner_chain(kitchen, twin, who, item):
    """The other chef's shortest run of actions on the held item, after the option, that ends in work (breadth first,
    at most CHAIN_DEPTH steps), or [] when the item is not where they can take it."""
    other = 'human' if who == 'jeff' else 'jeff'
    held = twin.chefs[other].hand is not None and twin.chefs[other].hand.id == item
    before = {(a.kind, a.target) for a in kitchen.actions(other)}
    if not held and not any(a.kind in PARTNER_KINDS and (a.kind, a.target) not in before and _names_item(a.expected, item)
                            for a in twin.actions(other)):
        return []
    frontier = [(twin, [])]
    first = None
    for _ in range(CHAIN_DEPTH):
        nxt = []
        for state, path in frontier:
            for a in state.actions(other):
                if a.kind in CHAIN_SKIP or not _names_item(a.expected, item):
                    continue
                if a.kind in WORK:
                    return path + [a]
                if first is None:
                    first = path + [a]
                fork = _fork(state)
                if _run(fork, other, a):
                    nxt.append((fork, path + [a]))
        frontier = nxt[:6]
    return first or []


def table(kitchen, who, actions, keys, names=False, partner=False):
    """{option key: [the work it leads to, in the request's English]} for the listed options that lead to new work;
    with partner (option_links_partner) also the other chef's chain on the held item (partner_chain)."""
    import contextlib
    import food_names
    import one_press
    unmark = food_names.unmark if names else (lambda text: text)
    by_key = {a.key: a for a in actions}
    out = {}
    with (food_names.naming() if names else contextlib.nullcontext()):
        now = kitchen.actions(who)
        held_item = kitchen.chefs[who].hand
        for key in keys:
            option = by_key.get(key)
            seen = {}
            linked = link(kitchen, who, option, now, seen=seen) if option is not None else []
            lines = [unmark(english_text(a.label)) for a in linked]
            # Where a one-press option or an intent that puts first leaves the held item depends on put_where, which is
            # not known yet (the fork takes the first place), so those options get no partner line.
            guessed = option is not None and (option.kind in one_press.KINDS or (option.kind == 'intent' and option.expected[0] == 'put'))
            if partner and 'twin' in seen and held_item is not None and not guessed:
                chain = partner_chain(kitchen, seen['twin'], who, held_item.id)
                if chain:
                    lines.append(THEN + ', then '.join(unmark(english_text(a.label)) for a in chain))
            if lines:
                out[key] = lines
    return out


def apply(payload, kitchen, who, actions, names=False, partner=False):
    """The option_links switch on a composed request (translated, as sent): state.option_links, rules.links and
    links_version; no option changes. partner (option_links_partner): the other chef's chains in the same table, the
    rule says so, and partner_links_version."""
    keys = list(payload['questions']['next_action']['criteria'])
    payload['state']['option_links'] = table(kitchen, who, actions, keys, names, partner)
    payload['state']['rules']['links'] = SEPARATE_RULE + (PARTNER_RULE if partner else '')
    payload['state']['links_version'] = SWITCH_VERSION
    if partner:
        payload['state']['partner_links_version'] = PARTNER_VERSION
    return payload


def annotate(payload, kitchen, who, actions, names=False):
    """Condition B alone (see arms): (payload, links found)."""
    out, found = arms(payload, kitchen, who, actions, names)
    return out['B'], found
