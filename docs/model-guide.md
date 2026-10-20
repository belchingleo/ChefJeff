# ChefJeff 模型连接说明

[English](#english) · [隐私说明与反馈](privacy.md)

Jeff 的每一步由你自己的模型账号决定，费用记在你的账号上。这一页说明在线版能直接用哪些服务、怎么填、一局大约花多少钱。

## Key 留在你的浏览器里

- 在线版的 Key 默认只在当前页面的内存里，刷新即消失；勾选「记住此设备」才以明文存进这个浏览器的 localStorage，「清除配置」即删除。
- 浏览器直接把请求发给你选的服务商，Key 不经过我们的服务器。唯一例外是 Jev：只有你明确勾选「同意通过试玩服务器调用 Jev」时，Key 才经我们的服务器转发，且不写入任何日志或记录。
- 详见[隐私说明与反馈](privacy.md)。

## 怎么填

打开「设置 → 连接」，选「模型服务」，填好 Key 后点「测试并连接」。测试会发一次小请求，可能产生少量费用。

- **DeepSeek**：选「DeepSeek」，模型名称已填好 deepseek-flash，只需粘贴 Key（[platform.deepseek.com](https://platform.deepseek.com/api_keys)）。
- **TypeSafe · Jev**：选「TypeSafe · Jev（推荐）」，并勾选「同意通过试玩服务器调用 Jev」。Jev 目前不允许浏览器直连，这一项由服务器转发。
- 下面几家选「其他兼容 Chat Completions 的服务」，填接口地址和模型名称：
  - **阿里云百炼（通义千问 Qwen）**：接口地址 `https://dashscope.aliyuncs.com/compatible-mode/v1`（国际站 `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`），模型如 qwen-plus、qwen-flash。
  - **Google Gemini（OpenAI 兼容接口）**：接口地址 `https://generativelanguage.googleapis.com/v1beta/openai`，模型如 gemini-2.5-flash-lite。需要所在网络能访问 Google。
  - **OpenRouter**：接口地址 `https://openrouter.ai/api/v1`，模型名称从 OpenRouter 模型页复制，形如「厂商/模型名」。
  - **硅基流动 SiliconFlow**：接口地址 `https://api.siliconflow.cn/v1`（国际站 `https://api.siliconflow.com/v1`），模型名称从模型广场复制，形如「厂商/模型名」。

我们在 2026-10-19 确认过以上接口允许浏览器跨域请求；能否真正调用，以你的账号点「测试并连接」的结果为准。模型名称会更新，请以服务商控制台为准。

**选模型的建议**：选响应快、不带深度思考（reasoning / thinking）的模型。每一步只需要回答一个动作，回复最多 128 个 token；思考型模型容易超时或回复被截断，超过 15 秒的回复会被丢弃。

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

- **DeepSeek**: choose DeepSeek; the model name deepseek-flash is filled in, so only the key is needed ([platform.deepseek.com](https://platform.deepseek.com/api_keys)).
- **TypeSafe · Jev**: choose TypeSafe · Jev (recommended) and tick **I agree to call Jev through the demo server**. Jev does not accept direct browser requests yet, so the server forwards them.
- For the following, choose **Other Chat Completions provider** and enter the base URL and model name:
  - **Alibaba Cloud Model Studio / DashScope (Qwen)**: base URL `https://dashscope.aliyuncs.com/compatible-mode/v1` (international `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`), models such as qwen-plus or qwen-flash.
  - **Google Gemini (OpenAI-compatible endpoint)**: base URL `https://generativelanguage.googleapis.com/v1beta/openai`, models such as gemini-2.5-flash-lite. Your network must reach Google.
  - **OpenRouter**: base URL `https://openrouter.ai/api/v1`; copy the model ID from OpenRouter's model page (vendor/model).
  - **SiliconFlow**: base URL `https://api.siliconflow.cn/v1` (international `https://api.siliconflow.com/v1`); copy the model ID from its model square (vendor/model).

On 2026-10-19 we confirmed that these endpoints accept cross-origin browser requests; whether a call really works is decided by **Test and connect** with your account. Model names change, so check your provider's console.

**Choosing a model**: pick a fast model without deep thinking (reasoning). Each step only needs one action and replies are capped at 128 tokens; thinking models tend to time out or get cut off, and replies older than 15 seconds are discarded.

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
