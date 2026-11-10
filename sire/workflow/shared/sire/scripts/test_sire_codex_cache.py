"""用量缓存的隔离回归测试源；不会访问真实 sessions 或缓存目录。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sire_codex_cache as cache


def event(kind, payload):
    return {"timestamp": "2026-11-10T00:00:00Z", "type": kind, "payload": payload}


def line(row):
    return (json.dumps(row) + "\n").encode("utf-8")


class CodexCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.ledger = self.base / "ledger"
        self.patch = patch.object(cache, "ledger_runs_dir", return_value=self.ledger)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.root = self.base / "sessions"
        self.root.mkdir()
        self.path = self.root / "rollout-date-session-a.jsonl"
        self.meta = event("session_meta", {"id": "session-a", "cwd": str(self.base)})
        self.first = event("token_usage_record", {
            "thread_id": "session-a", "turn_id": "turn-a", "response_id": "response-a",
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "thread_token_usage": {"input_tokens": 10, "output_tokens": 2}})
        self.path.write_bytes(line(self.meta) + line(self.first))

    def cache_data(self):
        path = cache._cache_path("events", str(self.path.resolve()))
        return cache._read_cache(path)

    def assert_matches_direct(self):
        self.assertEqual(cache.read_events(self.path), cache.read_events(self.path, use_cache=False))

    def test_cache_and_direct_semantics(self):
        context = event("turn_context", {"turn_id": "turn-a", "model": "model", "cwd": str(self.base)})
        count = event("event_msg", {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": 15, "output_tokens": 3},
            "last_token_usage": {"input_tokens": 5, "output_tokens": 1}},
            "rate_limits": {"primary": {"used_percent": 7, "window_minutes": 300, "resets_at": 123}}})
        with self.path.open("ab") as stream:
            for row in (context, event("event_msg", {"type": "task_started", "turn_id": "turn-a"}),
                        count, event("event_msg", {"type": "task_complete", "turn_id": "turn-a"})):
                stream.write(line(row))
        self.assert_matches_direct()
        self.assert_matches_direct()
        # 禁用缓存不触碰缓存目录或文件。
        with patch.object(cache, "_cache_path", side_effect=AssertionError("不应访问缓存")):
            cache.read_events(self.path, use_cache=False)

    def test_append_and_partial_line_offset(self):
        cache.read_events(self.path)
        committed = self.path.stat().st_size
        second = event("token_usage_record", {"response_id": "response-b",
                       "usage": {"input_tokens": 3, "output_tokens": 4}})
        encoded = line(second)
        with self.path.open("ab") as stream:
            stream.write(encoded[:-1])
        rows, warnings = cache.read_events(self.path)
        self.assertEqual(len(rows), 2)
        self.assertTrue(warnings)
        self.assertEqual(self.cache_data()["offset"], committed)
        with self.path.open("ab") as stream:
            stream.write(b"\n")
        rows, warnings = cache.read_events(self.path)
        self.assertEqual(len(rows), 3)
        self.assertFalse(warnings)
        self.assertEqual(self.cache_data()["offset"], self.path.stat().st_size)
        self.assert_matches_direct()

    def test_truncation_rebuilds(self):
        cache.read_events(self.path)
        self.path.write_bytes(line(self.meta))
        self.assert_matches_direct()
        self.assertEqual(len(cache.read_events(self.path)[0]), 1)

    def test_live_append_accepts_initial_prefix_without_retry(self):
        original_scan = cache._scan
        second = event("token_usage_record", {"response_id": "response-live",
                       "usage": {"input_tokens": 1, "output_tokens": 2}})
        for use_cache in (True, False):
            with self.subTest(use_cache=use_cache):
                self.path.write_bytes(line(self.meta) + line(self.first))
                if use_cache:
                    cache.read_events(self.path)

                def append_during_scan(stream, rows, warnings, limit):
                    offset = original_scan(stream, rows, warnings, limit)
                    with self.path.open("ab") as writer:
                        writer.write(line(second))
                    return offset

                with patch.object(cache, "_scan", side_effect=append_during_scan) as scan:
                    rows, warnings = cache.read_events(self.path, use_cache=use_cache)
                self.assertEqual(scan.call_count, 1)
                self.assertEqual(len(rows), 2)
                self.assertFalse(warnings)
                self.assertEqual(len(cache.read_events(self.path, use_cache=use_cache)[0]), 3)

    def test_live_prefix_changes_are_rejected(self):
        original_scan = cache._scan
        initial = line(self.meta) + line(self.first)
        for mutation in ("truncate", "replace", "rewrite-and-append"):
            with self.subTest(mutation=mutation):
                self.path.write_bytes(initial)

                def mutate_during_scan(stream, rows, warnings, limit):
                    offset = original_scan(stream, rows, warnings, limit)
                    if mutation == "truncate":
                        self.path.write_bytes(line(self.meta))
                    elif mutation == "replace":
                        replacement = self.base / "live-replacement.jsonl"
                        replacement.write_bytes(initial)
                        os.replace(replacement, self.path)
                    else:
                        changed = initial.replace(b"session-a", b"session-b")
                        self.path.write_bytes(changed + line(self.first))
                    return offset

                with patch.object(cache, "_scan", side_effect=mutate_during_scan):
                    _, _, _, stable = cache._snapshot(self.path)
                self.assertFalse(stable)

    def test_replacement_rebuilds(self):
        cache.read_events(self.path)
        replacement = self.base / "replacement.jsonl"
        replacement.write_bytes(line(event("session_meta", {"id": "replacement", "cwd": str(self.base)})))
        os.replace(replacement, self.path)
        self.assert_matches_direct()
        self.assertEqual(cache.read_events(self.path)[0][0]["payload"]["id"], "replacement")

    def test_projection_excludes_private_content(self):
        secret = "PRIVATE_PROMPT_TOOL_RESPONSE_SENTINEL"
        with self.path.open("ab") as stream:
            for row in (event("response_item", {"content": secret}),
                        event("event_msg", {"type": "task_complete", "turn_id": "turn-a",
                                            "last_agent_message": secret}),
                        event("turn_context", {"turn_id": "turn-a", "model": "model", "prompt": secret}),
                        event("token_usage_record", {"usage": {"input_tokens": 1, "output_tokens": 1,
                                                               "tool_payload": secret}, "prompt": secret})):
                stream.write(line(row))
        rows, _ = cache.read_events(self.path)
        self.assertNotIn(secret, json.dumps(rows))
        for path in (self.ledger / "usage-cache").glob("*.json"):
            self.assertNotIn(secret, path.read_text(encoding="utf-8"))

    def test_location_root_and_session_isolation_and_hit_without_rglob(self):
        other_root = self.base / "other-sessions"
        other_root.mkdir()
        other = other_root / self.path.name
        other.write_bytes(line(self.meta))
        second = self.root / "rollout-date-session-b.jsonl"
        second.write_bytes(line(event("session_meta", {"id": "session-b", "cwd": str(self.base)})))
        self.assertEqual(cache.locate_session(self.root, "session-a"), self.path.resolve())
        self.assertEqual(cache.locate_session(other_root, "session-a"), other.resolve())
        self.assertEqual(cache.locate_session(self.root, "session-b"), second.resolve())
        with patch.object(Path, "rglob", side_effect=AssertionError("命中不应扫描")):
            self.assertEqual(cache.locate_session(self.root, "session-a"), self.path.resolve())
            self.assertEqual(cache.locate_session(other_root, "session-a"), other.resolve())

    def test_location_rejects_cache_path_outside_root(self):
        cache_path = cache._cache_path("location", str(self.root.resolve()) + "\x00session-a")
        outside = self.base / self.path.name
        outside.write_bytes(line(self.meta))
        cache._write_cache(cache_path, {"version": cache.VERSION, "root": str(self.root.resolve()),
                                      "session_id": "session-a", "path": str(outside)})
        self.assertEqual(cache.locate_session(self.root, "session-a"), self.path.resolve())

    def test_corrupt_cache_falls_back(self):
        cache.read_events(self.path)
        event_cache = cache._cache_path("events", str(self.path.resolve()))
        event_cache.write_bytes(b"{broken")
        self.assert_matches_direct()
        cache.locate_session(self.root, "session-a")
        location_cache = cache._cache_path("location", str(self.root.resolve()) + "\x00session-a")
        location_cache.write_bytes(b"null")
        self.assertEqual(cache.locate_session(self.root, "session-a"), self.path.resolve())

    def test_unwritable_cache_does_not_block_source(self):
        expected = cache.read_events(self.path, use_cache=False)
        # ledger_runs_dir 指向普通文件，缓存目录创建必然失败，跨平台无需 chmod。
        blocker = self.base / "not-a-directory"
        blocker.write_bytes(b"blocked")
        with patch.object(cache, "ledger_runs_dir", return_value=blocker):
            self.assertEqual(cache.read_events(self.path), expected)
            self.assertEqual(cache.locate_session(self.root, "session-a"), self.path.resolve())


if __name__ == "__main__":
    unittest.main()
