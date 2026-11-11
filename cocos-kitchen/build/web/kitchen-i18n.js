/* Display-only localization. No game state, API inputs or logs are rewritten. */
(function (root) {
  'use strict';
  const catalog = {
  "messages": {
    "和AI一起经营餐馆": "Run a restaurant with AI",
    "正在打开小厨房…": "Opening your kitchen…",
    "当前厨房不支持位置上报": "This kitchen does not accept position reports.",
    "位置信息无效": "Invalid position.",
    "朝向无效": "Invalid aim.",
    "目标无效": "Invalid target",
    "iPhone 不支持网页全屏：在浏览器的分享菜单选「添加到主屏幕」，再从主屏幕打开即可全屏。": "iPhone browsers cannot go full screen: choose Add to Home Screen in the browser's Share menu, then open ChefJeff from the Home Screen.",
    "网络不稳定，正在重连…": "Unsteady connection, reconnecting…",
    "打开快慢取决于你的网络，第一次要下载约 2 MB，之后再打开会快很多。": "Loading time depends on your network: the first visit downloads about 2 MB, later visits are much faster.",
    "横屏游玩，工位和按钮会更清楚。": "Play in landscape for a clearer kitchen and controls.",
    "全屏看厨房": "Full screen",
    "请手动展开浏览器窗口": "Please enlarge your browser window",
    "完成订单": "Orders served",
    "营业收入": "Revenue",
    "准备开店": "Ready to open",
    "暂停": "Pause",
    "设置": "Settings",
    "声音": "Sound",
    "音乐": "Music",
    "音效": "Sound effects",
    "拉到 0 即静音。设置只保存在这台设备的浏览器里。": "Drag to 0 to mute. Settings are saved only in this device's browser.",
    "操作说明": "Controls",
    "手柄已连接": "Controller connected",
    "请松开按键并将左摇杆回中": "Release the buttons and center the left stick",
    "按输入计费，约每百万 token 0.02 美元 · 请求只含 model、state、questions": "Billed by input, about USD 0.02 per million tokens · requests carry only model, state and questions",
    "Parallel Decisions（仅本地游戏）": "Parallel Decisions (local game only)",
    "Key 放在 x-api-key 请求头里 · 请求只含 state、questions 和 mode（fast）": "The key goes in the x-api-key header · requests carry only state, questions and mode (fast)",
    "此手柄未提供标准映射，请使用键盘和鼠标。": "This controller has no standard mapping; use the keyboard and mouse.",
    "手柄：左摇杆或十字键移动，A/× 拿放，X/□ 切、洗、扔（持物长按瞄准、松手投掷），B/○ 冲刺；Start/Options 开始或暂停、继续。Switch 单只手柄横握（Safari，左右手柄都行）：右键拿放，左键切洗扔，下键冲刺，左手柄 − 暂停，右手柄 + 暂停。": "Controller: Left stick or D-pad to move; A/× to take or put; X/□ to chop, wash or throw (hold with an item to aim, release to throw); B/○ to dash; Start/Options to start, pause or resume. One Switch Joy-Con held sideways, left or right (Safari): right button takes or puts, left button chops, washes or throws, bottom button dashes, − (left) or + (right) pauses.",
    "首次连接后先按一下手柄按键，再放开按键并将左摇杆回中。设置和沟通菜单仍使用键盘和鼠标；只支持浏览器识别为标准布局的手柄。": "After connecting, press a controller button, then release the buttons and center the left stick. Settings and communication menus still use the keyboard and mouse. Only controllers the browser recognizes as standard are supported.",
    "开始经营": "Start cooking",
    "继续经营": "Resume",
    "重新开局": "Restart round",
    "准备下一局": "Next round",
    "关店结算 · 达成目标": "Closing time · Target reached",
    "关店结算 · 未达目标": "Closing time · Target missed",
    "本局已结束，点“准备下一局”再来一局。": "The round is over. Choose “Next round” to play again.",
    "先连接搭档": "Connect your AI",
    "重新连接": "Reconnect",
    "歇一小会儿": "Taking a break",
    "今天，配合得不错！": "Great teamwork today!",
    "明天再接再厉": "Try again tomorrow",
    "正在连接厨房…": "Connecting to the kitchen…",
    "等待厨房更新": "Waiting for update",
    "连接厨房": "Connecting",
    "备 菜 区": "PREP AREA",
    "烹 饪 区": "COOKING AREA",
    "你": "You",
    "生肉": "Raw meat",
    "生食材": "Raw ingredient",
    "半成品": "Chopped meat",
    "加热中": "Cooking",
    "熟牛排": "Cooked steak",
    "糊菜": "Burnt food",
    "灭火器": "Extinguisher",
    "干净餐盘": "Clean plate",
    "脏餐盘": "Dirty plate",
    "已装盘牛排": "Plated steak",
    "已装盘糊菜": "Burnt dish",
    "空锅": "Empty pot",
    "锅 · 未熟": "Pot · uncooked",
    "锅 · 熟牛排": "Pot · steak",
    "锅 · 糊菜": "Pot · burnt",
    "冰箱": "Fridge",
    "案板": "Board",
    "灶台": "Stove",
    "柜台": "Counter",
    "空柜台": "Empty counter",
    "垃圾桶": "Bin",
    "出餐口": "Serve",
    "水槽": "Sink",
    "脏盘回收": "Plate return",
    "沥水架": "Drying rack",
    "脏盘待洗": "Dirty plate",
    "洗好了": "Washed",
    "着火了！": "Fire!",
    "熟了！": "Ready!",
    "手中：": "Holding: ",
    "空手": "Empty hands",
    "营业中": "Open",
    "休息中": "Paused",
    "已结算": "Finished",
    "订单夹": "Orders",
    "待出餐": "To serve",
    "快超时了": "Hurry!",
    "香煎牛排": "Steak",
    "等待新订单": "Waiting for orders",
    "订单已结清": "All orders cleared",
    "空格 · ": "Space · ",
    "中断当前动作": "Stop current task",
    "继续当前动作": "Continue current task",
    "暂时等待": "Wait",
    "洗碗": "Wash dishes",
    "返回厨房": "Back to kitchen",
    "尚未配置": "Not configured",
    "建议优先选择 Jev": "Jev is recommended",
    "模型服务": "AI provider",
    "TypeSafe · Jev（推荐）": "TypeSafe · Jev (recommended)",
    "其他兼容 Chat Completions 的服务": "Other Chat Completions provider",
    "接口地址（Base URL）": "Base URL",
    "https://你的服务地址/v1": "https://your-provider.example/v1",
    "模型名称": "Model name",
    "服务商提供的模型 ID": "Model ID from your provider",
    "粘贴你的 API Key": "Paste your API key",
    "去服务商获取 Key ↗": "Get a key from your provider ↗",
    "记住此设备（共用电脑请勿勾选）": "Remember on this device (not on shared computers)",
    "测试并连接": "Test and connect",
    "清除配置": "Clear credentials",
    "跨局协作记忆 · 试验版": "Cross-round memory · experimental",
    "下一局使用并保存跨局记忆": "Use and save memory from the next round",
    "清空所有模型的协作记忆": "Clear memory for all models",
    "调用上限与用量": "Call limit and usage",
    "下一局最多调用次数（1–2000）": "Next-round call limit (1–2000)",
    "保存下一局上限": "Save call limit",
    "版本与问题反馈": "Version and feedback",
    "生成并预览反馈": "Generate feedback preview",
    "下载已预览 JSON": "Download previewed JSON",
    "待导出的反馈内容": "Feedback to export",
    "尚未配置 · 不使用开发者 Key": "Not configured · no developer key is used",
    "需要新版厨房服务。": "Please update the kitchen service.",
    "版本信息暂不可用": "Version information unavailable",
    "已开启": "Enabled",
    "已关闭": "Disabled",
    "正在清除…": "Clearing…",
    "正在测试连接，请稍候…": "Testing connection, please wait…",
    "连接失败": "Connection failed",
    "正在保存记忆设置…": "Saving memory settings…",
    "记忆设置失败": "Could not save memory settings",
    "厨房尚未连接": "Kitchen is not connected",
    "操作失败": "Action failed",
    "正在保存…": "Saving…",
    "放下和拾取": "Put down and pick up",
    "餐具和锅": "Plates and pots",
    "丢弃与消防": "Discarding and fires",
    "暂停与继续 · Esc / P": "Pause & resume · Esc / P",
    "界面语言": "Interface language",
    "抛掷已准备 · 左键选落点": "Ready to throw · left click a destination",
    "去灭火器架拿灭火器": "Take the extinguisher",
    "把灭火器放回架子": "Return the extinguisher",
    "把脏餐盘放入水槽": "Put the dirty plate in the sink",
    "拿已装盘的菜出餐": "Serve the plated dish",
    "到冰箱取一份生肉": "Take raw meat from the fridge",
    "去垃圾桶丢弃手中食物": "Discard the held food at the bin",
    "端锅走近，给队友手中的干净盘装菜": "Bring the pot to your teammate and fill their clean plate",
    "厨房返回了无效数据": "Invalid kitchen response",
    "无法连接厨房后端": "Cannot connect to the kitchen",
    "厨房连接超时": "Kitchen connection timed out",
    "，厨房会自动暂停。": ". The kitchen will pause automatically.",
    "请先暂停，再重新开局。": "Pause before restarting the round.",
    "先暂停，再重新开局。": "Pause before restarting the round.",
    "本局已经开始。": "This round has already started.",
    "当前无需继续。": "There is no paused round to resume.",
    "当前不能操作": "You cannot interact right now",
    "手中物品已变化，请重新按空格": "Your held item changed. Tap Space again.",
    "当前不能抛掷": "You cannot throw right now",
    "抛掷方向无效": "Invalid throw direction",
    "手中物品已变化": "Your held item changed",
    "没有可用落点，或此物品不能抛掷": "No landing space, or this item cannot be thrown",
    "这是上一局的操作，请刷新页面。": "This action belongs to an old round. Refresh the page.",
    "请求无效，请重试。": "Invalid request. Please try again.",
    "请在开局前或结算后修改下一局调用上限。": "Change the call limit before a round or after it ends.",
    "调用上限须为 1–2000 的整数。": "The call limit must be an integer from 1 to 2000.",
    "请在开局前或结算后修改记忆设置，保证一局内条件一致。": "Change memory settings before a round or after it ends.",
    "记忆设置无效。": "Invalid memory settings.",
    "没有指定记忆操作。": "No memory action was specified.",
    "无法保存记忆设置，请检查本地文件权限。": "Cannot save memory settings. Check local file permissions.",
    "正在测试连接，请等测试完成后再开局。": "Wait for the connection test to finish before starting.",
    "请先打开 API 设置，连接你自己的账号。不会使用开发者的 Key。": "Connect your own account in Settings first. No developer key will be used.",
    "请在开局前或结算后修改连接；请完成当前对局后再修改。": "Change your connection before a round or after the current round ends.",
    "对局已变化，请重试。": "The round changed. Please try again.",
    "请求无效。": "Invalid request.",
    "无法清除保存的连接，请检查文件权限。": "Cannot clear saved credentials. Check file permissions.",
    "本局已结束，但跨局记录未能保存；请检查本地文件权限。": "The round ended, but memory could not be saved. Check file permissions.",
    "使用你自己的 API 账号，调用费用由该账号承担。": "Use your own API account. Calls are billed to that account.",
    "：这间厨房是围绕 Jev 开发的；其他模型也可使用，响应速度和配合方式可能不同。": ": this kitchen was developed around Jev. Other models work too; response times and cooperation may differ.",
    "建议使用响应快的模型；过慢或无效的动作不会执行。": "Choose a responsive model. Actions that arrive too late or are invalid will not run.",
    "默认只在本次服务运行期间使用。记住后以明文保存在这台电脑的本地配置文件；Key 不进入对局日志和试玩包。": "By default, credentials last only until the local service stops. Remembering stores them in plain text on this computer. Keys are excluded from game logs and demo packages.",
    "测试连接会发送一次小型 API 请求，可能产生少量费用。": "Testing sends one small API request and may incur a charge.",
    "保留最近 3 局的有限事件片段，让搭档自行判断如何配合，不预设你的习惯。不同接口和模型分开保存。": "Keep limited event excerpts from the last 3 rounds. Your teammate decides how to adapt; no habits are assigned to you. Providers and models have separate memory.",
    "记录保存在本机，旧局片段会随决策请求发送给你选择的模型服务，增加输入 token 和费用。关闭后不读、不保存；中途退出的局不保存。": "Records stay on this computer. Past excerpts are sent with decisions to your chosen model, adding input tokens and cost. When disabled, memory is neither read nor saved. Aborted rounds are not saved.",
    "默认每局 200 次，失败请求也计入；达限后不再请求，已有动作继续，玩家仍可操作。设置仅保留到服务关闭。连接测试另计，每次可能收费。Token 仅统计成功回复提供的用量，不代表完整账单；费用以服务商为准。": "Default: 200 calls per round, including failed requests. At the limit, new requests stop; existing actions and player controls continue. This setting lasts until the service stops. Connection tests are counted separately and may cost money. Token totals include usage reported by successful replies, not the full bill. Check your provider for charges.",
    "导出当前局摘要和最近 80 条动作事件。不会附带 Key、接口地址、模型名称文本、跨局记忆、完整请求或私人日志。文件只下载到本机，不自动上传。": "Export a round summary and the latest 80 action events. Keys, endpoint URLs, model-name text, memory, full requests and private logs are excluded. The file downloads locally and is not uploaded.",
    "这个旧页面还不支持 API 配置，请使用新版服务。": "This page does not support API settings. Please update the service.",
    "请在开局前或结算后更换 API；请完成当前对局后再修改。": "Change the API before a round or after it ends. Please finish this round first.",
    "配置已清除。下次开局需要重新连接。": "Credentials cleared. Connect again before the next round.",
    "连接成功！返回厨房即可开局，费用由你的 API 账号承担。": "Connected! Return to the kitchen to start. Your API account pays for calls.",
    "请求超时。请检查网络后重试。": "Request timed out. Check your connection and try again.",
    "请求超时，请重新打开设置确认结果。": "Request timed out. Reopen Settings to check the result.",
    "请检查下方内容；点击下载后才会保存文件。": "Review the content below. The file is saved only when you click Download.",
    "靠近后按空格，底部文字会显示将执行的动作：取料、放到案板、切菜、拿起、下锅、装盘、洗碗或出餐。正在加工时再按空格可停下，进度保留。": "Move close and tap Space. The bottom hint shows the action: fetch, put on a board, chop, pick up, cook, plate, wash or serve. Tap Space while working to stop and keep progress.",
    "拿食材靠近垃圾桶按空格会销毁，扣 2 元；端锅则倒掉锅里的食物，保留空锅。灭火器在右上方，拿起后靠近着火灶台按空格灭火。": "Hold food near a bin and tap Space to discard it for a ¥2 penalty. If holding a pot, its food is discarded and the pot stays. Take the extinguisher at the top right, then tap Space near a burning stove.",
    "暂停会停止锅火、订单和双方动作。再按 Esc 或 P（键盘没有 Esc 键时用，如 iPad）或点「继续经营」回到厨房；也可重新开局、打开设置或查看本说明。结束本局、暂停中重新开局都会先请你确认；重新开局沿用当前配置与速度。更换 API、记忆和调用上限请在结算后或开局前进行。": "Pause freezes cooking, orders and both chefs. Press Esc or P again (P is for keyboards without Esc, such as an iPad's) or choose Resume to return to the kitchen; you can also restart, open Settings or read Controls. Ending a round, or restarting from pause, asks you to confirm first; a restart keeps the same configuration and speed. Change API, memory and call limits before a round or after it ends.",
    "请先从下方「设置」连接自己的 API，再开始经营。": "Connect your own API in Settings below before starting.",
    "只能抛生食材或切好的原料；餐盘、带盘菜、锅和工具请放下或搬运。": "Only raw or chopped ingredients can be thrown. Carry or put down plates, plated food, pots and tools.",
    "新版页面已就绪，厨房服务仍在保留旧对局。\n服务更新后会自动连接，请先完成更新确认。": "The new page is ready, but the service still holds the old round.\nConfirm the update; the page will reconnect automatically.",
    "暂时连接不上厨房，请稍后重试。\n连接中断时，游戏会自动暂停。": "Cannot connect to the kitchen. Please try again.\nThe game pauses automatically when disconnected.",
    "靠近 Jeff，按空格给他手中的干净盘装菜。": "Move near Jeff and tap Space to fill the clean plate he is holding.",
    "本局 AI 调用已达上限；已有动作继续。你可继续玩或暂停，下局可调整上限。": "AI call limit reached. Existing actions continue. Keep playing or pause; adjust the limit for the next round.",
    "锅火和订单都按下了暂停。\n准备好了，就和 Jeff 接着做菜。": "Cooking and orders are paused.\nResume cooking with Jeff when you are ready.",
    "页面已断开，厨房自动暂停。回来后点击继续。": "Disconnected: the kitchen paused. Click Resume when you return.",
    "厨房已暂停，你和 Jeff 的动作、锅与订单倒计时都已停下。": "Kitchen paused: both chefs, cooking and order timers are frozen.",
    "离开页面，厨房已自动暂停。": "Kitchen paused because the page was hidden.",
    "厨房已暂停：运行出现异常，请重新开局。": "Kitchen paused after an error. Please restart the round.",
    "本局运行出现异常，请重新开局。": "This round hit an error. Please restart the round.",
    "AI 搭档暂时连接不上，正在重试。你仍可以操作或先暂停。": "AI teammate disconnected; retrying. You can keep playing or pause.",
    " · 已记住此设备": " · remembered on this device",
    " · 已达上限": " · limit reached",
    "案板有食材正在飞入，本次放置取消": "An ingredient is landing on the board; placement cancelled",
    "队友已移动或物品变化，装盘取消": "Teammate moved or items changed; plating cancelled",
    "装盘时队友或物品变化，物品保持原样": "Teammate or items changed; nothing transferred",
    "地上锅或手中餐盘已变化，装盘取消": "The floor pot or held plate changed; plating cancelled",
    "没有这个操作。": "Unknown action.",
    "当前厨房不支持方向移动": "Directional movement is unavailable in this kitchen.",
    "移动输入无效": "Invalid movement input.",
    "仅允许本机页面访问。": "Only local pages may access this service.",
    "页面不存在。": "Page not found.",
    "仅允许本机页面操作。": "Only local pages may control this service.",
    "需要 JSON 请求。": "A JSON request is required.",
    "厨房未营业": "The kitchen is not open.",
    "请选择页面中的游戏节奏。": "Choose a game speed shown on the page.",
    "先开始或继续本局，再点击动作。": "Start or resume the round before choosing an action.",
    "动作信息无效，请重试。": "Invalid action data. Please try again.",
    "刚才的食材或工位状态变了，请按更新后的按钮操作。": "The ingredient or station changed. Use the updated action.",
    "请求格式无效。": "Invalid request format.",
    "没有读到可用的本地 Jev 配置，请检查 .env。厨房尚未开始计时。": "No usable local Jev configuration. Check .env. The kitchen timer has not started.",
    "对局已变化，连接未保存。": "The round changed. The connection was not saved.",
    "自动换手": "auto-swap",
    "切配进度保留；锅继续加热": "prep progress kept; pot keeps heating",
    "可捡回、不扣钱": "recoverable, no charge",
    "可捡回，不扣钱": "recoverable, no charge",
    "每格一件": "one item per tile",
    "有食物时恢复加热": "resume heating if filled",
    "离开灶台停止加热，占手持位": "stops heating off the stove; occupies your hands",
    "占用手持位": "occupies your hands",
    "可中断续洗": "can stop and resume",
    "损耗 2 元，无法捡回": "¥2 cost; cannot be recovered",
    "损耗2元，保留空锅": "¥2 cost; keep the pot",
    "损耗 2 元": "¥2 cost",
    "没有订单在等这道菜会扣钱，糊太久会被拒收": "serving a dish no order is waiting for costs money; a dish burnt too long is refused",
    "随后仍须端锅到垃圾桶倒掉糊菜": "then carry the pan to a bin to empty the burnt food",
    "抛出物品": "throw item",
    "糊了的菜": "burnt food",
    "没有待完成订单": "no pending order",
    "食物没熟或没切配": "food is uncooked or unprepared",
    "未装盘": "not plated",
    "超时": "expired",
    "失败": "failed",
    "任务失败": "Goal failed",
    "净收入": "Net revenue",
    "糊锅": "Burnt pots",
    "着火": "Fires",
    "剩": "left ",
    "最多": "maximum ",
    "元": " yuan",
    "次": " times",
    "单": " orders",
    "没有有效订单": "no valid order",
    "成功": "completed",
    "出餐": "Orders served",
    "剩余": "Remaining",
    "合计": "Total",
    "已切配": "Chopped",
    "未熟": "Uncooked",
    "熟菜": "Cooked food",
    "灭火器架": "Extinguisher rack",
    "去垃圾桶 2丢弃手中食物": "Discard the held food at bin 2",
    "切好": "Chopped",
    "熟了": "Cooked",
    "糊了": "Burnt",
    "锅": "Pot",
    "切菜": "Chop",
    "继续": "Continue",
    "已中断": "Stopped",
    "开始": "Started",
    "开始抛递": "Throw started",
    "同一本地玩家与当前接口/模型的过往已结束对局。事件为按时间抽样的事实，非完整录像、非玩家偏好结论；物品编号和坐标仅属于各自旧局。": "Past completed rounds for the same local player and provider/model. Events are facts sampled over time, not a full replay or inferred preferences. Item IDs and coordinates belong only to their original rounds.",
    "状态已变化，该动作已失效；请重新查看选项": "State changed; this action is no longer valid. Review the available choices.",
    "回复已过期、任务已变化或游戏已暂停": "Reply expired, task changed, or game paused",
    "当前无法执行；输入 m 查看可用动作": "Action unavailable; review the available choices.",
    "抛递目标已变化，请重新选择": "Throw target changed; choose again",
    "队友或锅中的物品已变化": "Teammate or pot contents changed",
    "待组装菜品": "Partially assembled dish",
    "第一关 · 练习": "Level 1 · Practice",
    "第二关 · 窄巷汉堡": "Level 2 · Burger alley",
    "汉堡": "Burger",
    "面包": "Bread",
    "生菜": "Lettuce",
    "番茄": "Tomato",
    "熟牛肉": "Cooked beef",
    "待组装": "Assembling",
    "缺少": "Missing",
    "冲刺": "Sprint",
    "冷却": "Cooldown",
    "生菜箱": "Lettuce supply",
    "番茄箱": "Tomato supply",
    "面包箱": "Bread supply",
    "开始前选择第二关。两个灶台、三口锅，备用空锅在右上柜台。面包直接装盘；生菜和番茄切好，牛肉切好后煎熟。把配料加入柜台上的干净盘，可任意顺序组装；缺料不能出餐。牛排 2 单、汉堡 2 单，顺序每局随机。": "Choose Level 2 before starting. Two stoves and three pots; the spare pot is on the top-right counter. Bread needs no prep. Chop lettuce and tomato; chop and cook beef. Add ingredients to a clean plate on a counter in any order. Incomplete dishes cannot be served. Each round has 2 steaks and 2 burgers in shuffled order.",
    "冲刺中": "Sprinting",
    "冲刺冷却": "Sprint cooldown",
    "走近，把食材加入队友手中的盘（容器留在原持有者手中）": "Approach and add food to the teammate's held plate (containers stay with their holders)",
    "暂不能出餐，还缺：": "Cannot serve yet. Missing: ",
    "切好的生菜": "Chopped lettuce",
    "切好的番茄": "Chopped tomato",
    "可手持盘从案板或柜台收集切好蔬菜和面包，也能给队友手中盘加料。两盘无重复配料可合并：成品留手中，柜台留空盘。牛肉须先煎熟；缺料不能出餐。": "Collect prepared vegetables and bread from boards or counters into a held plate, or add them to a teammate's plate. Merge plates with no duplicate ingredients: the combined dish stays in hand and the empty plate stays on the counter. Cook beef first; incomplete dishes cannot be served.",
    "开始前选择第二关。两个灶台、三口锅，备用空锅在右上柜台。面包直接装盘；生菜和番茄切好，牛肉切好后煎熟。可手持盘从案板或柜台收集切好蔬菜和面包，也能给队友手中盘加料。两盘无重复配料可合并：成品留手中，柜台留空盘。牛肉须先煎熟；缺料不能出餐。牛排 2 单、汉堡 2 单，顺序每局随机。": "Choose Level 2 before starting. Two stoves and three pots; the spare pot is on the top-right counter. Bread needs no prep. Chop lettuce and tomato; chop and cook beef. Add ingredients to a clean plate on a counter in any order. Incomplete dishes cannot be served. Each round has 2 steaks and 2 burgers in shuffled order. Held plates can collect prepared ingredients from boards/counters. Add food to a teammate's plate, or merge two non-overlapping plates; the empty source plate stays in place.",
    "把切好的牛肉放入地上空锅（离灶不加热）": "Load chopped beef into the empty floor pot (no heating off stove)",
    "地上物品或手中物品已变化，加入盘中取消": "Floor item or held item changed; adding to the plate was cancelled",
    "地上锅或手中食材已变化，入锅取消": "Floor pot or held ingredient changed; loading cancelled",
    "选中目标暂不可操作，请靠近或检查物品状态": "Selected target cannot be used now; move closer or check items",
    "请靠近选中的出餐口": "Move closer to the selected serving hatch",
    "地上物品已变化，请重新选择": "Ground item changed; select it again",
    "点击工位或地上物品后，空格只操作选中目标；条件不满足时给出提示。方向移动或点击空地恢复就近操作。地上空锅可先放切好的牛肉，再按空格端锅，离灶不加热。底部文字会显示将执行的动作：": "Space acts on the selected station or ground item; unavailable actions show a hint. Direction keys or clicking empty floor restore nearby interactions. Load chopped beef into an empty floor pot, then press Space again to lift it; it heats only on a stove. The footer shows the next action: ",
    "点击工位或地上物品后，空格只操作选中目标；条件不满足时给出提示。方向移动或点击空地恢复就近操作。地上空锅可先放切好的牛肉，再按空格端锅，离灶不加热。底部文字会显示将执行的动作：取料、放到案板、切菜、拿起、下锅、装盘、洗碗或出餐。正在加工时再按空格可停下，进度保留。": "Space acts on the selected station or ground item; unavailable actions show a hint. Direction keys or clicking empty floor restore nearby interactions. Load chopped beef into an empty floor pot, then press Space again to lift it; it heats only on a stove. The footer shows the next action: Move close and tap Space. The bottom hint shows the action: fetch, put on a board, chop, pick up, cook, plate, wash or serve. Tap Space while working to stop and keep progress.",
    "面前没有可操作目标": "Nothing to use in front of you",
    "结束本局": "End round",
    "本局已结束": "Round ended",
    "当前没有进行中的对局。": "There is no active round.",
    "第二关 · 长台汉堡": "Level 2 · Counter Burgers",
    "第三关 · 窄巷汉堡": "Level 3 · Narrow Aisle",
    "单间厨房由横向长柜台分为上下工作区，右侧通道相连。3 份汉堡，240 游戏秒，1 口锅、1 个灶台、2 只盘子、2 块案板；需要回收洗盘。食材和装盘规则与第三关相同。": "A horizontal counter divides the kitchen into upper and lower workspaces, joined on the right. Make 3 burgers in 240 game seconds with 1 pot, 1 stove, 2 plates and 2 boards. Recycle and wash plates. Ingredients and assembly follow the same rules as level 3.",
    "拿食材靠近垃圾桶按空格会销毁，扣 2 元；端锅则倒掉锅里的食物，保留空锅。拿起灭火器后靠近着火灶台按空格灭火。": "Hold food near a bin and tap Space to discard it for a ¥2 penalty. If holding a pot, its food is discarded and the pot stays. Take the extinguisher at the top right, then tap Space near a burning stove.",
    "开始前选择第三关。两个灶台、三口锅，备用空锅在右上柜台。面包直接装盘；生菜和番茄切好，牛肉切好后煎熟。把配料加入柜台上的干净盘，可任意顺序组装；缺料不能出餐。牛排 2 单、汉堡 2 单，顺序每局随机。": "Choose Level 3 before starting. Two stoves and three pots; the spare pot is on the top-right counter. Bread needs no prep. Chop lettuce and tomato; chop and cook beef. Add ingredients to a clean plate on a counter in any order. Incomplete dishes cannot be served. Each round has 2 steaks and 2 burgers in shuffled order.",
    "开始前选择第三关。两个灶台、三口锅，备用空锅在右上柜台。面包直接装盘；生菜和番茄切好，牛肉切好后煎熟。可手持盘从案板或柜台收集切好蔬菜和面包，也能给队友手中盘加料。两盘无重复配料可合并：成品留手中，柜台留空盘。牛肉须先煎熟；缺料不能出餐。牛排 2 单、汉堡 2 单，顺序每局随机。": "Choose Level 3 before starting. Two stoves and three pots; the spare pot is on the top-right counter. Bread needs no prep. Chop lettuce and tomato; chop and cook beef. Add ingredients to a clean plate on a counter in any order. Incomplete dishes cannot be served. Each round has 2 steaks and 2 burgers in shuffled order. Held plates can collect prepared ingredients from boards/counters. Add food to a teammate's plate, or merge two non-overlapping plates; the empty source plate stays in place.",
    "长 台 厨 房": "COUNTER KITCHEN",
    "导出当前局摘要、全部标记和最近 80 条动作事件。标记包含游戏时间和实际时间，可对应本地日志提取前后过程。不会附带 Key、接口地址、模型名称文本、跨局记忆或完整请求。文件只下载到本机，不自动上传。": "Export the run summary, all bookmarks and the last 80 action events. Game and wall timestamps locate surrounding context in the local log. Keys, endpoint and model text, cross-round memory and full requests are excluded. Downloads stay local; nothing is uploaded.",
    "只能在营业中标记片段。": "Bookmarks are available during active gameplay only.",
    "标记未保存，请重试。": "Bookmark not saved. Please retry.",
    "标记未确认，请检查导出记录。": "Bookmark unconfirmed. Please check the run export.",
    "已延长标记片段": "Bookmark interval extended",
    "已标记当前片段": "Moment bookmarked",
    "队友沟通": "Teammate communication",
    "你做错了": "You made a mistake",
    "沟通 · 1–6": "Communicate · 1–6",
    "偏好：备菜": "Preference: ingredient prep",
    "偏好：烹饪": "Preference: cooking",
    "偏好：摆盘": "Preference: plating",
    "偏好：传菜": "Preference: carrying / serving",
    "偏好：洗盘子": "Preference: washing dishes",
    "点击选项或按 1–6 发送": "Click an option or press 1–6",
    "请在对局开始后、结束前发送沟通。": "Send messages after the round starts and before it ends.",
    "未知的沟通选项。": "Unknown communication option.",
    "沟通冷却中，请稍后再发。": "Communication is cooling down. Please wait.",
    "沟通未保存，请重试。": "Message not saved. Please retry.",
    "沟通未确认，请检查导出记录。": "Message unconfirmed. Please check the run export.",
    "已记录沟通，将随下一次 AI 请求发送。": "Message recorded for the next AI request.",
    "沟通 · 1–6 / 点击": "Communicate · 1–6 / Click",
    "打开左下角沟通菜单，点击即可发送，也可直接按 1–5 表达当前偏好、按 6 反馈“你做错了”。共用 5 个实际秒冷却，暂停时也可发送。最新偏好只在本局有效；AI 在下一次正常请求中收到，自行判断如何配合，不强制分工或停止动作。纠错附带当时动作信息，但不指定正确答案。": "Open the bottom-left communication menu and click to send, or press 1–5 for a preference and 6 for a correction. All share a 5-real-second cooldown; messages also work while paused. The latest preference applies only to this round. The AI receives it in its next regular request and decides how to cooperate; jobs and roles are not forced. Corrections include action context, not a prescribed solution.",
    "导出当前局摘要、全部标记、沟通记录和最近 80 条动作事件。标记包含游戏时间和实际时间，可对应本地日志提取前后过程。不会附带 Key、接口地址、模型名称文本、跨局记忆或完整请求。文件只下载到本机，不自动上传。": "Export the run summary, all bookmarks, communication records and the last 80 action events. Game and wall timestamps locate surrounding context in the local log. Keys, endpoint and model text, cross-round memory and full requests are excluded. Downloads stay local; nothing is uploaded.",
    "打开左下角沟通菜单，点击偏好即可发送；“你做错了”是独立的红色描边按钮。也可按 1–5 表达偏好、按 6 纠错。共用 5 个实际秒冷却，暂停时也可发送。最新偏好只在本局有效；AI 在下一次正常请求中收到，自行判断如何配合，不强制分工或停止动作。纠错附带当时动作信息，但不指定正确答案。": "Click a preference in the bottom-left menu, or the separate red-outlined correction button. Shortcuts: 1–5 for preferences, 6 for correction. All share a 5-real-second cooldown; messages also work while paused. The latest preference applies only to this round. The AI receives it in its next regular request and decides how to cooperate; jobs and roles are not forced. Corrections include action context, not a prescribed solution.",
    "第一关 · 牛排": "Level 1 · Steak",
    "开始前选择第二关。两个灶台、三口锅，备用空锅在右上柜台。面包直接装盘；生菜和番茄切好，牛肉切好后煎熟。把配料加入柜台上的干净盘，可任意顺序组装；缺料不能出餐。牛排 2 单、汉堡 3 单，顺序每局随机。": "Choose Level 2 before starting. Two stoves and three pots; the spare pot is on the top-right counter. Bread needs no prep. Chop lettuce and tomato; chop and cook beef. Add ingredients to a clean plate on a counter in any order. Incomplete dishes cannot be served. Each round has 2 steaks and 3 burgers in shuffled order.",
    "开始前选择第二关。两个灶台、三口锅，备用空锅在右上柜台。面包直接装盘；生菜和番茄切好，牛肉切好后煎熟。可手持盘从案板或柜台收集切好蔬菜和面包，也能给队友手中盘加料。两盘无重复配料可合并：成品留手中，柜台留空盘。牛肉须先煎熟；缺料不能出餐。牛排 2 单、汉堡 3 单，顺序每局随机。": "Choose Level 2 before starting. Two stoves and three pots; the spare pot is on the top-right counter. Bread needs no prep. Chop lettuce and tomato; chop and cook beef. Add ingredients to a clean plate on a counter in any order. Incomplete dishes cannot be served. Each round has 2 steaks and 3 burgers in shuffled order. Held plates can collect prepared ingredients from boards/counters. Add food to a teammate's plate, or merge two non-overlapping plates; the empty source plate stays in place.",
    "第二关 · 汉堡": "Level 2 · Burger",
    "第三关 · 牛-堡": "Level 3 · Steak & Burger",
    "牛-堡": "Steak & Burger",
    "第四关 · 隔台协作": "Level 4 · Across the Counter",
    "隔台协作": "Across the Counter",
    "一排柜台从墙边连到墙边，把厨房隔成上下两块，谁也绕不过去。上面是食材箱、两个灶台、出餐口和垃圾桶；下面是两块案板、水槽、脏盘回收、灭火器架和第二个垃圾桶。生肉和蔬菜递到下面切，切好递回上面煎、装盘、出餐，干净盘子从下面递上来：每道菜都要两个人。180 游戏秒，每 30 秒来一单牛排或汉堡（¥50／¥80），关店时净收入达到 ¥100 即达标。": "A row of counters runs from wall to wall and splits the kitchen into an upper and a lower part; nobody can walk round. Above: the ingredient sources, two stoves, the serving window and a bin. Below: two boards, the sink, the dirty-plate return, the extinguisher rack and a second bin. Raw beef and vegetables are passed down to be chopped, then back up to be cooked, plated and served, and clean plates come up from the sink: every dish needs both chefs. 180 game seconds; a steak or burger order (¥50/¥80) arrives every 30 seconds; reach ¥100 net revenue by closing time.",
    "开始前选择第三关。两个灶台、三口锅，备用空锅在右上柜台。面包直接装盘；生菜和番茄切好，牛肉切好后煎熟。把配料加入柜台上的干净盘，可任意顺序组装；缺料不能出餐。牛排 2 单、汉堡 3 单，顺序每局随机。": "Choose Level 3 before starting. Two stoves and three pots; the spare pot is on the top-right counter. Bread needs no prep. Chop lettuce and tomato; chop and cook beef. Add ingredients to a clean plate on a counter in any order. Incomplete dishes cannot be served. Each round has 2 steaks and 3 burgers in shuffled order.",
    "开始前选择第三关。两个灶台、三口锅，备用空锅在右上柜台。面包直接装盘；生菜和番茄切好，牛肉切好后煎熟。可手持盘从案板或柜台收集切好蔬菜和面包，也能给队友手中盘加料。两盘无重复配料可合并：成品留手中，柜台留空盘。牛肉须先煎熟；缺料不能出餐。牛排 2 单、汉堡 3 单，顺序每局随机。": "Choose Level 3 before starting. Two stoves and three pots; the spare pot is on the top-right counter. Bread needs no prep. Chop lettuce and tomato; chop and cook beef. Add ingredients to a clean plate on a counter in any order. Incomplete dishes cannot be served. Each round has 2 steaks and 3 burgers in shuffled order. Held plates can collect prepared ingredients from boards/counters. Add food to a teammate's plate, or merge two non-overlapping plates; the empty source plate stays in place.",
    "火势失控": "Fire out of control",
    "火势失控，本局结束": "Fire out of control. Round ended.",
    "默认每局 200 次，失败请求也计入；达限后不再请求，已有动作继续，玩家仍可操作。设置仅保留到当前页面会话结束。连接测试另计，每次可能收费。Token 仅统计成功回复提供的用量，不代表完整账单；费用以服务商为准。": "Default: 200 calls per round, including failed requests. At the limit, new requests stop; existing actions and player controls continue. This setting lasts until the current page session ends. Connection tests are counted separately and may cost money. Token totals include usage reported by successful replies, not the full bill. Check your provider for charges.",
    "导出当前局摘要、全部标记和最近 80 条动作事件。标记包含游戏时间和实际时间，在线版没有可追溯的服务器对局日志。不会附带 Key、接口地址、模型名称文本、跨局记忆或完整请求。文件只下载到本机，不自动上传。": "Export the run summary, all bookmarks and the last 80 action events. Bookmarks include game and wall times; the hosted version has no persistent server journal. Keys, endpoint and model text, cross-round memory and full requests are excluded. Downloads stay local; nothing is uploaded.",
    "导出当前局摘要、全部标记、沟通记录和最近 80 条动作事件。标记包含游戏时间和实际时间，在线版没有可追溯的服务器对局日志。不会附带 Key、接口地址、模型名称文本、跨局记忆或完整请求。文件只下载到本机，不自动上传。": "Export the run summary, all bookmarks, communication records and the last 80 action events. Bookmarks include game and wall times; the hosted version has no persistent server journal. Keys, endpoint and model text, cross-round memory and full requests are excluded. Downloads stay local; nothing is uploaded.",
    "浏览器直连模型": "Browser-direct model connection",
    "：在线版由浏览器直连模型；服务商必须允许跨域访问。跨域失败不会改由服务器代发 Key。": ": The hosted version calls your model directly from the browser. Your provider must allow CORS; a CORS failure never forwards your key through our server.",
    "目标达成": "Goal reached",
    "未达目标": "Goal not reached",
    "提前退出": "Ended early",
    "—": "—",
    "ChefJeff 厨房画面": "ChefJeff kitchen view",
    "Jeff 已达本局调用上限": "Jeff reached this round's call limit",
    "Jeff 暂时连不上，正在重试": "Jeff can't connect; retrying",
    "结束本局？": "End this round?",
    "本局会立即结算，当前进度不会保留。": "The round is scored now; its progress won't be kept.",
    "重新开局？": "Restart this round?",
    "当前这局会被放弃，并立即开始新的一局。": "This round will be abandoned and a new one starts right away.",
    "返回": "Back",
    "设置分页": "Settings tabs",
    "连接": "Connection",
    "协作记忆": "Memory",
    "调用上限": "Call limit",
    "导出": "Export",
    "费用与隐私说明": "Costs and privacy",
    "说明分页": "Controls tabs",
    "基础操作": "Basics",
    "规则细节": "Rule details",
    "关卡": "Levels",
    "空格": "Space",
    "+ 左键": "+ left click",
    "暂停与继续。": "Pause and resume.",
    "标记当前片段，导出本局时可以回看。": "Bookmark this moment to review it in the run export.",
    "告诉 Jeff 你更想做哪类工作；6 表示他做错了。": "Tell Jeff which work you prefer; 6 says he made a mistake.",
    "更换并测试": "Replace and test",
    "已保存；要更换时粘贴新的 Key": "Saved; paste a new key to replace it",
    "手里没有可以抛出的东西。": "You are not holding anything to throw.",
    "牛排练习厨房，180 游戏秒。取生牛肉 → 案板切好 → 下锅煎熟 → 装进干净盘 → 出餐。每 30 秒来一张牛排单，每份 ¥50；关店时净收入达到 ¥200 即达标。熟了之后 10 秒内出锅，否则会糊，再过 8 秒着火。": "A steak practice kitchen, 180 game seconds. Fetch raw beef → chop it on a board → cook it in a pot → plate it on a clean plate → serve. A steak order arrives every 30 seconds, ¥50 each; reach ¥200 net revenue by closing time. Take the pot off within 10 seconds of it being cooked or it burns; 8 seconds later it catches fire.",
    "面前没有可以切、洗或灭火的东西": "Nothing to chop, wash or extinguish in front of you",
    "按住移动，松开停止；方向键也可以。只用键盘操作厨房。": "Hold to move, release to stop; arrow keys work too. The kitchen is played with the keyboard only.",
    "移动 · WASD / 方向键": "Move · WASD / arrow keys",
    "按住方向键移动，松开停止；走开会停下切菜和洗碗，进度保留。厨房里不用鼠标，左下角沟通菜单可以点。": "Hold WASD or arrow keys to move; release to stop. Walking away stops chopping and washing; progress is kept. The kitchen needs no mouse; the communication menu can be clicked.",
    "本局记录": "Round record",
    "工作": "Work",
    "取食材": "Fetch ingredients",
    "下锅加热": "Put on to cook",
    "装盘与组装": "Plating and assembly",
    "刷碗": "Dishwashing",
    "收脏盘": "Collect dirty plates",
    "抛接传递": "Throws and catches",
    "灭火": "Put out fires",
    "丢弃与清锅": "Discard and clear",
    "已出餐": "Served",
    "送错": "Wrong dish",
    "拒收": "Refused",
    "抛出": "Thrown",
    "接住": "Caught",
    "丢弃食物": "Food discarded",
    "清理糊锅": "Burnt pot cleared",
    "倒掉锅里食物": "Pot emptied",
    "对出餐的贡献": "Share of served work",
    "返回结算": "Back to results",
    "按完成的动作计数；两人一起切的菜各记一次。": "Counts completed actions; food chopped together counts once for each chef.",
    "牛肉": "Beef",
    "牛排": "Steak",
    "平底锅": "Frying pan",
    "汤锅": "Soup pot",
    "锅具": "Cookware",
    "空平底锅": "Empty frying pan",
    "空汤锅": "Empty soup pot",
    "各自保留里面的食物": "contents stay where they are",
    "离灶不加热": "no heating off the stove",
    "切配进度保留；锅具继续加热": "prep progress kept; cookware keeps heating",
    "黄瓜": "Cucumber",
    "洋葱": "Onion",
    "奶酪": "Cheese",
    "葱": "Scallion",
    "鸡肉": "Chicken",
    "鱼": "Fish",
    "薄饼": "Flatbread",
    "面条": "Noodles",
    "生鸡肉": "Raw chicken",
    "切好的鸡肉": "Chopped chicken",
    "煎制中": "Frying",
    "熟鸡肉": "Cooked chicken",
    "糊鸡肉": "Burnt chicken",
    "生鱼": "Raw fish",
    "切好的鱼": "Chopped fish",
    "熟鱼": "Cooked fish",
    "糊鱼": "Burnt fish",
    "生面条": "Raw noodles",
    "煮制中": "Boiling",
    "熟面条": "Cooked noodles",
    "煮干了": "Boiled dry",
    "切好的葱": "Chopped scallion",
    "切好的黄瓜": "Chopped cucumber",
    "切好的洋葱": "Chopped onion",
    "切好的奶酪": "Sliced cheese",
    "牛肉拌面": "Beef noodles",
    "鸡肉拌面": "Chicken noodles",
    "沙拉": "Salad",
    "芝士汉堡": "Cheeseburger",
    "鸡肉卷": "Chicken wrap",
    "煎鱼排": "Fried fish",
    "葱箱": "Scallion supply",
    "黄瓜箱": "Cucumber supply",
    "洋葱箱": "Onion supply",
    "奶酪箱": "Cheese supply",
    "鱼箱": "Fish supply",
    "薄饼箱": "Flatbread supply",
    "面条箱": "Noodle supply",
    "鸡肉箱": "Chicken supply",
    "第四关 · 拌面（试玩）": "Level 4 · Mixed noodles (trial)",
    "单间厨房由横向长柜台分为上下工作区，右侧通道相连。180 游戏秒，每 40 秒来一张汉堡单，每份 ¥80；关店时净收入达到 ¥200 即达标。1 口平底锅、1 个灶台、2 只盘子、2 块案板；需要回收洗盘。食材和灶台在上、案板在下，可以隔着柜台传递。": "One kitchen split into upper and lower work areas by a long counter, joined on the right. 180 game seconds; a burger order arrives every 40 seconds, ¥80 each; reach ¥200 net revenue by closing time. 1 frying pan, 1 stove, 2 plates, 2 boards; plates must be returned and washed. Sources and the stove are above, boards below: pass food across the counter.",
    "两个灶台、三口平底锅，备用的空平底锅在右上柜台。面包直接装盘；生菜和番茄切好，牛肉切好后煎熟。可手持盘从案板或柜台收集切好蔬菜和面包，也能给队友手中盘加料。两盘无重复配料可合并：成品留手中，柜台留空盘。牛肉须先煎熟；缺料不能出餐。180 游戏秒，每 30 秒来一单牛排或汉堡（¥50／¥80），关店时净收入达到 ¥160 即达标。": "Two stoves and three frying pans; the spare pan is on the top-right counter. Bread needs no prep. Chop lettuce and tomato; chop and cook beef. Held plates can collect prepared ingredients from boards/counters. Add food to a teammate's plate, or merge two non-overlapping plates; the empty source plate stays in place. Beef must be cooked; incomplete dishes cannot be served. 180 game seconds; a steak or burger order (¥50/¥80) arrives every 30 seconds; reach ¥160 net revenue by closing time.",
    "贡献（标准时间）": "Contribution (standard time)",
    "拖延出餐": "Delayed serving",
    "空转": "Idle",
    "贡献：出了餐的菜里，每人做的步骤按标准时间计算的占比（配置里的切菜、拿放等操作时间，加搬运所需的最短走路；煎、煮不算给任何人）。": "Contribution: each chef's share of the standard time of the served dishes (the configured chopping, handling and other work, plus the shortest walk needed to carry things; cooking counts for no one).",
    "拖延：每道菜比理想做法晚出的秒数，按两人各自做到理想能省多少来分摊。空转：做了但没用上的动作（比如来回换手）和等待的时间；你自己走动看不出是否空转，所以你的空转只是下限。": "Delayed serving: how many seconds later than ideal each dish went out, split by how much each chef would have saved by working ideally. Idle: time on actions that were never used (such as swapping items back and forth) and waiting; your own walking cannot be told apart, so your idle time is a lower bound.",
    "这三项的算法还在试验，欢迎在 GitHub Issue 里告诉我们是否合理。": "These three measures are experimental; tell us in a GitHub issue whether they look right.",
    "冲刺：移动时按 Shift。起步 2 倍速，1 秒内回到正常速度，之后可以立即再冲。": "Dash: press Shift while moving. It starts at 2× speed and eases back to walking over 1 second; you can dash again right after.",
    "冲刺 · Shift": "Dash · Shift",
    "移动时按 Shift：起步 2 倍速，1 秒内平稳回到正常速度，结束后可以立即再冲。持物也能冲刺，不加速切菜或洗碗。AI 使用相同规则；没有单独开关。暂停时计时冻结。": "Press Shift while moving: it starts at 2× speed and eases back to walking over 1 second; you can dash again right after. Carrying is allowed. Chopping and washing stay at normal speed. The AI has the same rules; there is no separate toggle. Timers freeze while paused.",
    "标记片段 · Enter": "Bookmark · Enter",
    "营业中按 Enter 标记当前时刻，不暂停、不打断动作。相邻两次标记间隔不超过 5 个实际秒时合并为一个区间，长按不重复。设置中的“导出本局”包含全部标记；标记不会发送给 AI。": "Press Enter during gameplay to bookmark without pausing or interrupting actions. Consecutive marks up to 5 real seconds apart merge into one interval; holding the key does not repeat. Export Run in Settings includes all bookmarks. Bookmarks are not sent to the AI.",
    "数据导出": "Data export",
    "导出本次游玩的全部数据：从启动游戏起玩过的每一局，各含关卡、结果、贡献记录、全部标记、沟通记录和全部动作事件。标记包含游戏时间和实际时间，可对应本地日志提取前后过程。不会附带 Key、接口地址、模型名称文本、跨局记忆或完整请求。文件只下载到本机，不自动上传。": "Export all data from this play session: every round since the game started, each with its level, result, work record, all bookmarks, messages and every action event. Bookmarks include game time and wall-clock time, so you can find the surrounding moments in the local log. Keys, endpoints, model name text, cross-round memory and full requests are never included. The file downloads only to this device and is never uploaded automatically.",
    "导出本次游玩的数据：从打开本页面起最近 20 局，各含关卡、结果、贡献记录、全部标记、沟通记录和全部动作事件。标记包含游戏时间和实际时间，在线版没有可追溯的服务器对局日志。不会附带 Key、接口地址、模型名称文本、跨局记忆或完整请求。文件只下载到本机，不自动上传。": "Export data from this play session: the latest 20 rounds since this page opened, each with its level, result, work record, all bookmarks, messages and every action event. Bookmarks include game time and wall-clock time; the online version keeps no server run log to trace. Keys, endpoints, model name text, cross-round memory and full requests are never included. The file downloads only to this device and is never uploaded automatically.",
    "导出本次游玩": "Export This Play Session",
    "待导出的游玩数据": "Play data to export",
    "标记当前片段，数据导出时可以回看。": "Bookmark this moment to review it in the data export.",
    "营业中按 Enter 标记当前时刻，不暂停、不打断动作。相邻两次标记间隔不超过 5 个实际秒时合并为一个区间，长按不重复。设置中的“数据导出”包含全部标记；标记不会发送给 AI。": "Press Enter during gameplay to bookmark without pausing or interrupting actions. Consecutive marks up to 5 real seconds apart merge into one interval; holding the key does not repeat. Data export in Settings includes all bookmarks. Bookmarks are not sent to the AI.",
    "松开空格投掷 · 方向键改方向": "Release Space to throw · direction keys to aim",
    "手机操作": "Touch controls",
    "请将手机横过来": "Turn your phone to landscape",
    "横屏后点“继续经营”，厨房不会自动恢复。": "After rotating, tap Resume. The kitchen will stay paused.",
    "横屏游玩": "Play in landscape",
    "全屏": "Full screen",
    "菜单": "Menu",
    "操作": "Action",
    "移动": "Move",
    "松开投掷": "Release to throw",
    "松开操作": "Release to interact",
    "标记": "Bookmark",
    "厨房连接中…": "Connecting to the kitchen…",
    "连接已中断": "Connection lost",
    "点击设置连接自己的 AI 搭档": "Open Settings to connect your own AI partner",
    "扔": "Throw",
    "当前无法操作": "No action available",
    "手持": "Holding",
    "订单": "Orders",
    "放开摇杆后继续移动": "Release the joystick before moving again",
    "手机试玩": "Phone trial",
    "按住移动，松开停止；方向键也可以。电脑使用键盘，手机使用屏幕摇杆和按钮。": "Hold to move and release to stop; arrow keys also work. Use a keyboard on a computer, or the on-screen joystick and buttons on a phone.",
    "沟通": "Talk",
    "瞄准": "Aim",
    "选择模型服务。": "Select a model provider.",
    "请输入完整的 API Key。": "Enter a complete API key.",
    "请使用外部公开的 HTTPS 模型服务地址。": "Use an external public HTTPS model service.",
    "请输入服务商提供的模型名称。": "Enter the model name supplied by your provider.",
    "接口地址无效，请填写完整的 HTTPS 地址。": "Invalid base URL. Enter a complete HTTPS URL.",
    "模型回复过大。": "Model response is too large.",
    "模型返回了无效动作，未执行任何操作。": "Model returned an invalid action. No action was applied.",
    "模型请求超时或已取消。": "Model request timed out or was cancelled.",
    "浏览器无法访问模型服务，请检查网络和跨域支持；Key 不会通过我们的服务器转发。": "Browser could not reach this provider. Check network/CORS support; your key was not forwarded through our server.",
    "请结束本局后再更换 API。": "Finish the round before changing your connection.",
    "请先在当前浏览器连接模型服务。": "Connect your model in this browser first.",
    "厨房连接不可用，请刷新页面重新连接。": "Kitchen connection unavailable. Refresh to create a new session.",
    "厨房请求失败。": "Kitchen request failed.",
    "请求失败。": "Request failed.",
    "删除凭证无效，或记录已删除／过期。": "Receipt invalid, record already deleted, or expired.",
    "已删除贡献数据。": "Contribution deleted.",
    "删除凭证格式不正确，请粘贴完整的凭证。": "Invalid receipt format. Paste the complete deletion receipt.",
    "本局进行中，可以先填写；请结束本局后再测试或更换 API。": "You can fill in a draft during this round. Finish the round before testing or changing the API.",
    "等待厨房连接。可以先填写，连接成功后再测试。": "Waiting for the kitchen. You can fill in a draft and test once connected.",
    "尚未连接厨房，暂时不能测试 API。": "The kitchen is not connected yet. API testing is temporarily unavailable.",
    "正在测试连接…": "Testing connection…",
    "厨房暂时已满或请求过于频繁。请关闭其他试玩页面；空位释放后会自动重试。": "Kitchens are full or too many attempts were made. Close other trial pages; this page will retry automatically.",
    "暂时无法创建厨房，请稍后重试。": "Unable to create a kitchen. Please try again later.",
    "创建厨房超时，将自动重试。": "Creating the kitchen timed out. Retrying automatically.",
    "暂时无法连接厨房，请检查网络；页面会自动重试。": "Cannot connect to the kitchen. Check your network; this page will retry automatically.",
    "在线版：Key 默认只在页面内存中，仅发送给所选模型服务，刷新即清除；主动记住才以明文保存在浏览器 localStorage。游戏动作与状态经过我们的服务器，普通会话不写磁盘对局日志。自愿贡献数据另见下方说明。": "Online privacy: your key stays in page memory and is sent only to your model provider. Refresh clears it unless you choose Remember, which stores it unencrypted in browser localStorage. Game actions and state pass through our server; ordinary sessions create no disk journal. Optional contributions are described below.",
    "会保存": "Saved",
    "不会保存": "Never saved",
    "结算结果": "Results",
    "账号身份": "Account identity",
    "模型接口地址": "Provider URL",
    "预览数据": "Preview data",
    "贡献数据预览": "Contribution preview",
    "贡献已结束的本局": "Contribute finished round",
    "下载删除凭证": "Download deletion receipt",
    "删除已贡献数据": "Delete a contribution",
    "粘贴删除凭证；持有该凭证即可删除对应数据，请妥善保管。": "Paste your deletion receipt below. Keep it private; anyone with it can delete that record.",
    "删除凭证": "Deletion receipt",
    "删除该记录": "Delete contributed record",
    "保存期限": "Retention",
    "英语": "English",
    "切换到英文": "Switch to English",
    "未开启数据贡献。": "Contributions are not enabled.",
    "关闭厨房的请求不得包含额外字段。": "Empty close request required.",
    "创建厨房的请求不得包含额外字段。": "Empty session request required.",
    "请先明确同意数据用途和保存期限。": "Explicit consent is required.",
    "请结束本局后再贡献数据。": "Finish the round before contributing.",
    "请先结束当前对局。": "Finish this round first.",
    "连接状态无效。": "Invalid connection state.",
    "删除凭证无效。": "Invalid deletion receipt.",
    "游戏请求无效。": "Invalid game command.",
    "请求必须使用 JSON 格式。": "JSON required.",
    "厨房暂时已满，请稍后重试。": "Kitchens full. Please try again later.",
    "未找到页面或资源。": "Not found.",
    "请求来源不允许。": "Origin rejected.",
    "厨房会话已过期。": "Session expired.",
    "厨房会话已过期，请刷新页面。": "Session expired. Refresh this page.",
    "厨房会话已过期，请刷新页面创建新厨房。": "Session expired. Refresh to start a new kitchen.",
    "未知的接口。": "Unknown endpoint.",
    "请求包含不支持的字段。": "Unsupported request fields.",
    "调用上限必须为 1–2000。": "Use a limit from 1 to 2000.",
    "连接测试已取消。": "Connection cancelled.",
    "游戏接口无效。": "Invalid game endpoint.",
    "下一关": "Next level",
    "再来一次": "Try again",
    "本局结束后才能进入下一关。": "Finish this round before starting the next level.",
    "贡献数据请求超时，请重试。": "The contribution request timed out. Please try again.",
    "下一局请求已取消。": "The next-round request was cancelled.",
    "松手取消": "Release to cancel",
    "投掷": "Throw",
    "持有": "Holding",
    "取消": "Cancel",
    "等待空位": "Waiting for a spot",
    "厨房暂时已满": "The kitchen slots are full",
    "厨房名额暂时已满。空位释放后按钮会恢复，请再点击继续。": "All kitchen slots are in use. The button will become available when a spot opens; press it to continue.",
    "厨房名额暂时已满，空位释放后请再试。": "All kitchen slots are in use. Try again when a spot opens.",
    "操作过于频繁，请稍后重试。": "Too many requests. Please try again shortly.",
    "厨房请求较多，请稍后重试。": "The kitchen server is busy. Please try again shortly.",
    "同一网络的厨房已满": "Kitchens for your network are full",
    "同意通过试玩服务器调用 Jev": "I agree to call Jev through the demo server",
    "勾选后，Key 和模型请求会经 HTTPS 通过试玩服务器发送给 Jev，不写入服务器配置、日志或对局记录。未勾选则由浏览器直连，需 Jev 允许本网站跨域访问。": "When selected, your key and model requests pass through the demo server over HTTPS to Jev. They are not written to server configuration, logs or game records. Otherwise, your browser calls Jev directly, which requires Jev to allow this website through CORS.",
    "当前连接：已同意服务器转发 Jev": "Current connection: consented Jev server forwarding",
    "当前连接：浏览器直连模型": "Current connection: browser-direct model calls",
    "在线模型连接": "Online model connection",
    "：默认由浏览器直连模型，需供应商允许跨域访问。Jev 可明确勾选下方服务器转发；跨域失败不会自动改为转发。": ": Models are called directly from your browser by default and require provider CORS support. You can explicitly select Jev server forwarding below; a CORS failure never switches modes automatically.",
    "在线版：Key 默认在页面内存中，刷新即清除；主动记住会将 Key 和所选转发方式以明文保存在浏览器 localStorage。浏览器直连时 Key 只发给模型服务；明确勾选 Jev 转发后，Key 和模型请求经试玩服务器发送给 Jev，仅用于处理请求，不写入服务器配置、日志或对局记录。游戏状态经过我们的服务器，自愿贡献数据另见下方说明。": "Online privacy: keys stay in page memory by default and refresh clears them. Remember stores the key and selected transport unencrypted in browser localStorage. Direct mode sends the key only to your provider; explicitly selecting Jev forwarding sends your key and model requests through the demo server to Jev for request processing only, without writing them to server configuration, logs or game records. Game state passes through our server; optional contributions are described below.",
    "服务器转发仅适用于 Jev。": "Server forwarding is available only for Jev.",
    "Jev 转发连接失败。": "Jev forwarding failed.",
    "暂时无法连接试玩服务器，请检查网络后重试。": "Could not connect to the demo server. Check your network and try again.",
    "Jev 返回了无效动作，未执行任何操作。": "Jev returned an invalid action; no action was executed.",
    "Jev 回复过大。": "Jev response is too large.",
    "试玩服务器无法连接 Jev，请稍后重试。": "The demo server could not reach Jev. Please try again shortly.",
    "请先同意通过试玩服务器调用 Jev。": "Please first agree to call Jev through the demo server.",
    "Jev 请求无效。": "Invalid Jev request.",
    "此厨房的 Jev 请求仍在处理中。": "This kitchen still has a Jev request in progress.",
    "当前不能请求 Jev。": "Jev cannot be called in the current game state.",
    "连接测试过于频繁，请稍后重试。": "Connection tests are too frequent. Please try again shortly.",
    "Jev 决策请求已过期。": "The Jev decision request has expired.",
    "Jev 转发请求较多，请稍后重试。": "Jev forwarding is busy. Please try again shortly.",
    "浏览器无法直连 Jev。请检查网络，或明确勾选服务器转发后重试；Key 尚未经过试玩服务器。": "Your browser could not call Jev directly. Check your network, or explicitly select server forwarding and try again; your key has not passed through the demo server.",
    "勾选后，Key 和模型请求会经 HTTPS 通过试玩服务器发送给 Jev，不写入服务器配置、日志或对局记录。未勾选则由浏览器直连，需 Jev 允许本网站跨域访问。更改选项后须测试并连接才生效，清除配置会停止后续模型请求。": "When selected, your key and model requests pass through the demo server over HTTPS to Jev. They are not written to server configuration, logs or game records. Otherwise, your browser calls Jev directly, which requires Jev to allow this website through CORS. Changes take effect after Test and connect; Clear stops future model requests.",
    "浏览器无法直连 Jev。请检查网络，或明确勾选服务器转发后重试；本次直连请求未通过试玩服务器转发 Key。": "Your browser could not call Jev directly. Check your network, or explicitly select server forwarding and try again; this direct request did not forward your key through the demo server.",
    "浏览器无法访问模型服务，请检查网络和跨域支持；本次直连请求未通过试玩服务器转发 Key。": "Browser could not reach this provider. Check network/CORS support; this direct request did not forward your key through the demo server.",
    "游戏引擎事件": "Engine events",
    "IP 与账号身份": "IP address and account identity",
    "暂不": "Not now",
    "贡献对局数据": "Contribute rounds",
    "查看说明并更改选择": "Read the terms and change your choice",
    "不贡献时仅维持内存会话，闲置 10 分钟后清除；网络通信仍经过云服务商。删除凭证只保存在此浏览器，清理浏览器数据前请先下载备份。": "Without a contribution the session stays in memory only and is cleared after 10 idle minutes; traffic still passes through the cloud provider. Deletion receipts live only in this browser, so download a backup before clearing browser data.",
    "当前选择：尚未选择。": "Your choice: not made yet.",
    "自动贡献已开启。": "Automatic contribution is on.",
    "已选择暂不贡献，之后不会自动上传。": "Not now: nothing will be uploaded automatically.",
    "贡献本局": "Contribute this round",
    "已贡献": "Contributed",
    "正在贡献…": "Contributing…",
    "反馈": "Feedback",
    "遇到卡住、画面错位或其他问题时：": "If the chef gets stuck, the picture looks wrong or anything else goes awry:",
    "在 GitHub 报告问题 ↗": "Report a problem on GitHub ↗",
    "自愿参与。贡献的对局只用于改进游戏和人机协作的评估方法，不公开原始数据。": "Voluntary. Contributed rounds are used only to improve the game and to research how to evaluate human-AI cooperation. Raw data is never published.",
    "选择“暂不”时，也可以在结算画面点「贡献本局」只贡献这一局。": "With “Not now” you can still choose “Contribute this round” on a result card to contribute just that round.",
    "当前选择：暂不自动贡献。结算画面可点「贡献本局」只贡献这一局。": "Your choice: not now. A result card's “Contribute this round” contributes just that round.",
    "模型连接说明：支持的服务、一局约多少钱 ↗": "Model connection guide: supported services and rough cost per round ↗",
    "模型连接说明 ↗": "Model connection guide ↗",
    "隐私说明与反馈 ↗": "Privacy and contact ↗",
    "尽快打开「设置 → 数据与贡献」，点「导出本次游玩」，检查内容后下载 JSON 文件。文件含最近 30 秒的页面记录，导出越快越好。": "Soon afterwards, open Settings → Data and contributions, choose Export This Play Session, check the content and download the JSON file. It holds the last 30 seconds of page diagnostics, so the sooner the better.",
    "在 GitHub 新建 Issue，写下经过、用的设备和浏览器，并附上这个文件。": "Open a new GitHub issue describing what happened and your device and browser, and attach the file.",
    "导出文件不含 API Key、接口地址和模型回复，但包含浏览器型号和画面大小；公开发布前请再看一遍。": "The export holds no API key, endpoint or model replies, but does include your browser and screen size; look it over before posting it publicly.",
    "导出还附带本页最近 30 秒的页面记录（游戏时间、角色位置、按键方向、页面报错，以及浏览器型号和画面大小），用于排查卡住或显示问题；遇到问题后请尽快导出。": "The export also carries this page's last 30 seconds of diagnostics (game time, chef positions, held direction, page errors, plus browser and screen size) to help trace stuck or display problems; export soon after a problem.",
    "决策模型（直接给每个动作打分）": "Decision models (score every action directly)",
    "对话模型": "Chat models",
    "Decision 3.0（需本地部署，待接入）": "Decision 3.0 (self-hosted, not yet supported)",
    "阿里 qwen-flash": "Alibaba qwen-flash",
    "豆包 Seed 2.0 lite": "Doubao Seed 2.0 lite",
    "智谱 GLM-4.7-Flash（免费，接口繁忙）": "Zhipu GLM-4.7-Flash (free, often busy)",
    "决策模型 · 已实测整局": "Decision model · tested over a full round",
    "有免费额度（限速）· 需能访问 Google · 未实测": "Free quota (rate-limited) · needs access to Google · not yet tested",
    "免费，但高峰常返回“访问量过大”· 未实测": "Free, but often “too busy” at peak times · not yet tested",
    "自己填接口地址和模型名；会先长篇思考的模型可能答不完": "Enter the base URL and model yourself; models that think at length may not finish an answer",
    "OpenRouter 决策模型": "OpenRouter decision models",
    "可填 OpenRouter 上任一决策模型的 ID（默认 Microsoft-Decision-1，约 ¥0.3–0.7/局）· 已实测整局": "Any OpenRouter decision model ID works (default Microsoft-Decision-1, about ¥0.3–0.7 a round) · tested over a full round",
    "StartLux-Decision（Bamboo 存在延迟，免费接口）": "StartLux-Decision (Bamboo, noticeable latency, free API)",
    "本机决策模型（仅本地游戏）": "Decision model on this computer (local game only)",
    "填这台电脑上决策服务的完整地址，如 http://127.0.0.1:8090/v1/systemone · 不用 Key · 电脑算得慢时一次决策可能要几分钟": "Enter the full address of a decision service on this computer, such as http://127.0.0.1:8090/v1/systemone · No key needed · On a slow computer one decision can take minutes",
    "免费测试额度 · 请求经第三方中转 Bamboo Relay · 已关闭自动思考 · 未实测整局": "Free testing quota · requests pass through third-party Bamboo Relay · automatic thinking disabled · no full round tested",
    "OpenRouter 对话模型": "OpenRouter chat models",
    "填 OpenRouter 模型页上的 ID（形如 厂商/模型名）；会先长篇思考的模型可能答不完": "Enter the model ID from its OpenRouter page (vendor/model); models that think at length may not finish an answer",
    "Key 无效，请检查后重试。": "Invalid key. Check it and try again.",
    "账号余额不足，请到服务商充值。": "Not enough balance. Top up with the provider.",
    "账号无权访问这个模型。": "This account cannot use this model.",
    "请求受限或额度不足，请稍后重试。": "Rate limited or out of quota. Try again later.",
    "保留同一关卡最近 3 局的合作摘要：双方完成的工作、结果、沟通和有限事件片段。不同接口和模型分开保存；旧局偏好不代表你本局的分工。": "Keep summaries of the last 3 completed rounds on this level: work by both chefs, results, communication and sampled events. Services and models are separate; old preferences do not assign your role this round.",
    "在线版默认开启，摘要保存在当前浏览器；开局时固定本局使用的旧局摘要，随请求发给所选模型。Jev 转发也会处理这些摘要，但服务器不持久保存。可在这里关闭或清空；中途退出的局不保存。摘要会增加输入 token 和费用。": "Online memory is on by default and stored in this browser. Past summaries are fixed at round start and sent to your selected model. The Jev relay also processes them without persistent server storage. Disable or clear memory here; abandoned rounds are not saved. Summaries add input tokens and cost.",
    "浏览器无法保存记忆，暂时仅在本页使用。": "Browser storage is unavailable; memory is temporary in this page.",
    "跨局记录无法读取，已关闭记忆；可清空后重新启用。": "Past-round records could not be read. Memory is disabled; clear it before enabling it again.",
    "跨局记忆格式无效；请清空记忆后重试。": "Invalid past-round memory. Clear memory and try again.",
    "记忆开关与使用局数": "Memory setting and number of past rounds used",
    "全部操作输入：移动、位置、转向、按键和投掷，可原样重放整局": "Every input: movement, positions, turning, key presses and throws, enough to replay the whole round",
    "双方开始操作的时刻，以及投掷是否瞄准队友": "When each chef starts working, and whether a throw aims at the other chef",
    "每次给 Jeff 的请求的校验值，以及重建请求所需的最近决策和预设沟通消息（含发送时间）": "A digest of each request to Jeff, plus the recent decisions and preset messages (with send times) needed to rebuild it",
    "模型给出的各选项概率（如有）": "Option probabilities reported by the model, if any",
    "开启跨局记忆时，用到了哪几局（局号）及记忆内容的校验值": "With cross-round memory on, which earlier rounds it used (round IDs) and a digest of that memory",
    "本局记忆条件已经固定。": "Memory conditions are fixed for this round.",
    "本局记忆来源已经固定。": "The memory sources are fixed for this round.",
    "不贡献时，服务器仅维持内存会话，闲置 10 分钟后清除；跨局摘要另存在此浏览器。删除凭证也只存在此浏览器，清理网站数据前请先下载备份。": "Without contribution, the server keeps only an in-memory session, cleared after 10 idle minutes. Past-round summaries remain in this browser. Deletion receipts also stay here; download them before clearing site data.",
    "下载凭证无效。": "Invalid download receipt.",
    "下载最近一局贡献": "Download latest contribution",
    "关闭自动贡献未确认，请重试。": "Turning off automatic contribution was not confirmed. Please retry.",
    "初始局面、每秒状态变化与关键事件状态": "Initial state, changes each game second, and event states",
    "另同意收集浏览器自报的请求耗时及受控错误类型（可不选；不采集模型名或地址）": "Also collect browser-reported request duration and controlled error categories (optional; no model name or endpoint)",
    "同意字段无效。": "Invalid consent fields.",
    "实际地图、菜谱、规则、种子与版本": "Resolved map, recipes, rules, seeds and versions",
    "尚无可下载的贡献记录。": "No contribution is available to download.",
    "开局后可预览本局记录。": "Start a round to preview its record.",
    "未同意可选决策测量。": "Optional decision measurements were not consented to.",
    "物品、订单、工位、动作与决策关联": "Item, order, station, action and decision links",
    "自动贡献会在开局时创建私有记录；正常结束、手动结束、重开、关闭请求或闲置回收时更新。突然断电或进程崩溃可能只保留未完成的开局记录，不会推断退出原因。记录容量耗尽会明确标注丢失范围。": "Automatic contribution creates a private opening record and updates it on normal or manual endings, restart, close requests or idle removal. A power or process failure may leave an incomplete opening record; no exit motive is inferred. Capacity losses are explicitly marked.",
    "自动贡献需在下一局开始前确认。": "Confirm automatic contribution before the next round starts.",
    "记录不存在或凭证无效。": "The record does not exist or the receipt is invalid.",
    "请阅读并选择本版数据说明。": "Read and choose under the current data terms.",
    "贡献保存失败，请下载本局预览并稍后重试。": "Saving the contribution failed. Download the round preview and retry later.",
    "跨局记忆的内容（只记局号和校验值）": "Past-round memory content (only round IDs and a digest)",
    "结算结果与报告的 token 用量（非账单）": "Outcomes and reported token usage (not a bill)",
    "选择“暂不”时，也可以在结算画面点「贡献本局」只贡献这一局。没有开局前同意时，只含已有事实与首尾状态，不含操作记录，缺失过程会标注。": "After Not now, you can contribute that round on the results screen. Without pre-start consent, only existing facts and the first and last states are included, without the input record; the missing process is labelled.",
    "更多": "More",
    "不保存 API Key、IP 或账号身份。": "Does not store API keys, IP addresses or account identity.",
    "本局模型服务与模型 ID（含自定义模型，注明浏览器上报、未经独立核验）": "This round’s model service and ID, including custom models, marked browser-reported and not independently verified",
    "不另存完整 API 请求或响应。每次请求只保存校验值和重建它所需的少量内容，研究时用操作记录把原请求重建出来。开启跨局记忆时记下的局号，能把这个浏览器里的几局联系起来。": "Verbatim API requests and replies are not stored. Each request keeps only a digest and the few parts needed to rebuild it; researchers rebuild the original request from the recorded inputs. With cross-round memory on, the recorded round IDs link this browser's rounds to each other.",
    "另同意收集浏览器自报的请求耗时及受控错误类型（默认不选）": "Also allow browser-reported request timing and controlled error types (off by default)",
    "导出本次游玩的全部数据：从启动游戏起玩过的每一局，各含关卡、结果、贡献记录、全部标记、沟通记录和全部动作事件，并注明可用的模型服务与模型 ID。标记包含游戏时间和实际时间，可对应本地日志提取前后过程。不会附带 Key、接口地址、跨局记忆或完整请求。文件只下载到本机，不自动上传。": "Export every round played since opening the game, including its level, outcome, work record, bookmarks, communication and action events, with model service and ID where available. Bookmarks include game and wall time for matching local logs. No keys, endpoints, memory content or full requests are included. The file downloads locally and is not uploaded.",
    "导出本次游玩的数据：从打开本页面起最近 20 局，各含关卡、结果、贡献记录、全部标记、沟通记录和全部动作事件，并注明可用的模型服务与模型 ID。标记包含游戏时间和实际时间，在线版没有可追溯的服务器对局日志。不会附带 Key、接口地址、跨局记忆或完整请求。文件只下载到本机，不自动上传。": "Export the latest 20 rounds since opening this page: levels, results, work records, bookmarks, communication and action events, with model service and ID where available. Bookmarks include game and wall time. The online version has no persistent game journal. No keys, endpoints, memory content or full requests are included. The file downloads locally and is not uploaded.",
    "记录服务暂时不可用，请稍后重试。": "The records service is temporarily unavailable. Please retry later.",
    "删除暂未完成，请保留凭证并稍后重试。": "Deletion is not complete. Keep your receipt and retry later.",
    "已停止继续记录，服务器删除失败，请保留凭证并稍后重试。": "Further recording has stopped, but server deletion failed. Keep your receipt and retry later.",
    "免费 AI 搭档": "Free AI partner",
    "选择免费 AI 搭档": "Choose a free AI partner",
    "StartLux · Bamboo": "StartLux · Bamboo",
    "智谱 · GLM-4.7-Flash": "Zhipu · GLM-4.7-Flash",
    "模型与默认选择说明": "Models and default choice",
    "使用自己的模型 / 设置": "Use your own model / Settings",
    "正在选择…": "Selecting…",
    "已选择。返回厨房即可开局。": "Selected. Return to the kitchen to start.",
    "模型选择未完成，请刷新厨房状态后重试。": "Model selection failed. Refresh the kitchen status and try again.",
    "本局模型已固定；结算后可选择另一模型。": "The model is fixed for this round. Choose another after the results.",
    "当前连接：服务器提供的免费模型": "Connection: server-provided free model",
    "已选择免费模型，返回厨房即可开局。": "Free model selected. Return to the kitchen to start.",
    "服务器提供额度": "Server-provided allowance",
    "免费试玩": "Free trial",
    "智谱 GLM-4.7-Flash": "Zhipu GLM-4.7-Flash",
    "智谱开放平台": "Zhipu API platform",
    "默认使用 StartLux：它原生返回候选动作及选项概率，便于观察决策；你也可以切换智谱进行比较。": "StartLux is the default because it natively returns candidate actions and option probabilities for inspecting decisions. You can also compare it with Zhipu.",
    "默认使用智谱 GLM-4.7-Flash：它通过通用对话接口生成动作；你也可以切换 StartLux 比较不同决策方式。": "Zhipu GLM-4.7-Flash is the default. It generates actions through a general chat API; switch to StartLux to compare decision methods.",
    "免费试玩由服务器提供调用额度，无需填写 Key；每局最多 200 次请求。开局前选择，本局固定。研究数据贡献由你单独选择。": "The server provides free trial calls; no Key is needed. Up to 200 requests per round. Choose before starting; the model stays fixed for the round. Research contribution is a separate choice.",
    "请选择开放的免费模型。": "Choose an available free model.",
    "免费模型暂不可用。": "The free model is temporarily unavailable.",
    "免费试玩暂未开放，请使用自己的模型配置。": "Free trials are not enabled. Use your own model configuration.",
    "厨房已更新，请刷新状态。": "The kitchen has changed. Refresh its status.",
    "本局模型已固定，请结算后切换。": "The model is fixed for this round. Switch after the results.",
    "免费试玩暂未开放。": "Free trials are not enabled.",
    "免费模型请求无效。": "Invalid free model request.",
    "当前模型请求仍在处理中。": "The current model request is still being processed.",
    "本局模型或对局状态已经改变。": "The round or its model has changed.",
    "模型决策请求已过期。": "The model decision request has expired.",
    "跨局记忆格式无效。": "Invalid cross-round memory format.",
    "本局免费模型调用已达 200 次上限。": "This round reached its limit of 200 free model calls.",
    "免费试玩请求较多，请稍后再试。": "Free trials are busy. Try again later.",
    "所选免费模型暂不可用，请稍后再试。": "The selected free model is temporarily unavailable. Try again later.",
    "所选免费模型正在服务其他厨房，请稍后再试。": "The selected free model is serving another kitchen. Try again later.",
    "所选免费模型暂不可用，请稍后再试；结算后可切换其他模型。": "The selected free model is temporarily unavailable. Try again later, or switch models after this round.",
    "免费模型连接超时或不可用，请稍后再试。": "The free model timed out or is unavailable. Try again later.",
    "免费模型回复过大，本次未执行。": "The free model reply was too large. No action was executed.",
    "免费模型回复不符合预期，本次未执行。": "The free model returned an unexpected response. No action was applied.",
    "StartLux 回复格式或动作无效，本次未执行。": "StartLux returned an invalid response or action. No action was executed.",
    "智谱回复格式或动作无效，本次未执行。": "Zhipu returned an invalid response or action. No action was executed.",
    "模型说明": "Model details",
    "请先取得当前模型的免费厨房名额。": "Acquire a free kitchen seat for this model before starting.",
    "正在申请免费名额，请稍候。": "Requesting a free place. Please wait.",
    "这个模型的免费厨房名额已满，请稍后开局或使用自己的模型。": "All free kitchen places for this model are occupied. Try later or use your own model.",
    "所选免费模型仍在处理请求，请稍后再试。": "The selected free model is still processing a request. Please try again later.",
    "本局免费名额已释放，请尝试继续；满额时需等待或结束本局。": "Your free place was released. Try resuming; if full, wait or end this round.",
    "免费服务已重启，请结束本局后重新开局。": "The free service restarted. End this round and start a new one.",
    "所选免费模型暂不可用，恢复确认后才能继续提供试玩。": "The selected free model is unavailable pending a recovery check.",
    "所选免费模型正在冷却，请稍后再试。": "The selected free model is cooling down. Please try again later.",
    "免费试玩调用预算已用完，请稍后再来或使用自己的模型。": "The free trial call budget is exhausted. Return later or use your own model.",
    "免费试玩预算服务暂不可用，本次未发起模型请求。": "The free trial budget service is unavailable. No model request was sent.",
    "免费模型协调服务暂不可用，请稍后再试。": "The shared free model service is unavailable. Please try again later.",
    " · 可用": " · Available",
    " · 名额已满": " · Full",
    " · 暂不可用": " · Unavailable",
    "免费模型暂时无法连接，请稍后再试。": "The free model is temporarily unreachable. Please try again later.",
    "模型平台过载，等待冷却后再试。": "The model provider is overloaded. Waiting for its cooldown.",
    "模型平台限流，等待冷却后再试。": "The model provider is rate limiting requests. Waiting for its cooldown.",
    "模型服务鉴权失败，免费调用已暂停。": "Model authentication failed. Free calls are paused.",
    "模型返回的动作或格式无效，稍后重新请求。": "The model returned an invalid action or format. Retrying shortly.",
    "模型平台拒绝请求，稍后再试。": "The model provider rejected the request. Retrying shortly.",
    "模型请求结果未知，免费调用已暂停，请结算后更换模型。": "The request outcome is unknown. Free calls are paused. Choose another model after this round.",
    "模型返回型号不符，免费调用已暂停。": "The returned model does not match. Free calls are paused.",
    "正在重新请求。": "Requesting again.",
    "免费模型返回格式或动作无效，本次未执行。": "The free model returned an invalid format or action. Nothing was executed.",
    "本局免费名额已释放，请结束本局后重新开局。": "This round’s free seat was released. End the round and start again.",
    "AI 搭档": "AI teammate",
    "跨局记忆": "Cross-round memory",
    "数据与贡献": "Data and contributions",
    "声音与语言": "Sound and language",
    "当前搭档": "Current teammate",
    "改完直接返回，下一局生效": "Changes apply from the next round",
    "← 返回": "← Back",
    "自定义模型": "Custom model",
    "自定义模型（API Key）": "Custom model (API key)",
    "自定义模型说明": "About custom models",
    "改用自定义模型（API Key）": "Use a custom model (API key) instead",
    "显示": "Show",
    "隐藏": "Hide",
    "也可以填自己申请的免费 Key：智谱 GLM-4.7-Flash、StartLux（Bamboo）等平台都提供免费额度，申请后选对应的服务填进来即可。": "You can also use a free key of your own: Zhipu GLM-4.7-Flash, StartLux (Bamboo) and similar platforms offer free quotas. Apply, then choose that service here and paste the key.",
    "也可以填自己申请的免费 Key：智谱 GLM-4.7-Flash、StartLux（Bamboo）等平台都提供免费额度，申请后选对应的服务填进来即可，不占免费模型的名额。": "You can also use a free key of your own: Zhipu GLM-4.7-Flash, StartLux (Bamboo) and similar platforms offer free quotas. Apply, then choose that service here and paste the key. It does not use a free-model seat.",
    "怎么申请、一局大约多少钱 →": "How to apply, and what a round costs →",
    "还没有 Key？": "No key yet?",
    "智谱 GLM-4.7-Flash、StartLux（Bamboo）等平台提供免费额度，自己申请一个就能填在这里。": "Zhipu GLM-4.7-Flash, StartLux (Bamboo) and similar platforms offer free quotas. Apply for a key and paste it here.",
    "智谱 GLM-4.7-Flash、StartLux（Bamboo）等平台提供免费额度，自己申请一个就能填在这里，不占免费模型的名额。": "Zhipu GLM-4.7-Flash, StartLux (Bamboo) and similar platforms offer free quotas. Apply for a key and paste it here. It does not use a free-model seat.",
    "DeepSeek、OpenRouter 等按用量付费，一局大约几毛到几块钱。": "DeepSeek, OpenRouter and similar services charge by usage, from under ¥1 to a few yuan per round.",
    "两类模型": "Two kinds of model",
    "决策模型": "Decision models",
    "快思考模型": "Fast-thinking models",
    "：直接从候选动作里选一个，还会给出每个选项的概率。": ": pick one of the candidate actions directly and give a probability for every option.",
    "：通用对话模型，读完厨房状态后回一个动作。": ": general chat models that read the kitchen state and reply with one action.",
    "调用按你在服务商那边的账号计费，或计入你的免费额度。Key 不会写进游戏记录或研究数据。": "Calls are billed to your account with the provider or count against your free quota. The key never goes into game records or research data.",
    "Key 默认只留在这个页面，由浏览器直接发给服务商；费用记在你的账号上。": "By default the key stays in this page and your browser sends it straight to the provider. Costs go to your account.",
    "记住此设备（Key 以明文保存在这个浏览器）": "Remember on this device (the key is stored as plain text in this browser)",
    "支持 Jev、DeepSeek、OpenRouter 等决策模型与快思考模型": "Decision and fast-thinking models such as Jev, DeepSeek and OpenRouter",
    "免费模型": "Free models",
    "免费": "Free",
    "免费模型不用 API Key，但名额有限": "Free models need no API key, but seats are limited",
    "不用 API Key。可以换着试，看看哪个更合拍。": "No API key needed. Try them in turn and see which one works best with you.",
    "使用限制": "Limits",
    "免费模型的使用限制": "Free model limits",
    "免费使用限制": "Free-use limits",
    "每个免费模型同一时间只能一位玩家使用，国内站和海外站共用这个名额。": "Each free model serves one player at a time, and the China and international sites share that seat.",
    "名额满了不排队：可以稍后再试，或者换另一个免费模型。": "There is no queue when the seat is taken: try again later, or pick another free model.",
    "不想等名额，可以自己去智谱、Bamboo 等平台申请免费的 API Key，填在“自定义模型”里使用。这样不占这里的名额，限额按你在服务商那边的账号算。": "If you would rather not wait, apply for a free API key on Zhipu, Bamboo or a similar platform and enter it under “Custom model”. It does not take a seat here, and its limits follow your account with that provider.",
    "开局时固定本局的模型，结算后才能换。": "The model is fixed when a round starts and can be changed after the results.",
    "列表由服务器提供，新接入的免费模型会直接出现在这里。": "The server provides this list; newly added free models appear here automatically.",
    "● 有空位": "● Seat available",
    "● 名额已满，稍后再试": "● Seat taken, try again later",
    "○ 暂不可用": "○ Unavailable for now",
    "● 已连接": "● Connected",
    "未连接": "Not connected",
    "StartLux 决策模型": "StartLux decision model",
    "选一位 AI 搭档": "Pick an AI teammate",
    "全部关卡": "All levels",
    "本局分析": "Round analysis",
    "换一位搭档": "Change teammate",
    "今天配合得不错！": "Great teamwork today!",
    "关店结算": "Closing time",
    "★ 达成目标": "★ Goal reached",
    "上一关": "Previous level",
    "（免费）": " (free)",
    "请先选一位 AI 搭档，再开始经营。": "Pick an AI teammate before you start.",
    "Enter 开始 · ← → 换关卡": "Enter Start · ← → Change level",
    "Enter 下一关 · R 再来一次 · L 全部关卡": "Enter Next level · R Try again · L All levels",
    "Enter 再来一次 · N 下一关 · L 全部关卡": "Enter Try again · N Next level · L All levels",
    "Enter 全部关卡 · R 再来一次": "Enter All levels · R Try again",
    "Enter 再来一次 · L 全部关卡": "Enter Try again · L All levels",
    "还没玩过": "Not played yet",
    "创建关卡": "Create a level",
    "有空位": "Seat available",
    "名额已满": "Seat taken",
    "暂不可用": "Unavailable",
    "做自己的地图和菜谱": "Make your own maps and recipes",
    "即将开放": "Coming soon",
    "○ 今日额度已用完": "○ Used up for today",
    "今日已用完": "Used up today",
    "全站每小时、每天的免费请求总数也有上限。某个模型今天的额度用完后，会显示“今日额度已用完”，第二天恢复。": "The whole site also caps free requests per hour and per day. When a model’s allowance for today is spent, it shows “Used up for today” and comes back the next day.",
    "这个免费模型今天的额度已经用完，明天再来，或换一个模型。": "This free model has used up today’s allowance. Come back tomorrow, or pick another model.",
    "这个免费模型每分钟能请求的次数有限，Jeff 会慢一点。": "This free model allows only a few requests a minute, so Jeff will be a little slower.",
    "默认使用 StartLux：它原生返回候选动作及选项概率，便于观察决策；你也可以切换其他免费模型比较。": "StartLux is the default: it returns the candidate actions with their probabilities, which makes decisions easy to follow. You can switch to another free model to compare.",
    "默认使用智谱 GLM-4.7-Flash：它通过通用对话接口生成动作；你也可以切换其他免费模型比较不同决策方式。": "Zhipu GLM-4.7-Flash is the default: it picks actions through a general chat interface. You can switch to another free model to compare.",
    "Gemma 4 26B": "Gemma 4 26B",
    "Llama 3.1 8B": "Llama 3.1 8B",
    "：默认由浏览器直连模型，需供应商允许跨域访问。Jev 可明确勾选下方服务器转发，Cloudflare 只能经服务器转发；跨域失败不会自动改为转发。": ": Models are called directly from your browser by default and require provider CORS support. You can explicitly select Jev server forwarding below; Cloudflare only works through server forwarding. A CORS failure never switches to forwarding automatically.",
    "默认由浏览器直连模型，需供应商允许跨域访问。Jev 可明确勾选下方服务器转发，Cloudflare 只能经服务器转发；跨域失败不会自动改为转发。": "Models are called directly from your browser by default and require provider CORS support. You can explicitly select Jev server forwarding below; Cloudflare only works through server forwarding. A CORS failure never switches to forwarding automatically.",
    "32 位 Account ID": "32-character account ID",
    "同意通过试玩服务器转发 Cloudflare 请求（Cloudflare 不支持浏览器直连）": "I agree to forward Cloudflare requests through the demo server (Cloudflare does not accept browser requests)",
    "勾选后，Key、Account ID 和模型请求会经 HTTPS 通过试玩服务器发送给 Cloudflare，不写入服务器配置、日志或对局记录。在线转发只支持 Gemma 4 26B 和 Llama 3.1 8B。": "When selected, your key, account ID and model requests pass through the demo server over HTTPS to Cloudflare. They are not written to server configuration, logs or round records. Online forwarding supports Gemma 4 26B and Llama 3.1 8B only.",
    "请填写 32 位的 Account ID（在服务商控制台里可以找到）。": "Enter the 32-character account ID (you can find it in the provider’s dashboard).",
    "在线转发只支持 Gemma 4 26B 和 Llama 3.1 8B。": "Online forwarding supports Gemma 4 26B and Llama 3.1 8B only.",
    "请先同意通过试玩服务器调用 Cloudflare。": "Please first agree to call Cloudflare through the demo server.",
    "当前连接：已同意服务器转发 Cloudflare": "Current connection: Cloudflare server forwarding accepted",
    "Cloudflare 回复过大。": "Cloudflare reply too large.",
    "试玩服务器无法连接 Cloudflare，请稍后重试。": "The demo server cannot reach Cloudflare. Try again later.",
    "Google AI Studio 免费层级：每分钟 15 次、每天 500 次 · 需能访问 Google · 合成快照单次实测": "Google AI Studio free tier: 15 requests a minute, 500 a day · needs access to Google · probed once with a synthetic snapshot",
    "Cloudflare Workers AI（Gemma 4 / Llama 3.1）": "Cloudflare Workers AI (Gemma 4 / Llama 3.1)",
    "免费额度每个账户每天 10,000 Neurons，约 100–140 次请求 · 也可填 @cf/meta/llama-3.1-8b-instruct-fp8 · 合成快照单次实测": "Free tier: 10,000 Neurons a day per account, about 100–140 requests · you can also enter @cf/meta/llama-3.1-8b-instruct-fp8 · probed once with a synthetic snapshot",
    "Gemini 3.5 Flash-Lite": "Gemini 3.5 Flash-Lite",
    "在线版：Key 默认在页面内存中，刷新即清除；主动记住会将 Key 和所选转发方式以明文保存在浏览器 localStorage。浏览器直连时 Key 只发给模型服务；明确勾选 Jev 或 Cloudflare 转发后，Key（Cloudflare 还有 Account ID）和模型请求经试玩服务器发送给对应服务，仅用于处理请求，不写入服务器配置、日志或对局记录。游戏状态经过我们的服务器，自愿贡献数据另见下方说明。": "Online: your key stays in this page’s memory by default and is cleared on refresh; choosing Remember stores the key and the chosen forwarding in this browser’s localStorage as plain text. With direct browser calls the key goes only to the model service; after you explicitly tick Jev or Cloudflare forwarding, the key (and for Cloudflare the account ID) and model requests pass through the demo server to that service, are used only to handle the request, and are not written to server configuration, logs or round records. Game state passes through our server; voluntary data contributions are described below.",
    "可填 OpenRouter 上任一决策模型的 ID（默认 Microsoft-Decision-1，约 ¥0.3–0.7/局）": "Enter any OpenRouter decision model ID (default Microsoft-Decision-1, about ¥0.3–0.7 a round)",
    "免费测试额度 · 请求经第三方中转 Bamboo Relay · 已关闭自动思考": "Free test quota · requests go through the third-party Bamboo Relay · automatic thinking off",
    "约 ¥1–3/局": "about ¥1–3 a round",
    "约 ¥0.2–0.3/局": "about ¥0.2–0.3 a round",
    "约 ¥0.7–1.3/局": "about ¥0.7–1.3 a round",
    "Google AI Studio 免费层级：每分钟 15 次、每天 500 次 · Jeff 每分钟常要问超过 15 次，超出时要等一会儿才能再问 · 需能访问 Google": "Google AI Studio free tier: 15 requests a minute, 500 a day · Jeff often asks more than 15 times a minute, and past the limit he has to wait before asking again · needs access to Google",
    "免费额度每个账户每天 10,000 Neurons，约 100–140 次请求 · 也可填 @cf/meta/llama-3.1-8b-instruct-fp8": "Free tier: 10,000 Neurons a day per account, about 100–140 requests · you can also enter @cf/meta/llama-3.1-8b-instruct-fp8",
    "免费，但高峰常返回“访问量过大”": "Free, but often answers “too many requests” at peak times",
    "请优先选择快思考模型": "Prefer a fast-thinking model",
    "没有校准好的这张关卡。": "This level has not been calibrated.",
    "这张关卡算下来不能玩。": "Calibration found that this level cannot be played.",
    "校准服务已停止。": "Level calibration has stopped.",
    "上一张关卡还在计算，请等它算完。": "Your previous level is still being calibrated; wait until it finishes.",
    "校准排队已满，请稍后再试。": "The calibration queue is full; try again later.",
    "没有这项校准。": "No such calibration.",
    "校准超时，请简化关卡后再试。": "Calibration took too long; simplify the level and try again.",
    "校准出错，请稍后再试。": "Calibration failed; try again later.",
    "墙": "Wall",
    "食材箱": "Ingredient box",
    "在案板上切好": "Chopped on a board",
    "直接放进盘子": "Goes straight onto the plate",
    "新关卡": "New level",
    "新菜": "New dish",
    "地板被柜台隔成了两块：两位厨师各站一边，隔着柜台扔东西": "Counters split the floor in two: each chef works one side and food is thrown over the counters",
    "菜单上至少要有 1 道菜": "The menu needs at least 1 dish",
    "编辑步骤": "Editing steps",
    "1 厨房布局": "1 Kitchen",
    "2 菜单": "2 Menu",
    "3 校准与试玩": "3 Calibrate and play",
    "关卡名字": "Level name",
    "← 我的关卡": "← My levels",
    "编辑关卡": "Edit level",
    "校准中": "Calibrating",
    "脚本厨师正在试做": "The scripted chefs are test-cooking",
    "算完会自动更新，可以先去玩别的关卡": "It updates by itself when done; play another level meanwhile",
    "草稿": "Draft",
    "补齐以后才能提交校准": "Complete it before submitting for calibration",
    "继续编辑": "Keep editing",
    "待校准": "Not calibrated",
    "设计好了，还没交给服务器计算": "Ready, not yet sent to the server",
    "在第 3 步提交校准": "Submit it in step 3",
    "可以玩": "Playable",
    "提示：一个人也能过": "Note: one player can pass it alone",
    "需要两个人配合，一个人过不了": "Needs both chefs; one alone cannot pass",
    "不能玩": "Not playable",
    "两个脚本厨师一道菜都没做出来": "The two scripted chefs served no dish",
    "常见原因：案板或灶台被围住，人站不到跟前": "Usually a board or stove is boxed in, with nowhere to stand",
    "回去修改": "Back to editing",
    "服务器的检查没通过": "The server's check failed",
    "打开第 3 步看具体原因": "Open step 3 for the reasons",
    "我的关卡": "My levels",
    "导入关卡文件": "Import a level file",
    "+ 新建关卡": "+ New level",
    "自己摆厨房、配菜，服务器算出订单节奏和目标以后就能开局。关卡只保存在这个浏览器里，换电脑或发给朋友，先导出成文件。": "Lay out a kitchen and a menu; once the server works out the order pace and the target, you can play it. Levels are kept in this browser only: to move one to another computer or send it to a friend, export it as a file first.",
    "这个浏览器不让网页保存数据，关卡关掉页面就没了。请先导出成文件。": "This browser does not let the page save data, so levels go when the page closes. Export them as files first.",
    "未命名": "Untitled",
    "编辑": "Edit",
    "确定删除？": "Delete it?",
    "删除": "Delete",
    "新建关卡": "New level",
    "从一间摆好基本设备的示例厨房开始": "Starts from a sample kitchen with the basic stations",
    "手机上可以玩已经做好的关卡；编辑关卡请用电脑浏览器。": "On a phone you can play finished levels; edit levels in a computer browser.",
    "编辑器只在电脑浏览器里打开；手机上可以玩已经做好的关卡。": "The editor opens in a computer browser only; on a phone you can play finished levels.",
    "这个文件不是关卡文件，没有导入。": "This file is not a level file; nothing was imported.",
    "导入好了。": "Imported.",
    "工具": "Tools",
    "食材箱里放什么": "What the box holds",
    "擦除": "Erase",
    "房间大小": "Room size",
    "厨房格子": "Kitchen grid",
    "下一步：菜单 →": "Next: Menu →",
    "，跟前没有地方站": ", nowhere to stand in front",
    "外墙": "Outer wall",
    "地板": "Floor",
    "检查": "Checks",
    "可以进入下一步": "Ready for the next step",
    "设备齐了，每台设备跟前都能站人": "All stations are there and each can be reached",
    "+ 加一道菜": "+ Add a dish",
    "菜名": "Dish name",
    "删掉这道菜": "Remove this dish",
    "去掉这样配料": "Remove this ingredient",
    "+ 加一样配料": "+ Add an ingredient",
    "售价": "Price",
    "用建议价": "Use the suggested price",
    "Jeff 看到的名字": "The name Jeff reads",
    "Jeff 读不到你起的菜名，只看到英文配料。": "Jeff never reads your dish name, only its ingredients in English.",
    "顾客能等多久": "How long customers wait",
    "这份菜单要的设备": "Stations this menu needs",
    "← 厨房布局": "← Kitchen",
    "下一步：校准 →": "Next: Calibrate →",
    "回第 1 步把缺的摆上": "Place the missing ones in step 1",
    "厨房": "Kitchen",
    "顾客": "Customers",
    "盘子": "Plates",
    "一局": "A round",
    "要交给服务器的关卡": "The level you send to the server",
    "重新校准": "Calibrate again",
    "提交校准": "Submit for calibration",
    "同一份设计算过一次就记住了，再交会立刻出结果。": "The server remembers a design it has calibrated, so sending it again answers at once.",
    "回厨房布局": "Back to the kitchen",
    "回菜单": "Back to the menu",
    "排队中": "Queued",
    "服务器一次只算一张关卡，前面的算完就轮到这张。": "The server calibrates one level at a time; this one is next after those ahead of it.",
    "每个页面同时只能排一张；排队的关卡多了，会请你稍后再交。": "Each page can queue one level at a time; when the queue is full you will be asked to try later.",
    "计算中": "Calculating",
    "算的时候可以离开这一页，回到「我的关卡」也能看到进度。": "You can leave this page while it runs; My levels shows the progress too.",
    "没交上去": "Not sent",
    "服务器没收下这张关卡": "The server did not take this level",
    "目标": "Target",
    "关店时净收入达到就算过关": "Reach it in net income by closing time to pass",
    "两个脚本厨师": "Two scripted chefs",
    "一个脚本厨师": "One scripted chef",
    "能达到目标": "reaches the target",
    "达不到目标": "misses the target",
    "一个人也能达到目标，照样可以玩。想让两个人非得配合，可以少放一块案板，或把食材箱和灶台拉远一些，再交一次。": "One chef alone reaches the target, and the level is still playable. To make teamwork necessary, use one board fewer or move the boxes and stoves further apart, then send it again.",
    "脚本厨师只是用来定目标的参照，不代表真人和 Jeff 能打多少分。": "The scripted chefs only set the target; they do not predict what you and Jeff will score.",
    "这张关卡还玩不了": "This level cannot be played yet",
    "最常见的原因：案板或灶台被柜台围住，人站不到跟前；或者出餐口离厨房太远。": "Most often a board or stove is boxed in by counters with nowhere to stand, or the serving window is too far from the kitchen.",
    "第 1 步的检查会标出“跟前没有地方站”的设备。": "The checks in step 1 mark stations with nowhere to stand in front.",
    "还没校准": "Not calibrated yet",
    "交上去以后，服务器先当场检查一遍：价格对不对、菜在这张地图上做不做得出来。检查通过才会排队计算。": "The server first checks it at once: are the prices right, can each dish be made on this map? Only then does it queue the calculation.",
    "墙把厨房隔开了，两边没法传递东西": "Walls cut the kitchen in two, so nothing can pass between the sides",
    "有设备跟前没有地方站": "A station has nowhere to stand in front of it",
    "水槽、脏盘回收、灭火器架要各有 1 个，出餐口 1 到 2 个": "One sink, one plate return and one extinguisher rack, and 1 or 2 serving windows",
    "柜台不够放开局的盘子": "Not enough counters for the starting plates",
    "柜台隔开的两块地板离得太远，东西扔不过去": "The two parts of the floor are too far apart to throw food across",
    "有菜的价格超出了范围": "A price is out of range",
    "有两道菜的配料一样": "Two dishes have the same ingredients",
    "地图不成立": "The map is not valid",
    "服务器暂时不能校准，请稍后再试。": "The server cannot calibrate right now; please try later.",
    "计算出错了，请再交一次。": "The calculation failed; please send it again.",
    "和服务器的连接断了，请再交一次。": "The connection to the server dropped; please send it again.",
    "这一局结束以后才能换关卡。": "You can change the level after this round ends.",
    "这张关卡要重新校准，请到第 3 步再交一次。": "This level needs calibrating again; send it again in step 3.",
    "没能换到这张关卡。": "Could not switch to this level.",
    "厨房还没连上，请稍等再试。": "The kitchen is not connected yet; try again in a moment.",
    "出餐口和脏盘回收要贴着外墙摆": "Serving windows and the plate return go against the outer wall",
    "按住拖动能连续摆；在同种设备上再点一下就擦掉；选「擦除」能拖着成片擦。外圈是墙，不能放东西；出餐口和脏盘回收只能贴着外墙摆。里面也可以画墙。": "Drag to place in a row; click a station of the kind you hold again to remove it; with Erase, drag to clear an area. The outer wall is wall and holds nothing; serving windows and the plate return go only against it. You can draw walls inside too.",
    "自制关卡": "My level",
    "编辑这张关卡": "Edit this level",
    "一个人也能过": "one player can pass",
    "需要两个人配合": "needs both chefs",
    "Enter 开始": "Enter Start",
    "测试": "Test",
    "测试功能，不是正式玩法，以后可能调整。": "A test feature, not part of the regular game; it may change.",
    "沟通 · 1–6 / 点击（测试功能）": "Communicate · 1–6 / Click (test feature)",
    "这是测试中的功能，不是正式玩法，以后可能调整。打开左下角沟通菜单，点击偏好即可发送；“你做错了”是独立的红色描边按钮。也可按 1–5 表达偏好、按 6 纠错。共用 5 个实际秒冷却，暂停时也可发送。最新偏好只在本局有效；AI 在下一次正常请求中收到，自行判断如何配合，不强制分工或停止动作。纠错附带当时动作信息，但不指定正确答案。": "This is a test feature, not part of the regular game; it may change. Click a preference in the bottom-left menu, or the separate red-outlined correction button. Shortcuts: 1–5 for preferences, 6 for correction. All share a 5-real-second cooldown; messages also work while paused. The latest preference applies only to this round. The AI receives it in its next regular request and decides how to cooperate; jobs and roles are not forced. Corrections include action context, not a prescribed solution.",
    "这是测试中的功能，不是正式玩法，以后可能调整。打开左下角沟通菜单，点击即可告诉 AI 由你来做哪类工作；“你做错了”是独立的红色描边按钮。也可按 1–5 说明分工、按 6 纠错。共用 5 个实际秒冷却，暂停时也可发送。最新的说明只在本局有效；AI 在下一次正常请求中收到，自行判断如何配合，不强制分工或停止动作。纠错附带当时动作信息，但不指定正确答案。": "This is a test feature, not part of the regular game; it may change. In the bottom-left menu, click to tell the AI which work you will do, or use the separate red-outlined correction button. Shortcuts: 1–5 to say who does what, 6 for correction. All share a 5-real-second cooldown; messages also work while paused. The latest message applies only to this round. The AI receives it in its next regular request and decides how to cooperate; jobs and roles are not forced. Corrections include action context, not a prescribed solution.",
    "我来备菜": "I'll prep ingredients",
    "我来烹饪": "I'll cook",
    "我来摆盘": "I'll plate",
    "我来传菜": "I'll carry / serve",
    "我来洗盘子": "I'll wash dishes",
    "还没说分工": "No split said yet",
    "玩自制关卡时：这张关卡的完整设计，包括你起的关卡名和菜名": "When you play a level you made: its full design, including the level and dish names you gave it",
    "厨房里能做": "The kitchen can make",
    "厨房里还做不了": "Not yet in this kitchen",
    "这里只能选厨房里做得出来的食材。一样食材要有它的食材箱，要切的还得有案板，要下锅的还得有对应的灶台。想用别的食材，先回第 1 步把这些摆上。": "Only ingredients this kitchen can make are offered here. Each needs its box; one that is chopped also needs a board, and one that is cooked needs the right stove. To use another ingredient, place these in step 1 first.",
    "计划模式（测试）": "Plan mode (trial)",
    "计划模式说明": "About plan mode",
    "Jeff 会写下接下来要做的几步，把前后动作连起来，用来减少来回倒腾": "Jeff writes down its next few steps in order, linking them up, to cut down on back-and-forth",
    "请在开局前或结算后修改计划模式。": "Change plan mode before a round or after the results.",
    "计划模式设置无效。": "Invalid plan mode setting.",
    "本局进行中；结束本局后可以修改。": "A round is in progress; change this after it ends.",
    "下一局起开启计划模式。": "Plan mode is on from the next round.",
    "下一局起关闭计划模式。": "Plan mode is off from the next round.",
    "两步打算（测试）": "Two-step intent (trial)",
    "下一局起开启两步打算。": "Two-step intent is on from the next round.",
    "下一局起关闭两步打算。": "Two-step intent is off from the next round.",
    "默认关闭，和计划模式二选一。Jeff 每次决定动作时，同时说出这个动作是为了哪道工序，以及做完之后打算做的下一道工序。下一次请求把这两道工序带回给它，做完的打上勾，然后再问一遍，用新的回答换掉旧的。它不用决定留不留，也不限制动作，随时可以改。沟通菜单里能看到 Jeff 当前的打算。开局前或结算后可以在「设置 → AI 搭档」里打开或关掉，一局内不变。": "Off by default; use it or plan mode, not both. Each time Jeff decides an action, it also says which piece of work that action is for, and the piece of work it intends to do after it. The next request shows these two back to Jeff, ticking what it has finished, and asks again; the new answer replaces the old one. Jeff never has to decide whether to keep it, it does not limit Jeff's actions, and Jeff can change it at any time. The communication menu shows Jeff's current intent. Turn it on or off in Settings → AI teammate before a round or after the results; it stays the same during a round.",
    "默认关闭。Jeff 没有计划时，会在决定下一步动作的同时，写下接下来打算做的几道工序，最多 4 步，比如切生菜、生菜装盘、出餐。它每做完一道，那一步就打上勾。计划没有时限：全部做完、Jeff 自己放弃，或者你发了新的分工说明时才结束，Jeff 立刻再写一份。计划不限制 Jeff 的动作，它每次仍从全部可选动作里选；中途去做计划外的事，计划也照旧留着。沟通菜单里能看到 Jeff 当前的计划。开局前或结算后可以在「设置 → AI 搭档」里关掉，一局内不变。": "Off by default. While Jeff has no plan, it writes down the next few pieces of work it intends to do along with its next action, up to 4 steps, such as chop lettuce, plate lettuce, serve. Each step is ticked when Jeff finishes it. The plan has no time limit: it ends only when every step is done, when Jeff drops it, or when you send a new message about who does what, and Jeff writes a new one at once. The plan does not limit Jeff's actions; it still chooses from every available action each time, and doing something outside the plan leaves the plan in place. The communication menu shows Jeff's current plan. Turn it off in Settings → AI teammate before a round or after the results; it stays the same during a round.",
    "一起改进 Jeff？": "Help improve Jeff?",
    "游戏会记录每一局的操作和模型的选择，但不包含 Key、IP、账号等个人信息。相关研究发表后，去掉身份信息的数据可能公开。": "The game records your moves and the model's choices in every round, but no personal information such as API keys, IP addresses or accounts. Once the research is published, the data may be made public with identifying information removed.",
    "使用免费模型需要贡献对局数据。": "Free models require contributing your round data.",
    "你以前贡献的对局，也会按这份新说明处理。不想的话，点": "Rounds you contributed earlier will follow these new terms too. If you don't want that, choose ",
    "「保持原样」": "“Keep as they were”",
    "你以前贡献的对局保持原来的说明，到期删除，不收进公开数据集。": "Your earlier rounds keep their original terms: deleted when they expire, never added to a public dataset. ",
    "改回按新说明处理": "Use the new terms for them",
    "同意贡献": "Contribute",
    "暂不，继续": "Not now, continue",
    "暂不贡献，用自己的 Key 或本地版": "Not now: use my own key or the local version",
    "详情 ▾": "Details ▾",
    "隐私说明 ↗": "Privacy ↗",
    "自愿参与。只有选「同意贡献」才会保存；选「暂不」也能正常游玩，随时可以在「设置 → 数据与贡献」更改。": "Participation is optional. Nothing is kept unless you choose Contribute; with Not now you can still play, and you can change your choice any time under Settings → Data and contributions.",
    "用途：改进游戏，研究人机协作的评估方法，并建立开放的人机协作基准。原始记录不公开。游戏没有玩家聊天输入框，记录的是局面、操作和模型的动作选择。": "Purpose: to improve the game, to study how to evaluate human–AI collaboration, and to build an open human–AI collaboration benchmark. Raw records are not published. The game has no chat box; records hold the kitchen, the moves and the model's choices of action.",
    "保存：私有保存在腾讯云（中国上海），海外站经加密连接提交。研究者会把记录下载到自己的电脑上分析。原始记录（包括下载的副本）最长保存两年，研究项目提前结束时一并删除，不做备份。": "Storage: kept privately on Tencent Cloud (Shanghai, China); the overseas site submits over an encrypted connection. Researchers download records to their own computers for analysis. Raw records, including downloaded copies, are kept for at most two years and deleted earlier if the research project ends. They are never backed up.",
    "公开数据集：相关研究发表后，我们可能把记录整理成数据集公开发布，任何人都可以下载使用，具体许可在发布时注明。发布前会对数据做脱敏处理，除了对局本身，只保留模型服务和模型 ID。": "Public dataset: once the research is published, we may publish the records as a dataset that anyone can download and use, under a licence named at release. Before release the data is de-identified: apart from the rounds themselves, only the model service and model ID are kept.",
    "删除：每局的删除凭证保存在这个浏览器里，可以在「设置 → 数据与贡献」删除。每份公开数据集只收录发布日 30 天以前贡献的对局，所以每局贡献后，你至少有 30 天可以删除；被收进数据集以后，就认不出是哪一局了，无法再删除。": "Deletion: each round's deletion receipt is kept in this browser; delete a round under Settings → Data and contributions. A public dataset only includes rounds contributed at least 30 days before its release date, so you always have at least 30 days to delete a round. Once a round is in a dataset it can no longer be identified, so it cannot be deleted.",
    "自动贡献会在开局时创建私有记录；正常结束、手动结束、重开、关闭请求或闲置回收时更新，提前结束的对局也包括在内。突然断电或进程崩溃可能只保留未完成的开局记录，不会推断退出原因。记录容量耗尽会明确标注丢失范围。关闭自动贡献会撤回本局未结束的记录。": "Automatic contribution creates a private record when a round starts and updates it when the round ends normally, is ended by hand, restarted, closed or reclaimed while idle; rounds that end early are included. A sudden power loss or crash may leave only the unfinished opening record, and no reason for leaving is guessed. If record capacity runs out, the missing range is marked. Turning automatic contribution off withdraws the record of a round still in progress.",
    "选「暂不」时，也可以在结算画面点「贡献本局」只贡献这一局。没有开局前同意时，只含已有事实与首尾状态，不含操作记录，缺失过程会标注。": "With Not now you can still contribute a single round from the result screen. Without consent before the round, the record holds only existing facts and the first and last states, no input record, and the gap is marked.",
    "可选：另同意收集浏览器自报的请求耗时及受控错误类型（默认不选）": "Optional: also allow browser-reported request timing and controlled error types (off by default)",
    "当前选择：以后每局自动贡献，最长保存两年。": "Current choice: contribute every round automatically; kept for at most two years.",
    "本局已贡献，最长保存两年。删除凭证在「设置 → 数据与贡献」。": "This round was contributed and is kept for at most two years. Its deletion receipt is under Settings → Data and contributions.",
    "本局已自动贡献，最长保存两年。": "This round was contributed automatically and is kept for at most two years.",
    "已开启自动贡献：此后每局自动保存，最长两年。": "Automatic contribution is on: every round from now on is kept, for at most two years.",
    "以前贡献的对局暂时没能按新说明处理，下次打开页面会再试。": "Your earlier rounds could not be moved to the new terms yet; this is tried again the next time you open the page.",
    "凭证或同意版本无效。": "Invalid receipt or consent version.",
    "记录不存在、已到期或凭证无效。": "The record does not exist, has expired, or the receipt is invalid.",
    "使用免费模型需要贡献本局数据；也可以改用自己的 Key 或本地版。": "Free models require contributing this round; you can use your own key or the local version instead.",
    "干净盘才可装菜。脏盘回收点取盘 → 放入水槽 → 空手按 E 洗碗 → 取净盘。没盘时可空手到锅边端锅，离灶停止加热；空锅需放回灶台。": "Only clean plates can hold food. Collect a dirty plate → put it in the sink → press E with empty hands to wash → take the clean plate. Without a plate, use empty hands to lift the whole pot. Taking it off the stove stops heating; return empty pots to the stove.",
    "拿食材靠近垃圾桶按空格会销毁，扣 2 元；端锅则倒掉锅里的食物，保留空锅。拿起灭火器后面向着火工位按 E（或空格）喷，累计喷 4 秒灭火；中途走开，进度保留，但停喷 2 秒后火会慢慢变旺。着火的工位会加热身边 8 格（含对角）的工位，旁边有一处着火 5 秒就会着火，多处同时着火更快，红色条显示进度；不跨空地或墙。同时 5 个工位着火，本局结束。": "Face a bin with food and press Space to discard it for a ¥2 penalty. Pots remain after emptying. Face a burning station with the extinguisher and press E (or Space) to spray; 4 seconds of spraying in total put it out. Walk away and the progress stays, but 2 seconds after spraying stops the fire starts growing back. A burning station heats the stations in the eight cells around it, diagonals included: next to one fire a station ignites after 5 seconds, faster beside several, and a red bar shows how close it is. Fire never crosses floors or walls. Five simultaneously burning stations end the round.",
    "拿/放": "Take/Put",
    "左摇杆或十字键移动 · A/× 拿放 · X/□ 切洗扔（长按瞄准） · B/○ 冲刺 · Start/Options 暂停/继续": "Left stick or D-pad: Move · A/×: Take/put · X/□: Chop/wash/throw (hold to aim) · B/○: Dash · Start/Options: Pause/resume",
    "摇杆移动 · 右键 拿放 · 左键 切洗扔（长按瞄准） · 下键 冲刺 · − 暂停/继续": "Stick: Move · Right button: Take/put · Left button: Chop/wash/throw (hold to aim) · Bottom button: Dash · −: Pause/resume",
    "摇杆移动 · 右键 拿放 · 左键 切洗扔（长按瞄准） · 下键 冲刺 · + 暂停/继续": "Stick: Move · Right button: Take/put · Left button: Chop/wash/throw (hold to aim) · Bottom button: Dash · +: Pause/resume",
    "拿和放：对正前方的东西取料、拿起、放下、下锅、装盘、出餐。要操作的工位会框出来，原地转身操作，不会把你挪过去。按下立即操作，手里拿着东西也一样。": "Take and put: fetch, pick up, put down, cook, plate or serve what is straight ahead. The station to be used is framed, and you work where you stand, without being moved. It acts on press, even with an item in hand.",
    "切、洗和扔：空手在案板前切菜、在水槽前洗碗，拿着灭火器时灭火；拿着能扔的东西时点按朝前扔出。和《胡闹厨房 2》的切/扔键一样，原作用左 Ctrl，网页里 Ctrl 加 W 会关掉标签页，所以用 E。": "Chop, wash and throw: with empty hands chop at a board or wash at a sink, spray when holding the extinguisher, and with a throwable item a tap throws it straight ahead. This is Overcooked 2's chop/throw key; it is left Ctrl there, but in a browser Ctrl with W closes the tab, so here it is E.",
    "按住 E": "Hold E",
    "投掷：手持可投掷物品时，面前是工位或空地都能按住 E 约 0.3 秒瞄准，角色停下，半透明弧形带显示方向与射程参考；方向键改方向，松开扔出，最远 4 格；队友在这个方向上就扔给他。终点仅表示最大射程，实际落点和接取由引擎判定。": "Throw: holding a throwable item, hold E for about 0.3 s to aim, whether facing a station or open floor. Your chef stops; a translucent curved band shows direction and range. Turn it with the direction keys and release to throw, up to 4 tiles, to your teammate when they are that way. The endpoint marks maximum range; the engine determines the actual landing and catches.",
    "手机触屏（横屏）：左下区域按住，摇杆出现在拇指下，朝任意方向推动移动，松手停止。右侧「拿/放」按下立即拿起或放下面前的东西（也用来下锅、装盘、出餐），手里拿着东西也一样。「切/洗/扔」在「拿/放」上方：空手时切菜、洗碗，拿着灭火器时灭火；手持可扔的物品时点按朝前方直接扔出，长按瞄准、用摇杆调方向、松开投掷；瞄准时旁边出现圆形「取消」，手指滑上去再松开即可取消。「冲刺」在「拿/放」左侧，移动时点按。顶部有暂停和菜单（设置、操作说明、本局记录、结束本局），沟通和标记也有按钮。手机转回竖屏会自动暂停，横屏后点「继续经营」。": "Touch (landscape): press in the lower-left area and the joystick appears under your thumb; push in any direction to move, let go to stop. Take/Put on the right picks up or puts down what is in front of you at once (also to cook, plate and serve), even with an item in hand. Chop/Wash/Throw, above Take/Put, chops and washes with empty hands and puts out fires with the extinguisher; with a throwable item, tap to throw straight ahead, or hold to aim, steer with the stick and release to throw; while aiming, a round Cancel appears beside it: slide onto it and let go to cancel. Tap Dash, left of Take/Put, while moving. The top bar has pause and the menu (settings, controls, round record, end round), plus communication and bookmark buttons. Turning the phone upright pauses automatically; turn it back and tap Continue.",
    "拿和放 · 空格，切、洗和扔 · E": "Take and put · Space, chop, wash and throw · E",
    "空格和 E 对角色正前方的东西起作用，像《胡闹厨房》一样：身边 8 格里最正对朝向的工位就是目标（朝向明显偏向对角时才选对角的），一转身就用框标出（有事可做时是蓝框）；身边和身后的工位不会选中，也不会把角色挪到别处，原地转身操作；切菜、洗碗前会先往旁边挪到工位正中。和《胡闹厨房 2》一样分成两个键：空格取料、放下、拿起、下锅、装盘、端锅、出餐、丢进垃圾桶；E 切菜、洗碗、灭火，手持可投掷物品时投掷（点按朝前扔，按住瞄准），空格不会切菜、洗碗或投掷。空格按下立即操作，手里拿着东西也一样。拿、放这类短动作开始后再按方向键，动作会先做完再走。切菜、洗碗开始后会一直做，按键不会停下，走开才停，进度保留。案板上的食材还没开始切或已经切好时可以拿走，切到一半拿不走，Jeff 也一样。地上空锅可先放切好的牛肉，再按空格端锅，离灶不加热。": "Space and E act on what is straight ahead of your chef, as in Overcooked: the station most squarely ahead among the eight tiles around you is the target (a diagonal one only when you clearly aim that way), framed the moment you turn (blue when there is something to do). Stations beside or behind you are never used, and your chef is never moved there: they turn and work where they stand, sliding sideways onto a board's or sink's centre before chopping or washing. As in Overcooked 2 the two keys split the work: Space fetches, puts down, picks up, cooks, plates, lifts a pot, serves or bins; E chops, washes or extinguishes, and with a throwable item in hand throws it (a tap throws ahead, holding aims); Space never chops, washes or throws. Space acts on press, even with an item in hand. Once a quick pick-up or put-down starts, a direction pressed during it takes effect after it finishes. Chopping and washing keep going once started; no key stops them, walking away does, and progress is kept. An ingredient on a board can be taken before chopping starts or once it is chopped, not part-way through; the same for Jeff. Load chopped beef into an empty floor pot, then press Space to lift it; it heats only on a stove.",
    "面前是工位时，按空格只对这个工位操作，不会把东西放到地上。面前是空地时，按空格先拿面前地上的东西，再拿脚下的，最后把手里的东西放在面前。拿干净盘面向地上的熟锅，也能盛菜。案板和柜台一样能放任何东西，包括装好菜的盘子和锅，只有生食材能用 E 切。食材箱顶上也能放一件东西：放着东西时，空格拿起的是它，空了才能再取料；手里有东西时对着空食材箱按空格，会把东西放上去。": "Facing a station, a Space press acts only on that station and never drops your item on the floor. Facing open floor, Space takes the item in front, then the one at your feet, and otherwise puts your item down in front. A clean plate facing a cooked pot on the floor takes its food. Like a counter, a board takes anything, plated dishes and pans included; only raw ingredients can be chopped, with E. An ingredient source holds one item on top too: while it does, Space takes that item, and only an empty source gives a new ingredient; with something in hand, Space at an empty source puts it there.",
    "抛掷与传菜 · E": "Throw and pass · E",
    "手持可投掷物品时，点按 E 朝前直接扔出；面前是工位或空地都能按住 E 约 0.3 秒瞄准，角色停下，半透明弧形带显示方向与射程参考；按方向键改方向（8 个方向），松开扔出；队友在这个方向的射程内时扔给他。终点仅表示最大射程，不是实际落点预测；墙体阻挡和接取仍由引擎判定。生食材、切好的原料、餐盘、装盘菜和锅都能抛，最远 4 格；灭火器不能扔。可以越过工位，飞到射程尽头，遇墙落在墙前：生料或切好的料落在空案板、空柜台、空食材箱上，或落进能煮这份料的空锅；其他东西落在地上。没有可用落点时保留手里的物品。队友空手、在走路或站着时能接住；正在切菜、洗碗或手里有东西时不会被打断，东西落在他旁边，盘里的菜和锅里的东西都保留。玩家与 AI 规则相同。": "Holding a throwable item, a tap of E throws it straight ahead; hold E for about 0.3 s to aim, whether facing a station or open floor. Your chef stops; a translucent curved band shows direction and range. Turn it with the direction keys (8 directions) and release to throw; a teammate that way within range gets it. The endpoint marks maximum range, not a predicted landing point; the engine still resolves walls and catches. Raw and chopped ingredients, plates, plated dishes and pots all fly up to 4 tiles; the extinguisher cannot be thrown. Throws cross stations and fly to the range limit, stopping before a wall: a raw or chopped ingredient lands on an empty board, counter or ingredient source, or in an empty pan that cooks it; anything else lands on the floor. If no landing place is available, the item stays in your hand. An empty-handed teammate who is walking or standing catches it; one who is chopping, washing or holding something is not interrupted and the item lands beside them, keeping plated food and pot contents. The player and the AI follow the same rules.",
    "「拿/放」按下立即拿起或放下，拿着东西也一样；「切/洗/扔」空手时切菜、洗碗，拿着灭火器时灭火，拿着能扔的东西时点按直接扔出、长按瞄准、松开投掷；瞄准时滑到「取消」可取消。": "Take/Put picks up or puts down at once, even with an item in hand. Chop/Wash/Throw chops and washes with empty hands and puts out fires with the extinguisher; with a throwable item, tap to throw straight ahead, or hold to aim and release to throw; while aiming, slide onto Cancel to cancel.",
    "使用左侧摇杆移动，右侧按钮拿放、切洗扔和冲刺。": "Move with the left joystick. Use the right buttons to take and put, chop, wash and throw, and dash.",
    "切/洗/扔": "Chop/Wash/Throw",
    "按住「切/洗/扔」瞄准": "Hold Chop/Wash/Throw to aim",
    "请选择 API 服务。": "Choose an API service.",
    "请填写完整的 API Key，不要包含空格或换行。": "Enter the complete API key, without spaces or line breaks.",
    "请填写接口地址和模型名称。": "Enter the base URL and the model name.",
    "接口地址需要是 HTTPS Base URL，不能包含密码、查询参数或片段。": "The base URL must be an HTTPS URL without a password, query string or fragment.",
    "第一版仅支持公网 HTTPS 模型接口。": "Only public HTTPS model endpoints are supported for now.",
    "不支持内网接口地址。": "Private network addresses are not supported.",
    "这里只能填这台电脑上的地址（localhost、127.0.0.1 或 [::1]）。": "Only an address on this computer works here (localhost, 127.0.0.1 or [::1]).",
    "保存选项无效。": "Invalid save option.",
    "需要配置玩家 API": "Set up your own model API first",
    "模型接口连接失败或返回了无效数据": "Could not reach the model API, or it returned invalid data",
    "回复里没有文本": "the reply has no text",
    "不是 JSON": "not JSON",
    "缺少 choice": "choice is missing",
    "sprint 不是真假值": "sprint is not true or false",
    "choice 不在候选动作里": "choice is not one of the offered actions",
    "本局 AI 调用已达上限，不再发起请求；已有动作继续，玩家仍可操作。": "This round's AI call limit is reached; no more requests are sent. Actions under way continue and you can keep playing.",
    "未找到 TYPESAFE_API_KEY。请在本地 .env 中配置，不要把密钥发到聊天。": "TYPESAFE_API_KEY was not found. Set it in your local .env; never paste the key into a chat.",
    "仅允许本机或 USB 转发访问。": "Only this computer or USB forwarding may connect.",
    "请先构建 Cocos Web 预览，或检查路径。": "Build the Cocos web preview first, or check the path.",
    "水槽旁边要留一格空位放沥水架": "Leave a free cell beside the sink for its drying rack",
    "沥水架要紧挨着水槽": "The drying rack goes right beside the sink"
  },
  "templates": [
    [
      "标准时间 {0} 秒",
      "{0} s of standard time"
    ],
    [
      "端起{0}的{1}（{2}）",
      "Lift the {1} from {0} ({2})"
    ],
    [
      "把{0}放入{1}的空{2}（{3}）",
      "Load {0} into the empty {2} at {1} ({3})"
    ],
    [
      "把{0}放入地上空{1}（{2}）",
      "Load {0} into the empty {1} on the floor ({2})"
    ],
    [
      "把手中的{0}放回{1}（{2}）",
      "Return the {0} to {1} ({2})"
    ],
    [
      "与{0}的锅交换",
      "Swap with the pot at {0}"
    ],
    [
      "与{0}的锅交换（各自保留锅内食物）",
      "Swap with the pot at {0} (contents stay in their own pots)"
    ],
    [
      "把切好的牛肉放入{0}的空锅（离灶不加热）",
      "Load chopped beef into the empty pot at {0} (no heating off stove)"
    ],
    [
      "用手中餐盘接取{0}的食材",
      "Collect the ingredient from {0} into the held plate"
    ],
    [
      "把{0}盘中食物合入手中盘（空盘留在原位）",
      "Merge food from the plate at {0} into the held plate (empty plate stays in place)"
    ],
    [
      "{0}把食材加入{1}手中的盘",
      "{0} added food to the plate held by {1}"
    ],
    [
      "本局 {0} / {1} 次{2}；成功回复 token：输入 {3} / 输出 {4}；本次服务连接测试 {5} 次",
      "Round: {0} / {1} calls{2}; reported tokens: {3} input / {4} output; connection tests: {5}"
    ],
    [
      "{0}到达后发现地上物品已变化或被捡走，动作取消",
      "{0}: the floor item changed or was taken; action cancelled"
    ],
    [
      "下一局最多 {0} 次，服务重启后恢复默认。",
      "Next round: up to {0} calls. Resets to default when the service restarts."
    ],
    [
      "{0}到达后发现目标已变化或被占用，动作取消",
      "{0}: target changed or is occupied; action cancelled"
    ],
    [
      "Jeff 选择：{0} | {1}s | 未执行：{2}",
      "Jeff chose: {0} | {1}s | Not executed: {2}"
    ],
    [
      "{0}到达后发现食材已不需要切配，动作取消",
      "{0}: ingredient no longer needs chopping; action cancelled"
    ],
    [
      "{0}着火！损失 5 元；必须先灭火再清锅",
      "{0} is on fire! -¥5; extinguish it before clearing the pot"
    ],
    [
      " · 本局使用 {0} 局，结算后可修改",
      " · Using {0} rounds this round; editable after it ends"
    ],
    [
      "净收入 ¥{0}（目标 ¥{1}），还差 ¥{2} 元",
      "Net revenue ¥{0} (target ¥{1}), ¥{2} short"
    ],
    [
      "净收入 ¥{0}（目标 ¥{1}）",
      "Net revenue ¥{0} (target ¥{1})"
    ],
    [
      "完成 {0} 单 · 超时 {1} 单 · 关店时未完成 {2} 单",
      "{0} orders served · {1} expired · {2} open at closing"
    ],
    [
      "盘里已经有{0}了",
      "The plate already has {0}"
    ],
    [
      "{0}糊锅！{1}s 后着火；糊太久上桌会被拒收",
      "{0} burnt! Fire in {1}s; a dish burnt too long is refused"
    ],
    [
      "{0} · 当前模型已保存 {1} / {2} 局{3}",
      "{0} · Saved for this model: {1} / {2} rounds{3}"
    ],
    [
      "{0}洗好了 {1}，可取走盛菜或放到空柜台",
      "{0} washed {1}; take it to plate food or put it on a counter"
    ],
    [
      "{0}把 {1} 放在{2}旁的地上，双方都可以捡",
      "{0} put {1} on the floor by {2}; either chef can pick it up"
    ],
    [
      "{0} 已回到脏盘回收点，洗净后可复用",
      "{0} returned dirty; wash it to reuse"
    ],
    [
      "{0}换手：把 {1} 留在{2}的地上，可捡回",
      "{0} swapped items; {1} is on the floor at {2}"
    ],
    [
      "{0}附近没有空位换手，物品保持原样",
      "{0}: no space to swap items; nothing changed"
    ],
    [
      "{0}的抛递落点不可用，仍拿着物品",
      "{0}: landing space unavailable; item kept"
    ],
    [
      "已连接：{0} · 玩家账号付费{1}",
      "Connected: {0} · Your account pays{1}"
    ],
    [
      "将半成品放进{0}，开始自动加热",
      "Put chopped meat in {0} to cook"
    ],
    [
      "{0}发现落点被占用，仍拿着食物",
      "{0}: landing space occupied; food kept"
    ],
    [
      "{0}受阻，重新规划路线",
      "{0}: path blocked; route re-planned"
    ],
    [
      "把手中锅里的菜盛到{0}的盘里",
      "Fill the plate on {0} from your pot"
    ],
    [
      "新订单 {0}：牛排，截止 {1}s",
      "New order {0}: steak, due at {1}s"
    ],
    [
      "{0} 落到{1}，可继续切配或取走",
      "{0} landed on {1}; chop it or take it"
    ],
    [
      "Jeff 选择：{0} | {1}s",
      "Jeff chose: {0} | {1}s"
    ],
    [
      "用手中的干净盘盛出{0}的菜",
      "Plate food from {0}"
    ],
    [
      "用手中的盘盛出{0}锅里的菜",
      "Plate food from the pot on {0}"
    ],
    [
      "{0}的 {1} 熟了！{2}s 后糊锅",
      "{1} in {0} is ready! Burns in {2}s"
    ],
    [
      "{0}抛出了 {1}，落点为 {2}",
      "{0} threw {1} toward {2}"
    ],
    [
      "{0} 落在地上，可拾取",
      "{0} landed on the floor; pick it up"
    ],
    [
      "{0}从{1}旁的地上捡起 {2}",
      "{0} picked up {2} from the floor by {1}"
    ],
    [
      "将手中食材放到{0}",
      "Put the held ingredient on {0}"
    ],
    [
      "把手中的锅放回{0}",
      "Return the pot to {0}"
    ],
    [
      "把手中物品放到{0}",
      "Put the held item on {0}"
    ],
    [
      "拿灭火器到{0}灭火",
      "Use the extinguisher at {0}"
    ],
    [
      "{0}停止手动移动",
      "{0} stopped moving"
    ],
    [
      "{0} {1}s 后糊",
      "{0} · burns in {1}s"
    ],
    [
      "地面({0},{1})",
      "floor ({0},{1})"
    ],
    [
      "{0}完成动作：{1}",
      "{0} completed: {1}"
    ],
    [
      "待洗 {0}s",
      "Wash: {0}s"
    ],
    [
      "从{0}拿走 {1}",
      "Take {1} from {0}"
    ],
    [
      "端起{0}的锅",
      "Lift the pot from {0}"
    ],
    [
      "去{0}捡起 {1}",
      "Pick up {1} at {0}"
    ],
    [
      "{0}手动移动",
      "{0} is moving"
    ],
    [
      "{0}接住了 {1}",
      "{0} caught {1}"
    ],
    [
      "到{0}切 {1}",
      "Chop {1} at {0}"
    ],
    [
      "从{0}拿起{1}",
      "Take {1} from {0}"
    ],
    [
      "{0}中断：{1}",
      "{0} stopped: {1}"
    ],
    [
      "{0}开始：{1}（路程 {2}s + 操作 {3}s）",
      "{0} started: {1} (travel {2}s + work {3}s)"
    ],
    [
      "{0}开始给队友装盘",
      "{0} started plating into the teammate's plate"
    ],
    [
      "{0}把锅中菜盛入{1}手中的盘",
      "{0} served the food from the pot into the plate held by {1}"
    ],
    [
      "新订单 {0}：{1}，截止 {2}s",
      "New order {0}: {1}, due at {2}s"
    ],
    [
      "取一份{0}",
      "Fetch {0}"
    ],
    [
      "在{0}向盘中加入食材",
      "Add ingredient to the plate at {0}"
    ],
    [
      "冷却 {0}s",
      "Cooldown {0}s"
    ],
    [
      "{0}着火！损失 5 元；必须先灭火再使用",
      "{0} caught fire! Lost 5 yuan; extinguish it before use."
    ],
    [
      "拿灭火器到{0}灭火（4s）",
      "Take the extinguisher to {0} and extinguish the fire (4s)."
    ],
    [
      "着火工位 {0}/{1}",
      "Burning stations {0}/{1}"
    ],
    [
      "{0}s 熟",
      "{0}s ready"
    ],
    [
      "{0}s 糊",
      "{0}s burn"
    ],
    [
      "本局 {0} / {1} 次{2}；成功回复 token：输入 {3} / 输出 {4}；本页面连接测试 {5} 次",
      "Round: {0} / {1} calls{2}; reported tokens: {3} input / {4} output; connection tests: {5}"
    ],
    [
      "你和 AI 搭档，一起照顾这间小厨房。\n本局目标：关店时净收入达到 ¥{0}",
      "Run this kitchen with your AI teammate.\nGoal: net revenue of ¥{0} at closing time"
    ],
    [
      "出餐 {0} 单 · 净收入 ¥{1} / ¥{2}",
      "{0} orders served · net revenue ¥{1} / ¥{2}"
    ],
    [
      "¥ {0} / {1}",
      "¥ {0} / {1}"
    ],
    [
      "{0}：净收入 {1}/{2} 元；完成 {3} 单；超时 {4}；拒收 {5}；关店未完成 {6}；糊锅 {7}，着火 {8}",
      "{0}: net revenue ¥{1}/¥{2}; {3} orders completed; expired {4}; refused {5}; open at closing {6}; burnt {7}, fires {8}"
    ],
    [
      "{0}完成 {1}，收入 +{2} 元{3}",
      "{0} completed {1}: +¥{2}{3}"
    ],
    [
      "（菜品糊了，扣 {0} 元）",
      " (burnt dish, -¥{0})"
    ],
    [
      "没有等待{0}的订单；扣 {1} 元",
      "No order is waiting for {0}: -¥{1}"
    ],
    [
      "{0}的顾客拒收糊菜，订单继续等待",
      "The customer of {0} refused a burnt dish; the order keeps waiting"
    ],
    [
      "{0}超时，顾客离开，扣 {1} 元",
      "{0} expired: the customer left, -¥{1}"
    ],
    [
      "{0}超时，扣 {1} 元，订单重新计时",
      "{0} expired: -¥{1}, the order starts again"
    ],
    [
      "已无法达成目标金额 {0} 元；本局继续至关店",
      "The ¥{0} target can no longer be reached; the round continues until closing"
    ],
    [
      "{0}在关店时仍未完成",
      "{0} was still open at closing time"
    ],
    [
      "{0}加入{1}的共同操作（{2}人）",
      "{0} joined the shared work at {1} ({2} chefs)"
    ],
    [
      "{0}离开{1}的共同操作，进度保留",
      "{0} left the shared work at {1}; progress kept"
    ],
    [
      "Jeff：{0}（未执行）",
      "Jeff: {0} (skipped)"
    ],
    [
      "Jeff：{0}",
      "Jeff: {0}"
    ],
    [
      "{0} 超时 -¥{1}",
      "{0} expired -¥{1}"
    ],
    [
      "熟 {0}",
      "cooked {0}"
    ],
    [
      "糊 {0}",
      "burnt {0}"
    ],
    [
      "合切 {0}",
      "shared {0}"
    ],
    [
      "把手中的{0}放进{1}的盘里",
      "Put the held {0} onto the plate at {1}"
    ],
    [
      "把{0}的{1}加进手中的盘",
      "Add the {1} from {0} to the held plate"
    ],
    [
      "与地上的{0}交换",
      "Swap with the {0} on the floor"
    ],
    [
      "与{0}的{1}交换",
      "Swap with the {1} at {0}"
    ],
    [
      "倒掉手中{0}里的食物",
      "Empty the food from the held {0}"
    ],
    [
      "损耗{0}元，保留空{1}",
      "¥{0} cost; keep the empty {1}"
    ],
    [
      "将{0}放进{1}的{2}，开始自动加热",
      "Put {0} into the {2} on {1}; it starts heating"
    ],
    [
      "把{0}放入地上空{1}",
      "Load {0} into the empty {1} on the floor"
    ],
    [
      "把{0}放入{1}的空{2}",
      "Load {0} into the empty {2} at {1}"
    ],
    [
      "把手中{0}里的菜盛到{1}的盘里",
      "Fill the plate on {1} from your {0}"
    ],
    [
      "空{0}留在手中",
      "keep the empty {0}"
    ],
    [
      "用手中的干净盘盛出地上{0}里的菜",
      "Plate food from the {0} on the floor"
    ],
    [
      "用手中的盘盛出{0}的{1}里的菜",
      "Plate food from the {1} on {0}"
    ],
    [
      "空{0}留在原地",
      "the empty {0} stays in place"
    ],
    [
      "把手中的{0}放回{1}",
      "Return the {0} to {1}"
    ],
    [
      "端起{0}的{1}",
      "Lift the {1} from {0}"
    ],
    [
      "平底锅 · {0}",
      "Frying pan · {0}"
    ],
    [
      "汤锅 · {0}",
      "Soup pot · {0}"
    ],
    [
      "切好的{0}",
      "chopped {0}"
    ],
    [
      "{0} 秒",
      "{0} s"
    ],
    [
      "模型接口返回 HTTP {0}，请检查账号和模型。",
      "Model API returned HTTP {0}. Check your account and model."
    ],
    [
      "已删除 {0} 份记录；{1} 份未删除，请检查凭证后重试。",
      "Deleted {0} records; {1} could not be deleted. Check the receipts and try again."
    ],
    [
      "下一关 · {0}",
      "Next level · {0}"
    ],
    [
      "贡献：你 {0}% · Jeff {1}%",
      "Contribution: you {0}% · Jeff {1}%"
    ],
    [
      "Jev 接口返回 HTTP {0}，请检查账号和模型。",
      "Jev API returned HTTP {0}. Check your account and model."
    ],
    [
      "你所在的网络已同时开了 {0} 个厨房。其中一个结束后按钮会恢复，请再点击继续。",
      "Your network already has {0} kitchens open. The button comes back when one of them ends; press it to continue."
    ],
    [
      "你所在的网络已同时开了 {0} 个厨房，其中一个结束后再试。",
      "Your network already has {0} kitchens open. Try again when one of them ends."
    ],
    [
      "贡献失败：{0}",
      "Contribution failed: {0}"
    ],
    [
      "自动贡献失败：{0}",
      "Automatic contribution failed: {0}"
    ],
    [
      "{0}被推开",
      "{0} was knocked back"
    ],
    [
      "{0}开始冲刺",
      "{0} started sprinting"
    ],
    [
      "到{0}取一份{1}",
      "Take {1} from {0}"
    ],
    [
      "抛给队友（接不住时落到{0}）",
      "Throw to the other chef (lands at {0} if not caught)"
    ],
    [
      "抛出手中物品（落到{0}）",
      "Throw the held item (lands at {0})"
    ],
    [
      "{0} 落进{1}的{2}，开始加热",
      "{0} landed in the {2} on {1} and started heating"
    ],
    [
      "向上方抛出手中物品（落到{0}）",
      "Throw the held item up (lands at {0})"
    ],
    [
      "向下方抛出手中物品（落到{0}）",
      "Throw the held item down (lands at {0})"
    ],
    [
      "向左方抛出手中物品（落到{0}）",
      "Throw the held item left (lands at {0})"
    ],
    [
      "向右方抛出手中物品（落到{0}）",
      "Throw the held item right (lands at {0})"
    ],
    [
      "向左上方抛出手中物品（落到{0}）",
      "Throw the held item up-left (lands at {0})"
    ],
    [
      "向右上方抛出手中物品（落到{0}）",
      "Throw the held item up-right (lands at {0})"
    ],
    [
      "向左下方抛出手中物品（落到{0}）",
      "Throw the held item down-left (lands at {0})"
    ],
    [
      "向右下方抛出手中物品（落到{0}）",
      "Throw the held item down-right (lands at {0})"
    ],
    [
      "Key 无效，请检查后重试。（{0}）",
      "Invalid key. Check it and try again. ({0})"
    ],
    [
      "账号余额不足，请到服务商充值。（{0}）",
      "Not enough balance. Top up with the provider. ({0})"
    ],
    [
      "账号无权访问这个模型。（{0}）",
      "This account cannot use this model. ({0})"
    ],
    [
      "请求受限或额度不足，请稍后重试。（{0}）",
      "Rate limited or out of quota. Try again later. ({0})"
    ],
    [
      "连接失败（{0}）",
      "Connection failed ({0})"
    ],
    [
      "模型接口 HTTP {0}：{1}",
      "Model API HTTP {0}: {1}"
    ],
    [
      "模型接口 HTTP {0}",
      "Model API HTTP {0}"
    ],
    [
      "受输入长度限制，本局省略 {0} 局较旧记录。",
      "Input length limit: {0} older rounds omitted for this round."
    ],
    [
      "超时 {0} 单 · 关店时未完成 {1} 单",
      "Expired {0} · Unfinished at closing {1}"
    ],
    [
      "免费试玩：{0} · 服务器提供额度",
      "Free trial: {0} · Server-provided allowance"
    ],
    [
      "当前：{0}（{1}）",
      "Current: {0} ({1})"
    ],
    [
      "默认：{0}（{1}）",
      "Default: {0} ({1})"
    ],
    [
      "{0} 剩余 {1} 秒。",
      "{0} {1} seconds remaining."
    ],
    [
      "{0} 正在重新请求。",
      "{0} Requesting again."
    ],
    [
      "{0} 约 {1} 秒后重试。",
      "{0} Retrying in about {1} seconds."
    ],
    [
      "Enter 开始 · ← → 换关卡 · 搭档：{0}",
      "Enter Start · ← → Change level · Teammate: {0}"
    ],
    [
      "搭档：{0}",
      "Teammate: {0}"
    ],
    [
      "第 {0} 关 · {1}",
      "Level {0} · {1}"
    ],
    [
      "第 {0} 关",
      "Level {0}"
    ],
    [
      "关店时净收入 ★ ¥{0} · ★★ ¥{1} · ★★★ ¥{2} · {3} / {4}",
      "Net revenue at closing ★ ¥{0} · ★★ ¥{1} · ★★★ ¥{2} · {3} / {4}"
    ],
    [
      "目标 ¥{0}",
      "Goal ¥{0}"
    ],
    [
      "{0} · 多赚 ¥{1} · 完成 {2} 单",
      "{0} · ¥{1} over the goal · {2} orders served"
    ],
    [
      "{0} · 离 {1} 还差 ¥{2} · 完成 {3} 单",
      "{0} · ¥{2} short of {1} · {3} orders served"
    ],
    [
      "还差 ¥{0} · 完成 {1} 单",
      "¥{0} short · {1} orders served"
    ],
    [
      "{0} · 最佳 ¥{1}",
      "{0} · best ¥{1}"
    ],
    [
      "未达成 · 最佳 ¥{0}",
      "Not reached · best ¥{0}"
    ],
    [
      "每局最多向模型请求 {0} 次，没成功的请求也算在内。",
      "Up to {0} model requests per round; failed requests count too."
    ],
    [
      "{0} 回复格式或动作无效，本次未执行。",
      "{0} returned an invalid format or action; nothing was done."
    ],
    [
      "请先同意通过试玩服务器调用 {0}。",
      "Please first agree to call {0} through the demo server."
    ],
    [
      "{0} 请求无效。",
      "{0} request is invalid."
    ],
    [
      "此厨房的 {0} 请求仍在处理中。",
      "A {0} request for this kitchen is still in progress."
    ],
    [
      "当前不能请求 {0}。",
      "{0} cannot be requested now."
    ],
    [
      "{0} 决策请求已过期。",
      "The {0} decision request has expired."
    ],
    [
      "{0} 转发请求较多，请稍后重试。",
      "{0} forwarding is busy. Try again later."
    ],
    [
      "{0} 转发连接失败。",
      "{0} forwarding failed."
    ],
    [
      "{0} 接口返回 HTTP {1}，请检查账号和模型。",
      "{0} API returned HTTP {1}. Check your account and model."
    ],
    [
      "切好后放进{0}加热",
      "Chop, then heat in the {0}"
    ],
    [
      "直接放进{0}加热",
      "Heat in the {0} as it comes"
    ],
    [
      "灶台·{0}",
      "Stove · {0}"
    ],
    [
      "{0}食材箱",
      "{0} box"
    ],
    [
      "墙把厨房隔成了 {0} 块，隔开的两边没法传递东西",
      "Walls cut the kitchen into {0} parts; nothing passes between them"
    ],
    [
      "地板被隔成了 {0} 块，两位厨师最多各管一块",
      "The floor is in {0} parts; two chefs can each work one at most"
    ],
    [
      "还缺：{0}",
      "Missing: {0}"
    ],
    [
      "{0}只能有 1 个，现在有 {1} 个",
      "Only 1 {0} allowed; there are {1}"
    ],
    [
      "出餐口最多 {0} 个，现在有 {1} 个",
      "At most {0} serving windows; there are {1}"
    ],
    [
      "柜台至少 {0} 个，用来放开局的盘子",
      "At least {0} counters, for the starting plates"
    ],
    [
      "{0}跟前没有地方站，人够不着",
      "{0}: nowhere to stand in front, so nobody can reach it"
    ],
    [
      "第 {0} 道菜还没起名",
      "Dish {0} has no name yet"
    ],
    [
      "第 {0} 道菜还没选配料",
      "Dish {0} has no ingredients yet"
    ],
    [
      "第 {0} 道菜的价格要在 {1} 到 {2} 元之间",
      "Dish {0} must cost {1} to {2}"
    ],
    [
      "第 {0} 道菜和第 {1} 道菜的配料一样，端上去分不清",
      "Dishes {0} and {1} have the same ingredients and could not be told apart"
    ],
    [
      "排在第 {0} 位",
      "Number {0} in line"
    ],
    [
      "小 {0}×{1}",
      "Small {0}×{1}"
    ],
    [
      "中 {0}×{1}",
      "Medium {0}×{1}"
    ],
    [
      "大 {0}×{1}",
      "Large {0}×{1}"
    ],
    [
      "还有 {0} 处要改",
      "{0} things to fix"
    ],
    [
      "¥{0} · {1} 样配料",
      "¥{0} · {1} ingredients"
    ],
    [
      "最多 {0} 道菜。每 {1} 秒来一单，菜单上的菜轮流出现。",
      "Up to {0} dishes. An order comes every {1} s, the menu dishes in turn."
    ],
    [
      "菜名只显示给人看，最多 {0} 个字。",
      "Only people see the dish name, up to {0} characters."
    ],
    [
      "配料（最多 {0} 样，做法由食材决定）",
      "Ingredients (up to {0}; each is prepared its own way)"
    ],
    [
      "第 {0} 样",
      "No. {0}"
    ],
    [
      "第 {0} 样配料",
      "Ingredient {0}"
    ],
    [
      "便宜 {0} 元",
      "{0} cheaper"
    ],
    [
      "贵 {0} 元",
      "{0} dearer"
    ],
    [
      "按做法算的建议价 ¥{0}",
      "Suggested price ¥{0}"
    ],
    [
      "{0} 到 {1} 元，每档 {2} 元。建议价 = {3} + 每样配料 {4} + 每样要下锅的再加 {5}。",
      "{0} to {1} in steps of {2}. Suggested price = {3} + {4} per ingredient + {5} more for each one that is heated."
    ],
    [
      "切和煮一共 {0} 秒 → 最多等 {1} 秒",
      "{0} s of chopping and cooking → waits up to {1} s"
    ],
    [
      "按工时的 {0} 倍算，在 {1} 到 {2} 秒之间。",
      "{0} times the work time, between {1} and {2} s."
    ],
    [
      "已摆：{0}",
      "Placed: {0}"
    ],
    [
      "{0} 台设备",
      "{0} stations"
    ],
    [
      "每 {0} 秒一单，菜单上的菜轮流出现",
      "An order every {0} s, the menu dishes in turn"
    ],
    [
      "每道菜最多等 {0} 秒",
      "Each dish waits up to {0} s"
    ],
    [
      "开局 {0} 个，用过要洗了再用",
      "{0} at the start; wash them to reuse"
    ],
    [
      "{0} 分钟，关店时看净收入",
      "{0} minutes; net income counts at closing"
    ],
    [
      "规则、走路速度和切煮时间都和官方关卡一样，不能改。服务器让两个脚本厨师照这张关卡试做 {0} 局，取收入中位数的一半作为目标。",
      "The rules, walking speed and chop and cook times are those of the official levels and cannot change. The server has two scripted chefs play this level {0} times and sets the target at half their median income."
    ],
    [
      "一共试做 {0} 局，大约 1 分钟。服务器只告诉我们“在算”和“算完了”，所以这里不画进度条。",
      "{0} rounds in all, about a minute. The server only says \"running\" or \"done\", so there is no progress bar."
    ],
    [
      "{0} 局收入中位数 ¥{1}，目标取一半",
      "Median income of {0} rounds ¥{1}; the target is half"
    ],
    [
      "中位数 ¥{0} · {1}",
      "Median ¥{0} · {1}"
    ],
    [
      "两个脚本厨师 {0} 局一道菜都没做出来。",
      "In {0} rounds the two scripted chefs served no dish."
    ],
    [
      "{0}要贴着外墙摆",
      "{0}: put it against the outer wall"
    ],
    [
      "{0}只能贴着外墙摆，点有橙色边框的格子",
      "{0} only goes against the outer wall: click a cell with an orange border"
    ],
    [
      "关店时净收入 ★ ¥{0} · ★★ ¥{1} · ★★★ ¥{2} · 一个人也能过",
      "Net revenue at closing ★ ¥{0} · ★★ ¥{1} · ★★★ ¥{2} · one player can pass"
    ],
    [
      "关店时净收入 ★ ¥{0} · ★★ ¥{1} · ★★★ ¥{2} · 需要两个人配合",
      "Net revenue at closing ★ ¥{0} · ★★ ¥{1} · ★★★ ¥{2} · needs both chefs"
    ],
    [
      "Enter 开始 · 搭档：{0}",
      "Enter Start · Teammate: {0}"
    ],
    [
      "已说：{0}",
      "Said: {0}"
    ],
    [
      "{0}（缺{1}）",
      "{0} (needs {1})"
    ],
    [
      "厨房里还缺{0}",
      "The kitchen still needs {0}"
    ],
    [
      "菜单没用上：{0}",
      "Not on the menu: {0}"
    ],
    [
      "送错 -¥{0}",
      "Wrong dish -¥{0}"
    ],
    [
      "已把以前贡献的 {0} 局按新说明处理。",
      "Moved {0} earlier rounds to the new terms."
    ],
    [
      "站到{0}正前方才能切",
      "Stand right in front of {0} to chop"
    ],
    [
      "站到{0}正前方才能洗",
      "Stand right in front of {0} to wash"
    ],
    [
      "对局记录包未能保存（{0}）",
      "The round record bundle could not be saved ({0})"
    ],
    [
      "模型没有返回可执行的合法动作（{0}）；本次不执行。",
      "The model returned no valid action to carry out ({0}); nothing was done this time."
    ],
    [
      "{0}；回复：{1}",
      "{0}; reply: {1}"
    ],
    [
      "{0} 返回了不符合候选集的选择",
      "{0} returned a choice outside the offered actions"
    ],
    [
      "{0} 拒绝回答这一题",
      "{0} refused to answer this question"
    ],
    [
      "{0} 网络连接失败或超时",
      "{0}: network connection failed or timed out"
    ],
    [
      "Jeff 请求失败：{0}；{1}s 后重试。无脚本队友代替。",
      "Jeff's request failed: {0}; retrying in {1}s. No scripted teammate stands in."
    ]
  ]
}
;
  const escape = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const templates = catalog.templates.map(([source, target]) => {
    const ids = [];
    const pattern = source.split(/(\{\d+\})/).map(part => {
      if (/^\{\d+\}$/.test(part)) { ids.push(Number(part.slice(1,-1))); return '(.*?)'; }
      return escape(part);
    }).join('');
    return { source, target, ids, regex: new RegExp('^' + pattern + '$', 's') };
  }).sort((a,b) => b.source.replace(/\{\d+\}/g,'').length-a.source.replace(/\{\d+\}/g,'').length);
  const keys = Object.keys(catalog.messages).sort((a,b) => b.length-a.length);
  const fragments = new RegExp(keys.map(escape).join('|'),'g');
  let locale = 'zh';
  try { if (root.localStorage?.getItem('chefjeff-language') === 'en') locale='en'; } catch (_) {}
  function english(text, depth=0) {
    if (typeof text !== 'string' || !text || depth>8) return text;
    if (Object.prototype.hasOwnProperty.call(catalog.messages,text)) return catalog.messages[text];
    for (const rule of templates) {
      const match=text.match(rule.regex);
      if (!match) continue;
      const args={}; rule.ids.forEach((id,i) => { args[id]=match[i+1]; });
      return rule.target.replace(/\{(\d+)\}/g,(_,id) =>
        rule.source.startsWith('已连接：') && id==='0' ? args[id] : english(args[id],depth+1));
    }
    if (text.includes('\n')) return text.split('\n').map(line=>english(line,depth+1)).join('\n');
    if (text.includes('　')) return text.split('　').map(part=>english(part,depth+1)).join('　');
    if (text.startsWith('空格 · ')) return 'Space · '+english(text.slice(5),depth+1);
    if (text.startsWith('E · ')) return 'E · '+english(text.slice(4),depth+1);
    return text.replace(fragments,key=>catalog.messages[key]);
  }
  const cache=new Map();
  function translate(text){
    if(locale!=='en')return text;
    if(cache.has(text))return cache.get(text);
    const value=english(text);if(cache.size>=512)cache.clear();cache.set(text,value);return value;
  }
  root.kitchenI18n = { t:translate, english, get language(){return locale;}, setLanguage };
  if (typeof module !== 'undefined') module.exports=root.kitchenI18n;
  const doc=root.document;
  const sources=new WeakMap(), attributes=new WeakMap();
  function textNode(node) {
    if (!node.parentElement || node.parentElement.closest('script,style,textarea,[data-no-i18n]')) return;
    let row=sources.get(node);
    if (!row || node.nodeValue!==row.rendered) row={source:node.nodeValue,rendered:node.nodeValue};
    row.rendered=translate(row.source);sources.set(node,row);
    if (node.nodeValue!==row.rendered) node.nodeValue=row.rendered;
  }
  function element(el) {
    if (el.nodeType!==1 || el.closest('script,style,textarea,[data-no-i18n]')) return;
    let rows=attributes.get(el)||{};
    for (const name of ['placeholder','aria-label','title','label']) {
      if (!el.hasAttribute(name)) continue;
      let row=rows[name],current=el.getAttribute(name);
      if (!row || current!==row.rendered) row={source:current};
      row.rendered=translate(row.source);rows[name]=row;
      if (current!==row.rendered) el.setAttribute(name,row.rendered);
    }
    attributes.set(el,rows);
  }
  function walk(node) {
    if (node.nodeType===3) {textNode(node);return;}
    if (node.nodeType!==1 || node.matches('script,style,textarea,[data-no-i18n]')) return;
    element(node); for (const child of node.childNodes) walk(child);
  }
  function chrome() {
    doc.documentElement.lang=locale==='en'?'en':'zh-CN';
    doc.title=locale==='en'?'ChefJeff · Cook together':'ChefJeff · 一起出餐';
    const toggle=doc.getElementById('kitchen-language');
    if(toggle){toggle.textContent=locale==='en'?'中文':'English';toggle.setAttribute('aria-label',locale==='en'?'Switch to Chinese':'切换到英文');}
  }
  function setLanguage(next) {
    if (!['zh','en'].includes(next)) return;
    locale=next;try{root.localStorage?.setItem('chefjeff-language',locale);}catch(_){}
    if(doc){walk(doc.body);chrome();root.dispatchEvent(new CustomEvent('kitchen-language-changed',{detail:locale}));}
  }
  if (doc) {
    function mount() {
      walk(doc.body);chrome();
      const toggle=doc.getElementById('kitchen-language');
      if(toggle)toggle.addEventListener('click',()=>setLanguage(locale==='en'?'zh':'en'));
      // Only changed DOM nodes are translated; no frame loop or game-state mutation.
      new MutationObserver(records=>{
        for(const record of records){
          if(record.type==='characterData')textNode(record.target);
          else if(record.type==='attributes')element(record.target);
          else for(const node of record.addedNodes)walk(node);
        }
      }).observe(doc.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','aria-label','title','label']});
    }
    if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
  }
})(typeof window !== 'undefined' ? window : globalThis);
