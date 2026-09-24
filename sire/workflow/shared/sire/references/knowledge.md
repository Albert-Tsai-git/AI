# Shared SIRE knowledge base

## Authoritative locations

`<SIRE_ROOT>/knowledge/global/` is the canonical Markdown knowledge directory, and `<SIRE_ROOT>/data/sire_vectors.sqlite3` is the single shared database. Both are resolved by `scripts/sire_paths.py`. The old `<SIRE_ROOT>/knowledge/global/` location is only a compatibility alias when it points to this same directory; it must not hold a writable copy.

`global_index.json` is generated only by `sire_kb.py reindex`. The Markdown files are source documents; indexed records, chunks, vectors, task runs, and metadata are stored in the SQLite database.

## Search before work

R1 extracts several concrete keywords from the complete request and searches both Markdown and vector knowledge before R2 begins. Search once with the user's terms and once with synonyms or related subsystem terms. Read full records for relevant hits. Record the query, IDs, reuse decision (`reuse`, `adapt`, `reference-only`, `avoid`, or `none`), reason, and gaps in the run's `kb-hits.md`.

```powershell
python <SHARED_SKILL_DIR>\scripts\sire_kb.py search "keyword one keyword two" --run <RUN_DIR>
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py search --query "task summary" --json --limit 5 --run <RUN_DIR>
python <SHARED_SKILL_DIR>\scripts\sire_kb.py show P-001
```

An empty result is not an error; record it accurately and continue analysis. If the shared database does not exist or has no indexed records, index the canonical sources first. Never redirect one app to an empty substitute database to manufacture a no-hit result.

## Add and index reusable knowledge

Store durable implementation facts and technical decisions in `global_dev_features.md` (F), verified problem fixes in `global_problem_solutions.md` (P), durable workflow/tooling gains in `global_dev_efficiency.md` (E), and stable user preferences in `global_dev_habits.md` (H). Keep secrets, keys, private user settings, raw personal paths, unverified claims, and transient chatter out of the repository and database.

Use `sire_kb.py next-id <F|P|E|H>` to allocate an ID, append a reproducible entry with date, project, context, solution/decision, files, validation, limitations, and keywords, then run:

```powershell
python <SHARED_SKILL_DIR>\scripts\sire_kb.py reindex
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py index
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py migrate
```

Verify the record count increased, IDs are unique, the record is searchable, embeddings/FTS are refreshed, and SQLite reports `integrity_check=ok`. `global_knowledge_records.md` is a generated export; regenerate it from the database rather than editing it by hand.

## Task archive

Keep each run ledger and its validation evidence under `.sire/runs/<RUN_ID>/` in the project or `sire/runs/<RUN_ID>/` in this repository. Once the run is complete, migrate the run into the shared database and set the latest project/run/status metadata. Record only evidence needed for future reuse; do not index caches, secrets, model weights, integrity snapshots, settings, or SQLite sidecars.
