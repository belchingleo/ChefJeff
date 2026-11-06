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
Game rules, levels, player preferences (memory, language) and numbers (request spacing, call limits) stay where
they are; this file is only for features that change what Jeff is asked or how his answers are carried out.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

import harness
import one_press
import undo_note

ROOT = Path(__file__).resolve().parent
PATH = ROOT / 'features.json'
STAGES = ('release', 'trial')
# name -> the version the code implements.
VERSIONS = {'one_press': one_press.VERSION, 'jeff_plan': harness.PLAN_RULES_VERSION,
            'rolling_intent': harness.ROLLING_RULES_VERSION, 'undo_note': undo_note.VERSION}
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
def _current():
    return load()


def current() -> dict:
    """The checked features.json of this checkout, read once (a copy: callers may not change it)."""
    return {name: dict(value) for name, value in _current().items()}


def snapshot(features) -> dict:
    """What a round records: each feature on or off, with its version."""
    return {name: {'on': value['on'], 'version': value['version']} for name, value in features.items()}


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
