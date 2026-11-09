# ChefJeff Benchmark

Run an agent on fixed levels with a fixed scripted partner, many rounds each, and get a result whose every number carries its interval. The agent can be Jeff on your model, or your own agent on the environment interface ([env-v1](../docs/architecture/environment-api.md)).

## v2

`v2/manifest.json` freezes what v2 measures:

- the environment interface (`env-v1`);
- levels 1–3, each with its configuration hash and the hash of its golden reference trace, which changes exactly when the engine plays the level differently;
- the scripted partner `assembler` from `reference_policy.py`;
- 12 rounds per level, on a real clock.

A test fails when the code no longer matches the manifest, so a change to any of these makes a new version instead of quietly changing what a score means. Level 4, which needs both chefs, comes in v2.1.

v2 measures what v1 did (the same levels, partner, rounds and interface). v1 (`v1/manifest.json`, kept as it was frozen) retired on 2026-11-09 before anyone ran it: the fridge's action key became `fetch beef`, like every other ingredient source, so the reference traces it froze changed although the engine plays exactly as before.

The scripted partner is not a person. These scores measure an agent with a steady, known partner. Rounds with people are counted with `scripts/decision_stats.py` and read alongside, never instead.

## Run

```bash
python3 scripts/benchmark.py run --agent jeff --out runs/my-model --dry-run
```

Prints the most a run can cost (36 rounds, 108 minutes of play) and plays nothing.

```bash
python3 scripts/benchmark.py run --agent jeff --out runs/my-model --parallel 3
```

Plays Jeff on the model connection saved in the game.

```bash
python3 scripts/benchmark.py run --agent example_agent:PriorityAgent --out runs/floor
```

Plays your own `environment.Agent`, named as `module:Class`.

```bash
python3 scripts/benchmark.py verify runs/my-model/result.json
```

Says whether the result counts as the version it was made for.

```bash
python3 scripts/benchmark.py report runs/*/result.json
```

Prints one table: money and goal rate with 95% intervals, the gain over the scripted chef alone, the agent's share of the work and calls per round.

Every round's journal and session bundle are kept under `--out`, and every round's replay is checked. `verify` refuses a result made for another manifest, from a checkout that no longer matches it, with the wrong number of rounds, on a virtual clock, or with a round that does not replay.

## Results

Put a result that `verify` accepts under `v2/results/<agent>-<model>.json`; `report` reads them all.

---

## 中文说明

# ChefJeff Benchmark

让一个 agent 在固定的关卡、固定的脚本搭档下各打多局，结果里的每个数字都带置信区间。agent 可以是用你的模型的 Jeff，也可以是你自己基于环境接口（[env-v1](../docs/architecture/environment-api.md)）写的 agent。

## v2

`v2/manifest.json` 冻结了 v2 测什么：

- 环境接口（`env-v1`）；
- 第 1–3 关，每关的配置哈希，以及该关黄金参考轨迹的哈希（引擎打法一变，这个哈希就变）；
- `reference_policy.py` 里的脚本搭档 `assembler`；
- 每关 12 局，按真实时间。

代码与清单不一致时测试会失败。所以改动其中任何一项，都要发新版本，而不是悄悄改变分数的含义。需要两人合作的第四关放在 v2.1。

v2 测的内容和 v1 完全一样（关卡、搭档、局数和接口都相同）。v1（`v1/manifest.json`，按冻结时的样子保留）在 2026-11-09 退役，当时还没有人跑过：冰箱的动作代号改成了和其他食材箱一致的 `fetch beef`，它冻结的参考轨迹因此变了，虽然引擎的玩法完全没变。

脚本搭档不是真人。这些分数衡量的是 agent 在一个稳定、已知的搭档下的表现。真人对局用 `scripts/decision_stats.py` 统计，与之对照着看，不能互相替代。

## 运行

命令与英文部分相同：

- `run --dry-run`：只打印最多花多少钱（36 局、108 分钟），不打任何对局；
- `run --agent jeff`：用游戏里保存的模型连接让 Jeff 打；
- `run --agent 模块:类名`：让你自己的 `environment.Agent` 打；
- `verify`：判断结果算不算它所属的版本；
- `report`：把多份结果汇总成一张表，内容包括带 95% 区间的收入和达标率、相对脚本单人的增益、agent 承担的工作占比，以及每局调用次数。

每一局的日志和会话包都保存在 `--out` 下，每一局都会检查能否精确回放。以下几种结果 `verify` 会拒收：为别的清单生成的、生成它的代码已与清单不一致的、局数不对的、用虚拟时钟跑的、有局不能回放的。

## 结果

通过 `verify` 的结果放到 `v2/results/<agent>-<模型>.json`，`report` 会把它们全部读进来。
