# SIRE workflow and knowledge export

Curated, reviewable export of SIRE v6 workflow materials and selected local knowledge-base content.

## Contents

- `workflows/sire/SKILL.md` and `workflows/sire/references/`: workflow specification and role, gate, knowledge, and review references.
- `database/sire/knowledge/records.jsonl`: two SIRE-related knowledge records from the local SQLite database.
- `database/sire/schema/summary.md`: schema and row-count snapshot.
- `database/sire/eval/` (queries.json, results.jsonl, run_eval.py): local retrieval evaluation set and runner.
- `database/sire/export-manifest.json`: export counts and exclusions.

## Export boundary

The raw database, WAL/SHM files, vector blobs, embedding cache, task/run journals, machine paths, session/message identifiers, and removed-record archive are intentionally excluded. This is a small curated snapshot, not a restorable database backup. Project-specific technical notes are not part of this workflow export.

Some workflow references include repository-specific development guidance; review before reuse elsewhere.
