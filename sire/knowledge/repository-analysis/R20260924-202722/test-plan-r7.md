# R7 Functional Acceptance Results (Executed)

适用对象：SIRE SQLite 知识库写入，不包含产品 UI/App/设备控制。先完成 R6 分析稿复核，再依此顺序执行。

|编号|真实使用操作步骤|预期表现|实际表现|证据|结论|
|---|---|---|---|---|---|
|R7-DB-01|Used SQLite to count new repository records, task records, matching FTS entries and run `PRAGMA integrity_check`.|22 knowledge records (14 Git roots, 3 no-Git source projects, 4 module types, 1 map), 5 task records; integrity ok.|22 knowledge, 5 tasks, 22 FTS entries; integrity `ok`; total 120 knowledge / 578 tasks / 1372 chunks.|`evidence/U-05/qa/R7-DB-01.json`|PASS|
|R7-DB-02|Ran SIRE vector CLI searches for EncoderPlotter IAP and driverSoftware protocol/architecture terms.|Each query returns its new matching knowledge record with source path.|IAP query top hit `K-REPO-ENCODERPLOTTER-0903-01-20260924` (0.929740); driverSoftware query top hit `K-REPO-DRIVERSOFTWARE-20260924` (0.863834).|`evidence/U-05/qa/R7-DB-02.json` and `vector-search.log`|PASS|
|R7-DB-03|Searched the new FTS index and SIRE vector CLI with a unique absent sentinel.|No exact FTS match and zero CLI hits.|FTS matches 0; CLI exit 0 with 0 hits.|`evidence/U-05/qa/R7-DB-03-04.json`|PASS|
|R7-DB-04|Compared chunk count to the pre-write backup; counted new knowledge vectors and scanned this run for `.env` files/secret-assignment patterns.|Chunk count remains 1372; 22 new knowledge vectors; no `.env` artifact or secret assignment detected.|Chunks 1372 before/after; 22 new knowledge embeddings; 0 `.env` files and 0 assignment-pattern matches.|`evidence/U-05/qa/R7-DB-03-04.json`; backup `@USER_HOME@/SIRE-DB-Backups/sire_vectors-20260924-205427.sqlite3`|PASS|
|R7-DB-05|Called `sire_vector_db.py search` without a query; compared database counts and SHA-256 before/after.|CLI exits nonzero and database state is unchanged.|Exit code 2; knowledge/tasks/chunks/embeddings/keywords and DB hash unchanged.|`evidence/U-05/qa/R7-DB-05.json`|PASS|

R10 / 真实 UI 路径：跳过，具体原因是交付对象为只读分析结果与 SQLite 条目，没有用户界面变更、发布或设备操作。
