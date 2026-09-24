# Restore the shared SIRE workflow

The Git repository is the complete shared SIRE archive. Claude and Codex use one skill, one Markdown knowledge directory, and one tracked SQLite database from the same checkout.

## Restore on this computer

1. Clone or check out the repository to a path both Claude and Codex can access.
2. Preserve any existing SIRE skill and knowledge directories as backups.
3. Link both client skill entry directories to `<SIRE_ROOT>/workflow/shared/sire/`.
4. Link the legacy `sire_global` entry, if needed, to `<SIRE_ROOT>/knowledge/global/`.
5. Do not copy the database to either client profile. Keep the tracked database at `<SIRE_ROOT>/data/sire_vectors.sqlite3`.
6. Keep models, credentials, settings, `integrity/`, `secrets/`, and SQLite sidecars outside Git.
7. Resolve paths with `<SHARED_SKILL_DIR>/scripts/sire_paths.py`; ensure any environment overrides are identical in both applications.

## Verify after restore

Run `sire_paths.py` through both client entry points and compare `SHARED_SKILL_DIR`, `KNOWLEDGE_DIR`, and `DATABASE_PATH`. Run the shared database `stats`, a keyword `search`, and `PRAGMA integrity_check`. Confirm both skill entry paths resolve to the same `SKILL.md` file and all results reference the repository database.

A light workflow ZIP may omit the database and run history; it is not a replacement for this Git repository.
