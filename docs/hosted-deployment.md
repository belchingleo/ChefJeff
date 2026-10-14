# Hosted pilot deployment

The hosted runtime is separate from the local launcher. It uses the same kitchen rules with a new ephemeral session per browser page. Model HTTP calls run in the browser; the Python process has no model credential configuration or model network transport.

## Run for local verification

```sh
python3 hosted_server.py --origin http://127.0.0.1:19780 --port 19780 --data-dir /tmp/chefjeff-pilot-data
node tests/hosted_browser_test.cjs
python3 -m unittest tests.test_hosted tests.test_hosted_records
```

`--data-dir` enables explicit contributions. Omit it to disable persistent contributions. A refresh creates a new kitchen; inactive sessions expire after 10 minutes. Capacity defaults to eight kitchens, with a busy response when full. The public reverse proxy limits new sessions and API traffic.

## Credentials and records

- A key lives in a JavaScript closure by default. Explicit Remember stores it as plaintext in browser localStorage. Clear removes both copies. The selected model provider must allow CORS; there is no server proxy fallback.
- Model results sent to the game server contain a validated action, sprint flag and numeric token usage only. Provider text, endpoint and model name are not submitted. The game server receives normal gameplay actions and processes the full state in memory.
- Ordinary sessions create no disk journal or cross-round memory. A completed round is saved only after the player previews the policy and explicitly consents.
- Contributions contain engine event types/actions, one-second chef positions, preset communication codes, configuration identifiers and result statistics. They are a pilot record format, not the final benchmark schema or deterministic replay.
- Contributions are kept privately for 30 days. Cleanup runs at startup, before saving and every 30 seconds while the service runs. A random deletion token is delivered once to the player; only its hash is stored. Losing the receipt means waiting for automatic expiry. Deleting a record does not publish or email anything.
- No account, email, IP address, key, model endpoint, raw model prompt or response is stored in a contribution. The cloud/network provider still handles connection metadata under its own policies.
- Do not back up the contribution database or include it in server snapshots unless the retention/deletion policy is extended accordingly. The supplied service does not create backups. The database directory must not be web-served or committed.

## Server installation

Upload an audited ZIP containing the allowlisted runtime, web build and `hosted/`, `deploy/` files. Verify its hash and every release-manifest entry; extract under `/opt/chefjeff/releases/<version>` and execute `deploy/install_backend.py` there. The service runs as an unprivileged dedicated account and binds only `127.0.0.1:8780`. This step does not open the website publicly.

The current pilot uses the operator's Hetzner instance in Nuremberg, Germany, with `chefjeff.belchingleo.online` pointing to that server.

The supplied Nginx templates limit traffic, compress state responses and disable access/request logs. After public exposure is approved, install Nginx/Certbot from Ubuntu's official repositories; keep the initial HTTP site on a 503 response except for ACME challenges. Request the certificate only after the operator accepts the certificate issuer's subscriber terms. Then install the HTTPS template, validate Nginx configuration and test renewal. Allow only 80/443 for the web entry; never expose the Python port. Certificate files stay on the server.

On this pilot's shared VPN server, run `bash deploy/finalize_hetzner.sh` as root after HTTPS works. It adds a drop-in to the enabled `personal-vpn-firewall.service`, using the existing `inet personal_vpn_filter input` chain to allow TCP 80/443 after startup and reload. The reviewed VPN loader and its hash arguments remain intact. It also installs a certificate-specific Nginx reload hook, enables the Certbot timer, and tests renewal with the hook. This helper requires that exact firewall service/table and does not reboot the server; boot persistence has to be confirmed during a later maintenance reboot.

## Operational checks

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

`--data-dir` 启用自愿数据贡献，省略则禁用持久化贡献。刷新新建厨房，闲置十分钟会话过期。默认最多八个厨房，满时提示忙碌；公开反向代理限制新会话与 API 流量。

## 凭据与记录

- Key 默认仅在 JavaScript 闭包内存中，主动记住才以明文保存至 localStorage，清除会移除两份。模型供应商须支持 CORS，不提供服务器代理回退。
- 回传游戏服务器的模型结果仅含已校验动作、冲刺值、数值 token 用量，不提交模型文本、端点或模型名称。服务器在内存处理正常游戏动作和完整状态。
- 普通会话不写磁盘日志或跨局记忆。仅对已结束对局，在玩家预览政策并明确同意后保存。
- 贡献包含引擎事件／动作、每秒厨师位置、预设沟通代码、配置标识和结果统计。这是试点记录格式，最终 benchmark schema 和确定性回放另行设计。
- 私有保存 30 天，在启动、保存前及运行期间每 30 秒清理过期数据。随机删除凭证仅交给玩家，服务器只保存其哈希；遗失后需等待自动过期。删除不产生发布或邮件。
- 贡献记录不存账号、邮箱、IP、Key、模型端点、原始模型提示或回复；云与网络供应商仍按自己的政策处理连接元数据。
- 不备份贡献数据库或将其包含在服务器快照中，除非同步扩展保留／删除政策。所提供服务不生成备份，数据库目录不得公开访问或提交仓库。

## 服务器安装

上传经过审阅、仅含明确清单中的运行文件、网页构建、`hosted/` 与 `deploy/` 的 ZIP。验证包哈希及每条 release-manifest 记录，解压至 `/opt/chefjeff/releases/<version>`，在该目录执行 `deploy/install_backend.py`。服务以专用低权限账号运行，仅监听 `127.0.0.1:8780`，此步骤不公开网站。

当前试玩部署在运营者的 Hetzner 德国纽伦堡服务器，`chefjeff.belchingleo.online` 解析至这台服务器。

Nginx 模板限流、压缩响应并关闭访问／请求日志。获得公开发布授权后，从 Ubuntu 官方仓库安装 Nginx／Certbot，初期 HTTP 除 ACME 验证外仅返回 503。运营者接受证书订户条款后申请证书，再安装 HTTPS 配置，校验 Nginx 并测试续期。网页仅开放 80／443，不公开 Python 端口；证书留在服务器。

在当前共用 VPN 的试玩服务器上，HTTPS 可用后以 root 执行 `bash deploy/finalize_hetzner.sh`。它为已启用的 `personal-vpn-firewall.service` 添加补充配置，在服务启动及重新加载后，通过现有 `inet personal_vpn_filter input` 链放行 TCP 80／443；原 VPN 加载脚本及其校验参数保持原样。脚本还安装仅针对试玩证书的 Nginx 重载钩子，启用 Certbot 定时器，并模拟续期及钩子执行。此脚本要求上述指定服务及规则链存在，不会重启服务器；实际开机持久化需在之后的维护重启时确认。

## 验证

安装 Nginx 后，运行 `python3 -m unittest tests.test_hosted_proxy`，通过真实代理验证外部链接打开首页、请求头转发、凭据移除，以及跨站游戏 API 请求被拒绝。Nginx 不在 PATH 时，可通过 `CHEFJEFF_NGINX_BIN` 指定可执行文件路径。

1. 使用配置的 Host 检查 `/healthz`，确认 Python 仅监听回环地址。
2. 用两个浏览器页面确认厨房和连接设置隔离。
3. 用占位 Key 检查出站请求：它只能出现在所选模型服务的 Authorization 中，不得出现在同源请求。
4. 验证记住／清除／刷新、CORS 失败、自愿贡献、删除、过期与容量限制。
5. 在 HTTPS 来源下用运营者提供的 Key 验证所选真实供应商。仅 OPTIONS 成功不代表真实模型调用成功。

DNS、HTTPS 和完整浏览器流程验证通过后，才将公开网址标为可用。届时同步更新 README 中的入口、启动方式和隐私说明。
