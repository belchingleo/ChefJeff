# 当前主网页版规则

第一关规则适用 ChefJeff 0.5.0-alpha，固定入口 8775；权威规则来自 kitchen.py、spatial_kitchen.py、config.json。旧文字版抽象移动不适用于本页。

## 当前练习关

14×9 固定厨房，三块案板、一口可搬锅、十个单格柜台、两只餐盘、一个右下垃圾桶、唯一出餐口、回收点和水槽。布局 practice-3：上半部隔墙、下半部通道；水槽在右上方灶台左侧，回收点在右下方。双方各占一个房间，出生在中央最近的合法空地，左右房间每局随机分配。只做牛排；自动接单，匹配最早到期有效订单。每人手持一件，拿取时可自动换手，旧物品留地上；没有空位则失败，不覆盖物品。

| 规则 | 游戏时间/金额 |
| --- | --- |
| 移动 | 3 格/秒，按可通行最短折线绕墙/设备；角色间可穿过 |
| 取放、装盘、出餐 | 通常 0.15 秒，另加实际路程 |
| 切配 / 烹饪 | 6 秒 / 12 秒；切配可中断保留进度 |
| 熟到糊 / 糊到火 | 10 秒 / 8 秒；起火后每 8 秒向一个相邻可燃工位蔓延 |
| 洗碗 / 顾客归还 | 4 秒 / 8 秒；洗碗可中断续洗；回收点容量 1，满则排队 |
| 灭火 / 清锅 | 4 秒 / 2 秒；先拿灭火器；清锅损耗 2 元 |
| 正确出餐 / 错餐 | +30 / −15 元；错餐差评一次 |
| 订单超时 / 着火 | −10 / −5 元；超时差评一次 |
| 丢弃菜品 | −2 元；盘锅不会被销毁 |
| 关卡 | 最长 180 秒；5 单、间隔24秒、耐心90秒 |
| 通关 | 出餐至少3单、营业净收入至少60元、差评不超过2；达成立即结束 |
| 剩余时间奖励 | 成功时每剩余整秒 +1 元，独立于营业收入目标 |

当前网页开始按钮采用 0.75 倍游戏速度，API 等待与调用间隔按现实时间计。此模式不是拟议的一倍速实时 benchmark。

## 移动和交接

WASD/方向键按住移动、松开停止，斜走不加速。鼠标点空地寻路，点工位走近，空格执行操作；自动走到最近可达操作侧；键盘与鼠标可互相接管任务。输入框中不触发快捷键。

短按空格松开时：点击选定的工位或地上物品优先；高亮、提示和执行共用同一个目标。选中目标不可用时说明原因，不转向垃圾桶、柜台或自动放下。按方向键移动或点击空地清除选定目标；没有明确点击目标时，空手优先拾取自己所在格的可拾取物品；脚下无可拾取物品或手中已有物品时，锁定角色面前一格，优先可用的装盘、放入、加工等动作；案板上生食材空手可切，水槽脏盘空手可洗，垃圾桶旁会丢弃手中食物。正在工作时按空格停止，进度保留。没有可用工位时，满手放在脚边，空手就近捡起。手中有物品时，短按空格也可与目标地面上的生食材或切好食材换手，旧物品留在附近合法地面，不销毁、不扣钱。面前有工位时不自动抢选脚下食材；要交换脚下食材，先点击选中它。装盘、入锅等已有合并动作仍优先于换手。底部显示本次操作提示。长按至少约 0.3 秒进入抛掷准备，保持按住并左键点落点；松开取消。右键也是准备/取消入口，左键选择落点。Esc 始终暂停，不用来取消抛掷。

抛掷最大7格，速度12格/游戏秒，出手约0.15秒。超距沿方向截短，遇墙落墙前可用地面，可越过设备。无合法落点不出手。生/切好食材可抛到空案板；盘、锅、工具不能放案板。仅未装盘的生食材、切好食材可抛；干净盘、脏盘、已装盘菜、锅和灭火器均不可抛。上述物品都可以放下再拾取，熟菜只能连锅或连盘搬运，不允许空手取出裸放。空手且未操作的队友可以接住；忙碌或满手时落邻近合法格，不打断切菜或洗碗。不直接夺取队友手中物品。

案板可暂存生食材或半成品，只有生食材可切。地面每格一件，保留进度，不加工、不加热。

## 锅和餐盘

锅在灶上加热，端走或放柜台/地面即停止加热；放回恢复。不允许裸手拿出熟菜。可以拿干净盘到灶边或地上/柜台上的锅边盛菜；也可以端锅到柜台干净盘旁、或队友手持干净盘旁盛菜。盛完空锅和盘保持各自去向。

手持锅可以与灶台、柜台或地上的另一口锅原位互换，各锅保留自己的食物和加热进度；玩家选中目标后短按空格，AI 有同样的交换动作。换上灶台的锅有食物即开始或恢复加热，离灶的锅停止加热；预先装入的半成品转为烹饪中，空锅不加热。

锅着火时不能直接端走，须灭火再清锅。脏盘不能装菜；脏盘需送水槽、空手洗净后再取用。盘有唯一身份，顾客用餐期间不可再用。两位厨师遵守相同规则。

## 暂停、连接与调用限制

游戏面板不再显示右侧操作按钮和人物卡。右上角使用无可见文字的 Ⅱ、▶、■ 三个并列图标：暂停、继续、提前结束。不可用操作置灰，继续为绿色、结束为红色图标。Esc 仍用于暂停。暂停面板保留重新开局、设置、操作说明，继续使用右上角 ▶。点击 ■ 直接结束本局，停止双方动作与 AI 后续调用，保留提前退出日志；不判为通关、不发时间奖励，也不写入跨局成功/失败回合记忆。开局菜单也提供设置，确保未配置 API 时能连接。页面隐藏/失联会暂停。刷新不会重开。重新开局需在暂停或结算状态进行，会立即启动新一局并沿用当前配置和速度；旧局终止日志保留；提前退出不写入跨局协作记忆。

模型每次选择一个当前合法动作，可继续或中断。事件触发、最短现实间隔2秒、无事件4秒刷新、最多一个在途。Jev 回复有效期6秒/网络超时8秒；兼容服务15秒/20秒；失败按2、4、8、16、30秒退避，没有脚本回退。

默认每局200次请求，开局前/结算后可改下一局1–2000次。失败计数，最后一个额度内请求仍可被处理；达限后已有动作继续，世界不因额度自动暂停，玩家可手动暂停。重开局恢复新局额度，重启服务恢复默认设置。配置不会把付费 Key 填给其他玩家。

停止后端：macOS 双击停止入口；也可执行 `python3 scripts/stop_web.py`（当前自动停止脚本只验证过 macOS）。Windows/Linux 可在前台用 `python3 cocos_server.py --port 8775` 启动并 Ctrl+C 停止；其平台启动体验尚未实测。停止脚本拒绝打断正在进行或暂停中的对局。

角色走路时朝向移动方向，到达工位后朝向实际操作目标（切配、洗碗、取放、装盘等），短动作结束后保留朝向，双方一致。

设置顶部可切换中文 / English，语言偏好保存在当前浏览器。切换立即作用于游戏面板、菜单、工位、物品、状态、操作说明和设置，不重开对局，也不更改模型输入与原始日志。

## 模型输入语言

从 0.3.1-alpha 起，发送给 Jev 和兼容模型的规则、动作说明、厨房状态描述、近期事件及跨局记忆描述统一为英文，标记为 `input_language: en-v1`。动作 ID、坐标、时间和数值不变；模型名称等标识符保持原样。界面中英文切换不影响模型输入。

翻译发生在模型请求边界：本地原始事件与记忆文件保留原文，`ai_request.payload` 记录实际发出的英文输入。旧版中英混合请求与新版英文请求属于不同评测条件，应同时记录语言版本和构建指纹；这次没有添加强制洗碗等策略，也不能据此宣称决策能力提高。

## 第二、三关与共用能力

新增[第二关：汉堡](第二关-长台汉堡.md)：240 秒内制作 3 份汉堡，1 锅 1 灶 2 盘。原窄巷关移为[第三关](第三关-窄巷汉堡.md)，共 5 单（3 汉堡、2 牛排）、三锅两灶。所有关卡固定开放冲刺，没有开关。三关柜台统一为连续木质台面与蓝色柜门，左墙不设柜台，删除左下垃圾桶。

地面及柜台上的空锅可先装入手持切好的牛肉（生肉仍须切配），此时手空、锅留原位，离灶不加热。再按空格拿起整锅，放回灶台后开始加热。不能覆盖锅内已有食物，蔬菜和面包不入锅；双方和三个关卡一致。

## Gameplay bookmarks (0.5.1)

Shift annotates the active run without pausing or changing gameplay. Held-key repeats are ignored. Success and interval-extension notices disappear after 1.6 seconds. Enter retains its existing menu behavior. Bookmarks never enter model observations, action choices or cooperation memory.

Consecutive accepted presses at most 5 real seconds apart merge into a rolling interval, regardless of game speed. Timestamps are captured on server receipt: each mark includes game seconds, timezone-aware wall time, the next kitchen-event index and the latest initiated AI request number. The append-only run log records `bookmark` events with `create`/`extend`, a stable interval ID and its updated snapshot; keep the last snapshot for each ID when extracting. The run-end record also includes the final list.

Settings → Export Run exports all intervals, independent of the 80 recent-event limit. Match `round_id` and game time to the full local run log to extract surrounding context. A new round starts an empty list; previous bookmarks remain in their original log. This is an annotation tool, not a message or correction sent to the AI.

## Teammate communication (0.5.2)

Click the five preference options in the bottom-left communication menu or the separate, always-visible red-outlined correction button; keyboard shortcuts are 1–6. Five preferences cover ingredient preparation, cooking, plating, carrying/serving, and washing; the sixth reports a perceived mistake. Messages share a server-enforced 5-real-second cooldown and are available during running or paused rounds. Text input and dialogs ignore the hotkeys. Messages are fixed choices, never arbitrary prompt text.

The latest preference replaces older preferences for this round only. The AI receives the latest preference and up to eight recent messages at its next regular request; a long-lived preference is retained even when older than that window. The model decides how to cooperate. A correction includes action context but is a player opinion, not a verified rule violation or solution. No jobs or requests are forcibly cancelled and normal API rate limits remain in effect; delivery can wait while paused, disconnected or at the call limit.

`player_message` logs capture send time, fixed text, action context and the full contemporaneous state. `player_message_delivery` identifies the first request containing each message, meaning sent as model input rather than understood or obeyed. Export Run includes all fixed messages with first request IDs, alongside bookmarks. Communications are not included in cross-round memory; this permits comparing autonomous and explicitly guided cooperation by intervention count and outcomes.

## 火势与冲刺表现（0.5.5）

每个着火灶台、案板或普通柜台每隔 8 游戏秒向一个上下左右相邻、尚未着火的可燃工位蔓延，不跨越地面或墙。水槽、食材来源、出餐及回收设备不参与蔓延。每次新起火扣 5 元；同时达到 5 个着火工位时本局失败，无通关奖励。灭火后该工位重新可用，但邻近火源仍可再次引燃它。着火会中断该工位操作，两位厨师都可拿灭火器扑灭。模型收到英文规则、各工位蔓延倒计时、邻接工位及总着火数。

冲刺沿用所有关卡的双击方向键和 AI sprint 判断，增加移动时的扬尘；暂停时动画停止。第一关使用像素火焰、烟雾与焦痕，第二、三关同样使用像素火焰、烟雾与扬尘。
