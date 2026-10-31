#!/usr/bin/env python3
"""Isolated, ephemeral kitchens. Browser-direct models or an explicit opt-in Jev relay.
Run behind the supplied HTTPS reverse proxy, never expose the Python port directly.
"""
import argparse
import hashlib
import ipaddress
from copy import deepcopy
import json
import math
import mimetypes
from pathlib import Path
import secrets
import signal
import sqlite3
import threading
import time
from collections import Counter, OrderedDict, deque
from urllib.parse import urlsplit, unquote
from http.server import ThreadingHTTPServer
from kitchen import ROOT
from spatial_kitchen import SpatialKitchen
from whitebox_server import SpatialJevClient
from web_server import GameSession, Handler
from release_info import release_info
from feedback import play_export
from hosted_records import ContributionStore, pilot_record, CONSENT_VERSION
from hosted_capacity import ActiveKitchens, RequestBudget, NETWORK_FULL
from hosted_jev import JevForwarder
from hosted_usage import UsageStats
from cooperation_memory import (ROUNDS, EVENTS, CONTEXT_CHARACTERS, DESCRIPTION,
                                memory_namespace, memory_context, portable_episode, validate_memory_condition)

HOSTED_HISTORY_LIMIT = 20  # rounds kept per page for the data export; bounds memory under MemoryMax


class NullJournal:
    """Never creates local journals, model payload logs, or memory files."""
    def __init__(self, *_): pass
    def __call__(self, *_): pass
    def close(self): pass


class BrowserRelay(SpatialJevClient):
    def __init__(self, config):
        # Payload construction only; never loads a machine credential or uses ask().
        super().__init__(config, key='browser-transport-no-server-credential')
        self.guard = threading.Lock()
        self.pending = None
        self.closed = False

    def ask(self, payload):
        task = {'id': secrets.token_urlsafe(24), 'payload': deepcopy(payload),
                'event': threading.Event(), 'result': None, 'sent': time.monotonic()}
        with self.guard:
            if self.closed: raise RuntimeError('Browser connection closed')
            self.pending = task
        try:
            if not task['event'].wait(24) or task['result'] is None:
                raise RuntimeError('Browser model request failed or expired')
            return task['result']
        finally:
            with self.guard:
                if self.pending is task: self.pending = None

    def request(self):
        with self.guard:
            task = self.pending
            if not task or task['event'].is_set(): return None
            return {'id': task['id'], 'payload': deepcopy(task['payload'])}

    def resolve(self, body):
        with self.guard:
            task = self.pending
            if not task or body.get('id') != task['id'] or task['event'].is_set(): return False
            if body.get('failed') is True:
                task['event'].set()
                return True
            choice = body.get('choice')
            criteria = task['payload']['questions']['next_action']['criteria']
            if not isinstance(choice, str) or choice not in criteria or type(body.get('sprint')) is not bool:
                return False
            usage = body.get('usage', {})
            if not isinstance(usage, dict) or set(usage) - {'input_tokens', 'output_tokens'}: return False
            if any(type(v) is not int or not 0 <= v <= 10000000 for v in usage.values()): return False
            task['result'] = {'choice': choice, 'sprint': body['sprint'], 'model': 'browser-model',
                              'usage': usage, 'latency': time.monotonic() - task['sent'],
                              'confidence': None, 'probabilities': {}}
            task['event'].set()
            return True

    def cancel(self):
        with self.guard:
            if self.pending: self.pending['event'].set()

    def close(self):
        with self.guard:
            self.closed = True
            if self.pending: self.pending['event'].set()


class HostedSession(GameSession):
    def __init__(self, release=None):
        self.relay = None
        self.positions = []
        self.receipt = None
        self.receipt_round = None
        self.research_armed = None
        self.research_telemetry = False
        self.research_active = False
        self.research_error = None
        self.research_mode = 'standing'
        self.store = None
        self.connected = False
        self.round_memory_condition = None
        self.usage = None
        self.usage_started = False  # Once per page session, including retries, restarts and later levels.
        self.usage_end_reason = 'restart'
        self.usage_visit_reported = False
        self.usage_play_reported = False
        self.release = release if release is not None else release_info()
        self.setting = None  # Connection secrets and endpoints remain browser-owned.
        self.jev_gate = threading.Lock()
        self.jev_receipts = OrderedDict()  # Sanitized answers/statuses only, never keys.
        self.jev_last_check = float('-inf')
        super().__init__(client_factory=self._client, journal_factory=NullJournal,
                         kitchen_factory=SpatialKitchen, log_prefix='hosted')
        self.history_limit = HOSTED_HISTORY_LIMIT
        self.network = None  # Set by Sessions.create; used only in memory for the per-network limit.
        self.c['ai_max_response_age'] = 15
        self.base_config['ai_max_response_age'] = 15
        self.deployment_mode = 'hosted'

    def _client(self, config):
        if self.relay: self.relay.close()
        self.relay = BrowserRelay(config)
        return self.relay

    def _finish(self, aborted=False):
        started = bool(self.journal)
        completed = bool(self.journal and self.phase == 'ended' and self.k.ended
                         and not aborted and not self.k.aborted)
        super()._finish(aborted)
        if started:
            self._persist_research()
        if started and self.usage:
            self.usage.end_round(self.c['level'], 'completed' if completed else self.usage_end_reason,
                                 self.k.time, self.speed)

    def _persist_research(self):
        if not self.research_active or not self.store or self.receipt_round != self.game_id:
            return
        try:
            data = {**pilot_record(self), 'consent_mode': self.research_mode}
            if not self.store.update(self.receipt['id'], data):
                self.research_active = False  # withdrawn or expired, never recreate
            self.research_error = None
        except (ValueError, OSError, sqlite3.Error):
            # The opening snapshot stays on disk, marked incomplete; the page must not call this round contributed.
            self.research_error = 'storage_failed'

    def command(self, path, body):
        # Actual browser command receipt, separate from model choice and engine execution.
        with self.lock:
            log = self.journal
            input_id = None
            gameplay = path in ('/api/action', '/api/interact', '/api/throw', '/api/select', '/api/move', '/api/position')
            if log and gameplay and body.get('game_id') == self.game_id:
                row = log._envelope('browser_input', {'command': path[5:], 'stage': 'server_received',
                                                     'raw_device_input': 'not_collected'}, 'session')
                row['actor_id'] = 'human'
                input_id = log._append(row)
            result = super().command(path, body)
            if log and input_id is not None:
                job = self.k.chefs['human'].job
                row = log._envelope('browser_result', {'command': path[5:], 'accepted': result[0] < 400,
                    'stage': 'server_command_result', 'reason': None if result[0] < 400 else 'command_rejected'}, 'session')
                row.update(actor_id='human', input_id=input_id, action_id=job.id if job and result[0] < 400 else None)
                log._append(row)
            return result

    def public_state(self):
        with self.lock:
            state = super().public_state()
            ai = self.ai
            limit = ai.call_limit if ai else self.c.get('ai_max_calls', 200)
            state['connection'] = {'configured': self.connected, 'editable': self.phase in ('ready', 'ended')}
            state['limits'] = {'max_calls': limit, 'next_max_calls': self.c.get('ai_max_calls', 200),
                'calls': ai.calls if ai else 0, 'remaining': max(0, limit - (ai.calls if ai else 0)),
                'reached': bool(ai and ai.calls >= limit), 'editable': self.phase in ('ready', 'ended'),
                'connection_checks': 0, 'usage': dict(ai.tokens) if ai else {'input_tokens': 0, 'output_tokens': 0}}
            # The browser owns persistent records and model scopes. Only this kitchen's
            # completed, allowlisted episode is exposed to its authenticated page.
            if self.phase == 'ended' and self.k.ended and not self.k.aborted and self.round_started_at:
                if getattr(self, '_memory_episode', (None,))[0] != self.game_id:
                    self._memory_episode = (self.game_id, portable_episode(
                        self.k, self.game_id, self.player_messages, self.round_record()))
                record = self._memory_episode[1]
            else:
                record = None
            state['memory'] = {'supported': True, 'enabled': True, 'editable': self.phase in ('ready','ended'),
                               'saved_rounds': 0, 'limit': ROUNDS, 'used_rounds': 0, 'event_limit': EVENTS,
                               'namespace': memory_namespace(), 'level_id': self.c['level_id'],
                               'max_characters': CONTEXT_CHARACTERS, 'description': DESCRIPTION,
                               'episode': record}
            state['release'] = self.release
            state['hosted'] = {'retention': 'session-only', 'idle_minutes': 10, 'contribution_enabled': self.store is not None,
                               'contributed': self.receipt_round == self.game_id and self.phase == 'ended' and not self.research_error,
                               'contribution_receipt': self.receipt if self.receipt_round == self.game_id else None,
                               'research_active': self.research_active and self.receipt_round == self.game_id, 'research_error': self.research_error}
            return state

    def _record_context_close(self, reason):
        log = self.session_log
        if self.phase == 'ended' and log and log.round_id == self.game_id and log.termination is None:
            log.observe_close(reason)
            self._persist_research()

    def _command(self, path, body):
        if path == '/api/contribution/consent':
            if set(body) - {'game_id', 'request_id', 'consent', 'consent_version', 'decision_telemetry', 'model_identity'}:
                return 400, {'error': '同意字段无效。'}
            if type(body.get('consent')) is not bool or body.get('consent_version') != CONSENT_VERSION or type(body.get('decision_telemetry', False)) is not bool:
                return 400, {'error': '请阅读并选择本版数据说明。'}
            if body['consent']:
                if not self.store: return 503, {'error': '未开启数据贡献。'}
                if self.phase not in ('ready', 'paused', 'ended'):
                    return 409, {'error': '自动贡献需在下一局开始前确认。'}
                from research_record import reported_model_identity
                try:
                    identity = reported_model_identity(body.get('model_identity'))
                except ValueError as error:
                    return 400, {'error': str(error)}
                self.research_armed = {'decision_telemetry': body.get('decision_telemetry', False),
                                       'model_identity': identity}
            else:
                self.research_armed = None
                if self.research_active and self.phase in ('running', 'paused') and self.receipt_round == self.game_id and self.store:
                    try:
                        self.store.delete(self.receipt['id'], self.receipt['deletion_token'])
                    except (OSError, sqlite3.Error):
                        self.research_active = False
                        self.research_telemetry = False
                        if self.journal:
                            self.journal.observations_withdrawn = self.journal.capture_observations
                            self.journal.capture_observations = False
                        return 503, {'error': '已停止继续记录，服务器删除失败，请保留凭证并稍后重试。'}
                    self.receipt = None
                    self.receipt_round = None
                self.research_active = False
                self.research_telemetry = False
                if self.journal:
                    self.journal.observations_withdrawn = self.journal.capture_observations
                    self.journal.capture_observations = False
            return 200, {'ok': True, 'consent_version': CONSENT_VERSION}
        if path == '/api/contribution/preview':
            if not self.session_log or self.session_log.round_id != self.game_id or self.session_log.kitchen is not self.k:
                return 409, {'error': '开局后可预览本局记录。'}
            return 200, {'record':{**pilot_record(self), 'consent_mode': 'standing' if self.research_active else 'round'}, 'consent_version':CONSENT_VERSION}
        if path == '/api/contribution/save':
            if self.phase != 'ended': return 409, {'error':'请结束本局后再贡献数据。'}
            if not self.store: return 503, {'error':'未开启数据贡献。'}
            if body.get('consent') is not True or body.get('consent_version') != CONSENT_VERSION:
                return 400, {'error':'请先明确同意数据用途和保存期限。'}
            mode = body.get('consent_mode', 'round')
            if mode not in ('round', 'standing'):
                return 400, {'error':'请先明确同意数据用途和保存期限。'}
            if self.receipt_round != self.game_id:
                from research_record import reported_model_identity
                try:
                    identity = reported_model_identity(body.get('model_identity'))
                except ValueError as error:
                    return 400, {'error': str(error)}
                if self.session_log and self.session_log.round_id == self.game_id and not getattr(self.session_log, 'model_identity', None):
                    self.session_log.model_identity = identity
                try:
                    self.receipt = self.store.save({**pilot_record(self), 'consent_mode':mode})
                except (ValueError, OSError, sqlite3.Error):
                    return 503, {'error': '贡献保存失败，请下载本局预览并稍后重试。'}
                self.receipt_round = self.game_id
                self.research_active = True
                self.research_mode = mode
                self.research_error = None
            elif self.research_error:
                # The finished round never reached disk: try again, and say so if it still fails.
                self._persist_research()
                if self.research_error:
                    return 503, {'error': '贡献保存失败，请下载本局预览并稍后重试。'}
            return 200, {'receipt':self.receipt}
        if path == '/api/browser-ready':
            if self.phase not in ('ready', 'ended'): return 409, {'error': '请先结束当前对局。'}
            if type(body.get('connected')) is not bool: return 400, {'error': '连接状态无效。'}
            self.connected = body['connected']
            return 200, {'ok': True}
        if path in ('/api/start','/api/next') and not self.connected:
            return 428, {'error': '请先在当前浏览器连接模型服务。'}
        if path == '/api/limits':
            n = body.get('max_calls')
            if self.phase not in ('ready', 'ended'): return 409, {'error': '请先结束当前对局。'}
            if type(n) is not int or not 1 <= n <= 2000: return 400, {'error': '调用上限必须为 1–2000。'}
            self.c['ai_max_calls'] = n
            return 200, {'ok': True, 'next_max_calls': n}
        if path in ('/api/export-run', '/api/feedback'):
            report = play_export(self)
            report['coverage'] = (f'The latest {self.history_limit} rounds since this page opened, each with its summary, '
                                  'work record, bookmarks, messages and every allowlisted game event. '
                                  'No persistent server journal exists.')
            report['bookmark_policy'].pop('log_join', None)
            return 200, {'ok': True, 'report': report}
        if path in ('/api/pause', '/api/end', '/api/reset', '/api/level', '/api/next') and self.relay:
            self.relay.cancel()
        previous_reason = self.usage_end_reason
        if path == '/api/next': self.pending_close_reason = 'next_level'
        elif path in ('/api/restart', '/api/reset'): self.pending_close_reason = 'restart'
        if path == '/api/end': self.usage_end_reason = 'manual_end'
        try:
            response = super()._command(path, body)
        finally:
            self.usage_end_reason = previous_reason
        if path == '/api/start' and response[0] == 200:
            self.research_active = False
            self.research_mode = 'standing'
            self.round_memory_condition = None
            self.research_telemetry = bool(self.research_armed and self.research_armed['decision_telemetry'])
            self.research_error = None
            # Freeze this round's consented metadata before the first disk snapshot.
            self.session_log.model_identity = deepcopy((self.research_armed or {}).get('model_identity'))
            if self.research_armed and self.store:
                try:
                    self.receipt = self.store.save({**pilot_record(self), 'consent_mode': 'standing'})
                    self.receipt_round = self.game_id
                    self.research_active = True
                    response = (response[0], {**response[1], 'receipt': self.receipt})
                except (ValueError, OSError, sqlite3.Error):
                    self.research_error = 'storage_failed'
            self.research_armed = None  # each next round needs its own pre-start declaration
            self.round_memory_condition = None
            # Establish the canonical memory rules in every pending payload. The page
            # supplies its frozen browser-only history when calling its chosen model.
            self.ai.cooperation_memory = memory_context(False, [])
            if self.usage:
                self.usage.start_round(self.c['level'], first=not self.usage_started)
            self.usage_started = True
        if path == '/api/reset' and response[0] == 200:
            self.round_memory_condition = None
        return response

    def close(self):
        with self.lock:
            observed_close = getattr(self, 'usage_close_reason', None)
            self.usage_end_reason = observed_close or 'page_close'  # existing aggregate contract
            self.round_close_reason = {'page_close': 'page_close_request', 'disconnected': 'idle_timeout',
                                       'shutdown': 'server_shutdown'}.get(observed_close, 'not_observed')
            if self.faulted:
                self.round_close_reason = 'engine_fault'
            if self.session_log and self.session_log.round_id == self.game_id and self.session_log.closed:
                self.session_log.observe_close(self.round_close_reason)
                self._persist_research()
            if self.relay: self.relay.close()
            super().close()


# Game fields plus the explicit opt-in Jev route. Never echo invalid bodies.
FIELDS = {
    '/api/usage': {'first_visit', 'first_play'},
    '/api/model/jev': {'api_key','consent','consent_version','test','id','memory'},
    '/api/contribution/preview': set(),
    '/api/contribution/consent': {'consent', 'consent_version', 'decision_telemetry', 'model_identity'},
    '/api/contribution/save': {'consent', 'consent_version', 'consent_mode', 'model_identity'},
    '/api/browser-ready': {'connected'}, '/api/start': {'speed'}, '/api/pause': {'reason'},
    '/api/resume': set(), '/api/end': set(), '/api/reset': set(), '/api/restart': set(),
    '/api/level': {'level'}, '/api/next': {'level'}, '/api/limits': {'max_calls'}, '/api/export-run': set(),
    '/api/feedback': set(), '/api/bookmark': set(), '/api/communicate': {'code'},
    '/api/move': {'dx', 'dy', 'seq', 'sprint'}, '/api/position': {'seq', 'base', 'at', 'press'}, '/api/select': {'target'},
    '/api/interact': {'expected_item', 'mode', 'at', 'base', 'aim', 'target'}, '/api/throw': {'direction', 'expected_item', 'at', 'base'},
    '/api/action': {'action', 'expected'},
    '/api/model/result': {'id', 'choice', 'sprint', 'usage', 'failed','memory_condition','telemetry'},
}


class Sessions:
    def __init__(self, capacity=8, ttl=600, factory=HostedSession, store=None, max_waiting=32, per_network=None, usage=None):
        self.capacity, self.ttl, self.factory = capacity, ttl, factory
        self.pool_limit = capacity + max_waiting
        self.slots = ActiveKitchens(capacity, per_network=per_network)
        self.budgets = {}
        self.rate_rejections = 0
        self.creating = 0
        self.closed = False
        self.store = store
        self.usage = usage
        self.entries = {}
        self.lock = threading.RLock()

    def reap(self):
        expired = []
        with self.lock:
            cutoff = time.monotonic() - self.ttl
            for token, (session, seen) in list(self.entries.items()):
                if seen < cutoff:
                    expired.append(session)
                    del self.entries[token]
                    self.budgets.pop(token, None)
            self.slots.refresh(self.entries)
        # Closing/summary calculation must not hold the global admission lock.
        for session in expired:
            session.usage_close_reason = 'disconnected'
            session.close()

    def create(self, network=None):
        self.reap()
        with self.lock:
            if self.closed: return None
            if len(self.entries)+self.creating >= self.pool_limit:
                if self.usage: self.usage.increment('page_full_rejections')
                return None
            self.creating += 1
        try:
            session = self.factory()
            session.store = self.store
            session.usage = self.usage
            session.network = network
            token = secrets.token_urlsafe(32)
        except BaseException:
            with self.lock: self.creating -= 1
            raise
        with self.lock:
            self.creating -= 1
            if not self.closed:
                self.entries[token] = (session, time.monotonic())
                self.budgets[token] = RequestBudget()
                threading.Thread(target=session.run, daemon=True).start()
                return token
        session.usage_close_reason = 'shutdown'
        session.close()
        return None

    def get(self, token):
        self.reap()
        with self.lock:
            found = self.entries.get(token)
            if not found: return None
            session, _ = found
            self.entries[token] = (session, time.monotonic())
            return session

    def remove(self, token):
        with self.lock:
            found = self.entries.pop(token, None)
            self.budgets.pop(token, None)
            self.slots.refresh(self.entries)
        if found:
            found[0].usage_close_reason = 'page_close'
            found[0].close()
        return found is not None

    def allow_request(self, token):
        with self.lock:
            budget = self.budgets.get(token)
            ok = budget is not None and budget.take()
            if not ok: self.rate_rejections += 1
            return ok

    def capacity_state(self, token):
        with self.lock:
            return self.slots.describe(token, self.entries)

    def reserve(self, token):
        with self.lock:
            if token not in self.entries: return None
            result = self.slots.reserve(token, self.entries)
            if self.usage:
                if result is None: self.usage.increment('kitchen_full_rejections')
                elif result == NETWORK_FULL: self.usage.increment('network_full_rejections')
            return result

    def settle(self, token, allocated, success):
        with self.lock:
            self.slots.settle(token, self.entries, allocated, success)

    def close(self):
        with self.lock:
            self.closed = True
            games = list(self.entries.values())
            self.entries.clear()
            self.budgets.clear()
            self.slots.refresh(self.entries)
        for session, _ in games:
            session.usage_close_reason = 'shutdown'
            session.close()


# Hosted-only copy swapped into the local web shell. Each anchor must stay verbatim in
# cocos-kitchen/web-shell.html (tests/test_hosted.py checks this).
SHELL_REPLACEMENTS = (
    ('默认只在本次服务运行期间使用。记住后以明文保存在这台电脑的本地配置文件；Key 不进入对局日志和试玩包。',
        '在线版：Key 默认在页面内存中，刷新即清除；主动记住会将 Key 和所选转发方式以明文保存在浏览器 localStorage。浏览器直连时 Key 只发给模型服务；明确勾选 Jev 转发后，Key 和模型请求经试玩服务器发送给 Jev，仅用于处理请求，不写入服务器配置、日志或对局记录。游戏状态经过我们的服务器，自愿贡献数据另见下方说明。'),
    ('这间厨房是围绕 Jev 开发的；其他模型也可使用，响应速度和配合方式可能不同。',
        '默认由浏览器直连模型，需供应商允许跨域访问。Jev 可明确勾选下方服务器转发；跨域失败不会自动改为转发。'),
    ('建议优先选择 Jev', '在线模型连接'),
    ('仅保留到服务关闭', '仅保留到当前页面会话结束'),
    ('本次服务连接测试', '本页面连接测试'),
    ('可对应本地日志提取前后过程', '在线版没有可追溯的服务器对局日志'),
    ('导出本次游玩的全部数据：从启动游戏起玩过的每一局', '导出本次游玩的数据：从打开本页面起最近 20 局'),
    ('记录保存在本机，旧局片段会随决策请求发送给你选择的模型服务，增加输入 token 和费用。关闭后不读、不保存；中途退出的局不保存。',
        '在线版默认开启，摘要保存在当前浏览器；开局时固定本局使用的旧局摘要，随请求发给所选模型。Jev 转发也会处理这些摘要，但服务器不持久保存。可在这里关闭或清空；中途退出的局不保存。摘要会增加输入 token 和费用。'),
)
CONTRIBUTION_SLOT = '<!-- hosted-contribution -->'
CONTRIBUTION_BADGE = ('<p id="contribution-badge" role="status" hidden style="position:fixed;left:50%;bottom:8px;'
                      'transform:translateX(-50%);z-index:60;margin:0;padding:3px 10px;background:#2b1a12cc;'
                      'color:#fff;font:12px/16px system-ui,sans-serif;pointer-events:none"></p>')


def hosted_html(raw):
    page = raw.decode('utf-8')
    page = page.replace('<head>', '<head><script src="/model-providers.js"></script><script src="/hosted-agent.js"></script>', 1)
    for old, new in SHELL_REPLACEMENTS:
        page = page.replace(old, new)
    panel = (ROOT / 'hosted' / 'contribution.html').read_text()
    # The one-time contribution question sits beside the dialogs, outside Settings.
    consent = (ROOT / 'hosted' / 'consent.html').read_text()
    page = page.replace('</body>', consent + CONTRIBUTION_BADGE + '</body>', 1)
    # Newer shells mark a slot in the Export tab; older builds append to the settings dialog.
    page = page.replace(CONTRIBUTION_SLOT, panel, 1) if CONTRIBUTION_SLOT in page else page.replace('</dialog>', panel + '</dialog>', 1)
    return page.encode('utf-8')


class RuntimeMetrics:
    """Aggregate operational counters only; no player IDs, IPs or payloads."""
    def __init__(self):
        self.lock = threading.Lock()
        self.statuses = Counter()
        self.latencies = deque(maxlen=4096)
        self.overloaded = 0
        self.last_wall = time.monotonic()
        self.last_cpu = time.process_time()

    def record(self, status, elapsed):
        with self.lock:
            self.statuses[status] += 1
            self.latencies.append(elapsed*1000)

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            cpu = time.process_time()
            percent = (cpu-self.last_cpu)/max(.001, now-self.last_wall)*100
            self.last_wall, self.last_cpu = now, cpu
            rows = sorted(self.latencies)
            percentile = lambda p: round(rows[min(len(rows)-1, int((len(rows)-1)*p))], 2) if rows else None
            state = {'responses':dict(self.statuses), 'recent_latency_ms':{'p95':percentile(.95), 'p99':percentile(.99)},
                     'overload_rejections':self.overloaded, 'python_cpu_percent_one_core':round(percent, 1),
                     'python_threads':threading.active_count()}
        try:
            import resource, sys
            state['python_peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1024 if sys.platform.startswith('linux') else 1)
        except ImportError:
            pass
        try:
            import os
            state['python_rss_bytes'] = int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
            cgroup = next(line.split(':',2)[2].strip() for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::'))
            base = Path('/sys/fs/cgroup')/cgroup.lstrip('/')
            state['service_memory_bytes'] = int((base/'memory.current').read_text())
        except (OSError, ValueError, StopIteration, IndexError):
            pass
        return state


class HostedHTTPServer(ThreadingHTTPServer):
    request_queue_size = 128

    def __init__(self, *args, **kwargs):
        self.request_slots = threading.BoundedSemaphore(32)
        self.metrics = RuntimeMetrics()
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        if not self.request_slots.acquire(blocking=False):
            with self.metrics.lock: self.metrics.overloaded += 1
            try:
                request.settimeout(1)
                body = json.dumps({'error':'厨房请求较多，请稍后重试。'}, ensure_ascii=False).encode()
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json\r\n'
                                b'Cache-Control: no-store\r\nRetry-After: 1\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.request_slots.release()

    def server_close(self):
        close_usage = getattr(getattr(self, 'usage', None), 'close', None)
        if close_usage:
            close_usage()
        super().server_close()


class HostedHandler(Handler):
    def reply(self, status, data, content_type='application/json; charset=utf-8',
              cache_control='no-store', etag=None):
        raw = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
        self._cache_control = cache_control
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        if status in (429,503): self.send_header('Retry-After','1')
        if status != 304:
            self.send_header('Content-Length', str(len(raw)))
        if etag:
            self.send_header('ETag', etag)
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.server.metrics.record(status, time.monotonic()-getattr(self, '_request_started', time.monotonic()))

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', getattr(self, '_cache_control', 'no-store'))
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' https:; img-src 'self' data: blob:; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        super().end_headers()

    def valid_origin(self, post=False):
        origin = self.server.public_origin
        return (self.headers.get('Host') == urlsplit(origin).netloc
                and self.headers.get('Origin', origin if not post else '') == origin
                and self.headers.get('Sec-Fetch-Site') not in ('cross-site', 'same-site'))

    def session(self):
        token = self.headers.get('X-ChefJeff-Session', '')
        game = self.server.sessions.get(token)
        stopping = self.command == 'POST' and urlsplit(self.path).path in ('/api/pause','/api/end')
        self._session_limited = game is not None and not stopping and not self.server.sessions.allow_request(token)
        return game

    def client_network(self):
        """The player's network from Nginx's client address (an IPv6 /64). Memory only, never logged.

        Without the header (an older proxy config, or a direct local run) every page would share
        the proxy's address, so no per-network limit applies; the total capacity still does."""
        raw = self.headers.get('X-ChefJeff-Client')
        if not raw: return None
        try:
            ip = ipaddress.ip_address(raw.strip())
        except ValueError:
            return None
        if ip.version == 6 and ip.ipv4_mapped: ip = ip.ipv4_mapped
        return str(ipaddress.ip_network(f'{ip}/64', strict=False)) if ip.version == 6 else str(ip)

    def limited(self):
        if not self._session_limited: return False
        self.reply(429, {'error':'操作过于频繁，请稍后重试。'})
        return True

    def do_GET(self):
        self._request_started = time.monotonic()
        if not self.valid_origin(): return self.reply(403, {'error': '请求来源不允许。'})
        path = unquote(urlsplit(self.path).path)
        if path == '/healthz': return self.reply(200, {'ok': True})
        if path == '/ops/usage':
            # Nginx blocks /ops/ and always adds this header on public requests.
            if self.headers.get('X-ChefJeff-Client') is not None:
                return self.reply(404, {'error': '未找到页面或资源。'})
            sessions = self.server.sessions
            sessions.reap()
            with sessions.lock:
                running = sum(g.phase == 'running' and not g.faulted and not g.stop_event.is_set()
                              for g, _ in sessions.entries.values())
            usage = self.server.usage.snapshot()
            if usage.get('shared'):
                usage['regional_running_sessions'] = running
                if usage.get('scope') != 'global':
                    usage['running_sessions'] = running
            else:
                usage['running_sessions'] = running
            return self.reply(200, {'usage': usage})
        if path == '/ops/capacity':
            sessions = self.server.sessions
            with sessions.lock:
                capacity = sessions.slots.describe('', sessions.entries)
                capacity.pop('can_start');capacity.pop('reason')
                capacity.update(page_sessions=len(sessions.entries), session_limit=sessions.pool_limit,
                                admission_rejections=sessions.slots.rejected, network_rejections=sessions.slots.network_rejected,
                                session_rate_rejections=sessions.rate_rejections,
                                faulted_kitchens=sum(bool(getattr(g,'faulted',False)) for g,_ in sessions.entries.values()))
            return self.reply(200, {'capacity':capacity, 'runtime':self.server.metrics.snapshot()})
        if path.startswith('/api/'):
            game = self.session()
            if not game: return self.reply(401, {'error': '厨房会话已过期，请刷新页面创建新厨房。'})
            if self.limited(): return
            with game.lock:
                if path == '/api/state':
                    state = game.public_state()
                    state['capacity'] = self.server.sessions.capacity_state(self.headers.get('X-ChefJeff-Session',''))
                    return self.reply(200, state)
                if path == '/api/model/request':
                    return self.reply(200, {'request': game.relay.request() if game.relay and game.phase == 'running' else None})
            return self.reply(404, {'error': '未知的接口。'})
        root = self.server.web_root.resolve()
        file = (root / path.lstrip('/')).resolve()
        if file == root: file = root / 'index.html'
        if path == '/hosted-agent.js': file = ROOT / 'hosted' / 'browser-agent.js'
        elif not file.is_relative_to(root): return self.reply(404, {'error': '未找到页面或资源。'})
        if not file.is_file() or file.suffix not in ('.html','.js','.json','.css','.png','.jpg','.webp','.ico','.woff','.woff2','.ttf','.mp3','.wasm','.bin','.cconb'):
            return self.reply(404, {'error': '未找到页面或资源。'})
        data = file.read_bytes()
        content_type = mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
        # HTML stays fresh and uncached. Asset URLs are not all content-addressed,
        # so always revalidate them rather than giving old builds a long lifetime.
        if file.suffix == '.html':
            if file.name == 'index.html':
                data = hosted_html(data)
                self.server.usage.increment('page_views')
            return self.reply(200, data, content_type)
        etag = '"' + hashlib.sha256(data).hexdigest() + '"'
        candidates = [tag.strip().removeprefix('W/') for tag in self.headers.get('If-None-Match', '').split(',')]
        cached = etag in candidates or '*' in candidates
        self.reply(304 if cached else 200, b'' if cached else data, content_type,
                   cache_control='public, max-age=0, must-revalidate', etag=etag)

    def do_POST(self):
        self._request_started = time.monotonic()
        if not self.valid_origin(post=True): return self.reply(403, {'error': '请求来源不允许。'})
        path = urlsplit(self.path).path
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(415, {'error': '请求必须使用 JSON 格式。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= (12288 if path == '/api/model/jev' else 8192): raise ValueError()
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError()
        except (ValueError, OSError): return self.reply(400, {'error': '请求无效。'})
        if path == '/api/session':
            if body: return self.reply(400, {'error': '创建厨房的请求不得包含额外字段。'})
            token = self.server.sessions.create(self.client_network())
            return self.reply(201 if token else 503, {'session': token} if token else {'error': '厨房暂时已满，请稍后重试。'})
        if path == '/api/session/close':
            if body: return self.reply(400, {'error': '关闭厨房的请求不得包含额外字段。'})
            token = self.headers.get('X-ChefJeff-Session', '')
            if not self.server.sessions.remove(token):
                return self.reply(401, {'error': '厨房会话已过期。'})
            return self.reply(200, {'ok': True})
        if path == '/api/contribution/download':
            if set(body) != {'id', 'deletion_token'} or not self.server.sessions.store:
                return self.reply(400, {'error': '下载凭证无效。'})
            try:
                record = self.server.sessions.store.download(body['id'], body['deletion_token'])
            except (OSError, sqlite3.Error):
                return self.reply(503, {'error': '记录服务暂时不可用，请稍后重试。'})
            return self.reply(200, {'record': record}) if record else self.reply(404, {'error': '记录不存在或凭证无效。'})
        if path == '/api/contribution/delete':
            if set(body) != {'id','deletion_token'} or not self.server.sessions.store:
                return self.reply(400, {'error':'删除凭证无效。'})
            try:
                ok = self.server.sessions.store.delete(body['id'],body['deletion_token'])
            except (OSError, sqlite3.Error):
                return self.reply(503, {'error': '删除暂未完成，请保留凭证并稍后重试。'})
            return self.reply(200 if ok else 404, {'deleted':ok})
        if path not in FIELDS or set(body) - FIELDS[path] - {'game_id', 'request_id'}:
            return self.reply(400, {'error': '请求包含不支持的字段。'})
        game = self.session()
        if not game: return self.reply(401, {'error': '厨房会话已过期，请刷新页面。'})
        if self.limited(): return
        if path == '/api/usage':
            if set(body) != {'first_visit', 'first_play'} or any(type(v) is not bool for v in body.values()):
                return self.reply(400, {'error': '请求无效，请重试。'})
            with game.lock:
                if body['first_play'] and not game.usage_started:
                    return self.reply(409, {'error': '当前没有进行中的对局。'})
                self.server.usage.record_browsers(body['first_visit'] and not game.usage_visit_reported,
                                                  body['first_play'] and not game.usage_play_reported)
                game.usage_visit_reported |= body['first_visit']
                game.usage_play_reported |= body['first_play']
            return self.reply(200, {'ok': True})
        if path == '/api/model/jev':
            status, result = self.server.jev_forwarder.handle(game,body)
            return self.reply(status,result)
        try:
            with game.lock:
                if path == '/api/model/result':
                    condition = validate_memory_condition(body['memory_condition']) if 'memory_condition' in body else None
                    if condition and game.round_memory_condition is not None and condition != game.round_memory_condition:
                        return self.reply(409, {'error':'本局记忆条件已经固定。'})
                    telemetry = None
                    if 'telemetry' in body:
                        from research_record import validate_telemetry
                        telemetry = validate_telemetry(body['telemetry'])
                        if not game.research_telemetry:
                            return self.reply(400, {'error': '未同意可选决策测量。'})
                    ok = bool(game.relay and game.relay.resolve(body))
                    if ok and telemetry and game.journal:
                        pending = game.ai.calls if game.ai else None
                        game.journal._append(game.journal._envelope('client_telemetry',
                            {**telemetry, 'request_id': pending, 'source': 'client-reported',
                             'provider_verified': False}, 'session'))
                    if ok and condition:
                        game.round_memory_condition = condition
                    return self.reply(200 if ok else 409, {'ok': ok})
                token = self.headers.get('X-ChefJeff-Session','')
                allocated = None
                status = 500
                if path in ('/api/start','/api/next','/api/restart','/api/resume') and game.connected and body.get('game_id') == game.game_id:
                    allocated = self.server.sessions.reserve(token)
                    if allocated is None:
                        return self.reply(503, {'error':'厨房名额暂时已满，空位释放后请再试。'})
                    if allocated == NETWORK_FULL:
                        limit = self.server.sessions.slots.per_network
                        return self.reply(503, {'error':f'你所在的网络已同时开了 {limit} 个厨房，其中一个结束后再试。'})
                try:
                    status, result = game.command(path, body)
                finally:
                    self.server.sessions.settle(token, allocated is True, status < 400)
        except (ValueError, TypeError, KeyError, OverflowError):
            return self.reply(400, {'error': '游戏请求无效。'})
        self.reply(status, result)


def make_server(port, origin, capacity=8, web_root=None, data_dir=None, max_waiting=32, per_network=4, shared_config=None):
    if type(capacity) is not int or not 1 <= capacity <= 16 or type(max_waiting) is not int or not 0 <= max_waiting <= 32:
        raise ValueError('Use 1–16 active kitchens and 0–32 waiting pages.')
    if per_network is not None and (type(per_network) is not int or not 1 <= per_network <= 16):
        raise ValueError('Use 1–16 active kitchens per network.')
    if shared_config is not None and data_dir is None:
        raise ValueError('Shared mode requires a persistent regional usage outbox')
    client = None
    if shared_config is not None:
        from shared_client import SharedClient
        from shared_server import read_private_json
        client = SharedClient(shared_config if isinstance(shared_config, dict) else read_private_json(shared_config))
    server = HostedHTTPServer(('127.0.0.1', port), HostedHandler)
    server.public_origin = origin.rstrip('/')
    # Build identity is immutable for the life of this release, not per page.
    release = release_info()
    if client:
        from shared_client import RegionalUsage, RemoteRecords
        server.usage = RegionalUsage(data_dir, client)
        store = RemoteRecords(client)
    else:
        server.usage = UsageStats(data_dir)
        store = ContributionStore(data_dir) if data_dir else None
    server.sessions = Sessions(capacity, factory=lambda:HostedSession(release),
                               store=store, max_waiting=max_waiting,
                               per_network=per_network, usage=server.usage)
    server.jev_forwarder = JevForwarder()
    server.web_root = Path(web_root or ROOT / 'cocos-kitchen' / 'build' / 'web')
    if client:
        def running():
            with server.sessions.lock:
                return sum(g.phase == 'running' and not g.faulted and not g.stop_event.is_set()
                           for g, _ in server.sessions.entries.values())
        server.usage.start(running)
    return server


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8780)
    p.add_argument('--origin', required=True)
    p.add_argument('--web-root', type=Path)
    p.add_argument('--data-dir', type=Path, help='Enable opt-in six-month (180-day) contributions in this private directory.')
    p.add_argument('--shared-config', type=Path, help='Private backend data-service configuration; data-dir holds only regional usage in shared mode.')
    p.add_argument('--max-sessions', type=int, choices=range(1,17), default=8, help='Active kitchens, including short pause/result leases.')
    p.add_argument('--max-waiting', type=int, choices=range(0,33), default=32, help='Additional page sessions that cannot consume active slots.')
    p.add_argument('--max-per-network', type=int, choices=range(1,17), default=4,
                   help='Active kitchens one network (address or IPv6 /64) may hold at once.')
    args = p.parse_args()
    url = urlsplit(args.origin)
    if url.scheme != 'https' and url.hostname not in ('127.0.0.1', 'localhost'):
        p.error('A public origin must use HTTPS.')
    if url.path not in ('', '/') or url.query or url.fragment or url.username or not url.netloc:
        p.error('Use an origin, without a path or credentials.')
    server = make_server(args.port, args.origin, args.max_sessions, web_root=args.web_root, data_dir=args.data_dir, max_waiting=args.max_waiting,
                         per_network=args.max_per_network, shared_config=args.shared_config)
    def reap():
        while True:
            time.sleep(30)
            server.sessions.reap()
            if server.sessions.store: server.sessions.store.prune()
    threading.Thread(target=reap, daemon=True).start()
    # systemd sends SIGTERM during a normal update. Finish in-memory aggregates as
    # shutdowns, not player exits; shutdown() must run outside serve_forever's thread.
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    print('ChefJeff hosted service ready; persistent credentials and journals disabled.', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.sessions.close()
        server.server_close()


if __name__ == '__main__': main()
