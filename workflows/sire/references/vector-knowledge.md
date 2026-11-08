# SIRE 向量知识库

## 目标

SIRE 在每个任务执行前，用最快的本地查询检索历史需求、解决方案、过程文档、失败记录和工作流规则。命中后必须读取关联 chunk，判断是 `reuse`、`adapt`、`reference-only` 还是 `avoid`，并将判断写入当前 run 的 G0/K​​B 回执。

## 存储与性能

- 数据库：`%SIRE_DB%`（默认 `%SIRE_HOME%\vector_db\sire_vectors.sqlite3`）。
- 实现（v2，见知识 F-028）：SQLite + 混合检索。
  - 语义：本地 `BAAI/bge-small-zh-v1.5`（fastembed/ONNX，512 维），向量存 `emb` 表，按 text_hash 增量计算；模型缓存后离线运行。
  - 全文：FTS5 `tokenize='trigram'`（≥3 字符），2 字中文词用覆盖率补足；查询词须双引号包裹。
  - 打分：0.55×语义 + 0.30×词项覆盖 + 0.15×BM25 名次 + 关键词精确命中 0.1 + 知识记录 0.06。
  - 回退：v2 异常时回退 v1（哈希 n-gram，384 维）。
  - ⚠ 待本机确认：2026-09-24 数据库快照的 `meta` 仍显示 `hash-ngram-v1 / 384`，需运行 `stats` 核实 v2 是否实际生效。
- 索引：任务结束或新增知识后增量运行 `index`；任务开始只运行 `search`，避免重复全量扫描。R9 的 `integrity/` 快照是审计证据，不重复进入向量索引。
- 迁移：恢复文件后运行 `index`，重新绑定新主机上的绝对路径。
- 隐私：只在本机读取，不上传知识、凭据、私有源码或生产数据。

## 命令

```powershell
python "$env:SIRE_SCRIPTS\sire_vector_db.py" search --query "任务需求" --json --limit 5 --run "$env:SIRE_RUN_DIR"
python "$env:SIRE_SCRIPTS\sire_vector_db.py" show <chunk-id> --json
python "$env:SIRE_SCRIPTS\sire_vector_db.py" index
python "$env:SIRE_SCRIPTS\sire_vector_db.py" stats
```

若数据库不存在或没有 chunk，先执行一次 `index`；若搜索没有命中，继续正常 G0 检索，不把“无命中”当成失败。

## G0 记录格式

```yaml
vector_search:
  query: "原始任务摘要"
  hits: ["chunk-id/path"]
  reuse_decision: reuse|adapt|reference-only|avoid|none
  reason: "关联内容是否适用于当前任务"
```
