"""clear-names-v1: no bare item ids or "the held item" in what Jeff reads; each says what the thing is.

A trial (features.json clear_names, off by default, no page switch). food_names (names-v1) names food in the state and
in the labels that name food, but left three kinds of text as before: labels that say only "the held item" ("Put the
held item on Counter 4", in every put and in put_where), pick-up labels that lead with the item id and say auto-swap
even with empty hands, and the recent events, written when they happened ("jeff threw F1 toward (3, 6)", "D1 returned
dirty", "human started: Put the held item on Board 2"). With this switch on, in the English request:

- every option label and put_where label that says "the held item" names what Jeff holds ("the held empty frying
  pan");
- a pick-up label reads "Pick up lettuce (as fetched) F7 at floor (5,3)", and, when Jeff holds something, "(the held
  plate with bread stays there)";
- a "then the other chef could" line names the item they would hold, which is the one Jeff passes;
- in recent_events, an item id that stands alone gets its kind after it ("F1 (beef, as fetched)" when the event says
  the stage, "D1 (plate)", "P1 (frying pan)"); "the held item" in an action event, and the page's old food words in
  it ("Take Chopped from Board 2", "Take raw meat from the fridge", "Pick up F1 (Raw meat; auto-swap)"), name the item
  that action touched as the recipes do ("Take beef (chopped) from Board 2"), from the kitchen's provenance, or for a
  step still under way from what the chef holds or what lies at its target;
- "Empty the food from the held frying pan" names what is in the pan;
- the decision loop's own result notes in recent_decisions that the language catalog does not cover (an answer asked
  ahead and dropped) are given in English.

Names come from the engine (provenance, vessels, the request's own state); nothing else changes, and applying it
twice changes nothing more, so it runs after the links table too. clear_names_version goes with the static part.
"""
from __future__ import annotations

import re

VERSION = 'clear-names-v1'
BARE = re.compile(r'\b([FDPE]\d+)\b(?! \()')
PICKUP = re.compile(r'Pick up ([FDPE]\d+) \((.+?); auto-swap\) at ')
# The page's own food words, which the engine's events keep (food_names leaves events as they were).
OLD = re.compile(r'\b(raw meat|Raw meat|Chopped|Cooked|Burnt|Tomato|Lettuce|Bread|Pot)\b')
WORDS = {'raw': 'as fetched', 'chopped': 'chopped', 'cooking': 'cooking', 'ready': 'cooked', 'burnt': 'burnt'}
# The decision loop's own result notes that the language catalog does not cover (they reached Jeff in Chinese).
RESULTS = ((re.compile(r'提前问的回复作废\s*[（(]([^）)]*)[）)]\s*[，,]\s*马上重问'),
            lambda m: 'the answer asked ahead was dropped ('
                      + {'已暂停或本局结束': 'paused, or the round ended'}.get(m.group(1).strip(), m.group(1).strip())
                      + '); asked again at once'),)


def _lower(text):
    """'Clean plate' -> 'clean plate'; names that start with an ingredient stay as they are."""
    return text[:1].lower() + text[1:] if text and text[:1].isupper() and not text[1:2].isupper() else text


def _held(payload, who='jeff'):
    held = payload['state']['kitchen']['chefs'].get(who, {}).get('holding')
    return _lower(held.get('meaning')) if isinstance(held, dict) and held.get('meaning') else None


def _kind(kitchen, item, stage=None):
    """What an item id is, from the engine: an ingredient (with the stage when given), a plate, a vessel, a tool."""
    head = item[:1]
    if head == 'F':
        ingredient = kitchen.provenance.ingredients.get(item)
        if ingredient:
            return f'{ingredient}, {WORDS.get(stage, stage)}' if stage in WORDS else ingredient
        return None
    if head == 'D':
        return 'plate'
    if head == 'P':
        try:
            from model_language import english_text
            return english_text(kitchen.vessel_name(item))
        except Exception:
            return 'pot'
    if head == 'E':
        return 'extinguisher'
    return None


def _touched(kitchen):
    """{action id: [(item, stage after the step)]} from the kitchen's provenance."""
    out = {}
    for item, touches in kitchen.provenance.history.items():
        for t in touches:
            for aid in t.action_ids:
                out.setdefault(aid, []).append((item, t.state[0] if t.state else None,
                                                tuple(t.state[1]) if t.state and len(t.state) > 1 and t.state[1] else ()))
    return out


def _pickup(label, held):
    def sub(m):
        return f'Pick up {_lower(m.group(2))} {m.group(1)} at '
    out = PICKUP.sub(sub, label)
    if out != label and held:
        out += f' (the held {held} stays there)'
    return out


def label(text, held, stays=True, contents=None):
    """An option label (or a partner line, stays=False: the pick-up there is not Jeff's) with the held item named."""
    if held:
        text = text.replace('the held item', f'the held {held}')
    if contents:
        text = text.replace('Empty the food from the held', f'Empty the {contents} from the held')
    return _pickup(text, held if stays else None)


def _recipe_name(kitchen, item, stage, components=()):
    if item[:1] == 'D':
        if stage in ('clean_plate', 'dirty_plate'):
            return stage.replace('_', ' ')
        return 'plate with ' + ', '.join(components) if components else 'plate'
    if item[:1] == 'F':
        ingredient = kitchen.provenance.ingredients.get(item)
        if not ingredient:
            return None
        return f'{ingredient} ({WORDS.get(stage, stage)})' if stage in WORDS else ingredient
    return _kind(kitchen, item)


def _action_item(kitchen, e, touched, payload):
    """The name of what an action event's step touched: from provenance once the step completed, else what the chef
    holds (a put or throw under way) or what lies at the step's target (a take under way)."""
    items = touched.get(e['action_id'])
    if items:
        # A plate's own touch names a dish being put together; an ingredient merged into it names what was added.
        for item, stage, components in items:
            if item[:1] in 'FPD':
                return _recipe_name(kitchen, item, stage, components)
        return None
    k = payload['state']['kitchen']
    chef = k.get('chefs', {}).get(e.get('actor'), {})
    if chef.get('job_id') != e['action_id']:
        return None
    if isinstance(chef.get('holding'), dict):
        return _lower(chef['holding'].get('meaning'))
    target = (e.get('action') or '').split()[-1:]
    food = k.get('stations', {}).get(target[0], {}).get('food') if target else None
    if not isinstance(food, dict):
        food = next((g.get('food') for g in k.get('ground', []) if isinstance(g.get('food'), dict)
                     and g['food'].get('id') == (target[0] if target else None)), None)
    return _lower(food.get('meaning')) if isinstance(food, dict) and food.get('meaning') else None


def event(kitchen, e, touched, payload):
    message = e.get('message')
    if not isinstance(message, str):
        return e
    def sub(m):
        item = m.group(1)
        what = _kind(kitchen, item, e.get('stage') if e.get('item') == item else None)
        return f'{item} ({what})' if what else item
    message = BARE.sub(sub, message)
    if e.get('action_id') is not None and e.get('kind') in ('action_start', 'action_done') and (
            'the held item' in message or OLD.search(message) or PICKUP.search(message)):
        name = _action_item(kitchen, e, touched, payload)
        if name:
            message = message.replace('the held item', f'the held {name}')
            message = PICKUP.sub(lambda m: f'Pick up {name} {m.group(1)} at ', message)
            message = OLD.sub(name, message, count=1)

    return {**e, 'message': message} if message != e.get('message') else e


def apply(payload, kitchen):
    """What the clear_names switch does to an English request (harness.compose, and again after the links table)."""
    held = _held(payload)
    holding = payload['state']['kitchen']['chefs'].get('jeff', {}).get('holding')
    inside = holding.get('contents') if isinstance(holding, dict) else None
    contents = _lower(inside.get('meaning')) if isinstance(inside, dict) and inside.get('meaning') else None
    for q in payload.get('questions', {}).values():
        criteria = q.get('criteria') if isinstance(q, dict) else None
        if criteria:
            for key in criteria:
                criteria[key] = label(criteria[key], held, contents=contents)
    links = payload['state'].get('option_links')
    if isinstance(links, dict):
        # "The held item" in a partner line is the other chef's, which is the item Jeff passes; Jeff's own lines name
        # what he would hold after the option already. A pick-up there is not Jeff's, so nothing is said to stay.
        for key, lines in links.items():
            links[key] = [label(l, held, stays=False) if l.startswith('then the other chef could') else _pickup(l, None)
                          for l in lines]
    events = payload['state'].get('recent_events')
    # The events are named once (the first pass); the labels and the links table are named on every pass, which
    # changes nothing already named.
    if events and 'clear_names_version' not in payload['state']:
        touched = _touched(kitchen)
        payload['state']['recent_events'] = [event(kitchen, e, touched, payload) for e in events]
    for decision in payload['state'].get('recent_decisions') or []:
        result = decision.get('result') if isinstance(decision, dict) else None
        if isinstance(result, str):
            for pattern, english in RESULTS:
                result = pattern.sub(english, result)
            decision['result'] = result
    payload['state']['clear_names_version'] = VERSION
    return payload
