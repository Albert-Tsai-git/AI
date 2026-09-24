# R9 — shared-source and archive review

R9 checks that Claude and Codex still use one repository source, that no required SIRE files were omitted or lost, and that the database/knowledge snapshot is safe to commit. The root [`SKILL.md`](../SKILL.md) defines the whole-task review contract.

## Canonical content

- `sire/workflow/shared/sire/` is the single SIRE workflow.
- `sire/knowledge/global/` is the single canonical Markdown knowledge directory.
- `sire/data/sire_vectors.sqlite3` is the single shared client database and Git snapshot.
- `scripts/sire_paths.py` must resolve the same database and knowledge path through both client aliases.
- Run ledgers are under `.sire/runs/<RUN_ID>/` or `sire/runs/<RUN_ID>/` and migrate into the shared database at closure.

App skill aliases and Claude role entry files may live in client configuration directories only as links to the shared repository resources. Local integrity evidence, user settings, model weights, credentials, and SQLite sidecars remain outside Git.

## Checks

Run `scripts/sire_supervisor.py preflight`, `start --run-id <RUN_ID>`, `check --run-id <RUN_ID> --unit-id <UNIT_ID>`, and `finalize --run-id <RUN_ID>` when applicable. Before close:

1. Resolve both app skill folders and confirm each targets the same repository skill directory.
2. Confirm the shared path resolver returns the same database and knowledge files from either installed entry.
3. Confirm the database file is tracked and that no `-wal`, `-shm`, or journal sidecar is staged.
4. Compare knowledge against the preserved source inventory; ensure private directories and model caches remain outside Git.
5. Inspect source manifests and package manifests for missing or duplicate SIRE rule sources.
6. Verify database integrity, core table counts, FTS search, embedding references/hashes, and last-run metadata.
7. Review staged blobs for credentials, private keys, machine-specific absolute paths, and database sidecars.

If a required source file is missing, a link points to a divergent copy, or the database is corrupt, record `STOP` with the exact artifact and last known state. Do not silently reconstruct private materials or erase prior evidence. Declared changes are recorded with before/after hashes and reason.

## ZIP scope

Only package a ZIP when the user explicitly requests “打包工作流”. A light ZIP includes one `shared/sire/` source and shared knowledge, but intentionally excludes the tracked SQLite database and history; the Git repository remains the complete archive. The ZIP manifest must name those omissions and restore both app links to the same shared directory.
