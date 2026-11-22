"""Byte-level fingerprints of Jeff's model input, for refactors that must not change it.

Each scenario plays a level's fixed round. The human chef follows the recipe
reference policy; Jeff is driven by the real ``DecisionLoop`` with a scripted
stand-in model (no network, no key), on a clock that follows game time, so
every request is reproducible. For each request we record the hash of:

- the payload as the model is sent it (``harness.for_model`` of what ``compose_payload``
  builds and the loop logs: no version tags since 2026-11-20; the online version relays
  the same to the browser), and of each of its sections;
- on every 4th request, the exact request body every client would send: local
  Jev, decision and chat presets, and the online server's Jev and free-model
  forwarders. The bodies are fixed transforms of the payload, so a change to how
  any client builds them shows on every sampled request.

``python3 tests/payload_fingerprint.py --update`` rewrites the golden files;
do that only for an intended, reviewed change to Jeff's input and say why in
the commit message. The browser's own request builder (hosted/browser-agent.js)
and the online memory insertion are not covered here. Each scenario clears the
navigation cache first, as a freshly started server would have it.

The scenarios leave the links table (option_links, released) off and every trial
switch at features.json's value. The switch sets (SWITCH_SETS, on SWITCH_LEVELS)
cover those: the release as written (links table on); the local play set (every
trial on but timeline and no_history); the local set with the links table off;
every feature on; every feature on but no_history, the only set with the timeline
(no_history wins over it); and the release with option_links_partner, the only set
with the separate links table's partner lines. Their decision loop gets its
switches from a started session (web_server.GameSession), so a change to how a
round wires them shows here too. Level 2 is played with the recipe roles; on level
5's split floor both chefs play zoned (ZONED), so Jeff takes, passes and throws
items there. The checked-in test plays a few sampled kitchen states per set
(SAMPLES: the level's policy plays both chefs up to a game time, then Jeff's loop
makes a few requests); request bodies are sampled on the release set only.

    python3 tests/payload_fingerprint.py --switches [--update]
    python3 tests/payload_fingerprint.py --switches --full [--update] [LEVEL] [SET]

check (or rewrite) the sampled sets, or play whole rounds instead (several minutes
a set, goldens in golden/payload-switches/full; a full run takes request bodies on
every FULL_WIRE_EVERY-th request of the release set). The sampled test reaches
fewer note branches than the whole rounds, so a change to how the request is put
together (jev.compose_payload and finish_payload, harness.compose, request_parts,
links, one_press and the note modules) must give the same `--switches --full`
result before and after it, and pass the checked-in test.

Checked on 2026-11-22 against the text of every request each net sends, and with
one-character changes. What only the whole rounds reach: burn_note's COOKING note,
undo_note's "before your last N steps", option_notes' SERVE_NONE and LINK_FOR, and
plate_result's "(makes a <dish>; ...)" notes.
What neither net reaches, so a change there passes both:
- kitchen_view's "the stove catches fire in ...", which needs burnt food whose fire is still ahead when a request
  is composed (level 2's stove fire is already burning by then, in the requests from about 80 to 114 s), and
  plate_result's "(makes a burnt dish)", which needs a plate of burnt food (the policies never make one);
- burn_note HELD_COOKING (a pan still cooking in Jeff's hands);
- step_check's "The waiting orders need nothing that is chopped first.";
- undo_note's "this takes back the ..." (an option that takes back what Jeff put);
- option_notes SERVE_FOR (the held food goes to a waiting order);
- plate_result's "(the plate then makes no dish on the menu)" and "still needs
  ...; no waiting order asks for a ...";
- ask_ahead: replies come at once, so Jeff is never asked ahead (the
  level2-ask-ahead scenario covers it);
- clear_text off: it is on in every set, so every request is in English
  (tests/test_engine_english.py composes requests with it off).
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import pickle
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hosted_free_models  # noqa: E402
import jev  # noqa: E402
import engine_english  # noqa: E402
import features  # noqa: E402
import hosted_jev  # noqa: E402
import player_api  # noqa: E402
import reference_policy  # noqa: E402
import spatial_kitchen  # noqa: E402
from cooperation_memory import episode, memory_context  # noqa: E402
from jev import DecisionLoop  # noqa: E402
from kitchen import load_config  # noqa: E402
from levels import level_config  # noqa: E402
from round_summary import round_summary  # noqa: E402
from spatial_kitchen import SpatialKitchen  # noqa: E402
from web_server import GameSession, PLAYER_MESSAGES  # noqa: E402
from whitebox_server import SpatialJevClient  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / 'golden' / 'payloads'
STEP = .05          # same quantisation as the behaviour fingerprints
HUMAN_EVERY = 10    # human policy decision every 0.5 game seconds
WIRE_EVERY = 4      # request bodies of every client on every 4th request (they are fixed transforms of the payload)
SPEED = .75         # default game seconds per wall second; the loop's clock is wall time
KEY = 'payload-fingerprint-key'
WALL_TIME = '2026-11-03T12:00:00+08:00'
SCENARIOS = {
    # name: (level id, with player messages and cross-round memory). The plan scenarios went with the plan modes
    # (2026-11-20).
    'level1': ('level-1', False),
    'level2': ('level-2', False),
    'level3': ('level-3', False),
    'level2-messages-memory': ('level-2', True),
    'level2-ask-ahead': ('level-2', False),
    'level2-food-names': ('level-2', False),
}
# Scenarios with ask_ahead on (ask_ahead.py): replies take REPLY_SECONDS of wall time, so Jeff's steps end before
# some of them come and he is asked ahead.
AHEAD = {'level2-ask-ahead'}
REPLY_SECONDS = 1.2
# Scenarios with food_names on (food_names.py): every food named from its ingredient and state.
NAMES = {'level2-food-names'}
MESSAGES = ((20.0, 'prep'), (70.0, 'mistake'), (120.0, 'wash'))
COMPOSE = jev.compose_payload
FINISH = jev.finish_payload

GOLDEN_SWITCHES = Path(__file__).resolve().parent / 'golden' / 'payload-switches'
SWITCH_LEVELS = ('level-2', 'level-5')      # level 5 has the split floor
SWITCH_SETS = ('release', 'local', 'local-links-off', 'all', 'all-but-no-history', 'release-partner-links')
LOCAL_OFF = ('timeline', 'no_history')      # the two trials the local play set leaves off
# The features each set leaves off (release: as features.json has them). no_history wins over timeline, so only
# all-but-no-history has the timeline; release-partner-links is the only set with the separate links table's partner
# lines (option_links_partner on, links_on_options off).
SET_OFF = {'local': LOCAL_OFF, 'local-links-off': LOCAL_OFF + ('option_links',), 'all': (),
           'all-but-no-history': ('no_history',)}
ROLES = {'human': 'assembler', 'jeff': 'cook'}
# Levels the switch net plays zoned: on level 5's split floor each chef works the part of the floor they stand in
# (reference_policy.choose_zoned, as tests/fingerprint.py plays level4-zoned), so Jeff holds, passes and throws items.
# With the recipe roles there Jeff answers wait to every request. Other levels use the recipe roles.
ZONED = {'level-5'}
# The decision loop's switches, as a started round sets them (web_server.GameSession, /api/start).
LOOP_SWITCHES = ('one_press', 'ask_ahead', 'undo', 'reach', 'names', 'links', 'split', 'burn', 'serve_note', 'steps',
                 'clear', 'walk', 'go', 'english', 'plate', 'parts', 'work')
# The checked-in test's kitchen states per level: (game seconds the level's policy plays both chefs, requests Jeff's
# loop then makes). Chosen (2026-11-22) so that each trial switch that is off in features.json, on alone over the
# release set, changes some request on one of the levels: burn_note on level 2 only; throw_to, option_notes and the
# split-floor notes (reach_note, split_floor, step_check) on level 5 only. The release set's request bodies are sampled
# on the first request of window WIRE_WINDOW.
SAMPLES = {'level-2': ((0, 1), (10, 2), (50, 2)), 'level-5': ((30, 2), (110, 2), (150, 2))}
WIRE_WINDOW = 1
FULL_WIRE_EVERY = 40


def recipe_roles(k, who):
    """The recipe reference policy's move: the human assembles, Jeff cooks."""
    return reference_policy.choose(k, who, ROLES[who])


def zoned(k, who):
    """The zoned reference policy's move, for the side of the floor the chef stands on now."""
    return reference_policy.choose_zoned(k, who, reference_policy._cell_side(k, k.anchor(who)))


def policy(level):
    """How the switch net plays both chefs on a level."""
    return zoned if level in ZONED else recipe_roles


def h(value) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def frozen(values):
    """Independent copies of compose_payload's arguments (it may modify them), keeping the 'no memory' sentinel."""
    if isinstance(values, dict):
        return {k: frozen((v,))[0] for k, v in values.items()}
    return tuple(v if v is jev.NO_MEMORY else pickle.loads(pickle.dumps(v)) for v in values)


class Captured(Exception):
    """Raised in place of network I/O once the request body is in hand."""


def captured(send) -> bytes:
    box = []

    def grab(request, *_, **__):
        box.append(request.data)
        raise Captured()

    class Opener:
        open = staticmethod(grab)

    with patch('urllib.request.urlopen', grab), patch('urllib.request.build_opener', lambda *_, **__: Opener()):
        try:
            send()
        except Exception:  # every client wraps or re-raises transport errors; the body is already captured
            pass
    if not box:
        raise AssertionError('client sent nothing')
    return box[0]


def wire_clients(config):
    """name -> (client that builds its own payload or None, send(payload)).

    Local clients build the payload themselves (a client may add fields such as its
    model), from the same arguments the loop used. The online forwarders receive the
    payload the browser relay was given, which is the loop's own payload.
    """
    clients = {}
    for provider, preset in sorted(player_api.PROVIDERS.items()):
        model = next((m for m in preset.get('models') or [] if m), None) or 'payload-fingerprint-model'
        setting = {'provider': provider, 'base_url': preset.get('base_url') or 'https://example.invalid/v1',
                   'model': model, 'api_key': KEY,
                   **({'account_id': 'payload-fingerprint-account'} if preset.get('account_id') else {})}
        client = player_api.create_client(config, setting)
        clients['local:' + provider] = (client, client.ask)
    forwarder = hosted_jev.JevForwarder()
    clients['hosted:jev'] = (None, lambda payload: forwarder.send(KEY, payload))
    free = hosted_free_models.FreeModels.__new__(hosted_free_models.FreeModels)
    free.keys = {p: KEY for p in hosted_free_models.MODELS}
    free.endpoints = {p: m['endpoint'] for p, m in hosted_free_models.MODELS.items()}
    for provider in sorted(hosted_free_models.MODELS):
        clients['hosted:' + provider] = (None, lambda payload, p=provider: free.send(p, payload))
    return clients


class StandIn(SpatialJevClient):
    """Scripted stand-in model: the recipe policy's cook move when offered, otherwise wait."""

    def __init__(self, config, kitchen, wires, keep=None):
        super().__init__(config, key=KEY)
        self.k, self.wires, self.requests = kitchen, wires, []
        self.keep = keep        # a list to receive each payload whole (recorded), or None
        self.sections = {}
        self.arguments = None   # what the loop passed to compose_payload for this request
        self.sample = None      # the first payload, kept whole in the golden file
        self.wire_every = None  # request bodies on every wire_every-th request (WIRE_EVERY when None, none when 0)
        # With the links table on, the loop composes with defer=True and finishes the request in its own thread
        # (jev.finish_payload) on a fork, while the kitchen moves on: for a request whose bodies are sampled, the
        # kitchen as it was asked about (a fork), and what the loop passed to finish_payload.
        self.fork = None
        self.finishing = None
        self.choose = recipe_roles  # (kitchen, who) -> the move Jeff's answer follows when it is offered
        self.note_choice = False    # whether each row records the answer (the switch net's rows do)

    def sampled(self):
        """Whether the request being built now (the next one asked) has its request bodies sampled."""
        every = WIRE_EVERY if self.wire_every is None else self.wire_every
        return bool(self.wires) and bool(every) and len(self.requests) % every == 0

    def compose(self, client, kitchen, *arguments, **options):
        self.arguments = (kitchen, frozen(arguments), frozen(options))
        self.fork = kitchen.fork() if options.get('defer') and self.sampled() else None
        return COMPOSE(client, kitchen, *arguments, **options)

    def finish(self, payload, kitchen, actions, *arguments, **options):
        """jev.finish_payload, noting its other arguments and the engine_english setting it runs under."""
        self.finishing = (frozen(arguments), frozen(options), engine_english.ON.get())
        return FINISH(payload, kitchen, actions, *arguments, **options)

    def rebuilt(self, client):
        kitchen, arguments, options = self.arguments
        if not options.get('defer'):
            return COMPOSE(client, kitchen, *frozen(arguments), **frozen(options))
        # Deferred: composed and finished as the loop does it, on a fork of the kitchen asked about.
        twin = self.fork.fork()
        payload, actions = COMPOSE(client, twin, *frozen(arguments), **frozen(options))
        rest, named, english = self.finishing
        with engine_english.writing(english):
            return FINISH(payload, twin, actions, *frozen(rest), **frozen(named))

    def ask(self, payload):
        if self.keep is not None:
            self.keep.append(json.loads(json.dumps(payload, ensure_ascii=False)))
        row = {'t': round(self.k.time, 3), 'payload': h(payload)}
        sections = {'top.' + key: h(value) for key, value in payload.items() if key != 'state'}
        sections.update({'state.' + key: h(value) for key, value in payload['state'].items() if key != 'rules'})
        sections.update({'rules.' + key: h(value) for key, value in payload['state']['rules'].items()})
        # Only sections that changed since the previous request, to keep the golden files small.
        row['sections'] = {key: value for key, value in sections.items() if self.sections.get(key) != value}
        row['removed'] = sorted(set(self.sections) - set(sections))
        self.sections = sections
        if self.sampled():
            row['wire'] = {name: h(captured(lambda: send(self.rebuilt(client) if client else frozen((payload,))[0])))
                           for name, (client, send) in self.wires.items()}
        self.requests.append(row)
        if self.sample is None:
            self.sample = deepcopy(payload)
        criteria = payload['questions']['next_action']['criteria']
        # The kitchen the request describes: the real one, or for a request asked ahead the fork at the step's end.
        described = self.arguments[0] if self.arguments else self.k
        move = self.choose(described, 'jeff')
        choice = (move.key if move and move.key in criteria else
                  next((key for key in ('wait', 'continue') if key in criteria), sorted(criteria)[0]))
        if self.note_choice:
            row['choice'] = choice
        return {'sprint_answer': {}, 'sprint': False, 'choice': choice, 'confidence': None,
                'probabilities': {}, 'model': 'payload-fingerprint', 'usage': {}, 'latency': 0.0}


class Inline:
    """Runs the loop's request thread in place, so answers arrive on the next poll."""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


def previous_round_memory(level):
    """A finished reference round on the same level, as cross-round memory sees it."""
    k = SpatialKitchen(level_config(load_config(), level))
    step = 0
    while not k.ended:
        if step % HUMAN_EVERY == 0:
            for who, role in (('human', 'assembler'), ('jeff', 'cook')):
                action = reference_policy.choose(k, who, role)
                if action:
                    k.start(who, action)
        k.advance(STEP)
        step += 1
    messages = [{'code': 'prep'}, {'code': 'mistake'}]
    return memory_context(True, [episode(k, 'payload-fingerprint-previous', 'payload-fingerprint', messages,
                                         round_summary(k))])


def message(k, loop, code):
    """The message dict the local session builds (web_server._communicate), with a fixed wall time."""
    chef = k.chefs['jeff']
    job = chef.job
    return {'id': 'M' + str(len(loop.player_messages) + 1), 'round_id': 'payload-fingerprint-round',
            'kind': 'correction' if code == 'mistake' else 'preference',
            'code': code, 'text': PLAYER_MESSAGES[code],
            'game_time': round(k.time, 3), 'wall_time': WALL_TIME,
            'first_request_id': None,
            'context': {'ai_request_id': loop.calls, 'current_action': job.action.key if job else None,
                        'last_choice': loop.recent_decisions[-1]['choice'] if loop.recent_decisions else None,
                        'holding_id': chef.hand.id if chef.hand else None,
                        'holding_stage': chef.hand.stage if chef.hand else None,
                        'event_index': len(k.events)}}


_RECORDED = {}


def recorded(name):
    """One scenario's fingerprint and every payload it sent, recorded once per process: the fingerprint test and
    other tests read the same round instead of playing it twice."""
    if name not in _RECORDED:
        payloads = []
        _RECORDED[name] = (run(name, keep=payloads), payloads)
    return _RECORDED[name]


def run(name, keep=None):
    if name in AHEAD:
        on = {key: dict(value) for key, value in features.current().items()}
        on['ask_ahead']['on'] = True
        with patch.object(features, 'current', lambda: {key: dict(value) for key, value in on.items()}):
            return _run(name, keep)
    if name in NAMES:
        on = {key: dict(value) for key, value in features.current().items()}
        on['clear_text']['on'] = True
        with patch.object(features, 'current', lambda: {key: dict(value) for key, value in on.items()}):
            return _run(name, keep)
    return _run(name, keep)


def _run(name, keep=None):
    level, talk = SCENARIOS[name]
    memory = previous_round_memory(level) if talk else None
    # Start like a freshly started server. Kitchens on one map share a navigation object and its
    # route caches, so rounds or tests run earlier in the same process never reach this recording.
    spatial_kitchen._map_navigation.cache_clear()
    k = SpatialKitchen(level_config(load_config(), level))
    model = StandIn(k.c, k, wire_clients(k.c), keep)
    loop = DecisionLoop(k, model, lambda *_: None, lambda *_: None)
    loop.game_speed = SPEED   # as the session sets it
    loop.player_messages = []
    if talk:
        loop.cooperation_memory = memory
    loop.one_press = features.one_press_flags(features.current())   # the released features, as a new session has them
    loop.ask_ahead = features.current()['ask_ahead']['on']
    # clear_text: food names, item names, the engine's English and plate names, as a new session sets them.
    loop.names = loop.clear = loop.english = loop.plate = features.current()['clear_text']['on']
    pending = list(MESSAGES) if talk else []
    step = 0
    replies = []                # (wall time due, request thread) when replies take time

    class Delayed:
        def __init__(self, target, daemon=None):
            self.target = target

        def start(self):
            replies.append((1000 + k.time / SPEED + REPLY_SECONDS, self.target))
    thread = Delayed if name in AHEAD else Inline
    with (patch('jev.time.monotonic', lambda: 1000 + k.time / SPEED), patch('jev.threading.Thread', thread),
          patch('jev.compose_payload', model.compose)):
        while not k.ended:
            for reply in [r for r in replies if r[0] <= 1000 + k.time / SPEED]:
                replies.remove(reply)
                reply[1]()
            if step % HUMAN_EVERY == 0:
                action = reference_policy.choose(k, 'human', 'assembler')
                if action:
                    k.start('human', action)
            while pending and k.time >= pending[0][0]:
                loop.player_messages.append(message(k, loop, pending.pop(0)[1]))
                loop.last_revision = -1   # the session refreshes Jeff at the normal cadence
            loop.poll(enabled=True)
            k.advance(STEP)
            step += 1
    return {'scenario': name, 'level': level, 'requests': model.requests, 'sample_payload': model.sample,
            'result': k.result()}


def switch_set(name):
    """A switch set's features, from this release's features.json as written (a server override does not count)."""
    release = features.load()
    if name == 'release':
        return release
    if name == 'release-partner-links':
        on = {key for key, value in release.items() if value['on']} | {'option_links_partner'}
    else:
        on = set(release) - set(SET_OFF[name])
    return {key: {**value, 'on': key in on} for key, value in release.items()}


class _Unasked:
    """The session's model client: never asked, the fingerprint's decision loop has its own."""

    def __init__(self, config):
        pass

    def payload(self, state, actions):
        return {'state': state}

    def ask(self, payload):
        raise RuntimeError('payload fingerprint: the session model is not asked')


class _Journal:
    def __init__(self, name):
        pass

    def __call__(self, kind, data):
        pass

    def close(self):
        pass


def session_switches(on):
    """The switches a started round's decision loop has with these features (LOOP_SWITCHES), from a session's start."""
    game = GameSession(config=None, client_factory=_Unasked, journal_factory=_Journal)
    game.features = on
    try:
        code, body = game.command('/api/start', {'game_id': game.game_id, 'request_id': 'payload-fingerprint',
                                                 'speed': SPEED})
        if code != 200:
            raise AssertionError(f'the session did not start: {code} {body}')
        return {name: deepcopy(getattr(game.ai, name)) for name in LOOP_SWITCHES}
    finally:
        game.close()


def digest(windows):
    """One hash over every request's payload hash, in order."""
    return hashlib.sha256(''.join(row['payload'] for w in windows for row in w['requests']).encode()).hexdigest()[:16]


def switch_run(level, name, samples=(), wire_every=None):
    """A switch set's fingerprint on a level: one window per sample (start, requests; SAMPLES by default), each
    from a fork of the kitchen played to its start, or the whole round when samples is None. Request bodies on every
    wire_every-th request of a window; by default on the first request of window WIRE_WINDOW for the release set,
    and none for the others."""
    on = switch_set(name)
    switches = session_switches(on)
    if samples == ():
        samples = SAMPLES[level]
    windows = []
    for index, (start, count) in enumerate(samples or ((0, None),)):
        every = wire_every
        if every is None:
            every = 10 ** 9 if name == 'release' and index == WIRE_WINDOW else 0
        k, step = played(level, start) if samples else played(level, 0, cached=False)
        windows.append(_window(k.fork() if samples else k, step, switches, start, count, every, policy(level)))
    return {'level': level, 'set': name, 'on': sorted(key for key, value in on.items() if value['on']),
            'switches': switches, 'digest': digest(windows), 'windows': windows}


_PLAYED = {}


def played(level, start, cached=True):
    """A level's kitchen with both chefs on the level's reference policy (policy) up to game time start, from a
    freshly started server's state, and the steps played; kept per (level, start) unless cached is False (callers
    fork it: a fork never changes it)."""
    if cached and (level, start) in _PLAYED:
        return _PLAYED[level, start]
    spatial_kitchen._map_navigation.cache_clear()
    k = SpatialKitchen(level_config(load_config(), level))
    choose = policy(level)
    step = 0
    while k.time < start - 1e-9 and not k.ended:
        if step % HUMAN_EVERY == 0:
            for who in ('human', 'jeff'):
                action = choose(k, who)
                if action:
                    k.start(who, action)
        k.advance(STEP)
        step += 1
    if cached:
        _PLAYED[level, start] = k, step
    return k, step


def _window(k, step, switches, start, count, wire_every, choose):
    model = StandIn(k.c, k, wire_clients(k.c) if wire_every else {})
    model.wire_every = wire_every
    model.choose, model.note_choice = choose, True
    loop = DecisionLoop(k, model, lambda *_: None, lambda *_: None)
    loop.game_speed = SPEED
    loop.player_messages = []
    for key, value in deepcopy(switches).items():
        setattr(loop, key, value)
    with (patch('jev.time.monotonic', lambda: 1000 + k.time / SPEED), patch('jev.threading.Thread', Inline),
          patch('jev.compose_payload', model.compose), patch('jev.finish_payload', model.finish)):
        while not k.ended and (count is None or len(model.requests) < count):
            if step % HUMAN_EVERY == 0:
                action = choose(k, 'human')
                if action:
                    k.start('human', action)
            loop.poll(enabled=True)
            k.advance(STEP)
            step += 1
    return {'start': start, 'requests': model.requests, 'end': round(k.time, 3),
            **({'result': k.result()} if k.ended else {})}


def switch_golden(level, name, full=False):
    return GOLDEN_SWITCHES / ('full' if full else '') / f'{level}-{name}.json'


def dump_switches(data):
    """One request per line, like dump."""
    compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    head = {k: v for k, v in data.items() if k != 'windows'}
    windows = []
    for window in data['windows']:
        rows = ',\n'.join('    ' + compact(row) for row in window['requests'])
        rest = ''.join(f',{compact(k)}:{compact(v)}' for k, v in window.items() if k not in ('start', 'requests'))
        windows.append(f'  {{"start":{compact(window["start"])}{rest},"requests":[\n{rows}\n  ]}}')
    return ('{\n' + ''.join(f' {compact(k)}:{compact(v)},\n' for k, v in head.items())
            + ' "windows":[\n' + ',\n'.join(windows) + '\n ]\n}\n')


def switches_main(argv):
    full, update = '--full' in argv, '--update' in argv
    names = [a for a in argv if not a.startswith('--')]
    levels = [a for a in names if a in SWITCH_LEVELS] or list(SWITCH_LEVELS)
    sets = [a for a in names if a in SWITCH_SETS] or list(SWITCH_SETS)
    unknown = sorted(set(names) - set(levels) - set(sets))
    if unknown:
        print('unknown level or set:', ', '.join(unknown), file=sys.stderr)
        return 2
    failed = 0
    for level in levels:
        for name in sets:
            started = time.monotonic()
            data = (switch_run(level, name, samples=None, wire_every=FULL_WIRE_EVERY if name == 'release' else 0)
                    if full else switch_run(level, name))
            path = switch_golden(level, name, full)
            seconds = round(time.monotonic() - started, 1)
            count = sum(len(w['requests']) for w in data['windows'])
            if update:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(dump_switches(data), encoding='utf-8')
                print(f'{level} {name}: {count} requests, digest {data["digest"]}, {seconds} s, written')
                continue
            golden = json.loads(path.read_text(encoding='utf-8'))
            same = json.loads(json.dumps(data, ensure_ascii=False)) == golden
            failed += not same
            print(f'{level} {name}: {count} requests, digest {data["digest"]} (golden {golden["digest"]}), '
                  f'{seconds} s, {"same" if same else "DIFFERENT"}')
    return 1 if failed else 0


def dump(data):
    """One request per line: small files whose diffs point at the request that changed."""
    compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    rows = ',\n'.join('  ' + compact(row) for row in data['requests'])
    head = {k: v for k, v in data.items() if k not in ('requests', 'sample_payload')}
    return ('{\n' + ''.join(f' {compact(k)}:{compact(v)},\n' for k, v in head.items())
            + ' "requests":[\n' + rows + '\n ],\n'
            + ' "sample_payload":' + json.dumps(data['sample_payload'], ensure_ascii=False, indent=1) + '\n}\n')


def main():
    if '--switches' in sys.argv:
        raise SystemExit(switches_main([a for a in sys.argv[1:] if a != '--switches']))
    if '--update' not in sys.argv:
        print('usage: python3 tests/payload_fingerprint.py --update\n'
              '       python3 tests/payload_fingerprint.py --switches [--full] [--update] [LEVEL] [SET]')
        return
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name in SCENARIOS:
        data = run(name)
        (GOLDEN / f'{name}.json').write_text(dump(data))
        print(name, len(data['requests']), 'requests', data['result'])


if __name__ == '__main__':
    main()
