"""compact-v1: how a client sends Jeff's request, as a fixed part per round and a changing part per request.

The request itself (harness.compose's payload, what journals and research records keep and rebuild) is not
changed by a single byte. When the compact_input feature is on (features.json), each client turns that payload,
just before sending it, into

- static: what stays the same for the whole round: every rule but player_communication, the kitchen's fixed
  fields (map, menu, timing, scoring, ...), each station's fixed attributes, the chefs' sprint constants, past
  episodes, the version fields, and a table of field defaults;
- live: everything else: the kitchen's changing fields, each station and chef without the fields at their
  defaults (an idle station is left out), recent events and decisions, player messages, Jeff's plan;

and puts static first: chat models get it in the system message, decision services as state.static before
state.live. Within a round static is byte-identical (sorted keys, compact separators), so a provider can cache
it as a prompt prefix and the model is sent only what changed. expand(static, live) gives back the payload's
state exactly; tests check it on every request of every payload fingerprint scenario. Fields are listed
explicitly: a field the lists do not name goes to live, and a default is matched by type and value (0 is not
False), so nothing is lost (key order aside, which JSON objects do not carry).
"""
from __future__ import annotations

import json

VERSION = 'compact-v1'

# The kitchen's fields that stay the same for the whole round.
KITCHEN_STATIC = ('map', 'menu', 'dishes', 'vessels', 'timing', 'scoring', 'goals', 'order_flow',
                  'end_policy', 'level', 'level_id', 'round_limit', 'order_seed', 'config_hash', 'assembly',
                  'ground_assembly')
# A station's fixed attributes; its other fields change.
STATION_STATIC = ('name', 'area', 'type', 'counter', 'stove', 'fire_neighbors')
STATION_DEFAULTS = {'food': None, 'used_by': None, 'fire': False, 'heating': False, 'pot_id': None, 'fire_heat': 0.0,
                    'fire_strength': None, 'workers': [], 'incoming_item': None}
CHEF_DEFAULTS = {'holding': None, 'job_id': None, 'target': None, 'action_kind': None, 'working': False,
                 'travel_remaining': 0, 'work_remaining': 0, 'can_throw': False, 'throw_range': None, 'knocked': False,
                 'handoff_target': None, 'manual_moving': False, 'move_direction': [0.0, 0.0], 'resync': 0, 'route': []}
SPRINT_STATIC = ('multiplier', 'duration', 'cooldown_after')
# State fields outside the kitchen that stay the same for the whole round.
STATE_STATIC = ('past_episodes', 'input_language', 'rules_version', 'plan_rules_version', 'one_press_version',
                'undo_note_version', 'reach_note_version')
# Rules that are not fixed for the round: player messages appear with the first one.
LIVE_RULES = ('player_communication',)
RULE = ('The state comes in two parts: static, the same for the whole round (rules, map, menu, station layout and the '
        'field defaults), and live, sent with each request. kitchen.stations and kitchen.chefs in live leave out the fields '
        'at their defaults (static.defaults); a station absent from live.kitchen.stations is idle, every field at its default. '
        'A station or chef is its static entry with its live entry over it.')
# How chat models are told where each part is (the browser's copy in hosted/browser-agent.js must match).
CHAT_STATIC_INTRO = '\n\nThe fixed part of the state for this round (static):\n'
CHAT_LIVE_NOTE = 'The changing part of the state (live) and the questions for this request:\n'


def enabled() -> bool:
    """Whether this checkout sends requests in the compact format (features.json compact_input)."""
    import features
    return features.current()['compact_input']['on']


def _default(value, default) -> bool:
    return type(value) is type(default) and value == default


def split(state: dict) -> tuple[dict, dict]:
    """The payload's state as (static, live); expand(static, live) == state."""
    static, live = {'defaults': {'stations': dict(STATION_DEFAULTS), 'chefs': dict(CHEF_DEFAULTS)}}, {}
    for key, value in state.items():
        if key == 'kitchen' and isinstance(value, dict):
            static['kitchen'], live['kitchen'] = _split_kitchen(value)
        elif key == 'rules' and isinstance(value, dict):
            static['rules'] = {**{k: v for k, v in value.items() if k not in LIVE_RULES}, 'compact_input': RULE}
            changing = {k: v for k, v in value.items() if k in LIVE_RULES}
            if changing:
                live['rules'] = changing
        elif key in STATE_STATIC:
            static[key] = value
        else:
            live[key] = value
    return static, live


def _split_kitchen(kitchen):
    static, live = {}, {}
    for key, value in kitchen.items():
        if key in KITCHEN_STATIC:
            static[key] = value
        elif key == 'stations' and isinstance(value, dict):
            static['stations'], static['station_fields'], live['stations'] = _split_stations(value)
        elif key == 'chefs' and isinstance(value, dict):
            static['chefs'], static['chef_fields'], live['chefs'] = _split_chefs(value)
        else:
            live[key] = value
    return static, live


def _split_stations(stations):
    fixed, fields, changing = {}, {}, {}
    for key, station in stations.items():
        fixed[key] = {f: station[f] for f in STATION_STATIC if f in station}
        dynamic = [f for f in station if f not in STATION_STATIC]
        # The fields with a default each type of station has (a station with others keeps its own list); fields
        # without one (a stove's vessel, ready_in, ...) come and go and always travel in live.
        defaulted = sorted(f for f in dynamic if f in STATION_DEFAULTS)
        if fields.setdefault(str(station.get('type')), defaulted) != defaulted:
            fixed[key]['fields'] = defaulted
        values = {f: station[f] for f in dynamic if not (f in STATION_DEFAULTS and _default(station[f], STATION_DEFAULTS[f]))}
        if values:
            changing[key] = values
    return fixed, fields, changing


def _split_chefs(chefs):
    """Each chef's fixed part (sprint constants), the defaulted fields the chefs have, and what changes."""
    fixed, fields, changing = {}, {}, {}
    for who, chef in chefs.items():
        fixed[who] = {}
        fields[who] = [f for f in CHEF_DEFAULTS if f in chef]
        values = {}
        for f, value in chef.items():
            if f == 'sprint' and isinstance(value, dict):
                fixed[who]['sprint'] = {k: value[k] for k in SPRINT_STATIC if k in value}
                values['sprint'] = {k: v for k, v in value.items() if k not in SPRINT_STATIC}
            elif not (f in CHEF_DEFAULTS and _default(value, CHEF_DEFAULTS[f])):
                values[f] = value
        changing[who] = values
    return fixed, fields, changing


def expand(static: dict, live: dict) -> dict:
    """The payload's state from its two parts."""
    defaults = static['defaults']
    parts = {**{k: v for k, v in static.items() if k in STATE_STATIC}, **live}
    if 'rules' in static:
        parts['rules'] = {**{k: v for k, v in static['rules'].items() if k != 'compact_input'}, **live.get('rules', {})}
    if 'kitchen' in static:
        parts['kitchen'] = _expand_kitchen(static['kitchen'], live.get('kitchen', {}), defaults)
    return parts


def _expand_kitchen(static, live, defaults):
    parts = {**{k: v for k, v in static.items() if k in KITCHEN_STATIC}, **live}
    if 'stations' in static:
        stations = {}
        for key, fixed in static['stations'].items():
            dynamic = fixed.get('fields', static['station_fields'].get(str(fixed.get('type'))))
            stations[key] = {**{f: v for f, v in fixed.items() if f in STATION_STATIC},
                             **{f: defaults['stations'].get(f) for f in dynamic}, **live.get('stations', {}).get(key, {})}
        parts['stations'] = stations
    if 'chefs' in static:
        chefs = {}
        for who, fixed in static['chefs'].items():
            chef = {**{f: defaults['chefs'][f] for f in static['chef_fields'][who]}, **live.get('chefs', {}).get(who, {})}
            if 'sprint' in fixed:
                chef['sprint'] = {**fixed['sprint'], **chef.get('sprint', {})}
            chefs[who] = chef
        parts['chefs'] = chefs
    return parts


def dumps(value) -> str:
    """The one serialization: the same object always gives the same bytes."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def plan_possible(static) -> bool:
    """Whether this round can ask plan questions (its plan rule is in the fixed rules)."""
    rules = static.get('rules', {})
    return 'jeff_plan' in rules or 'intent' in rules


def put_where_possible(static) -> bool:
    """Whether this round can ask put_where (one-press options are on)."""
    return 'one_press' in static.get('rules', {})


def chat_messages(payload, instructions, after_live=''):
    """A chat request's messages: the fixed instructions and static part first, the live part and questions last."""
    static, live = split(payload['state'])
    return [{'role': 'system', 'content': instructions + CHAT_STATIC_INTRO + dumps(static)},
            {'role': 'user', 'content': CHAT_LIVE_NOTE + dumps({'live': live, 'questions': payload['questions']}) + after_live}]


def decision_body(payload) -> dict:
    """A decision service's body: the same request with its state as {static, live}, static first."""
    static, live = split(payload['state'])
    return {**payload, 'state': {'static': static, 'live': live}}


def relay(payload) -> dict:
    """What the hosted page gets with a request to send from the browser: the two parts, ready to place."""
    static, live = split(payload['state'])
    return {'version': VERSION, 'static': static, 'live': live}
