VERDICT: PASS

# U-03 只读核验（以 mode=ro 打开 D:/sire/sire_vectors.sqlite3；证据：output.log）

- RSI-20260925-R9GATE：status=ACTIVE，created_at=2026-09-24T21:19:32.584126+00:00。
- improvement_metrics 中该提案有 3 行（rsi_rule_reachable、rsi_gate_tests_pass、regression_qa_all_pass），passed 都是 1。
- v6.2：ACTIVE，config_hash=ad38036a68f10c191e3ebc8ae85a57c6005b313f，等于 `git rev-parse HEAD:sire/workflow/shared/sire` 的结果。
- v6.1：RETIRED，retired_at=2026-09-24T22:42:54Z。
- PRAGMA integrity_check=ok。
- 附注：被查的库是 D:/sire/sire_vectors.sqlite3，与仓库内的 sire/data/sire_vectors.sqlite3 不是同一个文件（后者 47.8MB，mtime 05:19）。按派发要求只核验了前者。
- 本单元只做只读核验，没有设计异常路径用例。
