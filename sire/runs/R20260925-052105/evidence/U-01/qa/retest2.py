# -*- coding: utf-8 -*-
"""复测2：从未提交目录 + 未跟踪文件；finalize STOP 时写 rsi-report.json；真实库 rsi-check 只读。"""
import hashlib, json, os, shutil, sqlite3, subprocess, sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
QA = Path(__file__).resolve().parent; TMP = QA / "tmp"
S = Path(r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts"); SUP = S / "sire_supervisor.py"
REAL_DB = Path(r"D:\sire\AI\AI\sire\data\sire_vectors.sqlite3"); REAL_KB = Path(r"D:\sire\AI\AI\sire\knowledge\global")
sys.path.insert(0, str(S))
import sire_supervisor as m
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
env = {k: v for k, v in os.environ.items() if k not in ("SIRE_VECTOR_DB", "SIRE_KB_DIR", "SIRE_ROOT", "SIRE_DATA_DIR")}
env.update(PYTHONPYCACHEPREFIX=str(TMP / "pycache"), PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
res = {}
# 小型提案库副本：表结构只读取自真实库，只放一条 ACTIVE 提案
src = sqlite3.connect(REAL_DB.resolve().as_uri() + "?mode=ro", uri=True)
schema = src.execute("SELECT sql FROM sqlite_master WHERE name='improvement_proposals'").fetchone()[0]; src.close()
def mkdb(path, status):
    path.unlink(missing_ok=True); c = sqlite3.connect(path); c.execute(schema)
    c.execute("INSERT INTO improvement_proposals(proposal_id,title,hypothesis,change_summary,status,created_at) VALUES(?,?,?,?,?,?)",
              ("RSI-QA-OLD", "qa", "qa", "qa", status, "2026-09-21T00:50:31+00:00")); c.commit(); c.close()
db = TMP / "rt2_props.sqlite3"
def git(cwd, *a): return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)
# (1a) 仓库有提交，但工作流子目录从未提交，只有未跟踪文件；(1b) 仓库完全没有提交
for tag, commit_root in (("1a 仓库有其他提交", True), ("1b 仓库零提交", False)):
    repo = TMP / f"rt2_repo_{tag[:2]}"; shutil.rmtree(repo, ignore_errors=True); repo.mkdir()
    git(repo, "init", "-q")
    if commit_root:
        (repo / "README.txt").write_text("root file for qa repo\n", encoding="utf-8")
        git(repo, "add", "README.txt"); git(repo, "-c", "user.name=qa", "-c", "user.email=qa@example.invalid", "commit", "-q", "-m", "root")
    wf = repo / "workflow"; wf.mkdir(); (wf / "new_rule.md").write_text("untracked workflow file for qa\n", encoding="utf-8")
    out = {"git_status": git(wf, "status", "--porcelain", "--", ".").stdout.strip(), "log_rc": git(wf, "log", "-1", "--format=%cI", "--", ".").returncode}
    for status, want in (("ACTIVE", "STOP"), ("PROPOSED", "PASS")):
        mkdb(db, status)
        try:
            r = m.rsi_gate(db_path=db, skill_dir=wf); out[status] = {"status": r["status"], "classification": r.get("classification"), "changed": r.get("changed"), "last_workflow_commit": r.get("last_workflow_commit"), "matched": [x["proposal_id"] for x in r.get("matched_proposals", [])], "ok": r["status"] == want}
        except Exception as e:
            out[status] = {"raised": repr(e), "ok": False}
    res["R1 " + tag] = out
# (2) 隔离 SIRE_KB_DIR 跑 finalize，库只有早于提交的 ACTIVE 提案 → STOP
mkdb(db, "ACTIVE")
kb = TMP / "kb_d"; shutil.rmtree(kb, ignore_errors=True)
shutil.copytree(REAL_KB, kb, ignore=shutil.ignore_patterns("integrity", "secrets", "exports", "__pycache__"))
e2 = dict(env, SIRE_KB_DIR=str(kb), SIRE_VECTOR_DB=str(db)); rcs = []
for a in (["preflight"], ["start", "--run-id", "QA-RSI2"]):
    rcs.append(subprocess.run([sys.executable, str(SUP), *a], cwd=S, env=e2, capture_output=True, text=True, encoding="utf-8").returncode)
man = kb / "integrity" / "manifest.json"; hb = sha(man)
p = subprocess.run([sys.executable, str(SUP), "finalize", "--run-id", "QA-RSI2"], cwd=S, env=e2, capture_output=True, text=True, encoding="utf-8")
rep = kb / "integrity" / "runs" / "QA-RSI2" / "rsi-report.json"
rj = json.loads(rep.read_text(encoding="utf-8")) if rep.exists() else {}
res["R2 finalize STOP 写 rsi-report"] = {"preflight_start_rc": rcs, "finalize_rc": p.returncode, "traceback": "Traceback" in p.stderr, "rsi_report_exists": rep.exists(),
    "rsi_report_status": rj.get("status"), "rsi_report_classification": rj.get("classification"), "checked_at": rj.get("checked_at"), "manifest_unchanged": hb == sha(man),
    "ok": p.returncode == 3 and rep.exists() and rj.get("status") == "STOP" and hb == sha(man)}
# (3) 真实库 rsi-check
h0 = sha(REAL_DB); d0 = sorted(os.listdir(REAL_DB.parent))
p = subprocess.run([sys.executable, str(SUP), "rsi-check"], cwd=S, env=env, capture_output=True, text=True, encoding="utf-8")
h1 = sha(REAL_DB); d1 = sorted(os.listdir(REAL_DB.parent)); j = json.loads(p.stdout) if p.returncode == 0 else {}
res["R3 真实库 rsi-check"] = {"rc": p.returncode, "status": j.get("status"), "matched": [x["proposal_id"] for x in j.get("matched_proposals", [])], "sha_before": h0, "sha_after": h1, "data_before": d0, "data_after": d1,
    "ok": p.returncode == 0 and j.get("status") == "PASS" and h0 == h1 and d0 == d1}
db.unlink(missing_ok=True); shutil.rmtree(TMP / "pycache", ignore_errors=True)
print(json.dumps(res, ensure_ascii=False, indent=2))
