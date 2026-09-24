# 需求（用户原话："核实文件 没有风险就提交 然后继续"）

- REQ-01 核实暂停 run R20260924-192838 的 5 个未提交文件，无风险则提交。验收：独立重跑其 R7 脚本通过；diff 无敏感信息；提交后工作区干净。【已完成：31a3d7d / e537371】
- REQ-02 RSI 入口可达：SKILL.md 链接 self-optimization.md 并写明"改工作流前先 propose"。验收：SKILL.md 含 §Workflow changes (RSI) 与参考链接。
- REQ-03 R9 兜底：sire_supervisor.py 新增只读 rsi-check，并接入 finalize；工作流目录有未提交改动且最后提交后无未失败提案 → STOP(rc=3, rsi_unregistered_change)，且 finalize 不推进基线。验收：正常/异常/边界 CLI 实测。
- REQ-04 本次改动自身走 RSI：propose（已做）→ evaluate → activate。
- REQ-05 G6 归档：新增知识记录、reindex/index/migrate、meta、manifest 同步并本地提交，不 push。

非目标：sire_rsi.py status 改只读、evaluate 支持越低越好（另行提醒）；续跑暂停 run 的 U-07′/G5/G6。

## REQ-05 承接声明（R4 F-05）
- 工作流目录提交：U-04。
- G6 顺序（R0 执行，最终报告逐项给证据）：① P-20260925 写入 global_problem_solutions.md 并 SIRE_VECTOR_DB=归档库 reindex → ② R9 finalize/rsi-check（工作流已提交应 PASS）→ ③ sire_run.py finish --records P-20260925（SIRE_VECTOR_DB=归档库，内含 index/migrate）→ ④ meta 三键 → ⑤ snapshot_db.py 从归档库重建仓库库与 manifest → ⑥ 核对 manifest snapshot_sha256 == 仓库库 sha256、RSI 三表与提案 created_at → ⑦ 本地提交数据库/知识/run 台账，不 push。
