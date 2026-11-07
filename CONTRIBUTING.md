# Contributing

Help build the cooperative game and its whole-session benchmark together. Contributions can include maps, recipes, assets, agent adapters, gameplay improvements, scenario-schema proposals, evaluation protocols, and player observations. Start with the [README](README.md), [rules](docs/current-rules.md), and [project status](docs/status.md).

1. Use repository Issues to describe a concrete problem or proposal. Include the trigger, expected behavior, and a sanitized reproduction.
2. Keep changes focused. Explain behavior changes and model-prompt changes separately, with relevant validation.
3. Run `python3 -m unittest discover -s tests` with Python 3.10+, and `node tests/hosted_browser_test.cjs` for browser credential flow. Offline tests require no real API key and must not write into the project's `logs/` folder: a test that needs real journals or session bundles points `CHEFJEFF_LOG_DIR` at a temporary folder (CI fails if `logs/` appears). Run `python3 scripts/audit_release.py` before sharing a build.
   Changes to game behaviour are checked against the behaviour fingerprints in `tests/golden/`: fixed scripted rounds per level whose event sequences must not change by accident. If a change is intended, explain it and regenerate them with `python3 tests/fingerprint.py --update`.
   Jeff's model input is checked the same way against the payload fingerprints in `tests/golden/payloads/`: fixed rounds in which Jeff is driven by the real decision loop with a scripted stand-in model, recording every request's payload and the exact bodies each client would send. A refactor must leave them unchanged; an intended change to the input is a model-prompt change, so explain it separately and regenerate them with `python3 tests/payload_fingerprint.py --update`.
4. Frontend changes use Cocos Creator 3.8.8 and `python3 scripts/build_cocos.py web`. Check affected browser views and interactions; omit Creator caches and personal settings from commits. The page refuses a kitchen server whose `client_protocol` differs from its own: when a change alters what the page and the server expect of each other, bump `release_info.CLIENT_PROTOCOL` and `CLIENT_PROTOCOL` in `KitchenClient.ts` together. A release alone does not need the web build rebuilt.
5. Keep real model calls out of external PR checks and offline CI. Agree on a protocol and budget before collecting live comparisons. Model failures remain visible instead of being replaced with a scripted teammate.
6. Run `git diff --check`. Exclude credentials, local configuration, raw logs, memory, contribution databases, and machine paths. Review feedback before sharing.
7. Write reader-facing documentation in English first, followed by a matching Chinese version. Put planned capabilities in the roadmap.

Canonical actor IDs are `human` and `jeff`. TypeSafe Jev, provider ID `jev`, model IDs such as `jev-latest`, and the vendor adapter module `jev.py` retain their names.

Original code is [AGPL-3.0-only](LICENSE). Contribute only code and assets you have the right to share, and include third-party attribution and license terms.

---

## 中文说明

# 参与共创

欢迎共同建设合作游戏与完整对局 benchmark。贡献可以包括地图、菜谱、美术、agent 适配器、玩法改进、scenario schema 提案、评估协议和玩家观察。从 [README](README.md)、[玩法规则](docs/current-rules.md)及[项目状态](docs/status.md)开始。

1. 通过仓库 Issues 描述具体问题或提案，提供触发条件、预期行为和不含秘密的复现方式。
2. 保持改动聚焦，分别说明玩法变化与模型提示变化，并提供相关验证。
3. Python 3.10+ 运行 `python3 -m unittest discover -s tests`；浏览器凭据流程运行 `node tests/hosted_browser_test.cjs`。离线测试不需要真实 Key，也不能往项目的 `logs/` 目录里写东西：需要真实日志或会话包的测试，把 `CHEFJEFF_LOG_DIR` 指到临时目录（CI 发现 `logs/` 就会失败）。分享构建前运行 `python3 scripts/audit_release.py`。
   玩法行为的改动会与 `tests/golden/` 里的行为指纹比对：每一关用固定脚本跑出的事件序列，不应意外改变。确属有意的改动，请说明原因，并用 `python3 tests/fingerprint.py --update` 重新生成。
   Jeff 的模型输入也用同样的方式，与 `tests/golden/payloads/` 里的输入指纹比对：在固定对局中，Jeff 由真实的决策循环驱动、由脚本代替模型作答，记录每次请求的输入，以及各客户端实际会发出的请求内容。代码整理必须保持它们不变；有意修改输入属于模型提示的改动，请单独说明原因，并用 `python3 tests/payload_fingerprint.py --update` 重新生成。
4. 前端使用 Cocos Creator 3.8.8，通过 `python3 scripts/build_cocos.py web` 构建并检查受影响页面和交互，不提交 Creator 缓存或私人设置。页面只连接 `client_protocol` 与自己一致的厨房服务：改动若改变了页面与服务器之间的约定，就同时把 `release_info.CLIENT_PROTOCOL` 和 `KitchenClient.ts` 里的 `CLIENT_PROTOCOL` 加一；只是发新版本不需要重新构建网页。
5. 外部 PR 检查与离线 CI 不调用真实模型。实时对照需先确定协议与预算；模型失败明确显示，不以脚本队友替代。
6. 提交前运行 `git diff --check`，排除凭据、本地配置、原始日志、记忆、贡献数据库及本机路径；分享反馈前先检查内容。
7. 面向读者的说明采用英文在前、中文在后的对应版本；计划能力集中写入路线图。

统一角色 ID 为 `human` 和 `jeff`。供应商 TypeSafe Jev、provider ID `jev`、`jev-latest` 等模型名及供应商适配模块 `jev.py` 保持原名。

原创代码使用 [AGPL-3.0-only](LICENSE)。请确认有权贡献代码和素材，并注明第三方来源及许可。
