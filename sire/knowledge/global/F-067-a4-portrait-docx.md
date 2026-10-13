**日期**: 2026-10-13
**项目**: D:\code\mes
**关键词**: DOCX, A4, portrait, python-docx, section geometry, image scaling

**需求场景 / 现象**: 用户要求 MES 需求规格说明书 Word 中所有页面保持 A4 纵向，包括流程图页面。

**根因**（问题类必填）: DOCX 构建脚本为宽幅图新增横向 section，并将纸张尺寸设为近似英寸值；既有输出文件又被本机另一进程锁定，无法原位覆盖。

**方案 / 架构**: 通过 python-docx 将每个 section 固定为精确 210×297 mm，删除横向 section，并把图像最大宽度和高度限制在纵向页面版心内。原文件被锁时，生成独立 A4 纵向 DOCX，待关闭占用文件的应用后再替换。

**关键文件与接口**:
- `D:\code\mes\.sire\runs\R20261013-140114\build_srs_docx.py` — `add_section`/`add_figure` 页面设置与图像缩放。
- `D:\code\mes\docs\requirements\MES-SRS-A4-Portrait.docx` — A4 纵向输出。

**实施步骤**:
1. 对所有 Word 节设定 210×297 mm 与 portrait。
2. 所有流程图以版心宽高上限等比缩放。
3. 验证各节尺寸、需求编号、表格和嵌入图像。

**验证方法**: 6 个 section 全部为 A4 纵向；DOCX 结构检查 issues=[]、13 张表、5 张图片、105 个需求编号；Markdown 内容覆盖缺失 0。页面视觉效果未渲染验证。

**踩坑**: DOCX 原文件被另一个进程打开时无法删除或覆盖；应保留另存输出，待用户关闭占用后再替换。

**状态**: 部分完成（新文件完成，原路径被占用且视觉验证待完成）
