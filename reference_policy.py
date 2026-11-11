"""A deterministic, recipe-following reference policy for regression traces and calibration.

It reads the public snapshot, the legal action list and where each ingredient is
dispensed. It is not an AI teammate, a difficulty oracle or a benchmark baseline:
its purpose is to drive the engine through preparation, cooking, assembly, service
and plate reuse so that behaviour fingerprints cover those paths, and to give level
calibration a scripted pair to measure. What each dish needs comes from the
snapshot's ``dishes`` and ``vessels``, so it plays any recipe of the catalog:
``cook`` prepares and cooks what the level's vessels cook (chopping it first when the
vessel takes it chopped); ``assembler`` prepares the other components (chops them, or
takes them as they come), assembles, serves and washes.
"""



def _rack_plate(k, stations):
    """The drying rack beside the sink, when a clean plate waits on it (levels with a rack; washed plates go there)."""
    rack = getattr(k, 'dryer', None)
    return rack if rack and (stations.get(rack) or {}).get('food') else None

def _pick(actions, kind, target=None, key=None):
    for a in actions:
        if a.kind == kind and (target is None or a.target == target) and (key is None or a.key == key):
            return a
    return None


def _needs(state):
    """Earliest pending dish and the components still missing on the assembly plate."""
    pending = sorted((o for o in state['orders'] if o['status'] == 'pending'), key=lambda o: (o['deadline'], o['id']))
    return [o['dish'] for o in pending]


def _recipes(state):
    """Dish -> [(item, required state)] in recipe order, for every dish the level can serve."""
    return {d['id']: [(c['item'], c['state']) for c in d['components']] for d in state['dishes']}


def _heat(state):
    """Item -> (vessel kind, state it goes in) for everything this level's vessels cook."""
    return {c['item']: (kind, c['from']) for kind, v in sorted(state['vessels'].items()) for c in v['cooks']}


def _prep(state, heat):
    """Components no vessel cooks -> the state a dish takes them in ('chopped', or 'raw' as dispensed)."""
    out = {}
    for parts in _recipes(state).values():
        for item, need in parts:
            if item not in heat:
                out.setdefault(item, need)
    return out


def _chopped_first(item, heat, prep):
    """Whether ``item`` is chopped on a board before it is cooked or plated."""
    return prep.get(item) == 'chopped' or (item in heat and heat[item][1] == 'chopped')


def _cooked(state, dishes, heat):
    """Cooked components of ``dishes``, in dish then recipe order, each once."""
    recipes, out = _recipes(state), []
    for dish in dishes:
        for item, _ in recipes.get(dish, ()):
            if item in heat and item not in out:
                out.append(item)
    return out


def _fetch(k, actions, item):
    """Fetch ``item`` from the ingredient source that dispenses it."""
    source = next((key for key, it in sorted(k.rules.sources.items()) if it == item), None)
    return _pick(actions, 'fetch', source) if source else None


def _assembly(state):
    """Counter holding the most advanced clean/partial plate (stable order)."""
    best = None
    for key, s in sorted(state['stations'].items()):
        f = s.get('food')
        if not s.get('counter') or not f or s.get('fire'):
            continue
        if f['stage'] == 'clean_plate' or (f.get('plate_id') and f['stage'] in ('ready', 'assembled')):
            score = len(f.get('components') or [])
            if best is None or score > best[0]:
                best = (score, key, f)
    return (best[1], best[2]) if best else (None, None)


def _parts(food):
    if not food or food['stage'] == 'clean_plate':
        return set()
    return set(food.get('components') or ([food['ingredient']] if food.get('ingredient') else []))


def _target_parts(state, dish):
    return {item for item, _ in _recipes(state).get(dish, ())}


def _loose(state, ingredient, stages):
    n = 0
    places = [s.get('food') for s in state['stations'].values()] + [c['holding'] for c in state['chefs'].values()]
    places += [g['food'] for g in state['ground']]
    for f in places:
        if f and not f.get('plate_id') and f.get('ingredient') == ingredient and f['stage'] in stages:
            n += 1
        if f and f['stage'] == 'pot' and f.get('contents') and f['contents'].get('ingredient') == ingredient:
            n += 1
    return n


def _join(state, actions):
    """Join work the partner is already doing, where the layout offers a second side."""
    for a in actions:
        if a.kind in ('chop', 'wash') and state['stations'][a.target].get('workers'):
            return a
    return None


def choose(k, who, role):
    state = k.snapshot()
    me = state['chefs'][who]
    if me['job_id'] is not None:
        return None
    actions = k.actions(who)
    hand = me['holding']
    dishes = _needs(state)
    counter, plate = _assembly(state)
    have = _parts(plate)
    want = set().union(*(_target_parts(state, d) for d in dishes[:1])) if dishes else set()
    missing = want - have
    heat = _heat(state)

    def stoves(pred):
        return [key for key, s in sorted(state['stations'].items()) if s.get('stove') and pred(s)]

    if role == 'cook':
        if hand and hand['stage'] == 'pot':
            c = hand.get('contents')
            if c and c['stage'] == 'ready' and counter and c['ingredient'] in missing:
                return _pick(actions, 'plate_counter', counter)
            if not c or c['stage'] in ('ready', 'burnt'):
                if c and c['stage'] == 'burnt':
                    return _pick(actions, 'empty_pot')
                return _pick(actions, 'return_pot')
            return _pick(actions, 'return_pot')
        if hand and not hand.get('plate_id') and hand.get('ingredient') in heat:
            goes_in = heat[hand['ingredient']][1]
            if hand['stage'] == goes_in:
                return _pick(actions, 'put_pot')
            if hand['stage'] == 'raw' and goes_in == 'chopped':
                return _pick(actions, 'put_board')
        if hand and hand['stage'] == 'extinguisher':
            return _pick(actions, 'extinguish') or _pick(actions, 'put_tool')
        if hand:
            return _pick(actions, 'drop')
        if any(s['fire'] for s in state['stations'].values()):
            return _pick(actions, 'take_tool')
        for key in stoves(lambda s: s['food'] and s['food']['stage'] == 'burnt'):
            return _pick(actions, 'lift_pot', key)
        if counter:
            for key in stoves(lambda s: s['food'] and s['food']['stage'] == 'ready' and s['food']['ingredient'] in missing):
                a = _pick(actions, 'lift_pot', key)
                if a:
                    return a
        for key, s in sorted(state['stations'].items()):
            f = s.get('food')
            if (f and f.get('ingredient') in heat and heat[f['ingredient']][1] == 'chopped' and not f.get('plate_id')
                    and s['type'] == 'board' and s.get('used_by') is None):
                if f['stage'] == 'raw':
                    a = _pick(actions, 'chop', key)
                    if a:
                        return a
                vessel = heat[f['ingredient']][0]
                if f['stage'] == 'chopped' and stoves(lambda s: s['pot_id'] and not s['food'] and s.get('vessel') == vessel):
                    return _pick(actions, 'take_board', key)
        for item in _cooked(state, dishes, heat):
            if _loose(state, item, ('raw', 'chopped', 'cooking', 'ready')) < 1:
                return _fetch(k, actions, item)
        return _join(state, actions)

    # assembler
    prep = _prep(state, heat)
    if hand and hand['stage'] == 'dirty_plate':
        return _pick(actions, 'put_sink')
    if hand and hand.get('plate_id'):
        if hand.get('dish') and hand['dish'] in dishes:
            return _pick(actions, 'serve')
        return _pick(actions, 'put_counter')
    if hand and hand['stage'] == 'clean_plate':
        return _pick(actions, 'put_counter')
    if hand and hand.get('ingredient') in prep:
        ready = hand['stage'] == prep[hand['ingredient']]
        if ready and counter and hand['ingredient'] in missing:
            return _pick(actions, 'assemble', counter)
        if not ready:
            return _pick(actions, 'put_board')
        return _pick(actions, 'drop')
    if hand:
        return _pick(actions, 'drop')
    if plate and plate.get('dish') and plate['dish'] in dishes:
        return _pick(actions, 'take_counter', counter)
    sink = state['stations']['sink'].get('food')
    if sink and sink['stage'] == 'dirty_plate':
        return _pick(actions, 'wash', 'sink')
    if sink and sink['stage'] == 'clean_plate' and not counter:
        return _pick(actions, 'take_sink', 'sink')
    rack = _rack_plate(k, state['stations'])
    if rack and not counter:
        return _pick(actions, 'take_plate', rack)
    ret = state['stations']['returns'].get('food')
    if ret and not sink:
        return _pick(actions, 'take_return', 'returns')
    for key, s in sorted(state['stations'].items()):
        f = s.get('food')
        if f and prep.get(f.get('ingredient')) == 'chopped' and not f.get('plate_id') and s['type'] == 'board':
            if f['stage'] == 'raw' and s.get('used_by') is None:
                a = _pick(actions, 'chop', key)
                if a:
                    return a
            if f['stage'] == 'chopped' and f['ingredient'] in missing and counter:
                return _pick(actions, 'take_board', key)
    # Fetch the first dish's missing components: those used as dispensed, then those to chop.
    first = [item for item, _ in _recipes(state).get(dishes[0], ())] if dishes else []
    for item in [i for i in first if prep.get(i) == 'raw'] + [i for i in first if prep.get(i) == 'chopped']:
        if item in missing and _loose(state, item, ('raw', 'chopped')) == 0:
            return _fetch(k, actions, item)
    # Otherwise join any chopping/washing that the layout lets two chefs share.
    return _join(state, actions)


# --- Zoned pair with passing ---------------------------------------------------
# Calibration only (scripts/reference_sweep.py): a kitchen split by a counter row
# (Level 2) is worked from both sides. The 'runner' stays on the ingredient-source
# side: fetches, throws raw food onto boards, cooks, assembles near the stove and
# passes finished dishes across. The 'maker' stays on the board side: chops, throws
# prepared food back across, serves, returns and washes plates. The split is derived
# from the map (midway between source and board access rows), not from a level id.
# The runner watches the first stove holding each vessel kind it needs.

def _key(actions, key):
    return next((a for a in actions if a.key == key), None)


def _split(k):
    src = [k.equipment[s]['access'][1] for s in k.equipment if k.equipment[s].get('type') == 'ingredient_source']
    boards = [k.equipment[b]['access'][1] for b in k.boards]
    return (sum(src) / len(src) + sum(boards) / len(boards)) / 2, sum(src) / len(src) < sum(boards) / len(boards)


def _side(k, y):
    split, sources_low = _split(k)
    if abs(y - split) < .5:
        return 'both'
    return 'runner' if (y < split) == sources_low else 'maker'


def _runner_part(k):
    """On a kitchen split by counters: the part of the floor by the ingredient sources, where the runner works."""
    if '_runner_part' not in k.__dict__:
        counts = {}
        for e in k.equipment.values():
            if e.get('type') == 'ingredient_source':
                for c in k.nav.neighbors(tuple(e['cell'])):
                    if c in k.floor_part:
                        counts[k.floor_part[c]] = counts.get(k.floor_part[c], 0) + 1
        k.__dict__['_runner_part'] = max(counts, key=lambda p: (counts[p], -p)) if counts else 0
    return k.__dict__['_runner_part']


def _cell_side(k, cell):
    """Whose side a floor cell is on: by the split line, or by the part of a floor split by counters."""
    if getattr(k, 'split_floor', False):
        return 'runner' if k.floor_part.get(tuple(cell)) == _runner_part(k) else 'maker'
    return _side(k, cell[1])


def _station_side(k, key):
    if getattr(k, 'split_floor', False):
        # A counter in the dividing row is worked from both parts; it counts as the runner's.
        e = k.equipment[key]
        sides = {k.floor_part.get(c) for cell in e.get('cells', [e['cell']]) for c in k.nav.neighbors(tuple(cell))}
        return 'runner' if _runner_part(k) in sides else 'maker'
    return _side(k, k.equipment[key]['access'][1])


def _near(k, key, goal):
    a, b = k.equipment[key]['access'], k.equipment[goal]['access']
    return (abs(a[0] - b[0]) + abs(a[1] - b[1]), key)


def _loose_all(state, ingredient):
    return _loose(state, ingredient, ('raw', 'chopped', 'cooking', 'ready'))


def choose_zoned(k, who, role):
    state = k.snapshot()
    me = state['chefs'][who]
    if me['job_id'] is not None:
        return None
    actions = k.actions(who)
    hand = me['holding']
    dishes = _needs(state)
    st = state['stations']
    heat = _heat(state)
    prep = _prep(state, heat)
    stove = next((key for key, s in sorted(st.items()) if s.get('stove')), None)

    def stove_for(item):
        return next((key for key, s in sorted(st.items()) if s.get('stove') and s.get('vessel') == heat[item][0]), None)

    def free_vessel(item):
        key = stove_for(item)
        return bool(key and st[key]['pot_id'] and not st[key]['food'])

    runner_counters = [key for key, s in sorted(st.items()) if s.get('counter') and _station_side(k, key) == 'runner']
    # Assembly plate: the most advanced clean/partial plate on a runner-side counter.
    assembly, plate = None, None
    for key in runner_counters:
        f = st[key].get('food')
        if f and (f['stage'] == 'clean_plate' or (f.get('plate_id') and f['stage'] in ('ready', 'assembled'))):
            if plate is None or len(_parts(f)) > len(_parts(plate)):
                assembly, plate = key, f
    want = _target_parts(state, dishes[0]) if dishes else set()
    missing = want - _parts(plate) if plate else set(want)
    fire = any(s['fire'] for s in st.values())

    def throw_onto(stations, goal):
        options = [a for a in actions if a.kind == 'throw' and a.target in stations]
        return min(options, key=lambda a: _near(k, a.target, goal)) if options else None

    def pass_floor(side, goal):
        options = [a for a in actions if a.kind == 'throw' and a.target in k.floor_places and _cell_side(k, k.cell(a.target)) == side]
        return min(options, key=lambda a: (abs(k.cell(a.target)[0] - k.equipment[goal]['access'][0])
                                           + abs(k.cell(a.target)[1] - k.equipment[goal]['access'][1]), a.target)) if options else None

    empty_boards = [b for b in k.boards if not st[b].get('food')]
    split = getattr(k, 'split_floor', False)
    if hand and hand['stage'] == 'extinguisher':
        return _pick(actions, 'extinguish') or _pick(actions, 'put_tool')
    if hand and hand['stage'] == 'dirty_plate':
        return _pick(actions, 'put_sink')

    if role == 'runner':
        if hand and hand['stage'] == 'pot':
            c = hand.get('contents')
            if c and c['stage'] == 'ready' and assembly and c['ingredient'] in missing:
                return _pick(actions, 'plate_counter', assembly)
            if c and c['stage'] == 'burnt':
                return _pick(actions, 'empty_pot')
            return _pick(actions, 'return_pot')
        if hand and hand.get('plate_id') and hand.get('dish'):
            if split and _pick(actions, 'serve'):
                return _pick(actions, 'serve')  # the serving window is on this side
            return pass_floor('maker', 'serve') or pass_floor('both', 'serve') or _key(actions, 'go fridge')
        if hand and hand['stage'] == 'clean_plate':
            free = [c for c in runner_counters if not st[c].get('food')]
            return _key(actions, 'put ' + min(free, key=lambda c: _near(k, c, stove))) if free else None
        if hand and hand.get('ingredient'):
            name, stage = hand['ingredient'], hand['stage']
            if name in heat and stage == heat[name][1]:
                if stage == 'chopped':
                    return _pick(actions, 'put_pot') or throw_onto(empty_boards, stove)
                return _pick(actions, 'put_pot')
            if stage == 'raw' and _chopped_first(name, heat, prep):
                # Onto a free board when in range, else onto the floor across the counter by the boards.
                # Out of range of the maker's floor (e.g. straight from the fridge), pass onto the floor
                # on the dividing line instead; the maker picks it up from there.
                return throw_onto(empty_boards, stove) or ((pass_floor('maker', k.boards[0]) or pass_floor('both', k.boards[0]))
                                                           if empty_boards else None)
            if assembly and name in missing:
                return _pick(actions, 'assemble', assembly)
            return None
        if hand:
            return _pick(actions, 'drop')
        for key in sorted(st):
            if st[key].get('stove') and st[key]['food'] and st[key]['food']['stage'] == 'burnt':
                return _pick(actions, 'lift_pot', key)
        if plate and plate.get('dish') and plate['dish'] in dishes:
            return _key(actions, 'take ' + assembly)
        if assembly:
            for item in _cooked(state, dishes[:1], heat):
                key = stove_for(item)
                f = key and st[key]['food']
                if item in missing and f and f['stage'] == 'ready' and f['ingredient'] == item:
                    return _pick(actions, 'lift_pot', key)
        for g in state['ground']:
            f = g['food']
            if not (f.get('ingredient') and not f.get('plate_id') and _cell_side(k, k.cell(g['location'])) == 'runner'):
                continue
            name = f['ingredient']
            if ((name in heat and f['stage'] == heat[name][1] and free_vessel(name))
                    or (name not in heat and f['stage'] == 'chopped' and assembly and name in missing)):
                a = _key(actions, 'pickup ' + f['id'])
                if a:
                    return a
        for key in runner_counters:
            f = st[key].get('food')
            if f and not f.get('plate_id') and f.get('ingredient'):
                name = f['ingredient']
                if (name in heat and free_vessel(name)) or (name not in heat and assembly and name in missing):
                    a = _key(actions, 'take ' + key)
                    if a:
                        return a
        if not assembly and dishes:
            sink = st['sink'].get('food')
            if sink and sink['stage'] == 'clean_plate':
                return _pick(actions, 'take_sink', 'sink')
            rack = _rack_plate(k, st)
            if rack:
                return _pick(actions, 'take_plate', rack)
            for key, s in sorted(st.items()):
                f = s.get('food')
                if s.get('counter') and key not in runner_counters and f and f['stage'] == 'clean_plate':
                    return _key(actions, 'take ' + key)
        for item in _cooked(state, dishes, heat):
            if _loose_all(state, item) < 1:
                return _fetch(k, actions, item)
        first = [item for item, _ in _recipes(state).get(dishes[0], ())] if dishes else []
        for item in first:
            if assembly and prep.get(item) == 'raw' and item in missing:
                return _fetch(k, actions, item)
        for item in first:
            if (assembly and prep.get(item) == 'chopped' and item in missing
                    and _loose(state, item, ('raw', 'chopped')) == 0 and empty_boards):
                return _fetch(k, actions, item)
        return None

    # maker
    if hand and hand.get('plate_id'):
        if hand.get('dish') in dishes:
            return _pick(actions, 'serve')
        return _pick(actions, 'drop')
    if hand and hand.get('ingredient'):
        if hand['stage'] == 'raw' and _chopped_first(hand['ingredient'], heat, prep):
            return _pick(actions, 'put_board')
        free = [c for c in runner_counters if not st[c].get('food')]
        return throw_onto(free, assembly or stove) or pass_floor('runner', stove)
    if split and hand and hand['stage'] == 'clean_plate':
        # The runner cannot reach the sink: pass a clean plate onto a counter on its side.
        free = [c for c in runner_counters if not st[c].get('food')]
        near = [c for c in free if k.reaches(who, c)]  # a counter in the dividing row
        return throw_onto(free, stove) or (_key(actions, 'put ' + near[0]) if near else None)
    if hand:
        return _pick(actions, 'drop')
    if fire:
        return _pick(actions, 'take_tool')
    sink_food = st['sink'].get('food')
    if split and not assembly and dishes and sink_food and sink_food['stage'] == 'clean_plate':
        return _pick(actions, 'take_sink', 'sink')
    if split and not assembly and dishes and _rack_plate(k, st):
        return _pick(actions, 'take_plate', _rack_plate(k, st))
    for g in state['ground']:
        f = g['food']
        if f.get('plate_id') and f.get('dish') in dishes:
            a = _key(actions, 'pickup ' + f['id'])
            if a:
                return a
    for g in state['ground']:
        f = g['food']
        if (f.get('ingredient') and not f.get('plate_id') and f['stage'] == 'raw' and empty_boards
                and _chopped_first(f['ingredient'], heat, prep)
                and _cell_side(k, k.cell(g['location'])) in ('maker', 'both')):
            a = _key(actions, 'pickup ' + f['id'])
            if a:
                return a
    for b in k.boards:
        f = st[b].get('food')
        if f and f['stage'] == 'raw':
            a = _pick(actions, 'chop', b)
            if a:
                return a
        # On a kitchen split by counters the maker can also pass it across onto the runner's floor.
        if f and f['stage'] == 'chopped' and (any(not st[c].get('food') for c in runner_counters) or getattr(k, 'split_floor', False)):
            return _pick(actions, 'take_board', b)
    sink = st['sink'].get('food')
    if sink and sink['stage'] == 'dirty_plate':
        return _pick(actions, 'wash', 'sink')
    if st['returns'].get('food') and not sink:
        return _pick(actions, 'take_return', 'returns')
    return None


# --- One chef alone --------------------------------------------------------------
# Calibration only (scripts/reference_sweep.py): the "single chef" baseline. One chef
# takes both roles: cooking work that cannot wait (fire, burnt pot to the bin, cooked food for
# the plate, chopping and loading what a vessel cooks) first, then fetching what to cook when
# none is in the pipeline, then the assembler's work. It is a scripted lower bound on what one
# chef can earn, not a claim about the best solo play.
_URGENT_COOK = ('take_tool', 'lift_pot', 'take_board', 'chop', 'put_pot', 'return_pot', 'plate_counter', 'empty_pot')


def choose_solo(k, who, role=None):
    state = k.snapshot()
    me = state['chefs'][who]
    if me['job_id'] is not None:
        return None
    hand = me['holding']
    if hand:
        cookish = hand['stage'] in ('pot', 'extinguisher') or (hand.get('ingredient') in _heat(state) and not hand.get('plate_id'))
        return choose(k, who, 'cook' if cookish else 'assembler')
    cook = choose(k, who, 'cook')
    if cook and cook.kind in _URGENT_COOK:
        return cook
    if cook and cook.kind == 'fetch':
        return cook
    return choose(k, who, 'assembler') or cook
