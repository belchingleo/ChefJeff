# Changelog

All notable changes to ChefJeff. Versions follow the in-game release identity (`release_info.VERSION`).

[中文](#更新记录)

## 0.6.0-alpha — 2026-10-01

The game now runs on a data-driven core: five data models (map, recipes, orders, equipment, level) describe every level, and the engine has no per-level code.

### Rules
- One rule set for every level: each round lasts 180 game seconds and the goal is net revenue at closing. Orders keep arriving until closing, and orders still open at closing carry no penalty.
- Burnt dishes: burnt for up to 5 s is accepted at the price −10; burnt longer is refused and the order keeps waiting. Serving a dish no order is waiting for costs 20.
- The 0.5.9 rules are removed: bad reviews, the delivery-count goal, ending the round as soon as the goal is met, and the remaining-time bonus.
- Level 1 is the practice level; Levels 2 and 3 are calibrated against a reference pair.

### Kitchen and controls
- Overcooked-style keyboard controls: Space and E act on what the chef faces; Q dashes.
- Chefs can pass plates, dishes, pots and the extinguisher up to 4 tiles; ingredients are thrown up to 4 tiles.
- Assemble with a plate or ingredient lying on the floor, as on a counter.
- One chef body size against every workstation: chefs stay off cabinet fronts and work from where walking stops.
- Walking slides around shallow notches; stalled routes re-plan around the other chef; "go partner" walks into the other chef on purpose.

### Jeff (the AI teammate)
- Plain English input with clear chef names and fewer duplicate choices.
- Jeff's rules are generated from the same frozen configuration as the engine, with no collaboration-value wording.

### Records and analysis
- Every round is recorded as one event stream and a replayable session bundle.
- End-of-round record of who did which work, shown after closing.
- Item provenance, collaboration analysis, and contribution measured by time (effort and critical path).
- Capacity Analyzer and a calibration ladder (solo, solo with random partner, pair).
- Behaviour fingerprints of the three levels guard against unintended rule changes.

### Presentation
- Kitchen UI design system, pixel font, music and sound effects.
- Burnt dishes are recognisable wherever they are.

## 0.5.9-alpha — 2026-09-27

First private release: a local browser game with three playable maps and player-supplied model connections.

---

## 更新记录

## 0.6.0-alpha — 2026-10-01

游戏改为运行在数据驱动内核上：每一关都由五个数据模型（地图、菜谱、订单、设备、关卡）描述，引擎里没有针对某一关的代码。

### 规则
- 所有关卡使用同一套规则：每局 180 游戏秒，目标是关店时的净收入。订单持续到关店，关店时仍未完成的订单不扣钱。
- 糊菜：糊了 5 秒以内的按价格减 10 元收下；糊得更久会被拒收，订单继续等待。送出没有订单在等的菜扣 20 元。
- 删除 0.5.9 的旧规则：差评、出餐数目标、达标立即结束、剩余时间奖励。
- 第一关是练习关；第二、三关按参考双人组校准。

### 厨房与操作
- 胡闹厨房式键盘操作：空格和 E 对面前的东西操作，Q 冲刺。
- 盘子、菜、锅和灭火器可在 4 格内传递；食材可在 4 格内抛出。
- 盘子或食材放在地上时，也能像在柜台上一样组装。
- 厨师对所有工位使用同一身体尺寸：不再踩进柜台正面，走到哪里停下就在哪里操作。
- 行走时能滑过浅凹口；卡住的路线会绕开对方重新规划；“走向搭档”可以主动走到对方身边。

### Jeff（AI 队友）
- 使用清晰的英文输入，厨师称呼明确，重复选项更少。
- Jeff 看到的规则和引擎来自同一份冻结配置，不含任何“应该合作”的价值措辞。

### 记录与分析
- 每局记录为一条事件流，并生成可回放的对局包。
- 关店后显示本局记录：谁做了哪些活。
- 物品来历追踪、协作分析，以及按时间计算的贡献（投入时间与关键路径）。
- 容量分析器，以及校准阶梯（单人、单人加随机搭档、双人）。
- 三关的行为指纹，防止规则被无意改动。

### 画面与声音
- 厨房界面设计规范、像素字体、音乐与音效。
- 糊了的菜在任何位置都能认出来。

## 0.5.9-alpha — 2026-09-27

首个私有版本：本地浏览器游戏，三张可玩地图，玩家自带模型连接。
