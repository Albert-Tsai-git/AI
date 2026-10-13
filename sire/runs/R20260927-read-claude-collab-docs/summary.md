# Claude × Codex 协作约定摘要

来源：`D:/code/GAME/docs/COLLABORATION.md` v0.2（2026-09-27）。本文只摘录项目约定，不替代原文。

## 职责边界

- Claude 负责玩法机制、运行时逻辑、数据结构、CSV 导入和逻辑测试。
- Codex 负责 Blender/模型、美术资源、Unity 工程/渲染设置、场景搭建和美术导入设置。
- GDD 共同维护，机制章节以 Claude 为主，美术/环境章节以 Codex 为主；设计决策由用户确认。

## 路径与所有权

- 仓库根 `D:/code/GAME` 不是 Unity 工程；Unity Hub 应打开 `D:/code/GAME/UNITY`。`docs/` 留在仓库根。
- Unity 内的相对路径（例如 `Assets/`、`Data/`）均以 `UNITY/` 为根。`.blend` 源文件建议放在根目录 `ArtSource/`（新建顶层目录须先登记）；导出 FBX 放 `UNITY/Assets/`。
- `Assets/Scripts/`、CSV 数值与导入器归 Claude；`Assets/Art/`、`Assets/Models/`、`Assets/Materials/`、`Assets/Prefabs/`、`Assets/Scenes/`、`Assets/Settings/` 与 Unity 工程配置归 Codex。
- ScriptableObject 数值由 Claude 维护，`modelPrefab` 美术引用由 Codex 维护；CSV 重导会保留 `modelPrefab`，但部件类型变化会删建资产并丢引用，Claude 改类型前须登记。

## 资产接口和交接

- 挂点按 `Data/parts.csv` 的 `mounts` 列为准，节点名称精确为 `Mount_Main`、`Mount_Sub`、必要时 `Mount_SE`；新增类型由 Claude 先加数据，再由 Codex 加节点。
- 武器枢轴对齐挂点，本地炮口朝 +Z；单位 1 = 1 米，Unity 使用 Y-up；导出前应用变换，Prefab 根 Transform 为单位变换。
- 场景常量 `Field`、`Battle` 由代码消费：Codex 管 Build Settings，Claude 同步代码常量。逻辑组件由 Codex 摆放，Claude 在接入说明里提供组件、参数和引用。
- 每次交接列出新增脚本/组件、数据 ID、需要的挂点/资源或 Prefab、场景对象、标签/Layer、`modelPrefab` 和渲染/包设置变动。双方不在对方未确认前宣称联调通过。

## 当前关联项

- 待确认 Unity Hub 是否已切换到 `UNITY/`；文档称这项仍待用户确认。
- 轻型/重型底盘挂点仍待 Codex 制作。
- 本轮按约定确认实际工程文件存在于 `UNITY/`，并修正了先前 ART_BIBLE 中的概念文件链接及“缺少 Unity 工程结构”的错误说明；没有修改 `docs/COLLABORATION.md` 本身。
