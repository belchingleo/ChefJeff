# Privacy and model costs

## Model calls

Each connection test can make one paid model call. During play, decisions continue until paused, disconnected or at the call limit; already-issued requests may still be billed. Failed calls may also incur provider charges.

The default limit is 200 calls per round, configurable to 1–2000 before the next round. This limits calls rather than money. Input size, provider pricing and optional history affect charges; displayed tokens cover successfully parsed usage only. Refer to the provider's bill.

## Local play

Your own Python backend sends the key to the selected HTTPS model endpoint. The default is backend memory. “Remember this device” stores plaintext in `.player-api.json`, restricted to the current user where file permissions are supported; Clear removes it. Local play uses no ChefJeff-hosted game service.

Model inputs include kitchen state, rules, legal actions, recent events and choices. Enabled cross-round memory adds up to three completed rounds for the same endpoint/model, each with at most 18 sampled factual events. Memory lives in `.player-memory.json`; disabling stops reads and additions, and Clear removes saved episodes.

Local `logs/` journals can contain full state and model output. Feedback export uses an allowlist of build/session identifiers, timing, outcomes, call/usage totals, event counts, bookmarks, preset messages and recent action events. It omits credentials, service endpoints, memory and raw model payloads. Preview it before downloading or sharing.

## Hosted pilot

The browser sends model requests directly to the provider; API keys do not pass through the ChefJeff game backend. Keys live in page memory by default and disappear on refresh. Explicit Remember uses browser localStorage in plaintext; Clear removes it. Providers must support browser CORS. A CORS failure does not switch to a server proxy.

Gameplay actions and state are processed on the server. Anonymous sessions remain in memory and expire after 10 minutes of inactivity. No disk gameplay journal or cross-round memory is created. After a round, the player can preview and explicitly contribute allowlisted event/position/result data for game improvement and cooperation evaluation research. Contributions are private, retained for 30 days, and can be deleted using the supplied receipt.

Contributions exclude keys, account identity, email, IP addresses, model endpoints and raw model requests/responses. Network and model providers process traffic under their own policies. The demo operator must keep its reverse-proxy logging and backup practices consistent with this policy. See [deployment](hosted-deployment.md).

---

## 中文说明

# 隐私与模型费用

## 模型调用

每次连接测试最多进行一次可能计费的模型调用。游玩期间持续决策，直到暂停、断开或达到调用上限；已发出的请求仍可能计费，失败调用也可能产生费用。

每局默认上限 200 次，可在下一局前设置为 1–2000 次。这是次数限制，不是金额预算。输入长度、供应商价格和可选历史都会影响费用；界面 token 仅覆盖成功解析的用量，以供应商账单为准。

## 本地游玩

玩家自己的 Python 后端将 Key 发给所选 HTTPS 模型端点，默认仅在后端内存保存。勾选记住设备后，以明文保存在 `.player-api.json`，在支持权限的系统上限制为当前用户访问；清除配置会删除它。本地版不连接 ChefJeff 托管游戏服务。

模型输入包括厨房状态、规则、合法动作、近期事件及选择。开启跨局记忆后，会加入同接口／模型最近三场结束对局，每场最多 18 条抽样事实事件。记忆位于 `.player-memory.json`；关闭后不读取或新增，清空会删除已保存回合。

本地 `logs/` 可包含完整状态与模型输出。反馈导出按允许清单包含构建／对局标识、时间、结果、调用与用量统计、事件计数、标记、预设沟通及近期动作事件，不含凭据、服务端点、记忆和原始模型载荷。下载或分享前请先预览。

## 托管试玩

浏览器直接向供应商请求模型，API Key 不经过 ChefJeff 游戏后端。默认仅保存在页面内存，刷新后消失；主动记住后以明文进入浏览器 localStorage，清除会删除它。供应商必须支持浏览器 CORS；失败时不转为服务器代理。

游戏动作与状态由服务器处理。匿名会话在内存中维持，闲置十分钟后过期，不创建磁盘对局日志或跨局记忆。对局结束后，玩家可以预览并主动贡献允许清单中的事件、位置和结果数据，用于游戏改进与协作评估研究。贡献数据私有保存 30 天，也可用提供的凭证提前删除。

贡献记录不含 Key、账号身份、邮箱、IP、模型端点或完整模型请求／回复。网络与模型供应商仍按各自政策处理通信，试玩运营者需保证反向代理日志与备份方式符合上述政策，详见[部署说明](hosted-deployment.md)。
