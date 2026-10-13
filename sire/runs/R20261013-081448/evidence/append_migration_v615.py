from pathlib import Path

row = ("| 2026-10-13 | R20261013-081448（续） | RSI 闭环强制化：`sire_run.py finish` 新增 `telemetry_pending_gate`"
       "（未处理 pending 即 BLOCKED，`--pending-note` 显式移交并写 `pending-check.json`）；`sire_telemetry.py` 新增 "
       "`COLLECTION_DEAD` 规则与 `expected_clients()`/`check_clients()`（从三端配置反推应在采集的 client，"
       "`SIRE_CLIENT_CONFIGS` 可覆盖，`analyze --stale-hours` 默认 12 小时，30 分钟去重，只对「采过又哑了」的客户端报警）；"
       "`sire_qoder.py` 增加 `entry-file` 生成 `~/.qoder-cn/AGENTS.md` 薄入口（install 自动写、uninstall 只删自己生成的）；"
       "SKILL.md、global-contract §RSI 第 3-5 条、self-optimization §5.2、agents/qoder/README 同步；"
       "RSI-20261013-RSILOOP → v6.15 | 隔离遥测库 + 临时项目跑真实 CLI：存活自检 4 断言 PASS（claude 36 小时无事件→"
       "直接 PROPOSED 并进 pending；qoder 心跳正常不误报；连跑两次 analyze 不重复计数）；收尾门禁三态 PASS"
       "（BLOCKED rc=1 → resolve 后 rc=0 → `--pending-note` 移交 verdict=HANDED_OFF）；生产 pending 空、rsi-check PASS |\n")
p = Path(r"D:\sire\AI\AI\sire\knowledge\global\SIRE-MIGRATION.md")
text = p.read_text(encoding="utf-8")
if "RSI-20261013-RSILOOP" in text:
    print("迁移文档已有该记录，跳过")
else:
    p.write_text(text.rstrip() + "\n" + row, encoding="utf-8")
    print("迁移文档已追加 v6.15 行")
