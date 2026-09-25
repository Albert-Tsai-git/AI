# Shared SIRE workflow archive

This package makes Claude and Codex use one maintained SIRE v6 skill, one Markdown knowledge base, and one tracked SQLite database from this Git checkout.

## Canonical paths

- Skill source: `workflow/shared/sire/`
- Claude role adapters: `workflow/shared/sire/agents/claude/`
- Knowledge: `knowledge/global/`
- Database: `data/sire_vectors.sqlite3`
- Snapshot sanitizer and verifier: `tools/snapshot_db.py`
- Repository/knowledge analysis: `knowledge/repository-analysis/`
- Current migration and restore contract: `knowledge/global/SIRE-MIGRATION.md`

The Claude skill entry (`~/.claude/skills/sire-global-workflow/`) and Codex entry (`~/.codex/skills/ai-dev-sire-workflow/`) must be directory links to the exact same `workflow/shared/sire/` directory. Claude's `sire-*.md` role entries likewise link to files under `agents/claude/`. The compatibility `sire_global` path, when used, links to `knowledge/global/`; it is not another copy.

`workflow/support/ai-workflow-governor/` is a separate general-purpose helper, not a second SIRE workflow. Historical v1 documents are retained only when explicitly labelled legacy; they are not active instructions.

The initial Codex/Claude source copies are preserved outside this repository; `source-manifest.json` maps each source copy to an existing `canonical_target` and records hashes for both sides. Its `source_roots` defines the local provenance tokens, and entries state when a source copy is outside the repository. Earlier source digest discrepancies are retained as provenance instead of being silently rewritten. Scripts, retrieval, and both installed application aliases use only `workflow/shared/sire/`.

## Database and knowledge

Both applications use `scripts/sire_paths.py` to resolve the same values. The repository database is the one shared by Claude and Codex and the database tracked by Git. It holds knowledge records, task records, chunks, embeddings, keyword data, FTS data, and last-run metadata. Do not create app-profile databases. Read commands (`search`, `show`, and `stats`) use read-only SQLite connections and must leave the database file unchanged. Database write entry points, including index, migration, and RSI, create a verified backup before mutation and share a per-database lock with snapshot publication, so they cannot race a Git snapshot.

The machine-level archive database (`@SIRE_ARCHIVE_ROOT@\sire_vectors.sqlite3`) remains a closure archive required by the shared global contract, not a second application database. In PowerShell, `$env:SIRE_ARCHIVE_ROOT` names the local directory represented by `@SIRE_ARCHIVE_ROOT@`, and `$env:SIRE_ARCHIVE_DB` is `Join-Path $env:SIRE_ARCHIVE_ROOT 'sire_vectors.sqlite3'`. At task close, sync reusable knowledge and the run ledger there, then refresh the tracked repository database from that archive through the snapshot tool. This ordering keeps the repository snapshot and its manifest in sync. `sire_rsi.py` writes RSI records to both databases (archive first) and `snapshot_db.py` refuses to publish if the repository database holds RSI records missing from the archive.

## Privacy and snapshot boundary

`knowledge/global/` contains normalized, reproducible knowledge. User settings, key material, model weights, integrity snapshots, SQLite WAL/SHM/journal files, and temporary database backups remain outside Git. A compatibility `integrity/` or `secrets/` directory may be linked to an external preserved location and is Git-ignored.

Refresh the tracked repository database after the closure archive has received the current knowledge and task ledger:

```powershell
$env:SIRE_ARCHIVE_DB = Join-Path $env:SIRE_ARCHIVE_ROOT 'sire_vectors.sqlite3'
python sire/tools/snapshot_db.py --source $env:SIRE_ARCHIVE_DB --dest sire/data/sire_vectors.sqlite3
```

Set `$env:SIRE_ARCHIVE_ROOT` to the machine-level root represented by `@SIRE_ARCHIVE_ROOT@` and `$env:SIRE_EMBED_DIR` to the already installed local model directory before snapshotting. These one-command shell values are not app-specific database overrides. Review `sire/data/snapshot-manifest.json`, confirm its snapshot hash equals the database SHA-256, run the listed R7 checks, and commit the database together with the workflow and knowledge changes. Never push unless the user asks.

The light workflow ZIP is a separate distribution format. It includes one `shared/sire/` source and shared Markdown knowledge, but omits the SQLite database and historical runs. The Git repository remains the complete archive.
