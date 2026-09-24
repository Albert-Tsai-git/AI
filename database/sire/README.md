# database/sire

SIRE 知识库（本地 SQLite `sire_vectors.sqlite3`）的精选导出，不是可恢复的备份；原始库、向量、任务日志均未提交。

| 名称 | 说明 |
| --- | --- |
| `schema/summary.md` | 表结构与行数快照、检索元数据 |
| `knowledge/records.jsonl` | 导出的知识记录（E-007、F-028） |
| `eval/queries.json` | 检索评测集（20 条） |
| `eval/results.jsonl` | 评测结果（recall@1 0.95 / @3 1.00） |
| `eval/run_eval.py` | 评测脚本（依赖本机 SIRE 脚本与 `D:\sire` 库，仅在本机可运行） |
| `export-manifest.json` | 导出计数与排除项 |
| `migrations/`、`seeds/` | 预留 |
