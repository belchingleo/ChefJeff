"""Runtime rule tables derived from one frozen resolved configuration.

The kitchen engine reads every duration, rate, recipe and penalty from here, so
new content changes data rather than engine branches. ``runtime_config`` also
accepts the historical flat config (``config.json`` plus overrides) and turns
it into an explicit, frozen configuration whose ``overrides`` record every
changed value.
"""
from __future__ import annotations
import copy
import json
from functools import lru_cache
import math
from pathlib import Path

import config_contract as cc

ROOT = Path(__file__).resolve().parent
LEGACY_BASE = json.loads((ROOT / 'config.json').read_text())
# Flat keys that describe the game; all other flat keys (ai_*, model, ...) are agent/session settings.
GAME_KEYS = {'level', 'boards', 'pots', 'pot_count', 'plate_count', 'round_seconds', 'order_count', 'order_interval',
             'order_patience', 'target_served', 'target_money', 'max_bad_reviews', 'time_bonus_per_second',
             'chop_seconds', 'cook_seconds', 'burn_after_ready', 'fire_after_burn', 'same_area_walk', 'cross_area_walk',
             'handling_seconds', 'dining_seconds', 'wash_seconds', 'fire_spread_seconds', 'fire_loss_threshold',
             'order_seed', 'spawn_seed', 'level_id'}
DERIVED_KEYS = {'boards', 'pots'}  # counted from the map; kept in the flat view for compatibility
PLATE_COUNTERS = ('plates', 'counter2', 'counter3')


def _ms(seconds):
    value = seconds * 1000
    if not math.isfinite(value) or value <= 0:
        raise ValueError('durations must be positive and finite')
    return int(round(value))


def _apply_flat_overrides(docs, overrides):
    """Write explicit flat overrides into the referenced documents (copies)."""
    level, policy, recipes, ruleset = docs['level'], docs['order_policy'], docs['recipe_catalog'], docs['ruleset']
    for key, value in overrides.items():
        if key == 'round_seconds':
            level['round_limit_game_ms'] = _ms(value)
        elif key == 'order_count':
            if len(policy.get('sequence', [])) != 1:
                raise ValueError('order_count can only override a single-recipe legacy sequence')
            policy['sequence'][0]['count'] = int(value)
        elif key == 'order_interval':
            policy['interval_game_ms'] = _ms(value)
        elif key == 'order_patience':
            policy['patience_default_game_ms'] = _ms(value)
        elif key in ('target_served', 'target_money', 'max_bad_reviews'):
            if level['goal']['type'] != 'legacy_all_gates' and key != 'target_money':
                raise ValueError(f'{key} does not apply to a {level["goal"]["type"]} goal')
            level['goal'][{'target_served': 'min_served', 'target_money': 'min_money',
                           'max_bad_reviews': 'max_bad_reviews'}[key]] = value
        elif key == 'time_bonus_per_second':
            level['scoring']['time_bonus_per_second'] = value
        elif key == 'chop_seconds':
            for t in recipes['transforms']:
                if t['operation'] == 'chop':
                    t['work_game_ms'] = _ms(value)
        elif key in ('cook_seconds', 'burn_after_ready', 'fire_after_burn'):
            for t in recipes['transforms']:
                if t['operation'] == 'heat':
                    if key == 'cook_seconds':
                        t['work_game_ms'] = _ms(value)
                    else:
                        t['overcook']['after_done_game_ms' if key == 'burn_after_ready' else 'fire_after_overcook_game_ms'] = _ms(value)
        elif key == 'wash_seconds':
            recipes['containers']['plate']['wash_work_game_ms'] = _ms(value)
        elif key == 'handling_seconds':
            ruleset['operations']['handling_game_ms'] = _ms(value)
        elif key == 'dining_seconds':
            ruleset['tableware']['dining_game_ms'] = _ms(value)
        elif key == 'fire_spread_seconds':
            ruleset['fire']['spread_interval_game_ms'] = _ms(value)
        elif key == 'fire_loss_threshold':
            ruleset['fire']['loss_threshold'] = int(value)
        elif key in ('same_area_walk', 'cross_area_walk'):
            ruleset['abstract_travel']['same_area_game_ms' if key == 'same_area_walk' else 'cross_area_game_ms'] = _ms(value)
        elif key == 'plate_count':
            n = int(value)
            if not 1 <= n <= len(PLATE_COUNTERS):
                raise ValueError('plate_count override supports 1 to 3 plates on the first counters')
            kept = [e for e in level['initial_inventory'] if e['object'] != 'plate']
            level['initial_inventory'] = kept + [{'object': 'plate', 'id': f'D{i + 1}', 'state': 'clean', 'at': PLATE_COUNTERS[i]}
                                                 for i in range(n)]
        elif key == 'pot_count':
            if int(value) != sum(e['object'] == 'pot' for e in level['initial_inventory']):
                raise ValueError('pot_count is defined by the level inventory')
        elif key in ('order_seed', 'spawn_seed'):
            level['seeds']['orders' if key == 'order_seed' else 'spawn'] = None if value is None else int(value)
        else:
            raise ValueError(f'unsupported override {key}')
    for kind in ('ruleset', 'recipe_catalog', 'order_policy'):
        docs[kind]['version'] = docs[kind]['version']  # versions unchanged; overrides are recorded separately


@lru_cache(maxsize=128)
def _frozen_from_flat(level_id, overrides_json):
    overrides = json.loads(overrides_json)
    registry = cc.Registry()
    level = copy.deepcopy(registry.level(level_id))
    docs = {'level': level}
    for kind, field in cc.REF_FIELDS.items():
        docs[kind] = registry.get(kind, level[field])
    seeds = {k: overrides.pop(k) for k in ('order_seed', 'spawn_seed') if k in overrides}
    _apply_flat_overrides(docs, {**overrides, **seeds})
    bundle = {'schema_version': 1, 'level': docs['level'], **{kind: docs[kind] for kind in cc.REF_FIELDS}}
    draft, diagnostics = cc.resolve_config(bundle, registry)
    if draft is None:
        raise ValueError(json.dumps(cc.errors(diagnostics), ensure_ascii=False))
    draft['overrides'] = overrides
    return draft


def runtime_config(config=None, rng=None):
    """Return (resolved, flat) for a resolved configuration or a historical flat config.

    Flat game keys override the level only when they differ from both the
    level's own value and ``config.json``'s legacy value, so a base config
    merged into a level does not overwrite that level's authored parameters.
    A flat config without ``level_id`` is the historical format and selects the
    accepted legacy level (``legacy-level-N``); servers select listed levels by id.
    """
    if config is not None and config.get('kind') == 'resolved_configuration':
        if config.get('status') != 'frozen':
            raise ValueError('the engine runs only frozen configurations')
        resolved = config
        flat = dict(LEGACY_BASE)
        flat.update(cc.legacy_flat_config(resolved))
        flat['level_id'] = resolved['level']['id']
        return resolved, flat
    source = dict(LEGACY_BASE if config is None else config)
    level_id = source.get('level_id') or f"legacy-level-{source.get('level', 1)}"
    registry = cc.Registry()
    base = cc.legacy_flat_config({**_frozen_from_flat(level_id, '{}'), 'seeds': {'orders': None, 'spawn': None}})
    overrides = {}
    for key, value in source.items():
        if key not in GAME_KEYS or key in DERIVED_KEYS | {'level', 'level_id'}:
            continue
        if key in ('order_seed', 'spawn_seed'):
            if value is not None:
                overrides[key] = value
            continue
        if value != base.get(key) and value != LEGACY_BASE.get(key):
            overrides[key] = value
    draft = _frozen_from_flat(level_id, json.dumps(overrides, sort_keys=True))
    resolved, _ = cc.freeze_config(draft, rng)
    flat = {k: v for k, v in source.items() if k not in GAME_KEYS}
    for key, value in LEGACY_BASE.items():
        flat.setdefault(key, value)
    flat.update(cc.legacy_flat_config(resolved))
    flat['level_id'] = level_id
    # Seeds stay out of the flat view unless configured, so a reset draws new ones.
    for key, name in (('order_seed', 'orders'), ('spawn_seed', 'spawn')):
        if source.get(key) is None:
            flat.pop(key, None)
    return resolved, flat


class Rules:
    """Lookup tables for one frozen configuration. Values are in game seconds."""

    def __init__(self, resolved):
        self.resolved = resolved
        ruleset, recipes = resolved['ruleset'], resolved['recipe_catalog']
        self.types = resolved['equipment_catalog']['types']
        self.semantics = ruleset['engine_semantics']
        self.continuous = self.semantics == 'continuous-2026-09'
        self.tick = ruleset['tick_game_ms'] / 1000
        s = cc.seconds
        self.handling = s(ruleset['operations']['handling_game_ms'])
        self.extinguish = s(ruleset['operations']['extinguish_game_ms'])
        self.clear = s(ruleset['operations']['clear_game_ms'])
        self.dining = s(ruleset['tableware']['dining_game_ms'])
        self.return_capacity = ruleset['tableware']['return_capacity']
        self.fire_spread = s(ruleset['fire']['spread_interval_game_ms'])
        self.fire_loss = ruleset['fire']['loss_threshold']
        self.penalty = dict(ruleset['penalties'])
        self.burnt_service = [dict(t) for t in ruleset.get('burnt_service', [])]
        self.max_visible_orders = ruleset['limits']['max_visible_orders']
        self.same_area = s(ruleset['abstract_travel']['same_area_game_ms'])
        self.cross_area = s(ruleset['abstract_travel']['cross_area_game_ms'])
        move, throw = ruleset['movement'], ruleset['throw']
        self.walk_speed = move['walk_cells_per_game_s']
        self.sprint_multiplier = move['sprint_multiplier']
        self.sprint_duration = s(move['sprint_duration_game_ms'])
        self.sprint_cooldown = s(move['sprint_cooldown_game_ms'])
        self.chef_separation = move['chef_separation_cells']
        self.sprint_push = move['sprint_push_cells']
        self.sprint_food_nudge = move['sprint_food_nudge_cells']
        # Extra speed fraction while sprinting (1.4x -> 0.4), rounded to the authored precision.
        self.sprint_boost = round(self.sprint_multiplier - 1, 12)
        self.throw_enabled = throw['enabled']
        self.throw_range = throw['range_cells']
        self.throw_speed = throw['speed_cells_per_game_s']
        self.min_flight = s(throw['min_flight_game_ms'])
        self.catch_radius = throw['catch_radius_cells']

        self.items = recipes['items']
        self.item_names = {k: v['name'] for k, v in self.items.items()}
        self.recipes = recipes['recipes']
        self.recipe_names = {k: v['name'] for k, v in self.recipes.items()}
        self.recipe_parts = {k: frozenset(c['item'] for c in v['components']) for k, v in self.recipes.items()}
        self.component_labels = {c['item']: c['label'] for v in self.recipes.values() for c in v['components']}
        policy = resolved['order_policy']
        entries = policy.get('sequence') or policy.get('menu') or policy.get('arrivals') or []
        self.menu = list(dict.fromkeys(e['recipe_ref'] for e in entries))
        self.prices = {k: v['price'] for k, v in self.recipes.items()}
        self.all_parts = frozenset().union(*self.recipe_parts.values())
        # Assembly actions exist when this level serves a dish with several components.
        self.multi_component = any(len(self.recipe_parts[r]) > 1 for r in self.menu)
        self.chop = {t['item']: t for t in recipes['transforms'] if t['operation'] == 'chop'}
        self.heat = {t['item']: t for t in recipes['transforms'] if t['operation'] == 'heat'}
        self.wash_work = s(recipes['containers']['plate']['wash_work_game_ms'])

        self.station_types = {st['id']: st['type'] for st in resolved['stations']}
        self.sources = {st['id']: st['params']['item'] for st in resolved['stations'] if st['type'] == 'ingredient_source'}
        level = resolved['level']
        self.round_limit = s(level['round_limit_game_ms'])
        self.goal = level['goal']
        self.end_policy = level['end_policy']['type']
        self.time_bonus_per_second = level['scoring']['time_bonus_per_second']
        self.inventory = level['initial_inventory']
        self.plate_count = sum(e['object'] == 'plate' for e in self.inventory)
        self.pot_count = sum(e['object'] == 'pot' for e in self.inventory)

    # Equipment -----------------------------------------------------------
    def of_type(self, kind):
        return [key for key, t in self.station_types.items() if t == kind]

    def work_rate(self, station, capability):
        return self.types[self.station_types[station]].get('work_rates', {}).get(capability, 1.0)

    def shared(self, station, capability):
        kind = self.station_types.get(station)
        return self.types[kind].get('shared_work', {}).get(capability) if kind else None

    def max_workers(self, station, capability):
        rule = self.shared(station, capability)
        return rule['max_workers'] if rule else 1

    def progress_rate(self, station, capability, workers):
        """Work units per game second contributed by each of ``workers`` active chefs."""
        rule = self.shared(station, capability)
        multiplier = float(rule['rate_multiplier'].get(str(workers), 0.)) if rule else (1. if workers == 1 else 0.)
        return self.work_rate(station, capability) * multiplier / workers

    def combustible(self, station):
        kind = self.station_types.get(station)
        return bool(kind and self.types[kind]['combustible'])

    # Items and recipes ---------------------------------------------------
    def chop_work(self, item):
        t = self.chop.get(item)
        return cc.seconds(t['work_game_ms']) if t else 0

    def choppable(self, food):
        t = self.chop.get(food.ingredient)
        return bool(t and food.stage == t['from'] and not food.plate_id)

    def potable(self, food):
        """Held food that may enter an empty pot (the heat transform's input)."""
        t = self.heat.get(food.ingredient)
        return bool(t and food.stage == t['from'] and not food.plate_id)

    def heat_thresholds(self, item):
        t = self.heat[item]
        ready = cc.seconds(t['work_game_ms'])
        burn = ready + cc.seconds(t['overcook']['after_done_game_ms'])
        return ready, burn, burn + cc.seconds(t['overcook']['fire_after_overcook_game_ms'])

    def overcook(self, food, parts):
        """Seconds the worst heated component was past burning when it left the heat.

        Food burnt by a fire (before its own burn point) counts as burnt beyond every tier.
        """
        heated = [item for item in parts if item in self.heat]
        if food.stage != 'burnt' or not heated:
            return 0.
        burn = min(self.heat_thresholds(item)[1] for item in heated)
        return food.heated - burn if food.heated >= burn - 1e-8 else float('inf')

    def burnt_tier(self, overcook):
        for tier in self.burnt_service:
            limit = tier['max_overcook_game_ms']
            if limit is None or overcook <= limit / 1000 + 1e-8:
                return tier
        return None

    def platable(self, item, stage):
        return item in self.items and stage in self.items[item]['platable_states']

    def throwable(self, food):
        return bool(food and food.ingredient in self.items and food.stage in self.items[food.ingredient]['throwable_states']
                    and not food.plate_id)

    def dish(self, parts):
        parts = frozenset(parts)
        for recipe, needed in self.recipe_parts.items():
            if parts == needed:
                return recipe
        return None

    def missing(self, parts):
        """Components still absent for the largest menu dish containing ``parts``."""
        parts = frozenset(parts)
        targets = [self.recipe_parts[r] for r in self.menu if parts <= self.recipe_parts[r]]
        return sorted(max(targets, key=len) - parts) if targets else []
