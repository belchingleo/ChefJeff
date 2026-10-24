# 公测研究数据接口 v2

实现位置：`session_record.py` 是唯一事件流；`research_record.py` 是托管写入前的安全投影及读取器；`hosted_records.pilot_record()` 从该流导出。没有新增第二套引擎事件队列，没有更改厨房规则、地图、候选动作或模型策略。仅为日志增加的观察钩子不修改引擎 revision / engine_seq。

本版本为源码与合成验证交付，尚未部署或验证真人使用。它记录事实，不计算角色、意图、信任、注意力、合作质量或合作得分。预设偏好/纠正按钮不纳入新研究记录，也不在本任务中修改其玩法。

## 核对表

| 部分 | 原有能力 | 本次补齐 | 仍未知或不采集 |
|---|---|---|---|
| 事实 | SessionLog、统一 seq、双时钟、动作和决策关联 | 托管允许清单投影、浏览器命令接收/返回、结构化动作、关联缺失说明 | 物理按键输入、模型内在意图 |
| 状态 | 冻结 resolved-config，本地首尾快照 | 安全游戏配置、同意后的周期/事件状态、可读取增量 | 每帧轨迹、确定性回放 |
| 物品 | 引擎物品、订单、动作、handoff 编号 | 投影保留关联，装盘/拼盘输入输出关系 | 未经引擎匹配的食材→订单归属 |
| 结束 | aborted / 引擎结束 | 游戏条件与会话关闭分开，明确实际观测来源 | 崩溃、断网背后的玩家原因 |
| 保存 | 自愿贡献、私有 SQLite、30 天、删除凭证 | 新同意、逐局开局前确认、提前结束保存、本人下载 | 跨设备身份、跨页面玩家追踪 |
| 研究出口 | v1 简略记录 | 只读 CLI、版本化私有包、schema/关联/摘要校验 | 无数据库核对时的来源真实性 |

## 同意与记录范围

新记录 `chefjeff-pilot-session-v2`，同意版本 `pilot-session-2026-10-v4`。旧版自动贡献选项失效，必须展示新范围并主动选择。可选浏览器耗时/错误测量另有默认未勾选的复选框，不影响游玩。

选择自动贡献后，浏览器在**每一局** start / restart / next 前向服务器发送同意并等待确认；服务器只将这次声明用于下一次开局。开局创建一条有删除凭证的私有记录；正常结束、手动结束、重开、页面关闭请求、闲置回收、服务器正常关闭时更新同一行。凭证经开局响应和本厨房状态返回并保存在浏览器。

未同意的厨房不落盘，不新增连续局面历史；保留既有统一事实与首尾状态供当前页面游玩/预览。事后“贡献本局”只能保存这些已有资料，`state_history=initial_final_only_no_prestart_consent`、`complete=false`，缺失不能回填。中途关闭自动贡献会删除本局已创建的私有记录并停止新增过程状态和可选测量；不会删除已经结束的旧局，旧局使用各自凭证删除。记录一旦删除/过期，后续结束回调不会将其复活。

突然杀进程、断电时无法保证更新到最后一刻：可能只留下开局记录，`ended_at=null`、关闭未确认、完整性为 false。正常关店的 game_condition 先确定，session_close 可以暂时为 null；随后收到下一关/重开/关闭请求才追加 context_closed 并更新同一行。没有后台逐帧落盘或退出时必须成功的浏览器上传。浏览器 8 秒没有活动时只记录服务端自动暂停；10 分钟无请求后的回收记 `idle_timeout`，不声称观察到了玩家主动退出。

## 状态策略、容量与开销

- 开局首个完整检查点；结束时保留最终可用检查点。新增过程状态仅在开局前已同意时采集。
- 每 1000 **游戏毫秒**采样（引擎 tick 50 ms）；期间发生关键引擎事件或外层输入完成时也观察状态。暂停不推进游戏采样时钟，事件仍保留服务端单调时钟。
- 每 10000 游戏毫秒保存完整检查点，其间保存变化。`state_delta.payload.state` 中 `chefs` / `stations` 按 ID 合并，只发送有变化的实体；其他出现的顶层部分整体替换，未出现的部分保持不变。地图固定于本局，厨师/工位 ID 不在局内删除。`restored_states()` 实现读取。
- `seq` 同时编号事实和状态记录；事件 `state_before_seq/state_after_seq` 引用已存在的可读状态观察。**事件发出时的观察不是整个操作的事务边界**；外层调用结束的状态补充收尾变化。不能把两个采样之间没有事件当作“没有变化”。未同意连续采集时，这些事件状态关联为 null。
- 单局最多 24000 条、12 MB 保守计费的内存记录预算，其中预留 2 MB 和 4 条给结束资料。计费含每条额外 256 字节余量。达到预算后，统一序号继续递增，记录 `dropped/loss_ranges/truncated`，不删改已记录事实或悄悄缩减字段；终局资料若也无法容纳，保留 null 最终状态引用并标记丢失。投影失败单独计数，不保存原异常字符串。
- SQLite 单条紧凑 JSON 上限 13 MB；总有效 JSON 内容默认 256 MB、最多 1000 条。容量不足时拒绝保存/更新并提示，已有行保留上一版，不假称完整成功。JSON 使用逐实体增量减小重复；研究包按配置/事件/元数据分文件并压缩，CLI 逐条处理，不一次加载整个数据库。
- 新增事实记录不调用模型，不做模型摘要。仅可选采集浏览器自报的耗时/受控错误，不改变直连/转发选择。

在完整源码仓库中复现开销：`python3 scripts/benchmark_research.py`；高频输入：`python3 scripts/benchmark_research.py --dense-inputs`。只用测试中的合成轨迹驱动真实引擎，**不会调用 API，也不是产品里的脚本队友**。结果见 `docs/research-benchmark.json`；常规三关记录约 0.64/0.82/0.81 MB、跟踪峰值 4.4–5.4 MB；每秒 20 次输入的三关约 6.32/6.55/6.53 MB、峰值 23.7–24.9 MB，六种轨迹均无丢失。计时区分不带内存跟踪的 elapsed 时间与 tracemalloc 开销；同一共享环境上运行，不能当作隔离 CPU 基准，内存是该测量段的 Python 跟踪峰值，不是整个服务器 RSS。测量不证明线上负载、浏览器体验或模型协作效果。

## 玩家接口

均为同源 JSON POST。游戏相关接口沿用 `X-ChefJeff-Session`、本局 `game_id` 和去重用 `request_id`，其他厨房不可读。凭证接口只允许该凭证对应的单份记录，不列出其他玩家数据。完整类型见 `schemas/research-api.schema.json` 的 `$defs`，原有模型结果接口仍使用受控字段，不接收任意元数据。

| 路径 | 请求/响应 | 说明 |
|---|---|---|
| `/api/contribution/consent` | `consent_request` → `consent_response` | 本版明确同意、可选测量；false 停止当前未结束局的保存与新增测量 |
| `/api/contribution/preview` | `preview_request` → `preview_response` | 本局时点快照；首局未开始时返回 409；与保存共用 `pilot_record()`，仅后续实际发生的事实和同意模式会变化 |
| `/api/contribution/save` | `save_request` → `save_response` | 仅已结束局；本版明确同意；幂等返回同一凭证 |
| `/api/contribution/download` | `credential_request` → `record` | 凭证正确且未过期才返回；原有 v1 仍返回原版本；页面按钮下载最近一局，可用接口逐份下载 |
| `/api/contribution/delete` | `credential_request` → `delete_response` | 删除同一行的全部内容；错误凭证不泄露记录 |
| `/api/model/result` | 原字段加可选 `telemetry` | 严格 `duration_ms,error_type`；未经该局可选同意拒绝；标为 client-reported |

反向代理对私有 JSON 响应关闭 buffering/temp-file，下载沿用删除接口的限流级别；不记录请求/响应体和访问日志。删除/下载凭证只在响应和请求处理中使用，研究包不含凭证或凭证哈希。

## 私有研究 CLI

只读打开指定 SQLite，`mode=ro` + `query_only`；不创建数据库、不清理源记录、不新增公开 HTTP 研究接口。按记录逐条读取/释放读锁；期间发生变化的数据库不是全库原子快照，每份导出来源摘要在 manifest 中固定。

```sh
python3 scripts/research_export.py --database /var/lib/chefjeff/contributions.sqlite3 list
python3 scripts/research_export.py --database /var/lib/chefjeff/contributions.sqlite3 --schema chefjeff-pilot-session-v2 --level 2 --since 2026-10-23T00:00:00Z export --output /private/research/oct23.cjresearch.zip
python3 scripts/research_export.py verify --output /private/research/oct23.cjresearch.zip
python3 scripts/research_export.py --database /var/lib/chefjeff/contributions.sqlite3 verify --output /private/research/oct23.cjresearch.zip
```

时间筛选为含时区 ISO 8601，since 含起点、until 不含终点；无采集日期的 v1 不满足日期筛选，不能用导出日期代替。list 默认只列有效且未过期的贡献，显示版本/关卡/质量，不输出事件、凭证、URL 或身份信息。

包格式 `chefjeff-research-package-v1`：`manifest.json`；每条随机记录的不可逆路径引用目录中有 `metadata.json`、`resolved-config.json`、`events.jsonl`。状态就在统一 events 中，通过 seq 引用，没有另一份可漂移的事件流；研究者可另行派生状态视图。旧记录原样放 `legacy-v1.json` 与 `quality.json`，缺失标为 `not_collected`，不变造 v2、不补“未发生”。文件引用、字节数与 SHA256 由 manifest 列出；metadata、record、event、API、manifest 均有 JSON Schema。合成实例为 `tests/fixtures/research-v2-short.json`。

`verify` 检查 schema、摘要、状态引用、序号/同一时钟、过期。仅有自述摘要不能认证来源；manifest 明确 `authenticated=false`。同时指定源数据库时还核对记录仍有效且内容摘要一致，撤回/过期/更新会令旧包验证失败。研究标注应单独保存，使用 round_id / seq / action_id 等连接，不能写回事实记录。

## 字段字典、单位与信任

所有允许的字段、枚举、必填/可空规则以六份 `research-*.schema.json` 为准；现有游戏配置字段继续引用 `resolved.schema.json` 及它引用的游戏 schema。`research-event` 必填所有关联槽，未知为 null，默认由逐局的 `relation_missing_default=not_emitted` 说明，逐事件 `missing_relations` 仅记录覆盖该默认值的特殊原因，避免重复写入同一说明：`not_emitted` 表示来源没有提供该关联（也可能不适用），`join_via_action_id` 表示需经动作连接请求，`pending_handoff` 表示抛出时尚不知道真实接收者。不允许从相邻时间、相近位置或菜品类型猜测关联。

| 字段 | 单位/含义 | 来源与限制 |
|---|---|---|
| round_id | 随机 32 位 hex，本局 ID | 服务端；重开/下一关更新，无玩家身份 |
| seq / engine_seq | 会话序号 / 原引擎事件序号 | 服务端；相同时刻按 seq 排序；日志专用加工钩子没有 engine_seq |
| actor_id / receiver_id | human / jeff / null | 引擎角色，非真实身份；抛出意向不等于实际接收 |
| action_id / request_id / input_id | 动作 / 模型请求 / 服务器观察到的浏览器输入编号 | 通过对应记录连接；不使用浏览器任意请求字符串充当身份 |
| item_id / station_id / order_id / handoff_id | 原引擎对象或交接 ID | 输入输出加工关系见 payload 的 input_item_ids/output_item_ids，不能假设新对象永不换 ID；同 ID 的加工也可能构造新 Food |
| type / source | 受控事件类型 / engine 或 session | engine 为引擎事实或不改变引擎序号的生命周期钩子；session 为接口/记录器观察 |
| game_time_ms | 自开局游戏毫秒 | 引擎；暂停不前进 |
| elapsed_wall_ms / clock_id | 自日志创建起服务端单调毫秒 / server_monotonic | 所有服务端事件同一时钟；是入流/同步观测时点，初始化时已存在的 game_time=0 事件不声称追溯到了开局前真实墙钟；不是客户端或服务商时间 |
| state_before_seq / state_after_seq | 已保存状态观察的 seq | 并非帧级/事务级重建；非采集或未知时 null |
| payload.action / choice / action_catalog.actions | key、verb、引擎 kind、target、target_source | 动作目标优先来自实际 Action；没有时明确 not_collected，不从字符串补猜 |
| payload.stage | model_request、model_choice_and_application、engine_input_return、input_report、server_received、server_command_result | 区分模型选择、接口返回和实际动作执行；accepted 不等于完成 |
| payload.call / accepted / source_time_game_ms | 外层引擎调用、返回是否接受、调用起点游戏毫秒 | advance 仅进入状态采样，不逐 tick 输出；无布尔返回的调用 accepted=null |
| payload.command / raw_device_input | 服务器观察到的浏览器命令类型 / not_collected | 未获得真实设备按键；HTTP 请求被拒绝不等于引擎已接受 |
| payload.reason / reason_detail | 受控拒绝/中断/纠正类别 | 不保存错误原文；stop_called 不推断为何停止，arrival_state_changed 不推断争抢 |
| payload.fresh / applied / accepted_engine_seq | 处理时新鲜性 / 是否应用 / 当时引擎序号 | 服务器执行检查；动作是否完成仍需 action_done |
| payload.candidates / observed_state_seq / state_ref | 实际候选键 / 观察时引擎序号 / 可用状态记录引用 | 候选键引用同一流中的 action_catalog；首次出现的动作描述仅记录一次，后续复用，避免每次请求重复整张动作表。state_ref 不代表完整原始模型 payload；未采集过程状态时为 null |
| payload.server_round_trip_ms | 服务端等待浏览器任务往返的毫秒 | 不能称纯推理耗时，含浏览器轮询/网络 |
| payload.server_transport_started_wall_ms / server_received_wall_ms | 服务端调用工作线程开始 / 返回的 elapsed_wall_ms | 未暴露则 null；动作接受有独立引擎事件时刻 |
| client_telemetry.duration_ms / error_type | 客户端自报毫秒 / timeout 或 transport_or_response_error | 额外同意、可关闭、浏览器 performance.now 同一单调时钟、严格验证；超出 0–120000 ms 时不报送而非截断成合法值；仍可伪造；不与服务端时间相减 |
| payload.usage / usage_source / provider_verified | 报告的 input_tokens/output_tokens / client-reported / false | 成功响应报告，不是精确账单或验证过的服务商身份 |
| payload.base_state_seq / trigger / state | 增量基底 / 触发 / 可读状态 | checkpoint 为完整状态；delta 合并规则见上文 |
| state.chefs | 位置、location、hand、action_id、action、working、travel_remaining、work_remaining、manual | 位置为引擎格单位；剩余 travel/work 为游戏秒；working 不表示主观注意力 |
| state.stations | food、used_by、pot_id、heating、fire、fire_heat、fire_strength、workers | fire_heat 为引擎累积量；fire_strength 为引擎强度，均无心理含义 |
| state.*.food / hand / contents | id、stage、ingredient、components、plate_id、chopped、heated、washed、contents | 工作/加热量为游戏秒；contents 可嵌套；工具的默认 ingredient 不代表可食用内容 |
| state.ground / projectiles / dining | 地面物、飞行物、用餐盘及归还时间 | position/from/to 为引擎格；started/lands_at/returns_at 为游戏秒；handoff_id 连接实际交接 |
| state.orders | id、dish、arrival、deadline、status | 时刻为游戏秒；保留实际订单规则及计划，pending/served/expired/unresolved_at_close 与 future 分开 |
| resolved_config / config_hash / config_projection_hash | 白名单游戏配置 / 原引擎配置摘要 / 实际安全投影摘要 | 排除运行时 overrides 和未声明 params；实际规则已在强类型配置中展开。原 hash 不用于宣称安全投影逐字等于原包 |
| conditions.* | 规则/输入版本、接口、请求间隔/超时/年龄/调用上限、记忆条件、可选测量状态 | memory 是 browser-reported；不存内容、接口 URL、自定义模型名；model_parameters 的 sampling/reasoning/safety/upstream_adapter 明确为 null（not_collected_from_browser），不把默认值当成真实参数；model_identity=null，未验证/未采集 |
| termination.game_condition | round_limit / fire_loss / none_observed / in_progress | 与 aborted、won、会话关闭原因分开；达到目标本游戏不会自动关店，不虚构 goal 结束 |
| termination.session_close | reason + source=server，可为 null | 只写系统观察到的手动/重开/下一关/关闭请求/回收/正常关服/异常；null 不填“主动退出” |
| termination.last_game_time_ms / last_event_seq / final_state_seq / confirmed | 终点游戏时间、最终序号、可用终局状态、关闭是否确认 | 未确认的开局保留记录不冒充完整局 |
| quality.* | 范围、丢失数/范围、未投影数、异常数、采样/触发/预算、实际最大状态间隔 observed_max_state_gap_game_ms、state_history、missing、complete | complete 只针对本白名单范围且需完整同意下关闭、无丢失/投影异常；不代表回放/所有体验完整 |
| started_at / ended_at / source_expires_at | 服务端 ISO 8601 UTC | 同一记录时间，未关闭 ended_at=null；不是玩家设备时间 |
| manifest.* | 文件摘要、来源摘要、最早源到期时间、格式版本 | 自述完整性信息；源数据库核对前非来源认证 |

## 删除、兼容与部署

### 空动作关联与保存校验

AI 选择 wait / continue，或回复过时未应用时，`action_id` 可以为 null，表示没有本次新建的执行动作。此字段仍归入事件信封，不得残留在 payload。旧实现曾因此在结束保存时被严格 schema 拒绝，只留下开局预存行；修复保留 null 的真实含义，不放宽 payload 允许清单，不伪造动作关联。HTTP 回归覆盖真实浏览器 relay 返回、调度器处理、手动结束或关页、SQLite 更新及本人凭证下载。

历史上仅存开局的行仍保持 `complete=false`，不能补造缺失事件。已经关闭并释放的内存会话没有可供恢复的过程；此修复用于后续保存，不声称修复历史记录。

研究数据（配置、事实、状态、条件、质量）只保存在贡献 SQLite 的同一行，不生成服务器状态分块、持久派生视图或额外索引文件。删除/到期清理该行即删除本版本的全部服务器研究内容；沿用 SQLite secure_delete。没有研究数据备份。到期删除由原有后台清理执行；读取/更新还会拒绝过期行。应用层删除不承诺物理介质上的取证擦除。

CLI 私有导出是管理员明确创建的外部副本，临时文件 0600 且 finally 清理，输出文件 0600，新增父目录 0700。它们**不由游戏服务器自动追踪/删除**：不得放进网站根目录、Git、公开例子或备份；保留至 manifest 最早源到期时间前，玩家撤回任何包含记录时删除整包和所有人工派生/标注副本。每次使用前用源数据库 verify；运维需将导出目录纳入到期清理和撤回流程。未配置该流程之前不要在生产创建持久研究包。导出的 SHA 不是匿名玩家追踪 ID，而是单份随机记录的校验引用。

旧 v1 行保持原样只读；原有 15 局不进入测试或仓库。代码回滚不修改它们，新 v2 行也不降格。版本不兼容由 schema/consent 识别，不能用新字段默认值填补旧数据。跨局记忆内容、通信偏好、请求文本、原始回复、Key/Authorization/Cookie、账号/IP、端点、私有路径及删除凭证均不进入研究记录。

部署前：审查变更，完成 Python/JS 测试、发布包审计；同时安装运行时代码、schema、浏览器脚本、隐私页面与 Nginx 响应不落临时文件配置。使用现有固定提交+包摘要的部署器，在用户明确授权后执行；本任务不修改服务器权限或 VPN。

回滚：切回上一发布目录、恢复其匹配 Nginx 配置并验证 `nginx -t`，重启服务（会结束当前会话）；保留私有贡献数据库，继续到期/凭证删除服务。旧代码不应将 v2 当 v1 研究资料解释，管理员使用支持 v2 的只读导出器。新同意版选择在旧版本上失配并重新询问；不因回滚自动扩展同意。

## 本地验证记录（2026-10-23）

- Python 全量：675 项，671 成功、4 项跳过；包含真实 Nginx 1.26.3 的 12 项代理测试，大于 4 MB 的私有研究响应不落临时文件。
- 随后新增 ZIP 重复成员/来源有效性校验，相关研究投影及 CLI 共 16 项再次通过。
- 8 组 JavaScript 回归通过，含开局前同意确认、凭证提前保存、可选测量默认关闭与确认失败阻止自动留存。
- 六条真实引擎的合成完整轨迹（各 180 秒）均无事件丢失，数据量和内存见测量文件；没有付费模型调用。
- 发布包检查了全部新增运行时模块、六份 schema、私有 CLI 和接口文档。敏感标记审计无发现。
- 本轮没有访问生产 15 局，没有线上部署，没有真人试玩验收；不据此作模型协作或研究结论。
