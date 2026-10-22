# Intern-Decision opening test

## Archived result — 2026-10-22

**Cancelled at the user's request.** [PR #32](https://github.com/belchingleo/ChefJeff/pull/32) is closed and unmerged. The experiment was not deployed; the main branch and online game were not changed by this integration. Branch `codex/intern-decision` and the script are retained as an experiment record. The instructions below describe the archived experiment, not a request to resume testing.

The user ran the following real-API tests locally and supplied terminal screenshots. These observations are distinct from the developer's offline tests; no credentials or raw player records are included here.

| Level | Input tokens | Output tokens | Latency (seconds) | Result |
| --- | --- | --- | --- | --- |
| 1 | 6508 | 21 | 3.555 | Accepted; legal `fetch` choice, `sprint: false` |
| 2 | Not returned | Not returned | Not recorded | HTTP 400: context limit exceeded |
| 3 | Not returned | Not returned | Not recorded | HTTP 400: context limit exceeded |

Both failures reported: `estimated input tokens exceed the model's context limit`. Their actual token counts and response times are unknown; request bytes must not be substituted for either measurement. The request byte counts (original → compact) were 27502 → 25314 for level 1, 36497 → 30995 for level 2, and 36268 → 31576 for level 3.

Reproduction point: source commit `39d3c299c15ea7cf536f4d439759fdbad3c26fc9`, format `chefjeff-opening-sparse-jsonl-v1`, model `intern-decision-4b`, official endpoint `https://discovery-api.intern-ai.org.cn/v1/systemone`, documented context limit 8192 tokens. Each run used one first-decision request, the selected level, order seed 1, spawn seed 0, fresh empty cross-round memory, and a 20-second probe timeout. The script verified restoration of every original JSON value and preserved the action/sprint candidate sets. This verifies structural preservation, not identical model interpretation or behavior.

Conclusion: the short connection probe worked, but original gameplay input was refused as overlength. Reversible format compression allowed the first level's opening request; it did not fit the openings of levels 2 and 3. No later states, complete rounds, useful cooperation, sustained latency, or browser CORS were validated. This is a context-budget limitation of this integration attempt, not an assessment of the model's decision quality. The normal game never adopted the experimental compact format.

If the user later resumes this work, start from these known results and the retained branch. A larger supported context or a separately validated input representation may make a new attempt worthwhile. Recheck all three openings, later-state growth and game response deadlines before claiming gameplay support. Do not silently truncate evidence, infer model quality from acceptance failures, or restart paid tests as part of recording this cancellation.

The archived implementation had 27 focused offline tests passing (9 opening/protocol/privacy checks, 4 generated-page checks, 14 release checks), and its 501-file test package passed hash and sensitive-marker checks. Those checks do not override the real-API failures above.

## Archived procedure

This experiment sends **one first-decision request**, not the tiny connection probe and not a game round. The original full input was refused by Intern InkStone with HTTP 400, `estimated input tokens exceed the model's context limit`. The provider's 8192-token limit still applies.

From an extracted source checkout, run:

```sh
python3 scripts/probe_intern_opening.py
```

Paste your own InkStone API key at the hidden terminal prompt. The script does not load saved credentials or player memory, save the key, write game logs, run a server, execute an action, retry, or change game/server configuration. It makes one request to the fixed official endpoint; redirects are refused. Keep the key out of commands and screenshots.

The default is level 1 with order seed 1 and spawn seed 0, fresh local memory, and the normal scheduler's first complete payload, including rules, recent-event context, memory context and both choice questions. Experimental format `chefjeff-opening-sparse-jsonl-v1` shares repeated station/equipment fields as explicit defaults and renders the state as compact JSON lines. A round-trip check restores every original JSON value before any network request. Rule wording, candidate actions and sprint choices are preserved. Presentation changes can affect model behavior; this is not a comparison using identical prompts.

Success prints `outcome: success`, a valid action and sprint choice, `input_tokens`, `output_tokens`, and `latency_seconds`. Byte counts are **not token estimates**. The 20-second probe timeout allows measuring request acceptance and response latency; it does not change the game's shorter timeout or response-age limits. Acceptance of the first request proves neither useful actions nor compatibility with later states or full rounds. The normal game still sends its original input; this experimental format is only used by this script.

Optional checks, each requiring a separate invocation:

```sh
# Offline: no key prompt and no network request.
python3 scripts/probe_intern_opening.py --dry-run
# Another level's opening: exactly one request per invocation.
python3 scripts/probe_intern_opening.py --level 2
python3 scripts/probe_intern_opening.py --level 3
# Explicit control: the original, potentially overlength input.
python3 scripts/probe_intern_opening.py --uncompressed
```

## 中文操作

解压新的源码包，在终端输入 `cd ` 后拖入解压后的文件夹并回车，再运行：

```sh
python3 scripts/probe_intern_opening.py
```

提示输入 Key 时粘贴你自己的端砚 Key，再回车；输入不会显示，也不会保存。默认只测第一关开局的一条完整决策请求，调用一次后退出，不操作正在玩的游戏。把最后的结果发回来即可，不要提供 Key。

`outcome` 为 `success` 表示这条输入被接受并返回了合法选择；重点看 `input_tokens` 和 `latency_seconds`。为测量延迟，脚本允许等待 20 秒，游戏原有超时没有调整。字节数不是 Token 数，开局通过也不代表能玩完整局。

压缩只改变数据表示方式：共享重复字段、使用紧凑文本；发送前校验能还原全部规则和状态，不截断规则或减少动作。它暂时仅用于这个测试脚本，普通游戏的输入没有改动。测试采用固定种子和全新的空跨局记忆，与已有记忆的实际对局不完全相同。

## 取消与实测记录（2026-10-22）

用户决定暂时取消 Intern-Decision 接入。PR #32 已关闭，未合并、未部署；线上游戏未因本次接入发生改动。实验分支 `codex/intern-decision`、脚本和说明保留，以上命令仅作为历史复现步骤，不表示继续测试。

- 测试源码：`39d3c299c15ea7cf536f4d439759fdbad3c26fc9`；压缩格式：`chefjeff-opening-sparse-jsonl-v1`；模型：`intern-decision-4b`；上下文上限：8192 Token。
- 第一关：成功，输入 **6508 Token**、输出 **21 Token**，单次延迟 **3.555 秒**，返回合法动作 `fetch`、`sprint: false`。
- 第二、三关：均返回 **HTTP 400**，原因为 `estimated input tokens exceed the model's context limit`。接口未提供 Token 用量，截图未记录耗时，不估算其实际值。
- 三关均只测试了各自开局的第一条完整请求，固定订单种子 1、出生种子 0，使用全新的空跨局记忆，每次调用一次、测试超时 20 秒。结果来自用户本地实测截图。
- 当前可还原全部 JSON 数据的压缩，只使第一关的开局请求被接受；第二、三关开局仍超限。第一关后续状态与完整对局也没有验证，不能标记为正式可用，也不能据此判断模型决策能力好坏。普通游戏没有启用实验压缩。
- 若以后明确恢复，再从保留的分支继续，优先确认是否支持更长上下文，或验证新的输入表示；需覆盖三关开局、后续状态增长和游戏接受回复的时限。本次记录工作不重新调用模型，不合并、不部署。
