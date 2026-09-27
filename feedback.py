"""Small allowlisted local feedback reports, never raw requests or free text."""
import re
from copy import deepcopy
from collections import Counter

EVENTS = {'order','action_start','action_done','interrupted','arrival_conflict',
          'picked_up','dropped','thrown','landed','swapped','ready','burn','fire',
          'served','expired','washed','plate_returned','round_end'}


def feedback_report(session):
    k=session.k
    events=[]
    for e in k.events:
        if e.get('kind') not in EVENTS:continue
        row={'t':e['t'],'kind':e['kind']}
        if e.get('actor') in ('human','jeff'):row['actor']=e['actor']
        # Action IDs come from the game, not arbitrary notes or provider text.
        action=e.get('action','')
        if re.fullmatch(r'(?:fetch|wash|serve|drop|discard|stop|continue|wait|(?:go|put|take|plate|chop|pickup|throw|clear|extinguish) [a-zA-Z0-9_ .-]{1,60})',action):
            row['action']=action
        events.append(row)
    ai=session.ai
    return {'schema_version':2,'release':session.release,'phase':session.phase,
            'round_id':session.game_id,'speed':session.speed,'game_seconds':round(k.time,3),
            'provider':(session.setting or {}).get('provider','unconfigured'),
            # No user-provided model/base URL, path, notes, memory or payload.
            'summary':{'served':k.served,'money':k.money,'bad_reviews':k.bad_reviews,
                       'won':k.won() if k.ended else None},
            'api':{'calls':ai.calls if ai else 0,'successful_responses':ai.successes if ai else 0,
                   'request_or_parse_errors':ai.error_count if ai else 0,
                   'stale_or_cancelled_responses':ai.stale_count if ai else 0,
                   'game_rule_rejections':ai.rejected_count if ai else 0,
                   'max_calls':ai.call_limit if ai else session.c.get('ai_max_calls',200),
                   'usage':dict(ai.tokens) if ai else {},'usage_scope':'successful_responses_only'},
            'event_counts':dict(Counter(e['kind'] for e in events)),
            'recent_events':events[-80:],
            'bookmarks':deepcopy(session.bookmarks),
            'player_messages':deepcopy(session.player_messages),
            'bookmark_policy':{'schema_version':1,'merge_window_seconds':5,
                               'merge_clock':'server_monotonic_real_time',
                               'merge_rule':'consecutive presses within 5 seconds of the previous press',
                               'game_clock':'seconds since round start',
                               'wall_clock':'ISO 8601 with timezone, captured on server receipt',
                               'event_index':'zero-based index of the next kitchen event at each mark',
                               'log_join':'round_id plus game time; bookmark updates use stable id',
                               'coverage':'All marked intervals, independent of the recent_events limit. Full surrounding context remains in the local run log.'},
            'excluded':['API keys','endpoint and model text','absolute paths','raw model responses',
                        'request snapshots','cross-round memory','free-text messages'],
            'coverage':'Summary, all bookmarks and last 80 allowlisted events; not a complete replay. Use round_id and bookmark times to extract surrounding context from the local run log.'}
