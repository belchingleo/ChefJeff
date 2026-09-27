# Gameplay rules

The Cocos browser game uses the shared rules in `kitchen.py`, `spatial_kitchen.py`, map JSON and level configuration. Both chefs follow the same timing, item and contact rules.

## Timing and movement

| Rule | Game-time value |
| --- | --- |
| Walk | 4.5 cells/second for both chefs |
| Sprint | 1.4× walking speed for 1 second, then 3-second cooldown |
| Pick/place/plate/serve | Usually 0.15 seconds plus travel |
| Chop / cook | 6 / 12 seconds |
| Cooked → burnt → fire | 10 / 8 seconds while heating |
| Wash / customer plate return | 4 / 8 seconds |
| Extinguish / clear pot | 4 / 2 seconds |
| Discard food | −2; retain its plate or pot |
| Wrong order / expired order / new fire | −15 / −10 / −5 |

The default game clock runs at 0.75× real time. API latency and request limits use real time. Walk diagonals do not increase speed. Sprint accelerates movement, not preparation.

Hold WASD/arrows to move; release to stop. Click floor to approach a point, or a station/item to select it and approach its operation side. Keyboard input takes over from click movement. Automatic movement uses the same chef-contact response as manual movement: slide around a partner when there is space, gently push under sustained pressure, and apply a bounded sprint nudge of at most a quarter cell. A click or AI route that makes no progress for 0.3 s re-plans from where contact left it, around the other chef (the same rule for both chefs), so two walkers cannot lock each other up. Walls and cabinets block movement. Chefs chopping or washing cannot be pushed away. Ground food does not block walking or repel other food; sprint can nudge loose ingredients by at most a quarter cell.

## Actions and throwing

Tap Space for the selected target, or the nearby facing target when none is explicitly selected. An unavailable selected target shows a reason instead of switching to a bin. Empty hands can pick up eligible food at the chef's feet; carried items favor the facing station. With no usable station, drop or pick up nearby. Pickups can swap with raw/chopped ground ingredients; the old item stays on legal floor. Each logical floor tile or counter slot holds one resting item; small visual overlaps do not trigger automatic plating.

Hold Space for about 0.3 seconds and left-click to throw; release cancels. Alternatively right-click to prepare/cancel, then left-click the target. Only loose raw/chopped ingredients can be thrown, up to 7 cells at 12 cells/game-second. Walls truncate the route; equipment can be crossed. Empty boards accept ingredients. An empty-handed idle partner can catch; busy/full-handed partners are not interrupted. Plates, pots, plated dishes and tools cannot be thrown.

## Work and shared stations

Put raw ingredients on a board, chop with empty hands, then collect them. Bread is used directly. Chopping and washing preserve progress when voluntarily interrupted. Multiple chefs may cooperate where separate reachable operation sides exist, sharing progress; the current maps have no shared-sink layout. Each chef approaches a valid side without changing walls or footprints. Contact cannot interrupt active chopping/washing, but a fire can make the workstation unusable.

A pot heats only on a stove. Carrying it or placing it on a counter/floor pauses heat progress; returning resumes it, including the countdown to burning. Chopped beef may be put into an empty pot off the stove. Raw beef must be chopped first; vegetables and bread do not go in pots. Pot swaps retain each pot's contents and progress. Burning pots must be extinguished before moving/clearing.

## Assembly and service

Cooked beef moves with a pot or plate, never as a bare-handed loose item. Clean or compatible partial plates can collect prepared ingredients from boards/counters and cooked beef from pots. Prepared ingredients, cooked pot contents and compatible plated components may be added to a partner's plate without stealing their item or interrupting work. Merging two plates transfers food, leaving the source plate empty. Duplicate ingredients and dirty plates are rejected.

Steak requires plated cooked beef. A burger requires one bun, chopped lettuce, sliced tomato and cooked beef, assembled in any order. Visual layer order is fixed regardless of assembly order; missing layers remain hidden. Partial burgers can be carried and placed but not served; hints identify missing ingredients. Burnt or incorrect dishes incur penalties. Service matches the earliest-expiring valid order for that recipe. Customer plates return after a delay; move dirty plates to a sink, wash with empty hands, and collect clean plates.

Take the extinguisher to a burning station, then dispose of burnt contents. Fire spreads every 8 game seconds to one adjacent flammable station, never across floor/walls. Five simultaneously burning stations end the round. A bin removes food while preserving its container.

## Session controls, communication and models

Esc or Ⅱ pauses; ▶ resumes; ■ ends early without a success bonus. Settings and input fields suppress game shortcuts. Hidden/disconnected pages pause. The local page reconnects to its existing kitchen after refresh; the hosted pilot creates a new per-page kitchen. Restart from pause/results; select a level from ready/results.

Shift bookmarks the current round without affecting play or model input. Presses within 5 real seconds merge into an interval. Number keys 1–5 send a fixed cooperation preference; 6 reports a perceived mistake. Messages share a 5-second cooldown and are delivered with the next normal request, without forcing a task interruption. The latest preference lasts for the round. Feedback includes bookmarks and preset messages.

Models receive English structured observations (`en-v1`) and legal actions. UI language does not change model input. Requests distinguish selection, acceptance and completion; stale replies are rejected, and failures remain visible. The default budget is 200 requests/round (configurable 1–2000); failures count and in-flight requests can still complete. At the limit, current actions continue and the player may pause. See [agent integration](agent-integration.md) and [privacy/costs](privacy-and-costs.md).

## Levels

Level 1 is a steak practice kitchen (180 game seconds). [Level 2](第二关-长台汉堡.md) serves three burgers in 240 seconds; [Level 3](第三关-窄巷汉堡.md) mixes five steak/burger orders in 360 seconds. Successful completion adds one unit of bonus per remaining whole game second, separately from the operating-income target.

---

## 中文说明

# 玩法规则

Cocos 浏览器版共用 `kitchen.py`、`spatial_kitchen.py`、地图 JSON 和关卡配置中的规则。两位厨师遵循相同的时间、物品与碰撞规则。

## 时间与移动

| 规则 | 游戏时间参数 |
| --- | --- |
| 行走 | 双方均为 4.5 格／秒 |
| 冲刺 | 行走速度 1.4 倍，持续 1 秒，随后冷却 3 秒 |
| 取放／装盘／出餐 | 通常 0.15 秒，另加路程 |
| 切配／烹饪 | 6／12 秒 |
| 熟到糊／糊到火 | 持续加热时 10／8 秒 |
| 洗碗／顾客归还盘子 | 4／8 秒 |
| 灭火／清锅 | 4／2 秒 |
| 丢弃食物 | −2，保留盘或锅 |
| 错餐／订单超时／新起火 | −15／−10／−5 |

默认游戏时钟为现实时间的 0.75 倍，API 延迟及请求限制按现实时间计算。斜走不加速，冲刺仅加速移动。

按住 WASD／方向键移动，松开停止。点击地面走近坐标，点击工位／物品选中并走向操作侧；键盘可以接管点击移动。自动与手动移动共用厨师接触处理：有空间时沿搭档边缘滑过，持续前进时温和推挤，冲刺产生最多四分之一格的有限位移。点击或 AI 路线若 0.3 秒无进展，会从当前位置绕开对方重新规划（双方同一规则），两位自动行走的厨师不会互相卡死。墙与柜体不可穿过，正在切菜或洗碗的厨师不可被推离。地面食物不挡走路，食物之间不相互弹开；冲刺可将散落原料推移最多四分之一格。

## 操作与抛掷

短按空格操作选中目标，未明确选择时操作附近朝向目标。选中目标不可用会说明原因，不转向垃圾桶。空手可捡脚下符合条件的物品，持物时优先面前工位；无可用工位时就近放下或拾取。可与地面生／切好原料换手，旧物品留在合法地面。每个逻辑地面格或柜台槽容纳一件静置物品；小范围视觉重叠不会自动装盘。

按住空格约 0.3 秒后左键抛出，松开取消；也可右键准备／取消、左键选择落点。仅散放的生／切好原料可抛，最远 7 格、速度 12 格／游戏秒。墙截断路线，可越过设备，空案板能接收。空手且未工作的队友可接住，忙碌或满手时不打断操作。盘、锅、装盘菜及工具不能抛。

## 加工与合作工位

把生原料放在案板，空手切配后取走；面包直接使用。主动中断切菜或洗碗保留进度。有分别可达的操作侧时，多位厨师可共用工位推进加工；当前地图没有双人水槽。厨师走向合法操作侧，不改变墙和占格。碰撞不打断切菜／洗碗，着火会使工位不可用。

锅仅在灶台上加热，端走或放在柜台／地面时暂停，放回后继续，包括烧糊倒计时。离灶空锅可先装切好牛肉；生牛肉须先切，蔬菜和面包不入锅。交换锅保留各自内容与进度，着火锅须先灭火再搬动／清理。

## 组装与出餐

熟牛肉随锅或盘移动，不可裸手散拿。净盘或兼容半成品盘可从案板／柜台收配料，从锅收熟牛肉。准备好的配料、锅中熟食或兼容盘中食物可加入队友手持盘，不夺取物品、不打断工作。两盘合并只转移食物，源盘留空。重复配料和脏盘会被拒绝。

牛排需要装盘熟牛肉；汉堡需要各一份面包、切好生菜、番茄片和熟牛肉，添加顺序不限。显示层级固定，未添加层不显示。缺料汉堡可搬动暂放、不可出餐，提示会说明缺料。糊菜或错餐受罚；同菜品匹配最早到期的有效订单。顾客用完餐后延迟归还盘子，脏盘送水槽、空手清洗后取净盘。

拿灭火器扑灭着火工位，再处理糊食物。每 8 游戏秒向一个相邻可燃工位蔓延，不跨地面或墙；同时五处起火结束本局。垃圾桶只销毁食物，保留容器。

## 对局、沟通与模型

Esc 或 Ⅱ 暂停，▶ 继续，■ 提前结束且无成功奖励。设置及输入框禁用游戏快捷键，页面隐藏／失联会暂停。本地版刷新后连接原厨房，托管版刷新产生新的页面会话。暂停／结算时重开，准备／结算时选关。

Shift 标记本局片段，不影响玩法或模型输入；间隔五个现实秒内的按键合并为区间。数字 1–5 发送固定协作偏好，6 表示玩家认为出错；共用五秒冷却，下一次正常请求送达，不强行打断任务。最新偏好持续本局，反馈包含标记与预设消息。

模型收到英文结构化观察（`en-v1`）与合法动作，界面语言不改变模型输入。请求区分选择、接受与完成，拒绝过期回复并显示失败。默认每局 200 次（可设 1–2000），失败计数，在途请求仍可完成。达到上限后已有动作继续，玩家可暂停。详见 [agent 接入](agent-integration.md)与[隐私／费用](privacy-and-costs.md)。

## 关卡

第一关为 180 游戏秒的牛排练习厨房；[第二关](第二关-长台汉堡.md)在 240 秒内完成三份汉堡；[第三关](第三关-窄巷汉堡.md)在 360 秒内完成五份牛排／汉堡订单。成功时按剩余整游戏秒发放奖励，与营业收入目标分开计算。
