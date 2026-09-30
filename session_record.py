"""One event stream per session, and the record bundle derived from it.

``SessionLog`` is the single sink for a round: engine events, engine inputs,
human inputs, model requests/responses, communication, bookmarks and pauses
all receive one session-wide ``seq`` and two clocks (engine game time and the
server's monotonic clock). Local journals, the Session bundle and hosted
contribution records are all derived from these records, so they cannot
drift apart.

Bundle layout (``write_bundle``)::

    session.json            identity, conditions, interfaces, timing, outcome
    resolved-config.json    the frozen configuration the engine ran
    events.jsonl            the unified stream (Session Schema event envelope)
    engine-inputs.jsonl     accepted external calls, for engine-level replay
    model-requests.jsonl    exact model payloads, referenced by request_id + sha256

Records never contain API keys, authorization headers or deletion secrets.
No cooperation, attention or quality score is computed here; ``derived`` holds
only defined factual counts.
"""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
import time

import config_contract as cc

SCHEMA_VERSION = 1
DERIVED_VERSION = 'derived-v1'
ENVELOPE = ('actor_id', 'action_id', 'request_id', 'order_id')
# Heavy fields kept out of the in-memory stream; payloads go to model-requests.jsonl.
STATE_FIELDS = ('current_state',)


def _sha(value):
    return hashlib.sha256(cc.canonical(value).encode('utf-8')).hexdigest()


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


class SessionLog:
    """Callable like a journal (``log(kind, data)``); wraps an optional file journal."""

    def __init__(self, session, journal=None, keep_payloads=False, deployment_mode='local'):
        self.session = session
        self.journal = journal
        self.keep_payloads = keep_payloads
        self.deployment_mode = deployment_mode
        self.records = []
        self.payloads = []
        self.started_at = _now_iso()
        self.ended_at = None
        self.monotonic_start = time.monotonic()
        self.closed = False

    def __getattr__(self, name):
        # Journal-specific attributes (e.g. a file path) stay reachable through the log.
        journal = self.__dict__.get('journal')
        if journal is None:
            raise AttributeError(name)
        return getattr(journal, name)

    # Stream ---------------------------------------------------------------
    def _envelope(self, kind, data, source):
        k = self.session.k
        record = {'seq': len(self.records) + 1, 'type': kind, 'source': source,
                  'game_time_ms': round(k.time * 1000),
                  'elapsed_wall_ms': round((time.monotonic() - self.monotonic_start) * 1000),
                  'clock_id': 'server_monotonic'}
        payload = dict(data)
        if source == 'engine':
            record['game_time_ms'] = payload.pop('game_time_ms', record['game_time_ms'])
            record['engine_seq'] = payload.pop('seq', None)
            if 'actor' in payload:
                payload['actor_id'] = payload.pop('actor')
        else:
            payload.pop('t', None)
        for key in ENVELOPE:
            if payload.get(key) is not None:
                record[key] = payload.pop(key)
        record['payload'] = payload
        return record

    def __call__(self, kind, data):
        data = dict(data)
        original = dict(data)
        source = 'engine' if kind == 'event' else 'session'
        if kind == 'event':
            kind = data.get('kind', 'event')
            data.pop('kind', None)
        if 'payload' in data and kind == 'ai_request':
            body = data['payload']
            digest = _sha(body)
            if self.keep_payloads:
                self.payloads.append({'request_id': data.get('request_id'), 'sha256': digest, 'payload': body})
            data = {**{k: v for k, v in data.items() if k != 'payload'},
                    'payload_sha256': digest, 'payload_ref': 'model-requests.jsonl' if self.keep_payloads else None,
                    'candidates': list(body.get('questions', {}).get('next_action', {}).get('criteria', {}))}
        for field in STATE_FIELDS:
            if field in data:
                data[field + '_sha256'] = _sha(data.pop(field))
        record = self._envelope(kind, data, source)
        self.records.append(record)
        if self.journal:
            # The file journal receives the same record: one stream, two views.
            envelope = {k: v for k, v in record.items() if k not in ('payload', 'type', 'source')}
            self.journal(kind if source == 'session' else 'event', {**original, **envelope})
        return record

    def engine_events(self):
        return [r for r in self.records if r['source'] == 'engine']

    def close(self):
        if not self.closed:
            self.closed = True
            self.ended_at = _now_iso()
            if self.journal:
                self.journal.close()

    # Bundle -----------------------------------------------------------------
    def replay_check(self):
        from kitchen import replay
        k = self.session.k
        try:
            again = replay(type(k), k.resolved, k.inputs)
        except Exception as exc:  # a failed replay is a finding, not a crash
            return {'level': 'replay_partial', 'reason': f'replay raised {type(exc).__name__}'}
        original = [(e['seq'], e.get('kind'), e['game_time_ms']) for e in k.events]
        repeated = [(e['seq'], e.get('kind'), e['game_time_ms']) for e in again.events]
        if original == repeated:
            return {'level': 'engine_events_verified', 'events': len(original), 'inputs': len(k.inputs)}
        first = next((i for i, (a, b) in enumerate(zip(original, repeated)) if a != b), min(len(original), len(repeated)))
        return {'level': 'replay_partial', 'reason': 'engine events diverge on replay (state was changed outside recorded inputs)',
                'first_divergent_event_index': first}

    def session_document(self, artifacts):
        s, k = self.session, self.session.k
        ai = getattr(s, 'ai', None)
        client = getattr(ai, 'client', None) if ai else None
        setting = getattr(s, 'setting', None) or {}
        agent_config = {
            'provider': setting.get('provider') or ('typesafe' if client is not None else None),
            'model': (setting.get('model') or k.c.get('model')) if client is not None else None,
            'actual_model': getattr(ai, 'actual_model', None),
            'adapter': type(client).__name__ if client is not None else None,
            'sampling': None, 'sampling_reason': 'not exposed by the adapter',
            'reasoning': None, 'reasoning_reason': 'not requested or recorded',
            'request_policy': {key: k.c.get(key) for key in ('ai_min_interval', 'ai_refresh_seconds', 'ai_timeout_seconds',
                                                              'ai_max_response_age')} | {'max_calls': getattr(ai, 'call_limit', None)},
            'prompt': {'rules_version': _rules_version(), 'input_language': _input_language()},
            'memory': {'enabled': bool(getattr(ai, 'cooperation_memory', None)),
                       'sha256': _sha(ai.cooperation_memory) if getattr(ai, 'cooperation_memory', None) else None},
        }
        replay = self.replay_check()
        engine = [e for e in k.events]
        counts = {}
        for e in engine:
            key = (e.get('kind'), e.get('actor'))
            counts[key] = counts.get(key, 0) + 1
        by_kind = lambda kind: {actor or 'world': n for (kd, actor), n in counts.items() if kd == kind}
        latencies = [r['payload'].get('latency') for r in self.records if r['type'] == 'ai_response' and r['payload'].get('latency') is not None]
        responses = [r for r in self.records if r['type'] == 'ai_response']
        status = k.goal_status()
        end_reason = ('aborted' if k.aborted else 'fire_loss' if k.failure_reason == 'fire_spread'
                      else 'round_limit' if k.time >= k.rules.round_limit - 1e-8
                      else 'ended' if k.ended else 'in_progress')
        return {
            'schema_version': SCHEMA_VERSION,
            'session_id': s.game_id,
            'deployment_mode': self.deployment_mode,
            'runtime_versions': {'release': _release(), 'python': platform.python_version(), 'engine': type(k).__name__,
                                 'engine_semantics': k.rules.semantics, 'rules_version': _rules_version(),
                                 'input_language': _input_language()},
            'resolved_config': {'path': 'resolved-config.json', 'config_hash': k.config_hash},
            'config_hash': k.config_hash,
            'level_id': k.resolved['level']['id'],
            'initial_state_seq': next((r['seq'] for r in self.records if r['type'] == 'start'), None),
            'actors': [
                {'actor_id': 'human', 'controller_type': 'human',
                 'interface': {'observation': 'rendered browser view', 'actions': 'keyboard and pointer',
                               'communication': 'preset messages', 'version': _release()}},
                {'actor_id': 'jeff', 'controller_type': 'agent' if client is not None else 'none',
                 'interface': {'observation': 'structured state', 'actions': 'legal action choice',
                               'communication': 'receives preset messages', 'version': _rules_version()}},
            ],
            'agent_config': agent_config,
            'started_at': self.started_at, 'ended_at': self.ended_at,
            'clock': {'tick_game_ms': round(k.rules.tick * 1000), 'game_per_wall': getattr(s, 'speed', None),
                      'round_limit_game_ms': round(k.rules.round_limit * 1000)},
            'recording_meta': {
                'scope': ['engine events', 'engine inputs', 'human inputs', 'model requests and responses',
                          'communication', 'bookmarks', 'pauses'],
                'sampling': 'complete event stream; full state snapshots only at round start and end; model payloads by reference',
                'dropped': 0, 'truncated': False,
                'clock_sources': {'game_time_ms': 'engine', 'elapsed_wall_ms': 'server_monotonic',
                                  'started_at': 'server_utc', 'latency': 'server_monotonic (same clock as request)'},
                'model_payloads': 'model-requests.jsonl' if self.keep_payloads else None,
                'model_payloads_reason': None if self.keep_payloads else 'not_collected in this deployment',
                'replay': replay,
            },
            'artifacts': artifacts,
            'outcome': {'engine_result': k.result(), 'end_reason': end_reason, 'goal_status': status,
                        'served': k.served, 'expired': sum(o['status'] == 'expired' for o in k.orders),
                        'unresolved_at_close': sum(o['status'] == 'unresolved_at_close' for o in k.orders),
                        'money': k.money, 'raw_score': k.money},
            'contribution_meta': getattr(s, 'contribution_meta', {'status': 'not_contributed'}),
            'derived': {
                'definitions_version': DERIVED_VERSION,
                'actions_started': by_kind('action_start'), 'actions_completed': by_kind('action_done'),
                'actions_interrupted': by_kind('interrupted'), 'arrival_conflicts': by_kind('arrival_conflict'),
                'shared_work_joins': by_kind('shared_work_join'), 'shared_work_leaves': by_kind('shared_work_leave'),
                'shared_work_overlap_game_ms': {st: round(v * 1000) for st, v in sorted(k.shared_overlap.items())},
                'handoffs': {'thrown': by_kind('thrown'), 'caught': by_kind('caught'),
                             'landed': {o: sum(1 for e in engine if e.get('kind') == 'landed' and e.get('outcome') == o)
                                        for o in ('landed_floor', 'landed_station')}},
                'model_calls': {'requests': sum(r['type'] == 'ai_request' for r in self.records),
                                'responses': len(responses),
                                'applied': sum(bool(r['payload'].get('applied')) for r in responses),
                                'errors': sum(r['type'] == 'ai_error' for r in self.records),
                                'latency_ms': {'min': round(min(latencies) * 1000) if latencies else None,
                                               'max': round(max(latencies) * 1000) if latencies else None}},
            },
        }


def _release():
    try:
        from release_info import VERSION
        return VERSION
    except ImportError:
        return None


def _rules_version():
    from jev import AGENT_RULES_VERSION
    return AGENT_RULES_VERSION


def _input_language():
    from model_language import INPUT_LANGUAGE_VERSION
    return INPUT_LANGUAGE_VERSION


def _write_jsonl(path, rows):
    with open(path, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')


def write_bundle(log, folder):
    """Write the session bundle atomically into ``folder``; return the session document."""
    k = log.session.k
    folder = Path(folder)
    folder.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.session-', dir=folder.parent))
    try:
        files = {'resolved-config.json': None, 'events.jsonl': log.records, 'engine-inputs.jsonl': k.inputs}
        (work / 'resolved-config.json').write_text(json.dumps(k.resolved, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        _write_jsonl(work / 'events.jsonl', log.records)
        _write_jsonl(work / 'engine-inputs.jsonl', k.inputs)
        if log.keep_payloads:
            _write_jsonl(work / 'model-requests.jsonl', log.payloads)
            files['model-requests.jsonl'] = log.payloads
        artifacts = []
        for name, rows in files.items():
            raw = (work / name).read_bytes()
            artifacts.append({'path': name, 'sha256': hashlib.sha256(raw).hexdigest(),
                              'records': None if rows is None else len(rows)})
        document = log.session_document(artifacts)
        (work / 'session.json').write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        for path in work.iterdir():
            os.chmod(path, 0o600)
        if folder.exists():
            raise FileExistsError(folder)
        os.replace(work, folder)
        return document
    finally:
        if work.exists():
            for path in work.iterdir():
                path.unlink()
            work.rmdir()


def read_bundle(folder):
    folder = Path(folder)
    load = lambda name: [json.loads(line) for line in (folder / name).read_text(encoding='utf-8').splitlines() if line]
    bundle = {'session': json.loads((folder / 'session.json').read_text(encoding='utf-8')),
              'resolved': json.loads((folder / 'resolved-config.json').read_text(encoding='utf-8')),
              'events': load('events.jsonl'), 'inputs': load('engine-inputs.jsonl')}
    if (folder / 'model-requests.jsonl').exists():
        bundle['model_requests'] = load('model-requests.jsonl')
    return bundle


def replay_bundle(folder):
    """Rebuild the kitchen from a written bundle's frozen configuration and inputs."""
    from kitchen import Kitchen, replay
    from spatial_kitchen import SpatialKitchen
    bundle = read_bundle(folder)
    factory = {'Kitchen': Kitchen, 'SpatialKitchen': SpatialKitchen}[bundle['session']['runtime_versions']['engine']]
    return replay(factory, bundle['resolved'], bundle['inputs'])
