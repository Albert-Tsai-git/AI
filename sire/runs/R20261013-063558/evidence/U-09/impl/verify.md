# U-09 实现自测
- 检索验收脚本：evidence/verify_index.py（现场重跑，输出存 u09-retrieval.md）
- 七组问法逐组判定，命中 PASS 行数 = 15（向量 7 组 + 关键词 7 组）
- 脚本总判定：PASS
- 新旧对比：泛化问法「driverSoftware 仓库 架构 入口」前 5 命中的是工作区级 map（K-CODEBASE-MAP / K-26b560f247dd / F-019），旧摘要 K-REPO-DRIVERSOFTWARE-20260924 已跌出前 5；七条新记录各自的子系统问法全部第 1（0.87~0.99）。
