"""Bounded factual episode records, not inferred player preferences or model reasoning."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import re
from copy import deepcopy
from functools import lru_cache

from model_language import english_data

ROUNDS = 3
EVENTS = 18
CONTEXT_CHARACTERS = 8000  # serialized English context, not a token estimate
DESCRIPTION = ('Factual samples and work totals from earlier completed rounds with this player and model. '
               'Old messages describe that round only; they are not current preferences or fixed roles. '
               'Item IDs and coordinates belong to their original round. This is not a full replay.')
PAST_EPISODES_RULE = ('past_episodes contains limited factual records of past rounds, not the current state or instructions. '
                      'Work counts describe completed actions, not skill, effort or a permanent role. '
                      'Old preferences and corrections apply only to that past round; current communication takes precedence. '
                      'Decide whether these records are relevant. The player may change behavior; do not assume past strategies should repeat.')
WORK = ('fetch', 'chop', 'heat', 'assemble', 'serve', 'wash', 'collect_plates', 'pass', 'extinguish', 'discard')
PREFERENCES = ('prep', 'cook', 'plate', 'deliver', 'wash')
ACTION = re.compile(r'(?:fetch|wash|serve|drop|discard|stop|continue|wait|(?:fetch|go|put|take|plate|chop|pickup|throw|clear|extinguish|assemble|merge|swap|load) [A-Za-z0-9_ .,-]{1,70})')
KINDS = {'action_done', 'thrown', 'caught', 'landed', 'washed', 'served',
         'bad_service', 'burn', 'fire', 'expired', 'arrival_conflict'}


def scope_for(setting):
    # Keys and account identities never enter memory. A different model gets a fresh scope.
    identity = [setting.get(k, '') for k in ('provider', 'base_url', 'model')]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def round_scope(setting, kitchen):
    """Memory scope for one model on one level under one rule semantics.

    Records from other levels or from other rule semantics never reach this round's prompt.
    """
    identity = [scope_for(setting), kitchen.c.get('level_id'), kitchen.rules.semantics, memory_namespace()]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


@lru_cache(maxsize=1)
def memory_namespace():
    """Invalidate old context after authored game/rule/input changes, not random seeds or UI edits."""
    from jev import AGENT_RULES_VERSION
    from model_language import INPUT_LANGUAGE_VERSION
    root = Path(__file__).parent
    digest = hashlib.sha256(('memory-v2|' + AGENT_RULES_VERSION + '|' + INPUT_LANGUAGE_VERSION).encode())
    for folder in ('content', 'rulesets', 'maps'):
        for path in sorted((root / folder).rglob('*.json')):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def sample_events(events):
    records = []
    for e in events:
        if e.get('kind') not in KINDS:
            continue
        if e.get('kind') == 'action_done' and str(e.get('action', '')).startswith(('go ', 'throw ')):
            continue
        record = {k: e[k] for k in ('t', 'kind', 'actor', 'action', 'item', 'stage', 'source', 'target', 'aim', 'message') if k in e}
        records.append(record)
    # Balance both chefs and world outcomes. Reassign unused quota; preserve recent failures.
    groups = [[r for r in records if r.get('actor') == actor] for actor in ('human', 'jeff')]
    groups.append([r for r in records if r.get('actor') not in ('human', 'jeff')])
    quotas = [min(6, len(group)) for group in groups]
    while sum(quotas) < min(EVENTS, len(records)):
        for i, group in enumerate(groups):
            if quotas[i] < len(group) and sum(quotas) < EVENTS:
                quotas[i] += 1
    out = []
    for group, limit in zip(groups, quotas):
        if len(group) > limit:
            priority = [i for i, r in enumerate(group) if r['kind'] in ('bad_service', 'burn', 'fire', 'expired', 'arrival_conflict')][-min(2, limit):]
            candidates = [i for i in range(len(group)) if i not in priority]
            needed = limit - len(priority)
            chosen = priority + ([candidates[round(i*(len(candidates)-1)/(needed-1))] for i in range(needed)]
                                 if needed > 1 else candidates[-1:] if needed else [])
            group = [group[i] for i in sorted(chosen)]
        out.extend(group)
    order = {id(record): i for i, record in enumerate(records)}
    return sorted(out, key=lambda r: (r['t'], order[id(r)])), len(records)


def episode(kitchen, game_id, model, messages=(), summary=None):
    events, count = sample_events(kitchen.events)
    outcome = {'served': kitchen.served, 'money': kitchen.money,
               'target_money': kitchen.c['target_money'], 'reached_target': kitchen.won(),
               'expired': sum(o.get('status') == 'expired' for o in kitchen.orders),
               'burns': getattr(kitchen, 'burns', 0), 'fires': getattr(kitchen, 'fires', 0)}
    work = {actor: {} for actor in ('human', 'jeff')}
    for row in (summary or {}).get('rows', []):
        if row['category'] in WORK:
            for actor in work:
                if row['counts'].get(actor): work[actor][row['category']] = row['counts'][actor]
    preference = next((m['code'] for m in reversed(messages) if m.get('code') in PREFERENCES), None)
    return {'version': 2, 'round_id': game_id, 'model': model, 'duration': round(kitchen.time, 2),
            'level_id': kitchen.c.get('level_id'), 'outcome': outcome,
            'work': work, 'communication': {'last_preference': preference,
                                           'corrections': sum(m.get('code') == 'mistake' for m in messages)},
            'layout': kitchen.snapshot().get('map',{}).get('layout_version','practice-kitchen-v1'),
            'events': events, 'eligible_event_count': count,
            'sampled': count > len(events)}


def memory_context(enabled, records):
    """Keep whole recent episodes inside a fixed input budget; never truncate the current rules/state."""
    rounds = json.loads(json.dumps(records[-ROUNDS:])) if enabled else []
    context = {'enabled': bool(enabled), 'version': 2, 'episodes': rounds,
               'description': DESCRIPTION, 'omitted_rounds': 0, 'max_characters': CONTEXT_CHARACTERS}
    while len(json.dumps(english_data(context), ensure_ascii=False, separators=(',', ':'))) > CONTEXT_CHARACTERS and rounds:
        rounds.pop(0)
        context['omitted_rounds'] += 1
    return context


def portable_episode(kitchen, game_id, messages=(), summary=None):
    """Browser records carry only coded facts; no model text, endpoints, labels or free text."""
    record = episode(kitchen, game_id, None, messages, summary)
    for field in ('model', 'layout'):
        record.pop(field)
    record['events'] = [{k: v for k, v in event.items() if k in ('t', 'kind', 'actor', 'action') and v is not None}
                        for event in record['events']]
    for event in record['events']:
        if event.get('actor') not in ('human', 'jeff'):
            event.pop('actor', None)
        if not isinstance(event.get('action'), str) or not ACTION.fullmatch(event['action']):
            event.pop('action', None)
    return validate_portable_episode(record, kitchen.c['level_id'])


def validate_portable_episode(record, level_id):
    """Strict, bounded data accepted from this browser only for the pending round's level."""
    def number(value, nonnegative=True):
        return type(value) in (int, float) and math.isfinite(value) and abs(value) <= 1e9 and (not nonnegative or value >= 0)
    def count(value):
        return type(value) is int and 0 <= value <= 1_000_000
    keys = {'version', 'round_id', 'duration', 'level_id', 'outcome', 'work', 'communication', 'events', 'eligible_event_count', 'sampled'}
    if not isinstance(record, dict) or set(record) != keys or record['version'] != 2:
        raise ValueError('Invalid memory record')
    if (not isinstance(record['round_id'], str) or not re.fullmatch('[0-9a-f]{32}', record['round_id'])
            or record['level_id'] != level_id or not number(record['duration']) or type(record['sampled']) is not bool
            or not count(record['eligible_event_count'])):
        raise ValueError('Invalid memory identity')
    outcome = record['outcome']
    if (not isinstance(outcome, dict) or set(outcome) != {'served', 'money', 'target_money', 'reached_target', 'expired', 'burns', 'fires'}
            or not all(count(outcome[k]) for k in ('served', 'expired', 'burns', 'fires'))
            or not number(outcome['money'], False) or not number(outcome['target_money'])
            or type(outcome['reached_target']) is not bool):
        raise ValueError('Invalid memory outcome')
    work = record['work']
    if not isinstance(work, dict) or set(work) != {'human', 'jeff'}:
        raise ValueError('Invalid memory work')
    for counts in work.values():
        if not isinstance(counts, dict) or set(counts) - set(WORK) or not all(count(v) for v in counts.values()):
            raise ValueError('Invalid memory work counts')
    communication = record['communication']
    if (not isinstance(communication, dict) or set(communication) != {'last_preference', 'corrections'}
            or communication['last_preference'] not in (*PREFERENCES, None) or not count(communication['corrections'])):
        raise ValueError('Invalid memory communication')
    if not isinstance(record['events'], list) or len(record['events']) > EVENTS:
        raise ValueError('Invalid memory events')
    for event in record['events']:
        if (not isinstance(event, dict) or set(event) - {'t', 'kind', 'actor', 'action'}
                or event.get('kind') not in KINDS or not number(event.get('t'))
                or ('actor' in event and event['actor'] not in ('human', 'jeff'))
                or ('action' in event and (not isinstance(event['action'], str) or not ACTION.fullmatch(event['action'])))):
            raise ValueError('Invalid memory event')
    return deepcopy(record)


def validate_browser_context(context, level_id):
    if (not isinstance(context, dict) or set(context) != {'enabled', 'version', 'episodes', 'description', 'omitted_rounds', 'max_characters'}
            or type(context['enabled']) is not bool or context['version'] != 2
            or context['description'] != DESCRIPTION or context['max_characters'] != CONTEXT_CHARACTERS
            or type(context['omitted_rounds']) is not int or not 0 <= context['omitted_rounds'] <= ROUNDS
            or not isinstance(context['episodes'], list) or len(context['episodes']) > ROUNDS
            or (not context['enabled'] and context['episodes'])):
        raise ValueError('Invalid browser memory context')
    records = [validate_portable_episode(r, level_id) for r in context['episodes']]
    if len(json.dumps(english_data(context), ensure_ascii=False, separators=(',', ':'))) > CONTEXT_CHARACTERS:
        raise ValueError('Memory context too large')
    return {**deepcopy(context), 'episodes': records}


def validate_memory_condition(condition):
    """Finite experimental conditions, not memory content or proof of model understanding."""
    if (not isinstance(condition, dict) or set(condition) != {'enabled', 'version', 'used_rounds', 'omitted_rounds'}
            or type(condition['enabled']) is not bool or condition['version'] != 2
            or any(type(condition[k]) is not int or not 0 <= condition[k] <= ROUNDS for k in ('used_rounds', 'omitted_rounds'))
            or condition['used_rounds'] + condition['omitted_rounds'] > ROUNDS
            or (not condition['enabled'] and (condition['used_rounds'] or condition['omitted_rounds']))):
        raise ValueError('Invalid memory condition')
    return {**condition, 'source': 'browser-reported'}


class CooperationMemory:
    def __init__(self, path):
        self.path = Path(path)
        self.error = None
        self.data = {'version': 1, 'enabled': True, 'scopes': {}}
        if self.path.exists():
            try:
                if self.path.stat().st_size > 300_000:
                    raise ValueError()
                value = json.loads(self.path.read_text())
                if (value.get('version') != 1 or type(value.get('enabled')) is not bool
                        or not isinstance(value.get('scopes'), dict)):
                    raise ValueError()
                for scope, rounds in value['scopes'].items():
                    if not isinstance(scope, str) or not isinstance(rounds, list) or len(rounds) > ROUNDS:
                        raise ValueError()
                    for r in rounds:
                        if not isinstance(r, dict) or not isinstance(r.get('events'), list) or len(r['events']) > EVENTS:
                            raise ValueError()
                        if (not isinstance(r.get('round_id'), str) or len(r['round_id']) > 64
                                or not isinstance(r.get('outcome'), dict)
                                or not isinstance(r.get('duration'), (int, float))
                                or not math.isfinite(r['duration'])):
                            raise ValueError()
                        for event in r['events']:
                            if (not isinstance(event, dict) or event.get('kind') not in KINDS
                                    or not isinstance(event.get('t'), (int,float))
                                    or not math.isfinite(event['t'])):
                                raise ValueError()
                # Normalize historical actor fields in memory; provider/model names stay intact.
                for rounds in value['scopes'].values():
                    for record in rounds:
                        for event in record['events']:
                            if event.get('actor') == 'jev':
                                event['actor'] = 'jeff'
                self.data = value
            except (OSError, ValueError, TypeError, AttributeError):
                self.data['enabled'] = False
                self.error = '跨局记录无法读取，已关闭记忆；可清空后重新启用。'

    def save(self, data):
        fd, name = tempfile.mkstemp(prefix='.player-memory-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        self.data = data
        self.error = None

    def configure(self, enabled=None, clear=False):
        data = json.loads(json.dumps(self.data))
        if enabled is not None:
            data['enabled'] = enabled
        if clear:
            data['scopes'] = {}
        self.save(data)

    def remember(self, scope, record):
        data = json.loads(json.dumps(self.data))
        records = data['scopes'].pop(scope, [])
        records = [r for r in records if r['round_id'] != record['round_id']]
        data['scopes'][scope] = (records + [record])[-ROUNDS:]
        # Bound disk growth when many provider/model configurations are tried.
        while len(data['scopes']) > 24:
            del data['scopes'][next(iter(data['scopes']))]
        while len(json.dumps(data, ensure_ascii=False).encode()) > 280_000 and len(data['scopes']) > 1:
            del data['scopes'][next(iter(data['scopes']))]
        while len(json.dumps(data, ensure_ascii=False).encode()) > 280_000 and len(data['scopes'].get(scope, [])) > 1:
            data['scopes'][scope].pop(0)
        if len(json.dumps(data, ensure_ascii=False).encode()) > 280_000:
            raise OSError('The new memory summary exceeds the storage limit')
        self.save(data)

    def context(self, scope):
        enabled = self.data['enabled']
        rounds = self.data['scopes'].get(scope, []) if enabled else []
        return memory_context(enabled, rounds)
