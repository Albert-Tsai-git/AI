# -*- coding: utf-8 -*-
"""R7 功能测试（U-01）：sire_supervisor.py rsi-check 与 finalize 集成。

约束：真实库只读；所有数据库变体都在 tmp/ 下的副本上修改；finalize 只在隔离的 SIRE_KB_DIR 下运行；
字节码通过 PYTHONPYCACHEPREFIX 重定向到 tmp/pycache，避免在工作流目录写 .pyc。
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

QA = Path(__file__).resolve().parent
TMP = QA / "tmp"
S = Path(r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts")
SUP = S / "sire_supervisor.py"
WF = S.parent
REAL_DB = Path(r"D:\sire\AI\AI\sire\data\sire_vectors.sqlite3")
DATA = REAL_DB.parent
REAL_KB = Path(r"D:\sire\AI\AI\sire\knowledge\global")
QA_ALL = Path(r"C:\Users\ADMINI~1\AppData\Local\Temp\claude\D--code-driverSoftware\cf61fd01-38cb-47e9-bb50-00b26b934feb\scratchpad\verify-192838\u02b\qa_all.py")
T8_SCRIPT = QA / "t8_inproc.py"
PID = "RSI-20260925-R9GATE"
PY = sys.executable
LOG = QA / "run-output.log"
RESULTS = QA / "results.json"

if TMP.exists():
    shutil.rmtree(TMP)
TMP.mkdir(parents=True)
log_fh = LOG.open("w", encoding="utf-8")


def log(msg: str = "") -> None:
    print(msg)
    log_fh.write(msg + "\n")
    log_fh.flush()


BASE_ENV = dict(os.environ)
for key in ("SIRE_VECTOR_DB", "SIRE_KB_DIR", "SIRE_ROOT", "SIRE_DATA_DIR"):
    BASE_ENV.pop(key, None)
BASE_ENV.update({
    "PYTHONPYCACHEPREFIX": str(TMP / "pycache"),
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONIOENCODING": "utf-8",
})


def run(args, extra=None, cwd=S, label=""):
    env = dict(BASE_ENV)
    env.update(extra or {})
    t0 = time.time()
    p = subprocess.run([str(a) for a in args], cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log(f"\n===== [{label}] $ (cwd={cwd}) " + " ".join(str(a) for a in args))
    if extra:
        log("  env override: " + json.dumps(extra, ensure_ascii=False))
    log(f"  rc={p.returncode}  elapsed={time.time() - t0:.2f}s")
    log("  --- stdout ---\n" + p.stdout)
    log("  --- stderr ---\n" + p.stderr)
    return p


def parse_all(text: str) -> list:
    dec = json.JSONDecoder()
    i, out = 0, []
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        try:
            obj, j = dec.raw_decode(text, i)
            out.append(obj)
            i = j
        except json.JSONDecodeError:
            nl = text.find("\n", i)
            if nl < 0:
                break
            i = nl + 1
    return out


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tree(root: Path, follow: bool = False) -> dict:
    out = {}
    for d, _, files in os.walk(root, followlinks=follow):
        for f in files:
            p = Path(d) / f
            try:
                st = p.stat()
            except OSError:
                continue
            out[str(p.relative_to(root))] = [st.st_size, st.st_mtime_ns]
    return out


def diff_tree(a: dict, b: dict) -> dict:
    return {
        "added": sorted(set(b) - set(a)),
        "removed": sorted(set(a) - set(b)),
        "modified": sorted(k for k in set(a) & set(b) if a[k] != b[k]),
    }


def git(args, cwd=WF, extra_env=None):
    env = dict(BASE_ENV)
    env.update(extra_env or {})
    return subprocess.run(["git", *args], cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")


def rows(db: Path):
    c = sqlite3.connect(db)
    try:
        return c.execute("SELECT proposal_id, status, created_at FROM improvement_proposals ORDER BY proposal_id").fetchall()
    finally:
        c.close()


def rsi(label, db=None, extra=None):
    ex = dict(extra or {})
    if db is not None:
        ex["SIRE_VECTOR_DB"] = str(db)
    p = run([PY, SUP, "rsi-check"], ex, label=label)
    objs = parse_all(p.stderr if p.returncode == 3 else p.stdout)
    return p, (objs[-1] if objs else {})


def no_tb(p) -> bool:
    return "Traceback" not in (p.stdout + p.stderr)


def is_stop(p, j) -> bool:
    return p.returncode == 3 and j.get("status") == "STOP" and j.get("classification") == "rsi_unregistered_change" and no_tb(p)


results = []


def record(tid, name, steps, expected, actual, ok, blocked=False):
    verdict = "BLOCKED-无法真实验证" if blocked else ("PASS" if ok else "FAIL")
    results.append({"id": tid, "name": name, "steps": steps, "expected": expected, "actual": actual, "verdict": verdict, "evidence": str(LOG)})
    log(f">>> {tid} {name}: {verdict} | {json.dumps(actual, ensure_ascii=False)}")


def matched_ids(j):
    return [m.get("proposal_id") for m in j.get("matched_proposals", []) or []]


# ---------------- 前置快照 ----------------
log(f"[qa] python={PY} {sys.version.split()[0]}  started={time.strftime('%Y-%m-%d %H:%M:%S')}")
commit_before = git(["log", "-1", "--format=%H %cI", "--", "."]).stdout.strip()
status_before = git(["status", "--porcelain", "--", "."]).stdout
log(f"[qa] 工作流目录最后提交: {commit_before}")
log(f"[qa] 工作流目录 git status --porcelain:\n{status_before}")
log("[qa] 真实库提案（只读）: " + json.dumps(parse_all(subprocess.run([PY, "-c", (
    "import sqlite3,json,pathlib;p=pathlib.Path(r'%s');c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);"
    "print(json.dumps(c.execute('SELECT proposal_id,status,created_at FROM improvement_proposals').fetchall()));c.close()") % REAL_DB],
    capture_output=True, text=True, env=BASE_ENV).stdout), ensure_ascii=False))
wf_before = tree(WF)
kb_before = tree(REAL_KB, follow=True)
data_before = sorted(os.listdir(DATA))
log(f"[qa] 工作流目录文件数={len(wf_before)} 真实知识目录(跟随链接)文件数={len(kb_before)} data 目录={data_before}")

# ---------------- T1 + T5：真实库 rsi-check 与只读 ----------------
h0, st0 = sha(REAL_DB), REAL_DB.stat()
p, j = rsi("T1 真实库 rsi-check")
h1, st1 = sha(REAL_DB), REAL_DB.stat()
data_after = sorted(os.listdir(DATA))
sidecars = [n for n in data_after if n.endswith(("-wal", "-shm", "-journal"))]
record("T1", "真实库 rsi-check 正常路径",
       "cwd=scripts; 不设 SIRE_VECTOR_DB; python sire_supervisor.py rsi-check",
       f"rc=0, status=PASS, matched_proposals 含 {PID}",
       {"rc": p.returncode, "status": j.get("status"), "matched": matched_ids(j), "last_workflow_commit": j.get("last_workflow_commit"), "changed": j.get("changed"), "db": j.get("db")},
       p.returncode == 0 and j.get("status") == "PASS" and PID in matched_ids(j) and no_tb(p))
record("T5", "真实库只读",
       "T1 前后计算真实库 sha256/mtime，并列出 data 目录",
       "sha256 与 mtime 不变；data 目录无 -wal/-shm/-journal，文件列表不变",
       {"sha256_before": h0, "sha256_after": h1, "mtime_ns_before": st0.st_mtime_ns, "mtime_ns_after": st1.st_mtime_ns, "data_before": data_before, "data_after": data_after, "sidecars": sidecars},
       h0 == h1 and st0.st_mtime_ns == st1.st_mtime_ns and not sidecars and data_before == data_after)

# ---------------- 数据库副本 ----------------
db_full = TMP / "db_full.sqlite3"
shutil.copyfile(REAL_DB, db_full)
h_copy_src = sha(REAL_DB)
log(f"[qa] 副本 db_full sha256={sha(db_full)} 源 sha256={h_copy_src} rows={rows(db_full)}")
db_noprop = TMP / "db_noprop.sqlite3"
shutil.copyfile(db_full, db_noprop)
c = sqlite3.connect(db_noprop)
c.execute("DELETE FROM improvement_proposals WHERE proposal_id=?", (PID,))
c.commit()
c.close()
log(f"[qa] db_noprop 删除 {PID} 后 rows={rows(db_noprop)}")

# ---------------- T2 ----------------
p, j = rsi("T2 无提案副本", db_noprop)
record("T2", "库副本删除提案后 STOP",
       f"复制真实库→tmp/db_noprop.sqlite3，DELETE {PID}；SIRE_VECTOR_DB=副本 rsi-check",
       "rc=3, status=STOP, classification=rsi_unregistered_change",
       {"rc": p.returncode, "status": j.get("status"), "classification": j.get("classification"), "matched": matched_ids(j), "remaining_rows": rows(db_noprop)},
       is_stop(p, j) and matched_ids(j) == [])

# ---------------- T3 ----------------
missing = TMP / "nope" / "missing.sqlite3"
empty0 = TMP / "empty0.sqlite3"
empty0.write_bytes(b"")
notable = TMP / "no_table.sqlite3"
c = sqlite3.connect(notable)
c.execute("CREATE TABLE other(x TEXT)")
c.execute("INSERT INTO other VALUES ('placeholder row for no-table case')")
c.commit()
c.close()
t3 = {}
for name, path in (("不存在的文件", missing), ("0 字节空 sqlite", empty0), ("无 improvement_proposals 表的 sqlite", notable)):
    before = sha(path) if path.exists() else None
    p, j = rsi(f"T3 {name}", path)
    after = sha(path) if path.exists() else None
    side = [x.name for x in path.parent.glob(path.name + "-*")] if path.parent.exists() else []
    t3[name] = {"rc": p.returncode, "status": j.get("status"), "classification": j.get("classification"), "traceback": not no_tb(p),
                "file_unchanged": before == after, "exists_after": path.exists(), "sidecars": side, "ok": is_stop(p, j) and before == after and not side}
record("T3", "库缺失/缺表边界",
       "SIRE_VECTOR_DB 分别指向 tmp/nope/missing.sqlite3（不存在）、tmp/empty0.sqlite3（0 字节）、tmp/no_table.sqlite3（只有 other 表）",
       "均 rc=3、STOP、rsi_unregistered_change，无 Traceback；不创建文件、不改文件",
       t3, all(v["ok"] for v in t3.values()) and not missing.exists())

# 额外观察（不计入派发清单结论）：非 sqlite 垃圾文件、目录路径
extra_obs = {}
garbage = TMP / "garbage.sqlite3"
garbage.write_text("this is plain text, not a sqlite database file. " * 4, encoding="utf-8")
p, j = rsi("X1 垃圾文件（额外观察）", garbage)
extra_obs["X1 非 sqlite 垃圾文件"] = {"rc": p.returncode, "status": j.get("status"), "traceback": not no_tb(p), "stderr_tail": p.stderr.strip().splitlines()[-1:] if p.stderr.strip() else []}
p, j = rsi("X2 目录路径（额外观察）", TMP)
extra_obs["X2 SIRE_VECTOR_DB 指向目录"] = {"rc": p.returncode, "status": j.get("status"), "classification": j.get("classification"), "traceback": not no_tb(p)}

# ---------------- T4 ----------------
db_var = TMP / "db_var.sqlite3"
shutil.copyfile(db_full, db_var)
orig = {r[0]: r for r in rows(db_var)}[PID]


def set_row(**kw):
    c = sqlite3.connect(db_var)
    c.execute("UPDATE improvement_proposals SET " + ", ".join(f"{k}=?" for k in kw) + " WHERE proposal_id=?", (*kw.values(), PID))
    c.commit()
    c.close()


commit_iso = git(["log", "-1", "--format=%cI", "--", "."]).stdout.strip()
t4 = {}
cases = [
    ("a status=EVALUATED_FAIL", {"status": "EVALUATED_FAIL", "created_at": orig[2]}, "STOP"),
    ("b status=ROLLED_BACK", {"status": "ROLLED_BACK", "created_at": orig[2]}, "STOP"),
    ("c created_at 早于提交 2026-09-20T00:00:00+00:00", {"status": "PROPOSED", "created_at": "2026-09-20T00:00:00+00:00"}, "STOP"),
    ("d naive created_at 2026-09-25T00:00:00（按 UTC 晚于提交）", {"status": "PROPOSED", "created_at": "2026-09-25T00:00:00"}, "PASS"),
    ("e(额外) created_at 恰等于提交时间", {"status": "PROPOSED", "created_at": commit_iso}, "PASS"),
    ("f(额外) created_at=not-a-date", {"status": "PROPOSED", "created_at": "not-a-date"}, "STOP"),
    ("g(额外) status=EVALUATED_PASS", {"status": "EVALUATED_PASS", "created_at": orig[2]}, "PASS"),
    ("h(额外) status=ACTIVE", {"status": "ACTIVE", "created_at": orig[2]}, "PASS"),
]
for name, kw, want in cases:
    set_row(**kw)
    p, j = rsi(f"T4 {name}", db_var)
    got_row = {r[0]: r for r in rows(db_var)}[PID]
    if want == "STOP":
        ok = is_stop(p, j) and PID not in matched_ids(j)
    else:
        ok = p.returncode == 0 and j.get("status") == "PASS" and PID in matched_ids(j) and no_tb(p)
    t4[name] = {"row": list(got_row), "want": want, "rc": p.returncode, "status": j.get("status"), "classification": j.get("classification"), "matched": matched_ids(j), "traceback": not no_tb(p), "ok": ok}
set_row(status=orig[1], created_at=orig[2])
core = ["a status=EVALUATED_FAIL", "b status=ROLLED_BACK", "c created_at 早于提交 2026-09-20T00:00:00+00:00", "d naive created_at 2026-09-25T00:00:00（按 UTC 晚于提交）"]
record("T4", "提案状态/时间边界",
       f"db_var 副本依次 UPDATE {PID} 的 status/created_at 后运行 rsi-check（最后提交 {commit_iso}）",
       "EVALUATED_FAIL/ROLLED_BACK/早于提交 均 STOP rc=3；naive 晚于提交不崩溃（按 UTC 解释 → PASS）",
       t4, all(t4[k]["ok"] for k in core))
extra_obs["T4 额外子项 e/f/g/h"] = {k: v["ok"] for k, v in t4.items() if k not in core}

# ---------------- T6 finalize 集成 ----------------
def mk_kb(name):
    dst = TMP / name
    shutil.copytree(REAL_KB, dst, ignore=shutil.ignore_patterns("integrity", "secrets", "exports", "__pycache__"))
    return dst


t6 = {}
for tag, db, want in (("a 无提案副本", db_noprop, 3), ("b 含提案真实库副本", db_full, 0)):
    kb = mk_kb("kb_" + tag[0])
    ex = {"SIRE_KB_DIR": str(kb), "SIRE_VECTOR_DB": str(db)}
    man = kb / "integrity" / "manifest.json"
    p1 = run([PY, SUP, "preflight"], ex, label=f"T6{tag} preflight")
    p2 = run([PY, SUP, "start", "--run-id", "QA-RSI"], ex, label=f"T6{tag} start")
    hb = sha(man) if man.exists() else None
    lb = json.loads(man.read_text(encoding="utf-8")).get("label") if man.exists() else None
    p3 = run([PY, SUP, "finalize", "--run-id", "QA-RSI"], ex, label=f"T6{tag} finalize")
    ha = sha(man) if man.exists() else None
    la = json.loads(man.read_text(encoding="utf-8")).get("label") if man.exists() else None
    next_dir = (kb / "integrity" / "snapshots" / "baseline-next").exists()
    report = kb / "integrity" / "runs" / "QA-RSI" / "supervisor-report.json"
    report_status = json.loads(report.read_text(encoding="utf-8")).get("status") if report.exists() else None
    err_objs = parse_all(p3.stderr)
    out_objs = parse_all(p3.stdout)
    info = {"preflight_rc": p1.returncode, "preflight_status": (parse_all(p1.stdout) or [{}])[-1].get("status"),
            "start_rc": p2.returncode, "start_status": (parse_all(p2.stdout) or [{}])[-1].get("status"),
            "finalize_rc": p3.returncode, "run_check_report_status": report_status,
            "finalize_stderr_classification": (err_objs[-1].get("classification") if err_objs else None),
            "finalize_last_stdout_status": (out_objs[-1].get("status") if out_objs else None),
            "manifest_sha_before": hb, "manifest_sha_after": ha, "manifest_label_before": lb, "manifest_label_after": la,
            "baseline_next_snapshot_exists": next_dir, "traceback": not (no_tb(p1) and no_tb(p2) and no_tb(p3))}
    if want == 3:
        info["ok"] = (p1.returncode == 0 and p2.returncode == 0 and p3.returncode == 3 and report_status == "PASS"
                      and info["finalize_stderr_classification"] == "rsi_unregistered_change" and hb == ha and hb is not None
                      and not next_dir and not info["traceback"])
    else:
        info["ok"] = (p1.returncode == 0 and p2.returncode == 0 and p3.returncode == 0 and info["finalize_last_stdout_status"] == "FINALIZED"
                      and ha != hb and la == "baseline-next" and next_dir and not info["traceback"])
    t6[tag] = info
record("T6", "finalize 集成（隔离 SIRE_KB_DIR）",
       "复制真实知识目录（排除 integrity/secrets/exports）到 tmp/kb_a、tmp/kb_b；各自 preflight→start --run-id QA-RSI→finalize --run-id QA-RSI；a 用无提案副本，b 用含提案副本",
       "a: finalize rc=3 + rsi_unregistered_change，manifest.json 不变，不生成 baseline-next；b: finalize rc=0 FINALIZED，manifest 推进为 baseline-next",
       t6, all(v["ok"] for v in t6.values()))
log(f"[qa] db_full 在 T6 后 sha256={sha(db_full)}（应等于复制源 {h_copy_src}）")

# ---------------- T7 回归 ----------------
sp = TMP / "u02b"
sp.mkdir()
if QA_ALL.is_file():
    p = run([PY, QA_ALL, sp, "U-02B"], {}, cwd=QA, label="T7 qa_all.py U-02B")
    fails = [ln for ln in p.stdout.splitlines() if ln.startswith("FAIL ")]
    qa_all = {"rc": p.returncode, "all_pass_line": "ALL PASS" in p.stdout, "fail_lines": fails, "pass_count": sum(1 for ln in p.stdout.splitlines() if ln.startswith("PASS "))}
    qa_ok = p.returncode == 0 and "ALL PASS" in p.stdout and not fails
else:
    qa_all, qa_ok = {"missing": str(QA_ALL)}, None
ph = run([PY, SUP, "--help"], {}, label="T7 --help")
help_info = {"rc": ph.returncode, "lists_rsi_check": "rsi-check" in ph.stdout, "usage_line": ph.stdout.splitlines()[0] if ph.stdout else ""}
record("T7", "回归：verify-zip qa_all + --help",
       f"python qa_all.py {sp} U-02B；python sire_supervisor.py --help",
       "qa_all 输出 ALL PASS；--help 列出 rsi-check",
       {"qa_all": qa_all, "help": help_info}, bool(qa_ok) and ph.returncode == 0 and help_info["lists_rsi_check"], blocked=qa_ok is None)

# ---------------- T8 非 Git 目录 ----------------
sys_tmp = Path(tempfile.gettempdir())
nogit = TMP / "nogit"
nogit.mkdir()
probe_sys = git(["rev-parse", "--show-toplevel"], cwd=sys_tmp)
probe_ceiling = git(["rev-parse", "--show-toplevel"], cwd=nogit, extra_env={"GIT_CEILING_DIRECTORIES": str(TMP)})
probe_plain = git(["rev-parse", "--show-toplevel"], cwd=nogit)
log(f"[qa] git rev-parse 探测: 系统临时目录 {sys_tmp} rc={probe_sys.returncode}; tmp/nogit+CEILING rc={probe_ceiling.returncode}; tmp/nogit 无 CEILING rc={probe_plain.returncode} top={probe_plain.stdout.strip()}")
t8 = {}
for name, d, ex in (
    ("a 系统临时目录(真实非 Git)", sys_tmp, {}),
    ("b tmp/nogit + GIT_CEILING_DIRECTORIES", nogit, {"GIT_CEILING_DIRECTORIES": str(TMP)}),
):
    p = run([PY, T8_SCRIPT, d], ex, cwd=QA, label=f"T8 {name}")
    j = (parse_all(p.stdout) or [{}])[-1]
    t8[name] = {"rc": p.returncode, "raised": j.get("raised"), "status": (j.get("result") or {}).get("status"), "reason": (j.get("result") or {}).get("reason"),
                "ok": p.returncode == 0 and j.get("raised") is False and (j.get("result") or {}).get("status") == "SKIPPED"}
record("T8", "非 Git 目录 rsi_gate 返回 SKIPPED",
       "子进程内 import sire_supervisor，调用 rsi_gate(skill_dir=<非 Git 目录>)",
       "status=SKIPPED，不抛异常",
       {"probe_sys_tmp_rc": probe_sys.returncode, "probe_ceiling_rc": probe_ceiling.returncode, **t8}, probe_sys.returncode != 0 and all(v["ok"] for v in t8.values()))
# 额外观察：PATH 中没有 git、skill_dir 不存在
for name, d, ex in (
    ("X3 PATH 无 git", WF, {"PATH": r"C:\Windows\System32"}),
    ("X4 skill_dir 不存在", TMP / "does-not-exist", {}),
):
    p = run([PY, T8_SCRIPT, d], ex, cwd=QA, label=f"{name}（额外观察）")
    j = (parse_all(p.stdout) or [{}])[-1]
    extra_obs[name] = {"rc": p.returncode, "raised": j.get("raised"), "exc": j.get("exc"), "status": (j.get("result") or {}).get("status"), "reason": (j.get("result") or {}).get("reason")}

# ---------------- 后置核对 ----------------
wf_after = tree(WF)
kb_after = tree(REAL_KB, follow=True)
data_end = sorted(os.listdir(DATA))
commit_after = git(["log", "-1", "--format=%H %cI", "--", "."]).stdout.strip()
status_after = git(["status", "--porcelain", "--", "."]).stdout
h_end = sha(REAL_DB)
post = {"workflow_dir_diff": diff_tree(wf_before, wf_after), "real_kb_diff": diff_tree(kb_before, kb_after),
        "data_dir_before": data_before, "data_dir_end": data_end, "real_db_sha_start": h0, "real_db_sha_end": h_end,
        "workflow_commit_before": commit_before, "workflow_commit_after": commit_after,
        "workflow_status_unchanged": status_before == status_after}
log("[qa] 后置核对: " + json.dumps(post, ensure_ascii=False, indent=2))

# 清理大体积数据库副本（每个约 47MB），保留小文件与隔离知识目录作证据
for f in (db_full, db_noprop, db_var):
    f.unlink(missing_ok=True)
shutil.rmtree(TMP / "pycache", ignore_errors=True)

RESULTS.write_text(json.dumps({"results": results, "extra_observations": extra_obs, "post_checks": post}, ensure_ascii=False, indent=2), encoding="utf-8")
log("\n[qa] 汇总: " + ", ".join(f"{r['id']}={r['verdict']}" for r in results))
log("[qa] 额外观察: " + json.dumps(extra_obs, ensure_ascii=False))
log_fh.close()
