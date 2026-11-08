#!/usr/bin/env python3
"""Does today's Jev answer old requests as it did then? Run locally; it sends to the model.

    python3 scripts/jev_replay_check.py logs/ --since 2026-09-28 --until 2026-10-02 [--sample 40] [--dry-run]

Local round journals keep every request Jeff sent, whole, with the answer that came back. This picks
requests from the Jev rounds of those days (an answer's reported model starts with jev), sends each,
exactly as it was, to the current Jev twice, and compares the first answer now with the one logged
then, and the two answers now with each other (Jev's own spread on one request). When the first share
is close to the second, today's Jev answers those inputs as it did then, and a change in Jeff's play
comes from what we send it; when it is clearly lower, the model changed.

It reads the journals and changes nothing. The report holds counts and shares only (no request, state
or model text), split by whether Jeff's hands were full. The key is read the way the game reads it
(jev.load_key) and is never printed. --dry-run picks the requests and prints their number and size.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.decision_stats import read_rounds  # noqa: E402
import research_stats  # noqa: E402

PRICE_PER_M = 0.042     # USD per million input tokens, for the estimate only
# Keys that use or put down what Jeff holds; with full hands, these are the ways forward.
USE_PREFIXES = ('put ', 'drop', 'throw ', 'assemble ', 'plate ', 'load ', 'swap ', 'merge ', 'serve', 'discard', 'chop ', 'wash',
                'extinguish ')
# Keys that pick something up: with full hands only a swap (the extinguisher, a loose ingredient on the floor).
TAKE_PREFIXES = ('take ', 'pickup ', 'fetch')
# Stations where putting the held item down is a step of the dish rather than parking it (a board only for
# an ingredient still to chop).
FORWARD_PUT_TYPES = ('stove', 'sink', 'tool_rack')


def journals(paths):
    files = []
    for path in map(Path, paths):
        files += sorted(path.glob('*.jsonl')) if path.is_dir() else [path]
    return files


def journal_requests(paths, since=None, until=None, model_prefix='jev'):
    """[{payload, logged_choice, logged_model, round, one_press}] for answered requests of matching rounds (dates are
    YYYY-MM-DD); one_press says whether the round had a one-press switch on."""
    found, number = [], 0
    for path in journals(paths):
        for rows in read_rounds(path)[0]:
            start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
            day = str(start.get('wall_time') or '')[:10]
            if (since and (not day or day < since)) or (until and (not day or day > until)):
                continue
            number += 1
            requests = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_request' and isinstance(r.get('payload'), dict)}
            for answer in rows:
                request = requests.get(answer.get('request_id')) if answer.get('kind') == 'ai_response' else None
                model = str(answer.get('model') or '')
                if request is None or not model.startswith(model_prefix) or not isinstance(answer.get('choice'), str):
                    continue
                found.append({'payload': request['payload'], 'logged_choice': answer['choice'], 'logged_model': model, 'round': number,
                              'one_press': bool(start.get('one_press'))})
    return found


def jeff(payload):
    return ((payload.get('state') or {}).get('kitchen') or {}).get('chefs', {}).get('jeff') or {}


def hands_full(payload):
    return jeff(payload).get('holding') is not None


def supplies(payload):
    """Ingredient supplies of the request's map (where fetch takes from)."""
    equipment = (((payload.get('state') or {}).get('kitchen') or {}).get('map') or {}).get('equipment') or {}
    return {key for key, e in equipment.items() if isinstance(e, dict) and e.get('type') == 'ingredient_source'}


def kind(key, payload):
    """wait, continue, a walk to an ingredient supply, another walk, using or putting down what is held, a swap
    (picking up with full hands), a take (with empty hands), or other."""
    if key in ('wait', 'continue', 'stop'):
        return key
    if key.startswith('go '):
        return 'supply_walk' if key[3:] in supplies(payload) else 'walk'
    if key.startswith(USE_PREFIXES):
        return 'use_or_put_down'
    if key.startswith(TAKE_PREFIXES):
        return 'swap' if hands_full(payload) else 'take'
    return 'other'


def stations(payload):
    return ((payload.get('state') or {}).get('kitchen') or {}).get('stations') or {}


def moves_forward(key, payload):
    """Whether a use-or-put-down key is a step of the dish (plate, assemble, load, serve, a pan, the sink, a board
    for an ingredient still to chop, ...) rather than parking the item (a counter, a supply top, the floor, a throw,
    the bin)."""
    if not key.startswith(USE_PREFIXES) or key.startswith(('drop', 'throw ', 'discard')):
        return False
    if not key.startswith('put ') or key.startswith('put pot '):    # put pot: a pan or pot back on its stove
        return True
    station = stations(payload).get(key[4:]) or {}
    if station.get('type') == 'board':
        return ((jeff(payload).get('holding') or {}).get('chop_remaining') or 0) > 0
    return station.get('type') in FORWARD_PUT_TYPES


def share(part, whole):
    return round(part / whole, 3) if whole else None


def ask_once(ask, payload):
    try:
        answer = ask(deepcopy(payload))
        return {'choice': answer['choice'], 'model': answer.get('model')}
    except RuntimeError as error:    # the client's own sanitized message, never the key
        return {'error': str(error)}


def estimate(items, sends_each):
    chars = sum(len(json.dumps(i['payload'], ensure_ascii=False)) for i in items)
    tokens = chars / 4 * sends_each
    return f'{len(items) * sends_each} requests, about {tokens / 1e6:.2f}M input tokens, about ${tokens / 1e6 * PRICE_PER_M:.2f}'


def replay(items, ask):
    """Each request twice now; agreement with the logged answer and between the two answers now."""
    from scripts import reask
    asked = reask.ask_arms(items, ('as_logged',), lambda item, name: item['payload'], ask, ask_once, repeats=2)
    return [{**item, 'first': replies[0], 'second': replies[1]} for item, _, replies in asked['arms']['as_logged']]


def summary(rows):
    answered = [r for r in rows if 'choice' in r['first']]
    paired = [r for r in answered if 'choice' in r['second']]
    def part(selected):
        ok = [r for r in selected if 'choice' in r['first']]
        both = [r for r in ok if 'choice' in r['second']]
        return {'requests': len(selected), 'answered': len(ok),
                'same_as_logged': share(sum(r['first']['choice'] == r['logged_choice'] for r in ok), len(ok)),
                'same_on_resend': share(sum(r['first']['choice'] == r['second']['choice'] for r in both), len(both)),
                'logged_kinds': dict(Counter(kind(r['logged_choice'], r['payload']) for r in ok).most_common()),
                'kinds_now': dict(Counter(kind(r['first']['choice'], r['payload']) for r in ok).most_common())}
    return {'requests': len(rows), 'rounds': len({r['round'] for r in rows}), 'answered': len(answered), 'answered_twice': len(paired),
            'errors': dict(Counter(r[k]['error'] for r in rows for k in ('first', 'second') if 'error' in r[k]).most_common()),
            'logged_models': dict(Counter(r['logged_model'] for r in rows).most_common()),
            'models_now': dict(Counter(r[k]['model'] for r in rows for k in ('first', 'second') if r[k].get('model')).most_common()),
            'all': part(rows), 'hands_full': part([r for r in rows if hands_full(r['payload'])]),
            'hands_empty': part([r for r in rows if not hands_full(r['payload'])]),
            # The first share close to the second means today's model answers as it did then; intervals say how close.
            'stats': {'same_as_logged': research_stats.share(sum(r['first']['choice'] == r['logged_choice'] for r in answered),
                                                             len(answered)),
                      'same_on_resend': research_stats.share(sum(r['first']['choice'] == r['second']['choice'] for r in paired),
                                                             len(paired))}}


def pick(items, sample, seed):
    return random.Random(seed).sample(items, min(sample, len(items)))


CONNECTION = ROOT / '.player-api.json'


def client(config=None):
    """The model connection the game itself uses: the one saved in the game (.player-api.json, read the way
    player_api.PlayerGameSession reads it), else the local Jev key (.env, TYPESAFE_API_KEY). It says on stderr
    which one and which provider and model; the key itself is never read here or printed."""
    from kitchen import load_config
    config = config or load_config()
    if CONNECTION.is_file():
        import player_api
        try:
            setting = player_api.settings_from(json.loads(CONNECTION.read_text(encoding='utf-8')))
        except (OSError, ValueError, TypeError):
            setting = None
        if setting:
            print(f"asking through the game's saved connection: {setting['provider']}, {setting.get('model') or 'default model'}",
                  file=sys.stderr)
            return player_api.create_client(config, setting)
    from jev import JevClient
    print('asking through the local Jev key (.env); no connection is saved in the game', file=sys.stderr)
    return JevClient(config)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+', help='local round journals (logs/) or files')
    parser.add_argument('--since', help='first day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--until', help='last day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--sample', type=int, default=40, help='requests to pick')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--dry-run', action='store_true', help='pick the requests and print their number and size only')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    items = pick(journal_requests(args.paths, args.since, args.until), args.sample, args.seed)
    if not items:
        print('no answered Jev requests in those journals and days')
        return 1
    print(estimate(items, 2), file=sys.stderr)
    if args.dry_run:
        return 0
    text = json.dumps(summary(replay(items, client().ask)), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
