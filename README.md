# AI

统一收集和管理 AI 相关的所有内容：SIRE 工作流、SIRE 数据库、规则（Rules）、技能（Skills）、智能体、提示词、MCP 配置等。

## 目录结构

| 目录 | 内容 |
| --- | --- |
| `workflows/` | 工作流定义，`workflows/sire/` 存放 SIRE 工作流 |
| `database/` | 数据库相关，`database/sire/` 下分 `schema/`、`migrations/`、`seeds/` |
| `rules/` | AI 编码/行为规则（如 CLAUDE.md、Cursor rules 等） |
| `skills/` | Skills，每个技能一个目录，含 `SKILL.md`；模板见 `skills/_template/` |
| `agents/` | 子智能体（agent）定义 |
| `prompts/` | 常用提示词 |
| `mcp/` | MCP 服务器配置 |
| `docs/` | 说明文档、设计与笔记 |
| `scripts/` | 辅助脚本 |

## 约定

- 文件名使用小写短横线命名（kebab-case）。
- 每个新增条目在所在目录的 `README.md` 中登记一行说明。
- 不要提交密钥、令牌等敏感信息，使用 `.env`（已忽略）并提供 `.env.example`。

## SIRE 内容索引

- SIRE 工作流（v6 Skill 规范）：[`workflows/sire/`](workflows/sire/README.md)
- SIRE 数据库（结构摘要、精选知识、检索评测）：[`database/sire/`](database/sire/README.md)
- 导出说明与边界：[`docs/sire-export.md`](docs/sire-export.md)
