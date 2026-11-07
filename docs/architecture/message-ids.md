# Page text by message ID (design, not yet implemented)

Status: proposal. The guard in `tests/test_localization.py` (`PageMessageGuardTests`) is in place; the migration below is scheduled separately, after the current work on Jeff's input format and decision loop, because it touches the same server modules.

## Today

The server writes its page text in Chinese. The page translates it for English players by looking the text up in `cocos-kitchen/i18n.json`: 1131 whole messages, then 236 templates with `{n}` fields matched as regular expressions, and finally a fallback that replaces any catalog fragment found inside the text. Jeff's English input is produced the same way, from Chinese, by `model_language.py` with its own catalog (`model-language-en-v4.json`: 374 messages and 123 templates).

This works, but has three costs:

- **Silent loss.** Rewording a Chinese message on the server breaks its English text with no error. Before the guard, 27 of the 187 messages that reach the page from server code had no English entry.
- **Half translations.** The fragment fallback turns an unknown sentence into a mixture, for example `请填写完整的 API Key，不要包含Space或换行。`, which is worse than either language.
- **A third language costs a full reverse catalog.** Every language would need the same Chinese-keyed tables and regular expressions, and the Chinese text would stay the key of every message.

## Proposal

The server sends a message as an ID with fields, and keeps the Chinese text beside it during the migration:

```json
{"error": "请选择 API 服务。", "error_id": "settings.provider_missing"}
{"note": "Jeff 请求失败：…", "note_id": "jeff.request_failed", "fields": {"error": {"id": "model.unreachable"}, "retry": 4}}
```

- One catalog per language, keyed by ID: `i18n/zh.json`, `i18n/en.json`. A field can itself be a message (`{"id": ...}`), so nested messages such as a model error inside "Jeff's request failed" translate without regular expressions.
- The page renders the ID when it knows it and falls back to today's lookup on the Chinese text otherwise, so an older page or server keeps working while modules move one at a time.
- A test enumerates every ID the server can emit (from the code, as the guard does today) and requires an entry in every catalog, and every catalog entry to be used.
- Journals, session bundles and research records keep the text they record today. Adding the ID beside it is an additive field. Removing the Chinese text would change record formats and is not part of this plan.

## Not in scope

Jeff's model input. `model_language.py` also translates Chinese engine text into English, but that text is model input: changing how it is produced is a model-prompt change, guarded byte for byte by the payload fingerprints. If the engine later emits IDs, Jeff's English can come from the same English catalog. That needs a separate, versioned decision (`input_language`).

## Order

1. Guard (done): every message the page modules send has English, and every allowlisted exception is named with where it goes instead.
2. Error replies and notes from `web_server.py`, `player_api.py` and `hosted_server.py`, the most visible and the smallest set.
3. Engine labels and event messages (`kitchen.py`, `spatial_kitchen.py`): many templates, and they reach both the page and Jeff, so done together with the payload-fingerprint check that Jeff's input is unchanged.
4. Remove the fragment fallback once no page text depends on it. A test then fails on any untranslated text instead of producing a mixture.

---

## 中文说明

# 页面文字改用消息 ID（设计，尚未实施）

状态：提案。`tests/test_localization.py` 里的守卫（`PageMessageGuardTests`）已经就位。下面的迁移另行排期，排在 Jeff 输入格式和决策循环的改动之后，因为两边会动到同一批服务器模块。

## 现状

服务器用中文写页面文字。英文玩家看到的英文，是页面拿这段中文去 `cocos-kitchen/i18n.json` 里查出来的：先查 1131 条整句；再用 236 条带 `{n}` 字段的模板按正则匹配；最后还有一个兜底，把文字里出现的任何词条片段替换掉。Jeff 收到的英文输入也是这样从中文翻过去的，由 `model_language.py` 用另一份词表（`model-language-en-v4.json`：374 条整句、123 条模板）完成。

这套办法能用，但有三个代价：

- **静默丢失。** 服务器改了一句中文，对应的英文就失效了，而且不会报错。守卫加入之前，服务器代码送到页面的 187 条消息里有 27 条没有英文。
- **半中半英。** 片段兜底会把不认识的句子变成混合文字，例如 `请填写完整的 API Key，不要包含Space或换行。`，比哪种语言都难读。
- **加第三种语言要再做一整套反查表。** 每种语言都需要同样以中文为键的词表和正则，中文原文也就一直是所有消息的键。

## 提案

服务器发送"消息 ID + 字段"，迁移期间在旁边保留中文原文：

```json
{"error": "请选择 API 服务。", "error_id": "settings.provider_missing"}
{"note": "Jeff 请求失败：…", "note_id": "jeff.request_failed", "fields": {"error": {"id": "model.unreachable"}, "retry": 4}}
```

- 每种语言一份以 ID 为键的词表：`i18n/zh.json`、`i18n/en.json`。字段本身也可以是一条消息（`{"id": ...}`），这样像"Jeff 请求失败"里面套着的模型错误这种嵌套消息，不用正则也能翻译。
- 页面认识这个 ID 就按 ID 显示，不认识就退回今天的中文反查。这样旧页面配新服务器、新页面配旧服务器都能工作，模块可以一个一个地迁。
- 用测试列出服务器可能发出的每个 ID（像现在的守卫一样从代码里读），要求每份词表都有对应条目，每个词条也都有人用。
- 日志、会话包和研究记录继续记今天记的文字，ID 只是在旁边新增一个字段。去掉中文原文会改变记录格式，不在本计划之内。

## 不在范围内

Jeff 的模型输入。`model_language.py` 也负责把引擎的中文文字翻成英文，但那是模型输入：改它的生成方式就是改模型提示，由 payload 指纹逐字节把关。以后引擎改发 ID 时，Jeff 的英文可以直接取自同一份英文词表，但这需要单独、带版本号（`input_language`）的决定。

## 顺序

1. 守卫（已完成）：页面模块发出的每条消息都有英文；白名单里的例外都写明了它们实际去了哪里。
2. 先迁 `web_server.py`、`player_api.py`、`hosted_server.py` 的错误回复和提示：这部分最显眼，数量也最少。
3. 再迁引擎的标签和事件消息（`kitchen.py`、`spatial_kitchen.py`）：模板多，而且同时送给页面和 Jeff，所以要和"Jeff 输入不变"的 payload 指纹检查一起做。
4. 页面文字都不再依赖片段兜底之后，删掉兜底。从那以后，任何没有翻译的文字都会让测试失败，而不是显示成混合文字。
