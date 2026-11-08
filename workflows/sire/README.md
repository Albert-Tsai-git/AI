# workflows/sire

SIRE v6 工作流：当前以 Skill 机制执行（`ai-dev-sire-workflow`）。

| 名称 | 说明 |
| --- | --- |
| `CHANGELOG.md` | 本仓库对工作流的修改记录 |
| `SKILL.md` | 主规范：通道、门禁 G0–G6、角色 R0–R10、台账与证据 |
| `references/development-overlay.md` | 开发场景覆盖层（模型路由、工具权限、验证） |
| `references/role-boundaries.md` | 角色边界硬门禁 |
| `references/supervisor.md` | R9 监督员：完整性门禁 |
| `references/self-optimization.md` | 持续学习与自我优化规则 |
| `references/vector-knowledge.md` | 向量知识库使用说明 |

路径统一用环境变量 `SIRE_HOME` / `SIRE_SCRIPTS` / `SIRE_DB`（定义见 `SKILL.md`）。变更记录见 `CHANGELOG.md`，问题分析见 `docs/sire-review.md`。
