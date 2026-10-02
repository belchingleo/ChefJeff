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

Follow `CompatibleClient` in `player_api.py` and `SpatialJevClient` in `whitebox_server.py`:

- `payload(state, actions)` constructs input without modifying the game.
- `ask(payload)` returns a dictionary with `choice`, following existing `sprint`, `model`, `usage` and `latency` conventions.
- Add an explicit branch in `create_client(config, setting)`, with settings validation and UI choices.
- Use offline test doubles for invalid choices, stale replies, timeouts, budgets and recovery. Keep real keys out of CI.

Hosted play uses `BrowserRelay` plus `hosted/browser-agent.js`; add browser-provider support there separately. The relay only accepts a validated choice, sprint flag and numeric usage, and never receives provider credentials.

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

参考 `player_api.py` 中的 `CompatibleClient` 和 `whitebox_server.py` 中的 `SpatialJevClient`：

- `payload(state, actions)` 构造输入，不改变游戏。
- `ask(payload)` 返回含 `choice` 的字典，遵循现有 `sprint`、`model`、`usage`、`latency` 字段约定。
- 在 `create_client(config, setting)` 增加明确分支，同步设置校验与界面选项。
- 用离线替身覆盖非法选择、过期回复、超时、额度和恢复，CI 不使用真实密钥。

托管版使用 `BrowserRelay` 与 `hosted/browser-agent.js`，需要另外接入浏览器供应商适配。中继仅接收校验后的动作、冲刺值和数值用量，不接收供应商凭据。

## 共用规则与扩展点

人类持续移动并执行就近动作，agent 选择较高层动作。双方共用移动速度、碰撞、操作侧、加工时间与物品约束。工作中的厨师不会被推离；锅仅在灶台上加热。

地图由 `map_definition.py` 校验。菜谱合法性与部分加工条件仍在 Python 中，路线图是先转为可校验数据，再接地图与菜谱编辑器。视觉配料叠层独立于合法性判断。

未来与社区共同定义完整对局 scenario schema、搭档／配置条件及对照方法。结果需记录输入语言和构建标识；消息或记忆送达可以直接观察，理解与因果适应需要相应对照。
