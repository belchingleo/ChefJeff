# Changelog

All notable changes to ChefJeff. Versions follow the in-game release identity (`release_info.VERSION`).

[中文](#更新记录)

## Unreleased

### Kitchen and controls
- Throw poses: while aiming, the chef turns to the aim direction (any angle) and winds up; after a throw both chefs show a short release toward the target. The poses reuse the painted chop arms, and the held item follows the hand.
- Phone layout: the hand and hint line moves into the top toolbar so nothing covers the kitchen, which grows about 10%; the joystick floats to the thumb; aiming turns through 360°; Dash sits to the left of Action on an arc around it, following the right thumb; urgent orders blink; menu buttons are at least 44 px tall; supported Android browsers vibrate briefly on aim and throw.
- The aim trajectory bends to the other chef when the throw will target them, and rings them in the UI's denim blue.
- Frying pans turn so the handle points at the chef: on a stove or counter toward its operation side, in hand back toward the holder (new west/north pan frames in the same light). Food keeps the same size in a throw pose as when carried.
- Phone controls are plain, as in most mobile games: a translucent stick ring with a knob, and round translucent Action and Dash buttons with a one-word label (Action reads Throw while aiming); the knob and Action turn denim blue while aiming. The kitchen is centred horizontally. While aiming, a round Cancel button appears above Action on the same arc; slide onto it (it turns red, "Release to cancel") and let go to cancel the throw. Button labels are at least 14 px and stay readable when a button is unavailable; on phones narrower than 700 px the arc is slightly smaller and the kitchen keeps clear of it.
- Throwing chefs turn their whole body toward diagonal aims (within 22.5° of a diagonal), with painted 3/4 front and back bodies for both chefs in `art/throw-diagonal-v1` (brief: `docs/art/throw-diagonal-spec.md`; drawn from the chefs-v2 masters by `scripts/art/throw_diagonal_bodies.py`, packed by `scripts/art/throw_diagonals.py`). Left diagonals mirror the right ones, like the left views.
- Station targeting works like Overcooked: Space acts on the station under a point 0.75 cells ahead of the chef's feet, framed in the kitchen (denim when there is something to do, ink when idle). There is no fallback to a station beside the chef, and the player is never moved to a station: they turn and work where they stand. Jeff walks to the centre of a free station side (no 0.30 side drop). Shared work keeps the perpendicular-side rule, judged from where each chef stands. Engine semantics `continuous-2026-10`; behaviour fingerprints and capacity reports regenerated.
- Jeff's arms are shorter (8 px from shoulder to mitten instead of 10) in every chefs-v2 pose and the diagonal throws, so they no longer read as overlong; chop grips move by up to 2 px and the knife still lands on the board.
- One press from results to the next round: the result card stays on the kitchen (the round record no longer pops up over it) with one main button, Next level after a win and Try again otherwise; Space, Enter, A/Start or the phone button start it after a short 3·2·1 at the same pace. Presses in the card's first second are ignored so mashing from the last order does not skip it.
- Settings has its own Data export page. It exports the whole play session: every round since the game started (online: the latest 20 rounds since the page opened), each with its level, result, work record, bookmarks, messages, usage and every allowlisted action event, instead of only the current round's last 80 events.
- Online version: after agreeing to the contribution terms, players can turn on automatic upload so every round that ends afterwards is contributed (30-day retention, as before) until they turn it off. The record notes the consent mode, the result card shows when it is on, and deletion receipts stay in the browser so uploads can be deleted later.
- Online capacity: active kitchens are limited separately from open pages (8 by default); a full server shows Waiting for a spot, and one network (an address or an IPv6 /64) may run at most 4 kitchens at once (`--max-per-network`). Pages that are not playing check the kitchen once a second instead of 20 times, and the online data export keeps the latest 20 rounds per page.
- Faster loading: the web build is now a release build without unused engine modules (engine 5.7 MB → 1.6 MB, page download about half). Build files carry content hashes, so the online version caches them for a year and a repeat visit downloads only what changed; HTTPS uses HTTP/2.
- Unsteady networks: a slow or failed state request no longer shows the disconnect screen or stops the chef. The page keeps the picture and the keys held, shows "Unsteady connection, reconnecting…", and calls it a disconnect only after 6 seconds without any state (the server still pauses a running round after 8). The loading card explains, after 4 seconds, that opening time depends on the network.
- iPhone: Jev forwarding works in iPhone browsers (the request now keeps its Origin header under the page's no-referrer policy). The Full screen button, which iPhone browsers cannot use, becomes a tip to add ChefJeff to the Home Screen, which now has the pot icon and the name ChefJeff. Controls describe the touch layout.
- Movement works as in Overcooked online: the browser walks the player's chef at once and reports its position about ten times a second; the engine follows with the same physics, within 1.25x walking speed, and resyncs only after a push, a blocked walk or a report too far ahead. On slow or unsteady networks the chef no longer jumps back. Space and throws carry the drawn position. New engine input `report_position`; Jeff is unchanged.
- Snappier actions: Space, throws and clicked actions reply with the resulting state, so the outcome shows one round trip sooner, and numbered states keep a late poll from undoing it. On the key press the chef leans toward what it acts on and the action's sound plays at once (the confirmed change then stays quiet); phones give a short haptic tick (Android vibration; iOS 18 a light tap).

## 0.6.0-beta.1 — 2026-10-01 · first public test release

The game now runs on a data-driven core: five data models (map, recipes, orders, equipment, level) describe every level, and the engine has no per-level code.

### Rules
- One rule set for every level: each round lasts 180 game seconds and the goal is net revenue at closing. Orders keep arriving until closing, and orders still open at closing carry no penalty.
- Burnt dishes: burnt for up to 5 s is accepted at the price −10; burnt longer is refused and the order keeps waiting. Serving a dish no order is waiting for costs 20.
- The 0.5.9 rules are removed: bad reviews, the delivery-count goal, ending the round as soon as the goal is met, and the remaining-time bonus.
- Level 1 is the practice level; Levels 2 and 3 are calibrated against a reference pair.

### Kitchen and controls
- Overcooked-style keyboard controls with browser-safe keys: Space acts on what the chef faces (hold it to aim a throw), Shift dashes, Enter bookmarks.
- Beef fries in a frying pan; the engine also supports a soup pot for noodles, and each stove holds one vessel.
- Chefs can pass plates, dishes, pans and the extinguisher up to 4 tiles; ingredients are thrown up to 4 tiles.
- Assemble with a plate or ingredient lying on the floor, as on a counter.
- One chef body size against every workstation: chefs stay off cabinet fronts and work from where walking stops.
- Walking slides around shallow notches; stalled routes re-plan around the other chef; "go partner" walks into the other chef on purpose.

### Jeff (the AI teammate)
- Clear chef names (`human`, `jeff`) and fewer duplicate choices in Jeff's input; a plate's missing parts name the state they need.
- Jeff's rules are generated from the same frozen configuration as the engine, with no collaboration-value wording.

### Records and analysis
- Every round is recorded as one event stream and a replayable session bundle.
- End-of-round record of who did which work, shown after closing.
- Item provenance and collaboration analysis. The round record shows three experimental measures: contribution by standard time (configured work plus the shortest walk needed), delay beyond the ideal split between the chefs, and idle time. The analyzer also reports each dish's critical path.
- Capacity Analyzer and a calibration ladder (solo, solo with random partner, pair).
- Behaviour fingerprints of the three levels guard against unintended rule changes.

### Presentation
- Kitchen UI design system, pixel font, music and sound effects.
- Both chefs are drawn from one master body per view, so they keep their size while chopping; the knife is its own layer.
- Eight more ingredients (cucumber, onion, cheese, scallion, chicken, fish, flatbread, noodles) and six recipes with pixel art, ready for new levels.
- Burnt dishes are recognisable wherever they are.

## 0.5.9-alpha — 2026-09-27

First private release: a local browser game with three playable maps and player-supplied model connections.

---

## 更新记录

### 未发布

- 投掷动作：瞄准时人物转向瞄准方向（任意角度）并做出蓄力姿势；投出后两位厨师都会朝目标短暂显示出手姿势。姿势沿用已绘制的切菜手臂，手中物品跟随手部。
- 手机界面：手中物品和提示移到顶部工具栏，不再遮挡厨房，厨房画面约放大 10%；摇杆出现在拇指按下处；瞄准方向 360° 连续；「冲刺」在「操作」左侧，沿右手拇指的弧线围绕操作键排列；快超时的订单闪烁；菜单按钮至少 44 像素高；支持的安卓浏览器在瞄准和投出时轻微震动。
- 投掷会瞄准另一位厨师时，抛物线弯向他并用牛仔蓝圈标出。
- 平底锅统一让手柄朝向厨师：在灶台或柜台上朝工位的操作侧，拿在手里时朝向持锅者（新增朝左、朝上两个方向的锅，光照一致）。投掷姿势中的食物与平时手持大小一致。
- 手机按键按常见手游简化：半透明摇杆圈加摇杆头，半透明圆形「操作」「冲刺」键只显示一个词（瞄准时操作键显示「投掷」），瞄准时摇杆头和操作键变为海军蓝。厨房画面水平居中。瞄准时操作键上方（同一弧线上）出现圆形「取消」键，手指滑到上面（变红并提示「松手取消」）后松开即取消投掷。按键文字至少 14 像素，按键不可用时文字仍清晰可读；宽度小于 700 像素的手机上弧形按键略小，厨房画面不被遮挡。
- 斜向投掷时（瞄准方向在斜向 ±22.5° 内）厨师整个身体转向瞄准方向，两位厨师新增四分之三正面和背面身体，美术包 `art/throw-diagonal-v1`（需求见 `docs/art/throw-diagonal-spec.md`；由 `scripts/art/throw_diagonal_bodies.py` 从 chefs-v2 母版绘制，`scripts/art/throw_diagonals.py` 打包）。左向斜向与左向视图一样由右向镜像。
- 选中工位改成《胡闹厨房》的方式：空格操作脚下往前 0.75 格处的工位，并在厨房里框出（有事可做时为牛仔蓝，否则为墨色）。不再改用身边的工位，玩家也不会被挪到工位前，原地转身操作。Jeff 走到空闲操作侧的正中（去掉侧面 0.30 的下偏）。共用工位仍要求相互垂直的两侧，按各自实际站位判断。引擎语义改为 `continuous-2026-10`，行为指纹和产能报告已重新生成。
- Jeff 的手臂缩短（肩到手套 8 像素，原为 10），涵盖 chefs-v2 的全部姿势和斜向投掷，不再显得过长；切菜握点最多移动 2 像素，刀仍落在砧板上。
- 结算后一键进入下一局：结算卡片留在厨房画面上（本局记录不再弹窗遮挡），只有一个主按钮，达成目标为「下一关」，否则为「再来一次」；空格、Enter、手柄 A/Start 或手机按钮都可触发，短暂 3·2·1 后按原节奏开局。卡片出现后的第一秒内忽略按键，避免最后一单连按时误跳过。
- 设置中新增单独的「数据导出」页，导出本次游玩的全部数据：本机版从启动游戏起的每一局、在线版打开页面以来最近 20 局，各含关卡、结果、贡献记录、标记、沟通、调用用量和全部允许清单内的动作事件，不再只有当前局最近 80 条事件。
- 在线版：同意贡献条款后可开启「以后每局结束自动上传」，此后每局结束自动贡献（仍保存 30 天），随时可关闭。记录注明同意方式，开启时结算卡片有提示，删除凭证保存在浏览器中，之后仍可删除。
- 在线版容量：正在经营的厨房与打开的页面分开计数（默认 8 个厨房），满了显示「等待空位」；同一网络（同一地址或同一 IPv6 /64）最多同时开 4 个厨房（`--max-per-network`）。没在经营的页面每秒只检查一次厨房（原为 20 次），在线版数据导出每个页面保留最近 20 局。
- 加载更快：网页改为正式模式构建并去掉未用的引擎模块（引擎 5.7 MB → 1.6 MB，页面下载量约减半）。构建文件名带内容哈希，在线版缓存一年，再次打开只下载有变化的文件；HTTPS 启用 HTTP/2。
- 网络不稳：偶尔一次状态请求变慢或失败，不再弹出断连画面，也不会让人物停下。画面和按住的方向键保持不变，提示「网络不稳定，正在重连…」；连续 6 秒收不到任何状态才算断线（服务器仍在 8 秒后自动暂停）。打开超过 4 秒时，加载卡片会说明打开快慢取决于网络。
- iPhone：iPhone 浏览器里可以正常通过服务器转发调用 Jev（该请求在页面的不发送来源策略下也会带上来源）。iPhone 浏览器不支持的「全屏」按钮换成「添加到主屏幕」的提示，主屏幕图标为像素锅，名称为 ChefJeff。操作说明加入触屏玩法。
- 移动改成《胡闹厨房》联机的方式：浏览器立刻移动玩家的厨师，每秒约 10 次报告位置；引擎用同样的物理跟上，最多 1.25 倍走路速度，只在被推开、走不过去或报告太远时重新同步。网络慢或不稳时人物不再被拽回。空格和投掷会带上画面上的位置。新增引擎输入 `report_position`；Jeff 不变。
- 操作更跟手：空格、投掷和点选动作的回复直接带回执行后的状态，结果早一个来回显示；状态带序号，迟到的旧状态不会把它盖回去。按下时人物立刻朝目标前探，并先播放该动作的音效（确认后不再重复）；手机上轻振一下（安卓为振动，iOS 18 为轻触感）。


## 0.6.0-beta.1 — 2026-10-01 · 首次公开测试版

游戏改为运行在数据驱动内核上：每一关都由五个数据模型（地图、菜谱、订单、设备、关卡）描述，引擎里没有针对某一关的代码。

### 规则
- 所有关卡使用同一套规则：每局 180 游戏秒，目标是关店时的净收入。订单持续到关店，关店时仍未完成的订单不扣钱。
- 糊菜：糊了 5 秒以内的按价格减 10 元收下；糊得更久会被拒收，订单继续等待。送出没有订单在等的菜扣 20 元。
- 删除 0.5.9 的旧规则：差评、出餐数目标、达标立即结束、剩余时间奖励。
- 第一关是练习关；第二、三关按参考双人组校准。

### 厨房与操作
- 胡闹厨房式键盘操作，按键避开浏览器冲突：空格对面前的东西操作（按住可瞄准投掷），Shift 冲刺，Enter 标记。
- 牛肉用平底锅煎；引擎也支持煮面条的汤锅，一个灶台同时只放一口锅。
- 盘子、菜、平底锅和灭火器可在 4 格内传递；食材可在 4 格内抛出。
- 盘子或食材放在地上时，也能像在柜台上一样组装。
- 厨师对所有工位使用同一身体尺寸：不再踩进柜台正面，走到哪里停下就在哪里操作。
- 行走时能滑过浅凹口；卡住的路线会绕开对方重新规划；“走向搭档”可以主动走到对方身边。

### Jeff（AI 队友）
- Jeff 的输入里厨师称呼明确（`human`、`jeff`），重复选项更少；盘子缺的部件写明所需状态。
- Jeff 看到的规则和引擎来自同一份冻结配置，不含任何“应该合作”的价值措辞。

### 记录与分析
- 每局记录为一条事件流，并生成可回放的对局包。
- 关店后显示本局记录：谁做了哪些活。
- 物品来历追踪与协作分析。本局记录显示三项试验性指标：按标准时间计算的贡献（配置里的操作时间加必要的最短走路）、超出理想的拖延（在两人之间分摊）和空转时间。分析工具还会给出每道菜的关键路径。
- 容量分析器，以及校准阶梯（单人、单人加随机搭档、双人）。
- 三关的行为指纹，防止规则被无意改动。

### 画面与声音
- 厨房界面设计规范、像素字体、音乐与音效。
- 两名厨师的每个视角都从同一个身体母版画出，切菜时不再变大；刀单独一层。
- 新增八种食材（黄瓜、洋葱、芝士、葱、鸡肉、鱼、饼、面条）和六道菜谱及像素图，可用于新关卡。
- 糊了的菜在任何位置都能认出来。

## 0.5.9-alpha — 2026-09-27

首个私有版本：本地浏览器游戏，三张可玩地图，玩家自带模型连接。
