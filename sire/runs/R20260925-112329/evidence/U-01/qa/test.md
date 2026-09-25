VERDICT: PASS
# U-01 R7 功能测试（最终版代码，R5 按 R6 意见修改后重跑）
早期一次运行因脚本解析 JSON 出错中断，未形成结论；以下全部基于最终版本，无作废结论。
环境：库副本放在 scratchpad/r7-sync（A=repo data 库副本，B=D:/sire 库副本），SIRE_DB_BACKUP_DIR 指向临时目录；运行前后两个真实库 sha256 一致（[REAL] OK）。

| 编号 | 步骤 | 预期 | 实际 | 结论 |
|---|---|---|---|---|
| T1 | 清空 ARCHIVE 环境变量，不传 --repo-only，执行 propose | 拒绝，两副本不变 | rc!=0，提示“未解析到归档库”；sha256 不变 | PASS |
| T2 | --db A --archive-db B propose | 两库都有记录，created_at 相同；归档库排在前面 | databases=[B,A]；created_at 均为 03:26:04.906251 | PASS |
| T3 | 先 evaluate，再 activate | 两库 status/metrics/workflow_versions 一致 | EVALUATED_PASS 一致；metrics 行一致；versions 全表一致，vT2 为 ACTIVE | PASS |
| T4 | 只在 A 上执行 --repo-only evaluate 后再 activate（正反两种顺序） | 拒绝，两库 sha256 不变 | 两次 rc 均!=0，sha256 不变 | PASS |
| T5 | 对 status 执行前后比较；库不存在；空库 | 哈希不变，无边车文件；返回空列表 | 目录仍只有 A/B，哈希不变；不存在的库返回 []，且没有新建；空库返回 [] | PASS |
| T6 | dest 有 source 缺失的 RSI-T6-ONLY；补齐 source；dest 不存在 | 依次为：RuntimeError 且不变；成功；成功 | 报 RuntimeError，指出缺失 RSI-T6-ONLY，dest/manifest 的 sha256 不变；补齐后发布成功；新 dest 发布成功 | PASS |
| T7 | 分别设置 SIRE_ARCHIVE_ROOT、SIRE_ARCHIVE_DB，以及都不设置 | 依次为 <root>/sire_vectors.sqlite3、DB 优先、None | 符合 | PASS |
| T8 | rsi-check；bundle --dry-run；检查 ~/.codex/skills | PASS；包含 support/ai-workflow-governor，不包含 references/governor；只剩 ai-dev-sire-workflow 和 .system，备份存在 | status=PASS，命中 RSI-20260925-SYNC；support 命中 8 次，references/governor 命中 0 次；目录与备份均符合 | PASS |
| T9 | 对同一 ID 重复 propose | 拒绝，两库不变 | rc!=0，sha256 不变 | PASS |
| T10 | dest 是文本文件，执行 snapshot_main | 报错拒绝，dest 不变 | RuntimeError "destination is not a supported SQLite database"；dest 不变，也没有生成 manifest | PASS |

证据：同目录 output.log（含脚本全文和完整输出）。
