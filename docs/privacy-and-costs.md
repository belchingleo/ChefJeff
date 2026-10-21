# Privacy and model costs

## Model calls

Each connection test can make one paid model call. During play, decisions continue until paused, disconnected or at the call limit; already-issued requests may still be billed. Failed calls may also incur provider charges.

The default limit is 200 calls per round, configurable to 1–2000 before the next round. This limits calls rather than money. Input size, provider pricing and optional history affect charges; displayed tokens cover successfully parsed usage only. Refer to the provider's bill.

## Local play

Your own Python backend sends the key to the selected HTTPS model endpoint. The default is backend memory. “Remember this device” stores plaintext in `.player-api.json`, restricted to the current user where file permissions are supported; Clear removes it. Local play uses no ChefJeff-hosted game service.

Model inputs include kitchen state, rules, legal actions, recent events and choices. Enabled cross-round memory adds up to three completed rounds for the same endpoint/model, each with at most 18 sampled factual events. Memory lives in `.player-memory.json`; disabling stops reads and additions, and Clear removes saved episodes.

Local `logs/` journals can contain full state and model output. Each local round also writes a session record bundle under `logs/sessions/<session-id>/` (frozen configuration, event stream, engine inputs and the exact model requests); it is derived from the same stream as the journal, contains no credentials, and stays on your computer. Feedback export uses an allowlist of build/session identifiers, timing, outcomes, call/usage totals, event counts, bookmarks, preset messages and recent action events. It omits credentials, service endpoints, memory and raw model payloads. Preview it before downloading or sharing.

## Hosted pilot

Browser-direct mode sends model requests and keys only to the provider and requires provider CORS. A CORS failure never switches transport automatically. For Jev, players can explicitly select **I agree to call Jev through the demo server**. In this mode their key and model request pass over HTTPS through the ChefJeff server to the fixed TypeSafe Jev endpoint. The server uses the key only while processing that request and does not write it or model payloads to configuration, logs, game records or contribution storage. Already-issued calls may still be billed after cancellation or a page exit.

Keys live in page memory by default and disappear on refresh. Explicit Remember stores the key **and chosen transport** in browser localStorage in plaintext; Clear removes them. A remembered Jev relay choice remains in effect on that device until cleared or changed. Browser-direct remains the default for new/older saved configurations and for other providers. The game server never supplies a developer key.

Gameplay actions and state are processed on the server. Anonymous sessions remain in memory and expire after 10 minutes of inactivity. No disk gameplay journal or cross-round memory is created. Before the first round the page asks once, with two equal choices and nothing preselected, whether to contribute every later round; after "not now" the result card offers a one-tap contribution of that round. Contributions hold allowlisted event/position/result data for game improvement and cooperation evaluation research, are private, retained for 30 days, and can be deleted using the receipt kept in the browser. The player-facing summary is [privacy and contact](privacy.md); costs per round are estimated in the [model connection guide](model-guide.md).

Contributions exclude keys, account identity, email, IP addresses, model endpoints and raw model requests/responses. Network and model providers process traffic under their own policies. The demo operator must keep its reverse-proxy logging and backup practices consistent with this policy. See [deployment](hosted-deployment.md).

The hosted server also retains aggregate visit/start/completion/end/capacity counts, per-level starts/completions, and duration bucket counts with summed game/effective seconds for the service's lifetime. It keeps no individual visit or round analytics records. Browsers use two fixed localStorage booleans to report a first visit/play, without generating an identifier or fingerprint; only aggregate browser estimates are persisted. Storage-disabled browsers are omitted; clearing storage, private browsing, different devices, retries and tab races can skew estimates. No IPs, credentials, model information, cookies or session/round identifiers are added to persistent statistics. This counting is independent of opting into detailed 30-day round contributions, and earlier traffic cannot be backfilled. Operator queries stay loopback-only; see [deployment](hosted-deployment.md).

---

## 中文说明

# 隐私与模型费用

## 模型调用

每次连接测试最多进行一次可能计费的模型调用。游玩期间持续决策，直到暂停、断开或达到调用上限；已发出的请求仍可能计费，失败调用也可能产生费用。

每局默认上限 200 次，可在下一局前设置为 1–2000 次。这是次数限制，不是金额预算。输入长度、供应商价格和可选历史都会影响费用；界面 token 仅覆盖成功解析的用量，以供应商账单为准。

## 本地游玩

玩家自己的 Python 后端将 Key 发给所选 HTTPS 模型端点，默认仅在后端内存保存。勾选记住设备后，以明文保存在 `.player-api.json`，在支持权限的系统上限制为当前用户访问；清除配置会删除它。本地版不连接 ChefJeff 托管游戏服务。

模型输入包括厨房状态、规则、合法动作、近期事件及选择。开启跨局记忆后，会加入同接口／模型最近三场结束对局，每场最多 18 条抽样事实事件。记忆位于 `.player-memory.json`；关闭后不读取或新增，清空会删除已保存回合。

本地 `logs/` 可包含完整状态与模型输出。每局还会在 `logs/sessions/<会话 id>/` 生成对局记录包（冻结配置、事件流、引擎输入与实际发送的模型请求），与日志同源派生，不含凭据，只保存在本机。反馈导出按允许清单包含构建／对局标识、时间、结果、调用与用量统计、事件计数、标记、预设沟通及近期动作事件，不含凭据、服务端点、记忆和原始模型载荷。下载或分享前请先预览。

## 托管试玩

服务器另外保留访问、开局、自然完成、手动结束、满员拒绝等累计数，分关卡的开局／完成数，以及按结束方式分组的时长区间次数和游戏／有效游玩总秒数，在服务运营期间保留。不保存逐个访客或逐局的统计明细。浏览器用两个固定的 localStorage 是／否标记上报首次访问／试玩，不生成独立编号或指纹，服务器只保存估算汇总数。禁用存储时跳过浏览器估算；清除数据、无痕、换设备、重试或多标签竞争会使估算有偏差。统计不保存 IP、凭据、模型信息、Cookie 或会话／对局标识，无法补算启用前的访问；与自愿贡献的 30 天记录分别处理。查询入口只允许服务器本机访问，详见[部署说明](hosted-deployment.md)。

浏览器直连模式只将模型请求和 Key 发给供应商，要求其支持 CORS；失败不会自动切换转发。Jev 玩家可明确勾选**同意通过试玩服务器调用 Jev**。此模式下，Key 和模型请求经 HTTPS 通过 ChefJeff 服务器发往固定的 TypeSafe Jev 接口。服务器仅在处理该请求时使用 Key，不将其或模型载荷写入配置、日志、对局记录或贡献存储。取消请求或关闭页面时，已经发出的调用仍可能计费。

Key 默认保存在页面内存，刷新后消失；主动记住会将 **Key 和所选转发方式**以明文保存至浏览器 localStorage，清除会删除它们。被记住的 Jev 转发选项在该设备上持续有效，直到清除或更换。新配置／旧的已记住配置默认浏览器直连，其他供应商也保持直连；游戏服务器不提供开发者 Key。

游戏动作与状态由服务器处理。匿名会话在内存中维持，闲置十分钟后过期，不创建磁盘对局日志或跨局记忆。第一局前页面会问一次是否以后每局自动贡献，两个选项同等、没有默认；选「暂不」后，结算画面可一键贡献这一局。贡献内容为允许清单中的事件、位置和结果数据，用于游戏改进与协作评估研究，私有保存 30 天，也可用浏览器里保存的凭证提前删除。面向玩家的说明见[隐私说明与反馈](privacy.md)，每局费用估算见[模型连接说明](model-guide.md)。

贡献记录不含 Key、账号身份、邮箱、IP、模型端点或完整模型请求／回复。网络与模型供应商仍按各自政策处理通信，试玩运营者需保证反向代理日志与备份方式符合上述政策，详见[部署说明](hosted-deployment.md)。
