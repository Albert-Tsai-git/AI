"""SIRE 收尾合并命令：把 R9 那一串手工步骤压成一次调用，降低收尾占比。

遥测依据：CLOSE_HEAVY 规则建议"把多步手工收尾合并成脚本命令"；实测本端一个回合计 212s，
其中 rsi/archiving 类收尾动作占 101s（48%），收尾由十余次 python 冷启动组成。

用法（在本目录或任意 cwd）：
  python sire_close.py close --root <项目根> [--run <RUN_ID>]
        [--stages stages.json] [--records E-013,P-20260934 | --no-archive "原因"]
        [--migration "迁移文档行文本"] [--kb-add "P|标题|正文文件"]
        [--archive-root D:/sire] [--dry-run]

stages.json 形如：
  [{"stage":"R5","status":"DONE","artifact":"…","note":"…"},
   {"stage":"R10","status":"SKIPPED","reason":"无 OS 级操作"}]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from sire_paths import SHARED_SKILL_DIR  # noqa: E402

PY = sys.executable


def run(cmd: list[str], env: dict, dry: bool) -> tuple[int, str]:
    if dry:
        print("DRY:", " ".join(cmd))
        return 0, ""
    result = subprocess.run([PY, *cmd], env=env, text=True, capture_output=True,
                            encoding="utf-8", errors="replace")
    out = (result.stdout or "") + (result.stderr or "")
    print(("  ok  " if result.returncode == 0 else "  FAIL") + " " + " ".join(cmd[1:4]))
    if result.returncode:
        print(out[-800:])
    return result.returncode, out


def main() -> int:
    ap = argparse.ArgumentParser(description="SIRE 收尾合并命令")
    ap.add_argument("cmd", choices=("close",))
    ap.add_argument("--root", required=True, help="项目根（含 .sire/runs）")
    ap.add_argument("--run", default="", help="RUN_ID，默认取 .sire/current")
    ap.add_argument("--stages", default="", help="阶段清单 json")
    ap.add_argument("--records", default="", help="本次归档记录编号，逗号分隔")
    ap.add_argument("--no-archive", dest="no_archive", default="", help="免归档原因")
    ap.add_argument("--migration", default="", help="追加到 SIRE-MIGRATION.md 变更记录的行文本")
    ap.add_argument("--kb-add", default="", help="归档知识记录：类型|标题|正文文件")
    ap.add_argument("--archive-root", default=os.environ.get("SIRE_ARCHIVE_ROOT", ""),
                    help="机器级归档库根目录（写 RSI/归档记录时需要）")
    ap.add_argument("--skip-reindex", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    env = dict(os.environ)
    if args.archive_root:
        env["SIRE_ARCHIVE_ROOT"] = args.archive_root
        env.setdefault("SIRE_ARCHIVE_DB", str(Path(args.archive_root) / "sire_vectors.sqlite3"))
    run_dir = args.run or (root / ".sire" / "current").read_text(encoding="utf-8").strip()
    ledger = [str(root / ".sire" / "runs" / run_dir)]
    steps = []

    if args.kb_add:
        kind, title, body = args.kb_add.split("|", 2)
        steps.append((str(SHARED_SKILL_DIR / "scripts" / "sire_kb.py"),
                      "add", kind, "--title", title, "--file", body))
    if not args.skip_reindex:
        steps.append((str(SHARED_SKILL_DIR / "scripts" / "sire_kb.py"), "reindex"))
        steps.append((str(SHARED_SKILL_DIR / "scripts" / "sire_vector_db.py"), "index"))

    if args.migration and not args.dry_run:
        doc = root / "knowledge" / "global" / "SIRE-MIGRATION.md"
        if not doc.is_file():
            doc = SHARED_SKILL_DIR.parent.parent / "knowledge" / "global" / "SIRE-MIGRATION.md"
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        text = doc.read_text(encoding="utf-8")
        if args.migration.strip() in text:  # 按行内容判重，重复执行不再追加第二行
            print("  跳过  迁移文档已有该记录")
        else:
            doc.write_text(text.rstrip() + "\n" + args.migration.strip() + "\n", encoding="utf-8")
            print(f"  ok   迁移文档追加记录（{stamp}）")

    for step in steps:  # kb add / reindex / index 必须先落地，finish 才能在索引里找到新记录
        rc, _ = run(list(step), env, args.dry_run)
        if rc:
            return rc

    stage_args = ["--root", str(root)]
    if args.stages:
        entries = json.loads(Path(args.stages).read_text(encoding="utf-8"))
        for e in entries:
            cmd = [str(SHARED_SKILL_DIR / "scripts" / "sire_run.py"), *stage_args,
                   "stage-output", e["stage"], e["status"]]
            for flag, key in (("--artifact", "artifact"), ("--note", "note"), ("--reason", "reason")):
                if e.get(key):
                    cmd += [flag, e[key]]
            if not args.dry_run:
                r = subprocess.run([PY, *cmd], env=env, text=True, capture_output=True,
                                   encoding="utf-8", errors="replace")
                print(("  ok   " if r.returncode == 0 else "  FAIL ") + "stage-output " + e["stage"])
                if r.returncode:
                    print((r.stdout + r.stderr)[-400:])
                    return 1
            else:
                print("DRY:", " ".join(cmd[:8]), "…")

    finish = [str(SHARED_SKILL_DIR / "scripts" / "sire_run.py"), *stage_args, "finish"]
    if args.records:
        finish += ["--records", args.records]
    if args.no_archive:
        finish += ["--no-archive", "--note", args.no_archive]
    rc, out = run(finish, env, args.dry_run)
    if rc:
        return rc
    if "已收尾" in out:
        ledger.append(out.splitlines()[0].strip())

    if not args.dry_run:
        src = root / ".sire" / "runs" / run_dir
        dst = root / "runs" / run_dir
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            ledger.append(str(dst))

    print(json.dumps({"run": run_dir, "records": args.records or ("免归档: " + args.no_archive),
                      "台账位置": ledger[-1] if ledger else run_dir,
                      "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
