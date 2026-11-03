"""Byte-level fingerprints of Jeff's model input, for refactors that must not change it.

Each scenario plays a level's fixed round. The human chef follows the recipe
reference policy; Jeff is driven by the real ``DecisionLoop`` with a scripted
stand-in model (no network, no key), on a clock that follows game time, so
every request is reproducible. For each request we record the hash of:

- the harness payload (``compose_payload``: what the loop logs and the online
  version relays to the browser), and of each of its sections;
- on every 4th request, the exact request body every client would send: local
  Jev, decision and chat presets, and the online server's Jev and free-model
  forwarders. The bodies are fixed transforms of the payload, so a change to how
  any client builds them shows on every sampled request.

``python3 tests/payload_fingerprint.py --update`` rewrites the golden files;
do that only for an intended, reviewed change to Jeff's input and say why in
the commit message. The browser's own request builder (hosted/browser-agent.js)
and the online memory insertion are not covered here. Each scenario clears the
navigation cache first, as a freshly started server would have it.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import pickle
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hosted_free_models  # noqa: E402
import jev  # noqa: E402
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
from web_server import PLAYER_MESSAGES  # noqa: E402
from whitebox_server import SpatialJevClient  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / 'golden' / 'payloads'
STEP = .05          # same quantisation as the behaviour fingerprints
HUMAN_EVERY = 10    # human policy decision every 0.5 game seconds
WIRE_EVERY = 4      # request bodies of every client on every 4th request (they are fixed transforms of the payload)
SPEED = .75         # default game seconds per wall second; the loop's clock is wall time
KEY = 'payload-fingerprint-key'
WALL_TIME = '2026-11-03T12:00:00+08:00'
SCENARIOS = {
    # name: (level id, with player messages and cross-round memory)
    'level1': ('level-1', False),
    'level2': ('level-2', False),
    'level3': ('level-3', False),
    'level2-messages-memory': ('level-2', True),
}
MESSAGES = ((20.0, 'prep'), (70.0, 'mistake'), (120.0, 'wash'))
COMPOSE = jev.compose_payload


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

    def __init__(self, config, kitchen, wires):
        super().__init__(config, key=KEY)
        self.k, self.wires, self.requests = kitchen, wires, []
        self.sections = {}
        self.arguments = None   # what the loop passed to compose_payload for this request
        self.sample = None      # the first payload, kept whole in the golden file

    def compose(self, client, kitchen, *arguments, **options):
        self.arguments = (kitchen, frozen(arguments), frozen(options))
        return COMPOSE(client, kitchen, *arguments, **options)

    def rebuilt(self, client):
        kitchen, arguments, options = self.arguments
        return COMPOSE(client, kitchen, *frozen(arguments), **frozen(options))

    def ask(self, payload):
        row = {'t': round(self.k.time, 3), 'payload': h(payload)}
        sections = {'top.' + key: h(value) for key, value in payload.items() if key != 'state'}
        sections.update({'state.' + key: h(value) for key, value in payload['state'].items() if key != 'rules'})
        sections.update({'rules.' + key: h(value) for key, value in payload['state']['rules'].items()})
        # Only sections that changed since the previous request, to keep the golden files small.
        row['sections'] = {key: value for key, value in sections.items() if self.sections.get(key) != value}
        row['removed'] = sorted(set(self.sections) - set(sections))
        self.sections = sections
        if len(self.requests) % WIRE_EVERY == 0:
            row['wire'] = {name: h(captured(lambda: send(self.rebuilt(client) if client else frozen((payload,))[0])))
                           for name, (client, send) in self.wires.items()}
        self.requests.append(row)
        if self.sample is None:
            self.sample = deepcopy(payload)
        criteria = payload['questions']['next_action']['criteria']
        move = reference_policy.choose(self.k, 'jeff', 'cook')
        choice = (move.key if move and move.key in criteria else
                  next((key for key in ('wait', 'continue') if key in criteria), sorted(criteria)[0]))
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


def run(name):
    level, talk = SCENARIOS[name]
    memory = previous_round_memory(level) if talk else None
    # Start like a freshly started server. Kitchens on one map share a navigation object and its
    # route caches, so rounds or tests run earlier in the same process never reach this recording.
    spatial_kitchen._map_navigation.cache_clear()
    k = SpatialKitchen(level_config(load_config(), level))
    model = StandIn(k.c, k, wire_clients(k.c))
    loop = DecisionLoop(k, model, lambda *_: None, lambda *_: None)
    loop.player_messages = []
    if talk:
        loop.cooperation_memory = memory
    pending = list(MESSAGES) if talk else []
    step = 0
    with (patch('jev.time.monotonic', lambda: 1000 + k.time / SPEED), patch('jev.threading.Thread', Inline),
          patch('jev.compose_payload', model.compose)):
        while not k.ended:
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


def dump(data):
    """One request per line: small files whose diffs point at the request that changed."""
    compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    rows = ',\n'.join('  ' + compact(row) for row in data['requests'])
    head = {k: v for k, v in data.items() if k not in ('requests', 'sample_payload')}
    return ('{\n' + ''.join(f' {compact(k)}:{compact(v)},\n' for k, v in head.items())
            + ' "requests":[\n' + rows + '\n ],\n'
            + ' "sample_payload":' + json.dumps(data['sample_payload'], ensure_ascii=False, indent=1) + '\n}\n')


def main():
    if '--update' not in sys.argv:
        print('usage: python3 tests/payload_fingerprint.py --update')
        return
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name in SCENARIOS:
        data = run(name)
        (GOLDEN / f'{name}.json').write_text(dump(data))
        print(name, len(data['requests']), 'requests', data['result'])


if __name__ == '__main__':
    main()
