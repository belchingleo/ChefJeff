"""Order pacing and target money for a level a player built, measured with the scripted reference chefs.

A player's level keeps the release's rules: the ruleset, the equipment and every ingredient,
container and cooking step come from the release; the player supplies the map, the level's
spawns and inventory, the dishes (name, price, components) and the menu.

Pacing follows a fixed rule (owner decision 2026-11-01): one order every 30 game seconds, as on
levels 1 and 3, and each dish waits 5 times its chop and cook seconds, rounded to 15 s within
60-135 s (steak 75 s and burger 105 s, as authored). 135 s is the longest wait that keeps at most
five tickets open at one order per 30 s, the most the order rail shows. The target is half the scripted pair's median
income, rounded down to 10, as for the authored levels; a player level is measured on 7 order seeds
(authored levels on 21). A level the scripted pair serves nothing on is not playable; one the solo
chef can pass is playable with a note.
"""
import copy
from multiprocessing import Pool
import statistics
import unicodedata

import config_contract as cc

INTERVAL_GAME_MS = 30000
PATIENCE_FACTOR = 5
PATIENCE_STEP_GAME_MS = 15000
PATIENCE_RANGE_GAME_MS = (60000, 135000)
SEEDS = tuple(range(1, 8))
PRICE_RANGE = (10, 150)
PRICE_STEP = 10
DISPLAY_NAME_LENGTH = 20
# Where a player's own names for the dishes are kept: for the page, never in the game's text.
DISPLAY_NAMES = 'chefjeff.player_dish_names'
PAIRINGS = (('classic', False), ('classic', True), ('zoned', False), ('zoned', True))
PLAYER_PREFIX = 'player-'
# Any authored level carries the release's ruleset, equipment and ingredient data.
RELEASE_LEVEL = 'level-1'


def drive(k, roles, policy, period):
    """Run one round to closing. Stalled routes are the engine's job (movement.stall_replan)."""
    step = 0
    while not k.ended:
        for who, role in roles:
            if step % period[who] == 0:
                action = policy(k, who, role)
                if action:
                    k.start(who, action)
        k.advance(.05)
        step += 1


def component_name(part):
    """A component in English from its item id and state, e.g. "chopped lettuce", "cooked chicken", "bread"."""
    words = {'raw': '', 'chopped': 'chopped ', 'ready': 'cooked '}
    return words.get(part['state'], part['state'] + ' ') + part['item']


def display_name(value):
    """A player's name for a dish, trimmed and without control characters, or None."""
    if not isinstance(value, str):
        return None
    text = ''.join(ch for ch in value if not unicodedata.category(ch).startswith('C')).strip()
    return text if 1 <= len(text) <= DISPLAY_NAME_LENGTH else None


def _dishes(recipes, given, problems):
    """The player's dishes renamed dish_1, dish_2... and named by their components (owner decision 2026-11-01:
    Jeff reads dish ids and names, and must see the components in English, never a player's text), plus
    {old id: new id} and {new id: the player's name}. ``given`` holds names an earlier pass kept, so a
    normalized level normalizes to itself."""
    dishes, renamed, names = {}, {}, {}
    for n, (dish, recipe) in enumerate(recipes.items(), 1):
        parts = recipe.get('components') if isinstance(recipe, dict) else None
        if (not isinstance(parts, list) or not parts
                or not all(isinstance(p, dict) and isinstance(p.get('item'), str) and isinstance(p.get('state'), str) for p in parts)):
            problems.append(cc.diag('BUNDLE_INVALID', 'ERROR', f'/recipe_catalog/recipes/{dish}/components',
                                    'each component needs an item and a state'))
            continue
        price = recipe.get('price')
        if type(price) is not int or not PRICE_RANGE[0] <= price <= PRICE_RANGE[1] or price % PRICE_STEP:
            problems.append(cc.diag('PRICE_OUT_OF_RANGE', 'ERROR', f'/recipe_catalog/recipes/{dish}/price',
                                    f'a dish costs {PRICE_RANGE[0]}-{PRICE_RANGE[1]} in steps of {PRICE_STEP}'))
        new = f'dish_{n}'
        components = [{'item': p['item'], 'state': p['state'], 'label': component_name(p)} for p in parts]
        name = ' + '.join(c['label'] for c in components)
        dishes[new] = {'name': name, 'container': 'plate', 'price': price, 'components': components}
        renamed[dish] = new
        names[new] = display_name(given.get(dish)) or display_name(recipe.get('name')) or name
    return dishes, renamed, names


def normalize(bundle, registry=None):
    """The player's level on the release's rules: (bundle, diagnostics). Nothing is calibrated yet."""
    release = cc.level_bundle(RELEASE_LEVEL, registry, embed=True)
    out = copy.deepcopy(bundle) if isinstance(bundle, dict) else {}
    problems = []
    for kind in ('level', 'map', 'order_policy'):
        if not isinstance(out.get(kind), dict):
            problems.append(cc.diag('BUNDLE_INVALID', 'ERROR', '/' + kind, f'{kind} must be an object'))
    recipes = (out.get('recipe_catalog') or {}).get('recipes') if isinstance(out.get('recipe_catalog'), dict) else None
    if not isinstance(recipes, dict) or not recipes:
        problems.append(cc.diag('BUNDLE_INVALID', 'ERROR', '/recipe_catalog/recipes', 'at least one dish is needed'))
    if problems:
        return None, problems
    out['schema_version'] = release['schema_version']
    for kind in ('ruleset', 'equipment_catalog'):
        out[kind] = copy.deepcopy(release[kind])
    given = (out['recipe_catalog'].get('extensions') or {}).get(DISPLAY_NAMES)
    dishes, renamed, names = _dishes(recipes, given if isinstance(given, dict) else {}, problems)
    if problems:
        return None, problems
    catalog = copy.deepcopy(release['recipe_catalog'])
    catalog.update(name='player dishes', recipes=dishes, extensions={DISPLAY_NAMES: names})
    out['recipe_catalog'] = catalog
    menu = out['order_policy'].get('menu')
    if isinstance(menu, list):
        for entry in menu:
            if isinstance(entry, dict) and entry.get('recipe_ref') in renamed:
                entry['recipe_ref'] = renamed[entry['recipe_ref']]
    out['order_policy'].pop('patience_by_recipe', None)  # set again by the pacing rule
    level = out['level']
    for field, kind in (('ruleset_ref', 'ruleset'), ('equipment_catalog_ref', 'equipment_catalog'),
                        ('recipe_catalog_ref', 'recipe_catalog')):
        level[field] = {'id': out[kind]['id'], 'version': out[kind]['version']}
    level.pop('menu_order', None)  # never listed among the authored levels
    # Named by its content: two designs never share an id, with each other or with an authored level.
    named = {'level': 'version', 'map': 'revision', 'order_policy': 'version', 'recipe_catalog': 'version'}
    refs = {'map': 'map_ref', 'order_policy': 'order_policy_ref', 'recipe_catalog': 'recipe_catalog_ref'}

    def name_documents(content_id):
        for kind, field in named.items():
            out[kind].update({'id': content_id, field: 1})
        for kind, field in refs.items():
            level[field] = {'id': content_id, 'version': 1}
    name_documents('player')  # a placeholder, so the hash covers the content only
    name_documents(PLAYER_PREFIX + cc.sha256({kind: out[kind] for kind in named})[:12])
    return out, problems


def dish_work_ms(catalog, dish):
    """Chop and cook game ms a dish needs, from each component's dispensed state; None if unreachable."""
    items = catalog['items']
    total = 0
    for part in catalog['recipes'][dish]['components']:
        state = items[part['item']]['initial_state']
        for _ in range(len(catalog['transforms']) + 1):
            if state == part['state']:
                break
            step = next((t for t in catalog['transforms'] if t['item'] == part['item'] and t['from'] == state), None)
            if step is None:
                return None
            total += step['work_game_ms']
            state = step['to']
        else:
            return None
    return total


def patience_ms(work_ms):
    low, high = PATIENCE_RANGE_GAME_MS
    rounded = PATIENCE_STEP_GAME_MS * int(PATIENCE_FACTOR * work_ms / PATIENCE_STEP_GAME_MS + .5)
    return min(high, max(low, rounded))


def pacing(bundle):
    """{interval_game_ms, patience_by_recipe} for the dishes on the menu."""
    catalog = bundle['recipe_catalog']
    menu = [entry['recipe_ref'] for entry in bundle['order_policy']['menu']]
    return {'interval_game_ms': INTERVAL_GAME_MS,
            'patience_by_recipe': {dish: patience_ms(dish_work_ms(catalog, dish) or 0) for dish in menu}}


def paced(bundle, seed=None, target=0):
    """A copy with the pacing rule, ``target`` as the goal and, for a calibration run, that run's seeds."""
    out = copy.deepcopy(bundle)
    policy = out['order_policy']
    policy.update(pacing(out), mode='fixed_interval_seeded', first_spawn_game_ms=0)
    policy['patience_default_game_ms'] = max(policy['patience_by_recipe'].values())
    seed = SEEDS[0] if seed is None else seed
    out['level']['seeds'] = {'orders': seed, 'spawn': seed % 2}
    out['level']['goal'] = {'type': 'minimum_money', 'min_money': target}
    return out


def _run(job):
    """One calibration seed: every pairing's money and dishes, and the solo chef's."""
    bundle, seed = job
    import reference_policy
    from spatial_kitchen import SpatialKitchen
    frozen = cc.freeze_bundle(paced(bundle, seed))
    pairings = {}
    for pair, swap in PAIRINGS:
        policy, roles = {'classic': (reference_policy.choose, ('assembler', 'cook')),
                         'zoned': (reference_policy.choose_zoned, ('maker', 'runner'))}[pair]
        roles = roles[::-1] if swap else roles
        k = SpatialKitchen(copy.deepcopy(frozen))
        drive(k, (('human', roles[0]), ('jeff', roles[1])), policy, {'human': 10, 'jeff': 10})
        pairings[pair + (' swapped' if swap else '')] = (k.money, k.served)
    best = max(pairings, key=lambda name: (pairings[name], name))
    solo = SpatialKitchen(copy.deepcopy(frozen))
    drive(solo, (('human', 'solo'),), lambda k, who, role: reference_policy.choose_solo(k, who), {'human': 10, 'jeff': 10})
    return {'seed': seed, 'pairings': {name: money for name, (money, _) in pairings.items()}, 'pair': best,
            'money': pairings[best][0], 'served': pairings[best][1], 'solo': solo.money, 'solo_served': solo.served}


def calibrate(bundle, seeds=SEEDS, workers=1, registry=None):
    """Check a player's level, then measure it: the pacing, target and whether it can be played."""
    level, problems = normalize(bundle, registry)
    if level is None:
        return {'playable': False, 'diagnostics': problems}
    draft, diagnostics = cc.resolve_config(paced(level), registry)
    if draft is None:
        return {'playable': False, 'diagnostics': cc.errors(diagnostics)}
    jobs = [(level, seed) for seed in seeds]
    if workers == 1:
        runs = [_run(job) for job in jobs]
    else:
        with Pool(workers) as pool:
            runs = pool.map(_run, jobs)
    median = statistics.median(r['money'] for r in runs)
    target = max(0, int(median * .5) // 10 * 10)
    solo_median = statistics.median(r['solo'] for r in runs)
    return {'playable': target > 0 and statistics.median(r['served'] for r in runs) >= 1,
            'pacing': pacing(level), 'target': target, 'seeds': list(seeds), 'runs': runs,
            'pair_median': median, 'solo_median': solo_median,
            'solo_reaches_target': target > 0 and solo_median >= target,
            'diagnostics': [d for d in diagnostics if d['severity'] != 'ERROR']}


def finalize(bundle, report, registry=None):
    """The frozen configuration a calibrated, playable player level runs."""
    if not report.get('playable'):
        raise ValueError('this level cannot be played')
    level, problems = normalize(bundle, registry)
    if level is None:
        raise ValueError(problems)
    return cc.freeze_bundle(paced(level, target=report['target']), registry)
