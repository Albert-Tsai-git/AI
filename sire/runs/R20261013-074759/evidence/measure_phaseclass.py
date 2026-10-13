"""基线度量：用新旧 PHASE_PATTERNS 分别重算每个任务的阶段耗时，比较 CLOSE_HEAVY / FAST_SCOPE 命中数。

用法：python measure_phaseclass.py old|new
不改动生产遥测库，只读；判定逻辑与 sire_telemetry.detect() 中这两条规则一致。
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

DB = Path(r"D:\sire\AI\AI\sire\data\sire_telemetry.sqlite3")
CLOSE_PHASES = ("ledger", "archive", "rsi", "commit")
FAST_FORBIDDEN = ("retrieve", "ledger", "archive", "rsi", "subagent", "commit")

OLD = (
    ("rsi", r"sire_rsi\.py|sire_supervisor\.py|sire_telemetry\.py\W+(pending|resolve|report)"),
    ("retrieve", r"sire_kb\.py\W+(search|show|database-search|search-database)|sire_vector_db\.py\W+(search|show|stats)"),
    ("archive", r"sire_kb\.py\W+(reindex|add|next-id|export-md|lint)|sire_vector_db\.py\W+(index|migrate)"
                r"|sire_db_backup|snapshot_db|knowledge[\\/]+global|archive[_-]?(db|root|result)"),
    ("ledger", r"sire_run\.py|[\\/]runs[\\/]|[\\/]\.sire[\\/]"),
    ("commit", r"\bgit\W+(add|commit|push)\b"),
    ("rules", r"skill\.md|global-contract\.md|[\\/]references[\\/]+[\w-]+\.md"),
)
NEW = (
    ("rsi", OLD[0][1]),
    ("retrieve", OLD[1][1] + r"|knowledge[\\/]global"),  # 读知识库文件属检索，不属收尾
    ("archive", r"sire_kb\.py\W+(reindex|add|next-id|export-md|lint)|sire_vector_db\.py\W+(index|migrate)"
                r"|sire_db_backup|snapshot_db|SIRE_ARCHIVE_(ROOT|DB)"),
    ("ledger", r"sire_run\.py|(journal\.log|run\.json|units\.json|blockers\.md|assumptions\.md|kb-hits\.md"
               r"|stage-output|\.sire[\\/]current)"),
    ("commit", OLD[4][1]),
    ("rules", OLD[5][1]),
)


def classify(tool: str, detail: str, patterns) -> str:
    if (tool or "").lower() in {"agent", "task"}:
        return "subagent"
    text = (tool or "") + " " + detail
    for phase, pat in patterns:
        if re.search(pat, text, re.I):
            return phase
    return "execute"


def main():
    use_new = sys.argv[1] == "new"
    patterns = NEW if use_new else OLD
    c = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    tasks = c.execute("SELECT * FROM tasks ORDER BY end_ts").fetchall()
    events = c.execute("SELECT * FROM events ORDER BY ts, id").fetchall()
    by_session: dict[str, list] = {}
    for e in events:
        by_session.setdefault(e["session"], []).append(e)

    close_hits = fast_hits = 0
    ledger_seconds = archive_seconds = 0.0
    for t in tasks:
        total, mode = t["total_s"] or 0, t["mode"]
        sec: dict[str, float] = {}
        calls: dict[str, int] = {}
        last = t["start_ts"]
        for e in by_session.get(t["session"], []):
            if not (t["start_ts"] <= e["ts"] <= t["end_ts"]) or e["event"] == "prompt":
                continue
            phase = "reply" if e["event"] == "stop" else classify(e["tool"], e["detail"] or "", patterns)
            sec[phase] = sec.get(phase, 0.0) + max(0.0, e["ts"] - last)
            last = e["ts"]
            if e["event"] == "tool":
                calls[phase] = calls.get(phase, 0) + 1
        ledger_seconds += sec.get("ledger", 0)
        archive_seconds += sec.get("archive", 0)
        if mode != "fast" and total >= 180:
            close = sum(sec.get(p, 0) for p in CLOSE_PHASES)
            if close / total >= 0.4:
                close_hits += 1
        if mode == "fast" and any(calls.get(p) for p in FAST_FORBIDDEN):
            fast_hits += 1
    print(json.dumps({"variant": "new" if use_new else "old", "tasks": len(tasks),
                      "CLOSE_HEAVY命中": close_hits, "FAST_SCOPE命中": fast_hits,
                      "ledger累计秒": round(ledger_seconds), "archive累计秒": round(archive_seconds)},
                     ensure_ascii=False))
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
