# 上海主站、德国海外站与统一数据服务

本方案以德国线上提交 `1cee1df842f19890077f1adc83e3f6d0e2ec30d8` 为基准。上海服务器已由操作者确认为 Ubuntu 24.04、x86_64、4 核 / 4 GB。备案状态由操作者确认已完成，接入状态仍需在腾讯云核验。

## 最终入口

| 主机记录 | IP | 用途 |
| --- | --- | --- |
| `@`、`www` | `101.34.212.148` | 上海游戏服务；`www` 跳转到主域名 |
| `global` | `2.31.58.179` | 德国游戏服务 |
| `data` | `101.34.212.148` | 两站后端使用的统一数据接口 |

Shanghai game → loopback data service. Germany game → authenticated HTTPS `data.chefjeff.online` → Shanghai data service. Both retain local game simulation. The data process alone writes the authoritative SQLite files. Nginx restricts the data virtual host to the German server address and the service independently checks separate regional tokens. Client tokens never appear in browser scripts, command-line arguments or the distributable ZIP.

## 行为和边界

- 贡献保存、更新、下载和删除统一经过数据服务，原有记录 ID、凭证哈希、内容、同意版本和绝对到期时间随数据库迁移保留。过期或删除的记录不能被更新或同一创建请求重新建立。
- 统计在各站私有目录 `shared-usage-outbox/usage.sqlite3` 中累计，后台约每两秒提交累计快照。统一服务在同一事务内保存流检查点并增加差额，普通重试与重启不会重复累加。网络故障不进入按键或状态轮询的统计路径。
- 贡献网络请求有三秒 socket 超时；创建可用相同请求标识重试一次。开局、结算或明确保存可能等待该请求；保存失败会明确反馈，不会假称持久化成功。活跃游戏不逐帧上传贡献数据库。
- `scripts/hosted_usage.py` 显示共享数据的范围和同步状态。汇总最多每两秒刷新；失联超过 15 秒显示未同步，首次成功前明确显示仅本站。全局运行会话是近 15 秒的后端估算，不是严格瞬时值。
- 浏览器估算仍使用各域名自己的本地标记，不是跨域去重人数。持久化增量文件与其流身份在同一个 SQLite 文件内，不要复制到另一站或清零后复用。
- 隐私说明已改为腾讯云中国上海保存；新贡献使用 `pilot-session-2026-10-v6`，旧自动贡献选择需重新确认。旧 v4/v5 数据仍可读取，不会改写为新同意版本。
- 数据服务每 30 秒清理过期记录。迁移临时包只用于一次切换，一小时后拒绝导入；操作完成后应立即清除临时副本。贡献数据库仍不做长期备份或包含进服务器快照。
- 进行中的对局是进程内存状态，部署重启需要结束对局并刷新页面。浏览器保存的模型设置和跨局记忆不会自动跨域迁移。

## 准备上海环境

在腾讯云网页终端执行；本地 SSH 不是前置条件：

```sh
sudo apt-get update
sudo apt-get install -y python3 nginx certbot unzip
```

通过腾讯云文件管理上传经过验证的 `chefjeff-web-demo.zip`。先用 `sha256sum` 对照随包摘要，再将包解压到独立的 `/opt/chefjeff/releases/china-shared/` 目录。包内根目录为 `chefjeff-web-demo/`。不要把私人配置和迁移数据放进程序目录。

## 先生成和审阅配置

下列命令仅生成文件，不修改在线 Nginx 或 systemd。以新发布目录为当前目录：

```sh
python3 deploy/render_region.py --domain chefjeff.online --alias www.chefjeff.online --data-domain data.chefjeff.online --peer-ip 2.31.58.179 --output-dir /root/chefjeff-cn-review
python3 deploy/render_region.py --domain global.chefjeff.online --legacy-redirect chefjeff.belchingleo.online --output-dir /root/chefjeff-global-review
python3 deploy/init_shared_config.py --output-dir /root/chefjeff-secrets --remote-url https://data.chefjeff.online
```

在上海生成的 `cn-client.json` 用 loopback，`global-client.json` 用加密远程接口。两份文件使用不同 token。配置目录为 0700，文件为 0600，不打印 token。通过操作者已有的安全连接或腾讯云文件管理转交德国配置，不通过聊天发送。

新 `global` / `data` 子域名可先添加 A 记录并申请自己的证书；原域名暂时保持德国解析。上海主域名和 `www` 的证书需在切换前准备，可使用 DNS 验证。签发证书时由操作者在控制台/Certbot 中处理账户及服务条款。私钥留在操作者控制的服务器或安全传输通道。

上海与德国都需要 80/443 入站，Python 的 8780、8790 保持 loopback。德国已有 VPN 规则，不运行面向其旧防火墙的 `finalize_hetzner.sh` 来配置上海；本套安装器不改 VPN 或防火墙。

## 区域后端安装

上海，以 root 在新发布目录运行：

```sh
python3 deploy/install_region.py --domain chefjeff.online --client-config /root/chefjeff-secrets/cn-client.json
```

安装器逐项验证 manifest，配置专用服务账号与私有统计目录，仅启动 loopback 游戏服务。已有安装需显式加 `--replace-existing`。它保留已有的厨房/等待/同网络名额设置，并用单独的区域 ExecStart drop-in 避免旧容量配置覆盖共享参数；失败会恢复原程序链接、服务文件和配置。更新不会自动安装公开 Nginx 配置。

德国安装对应版本时使用域名 `global.chefjeff.online`、它的 `global-client.json` 和 `--replace-existing`。重启结束当前对局。不要再使用旧的固定域名 `update_hetzner.py` 更新区域部署；新版本会拒绝这种操作。

容量调整使用新脚本，例如德国：

```sh
python3 deploy/set_kitchen_capacity.py 8 --host global.chefjeff.online
```

## 最终数据迁移窗口

在公开切换前安排短暂维护窗口，完成下面的有序操作。不要在本阶段之前更改原域名 A 记录。

1. 在德国核对实际 release-manifest、数据库完整性和服务参数。安装新包中的迁移脚本供 root 使用；不要用旧目录中的旧脚本替代。
2. 停止德国 `chefjeff.service`，确保旧写入收敛；上海的数据服务保持停止。游戏进程停止会结束当时的对局。
3. 德国导出短期迁移包，脚本使用 SQLite backup API 形成一致状态，校验数据库并只报告数量和摘要，不打印记录内容：

   ```sh
   python3 deploy/migrate_data.py export --output /tmp/chefjeff-transfer.zip --owner vpnadmin
   ```

4. 操作者通过现有德国 SSH 连接取回该 0600 文件，并通过腾讯云文件管理上传上海，整个过程控制在迁移窗口内。迁移包包含私人贡献数据，不上传聊天或公开仓库。
5. 上海导入到尚无数据库的专用目录（脚本拒绝覆盖现有数据库），逐文件核对摘要、完整性、原始 schema；导入不会重建贡献记录或延长其保存期：

   ```sh
   python3 deploy/migrate_data.py import --archive /path/to/chefjeff-transfer.zip
   ```

6. 对照两端验证输出及迁移凭据，确认上海的两份数据库完整并由 `chefjeff` 账号持有。在重新接收公开写入/删除前，清除德国原贡献数据库及其附属 SQLite 日志文件与所有迁移临时副本，避免旧副本脱离删除和到期管理；该清理仅在目标验证完成后进行。数据库回滚不能重新带回已删除记录。
7. 上海安装数据服务配置：将 `data-server.json` 安装到 `/etc/chefjeff/`，root:chefjeff、0640；将生成的 `chefjeff-data.service` 安装到 `/etc/systemd/system/`。`/var/lib/chefjeff-data` 为 chefjeff:chefjeff、0700。随后启动并启用数据服务。
8. 两个区域游戏服务都连接上海的数据服务。历史统计仅存在于主数据源的 `usage.sqlite3`，两站 outbox 从零开始，不能把历史累计值再分别导入两次。
9. 用测试贡献凭据验证跨站保存、下载和删除，并核对旧凭据及原到期时间；验证两站统计计数和重试。真实玩家记录的验证不要公开输出其内容。

## HTTPS 与 DNS 切换

在对应服务器核对生成的 Nginx 文件和证书后安装。先执行 `nginx -t`，通过后 reload。安装生成的 renewal hook，启用 Certbot timer 并验证续期；它只为相关域名 reload Nginx，不改动 VPN 服务。

最终将 `@` / `www` 改指上海，`global` 指德国，`data` 指上海。TTL 600 秒不保证所有客户端十分钟内都切换。在切换窗口明确处理德国旧域名入口的缓存流量与旧游戏会话，可采用短期维护响应；不能把两个私有数据库重新启用成独立写入源。原始 `chefjeff.belchingleo.online` 按生成的专用证书配置跳转到海外入口。

上线验收包括：国内实际访问、德国入口、同源 API 检查、共享数据服务鉴权、旧删除凭证、原过期时间、并发和断网恢复、统计口径、内存以及模型服务连通性。真实付费模型调用由操作者选定账号与用量另行验证；本地自动化测试不调用模型。
