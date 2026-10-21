# ChefJeff 隐私说明与反馈

[English](#english) · [模型连接说明](model-guide.md)

这一页说明 ChefJeff 存了什么、存在哪里、保存多久、怎样删除，以及怎样联系我们。更细的技术说明见 GitHub 仓库里的 docs/privacy-and-costs.md 和 docs/hosted-deployment.md。

## 在线版

- **API Key**：默认只在当前页面的内存里，刷新或关闭页面即消失。勾选「记住此设备」后，Key 和所选转发方式以明文保存在这个浏览器的 localStorage；在「设置 → 连接」点「清除配置」即删除。
- **模型请求**：默认由浏览器直接发给你选的模型服务，费用记在你的账号上。只有你为 Jev 明确勾选「同意通过试玩服务器调用 Jev」时，Key 和模型请求才经 HTTPS 通过我们的服务器转发给 TypeSafe；服务器只在处理这次请求时使用 Key，不写入配置、日志或对局记录。
- **对局**：游戏状态和你的操作在服务器内存中处理。关闭页面或闲置 10 分钟后清除，不写磁盘对局日志，也没有跨局记忆。
- **使用统计**：为改进游戏，服务器保存访问、试玩、关卡完成、退出、满员情况及游玩时长的汇总；浏览器用本地标记估算访问／试玩的浏览器数量，估算不代表真实人数。统计不保存 IP、账号、Key 或逐局明细，不生成唯一访客编号或指纹。汇总数据私有保存，在服务运营期间保留，与下述自愿贡献的 30 天记录分开。清除网站数据可删除本地标记。
- **数据贡献（自愿）**：第一次开局前会问你一次，可以选「同意以后每局自动贡献」或「暂不」，没有默认选项，之后可在「设置 → 数据导出」更改；选「暂不」时，也可在结算画面点「贡献本局」只贡献那一局。
  - 会保存：游戏引擎事件、每秒角色位置、结算结果、预设沟通代码（例如「我更爱备菜」）、地图与版本。
  - 不会保存：API Key、自由输入的文字（游戏里也没有自由输入框）、模型回复与完整请求、IP 与账号身份、模型接口地址。
  - 用途：改进游戏，研究人机协作的评估方法；不公开原始数据。
  - 保存：私有保存在试玩服务器（Hetzner，德国纽伦堡），30 天后自动删除，不做备份。
  - 删除：每份贡献的删除凭证保存在你的浏览器里，在「设置 → 数据导出 → 删除已贡献数据」即可提前删除；也可以下载凭证备份。凭证只交给你，服务器只存它的哈希；凭证丢失时我们无法认出哪条记录是你的，只能等 30 天自动删除。
- **浏览器里的其他设置**：界面语言、音量、数据贡献选择和删除凭证，都只保存在这个浏览器；清除本网站的数据即可全部删除。
- **网络**：云服务商和网络运营商会按各自政策处理连接信息；我们提供的反向代理关闭了访问日志。

## 本地版

本地版不连接 ChefJeff 的服务器。Key 默认只在你电脑上的后端内存里；勾选记住后以明文保存在本地文件 .player-api.json。跨局记忆在 .player-memory.json，对局日志在 logs/ 文件夹，都只在你的电脑上，可以随时删除。

## 数据导出与问题反馈

「设置 → 数据导出」生成的文件只下载到你的电脑，不会自动上传。文件包含对局数据和本页最近 30 秒的画面诊断（游戏时间、角色位置、按键方向、页面错误、浏览器型号和屏幕尺寸），不含 Key、接口地址和模型回复。附到公开 Issue 之前请先看一遍。

## 联系我们

- 问题、建议和隐私疑问：在 GitHub 提 Issue：[github.com/belchingleo/ChefJeff/issues](https://github.com/belchingleo/ChefJeff/issues)。
- 安全漏洞：请按仓库里 SECURITY.md 的说明私下报告，不要在公开 Issue 里发 Key、删除凭证或利用细节。
- 删除数据不需要联系我们：用浏览器里保存的删除凭证即可。

---

## English

[模型连接说明 · Model connection guide](model-guide.md)

What ChefJeff stores, where, for how long, how to delete it, and how to reach us. Technical details are in docs/privacy-and-costs.md and docs/hosted-deployment.md in the GitHub repository.

### Online version

- **API key**: kept in this page's memory by default and gone on refresh or close. With **Remember on this device**, the key and chosen transport are saved in plain text in this browser's localStorage; **Clear credentials** in Settings → Connection deletes them.
- **Model requests**: sent by your browser straight to the model service you choose and billed to your account. Only if you explicitly tick **I agree to call Jev through the demo server** do the key and model request pass over HTTPS through our server to TypeSafe; the server uses the key only for that request and never writes it to configuration, logs or game records.
- **Rounds**: game state and your actions are processed in server memory and cleared when you close the page or after 10 idle minutes. No game journal is written to disk and there is no cross-round memory.
- **Usage statistics**: to improve the game, the server keeps aggregate counts of visits, play, level completions, exits and capacity rejections, along with play duration summaries. Local browser flags help estimate visiting and playing browsers, not people. No unique identifier or fingerprint is generated; statistics exclude IPs, accounts, keys and individual-round records. Aggregates remain private and are retained for the service’s lifetime, separately from the voluntary 30-day contributions below. Clearing site data removes the local flags.
- **Data contribution (voluntary)**: before your first round you are asked once, with two equal choices: **Contribute every round from now on** or **Not now**. Nothing is preselected; change it later in Settings → Data export. After **Not now**, the result card offers **Contribute this round** for that round alone.
  - Saved: engine events, chef positions once a second, results, preset communication codes (such as "I prefer ingredient prep"), map and version.
  - Never saved: API keys, free text (the game has no free-text input), model replies and full requests, IP address and account identity, model endpoints.
  - Purpose: improving the game and researching how to evaluate human-AI cooperation. Raw data is not published.
  - Retention: stored privately on the demo server (Hetzner, Nuremberg, Germany), deleted automatically after 30 days, never backed up.
  - Deletion: each contribution's deletion receipt is kept in your browser; Settings → Data export → Delete a contribution removes it early, and you can download the receipts as a backup. Only you get the receipt; the server keeps its hash, so without the receipt we cannot tell which record is yours and it expires after 30 days.
- **Other browser settings**: language, volume, your contribution choice and deletion receipts stay in this browser only; clearing this site's data removes them all.
- **Network**: hosting and network providers process connection metadata under their own policies; our reverse proxy has access logs disabled.

### Local version

The local version never connects to a ChefJeff server. Your key stays in your own backend's memory unless you choose Remember, which saves it in plain text to .player-api.json. Cross-round memory lives in .player-memory.json and game journals in logs/, all on your computer and deletable at any time.

### Data export and bug reports

Settings → Data export only downloads a file to your computer; nothing is uploaded. It contains your rounds plus the last 30 seconds of page diagnostics (game time, chef positions, held direction, page errors, browser and screen size), and no keys, endpoints or model replies. Look it over before attaching it to a public issue.

### Contact

- Questions, suggestions and privacy concerns: open a GitHub issue at [github.com/belchingleo/ChefJeff/issues](https://github.com/belchingleo/ChefJeff/issues).
- Security vulnerabilities: report privately as described in SECURITY.md; never post keys, deletion receipts or exploit details in a public issue.
- Deleting data needs no contact: use the deletion receipt kept in your browser.
