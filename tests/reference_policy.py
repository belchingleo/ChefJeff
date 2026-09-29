"""A deterministic, recipe-following reference policy for regression traces.

It reads only the public snapshot and legal action list. It is not an AI
teammate, a difficulty oracle or a benchmark baseline: its sole purpose is to
drive the engine through preparation, cooking, assembly, service and plate
reuse so that behaviour fingerprints cover those paths. ``cook`` prepares and
cooks beef; ``assembler`` prepares vegetables/bread, assembles, serves and
washes.
"""

VEG = ('lettuce', 'tomato')


def _pick(actions, kind, target=None, key=None):
    for a in actions:
        if a.kind == kind and (target is None or a.target == target) and (key is None or a.key == key):
            return a
    return None


def _needs(state):
    """Earliest pending dish and the components still missing on the assembly plate."""
    pending = sorted((o for o in state['orders'] if o['status'] == 'pending'), key=lambda o: (o['deadline'], o['id']))
    # Legacy level 1 labels its steak orders with the display name.
    return [{'牛排': 'steak'}.get(o['dish'], o['dish']) for o in pending]


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
    if not food:
        return set()
    if food['stage'] == 'clean_plate':
        return set()
    return set(food.get('components') or ['beef'])


def _target_parts(dish):
    return {'steak': {'beef'}, 'burger': {'beef', 'bread', 'lettuce', 'tomato'}}.get(dish, {'beef'})


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
    want = set().union(*(_target_parts(d) for d in dishes[:1])) if dishes else set()
    missing = want - have

    def stoves(pred):
        return [key for key, s in sorted(state['stations'].items()) if s.get('stove') and pred(s)]

    if role == 'cook':
        if hand and hand['stage'] == 'pot':
            c = hand.get('contents')
            if c and c['stage'] == 'ready' and counter and 'beef' in missing:
                return _pick(actions, 'plate_counter', counter)
            if not c or c['stage'] in ('ready', 'burnt'):
                if c and c['stage'] == 'burnt':
                    return _pick(actions, 'empty_pot')
                return _pick(actions, 'return_pot')
            return _pick(actions, 'return_pot')
        if hand and hand.get('ingredient') == 'beef' and hand['stage'] == 'chopped':
            return _pick(actions, 'put_pot')
        if hand and hand.get('ingredient') == 'beef' and hand['stage'] == 'raw':
            return _pick(actions, 'put_board')
        if hand and hand['stage'] == 'extinguisher':
            return _pick(actions, 'extinguish') or _pick(actions, 'put_tool')
        if hand:
            return _pick(actions, 'drop')
        if any(s['fire'] for s in state['stations'].values()):
            return _pick(actions, 'take_tool')
        for key in stoves(lambda s: s['food'] and s['food']['stage'] == 'burnt'):
            return _pick(actions, 'clear', key)
        if counter and 'beef' in missing:
            for key in stoves(lambda s: s['food'] and s['food']['stage'] == 'ready'):
                a = _pick(actions, 'lift_pot', key)
                if a:
                    return a
        for key, s in sorted(state['stations'].items()):
            f = s.get('food')
            if f and f.get('ingredient') == 'beef' and not f.get('plate_id') and key.startswith('b') and s.get('used_by') is None:
                if f['stage'] == 'raw':
                    a = _pick(actions, 'chop', key)
                    if a:
                        return a
                if f['stage'] == 'chopped' and stoves(lambda s: s['pot_id'] and not s['food']):
                    return _pick(actions, 'take_board', key)
        beef = _loose(state, 'beef', ('raw', 'chopped', 'cooking', 'ready'))
        if beef < 1 and dishes:
            return _pick(actions, 'fetch', 'fridge')
        return _join(state, actions)

    # assembler
    if hand and hand['stage'] == 'dirty_plate':
        return _pick(actions, 'put_sink')
    if hand and hand.get('plate_id'):
        if hand.get('dish') and hand['dish'] in dishes:
            return _pick(actions, 'serve')
        return _pick(actions, 'put_counter')
    if hand and hand['stage'] == 'clean_plate':
        return _pick(actions, 'put_counter')
    if hand and hand.get('ingredient') in VEG + ('bread',):
        ready = hand['stage'] == 'chopped' or hand['ingredient'] == 'bread'
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
    ret = state['stations']['returns'].get('food')
    if ret and not sink:
        return _pick(actions, 'take_return', 'returns')
    for key, s in sorted(state['stations'].items()):
        f = s.get('food')
        if f and f.get('ingredient') in VEG and not f.get('plate_id') and key.startswith('b') and not key.startswith('bin'):
            if f['stage'] == 'raw' and s.get('used_by') is None:
                a = _pick(actions, 'chop', key)
                if a:
                    return a
            if f['stage'] == 'chopped' and f['ingredient'] in missing and counter:
                return _pick(actions, 'take_board', key)
    for name in ('bread',) + VEG:
        if name in missing and _loose(state, name, ('raw', 'chopped')) == 0:
            return _pick(actions, 'fetch', name)
    # Otherwise join any chopping/washing that the layout lets two chefs share.
    return _join(state, actions)


# --- Zoned pair with passing ---------------------------------------------------
# Calibration only (scripts/reference_sweep.py): a kitchen split by a counter row
# (Level 2) is worked from both sides. The 'runner' stays on the ingredient-source
# side: fetches, throws raw food onto boards, cooks, assembles near the stove and
# passes finished dishes across. The 'maker' stays on the board side: chops, throws
# prepared food back across, serves, returns and washes plates. The split is derived
# from the map (midway between source and board access rows), not from a level id.

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


def _station_side(k, key):
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
    stove = next((key for key, s in sorted(st.items()) if s.get('stove')), None)
    runner_counters = [key for key, s in sorted(st.items()) if s.get('counter') and _station_side(k, key) == 'runner']
    # Assembly plate: the most advanced clean/partial plate on a runner-side counter.
    assembly, plate = None, None
    for key in runner_counters:
        f = st[key].get('food')
        if f and (f['stage'] == 'clean_plate' or (f.get('plate_id') and f['stage'] in ('ready', 'assembled'))):
            if plate is None or len(_parts(f)) > len(_parts(plate)):
                assembly, plate = key, f
    want = _target_parts(dishes[0]) if dishes else set()
    missing = want - _parts(plate) if plate else set(want)
    fire = any(s['fire'] for s in st.values())

    def throw_onto(stations, goal):
        options = [a for a in actions if a.kind == 'throw' and a.target in stations]
        return min(options, key=lambda a: _near(k, a.target, goal)) if options else None

    def pass_floor(side, goal):
        options = [a for a in actions if a.kind == 'throw' and a.target in k.floor_places and _side(k, k.cell(a.target)[1]) == side]
        return min(options, key=lambda a: (abs(k.cell(a.target)[0] - k.equipment[goal]['access'][0])
                                           + abs(k.cell(a.target)[1] - k.equipment[goal]['access'][1]), a.target)) if options else None

    empty_boards = [b for b in k.boards if not st[b].get('food')]
    if hand and hand['stage'] == 'extinguisher':
        return _pick(actions, 'extinguish') or _pick(actions, 'put_tool')
    if hand and hand['stage'] == 'dirty_plate':
        return _pick(actions, 'put_sink')

    if role == 'runner':
        if hand and hand['stage'] == 'pot':
            c = hand.get('contents')
            if c and c['stage'] == 'ready' and assembly and 'beef' in missing:
                return _pick(actions, 'plate_counter', assembly)
            if c and c['stage'] == 'burnt':
                return _pick(actions, 'empty_pot')
            return _pick(actions, 'return_pot')
        if hand and hand.get('plate_id') and hand.get('dish'):
            return pass_floor('maker', 'serve') or _key(actions, 'go fridge')
        if hand and hand['stage'] == 'clean_plate':
            free = [c for c in runner_counters if not st[c].get('food')]
            return _key(actions, 'put ' + min(free, key=lambda c: _near(k, c, stove))) if free else None
        if hand and hand.get('ingredient'):
            name, stage = hand['ingredient'], hand['stage']
            if name == 'beef' and stage == 'chopped':
                return _pick(actions, 'put_pot') or throw_onto(empty_boards, stove)
            if stage == 'raw' and name != 'bread':
                # Onto a free board when in range, else onto the floor across the counter by the boards.
                return throw_onto(empty_boards, stove) or (pass_floor('maker', k.boards[0]) if empty_boards else None)
            if assembly and name in missing:
                return _pick(actions, 'assemble', assembly)
            return None
        if hand:
            return _pick(actions, 'drop')
        for key in sorted(st):
            if st[key].get('stove') and st[key]['food'] and st[key]['food']['stage'] == 'burnt':
                return _pick(actions, 'clear', key)
        if plate and plate.get('dish') and plate['dish'] in dishes:
            return _key(actions, 'take ' + assembly)
        if assembly and 'beef' in missing and st[stove]['food'] and st[stove]['food']['stage'] == 'ready':
            return _pick(actions, 'lift_pot', stove)
        for g in state['ground']:
            f = g['food']
            if (f.get('ingredient') and not f.get('plate_id') and f['stage'] == 'chopped'
                    and _side(k, k.cell(g['location'])[1]) == 'runner'
                    and ((f['ingredient'] == 'beef' and st[stove]['pot_id'] and not st[stove]['food'])
                         or (f['ingredient'] != 'beef' and assembly and f['ingredient'] in missing))):
                a = _key(actions, 'pickup ' + f['id'])
                if a:
                    return a
        for key in runner_counters:
            f = st[key].get('food')
            if f and not f.get('plate_id') and f.get('ingredient'):
                if (f['ingredient'] == 'beef' and st[stove]['pot_id'] and not st[stove]['food']) or (
                        f['ingredient'] != 'beef' and assembly and f['ingredient'] in missing):
                    a = _key(actions, 'take ' + key)
                    if a:
                        return a
        if not assembly and dishes:
            sink = st['sink'].get('food')
            if sink and sink['stage'] == 'clean_plate':
                return _pick(actions, 'take_sink', 'sink')
            for key, s in sorted(st.items()):
                f = s.get('food')
                if s.get('counter') and key not in runner_counters and f and f['stage'] == 'clean_plate':
                    return _key(actions, 'take ' + key)
        if dishes and _loose_all(state, 'beef') < 1:
            return _pick(actions, 'fetch', 'fridge')
        if assembly and 'bread' in missing:
            return _pick(actions, 'fetch', 'bread')
        for name in VEG:
            if assembly and name in missing and _loose(state, name, ('raw', 'chopped')) == 0 and empty_boards:
                return _pick(actions, 'fetch', name)
        return None

    # maker
    if hand and hand.get('plate_id'):
        if hand.get('dish') in dishes:
            return _pick(actions, 'serve')
        return _pick(actions, 'drop')
    if hand and hand.get('ingredient'):
        if hand['stage'] == 'raw':
            return _pick(actions, 'put_board')
        free = [c for c in runner_counters if not st[c].get('food')]
        return throw_onto(free, assembly or stove) or pass_floor('runner', stove)
    if hand:
        return _pick(actions, 'drop')
    if fire:
        return _pick(actions, 'take_tool')
    for g in state['ground']:
        f = g['food']
        if f.get('plate_id') and f.get('dish') in dishes:
            a = _key(actions, 'pickup ' + f['id'])
            if a:
                return a
    for g in state['ground']:
        f = g['food']
        if (f.get('ingredient') and not f.get('plate_id') and f['stage'] == 'raw' and empty_boards
                and _side(k, k.cell(g['location'])[1]) == 'maker'):
            a = _key(actions, 'pickup ' + f['id'])
            if a:
                return a
    for b in k.boards:
        f = st[b].get('food')
        if f and f['stage'] == 'raw':
            a = _pick(actions, 'chop', b)
            if a:
                return a
        if f and f['stage'] == 'chopped' and any(not st[c].get('food') for c in runner_counters):
            return _pick(actions, 'take_board', b)
    sink = st['sink'].get('food')
    if sink and sink['stage'] == 'dirty_plate':
        return _pick(actions, 'wash', 'sink')
    if st['returns'].get('food') and not sink:
        return _pick(actions, 'take_return', 'returns')
    return None


# --- One chef alone --------------------------------------------------------------
# Calibration only (scripts/reference_sweep.py): the "single chef" baseline. One chef
# takes both roles: beef work that cannot wait (fire, burnt pot, ready beef for the
# plate, chopping and loading beef) first, then fetching beef when none is in the
# pipeline, then the assembler's work. It is a scripted lower bound on what one chef
# can earn, not a claim about the best solo play.
_URGENT_COOK = ('take_tool', 'clear', 'lift_pot', 'take_board', 'chop', 'put_pot', 'return_pot', 'plate_counter', 'empty_pot')


def choose_solo(k, who, role=None):
    state = k.snapshot()
    me = state['chefs'][who]
    if me['job_id'] is not None:
        return None
    hand = me['holding']
    if hand:
        cookish = hand['stage'] in ('pot', 'extinguisher') or (hand.get('ingredient') == 'beef' and not hand.get('plate_id'))
        return choose(k, who, 'cook' if cookish else 'assembler')
    cook = choose(k, who, 'cook')
    if cook and cook.kind in _URGENT_COOK:
        return cook
    if cook and cook.kind == 'fetch':
        return cook
    return choose(k, who, 'assembler') or cook
