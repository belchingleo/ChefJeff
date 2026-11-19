"""engine-english-v1: the engine writes the English Jeff reads where the language catalog garbles or misses it.

A trial (features.json engine_english, off by default, no page switch). The engine writes every action label and
event message in Chinese for the player, and Jeff's request maps them to English through the phrase catalog
(model-language-en-v4.json, model_language.english_text). A few strings the catalog matches wrongly or not at all
reached Jeff half in Chinese, in about one request in six of the logged rounds:

- plating from a pan or pot on a counter, "用手中的盘盛出柜台 4的平底锅里的菜", came out "Plate food from the pot on
  Counter 4的平底" (the catalog's "...{0}锅里的菜" template matches before "...{0}的{1}里的菜"); plating from one on
  the floor came out "Plate food from 地上frying pan里 (...)". Both are in the options, in the events that carry the
  label (started / stopped / completed / completed together) and in a chef's task while it does it;
- the decision loop's own notes in recent_decisions: an answer asked ahead and dropped, and a one-press choice
  whose first step cannot be done now, stayed Chinese.

With this switch on, the engine writes these in English itself, next to the Chinese: an Action carries `english`
(not compared, not shown), Kitchen.emit keeps an event's English in `Kitchen.english_events` by seq (never in the
event, so the page, the journals, the research records and their engine state are as before), and the request takes
the English where the engine wrote one. The station names are the catalog's for now (english_text of the name), the
vessels are named by kind (pan "frying pan", pot "soup pot", any other "pot"). Food words stay names-v1's. Nothing
else changes; with the switch off every request is byte-identical. engine_english_version goes with the static part.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from model_language import english_text

VERSION = 'engine-english-v1'
# Whether the request being built takes the engine's English (jev.compose_payload sets it; a thread sets its own).
ON = ContextVar('engine_english', default=False)
# The chefs as the catalog names them (its actors: 你 -> human, Jeff -> jeff).
ACTORS = {'human': 'human', 'jeff': 'jeff'}
# Cooking vessels by kind (content/recipes: pot 汤锅, pan 平底锅); a vessel of no known kind is a "pot" (锅).
VESSELS = {'pan': 'frying pan', 'pot': 'soup pot'}
VESSEL = 'pot'

# The decision loop's result notes (jev.DecisionLoop.poll), as Jeff reads them with the switch on.
AHEAD_REASONS = {'已暂停或本局结束': 'paused, or the round ended'}
CHAIN_NOT_NOW = 'the first step of this one-press choice cannot be done now'


def ahead_dropped(reason=None):
    """An answer asked ahead and dropped, in clear_names' wording; reason is ask-ahead's check (jev.DecisionLoop:
    too_old, hand_differs, ...), None when the round was paused or ended."""
    reason = AHEAD_REASONS.get(reason, reason) or AHEAD_REASONS['已暂停或本局结束']
    return f'the answer asked ahead was dropped ({reason}); asked again at once'


@contextmanager
def writing(on=True):
    """The request built for the duration takes the engine's English when on (restored after)."""
    token = ON.set(bool(on))
    try:
        yield
    finally:
        ON.reset(token)


def vessel(kind):
    return VESSELS.get(kind, VESSEL)


def started(who, english, travel, work):
    return f'{ACTORS[who]} started: {english} (travel {travel:.0f}s + work {work:.1f}s)'


def stopped(who, english):
    return f'{ACTORS[who]} stopped: {english}'


def completed(who, english):
    return f'{ACTORS[who]} completed: {english}'


def completed_together(who, english):
    return f'{ACTORS[who]} completed together: {english}'


def label(action):
    """An option's label in the request before translation: the engine's English when on and written."""
    english = getattr(action, 'english', '')
    return english if english and ON.get() else action.label


def text(action):
    """An action's label in English, as the links table writes it: the engine's when on and written."""
    english = getattr(action, 'english', '')
    return english if english and ON.get() else english_text(action.label)


def events(kitchen, shown):
    """The events shown to Jeff, those the engine wrote in English too given that message (copies; the kitchen's
    events are never changed). As they are when off."""
    table = getattr(kitchen, 'english_events', None) if ON.get() else None
    if not table:
        return shown
    return [{**e, 'message': table[e['seq']]} if e.get('seq') in table else e for e in shown]


def apply(payload, kitchen):
    """What the switch adds to a translated request (harness.compose): each chef's task in the engine's English
    where it wrote one, and the version."""
    chefs = payload['state'].get('kitchen', {}).get('chefs') or {}
    for who, chef in getattr(kitchen, 'chefs', {}).items():
        job = getattr(chef, 'job', None)
        english = getattr(job.action, 'english', '') if job else ''
        if english and isinstance(chefs.get(who), dict) and 'task' in chefs[who]:
            chefs[who]['task'] = english
    payload['state']['engine_english_version'] = VERSION
    return payload
