"""Private research projection of SessionLog, never a second event sink.

Only server-authored game identifiers, numbers and explicit structures cross this
boundary. No model payload, exception string, player message or endpoint does.
"""
from copy import deepcopy
from pathlib import Path
import json
import math
import re
import config_contract as cc
import schema_check

SCHEMA = 'chefjeff-pilot-session-v2'
CONSENT = 'pilot-session-2026-10-v7'
MODEL_PROVIDERS = {p['id']: p for p in json.loads(
    (Path(__file__).resolve().parent / 'model-providers.json').read_text())['providers']
    if not p.get('disabled')}
MAX_RECORDS = 24000
MAX_BYTES = 12_000_000
PERIOD_MS = 1000
CHECKPOINT_MS = 10000
CODE = re.compile(r'^[A-Za-z0-9_ .:-]{1,100}$')
REASONS = {'manual', 'hidden', 'connection_timeout', 'manual_end', 'restart', 'next_level',
           'page_close_request', 'idle_timeout', 'server_shutdown', 'engine_fault', 'state_changed',
           'stale_or_disabled', 'engine_rejected', 'transport_failed', 'not_observed',
           'route_blocked', 'position_resync', 'arrival_state_changed', 'action_replaced', 'stop_called'}
EVENT_FIELDS = ('action', 'station', 'item', 'taken', 'dish', 'receiver', 'thrower', 'outcome',
                'source', 'workers', 'participants', 'price', 'adjustment', 'overcook_game_ms',
                'from', 'to', 'at', 'base', 'target', 'position', 'duration', 'max_distance',
                'input_item_ids', 'output_item_ids')
EVENT_TYPES = {'order', 'action_start', 'action_done', 'interrupted', 'arrival_conflict',
               'shared_work_join', 'shared_work_leave', 'thrown', 'caught', 'landed', 'washed',
               'served', 'wrong_dish', 'dish_rejected', 'plate_returned', 'ready', 'burn', 'fire',
               'fire_spread', 'fire_loss', 'expired', 'unresolved_at_close', 'round_end',
               'goal_unreachable', 'dropped', 'picked_up', 'swapped', 'manual_move', 'sprint',
               'knocked', 'ground_nudge', 'route_replanned', 'position_resync', 'item_transform'}


def code(value):
    return value if isinstance(value, str) and CODE.fullmatch(value) else None


def reported_model_identity(value):
    """Explicit model metadata only; never accept connection settings or a claimed verification."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'provider', 'model_id'}:
        raise ValueError('模型标识字段无效。')
    provider, model = value['provider'], value['model_id']
    if not isinstance(provider, str) or provider not in MODEL_PROVIDERS:
        raise ValueError('模型服务标识无效。')
    if (not isinstance(model, str) or not 1 <= len(model) <= 120 or model != model.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in model) or '://' in model):
        raise ValueError('模型 ID 无效。')
    return {'provider': provider, 'model_id': model,
            'interface': 'systemone' if MODEL_PROVIDERS[provider]['group'] == 'decision' else 'chat_completions',
            'source': 'browser-reported', 'verified': False}


def model_condition(session):
    log = getattr(session, 'session_log', None)
    if log is None or log.round_id != session.game_id or log.kitchen is not session.k:
        return None
    return deepcopy(getattr(log, 'model_identity', None))


def number(value):
    return round(value, 4) if type(value) in (int, float) and math.isfinite(value) and abs(value) <= 1e10 else None


def point(value):
    return [number(v) for v in value] if isinstance(value, (list, tuple)) and len(value) == 2 else None


def action(value, target=None, kind=None):
    key = code(value)
    return {'key': key, 'verb': key.split(' ', 1)[0] if key else None,
            'kind': code(kind), 'target': code(target),
            'target_source': 'engine_action' if target is not None else 'not_collected'}


def food(f):
    if f is None:
        return None
    return {'id': code(f.id), 'stage': code(f.stage), 'ingredient': code(f.ingredient),
            'components': [code(v) for v in f.components], 'plate_id': code(f.plate_id),
            'chopped': number(f.chopped), 'heated': number(f.heated), 'washed': number(f.washed),
            'contents': food(f.contents)}


def state(k):
    """Explicit engine-object field allowlist; labels and rendered text are excluded."""
    chefs = {}
    for who, c in k.chefs.items():
        j = c.job
        chefs[who] = {'position': point(getattr(k, 'positions', {}).get(who)),
                      'location': code(c.location), 'hand': food(c.hand),
                      'action_id': j.id if j else None,
                      'action': action(j.action.key, j.action.target, j.action.kind) if j else None,
                      'working': bool(j and j.working), 'travel_remaining': number(j.travel) if j else 0,
                      'work_remaining': number(j.work) if j else 0,
                      'manual': point(getattr(k, 'manual', {}).get(who))}
    stations = {key: {'food': food(s.food), 'used_by': code(s.lock), 'pot_id': code(s.pot_id),
                      'heating': bool(s.heating), 'fire': bool(s.fire), 'fire_heat': number(s.fire_heat),
                      'fire_strength': number(s.fire_strength),
                      'workers': k.work_participants(key, 'chop') + k.work_participants(key, 'wash')}
                for key, s in k.stations.items()}
    return {'chefs': chefs, 'stations': stations,
            'ground': [{'food': food(v.food), 'location': code(v.location), 'used_by': code(v.lock),
                        'position': point(k.ground_position(v)) if hasattr(k, 'ground_position') else None}
                       for v in k.ground.values()],
            'projectiles': [{'food': food(p['food']), 'actor': code(p['actor']),
                             'target': code(p['target']), 'from': point(p['from']), 'to': point(p['to']),
                             'started': number(p['started']), 'lands_at': number(p['lands_at']),
                             'handoff_id': p['handoff_id']} for p in getattr(k, 'projectiles', {}).values()],
            'orders': [{'id': code(o['id']), 'dish': code(o['dish']), 'arrival': number(o['arrival']),
                        'deadline': number(o['deadline']), 'status': code(o['status'])} for o in k.orders],
            'dining': [{'plate': food(p['plate']), 'returns_at': number(p['returns_at'])} for p in k.dining],
            'money': number(k.money), 'served': k.served, 'ended': bool(k.ended), 'aborted': bool(k.aborted)}


def _project(value, spec, base):
    """Schema properties form the config allowlist. Open extension bags are excluded."""
    if '$ref' in spec:
        spec, base = schema_check._resolve(spec['$ref'], base)
    if 'oneOf' in spec:
        chosen = next((s for s in spec['oneOf'] if not list(schema_check.check(value, s, base))), {})
        spec = {**spec, **chosen, 'properties': {**spec.get('properties', {}), **chosen.get('properties', {})}}
    if isinstance(value, dict):
        props, extra = spec.get('properties', {}), spec.get('additionalProperties')
        result = {}
        for key, v in value.items():
            sub = props.get(key)
            if sub is None and isinstance(extra, dict):
                sub = extra
            if sub is not None:
                result[key] = _project(v, sub, base)
        return result
    if isinstance(value, (list, tuple)):
        return [_project(v, spec.get('items', {}), base) for v in value]
    return deepcopy(value)


def config(k):
    result = _project(k.resolved, schema_check.load_schema('resolved.schema.json'), 'resolved.schema.json')
    # Runtime overrides are already resolved into the typed game documents.
    result['overrides'] = {}
    # Params are equipment-declared item refs, never arbitrary runtime strings.
    types = k.resolved['equipment_catalog']['types']
    for rows in (result['stations'], result['map']['equipment']):
        for row in rows:
            declared = types[row['type']].get('params', {})
            row['params'] = {key: value for key, value in row.get('params', {}).items() if key in declared}
    return result


def payload(kind, data, k):
    """Field-by-field projection before hosted data enters SessionLog.records."""
    if kind in EVENT_TYPES:
        out = {}
        for key in EVENT_FIELDS:
            if key not in data: continue
            v = data[key]
            if key in ('from', 'to', 'at', 'base', 'position') or key in ('source', 'target') and isinstance(v, (list, tuple)):
                out[key] = point(v)
            elif isinstance(v, (list, tuple)):
                out[key] = [code(x) for x in v[:32]]
            elif type(v) is bool: out[key] = v
            elif type(v) in (int, float): out[key] = number(v)
            else: out[key] = code(v)
        if 'action' in out:
            out['action'] = action(out['action'], data.get('station'))
        if kind in ('interrupted', 'arrival_conflict', 'route_replanned', 'position_resync'):
            out['reason'] = {'interrupted': 'stop_called', 'arrival_conflict': 'arrival_state_changed',
                             'route_replanned': 'route_blocked', 'position_resync': 'position_resync'}[kind]
            if kind == 'position_resync' and data.get('reason') in ('pushed', 'blocked', 'too_far'):
                out['reason'] = data['reason']
            out['reason_detail'] = 'not_collected'  # never infer chef competition
        return out
    if kind == 'ai_request':
        body = data.get('payload', {})
        candidates = body.get('questions', {}).get('next_action', {}).get('criteria', {})
        return {'observed_state_seq': data.get('observed_state_seq'),
                'candidates': [code(v) for v in candidates],
                'candidate_actions': [action(a.key, a.target, a.kind) for a in k.actions('jeff') if a.key in candidates], 'stage': 'model_request',
                'choice_source': 'not_observed', 'state_ref': getattr(k, '_research_state_ref', None) if getattr(getattr(k, '_record_observer', None), 'capture_observations', False) else None}
    if kind == 'ai_response':
        fresh, applied = bool(data.get('fresh')), bool(data.get('applied'))
        return {'choice': action(data.get('choice')), 'fresh': fresh, 'applied': applied,
                'accepted_engine_seq': data.get('accepted_engine_seq'),
                'stage': 'model_choice_and_application', 'choice_source': 'client-reported',
                'server_round_trip_ms': number(data.get('latency', 0) * 1000),
                'server_received_wall_ms': number(data.get('server_received_wall_ms')),
                'server_transport_started_wall_ms': number(data.get('server_transport_started_wall_ms')),
                'reason': None if applied else 'stale_or_disabled' if not fresh else 'engine_rejected',
                'usage': {key: value for key, value in data.get('usage', {}).items()
                          if key in ('input_tokens', 'output_tokens') and type(value) is int and 0 <= value <= 10000000},
                'usage_source': 'client-reported', 'provider_verified': False}
    if kind == 'request_unresolved':
        return {'reason': 'not_observed'}
    if kind == 'ai_error':
        return {'reason': 'transport_failed', 'retry_in_seconds': number(data.get('retry_in')),
                'server_received_wall_ms': number(data.get('server_received_wall_ms'))}
    if kind == 'human_input':
        return {'action': action(data.get('action')), 'applied': bool(data.get('applied')),
                'stage': 'input_report', 'reason': None if data.get('applied') else 'engine_rejected',
                'missing_stages': ['raw_device_input'], 'source': 'server_observed_browser_command'}
    if kind == 'call_limit':
        return {key: data[key] for key in ('calls', 'limit') if type(data.get(key)) is int}
    if kind in ('pause', 'resume', 'start', 'end', 'engine_error', 'context_closed'):
        return {'reason': data.get('reason') if data.get('reason') in REASONS else 'not_observed',
                'speed': number(data.get('speed')), 'aborted': bool(k.aborted)}
    return None  # presets, bookmark texts, release metadata, raw errors: not this study


def project_event(record):
    result = {key: deepcopy(record[key]) for key in ('seq', 'type', 'source', 'game_time_ms',
              'elapsed_wall_ms', 'clock_id', 'payload')}
    for key in ('engine_seq', 'actor_id', 'action_id', 'request_id', 'order_id', 'item_id',
                'station_id', 'receiver_id', 'handoff_id', 'input_id', 'state_before_seq', 'state_after_seq'):
        result[key] = record.get(key)
    result['missing_relations'] = {}
    if result['request_id'] is None and result['action_id'] is not None:
        result['missing_relations']['request_id'] = 'join_via_action_id'
    if result['receiver_id'] is None and result['type'] == 'thrown':
        result['missing_relations']['receiver_id'] = 'pending_handoff'
    return result


def record(session):
    log, k = session.session_log, session.k
    if log is None or log.kitchen is not k or log.round_id != session.game_id:
        raise ValueError('No started round to project.')
    from feedback import memory_condition
    from session_record import _rules_version, _input_language
    ending = getattr(log, 'termination', None)
    game_reason = ('fire_loss' if k.failure_reason == 'fire_spread' else 'round_limit'
                   if k.time >= k.rules.round_limit - 1e-8 else 'none_observed' if k.aborted else 'in_progress')
    rows = [project_event(r) for r in log.records]
    # Exact replay needs the unprojected frozen configuration and every outer engine call. Both
    # describe the whole round, so they are kept only when it was observed with pre-start consent.
    observed = bool(log.capture_observations and not log.observations_withdrawn)
    replay = {'engine': type(k).__name__, 'resolved_config': deepcopy(k.resolved),
              'inputs': deepcopy(k.inputs)} if observed else None
    state_times = [r['game_time_ms'] for r in rows if r['type'] in ('state_checkpoint', 'state_delta')]
    max_gap = max((b-a for a,b in zip(state_times,state_times[1:])), default=0)
    return {'schema': SCHEMA, 'consent_version': CONSENT, 'round_id': session.game_id,
            'relation_missing_default': 'not_emitted',
            'level': k.c.get('level', 1), 'speed': session.speed, 'duration': round(k.time, 3),
            'aborted': bool(k.aborted), 'result': {'served': k.served, 'money': k.money, 'won': k.won()},
            'release': {key: code(session.release.get(key)) for key in ('version', 'fingerprint')},
            'started_at': log.started_at, 'ended_at': log.ended_at,
            'initial_state_seq': next((r['seq'] for r in rows if r['type']=='state_checkpoint' and r['payload']['trigger']=='initial'), None),
            'config_hash': k.config_hash, 'resolved_config': deepcopy(log.research_config),
            'config_projection_hash': 'sha256:' + cc.sha256(log.research_config),
            'conditions': {'cross_round_memory': memory_condition(session),
                           'engine_semantics': k.rules.semantics,
                           'rules_version': _rules_version(),
                           'input_language': _input_language(),
                           'observation_interface': 'structured_state', 'action_interface': 'legal_action_choice',
                           'model_identity': model_condition(session),
                           'model_identity_reason': 'browser_reported_not_verified' if model_condition(session) else 'not_reported',
                           'decision_telemetry': bool(getattr(session, 'research_telemetry', False)),
                           'model_parameters': {'sampling': None, 'reasoning': None, 'safety': None, 'upstream_adapter': None, 'status': 'not_collected_from_browser'},
                           'request_policy': {key: number(k.c.get(key)) for key in ('ai_min_interval', 'ai_refresh_seconds', 'ai_timeout_seconds', 'ai_max_response_age')} | {'max_calls': getattr(getattr(session, 'ai', None), 'call_limit', None)}},
            'events': rows, 'replay': replay,
            'termination': {'game_condition': game_reason, 'session_close': ending,
                            'confirmed': ending is not None and ending['reason'] != 'not_observed', 'last_game_time_ms': round(k.time * 1000),
                            'last_event_seq': log.next_seq - 1, 'final_state_seq': log.final_state_ref},
            'quality': {'scope': 'allowlisted_session_facts_and_state_observations',
                        'complete': bool(log.closed and log.capture_observations and not log.observations_withdrawn and not log.dropped and not log.projection_errors),
                        'truncated': bool(log.dropped), 'dropped': log.dropped,
                        'loss_ranges': deepcopy(log.loss_ranges), 'projection_errors': log.projection_errors,
                        'not_projected': dict(log.not_projected),
                        'observed_max_state_gap_game_ms': max_gap,
                        'state_history': 'partial_consent_withdrawn' if log.observations_withdrawn else 'consented_capture' if log.capture_observations else 'initial_final_only_no_prestart_consent',
                        'engine_input_scope': 'non-advance outer calls; advance sampled as state observations',
                        'capacity_records': MAX_RECORDS, 'capacity_bytes': MAX_BYTES,
                        'period_game_ms': PERIOD_MS, 'checkpoint_game_ms': CHECKPOINT_MS,
                        'state_trigger': 'initial,event_emission,outer_input_completion,periodic,final',
                        'delta_format': 'merge_chefs_stations_by_id_replace_other_sections',
                        'state_precision': 'emission observations are not atomic operation boundaries',
                        'replay': 'engine_inputs' if replay else 'not_claimed',
                        'missing': ['raw_device_input', 'provider_verified_model',
                                    'provider_server_clock', 'free_text', 'preset_communication'] + ([] if log.capture_observations else ['intermediate_state_not_collected_without_prestart_consent']) + ([] if replay else ['engine_inputs_not_collected_without_prestart_consent'])}}


def validate_telemetry(value):
    if not isinstance(value, dict) or set(value) != {'duration_ms', 'error_type'}:
        raise ValueError('Invalid telemetry fields')
    if type(value['duration_ms']) is not int or not 0 <= value['duration_ms'] <= 120000:
        raise ValueError('Invalid client duration')
    if value['error_type'] not in (None, 'timeout', 'transport_or_response_error'):
        raise ValueError('Invalid client error category')
    return deepcopy(value)


def validate_record(value):
    """Structural and referential verification, not evidence of human intent or replay."""
    errors = schema_check.validate(value, 'research-record.schema.json')
    if errors:
        raise ValueError('Research schema violation at ' + errors[0][0])
    if value['config_projection_hash'] != 'sha256:' + cc.sha256(value['resolved_config']):
        raise ValueError('Configuration projection digest mismatch')
    replay = value.get('replay')
    if replay is not None:
        resolved = dict(replay['resolved_config'])
        if resolved.pop('config_hash', None) != value['config_hash'] or 'sha256:' + cc.sha256(resolved) != value['config_hash']:
            raise ValueError('Replay configuration digest mismatch')
        if [row['n'] for row in replay['inputs']] != list(range(len(replay['inputs']))):
            raise ValueError('Replay inputs are not contiguous')
    previous, wall, states = 0, -1, set()
    for row in value['events']:
        seq = row['seq']
        if seq <= previous or row['elapsed_wall_ms'] < wall:
            raise ValueError('Event order or monotonic clock violation')
        previous, wall = seq, row['elapsed_wall_ms']
        if row['type'] in ('state_delta', 'state_checkpoint'):
            data = row['payload']
            if not {'base_state_seq', 'trigger', 'state'} <= data.keys():
                raise ValueError('Missing state payload fields')
            if row['type'] == 'state_delta' and data['base_state_seq'] not in states:
                raise ValueError('Missing state base')
            if row['type'] == 'state_checkpoint' and (data['base_state_seq'] is not None or set(data['state']) != {'chefs','stations','ground','projectiles','orders','dining','money','served','ended','aborted'}):
                raise ValueError('Incomplete checkpoint')
            states.add(seq)
        for key in ('state_before_seq', 'state_after_seq'):
            if row[key] is not None and row[key] not in states:
                raise ValueError('Unknown state reference')
    last = value['termination']['last_event_seq']
    if last is not None and last < previous:
        raise ValueError('Last sequence precedes saved records')
    if value['termination']['final_state_seq'] is not None and value['termination']['final_state_seq'] not in states:
        raise ValueError('Missing final state')
    if value['initial_state_seq'] is not None and value['initial_state_seq'] not in states:
        raise ValueError('Missing initial state')
    gaps, previous = [], 0
    for row in value['events']:
        if row['seq'] > previous + 1: gaps.append({'first_seq': previous+1, 'last_seq': row['seq']-1})
        previous = row['seq']
        expected = {}
        if row['request_id'] is None and row['action_id'] is not None: expected['request_id']='join_via_action_id'
        if row['receiver_id'] is None and row['type']=='thrown': expected['receiver_id']='pending_handoff'
        if row['missing_relations'] != expected: raise ValueError('Incorrect missing relation declarations')
    if last > previous: gaps.append({'first_seq': previous+1, 'last_seq': last})
    if gaps != value['quality']['loss_ranges'] or sum(g['last_seq']-g['first_seq']+1 for g in gaps) != value['quality']['dropped']:
        raise ValueError('Loss declarations do not match sequence gaps')
    if value['quality']['complete'] and value['quality']['state_history'] != 'consented_capture':
        raise ValueError('Incomplete consented capture')
    if value['quality']['complete'] and (value['quality']['dropped'] or value['quality']['projection_errors'] or value['ended_at'] is None):
        raise ValueError('False completeness claim')
    return True


def restored_states(value):
    """Yield readable observations; deltas replace whole named state sections."""
    states = {}
    for row in value['events']:
        if row['type'] not in ('state_checkpoint', 'state_delta'):
            continue
        data = row['payload']
        current = {} if data['base_state_seq'] is None else deepcopy(states[data['base_state_seq']])
        for key, value in data['state'].items():
            if data['base_state_seq'] is not None and key in ('chefs','stations'):
                current[key].update(deepcopy(value))
            else:
                current[key] = deepcopy(value)
        states[row['seq']] = current
        yield row['seq'], current
