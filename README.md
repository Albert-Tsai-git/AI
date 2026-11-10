# AI

AI 相关内容的集合库：SIRE 工作流与知识库、飞书多 AI 中转服务，以及预留的 rules / skills / agents / prompts / mcp 分类目录。

## 目录结构（2026-11-10 确认）

| 目录 | 状态 | 内容 |
| --- | --- | --- |
| `sire/` | 使用中（核心） | SIRE v6 唯一正本，Claude / Codex / Qoder 共用，详见 [`sire/README.md`](sire/README.md)：`workflow/shared/sire/` 技能与脚本、`knowledge/` 知识库与决策记录、`data/` 数据库说明（SQLite 本体在本机，不进 Git）、`tools/` 快照脱敏校验、`eval/` 检索评测 |
| `feishu-hub/` | 使用中 | 飞书多 AI 中转服务（hub + Claude / Codex / Qoder 执行器 + Stop Hook 完成通知），见 [`feishu-hub/README.md`](feishu-hub/README.md) |
| `feishu-bridge/` | 已被取代，暂留 | 早期飞书桥（TypeScript），已被 `feishu-hub/` 替换，计划任务 `FeishuClaudeBridge` 已禁用；`docs/feishu-ai-hub-design.md` 引用它，确认无用后可删 |
| `docs/` | 使用中 | `feishu-ai-hub-design.md`：飞书 × 多 AI 中枢方案设计 |
| `skills/` | 预留 | 个人 Skill，每个技能一个目录含 `SKILL.md`，模板见 `skills/_template/` |
| `rules/` | 预留 | AI 编码/行为规则（CLAUDE.md、Cursor rules 等） |
| `agents/` | 预留 | 子智能体定义 |
| `prompts/` | 预留 | 常用提示词 |
| `mcp/` | 预留 | MCP 服务器配置 |
| `scripts/` | 预留 | 辅助脚本 |

2026-11-10 已移除早期遗留的 `workflows/`、`database/` 和 `docs/sire-export.md`：内容已被 `sire/` 正本取代（知识记录 E-007/F-028 已在 `sire/knowledge/global`，评测集 `sire/eval` 一致），仍有价值的变更记录与评审结论迁入 `sire/knowledge/decisions/`。

## 约定

- 新增内容放入对应目录，并在该目录 `README.md` 登记一行说明；文件名使用小写短横线命名。
- 文档默认使用中文；禁止提交任何密钥、令牌，使用 `.env`（已忽略）并提供 `.env.example`。
- SQLite 数据库、遥测库、运行台账、通讯数据都在本机（`D:\sire\`），不进 Git，见 `sire/data/DATABASE-RECORD.md`。
