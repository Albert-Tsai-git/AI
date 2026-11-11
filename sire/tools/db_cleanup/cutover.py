# -*- coding: utf-8 -*-
"""[切换] 用清理后的候选库替换线上工作库（可选同时替换机器级归档库）。

用法（在用户自己的终端里运行，密码由用户本人输入，脚本和 AI 都不代填）:
  python cutover.py --dry-run            只做前置检查，不改任何文件、不要密码
  python cutover.py                      检查 + 输入删除确认密码 + 备份 + 替换 + 核对
  python cutover.py --archive            同时替换机器级归档库 D:\\sire\\sire_vectors.sqlite3
回滚: 把备份目录里的 sire_vectors.sqlite3 复制回原路径（脚本结束时会打印具体命令）。
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SCRIPTS = Path(r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts")
sys.path.insert(0, str(SCRIPTS))

CAND = Path(r"D:\sire\db-candidate\sire_vectors.sqlite3")
WORKING = Path(r"D:\sire\AI\AI\sire\data\sire_vectors.sqlite3")
ARCHIVE = Path(r"D:\sire\sire_vectors.sqlite3")
BACKUP_ROOT = Path(r"D:\sire\db-backups")
WORKER_LOCK = Path(r"D:\sire\sire_ledger\sync_queue\worker.lock")
QUEUE = Path(r"D:\sire\sire_ledger\sync_queue")


def pid_alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def counts(path: Path) -> dict:
    c = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    r = {"integrity": c.execute("PRAGMA integrity_check").fetchone()[0],
         "knowledge_records": c.execute("SELECT COUNT(*) FROM knowledge_records").fetchone()[0],
         "chunks": c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
         "task_records": c.execute("SELECT COUNT(*) FROM task_records").fetchone()[0],
         "proposals": c.execute("SELECT COUNT(*) FROM improvement_proposals").fetchone()[0],
         "aliases": c.execute("SELECT COUNT(*) FROM knowledge_aliases").fetchone()[0]}
    c.close()
    return r


def preflight() -> list[str]:
    problems = []
    if not CAND.is_file():
        problems.append(f"候选库不存在: {CAND}")
    else:
        cc = counts(CAND)
        print("候选库:", json.dumps(cc, ensure_ascii=False))
        if cc["integrity"] != "ok":
            problems.append("候选库 integrity_check 不是 ok")
        if cc["knowledge_records"] < 300 or cc["aliases"] < 40:
            problems.append("候选库计数异常（知识记录<300 或 别名<40）")
    if WORKER_LOCK.is_file():
        try:
            pid = json.loads(WORKER_LOCK.read_text(encoding="utf-8")).get("pid")
        except Exception:  # noqa: BLE001
            pid = None
        if pid and pid_alive(int(pid)):
            problems.append(f"归档 worker 仍在运行(PID {pid})，等它结束后再切换，否则会写到被替换的库上")
    running = []
    for q in QUEUE.glob("*.json"):
        try:
            if json.loads(q.read_text(encoding="utf-8")).get("state") == "running":
                running.append(q.name)
        except Exception:  # noqa: BLE001
            pass
    if running:
        problems.append("归档队列有 running 任务: " + ", ".join(running))
    if not os.environ.get("SIRE_DB_DELETE_PASSWORD_SHA256"):
        problems.append("未配置 SIRE_DB_DELETE_PASSWORD_SHA256，删除保护无法校验密码")
    for p in (WORKING,):
        if not p.is_file():
            problems.append(f"目标库不存在: {p}")
    return problems


def replace(target: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    before = sha(target)
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(target) + suffix)
        if src.exists():
            shutil.copy2(src, backup_dir / (target.stem + suffix if suffix else target.name))
    bk = backup_dir / target.name
    if sha(bk) != before:
        raise RuntimeError(f"备份校验失败: {bk}")
    print(f"  已备份并校验: {bk}")
    for suffix in ("-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)
    tmp = target.with_suffix(".sqlite3.new")
    shutil.copy2(CAND, tmp)
    os.replace(tmp, target)
    after = counts(target)
    print("  替换后:", json.dumps(after, ensure_ascii=False))
    if after["integrity"] != "ok":
        raise RuntimeError("替换后 integrity_check 不是 ok，请按回滚命令恢复")
    print(f'  回滚命令: copy /Y "{bk}" "{target}"')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--archive", action="store_true", help="同时替换机器级归档库")
    a = ap.parse_args()
    problems = preflight()
    for p in problems:
        print("前置检查未通过:", p)
    if a.dry_run:
        print("DRY-RUN 结束：", "全部通过" if not problems else f"{len(problems)} 项未通过", "；未改动任何文件")
        return 1 if problems else 0
    if problems:
        return 2
    import sire_vector_db as vsd
    vsd.require_delete_password()  # 由用户本人在终端输入；输错会抛 PermissionError
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = BACKUP_ROOT / f"pre-cutover-{stamp}"
    print("替换工作库:", WORKING)
    replace(WORKING, backup_dir)
    if a.archive and ARCHIVE.is_file():
        print("替换归档库:", ARCHIVE)
        replace(ARCHIVE, backup_dir / "archive")
    print("完成。建议随后运行: python sire_vector_db.py stats")
    return 0


if __name__ == "__main__":
    sys.exit(main())
