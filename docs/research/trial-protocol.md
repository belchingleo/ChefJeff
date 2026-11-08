# Trial protocol

Write this down before a trial switch is measured, and before any paid model call. It keeps what counts as a result fixed before the answers are in, and it says how many rounds or moments a difference needs, so a share from a handful of rounds is read as what it is.

The tools report every share with its 95% interval (`research_stats.py`): 6 goals in 6 rounds is a share between 0.61 and 1.0, 5 of 5 answers between 0.57 and 1.0, 9 of 20 between 0.26 and 0.66. Two arms whose intervals overlap widely have not been told apart.

## Template

| Item | What to write |
| --- | --- |
| Question | One sentence: what the change is expected to do, and to what. |
| Change | The `features.json` switch and its version, or the request change; everything else held as it is (level, rules version, config hash, human policy). |
| Arms | Usually two: the switch off and on. Name them as the tools will (`as_logged`, `compact`, ...). |
| Unit | A **moment** (one logged request, re-asked: `scripts/reask.py`) or a **round** (a whole round: `scripts/model_rounds.py` with a scripted human, or real rounds through `scripts/decision_stats.py`). |
| Primary outcome | One. The result is read from this one; everything else is secondary. |
| Guard outcomes | What must not get worse (for Jeff: fires and burnt food per round, the goal rate). A worse guard stops the change whatever the primary says. |
| Size | Moments or rounds per arm, from `research_stats.per_arm_rounds(p1, p2)` for the smallest difference worth finding; for times and money, the bootstrap interval of the difference (`research_stats.bootstrap_difference`) narrower than that difference. |
| Models | At least two, so a wording that helps one model is not taken for a change that helps Jeff. The tools add a note when one model answered everything. |
| Budget | The `--dry-run` line of the tool, agreed before the run (CONTRIBUTING, item 5). |
| Decision rule | What result releases the change, what result rolls it back, and what result means "run more". |

Paired moments are stronger than separate rounds: the same request asked two ways differs only in the change, so `scripts/reask.py` reports the paired difference and its exact McNemar p next to the shares. With two or more asks per moment it also reports how often the model gives the same answer twice. A change smaller than that spread cannot be seen.

## Example 1: `compact_input` (Jeff's input sent compact, with a stable prefix)

- **Question:** does sending the same information in the compact layout cut reply time and input tokens without changing what Jeff chooses?
- **Change:** `compact_input` on (`compact-v1`); rules version, level and human policy as they are.
- **Moments (choices unchanged):** a re-ask check with arms `as_sent` and `compact` on the same logged requests, each asked twice. Primary: agreement between the two arms' first answers. Reference: each arm's agreement with itself on the repeat. The model's own repeat agreement was about 0.75 in the `put_where` check. Telling 0.75 from 0.60 needs about **152 moments** (`per_arm_rounds(.75, .60)`), and 0.75 from 0.65 about 329, so 20 moments cannot settle it.
- **Rounds (time and tokens):** `scripts/model_rounds.py --level level-2 --human assembler`, 12 rounds per arm and per model, with Jev and one chat model (DeepSeek). Primary: median reply time per round. Secondary: input tokens per request, and cache hits where the provider reports them. Guards: fires and burnt food per round, goal rate.
- **Budget:** the dry run for 12 rounds is at most 2400 requests and 23.3M input tokens, about $0.98 at Jev's price. Each further arm or model adds as much.
- **Decision:** release when the arms' agreement is not below the repeat agreement (interval of the paired difference includes 0), reply time is shorter, and no guard is worse. Roll back on a worse guard.

## Example 2: `ask_ahead` (Jeff asks for his next step before the current one ends)

- **Question:** does asking ahead shorten Jeff's wait between steps without making him handle emergencies worse?
- **Change:** `ask_ahead` on; `request_policy.ask_ahead` keeps rounds apart in the stats.
- **Rounds:** `scripts/model_rounds.py --level level-2 --human assembler`, 12 rounds per arm and per model, two models.
- **Primary:** median gap between steps (`decision_stats.py` `step_gaps`), with the bootstrap interval of the difference between arms.
- **Guards:** fires and burnt food per round (must not rise), goal rate, rejected and discarded replies. A goal rate moving from 0.5 to 0.8 needs about 39 rounds per arm to show, so 12 rounds watch the guards and the gap; they do not prove a better goal rate.
- **Decision:** release when the gap is shorter and the guards are not worse; otherwise switch it off.

## What the tools give

| Unit | Tool | Reports |
| --- | --- | --- |
| Moment | `python3 scripts/reask.py <check> ...` (`list` names the checks) | shares with intervals, paired differences with McNemar p, repeat agreement, a note for a single model |
| Round, scripted human | `python3 scripts/model_rounds.py --rounds N --out DIR` | each round's result and `decision_stats` for the set; journals and bundles in DIR |
| Round, real players | `python3 scripts/decision_stats.py logs/ --split ...` | outcomes and work per group |

---

## 中文说明

# 试验方案

在测量一个试验开关之前、在调用任何付费模型之前，先把下面这些写下来。这样在拿到结果之前，就已经定好了什么算结果；也写清楚了一个差别需要多少局或多少个时刻才看得出来，几局得出的比例就不会被当成定论。

现在这些工具报告每个比例时，都会附上 95% 区间（`research_stats.py`）：6 局里 6 局达标，比例在 0.61 到 1.0 之间；5 次回答里 5 次，在 0.57 到 1.0 之间；20 次里 9 次，在 0.26 到 0.66 之间。两组的区间如果大面积重叠，就还没有分出高下。

## 模板

| 项目 | 写什么 |
| --- | --- |
| 问题 | 一句话：这个改动预计会改变什么、改变多少。 |
| 改动 | `features.json` 里的开关及其版本，或者对请求的改动；其他一律不变（关卡、规则版本、配置指纹、人类一方的策略）。 |
| 对照组 | 通常两组：开关关、开关开。名字和工具里用的一致（`as_logged`、`compact` 等）。 |
| 单位 | **时刻**：把记录里的一次请求重新问一遍，用 `scripts/reask.py`。或者**整局**：用 `scripts/model_rounds.py` 配脚本人类，或者用 `scripts/decision_stats.py` 统计真人对局。 |
| 主要指标 | 只有一个。结论只看它，其余都是次要指标。 |
| 底线指标 | 不能变差的东西。对 Jeff 来说是每局着火和烧糊的次数，以及达标率。底线一旦变差，不管主要指标怎样，这个改动都不上线。 |
| 样本量 | 比例类指标：用 `research_stats.per_arm_rounds(p1, p2)` 算出每组需要多少个时刻或多少局，才能看出值得关心的最小差别。时间和金额类指标：两组之差的 bootstrap 区间（`research_stats.bootstrap_difference`）要比这个差别窄。 |
| 模型 | 至少两个，以免把"只对某一个模型管用的措辞"当成"对 Jeff 管用的改动"。全部回答都来自同一个模型时，工具会给出提示。 |
| 预算 | 工具 `--dry-run` 打印的那一行，正式运行前先定下来（CONTRIBUTING 第 5 条）。 |
| 决策规则 | 什么结果上线，什么结果回退，什么结果意味着"再跑一些"。 |

成对比较的时刻比分开跑的整局更有说服力：同一次请求用两种方式问，两次之间只差这一个改动。所以 `scripts/reask.py` 在比例旁边给出成对差别和精确 McNemar p 值。每个时刻问两次以上时，它还会报告模型两次给出相同回答的比例；比这个波动还小的差别是看不出来的。

## 例一：`compact_input`（Jeff 的输入以紧凑格式发送，带稳定前缀）

- **问题：** 用紧凑格式发送同样的信息，能不能缩短回复时间、减少输入 token，同时不改变 Jeff 的选择？
- **改动：** 打开 `compact_input`（`compact-v1`）；规则版本、关卡、人类一方的策略都不变。
- **按时刻比较（看选择有没有变）：** 用一个重问检查，对同一批记录里的请求分两组问：`as_sent` 和 `compact`，每个时刻问两次。主要指标是两组首次回答的一致率；参照是每组自己重复问两次的一致率。`put_where` 那次检查里，模型自身的重复一致率约为 0.75。要分辨 0.75 和 0.60，每组大约需要 **152 个时刻**（`per_arm_rounds(.75, .60)`）；分辨 0.75 和 0.65 约需 329 个。所以 20 个时刻下不了结论。
- **按整局比较（看时间和 token）：** `scripts/model_rounds.py --level level-2 --human assembler`，每组、每个模型各 12 局，模型用 Jev 和一个对话模型（DeepSeek）。主要指标是每局回复时间的中位数；次要指标是每次请求的输入 token，以及服务商报告的缓存命中。底线指标是每局着火和烧糊次数、达标率。
- **预算：** 12 局的 dry run 显示，最多 2400 次请求、2330 万输入 token，按 Jev 的价格约 0.98 美元。每多一组或多一个模型，再加这么多。
- **决策：** 同时满足以下三条就上线：两组之间的一致率不低于各自的重复一致率（成对差别的区间包含 0）；回复时间变短；底线指标没有变差。底线变差就回退。

## 例二：`ask_ahead`（当前这一步结束前，Jeff 就先问下一步）

- **问题：** 提前问能不能缩短 Jeff 两步之间的等待，同时不让他应付紧急情况的表现变差？
- **改动：** 打开 `ask_ahead`；`request_policy.ask_ahead` 会把开关前后的对局分开统计。
- **按整局比较：** `scripts/model_rounds.py --level level-2 --human assembler`，每组、每个模型各 12 局，用两个模型。
- **主要指标：** 两步之间间隔的中位数（`decision_stats.py` 的 `step_gaps`），附两组之差的 bootstrap 区间。
- **底线指标：** 每局着火和烧糊次数（不能增加）、达标率、被拒绝和被丢弃的回复数。达标率从 0.5 提到 0.8，每组大约需要 39 局才看得出来。所以这 12 局只用来盯住底线指标和间隔，不能证明达标率提高了。
- **决策：** 间隔变短、底线指标没有变差，就上线；否则关掉开关。

## 工具对照

| 单位 | 工具 | 报告内容 |
| --- | --- | --- |
| 时刻 | `python3 scripts/reask.py <检查名> ...`（`list` 列出所有检查） | 带区间的比例、带 McNemar p 值的成对差别、重复一致率；只有一个模型作答时给出提示 |
| 整局，脚本人类 | `python3 scripts/model_rounds.py --rounds N --out DIR` | 每局结果和整组的 `decision_stats` 统计；日志和会话包都在 DIR 里 |
| 整局，真人玩家 | `python3 scripts/decision_stats.py logs/ --split ...` | 按组统计的结果和工作量 |
