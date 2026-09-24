VERDICT: PASS

单元: U-01（附 U-02 文档小节）
方向: R6A 行为正确性（独立盲审，未读取 R6B/R6C 报告与实现者推理）
结论: PASS

## 检查对象

- D:/sire/AI/AI/sire/workflow/shared/sire/scripts/sire_supervisor.py（工作区全文 + change.diff）
- D:/sire/AI/AI/sire/workflow/shared/sire/SKILL.md、references/supervisor.md（U-02）
- 对照：scripts/sire_rsi.py（表结构与状态写入）、scripts/sire_paths.py（DATABASE_PATH / SHARED_SKILL_DIR）、references/self-optimization.md 5.1 节
- 验收：units-draft.json 的 U-01 / U-02 accept 字段；requirements.md 的 REQ-02 / REQ-03

## 验收对照（U-01）

| 验收项 | 结果 | 依据 |
|---|---|---|
| 有未提交改动且最后提交后无 PROPOSED/EVALUATED_PASS/ACTIVE 提案 → rsi-check rc=3 + rsi_unregistered_change | 满足 | sire_supervisor.py:299-301, 304-308；CLI 实测（SIRE_VECTOR_DB 指向空库）rc=3，STOP JSON 输出到 stderr |
| finalize 同条件 rc=3 且不推进 BASELINE_MANIFEST | 满足 | sire_supervisor.py:315-317 在 snapshot/write_json 之前返回；打桩实测 FIN-STOP rc=3，snapshot/write_json 调用数为 0 |
| 有匹配提案或目录无改动 → rc=0 | 满足 | 真实库实测 PASS rc=0（匹配 RSI-20260925-R9GATE，created_at 2026-09-24T21:19:32Z，晚于最后提交 2026-09-25T05:18:45+08:00）；干净目录场景 PASS |
| 数据库只读打开，库/表缺失不崩溃 | 满足 | :259-261 mode=ro + PRAGMA query_only；真实库运行前后 sha256 都是 cc4924ce...9659，无 -wal/-shm；库头字节 18/19 为 1/1（回滚日志模式，只读打开不会产生 -shm）；无库文件、0 字节文件、无表的库都返回 STOP，没有崩溃 |
| 非 Git 目录 → SKIPPED | 满足 | :272-274；实测 A-nongit 为 SKIPPED |

## 行为路径核验（临时 git 仓库 + 临时库，直接调用 rsi_gate；finalize 依赖打桩，不写真实基线）

- 状态过滤：EVALUATED_FAIL / ROLLED_BACK 即使晚于提交也 STOP；PROPOSED / EVALUATED_PASS / ACTIVE 晚于提交时 PASS；小写 proposed 会 STOP（sire_rsi 写的是大写，所以一致）
- 时间比较：提案早于提交 1 秒时 STOP，晚于提交 1 秒时 PASS；ACTIVE 提案早于提交也 STOP
- 时区：提交带 +08:00，提案用 UTC +00:00 存储，按绝对时间比较，结果正确；Git 2.45 对 UTC 提交输出 Z 后缀（实测 2026-09-24T21:18:45Z），在 Python 3.12 下可正确解析；提案带 Z 后缀也能解析
- created_at 异常：None 或无法解析的字符串会被跳过，最终 STOP；没有时区的时间串按 UTC 处理
- 改动类型：仅修改、仅暂存、删除、仅新增未跟踪文件、新增未跟踪子目录，全部识别为改动并 STOP
- 范围：只有工作流目录外的文件改动时 PASS；目录外有更晚的提交不影响 since，since 只取工作流目录的最后提交
- 工作流目录从未提交（仓库有其他提交）或仓库一个提交都没有：since=None；没有提案时 STOP，有任意开放提案（包括 2020 年的旧提案）时 PASS（见发现 1）
- 损坏的库文件：抛出 DatabaseError，未被捕获（见发现 2）
- 通过 ~/.claude/skills/sire-global-workflow 别名调用时，SHARED_SKILL_DIR 解析到 D:\sire\AI\AI\sire\workflow\shared\sire，结果与直接路径一致
- 数据库路径包含中文、空格和 # 时，as_uri 生成的 URI 能正常打开，不产生旁路文件

## 发现（U-01）

1. [LOW] sire_supervisor.py:281-283, 294。问题：git log 的返回码被忽略；工作流目录从未提交、仓库没有提交或 git log 失败时 since=None，任意 PROPOSED/EVALUATED_PASS/ACTIVE 提案都算匹配，不看创建时间。真实库中 RSI-20260921-DB 一直保持 ACTIVE（sire_rsi.py:53-55 激活新版本时只把 workflow_versions 标为 RETIRED，不改旧提案状态），所以这条路径上门禁实际会一直 PASS。对规范中的已提交目录，这条路径基本不可达。修复要求（非阻断）：检查 git log 返回码；since 为 None 时只接受 PROPOSED/EVALUATED_PASS，或者返回单独分类的 STOP。
2. [LOW] sire_supervisor.py:259-266。问题：只捕获 OperationalError。库文件损坏时抛出 sqlite3.DatabaseError，打出 traceback，rc=1（实测 P-corrupt）；sqlite3.connect 在 try 之外。库被写锁占用超过 30 秒时返回空列表，会被误报为 rsi_unregistered_change。整体是 fail-closed，但分类不准。修复要求（非阻断）：捕获 sqlite3.DatabaseError，给出单独分类（例如 rsi_db_unreadable）。
3. [LOW] sire_supervisor.py:283。问题：datetime.fromisoformat(last_commit) 没有异常保护；Git 对 UTC 提交输出 Z 后缀，Python 3.11 以下无法解析，会抛 ValueError。当前环境是 Python 3.12.10，不受影响。修复要求（非阻断）：解析前把 Z 替换为 +00:00，或者加 try。
4. [LOW] sire_supervisor.py:272-277 与 :316。问题：SKIPPED 返回 rc=0，finalize 会继续推进基线；git 不存在或 git status 失败（例如 safe.directory 报 dubious ownership）时门禁 fail-open。这符合“非 Git 目录返回 SKIPPED”的验收，但没有区分“不在仓库中”和“git 执行出错”，文档也没写（见 U-02 D2）。修复要求（非阻断）：git 执行出错时返回 STOP，或者至少写进文档。
5. [LOW] sire_supervisor.py:312-317。问题：check() 已经把 status=PASS 写入 RUNS_DIR/<run>/supervisor-report.json，随后 RSI 门禁 STOP，但 STOP 结果只输出到 stderr，没有落盘。审计时读报告文件会看到 PASS。目前 sire_run.py / sire_bundle.py 都不读取 finalize 的输出，不影响自动化流程。修复要求（非阻断）：把 rsi_gate 的结果写进本 run 的报告文件，或单独写 rsi.json。
6. [LOW] sire_supervisor.py:275。问题：git status 没有显式指定 --untracked-files，用户如果配置了 status.showUntrackedFiles=no，新增的未跟踪文件会被漏掉。修复要求（非阻断）：加 --untracked-files=all，同时建议加 --no-optional-locks，以符合“只读”的说法。本次实测 .git/index 的 mtime 没有变化。
7. [INFO] sire_supervisor.py:315。注释说“不推进基线是为了下次还能发现”，但再次发现依赖的是 git status，与基线无关。只是注释表述不准，行为没有问题。

越界检查: 无越界。diff 只涉及 sire_supervisor.py、SKILL.md、references/supervisor.md，分别属于 U-01/U-02 的文件集。工作区里另有 M sire/data/sire_vectors.sqlite3，来自 REQ-04 的 propose（RSI-20260925-R9GATE），属于 U-03 的文件集，不算 U-01/U-02 的越界改动。本次复核前后该库的 sha256 没有变化。

技术债务: 发现 1-7 都是可接受的遗留问题，不阻断：均为 fail-closed、不可达或只影响可观测性。发现 1 被 sire_rsi 旧提案一直保持 ACTIVE 放大，而修改 sire_rsi 属于本 run 非目标，建议另开提案处理。

## U-02 文档复核

结论: PASS

验收对照:
- SKILL.md 有“## Workflow changes (RSI)”段（SKILL.md:76-78）：满足
- Supporting references 链接 self-optimization.md（SKILL.md:87），目标文件存在，其中有“## 5.1 RSI 改进门禁”（self-optimization.md:72）：满足
- supervisor.md Checks 新增第 8 项 rsi-check（supervisor.md:26）：满足
- 文档与 U-01 实现逐字对照：
  - 命令名 rsi-check / finalize 与 sire_supervisor.py:406, 404, 419-420 一致
  - sire_rsi.py 的 propose / evaluate / activate / rollback 与 sire_rsi.py:28-31 一致
  - “只能激活 EVALUATED_PASS”与 sire_rsi.py:52 一致
  - 状态名 PROPOSED / EVALUATED_PASS / ACTIVE 与 :244 一致
  - 分类名 rsi_unregistered_change 与 :299 一致
  - “不推进基线”与 :316-317 一致
  - “只读读库”与 :259-261 一致
  - “最后一次提交之后创建”与 :281-294 一致
  - 结论：满足

发现（U-02）:
- D1 [LOW] SKILL.md:78。“Full rules: self-optimization.md 5.1”说法偏大：5.1 节（self-optimization.md:72-78）只讲 RSI 生命周期，不包含 R9 门禁规则（rsi-check、开放状态集合、rsi_unregistered_change、以最后提交为时间点），也没有“首次编辑前先 propose”。门禁的完整描述只在 supervisor.md:26。修复要求（非阻断）：把门禁细节指向 supervisor.md；如需在 5.1 节补充，超出 U-02 文件集，另行处理。
- D2 [LOW] SKILL.md:78 / supervisor.md:26。没有写明 SKIPPED 语义（非 Git 目录或 git 不可用时 rc=0，finalize 照常推进基线），也没有写从未提交目录的语义（since 为空时任意开放提案都匹配）。
- D3 [INFO] 文档写“created after”，代码用 >=（同一秒也算），提交时间精度为秒，影响可以忽略。

## 验证命令记录（只读）

- python -B sire_supervisor.py rsi-check（真实库）→ PASS rc=0；前后 sha256 都是 cc4924ce0b309f846a1fcfa77664067e04afefc1c3ab34aa5c9abcf76afe9659，data/ 下没有 -wal/-shm
- SIRE_VECTOR_DB=<临时 0 字节库，路径含中文/空格/#> python -B sire_supervisor.py rsi-check → STOP rc=3，stderr 含 classification=rsi_unregistered_change，stdout 为空
- 经 ~/.claude/skills/sire-global-workflow 别名调用 rsi-check → PASS rc=0
- 场景脚本 scratchpad/r6a/scen.py：在临时仓库和临时库中跑 30 个场景（结果见上文“行为路径核验”）；finalize 打桩后四种情况为 STOP rc=3 且无写入 / PASS rc=0 且写入 / SKIPPED rc=0 且写入 / check 为 STOP 时 rc=3 且无写入
- 没有运行 start / finalize / preflight 真实命令，没有写本机完整性基线；没有修改任何被审文件
