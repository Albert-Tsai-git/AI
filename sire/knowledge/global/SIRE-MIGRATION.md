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
- SIRE 修改共享数据库后，应按本仓库快照流程备份、检查并提交数据库与知识/工作流改动。
- 数据库备份放到仓库外；不要将 WAL/SHM、私有密钥、模型缓存或整份个人配置写入 Git。

## Git 快照与轻量 ZIP

本 Git 仓库保存完整的已检查 SQLite 数据库快照。轻量 ZIP 分发仍不含数据库和历史运行台账，两种归档用途不同，不能互相覆盖。ZIP 内的 skill 也只保存一份 `shared/sire/`，恢复时将 Claude 与 Codex 两个入口同时联接到这份目录。

## 两端验收

部署后从 Codex 和 Claude 分别核对：

1. 两个 skill 入口的真实目标相同，读取同一个 `SKILL.md`。
2. `sire_paths.py` 输出相同的数据库路径和知识目录。
3. 分别运行数据库 `stats` 与共同关键词 `search`，计数和命中 ID 相同。
4. 在一个入口新增知识并索引后，另一个入口可立即检索到该记录；确认 Git 工作区中的同一数据库文件发生变化。

历史目录命名和旧 ZIP 操作说明见 `SIRE-MIGRATION-legacy-v1.md`，不作为当前安装规范。
