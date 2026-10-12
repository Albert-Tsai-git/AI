# R2 需求分析

## 目标（用户原话）
"将当前仓库里面的内容分析整理到 sire 数据库 并建立好索引 便于后面（开发功能）"

## 可观察结果
后续任何人（或 AI）在 driverSoftware2 上开发新功能前，用 `sire_kb.py search` / `sire_vector_db.py search`
以功能名、模块名、文件名、协议字段等关键词检索，能命中本仓的**架构地图级知识记录**，
记录里带 `文件路径:行号` 入口，可直接跳到代码。

## 范围
- 覆盖：仓库分层与入口、后端 core（reader/protocol/commands/worker/档案/诊断）、前端页面与通信与图表、
  测试与门禁、构建与发布、文档体系与"改动→必读 skill"映射、当前在研的下线检测功能全貌。
- 不覆盖：逐行代码解释、一次性调试细节、缺陷池工单内容、固件仓内部实现（属另一仓）。

## 输入
- 本仓代码（VERSION 0.16.1 / 分支 feat/offline-detection-optimize）
- 4 路只读勘察代理报告（后端 / 前端 / 工程基建 / 文档与在研功能）
- SIRE 既有知识：F-019/F-024（流程规范）、H-004（排查纪律）、K-REPO-DRIVERSOFTWARE-20260924（过时地图，需替换）

## 输出
- `knowledge/global/global_dev_features.md` 新增 F 记录若干条（编号由 `sire_kb.py next-id F` 分配，不手填）
- 索引重建：`sire_kb.py reindex` + `sire_vector_db.py index`（内含备份、chunks、FTS、knowledge_records、keywords、语义向量后处理）
- 台账与检索验收证据

## 验收标准
1. 每条记录含 需求场景/方案/关键文件与接口(带行号)/验证方法/状态/关键词 段落，`sire_kb.py lint` 不缺段。
2. `sire_vector_db.py stats` 的 knowledge_record_count 比入库前增加，且增加数 = 新记录数。
3. 用 ≥5 组"后续开发会用的真实查询词"检索，每组 Top5 至少命中 1 条本次新记录（记录 ID 需在结果中出现）。
4. SQLite `PRAGMA integrity_check` = ok；索引前有可恢复备份。

## 依赖与授权
- 授权：写 SIRE 知识库 Markdown + 写共享数据库（索引操作自带备份）；**不改** `workflow/shared/sire/`（避免触发 RSI 机制变更）；不把整仓源码切片入库。
- 依赖：数据库写入走 `sire_vector_db.py index` 的既有备份/锁路径（`backup_before_mutation` + `snapshot_db` 锁）。
- 本仓 git：知识库文件在 D:\sire 仓，不在 driverSoftware2 仓；driverSoftware2 只新增 `.sire/runs/`（已 gitignore），**不产生本仓 commit**。

## 关键取舍
- 选"蒸馏成 F 记录"而非"整仓源码进向量库"：`sync_knowledge_records` 只解析四类 global md（受支持路径）；
  共享库为多项目共用，塞源码属机制变更且需 RSI 提案。
- 旧的 K-REPO-* 记录不删除：删除需 `SIRE_DB_ALLOW_DELETE=1` + 密码，属破坏性操作，留给用户决定；
  新记录标题带 driverSoftware2 与当前版本，检索时按项目词即可区分。
