VERDICT: PASS

# U-01 R7 功能测试：sire_supervisor.py rsi-check 与 finalize 集成

- 被测：`D:/sire/AI/AI/sire/workflow/shared/sire/scripts/sire_supervisor.py`（未提交改动，见 `../../change.diff`）
- 执行时间：2026-09-25 05:27:45 起（本机 +08:00）；Python 3.12.10（`C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe`）
- 执行方式：全部真实执行，脚本为 `qa_u01.py`（主测试）、`t8_inproc.py`（T8 进程内调用）、`qa_x1_finalize.py`（额外观察 X1b）
- 完整命令与输出：`run-output.log`；结构化结果：`results.json`；X1b 结果：`x1-finalize-garbage.json`
- 环境确认：`sire_paths.py` 在 import 时读取 `SIRE_VECTOR_DB` → `DATABASE_PATH`、`SIRE_KB_DIR` → `KNOWLEDGE_DIR`；`sire_bundle.kb_dir()` 直接返回 `KNOWLEDGE_DIR`，`sire_supervisor.INTEGRITY_DIR = kb_dir()/"integrity"`。因此测试按子进程注入环境变量。子进程统一移除 `SIRE_VECTOR_DB/SIRE_KB_DIR/SIRE_ROOT/SIRE_DATA_DIR` 后按用例注入，并设 `PYTHONPYCACHEPREFIX=qa/tmp/pycache` + `PYTHONDONTWRITEBYTECODE=1`，避免往工作流目录写 .pyc。
- 测试时的门禁前提：工作流目录 `git status --porcelain -- .` 有 3 个 M（SKILL.md、references/supervisor.md、scripts/sire_supervisor.py）；该目录最后提交 `31a3d7d 2026-09-25T05:18:45+08:00`（= 21:18:45Z）；真实库提案：RSI-20260921-DB ACTIVE 2026-09-21、RSI-TEST-ROLLBACK ROLLED_BACK 2026-09-21、RSI-20260925-R9GATE PROPOSED 2026-09-24T21:19:32Z。

## 逐项结果

| 编号 | 操作步骤 | 预期 | 实际 | 结论 |
|---|---|---|---|---|
| T1 正常 | cwd=scripts，不设 SIRE_VECTOR_DB，`python sire_supervisor.py rsi-check` | rc=0，status=PASS，matched_proposals 含 RSI-20260925-R9GATE | rc=0，status=PASS，matched_proposals=[RSI-20260925-R9GATE]（较早的 ACTIVE 提案 RSI-20260921-DB 按时间正确排除），changed=3 个文件，last_workflow_commit=2026-09-25T05:18:45+08:00 | PASS |
| T2 异常 | 复制真实库到 tmp/db_noprop.sqlite3（副本 sha256 与源一致），`DELETE` R9GATE，SIRE_VECTOR_DB=副本运行 rsi-check | rc=3，STOP，rsi_unregistered_change | rc=3，stderr JSON status=STOP，classification=rsi_unregistered_change，matched_proposals=[]（剩余 ACTIVE 提案早于提交，未误匹配） | PASS |
| T3 边界 | SIRE_VECTOR_DB 分别指向：①tmp/nope/missing.sqlite3（不存在）②tmp/empty0.sqlite3（0 字节）③tmp/no_table.sqlite3（只有 other 表） | 均 rc=3、STOP，无 Traceback | 三种情况均 rc=3、STOP、rsi_unregistered_change、无 Traceback；①未创建文件；②③ sha256 前后一致，无 -journal/-wal/-shm | PASS |
| T4 边界 | tmp/db_var.sqlite3 副本依次 UPDATE R9GATE：a status=EVALUATED_FAIL；b status=ROLLED_BACK；c PROPOSED + created_at=2026-09-20T00:00:00+00:00；d PROPOSED + created_at=2026-09-25T00:00:00（naive） | a/b/c STOP；d 不崩溃 | a/b/c 均 rc=3、STOP、rsi_unregistered_change；d rc=0、PASS、匹配 R9GATE（naive 按 UTC 解释，晚于 21:18:45Z），无 Traceback。额外子项：e created_at 恰等于提交时间 → PASS（>= 边界）；f created_at=not-a-date → STOP 无崩溃；g EVALUATED_PASS → PASS；h ACTIVE → PASS | PASS |
| T5 只读 | T1 前后计算真实库 sha256/mtime，列 data 目录 | sha256 不变，无 -wal/-shm/-journal | 前后 sha256 均为 cc4924ce0b309f846a1fcfa77664067e04afefc1c3ab34aa5c9abcf76afe9659，mtime_ns 1790284772590226500 不变；data 目录前后均只有 sire_vectors.sqlite3、snapshot-manifest.json；全部测试结束时 sha256 仍相同 | PASS |
| T6 finalize 集成 | 复制真实知识目录（排除 integrity/secrets/exports 链接与目录）到 tmp/kb_a、tmp/kb_b；各自 SIRE_KB_DIR=临时目录执行 preflight → start --run-id QA-RSI → finalize --run-id QA-RSI；a 用无提案副本，b 用含提案的真实库副本 | a：finalize rc=3 且 manifest.json 不变；b：finalize rc=0 FINALIZED | a：preflight INITIALIZED、start STARTED、run-check 报告 PASS，finalize rc=3，stderr classification=rsi_unregistered_change；manifest.json sha256 前后均 d1194b2d…，label 仍为 baseline，未生成 snapshots/baseline-next。b：finalize rc=0，末行 status=FINALIZED；manifest sha256 1fa5f147… → 30b7d99c…，label=baseline-next，生成 baseline-next 快照。T6 后含提案副本 sha256 仍与源相同（finalize 未写库）；真实知识目录（含 integrity 链接目标）前后文件清单与 size/mtime 完全一致 | PASS |
| T7 回归 | `python qa_all.py qa/tmp/u02b U-02B`；`python sire_supervisor.py --help` | qa_all 输出 ALL PASS；--help 列出 rsi-check | qa_all rc=0，30 条 PASS、0 条 FAIL，末行 ALL PASS；--help rc=0，子命令列表含 rsi-check | PASS |
| T8 边界 | 子进程 import sire_supervisor 并调用 `rsi_gate(skill_dir=...)`：a 系统临时目录 `C:\Users\ADMINI~1\AppData\Local\Temp`（git rev-parse rc=128，真实非 Git）；b qa/tmp/nogit + `GIT_CEILING_DIRECTORIES=qa/tmp`（rev-parse rc=128；不设 ceiling 时会上溯到 D:/code/driverSoftware） | status=SKIPPED，不抛异常 | a、b 均未抛异常，status=SKIPPED，reason=工作流目录不在 Git 仓库中或未找到 git | PASS |

## FAIL 发现与额外观察

协调者要求把 X1、X4 列为 FAIL 发现，交 R5 修复。T1–T8 全部 PASS，因 X1、X4 未通过，整体 VERDICT 为 FAIL；R5 修复后只复测 X1、X4。

- X1【FAIL】：SIRE_VECTOR_DB 指向**存在但不是 sqlite 的文件**（tmp/garbage.sqlite3，纯文本）时，`rsi-check` 以 rc=1 + Traceback 退出（`sqlite3.DatabaseError: file is not a database`），没有输出结构化 STOP/rc=3。原因：`rsi_proposals` 只捕获 `sqlite3.OperationalError`，而 `DatabaseError` 是它的父类，不会被捕获。X1b：同场景下 finalize rc=1、Traceback，但 manifest.json 未变、未生成 baseline-next，即**故障安全（不推进基线）**，只是分类与退出码不规范。证据：`run-output.log` 的 `[X1 垃圾文件（额外观察）]` 段、`x1-finalize-garbage.json`。
- X2：SIRE_VECTOR_DB 指向目录 → rc=3、STOP，无崩溃。
- X3：子进程 PATH 只含 `C:\Windows\System32`（找不到 git）→ rsi_gate 返回 SKIPPED，无异常。
- X4【FAIL】：`rsi_gate(skill_dir=<不存在的目录>)` 抛 `NotADirectoryError`（WinError 267），因为 `git_output` 只捕获 `FileNotFoundError`。CLI 的 skill_dir 固定为脚本所在的父目录，正常使用不会触发。

## 隔离与副作用核对

- 真实库 `D:/sire/AI/AI/sire/data/sire_vectors.sqlite3` 只读：开始与结束时 sha256 相同，data 目录没有新增文件。
- 工作流目录 `D:/sire/AI/AI/sire/workflow/shared/sire`：测试前后递归文件清单（含 __pycache__，size+mtime）零差异；`git status --porcelain` 前后相同；最后提交未变化。注：`scripts/__pycache__/sire_supervisor.cpython-312.pyc` 的 mtime 为 05:25:46，早于本测试开始时间 05:27:45，是其他会话写入的，不是本测试写入。
- 真实知识目录：前后清单零差异（跟随 integrity/secrets 链接统计）。没有对真实知识目录运行 start/finalize/preflight。
- qa_all.py 内部的 `py_compile` 受 `PYTHONPYCACHEPREFIX` 影响，字节码写到 qa/tmp/pycache（已清理）。
- 3 份约 47MB 的数据库副本在测试结束后已删除；保留 tmp/ 下小文件（empty0/no_table/garbage sqlite、kb_a/kb_b/kb_c 隔离知识目录及其 integrity 产物）作为证据。

## 复测（R5 修复 X1/X4 后）

R5 的修复：`rsi_proposals` 改为捕获 `sqlite3.Error`，连接失败也返回空列表；`git_output` 改为捕获 `OSError`（grep 确认在 sire_supervisor.py 第 250、262、267 行）。复测只执行下面 3 项；脚本是 `retest.sh`，完整输出在 `retest-output.log`。字节码仍重定向到 tmp/pycache。

| 编号 | 操作 | 预期 | 实际 | 结论 |
|---|---|---|---|---|
| R1（X1） | `SIRE_VECTOR_DB=qa/tmp/garbage.sqlite3`（纯文本文件）`python sire_supervisor.py rsi-check` | rc=3、STOP、无 Traceback | rc=3，status=STOP，classification=rsi_unregistered_change，matched_proposals=[]，无 Traceback；garbage 文件 sha256 前后一致 | PASS |
| R2（X4） | `t8_inproc.py`：进程内 `rsi_gate(skill_dir=qa/tmp/does-not-exist)` | 返回 SKIPPED，不抛异常 | raised=false，status=SKIPPED，reason=工作流目录不在 Git 仓库中或未找到 git | PASS |
| R3 | 真实库 `python sire_supervisor.py rsi-check` | rc=0、PASS | rc=0，status=PASS，matched_proposals=[RSI-20260925-R9GATE]；真实库 sha256 前后都以 cc4924ce0b309f84 开头，data 目录没有 -wal/-shm/-journal | PASS |

复测后：T1–T8 仍为 PASS（本轮没有重跑），X1/X4 已关闭，所以 VERDICT 从 FAIL 改为 PASS。

## 复测2（R5 按 R6 MEDIUM 意见再次修改后）

被测文件 sha256 为 `88f7946f08826340252984cfd03636fc3f0fdb91a780010e4c72a9c77e38024a`，运行前后都记录了，值相同（见 `retest2-target-sha.txt`）。脚本是 `retest2.py`，输出在 `retest2-output.json`。
第一次运行时，被测文件在 05:31:00 被 R5 再次修改，那次结果作废，存档为 `retest2-output-run1-midchange.json`。以下结论全部来自文件稳定后的第二次运行。
提案库是 qa/tmp 下的小型 sqlite：表结构以只读方式取自真实库，只放一条提案 RSI-QA-OLD，created_at 为 2026-09-21。

| 编号 | 操作 | 预期 | 实际 | 结论 |
|---|---|---|---|---|
| R1 | 在 qa/tmp 下 `git init` 临时仓库，子目录 workflow/ 从未提交，里面只有一个未跟踪文件（git status 为 `?? workflow/`）。先把提案设为 ACTIVE，调用 `rsi_gate(db_path=副本, skill_dir=workflow)`；再改为 PROPOSED 调用一次。分两种仓库各测一遍：1a 仓库根有其他提交，1b 仓库零提交 | ACTIVE 时 STOP；PROPOSED 时 PASS | 1a：ACTIVE → STOP / rsi_unregistered_change，matched=[]；PROPOSED → PASS，matched=[RSI-QA-OLD]。1b 结果与 1a 相同。last_workflow_commit 均为 null；未跟踪文件记入 changed=[workflow/] | PASS |
| R2 | 复制真实知识目录（排除 integrity/secrets/exports）到 tmp/kb_d，设 SIRE_KB_DIR=tmp/kb_d，库里只有早于提交的 ACTIVE 提案；依次执行 preflight → start --run-id QA-RSI2 → finalize --run-id QA-RSI2 | finalize STOP 时 RUNS_DIR/QA-RSI2/rsi-report.json 存在，且 status=STOP | preflight 和 start 的 rc 均为 0；finalize rc=3，无 Traceback；tmp/kb_d/integrity/runs/QA-RSI2/rsi-report.json 存在，status=STOP，classification=rsi_unregistered_change，带 checked_at；manifest.json 不变 | PASS |
| R3 | 真实库 `python sire_supervisor.py rsi-check` | rc=0，真实库 sha256 不变 | rc=0，status=PASS，matched=['RSI-20260925-R9GATE']；sha256 前后均为 cc4924ce0b309f846a1fcfa77664067e04afefc1c3ab34aa5c9abcf76afe9659；data 目录前后都是 ['sire_vectors.sqlite3', 'snapshot-manifest.json'] | PASS |

补充说明（不在本轮复测范围）：新代码把“找不到 git 或 rev-parse 失败（不在 Git 仓库的情况除外）”改为 STOP / `rsi_git_undetermined`，并且在 skill_dir 不存在时直接返回 SKIPPED。所以第一轮 X3（PATH 中没有 git → SKIPPED）的观察结果已被新设计取代，本轮没有复测 X3。

复测2 结论：R1–R3 全部 PASS，VERDICT 保持 PASS。
