# Retrieval receipts and reuse decision

R1 initial attempt: Markdown search used a not-yet-created receipt path and correctly warned that no receipt was recorded. Corrected run directory was created and both searches were rerun successfully.

- Markdown query `模型分级 低成本 token 模型选择简单任务 archive`: 7 hits, including E-008 (shared SIRE single-source/archive flow) and F-028 (knowledge retrieval system); model-tiering rules are already in the shared contract.
- Vector query `用户偏好 按复杂度选择模型 简单任务低耗模型 当前 Codex gpt-6-luna low`: returned shared contract and SIRE knowledge/database records.
- Decision: reuse the existing global model-selection gate; add only the stable user preference and this run's actual model-routing fact. No workflow source change.
- Gap: no equivalent preference existed in `global_dev_habits.md`; H-005 was added.
