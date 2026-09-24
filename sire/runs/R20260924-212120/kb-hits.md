# KB-Check KB-001

- 检索库：`@SIRE_ROOT@\sire_vectors.sqlite3`。关键词：SIRE workflow, Git archive, SQLite snapshot, database sanitization, secrets, WAL/SHM, model cache。
- 命中 K-CODEBASE-MAP-20260924（前序 @CODE_ROOT@ 仓库分析已汇总在库）；可复用其 22 条知识和 5 条任务归档，不重复扫描业务代码。
- 命中 F-028（知识库 v2 与向量/FTS一致性）、P-021（避免把整仓源码导入知识库及先备份后改 DB）、迁移/同步约定（ZIP 轻量包与公用 SQLite 分开）。
- 机器级闭环归档初始只读基线：121 knowledge_records，578 task_records，1,473 chunks，1,328 BGE embedding rows，5,685 keywords；PRAGMA integrity_check=ok。检索运行数据库已改为仓库内唯一 `sire/data/sire_vectors.sqlite3`。
- 仓库基线：`@SIRE_ROOT@\AI\AI` 分支 `feature/feishu-hub`，HEAD `28cb18c`，本地领先 origin 1 个提交，工作区干净。
- 决策：保留完整数据库逻辑数据于 Git 快照，但不原样复制原 DB；规范化本机路径/PII 并清空旧 SQLite 空闲页。密钥与环境快照排除。
- 未复用：整目录镜像（可能包含密钥与个人配置），模型缓存与临时数据库 sidecar。
