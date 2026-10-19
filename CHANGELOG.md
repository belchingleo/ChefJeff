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
- Space targeting works like Overcooked 2: among the stations in the eight cells around the chef, Space uses the one most squarely ahead along the aim (the stick in any direction), within 0.85 cells of the feet, never one beside or behind; the straight-ahead station keeps the target until the aim is about 30 degrees off, so a slightly tilted stick never picks a diagonal, and aiming sideways counts from the cell the hands are over. The page frames the target the moment the chef turns and sends it with the press; the engine accepts it only if it can still pick it from the reported position and aim (engine inputs `face` and `pick_station`). A loose item on the aimed tile or at the feet that lies nearer the point ahead goes first, and is ringed. Jeff walks to the centre of a free station side, and works in place when his pick is straight ahead. Shared work keeps the perpendicular-side rule.
- Jeff's arms are shorter (8 px from shoulder to mitten instead of 10) in every chefs-v2 pose and the diagonal throws, so they no longer read as overlong; chop grips move by up to 2 px and the knife still lands on the board.
- One press from results to the next round: the result card stays on the kitchen (the round record no longer pops up over it) with one main button, Next level after a win and Try again otherwise; Space, Enter, A/Start or the phone button start it after a short 3·2·1 at the same pace. Presses in the card's first second are ignored so mashing from the last order does not skip it.
- Settings has its own Data export page. It exports the whole play session: every round since the game started (online: the latest 20 rounds since the page opened), each with its level, result, work record, bookmarks, messages, usage and every allowlisted action event, instead of only the current round's last 80 events.
- Online capacity: active kitchens are limited separately from open pages (8 by default); a full server shows Waiting for a spot, and one network (an address or an IPv6 /64) may run at most 4 kitchens at once (`--max-per-network`). Pages that are not playing check the kitchen once a second instead of 20 times, and the online data export keeps the latest 20 rounds per page.
- Faster loading: the web build is now a release build without unused engine modules (engine 5.7 MB → 1.6 MB, page download about half). Build files carry content hashes, so the online version caches them for a year and a repeat visit downloads only what changed; HTTPS uses HTTP/2.
- Unsteady networks: a slow or failed state request no longer shows the disconnect screen or stops the chef. The page keeps the picture and the keys held, shows "Unsteady connection, reconnecting…", and calls it a disconnect only after 6 seconds without any state (the server still pauses a running round after 8). The loading card explains, after 4 seconds, that opening time depends on the network.
- iPhone: Jev forwarding works in iPhone browsers (the request now keeps its Origin header under the page's no-referrer policy). The Full screen button, which iPhone browsers cannot use, becomes a tip to add ChefJeff to the Home Screen, which now has the pot icon and the name ChefJeff. Controls describe the touch layout.
- Movement works as in Overcooked online: the browser walks the player's chef at once and reports its position about ten times a second; the engine follows with the same physics, within 1.25x walking speed, and resyncs only after a push, a blocked walk or a report too far ahead. On slow or unsteady networks the chef no longer jumps back. Space and throws carry the drawn position. New engine input `report_position`; Jeff is unchanged.
- Snappier actions: Space, throws and clicked actions reply with the resulting state, so the outcome shows one round trip sooner, and numbered states keep a late poll from undoing it. On the key press the chef leans toward what it acts on and the action's sound plays at once (the confirmed change then stays quiet); phones give a short haptic tick (Android vibration; iOS 18 a light tap).
- Fixed: with local movement, the chef could not move at all when Jeff stood in the way (for example stepping out from between counters with Jeff just above): the browser treated Jeff as a wall and so never reported a move for the engine to push him aside. When Jeff blocks the local walk, the browser now reports that it is pressing and follows the engine, which walks with the held direction as keyboard walking always did (an idle Jeff is pushed, a busy one is not). Held-direction walking no longer slides back against the walk or corner-slides away from a chef, which made the chef jitter when pressing into a busy Jeff in a narrow corridor; routed walking is unchanged. A chase that stops getting closer to the reported point resyncs.
- Fixed: on iPhone every Action press paused the round. The haptic tick's hidden switch took focus, which the touch and controller code read as typing into a field; it is now excluded from that check and gives focus straight back.
- Fixed: after rotating an iPhone, the kitchen could stay drawn at the portrait size (only a strip, magnified, the rest black). The page announces the size again once it settles, and once a second checks that the canvas fills the window with a drawing buffer of the same shape. The data export now includes position resyncs (reason and position) to diagnose places where the chef seems stuck.
- Fixed: in the web build, a burst of earlier event sounds could replay at once about every 80 events in a round (the release compiler dropped a set copy).
- Overcooked feel, round two: every cabinet is walked up to from behind, as boards were, so a chef works at any counter from the same line and the board notches (where chefs got stuck) are gone. Chopping or washing started in place first slides the chef sideways onto the station's centre (about 0.1 s), never toward it. Work is sticky: no button stops it, walking away does. After a throw, or once work starts, the direction still held waits for the stick to return to neutral or turn 15 degrees; a second press within 0.5 s of a pick-up is ignored. Chopping takes 3 s with a quicker knife (about 3.7 strikes a second). The dash starts at 2x and eases back to walking over 1 s, ready again when it ends. A throw is caught when it passes within reach of an empty-handed partner on its way, and a throw you will catch is ringed. Two chefs meeting head-on in a passage too narrow to pass no longer lock: the one with farther to go steps aside. Engine semantics `continuous-2026-10b`; fingerprints, capacity reports and calibration regenerated.
- Phones: Grab (picks up or puts down at once, even holding a throwable item) and Throw (hold to aim, release to throw; tap throws straight away) join Action and Dash; keyboard and gamepad are unchanged.
- Fixed: the chef could freeze for the rest of a round after sliding along a counter corner on a phone (a walk started from a point drawn between two steps, inside the counter). The page now steps its chef 60 times a game second.
- Fixed: food and plates on the floor just below a counter were half hidden by its front panel; floor items now draw in front of the cabinets behind them, by row, on any layout.
- Maps from coordinates: `map_definition.build_map` turns station coordinates and facings into a full map, and `scripts/audit_map.py` checks any map (Space selection, stuck points for the engine and the page, hidden floor items, passages too narrow to pass, scripted solo and pair play). Levels place starting items by station type (`at_type`), the page accepts any map name, and vertical counter runs get the trimmed front panel.
- Online launch: contribution consent is asked once before the first round, with two equal choices (contribute every round from now on, kept 30 days and deletable with the receipts kept in the browser, or not now); it can be changed in Settings, and the result card offers a one-tap 贡献本局 for this round. The consent text is versioned `pilot-session-2026-10-v2`. New privacy page and model-connection guide (supported providers, rough cost per round). The data export includes page-side diagnostics (recent frames and errors) for bug reports, with how to report on GitHub. A local load test checks the waiting page and the per-network limit.

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
- 空格选目标改成《胡闹厨房 2》的方式：在角色周围 8 格的工位里，选最正对瞄准方向的那个（瞄准随摇杆可以是任意方向），离脚下 0.85 格以内，身边和身后的不会选；瞄准偏离约 30° 之前一直选正前方的，摇杆稍偏不会选到斜对角，朝左右瞄准时按手所在的那一格计算。角色一转身，页面立即框出目标，按键时一并发出；引擎核对从报告的位置和朝向仍能选中它才采用（引擎输入 `face` 和 `pick_station`）。瞄准那格或脚下的散落物品更靠近前方那点时先操作物品，并用蓝圈标出。Jeff 走到空闲操作侧的正中，要选的工位在正前方时原地操作。共用工位仍要求相互垂直的两侧。
- Jeff 的手臂缩短（肩到手套 8 像素，原为 10），涵盖 chefs-v2 的全部姿势和斜向投掷，不再显得过长；切菜握点最多移动 2 像素，刀仍落在砧板上。
- 结算后一键进入下一局：结算卡片留在厨房画面上（本局记录不再弹窗遮挡），只有一个主按钮，达成目标为「下一关」，否则为「再来一次」；空格、Enter、手柄 A/Start 或手机按钮都可触发，短暂 3·2·1 后按原节奏开局。卡片出现后的第一秒内忽略按键，避免最后一单连按时误跳过。
- 设置中新增单独的「数据导出」页，导出本次游玩的全部数据：本机版从启动游戏起的每一局、在线版打开页面以来最近 20 局，各含关卡、结果、贡献记录、标记、沟通、调用用量和全部允许清单内的动作事件，不再只有当前局最近 80 条事件。
- 在线版容量：正在经营的厨房与打开的页面分开计数（默认 8 个厨房），满了显示「等待空位」；同一网络（同一地址或同一 IPv6 /64）最多同时开 4 个厨房（`--max-per-network`）。没在经营的页面每秒只检查一次厨房（原为 20 次），在线版数据导出每个页面保留最近 20 局。
- 加载更快：网页改为正式模式构建并去掉未用的引擎模块（引擎 5.7 MB → 1.6 MB，页面下载量约减半）。构建文件名带内容哈希，在线版缓存一年，再次打开只下载有变化的文件；HTTPS 启用 HTTP/2。
- 网络不稳：偶尔一次状态请求变慢或失败，不再弹出断连画面，也不会让人物停下。画面和按住的方向键保持不变，提示「网络不稳定，正在重连…」；连续 6 秒收不到任何状态才算断线（服务器仍在 8 秒后自动暂停）。打开超过 4 秒时，加载卡片会说明打开快慢取决于网络。
- iPhone：iPhone 浏览器里可以正常通过服务器转发调用 Jev（该请求在页面的不发送来源策略下也会带上来源）。iPhone 浏览器不支持的「全屏」按钮换成「添加到主屏幕」的提示，主屏幕图标为像素锅，名称为 ChefJeff。操作说明加入触屏玩法。
- 移动改成《胡闹厨房》联机的方式：浏览器立刻移动玩家的厨师，每秒约 10 次报告位置；引擎用同样的物理跟上，最多 1.25 倍走路速度，只在被推开、走不过去或报告太远时重新同步。网络慢或不稳时人物不再被拽回。空格和投掷会带上画面上的位置。新增引擎输入 `report_position`；Jeff 不变。
- 操作更跟手：空格、投掷和点选动作的回复直接带回执行后的状态，结果早一个来回显示；状态带序号，迟到的旧状态不会把它盖回去。按下时人物立刻朝目标前探，并先播放该动作的音效（确认后不再重复）；手机上轻振一下（安卓为振动，iOS 18 为轻触感）。
- 修复：浏览器负责移动后，Jeff 挡在路上时人物可能完全不动（例如从两个柜台之间走出来、Jeff 在上方）：浏览器把 Jeff 当成墙，从不报告移动，引擎也就没机会推开他。现在 Jeff 挡住本地行走时，浏览器报告「正在挤」并跟随引擎，引擎按按住的方向照原来的键盘走法移动（空闲的 Jeff 会被推开，正在干活的不会）。按住方向走路时不再向后侧滑、也不会因为厨师挡路而贴边滑出，避免在窄通道顶着正在干活的 Jeff 时抖动；沿路线走路不变。追位置时离目标不再变近就重新同步。
- 修复：iPhone 上每按一次「操作」都会暂停对局。触感用的隐藏开关抢走了焦点，触屏和手柄代码把它当成在输入框里打字；现在判断时排除它，并立即把焦点还回去。
- 修复：iPhone 转屏后，厨房可能仍按竖屏尺寸绘制（只画一条、被放大、其余为黑）。页面在尺寸稳定后再通知一次，并每秒检查画布是否铺满窗口、绘制缓冲区形状是否一致。数据导出加入位置重新同步（原因和位置），便于排查人物「卡住」的地方。
- 修复：网页版一局里大约每 80 个事件，会一下子重放一批之前的事件音效（正式构建的编译器漏拷了一个集合）。

- 手感第二轮对齐《胡闹厨房》：所有柜台背面都能走到贴边，和案板一样，站在哪个柜台前操作都在同一条线上，原来案板凹槽处会卡人的问题随之消失。原地开始切菜或洗碗时，先侧移到工位正中（约 0.1 秒），不会向前挪。切菜、洗碗开始后任何按键都不会打断，走开才停。扔出东西或开始工作后，仍按着的方向要等摇杆回中或转过 15° 才移动；拿起后 0.5 秒内再按会被忽略。切菜改为 3 秒，挥刀更快（每秒约 3.7 下）。冲刺起步 2 倍速、1 秒内平滑回落，结束后可立即再冲。扔出的东西飞行途中经过空手队友身边就能接住，玩家能接住的也会标出。窄到无法错身的通道里迎面相遇不再僵持：剩余路程更长的一方让路。引擎规则版本 `continuous-2026-10b`，行为指纹、容量报告和校准已重新生成。
- 手机：在「操作」「冲刺」旁新增「拿放」（按下立即拿起或放下，手持可投掷物品时也一样）和「扔」（按住瞄准、松开扔出，点按直接扔出）；键盘和手柄不变。
- 修复：手机上贴着柜台转角滑动后，人物可能一直卡到本局结束（新一段移动从两步之间画出的点出发，而那一点在柜台里）。页面现在每游戏秒走 60 步。
- 修复：柜台正下方地上的食物和盘子会被柜台前面板挡住一半；地上物品现在按行画在后排柜台前面，任何布局都成立。
- 按坐标生成地图：`map_definition.build_map` 把工位坐标和朝向生成完整地图，`scripts/audit_map.py` 可检查任意地图（空格选取、引擎和页面是否卡住、地上物品遮挡、无法错身的窄通道、脚本单人与双人试玩）。关卡初始物品按工位类型放置（`at_type`），页面接受任意地图名，竖排柜台也用带装饰的前面板。
- 在线公测准备：首局开始前询问一次是否同意贡献数据，两个同等选项（以后每局自动贡献，保存 30 天，可凭浏览器里的凭证删除；或暂不），可在设置中修改，结算卡片可一键「贡献本局」。同意文本版本为 `pilot-session-2026-10-v2`。新增隐私说明页和模型连接说明（支持的服务、一局大约花费）。数据导出加入页面端诊断（最近的帧和报错），并说明如何在 GitHub 反馈。新增本地压测脚本，检查排队页面和每个网络的上限。

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
