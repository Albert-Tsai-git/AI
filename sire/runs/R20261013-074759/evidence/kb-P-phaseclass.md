**日期**: 2026-10-13
**项目**: SIRE v6.14 遥测阶段归属收紧（`D:\sire\AI\AI\sire`）
**状态**: 已验证（run R20261013-074759，RSI-20261013-PHASECLASS → v6.14）
**关键词**: SIRE, 遥测, sire_telemetry, PHASE_PATTERNS, classify, ledger, archive, CLOSE_HEAVY, FAST_SCOPE, 误报, .sire/runs, knowledge/global, detail 截断, RSI, v6.14

**需求场景 / 现象**: RSI 自动发现的 `CLOSE_HEAVY`（收尾占完整任务 40% 以上）累积到 3 次命中转为 PROPOSED，证据是 `收尾 94s/231s`、`155s/304s`、`419s/912s`；第三条里 ledger 一个阶段就占 419s / 19 次调用。同时 `FAST_SCOPE`（快速通道越界）也在一次 10.7 秒的快任务上误报，唯一越界阶段仍是 ledger。

**根因**: 阶段归属靠 `PHASE_PATTERNS` 对"工具名 + 工具输入 JSON 文本"做先命中先用的正则匹配，两个模式的匹配面过宽：
1. `ledger = sire_run\.py|[\\/]runs[\\/]|[\\/]\.sire[\\/]` —— 任何命令里出现 `.sire/runs/` 路径就算写台账。真实场景测试（R7）的夹具与 Playwright 脚本恰好都放在 run 目录下（`.sire/runs/R…/ui_fixture.py`、`getByRole('button').click()`），于是被整段记成收尾时间。
2. `archive` 里含裸 `knowledge[\\/]+global` —— 读 `knowledge/global/KNOWLEDGE_TEMPLATE.md` 这类检索动作被记成归档收尾。
3. 附带缺陷：钩子把事件 `detail` 截断到 160 字，导致事后无法重新分类核对（现存 161 条 ledger/archive 事件里 145 条已是不可解析的半截 JSON），规则命中对不对根本复核不了。
4. 一次 Bash 里串多条命令只归一个阶段（先命中先用），进一步放大误分类。

**方案 / 架构**: 只收紧匹配面，不动规则编号与阈值：
- `ledger` 改为只认台账写入：`sire_run\.py|journal\.log|run\.json|units\.json|blockers\.md|assumptions\.md|kb-hits\.md|stage-output|\.sire[\\/]current`。
- `archive` 去掉裸 `knowledge/global` 与 `archive[_-]?(db|root|result)`，只认动作：`sire_kb\.py (reindex|add|next-id|export-md|lint)|sire_vector_db\.py (index|migrate)|sire_db_backup|snapshot_db|SIRE_ARCHIVE_(ROOT|DB)`。
- 读知识库改判 `retrieve`（在 retrieve 模式里加 `knowledge[\\/]global`），语义归位而不是简单删掉。
- 事件 `detail` 上限 160→320，保证该规则可被复核。

**关键文件与接口**:
- `sire/workflow/shared/sire/scripts/sire_telemetry.py:31-41` — `PHASE_PATTERNS` 的 retrieve/archive/ledger 三项
- 同文件 `cmd_hook()` — `redact(json.dumps(tool_input…), 320)`
- `sire/.sire/runs/R20261013-074759/evidence/measure_phaseclass.py` — 新旧模式重放对比
- 同目录 `r7_phase_test.py` + `r7_phase_result.json` — 隔离库真实 hook 链路断言

**验证方法**: 用打补丁后的 `classify()` 重放 62 个历史任务（只读生产库）：`CLOSE_HEAVY` 命中 3→0、`FAST_SCOPE` 1→0，ledger 累计 1033s→716s、archive 368s→286s；full 任务收尾占比分布仍为 37/27/23/21/18/12%，即真实收尾工作量照样可见，规则没有空转。R7 在隔离遥测库走真实 `hook → summarize_task → analyze`：`stage-output` 记 ledger、`.sire/runs` 下的 Playwright 夹具不再记 ledger、读 `knowledge/global` 记 retrieve、`sire_kb.py reindex` 仍记 archive，5 条断言全 PASS。`sire_qoder.py selftest` 回归 PASS，`pending` 清空，`rsi-check` PASS。

**踩坑**: ① 写 A/B 度量脚本时不要用 `needle in line` 匹配客户端日志——本端 `sire-telemetry` 字样会先被模型自己写进代码文本里，导致假阳性结论；② 造遥测场景必须走 `summarize_task()`，直接往 `tasks` 插行不参与 `analyze`；③ 断言里截断 `detail[:60]` 会把文件名切掉而误判 FAIL；④ `evaluate` 的指标只认"越高越好"，写 `after<target` 会把提案打死。

**限制**: 阶段归属仍是"从工具文本猜"，不是角色声明，一次调用串多条命令时只能归一个阶段；彻底修需要钩子侧记录显式阶段标记或拆分批量命令，属更大改动，本轮未做。收紧后 CLOSE_HEAVY 在现存数据里 0 命中，若将来真实收尾开销变大，该规则仍会按 40% 阈值报出。
