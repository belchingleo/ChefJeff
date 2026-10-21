# ChefJeff 模型连接说明

[English](#english) · [隐私说明与反馈](privacy.md)

Jeff 的每一步由你自己的模型账号决定，费用记在你的账号上。这一页说明在线版能直接用哪些服务、怎么填、一局大约花多少钱。

## Key 留在你的浏览器里

- 在线版的 Key 默认只在当前页面的内存里，刷新即消失；勾选「记住此设备」才以明文存进这个浏览器的 localStorage，「清除配置」即删除。
- 浏览器直接把请求发给你选的服务商，Key 不经过我们的服务器。唯一例外是 Jev：只有你明确勾选「同意通过试玩服务器调用 Jev」时，Key 才经我们的服务器转发，且不写入任何日志或记录。
- 详见[隐私说明与反馈](privacy.md)。

## 怎么填

打开「设置 → 连接」，选「模型服务」，填好 Key 后点「测试并连接」。测试会发一次小请求，可能产生少量费用。

「模型服务」按类型分组，选好后接口地址和模型名称会自动填好，下方一行写着大约每局花费和是否实测过：

- **决策模型**（直接从可选动作中选择）
  - **TypeSafe · Jev（推荐）**：勾选「同意通过试玩服务器调用 Jev」。Jev 目前不允许浏览器直连，这一项由服务器转发。已实测整局。
  - **OpenRouter 决策模型**：在 [OpenRouter](https://openrouter.ai/keys) 开 Key。默认是 Microsoft-Decision-1（输入每百万 token 0.042 美元、输出免费，约 ¥0.3–0.7/局）；「模型名称」可以换成 OpenRouter 上[任一决策模型](https://openrouter.ai/models?output_modalities=decisions)的 ID，例如 `typesafe/jev-1.14`、`openai/gpt-6-luna-decisions`、`perplexity/pplx-decider-v1.2`。已实测整局。只读前约 2 千 token 的模型（如 Cloudflare Clef）看不全厨房，不要选。
  - **StartLux-Decision（Bamboo 免费接口）**：在 [Bamboo Relay](https://bamboonode.dev/) 申请 Key，有免费测试额度；请求经第三方中转 Bamboo Relay。接口 `https://api.bamboonode.dev/v1/decisions`，默认模型 `startlux-decision-27b-autothink`，模型名可编辑。本地版和在线版均可选，在线版由浏览器跨域直连 Bamboo Relay。拿不准时会先思考，偶尔较慢，可能超时或超过游戏接受回复的时限；未用真实 Key 验证连接，未实测整局。[官网](https://decision.startlux.com/) · [接口文档](https://github.com/StartLuxLabs/StartLux-Decision/blob/main/docs/api.md)。返回与 Jev 相同的 `answers.next_action.choice` 和 `usage`；`think_mode` 等字段可省略，使用服务端默认值。
  - **Decision 3.0**：开源决策模型，需要自己部署，暂不能选。
- **对话模型**（已为各家关闭深度思考、只要求回一个 JSON）
  - **DeepSeek**：[platform.deepseek.com](https://platform.deepseek.com/api_keys)，模型 deepseek-flash（10 月 17 日起为 V4.1-Flash-1017）。已实测整局。
  - **阿里 qwen-flash**：[阿里云百炼](https://bailian.console.aliyun.com/)，约 ¥0.2–0.3/局。未实测。
  - **豆包 Seed 2.0 lite**：[火山方舟](https://console.volcengine.com/ark)，约 ¥0.7–1.3/局。未实测。
  - **Gemini 2.5 Flash-Lite**：[Google AI Studio](https://aistudio.google.com/apikey)，有限速的免费额度，需要所在网络能访问 Google。未实测。
  - **OpenRouter 对话模型**：同一个 OpenRouter Key，地址已填好（`https://openrouter.ai/api/v1`），「模型名称」填模型页上的 ID（形如「厂商/模型名」）。不会自动关闭思考，挑不带深度思考的模型。未实测。
  - **其他兼容 Chat Completions 的服务**：自己填接口地址和模型名称，例如硅基流动 `https://api.siliconflow.cn/v1`。不会自动关闭思考，思考型模型可能答不完。
- 智谱 GLM-4.7-Flash（免费）只在本地版提供：智谱接口不允许浏览器跨域请求。

我们在 2026-10-19 和 2026-10-20 确认过上述其他在线接口允许浏览器跨域请求；StartLux 的 Bamboo Relay 接口支持跨域直连，但尚未在此项目中用真实 Key 验证。能否真正调用，以你的账号点「测试并连接」的结果为准。模型名称会更新，请以服务商控制台为准。

**响应时限**：对话模型的回复最多 128 个 token，超过 15 秒的回复会被丢弃。决策模型走独立的 systemone 协议，不受这项对话输出上限约束，但过时的回复也会被丢弃（默认本地版 6 秒、在线版 15 秒）。StartLux 的思考可能延长响应时间；连接测试通过不代表整局响应都能及时采用。

## 一局大约多少钱（估算）

- **调用次数**：游戏最多每 2 秒请求一次决策。默认速度下一局 180 游戏秒约 4 分钟，最多约 120 次。开发者用 Jev 玩的 11 个完整对局里，每局 63–120 次，中位数 111 次。
- **每次的输入**：每次请求附带完整的厨房状态和规则，约 2.7–3.7 万字符；Jev 实测每次约 1.4–2 万输入 token。其他模型的分词方式不同，按每次 1–2 万输入 token、几十个输出 token 估算。
- **合计**：一局约 110 万–220 万输入 token，输出只有几千 token，费用主要由输入单价决定：
  - 输入单价每百万 token 1 元：一局约 1–2 元；
  - 每百万 token 0.1 美元：一局约 0.1–0.2 美元；
  - 每百万 token 0.3 美元：一局约 0.3–0.7 美元。
- 服务商的缓存折扣可能让实际费用更低；失败的请求也可能计费。以上只是估算，以服务商账单为准。
- 每局结束后，「设置 → 调用上限」会显示本局的调用次数和成功回复的 token 数，可以据此算出你自己的实际用量。
- 想省钱：在「调用上限」把每局次数调低（默认 200 次，例如 60 次约为一半费用），Jeff 达到上限后不再请求，你仍可以继续操作。

---

## English

[隐私说明与反馈 · Privacy and contact](privacy.md)

Jeff's moves are decided by your own model account and billed to it. This page lists the services the online version can use directly, what to enter, and roughly what a round costs.

### Your key stays in your browser

- Online, the key lives in this page's memory by default and is gone on refresh. Only **Remember on this device** saves it, in plain text, to this browser's localStorage; **Clear credentials** deletes it.
- Your browser sends requests straight to the provider; the key does not pass through our server. The one exception is Jev: only when you explicitly tick **I agree to call Jev through the demo server** is the key forwarded by our server, which never writes it to any log or record.
- See [privacy and contact](privacy.md).

### What to enter

Open Settings → Connection, choose an **AI provider**, paste your key and press **Test and connect**. The test sends one small request, which may cost a little.

**AI provider** is grouped by kind; picking one fills in the base URL and model name, and a line below gives the rough cost per round and whether it has been tested:

- **Decision models** (choose directly from the available actions)
  - **TypeSafe · Jev (recommended)**: tick **I agree to call Jev through the demo server**. Jev does not accept direct browser requests yet, so the server forwards them. Tested over a full round.
  - **OpenRouter decision models**: get a key at [OpenRouter](https://openrouter.ai/keys). The default is Microsoft-Decision-1 (USD 0.042 per million input tokens, output free, about ¥0.3–0.7 a round); the model name can be the ID of [any OpenRouter decision model](https://openrouter.ai/models?output_modalities=decisions), for example `typesafe/jev-1.14`, `openai/gpt-6-luna-decisions` or `perplexity/pplx-decider-v1.2`. Tested over a full round. Avoid models that read only the first ~2,000 tokens (such as Cloudflare Clef): they miss most of the kitchen.
  - **StartLux-Decision (Bamboo free API)**: get a key at [Bamboo Relay](https://bamboonode.dev/), which offers a free testing quota. Requests pass through the third-party Bamboo Relay. The endpoint is `https://api.bamboonode.dev/v1/decisions`, with editable model name `startlux-decision-27b-autothink`. Available locally and online; the browser calls Bamboo Relay directly with CORS. It thinks when uncertain, so responses can occasionally be slow and may time out or arrive too late for the game. No connection verified with a real key and no full round tested. [Website](https://decision.startlux.com/) · [API docs](https://github.com/StartLuxLabs/StartLux-Decision/blob/main/docs/api.md). Responses use the same `answers.next_action.choice` and `usage` as Jev; fields such as `think_mode` can be omitted to use server defaults.
  - **Decision 3.0**: an open decision model you host yourself; not selectable yet.
- **Chat models** (thinking turned off and one JSON object requested for each provider)
  - **DeepSeek**: [platform.deepseek.com](https://platform.deepseek.com/api_keys), model deepseek-flash (V4.1-Flash-1017 since 17 October). Tested over a full round.
  - **Alibaba qwen-flash**: [Model Studio](https://bailian.console.aliyun.com/), about ¥0.2–0.3 a round. Not yet tested.
  - **Doubao Seed 2.0 lite**: [Volcano Ark](https://console.volcengine.com/ark), about ¥0.7–1.3 a round. Not yet tested.
  - **Gemini 2.5 Flash-Lite**: [Google AI Studio](https://aistudio.google.com/apikey), a rate-limited free quota; your network must reach Google. Not yet tested.
  - **OpenRouter chat models**: the same OpenRouter key and a ready-filled address (`https://openrouter.ai/api/v1`); enter the model ID from its page (vendor/model). Thinking is not turned off for you, so pick a model without deep thinking. Not yet tested.
  - **Other Chat Completions provider**: enter the base URL and model yourself, for example SiliconFlow `https://api.siliconflow.cn/v1`. Thinking is not turned off for you, so thinking models may not finish an answer.
- Zhipu GLM-4.7-Flash (free) is offered in the local game only: Zhipu's API does not accept cross-origin browser requests.

On 2026-10-19 and 2026-10-20 we confirmed that the other online endpoints above accept cross-origin browser requests. StartLux's Bamboo Relay endpoint supports direct cross-origin requests, but has not been verified with a real key in this project. Whether a call really works is decided by **Test and connect** with your account. Model names change, so check your provider's console.

**Response limits**: chat replies are capped at 128 tokens and discarded when older than 15 seconds. Decision models use the separate systemone protocol without that chat output cap, but stale replies are also discarded (by default, after 6 seconds locally or 15 seconds online). StartLux's thinking can extend response time; passing the connection test does not establish that replies will arrive in time throughout a round.

### Roughly what a round costs (estimate)

- **Calls**: the game asks for a decision at most once every 2 seconds. At the default speed a 180-game-second round takes about 4 minutes, so at most about 120 calls. In 11 complete rounds the developer played with Jev, rounds made 63–120 calls, median 111.
- **Input per call**: each request carries the full kitchen state and rules, about 27,000–37,000 characters; Jev measured about 14,000–20,000 input tokens per call. Other tokenizers differ, so estimate 10,000–20,000 input tokens and a few dozen output tokens per call.
- **Per round**: about 1.1–2.2 million input tokens and only a few thousand output tokens, so the input price dominates:
  - at 1 CNY per million input tokens: about 1–2 CNY per round;
  - at USD 0.10 per million: about USD 0.10–0.20 per round;
  - at USD 0.30 per million: about USD 0.30–0.70 per round.
- Provider caching discounts may lower this; failed requests may also be billed. These are estimates; your provider's bill is what counts.
- After each round, Settings → Call limit shows that round's calls and the tokens of successful replies, so you can work out your own usage.
- To spend less, lower the per-round call limit (default 200; 60 calls is roughly half the cost). Once Jeff reaches the limit he stops asking and you can keep playing.
