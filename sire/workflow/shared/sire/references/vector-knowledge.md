# Shared SQLite and vector knowledge

## Storage model

- One database is resolved by `scripts/sire_paths.py`: `<SIRE_ROOT>/data/sire_vectors.sqlite3` by default.
- Knowledge sources are `<SIRE_ROOT>/knowledge/global/`, the shared skill source, and configured task roots.
- `SIRE_ROOT`, `SIRE_DATA_DIR`, `SIRE_VECTOR_DB`, `SIRE_KB_DIR`, `SIRE_EMBED_DIR`, and `SIRE_TASK_ROOTS` are common overrides. Claude and Codex must inherit identical values.
- The repository tracks the SQLite database itself. `-wal`, `-shm`, and journal files, temporary copies, models, and secrets stay outside Git.
- SQLite uses local FTS and stored embeddings. Model weights remain outside the repository; ordinary search should not require downloading a model.

## Commands

```powershell
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py search --query "task summary" --json --limit 5 --run <RUN_DIR>
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py show <CHUNK_ID> --json
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py stats
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py index
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py migrate
```

Search, show, and stats are read-only and belong at task start. Their SQLite connections must use `mode=ro` with `query_only`; retrieval must never create tables, run migrations, or switch journal mode. Schema changes belong to index/migrate. Before writing, keep a recoverable database backup. After a write, check counts, duplicate IDs, FTS results, embedding hashes, `PRAGMA integrity_check`, and the resulting Git diff.

## Retrieval record

The G0/run record stores the actual search queries, chunk paths/IDs, decision (`reuse`, `adapt`, `reference-only`, `avoid`, or `none`), reason, limitations, and any missing knowledge. Read the full associated chunk before reusing a result. A no-hit result does not stop work; continue the Markdown knowledge search and record the gap.

## Source indexing boundaries

Include canonical source Markdown, relevant workflow files, and approved run records. Exclude generated indexes and exports, `integrity/`, `secrets/`, settings, model caches, build output, and SQLite sidecars. Re-index the shared repository database only; never build app-specific vector databases.
