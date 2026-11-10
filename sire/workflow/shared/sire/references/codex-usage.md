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
- 支持 `token_usage_record.thread_token_usage` 和 `event_msg/token_count.info.total_token_usage`，统一累计高水位计算差值。同一累计值不重复相加。首个快照只计入可证明的单次量；缺基线、累计回退会报告不完整，回退保留原高水位。
- 只有单次明细的旧转录按 `response_id` 去重；存在累计序列时不叠加没有累计锚点的明细，并报告限制。输入、输出为真实 token；缓存和推理为子集，不重复相加。缺失与真实零分开，不套 Claude 权重，不把 token 当成账号额度扣减。

## 阶段与额度

- 阶段记录在 `sire_paths.ledger_runs_dir()` 下，按 client/session/turn/run/cwd 隔离；`--run-id` 可进一步隔离。指定 `SIRE_STAGE_LOG` 时仍筛选完整来源键。重复结束不重复记账。旧全局日志不导入，升级前阶段不参与新排名。
- 阶段用量按事件落盘时间归属，跨阶段请求不能精确拆分。统计只含当前 rollout；子代理有独立 rollout，不冒称整个代理树合计。排名比较输入加输出 token，缺用量阶段不参与用量排名。
- 5 小时额度只读 `rate_limits.primary.window_minutes == 300` 的有效快照，输出时间及 `used_percent`。开始前已有基线、结束后已有快照、reset 一致且无回退时，才报告账号全局读数变化。缺读数写“没有读数来源”，缺基线写“没有真实记录”。快照可能滞后、混入并行会话，不能归因本任务。不接受 Codex 的无来源手填 `--plan-mark/--plan-end`。
- Codex 暂不支持跨会话 `--days/--by-day`。`--session` 为当前文件已观测会话用量，`--turn`（默认）为选定回合，`--final` 同时输出耗时、用量、额度快照和阶段排名。

Claude 统计渲染及权重保留，可显式 `--client claude`；`--file` 可与 `--final/--turn` 配合。Claude 只在当前项目查找，支持 `--session-id`/`CLAUDE_SESSION_ID`；无身份时保留当前项目最新转录的旧行为，并行会话建议显式绑定。日志也按会话和回合隔离，不读取旧全局日志。无需修改任何客户端配置、Claude 钩子或提醒文件。
