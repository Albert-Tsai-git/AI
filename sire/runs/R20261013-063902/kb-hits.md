# G0 知识检索记录

**检索词**: `RSI 遥测 自我审查 自动优化`（sire_kb.py search）、`RSI 自我审查 遥测 阶段耗时 误报 自动优化`（sire_vector_db.py search）、`RSI 遥测 阶段耗时 误报`（sire_kb.py search --run，回执 R20261013-063902）

**判定**: 部分可参考（RSI 门禁与双库写入已有已验证记录，遥测自动发现的实际存活面与检测精度无记录）

## 命中与复用决定

| 记录 | 得分 | 内容 | 复用决定 |
| --- | --- | --- | --- |
| P-20260925 | 0.707 | RSI 规则曾是孤岛，改由 R9 `rsi-check`/`finalize` 门禁兜底；限制已写明"门禁把最后提交后任一未失败提案视为已登记，无法证明提案与 diff 对应"、"`evaluate` 只支持越高越好" | 复用为流程/精准度两项结论的既有依据，实测确认两条限制仍未修 |
| E-010 | 0.664 | v6.11 遥测上线，状态标注"真实客户端自动遥测事件触发未实测"，限制写"钩子配置和脚本成功不能证明真实客户端会自动触发" | 用遥测库实际数据（claude 187 / codex 355 条事件）落地该未决项：Codex 侧真实在跑，Claude 侧已断流 |
| E-008 | 0.615 | RSI 双库写入顺序与归档库解析要求（`SIRE_ARCHIVE_ROOT`/`SIRE_ARCHIVE_DB`） | 复用：本轮 propose/evaluate/activate 按该做法执行，未出现分叉 |
| global-contract.md §RSI | 0.594 | 钩子三事件、后台 analyze、R9 pending 处理一条、`自动优化：` 输出行 | 作为"应然"基准与实测对照得出偏差 |
| self-optimization.md §5.1/5.2 | 0.583 | 提案→基线→独立评估→版本化激活→观测→回滚；OPEN→PROPOSED→FIXED/REGRESSED/IGNORED | 复用为门禁审查条款 |

## 缺口（知识库未覆盖，本轮归档进 P-20260931）

1. 遥测采集的实际存活面（哪个客户端在写、何时静默断流）无记录。
2. `mode=unknown` 占比（实测 51%）及其对检测规则的分桶污染无记录。
3. `classify`/`PHASE_PATTERNS` 阶段误分类与 `tool_failed` 近失效无记录。
4. `sire_telemetry.py resolve` 不校验提案存在性与状态无记录。
