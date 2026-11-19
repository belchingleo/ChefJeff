"""option-effects-v1: each option says what carrying it out directly does, as the engine computes it.

A trial (features.json option_effects, off by default, no page switch). Jeff reads the whole kitchen with every
request, but a decision model scores each option mostly from its own label: it does not join a pan's heat in one field,
the burn threshold in another and "resume heating" in a third into "this burns 1.4 s after it is back". A player sees
those results on the screen the moment the step ends. With this switch on, each next_action option whose step has such
a result gets one note after its label, worked out on forks of the kitchen the request describes:

- the option's fork carries the option out to the end of its step (a one-press option: all its steps), the other chef
  keeping what it does with no new input, as the links table does (links._carry_out);
- the waiting fork plays the same game time with Jeff starting nothing;
- the note names what differs at that moment, of three kinds only:
  money the step itself brings: an order served and what it pays, a dish no order waits for, a refused burnt dish, food
  thrown away, a stove that catches fire in the option's fork and not in the waiting one;
  heat: food that heats in one fork and not in the other ("beef (cooked) heats again on Stove 2: it burns and Stove 2
  catches fire in 1.4 s", "beef (cooked) stops heating", "beef (chopped) starts cooking on Stove 1: cooked in 10.0 s,
  burns in 20.0 s");
  supplies: one that gives nothing in one fork and gives its ingredient in the other, with what lies on it.

One step only: nothing about what the option leads to afterwards or what to do next, and nothing the waiting fork has as
well (an order that expires, a pan that burns either way). Where a one-press option puts the held item depends on
put_where, which the fork cannot know, so what happens at that place is left out. Options with no such result get no
note; the static part is rules.effects and option_effects_version.
"""
from __future__ import annotations

from model_language import english_text

VERSION = 'option-effects-v1'
STEP = .05
NO_STEP = ('go', 'wait', 'stop', 'continue')
RULE = ('Some options of next_action end with "(Result: ...)": what carrying out that option directly does, as the game '
        'computes it, compared with waiting for the same time: money it brings, food that starts or stops heating (with '
        'when it is cooked and when it burns), and supplies that stop or start giving their ingredient. It does not say '
        'whether you should choose that option.')


class _Names:
    """Stations as the request names them, food as food_names does (the engine in naming mode), all in English."""

    def __init__(self, payload, kitchen):
        stations = ((payload or {}).get('state', {}).get('kitchen', {}) or {}).get('stations') or {}
        self.stations = {key: s.get('name') for key, s in stations.items() if isinstance(s, dict) and s.get('name')}
        self.kitchen = kitchen

    def station(self, key):
        return self.stations.get(key) or english_text(self.kitchen.stations[key].name)

    def food(self, kitchen, food):
        import food_names
        if food is None:
            return 'nothing'
        if food.stage == 'pot':
            vessel = english_text(kitchen.vessel_name(food.id))
            return f'{vessel} with {self.food(kitchen, food.contents)}' if food.contents else f'empty {vessel}'
        if food.stage in ('clean_plate', 'dirty_plate'):
            return food.stage.replace('_', ' ')
        if food.stage == 'extinguisher':
            return 'extinguisher'
        with food_names.naming():
            return english_text(food_names.plain(kitchen, food))


def _heat(kitchen):
    """{food id: (stove key, heating, heated, stage, ingredient)} for the food in each pan or pot on a stove."""
    out = {}
    for key in kitchen.pots:
        s = kitchen.stations[key]
        if s.food is not None and s.food.stage != 'pot':
            out[s.food.id] = (key, bool(s.heating and not s.fire), s.food.heated, s.food.stage, s.food.ingredient)
    return out


def _blocked(kitchen):
    """{supply key: what lies on it} for each ingredient supply that gives nothing because something lies on it."""
    return {key: kitchen.stations[key].food for key in kitchen.ingredients if kitchen.stations[key].food is not None}


def _fires(kitchen):
    return frozenset(key for key, s in kitchen.stations.items() if s.fire)


def _quiet(twin, who):
    other = 'human' if who == 'jeff' else 'jeff'
    if any(getattr(twin, 'manual', {}).get(other, (0.0, 0.0))):
        twin.set_manual(other, 0, 0)
    return twin


class _Waiting:
    """The waiting fork, played forward as far as an option's step needs: Jeff starts nothing."""

    def __init__(self, kitchen, who):
        import links
        self.twin = _quiet(links._fork(kitchen), who)
        self.start = self.twin.time
        self.seen = [self._summary()]

    def _summary(self):
        return {'heat': _heat(self.twin), 'blocked': _blocked(self.twin), 'fires': _fires(self.twin)}

    def at(self, seconds):
        n = max(0, round(seconds / STEP))
        while len(self.seen) <= n and not self.twin.ended:
            self.twin.advance(STEP)
            self.seen.append(self._summary())
        return self.seen[min(n, len(self.seen) - 1)]


def carried_out(kitchen, who, option, place=None):
    """(the option's fork after its step ends, the station its first put lands on or None), or None when the option
    cannot be carried out to its end."""
    import links
    import one_press
    if option.kind in NO_STEP:
        return None
    twin = _quiet(links._fork(kitchen), who)
    put_at = None
    if option.kind in one_press.KINDS:
        rest = one_press.steps(option, twin)
        first = 'put' if twin.chefs[who].hand is not None else one_press.find(twin, who, rest[0])
        if first == 'put':
            action, _ = one_press.place(twin.actions(who), place)
            put_at = action.target if action is not None else None
        else:
            rest = rest[1:]
    else:
        first, rest = option, []
    if first is None or not links._carry_out(twin, who, first, rest, place):
        return None
    return twin, put_at


def _money(names, twin, start, base, who, option, held):
    parts = []
    for e in twin.events[start:]:
        kind = e.get('kind')
        if e.get('actor') != who:
            continue
        if kind == 'served':
            paid = e.get('price', 0) + e.get('adjustment', 0)
            parts.append(f"serves {e.get('order_id')} ({english_text(twin.recipe_name(e.get('dish')))}): "
                         f"{'+' if paid >= 0 else ''}{paid}")
        elif kind == 'wrong_dish':
            parts.append(f"no order waits for {english_text(twin.recipe_name(e.get('dish')))}: "
                         f"{twin.rules.penalty['wrong_dish']}")
        elif kind == 'dish_rejected':
            parts.append(f"{e.get('order_id')} refuses the dish, burnt too long, and keeps waiting")
    if option.kind == 'discard' and held is not None and held.plate_id:
        parts.append(f"throws away {names.food(twin, held)}, the plate stays in hand, dirty: {twin.rules.penalty['discard']}")
    elif option.kind == 'discard' and held is not None:
        parts.append(f"throws away {names.food(twin, held)}: {twin.rules.penalty['discard']}")
    elif option.kind == 'empty_pot' and held is not None and held.contents is not None:
        parts.append(f"throws away {names.food(twin, held.contents)}: {twin.rules.penalty['discard']}")
    for key in sorted(_fires(twin) - base['fires']):
        parts.append(f"{names.station(key)} catches fire: {twin.rules.penalty['new_fire']}")
    return parts


def _heat_parts(names, twin, base, skip):
    parts = []
    now, then = _heat(twin), base['heat']
    for item, (key, heating, heated, stage, ingredient) in now.items():
        before = then.get(item)
        if key == skip or not heating or (before and before[1]):
            continue
        ready, burn, fire = twin.rules.heat_thresholds(ingredient)
        food, stove = names.food(twin, twin.stations[key].food), names.station(key)
        burns = (f'it burns and {stove} catches fire in {max(0.0, burn - heated):.1f} s' if fire - burn < STEP else
                 f'it burns in {max(0.0, burn - heated):.1f} s and {stove} catches fire in {max(0.0, fire - heated):.1f} s')
        if stage == 'cooking':
            parts.append(f'{food} starts cooking on {stove}: cooked in {max(0.0, ready - heated):.1f} s, {burns}')
        elif stage == 'ready':
            parts.append(f'{food} heats again on {stove}: {burns}')
    for item, (key, heating, heated, stage, ingredient) in then.items():
        if key != skip and heating and stage in ('cooking', 'ready') and not (now.get(item) and now[item][1]):
            parts.append(f'{ingredient} ({"cooking" if stage == "cooking" else "cooked"}) stops heating')
    return parts


def _supply_parts(names, twin, base, skip):
    parts = []
    now, then = _blocked(twin), base['blocked']
    for key, item in now.items():
        if key != skip and key not in then:
            parts.append(f'{names.station(key)} gives no {twin.ingredients[key]} while {names.food(twin, item)} lies on it')
    for key in then:
        if key != skip and key not in now:
            parts.append(f'{names.station(key)} gives {twin.ingredients[key]} again')
    return parts


def notes(kitchen, who, actions, keys, payload=None, place=None):
    """{option key: note} for the listed options whose step has a direct result."""
    import food_names
    by_key = {a.key: a for a in actions}
    names = _Names(payload, kitchen)
    waiting = None
    out = {}
    held = kitchen.chefs[who].hand
    for key in keys:
        option = by_key.get(key)
        if option is None or option.kind in NO_STEP:
            continue
        done = carried_out(kitchen, who, option, place)
        if done is None:
            continue
        twin, put_at = done
        if waiting is None:
            waiting = _Waiting(kitchen, who)
        base = waiting.at(twin.time - kitchen.time)
        with food_names.naming():
            parts = (_money(names, twin, len(kitchen.events), base, who, option, held)
                     + _heat_parts(names, twin, base, put_at) + _supply_parts(names, twin, base, put_at))
        if parts:
            out[key] = ' (Result: ' + '; '.join(parts) + ')'
    return out


def apply(payload, kitchen, who, actions):
    """What the option_effects switch adds to an English request: the notes, rules.effects and the version."""
    criteria = payload['questions']['next_action']['criteria']
    found = notes(kitchen, who, actions, list(criteria), payload)
    for key, text in found.items():
        criteria[key] += text
    payload['state']['rules']['effects'] = RULE
    payload['state']['option_effects_version'] = VERSION
    return found

