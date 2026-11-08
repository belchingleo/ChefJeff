#!/usr/bin/env python3
"""Does the reach note change whether Jeff passes what he holds across a split floor? Run locally; it asks a model.

    python3 scripts/reach_note_check.py logs/ [--since 2026-11-08] [--sample 6] [--local http://127.0.0.1:8090/v1/systemone] [--dry-run]

From local round journals this picks the requests of level-4-style rounds (a floor the counters split) at which
Jeff held a raw ingredient the menu needs prepared (chopped, cooked) while no board was on his side, so the only
way on is to pass it: leave it on a counter both chefs can reach (a put, or a swap that puts it there), or
throw it to the partner. Each is sent again,
re-asking the logged request instead of playing new rounds:

- as_logged: exactly as it was sent (these rounds ran with reach_note off);
- reach_note: the same, with what the reach_note switch adds (reach_note.apply): rules.reach and the version.

Both arms ask next_action only: the other questions (sprint, plan) are left out of both alike, since a decision
model reads the whole request once per question and on a CPU each read takes minutes. The game's own requests
do not change. Which stations each chef reaches is worked out as the game does (SpatialKitchen.reaches), on the
logged round's map (its config hash must match) with the chefs where the request says they stood.

For each arm it reports how often the answer passed, how often it was the logged answer, and, when the model
gives option probabilities (a decision service), the probability it put on the passing options: the mean per arm
and the paired change per moment. The report holds counts, shares and probabilities only (no request, state or
model text). It reads the journals and changes nothing.

--local URL asks the decision service at that address on this computer (player_api local-decision, no key, no
saved connection read). --bamboo asks StartLux-Decision on Bamboo Relay (player_api startlux, free during its
test) with the key in ~/.config/chefjeff/bamboo.key, which only its owner may read; the key goes only into that
request's header and is never printed. --hf-space asks StartLux's own demo Space on Hugging Face
(startlux-models/startlux-decision-27b-autothink, its /decide endpoint, shared GPU) with the same state and
questions, think_mode never and allow_none off as on Bamboo; it is a demo, so its queue time is not a model's
reply time. Anonymous runs get a few a day; a Hugging Face token in ~/.config/chefjeff/hf.token (owner-only) raises
the quota and is sent only to that Space. Without any of these, it asks through the connection saved in the game
(jev_replay_check.client), whose key is read the way the game reads it and never printed: run that one yourself,
in your own terminal.
--dry-run picks the moments and prints their number and size without asking anything.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import reach_note  # noqa: E402
from scripts.decision_stats import read_rounds  # noqa: E402
from scripts.jev_replay_check import estimate, journals, pick, share  # noqa: E402
from scripts import reask  # noqa: E402

ARMS = ('as_logged', 'reach_note')
_KITCHENS = {}


def kitchen_for(state):
    """A fresh kitchen of the logged round's level with the chefs where the request says they stood, or None if
    this checkout builds that level differently (another config hash) or the floor is in one piece."""
    from kitchen import load_config
    from levels import level_config
    from spatial_kitchen import SpatialKitchen
    k = state['kitchen']
    level = k.get('level')
    if level not in _KITCHENS:
        try:
            _KITCHENS[level] = SpatialKitchen(dict(level_config(load_config(), level)))
        except (KeyError, ValueError, TypeError):
            _KITCHENS[level] = None
    fresh = _KITCHENS[level]
    if fresh is None or not fresh.split_floor or fresh.config_hash != k.get('config_hash'):
        return None
    for who in ('jeff', 'human'):
        fresh.positions[who] = tuple(k['chefs'][who]['position'])
    return fresh


def must_pass(kitchen_state, reach):
    """Whether Jeff holds a raw ingredient the menu wants prepared and no board is on his side."""
    held = kitchen_state['chefs']['jeff'].get('holding')
    if not isinstance(held, dict) or held.get('stage') != 'raw' or not held.get('ingredient'):
        return False
    wanted = {c.get('state') for dish in kitchen_state.get('menu') or [] for c in dish.get('components') or []
              if c.get('item') == held['ingredient']}
    boards = [name for name, station in kitchen_state['stations'].items() if station.get('type') == 'board']
    return bool(wanted - {'raw'}) and bool(boards) and not set(boards) & set(reach['jeff'] + reach['both'])


def put_station(key):
    """Where an option puts what Jeff holds: a plain put, or the put of a put-then-take swap; else None."""
    if key.startswith('put then take '):
        return key[len('put then take '):]
    if key.startswith('put ') and not key.startswith(('put then ', 'put pot ')):
        return key[4:]
    return None


def passing(payload, reach):
    """The next_action options that pass what Jeff holds: it ends on a station both reach (a put, or a swap that
    puts it there), or is thrown to the partner."""
    return [key for key in payload['questions']['next_action']['criteria']
            if key == 'throw partner' or put_station(key) in reach['both']]


def moments(paths, since=None, until=None):
    """[{payload, noted, reach, passing, logged_choice, round}] for answered requests on a split floor where Jeff held
    a raw ingredient he could only get prepared by passing it."""
    found, number = [], 0
    for path in journals(paths):
        for rows in read_rounds(path)[0]:
            start = rows[0] if rows and rows[0].get('kind') == 'start' else {}
            day = str(start.get('wall_time') or '')[:10]
            if (since and (not day or day < since)) or (until and (not day or day > until)):
                continue
            number += 1
            answers = {r.get('request_id'): r for r in rows if r.get('kind') == 'ai_response'}
            for row in rows:
                payload = row.get('payload')
                if row.get('kind') != 'ai_request' or not isinstance(payload, dict):
                    continue
                answer = answers.get(row.get('request_id'))
                state = payload.get('state') or {}
                if (answer is None or not isinstance(answer.get('choice'), str) or 'reach_note_version' in state
                        or not isinstance(state.get('kitchen'), dict)
                        or (state['kitchen'].get('chefs') or {}).get('jeff', {}).get('holding') is None):
                    continue
                kitchen = kitchen_for(state)
                if kitchen is None:
                    continue
                noted = deepcopy(payload)
                reach = reach_note.apply(noted, kitchen)      # exactly what the switch adds in the game
                options = passing(payload, reach)
                if options and must_pass(state['kitchen'], reach):
                    found.append({'payload': payload, 'noted': noted, 'reach': reach, 'passing': options,
                                  'logged_choice': answer['choice'], 'round': number})
    return found


def arm(item, name):
    payload = deepcopy(item['noted'] if name == 'reach_note' else item['payload'])
    payload['questions'] = {'next_action': payload['questions']['next_action']}
    return payload


def ask_once(ask, payload):
    try:
        answer = ask(deepcopy(payload))
        return {'choice': answer['choice'], 'probabilities': answer.get('probabilities') or {}, 'model': answer.get('model')}
    except RuntimeError as error:    # the client's own sanitized message, never the key
        return {'error': str(error)}


def pass_mass(item, answer):
    """The probability the answer put on the passing options, or None without probabilities."""
    p = answer.get('probabilities') or {}
    return round(sum(float(p.get(k, 0)) for k in item['passing']), 4) if p else None


OUTCOMES = {
    'passed': lambda i, p, a: a['choice'] in i['passing'],
    'same_as_logged': lambda i, p, a: a['choice'] == i['logged_choice'],
}


def run(items, ask, arms_asked=ARMS, repeats=1):
    out = {'moments': len(items), 'rounds': len({i['round'] for i in items}), 'repeats': repeats,
           'questions_asked': ['next_action'],
           'logged': {'passed': share(sum(i['logged_choice'] in i['passing'] for i in items), len(items))}, 'arms': {}}
    # Moment by moment, both arms back to back: a quota or budget that runs out midway leaves whole pairs.
    asked = {'arms': {name: [] for name in arms_asked}, 'models': Counter()}
    for item in items:
        one = reask.ask_arms([item], arms_asked, arm, ask, ask_once, repeats)
        for name in arms_asked:
            asked['arms'][name] += one['arms'][name]
        asked['models'].update(one['models'])
    asked['models'] = dict(asked['models'].most_common())
    masses = {}
    for name, rows in asked['arms'].items():
        errors, answered_, mass = Counter(), [], []
        for item, _, replies in rows:
            for answer in replies:
                if 'error' in answer:
                    errors[answer['error']] += 1
                else:
                    answered_.append((item, answer))
            first = replies[0] if replies and 'error' not in replies[0] else None
            mass.append(pass_mass(item, first) if first else None)
        masses[name] = mass
        known = [m for m in mass if m is not None]
        out['arms'][name] = {'asked': len(items) * repeats, 'answered': len(answered_),
                             'passed': share(sum(a['choice'] in i['passing'] for i, a in answered_), len(answered_)),
                             'same_as_logged': share(sum(a['choice'] == i['logged_choice'] for i, a in answered_), len(answered_)),
                             'pass_probability_mean': round(statistics.fmean(known), 4) if known else None,
                             'errors': dict(errors.most_common())}
    if len(arms_asked) > 1:
        base = masses[arms_asked[0]]
        for name in arms_asked[1:]:
            changes = [round(b - a, 4) for a, b in zip(base, masses[name]) if a is not None and b is not None]
            out['arms'][name]['pass_probability_change'] = {
                'moments': len(changes), 'per_moment': changes,
                'mean': round(statistics.fmean(changes), 4) if changes else None,
                'up': sum(c > 0 for c in changes), 'down': sum(c < 0 for c in changes), 'same': sum(c == 0 for c in changes)}
    out['stats'] = reask.stats(asked, OUTCOMES)
    return out


def local_client(url, model):
    """The decision service on this computer, as the game's local-decision setting asks it: no key, no saved file."""
    from kitchen import load_config
    import player_api
    setting = player_api.settings_from({'provider': 'local-decision', 'base_url': url, 'model': model})
    print(f'asking the decision service at {setting["base_url"]} ({setting["model"]}), no key', file=sys.stderr)
    return player_api.create_client(load_config(), setting)


BAMBOO_KEY = Path.home() / '.config/chefjeff/bamboo.key'
HF_TOKEN = Path.home() / '.config/chefjeff/hf.token'


def private_secret(path):
    """A key from a file only its owner may read, checked to be one printable word (a stray arrow key or paste
    marker in it would make the request header invalid). The value is returned, never printed."""
    import os
    import stat
    import unicodedata
    try:
        mode = os.stat(path).st_mode
    except OSError:
        raise SystemExit(f'no key file at {path}') from None
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise SystemExit(f'{path} can be read by other users; chmod 600 it first')
    value = path.read_text(encoding='utf-8').strip()
    odd = [(i, unicodedata.name(c, 'U+%04X' % ord(c))) for i, c in enumerate(value) if not 33 <= ord(c) < 127]
    if not value or odd:
        raise SystemExit(f'{path} is empty or holds characters a key cannot have, e.g. {odd[:2]}; save it again')
    return value


def bamboo_client(path=BAMBOO_KEY, timeout=120):
    """StartLux on Bamboo Relay, as the game's startlux setting asks it, with the key from a private file."""
    from kitchen import load_config
    import player_api
    setting = player_api.settings_from({'provider': 'startlux', 'api_key': private_secret(path)})
    client = player_api.create_client(load_config(), setting)
    client.timeout = timeout          # an offline check: a long request may take Bamboo more than the game's 8 s
    print(f'asking {setting["base_url"]} ({setting["model"]}) with the key from {path} (not printed)', file=sys.stderr)
    return client


HF_SPACE = 'startlux-models/startlux-decision-27b-autothink'


class SpaceClient:
    """StartLux's demo Space through its Gradio API (/decide), answering like the game's decision client."""

    def __init__(self, space=HF_SPACE, timeout=300, opener=None, token=None):
        import urllib.request
        self.space, self.timeout = space, timeout
        # A Hugging Face token raises the shared GPU's quota; it only ever goes to this Space's own address.
        self.headers = {'Authorization': 'Bearer ' + token} if token else {}
        self.base = 'https://' + space.replace('/', '-').replace('.', '-').lower() + '.hf.space/gradio_api'
        self.opener = opener or urllib.request.build_opener()

    def _json(self, request):
        with self.opener.open(request, timeout=self.timeout) as r:
            return json.load(r)

    def ask(self, payload):
        import time
        import urllib.error
        import urllib.request
        from model_language import english_data
        payload = english_data(payload)          # as the game's decision client sends it
        criteria = payload['questions']['next_action']['criteria']
        data = [json.dumps(payload['state'], ensure_ascii=False), json.dumps(payload['questions'], ensure_ascii=False),
                None, 'never', 0.6, 512, 0.75, True, False, False]
        started = time.monotonic()
        try:
            call = self._json(urllib.request.Request(self.base + '/call/decide', data=json.dumps({'data': data}).encode(),
                                                     headers={**self.headers, 'Content-Type': 'application/json'}, method='POST'))
            event, result = None, None
            with self.opener.open(urllib.request.Request(f"{self.base}/call/decide/{call['event_id']}", headers=self.headers),
                                  timeout=self.timeout) as stream:
                for raw in stream:
                    line = raw.decode('utf-8', 'replace').rstrip('\n')
                    if line.startswith('event: '):
                        event = line[7:]
                    elif line.startswith('data: ') and event in ('complete', 'error'):
                        result = (event, line[6:])
                        break
        except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
            raise RuntimeError(f'Space {type(error).__name__}' + (f' HTTP {error.code}' if hasattr(error, 'code') else '')) from None
        if result is None or result[0] != 'complete':
            raise RuntimeError('Space error: ' + (result[1][:160] if result else 'no answer'))
        try:
            raw = json.loads(result[1])[1]
            answer = raw['answers']['next_action']
        except (ValueError, TypeError, KeyError, IndexError):
            raise RuntimeError('Space answer not readable') from None
        if answer.get('type') != 'choice' or answer.get('choice') not in criteria:
            raise RuntimeError('Space chose outside the offered options')
        return {'choice': answer['choice'], 'probabilities': answer.get('probabilities') or {},
                'confidence': answer.get('confidence'), 'model': 'hf-space:' + self.space,
                'usage': raw.get('usage', {}), 'latency': time.monotonic() - started}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('paths', nargs='+', help='local round journals (logs/) or files')
    parser.add_argument('--since', help='first day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--until', help='last day of rounds to use, YYYY-MM-DD')
    parser.add_argument('--sample', type=int, default=6, help='moments to pick')
    parser.add_argument('--repeats', type=int, default=1, help='times each moment is asked in each arm')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--start', type=int, default=0, help='skip this many of the picked moments (to go on after a quota ran out)')
    parser.add_argument('--arms', default=','.join(ARMS), help='comma-separated arms to send: ' + ', '.join(ARMS))
    parser.add_argument('--local', metavar='URL', help='a decision service on this computer, e.g. http://127.0.0.1:8090/v1/systemone')
    parser.add_argument('--model', default='startlux-local-2b-instant-q4', help='with --local: the model name')
    parser.add_argument('--bamboo', action='store_true', help='StartLux on Bamboo Relay, key from ' + str(BAMBOO_KEY))
    parser.add_argument('--hf-space', action='store_true', help="StartLux's demo Space on Hugging Face: " + HF_SPACE)
    parser.add_argument('--dry-run', action='store_true', help='pick the moments and print their number and size only')
    parser.add_argument('--out', help='write the JSON report here instead of printing it')
    args = parser.parse_args(argv)
    arms_asked = tuple(a for a in args.arms.split(',') if a)
    if not arms_asked or set(arms_asked) - set(ARMS):
        parser.error('--arms takes ' + ', '.join(ARMS))
    if args.repeats < 1:
        parser.error('--repeats takes 1 or more')
    found = moments(args.paths, args.since, args.until)
    items = pick(found, args.sample, args.seed)[max(0, args.start):]
    if not items:
        print('no request in those journals and days had Jeff holding a raw ingredient he could only pass on a split floor')
        return 1
    print(f"{len(found)} moments found, {len(items)} picked from {len({i['round'] for i in items})} rounds; "
          f"logged answers passed {share(sum(i['logged_choice'] in i['passing'] for i in items), len(items))}",
          file=sys.stderr)
    print(estimate([{'payload': arm(i, 'reach_note')} for i in items], len(arms_asked) * args.repeats), file=sys.stderr)
    if args.dry_run:
        return 0
    if sum(map(bool, (args.local, args.bamboo, args.hf_space))) > 1:
        parser.error('one of --local, --bamboo and --hf-space')
    if args.local:
        ask = local_client(args.local, args.model).ask
    elif args.bamboo:
        ask = bamboo_client().ask
    elif args.hf_space:
        token = private_secret(HF_TOKEN) if HF_TOKEN.exists() else None
        print(f'asking the Hugging Face Space {HF_SPACE} ' + (f'with the token from {HF_TOKEN} (not printed)' if token else
              '(no token: the shared GPU allows only a few anonymous runs a day)'), file=sys.stderr)
        ask = SpaceClient(token=token).ask
    else:
        from scripts.jev_replay_check import client
        ask = client().ask
    text = json.dumps(run(items, ask, arms_asked, args.repeats), ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
