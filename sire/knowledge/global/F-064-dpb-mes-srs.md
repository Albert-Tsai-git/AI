**日期**: 2026-10-13
**项目**: D:\code\mes
**关键词**: MES 需求规格说明书, DPB 定子工艺流程, 工艺版本, DOCX 图号, 需求追踪, MES-SRS-001

**需求场景 / 现象**: 将会议绘制的多版本制造流程图纳入综合 MES SRS，并同步生成包含流程图截图的 Word 版。

**根因**（问题类必填）: 两张同名产品流程截图显示的工序顺序和检查次数不一致；图中部分动作/失败门禁未定义，不能合并或擅自推导。

**方案 / 架构**: A/B 流程独立记录并保留原始图像，分别整理工序顺序、动作/数据、追溯需求、验收条件和待业务确认事项。与通用 MES 业务流程图区分编号。Markdown 作为内容基线；Word 内嵌三张由 Mermaid 图生成的静态图片及两张原始会议截图。静态 DOCX 检查确认全部 Markdown 内容、表格、需求编号和五张图片映射。

**关键文件与接口**:
- `docs/requirements/MES-综合需求规格说明书.md` — 统一需求基线，版本 0.9。
- `docs/requirements/MES-综合需求规格说明书.docx` — Word 排版版，五张流程截图/图示静态内嵌。
- `docs/requirements/assets/dpb-stator-process-a.png` — 用户提供的 A 流程原图。
- `docs/requirements/assets/dpb-stator-process-b.png` — 用户提供的 B 流程原图。

**实施步骤**:
1. 按截图分别摘录工序顺序，明确差异和图上未说明的动作/门禁为待确认。
2. 增加唯一需求/验收编号和追踪关系，在版本历史中登记 0.9。
3. 生成 DOCX 并把 Mermaid 源图作为图片插入，保持图号连续。

**验证方法**: `validate_srs.py`: issues=[]、13 张 Word 表格、5 张图片、105 个需求编号；`content_coverage.py`: missing source text lines/cells: 0。独立结构复核确认 0.9 版本行和图 3-2/3-3 位置正确。页面渲染未能执行：环境无 Word、LibreOffice、WPS 或连接的文档会话；视觉分页/裁切仍待真实检查。

**踩坑**: 更新 Markdown 后需重新构建 DOCX；最初 DOCX 没有 0.9 版本历史行，且 DPB 图号不连续。修正 Markdown 并重新构建后，独立复核通过。不要把静态结构检查当作全页视觉验收。

**状态**: 部分完成（交付物与结构验收完成；页面视觉验收受环境限制）
