

### E-008: SIRE 单一来源收敛与 RSI 双库写入

**日期**: 2026-09-25
**项目**: SIRE v6 Claude/Codex 共享工作流
**状态**: 已验证（run R20260925-112329，RSI-20260925-SYNC → v6.3）
**关键词**: SIRE, 单一来源, governor, ai-workflow-governor, Codex skill, 目录联接, RSI, sire_rsi, 归档库, SIRE_ARCHIVE_ROOT, SIRE_ARCHIVE_DB, snapshot_db, RSI 丢失保护, fail-closed, WAL

## 场景
复查"Claude/Codex 共用一份 SIRE"时发现：governor 有三份副本（support/、shared/sire/references/governor、Codex 独立 skill）；RSI 只写仓库库而收尾快照从归档库重建仓库库，RSI 记录会丢失；归档库为 WAL 模式时快照工具报"source -wal changed"。

## 做法
- governor 只保留 `sire/workflow/support/ai-workflow-governor/`（sire_run/sire_bundle 引用的路径），删除 shared 下副本并清理 source-manifest；Codex 独立 governor 移到 `~/.codex/skills-backup/`，Codex 只加载 SIRE 联接。
- `sire_rsi.py` 写命令先写归档库再写仓库库（`SIRE_ARCHIVE_ROOT`/`SIRE_ARCHIVE_DB`/`--archive-db`，解析不到则拒绝，测试用 `--repo-only`）；写前两库一致性预检，禁止重复 propose；`status` 只读。
- `snapshot_db.py` 发布前比较 RSI 三表键（脱敏对齐），仓库库有而归档库无、或目标库无法校验时拒绝发布。
- 快照前若归档库是 WAL 模式，先 checkpoint 并切 DELETE 日志模式。

## 验证
R4 两轮、R6A/R6C PASS、R6B 两轮 PASS、R7 T1–T10 在最终版 PASS；两库 v6.3 ACTIVE 一致。

## 限制
activate 前置检查在锁外、两库锁分别获取（LOW）；执行 RSI 写命令需在 shell 设置 SIRE_ARCHIVE_ROOT（本机为归档库所在目录）。


### E-009: Claude×Codex 同机本地通讯与协作机制（msg.py 信箱/进度/锁 + 路径所有权 + 接口文档）

**日期**: 2026-09-27
**项目**: MetalMax 同人（Unity 6）/ D:\code\GAME（GitHub Albert-Tsai-git/MetalMax）
**关键词**: Claude Codex 本地通讯, 双 AI 协作, 消息信箱, msg.py, comms, messages.jsonl, 进度同步, status.json, 资源锁, unity.lock, 接收到 Codex 消息, 路径所有权, ownership.py, commit-msg 钩子, INTERFACE.md, 工作副本, git worktree, multi-agent local messaging

**需求场景 / 现象**: 同一台 Windows 机器上 Claude Code 与 Codex 并行开发同一个 Unity 项目（Claude 管逻辑机制，Codex 管文案/美术/UI/模型/动效）。需要：互相传话与交接、双方进度让用户可查、避免两边同时打开同一个 Unity 工程、避免改到对方文件、共同约定的字段/ID/路径有单一可信来源；且用户要能在对话里看到双方收到了什么。

**方案 / 架构**: 纯本地文件通讯，不走网络/服务器；分五条通道：
1. 消息：`comms/messages.jsonl` 追加式信箱（编号、时间、发件人、收件人、类型、内容、re）。类型 info/request/question/reply/handoff；request/question 必须用 reply --re 回复。已读记录 `read_Claude.json` / `read_Codex.json`。inbox 同时列出“我发出但对方未回复”的 request/question。
2. 进度：`comms/status.json`，每方一行“当前任务 | 进度 | 下一步”，`msg.py status` 查看双方与锁。
3. 资源锁：`comms/unity.lock`，lock/unlock/locks；用户试玩时由 Claude 以 User 身份代持锁。锁是约定，不强制。
4. 代码/素材交付：同一本地仓库 main；提交信息必须以 [Claude]/[Codex]/[User] 开头（.githooks/commit-msg），`tools/ownership.py` 定义每条路径归属，提交钩子拒绝越界文件。Claude 在 git worktree（D:\code\GAME-claude，分支 claude/dev）开发，`tools/integrate.py` rebase→离线编译检查→快进合并→推送，避免对方 Unity 编译到半成品。
5. 约定：`docs/INTERFACE.md` 只放双方需共同遵守的字段/ID/路径/事件，每条 Claude/Codex 两列都 ✅ 才生效；Codex 不直接改，由 Claude 按其回复回填。
展示规则（用户要求）：收到对方消息后必须在与用户的对话中逐条写【接收到 Codex 消息：#编号 要点】（Codex 侧写【接收到 Claude 消息：…】），并说明是否已执行、结果、未执行原因。
被否决：直接共享一个分支（对方 Unity 会编译到半成品）；用网络服务（没必要，且两边都在本机）。

**关键文件与接口**:
- `tools/msg.py` — send/inbox/ack/log/status/lock/unlock/locks
- `comms/`（.gitignore 忽略）— messages.jsonl、read_*.json、status.json、unity.lock
- `tools/ownership.py`、`.githooks/commit-msg`（core.hooksPath=.githooks）— 路径所有权与提交前缀
- `tools/integrate.py`、`tools/compile_check.py`（用 Unity 自带 dotnet+Roslyn 离线编译）
- `tools/playtest.sh` — 在 worktree 的 Unity 工程跑 PlayMode 实机测试，不占主工程锁
- `docs/COLLABORATION.md` §3 通讯规则、`docs/INTERFACE.md` 对接条款

**实施步骤**:
1. 新建 comms/ 并加入 .gitignore；写 msg.py（JSONL 追加 + 已读表 + 状态 + 锁）。
2. COLLABORATION.md 写明：开始任务/提交前/结束时查 inbox 并 ack；阶段变化更新 status；用 Unity 前 lock。
3. ownership.py + commit-msg 钩子；Claude 用 worktree + integrate.py。
4. 等待对方时后台循环：`until python tools/msg.py inbox Claude | grep -q "Codex→Claude"; do sleep 30; done`（先 ack all，否则旧未读会立刻命中）。

**验证方法**: 双方互发 request/reply 编号连续、inbox 能显示待回复项；status 显示双方进度；锁冲突时一方等待；越界提交被钩子拒绝；本会话中 #37~#64 往返均正常，Codex 编译错误、地形/UI 缺陷经消息往返修复。

**踩坑**:
- 后台等待前没 ack 旧消息，循环立即返回。
- 锁显示空闲但另一方仍有 Unity 进程（在不同工程），需说明 worktree 工程与主工程不冲突。
- Codex 本机无 Unity 时提交的二进制 TerrainData 无法被 Unity 读取——素材须在 Unity 中生成，接收方必须实机验证后再推送。
- 只有本机有效：跨机器/云端需改用 GitHub 等外部通道；无推送通知，只能轮询。

**状态**: 已完成（运行中）

### E-010: SIRE 规则同步直接加载共享源并补齐客户端薄入口

**日期**: 2026-10-12
**项目**: SIRE v6.11 规则同步
**状态**: 已验证规则入口与实际脚本；真实客户端自动遥测事件触发未实测
**关键词**: SIRE, Codex, Claude, v6.11, 快速通道, 薄入口, 单一来源, telemetry, RSI, 数据库不进Git

**方案**: 两客户端 skill 别名指向同一 `workflow/shared/sire`，无需复制或重装工作流。同步快速通道副本时同时补齐目录/环境变量查看、新建空文件、概念用法问答、兜底判定、目标不明或不存在时退出快速通道；Codex AGENTS 与 Claude reminder 的中文副本保持同文。共享工作库不进 Git，恢复步骤由 `data/DATABASE-RECORD.md` 定义。v6.11 新增自动耗时遥测、Stop 后静默分析及 R9 按 pending 处理一条 RSI 发现。

**验证**: 从两个别名实际读取文件并调用路径解析器，物理源、规则 SHA-256、知识与数据库路径一致；实际向量正常查询命中 ID 相同，无命中边界及查询前后数据库哈希验证通过。两个实际遥测脚本入口用隔离库接收 prompt/tool/stop，均产生三事件和一条 full 任务；畸形 JSON 静默返回且计数不变。当前 Codex 对话收到更新后的入口指令。R9 pending 输出为空，rsi-check PASS。

**限制**: 钩子配置和脚本成功不能证明真实客户端会自动触发；该路径单独标记 `BLOCKED-无法真实验证`。历史知识中的 SQLite 入 Git 建议已被当前合同取代。此次没有修改共享机制源，因此不新建 RSI 提案。

**证据**: `runs/R20261012-rule-sync/`。同步任务应保留预存脏状态，只提交自身规则/知识/证据，不提交数据库或客户端个人配置。


### E-011: Qoder 端 SIRE 完全兼容适配：junction 入口 + remind 实时注入 + 四事件遥测

**日期**: 2026-10-13
**项目**: SIRE v6.13 Qoder 端完全兼容适配（`D:\sire\AI\AI\sire`）
**状态**: 已验证（run R20261013-074759，RSI-20261013-QODERADAPTER → v6.13；客户端钩子真实触发待重启后用 verify 补测）
**关键词**: SIRE, Qoder, 客户端适配, 钩子, hooks.json, settings.json, installed_plugins_v2.json, junction, sire_qoder.py, sire_telemetry, --client qoder, PostToolUseFailure, transcript, 薄入口, v6.13

**场景**: 要求 Qoder 端与 Codex/Claude 一样自动执行 SIRE：自动入口注入、自动阶段遥测、可校验可回退，且不得在客户端目录留第二份工作流/知识库/数据库。

**做法**:
1. 入口用 junction，不用副本：`mklink /J %USERPROFILE%\.qoder-cn\skills\sire-global-workflow <唯一源目录>`（与 Claude 的 `~/.claude/skills/sire-global-workflow` 同构）。新建 junction 后 Qoder 技能列表**即时**出现该 skill，无需重启。
2. 规则注入不留手工副本：UserPromptSubmit 钩子调用 `sire_qoder.py remind`，它现场从 `global-contract.md` 抽取"## 简单任务快速通道"整段并附 SHA-256 前 12 位指纹打印到 stdout → 副本永远不会与源脱节（Claude/Codex 仍是手工副本，改契约时须人工同步）。
3. 遥测直接复用 Codex 的通道：`sire_telemetry.py hook --client qoder`，事件取 `UserPromptSubmit`/`PostToolUse`/`PostToolUseFailure`/`Stop`；载荷字段与 Claude 同形（`hook_event_name`/`session_id`/`tool_name`/`tool_input`/`tool_response`/`transcript_path`），转录 `~/.qoder-cn/projects/<cwd 转义>/<session>.jsonl` 也是 Claude 形（`type=assistant` + `message.content[].text`），所以 `last_assistant_text()` 无需新分支；只补了 `qoder_transcript()` 在 Stop 载荷不带路径时按 `session_id` 回退查找。
4. `PostToolUseFailure` 单独接：直接记 `ok=0`，比 `tool_failed()` 猜 `tool_response` 字段可靠（后者在 Codex 侧 421 个工具事件里只识别出 2 次失败）。
5. 写客户端配置前先备份、只增自己的键、可精确回退：`sire_qoder.py install/uninstall/status/verify/selftest/link`，`_is_ours()` 用标记串过滤，绝不覆盖别的客户端配置。

**关键文件与接口**:
- `sire/workflow/shared/sire/scripts/sire_qoder.py` — install/status/verify/uninstall/link/remind/selftest
- `sire/workflow/shared/sire/scripts/sire_telemetry.py` — `--client` 加 `qoder`、`qoder_transcript()`、`PostToolUseFailure`
- `sire/workflow/shared/sire/agents/qoder/README.md` — 三端能力对照表与安装命令
- `sire_supervisor.py REQUIRED_ARCHIVE_ENTRIES` — 缺 `scripts/sire_qoder.py` 或 `agents/qoder/README.md` 即 `package_omission`

**验证方法**: `sire_qoder.py selftest` 用隔离遥测库（`SIRE_TELEMETRY_DB`）合成 Qoder 载荷跑真实链路，断言全 PASS：7 事件入库、`mode=full` 由转录识别、`PostToolUseFailure` 记为 1 次失败、`subagent` 独立成阶段、rules/retrieve/archive 归位。`status` 显示四事件 + 入口注入 + junction 均 true，快速通道指纹 `57de3e652f6f`。rsi-check PASS，v6.13 两库 ACTIVE。

**踩坑**: ① Qoder 的钩子清单在会话启动时加载，`install` 后当前会话不会触发，必须重启后用 `verify` 复核（`verify` 返回 PENDING/PASS 会明确区分）；② 技能目录却会热加载，所以"入口已生效"不能当作"钩子已生效"的证据；③ `~/.qoder-cn/settings.json` 原本只有 `enabledPlugins` 一个键，写入 `hooks` 后需保留原键（本工具用读-合并-写回并先备份）；④ 插件通道（`--channel plugin`，写 `installed_plugins_v2.json` + `cache/local/sire/<ver>`）已实现但未作为默认，因为 settings 通道已能覆盖，且注册表被客户端更新覆盖的风险更高。

**补充（同日实测两个缺陷）**: ① `last_assistant_text()` 原来只读转录尾部 256KB，而 Qoder 一个长回合的尾部全是 `tool_use`/`tool_result` 块，最终回复的 `快速通道：…` 标记在更前面 → 本端任务全部被 `detect_mode()` 判成 `unknown`（实测命中）。改成先试 256KB、取不到就扫全文（`_scan_assistant()` 抽成函数），实测对本会话真实转录取到 1730 字文本并正确判为 `full`。② 适配器自己的 `verify` 用 `needle in line` 匹配客户端日志，会把我写进代码里的 `sire-telemetry` 字样当成钩子触发证据而报假 PASS；改成只匹配 `hook.(started|finished) hook_name="...sire-telemetry"`，并同时以遥测库 `client='qoder'` 的事件/任务增长为准。

**限制（已更新）**: 真实客户端采集已确认在跑——本端事件 0→30 条并产生 `client='qoder'` 的回合，且**不需要重启客户端**，配置写入后最迟下一个用户提示词起生效；`--with-remind` 入口注入与遥测条目并存的跨提示词稳定性仍在 A/B。`Agent` 工具无 `model` 参数 → 模型分级在本端只能记"主控直接执行"；`QoderComputerUse.exe` 存在但未验证工具暴露，OS 级 R7/R10 仍标 `BLOCKED-无法真实验证`。


### E-012: Qoder 钩子生效时机与可复核判据：下一个提示词即采集、以遥测心跳为准、junction 热加载不等于钩子在跑

**日期**: 2026-10-13
**项目**: SIRE v6.13/v6.14 Qoder 端接入（`D:\sire\AI\AI\sire`）
**状态**: 已验证（run R20261013-081448，本端实测采集在跑）
**关键词**: Qoder, 钩子生效时机, 下一个提示词, 无需重启, hooks 条目写法, verify 心跳, junction 热加载, sire_qoder.py, client=qoder, 假 PASS, v6.14

**场景**: 把 SIRE 遥测与入口接到 Qoder 后，要判断"配置写进去了"与"真的在采集"之间的差别，并给出可复核的判据。

**做法**:
1. 判据只认遥测心跳：`sire_qoder.py verify` 检查生产遥测库里 `client='qoder'` 的 `events`/`tasks` 是否在增长（默认要求 10 分钟内有心跳，`--within` 可调）。**不要**用日志字符串匹配判断钩子是否触发。
2. 生效时机：配置写入后**不需要重启客户端**，最迟在下一个用户提示词就开始采集。实测序列：install 前本端 0 条 → 下一次提示词回合内 30 条事件、并生成 1 条 `client='qoder'` 任务（Stop→summarize_task→analyze 全链路在跑）。中途出现过 07:53–08:08 的本端事件空窗，原因未定（不要归因于"条目叠加"——remind 条目开启后事件仍在增长），如实记为待观测。
3. 写法约束（观测上有效，但因果未证实）：`hooks` 每个事件只放一个条目，命令里每个 token 都加引号。
4. 入口与钩子是两套加载时机：技能 junction（`~/.qoder-cn/skills/sire-global-workflow` → 唯一源）**即时热加载**，钩子则要到下一个提示词。所以"技能列表里出现了 SIRE"绝不能当作"钩子在采"。
5. 入口注入 `remind` 与遥测条目并存可能相互影响，改为默认关闭、`--with-remind` 显式开启，跨提示词稳定性用 A/B 观察后再定默认值。

**关键文件与接口**:
- `sire/workflow/shared/sire/scripts/sire_qoder.py` — `cmd_verify()`（心跳判据 + `--within`）、`_shell()`、`_settings_hooks(with_remind)`、`cmd_link()`
- `sire/workflow/shared/sire/agents/qoder/README.md` — 三端能力对照与踩坑实录
- `~/.qoder-cn/settings.json` 的 `hooks` 键；`~/.qoder-cn/logs/runs/*/qodercli.log` 的 `hook_event_name` 事件枚举

**验证方法**: 同一台机器连续观测：`status` 四事件 true + alias 指向唯一源；`verify` 由 `PASS`（心跳）判定；`selftest` 在隔离库（`SIRE_TELEMETRY_DB`）跑真实 hook→analyze 链路，与生产库互不干扰；`uninstall` 只删自有条目。

**踩坑**: ① `verify` 早期用 `needle in line` 匹配客户端日志，而我自己写的代码文本里就有 `sire-telemetry`，结果报了**假 PASS**；日志证据必须限定为 `hook.started/finished hook_name="…"` 行，且以数据库为准。② 手工把钩子载荷灌进**生产**遥测库会污染统计（本次已清理 `session in ('handcheck','qoder-selftest')` 的 4 事件/1 任务）；自测一律走隔离库。③ `sire_kb.py search --run` 传相对/裸 run id 时回执可能不落进目标 run 目录，G0 会说"没有检索回执"，用完整 run 目录路径重试。

**限制**: 空窗期成因与 remind 并存性未证实；OS 级 computer-use 与模型分级派工仍是本端能力缺口（见 `agents/qoder/README.md` 对照表）。


### E-013: 把 RSI 闭环写进代码：finish 强制核对 pending、analyze 自检采集断流、Qoder 加用户级 AGENTS.md 入口

**日期**: 2026-10-13
**项目**: SIRE v6.15 RSI 闭环强制化（`D:\sire\AI\AI\sire`）
**状态**: 已验证（run R20261013-081448 续，RSI-20261013-RSILOOP → v6.15）
**关键词**: SIRE, RSI, 自动优化, pending, finish 门禁, sire_run.py, telemetry_pending_gate, pending-check.json, COLLECTION_DEAD, expected_clients, SIRE_CLIENT_CONFIGS, 采集断流, Qoder AGENTS.md, entry-file, v6.15

**场景**: 自审发现 RSI 的两处结构性空转：① "R9 收尾必须处理 pending"只写在 SKILL.md / global-contract.md / supervisor.md 的文字里，任何脚本都不检查，历史上除一次人工执行外从未跑过；② 采集面坏了没人知道——claude 末次事件距当时已 21 小时，Codex/Qoder 都在 1 分钟内心跳，机制对此完全无感。目标是让闭环不依赖模型自觉。

**根因**: 规则只声明"应当做什么"，没有落进收尾路径的判定；而"哪个客户端应当有心跳"这个事实此前只存在于人脑里，代码里没有可推导的来源。

**方案 / 架构**:
1. `sire_run.py finish` 在收尾链里加 `telemetry_pending_gate(rd, note)`：调用真实 `sire_telemetry.py pending --json`，有未处理发现即 `BLOCKED`；把 `checked_at / pending / handoff_note / verdict` 写进 run 目录 `pending-check.json` 留痕。唯一的绕行是**显式**的 `--pending-note "原因"`（verdict=HANDED_OFF），与契约里"需用户决定就 resolve --ignore"同构——可以移交，但不能无声跳过。
2. `sire_telemetry.py` 新增 `COLLECTION_DEAD` 规则（need=1，命中即 PROPOSED）与 `check_clients()`：从客户端配置反推"应在采的 client 名单"（`~/.codex/hooks.json`、`~/.claude/settings.json`、`~/.claude/settings.local.json`、`~/.qoder-cn/settings.json` 里出现的 `--client <name>`；可用 `SIRE_CLIENT_CONFIGS` 用 pathsep 覆盖，便于测试与自定义安装），**只对"曾经采过、现在哑了"的客户端报警**（`last is None` 不报，避免新装客户端误报），30 分钟内不重复计数，防止每次 analyze 刷命中。
3. Qoder 再补一个常驻入口：`sire_qoder.py entry-file` 生成/更新 `~/.qoder-cn/AGENTS.md` 短指针（唯一源路径 + 声明行要求 + 快速通道规则指纹，不复述规则正文），`install` 自动写、`uninstall` 只删带 `<!-- sire-qoder-entry -->` 标记的文件；这样即使 UserPromptSubmit 的 stdout 不被注入上下文，也还有一个和 Codex 用户级 AGENTS.md 同构的入口。

**关键文件与接口**:
- `sire/workflow/shared/sire/scripts/sire_run.py` — `telemetry_pending_gate()`，`finish --pending-note`
- `sire/workflow/shared/sire/scripts/sire_telemetry.py` — `CLIENT_CONFIGS` / `expected_clients()` / `check_clients()` / `analyze --stale-hours`（默认 12）
- `sire/workflow/shared/sire/scripts/sire_qoder.py` — `entry_text()` / `cmd_entry_file()` / `status.entry_file`
- `sire/.sire/runs/R20261013-081448/evidence/r7_enforce_test.py` + `r7_enforce_result.json` — 真实 CLI 三态测试

**验证方法**: 隔离遥测库 + 临时项目目录跑真实 CLI：A 组 4 条断言全 PASS（36 小时无事件的 claude → `COLLECTION_DEAD:claude` 直接 PROPOSED 且进 pending；有 1 分钟心跳的 qoder 不误报；连跑两次 analyze 命中仍为 1）；B/C/D 组证明收尾门禁 `rc=1 BLOCKED → resolve 后 rc=0 → --pending-note 移交 rc=0 且 verdict=HANDED_OFF`。生产库现状：`pending` 空、`rsi-check` PASS、v6.15 ACTIVE、Qoder 心跳正常。

**踩坑**: ① 测试里判定"钩子是否触发"绝不能用日志字符串包含匹配——我自己写的代码文本里就有 `sire-telemetry`，会造出假 PASS（上一轮真踩过）；② `findings` 表列顺序是 `(finding_id,rule,status,hits,first_seen,last_seen,evidence,suggestion,proposal_id,resolved_at,note)`，手写 INSERT 要正好 11 个值；③ `sire_kb.py search --run` 的 run 参数要用完整 run 目录路径，裸 run id 会让 G0 说"没有检索回执"；④ 对已 ACTIVE 的提案再跑 `evaluate` 会按新指标重算状态，含"越低越好"写法会把它打成 `EVALUATED_FAIL`，从而失去门禁放行资格——指标一律写成上升率。

**关键取证方法（可复用）**: 要判断某个客户端支不支持某个钩子事件或注入能力，别猜也别只看文档——直接 grep 它的安装包。Qoder 的逻辑在 `D:\software\Qoder CN\resources\app.asar`（141MB，纯文本可搜）；进程路径先用 `Get-Process | Where-Object ProcessName -match qoder | Select-Object -ExpandProperty Path` 拿到。结果：SDK 事件枚举为 `PreToolUse/PostToolUse/PostToolUseFailure/UserPromptSubmit/SessionStart/SessionEnd/Stop/SubagentStart/SubagentStop/PreCompact/PostCompact/CwdChanged/InstructionsLoaded`；而 `additionalContext`、`hookSpecificOutput`、`transcript_path`、`AGENTS.md`、`QODER.md` 全部 0 次命中——据此判定 Qoder 不走 Claude 的钩子注入协议、Stop 不给转录路径、用户级 AGENTS.md 不是它的入口，规则注入只能用每轮必进上下文的 `~/.qoder-cn/memory/`。

**限制**: `COLLECTION_DEAD` 只在客户端**曾采过**之后才报警，全新装但一直没心跳的客户端要靠 `sire_qoder.py verify`；`expected_clients()` 依赖配置文件里出现 `--client` 字样，Claude 目前根本没配 SIRE 钩子，因此不会报 claude——补装 Claude 钩子涉及它已被 feishu-hub 占用的 Stop 钩子，需用户授权，未擅自改。`~/.qoder-cn/AGENTS.md` 已确认不是 Qoder 的注入通道（asar 无该文件名），保留为无害冗余；`remind` 钩子降为 `--with-remind` 可选。


### E-014: SIRE 收尾合并命令 sire_close.py：一条调用跑完归档+索引+阶段+finish+台账复制，不绕过 pending 门禁

**日期**: 2026-10-13
**项目**: SIRE v6.17 收尾合并命令（`D:\sire\AI\AI\sire`）
**状态**: 已验证（RSI-20261013-CLOSESCRIPT → v6.17）
**关键词**: SIRE, 收尾, R9, sire_close.py, close, 合并命令, 效率, CLOSE_HEAVY, stages.json, 台账复制, pending 门禁, v6.17

**场景**: 遥测显示一个回合计 212s，其中收尾类动作占 101s（48%），`CLOSE_HEAVY` 规则的建议就是"把多步手工收尾合并成脚本命令"。手工收尾由 `sire_kb.py add` + `reindex` + `sire_vector_db.py index` + 11 次 `stage-output` + `gate G0` + `finish` + 台账目录复制组成，十余次 python 冷启动。

**做法**: 新增 `scripts/sire_close.py`，一条命令跑完整条收尾链，顺序固定、任一步非零即中止：

```
python <SHARED_SKILL_DIR>/scripts/sire_close.py close --root <项目根>
    [--run RUN_ID] [--stages stages.json]
    [--records E-013,P-20260934 | --no-archive "原因"]
    [--kb-add "P|标题|正文文件"] [--migration "迁移文档行"]
    [--archive-root D:/sire] [--skip-reindex] [--dry-run]
```

`stages.json` 是阶段清单：`[{"stage":"R5","status":"DONE","artifact":"…","note":"…"}, {"stage":"R10","status":"SKIPPED","reason":"…"}]`；`--dry-run` 只打印计划。

**关键约束**: 脚本内部仍调用 `sire_run.py finish`，所以 **pending 强制门禁、G6 记录校验、迁移文档同步检查一个都没绕过**；`--archive-root` 用于给 RSI/归档写命令注入 `SIRE_ARCHIVE_ROOT/SIRE_ARCHIVE_DB`；最后把 `.sire/runs/<RUN>` 复制到 `runs/<RUN>` 完成台账归档（先删旧副本，保持幂等）。

**验证方法**: 真实收尾 run R20261013-084551 一次调用 29.7s 完成：11 条 stage 全 ok、finish 通过、`pending-check.json` verdict=PASS、台账落到 `sire/runs/R20261013-084551`；`--dry-run` 输出与真实执行一致。`sire_close.py` 已加入 `sire_supervisor.REQUIRED_ARCHIVE_ENTRIES`（缺失即 `package_omission`），SKILL.md 与 global-contract §RSI 第 3 条写明用法。

**踩坑**: ① `--records` 与 `--no-archive` 互斥，且记录必须晚于 run 创建（`kb_baseline` 会拒收"任务开始前就存在"的记录充数）；② `gate G0` 不在 close 链路里——检索回执必须在 init 之后、stage 之前用 `sire_kb.py search --run <完整 run 目录路径>` 生成，否则 G0 会说没有回执；③ 迁移文档追加要先判重，否则重复执行会写两行。

**限制**: 只覆盖 R9 收尾链，R0–R8 的拆解与执行仍需模型判断；`--stages` 清单得自己写（也可以用 `--dry-run` 先验）。


### E-015: git-bash 下 git show ref:path 被 MSYS 转换毁参数，需 MSYS_NO_PATHCONV

**日期**: 2026-10-13
**项目**: Windows + Git Bash（Qoder / Claude / Codex 三端通用）
**关键词**: MSYS_NO_PATHCONV, git show, ref:path, git-bash, 跨分支读文件, fatal ambiguous argument

**需求场景 / 现象**: 在不 checkout、不动工作区的前提下读另一个分支（`git show "origin/<branch>:<path>"`）的文件内容。git-bash 下报 `fatal: ambiguous argument 'origin\feature\x;.gitlab-ci.yml': unknown revision or path not in the working tree`。**同一条命令对 `electron-builder.yml` 能过、对 `.gitlab-ci.yml` 就挂**（前导点号触发转换），极易误判成"分支或文件不存在"——那是一类假阴性。

**根因**: MSYS2 的参数转换会把含 `:` 的参数当路径列表处理（`:`→`;`、`/`→`\`），`ref:path` 这种 Git 语法被毁成非法 revision。

**方案 / 架构**: 用 `MSYS_NO_PATHCONV=1` 关掉参数转换来跨分支取文件，而不是 checkout 目标分支或改用 `git cat-file --textconv` 之类的绕行——checkout 会动工作区，绕行要多记一套语法。取回的内容再 `cmp` 与分支原文对账。

**实施步骤**:
1. 每个 shell 会话开头 `export MSYS_NO_PATHCONV=1`（对 `git show`/`git grep <ref>`/`git cat-file` 全生效）。
2. `git show "origin/<branch>:<path>" > 本地副本`，再用 `git ls-tree -r --name-only <ref>` 确认路径真的存在。
3. 需要判"某结论是不是这个分支特有"时，配合 `git diff --numstat origin/develop <ref> -- <path>`。

**验证方法**: 本次实跑，去掉该变量 3 次全 fatal，加上后一次成功；随后用 `cmp` 把取回的副本与分支原文逐字节对比确认取数没错。

**状态**: 已完成（实测）


### E-016: feishu-hub 接入 Qoder 执行器与桌面 Hook：协议落点、CLI 缺口与真机待验项

**日期**: 2026-10-13
**项目**: feishu-hub Qoder 执行器（`D:\sire\AI\AI\feishu-hub`）
**状态**: 单元级已验证；真机端到端 BLOCKED-无法真实验证（Qoder CLI 未安装、启动 Hub 会与旧飞书桥抢长连接）
**关键词**: feishu-hub, 飞书中转, 执行器协议 v1, Qoder 执行器, qoderclicn, QODER_CLI_BIN, hook_stop, sessions/turns, spool, FEISHU_HUB_TASK_ID, executors 白名单, STRICT_TASK, CUTOVER, parity 复测

**场景**: 让飞书既能给 Qoder 派任务，也能把 Qoder 桌面上的独立回复同步成卡片并可续接；与既有 Claude / Codex 执行器同级接入。

**做法**:
1. `executors/qoder/executor.py`：按 PROTOCOL v1 上线（`new_session/resume`，`desktop_queue:false`）、`claim` 长轮询、`started(pid,pid_ctime)`、心跳、终态事件；`LeaseLost` 时 `taskkill /T /F` 杀进程树后立刻停止上报；**子进程已启动过就不能 release，只能 interrupted**。目录必须真实存在否则 `CWD_MISSING`（绝不猜目录）。
2. CLI 定位顺序：`QODER_CLI_BIN` → PATH(`qoderclicn`/`qodercn`) → 已知安装目录；找不到时任务报 `CLI_NOT_FOUND`，不影响其它执行器。参数模板可配置（`args_new`/`args_resume`），默认 `-p --output-format json [--resume S] --permission-mode bypassPermissions`——**这是按 Qoder 与 Claude Code 同源推断的，未真机验证**。
3. 结果解析：stdout 取最后一个 `{"type":"result"}`；`is_error` 或错误文案映射为 `AUTH_REQUIRED`(login/unauthor/401)、`SESSION_NOT_FOUND`(no conversation found)、`NO_RESULT`；session 变化先报 `session` 事件，飞书卡片才能续接。
4. 子进程环境注入 `FEISHU_HUB_TASK_ID/LEASE_ID/CWD/URL`，桌面 Hook 见到任务号就抑制，避免双卡片；独立轮次由 `hook_stop.py` 读 Qoder 转录尾部最终可见回复 → `POST /v1/sessions/turns`，Hub 不可达时 `spool` 落盘、执行器上线 `flush_spool` 补发。
5. Hub 侧接入点只有两处：`hub/config.py` 的 `executors` 白名单，以及 `hub/service.py` 里 5 条指令正则 + 2 处提示文案（`STRICT_TASK`、`PROJECT_LIST`、回复前缀、粘连拆分、协作句）；运行期 `~/.feishu_hub/config.json` 若显式写了 `executors` 会覆盖默认值，要先确认。
6. Qoder 桌面钩子与 SIRE 遥测钩子共用 `Stop` 事件：Qoder 侧每个事件保持**单条目**（多条目曾出现停采），需要共存时改成一条链式命令，装完立刻 `sire_qoder.py parity` 复测心跳是否仍在增长。

**关键文件与接口**:
- `feishu-hub/executors/qoder/executor.py`（`--check` 只探测 CLI 与配置，不领任务）
- `feishu-hub/executors/qoder/hook_stop.py`（`build_turn` / `handle_payload`）
- `feishu-hub/hub/config.py:50`、`hub/service.py:21,22,206,207,246,251,382,429`
- `feishu-hub/docs/QODER_ADAPTER.md`（用法、接线、验收表 Q1–Q9、上线四步）
- `feishu-hub/tests/test_qoder_executor.py`（假 HubClient/FakeReporter，不联网）

**验证方法**: `python tests/test_qoder_executor.py` → 9 项全 OK（三端指令解析、new/resume 命令构造、result 与 session 上报、四种错误码、CWD_MISSING、Hook 抑制/invalid/spool、转录回退读取）。回归：`tests/test_codex_executor.py` 20 项 0 失败；`tests/test_hub.py` 79 项 2 失败，且把本次 `hub/service.py` 改动 `git stash` 后**同样 2 项失败** → 属既有问题（Claude 执行器的 `--resume` + prompt 走 stdin、重复卡片两条用例），不是接入 Qoder 引入。`executor.py --check` 如实报 `CLI_NOT_FOUND`。

**踩坑**: ① 用 `git stash push <file>` + 跑测试 + `git stash pop` 是判定"红是既有还是我引入"的最低成本办法；② 中文正则锚点做批量替换时，`Claude」或「Codex」` 这类整句提示词也在断言里，扩三端要同时改文案与测试期望；③ 测试脚本别真去构造 `HubClient`——它会 `_bootstrap()` 写 `~/.feishu_hub/token`，用假客户端注入即可。

**限制**: 未做真机端到端（Q8/Q9 BLOCKED）：需要装 Qoder CLI 并按 `docs/CUTOVER.md` 停旧飞书桥再启 Hub；CLI 的参数与结果字段形态、错误文案都是推断，装好后按 `docs/QODER_ADAPTER.md` §6 第 2 步先校对。Qoder 侧也不能按任务指定模型档位。


### E-017: Qoder CLI（qoderclicn）离线安装与 headless 调用契约：manifest+sha256、SDK 环境变量陷阱、单行 result JSON、--resume、按档位选模型

**日期**: 2026-10-13
**项目**: Qoder CLI headless 接入（feishu-hub Qoder 执行器）（`D:\sire\AI\AI\feishu-hub`）
**状态**: 已验证（真机实测；`tests/test_qoder_executor.py` 11/11）
**关键词**: qoderclicn, Qoder CLI, headless, manifest.json, sha256, sdk_invalid_args, QODER_AGENT_SDK_ENTRYPOINT, --permission-mode bypass_permissions, dont_ask, --output-format json, --resume, total_credits, login 设备码, model_by_tier, reasoning-effort

**场景**: 要让飞书 / 脚本能像调用 `claude -p` 那样非交互调用 Qoder。本机只有 IDE（`D:\software\Qoder CN\Qoder CN.exe`），PATH 上没有 `qoderclicn`，`entry/qodercn-dispatcher.ps1` 会回落报错。

**做法**:
1. **版本对齐**：在 `resources/app.asar` 里 grep `qoderCliVersion` 得到 IDE 期望的 CLI 版本（本次 1.1.66），不要盲目装最新。
2. **官方安装**：`https://static.qoder.com.cn/qoder-cli-cn/channels/1.1.66/manifest.json` → `files[]` 取 `os=windows / arch=amd64 / variant!=legacy` 的 `url`+`sha256`；下载 97MB zip，**校验 sha256 相等再解包**（实测 `2010601e43ef…e191b5` 一致），产物 `qoderclicn.exe`、`sites-build.json`、`sites-verification.json`。
3. **落位**：解到 `~/.qoder-cn/bin/qoderclicn/`——官方 dispatcher 的 `Find-Cli` 就找这个路径；不改 PATH、不改注册表、不改 IDE。
4. **调用契约**（真机确认）：`-p --output-format json`，prompt 走 stdin；输出单行 `{"type":"result","result","session_id","is_error","num_turns","total_credits","duration_ms",…}`；`--permission-mode` 用蛇形（`bypass_permissions|dont_ask|accept_edits|auto|default`）；`--tools ""` 做零副作用冒烟；`--resume <session_id>` 可续接（实测能复述上一轮）。
5. **模型分档**：`-m/--model`、`--reasoning-effort`、`--thinking-budget`、`--list-models` 都在 → 执行器加 `model_by_tier`/`effort_by_tier` 配置，飞书任务可按档位派发（推翻"Qoder 无法分档"的旧结论；交互式 `Agent` 工具仍无 model 参数）。
6. **登录**：`qoderclicn login` 打印设备码 URL，桌面已有信任会话时**自动完成**；未登录时结果 JSON `is_error:true`、`result:"Not logged in — Please run /login"` 且 rc=1，执行器映射 `AUTH_REQUIRED`。

**关键文件与接口**:
- `feishu-hub/executors/qoder/executor.py` — `find_cli()`（含 `.qoder-cn/bin/qoderclicn/`）、`ENV_DROP_PREFIX`、`build_cmd()`（含 tier→model/effort）、`--check`
- `feishu-hub/docs/QODER_ADAPTER.md` §5.5 安装来源与实测要点、§5 验收表 Q8a/Q8b/Q8c
- `feishu-hub/tests/test_qoder_executor.py` — 假 Hub + stub CLI 的 `started→session→result` 全序列

**验证方法**: `executor.py --check` 从 `CLI_NOT_FOUND` 变 `OK` 并给出真实路径；真机 headless：`is_error=false`、`result="收到"`、`total_credits=1.278`、15.5s；`--resume` 续接正确；`tests/test_qoder_executor.py` 11 项全 OK；回归 `tests/test_codex_executor.py` 20 项 0 失败。

**踩坑**: ① 直接在 Qoder/IDE 的子 shell 里调 CLI 必失败——`QODER_AGENT_SDK_ENTRYPOINT` 会让它强制要求 `--input-format stream-json --output-format stream-json`，必须在 `build_env()` 里按前缀剔变量；② 只把 `--config-dir`/PATH 之类当排查方向会浪费时间，先看 `sdk_invalid_args` 报的期望参数；③ CLI 报"未登录"这类致命错也照样输出 JSON 且 **stdout 才有信息**，不能只看 rc；④ `--check` 早期把候选路径写成 `bin/qoderclicn.exe` 漏了子目录，探测型代码要用真实安装路径回归。

**限制**: Hub → 执行器 → 飞书卡片的端到端仍待用户按 `docs/CUTOVER.md` 停旧飞书桥后启 Hub 验证（Q8b）；`model_by_tier` 需要登录后 `--list-models` 取值；CLI 每次执行消耗 credits（本次 1.28/条），Hub 侧 `daily_task_limit=20` 仍生效。
