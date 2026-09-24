# R7 功能与回归测试结果

- 更新：2026-09-25T00:11:54+08:00
- 范围：仓库文件/路径别名、知识索引、只读查询、数据库快照完整性与隐私。
- 总结：CLI 和 Git 存储验收通过；仅 R7-UI-01/02 与 R10 原生 UI 交互阻塞，因为本机 CUA 没有可控制的桌面应用。
- 快照数据库与精确计数以 `../data/snapshot-manifest.json` 为准。

| 测试编号 | 操作/验收 | 结果 | 证据 |
|---|---|---|---|
| R7-GIT-01 | 目标仓库范围/基线与业务仓库保护 | PASS | `requirements.md`; repository analysis run |
| R7-FILE-02 | source-manifest 56 source entries / 55 canonical targets 与哈希核对 | PASS | `source-manifest.json` |
| R7-DB-03 | 仓库快照可重开、表计数、integrity_check、FTS | PASS | `evidence/R7-DB-03-04.json` |
| R7-DB-04 | SQLite 文本与 printable-byte 路径/PII/凭据检查 | PASS | `evidence/R7-DB-03-04.json`; `data/snapshot-manifest.json` |
| R7-GIT-05 | diff --check、精确归档范围、提交后 clean/基线验证 | PASS | 最终本地提交与提交后 Git 状态 |
| R7-KB-01 | 临时 canonical + duplicate backup/export fixture | PASS | `evidence/R7-KB.json` |
| R7-KB-02 | 全局 KB reindex 与新增知识索引 | PASS | `evidence/R7-KB.json` |
| R7-KB-03 | 重复 canonical ID 拒绝且旧索引保留 | PASS | `evidence/R7-KB.json` |
| R7-DB-06 | 不存在源库不得生成目标/sidecar | PASS | `evidence/R7-SNAPSHOT-PUBLICATION.json` |
| R7-DB-07 | 私有临时快照来源稳定、完整性、FTS、隐私与清理 | PASS | `evidence/R7-DB-07-08.json` |
| R7-DB-08 | 所有 knowledge/chunk 的 BGE text_hash 一一匹配 | PASS | `evidence/R7-DB-07-08.json` |
| R7-DB-09 | 缺失源库错误不改变已有 DB/manifest | PASS | `evidence/R7-SNAPSHOT-PUBLICATION.json` |
| R7-DB-10 | manifest replace 失败成对回滚；旧 WAL 模式逻辑恢复 | PASS | `evidence/R7-SNAPSHOT-PUBLICATION.json` |
| R7-DB-11 | 拒绝将 snapshot-manifest.json 当数据库目标 | PASS | `evidence/R7-SNAPSHOT-PUBLICATION.json` |
| R7-SHARE-01 | Codex/Claude skill directory links 与 SKILL 哈希一致 | PASS | `evidence/R7-SHARE-01.txt` |
| R7-SHARE-02 | 两端路径解析到同一 tracked DB 和知识根 | PASS | `evidence/R7-SHARE-02-04.json` |
| R7-SHARE-03 | 两端 stats 与同一关键词检索一致 | PASS | `evidence/R7-SHARE-02-04.json` |
| R7-SHARE-04 | 共享 skill/script/role canonical source 与唯一副本 | PASS | `evidence/R7-SHARE-02-04.json`; `source-manifest.json` |
| R7-UI-01 | Codex 原生 UI skill 与查询验收 | BLOCKED-无法真实验证 | `evidence/R7-UI-preflight.txt` |
| R7-UI-02 | Claude 原生 UI 正常与边界查询验收 | BLOCKED-无法真实验证 | `evidence/R7-UI-preflight.txt` |
| R7-READ-ONLY-12 | stats/search/show 正常与边界且只读哈希不变 | PASS | `evidence/R7-READ-ONLY-12.json` |
| R7-DB-12 | RSI 与快照/索引使用共同锁且写前备份 | PASS | `evidence/R7-RSI-WRITER-LOCK.json`; `evidence/R7-SNAPSHOT-PUBLICATION.json` |
| R7-DB-13 | 元数据知识/任务/关键字计数与实际表计数一致 | PASS | `evidence/R7-SNAPSHOT-PUBLICATION.json` |
| R10-UI | Claude/Codex 桌面应用启动与真实界面验收 | BLOCKED-无法真实验证 | `evidence/R7-UI-preflight.txt`; `blockers.md` |
