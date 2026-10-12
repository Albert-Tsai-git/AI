# Run validation

- Canonical paths: `sire_paths.py` resolves shared SIRE root `D:\sire\AI\AI\sire`, knowledge `...\knowledge\global`, and repository DB `...\data\sire_vectors.sqlite3`.
- Machine-level archive confirmed by historical configuration naming `D:\sire\sire_vectors.sqlite3` the shared runtime DB, plus read-only SIRE schema, historical tasks, existing `sire_last_*`, and `integrity_check=ok`.
- H-005 added with `sire_kb.py add H`; `sire_kb.py reindex`, then `sire_vector_db.py index` and `migrate` completed for both databases. Both DBs have H-005 and current run tasks, FTS matches, embeddings, and `PRAGMA integrity_check=ok`.
- Parent R7/R8/R9 final review PASS: independent read-only checks confirmed H-005 exists once in each DB, database title exactly matches canonical Markdown, body length 900, full-title FTS query returns one result in each DB, current run has 13 task rows in both DBs, and `sire_last_run`/`sire_last_status` are correct (`R20261012-model-routing-preference` / `DONE`).
- Backups all verified `integrity=ok` under `C:\Users\Administrator\sire\db-backups`; latest archive/repository backups before this final ledger sync were `sire_vectors-20261012-082638-385857.sqlite3` and `sire_vectors-20261012-082652-464761.sqlite3`.
- R7 T1 PASS; T2 PASS as contract boundary review only; R10 skipped because no UI/native-app operation was in scope.
