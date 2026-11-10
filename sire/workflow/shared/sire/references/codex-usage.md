# Codex 用量、计时和额度来源

`scripts/sire_usage.py` 自动读取 `CODEX_THREAD_ID`（其次 `CODEX_SESSION_ID`）并绑定 `~/.codex/sessions` 下唯一的 `rollout-*.jsonl`。`CODEX_HOME` 可指定客户端目录。不取最近的其他会话，不回退到 Claude。

```powershell
python <SHARED_SKILL_DIR>/scripts/sire_usage.py --client codex --cwd <项目目录> --stage-start R1
python <SHARED_SKILL_DIR>/scripts/sire_usage.py --client codex --cwd <项目目录> --stage-end R1
python <SHARED_SKILL_DIR>/scripts/sire_usage.py --client codex --cwd <项目目录> --final
python <SHARED_SKILL_DIR>/scripts/sire_usage.py --client codex --file <rollout.jsonl> --session-id <会话ID> --turn-id <回合ID> --cwd <项目目录> --final
```

## 来源与计数

- `session_meta.id/cwd` 必须匹配指定会话和项目。无环境身份时必须给 `--session-id` 或 `--file`；显式文件必须有有效身份。来源缺失、多个匹配、压缩 `.jsonl.zst` 暂不支持时，如实拒绝。
- 默认回合取最近的 `task_started`，可用 `--turn-id` 指定。耗时来自该事件的真实时间戳；结束取统计时刻或已记录的 `task_complete`。追加提示不重置起点；思考、执行、暂停不作虚假拆分。
- 有有效 `response_id` 和 `usage` 的回合优先按响应明细去重，重复响应取最后一条；不再叠加 `token_count`。累计回退后仍按唯一响应继续统计，不等待超过旧高水位。始终注明“仅统计已落盘明细”，不保证完整覆盖回合。
- 只有累计事件的旧回合使用高水位差值；单次下降可能是重置或旧快照乱序，不能据此断言重置。低位连续增长单列“候选增量”，不混入确认总量，并报告无法恢复的区间；候选量可能与确认量重叠。没有基线时只计可核实单次量。输入、输出为真实 token；缓存和推理为子集，不重复相加。缺失与真实零分开，不套 Claude 权重，不把 token 当成账号额度扣减。
- 来源定位缓存按 sessions 根目录及会话隔离；事件缓存只保留元数据、回合、用量及额度字段，放在 `sire_paths.ledger_runs_dir()/usage-cache`，不缓存完整提示或回答。正常追加时只读新增完整行；截断、替换、锚点变化等会重建，半行留待下次读取；缓存失败回退源读取。`--no-cache` 可强制重新定位和流式重读。增量模式依赖正常追加语义，不能证明任意中部改写后再追加；严格取证应禁用缓存。缓存命中不扫描后续新增的同 ID 重复文件，禁用缓存可重新检查唯一性。未做性能实测，不宣称具体提速比例。

## 阶段与额度

- 阶段记录在 `sire_paths.ledger_runs_dir()` 下，按 client/session/turn/run/cwd 隔离；`--run-id` 可进一步隔离。指定 `SIRE_STAGE_LOG` 时仍筛选完整来源键。重复结束不重复记账。旧全局日志不导入，升级前阶段不参与新排名。
- 新回合的 `--stage-end` 不会结束上回合阶段，会报告当前回合没有开始记录。确需补记旧阶段可显式指定同一 `--turn-id` 和 `--run-id`，结束时刻仍是实际调用时刻，不能还原过去未记录的真实结束时间。
- 阶段用量按事件落盘时间归属，跨阶段请求不能精确拆分。统计只含当前 rollout；子代理有独立 rollout，不冒称整个代理树合计。排名比较输入加输出 token，缺用量阶段不参与用量排名。
- 5 小时额度只读 `rate_limits.primary.window_minutes == 300` 的有效快照，输出时间及 `used_percent`。开始前已有基线、结束后已有快照、reset 一致且无回退时，才报告账号全局读数变化。缺读数写“没有读数来源”，缺基线写“没有真实记录”。快照可能滞后、混入并行会话，不能归因本任务。不接受 Codex 的无来源手填 `--plan-mark/--plan-end`。
- Codex 暂不支持跨会话 `--days/--by-day`。`--session` 为当前文件已观测会话用量，`--turn`（默认）为选定回合，`--final` 同时输出耗时、用量、额度快照和阶段排名。

Claude 统计渲染及权重保留，可显式 `--client claude`；`--file` 可与 `--final/--turn` 配合。显式 `--file` 优先于 `CLAUDE_SESSION_ID`，只有显式 `--session-id` 仍需匹配文件名。Claude 只在当前项目查找；没有当前项目转录时，需传业务项目的 `--cwd` 或显式 `--file`，不回退全机最近会话。无身份时保留当前项目最新转录的旧行为。默认隔离目录内日志名为 `stages.jsonl`/`plan.jsonl`；自定义文件才加来源后缀。无需修改任何客户端配置、Claude 钩子或提醒文件。
