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
        plan = {}
        if 'plan_role' in payload['questions']:
            # A missing or unknown plan answer only leaves Jeff without a plan; the action stands.
            plan_answer = result.get('answers', {}).get('plan_role', {})
            offered = payload['questions']['plan_role']['criteria']
            plan = {'plan_answer': plan_answer, 'plan_role': plan_answer.get('choice') if plan_answer.get('type') == 'choice'
                    and plan_answer.get('choice') in offered else None}
        return {"sprint_answer":sprint_answer, "sprint":sprint_answer.get('choice')=='yes', "choice": answer["choice"], "confidence": answer.get("confidence"),
                "probabilities": answer.get("probabilities", {}), "model": result.get("model"),
                "usage": result.get("usage", {}), "latency": time.monotonic()-start, **plan}


def compose_payload(client, kitchen, state, actions, recent_decisions, communication, memory=NO_MEMORY, plan=None):
    """Jeff's request from the kitchen and the few parts it cannot derive; research replay rebuilds it here too."""
    return harness.compose(client.payload(state, actions), kitchen, recent_decisions, communication, memory, plan)


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
                for key in self.tokens:
                    self.tokens[key] += result["usage"].get(key, 0)
                decision = context["actions"][result["choice"]]
                chef = self.k.chefs["jeff"]
                current_job = chef.job.id if chef.job else None
                fresh = (not self.closed and enabled and not self.k.ended and context["epoch"] == self.epoch
                         and now-context["sent"] <= self.k.c["ai_max_response_age"]
                         and context["job_id"] == current_job)
                applied, message = self.k.start("jeff", decision) if fresh else (False, "回复已过期、任务已变化或游戏已暂停")
                sprint_applied=bool(applied and result.get('sprint') is True and hasattr(self.k,'sprint') and self.k.sprint('jeff'))
                # A plan answer counts like the action: only from a fresh reply, and only if plan_role was asked.
                plan_set = bool(self.plan and fresh and self.plan.accept(result.get('plan_role'), self.k.time,
                                                                         context.get('plan_offered'), context.get('preference')))
                if not fresh:self.stale_count += 1
                elif not applied:self.rejected_count += 1
                chef_job = self.k.chefs["jeff"].job
                self.log("ai_response", {"request_id": context["id"], **result, "applied": applied, "execution": message, "sprint_applied":sprint_applied,
                                         "fresh": fresh, **({"plan_set": plan_set} if self.plan else {}),
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
        if not enabled or self.closed or self.k.ended or self.inflight or now < self.next_allowed:
            return
        if self.calls >= self.call_limit:
            if not self.budget_notified:
                self.budget_notified = True
                self.log('call_limit', {'calls': self.calls, 'limit': self.call_limit})
                self.notify('本局 AI 调用已达上限，不再发起请求；已有动作继续，玩家仍可操作。')
            return
        age = now-self.last_request
        if age < self.k.c["ai_min_interval"]:
            return
        urgency = self.urgency()
        changed = self.k.revision != self.last_revision
        urgent = urgency != self.last_urgency
        if not (changed or urgent or age >= self.k.c["ai_refresh_seconds"]):
            return
        actions = self.k.actions("jeff")
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
            plan_ended = self.plan.check(self.k.time, state, actions, context['preference'])
            plan = self.plan.input(state)
            context['plan_offered'] = plan['options']
        payload = compose_payload(self.client, self.k, state, actions, self.recent_decisions, communication,
                                  self.cooperation_memory if hasattr(self, 'cooperation_memory') else NO_MEMORY, plan)
        self.log("ai_request", {"request_id": self.calls, "triggers": causes, "observed_state_seq": self.k.event_seq, "payload": payload,
                                **({"jeff_plan": plan, "plan_ended": plan_ended} if plan is not None else {})})
        self.last_request = now
        self.last_revision = self.k.revision
        self.last_urgency = urgency
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
