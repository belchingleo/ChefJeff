"""Which of Jeff's harness features are on, from features.json: one file for what is released and what is on trial.

Each feature has a stage:

- release: on unless the file says "on": false (to roll it back, or to run a comparison with it off); the page
  shows no switch for it.
- trial: off unless the file says "on": true; with "player_switch": true it also shows in Settings -> AI teammate
  as a "(测试)" switch, and "on" is then its default for a new session.

"version" must be the version the code implements, so the file cannot name behaviour the code does not have:
rolling a feature back to an older version still means rolling back the code. The file is read once and checked;
a wrong name, stage or value stops the server instead of running with it. Every round's start row and research
record carry the snapshot (name -> on, version), so rounds stay comparable when the file changes.

A server can switch features without a new release, through an override file outside the release
(/etc/chefjeff/features.override.json, or the path in CHEFJEFF_FEATURES_OVERRIDE): {name: {"on": ..,
"player_switch": ..}}, only those two fields, for features this release has. The result is checked like
features.json (a released feature has no player switch, one plan mode at a time); a wrong override is not used,
the release's file is, and the reason goes to stderr. The file is read again when it changes, and a session takes
the switches as each round starts, so a round already running keeps its own; compact_input, which only lays out a
request and does not change it, applies from the next request. A feature the override sets is recorded with
"source": "server". From the command line (python3 features.py ...): show, check [FILE], set NAME on|off
[--switch on|off], unset NAME.
Game rules, levels, player preferences (memory, language) and numbers (request spacing, call limits) stay where
they are; this file is only for features that change what Jeff is asked or how his answers are carried out.
"""
from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import sys
import threading

import harness
import one_press
import wire_format
import ask_ahead
import undo_note
import reach_note
import food_names
import links

ROOT = Path(__file__).resolve().parent
PATH = ROOT / 'features.json'
STAGES = ('release', 'trial')
# name -> the version the code implements.
VERSIONS = {'one_press': one_press.VERSION, 'jeff_plan': harness.PLAN_RULES_VERSION,
            'rolling_intent': harness.ROLLING_RULES_VERSION, 'undo_note': undo_note.VERSION,
            'compact_input': wire_format.VERSION, 'ask_ahead': ask_ahead.VERSION,
            'reach_note': reach_note.VERSION, 'food_names': food_names.VERSION,
            'option_links': links.SWITCH_VERSION}
# The plan modes (harness.PLAN_MODES), one at a time, and the feature of each.
PLAN_FEATURES = {'choice': 'jeff_plan', 'rolling': 'rolling_intent'}
FIELDS = {'stage', 'on', 'player_switch', 'version'}


def check(data) -> dict:
    """The features, each with stage, on, player_switch and version, or ValueError naming what is wrong."""
    if not isinstance(data, dict):
        raise ValueError('features.json must hold an object')
    if set(data) != set(VERSIONS):
        missing, unknown = sorted(set(VERSIONS) - set(data)), sorted(set(data) - set(VERSIONS))
        raise ValueError(f'features.json: missing {missing}, unknown {unknown}')
    out = {}
    for name, value in data.items():
        if not isinstance(value, dict) or set(value) - FIELDS or not {'stage', 'on', 'version'} <= set(value):
            raise ValueError(f'features.json: {name} takes stage, on, version and (for a trial) player_switch')
        stage, on, switch = value['stage'], value['on'], value.get('player_switch', False)
        if stage not in STAGES:
            raise ValueError(f'features.json: {name} stage must be one of {STAGES}')
        if type(on) is not bool or type(switch) is not bool:
            raise ValueError(f'features.json: {name} on and player_switch must be true or false')
        if switch and stage == 'release':
            raise ValueError(f'features.json: {name} is released, so it has no player switch')
        if value['version'] != VERSIONS[name]:
            raise ValueError(f'features.json: {name} version {value["version"]!r} is not the code\'s {VERSIONS[name]!r}')
        out[name] = {'stage': stage, 'on': on, 'player_switch': switch, 'version': value['version']}
    if sum(out[name]['on'] for name in PLAN_FEATURES.values()) > 1:
        raise ValueError('features.json: one plan mode at a time (jeff_plan or rolling_intent)')
    return out


def load(path=None) -> dict:
    return check(json.loads(Path(path or PATH).read_text(encoding='utf-8')))


@lru_cache(maxsize=1)
def _release():
    """This release's features.json, as written (raw), and checked."""
    raw = json.loads(PATH.read_text(encoding='utf-8'))
    return raw, check(raw)


OVERRIDE_ENV = 'CHEFJEFF_FEATURES_OVERRIDE'
DEFAULT_OVERRIDE = Path('/etc/chefjeff/features.override.json')
OVERRIDE_FIELDS = ('on', 'player_switch')
_override_lock = threading.Lock()
_override = {'key': object(), 'value': None}       # read on first use; key None means no override file


def override_path() -> Path:
    return Path(os.environ.get(OVERRIDE_ENV) or DEFAULT_OVERRIDE)


def with_override(raw, override) -> dict:
    """features.json as written with a server override applied, checked; ValueError naming what is wrong."""
    if not isinstance(override, dict):
        raise ValueError('the override must hold an object {feature: {"on": ..., "player_switch": ...}}')
    merged = {name: dict(value) for name, value in raw.items()}
    for name, fields in override.items():
        if name not in merged:
            raise ValueError(f'the override names {name!r}, which this release does not have')
        if not isinstance(fields, dict) or not fields or set(fields) - set(OVERRIDE_FIELDS):
            raise ValueError(f'the override may set only {OVERRIDE_FIELDS} for {name}')
        merged[name].update(fields)
        if merged[name].get('player_switch') is False:
            merged[name].pop('player_switch')        # a released feature takes no switch field at all
    out = check(merged)
    for name in override:
        out[name]['source'] = 'server'
    return out


def _effective():
    raw, base = _release()
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
                    value = with_override(raw, json.loads(path.read_text(encoding='utf-8')))
                except (OSError, ValueError) as error:
                    print(f'features: {path} not used, the release\'s features.json is: {error}', file=sys.stderr)
            _override.update(key=key, value=value)
        return _override['value']


def current() -> dict:
    """The switches as of now: this release's features.json and the server's override, if any, checked (a copy:
    callers may not change it). A session takes them as each round starts."""
    return {name: dict(value) for name, value in _effective().items()}


def snapshot(features) -> dict:
    """What a round records: each feature on or off, with its version, and "source": "server" where the server's
    override set it."""
    return {name: {'on': value['on'], 'version': value['version'],
                   **({'source': 'server'} if value.get('source') == 'server' else {})}
            for name, value in features.items()}


def plan_default(features) -> str:
    """The plan mode a session starts with: the plan feature that is on, else off."""
    return next((mode for mode, name in PLAN_FEATURES.items() if features[name]['on']), 'off')


def plan_choices(features) -> list:
    """The plan modes the player can pick in Settings (besides off): those with a player switch."""
    return [mode for mode, name in PLAN_FEATURES.items() if features[name]['player_switch']]


def undo_start(features):
    """The decision loop's undo-note state for a new round: {'step': None} when undo_note is on, else None."""
    return {'step': None} if features['undo_note']['on'] else None


def one_press_flags(features):
    """The decision loop's one-press switches (one_press.flags) for these features: all on, or None."""
    return one_press.flags({name: True for name in one_press.NAMES}) if features['one_press']['on'] else None


def _write_override(value, path):
    """Write the override atomically, readable by the game's service account, after checking it applies."""
    raw, _ = _release()
    with_override(raw, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.chmod(temp, 0o644)
    os.replace(temp, path)


def _read_override(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description='Show and change which harness features are on, without a new release.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('show', help='the switches as a new round would take them, and where each comes from')
    checking = sub.add_parser('check', help='check an override file against this release (default: the server\'s)')
    checking.add_argument('file', nargs='?')
    setting = sub.add_parser('set', help='set a feature on or off in the server\'s override')
    setting.add_argument('name')
    setting.add_argument('on', choices=('on', 'off'))
    setting.add_argument('--switch', choices=('on', 'off'), help='also show (on) or hide (off) its Settings switch')
    unsetting = sub.add_parser('unset', help='drop a feature from the override: the release\'s value again')
    unsetting.add_argument('name')
    args = parser.parse_args(argv)
    path = override_path()
    try:
        if args.command == 'check':
            raw, _ = _release()
            target = Path(args.file) if args.file else path
            value = with_override(raw, _read_override(target))
            print(f'{target}: valid for this release')
            path, effective = target, value
        elif args.command in ('set', 'unset'):
            value = _read_override(path)
            if args.command == 'set':
                value[args.name] = {**value.get(args.name, {}), 'on': args.on == 'on',
                                    **({'player_switch': args.switch == 'on'} if args.switch else {})}
            else:
                value.pop(args.name, None)
            _write_override(value, path)
            print(f'{path} written; new rounds take it, rounds already running keep theirs')
            effective = with_override(_release()[0], value)
        else:
            effective = _effective()
    except (OSError, ValueError) as error:
        print(f'not changed: {error}', file=sys.stderr)
        return 1
    print(f'override file: {path}' + ('' if path.exists() else ' (none)'))
    for name, value in effective.items():
        print(f"  {name:15s} {'on ' if value['on'] else 'off'}  {value['stage']:7s} "
              f"{'switch ' if value['player_switch'] else '       '}{value['version']:14s} {value.get('source', 'release')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
