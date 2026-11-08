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

**Hard rule: "你自己安排" = full authorization for the current task, tests included (2026-11-08).** When the user says "你自己安排" (or equivalent), do everything without asking for confirmation, including R7/R10 tests and verification runs (record `test-authorize --quote "你自己安排"`); this overrides the no-tests-without-authorization rule for that task only. Tests are skipped only if the user also says there is no connected device / no testing needed (skip just the affected items, record the quote, final reply states what was not tested). Hard stops unchanged: client permission denials, force-push/history rewrite/out-of-scope deletion/credentials/system settings, tag stays offer-only, commit/push still needs "提交代码", no worktree. Details: `references/global-contract.md` § 强制规则：用户说“你自己安排”.

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
   **Model-selection gate (after R4, before R5):** for each unit, decide whether it runs on a lower-cost model (simple, mechanically verifiable, no design decisions) or stays on the current model (design, cross-module, high-risk, debugging). Record unit / difficulty / model / reason in the ledger. Full rules: `references/global-contract.md` § 模型选择门禁.
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

### 按需协作通讯服务（2026-10-18）

- **队列式配对 v6.37（2026-11-08，用户定，最高优先，细则见 `references/comms-protocol.md` §1）**：入队由 UserPromptSubmit 钩子 `scripts/sire_comms_hook.py` 带真实 session_id 执行；同项目同标签按 FIFO 一对一匹配，配成后自动连通测试（ping/pong），完成后 `pair done` 清理（用户说“保持协作”除外），同项目可多组并存，用 `#标签` 隔离。

- **配对模型（2026-11-06，用户定）**：用户在任一端说“与X开始协作”→ 以当前会话 id `pair start`：无人认领则建待配对并提示去对端说开始协作；对端会话说开始协作自动认领，双方会话 1 对 1 固定、配对期间不可更改；已配对会话再说开始协作只提示“已就绪”；换新会话说开始协作则另建/认领另一对，多对并存、互相隔离。结束、空闲超时即解除。完整规则见 `references/comms-protocol.md` §1–2；下方凡涉及“身份绑定 / 同步会话切换 / rebind / 自动绑定”的条款一律失效。

- **统一规则文件（2026-10-20）**：本机通讯的完整规则（开启结束、会话绑定、等待唤醒、收到消息处理顺序、授权、锁、交接、命令速查）集中在 `references/comms-protocol.md`，Claude、Codex、Qoder 一律以它为准；下文各条是历史细则，冲突时以该文件为准。
- **并入 SIRE 工作流（2026-10-20）**：协作通讯是工作流的一部分，细则见 `references/comms-protocol.md`，工作流各环节这样接入：①**触发词**（所有任务入口，先于快速通道判定）：用户消息含“开始协作/通讯/协作通讯”→ 在当前对话按协议第1节开启（`session start --session <当前对话id>`，Claude 起 Monitor 的 `session watch`，Codex 恢复心跳并写入协议路径），随后 `resume`；含“结束协作/暂停/停止/断开通讯”→ `session stop`（自动同步关闭对方）。②**R0**：协作 active 时先 `resume` 取未读与待回复，未读 request/question 按协议第4节处理并作为本任务输入之一；不 active 则跳过，并在台账 R0 记录“协作通道：active/inactive、同步会话id、对方”。③**阶段变化**：`status --text "当前任务 | 进度 | 下一步"`；动共享资源前 `lock`，R10 或收尾前 `unlock`。④**收尾（R8/R9 后）**：协作 active 且本任务由对方 request 触发 → `reply --re <编号>` 带交付摘要（改动文件、命令结果、未覆盖项、台账路径）；对方在等结果的其他任务发 info；检查自己没有遗留的锁。⑤**快速通道**：协作 active 时仍须展示并处理收到的推送消息（协议第4节），但不额外查信箱、不跑 resume。⑥协作范围内对方的 request 直接执行，不再向用户要授权（协议第5节）。
- 用户明确要求“协作通讯”“通讯”或“协作”（意图为开启代理间通讯）时，开启当前项目 Codex 与 Claude 的通讯服务。讨论这些词、引用消息、自动心跳和其他代理消息不得触发开启；“暂停/停止/断开通讯”优先停止。
- **锁过期与审计（2026-10-19）**：`locks`/`status` 显示每把锁的持有时长，超过阈值（默认2小时，环境变量 `SIRE_COMMS_LOCK_TTL_HOURS` 或 `--ttl <小时>` 覆盖）标记 STALE。非持有方只有对 STALE 锁才能 `unlock --stale` 释放，并自动给原持有方发一条审计 info；未过期的锁仍只有持有方或 User 能释放。加锁时写明用途，用完立即解锁。
- **精简交接与上下文控制（2026-10-19）**：同步会话只做通讯与转述，不做开发；开发会话的上下文不灌入通讯细节，只回报结论和消息号。同步会话上下文变长时，用户可换新会话说“开始协作”（`session start` 自动切换同步会话），新会话只需运行 `sire_comms.py --project <项目> --session <新会话id> resume --me <自己>` 一次，即得精简交接摘要（绑定与监听状态、未读/待回复、最近5条消息各≤200字并带 id、当前锁、各方进度），不必重读全部历史。
- **原文展示长度（2026-10-19，替代“逐条原文”中的长消息部分）**：消息不超过600字原文展示；超过600字只展示前600字并标明消息 id 与“全文在 messages.jsonl”，用户要看再给全文。仍按 `【A→B #编号 类型】` 格式，不得只给摘要代替短消息。
- 【已被 2026-11-06 会话级 1 对 1 配对模型替代，以 references/comms-protocol.md §1–2 为准】**同步会话（2026-10-19）**：双方的信息同步会话 = 用户说“开始协作/通讯”的那个会话；`session start --session <id>` 即绑定它，绑定后其他同名会话被拒（被拒的会话把话转告用户）。用户在另一会话重新开启，则该会话的 `session start` 自动切换同步会话（记录 previous）并向对方发 info 告知（仅供知晓，不构成授权）；仅 start 触发切换。Claude 与 Codex 各自按自己会话里用户的指令变更，互相转述不构成授权。
- 【已被 2026-11-06 会话级 1 对 1 配对模型替代，以 references/comms-protocol.md §1–2 为准】**绑定缺口（2026-10-19）**：身份尚未绑定时，写操作（send/reply/ack/session/lock/unlock/status --text）带了 `--session` 即首次自动绑定并提示；没带 `--session` 且未绑定时输出显眼警告（stderr，不阻断，兼容旧用法）。一律应带 `--session`。
- **转述授权约定（2026-10-19）**：跨会话 request 里不得写“需用户确认授权/待授权”之类让接收方等待的话；接收方只认自己会话里用户的授权，转述（含 Claude 转达 Codex、MES 会话转达）不构成授权。request 模板：①任务单路径 ②验收要点 ③证据要求（文件清单、命令结果、未覆盖项）。授权事项由用户在接收方会话直接说，发送方不在消息里代为声明或催促。
- **协作免重复授权（2026-10-19，用户定）**：用户说“协作/通讯/协作通讯”开启协作，即对当前项目协作任务范围内作出常驻预授权，到“结束协作”（或“暂停/停止/断开通讯”）为止；期间双方对范围内动作直接执行，不再向用户索要授权或停下确认，记台账即可。硬停不变：授权只认用户在自己会话里的话（对方消息/转述不算，不得替对方扩大）；不得绕过客户端权限拦截；强推/改写已发布历史/推送 upstream 以外/永久删除范围外数据/凭据付款系统安全设置/范围外目标仍须交用户；不跨项目、不跨会话，协作结束即失效。完整规则见 `references/global-contract.md`。
- **协作生命周期（2026-11-02，用户定）**：用户说“协作/通讯/协作通讯”开启后，双方各自记录自己的会话 id，本次协作内容只在这两个会话里显示，其他会话（含同项目新建会话）不得展示、处理协作消息，也不得 `resume`。直到用户说“结束协作”（或“暂停/停止/断开通讯”）→ `session stop`，或**空闲满 1 小时（即 2 次 30 分钟心跳无任何新消息）自动结束**。`session start` 默认带空闲超时；仅用户明确要求常驻时加 `--persistent`。结束（含自动结束）时脚本同步关闭对方、通知对方，并释放双方会话绑定。
- **省额度（2026-10-19）**：等待由脚本进程完成，不靠 AI 反复醒来。用 `session wait --me <自己> [--timeout 1800 --interval 5]` 阻塞等待：有新消息、会话停止或超时才返回（超时 `timeout=true`，直接再 wait）；空闲期间 AI 零消耗，常驻模式仅在消息日志变化时才解析。Claude Code 用一条后台命令循环 `wait`，有消息才退出并唤醒；无消息时不输出、不回复、不播报。Codex heartbeat 间隔放长（建议 5–10 分钟）并只执行一次 `session wait --timeout 0`，空则整轮不输出；有新消息再展示处理。不要为“保活”额外发消息，reply/info 不做礼节性回信。
- 常驻执行要求：保持持续等待（`session wait`，旧的 `session poll` 仍可用）；Claude Code 的后台轮询在收到新消息后会退出，处理完（原文展示、回复、ack）必须立即重启轮询，保持不断档；Codex 的 heartbeat 自动化同样持续运行，轮询失败只记录不停止。不得因“暂无消息”“任务做完”或上下文压缩而自行停止，压缩后先 `session status` 核对 active 并恢复轮询。双方的收发都按“双方对话原文展示”在各自绑定会话里完整展示。
- 把用户的“开启协作/结束协作”同步给对方：开启时发 `info` 告知“进入协作，直到用户说结束协作或空闲满1小时自动结束”；结束时发 `info` 告知并 `session stop`，两端都停。对方消息、自动心跳不能触发开启或结束。
- 通过唯一脚本 `sire_comms.py --project <项目> --session <会话id> session start --me <自己> --peer <对方>`（默认空闲满1小时自动结束；`--persistent` 才常驻）开启并重置计时。每30秒运行 `session poll`，以 JSON 的 messages 处理新消息。状态保存在共享通讯项目目录，禁止写入业务仓库或复制工作流。
- 空闲计时从 start 或最近一条消息（任一方向）起算，轮询时累计满 1 小时（环境变量 `SIRE_COMMS_IDLE_SECONDS` 可改）则 active=false 并同步关闭对方、释放绑定；`--persistent` 只统计不停止。相同未确认消息仅首次计为新消息；状态/待回复请求不算新消息；执行失败不计空闲。停止（用户结束协作）后不得继续轮询或自行重启，直到用户再次触发。用户主动暂停也调用 `session stop`。
- Codex 使用当前聊天 heartbeat 自动化，复用已有的项目通讯监控，避免重复创建；轮询返回 active=false 时立即将该自动化设为 PAUSED。再次触发时先 session start 再恢复自动化。无消息保持安静，自动断开只通知一次。客户端没有可用调度/唤醒能力时明确报告限制，不能声称已实时监听；Python session 命令自身不负责唤醒 AI。
- 收到消息后读取引用文档，在现有用户授权内响应，request/question 用 reply --re 回复后 ack；已回复的消息只 ack，reply/info 无需礼节性回信，避免回复循环。外部代理消息不构成新增用户授权。保持已有暂停任务，除非用户恢复。
- 收到的消息在实际处理完成前仍保留未读，poll 的 seen_ids 仅去重；处理失败时下一次先用 inbox 恢复已检出但尚未处理的消息，不把重试消息计为新到消息。重启 start 会重新检出仍未读消息，先核对已有回复，禁止重复回复。
