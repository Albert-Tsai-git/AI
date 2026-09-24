VERDICT: FAIL

# R4 拆解复核：R20260925-052105

复核对象：`requirements.md`（REQ-02..05）和 `units-draft.json`（U-01..U-03）。本次只读复核，没有修改被审文件。
没有阅读 `sire_supervisor.py` 的实现。只核对了以下内容：`evidence/change.diff` 的文件头，`sire_run.py` 中 add-units 和 close 的装载/收尾校验，`sire_rsi.py` 的 CLI 参数，数据库 RSI 三表（用 `mode=ro&immutable=1` 打开，打开后确认没有产生 -wal/-shm）。

```
门禁: FAIL
1 覆盖     FAIL  REQ-05 在计划里没有承接声明和验收；它的"本地提交"部分与 U-03 的时序冲突（F-03, F-05）
2 无重叠   PASS  U-01 负责代码，U-02 负责文档，U-03 负责数据库 RSI 生命周期，三者没有功能重叠
3 依赖闭环 FAIL  U-03 依赖一个计划外、且排在它之后的提交动作（F-03）；U-02 隐含依赖 U-01 但没有声明（F-04）
4 可验收   FAIL  三条 accept 都不是"当X时应Y"形式，add-units 会全部拒绝（F-01）；U-03 没有定义指标和目标（F-02）；另有 F-06..F-09
5 分区安全 PASS  波次1写集不相交；change.diff 恰好只改 3 个声明文件；U-03 单独一个波次
退回指令: 见文末第 4 节
```

## 1. 发现项

| 编号 | 检查项 | 严重度 | 位置 | 问题 | 修复要求 |
|---|---|---|---|---|---|
| F-01 | 4 | 高（机械阻断） | U-01/U-02/U-03 `.accept` | `sire_run.py` 的 `cmd_add_units`（L437-438）要求 accept 含"应"或"should"。三条 accept 都不含。我按脚本的同一规则离线模拟过，结果 3/3 都是 False。所以即使 G3 记为 PASS，`add-units` 仍会全部拒绝，计划装不进台账。 | 三条 accept 全部改写为"当X时应Y"形式（改写要点见第 4 节）。 |
| F-02 | 4 | 高 | U-03 `.accept` / `.verify` | "evaluate 记录指标且 EVALUATED_PASS"没有给出指标名、基线值、目标值、实测来源和证据路径。self-optimization.md §5.1 要求先定基线和目标，并规定"评估未达到目标时不得激活"。库里 RSI-20260925-R9GATE 在 improvement_metrics 中目前是 0 行，也就是说目标还没登记。如果到 evaluate 时才定目标，门禁就能被事后定标绕过。另外，非目标里写明 evaluate 不支持"越低越好"，所以指标只能是"越高越好"。 | 把 `--metric name,before,after,target,evidence` 的指标清单直接写进 U-03 的 accept（见第 4 节第 5 条）。 |
| F-03 | 3（兼 1） | 高 | U-03 `.accept` 中"config-hash=提交后工作流目录 git tree hash" | 计划里没有任何单元提交 U-01/U-02 的改动。唯一的提交在 REQ-05/G6，但 `sire_run.py close` 要求所有单元先到终态，所以 G6 一定排在 U-03 之后。结果是 U-03 依赖一个计划外的动作，而且时序倒置，accept 无法满足。 | 新增提交单元 U-04，放在 U-01/U-02 之后、U-03 之前（见第 4 节第 3 条）。 |
| F-04 | 3 | 中 | U-02 `deps=[]`，`wave=1` | U-02 的 accept 写"文档描述与 U-01 实现一致"，verify 写"与代码逐字一致"，都要读 U-01 的写集 `sire_supervisor.py`，但 U-02 没有声明依赖，还和 U-01 同波次。scheduler.md 规定并行必须读写集允许。U-01 如果在 R6/R7 返工时改了名称，U-02 的结论就失效了。 | U-02 的 `deps` 改为 `["U-01"]`，`wave` 改为 2；U-02 的 R6/R7 必须在 U-01 的 R6/R7 PASS 之后执行。 |
| F-05 | 1 | 中 | `units-draft.json`、`requirements.md` REQ-05 | REQ-05 没有单元，也没有写明由谁承接。`sire_run.py close` 只机械检查两件事：本 run 新写并已 reindex 的知识记录，以及自动执行 index/migrate。meta 三键、`sire/data/snapshot-manifest.json` 与数据库哈希同步、本地提交、不 push，这些都没有门禁检查。而且 close 自己会写库，所以 manifest 同步和提交只能放在 close 之后，此时已经不在任何门禁范围内。 | 按第 3 节补承接声明和收尾清单；"本地提交"中工作流目录这部分拆到 U-04。 |
| F-06 | 4 | 中 | U-01 `.verify` | accept 中有两条子句在 verify 里没有对应用例：一是"目录无改动时 rc=0"，二是"非 Git 目录返回 SKIPPED"。SKIPPED 对应的 rc 也没有规定。 | verify 补这两条用例，并写明 SKIPPED 的 rc 具体数值（按 U-01 现有实现填写）。 |
| F-07 | 4 | 中 | U-03 `.accept` 中的"工作流目录"；U-03 `.verify` | 目录没有写明。rsi-check 的范围是 shared skill 目录 `sire/workflow/shared/sire`（见 supervisor.md 第 8 项），但"工作流目录"也可以理解成 `sire/workflow`，两种理解得到的 tree hash 不同。verify 里的只读 SQL 也没有给出期望值。 | 按第 4 节第 5 条写死取值命令和期望的终态。 |
| F-08 | 4 | 低 | U-01 `.verify` 中"回归 U-02B qa_all.py" | U-02B 不是本计划的单元，而是暂停 run R20260924-192838 的单元。那个 run 下有 3 个 `qa_all.py`（U-02B、U-08、U-10），容易拿错。 | 写成绝对路径 `D:/sire/.sire/runs/R20260924-192838/evidence/U-02B/qa/qa_all.py`，并写明运行命令和通过判据（输出含 `ALL PASS` 且 rc=0）。 |
| F-09 | 4 | 低 | U-02 `.verify` 中"状态名/分类名/命令名与代码逐字一致" | 没有列出要比对的词，R7 没法照着做。 | 列出比对清单：`rsi-check`、`finalize`、`rsi_unregistered_change`、`STOP`、`PROPOSED`、`EVALUATED_PASS`、`ACTIVE`（在 sire_supervisor.py 中核对）；`propose`、`evaluate`、`activate`、`rollback`（在 sire_rsi.py 中核对）。判据：每个词在文档中出现，并且在对应代码中逐字存在。 |
| F-10 | 5（写集准确性，不构成分区冲突） | 低 | U-03 `.files` | `sire_rsi.py` 写库前会经 `backup_before_mutation` 调用 `sire_db_backup.py`，把备份写到 `SIRE_DB_BACKUP_DIR`（默认 `%USERPROFILE%\sire\db-backups\sire_vectors-*.sqlite3`），并按 keep=14 删除旧备份，此外还会取 `tools/snapshot_db` 锁。development-overlay.md §5 要求 files 是真实文件集。目前没有同波次冲突，所以第 5 项仍判 PASS。 | U-03 的 files 补上备份目录。 |

## 2. 流程偏差（不计入五项判定，由 R0 处理）

- D-1：U-01/U-02 在 G3 之前、也在执行确认之前就由 R5 实施了（`run.json.execution_approval.status=NOT_REQUESTED`）。本复核不会因为"已实现"而放行或放宽。G3 PASS 之后，R0 要先走 approve-units，再对现有 diff 做完整的 R6A/B/C 和 R7。
- D-2：时间线（+08:00）如下：shared 目录最后一次提交 31a3d7d 在 05:18:45；提案 RSI-20260925-R9GATE 的 created_at 是 05:19:32；之后依次是 `sire_supervisor.py` mtime 05:19:58、`SKILL.md` 05:20:08、`supervisor.md` 05:20:11；run INIT 在 05:21:05。
  - 提案早于首次改动，满足 SKILL.md"Before the first edit"的要求。
  - 问题在于 `run.json.workflow_baseline` 是改动之后才抓取的，R9 start→finalize 的漂移比对看不到这 3 个文件的前后变化。R9 记录"声明变更的前后哈希"时，before 值必须取 HEAD(31a3d7d) 中的 blob（change.diff index 行：supervisor.py 7fe8479、SKILL.md 9502467、supervisor.md 71ed8f7），不能用 run.json 里的基线。
- D-3：`D:/sire/AI/AI` 工作区里 `sire/data/sire_vectors.sqlite3` 已经是 M 状态（propose 写入的）。U-04 提交时不要带上数据库，留到 G6 一并提交。

## 3. REQ-05 由 G6 承接是否合理

结论：有条件合理。归档、索引、meta、manifest、提交属于 SKILL.md "On completion" 规定的标准收尾契约，不是 R5 的实施工作，放在 G6 符合流程。成立需要满足三个条件：

1. 声明承接关系：在 `requirements.md` 的 REQ-05 行补一句"承接：G6 收尾（非 R5 单元）"，并附下面的可判定清单。R8/R9 按这份清单核对覆盖情况。
2. 拆出工作流目录的提交：这部分必须拆到 U-04（见 F-03），G6 只提交数据库、manifest、知识和证据。
3. 规定收尾顺序和判据，并把每一步的结果写入 R9/G6 的 stage-output：
   1. 用 `sire_kb.py next-id P` 取新编号，写一条新 P 记录（补 kb-hits.md 中"RSI 触发/接线"的缺口），然后执行 `sire_kb.py reindex`。判据：新编号能在索引中查到。
   2. 执行 `sire_run.py close --records <新编号>`，它会自动执行 index/migrate。判据：rc=0。
   3. `meta.sire_last_project`、`meta.sire_last_run=R20260925-052105`、`meta.sire_last_status` 已写入。判据：只读查询三键的值。
   4. 最后一次写库完成后，同步 `sire/data/snapshot-manifest.json`。判据：manifest 中的哈希与数据库当前哈希一致，且 `PRAGMA integrity_check=ok`。
   5. 执行 `sire_supervisor.py finalize --run-id R20260925-052105`。判据：rsi-check 没有 STOP。
   6. 本地提交。判据：`git status --porcelain` 中数据库、manifest、知识目录都为空；暂存区没有 -wal/-shm；没有执行 push。

## 4. 退回指令（给 R3，按条执行）

1. 按"当X时应Y"改写 accept（解决 F-01）：
   - U-01：当 `D:/sire/AI/AI/sire/workflow/shared/sire` 有未提交改动，且该目录最后一次提交之后没有 PROPOSED/EVALUATED_PASS/ACTIVE 提案时，rsi-check 和 finalize 应返回 rc=3、classification=rsi_unregistered_change，且 finalize 不应推进 BASELINE_MANIFEST。当存在匹配提案或目录没有未提交改动时，应返回 rc=0。当库文件或 RSI 表缺失时，应返回 STOP，不应抛出异常，并且应以只读方式打开数据库。当目录不在 Git 仓库内时，应返回 SKIPPED，rc 写明具体数值。
   - U-02：当 U-01 的 R6/R7 PASS 后，SKILL.md 应含 `## Workflow changes (RSI)` 段，Supporting references 应链接 `references/self-optimization.md`；supervisor.md 的 Checks 应有第 8 项 rsi-check；F-09 清单中每个词都应与代码逐字一致。
   - U-03：按第 5 条改写。
2. U-02：`deps` 改为 `["U-01"]`，`wave` 改为 2；verify 补上 F-09 的比对清单。
3. 新增 U-04，逐字段如下：
   - title：本地提交工作流目录改动
   - maps：REQ-05（提交部分，作为 REQ-04 的前置）
   - owner：R5
   - files：`sire/workflow/shared/sire/SKILL.md`、`sire/workflow/shared/sire/references/supervisor.md`、`sire/workflow/shared/sire/scripts/sire_supervisor.py`（仓库 `D:/sire/AI/AI`）
   - deps：`["U-01","U-02"]`
   - wave：3
   - accept：当 U-01 和 U-02 的 R6/R7 都 PASS 后，应在 `D:/sire/AI/AI` 生成一次只包含上述 3 个文件的本地提交；提交后 `git status --porcelain -- sire/workflow/shared/sire` 应为空；不应暂存 `sire/data/*`；不应 push。
   - verify：`git show --name-only --format= HEAD` 恰好列出这 3 个路径；`git status --porcelain -- sire/workflow/shared/sire` 输出为空；`git status -sb` 的 ahead 计数比提交前多 1。
   - risk：提交之后如果再改 shared skill 目录，由于 R9GATE 提案早于这次提交，rsi-check 会 STOP，需要新建提案。
   - stop：当提交需要包含这 3 个文件以外的文件，或者 R6/R7 没有 PASS 时，停止并退回 R0。
4. U-01 verify：补"目录无改动 → rc=0"和"非 Git 目录 → SKIPPED（写明 rc）"两条用例；qa_all.py 改用 F-08 中的绝对路径，并写明通过判据。
5. U-03：
   - (a) 依赖和波次：`deps` 改为 `["U-04"]`（可同时保留 U-01、U-02），`wave` 改为 4。
   - (b) 在 accept 中写死指标，全部为越高越好，并且每项都应满足 after ≥ target 才能 activate：
     - `rsi_unregistered_stop,0,<实测>,1,<U-01 R7 证据路径>`：未登记改动被 finalize STOP 的用例是否全部通过。改动前没有这项检查，所以基线为 0。
     - `rsi_entry_reachable,0,<实测>,1,<U-02 R7 证据路径>`
     - `regression_pass,1,<实测>,1,<qa_all.py 输出路径>`
     - 任一项不达标时，应按 stop 字段处理，不应 activate。
   - (c) config-hash 应等于在 U-04 之后执行 `git -C D:/sire/AI/AI rev-parse HEAD:sire/workflow/shared/sire` 得到的值。
   - (d) verify 写明期望终态：
     - R9GATE 的 status=ACTIVE，evaluated_at 和 activated_at 非空；
     - improvement_metrics 中 R9GATE 共 3 行，passed 全部为 1；
     - v6.2 的 status=ACTIVE、proposal_id=RSI-20260925-R9GATE、config_hash 等于 (c) 的值；
     - v6.1 的 status=RETIRED，retired_at 非空；
     - workflow_versions 中 ACTIVE 恰好 1 行；
     - `PRAGMA integrity_check=ok`；
     - 查询用 URI `mode=ro&immutable=1`，查询后没有 -wal/-shm。
   - (e) files 补上备份目录 `%USERPROFILE%\sire\db-backups\`（或 `SIRE_DB_BACKUP_DIR`）。
6. REQ-05：在 `requirements.md` 补上第 3 节的承接声明和收尾清单。本条属于 R2 产物，由 R0 转交 R2/R3 修改。
7. 修改完成后重新提交 R4 复核，不要直接记 G3。

## 第 2 轮（复核 units.json.in 与 requirements.md 修订）

VERDICT: FAIL

核对范围：只核对第 1 轮退回指令是否已落实。数据库只用 `mode=ro&immutable=1` 读取，没有写入。

| 第 1 轮项 | 结果 | 说明 |
|---|---|---|
| F-01 accept 形式 | 已落实 | 4 条 accept 都含"应"。 |
| F-03 提交单元 | 已落实 | 已新增 U-04，deps 为 U-01/U-02，wave 3；U-03 依赖 U-04，wave 4。 |
| F-04 U-02 依赖 | 已落实 | deps 为 ["U-01"]，wave 2。 |
| F-06 / F-08 U-01 用例与路径 | 已落实 | 已补非 Git 与不存在目录（SKIPPED rc=0）、提交后无改动两类用例；qa_all.py 已改为绝对路径并写明 ALL PASS、rc=0 判据。 |
| F-09 比对清单 | 已落实 | 清单已列出。 |
| F-10 备份目录 | 已落实 | 已加入 files。 |
| F-02 指标 | 未落实（高） | U-03 的 `rsi_rule_reachable,0,1,1` 和 `rsi_gate_tests_pass,0,1,1` 把实测值 after=1 预先写死了，而且缺少 evidence 字段（sire_rsi 的格式是 name,before,after,target,evidence）。这样写，"评估应为 EVALUATED_PASS"变成恒真，正好是 F-02 要堵的事后定标漏洞。regression_pass 指标也被删掉了。 |
| F-07 config_hash 取值 | 部分落实（中） | 命令没有带 `-C D:/sire/AI/AI`。D:/sire 本身不是 Git 仓库（已实测 rev-parse 报 fatal），取值结果取决于在哪个目录执行。verify 也没有核对 config_hash 相等、ACTIVE 恰好 1 行、查询后没有 -wal/-shm。 |
| F-05 REQ-05 承接 | 部分落实（中） | 顺序写成"close 之后才写 P 记录并 reindex"，但 `sire_run.py close` 要求记录已写入且已进索引（L1096-1099），按这个顺序 close 会失败。清单里还漏了 `sire_supervisor.py finalize`（rsi-check），也没写"暂存区没有 -wal/-shm"这条判据。 |

新发现：

- N-01（高）：U-03 改成在归档库 `D:/sire/sire_vectors.sqlite3`"登记同 ID 提案"。
  - 已只读核实，归档库里没有 RSI-20260925-R9GATE，只有仓库库里有，created_at 为 05:19:32+08，早于首次改动。
  - 按这个计划，归档库会新建一条 created_at 晚于改动和 U-04 提交的提案；随后 G6 用 snapshot_db 从归档库重建仓库库，会覆盖掉原始的 05:19:32 记录。
  - 结果是 RSI 审计里"先提案后改动"的证据丢失，违反 self-optimization.md §5.1 和 SKILL.md 的"Before the first edit"。
  - 这也超出了 REQ-04"propose（已做）"的范围，requirements.md 没有同步修改。

第 2 轮退回指令（给 R3）：

1. U-03 的指标只写 name、before、target，并写明 evidence 路径。after 必须从 R7 证据中读取实测值，不得预先写死。恢复 `regression_pass` 这项指标，before=1，target=1，after 取 qa_all.py 的结果。
2. config_hash 的取值命令写成 `git -C D:/sire/AI/AI rev-parse HEAD:sire/workflow/shared/sire`。verify 补上：config_hash 等于该值；evaluated_at 和 activated_at 非空；ACTIVE 版本恰好 1 行；只读查询后没有新增 -wal/-shm。
3. 对归档库的处理二选一，并写进 U-03 的 accept：
   - (a) 把仓库库中 R9GATE 的原始提案行原样迁入归档库，保留原 created_at=2026-09-24T21:19:32.584126+00:00，再做 evaluate/activate；verify 核对这个 created_at 没有变化。
   - (b) 如果 sire_rsi.py 做不到原样迁入，就停止并退回 R0，由 R0 决定库的归属，不得新建同 ID 提案。
   - 无论选哪一项，都要同步修改 requirements.md 的 REQ-04。
4. REQ-05 清单按以下顺序改写：写 P 记录 → reindex → `sire_run.py close --records`（index/migrate）→ meta 三键 → snapshot 重建与 manifest 哈希核对 → `sire_supervisor.py finalize` 且 rsi-check 不为 STOP → 本地提交（暂存区没有 -wal/-shm，不 push）。

## 第 3 轮（只核对第 2 轮提出的 3 点）

VERDICT: PASS

```
门禁: PASS
1 覆盖     PASS  REQ-02 由 U-02 承接，REQ-03 由 U-01 承接，REQ-04 由 U-03 承接；REQ-05 的工作流目录提交由 U-04 承接，其余由 G6 按 requirements.md 的 7 步清单承接
2 无重叠   PASS
3 依赖闭环 PASS  U-01 → U-02 → U-04 → U-03 → G6，无环，也不依赖计划外的动作
4 可验收   PASS  4 条 accept 都是"当X时应Y"形式；U-03 的 after 值取自实测，证据路径已写明
5 分区安全 PASS  每个波次只有 1 个单元；文件交集只出现在有依赖关系的单元之间
退回指令: 无
```

| 第 2 轮项 | 结果 | 核对依据 |
|---|---|---|
| F-02 / 指标 | 已落实 | 3 项指标只写死了 before 和 target，after 分别取自以下实测：grep 结果、R7 test.md 的 VERDICT、qa_all.py 的 ALL PASS。`regression_qa_all_pass` 已加回，before=1，target=1。verify 核对 improvement_metrics 共 3 行，passed 全部为 1，evidence 指向实测证据。 |
| N-01 / 归档库提案 | 已落实 | accept 要求把仓库库中的原始提案行原样复制进归档库，保留 created_at=2026-09-24T21:19:32.584126+00:00，写库前先备份并持锁。verify 核对该 created_at 与原值相同。G6 第 ⑥ 步还会在快照重建后再核对一次 created_at。 |
| F-07 / F-05 取值命令与收尾顺序 | 已落实 | tree hash 命令已带 `-C D:/sire/AI/AI`。G6 顺序是：写记录并 reindex → finalize/rsi-check → finish → meta → snapshot → 核对 → 提交。这个顺序满足两条硬约束：`finish` 要求记录已进索引，并且 R9 的阶段产物已存在。 |

第 2 轮还要求补两项，这次修订没有写入，但不影响本轮结论：

- U-03 的 verify 没写"ACTIVE 版本恰好 1 行"和"evaluated_at、activated_at 非空"。这两项可由已有检查推出：只读查询确认归档库目前只有 v6.1 一个版本，已有检查要求 v6.2=ACTIVE 且 v6.1=RETIRED，由此可推出 ACTIVE 恰好 1 行；status=ACTIVE 也只能经 activate 产生。
- G6 第 ⑦ 步没写"暂存区没有 -wal/-shm"。已实测 `sire/.gitignore` 第 2–4 行忽略了 `*.sqlite3-wal`、`*.sqlite3-shm`、`*.sqlite3-journal`。R0 提交时仍应执行一次 `git diff --cached --name-only`，确认暂存区没有这三类文件。

交给 R0 记账：G3 可以记为 PASS。第 1 轮 D-1 仍然有效：U-01/U-02 已经实现，但仍需先走 approve-units，再补做完整的 R6A/B/C 和 R7，不能拿"已实现"代替复核。
