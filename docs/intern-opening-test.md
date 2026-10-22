# Intern-Decision opening test

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
