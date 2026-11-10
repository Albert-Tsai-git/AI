**日期**: 2026-10-26
**项目**: D:/code/GAME
**关键词**: Unity切面室内, FC旅店, procedural room builder, collider-free art, spawn clearance, 端柱净宽, scene root cleanup

**需求场景 / 现象**: 在既有Unity俯视角色扮演游戏中，按参考图扩展一间切面旅店：木地板、锈蚀钢板、左右客房与前厅，外门廊对齐场景入口；需要改善可读性，同时避免改动旅店传送和住宿玩法。

**根因**（问题类必填）: 不适用；属于现有程序化房间美术扩展。

**方案 / 架构**: 将新房间几何、材质和纹理限定在单一美术Builder中，挂到专用scene art root，并由root生命周期释放资源。保持Portal/Spawn及住宿服务的水平坐标与行为不变；明确既有TerrainHeight仅调整Y并予以保留。门框、门扇、装饰栏杆与门廊铺面不参与碰撞，实际可走宽度需扣除端柱占用，而不是只比较栏段中心位置间距。

**关键文件与接口**:
- `UNITY/Assets/Scripts/Presentation/FC/FcRadoInnArtBuilder.cs` — `BuildRoom`、`BuildExterior`、`RoomPartitions`、`OnDestroy`。
- `UNITY/Assets/Scripts/Presentation/FC/FcWorldBuilder.cs` — `AlignLogicSpawnsAndTriggers`是既有贴地行为，本类美术变更不应改动其水平坐标/路由。

**实施步骤**:
1. 先写清单元写集和玩法边界，只触碰房间美术Builder。
2. 以墙段间距确定门洞，再将门框/门扇放入门洞并计算最窄内沿净宽；确认装饰Collider关闭。
3. 用实际端柱内沿检查外廊通道宽度，并核对入口与Spawn水平位置对齐。
4. 检查桌椅与出生点净距、床/柜相交、生成对象root归属及Material/Texture释放。
5. 先完成静态坐标与代码审查；运行时画面、性能和构图需要单独授权后确认。

**验证方法**: 本次静态审查确认门洞净宽约1.68m、门廊端柱内沿净宽约2.98m、圆凳至出生点外缘约1.034m，静态对象估算486个；R6A/B/C独立审查及交叉复核通过。未运行Unity、构建或测试，因此数值和构图仍需在授权后的运行时画面确认。

**踩坑**: 前栏两段的中心端点看似留有2.8m间隙，但端柱各向通道内伸0.06m，实际仅2.68m。要按端柱内沿计算，并把侧栏角柱与前栏端柱明确对齐；修改几何后也同步更新自检与评审报告，避免旧静态数字和新代码并存。

**状态**: 已完成静态实现与独立复核；运行时视觉/性能验证待授权。
