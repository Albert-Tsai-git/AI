# G0 知识检索回执

| # | 检索词 | 命中 | 判定 | 理由 |
|---|---|---|---|---|
| 1 | `sire_kb.py search "RSI 自我优化 改进提案 工作流版本 回滚"` | 27 条（F-019/F-024 等） | avoid | 均为 "RSI" 子串误命中 "VERSION"/"supportedVersions"，与 RSI 无关 |
| 2 | `sire_vector_db.py search --query "SIRE 工作流 RSI 递归自我改进 角色 流程"` | P-20260924（共享源+SQLite 单一 Git 源） | reference-only | 说明 RSI 写入口须持锁并备份；本任务 RSI 写入沿用 sire_rsi.py 的锁与备份 |
| 3 | 只读 SQL：improvement_proposals / workflow_versions | 2 条提案（09-21 冒烟）、活动版本 v6.1 | reference-only | 作为基线：此前工作流改动未登记 RSI |

缺口：知识库无"RSI 如何触发 / 未接线"的记录 —— 本任务结束时补 P 记录。

判定: 部分可参考
