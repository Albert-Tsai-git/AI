# SIRE package instructions

All work under this package follows the single workflow in `workflow/shared/sire/SKILL.md` and its mandatory [`references/global-contract.md`](workflow/shared/sire/references/global-contract.md). Keep all SIRE rules, scripts, role adapters, Markdown knowledge, and the shared SQLite database in this repository.

Claude and Codex must resolve their installed skill aliases to `workflow/shared/sire/`, knowledge to `knowledge/global/`, and shared working database to `data/sire_vectors.sqlite3` through `workflow/shared/sire/scripts/sire_paths.py`. The database is temporarily outside Git; keep an external backup as described in [`data/DATABASE-RECORD.md`](data/DATABASE-RECORD.md). Do not add client-specific copies or databases.

Before changing the shared working database, create and verify an external backup. Keep the database itself, credentials, personal app settings, model caches, SQLite sidecars, and R9 integrity snapshots out of Git. Use `tools/snapshot_db.py` for normalized snapshots. The external backup preserves the database; Git archives the workflow and knowledge. The explicitly requested light ZIP remains database-free.
