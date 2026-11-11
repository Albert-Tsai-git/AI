"""sire_gate 新增逻辑单测：提交命令匹配、本轮额度读数核对、Stop 缺计量拦截、遥测谓词。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sire_paths  # noqa: E402
import sire_gate  # noqa: E402
from sire_telemetry import reply_lacks_usage  # noqa: E402


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


class CommitRegexTest(unittest.TestCase):
    def test_hits(self):
        for cmd in ("git commit -m x", "cd a && git push", "git -C d commit", "git -c a=b push origin main",
                    "git status\ngit commit", "/usr/bin/git push"):
            self.assertTrue(sire_gate.COMMIT_RE.search(cmd), cmd)

    def test_misses(self):
        for cmd in ("git log --grep commit", "git add docs/commit-guide.md", "git checkout feature/push-fix",
                    'gh pr create --body "git push"', "cat commit-notes.txt", "git diff -- push.py"):
            self.assertIsNone(sire_gate.COMMIT_RE.search(cmd), cmd)


class UsageMarkedTest(unittest.TestCase):
    def setUp(self):
        # 台账根目录在 sire_paths 导入时固定（合并运行时早已指向真实台账），所以用 patch 指向临时目录，
        # 并断言生效后才写文件；绝不对真实台账做删除
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.object(sire_paths, "LEDGER_ROOT", Path(self.tmp))
        self.patch.start()
        self.assertTrue(str(sire_paths.ledger_runs_dir()).startswith(self.tmp))
        self.dir = sire_paths.ledger_runs_dir() / "usage-t"
        self.dir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        self.transcript = Path(self.tmp) / "tr.jsonl"
        self.transcript.write_text("\n".join(json.dumps(x) for x in [
            {"type": "user", "timestamp": iso(now - 30), "message": {"role": "user", "content": "提交代码"}},
            {"type": "assistant", "timestamp": iso(now - 20),
             "message": {"role": "assistant", "stop_reason": "tool_use", "content": []}}]) + "\n", encoding="utf-8")
        self.payload = {"transcript_path": str(self.transcript)}
        self.now = now

    def tearDown(self):
        self.patch.stop()

    def write(self, name, rows):
        (self.dir / name).write_text("\n".join(rows) + "\n", encoding="utf-8")

    def test_no_marks_denied(self):
        self.assertFalse(sire_gate.usage_marked_this_turn(self.payload))

    def test_old_mark_denied(self):
        self.write("plan.jsonl", [json.dumps({"ts": self.now - 1000})])
        self.assertFalse(sire_gate.usage_marked_this_turn(self.payload))

    def test_fresh_mark_allowed_including_override_name(self):
        self.write("plan-abc.jsonl", [json.dumps({"ts": self.now - 5})])
        self.assertTrue(sire_gate.usage_marked_this_turn(self.payload))

    def test_garbage_rows_do_not_crash(self):
        self.write("plan.jsonl", ["[]", "null", "{坏", json.dumps({"ts": self.now - 5})])
        self.assertTrue(sire_gate.usage_marked_this_turn(self.payload))

    def test_no_transcript_fails_open(self):
        self.assertTrue(sire_gate.usage_marked_this_turn({"transcript_path": "nope"}))


class StopCheckTest(unittest.TestCase):
    def run_stop(self, payload):
        r = subprocess.run([sys.executable, str(HERE / "sire_gate.py"), "stop-check"], input=json.dumps(payload),
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout.strip()

    def test_cases(self):
        base = {"session_id": "s"}
        full = "快速通道：否，完整流程 汇总"
        self.assertIn("block", self.run_stop({**base, "last_assistant_message": full})[1])
        self.assertIn("block", self.run_stop({**base, "last_assistant_message": "快速通道: 否 汇总"})[1])
        self.assertEqual("", self.run_stop({**base, "last_assistant_message": full + " 耗时:1秒 额度消耗：1"})[1])
        self.assertEqual("", self.run_stop({**base, "last_assistant_message": "快速通道：简单任务 答案"})[1])
        self.assertEqual("", self.run_stop({**base, "stop_hook_active": True, "last_assistant_message": full})[1])
        self.assertEqual("", self.run_stop({**base, "agent_id": "a", "last_assistant_message": full})[1])
        self.assertEqual(0, self.run_stop(base)[0])


class PredicateTest(unittest.TestCase):
    def test_predicate(self):
        self.assertTrue(reply_lacks_usage("快速通道：否 x"))
        self.assertTrue(reply_lacks_usage("快速通道:否 x"))
        self.assertFalse(reply_lacks_usage("快速通道：否 耗时 额度消耗"))
        self.assertFalse(reply_lacks_usage("快速通道：简单任务"))
        self.assertFalse(reply_lacks_usage("没有标记"))


if __name__ == "__main__":
    unittest.main()
