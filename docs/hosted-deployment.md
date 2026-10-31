# Hosted pilot deployment

The hosted runtime is separate from the local launcher. It uses the same kitchen rules with a new ephemeral session per browser page. Model HTTP calls run in the browser; the Python process has no model credential configuration or model network transport.

## Run for local verification

```sh
python3 hosted_server.py --origin http://127.0.0.1:19780 --port 19780 --data-dir /tmp/chefjeff-pilot-data
node tests/hosted_browser_test.cjs
python3 -m unittest tests.test_hosted tests.test_hosted_records
```

`--data-dir` enables explicit contributions. Omit it to disable persistent contributions. A refresh creates an independent page session. On page exit, the browser sends an authenticated close request containing no model credentials, except when retained in the back/forward cache. Inactive page sessions expire after 10 minutes. `--max-sessions` now limits active kitchens (default 8, configurable 1–16), while `--max-waiting` adds a bounded page-session allowance (default 32, configurable 0–32). Browsing and model setup do not reserve active slots. `--max-per-network` (default 4, 1–16) caps the active kitchens one network may hold at once: Nginx passes the client address in `X-ChefJeff-Client` (always overwritten), IPv6 addresses count per /64, and the address stays in memory only; without the header no per-network limit applies. A page that reaches its network's share shows why and waits like a full server. Pages that are not playing tick once a second instead of 20 times; a start or resume wakes them at once. The data export keeps the latest 20 rounds per page. A pause holds its slot for 60 seconds and a result for 30 seconds; polling does not extend either lease. Expiry releases the slot while retaining the page's game state, so resume/next-round may have to wait. A disconnected running game still pauses after 8 seconds.

When active slots are full, the browser can configure its model and displays a waiting button. State polling restores that button when a spot opens; the player must press it to start/resume. There is no automatic paid model call or promised FIFO order. If the bounded page-session pool itself is full/unavailable, creation retries at most every 15 seconds.

The backend uses a 128-connection accept queue and at most 32 request threads. Each validated session has a 40-request/second token bucket with a 40-request burst; pause/end/close remain available when its budget is exhausted. Nginx retains a coarse 500-request/second/IP bound plus a separate 15-creation/minute/IP quota with burst 10, accommodating several players behind one network. Anonymous receipt deletion retains its former 30-request/second/IP budget. Unknown tokens cannot create backend request-budget entries. Build identity is calculated once per server release. Public build scripts, images, fonts and audio are served directly by Nginx with MIME types and compression. The web build is a release build (minified engine, unused engine modules such as Spine, DragonBones, 2D physics, tiled maps, video and web views removed) with Creator's md5Cache, so build files carry a content hash in their names (`cc.<hash>.js`); Nginx serves those with `public, max-age=31536000, immutable` and errors with `no-store`, while unhashed files (`kitchen-i18n.js`, touch/controller scripts, fonts) keep revalidation. HTTPS uses HTTP/2, so the page's startup requests share one connection; HTML and the hosted agent remain on their existing Python paths. Static errors remain uncached. Idle ticks stop manual movement only when needed, rather than accumulating no-op engine inputs.

## Credentials and records

- A key lives in a JavaScript closure by default. Explicit Remember stores it and the chosen transport as plaintext in browser localStorage; Clear removes them. Browser-direct providers must allow CORS. Jev offers explicit opt-in forwarding, never an automatic fallback. `/api/model/jev` accepts a key only with the versioned consent flag and a valid page/game/task ID; neither games nor forwarding receipts store keys.
- Deploy the matching Nginx configuration with the runtime. Its exact Jev route has a 12 KiB body cap, request/response buffering disabled and HTTP/1.1 streaming, preventing key-bearing bodies from being written to proxy temporary files. Keep access/body logging disabled. The upstream is fixed at `https://api.typesafe.ai/v1/systemone`, `jev-latest`, with verified TLS, no redirects and no forwarding retries. No provider credentials are configured on the game server; each player supplies their own.
- Forwarding is bounded to eight concurrent upstream calls and one per kitchen, with an 18-second socket timeout. Connection tests have a ten-second per-page cooldown and deduplicate their request IDs. Game calls use existing decision IDs and call limits. Upstream I/O holds no game lock; pause/close/round changes discard late answers. Already-issued requests may still be billed. Global/per-kitchen limits can temporarily reject a call rather than queue paid work.
- Model results sent to the game server contain a validated action, sprint flag and numeric token usage only. Provider text, endpoint and model name are not submitted. The game server receives normal gameplay actions and processes the full state in memory.
- Ordinary sessions create no disk journal or shared server history file. Default-on browser-owned cooperation memory is described in [cooperation-memory.md](cooperation-memory.md). The browser freezes the selected history at round start; direct models and the consented Jev relay receive the same context. The server processes validated relay history only in memory. When contributions are enabled, the page asks once before the first round (`hosted/consent.html`), with two equal buttons and nothing preselected: **contribute every round from now on** or **not now**. The question states what is and is not saved, the purpose, 30-day retention and deletion. Agreeing never uploads an already-ended round. After **not now**, the result card offers a one-tap **贡献本局** for that round only. Settings → Data export shows the current answer and reopens the question to change it. The answer and deletion receipts are kept in this browser; clearing browser storage removes them. Records identify per-round (`round`) or standing (`standing`) consent. The answer is tied to `CONSENT_VERSION` (`pilot-session-2026-10-v3`; `hosted_records.py`, mirrored in `hosted/browser-agent.js`): changing the terms means bumping it, which asks every player again.
- Contributions contain engine event types/actions, one-second chef positions, preset communication codes, configuration identifiers and result statistics. They are a pilot record format, not the final benchmark schema or deterministic replay.
- Contributions are kept privately for 30 days. Cleanup runs at startup, before saving and every 30 seconds while the service runs. A random deletion token is delivered once to the player; only its hash is stored. Losing the receipt means waiting for automatic expiry. Deleting a record does not publish or email anything.
- No account, email, IP address, key, model endpoint, raw model prompt or response is stored in a contribution. The cloud/network provider still handles connection metadata under its own policies.
- Do not back up the contribution database or include it in server snapshots unless the retention/deletion policy is extended accordingly. The supplied service does not create backups. The database directory must not be web-served or committed.

The next-round button waits for any consented upload of the previous round before resetting it. Uploads time out after 10 seconds; failure is displayed and does not prevent continued play. Deletion receipts can be downloaded together or used for bulk deletion; failed deletions retain their receipts for retry.

## Server installation

Upload an audited ZIP containing the allowlisted runtime, web build and `hosted/`, `deploy/` files. Verify its hash and every release-manifest entry; extract under `/opt/chefjeff/releases/<version>` and execute `deploy/install_backend.py` there. The service runs as an unprivileged dedicated account and binds only `127.0.0.1:8780`. This step does not open the website publicly.

The current pilot uses the operator's Hetzner instance in Nuremberg, Germany, at `chefjeff.online` (and `www.chefjeff.online`). The first address, `chefjeff.belchingleo.online`, still points there and redirects to `chefjeff.online`.

Moving from the first address (once): point `chefjeff.online` and `www` at the server; as root run `certbot certonly --webroot -w /var/www/chefjeff-acme -d chefjeff.online -d www.chefjeff.online`; then run the update script from the new commit, `curl -fsSLo /root/update_hetzner.py https://raw.githubusercontent.com/belchingleo/ChefJeff/<commit>/deploy/update_hetzner.py` and `python3 /root/update_hetzner.py <commit> <package SHA-256>`. It installs the redirects and moves the service's `--origin` to the new address, restoring both on failure. Finally rerun `bash deploy/finalize_hetzner.sh` from the new release so certificate renewals of either address reload Nginx. Players' browser storage is per address: keys remembered on the old address and contribution receipts kept only in that browser stay with it.

The supplied Nginx templates limit traffic, compress state responses and disable access/request logs. After public exposure is approved, install Nginx/Certbot from Ubuntu's official repositories; keep the initial HTTP site on a 503 response except for ACME challenges. Request the certificate only after the operator accepts the certificate issuer's subscriber terms. Then install the HTTPS template, validate Nginx configuration and test renewal. Allow only 80/443 for the web entry; never expose the Python port. Certificate files stay on the server.

On this pilot's shared VPN server, run `bash deploy/finalize_hetzner.sh` as root after HTTPS works. It adds a drop-in to the enabled `personal-vpn-firewall.service`, using the existing `inet personal_vpn_filter input` chain to allow TCP 80/443 after startup and reload. The reviewed VPN loader and its hash arguments remain intact. It also installs a certificate-specific Nginx reload hook, enables the Certbot timer, and tests renewal with the hook. This helper requires that exact firewall service/table and does not reboot the server; boot persistence has to be confirmed during a later maintenance reboot.

## Operational checks

### Aggregate usage counters

On the server, run `python3 /opt/chefjeff/current/scripts/hosted_usage.py`. From a Mac with the existing `hetzner-vpn` SSH alias, run `ssh -t -o BatchMode=no -o UseKeychain=yes hetzner-vpn 'python3 /opt/chefjeff/current/scripts/hosted_usage.py'`. The script reads `GET /ops/usage` on `127.0.0.1:8780` with the configured Host; it needs no database permissions or model credentials. The shipped Nginx configuration blocks `/ops/` publicly; the usage handler also refuses the proxy's client-address header. Keep the Python listener loopback-only.

Metric definitions:

- `page_views`: successful homepage (`/` or `/index.html`) responses. Includes refreshes, bots and tests; it does not prove that a human loaded all game assets. Assets, polling, health/privacy pages and failed requests are excluded.
- `started_sessions`: once per page session after its first successful start, regardless of retries, pauses, restarts and later levels. A reload/new tab creates another session. `started_rounds` counts each successful round start, including restarts and later levels. Replayed request receipts, failed starts and resumes do not add rounds.
- `completed_rounds`: each natural closing, including losses, once. `manual_ends`: successful manual End commands only; restarting/changing level, closing, disconnection and service shutdown are separate endings. `levels` holds round starts/completions for each of the three levels.
- `full_rejections`: rejected creation/start/resume attempts due to the global page pool or active-kitchen limit (`page_full_rejections` / `kitchen_full_rejections`). The same browser's retries count again. `network_full_rejections` separately counts the per-network limit. State polling and validation failures do not add rejections.
- `running_sessions`: running phase only, excluding paused/results/waiting sessions. It resets after shutdown. A lost connection pauses after the existing 8-second heartbeat timeout.
- `durations`: per-level and per-ending histograms, with bucket counts, summed game seconds, and effective running seconds (`game_seconds / speed`). Pauses and waiting do not advance game progress. This measures simulated play progress at the selected pace, not precise time spent looking at the screen. Buckets are [0,10), [10,30), [30,60), [60,120), [120,180), [180,300), and 300+ seconds. Endings distinguish natural closing, manual End, received page-close notification, idle-session cleanup, restart/level change and service shutdown. Without a close notification, disconnection is finalized at the existing 10-minute idle cleanup, using the last game progress; its precise wall-clock exit time is unknown. Normal systemd SIGTERM is handled gracefully and classified as shutdown, not a player choosing to quit. A force-kill or crash can leave in-progress rounds without ending aggregates. No round ID, exact exit timestamp or individual-duration row is retained.
- `estimated_visitor_browsers` / `estimated_player_browsers`: first-visit/play reports from the browser. Only two fixed localStorage flags (`chefjeff.usage-visited.v1`, `chefjeff.usage-played.v1`, each `1`) persist in the browser; no identifier or fingerprint is generated. Reports contain two booleans over the existing authenticated session, which is never persisted in stats. The server deduplicates retries in that session's memory and accepts first-play only after an actual start. Web Locks serializes tabs where available. These are approximate browsers, not people: cleared data, private browsing, other devices, shared profiles, missing acknowledgements, unsupported cross-tab locking and manipulated reports can skew totals. Browsers with unavailable storage or no admitted session are omitted. Flags span visits but do not support unique counts per day or arbitrary time window; normal API-key clearing does not clear these flags, while clearing site data does.

With `--data-dir`, the private `usage.sqlite3` contains one totals row and bounded aggregates for the three levels and six ending types, not per-event records. The production directory is `/var/lib/chefjeff`; updates/restarts retain it. Tracking starts at first deployment with no historical backfill, and aggregates persist for the service's lifetime independently of optional 30-day contributions. No IPs, accounts, referrers, user agents, model information, payloads, keys or session/round IDs are written. Without `--data-dir`, counters are memory-only. `persistent: false` / `storage_errors` expose storage failure: counting continues in memory without stopping play, and unpersisted increments can be lost on restart.

`/ops/capacity` is accessible on the loopback backend and blocked by the public Nginx route. It reports held slots, per-network rejections, page sessions, aggregate rejections, recent response P95/P99, Python CPU/RSS/threads and Linux service cgroup memory where available. No session token, game ID, IP or model payload is included. These are backend metrics, not browser/network latency or total host CPU.

After an approved release is installed, run `python3 /opt/chefjeff/current/deploy/set_kitchen_capacity.py 8` in the server's root SSH terminal to explicitly replace the old two-kitchen command. Existing memory/data/VPN settings remain in place. The helper restarts ChefJeff (ending current rounds), checks the effective limit and restores its previous drop-in if verification fails. A normal release update intentionally preserves existing capacity overrides.

### Raising capacity

Two limits apply: `--max-sessions` (active kitchens, 1–16) and `--max-waiting` (extra page sessions that can browse, set up a model and wait, 0–32). A page beyond both cannot open a kitchen and retries every 15 seconds. `--max-per-network` (default 4) is separate. On the server, as root in its SSH terminal:

```sh
python3 /opt/chefjeff/current/deploy/set_kitchen_capacity.py 12             # active kitchens; waiting pages unchanged
python3 /opt/chefjeff/current/deploy/set_kitchen_capacity.py 12 --waiting 32 # also set waiting pages (0–32)
```

The helper accepts 2, 4, 8, 12 or 16 kitchens, rewrites only its own drop-in (`/etc/systemd/system/chefjeff.service.d/zz-chefjeff-capacity.conf`), restarts the service (ending current rounds), verifies both limits through `/ops/capacity` and restores the previous drop-in if verification fails. Memory, data and VPN settings stay as they are. Each active kitchen adds one game thread; raise `MemoryMax` only after checking the cgroup peak.

Before changing the real server, rehearse locally. `scripts/load_test_hosted.py` (test-only, not in the runtime package) starts a local `hosted_server.py` and simulates pages with a stand-in browser model that always answers "wait", so no model is called. It checks that one network gets at most its share, pages past the limit see the waiting state, pages past the pool are refused, and freed slots are taken; it prints latencies, statuses and the server's own metrics:

```sh
python3 scripts/load_test_hosted.py --pages 44 --capacity 8 --max-waiting 32 --seconds 30
python3 scripts/load_test_hosted.py --pages 52 --capacity 16 --max-waiting 32 --seconds 60
```

On the development Mac (Intel i5-1038NG7, load generator on the same machine) both passed: 8 kitchens, 44 pages: 40 sessions opened, 4 refused, 4 of 6 same-network pages started, 32 waited, 4 freed slots taken within 0.2 s; server P95 11 ms / P99 48 ms, 23% of one core, 49 MB peak RSS. 16 kitchens, 52 pages for 60 s: 48 opened, 8 freed slots taken within 0.5 s, server P95 15 ms / P99 29 ms, 21% of one core, 56 MB peak RSS. Client-side times are higher because the generator's own threads share the CPU. This is not a Hetzner capacity measurement; follow the gates below there.

Start with 8 active kitchens and validate on the actual shared server for 30–60 minutes before trying 12 or 16. Include normal VPN load, simultaneous cold loads, same-network players, continuous rounds/contributions and idle lease expiry. Suggested gates: sustained total host CPU below 65%, at least 200 MiB available host RAM, service cgroup peak below 384 MiB, backend P95 below 100 ms/P99 below 200 ms, and no unexplained 5xx, timeouts, OOM or continuing memory growth. Cloud single-core tests are supporting evidence, not a Hetzner capacity guarantee.

With Nginx installed, run `python3 -m unittest tests.test_hosted_proxy`. The real-proxy checks cover public-page navigation from other sites, header forwarding and credential stripping, and rejection of cross-site game API requests. If Nginx is outside PATH, set `CHEFJEFF_NGINX_BIN` to its executable path.

1. Check `/healthz` with the configured Host and confirm the Python listener is loopback-only.
2. Use two browser pages to verify independent kitchens and connection settings.
3. Inspect outgoing browser traffic with a dummy key: it must appear only in the selected provider's Authorization header, never a same-origin request.
4. Verify remembered-key/transport opt-in and clear/refresh behavior, provider CORS failure without automatic fallback, consented Jev connection, no keys in logs/records/exports, explicit contribution, deletion, expiry and capacity limits.
5. Test the chosen real provider from the HTTPS origin with an owner-supplied key. An OPTIONS response alone does not verify an actual paid model call.

No public URL is declared available until DNS, HTTPS and the full browser flow have passed validation.

---

## 中文说明

# 托管试玩部署

托管运行时独立于本地启动器，使用同一厨房规则，每个浏览器页面有独立临时会话。模型 HTTP 请求在浏览器执行，Python 进程不配置模型凭据，也不传输模型网络请求。

## 本地验证

```sh
python3 hosted_server.py --origin http://127.0.0.1:19780 --port 19780 --data-dir /tmp/chefjeff-pilot-data
node tests/hosted_browser_test.cjs
python3 -m unittest tests.test_hosted tests.test_hosted_records
```

`--data-dir` 启用自愿数据贡献，省略则禁用持久化贡献。刷新创建独立页面会话，闲置十分钟过期。`--max-sessions` 现在限制活跃厨房（默认 8，可配置 1–16），`--max-waiting` 提供额外的有限页面会话额度（默认 32，可配置 0–32）。浏览和填写／连接模型不占经营名额。`--max-per-network`（默认 4，可配置 1–16）限制同一网络同时占用的经营名额：Nginx 通过 `X-ChefJeff-Client` 传入客户端地址（始终覆盖客户端自带的值），IPv6 按 /64 计，地址只保存在内存中；没有这个头时不按网络限制。达到本网络上限的页面会说明原因，并像满员时一样等待。没在经营的页面每秒只运行一次（原为 20 次），开局或继续时立即唤醒。数据导出每个页面保留最近 20 局。暂停保留名额 60 秒，结算保留 30 秒，轮询不会延长保留；超时释放名额并保留页面状态，继续或下一局可能需要等待。断开页面的经营中对局仍在 8 秒后自动暂停。

经营名额已满时，仍可配置模型，开局／继续按钮显示等待；状态轮询发现空位后恢复按钮，须玩家再次点击，不自动开局或调用付费模型，也不承诺按等待顺序排队。页面会话池本身已满或服务不可用时，最多每 15 秒重试创建一次。

后端采用 128 个连接的等待队列，最多 32 个请求线程；按有效会话限制每秒 40 请求，突发额度 40，额度耗尽仍可暂停／结束／关闭厨房。Nginx 保留每 IP 每秒 500 请求的总量限制，以及每 IP 每分钟 15 次建房、突发 10 次的独立限制，容纳同一网络多人；无需活跃会话的删除凭证接口保留原每 IP 每秒 30 请求限制。无效 token 不创建后端限流记录。发布身份仅在服务启动时计算一次。审核过的网页脚本、图片、字体和音频由 Nginx 直接提供，保留 MIME、压缩和更新检查；HTML 与托管代理脚本仍走原 Python 路径，静态错误不缓存。空闲时仅在确有移动输入时记录停止，避免长期积累无效引擎输入。

## 凭据与记录

- Key 默认仅在 JavaScript 闭包内存中，主动记住会将 Key 和所选转发方式以明文保存至 localStorage，清除会移除它们。浏览器直连要求供应商支持 CORS。Jev 提供明确同意的可选转发，失败不自动回退。`/api/model/jev` 仅在同意标志／版本和页面／对局／决策标识有效时接收 Key，游戏对象和转发回执均不保存 Key。
- 运行时和匹配的 Nginx 配置须一同部署。Jev 精确路由限制请求体 12 KiB，关闭请求／响应缓冲并使用 HTTP/1.1 流式转发，避免带 Key 的请求进入代理临时文件；保持访问／正文日志关闭。上游固定为 `https://api.typesafe.ai/v1/systemone`、`jev-latest`，校验证书、不跟随重定向、不自动重试。服务器不配置模型凭据，各玩家使用自己的 Key。
- 最多同时转发八个请求、每厨房一个，上游 socket 超时 18 秒。连接测试每页面冷却十秒并按请求 ID 去重；经营决策沿用现有决策 ID 和调用上限。网络等待不持有游戏锁，暂停／关闭／切换回合使迟到回复失效，已发出的请求仍可能计费。达到总量／单厨房限制时会暂时拒绝，不排队调用付费模型。
- 回传游戏服务器的模型结果含已校验动作、冲刺值、数值 token 用量，不提交完整模型文本或端点。经 v5 数据贡献同意后，另上报该局的模型服务与模型 ID（含自定义模型），注明 browser-reported、verified=false。服务器在内存处理正常游戏动作和完整状态。
- 普通会话不写磁盘日志或共享记忆文件。跨局记忆默认开启，保存在各自浏览器，开局固定后用于直连模型或明确同意的 Jev 转发；服务器只在内存中处理经过校验的旧局摘要，详见 `docs/cooperation-memory.md`。开启数据贡献时，页面在第一局前问一次（`hosted/consent.html`）：两个同等按钮「同意以后每局自动贡献」和「暂不」，没有默认选项；问题写明保存与不保存的内容、用途、30 天保存期和删除方式。同意时不补传已经结束的对局。选「暂不」后，结算画面提供一键「贡献本局」，只贡献这一局。「设置 → 数据导出」显示当前选择，并可重新打开问题更改。选择和删除凭证保存在此浏览器，清理浏览器存储会移除它们。记录区分单局同意（`round`）和持续同意（`standing`）。选择与 `CONSENT_VERSION`（`hosted_records.py`，`hosted/browser-agent.js` 中同值）绑定，条款改动须升级版本，所有玩家会被重新询问。
- 贡献包含引擎事件／动作、每秒厨师位置、预设沟通代码、配置标识和结果统计。这是试点记录格式，最终 benchmark schema 和确定性回放另行设计。
- 私有保存 30 天，在启动、保存前及运行期间每 30 秒清理过期数据。随机删除凭证仅交给玩家，服务器只保存其哈希；遗失后需等待自动过期。删除不产生发布或邮件。
- 贡献记录不存账号、邮箱、IP、Key、模型端点、原始模型提示或回复；云与网络供应商仍按自己的政策处理连接元数据。
- 不备份贡献数据库或将其包含在服务器快照中，除非同步扩展保留／删除政策。所提供服务不生成备份，数据库目录不得公开访问或提交仓库。

进入下一局前先等待本局已同意的上传，避免重置后丢失记录。上传十秒超时，失败会显示提示并允许继续游戏。删除凭证可一起下载备份或批量删除；删除失败时保留对应凭证，方便重试。

## 服务器安装

上传经过审阅、仅含明确清单中的运行文件、网页构建、`hosted/` 与 `deploy/` 的 ZIP。验证包哈希及每条 release-manifest 记录，解压至 `/opt/chefjeff/releases/<version>`，在该目录执行 `deploy/install_backend.py`。服务以专用低权限账号运行，仅监听 `127.0.0.1:8780`，此步骤不公开网站。

当前试玩部署在运营者的 Hetzner 德国纽伦堡服务器，地址为 `chefjeff.online`（及 `www.chefjeff.online`）。最初的地址 `chefjeff.belchingleo.online` 仍指向这台服务器，并跳转到 `chefjeff.online`。

从最初地址迁移（只需一次）：把 `chefjeff.online` 和 `www` 解析到服务器；以 root 执行 `certbot certonly --webroot -w /var/www/chefjeff-acme -d chefjeff.online -d www.chefjeff.online`；再用新提交里的更新脚本更新：`curl -fsSLo /root/update_hetzner.py https://raw.githubusercontent.com/belchingleo/ChefJeff/<提交 ID>/deploy/update_hetzner.py`，然后 `python3 /root/update_hetzner.py <提交 ID> <部署包 SHA-256>`。它会装好跳转，并把服务的 `--origin` 改到新地址，失败则两者一并恢复。最后在新版本目录重新执行 `bash deploy/finalize_hetzner.sh`，让两个地址的证书续期后都会重新加载 Nginx。玩家的浏览器存储按地址区分：在旧地址记住的 Key、只存在那个浏览器里的贡献删除凭证都留在旧地址。

Nginx 模板限流、压缩响应并关闭访问／请求日志。获得公开发布授权后，从 Ubuntu 官方仓库安装 Nginx／Certbot，初期 HTTP 除 ACME 验证外仅返回 503。运营者接受证书订户条款后申请证书，再安装 HTTPS 配置，校验 Nginx 并测试续期。网页仅开放 80／443，不公开 Python 端口；证书留在服务器。

JavaScript 压缩同时覆盖 `text/javascript` 与 `application/javascript`，以兼容 Ubuntu/Python 的实际 MIME 类型。网页采用正式模式构建（引擎压缩，去掉 Spine、DragonBones、2D 物理、瓦片地图、视频、网页嵌入等未用模块，引擎脚本由约 5.7 MB 降至 1.6 MB），并启用 Creator 的 md5Cache：构建文件名带内容哈希（如 `cc.<哈希>.js`），Nginx 以 `public, max-age=31536000, immutable` 提供，错误响应为 `no-store`。HTTPS 启用 HTTP/2，页面启动时的请求共用一个连接。不带哈希的文件（`kitchen-i18n.js`、触控／手柄脚本、字体）仍通过 ETag 和 `public, max-age=0, must-revalidate` 检查更新，内容未变则返回 304；Nginx 使用文件元数据 ETag，Python 托管代理脚本使用内容 ETag。HTML、API、健康检查和错误响应仍为 `no-store`，不长期缓存无版本号的脚本。

美术图集并发下载，全部完成后按原有顺序安装，保留后加载图集覆盖旧图集的规则。网页音频在第一次键盘／指针交互后按需下载正在使用的曲目及音效，不再在首屏下载整个音效目录；过晚到达的动作音效不补播，下载失败不会阻塞游戏。原生端保持整目录加载。真实用户首屏耗时仍受设备、网络和德国服务器到访客的往返延迟影响。

设置中的供应商、地址、模型及 Key 可以先填写；收到厨房状态且处于开局前／结算后，才允许测试、更换或清除配置。等待连接不会再误报“旧页面”；容量或网络错误显示在设置页，恢复连接时保留尚未提交的草稿。只填写不会发送模型请求或产生 API 调用费用。

后续更新可在服务器 SSH 终端以 root 执行 `python3 deploy/update_hetzner.py <完整提交 ID> <已测试部署包 SHA-256>`。脚本只从固定 Git 提交下载源码并打包，校验与本地测试包完全一致后，切换到新目录、重启厨房并检查健康状态，失败则回退旧版本和 Nginx 配置。它保留现有 systemd 容量／内存配置、记录数据和 VPN 配置。成功更新会结束正在进行的试玩对局；服务器部署与 Git 主线合并是独立操作。

在当前共用 VPN 的试玩服务器上，HTTPS 可用后以 root 执行 `bash deploy/finalize_hetzner.sh`。它为已启用的 `personal-vpn-firewall.service` 添加补充配置，在服务启动及重新加载后，通过现有 `inet personal_vpn_filter input` 链放行 TCP 80／443；原 VPN 加载脚本及其校验参数保持原样。脚本还安装仅针对试玩证书的 Nginx 重载钩子，启用 Certbot 定时器，并模拟续期及钩子执行。此脚本要求上述指定服务及规则链存在，不会重启服务器；实际开机持久化需在之后的维护重启时确认。

## 验证

### 查看使用统计

在服务器执行 `python3 /opt/chefjeff/current/scripts/hosted_usage.py`；在已配置 `hetzner-vpn` 的 Mac 上可执行 `ssh -t -o BatchMode=no -o UseKeychain=yes hetzner-vpn 'python3 /opt/chefjeff/current/scripts/hosted_usage.py'`。不需要 sudo、数据库读取权限或模型 Key。统计接口为本机 `GET /ops/usage`，Nginx 禁止公开访问 `/ops/`；处理器还会拒绝带代理客户端地址头的统计读取。

累计项包括首页成功响应、首次开局会话、实际开局局数、自然完成、手动结束、全局满员拒绝及同网络名额拒绝，另按三关显示开局／完成数。访问次数含刷新、爬虫和作者测试，不是独立人数；实际开局含重开和下一关，重复请求、继续和失败请求不算新局；满员计拒绝请求次数，重复尝试会重复计数。当前游戏中的会话数只算运行阶段，不含暂停、结算或等待。

已结束对局按关卡和结束方式保存时长区间次数及总秒数，不保存逐局记录。有效游玩秒数按“游戏内进度 ÷ 本局节奏”换算，暂停和等待不计；不等于人在屏幕前的精确时间。区间为 0–10、10–30、30–60、60–120、120–180、180–300、300+ 秒（左含右不含）。结束方式区分自然完成、手动结束、收到页面关闭通知、断线清理、重开／换关及服务停止。没有关闭通知的断线会在原有 10 分钟闲置清理时确认，使用最后游戏进度，不能知道实际关页时刻；普通 systemd 停止（SIGTERM）会正常结算为服务停止，不当作玩家主动退出；强制杀死或崩溃可能导致未结束局的时长缺失。

“估算访问／试玩浏览器数”只用浏览器中两个固定的已计入标记（`chefjeff.usage-visited.v1` / `chefjeff.usage-played.v1`），不生成独立编号、指纹或 Cookie。服务器只接收两个布尔值，在现有页面会话内去重重试，试玩须确实开过局。支持 Web Locks 时会串行处理多标签；无痕、清除数据、换设备、共用浏览器、上报丢失、旧浏览器竞争或伪造会影响估算。禁用存储或未获页面会话者不计，不能做每日或任意时间窗口的独立人数；清除模型 Key 不影响标记，清除站点数据会清掉标记。

统计从部署此功能开始，无法补算之前的访问。`--data-dir` 下的私有 `usage.sqlite3` 仅保存统计开始时间、累计数、关卡汇总和有界时长区间，在服务运营期间保留，更新／重启不清零；既有生产配置目录为 `/var/lib/chefjeff`。统计不写 IP、账号、浏览器编号、来源、User-Agent、模型、Key、会话／对局标识或逐条事件，与自愿贡献的 30 天记录分开。未配置数据目录时仅在内存计数；存储失败会标记 `persistent: false` 和 `storage_errors`，不阻断游戏，但未持久化计数可能在重启后丢失。


`/ops/capacity` 仅从回环后端读取，公开 Nginx 入口拒绝访问。指标包含保留名额、按网络拒绝次数、页面会话数、拒绝数、近期响应 P95／P99、Python CPU／内存／线程和可用时的 Linux 服务 cgroup 内存；不包含会话 token、游戏 ID、IP 或模型正文。这些是后端指标，不是浏览器／网络延迟或整机 CPU。

获得合并及部署授权、安装新版后，在服务器 root SSH 终端执行 `python3 /opt/chefjeff/current/deploy/set_kitchen_capacity.py 8`，显式替换原来的两个厨房命令。内存／数据／VPN 设置保留；脚本重启厨房（结束现有对局），校验实际容量，失败则恢复原补充配置。普通版本更新会保留现有容量覆盖配置。

### 提高容量

有两个上限：`--max-sessions`（活跃厨房，1–16）和 `--max-waiting`（额外的页面会话，可浏览、配置模型并等待，0–32）。两者都满时页面无法创建厨房，每 15 秒重试。`--max-per-network`（默认 4）另行限制。在服务器 root SSH 终端执行：

```sh
python3 /opt/chefjeff/current/deploy/set_kitchen_capacity.py 12             # 活跃厨房，等待页数不变
python3 /opt/chefjeff/current/deploy/set_kitchen_capacity.py 12 --waiting 32 # 同时设置等待页数（0–32）
```

脚本接受 2、4、8、12、16 个厨房，只改写自己的补充配置（`/etc/systemd/system/chefjeff.service.d/zz-chefjeff-capacity.conf`），重启服务（结束当前对局），通过 `/ops/capacity` 校验两个上限，失败则恢复原配置；内存、数据和 VPN 设置不变。每个活跃厨房多一个游戏线程，确认 cgroup 峰值后再考虑提高 `MemoryMax`。

改真实服务器前先在本机演练。`scripts/load_test_hosted.py`（仅测试用，不进运行包）启动本地 `hosted_server.py`，模拟多个页面，模型由一律回答 wait 的替身代替，不调用任何模型；它检查同一网络只占自己的份额、超出上限的页面显示等待、超出页面池的被拒绝、空出的名额会被接上，并输出延迟、状态码和服务端指标：

```sh
python3 scripts/load_test_hosted.py --pages 44 --capacity 8 --max-waiting 32 --seconds 30
python3 scripts/load_test_hosted.py --pages 52 --capacity 16 --max-waiting 32 --seconds 60
```

开发用 Mac（Intel i5-1038NG7，压测程序同机运行）上两组均通过：8 个厨房、44 个页面：40 个会话建立、4 个被拒，同一网络 6 个页面中 4 个开局，32 个等待，4 个空出的名额 0.2 秒内被接上；服务端 P95 11 毫秒／P99 48 毫秒，单核 23%，峰值内存 49 MB。16 个厨房、52 个页面、60 秒：48 个会话建立，8 个空出的名额 0.5 秒内被接上，服务端 P95 15 毫秒／P99 29 毫秒，单核 21%，峰值内存 56 MB。客户端测得的时间更高，因为压测线程同机争用 CPU。这不是 Hetzner 上的容量测量，在那里仍按下列门槛验证。

首档 8 个活跃厨房，在真实共用服务器测试 30–60 分钟后再试 12 或 16；覆盖正常 VPN 流量、同时冷启动、同一网络多人、连续游玩／贡献，以及空闲名额释放。建议门槛：整机 CPU 持续低于 65%、可用内存至少 200 MiB、服务 cgroup 峰值低于 384 MiB、后端 P95 低于 100 毫秒／P99 低于 200 毫秒；没有无法解释的 5xx、超时、OOM 或持续内存增长。云端单核测试提供参考，不能作为 Hetzner 容量保证。

安装 Nginx 后，运行 `python3 -m unittest tests.test_hosted_proxy`，通过真实代理验证外部链接打开首页、请求头转发、凭据移除，以及跨站游戏 API 请求被拒绝。Nginx 不在 PATH 时，可通过 `CHEFJEFF_NGINX_BIN` 指定可执行文件路径。

1. 使用配置的 Host 检查 `/healthz`，确认 Python 仅监听回环地址。
2. 用两个浏览器页面确认厨房和连接设置隔离。
3. 用占位 Key 检查出站请求：它只能出现在所选模型服务的 Authorization 中，不得出现在同源请求。
4. 验证记住 Key／转发选项、清除／刷新、CORS 失败不自动切换、明确同意的 Jev 连接、日志／记录／导出不含 Key，以及自愿贡献、删除、过期与容量限制。
5. 在 HTTPS 来源下用运营者提供的 Key 验证所选真实供应商。仅 OPTIONS 成功不代表真实模型调用成功。

DNS、HTTPS 和完整浏览器流程验证通过后，才将公开网址标为可用。届时同步更新 README 中的入口、启动方式和隐私说明。

The v3 contribution terms add only the memory on/off/version/selected-round-count condition, not episode contents, model names or endpoints. Old standing consent is re-asked. Deploy the runtime and new 12 KiB Jev Nginx route together using the update helper. v3 贡献说明只新增记忆开关、版本与使用局数条件，不含旧局摘要或模型信息；旧的自动贡献选择须重新询问。使用更新脚本同时部署运行时和新的 12 KiB Jev 代理配置。
