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
- Throwing chefs turn their whole body toward diagonal aims when the optional painted pack `art/throw-diagonal-v1` is present (brief: `docs/art/throw-diagonal-spec.md`, importer: `scripts/art/throw_diagonals.py`); without it, throws keep the four-view bodies.

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
- 若提供可选美术包 `art/throw-diagonal-v1`，斜向投掷时厨师整个身体转向瞄准方向（需求见 `docs/art/throw-diagonal-spec.md`，导入脚本 `scripts/art/throw_diagonals.py`）；未提供时沿用四向身体。


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
