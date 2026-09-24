# SIRE role charter

The shared [`SKILL.md`](../SKILL.md) is the canonical execution contract. This reference gives each role its output boundary; it does not create another approval gate or data source.

| Role | Responsibility | Minimum output |
|---|---|---|
| R0 Coordinator | Preserve the complete request and authorization, schedule work, track status, resolve dependencies, and close the task. | Scope, requirement/unit map, role log, blockers, final report. |
| R1 Knowledge retriever/curator | Search shared Markdown and SQLite before analysis; archive reusable knowledge and the task record after validation. | Queries, hits, reuse decision, gaps, knowledge ID, indexing result. |
| R2 Requirements analyst | Turn the complete request into observable requirements, boundaries, inputs/outputs, dependencies, and acceptance checks. | Requirements and risk/non-goal notes. |
| R3 Decomposer | Split requirements into atomic units with owners, read/write sets, dependencies, outputs, tests, review, and recovery. | Unit ledger and dependency graph. |
| R4 Plan reviewer | Independently check coverage, overlap, testability, dependencies, parallel conflicts, and authorization fit. | Pass/fail with findings and repair request. |
| R5 Executor | Complete assigned units and record decisions and actual command/output evidence. | Changed artifact, self-check record, assumptions, blockers. |
| R6 Independent reviewer | Inspect completed artifacts against requirements, safety, compatibility, and evidence. | Findings with path/line, severity, verdict, and required repair. |
| R7 Functional tester | Execute the prelisted real user/data path tests and inspect resulting state. | Actual steps, expected/actual, evidence, boundary result, verdict. |
| R8 Integrator | Check requirement coverage and cross-unit behavior after unit gates pass. | Coverage matrix, regression evidence, delivery status, remaining debt. |
| R9 Closure auditor | Check privacy/security, omissions, evidence completeness, and overall archive integrity. | Review status, findings, repairs, and unresolved unrelated items. |
| R10 Native computer operator | Operate authorized desktop/native system paths when required. | Before/after state and operation evidence; otherwise explicit skip reason. |

Every role records “执行中” and “执行完毕”. A skipped role records “跳过” and a reason. Each record lists artifacts, verification, and blockers. Keep full evidence in the run directory and repeat the complete role/stage log in the final answer.

## Independence and handoff

R6 must not be the author of the unit being reviewed. R7 must independently execute the test and may not use the executor's self-check as acceptance. R10 performs authorized native operations but does not decide R7's result. A failed review/test returns the affected unit to R5 with the precise defect and acceptance criterion; record the repair and rerun both gates.

## Knowledge handling

Read user preferences from `<SIRE_ROOT>/knowledge/global/global_dev_habits.md` when relevant. Search records through the shared scripts. R1 writes only durable facts that will help a later task reproduce a decision or fix; exclude secrets, tokens, private settings, and unnecessary personal data.
