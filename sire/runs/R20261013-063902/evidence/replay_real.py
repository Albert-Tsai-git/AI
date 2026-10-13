"""用真实 detect() 重放历史任务，核对修复后各规则命中数（评估指标与回归无副作用）。"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts")
import sire_telemetry as t  # noqa: E402

DB = Path(r"D:\sire\AI\AI\sire\data\sire_telemetry.sqlite3")
c = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
tasks = c.execute("SELECT * FROM tasks ORDER BY end_ts").fetchall()
rules = Counter()
outlier_detail = []
for i, task in enumerate(tasks):
    history = [h for h in tasks[:i] if h["analyzed"]]
    for fid, rule, evidence in t.detect(task, history):
        rules[rule] += 1
        if rule == "PHASE_OUTLIER":
            outlier_detail.append([task["task_id"][:14], task["mode"], evidence])
print(json.dumps({"tasks": len(tasks), "rules": dict(rules), "outlier": outlier_detail},
                 ensure_ascii=False, indent=1))
c.close()
