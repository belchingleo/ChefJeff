# ChefJeff 私人数据管理台 v2

入口仍为 **https://chefjeff.belchingleo.online/research-admin/**。沿用已有账号与海军蓝像素风。

## 这次增加的功能

- 每行可 **预览**或**下载本条**；勾选支持跨页保留，一次导出1至50条。应用新筛选时清空勾选。
- 预览分为概览、记录内保存的配置、分页事件。可筛选事件类型，展开查看JSON；旧记录未采集的内容保持未知，不使用当前游戏配置补填。
- 日期、关卡、版本和游戏入口筛选。关卡选项来自实际有效记录，不再写死1、2、3；兼容格式的新关卡有记录后就会出现。若将来研究schema或游戏数据接口改变，仍需同步适配管理台，不自动拉取或执行未审核的新代码。
- 自定义图表：全部筛选结果或仅勾选记录；按UTC开始日期、关卡、模型、完整性、结束原因、游戏入口分组；记录数、平均时长、平均出餐、平均金额、已结束贡献胜率、完整记录率。
- 柱状图、日期折线、数据表；导出全部分组CSV与带本地像素字体的独立SVG。图示超过30组时标记截取范围，CSV保留全部。表格显示前300组。
- 保存与载入图表配置JSON，自动记住上次设置。配置不包含研究记录、账号、密码或勾选引用；载入“仅已选”配置后需重新选择记录。

图表覆盖整个筛选范围，不限于当前50条页面。记录最多5000条时进行分析，超过则要求缩小范围。缺失值不计为0，每组显示有效与排除样本。胜率只使用结束时间和布尔胜负均已记录的样本；“完整”不等于“获胜”。图表仅代表仍有效的自愿贡献，不能解释为全部玩家或全站对局。

## 国内／海外的准确含义

这里的站点指**上海国内游戏入口（cn）**与**德国海外游戏入口（global）**，不是玩家本人所在地。不会采集或推断玩家的国家、IP或位置。

访问统计：从上海现有共享统计的站点累计检查点只读拆分；迁移前无法可靠归属的总量列为“来源未知”。所有分站加总与同一数据库快照的累计总量核对，不从总量倒猜历史分配。浏览器数为估算，跨站访问可能重复计数。

贡献来源：原研究记录没有站点字段。升级后，共享服务只对经过原认证流程、成功的新保存请求建立独立来源索引；历史记录或早于索引启用时间的旧创建重试不回填。来源来自认证的保存入口，不是客户端自行上报的国家。已有来源不会因跨站更新或重试而改写。

来源索引是 `/var/lib/chefjeff-data/record-sources.sqlite3` 新文件，只保存不可逆引用、站点与到期时间。不改变既有研究记录或贡献保存格式；索引失败不会把原本成功的研究保存改成失败，无法确认时显示未知。到期与撤回会清除对应索引。研究ZIP额外包含 `source-sites.json`，以研究包既有source_ref关联，不在原研究内容中补造字段。

将来 `chefjeff.online` 接回同一共享数据源与对应cn/global配置后，自然使用这套查询和来源索引，不需要另做域名下载功能。

## 只读导出令牌：在本机用脚本直接拉取

浏览器登录每次都要输入密码，下载时还要手动确认保存，所以不适合让本机脚本或 AI 定期拉取最新数据。只读导出令牌解决的就是这件事。令牌由研究者本人在上海服务器上签发，保存在自己电脑的私有文件里，之后由 `scripts/pull_research.py` 带着它直接下载研究包，不再经过浏览器。

### 令牌能做什么、不能做什么

令牌只能用于四个读取接口：记录列表 `api/records`、单条预览 `api/preview`、按筛选下载 `download/research.cjresearch.zip`，以及按勾选下载 `download/selected.cjresearch.zip`。带令牌访问其他任何地址都会得到 403，包括登录、登出、首页、图表和访问统计。令牌不能改账号，也不能做任何写操作。

令牌只认 `Authorization: Bearer` 请求头，放在网址参数或 Cookie 里都不会生效。请求里只要有这个请求头，服务器就只按令牌判断，不再看 Cookie。令牌请求也不碰浏览器登录的会话，所以新登录不会让令牌失效，用令牌也不会踢掉浏览器里的登录。

导出仍然受原有限制。一次只生成一份研究包，大小上限280MB，筛选范围最多5000条，发送前重新核对撤回和到期。研究包生成后、发送前，服务器还会再核对一次令牌，所以导出途中吊销令牌的话，这份包不会发出。

服务器不保存令牌本身。它在 `/etc/chefjeff-admin/export-token.json` 里只存令牌编号、scrypt 哈希和起止时间，文件属主和权限与 `auth.json` 相同。同一时间只有一枚令牌有效，重新签发就会作废旧令牌。管理服务每次收到令牌请求都会重新读这个文件，所以签发和吊销立即生效，不需要重启服务。

### 签发：只能由研究者本人执行

签发命令会在终端里显示令牌明文，而且只显示这一次。所以这条命令必须由研究者本人在腾讯云网页终端里运行，不要交给部署代理或 AI 执行，也不要把输出截图或复制到聊天里。下面的 `~/chefjeff-admin-token` 是上传管理包时使用的文件夹，若用了别的名字请相应替换：

```sh
sudo python3 ~/chefjeff-admin-token/upgrade_admin.py issue-export-token --days 90
```

有效期默认90天，可在1至365天之间选择。输出的最后一行就是令牌，以 `cjx1.` 开头。接着在自己电脑的仓库目录里运行下面的命令，在不回显的提示里粘贴这一行：

```sh
python3 scripts/pull_research.py save-token
```

令牌保存在 `~/.config/chefjeff/research-export.token`，文件权限600。这个位置在仓库外面，所以不会被提交。脚本发现文件权限宽于600、属主不是当前用户，或者文件放在仓库目录里时，都会拒绝使用。以后换成新令牌时，加 `--replace` 再运行一次。

### 使用

```sh
python3 scripts/pull_research.py pull --out ~/ChefJeff-research
```

`pull` 可以加 `--since`、`--until`（UTC日期，含首尾两天）、`--level`、`--schema`、`--site cn|global|unknown` 缩小范围。也可以先用 `list` 查看记录编号，再用 `--refs` 下载指定的1至50条：

```sh
python3 scripts/pull_research.py list --since 2026-10-01
```

```sh
python3 scripts/pull_research.py pull --out ~/ChefJeff-research --refs 编号1,编号2
```

脚本先把研究包写成目标目录里的临时文件，然后核对收到的字节数，再用仓库自带的 `verify_package` 核对 manifest，包括每个文件的哈希、文件清单和记录摘要。全部通过后，才以不覆盖的方式存成 `chefjeff-research-<UTC时间>.cjresearch.zip`，权限600。任何一步失败，临时文件都会删除，并报告原因。最后输出文件路径、局数、最早到期时间和ZIP的SHA-256，不会输出令牌。

服务器地址在脚本里固定为 `https://chefjeff.belchingleo.online`，脚本会验证证书，也不跟随重定向，所以令牌只会发往这个域名。AI 帮忙拉数据时只运行 `list` 和 `pull`，不读取令牌文件，也不运行 `save-token` 或服务器上的签发命令。

### 查看状态和吊销

```sh
sudo python3 ~/chefjeff-admin-token/upgrade_admin.py export-token-status
```

```sh
sudo python3 ~/chefjeff-admin-token/upgrade_admin.py revoke-export-token
```

状态只显示令牌编号、签发时间、到期时间和是否已过期，不显示哈希。吊销会删除服务器上的令牌文件，下一次请求就会被拒绝。吊销后本机的令牌文件已经没有用处，可以删掉。

### 审计和限流

每个令牌请求会在管理服务的 journald 日志里留一行，内容只有方法、接口名、状态码和令牌编号，例如 `export-token GET download 200 id=1a2b3c4d`。核对失败时编号记为 `-`。日志不记令牌、网址查询串、记录内容或 IP。管理服务只能看到本机代理地址，本来也拿不到真实 IP。查看最近的令牌使用：

```sh
sudo journalctl -u chefjeff-admin --since '7 days ago' | grep export-token
```

令牌失败单独计数，与密码登录互不影响。一分钟内失败满10次后，之后的令牌请求直接返回429，服务器不再计算哈希，所以乱填的令牌耗不了服务器资源。成功的请求不另设次数上限，因为泄露的令牌一次请求就能下载整个研究包，限次数挡不住泄露，起作用的是到期、吊销和审计。

### 风险与保管

令牌泄露就等于研究数据泄露。拿到令牌的人，在它到期或被吊销之前，可以下载全部仍然有效的贡献记录，令牌不按日期缩小范围。上面的到期、单一令牌、立即吊销、服务器只存哈希、只发往固定域名和审计日志都是为了缩小这个风险。研究者本人还需要做到下面几点：

- 令牌只从服务器终端复制到 `save-token` 的输入提示里，不要贴进聊天、文档、提交、云笔记或发给 AI。
- 不要在共用电脑上保存令牌，能登录这台电脑账号的人也能读到令牌文件。
- 怀疑泄露时先运行 `revoke-export-token`，再重新签发。
- 偶尔查看审计日志，确认没有意料之外的使用。
- 一段时间不需要拉取时，吊销令牌并删除本机文件。

### 部署：只更新上海管理台

令牌功能只改管理台，德国站没有管理台，不需要部署。在本机构建管理包：

```sh
python3 scripts/package_research_admin.py
```

解压 `dist/chefjeff-admin-v2.zip`，把里面的 `chefjeff-admin-v2` 文件夹改名为 `chefjeff-admin-token`，上传到 `/home/ubuntu`，不要覆盖已有的管理包文件夹。然后在上海执行：

```sh
sudo python3 ~/chefjeff-admin-token/upgrade_admin.py prepare-admin
```

准备阶段核对包摘要、管理配置、服务单元和账号文件元信息，并确认新包绑定的游戏文件与管理台配置里的游戏目录（`config.json` 的 `release`）一致，然后暂存新程序和候选服务单元。这一步不打开数据库、不修改线上配置、不重启服务，也不改变管理台绑定的游戏目录。

`/opt/chefjeff/current` 可能指向另一个游戏版本，例如试运行版。共享数据服务跟着 `current` 走，管理台则继续使用配置里绑定的游戏导出程序，这次更新不改变这一点。输出会同时列出两个目录，供核对研究格式是否一致。若报告游戏绑定不一致，说明这个包与管理台绑定的游戏不配套，例如 v7 发布升级还没有执行。这时不要继续，改用上面的 `prepare-release` / `activate-release` 流程，同一个新包会把令牌功能一起带上。若共享数据程序与正在运行的版本不同，准备也会停止，因为那需要完整发布升级。看到 `admin-code-prepared` 后，选无人下载数据的时段执行：

```sh
sudo python3 ~/chefjeff-admin-token/upgrade_admin.py activate-admin
```

激活只切换并重启 `chefjeff-admin.service`。游戏、共享数据服务、Nginx、游戏目录和账号文件都不变。重启会清掉内存里的登录会话，所以浏览器需要重新登录一次。验收访问登录页（200）、未登录的记录接口（401），以及带无效令牌请求头的选项接口（403）；最后一项证明 Nginx 把请求头转给了新程序。验收期间会核对游戏和共享数据服务进程没有变化，任何一步失败都会自动恢复原管理台。需要主动回退时执行：

```sh
sudo python3 ~/chefjeff-admin-token/upgrade_admin.py rollback-admin
```

回退恢复原管理台程序目录，新旧程序目录都会保留。旧程序不认令牌，所以回退后令牌只是不再生效，服务器上的令牌文件可以保留，也可以用 `revoke-export-token` 删除。

## 从主线构建与维护

源码位于 `ops/research_admin/`；服务端只用Python标准库。游戏代码、模型输入和研究保存仍在原有模块中，管理台不复制这些逻辑。

```sh
python3 scripts/package_research_admin.py
```

生成 `dist/chefjeff-admin-v2.zip`、独立SHA-256文件和包内allowlist清单；重复构建摘要一致。包中不含账号、配置、SQLite或研究下载。游戏ZIP与管理台ZIP分别打包，合并Git代码不会自动重启线上服务。

已有v2实例不需要因为本次代码归档而重新部署。下面的安装与升级工具是当前上海实例的固定版本操作手册，会拒绝未知服务配置或变化后的游戏目录。未来发布新游戏时先审核部署差异与研究schema，保留共享配置和来源观察器；不能把这些固定版本工具当成自动升级任意新提交的入口。

### v7 游戏发布时更新已有 v2 管理台

管理服务启动时从 `/etc/chefjeff-admin/config.json` 的 `release` 导入导出器和校验器，
不是每次跟随游戏 `current`。游戏升级必须同步更新此绑定。新管理包的
`game-binding.json` 固定同一次源码构建的运行模块、schema 和导出器的 SHA-256；
只核对 `research_export.py` 一个文件不足以判断兼容性。初次安装器也核对该绑定。

这个发布升级命令只认 2026-11-01 部署 25e4931 后核对过的上海实例：
- 游戏链接和管理配置绑定的都是 `china-free-25e4931a262b`；
- 管理台和共享数据服务都运行 `v2-818a6d7d18b0b8c1`（25e4931 的管理包）里的程序，在同一个目录；
- 这个目录里每个程序文件的 SHA-256 都写在 `release_upgrade.py` 里，任何一个不一致都会拒绝。

激活后，管理台和共享数据服务都改用新管理包的程序目录，配置绑定到新游戏目录；
共享数据服务的工作目录仍是 `/opt/chefjeff/current`。先暂存新游戏目录和独立管理包，然后执行（替换 `<新游戏目录>`）：

```sh
sudo python3 ~/chefjeff-admin-v2/upgrade_admin.py prepare-release --game-release '<新游戏目录>'
```

准备阶段只核对代码、配置、服务单元和账号文件元信息，备份配置及服务单元，
不打开数据库、不修改线上配置、不重启服务。未知的实例或额外修改会被拒绝。

激活有两个前提：上海的游戏链接已经切到新目录，并且上海游戏已经停止。
而 `deploy/install_free_region.py activate` 切换链接后会立刻启动游戏，
还要求管理和数据服务在它准备之后没有重启过。所以上海只能先切游戏、再停下，然后激活管理台。
两站游戏、协调服务和管理台的准备（`prepare`）都在停服前做完，维护窗口内按这个顺序执行：

1. 停止两站游戏（`sudo systemctl stop chefjeff.service`）。
2. 如果协调服务也要升级，在上海执行 `deploy/upgrade_free_gateway.py activate --allow-round-end`。
3. 上海执行 `deploy/install_free_region.py activate --site cn … --allow-round-end`，它会切换链接、启动游戏并自检。
4. 再次停止上海游戏。
5. 激活管理台：

   ```sh
   sudo python3 ~/chefjeff-admin-v2/upgrade_admin.py activate-release
   ```

6. 启动上海游戏，再在德国执行 `deploy/install_free_region.py activate --site de … --allow-round-end`。
7. 核对两站公开指纹一致、`/api/session` 返回 201、管理台登录页返回 200。

第 3 到第 4 步之间，上海的新游戏会短暂连着旧管理台运行；德国这时仍然停服。

第 5 步保留账号，更新管理配置里的游戏目录以及管理/数据服务的程序路径，
仅启动管理和共享数据服务，不启动游戏、不修改Nginx、不切换游戏软链接。
合成 v7 数据的预览和导出检查必须使用独立临时数据库和隔离服务，不写入生产库。

失败会恢复原配置和服务单元，**管理与数据服务保持停止**，避免混用同意版本。
不要单独恢复一站或直接启动旧服务。若需要主动回退，先停止两站游戏，再运行：

```sh
sudo python3 ~/chefjeff-admin-v2/upgrade_admin.py rollback-release
```

之后由协调流程回退两站游戏软链接，再启动旧版管理/数据和两站游戏。
旧代码目录、账号和所有数据库保留；不会恢复数据库快照或修改已有记录到期时间。

新装管理台可先运行包内 `install_admin.py prepare`、`install_admin.py activate`，自行设置账号；它只启用管理路径。需要来源追踪时再运行下述升级步骤。现有账号不会被升级工具重设。

本地／CI检查：Python用例使用合成数据库和隔离服务管理器；浏览器用例使用合成TLS站点，不需要实际服务器或任何密码。

```sh
npm ci
python3 -m pip install -r tests/requirements.txt
npx playwright install chromium
python3 -m unittest discover -s tests
python3 tests/run_admin_browser.py
```

浏览器检查需要Nginx与OpenSSL；可通过 `CHEFJEFF_NGINX_BIN`、`CHEFJEFF_CHROMIUM_BIN` 指定本机已有程序。产物默认放在被Git忽略的 `dist/admin-browser-check`；字体由安装包本地提供。Node依赖仅用于开发测试，不是线上管理服务依赖。

## 一次升级：在上海腾讯云网页终端执行

解压安装包，将整个 `chefjeff-admin-v2` 文件夹上传到 `/home/ubuntu`。不要覆盖原 `chefjeff-admin` 文件夹。

```sh
sudo python3 ~/chefjeff-admin-v2/upgrade_admin.py prepare
```

准备会校验包摘要、当前服务配置和游戏目录，暂存新程序与候选服务单元，备份原服务单元。**不读取密码内容、不查询玩家记录、不启动或重启服务、不修改Nginx或游戏。**看到 `admin-v2-prepared` 后再执行：

```sh
sudo python3 ~/chefjeff-admin-v2/upgrade_admin.py activate
```

激活会 **短暂重启 `chefjeff-data.service` 和 `chefjeff-admin.service`**，以启用认证来源索引及新管理页；这几秒共享保存/统计接口可能暂时不可用。请选无人进行数据下载、也尽量无对局的时段执行。游戏服务不重启，游戏current不切换，Nginx与域名配置不改。账号文件不变，管理台内存会话会失效，升级后刷新并用原账号重新登录。

升级没有导出、回填或恢复历史数据库。共享服务仍使用当前已验证游戏版本的原认证、保存、更新、删除与统计逻辑；原有例行的过期清理照常运行。新增的写入仅为独立来源索引。管理网页读取贡献与来源索引为SQLite `mode=ro/query_only`，统计拆分也使用只读事务；现有管理服务的只读文件系统限制保持不变。

激活验收只访问健康状态、公开登录页和未认证接口（必须401），检查游戏PID与目录、Nginx摘要、账号文件元信息不变；不会读取实际玩家记录，也不会运行模型或开局。

## 失败与回退

激活失败会恢复原管理／共享服务单元，并仅重启这两个服务；账号、游戏与所有数据库文件保留。不会删除新来源索引或回放、覆盖研究数据。

需要手动回退时，在上海执行：

```sh
sudo python3 ~/chefjeff-admin-v2/upgrade_admin.py rollback
```

升级后服务单元有额外修改时会拒绝覆盖，需先核对。旧管理台代码目录保留。回退不恢复数据库快照，也不撤销这期间正常新增的贡献记录。

## 验收与边界

安装后自行确认：原账号登录；勾选两条并导出；逐条预览配置和事件；按国内／海外／未知筛选；用不同分组生成图表；下载CSV、SVG，保存和载入配置。请不要把密码或原始玩家记录发进聊天。

开发测试只使用合成SQLite与合成记录。当前工作区没有线上SSH或登录凭证；线上成功需以操作者输出和浏览器检查为准。

新网页文件与脚本只安装到独立管理服务目录；未修改游戏Git分支、main或PR，也没有处理待备案域名。

像素字体与原管理台一致，源自Fusion Pixel 12px Proportional SC，SIL OFL 1.1；完整许可见OFL.txt。下载SVG内嵌字体及许可，无第三方图表脚本或外部数据上传。
