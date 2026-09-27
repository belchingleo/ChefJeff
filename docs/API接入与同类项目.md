# Player-supplied model connections

Choose a provider in Settings, enter your own credentials, test the connection and start a round. TypeSafe Jev uses structured Choice requests; DeepSeek and compatible Chat Completions services use JSON action responses. A connection test may incur a provider charge.

The actor is Jeff (`jeff`) regardless of the selected model. Provider and model names retain their original spelling. A failed real-model request is reported and retried under the existing budget policy, without a scripted replacement.

Local play uses the user's Python backend; hosted play uses browser-direct model requests and requires provider CORS. Default and remembered credential storage differ between these modes; see [privacy and costs](privacy-and-costs.md). Adapter contracts, valid choices and extension steps are in [agent integration](agent-integration.md).

ChefJeff's community direction is real-time cooperation: shared equipment, material handoffs, task coordination and recovery from partner mistakes. The [README](../README.md) describes the open game and whole-session benchmark vision, including its Overcooked inspiration. Future comparisons should record partner, model, interface, language and latency conditions as well as outcomes.

---

## 中文说明

# 玩家自带模型连接

在设置中选供应商、填写自己的凭据、测试连接后开局。TypeSafe Jev 使用结构化 Choice 请求，DeepSeek 和兼容 Chat Completions 服务返回 JSON 动作。连接测试可能产生模型费用。

无论使用哪种模型，角色均为 Jeff（`jeff`）；供应商和模型名保持原名。真实请求失败会明确提示，并按既有额度规则重试，不用脚本替代。

本地版由玩家自己的 Python 后端请求模型，托管版浏览器直连并要求供应商支持 CORS。两种模式默认／记住凭据的方式见[隐私与费用](privacy-and-costs.md)，适配契约、合法选择及扩展步骤见 [agent 接入](agent-integration.md)。

ChefJeff 的社区方向是实时协作，包括共用设备、交接物品、协调任务及从伙伴失误恢复。[README](../README.md) 说明游戏与完整对局 benchmark 的共创愿景及 Overcooked 的启发。未来比较需同时记录搭档、模型、接口、语言、延迟条件与结果。
