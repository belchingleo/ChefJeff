# Level 4 — Across the counter

A row of counters runs from wall to wall across the middle of the kitchen and splits the floor in two. Above it are the four ingredient sources (beef, lettuce, tomato, bread), two stoves with a frying pan each, the serving window and a bin; below it are two boards, the sink, the dirty-plate return, the extinguisher rack and a second bin. One chef spawns on each side, sides set by the level's spawn seed, and nobody can walk round: food, plates, pans and tools cross by being put on the dividing counters, which both sides can reach, or thrown within 4 cells.

Every dish needs both chefs. Beef, lettuce and tomato are chopped on the lower side, beef is cooked and every plate is served on the upper side, and clean plates come out of the sink below. One chef alone serves nothing (`requires_pair: true`; `tests/test_level_four.py` checks this against the committed calibration report).

## Recipes and assembly

- Steak: chop beef for 2.2 seconds, cook for 10, and plate it.
- Burger: one bun, chopped lettuce, sliced tomato and cooked beef. Vegetables take 2.2 seconds to prepare and need no cooking; bread is ready to use.
- Assembly works as on Level 3: a plate with only cooked beef is a steak; once other burger ingredients are added, all four are required.

## Orders and target

Orders: two from the start, then one every 30 seconds and at once whenever fewer than two wait, at most five at a time, in a fixed sequence that starts steak, burger, burger, steak, burger, steak; an expired one starts again. Steaks have 60 seconds and burgers 90 (the pacing rule of player levels: five times each dish's chop and cook time). The round lasts 180 seconds. Prices are 50/80. The goal is at least 90 net revenue at closing: half the median of the scripted pair (a runner above and a maker below, Jeff deciding every 3 seconds) over order seeds 1–21, which ranged from 88 to 290; the solo script earned −80 to −40.

Order and spawn seeds are fixed per level version and recorded with the round.

---

## 中文说明

# 第四关：隔台协作

一排柜台从墙边连到墙边，横穿厨房中间，把地面隔成两块。上面是四个食材箱（牛肉、生菜、番茄、面包）、两个各放一口平底锅的灶台、出餐口和一个垃圾桶；下面是两块案板、水槽、脏盘回收、灭火器架和第二个垃圾桶。两名厨师一边一个出生，谁在哪边由本关的出生种子决定，谁也绕不过去：食物、盘子、锅和工具只能放到中间那排两边都够得着的柜台上，或者在 4 格内扔过去。

每道菜都要两个人。牛肉、生菜、番茄在下面切，牛肉在上面煎，每一盘都从上面出餐，干净盘子从下面的水槽出来。一个人单干一单也出不了（`requires_pair: true`；`tests/test_level_four.py` 拿已提交的校准报告核对这一点）。

## 菜谱与组装

- 牛排：牛肉切配 2.2 秒、烹饪 10 秒后装盘。
- 汉堡：面包、切好生菜、番茄片、熟牛肉各一份；蔬菜切配 2.2 秒但不煮，面包直接用。
- 组装规则同第三关：盘里只有熟牛肉就是牛排；加了别的汉堡配料后，四样都要齐。

## 订单与目标

订单开局就有两张，之后每 30 秒来一张，等待中的少于两张时立刻补，最多同时 5 张，顺序固定，开头是牛排、汉堡、汉堡、牛排、汉堡、牛排；超时后重新计时。牛排 60 秒、汉堡 90 秒内出餐（沿用玩家关卡的节奏规则：每道菜切和煮总时长的 5 倍）。每局 180 秒，单价 50／80。目标为关店时净收入至少 90 元：取脚本双人组合（上面一人跑菜、下面一人备料，Jeff 每 3 秒决定一次）在订单种子 1–21 上收入中位数的一半，这 21 局在 88 到 290 之间；单人脚本是 −80 到 −40。

订单与出生种子按关卡版本固定并随对局记录。
