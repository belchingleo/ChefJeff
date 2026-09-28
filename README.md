# ChefJeff · Cook Together

![ChefJeff gameplay — human and AI chefs sharing a kitchen](docs/images/gameplay.png)

English · [中文](#中文说明)

**An open-source collaboration project exploring how humans and AI agents work together in real time.**

ChefJeff brings a human player and an AI chef into a shared pixel-art kitchen. Orders arrive, food cooks, dishes pile up, and both partners must coordinate as the situation changes. Jeff observes the kitchen, chooses actions, and works alongside the player without a fixed role.

We are building two things together: **a cooperative game that the community can extend**, and **an open benchmark for studying and comparing agent cooperation through complete game sessions**. The game provides a playable environment; the benchmark will connect session descriptions, interaction records, and evaluation methods contributed by the community.

## Who is ChefJeff for?

| Community | What you can explore or contribute |
| --- | --- |
| Human–AI interaction and collaboration researchers | How agents divide work, respond to a partner, communicate, and recover from coordination failures under time pressure |
| Agent and model developers | Compare models, decision policies, memory, communication, and planning approaches within a shared environment |
| Multi-agent researchers | Develop comparisons across agent teammates, team compositions, and coordination strategies, starting with human–agent play and extending toward agent–agent teams |
| Game developers, designers, and artists | Build maps, recipes, mechanics, interfaces, and assets that create new forms of cooperation |
| Players and community contributors | Play with different agents, report experiences, and help shape the game and future evaluation collection |

## A benchmark built around complete cooperation

The intended evaluation target is **an agent's ability to work with a partner in a changing, real-time environment**. A successful dish is one outcome; the process also matters: when to help, when to take over another task, how to respond to a request, and how to recover when the plan breaks down.

Our planned **scenario schema** describes an entire cooperative session: environment and rule configuration, participant and agent setup, observation and action interfaces, timing and communication, the interaction timeline, and outcomes. Different players, agents, maps, and team configurations can contribute sessions using that common structure.

This supports questions such as:

- How does the same agent cooperate with people who have different play styles?
- How do different agents perform with comparable partner and environment conditions?
- What changes when communication, memory, planning, or response latency changes?
- How do human–agent and agent–agent teams coordinate under shared resource and time constraints?

The community can help define comparison protocols and measures for task outcomes, coordination, adaptation, resource use, and player experience. Interface conditions, model latency, and partner setup belong in those comparisons so their effects remain visible. Fixed map layouts provide useful test conditions; **the complete session and its context form the organizing unit of the benchmark**.

## What you can use today

**0.5.9-alpha** provides a local browser game with three playable maps and player-supplied model connections.

- Steak, burger, and mixed-menu kitchens with preparation, cooking, plating, serving, plate returns, washing, and fire handling.
- Shared workstations, cooperative chopping, ingredient throwing, movable pots, and gentle chef collisions.
- Direction-aware work animations, layered ingredients, and cooking/burning countdowns. Removing a pot from heat pauses heating; putting it back resumes it.
- English/Chinese UI, pause and restart, call budgets, player preference messages, session bookmarks, and feedback export.
- Structured agent observations and actions, event records, bounded local cross-round memory, and data-driven maps.

### Structured cooperation rather than screen control

ChefJeff gives the agent kitchen state, rules, and legal action candidates directly. The agent chooses actions such as fetching, chopping, washing, or serving; the kitchen engine validates and executes them. This makes coordination and decision-making accessible without first requiring visual recognition or mouse control.

The human plays through keyboard and pointer input, while the agent uses higher-level actions. Both operate within the same kitchen rules. Action selection, acceptance, and completion are tracked separately so developers can inspect what actually happened.

## Quick start

**The online demo is not open yet. You can run the full prototype locally using the steps below.**

You need **Python 3.10+ and a desktop/laptop browser with a keyboard and mouse**. The backend uses Python's standard library, and the repository includes a prebuilt web client.

```sh
git clone https://github.com/belchingleo/ChefJeff.git
cd ChefJeff
python3 scripts/launch_web.py
```

On Windows, use `py -3 scripts/launch_web.py`. You can also launch with `start-web.command` on macOS or `start-web.bat` on Windows.

Open <http://127.0.0.1:8775/>, enter your own TypeSafe Jev, DeepSeek, or compatible Chat Completions credentials in Settings, test the connection, and start a round. Connection tests and gameplay requests use your model account and may incur charges.

For a foreground process on any supported platform:

```sh
python3 cocos_server.py --port 8775
```

Stop it with Ctrl+C after playing. For the macOS background launcher, use `python3 scripts/stop_web.py`.

### Supported devices

The current release supports **desktop and laptop browsers with a keyboard and mouse**. Phones and touch-only play are not supported. iPads with an external keyboard and mouse are a future compatibility target: iPadOS supports these accessories, but ChefJeff still needs real-device checks for simultaneous keys, pointer buttons, focus, and rendering. They are not included in current supported devices. See [device support](docs/device-support.md).

### Controls

- **WASD / arrow keys:** move. Click a floor tile or workstation to approach it. Double-tap a direction to sprint.
- **Space:** perform the nearby action shown in the bottom hint. Cancelling chopping or washing preserves progress.
- **Throw:** hold Space briefly, then left-click a target; release to cancel. Alternatively, right-click to prepare, left-click to throw, and right-click to cancel. Ingredients, plates, dishes, pots and the extinguisher all fly up to 4 cells.
- **Serve and wash:** use a clean plate to collect cooked food; return dirty plates to the sink and wash with empty hands.
- **Esc:** pause. Settings provide model connections, language selection, usage limits, and feedback export.

See [current rules](docs/current-rules.md) for the full gameplay reference.

## Build on ChefJeff

The environment separates kitchen rules, spatial movement, agent decisions, and rendering. Maps have a schema, validation, and a loading path; these foundations support community-authored kitchens and future editors.

| Module | Entry points | Responsibility |
| --- | --- | --- |
| Kitchen rules | `kitchen.py` | Ingredients, preparation, containers, orders, shared work, events |
| Maps and space | `maps/`, `map_definition.py`, `spatial_kitchen.py`, `navigation.py` | Map validation, movement, docking, contact, throwing |
| Decision loop | `jev.py` | Asynchronous requests, response freshness, execution, call budgets |
| Model adapters | `whitebox_server.py`, `player_api.py` | Spatial observations, TypeSafe and Chat Completions protocols |
| Local service | `web_server.py`, `cocos_server.py` | Kitchen session, player inputs, state synchronization |
| Rendering | `cocos-kitchen/assets/scripts/` | Cocos Creator 3.8.8, TypeScript, geometry, pixel assets |
| Session records | `cooperation_memory.py`, `feedback.py` | Bounded history, communication, inspectable feedback |

For a new model adapter, implement `payload(state, actions)` and `ask(payload)` and return the chosen action to `DecisionLoop`. The environment handles action validation and execution. Existing compatible services can be configured directly in Settings.

Start with [agent integration](docs/agent-integration.md) and [map format](docs/map-format.md). The character is named Jeff; TypeSafe Jev is one supported model service, and `jeff` is the internal actor identifier.

### Development

Playing uses the prebuilt client. Visual changes require **Cocos Creator 3.8.8**; backend changes need only a server restart.

```sh
python3 -m unittest discover -s tests
python3 scripts/audit_release.py
python3 scripts/build_cocos.py web
python3 scripts/package_web.py
```

Set `COCOS_CREATOR` if Creator is installed elsewhere. Geometry execution tests use Node.js and TypeScript. GitHub CI runs offline tests without paid model calls. The `scenarios/` directory contains development regression fixtures.

## Privacy and model costs

When you run ChefJeff locally, your computer runs the backend and connects to the model service you select. Your API key stays in backend memory by default; choosing “Remember this device” saves it in the local plaintext file `.player-api.json`. Local sessions do not connect to a ChefJeff-hosted game server.

Your selected model service receives game state, rules, communication, and any enabled bounded history. Local journals and memory remain on your computer. Review exported feedback before sharing it, and keep keys out of issues, screenshots, and commits.

The default budget is **200 model calls per round**, adjustable from 1 to 2000. Failed requests count toward the limit; connection tests are separate. Charges follow your provider's billing. See [privacy and costs](docs/privacy-and-costs.md) and [security](SECURITY.md).

## Project stage and roadmap

ChefJeff is an early playable prototype. The repository is currently private while we prepare a public release; collaborators need access to clone it. The benchmark schema, evaluation protocol, and community dataset are the next major development direction.

1. **Open the game to co-creation.** Refine interaction and pacing through playtesting, add shared-sink maps, and complete the asset/license review for public distribution. Cooperative washing already has a shared-work implementation and a test layout.
2. **Make content easier to create.** Extend map data contracts, move recipe legality and processing conditions into reusable data, and build map and recipe editors.
3. **Broaden agent participation.** Improve adapters and experiment configuration, then support agent–agent teams and comparisons across multiple models and coordination methods.
4. **Co-create the benchmark.** Define the whole-session scenario schema, reproducible comparison protocols, and evaluation measures with researchers, developers, and players. Grow the session collection through varied human participation and agent configurations.
5. **Bring the prototype online.** Deploy isolated kitchens over HTTPS with browser-direct model requests. The planned contribution flow uses anonymous sessions, explicit opt-in, 30-day retention, and a deletion receipt. The hosted service is in preparation; the local version's credential behavior is described above.

6. **Reach more devices.** Validate iPad with keyboard and mouse, then explore touch controls and other terminals.

## Inspiration and thanks

[Overcooked](https://www.ghosttowngames.com/overcooked/) is a remarkable work for exploring cooperation and coordination. ChefJeff's creator is a devoted Overcooked player on Nintendo Switch, and this project is a tribute to the shared challenges and delight of cooking together.

Overcooked inspired ChefJeff from the beginning. Its overall gameplay and some early kitchen-layout ideas informed our initial designs. This acknowledgement concerns gameplay and map-design inspiration, rather than a reference to its specific software implementation. ChefJeff develops those ideas into a community-built environment for real-time human–AI cooperation and agent comparison.

## Join the project

We welcome game improvements and benchmark design as equal parts of the project. Bring a new kitchen, an agent adapter, a cooperation question, a proposed session field, an evaluation protocol, or a playtest observation. Issues and pull requests are places to develop these together; see [CONTRIBUTING](CONTRIBUTING.md).

Original project code is licensed under [AGPL-3.0-only](LICENSE). Dependency and asset terms are listed in [third-party notices](THIRD_PARTY_NOTICES.md) and [license status](LICENSE-STATUS.md).

---

## 中文说明

# ChefJeff · 一起出餐

**一个探索人类与 AI agent 如何在实时环境中共同工作的开源项目。**

ChefJeff 让人类玩家和 AI 厨师进入同一个厨房。订单不断到来，食物持续加热，脏盘逐渐堆积，双方需要随着局势变化协调行动。Jeff 观察厨房、自主选择动作，与玩家共同完成任务，没有预设的固定分工。

我们希望共同建设两部分：**一个可由社区持续扩展的协作游戏**，以及**一个通过完整对局研究和对照 agent 协作能力的开放 benchmark**。游戏提供可参与的实时环境，benchmark 则将通过社区贡献的对局描述、交互记录和评估方法不断探索并建立。

## 面向谁，能一起做什么

| 参与者 | 可以探索或贡献的方向 |
| --- | --- |
| 人机交互、人机协作研究者 | 研究时间压力下的分工、伙伴响应、沟通及协作失误后的恢复 |
| Agent 与模型开发者 | 在共同环境中对照不同模型、决策策略、记忆、沟通和规划方法 |
| 多 agent 研究者 | 从人类—agent 合作起步，拓展 agent—agent 团队，对照不同搭档组合、团队配置与协调策略 |
| 游戏开发者、设计师与美术创作者 | 创作地图、菜谱、机制、界面和素材，带来新的合作情境 |
| 玩家与社区贡献者 | 与不同 agent 试玩、分享体验，参与游戏和未来评估集合的建设 |

## 围绕完整协作过程建设 benchmark

我们希望评估的是 **agent 在持续变化的实时环境中与伙伴共同完成任务的能力**。出餐成绩是一种结果，合作过程同样重要：什么时候帮忙，什么时候接手其他任务，怎样回应伙伴的请求，以及计划失效后如何恢复。

计划中的 **scenario schema** 描述的是一整局合作：环境与规则配置、参与者和 agent 设置、观察与动作接口、时序与沟通、交互时间线，以及最终结果。不同玩家、agent、地图和团队组合，都可以用这套共同结构贡献对局。

它将支持这样的探索：

- 同一个 agent 怎样与不同操作习惯的玩家合作？
- 在可对照的伙伴和环境条件下，不同 agent 有怎样的表现差异？
- 沟通、记忆、规划或响应延迟变化时，合作过程如何改变？
- 人类—agent 与 agent—agent 团队，如何在共同的资源和时间约束下协调？

社区可以共同制定比较协议，以及任务结果、协调、适应、资源使用和玩家体验等方面的度量。接口条件、模型延迟与搭档配置也应进入比较记录，让这些因素的影响可被检查。固定地图可以提供测试条件；**组织 benchmark 的基本单位是完整对局及其上下文**。

## 现在可以使用什么

**0.5.9-alpha** 提供本地浏览器游戏、三张可玩地图，以及玩家自带的模型连接。

- 牛排、汉堡和混合菜谱厨房，包含备料、烹饪、装盘、出餐、餐具回收、洗碗和消防。
- 共享工位、合作切菜、抛接原料、传菜、搬锅和厨师之间的温和碰撞。
- 按朝向呈现的操作动画、食材叠层及熟成／烧糊倒计时；锅离灶暂停加热，放回后续算。
- 中文／英文界面、暂停与重开、调用上限、玩家偏好沟通、局内标记和反馈导出。
- 结构化的 agent 观察与动作、事件记录、有限本地跨局记忆和数据化地图。

### 通过结构化接口探索协作

ChefJeff 直接向 agent 提供厨房状态、规则和当前合法动作候选。Agent 选择取料、切菜、洗碗、出餐等动作，由厨房引擎校验和执行。这让开发者可以直接研究协调与决策，而无需先解决识图或鼠标操作问题。

人类通过键盘和鼠标实时操作，agent 使用较高层的动作接口，双方遵循同一套厨房规则。系统分别记录动作选择、接受与完成，便于检查实际发生的过程。

## 快速运行

**在线试玩暂未开放，当前可按以下步骤在本地运行完整原型。**

需要 **Python 3.10+，以及配备键盘和鼠标的电脑浏览器**。后端使用 Python 标准库，仓库包含预构建网页。

```sh
git clone https://github.com/belchingleo/ChefJeff.git
cd ChefJeff
python3 scripts/launch_web.py
```

Windows 使用 `py -3 scripts/launch_web.py`。也可双击 `start-web.command`（macOS）或 `start-web.bat`（Windows）。

打开 <http://127.0.0.1:8775/>，在「设置」中填写自己的 TypeSafe Jev、DeepSeek 或兼容 Chat Completions 的 API，测试连接后开局。连接测试和游戏请求使用你的模型账号，费用由该账号承担。

各平台也可在前台运行：

```sh
python3 cocos_server.py --port 8775
```

游玩结束后按 Ctrl+C 停止。使用 macOS 后台启动器时，可运行 `python3 scripts/stop_web.py`。

### 支持的设备

当前版本支持 **配备键盘和鼠标的台式机／笔记本浏览器**。暂不支持手机或纯触屏操作。外接键鼠的 iPad 是后续兼容目标：iPadOS 支持这些外设，但 ChefJeff 仍需真机检查组合按键、鼠标按钮、焦点和渲染，当前不列入支持设备。详见[设备支持](docs/device-support.md)。

### 基本操作

- **WASD／方向键：**移动；点击地面或工位走近；双击同一方向键冲刺。
- **空格：**执行底部提示的就近动作；主动取消切菜或洗碗时保留加工进度。
- **抛原料：**短暂按住空格后左键点击目标，松开取消；也可右键准备、左键抛出、右键取消。原料、盘子、菜、锅和灭火器都可以抛，最远 4 格。
- **出餐和洗碗：**用净盘收取熟食；将脏盘送进水槽，空手洗净。
- **Esc：**暂停；设置中可连接模型、切换语言、控制调用次数和导出反馈。

完整玩法见 [当前规则](docs/current-rules.md)。

## 在 ChefJeff 上继续开发

项目将厨房规则、空间移动、agent 决策和画面呈现分开维护。地图已有数据格式、校验和加载入口，为社区创作厨房及后续编辑器提供基础。

| 模块 | 入口 | 职责 |
| --- | --- | --- |
| 厨房规则 | `kitchen.py` | 食材、加工、容器、订单、合作与事件 |
| 地图与空间 | `maps/`、`map_definition.py`、`spatial_kitchen.py`、`navigation.py` | 地图校验、移动、停靠、碰撞与抛接 |
| 决策调度 | `jev.py` | 异步请求、响应时效、动作执行与调用上限 |
| 模型适配 | `whitebox_server.py`、`player_api.py` | 空间观察、TypeSafe 与 Chat Completions 协议 |
| 本地服务 | `web_server.py`、`cocos_server.py` | 厨房会话、玩家输入与状态同步 |
| 画面 | `cocos-kitchen/assets/scripts/` | Cocos Creator 3.8.8、TypeScript、几何与像素素材 |
| 对局记录 | `cooperation_memory.py`、`feedback.py` | 有限历史、沟通与可检查的反馈 |

接入新模型时，实现 `payload(state, actions)` 和 `ask(payload)`，将动作选择返回给 `DecisionLoop`；环境负责校验与执行。已有兼容服务可直接通过设置接入。

从 [agent 接入](docs/agent-integration.md) 和 [地图数据格式](docs/map-format.md) 开始了解。游戏角色名是 Jeff；TypeSafe Jev 是支持的模型服务之一，`jeff` 是内部角色标识。

### 开发与验证

试玩使用预构建网页；画面修改需要 **Cocos Creator 3.8.8** 重新构建，后端修改只需重启服务。

```sh
python3 -m unittest discover -s tests
python3 scripts/audit_release.py
python3 scripts/build_cocos.py web
python3 scripts/package_web.py
```

Creator 安装在其他位置时可设置 `COCOS_CREATOR`。几何执行测试使用 Node.js 和 TypeScript；GitHub CI 运行离线测试，不调用付费模型。`scenarios/` 目录提供开发回归用例。

## 隐私与模型费用

本地运行时，你的电脑承担后端工作，并连接你选择的模型服务。Key 默认保存在本机后端内存中；勾选「记住设备」后，写入本地明文文件 `.player-api.json`。本地对局不连接 ChefJeff 托管的游戏服务器。

你选择的模型服务会接收游戏状态、规则、沟通及启用后的有限历史。原始日志和协作记忆保留在本机。分享前请检查导出的反馈，避免将 Key 放入 Issue、截图或提交记录。

默认每局最多 **200 次模型调用**，可设置为 1–2000 次；失败请求计入上限，连接测试另计。费用以模型服务商账单为准。详见 [隐私与调用费用](docs/privacy-and-costs.md) 和 [安全说明](SECURITY.md)。

## 项目阶段与后续计划

ChefJeff 目前处于可玩的早期原型阶段。仓库在公开发布准备期间保持私有，协作者获得访问权限后即可克隆。Benchmark 的 schema、评估协议和社区数据集是接下来的主要建设方向。

1. **共同打磨游戏。** 通过真人试玩改进交互与节奏，增加双人水槽地图，完成公开分发所需的素材与许可清理。合作洗碗已有规则实现及测试布局。
2. **降低内容创作门槛。** 完善地图数据契约，将配方合法性和加工条件整理为可复用数据，建设地图与菜谱编辑器。
3. **拓展 agent 参与。** 完善适配器与实验配置，进一步支持 agent—agent 团队，以及不同模型和协调方法之间的对照。
4. **共创 benchmark。** 与研究者、开发者和玩家共同定义整局 scenario schema、可复现的比较协议和评估指标，通过不同玩家与 agent 配置逐步扩充对局集合。
5. **提供在线试玩。** 部署 HTTPS 与独立厨房会话，由浏览器直接请求模型。计划采用匿名会话、主动贡献数据、保留 30 天并提供删除凭证的流程。托管服务正在准备中；本地版本的密钥处理方式见上文。

6. **拓展终端支持。** 验证 iPad 外接键鼠的兼容性，再探索触屏交互和其他终端。

## 启发与鸣谢

[Overcooked（分手厨房）](https://www.ghosttowngames.com/overcooked/) 是一部在探索协作与多方配合方面的伟大作品。ChefJeff 的创作者是该游戏忠实的 Nintendo Switch 玩家，希望借此项目向共同做菜带来的挑战与欢乐致敬。

ChefJeff 从项目初期就受到了 Overcooked 的启发，整体玩法与早期厨房地图设计对该游戏都有所参考。这里所指的是玩法与地图设计层面的启发，而非其具体软件实现。ChefJeff 在此基础上，探索由社区共同建设的实时人机协作与 agent 能力对照环境。

## 参与共创

游戏建设和 benchmark 设计都是项目的重要组成部分。欢迎带来新厨房、agent 适配器、协作研究问题、对局字段建议、评估协议或试玩观察，通过 Issues 和 Pull Requests 一起完善。贡献方式见 [CONTRIBUTING](CONTRIBUTING.md)。

原创项目代码采用 [AGPL-3.0-only](LICENSE)。依赖和素材的许可信息见 [第三方说明](THIRD_PARTY_NOTICES.md) 与 [许可状态](LICENSE-STATUS.md)。
