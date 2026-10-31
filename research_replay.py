"""Read-only integrity check and exact replay of one research record.

Never calls a model. A record that carries ``replay`` (pre-start consent, v7 terms) is rebuilt
from its frozen configuration and every outer engine call; each state observation taken at an
engine-input boundary must then match the rebuilt kitchen exactly.
"""
from copy import deepcopy

import research_record as rr
from kitchen import apply_input

# States captured between two outer calls; event emissions happen inside a call.
BOUNDARY = ('initial', 'outer_input_completion', 'periodic', 'final')


def factory(name):
    from kitchen import Kitchen
    from spatial_kitchen import SpatialKitchen
    return {'Kitchen': Kitchen, 'SpatialKitchen': SpatialKitchen}[name]


def states(record):
    """Full state at every state row, applying deltas as the record format defines them."""
    by_seq, rows = {}, []
    for row in record['events']:
        if row['type'] not in ('state_checkpoint', 'state_delta'):
            continue
        data = row['payload']
        if row['type'] == 'state_checkpoint':
            full = deepcopy(data['state'])
        else:
            full = deepcopy(by_seq[data['base_state_seq']])
            for key, value in data['state'].items():
                if key in ('chefs', 'stations'):
                    full[key] = {**full[key], **deepcopy(value)}
                else:
                    full[key] = deepcopy(value)
        by_seq[row['seq']] = full
        rows.append({'seq': row['seq'], 'trigger': data['trigger'], 'engine_input_n': data.get('engine_input_n'),
                     'game_time_ms': row['game_time_ms'], 'state': full})
    return rows


def rebuild(record, upto=None):
    """The replayed kitchen after the first ``upto`` engine inputs (all of them by default)."""
    replay = record.get('replay')
    if not replay:
        raise ValueError('This record carries no engine inputs; it cannot be replayed exactly.')
    k = factory(replay['engine'])(deepcopy(replay['resolved_config']))
    for row in replay['inputs'][:upto]:
        apply_input(k, row)
    return k


def check(record):
    """What a record covers and whether it replays; a report, never an exception for gaps."""
    rr.validate_record(record)
    quality, events = record['quality'], record['events']
    seqs = [row['seq'] for row in events]
    gaps = [[a + 1, b - 1] for a, b in zip(seqs, seqs[1:]) if b != a + 1]
    report = {'round_id': record['round_id'], 'consent_version': record['consent_version'],
              'started': record['initial_state_seq'] is not None, 'ended_at': record['ended_at'],
              'duration': record['duration'], 'complete': quality['complete'],
              'closed': record['termination']['confirmed'], 'truncated': quality['truncated'],
              'dropped': quality['dropped'], 'loss_ranges': quality['loss_ranges'],
              'projection_errors': quality['projection_errors'], 'event_count': len(events),
              'seq_gaps': gaps, 'last_event_seq': record['termination']['last_event_seq'],
              'replay': 'not_available'}
    if not record.get('replay'):
        return report
    replay = record['replay']
    observed = [row for row in states(record) if row['trigger'] in BOUNDARY and row['engine_input_n'] is not None]
    k = factory(replay['engine'])(deepcopy(replay['resolved_config']))
    done, mismatches = 0, []
    for row in sorted(observed, key=lambda r: (r['engine_input_n'], r['seq'])):
        for item in replay['inputs'][done:row['engine_input_n']]:
            apply_input(k, item)
        done = row['engine_input_n']
        if rr.state(k) != row['state']:
            mismatches.append({'seq': row['seq'], 'engine_input_n': done, 'game_time_ms': row['game_time_ms']})
    for item in replay['inputs'][done:]:
        apply_input(k, item)
    report.update(replay='verified' if not mismatches else 'diverged', replay_inputs=len(replay['inputs']),
                  replay_states_checked=len(observed), replay_mismatches=mismatches[:20],
                  replay_end_time_ms=round(k.time * 1000))
    return report


def rebuild_requests(record):
    """Recompose each recorded Jeff request and compare it with the digest taken when it was sent.

    Yields one row per request; ``rebuilt`` is the payload, so a researcher can vary it offline.
    """
    from cooperation_memory import memory_context
    from jev import NO_MEMORY, compose_payload
    from whitebox_server import SpatialJevClient
    import config_contract as cc
    replay = record.get('replay')
    if not replay:
        raise ValueError('This record carries no engine inputs; its requests cannot be rebuilt.')
    k = factory(replay['engine'])(deepcopy(replay['resolved_config']))
    client = SpatialJevClient(k.c, key='research-replay-no-credential')
    done = 0
    for row in record['events']:
        data = row['payload']
        if row['type'] != 'ai_request' or 'payload_sha256' not in data:
            continue
        for item in replay['inputs'][done:data['engine_input_n']]:
            apply_input(k, item)
        done = data['engine_input_n']
        if data['memory_input'] == 'not_stored':
            yield {'request_id': row['request_id'], 'seq': row['seq'], 'status': 'memory_not_stored', 'rebuilt': None}
            continue
        memory = memory_context(False, []) if data['memory_input'] == 'empty_placeholder' else NO_MEMORY
        payload = compose_payload(client, k, k.snapshot(), k.actions('jeff'), data['recent_decisions'],
                                  data['player_communication'], memory)
        yield {'request_id': row['request_id'], 'seq': row['seq'], 'rebuilt': payload,
               'status': 'verified' if cc.sha256(payload) == data['payload_sha256'] else 'diverged'}
