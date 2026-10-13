# 验证与归档

## 文档和路径核对

- 已读取 `docs/COLLABORATION.md` 全文（v0.2，§1–§7）。摘要在 `summary.md`。
- 静态检查确认 `UNITY/ProjectSettings/ProjectVersion.txt`、`UNITY/Packages/manifest.json`、`UNITY/Assets/Scenes/Prototype/Field.unity` 存在。
- Unity 下未发现 `.fbx` 或 `.blend` 文件；原概念 SVG 存在于 `UNITY/Assets/Art/Concepts/TNK_Light_Rover_Concept_v01.svg`。
- 已更正 `docs/ART_BIBLE.md` 的 SVG 相对链接、Unity 工程结构描述和坐标/单位/武器朝向合同；协作约定文件未修改。
- 已更正前一 run 的美术记录、`F-044` 知识项中的错误资源路径和工程状态，以保留准确可检索事实。

## R7 / R10

- R7 跳过真实应用测试：本轮是读取协作文档和修正文档引用，没有 Unity UI 或运行时改动；真实游戏功能未测试。
- R10 跳过：无需打开 Unity、修改设置或执行系统操作。

## SIRE

- 检索日志：`kb-search.log`、`vector-search.log`；详细判断见 `kb-hits.md`。
- SIRE run 启动：preflight PASS；快照记录见共享 SIRE 完整性目录中的 `before.json`。
- 知识更新：修正共享知识 F-044 后重建 Markdown 索引（22 条索引记录：F9/P11/E1/H1）和向量索引（本轮插入 24 chunks，生成 25 embeddings）；F-044 已显示正确的 `UNITY/Assets` 路径和坐标合同。
- DB 预迁移备份：`D:/sire/db-backups/sire_vectors-20260927-092058-097423.sqlite3`，完整性 `ok`。
- 首次迁移后核对：`PRAGMA integrity_check=ok`；129 条 knowledge_records（F-044 唯一）；2139 条 task_records（本 run 7 条）；6124 embeddings 均非空；`chunks_fts` 命中 11 条，`cfts` 命中 5 条。向量检索已返回修正后的 F-044（Unity Y-up、前向 +Z、资源路径为 `UNITY/Assets/...`）。
- 任务元数据目标：`sire_last_project=@CODE_ROOT@\\GAME`、`sire_last_run=R20260927-read-claude-collab-docs`、`sire_last_status=DONE_WITH_ARCHIVE_BLOCKER`；在最终同步前写入并复核。
- 机器级 archive：未配置；不得猜测 `SIRE_ARCHIVE_ROOT`/`SIRE_ARCHIVE_DB`，因此未写入机器级副本或更新 snapshot manifest。
- Git：GAME 根目录未确认存在 Git 元数据；SIRE 仓库已有本任务开始前的 DB、manifest、SIRE 文档及运行目录改动，本轮不提交或重置预存内容。
- Supervisor：本 run start 的 preflight `PASS`；最终 run-check `PASS`（无缺失）；finalize `STOP` / `rsi_unregistered_change`，原因是开始前已有的 `sire/workflow/shared/sire/references/global-contract.md` 未提交且无 RSI 提案。本轮没有修改该文件。
