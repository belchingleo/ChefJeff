# 参与开发

先阅读 README、docs/current-rules.md 和 docs/status.md。当前主线是本地 Cocos 网页和 Python 规则引擎；benchmark 场景与计分仍待设计。

1. 问题通过仓库 Issues 提交，使用问题模板。仓库尚未发布或未提供 Issues 时，先将本地反馈文件交给维护者指定的渠道；程序不自动上传。
2. 改动只覆盖具体问题，说明触发条件、修改前后行为、测试证据和未验证项。规则变化与模型提示变化分开说明。
3. Python 3.10+ 运行 `python3 -m unittest discover -s tests`；无需 API Key。运行 `python3 scripts/audit_release.py` 检查跟踪文件与历史中的敏感标记。不要把真实 Key 写进测试。
4. 前端构建需 Cocos Creator 3.8.8，执行 `python3 scripts/build_cocos.py web`；检查受影响视口及交互。源码仓库不依赖提交 Creator 缓存或本地设置。
5. 不在外部 PR 或离线 CI 中调用真实模型。真实跑分由维护者确认协议与预算后另行执行。
6. 不将模型失败替换为脚本救场。保留物品唯一性、相同行动规则和动作执行前后的校验。
7. 提交前检查 `git diff --check`；排除 `.env`、`.player-api.json`、`.player-memory.json`、原始对局日志、工具链及本机路径。反馈摘要不是完整回放证据。

项目原创代码采用 AGPL-3.0-only；贡献前需确认根 LICENSE 的适用条款，并确保有权贡献代码和素材。第三方内容需注明来源与许可证。项目名称不改变内部 `human` / `jev` actor ID，也不把厂商 TypeSafe Jev 改名为角色 Jeff。
