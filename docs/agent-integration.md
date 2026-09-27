# Agent 接入与扩展边界

ChefJeff 当前面向本机单厨房运行。Cocos 是画面和输入端，Python 保存权威游戏状态；模型选择动作，规则引擎判断动作是否仍然合法。

## 决策链路

`SpatialKitchen.snapshot()` 和 `actions('jev')` → client `payload(state, actions)` → 异步 `ask(payload)` → `DecisionLoop` 校验 → `kitchen.start()` → 移动/加工 → 完成事件。

“返回动作”不等于“已经完成”：候选动作在请求后可能过期，操作可能被玩家主动中断，目标物品也可能发生变化。记录中需要区分请求、选择、接受和 `action_done`。

## 接现有兼容服务

在游戏设置中选择兼容 Chat Completions 服务，填写自己的公网 HTTPS Base URL、模型名和 Key。`CompatibleClient` 将结构化厨房状态、规则和动作候选放入消息。响应内容必须是 JSON，例如：

```json
{"choice": "wash", "sprint": false}
```

`choice` 必须来自当次 `questions.next_action.criteria`。只有候选里存在 `wash` 才能选择它；`sprint` 在请求包含对应问题时必须为布尔值。不能让模型根据示例固定返回洗碗。

## 增加新适配器

参考 `player_api.py` 的 `CompatibleClient` 与 `whitebox_server.py` 的 `SpatialJevClient`：

- `payload(state, actions)` 构造请求，不改变规则状态。
- `ask(payload)` 返回字典，至少提供所选 `choice`；沿用现有 `sprint`、`model`、`usage`、`latency` 等字段契约。
- 在 `create_client(config, setting)` 增加明确分支，并同步设置校验及界面选项。
- 用离线替身检查非法选择、过期响应、超时、额度和恢复；不要在 CI 中配置真实 Key。

当前 client 接口是内部 Python 扩展点，不是已经版本化的外部 SDK。TypeSafe 的供应商协议与兼容 Chat Completions 协议分别适配。

## 共用规则与不同输入

人类使用移动键和就近动作，AI 选择高层动作并走向目标。双方共用物品约束、加工时间、碰撞和工位入口，但输入粒度与决策时延不同。操作中的厨师固定站位；普通接触或冲刺不打断加工。锅只在灶上加热，与厨师是否持续站在旁边无关。

## 数据化的真实范围

地图 JSON 由 `map_definition.py` 校验，设备位置、操作侧与表现方向分开定义。地图编辑器尚未交付。菜谱、合法配料与加工条件仍有代码内规则；后续先迁移成可校验数据，再做菜谱编辑器。视觉配料叠层不承担配方合法性判断。

## 后续整局 scenario schema

未来 schema 将描述完整对局的环境、参与者条件、动作与事件时间线、沟通和结果，并支持不同玩家与 AI 的真实合作记录逐步扩充。具体字段、隐私处理和评分协议尚待设计。固定离线回归用例不作为 benchmark 标准；收到记忆或沟通内容，也不等于模型理解了它或因此改变行为。
