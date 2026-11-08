"""reach-v1: on a kitchen whose floor counters split in two, tell Jeff which stations each chef can walk to.

A trial (features.json reach_note, off by default, no page switch). The player sees the split on screen; Jeff
gets walls and equipment as coordinates and has to work it out. With the switch on, a request on a split floor
gets one rule, rules.reach, that lists the stations only Jeff can reach, only the human can reach, and both can
reach, as the engine decides it (SpatialKitchen.reaches). It states facts only: nothing about passing food or
dividing work. On a floor in one piece nothing is added, so levels 1-3 are asked exactly as before. The lists
depend only on the map and on which part each chef stands, which does not change in a round, so the rule is
the same in every request of a round (compact_input sends it with the static part, like the other rules).
"""
from __future__ import annotations

VERSION = 'reach-v1'
RULE = ('The floor is split into parts by counters, and a chef cannot walk from one part to another, so each '
        'chef can reach only some stations for the whole round. Stations only you can reach: {jeff}. Stations '
        'only the human can reach: {human}. Stations both of you can reach, each from your own part: {both}.')


def lists(kitchen, stations):
    """{'jeff': [...], 'human': [...], 'both': [...]} for these station ids on a split floor, else None."""
    if not getattr(kitchen, 'split_floor', False):
        return None
    out = {'jeff': [], 'human': [], 'both': []}
    for station in stations:
        jeff, human = kitchen.reaches('jeff', station), kitchen.reaches('human', station)
        if jeff and human:
            out['both'].append(station)
        elif jeff or human:
            out['jeff' if jeff else 'human'].append(station)
    return out


def apply(payload, kitchen):
    """What the reach_note switch adds to an English request (harness.compose): the rule and the version, or nothing."""
    found = lists(kitchen, list(payload['state']['kitchen']['stations']))
    if found is None:
        return None
    payload['state']['rules']['reach'] = RULE.format(**{key: ', '.join(ids) or 'none' for key, ids in found.items()})
    payload['state']['reach_note_version'] = VERSION
    return found
