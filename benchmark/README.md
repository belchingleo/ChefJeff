# ChefJeff Benchmark

Run an agent on fixed levels with a fixed scripted partner, many rounds each, and get a result whose every number carries its interval. The agent can be Jeff on your model, or your own agent on the environment interface ([env-v1](../docs/architecture/environment-api.md)).

## v5

`v5/manifest.json` freezes the same things as v4, on the same kitchen and with the same level configurations. Two things differ. First, from 2026-11-22 the option to put out a burning stove says what follows for the food in its pan, from the rules at that moment. Burnt food the −10 tier still accepts when the spray ends can be plated and served, with the seconds left in the tier, or emptied at a bin; burnt food past it by then is refused if served and can only be emptied at a bin (2 yuan); food a fire spread to is not burnt and cooks on once the fire is out (cooked food with the seconds until it burns); an empty pan or a stove without one gets nothing more. Jeff's task and the events that carry the option leave all of this out. Second, later on 2026-11-22: burnt food in Jeff's request, and the engine's labels that plate it, lift or swap its pan, take it, pick it up or serve it (the labels `env-v1` lists too), say whether a dish with it is still accepted and at what price, or refused (`servability-v1`); Jeff's task and the events leave this out too. No v5 result had been made before it, and none of the values v5 freezes changed with it, so v5 was kept rather than retired.

v4 (`v4/manifest.json`, kept as it was frozen) retired on 2026-11-22 before anyone ran it: Jeff reads the option, and level 2's reference trace, whose events carry its label, changed with it, although the engine plays exactly as before.

## v4

`v4/manifest.json` freezes the same things as v3 (the `env-v1` interface, levels 1–3, the scripted partner `assembler`, 12 rounds per level on a real clock), measured on the kitchen as it is from 2026-11-22: burnt food's burnt time runs while it stays on a stove, whether the stove is burning, put out or neither, and stops when it leaves the stove, so a pan of burnt food left on its stove goes past the −10 tier and is refused; burnt food sets its stove alight once, as it burns, and after that only a fire spreading from nearby sets the stove alight again; and a fire no longer burns the food in a pan: food still cooking when a fire reaches its stove is cooked and then waits, cooked food waits, and both cook on once the fire is out. Jeff's rules are `rules-v15` and the engine semantics `continuous-2026-11`.

v3 (`v3/manifest.json`, kept as it was frozen) retired on 2026-11-22 with that change: every level's configuration changed with the engine semantics, and level 2's reference trace with the burnt time, so v3 and v4 scores are not compared.

## v3

`v3/manifest.json` freezes the same things as v2 (the `env-v1` interface, levels 1–3, the scripted partner `assembler`, 12 rounds per level on a real clock), measured on the kitchen as it is from 2026-11-11: every sink has a drying rack beside it, as in Overcooked 2 (dirty plates stack in the sink and stay there until washed; each washed plate goes onto the rack); level 1 moved its stove and plates one cell to make room for the rack, levels 2 and 3 turned the counter beside the sink into it; a held empty pan scoops an ingredient off a board or counter; and both chefs walk 4 cells per second (was 5), with the targets of levels 2 and 3 recalibrated to 160 and 140. From 2026-11-22 one thing changed: a chef at the sink, either chef, takes the drying rack's top clean plate where it stands, as in Overcooked 2 (from anywhere else the take walks to the rack; before that date it always did), and Jeff's rules are `rules-v15` (before that, `rules-v14`). No v3 result had been made with `rules-v14`, and none of the values v3 freezes changed with this, so v3 was kept rather than retired.

v2 (`v2/manifest.json`, kept as it was frozen) retired on 2026-11-11 with that change: its levels now play differently, so v2 and v3 scores are not compared.

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

Put a result that `verify` accepts under `v5/results/<agent>-<model>.json`; `report` reads them all.

---

## 中文说明

# ChefJeff Benchmark

让一个 agent 在固定的关卡、固定的脚本搭档下各打多局，结果里的每个数字都带置信区间。agent 可以是用你的模型的 Jeff，也可以是你自己基于环境接口（[env-v1](../docs/architecture/environment-api.md)）写的 agent。

## v5

`v5/manifest.json` 冻结的内容和 v4 相同，厨房一样，每关的配置也一样。有两处不同。第一处，从 2026-11-22 起，给着火灶台灭火的选项会按当时的规则写明锅里的菜之后怎么办。喷完火时糊菜还在 −10 那一档里，选项写明可以装盘上菜、这一档还剩几秒，也可以端锅到垃圾桶倒掉；喷完火时已经超过这一档，选项写明上菜会被拒收，只能端锅到垃圾桶倒掉（花 2 元）；火是从旁边蔓延过来的，锅里的菜没有糊，选项写明灭火后接着加热（熟了的菜还写明再过几秒糊锅）；空锅或灶台上没有锅时，选项不加这些话。Jeff 当前任务和带着这个选项的事件不写这些话。第二处是同一天晚些时候改的：Jeff 请求里的糊菜，以及引擎给糊菜装盘、端起或换下装着糊菜的锅、拿起、捡起和出餐的说明（`env-v1` 列出的也是这些说明），会写明这份菜还能不能上菜、扣多少钱，或者会被拒收（`servability-v1`）；Jeff 当前任务和事件同样不写这些话。因为改动之前还没有做出过任何 v5 成绩，v5 冻结的各项数值也没有因此改变，所以 v5 保留下来，没有退役。

v4（`v4/manifest.json`，保持冻结时的样子）在 2026-11-22 退役，退役前没有人跑过它。Jeff 会读这个选项，第二关参考轨迹里的事件带着这个选项的文字，也跟着变了，所以 v4 冻结的参考轨迹对不上了，尽管引擎的玩法和之前完全一样。

## v4

`v4/manifest.json` 冻结的内容和 v3 相同（`env-v1` 接口、第 1–3 关、脚本搭档 `assembler`、每关 12 局、真实时钟），量的是 2026-11-22 起的厨房：糊了的菜只要留在灶台上，糊的时长就一直累计，灶台着火、火已扑灭或从没着火都一样，离开灶台才停止，所以糊菜一直留在灶台上就会超过 −10 那一档、被顾客拒收；糊菜只在烧糊那一刻让灶台起一次火，之后只有旁边的火蔓延过来才会再着火；火也不再把锅里的菜烧糊：火烧到灶台上时，还在煎的菜照样煎到熟再停下来等着，已经熟了的菜马上等着，灭火后都从原来的进度接着加热。Jeff 的规则是 `rules-v15`，引擎规则版本是 `continuous-2026-11`。

v3（`v3/manifest.json`，保持冻结时的样子）在 2026-11-22 随这次改动退役：引擎规则版本一变，每关的配置都变了，第二关的参考轨迹也因为糊的计时而变了，所以 v3 和 v4 的成绩不放在一起比较。

## v3

`v3/manifest.json` 冻结的内容和 v2 相同（`env-v1` 接口、第 1–3 关、脚本搭档 `assembler`、每关 12 局、真实时钟），只是量的是 2026-11-11 起的厨房：每个水槽旁都有沥水架，和《Overcooked 2》一样，脏盘在水槽里叠放、洗好才离开，洗好的盘子放到沥水架上；第一关把灶台和盘子各挪一格给沥水架让位，第二、三关把水槽旁的柜台改成沥水架；手里拿着空锅可以盛起案板或柜台上的食材；两位厨师每秒走 4 格（原来 5 格），第二、三关达标线随之重新校准为 160 和 140。从 2026-11-22 起又改了一处：两位厨师站在水槽前都能就地取走沥水架最上面的干净盘子，和《Overcooked 2》一样（在别处取仍要走到沥水架；在这之前，在哪里取都要走过去），Jeff 的规则也随之改为 `rules-v15`（之前是 `rules-v14`）。因为用 `rules-v14` 还没有做出过任何 v3 成绩，v3 冻结的各项数值也没有因此改变，所以 v3 保留下来，没有退役。

v2（`v2/manifest.json`，保持冻结时的样子）在 2026-11-11 随这次改动退役：它的关卡现在玩法不同，v2 和 v3 的成绩不放在一起比较。

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

通过 `verify` 的结果放到 `v5/results/<agent>-<模型>.json`，`report` 会把它们全部读进来。
