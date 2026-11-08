#!/usr/bin/env python3
"""ChefJeff Benchmark: an agent plays fixed levels with a fixed scripted partner, many rounds, and the result says how sure it is.

    python3 scripts/benchmark.py run --agent jeff --out runs/jev [--parallel 3] [--dry-run]
    python3 scripts/benchmark.py run --agent example_agent:PriorityAgent --out runs/example
    python3 scripts/benchmark.py verify runs/jev/result.json
    python3 scripts/benchmark.py report runs/jev/result.json runs/example/result.json

What a version measures is frozen in benchmark/<version>/manifest.json: the environment interface (env-v1), each
level's configuration hash, the engine's behaviour on it (the hash of its golden reference trace, which changes
exactly when the engine plays differently), the scripted partner (reference_policy.py), the partner role and the
rounds per cell. `freeze` recomputes these from the code; a test fails when they differ from the manifest, so a
change to any of them makes a new benchmark version instead of silently changing what an old score means.

An agent is `jeff` (the game's own Jeff on the connection saved in the game, the way the game asks) or
`module:Class`, an environment.Agent made with no arguments (example_agent:PriorityAgent is the floor). Each cell is
played with scripts/model_rounds.play_round in real time; every round's journal and session bundle are kept, and
its replay is checked. result.json holds every round and, per cell, the means with 95% bootstrap intervals and the
goal rate with its Wilson interval. `verify` refuses a result made with other frozen values, the wrong number of
rounds, a virtual clock, or a round that does not replay. Paid rounds are run by the owner, after --dry-run.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import research_stats  # noqa: E402

FORMAT = 'chefjeff-benchmark-result-v1'
LEVEL_TRACES = {'level-1': 'level1-reference.json', 'level-2': 'level2-reference.json', 'level-3': 'level3-reference.json',
                'level-4': 'level4-zoned.json'}


def sha(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest_path(version):
    return ROOT / 'benchmark' / version / 'manifest.json'


def read_manifest(version='v1'):
    return json.loads(manifest_path(version).read_text(encoding='utf-8'))


def freeze(levels, partner, rounds_per_cell, version):
    """What a benchmark version measures, computed from the code as it is now."""
    import environment
    from scripts.model_rounds import config_for
    from spatial_kitchen import SpatialKitchen
    return {'benchmark': 'chefjeff', 'version': version, 'env_api_version': environment.ENV_API_VERSION,
            'clock': 'real', 'partner': partner, 'rounds_per_cell': rounds_per_cell,
            'partner_policy': sha(ROOT / 'reference_policy.py'),
            'levels': [{'id': level, 'config_hash': SpatialKitchen(config_for(level)).config_hash,
                        'engine_trace': sha(ROOT / 'tests' / 'golden' / LEVEL_TRACES[level])} for level in levels]}


def refreeze(manifest):
    """The manifest's frozen values recomputed now; equal to the manifest while nothing it froze has changed."""
    return freeze([level['id'] for level in manifest['levels']], manifest['partner'], manifest['rounds_per_cell'],
                  manifest['version'])


def manifest_hash(manifest):
    return 'sha256:' + hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def agent_factory(spec):
    """A client factory for the game's session: jeff on the saved connection, or an environment.Agent class."""
    if spec == 'jeff':
        from scripts.jev_replay_check import client
        return lambda config: client(config)
    module, _, name = spec.partition(':')
    if not name:
        raise ValueError("an agent is 'jeff' or 'module:Class'")
    cls = getattr(importlib.import_module(module), name)
    return lambda config: cls()


def _round(job):
    """One round in its own process (journal names never collide); its bundle analysed and its replay checked."""
    spec, level, partner, out = job
    os.environ['CHEFJEFF_LOG_DIR'] = out
    from scripts.model_rounds import play_round
    return analyse(play_round(level, agent_factory(spec), partner), out)


def analyse(result, out):
    """A round's result with what the analyzer finds in its bundle: replay check, contribution and gain."""
    from collaboration_analyzer import analyze_bundle
    report = analyze_bundle(Path(out) / result['bundle'])
    who = report.get('chefs', {})
    return {**result, 'replay_matches': report['replay']['matches_recording'],
            'served': report.get('served'), 'contribution_rate': report.get('contribution_rate'),
            'agent_share_of_contributing': (who.get('jeff') or {}).get('share_of_contributing')}


def solo_baseline():
    """The scripted solo chef's median income per level (calibration report), for the gain over playing alone."""
    data = json.loads((ROOT / 'docs/architecture/reports/calibration.json').read_text(encoding='utf-8'))
    return {f"level-{row['level']}": row.get('solo_median') for row in data['levels']}


def summarise(rounds, level):
    money = [r['money'] for r in rounds]
    solo = solo_baseline().get(level)
    shares = [r['agent_share_of_contributing'] for r in rounds if r.get('agent_share_of_contributing') is not None]
    return {'rounds': len(rounds), 'money_mean': round(research_stats.mean(money), 1) if money else None,
            'money_ci95': research_stats.bootstrap(money),
            'goal': research_stats.share(sum(bool(r['goal_reached']) for r in rounds), len(rounds)),
            'gain_over_scripted_solo_mean': round(research_stats.mean(money) - solo, 1) if money and solo is not None else None,
            'agent_share_of_contributing_mean': round(research_stats.mean(shares), 3) if shares else None,
            'agent_share_of_contributing_ci95': research_stats.bootstrap(shares),
            'ai_calls_mean': round(research_stats.mean([r['ai_calls'] for r in rounds]), 1) if rounds else None,
            'replays_exactly': all(r['replay_matches'] for r in rounds)}


def run(spec, out, manifest, parallel=1, play=None, clock='real'):
    """Every cell of the manifest; play(job) plays one round (a process pool by default)."""
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(spec, level['id'], manifest['partner'], str(out)) for level in manifest['levels']
            for _ in range(manifest['rounds_per_cell'])]
    if play is None:
        with ProcessPoolExecutor(max_workers=parallel) as pool:
            rounds = list(pool.map(_round, jobs))
    else:
        rounds = [play(job) for job in jobs]
    cells = []
    for level in manifest['levels']:
        mine = [r for r in rounds if r['level'] == level['id']]
        cells.append({'level': level['id'], 'partner': manifest['partner'], 'summary': summarise(mine, level['id']),
                      'rounds': mine})
    models = sorted({str(r.get('model') or '') for r in rounds} - {''})
    result = {'format': FORMAT, 'benchmark': manifest['benchmark'], 'version': manifest['version'],
              'manifest': manifest_hash(manifest), 'env_api_version': manifest['env_api_version'], 'clock': clock,
              'agent': {'spec': spec, **({'models': models} if models else {})},
              'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'cells': cells}
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def verify(result, manifest):
    """Problems that keep a result from counting as this benchmark version's; [] when it counts."""
    problems = []
    if result.get('format') != FORMAT:
        problems.append('not a benchmark result')
    if result.get('manifest') != manifest_hash(manifest):
        problems.append(f"made for another manifest than benchmark {manifest['version']}")
    if refreeze(manifest) != manifest:
        problems.append('this checkout no longer matches the manifest (levels, engine, partner or interface changed)')
    if result.get('clock') != manifest['clock']:
        problems.append(f"played on a {result.get('clock')} clock; the benchmark needs a {manifest['clock']} one")
    frozen = {level['id']: level['config_hash'] for level in manifest['levels']}
    cells = {cell['level']: cell for cell in result.get('cells', [])}
    for level, config in frozen.items():
        rounds = (cells.get(level) or {}).get('rounds', [])
        if len(rounds) != manifest['rounds_per_cell']:
            problems.append(f'{level}: {len(rounds)} rounds, {manifest["rounds_per_cell"]} needed')
        if any(r.get('config_hash') != config for r in rounds):
            problems.append(f'{level}: a round played another configuration')
        if any(r.get('human') != manifest['partner'] for r in rounds):
            problems.append(f'{level}: a round had another partner')
        if any(r.get('phase') != 'ended' for r in rounds):
            problems.append(f'{level}: a round did not end')
        if not all(r.get('replay_matches') for r in rounds):
            problems.append(f'{level}: a round does not replay')
    if set(cells) - set(frozen):
        problems.append('cells for levels the manifest does not hold')
    return problems


def report(results):
    """A Markdown table of results side by side, each cell with its intervals."""
    lines = ['| agent | level | money (95% CI) | goal (95% CI) | gain over scripted solo | agent share of work | calls |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for result in results:
        name = result['agent']['spec'] + (f" ({', '.join(result['agent']['models'])})" if result['agent'].get('models') else '')
        for cell in result['cells']:
            s = cell['summary']
            goal = s['goal']
            lines.append(f"| {name} | {cell['level']} | {s['money_mean']} {s['money_ci95']} | {goal['share']} {goal['ci95']} "
                         f"| {s['gain_over_scripted_solo_mean']} | {s['agent_share_of_contributing_mean']} | {s['ai_calls_mean']} |")
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    playing = commands.add_parser('run', help='play every cell of a benchmark version')
    playing.add_argument('--agent', required=True, help="jeff, or module:Class of an environment.Agent")
    playing.add_argument('--out', required=True, help='folder for journals, bundles and result.json (not logs/)')
    playing.add_argument('--version', default='v1')
    playing.add_argument('--parallel', type=int, default=1)
    playing.add_argument('--dry-run', action='store_true', help="print the most it can cost and play nothing")
    checking = commands.add_parser('verify', help='check a result against its benchmark version')
    checking.add_argument('result')
    tables = commands.add_parser('report', help='compare results in one table')
    tables.add_argument('results', nargs='+')
    args = parser.parse_args(argv)
    if args.command == 'verify':
        result = json.loads(Path(args.result).read_text(encoding='utf-8'))
        problems = verify(result, read_manifest(result.get('version', 'v1')))
        print(json.dumps({'counts': not problems, 'problems': problems}, ensure_ascii=False, indent=2))
        return 0 if not problems else 1
    if args.command == 'report':
        print(report([json.loads(Path(p).read_text(encoding='utf-8')) for p in args.results]))
        return 0
    manifest = read_manifest(args.version)
    if refreeze(manifest) != manifest:
        print('this checkout no longer matches the manifest; a result made here would not count', file=sys.stderr)
        return 1
    from scripts.model_rounds import estimate
    cost = [estimate(level['id'], manifest['rounds_per_cell']) for level in manifest['levels']]
    print(json.dumps({'rounds': sum(c['rounds'] for c in cost), 'max_requests': sum(c['max_requests'] for c in cost),
                      'max_input_tokens_m': round(sum(c['max_input_tokens_m'] for c in cost), 2),
                      'max_cost_usd_at_jev_price': round(sum(c['max_cost_usd'] for c in cost), 2),
                      'minutes_of_play': round(sum(c['minutes_of_play'] for c in cost), 1)}), file=sys.stderr)
    if args.dry_run:
        return 0
    agent_factory(args.agent)          # a wrong spec fails here, before anything is played
    result = run(args.agent, args.out, manifest, args.parallel)
    print(report([result]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
