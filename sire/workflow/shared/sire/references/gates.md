# SIRE gates and evidence

This file defines the operational checklist used with the whole-request contract in [`SKILL.md`](../SKILL.md). Where wording differs, follow the user's current request and the shared skill.

## R1 — Knowledge retrieval

Before requirement analysis, search both the shared Markdown and SQLite/vector database. Capture at least two distinct searches, full-record reads for relevant hits, reuse decisions, and gaps in the run record. The source must resolve to the repository's shared knowledge and database; do not use an empty alternate path.

## R2 — Requirement analysis

For the full request, state the goal, scope, inputs, outputs, acceptance criteria, dependencies, authorization, risks, and non-goals. Every requirement must have an observable acceptance check. Stop dependent work when material ambiguity changes the result; continue independent work.

## R3/R4 — Decomposition and independent plan review

Split into the smallest useful units. Each unit has one main result, owner, read set, write set, dependency, artifact, acceptance test, review method, and recovery note if it changes state. The independent reviewer checks coverage, overlap, dependency closure, measurability, and write conflicts. Parallelize only non-conflicting ready units.

## R5/R6 — Execution and independent review

The executor records the change, commands, outputs, assumptions, and blockers. An independent reviewer checks the unit against its contract and inspects actual evidence. The author cannot approve their own work. On failure, record the defect and repair, then repeat review and test. Three materially identical failures stop only the affected unit.

## R7 — Functional acceptance

Before execution, list test ID, user operation steps, expected result, actual result, evidence location, and conclusion. Exercise the real user path for app/UI/system work, including one normal and one boundary/error route. For code, data, files, and Git, run the actual command/data path and inspect resulting state. Static inspection is supporting evidence only. If the required environment is unavailable, use `BLOCKED-无法真实验证`.

## R8/R9 — Integration and whole-task review

Check requirement coverage, cross-unit behavior, regressions, privacy/security, archive completeness, and remaining risks. Fix related in-scope optimizations. Report unrelated improvements separately. Do not close while a required unit lacks a passed review or test.

## R10 — Native computer operation

When the task requires an authorized native-app/system interaction, R10 performs the user path and records before/after state. R10 does not decide R7's conclusion. When no native operation is required, explicitly record “跳过” and the reason. If a required UI tool or environment is missing, record a blocked result rather than inferring success.

## Closure

R1 archives the durable task record and reusable knowledge in the shared database, updates the generated index, and verifies the result. Check database integrity, counts, searchability, and Git status. The final report repeats the complete stage/role status log, overall review, fixes, test evidence, archive result, blockers, and final state.
