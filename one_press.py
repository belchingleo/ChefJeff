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
- empty <station> (v8; "empty p2" for a stove, "empty counter16" for a counter, board or supply, "empty ground P1" for
  a pan on the floor): a pan or pot of burnt food lies where Jeff could take it with empty hands (the engine's lift
  off a stove, take off a counter, board or supply, or pick-up off the floor, as the engine lists them for him with
  empty hands; on a split floor, by its reach rules), that station is not burning, and with that pan in his hands the
  engine would list an emptying for him (a bin he can reach). He puts down what he holds where put_where says (if he
  holds something), takes the pan (that same take), walks to the nearest bin the engine lists the emptying at (by
  its walk time from where he then stands) and empties the pan there (the engine's emptying of a held pan, at the
  ruleset's discard cost); the empty pan stays in his hands. The label gives the cost, and the burnt food's tier as
  the engine's own take of that pan gives it (servability): off a stove as it stands still there, on a stove as the
  lift leaves it, or, after a put, as it is now (as put then lift gives it), so serving it can be weighed against
  emptying it. The take and the emptying are done only while the pan holds burnt food: once it no longer does (the other
  chef swapped it out, took it or plated from it meanwhile) the chain ends. On a stove, counter, board or supply a pan swapped in that also holds burnt
  food is emptied all the same; on the floor a swap gives the ground item the incoming pan's id, so the chain ends. No listed action does this in one step (the
  engine empties only a pan in the hands). Also with the put_then_take flag.
  Counters, boards, supplies and the floor as well as stoves: emptying a pan there saves the same choice (the take,
  then the engine's emptying), and the pan holds up the next dish there too, since levels 1, 2, 4 and 5 have one pan
  per stove and no spare (level 3 has one spare): its stove cooks nothing until someone empties the pan and puts it
  back.
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

from kitchen import Action, Food

VERSION = 'one-press-v8'
THROW_TO_VERSION = 'throw-to-v1'      # the throw_to trial (features.json)
# v1: put then take and wash from the plate return only; v2 added put then chop and put then wash; v3 gives those two
# the seconds of work left, as the engine's own chop and wash labels do; v4 adds put then fetch; v5 words put then take
# of a pan or pot on a stove as the engine's own lift does (lift the pan, which stops heating off the stove), where v4
# said "take <its food> from Stove N": Jev took a pan whose food was still cooking about 20% of the times that option
# was offered and 1% of the times the plain lift was. v6 adds a free stove to the put places (the engine's own "put pot
# <stove>", listed while Jeff holds a pan or pot and the stove is free): before it, after plating from a pan Jeff could
# put the empty pan only on a counter, a supply or the floor, and in the user's 2026-11-21 level-4 rounds he set it
# down off the stoves about 3.5 times a round and never straight back. v7 (2026-11-22, servability-v1): put then take
# of burnt food or a pan of it ends with the tier a dish with it would be in, as the engine's take label does, and put
# then lift of a pan of burnt food with the tier as it is now, since the put comes first (" (it holds burnt food:
# accepted at -10 yuan for 2.1 s more while on the stove)"); v6 said nothing of the tier. v8 (2026-11-22) adds empty
# <station>: take a pan of burnt food off a stove, counter, board or supply that is not burning, or off the floor, walk
# to the nearest bin and empty it there, after a put when Jeff holds something; its label gives the discard cost and
# the tier as the engine's take of that pan does ("Lift the frying pan from Stove 1 and empty its burnt food at the
# nearest bin (2 yuan cost; keep the empty frying pan) (it holds burnt food: refused, burnt too long by the time it is
# lifted)"). Until v7 that took two choices: the take (or put then take), then the engine's emptying at a bin. RULE
# and the put_where question name it.
NAMES = ('put_then_take', 'wash_from_returns')
EMPTY = 'empty_burnt'           # empty <station> (v8)
EMPTY_KEY = 'empty '
# The engine's takes of a pan lying somewhere, as it lists them with empty hands: off a stove, a counter, a board (or a
# supply, whose take is take_counter) and the floor (empty_options).
EMPTY_TAKES = ('lift_pot', 'take_counter', 'take_board', 'pickup')
# A pan on the floor in empty's key and its pick-up step: "empty ground P1", as the engine's "plate ground P1".
GROUND = 'ground '
# The options that put the held item down first, where put_where says.
PUT_KINDS = ('put_then_take', 'put_then_chop', 'put_then_wash', 'put_then_fetch', 'wash_from_returns', EMPTY)
KINDS = PUT_KINDS + ('throw_to',)
THROW_TO = 'throw_to'           # the trial's flag in the one-press switches (features.one_press_flags)
PUT_WHERE = 'put_where'
PUT_WHERE_INSTRUCTIONS = ('Only if next_action is a "put then ...", "wash from" or "empty" action: where the held item goes '
                          'first. Otherwise it is not used.')
PUT_THEN_TAKE = 'put then take '
# The empty step's target: the bin nearest to Jeff when the step comes (find), among those listed for him.
NEAREST_BIN = 'nearest bin'
# A step with this third part is done only while the pan it lifts or holds has burnt food in it (the empty steps).
BURNT = 'burnt'
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
        'you hold something), takes the dirty plate from the plate return, puts it in the sink and washes it. "empty <station>" '
        '(and "empty ground <pot>" for a pot on the floor) puts down what you hold where questions.put_where says (if you hold '
        'something), takes the pot of burnt food lying there, carries it to the nearest bin you can reach and empties it '
        'there, at the cost its option gives; the empty pot stays in your hands, and the take and the emptying are done only '
        'while the pot holds burnt food. Each step follows the usual rules, as if you had chosen it; a step that cannot be '
        'done when it comes ends the action, and another '
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
                # The engine's own lift label: the pan or pot is what is taken, and it stops heating off the stove. v7:
                # its burnt food's tier is given as it is now (servability-v1): the lift's own label gives it as a lift
                # started now leaves it, and here the put comes first.
                label = (f'先把手中的{kitchen.food_name(held)}放到 put_where 选的位置，再{kitchen.plain_action(take).label}'
                         + kitchen.burnt_note(kitchen.burnt_service(food, kitchen.heat_rate(target)), '锅里是糊菜'))
            else:
                label = (f'先把手中的{kitchen.food_name(held)}放到 put_where 选的位置，'
                         f'再从{kitchen.stations[target].name}拿起{kitchen.food_name(food)}' + kitchen.food_note(food))
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
    if on['put_then_take']:
        out.extend(empty_options(kitchen, who, actions, empty))
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


def _taken_pan(kitchen, take):
    """The pan or pot this take of the engine's (EMPTY_TAKES) would put in the chef's hands, as the engine makes it, or
    None when it takes no pan."""
    if take.kind == 'pickup':
        item = kitchen.ground.get(take.expected[1])
        return item.food if item is not None and item.food.stage == 'pot' else None
    s = kitchen.stations.get(take.target)
    if s is None:
        return None
    if take.kind == 'lift_pot':
        return Food(s.pot_id, 'pot', contents=s.food) if s.pot_id else None     # as the engine's lift (Kitchen._finish)
    return s.food if s.food is not None and s.food.stage == 'pot' else None


def _empties(kitchen, who, pan):
    """Whether the engine lists an emptying of a held pan (empty_pot) for the chef with this pan in its hands,
    everything else as it is: on a split floor, at a bin on its part of the floor."""
    chef = kitchen.chefs[who]
    held = chef.hand
    chef.hand = pan
    try:
        return any(a.kind == 'empty_pot' for a in kitchen.actions(who))
    finally:
        chef.hand = held


def empty_options(kitchen, who, actions, empty):
    """empty <station> (see the module docstring): one per pan of burnt food that the engine lists a take of for the
    chef with empty hands (empty), off a station that is not burning, and that the engine would list an emptying of
    with the pan in the chef's hands."""
    held = kitchen.chefs[who].hand
    listed = {a.key for a in actions}
    loss = -kitchen.rules.penalty['discard']
    head = f'先把手中的{kitchen.food_name(held)}放到 put_where 选的位置，再' if held is not None else ''
    out, seen = [], set()
    for take in empty:
        if take.kind not in EMPTY_TAKES:
            continue
        pan, floor = _taken_pan(kitchen, take), take.kind == 'pickup'
        s = None if floor else kitchen.stations[take.target]
        if pan is None or pan.contents is None or pan.contents.stage != 'burnt' or (s is not None and s.fire):
            continue
        key = EMPTY_KEY + (GROUND + pan.id if floor else take.target)
        if key in seen or key in listed or not _empties(kitchen, who, pan):
            continue
        seen.add(key)
        v = kitchen.vessel_name(pan.id)
        # The tier as the engine's own take of the pan gives it (servability): on a stove as the lift leaves it (its
        # burnt time runs until the lift ends) or, after a put, as it is now (as put then lift); off a stove as it
        # stands still there. The engine's own discard cost; the empty pan stays in the hands, as with its emptying.
        if take.kind == 'lift_pot':
            taking = f'端起{s.name}的{v}'
            note = (kitchen.burnt_note(kitchen.burnt_service(pan.contents, kitchen.heat_rate(take.target)), '锅里是糊菜')
                    if held is not None else
                    kitchen.burnt_note(kitchen.step_service(who, take.target, 'lift_pot'), '锅里是糊菜', '端起'))
        else:
            taking = f'去{kitchen.place(take.target).name}捡起{v}' if floor else f'从{s.name}拿起{v}'
            note = kitchen.food_note(pan)
        label = f'{head}{taking}，到最近的垃圾桶倒掉锅里的糊菜（损耗{loss}元，保留空{v}）{note}'
        step = GROUND + pan.id if floor else take.target
        out.append(Action(key, label, EMPTY, take.target, (take.kind, step)))
    return out


def steps(action, kitchen):
    """The steps after the first put (or, with empty hands, all of them), as (kinds, target) to find among the listed
    actions; the empty steps carry a third part, BURNT (find)."""
    if action.kind == THROW_TO:
        return [(('go',), action.expected[1]), (('throw',), action.target)]
    if action.kind == EMPTY:
        take, where = action.expected
        return [((take,), where, BURNT), (('empty_pot',), NEAREST_BIN, BURNT)]
    if action.kind == 'put_then_take':
        return [(TAKES, action.target)]
    if action.kind == 'put_then_fetch':
        return [(('fetch',), action.target)]
    work = next((w for w, (kind, _) in PUT_THEN_WORK.items() if kind == action.kind), None)
    if work:
        return [((work,), action.target)]
    sink = getattr(kitchen, 'sink', None)
    return [(('take_return',), action.target), (('put_sink',), sink), (('wash',), sink)]


def _burnt_pan(kitchen, who, target):
    """Whether the pan this step takes (from the station target, or the floor: GROUND and its id), or holds for the
    nearest bin, has burnt food in it."""
    if target == NEAREST_BIN:
        pan = kitchen.chefs[who].hand
    elif isinstance(target, str) and target.startswith(GROUND):
        item = kitchen.ground.get(target[len(GROUND):])
        pan = item.food if item is not None else None
    else:
        s = kitchen.stations.get(target)
        pan = None if s is None else Food(s.pot_id, 'pot', contents=s.food) if s.pot_id else s.food
    food = pan.contents if pan is not None and pan.stage == 'pot' else None
    return food is not None and food.stage == 'burnt'


def _nearest(kitchen, who, actions):
    """Of these actions, the one at the station the chef walks to in the least time (the engine's walk time), or None."""
    chef, timed = kitchen.chefs[who], []
    for a in actions:
        try:
            timed.append((kitchen.travel_time(chef, a.target, a.kind), a.target, a))
        except ValueError:      # no route there from where the chef stands
            continue
    return min(timed, key=lambda row: row[:2])[2] if timed else None


def find(kitchen, who, step):
    """The listed action that does this step now, or None. A step with BURNT as its third part is done only while its
    pan has burnt food in it (_burnt_pan); NEAREST_BIN is the listed one of its kinds at the bin nearest to the chef,
    and GROUND and an item's id the listed pick-up of that item. A throw step (throw_to) is found with throws listed,
    also in a note fork that lists without them (links.LEAN)."""
    if 'throw' in step[0]:
        from kitchen import throw_listing
        with throw_listing(True):
            return _find(kitchen, who, step)
    return _find(kitchen, who, step)


def _find(kitchen, who, step):
    kinds, target = step[0], step[1]
    if len(step) > 2 and step[2] == BURNT and not _burnt_pan(kitchen, who, target):
        return None
    if target == NEAREST_BIN:
        return _nearest(kitchen, who, [a for a in kitchen.actions(who) if a.kind in kinds])
    if isinstance(target, str) and target.startswith(GROUND):
        item = target[len(GROUND):]
        return next((a for a in kitchen.actions(who) if a.kind in kinds and a.expected[1:2] == (item,)), None)
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

