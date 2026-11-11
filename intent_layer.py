"""The intent layer (features.json intent_layer, a trial, off by default, intent-v1): Jeff chooses a piece of work,
and the decision loop carries out its steps one after another without asking him in between.

Today each option Jeff reads is one engine action, and most of them name a place (walk to, put on, throw to). With
the switch on, each option is an intent: one piece of work, named as work, with where it is done.

- An engine action that already does a piece of work by itself stays one option with its own key and label
  (fetch beef, take b2, chop b1, put p1 for cooking, plate p1, serve, wash, take pot p1, extinguish, discard, ...).
  Each source, board, pan, plate and station is its own option, as today, so where an item comes from and where
  the work is done stay Jeff's choice. The engine's rule of listing only the nearest few empty counters per area
  stays.
- Walking stays an option for every station ("go X"), also where another option works at X, so he can walk to
  the pan and wait there (harness.model_candidates keep_go).
- Holding something, the steps the engine allows only one at a time become one option:
  "chop held <board>" (put the held food on that empty board, then chop it), "wash held <sink>" (put the held dirty
  plate in the sink, then wash it), and the one-press options (one_press.py: put then take, put then chop, put then
  wash, put then fetch, wash from the plate return), whose first put goes where questions.put_where says.
- The put places and the throws in a direction are no longer options of their own: "put down" puts the held item
  where put_where says (the same places as today), and "throw partner" stays. On a split floor the throws stay
  options as they are (not designed yet for this version).

Nothing here judges what he should do: the intents only chain the steps a player makes one after another, each
step is checked and started by the engine as if he had chosen it, and a step that cannot be done when it comes ends
the intent. No step fetches or takes an item for him, does a previous process step, or clears an occupied station.
The engine is unchanged; the decision loop (jev.DecisionLoop) runs the steps and decides when he is asked again.
"""
from __future__ import annotations

from kitchen import Action
from model_language import english_text
import one_press

VERSION = 'intent-v1'
KIND = 'intent'                 # an option's kind in the request; its first step and the rest are in expected
PLACE = 'intent_place'          # a put place, listed under questions.put_where
PUT = 'put'                     # a first step that puts the held item where put_where says
PUT_WHERE = one_press.PUT_WHERE
PLACES = one_press.PLACES       # put_counter, put_board, put_tool, drop
PRESSES = {name: True for name in one_press.NAMES}
END_REASONS = ('finished', 'step_not_possible', 'knocked', 'interrupted', 'replaced', 'round_ended')
RULE = ('Each option of next_action is an intent: one piece of work, and where it is done. The game carries out its '
        'steps one after another, as if you had chosen each of them (walking there, putting the held item where '
        'questions.put_where says when the intent says so, then the work), without asking you in between. You are '
        'asked again when the intent is finished, when one of its steps cannot be done, when the other chef knocks '
        'you away with a sprint (your progress is kept), when an order or a pan crosses a countdown band, or when '
        'the human chef sends a message; while an intent is under way, "continue" keeps it going and another option '
        'replaces it. "put down" puts the held item where put_where says. intent.current is the intent under way, '
        'intent.last how your previous intent ended.')
PUT_WHERE_RULE = ('Only if next_action is "put down" or an intent that first puts the held item: where the held item '
                  'goes. Otherwise it is not used.')


def flags(value):
    """Whether the switch is on (a bool)."""
    return bool(value)


def condition(on):
    """The intent_layer condition a round's start row carries; nothing when off."""
    return {'intent_layer': {'version': VERSION}} if on else {}


def _en(text):
    return english_text(text) if isinstance(text, str) else str(text)


def _intent(action, first, rest=(), key=None, label=None):
    return Action(key or action.key, label or action.label, KIND, action.target, (first, tuple(rest)))


def steps_of(option):
    """(first, rest) of an intent: the first step (an engine Action, or PUT) and the steps after it."""
    return option.expected


def options(kitchen, who, listed, names=False):
    """The intents for the actions the request would list (already filtered by harness.model_candidates), and the
    put places for put_where, as Actions of kind KIND and PLACE.

    listed must keep every "go X" (model_candidates keep_go); the rest of the engine's actions are read from
    kitchen.actions(who) where a chain needs a step the request does not list (the steps after the first)."""
    chef = kitchen.chefs[who]
    held = chef.hand
    out, places = [], []
    if chef.job is not None:
        # Asked while an intent is under way (an urgent band, a message): continuing comes first.
        cont = next((a for a in listed if a.kind == 'continue'), None)
        if cont is not None:
            out.append(_intent(cont, cont))
    held_name = _en(kitchen.food_name(held)) if held is not None else None
    for a in listed:
        if a.kind == 'continue':
            continue
        if a.kind in PLACES:
            places.append(Action(a.key, a.label, PLACE, a.target, a.expected))
            if a.kind == 'put_board' and held is not None and kitchen.rules.choppable(held) and not kitchen.stations[a.target].food:
                board = _en(kitchen.stations[a.target].name)
                work = max(0, kitchen.rules.chop_work(held.ingredient) - getattr(held, 'chopped', 0))
                out.append(_intent(a, a, [(('chop',), a.target)], key=f'chop held {a.target}',
                                   label=f'Chop the held {held_name} on {board}: put it there, then chop ({work:.1f}s)'))
            continue
        if a.kind == 'put_sink':
            sink = _en(kitchen.stations[a.target].name)
            out.append(_intent(a, a, [(('wash',), a.target)], key=f'wash held {a.target}',
                               label=f'Wash the held dirty plate in {sink}: put it in, then wash ({kitchen.wash_seconds:.1f}s)'))
            continue
        if a.kind == 'throw' and a.key != 'throw partner' and not getattr(kitchen, 'split_floor', False):
            continue
        out.append(_intent(a, a))
    if chef.job is None:
        for press in one_press.options(kitchen, who, listed, PRESSES):
            rest = one_press.steps(press, kitchen)
            if held is not None:
                first = PUT
            else:
                first, rest = one_press.find(kitchen, who, rest[0]), rest[1:]
                if first is None:
                    continue
            out.append(_intent(press, first, rest))
        if held is not None and places:
            out.append(Action('put down', f'Put down the held {held_name} where put_where says', KIND, '', (PUT, ())))
    if held is None or not any(o.expected[0] == PUT for o in out):
        places = []
    return out, places


def build(kitchen, who, per_area, spatial, names=False):
    """The request's intents and put places for this kitchen (a fork when asked ahead), in naming mode when the
    food_names switch is on, so the labels written here name food as the engine's own do."""
    import contextlib
    import food_names
    import harness
    with (food_names.naming() if names else contextlib.nullcontext()):
        actions = kitchen.actions(who)
        listed = harness.model_candidates(kitchen.snapshot(), actions, per_area, keep_go=True) if spatial else actions
        return options(kitchen, who, listed, names)


def place(kitchen, who, answer):
    """The put action put_where chose, among the engine's actions now, or the first put place (fallback)."""
    return one_press.place(kitchen.actions(who), answer)


def describe(chain, kitchen):
    """What a request says about an intent under way: its label, the step under way and how many there are."""
    return {'intent': chain['label'], 'step': chain['done_steps'] + 1, 'steps': chain['total'],
            'started_at': chain['started']}


def ended(record):
    """What a request says about how the previous intent ended (record is the decision loop's intent_end row)."""
    words = {'finished': 'finished', 'step_not_possible': 'a step could not be done',
             'knocked': 'the human chef knocked you away with a sprint; progress is kept',
             'interrupted': 'interrupted', 'replaced': 'replaced by your next choice', 'round_ended': 'the round ended'}
    out = {'intent': record['label'], 'result': words.get(record['reason'], record['reason']),
           'steps_done': record['steps_done'], 'steps': record['steps'], 'ended_at': record['t']}
    if record.get('step_not_possible'):
        out['stopped_at'] = record['step_not_possible']
    return out

