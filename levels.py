"""Authored level lookup. Level parameters live in ``content/levels`` and friends.

``level_config`` keeps the historical flat entry point used by the local server:
it selects a level and leaves every game parameter to the level's documents.
"""
from functools import lru_cache

import config_contract


@lru_cache(maxsize=1)
def _listed():
    return tuple({'id': d['id'], 'name': d['name'], 'menu_order': d.get('menu_order')}
            for d in config_contract.Registry().levels() if d.get('menu_order') is not None)


def available_levels():
    """Listed levels in menu order: [{id, name, menu_order}]."""
    return [dict(entry) for entry in _listed()]


def level_id(level):
    """Accept a legacy level number or a level id; return the level id."""
    if type(level) is int:
        level = f'level-{level}'
    if not isinstance(level, str) or level not in {entry['id'] for entry in available_levels()}:
        raise ValueError('Unknown level')
    return level


def level_config(base, level):
    """Flat config selecting ``level``; seeds are drawn when the round's configuration is frozen."""
    c = {k: v for k, v in dict(base).items() if k not in ('order_seed', 'spawn_seed')}
    for key in ('order_seed', 'spawn_seed'):
        if base.get(key) is not None:
            c[key] = base[key]
    c['level_id'] = level_id(level)
    c['level'] = next(entry['menu_order'] for entry in available_levels() if entry['id'] == c['level_id'])
    return c
