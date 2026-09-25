

### E-008: SIRE 单一来源收敛与 RSI 双库写入

**日期**: 2026-09-25
**项目**: SIRE v6 Claude/Codex 共享工作流
**状态**: 已验证（run R20260925-112329，RSI-20260925-SYNC → v6.3）
**关键词**: SIRE, 单一来源, governor, ai-workflow-governor, Codex skill, 目录联接, RSI, sire_rsi, 归档库, SIRE_ARCHIVE_ROOT, SIRE_ARCHIVE_DB, snapshot_db, RSI 丢失保护, fail-closed, WAL

## 场景
复查"Claude/Codex 共用一份 SIRE"时发现：governor 有三份副本（support/、shared/sire/references/governor、Codex 独立 skill）；RSI 只写仓库库而收尾快照从归档库重建仓库库，RSI 记录会丢失；归档库为 WAL 模式时快照工具报"source -wal changed"。

## 做法
- governor 只保留 `sire/workflow/support/ai-workflow-governor/`（sire_run/sire_bundle 引用的路径），删除 shared 下副本并清理 source-manifest；Codex 独立 governor 移到 `~/.codex/skills-backup/`，Codex 只加载 SIRE 联接。
- `sire_rsi.py` 写命令先写归档库再写仓库库（`SIRE_ARCHIVE_ROOT`/`SIRE_ARCHIVE_DB`/`--archive-db`，解析不到则拒绝，测试用 `--repo-only`）；写前两库一致性预检，禁止重复 propose；`status` 只读。
- `snapshot_db.py` 发布前比较 RSI 三表键（脱敏对齐），仓库库有而归档库无、或目标库无法校验时拒绝发布。
- 快照前若归档库是 WAL 模式，先 checkpoint 并切 DELETE 日志模式。

## 验证
R4 两轮、R6A/R6C PASS、R6B 两轮 PASS、R7 T1–T10 在最终版 PASS；两库 v6.3 ACTIVE 一致。

## 限制
activate 前置检查在锁外、两库锁分别获取（LOW）；执行 RSI 写命令需在 shell 设置 SIRE_ARCHIVE_ROOT（本机为归档库所在目录）。
