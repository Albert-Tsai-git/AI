# 验证与归档

## 交付验证

- `docs/ART_BIBLE.md` 已创建：包含视觉支柱、色板、提案状态、Blender/Unity 交付合同、首片资产优先级和评审表。
- `UNITY/Assets/Art/Concepts/TNK_Light_Rover_Concept_v01.svg` 已创建；PowerShell XML parser 正常解析。尺寸为 1600×1100，内容含主视图、多向视图、模块武器和色板。
- 数据接口对照：轻底盘 `TNK_Chassis_Light` 有 `Mount_Main`/`Mount_Sub`；概念板对应 `WPN_Cannon_75` 与 `WPN_MG_77`。重型底盘的 `Mount_SE` 未混入本轻车概念。
- GDD 方向复核：保留俯视 2.5D、Low-poly/Toon、低饱和盐尘色系和战车面数建议。六轮车、车体比例、Blender 轴向均明确标为提案。
- **更正（2026-09-27）**：Unity 工程位于 `UNITY/`，其中存在 `ProjectSettings/`、`Packages/manifest.json` 和 `Assets/Scenes/Prototype/`。先前在仓库根检查工程结构导致该项误报。仍未发现本概念对应的 `.blend` 或 `.fbx`，因此不能验收模型导入和武器挂点。

## 功能测试（R7）

| ID | 真实操作 | 预期 | 实际 / 证据 | 结论 |
|---|---|---|---|---|
| T01 | 通过 Codex in-app 浏览器打开概念 SVG | 显示整张可读概念板 | CUA 拒绝本地 `file:` 协议，策略只允许 `http:`/`https:` | BLOCKED-无法真实验证 |
| T02 | 边界路径：本地 `file:` 协议 | 显示内容或可理解错误 | 策略在打开前拦截并说明只允许 `http:`/`https:`；未重复尝试其他界面 | BLOCKED-无法真实验证 |
| T03 | 在 Unity 导入 FBX 后，以游戏俯视相机检查比例和挂点 | 朝向、尺寸、挂点与换装可读 | 工程存在于 `UNITY/`；当前没有本概念对应的 Blender/FBX 模型，无法执行导入检查 | BLOCKED-无法真实验证 |

- 静态结构检查：SVG XML 可解析；只证明文件结构，不证明视觉布局或游戏效果。
- ImageGen：两次调用均返回 HTTP 404；使用原生可编辑 SVG 提供概念参考，未伪称 AI 图像生成成功。

## SIRE 归档

- 查询回执：见 `kb-search.log`、`vector-search.log` 和 `kb-hits.md`。
- 可复用知识：新增 F-044 于共享知识 Markdown；`sire_kb.py reindex` 完成，索引含 F:9、P:11、E:1、H:1。`sire_vector_db.py index` 完成，新增 40 条索引、41 个 embedding。
- 预写备份：`D:/sire/db-backups/sire_vectors-20260927-090310-721911.sqlite3`，完整性 `ok`；增量索引脚本也自动生成并校验了数据库备份。
- 本地共享库迁移：`sire_vector_db.py migrate` 完成；最终库有 129 条 knowledge_records、2132 条 task_records，本 run 命中 6 条；F-044 可由 `sire_kb.py show` 读取，向量检索第一条命中 F-044（score 0.914）。
- 完整性与索引：`PRAGMA integrity_check=ok`；6070 条 embedding 均非空；`chunks_fts` 对挂点词检索命中 4 条。迁移脚本写入前生成的自动备份和显式备份均报告 `integrity=ok`。
- 机器级归档：`sire_paths.archive_database_path()` 返回 `None`，环境未设置 `SIRE_ARCHIVE_ROOT` / `SIRE_ARCHIVE_DB`。尽管机器根目录有另一个同名库，路径权威工具明确要求未设置时不猜目标，故未写入。
- Snapshot manifest：不从未确认的机器 archive 发布快照。
- Git：`D:/code/GAME` 不是 Git 仓库；SIRE repo 已有本任务开始前的 tracked/untracked 改动，未提交或重置。
- Supervisor run-check：`PASS`，无缺失文件；修改仅为本轮 `global_dev_features.md` 与其生成索引。
- Supervisor finalize：`STOP` / `rsi_unregistered_change`，仅因任务开始前已存在的 `sire/workflow/shared/sire/references/global-contract.md` 未提交且无 RSI 提案。此任务未修改该文件，也未创建提案或提交预存改动。
- 元数据已设置并复核：`sire_last_project=@CODE_ROOT@\\GAME`、`sire_last_run=R20260927-game-art-start`、`sire_last_status=DONE_WITH_ARCHIVE_BLOCKER`；元数据提交后 `PRAGMA integrity_check=ok`。
- 更正说明：工程路径依据用户指定的 `docs/COLLABORATION.md` §2.1 更新；SVG 本来已位于 `UNITY/Assets/Art/Concepts/`，此前文档和知识记录中的文件路径错误已修正。坐标/单位和武器 +Z 朝向现与 §3.2 一致。
