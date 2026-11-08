#!/usr/bin/env python3
"""Re-ask the model about logged moments in arms that change one thing, and say how sure the differences are.

    python3 scripts/reask.py list
    python3 scripts/reask.py <check> [the check's own arguments, e.g. logs/ --since 2026-11-04 --dry-run]

Each check keeps its own question: which logged moments it picks (walks, full hands, one-press put_where answers,
undo notes, split-floor passes, any answered request, or fixed emergencies), what each arm changes in the request, and the outcomes it
counts. They share what is the same in all of them, here:

- ask_arms: every arm asks every moment, the same number of times, in one fixed order (arm, then moment, then
  repeat), through the connection saved in the game, and records which model answered;
- stats: for each outcome, every arm's share with its 95% interval (research_stats.wilson); for the same moments
  under the first arm and each other arm, the paired difference and its exact McNemar p; with two or more asks per
  moment, how often an arm gave the same answer twice (the model's own spread, the floor any difference has to
  clear); and a note when a single model answered, since a wording that helps one model need not help another.

The reports hold counts and shares only (no request, state or model text). Nothing here changes a journal; each
check's --dry-run prints how many requests it would send before anything is sent.
"""
from __future__ import annotations
from collections import Counter
import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import research_stats  # noqa: E402

# name -> (module, what it asks)
CHECKS = {
    'replay': ('scripts.jev_replay_check', 'old requests, exactly as sent, to today\'s model twice'),
    'walk_labels': ('scripts.walk_label_check', 'walks with and without a label saying nothing else listed is there'),
    'hands_full': ('scripts.hands_full_check', 'stuck moments with full hands, as logged, without history, without supply walks'),
    'put_where': ('scripts.put_where_check', 'where one-press puts the held item, with and without the floor note'),
    'undo_note': ('scripts.undo_note_check', 'moments that could take back the last step, with and without the undo note'),
    'plan': ('scripts.plan_probe', 'fixed emergencies with Jeff\'s plan off, asked for, and held'),
    'reach_note': ('scripts.reach_note_check', 'split-floor moments Jeff could pass, with and without the reach note'),
}
SINGLE_MODEL = ('one model answered every arm; a change that helps it need not help another model, so check '
                'with a second connection before changing what Jeff is sent')


def ask_arms(items, arms, transform, ask, answer, repeats=1):
    """{'arms': {arm: [(item, payload, [answer per repeat])]}, 'models': {model: answers}}.

    transform(item, arm) is the request an arm sends for a moment; answer(ask, payload) asks once and returns the
    check's own answer record ({'error': ...} when the client refused). Every arm asks every moment repeats times,
    arm by arm, moment by moment."""
    models = Counter()

    def recorded(payload):
        reply = ask(payload)
        models[str(reply.get('model') or 'unreported')] += 1
        return reply
    out = {}
    for name in arms:
        rows = []
        for item in items:
            payload = transform(item, name)
            rows.append((item, payload, [answer(recorded, payload) for _ in range(repeats)]))
        out[name] = rows
    return {'arms': out, 'models': dict(models.most_common())}


def answered(reply):
    return isinstance(reply, dict) and 'error' not in reply


def stats(asked, outcomes):
    """Shares with intervals, paired differences against the first arm, and repeat agreement.

    asked is ask_arms' result; outcomes maps a name to outcome(item, payload, answer) -> True, False, or None when the
    outcome does not apply to that answer (it is then left out of that share)."""
    arms = asked['arms']
    names = list(arms)
    out = {'outcomes': {}, 'paired_with': names[0] if names else None, 'paired': {}, 'repeat_agreement': {}}
    for outcome, test in outcomes.items():
        shares, firsts = {}, {}
        for name, rows in arms.items():
            values = [test(item, payload, a) for item, payload, replies in rows for a in replies if answered(a)]
            values = [v for v in values if v is not None]
            shares[name] = research_stats.share(sum(bool(v) for v in values), len(values))
            firsts[name] = [test(item, payload, replies[0]) if replies and answered(replies[0]) else None
                            for item, payload, replies in rows]
        out['outcomes'][outcome] = shares
        out['paired'][outcome] = {name: research_stats.paired(firsts[names[0]], firsts[name]) for name in names[1:]}
    for name, rows in arms.items():
        twice = [(replies[0], replies[1]) for _, _, replies in rows if len(replies) > 1
                 and answered(replies[0]) and answered(replies[1])]
        if twice:
            out['repeat_agreement'][name] = research_stats.share(sum(a.get('choice') == b.get('choice') for a, b in twice),
                                                                 len(twice))
    out['models'] = asked['models']
    if len([m for m in asked['models'] if m != 'unreported']) <= 1:
        out['note'] = SINGLE_MODEL
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('list', '-h', '--help'):
        print(__doc__.split('\n\n')[0].strip() + '\n')
        for name, (_, about) in CHECKS.items():
            print(f'  {name:12s} {about}')
        return 0
    if argv[0] not in CHECKS:
        print(f'unknown check {argv[0]!r}; python3 scripts/reask.py list names them', file=sys.stderr)
        return 2
    return importlib.import_module(CHECKS[argv[0]][0]).main(argv[1:])


if __name__ == '__main__':
    raise SystemExit(main())
