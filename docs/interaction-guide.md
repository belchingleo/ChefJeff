# Interaction guide

Use a desktop/laptop browser with a keyboard and mouse, or try the experimental desktop controller or landscape touch controls. Phone and small touch viewport compatibility still needs real-device validation; see [device support](device-support.md). Full timing and item rules are in [gameplay rules](current-rules.md).

| Input / interaction | Behavior |
| --- | --- |
| WASD / arrows | Hold to move; release to stop |
| Shift | Dash while moving, with the shared cooldown |
| Space | Whatever the faced target needs (fetch, take, put, cook, plate, lift a pan or pot, chop, wash, extinguish, serve, bin); with nothing usable ahead, the nearest thing beside. With a throwable item in hand, a tap acts when released; empty-handed actions start on press. Stops chopping/washing, keeping progress |
| Hold Space | Holding a throwable item, hold for about 0.3 s to aim, whether facing a station or open floor. Turn with the direction keys and release to throw (to the partner when that way in range) |
| Esc or P / Ⅱ / ▶ / ■ | Esc or P pauses and resumes (P for keyboards without Esc, such as iPad) / pause / resume / end early (asks to confirm; restarting from pause also confirms) |
| Enter | Bookmark a moment; nearby marks merge into intervals |
| 1–5 / 6 | Cooperation preference / perceived mistake, with a shared cooldown; the dock (open by default) also takes clicks |
| Settings | Provider connection, language, next-round call limit, local memory, feedback |

## Experimental desktop controller

Requires a browser Gamepad API on `localhost` or HTTPS, initially targeting Chrome. Press a controller button if the browser has not discovered it. Only one active `standard`-mapped controller is used; the phone touch layout suppresses controller takeover. Real-controller testing is still pending.

| Standard controller input | Behavior |
| --- | --- |
| Left stick / D-pad | Move; center/release to stop. While aiming, changes the throw direction. The stick allows continuous directions; keyboard/D-pad directions use the eight discrete directions |
| A / × | Empty-handed actions start on press. Holding an item, a short press interacts on release; hold about 0.3 s to aim and release to throw, including in front of a station |
| X / □ | Dash while moving, using the existing speed, duration and cooldown |
| B / ○ | Cancel the current controller aim without throwing |
| Start / Options | Ready: start, or open Settings if no model is connected. Running: pause. Paused: resume. Results: no automatic restart |

Keep the keyboard/mouse for model setup, communication and menus; complete controller menu navigation is not included. Focus loss, backgrounding, disconnects, input fields, dialogs, keyboard/mouse takeover and new rounds clear controller input and cancel pending actions. Center the stick and release buttons before taking control again. An active-controller disconnect pauses the round; initial connection or an unused controller does not interrupt keyboard play. Paused rounds require explicit resume.

## Experimental touch controls

When the small-screen touch layout is active, the device must be in landscape to start or resume. Full-screen and orientation lock are optional browser features, not a requirement. The desktop controls above still work.

| Touch input | Behavior |
| --- | --- |
| Left joystick | Press anywhere in the lower-left area: the stick appears under your thumb. Push to move in any direction (360°), release to stop; diagonals do not increase speed. While aiming, it turns the throw (any angle) instead of moving |
| Action, empty hands | Interact on press, including fetching, chopping, washing and stopping ongoing work |
| Action, holding an item | Short press interacts on release. Hold about 0.3 s to stop and aim (the button reads Throw), including in front of a station; release to throw. When the other chef stands roughly on the aim line within reach, the trajectory bends to them and they are ringed in denim blue |
| Cancel while aiming | A round Cancel button appears above Action; slide the Action finger onto it (it turns red) and release to cancel, without throwing or interacting |
| Dash | Up and to the left of Action, on a diagonal arc. Tap while moving for 1.4× speed for 1 game second, then 3-game-second cooldown. Disabled while standing still or aiming |
| Communication / Bookmark | Expand the collapsed message panel for preset messages; bookmark uses the same timing and export rules as Enter |
| Pause / Menu | Pause and reach Settings, controls, round records and end-round controls without a keyboard |

The hand and hint line sits in the top toolbar, so nothing covers the kitchen. Supported Android browsers give a short vibration when aiming starts and when the throw leaves the hand. Movement and Action/Dash accept separate fingers. After aiming, let go of the joystick before pushing it again to move. Touch cancellation clears held input and cancels pending actions/throws. Turning to portrait, switching away or disconnecting also pauses a running round. After returning to landscape, resume manually. Settings fields retain normal text entry and paste. A phone still needs an accessible backend on a computer/server; its own `localhost` is not that server.

The cooking loop is fetch → board → chop → pan → heat → plate → serve → dirty return → sink → clean plate. Bread skips chopping; vegetables skip heating. Partial burgers accept missing ingredients in any order, with fixed visual layers. Pans, pots and plates retain identity through swaps/merges. Shared chopping/washing requires available operation sides; active workers resist contact pushes.

Space acts on what the chef faces (Overcooked-style); that station glows faintly and the bottom line names the action, and "hold Space · aim and throw" where a throw is possible. With a throwable item in hand, releasing a short press starts the target interaction; holding instead aims a throw, including in front of a station. An unavailable station interaction shows a reason and never drops the held item on the floor. Throws can cross equipment; walls and available landing places still constrain them. Once a quick pick-up or put-down starts, a direction pressed during it takes effect after it finishes. Ground interactions include pickup, swapping loose ingredients, filling/serving/swapping pans and pots; direct loose-vegetable-to-plate and plate-to-plate merging on the ground are future additions.

Hosted Settings additionally offer explicit contribution after the round, a data preview and deletion receipt. Hosted sessions do not use local disk memory. See [privacy](privacy-and-costs.md).

---

## 中文说明

# 交互指南

使用配备键鼠的电脑浏览器，或尝试试验版桌面手柄／横屏触控；手机及小尺寸触屏视口兼容性仍需真机验证，见[设备支持](device-support.md)。完整时间与物品约束见[玩法规则](current-rules.md)。

| 输入／交互 | 行为 |
| --- | --- |
| WASD／方向键 | 按住移动，松开停止 |
| Shift | 移动时冲刺，遵循共用冷却 |
| 空格 | 对面前的目标做需要的事（取料、拿起、放下、下锅、装盘、端锅、切菜、洗碗、灭火、出餐、丢弃）；面前没有可用的就用身边最近的。手持可投掷物品时，短按松开后操作；空手时按下立即操作。停下切菜／洗碗，进度保留 |
| 按住空格 | 手持可投掷物品时，面前是工位或空地都能按住约 0.3 秒瞄准：方向键改方向，松开扔出（队友在这个方向的射程内则扔给他） |
| Esc 或 P／Ⅱ／▶／■ | Esc 或 P 暂停与继续（P 用于没有 Esc 键的键盘，如 iPad）／暂停／继续／提前结束（需确认；暂停中重新开局也需确认） |
| Enter | 标记时刻，相近标记合并为区间 |
| 1–5／6 | 协作偏好／玩家认为出错，共用冷却；沟通面板默认展开，也可以用鼠标点 |
| 设置 | 接口连接、语言、下一局调用上限、本地记忆、反馈 |

## 试验版桌面手柄

要求浏览器在 `localhost` 或 HTTPS 页面提供 Gamepad API，首轮以 Chrome 为目标；未发现设备时可先按手柄按钮。只使用一个采用 `standard` 映射的活动手柄，手机触控布局启用时不接管。真实手柄验证仍待完成。

| 标准手柄输入 | 行为 |
| --- | --- |
| 左摇杆／十字键 | 移动，归中／松开停止；瞄准时调整投掷方向。摇杆支持连续方向，键盘／十字键使用八个离散方向 |
| A／× | 空手按下立即操作；持物时短按松开交互，长按约 0.3 秒瞄准、松开投掷，工位前也能投掷 |
| X／□ | 移动时冲刺，沿用当前速度、时长和冷却 |
| B／○ | 取消当前手柄瞄准，不投掷 |
| Start／Options | 准备时开局，未连接模型则打开设置；经营中暂停，暂停时继续；结算后不自动重开 |

模型设置、沟通和菜单仍用键鼠，本轮不包含完整手柄菜单导航。失焦、切后台、断连、输入框、对话框、键鼠接管及新局都会清理手柄输入并取消待执行动作，先让摇杆归中、按键放开后再接管。活动手柄断连会暂停，初次连接或尚未用于游戏的手柄不会打断键盘操作；暂停后需要明确继续，不自动恢复。

## 试验版触控

小尺寸触屏布局启用时，需要横屏才能开局或继续。全屏、横屏锁定是浏览器可选功能，不是运行前提；原有电脑键盘操作仍可使用。

| 触控输入 | 行为 |
| --- | --- |
| 左摇杆 | 在左下区域任意位置按下，摇杆出现在拇指下方。可朝任意方向（360°）移动，松手停止；斜走不加速。瞄准时改为调整投掷方向（任意角度），不移动角色 |
| 空手按「操作」 | 按下立即交互，包括取料、切菜、洗碗和中断当前工作 |
| 持物按「操作」 | 短按松开后交互；长按约 0.3 秒停下并瞄准（按钮显示「投掷」），站在工位前也一样，松开投掷。另一位厨师大致站在瞄准线上且在射程内时，抛物线会弯向他，并用牛仔蓝圈标出 |
| 瞄准时取消 | 操作键上方出现圆形「取消」键；按住操作的手指滑到上面（变红）后松开，取消本次瞄准，不投掷也不交互 |
| 冲刺 | 位于「操作」左上方，斜向弧形排列。移动时点击，以 1.4 倍速度持续 1 游戏秒，然后冷却 3 游戏秒。静止／瞄准时禁用 |
| 沟通／标记 | 打开默认折叠的沟通面板发送预设消息；标记与 Enter 使用相同时间与导出规则 |
| 暂停／菜单 | 不用键盘也能暂停、进入设置和操作说明、查看本局记录或结束本局 |

手中物品和提示显示在顶部工具栏，不遮挡厨房。支持的安卓浏览器在开始瞄准和投出时会轻微震动。移动与操作／冲刺可双指同时使用。瞄准结束后，先放开摇杆再推动，才恢复移动。触摸取消会清理持续输入、取消待执行交互／投掷；转竖屏、切后台或断线还会暂停正在进行的对局。恢复横屏后手动继续。设置输入框保留正常输入和粘贴。手机仍需访问电脑／服务器上的后端，手机里的 `localhost` 不是那台服务器。

做菜循环为取料→案板→切配→装锅→加热→装盘→出餐→脏盘回收→水槽→净盘。面包不切，蔬菜不加热。半成品汉堡按任意顺序补齐配料，显示层级固定。锅盘交换／合并仍保留各自身份。合作切菜／洗碗要求有可用操作侧，工作中的角色不被碰撞推离。

目标、高亮和提示指向同一对象。手持可投掷物品时，短按松开才执行目标交互，长按则瞄准投掷，站在工位前也一样。工位短按无效时会说明原因，不会把手里物品丢到地上，也不触发无关相邻操作。投掷可越过设备，仍受墙和可用落点约束。拿、放这类短动作开始后再按方向键，动作先完成再移动。地面支持拾取、散放原料换手、装锅／盛锅／换锅；地面散放蔬菜直接装盘和地面两盘合并留待后续。

托管设置另提供结束后的自愿数据贡献、预览和删除凭证，不使用本地磁盘记忆。详见[隐私说明](privacy-and-costs.md)。
