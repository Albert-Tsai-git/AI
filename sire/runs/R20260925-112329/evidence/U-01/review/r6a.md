VERDICT: PASS
单元: U-01
方向: R6A 行为正确性
检查对象: evidence/change.diff；sire_paths.py:16-23，sire_rsi.py:1-105，tools/snapshot_db.py:332-365,453-455
结论: PASS
问题:
- [LOW] tools/snapshot_db.py:453 rsi_records_missing 用未 redact 的 tmp_conn 与已 redact 的 dest 比较；若 proposal_id/version/metric 含 D:/、C:/Users、邮箱或私网 IP，会误报"缺失"并永久拒绝发布。现有键为 ID/ISO 时间戳，实际触发概率低；建议对 before/after 两侧都做 redact 后再比较，或者在 redact 之后再检查。
- [LOW] sire_rsi.py:97-98 backup_before_mutation 在无 chunks 表的库上失败（sire_db_backup.py:32）；这是既有行为，真实库不受影响，但只含 RSI 表的临时库做不了第二次写入的测试。
- [INFO] 双写中途失败时只会"归档有、仓库无"，与单元 risk 声明一致；此时 rsi-check 读仓库库会 STOP，属可接受的失败方向。
验收对照: 满足
- 无归档且无 --repo-only 时拒绝（sire_rsi.py:85-86；实测 rc=1，未生成库）
- 先写归档库再写仓库库，两库共用 ts（sire_rsi.py:89,90,96-102；实测两库 created_at 相同）
- activate 在写入前逐库校验 EVALUATED_PASS（sire_rsi.py:92-97；实测 PROPOSED 时 rc=1，两库哈希不变）
- status 走 mode=ro + query_only，不建表也不备份（sire_rsi.py:59-72；实测 md5 不变，没有 -wal/-shm/-journal 边车）
- snapshot 保护：比较的键 proposal_id / version / (proposal_id,metric,created_at) 与 schema 一致；evaluate 在两库插入相同 ts，因此 metrics 键两库一致
行为路径: 正常路径 propose 双写已实测；evaluate 是逐库执行，metric 解析失败时会在写归档库阶段就退出，仓库库不受影响；--archive-db 与 --db 相同时去重，只写一次（sire_rsi.py:87）
越界检查: 无越界（U-01 文件集内）；已 grep 仓库，除 SIRE-MIGRATION.md:62 的变更记录文字外，代码中没有 references/governor 引用
技术债务: 上述 redact 比较口径（LOW）
我没跑过的: 在真实结构库副本上跑 evaluate/activate 成功路径和 snapshot_db 实际拒绝/发布；rsi-check 与 qa_all.py 回归
