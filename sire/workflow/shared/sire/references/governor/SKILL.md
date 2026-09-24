---
name: ai-workflow-governor
description: Orchestrate non-trivial AI work through knowledge reuse, role-separated requirement decomposition, executable task units, mandatory per-unit review and functional tests, parallel lanes, remediation, and evidence-based closure. Use for multi-step builds, changes, analyses, research, and deliverables; skip only for trivial one-step requests.
metadata:
  short-description: 角色化拆解、复核、测试与知识沉淀闭环
---

# AI Workflow Governor

Use this skill as an execution protocol for any non-trivial request. The goal is to reduce routine human analysis and coordination while increasing quality through explicit roles, small verifiable units, immediate gates, and reusable knowledge.

Read [references/workflow-spec.md](references/workflow-spec.md) when the task needs the full role charter, state machine, evidence schema, or operating metrics. Read [references/templates.md](references/templates.md) when creating the task ledger, review records, test records, or knowledge-base entries.

## Non-negotiable invariants

1. Check for existing implementations, decisions, constraints, and tests before proposing work. Record the search and its result; do not silently reuse or ignore prior work.
2. Convert the request into atomic requirements with observable acceptance criteria, then decompose those requirements again into executable task units. Do not execute an unreviewed decomposition.
3. Every executable unit must have an owner role, inputs, output artifact, dependencies, acceptance criteria, review method, and functional test.
4. Immediately after each unit executes, run an independent review and a functional test. A unit is not complete until both pass and evidence is recorded.
5. An executor cannot be the sole approver of its own work. If only one model/agent is available, use separate labelled passes with fresh scrutiny and do not treat the execution narrative as review evidence.
6. Independent units may run in parallel, but every lane uses the same execute → review → test → remediate loop. A blocked lane must not stop independent lanes.
7. When review or testing fails, classify the defect, change the implementation or plan, and repeat the gates. After three materially identical failures, stop repeating the same approach, record an actionable blocker, and continue all unblocked work.
8. Mark the overall request complete only when every requirement maps to a passed unit and integration/end-to-end checks pass. Capture reusable knowledge and update the index before closing.
9. Never invent authorization for external, irreversible, sensitive, or high-impact actions. Escalate only the specific decision or permission that cannot be safely inferred; continue independent work.

## Roles as people

Treat these as distinct accountable roles, even when one model performs multiple passes. Each role must produce its stated output before the next gate.

- **Orchestrator** — owns scope, risk, dependency graph, ready queue, retries, and final closure; keeps work moving around blockers.
- **Knowledge Curator/Indexer** — searches existing knowledge and implementations before analysis, identifies reusable assets, and records new durable knowledge with an index entry.
- **Requirement Analyst** — extracts intent, constraints, non-goals, stakeholders, risks, and observable acceptance criteria.
- **Task Decomposer** — maps requirements into small executable units and dependencies; makes each unit independently verifiable.
- **Requirement Reviewer** — challenges coverage, ambiguity, sizing, ordering, and testability; rejects weak decomposition before execution.
- **Executor** — performs one approved unit and produces the requested artifact plus a concise change/decision record.
- **Work Reviewer** — checks the artifact against the unit contract, requirements, conventions, security/safety constraints, and regression risks.
- **Functional Tester/Validator** — runs the narrowest meaningful checks first, then broader checks as justified; records commands, inputs, expected result, actual result, and evidence.
- **Integrator/Closure Auditor** — verifies cross-unit contracts, end-to-end behavior, requirement coverage, and final evidence completeness.

If delegation is available, use separate workers for analysis, execution, and review. If not, simulate role separation with explicit headings and a fresh review pass. Do not let convenience remove a required gate.

## Mandatory operating sequence

### 0. Intake, scope, and risk

Classify the request as trivial or governed. For governed work, state the desired outcome, in-scope systems/files, out-of-scope items, constraints, and whether any action changes external state. Preserve existing user permissions and do not widen the task.

### Lightweight path and sparse-input rule

For a single-step, reversible, low-risk request with no material ambiguity, answer or edit directly and perform a quick semantic/syntax sanity check; do not manufacture a full KB/REQ/UNIT ledger just to add ceremony. If a short prompt is governed, infer only low-impact, reversible defaults and list them. When missing information would prevent a meaningful test, change scope, select a target, or authorize an external/high-impact action, create a blocker or decision packet and request only the exact missing input. Never invent files, data, credentials, targets, or acceptance criteria.

### 1. Knowledge-first check

The Knowledge Curator searches the workspace's established knowledge locations first, then relevant source/configuration/history and prior deliverables. Use fast local search such as `rg --files` and `rg` where appropriate. If the answer depends on current or niche external facts, browse only as needed and record sources.

Produce a `KB-Check` record containing:

- search scope and queries;
- matched implementations, decisions, templates, tests, or prior failures;
- what can be reused, adapted, or must be avoided;
- confidence and unresolved gaps.

If no knowledge base exists, create or nominate one under the task's workspace convention; do not hide the absence. At minimum maintain an index file and one structured entry per reusable decision or solution.

### 2. Requirement analysis

The Requirement Analyst creates `REQ-*` items. Each item must include: user outcome, business/technical intent, constraints, non-goals, inputs, observable acceptance criteria, risk, and evidence needed to prove acceptance. Resolve contradictions from available context; escalate only decisions that materially change scope, risk, or expected outcome.

### 3. Second decomposition into executable units

The Task Decomposer creates `UNIT-*` cards from the `REQ-*` items. A good unit has one primary outcome, bounded scope, explicit inputs and outputs, a named role owner, dependencies, an implementation approach, a review method, a functional test, and a recovery/rollback note when state can change.

The Requirement Reviewer must check the mapping `REQ → UNIT → evidence` and reject any unit that is too large, non-verifiable, missing a test, missing a dependency, or hiding multiple unrelated decisions. Return rejected work to analysis/decomposition; do not execute it.

### 4. Scheduling and parallel lanes

Build a dependency DAG and a ready queue. Run independent units concurrently when the environment and side effects permit it. Serialize units that share mutable state, conflict on files/resources, or depend on an unresolved decision. Each lane has its own unit card and evidence record. When one lane is blocked, mark the exact dependency and move to the next ready unit.

### 5. Per-unit closed loop

For every ready unit, perform exactly this gate sequence:

1. **Context load** — read the unit card and relevant `KB-Check` results; confirm assumptions and boundaries.
2. **Execute** — make the change, analysis, or artifact; record the output and notable decisions.
3. **Immediate independent review** — the Work Reviewer checks the result against the unit contract and risks. A pass must cite the inspected artifact or evidence.
4. **Immediate functional test** — the Functional Tester runs the unit's test and records reproducible evidence. For non-code work, use an equivalent validation such as schema check, source verification, render inspection, sample evaluation, or acceptance walkthrough.
5. **Remediate** — on either failure, record the defect, suspected cause, changed approach, and rerun both review and test. Do not close a unit on a partial pass.
6. **Unit closure** — set `UNIT-*` to `DONE` only when review and test both pass; attach the evidence and update downstream readiness.

Choose the unit test by domain, not by habit: games test rules, state transitions, input boundaries, and win/lose paths; music tests timing, duration, note/event structure, and render/playback where available; parsers test valid, missing, malformed, and boundary inputs; literature tests required motifs, length, structure, and consistency while a reviewer assesses voice and meaning; creative work tests its output schema, constraints, and internal consistency while a reviewer assesses originality and fit. Never use a structural test as proof of subjective quality.

### 6. Integration and final closure

The Integrator runs cross-unit contract checks, regression checks, and end-to-end acceptance. The Closure Auditor verifies that every `REQ-*` is covered, every `UNIT-*` is `DONE`, all failures are resolved or explicitly escalated, and the final artifact is usable in the requested context.

The Knowledge Curator then extracts only durable, reusable information: decision, context, solution, verification, limitations, and tags. Update the knowledge index with links to the entry and relevant artifact. Avoid recording secrets or transient noise.

## Decision and escalation policy

AI may decide implementation details, ordering, tool choice, test depth, and remediation strategy when they stay within the stated scope and constraints. Escalate a compact decision packet only for:

- ambiguous or contradictory acceptance criteria;
- missing authorization or a proposed irreversible/external action;
- privacy, security, legal, financial, medical, or safety impact requiring human judgment;
- a subjective trade-off with no inferable preference;
- an unavailable environment or repeated blocker that prevents meaningful verification.

The packet must state the blocker, why it cannot be inferred, 2–3 options, a recommendation, impact, and the exact input needed. Continue all safe independent units while waiting.

## Required evidence and status vocabulary

Maintain a task ledger using the templates in `references/templates.md`. Minimum fields are `REQ-*`, `UNIT-*`, role owner, dependency, artifact, review verdict, test verdict, retry history, blocker/escalation, and knowledge links.

Use these states consistently:

`INTAKE → KB_CHECKED → ANALYZED → DECOMPOSED → DECOMPOSITION_REVIEWED → READY → EXECUTING → REVIEWED → TESTED → DONE`

Failure returns to `EXECUTING` with a remediation record. A true external or human dependency uses `BLOCKED` with a next action and does not erase prior evidence. Overall `DONE` requires no uncovered requirement, no unverified unit, and a passing integration check.

An individual safe artifact may be `DONE` while another lane is `BLOCKED`. The overall task must remain `BLOCKED` or `NEEDS_INPUT` whenever a required requirement cannot be satisfied; do not report a partially blocked task as fully complete.

## Response contract

For governed work, expose a compact progress summary organized by: scope, KB reuse, requirement map, ready/blocked lanes, unit evidence, decisions/escalations, and final verification. Do not claim completion from intent or from a successful command alone; cite the concrete artifact and test result.
