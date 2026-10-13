"""R7：验证两项新强制——采集存活自检 COLLECTION_DEAD 与 finish 的 pending 门禁（全部走真实 CLI 路径）。"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts")
RUN = Path(r"D:\sire\AI\AI\sire\.sire\runs\R20261013-081448\logs")
RUN.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="sire_enforce_"))
db = work / "tele.sqlite3"
os.environ["SIRE_TELEMETRY_DB"] = str(db)
env = dict(os.environ)
res = {}

# ---- A. 采集存活自检：claude 配了钩子但 36 小时没事件，qoder 有心跳
claude_cfg = work / "claude.json"
qoder_cfg = work / "qoder.json"
claude_cfg.write_text(json.dumps({"hooks": {"PostToolUse": [{"command": "python sire_telemetry.py hook --client claude"}]}}),
                      encoding="utf-8")
qoder_cfg.write_text(json.dumps({"hooks": {"PostToolUse": [{"command": "python sire_telemetry.py hook --client qoder"}]}}),
                     encoding="utf-8")
env["SIRE_CLIENT_CONFIGS"] = os.pathsep.join([str(claude_cfg), str(qoder_cfg)])


def cli(*args, extra_env=None):
    e = dict(env)
    if extra_env:
        e.update(extra_env)
    p = subprocess.run([sys.executable, str(SCRIPTS / args[0]), *args[1:]], env=e, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    name = "_".join(ch for ch in " ".join(args[1:]) if ch.isalnum() or ch in "-.")[:60] or "call"
    (RUN / ("%s-%s.log" % (args[0].replace(".py", ""), name))).write_text(
        "rc=%s\nSTDOUT:\n%s\nSTDERR:\n%s\n" % (p.returncode, p.stdout, p.stderr), encoding="utf-8")
    return p


sys.path.insert(0, str(SCRIPTS))
import sire_telemetry as t  # noqa: E402
conn = t.connect()
now = time.time()
with conn:
    conn.execute("INSERT INTO events(ts,client,session,event,detail,ok) VALUES(?,?,?,?,?,1)",
                 (now - 36 * 3600, "claude", "s-a", "prompt", "stale"))
    conn.execute("INSERT INTO events(ts,client,session,event,detail,ok) VALUES(?,?,?,?,?,1)",
                 (now - 60, "qoder", "s-b", "prompt", "fresh"))
conn.close()

p = cli("sire_telemetry.py", "analyze", "--stale-hours", "12")
p2 = cli("sire_telemetry.py", "analyze", "--stale-hours", "12")
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
rows = {r["finding_id"]: (r["status"], r["hits"]) for r in conn.execute(
    "select finding_id,status,hits from findings")}
pending = cli("sire_telemetry.py", "pending").stdout.strip()
conn.close()
res["A_存活自检"] = {
    "findings": rows,
    "pending": pending,
    "断言": {
        "哑掉的 claude 被报出且直接 PROPOSED": rows.get("COLLECTION_DEAD:claude", ("", 0))[0] == "PROPOSED",
        "有心跳的 qoder 不被误报": "COLLECTION_DEAD:qoder" not in rows,
        "30 分钟去重生效（两次 analyze 命中仍为 1）": rows.get("COLLECTION_DEAD:claude", ("", 0))[1] == 1,
        "进入 pending 队列": "COLLECTION_DEAD:claude" in pending},
}

# ---- B. finish 的 pending 门禁：有未处理发现必须挡下，显式移交才放行
proj = work / "proj"
proj.mkdir()
stage_args = ["sire_run.py", "--root", str(proj)]
cli("sire_run.py", "--root", str(proj), "init", "--title", "门禁测试", "--channel", "light")
for stage in ["R%d" % i for i in range(11)]:
    cli("sire_run.py", "--root", str(proj), "stage-output", stage, "DONE", "--artifact", "测试产物")
blocked = cli("sire_run.py", "--root", str(proj), "finish", "--no-archive", "--note", "门禁测试收尾")
res["B_无移交"] = {"rc": blocked.returncode, "消息": (blocked.stdout + blocked.stderr).strip()[:200]}

# 处理掉发现（模拟已 resolve）后再收尾，应当直接通过
conn = sqlite3.connect(db)
with conn:
    conn.execute("UPDATE findings SET status='FIXED',hits=0,proposal_id='RSI-DEMO',resolved_at=? "
                 "WHERE finding_id='COLLECTION_DEAD:claude'", (time.time(),))
conn.close()
fixed = cli("sire_run.py", "--root", str(proj), "finish", "--no-archive", "--note", "门禁测试收尾")
res["C_处理后放行"] = {"rc": fixed.returncode, "消息": (fixed.stdout + fixed.stderr).strip()[:160]}

# 再造一条未处理发现，开新 run 用 --pending-note 显式移交
cli("sire_run.py", "--root", str(proj), "init", "--title", "移交测试", "--channel", "light")
for stage in ["R%d" % i for i in range(11)]:
    cli("sire_run.py", "--root", str(proj), "stage-output", stage, "DONE", "--artifact", "移交测试产物")
conn = sqlite3.connect(db)
with conn:
    conn.execute("INSERT OR REPLACE INTO findings VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                 ("COLLECTION_DEAD:demo", "COLLECTION_DEAD", "PROPOSED", 1, time.time(), time.time(),
                  "[]", "演示", None, None, None))
conn.close()
handed = cli("sire_run.py", "--root", str(proj), "finish", "--no-archive", "--note", "门禁测试收尾",
             "--pending-note", "需用户决定：是否改动 Claude 配置")
checks = sorted((proj / ".sire" / "runs").glob("*/pending-check.json"), key=lambda p: p.stat().st_mtime)
res["D_显式移交"] = {"rc": handed.returncode,
                    "pending-check": json.loads(checks[-1].read_text(encoding="utf-8")) if checks else "无文件"}
assertions = {
    "有待处理发现时 finish 被挡下": blocked.returncode != 0 and "自动优化未闭环" in (blocked.stdout + blocked.stderr),
    "发现处理完后 finish 放行": fixed.returncode == 0,
    "显式移交可收尾并留痕": handed.returncode == 0 and res["D_显式移交"]["pending-check"].get("verdict") == "HANDED_OFF",
}
res["断言汇总"] = assertions
res["结论"] = "PASS" if all(assertions.values()) and all(res["A_存活自检"]["断言"].values()) else "FAIL"
text = json.dumps(res, ensure_ascii=False, indent=1)
Path(__file__).with_name("r7_enforce_result.json").write_text(text, encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
print(text)
shutil.rmtree(work, ignore_errors=True)
