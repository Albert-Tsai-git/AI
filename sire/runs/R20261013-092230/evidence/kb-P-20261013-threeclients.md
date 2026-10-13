**日期**: 2026-10-13
**项目**: SIRE 三端兼容性复核（`D:\sire\AI\AI\sire`）
**状态**: 已验证（取证脚本 scratch/probe_three_clients.py，run 见本次台账）
**关键词**: SIRE, 三端兼容, Codex, Claude, Qoder, 入口副本漂移, AGENTS.md, sire-reminder.txt, memory, hooks.json, config.toml 信任哈希, 别名 junction, COLLECTION_DEAD, parity, 链式钩子, feishu-hub

**需求场景 / 现象**: 要判断"Codex 与 Claude 是否仍与唯一源兼容"。实测关键词覆盖：唯一源 `global-contract.md` 命中 `Qoder / pending / COLLECTION_DEAD / sire_close / sire_qoder / 强制 / parity` **7/7**；`~/.codex/AGENTS.md`（3033 字节）**0/7**；`~/.claude/sire-reminder.txt`（2587 字节）**0/7**；`~/.qoder-cn/memory/sire-mandatory-workflow.md` 4/7。也就是说 v6.12–v6.17 的改动（三端表述、finish 强制核对 pending、COLLECTION_DEAD、sire_close 合并收尾、parity/role）只有写它们的人知道，另两个客户端的入口副本一字未提，而且**没有任何机制能发现这种漂移**——三份副本都是人手改写的摘要，连"## 简单任务快速通道"整段都不含（`section()` 取不到），无法做指纹比对。

**根因**:
1. 入口副本制度是"摘要 + 人工同步"：契约只说"修改本节时同步 Codex AGENTS.md 与 Claude reminder"，没有任何命令校验，副本与源之间没有可比较的结构（既非同一文件也非同一小节）。
2. 采集面本来就三端不齐：Codex 钩子三事件走 `~/.codex/skills/ai-dev-sire-workflow/scripts/sire_telemetry.py`（别名路径）在采；**Claude 的 Stop 与 UserPromptSubmit 都被 feishu-hub 占用**（`hook_prompt.py` / `hook_stop.py` + `Get-Content sire-reminder.txt`），对 `sire_telemetry` 的引用是 0，所以它的采集完全缺失（库里 17 条 claude 任务都是更早配置留下的）；Qoder 是我这次接上的四事件。
3. 别名即单点：Codex 钩子命令硬编码别名目录路径，junction 一旦失效采集会静默断掉；Claude 的 `settings.hooks` 无 PostToolUse；Codex 另有 `config.toml` 的 3 条 `[hooks.state...]` 信任哈希——**改 hooks.json 需重新信任**，否则钩子不生效且无提示。
4. 分档委派能力不齐：Claude 有 16 个 `~/.claude/agents/sire-*.md`（含 low/mid/high）；Qoder 没有子代理定义也没有 `model` 参数，只能靠 `sire_qoder.py role` 生成委派文本；Codex 侧未验证。
5. `COLLECTION_DEAD` 从配置反推"应采集客户端"，未配置的客户端隐形 → Claude 永远不报警，规则只能测"接过又掉"的，测不出"根本没接"。

**方案 / 建议架构**:
1. **入口副本改为同源生成 + 指纹校验**：新增 `scripts/sire_entry.py`，`render --client codex|claude|qoder` 从 `global-contract.md` 生成固定小节（含源 SHA 前 12 位与"由脚本生成，勿手改"标记），`check` 比对三端指纹并把不一致变成一条发现（等价于把 `parity` 从 Qoder 单端扩成三端）；这一步先做，否则后续任何机制改动都会继续静默漂移。
2. **Claude 采集用链式而非抢占**：在 feishu-hub 的 `hook_prompt.py` / `hook_stop.py` 内追加调用 `sire_telemetry.py hook --client claude`（或同事件加第二个条目，但 Qoder 实测同事件多条目后曾出现停采，链式更稳）；Codex 侧改 `hooks.json` 后必须提醒重新信任。
3. **钩子命令不再指向别名**：统一指向唯一源真实路径（或由 `sire_paths.py` 生成的启动器），`check` 同时验证"别名解析 == 唯一源""脚本文件存在""近 N 小时有心跳"三件事。
4. **显式客户端清单**：`sire_clients.json` 声明应当接入的客户端与必备事件，缺失=发现（`CLIENT_NOT_INSTALLED`），补上"根本没接"的盲区。
5. **分档文本同源**：把 low/mid/high 的委派约束也收进唯一源生成，Claude 用它生成 `agents/sire-*.md`、Qoder 用 `sire_qoder.py role` 消费，Codex 待验证后接入。

**关键文件与接口**:
- `~/.codex/AGENTS.md`、`~/.codex/hooks.json`、`~/.codex/config.toml`（3 条 hooks 信任项）
- `~/.claude/sire-reminder.txt`、`~/.claude/settings.json`（Stop/UserPromptSubmit → `D:\sire\AI\AI\feishu-hub\executors\claude\hook_*.py`）、`~/.claude/agents/sire-*.md`（16 个）
- `~/.qoder-cn/settings.json`（4 事件 + telemetry）、`~/.qoder-cn/memory/sire-mandatory-workflow.md`、`sire/workflow/shared/sire/agents/qoder/README.md`
- 三端别名均解析到 `D:\sire\AI\AI\sire\workflow\shared\sire`（junction 正常，工作流本体是真兼容的）

**验证方法**: `scratch/probe_three_clients.py`（输出 `three_clients.json`）逐端打印别名解析、钩子事件与命令、脚本是否存在、副本关键词覆盖；漂移比对用 `section()`+`sha256[:12]`，副本无该段即判"不可比对"，本身就是要修的缺陷。

**限制**: 本次为只读复核，未改任何机制；`sire_entry.py`、Claude 链式钩子、`sire_clients.json` 均属新的机制改动，需各自走 RSI 提案，Claude 那项还要用户授权（涉及 feishu-hub 现有集成）。另注：`plugin:computer-use` 现已在 Qoder 暴露并实测可用（`list_windows` 返回真实窗口列表），此前记录的"R10 本端不支持"已失效，需更正 README 与契约。
