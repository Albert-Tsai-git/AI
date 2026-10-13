"""RSI 自审证据：对历史任务重放 PHASE_OUTLIER 检测，统计新旧判定的命中数。

用法：python replay_outlier.py old|new
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from pathlib import Path

SCRIPTS = Path(r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts")
sys.path.insert(0, str(SCRIPTS))
import sire_telemetry as t  # noqa: E402

DB = Path(r"D:\sire\AI\AI\sire\data\sire_telemetry.sqlite3")
CATCH_ALL = ("execute", "reply")


def detect_outlier(task, history, mode_new):
    data = json.loads(task["phases"] or "{}")
    sec = data.get("seconds", {})
    total, mode, hits = task["total_s"] or 0, task["mode"], []
    for phase, value in sec.items():
        if mode_new and (mode == "unknown" or phase in CATCH_ALL):
            continue
        if value < 120:
            continue
        past = [json.loads(h["phases"] or "{}").get("seconds", {}).get(phase, 0)
                for h in history if h["mode"] == mode]
        past = [v for v in past if v > 0]
        if len(past) >= 5 and value > 3 * statistics.median(past):
            hits.append((phase, round(value), round(statistics.median(past)), mode))
    return hits


def main():
    new = sys.argv[1] == "new"
    c = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    tasks = c.execute("SELECT * FROM tasks ORDER BY end_ts").fetchall()
    all_hits = []
    for i, task in enumerate(tasks):
        history = [h for h in tasks[:i] if h["analyzed"]]
        all_hits += [(task["task_id"], h) for h in detect_outlier(task, history, new)]
    by_phase = {}
    for _, (phase, value, med, mode) in all_hits:
        by_phase.setdefault(phase, []).append((value, med, mode))
    print(json.dumps({"variant": "new" if new else "old", "tasks": len(tasks),
                      "hits": len(all_hits),
                      "by_phase": {k: len(v) for k, v in by_phase.items()},
                      "unknown_mode_hits": sum(1 for _, (_, _, _, m) in all_hits if m == "unknown"),
                      "detail": [[tid[:14], *h] for tid, h in all_hits]},
                     ensure_ascii=False, indent=1))
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
