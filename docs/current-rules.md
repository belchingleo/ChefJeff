# Gameplay rules

The Cocos browser game uses the shared rules in `kitchen.py`, `spatial_kitchen.py`, map JSON and level configuration. Both chefs follow the same timing, item and contact rules.

## Timing and movement

| Rule | Game-time value |
| --- | --- |
| Walk | 4.5 cells/second for both chefs |
| Sprint | Starts at 2× walking speed and eases back to walking over 1 second (Overcooked's dash); the next can start as soon as one ends |
| Pick/place/plate/serve | Usually 0.15 seconds plus travel |
| Chop / cook | 3 / 12 seconds (the knife strikes about 3.7 times a second) |
| Cooked → burnt → fire | 10 / 8 seconds while heating |
| Wash / customer plate return | 4 / 8 seconds |
| Extinguish / clear a pan or pot | 4 / 2 seconds |
| Discard food | −2; retain its plate, pan or pot |
| Dish no shown order is waiting for / expired order / new fire | −20 / −10 / −5 |
| Dish burnt ≤ 5 s / > 5 s when it left the heat | price −10 / refused, no money, order keeps waiting |

The default game clock runs at 0.75× real time. API latency and request limits use real time. Walk diagonals do not increase speed. Sprint accelerates movement, not preparation.

Hold WASD/arrows to move; release to stop. Experimental landscape touch controls also provide a left joystick: push to move, release to stop. Shift or the touch Dash button while moving triggers the same sprint; touch input does not change speed, duration or cooldown. Automatic movement uses the same chef-contact response as manual movement: slide around a partner when there is space, gently push under sustained pressure, and apply a bounded sprint nudge of at most a quarter cell. An AI route that makes no progress for 0.3 s re-plans from where contact left it, around the other chef (the same rule for both chefs), so two walkers cannot lock each other up. Walls and cabinets block movement: feet stop short of a cabinet's front panel and sides, and every cabinet is walked right up to from behind, so a chef works at any cabinet from the same line (boards are no longer a deeper exception). A held direction key that is fully blocked by an edge you could clear by stepping at most 0.3 cells sideways slides you out first, for example at the end of a counter run. In a passage too narrow for two chefs to pass, two chefs meeting head-on do not lock: the one with farther to go (Jeff on a tie, and always Jeff against the player's own walking) backs off to the nearest spot clear of the other's way, then goes on. Chefs chopping or washing cannot be pushed away. Either chef can also walk straight into the other on purpose ("go partner", the AI's counterpart of walking into Jeff): the walk ends on contact, which pushes, and a dash then gives the same bounded nudge. Ground food does not block walking or repel other food; sprint can nudge loose ingredients by at most a quarter cell.

## Actions and throwing

Controls follow Overcooked, with browser-safe keys: Space acts on what the chef aims at, as in Overcooked 2: of the stations in the eight cells around the chef's cell, the one most squarely ahead along the aim is the target (the aim can point any way, from the stick or the last diagonal step), the one nearer a point half a cell ahead when two are equally ahead, and only within 0.85 cells of the feet. Directions are compared by angle and the straight-ahead station keeps the target until the aim is about 30 degrees off it, so a stick that leans a little never picks a diagonal; aiming sideways, directions count from the cell the hands are over. A station beside or behind is never the target, and the player is never walked to a station: they turn and work where they stand. Chopping or washing started there first slides the chef sideways onto the station's centre line (at most 0.6 cells, about 0.1 s), never toward it. A loose item on the aimed tile or at the feet that lies nearer that point goes first; the item Space would take is ringed in denim. The page frames the target the moment the chef turns and sends it with the Space press; the engine uses it only if it can still be picked from the reported position and aim; otherwise it picks by the same rule itself. Space does what the target needs (fetch, take, put, cook, plate, lift a pan or pot, chop, wash, extinguish, serve, bin). With a throwable item in hand, releasing a short press executes that interaction; empty-handed actions start on press. Holding Space for about 0.3 s aims a throw, whether facing a station or open floor: the chef stops, a translucent curved guide shows the direction and range, the direction keys turn it (8 directions), and releasing throws — to the partner if they stand that way within range. Facing a station, a short press uses only that station, with a reason when nothing is possible; the held item is never dropped instead. Facing open floor, a short press takes the item in front, then the one at the feet, otherwise puts the held item down; a counter ahead that is still out of reach never makes it drop the item. Authored corner counters are used by facing their side. A direction pressed during a quick pick-up or put-down starts after it (about 0.15 s); for a held item, that action starts when the short Space press is released. Work is sticky, as in Overcooked: once chopping or washing starts no button stops it; walking away does, keeping progress. The direction still held when work starts or a throw is released does not walk until it returns to neutral or turns about 15 degrees, so a resting thumb cannot cancel the work. A second press within 0.5 s of a pick-up is ignored. Pickups can swap with raw/chopped ground ingredients; the old item stays on legal floor. Each logical floor tile or counter slot holds one resting item; small visual overlaps do not trigger automatic plating.

The touch Action button follows the same timing: empty-handed actions start on press; holding a throwable item, a short press acts on release and a hold of about 0.3 s aims. The left joystick changes the aim direction; release Action to throw, or drag into the cancel area and release to cancel. Two more buttons follow Overcooked 2's two-button split (keyboard and gamepad are unchanged): Grab only picks up or puts down, at once on press, even with a throwable item in hand, and never chops, washes or extinguishes; Throw, with a throwable item, aims while held and throws on release, and a quick tap throws along the stick or the facing.

The curved guide is a visual reference only: its endpoint marks maximum range, not a solved landing position. Input, range and item rules are unchanged; the engine still resolves walls and catches.

Movement works as in Overcooked online: the browser walks the player's chef itself, with the same walking rules, and reports where it is about ten times a second; the engine walks the chef there with its own physics (wall slides, contact with Jeff, sprint nudges). The engine accepts at most 1.25 times the walking speed (sprint included), banked up to 2 cells so a late report catches up at once. A report more than 2.5 cells away, a push by Jeff, or 0.25 s without progress resyncs: the browser then moves the chef to the engine's position. Space and throws carry the position the browser drew, so the engine targets from the same spot. Jeff's movement is unchanged.

Loose raw/chopped ingredients, plates, plated dishes, pans, pots and the extinguisher all fly up to 4 cells. Everything travels at 12 cells/game-second. Walls truncate the route; equipment can be crossed. A throw lands on the floor at the range limit. An empty-handed partner who is walking or standing catches it when it passes within 0.75 cells of them on its way, not only where it lands (a throw the player will catch is ringed); a partner chopping, washing or holding something is not interrupted and the item lands beside them. Dropped plates keep their food and dropped pans and pots their contents; both can be picked up again. The rules are identical for the player and the AI.

## Work and shared stations

Put raw ingredients on a board, chop with empty hands, then collect them. Bread is used directly. Chopping and washing keep their progress when the chef walks away. Multiple chefs may cooperate where separate reachable operation sides exist, sharing progress; the current maps have no shared-sink layout. Jeff's actions are whole, so he walks to a free side and stands at its centre, feet stopping at the walk limit (cabinet fronts are never entered); the player works from where they stand, after the short sideways slide onto the centre line. Two chefs sharing a board must work from perpendicular sides, judged from where each actually stands. Contact cannot interrupt active chopping/washing, but a fire can make the workstation unusable.

Each ingredient cooks in one kind of vessel, set by the recipe data: beef fries in a frying pan, noodles boil in a soup pot (left too long, the water boils dry, then they burn and catch fire). A stove holds one vessel at a time. The three current levels use frying pans only. A pan or pot heats only on a stove. Carrying it or placing it on a counter/floor pauses heat progress; returning resumes it, including the countdown to burning. Chopped beef may be put into an empty pan off the stove. Raw beef must be chopped first; vegetables and bread do not go in pans. Swaps retain each vessel's contents and progress. Burning pans and pots must be extinguished before moving/clearing.

## Assembly and service

Cooked beef moves with a pan or plate, never as a bare-handed loose item. Clean or compatible partial plates can collect prepared ingredients from boards/counters and cooked beef from pans. On levels with burgers the same works on the floor: add a held ingredient to a plate lying on the floor (the plate stays on its tile), or a floor ingredient to the held plate; picking up still swaps instead. Prepared ingredients, cooked pan contents and compatible plated components may be added to a partner's plate without stealing their item or interrupting work. Merging two plates transfers food, leaving the source plate empty. Duplicate ingredients and dirty plates are rejected.

Steak requires plated cooked beef. A burger requires one bun, chopped lettuce, sliced tomato and cooked beef, assembled in any order. Visual layer order is fixed regardless of assembly order; missing layers remain hidden. Partial burgers can be carried and placed but not served; hints identify missing ingredients. A served dish goes to the waiting order of that dish with the earliest deadline; serving exactly at the deadline counts. Steak pays 50 and a burger 80. If any component was burnt, what counts is how long it had been burnt when it left the heat: up to 5 seconds, the order is completed at the price −10; longer (or burnt by a fire), the customer refuses it, pays nothing and keeps waiting. Serving a dish that no shown order is waiting for costs 20. There are no bad reviews. Customer plates return after a delay; move dirty plates to a sink, wash with empty hands, and collect clean plates.

Take the extinguisher to a burning station, then dispose of burnt contents. Fire spreads every 8 game seconds to one adjacent flammable station, never across floor/walls. Five simultaneously burning stations end the round. A bin removes food while preserving its container.

## Session controls, communication and models

Esc, P or Ⅱ pauses (Esc or P also resumes); ▶ resumes; ■ ends early without a success bonus. Settings and input fields suppress game shortcuts. Hidden/disconnected pages pause. With the small-screen touch layout active, devices must be in landscape to start or resume; turning to portrait clears input, cancels pending actions/throws and pauses a running round. Returning to landscape does not resume automatically. Browsers need not support orientation lock. The local page reconnects to its existing kitchen after refresh; the hosted pilot creates a new per-page kitchen. Restart from pause/results; select a level from ready/results.

Enter or the touch Bookmark button bookmarks the current round without affecting play or model input. Presses within 5 real seconds merge into an interval. Number keys 1–5 send a fixed cooperation preference; 6 reports a perceived mistake. The touch Communication button opens the same preset messages, collapsed by default. Messages share a 5-second cooldown and are delivered with the next normal request, without forcing a task interruption. The latest preference lasts for the round. Feedback includes bookmarks and preset messages.

Models receive English structured observations (`en-v3`, plain ASCII; the chefs are named `human` and `jeff`), factual rules (`rules-v4`) and legal actions. The rules describe what the kitchen allows; they do not instruct the agent to cooperate with or help the human. UI language does not change model input. Requests distinguish selection, acceptance and completion; stale replies are rejected, and failures remain visible. The default budget is 200 requests/round (configurable 1–2000); failures count and in-flight requests can still complete. At the limit, current actions continue and the player may pause. See [agent integration](agent-integration.md) and [privacy/costs](privacy-and-costs.md).

## Levels

Every level lasts 180 game seconds (about 4 minutes at the default 0.75 clock). [Level 1](level-1-steak.md) serves steak, [Level 2](level-2-burger.md) burgers and [Level 3](level-3-steak-burger.md) both. Orders arrive one at a time at a fixed interval until closing; several can wait at once (at most five tickets). Each dish has its own countdown; an expired order costs 10 and disappears. The goal is a net revenue target at closing: the round always runs to the end, penalties after reaching the target count, and orders still open at closing carry no penalty. There is no remaining-time bonus. Targets: Level 1 ¥150, Level 2 ¥150, Level 3 ¥190. The target is half of the median net income of the scripted reference pair over 21 runs (order seeds 1–21, the better of the classic and zoned pairings on each), rounded down to ¥10 (`docs/architecture/reports/calibration.json`); Level 3 stays at ¥190, above its calibrated ¥160, by owner decision (2026-10-06). One chef can reach the target on Level 1 (practice) and, for now, Level 3; two are faster. On Level 2 the scripted solo chef falls short. Orders and spawn sides are fixed per level version, so every round of a level is the same.

---

## 中文说明

# 玩法规则

Cocos 浏览器版共用 `kitchen.py`、`spatial_kitchen.py`、地图 JSON 和关卡配置中的规则。两位厨师遵循相同的时间、物品与碰撞规则。

## 时间与移动

| 规则 | 游戏时间参数 |
| --- | --- |
| 行走 | 双方均为 4.5 格／秒 |
| 冲刺 | 起步 2 倍行走速度，1 秒内平滑回落到正常速度（《胡闹厨房》的冲刺）；结束后可立即再冲 |
| 取放／装盘／出餐 | 通常 0.15 秒，另加路程 |
| 切配／烹饪 | 3／12 秒（每秒约挥刀 3.7 下） |
| 熟到糊／糊到火 | 持续加热时 10／8 秒 |
| 洗碗／顾客归还盘子 | 4／8 秒 |
| 灭火／清锅 | 4／2 秒 |
| 丢弃食物 | −2，保留盘或锅 |
| 端了没有订单在等的菜／订单超时／新起火 | −20／−10／−5 |
| 离火时糊 ≤5 秒／>5 秒 | 菜价 −10／拒收，无收入，订单继续等待 |

默认游戏时钟为现实时间的 0.75 倍，API 延迟及请求限制按现实时间计算。斜走不加速，冲刺仅加速移动。

按住 WASD／方向键移动，松开停止；试验版横屏触控也可推动左摇杆移动、松手停止。移动时按 Shift 或触屏「冲刺」按钮，均沿用相同冲刺速度、时长和冷却。自动与手动移动共用厨师接触处理：有空间时沿搭档边缘滑过，持续前进时温和推挤，冲刺产生最多四分之一格的有限位移。AI 路线若 0.3 秒无进展，会从当前位置绕开对方重新规划（双方同一规则），两位自动行走的厨师不会互相卡死。墙与柜体不可穿过：脚步停在柜门面板和柜体两侧之外，柜台背面则都可以走到贴边，所以站在哪个柜台前操作都在同一条线上（案板不再是更深的特例）；按住方向键被挡住时，如果往侧边挪不超过 0.3 格就能绕开（比如一排柜台的尽头），会先自动滑出再继续走；在窄到两人无法错身的通道里迎面相遇时不会僵持：剩余路程更长的一方（相同时由 Jeff 让，玩家自己走时总是 Jeff 让）退到最近一个不挡对方的位置，等对方过去再走；正在切菜或洗碗的厨师不可被推离。双方也都可以有意走向并撞上对方（“走到对方厨师当前的位置”，即 AI 版的“走过去撞 Jeff”）：接触即结束行走并产生推挤，冲刺时同样有上述有限位移。地面食物不挡走路，食物之间不相互弹开；冲刺可将散落原料推移最多四分之一格。

## 操作与抛掷

操作方式参照《胡闹厨房》，按键改为浏览器里不冲突的键：空格对角色瞄着的东西起作用，与《胡闹厨房 2》相同：在角色所在格周围 8 格的工位里，以最正对瞄准方向的为目标（瞄准可以是任意方向，来自摇杆或最后一次斜向移动）；同样正对时选离前方半格处更近的，且离脚下不超过 0.85 格。方向按夹角比较，正前方的工位在瞄准偏离约 30° 之前一直保持为目标，摇杆稍微偏一点不会选到斜对角；朝左右瞄准时，按手所在的那一格计算方向。身边和身后的工位不会成为目标；玩家也不会被带着走到工位前，原地转身操作；在原地开始切菜或洗碗时，先沿柜台方向侧移到工位正中（最多 0.6 格，约 0.1 秒），不会向前挪。瞄准的那格或脚下有更靠近前方那点的散落物品时，先操作物品，空格要拿的物品会用蓝圈标出。角色一转身，页面立即框出目标，按空格时一并发给引擎；引擎核对从报告的位置和朝向仍能选中它才采用，否则按同一规则自己选。空格做目标需要的事（取料、拿起、放下、下锅、装盘、端锅、切菜、洗碗、灭火、出餐、丢弃）。手持可投掷物品时，短按松开后执行目标交互；空手时按下立即操作。面前是工位或空地都能按住空格约 0.3 秒进入瞄准：角色停下，半透明弧形轨迹显示方向与射程参考，方向键改方向（8 个方向），松开扔出，队友在这个方向的射程内时扔给他。面前是工位时，短按只操作这个工位，做不了会说明原因，不会改成把东西放到地上；面前是空地时，短按先拿面前地上的，再拿脚下的，否则把手里的放下；面前的工位够不着时，也不会改成把东西放到地上。角落柜台面向它所在的一侧即可操作。拿、放这类短动作（约 0.15 秒）进行中按方向键，会在动作完成后再走；持物时，这个动作从短按空格松开后开始。切菜和洗碗与《胡闹厨房》一样一旦开始就一直做：任何按键都不会中断，走开才停，进度保留。开始工作或扔出东西时仍按着的方向，要先回到中间或转过约 15° 才会移动，所以拇指搭在摇杆上不会打断工作。拿起东西后 0.5 秒内再按会被忽略。可与地面生／切好原料换手，旧物品留在合法地面。每个逻辑地面格或柜台槽容纳一件静置物品；小范围视觉重叠不会自动装盘。

触屏「操作」按钮沿用相同时序：空手按下立即交互，手持可投掷物品时短按松开执行交互、长按约 0.3 秒瞄准。左摇杆调整瞄准方向，松开操作按钮投掷，拖入取消区后松开则取消。另有两个按钮，按《胡闹厨房 2》的双键分工（键盘和手柄不变）：「拿放」只拿起或放下，按下立即执行，手持可投掷物品时也一样，不会切菜、洗碗或灭火；「扔」在手持可投掷物品时按住瞄准、松开扔出，快速点按则沿摇杆方向或朝向直接扔出。

弧形轨迹仅作视觉参考，终点表示最大射程，不是已经求解的实际落点。输入、射程和物品规则不变，墙体阻挡和队友接取仍由引擎判定。

移动方式与《胡闹厨房》联机一样：浏览器按同样的走路规则自己移动玩家的厨师，每秒约 10 次报告位置；引擎用自己的物理（贴墙滑动、与 Jeff 的接触、冲刺推开食物）走到那里。引擎最多接受 1.25 倍走路速度（含冲刺），可累积 2 格，晚到的报告能立刻追上。报告超出 2.5 格、被 Jeff 推开、或 0.25 秒没有进展时重新同步：浏览器把厨师移到引擎的位置。空格和投掷会带上浏览器画出的位置，引擎从同一处判断目标。Jeff 的移动不变。

散放的生／切好原料、餐盘、装盘菜、锅和灭火器都可以抛，最远 4 格。速度均为 12 格／游戏秒。墙截断路线，可越过设备，东西落在射程尽头的地上。空手且在走路或站着的队友，东西飞行途中经过他 0.75 格以内即可接住，不只看落点（玩家能接住的会用蓝圈标出）；正在切菜、洗碗或手里有东西时不打断，东西落在他旁边。掉在地上的盘子保留菜、锅保留内容，都能再捡起。玩家与 AI 规则相同。

## 加工与合作工位

把生原料放在案板，空手切配后取走；面包直接使用。走开时切菜或洗碗的进度保留。有分别可达的操作侧时，多位厨师可共用工位推进加工；当前地图没有双人水槽。Jeff 的动作是整段的，会走到空闲操作侧的正中，脚停在行走极限处（不会走进柜门）；玩家在自己站的位置操作，只会先侧移到正中。两人共用案板时要在相互垂直的两侧，按各自实际站的位置判断。碰撞不打断切菜／洗碗，着火会使工位不可用。

每种食材只进一种锅，由菜谱数据决定：牛肉用平底锅煎，面条用汤锅煮（煮太久水烧干会糊，再久会着火）。一个灶台同时只放一口锅。目前三关只用平底锅。锅仅在灶台上加热，端走或放在柜台／地面时暂停，放回后继续，包括烧糊倒计时。离灶空锅可先装切好牛肉；生牛肉须先切，蔬菜和面包不入锅。交换锅保留各自内容与进度，着火锅须先灭火再搬动／清理。

## 组装与出餐

熟牛肉随锅或盘移动，不可裸手散拿。净盘或兼容半成品盘可从案板／柜台收配料，从锅收熟牛肉。有汉堡的关卡在地面上也一样：手里的配料可以加进地上的盘（盘留在原格），地上的配料也可以加进手中的盘；“捡起”仍是换手。准备好的配料、锅中熟食或兼容盘中食物可加入队友手持盘，不夺取物品、不打断工作。两盘合并只转移食物，源盘留空。重复配料和脏盘会被拒绝。

牛排需要装盘熟牛肉；汉堡需要各一份面包、切好生菜、番茄片和熟牛肉，添加顺序不限。显示层级固定，未添加层不显示。缺料汉堡可搬动暂放、不可出餐，提示会说明缺料。出餐交给同菜品中截止最早的等待订单，恰好在截止时刻送达也算成功。牛排 50 元、汉堡 80 元。菜中任一原料糊了时，按它离火时已糊的时长计：5 秒以内订单完成、收入为菜价 −10；超过 5 秒（或被火烧糊）顾客拒收、不付钱，订单继续等待。端出当前没有订单在等的菜扣 20。没有差评。顾客用完餐后延迟归还盘子，脏盘送水槽、空手清洗后取净盘。

拿灭火器扑灭着火工位，再处理糊食物。每 8 游戏秒向一个相邻可燃工位蔓延，不跨地面或墙；同时五处起火结束本局。垃圾桶只销毁食物，保留容器。

## 对局、沟通与模型

Esc、P 或 Ⅱ 暂停（Esc 或 P 也可继续），▶ 继续，■ 提前结束且无成功奖励。设置及输入框禁用游戏快捷键，页面隐藏／失联会暂停。小尺寸触屏布局启用时，需横屏才能开局或继续；转竖屏会清理输入、取消待执行交互／投掷并暂停正在运行的对局，恢复横屏后不自动继续，网页不要求浏览器支持横屏锁定。本地版刷新后连接原厨房，托管版刷新产生新的页面会话。暂停／结算时重开，准备／结算时选关。

Enter 或触屏「标记」按钮标记本局片段，不影响玩法或模型输入；间隔五个现实秒内的按键合并为区间。数字 1–5 发送固定协作偏好，6 表示玩家认为出错；触屏「沟通」入口展开相同预设消息，默认折叠；共用五秒冷却，下一次正常请求送达，不强行打断任务。最新偏好持续本局，反馈包含标记与预设消息。

模型收到英文结构化观察（`en-v3`，纯 ASCII；两位厨师分别称为 `human` 和 `jeff`）、事实规则（`rules-v4`）与合法动作；规则只说明厨房允许什么，不要求 agent 协作或帮助玩家。界面语言不改变模型输入。请求区分选择、接受与完成，拒绝过期回复并显示失败。默认每局 200 次（可设 1–2000），失败计数，在途请求仍可完成。达到上限后已有动作继续，玩家可暂停。详见 [agent 接入](agent-integration.md)与[隐私／费用](privacy-and-costs.md)。

## 关卡

每关 180 游戏秒（默认 0.75 时钟约 4 分钟）。[第一关](level-1-steak.md)做牛排，[第二关](level-2-burger.md)做汉堡，[第三关](level-3-steak-burger.md)两者都有。订单按固定间隔逐张到来直至关店，可同时等待多张（最多 5 张）。每道菜有各自的倒计时，超时扣 10 元并消失。目标是关店时的净收入：本局总是打满全场，达标后的罚款照样计入，关店时未完成的订单不罚款。剩余时间不折算奖励。目标金额：第一关 ¥150、第二关 ¥150、第三关 ¥190。目标取脚本参考组合在 21 局（订单种子 1–21，每局取 classic 与 zoned 两种配合中较好的一种）净收入中位数的一半，向下取整到 10 元（`docs/architecture/reports/calibration.json`）；第三关按负责人决定（2026-10-06）保持 ¥190，高于校准值 ¥160。第一关（练手关）和第三关暂时一个人也能达标，两个人更快；第二关单人脚本达不到。订单与出生位置按关卡版本固定，同一关每局相同。
