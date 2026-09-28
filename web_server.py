#!/usr/bin/env python3
"""Local click-to-play interface around the existing kitchen and real Jev loop."""
from __future__ import annotations
import argparse
from collections import OrderedDict
from dataclasses import asdict
from copy import deepcopy
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import threading
import traceback
import time
from urllib.parse import urlparse
import uuid
import webbrowser

from kitchen import Kitchen, ROOT, load_config
from jev import JevClient, DecisionLoop
from play import Journal
from session_record import SessionLog, write_bundle
from levels import available_levels


PLAYER_MESSAGES = {
    'prep': 'I prefer preparing ingredients.',
    'cook': 'I prefer cooking.',
    'plate': 'I prefer plating and assembling dishes.',
    'deliver': 'I prefer carrying ingredients and dishes between stations and serving customers.',
    'wash': 'I prefer washing dishes.',
    'mistake': 'You made a mistake. Please reassess your recent or current action.'
}


class GameSession:
    def __init__(self, config=None, client_factory=JevClient, journal_factory=Journal, kitchen_factory=Kitchen, log_prefix='web'):
        if config is None:
            # Players get the listed levels; an explicit flat config is the historical format (legacy levels).
            from levels import level_config
            config = level_config(load_config(), 1)
        self.c = dict(config)
        self.base_config = dict(self.c)
        self.client_factory = client_factory
        self.journal_factory = journal_factory
        self.kitchen_factory = kitchen_factory
        self.log_prefix = log_prefix
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.k = self.kitchen_factory(self.c)
        self.c = self.k.c
        self.game_id = uuid.uuid4().hex
        self.phase = 'ready'
        self.faulted = False
        self.speed = .75
        self.ai = None
        self.journal = None
        self.cursor = 0
        self.notes = []
        self.ai_error = None
        self.totals = {}
        self.receipts = OrderedDict()
        self.last_tick = time.monotonic()
        self.last_seen = self.last_tick
        self.game_backlog = 0.
        self.ticks = 0
        self.move_seq = -1
        self.move_until = 0.
        self.interaction_focus = None
        self.player_messages = []
        self.last_player_message_at = None
        self.bookmarks = []
        self.last_bookmark_at = None
        # Local play keeps a Session bundle beside the journal; other sinks keep records in memory only.
        self.session_log = None
        self.bundle_root = ROOT / 'logs' / 'sessions' if journal_factory is Journal else None
        self.deployment_mode = 'local'

    def note(self, message):
        self.notes.append({'t': round(self.k.time, 2), 'message': message})
        self.notes = self.notes[-30:]
        if message.startswith('Jeff 请求失败'):
            self.ai_error = 'AI 搭档暂时连接不上，正在重试。你仍可以操作或先暂停。'

    def _events(self):
        if self.journal:
            for event in self.k.events[self.cursor:]:
                self.journal('event', event)
        self.cursor = len(self.k.events)

    def _finish(self, aborted=False):
        if self.ai:
            self.ai.closed = True
            self.ai.invalidate()
        if self.journal:
            self._events()
            self.k.aborted = aborted
            self.journal('end', {'state': self.k.snapshot(), 'result': self.k.result(),
                                'aborted': aborted, 'ai_calls': self.ai.calls,
                                'ai_successes': self.ai.successes, 'usage': self.ai.tokens,
                                'bookmarks': deepcopy(self.bookmarks),
                                'player_messages': deepcopy(self.player_messages)})
            self.journal.close()
            if self.bundle_root is not None:
                try:
                    write_bundle(self.journal, self.bundle_root / self.game_id)
                except OSError as exc:
                    self.note(f'对局记录包未能保存（{type(exc).__name__}）')
            self.journal = None

    def _advance_ticks(self, elapsed, now):
        """Advance whole fixed game ticks; the fractional remainder carries over.

        Wall-clock polling decides only how many ticks run, never their size, so
        the same inputs at the same tick produce the same rule results.
        """
        tick = self.k.rules.tick
        self.game_backlog += elapsed*self.speed
        steps = int(self.game_backlog/tick+1e-9)
        self.game_backlog = max(0., self.game_backlog-steps*tick)
        moving = hasattr(self.k,'manual') and any(self.k.manual['human'])
        for i in range(steps):
            # Wall time at which this tick starts; a click-move ends at move_until.
            start = now-(self.game_backlog+(steps-i)*tick)/self.speed
            if moving and start >= self.move_until-1e-9:
                self.k.set_manual('human',0,0)
                moving = False
            self.k.advance(tick)
            self.ticks += 1
            if self.k.ended:
                break
        if moving and now >= self.move_until:
            self.k.set_manual('human',0,0)

    def tick(self, now=None):
        with self.lock:
            if self.faulted:
                return  # A round whose state check failed stays frozen until reset.
            now = time.monotonic() if now is None else now
            elapsed = max(0, now-self.last_tick)
            self.last_tick = now
            if self.phase != 'running' and hasattr(self.k,'set_manual'):
                self.k.set_manual('human',0,0)
            if self.phase == 'running':
                if now-self.last_seen > 8:
                    if hasattr(self.k,'set_manual'): self.k.set_manual('human',0,0)
                    self.phase = 'paused'
                    self.ai.invalidate()
                    self.note('页面已断开，厨房自动暂停。回来后点击继续。')
                else:
                    self._advance_ticks(elapsed, now)
                    if self.k.ended:
                        self.phase = 'ended'
                        self._finish()
            if self.ai and self.phase in ('running', 'paused'):
                self.ai.poll(enabled=self.phase == 'running')
                if self.ai.failures == 0:
                    self.ai_error = None
            self._events()
            for chef in self.k.chefs.values():
                if chef.job:
                    self.totals.setdefault(chef.job.id, chef.job.travel+chef.job.work)
            self.k.assert_invariants()

    def run(self):
        while not self.stop_event.wait(.05):
            try:
                self.tick()
            except Exception as exc:
                # Never let a broken round keep running, but keep the loop alive:
                # the faulted round freezes and the next round ticks normally.
                with self.lock:
                    self.phase = 'paused'
                    self.faulted = True
                    if self.ai:
                        self.ai.invalidate()
                    self.note('厨房已暂停：运行出现异常，请重新开局。')
                    try:
                        if self.journal:
                            self.journal('engine_error', {'t': self.k.time, 'error': f'{type(exc).__name__}: {exc}',
                                                          'trace': traceback.format_exc(limit=8)})
                    except Exception:
                        pass

    def close(self):
        self.stop_event.set()
        with self.lock:
            self._finish(aborted=self.phase != 'ended')

    def public_state(self):
        with self.lock:
            self.last_seen = time.monotonic()
            state = self.k.snapshot()
            actions = self.k.actions('human')
            focus, interaction, cell, hint = self._interaction_view(actions)
            for who, chef in self.k.chefs.items():
                j = chef.job
                total = self.totals.setdefault(j.id, j.travel+j.work) if j else 0
                state['chefs'][who]['progress'] = max(0, min(1, 1-(j.travel+j.work)/total)) if total else 0
            events = [{'t': e['t'], 'message': e['message'], 'kind': e.get('kind')} for e in self.k.events
                      if e.get('kind') not in ('action_start', 'action_done')]
            events += self.notes
            events = sorted(events, key=lambda e:e['t'])[-10:]
            return {'game_id': self.game_id, 'phase': self.phase, 'speed': self.speed,
                    'communication': self.communication_state(),
                    'interaction': asdict(interaction) if interaction else None,
                    'interaction_focus': focus,
                    'interaction_cell': cell,
                    'interaction_hint': hint,
                    'kitchen': state, 'actions': [asdict(a) for a in actions],
                    'boards': self.k.boards, 'pots': self.k.pots, 'events': events,
                    'ai': {'connected': bool(self.ai and self.ai.successes),
                           'thinking': bool(self.ai and self.ai.inflight),
                           'error': self.ai_error, 'calls': self.ai.calls if self.ai else 0,
                           'latency': self.ai.last_latency if self.ai else None},
                    'result': self.k.result() if self.phase == 'ended' else None,
                    'aborted': self.k.aborted,
                    'won': self.k.won() and not self.k.aborted if self.phase == 'ended' else False,
                    'levels': available_levels(),
                    'rules': {key:self.c[key] for key in ('chop_seconds', 'cook_seconds', 'burn_after_ready',
                              'fire_after_burn', 'order_patience', 'round_seconds', 'order_count')}}

    def _interaction_view(self, actions):
        # Space-key focus is a position-dependent convenience: if it fails, the page still
        # gets the kitchen state (instead of an empty response that reads as a disconnect).
        k = self.k
        try:
            focus = k.interaction_target('human',self.interaction_focus) if hasattr(k,'interaction_target') else None
            interaction = k.quick_interaction('human',actions,preferred=focus) if hasattr(k,'quick_interaction') else None
            cell = k.interaction_cell('human',focus) if hasattr(k,'interaction_cell') else None
            hint = k.interaction_hint('human',focus) if hasattr(k,'interaction_hint') and not interaction else None
            return focus, interaction, cell, hint
        except Exception as exc:
            if self.journal and not getattr(self, '_interaction_error_logged', False):
                self._interaction_error_logged = True
                try:
                    self.journal('engine_error', {'t': k.time, 'where': 'interaction_view', 'error': f'{type(exc).__name__}: {exc}',
                                                  'position': k.positions.get('human'), 'facing': getattr(k,'facing',{}).get('human'),
                                                  'trace': traceback.format_exc(limit=8)})
                except Exception:
                    pass
            return None, None, None, None

    def command(self, path, body):
        with self.lock:
            if body.get('game_id') != self.game_id:
                return 409, {'error': '这是上一局的操作，请刷新页面。'}
            if path == '/api/move':
                return self._move(body)
            request_id = body.get('request_id')
            if not isinstance(request_id, str) or not (1 <= len(request_id) <= 100):
                return 400, {'error': '请求无效，请重试。'}
            if request_id in self.receipts:
                return self.receipts[request_id]
            response = self._command(path, body)
            self.receipts[request_id] = response
            while len(self.receipts) > 128:
                self.receipts.popitem(last=False)
            return response

    def _move(self, body):
        if not hasattr(self.k,'set_manual'):
            return 400, {'error':'当前厨房不支持方向移动'}
        dx, dy, seq = body.get('dx'), body.get('dy'), body.get('seq')
        if (('sprint' in body and type(body['sprint']) is not bool) or not isinstance(seq,int) or isinstance(seq,bool) or seq < 0
                or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1 for v in (dx,dy))):
            return 400, {'error':'移动输入无效'}
        if seq <= self.move_seq:
            return 200, {'ok':True,'ignored':True}
        self.move_seq = seq
        if self.phase != 'running':
            self.k.set_manual('human',0,0)
            return (409, {'error':'厨房未营业'}) if dx or dy else (200,{'ok':True})
        if dx or dy:self.interaction_focus=None
        before = self.k.manual['human']
        self.k.set_manual('human',dx,dy)
        sprint_applied=self.k.sprint('human') if body.get('sprint') is True else False
        if body.get('sprint') is True and self.journal:
            self.journal('human_input',{'t':self.k.time,'source':'keyboard','sprint':True,'applied':sprint_applied,'seq':seq})
        self.move_until = time.monotonic()+.5
        if before != self.k.manual['human'] and self.journal:
            self.journal('human_input',{'t':self.k.time,'source':'keyboard','direction':[dx,dy],
                                      'seq':seq,'applied':True})
        self._events()
        return 200, {'ok':True}

    def communication_state(self):
        preference=next((m for m in reversed(self.player_messages) if m['kind']=='preference'),None)
        last=self.player_messages[-1] if self.player_messages else None
        remaining=max(0.,5-(time.monotonic()-self.last_player_message_at)) if self.last_player_message_at is not None else 0.
        return {'preference': preference['code'] if preference else None,
                'cooldown_remaining': round(remaining,2), 'last_message': deepcopy(last),
                'allowed': self.phase in ('running','paused') and not self.k.ended}

    def _communicate(self, body):
        if self.phase not in ('running','paused') or self.k.ended or self.journal is None:
            return 409, {'error':'请在对局开始后、结束前发送沟通。'}
        code=body.get('code')
        if not isinstance(code,str) or code not in PLAYER_MESSAGES:
            return 400, {'error':'未知的沟通选项。'}
        now=time.monotonic()
        if self.last_player_message_at is not None and now-self.last_player_message_at < 5:
            return 429, {'error':'沟通冷却中，请稍后再发。','communication':self.communication_state()}
        chef=self.k.chefs['jeff'];job=chef.job
        message={'id':'M'+str(len(self.player_messages)+1),'round_id':self.game_id,
                 'kind':'correction' if code=='mistake' else 'preference',
                 'code':code,'text':PLAYER_MESSAGES[code],
                 'game_time':round(self.k.time,3),'wall_time':datetime.now().astimezone().isoformat(),
                 'first_request_id':None,
                 'context':{'ai_request_id':self.ai.calls,'current_action':job.action.key if job else None,
                            'last_choice':self.ai.recent_decisions[-1]['choice'] if self.ai.recent_decisions else None,
                            'holding_id':chef.hand.id if chef.hand else None,
                            'holding_stage':chef.hand.stage if chef.hand else None,
                            'event_index':len(self.k.events)}}
        try:
            self.journal('player_message',{'t':message['game_time'],'message':deepcopy(message),
                                           'state':self.k.snapshot()})
        except OSError:return 503, {'error':'沟通未保存，请重试。'}
        self.player_messages.append(message);self.last_player_message_at=now
        self.ai.player_messages=self.player_messages
        # Refresh at the normal decision cadence. Keep jobs and in-flight requests intact.
        self.ai.last_revision=-1
        return 200, {'ok':True,'communication':self.communication_state()}

    def _bookmark(self):
        # Annotation only: never emit a kitchen event, revise state, or wake/invalidate AI.
        if self.phase != 'running' or self.k.ended or self.journal is None:
            return 409, {'error': '只能在营业中标记片段。'}
        now = time.monotonic()
        mark = {'game_time': round(self.k.time, 3),
                'wall_time': datetime.now().astimezone().isoformat(),
                'event_index': len(self.k.events),
                'ai_request_id': self.ai.calls if self.ai else 0}
        merged = bool(self.bookmarks and self.last_bookmark_at is not None
                      and 0 <= now-self.last_bookmark_at <= 5)
        interval = deepcopy(self.bookmarks[-1]) if merged else {
            'id': 'B'+str(len(self.bookmarks)+1), 'round_id': self.game_id,
            'start_game_time': mark['game_time'], 'start_wall_time': mark['wall_time'],
            'press_count': 0, 'marks': []}
        interval.update(end_game_time=mark['game_time'], end_wall_time=mark['wall_time'])
        interval['press_count'] += 1
        interval['marks'].append(mark)
        try:
            self.journal('bookmark', {'t': mark['game_time'], 'schema_version': 1,
                                     'operation': 'extend' if merged else 'create',
                                     'bookmark': deepcopy(interval)})
        except OSError:
            return 503, {'error': '标记未保存，请重试。'}
        if merged:self.bookmarks[-1] = interval
        else:self.bookmarks.append(interval)
        self.last_bookmark_at = now
        return 200, {'ok': True, 'merged': merged, 'bookmark': deepcopy(interval)}

    def _command(self, path, body):
        if path == '/api/bookmark':return self._bookmark()
        if path == '/api/communicate':return self._communicate(body)
        if path == '/api/level':
            if self.phase not in ('ready','ended') or not hasattr(self.k,'nav'):
                return 409,{'error':'Choose a level before starting or after the round ends.'}
            from levels import level_config, level_id
            level=body.get('level')
            try:level_id(level)
            except ValueError:return 400,{'error':'Unknown level.'}
            self._finish(aborted=self.phase!='ended')
            self.c=level_config({**self.base_config, **{key:self.c[key] for key in ('ai_max_calls','ai_max_response_age','model')}},level)
            return self._command('/api/reset',{})
        if path == '/api/restart':
            if self.phase not in ('paused','ended'):
                return 409, {'error': '请先暂停，再重新开局。'}
            speed = self.speed
            result = self._command('/api/reset', {})
            if result[0] != 200:return result
            # Dispatch through subclass hooks so credentials, memory and budgets
            # follow exactly the same initialization as a normal start.
            return self._command('/api/start', {'speed':speed})
        if path == '/api/start':
            if self.phase != 'ready':
                return 409, {'error': '本局已经开始。'}
            speed = body.get('speed', .75)
            if isinstance(speed, bool) or speed not in (.5, .75, 1):
                return 400, {'error': '请选择页面中的游戏节奏。'}
            try:
                client = self.client_factory(self.c)
            except (RuntimeError, OSError, ValueError):
                return 503, {'error': '没有读到可用的本地 Jev 配置，请检查 .env。厨房尚未开始计时。'}
            self.speed = speed
            self.journal = SessionLog(self, self.journal_factory(self.log_prefix+'-'+self.game_id[:8]),
                                      keep_payloads=self.bundle_root is not None, deployment_mode=self.deployment_mode)
            self.session_log = self.journal
            self.journal('start', {'config':self.c, 'config_hash':self.k.config_hash, 'speed':self.speed, 'state':self.k.snapshot()})
            self.ai = DecisionLoop(self.k, client, self.journal, self.note)
            self.phase = 'running'
            self.last_tick = self.last_seen = time.monotonic()
            return 200, {'ok': True}
        if path == '/api/pause':
            if self.phase == 'running':
                self.phase = 'paused'
                if hasattr(self.k,'set_manual'): self.k.set_manual('human',0,0)
                self.ai.invalidate()
                reason = '离开页面，厨房已自动暂停。' if body.get('reason') == 'hidden' else '厨房已暂停，你和 Jeff 的动作、锅与订单倒计时都已停下。'
                self.note(reason)
                self.journal('pause', {'t':self.k.time, 'reason':body.get('reason','manual')})
            return 200, {'ok': True}
        if path == '/api/resume':
            if self.faulted:
                return 409, {'error': '本局运行出现异常，请重新开局。'}
            if self.phase != 'paused':
                return 409, {'error': '当前无需继续。'}
            self.phase = 'running'
            self.last_tick = self.last_seen = time.monotonic()
            self.ai.invalidate()
            self.journal('resume', {'t':self.k.time})
            return 200, {'ok': True}
        if path == '/api/end':
            if self.phase=='ended':return 200,{'ok':True}
            if self.phase not in ('running','paused'):
                return 409,{'error':'当前没有进行中的对局。'}
            self.k.abort()
            self.phase='ended'
            self._finish(aborted=True)
            return 200,{'ok':True}
        if path == '/api/reset':
            if self.phase == 'running':
                return 409, {'error': '先暂停，再重新开局。'}
            self._finish(aborted=self.phase != 'ended')
            # Unconfigured seeds are drawn again when the new round is frozen.
            self.k = self.kitchen_factory(self.c)
            self.game_backlog = 0.
            self.ticks = 0
            self.c = self.k.c
            self.move_seq = -1
            self.move_until = 0.
            self.interaction_focus=None
            self.player_messages=[]
            self.last_player_message_at=None
            self.bookmarks=[]
            self.last_bookmark_at=None
            self.game_id = uuid.uuid4().hex
            self.phase = 'ready'
            self.faulted = False
            self.ai = None
            self.cursor = 0
            self.notes = []
            self.ai_error = None
            self.totals = {}
            return 200, {'ok': True}
        if path == '/api/select':
            if self.phase!='running' or not hasattr(self.k,'quick_interaction'):
                return 409,{'error':'当前不能操作'}
            target=body.get('target')
            if not isinstance(target,str):return 400,{'error':'目标无效'}
            actions=self.k.actions('human')
            if target.startswith('item:'):
                item=self.k.ground.get(target[5:])
                if not item:return 409,{'error':'地上物品已变化，请重新选择'}
                destination=item.location;focus=target
            elif target in self.k.equipment:
                destination=target;focus=target
            else:
                destination=target;focus=None
                if not any(a.kind=='go' and a.target==target for a in actions) and target!=self.k.chefs['human'].location:
                    return 400,{'error':'目标无效'}
            action=next((a for a in actions if a.kind=='go' and a.target==destination),None)
            if action:
                result=self._command('/api/action',{'action':action.key,'expected':list(action.expected)})
                if result[0]!=200:return result
            self.interaction_focus=focus
            return 200,{'ok':True}
        if path == '/api/interact':
            if self.phase != 'running' or not hasattr(self.k, 'quick_interaction'):
                return 409, {'error': '当前不能操作'}
            hand = self.k.chefs['human'].hand
            if (hand.id if hand else None) != body.get('expected_item'):
                return 409, {'error': '手中物品已变化，请重新按空格'}
            focus=self.k.interaction_target('human',self.interaction_focus)
            action = self.k.quick_interaction('human',preferred=focus)
            if not action:
                message=self.k.interaction_hint('human',focus) or '请靠近工位或物品，再按空格操作'
                self.journal('human_input',{'t':self.k.time,'source':'browser','action':'interact','applied':False,'message':message})
                return 409, {'error': message}
            return self._command('/api/action', {'action': action.key, 'expected': list(action.expected)})
        if path == '/api/throw':
            if self.phase != 'running' or not hasattr(self.k,'throw_action'):
                return 409, {'error':'当前不能抛掷'}
            target = body.get('target')
            if (not isinstance(target,list) or len(target)!=2
                    or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>10000 for v in target)):
                return 400, {'error':'抛掷坐标无效'}
            hand = self.k.chefs['human'].hand
            if not hand or hand.id != body.get('expected_item'):
                return 409, {'error':'手中物品已变化'}
            action = self.k.throw_action('human',target)
            if not action:
                return 409, {'error':'没有可用落点，或此物品不能抛掷'}
            ok,message = self.k.start('human',action)
            self.journal('human_input',{'t':self.k.time,'source':'browser','action':action.key,
                                      'target':target,'landing':action.target,'applied':ok,'message':message})
            self._events()
            return (200,{'ok':True}) if ok else (409,{'error':message})
        if path == '/api/action':
            if self.phase != 'running':
                return 409, {'error': '先开始或继续本局，再点击动作。'}
            expected = body.get('expected')
            if not isinstance(expected, list) or len(expected) > 5:
                return 400, {'error': '动作信息无效，请重试。'}
            action = next((a for a in self.k.actions('human') if a.key == body.get('action') and list(a.expected) == expected), None)
            if not action:
                return 409, {'error': '刚才的食材或工位状态变了，请按更新后的按钮操作。'}
            ok, message = self.k.start('human', action)
            if ok and action.kind=='go' and hasattr(self.k,'equipment'):
                self.interaction_focus=action.target if action.target in self.k.equipment else next(('item:'+key for key,item in self.k.ground.items() if item.location==action.target),None)
            self.journal('human_input', {'t':self.k.time, 'source':'browser', 'action':action.key, 'applied':ok, 'message':message})
            if self.k.chefs['human'].job:
                j=self.k.chefs['human'].job
                self.totals.setdefault(j.id,j.travel+j.work)
            self._events()
            return (200, {'ok':True, 'message':action.label}) if ok else (409, {'error':message})
        return 404, {'error':'没有这个操作。'}


class Handler(BaseHTTPRequestHandler):
    web_root = ROOT/'web'
    static_files = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
    def log_message(self, format, *args):
        pass

    def reply(self, status, data, content_type='application/json; charset=utf-8'):
        raw = json.dumps(data,ensure_ascii=False).encode() if isinstance(data,dict) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def local_request(self):
        port=self.server.server_port
        hosts=(f'127.0.0.1:{port}',f'localhost:{port}')
        if self.headers.get('Host') not in hosts:
            return False
        origin=self.headers.get('Origin')
        return not origin or origin in ('http://'+host for host in hosts)

    def do_GET(self):
        if not self.local_request():
            return self.reply(403,{'error':'仅允许本机页面访问。'})
        path=urlparse(self.path).path
        if path=='/api/state':
            return self.reply(200,self.server.game.public_state())
        files=self.static_files
        if path not in files:
            return self.reply(404,{'error':'页面不存在。'})
        file=self.web_root/files[path]
        mime=mimetypes.guess_type(str(file))[0] or 'text/plain'
        self.reply(200,file.read_bytes(),mime+'; charset=utf-8')

    def do_POST(self):
        if not self.local_request() or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return self.reply(403,{'error':'仅允许本机页面操作。'})
        if not self.headers.get('Content-Type','').startswith('application/json'):
            return self.reply(415,{'error':'需要 JSON 请求。'})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=8192:
                raise ValueError()
            body=json.loads(self.rfile.read(n))
            if not isinstance(body,dict):
                raise ValueError()
        except (ValueError, json.JSONDecodeError):
            return self.reply(400,{'error':'请求格式无效。'})
        status,data=self.server.game.command(urlparse(self.path).path,body)
        self.reply(status,data)


def main():
    p=argparse.ArgumentParser(description='打开可点击的本地文字厨房')
    p.add_argument('--port',type=int,default=8767)
    p.add_argument('--open',action='store_true')
    args=p.parse_args()
    game=GameSession()
    try:
        server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError as e:
        raise SystemExit(f'无法启动本地厨房：{e}')
    server.game=game
    threading.Thread(target=game.run,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'文字厨房已就绪：{url}\n点击页面中的「开始一起做菜」才会计时和调用 Jev。Ctrl+C 关闭服务。',flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        game.close()
        server.server_close()


if __name__=='__main__':
    main()
