

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
