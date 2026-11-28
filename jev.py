"""Real TypeSafe HTTP Choice client and bounded asynchronous decision scheduling."""
from __future__ import annotations
from model_status import ModelWait
from copy import deepcopy
from dataclasses import replace
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from kitchen import ROOT, Kitchen
from model_language import english_data
# Jeff's input is assembled in harness.py; these names stay importable from here.
from harness import (AGENT_RULES_VERSION, CONTINUITY_RULE, NO_MEMORY, PLAYER_COMMUNICATION_RULE,  # noqa: F401
                     STATE_WORDS, model_kitchen, objective_text, score_text)
import harness
import one_press
import undo_note
import environment
import ask_ahead
import engine_english
import servability
import joint_plan

ENDPOINT = "https://api.typesafe.ai/v1/systemone"


def load_key():
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if key:
        return key
    paths = [ROOT / ".env"]
    local = ROOT / ".local.json"
    if local.exists():
        setting = json.loads(local.read_text(encoding="utf-8"))
        if setting.get("env_file"):
            paths.append(Path(setting["env_file"]).expanduser())
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
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

    timeout = None              # seconds one decision may take; None: the config's ai_timeout_seconds

    def __init__(self, config, key=None):
        self.key = key or load_key()
        self.c = config

    def payload(self, state, actions):
        return harness.payload(state, actions, self.c, spatial=self.spatial)


    def key_headers(self):
        """The key as Authorization: Bearer (systemone); a service that wants another header overrides this."""
        return {"Authorization": "Bearer " + self.key} if self.key else {}

    def ask(self, payload):
        payload = english_data(harness.for_model(payload))
        start = time.monotonic()
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload, ensure_ascii=False).encode(),
                                         headers={**self.key_headers(), "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout or self.c["ai_timeout_seconds"]) as r:
                result = json.load(r)
        except urllib.error.HTTPError as e:
            # Only the status and the provider's short message; no headers, request or key.
            raise RuntimeError(f"{self.vendor} HTTP {e.code}{http_error_detail(e, self.key)}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError(f"{self.vendor} 网络连接失败或超时") from None
        answer = result.get("answers", {}).get("next_action", {})
        if answer.get("type") == "refusal":
            raise RuntimeError(f"{self.vendor} 拒绝回答这一题")
        if answer.get("type") != "choice" or answer.get("choice") not in payload["questions"]["next_action"]["criteria"]:
            raise RuntimeError(f"{self.vendor} 返回了不符合候选集的选择")
        sprint_answer=result.get('answers',{}).get('sprint',{})
        if 'sprint' in payload['questions'] and (sprint_answer.get('type')!='choice' or sprint_answer.get('choice') not in ('yes','no')):
            raise RuntimeError('Invalid sprint decision')
        # A missing or unknown put_where answer only leaves the one-press choice to its default place; the action stands.
        extra = harness.choice_answer(harness.choices(result.get('answers'), harness.choice_questions(payload)), payload)
        return {"sprint_answer":sprint_answer, "sprint":sprint_answer.get('choice')=='yes', "choice": answer["choice"], "confidence": answer.get("confidence"),
                "probabilities": answer.get("probabilities", {}), "model": result.get("model"),
                "usage": result.get("usage", {}), "latency": time.monotonic()-start, **extra}


def compose_payload(client, kitchen, state, actions, recent_decisions, communication, memory=NO_MEMORY, one_press=None,
                    undo=None, reach=False, names=False, links=False, split=False, burn=False,
                    serve_note=False, steps=False, clear=False, walk=False,
                    english=False, plate=False, parts=None, go=False, work=None, defer=False,
                    joint=None, is_ahead=False):
    """Jeff's request from the kitchen and the few parts it cannot derive; research replay rebuilds it here too.

    one_press is the round's one-press switches (one_press.flags), or None: the options are added to the
    listed actions here, unless the caller already did.
    links is whether the option_links switch is on (links.py): the table is computed here, from this kitchen and
    these actions, after the request is composed; 'partner' adds the other chef's side (option_links_partner).
    split is whether the split_floor switch is on (split_floor.py), burn whether burn_note is (burn_note.py),
    serve_note whether option_notes is (option_notes.py),
    steps whether step_check is (step_check.py), clear whether clear_names is (clear_names.py; it runs again after
    the links table, which it may name in), walk whether walk_note is (walk_note.py: each option's walk), english
    whether engine_english is (engine_english.py: the engine's own English where the catalog garbles it), plate
    whether plate_names is (plate_names.py: a plating option says what the plate there holds). parts is
    request_parts.finish's switches (request_parts.parts), or None: they run last, after the links table. go whether
    go_note is (go_note.py: a "go X" option says when nothing there takes what Jeff holds). work is work_notes.flags
    (own_chain, plate_result, board_taken: facts on options about the work they lead to), or None. joint is the
    joint_plan state snapshot when that trial is on, or None.

    defer: return (payload, actions) once the request is translated (harness.compose), before the notes that fork the
    kitchen for each option; finish_payload then adds them in this same order (the decision loop does that in its
    links thread, so the game loop does not stand still while they are worked out)."""
    with engine_english.writing(english):
        return _compose(client, kitchen, state, actions, recent_decisions, communication, memory, one_press,
                        undo, reach, names, links, split, burn, serve_note, steps, clear, walk, plate, parts, go, work,
                        defer, joint, is_ahead)


def _compose(client, kitchen, state, actions, recent_decisions, communication, memory, one_press,
             undo, reach, names, links, split, burn, serve_note, steps, clear, walk, plate, parts, go=False, work=None,
             defer=False, joint=None, is_ahead=False):
    if one_press:
        import one_press as presses
        if not any(a.kind in presses.KINDS for a in actions):     # the decision loop adds them itself
            keys = {a.key for a in actions}
            actions = list(actions) + [a for a in presses.options(kitchen, 'jeff', actions, one_press) if a.key not in keys]
    if names:
        # The food_names trial (food_names.py): every food named from its ingredient and state, labels included.
        import food_names
        state, actions = food_names.state(state), food_names.labels(kitchen, actions, one_press)
    payload = harness.compose(client.payload(state, actions), kitchen, recent_decisions, communication, memory, one_press,
                              undo, reach, names, split, burn, serve_note, steps, clear)
    if defer:
        return payload, actions
    return finish_payload(payload, kitchen, actions, undo, names, links, serve_note, clear, walk, plate, parts, go, work,
                          joint=joint, is_ahead=is_ahead)


def finish_payload(payload, kitchen, actions, undo, names, links, serve_note, clear, walk, plate, parts, go=False,
                   work=None, joint=None, is_ahead=False):
    """The notes that fork the kitchen for each option, the links table and the request parts, in compose_payload's
    order (see defer there)."""
    if undo is not None:
        # undo-note-v4: worked out on forks of this kitchen, before the links table (live and in replay alike).
        undo_note.apply(payload, undo, kitchen)
    if walk:
        import walk_note
        walk_note.apply(payload, kitchen, actions)
    if go:
        import go_note
        go_note.apply(payload, kitchen, actions)
    if plate:
        import plate_names
        plate_names.apply(payload)
    if work:
        import work_notes
        work_notes.apply(payload, kitchen, actions, names=names, **work)
    if links:
        import links as option_links
        payload = option_links.apply(payload, kitchen, 'jeff', actions, names, **option_links.flags(links))
        if clear:
            import clear_names
            clear_names.apply(payload, kitchen)
        if serve_note:
            import option_notes
            option_notes.apply_links(payload, kitchen)
    # Released (servability-v1): each burnt food's tier in the state's food text. After the notes that read the
    # state's names (clear_names puts them into labels), before the request parts (the kitchen view shows it too).
    servability.apply(payload, kitchen)
    if parts:
        import request_parts
        request_parts.finish(payload, kitchen, **parts)
    if joint is not None:
        joint_plan.apply(payload, kitchen, joint, ask_ahead=is_ahead)
    return payload


def more_urgent(before, now):
    """Whether an order or a pan that is in both urgency tuples (DecisionLoop.urgency) has crossed into a more urgent
    band; one that appeared or went (a new order, an order served, food put on or taken off a stove) does not count.
    (2026-11-21: an ask-ahead answer was dropped on any change, and asked again it came back the same 13 times in 16.)"""
    old = {item[0]: item[1:] for item in before or ()}
    return any(key in old and any(n > o for n, o in zip(bands, old[key])) for key, *bands in now or ())


class DecisionLoop:
    def __init__(self, kitchen, client, log, notify):
        # Jeff plays through an AgentPort (environment.py): he reads the kitchen through its read-only view and
        # changes it only through the port, like any other agent.
        self.port = kitchen if isinstance(kitchen, environment.AgentPort) else environment.AgentPort(kitchen, 'jeff')
        self.k = self.port.view
        self.client = client
        self.log = log
        self.notify = notify
        self.q = queue.Queue()
        self.inflight = False
        self.last_request = -1e9
        self.last_revision = -1
        self.next_allowed = 0.0
        self.last_urgency = None
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
        # Undo notes (undo_note.py) when the round's switch is on: Jeff's last steps, as {'history': [...]}; None when off.
        self.undo = None
        # The reach_note trial (reach_note.py): on a split floor, which stations each chef can reach.
        self.reach = False
        # The split_floor trial (split_floor.py): on such a floor, that no dish can be made by one chef alone.
        self.split = False
        # The burn_note trial (burn_note.py): options on a stove with cooked food say when it burns.
        self.burn = False
        # The option_notes trial (option_notes.py): options that serve or pick up a finished dish name its order.
        self.serve_note = False
        # The step_check trial (step_check.py): whether each step the waiting orders need is possible now.
        self.steps = False
        # The clear_names trial (clear_names.py): what each item id and "the held item" is.
        self.clear = False
        # The walk_note trial (walk_note.py): each option's walk in seconds.
        self.walk = False
        # The go_note trial (go_note.py): a "go X" option says when nothing there takes what Jeff holds.
        self.go = False
        # The work notes trials (work_notes.py): own_chain, plate_result, board_taken; None when all are off.
        self.work = None
        # Called when a request is ready to send or a reply has come (the session's wake event): the game loop then
        # handles it at once instead of at its next tick.
        self.wake = None
        # The plate_names trial (plate_names.py): a plating option says what the plate there holds.
        self.plate = False
        # The engine_english trial (engine_english.py): the engine's own English where the catalog garbles it.
        self.english = False
        # The food_names trial (food_names.py): food named "<item> (<state>)" in Jeff's request.
        self.names = False
        # The option_links trial (links.py): each request lists the work each option leads to; the time it takes to
        # compute is counted in when deciding whether to ask ahead (link_times, recent seconds).
        self.links = False
        self.link_times = []
        # The parts of the restructured request (request_parts.py): finish's switches, or None. They run last: in
        # compose_payload, or at the end of the links thread when the table is computed there.
        self.parts = None
        # The table is computed outside the game loop (prepare in send_request): a thread fills it on a private fork,
        # and the next poll logs and sends the request it completes.
        self.prepared = queue.Queue()
        # Ask ahead (ask_ahead.py) when the round's switch is on: an answer about the next step, held until this step
        # ends, and the step it was asked for (asked once per step).
        self.ask_ahead = False
        self.held = None
        self.ahead_job = None
        self.step_end_seen = None   # (step id, countdown bands, hand) when Jeff's last step ended
        # Shared order focus (joint_plan.py) when the joint_plan trial is on; None when off.
        self.joint_plan = None

    def _notify_joint(self, entry):
        """Short player notice when a shared order focus changes state."""
        kind = entry.get('transition')
        order_id = entry.get('order_id') or ''
        by = entry.get('by')
        if kind == 'proposed' and by == 'jeff':
            self.notify(f'Jeff 提议共同聚焦订单 {order_id}（按 Y 同意 / N 拒绝）')
        elif kind == 'accepted' and by == 'jeff':
            self.notify(f'Jeff 同意共同聚焦订单 {order_id}')
        elif kind == 'declined' and by == 'jeff':
            self.notify(f'Jeff 暂不聚焦订单 {order_id}，转为自由配合')
        elif kind == 'released' and by == 'jeff':
            self.notify(f'Jeff 已解除订单 {order_id} 的共同聚焦')
        elif kind == 'accepted_implicit':
            self.notify(f'已自动确认共同聚焦订单 {order_id}')
        elif kind == 'suspended':
            reason = '起火' if entry.get('reason') == 'fire' else '炉灶快糊'
            self.notify(f'检测到{reason}，已暂时挂起订单聚焦')
        elif kind == 'completed':
            self.notify(f'共同聚焦的订单 {order_id} 已完成')

    def reply_time(self):
        """The typical recent reply time, or None before any answer."""
        recent = sorted(self.reply_times[-5:])
        return recent[len(recent)//2] if recent else None

    def can_ask_ahead(self, job):
        """Whether ask_ahead may ask about the end of this step: on, not asked for it yet, no one-press steps left to
        come, and an ordinary step. The undo note may be on (undo-note-v2):
        the step under way, kept as Jeff's last step when it started, is his last step at the moment asked about."""
        return (self.ask_ahead and self.ahead_job != job.id and (self.chain is None or not self.chain['steps'])
                and job.action.kind not in ('continue', 'wait'))

    def outlasts_reply(self, job):
        """Whether Jeff's current step will end before a request sent now could be answered."""
        expected = self.reply_time()
        if expected is None:
            return False
        remaining = max(0.0, job.travel) + max(0.0, job.work)
        if self.links and self.link_times:
            expected += sorted(self.link_times[-5:])[len(self.link_times[-5:]) // 2]
        return remaining / max(self.game_speed, 1e-6) < expected

    def start_chain(self, decision, put_where):
        """Start a one-press choice: its first step now (the put put_where chose, or the first step itself with empty
        hands); the rest follow as each step finishes. Returns applied, message and how it started."""
        steps = one_press.steps(decision, self.k)
        fallback = False
        if self.k.chefs['jeff'].hand is not None and decision.kind in one_press.PUT_KINDS:
            first, fallback = one_press.place(self.k.actions('jeff'), put_where)
        else:
            first, steps = one_press.find(self.k, 'jeff', steps[0]), steps[1:]
        if first is None:
            return False, '一键操作的第一步现在做不了', {'first': None, 'fallback': fallback}
        applied, message = self.port.start(first)
        self.end_chain('replaced')
        job = self.k.chefs['jeff'].job
        if applied and job is not None:
            self.chain = {'key': decision.key, 'steps': list(steps), 'job': job.id, 'done': False}
            self.chain_cursor = len(self.k.events)
        return applied, message, {'first': first.key, 'fallback': fallback}

    def end_chain(self, reason, failed=None):
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
        step = self.chain['steps'].pop(0)
        action = one_press.find(self.k, 'jeff', step)
        applied = action is not None and self.port.start(action)[0]
        job = self.k.chefs['jeff'].job
        if not applied or job is None:
            self.end_chain('step_not_possible', failed={'kinds': list(step[0]), 'target': step[1]})
            return
        self.chain.update(job=job.id, done=False)
        self.chain_cursor = len(self.k.events)

    def invalidate(self):
        self.epoch += 1
        self.last_revision = -1

    def urgency(self, kitchen=None):
        k = kitchen or self.k
        # Bucket changes trigger once when crossing each threshold, not each tick.
        def band(t):
            return sum(t <= x for x in (15, 8, 3, 0))
        return tuple((o["id"], band(o["deadline"]-k.time)) for o in k.orders if o["status"] == "pending") + tuple(
            (key, band(k.rules.heat_thresholds(s.food.ingredient)[1]-s.food.heated),
             band(k.rules.heat_thresholds(s.food.ingredient)[2]-s.food.heated))
            for key, s in k.stations.items() if key in k.pots and s.food)

    def release_held(self, now):
        """The held ask-ahead answer once Jeff's step is over, with why it may not be carried out (or None); None while
        the step goes on."""
        context, result, error = self.held
        ahead = context['ahead']
        job = self.k.chefs['jeff'].job
        too_old = now - context['sent'] > self.k.c['ai_max_response_age']
        if job is not None and job.id == ahead['job_id'] and not too_old:
            return None
        ended = next((e.get('kind') for e in self.k.events[ahead['cursor']:] if e.get('actor') == 'jeff'
                      and e.get('action_id') == ahead['job_id'] and e.get('kind') in ('action_done', 'interrupted', 'knocked')), None)
        decision, reason = None, None
        # The prediction was of the step's end: compare with the kitchen then (an answer that comes later finds the
        # clocks moved on, as any answer does), or now if the step ended at this very tick.
        seen = self.step_end_seen if self.step_end_seen and self.step_end_seen[0] == ahead['job_id'] else None
        urgency, holding = (seen[1], seen[2]) if seen else (self.urgency(), ask_ahead.hand(self.k))
        if too_old:
            reason = 'too_old'
        elif ended != 'action_done':
            reason = 'step_' + (ended or 'replaced')
        elif job is not None:
            reason = 'new_step_started'
        elif holding != ahead['hand']:
            reason = 'hand_differs'
        elif more_urgent(ahead['urgency'], urgency):
            reason = 'urgency_changed'
        elif self.epoch != context['epoch']:
            reason = 'paused_or_restarted'
        else:
            chosen = context['actions'][result['choice']]
            listed = self.k.actions('jeff')
            if self.one_press:
                listed = listed + one_press.options(self.k, 'jeff', listed, self.one_press)
            decision = ask_ahead.still_listed(listed, chosen)
            reason = None if decision is not None else 'not_listed'
        self.held = None
        return {**context, 'ahead_check': reason, 'decision': decision}, result, error

    def send_prepared(self):
        """A request whose links table a thread has finished: logged and sent now, from the game loop."""
        try:
            context, payload, record, seconds, error = self.prepared.get_nowait()
        except queue.Empty:
            return
        self.link_times = (self.link_times + [seconds])[-5:]
        if error is not None:
            # No request without the table it was built for: this one is dropped and Jeff is asked again.
            self.inflight = False
            self.last_revision = -1
            self.log('ai_error', {'request_id': context['id'], 'error': f'步骤提示计算失败（{type(error).__name__}）', 'retry_in': 0})
            return
        self.send(context, payload, {**record, 'links_ms': round(seconds * 1000)})

    def send(self, context, payload, record):
        context['joint_questions'] = [q for q in joint_plan.QUESTIONS if q in payload.get('questions', {})]
        self.log("ai_request", {**record, "payload": payload})

        def work():
            try:
                context['transport_started_monotonic'] = time.monotonic()
                # The record above keeps the payload as composed; the model is sent it without version tags (also the
                # browser relay, which has no client of its own here).
                result = self.client.ask(harness.for_model(payload))
                context['returned_monotonic'] = time.monotonic()
                self.q.put((context, result, None))
                if self.wake:
                    self.wake()             # take the reply at once, not at the next tick
            except ModelWait as exc:
                context['returned_monotonic']=time.monotonic()
                self.q.put((context,None,exc))
            except Exception as exc:
                context['returned_monotonic'] = time.monotonic()
                # Only our sanitized failures should reach logs.
                message = str(exc) if type(exc) is RuntimeError else f"响应读取失败（{type(exc).__name__}）"
                self.q.put((context, None, message))
        threading.Thread(target=work, daemon=True).start()

    def poll(self, enabled=True):
        now = time.monotonic()
        if enabled and not self.closed and not self.k.ended and self.joint_plan is not None:
            for entry in joint_plan.sync(self.joint_plan, self.k):
                self.log('joint_plan', entry)
                self._notify_joint(entry)
        self.send_prepared()
        packet = None
        if self.held is not None:
            packet = self.release_held(now)
        if packet is None:
            try:
                packet = self.q.get_nowait()
            except queue.Empty:
                packet = None
            if packet and packet[2] is None and packet[0].get('ahead') and 'ahead_check' not in packet[0]:
                # An answer asked ahead waits for the step it was asked about to end.
                self.inflight = False
                packet[0]['received'] = now     # its reply time ends here, not when it is released
                self.held = packet
                packet = self.release_held(now)
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
                self.reply_times = (self.reply_times + [context.get('received', now)-context["sent"]])[-5:]
                for key in self.tokens:
                    self.tokens[key] += result["usage"].get(key, 0)
                decision = context.get('decision') or context["actions"][result["choice"]]
                chef = self.k.chefs["jeff"]
                current_job = chef.job.id if chef.job else None
                if context.get('ahead'):
                    # Asked ahead: released once the step ended, and carried out only if every check passed.
                    fresh = not self.closed and enabled and not self.k.ended and context['ahead_check'] is None
                else:
                    fresh = (not self.closed and enabled and not self.k.ended and context["epoch"] == self.epoch
                             and now-context["sent"] <= self.k.c["ai_max_response_age"]
                             and context["job_id"] == current_job)
                # "continue" to a request made during a one-press chain that is still under way: the chain has moved
                # to its next step (a new job), so the reply used to be dropped as stale and Jeff asked again, while
                # the step outlasted nothing he chose; it holds as long as that same chain goes on.
                chain_goes_on = (not fresh and not context.get('ahead') and decision.kind == 'continue'
                                 and context.get('chain') is not None and self.chain is context.get('chain')
                                 and not self.closed and enabled and not self.k.ended and context["epoch"] == self.epoch
                                 and now-context["sent"] <= self.k.c["ai_max_response_age"])
                pressed = None      # how a one-press choice started: its first step and whether put_where fell back
                if chain_goes_on:
                    applied, message = True, "继续"
                elif fresh and decision.kind in one_press.KINDS:
                    applied, message, pressed = self.start_chain(decision, result.get(one_press.PUT_WHERE))
                elif fresh:
                    applied, message = self.port.start(decision)
                    if applied and decision.kind != 'continue':
                        self.end_chain('replaced')
                elif context.get('ahead'):
                    applied, message = False, f"提前问的回复作废（{context['ahead_check'] or '已暂停或本局结束'}），马上重问"
                else:
                    applied, message = False, "回复已过期、任务已变化或游戏已暂停"
                fresh = fresh or chain_goes_on
                note = message      # what recent_decisions keeps; the player's notice below stays as written
                if self.english and not applied:
                    # The engine_english trial (engine_english.py): the loop's own notes in English.
                    if not fresh and context.get('ahead'):
                        note = engine_english.ahead_dropped(context['ahead_check'])
                    elif fresh and decision.kind in one_press.KINDS and pressed and pressed['first'] is None:
                        note = engine_english.CHAIN_NOT_NOW
                sprint_applied=bool(applied and result.get('sprint') is True and self.port.sprint())
                if not fresh:self.stale_count += 1
                elif not applied:self.rejected_count += 1
                chef_job = self.k.chefs["jeff"].job
                current_state = self.k.snapshot()
                if self.undo is not None and applied:
                    # (undo-note-v4) The step as it starts: the kitchen's layout and the places it acts on, kept with
                    # each request's record so research replay rebuilds the notes from the same history.
                    listed = context.get('actions') or {}
                    first = (pressed or {}).get('first')
                    self.undo = undo_note.remember(self.undo, undo_note.record(
                        self.k, listed.get(result["choice"]), listed.get(first) if first else None, self.k.time))
                if fresh and self.joint_plan is not None and context.get('joint_questions'):
                    jp_entry = joint_plan.apply_answer(self.joint_plan, self.k, result, context['joint_questions'])
                    if jp_entry is not None:
                        self.log('joint_plan', jp_entry)
                        self._notify_joint(jp_entry)
                self.log("ai_response", {"request_id": context["id"], **result, "applied": applied, "execution": message, "sprint_applied":sprint_applied,
                                         "fresh": fresh,
                                         **({"chain_continue": True} if chain_goes_on else {}),
                                         **({"one_press": pressed} if pressed else {}),
                                         **({"ask_ahead": {'result': 'applied' if applied else 'discarded',
                                                           'reason': None if applied else context['ahead_check'] or 'not_fresh'}}
                                            if context.get('ahead') else {}),
                                         "server_received_wall_ms": round((context["returned_monotonic"]-self.log.monotonic_start)*1000) if "returned_monotonic" in context and hasattr(self.log,"monotonic_start") else None,
                                         "server_transport_started_wall_ms": round((context["transport_started_monotonic"]-self.log.monotonic_start)*1000) if "transport_started_monotonic" in context and hasattr(self.log,"monotonic_start") else None,
                                         "action_id": chef_job.id if applied and chef_job and decision.kind not in ("continue", "wait")
                                                      and decision.key not in ("continue", "wait") else None,
                                         "accepted_engine_seq": self.k.event_seq, "current_state": current_state})
                self.last_choice = result["choice"] + ("" if applied else "（未执行）")
                self.recent_decisions.append({"t": round(self.k.time, 2), "choice": result["choice"],
                                              "accepted": applied, "result": note, "sprint_applied":sprint_applied})
                self.recent_decisions = self.recent_decisions[-8:]
                quiet = decision.kind in ("continue", "wait")
                if not quiet or not applied or now-self.last_wait_notice >= 8:
                    # The label without what it said at listing time of burnt food's tier or of what follows a fire
                    # (Kitchen.plain_action): the notice stays on the player's status line after its seconds go stale.
                    shown = Kitchen.plain_action(decision).label
                    self.notify(f"Jeff 选择：{shown} | {result['latency']:.2f}s" + ("" if applied else f" | 未执行：{message}"))
                    self.last_wait_notice = now
                if not applied:
                    self.last_revision = -1
                    if context.get('ahead') and self.k.chefs['jeff'].job is None:
                        self.step_ended = True      # dropped at the end of the step: ask at once, as today
        # A one-press chain goes on before anything else looks at Jeff's step, so its steps read as one.
        self.advance_chain()
        job = self.k.chefs["jeff"].job
        if job is None and self.watched_job is not None:
            self.step_ended = True      # done, interrupted or knocked off: he now needs his next step
            if self.ask_ahead:
                self.step_end_seen = (self.watched_job, self.urgency(), ask_ahead.hand(self.k))
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
        # Ask ahead: the moment a reply would come only after Jeff's step ends is itself a reason to ask (once per step),
        # so the answer about his next step arrives as this one ends.
        ahead_now = (self.ask_on_step_end and job is not None and self.held is None and self.can_ask_ahead(job)
                     and self.outlasts_reply(job))
        if age < self.k.c["ai_min_interval"] and not (step_end or ahead_now):
            return
        urgency = self.urgency()
        changed = self.k.revision != self.last_revision
        urgent = urgency != self.last_urgency
        if not (changed or urgent or step_end or ahead_now
                or age >= self.k.c["ai_refresh_seconds"]):
            return
        # (2026-11-21) A change of urgency during a one-press chain no longer asks when the reply would come only after
        # the step ends: such a reply could be carried out only as "continue" (the chain's next step is a new job), so
        # it was dropped about 5 times a round; the chain's last step is asked about ahead as usual.
        source = self.k             # the kitchen the request describes: this one, or with ask_ahead its fork at the step's end
        if self.held is not None:
            return                  # an answer about the next step is waiting for this one to end
        if self.ask_on_step_end and job is not None and self.outlasts_reply(job):
            # The answer would come after this step ends and be discarded; ask when it ends instead, or with
            # ask_ahead ask now about the kitchen as it will be when the step ends (once per step).
            if not self.can_ask_ahead(job):
                return
            source = ask_ahead.predict(self.k)
            self.ahead_job = job.id
            if source is None:
                return
        actions = source.actions("jeff")
        if self.one_press:
            actions = actions + one_press.options(source, 'jeff', actions, self.one_press)
        state = source.snapshot()
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
                   "actions": {a.key: a for a in actions},
                   # The one-press chain under way when asked (the object itself), for a "continue" reply (below).
                   "chain": self.chain}
        ahead = None
        if source is not self.k:
            ahead = {'job_id': chef.job.id, 'predicted_end_t': round(source.time, 3)}
            # What the prediction expects at the step's end: Jeff's hand, and the countdown bands (the clocks of orders and
            # pans played forward, so a band the clock alone crosses is already in the request).
            context['ahead'] = {**ahead, 'cursor': len(self.k.events), 'hand': ask_ahead.hand(source),
                                'urgency': self.urgency(source)}
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
        undo = deepcopy(self.undo)
        plan_snap = joint_plan.snapshot_for_record(self.joint_plan)
        is_ahead = source is not self.k
        # With the links table on, only the translation is done here; the notes that fork the kitchen per option (undo,
        # walk, go, plate names, work notes) and the table follow in its thread (finish_payload, same order).
        composed = compose_payload(self.client, source, state, actions, self.recent_decisions, communication,
                                   self.cooperation_memory if hasattr(self, 'cooperation_memory') else NO_MEMORY, self.one_press,
                                   undo, self.reach, self.names, split=self.split,
                                   burn=self.burn, serve_note=self.serve_note,
                                   steps=self.steps, clear=self.clear, walk=self.walk,
                                   english=self.english, plate=self.plate, parts=self.parts,
                                   go=self.go, work=self.work, defer=bool(self.links),
                                   joint=plan_snap, is_ahead=is_ahead)
        payload, tail_actions = composed if self.links else (composed, None)
        record = {"request_id": self.calls, "triggers": causes, "observed_state_seq": self.k.event_seq,
                  **({"one_press": dict(self.one_press)} if self.one_press else {}),
                  **({"undo_note": deepcopy(self.undo)} if self.undo is not None else {}),
                  **({"joint_plan": plan_snap} if plan_snap is not None else {}),
                  # The request parts (request_parts.py) may leave the decisions out of the request or rewrite them;
                  # research replay rebuilds from the loop's own list then.
                  **({"recent_decisions": deepcopy(self.recent_decisions)} if self.parts else {}),
                  **({"ask_ahead": ahead} if ahead else {})}
        self.last_request = now
        self.last_revision = self.k.revision
        self.last_urgency = urgency
        self.step_ended = False
        self.inflight = True
        if not self.links:
            self.send(context, payload, record)
            return
        # The links table (links.py) takes a few tenths of a second; computed here it would hold the whole kitchen
        # (both chefs) still. A private fork of the kitchen the request describes goes to a thread instead, and the
        # request is logged and sent at the next poll once the table is in. The record keeps where the engine was now,
        # so research replay rebuilds this request, not a later one.
        twin = source if source is not self.k else source.fork()
        criteria = payload['questions']['next_action']['criteria']
        record.update(engine_input_n=len(self.k.inputs), state_ref=getattr(self.k, '_research_state_ref', None),
                      candidate_source=[[a.key, a.target, a.kind] for a in self.k.actions('jeff') if a.key in criteria])
        mode, names, clear, english = self.links, self.names, self.clear, self.english
        serve_note, parts, work, walk, go, plate = self.serve_note, self.parts, self.work, self.walk, self.go, self.plate

        def prepare():
            start = time.monotonic()
            try:
                # A context variable does not cross into a thread: the engine_english switch is set here again.
                # (2026-11-21: the per-option notes moved here from the game loop, where they held both chefs still
                # about 0.2 s a request; the request is byte for byte what compose_payload builds.)
                with engine_english.writing(english):
                    done = finish_payload(payload, twin, tail_actions, undo, names, mode, serve_note, clear, walk, plate,
                                          parts, go, work, joint=plan_snap, is_ahead=is_ahead)
                self.prepared.put((context, done, record, time.monotonic() - start, None))
            except Exception as error:      # never the payload or a key: only the kind of failure is logged
                self.prepared.put((context, payload, record, time.monotonic() - start, error))
            if self.wake:
                self.wake()                 # send it at once, not at the next tick
        threading.Thread(target=prepare, daemon=True).start()
