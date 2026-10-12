# R7 check list

| ID | Scenario and steps | Expected | Actual/evidence | Result |
|---|---|---|---|---|
| T1 | Normal route: execute the mechanical preference/run archive under the R4-approved low-cost model assignment. | Low-cost route completes bounded work and yields verifiable artifacts. | This R1 agent executed the task; H-005, run evidence, DB indexing/migration and backup outputs were created. | PASS |
| T2 | Boundary: inspect the shared contract for the single tiny-task case. | Tiny single-unit task stays with controller; no proxy delegation overhead. | `global-contract.md` model-selection gate explicitly says “极小任务，主控直接执行”; policy check only, no fabricated UI scenario. | PASS |
