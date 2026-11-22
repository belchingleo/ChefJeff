"""servability-v1: burnt food says whether a dish with it is still accepted, the same on every level (released, no
switch; 2026-11-22).

The burnt-food scoring (the ruleset's burnt_service tiers) accepts a dish whose worst heated component has been burnt
up to a tier's limit, at that tier's price change, and refuses one burnt longer: no payment, the dish is lost and the
order keeps waiting. The burnt time runs while the food stays on a stove, burning or not, and stops when it leaves
the stove (Rules.overcook). Before this the state said only that food was burnt ("beef (burnt)", and with the
kitchen view how long), and the options that plate, serve or lift it said nothing of the tier, so a pan burnt past
the limit read the same as one still accepted.

The engine works the tier out (Kitchen.burnt_service, which Kitchen._serve reads when a dish is served to the order
waiting for it, Kitchen.waiting_order):

- the food's text in the kitchen state Jeff reads (each burnt food's meaning in the plain state, which the kitchen
  view also shows) says it: "beef (burnt; accepted at -10 yuan for 2.1 s more while on the stove)" on a stove, where
  the burnt time runs, "beef (burnt; accepted at -10 yuan)" off it, "beef (burnt too long; refused)" (apply). Items
  in the air keep only their stage in the plain state; the kitchen view names them with the tier (request_parts);
- the engine's labels of a step that plates burnt food or picks it up end with the tier the dish would be in
  (Kitchen.burnt_note, translated by the language catalog, or this module's label_note where the engine writes its
  own English). Off a stove, where the burnt time stands still: " (burnt food: accepted at -10 yuan)" or " (burnt
  food: refused)", and " (it holds burnt food: ...)" for a pan (plating from a pan or onto a plate, filling the
  other chef's plate, taking it from a counter, picking it up from the floor, swapping a held pan with a counter's
  pan of it). A step that takes it off a stove (plating from it, lifting its pan, swapping a held pan with its pan)
  gives the tier as the step leaves it, the burnt time running on through the step's walk and handling
  (Kitchen.step_service): " (burnt food: accepted at -10 yuan if this starts within 1.6 s)", " (burnt food: refused,
  burnt too long by the time it is plated)", " (it holds burnt food: refused, burnt too long by the time it is
  lifted)" (for a swap: "by the time the swap takes it off the stove"); the one-press put-then-lift, whose put comes
  first, gives it as it is now (" (it holds burnt food: accepted at -10 yuan for 2.1 s more while on the stove)");
- every seconds figure is rounded down to the tenth (tenths), so "for X s more" and "within X s" never give more time
  than the engine does, and on a stove that heats at the standard rate the kitchen view's burnt time (rounded up) and
  the seconds left never add up to more than the tier's limit. Under a tenth, a step says " (burnt food: accepted at -10 yuan only if this starts now)" and food
  on a stove "accepted at -10 yuan for under 0.1 s more while on the stove". A step's seconds count its walk on a
  free route, as walk times do everywhere else in the request (Kitchen.step_gain): when the other chef stands in the
  way the walk takes longer, and a step started in time can end past the tier;
- the serve option of a held burnt dish says what serving it does now, as the serve step decides: with an order
  waiting for the dish, accepted at the tier's price change, or refused with no payment, the dish lost and the order
  still waiting; with none, the wrong-dish cost, whatever the tier (Kitchen.serve_label).

The player reads the same labels in Chinese. The links table and own_chain take their lines from the engine's labels
in their forks, so after lifting a pan the line "Fill the plate on Counter 1 from your frying pan" says the dish is
refused when, by the time the lift ends, it would be. These labels belong to the modules that write them (kitchen,
one_press, whose one-press-v7 gives the tier and whose v8 empty option gives it as the engine's take of the same pan
does, and the request's food_names and clear_names wording around them); what they say of the tier is this module's
version, state.servability_version. With the option_notes trial on, serve-note-v3 names no order for a dish the engine
refuses.

A chef's task, the events that carry such a label and the player's notice of Jeff's choice leave the tier out
(Kitchen.plain_action): it is true when the option is listed, and its seconds go stale after. Nothing here is per
level.
"""
from __future__ import annotations

import math
import re

VERSION = 'servability-v1'
BURNT = ' (burnt)'
# The engine's own English label note (label_note), for taking it off again (Kitchen.plain_action).
LABEL_NOTE = re.compile(r' \(burnt food: [^()]*\)$')


def tenths(seconds):
    """Seconds left in a tier as every label writes them: rounded down to the tenth of a second (past float noise),
    so "for X s more" and "within X s" never give more time than the engine does; 0.0 is under a tenth."""
    return math.floor(seconds * 10 + 1e-9) / 10


def accepted(status):
    """'accepted at -10 yuan', with the seconds left in the tier while the burnt time runs on a stove (tenths)."""
    text = f"accepted at -{-status['adjustment']} yuan"
    if status.get('left') is not None:
        left = tenths(status['left'])
        text += f" for {left:.1f} s more while on the stove" if left else ' for under 0.1 s more while on the stove'
    return text


def label_note(status):
    """The note after a label whose step plates this burnt food or lifts it (the English of Kitchen.burnt_note)."""
    if not status:
        return ''
    return ' (burnt food: refused)' if status['outcome'] == 'rejected' else f' (burnt food: {accepted(status)})'


def described(meaning, status):
    """A burnt food's name in the state with its tier: "beef (burnt)" -> "beef (burnt; accepted at -10 yuan)" or
    "beef (burnt too long; refused)"; a name that does not end in "(burnt)" ("burnt dish", "frying pan with ...")
    gets the tier after it."""
    if status['outcome'] == 'rejected':
        tier = 'burnt too long; refused'
        return meaning[:-len(BURNT)] + f' ({tier})' if meaning.endswith(BURNT) else meaning + f' ({tier})'
    if meaning.endswith(BURNT):
        return meaning[:-1] + '; ' + accepted(status) + ')'
    return meaning + f' ({accepted(status)})'


def apply(payload, kitchen):
    """Each burnt food in the request's kitchen state (on a station, in a chef's hands, on the floor; a pan's food and
    the pan itself) with its tier in its meaning, from the engine's kitchen at the same places (Kitchen.burnt_places);
    and the version. Runs on the finished English request, after the notes that read the state's names, before the
    request parts (jev.finish_payload), so the kitchen view shows it too."""
    state = payload['state']
    k = state.get('kitchen')
    if isinstance(k, dict):
        stations, chefs = k.get('stations') or {}, k.get('chefs') or {}
        ground = {g['food'].get('id'): g['food'] for g in k.get('ground') or []
                  if isinstance(g, dict) and isinstance(g.get('food'), dict)}
        for where, key, food, status in kitchen.burnt_places():
            entry = ((stations.get(key) or {}).get('food') if where == 'station' else
                     (chefs.get(key) or {}).get('holding') if where == 'chef' else ground.get(key))
            if not isinstance(entry, dict):
                continue
            inner = entry.get('contents')
            named = [inner, entry] if isinstance(inner, dict) else [entry]     # a pan's own name says what it holds
            if named[0].get('id') != food.id or named[0].get('stage') != 'burnt':
                continue
            for item in named:
                if isinstance(item.get('meaning'), str):
                    item['meaning'] = described(item['meaning'], status)
    state['servability_version'] = VERSION
    return payload
