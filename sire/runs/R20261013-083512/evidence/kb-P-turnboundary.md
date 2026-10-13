**日期**: 2026-10-13
**项目**: SIRE v6.16 遥测回合边界兜底（`D:\sire\AI\AI\sire`）
**状态**: 已验证（RSI-20261013-TURNBOUNDARY → v6.16）
**关键词**: 遥测, summarize_task, UserPromptSubmit, Stop, 回合边界, prompt 事件缺失, 目标续跑, automation, Qoder, CLOSE_HEAVY 失效, v6.16

**需求场景 / 现象**: Qoder 端接入钩子后事件在涨（119 条），但 `tasks` 表只有 1 条且不是本会话的：本会话 117 条事件里有 3 个 `stop`、却只有 0 个 `prompt` 事件（全库 `prompt` 仅 1 条）。结果是本端所有回合都进不了 `analyze`，`CLOSE_HEAVY`/`PHASE_OUTLIER`/`FAST_SLOW` 这些按回合判定的规则对这一端完全失效——表面上"心跳正常"，实际上分析层空转。

**根因**: `sire_telemetry.summarize_task()` 把 UserPromptSubmit 当成回合起点硬依赖：
```
prompts = [r for r in rows if r["event"] == "prompt"]
if not prompts:
    return          # ← 没有 prompt 事件就整窗丢弃
start = prompts[0]["ts"]
```
而自动化/续跑型提示（目标系统注入的 continue、飞书转发、定时任务）不触发 `UserPromptSubmit` 钩子，只有 `Stop`。所以这类会话只有终点没有起点。

**方案 / 架构**: 回合边界改以 `Stop` 为准，`UserPromptSubmit` 降为可选起点——无 prompt 事件时取窗口内最早的非 prompt 事件作为起点、`prompt` 字段留空，`mode` 仍由 Stop 读最终回复判定；有 prompt 时行为完全不变（零回归）。契约 §静默分析同步写明这条口径，防止以后再把它当硬前提。

**关键文件与接口**:
- `sire/workflow/shared/sire/scripts/sire_telemetry.py` — `summarize_task()` 起点选择与 INSERT 的 prompt 取值
- `sire/workflow/shared/sire/references/global-contract.md` — §RSI 自动发现 第 2 条

**验证方法**: 从**生产库**导出本端全部事件灌进隔离遥测库（`SIRE_TELEMETRY_DB`）重放真实 `summarize_task()`：2 个会话 4 个 stop → 修复前 0 个任务，修复后 4 个任务，且阶段分布合理，例如某回合 `总1519s / 工具40 / 失败3`（rules 76s、retrieve 169s、execute 1031s、rsi 127s、archive 84s、ledger 12s、reply 22s）。`ast` 语法校验通过，`rsi-check` PASS，`sire_qoder.py parity` rc=0。

**踩坑 / 注意**: ① 验证"是否真的在采集"不能只看 events 数量，必须看 `tasks` 是否在增长——events 有、tasks 无就是分析层空转；② 重放验证要用生产真实事件灌隔离库，别手造数据（手造容易漏掉 prompt 缺失这种触发条件）；③ 我第一版验证脚本把事件按原 session 插入、却用另一个 session id 调 `summarize_task`，得到 0 任务是测试写错而非代码错——先怀疑量具再怀疑被测物。

**限制**: 兜底起点的 `prompt` 字段为空，`report` 里这类回合看不到用户原话；`mode` 仍依赖最终回复里的快速通道标记，没有标记的自动化回合依旧是 `unknown`（已知项，另行处理）。
