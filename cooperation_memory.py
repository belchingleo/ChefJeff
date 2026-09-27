"""Bounded factual episode records, not inferred player preferences or model reasoning."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

ROUNDS = 3
EVENTS = 18
KINDS = {'action_done', 'thrown', 'caught', 'landed', 'washed', 'served',
         'bad_service', 'burn', 'fire', 'expired', 'arrival_conflict'}


def scope_for(setting):
    # Keys and account identities never enter memory. A different model gets a fresh scope.
    identity = [setting.get(k, '') for k in ('provider', 'base_url', 'model')]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()


def sample_events(events):
    records = []
    for e in events:
        if e.get('kind') not in KINDS:
            continue
        if e.get('kind') == 'action_done' and str(e.get('action', '')).startswith(('go ', 'throw ')):
            continue
        record = {k: e[k] for k in ('t', 'kind', 'actor', 'action', 'item', 'stage', 'source', 'target', 'aim', 'message') if k in e}
        records.append(record)
    # Deterministic temporal sampling, with human actions and world/partner outcomes separate.
    groups = ([r for r in records if r.get('actor') == 'human'],
              [r for r in records if r.get('actor') != 'human'])
    out = []
    for group, limit in zip(groups, (12, 6)):
        if len(group) > limit:
            group = [group[round(i*(len(group)-1)/(limit-1))] for i in range(limit)]
        out.extend(group)
    return sorted(out, key=lambda r: r['t']), len(records)


def episode(kitchen, game_id, model):
    events, count = sample_events(kitchen.events)
    return {'round_id': game_id, 'model': model, 'duration': round(kitchen.time, 2),
            'outcome': {'served': kitchen.served, 'money': kitchen.money,
                        'bad_reviews': kitchen.bad_reviews, 'won': kitchen.won()},
            'layout': kitchen.snapshot().get('map',{}).get('layout_version','practice-kitchen-v1'),
            'events': events, 'eligible_event_count': count,
            'sampled': count > len(events)}


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
        while len(data['scopes']) > 8:
            del data['scopes'][next(iter(data['scopes']))]
        self.save(data)

    def context(self, scope):
        enabled = self.data['enabled']
        rounds = self.data['scopes'].get(scope, []) if enabled else []
        return {'enabled': enabled, 'version': 1, 'episodes': json.loads(json.dumps(rounds)),
                'description': '同一本地玩家与当前接口/模型的过往已结束对局。事件为按时间抽样的事实，非完整录像、非玩家偏好结论；物品编号和坐标仅属于各自旧局。'}
