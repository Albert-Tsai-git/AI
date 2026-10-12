# 模型选择与执行台账

- R0：目标=Claude 侧按任务难度选择低成本模型；用户授权“Codex 已完善则直接对齐执行”。
- R1：sire_kb search 命中 H-005；向量检索命中 global-contract.md §模型选择门禁、SIRE-MIGRATION.md 变更记录。RSI-20261010-MODELGATE 状态 ACTIVE。决策：复用，不改工作流源。
- R2/R3：两单元。U1 写本台账；U2 双库归档。
- R4：PASS（主控）。
- 模型选择门禁：
  - U1 / 低 / 主控 Opus 5.5 / 极小单元，主控直接执行（内容需主控判断，派工冷启动不划算）
  - U2 / 低 / haiku（sire-low）/ 既定命令 + 机械核对 + 有备份可回滚
  - R6/R8/R9 / 高 / 主控 Opus 5.5 / 契约规定最终裁决不降级
- Claude 侧映射核对：sire-low=haiku+low，sire-mid=opus+low，sire-high=opus+high，与契约表一致。
- 发现（不在本次修复范围，报告用户）：sire-low/mid/high 三个子代理文件只在 ~/.claude/agents/ 本地，未像其它角色文件那样链接到共享源 agents/claude/，换机/从 Git 恢复时不会自动出现。
- R10：跳过，无 UI/原生应用操作。
