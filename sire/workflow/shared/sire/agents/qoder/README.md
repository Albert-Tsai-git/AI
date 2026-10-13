# Qoder 端 SIRE 适配（agents/qoder）

Qoder 与 Claude / Codex 一样只是客户端，不持有第二份工作流、知识库或数据库。本目录记录适配关系；全部实现代码在
`../../scripts/sire_qoder.py`（唯一可执行入口），规则正文仍只来自 `../../references/global-contract.md`。

## 与两个既有客户端的对照

| 能力 | Codex | Claude | Qoder |
| --- | --- | --- | --- |
| 薄入口 | `~/.codex/AGENTS.md` + skill 别名 | `~/.claude/skills/sire-global-workflow/` 别名 + `sire-reminder.txt` | 两件套：`~/.qoder-cn/skills/sire-global-workflow` junction → 唯一源（即时出现在技能列表），以及用户级 `~/.qoder-cn/AGENTS.md` 短指针（`entry-file` 子命令生成，含声明行要求与契约指纹，不复述规则正文） |
| 规则注入 | 手工副本，随 AGENTS.md 载入 | UserPromptSubmit 钩子 `Get-Content sire-reminder.txt` | **由用户级记忆 `~/.qoder-cn/memory/` 承担**（每轮必进上下文，声明行与判定要求在 `sire-mandatory-workflow.md`）。`remind` 钩子与 `~/.qoder-cn/AGENTS.md` 保留为可选：`resources/app.asar` 里没有 Claude 的 `additionalContext`/`hookSpecificOutput` 字段（各 0 次命中），实测钩子 stdout 不进上下文，因此不能当注入通道 |
| 阶段遥测 | UserPromptSubmit + PostToolUse + Stop | 同左（当前实际断流，见 P-20260931） | UserPromptSubmit + PostToolUse + PostToolUseFailure + Stop，`--client qoder` |
| 模型分级派工 | Agent `model` 参数 | `~/.claude/agents/sire-low|mid|high` | 无 `model` 参数、`create_chat_session` 也不接受模型 → 改成**角色档 + 隔离会话**：`sire_qoder.py role low\|mid\|high` 生成委派文（Explore / general-purpose / Plan），台账模型栏写 `qoder-role:<tier>`；真正的成本降级在本端做不到，不假称能做 |
| R10 原生操作 | computer-use（`mcp__cua_repl__js`） | 视插件 | `browser-use` MCP 已可用；`bin/qoder-cn-computer-use/QoderComputerUse.exe` 存在但未经工具暴露验证 → OS 级验收仍标 `BLOCKED-无法真实验证` |

## 安装与校验

```
python <SHARED_SKILL_DIR>/scripts/sire_qoder.py install            # settings 通道（默认）+ junction
python <SHARED_SKILL_DIR>/scripts/sire_qoder.py install --channel both   # 追加插件通道
python <SHARED_SKILL_DIR>/scripts/sire_qoder.py status              # 只读：注册状态与规则指纹
python <SHARED_SKILL_DIR>/scripts/sire_qoder.py selftest            # 隔离遥测库跑全链路，不碰生产库
python <SHARED_SKILL_DIR>/scripts/sire_qoder.py verify              # 只读：钩子是否真触发并有 client='qoder' 数据
python <SHARED_SKILL_DIR>/scripts/sire_qoder.py uninstall           # 只删自己写入的键，配置先备份
```

生效条件（实测）：**配置写入后最迟在下一个用户提示词就开始采集，不需要重启客户端**。本端实测从 0 增至 30 条事件并出现 `client='qoder'` 的回合，Stop→summarize→analyze 链路在跑；技能 junction 则是即时热加载，所以"入口出现在技能列表"不能当作"钩子在跑"的证据。
`verify` 的判据是遥测库里 `client='qoder'` 的事件与任务心跳（默认要求 10 分钟内有新增，`--within` 可调），不再把日志文本当证据——早先版本用字符串匹配日志，会把模型自己写进代码里的 `sire-telemetry` 字样误判成钩子触发（出现过假 PASS）。
待确认项：07:53–08:08 曾出现一段本端事件空窗，原因未定（不是"叠加条目"导致——remind 条目开启后事件仍在增长）；`--with-remind` 与遥测条目并存跨提示词的稳定性仍在 A/B。

## 事件与载荷

Qoder 支持的钩子事件全集（`resources/app.asar` 内 SDK 枚举，与日志实测一致）：
`PreToolUse`、`PostToolUse`、`PostToolUseFailure`、`UserPromptSubmit`、`SessionStart`、`SessionEnd`、`Stop`、`SubagentStart`、`SubagentStop`、`PreCompact`、`PostCompact`、`CwdChanged`、`InstructionsLoaded`；日志里另有客户端内部的 `QueryEnd`。
载荷字段与 Claude 同形（`hook_event_name`/`session_id`/`tool_name`/`tool_input`/`tool_response`），**但 Stop 载荷不带 `transcript_path`**（该字符串在 asar 里 0 次命中），所以转录一律由 `qoder_transcript()` 按会话 id 在 `~/.qoder-cn/projects/*/<session>.jsonl` 回退查找——这就是本端必须实现该回退的原因。
转录在 `~/.qoder-cn/projects/<cwd 转义>/<session>.jsonl`，因此 `last_assistant_text()` 的 Claude 分支可直接复用；
Stop 载荷未带转录路径时，`sire_telemetry.qoder_transcript()` 按会话 id 回退查找。

`--client` 白名单在 `sire_telemetry.py` 中是 `claude|codex|qoder`；遥测库仍是同一个
`DATA_DIR/sire_telemetry.sqlite3`，客户端 profile 目录不保留任何遥测副本。
