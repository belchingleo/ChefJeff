# Level 3 — Steak and burgers

Two work areas connect through a one-cell passage. Ingredient sources, three boards and a sink occupy the left; two stoves, serving, dirty returns and plate counters are on the right. Chefs spawn near opposite area centers with randomized sides. Both use shared sliding/pushing contact, while walls and equipment remain solid.

Three pots and three clean plates are available: two pots start on stoves, the third on a counter. Pots may be moved, parked and swapped, preserving food and heating progress. Off-stove pots do not heat. Plates, pots and tools can be passed within 4 cells, to a partner or the floor.

## Recipes and assembly

- Steak: chop beef for 6 seconds, cook for 12, and plate it.
- Burger: one bun, chopped lettuce, sliced tomato and cooked beef. Vegetables take 6 seconds to prepare and need no cooking; bread is ready to use.
- Hold a clean/compatible plate to collect ingredients from boards/counters or beef from pots. Add ingredients to a partner's plate without taking their item. Duplicate ingredients and dirty plates are rejected.
- Merge compatible plates without destroying a plate. Burnt contents retain their state.
- Assembly order is free. A plate containing only cooked beef can be served as steak; once other burger ingredients are added, all four are required. Incomplete plates may be carried and placed, with missing-ingredient hints.
- Arrival and completion checks reject stale actions when contents change. Working chefs cannot be interrupted by contact or handoffs.

## Orders and movement

An order arrives every 30 game seconds until closing: steak, burger, burger, steak, burger, steak (the same sequence every round). Steaks have 75 seconds and burgers 105. The round always lasts 180 game seconds. Prices are 50/80. The goal is at least 190 net revenue at closing, with the global penalties. Orders are matched by recipe and earliest deadline; a dish served exactly at the deadline still counts.

Order and spawn seeds are fixed per level version and recorded with the round; the session record's inputs replay a complete game.

All levels allow sprint: double-tap a movement direction within 0.3 seconds, then hold. Sprint lasts 1 game second at 1.4× speed with 3 seconds of cooldown. AI adapters submit a sprint decision alongside the chosen action; only accepted, fresh moving actions may start it. Both chefs share movement/contact rules and paused game time freezes the effect.

Click-selected targets take priority for Space, with a reason when unavailable. Directional movement or clicking open floor returns to nearby targeting. Empty off-stove pots accept chopped beef; pick up and return the pot to heat it.

---

## 中文说明

# 第三关：牛排与汉堡

两个工作区通过一格宽通道连接。左侧为食材来源、三块案板及水槽，右侧为两台灶、出餐口、脏盘回收与餐盘柜台。两名厨师分别在两区中央附近出生，左右身份随机，双方采用共用滑动／推挤碰撞，墙与设备不可穿过。

本关三锅三净盘：两锅在灶上，一锅在柜台备用。锅可搬动、暂放或交换，内容与加热进度保留，离灶不加热。盘、锅、工具可在 4 格内传给队友或地面。

## 菜谱与组装

- 牛排：牛肉切配 6 秒、烹饪 12 秒后装盘。
- 汉堡：面包、切好生菜、番茄片、熟牛肉各一份；蔬菜切配 6 秒但不煮，面包直接用。
- 手持净盘／兼容盘收取案板／柜台配料或锅中牛肉；也可给队友盘加料但不夺取物品。拒绝重复配料与脏盘。
- 兼容两盘可合并但不销毁盘子，糊食物保留糊的状态。
- 添加顺序不限。仅装熟牛肉时可出牛排；加入其他汉堡配料后须四种齐全。缺料盘可搬动暂放，并显示缺料提示。
- 到达与完成时检查内容变化，拒绝过期动作；工作中的厨师不被接触或交接打断。

## 订单与移动

关店前每 30 游戏秒来一单，顺序固定为：牛排、汉堡、汉堡、牛排、汉堡、牛排。牛排 75 秒、汉堡 105 秒内出餐，每局固定 180 游戏秒。单价 50／80；目标为关店时净收入至少 190 元，罚款按全局规则。同菜品优先匹配最早到期订单，恰好在截止时刻出餐仍算成功。

订单与出生种子按关卡版本固定并随对局记录；对局记录中的输入可完整重放一局。

各关均可冲刺：0.3 秒内双击方向并按住，持续一游戏秒、速度 1.4 倍、随后冷却三秒。AI 随动作提交冲刺选择，仅新鲜、被接受且正在移动的动作可触发。双方共用移动／碰撞规则，暂停冻结冲刺时间。

空格优先点击选定目标，不可用时说明原因；方向移动或点击空地恢复就近目标。离灶空锅能装切好牛肉，拿起后放回灶台开始加热。
