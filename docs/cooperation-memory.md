# Cross-round cooperation memory

Online memory is **on by default** and belongs to the current browser profile. Local play keeps its existing `.player-memory.json` file. There is no shared player-history file or memory database on the demo server.

## What is remembered

Up to three **naturally completed rounds**, separately for each service/endpoint, model, level and game/input contract. Reaching closing time or a game-rule loss can produce a record; manual endings, restarts of unfinished rounds, page exits and unstarted rounds do not. Rotating a key does not change a model's memory scope. Authored content or model-rule/language changes invalidate the old namespace; random order/spawn seeds and cosmetic UI changes do not.

Version 2 episodes contain:

- The round's duration, revenue, target, dishes served, expired orders, burns and fires.
- Completed-work totals for **both** chefs, using the existing settlement categories: fetching, chopping, heating, assembly, serving, washing, collecting plates, passing, extinguishing and discarding. Counts do not measure skill, effort or a permanent division of labor.
- The last preset preference and number of corrections in that old round, not a profile of the player. Current-round communication takes precedence.
- At most 18 sampled events. Sampling balances human, Jeff and world events, reallocates unused quota and keeps recent adverse events. This is a sample, not a replay or a complete explanation of an outcome.

The online portable record uses coded events and numeric facts. It excludes keys, endpoints, model/provider reply text, display labels, free text and raw model requests. Existing local journals and local memory retain their separate local-only policies.

## Model input and cost

The browser freezes its context **before sending each start/restart/next request**. Refreshing a setting or another tab writing a later record cannot replace that round's context. A lost start acknowledgement keeps the prepared snapshot; a definite failed start restores the previous one. No extra model calls summarize memory: the game engine and completed-work record generate the facts.

The newest complete episodes must fit within **8000 serialized English JSON characters**. Whole oldest episodes are omitted if needed; current rules, kitchen state and candidate actions are not truncated. Character counts are not token counts and cannot guarantee compatibility with any provider context window. Stored rounds and rounds selected for input can therefore differ. `omitted_rounds` records this budget effect.

`past_episodes` and its historical-evidence rule are included for browser-direct services and the explicitly consented Jev relay. The relay validates episode fields, level, numeric bounds and context size before adding history to the server-created task. It cannot accept arbitrary replacement game state, instructions, endpoints or extra credentials. It does not retain the history as a server profile.

This is bounded context supplied to the selected model, **not model training or a promise of better cooperation**. Rules are versioned as `rules-v6`, memory context/episodes as version 2. A changed representation can change model behavior; evaluate it as an experimental condition.

## Storage and controls

- Online records and their enable/disable setting live in `chefjeff.cooperation-memory.v2` in this browser's localStorage. At most 24 scopes and three records per scope are retained, with a total storage bound. They persist across refresh and server restarts. There is no login, visitor identifier, account lookup or cross-device synchronization.
- Settings → Cooperation memory can disable use/addition for the next round or clear **all** saved model scopes. Existing records remain when disabled. Controls are locked during running and paused rounds. Clearing credentials is a separate action and does not clear memory; clearing site data removes both.
- With unavailable browser storage, records remain usable within the page and the UI says they are temporary. Corrupt saved data disables memory until cleared. Failed storage must not stop play.
- Local files retain their existing storage envelope. Older records remain readable, but old scope namespaces are not silently merged into the new game/input namespace. Clearing removes them.

Browser history is user-editable. The server validates its shape, not the truth or ownership of historical claims. Browser-reported conditions are not independent evidence that a model received, understood or followed memory.

## Research records and deployment

Feedback exports and optional contributions include only the memory **condition**: enabled, version, number of selected/omitted past rounds, and whether the source is local runtime or browser-reported. The online server freezes this declaration on the first accepted model-result report, including a reported request failure. With no report, it is unknown (`null`), not falsely marked off. The declaration is not proof of successful model receipt. Old episode contents remain excluded from exports and contributions.

Optional contribution terms are updated to `pilot-session-2026-10-v3`; previous standing consent is not carried forward silently. Players are asked again, with the same unselected choices. Retention and deletion remain 30 days and receipt-based. Usage aggregates do not acquire memory records or per-player histories.

Deploy the matching runtime, page and `deploy/nginx-https.conf` together. The Jev route permits a bounded 12 KiB body (key plus validated context), keeps a 16 KiB body buffer, and continues to disable request/response buffering and body/access logging. The normal update helper already installs and validates this configuration and rolls back on failure.

Offline tests cover actual second-round input on direct/relay paths, browser reload, key rotation, model/level/contract/browser isolation, interrupted rounds, storage failures, bounded context, fixed round conditions, summary provenance and no credential/episode-content leakage into research records. Paid model quality and production deployment still require explicit observation.

## 中文说明

在线版默认开启跨局记忆，摘要和开关保存在**当前浏览器**，刷新、服务器重启后仍可使用；本地版仍保存在 `.player-memory.json`。不同模型、接口、关卡和规则／输入版本分开，换 Key 不会丢掉同一模型的记忆，不生成访客编号，也不跨设备同步。

每个范围保留最近三局自然结束的摘要：双方完成的工作、结果、过期订单、烧糊与起火、旧局的最后偏好与纠正次数，以及最多 18 条抽样事件。手动结束、中途重开或退出的局不保存。工作次数不等于能力或固定角色，旧局偏好也不会强制覆盖本局沟通。

本局使用的旧局摘要在开局前固定，不随中途写入变化；直连和明确同意的 Jev 转发都使用它。摘要由游戏事实生成，不额外调用模型。模型输入中的记忆限制为 8000 个序列化英文 JSON 字符，超限时整体省略更旧的回合，不截断当前规则、状态或动作；字符数不是 Token 数，不能保证适配任何模型的上下文上限。

在「设置 → 协作记忆」可关闭下一局的使用与新增，或清空所有模型的记忆；对局进行和暂停时锁定设置。关闭保留已有记录，清空配置和清空记忆是两回事。浏览器不能保存时退回本页临时记忆并提示；损坏数据会关闭记忆，可清空后重启。旧本地文件仍可读取，但不会把旧命名范围的记录强行并入新版条件。

服务器不保存共享记忆文件。旧局摘要随模型请求处理，Jev 转发也会校验并在内存中使用；它们不随反馈导出或自愿贡献上传。研究记录只增加「是否启用、版本、选用／省略几局、由谁报告」这些条件。浏览器报告可以被修改，也不代表模型已经收到或理解了记忆。没有报告时标记未知，不当作关闭。

数据贡献说明升级为 v3，已有自动贡献选择会重新询问；记录仍私有保留 30 天并可凭删除凭证提前删除。部署时需一同更新运行时、页面和 Nginx 配置，Jev 的请求容量同步调整，继续避免 Key 请求体进入代理临时文件。
