---
name: sire
description: Use for every Claude or Codex task. Runs the shared SIRE workflow and reads and writes the repository's single knowledge base and SQLite database.
---

# SIRE v6 — Claude and Codex shared workflow

This is the sole SIRE workflow source for Claude and Codex. Both installed skill folders must resolve to this same directory. The knowledge directory and SQLite database also live in this repository. App-specific files may only provide discovery metadata or point to these shared resources; never keep a second writable workflow, knowledge base, or database.

Every response must include this exact line: `[SIRE v6] 已使用 SIRE 工作流执行当前任务`.

Before doing any task, read [`references/global-contract.md`](references/global-contract.md). It contains the user's complete mandatory SIRE process, output contract, R7/R10 real-scenario rules, and task-end archive requirement. This shared skill is the only workflow source; app-level instructions must point here rather than restate the rules.

## Shared locations

`scripts/sire_paths.py` is the only path authority. By default it resolves:

- Skill: `sire/workflow/shared/sire/`
- Markdown knowledge: `sire/knowledge/global/`
- SQLite database: `sire/data/sire_vectors.sqlite3`
- Model cache: outside Git

Claude and Codex must use the same values for `SIRE_ROOT`, `SIRE_DATA_DIR`, `SIRE_VECTOR_DB`, `SIRE_KB_DIR`, `SIRE_EMBED_DIR`, and `SIRE_TASK_ROOTS` when overrides are set. Do not configure app-specific data paths. Run scripts from this skill's `scripts/` directory or invoke the same script file through either installed alias. Never copy the database to an app profile.

The tracked SQLite file is both the shared working database and Git archive. SQLite `-wal`, `-shm`, and journal files are runtime-only and excluded from Git. Keep encryption keys, tokens, personal settings, integrity snapshots, and model weights outside this repository.

`search`, `show`, and `stats` must open the database read-only and must not create schema or switch journal mode. Only intentional `index`/`migrate` and archive operations may write; they must create a verified backup and keep the snapshot manifest in sync with the database hash.

## Whole-request contract

Treat the complete user request as one objective. Before decomposing, identify the goal, scope, inputs, outputs, acceptance criteria, dependencies, and authorized actions. If an ambiguity, contradiction, missing input, or acceptance gap could materially change the outcome, stop dependent work and ask a focused question; continue independent work that does not depend on the answer.

Every task uses the SIRE workflow, including analysis and simple requests. Before task analysis, search the shared local knowledge and vector database. At task end, store reusable knowledge, the task record, and validation results in the shared database. Do not skip retrieval, visible SIRE status, or archiving because a task seems small.

## Stages and role responsibilities

1. **R0 — Coordinator:** preserve the full request, scope, authorization, dependencies, unit status, blockers, and final closure.
2. **R1 — Knowledge retriever/curator:** extract search terms; search Markdown and SQLite/vector knowledge; read matching records; state reuse decisions and gaps; archive durable results and reindex.
3. **R2 — Requirements analyst:** define observable outcomes, scope, inputs, outputs, acceptance, dependencies, and authorization.
4. **R3 — Decomposer:** split work into smallest independently executable units with owner, read/write sets, dependencies, outputs, review, tests, and recovery.
5. **R4 — Plan reviewer:** independently check requirement coverage, unit overlap, dependency closure, testability, and read/write conflicts.
6. **R5 — Executor:** execute assigned units; state “执行中” and “执行完毕”; report artifacts, verification, assumptions, and blockers.
7. **R6 — Independent reviewer:** review each completed unit independently; reject failures and record the cause and repair. The author cannot approve their own work.
8. **R7 — Functional tester:** run the prelisted tests against real user paths and record actual behavior, evidence, and conclusions.
9. **R8 — Integrator:** verify cross-unit contracts, regressions, requirement coverage, and final usability.
10. **R9 — Closure auditor:** inspect scope coverage, privacy/security, related risks, archive completeness, and remaining optimizations. Fix related in-scope issues; report unrelated ones.
11. **R10 — Native computer operator:** perform authorized native-app/system operations when required. R10 does not review code or decide R7 results. If no UI/system action is needed, record “跳过” and why.

Parallelize units only when their read/write sets do not conflict and their dependencies are satisfied. After every unit, perform independent review and functional acceptance. A failed unit returns for repair. After three materially identical failures, stop that affected branch and report the reason; continue independent branches.

## Functional test rules

Before R7 starts, list each test ID, real user operation steps, expected behavior, actual behavior, evidence, and conclusion. For tasks involving an app, webpage, desktop program, file picker, system settings, device, publication, or user interface, use the real target and user interaction path; static inspection or function-only calls do not prove acceptance. Include a normal route and at least one boundary/error route. When a required tool, environment, or permission is unavailable, report `BLOCKED-无法真实验证`, never PASS. R10 performs authorized computer operations; R7 records the test conclusion.

## Output and evidence contract

Each stage and role must visibly report “执行中” and “执行完毕”. If skipped, say “跳过” and give the reason. At each stage boundary, list artifacts, verification results, and blockers. Keep the run ledger/evidence under the current run directory and repeat the complete stage/role log in the final report so users do not need to open it to learn the outcome.

Use the local run ledger and scripts when available. Record failed reviews/tests, repair actions, retry counts, and final evidence. Do not call a stage complete merely because a command returned successfully; inspect the resulting data and state.

## Shared database commands

Resolve the shared skill, database, and knowledge locations with `scripts/sire_paths.py`. The common commands are:

```powershell
python <SHARED_SKILL_DIR>\scripts\sire_kb.py search "keyword one keyword two" --run <RUN_DIR>
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py search --query "task summary" --json --limit 5 --run <RUN_DIR>
python <SHARED_SKILL_DIR>\scripts\sire_kb.py reindex
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py index
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py migrate
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py stats
```

On completion, archive reusable facts, search terms, decisions, limitations, validation results, and the task record to the shared database; update the shared Markdown index; and set `meta.sire_last_project`, `meta.sire_last_run`, and `meta.sire_last_status`. Commit the changed database, knowledge, workflow, and evidence to this Git repository. Do not push unless explicitly asked. Database migrations/indexing must keep a recoverable backup and verify row counts, FTS, vectors, and `integrity_check`.

## Workflow changes (RSI)

Any change to files in this shared skill directory is a workflow mechanism change. Before the first edit, register a proposal with `scripts/sire_rsi.py propose`; after verification, record metrics with `evaluate`, and `activate` only an `EVALUATED_PASS` proposal; `rollback` on regression. R9 `sire_supervisor.py finalize` (and the read-only `rsi-check`) returns `STOP` (`rsi_unregistered_change`) when this directory has uncommitted changes but no `PROPOSED`/`EVALUATED_PASS`/`ACTIVE` proposal was created after its last commit. Full rules: references/self-optimization.md §5.1.

## Supporting references

- Role and output details: [references/roles.md](references/roles.md)
- Knowledge and indexing details: [references/knowledge.md](references/knowledge.md)
- Gates and test evidence: [references/gates.md](references/gates.md)
- Vector database design: [references/vector-knowledge.md](references/vector-knowledge.md)
- Integrity and final review: [references/supervisor.md](references/supervisor.md)
- Learning, self-optimization, and RSI gate: references/self-optimization.md
- Claude adapter role files: [agents/claude/](agents/claude/)
- Codex discovery metadata: [agents/openai.yaml](agents/openai.yaml)

## ZIP packages

The Git repository holds the complete shared database and history. A light ZIP, when explicitly requested, does not include the SQLite database or run history; it must still include exactly one `shared/sire/` workflow source and clearly state the omitted data. Sensitive files (`secrets` directories and `.pem/.key/.pfx/.p12/.vault`) and old packages under the knowledge `exports` directory are never packaged. After packaging, R9 `verify-zip` checks its own required-entry list (a missing entry is `package_omission`) and rejects any sensitive file in the ZIP (`package_sensitive_leak`). Restoring a ZIP must reconnect both client aliases to the same repository copy.
