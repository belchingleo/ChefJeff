# 第三方内容与分发范围

| 内容 | 来源与许可 | 本项目处理 |
| --- | --- | --- |
| Cocos Creator / Web 引擎 | Creator 3.8.8；随工程的 Cocos MIT 文本见 cocos-kitchen/THIRD_PARTY_LICENSE.md | 保留版权与许可文件；运行包包含 Creator 生成的 Web 引擎，不包含编辑器安装包 |
| 厨师、食物、设备与动画 | Images 生成素材、用户提供的美术参考及确定性切片；来源与提示记录在 art-candidates，接入说明见 docs/art/integration.md | 使用本地像素图集与节点动画，Graphics 保留为缺图回退；未从星露谷或 Overcooked 游戏程序提取贴图 |
| 字体 | 浏览器/操作系统 system-ui、sans-serif、monospace | 不随包分发商业字体文件 |
| Python | 运行所需系统 Python 3.10+ 标准库 | 不捆绑 Python 运行时；源码不要求第三方 Python 包 |
| 模型服务 | TypeSafe、DeepSeek 或玩家自选兼容接口 | 不包含模型权重；账号、服务条款、可用性与费用由所选服务决定 |

项目原创代码采用 AGPL-3.0-only，见 LICENSE 与 LICENSE-STATUS.md；根 LICENSE 不替代第三方许可，也不授予模型服务、玩家日志或研究数据的使用权。本清单对应当前像素图集版本；代码许可证不替代素材及参考图各自的权利条件。
