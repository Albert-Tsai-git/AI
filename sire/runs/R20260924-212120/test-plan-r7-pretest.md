# R7 测试前清单（先列清单，再执行）

| 编号 | 用户路径/操作步骤 | 预期表现 | 实际表现 | 证据 | 结论 |
|---|---|---|---|---|---|
| R7-GIT-01 | 在目标仓库读取 README/文件清单和 git status | 仅增加 sire/归档；原 feishu-hub 与已有提交不变 | 待执行 | 待填 | 待执行 |
| R7-FILE-02 | 打开打包后的工作流、规则、知识和评测文件；按 manifest 比较 SHA256 | 目标文件可读、内容字节对应源，排除项不存在 | 待执行 | 待填 | 待执行 |
| R7-DB-03 | 用 sqlite3 只读打开仓库 DB，核对 sqlite_master、记录计数、integrity_check、FTS 查询 | 库可重开，计数与 source 一致，integrity=ok，全文检索有效 | 待执行 | 待填 | 待执行 |
| R7-DB-04 | 扫描仓库 DB、被跟踪文本和 Git blob（含整个 SQLite 文件） | 无 machine absolute paths、emails、private IP、credential patterns、密钥文件和 WAL/SHM | 待执行 | 待填 | 待执行 |
| R7-GIT-05 | 执行 `git diff --check`、列出 staged files、提交后复查 `git status`/基线 ancestry | whitespace clean；只提交新增 SIRE 目录和 README 链接；提交后 clean且无 push | 待执行 | 待填 | 待执行 |

本任务涉及 Claude/Codex 应用入口。R10 已通过本机目录联接操作完成安装；尝试进行桌面路径时，当前 CUA 返回 apps 为空且 native app API 不可用，因此 R10 的应用启动/点选路径与 R7 两端 UI 测试记为 BLOCKED-无法真实验证；共享文件和数据库仍执行 CLI 实际路径验收。

| R7-KB-01 | 在临时知识库 CLI `reindex`（正常记录 + `integrity/` 中同 ID 备份 + `global_knowledge_records.md` 同 ID 导出） | 只保留 canonical 记录，exit 0，无 duplicate ID warning | 待执行 | 待填 | 待执行 |
| R7-KB-02 | 在实际 SIRE 全局知识库运行 `sire_kb.py reindex` 并核对索引记录数/编号 | 无重复编号警告，新增 P-024 进入索引，派生导出与快照不计入来源 | 待执行 | 待填 | 待执行 |

| R7-DB-06 | snapshot CLI 使用不存在的源库并指向临时目的地 | 返回非零且不生成目标/sidecar，不泄露匹配内容 | 待执行 | 待填 | 待执行 |
| R7-DB-07 | snapshot CLI 对真实源库写临时快照，重开数据库、查计数/FTS/隐私并清理临时文件 | 完整副本可读且脱敏工具所有检查通过；清理后临时目标不存在 | 待执行 | 待填 | 待执行 |
| R7-KB-03 | 临时 canonical Markdown 文件包含两条同 ID 记录，运行 `sire_kb.py reindex` | 输出重复编号且 exit 非零；索引不被当作有效结果 | 待执行 | 待填 | 待执行 |
| R7-DB-08 | 生成本地 SQLite 快照后遍历所有 knowledge/chunk 与 BGE 向量 text_hash | 每条记录均有匹配当前文本的向量，含历史 chunk；行数相等 | 待执行 | 待填 | 待执行 |
| R7-DB-09 | 对不存在源库指定现有目的库路径 | 命令失败且现存数据库/manifest 字节不变 | 待执行 | 待填 | 待执行 |
| R7-DB-10 | 向现存临时数据库/manifest 运行快照，注入 manifest replace 失败 | CLI 工作流异常退出；DB 与 manifest 成对恢复为原字节，临时文件清理 | 待执行 | 待填 | 待执行 |
| R7-DB-11 | 将输出路径设为 `snapshot-manifest.json` | 预检明确拒绝，输入 DB 和目录文件均不改变 | 待执行 | 待填 | 待执行 |
| R7-SHARE-01 | 从 Claude 与 Codex 的已安装 skill 路径分别解析真实目录与 SKILL.md | 两个入口均指向同一仓库物理目录与同一 SKILL 文件 | PowerShell 确认两个入口均为 Junction 且 Target 相同；Python pathlib.Path.resolve() 两端均解析到 `@SIRE_ROOT@\AI\AI\sire\workflow\shared\sire`；SKILL SHA256 相同 | `@CODE_ROOT@\.sire\runs\R20260924-212120\evidence\R7-SHARE-01.txt` | PASS |
| R7-SHARE-02 | 分别导入 Claude `sire_kb.py` 与 Codex `sire_vector_db.py` 的路径解析 | 两者返回完全相同的 Git 跟踪 DB 与 canonical knowledge 路径 | 待执行 | 待填 | 待执行 |
| R7-SHARE-03 | 从两端各执行数据库统计与一个共同关键词查询 | 两端读取同一 SQLite 文件、同一知识记录并返回一致计数/命中 ID | 待执行 | 待填 | 待执行 |
| R7-SHARE-04 | 检查共享 skill 与脚本的哈希以及两端目录别名 | 只有一份实际 SIRE SKILL、脚本、角色资源；差异仅为入口别名 | 待执行 | 待填 | 待执行 |

| R7-UI-01 | 在 Codex 桌面打开 `$sire`，搜索共享知识并查询数据库统计 | 界面显示共享 skill 生效；统计指向仓库内唯一 DB | CUA `getState()` 返回 `apps=[]`，仅有无标签 IAB；原生 UI API 不可用，无法打开 Codex | `@CODE_ROOT@\.sire\runs\R20260924-212120\evidence\R7-UI-preflight.txt` | BLOCKED-无法真实验证 |
| R7-UI-02 | 在 Claude 桌面打开共享 SIRE skill，执行同一关键词检索；再用无效查询触发边界结果 | 正常检索命中与 Codex 相同；边界输入返回受控空结果/错误，不创建副本 DB | CUA `getState()` 返回 `apps=[]`；native app API 不可用，正常与边界 UI 路径均无法执行 | `@CODE_ROOT@\.sire\runs\R20260924-212120\evidence\R7-UI-preflight.txt` | BLOCKED-无法真实验证 |
