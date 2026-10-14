# Interface design

ChefJeff presents a warm pixel-art kitchen where players can read orders, workstation progress and held items while moving. The interface serves keyboard-and-mouse desktop play and experimental landscape phone touch play; real-device validation is pending.

## Visual system

Every colour is sampled from the art and shared by the canvas (`KitchenClient.ts` `COLORS`) and the web shell (CSS variables in `web-shell.html`). Surface `#f0d9b5` and paper `#fdf3e1` carry ink `#2b1a12` text; walnut `#6b3418` frames panels and the order rail; the page around the letterboxed game is dark wall planks `#4a2616`. Identity follows the sprites: the player's denim overalls give denim `#2a5a9e` (name tag, selected target, primary buttons), and white, copper-eared Jeff gets a paper tag with copper `#a8520e` text. Honey `#e8983a` (floorboards) highlights and warns, steel `#3d5566` marks neutral states, herb `#3c7a2a` means success and tomato `#b8321e` danger; status always carries a word or sign as well as colour. Shapes are square with 1–3px ink or walnut borders and hard, unblurred shadows; keyboard focus is a 3px ink ring outside the control. Titles, buttons, name tags and HUD numbers use the ChefJeffPixel face (a Fusion Pixel subset, `scripts/subset_pixel_font.py`) at 12/24/48px; body text stays in system fonts.

Desktop orders occupy the top horizontal rail as paper slips with recipe icons and herb/honey/tomato patience bars. The kitchen is the main interaction area, with the held item and next action below, results on the left and Jeff's status on the right. Pause, resume and end sit at the top right; ending or abandoning a round asks first. The communication dock follows the game's lower-left corner. Ready, pause and results share one overlay with a language switch; the pause overlay leads with Resume. Settings use tabs for connection, memory, call limit and export; Controls use a key map plus rule and level tabs.

In the experimental phone touch layout, orders form a 112 CSS-pixel-wide vertical column on the left and scroll vertically. Each card keeps the dish name, countdown, ingredient icons and patience bar; a missing ingredient sprite falls back to its text label. The desktop order rail is unchanged.

## Interaction and language

Selection outlines, hints and Space actions share a single target. Keyboard movement takes over from clicking, and unavailable targets explain why an action cannot run. Workstation progress, heat countdowns, chopping/washing effects and collision feedback reflect authoritative game state.

English and Chinese UI share an explicit translation catalog. Explanatory documents present English first, then Chinese. Keep credential storage and contribution consent language accurate for the local versus hosted runtime. Model names and actor IDs are identifiers, not translated labels.

`KitchenClient.ts` composes the game, `KitchenGeometry.ts` owns projection, `web-shell.html` hosts browser settings, and `i18n.js`/`i18n.json` handle translation. Inspect affected views and input flows in the actual browser after building; small viewport scaling does not establish mobile support.

---

## 中文说明

# 界面设计

ChefJeff 用温暖的像素厨房，让玩家在移动中看清订单、工位进度和持物。当前支持键鼠电脑和试验版手机横屏触控，手机真机验证尚待完成。

## 视觉系统

所有颜色都取自美术，画布（`KitchenClient.ts` 的 `COLORS`）与网页层（`web-shell.html` 的 CSS 变量）共用。底色 `#f0d9b5` 与纸色 `#fdf3e1` 上写墨棕 `#2b1a12` 文字；胡桃棕 `#6b3418` 做面板边框和订单轨道；游戏画面四周是深色墙板 `#4a2616`。身份色跟随角色：玩家的牛仔背带裤对应牛仔蓝 `#2a5a9e`（名牌、选中目标、主按钮），白色机身、铜色耳机的 Jeff 用纸色名牌配铜色 `#a8520e` 文字。蜂蜜木色 `#e8983a`（地板）表示高亮与警示，钢灰蓝 `#3d5566` 表示中性状态，香草绿 `#3c7a2a` 表示成功，番茄红 `#b8321e` 表示危险；状态除颜色外总带文字或符号。形状一律方角，1–3px 墨棕或胡桃棕描边，硬阴影不带模糊；键盘焦点是控件外 3px 墨棕色环。标题、按钮、名牌和 HUD 数字用 ChefJeffPixel 像素字（Fusion Pixel 子集，见 `scripts/subset_pixel_font.py`），字号 12/24/48px；正文使用系统字体。

桌面订单以纸条形式挂在顶部横栏，显示菜品图标和绿／黄／红三段耐心条。厨房为主要操作区，下方显示持物与下一步动作，左侧是结果，右侧是 Jeff 的状态。右上为暂停、继续和结束，结束或放弃对局前会先确认。沟通面板跟随游戏画面的左下角。准备、暂停和结算共用一个浮层并带语言切换，暂停浮层以「继续经营」为主按钮。设置分为连接、记忆、调用上限、导出四页；操作说明是键位图加规则、关卡分页。

试验版手机触控布局将订单放在左侧宽 112 CSS 像素的纵向列，支持上下滚动。每张卡片保留菜名、倒计时、材料图标和耐心条；材料精灵缺失时改为文字标签。桌面订单横栏保持不变。

## 交互与语言

选框、提示和空格操作共用目标。键盘移动接管点击，目标不可用时解释原因。加工进度、加热倒计时、切菜／洗碗特效和碰撞反馈对应权威游戏状态。

中英文界面共用明确的翻译表，说明文档英文在前、中文在后。凭据保存和贡献同意文案按本地／托管模式准确区分。模型名与角色 ID 是标识符，不作为标签翻译。

`KitchenClient.ts` 组合游戏，`KitchenGeometry.ts` 负责投影，`web-shell.html` 承载设置，`i18n.js`／`i18n.json` 提供翻译。构建后在真实浏览器检查受影响页面和输入流程；缩小视口不等于支持手机。
