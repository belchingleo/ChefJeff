# Environment interface (env-v1) and Jeff as the reference agent

`environment.py` is the line between the game and whoever plays a chef in it. On one side is the environment: the engine, levels and configuration, real-time ticking, recording and replay, the human's input. On the other side is an agent. Jeff is one agent, the reference one, and everything that makes him Jeff belongs to his side: the rule text he reads, which options his model is shown, one-press actions, plans, undo notes, the compact request format, when he asks and how he asks ahead.

Benchmark v1 freezes this line, not Jeff. An agent's score means the same as long as `ENV_API_VERSION` and the benchmark manifest are unchanged, however Jeff's harness moves on.

## The port

An agent gets an `AgentPort` for its chef, never the kitchen object.

**Tier 1, plain data: the contract any agent can rely on.**

- `observe()` returns `{env_api_version, who, time, event_seq, ended, kitchen, actions}`:
  - `kitchen` is the engine's state with display-only fields left out and text in English;
  - `actions` is every action the engine lists for this chef now, unpruned, as `{key, kind, target, label}`.
- `events_since(seq)` returns the engine events after a sequence number, in English.
- `act(key, sprint=False, expect_job=ANY_JOB)` returns `{applied, reason, sprinted, job_id}`.
  - The action is checked when it arrives, not when the agent looked. A choice can be legal when asked and gone when answered, as it always has been.
  - `expect_job` carries it out only while the chef still does that job (`None`: only while idle), so an answer about one moment is not used in another.

**Tier 2, the engine read-only: for agents that run in this process.**

- `view` is the kitchen with every engine input refused: `start`, `stop`, `advance`, `sprint`, `set_manual` and any method marked by the engine's `engine_input` decorator. Attribute assignment is refused too.
- `start(action)`, `sprint()` and `fork_until_step_end()` are the engine calls an agent may make through the port.
- Whatever an agent does to the kitchen therefore goes through the port and is recorded as an engine input, so every round replays exactly.

**Time.** The kitchen does not wait. The session ticks in real time and calls `Agent.poll(port, now)` on its own thread. An agent that waits for a model asks from a thread of its own and acts on a later poll. A model that thinks for two seconds has spent two seconds of the round. Measuring that is the point.

## An agent

```python
import environment

class MyAgent(environment.Agent):
    name = 'my-agent'
    def start(self, port): ...
    def poll(self, port, now):
        seen = port.observe()
        ...                      # decide, perhaps over several polls
        port.act(key, expect_job=job_it_was_decided_for)
    def close(self): ...
```

`GameSession(config, client_factory=lambda config: MyAgent(), ...)` plays it: when the factory returns an `environment.Agent`, the session runs it through `agent_loop.AgentLoop` where Jeff's loop would run. `example_agent.PriorityAgent` is the smallest complete agent. It imports nothing but `environment` and is a floor to beat, not a cook.

## Jeff on the port

`jev.DecisionLoop` reads the kitchen through `view` and starts actions and sprints through the port. His helpers (`harness`, `one_press`, `undo_note`, `ask_ahead`, `reach_note`) read the same view. Moving him there changed no byte of what he is sent and no engine decision. The payload and behaviour fingerprints are unchanged and research replay rebuilds every request.

## Versions

- A change to what `observe()` returns, what `act()` does, the timing above, or what the view allows bumps `ENV_API_VERSION`, and with it the benchmark version.
- Jeff's own changes keep their own versions: rules, `features.json` and input language.

---

## 中文说明

# 环境接口（env-v1）与作为参考 agent 的 Jeff

`environment.py` 是游戏和"扮演厨师的那一方"之间的分界线。

- **环境一侧**：引擎、关卡与配置、实时推进、记录与回放、人这一方的输入。
- **agent 一侧**：Jeff 是其中一个，也是参考 agent。凡是让 Jeff 成为 Jeff 的东西都归他这一侧：他读的规则说明、给模型看哪些选项、one-press、计划、撤销提示、紧凑请求格式、什么时候问、怎样提前问。

Benchmark v1 冻结的是这条线，不是 Jeff。只要 `ENV_API_VERSION` 和 benchmark 清单不变，不管 Jeff 的 harness 怎么改，一个 agent 的分数含义都不变。

## 端口

agent 拿到的是自己那名厨师的 `AgentPort`，拿不到厨房对象本身。

**第一层：普通数据，任何 agent 都可以依赖的约定。**

- `observe()` 返回 `{env_api_version, who, time, event_seq, ended, kitchen, actions}`：
  - `kitchen` 是引擎状态，去掉了只供页面显示的字段，文字都是英文；
  - `actions` 是引擎此刻为这名厨师列出的全部动作，不做裁剪，每条为 `{key, kind, target, label}`。
- `events_since(seq)` 返回某个序号之后的引擎事件，英文。
- `act(key, sprint=False, expect_job=ANY_JOB)` 返回 `{applied, reason, sprinted, job_id}`。
  - 动作在到达时按当时的状态校验，不在 agent 观察时校验。提问时合法的选择，到回答时可能已经不行了，游戏一直是这样。
  - `expect_job` 表示"只有这名厨师还在做那件事时才执行"（`None` 表示只在空闲时执行），以免把针对某一刻的回答用到另一刻。

**第二层：只读的引擎，供在本进程里运行的 agent 使用。**

- `view` 就是厨房对象，但所有引擎输入都会被拒绝：`start`、`stop`、`advance`、`sprint`、`set_manual`，以及其他带引擎 `engine_input` 标记的方法。给属性赋值也会被拒绝。
- `start(action)`、`sprint()`、`fork_until_step_end()` 是 agent 可以通过端口调用的引擎操作。
- 所以 agent 对厨房做的任何改动都必须经过端口，并作为引擎输入记录下来，每一局都能精确回放。

**时间。** 厨房不会停下来等 agent。会话按真实时间推进，在自己的线程里调用 `Agent.poll(port, now)`。要等模型回复的 agent，在自己的线程里发请求，在后面的某次 poll 里再行动。模型想了两秒，就是用掉了这一局的两秒，这正是要测的东西。

## 写一个 agent

代码见上方英文部分。工厂函数返回 `environment.Agent` 时，会话会用 `agent_loop.AgentLoop` 在原本运行 Jeff 循环的位置运行它。`example_agent.PriorityAgent` 是最小的完整示例：它只引用 `environment`，是一个用来超越的底线，不是一个好厨师。

## Jeff 改为通过端口工作

`jev.DecisionLoop` 通过 `view` 读厨房，通过端口开始动作和冲刺。他的辅助模块（`harness`、`one_press`、`undo_note`、`ask_ahead`、`reach_note`）读的也是同一个只读视图。这次迁移没有改变发给他的任何一个字节，也没有改变引擎的任何一个决定：payload 指纹和行为指纹不变，研究回放能重建每一次请求。

## 版本

- `observe()` 返回的内容、`act()` 的行为、上面说的时间语义，或者只读视图允许的操作，任何一项改变都要升 `ENV_API_VERSION`，benchmark 版本也随之升级。
- Jeff 自己的改动仍用他自己的版本号：规则版本、`features.json`、输入语言版本。
