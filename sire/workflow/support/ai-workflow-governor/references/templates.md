# AI Workflow Governor：记录模板

以下模板是最小字段集合。可以扩展，但不能删除能证明闭环的字段。

## 任务总账

```yaml
task_id: TASK-YYYYMMDD-###
title: ""
scope:
  in: []
  out: []
risk: low|medium|high|critical
roles:
  orchestrator: ""
  knowledge_curator: ""
  requirement_analyst: ""
  decomposer: ""
  requirement_reviewer: ""
  integrator: ""
status: INTAKE
kb_check_id: KB-###
requirements: [REQ-001]
units: [UNIT-001]
decisions: []
blockers: []
integration_evidence: []
knowledge_entries: []
```

## KB-Check

```yaml
kb_check_id: KB-###
scope: "搜索了哪些目录、仓库、历史任务或外部来源"
queries: []
matches:
  - source: "绝对路径、任务 ID 或 URL"
    relevance: high|medium|low
    status: reusable|adaptable|reference-only|not-applicable
reuse_decision: reuse|adapt|new|avoid
reason: ""
gaps: []
checked_by: Knowledge Curator/Indexer
checked_at: "YYYY-MM-DD"
```

## REQ 需求项

```yaml
req_id: REQ-001
statement: "可观察的用户/业务结果"
intent: "为什么需要"
constraints: []
non_goals: []
inputs: []
acceptance:
  - id: AC-001
    criterion: ""
    evidence_type: artifact|test|source|inspection|approval
risk: ""
open_decisions: []
derived_from: "用户请求或既有决策"
review: pending|passed|rejected
```

## UNIT 执行单元

```yaml
unit_id: UNIT-001
req_ids: [REQ-001]
objective: "一个主要、可验证的结果"
owner_role: Executor
inputs: []
outputs: []
dependencies: []
parallel_safe: true
approach: ""
acceptance_ids: [AC-001]
review_method: "由谁检查什么"
test_plan:
  command_or_steps: []
  expected: ""
recovery: "失败时如何回滚或换策略"
status: READY
artifact: "绝对路径或外部资源标识"
```

## 复核记录

```yaml
review_id: REVIEW-###
unit_id: UNIT-001
reviewer_role: Work Reviewer
independent_of_executor: true
scope_checked: []
findings: []
verdict: passed|failed|needs-input
evidence: []
remediation_id: null
```

## 测试记录

```yaml
test_id: TEST-###
unit_id: UNIT-001
tester_role: Functional Tester/Validator
checks:
  - step: "命令、输入或检查动作"
    expected: ""
    actual: ""
    result: passed|failed|skipped
evidence: []
verdict: passed|failed|needs-environment
failure_class: none|implementation|requirement|environment|permission|data
```

## Remediation

```yaml
remediation_id: REM-###
unit_id: UNIT-001
attempt: 1
defect: "复核或测试观察到的问题"
root_cause_hypothesis: ""
change_made: ""
strategy_changed: true|false
rerun_review: REVIEW-###
rerun_test: TEST-###
result: resolved|repeated|blocked
next_action: ""
```

## 人工决策包

```yaml
decision_id: DEC-###
blocker: "不能安全推断的具体问题"
why_human_input_is_required: "权限、业务取舍或高影响风险"
options:
  - option: A
    impact: ""
  - option: B
    impact: ""
recommendation: A
exact_input_needed: ""
independent_work_continues: []
```

## 知识条目

```yaml
knowledge_id: KB-SOL-###
title: "可被未来搜索命中的标题"
type: decision|solution|failure|test-pattern|reference
context: "何时适用"
problem: ""
solution_or_decision: ""
constraints: []
verification: []
limitations: []
tags: []
source_artifacts: []
related_tasks: []
updated_at: "YYYY-MM-DD"
```

## 最终关闭清单

```text
[ ] 已完成 KB-Check，且说明了复用/不复用理由
[ ] 每个 REQ 有验收标准和至少一个 UNIT
[ ] 拆分已由 Requirement Reviewer 通过
[ ] 每个 UNIT 都有产物、独立复核证据和功能测试证据
[ ] 失败单元有 remediation，未重复无效策略
[ ] 并行 lane 的冲突和依赖已处理
[ ] 集成/端到端验证通过
[ ] 权限和外部副作用均在授权范围内
[ ] 可复用知识已创建并进入索引
[ ] Closure Auditor 已确认无遗漏需求
```
