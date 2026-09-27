"""Configuration contract: validate -> resolve -> freeze.

    validate_config(bundle) -> diagnostics
    resolve_config(bundle, registry) -> (resolved_draft | None, diagnostics)
    freeze_config(resolved_draft) -> (resolved_config, config_hash)

The resolver only follows references, fills documented defaults and converts
units; it never tunes difficulty or repairs author choices. Editors, the
command line, local and hosted rounds share these entry points. The engine is
the authority for runtime rules; this module describes and checks the
conditions it will run under.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
import random

from map_definition import MAP_ROOT, upgrade_map, validate_map
import schema_check

ROOT = Path(__file__).resolve().parent
CONTENT_DIRS = {
    'ruleset': ROOT / 'rulesets',
    'equipment_catalog': ROOT / 'content' / 'equipment',
    'recipe_catalog': ROOT / 'content' / 'recipes',
    'order_policy': ROOT / 'content' / 'orders',
    'level': ROOT / 'content' / 'levels',
    'map': MAP_ROOT,
}
SCHEMAS = {
    'ruleset': 'ruleset.schema.json', 'equipment_catalog': 'equipment.schema.json',
    'recipe_catalog': 'recipe.schema.json', 'order_policy': 'order.schema.json',
    'level': 'level.schema.json', 'map': 'map.schema.json',
}
REF_FIELDS = {'ruleset': 'ruleset_ref', 'map': 'map_ref', 'equipment_catalog': 'equipment_catalog_ref',
              'recipe_catalog': 'recipe_catalog_ref', 'order_policy': 'order_policy_ref'}
# Operations whose capability must exist on some equipment instance.
OPERATION_CAPABILITY = {'chop': 'chop', 'heat': 'heat'}
INVENTORY_HOSTS = {'plate': ('counter', 'sink', 'plate_return'), 'pot': ('stove', 'counter'),
                   'extinguisher': ('tool_rack',)}
ORDER_ALGORITHMS = {'legacy_finite': 'legacy_finite/python-random-shuffle-v1',
                    'fixed_interval_seeded': 'fixed_interval_seeded/weighted-cumulative-v1',
                    'fixed_table': 'fixed_table/stable-sort-v1'}
SEED_LIMIT = 2 ** 31


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha256(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def diag(code, severity, field_path, message, evidence=None):
    row = {'code': code, 'severity': severity, 'field_path': field_path, 'message': message}
    if evidence is not None:
        row['evidence'] = evidence
    return row


def errors(diagnostics):
    return [d for d in diagnostics if d['severity'] == 'ERROR']


def document_version(kind, document):
    return document.get('revision') if kind == 'map' else document.get('version')


class Registry:
    """Local content lookup by (kind, id, version). Nothing is fetched remotely."""

    def __init__(self, dirs=None, documents=()):
        self.dirs = dict(CONTENT_DIRS if dirs is None else dirs)
        self.memory = {}
        for kind, document in documents:
            self.add(kind, document)

    def add(self, kind, document):
        self.memory[(kind, document.get('id'), document_version(kind, document))] = copy.deepcopy(document)

    def get(self, kind, ref):
        key = (kind, ref.get('id'), ref.get('version'))
        if key in self.memory:
            return copy.deepcopy(self.memory[key])
        folder = self.dirs.get(kind)
        name = ref.get('id')
        if folder is None or not isinstance(name, str) or '/' in name or '\\' in name or name.startswith('.'):
            return None
        path = folder / f'{name}.json'
        if not path.is_file():
            return None
        document = json.loads(path.read_text(encoding='utf-8'))
        if document_version(kind, document) != ref.get('version') or document.get('id') != name:
            return {'__version_mismatch__': document_version(kind, document)}
        return document

    def levels(self):
        found = []
        for path in sorted(self.dirs['level'].glob('*.json')):
            document = json.loads(path.read_text(encoding='utf-8'))
            found.append(document)
        for (kind, _, _), document in self.memory.items():
            if kind == 'level':
                found.append(copy.deepcopy(document))
        return sorted(found, key=lambda d: (d.get('menu_order', 10 ** 6), d.get('id', ''), d.get('version', 0)))

    def level(self, level_id):
        matches = [d for d in self.levels() if d.get('id') == level_id]
        if not matches:
            raise ValueError(f'unknown level {level_id!r}')
        return max(matches, key=lambda d: d.get('version', 0))


def validate_config(bundle):
    """Format checks for a bundle: {schema_version, level, [embedded documents...]}."""
    out = []
    if not isinstance(bundle, dict):
        return [diag('BUNDLE_INVALID', 'ERROR', '/', 'bundle must be an object')]
    for path, message in schema_check.validate(bundle, 'configuration.schema.json'):
        out.append(diag('SCHEMA_INVALID', 'ERROR', path, message))
    return out


def _schema(kind, document, prefix):
    return [diag('SCHEMA_INVALID', 'ERROR', prefix + path, message)
            for path, message in schema_check.validate(document, SCHEMAS[kind])]


def _fetch(bundle, registry, kind, ref, prefix, out):
    embedded = bundle.get(kind)
    if embedded is not None:
        if embedded.get('id') == ref.get('id') and document_version(kind, embedded) == ref.get('version'):
            return copy.deepcopy(embedded)
        out.append(diag('REF_MISMATCH', 'ERROR', f'/{kind}', f'embedded {kind} is not the referenced {ref}'))
        return None
    document = registry.get(kind, ref)
    if document is None:
        out.append(diag('REF_MISSING', 'ERROR', prefix, f'{kind} {ref.get("id")!r} version {ref.get("version")} not found'))
        return None
    if '__version_mismatch__' in document:
        out.append(diag('REF_VERSION_MISMATCH', 'ERROR', prefix,
                        f'{kind} {ref.get("id")!r} is version {document["__version_mismatch__"]}, reference asks {ref.get("version")}'))
        return None
    return document


def _producible(recipe_catalog, map_types, item, state, have_pot):
    """Whether a component can be produced from a map source through transforms."""
    items = recipe_catalog['items']
    if item not in items or 'ingredient_source' not in map_types.get('__sources__', {}).get(item, ()):
        return False, 'no ingredient source for this item on the map'
    reachable, frontier = {items[item]['initial_state']}, [items[item]['initial_state']]
    steps = [t for t in recipe_catalog['transforms'] if t['item'] == item]
    while frontier:
        current = frontier.pop()
        for t in steps:
            if t['from'] != current or t['to'] in reachable:
                continue
            capability = OPERATION_CAPABILITY[t['operation']]
            if capability not in map_types['__capabilities__']:
                continue
            if t.get('container') == 'pot' and not have_pot:
                continue
            reachable.add(t['to'])
            frontier.append(t['to'])
    if state in reachable:
        return True, None
    return False, f'state {state!r} is not reachable from {items[item]["initial_state"]!r} with equipment on this map'


def _order_count(policy, round_limit):
    mode = policy['mode']
    if mode == 'legacy_finite':
        return sum(entry['count'] for entry in policy['sequence'])
    if mode == 'fixed_table':
        return len(policy['arrivals'])
    t0, stop, interval = policy['first_spawn_game_ms'], policy['stop_spawn_game_ms'], policy['interval_game_ms']
    return max(0, math.ceil((stop - t0) / interval))


def resolve_config(bundle, registry=None):
    """Return (resolved_draft, diagnostics). The draft is None when any ERROR exists."""
    registry = registry or Registry()
    out = validate_config(bundle)
    if errors(out):
        return None, out
    level = copy.deepcopy(bundle['level'])
    docs = {'level': level}
    for kind, field in REF_FIELDS.items():
        document = _fetch(bundle, registry, kind, level[field], f'/level/{field}', out)
        if document is None:
            continue
        if kind == 'map':
            out.extend(_schema(kind, upgrade_map(document), f'/{kind}'))
            try:
                validate_map(document)
            except (ValueError, KeyError, TypeError) as exc:
                out.append(diag('MAP_INVALID', 'ERROR', '/map', str(exc)))
                continue
            document = upgrade_map(document)
        else:
            out.extend(_schema(kind, document, f'/{kind}'))
        docs[kind] = document
    if errors(out) or len(docs) != 6:
        return None, out

    ruleset, catalog, recipes = docs['ruleset'], docs['equipment_catalog'], docs['recipe_catalog']
    game_map, policy = docs['map'], docs['order_policy']
    applied = []
    limits = ruleset['limits']
    for kind, document in docs.items():
        size = len(canonical(document).encode('utf-8'))
        if size > limits['max_document_bytes']:
            out.append(diag('LIMIT_DOCUMENT_SIZE', 'ERROR', f'/{kind}', f'{size} bytes exceeds {limits["max_document_bytes"]}'))

    # Equipment catalog against engine support.
    for type_id in catalog['types']:
        if type_id not in ruleset['supported_equipment_types']:
            out.append(diag('UNSUPPORTED_EQUIPMENT_TYPE', 'ERROR', f'/equipment_catalog/types/{type_id}',
                            f'the {ruleset["id"]} ruleset has no engine semantics for {type_id!r}'))

    # Map instances against the catalog and recipe items.
    stations, sources, capabilities, counts = [], {}, set(), {}
    if len(game_map['equipment']) > limits['max_equipment']:
        out.append(diag('LIMIT_EQUIPMENT', 'ERROR', '/map/equipment', f'more than {limits["max_equipment"]} instances'))
    for i, e in enumerate(game_map['equipment']):
        path = f'/map/equipment/{i}'
        kind = catalog['types'].get(e['type'])
        if kind is None:
            out.append(diag('MAP_UNKNOWN_EQUIPMENT_TYPE', 'ERROR', path + '/type', f'{e["type"]!r} is not in the equipment catalog'))
            continue
        counts[e['type']] = counts.get(e['type'], 0) + 1
        capabilities.update(kind['capabilities'])
        params = e.get('params', {})
        for name in set(params) - set(kind.get('params', {})):
            out.append(diag('MAP_UNKNOWN_PARAM', 'ERROR', f'{path}/params/{name}', f'{e["type"]} has no parameter {name!r}'))
        for name, param_type in kind.get('params', {}).items():
            if name not in params:
                out.append(diag('MAP_MISSING_PARAM', 'ERROR', f'{path}/params/{name}', f'{e["type"]} requires {name!r}'))
            elif param_type == 'item_ref':
                if params[name] not in recipes['items']:
                    out.append(diag('MAP_UNKNOWN_ITEM', 'ERROR', f'{path}/params/{name}', f'{params[name]!r} is not a recipe item'))
                else:
                    sources.setdefault(params[name], set()).add(e['type'])
        record = {'id': e['id'], 'type': e['type'], 'name': e['name'], 'area': e['area']}
        if params:
            record['params'] = dict(params)
        stations.append(record)
    for type_id, needed in (('serving_window', 'at least one'), ('sink', 'exactly one'), ('plate_return', 'exactly one'),
                            ('tool_rack', 'exactly one')):
        n = counts.get(type_id, 0)
        if n == 0 or (needed == 'exactly one' and n != 1):
            out.append(diag('UNSUPPORTED_EQUIPMENT_COUNT', 'ERROR', '/map/equipment',
                            f'this engine version needs {needed} {type_id} (found {n})'))

    # Recipe catalog consistency.
    for i, t in enumerate(recipes['transforms']):
        item = recipes['items'].get(t['item'])
        if item is None:
            out.append(diag('RECIPE_UNKNOWN_ITEM', 'ERROR', f'/recipe_catalog/transforms/{i}/item', f'{t["item"]!r} is not defined'))
        elif t['from'] not in item['states'] or t['to'] not in item['states']:
            out.append(diag('RECIPE_STATE_INVALID', 'ERROR', f'/recipe_catalog/transforms/{i}', 'transform uses a state the item does not have'))
    for key, item in recipes['items'].items():
        if item['initial_state'] not in item['states']:
            out.append(diag('RECIPE_STATE_INVALID', 'ERROR', f'/recipe_catalog/items/{key}/initial_state', 'initial state is not listed'))

    # Initial inventory: engine conservation rules need contiguous IDs and one extinguisher.
    inventory = level['initial_inventory']
    by_id = {e['id']: e for e in game_map['equipment']}
    occupied, ids = {}, set()
    if len(inventory) > limits['max_inventory']:
        out.append(diag('LIMIT_INVENTORY', 'ERROR', '/level/initial_inventory', f'more than {limits["max_inventory"]} objects'))
    for i, entry in enumerate(inventory):
        path = f'/level/initial_inventory/{i}'
        if entry['id'] in ids:
            out.append(diag('INVENTORY_DUPLICATE_ID', 'ERROR', path + '/id', f'{entry["id"]} appears twice'))
        ids.add(entry['id'])
        station = by_id.get(entry['at'])
        if station is None:
            out.append(diag('INVENTORY_UNKNOWN_STATION', 'ERROR', path + '/at', f'{entry["at"]!r} is not on the map'))
            continue
        if station['type'] not in INVENTORY_HOSTS[entry['object']]:
            out.append(diag('INVENTORY_INCOMPATIBLE', 'ERROR', path + '/at', f'{entry["object"]} cannot start on a {station["type"]}'))
        if entry['at'] in occupied:
            out.append(diag('INVENTORY_SLOT_CONFLICT', 'ERROR', path + '/at', f'{entry["at"]} already holds {occupied[entry["at"]]}'))
        occupied[entry['at']] = entry['id']
        if entry['object'] == 'plate' and 'state' not in entry:
            entry['state'] = 'clean'
            applied.append(f'/level/initial_inventory/{i}/state=clean')
    for obj, prefix in (('plate', 'D'), ('pot', 'P'), ('extinguisher', 'E')):
        found = sorted(e['id'] for e in inventory if e['object'] == obj)
        if found != [f'{prefix}{n}' for n in range(1, len(found) + 1)] or any(not e['id'].startswith(prefix) for e in inventory if e['object'] == obj):
            out.append(diag('INVENTORY_ID_SEQUENCE', 'ERROR', '/level/initial_inventory', f'{obj} IDs must be {prefix}1..{prefix}n', found))
    if sum(e['object'] == 'extinguisher' for e in inventory) != 1:
        out.append(diag('INVENTORY_EXTINGUISHER', 'ERROR', '/level/initial_inventory', 'exactly one extinguisher is supported'))
    plates = sum(e['object'] == 'plate' for e in inventory)
    pots = sum(e['object'] == 'pot' for e in inventory)
    if plates == 0:
        out.append(diag('INVENTORY_NO_PLATES', 'ERROR', '/level/initial_inventory', 'recipes are served on plates; no plate exists'))

    # Production chains for ordered recipes.
    map_types = {'__sources__': sources, '__capabilities__': capabilities}
    ordered = []
    if policy['mode'] == 'legacy_finite':
        ordered = [e['recipe_ref'] for e in policy.get('sequence', [])]
    elif policy['mode'] == 'fixed_interval_seeded':
        ordered = [e['recipe_ref'] for e in policy.get('menu', [])]
    else:
        ordered = [e['recipe_ref'] for e in policy.get('arrivals', [])]
    for recipe_id in dict.fromkeys(ordered):
        recipe = recipes['recipes'].get(recipe_id)
        if recipe is None:
            out.append(diag('ORDER_UNKNOWN_RECIPE', 'ERROR', '/order_policy', f'{recipe_id!r} is not in the recipe catalog'))
            continue
        for j, component in enumerate(recipe['components']):
            ok, why = _producible(recipes, map_types, component['item'], component['state'], pots > 0)
            if not ok:
                out.append(diag('NO_PRODUCTION_CHAIN', 'ERROR', f'/recipe_catalog/recipes/{recipe_id}/components/{j}',
                                f'{recipe_id} needs {component["item"]} {component["state"]}: {why}',
                                {'map': game_map['id'], 'capabilities': sorted(capabilities)}))
    for recipe_id in policy.get('patience_by_recipe', {}):
        if recipe_id not in recipes['recipes']:
            out.append(diag('ORDER_UNKNOWN_RECIPE', 'ERROR', f'/order_policy/patience_by_recipe/{recipe_id}', 'unknown recipe'))

    # Order timing by mode.
    D = level['round_limit_game_ms']
    if D > limits['max_round_game_ms']:
        out.append(diag('LIMIT_ROUND', 'ERROR', '/level/round_limit_game_ms', f'exceeds {limits["max_round_game_ms"]}'))
    required = {'legacy_finite': ('interval_game_ms', 'sequence'),
                'fixed_interval_seeded': ('interval_game_ms', 'stop_spawn_game_ms', 'menu'),
                'fixed_table': ('arrivals',)}[policy['mode']]
    missing = [f for f in required if f not in policy]
    for f in missing:
        out.append(diag('ORDER_MODE_FIELD', 'ERROR', f'/order_policy/{f}', f'{policy["mode"]} requires {f}'))
    if not missing:
        if 'first_spawn_game_ms' not in policy and policy['mode'] != 'fixed_table':
            policy['first_spawn_game_ms'] = 0
            applied.append('/order_policy/first_spawn_game_ms=0')
        if 'patience_by_recipe' not in policy:
            policy['patience_by_recipe'] = {}
            applied.append('/order_policy/patience_by_recipe={}')
        if policy['mode'] == 'legacy_finite' and 'shuffle' not in policy:
            policy['shuffle'] = False
            applied.append('/order_policy/shuffle=false')
        if policy['mode'] == 'fixed_interval_seeded':
            t0, C = policy['first_spawn_game_ms'], policy['stop_spawn_game_ms']
            if not 0 <= t0 < C <= D:
                out.append(diag('ORDER_TIMING', 'ERROR', '/order_policy', 'requires 0 <= first_spawn < stop_spawn <= round_limit',
                                {'first_spawn_game_ms': t0, 'stop_spawn_game_ms': C, 'round_limit_game_ms': D}))
        elif policy['mode'] == 'fixed_table':
            late = [a['arrival_game_ms'] for a in policy['arrivals'] if a['arrival_game_ms'] >= D]
            if late:
                out.append(diag('ORDER_TIMING', 'ERROR', '/order_policy/arrivals', 'arrivals at or after round end', late))
        elif policy['first_spawn_game_ms'] >= D:
            out.append(diag('ORDER_TIMING', 'ERROR', '/order_policy/first_spawn_game_ms', 'first order after round end'))
        count = _order_count(policy, D)
        if count > limits['max_orders']:
            out.append(diag('LIMIT_ORDERS', 'ERROR', '/order_policy', f'{count} orders exceeds {limits["max_orders"]}'))
        goal = level['goal']
        target = goal['min_served'] if goal['type'] == 'legacy_all_gates' else goal['min_deliveries']
        if target > count:
            out.append(diag('GOAL_EXCEEDS_ORDERS', 'ERROR', '/level/goal', f'goal needs {target} deliveries; the plan offers {count}',
                            {'orders_offered': count, 'goal': target}))
        for recipe_id, patience in [(None, policy['patience_default_game_ms'])] + list(policy['patience_by_recipe'].items()):
            if patience < 10000:
                out.append(diag('PATIENCE_SHORT', 'WARNING', '/order_policy', f'patience {patience} ms is very short', recipe_id))

    # Actors, spawns, clock and goal/end compatibility.
    actor_ids = [a['actor_id'] for a in level['actors']]
    if sorted(actor_ids) != ['human', 'jeff']:
        out.append(diag('ACTORS_UNSUPPORTED', 'ERROR', '/level/actors', 'this engine version runs exactly human and jeff'))
    clock = level['clock']
    if clock['game_per_wall_default'] not in clock['game_per_wall_options']:
        out.append(diag('CLOCK_DEFAULT', 'ERROR', '/level/clock', 'default game speed must be one of the options'))
    width, height = game_map['size']
    blocked = {tuple(w) for w in game_map['walls']} | {tuple(c) for e in game_map['equipment'] for c in e.get('cells', [e['cell']])}
    floor = [(x, y) for x in range(width) for y in range(height) if (x, y) not in blocked]
    part = level['spawns']['partition']
    axis = 0 if part['axis'] == 'x' else 1
    for j, center in enumerate(level['spawns']['centers']):
        side = center[axis] < part['split']
        if not any((c[axis] < part['split']) == side for c in floor):
            out.append(diag('SPAWN_NO_FLOOR', 'ERROR', f'/level/spawns/centers/{j}', 'no walkable floor on this side of the partition'))
    semantics = ruleset['engine_semantics']
    goal_type, end_type = level['goal']['type'], level['end_policy']['type']
    if semantics == 'legacy-2026-09' and (goal_type, end_type, policy['mode']) != ('legacy_all_gates', 'legacy_immediate', 'legacy_finite'):
        out.append(diag('RULESET_MISMATCH', 'ERROR', '/level', 'legacy semantics support only legacy_all_gates + legacy_immediate + legacy_finite'))
    if semantics != 'legacy-2026-09' and (goal_type, end_type) != ('minimum_deliveries', 'fixed_round'):
        out.append(diag('RULESET_MISMATCH', 'ERROR', '/level', 'continuous semantics require minimum_deliveries + fixed_round'))

    if errors(out):
        return None, out
    draft = {
        'schema_version': 1, 'kind': 'resolved_configuration', 'status': 'draft',
        'level': level,
        'sources': {kind: {'id': d['id'], 'version': document_version(kind, d), 'sha256': sha256(d)} for kind, d in docs.items()},
        'ruleset': ruleset, 'map': game_map, 'equipment_catalog': catalog, 'recipe_catalog': recipes,
        'order_policy': policy, 'stations': stations, 'applied_defaults': applied, 'overrides': {},
    }
    return draft, out


def order_plan(policy, seed, round_limit_game_ms, recipe_ids):
    """Deterministic order plan. The algorithm name is recorded with the plan."""
    mode = policy['mode']
    patience = lambda recipe: policy['patience_by_recipe'].get(recipe, policy['patience_default_game_ms'])
    rows = []
    if mode == 'legacy_finite':
        menu = [e['recipe_ref'] for e in policy['sequence'] for _ in range(e['count'])]
        if policy['shuffle']:
            random.Random(seed).shuffle(menu)
        for i, recipe in enumerate(menu):
            arrival = policy['first_spawn_game_ms'] + i * policy['interval_game_ms']
            # Legacy deadlines are not clipped to the round end.
            rows.append((recipe, arrival, patience(recipe), arrival + patience(recipe)))
    elif mode == 'fixed_interval_seeded':
        rng = random.Random(seed)
        menu = sorted(policy['menu'], key=lambda e: e['recipe_ref'])
        total = sum(e['weight'] for e in menu)
        arrival = policy['first_spawn_game_ms']
        while arrival < policy['stop_spawn_game_ms']:
            pick, acc = rng.random() * total, 0.
            recipe = menu[-1]['recipe_ref']
            for e in menu:
                acc += e['weight']
                if pick < acc:
                    recipe = e['recipe_ref']
                    break
            rows.append((recipe, arrival, patience(recipe), min(arrival + patience(recipe), round_limit_game_ms)))
            arrival += policy['interval_game_ms']
    else:
        table = sorted(enumerate(policy['arrivals']), key=lambda p: (p[1]['arrival_game_ms'], p[0]))
        for _, a in table:
            p = a.get('patience_game_ms', patience(a['recipe_ref']))
            rows.append((a['recipe_ref'], a['arrival_game_ms'], p, min(a['arrival_game_ms'] + p, round_limit_game_ms)))
    return {'algorithm': ORDER_ALGORITHMS[mode],
            'orders': [{'order_id': f'O{i + 1}', 'recipe_ref': r, 'arrival_game_ms': a, 'deadline_game_ms': d,
                        'patience_game_ms': p} for i, (r, a, p, d) in enumerate(rows)]}


def freeze_config(draft, rng=None):
    """Fix seeds and the order plan, then hash. Returns (resolved, config_hash)."""
    if draft.get('status') != 'draft':
        raise ValueError('only a resolved draft can be frozen')
    resolved = copy.deepcopy(draft)
    rng = rng or random.SystemRandom()
    configured = resolved['level']['seeds']
    seeds, drawn = {}, 0
    for name in ('orders', 'spawn'):
        value = configured[name]
        if value is None:
            value = rng.randrange(SEED_LIMIT)
            drawn += 1
        seeds[name] = value
    seeds['source'] = 'configured' if drawn == 0 else ('drawn_at_freeze' if drawn == 2 else 'mixed')
    resolved['seeds'] = seeds
    resolved['order_plan'] = order_plan(resolved['order_policy'], seeds['orders'], resolved['level']['round_limit_game_ms'],
                                        list(resolved['recipe_catalog']['recipes']))
    resolved['status'] = 'frozen'
    resolved.pop('config_hash', None)
    resolved['config_hash'] = 'sha256:' + sha256(resolved)
    return resolved, resolved['config_hash']


def verify_frozen(resolved):
    """Return diagnostics for a frozen configuration (schema and hash integrity)."""
    out = [diag('SCHEMA_INVALID', 'ERROR', path, message) for path, message in schema_check.validate(resolved, 'resolved.schema.json')]
    body = {k: v for k, v in resolved.items() if k != 'config_hash'}
    if resolved.get('config_hash') != 'sha256:' + sha256(body):
        out.append(diag('CONFIG_HASH_MISMATCH', 'ERROR', '/config_hash', 'content does not match its hash'))
    return out


def level_bundle(level_id, registry=None):
    registry = registry or Registry()
    return {'schema_version': 1, 'level': registry.level(level_id)}


def load_level(level_id, registry=None, seeds=None, rng=None):
    """Resolve and freeze an authored level; raise ValueError with diagnostics on error."""
    registry = registry or Registry()
    bundle = level_bundle(level_id, registry)
    if seeds:
        bundle['level']['seeds'].update({k: v for k, v in seeds.items() if v is not None})
    draft, diagnostics = resolve_config(bundle, registry)
    if draft is None:
        raise ValueError(json.dumps(errors(diagnostics), ensure_ascii=False))
    return freeze_config(draft, rng)[0]


def legacy_flat_config(resolved):
    """Parameters of the accepted flat engine config, derived from a resolved configuration."""
    level, ruleset, recipes = resolved['level'], resolved['ruleset'], resolved['recipe_catalog']
    policy, stations = resolved['order_policy'], resolved['stations']
    catalog = resolved['equipment_catalog']['types']
    transform = {t['id']: t for t in recipes['transforms']}
    rate = lambda kind, capability: catalog[kind].get('work_rates', {}).get(capability, 1.0)
    cook = transform['cook_beef']
    goal = level['goal']
    inventory = level['initial_inventory']
    s = lambda ms: ms / 1000
    return {
        'level': level.get('menu_order'),
        'boards': sum(st['type'] == 'board' for st in stations),
        'pots': sum(st['type'] == 'stove' for st in stations),
        'pot_count': sum(e['object'] == 'pot' for e in inventory),
        'plate_count': sum(e['object'] == 'plate' for e in inventory),
        'round_seconds': s(level['round_limit_game_ms']),
        'order_count': _order_count(policy, level['round_limit_game_ms']),
        'order_interval': s(policy['interval_game_ms']),
        'order_patience': s(policy['patience_default_game_ms']),
        'target_served': goal['min_served'], 'target_money': goal['min_money'], 'max_bad_reviews': goal['max_bad_reviews'],
        'time_bonus_per_second': level['scoring']['time_bonus_per_second'],
        'chop_seconds': s(transform['chop_beef']['work_game_ms']) / rate('board', 'chop'),
        'cook_seconds': s(cook['work_game_ms']) / rate('stove', 'heat'),
        'burn_after_ready': s(cook['overcook']['after_done_game_ms']),
        'fire_after_burn': s(cook['overcook']['fire_after_overcook_game_ms']),
        'same_area_walk': s(ruleset['abstract_travel']['same_area_game_ms']),
        'cross_area_walk': s(ruleset['abstract_travel']['cross_area_game_ms']),
        'handling_seconds': s(ruleset['operations']['handling_game_ms']),
        'dining_seconds': s(ruleset['tableware']['dining_game_ms']),
        'wash_seconds': s(recipes['containers']['plate']['wash_work_game_ms']) / rate('sink', 'wash'),
        'fire_spread_seconds': s(ruleset['fire']['spread_interval_game_ms']),
        'fire_loss_threshold': ruleset['fire']['loss_threshold'],
        'order_seed': resolved['seeds']['orders'],
        'spawn_seed': resolved['seeds']['spawn'],
    }


def main(argv=None):
    """``python config_contract.py level-2`` or ``python config_contract.py path/to/bundle.json``."""
    import sys
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print('usage: python config_contract.py <level-id | bundle.json>')
        return 2
    target = args[0]
    if target.endswith('.json'):
        bundle = json.loads(Path(target).read_text(encoding='utf-8'))
    else:
        bundle = level_bundle(target)
    draft, diagnostics = resolve_config(bundle)
    result = {'diagnostics': diagnostics, 'structurally_valid': draft is not None}
    if draft is not None:
        frozen, digest = freeze_config(draft)
        result.update(config_hash=digest, seeds=frozen['seeds'], orders=len(frozen['order_plan']['orders']))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if draft is not None else 1


if __name__ == '__main__':
    raise SystemExit(main())
