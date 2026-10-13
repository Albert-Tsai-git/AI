"""R7 真实场景测试：在隔离遥测库上造事件，跑真实 analyze/pending 路径验证 PHASE_OUTLIER 修复。

T1 正常路径：full 任务 execute=600s（远超历史中位数）→ 不应再产生 PHASE_OUTLIER 发现
T2 能力保留：full 任务 archive=300s（真实收尾阶段离群）→ 连中 2 次后应转 PROPOSED 并被 pending 列出
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts\sire_telemetry.py"
TMP = Path(os.environ.get("TEMP", "/tmp")) / "sire_rsi_r7.sqlite3"
for suffix in ("", "-wal", "-shm"):
    p = Path(str(TMP) + suffix)
    if p.exists():
        p.unlink()
ENV = {**os.environ, "SIRE_TELEMETRY_DB": str(TMP)}
os.environ["SIRE_TELEMETRY_DB"] = str(TMP)

sys.path.insert(0, r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts")
import sire_telemetry as t  # noqa: E402

c = t.connect()
c.close()
db = sqlite3.connect(TMP)
db.row_factory = sqlite3.Row
now = time.time()


def add_task(start_offset_total: float, seconds: dict[str, float], mode: str, analyzed: int, tag: str):
    """按'相邻事件时间差记到后一个阶段'的口径造事件序列，再交给真实 analyze 汇总。"""
    session = f"r7-{tag}"
    ts = now - start_offset_total
    db.execute("INSERT INTO events(ts,client,session,event,detail,ok) VALUES(?,?,?,?,?,1)",
               (ts, "codex", session, "prompt", tag))
    prev = ts
    for phase, dur in seconds.items():
        prev = prev + dur
        db.execute("INSERT INTO events(ts,client,session,event,tool,phase,detail,ok,agent) "
                   "VALUES(?,?,?,?,?,?,?,?,NULL)",
                   (prev, "codex", session, "tool", "Bash", phase, json.dumps({"command": phase}), 1))
    db.execute("INSERT INTO events(ts,client,session,event,detail,ok) VALUES(?,?,?,?,?,1)",
               (prev + 1, "codex", session, "stop", mode))
    db.commit()
    if analyzed:
        # 历史任务直接落库为已分析，充当 PHASE_OUTLIER 的中位数基线
        summary = {"seconds": {k: round(v, 1) for k, v in seconds.items()},
                   "calls": {k: 1 for k in seconds}}
        db.execute("INSERT OR REPLACE INTO tasks(task_id,client,session,start_ts,end_ts,total_s,mode,phases,"
                   "tool_calls,failures,cwd,prompt,analyzed) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (f"{session}:{ts:.3f}", "codex", session, ts, prev + 1, prev + 1 - ts, mode,
                    json.dumps(summary), len(seconds), 0, "", tag, 1))
        db.commit()
    else:
        # 走被测代码同一条汇总路径：Stop 钩子里的 summarize_task
        with sqlite3.connect(TMP) as conn:
            conn.row_factory = sqlite3.Row
            t.summarize_task(conn, "codex", session, prev + 1, mode, "")
    return session, ts


def run_pending() -> list[str]:
    out = subprocess.run([sys.executable, SCRIPT, "pending"], env=ENV, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    return [line for line in out.stdout.splitlines() if line.strip()]


# 历史 6 条 full 任务：execute≈10s、archive≈20s，作为中位数基线
for i in range(6):
    add_task(60000 - i * 1000, {"execute": 10.0, "archive": 20.0}, "full", 1, f"hist{i}")
# T1：execute 离群（600s > 3x10s），不应产生 PHASE_OUTLIER
add_task(5000, {"execute": 600.0, "archive": 20.0}, "full", 0, "t1")
# mode=unknown 的同等离群任务，同样不应产生发现
add_task(4000, {"execute": 600.0}, "unknown", 0, "t1u")
db.commit()
db.close()
subprocess.run([sys.executable, SCRIPT, "analyze"], env=ENV, capture_output=True)
t1_pending = run_pending()

db = sqlite3.connect(TMP)
db.row_factory = sqlite3.Row
# T2：真实收尾阶段离群，连续两次命中应转 PROPOSED
for tag, offset in (("t2a", 3000), ("t2b", 2000)):
    add_task(offset, {"execute": 10.0, "archive": 300.0}, "full", 0, tag)
db.commit()
db.close()
subprocess.run([sys.executable, SCRIPT, "analyze"], env=ENV, capture_output=True)
t2_pending = run_pending()
cur = sqlite3.connect(TMP).execute("SELECT finding_id,status,hits FROM findings ORDER BY finding_id")
rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]

result = {"T1_execute离群不再报": t1_pending, "T2_archive离群仍应报": t2_pending, "findings": rows,
          "T1结论": "PASS" if not any("PHASE_OUTLIER" in x for x in t1_pending) else "FAIL",
          "T2结论": "PASS" if any("PHASE_OUTLIER:archive" in x for x in t2_pending) else "FAIL"}
text = json.dumps(result, ensure_ascii=False, indent=1)
Path(__file__).with_name("r7_result.json").write_text(text, encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
print(text)
