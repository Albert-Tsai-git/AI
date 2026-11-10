---
name: sire
description: Use for every Claude, Codex or Qoder task. Runs the shared SIRE workflow and reads and writes the repository's single knowledge base and SQLite database.
---

# SIRE v6 — Claude, Codex and Qoder shared workflow

This is the sole SIRE workflow source for Claude, Codex and Qoder. Both installed skill folders must resolve to this same directory. The knowledge directory and SQLite database also live in this repository. App-specific files may only provide discovery metadata or point to these shared resources; never keep a second writable workflow, knowledge base, or database.

Every response must include this exact line: `[SIRE v6] 已使用 SIRE 工作流执行当前任务`.

Before doing any task, read [`references/global-contract.md`](references/global-contract.md). It contains the user's complete mandatory SIRE process, output contract, R7/R10 real-scenario rules, and task-end archive requirement. This shared skill is the only workflow source; app-level instructions must point here rather than restate the rules.

**Hard rule: never create a git worktree** (no `git worktree add`, `EnterWorktree`, `isolation: "worktree"`, `--worktree`); work in the current directory and branch. Applies to every task, subagent and fast path. Details: `references/global-contract.md` § 强制规则：禁止创建 git worktree.

**Hard rule: no tests without the user's authorization.** Finish implementing the whole requirement (plus R6 code review), then tell the user it is done and awaiting test authorization; never run tests, builds-as-verification, servers, or browsers for verification until the user explicitly says to. Unauthorized R7 is recorded as `跳过：待用户授权测试`; units close with `sire_run.py test <unit> DEFERRED`. Final reply must say "未测试". Details: `references/global-contract.md` § 强制规则：测试须用户授权.

**Hard rule: "你自己安排" = full authorization for the current task, tests included (2026-11-08).** When the user says "你自己安排" (or equivalent), do everything without asking for confirmation, including R7/R10 tests and verification runs (record `test-authorize --quote "你自己安排"`); this overrides the no-tests-without-authorization rule for that task only. Tests are skipped only if the user also says there is no connected device / no testing needed (skip just the affected items, record the quote, final reply states what was not tested). Hard stops unchanged: client permission denials, force-push/history rewrite/out-of-scope deletion/credentials/system settings, tag stays offer-only, no worktree. Push = only the current branch to its configured upstream (commit+push of in-scope changes is included under this phrase, and an unfinished requirement may be committed in stages); never merge into develop/main or other key branches, and never push any other ref, without the user's explicit authorization. Details: `references/global-contract.md` § 强制规则：用户说“你自己安排”.

**Hard rule: when the user asks for a tag, only offer it.** Derive the tag name from the current repository's own tag rules (project docs, CI config, version file, existing `git tag -l` naming), report name + basis + preconditions, and state "未创建、待你确认". Never run `git tag`, push a tag, or create a release until the user explicitly confirms that specific tag. Applies to every task, subagent and fast path. Details: `references/global-contract.md` § 强制规则：提供 tag 只给建议，不创建不提交.

**Trigger: when the user says "提测" / "准备提测"** (intent is to prepare or submit a test submission), open the fixed Feishu 提测 directory in the built-in browser and ask the user to log in; the user then says whether it is 编码器 or 舵机. Address, flow and document format: `references/submit-test.md`. Applies before the fast-path check, in every task.

## Simple-task fast path (confirm once on every run)

On every SIRE run, before any retrieval or analysis, Claude, Codex and Qoder must first confirm once whether the task is simple. A simple task is a read-only query, a quick question, or a single-step operation on a target the user named explicitly (for example, "what is the current branch" or "delete directory X"), done in one to three commands, with no code-logic change, no change to the SIRE workflow/knowledge/database, no Git commit/push/history rewrite, no system settings, no bulk or wildcard target, and no design choice or acceptance test. If it is simple, reply with only the declaration line, the line `快速通道：简单任务`, and the shortest direct answer or result taken from what was actually run or read in this turn; think only about which command to use (no option analysis, alternatives, or extra risk review); use at most two commands, one to act (it may check the target first) and one to verify, write commands in their simplest form; if the command itself errors, report it instead of trying another method, but if the tool is blocked by policy or cannot start, retry once another way; put all three lines in one final reply; do not read SKILL.md or the contract when the whitelist matches, since the client entry files carry a copy of the whitelist and limits that must be kept in sync (Qoder regenerates that section live through `scripts/sire_qoder.py remind`, so it keeps no manual copy); skip retrieval, stage logs, the model gate, subagents, the ledger, database backup and archiving, and commits, and add nothing extra. Decide by the contract's whitelist first: viewing anything (branch, Git status/log, file contents, config values, processes) and deleting, moving, renaming, copying, or creating user-named files or directories are always simple, with no further deliberation. Otherwise write `快速通道：否，完整流程` and run the full workflow. When unsure, use the full workflow. Full rules: `references/global-contract.md` § 简单任务快速通道.

## Shared locations

`scripts/sire_paths.py` is the only path authority. By default it resolves:

- Skill: `sire/workflow/shared/sire/`
- Markdown knowledge: `sire/knowledge/global/`
- SQLite database: `sire/data/sire_vectors.sqlite3`
- Model cache: outside Git

Run ledgers and evidence must be created only under the directory resolved by `ledger_runs_dir()` (default `D:/sire/sire_ledger/runs/<RUN_ID>/`; override with `SIRE_LEDGER_ROOT`). Never create or copy a new run ledger into a project, including at closure. Legacy project copies may be cleaned only after database contents are verified against their files; retain evidence not imported into the database and keep the fixed-directory source by default. Database indexing and archival run asynchronously after the user receives the result; failures stay in a local queue and retry at the next SIRE trigger.

Claude, Codex and Qoder talk to each other only through `scripts/sire_comms.py` (messages, progress, resource locks). Its data lives under `comms_dir()` (default `D:/sire/sire_comms/projects/<project>/`, override with `SIRE_COMMS_ROOT`), never inside a business project. Full-workflow tasks check `inbox` at R0, show each received message to the user, `ack` it, update `status` at phase changes, and send `handoff` when pausing. Collaboration is a session-level 1:1 pairing (since 2026-11-06): saying "start collaboration" in a conversation runs `pair start` with that conversation's id; the peer conversation claims it by saying the same, after which the two session ids are fixed for the life of the pair (no rebind), every received and sent message is shown verbatim in both conversations, and a different conversation starts a separate pair. Rules: `references/global-contract.md` § 本机通讯.

Claude, Codex and Qoder must use the same values for `SIRE_ROOT`, `SIRE_DATA_DIR`, `SIRE_VECTOR_DB`, `SIRE_KB_DIR`, `SIRE_EMBED_DIR`, and `SIRE_TASK_ROOTS` when overrides are set. Do not configure app-specific data paths. Run scripts from this skill's `scripts/` directory or invoke the same script file through either installed alias. Never copy the database to an app profile.

## Silent command execution

Never open or show Windows Terminal, PowerShell, Command Prompt, or another terminal window. Run commands through a non-interactive execution interface with PTY disabled. Every child process started by a SIRE script on Windows must use `scripts/sire_process.py` `no_console_kwargs()`; do not use `Start-Process` or launch a terminal app. Background archive and telemetry work must stay detached and hidden, write output to a log or discard it, and never delay the user-facing result.

Qoder is bound to this same source by `scripts/sire_qoder.py`: `install` registers the four telemetry events plus the entry-injection hook and links `~/.qoder-cn/skills/sire-global-workflow` to this directory as a junction; `selftest` proves the pipeline on an isolated telemetry DB; `verify` proves the hooks actually fire; `uninstall` removes only what the adapter wrote. Hook config takes effect by the next user prompt — measured, no client restart required. `verify` decides by telemetry heartbeat for `client='qoder'`, not by log text matching (string matching produced a false PASS once). Entry injection is opt-in via `--with-remind`. The Qoder alias is a junction, never a second writable copy.

The SQLite file is the shared working database but is **not tracked in Git for now** (it exceeds GitHub's 100MB file limit); `sire/data/DATABASE-RECORD.md` records its actual local paths and restore steps, and `.gitignore` excludes it — never `git add -f` it. SQLite `-wal`, `-shm`, and journal files are runtime-only and excluded from Git. Keep encryption keys, tokens, personal settings, integrity snapshots, and model weights outside this repository.

`search`, `show`, and `stats` must open the database read-only and must not create schema or switch journal mode. Only intentional `index`/`migrate` and archive operations may write; they must create a verified backup and keep the snapshot manifest in sync with the database hash.

## Whole-request contract

Treat the complete user request as one objective. Before decomposing, identify the goal, scope, inputs, outputs, acceptance criteria, dependencies, and authorized actions. If an ambiguity, contradiction, missing input, or acceptance gap could materially change the outcome, stop dependent work and ask a focused question; continue independent work that does not depend on the answer.

Every task uses the SIRE workflow, including analysis and simple requests. Except for tasks confirmed as simple by the fast path above, search the shared local knowledge and vector database before task analysis, and at task end store reusable knowledge, the task record, and validation results in the shared database. Outside the fast path, do not skip retrieval, visible SIRE status, or archiving because a task seems small.

## Stages and role responsibilities

1. **R0 — Coordinator:** preserve the full request, scope, authorization, dependencies, unit status, blockers, and final closure.
2. **R1 — Knowledge retriever/curator:** extract search terms; search Markdown and SQLite/vector knowledge; read matching records; state reuse decisions and gaps; archive durable results and reindex.
3. **R2 — Requirements analyst:** define observable outcomes, scope, inputs, outputs, acceptance, dependencies, and authorization.
   **Rule-read budget:** `SKILL.md` 与 `references/global-contract.md` 在同一任务内整读至多一次；需要回看时用 `grep`/`sed` 定位段落，不重读全文（遥测 `RULE_READ` 以每任务 4 次为告警阈值）。
4. **R3 — Decomposer:** split work into smallest independently executable units with owner, read/write sets, dependencies, outputs, review, tests, and recovery.
5. **R4 — Plan reviewer:** independently check requirement coverage, unit overlap, dependency closure, testability, and read/write conflicts.
   **Model-selection gate (after R4, before R5):** for each unit, decide whether it runs on a lower-cost model (simple, mechanically verifiable, no design decisions) or stays on the current model (design, cross-module, high-risk, debugging). Record unit / difficulty / model / reason in the ledger. Tiers: high = Opus medium, mid = Sonnet medium, low = Haiku high; the current model may delegate a unit it judges too simple to a lower-tier subagent (子代理降级) — this is the preferred token-saving mechanism and must be used by default for any strippable work; every delegation must state why and for what task (ledger + one reply line `子代理降级：<任务> → <档位>，因<理由>`). Full rules: `references/global-contract.md` § 模型选择门禁.
6. **R5 — Executor:** execute assigned units; record “执行中” and “执行完毕”, artifacts, verification, assumptions, and blockers in the run ledger.
7. **R6 — Independent reviewer:** review each completed unit independently; reject failures and record the cause and repair. The author cannot approve their own work.
8. **R7 — Functional tester:** run the prelisted tests against real user paths and record actual behavior, evidence, and conclusions.
9. **R8 — Integrator:** verify cross-unit contracts, regressions, requirement coverage, and final usability.
10. **R9 — Closure auditor:** inspect scope coverage, privacy/security, related risks, archive completeness, and remaining optimizations. Fix related in-scope issues; report unrelated ones. Then run `scripts/sire_telemetry.py pending` and, if it prints anything, fix the first finding through RSI (see `references/global-contract.md` § RSI 自动发现与自我优化). `sire_run.py finish` enforces this step: unhandled findings block closure unless resolved, ignored with a reason, or handed off via `--pending-note`, and the check is written to `pending-check.json`. `analyze` also raises `COLLECTION_DEAD:<client>` when a client that has hooks configured stops producing events for more than `--stale-hours` (default 12), which is how a silently broken collection channel gets caught.
11. **R10 — Native computer operator:** perform authorized native-app/system operations when required. R10 does not review code or decide R7 results. If no UI/system action is needed, record “跳过” and why.

Parallelize units only when their read/write sets do not conflict and their dependencies are satisfied. After every unit, perform independent review and functional acceptance. A failed unit returns for repair. After three materially identical failures, stop that affected branch and report the reason; continue independent branches.

## Functional test rules

Before R7 starts, list each test ID, real user operation steps, expected behavior, actual behavior, evidence, and conclusion. For tasks involving an app, webpage, desktop program, file picker, system settings, device, publication, or user interface, use the real target and user interaction path; static inspection or function-only calls do not prove acceptance. Include a normal route and at least one boundary/error route. When a required tool, environment, or permission is unavailable, report `BLOCKED-无法真实验证`, never PASS. R10 performs authorized computer operations; R7 records the test conclusion.

## Output and evidence contract

Each stage and role records “执行中”, “执行完毕”, or “跳过” with a reason, plus artifacts, verification results, and blockers, in the run ledger/evidence under the current run directory, not in the chat. In the chat, speak only when there is a result, a blocker, or a decision the user must make; the final reply gives only the result, risks ("无" if none), and suggestions, each in one to three lines, optionally with one verification line and the ledger path. No step narration, file recaps, or repeated logs.

Use the local run ledger and scripts when available. Record failed reviews/tests, repair actions, retry counts, and final evidence. Do not call a stage complete merely because a command returned successfully; inspect the resulting data and state.

## Shared database commands

Resolve the shared skill, database, and knowledge locations with `scripts/sire_paths.py`. The common commands are:

```powershell
python <SHARED_SKILL_DIR>\scripts\sire_kb.py search --combined "keyword one keyword two" --run <RUN_DIR>
python <SHARED_SKILL_DIR>\scripts\sire_kb.py reindex
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py index
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py migrate
python <SHARED_SKILL_DIR>\scripts\sire_vector_db.py stats
```

On completion, archive reusable facts, search terms, decisions, limitations, validation results, and the task record to the shared database; update the shared Markdown index; and set `meta.sire_last_project`, `meta.sire_last_run`, and `meta.sire_last_status`. Commit changed knowledge and workflow to this Git repository; keep run ledgers and their evidence in the fixed directory and archive their records to the database, never copy them into Git. The database stays outside Git (see `sire/data/DATABASE-RECORD.md`). When the user explicitly says "提交代码", commit the current changes within the scope of that task and push them to the upstream configured for the current branch, using that upstream remote and branch; do not ask again whether to push. First inspect the current branch, its upstream, and the working-tree diff; exclude unrelated or pre-existing changes. If no upstream is configured, the remote is unavailable, or the target ref is ambiguous, stop and report the blocker rather than guessing a remote or branch. Never force-push, rewrite published history, or push another ref; any other push still requires explicit authorization. Database migrations/indexing must keep a recoverable backup and verify row counts, FTS, vectors, and `integrity_check`.

## Workflow changes (RSI)

**Time self-analysis (2026-11-10):** `scripts/sire_telemetry.py diagnose` reports per-phase time share and the likely cause (retry failures / one long step / fragmented calls / slow per-call / model thinking); `analyze` runs it every 24 h, writes `telemetry_digest.md`, and turns an overhead share >=50% or a single SIRE phase >=20% into pending findings that R9 handles through RSI. Quality rules (user corrections, rule violations, gate/review/comms failures) and ignored-finding revival (`resolve --ignore` revives after repeated hits; `--accepted` never) are described in `references/global-contract.md` § RSI 自动发现与自我优化 items 6-7.

RSI also finds problems on its own: Claude, Codex and Qoder hooks call `scripts/sire_telemetry.py hook --client claude|codex|qoder` to record per-phase task timings in the local `sire_telemetry.sqlite3`; after each task the Stop hook runs `analyze` in the background and turns repeated issues into pending findings, which the next full-workflow task fixes during R9. No user scheduling is needed. Qoder is bound to this same source by `scripts/sire_qoder.py` (`install` registers the four events plus an entry-injection hook and links `~/.qoder-cn/skills/sire-global-workflow` to this directory as a junction; `selftest` proves the pipeline on an isolated telemetry DB; `verify` proves the hooks really fire; `uninstall` removes only the keys this adapter wrote). Hook config takes effect by the next user prompt — measured, no client restart required. `verify` decides by telemetry heartbeat for `client='qoder'`, not by log text matching (string matching produced a false PASS once). Entry injection is opt-in via `--with-remind`. Client adapters must never copy the workflow, knowledge base, or database.


**Merge before activating (2026-11-08):** whenever RSI is triggered and several proposals are still `PROPOSED`/`EVALUATED_PASS`, first analyse whether they should be merged into one latest proposal (drop duplicates and superseded ones with `rollback`), show the analysis to the user, then register → evaluate → activate that single proposal; never activate old proposals one by one. `config-hash` is taken after the commit: `git rev-parse HEAD:sire/workflow/shared/sire`. Details: [references/self-optimization.md](references/self-optimization.md) §5.1.

Any change to files in this shared skill directory is a workflow mechanism change. Before the first edit, register a proposal with `scripts/sire_rsi.py propose`; after verification, record metrics with `evaluate`, and `activate` only an `EVALUATED_PASS` proposal; `rollback` on regression. R9 `sire_supervisor.py finalize` (and the read-only `rsi-check`) returns `STOP` (`rsi_unregistered_change`) when this directory has uncommitted changes but no `PROPOSED`/`EVALUATED_PASS`/`ACTIVE` proposal was created after its last commit. `sire_rsi.py` write commands update both the machine-level archive database (set `SIRE_ARCHIVE_ROOT` or `SIRE_ARCHIVE_DB`, or pass `--archive-db`) and the repository database, archive first; `status` is read-only. `sire/tools/snapshot_db.py` refuses to publish when the repository database holds RSI records missing from the archive. Full rules: [references/self-optimization.md](references/self-optimization.md) §5.1.

## Supporting references

- Internal GitLab access (token file, glab login, SSH; never ask the user to log in to git again): [references/git-access.md](references/git-access.md)
- Role and output details: [references/roles.md](references/roles.md)
- Knowledge and indexing details: [references/knowledge.md](references/knowledge.md)
- Gates and test evidence: [references/gates.md](references/gates.md)
- Vector database design: [references/vector-knowledge.md](references/vector-knowledge.md)
- Integrity and final review: [references/supervisor.md](references/supervisor.md)
- Learning, self-optimization, and RSI gate: [references/self-optimization.md](references/self-optimization.md)
- Claude adapter role files: [agents/claude/](agents/claude/)
- Qoder client adapter (hooks, junction, selftest/verify): [agents/qoder/](agents/qoder/)
- One-call R9 closure (stages + finish + queued background archive; ledger stays outside projects): scripts/sire_close.py
- Codex discovery metadata: [agents/openai.yaml](agents/openai.yaml)

## ZIP packages

The Git repository holds the workflow, knowledge, and history; the database stays local (see `sire/data/DATABASE-RECORD.md`). A light ZIP, when explicitly requested, does not include the SQLite database or run history; it must still include exactly one `shared/sire/` workflow source and clearly state the omitted data. Sensitive files (`secrets` directories and `.pem/.key/.pfx/.p12/.vault`) and old packages under the knowledge `exports` directory are never packaged. After packaging, R9 `verify-zip` checks its own required-entry list (a missing entry is `package_omission`) and rejects any sensitive file in the ZIP (`package_sensitive_leak`). Restoring a ZIP must reconnect both client aliases to the same repository copy.

### 按需协作通讯服务

本机协作通讯的**唯一规则文件**是 `references/comms-protocol.md`（v6.38），本节不再重复细则，冲突以该文件为准。要点：队列式会话级 1 对 1 配对（钩子入队、FIFO、标签隔离）；ping 由脚本自动回 pong；request 须带 `--files/--accept/--evidence`，可写文件与未回复 request 重叠时被拒；完成后请求方验收再 `pair done --accepted`（未验收须 `--unaccepted <原因>`）；协作范围内免重复授权，硬停边界不变；收发消息在各自会话原文展示。工作流接入点（触发词、R0、阶段、收尾）见契约 § 本机通讯。
