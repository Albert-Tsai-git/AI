#!/usr/bin/env python
"""Queue database archival after a SIRE run has already reported completion."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from sire_paths import DATABASE_PATH, KNOWLEDGE_DIR, LEDGER_ROOT, SHARED_SKILL_DIR, archive_database_path
from sire_process import no_console_kwargs

QUEUE = LEDGER_ROOT / "sync_queue"
LOGS = LEDGER_ROOT / "sync_logs"
PATH_KEYS = ("SIRE_ROOT", "SIRE_DATA_DIR", "SIRE_VECTOR_DB", "SIRE_KB_DIR",
             "SIRE_EMBED_DIR", "SIRE_TASK_ROOTS", "SIRE_LEDGER_ROOT",
             "SIRE_ARCHIVE_ROOT", "SIRE_ARCHIVE_DB")
PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def spawn() -> bool:
    QUEUE.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    log = (LOGS / "worker.log").open("a", encoding="utf-8")
    try:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "worker"],
                         cwd=str(SHARED_SKILL_DIR), stdin=subprocess.DEVNULL,
                         stdout=log, stderr=subprocess.STDOUT, close_fds=True,
                         **no_console_kwargs(PROCESS_GROUP))
        return True
    except OSError as exc:
        log.write(f"{stamp()} worker launch failed: {exc}\n")
        log.close()
        return False


def enqueue(run_dir: str | Path, project: str, env: dict[str, str] | None = None) -> Path:
    env = dict(os.environ if env is None else env)
    run_dir = Path(run_dir).resolve()
    archive = archive_database_path()
    archive_path = str(Path(env.get("SIRE_ARCHIVE_DB") or env.get("SIRE_ARCHIVE_ROOT", "") and
                            (Path(env["SIRE_ARCHIVE_ROOT"]) / "sire_vectors.sqlite3") or
                            (archive or "")).expanduser().resolve())
    queue_file = QUEUE / f"{run_dir.name}.json"
    prior = {}
    if queue_file.exists():
        try:
            prior = json.loads(queue_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    record = {**prior, "run_id": run_dir.name, "run_dir": str(run_dir), "project": project,
              "working_db": str(Path(env.get("SIRE_VECTOR_DB") or DATABASE_PATH).resolve()),
              "archive_db": archive_path,
              "env": {key: env[key] for key in PATH_KEYS if env.get(key)},
              "state": "pending", "updated_at": stamp(), "last_error": ""}
    write_json(queue_file, record)
    spawned = spawn()
    if not spawned:
        record["last_error"] = "worker could not start; queued for the next SIRE run"
        write_json(queue_file, record)
    return queue_file


def kick_pending() -> None:
    if not QUEUE.is_dir():
        return
    changed = False
    for path in QUEUE.glob("*.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            if job.get("state") == "done":
                continue
            job["env"] = {**job.get("env", {}), **{key: os.environ[key] for key in PATH_KEYS if os.environ.get(key)}}
            archive = archive_database_path()
            if archive:
                job["archive_db"] = str(archive.resolve())
            job["state"] = "pending"
            write_json(path, job)
            changed = True
        except (OSError, ValueError):
            continue
    if changed:
        spawn()


def run_step(command: list[str], env: dict[str, str]) -> None:
    result = subprocess.run(command, cwd=str(SHARED_SKILL_DIR), env=env,
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            **no_console_kwargs())
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "archive command failed")[-3000:])


def verify_database(path: Path, run_id: str, run_dir: Path) -> None:
    with sqlite3.connect(str(path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"integrity_check={result}: {path}")
        row = conn.execute("SELECT content FROM task_records WHERE run_id=? AND record_path=?",
                           (run_id, str((run_dir / "run.json").resolve()))).fetchone()
        source = (run_dir / "run.json").read_text(encoding="utf-8-sig")
        if not row or row[0] != source:
            raise RuntimeError(f"final run.json missing or differs in database: {path}")


def worker() -> int:
    QUEUE.mkdir(parents=True, exist_ok=True)
    lock = QUEUE / "worker.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime > 1800:
        try:
            lock.unlink()
        except OSError:
            pass
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return 0
    os.close(fd)
    try:
        for queue_file in sorted(QUEUE.glob("*.json")):
            job = {}
            try:
                job = json.loads(queue_file.read_text(encoding="utf-8"))
                if job.get("state") == "done":
                    continue
                env = dict(os.environ)
                env.update(job.get("env", {}))
                run_dir = Path(job["run_dir"])
                archive_db = Path(job.get("archive_db") or "")
                if not job.get("archive_db") or not archive_db.is_file():
                    raise RuntimeError("machine archive database is not configured or unavailable")
                job.update(state="running", attempts=int(job.get("attempts", 0)) + 1,
                           updated_at=stamp(), last_error="")
                write_json(queue_file, job)
                run_step([sys.executable, str(SCRIPTS / "sire_kb.py"), "reindex"], env)
                for database in dict.fromkeys((job["working_db"], str(archive_db.resolve()))):
                    run_step([sys.executable, str(SCRIPTS / "sire_vector_db.py"), "--db", database, "index"], env)
                    run_step([sys.executable, str(SCRIPTS / "sire_vector_db.py"), "--db", database, "migrate"], env)
                for database in dict.fromkeys((job["working_db"], str(archive_db.resolve()))):
                    with sqlite3.connect(database) as conn:
                        conn.executemany("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                                         [("sire_last_project", job["project"]),
                                          ("sire_last_run", job["run_id"]),
                                          ("sire_last_status", "CLOSED")])
                for database in dict.fromkeys((job["working_db"], str(archive_db.resolve()))):
                    verify_database(Path(database), job["run_id"], run_dir)
                job.update(state="done", updated_at=stamp(), last_error="")
                write_json(queue_file, job)
            except Exception as exc:  # keep the durable queue entry for the next SIRE trigger
                job.update(state="pending", updated_at=stamp(), last_error=str(exc))
                write_json(queue_file, job)
    finally:
        try:
            lock.unlink()
        except OSError:
            pass
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        return worker()
    if len(sys.argv) > 1 and sys.argv[1] == "kick":
        kick_pending()
        return 0
    if len(sys.argv) < 4:
        print("usage: sire_archive_sync.py enqueue <run-dir> <project>", file=sys.stderr)
        return 2
    path = enqueue(sys.argv[2], sys.argv[3])
    print(f"数据库归档已排队（后台执行）：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
