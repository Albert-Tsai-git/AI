VERDICT: PASS

单元: U-01（主）+ U-02（文档一致性，同一 diff 合审）
方向: R6C 工程质量与回归
结论: PASS
检查对象: D:/sire/AI/AI/sire/workflow/shared/sire/scripts/sire_supervisor.py（工作区未提交版本，426 行）、SKILL.md、references/supervisor.md；对照 change.diff、units-draft.json U-01/U-02；关联 sire_bundle.py、sire_paths.py、sire_rsi.py、sire_vector_db.py、sire_db_backup.py、sire_run.py、agents/claude/sire-supervisor.md
说明: 按派发要求未运行 start/finalize/preflight；finalize 不推进基线仅做静态核验（R7 负责真实执行）。

## 实测证据（只读 / 仅 scratchpad）
- 编译: py_compile 到 scratchpad 输出 → compile ok
- `--help`: rc=0，子命令 {preflight,start,check,finalize,rsi-check,verify-zip} 全在；`rsi-check --bogus` rc=2（argparse 既有行为）
- 真实库 `rsi-check`: rc=0，PASS，changed=3 个文件，last_workflow_commit=2026-09-25T05:18:45+08:00，matched=RSI-20260925-R9GATE(PROPOSED, 2026-09-24T21:19:32Z)；耗时 0.19s
- 真实库前后 sha256 均为 cc4924ce0b309f846a1fcfa77664067e04afefc1c3ab34aa5c9abcf76afe9659；data 目录无 -wal/-shm；库头 byte18/19=1/1（rollback 日志模式）
- `SIRE_VECTOR_DB=<scratch 不存在路径> rsi-check`: rc=3，stdout 0 字节，stderr JSON status=STOP classification=rsi_unregistered_change，未创建库文件
- scratch 临时 git 仓库 + 临时库直接调用 rsi_gate：干净→PASS；脏+无库/无表/EVALUATED_FAIL/提案早于提交/created_at 为 NULL 或乱码/仅未跟踪文件→STOP；提案晚于提交、`Z` 后缀→PASS；非 git 目录→SKIPPED
- 回归: D:/sire/.sire/runs/R20260924-192838/evidence/U-02B/qa/qa_all.py（SP=scratchpad）→ ALL PASS（build + verify-zip 21 项必需清单 + secrets 泄漏 + zip 不存在）

## 问题
1. (MEDIUM) sire_supervisor.py:259-264 `rsi_proposals` 错误分类不准：只捕获 OperationalError 且一律当作“无提案”。实测 scratch 库被 `BEGIN EXCLUSIVE` 占用时，等待 42.6s 后返回 []，门禁报 STOP“没有登记未失败的 RSI 提案”，与真实原因（库被锁）不符；库损坏时抛 `sqlite3.DatabaseError: file is not a database` 直接 traceback、rc=1，不符合本文件 0/3 + JSON 约定，也不符合 supervisor.md:28“库损坏须记录 STOP 与具体产物”。均为 fail-closed，不会误放行。修复要求：仅 `no such table` 视为空；其余 sqlite3.Error 返回独立分类（如 `rsi_db_unreadable`，带错误文本和库路径）并 rc=3；connect 放进 try。
2. (MEDIUM) sire_supervisor.py:281-283、294 异常时 fail-open：`git log` 返回码被忽略，输出为空时 since=None，任意 open 提案都算匹配；真实库中 RSI-20260921-DB 常驻 ACTIVE（2026-09-21），因此只要 since=None 就必然 PASS。实测 scratch“目录尚无提交 + 旧 ACTIVE”→PASS。触发场景：工作流目录整体改名/迁移（新路径无历史）、git log 执行失败。另：275-277 在 rev-parse 已成功后 `git status` 失败也降级为 SKIPPED rc=0。修复要求：log rc≠0 或 status rc≠0 时判 STOP；since=None 时不接受 ACTIVE（只接受 PROPOSED/EVALUATED_PASS）。
3. (MEDIUM) sire_supervisor.py:311-317 finalize 中 check() 已在 239 行把 runs/<RUN_ID>/supervisor-report.json 写成 status=PASS，随后 RSI 门禁 STOP 只输出到 stderr，不落盘。事后审计只看报告会误判 finalize 通过。修复要求：RSI 结果写入同一运行目录（如 runs/<RUN_ID>/rsi-gate.json 或并入报告）。
4. (MEDIUM，设计层技术债，符合当前验收字面) sire_supervisor.py:270-301 门禁只看“未提交改动 + 最后一次提交之后存在任一 open 提案”：(a) 先 commit 再 finalize 即可绕过；(b) 提案不绑定文件/会话，任一会话的 PROPOSED 提案会放行所有会话的未提交改动（当前 RSI-20260925-R9GATE 即对其他并行会话生效）；(c) RSI 改动中途分批 commit 后，剩余未提交部分的提案因早于新提交而失效，重新 propose 同 ID 会被 sire_rsi.py:42 `INSERT OR REPLACE` 重置为 PROPOSED 并清掉评估状态；amend/rebase 抬高 committer date 同样使提案失效（scratch 实测 T13b）。建议后续：以 run 的 before.json 差异中 `shared/sire/` 条目为准，或按 workflow_versions.config_hash 对比已提交树。
5. (LOW) sire_supervisor.py:249 `git status` 可能顺带刷新并写 .git/index（取 index.lock）；多会话并行时与他人 `git commit` 存在极小竞争窗口。建议 `git --no-optional-locks status`。
6. (LOW) sire_supervisor.py:259 未复用 sire_vector_db.py:241-249 `connect_readonly`，属 3 行重复；但本文件需要 timeout=30 且缺库返回空而非抛异常，且 sire_db_backup.py:23 已有同样内联写法，R9 不依赖向量库模块也有合理性。可接受。
7. (LOW) 风格细节：sire_supervisor.py:1 模块 docstring 未提 RSI 门禁；244 行 RSI_OPEN_STATUSES 常量放在文件中部而非顶部常量区；rsi-check 无 `--db` 参数（sire_rsi.py 有 `--db`），只能用 SIRE_VECTOR_DB 覆盖；naive created_at 被当作 UTC（sire_rsi 目前总写带时区 UTC，无现实影响）。

## 兼容性核验
- 接口: 原 5 个子命令参数与分派不变（410-421），新增 `rsi-check` 无参数；verify-zip 回归 ALL PASS。
- 导入: 新增 sqlite3/subprocess 为标准库；`from sire_paths import DATABASE_PATH, SHARED_SKILL_DIR` 与 sire_bundle.py:14 已有依赖相同，无循环（supervisor→bundle→paths、supervisor→paths；bundle 仅以 subprocess 调 supervisor 的 preflight/verify-zip，不经过 RSI 门禁）。qa_all.py 以 `import sire_supervisor` 方式导入无副作用。
- 数据/配置: 数据库只读（mode=ro + query_only，实测 hash 不变、无 sidecar）；门禁读 DATABASE_PATH，与 sire_rsi.py 默认写入位置一致，受同一 SIRE_VECTOR_DB 覆盖。
- 输出约定: STOP→stderr+rc=3、PASS/SKIPPED→stdout+rc=0，与 fail_if_loss/verify_zip 一致；JSON indent=2、ensure_ascii=False 一致；分类名 snake_case 与 package_omission 等一致；中文注释/docstring 一致。
- 性能: rev-parse + status（+ 仅脏时 log）共 2-3 次 git 调用，实测全命令 0.19s；仅在 finalize/rsi-check 触发，不在热路径。

## 回归核验
- 调用方: sire_run.py 不调用 sire_supervisor（其 `--finalize` 是复核综合放行，无关）；~/.claude settings/hooks、~/.codex 配置中无自动调用 sire_supervisor；finalize 只由 R9 手动执行，新 STOP 不会打断任何自动链路。
- 行为变化: finalize 在“工作流目录脏且无匹配提案”时新增 rc=3 且不推进 BASELINE_MANIFEST（316-319 静态确认 return 3 先于 snapshot/write_json）。其他会话留下未提交工作流改动时本会话 finalize 会 STOP，已在 U-01 risk 中声明为预期；STOP 提示“先运行 sire_rsi.py propose”对他人改动场景指引不足（归入问题 4）。
- 暂停 run R20260924-192838: 其文件已提交（31a3d7d/e537371），不会留下脏工作流目录。
- 门禁可达性: agents/claude/sire-supervisor.md:9-16 的 R9 检查清单未提到 finalize/rsi-check，只有 references/supervisor.md:26 写明；R9 角色若不读 references 可能不执行门禁。不在 U-01/U-02 文件集，记录为后续项（LOW）。

## U-02 文档一致性
- SKILL.md:76-78 与 supervisor.md:26 的状态名 PROPOSED/EVALUATED_PASS/ACTIVE、分类 rsi_unregistered_change、命令 `rsi-check`/`finalize` 与代码 244/299/406 逐字一致；链接 references/self-optimization.md 存在，§5.1 标题在 72 行。
- 偏差（LOW）：文档未说明非 Git 时 SKIPPED（rc=0）；SKILL.md 称“Full rules: §5.1”，但 §5.1 未包含该门禁规则；门禁范围只覆盖共享 skill 目录，而 sire_run.py:248-258 的 workflow_control_paths 还包括 governor、~/.claude/agents、sire_ai_rules.md 等，二者口径不同（文档与实现自洽）。

越界检查: 无越界。diff 仅含 U-01/U-02 声明的 3 个文件；工作区另有 sire/data/sire_vectors.sqlite3 修改，来自 REQ-04 已执行的 propose，不属于本 diff。
技术债务: 问题 1-4（MEDIUM）建议作为下一轮 RSI 修复项；问题 5-7 与 R9 角色文件补充门禁步骤为 LOW。均不破坏现有接口、数据格式或回归路径，且错误方向均为 fail-closed，只有问题 2 在罕见异常下 fail-open。
