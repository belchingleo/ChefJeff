"""Which of Jeff's harness features are on, from features.json: one file for what is released and what is on trial.

Each feature has a stage:

- release: on unless the file says "on": false (to roll it back, or to run a comparison with it off).
- trial: off unless the file says "on": true.

The page offers no switch for any of them (the last one, 步骤提示 for option_links, went 2026-11-20): what Jeff is
sent is set here, the same for every player. A feature that is on may name, in "off_for", the model services (ids in
model-providers.json) whose rounds take it off (model_defaults); a server's override can set it too. A round whose
service turned a feature off records "source": "model" for it.

"version" must be the version the code implements, so the file cannot name behaviour the code does not have:
rolling a feature back to an older version still means rolling back the code. The file is read once and checked;
a wrong name, stage or value stops the server instead of running with it. Every round's start row and research
record carry the snapshot (name -> on, version), so rounds stay comparable when the file changes.

A server can switch features without a new release, through an override file outside the release
(/etc/chefjeff/features.override.json, or the path in CHEFJEFF_FEATURES_OVERRIDE): {name: {"on": ..,
"off_for": [..]}}, only those two fields, for features this release has ("off_for": [] gives the feature to every
service, as a comparison with it on for all needs). The result is checked like features.json; a wrong override is
not used,
the release's file is, and the reason goes to stderr. The file is read again when it changes, and a session takes
the switches as each round starts, so a round already running keeps its own. A feature the override sets is recorded with
"source": "server". From the command line (python3 features.py ...): show, check [FILE], set NAME on|off,
unset NAME.
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

import one_press
import ask_ahead
import undo_note
import reach_note
import split_floor
import burn_note
import option_notes
import step_check
import clear_names
import walk_note
import go_note
import work_notes
import plate_names
import engine_english
import food_names
import links
import request_parts

ROOT = Path(__file__).resolve().parent
PATH = ROOT / 'features.json'
STAGES = ('release', 'trial')
# name -> the version the code implements.
VERSIONS = {'one_press': one_press.VERSION, 'undo_note': undo_note.VERSION,
            'ask_ahead': ask_ahead.VERSION,
            'reach_note': reach_note.VERSION,
            'option_links': links.SWITCH_VERSION,
            'option_links_partner': links.PARTNER_VERSION,
            'split_floor': split_floor.VERSION,
            'burn_note': burn_note.VERSION,
            'step_check': step_check.VERSION,
            'walk_note': walk_note.VERSION,
            'go_note': go_note.VERSION,
            'clear_text': 'clear-text-v1',
            'option_notes': option_notes.VERSION,
            'throw_to': one_press.THROW_TO_VERSION,
            **{name: version for name, (_, version) in work_notes.SWITCHES.items()},
            # The parts of the restructured request (request_parts.py), one switch each.
            **{name: version for name, (_, version) in request_parts.SWITCHES.items()}}
# clear_text (2026-11-19: was food_names, clear_names, engine_english and plate_names) turns those four on together;
# clear-text-v1 is names-v1, clear-names-v3, engine-english-v1 and plate-names-v1. option_notes (was serve_note and
# wait_note) is serve-note-v1 and wait-note-v2 in option-notes-v1, serve-note-v2 and wait-note-v2 in option-notes-v2,
# serve-note-v2 alone in option-notes-v3 (the wait note went 2026-11-20), serve-note-v3 in option-notes-v4.
FIELDS = {'stage', 'on', 'version', 'off_for'}
# The model services a feature's off_for may name: every preset in the shared service list.
SERVICES = frozenset(p['id'] for p in json.loads((ROOT / 'model-providers.json').read_text(encoding='utf-8'))['providers'])


def check(data) -> dict:
    """The features, each with stage, on and version (and off_for where set), or ValueError naming what is wrong."""
    if not isinstance(data, dict):
        raise ValueError('features.json must hold an object')
    if set(data) != set(VERSIONS):
        missing, unknown = sorted(set(VERSIONS) - set(data)), sorted(set(data) - set(VERSIONS))
        raise ValueError(f'features.json: missing {missing}, unknown {unknown}')
    out = {}
    for name, value in data.items():
        if not isinstance(value, dict) or set(value) - FIELDS or not {'stage', 'on', 'version'} <= set(value):
            raise ValueError(f'features.json: {name} takes stage, on, version and off_for')
        stage, on = value['stage'], value['on']
        if stage not in STAGES:
            raise ValueError(f'features.json: {name} stage must be one of {STAGES}')
        if type(on) is not bool:
            raise ValueError(f'features.json: {name} on must be true or false')
        if value['version'] != VERSIONS[name]:
            raise ValueError(f'features.json: {name} version {value["version"]!r} is not the code\'s {VERSIONS[name]!r}')
        out[name] = {'stage': stage, 'on': on, 'version': value['version']}
        if 'off_for' in value:
            services = value['off_for']
            if (not isinstance(services, list) or len(set(map(str, services))) != len(services)
                    or not all(isinstance(x, str) and x in SERVICES for x in services)):
                raise ValueError(f'features.json: {name} off_for must list distinct model services from '
                                 f'model-providers.json ({", ".join(sorted(SERVICES))})')
            out[name]['off_for'] = list(services)
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
OVERRIDE_FIELDS = ('on', 'off_for')
_override_lock = threading.Lock()
_override = {'key': object(), 'value': None}       # read on first use; key None means no override file


def override_path() -> Path:
    return Path(os.environ.get(OVERRIDE_ENV) or DEFAULT_OVERRIDE)


def with_override(raw, override) -> dict:
    """features.json as written with a server override applied, checked; ValueError naming what is wrong."""
    if not isinstance(override, dict):
        raise ValueError('the override must hold an object {feature: {"on": ..., "off_for": [...]}}')
    merged = {name: dict(value) for name, value in raw.items()}
    for name, fields in override.items():
        if name not in merged:
            raise ValueError(f'the override names {name!r}, which this release does not have')
        if not isinstance(fields, dict) or not fields or set(fields) - set(OVERRIDE_FIELDS):
            raise ValueError(f'the override may set only {OVERRIDE_FIELDS} for {name}')
        merged[name].update(fields)
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


def model_defaults(features, service) -> dict:
    """These features as a round with this model service (a model-providers.json id, or None where the session does
    not know one) takes them: each feature that is on and names the service in off_for
    is off, with "source": "model"."""
    if not service:
        return features
    return {name: ({**value, 'on': False, 'source': 'model'} if value['on'] and service in value.get('off_for', ()) else value)
            for name, value in features.items()}


def snapshot(features) -> dict:
    """What a round records: each feature on or off, with its version, and "source": "server" where the server's
    override set it or "model" where the round's model service took it off (model_defaults). Records from before
    2026-11-20 may also say "player", where the player's own 步骤提示 switch did."""
    return {name: {'on': value['on'], 'version': value['version'],
                   **({'source': value['source']} if value.get('source') in ('server', 'model') else {})}
            for name, value in features.items()}


def links_option(features):
    """The decision loop's links setting: False, True (option_links), or 'partner' (option_links_partner: the other
    chef's side too, which does nothing alone)."""
    if not features['option_links']['on']:
        return False
    extras = [part for part, name in (('partner', 'option_links_partner'),) if (features.get(name) or {}).get('on')]
    return '+'.join(extras) or True


def undo_start(features):
    """The decision loop's undo-note state for a new round: {'history': []} when undo_note is on (undo-note-v4: the
    layout at each of Jeff's last steps), else None."""
    return {'history': []} if features['undo_note']['on'] else None


def one_press_flags(features):
    """The decision loop's one-press switches (one_press.flags) for these features: all on, or None."""
    names = {name: True for name in one_press.NAMES}
    on = one_press.flags(names) if features['one_press']['on'] else None
    if on and features.get('throw_to', {}).get('on'):
        on[one_press.THROW_TO] = True       # the throw_to trial rides on the one-press switches (one_press.py)
    return on


def _round_options(features):
    """compose_payload's round-wide switches for these features (a feature they do not name is off): all but
    one_press and undo, which a round sets as it starts and research replay takes from each request's record.
    parts and work are None when off."""
    def on(name):
        return bool((features.get(name) or {}).get('on'))
    flat = {name: {'on': on(name)} for name in VERSIONS}
    text = on('clear_text')
    return {'reach': on('reach_note'), 'names': text, 'links': links_option(flat), 'split': on('split_floor'),
            'burn': on('burn_note'), 'serve_note': on('option_notes'), 'steps': on('step_check'), 'clear': text,
            'walk': on('walk_note'), 'go': on('go_note'), 'english': text, 'plate': text,
            'parts': request_parts.parts(flat), 'work': work_notes.flags(flat)}


def compose_options(features):
    """compose_payload's switches for a new round with these features: what the session sets on the decision loop
    (loop_switches), and what scripts that build Jeff's request outside a session pass. parts and work only when on."""
    options = {'one_press': one_press_flags(features), 'undo': undo_start(features), **_round_options(features)}
    return {name: value for name, value in options.items() if value is not None or name not in ('parts', 'work')}


def loop_switches(features):
    """The decision loop's switches for a new round with these features, as the session sets them (web_server.py):
    compose_options with parts and work None when off, and ask_ahead."""
    return {'parts': None, 'work': None, **compose_options(features), 'ask_ahead': features['ask_ahead']['on']}


# Names a round's snapshot gave, before 2026-11-19, to what one of compose_payload's switches does: since then
# clear_text turns the first four on together and option_notes the last. A record's wait_note turns nothing on (its
# note went 2026-11-20).
NAMES_BEFORE_1119 = {'names': 'food_names', 'clear': 'clear_names', 'english': 'engine_english',
                     'plate': 'plate_names', 'serve_note': 'serve_note'}


def replay_options(snapshot):
    """compose_payload's round-wide switches for research replay, from a round's recorded feature snapshot
    (snapshot()): those of compose_options but one_press and undo, which each request's record carries; parts and
    work None when off. A name the snapshot lacks is off, and a record from before 2026-11-19 is read with its own
    names (NAMES_BEFORE_1119), so old rounds replay as they were played."""
    options = _round_options(snapshot)
    for option, old in NAMES_BEFORE_1119.items():
        options[option] = options[option] or bool((snapshot.get(old) or {}).get('on'))
    return options


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
                value[args.name] = {**value.get(args.name, {}), 'on': args.on == 'on'}
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
              f"{value['version']:14s} {value.get('source', 'release')}"
              + (f"  off for {', '.join(value['off_for'])}" if value.get('off_for') else ''))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
