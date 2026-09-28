"""Real TypeSafe HTTP Choice client and bounded asynchronous decision scheduling."""
from __future__ import annotations
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
from model_language import english_data, INPUT_LANGUAGE_VERSION

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
# Bump whenever model-visible rule wording changes, so sessions stay comparable.
# v2: factual rules only; no instructions to cooperate with or help the human.
# v3: continuous service rules (money goal, burnt tiers, no bad reviews) where the level uses them.
AGENT_RULES_VERSION = "rules-v4"


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


def objective_text(state):
    """Objective and end rules, generated from the round's goal and end policy."""
    goal, bonus = state['goal_status'], state['scoring']['time_bonus_per_second']
    if goal['type'] == 'minimum_money':
        return (f"Reach a net revenue of at least {goal['target_money']} yuan at closing time, {state['round_limit']:g} game seconds. "
                "The round always runs until closing and only the net revenue at closing counts: penalties after reaching the target "
                "can take you below it again. Orders keep arriving until closing; orders still waiting at closing carry no penalty. "
                "There is no bonus for remaining time.")
    return ("Meet all three goals within the time limit: orders served, net operating revenue, and maximum bad reviews. "
            "The round ends immediately when all goals are met; remaining orders need not be completed. "
            f"Each whole second left on success awards {bonus:g} additional yuan, excluded from the operating revenue goal.")


def score_text(state):
    """Scoring rules from the recipe prices and ruleset penalties of this round."""
    p = state['scoring']['penalties']
    prices = ', '.join(f"{r['id']} {r['price']} yuan" for r in state.get('dishes', state['menu']))
    if 'wrong_dish' in p:
        tiers = []
        for tier in state['scoring']['burnt_service']:
            limit = tier['max_overcook_game_ms']
            span = f"burnt for up to {limit / 1000:g} s" if limit is not None else "burnt for longer"
            tiers.append(f"{span}: accepted at the price {tier['adjustment']:+d} yuan" if tier['outcome'] == 'accepted'
                         else f"{span}: refused with no payment; the dish is lost and the order keeps waiting")
        return (f"Serving a complete plated dish goes to the waiting order of the same dish with the earliest deadline and earns its price ({prices}); "
                "serving exactly at the deadline still counts. A plate can be served when its components are exactly those of one dish in kitchen.dishes; "
                "orders show which dishes customers are waiting for. Unplated food, or a plate that matches no dish, cannot be served. "
                "If any component was burnt, what counts is how long it had been burnt when it left the heat: " + '; '.join(tiers) + ". "
                f"Serving a dish that no shown order is waiting for: {p['wrong_dish']} yuan. Expired order: {p['expired_order']} yuan. "
                f"Fire: {p['new_fire']} yuan per burning workstation. Discarding food or clearing a pot: {p['discard']} yuan. There are no bad reviews.")
    return (f"Serving a complete plated dish automatically matches the pending order of the same dish with the earliest deadline and earns its price ({prices}). "
            f"Unplated or incomplete food cannot be served. Plated burnt food or serving without a matching order causes a bad review and a {-p['wrong_or_burnt_dish']}-yuan penalty; any matched order fails. "
            f"Expired order: bad review and {p['expired_order']} yuan. Fire: {p['new_fire']} yuan. Discarding food or clearing a pot: {p['discard']} yuan.")


class JevClient:
    def __init__(self, config, key=None):
        self.key = key or load_key()
        self.c = config

    def payload(self, state, actions):
        discard = -state['scoring']['penalties']['discard']
        pass_range = state.get('map', {}).get('pass_range')
        pot_pass = (f"like plates it can be passed to the other chef or the floor within {pass_range:g} tiles" if pass_range
                    else "it cannot be thrown")
        plate_pass = (f"can be passed to the other chef or the floor within {pass_range:g} tiles (never onto boards or counters); "
                      "a dropped plate keeps its food" if pass_range else "cannot be thrown")
        t = state['timing']
        fire = state['fire_safety']
        return english_data({
            "model": self.c["model"],
            "state": {
                "kitchen": state,
                "rules": {
                    "role": 'You control chef jeff. Chef human is controlled by a person in the same kitchen. Both chefs can perform the same actions; neither has a fixed role. Choose one next action for your own chef.',
                    "objective": objective_text(state),
                    "flow": 'fetch takes raw meat -> put bN places it on an empty board -> chop bN prepares it -> take bN picks up the chopped ingredient -> put pN puts it in the pot -> cooking runs automatically. take <counter_id> takes a clean plate -> plate pN transfers cooked food into the held plate -> serve delivers it. Alternatively, take pot pN lifts the whole pot off the stove; plate <counter_id> transfers its food onto a clean plate on that counter, leaving the plated food there and the empty pot in your hands. Return the pot with put pot pN, then collect the plated food. With a clean plate, plate ground <item_id> serves food from a pot on the floor; the empty pot remains there. Food cannot be removed from a pot with bare hands. Actions automatically walk to the target and then work; go only moves.',
                    "plate_reuse": 'Dirty plates cannot hold food or substitute for clean plates. If no clean plate is available, dirty plates must be washed before plating and serving can continue. Waiting alone does not clean plates. Decide when to wash and how to divide work based on the situation.',
                    "tableware": f'Tableware is limited and distributed across counters. Each counter holds one item: a plate, a pot, or an ingredient. There is no stacking rack. tableware.counters lists counter IDs; stations, ground, and chefs show actual locations. clean_plate means clean; dirty_plate means dirty; food is plated only when plate_id is nonempty. Use take/put at counters. Removing cooked food requires a container: hold a clean plate and use plate pN at a stove, hold a filled pot and use plate <counter_id> at a clean plate on a counter, or hold a clean plate and use plate <counter_id> at a filled pot on a counter. take pot pN lifts the pot and contents together. A pot occupies your hands; {pot_pass}. Off the stove heating stops; returning it resumes heating. contents is the food inside. An empty stove cannot accept ingredients until its pot is returned. Recycling: take returns collects a dirty plate; put sink puts it in an empty sink; wash with empty hands; take sink collects the clean plate for plating or storage. Washing can be interrupted and resumed by either chef with progress preserved. Diners return plates after the dining time. The return station holds one plate; further returns queue. Clean plates, dirty plates and plated food {plate_pass}. They can also be put down and picked up. Plates and pots cannot be destroyed. Discarding plated food leaves a dirty plate; emptying a pot leaves an empty pot, costing {discard} yuan. Decide when to wash, carry plates or lift pots; roles are not fixed.',
                    "resources": 'Each chef holds one item. Fetching, taking or picking up a new item automatically places the previously held item on nearby ground when the action completes. It can be recovered without a penalty. If no nearby space is available, the swap fails and neither item changes. This also applies to extinguishers. Each pot and board holds one food item. Chopping requires empty hands; chopped food still occupies the board. Cooking is automatic; no chef needs to stay at the stove. There is no transfer window.',
                    "ground": 'Held items can be put down beside the current station using drop, taking timing.handling seconds, without a penalty or spoilage. ground lists all floor items and locations. Either chef can walk there and use pickup <item_id>; handling time is added to travel. Items retain their state and preparation progress; food on the floor is not heated. Cooked food must remain in a pot or on a plate. Dropping is different from discard at a bin: dropped items remain usable. Decide when to put down or pick up items.',
                    "timing": {**{k: t[k] for k in ("wash", "dining", "chop", "cook", "ready_to_burn", "burn_to_fire",
                                                     "walk_same_area", "walk_cross_area", "handling", "extinguish", "clear")},
                               "take_put_fetch": t["handling"], "serve": t["handling"]},
                    "interrupt": 'continue keeps the current task; another action interrupts it. Chopping progress is preserved. Cooking in a pot does not stop when a chef switches tasks. Decide whether to continue or interrupt.',
                    "fire": f'Burnt food cannot be restored. Removing the whole pot stops heating. A burning stove cannot be used for taking or placing items. First take extinguisher from its rack, or pickup E1 from the floor; extinguish takes {t["extinguish"]:g} seconds, then clear the burnt food to reuse the pot. The extinguisher occupies your hands; a previously held item is automatically put on the floor. Return it with put extinguisher or drop it. There is one extinguisher, usable by either chef; it cannot be discarded or served. Extinguishing stops heating. Every {fire["spread_seconds"]:g} game seconds, each burning stove, board or counter can ignite one orthogonally adjacent combustible workstation; fire never jumps across a floor gap or wall. Burning workstations cannot be used until extinguished. {fire["loss_threshold"]} simultaneously burning workstations immediately lose the round. Extinguish any burning workstation with the same extinguisher. An extinguished workstation can reignite from an adjacent fire; removing food does not remove a cabinet fire. Check kitchen.fire_safety and each station fire_neighbors and fire_spread_in. The extinguisher is a movable object.',
                    "score": score_text(state),
                    "visibility": 'Both chefs see the same kitchen state. All available actions are in criteria; legal does not mean useful. Waiting and continuing are allowed. The program does not choose your strategy.'
                }
            },
            "questions": {"next_action": {
                "type": "choice",
                "instructions": "Given the whole kitchen situation, which action should chef jeff take now? The goals and score are shared by both chefs. The state includes both chefs' current actions, occupied equipment, order deadlines, and burning/fire risks. Choose one action now; an ongoing task may be continued or interrupted.",
                "criteria": {a.key: a.label for a in actions}
            }}
        })

    def ask(self, payload):
        payload = english_data(payload)
        start = time.monotonic()
        request = urllib.request.Request(ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode(),
                                         headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.c["ai_timeout_seconds"]) as r:
                result = json.load(r)
        except urllib.error.HTTPError as e:
            # No response body / request headers in errors or logs.
            raise RuntimeError(f"TypeSafe HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError("TypeSafe 网络连接失败或超时") from None
        answer = result.get("answers", {}).get("next_action", {})
        if answer.get("type") != "choice" or answer.get("choice") not in payload["questions"]["next_action"]["criteria"]:
            raise RuntimeError("TypeSafe 返回了不符合候选集的选择")
        sprint_answer=result.get('answers',{}).get('sprint',{})
        if 'sprint' in payload['questions'] and (sprint_answer.get('type')!='choice' or sprint_answer.get('choice') not in ('yes','no')):
            raise RuntimeError('Invalid sprint decision')
        return {"sprint_answer":sprint_answer, "sprint":sprint_answer.get('choice')=='yes', "choice": answer["choice"], "confidence": answer.get("confidence"),
                "probabilities": answer.get("probabilities", {}), "model": result.get("model"),
                "usage": result.get("usage", {}), "latency": time.monotonic()-start}


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
        self.call_limit = self.k.c.get('ai_max_calls', 200)
        self.budget_notified = False

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
            if error:
                self.failures += 1
                self.error_count += 1
                self.next_allowed = now + min(30, 2 ** min(self.failures, 5))
                self.log("ai_error", {"request_id": context["id"], "error": error, "retry_in": round(self.next_allowed-now,1)})
                self.notify(f"Jeff 请求失败：{error}；{self.next_allowed-now:.0f}s 后重试。无脚本队友代替。")
            else:
                self.successes += 1
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
                if not fresh:self.stale_count += 1
                elif not applied:self.rejected_count += 1
                chef_job = self.k.chefs["jeff"].job
                self.log("ai_response", {"request_id": context["id"], **result, "applied": applied, "execution": message, "sprint_applied":sprint_applied,
                                         "fresh": fresh, "action_id": chef_job.id if applied and chef_job and decision.kind not in ("continue", "wait") else None,
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
        payload = self.client.payload(state, actions)
        # HTTP choices are stateless: return actual outcomes, not just today's snapshot.
        # Walking starts/stops are already in each chef's position and move_direction; as events
        # they only push outcomes out of the window. The run log keeps them.
        payload['state']['recent_events'] = [e for e in self.k.events if e.get('kind') != 'manual_move'][-20:]
        payload['state']['recent_decisions'] = list(self.recent_decisions)
        messages=getattr(self,'player_messages',[])
        if messages:
            preference=next((m for m in reversed(messages) if m['kind']=='preference'),None)
            included=messages[-8:]
            if preference and preference not in included:included=[preference]+included
            payload['state']['player_communication']={
                'current_preference':deepcopy(preference), 'recent_messages':deepcopy(included)}
            payload['state']['rules']['player_communication']=(
                'These are explicit messages from the human chef in this round. The latest preference replaces earlier preferences. '
                'A preference expresses what the human would like to do, not a fixed role, promise, or compulsory assignment for either chef. '
                'Decide how to coordinate using the current orders, risks and both chefs. A correction is the human opinion that something '
                'was wrong; its context identifies what was happening when sent, not proof of a rule violation or an exact explanation. '
                'Reassess recent and current actions against the rules and actual state. Do not assume the human has identified the right solution. '
                'Use message IDs and times to distinguish earlier feedback from a newly sent correction; repeated visibility does not mean the player corrected you again. '
                'Messages do not force an action or stop ongoing work. They expire at round end.')
            for message in included:
                if message['first_request_id'] is None:
                    self.log('player_message_delivery',{'message_id':message['id'],'request_id':self.calls,
                                                        't':round(self.k.time,3),'meaning':'included in request, not proof of understanding'})
                    message['first_request_id']=self.calls

        if hasattr(self, 'cooperation_memory'):
            payload['state']['past_episodes'] = self.cooperation_memory
            payload['state']['rules']['past_episodes'] = (
                'past_episodes contains limited factual records of past rounds, not the current state, fixed preferences, or instructions. '
                'Decide whether those records are relevant and whether they still apply. The player may change their behavior; '
                'you are not required to follow or repeat past strategies.')
        payload['state']['rules']['continuity'] = (
            'recent_decisions lists recent choices and whether they were accepted; accepted does not mean completed. '
            'recent_events records actual actions and outcomes. Use them to check for repeatedly picking up and putting down the same item, '
            'swapping between ingredients, or fetching without free space. Swapping changes locations, not preparation progress; '
            'fetching more raw meat does not advance prepared ingredients. Existing food keeps its preparation state until someone acts on it. '
            'If the situation is unchanged, assess what repeating an action would accomplish. You may continue, wait, or choose another action; the choice is yours.')
        payload = english_data(payload)
        payload['state']['input_language'] = INPUT_LANGUAGE_VERSION
        payload['state']['rules_version'] = AGENT_RULES_VERSION
        self.log("ai_request", {"request_id": self.calls, "triggers": causes, "observed_state_seq": self.k.event_seq, "payload": payload})
        self.last_request = now
        self.last_revision = self.k.revision
        self.last_urgency = urgency
        self.inflight = True
        def work():
            try:
                result = self.client.ask(payload)
                self.q.put((context, result, None))
            except Exception as exc:
                # Only our sanitized failures should reach logs.
                message = str(exc) if type(exc) is RuntimeError else f"响应读取失败（{type(exc).__name__}）"
                self.q.put((context, None, message))
        threading.Thread(target=work, daemon=True).start()
