"""归档 worker 批量语义：队列是为了不丢内容而不是阻塞内容；每次启动先合并全部未归档任务，全库索引只做一次。

隔离：QUEUE 指向临时目录，run_step 与 verify_database 全部替换，不碰真实队列与真实数据库。
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sire_archive_sync as sync  # noqa: E402

REAL_RUN_STEP = sync.run_step
REAL_VERIFY = sync.verify_database


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.queue = self.tmp / "sync_queue"
        self.queue.mkdir()
        self.patch_queue = mock.patch.object(sync, "QUEUE", self.queue)
        self.patch_queue.start()
        self.assertTrue(str(sync.QUEUE).startswith(str(self.tmp)))  # 隔离生效
        self.steps = []
        self.on_step = None
        self.patch_step = mock.patch.object(sync, "run_step", side_effect=self.fake_step)
        self.patch_step.start()
        self.verify_fail = set()
        self.verify_calls = []
        self.patch_verify = mock.patch.object(sync, "verify_database", side_effect=self.fake_verify)
        self.patch_verify.start()
        self.working = self.tmp / "work.sqlite3"
        self.archive = self.tmp / "archive.sqlite3"
        for db in (self.working, self.archive):
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")

    def tearDown(self):
        for p in (self.patch_queue, self.patch_step, self.patch_verify):
            p.stop()

    def fake_step(self, command, env):
        self.steps.append(command)
        if self.on_step:
            self.on_step(len(self.steps))

    def fake_verify(self, path, run_id, run_dir, check_integrity=True):
        self.verify_calls.append((str(path), run_id, check_integrity))
        if run_id in self.verify_fail:
            raise RuntimeError("校验失败 " + run_id)

    def job(self, name, state="pending", with_run=True, archive=True, env=None, attempts=0):
        run_dir = self.tmp / "runs" / name
        run_dir.mkdir(parents=True, exist_ok=True)
        if with_run:
            (run_dir / "run.json").write_text("{}", encoding="utf-8")
        data = {"state": state, "run_dir": str(run_dir), "project": "p", "run_id": name,
                "working_db": str(self.working), "archive_db": str(self.archive) if archive else "",
                "env": env or {}, "attempts": attempts}
        (self.queue / (name + ".json")).write_text(json.dumps(data), encoding="utf-8")
        return name

    def state(self, name):
        return json.loads((self.queue / (name + ".json")).read_text(encoding="utf-8"))

    def meta(self, db):
        with sqlite3.connect(db) as conn:
            return dict(conn.execute("SELECT key,value FROM meta").fetchall())

    def run_worker(self):
        out = StringIO()
        with redirect_stdout(out):
            code = sync.worker()
        return code, out.getvalue()


class BatchWorkerTest(BaseCase):
    def test_many_jobs_share_one_full_index_pass(self):
        names = [self.job("R1"), self.job("R2"), self.job("R3")]
        self.run_worker()
        # 1 次 reindex + 2 个库各 index、migrate 一次 = 5 步；旧逻辑每个任务都重复，3 个任务是 15 步
        self.assertEqual(5, len(self.steps))
        self.assertTrue(all(self.state(n)["state"] == "done" for n in names))
        self.assertTrue(all(self.state(n)["attempts"] == 1 for n in names))

    def test_done_jobs_are_skipped_and_unarchived_are_merged(self):
        self.job("R1", state="done")
        self.job("R2")
        self.job("R3")
        self.run_worker()
        self.assertEqual(5, len(self.steps))
        self.assertEqual("done", self.state("R2")["state"])
        self.assertEqual(0, self.state("R1")["attempts"])  # 已完成的不重复处理

    def test_invalid_job_does_not_block_others(self):
        self.job("R1")
        self.job("BAD", with_run=False)
        self.job("R3")
        self.run_worker()
        self.assertEqual("done", self.state("R1")["state"])
        self.assertEqual("done", self.state("R3")["state"])
        bad = self.state("BAD")
        self.assertEqual("pending", bad["state"])  # 内容不丢：仍在队列，等修复后重试
        self.assertIn("run.json missing", bad["last_error"])

    def test_one_verify_failure_only_affects_that_job(self):
        self.job("R1")
        self.job("R2")
        self.verify_fail = {"R2"}
        self.run_worker()
        self.assertEqual("done", self.state("R1")["state"])
        self.assertEqual("pending", self.state("R2")["state"])
        self.assertIn("校验失败", self.state("R2")["last_error"])

    def test_shared_step_failure_keeps_all_pending_and_logs_once(self):
        for name in ("R1", "R2", "R3"):
            self.job(name)
        self.on_step = lambda n: (_ for _ in ()).throw(RuntimeError("索引失败"))
        _, log = self.run_worker()
        for name in ("R1", "R2", "R3"):
            self.assertEqual("pending", self.state(name)["state"])
            self.assertIn("索引失败", self.state(name)["last_error"])
        self.assertEqual(1, log.count("批量全库步骤失败"))  # 共用步骤的错误只打印一次，不按任务重复

    def test_unconfigured_archive_runs_nothing_and_keeps_job(self):
        self.job("R1", archive=False)
        self.run_worker()
        self.assertEqual(0, len(self.steps))
        self.assertIn("not configured", self.state("R1")["last_error"])
        self.assertEqual("pending", self.state("R1")["state"])

    def test_different_environments_are_separate_batches(self):
        self.job("R1", env={"SIRE_TASK_ROOTS": "a"})
        self.job("R2", env={"SIRE_TASK_ROOTS": "a"})
        self.job("R3", env={"SIRE_TASK_ROOTS": "b"})
        self.run_worker()
        self.assertEqual(10, len(self.steps))  # 两个环境组，各 5 步


class RobustnessTest(BaseCase):
    def test_running_write_failure_only_affects_that_job(self):
        """批头写 running 被占用时，不能让整个 worker 中止，其余任务照常归档。"""
        self.job("R1")
        self.job("R2")
        self.job("R3")
        real_write = sync.write_json

        def flaky(path, value):
            if path.name == "R2.json" and value.get("state") == "running":
                raise PermissionError("文件被占用")
            return real_write(path, value)

        with mock.patch.object(sync, "write_json", side_effect=flaky):
            self.run_worker()
        self.assertEqual("done", self.state("R1")["state"])
        self.assertEqual("done", self.state("R3")["state"])
        self.assertEqual("pending", self.state("R2")["state"])  # 记录仍在，等下次重试

    def test_non_object_queue_file_does_not_stop_worker(self):
        (self.queue / "BROKEN.json").write_text("[1, 2]", encoding="utf-8")
        self.job("R1")
        self.run_worker()
        self.assertEqual("done", self.state("R1")["state"])
        self.assertEqual("[1, 2]", (self.queue / "BROKEN.json").read_text(encoding="utf-8"))  # 原文件不被覆盖

    def test_new_job_enqueued_during_run_is_merged_in_same_start(self):
        """用户原则：下一次归档先合并所有未归档内容。运行中新入队的任务不能等到下一次触发。"""
        self.job("R1")

        def enqueue_late(count):
            if count == 1:
                self.job("LATE")

        self.on_step = enqueue_late
        self.run_worker()
        self.assertEqual("done", self.state("R1")["state"])
        self.assertEqual("done", self.state("LATE")["state"])

    def test_meta_written_once_for_newest_verified_job(self):
        self.job("OLD")
        self.job("NEW")
        now = time.time()
        os.utime(self.tmp / "runs" / "OLD" / "run.json", (now - 1000, now - 1000))
        os.utime(self.tmp / "runs" / "NEW" / "run.json", (now, now))
        self.run_worker()
        for db in (self.working, self.archive):
            self.assertEqual("NEW", self.meta(db)["sire_last_run"])

    def test_meta_not_taken_from_failed_job(self):
        self.job("OLD")
        self.job("NEW")
        now = time.time()
        os.utime(self.tmp / "runs" / "OLD" / "run.json", (now - 1000, now - 1000))
        os.utime(self.tmp / "runs" / "NEW" / "run.json", (now, now))
        self.verify_fail = {"NEW"}
        self.run_worker()
        self.assertEqual("OLD", self.meta(self.working)["sire_last_run"])  # 校验失败的最新任务不能写成“已关闭”

    def test_integrity_checked_once_per_database(self):
        for name in ("R1", "R2", "R3"):
            self.job(name)
        self.run_worker()
        checks = [call for call in self.verify_calls if call[2]]
        self.assertEqual(2, len(checks))  # 工作库与归档库各一次，不再按任务重复整库扫描
        self.assertEqual(6, len(self.verify_calls))  # 但每个任务在每个库都校验自己的 run.json


class LockTest(BaseCase):
    def lock(self):
        return self.queue / "worker.lock"

    def write_lock(self, pid, age, token="other"):
        self.lock().write_text(json.dumps({"pid": pid, "token": token}), encoding="utf-8")
        past = time.time() - age
        os.utime(self.lock(), (past, past))

    def test_fresh_lock_blocks_second_worker(self):
        self.job("R1")
        self.write_lock(os.getpid(), 5)
        self.assertEqual(0, self.run_worker()[0])
        self.assertEqual(0, len(self.steps))
        self.assertEqual("pending", self.state("R1")["state"])

    def test_stale_lock_with_dead_process_is_taken_over(self):
        self.job("R1")
        self.write_lock(2147480000, sync.LOCK_STALE_SECONDS + 60)  # 不存在的 PID
        self.run_worker()
        self.assertEqual("done", self.state("R1")["state"])

    def test_old_lock_with_live_process_is_not_taken_over(self):
        """批次可能超过 30 分钟：持有进程还活着时不能因为锁文件旧就接管，否则出现双 worker 同时写库。"""
        self.job("R1")
        self.write_lock(os.getpid(), sync.LOCK_STALE_SECONDS + 600)
        self.run_worker()
        self.assertEqual(0, len(self.steps))
        self.assertEqual("pending", self.state("R1")["state"])

    def test_hung_lock_is_taken_over_even_if_process_alive(self):
        self.job("R1")
        self.write_lock(os.getpid(), sync.LOCK_HUNG_SECONDS + 60)
        self.run_worker()
        self.assertEqual("done", self.state("R1")["state"])

    def test_legacy_empty_lock_follows_age_rule(self):
        self.job("R1")
        self.lock().write_text("", encoding="utf-8")
        past = time.time() - (sync.LOCK_STALE_SECONDS + 60)
        os.utime(self.lock(), (past, past))
        self.run_worker()
        self.assertEqual("done", self.state("R1")["state"])

    def test_lock_is_released_after_run(self):
        self.job("R1")
        self.run_worker()
        self.assertFalse(self.lock().exists())

    def test_does_not_delete_lock_taken_over_by_another_worker(self):
        self.job("R1")

        def steal(count):
            if count == 1:
                self.lock().write_text(json.dumps({"pid": 1, "token": "someone-else"}), encoding="utf-8")

        self.on_step = steal
        self.run_worker()
        self.assertTrue(self.lock().exists())  # 结束时只删自己的锁
        self.assertEqual("someone-else", json.loads(self.lock().read_text(encoding="utf-8"))["token"])

    def test_heartbeat_refreshes_lock_mtime(self):
        """touch_lock 把旧的锁时间刷新到当前，长批次不会被误判为遗留锁。"""
        past = time.time() - 600
        self.lock().write_text("{}", encoding="utf-8")
        os.utime(self.lock(), (past, past))
        sync.touch_lock()
        self.assertGreater(self.lock().stat().st_mtime, past + 300)

    def test_pid_alive(self):
        self.assertTrue(sync.pid_alive(os.getpid()))
        self.assertFalse(sync.pid_alive(2147480000))
        self.assertFalse(sync.pid_alive(0))


class RunStepTest(unittest.TestCase):
    def test_timeout_is_passed_to_subprocess(self):
        """删掉 timeout 参数时必须失败：只模拟 TimeoutExpired 抓不到这一点。"""
        completed = subprocess.CompletedProcess(args=["x"], returncode=0, stdout="", stderr="")
        with mock.patch.object(sync.subprocess, "run", return_value=completed) as run:
            REAL_RUN_STEP([sys.executable, "-c", "pass"], {})
        self.assertEqual(sync.RUN_STEP_TIMEOUT, run.call_args.kwargs["timeout"])

    def test_timeout_becomes_runtime_error(self):
        with mock.patch.object(sync.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=1)):
            with self.assertRaises(RuntimeError) as ctx:
                REAL_RUN_STEP([sys.executable, "-c", "pass"], {})
        self.assertIn("timed out", str(ctx.exception))

    def test_nonzero_exit_is_error(self):
        with self.assertRaises(RuntimeError):
            REAL_RUN_STEP([sys.executable, "-c", "import sys; sys.exit(3)"], dict(os.environ))


class RaceAndRecordTest(BaseCase):
    def test_reenqueued_same_name_job_is_merged_in_same_start(self):
        """任务处理期间被同名重新入队：本次启动内要再合并处理一次，不能因为文件名已处理过就漏掉。"""
        self.job("R1")

        def requeue(count):
            if count == 1:
                data = self.state("R1")
                data["updated_at"] = "2099-01-01T00:00:00+00:00"  # 重新入队：记录被改写，updated_at 与我写入的不同
                data["state"] = "pending"
                (self.queue / "R1.json").write_text(json.dumps(data), encoding="utf-8")

        self.on_step = requeue
        self.run_worker()
        self.assertEqual("done", self.state("R1")["state"])
        self.assertEqual(10, len(self.steps))  # 两批，各 5 步

    def test_stale_snapshot_does_not_overwrite_new_record(self):
        """批处理期间记录被改写：旧快照不能用 done 覆盖新记录。只允许处理一轮来验证“不覆盖”这一性质本身。"""
        self.job("R1")

        def rewrite(count):
            if count == 1:
                data = self.state("R1")
                data.update(updated_at="2099-01-01T00:00:00+00:00", state="pending", note="新记录")
                (self.queue / "R1.json").write_text(json.dumps(data), encoding="utf-8")

        self.on_step = rewrite
        real = sync.collect_groups
        calls = []

        def one_round(attempted):
            calls.append(1)
            return real(attempted) if len(calls) == 1 else ({}, {})

        with mock.patch.object(sync, "spawn"), mock.patch.object(sync, "collect_groups", side_effect=one_round):
            self.run_worker()
        record = self.state("R1")
        self.assertEqual("新记录", record.get("note"))  # 新记录还在，没有被旧快照的 done 覆盖
        self.assertEqual("pending", record["state"])

    def test_stale_lock_takeover_rechecks_token(self):
        """判定过期后、删除前锁已被别的 worker 换成新锁：不能删别人的新锁。"""
        lock = self.queue / "worker.lock"
        lock.write_text(json.dumps({"pid": 2147480000, "token": "A"}), encoding="utf-8")
        past = time.time() - (sync.LOCK_STALE_SECONDS + 60)
        os.utime(lock, (past, past))
        answers = [{"pid": 2147480000, "token": "A"}, {"pid": 4242, "token": "B"}]
        with mock.patch.object(sync, "read_lock", side_effect=lambda p: answers.pop(0) if answers else {"token": "B"}):
            self.assertIsNone(sync.acquire_lock())
        self.assertTrue(lock.exists())  # 别人的新锁仍在

    def test_huge_pid_in_lock_does_not_crash(self):
        lock = self.queue / "worker.lock"
        lock.write_text(json.dumps({"pid": 10 ** 30, "token": "x"}), encoding="utf-8")
        past = time.time() - (sync.LOCK_STALE_SECONDS + 60)
        os.utime(lock, (past, past))
        token = sync.acquire_lock()
        self.assertIsNotNone(token)
        sync.release_lock(token)

    def test_record_missing_required_field_does_not_block_others(self):
        self.job("R1")
        self.job("R2")
        data = self.state("R2")
        data.pop("project")
        (self.queue / "R2.json").write_text(json.dumps(data), encoding="utf-8")
        self.run_worker()
        self.assertEqual("done", self.state("R1")["state"])
        self.assertEqual("pending", self.state("R2")["state"])
        self.assertIn("project", self.state("R2")["last_error"])

    def test_last_second_enqueue_after_release_respawns_worker(self):
        """释放锁之后才入队的任务：释放锁后再检查一次，有就重新拉起 worker，不留到下一次触发。"""
        self.job("R1")
        real_release = sync.release_lock

        def release_then_enqueue(token):
            real_release(token)
            self.job("LATE")

        with mock.patch.object(sync, "release_lock", side_effect=release_then_enqueue), \
                mock.patch.object(sync, "spawn") as spawn:
            self.run_worker()
        spawn.assert_called_once()
        self.assertEqual("pending", self.state("LATE")["state"])  # 没丢，等重新拉起的 worker 处理


class VerifyDatabaseTest(unittest.TestCase):
    """verify_database 的真实逻辑（其他用例里被替换掉了）：run.json 比对与完整性检查开关。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()
        (self.run_dir / "run.json").write_text('{"a": 1}', encoding="utf-8")
        self.db = self.tmp / "d.sqlite3"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE task_records(run_id TEXT, record_path TEXT, content TEXT)")

    def put(self, content):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO task_records VALUES(?,?,?)",
                         ("R", str((self.run_dir / "run.json").resolve()), content))

    def test_matching_record_passes(self):
        self.put('{"a": 1}')
        REAL_VERIFY(self.db, "R", self.run_dir)
        REAL_VERIFY(self.db, "R", self.run_dir, check_integrity=False)

    def test_missing_or_different_record_fails(self):
        with self.assertRaises(RuntimeError):
            REAL_VERIFY(self.db, "R", self.run_dir)  # 库里没有
        self.put("不同的内容")
        with self.assertRaises(RuntimeError):
            REAL_VERIFY(self.db, "R", self.run_dir)

    def test_integrity_flag_controls_pragma(self):
        self.put('{"a": 1}')
        calls = []
        real_connect = sqlite3.connect

        class Spy:
            def __init__(self, conn):
                self.conn = conn

            def __enter__(self):
                self.conn.__enter__()
                return self

            def __exit__(self, *args):
                return self.conn.__exit__(*args)

            def execute(self, sql, *args):
                calls.append(sql)
                return self.conn.execute(sql, *args)

        with mock.patch.object(sync.sqlite3, "connect", side_effect=lambda p: Spy(real_connect(p))):
            REAL_VERIFY(self.db, "R", self.run_dir, check_integrity=True)
            with_check = [c for c in calls if "integrity_check" in c]
            calls.clear()
            REAL_VERIFY(self.db, "R", self.run_dir, check_integrity=False)
            without_check = [c for c in calls if "integrity_check" in c]
        self.assertEqual(1, len(with_check))
        self.assertEqual(0, len(without_check))


if __name__ == "__main__":
    unittest.main()
