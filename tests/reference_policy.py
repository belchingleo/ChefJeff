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
