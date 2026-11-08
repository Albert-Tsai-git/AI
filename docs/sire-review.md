# SIRE v6 评审与待办

评审日期：2026-09-24。对象：`workflows/sire/`、`database/sire/`。

## 已在仓库中处理

| # | 问题 | 处理 |
|---|---|---|
| 1 | 向量库文档写 v1 哈希 384 维，F-028 记录 v2 bge 512 维 | `vector-knowledge.md` 改为 v2 描述，标注待本机核实 |
| 3 | 脚本分散在 `.claude` 旧目录与 `.codex` 新目录 | 命令统一为 `$env:SIRE_SCRIPTS`，SKILL 明确迁移要求 |
| 4 | “所有消息加载”与 description 冲突 | 改为仅开发类任务加载 |
| 5 | 流程过重 | 新增轻量 / 标准 / 完整三档通道 |
| 7 | 打包嵌套历史 zip 导致膨胀 | 历史 zip 只记哈希 |
| 9 | 知识 domain 错误 | F-028 → `sire`，E-007 → `devops` |
| 10 | 硬编码 Windows 路径 | 引入 `SIRE_HOME`/`SIRE_SCRIPTS`/`SIRE_DB`；F-028 正文与 `run_eval.py` 已脱敏 |

## 需在本机完成

- [ ] 运行 `sire_vector_db.py stats`，确认 encoder 是否为 bge v2（问题 1）。
- [ ] 核查 knowledge_records 98 → 77 条的差异（问题 2，违反“只增不减”）；若为误删，从 `opt-backup-20260924` 恢复。
- [ ] 将 `sire_run.py`、`sire_kb.py` 迁入新 Skill 的 scripts 目录，设置三个环境变量（本机 `SIRE_DB` 应指向实际库，如 D 盘路径）。
- [ ] `sire_bundle.py`、`sire_supervisor.py` 按新打包规则改为历史 zip 只记哈希。
- [ ] 同步 `workflows/sire/CHANGELOG.md` 到本机 `SIRE-MIGRATION.md`，跑一个代表性任务回归。
- [ ] 本机数据库中修正 F-028、E-007 的 domain。
- [ ] 评测集扩到 ≥50 条，拆出不参与调参的 holdout 集（问题 8）。
- [ ] R10 未接通时 UI 测试的替代方案（问题 6）：允许 Playwright 等自动化证据作为真实场景 PASS。
- [ ] 同步脚本（`sire_*.py`）和 rules 到本仓库。
