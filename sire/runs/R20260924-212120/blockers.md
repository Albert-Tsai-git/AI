# Blockers

## BLOCKER-UI-01 — Claude/Codex 桌面 UI 无法访问

- 状态：`BLOCKED-无法真实验证`。
- 受影响验收：R7-UI-01、R7-UI-02 及 R10 的原生应用启动/交互。
- 证据：`evidence/R7-UI-preflight.txt` 记录 CUA `apps=[]`，且当前接口无原生桌面应用控制能力。
- 已完成的旁路：共享目录联接、路径解析、CLI stats/search、读写保护与数据库快照可分别验证。
- 解除条件：Codex 与 Claude 桌面应用能在原生 UI 自动化环境中被发现和控制；随后执行正常及边界路径。
