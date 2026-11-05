"""Real TypeSafe HTTP Choice client and bounded asynchronous decision scheduling."""
from __future__ import annotations
from model_status import ModelWait
from copy import deepcopy
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from kitchen import ROOT
from model_language import english_data
# Jeff's input is assembled in harness.py; these names stay importable from here.
from harness import (AGENT_RULES_VERSION, CONTINUITY_RULE, NO_MEMORY, PLAYER_COMMUNICATION_RULE,  # noqa: F401
                     STATE_WORDS, model_kitchen, objective_text, score_text)
import harness
import one_press

ENDPOINT = "https://api.typesafe.ai/v1/systemone"


def load_key():
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if key:
        return key
    paths = [ROOT / ".env"]
    local = ROOT / ".local.json"
    if local.exists():
        setting = json.loads(local.read_text())
        if setting.get("env_file"):
            paths.append(Path(setting["env_file"]).expanduser())
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            if line.strip().startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
                if key:
                    return key
    raise RuntimeError("未找到 TYPESAFE_API_KEY。请在本地 .env 中配置，不要把密钥发到聊天。")


def http_error_detail(error, key):
    """The provider's short error message (never headers), with the key redacted, for diagnosing a refused request."""
    try:
        body = json.loads(error.read(4096) or b"{}")
        detail = body.get("error", body) if isinstance(body, dict) else {}
        message = detail.get("message") if isinstance(detail, dict) else detail
        message = str(message or "").replace(key, "***").strip()[:160] if key else ""
    except (ValueError, OSError, AttributeError):
        message = ""
    return f"：{message}" if message else ""


class JevClient:
    # Any systemone-style decision API: state + questions in, option probabilities out.
    endpoint, vendor = ENDPOINT, "TypeSafe"
    # The plain kitchen; whitebox_server.SpatialJevClient (every listed level) sets spatial.
    spatial = False

    def __init__(self, config, key=None):
        self.key = key or load_key()
        self.c = config

    def payload(self, state, actions):
        return harness.payload(state, actions, self.c, spatial=self.spatial)


    def ask(self, payload):
        payload = english_data(payload)
        start = time.monotonic()
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload, ensure_ascii=False).encode(),
                                         headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.c["ai_timeout_seconds"]) as r:
                result = json.load(r)
        except urllib.error.HTTPError as e:
            # Only the status and the provider's short message; no headers, request or key.
            raise RuntimeError(f"{self.vendor} HTTP {e.code}{http_error_detail(e, self.key)}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError(f"{self.vendor} 网络连接失败或超时") from None
        answer = result.get("answers", {}).get("next_action", {})
        if answer.get("type") != "choice" or answer.get("choice") not in payload["questions"]["next_action"]["criteria"]:
            raise RuntimeError(f"{self.vendor} 返回了不符合候选集的选择")
        sprint_answer=result.get('answers',{}).get('sprint',{})
        if 'sprint' in payload['questions'] and (sprint_answer.get('type')!='choice' or sprint_answer.get('choice') not in ('yes','no')):
            raise RuntimeError('Invalid sprint decision')
        # A missing or unknown plan answer only leaves Jeff without a plan (or keeps it); the action stands.
        plan = harness.choice_answer(harness.choices(result.get('answers'), harness.choice_questions(payload)), payload)
        return {"sprint_answer":sprint_answer, "sprint":sprint_answer.get('choice')=='yes', "choice": answer["choice"], "confidence": answer.get("confidence"),
                "probabilities": answer.get("probabilities", {}), "model": result.get("model"),
                "usage": result.get("usage", {}), "latency": time.monotonic()-start, **plan}


def compose_payload(client, kitchen, state, actions, recent_decisions, communication, memory=NO_MEMORY, plan=None, one_press=None):
    """Jeff's request from the kitchen and the few parts it cannot derive; research replay rebuilds it here too.

    one_press is the round's one-press switches (one_press.flags), or None: the options are added to the
    listed actions here, unless the caller already did."""
    if one_press:
        import one_press as presses
        keys = {a.key for a in actions}
        actions = list(actions) + [a for a in presses.options(kitchen, 'jeff', actions, one_press) if a.key not in keys]
    return harness.compose(client.payload(state, actions), kitchen, recent_decisions, communication, memory, plan, one_press)


class DecisionLoop:
    def __init__(self, kitchen, client, log, notify):
        self.k = kitchen
        self.client = client
        self.log = log
        self.notify = notify
        self.q = queue.Queue()
        self.inflight = False
        self.last_request = -1e9
        self.last_revision = -1
        self.next_allowed = 0.0
        self.last_urgency = None
        self.last_job = None
        self.failures = 0
        self.calls = 0
        self.successes = 0
        self.error_count = 0
        self.stale_count = 0
        self.rejected_count = 0
        self.tokens = {"input_tokens": 0, "output_tokens": 0}
        self.epoch = 0
        self.closed = False
        self.last_choice = "尚未请求"
        self.last_latency = None
        self.actual_model = None
        self.event_cursor = 0
        self.last_wait_notice = -1e9
        self.recent_decisions = []
        self.service_wait=None
        self.deferred_count=0
        self.call_limit = self.k.c.get('ai_max_calls', 200)
        self.budget_notified = False
        # Jeff's plan (harness.Plan) when the round's plan switch is on.
        self.plan = None
        self.plan_work = {}         # action id -> the work item it does, for Jeff's started actions
        self.plan_cursor = 0        # engine events already checked for Jeff's finished actions
        self.plan_due = False       # the plan ended and Jeff has not been asked for a new one since
        # ai_ask_on_step_end: when Jeff's step ends, ask at once instead of waiting out ai_min_interval,
        # and do not start a request his current step will outlast (its reply would be discarded as stale
        # and, while on its way, would hold back the question about his next step).
        self.ask_on_step_end = bool(self.k.c.get('ai_ask_on_step_end', False))
        self.game_speed = 1.0       # game seconds per wall second; the session sets the round's speed
        self.watched_job = None     # Jeff's job at the previous poll
        self.step_ended = False     # his step ended and he has not been asked since
        self.reply_times = []       # recent reply times (wall seconds) of answered requests
        # One-press options (one_press.py) when a round's switch is on: the flags, the chain under way, and the
        # engine events already checked for its current step.
        self.one_press = None
        self.chain = None           # {'key', 'steps': [(kinds, target)], 'job': action id of the step under way, 'done'}
        self.chain_cursor = 0

    def reply_time(self):
        """The typical recent reply time, or None before any answer."""
        recent = sorted(self.reply_times[-5:])
        return recent[len(recent)//2] if recent else None

    def outlasts_reply(self, job):
        """Whether Jeff's current step will end before a request sent now could be answered."""
        expected = self.reply_time()
        if expected is None:
            return False
        remaining = max(0.0, job.travel) + max(0.0, job.work)
        return remaining / max(self.game_speed, 1e-6) < expected

    def start_chain(self, decision, put_where):
        """Start a one-press choice: its first step now (the put put_where chose, or the first step itself with empty
        hands); the rest follow as each step finishes. Returns applied, message and how it started."""
        steps = one_press.steps(decision, self.k)
        fallback = False
        if self.k.chefs['jeff'].hand is not None:
            first, fallback = one_press.place(self.k.actions('jeff'), put_where)
        else:
            first, steps = one_press.find(self.k, 'jeff', steps[0]), steps[1:]
        if first is None:
            return False, '一键操作的第一步现在做不了', {'first': None, 'fallback': fallback}
        applied, message = self.k.start('jeff', first)
        self.end_chain('replaced')
        job = self.k.chefs['jeff'].job
        if applied and job is not None:
            self.chain = {'key': decision.key, 'steps': list(steps), 'job': job.id, 'done': False}
            self.chain_cursor = len(self.k.events)
        return applied, message, {'first': first.key, 'fallback': fallback}

    def end_chain(self, reason):
        """Drop the chain under way, if any, and log why (finished, replaced, interrupted, a step not possible)."""
        if self.chain is not None:
            self.log('one_press_end', {'choice': self.chain['key'], 'reason': reason, 'steps_left': len(self.chain['steps']),
                                       't': round(self.k.time, 3)})
            self.chain = None

    def advance_chain(self):
        """After the chain's step finishes, start its next step at once; a step the engine does not list ends it."""
        if self.chain is None:
            return
        for event in self.k.events[self.chain_cursor:]:
            if event.get('actor') != 'jeff' or event.get('action_id') != self.chain['job']:
                continue
            if event.get('kind') == 'action_done':
                self.chain['done'] = True
            elif event.get('kind') in ('interrupted', 'knocked'):
                self.end_chain('interrupted')
                break
        self.chain_cursor = len(self.k.events)
        if self.chain is None or not self.chain['done'] or self.k.chefs['jeff'].job is not None:
            return
        if not self.chain['steps']:
            self.end_chain('finished')
            return
        action = one_press.find(self.k, 'jeff', self.chain['steps'].pop(0))
        applied = action is not None and self.k.start('jeff', action)[0]
        job = self.k.chefs['jeff'].job
        if not applied or job is None:
            self.end_chain('step_not_possible')
            return
        self.chain.update(job=job.id, done=False)
        self.chain_cursor = len(self.k.events)

    def invalidate(self):
        self.epoch += 1
        self.last_revision = -1

    def urgency(self):
        k = self.k
        # Bucket changes trigger once when crossing each threshold, not each tick.
        def band(t):
            return sum(t <= x for x in (15, 8, 3, 0))
        return tuple((o["id"], band(o["deadline"]-k.time)) for o in k.orders if o["status"] == "pending") + tuple(
            (key, band(k.rules.heat_thresholds(s.food.ingredient)[1]-s.food.heated),
             band(k.rules.heat_thresholds(s.food.ingredient)[2]-s.food.heated))
            for key, s in k.stations.items() if key in k.pots and s.food)

    def poll(self, enabled=True):
        now = time.monotonic()
        try:
            packet = self.q.get_nowait()
        except queue.Empty:
            packet = None
        if packet:
            self.inflight = False
            context, result, error = packet
            if isinstance(error,ModelWait):
                self.error_count+=1
                self.deferred_count+=int(error.deferred)
                self.failures=0
                self.next_allowed=float('inf') if error.blocked else max(now,error.retry_deadline)
                retry=None if error.blocked else max(0,self.next_allowed-now)
                self.service_wait={'diagnostic':error.diagnostic,'message':str(error),'blocked':error.blocked}
                self.log('ai_error',{'request_id':context['id'],'error':str(error),'retry_in':retry,
                    'server_received_wall_ms':round((context['returned_monotonic']-self.log.monotonic_start)*1000) if 'returned_monotonic' in context and hasattr(self.log,'monotonic_start') else None})
                self.notify(str(error)+('' if error.blocked else f" 约 {retry:.0f} 秒后重试。"))
            elif error:
                self.service_wait=None
                self.failures += 1
                self.error_count += 1
                self.next_allowed = now + min(30, 2 ** min(self.failures, 5))
                self.log("ai_error", {"request_id": context["id"], "error": error, "retry_in": round(self.next_allowed-now,1),
                    "server_received_wall_ms": round((context["returned_monotonic"]-self.log.monotonic_start)*1000) if "returned_monotonic" in context and hasattr(self.log,"monotonic_start") else None})
                self.notify(f"Jeff 请求失败：{error}；{self.next_allowed-now:.0f}s 后重试。无脚本队友代替。")
            else:
                self.successes += 1
                self.service_wait=None
                self.failures = 0
                self.actual_model = result["model"]
                self.last_latency = result["latency"]
                self.reply_times = (self.reply_times + [now-context["sent"]])[-5:]
                for key in self.tokens:
                    self.tokens[key] += result["usage"].get(key, 0)
                decision = context["actions"][result["choice"]]
                chef = self.k.chefs["jeff"]
                current_job = chef.job.id if chef.job else None
                fresh = (not self.closed and enabled and not self.k.ended and context["epoch"] == self.epoch
                         and now-context["sent"] <= self.k.c["ai_max_response_age"]
                         and context["job_id"] == current_job)
                # The work an action does is read from the kitchen as it starts (what is in hand, on the board).
                work = harness.work_item(decision, self.k.snapshot()) if self.plan and fresh and harness.does_work(decision) else None
                pressed = None      # how a one-press choice started: its first step and whether put_where fell back
                if fresh and decision.kind in one_press.KINDS:
                    applied, message, pressed = self.start_chain(decision, result.get(one_press.PUT_WHERE))
                elif fresh:
                    applied, message = self.k.start("jeff", decision)
                    if applied and decision.kind != 'continue':
                        self.end_chain('replaced')
                else:
                    applied, message = False, "回复已过期、任务已变化或游戏已暂停"
                if applied and work and self.k.chefs["jeff"].job:
                    self.plan_work[self.k.chefs["jeff"].job.id] = work
                sprint_applied=bool(applied and result.get('sprint') is True and hasattr(self.k,'sprint') and self.k.sprint('jeff'))
                # A plan answer counts like the action: only from a fresh reply, and only for the questions asked.
                plan_set = plan_dropped = False
                if self.plan and fresh:
                    plan_set = self.plan.accept(result.get('plan'), self.k.time, context.get('plan_offered'), context.get('preference'))
                    plan_dropped = self.plan.keep(result.get('plan'))
                    self.plan_due = self.plan_due or plan_dropped
                if not fresh:self.stale_count += 1
                elif not applied:self.rejected_count += 1
                chef_job = self.k.chefs["jeff"].job
                self.log("ai_response", {"request_id": context["id"], **result, "applied": applied, "execution": message, "sprint_applied":sprint_applied,
                                         "fresh": fresh, **({"plan_set": plan_set, "plan_dropped": plan_dropped} if self.plan else {}),
                                         **({"one_press": pressed} if pressed else {}),
                                         "server_received_wall_ms": round((context["returned_monotonic"]-self.log.monotonic_start)*1000) if "returned_monotonic" in context and hasattr(self.log,"monotonic_start") else None,
                                         "server_transport_started_wall_ms": round((context["transport_started_monotonic"]-self.log.monotonic_start)*1000) if "transport_started_monotonic" in context and hasattr(self.log,"monotonic_start") else None,
                                         "action_id": chef_job.id if applied and chef_job and decision.kind not in ("continue", "wait") else None,
                                         "accepted_engine_seq": self.k.event_seq, "current_state": self.k.snapshot()})
                self.last_choice = result["choice"] + ("" if applied else "（未执行）")
                self.recent_decisions.append({"t": round(self.k.time, 2), "choice": result["choice"],
                                              "accepted": applied, "result": message, "sprint_applied":sprint_applied})
                self.recent_decisions = self.recent_decisions[-8:]
                if decision.kind not in ("continue", "wait") or not applied or now-self.last_wait_notice >= 8:
                    self.notify(f"Jeff 选择：{decision.label} | {result['latency']:.2f}s" + ("" if applied else f" | 未执行：{message}"))
                    self.last_wait_notice = now
                if not applied:
                    self.last_revision = -1
        if self.plan:
            # Jeff's finished actions tick his plan; the step that finishes it asks for a new one at once.
            for event in self.k.events[self.plan_cursor:]:
                if event.get('actor') != 'jeff' or event.get('action_id') not in self.plan_work:
                    continue
                if event.get('kind') == 'action_done':
                    self.plan_due = self.plan.tick(self.plan_work.pop(event['action_id'])) or self.plan_due
                elif event.get('kind') == 'interrupted':
                    self.plan_work.pop(event['action_id'])
            self.plan_cursor = len(self.k.events)
        # A one-press chain goes on before anything else looks at Jeff's step, so its steps read as one.
        self.advance_chain()
        job = self.k.chefs["jeff"].job
        if job is None and self.watched_job is not None:
            self.step_ended = True      # done, interrupted or knocked off: he now needs his next step
        elif job is not None:
            self.step_ended = False
        self.watched_job = job.id if job else None
        if not enabled or self.closed or self.k.ended or self.inflight or now < self.next_allowed:
            return
        if self.calls >= self.call_limit:
            if not self.budget_notified:
                self.budget_notified = True
                self.log('call_limit', {'calls': self.calls, 'limit': self.call_limit})
                self.notify('本局 AI 调用已达上限，不再发起请求；已有动作继续，玩家仍可操作。')
            return
        age = now-self.last_request
        step_end = self.ask_on_step_end and self.step_ended
        # A plan that just ended asks for the next one like a finished step does.
        plan_end = self.ask_on_step_end and self.plan_due
        if age < self.k.c["ai_min_interval"] and not (step_end or plan_end):
            return
        urgency = self.urgency()
        changed = self.k.revision != self.last_revision
        urgent = urgency != self.last_urgency
        if not (changed or urgent or step_end or self.plan_due or age >= self.k.c["ai_refresh_seconds"]):
            return
        # Rolling intent or a one-press chain: a change of urgency (an order or a pan crossing a countdown band) asks even then.
        rolling_urgent = urgent and ((self.plan is not None and self.plan.mode == 'rolling') or self.chain is not None)
        if self.ask_on_step_end and job is not None and self.outlasts_reply(job) and not rolling_urgent:
            # The answer would come after this step ends and be discarded; ask when it ends instead.
            return
        actions = self.k.actions("jeff")
        if self.one_press:
            actions = actions + one_press.options(self.k, 'jeff', actions, self.one_press)
        state = self.k.snapshot()
        causes = [e["message"] for e in self.k.events[self.event_cursor:]]
        if urgent:
            causes.append("订单或锅的紧急倒计时档位变化")
        if not causes:
            causes = ["定期全局状态刷新"]
        self.event_cursor = len(self.k.events)
        self.calls += 1
        chef = self.k.chefs["jeff"]
        context = {"id": self.calls, "sent": now, "epoch": self.epoch,
                   "job_id": chef.job.id if chef.job else None,
                   "actions": {a.key: a for a in actions}}
        communication = None
        messages=getattr(self,'player_messages',[])
        if messages:
            preference=next((m for m in reversed(messages) if m['kind']=='preference'),None)
            included=messages[-8:]
            if preference and preference not in included:included=[preference]+included
            communication={'current_preference':deepcopy(preference), 'recent_messages':deepcopy(included)}
            for message in included:
                if message['first_request_id'] is None:
                    self.log('player_message_delivery',{'message_id':message['id'],'request_id':self.calls,
                                                        't':round(self.k.time,3),'meaning':'included in request, not proof of understanding'})
                    message['first_request_id']=self.calls
        plan = plan_ended = None
        if self.plan:
            context['preference'] = next((m['id'] for m in reversed(messages) if m['kind'] == 'preference'), None)
            plan_ended = self.plan.check(context['preference'])
            plan = self.plan.input(state)
            context['plan_offered'] = plan['options']
        payload = compose_payload(self.client, self.k, state, actions, self.recent_decisions, communication,
                                  self.cooperation_memory if hasattr(self, 'cooperation_memory') else NO_MEMORY, plan, self.one_press)
        self.log("ai_request", {"request_id": self.calls, "triggers": causes, "observed_state_seq": self.k.event_seq, "payload": payload,
                                **({"jeff_plan": plan, "plan_ended": plan_ended} if plan is not None else {}),
                                **({"one_press": dict(self.one_press)} if self.one_press else {})})
        self.last_request = now
        self.last_revision = self.k.revision
        self.last_urgency = urgency
        self.step_ended = False
        self.plan_due = False
        self.inflight = True
        def work():
            try:
                context['transport_started_monotonic'] = time.monotonic()
                result = self.client.ask(payload)
                context['returned_monotonic'] = time.monotonic()
                self.q.put((context, result, None))
            except ModelWait as exc:
                context['returned_monotonic']=time.monotonic()
                self.q.put((context,None,exc))
            except Exception as exc:
                context['returned_monotonic'] = time.monotonic()
                # Only our sanitized failures should reach logs.
                message = str(exc) if type(exc) is RuntimeError else f"响应读取失败（{type(exc).__name__}）"
                self.q.put((context, None, message))
        threading.Thread(target=work, daemon=True).start()
