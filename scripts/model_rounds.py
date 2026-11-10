#!/usr/bin/env python3
"""Whole rounds of a scripted human and the real Jeff, offline: the baseline ladder's fourth rung. Run locally; it calls the model.

    python3 scripts/model_rounds.py --level level-2 --rounds 6 --out runs/l2-jev [--human assembler] [--parallel 3] [--dry-run]

Each round is played by the same session the local game runs (web_server.GameSession): Jeff is the real decision
loop asking the connection saved in the game (scripts/jev_replay_check.client: .player-api.json, else the local Jev
key), and the round runs in real time, so the model's reply time counts as it does for a player. The human chef is
a scripted reference chef (reference_policy), choosing every half second:

- assembler / cook: the reference pair's two roles (the calibration pair plays both);
- solo: the scripted chef that does everything by itself, ignoring Jeff;
- idle: nobody, so Jeff alone.

A scripted human is not a person: these rounds measure Jeff with a steady, known partner, many times and cheaply,
which a handful of real rounds cannot. Read them as such, next to real rounds, never instead of them.

Every round's journal and session bundle go to --out (never the project's logs/), so collaboration_analyzer.py
replays them exactly and scripts/decision_stats.py reads them; at the end --out/summary/report.json holds each
round's result and decision_stats' report for the set. --dry-run builds the first request and prints the most a set can cost
(requests and input tokens at ai_max_calls per round) without calling anything. Agree on the protocol and budget
first (docs/research/trial-protocol.md).
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HUMANS = ('assembler', 'cook', 'solo', 'idle')
STEP = .05             # wall seconds between session ticks, as the game's own loop
HUMAN_EVERY = 10       # the scripted human chooses every 10 steps (0.5 s), as the calibration's fast chefs
DEFAULT_PRICE_PER_M = .042    # USD per million input tokens (Jev), for the estimate only


def human_choice(k, human):
    import reference_policy
    if human == 'idle':
        return None
    if human == 'solo':
        return reference_policy.choose_solo(k, 'human')
    return reference_policy.choose(k, 'human', human)


def config_for(level, max_calls=None):
    from kitchen import load_config
    from levels import level_config
    config = dict(level_config(load_config(), level))
    if max_calls:
        config['ai_max_calls'] = max_calls
    return config


def play_round(level, client_factory, human='assembler', max_calls=None, clock=time.monotonic, wait=time.sleep):
    """One whole round in the local game's session; journal and bundle go to play.log_root(). Returns its result."""
    import play
    from spatial_kitchen import SpatialKitchen
    from web_server import GameSession
    game = GameSession(config_for(level, max_calls), client_factory=client_factory, journal_factory=play.Journal,
                       kitchen_factory=SpatialKitchen, log_prefix='rounds')
    try:
        game.last_tick = game.last_seen = clock()
        status, reply = game._command('/api/start', {'speed': 1})
        if status != 200:
            raise RuntimeError(f"the round did not start: {reply.get('error')}")
        journal = str(game.journal.path)
        step = 0
        while game.phase == 'running':
            now = clock()
            game.last_seen = now                 # the scripted human is always there; the game pauses after 8 s without
            if step % HUMAN_EVERY == 0:
                with game.lock:
                    if game.k.chefs['human'].job is None:
                        action = human_choice(game.k, human)
                        if action is not None:
                            game.k.start('human', action)
            game.tick(now)
            step += 1
            wait(STEP)
        goal = game.k.snapshot().get('goal_status') or {}
        return {'game_id': game.game_id, 'level': level, 'human': human, 'phase': game.phase, 'config_hash': game.k.config_hash,
                'money': game.k.money, 'goal_reached': bool(goal.get('met_now')), 'stars': goal.get('stars_now'),
                'result': game.k.result(), 'ai_calls': game.ai.calls if game.ai else 0,
                'model': getattr(game.ai, 'actual_model', None) if game.ai else None,
                'journal': Path(journal).name, 'bundle': f'sessions/{game.game_id}'}
    finally:
        game.close()


def _one(job):
    """A round in its own process, so journals never share a name and a crash takes one round down only."""
    level, human, max_calls, out = job
    os.environ['CHEFJEFF_LOG_DIR'] = out
    from scripts.jev_replay_check import client
    return play_round(level, lambda config: client(config), human, max_calls)


def estimate(level, rounds, max_calls=None, price_per_m=DEFAULT_PRICE_PER_M):
    """The most a set can send: every round at its call limit, each request as large as the first one."""
    from jev import NO_MEMORY, compose_payload
    from spatial_kitchen import SpatialKitchen
    from whitebox_server import SpatialJevClient
    config = config_for(level, max_calls)
    k = SpatialKitchen(config)
    import features
    payload = compose_payload(SpatialJevClient(config, key='model-rounds-estimate'), k, k.snapshot(), k.actions('jeff'),
                              [], None, NO_MEMORY, **features.compose_options(features.current()))
    requests = rounds * config['ai_max_calls']
    tokens = len(json.dumps(payload, ensure_ascii=False)) / 4 * requests
    return {'rounds': rounds, 'max_requests': requests, 'max_input_tokens_m': round(tokens / 1e6, 2),
            'max_cost_usd': round(tokens / 1e6 * price_per_m, 2), 'price_per_m_input_usd': price_per_m,
            'minutes_of_play': round(rounds * k.snapshot()['round_limit'] / 60, 1)}


def summary(results, out):
    """Each round's result and decision_stats' outcomes for the set (read from the journals in out)."""
    from scripts import decision_stats
    from scripts.reask import SINGLE_MODEL
    stats = decision_stats.report([out])
    # One connection per run: compare with a second model's run before reading a change as Jeff's.
    return {'rounds': results, 'decision_stats': stats, 'note': SINGLE_MODEL}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--level', default='level-2', help='level id, e.g. level-1')
    parser.add_argument('--rounds', type=int, default=6)
    parser.add_argument('--human', choices=HUMANS, default='assembler')
    parser.add_argument('--max-calls', type=int, help='call limit per round (default: config.json ai_max_calls)')
    parser.add_argument('--parallel', type=int, default=1, help='rounds played at once, each in its own process')
    parser.add_argument('--out', required=True, help='folder for journals, bundles and the report (not logs/)')
    parser.add_argument('--price-per-m', type=float, default=DEFAULT_PRICE_PER_M, help='USD per million input tokens')
    parser.add_argument('--dry-run', action='store_true', help='print the most the set can cost and call nothing')
    args = parser.parse_args(argv)
    if args.rounds < 1 or args.parallel < 1:
        parser.error('--rounds and --parallel take 1 or more')
    out = Path(args.out).resolve()
    from play import ROOT as PROJECT
    if out == (PROJECT / 'logs').resolve():
        parser.error("--out must not be the game's own logs/ folder")
    cost = estimate(args.level, args.rounds, args.max_calls, args.price_per_m)
    print(json.dumps(cost), file=sys.stderr)
    if args.dry_run:
        return 0
    from scripts.jev_replay_check import client
    try:
        client(config_for(args.level, args.max_calls))       # says on stderr which connection it will use
    except RuntimeError as error:                             # no saved connection and no local Jev key
        print(f'no model connection: {error}', file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(args.level, args.human, args.max_calls, str(out))] * args.rounds
    with ProcessPoolExecutor(max_workers=args.parallel) as pool:
        results = list(pool.map(_one, jobs))
    # Beside the journals, not among them: decision_stats reads every *.json in the folder it is given.
    report_path = out / 'summary' / 'report.json'
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(summary(results, str(out)), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'rounds': len(results), 'goal_reached': sum(r['goal_reached'] for r in results),
                      'money': [r['money'] for r in results], 'report': str(report_path)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
