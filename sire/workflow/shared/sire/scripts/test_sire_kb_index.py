# -*- coding: utf-8 -*-
"""sire_kb.cmd_reindex 索引写入回归测试；只使用临时目录和 mock。"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sire_kb  # noqa: E402


class ReindexWriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.kb_dir = self.root / "knowledge"
        self.kb_dir.mkdir()
        self.index_path = self.kb_dir / "global_index.json"
        self.args = SimpleNamespace(warn_conflicts=True)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def record(rid="F-001", title="fixture title"):
        return {"id": rid, "letter": "F", "title": title}

    @staticmethod
    def index(records, last_updated):
        return {
            "records": [dict(record) for record in records],
            "total_records": len(records),
            "last_updated": last_updated,
        }

    def reindex(self, records, last_updated="2026-11-10T00:00:00Z"):
        output = io.StringIO()
        with mock.patch.object(sire_kb, "KB_DIR", str(self.kb_dir)), \
                mock.patch.object(sire_kb, "INDEX_PATH", str(self.index_path)), \
                mock.patch.object(sire_kb, "parse_records", return_value=(records, {})), \
                mock.patch.object(sire_kb, "build_index",
                                  side_effect=lambda rows: self.index(rows, last_updated)), \
                redirect_stdout(output):
            code = sire_kb.cmd_reindex(self.args)
        return code, output.getvalue()

    def test_kb_index_unchanged_content_only_changes_last_updated(self):
        records = [self.record()]
        old_index = self.index(records, "2026-11-09T00:00:00Z")
        original = (json.dumps(old_index, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self.index_path.write_bytes(original)
        old_mtime_ns = 1_600_000_000_000_000_000
        os.utime(self.index_path, ns=(old_mtime_ns, old_mtime_ns))

        code, output = self.reindex(records, "2026-11-10T00:00:00Z")

        self.assertEqual(code, 0)
        self.assertIn("reindex unchanged", output)
        self.assertEqual(self.index_path.read_bytes(), original)
        self.assertEqual(self.index_path.stat().st_mtime_ns, old_mtime_ns)

    def test_kb_index_substantive_count_or_record_change_is_written(self):
        cases = (
            ([self.record()], [self.record(), self.record("F-002", "second")]),
            ([self.record()], [self.record(title="updated title")]),
        )
        for old_records, new_records in cases:
            with self.subTest(old=old_records, new=new_records):
                case_dir = self.root / f"case-{len(list(self.root.glob('case-*')))}"
                case_dir.mkdir()
                self.kb_dir = case_dir
                self.index_path = case_dir / "global_index.json"
                self.index_path.write_text(
                    json.dumps(self.index(old_records, "2026-11-09T00:00:00Z"), ensure_ascii=False),
                    encoding="utf-8",
                )
                old_bytes = self.index_path.read_bytes()

                code, output = self.reindex(new_records, "2026-11-10T00:00:00Z")

                self.assertEqual(code, 0)
                self.assertIn("reindex ok", output)
                self.assertNotEqual(self.index_path.read_bytes(), old_bytes)
                written = json.loads(self.index_path.read_text(encoding="utf-8"))
                self.assertEqual(written["records"], new_records)
                self.assertEqual(written["total_records"], len(new_records))

    def test_kb_index_invalid_json_is_rebuilt(self):
        self.index_path.write_text("{ invalid json", encoding="utf-8")

        code, output = self.reindex([self.record()])

        self.assertEqual(code, 0)
        self.assertIn("reindex ok", output)
        rebuilt = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["records"], [self.record()])
        self.assertEqual(rebuilt["total_records"], 1)


if __name__ == "__main__":
    unittest.main()
