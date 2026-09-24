# REQ-001..003 需求与验收

## REQ-001：保存 SIRE 工作流规则与可执行源
- 意图：让该仓库内可查阅、维护 SIRE 工作流实现及 Codex/Claude 角色资料。
- 输入：Codex `ai-dev-sire-workflow` 与 `ai-workflow-governor`、Claude SIRE skill/role 文件、用户提供的 SIRE 执行规则。
- 约束：独立目录；保留上游文件结构和引用；排除 `.bak`、`__pycache__`、个人设置和密钥。
- 非目标：不改 `feishu-hub`；不改变轻量 ZIP 数据库排除政策。
- AC-001：工作流源文件有清单，README 可说明用途/来源；文件数、SHA256 与来源复核相符。

## REQ-002：保存 SIRE 知识与评测资源
- 输入：全局知识文档、评测集、移出知识档案、与本归档任务有关的记录。
- 约束：去机器绝对路径、邮箱/私网地址；不复制密钥库、环境配置备份、模型或 cache。
- AC-002：预期文件均可读且结构保留；排除清单在 manifest 记录；敏感模式扫描无命中。

## REQ-003：将 SQLite 知识库快照存入 Git 并安全校验
- 输入：机器级闭环归档 `@SIRE_ARCHIVE_ROOT@\sire_vectors.sqlite3`；Claude/Codex 活动工作库始终为仓库内 `sire/data/sire_vectors.sqlite3`。
- 约束：闭环源数据库不修改；通过可见已提交 WAL 的 SQLite 在线备份得到一致快照；数据库保留业务数据行数/表结构；规范化本机身份和路径；重建全文索引、处理向量文本哈希、VACUUM 清除历史空闲页；不纳入 WAL/SHM。
- AC-003：仓库副本 `PRAGMA integrity_check=ok`，行数/表清单与源一致，无路径/PII/凭据命中、无 sidecar；快照 manifest 记录脱敏和计数。

## Git 集成验收
- AC-004：`sire/` 归档文件均已进入本地 commit；现有 `feishu-hub/` 与之前提交保持不变；`git diff --check` 通过；提交后工作区干净；HEAD 仍在原本地基线后，未推送。

## REQ-004：重建索引时忽略备份快照和数据库导出副本
- 意图：保证打包到 Git 的全局知识索引不含重复旧记录。
- 输入：SIRE 的 `sire_kb.py` 知识文件发现逻辑。
- 约束：只跳过 `integrity/`、`secrets/`、`exports/` 和生成的 `global_knowledge_records.md`；保留 canonical Markdown。
- AC-005：临时样例含 canonical 记录及两个相同 ID 的备份/导出副本，CLI `reindex` 只生成一条 canonical 记录且无重复 ID 警告。
- AC-006：实际知识库重建无重复 ID 警告；新增 P-024 保持索引可检索。
