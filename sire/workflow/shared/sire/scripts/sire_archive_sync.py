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
import uuid
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
    # 未配置归档库时保持空串：旧写法会把 Path("") 解析成当前目录，worker 误判为“已配置”
    if env.get("SIRE_ARCHIVE_DB"):
        archive_path = str(Path(env["SIRE_ARCHIVE_DB"]).expanduser().resolve())
    elif env.get("SIRE_ARCHIVE_ROOT"):
        archive_path = str((Path(env["SIRE_ARCHIVE_ROOT"]).expanduser() / "sire_vectors.sqlite3").resolve())
    elif archive:
        archive_path = str(archive.resolve())
    else:
        archive_path = ""
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


RUN_STEP_TIMEOUT = 3600   # 单个全库步骤（reindex/index/migrate）的超时秒数，超时按失败处理、任务留在队列
LOCK_STALE_SECONDS = 1800  # 锁超过此时长没有心跳且持有进程已不在，判为遗留锁
LOCK_HUNG_SECONDS = 7200   # 锁超过此时长没有心跳，即使进程还在也判为挂死，允许接管


def pid_alive(pid: int) -> bool:
    """进程是否还在。Windows 上不能用 os.kill(pid, 0)（会终止进程），改用 OpenProcess。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def run_step(command: list[str], env: dict[str, str]) -> None:
    try:
        result = subprocess.run(command, cwd=str(SHARED_SKILL_DIR), env=env,
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=RUN_STEP_TIMEOUT, **no_console_kwargs())
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"archive command timed out after {RUN_STEP_TIMEOUT}s: {' '.join(command[-3:])}") from exc
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "archive command failed")[-3000:])


def verify_database(path: Path, run_id: str, run_dir: Path, check_integrity: bool = True) -> None:
    with sqlite3.connect(str(path)) as conn:
        if check_integrity:  # 批量时每个库只需做一次整库完整性检查，逐任务只比对自己的 run.json
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(f"integrity_check={result}: {path}")
        row = conn.execute("SELECT content FROM task_records WHERE run_id=? AND record_path=?",
                           (run_id, str((run_dir / "run.json").resolve()))).fetchone()
        source = (run_dir / "run.json").read_text(encoding="utf-8-sig")
        if not row or row[0] != source:
            raise RuntimeError(f"final run.json missing or differs in database: {path}")


def queue_order(path: Path) -> tuple:
    """失败次数少的 job 先处理，避免队头长期失败的 job 阻塞其余归档。"""
    try:
        attempts = int(json.loads(path.read_text(encoding="utf-8")).get("attempts", 0))
    except (OSError, ValueError, AttributeError):
        attempts = 0
    return (attempts, path.name)


def current_updated_at(queue_file: Path) -> str | None:
    try:
        data = json.loads(queue_file.read_text(encoding="utf-8"))
        return data.get("updated_at") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_if_unchanged(queue_file: Path, job: dict, expect: str | None) -> bool:
    """写回前重读：队列记录的 updated_at 与我上次写入的不一致，说明期间被同名重新入队或别处修改，
    此时不能用旧快照覆盖新记录（内容不丢的前提）。返回是否真的写入。"""
    if expect is not None and current_updated_at(queue_file) != expect:
        print(f"{stamp()} {queue_file.name} 在批处理期间被重新入队或修改，保留新记录不覆盖", flush=True)
        return False
    write_json(queue_file, job)
    return True


def mark_failed(queue_file: Path, job: dict, exc: Exception, log: bool = True, expect: str | None = None) -> None:
    """单个任务失败：保留队列记录等下次重试，不影响同批其他任务。本函数自身不抛异常。"""
    if log:
        print(f"{stamp()} {queue_file.name} 失败: {exc}", flush=True)
    if not isinstance(job, dict) or not job:  # 读取失败或不是对象的文件不能用新对象覆盖原记录
        return
    job.update(state="pending", updated_at=stamp(), last_error=str(exc))
    try:
        write_if_unchanged(queue_file, job, expect)
    except OSError as write_exc:  # 写回被占用时只记录，不终止 worker，其余 job 继续
        print(f"{stamp()} {queue_file.name} 状态写回失败: {write_exc}", flush=True)


def group_key(job: dict, archive_db: Path) -> tuple:
    """同一工作库、同一归档库、同一环境的任务共用一次全库索引。"""
    return (job["working_db"], str(archive_db.resolve()),
            json.dumps(job.get("env", {}), sort_keys=True, ensure_ascii=False))


def read_lock(lock: Path) -> dict:
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def acquire_lock() -> str | None:
    """取得 worker 锁，返回本进程的令牌；已有存活 worker 时返回 None。
    锁里记 PID 和令牌：只有「很久没有心跳且进程已不在」或「超长时间没有心跳」才接管；结束时只删自己的锁。
    接管前重读令牌，确认仍是刚才判定过期的那把锁，避免误删别的 worker 刚建的新锁。"""
    lock = QUEUE / "worker.lock"
    if lock.exists():
        try:
            age = time.time() - lock.stat().st_mtime
        except OSError:
            age = 0.0
        observed = read_lock(lock)
        try:
            pid = int(observed.get("pid") or 0)
        except (TypeError, ValueError, OverflowError):
            pid = 0
        try:
            alive = pid_alive(pid)
        except Exception:  # noqa: BLE001  损坏的 pid 视为不存在
            alive = False
        if age > LOCK_HUNG_SECONDS or (age > LOCK_STALE_SECONDS and not alive):
            if read_lock(lock).get("token") == observed.get("token"):  # 仍是同一把过期锁才删
                try:
                    lock.unlink()
                except OSError:
                    pass
    token = uuid.uuid4().hex
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps({"pid": os.getpid(), "token": token, "started_at": stamp()}))
    return token


def release_lock(token: str) -> None:
    lock = QUEUE / "worker.lock"
    if read_lock(lock).get("token") == token:  # 锁已被别的 worker 接管时不删它的锁
        try:
            lock.unlink()
        except OSError:
            pass


def touch_lock() -> None:
    """刷新锁的心跳，让长批次不会被误判为遗留锁。"""
    try:
        os.utime(QUEUE / "worker.lock")
    except OSError:
        pass


def collect_groups(attempted: dict[str, str | None]) -> tuple[dict, dict]:
    """扫描队列，把本次启动内还没处理过的未完成任务按组合并；预检失败的任务留在队列。
    attempted 记录「文件名 → 我处理后写入的 updated_at」：同名任务被重新入队（updated_at 变了）会被重新合并进来。"""
    groups: dict[tuple, list[tuple[Path, dict]]] = {}
    archives: dict[tuple, Path] = {}
    for queue_file in sorted(QUEUE.glob("*.json"), key=queue_order):
        job = {}
        try:
            job = json.loads(queue_file.read_text(encoding="utf-8"))
            if not isinstance(job, dict):
                raise ValueError("queue file is not a JSON object")
            if queue_file.name in attempted and attempted[queue_file.name] == job.get("updated_at"):
                continue
            if job.get("state") == "done":
                attempted[queue_file.name] = job.get("updated_at")
                continue
            archive_db = Path(job.get("archive_db") or "")
            if not job.get("archive_db") or not archive_db.is_file():
                raise RuntimeError("machine archive database is not configured or unavailable")
            for key in ("run_dir", "project", "run_id", "working_db"):  # 必需键缺失的手工/遗留记录不能拖垮整批
                if not job.get(key):
                    raise RuntimeError(f"queue record missing required field: {key}")
            if not (Path(job["run_dir"]) / "run.json").is_file():
                raise RuntimeError(f"run.json missing: {Path(job['run_dir']) / 'run.json'}")  # 无效任务不拖慢整批
            key = group_key(job, archive_db)
            groups.setdefault(key, []).append((queue_file, job))
            archives[key] = archive_db
            attempted[queue_file.name] = job.get("updated_at")
        except Exception as exc:  # keep the durable queue entry for the next SIRE trigger
            mark_failed(queue_file, job, exc)
            attempted[queue_file.name] = job.get("updated_at") if isinstance(job, dict) else None
    return groups, archives


def run_json_mtime(job: dict) -> float:
    try:
        return (Path(job["run_dir"]) / "run.json").stat().st_mtime
    except (OSError, KeyError):
        return 0.0


def run_batch(items: list[tuple[Path, dict]], archive_db: Path) -> None:
    """一批任务：reindex / index / migrate 是全库操作，整批只做一次；之后逐任务校验自己的 run.json，
    全部校验后只给时间上最新的已校验任务写一次 meta。任何失败都只让相应任务留在队列等下次重试，不丢内容；
    写回前核对记录没有被重新入队或修改，避免用旧快照覆盖新记录。"""
    first = items[0][1]
    env = dict(os.environ)
    env.update(first.get("env", {}))
    databases = list(dict.fromkeys((first["working_db"], str(archive_db.resolve()))))
    ready: list[tuple[Path, dict]] = []
    for queue_file, job in items:
        job.update(state="running", attempts=int(job.get("attempts", 0)) + 1, updated_at=stamp(), last_error="")
        try:
            write_json(queue_file, job)
            ready.append((queue_file, job))
        except OSError as exc:  # 队列文件被占用：该任务留在队列，其余照常
            mark_failed(queue_file, job, exc)
    if not ready:
        return
    marks = {queue_file.name: job["updated_at"] for queue_file, job in ready}  # 我写入的 running 标记
    try:
        touch_lock()
        run_step([sys.executable, str(SCRIPTS / "sire_kb.py"), "reindex", "--warn-conflicts"], env)
        for database in databases:
            touch_lock()
            run_step([sys.executable, str(SCRIPTS / "sire_vector_db.py"), "--db", database, "index"], env)
            touch_lock()
            run_step([sys.executable, str(SCRIPTS / "sire_vector_db.py"), "--db", database, "migrate"], env)
    except Exception as exc:  # 共用的全库步骤失败：整批留在队列，错误只打印一次
        print(f"{stamp()} 批量全库步骤失败，{len(ready)} 个任务保留在队列等待重试: {exc}", flush=True)
        for queue_file, job in ready:
            mark_failed(queue_file, job, exc, log=False, expect=marks[queue_file.name])
        return
    verified: list[tuple[Path, dict]] = []
    integrity_checked: set[str] = set()
    for queue_file, job in ready:
        try:
            for database in databases:
                verify_database(Path(database), job["run_id"], Path(job["run_dir"]),
                                check_integrity=database not in integrity_checked)
                integrity_checked.add(database)
            verified.append((queue_file, job))
        except Exception as exc:
            mark_failed(queue_file, job, exc, expect=marks[queue_file.name])
        touch_lock()
    if not verified:
        return
    newest = max(verified, key=lambda item: run_json_mtime(item[1]))[1]
    try:
        for database in databases:
            with sqlite3.connect(database) as conn:
                conn.executemany("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                                 [("sire_last_project", newest["project"]),
                                  ("sire_last_run", newest["run_id"]),
                                  ("sire_last_status", "CLOSED")])
    except Exception as exc:
        for queue_file, job in verified:
            mark_failed(queue_file, job, exc, expect=marks[queue_file.name])
        return
    finished = []
    for queue_file, job in verified:
        job.update(state="done", updated_at=stamp(), last_error="")
        try:
            if write_if_unchanged(queue_file, job, marks[queue_file.name]):
                finished.append(job["run_id"])
        except OSError as exc:
            mark_failed(queue_file, job, exc, expect=marks[queue_file.name])
    print(f"{stamp()} 批量归档完成：{len(finished)}/{len(ready)} 个任务共用一次全库索引：" + ",".join(finished), flush=True)


def worker() -> int:
    """每次启动把队列里所有未归档的任务合并后归档；运行中新入队（含同名重新入队）的任务在同一次启动内继续合并处理；
    释放锁之后再扫一次，期间若又有新任务入队就重新拉起 worker，避免最后一刻入队的任务被漏掉。"""
    QUEUE.mkdir(parents=True, exist_ok=True)
    token = acquire_lock()
    if token is None:
        return 0
    attempted: dict[str, str | None] = {}
    try:
        for _ in range(10):  # 有上限，避免异常情况下无限循环
            groups, archives = collect_groups(attempted)
            if not groups:
                break
            for key, items in groups.items():
                try:
                    run_batch(items, archives[key])
                except Exception as exc:  # 单批异常不能终止 worker，也不能丢任务
                    print(f"{stamp()} 批处理异常，{len(items)} 个任务保留在队列: {exc}", flush=True)
                    for queue_file, job in items:
                        mark_failed(queue_file, job, exc, log=False)
                for queue_file, job in items:  # 以我自己最后写入的 updated_at 为准：文件里的值若不同，说明被重新入队，要再合并一次
                    attempted[queue_file.name] = job.get("updated_at")
    finally:
        release_lock(token)
    try:
        if collect_groups(dict(attempted))[0]:  # 释放锁后的最后一次检查
            spawn()
    except Exception as exc:  # noqa: BLE001
        print(f"{stamp()} 收尾重扫失败: {exc}", flush=True)
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
