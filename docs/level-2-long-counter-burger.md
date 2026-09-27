# Level 2 — Burger kitchen

A 14×9 kitchen with a horizontal counter dividing upper and lower work areas, joined by a two-cell passage on the right. Ingredient sources and one stove are above; two boards and two plates below. The right wall holds a sink and bin; serving/dirty returns are at the lower left, with an extinguisher on the middle counter. Chefs spawn near each area's center with randomized assignments.

One pot starts on the stove; two plates rest on counters. Each counter slot holds one item. Off-stove pots do not heat. Shared pickup, throwing, catching, plating, merging, carrying, washing, collision and sprint rules apply. A pot swap needs another pot; this level supplies only one.

## Orders

Three burgers arrive at 0/30/60 game seconds, each with 180 seconds of patience. The round lasts up to 240 game seconds, about 5 minutes 20 seconds at the default 0.75× clock. Each burger earns 60. Finish three orders with at least 120 operating income and no more than two bad reviews to complete the level. Two plates require at least one wash cycle.

Each burger needs a bun, chopped lettuce, sliced tomato and cooked chopped beef, assembled in any order on a clean plate. Bread needs no chopping, vegetables no heat, and raw beef cannot be plated. Global preparation, burning and penalty rules apply.

## Delivery and observations

Either chef can fetch and throw ingredients to a partner or empty board, then fetch again once the hand is free. Occupied/reserved boards cannot be overwritten; plates and pots cannot be thrown. The agent chooses its own delivery and preparation actions.

Observations include active orders, ingredient states, held items, occupied workstations and flying ingredients. Future orders expose a count, not their full contents. Planning currently uses these observations without a precomputed ingredient-shortfall summary. Timing and order pressure remain playtesting parameters.

---

## 中文说明

# 第二关：汉堡

适用当前三关版本。开局前或结算后选择第二关。原窄巷地图移到第三关。

## 布局与资源

14×9 单间厨房，连续外围柜台和从左侧伸出的横向长柜台形成上下工作区，右侧两格通道连接。上边四处食材来源和一台灶台；下边两块案板和两只餐盘；右墙水槽、垃圾桶；左下出餐口、脏盘回收；中间柜台有灭火器。所有设备有可达操作面。两名厨师分别在上下工作区中央附近出生，身份随机分配。

只有一口锅，开局在唯一灶台上；两只餐盘分别放在柜台。柜台视觉连续，每格仍只容纳一个物品。锅离灶不加热。双方共用全部取放、抛食材、接物、装盘、合盘、端锅、换锅、洗碗和冲刺规则；本关只有一口锅，因此不会凭空出现换锅目标。

## 订单

共 3 份汉堡，0 / 30 / 60 游戏秒到单，每单耐心 180 秒，总时长 240 游戏秒。默认 0.75 倍游戏时钟，未提前结束时约 5 分 20 秒现实时间。每份 60 元；目标为出餐 3 单、净收入至少 120 元、差评不超过 2 次，达成即结算。三单菜品相同，随机排序不会产生菜品差别。资源只有两只盘，完成三单必须至少回收洗净一只。

汉堡为一份面包、切好生菜、切好番茄及切配后煎熟的牛肉，任意顺序装入干净盘。面包不用切，蔬菜不烹饪，生牛肉不能装盘。加工、糊锅、处罚和餐具循环沿用全局规则。

## 连续送料与模型边界

AI 与玩家均可取料后抛给队友或空案板，再取下一份继续抛或自己加工。出手后即腾出手，不必等上一次落地；占用或已预约的案板不会被覆盖，餐盘和锅不能抛。该动作链不等于自动分工；模型自己选择送料次数和后续工作。

已出现订单、食材状态、手持物、工位占用、飞行中物品均提供给模型。未出现订单只给数量。暂不提供预计算的缺料量，不添加自动批量送料策略。未来评测应区分模型自行规划与系统提供需求汇总的辅助条件。

时长与订单压力将随社区试玩继续打磨。
