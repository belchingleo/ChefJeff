# Security

Local and hosted services bind to loopback by default and validate Host and Origin. Expose the hosted runtime only through an HTTPS reverse proxy with isolated sessions and request limits; keep the Python port private.

Local play sends the key through the user's own Python backend. Remembering it saves a permission-restricted plaintext `.player-api.json`. The hosted client instead sends model requests directly from the browser: keys stay in page memory unless the player explicitly chooses browser localStorage. Both remembered forms are plaintext. See [privacy and costs](docs/privacy-and-costs.md).

Report vulnerabilities through GitHub private vulnerability reporting when enabled, or ask the maintainer for a private contact channel. Include build fingerprint, affected component and sanitized reproduction. Keep keys, exploit details and private logs out of public Issues. Revoke exposed credentials at the provider before cleaning files or history.

For releases, review the explicit file manifest, run offline tests and secret-marker checks, and verify a clean package. The Cocos web runtime requires `unsafe-eval`; the supplied CSP is one layer alongside session isolation, origin checks, limits and server sandboxing. Hosted contribution storage belongs outside the web root, with expiry and deletion enforced; access logs are disabled in the provided proxy templates.

---

## 中文说明

# 安全说明

本地与托管服务默认监听回环地址，并校验 Host 和 Origin。托管版本通过带会话隔离和请求限制的 HTTPS 反向代理提供访问，Python 端口保持不公开。

本地游玩由玩家自己的 Python 后端接收 Key；记住设备会保存权限受限的明文 `.player-api.json`。托管客户端由浏览器直接请求模型：默认仅在页面内存中保存 Key，主动选择记住后才进入浏览器 localStorage。两种记住方式均为明文。详见[隐私与费用](docs/privacy-and-costs.md)。

漏洞优先通过已启用的 GitHub 私密漏洞报告入口提交，或向维护者询问私下联系方式。提供构建指纹、受影响组件和脱敏复现方式，不在公开 Issue 发布 Key、利用细节或私人日志。真实凭据泄露后应先在服务商撤销，再清理文件和历史。

发布前审阅明确的文件清单，运行离线测试、敏感标记检查和干净包验证。Cocos 网页运行时需要 `unsafe-eval`；所配 CSP 与会话隔离、来源校验、限流、服务沙箱共同发挥作用。托管贡献数据库应位于网页目录之外，落实过期清理与删除；所提供代理模板关闭访问日志。
