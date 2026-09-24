# Local SIRE SQLite database summary

Read-only snapshot inspected on 2026-09-24. Counts describe the local database at inspection time. Raw records and vectors are not included.

| Table | Rows | Purpose |
|---|---:|---|
| `chunks` | 1349 | indexed chunks and vector metadata |
| `knowledge_records` | 77 | curated knowledge records |
| `task_records` | 536 | task/run records (excluded) |
| `emb` | 1155 | embedding cache (excluded) |
| `keywords` | 5307 | keyword index |
| `synonyms` | 45 | synonym map |
| `knowledge_relations` | 0 | knowledge links |
| `improvement_proposals` | 2 | workflow improvement proposals |
| `improvement_metrics` | 3 | proposal evaluation metrics |
| `workflow_versions` | 1 | workflow version history |
| `meta` | 13 | index metadata |
| `cfts` | 964 | trigram full-text index |
| `kfts` | 77 | knowledge full-text index |

## Retrieval metadata

- Schema version: 2
- Embedding dimension: 384
- Encoder: `hash-ngram-v1`
- Retrieval: hybrid FTS5 and cosine similarity
- Knowledge table includes project-specific records; only selected workflow/knowledge entries are exported.
- Vectors, task journal rows, absolute paths, and credentials are not reproduced.
