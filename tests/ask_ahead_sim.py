"""Offline simulation of ask_ahead: a level-2 round with a stand-in model whose every reply takes a fixed time.

    python3 tests/ask_ahead_sim.py            prints both reply times, ask_ahead off and on

The human plays the reference assembler; Jeff's stand-in answers the reference cook's move for the kitchen the request
describes (for a request asked ahead, the fork at the end of his step), else continue or wait. Replies arrive exactly
`latency` game seconds after the request (speed 1, so wall and game seconds agree). Reported: the wait from each of
Jeff's finished steps to the start of his next (median and mean), requests, how answers asked ahead ended, and
answers refused by the engine.
"""
from __future__ import annotations
from collections import Counter
import statistics
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import jev  # noqa: E402
import reference_policy  # noqa: E402
import spatial_kitchen  # noqa: E402
from jev import DecisionLoop  # noqa: E402
from kitchen import load_config  # noqa: E402
from levels import level_config  # noqa: E402
from spatial_kitchen import SpatialKitchen  # noqa: E402
from whitebox_server import SpatialJevClient  # noqa: E402

STEP = .05
HUMAN_EVERY = 10
COMPOSE = jev.compose_payload


class StandIn(SpatialJevClient):
    def __init__(self, config):
        super().__init__(config, key='simulation-no-key')
        self.described = None       # the kitchen the request being composed describes

    def compose(self, client, kitchen, *arguments, **options):
        self.described = kitchen
        return COMPOSE(client, kitchen, *arguments, **options)

    def ask(self, payload):
        criteria = payload['questions']['next_action']['criteria']
        move = reference_policy.choose(self.described, 'jeff', 'cook')
        choice = move.key if move and move.key in criteria else next(k for k in ('continue', 'wait') if k in criteria)
        return {'choice': choice, 'sprint': False, 'confidence': None, 'probabilities': {}, 'model': 'simulation',
                'usage': {}, 'latency': 0.0}


def simulate(latency, ahead, level='level-2', seconds=180.0):
    spatial_kitchen._map_navigation.cache_clear()
    k = SpatialKitchen(level_config(load_config(), level))
    model = StandIn(k.c)
    rows = []
    loop = DecisionLoop(k, model, lambda kind, data: rows.append((kind, data)), lambda *_: None)
    loop.player_messages = []
    loop.ask_ahead = ahead
    clock = [1000.0]
    due = []                                    # (wall time, work) of replies on their way

    class Delayed:
        def __init__(self, target, daemon=None):
            self.target = target

        def start(self):
            due.append((clock[0] + latency, self.target))

    step = 0
    with patch('jev.time.monotonic', lambda: clock[0]), patch('jev.threading.Thread', Delayed), \
            patch('jev.compose_payload', model.compose):
        while not k.ended and k.time < seconds:
            if step % HUMAN_EVERY == 0:
                action = reference_policy.choose(k, 'human', 'assembler')
                if action:
                    k.start('human', action)
            for item in [d for d in due if d[0] <= clock[0]]:
                due.remove(item)
                item[1]()
            loop.poll(enabled=True)
            k.advance(STEP)
            clock[0] += STEP
            step += 1
    responses = [d for kind, d in rows if kind == 'ai_response']
    ahead_started = {d.get('action_id') for d in responses if d.get('ask_ahead', {}).get('result') == 'applied'}
    gaps, ahead_gaps, open_at, step_time, started_at = [], [], None, [], None
    for event in k.events:
        if event.get('actor') != 'jeff':
            continue
        if event.get('kind') == 'action_done':
            open_at = event.get('t', None)
            if started_at is not None:
                step_time.append(event['t'] - started_at)
        elif event.get('kind') == 'action_start':
            started_at = event['t']
            if open_at is not None:
                gaps.append(event['t'] - open_at)
                if event.get('action_id') in ahead_started:
                    ahead_gaps.append(event['t'] - open_at)
            open_at = None
    asked = [d for d in responses if 'ask_ahead' in d]
    return {'latency': latency, 'ask_ahead': ahead, 'requests': sum(kind == 'ai_request' for kind, _ in rows),
            'asked_ahead': sum('ask_ahead' in d for kind, d in rows if kind == 'ai_request'),
            'ahead_results': dict(Counter(d['ask_ahead']['result'] for d in asked)),
            'ahead_discarded_why': dict(Counter(d['ask_ahead']['reason'] for d in asked if d['ask_ahead']['result'] == 'discarded')),
            'refused_by_engine': loop.rejected_count, 'stale': loop.stale_count,
            'steps': len(gaps), 'wait_median': round(statistics.median(gaps), 3) if gaps else None,
            'wait_mean': round(statistics.fmean(gaps), 3) if gaps else None,
            'steps_started_ahead': len(ahead_gaps), 'wait_median_ahead': round(statistics.median(ahead_gaps), 3) if ahead_gaps else None,
            'step_seconds_median': round(statistics.median(step_time), 2) if step_time else None,
            'steps_shorter_than_reply': sum(t < latency for t in step_time), 'result': k.result()}


def main():
    for latency in (1.2, 3.5):
        for ahead in (False, True):
            print(simulate(latency, ahead))


if __name__ == '__main__':
    main()
