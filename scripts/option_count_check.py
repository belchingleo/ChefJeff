#!/usr/bin/env python3
"""How many options Jeff is offered, and what he picks with few or many. Record only: no model call.

    python3 scripts/option_count_check.py logs/ [--since 2026-09-28] [--until 2026-11-04] [--split 25]

From local round journals it reads the answered requests of Jev rounds (an answer's reported model
starts with jev) and counts the options of next_action in each. Requests are grouped by the rules
version Jeff was sent (state.rules_version), so rounds before and after a change of rules are apart.
For each group it reports the number of requests and rounds, the median and largest number of
options, the share above --split, and the kinds of logged answers (scripts/jev_replay_check.kind: a
walk, wait, using or putting down what he holds and of those a step of the dish, a take or swap) for
requests with at most --split options and with more, each also with full hands only.

The report holds counts and shares only (no request, state or model text). It reads the journals and
changes nothing.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.jev_replay_check import hands_full, journal_requests, kind, moves_forward, share  # noqa: E402

SPLIT = 25


def options(item):
    return len(item['payload']['questions']['next_action']['criteria'])


def answers(items):
    """The kinds of logged answers of these requests, as shares."""
    kinds = Counter(('walk' if k == 'supply_walk' else 'take' if k == 'swap' else k)
                    for k in (kind(i['logged_choice'], i['payload']) for i in items))
    return {'requests': len(items),
            **{f'chose_{k}': share(kinds[k], len(items)) for k in ('walk', 'wait', 'use_or_put_down', 'take', 'continue')},
            'chose_a_step_of_the_dish': share(sum(moves_forward(i['logged_choice'], i['payload']) for i in items), len(items))}


def report(items, split=SPLIT):
    groups = defaultdict(list)
    for item in items:
        groups[str((item['payload'].get('state') or {}).get('rules_version') or 'not recorded')].append(item)
    out = {}
    for version, chosen in sorted(groups.items()):
        counts = [options(i) for i in chosen]
        few = [i for i in chosen if options(i) <= split]
        many = [i for i in chosen if options(i) > split]
        out[version] = {'requests': len(chosen), 'rounds': len({i['round'] for i in chosen}),
                        'median_options': median(counts), 'most_options': max(counts),
                        f'share_above_{split}': share(len(many), len(chosen)),
                        f'at_most_{split}': {'all': answers(few), 'hands_full': answers([i for i in few if hands_full(i['payload'])])},
                        f'above_{split}': {'all': answers(many), 'hands_full': answers([i for i in many if hands_full(i['payload'])])}}
    return {'split': split, 'rules_versions': out}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+', help='local round journals (logs/) or files')
    parser.add_argument('--since', help='first day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--until', help='last day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--split', type=int, default=SPLIT, help='compare requests with at most this many options and with more')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    items = journal_requests(args.paths, args.since, args.until)
    if not items:
        print('no answered Jev requests in those journals and days')
        return 1
    text = json.dumps(report(items, args.split), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
