# Agent integration

Cocos provides rendering and player input; Python maintains authoritative kitchen state. The agent selects an action, and the engine validates and executes it.

## Decision flow

`SpatialKitchen.snapshot()` and `actions('jeff')` → client `payload(state, actions)` → asynchronous `ask(payload)` → `DecisionLoop` validation → `kitchen.start()` → movement/work → completion event.

Use actor IDs `human` and `jeff`. TypeSafe's provider ID `jev`, model IDs and `jev.py` adapter name remain unchanged. Old local memory actor fields are normalized when read; model identities and historical files remain intact.

Track requests, selections, accepted actions and `action_done` separately. A legal choice can become stale while the request is in flight.

## Compatible services

Choose a compatible Chat Completions service in Settings and supply your own HTTPS base URL, model and key. `CompatibleClient` sends structured state, rules and candidates. Return JSON such as:

```json
{"choice": "wash", "sprint": false}
```

`choice` must occur in the current `questions.next_action.criteria`; choose `wash` only when offered. `sprint` is a boolean when requested.

## New adapters

Jeff's input is assembled in `harness.py`: `harness.payload` builds the kitchen, rules and listed actions, and `harness.compose` adds recent events and decisions, player messages and memory. Follow `CompatibleClient` in `player_api.py`, which inherits `SpatialJevClient` from `whitebox_server.py`:

- `payload(state, actions)` returns the harness input, adding only the adapter's own fields (such as `model`), without modifying the game.
- `ask(payload)` returns a dictionary with `choice`, following existing `sprint`, `model`, `usage` and `latency` conventions.
- Add an explicit branch in `create_client(config, setting)`, with settings validation and UI choices.
- Use offline test doubles for invalid choices, stale replies, timeouts, budgets and recovery. Keep real keys out of CI.

Hosted play uses `BrowserRelay` plus `hosted/browser-agent.js`; add browser-provider support there separately. `BrowserRelay` only accepts a validated choice, sprint flag and numeric usage and never stores credentials. Jev's explicit opt-in path uses `hosted_jev.py` at `/api/model/jev`: it requires the authenticated page token, game/task ID and consent version, forwards only the server-created task (or a fixed connection test) to the fixed Jev URL/model, and keeps the supplied key local to HTTP request processing. Never send that body through game-command receipts/journals or add a user-selected forwarding URL.

## Jeff's plan (plan questions)

With the plan switch on, a request made while no plan holds also carries `questions.plan_step_1` to `plan_step_4`: `choice` questions whose criteria are the level's work items (`harness.work_items`: fetch, chop, cook or plate an ingredient, take a clean plate, serve, collect or wash plates), with `none` from step 2 on to end the plan there. While a plan holds, the request shows it as `state.jeff_plan` (its steps, each marked done) and asks `questions.plan_keep` (`keep` or `drop`) instead. The adapter returns each chosen key next to the action: a chat model writes `"plan_step_1": "<key>"` and so on in the same JSON (its system prompt gets `harness.PLAN_CHAT_RULE` only when plan questions are asked), a decision model answers each as a choice under `answers`. Pass the answers through `harness.plan_answer(answers, payload)`, which returns `{}` when nothing was asked, `{"plan": {"steps": [...]}}` (stopping at `none` or a key that was not offered) or `{"plan": {"keep": True, False or None}}`. `DecisionLoop` takes the plan only from a fresh reply and a bad plan answer never rejects the action. It ticks a step when Jeff finishes an action doing that work (`harness.work_item`), in any order; the plan has no clock and ends when every step is done, when Jeff answers `drop`, or when the human sends a new preference, and the next request, sent at once like after a finished step, asks for a new one. Hosted play does the same in `hosted/browser-agent.js`, which sends the answers as `plan` with the result.

The two-step rolling intent is a trial plan mode (`mode` `rolling`, rules version `rolling-v3`, off by default). Every request asks `questions.plan_step_1` (a note on `next_action`: the work item the chosen action does or is for) and `plan_step_2` (the one after it, or `none`), with the same work-item criteria, and never `plan_keep`. The newest valid answer is shown as history, not as a plan: as `intent` on the decision it was noted with in `state.recent_decisions`, ticked as above, under `state.rules.intent` = `harness.ROLLING_RULE`; there is no `state.jeff_plan`. A new valid answer replaces it and a missing one leaves it. While food in a pan on a stove is within `harness.ROLLING_YIELD_SECONDS` (8) game seconds of burning, the intent is left out of the request (the two questions are still asked) and shows again once no pan is that close. (`rolling-v1` showed it as `state.jeff_plan` and `rolling-v2` as history without that exception; with a pan about to burn, an intent shown either way kept Jeff on it.) The answers are read exactly as above (`harness.plan_answer`), so clients need no change. With `ai_ask_on_step_end` on, a change in an order's or a pan's countdown band asks even while Jeff's step will end before a reply could return (the four-step plan and plan mode off still wait for the step to end).

One-press options are released (`one_press.py`, version `one-press-v3`): `features.json` has `one_press` on, the page has no switch for it, and turning it off there (then restarting) is the rollback. (Until then they were two trial switches, `put_then_take` and `wash_from_returns`, set with `POST /api/one-press`, which is gone.) With it on, `next_action` can also offer `put then take <station>` (Jeff holds an item, another lies on a station he could take with empty hands, and no other listed action, walks and throws aside, is at that station; the plain `go <station>` then drops out as for any other action there), under the same switch `put then chop <board>` and `put then wash <sink>` (the same, for chopping what lies on a board or washing the dirty plate in the sink, which the engine lists only with empty hands; their labels give the seconds of work left, as the engine's own chop and wash labels do; `one-press-v1` had neither, and `one-press-v2` gave no seconds) and `wash from <plate return>` (a dirty plate is on the plate return and the sink is empty, not burning and not taken by the other chef). Whenever such an option is listed and Jeff holds something, the request also has `questions.put_where`, a `choice` question whose criteria are the put places already in `next_action` (`put …` and `drop`, same keys and labels); it is used only when `next_action` is one of these options. `state.rules.one_press` (`one_press.RULE`) and `state.one_press_version` say so. Answer `put_where` like the plan questions: decision models as a `choice` question, chat models as a `"put_where": "<key>"` field (`harness.PUT_WHERE_CHAT_RULE`), the browser relay inside `plan`; `harness.choice_answer` reads it, and a missing or unlisted answer falls back to the first listed put place (logged as `fallback`). The loop then runs the steps as ordinary starts: each is checked when it comes, a step that cannot be done ends the chain (`one_press_end`, reason `step_not_possible`), and another applied choice replaces it (`replaced`); a change of urgency asks even while a step is under way.

## Feature switches (`features.json`)

Jeff's harness features, the ones that change what he is asked or how his answers are carried out, are switched in one file, `features.json`, checked by `features.py` when the server starts (a wrong name, stage, value or version stops it). Each has a `stage`: `release` is on unless the file says `"on": false`, with no switch in the page, so turning it off and restarting rolls it back; `trial` is off unless the file says `"on": true`, and with `"player_switch": true` it shows in Settings → AI teammate as a (测试) switch whose default is `on`. `version` must be the version the code implements: the file only turns features on and off, and going back to an older version still means going back in the code. Today `one_press` is released and the two plan modes, `jeff_plan` (`choice`) and `rolling_intent` (`rolling`), are trials, one at a time; `communication.jeff_plan.available` lists the modes the page offers. `undo_note` is a trial without a player switch: with it on, an option that would take back what Jeff's last step put down, or put back what it took, carries a factual note with the time (`undo_note.py`; the player sees no note), and each request's research record keeps that step so it can be rebuilt; `scripts/undo_note_check.py` re-asks logged moments with and without the notes. `compact_input` is a trial without a player switch (version `compact-v1`, `wire_format.py`): with it on, every client sends the same request as two parts, the parts that stay the same for the whole round (`static`: every rule but `player_communication`, the kitchen's fixed fields such as map, menu and timing, each station's fixed attributes, the chefs' sprint constants, past episodes, the version fields and a table of field defaults) and the rest (`live`: the changing kitchen fields, stations and chefs without the fields at their defaults, an idle station left out, recent events and decisions, player messages, Jeff's plan). Chat models get `static` in the system message, after the fixed instructions, and `live` with the questions in the user message (for Zhipu the JSON Schema, whose enum changes, comes last); decision services get `state` as `{static, live}`; the hosted page gets both parts with each request (`wire`) and only places them, adding the browser's cross-round memory to `static`. `static` is byte-identical within a round, so providers can cache it as a prompt prefix, and `live` is about a fifth to a quarter of today's message. The request itself does not change: journals, research records (`payload_sha256`), replays and the analysis scripts see the same payload, `wire_format.expand(static, live)` gives back its state exactly, and with the switch off every client sends today's bytes. Local chat clients record `cached_input_tokens` when the provider reports cache hits. Every round's start row and research record carry the snapshot (`features`: each name with `on` and `version`). Game rules, levels, player preferences and numbers such as request spacing stay in their own files (`config.json` keeps `ai_ask_on_step_end` for now, since moving it would change every round's config hash).

## Shared rules and extension points

Human input is continuous movement plus nearby actions; agent input is higher-level action selection. Both share movement speed, contact, access sides, preparation times and item constraints. Working chefs cannot be pushed away; pans and pots heat only while on a stove.

Maps are validated by `map_definition.py`. Recipe legality and some processing conditions remain in Python; the roadmap moves them into validated data before introducing map and recipe editors. Visual ingredient layers are independent from legality.

Future benchmark work will define a complete-session scenario schema, partner/configuration conditions and comparison methods with the community. Record input language and build identity alongside results; receipt of a message or memory is observable, while understanding or causal adaptation requires an appropriate comparison.

---

## 中文说明

# Agent 接入

Cocos 提供画面与玩家输入，Python 维护权威厨房状态。Agent 选择动作，由引擎校验并执行。

## 决策链路

`SpatialKitchen.snapshot()` 与 `actions('jeff')` → client `payload(state, actions)` → 异步 `ask(payload)` → `DecisionLoop` 校验 → `kitchen.start()` → 移动／加工 → 完成事件。

角色 ID 使用 `human` 和 `jeff`。TypeSafe 的 provider ID `jev`、模型名及 `jev.py` 适配器名称保留。旧本地记忆读取时转换角色字段，模型身份与历史文件保持原样。

分别记录请求、选择、动作接受和 `action_done`；请求在途时，原本合法的选择也可能过期。

## 兼容服务

在设置中选择兼容 Chat Completions 服务，填写自己的 HTTPS Base URL、模型与 Key。`CompatibleClient` 发送结构化状态、规则与候选动作，返回 JSON，例如：

```json
{"choice": "wash", "sprint": false}
```

`choice` 必须位于当前 `questions.next_action.criteria`；只有提供 `wash` 候选时才能选择它。请求包含冲刺问题时，`sprint` 为布尔值。

## 新增适配器

Jeff 的输入在 `harness.py` 中拼装：`harness.payload` 生成厨房状态、规则说明和可选动作，`harness.compose` 再加入最近事件与选择、玩家消息和记忆。参考 `player_api.py` 中的 `CompatibleClient`，它继承 `whitebox_server.py` 的 `SpatialJevClient`：

- `payload(state, actions)` 返回 harness 生成的输入，只添加适配器自己的字段（如 `model`），不改变游戏。
- `ask(payload)` 返回含 `choice` 的字典，遵循现有 `sprint`、`model`、`usage`、`latency` 字段约定。
- 在 `create_client(config, setting)` 增加明确分支，同步设置校验与界面选项。
- 用离线替身覆盖非法选择、过期回复、超时、额度和恢复，CI 不使用真实密钥。

托管版使用 `BrowserRelay` 与 `hosted/browser-agent.js`，需要另外接入浏览器供应商适配。中继仅接收校验后的动作、冲刺值和数值用量，不接收供应商凭据。

## Jeff 的计划（计划题）

计划开关打开后，在没有计划时发出的请求会多出 `questions.plan_step_1` 到 `plan_step_4`，类型为 `choice`，选项是本关的工序（`harness.work_items`：取、切、下锅、装盘某种食材，拿干净盘子，出餐，收脏盘，洗盘子），从第 2 步起多一个 `none`，表示计划到此为止。有计划时，请求在 `state.jeff_plan` 里给出这份计划（每一步是否已做完），并改问 `questions.plan_keep`（`keep` 或 `drop`）。适配器把选中的键和动作一起返回：对话模型在同一个 JSON 里写 `"plan_step_1": "<键>"` 等字段（只有问到计划题时，系统提示才加上 `harness.PLAN_CHAT_RULE`），决策模型在 `answers` 里逐题以选择题形式回答。把这些回答交给 `harness.plan_answer(answers, payload)`：没有问到时返回 `{}`，问步骤时返回 `{"plan": {"steps": [...]}}`（遇到 `none` 或不在选项里的键就停），问去留时返回 `{"plan": {"keep": True、False 或 None}}`。`DecisionLoop` 只采用未过期回复里的计划，计划回答有误也不会拒绝动作。Jeff 每做完一个对应工序的动作（`harness.work_item`），计划里那一步就打勾，不要求顺序。计划没有时限，全部做完、Jeff 回答 `drop`，或玩家发来新的偏好时结束，下一次请求会像一步做完时那样马上发出，问新的计划。托管版在 `hosted/browser-agent.js` 里做同样的处理，回答随结果放在 `plan` 里发回。

两步打算是一种试验中的计划模式（`mode` 为 `rolling`，规则版本 `rolling-v3`，默认关闭）。每次请求都问 `questions.plan_step_1`（对 `next_action` 的备注：选的动作所做的、或为之去做的那道工序）和 `plan_step_2`（之后打算做的下一道，或 `none`），选项同样是本关的工序，从不问 `plan_keep`。最新的有效回答当作历史记录给出，而不是计划：附在 `state.recent_decisions` 里记下它的那条决定上，字段名 `intent`，按上面的方式打勾，规则说明是 `state.rules.intent` = `harness.ROLLING_RULE`，不再有 `state.jeff_plan`。新的有效回答替换旧的，没有回答就保留旧的。灶上锅里的食物离糊不到 `harness.ROLLING_YIELD_SECONDS`（8）个游戏秒时，这次请求不给出打算（两道题照常问），等没有锅这么接近糊了再给出。（`rolling-v1` 放在 `state.jeff_plan`，`rolling-v2` 当作历史记录但没有这条例外；锅快糊时，只要给他看打算，他都会照着做。）回答的读取方式和上面完全相同（`harness.plan_answer`），客户端不用改。`ai_ask_on_step_end` 打开时，订单或锅的倒计时跨档，即使 Jeff 这一步会在回复到达前结束，也会马上问（四步计划和关闭计划时仍等这一步做完）。

一键操作已经正式上线（`one_press.py`，版本 `one-press-v3`）：`features.json` 里 `one_press` 是打开的，页面上没有它的开关，要回退就在那里关掉再重启。（此前是两个试验开关 `put_then_take` 和 `wash_from_returns`，用 `POST /api/one-press` 设置，这个接口已经去掉。）打开时，`next_action` 里可能多出 `put then take <工位>`（Jeff 手里拿着东西，另一个工位上放着他空手就能拿的东西，而且除了走路和抛掷，没有别的选项在那个工位上；这时那个工位的 `go <工位>` 会像有别的动作在那里时一样去掉），同一个开关下还有 `put then chop <菜板>` 和 `put then wash <水槽>`（条件相同，换成切菜板上的食材、洗水槽里的脏盘子，引擎只在空手时列出这两种动作；说明里写着还要切或洗几秒，和引擎自己的切、洗说明一样；`one-press-v1` 没有这两种，`one-press-v2` 没写秒数），以及 `wash from <回收口>`（回收口上有脏盘子，水槽空着、没着火、也没被另一位厨师占着）。只要列出了这类选项而 Jeff 手里拿着东西，请求就多一道 `questions.put_where`，类型为 `choice`，选项就是 `next_action` 里已有的放置选项（`put …` 和 `drop`，键和说明都相同），只在 `next_action` 选了这类选项时才用。`state.rules.one_press`（`one_press.RULE`）和 `state.one_press_version` 说明这一点。`put_where` 的回答方式和计划问题相同：决策模型当作一道 `choice` 题，对话模型在 JSON 里加 `"put_where": "<键>"`（`harness.PUT_WHERE_CHAT_RULE`），浏览器中转放在 `plan` 里；由 `harness.choice_answer` 读取，没有回答或回答不在选项里时，用第一个列出的放置位置（记为 `fallback`）。之后决策循环把这几步当作普通动作依次开始：每一步轮到时再检查，做不了就结束整串（`one_press_end`，原因 `step_not_possible`），他另选并执行了别的动作就替换它（`replaced`）；进行中倒计时跨档也会马上问他。

## 功能开关（`features.json`）

会改变 Jeff 被问什么、或他的回答怎么执行的功能，都在一个文件 `features.json` 里开关，服务启动时由 `features.py` 检查（名字、阶段、取值或版本写错，服务就不启动）。每个功能有一个阶段 `stage`：`release`（已上线）默认打开，除非文件里写 `"on": false`，页面上没有它的开关，所以关掉再重启就是回退；`trial`（测试中）默认关闭，除非写 `"on": true`，写了 `"player_switch": true` 的会在「设置 → AI 搭档」里显示成（测试）开关，`on` 是它的默认值。`version` 必须是代码实现的版本：这个文件只管开关，要退回旧版本仍然要回退代码。目前 `one_press` 已上线，两种计划模式 `jeff_plan`（`choice`）和 `rolling_intent`（`rolling`）在测试中，一次只能开一种；`communication.jeff_plan.available` 列出页面提供哪几种。`undo_note` 也在测试中，页面上没有它的开关：打开后，如果某个选项正好会把 Jeff 上一步放下的东西拿回来，或者把他上一步拿起的东西放回原处，这个选项后面会附一句带时间的事实说明（`undo_note.py`，玩家看不到）；每次请求的研究记录会存下这一步，以便原样重建。`scripts/undo_note_check.py` 拿记录里的时刻，加说明和不加说明各问一遍模型做对比。`compact_input` 也在测试中，页面上没有它的开关（版本 `compact-v1`，`wire_format.py`）：打开后，每个客户端把同一个请求分成两部分发出。一部分是整局不变的（`static`：除 `player_communication` 外的全部规则、厨房里地图、菜单、时长这类固定字段、每个工位的固定属性、厨师冲刺的常数、跨局记忆、各版本字段和一张字段默认值表），另一部分是其余内容（`live`：会变的厨房字段、去掉默认值字段的工位和厨师（空闲的工位整个省略）、最近事件和决定、玩家消息、Jeff 的计划）。对话模型把 `static` 放在 system 消息里固定指令的后面，`live` 和问题放在 user 消息里（智谱的 JSON Schema 带着每次不同的选项，放在最后）；决策服务收到的 `state` 是 `{static, live}`；在线页面随每个请求收到这两部分（`wire`），只负责摆放，并把浏览器自己保存的跨局记忆加进 `static`。同一局里 `static` 逐字节相同，服务商可以把它当作提示前缀缓存起来；`live` 大约只有今天整条消息的五分之一到四分之一。请求本身不变：日志、研究记录（`payload_sha256`）、回放和各个分析脚本看到的都是同一个请求，`wire_format.expand(static, live)` 能原样还原出它的 state；开关关闭时，每个客户端发出的字节和今天完全一样。服务商报告缓存命中时，本地对话客户端会记下 `cached_input_tokens`。每局的开局记录和研究记录都带上当时的开关（`features`：每个功能的 `on` 和 `version`）。游戏规则、关卡、玩家偏好和请求间隔这类数值仍在各自的文件里（`ai_ask_on_step_end` 暂时留在 `config.json`，因为搬走会改变每局的配置指纹）。

## 共用规则与扩展点

人类持续移动并执行就近动作，agent 选择较高层动作。双方共用移动速度、碰撞、操作侧、加工时间与物品约束。工作中的厨师不会被推离；锅仅在灶台上加热。

地图由 `map_definition.py` 校验。菜谱合法性与部分加工条件仍在 Python 中，路线图是先转为可校验数据，再接地图与菜谱编辑器。视觉配料叠层独立于合法性判断。

未来与社区共同定义完整对局 scenario schema、搭档／配置条件及对照方法。结果需记录输入语言和构建标识；消息或记忆送达可以直接观察，理解与因果适应需要相应对照。
