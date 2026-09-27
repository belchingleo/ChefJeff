# Interface design

ChefJeff presents a warm pixel-art kitchen where players can read orders, workstation progress and held items while moving. The interface serves keyboard-and-mouse desktop play; other terminals are part of the roadmap.

## Visual system

Wood brown `#795539` frames the kitchen; cream `#fff5dc` supports panels; ink brown `#382f29` provides readable text. Green `#4c7661` identifies the human and selected work area, blue `#567fa4` identifies Jeff, and red `#b64032` signals urgency/fire/discard. Names and state text supplement color. System fonts keep small text readable; art comes from local atlases.

Orders occupy the top rail with recipe icons and patience bars. The kitchen is the main interaction area, with current action hints below. Pause, resume and end controls sit at the top right; fixed communication options are accessible at the lower left. Ready, pause and results use a consistent overlay. Settings separate connection, language, call budget and feedback.

## Interaction and language

Selection outlines, hints and Space actions share a single target. Keyboard movement takes over from clicking, and unavailable targets explain why an action cannot run. Workstation progress, heat countdowns, chopping/washing effects and collision feedback reflect authoritative game state.

English and Chinese UI share an explicit translation catalog. Explanatory documents present English first, then Chinese. Keep credential storage and contribution consent language accurate for the local versus hosted runtime. Model names and actor IDs are identifiers, not translated labels.

`KitchenClient.ts` composes the game, `KitchenGeometry.ts` owns projection, `web-shell.html` hosts browser settings, and `i18n.js`/`i18n.json` handle translation. Inspect affected views and input flows in the actual browser after building; small viewport scaling does not establish mobile support.

---

## 中文说明

# 界面设计

ChefJeff 用温暖的像素厨房，让玩家在移动中看清订单、工位进度和持物。当前面向键鼠电脑，其他终端列入路线图。

## 视觉系统

木棕 `#795539` 组织厨房边框，奶油白 `#fff5dc` 用于面板，墨棕 `#382f29` 保证文字可读。绿 `#4c7661` 标识人类和选中工位，蓝 `#567fa4` 标识 Jeff，红 `#b64032` 表示紧急／火情／丢弃；名字与状态文字补充颜色信息。小字号使用系统字体，美术读取本地图集。

订单位于顶部横栏，显示菜品图标与耐心条。厨房为主要操作区，下方提供当前动作提示。右上为暂停、继续和结束，左下提供固定沟通。准备、暂停和结算使用一致浮层，设置区分连接、语言、额度与反馈。

## 交互与语言

选框、提示和空格操作共用目标。键盘移动接管点击，目标不可用时解释原因。加工进度、加热倒计时、切菜／洗碗特效和碰撞反馈对应权威游戏状态。

中英文界面共用明确的翻译表，说明文档英文在前、中文在后。凭据保存和贡献同意文案按本地／托管模式准确区分。模型名与角色 ID 是标识符，不作为标签翻译。

`KitchenClient.ts` 组合游戏，`KitchenGeometry.ts` 负责投影，`web-shell.html` 承载设置，`i18n.js`／`i18n.json` 提供翻译。构建后在真实浏览器检查受影响页面和输入流程；缩小视口不等于支持手机。
