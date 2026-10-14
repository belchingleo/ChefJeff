"""Small allowlisted local feedback reports, never raw requests or free text."""
import re
from copy import deepcopy
from collections import Counter
from datetime import datetime

from levels import available_levels

EVENTS = {'order','action_start','action_done','interrupted','arrival_conflict',
          'picked_up','dropped','thrown','landed','swapped','ready','burn','fire',
          'served','expired','washed','plate_returned','round_end'}


HISTORY_LIMIT = 100  # finished rounds kept per play session; older rounds stay in the local run logs
EXCLUDED = ['API keys', 'endpoint and model text', 'absolute paths', 'raw model responses',
            'request snapshots', 'cross-round memory', 'free-text messages']
BOOKMARK_POLICY = {'schema_version': 1, 'merge_window_seconds': 5,
                   'merge_clock': 'server_monotonic_real_time',
                   'merge_rule': 'consecutive presses within 5 seconds of the previous press',
                   'game_clock': 'seconds since round start',
                   'wall_clock': 'ISO 8601 with timezone, captured on server receipt',
                   'event_index': 'zero-based index of the next kitchen event at each mark',
                   'log_join': 'round_id plus game time; bookmark updates use stable id'}


def allowed_events(k):
    events = []
    for e in k.events:
        if e.get('kind') not in EVENTS:continue
        row = {'t': e['t'], 'kind': e['kind']}
        if e.get('actor') in ('human', 'jeff'):row['actor'] = e['actor']
        # Action IDs come from the game, not arbitrary notes or provider text.
        action = e.get('action', '')
        if re.fullmatch(r'(?:fetch|wash|serve|drop|discard|stop|continue|wait|(?:go|put|take|plate|chop|pickup|throw|clear|extinguish) [a-zA-Z0-9_ .-]{1,60})', action):
            row['action'] = action
        events.append(row)
    return events


def round_export(session, status):
    """One round, every allowlisted event: status is finished, aborted, in_progress or not_started."""
    k, ai = session.k, session.ai
    events = allowed_events(k)
    count = lambda s: sum(o.get('status') == s for o in getattr(k, 'orders', []))
    level = session.c.get('level_id')
    return {'round_id': session.game_id, 'level_id': level,
            'level_name': next((l['name'] for l in available_levels() if l['id'] == level), level),
            'status': status, 'started_at': getattr(session, 'round_started_at', None),
            'speed': session.speed, 'game_seconds': round(k.time, 3),
            'summary': {'served': k.served, 'money': k.money, 'target_money': k.rules.goal['min_money'],
                        'won': k.won() if k.ended else None, 'failure_reason': getattr(k, 'failure_reason', None),
                        'expired': count('expired'), 'unresolved_at_close': count('unresolved_at_close'),
                        'burns': getattr(k, 'burns', 0), 'fires': getattr(k, 'fires', 0)},
            'round_record': session.round_record() if k.ended else None,
            'api': {'calls': ai.calls if ai else 0, 'successful_responses': ai.successes if ai else 0,
                    'request_or_parse_errors': ai.error_count if ai else 0,
                    'stale_or_cancelled_responses': ai.stale_count if ai else 0,
                    'game_rule_rejections': ai.rejected_count if ai else 0,
                    'max_calls': ai.call_limit if ai else session.c.get('ai_max_calls', 200),
                    'usage': dict(ai.tokens) if ai else {}, 'usage_scope': 'successful_responses_only'},
            'event_counts': dict(Counter(e['kind'] for e in events)),
            'events': events,
            'bookmarks': deepcopy(session.bookmarks),
            'player_messages': deepcopy(session.player_messages)}


def play_export(session):
    """Everything allowlisted from this play session: every round since the game (or page) opened."""
    rounds = deepcopy(session.history)
    if session.game_id not in {r['round_id'] for r in rounds}:
        started = session.phase in ('running', 'paused') or session.journal is not None
        if started or session.k.events or session.bookmarks or session.player_messages or not rounds:
            rounds.append(round_export(session, 'in_progress' if started else 'not_started'))
    return {'schema_version': 3, 'export_scope': 'play_session', 'release': getattr(session, 'release', None),
            'session_started_at': session.session_started_at,
            'exported_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            'provider': (getattr(session, 'setting', None) or {}).get('provider', 'unconfigured'),
            'current_round_id': session.game_id, 'phase': session.phase,
            'totals': {'rounds': len(rounds), 'won': sum(r['summary']['won'] is True for r in rounds),
                       'served': sum(r['summary']['served'] for r in rounds),
                       'money': sum(r['summary']['money'] for r in rounds),
                       'api_calls': sum(r['api']['calls'] for r in rounds)},
            'rounds': rounds,
            'bookmark_policy': dict(BOOKMARK_POLICY),
            # No user-provided model/base URL, path, notes, memory or payload.
            'excluded': list(EXCLUDED),
            'coverage': f'Every round of this play session (up to the latest {HISTORY_LIMIT}), each with its '
                        'summary, work record, all bookmarks, messages and every allowlisted game event. '
                        'Not a frame-by-frame replay; the local run log keeps full context.'}
