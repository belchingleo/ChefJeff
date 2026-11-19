"""clear-names-v3: no bare item ids or "the held item" in what Jeff reads; each says what the thing is.

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
  ahead and dropped) are given in English;
- (v2) each chef's task in the state, and any option label that quotes it ("Continue current task: Chop F1 at Board
  1"), names the item before its id as the option labels do ("Chop lettuce (as fetched) F1 at Board 1"), from what
  the request's own kitchen shows of that item;
- (v2) the dropped-ahead note is read in the form the catalog leaves it too: v1 read it after the catalog had
  half-translated it, so the paused case stayed "dropped (已Pause或本局结束); asked again at once)" and every other one
  kept a stray ")" the catalog adds;
- (v3) an action event of a step that adds food to a plate names the food added, as it was when the step began
  ("Put the held bread (as fetched) onto the plate at Counter 2"): v2 named the first item the step changed, which
  could be the plate's own food, named after its first ingredient and stage ("Put the held lettuce (cooked) onto
  the plate"); and food on a plate is named as food_names names it (its dish, or "plate with" its components), not
  as its first ingredient ("Put the held plate with lettuce on Counter 10", not "the held lettuce"); a pick-up
  names the item its id says, also when the chef's hands swap (v2 could name the item put down) or the step is still
  under way (v2 named what the chef held).

Names come from the engine (provenance, vessels, the request's own state); nothing else changes, and applying it
twice changes nothing more, so it runs after the links table too. clear_names_version goes with the static part.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import engine_english
from model_language import english_text

VERSION = 'clear-names-v3'
BARE = re.compile(r'\b([FDPE]\d+)\b(?! \()')
PICKUP = re.compile(r'Pick up ([FDPE]\d+) \((.+?); auto-swap\) at ')
# The page's own food words, which the engine's events keep (food_names leaves events as they were).
OLD = re.compile(r'\b(raw meat|Raw meat|Chopped|Cooked|Burnt|Tomato|Lettuce|Bread|Pot)\b')
OLD_BEFORE = re.compile(r'\b(?:raw meat|Raw meat|Chopped|Cooked|Burnt|Tomato|Lettuce|Bread|Pot) $')
# The old words that name one ingredient (the others name a state or a vessel).
FOOD_WORDS = {'raw meat': 'beef', 'Raw meat': 'beef', 'Tomato': 'tomato', 'Lettuce': 'lettuce', 'Bread': 'bread'}
WORDS = {'raw': 'as fetched', 'chopped': 'chopped', 'cooking': 'cooking', 'ready': 'cooked', 'burnt': 'burnt'}
# The decision loop's own result notes that the language catalog does not cover (they reached Jeff in Chinese).
# They arrive here translated (harness.compose runs the catalog first): "提前问的回复作废 (not_listed), 马上重问)", the
# catalog's own ")" at the end and the paused reason half-translated ("已Pause或本局结束"); as written they match too.
PAUSED = {'已暂停或本局结束', english_text('已暂停或本局结束')}
RESULTS = ((re.compile(r'提前问的回复作废\s*[（(]([^）)]*)[）)]\s*[，,]\s*马上重问[）)]?'),
            lambda m: engine_english.ahead_dropped(None if m.group(1).strip() in PAUSED else m.group(1).strip())),)


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


@dataclass(frozen=True)
class Touched:
    """An item one completed step changed, from the kitchen's provenance."""
    item: str
    stage: str | None           # after the step (None: it left the kitchen or went into a plate)
    components: tuple           # after the step
    before: tuple | None        # (stage, components) after the item's previous step, None if it had none
    held_by: str | None         # the chef holding it after its previous step
    gone: bool                  # it went into a plate or left the kitchen in this step


def _state(touch):
    if not touch or not touch.state:
        return None, ()
    return touch.state[0], tuple(touch.state[1]) if len(touch.state) > 1 and touch.state[1] else ()


def _touched(kitchen):
    """{action id: [Touched]} from the kitchen's provenance."""
    out = {}
    for item, touches in kitchen.provenance.history.items():
        for i, t in enumerate(touches):
            previous = touches[i - 1] if i else None
            stage, components = _state(t)
            touched = Touched(item, stage, components, _state(previous) if previous and previous.state else None,
                              previous.place[5:] if previous and previous.place.startswith('hand:') else None,
                              not t.place)
            for aid in t.action_ids:
                out.setdefault(aid, []).append(touched)
    return out


def _names(payload):
    """{item id: what it is} for every item the request's own kitchen shows (stations, hands, floor, in flight)."""
    out = {}

    def add(food):
        if isinstance(food, dict) and food.get('id') and food.get('meaning'):
            out.setdefault(food['id'], _lower(food['meaning']))
            add(food.get('contents'))
    k = payload['state']['kitchen']
    for s in (k.get('stations') or {}).values():
        add(s.get('food'))
    for c in (k.get('chefs') or {}).values():
        add(c.get('holding'))
    for g in k.get('ground') or []:
        add(g.get('food'))
    for item in k.get('projectiles') or []:
        add(item)
    return out


def name_ids(text, names):
    """An id that stands alone gets what it is before it ("Chop F1 at" -> "Chop lettuce (as fetched) F1 at"), in place
    of one of the page's old food words there ("Pick up raw meat F2 at" -> "Pick up beef (as fetched) F2 at"); one
    already named so is left as it is."""
    out, last = [], 0
    for m in BARE.finditer(text):
        before, name = text[last:m.start()], names.get(m.group(1))
        if name and not text[:m.start()].endswith(name + ' '):
            old = OLD_BEFORE.search(before)
            out.append((before[:old.start()] if old else before) + f'{name} {m.group(1)}')
        else:
            out.append(before + m.group(0))
        last = m.end()
    return ''.join(out) + text[last:]


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
        if components:
            # (v3) Food on a plate is named as food_names names it: its dish when this round's orders can ask for
            # it, else "plate with" its components. Its id is its first ingredient's, which is not what it is now.
            if stage == 'burnt':
                return 'burnt dish'
            dish = kitchen.rules.dish(components)
            if dish and dish in kitchen.rules.menu:
                return english_text(kitchen.recipe_name(dish))     # as the request's menu names it
            return 'plate with ' + ', '.join(components)
        ingredient = kitchen.provenance.ingredients.get(item)
        if not ingredient:
            return None
        return f'{ingredient} ({WORDS.get(stage, stage)})' if stage in WORDS else ingredient
    return _kind(kitchen, item)


def _step_item(kitchen, items, actor, message):
    """(v3) Which of the items a plating step changed its event speaks of, named as it was when the step began.

    Adding food to a plate changes two items: the food added (gone into the plate) and the plate's food (which keeps
    its first ingredient's id). The event names one: the ingredient its old food word says ("Put the held Bread onto
    the plate", "Add the Tomato from Board 2"), else the one the chef held."""
    pickup = PICKUP.search(message)
    if pickup:
        # A pick-up that swaps hands changes the item picked up and the one put down; its event says the id.
        same = [t for t in items if t.item == pickup.group(1)]
        if same:
            return same[0]
    words = [FOOD_WORDS[m.group(1)] for m in OLD.finditer(message) if m.group(1) in FOOD_WORDS]
    if words:
        same = [t for t in items if t.item[:1] == 'F' and kitchen.provenance.ingredients.get(t.item) == words[0]
                and not (t.before and t.before[1])]
        if same:
            return min(same, key=lambda t: not t.gone)
    held = [t for t in items if t.held_by == actor]
    if held:
        return held[0]
    return None


def _action_item(kitchen, e, touched, payload, message=''):
    """The name of what an action event's step touched: from provenance once the step completed, else what the chef
    holds (a put or throw under way) or what lies at the step's target (a take under way)."""
    items = touched.get(e['action_id'])
    if items:
        foods = [t for t in items if t.item[:1] in 'FPD']
        if len(foods) > 1:
            chosen = _step_item(kitchen, foods, e.get('actor'), message)
            if chosen:
                stage, components = chosen.before or (chosen.stage, chosen.components)
                return _recipe_name(kitchen, chosen.item, stage, components)
        for t in foods:
            return _recipe_name(kitchen, t.item, t.stage, t.components)
        return None
    k = payload['state']['kitchen']
    chef = k.get('chefs', {}).get(e.get('actor'), {})
    if chef.get('job_id') != e['action_id']:
        return None
    pickup = PICKUP.search(message)
    if pickup and pickup.group(1) in _names(payload):
        # (v3) A pick-up under way: the item still lies there, as the request shows it (not what the chef holds).
        return _names(payload)[pickup.group(1)]
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
        name = _action_item(kitchen, e, touched, payload, message)
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
    names = _names(payload)
    for chef in (payload['state']['kitchen'].get('chefs') or {}).values():
        if isinstance(chef.get('task'), str):
            chef['task'] = name_ids(chef['task'], names)
    for q in payload.get('questions', {}).values():
        criteria = q.get('criteria') if isinstance(q, dict) else None
        if criteria:
            for key in criteria:
                criteria[key] = name_ids(label(criteria[key], held, contents=contents), names)
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
