# SIRE package instructions

All work under this package follows the single workflow in `workflow/shared/sire/SKILL.md` and its mandatory [`references/global-contract.md`](workflow/shared/sire/references/global-contract.md). Keep all SIRE rules, scripts, role adapters, Markdown knowledge, and the shared SQLite database in this repository.

Claude and Codex must resolve their installed skill aliases to `workflow/shared/sire/`, knowledge to `knowledge/global/`, and database to `data/sire_vectors.sqlite3` through `workflow/shared/sire/scripts/sire_paths.py`. Do not add client-specific copies or databases.

Before changing the tracked database, create and verify an external backup. Keep credentials, personal app settings, model caches, SQLite sidecars, and R9 integrity snapshots out of Git. Use `tools/snapshot_db.py` for normalized snapshots. The Git database is the full archive; the explicitly requested light ZIP remains database-free.
