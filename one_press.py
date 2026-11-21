"""One-press options for Jeff (released: features.json turns them on for every round, with no switch in the page;
turning `one_press` off there rolls them back): several presses a player makes without
thinking, offered as one choice and carried out as the same ordinary steps, one after another.

- put then take <station>: Jeff holds an item and another item lies on <station> that he could take with empty
  hands, while no other listed action is at <station>. He puts the held item where questions.put_where says
  (one of the put places the request already lists; a free stove for a held pan or pot is one of them since v6),
  then takes the item from <station>.
- put then chop <board> and put then wash <sink>: the same, for the work the engine lets him do there only with
  empty hands (chopping what lies on the board, washing the dirty plate in the sink): he puts the held item
  where put_where says, then chops or washes. All three go with the put_then_take flag (one_press.flags; both
  flags are on whenever the feature is, as features.one_press_flags gives them).
- put then fetch <ingredient> (key as the engine's fetch key, e.g. "put then fetch beef"): Jeff holds an item, so
  the engine does not list fetching from an ingredient source he could fetch from with empty hands. He puts the
  held item where put_where says, then fetches from that source. Also with the put_then_take flag.
- wash from <plate return>: a dirty plate is on the plate return, the sink is empty and not burning. Jeff puts
  down what he holds where put_where says (if he holds something), takes the dirty plate, puts it in the sink
  and washes it.
- throw to <station> (the throw_to trial, features.json, off by default; with it on the flags carry throw_to): on a
  split floor Jeff holds an item a station on the other part would take and work on (an empty board while it still
  needs chopping, an empty pan on a stove that cooks it), and no throw listed from where he stands lands there. He
  walks to the nearest floor tile one of the player's eight aimed throws lands there from
  (SpatialKitchen.throw_spots), then throws. No put first, so no put_where.

Nothing here judges what he should do: the options only save presses, and each step is checked and started
by the engine as if he had chosen it, so a step that cannot be done when it comes ends the chain. The engine
itself is unchanged, but for accepting the walk to a throw spot (SpatialKitchen.throw_spot_walk); the decision loop (jev.DecisionLoop) runs the steps. Both chefs keep the same rules.
"""
from __future__ import annotations

from kitchen import Action

VERSION = 'one-press-v6'
THROW_TO_VERSION = 'throw-to-v1'      # the throw_to trial (features.json)
# v1: put then take and wash from the plate return only; v2 added put then chop and put then wash; v3 gives those two
# the seconds of work left, as the engine's own chop and wash labels do; v4 adds put then fetch; v5 words put then take
# of a pan or pot on a stove as the engine's own lift does (lift the pan, which stops heating off the stove), where v4
# said "take <its food> from Stove N": Jev took a pan whose food was still cooking about 20% of the times that option
# was offered and 1% of the times the plain lift was. v6 adds a free stove to the put places (the engine's own "put pot
# <stove>", listed while Jeff holds a pan or pot and the stove is free): before it, after plating from a pan Jeff could
# put the empty pan only on a counter, a supply or the floor, and in the user's 2026-11-21 level-4 rounds he set it
# down off the stoves about 3.5 times a round and never straight back.
NAMES = ('put_then_take', 'wash_from_returns')
# The options that put the held item down first, where put_where says.
PUT_KINDS = ('put_then_take', 'put_then_chop', 'put_then_wash', 'put_then_fetch', 'wash_from_returns')
KINDS = PUT_KINDS + ('throw_to',)
THROW_TO = 'throw_to'           # the trial's flag in the one-press switches (features.one_press_flags)
PUT_WHERE = 'put_where'
PUT_THEN_TAKE = 'put then take '
# Work at a station the engine lists only with empty hands, offered after a put: kind -> (option kind, key prefix).
PUT_THEN_WORK = {'chop': ('put_then_chop', 'put then chop '), 'wash': ('put_then_wash', 'put then wash ')}
# What takes the item lying on a station with empty hands (the engine's own kinds).
TAKES = ('take_board', 'take_counter', 'take_return', 'take_sink', 'take_plate', 'lift_pot')
# Where a held item can be put down: the put places a request lists.
PLACES = ('put_counter', 'put_board', 'put_tool', 'drop', 'return_pot')
RULE = ('Some actions save presses. "put then take <station>" puts the item you hold where questions.put_where says, then takes '
        'the item lying on that station; "put then chop <board>" and "put then wash <sink>" put it there likewise, then chop what '
        'lies on the board or wash the dirty plate in the sink; "put then fetch <ingredient>" puts it there likewise, then '
        'fetches that ingredient from its source. "wash from <plate return>" puts down what you hold where questions.put_where says (if '
        'you hold something), takes the dirty plate from the plate return, puts it in the sink and washes it. Each step follows '
        'the usual rules, as if you had chosen it; a step that cannot be done when it comes ends the action, and another '
        'action you choose meanwhile replaces it. questions.put_where lists the put places of next_action and is used only by '
        'these actions.')


def flags(value):
    """The switches as a dict of booleans, or None when none is on."""
    on = {name: bool((value or {}).get(name)) for name in NAMES}
    return on if any(on.values()) else None


def condition(value):
    """The one_press condition a round's start row and research record carry; nothing when every switch is off."""
    on = flags(value)
    trial = {THROW_TO: True} if on and (value or {}).get(THROW_TO) else {}
    return {'one_press': {**on, **trial, 'version': VERSION}} if on else {}


def _empty_handed(kitchen, who):
    """The actions the engine would list if the chef's hands were empty, everything else as it is."""
    chef = kitchen.chefs[who]
    held = chef.hand
    if held is None:
        return kitchen.actions(who)
    chef.hand = None
    try:
        return kitchen.actions(who)
    finally:
        chef.hand = held


def options(kitchen, who, actions, value):
    """The one-press actions to add to these listed actions, for the switches that are on."""
    on = flags(value)
    if not on or kitchen.chefs[who].job is not None:
        return []
    chef = kitchen.chefs[who]
    held = chef.hand
    empty = _empty_handed(kitchen, who)
    acted = {a.target for a in actions if a.kind not in ('go', 'throw')}
    out = []
    if on['put_then_take'] and held is not None:
        seen = set()
        for take in empty:
            target = take.target
            if take.kind not in TAKES or target in acted or target in seen or target not in kitchen.stations:
                continue
            food = kitchen.stations[target].food
            if food is None:
                continue
            seen.add(target)
            if take.kind == 'lift_pot':
                # The engine's own lift label: the pan or pot is what is taken, and it stops heating off the stove.
                label = f'先把手中的{kitchen.food_name(held)}放到 put_where 选的位置，再{take.label}'
            else:
                label = (f'先把手中的{kitchen.food_name(held)}放到 put_where 选的位置，'
                         f'再从{kitchen.stations[target].name}拿起{kitchen.food_name(food)}')
            out.append(Action(PUT_THEN_TAKE + target, label, 'put_then_take', target))
        worked = set()
        for work in empty:
            target = work.target
            if work.kind not in PUT_THEN_WORK or target in acted or (work.kind, target) in worked or target not in kitchen.stations:
                continue
            food = kitchen.stations[target].food
            if food is None:
                continue
            worked.add((work.kind, target))
            kind, prefix = PUT_THEN_WORK[work.kind]
            name, item = kitchen.stations[target].name, kitchen.food_name(food)
            # The seconds of work left, as the engine's own chop and wash labels give them.
            if work.kind == 'chop':
                then = f'再到{name}切{item}（剩 {max(0, kitchen.rules.chop_work(food.ingredient) - food.chopped):.1f}s）'
            else:
                then = f'再到{name}洗碗（剩 {max(0, kitchen.wash_seconds - food.washed):.1f}s）'
            out.append(Action(prefix + target, f'先把手中的{kitchen.food_name(held)}放到 put_where 选的位置，{then}', kind, target))
        listed, fetched = {a.key for a in actions}, set()
        for fetch in empty:
            target = fetch.target
            if fetch.kind != 'fetch' or fetch.key in listed or target in fetched or target not in kitchen.stations:
                continue
            fetched.add(target)
            ingredient = kitchen.ingredients[target]
            item = kitchen.state_label(ingredient, kitchen.rules.items[ingredient]['initial_state'])   # as the fetch label
            out.append(Action('put then ' + fetch.key, f'先把手中的{kitchen.food_name(held)}放到 put_where 选的位置，'
                              f'再到{kitchen.stations[target].name}取一份{item}', 'put_then_fetch', target))
    if (value or {}).get(THROW_TO) and held is not None and hasattr(kitchen, 'throw_spots'):
        out.extend(throw_to_options(kitchen, who, actions))
    if on['wash_from_returns']:
        returns = getattr(kitchen, 'returns', None)
        sink_key = getattr(kitchen, 'sink', None)
        takes_plate = any(a.kind == 'take_return' and a.target == returns for a in empty)
        sink = kitchen.stations.get(sink_key) if sink_key else None
        plate = kitchen.stations[returns].food if returns in kitchen.stations else None
        if (takes_plate and sink is not None and plate is not None and plate.stage == 'dirty_plate'
                and sink.food is None and not sink.fire and sink.lock in (None, who)):
            names = kitchen.stations[returns].name, sink.name
            label = (f'先把手中的{kitchen.food_name(held)}放到 put_where 选的位置，再从{names[0]}拿起脏餐盘，放入{names[1]}并洗碗'
                     if held is not None else f'从{names[0]}拿起脏餐盘，放入{names[1]}并洗碗')
            out.append(Action(f'wash from {returns}', label, 'wash_from_returns', returns))
    return out


def steps(action, kitchen):
    """The steps after the first put (or, with empty hands, all of them), as (kinds, target) to find among the listed actions."""
    if action.kind == THROW_TO:
        return [(('go',), action.expected[1]), (('throw',), action.target)]
    if action.kind == 'put_then_take':
        return [(TAKES, action.target)]
    if action.kind == 'put_then_fetch':
        return [(('fetch',), action.target)]
    work = next((w for w, (kind, _) in PUT_THEN_WORK.items() if kind == action.kind), None)
    if work:
        return [((work,), action.target)]
    sink = getattr(kitchen, 'sink', None)
    return [(('take_return',), action.target), (('put_sink',), sink), (('wash',), sink)]


def find(kitchen, who, step):
    """The listed action that does this step now, or None."""
    kinds, target = step
    listed = next((a for a in kitchen.actions(who) if a.kind in kinds and a.target == target), None)
    if listed is None and kinds == ('go',) and hasattr(kitchen, 'throw_spot_walk'):
        # throw_to's walk to its throw spot: not listed for Jeff, accepted by the engine (throw_spot_walk).
        walk = Action('go ' + target, f'走到{kitchen.place(target).name}', 'go', target)
        return walk if kitchen.throw_spot_walk(who, walk) else None
    return listed


def place(actions, answer):
    """The put action put_where chose among these listed actions, or a fallback: the first listed put place."""
    listed = {a.key: a for a in actions if a.kind in PLACES}
    if answer in listed:
        return listed[answer], False
    fallback = next(iter(listed.values()), None)
    return fallback, fallback is not None


def throw_to_options(kitchen, who, actions):
    """The throw_to trial's options (see the module docstring): one per station, from its nearest throw spot."""
    import food_names
    from model_language import english_text
    from spatial_kitchen import THROW_DIRECTIONS
    held = kitchen.chefs[who].hand
    hit = {a.target for a in actions if a.kind == 'throw'}
    out = []
    for station, spots in kitchen.throw_spots(who).items():
        if station in hit:
            continue
        chef = kitchen.chefs[who]
        timed = []
        for tile, direction in spots:
            try:
                timed.append((kitchen.travel_time(chef, tile), tile, direction))
            except Exception:       # no route the engine would walk
                continue
        if not timed:
            continue
        seconds, tile, direction = min(timed)
        cell = kitchen.cell(tile)
        name, floor = kitchen.stations[station].name, kitchen.place(tile).name
        toward = THROW_DIRECTIONS[direction][1]
        label = f'走到{floor}，向{toward}抛出手中物品（落到{name}）'
        english = (f'Walk to floor ({cell[0]},{cell[1]}) and throw the held {food_names.plain(kitchen, held)} {direction} '
                   f'onto {english_text(name)}')
        out.append(Action(f'throw to {station}', label, THROW_TO, station, (held.id, tile, direction), english=english))
    return out

