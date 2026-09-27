# 数据驱动内核 v0.1 — 阶段 A 审计与映射

状态：阶段 A 产物（2026-09-27）。只描述当前源码事实、迁移映射与保护网，不改变玩法。
依据：《ChefJeff 数据驱动游戏内核 开发规范 v0.1》《协作规则补充 v0.1》、`continuation-handoff.md`、三关评审 `review.md`、`order-pacing-proposal.md`，以及当前源码（基线提交 `bd473b9`，345 项离线测试通过）。

已确认的用户决策（本轮）：

1. 旧三关合作切菜／洗碗保持 **单人 6 s／4 s，两人 2 倍速**；只把倍率规则改为数据。补充文档中的 10 s 基线暂不采用。
2. Jeff 规则文本中的协作价值措辞 **立即去除**（所有关卡），只保留事实规则与合法动作。
3. Schema 校验方式由实施方决定：见 §9。
4. 整个项目一个 PR，每完成一个阶段推送一次。

---

## 1. 现有字段 → 新契约映射

| 现有位置 | 字段 | 当前值（L1 / L2 / L3） | 新契约归属 |
|---|---|---|---|
| `config.json` | `round_seconds` | 180 / 240 / 360 | Level `round_limit_game_ms` |
| `config.json`/`levels.py` | `order_count`, `order_interval`, `order_patience` | 5,24,90 / 3,30,180 / 5,30,(100 牛排,150 汉堡) | Order（`legacy_finite` 模式：`arrivals[]` 或 count+interval）；`patience_by_recipe` |
| `levels.py` | `order_seed` | L1 无；L2/L3 开局 `SystemRandom` 生成 | Level `seeds.orders`（冻结时必须显式） |
| `spatial_kitchen.py` | `spawn_seed` | 缺省 `None` → 不可复现、未记录 | Level `seeds.spawn`（冻结时必须显式） |
| `config.json` | `target_served`, `target_money`, `max_bad_reviews` | 3,60,2 / 3,120,2 / 5,140,2 | Level `goal`（`legacy_all_gates`） |
| `config.json` | `time_bonus_per_second` | 1 | Level `scoring` |
| `config.json` | `boards`, `pots` | 3,1 / 2,1 / 3,2 | **删除**：由 Map 实例列表推导（当前与地图重复记录） |
| `levels.py` | `pot_count` | 1 / 1 / 3 | Level 初始库存（锅是物品，灶是设备） |
| `config.json`/`levels.py` | `plate_count` | 2 / 2 / 3 | Level 初始库存 |
| `config.json` | `chop_seconds` | 6 | Recipe step `work_units` + Equipment（案板）`work_rate` |
| `config.json` | `wash_seconds` | 4 | 循环资源操作 `wash` 的 `work_units` + Equipment（水槽） |
| `config.json` | `cook_seconds`, `burn_after_ready`, `fire_after_burn` | 12,10,8 | Equipment（灶）热过程规则 + Recipe（牛肉热阈值） |
| `config.json` | `handling_seconds` | 0.15 | Ruleset 操作注册表（取／放／装盘／出餐的默认耗时） |
| `config.json` | `dining_seconds` | 8 | Ruleset 餐盘循环 |
| `config.json` | `fire_spread_seconds`, `fire_loss_threshold` | 8, 5 | Ruleset 火灾规则 |
| `config.json` | `same_area_walk`, `cross_area_walk` | 1, 3 | 仅非空间文字原型使用；Ruleset `abstract_travel`（空间厨房不用） |
| `kitchen.py::start` | 灭火 4 s、清锅 2 s | 字面量 | Ruleset 操作注册表 |
| `kitchen.py::_finish` | 牛排 30、汉堡 60、错餐 −15、超时 −10、起火 −5、丢弃 −2 | 字面量 | Recipe `price`；Ruleset `penalties` |
| `spatial_kitchen.py` 模块常量 | 步行 4.5 格/s、抛掷射程 7、速度 12、冲刺 1.4×/1 s/冷却 3 s、碰撞半径 0.4、推挤 0.25 | 常量 | Ruleset `movement`／`throw` |
| `config.json` | `ai_*`, `model` | — | **不属于游戏配置**：agent 绑定（开局时绑定，不进 Resolved Configuration 的规则部分） |
| `web_server.py` | `speed` 0.5/0.75/1（界面选择，默认 0.75） | — | Level `clock.wall_per_game`（候选值由配置声明；实际值记入 Session） |

## 2. 按关卡编号的分支与写死规则（迁移清单）

每一项迁移后由阶段 C 删除分支；删除前以行为指纹证明等价。

| 位置 | 当前行为 | 目标 |
|---|---|---|
| `levels.py::level_config` | `if level==2/3` 覆盖参数 | Level 文档 |
| `kitchen.py::__init__` | 固定站点（冰箱、出餐口、垃圾桶、灭火器架、回收、水槽）；固定三柜台 `plates/counter2/counter3`，`plate_count` 限 1–3 | Map 实例 + Equipment 类型；初始库存 |
| `kitchen.py::__init__` | L2/L3 增加生菜/番茄/面包箱；菜单 `['burger']*3` 或 `['steak']*2+['burger']*3` 洗牌；耐心按关卡/菜品 | Map（食材源设备）＋ Order `legacy_finite` |
| `kitchen.py::__init__` | L1 订单 `dish='牛排'`（显示名），L2/L3 用 `'steak'/'burger'`（ID） | 统一使用 recipe ID；显示名由本地化提供（兼容旧日志） |
| `kitchen.py::actions` | `level in (2,3)` 才开放 `assemble`/`merge_plates` | Recipe：存在多组分菜谱即开放 |
| `kitchen.py::actions` | 只有牛肉可入锅、面包不切、只能切 `raw` 非面包 | Recipe step `operation_ref` |
| `kitchen.py::food_name/dish/can_add/merge_plate/can_merge_plates` | 组分集合与合法阶段写死 | Recipe 组分／状态／出餐匹配 |
| `kitchen.py::_finish serve` | L1 不按菜品匹配订单；L2/L3 按菜品 | Order 匹配规则：按 recipe ID（L1 仅一种菜，等价） |
| `kitchen.py::snapshot` | `missing` 仅 L2/L3；汉堡组分写死 | Recipe |
| `spatial_kitchen.py::__init__` | L1 强制 3 板 1 锅；`bin`/`sink` 所属区域按关卡；L3 在 `counter4` 放 P3；L2 出生点规则不同 | Map `areas`、Level 初始库存与 `spawns` |
| `spatial_kitchen.py::can_plate_partner` | `level in (2,3)` 才允许合盘给队友 | Recipe |
| `spatial_kitchen.py::interaction_hint` | 汉堡缺料名写死 | Recipe + 本地化 |
| `whitebox_server.py` | L2/L3 规则文本另写一套 | 规则文本由冻结配置生成 |
| `map_definition.load_map` / `web_server.py` `/api/level` | 只接受 1–3 | Level 注册表 |
| `KitchenClient.ts` | 三个关卡按钮、`layout_version` 正则 `level-[123]`、`level===2` 的招牌与美术试点、订单名 `burger→汉堡` 否则“香煎牛排” | 服务端提供关卡列表与菜谱显示名（v0.1 仅做最小改动，美术试点保留） |
| 设备类型识别 | 由 ID 前缀推断（`b*` 案板、`p*` 灶、`counter*`/`plates` 柜台、`bin*`） | Map 实例 `type_ref` |

## 3. 实际时序与协作速率（迁移时必须保持）

- 游戏时间：`advance(seconds)` 以 **可变** 子步 `dt=min(剩余,0.05,局剩余)` 推进；`web_server.tick` 以现实经过时间 × `speed` 驱动。帧率会影响时间量化 → 阶段 C 改为固定 50 ms 步长累加器（对以 0.05 倍数推进的测试逐位等价）。
- 同一子步内顺序：订单到达 → 餐盘归还 → 加热/烧糊/起火 → 火势蔓延 → 各厨师（`chefs` 字典顺序：human、jeff）移动/开始/加工/完成（胜利立即结束） → 手动移动与抛掷落地 → 订单到期 → 局末/全部订单结束判定。
- 合作加工（切菜、洗碗）：
  - 每位正在该工位工作的厨师在每个子步贡献 `dt` 工作量 → 1 人 1×、2 人 2×（线性），与补充文档 `rate_multiplier {1:1, 2:2}` 一致；上限由“另一条垂直且可达的操作侧”几何决定，实际至多 2 人（厨师数为 2）。
  - 中途加入立即加速，退出后恢复单人速率，进度保留；锁转交给仍在工作的伙伴；完成时双方同时结束（`action_done` 各一条，伙伴消息为“共同完成”）。
  - 可共享的操作种类写死为 `chop`/`wash`；共享操作侧规则（垂直、距离 > 0.4）写死在 `shared_access`。
  - 当前三关：仅 L1 的 b1、b3 有第二（垂直）操作侧，b2 没有；L2/L3 无（**不是缺陷**）；三关均无双人水槽（合作洗碗仅合成布局测试）。
- 抛掷：仅散装 `raw/chopped` 可抛；射程 7、速度 12 格/游戏秒，最短飞行 0.2 s；墙截断、可越设备；空手且未工作的接收者在 0.75 格内可接住；否则落在预留格。

## 4. 订单、目标与结束现状

- 订单全部预生成（`future` 状态），到达 `i*interval`；**无** `fixed_interval_seeded` 模式；超时不补单。
- 胜利判定 `won()`：出餐数、净收入、差评三道门槛同时满足 → **立即结束**；或到局长、或所有订单已结算（`served/expired/rejected`）→ 结束。
- 已确认问题（review §1）：L2/L3 要求全部订单成功，一单超时后已无通关可能仍继续运行，缺少提示。行为指纹 `level2-reference-expiry` 记录了该现状。修复只在新 ruleset 中进行（见开发规范 §8），旧模式先原样迁移。
- 快照向 agent／界面公开 `future_orders`（未来订单**数量**，不含内容）。开发规范要求不泄露未来队列；数量是否可见列为待确认（O-6）。

## 5. 随机性与可复现

- 订单：`random.Random(order_seed).shuffle(menu)`；L1 不使用。
- 出生：`random.Random(spawn_seed).shuffle(spawns)`；**缺省 `spawn_seed=None` 时不可复现且未记录** → 冻结配置必须写入显式 seed。
- 无其他游戏内随机源。模型响应到达时刻取决于现实时间（外部输入），需按接纳的 `game_time`/`seq` 记录。

## 6. 记录现状与缺失采集项

| 现有通道 | 内容 | 缺口 |
|---|---|---|
| `Kitchen.events` | `{t, message(中文), kind, actor?, action?, …}` | 无 `seq`／`game_time_ms`／`action_id`（`job_id` 存在但未写入事件）／`request_id`／`order_id` |
| `play.Journal`（`logs/*.jsonl`） | `start`（整份 config＋快照）、`event`、`ai_request`（完整 payload）、`ai_response`（含当前快照）、`pause/resume`、`end` | 无 `config_hash`／冻结配置；每次响应重复整份快照；无统一 schema 版本 |
| `hosted_records.pilot_record` | 另一套 `chefjeff-pilot-session-v1`：过滤事件＋1 s 位置采样 | 与 Journal 各自为政（开发规范 §13 要求单一事件流派生） |
| `feedback.feedback_report` | 再过滤一次事件 | 同上 |

缺失的协作事实：共享工作的 join/leave 时刻与重叠时长（只能从 `action_start/interrupted/action_done` 推断）；抛接的“发起→飞行→接住/落地/失败”缺 `action_id` 串联；“环境提供共享机会”（`can_share_work` 为真）与“实际加入”无法区分。

## 7. Agent 观察与规则文本

- `jev.JevClient.payload` 与 `whitebox_server.SpatialJevClient` 手写英文规则；时长取自配置，但流程、计分（30/60 元）、组装规则写死，L2/L3 覆盖一段文本。→ 新菜谱不会自动出现在 Jeff 的规则中。
- 协作价值措辞（本轮去除）：`role` “cooperate with chef human”；`objective` “Choose how to cooperate…”；问题说明 “to cooperate with human toward the shared goals”；`partner` 规则中的“coordinating handoffs… you may consider throwing prepared ingredients nearby”；`continuity` 中 “or a handoff”；Chat Completions／浏览器 agent 系统提示 “cooperative kitchen”；记忆说明 “reveal cooperation patterns”。

## 8. 保护网：行为指纹

- `tests/fingerprint.py` 以固定 seed 驱动公开接口 `start/advance`，记录事件、决策、每 5 游戏秒状态投影哈希与终局投影；`tests/golden/*.json` 为已验收行为。
- 策略：`reference`（`tests/reference_policy.py`，只读快照与合法动作，按菜谱做菜／装配／出餐／洗盘，并加入对方已在进行的切菜）、`greedy`、`random`。覆盖：三关全部成功路径、L2 丢单后继续、合作切菜、抛掷／落地、换手、地面物品、起火／蔓延／火势失控、糊锅、清锅、错餐与超时惩罚。
- `tests/test_legacy_fingerprint.py` 在 CI 中逐条比较。**任何阶段只能在有意且经审阅的规则变更时用 `python tests/fingerprint.py --update` 更新。**

## 9. 实施决定（由实施方决定的项）

- **Schema 校验**：保存 JSON Schema（Draft 2020-12）文件作为正式契约；运行时校验用标准库实现所用关键字子集（`type/enum/const/required/properties/additionalProperties/items/minimum/maximum/exclusiveMinimum/minItems/maxItems/pattern/$ref/$defs/oneOf`），测试同时校验“schema 文件本身只使用这些关键字”。保持后端零第三方依赖，也不远程下载 schema。
- **单位**：契约用整数 `*_game_ms`；引擎内部暂保留浮点秒，由 Resolver 在边界换算（v0.1 不重写引擎时间类型）。
- **目录**：`schemas/`（契约）、`content/`（equipment / recipes / orders / levels）、`rulesets/`；地图仍在 `maps/`。Python 模块保持仓库现有的扁平布局。

## 10. Open decisions（无法从源码核实，暂不伪造默认值）

| # | 问题 | 当前处理 |
|---|---|---|
| O-1 | “三分钟”指游戏时间还是有效现实时间 | 新 pilot 前确认；旧三关按游戏秒迁移 |
| O-2 | 新 pilot 的目标、间隔、耐心、停单点（订单节奏提案仅为讨论值） | 不写入默认关 |
| O-3 | 锅与灶关系是否在新设备中改变 | v0.1 保持：锅是可搬物品，灶是加热设备，锅离灶暂停 |
| O-4 | 旧关“全单必成”无提示问题的修复方式 | 旧模式原样迁移；新 ruleset 实现“已无通关可能”提示 |
| O-5 | 协作 10 s 基线 | 用户决定暂不采用；旧关 6 s/4 s |
| O-6 | `future_orders` 数量是否对 agent/玩家可见 | 旧关保持；新模式默认不公开，待确认 |
| O-7 | 模型响应在暂停期间到达的处理 | 现行为：`epoch` 失效，响应作废并记录；原样保留 |

---

## 11. 迁移结果（阶段 A–E 完成后）

| 规范要求 | 实现位置 | 验证 |
|---|---|---|
| 旧三关按原值迁移不变 | `content/`、`rulesets/chefjeff-legacy.json`、地图 schema 2（revision 4，几何不变） | `test_config_contract`（参数与订单表对比迁移前 golden）、`test_legacy_fingerprint`（8 条完整对局轨迹逐事件一致） |
| 不出现按关卡编号的特判 | `rules.py`、`kitchen.py`、`spatial_kitchen.py`、`jev.py`、`whitebox_server.py` | `test_data_driven.test_runtime_code_has_no_level_number_branches` |
| 只改数据即可切换菜谱、设备速率/数量、节奏与协作倍率 | Resolver + `Rules` | `test_data_driven`（价格、切配时长、非线性倍率、中途加入/退出）、`test_capacity_analyzer`（负载随数据变化） |
| 合作切菜/洗碗 6 s／4 s，两人 2 倍速；补充文档的 10 s → 5 s 可纯数据表达 | `content/equipment` 的 `shared_work` | `test_shared_work`、`test_data_driven` |
| Agent 不收到协作价值指令 | `jev.py`、`whitebox_server.py`、`player_api.py`、`hosted/browser-agent.js`（`rules-v2`） | `test_agent_rules_neutral` |
| 规则说明与合法动作来自同一配置 | 快照中的 `menu`、`scoring`、`timing`、`goal_status` | `test_data_driven.test_price_change_reaches_engine_and_agent_rules` |
| 固定步长与确定性 | 服务器 50 ms tick 累加器；显式 seed 冻结 | `test_web.FixedTickTests`、`test_continuous_mode.test_one_large_step_equals_many_small_steps` |
| 新订单模式与独立结束规则 | `rulesets/chefjeff-continuous.json`、未上架试点 `pilot-draft-mixed` | `test_continuous_mode` |
| Capacity Analyzer | `capacity_analyzer.py`、`docs/architecture/reports/` | `test_capacity_analyzer` |
| 单一事件流、Session 记录包、重放 | `session_record.py`、`schemas/session|event.schema.json` | `test_session_record` |

两处有意的可见变化（已在提交说明中记录）：第 1 关订单的 `dish` 由显示名“牛排”改为菜谱 id `steak`；新订单消息使用菜谱显示名（“汉堡”）。

### 仍需确认或后续处理

| # | 状态 |
|---|---|
| O-1 三分钟的时钟口径 | 未决；试点草案仅用游戏毫秒 |
| O-2 新试点的目标、间隔、耐心、停单点 | 未决；`pilot-draft-mixed` 使用提案讨论值并标注“未批准”，未上架 |
| O-3 锅与灶关系 | 维持现状 |
| O-4 旧关“全单必成”无提示 | 旧关行为未改；快照新增 `goal_status` 供界面/分析使用；新 ruleset 已实现明确提示 |
| O-5 协作 10 s 基线 | 不采用；已证明可纯数据表达 |
| O-6 未来订单数量是否可见 | 旧关保持计数；新模式只公开“是否还会来单” |
| O-7 暂停期间到达的模型响应 | 维持现状，记录为 stale |
| 前端 | 预构建 Cocos 客户端未重新构建（需 Creator 3.8.8）；服务端已提供 `levels` 列表，客户端仍显示三个关卡按钮 |
| 文字原型 | 非空间 `Kitchen` 现使用地图上的全部工位（原为抽象的 3 个柜台），与空间版一致 |
