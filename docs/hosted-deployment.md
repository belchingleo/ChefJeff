# Hosted pilot deployment

The hosted runtime is separate from the local launcher. It uses the same kitchen rules with a new ephemeral session per browser page. Model HTTP calls run in the browser; the Python process has no model credential configuration or model network transport.

## Run for local verification

```sh
python3 hosted_server.py --origin http://127.0.0.1:19780 --port 19780 --data-dir /tmp/chefjeff-pilot-data
node tests/hosted_browser_test.cjs
python3 -m unittest tests.test_hosted tests.test_hosted_records
```

`--data-dir` enables explicit contributions. Omit it to disable persistent contributions. A refresh creates an independent page session. On page exit, the browser sends an authenticated close request containing no model credentials, except when retained in the back/forward cache. Inactive page sessions expire after 10 minutes. `--max-sessions` now limits active kitchens (default 8, configurable 1–16), while `--max-waiting` adds a bounded page-session allowance (default 32, configurable 0–32). Browsing and model setup do not reserve active slots. A pause holds its slot for 60 seconds and a result for 30 seconds; polling does not extend either lease. Expiry releases the slot while retaining the page's game state, so resume/next-round may have to wait. A disconnected running game still pauses after 8 seconds.

When active slots are full, the browser can configure its model and displays a waiting button. State polling restores that button when a spot opens; the player must press it to start/resume. There is no automatic paid model call or promised FIFO order. If the bounded page-session pool itself is full/unavailable, creation retries at most every 15 seconds.

The backend uses a 128-connection accept queue and at most 32 request threads. Each validated session has a 40-request/second token bucket with a 40-request burst; pause/end/close remain available when its budget is exhausted. Nginx retains a coarse 500-request/second/IP bound plus a separate 15-creation/minute/IP quota with burst 10, accommodating several players behind one network. Anonymous receipt deletion retains its former 30-request/second/IP budget. Unknown tokens cannot create backend request-budget entries. Build identity is calculated once per server release. Public build scripts, images, fonts and audio are served directly by Nginx with revalidation, MIME types and compression; HTML and the hosted agent remain on their existing Python paths. Static errors remain uncached. Idle ticks stop manual movement only when needed, rather than accumulating no-op engine inputs.

## Credentials and records

- A key lives in a JavaScript closure by default. Explicit Remember stores it as plaintext in browser localStorage. Clear removes both copies. The selected model provider must allow CORS; there is no server proxy fallback.
- Model results sent to the game server contain a validated action, sprint flag and numeric token usage only. Provider text, endpoint and model name are not submitted. The game server receives normal gameplay actions and processes the full state in memory.
- Ordinary sessions create no disk journal or cross-round memory. Manual contribution remains the default. After explicitly accepting the policy, a player can enable automatic contribution of subsequently completed rounds; enabling it does not upload an already-ended round. Unchecking either agreement or automatic upload stops future uploads. This preference and deletion receipts are kept in this browser; clearing browser storage removes them. Records identify manual (`round`) or standing (`standing`) consent.
- Contributions contain engine event types/actions, one-second chef positions, preset communication codes, configuration identifiers and result statistics. They are a pilot record format, not the final benchmark schema or deterministic replay.
- Contributions are kept privately for 30 days. Cleanup runs at startup, before saving and every 30 seconds while the service runs. A random deletion token is delivered once to the player; only its hash is stored. Losing the receipt means waiting for automatic expiry. Deleting a record does not publish or email anything.
- No account, email, IP address, key, model endpoint, raw model prompt or response is stored in a contribution. The cloud/network provider still handles connection metadata under its own policies.
- Do not back up the contribution database or include it in server snapshots unless the retention/deletion policy is extended accordingly. The supplied service does not create backups. The database directory must not be web-served or committed.

The next-round button waits for any consented upload of the previous round before resetting it. Uploads time out after 10 seconds; failure is displayed and does not prevent continued play. Deletion receipts can be downloaded together or used for bulk deletion; failed deletions retain their receipts for retry.

## Server installation

Upload an audited ZIP containing the allowlisted runtime, web build and `hosted/`, `deploy/` files. Verify its hash and every release-manifest entry; extract under `/opt/chefjeff/releases/<version>` and execute `deploy/install_backend.py` there. The service runs as an unprivileged dedicated account and binds only `127.0.0.1:8780`. This step does not open the website publicly.

The current pilot uses the operator's Hetzner instance in Nuremberg, Germany, with `chefjeff.belchingleo.online` pointing to that server.

The supplied Nginx templates limit traffic, compress state responses and disable access/request logs. After public exposure is approved, install Nginx/Certbot from Ubuntu's official repositories; keep the initial HTTP site on a 503 response except for ACME challenges. Request the certificate only after the operator accepts the certificate issuer's subscriber terms. Then install the HTTPS template, validate Nginx configuration and test renewal. Allow only 80/443 for the web entry; never expose the Python port. Certificate files stay on the server.

On this pilot's shared VPN server, run `bash deploy/finalize_hetzner.sh` as root after HTTPS works. It adds a drop-in to the enabled `personal-vpn-firewall.service`, using the existing `inet personal_vpn_filter input` chain to allow TCP 80/443 after startup and reload. The reviewed VPN loader and its hash arguments remain intact. It also installs a certificate-specific Nginx reload hook, enables the Certbot timer, and tests renewal with the hook. This helper requires that exact firewall service/table and does not reboot the server; boot persistence has to be confirmed during a later maintenance reboot.

## Operational checks

`/ops/capacity` is accessible on the loopback backend and blocked by the public Nginx route. It reports held slots, page sessions, aggregate rejections, recent response P95/P99, Python CPU/RSS/threads and Linux service cgroup memory where available. No session token, game ID, IP or model payload is included. These are backend metrics, not browser/network latency or total host CPU.

After an approved release is installed, run `python3 /opt/chefjeff/current/deploy/set_kitchen_capacity.py 8` in the server's root SSH terminal to explicitly replace the old two-kitchen command. Existing memory/data/VPN settings remain in place. The helper restarts ChefJeff (ending current rounds), checks the effective limit and restores its previous drop-in if verification fails. A normal release update intentionally preserves existing capacity overrides.

Start with 8 active kitchens and validate on the actual shared server for 30–60 minutes before trying 12 or 16. Include normal VPN load, simultaneous cold loads, same-network players, continuous rounds/contributions and idle lease expiry. Suggested gates: sustained total host CPU below 65%, at least 200 MiB available host RAM, service cgroup peak below 384 MiB, backend P95 below 100 ms/P99 below 200 ms, and no unexplained 5xx, timeouts, OOM or continuing memory growth. Cloud single-core tests are supporting evidence, not a Hetzner capacity guarantee.

With Nginx installed, run `python3 -m unittest tests.test_hosted_proxy`. The real-proxy checks cover public-page navigation from other sites, header forwarding and credential stripping, and rejection of cross-site game API requests. If Nginx is outside PATH, set `CHEFJEFF_NGINX_BIN` to its executable path.

1. Check `/healthz` with the configured Host and confirm the Python listener is loopback-only.
2. Use two browser pages to verify independent kitchens and connection settings.
3. Inspect outgoing browser traffic with a dummy key: it must appear only in the selected provider's Authorization header, never a same-origin request.
4. Verify remembered-key opt-in and clear/refresh behavior, provider CORS failure, explicit contribution, deletion, expiry and capacity limits.
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

`--data-dir` 启用自愿数据贡献，省略则禁用持久化贡献。刷新创建独立页面会话，闲置十分钟过期。`--max-sessions` 现在限制活跃厨房（默认 8，可配置 1–16），`--max-waiting` 提供额外的有限页面会话额度（默认 32，可配置 0–32）。浏览和填写／连接模型不占经营名额。暂停保留名额 60 秒，结算保留 30 秒，轮询不会延长保留；超时释放名额并保留页面状态，继续或下一局可能需要等待。断开页面的经营中对局仍在 8 秒后自动暂停。

经营名额已满时，仍可配置模型，开局／继续按钮显示等待；状态轮询发现空位后恢复按钮，须玩家再次点击，不自动开局或调用付费模型，也不承诺按等待顺序排队。页面会话池本身已满或服务不可用时，最多每 15 秒重试创建一次。

后端采用 128 个连接的等待队列，最多 32 个请求线程；按有效会话限制每秒 40 请求，突发额度 40，额度耗尽仍可暂停／结束／关闭厨房。Nginx 保留每 IP 每秒 500 请求的总量限制，以及每 IP 每分钟 15 次建房、突发 10 次的独立限制，容纳同一网络多人；无需活跃会话的删除凭证接口保留原每 IP 每秒 30 请求限制。无效 token 不创建后端限流记录。发布身份仅在服务启动时计算一次。审核过的网页脚本、图片、字体和音频由 Nginx 直接提供，保留 MIME、压缩和更新检查；HTML 与托管代理脚本仍走原 Python 路径，静态错误不缓存。空闲时仅在确有移动输入时记录停止，避免长期积累无效引擎输入。

## 凭据与记录

- Key 默认仅在 JavaScript 闭包内存中，主动记住才以明文保存至 localStorage，清除会移除两份。模型供应商须支持 CORS，不提供服务器代理回退。
- 回传游戏服务器的模型结果仅含已校验动作、冲刺值、数值 token 用量，不提交模型文本、端点或模型名称。服务器在内存处理正常游戏动作和完整状态。
- 普通会话不写磁盘日志或跨局记忆，默认手动贡献。明确同意政策后，可勾选自动贡献后续已结束的对局；开启时不补传已经结束的本局。取消同意或自动上传任一勾选，即停止后续自动上传。选择和删除凭证保存在此浏览器，清理浏览器存储会移除它们。记录区分单局同意（`round`）和持续同意（`standing`）。
- 贡献包含引擎事件／动作、每秒厨师位置、预设沟通代码、配置标识和结果统计。这是试点记录格式，最终 benchmark schema 和确定性回放另行设计。
- 私有保存 30 天，在启动、保存前及运行期间每 30 秒清理过期数据。随机删除凭证仅交给玩家，服务器只保存其哈希；遗失后需等待自动过期。删除不产生发布或邮件。
- 贡献记录不存账号、邮箱、IP、Key、模型端点、原始模型提示或回复；云与网络供应商仍按自己的政策处理连接元数据。
- 不备份贡献数据库或将其包含在服务器快照中，除非同步扩展保留／删除政策。所提供服务不生成备份，数据库目录不得公开访问或提交仓库。

进入下一局前先等待本局已同意的上传，避免重置后丢失记录。上传十秒超时，失败会显示提示并允许继续游戏。删除凭证可一起下载备份或批量删除；删除失败时保留对应凭证，方便重试。

## 服务器安装

上传经过审阅、仅含明确清单中的运行文件、网页构建、`hosted/` 与 `deploy/` 的 ZIP。验证包哈希及每条 release-manifest 记录，解压至 `/opt/chefjeff/releases/<version>`，在该目录执行 `deploy/install_backend.py`。服务以专用低权限账号运行，仅监听 `127.0.0.1:8780`，此步骤不公开网站。

当前试玩部署在运营者的 Hetzner 德国纽伦堡服务器，`chefjeff.belchingleo.online` 解析至这台服务器。

Nginx 模板限流、压缩响应并关闭访问／请求日志。获得公开发布授权后，从 Ubuntu 官方仓库安装 Nginx／Certbot，初期 HTTP 除 ACME 验证外仅返回 503。运营者接受证书订户条款后申请证书，再安装 HTTPS 配置，校验 Nginx 并测试续期。网页仅开放 80／443，不公开 Python 端口；证书留在服务器。

JavaScript 压缩同时覆盖 `text/javascript` 与 `application/javascript`，以兼容 Ubuntu/Python 的实际 MIME 类型。主要引擎脚本由约 5.7 MB 压至 0.95 MB。静态资源通过 ETag 和 `public, max-age=0, must-revalidate` 检查更新，内容未变则返回 304；Nginx 使用文件元数据 ETag，Python 托管代理脚本使用内容 ETag。HTML、API、健康检查和错误响应仍为 `no-store`，不长期缓存无版本号的脚本。

美术图集并发下载，全部完成后按原有顺序安装，保留后加载图集覆盖旧图集的规则。网页音频在第一次键盘／指针交互后按需下载正在使用的曲目及音效，不再在首屏下载整个音效目录；过晚到达的动作音效不补播，下载失败不会阻塞游戏。原生端保持整目录加载。真实用户首屏耗时仍受设备、网络和德国服务器到访客的往返延迟影响。

设置中的供应商、地址、模型及 Key 可以先填写；收到厨房状态且处于开局前／结算后，才允许测试、更换或清除配置。等待连接不会再误报“旧页面”；容量或网络错误显示在设置页，恢复连接时保留尚未提交的草稿。只填写不会发送模型请求或产生 API 调用费用。

后续更新可在服务器 SSH 终端以 root 执行 `python3 deploy/update_hetzner.py <完整提交 ID> <已测试部署包 SHA-256>`。脚本只从固定 Git 提交下载源码并打包，校验与本地测试包完全一致后，切换到新目录、重启厨房并检查健康状态，失败则回退旧版本和 Nginx 配置。它保留现有 systemd 容量／内存配置、记录数据和 VPN 配置。成功更新会结束正在进行的试玩对局；服务器部署与 Git 主线合并是独立操作。

在当前共用 VPN 的试玩服务器上，HTTPS 可用后以 root 执行 `bash deploy/finalize_hetzner.sh`。它为已启用的 `personal-vpn-firewall.service` 添加补充配置，在服务启动及重新加载后，通过现有 `inet personal_vpn_filter input` 链放行 TCP 80／443；原 VPN 加载脚本及其校验参数保持原样。脚本还安装仅针对试玩证书的 Nginx 重载钩子，启用 Certbot 定时器，并模拟续期及钩子执行。此脚本要求上述指定服务及规则链存在，不会重启服务器；实际开机持久化需在之后的维护重启时确认。

## 验证

`/ops/capacity` 仅从回环后端读取，公开 Nginx 入口拒绝访问。指标包含保留名额、页面会话数、拒绝数、近期响应 P95／P99、Python CPU／内存／线程和可用时的 Linux 服务 cgroup 内存；不包含会话 token、游戏 ID、IP 或模型正文。这些是后端指标，不是浏览器／网络延迟或整机 CPU。

获得合并及部署授权、安装新版后，在服务器 root SSH 终端执行 `python3 /opt/chefjeff/current/deploy/set_kitchen_capacity.py 8`，显式替换原来的两个厨房命令。内存／数据／VPN 设置保留；脚本重启厨房（结束现有对局），校验实际容量，失败则恢复原补充配置。普通版本更新会保留现有容量覆盖配置。

首档 8 个活跃厨房，在真实共用服务器测试 30–60 分钟后再试 12 或 16；覆盖正常 VPN 流量、同时冷启动、同一网络多人、连续游玩／贡献，以及空闲名额释放。建议门槛：整机 CPU 持续低于 65%、可用内存至少 200 MiB、服务 cgroup 峰值低于 384 MiB、后端 P95 低于 100 毫秒／P99 低于 200 毫秒；没有无法解释的 5xx、超时、OOM 或持续内存增长。云端单核测试提供参考，不能作为 Hetzner 容量保证。

安装 Nginx 后，运行 `python3 -m unittest tests.test_hosted_proxy`，通过真实代理验证外部链接打开首页、请求头转发、凭据移除，以及跨站游戏 API 请求被拒绝。Nginx 不在 PATH 时，可通过 `CHEFJEFF_NGINX_BIN` 指定可执行文件路径。

1. 使用配置的 Host 检查 `/healthz`，确认 Python 仅监听回环地址。
2. 用两个浏览器页面确认厨房和连接设置隔离。
3. 用占位 Key 检查出站请求：它只能出现在所选模型服务的 Authorization 中，不得出现在同源请求。
4. 验证记住／清除／刷新、CORS 失败、自愿贡献、删除、过期与容量限制。
5. 在 HTTPS 来源下用运营者提供的 Key 验证所选真实供应商。仅 OPTIONS 成功不代表真实模型调用成功。

DNS、HTTPS 和完整浏览器流程验证通过后，才将公开网址标为可用。届时同步更新 README 中的入口、启动方式和隐私说明。
