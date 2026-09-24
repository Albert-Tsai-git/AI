# SIRE workflow and knowledge export

Curated, reviewable export of SIRE v6 workflow materials and selected local knowledge-base content.

## Contents

- `workflow/SKILL.md` and `workflow/references/`: workflow specification and role, gate, knowledge, and review references.
- `knowledge-records.jsonl`: two SIRE-related knowledge records from the local SQLite database.
- `database-summary.md`: schema and row-count snapshot.
- `eval-queries.json`, `eval-results.jsonl`, `run-eval.py`: local retrieval evaluation set and runner.
- `export-manifest.json`: export counts and exclusions.

## Export boundary

The raw database, WAL/SHM files, vector blobs, embedding cache, task/run journals, machine paths, session/message identifiers, and removed-record archive are intentionally excluded. This is a small curated snapshot, not a restorable database backup. Project-specific technical notes are not part of this workflow export.

Some workflow references include repository-specific development guidance; review before reuse elsewhere.
