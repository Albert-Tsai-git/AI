# R7 验收清单（运行前登记）

| ID | 实际操作 | 预期 | 实际/证据/结论 |
|---|---|---|---|
| T1 | 从 Codex/Claude 别名读取 SKILL、合同并调用各别名的 sire_paths | 同物理目录、文件哈希和工作库/知识目录一致；含 v6.11 自动发现规则 | 待执行，validation.json |
| T2 | 检查两薄入口中文快速通道副本及数据库说明 | 同文副本且覆盖目录/环境变量、空文件、概念用法、兜底判定、退出条件；不存在 tracked 数据库旧描述 | 待执行，validation.json，独立 R6 |
| T3 | 按实际 hook 命令入口，在隔离遥测库送入 prompt/tool/stop JSON；运行 analyze/report | 两客户端均形成三事件、一任务，记录客户端名、full模式；静默 rc=0 | 待执行，validation.json；不代表客户端自动触发 |
| T4 | 按同入口送入畸形 JSON | 静默 rc=0，原事件/任务计数不变，不阻断主任务 | 待执行，validation.json |
| T5 | 两别名执行实际向量正常检索；执行阈值999的无命中边界 | 相同命中ID与工作库；边界空结果；数据库字节哈希不变 | 待执行，validation.json |
| T6 | R9 调用实际 pending、rsi-check，双库归档后查任务、知识、meta、integrity、FTS、emb | 无待处理发现、无shared源未登记修改；双库记录可查且完整 | 待执行，archive-result.json |
| T7 | 真实客户端新会话自动触发三个hooks | 需真实客户端事件证据 | BLOCKED-无法真实验证；没有可访问的原生客户端自动事件验收路径 |

当前对话已收到用户注入的更新版 Codex AGENTS；规则同步本身可验证。T7 是遥测运行时的验证限制，不能冒称 PASS。
