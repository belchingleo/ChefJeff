"""The parts of the restructured request (2026-11-20), each its own switch in features.json, on the server only.

They run last, on the finished English request (after the links table, clear names and the serve note), through
finish(): in the decision loop (at the end of the links thread when the table is made there) and in research replay
alike, so every combination rebuilds exactly. With every part off the request is what it was, byte for byte.

- place_names (place-names-v1): station ids written with their names where text lists them bare: the reach rule
  ("Board 1 (b1)"), the split_floor rule ("Board 1", "Counters 2–13"), and each recent decision gets "place", the
  stations its option names.
- timeline (timeline-v2): recent_events and recent_decisions become one list, state.timeline, in time order: Jeff's
  own steps (each with the option he chose, and with place_names on the stations it names: "you chose chop b1 at
  Board 1"), what became of the items he threw, the options he chose that were not
  done, and what went wrong in the kitchen (an order expired, a dish refused or matching no order, food burnt, a
  fire). The other chef's actions are left out: a 2026-11-20 re-ask found no use in them. rules.continuity becomes
  TIMELINE_RULE, which keeps the continuity rule's checks for repeated back-and-forth (v2; v1 had left them out).
- no_history (no-history-v1): no recent_events, no recent_decisions and no continuity rule (it wins over timeline).
  With both off the request keeps the two lists.
- links_on_options (links-on-options-v1): each option's lines from the links table (option_links) follow the option
  itself, as condition B of the 2026-11-10 links check wrote them; state.option_links goes and rules.links says so.
- rules_by_action (rules-by-action-v2): a rule paragraph about a kind of action (RULE_KINDS) comes only while an
  option of that kind is listed; the fire rule also while food is on a stove or anything burns or heats up; the
  others always, the vessels rule included (v2: v1 left it out while no pot option was listed, so a chef holding raw
  beef read nowhere that a pan takes beef only once chopped). past_episodes, rule and state, goes while it is disabled.
- kitchen_view (kitchen-view-v8): state.kitchen keeps what the kitchen is now, written out: the clock, money and
  stars, which vessel cooks what (v2), waiting and served orders (v5: no dishes block; the rules give the recipes and
  prices), the two chefs (v6: Jeff's own line only while he holds something, and then only what he holds; with "you:
  at Counter 4, holding nothing, doing nothing" Jev took back what he had just put down for the other chef in 52 of
  147 re-asks of the user's level-4 rounds, without that line in 8 of 147), every station (empty counters in one line; on a split
  floor grouped by who reaches them), plates, the floor and items in the air. Walls, map cells, routes, collision
  numbers, hashes, seeds, the menu (the same as dishes), the numbers the rules already give, and empty fields go.
  v7: a stove's line follows the stove's heating too: food that does not heat on a burning stove waits until the fire
  there is out, and food still cooking on one is cooked and then waits (v6 gave the times of a stove that is not
  burning, which a fire spreading to a stove made false once it stopped burning food, 2026-11-22); burnt food says
  how long it has been burnt, on a stove and off it (its burnt time runs while it stays on a stove, and the burnt-food
  scoring counts it); a pan off the stove gives its times for a stove that is not on fire while one is.
  v8: burnt food's name says whether a dish with it is accepted, at what price change and, on a stove, for how many
  seconds more, or refused (the state's food text, servability.py: "frying pan P1 with beef (burnt; accepted at -10
  yuan for 2.1 s more while on the stove) B1: burnt for 2.9 s"), and so does burnt food in the air ("B2 burnt dish
  (accepted at -10 yuan), thrown by you: ..."; a burnt dish read as its dish before); v7 said only how long it
  had been burnt. The burnt time is rounded up to the tenth of a second (burnt_seconds), so food the tier refuses
  never reads as burnt for the tier's limit ("burnt for 5.0 s" for 5.02 s), and the seconds left are rounded down
  (servability.tenths), so on a stove at the standard heat rate the two never add up to more than the limit ("burnt
  for 3.0 s" with "for 2.0 s more" for 2.94 s).
  v3: a stove's line gives only the next thing to happen (cooked; then burns and catches fire; then catches fire).
  v2: a loose ingredient says what it still needs, from the same request's facts ("beef (as fetched) F3 (not chopped
  yet (2.2 s of chopping); a frying pan cooks it only once it is chopped)"); v1 dropped the chopping left and the
  vessels, and with rules_by_action v1 Perplexity and Jev walked raw beef between the stoves (user play 2026-11-20).

Every part says what is, never what to do, and is worked out from the engine and the request alone, the same on
every level. Each adds its version tag to state (left out of what a model is sent, harness.for_model).
"""
from __future__ import annotations

from collections import defaultdict
import math
import re
from types import SimpleNamespace

import servability

PLACE_NAMES_VERSION = 'place-names-v1'
TIMELINE_VERSION = 'timeline-v3'
NO_HISTORY_VERSION = 'no-history-v1'
LINKS_ON_OPTIONS_VERSION = 'links-on-options-v1'
RULES_BY_ACTION_VERSION = 'rules-by-action-v3'
KITCHEN_VIEW_VERSION = 'kitchen-view-v8'
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

# What the timeline holds (v3), then the continuity rule's own checks as the request words them (v2 brought them back
# after a Jev round looped go stove / drop / pick up for 75 s; v3 takes them from the request, so food_names' wording
# stays: "fetching more of an ingredient", not "raw meat").
TIMELINE_LISTS = ('timeline lists, in time order, your own last steps, each with the option you chose; options you '
                  'chose whose steps are no longer in the list, and runs of waiting; what became of the items you '
                  'threw, and of items the other chef threw to your side; options you chose that were not done, and '
                  'why; and what went wrong in the kitchen (an order expired, a dish was refused or matched no order, '
                  'food burnt, a fire).')
TIMELINE_USE = ' Use it to see whether your recent steps moved any dish forward, and to '


def timeline_rule(continuity=None):
    import harness
    text = continuity if isinstance(continuity, str) and 'Use them to ' in continuity else harness.CONTINUITY_RULE
    return TIMELINE_LISTS + TIMELINE_USE + text.split('Use them to ', 1)[1] + ' Accepted does not mean completed.'


TIMELINE_RULE = timeline_rule()
# picked_up and dropped say again what the step's action_done says; swapped (where the held item went), washed (where
# the plate went) and served (the money) say more.
OWN_KINDS = ('action_done', 'thrown', 'interrupted', 'arrival_conflict', 'swapped', 'washed', 'served', 'knocked')
KITCHEN_KINDS = ('expired', 'wrong_dish', 'dish_rejected', 'burn', 'fire', 'fire_spread')
# A finished step's stale timer, also with a note after it ("(2.0s left; can stop and resume)").
LEFT = re.compile(r' \(\d+(?:\.\d+)?s left(?:;[^)]*)?\)')
DONE = re.compile(r'^(jeff|human) completed( together)?: ')
WHO = (('jeff', 'you'), ('human', 'the other chef'))
QUIET = ('wait', 'continue')


def _speaker(message, actor=None):
    """The engine's message with its chef named as the timeline names them ("you", "the other chef")."""
    done = DONE.match(message)
    if done:
        who = dict(WHO)[done.group(1)]
        return who + (' (together with the other chef)' if done.group(2) and done.group(1) == 'jeff' else '') + ': ' + message[done.end():]
    for engine, said in WHO:
        if message.startswith(engine + ' ') or message.startswith(engine + ':'):
            return said + message[len(engine):]
    return message


def _said(d):
    return str(d.get('choice')) + (f" at {d['place']}" if d.get('place') else '')


def make_timeline(payload, kitchen=None):
    """v3: each of Jeff's steps is credited to the latest accepted choice made by the time the step started (v2
    matched option keys and missed one-press steps); accepted choices with no step in the list get a line of their
    own, runs of waiting one line; a cancelled step names itself; items the other chef threw that landed where Jeff
    reaches, or that he caught, are listed."""
    state = payload['state']
    events, decisions = state.get('recent_events') or [], state.get('recent_decisions') or []
    acting = [d for d in decisions if d.get('accepted') and d.get('choice') not in QUIET + ('stop',)]
    started = {e.get('action_id'): e for e in events if e.get('kind') == 'action_start' and e.get('actor') == 'jeff'}
    reaches = getattr(kitchen, 'reaches', None)

    def decision_for(t):
        found = None
        for d in acting:
            if float(d.get('t', 0)) <= float(t if t is not None else 0) + 0.06:
                found = d
        return found
    def by_key(action, t):
        found = None
        for d in acting:
            choice = str(d.get('choice'))
            if action and float(d.get('t', 0)) <= float(t or 0) and (choice == action or choice == 'put then ' + action):
                found = d
        return found
    steps, lines = defaultdict(list), []
    for e in events:
        kind, actor, message = e.get('kind'), e.get('actor'), str(e.get('message', ''))
        if kind == 'action_done' and str(e.get('action', '')).startswith('throw'):
            continue                                    # the thrown event says it, with the item and where
        mine = actor == 'jeff' and kind in OWN_KINDS
        mine_thrown = (kind == 'caught' and e.get('thrower') == 'jeff') or (kind == 'landed' and actor == 'jeff')
        to_me = (kind == 'caught' and actor == 'jeff') or (kind == 'landed' and actor == 'human' and e.get('target')
                                                           and (reaches is None or reaches('jeff', e['target'])))
        if not (mine or mine_thrown or to_me or kind in KITCHEN_KINDS):
            continue
        start = started.get(e.get('action_id'))
        if kind == 'arrival_conflict' and start is not None:
            label = re.sub(r' \(travel [^)]*\)$', '', str(start.get('message', '')).split('started: ', 1)[-1])
            reason = message.split(': ', 1)[-1].replace('; action cancelled', '')
            text = f'you: {LEFT.sub("", label)} - cancelled ({reason})'
        else:
            text = LEFT.sub('', _speaker(message, actor))
        if kind == 'landed' and actor == 'human':
            text += ' (thrown by the other chef)'
        if mine and kind in ('action_done', 'thrown', 'arrival_conflict', 'interrupted'):
            # By the time the step started; a step that started before the list did is matched by its option name
            # (a choice asked ahead is applied the moment the step before it ends, so the end time would mislead).
            d = decision_for(start.get('t')) if start is not None else by_key(e.get('action'), e.get('t'))
            if d is not None:
                steps[id(d)].append(len(lines))
                text += f' (you chose {_said(d)})'
        lines.append((e.get('t', 0), text))
    latest = acting[-1] if acting else None
    busy = kitchen is not None and getattr(kitchen.chefs.get('jeff'), 'job', None) is not None
    run = []

    def close_run():
        if run:
            first, last = run[0], run[-1]
            word = first.get('choice')
            if len(run) == 1:
                lines.append((first.get('t', 0), f'you chose {word}'))
            else:
                lines.append((first.get('t', 0), f"you chose {word} {len(run)} times, until {float(last.get('t', 0)):.1f} s"))
            run.clear()
    for d in decisions:
        if d.get('accepted') and d.get('choice') in QUIET and (not run or run[0].get('choice') == d.get('choice')):
            run.append(d)
            continue
        close_run()
        if d.get('accepted') and d.get('choice') in QUIET:
            run.append(d)
            continue
        if not d.get('accepted'):
            lines.append((d.get('t', 0), f"you chose {_said(d)}: not done ({d.get('result')})"))
        elif d.get('choice') in ('stop',):
            lines.append((d.get('t', 0), 'you chose stop'))
        elif not steps[id(d)]:
            lines.append((d.get('t', 0), f'you chose {_said(d)}' + (' (under way)' if d is latest and busy else '')))
        elif str(d.get('choice')).startswith('put then ') and len(steps[id(d)]) == 1 and d is not latest:
            at = steps[id(d)][0]
            when, text = lines[at]
            lines[at] = (when, text[:-1] + '; its second step did not start)')
    close_run()
    lines.sort(key=lambda line: line[0])                # stable: the engine's order within one moment
    state.pop('recent_events', None)
    state.pop('recent_decisions', None)
    state['timeline'] = [f'{t:.1f} s {text}' for t, text in lines]
    state['rules']['continuity'] = timeline_rule(state['rules'].get('continuity'))
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
# always comes. v2: the vessels rule always comes: it also says why an option is missing (an ingredient goes only into
# the vessel that cooks it, in the state it is cooked from), and v1 left it out exactly while Jeff held raw beef.
RULE_KINDS = {
    'tableware': POT_KINDS + WASH_KINDS + ('take_plate', 'plate_from_counter', 'discard', 'empty_burnt'),
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
    'one_press': ('put_then_take', 'put_then_chop', 'put_then_wash', 'put_then_fetch', 'wash_from_returns', 'empty_burnt'),
}


def listed_kinds(payload, kitchen):
    """The engine kinds of the options next_action lists; a one-press option is not in the engine's list, so its key
    names it ("put then take ...", "wash from ...", "empty ...")."""
    criteria = payload['questions']['next_action']['criteria']
    kinds = {a.kind for a in kitchen.actions('jeff') if a.key in criteria} if kitchen is not None else set()
    for key in criteria:
        if key.startswith('wash from '):
            kinds.add('wash_from_returns')
        elif key.startswith('empty '):
            kinds.add('empty_burnt')
        elif key.startswith('put then '):
            kinds.add('put_then_' + key.split()[2])
    return kinds


def _heat(kitchen_state):
    stations = (kitchen_state or {}).get('stations') or {}
    return any(s.get('fire') or s.get('fire_heat') or (s.get('stove') and s.get('food'))
               for s in stations.values() if isinstance(s, dict))


def _passing(kitchen_state, kitchen):
    """v3: the throw rule also says how a thrown item is caught or lands; it stays on a split floor (Jeff may be the
    one an item is thrown to) and while anything is in the air."""
    stations = (kitchen_state or {}).get('stations') or {}
    return (bool(getattr(kitchen, 'split_floor', False)) or bool((kitchen_state or {}).get('projectiles'))
            or any(isinstance(s, dict) and s.get('incoming_item') for s in stations.values()))


def rules_by_action(payload, kitchen):
    kinds = listed_kinds(payload, kitchen)
    state = payload['state']
    rules = state['rules']
    for name, needs in RULE_KINDS.items():
        if name not in rules or kinds & set(needs):
            continue
        if name == 'fire' and _heat(state.get('kitchen')):
            continue
        if name == 'throw' and _passing(state.get('kitchen'), kitchen):
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


def _needs(food, kj):
    """What a loose ingredient still needs before a dish takes it, from the engine's own facts in the request (v2):
    chopping left, and the vessel that cooks it and from which state."""
    item, stage = food.get('ingredient'), food.get('stage')
    if not item or food.get('plate_id') or stage not in ('raw', 'chopped'):
        return []
    out = []
    if stage == 'raw' and food.get('chop_remaining'):
        out.append(f"not chopped yet ({food['chop_remaining']:.1f} s of chopping)")
    cooked = any(c.get('item') == item and c.get('state') == 'ready'
                 for d in kj.get('dishes') or [] for c in d.get('components', []))
    for vessel in (kj.get('vessels') or {}).values():
        for c in vessel.get('cooks', []):
            if cooked and c.get('item') == item:
                out.append(f"a {vessel.get('name')} cooks it" + ('' if c.get('from') == stage else f" only once it is {c.get('from')}"))
    return out


def _burnt_for(food, kitchen):
    """v7: how long burnt food has been burnt, by the engine's own measure (Rules.overcook, what the burnt-food scoring
    reads); None for food that is not burnt."""
    if not isinstance(food, dict) or food.get('stage') != 'burnt' or kitchen is None:
        return None
    parts = food.get('components') or [food.get('ingredient')]
    try:
        return kitchen.rules.overcook(SimpleNamespace(stage='burnt', heated=float(food.get('heat_elapsed') or 0)), parts)
    except Exception:
        return None


def burnt_seconds(burnt):
    """v8: a burnt time as the view writes it, rounded up to the tenth of a second (within the 1e-8 s the tiers allow,
    Rules.burnt_tier), so food burnt past a tier's limit never reads as burnt for the limit itself."""
    return f'{math.ceil((burnt - 1e-8) * 10) / 10:.1f}'


def _a_stove_burns(kitchen):
    try:
        return any(kitchen.stations[sid].fire for sid in kitchen.pots)
    except Exception:
        return False


def _pan_next(food, kitchen):
    """v4: for a pan or pot off the stove with food in it, the next thing that happens once it is back on a stove,
    from the engine's heat thresholds and the food's heat so far (it keeps its heat off the stove). v7: while a stove
    burns, these times are for a stove that is not on fire (on a burning one food that is not burnt waits, and the
    stove does not catch fire again); burnt food says how long it has been burnt."""
    contents = food.get('contents')
    if food.get('stage') != 'pot' or not isinstance(contents, dict) or kitchen is None:
        return None
    try:
        ready, burn, fire = kitchen.rules.heat_thresholds(contents.get('ingredient'))
    except Exception:       # an item no vessel heats: nothing to say
        return None
    stage, heated = contents.get('stage'), float(contents.get('heat_elapsed') or 0)
    stove = 'a stove that is not on fire' if _a_stove_burns(kitchen) else 'a stove'
    if stage in ('chopped', 'cooking') and heated < ready:
        return f'cooked {ready - heated:.1f} s after it is back on {stove}'
    if stage == 'ready' and heated < burn:
        return f'burns {burn - heated:.1f} s after it is back on {stove}'
    if stage == 'burnt':
        burnt = _burnt_for(contents, kitchen)
        out = [f'burnt for {burnt_seconds(burnt)} s'] if burnt is not None else []
        if heated < fire:
            out.append(f'the stove catches fire {fire - heated:.1f} s after it is back on {stove}')
        return '; '.join(out) or None
    return None


def _food(food, kj=None, kitchen=None):
    if not isinstance(food, dict):
        return 'nothing'
    text = ' '.join(str(x) for x in (food.get('meaning') or food.get('stage'), food.get('id')) if x)
    if food.get('missing'):
        text += ' (still needs ' + ', '.join(food['missing']) + ')'
    needs = _needs(food, kj or {})
    pan = _pan_next(food, kitchen)
    if pan:
        needs.append(pan)
    burnt = _burnt_for(food, kitchen)       # v7: burnt food on a plate or loose
    if burnt is not None:
        needs.append(f'burnt for {burnt_seconds(burnt)} s')
    if needs:
        text += ' (' + '; '.join(needs) + ')'
    return text


def _stove(s, partner=None, kitchen=None):
    """Only the next thing to happen: while the food cooks when it is cooked (v3, the user's wording), once cooked
    when it burns, once burnt when the stove catches fire. v2 gave the burn and fire countdown while the food was
    still cooking, and Jev took the extinguisher with nothing burning (7 times in 3 rounds); v4 leaves the fire out
    of a cooked pan's line too (re-ask: extinguisher 3/57 with it, 0/57 without; the fire rule says it). partner:
    the other chef's walk to this stove in seconds, when the stove holds food (v4). v7: from the stove's heating as
    well, so on a burning stove food that does not heat waits until the fire is out and food still cooking is cooked
    and then waits (kitchen.ignite); burnt food says how long it has been burnt, and a burning stove does not catch
    fire again."""
    pan = f"{s.get('vessel_name') or 'pan'} {s['pot_id']}" if s.get('pot_id') else 'no pan'
    food = s.get('food')
    if not food:
        return f'{pan}, empty' if s.get('pot_id') else pan
    stage, ready, burn, fire = food.get('stage'), s.get('ready_in'), s.get('burn_in'), s.get('fire_in')
    heating, burning = bool(s.get('heating')), bool(s.get('fire'))
    wait = f"waits until the fire on {s.get('name') or 'this stove'} is out"
    times = []
    if stage == 'cooking' and heating and ready:
        times.append(f'cooked in {ready:.1f} s' + (f', then {wait}' if burning else ''))
    elif stage in ('cooking', 'ready') and burning and not heating:
        times.append(wait)
    elif stage == 'ready' and heating and burn:
        times.append(f'burns in {burn:.1f} s')
    elif stage == 'burnt':
        burnt = _burnt_for(food, kitchen)
        if burnt is not None:
            times.append(f'burnt for {burnt_seconds(burnt)} s')
        if fire and heating and not burning:
            times.append(f'the stove catches fire in {fire:.1f} s')
    if partner is not None:
        times.append(f'the other chef is {partner:.1f} s walk away')
    return f'{pan} with {_food(food)}' + (': ' + ', '.join(times) if times else '')


def _station(s, kj, kitchen=None, partner=None):
    kind, food = s.get('type'), s.get('food')
    if kind == 'ingredient_source':
        text = f"gives {s.get('supplies')}" + (f'; {_food(food, kj, kitchen)} lies on top, so it gives nothing' if food else '')
    elif kind == 'stove':
        text = _stove(s, partner, kitchen)
    elif kind in ('sink', 'drying_rack'):
        # v4: the top plate (the one being washed, or the clean one on top) is the station's food; the others stack
        # under it (v3 counted only those, so one clean plate on the rack read 'empty').
        plates = ([food] if food else []) + list(s.get('stack') or [])
        if plates:
            word = 'dirty' if kind == 'sink' else 'clean'
            text = f"{len(plates)} {word} plate" + ('' if len(plates) == 1 else 's') + f", {plates[0].get('id')} on top"
            washing, whole = (food or {}).get('wash_remaining'), (kj.get('tableware') or {}).get('wash_seconds')
            if kind == 'sink' and washing and whole and washing < whole:
                text += f' ({washing:.1f} s of washing left)'
        else:
            text = 'empty'
    elif kind == 'bin':
        text = 'bin'
    elif kind == 'serving_window':
        text = 'serving window'     # v4: v3 wrote "serve finished dishes here", which reads like an instruction
    elif food:
        text = _food(food, kj, kitchen)
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


def _walk(twin, who, target):
    """Seconds of walking from where the chef stands to the target, on a private fork; None when there is no route."""
    if twin is None:
        return None
    try:
        if not twin.reaches(who, target):
            return None
        return twin.travel_time(twin.chefs[who], target)
    except Exception:
        return None


def _stations(kj, kitchen):
    split = bool(getattr(kitchen, 'split_floor', False))
    vessels = kj.get('vessels') or {}
    forked = []

    def twin():                 # one private fork, made only when a stove holds food
        if not forked and kitchen is not None and hasattr(kitchen, 'travel_time'):
            import links
            forked.append(links._fork(kitchen))
        return forked[0] if forked else None
    groups = {}
    for sid, s in (kj.get('stations') or {}).items():
        if s.get('vessel') in vessels:
            s = {**s, 'vessel_name': vessels[s['vessel']].get('name')}
        groups.setdefault(_side(kitchen, sid) if split else 'all', []).append((sid, s))
    out = {}
    for side in (SIDES if split else ('all',)):
        listed, empty = {}, []
        for sid, s in groups.get(side, []):
            partner = _walk(twin(), 'human', sid) if s.get('type') == 'stove' and s.get('food') else None
            text = _station(s, kj, kitchen, partner)
            if text == 'empty' and s.get('type') == 'counter':
                empty.append(sid)
            else:
                listed[f"{s.get('name', sid)} ({sid})"] = text
        if empty:
            listed['empty counters'] = _ranges(empty)
        if listed:
            out[side] = listed
    return out if split else out.get('all', {})


def _nearest(kitchen, who):
    """v4: the station nearest to a chef standing on the floor (straight line to its access cell), by name."""
    try:
        here = kitchen.positions[who]
        best = min((math.dist(here, tuple(e.get('access') or e['cell'])), sid) for sid, e in kitchen.equipment.items()
                   if kitchen.reaches(who, sid))
    except Exception:
        return None
    return best[1]


def _chefs(kj, kitchen=None):
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
        at = ', '.join(x for x in (c.get('location_name'), c.get('area')) if x)
        if kitchen is not None and str(c.get('location', '')).startswith('floor'):
            near = _nearest(kitchen, who)
            if near:
                at += f", nearest station {(kj.get('stations') or {}).get(near, {}).get('name', near)} ({near})"
        if who == 'jeff':
            # v6: what Jeff holds (and what it still needs), nothing else; with empty hands no line at all.
            if c.get('holding'):
                out[WHO_LABEL[who]] = {'holding': _food(c.get('holding'), kj, kitchen)}
            continue
        out[WHO_LABEL[who]] = {'at': at, 'holding': _food(c.get('holding'), kj, kitchen), 'doing': doing}
        if c.get('knocked'):
            out[WHO_LABEL[who]]['knocked back'] = True
    return out


STATE_WORD = {'raw': 'as fetched', 'ready': 'cooked'}


def _flying(p, kj, kitchen=None):
    """v4: an item in the air named as the request names food elsewhere (v3 printed the raw stage: "P1 beef (pot)").
    v8: burnt food with its tier (_tiered); a burnt dish is a burnt dish, as food_names names it."""
    stage = p.get('stage')
    if stage == 'pot':
        vessel = ((kj.get('vessels') or {}).get(p.get('vessel')) or {}).get('name', 'pan')
        c = p.get('contents')
        return _tiered(f"{vessel} with {c['ingredient']} ({STATE_WORD.get(c['stage'], c['stage'])})" if c
                       else f'empty {vessel}', p, kitchen)
    if stage in ('clean_plate', 'dirty_plate'):
        return 'Clean plate' if stage == 'clean_plate' else 'Dirty plate'
    if p.get('plate_id') or p.get('components'):
        if stage == 'burnt':
            return _tiered('burnt dish', p, kitchen)
        parts = sorted(p.get('components') or [])
        dish = next((d.get('name') for d in kj.get('dishes') or []
                     if sorted(c.get('item') for c in d.get('components', [])) == parts), None)
        return dish or 'plate with ' + ', '.join(parts)
    return _tiered(f"{p.get('ingredient')} ({STATE_WORD.get(stage, stage)})", p, kitchen)


def _tiered(name, p, kitchen):
    """v8: the name of burnt food in the air with its tier (servability.described; its burnt time stands still in
    flight), from the engine's own item (Kitchen.burnt_service); the name as it is for anything else."""
    flying = (getattr(kitchen, 'projectiles', None) or {}).get(p.get('id')) if kitchen is not None else None
    food = flying.get('food') if isinstance(flying, dict) else None
    status = kitchen.burnt_service(food.contents if food.stage == 'pot' else food) if food is not None else None
    return servability.described(name, status) if status else name


def _in_the_air(kj, names, kitchen=None):
    out = []
    chefs = kj.get('chefs') or {}
    for p in kj.get('projectiles') or []:
        onto = p.get('onto')
        where = (f'{names.get(onto, onto)} ({onto})' if onto else
                 'floor ({},{})'.format(*p['landing_cell']) if p.get('landing_cell') else 'the floor')
        lands = max(0.0, float(p.get('lands_at', 0)) - float(kj.get('time', 0)))
        aimed = next((WHO_LABEL[who] for who, c in chefs.items() if who in WHO_LABEL and p.get('to') and c.get('position')
                      and math.dist(tuple(p['to']), tuple(c['position'])) < 0.75), None)
        out.append(f"{p.get('id')} {_flying(p, kj, kitchen)}, thrown by {WHO_LABEL.get(p.get('actor'), p.get('actor'))}"
                   + (f', aimed at {aimed}' if aimed else '') + f': comes down at {where} in {lands:.1f} s')
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
    # v5: no dishes block. The recipes are in rules.flow and the prices in rules.score; written out here as
    # "Steak": "beef (cooked); 50 yuan" the block made Jev take a plate first at 18 of 18 openings (1/18 without it)
    # and walk to the serving window 14/36 (6/36), the key steps unchanged (re-ask 2026-11-20).
    view = {
        'clock': f"{kj.get('time', 0):.1f} s of {kj.get('round_limit')} s ({kj.get('round_remaining', 0):.1f} s left)",
        'money': money,
        'orders_waiting': [{'id': o['id'], 'dish': dishes.get(o['dish'], o['dish']),
                            'time_left': f"{o.get('remaining', 0):.1f} s"}
                           for o in kj.get('orders') or [] if o.get('status') == 'pending'],
        'orders_served': ', '.join(f"{o['id']} {dishes.get(o['dish'], o['dish'])}" for o in kj.get('orders') or []
                                   if o.get('status') == 'served') or 'none',
        'chefs': _chefs(kj, kitchen),
        'stations': _stations(kj, kitchen),
    }
    if kj.get('vessels'):       # v2: which vessel cooks what, from which state
        view['vessels'] = {v.get('name', key): 'cooks ' + ', '.join(f"{c.get('item')} ({c.get('from')})" for c in v.get('cooks', []))
                           for key, v in kj['vessels'].items()}
    tableware = kj.get('tableware') or {}
    if tableware.get('total'):
        view['plates'] = f"{tableware['total']} plates in all" + ''.join(
            f"; {c.get('plate_id')} comes back " + ('when the plate return is free' if c.get('waiting_for_space')
                                                    else f"in {float(c.get('returns_in') or 0):.1f} s")
            for c in tableware.get('customers') or [])
    if kj.get('ground'):
        # v4: on a split floor grouped by who reaches the tile; two items on one tile both listed.
        split = bool(getattr(kitchen, 'split_floor', False))
        floor = {}
        for g in kj['ground']:
            bucket = floor.setdefault(_side(kitchen, g.get('location')), {}) if split else floor
            key, text = g.get('near', g.get('location')), _food(g.get('food'), kj, kitchen)
            bucket[key] = f'{bucket[key]}; {text}' if key in bucket else text
        view['floor'] = floor
    air = _in_the_air(kj, names, kitchen)
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
        make_timeline(payload, kitchen)
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
