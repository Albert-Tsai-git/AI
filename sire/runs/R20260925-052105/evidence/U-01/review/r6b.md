VERDICT: PASS

单元: U-01
方向: R6B 安全与边界（独立初审，未读取 R6A/R6C 报告与实现者推理）
检查对象: D:/sire/AI/AI/sire/workflow/shared/sire/scripts/sire_supervisor.py（未提交工作区）
  新增 git_output(247-252) / rsi_proposals(255-267) / rsi_gate(270-301) / rsi_check(304-308) / finalize 调用(311-321) / rsi-check 子命令(406, 419-420)
  对照 evidence/change.diff 与 units-draft.json U-01 验收
结论: FAIL

## 问题

### F1 (MEDIUM) SKIPPED 分支越出验收范围且 fail-open：Git 仓库内的 git 故障会放行 finalize 推进基线
- 位置: sire_supervisor.py:272-277（rev-parse / status 非 0 即 SKIPPED），:308（SKIPPED 返回 0），:316（finalize 仅在 rc!=0 时阻断）
- 验收只允许"非 Git 目录返回 SKIPPED"。实现把以下情形也归为 SKIPPED 并返回 rc=0：
  a) git status 在有效仓库内失败（实测 T11：索引文件损坏，rev-parse rc=0、status rc=128 → SKIPPED，工作区实际有未提交改动）；
  b) PATH 中找不到 git（实测 T2：脏目录 → SKIPPED）；
  c) rev-parse 的非"not a git repository"类失败（例如 dubious ownership / safe.directory 拒绝，理论推断，未实测；本机全局 safe.directory=* 掩盖了该场景）。
- 影响: finalize 继续执行 snapshot("baseline-next") 并覆盖 BASELINE_MANIFEST，未登记的工作流改动被纳入新基线，下次不再被发现；输出原因"不在 Git 仓库中或未找到 git"与实际情况不符。
- 可利用性: 非恶意场景即可触发（环境/权限/索引损坏）；门禁在最需要判断的时候静默失效。
- 修复要求: 仅当 rev-parse 明确判定"不是 Git 仓库"时返回 SKIPPED；git 不可用、git status 失败等"仓库状态未知"的情形返回 STOP（独立 classification，例如 rsi_check_error，rc=3），finalize 不推进基线。

### F2 (MEDIUM) git log 返回码被忽略，since=None 时历史 ACTIVE 提案永久满足门禁
- 位置: sire_supervisor.py:281-283, :294（`_ , last_commit = git_output(...)`；`since is None` 时任何开放提案都匹配）
- 实测 T12：无提交仓库（unborn）+ 2020 年的 ACTIVE 提案 → PASS。真实库中 RSI-20260921-DB 状态为 ACTIVE（sire_rsi.py activate 只退役 workflow_versions，不降级旧提案状态，sire_rsi.py:53-55），因此只要 git log 失败或返回空，任何工作流改动都会 PASS。
- 修复要求: git log rc!=0 → STOP；rc==0 且为空（目录从未提交）需显式策略（例如只接受当前时间窗内新建的 PROPOSED/EVALUATED_PASS，或直接 STOP），不得让历史 ACTIVE 提案兜底。

### F3 (LOW) 损坏库抛未捕获 sqlite3.DatabaseError，门禁以 traceback 退出
- 位置: sire_supervisor.py:259（connect 在 try 外），:263（只捕获 OperationalError）
- 实测 T9/T9b 与 CLI：非 SQLite 文件 → `sqlite3.DatabaseError: file is not a database`；截断库 → `database disk image is malformed`；`rsi-check` rc=1 并打印 traceback。finalize 中异常上抛，基线不推进（fail-closed），但无结构化 STOP/classification。
- 修复要求: 捕获 sqlite3.DatabaseError（含 connect 阶段），返回结构化 STOP（独立 classification，例如 rsi_db_unreadable）。

### F4 (LOW) 数据库读取失败被当作"无提案"，误报 rsi_unregistered_change 并给出错误处置建议
- 位置: sire_supervisor.py:263-264
- 实测 T15：另一连接持 EXCLUSIVE 锁 → 等待约 42.8s 后 OperationalError 被吞 → STOP rsi_unregistered_change；T19：热日志 → SQLITE_READONLY_ROLLBACK 被吞 → 同样的 STOP。结果为 fail-closed，但提示"先运行 sire_rsi.py propose"会诱导操作者为规避锁/热日志问题登记无关提案。
- 修复要求: 仅对 "no such table: improvement_proposals" 视为无提案；其余 OperationalError 返回独立 classification 的 STOP。

### F5 (LOW) WAL 模式库下只读连接会生成并遗留 -wal/-shm 边车
- 位置: sire_supervisor.py:259-262；关联 sire_vector_db.py:155（可写连接持久设置 journal_mode=WAL）
- 实测 T10：WAL 库经 rsi_gate 读取后遗留 wal.sqlite3-wal(0B) 与 wal.sqlite3-shm(32KB)，主文件 sha256 不变。真实库当前为 DELETE 模式（文件头 18/19 字节=1/1），因此本次实测真实库无边车；但 run 收尾归档时 sire_vector_db.connect 会把库切为 WAL，此后 finalize 中的 rsi-check 会留下边车。边车已被 sire/.gitignore 忽略，snapshot_db.py:276-284 会清理空边车，不影响数据完整性。
- 修复要求: 在 U-01 验收/文档中注明"无 -wal/-shm"只在 DELETE 模式成立；或读取前检查文件头日志模式并在 WAL 时说明。可作为技术债务。

### F6 (LOW) created_at 时间语义可被异常数据放大为长期放行
- 位置: sire_supervisor.py:288-295
- 实测 T6b：朴素时间 "2099-01-01T00:00:00" 的 PROPOSED 提案 → PASS，且在下次提交前对所有改动长期有效；T6c：提交前 30 分钟的本地朴素时间（UTC+8）被当成 UTC，晚了 8 小时，从而被判为提交后 → PASS。sire_rsi.py 写入带时区 UTC，正常路径不触发；手工写入、跨机器时钟偏差（库通过 Git 共享）可触发。
- 修复要求: 拒绝 created_at > now()+容差 的记录；朴素时间应拒绝或按本地时区解释，并在输出中标注。

### F7 (LOW) git status 结果受外部配置/环境影响，可漏检
- 位置: sire_supervisor.py:249, :275
- 实测 T13：status.showUntrackedFiles=no 时新增 new_script.py 不可见 → PASS；T14：skip-worktree 文件修改不可见 → PASS；T18：继承 GIT_DIR/GIT_WORK_TREE 时检查了另一个干净仓库 → PASS（在 git hook 内调用 finalize 时会出现）。另外 .gitignore 中的 *.bak、*.key、secrets/、integrity/ 等模式在技能目录下同样不可见。
- 修复要求: 使用 `git --no-optional-locks status --porcelain --untracked-files=all -- .`；调用 git 前从 env 中移除 GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE 等；skip-worktree/assume-unchanged 可作为技术债务记录。

### F8 (LOW) git 子进程无超时
- 位置: sire_supervisor.py:249
- git 卡住（例如 fsmonitor、网络盘、锁等待）时 rsi-check/finalize 会无限挂起。修复要求: 加 timeout，TimeoutExpired → STOP。

### F9 (LOW) 审计留痕缺口
- 位置: sire_supervisor.py:312-317
- check() 已把 runs/<RUN_ID>/supervisor-report.json 写为 status=PASS，随后 RSI STOP 只输出到 stderr、不落盘，run 报告显示 PASS 与 finalize rc=3 不一致。修复要求: 把 rsi_gate 结果写入 run 报告或单独证据文件。

## 风险场景
- F1/F2 是门禁核心属性问题：门禁在"无法判断"时放行（fail-open），finalize 会覆盖 BASELINE_MANIFEST，未登记改动随后不可追溯。触发条件为环境类故障（git 缺失、索引损坏、所有权校验、unborn 仓库），不需要恶意操作。
- F3/F4 为 fail-closed，但诊断信息错误或不结构化。
- F5-F9 为数据异常、配置依赖、资源和审计类问题，不直接破坏验收主路径。

## 边界核验（已实测，均在 scratchpad 隔离目录；真实库仅运行只读 rsi-check）
- 注入: subprocess 参数为固定列表，无 shell=True，无外部输入进入 argv；SQL 为静态语句；库路径经 Path.as_uri() 百分号编码，`#`/`%`/空格/中文均正确转义（T16 PASS），无法通过路径注入 URI 参数覆盖 mode=ro。Windows 当前目录放置伪 git.exe 未被调用（实测，不构成问题）。
- 只读: 真实库 rsi-check 前后 sha256 均为 cc4924ce…9659，无 -wal/-shm，.git/index mtime 不变；无表库（T5）读取后未建表、哈希不变、无边车；热日志（T19）未被回滚、journal 保留，说明 mode=ro 生效；WAL 库见 F5。
- 缺失: 库不存在 → STOP rc=3（CLI 实测，输出到 stderr）；表不存在 → STOP；未创建 SIRE_KB_DIR。
- 行数据: created_at 为 NULL / 非 ISO 字符串 / int / blob / 空串、proposal_id 与 status 为 NULL → 不崩溃，均被跳过（T6）；小写 "proposed"、EVALUATED_FAIL、ROLLED_BACK 不匹配（T7）；提交前创建的开放提案不匹配（T8），提交后创建的匹配（T8b）。
- 真实环境: rsi-check → PASS rc=0，匹配 RSI-20260925-R9GATE（created 2026-09-24T21:19:32Z，晚于目录最后提交 2026-09-25T05:18:45+08:00）。
- 资源/并发: SQLite timeout=30 有界（实测独占锁约 42.8s 后返回）；fetchall 仅读 3 列，表规模小；git 无超时见 F8；与 sire_rsi 并发写时依赖 SQLite 锁，最坏结果为 STOP。
- 危险副作用: finalize 在 rsi_check()!=0 时于 :317 返回 3，位于 snapshot/write_json(BASELINE_MANIFEST) 之前（代码核验，按指令未运行 finalize），STOP 不推进基线；rsi_gate 抛异常时同样不推进基线；SKIPPED 时推进基线（F1）。
- 信息泄露: 输出含库绝对路径与 skill_dir 绝对路径，与脚本既有输出（manifest 路径等）一致，仅输出到终端、不落盘；若被复制进会提交的证据，需要按 R9 第 7 条脱敏。不含密钥或个人数据。

## 越界检查
- U-01 代码改动只在 sire_supervisor.py 中（+82 行），无越界。
- 工作区另有 SKILL.md、references/supervisor.md（属于 U-02 文件集）以及 sire/data/sire_vectors.sqlite3（mtime 05:19:32 与 RSI-20260925-R9GATE 的 created_at 一致，来自 propose 流程步骤，不是 U-01 代码写入）。

## 技术债务（可接受遗留）
- 门禁仅按时间窗关联"任意"未失败提案，不绑定改动内容；直接提交工作流改动可绕过（设计范围内）。
- skip-worktree/assume-unchanged、跨机器时钟偏差、WAL 边车（F5）可记录为技术债务。

## 通过条件
修复 F1、F2（最低要求），建议同时修复 F3、F4；复测：索引损坏/无 git/unborn 仓库 → STOP rc=3 且 finalize 不推进基线；非 Git 目录仍为 SKIPPED。

## 第 2 轮（仅复核 F1/F2 修复，F3 与报告落盘顺带核验）

VERDICT: PASS（首行已由第 1 轮的 FAIL 更新为第 2 轮结论 PASS）
检查对象: sire_supervisor.py git_output(247-253) / rsi_proposals(256-272) / rsi_gate(275-322) / rsi_check(325-332) / finalize(335-345)
结论: PASS，F1、F2 已修复，F3 已修复，F9 已修复。

逐项核验（scratchpad 探针 r6b_r2.py 实测）:
- F1 → 已修复: 非 Git 目录 → SKIPPED；目录不存在 → SKIPPED；PATH 中没有 git → STOP rsi_git_undetermined git_rc=127；索引损坏导致 status 失败 → STOP rsi_git_undetermined git_rc=128（:280-288）。git_output 已加 timeout=60，并捕获 OSError/SubprocessError（:249-252），F8 一并修复。
- F2 → 已修复: git log 失败 → STOP（:296-297）；提交时间无法解析 → STOP（:299-302）；unborn 仓库 + 2020 年 ACTIVE 提案 → STOP rsi_unregistered_change，只认 PROPOSED/EVALUATED_PASS（:304）。有未提交改动且只有旧 ACTIVE 时 → STOP；有新 PROPOSED 时 → PASS。
- F3 → 已修复: 捕获 sqlite3.Error，损坏库不再崩溃，结果为 STOP（:260-269）。
- F9 → 已修复: finalize 调用 rsi_check(run_id)，写入 RUNS_DIR/<run>/rsi-report.json（:327-329），写在推进基线之前；写入异常时基线同样不推进。
- 附带: status 已显式使用 --untracked-files=normal 和 --no-optional-locks（:286），showUntrackedFiles=no 时新增文件已能发现（实测 STOP），F7 部分修复。
- 真实库: rsi-check rc=0，sha256 仍为 cc4924ce…9659，无 -wal/-shm，未创建 SIRE_KB_DIR。

遗留（LOW，不阻断）:
- F4 未修: 损坏库/锁/热日志仍报 rsi_unregistered_change（本轮实测损坏库时仍如此）。
- F5 未修: WAL 边车。
- F6 未修: 未来时间和不带时区的时间。
- F7 剩余: GIT_DIR 继承、skip-worktree。
- 新增 LOW: 从未提交的仓库中，任意时间登记的 PROPOSED/EVALUATED_PASS 提案都可放行（实测 2020 年的 PROPOSED 提案 → PASS）。
- 新增 LOW: "not a git repository"/"does not have any commits" 依赖英文错误信息，本机 zh 环境下 git 仍输出英文。若 git 输出被本地化，结果为 STOP（fail-closed），可接受；建议子进程设置 LC_ALL=C。
