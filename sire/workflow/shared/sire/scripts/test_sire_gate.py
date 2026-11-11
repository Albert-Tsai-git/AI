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


NL = chr(10)


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


class CommitRegexTest(unittest.TestCase):
    def test_hits(self):
        for cmd in ("git commit -m x", "cd a && git push", "git -C d commit", "git -c a=b push origin main",
                    "git status\ngit commit", "/usr/bin/git push",
                    # 复核补充的漏拦写法：环境变量与包装前缀、bash -c、控制流关键字、花括号、带引号参数、
                    # 带空格的 git 路径、其他会产生提交的子命令、gh pr merge、命令替换、xargs
                    "FOO=1 git commit", "sudo git push", "env git push", "time git push", "x | xargs git push",
                    'bash -c "git commit -m x"', "if x; then git commit", "{ git commit; }",
                    'git -C "my dir" commit', 'git -c user.name="A B" commit', "git --git-dir /x commit",
                    r'"C:\Program Files\Git\bin\git.exe" commit', r"C:\Git\bin\git.exe commit", "git.exe push",
                    "git merge x", "git revert HEAD", "git cherry-pick a", "git rebase main", "git am p.patch",
                    "gh pr merge 1", "$(git commit)", "`git push`"):
            self.assertTrue(sire_gate.COMMIT_RE.search(cmd), cmd)

    def test_misses(self):
        for cmd in ("git log --grep commit", "git add docs/commit-guide.md", "git checkout feature/push-fix",
                    'gh pr create --body "git push"', "cat commit-notes.txt", "git diff -- push.py",
                    "git commit-tree abc", "git commit-graph write", "git stash push", "echo git commit",
                    "git status", "git log --oneline",
                    # 冲突中途的恢复命令不能被拦
                    "git rebase --abort", "git merge --abort", "git rebase --continue", "git cherry-pick --quit"):
            self.assertIsNone(sire_gate.COMMIT_RE.search(cmd), cmd)


class UsageMarkedTest(unittest.TestCase):
    def setUp(self):
        # 台账根目录在 sire_paths 导入时固定（合并运行时早已指向真实台账），所以用 patch 指向临时目录，
        # 并断言生效后才写文件；绝不对真实台账做删除
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ)  # 隔离外部预设的 SIRE_PLAN_LOG
        self.env.start()
        os.environ.pop("SIRE_PLAN_LOG", None)
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
        self.env.stop()

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

    def test_plan_log_override_dir_is_scanned(self):
        """设置 SIRE_PLAN_LOG 后读数写到覆盖目录下的 <stem>-<key><suffix>，门禁必须读得到。"""
        override_dir = Path(self.tmp) / "custom"
        override_dir.mkdir()
        (override_dir / "plan-abc123.jsonl").write_text(json.dumps({"ts": self.now - 5}) + "\n", encoding="utf-8")
        self.assertFalse(sire_gate.usage_marked_this_turn(self.payload))  # 未设置环境变量时读不到
        with mock.patch.dict(os.environ, {"SIRE_PLAN_LOG": str(override_dir / "plan.jsonl")}):
            self.assertTrue(sire_gate.usage_marked_this_turn(self.payload))

    def test_plan_log_override_special_chars_in_stem(self):
        """覆盖路径文件名含 [ 时必须读得到（不能被当字符类而误拦）；含 ** 时不能抛异常也不能意外放行。
        注意 Windows 文件名不允许 *，含 ** 的文件写不出来，所以只验证不崩溃且判未记录。"""
        d = Path(self.tmp) / "bracket"
        d.mkdir()
        (d / "plan[1]-k1.jsonl").write_text(json.dumps({"ts": self.now - 5}) + NL, encoding="utf-8")
        with mock.patch.dict(os.environ, {"SIRE_PLAN_LOG": str(d / "plan[1].jsonl")}):
            self.assertTrue(sire_gate.usage_marked_this_turn(self.payload))
        empty = Path(self.tmp) / "empty"
        empty.mkdir()
        with mock.patch.dict(os.environ, {"SIRE_PLAN_LOG": str(empty / "a**b.jsonl")}):
            import sire_usage
            self.assertEqual([], sire_usage.usage_rows("plan"))
            self.assertFalse(sire_gate.usage_marked_this_turn(self.payload))

    def test_plan_log_override_missing_dir_does_not_crash(self):
        with mock.patch.dict(os.environ, {"SIRE_PLAN_LOG": str(Path(self.tmp) / "nope" / "plan.jsonl")}):
            self.assertFalse(sire_gate.usage_marked_this_turn(self.payload))

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
