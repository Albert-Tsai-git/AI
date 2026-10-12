# SIRE 共享安装与数据迁移契约

**当前规范版本：2.0（Claude 与 Codex 共用）**

本文件替代本目录中的 `SIRE-MIGRATION-legacy-v1.md`。旧文档只用于历史追溯，不得按其中的分离目录方案部署。

## 唯一来源

- 共享 skill：`sire/workflow/shared/sire/`。
- 共享知识：`sire/knowledge/global/`。
- 共享 SQLite：`sire/data/sire_vectors.sqlite3`。
- 共享脚本通过 `scripts/sire_paths.py` 取得这些路径。
- Claude 的 `~/.claude/skills/sire-global-workflow/` 与 Codex 的 `~/.codex/skills/ai-dev-sire-workflow/` 必须是指向同一共享 skill 目录的目录联接；两个入口的 `SKILL.md`、脚本和角色资源解析后必须是同一物理文件。
- Claude 与 Codex 命令都必须读取同一 `DATABASE_PATH` 与 `KNOWLEDGE_DIR`。不要复制另一份 skill、Markdown 知识或数据库。

`SIRE_ROOT`、`SIRE_DATA_DIR`、`SIRE_VECTOR_DB`、`SIRE_KB_DIR`、`SIRE_EMBED_DIR` 和 `SIRE_TASK_ROOTS` 是共享覆盖项。若设置覆盖项，Claude 和 Codex 启动环境必须相同。默认值以当前仓库里的共享目录为准。

## 部署或恢复

1. 将仓库放在两种客户端均可访问的本机路径，并保留 `sire/data/` 与 `sire/knowledge/global/`。
2. 先将已有 Codex/Claude SIRE skill 目录改名保留为备份；不要在未备份前删除旧目录。
3. 分别创建两个目录联接，都指向 `sire/workflow/shared/sire/`。Windows PowerShell 示例：

   ```powershell
   New-Item -ItemType Junction -Path $codexSkillPath -Target $sharedSkillPath
   New-Item -ItemType Junction -Path $claudeSkillPath -Target $sharedSkillPath
   ```

4. 如需兼容原 `sire_global` 路径，只能把它联接到 `sire/knowledge/global/`；不得另建可写副本。
5. 不要把模型权重、数据库 WAL/SHM、加密密钥、个人设置或 `integrity/` 配置快照纳入 Git。需要保留的本机私密资源存放在仓库外。
6. 重启两个客户端进程，使其重新读取安装目录中的共享 skill。

## 知识与数据库写入

- 新增/修改 Markdown：使用共享 `sire_kb.py` 操作 `KNOWLEDGE_DIR`，随后运行 `reindex` 和 `sire_vector_db.py index`。
- 归档 run 台账：将运行记录留存在工作区 `.sire/runs/` 或 `sire/runs/`，随后运行 `sire_vector_db.py migrate`。
- 两端检索都使用同一 SQLite。更新后复核知识 ID、FTS、`integrity_check`、计数和 embedding 文本哈希。
- SIRE 修改共享数据库后，应备份并检查数据库，只提交知识/工作流改动；数据库暂不进 Git，本机路径见 `sire/data/DATABASE-RECORD.md`。
- 数据库备份放到仓库外；不要将 WAL/SHM、私有密钥、模型缓存或整份个人配置写入 Git。
- 修改共享 skill 目录（`sire/workflow/shared/sire/`）前先运行 `sire_rsi.py propose` 登记 RSI 提案；R9 `sire_supervisor.py finalize` / `rsi-check` 会拦截未登记的未提交改动（`rsi_unregistered_change`）。`sire_rsi.py` 写命令同时写机器级归档库（`SIRE_ARCHIVE_ROOT`/`SIRE_ARCHIVE_DB`/`--archive-db`）与仓库库；`snapshot_db.py` 发现仓库库独有的 RSI 记录时拒绝发布。

## Git 快照与轻量 ZIP

2026-10-12 起数据库暂不进 Git（超过 GitHub 100MB 单文件上限），本仓库只保留 `sire/data/DATABASE-RECORD.md` 记录本机路径；Git 历史中最后一份数据库是 69MB 的旧版，不代表最新数据。轻量 ZIP 分发同样不含数据库和历史运行台账。ZIP 内的 skill 也只保存一份 `shared/sire/`，恢复时将 Claude 与 Codex 两个入口同时联接到这份目录。

## 两端验收

部署后从 Codex 和 Claude 分别核对：

1. 两个 skill 入口的真实目标相同，读取同一个 `SKILL.md`。
2. `sire_paths.py` 输出相同的数据库路径和知识目录。
3. 分别运行数据库 `stats` 与共同关键词 `search`，计数和命中 ID 相同。
4. 在一个入口新增知识并索引后，另一个入口可立即检索到该记录；用 `sire_vector_db.py stats` 计数和数据库文件修改时间确认是同一个本机数据库发生了变化（数据库已被 .gitignore 忽略，`git status` 看不到它）。

历史目录命名和旧 ZIP 操作说明见 `SIRE-MIGRATION-legacy-v1.md`，不作为当前安装规范。

## 变更记录

| 日期 | run | 变更 | 验证 |
|---|---|---|---|
| 2026-09-25 | R20260925-052105 | RSI 接入入口（SKILL.md、supervisor.md 检查项 8）与 R9 `rsi-check`/`finalize` 门禁；RSI-20260925-R9GATE → v6.2 | R6A/R6B/R6C 复核、R7 T1–T8 及复测，见 run evidence/U-01 |
| 2026-09-25 | R20260925-SYNC（本会话） | governor 收敛为 `sire/workflow/support/ai-workflow-governor/` 单份（删除 `shared/sire/references/governor/`；Codex 不再安装独立 governor skill）；RSI 双库写入、只读 status、快照 RSI 丢失保护；RSI-20260925-SYNC → v6.3 ACTIVE（78e25b4）| run R20260925-112329：R4/R6A/R6B/R6C/R7 PASS；知识 E-008 |
| 2026-09-25 | 本会话 | global-contract.md 新增“模型分级与省 token 机制”：低难度派 haiku、中难度派 sonnet、高难度留主控，失败逐级升模型 | 规则文本已写入并校验 grep 命中 |
| 2026-09-26 | 本会话 | 模型分级改为：低=haiku，中=Opus 5.5 low 思考，高=Opus 5.5 high 思考；新增子代理 sire-low/sire-mid/sire-high | grep 校验 |
| 2026-10-12 | R20261012-claude-tier-agents-link | sire-low/mid/high 纳入 `shared/sire/agents/claude/`，`~/.claude/agents` 同名文件改为符号链接（原件留 `.legacy-backup-20261012`）；R9 `REQUIRED_AGENT_NAMES` 加 low/mid/high，打包缺失即 `package_omission`；RSI-20261012-TIERAGENTS → v6.5 | R6 sire-mid PASS；R7 T2 打包+verify-zip PASS、T3 删件后 STOP；T1 新进程加载 BLOCKED（CLI 401） |
| 2026-10-12 | R20261012-db-untrack | 数据库 168MB 超 GitHub 100MB 上限推送被拒；用户决定数据库暂不进 Git：未推送提交改写去掉大文件、停止跟踪并 .gitignore、新增 `sire/data/DATABASE-RECORD.md` 记录本机路径；SKILL.md/global-contract/supervisor/vector-knowledge/README 同步改述；RSI-20261012-DBUNTRACK → v6.6 | 待推送范围无 >50MB 对象；文档无残留“数据库进 Git”表述 |
