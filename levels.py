"""Authored level lookup. Level parameters live in ``content/levels`` and friends.

``level_config`` keeps the historical flat entry point used by the local server:
it selects a level and leaves every game parameter to the level's documents.

Which listed levels players see is switched in ``level_switches.json``: {"level-4": {"on": false}} keeps level 4 out
of the page's level list and out of /api/level, while the engine, tests, research replay and the research console
still know it (available_levels, level_id, level_config). A level the file does not name is shown. A machine can
override the file without a new release (/etc/chefjeff/levels.override.json, or the path in
CHEFJEFF_LEVELS_OVERRIDE), in the same shape; it is read again when it changes, and a wrong override is not used.
From the command line: python3 levels.py show | set LEVEL on|off
"""
from functools import lru_cache
import json
import os
from pathlib import Path
import sys
import threading

import config_contract

SWITCHES = Path(__file__).resolve().with_name('level_switches.json')
OVERRIDE_ENV = 'CHEFJEFF_LEVELS_OVERRIDE'
DEFAULT_OVERRIDE = Path('/etc/chefjeff/levels.override.json')


@lru_cache(maxsize=1)
def _listed():
    return tuple({'id': d['id'], 'name': d['name'], 'menu_order': d.get('menu_order'),
                  'target': (d.get('goal') or {}).get('min_money')}
            for d in config_contract.Registry().levels() if d.get('menu_order') is not None)


# Every level a player built counts as level 0 in usage statistics and research records; which
# design it was is in the record's resolved configuration (its id starts with "player-").
PLAYER_LEVEL = 0


def level_number(config):
    """The listed level's number, or PLAYER_LEVEL for a level no menu lists."""
    number = config.get('level', 1)
    return PLAYER_LEVEL if number is None else number


def available_levels():
    """Listed levels in menu order: [{id, name, menu_order, target}] (target: the net income goal)."""
    return [dict(entry) for entry in _listed()]


def check_switches(raw):
    """{level id: on} from a switch file's object, or ValueError naming what is wrong."""
    listed = {entry['id'] for entry in _listed()}
    if not isinstance(raw, dict):
        raise ValueError('level switches must be an object {level id: {"on": true|false}}')
    out = {}
    for name, fields in raw.items():
        if name not in listed:
            raise ValueError(f'level switches name {name!r}, which no menu lists')
        if not isinstance(fields, dict) or set(fields) != {'on'} or type(fields['on']) is not bool:
            raise ValueError(f'level switches take only {{"on": true|false}} for {name}')
        out[name] = fields['on']
    return out


@lru_cache(maxsize=1)
def _released():
    return check_switches(json.loads(SWITCHES.read_text(encoding='utf-8')))


_override_lock = threading.Lock()
_override = {'key': object(), 'value': None}


def override_path() -> Path:
    return Path(os.environ.get(OVERRIDE_ENV) or DEFAULT_OVERRIDE)


def switches():
    """{level id: on}: level_switches.json with this machine's override, if any, applied."""
    base = _released()
    path = override_path()
    try:
        info = path.stat()
        key = (str(path), info.st_mtime_ns, info.st_size)
    except OSError:
        key = None
    with _override_lock:
        if key != _override['key']:
            value = base
            if key is not None:
                try:
                    value = {**base, **check_switches(json.loads(path.read_text(encoding='utf-8')))}
                except (OSError, ValueError) as error:
                    print(f'levels: {path} not used, the release\'s level_switches.json is: {error}', file=sys.stderr)
            _override.update(key=key, value=value)
        return dict(_override['value'])


def shown_levels():
    """The listed levels players see, in menu order: available_levels without those switched off."""
    on = switches()
    return [entry for entry in available_levels() if on.get(entry['id'], True)]


def shown_level_id(selection):
    """level_id for a level players may choose; ValueError for one switched off."""
    chosen = level_id(selection)
    if not switches().get(chosen, True):
        raise ValueError('Unknown level')
    return chosen


def level_id(selection):
    """Accept a level number or a level id; return the listed level id."""
    if type(selection) is int:
        selection = f'level-{selection}'
    listed = {entry['id'] for entry in available_levels()}
    if not isinstance(selection, str) or selection not in listed:
        raise ValueError('Unknown level')
    return selection


def level_config(base, level):
    """Flat config selecting ``level``; seeds are drawn when the round's configuration is frozen."""
    c = {k: v for k, v in dict(base).items() if k not in ('order_seed', 'spawn_seed')}
    for key in ('order_seed', 'spawn_seed'):
        if base.get(key) is not None:
            c[key] = base[key]
    c['level_id'] = level_id(level)
    c['level'] = next(entry['menu_order'] for entry in available_levels() if entry['id'] == c['level_id'])
    return c


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ['show']:
        on = switches()
        print(f'override file: {override_path()}' + ('' if override_path().exists() else ' (none)'))
        for entry in available_levels():
            print(f"  {entry['id']:10} {'shown' if on.get(entry['id'], True) else 'hidden'}")
        return 0
    if len(args) == 3 and args[0] == 'set' and args[2] in ('on', 'off'):
        path = override_path()
        try:
            current = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        except (OSError, ValueError):
            current = {}
        current[args[1]] = {'on': args[2] == 'on'}
        check_switches(current)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        return main(['show'])
    print('usage: python3 levels.py show | set LEVEL on|off', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
