# Device support

| Device | Current support |
| --- | --- |
| Desktop/laptop browser with keyboard and mouse | Current target; use a WebGL-capable browser |
| Phone or small touch viewport | Experimental landscape touch controls; real-device validation pending |
| Large touch-only tablet | Touch controls do not enable automatically at large viewports; compatibility unverified |
| iPad with external keyboard and mouse | Existing keyboard input is available; iPad compatibility remains unverified |
| Desktop controller with standard Gamepad mapping | Experimental; requires browser Gamepad API, real-controller validation pending |
| Nonstandard controller mapping or other terminal | Not mapped; future work |

## Landscape touch trial

Touch controls enable automatically on small touch screens with a viewport whose shorter side is at most 600 CSS pixels and longer side at most 1400 CSS pixels. A standard large iPad viewport does not enable them automatically. These thresholds identify the trial layout; they do not establish compatibility with a particular device.

Open an accessible hosted game or a separately configured computer on your network in a WebGL-capable browser. The phone or small touch device runs the browser client; the Python backend runs on a separate computer or server. A phone's `localhost` points to the phone, not your computer. The desktop launcher binds locally by default and does not by itself expose a service to another device; see [hosted deployment](hosted-deployment.md). Browser-to-model requests on hosted games still require the provider to allow CORS, and use your own model account.

Touch devices show a landscape prompt in portrait and cannot start cooking until rotated. The page does not depend on browser orientation lock: some browsers cannot lock or force landscape, even when they support full screen. Rotating a running round to portrait, hiding the page or losing the connection clears held movement and cancels pending actions/throws, then pauses. Return to landscape and choose Resume manually.

The left joystick moves; releasing stops. On the right, Action does the same work as Space: empty-handed actions start on press; holding an item, a short press interacts on release, while a hold of about 0.3 seconds aims a throw. During aiming, the joystick changes direction and the chef stands still. Release Action to throw, or drag into the cancel area before releasing to cancel. After aiming, release the joystick before using it to move again. The Dash button triggers the existing 1.4× speed for 1 game second, followed by a 3-game-second cooldown; it is unavailable while standing still or aiming. The communication panel is collapsed on touch devices; open it to send the existing preset messages. Bookmark, pause and menu buttons provide the other keyboard functions. See [interaction guide](interaction-guide.md).

Desktop orders remain in the top horizontal rail. In the touch layout, orders use a 112 CSS-pixel-wide vertical column on the left, with vertical scrolling when needed. Each card shows the dish name, countdown, ingredient icons and patience bar. Missing ingredient artwork falls back to a text label.

**This is experimental support, not a claim of full phone compatibility.** Desktop browser emulation can check layout and input state, but does not establish iPhone Safari, Android Chrome, or iPad compatibility. Real-device checks must include:

- WebGL rendering, a complete round, performance and heat during play;
- two simultaneous fingers (move + Action/Dash), hold/release timing, pointer cancellation and screen-edge gestures;
- portrait/landscape changes, browser address bars, safe areas, full-screen exit and no unwanted resume;
- backgrounding, lock screen, interruption and reconnection without stuck movement or an unintended throw;
- API settings, paste/soft keyboard, model-provider CORS, sound unlock, records, export and optional contribution.

Use Safari or Chrome directly for the first trial. In-app browsers have not been validated. Record the device, operating system and browser versions with bug reports.

## Experimental desktop controller

Use a WebGL-capable desktop browser with the Gamepad API on `localhost` or HTTPS; Chrome is the initial browser target. The browser may not expose a connected controller until you press a button. Only one active controller reporting the browser's `standard` mapping is used; nonstandard mappings are not guessed. This does not change the desktop layout or take over input while the phone touch layout is active.

The left stick or D-pad moves; A/× interacts (with an item, a tap acts on release and a hold of about 0.3 seconds aims, then releases to throw). X/□ dashes, B/○ cancels a controller aim without throwing, and Start/Options starts a ready round or opens Settings if no model is connected, pauses a running round, or resumes a paused one. It does not restart a completed round. Model setup, communication and menu navigation still need the keyboard/mouse; this trial does not provide complete controller menu navigation. See [interaction guide](interaction-guide.md).

Losing focus, hiding the page, disconnecting, focusing an input field, opening a dialog, keyboard/mouse takeover or starting a new round clears held controller input and cancels pending actions. Center the stick and release buttons before taking control again; paused rounds never resume automatically. Disconnecting the active controller pauses play, while first connection or a controller not used for the game does not interrupt keyboard play. Real-controller compatibility remains unverified; scripted Gamepad/browser checks cannot establish hardware compatibility.

## Keyboard devices

The desktop controls are unchanged: held WASD/arrows move, Space interacts (hold it to aim a throw), Shift dashes, Enter bookmarks, 1–6 sends messages and Esc or P pauses. P is available for keyboards without Esc, such as the iPad Magic Keyboard; menus also take pointer input.

Apple documents [mouse support on iPad](https://support.apple.com/en-ie/guide/ipad/ipad10939edf/ipados), but accessory support alone does not establish game compatibility. An actual iPad validation pass should also record accessory versions and check held/simultaneous keys, repeat suppression, pointer buttons, input-field focus and a complete round. Desktop device emulation cannot substitute for these checks.

---

## 中文说明

# 设备支持

| 设备 | 当前支持情况 |
| --- | --- |
| 配备键鼠的台式机／笔记本浏览器 | 当前目标，需支持 WebGL |
| 手机或小尺寸触屏视口 | 试验版横屏触控，尚待真机验证 |
| 大尺寸纯触屏平板 | 大视口不会自动启用触控，兼容性尚未验证 |
| 外接键鼠的 iPad | 可使用现有键盘输入，iPad 兼容性尚未验证 |
| 标准 Gamepad 映射的桌面手柄 | 试验支持，需浏览器 Gamepad API，真实手柄验证尚待完成 |
| 非标准映射手柄或其他终端 | 暂不映射，后续开发目标 |

## 横屏触控试玩

触控界面在小尺寸触屏上自动启用：视口短边不超过 600 CSS 像素、长边不超过 1400 CSS 像素。常规大尺寸 iPad 视口不会自动启用；这些门槛只用于选择试验布局，不代表已经验证对应设备兼容性。

用支持 WebGL 的浏览器访问已有托管网站，或单独配置为可访问的局域网电脑服务。手机／小尺寸触屏设备只运行网页，Python 后端需在另一台电脑或服务器运行。手机里的 `localhost` 指向手机，不是你的电脑。默认电脑启动器只监听本机，不能直接供另一台设备访问；见[托管部署](hosted-deployment.md)。托管版浏览器直连模型仍要求服务商允许 CORS，调用使用你自己的模型账号。

触屏设备竖屏时显示横屏提示，不能开始经营，横过来后才能操作。页面不依赖强制横屏锁定：部分浏览器即使支持全屏，也不能锁定或强制旋转。对局中转回竖屏、切后台或连接中断，会停止持续移动、取消待执行交互／投掷，然后暂停；恢复横屏后需要手动点「继续经营」。

左摇杆控制移动，松手停止。右侧「操作」与空格执行相同动作：空手按下立即交互；持物短按松开交互，长按约 0.3 秒瞄准投掷。瞄准时角色停下，左摇杆改投掷方向；松开操作按钮投掷，或拖到取消区再松开取消。瞄准结束后，先放开摇杆再重新推动，才恢复移动。「冲刺」沿用 1.4 倍速度、持续 1 游戏秒、随后冷却 3 游戏秒；静止和瞄准时不可用。手机沟通面板默认折叠，打开后发送原有预设消息；标记、暂停和菜单按钮提供其余键盘功能。见[交互指南](interaction-guide.md)。

桌面订单仍位于顶部横栏；手机触控布局将订单放在左侧宽 112 CSS 像素的纵向列，内容超出时可上下滚动。每张卡片显示菜名、倒计时、材料图标和耐心条；缺少材料美术时显示文字标签。

**这是试验支持，不代表已经完成手机兼容验证。** 电脑浏览器模拟能检查布局和输入状态，不能证明 iPhone Safari、Android Chrome 或 iPad 已兼容。真机验证至少需要：

- WebGL 画面、完整一局、持续游玩的性能和发热；
- 双指同时操作（移动＋操作／冲刺）、长按松开、触摸取消和屏幕边缘系统手势；
- 横竖屏变化、浏览器地址栏、安全区、退出全屏及不会自动恢复；
- 切后台、锁屏、中断和重连后，不持续走动、不误投掷；
- API 设置、粘贴和软键盘、模型服务商 CORS、声音解锁、记录、导出及自愿贡献数据。

首次试玩建议直接用 Safari 或 Chrome；应用内置浏览器尚未验证。反馈问题时请附设备、系统和浏览器版本。

## 试验版桌面手柄

使用支持 WebGL 和 Gamepad API 的桌面浏览器，网页需要在 `localhost` 或 HTTPS 上打开，首轮以 Chrome 为目标。浏览器可能需要先按一下手柄按钮才会发现设备。只接管一个采用浏览器 `standard` 映射的活动手柄，不猜测非标准映射。桌面布局不变，手机触控布局启用时手柄不抢占输入。

左摇杆或十字键移动；A/× 操作（持物时短按松开执行交互，长按约 0.3 秒瞄准，松开投掷）；X/□ 冲刺；B/○ 取消当前手柄瞄准，不投掷；Start/Options 在准备阶段开局（未连接模型时打开设置）、经营中暂停、暂停时继续，结算后不自动重开。模型设置、沟通及菜单导航仍需键鼠，本轮不提供完整手柄菜单导航。见[交互指南](interaction-guide.md)。

失焦、切后台、手柄断连、聚焦输入框、打开对话框、键鼠接管或新一局开始后，都会清理持续手柄输入并取消待执行动作。摇杆先归中、按键先放开，才能重新接管；暂停的对局不会自动继续。活动手柄断连会暂停，而初次连接或尚未用于游戏的手柄不会打断键盘操作。真实手柄兼容性尚未验证，脚本注入的 Gamepad／浏览器检查不能证明硬件兼容。

## 键盘设备

电脑操作保持不变：按住 WASD／方向键移动，空格操作（按住可瞄准投掷）、Shift 冲刺、Enter 标记、1–6 发消息、Esc 或 P 暂停。没有 Esc 键的键盘（如 iPad 妙控键盘）可用 P；菜单也可以用鼠标点。

Apple 提供了 [iPad 鼠标支持说明](https://support.apple.com/en-ie/guide/ipad/ipad10939edf/ipados)，外设能连接不代表游戏已经兼容。实际 iPad 验证还需记录外设版本，检查持续／组合按键、重复处理、鼠标按钮、输入框焦点和完整一局；电脑模拟不能代替这些检查。
