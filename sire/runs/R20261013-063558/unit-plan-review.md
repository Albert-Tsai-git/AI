# R4 计划复核（独立代理，两轮）

## 第 1 轮：结论 FAIL（6 处）
1. U-01/U-04 状态机与内圈零位双写；U-02 通信与 U-01 endpoint 重叠；Electron 打包与构建重叠。
2. wave 1 多单元同写 75KB md，`next-id F` 并发撞号（撞号后变 `F-0NN#2`）→ 必须改顺序依赖链。
3. verify 缺脚本全路径与 cwd；`sire_kb.py lint` 无 ID 过滤；向量 hits 无 record_id，只能匹配 title/content。
4. `sire_vector_db.py --db` 是全局项，必须放子命令前。
5. 旧 `K-REPO-DRIVERSOFTWARE-20260924`（v0.13.11 摘要）不会被索引流程更新，可能继续抢 Top5 → 需取代标注与新旧对比断言。
6. 缺"备份文件存在"断言。
遗漏：运行形态与环境变量、新加协议命令链路、自验路径（可见 UI / 真实数据流 / 真机台账）。

## 第 2 轮（修订后 9 单元）：结论 FAIL（还差 6 处）
- 上轮已落地：串行依赖链、`--db` 前置、备份断言、边界基本互斥（U-02 内圈零位 vs U-06 卸力建零经核 `/api/offline-detection/*` 与 `/api/calibrate/inner_zero` 分离，不双写）。
- 仍差：
  1. `sire_kb.py load_records` 是**数据库优先**（实测库 149 / md 40），未 index 时 `show <新ID>` 必返 "未找到记录" → U-01..U-07 自验要改成 grep md 记录块。
  2. U-02..U-09 路径写成 `...\sire_kb.py` 或裸文件名且无 cwd；U-08 用 `sqlite3` CLI（不在 PATH）；U-09 未列 6 组查询词与标题串。
  3. 新记录正文需标注"取代 K-REPO-DRIVERSOFTWARE-20260924"，U-09 加新旧对比断言。
  4. "四段齐全"要写进断言（lint 无 ID 过滤）。
  5. U-04 与 U-05 就"前端随 server.dist 走"定唯一归属。
  6. skill 文件数是 13 不是 12；自验三条要列入 U-07 accept。

## 修复落地核对（主控机械核对，命令均实跑）
- ① grep md 记录块取代 `show`；② 全路径 + cwd 已写进 U-01..U-09 verify，U-08 改 `python` 单行连库；③ 取代标注写进每条记录正文（见 U-09 新旧对比断言）；
- ④ 每条 verify 断言四个段名；⑤ 该事实唯一归属 U-05，U-04 只留一行指向；⑥ U-07 改 13 并纳入自验三条。
- 实测数字：`ls docs/skills/*.md`=13、`ls frontend/js/pages/*.js`=13、`ls core/*.py`=39、`ls tests/unit/test_*.py`=244、`grep -h '^def test_'` 合计 2236、`grep -c '^@app\.' server.py`=160、`tests/unit/test_od_*.py`=11、CHANGELOG [未发布] 条目 23（变更 13 / 新增 6 / 修复 4）、`wc -l server.py`=11178。
- 编号基线：`sire_kb.py next-id F` = **F-053**；入库前 knowledge_records=148、chunks=7688、keywords=24866、task_records=2790、integrity_check=ok。

## 结论
6 处修复逐项落地，9 单元字段与措辞均可过 `cmd_add_units`（accept 含「应」、无 UNTESTABLE/WEAK_VERIFY 词、owner 全 R5、deps 闭环无环）。G3 放行。
