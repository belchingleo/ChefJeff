# Device support

| Device | Current support |
| --- | --- |
| Desktop/laptop browser with keyboard and mouse | Current target; use a WebGL-capable browser |
| Phone or touch-only tablet | Not supported |
| iPad with external keyboard and mouse | Candidate for future validation; not currently supported |
| Controller or other terminal | Roadmap |

Apple documents [mouse support on iPad](https://support.apple.com/en-ie/guide/ipad/ipad10939edf/ipados). Accessory support alone does not establish game compatibility. ChefJeff uses held movement keys, Space plus pointer input for throwing, double-tap sprint, right-click, and browser focus changes.

An iPad validation pass needs an actual iPad, iPadOS/Safari and accessory versions: check WebGL rendering, held and simultaneous keys, repeat suppression, pointer buttons/context menus, input-field focus, pause/resume after backgrounding, viewport scaling, and a complete round. Desktop device emulation cannot establish these results. The local Python backend must run on a separate computer or server for iPad play.

---

## 中文说明

# 设备支持

| 设备 | 当前支持情况 |
| --- | --- |
| 配备键鼠的台式机／笔记本浏览器 | 当前目标，需支持 WebGL |
| 手机或纯触屏平板 | 暂不支持 |
| 外接键鼠的 iPad | 后续待验证，当前不列入支持范围 |
| 手柄或其他终端 | 后续开发目标 |

Apple 提供了 [iPad 鼠标支持说明](https://support.apple.com/en-ie/guide/ipad/ipad10939edf/ipados)。外设能连接不代表游戏已经兼容：ChefJeff 使用持续移动按键、空格与鼠标组合抛掷、双击冲刺、右键和浏览器焦点切换。

iPad 验证需记录真机、iPadOS／Safari 和外设版本，检查 WebGL 渲染、持续／组合按键、按键重复处理、鼠标按钮与右键菜单、输入框焦点、切后台后的暂停恢复、视口缩放，以及完整一局。电脑模拟平板视口不能替代真机验证。iPad 游玩时，本地 Python 后端需在另一台电脑或服务器运行。
