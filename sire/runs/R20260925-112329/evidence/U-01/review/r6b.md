VERDICT: PASS
VERDICT: FAIL
单元: U-01
方向: R6B 安全与边界
检查对象: evidence/change.diff（tools/snapshot_db.py rsi_records_missing、scripts/sire_rsi.py 双写/status、scripts/sire_paths.py archive_database_path、删除 references/governor）
结论: FAIL
问题:
1. (HIGH) 快照保护 fail-open：tools/snapshot_db.py rsi_records_missing 对目标库每表 SELECT 的 sqlite3.Error 一律 continue。目标库损坏/非 SQLite/被加密/被锁（SQLITE_BUSY）时返回 {}，随后 publish 用归档快照整体覆盖，仓库库独有 RSI 记录被静默丢失。临时库实验：dest 写入垃圾字节 -> 返回 {}（已验证，临时目录，未触碰真实库）。应仅对"no such table"放行，其余错误拒绝。
2. (MEDIUM) 误拒风险：保护检查（snapshot_db.py:453）在 redact（:470-481）之前执行，而目标仓库库是上次已脱敏的快照。若 RSI 键（proposal_id / metric / version）含 D:/code、D:/sire、用户目录、邮箱、私网 IP，dest 中为脱敏值、源为原值，永远判缺失 -> 快照永久被拒。未做实验，依据代码顺序推断。
3. (MEDIUM) 双写非原子且不可安全重试：sire_rsi.py main 逐库顺序加锁提交，归档成功而仓库失败后，重跑 evaluate 会以新 ts 在归档库重复插入 improvement_metrics（键含 created_at，不去重）；evaluate/rollback 在某库缺提案时 UPDATE 静默 0 行导致两库状态分叉，无检测。
4. (LOW) activate 前置校验在锁外（TOCTOU），校验与写入之间另一进程可改状态；且两库锁非同时持有。
5. (LOW) status 以 mode=ro 打开 WAL 库时仍可能创建 -shm/-wal 附属文件（SQLite 行为），非严格零写入；未验证。
风险场景: 1 需目标库不可读（损坏/并发锁），触发即数据丢失，非外部攻击面；2/3 为运维一致性风险。
边界核验: SQL 表/列名来自常量 RSI_KEYS，无注入；rsi 写 SQL 全参数化；archive_database_path 未设置返回 None 且写命令拒绝（fail-closed，正确），resolve() 相同则去重；dest 缺表 -> continue（合理），快照缺表 -> 判缺失（fail-closed，已实验验证）；备份与锁对两库各自生效；缺失清单输出含 RSI 键原文到异常信息（可能含未脱敏路径，LOW）；evaluate --metric 非法 float 在写归档后抛出前会在第一库部分失败——实际 split/float 在 apply 内，第一库回滚未提交，OK。
越界检查: 无越界（删除 references/governor 为计划内）
技术债务: 两库无分布式事务，可接受前提是补幂等（metrics 唯一键）与分叉检测。

## 第 2 轮复核（仅 HIGH + 2 MEDIUM，临时副本实验）
- HIGH 快照 fail-open -> 已修复：损坏目标库拒绝（"file is not a database"），目标库被 BEGIN EXCLUSIVE 锁住时拒绝（"database is locked"），只有 no such table 才跳过。临时库实测。
- MEDIUM 脱敏误拒 -> 已修复：比较前对来源键做 redact；dest '@CODE_ROOT@/x' 与源 'D:/code/x' 比较结果为 {}。实测。
- MEDIUM 双写 -> 已修复：重复 propose 被拒（两库都命中，实测）；非 propose 命令要求提案在各库都存在且状态一致，否则在任何写入之前就拒绝。归档库已 EVALUATED、仓库库仍 PROPOSED 时，重跑会被拒，不会重复插入 metrics（依据代码 sire_rsi.py main 写前校验段；状态分叉场景未能实测：临时库在 backup_before_mutation 阶段因缺 chunks 表失败，这是测试环境限制，与本改动无关）。
- 遗留 LOW：activate 前置检查在锁外、两库锁分别获取；status() 遇 sqlite 错误返回空，propose 在损坏库上的存在性判断会放行，但随后的备份/写入会失败，不静默。
第 2 轮结论: PASS
