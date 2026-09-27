# ChefJeff · Cook Together

English · [中文](#中文说明)

**A prototype for real-time cooperation between a human player and an AI chef.** You operate a pixel-art kitchen while Jeff receives structured kitchen state, rules, and available actions and chooses what to do next. Both chefs share ingredients, workstations, orders, and time, without fixed roles.

The current release is **0.5.9-alpha, a local browser game** with three playable maps and player-provided model credentials. This iteration passed the project maintainer's overall playtest acceptance. It remains an early prototype: interaction, rules, and interfaces need further refinement.

The repository initially stays **private**. Original project code uses [AGPL-3.0-only](LICENSE); see [third-party notices](THIRD_PARTY_NOTICES.md) for dependency and asset information. Temporary assets, development assumptions, and asset licensing still need review before a public release. A private repository is not a completed public-distribution clearance.

## What this project contributes

ChefJeff turns cooperative cooking into an observable, extensible interactive environment. Its current engineering focus is:

- **Shared rules and state.** Human inputs and AI actions ultimately use one kitchen engine for preparation, containers, occupancy, timing, collisions, and action completion.
- **A structured agent interface.** Models receive state, rules, and legal action candidates and return a choice. The environment validates and executes it, distinguishing selection, acceptance, and completion.
- **Data and module boundaries for extensions.** Maps have a data format, validation, and loading path. Kitchen rules, spatial movement, decision scheduling, and rendering are separated to support future map editors, recipe editors, and new agents.
- **A foundation for whole-session records.** Events, actions, bounded cross-round memory, and player communication provide material for describing complete cooperative sessions.

These are prototype contributions, not evidence that a model has acquired cooperative ability or that a general game framework or benchmark is complete.

### How it differs from screen-based Computer Use

| Aspect | Current ChefJeff agent interface | Screen-based Computer Use |
| --- | --- | --- |
| Observation | Structured kitchen, orders, objects, and both chefs' actions | Usually screenshots or interface information |
| Action | Environment actions such as fetching, chopping, washing, and serving | Usually mouse and keyboard interactions |
| Execution | A shared engine validates targets, occupancy, and timing | Depends on feedback from the operated interface |
| Focus | Cooperation in a changing shared task | Perceiving and operating an interface |

The AI does not need to recognize pixels or press keys. Humans retain real-time keyboard and pointer input; the AI uses higher-level actions. Shared rules do **not** mean identical input granularity, information presentation, or decision latency.

## Quick start

Requirements: **Python 3.10+ and a desktop browser**. The backend uses only Python's standard library. The distribution repository and download package include the built web client, so playing does not require Cocos Creator or the maintainer's API key.

Private-repository access is required initially:

```sh
git clone https://github.com/belchingleo/ChefJeff.git
cd ChefJeff
python3 scripts/launch_web.py
```

On Windows:

```powershell
py -3 scripts/launch_web.py
```

Alternatively, use `开始网页版.command` on macOS or `开始网页版.bat` on Windows. Open <http://127.0.0.1:8775/>, go to Settings, enter your own TypeSafe Jev, DeepSeek, or compatible Chat Completions credentials, test the connection, and start. Connection tests and gameplay requests use your account and may incur charges. A failed or missing model connection is not replaced by a scripted teammate.

If macOS blocks double-clicking a script, use the terminal command above; do not weaken system security settings. After ending a round, macOS users can run `python3 scripts/stop_web.py`. On other systems, run `python3 cocos_server.py --port 8775` in the foreground and use Ctrl+C after playing. A port conflict does not cause the launcher to terminate another program.

**An online playable deployment is not available yet.** This implementation needs a Python backend in addition to the web client. GitHub Pages hosts static sites and cannot run that backend. Repository publication and online deployment are separate deliverables. A hosted version needs HTTPS, session isolation, access control, and credential/usage management; do not expose the current local server directly to the Internet.

## Current gameplay

- Three maps: steak, burgers, and a mixed menu, with shared cooking, plate returns, washing, carrying pots, throwing ingredients, serving, and fire handling.
- Direction-aware chopping and workstation poses, layered food presentation, and cooking/burning countdowns. Removing a pot from heat pauses heating; returning it resumes the remaining time.
- Cooperative chopping where two perpendicular workstation sides are accessible. Cooperative washing is implemented and tested in a fixture layout; the three shipped maps do not yet provide a shared sink layout.
- Shared movement and gentle contact rules: edge sliding, gradual pushing, and limited sprint bumps. **Chefs actively working at a station are not displaced or interrupted by collisions.**
- English/Chinese UI, pause/restart, model-call limits, player preference messages, in-round bookmarks, and local feedback export.

### Controls

- WASD / arrow keys to move; click the floor or a workstation to approach it. Double-tap a direction to sprint.
- Tap Space for the nearby action shown in the bottom hint. You can actively cancel processing; chopping and washing progress is retained.
- Hold Space for about 0.3 seconds, then left-click a target to throw an ingredient; release to cancel. Alternatively, right-click to prepare, left-click to throw, and right-click to cancel. Plates, plated dishes, pots, and tools cannot be thrown.
- Use clean plates to serve from pots. Collect dirty plates, place them in the sink, and wash with empty hands. Pots stop heating when removed from the stove.
- Esc pauses. Settings contain model connections, usage limits, language selection, and feedback preview/export.

See [current rules](docs/current-rules.md) for details (Chinese).

## Architecture and agent integration

| Module | Entry points | Responsibility |
| --- | --- | --- |
| Kitchen rules | `kitchen.py` | Items, preparation, containers, orders, cooperation, events |
| Maps and space | `maps/`, `map_definition.py`, `spatial_kitchen.py`, `navigation.py` | Map validation, movement, docking, contact, throwing |
| Decision loop | `jev.py` | Asynchronous requests, response freshness, execution, call budgets |
| Model adapters | `whitebox_server.py`, `player_api.py` | Spatial-state prompts, TypeSafe and Chat Completions protocols |
| Local service | `web_server.py`, `cocos_server.py` | Single-kitchen session, input and state synchronization |
| Rendering | `cocos-kitchen/assets/scripts/` | Cocos Creator 3.8.8, TypeScript, shared geometry, pixel assets |
| Records | `cooperation_memory.py`, `feedback.py` | Bounded cross-round records, communication, inspectable feedback |

Use Settings for an existing compatible service. For a new adapter, implement the existing client contracts `payload(state, actions)` and `ask(payload)` and return results to `DecisionLoop`; do not mutate the kitchen state directly. Choices must come from the current candidate set. Stale or invalid responses are rejected. Failures are reported and retried without substituting a scripted AI.

See [agent integration](docs/agent-integration.md) and [map format](docs/地图数据格式.md) for implementation details (Chinese). These are internal extension points, not a stable external SDK. Jeff is the character name, TypeSafe Jev is a model service, and `jev` remains the internal actor identifier.

## Development and validation

The prebuilt web client is sufficient for playing. Rendering changes require **Cocos Creator 3.8.8**; backend-only changes require a server restart but no Cocos rebuild.

```sh
python3 -m unittest discover -s tests
python3 scripts/audit_release.py
python3 scripts/build_cocos.py web
python3 scripts/package_web.py
```

Set `COCOS_CREATOR` if Creator is installed elsewhere. Geometry execution tests also require Node.js and TypeScript; missing tools cause an explicit skip. The GitHub workflow runs offline checks without paid model calls; Cocos builds are currently manual.

The latest local full suite passed **334 tests**, alongside actual-browser checks and maintainer playtesting. This does not cover every device, model, or long-running session. `scenarios/fixed_entry_001` is a deterministic development regression fixture, not a benchmark standard or evidence of AI ability.

## Privacy and cost

- **No person's API key is included in the repository.** Never put keys in code, issues, commit messages, or screenshots.
- Keys are kept in local backend memory by default. “Remember this device” stores them in a permission-restricted plaintext `.player-api.json`; this is not an OS keychain.
- Local credentials, connection settings, logs, memory, and private debugging material are excluded from publication. A reviewed file allowlist and content scanning are used in addition to `.gitignore`.
- State, rules, communication, and enabled bounded history are sent to the model service you select. Raw logs stay local. Review feedback before sharing it.
- The default budget is 200 model calls per round, including failures; it can be set to 1–2000. Connection tests are counted separately. Call limits are not monetary limits; provider billing applies.

See [privacy and costs](docs/privacy-and-costs.md) and [security](SECURITY.md).

## Roadmap

1. Continue human playtesting and refine feedback, contact, cooperative actions, pacing, and state consistency.
2. Complete map and recipe data contracts, then add editors. Maps are already data-driven; recipe legality and some processing conditions remain in code. A recipe editor is not implemented.
3. Extend agent adapters, communication, and record interfaces for other developers to build on the same environment.
4. Develop a **scenario schema for complete human–AI cooperative game sessions**: describe the environment configuration, participant conditions, interaction process, and outcomes in a consistent structure; expand the collection through different players' participation, then build the benchmark around it.

The fourth item is future research and engineering work. There is no finalized schema, dataset, or scoring protocol yet. Fixed development fixtures remain regression tests, not the unit defining the benchmark. Collecting and sharing real sessions will require separate consent, de-identification, and data-use decisions; private play logs are not published here.

Please report reproducible issues with the version, map, steps, and screenshots stripped of private information. See [CONTRIBUTING](CONTRIBUTING.md).

---

## 中文说明

# ChefJeff · 一起出餐

**一个让人类玩家与 AI 厨师共同完成整局烹饪任务的游戏原型。** 玩家在像素厨房里实时操作，AI 厨师 Jeff 接收结构化的厨房状态、规则和当前可选动作，自行决定下一步。两位厨师共享食材、工位、订单和时间，没有预设的固定分工。

当前为 **0.5.9-alpha，本地浏览器版**：三张地图可玩，支持玩家自己的模型 API。本轮整体试玩已获得项目维护者验收；系统仍处于早期阶段，需要继续调整协作体验、规则和接口。仓库初期保持私有；原创代码的许可选择为 [AGPL-3.0-only](LICENSE)，第三方软件及素材说明见 [授权清单](THIRD_PARTY_NOTICES.md)。公开发布前仍需清理临时资源、开发依赖和素材许可，不将当前仓库当作已完成公开分发审查。

## 项目在做什么

ChefJeff 将合作烹饪做成一个可观察、可扩展的交互环境。工程重点包括：

- **共用规则与状态。** 人类输入和 AI 动作最终进入同一个厨房规则引擎，处理食材加工、容器、占用、计时、碰撞与动作完成。
- **结构化 agent 接口。** 模型获得当前状态、规则和合法动作候选，返回动作选择；环境负责验证与执行，记录“选择、接受、完成”之间的区别。
- **可扩展的数据与模块边界。** 地图已有数据格式、校验和加载入口；厨房规则、空间移动、决策调度和画面呈现分别维护，供后续地图编辑器、菜谱编辑器及新 agent 使用。
- **整局协作记录基础。** 已有事件、动作、有限跨局记忆和玩家沟通记录，为后续整理完整对局提供材料。

这些是当前原型的实现方向与贡献，不代表已经验证了模型的合作能力，也不等于完成了通用游戏框架或 benchmark。

### 与通过屏幕操作的 Computer Use 有什么不同

| 方面 | 本项目当前 agent 接口 | 基于屏幕的 Computer Use 方式 |
| --- | --- | --- |
| 观察 | 结构化的厨房、订单、物品和双方动作状态 | 主要从截图或界面信息理解状态 |
| 行动 | 选择环境提供的动作，例如取料、切菜、洗碗、出餐 | 通常发送鼠标、键盘等界面操作 |
| 执行 | 共用规则引擎校验目标、占用与时序 | 依赖界面的操作反馈 |
| 关注点 | 人与 agent 在持续变化的共同任务中如何协作 | 感知界面与操作界面的能力 |

本项目没有要求 AI 识图或按键。人类保留键盘、点击等实时交互，AI 使用较高层的动作接口；共用规则不表示双方输入粒度、信息呈现或决策延迟完全相同。

## 快速运行

需要 **Python 3.10+ 和桌面浏览器**，后端仅使用 Python 标准库。发布仓库和下载包包含构建好的网页，试玩无需安装 Cocos Creator，也无需填写维护者的密钥。

私有阶段需先获得仓库访问权限。克隆后进入项目目录：

```sh
git clone https://github.com/belchingleo/ChefJeff.git
cd ChefJeff
```

在克隆或解压后的项目根目录运行：

```sh
python3 scripts/launch_web.py
```

Windows 使用：

```powershell
py -3 scripts/launch_web.py
```

也可双击 `开始网页版.command`（macOS）或 `开始网页版.bat`（Windows）。打开 <http://127.0.0.1:8775/>，进入「设置」，填写自己的 TypeSafe Jev、DeepSeek 或兼容 Chat Completions 的 API，测试连接后开局。连接测试与游戏中的模型请求会产生由你的账号承担的费用。没有可用连接时不会用脚本冒充 AI 搭档。

macOS 不允许双击脚本时使用上述终端命令，无需修改系统安全设置。结束对局后可运行 `python3 scripts/stop_web.py` 停止 macOS 后台服务；其他系统可在前台运行 `python3 cocos_server.py --port 8775`，结束游玩后按 Ctrl+C 退出。端口冲突时不会自动关闭其他程序。

**在线试玩尚未部署。** 当前是浏览器前端加本地 Python 后端，GitHub Pages 只能托管静态网页，不能直接运行这个后端。源码公开与公网试玩分开交付；后续在线版需要会话隔离、HTTPS、凭据和调用额度管理。不要把当前本地服务直接暴露到公网。

## 现在可以玩什么

- 三张地图：牛排、汉堡、牛排与汉堡混合；共享厨房、餐具回收、洗碗、搬锅、抛接、出餐与消防。
- 切菜方向和工位站位、食材叠层、锅的熟成/烧糊倒计时；端离灶台暂停加热，放回续算。
- 转角有两个垂直可操作侧时可以合作切菜。合作洗碗规则已实现并用测试布局验证，当前三张地图未新增双人水槽。
- 两位厨师共用移动和温和碰撞规则：贴边滑动、缓慢推挤、冲刺轻撞；**操作中的厨师不会被碰撞挪走或打断**。
- 中文/英文界面、暂停与重开、模型调用次数上限、玩家偏好沟通、局内片段标记和本地反馈导出。

### 基本操作

- WASD / 方向键移动；点击地面或工位走近；双击同一方向键冲刺。
- 短按空格执行就近动作，底部提示显示将做什么；正在加工时可主动取消，切配/洗碗进度保留。
- 长按空格约 0.3 秒，再左键点目标抛原料；松开取消。也可右键准备、左键抛出、右键取消。盘子、成品、锅和工具不能抛。
- 净盘到锅边装盘；脏盘从回收点取回，放水槽后空手洗净。锅端离灶台停止加热。
- Esc 暂停；设置中连接模型、控制调用次数、切换界面语言、查看和导出反馈。

详细说明见 [当前规则](docs/current-rules.md)。

## 技术结构与 agent 接入

| 模块 | 入口 | 职责 |
| --- | --- | --- |
| 厨房规则 | `kitchen.py` | 物品、加工、容器、订单、合作与事件 |
| 地图与空间 | `maps/`、`map_definition.py`、`spatial_kitchen.py`、`navigation.py` | 地图校验、移动、站位、碰撞、抛接 |
| 决策调度 | `jev.py` | 状态请求、异步响应、时效校验、动作执行与调用上限 |
| 模型适配 | `whitebox_server.py`、`player_api.py` | 空间状态提示、TypeSafe 和 Chat Completions 协议 |
| 浏览器服务 | `web_server.py`、`cocos_server.py` | 本地单厨房会话、输入与状态同步 |
| 画面 | `cocos-kitchen/assets/scripts/` | Cocos Creator 3.8.8、TypeScript、共享几何与像素素材 |
| 记录 | `cooperation_memory.py`、`feedback.py` | 有限跨局记录、沟通与可检查的反馈摘要 |

已有兼容接口可直接在设置中接入。开发新的适配器时，实现现有 client 的 `payload(state, actions)` 与 `ask(payload)` 契约，把结果交回 `DecisionLoop`，不要直接修改厨房状态。动作必须来自当前候选集，过期或非法结果会被拒绝；请求失败会提示并重试，不会切换为脚本队友。

具体契约、示例和扩展边界见 [agent 接入与架构](docs/agent-integration.md)、[地图数据格式](docs/地图数据格式.md)。内部角色标识仍为 `jev`；游戏角色名是 Jeff，TypeSafe Jev 是模型服务。

## 开发与验证

直接试玩使用预构建网页；修改画面后需安装 **Cocos Creator 3.8.8** 重新构建。Python 规则修改不需要重建网页，但需要重启本地服务。

```sh
python3 -m unittest discover -s tests
python3 scripts/audit_release.py
python3 scripts/build_cocos.py web
python3 scripts/package_web.py
```

Creator 安装位置不同可设置 `COCOS_CREATOR`。几何执行测试还需要 Node.js 和 TypeScript；缺少工具时会明确跳过相应执行测试。GitHub CI 配置运行离线检查，不调用付费模型。

本轮本地完整测试 334 项通过，并做过真实浏览器检查和维护者试玩。这个结果不代表所有设备、所有模型和所有长局均已验证。`scenarios/fixed_entry_001` 是可复现的开发回归用例，不是 benchmark 标准，也不证明 AI 能力。

## 隐私与费用

- **仓库不附带任何人的 API Key。** 不要把密钥写进源码、Issue、提交信息或截图。
- Key 默认只留在本机后端内存；勾选“记住设备”后保存到本机权限受限的明文文件 `.player-api.json`，它不是系统钥匙串。
- `.env`、本地连接配置、对局日志、跨局记忆和私人调试资料不随项目发布。公开前按明确文件清单导出并扫描，不能只依赖 `.gitignore`。
- 游戏状态、规则、沟通及启用后的有限历史记录会发送给你选择的模型服务；原始日志留在本地。导出反馈前仍应自己检查。
- 默认每局最多 200 次模型调用，失败也计数；可设 1–2000 次。连接测试另计。次数上限不是金额上限，费用以服务商账单为准。

更多说明见 [隐私与调用费用](docs/privacy-and-costs.md)、[安全说明](SECURITY.md)。

## 后续计划

1. 继续真人试玩，完善交互反馈、碰撞、合作操作、节奏和状态一致性。
2. 完善地图与菜谱的数据契约，再提供编辑器。地图已数据化；配方合法性和部分加工条件仍在代码里，菜谱编辑器尚未实现。
3. 扩展 agent 适配、沟通和记录接口，让其他开发者能在同一环境中接入和比较不同协作方法。
4. 建立覆盖**完整人类—AI 合作对局**的 **scenario schema**：以一致结构描述一局的环境配置、参与者条件、交互过程及结果，随着不同玩家参与逐步积累和扩充，再据此发展 benchmark。

第 4 项是后续研究与工程方向，目前尚无定稿的 schema、数据集或评分协议。已有固定开发用例继续服务于回归测试，不作为定义 benchmark 的单位。收集和分享真实对局前，需要另行确定知情同意、去标识化和数据使用范围；本仓库不发布私人对局。

欢迎通过 Issues 提交可复现问题或讨论接口设计，附版本、地图、操作步骤和去除私人信息的截图。贡献方式见 [CONTRIBUTING](CONTRIBUTING.md)。
