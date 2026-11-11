"""额度日志公共读取、收尾门禁 usage_record_gate、遥测 Stop 记录、提交门禁端到端与回合起点的单测。

隔离原则：sire_paths.LEDGER_ROOT 在导入时固定（整库合并运行时早已指向真实台账），
所以一律用 mock.patch 指向临时目录，并在写任何文件前断言已生效；本文件不删除任何真实台账内容。
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sire_paths  # noqa: E402
import sire_run  # noqa: E402
import sire_telemetry  # noqa: E402
import sire_usage  # noqa: E402

NL = chr(10)


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def jl(*rows):
    return NL.join(json.dumps(r) if not isinstance(r, str) else r for r in rows) + NL


class LedgerCase(unittest.TestCase):
    """把台账根目录指向临时目录，并清掉可能影响结果的环境变量。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        for name in ("SIRE_PLAN_LOG", "SIRE_STAGE_LOG", "CODEX_THREAD_ID", "CODEX_SESSION_ID"):
            os.environ.pop(name, None)
        self.patch = mock.patch.object(sire_paths, "LEDGER_ROOT", Path(self.tmp))
        self.patch.start()
        self.assertTrue(str(sire_paths.ledger_runs_dir()).startswith(self.tmp))  # 隔离生效后才写文件
        self.dir = sire_paths.ledger_runs_dir() / "usage-t"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.now = time.time()

    def tearDown(self):
        self.patch.stop()
        self.env.stop()


class UsageRowsTest(LedgerCase):
    def test_default_dir_and_since_filter(self):
        (self.dir / "plan.jsonl").write_text(jl({"ts": self.now - 100}, {"ts": self.now - 1}), encoding="utf-8")
        self.assertEqual(2, len(sire_usage.usage_rows("plan")))
        self.assertEqual(1, len(sire_usage.usage_rows("plan", self.now - 10)))

    def test_kinds_are_separate(self):
        (self.dir / "plan.jsonl").write_text(jl({"ts": self.now}), encoding="utf-8")
        (self.dir / "stages.jsonl").write_text(jl({"ts": self.now, "kind": "end"}), encoding="utf-8")
        self.assertEqual("end", sire_usage.usage_rows("stage")[0]["kind"])
        self.assertNotIn("kind", sire_usage.usage_rows("plan")[0])

    def test_garbage_lines_are_skipped_per_line(self):
        (self.dir / "plan.jsonl").write_text(jl("[]", "null", "{坏", {"ts": "x"}, {"ts": self.now}), encoding="utf-8")
        self.assertEqual(1, len(sire_usage.usage_rows("plan")))

    def test_plan_and_stage_override_dirs(self):
        d = Path(self.tmp) / "custom"
        d.mkdir()
        (d / "plan-k1.jsonl").write_text(jl({"ts": self.now}), encoding="utf-8")
        (d / "stages-k1.jsonl").write_text(jl({"ts": self.now, "kind": "end"}), encoding="utf-8")
        (d / "other-k1.jsonl").write_text(jl({"ts": self.now}), encoding="utf-8")  # 不同 stem 不应被扫到
        self.assertEqual([], sire_usage.usage_rows("plan"))
        os.environ["SIRE_PLAN_LOG"] = str(d / "plan.jsonl")
        os.environ["SIRE_STAGE_LOG"] = str(d / "stages.jsonl")
        self.assertEqual(1, len(sire_usage.usage_rows("plan")))
        self.assertEqual(1, len(sire_usage.usage_rows("stage")))

    def test_override_special_chars_and_missing_dir(self):
        d = Path(self.tmp) / "br"
        d.mkdir()
        (d / "plan[1]-k1.jsonl").write_text(jl({"ts": self.now}), encoding="utf-8")
        os.environ["SIRE_PLAN_LOG"] = str(d / "plan[1].jsonl")
        self.assertEqual(1, len(sire_usage.usage_rows("plan")))
        os.environ["SIRE_PLAN_LOG"] = str(Path(self.tmp) / "nope" / "plan.jsonl")
        self.assertEqual([], sire_usage.usage_rows("plan"))


class UsageRecordGateTest(LedgerCase):
    def run_info(self, offset=100):
        return {"created": datetime.fromtimestamp(self.now - offset).strftime("%Y-%m-%d %H:%M:%S")}

    def put(self, plan=True, stage=True, ts=None):
        ts = self.now if ts is None else ts
        if plan:
            with (self.dir / "plan.jsonl").open("a", encoding="utf-8") as f:
                f.write(jl({"ts": ts, "five_hour": 1}))
        if stage:
            with (self.dir / "stages.jsonl").open("a", encoding="utf-8") as f:
                f.write(jl({"ts": ts, "kind": "end", "stage": "R1"}))

    def test_both_missing_blocks(self):
        message = sire_run.usage_record_gate(self.run_info(), "")
        self.assertIn("额度读数", message)
        self.assertIn("阶段计时", message)

    def test_usage_note_releases(self):
        self.assertIsNone(sire_run.usage_record_gate(self.run_info(), "未读到"))

    def test_only_plan_or_only_stage_blocks(self):
        self.put(stage=False)
        self.assertIn("阶段计时", sire_run.usage_record_gate(self.run_info(), ""))
        (self.dir / "plan.jsonl").unlink()
        self.put(plan=False)
        self.assertIn("额度读数", sire_run.usage_record_gate(self.run_info(), ""))

    def test_both_present_passes(self):
        self.put()
        self.assertIsNone(sire_run.usage_record_gate(self.run_info(), ""))

    def test_records_older_than_run_are_ignored(self):
        self.put(ts=self.now - 1000)
        self.assertIsNotNone(sire_run.usage_record_gate(self.run_info(), ""))

    def test_codex_needs_only_stage(self):
        os.environ["CODEX_THREAD_ID"] = "x"
        self.assertIsNotNone(sire_run.usage_record_gate(self.run_info(), ""))
        self.put(plan=False)
        self.assertIsNone(sire_run.usage_record_gate(self.run_info(), ""))

    def test_override_variables_are_honored(self):
        d = Path(self.tmp) / "ov"
        d.mkdir()
        (d / "plan-k.jsonl").write_text(jl({"ts": self.now}), encoding="utf-8")
        (d / "stages-k.jsonl").write_text(jl({"ts": self.now, "kind": "end"}), encoding="utf-8")
        self.assertIsNotNone(sire_run.usage_record_gate(self.run_info(), ""))
        os.environ["SIRE_PLAN_LOG"] = str(d / "plan.jsonl")
        os.environ["SIRE_STAGE_LOG"] = str(d / "stages.jsonl")
        self.assertIsNone(sire_run.usage_record_gate(self.run_info(), ""))  # 与提交门禁同一套发现规则

    def test_one_bad_line_does_not_drop_valid_rows(self):
        (self.dir / "plan.jsonl").write_text(jl("{坏", {"ts": self.now}), encoding="utf-8")
        (self.dir / "stages.jsonl").write_text(jl("{坏", {"ts": self.now, "kind": "end"}), encoding="utf-8")
        self.assertIsNone(sire_run.usage_record_gate(self.run_info(), ""))

    def test_start_only_stage_record_blocks(self):
        """只有阶段开始、没有结束记录，必须拦截（“至少一个阶段结束记录”这一验收点的唯一保障）。"""
        with (self.dir / "plan.jsonl").open("a", encoding="utf-8") as f:
            f.write(jl({"ts": self.now, "five_hour": 1}))
        with (self.dir / "stages.jsonl").open("a", encoding="utf-8") as f:
            f.write(jl({"ts": self.now, "kind": "start", "stage": "R1"}))
        self.assertIn("阶段计时", sire_run.usage_record_gate(self.run_info(), ""))

    def test_deeply_nested_bad_line_is_skipped(self):
        deep = "[" * 100000
        (self.dir / "plan.jsonl").write_text(jl(deep, {"ts": self.now}), encoding="utf-8")
        self.assertEqual(1, len(sire_usage.usage_rows("plan")))

    def test_unparsable_created_counts_all_history(self):
        self.put(ts=self.now - 100000)
        self.assertIsNone(sire_run.usage_record_gate({"created": "坏"}, ""))


class FinishWiringTest(LedgerCase):
    """cmd_finish 必须真正调用 usage_record_gate 并接上 --usage-note；删掉接线时这里要失败。"""

    def finish(self, usage_note="", gate=None):
        import argparse
        import contextlib
        import io
        args = argparse.Namespace(records="", no_archive=True, note="无新知识", pending_note="", usage_note=usage_note)
        run = {"channel": "light", "created": datetime.fromtimestamp(self.now - 100).strftime("%Y-%m-%d %H:%M:%S"),
               "gates": {}}
        out = io.StringIO()
        patches = [mock.patch.object(sire_run, "ctx", return_value=("r", "rid", self.tmp, (run, []))),
                   mock.patch.object(sire_run, "telemetry_pending_gate", return_value=None),
                   mock.patch.object(sire_run, "migration_sync_error", return_value=None)]
        if gate is not None:
            patches.append(mock.patch.object(sire_run, "usage_record_gate", side_effect=gate))
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(out))
            sire_run.cmd_finish(args)
        return out.getvalue()

    def test_finish_calls_gate_and_passes_note(self):
        calls = []

        def spy(run, note):
            calls.append(note)
            return "BLOCK-USAGE" if not note else None

        self.assertIn("BLOCK-USAGE", self.finish(gate=spy))
        self.assertNotIn("BLOCK-USAGE", self.finish(usage_note="未读到", gate=spy))
        self.assertEqual(["", "未读到"], calls)

    def test_finish_real_gate_message_when_records_missing(self):
        self.assertIn("耗时/额度记录缺失", self.finish())
        self.assertNotIn("耗时/额度记录缺失", self.finish(usage_note="未读到"))


class TelemetryStopTest(unittest.TestCase):
    """遥测 Stop 记录：被 sire_gate 拦过仍缺才记，非 Claude 端缺就记，齐全或快速通道不记。"""

    FULL = "快速通道：否，完整流程 汇总"

    def hook(self, client, reply, **extra):
        db = Path(tempfile.mkdtemp()) / "t.sqlite3"
        env = {**os.environ, "SIRE_TELEMETRY_DB": str(db)}
        payload = {"hook_event_name": "Stop", "session_id": "s", "cwd": "D:/x", "last_assistant_message": reply, **extra}
        subprocess.run([sys.executable, str(HERE / "sire_telemetry.py"), "hook", "--client", client],
                       input=json.dumps(payload), text=True, encoding="utf-8", env=env, capture_output=True)
        con = sqlite3.connect(db)
        try:
            return [r[0] for r in con.execute("SELECT event FROM events WHERE event='usage_missing'")]
        finally:
            con.close()

    def test_claude_first_stop_not_recorded(self):
        self.assertEqual([], self.hook("claude", self.FULL))

    def test_claude_after_block_recorded(self):
        self.assertEqual(["usage_missing"], self.hook("claude", self.FULL, stop_hook_active=True))

    def test_non_claude_recorded(self):
        self.assertEqual(["usage_missing"], self.hook("codex", self.FULL))

    def test_complete_or_fast_not_recorded(self):
        self.assertEqual([], self.hook("codex", self.FULL + " 耗时:1秒 额度消耗：1"))
        self.assertEqual([], self.hook("codex", "快速通道：简单任务 答案"))

    def test_halfwidth_colon_mode(self):
        self.assertEqual("full", sire_telemetry.detect_mode("快速通道: 否 汇总"))
        self.assertEqual("fast", sire_telemetry.detect_mode("快速通道：简单任务"))

    def test_both_markers_agree_with_predicate(self):
        text = "快速通道：简单任务 之后又写 快速通道：否"
        self.assertEqual("full", sire_telemetry.detect_mode(text))  # 取最后出现的标记
        self.assertTrue(sire_telemetry.reply_lacks_usage(text))

    def test_detect_quality_turns_event_into_finding(self):
        task = {"prompt": "普通提示"}
        events = [{"event": "usage_missing", "detail": "", "ok": 0}]
        self.assertIn("USAGE_MISSING", [item[0] for item in sire_telemetry.detect_quality(task, events)])
        self.assertNotIn("USAGE_MISSING", [item[0] for item in sire_telemetry.detect_quality(task, [])])


class TurnStartTest(unittest.TestCase):
    def entries(self, items):
        base = time.time() - 1000
        out = []
        for i, (kind, stop) in enumerate(items):
            obj = {"type": kind, "timestamp": iso(base + i * 10),
                   "message": {"role": kind, "stop_reason": stop, "content": "提示" if kind == "user" else []}}
            out.append((sire_usage.parse_ts(obj["timestamp"]), obj))
        return out

    def test_end_turn_resets_start(self):
        entries = self.entries([("user", None), ("assistant", "end_turn"), ("user", None), ("assistant", "tool_use")])
        self.assertEqual(2, sire_usage.turn_start_index(entries))

    def test_mid_turn_user_message_does_not_reset(self):
        entries = self.entries([("user", None), ("assistant", "tool_use"), ("user", None)])
        self.assertEqual(0, sire_usage.turn_start_index(entries))

    def test_no_entries_returns_none(self):
        self.assertIsNone(sire_usage.turn_start_index([]))


class GateCheckEndToEndTest(unittest.TestCase):
    """sire_gate.py check 作为真实钩子子进程：已加载 SIRE 的会话里，提交无读数拦截、有读数放行。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = {**os.environ, "SIRE_LEDGER_ROOT": self.tmp}
        for name in ("SIRE_PLAN_LOG", "SIRE_STAGE_LOG", "SIRE_GATE_OFF"):
            self.env.pop(name, None)
        self.now = time.time()
        self.transcript = Path(self.tmp) / "tr.jsonl"
        self.transcript.write_text(jl(
            {"type": "user", "timestamp": iso(self.now - 30), "message": {"role": "user", "content": "提交代码"}},
            {"type": "assistant", "timestamp": iso(self.now - 20),
             "message": {"role": "assistant", "stop_reason": "tool_use", "content": []}}), encoding="utf-8")
        self.run_gate("record", {"session_id": "e2e", "tool_name": "Skill",
                                 "tool_input": {"skill": "sire-global-workflow"}, "tool_response": {}})

    def run_gate(self, mode, payload):
        r = subprocess.run([sys.executable, str(HERE / "sire_gate.py"), mode], input=json.dumps(payload),
                           text=True, encoding="utf-8", env=self.env, capture_output=True)
        return r.stdout.strip()

    def check(self, command):
        return self.run_gate("check", {"session_id": "e2e", "tool_name": "Bash", "transcript_path": str(self.transcript),
                                       "tool_input": {"command": command}})

    def test_commit_denied_without_mark_then_allowed(self):
        self.assertIn("deny", self.check("git commit -m x"))
        self.assertEqual("", self.check("git status"))
        plan_dir = Path(self.tmp) / "runs" / "usage-e2e"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.jsonl").write_text(jl({"ts": self.now - 5}), encoding="utf-8")
        self.assertEqual("", self.check("git commit -m x"))

    def test_gate_off_and_unloaded_session(self):
        self.env["SIRE_GATE_OFF"] = "1"
        self.assertEqual("", self.check("git commit -m x"))
        self.env.pop("SIRE_GATE_OFF")
        other = self.run_gate("check", {"session_id": "never-loaded", "tool_name": "Bash",
                                        "tool_input": {"command": "ls"}})
        self.assertIn("deny", other)  # 未加载 SIRE 的会话仍走原拦截


if __name__ == "__main__":
    unittest.main()
