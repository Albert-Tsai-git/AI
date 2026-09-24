# -*- coding: utf-8 -*-
"""额外观察 X1b：SIRE_VECTOR_DB 指向非 sqlite 垃圾文件时，finalize 的退出码与基线是否推进（隔离 SIRE_KB_DIR）。"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

QA = Path(__file__).resolve().parent
TMP = QA / "tmp"
SUP = Path(r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts\sire_supervisor.py")
REAL_KB = Path(r"D:\sire\AI\AI\sire\knowledge\global")
kb = TMP / "kb_c"
if kb.exists():
    shutil.rmtree(kb)
shutil.copytree(REAL_KB, kb, ignore=shutil.ignore_patterns("integrity", "secrets", "exports", "__pycache__"))
garbage = TMP / "garbage.sqlite3"
env = {k: v for k, v in os.environ.items() if k not in ("SIRE_VECTOR_DB", "SIRE_KB_DIR", "SIRE_ROOT", "SIRE_DATA_DIR")}
env.update({"SIRE_KB_DIR": str(kb), "SIRE_VECTOR_DB": str(garbage), "PYTHONPYCACHEPREFIX": str(TMP / "pycache"),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
man = kb / "integrity" / "manifest.json"
out = []
for args in (["preflight"], ["start", "--run-id", "QA-RSI"], ["finalize", "--run-id", "QA-RSI"]):
    before = hashlib.sha256(man.read_bytes()).hexdigest() if man.exists() else None
    p = subprocess.run([sys.executable, str(SUP), *args], cwd=str(SUP.parent), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    after = hashlib.sha256(man.read_bytes()).hexdigest() if man.exists() else None
    out.append({"cmd": args, "rc": p.returncode, "traceback": "Traceback" in p.stderr, "stderr_tail": p.stderr.strip().splitlines()[-1:] if p.stderr.strip() else [],
                "manifest_before": before, "manifest_after": after})
out.append({"baseline_next_exists": (kb / "integrity" / "snapshots" / "baseline-next").exists()})
shutil.rmtree(TMP / "pycache", ignore_errors=True)
text = json.dumps(out, ensure_ascii=False, indent=2)
(QA / "x1-finalize-garbage.json").write_text(text, encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
print(text)
