"""engine-english-v1 (trial, off): the engine writes the English Jeff reads for the strings the catalog garbles.

With the switch off every request is byte-identical to the one before the switch existed: scripted rounds of
levels 1-4 compose requests with no switch, the released switches and every trial switch, and their digests are
compared with the ones recorded at b021713 (tests/golden/engine-english-off.json; ``python3
tests/test_engine_english.py --record`` rewrites it, only for an intended change to Jeff's input). Rewritten once since,
for clear-names-v2: the every_trial requests (clear_names on) differ from b021713 only in clear_names_version, the
dropped-ahead notes of recent_decisions and chef tasks (and continue labels quoting them) naming the item; the plain
and released ones are b021713's. Rewritten again for clear-names-v3 and plate-names-v1 (every_trial now has plate_names
on): the every_trial requests differ from aaf945d only in the two version fields, events of steps that add food to a
plate or pick an item up naming that item (v3), and plating labels and chef tasks naming the plate there or in hand.
Rewritten once more when backlog_note was removed: the level-4 every_trial requests lose state.backlog and its version
and are otherwise the same; for step-check-v2, whose fetching sentence is all they gain (with the version); and for
undo-note-v2, whose version field is all that changes; and for burn-note-v3 and undo-note-v3: the two versions, and the
options that put a held pan of cooked food on a stove say when it burns; and for step-check-v3, whose version field is
all that changes in these rounds; and for serve-note-v2: its version, the take options of a Steak lying on a counter in
level 1 and the serve line the links table gives one of them; and for undo-note-v4, whose version field is all that
changes (these requests carry no step history); and for rules-v15, whose tableware rule and rules_version change in
every request: in level 1 Jeff takes the drying rack's plate at the sink where he stands, so that option's walk is
0.0 s (was 0.2 s), and the requests from 54 to 64 s differ in positions, event times and a few options (at 60 s the
player, who took the rack's plate at the sink, is at the sink, no longer at the rack); from 66 s on they are as before.
Rewritten again for rules-v15's burnt and fire rules (engine semantics continuous-2026-11): every request's score and
fire rules and its config_hash change; in levels 2 and 3 the beef that burns on Stove 1 keeps heating while the stove
burns (heating true, heat_elapsed running on from 20.0); in level 3 the fire spreading to Stove 2 leaves its beef
cooked (it was burnt), and it waits there. Rewritten once more when the fire rule said that food still cooking when a
fire reaches its stove cooks on until it is cooked (every request's fire rule), and for burn-note-v4: its version, the
take option of Stove 2's pan in that level-3 request, which says the beef waits until the fire on Stove 2 is out (v3
gave when it burns), and the first request's go option to Stove 1, whose cooked beef the scripted round puts there
without heating it, which gets no note (v3 gave when it burns). Rewritten again when the fire rule said that food put
on a burning stove waits whether its pot is put there or the food is put or thrown into its pot, and the swap rule
that a pot can be lifted, put back or swapped on a burning stove (it said the stove had to be put out first): those two
rules are all that change, in every request. Rewritten again for servability-v1 (released): its version field in every
request; in the 24 level-2 and level-3 requests with burnt beef on Stove 1 (8 per combination), that beef's meaning
and the lift option of its pan say its tier ("beef (burnt; accepted at -10 yuan for 2.9 s more while on the stove)",
"beef (burnt too long; refused)", "Burnt (accepted at ...)" with names off), and the lift label ends with the tier the
lift leaves the pan in, its walk counted (" (it holds burnt food: accepted at -10 yuan if this starts within 0.6 s)",
" (it holds burnt food: refused, burnt too long by the time it is lifted)"). Rewritten once more for one-press-v7 and
serve-note-v3, whose version fields are all that change here: every seconds figure in these rounds falls on a tenth of
a second, so rounding them down (servability.tenths) changes none, and no option there serves or picks up a dish
the engine refuses. Rewritten again for one-press-v8, which adds "empty <station>": in the released and every_trial
requests the one_press rule (it describes the new option), the put_where question's instructions (they name "empty"
actions too) and one_press_version change, and no request in these rounds lists the new option. With it, the engine
lists the second bin's discard for a chef whose part of a split floor has only that bin: the level-4 player now has
"discard bin2" while holding food, so the greedy policy's seeded draws for the player go differently, and the level-4
requests differ from 22 s on (plain ones too); levels 1 to 3 keep their plain requests. Rewritten again for
partner-links-v4: only the every_trial requests that carry the links table (every 10th, five per level) change, through
the partner links' version and the partner lines that now first free the other chef's hands; plain and released are
as before. Rewritten again for throw-rest-v1 (a throw with no free tile where it comes down rests on the nearest free
floor tile instead of being refused): levels 1 to 3 are unchanged; in level 4 a throw that used to be refused is listed
from 30 s on and the scripted round plays on differently, so the level-4 requests from the 16th on differ in all three
combinations. Rewritten again for burn-note-v6: every_trial requests carry its version, and the options on a stove whose
food is still cooking carry no note; plain and released are as before. Rewritten again for partner-links-v5 (a partner
line only for work at a place the chef cannot reach itself): only the every_trial requests that carry the links table
(every 10th, five per level) change, through the partner links' version and rule and the partner lines they drop;
plain and released are as before.
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_contract as cc  # noqa: E402
import engine_english  # noqa: E402
import fingerprint  # noqa: E402
import one_press  # noqa: E402
import research_record as rr  # noqa: E402
import research_replay  # noqa: E402
from jev import DecisionLoop, compose_payload  # noqa: E402
from kitchen import Action, Food, GroundItem  # noqa: E402
from model_language import english_text  # noqa: E402
from research_record import validate_record  # noqa: E402
from spatial_kitchen import tile_key  # noqa: E402
import test_research_save_paths as paths  # noqa: E402
from spatial_kitchen import SpatialKitchen  # noqa: E402
from whitebox_server import SpatialJevClient  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / 'golden' / 'engine-english-off.json'
# level id, policy seed, policy (tests/fingerprint.py), seconds of play
ROUNDS = {'level1': ('level-1', 11, 'greedy', 90), 'level2': ('level-2', 12, 'greedy', 90),
          'level3': ('level-3', 13, 'greedy', 90), 'level4': ('level-4', 14, 'greedy', 90)}
ASK_EVERY = 40      # steps of 0.05 s between requests (2 game seconds)
LINKS_EVERY = 10    # the links table on every 10th request only (it takes a few tenths of a second)
# The loop's own result notes, as they reach recent_decisions today.
DECISIONS = [{'t': 1.0, 'choice': 'wait', 'accepted': True, 'result': '等待', 'sprint_applied': False},
             {'t': 2.0, 'choice': 'wait', 'accepted': False, 'result': '提前问的回复作废（已暂停或本局结束），马上重问',
              'sprint_applied': False},
             {'t': 3.0, 'choice': 'wait', 'accepted': False, 'result': '提前问的回复作废（not_listed），马上重问',
              'sprint_applied': False},
             {'t': 4.0, 'choice': 'put then take counter1', 'accepted': False, 'result': '一键操作的第一步现在做不了',
              'sprint_applied': False},
             {'t': 5.0, 'choice': 'wait', 'accepted': False, 'result': '这个意图的第一步现在做不了',
              'sprint_applied': False}]


def released():
    return {'one_press': one_press.flags({name: True for name in one_press.NAMES}), 'names': True, 'links': True}


def every_trial():
    return {'one_press': one_press.flags({name: True for name in one_press.NAMES}),
            'undo': {'history': []}, 'reach': True, 'names': True, 'links': 'partner', 'split': True,
            'burn': True, 'serve_note': True, 'steps': True, 'clear': True,
            'walk': True, 'plate': True}


COMBOS = {'plain': lambda: {}, 'released': released, 'every_trial': every_trial}


class Round:
    """A scripted round: the plating the catalog garbles staged first (a pan lifted to a counter and plated from
    there, once stopped part-way, then a pan on the floor plated), then both chefs on tests/fingerprint.py's
    policy. Jeff's request is composed every ASK_EVERY steps with each switch combination."""

    def __init__(self, name, **extra):
        self.name, self.extra = name, extra
        level, seed, self.policy, self.seconds = ROUNDS[name]
        self.k = SpatialKitchen(cc.load_level(level))
        self.client = SpatialJevClient(self.k.c, key='engine-english-no-credential')
        self.rng = random.Random(seed)
        self.step = self.n = 0
        self.out = []

    def tick(self):
        k = self.k
        if self.step % ASK_EVERY == 0:
            for combo, switches in COMBOS.items():
                options = switches()
                if self.n % LINKS_EVERY:
                    options.pop('links', None)
                payload = compose_payload(self.client, k, k.snapshot(), k.actions('jeff'),
                                          [dict(d) for d in DECISIONS], None, **options, **self.extra)
                self.out.append((combo, self.n, payload))
            self.n += 1
        k.advance(fingerprint.STEP)
        self.step += 1

    def find(self, who, kind=None, key=None):
        action = next((a for a in self.k.actions(who) if (key is None or a.key == key)
                       and (kind is None or a.kind == kind)), None)
        assert action is not None, (self.name, who, kind, key, [a.key for a in self.k.actions(who)])
        return action

    def do(self, who, kind=None, key=None, stop_after=None):
        action = self.find(who, kind, key)
        self.k.start(who, action)
        if stop_after is not None:
            for _ in range(stop_after):
                self.tick()
            self.k.stop(who)
            self.tick()
            action = self.find(who, kind, action.key)
            self.k.start(who, action)
        while self.k.chefs[who].job is not None:
            self.tick()
        return action

    def stage(self):
        k = self.k
        stove = k.pots[0]
        pan = k.stations[stove].pot_id
        k.stations[stove].food = Food('F90', 'ready', ingredient='beef')
        self.do('jeff', 'lift_pot', f'take pot {stove}')
        counter = self.do('jeff', 'put_counter').target
        self.do('jeff', 'take_plate')
        self.do('jeff', 'plate_from_counter', f'plate {counter}', stop_after=4)
        self.do('jeff', 'serve' if any(a.kind == 'serve' for a in k.actions('jeff')) else 'put_counter')
        k.stations[counter].food.contents = Food('F91', 'ready', ingredient='beef')
        self.do('jeff', 'take_counter', f'take {counter}')
        self.do('jeff', 'drop')
        # The floor pan is plated by the human where the human can take a plate and reach it (not on level 4).
        plater = 'human' if any(a.key == f'plate ground {pan}' for a in self._with_plate('human')) else 'jeff'
        if plater == 'jeff':
            self.do('jeff', 'take_plate')
        self.do(plater, 'plate_ground', f'plate ground {pan}', stop_after=2)

    def _with_plate(self, who):
        if self.k.chefs[who].hand is None and any(a.kind == 'take_plate' for a in self.k.actions(who)):
            self.do(who, 'take_plate')
        return self.k.actions(who)

    def play(self):
        self.stage()
        k = self.k
        while not k.ended and k.time < self.seconds:
            if self.step % fingerprint.DECIDE_EVERY == 0:
                for who in ('human', 'jeff'):
                    action = fingerprint.choose(k, who, self.rng, self.policy)
                    if action:
                        k.start(who, action)
            self.tick()
        return self


def requests(name, **extra):
    """(combo, request number, payload) for every request of the scripted round, extra switches added to each."""
    return Round(name, **extra).play().out


def digests(**extra):
    return {name: {f'{combo}/{n}': cc.sha256(payload) for combo, n, payload in requests(name, **extra)}
            for name in ROUNDS}


CJK = re.compile(r'[\u3000-\u303f\u3400-\u9fff\uff00-\uffef]')
ZH = {'pan': '平底锅', 'pot': '汤锅', 'wok': '锅'}
EN = {'pan': 'frying pan', 'pot': 'soup pot', 'wok': 'pot'}


def plating(kind='pan'):
    """Level 3: Jeff holds a clean plate; the pan on Counter 4 (P3) holds cooked beef, and so does P1, lifted off
    Stove 1 and left on the floor beside him. kind: what P1 and P3 are (pan, a soup pot, or a kind no recipe has)."""
    k = SpatialKitchen(cc.load_level('level-3'))
    for vessel in ('P1', 'P3'):
        k.rules.vessels[vessel] = kind
    k.stations['counter4'].food.contents = Food('F90', 'ready', ingredient='beef')
    k.chefs['jeff'].hand, k.stations['plates'].food = k.stations['plates'].food, None
    k.stations['p1'].pot_id = None
    k.ground['P1'] = GroundItem(Food('P1', 'pot', contents=Food('F91', 'ready', ingredient='beef')),
                                tile_key(k.drop_cell('jeff')))
    return k


def find(k, who, key):
    return next(a for a in k.actions(who) if a.key == key)


def finish(k, who):
    while k.chefs[who].job is not None:
        k.advance(.05)


def ask(k, *, english, **switches):
    client = SpatialJevClient(k.c, key='engine-english-no-credential')
    return compose_payload(client, k, k.snapshot(), k.actions('jeff'), switches.pop('decisions', []), None,
                           english=english, **switches)


def played():
    """plating(): Jeff plates from Counter 4, stopped once part-way, then from the floor."""
    k = plating()
    k.start('jeff', find(k, 'jeff', 'plate counter4'))
    k.advance(.1)
    k.stop('jeff')
    k.start('jeff', find(k, 'jeff', 'plate counter4'))
    finish(k, 'jeff')
    k.chefs['jeff'].hand = Food('D9', 'clean_plate')
    k.start('jeff', find(k, 'jeff', 'plate ground P1'))
    return k


def loop_notes(english):
    """The decision loop's recent_decisions and notices after the three notes: an answer asked ahead dropped (once
    paused, once not listed) and a one-press choice whose first step cannot be done now."""
    from test_walk_and_pickup import floor_beef_and_lettuce_in_hand
    k = floor_beef_and_lettuce_in_hand()
    notices = []
    loop = DecisionLoop(k, SpatialJevClient(k.c, key='engine-english-no-credential'), lambda kind, data: None,
                        notices.append)
    loop.english = english
    loop.send = lambda *args: None        # no request leaves the test
    flags = one_press.flags({name: True for name in one_press.NAMES})
    loop.one_press = flags
    wait = find(k, 'jeff', 'wait')
    press = one_press.options(k, 'jeff', k.actions('jeff'), flags)[0]
    clock = [100.0]

    def reply(decision, **context):
        loop.q.put(({'id': loop.calls, 'sent': clock[0], 'epoch': loop.epoch, 'job_id': None,
                     'actions': {decision.key: decision}, 'decision': decision, **context},
                    {'choice': decision.key, 'sprint': False, 'confidence': None, 'probabilities': {},
                     'model': 'test-only', 'usage': {}, 'latency': 0.1}, None))
        clock[0] += 1
        with patch('jev.time.monotonic', lambda: clock[0]):
            loop.poll()

    with patch('jev.time.monotonic', lambda: clock[0]):
        loop.q.put(({'id': 0, 'sent': clock[0], 'epoch': loop.epoch, 'job_id': None, 'actions': {'wait': wait},
                     'decision': wait, 'ahead': {'job_id': 1}, 'ahead_check': None},
                    {'choice': 'wait', 'sprint': False, 'confidence': None, 'probabilities': {}, 'model': 'test-only',
                     'usage': {}, 'latency': 0.1}, None))
        loop.poll(enabled=False)                      # paused: the answer asked ahead is dropped
    reply(wait, ahead={'job_id': 1}, ahead_check='not_listed')
    with patch('one_press.place', lambda actions, where: (None, False)):
        reply(press)
    return loop.recent_decisions, notices


class LabelTests(unittest.TestCase):
    def test_plating_labels_in_english_by_the_vessels_kind_and_the_chinese_as_before(self):
        for kind in ('pan', 'pot', 'wok'):
            k = plating(kind)
            counter, ground = find(k, 'jeff', 'plate counter4'), find(k, 'jeff', 'plate ground P1')
            self.assertEqual(counter.label, f'用手中的盘盛出柜台 4的{ZH[kind]}里的菜')
            self.assertEqual(ground.label, f'用手中的干净盘盛出地上{ZH[kind]}里的菜（空{ZH[kind]}留在原地）')
            self.assertEqual(counter.english, f'Plate food from the {EN[kind]} on Counter 4')
            self.assertEqual(ground.english, f'Plate food from the {EN[kind]} on the floor (empty {EN[kind]} stays in place)')
            # Not compared and not shown: the action is the same action, and prints as before.
            self.assertEqual(counter, Action(counter.key, counter.label, counter.kind, counter.target, counter.expected))
            self.assertNotIn('english', repr(counter))
            self.assertEqual(k.vessel_english('P1'), EN[kind])

    def test_the_request_takes_them_only_with_the_switch_on(self):
        k = plating()
        for english in (False, True):
            payload = ask(k, english=english, names=True)
            criteria = payload['questions']['next_action']['criteria']
            if english:
                self.assertEqual(criteria['plate counter4'], 'Plate food from the frying pan on Counter 4')
                self.assertEqual(criteria['plate ground P1'],
                                 'Plate food from the frying pan on the floor (empty frying pan stays in place)')
                self.assertEqual(payload['state']['engine_english_version'], engine_english.VERSION)
            else:
                self.assertEqual(criteria['plate counter4'], 'Plate food from the pot on Counter 4的平底')
                self.assertEqual(criteria['plate ground P1'],
                                 'Plate food from 地上frying pan里 (the empty frying pan stays in place)')
                self.assertNotIn('engine_english_version', payload['state'])

    def test_the_links_table_carries_them_too(self):
        k = plating()
        payload = ask(k, english=True, names=True, links=True)
        self.assertIsNone(CJK.search(json.dumps(payload['state'].get('option_links'), ensure_ascii=False)))
        counter = find(k, 'jeff', 'plate counter4')
        with engine_english.writing():
            self.assertEqual(engine_english.label(counter), 'Plate food from the frying pan on Counter 4')
        self.assertEqual(engine_english.label(counter), counter.label)       # off outside writing()


class EventTests(unittest.TestCase):
    def test_started_stopped_and_completed_in_english_beside_the_engines_events(self):
        k = played()
        k.advance(.1)
        travel = [e for e in k.events if e.get('kind') == 'action_start'][0]['message'].split('路程 ')[1].split('s')[0]
        english = [k.english_events[e['seq']] for e in k.events if e['seq'] in k.english_events]
        self.assertEqual(english[:4], [
            f'jeff started: Plate food from the frying pan on Counter 4 (travel {travel}s + work 0.0s)',
            'jeff stopped: Plate food from the frying pan on Counter 4',
            english[2],
            'jeff completed: Plate food from the frying pan on Counter 4'])
        self.assertTrue(english[2].startswith('jeff started: Plate food from the frying pan on Counter 4 (travel '))
        self.assertTrue(english[4].startswith('jeff started: Plate food from the frying pan on the floor '
                                              '(empty frying pan stays in place) (travel '))
        # The engine's events are as before: Chinese, and nothing added to them.
        self.assertTrue(all('english' not in e for e in k.events))
        self.assertTrue(all(CJK.search(e['message']) for e in k.events if e['seq'] in k.english_events))
        payload = ask(k, english=True, names=True)
        shown = [e['message'] for e in payload['state']['recent_events']]
        self.assertEqual([m for m in shown if 'Plate' in m], english)
        self.assertEqual(payload['state']['kitchen']['chefs']['jeff']['task'],
                         'Plate food from the frying pan on the floor (empty frying pan stays in place)')
        self.assertEqual(rr.state(k), rr.state(k))
        off = ask(k, english=False, names=True)
        self.assertEqual([e['message'] for e in off['state']['recent_events']],
                         [english_text(e['message']) for e in k.events
                          if e.get('kind') not in ('manual_move', 'position_resync')][-20:])

    def test_a_partner_completing_together_and_a_replayed_action_without_english(self):
        k = SpatialKitchen(cc.load_level('level-1'))
        board = k.boards[0]
        k.stations[board].food = Food('F95', 'raw', ingredient='beef')
        chop = replace_english(find(k, 'jeff', f'chop {board}'), 'Chop beef (as fetched) F95')
        k.start('jeff', chop)
        while not k.chefs['jeff'].job.working:
            k.advance(.05)
        join = find(k, 'human', f'chop {board}')
        k.start('human', replace_english(join, 'Join chopping beef (as fetched) F95'))
        finish(k, 'jeff')
        finish(k, 'human')
        done = [k.english_events.get(e['seq']) for e in k.events if e.get('kind') == 'action_done']
        self.assertEqual(done, ['human completed: Join chopping beef (as fetched) F95',
                                'jeff completed together: Chop beef (as fetched) F95'])
        # An action as a record replays it (no English): the engine's own listing gives the English.
        k = plating()
        listed = find(k, 'jeff', 'plate counter4')
        k.start('jeff', Action(listed.key, listed.label, listed.kind, listed.target, listed.expected))
        self.assertEqual(k.chefs['jeff'].job.action.english, listed.english)
        self.assertTrue(k.english_events[k.events[-1]['seq']].startswith('jeff started: Plate food from the frying pan'))

    def test_a_fork_keeps_its_own(self):
        k = played()
        twin = k.fork()
        finish(twin, 'jeff')
        self.assertGreater(len(twin.english_events), len(k.english_events))
        self.assertTrue(set(k.english_events) < set(twin.english_events))


def replace_english(action, english):
    from dataclasses import replace
    return replace(action, english=english)


class LoopNoteTests(unittest.TestCase):
    def test_the_loops_own_notes_reach_jeff_in_english_and_the_player_reads_chinese(self):
        decisions, notices = loop_notes(True)
        self.assertEqual([d['result'] for d in decisions], [
            'the answer asked ahead was dropped (paused, or the round ended); asked again at once',
            'the answer asked ahead was dropped (not_listed); asked again at once',
            'the first step of this one-press choice cannot be done now'])
        self.assertTrue(all(CJK.search(n) for n in notices))
        self.assertIn('未执行：一键操作的第一步现在做不了', notices[-1])
        decisions, _ = loop_notes(False)
        self.assertEqual([d['result'] for d in decisions], [
            '提前问的回复作废（已暂停或本局结束），马上重问', '提前问的回复作废（not_listed），马上重问',
            '一键操作的第一步现在做不了'])


class OffIsByteIdenticalTests(unittest.TestCase):
    def test_requests_with_the_switch_off_match_the_digests_from_before_it(self):
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(digests(), golden)

    def test_with_the_switch_on_the_staged_plating_reaches_jeff_in_english(self):
        r = Round('level4', english=True).play()
        text = [json.dumps(p['questions'], ensure_ascii=False) + json.dumps(p['state']['recent_events'], ensure_ascii=False)
                for _, _, p in r.out]
        self.assertTrue(any('jeff stopped: Plate food from the frying pan on Counter 4' in t for t in text))
        self.assertFalse(any(CJK.search(t) for t in text))


if __name__ == '__main__':
    if '--record' in sys.argv:
        GOLDEN.write_text(json.dumps(digests(), indent=1, sort_keys=True) + '\n', encoding='utf-8')
        print('written', GOLDEN)
    else:
        unittest.main()
