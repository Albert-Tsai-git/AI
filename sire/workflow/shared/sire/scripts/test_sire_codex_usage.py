# -*- coding: utf-8 -*-
"""Codex usage CLI 回归测试；仅使用临时 fixture，不触碰真实会话数据。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sire_process import no_console_kwargs  # noqa: E402


SCRIPT = Path(__file__).resolve().with_name("sire_usage.py")


class CodexUsageCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.transcript = self.root / "fixture.jsonl"
        self.stage_log = self.root / "stage_usage.jsonl"
        self.cwd = str(self.root / "fixture_meta_cwd")
        self.session_id = "fixture_meta_id"
        self.base = datetime(2026, 11, 10, 1, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def row(self, kind, payload, seconds=0):
        return {
            "timestamp": (self.base + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
            "type": kind,
            "payload": payload,
        }

    def write_fixture(self, rows=None):
        if rows is None:
            rows = [
                self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
                self.row("event_msg", {"type": "task_started", "turn_id": "turn-1"}, 1),
                self.row("turn_context", {"turn_id": "turn-1", "model": "fixture-model", "cwd": self.cwd}, 2),
                self.row("token_usage_record", {
                    "thread_id": self.session_id,
                    "turn_id": "turn-1",
                    "response_id": "response-1",
                    "usage": {"input_tokens": 120, "output_tokens": 30},
                    "thread_token_usage": {"input_tokens": 120, "output_tokens": 30},
                }, 3),
                self.row("event_msg", {
                    "type": "token_count",
                    "info": {"total_token_usage": {"input_tokens": 120, "output_tokens": 30}},
                    "rate_limits": {
                        "primary": {"used_percent": 10, "window_minutes": 300, "resets_at": 1794290000},
                        "secondary": {"used_percent": 20, "window_minutes": 10080, "resets_at": 1794890000},
                    },
                }, 4),
            ]
        self.transcript.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return self.transcript

    def cli(self, *args, transcript=None, cwd=None, session_id=None, client="codex",
            env_overrides=None, use_stage_log=True):
        env = os.environ.copy()
        env["SIRE_LEDGER_ROOT"] = str(self.root / "ledger-default")
        env.pop("CODEX_THREAD_ID", None)  # 保证 fixture 身份由显式 --session-id 决定
        if use_stage_log:
            env["SIRE_STAGE_LOG"] = str(self.stage_log)
        else:
            env.pop("SIRE_STAGE_LOG", None)
        if env_overrides:
            env.update(env_overrides)
        transcript = transcript or self.transcript
        cwd = cwd or self.cwd
        session_id = self.session_id if session_id is None else session_id
        cmd = [
            sys.executable, str(SCRIPT), "--client", client, "--file", str(transcript),
            "--cwd", cwd,
        ]
        if session_id:
            cmd.extend(["--session-id", session_id])
        cmd.extend(args)
        return subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", env=env,
            timeout=30, **no_console_kwargs(),
        )

    def test_c01_dual_usage_formats_are_deduplicated(self):
        self.write_fixture()
        result = self.cli("--session")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("输入 120", result.stdout)
        self.assertIn("输出 30", result.stdout)

    def test_c02_pre_turn_baseline_is_excluded_from_turn_usage(self):
        rows = [
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("token_usage_record", {
                "thread_id": self.session_id, "turn_id": "turn-old", "response_id": "old",
                "usage": {"input_tokens": 500, "output_tokens": 100},
                "thread_token_usage": {"input_tokens": 500, "output_tokens": 100},
            }, 1),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-new"}, 10),
            self.row("turn_context", {"turn_id": "turn-new", "model": "fixture-model", "cwd": self.cwd}, 11),
            self.row("token_usage_record", {
                "thread_id": self.session_id, "turn_id": "turn-new", "response_id": "new",
                "usage": {"input_tokens": 40, "output_tokens": 12},
                "thread_token_usage": {"input_tokens": 540, "output_tokens": 112},
            }, 12),
        ]
        self.write_fixture(rows)
        result = self.cli("--turn")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("输入 40", result.stdout)
        self.assertIn("输出 12", result.stdout)
        self.assertNotIn("输入 540", result.stdout)

    def test_c03_missing_usage_is_reported_not_zero(self):
        self.write_fixture([
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-1"}, 1),
            self.row("turn_context", {"turn_id": "turn-1", "model": "fixture-model", "cwd": self.cwd}, 2),
        ])
        result = self.cli("--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("没有真实记录", result.stdout)

    def test_c04_file_for_another_session_is_rejected(self):
        self.write_fixture([
            self.row("session_meta", {"id": "foreign-session", "cwd": self.cwd}),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-1"}, 1),
            self.row("turn_context", {"turn_id": "turn-1", "model": "fixture-model", "cwd": self.cwd}, 2),
        ])
        result = self.cli("--session")
        self.assertNotEqual(result.returncode, 0)

    def test_c05_repeated_stage_end_does_not_double_count(self):
        self.write_fixture()
        start = self.cli("--stage-start", "R1")
        self.assertEqual(start.returncode, 0, start.stderr)
        first = self.cli("--stage-end", "R1")
        self.assertEqual(first.returncode, 0, first.stderr)
        first_log = self.stage_log.read_text(encoding="utf-8")
        second = self.cli("--stage-end", "R1")
        self.assertEqual(second.returncode, 0, second.stderr)
        second_log = self.stage_log.read_text(encoding="utf-8")
        self.assertEqual(first_log, second_log)

    def test_c06_missing_session_does_not_guess_latest(self):
        decoy = self.root / "codex-home" / "sessions" / "2026" / "11" / "10" / f"rollout-{self.session_id}.jsonl"
        decoy.parent.mkdir(parents=True)
        self.write_fixture()
        decoy.write_text(self.transcript.read_text(encoding="utf-8"), encoding="utf-8")
        env = os.environ.copy()
        env["SIRE_LEDGER_ROOT"] = str(self.root / "ledger-default")
        env.pop("CODEX_THREAD_ID", None)
        env.pop("CODEX_SESSION_ID", None)
        env["CODEX_HOME"] = str(self.root / "codex-home")
        env["SIRE_STAGE_LOG"] = str(self.stage_log)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--client", "codex", "--turn", "--cwd", self.cwd],
            capture_output=True, text=True, encoding="utf-8",
            env=env,
            timeout=30, **no_console_kwargs(),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("输入 70", result.stdout)

    def test_c07_cumulative_usage_rollback_emits_warning(self):
        rows = [
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-1"}, 1),
            self.row("turn_context", {"turn_id": "turn-1", "model": "fixture-model", "cwd": self.cwd}, 2),
            self.row("event_msg", {
                "type": "token_count", "info": {"total_token_usage": {"input_tokens": 400, "output_tokens": 80}},
                "rate_limits": {},
            }, 3),
            self.row("event_msg", {
                "type": "token_count", "info": {"total_token_usage": {"input_tokens": 200, "output_tokens": 40}},
                "rate_limits": {},
            }, 4),
        ]
        self.write_fixture(rows)
        result = self.cli("--session")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(word in result.stdout.lower() for word in ("回退", "rollback", "下降", "警告")))

    def test_c08_claude_client_reads_claude_message_fixture(self):
        claude_path = self.root / "fixture_claude_session.jsonl"
        claude_cwd = str(self.root / "claude_project")
        rows = [
            {"timestamp": "2026-11-10T01:00:00Z", "type": "user", "message": {"content": "hello"}},
            {"timestamp": "2026-11-10T01:00:01Z", "type": "assistant", "message": {
                "id": "claude-response-1", "model": "fixture-claude-model",
                "usage": {"input_tokens": 21, "output_tokens": 7},
            }},
        ]
        claude_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        result = self.cli("--session", transcript=claude_path, cwd=claude_cwd,
                          session_id=claude_path.stem, client="claude")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fixture-claude-model", result.stdout)

    def test_c09_two_sessions_sharing_stage_log_remain_isolated(self):
        self.write_fixture()
        other_path = self.root / "other.jsonl"
        other_id = "other-session"
        other_cwd = str(self.root / "other-cwd")
        other_rows = [
            self.row("session_meta", {"id": other_id, "cwd": other_cwd}),
            self.row("event_msg", {"type": "task_started", "turn_id": "other-turn"}, 1),
            self.row("turn_context", {"turn_id": "other-turn", "model": "fixture-model", "cwd": other_cwd}, 2),
        ]
        other_path.write_text("".join(json.dumps(row) + "\n" for row in other_rows), encoding="utf-8")
        self.cli("--stage-start", "R1")
        self.cli("--stage-start", "R1", transcript=other_path, cwd=other_cwd, session_id=other_id)
        result = self.cli("--stage-end", "R1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("没有真实记录（未记录当前会话回合的开始时刻）", result.stdout)
        rows = [json.loads(line) for line in self.stage_log.read_text(encoding="utf-8").splitlines()]
        scopes = {json.dumps(row["scope"], sort_keys=True) for row in rows}
        self.assertGreaterEqual(len(scopes), 2)

    def test_c10_quota_uses_300_minute_snapshot(self):
        rows = [
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 0, "output_tokens": 0}},
                "rate_limits": {"primary": {"used_percent": 10, "window_minutes": 300, "resets_at": 1794290000}}}, 0),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-1"}, 1),
            self.row("turn_context", {"turn_id": "turn-1", "model": "fixture-model", "cwd": self.cwd}, 2),
            self.row("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 1, "output_tokens": 1}},
                "rate_limits": {"primary": {"used_percent": 12, "window_minutes": 300, "resets_at": 1794290000}}}, 4),
        ]
        self.write_fixture(rows)
        result = self.cli("--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot_time = datetime.fromtimestamp(1794272404, timezone.utc).astimezone().strftime("%H:%M:%S")
        self.assertIn(f"快照 {snapshot_time} 已用 12%", result.stdout)
        self.assertIn("12%", result.stdout)
        self.assertIn("10% → 12%", result.stdout)

    def test_c11_quota_reset_does_not_report_a_delta(self):
        rows = [
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 0, "output_tokens": 0}},
                "rate_limits": {"primary": {"used_percent": 80, "window_minutes": 300, "resets_at": 1794290000}}}, 0),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-1"}, 1),
            self.row("turn_context", {"turn_id": "turn-1", "model": "fixture-model", "cwd": self.cwd}, 2),
            self.row("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 1, "output_tokens": 1}},
                "rate_limits": {"primary": {"used_percent": 5, "window_minutes": 300, "resets_at": 1794300000}}}, 4),
        ]
        self.write_fixture(rows)
        result = self.cli("--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("窗口已变化或读数回退，差值没有真实记录", result.stdout)
        self.assertNotIn("账号全局读数变化", result.stdout)

    def test_c12_quota_without_pre_turn_baseline_says_no_real_start_reading(self):
        rows = [
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-1"}, 1),
            self.row("turn_context", {"turn_id": "turn-1", "model": "fixture-model", "cwd": self.cwd}, 2),
            self.row("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 1, "output_tokens": 1}},
                "rate_limits": {"primary": {"used_percent": 12, "window_minutes": 300, "resets_at": 1794290000}}}, 4),
        ]
        self.write_fixture(rows)
        result = self.cli("--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("任务开始读数没有真实记录", result.stdout)
        self.assertNotIn("账号全局读数变化", result.stdout)

    def test_c13_identical_cumulative_snapshot_reports_zero_for_new_turn(self):
        rows = [
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-old"}, 1),
            self.row("turn_context", {"turn_id": "turn-old", "model": "fixture-model", "cwd": self.cwd}, 2),
            self.row("token_usage_record", {
                "thread_id": self.session_id, "turn_id": "turn-old", "response_id": "old-response",
                "usage": {"input_tokens": 500, "output_tokens": 100},
                "thread_token_usage": {"input_tokens": 500, "output_tokens": 100},
            }, 3),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-new"}, 10),
            self.row("turn_context", {"turn_id": "turn-new", "model": "fixture-model", "cwd": self.cwd}, 11),
            self.row("event_msg", {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": 500, "output_tokens": 100}}, "rate_limits": {}}, 12),
        ]
        self.write_fixture(rows)
        result = self.cli("--turn")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("输入 0", result.stdout)
        self.assertIn("输出 0", result.stdout)
        self.assertNotIn("额度消耗：没有真实记录", result.stdout)

    def test_c14_historical_final_quota_stops_at_selected_turn_end(self):
        rows = [
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 0, "output_tokens": 0}},
                "rate_limits": {"primary": {"used_percent": 10, "window_minutes": 300, "resets_at": 1794290000}}}, 0),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-old"}, 1),
            self.row("turn_context", {"turn_id": "turn-old", "model": "fixture-model", "cwd": self.cwd}, 2),
            self.row("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 0, "output_tokens": 0}},
                "rate_limits": {"primary": {"used_percent": 12, "window_minutes": 300, "resets_at": 1794290000}}}, 9),
            self.row("event_msg", {"type": "task_complete", "turn_id": "turn-old"}, 10),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-new"}, 20),
            self.row("turn_context", {"turn_id": "turn-new", "model": "fixture-model", "cwd": self.cwd}, 21),
            self.row("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 0, "output_tokens": 0}},
                "rate_limits": {"primary": {"used_percent": 40, "window_minutes": 300, "resets_at": 1794290000}}}, 22),
        ]
        self.write_fixture(rows)
        result = self.cli("--turn-id", "turn-old", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot_time = datetime.fromtimestamp(1794272409, timezone.utc).astimezone().strftime("%H:%M:%S")
        self.assertIn(f"快照 {snapshot_time} 已用 12%", result.stdout)
        self.assertIn("10% → 12%", result.stdout)
        self.assertNotIn("已用 40%", result.stdout)

    def test_c15_response_details_recover_after_cumulative_rollback_and_deduplicate(self):
        rows = [
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-1"}, 1),
            self.row("turn_context", {"turn_id": "turn-1", "model": "fixture-model", "cwd": self.cwd}, 2),
            self.row("token_usage_record", {
                "thread_id": self.session_id, "turn_id": "turn-1", "response_id": "r1",
                "usage": {"input_tokens": 1000, "output_tokens": 100},
                "thread_token_usage": {"input_tokens": 1000, "output_tokens": 100},
            }, 3),
            self.row("token_usage_record", {
                "thread_id": self.session_id, "turn_id": "turn-1", "response_id": "r2",
                "usage": {"input_tokens": 30, "output_tokens": 3},
                "thread_token_usage": {"input_tokens": 30, "output_tokens": 3},
            }, 4),
            self.row("token_usage_record", {
                "thread_id": self.session_id, "turn_id": "turn-1", "response_id": "r2",
                "usage": {"input_tokens": 30, "output_tokens": 3},
                "thread_token_usage": {"input_tokens": 30, "output_tokens": 3},
            }, 5),
            self.row("token_usage_record", {
                "thread_id": self.session_id, "turn_id": "turn-1", "response_id": "r3",
                "usage": {"input_tokens": 20, "output_tokens": 2},
                "thread_token_usage": {"input_tokens": 50, "output_tokens": 5},
            }, 6),
            self.row("event_msg", {"type": "token_count", "turn_id": "turn-1", "info": {
                "total_token_usage": {"input_tokens": 50, "output_tokens": 5}}, "rate_limits": {}}, 7),
        ]
        self.write_fixture(rows)
        result = self.cli("--turn")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("输入 1,050", result.stdout)
        self.assertIn("输出 105", result.stdout)
        self.assertIn("仅统计已落盘明细", result.stdout)
        self.assertIn("回退后重新起算", result.stdout)

    def test_c16_ambiguous_cumulative_rollback_does_not_confirm_candidate_delta(self):
        rows = [
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-1"}, 1),
            self.row("turn_context", {"turn_id": "turn-1", "model": "fixture-model", "cwd": self.cwd}, 2),
            self.row("event_msg", {"type": "token_count", "turn_id": "turn-1", "info": {
                "total_token_usage": {"input_tokens": 120, "output_tokens": 12}}, "rate_limits": {}}, 3),
            self.row("event_msg", {"type": "token_count", "turn_id": "turn-1", "info": {
                "total_token_usage": {"input_tokens": 80, "output_tokens": 8}}, "rate_limits": {}}, 4),
            self.row("event_msg", {"type": "token_count", "turn_id": "turn-1", "info": {
                "total_token_usage": {"input_tokens": 90, "output_tokens": 9}}, "rate_limits": {}}, 5),
            self.row("event_msg", {"type": "token_count", "turn_id": "turn-1", "info": {
                "total_token_usage": {"input_tokens": 120, "output_tokens": 12}}, "rate_limits": {}}, 6),
        ]
        self.write_fixture(rows)
        result = self.cli("--turn")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("候选增量", result.stdout)
        self.assertIn("无法区分重置与乱序", result.stdout)
        self.assertNotIn("输入 40", result.stdout)
        self.assertNotIn("输出 4", result.stdout)

    def claude_fixture(self):
        path = self.root / "fixture_claude_stage_session.jsonl"
        cwd = str(self.root / "claude_stage_project")
        rows = [
            {"timestamp": "2026-11-10T01:00:00Z", "type": "user", "message": {"content": "hello"}},
            {"timestamp": "2026-11-10T01:00:01Z", "type": "assistant", "message": {
                "id": "claude-stage-response", "model": "fixture-claude-model",
                "usage": {"input_tokens": 21, "output_tokens": 7},
            }},
        ]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path, cwd

    def test_c17_claude_explicit_file_ignores_session_env_but_explicit_id_must_match(self):
        path, cwd = self.claude_fixture()
        env = {"CLAUDE_SESSION_ID": "other"}
        accepted = self.cli("--session", transcript=path, cwd=cwd, session_id="",
                            client="claude", env_overrides=env)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn("fixture-claude-model", accepted.stdout)
        rejected = self.cli("--session", transcript=path, cwd=cwd, session_id="other",
                            client="claude", env_overrides=env)
        self.assertNotEqual(rejected.returncode, 0)

    def test_c18_claude_stage_log_key_is_applied_once_for_default_and_custom_paths(self):
        path, cwd = self.claude_fixture()
        ledger_root = self.root / "ledger"
        env = {"SIRE_LEDGER_ROOT": str(ledger_root)}
        default = self.cli("--stage-start", "R1", transcript=path, cwd=cwd,
                           session_id=path.stem, client="claude", env_overrides=env,
                           use_stage_log=False)
        self.assertEqual(default.returncode, 0, default.stderr)
        default_logs = list(ledger_root.glob("runs/usage-*/stages.jsonl"))
        self.assertEqual(len(default_logs), 1)
        key = default_logs[0].parent.name.removeprefix("usage-")
        self.assertTrue(key)

        custom_base = self.root / "custom_stage.jsonl"
        custom = self.cli("--stage-start", "R1", transcript=path, cwd=cwd,
                          session_id=path.stem, client="claude",
                          env_overrides={**env, "SIRE_STAGE_LOG": str(custom_base)})
        self.assertEqual(custom.returncode, 0, custom.stderr)
        expected_custom = self.root / f"custom_stage-{key}.jsonl"
        self.assertTrue(expected_custom.is_file())
        self.assertEqual(list(self.root.glob("custom_stage-*.jsonl")), [expected_custom])

    def test_c19_detail_turn_baseline_carries_into_later_cumulative_only_turn(self):
        rows = [
            self.row("session_meta", {"id": self.session_id, "cwd": self.cwd}),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-A"}, 1),
            self.row("turn_context", {"turn_id": "turn-A", "model": "fixture-model", "cwd": self.cwd}, 2),
            self.row("token_usage_record", {
                "thread_id": self.session_id, "turn_id": "turn-A", "response_id": "turn-a-response",
                "usage": {"input_tokens": 10, "output_tokens": 1},
                "thread_token_usage": {"input_tokens": 110, "output_tokens": 11},
            }, 3),
            self.row("event_msg", {"type": "token_count", "turn_id": "turn-A", "info": {
                "total_token_usage": {"input_tokens": 120, "output_tokens": 12}}, "rate_limits": {}}, 4),
            self.row("event_msg", {"type": "task_started", "turn_id": "turn-B"}, 10),
            self.row("turn_context", {"turn_id": "turn-B", "model": "fixture-model", "cwd": self.cwd}, 11),
            self.row("event_msg", {"type": "token_count", "turn_id": "turn-B", "info": {
                "total_token_usage": {"input_tokens": 130, "output_tokens": 13},
                "last_token_usage": {"input_tokens": 10, "output_tokens": 1}}, "rate_limits": {}}, 12),
        ]
        self.write_fixture(rows)
        result = self.cli("--turn")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("输入 10", result.stdout)
        self.assertIn("输出 1", result.stdout)
        self.assertNotIn("输入 20", result.stdout)
        self.assertNotIn("输出 2", result.stdout)


if __name__ == "__main__":
    unittest.main()
