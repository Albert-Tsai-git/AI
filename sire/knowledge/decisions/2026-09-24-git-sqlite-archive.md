# SIRE Git 数据库快照：保留完整记录并规范化本机路径

**日期**: 2026-09-24
**项目**: SIRE v6
**关键词**: SIRE, Git 归档, SQLite 快照, 在线备份, 路径脱敏, FTS, embedding, VACUUM

## 需求场景
当 SIRE 工作流与向量数据库需要进入 Git 仓库时，原始 SQLite 文件可能包含本机路径、邮箱/私网地址和过去更新留下的 freelist 页。直接复制虽可能 `integrity_check=ok`，仍会泄露旧值。

## 方案
用 SQLite backup API 在源库只读连接上生成一致副本；只在副本文本列中统一机器盘符与用户目录并清理邮箱/私网 IPv4；重建 `chunks_fts`、`kfts`、`cfts`，重算受影响的 legacy hashed vectors 与 v2 semantic embeddings；启用 `secure_delete` 后 `VACUUM`；扫描 SQLite 全部可见文本及整个文件字节，再确认 sidecar 不存在。Git 快照保留业务行和表，排除 key/vault、个人配置快照、模型权重和 WAL/SHM。

## 关键文件
- `sire/tools/snapshot_db.py`：可重复的脱敏在线备份、索引重建和泄露验证。
- `sire/data/sire_vectors.sqlite3`：Git 数据快照。
- `sire/data/snapshot-manifest.json`：来源 hash、表计数、替换计数和验证结果。
- `sire/workflow/codex/ai-dev-sire-workflow/scripts/sire_knowledge_index.py`：当前 FTS/embedding 逻辑来源。

## 验证
本任务 R7 逐项记录 SQLite 完整性与计数、FTS 查询、embedding 文本 hash 一致性、全文件凭据/路径/PII扫描、WAL/SHM 排除和 Git 实际跟踪/提交状态。源数据库另行备份，不被快照工具改写。

## 限制
匹配式隐私扫描只能识别常见凭据格式；清理的是机器标识而非语义知识。执行脚本需要本机可用的匹配 embedding 模型；如模型不可用会失败并保留原快照，不得跳过向量一致性校验。
