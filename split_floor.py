"""split-floor-v1: on a split floor where no dish on the menu can be made by one chef alone, Jeff is told so.

A trial (features.json split_floor, off by default, no page switch). reach_note lists the stations each chef can
reach, but Jeff still has to work out from the recipes that the menu needs both chefs. With this switch on, a
request on such a floor gets one more rule, rules.split_floor, right after rules.reach (when that is on): which of
the operations the menu needs (the supplies, chopping, cooking, serving) are only on the human's side and which
only on Jeff's, as the engine decides reach (SpatialKitchen.reaches), and the counters both chefs reach. It states
facts only: nothing about who should do which step or when to pass. A dish needs the supplies and serving; chopping
when a component is served chopped or cooked from chopped; cooking when a component is served cooked. On a floor in
one piece, or when one chef alone could make some dish on the menu, nothing is added, so levels 1-3 are asked
exactly as before. The line depends only on the map and the menu, so it is the same in every request of a round.
"""
from __future__ import annotations

from collections import defaultdict
import re

VERSION = 'split-floor-v1'
# The operations a dish can need, with the station type that does each, in the order the line names them.
OPERATIONS = (('the supplies', 'ingredient_source'), ('chopping', 'board'), ('cooking', 'stove'), ('serving', 'serving_window'))


def _ids(names):
    """counter2..counter13 as 'counter2–counter13' when they run on; other names as listed."""
    nums = [int(m.group(1)) for n in names for m in [re.fullmatch(r'counter(\d+)', n)] if m]
    if len(nums) == len(names) and len(nums) > 2 and nums == list(range(nums[0], nums[0] + len(nums))):
        return f'counter{nums[0]}–counter{nums[-1]}'
    return ', '.join(names)


def _join(parts):
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]


def needs(kitchen, recipe):
    """The station types a dish needs, from its components (Kitchen.rules.recipes) and how each is heated."""
    out = {'ingredient_source', 'serving_window'}
    for c in kitchen.rules.recipes[recipe]['components']:
        heat = kitchen.rules.heat.get(c['item'])
        if c['state'] == 'chopped' or (c['state'] == 'ready' and heat and heat.get('from') == 'chopped'):
            out.add('board')
        if c['state'] == 'ready':
            out.add('stove')
    return out


def line(kitchen):
    """The rule's text for this kitchen, or None (a floor in one piece, or a dish one chef alone can make)."""
    if not getattr(kitchen, 'split_floor', False):
        return None
    by_type = defaultdict(list)
    for sid, e in kitchen.equipment.items():
        by_type[e.get('type')].append(sid)
    dishes = list(kitchen.rules.servable)
    if not dishes:
        return None

    def can(who, kind):
        return any(kitchen.reaches(who, s) for s in by_type[kind])
    if any(all(can(who, kind) for kind in needs(kitchen, d)) for who in ('jeff', 'human') for d in dishes):
        return None
    used = set().union(*(needs(kitchen, d) for d in dishes))
    mine, theirs = [], []
    for label, kind in OPERATIONS:
        places = by_type[kind]
        if kind not in used or not places:
            continue
        if all(kitchen.reaches('jeff', s) and not kitchen.reaches('human', s) for s in places):
            mine.append(f'{label} ({", ".join(places)})')
        elif all(kitchen.reaches('human', s) and not kitchen.reaches('jeff', s) for s in places):
            theirs.append(f'{label} ({", ".join(places)})')
    pieces = []
    if theirs:
        pieces.append(f"{_join(theirs)} {'is' if len(theirs) == 1 else 'are'} only on the human's side")
    if mine:
        pieces.append(f"{_join(mine)} {'is' if len(mine) == 1 else 'are'} only on your side")
    text = 'On this floor no dish can be made by one chef alone' + (': ' + '; '.join(pieces) if pieces else '') + '.'
    shared = [s for s in by_type['counter'] if kitchen.reaches('jeff', s) and kitchen.reaches('human', s)]
    if shared:
        text += f' Items cross between the two parts on the counters both of you reach ({_ids(shared)}) or by throwing.'
    return text


def apply(payload, kitchen):
    """What the split_floor switch adds to an English request (harness.compose): the rule and the version, or nothing."""
    found = line(kitchen)
    if found is None:
        return None
    payload['state']['rules']['split_floor'] = found
    payload['state']['split_floor_version'] = VERSION
    return found
