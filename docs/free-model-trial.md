# 可选免费试玩与智谱输出约束

免费试玩默认关闭。它不是运行接口测试脚本之后自动启用的功能。
只有智谱与 StartLux 在上海、德国都通过固定模型的合成快照、少量并发与完整模拟对局验证后，
才能安排维护窗口启用。尚未通过的真实接口测试不能用离线 mock 测试代替。
操作者已同意以全站智谱 1、StartLux 1 的保守上限进行小规模试运行。
智谱账号并发 1 已确认，Bamboo 的正式最大额度仍未知，不承诺大规模容量。
两地区通过上海的独立协调服务统一控制调用和开局名额。

## 智谱格式修复

`model_output.py` 给智谱固定模型构建输出约束：列出实际候选 action key；
明确把冲刺问题的 `yes` / `no` 编码为 JSON 布尔值 `true` / `false`。
无冲刺问题时省略该字段。保持 `max_tokens=128`、关闭思考、JSON 模式。
JSON 模式并不能保证字段类型；系统消息提供具体 schema，返回值仍由程序严格校验。
不会把 `"false"`、`"no"`、数字或 null 自动转成合法值，不修改厨房输入、候选动作、规则或英文词典。
输出约束版本为 `zhipu-choice-boolean-v1`；本地、服务端和浏览器共用匹配的约束，探测报告单独记录此版本。
格式修复无法消除智谱的 1305 平台过载；遇到过载应间隔后补测。

## 开局前选择

开启后，无自有模型配置的页面自动选中运维指定的免费模型；已有自有配置保持原选择。
选中和切换本身不消耗模型请求。玩家可在开局前或结算后，一键选择两种免费模型。
运行和暂停期间，浏览器与服务端都拒绝更换。本局模型身份在开局时固定；
结算后换模型不会改写上一局的模型身份、导出或贡献记录。
研究记录仍按原有同意版本决定是否保存，不把选择免费模型视为研究贡献同意。
免费模式与自有 Key 模式的浏览器跨局记忆使用不同作用域，模型间也互相隔离。

页面沿用像素字体和方角按钮，免费选择面板使用海军蓝。
公开模型的完整名称、API 接入平台、默认选择及理由、每局额度和自有模型入口。
默认选择理由描述接口特点，不把少量样本当作模型能力排名。

## 服务端边界

服务器只允许登记过的固定免费模型和固定 HTTPS 端点，无其他模型回退。最初两家（智谱、StartLux）必须同时验证；之后的模型各自凭自己的 Key 启用，见下文“后加入的免费模型”。
客户端不能提交 API Key、模型 ID、URL 或任意 payload，只能提交所选服务与自己的待处理请求 ID；
真正的厨房输入由服务器当前请求重建。来源、会话、游戏 ID、阶段和请求 ID 均须匹配。
响应仅保留候选内动作、合法冲刺、数值用量及候选内概率。
不打印上游错误正文、返回的模型名称、请求头、私密配置或 Key。
HTTP 错误触发至少 60 秒冷却；鉴权错误、模型不符或上游结果不确定的超时会持久阻断。
恢复需操作者确认上游空闲，在协调服务停止后执行恢复命令，保留预算并再冷却 60 秒。
无自动重试；暂停、结束或进入下一局后，迟到的回复会被丢弃。

## 全站协调与名额

独立的 `free_model_gateway.py` 在上海 loopback 8798 运行；模型 Key 只由这个服务读取。
上海使用 loopback，德国通过既有 data 域名的 `/v1/free-models/` 前缀访问。
复用已存在的分站身份，后端间认证；浏览器从不获得站点令牌或模型 Key。
Nginx 只为该前缀增加新位置，原贡献记录和统计路由保持不变；无需重启共享数据服务或管理台。

全站合计的初始保护：

- 每个模型 1 个免费厨房名额、最多 1 个在处理的上游请求。
- 每个模型每分钟最多 30 次；两家合计滚动一小时 300 次、滚动 24 小时 1000 次尝试。
- 每局最多 200 次免费调用，失败尝试也占额度；玩家不能通过设置自有调用上限绕过。
- 开局前申请名额，满额不启动游戏计时。选择模型本身不预占名额，也不调用模型。
- 每五秒续期，租约 45 秒；结束、断开或异常时释放，暂停停止续期，到期后继续需重新申请。
- 暂停后再继续保留本局调用计数；协调服务重启后旧局不能重置预算继续调用，需结束后重新开局。
- 相同待处理决策重复请求返回缓存，不重复调用上游；同一名额不会被不同分站同时占用。
- 请求在处理期间，即使名额租约过期或已释放，也必须等它完成才允许新厨房取得对应名额。
- 不提供无限排队；页面显示全站占用情况。小规模试运行的名额按先到先得申请，不承诺排队顺序。

预算保存在独立的 `/var/lib/chefjeff-free/budget.json`，只有聚合时间、型号、调用数量和断路标志，
没有 Key、站点令牌、玩家记录、请求内容或回复正文。文件原子写入并同步，权限 0600；独占锁防止两个进程使用同一预算目录。
每次调用前先持久保存进行中标记。重启时发现未完成标记会阻断对应模型，不能借重启绕过调用预算。
这一个文件不属于贡献数据库或访问统计，协调服务沙箱禁止访问这些目录。

这些额度是保守试运行预算，不是服务商的实际额度；尤其一小时 300 次不足以承诺持续多人容量。
Bamboo 最大额度仍需确认后才能考虑增加名额。游戏回复约 15 秒后过期，不积压长队列。

## 后续启用流程（本次不执行）

按现有分站发布流程将同一提交部署到两站，并保留旧发布目录。
服务器测试 Key 配置可沿用 `chefjeff-private-api-keys-v1` 格式，但生产配置需置于发布目录和公开网页目录之外，
只允许 root / 服务用户读取（0600，或 root 所有、服务专属组可读的 0640）。
两家 Key 都必填；只读加载，不自动修改配置。不要提交含 Key 的配置文件。

部署分为准备、审阅、激活三个步骤：

1. 从固定 GitHub 提交构建两次、确认包 SHA-256 一致，并将同一包暂存到两站，不切换 current。
2. 上海 `deploy/install_free_gateway.py prepare`：创建专属服务账户和私密配置副本；生成 Nginx 差异与服务单元并校验候选配置。此时不启动服务，不改动现有 Nginx 路由。
3. 审阅后激活新协调服务并 reload Nginx。不重启游戏、共享数据服务或管理台。
4. 两站各运行 `scripts/probe_free_gateway.py`，每站最多两次真实免费模型请求，使用内置合成快照，不连接线上厨房。
5. 再审阅 `deploy/install_free_region.py prepare` 的候选参数；确认允许结束当前对局后激活游戏代码，保留旧发布目录和回滚入口。

游戏服务仅增加 `--free-model-gateway` 开关，通过现有私密 shared-config 连接唯一协调服务。
取消分站直接读取站点模型 Key 的启用入口，防止两站各自绕过全站并发控制。
所有 root 操作和重启仍由操作者在看到具体命令与审阅结果后执行。
备案域名、CV、VPN、管理台绑定、已有贡献数据和统计文件均不改动。
真实完整模型对局质量仍需后续操作者体验验证；本地 mock 完整对局不能代表真实模型水平。

## 离线验证

```bash
python3 -m unittest discover -s tests
node tests/hosted_browser_test.cjs
node tests/auto_contribution_test.cjs
```

测试使用临时文件、合成厨房及 mock 上游。开发验证不读取线上玩家记录，也不调用任何付费或真实模型。


## Failure diagnostics and recovery

Free calls expose only allowlisted operational fields: provider, safe error category,
upstream HTTP status, numeric provider error code, elapsed time, whether an upstream
request was actually made, and the remaining cooldown. No prompt, response text,
credential or player identifier enters the gateway summary.

A platform rejection (including Zhipu 429/1305) waits for the gateway cooldown.
An invalid action/format waits two seconds. The regional scheduler uses that deadline
instead of adding its generic exponential backoff. Local cooldown and budget denials
are marked as deferred requests, not additional upstream API calls. The existing
stale/job-change checks still decide whether a successful answer may execute.

Unknown transport outcomes, authentication failures and model mismatches retain the
existing fail-closed block. These are not automatically cleared or retried. The page
shows a paused service; players may choose another model after ending the round.

The ordinary **Settings → Data and contributions** download includes per-round
`free_model_diagnostics`; this does not require research contribution consent. These
entries live only in the page session until export/closure. Research schema, consent,
retention and database export validation stay unchanged. Research ZIPs from earlier
rounds cannot retroactively recover the upstream error codes.

`/var/lib/chefjeff-free/diagnostics.json` is a separate, bounded private file containing
only each provider's upstream-attempt counter and latest safe result. It never changes
or replaces `budget.json`. Authenticated operators can run
`sudo python3 /opt/chefjeff/current/scripts/free_gateway_status.py` on either region to
read this summary without making any model API calls or reading player databases.
The most recent result is shared across players; it is not a full per-player history.

### Upgrade an already running free-model deployment

This upgrade expects the game release `b98a4fc6b8e8` on both regions and the gateway
running from that release in Shanghai (both checked on the servers on 2026-11-01). Build the pinned GitHub commit
archive twice and require matching SHA-256 before staging. The regional installer
preserves and restores the existing free-model startup override on rollback.

On Shanghai, use `deploy/upgrade_free_gateway.py prepare`, review its output, then
`activate --allow-round-end`, with the staged `--release` and `--manifest-sha`.
This replaces only the gateway unit's code paths and restarts `chefjeff-free.service`;
credentials, Nginx, the locked budget and data/admin services are retained. Existing
free-model leases expire on gateway restart. Update both game regions in the same
maintenance window using `deploy/install_free_region.py`. New game verification
requires gateway `diagnostics_version: 1` and performs zero model calls.

Both installers retain the previous release/unit and support explicit `rollback`.
Rollback the games first, then the gateway. The old gateway ignores the additional
private summary file; its budget schema is unchanged. Root commands, game restarts
and link switches must be executed by the operator after reviewing the fixed release.

## 后加入的免费模型：Gemini 3.5 Flash-Lite、Gemma 4 26B、Llama 3.1 8B

2026-11-01 加入登记，代码默认不启用。三者都只在开发者的 Mac 上用第一关合成快照各成功调用过一次；
服务器出口、整局和并发都还没有验证。

| 模型 | 平台 | 固定模型 ID | 研究记录服务名 |
| --- | --- | --- | --- |
| Gemini 3.5 Flash-Lite | Google AI Studio | `gemini-3.5-flash-lite` | `gemini` |
| Gemma 4 26B | Cloudflare Workers AI | `@cf/google/gemma-4-26b-a4b-it` | `cloudflare` |
| Llama 3.1 8B | Cloudflare Workers AI | `@cf/meta/llama-3.1-8b-instruct-fp8` | `cloudflare` |

**Key 文件。** 它们的 Key 放在单独的私密文件 `/etc/chefjeff-free/extra-model-keys.json`，
格式 `chefjeff-private-extra-keys-v1`，可选字段 `gemini_api_key`、`cloudflare_api_key` 和 `cloudflare_account_id`（32 位十六进制，
和 Cloudflare Key 必须同时出现）。文件里写了哪个平台，才启用那个平台的模型。原来的 `model-keys.json` 和它的格式不变，
所以协调服务回滚到旧版本时仍能启动。权限要求与原文件相同。

**额度。** 每个平台一个独立的预算目录（`/var/lib/chefjeff-free/gemini`、`/var/lib/chefjeff-free/cloudflare`），
原来的 `budget.json` 不变。上限都低于平台的免费额度：

- Gemini：每分钟最多 14 次，两次请求至少间隔 4.3 秒（平台每分钟 15 次）；滚动 24 小时最多 450 次（平台每天 500 次）。
  间隔不够时本次不调用模型，Jeff 等几秒再请求，不消耗额度。
- Cloudflare：两个模型共用一个账户的每天 10,000 Neurons。按每次约 7 千输入 Token 估算，Gemma 记 80、Llama 记 115，
  滚动 24 小时合计不超过 9,000；每个模型每分钟最多 30 次。
- 一天的额度用完后，名额状态显示“今日额度已用完”（`daily_budget`），和每分钟、每小时的临时限制（`call_budget`）分开。

这些是按平台公开的免费额度设置的保守值。滚动 24 小时与平台的重置时间（Cloudflare 按 UTC 零点，Gemini 按太平洋时间零点）不同，只会更早停下，不会超出。

**研究记录。** `cloudflare` 是新增的研究记录服务名。研究管理台按它自己发布版本里的
`schemas/research-record.schema.json` 校验，所以上线顺序必须是：先升级研究管理台，再升级两站游戏；
否则带 `cloudflare` 的贡献记录会被拒收。

**启用步骤（由运维执行）：**

1. 在上海创建 `extra-model-keys.json`（不经过聊天或 Git），权限 0640，属主与 `model-keys.json` 相同。
2. `deploy/upgrade_free_gateway.py prepare --extra-models` 会校验这个文件（不打印内容），生成带
   `--extra-keys-file … --extra-models-verified` 的服务单元；审阅后按原流程 `activate --allow-round-end`。
   验证时，名额列表必须正好是原来两家加上文件里启用的模型，每个名额上限 1。
3. 启用后立刻做服务器出口检查：`scripts/probe_free_gateway.py --providers gemini,cloudflare-gemma,cloudflare-llama`，
   每个模型最多一次真实请求。连不上的模型会显示“暂不可用”和实际原因，不会被当成可用。

玩家也可以在「自定义模型」里填自己的 Gemini 或 Cloudflare Key，不占这里的名额。Gemini 由浏览器直连；
Cloudflare 不接受浏览器直连，在线版经 `/api/model/cloudflare` 转发，必须勾选单独的同意项
（`cloudflare-relay-2026-11-v1`），只转发上面两个固定模型，Key 和 Account ID 只用于这一次请求。

