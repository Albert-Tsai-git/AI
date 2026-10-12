# G0 知识检索回执

RUN: R20261013-063558 · 项目: driverSoftware2 · 日期: 2026-10-13
工具: `sire_kb.py search` × 4 + `sire_vector_db.py search` × 1（日志见 `kb-search.log` / `vector-search.log`）

## 检索词与命中

| 检索词 | 主要命中 | 判定 |
|---|---|---|
| driverSoftware 仓库 架构 模块 | F-019, F-020, F-024, K-CODEBASE-MAP-20260924, K-26b560f247dd | reference-only（流程/发布规范可参考，架构地图缺失） |
| driverSoftware 后端 core reader 模块 架构 入口（向量） | **K-REPO-DRIVERSOFTWARE-20260924**(0.75), F-019 | adapt（该记录是 2026-09-24 基线 v0.13.11 / 分支 feature/offline-detection-dev，已过时 20 个版本） |
| 下线检测 状态机 坏点 额定扭矩 | F-052（信息确认人工决定/订单号） | reference-only（只覆盖一条交互细节，无功能全貌） |
| RS485 协议 reader HID 波特率 固件档案 | K-servo-fw-host-compatibility-register-read, knowledge:why-reg-read-fails, H-004 | reuse（兼容性事实与排查纪律仍有效，可直接引用） |

## 总体判定

**部分可参考** — 流程规范与硬件兼容性事实**已实现过**（F-019/F-024/H-004/K-servo-fw-host-compatibility 直接引用）；"仓库模块级架构地图 + 索引"这一项是**全新需求**（唯一仓库级记录停在 v0.13.11，无文件级入口）。

## 可复用结论

- 发布/分支/打包规范：F-019、F-024 已覆盖，本次不重写，只做与现状对齐的必要补充。
- 硬件排查纪律：H-004 生效中；军规 12（符号名+字面量双搜）、军规 9（档案门控静默回退）与之重复的部分不再抄。
- 寄存器兼容性事实（固件 v3.4.5 各波特率单帧上限 3/8/13/16）：沿用 K-servo-fw-host-compatibility-register-read。

## 缺口（本次要补的）

1. **没有 driverSoftware2 的模块级架构地图**：唯一的仓库级记录 K-REPO-DRIVERSOFTWARE-20260924 是单段摘要，无文件/行号级入口，且基线停在 v0.13.11。当前 0.16.1、下线检测已扩成多条子功能。
2. **前端页面地图缺失**：pages/*.js 各页职责、页面注册/路由机制、发帧循环（await 链替代定时器）没有可检索条目。
3. **测试与门禁地图缺失**：pytest 布局、CI job、源码扫描门禁脚本清单没有条目；军规 3/4 是原则，不是"这个仓具体有哪些门禁"。
4. **构建发布落地细节缺失**：F-019/F-024 讲了规范，`scripts/build.bat` 步骤顺序、`release.py` 实际动作、SKU 区分没有可检索记录。
5. **文档→改动映射缺失**：AGENTS.md 的"改哪个模块必读哪个 skill"是表格式引用，但知识库里没有"这条功能的实现在哪几个文件"的反向索引。

## 入库机制选择（已核）

- `sire_vector_db.py sync_knowledge_records` 只从 `knowledge/global/global_dev_{features,efficiency,habits}.md` 与 `global_problem_solutions.md` 解析 `### [FPEH]-NNN:` 头（脚本 431-483 行）；`K-REPO-*` 那批 50 条是 2026-09-24 一次性直写数据库的产物，不会再被索引流程更新。
- 因此本次走**受支持路径**：新增 F 记录 → `sire_kb.py reindex` → `sire_vector_db.py index`（内部会 backup、chunks+FTS、sync_knowledge_records、sync_keywords、`sire_knowledge_index.post_index` 语义向量与关键词补全）。不改 `workflow/shared/sire/`，不触发 RSI。
- 不把整仓源码切片塞进共享库：`source_paths()`（118-147 行）只收 SIRE 知识/工作流/任务台账，且该库是多项目共用的 210MB 全局库，塞源码属机制变更。
