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
ENVELOPE = ('actor_id', 'action_id', 'request_id', 'order_id', 'item_id', 'station_id', 'receiver_id', 'handoff_id', 'input_id')
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
        self.kitchen = session.k
        self.round_id = session.game_id
        self.journal = journal
        self.keep_payloads = keep_payloads
        self.deployment_mode = deployment_mode
        self.records = []
        self.payloads = []
        self.started_at = _now_iso()
        self.ended_at = None
        self.monotonic_start = time.monotonic()
        self.closed = False
        self.next_seq = 1
        self.research = deployment_mode == 'hosted'
        self.capture_observations = bool(getattr(session, 'research_armed', None))
        self.observations_withdrawn = False
        self.dropped = 0
        self.loss_ranges = []
        self.projection_errors = 0
        self.record_bytes = 0
        self.state_ref = None
        self.final_state_ref = None
        self.not_projected = {'engine_events': 0, 'session_records': 0}
        self.last_state = None
        self.last_sample_ms = -1000
        self.last_checkpoint_ms = -10000
        self.last_engine_seq = 0
        self.action_links = {}
        self.candidate_catalog = {}
        self.termination = None
        if self.research:
            from research_record import config
            self.research_config = config(session.k)
            session.k._record_observer = self

    def __getattr__(self, name):
        # Journal-specific attributes (e.g. a file path) stay reachable through the log.
        journal = self.__dict__.get('journal')
        if journal is None:
            raise AttributeError(name)
        return getattr(journal, name)

    # Stream ---------------------------------------------------------------
    def _envelope(self, kind, data, source):
        k = self.session.k
        record = {'seq': self.next_seq, 'type': kind, 'source': source,
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
            # Consume absent links too: a null ID left in payload breaks the
            # hosted schema and blocks saving the whole round. Hosted projection
            # restores null links; local envelopes omit optional, non-null IDs.
            if key in payload:
                value = payload.pop(key)
                if value is not None:
                    record[key] = value
        record['payload'] = payload
        return record

    def __call__(self, kind, data):
        data = dict(data)
        original = dict(data)
        if self.research:
            from research_record import payload
            if kind == 'event':
                if data.get('seq') is not None and data['seq'] <= self.last_engine_seq:
                    return
                if data.get('seq') is not None:
                    self.last_engine_seq = data['seq']
                name = data.get('kind', 'event')
                projected = payload(name, data, self.session.k)
                if projected is None:
                    self.not_projected['engine_events'] += 1
                    return
                if data.get('actor') not in ('human','jeff'): data.pop('actor',None)
                if data.get('receiver') not in ('human','jeff'): data.pop('receiver',None)
                data = {**projected, 'kind': name,
                        **{key: data[key] for key in ('seq', 'game_time_ms', 'actor', 'action_id', 'request_id', 'order_id', 'handoff_id') if key in data},
                        'item_id': data.get('item'), 'station_id': data.get('station'),
                        'receiver_id': data.get('receiver') or (data.get('actor') if name == 'caught' else None)}
            else:
                projected = payload(kind, data, self.session.k)
                if projected is None:
                    self.not_projected['session_records'] += 1
                    return
                if kind == 'ai_request':
                    descriptors = projected.pop('candidate_actions', [])
                    added = [a for a in descriptors if self.candidate_catalog.get(a['key']) != a]
                    if added:
                        catalog = self._envelope('action_catalog', {'actions': added}, 'session')
                        self._append(catalog)
                        self.candidate_catalog.update({a['key']: a for a in added})
                    while len(self.candidate_catalog) > 4096:
                        self.candidate_catalog.pop(next(iter(self.candidate_catalog)))
                    projected['candidate_catalog'] = 'session_action_catalog'
                elif kind == 'ai_response':
                    selected = projected['choice']['key']
                    if selected in self.candidate_catalog:
                        projected['choice'] = copy.deepcopy(self.candidate_catalog[selected])
                data = {**projected, **{key: data[key] for key in ENVELOPE if key in data}}
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
        self._append(record, reserve=kind == 'end')
        if self.research and kind in ('start', 'end'):
            self.capture_state('initial' if kind == 'start' else 'final', force=True)
            if kind == 'start':
                for event in self.session.k.events:
                    self('event', event)
        if self.journal:
            # The file journal receives the same record: one stream, two views.
            envelope = {k: v for k, v in record.items() if k not in ('payload', 'type', 'source')}
            self.journal(kind if source == 'session' else 'event', {**original, **envelope})
        return record

    def _append(self, record, reserve=False):
        if self.closed:
            return None
        record['seq'] = self.next_seq
        self.next_seq += 1
        if self.research:
            from research_record import MAX_RECORDS, MAX_BYTES
            size = len(json.dumps(record, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()) + 256
            if self.record_bytes + size > MAX_BYTES or (not reserve and (len(self.records) >= MAX_RECORDS - 4 or self.record_bytes + size > MAX_BYTES - 2000000)):
                self.dropped += 1
                seq = record['seq']
                if self.loss_ranges and self.loss_ranges[-1]['last_seq'] == seq - 1:
                    self.loss_ranges[-1]['last_seq'] = seq
                elif len(self.loss_ranges) < 16:
                    self.loss_ranges.append({'first_seq': seq, 'last_seq': seq})
                else:
                    self.loss_ranges[-1]['last_seq'] = seq
                return None
            self.record_bytes += size
        self.records.append(record)
        return record['seq']

    def capture_state(self, trigger, force=False):
        if not self.research or self.closed or (not self.capture_observations and trigger not in ('initial', 'final')):
            return self.state_ref
        from research_record import state, PERIOD_MS, CHECKPOINT_MS
        now = round(self.session.k.time * 1000)
        current = state(self.session.k)
        full = self.last_state is None or force or now - self.last_checkpoint_ms >= CHECKPOINT_MS
        changes = current if full else {key: value for key, value in current.items() if self.last_state.get(key) != value}
        if not full:
            for key in ('chefs', 'stations'):
                if key in changes:
                    changes[key] = {entity: value for entity, value in current[key].items()
                                    if self.last_state[key].get(entity) != value}
        if not changes and trigger != 'periodic':
            return self.state_ref
        row = self._envelope('state_checkpoint' if full else 'state_delta',
                             {'base_state_seq': None if full else self.state_ref, 'trigger': trigger,
                              'state': changes}, 'session')
        seq = self._append(row, reserve=trigger == 'final')
        self.last_sample_ms = now
        if seq is not None:
            self.state_ref = seq
            if trigger == 'final': self.final_state_ref = seq
            self.session.k._research_state_ref = seq
            self.last_state = current
            self.last_sample_ms = now
            if full:
                self.last_checkpoint_ms = now
        return self.state_ref

    def observe_event(self, event):
        if self.closed:
            return
        try:
            before = self.state_ref if self.capture_observations else None
            after = self.capture_state('event_emission') if self.capture_observations else None
            enriched = dict(event)
            actor = event.get('actor')
            chef = self.session.k.chefs.get(actor)
            job = chef.job if chef else None
            action_id = event.get('action_id')
            if job and action_id == job.id:
                self.action_links[action_id] = {'key': job.action.key, 'target': job.action.target, 'kind': job.action.kind}
                if len(self.action_links) > 2048:
                    self.action_links.pop(next(iter(self.action_links)))
            link = self.action_links.get(action_id)
            if link:
                enriched['station'] = enriched.get('station') or (link['target'] if link['target'] in self.session.k.stations else None)
            if event['kind'] in ('served', 'wrong_dish', 'dish_rejected') and chef and chef.hand:
                enriched['item'] = chef.hand.id
            if event['kind'] == 'plate_returned':
                tray = self.session.k.stations[self.session.k.returns].food
                if tray: enriched['item'] = tray.id
            row = self('event', enriched)
            if row is not None and link and 'action' in row['payload']:
                from research_record import action
                row['payload']['action'] = action(link['key'], link['target'], link['kind'])
            if row is not None:
                row['state_before_seq'], row['state_after_seq'] = before, after
        except Exception:
            # A recorder failure must not change kitchen behavior; never retain exception text.
            self.projection_errors += 1

    def observe_input(self, data):
        if self.closed:
            return
        try:
            from research_record import action, PERIOD_MS, code, point
            call = data['call']
            before = self.state_ref
            low_frequency = call in ('advance','report_position','set_manual','face','pick_station')
            sampled = not low_frequency or round(self.session.k.time * 1000) - self.last_sample_ms >= PERIOD_MS
            if sampled:
                self.capture_state('periodic' if low_frequency else 'outer_input_completion')
            if call not in ('advance', 'face', 'pick_station'):
                a = data.get('action', {})
                record = self._envelope('engine_input', {
                    'call': call, 'action': action(a.get('key'), a.get('target'), a.get('kind')),
                    'accepted': data.get('accepted'), 'stage': 'engine_input_return',
                    'reason': 'engine_rejected' if data.get('accepted') is False else None,
                    'vector': point(data.get('vector')), 'at': point(data.get('at')),
                    'source_time_game_ms': data['game_time_ms'],
                    'actor_id': data.get('actor')}, 'session')
                chef = self.session.k.chefs.get(data.get('actor'))
                record['action_id'] = chef.job.id if chef and chef.job and call == 'start' and data.get('accepted') else None
                record['state_before_seq'], record['state_after_seq'] = (before, self.state_ref) if self.capture_observations and sampled else (None, None)
                self._append(record)
        except Exception:
            # A recorder failure must not change kitchen behavior; never retain exception text.
            self.projection_errors += 1

    def item_transform(self, inputs, outputs):
        if self.closed:
            return
        self('event', {'kind': 'item_transform', 'input_item_ids': inputs,
                       'output_item_ids': outputs, 'game_time_ms': round(self.session.k.time * 1000)})

    def observe_close(self, reason):
        """A later context close may follow natural game end; keep it in this stream."""
        if not self.research or self.termination is not None or reason == 'not_observed':
            return
        was_closed = self.closed
        self.closed = False
        try:
            row = self._envelope('context_closed', {'reason': reason}, 'session')
            row['game_time_ms'] = round(self.kitchen.time * 1000)
            self._append(row, reserve=True)
            self.termination = {'reason': reason, 'source': 'server'}
        finally:
            self.closed = was_closed

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
