"""The parts of the restructured request (2026-11-20), each its own switch in features.json, on the server only.

They run last, on the finished English request (after the links table, clear names and the serve note), through
finish(): in the decision loop (at the end of the links thread when the table is made there) and in research replay
alike, so every combination rebuilds exactly. With every part off the request is what it was, byte for byte.

- place_names (place-names-v1): station ids written with their names where text lists them bare: the reach rule
  ("Board 1 (b1)"), the split_floor rule ("Board 1", "Counters 2–13"), and each recent decision gets "place", the
  stations its option names.
- timeline (timeline-v1): recent_events and recent_decisions become one list, state.timeline, in time order: Jeff's
  own steps (each with the option he chose, and with place_names on the stations it names: "you chose chop b1 at
  Board 1"), what became of the items he threw, the options he chose that were not
  done, and what went wrong in the kitchen (an order expired, a dish refused or matching no order, food burnt, a
  fire). The other chef's actions are left out: a 2026-11-20 re-ask found no use in them. rules.continuity becomes
  TIMELINE_RULE.
- no_history (no-history-v1): no recent_events, no recent_decisions and no continuity rule (it wins over timeline).
  With both off the request keeps the two lists.
- links_on_options (links-on-options-v1): each option's lines from the links table (option_links) follow the option
  itself, as condition B of the 2026-11-10 links check wrote them; state.option_links goes and rules.links says so.
- rules_by_action (rules-by-action-v1): a rule paragraph about a kind of action (RULE_KINDS) comes only while an
  option of that kind is listed; the fire rule also while food is on a stove or anything burns or heats up; the
  others always. past_episodes, rule and state, goes while it is disabled.
- kitchen_view (kitchen-view-v1): state.kitchen keeps what the kitchen is now, written out: the clock, money and
  stars, dishes, waiting and served orders, the two chefs, every station (empty counters in one line; on a split
  floor grouped by who reaches them), plates, the floor and items in the air. Walls, map cells, routes, collision
  numbers, hashes, seeds, the menu (the same as dishes), the numbers the rules already give, and empty fields go.

Every part says what is, never what to do, and is worked out from the engine and the request alone, the same on
every level. Each adds its version tag to state (left out of what a model is sent, harness.for_model).
"""
from __future__ import annotations

import re

PLACE_NAMES_VERSION = 'place-names-v1'
TIMELINE_VERSION = 'timeline-v1'
NO_HISTORY_VERSION = 'no-history-v1'
LINKS_ON_OPTIONS_VERSION = 'links-on-options-v1'
RULES_BY_ACTION_VERSION = 'rules-by-action-v1'
KITCHEN_VIEW_VERSION = 'kitchen-view-v1'
# features.json name -> (finish() argument, version).
SWITCHES = {'place_names': ('place', PLACE_NAMES_VERSION), 'timeline': ('timeline', TIMELINE_VERSION),
            'no_history': ('no_history', NO_HISTORY_VERSION),
            'links_on_options': ('links_on', LINKS_ON_OPTIONS_VERSION),
            'rules_by_action': ('rules', RULES_BY_ACTION_VERSION), 'kitchen_view': ('view', KITCHEN_VIEW_VERSION)}

# -- place_names ---------------------------------------------------------------------------------------------------

ID_LIST = r'[a-z][a-z0-9_]*(?:, [a-z][a-z0-9_]*)*'
ID_RANGE = re.compile(r'\b([a-z]+)(\d+)–\1(\d+)\b')


def _station_names(payload):
    stations = payload['state'].get('kitchen', {}).get('stations') or {}
    return {sid: s['name'] for sid, s in stations.items() if isinstance(s, dict) and s.get('name')}


def _named(text, names, with_id):
    """Lists of station ids (after a colon up to the full stop, or in parentheses) and id ranges, with names."""
    def one(sid):
        return f'{names[sid]} ({sid})' if with_id else names[sid]

    def listed(match):
        ids = match.group(2).split(', ')
        if not all(i in names for i in ids):
            return match.group(0)
        return match.group(1) + ', '.join(one(i) for i in ids) + match.group(3)

    def span(match):
        first, last = match.group(1) + match.group(2), match.group(1) + match.group(3)
        if first not in names or last not in names or not names[first].endswith(' ' + match.group(2)):
            return match.group(0)
        text = f'{names[first].rsplit(" ", 1)[0]}s {match.group(2)}–{match.group(3)}'
        return text + (f' ({match.group(0)})' if with_id else '')
    # Parentheses first: the names the colon lists get are followed by their ids in parentheses.
    text = re.sub(rf'(\()({ID_LIST})(\))', listed, text)
    text = re.sub(rf'(: )({ID_LIST})(\.)', listed, text)
    return ID_RANGE.sub(span, text)


def place_names(payload):
    names = _station_names(payload)
    state = payload['state']
    rules = state.get('rules', {})
    if isinstance(rules.get('reach'), str):
        rules['reach'] = _named(rules['reach'], names, True)
    if isinstance(rules.get('split_floor'), str):
        rules['split_floor'] = _named(rules['split_floor'], names, False)
    if state.get('recent_decisions'):
        decisions = []
        for decision in state['recent_decisions']:      # copies: the decision loop keeps its own list
            places = [names[word] for word in str(decision.get('choice', '')).split() if word in names]
            decisions.append({**decision, 'place': ', '.join(places)} if places else dict(decision))
        state['recent_decisions'] = decisions
    state['place_names_version'] = PLACE_NAMES_VERSION


# -- timeline / no_history -----------------------------------------------------------------------------------------

TIMELINE_RULE = ('timeline lists, in time order, your own last steps, each with the option you chose; what became of '
                 'the items you threw; options you chose that were not done, and why; and what went wrong in the '
                 'kitchen (an order expired, a dish was refused or matched no order, food burnt, a fire). Use it to see '
                 'whether your recent steps moved any dish forward. Accepted does not mean completed.')
# picked_up and dropped say again what the step's action_done says; swapped (where the held item went), washed (where
# the plate went) and served (the money) say more.
OWN_KINDS = ('action_done', 'thrown', 'interrupted', 'arrival_conflict', 'swapped', 'washed', 'served', 'knocked')
KITCHEN_KINDS = ('expired', 'wrong_dish', 'dish_rejected', 'burn', 'fire', 'fire_spread')
LEFT = re.compile(r' \(\d+(?:\.\d+)?s left\)')
WHO = (('jeff', 'you'), ('human', 'the other chef'))


def _speaker(message):
    for engine, said in WHO:
        if message.startswith(engine + ' '):
            return said + message[len(engine):]
    return message


def make_timeline(payload):
    state = payload['state']
    events, decisions = state.get('recent_events') or [], state.get('recent_decisions') or []
    chosen = {}
    for d in decisions:
        if d.get('accepted'):
            # The option as Jeff chose it, with the stations it names when place_names gave them ("chop b1 at Board 1").
            said = str(d.get('choice')) + (f" at {d['place']}" if d.get('place') else '')
            key = str(d.get('choice'))
            chosen.setdefault(key, said)
            if key.startswith('put then '):          # a one-press option: its second step is the option named after it
                chosen.setdefault(key[len('put then '):], said)
    started = {e.get('action_id'): e.get('action') for e in events if e.get('kind') == 'action_start'}
    lines = []
    for e in events:
        kind, actor, message = e.get('kind'), e.get('actor'), str(e.get('message', ''))
        if kind == 'action_done' and str(e.get('action', '')).startswith('throw'):
            continue                                    # the thrown event says it, with the item and where
        mine = actor == 'jeff' and kind in OWN_KINDS
        throw = (kind == 'caught' and e.get('thrower') == 'jeff') or (kind == 'landed' and actor == 'jeff')
        if not (mine or throw or kind in KITCHEN_KINDS):
            continue
        if kind == 'action_done':
            text = 'you: ' + LEFT.sub('', message.split('completed: ', 1)[-1])
        else:
            text = LEFT.sub('', _speaker(message))
        action = e.get('action') or started.get(e.get('action_id'))
        if mine and kind in ('action_done', 'thrown') and action in chosen:
            text += f' (you chose {chosen[action]})'
        lines.append((e.get('t', 0), text))
    for d in decisions:
        if not d.get('accepted'):
            place = f" at {d['place']}" if d.get('place') else ''
            lines.append((d.get('t', 0), f"you chose {d.get('choice')}{place}: not done ({d.get('result')})"))
    lines.sort(key=lambda line: line[0])                # stable: the engine's order within one moment
    state.pop('recent_events', None)
    state.pop('recent_decisions', None)
    state['timeline'] = [f'{t:.1f} s {text}' for t, text in lines]
    state['rules']['continuity'] = TIMELINE_RULE
    state['timeline_version'] = TIMELINE_VERSION


def drop_history(payload):
    state = payload['state']
    state.pop('recent_events', None)
    state.pop('recent_decisions', None)
    state['rules'].pop('continuity', None)
    state['no_history_version'] = NO_HISTORY_VERSION


# -- links_on_options ----------------------------------------------------------------------------------------------

PARTNER_OPTION_RULE = (' A part starting "then the other chef could" says what the other chef could do next with the '
                       'item you hold after that option, up to their first work on it, as the game computes it if '
                       'nothing else changes first.')


def links_on_options(payload):
    import links
    state = payload['state']
    table = state.pop('option_links', None)
    if table is None:
        return
    criteria = payload['questions']['next_action']['criteria']
    for key, lines in table.items():
        if key not in criteria or not lines:
            continue
        lines = list(dict.fromkeys(lines))      # two pans alike give the same line twice
        own = [line for line in lines if not line.startswith(links.THEN)]
        partner = [line for line in lines if line.startswith(links.THEN)]
        text = links._end(criteria[key])
        if own:
            text += links.LEAD + '; '.join(own)
        if partner:
            text += ('; ' if own else ' If nothing else changes first, ') + '; '.join(partner)
        criteria[key] = text
    state['rules']['links'] = links.RULE + (PARTNER_OPTION_RULE if 'partner_links_version' in state else '')
    state['links_on_options_version'] = LINKS_ON_OPTIONS_VERSION


# -- rules_by_action -----------------------------------------------------------------------------------------------

POT_KINDS = ('put_pot', 'lift_pot', 'return_pot', 'plate_pot', 'plate_counter', 'plate_ground', 'scoop_counter',
             'swap_pot', 'swap_ground_pot', 'load_counter', 'load_ground', 'empty_pot')
WASH_KINDS = ('take_return', 'put_sink', 'take_sink', 'wash', 'put_then_wash', 'wash_from_returns')
# Rule paragraph -> the engine action kinds that bring it (the same kinds on every level); a paragraph not named here
# always comes.
RULE_KINDS = {
    'vessels': POT_KINDS,
    'tableware': POT_KINDS + WASH_KINDS + ('take_plate', 'plate_from_counter'),
    'plate_reuse': WASH_KINDS,
    'resources': ('put_counter', 'put_board', 'take_tool', 'pickup', 'take_counter', 'take_board'),
    'ground': ('drop', 'pickup', 'assemble_ground', 'load_ground', 'plate_ground', 'swap_ground_pot'),
    'interrupt': ('continue', 'stop'),
    'fire': ('take_tool', 'put_tool', 'extinguish', 'put_pot', 'lift_pot', 'return_pot', 'swap_pot', 'swap_ground_pot'),
    'throw': ('throw',),
    'partner_plating': ('plate_partner',),
    'pot_swap': ('swap_pot', 'swap_ground_pot'),
    'off_stove_pots': ('load_counter', 'load_ground'),
    'assembly': ('assemble', 'merge_plates', 'assemble_ground', 'plate_partner'),
    'one_press': ('put_then_take', 'put_then_chop', 'put_then_wash', 'put_then_fetch', 'wash_from_returns'),
}


def listed_kinds(payload, kitchen):
    """The engine kinds of the options next_action lists; a one-press option is not in the engine's list, so its key
    names it ("put then take ...", "wash from ...")."""
    criteria = payload['questions']['next_action']['criteria']
    kinds = {a.kind for a in kitchen.actions('jeff') if a.key in criteria} if kitchen is not None else set()
    for key in criteria:
        if key.startswith('wash from '):
            kinds.add('wash_from_returns')
        elif key.startswith('put then '):
            kinds.add('put_then_' + key.split()[2])
    return kinds


def _heat(kitchen_state):
    stations = (kitchen_state or {}).get('stations') or {}
    return any(s.get('fire') or s.get('fire_heat') or (s.get('stove') and s.get('food'))
               for s in stations.values() if isinstance(s, dict))


def rules_by_action(payload, kitchen):
    kinds = listed_kinds(payload, kitchen)
    state = payload['state']
    rules = state['rules']
    for name, needs in RULE_KINDS.items():
        if name not in rules or kinds & set(needs):
            continue
        if name == 'fire' and _heat(state.get('kitchen')):
            continue
        del rules[name]
    episodes = state.get('past_episodes')
    if isinstance(episodes, dict) and episodes.get('enabled') is False:
        state.pop('past_episodes')
        rules.pop('past_episodes', None)
    state['rules_by_action_version'] = RULES_BY_ACTION_VERSION


# -- kitchen_view --------------------------------------------------------------------------------------------------

SIDES = ('your side', 'shared', "other chef's side")
WHO_LABEL = {'jeff': 'you', 'human': 'the other chef'}


def _food(food):
    if not isinstance(food, dict):
        return 'nothing'
    text = ' '.join(str(x) for x in (food.get('meaning') or food.get('stage'), food.get('id')) if x)
    if food.get('missing'):
        text += ' (still needs ' + ', '.join(food['missing']) + ')'
    return text


def _stove(s):
    pan = f"{s.get('vessel_name') or 'pan'} {s['pot_id']}" if s.get('pot_id') else 'no pan'
    food = s.get('food')
    if not food:
        return f'{pan}, empty' if s.get('pot_id') else pan
    times, ready, burn, fire = [], s.get('ready_in'), s.get('burn_in'), s.get('fire_in')
    if ready:
        times.append(f'cooked in {ready:.1f} s')
    if burn and fire is not None and abs(fire - burn) < 1e-6:
        times.append(f'burns and the stove catches fire in {burn:.1f} s')
    else:
        if burn:
            times.append(f'burns in {burn:.1f} s')
        if fire:
            times.append(f'the stove catches fire in {fire:.1f} s')
    return f'{pan} with {_food(food)}' + (': ' + ', '.join(times) if times else '')


def _station(s):
    kind, food = s.get('type'), s.get('food')
    if kind == 'ingredient_source':
        text = f"gives {s.get('supplies')}" + (f'; {_food(food)} lies on top, so it gives nothing' if food else '')
    elif kind == 'stove':
        text = _stove(s)
    elif kind in ('sink', 'drying_rack'):
        n = len(s.get('stack') or [])
        text = f'{n} plate' + ('' if n == 1 else 's') if n else 'empty'
    elif kind == 'bin':
        text = 'bin'
    elif kind == 'serving_window':
        text = 'serve finished dishes here'
    elif food:
        text = _food(food)
        if kind == 'board' and food.get('stage') == 'raw' and food.get('chop_remaining'):
            text += f" ({food['chop_remaining']:.1f} s of chopping)"
    else:
        text = 'empty'
    if s.get('fire'):
        text += ' - ON FIRE'
    elif s.get('fire_heat'):
        text += f" - heating up from a fire nearby ({s['fire_heat']:.1f} of 1)"
    if s.get('workers'):
        text += ' - in use by ' + ', '.join(WHO_LABEL.get(w, w) for w in s['workers'])
    if s.get('incoming_item'):
        text += f" - {s['incoming_item']} is flying here"
    return text


def _ranges(ids):
    """counter6, counter7, ..., counter13 -> 'counter6–counter13' where the numbers run on; else the list."""
    parsed = [re.fullmatch(r'([a-z_]*[a-z])(\d+)', i) for i in ids]
    if len(ids) >= 3 and all(parsed) and len({m.group(1) for m in parsed}) == 1:
        numbers = [int(m.group(2)) for m in parsed]
        if numbers == list(range(numbers[0], numbers[0] + len(numbers))):
            return f'{ids[0]}–{ids[-1]}'
    return ', '.join(ids)


def _side(kitchen, sid):
    mine, theirs = kitchen.reaches('jeff', sid), kitchen.reaches('human', sid)
    return SIDES[1] if mine and theirs else SIDES[0] if mine else SIDES[2]


def _stations(kj, kitchen):
    split = bool(getattr(kitchen, 'split_floor', False))
    vessels = kj.get('vessels') or {}
    groups = {}
    for sid, s in (kj.get('stations') or {}).items():
        if s.get('vessel') in vessels:
            s = {**s, 'vessel_name': vessels[s['vessel']].get('name')}
        groups.setdefault(_side(kitchen, sid) if split else 'all', []).append((sid, s))
    out = {}
    for side in (SIDES if split else ('all',)):
        listed, empty = {}, []
        for sid, s in groups.get(side, []):
            text = _station(s)
            if text == 'empty' and s.get('type') == 'counter':
                empty.append(sid)
            else:
                listed[f"{s.get('name', sid)} ({sid})"] = text
        if empty:
            listed['empty counters'] = _ranges(empty)
        if listed:
            out[side] = listed
    return out if split else out.get('all', {})


def _chefs(kj):
    out = {}
    for who in ('jeff', 'human'):
        c = (kj.get('chefs') or {}).get(who)
        if not isinstance(c, dict):
            continue
        task = c.get('task')
        doing = LEFT.sub('', task) if task not in (None, '', 'idle') else 'nothing'
        left = float(c.get('travel_remaining') or 0) + float(c.get('work_remaining') or 0)
        if doing != 'nothing' and left:
            doing += f' ({left:.1f} s left)'
        out[WHO_LABEL[who]] = {'at': ', '.join(x for x in (c.get('location_name'), c.get('area')) if x),
                               'holding': _food(c.get('holding')), 'doing': doing}
        if c.get('knocked'):
            out[WHO_LABEL[who]]['knocked back'] = True
    return out


def _in_the_air(kj, names):
    out = []
    for p in kj.get('projectiles') or []:
        what = ' '.join(x for x in (p.get('id'), p.get('ingredient'), f"({p['stage']})" if p.get('stage') else '') if x)
        onto = p.get('onto')
        where = (f'{names.get(onto, onto)} ({onto})' if onto else
                 'floor ({},{})'.format(*p['landing_cell']) if p.get('landing_cell') else 'the floor')
        lands = max(0.0, float(p.get('lands_at', 0)) - float(kj.get('time', 0)))
        out.append(f"{what}, thrown by {WHO_LABEL.get(p.get('actor'), p.get('actor'))}: comes down at {where} in {lands:.1f} s")
    return out


def kitchen_view(payload, kitchen):
    kj = payload['state'].get('kitchen')
    if not isinstance(kj, dict):
        return
    names = {sid: s.get('name', sid) for sid, s in (kj.get('stations') or {}).items()}
    dishes = {d.get('id'): d.get('name', d.get('id')) for d in kj.get('dishes') or []}
    goal = kj.get('goal_status') or {}
    stars = goal.get('star_scores') or []
    money = f"{kj.get('money')} yuan"
    if 'target_money' in goal:
        money += f"; target {goal['target_money']} " + ('reached' if goal.get('met_now') else 'not reached yet')
    if len(stars) >= 3:
        money += f'; {stars[1]} for two stars, {stars[2]} for three'
    state_word = {'ready': 'cooked', 'raw': 'as fetched'}
    view = {
        'clock': f"{kj.get('time', 0):.1f} s of {kj.get('round_limit')} s ({kj.get('round_remaining', 0):.1f} s left)",
        'money': money,
        'dishes': {d.get('name', d.get('id')): ', '.join(f"{c['item']} ({state_word.get(c['state'], c['state'])})"
                                                         for c in d.get('components', [])) + f"; {d.get('price')} yuan"
                   for d in kj.get('dishes') or []},
        'orders_waiting': [{'id': o['id'], 'dish': dishes.get(o['dish'], o['dish']),
                            'time_left': f"{o.get('remaining', 0):.1f} s"}
                           for o in kj.get('orders') or [] if o.get('status') == 'pending'],
        'orders_served': ', '.join(f"{o['id']} {dishes.get(o['dish'], o['dish'])}" for o in kj.get('orders') or []
                                   if o.get('status') == 'served') or 'none',
        'chefs': _chefs(kj),
        'stations': _stations(kj, kitchen),
    }
    tableware = kj.get('tableware') or {}
    if tableware.get('total'):
        view['plates'] = f"{tableware['total']} plates in all" + ''.join(
            f"; {c.get('plate_id')} comes back " + ('when the plate return is free' if c.get('waiting_for_space')
                                                    else f"in {float(c.get('returns_in') or 0):.1f} s")
            for c in tableware.get('customers') or [])
    if kj.get('ground'):
        view['floor'] = {g.get('near', g.get('location')): _food(g.get('food')) for g in kj['ground']}
    air = _in_the_air(kj, names)
    if air:
        view['in_the_air'] = air
    fire = kj.get('fire_safety') or {}
    if fire.get('burning_count'):
        view['fire'] = f"{fire['burning_count']} burning; {fire.get('loss_threshold')} at once lose the round"
    payload['state']['kitchen'] = view
    payload['state']['kitchen_view_version'] = KITCHEN_VIEW_VERSION


# -- all of them ---------------------------------------------------------------------------------------------------


def finish(payload, kitchen, place=False, timeline=False, no_history=False, links_on=False, rules=False, view=False):
    """The parts that are on, in this order: names first (the kitchen still lists stations by id, and the timeline
    shows a refused decision's place), then the history, the links, the rules, and the kitchen view last (the others
    read the full kitchen)."""
    if place:
        place_names(payload)
    if no_history:
        drop_history(payload)
    elif timeline:
        make_timeline(payload)
    if links_on:
        links_on_options(payload)
    if rules:
        rules_by_action(payload, kitchen)
    if view:
        kitchen_view(payload, kitchen)
    return payload


def parts(features):
    """finish()'s switches from the round's features (features.json and an override), or None when all are off."""
    on = {arg: True for name, (arg, _) in SWITCHES.items() if (features.get(name) or {}).get('on')}
    return on or None
