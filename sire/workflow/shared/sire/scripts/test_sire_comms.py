# -*- coding: utf-8 -*-
"""sire_comms 单元测试：python -m unittest test_sire_comms（在 scripts 目录下运行）"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sire_comms as sc  # noqa: E402


class CommsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "comms"
        self.proj = Path(self.tmp.name) / "proj"
        self.proj.mkdir()
        self.patch = mock.patch.object(sc, "comms_dir", return_value=self.root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def ch(self):
        slug, path = sc.resolve_project(str(self.proj))
        return sc.Channel(slug, path)

    def cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = sc.run(["--project", str(self.proj), *argv])
        return code, buf.getvalue()

    def test_c01_data_lives_outside_project(self):
        ch = self.ch()
        ch.send("Claude", "Codex", "info", "hello")
        self.assertTrue((self.root / "projects" / ch.slug / "messages.jsonl").exists())
        self.assertEqual(list(self.proj.iterdir()), [], "项目目录内不应产生任何通讯文件")
        meta = json.loads((ch.dir / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(meta["path"]), self.proj.resolve())

    def test_c02_send_inbox_ack_reply_flow(self):
        ch = self.ch()
        m1 = ch.send("Claude", "Codex", "request", "请读 PROGRESS.md")
        self.assertEqual([m["id"] for m in ch.unread("Codex")], [m1["id"]])
        self.assertEqual([m["id"] for m in ch.waiting("Claude")], [m1["id"]])
        r = ch.reply("Codex", m1["id"], "已读")
        self.assertEqual((r["to"], r["type"], r["re"]), ("Claude", "reply", m1["id"]))
        self.assertEqual(ch.waiting("Claude"), [], "已回复的 request 不再等待")
        self.assertEqual(ch.ack("Codex", ["all"]), 1)
        self.assertEqual(ch.unread("Codex"), [])

    def test_c03_validation_errors(self):
        ch = self.ch()
        with self.assertRaises(sc.CommsError):
            ch.send("Claude", "Claude", "info", "x")
        with self.assertRaises(sc.CommsError):
            ch.send("Claude", "Codex", "spam", "x")
        with self.assertRaises(sc.CommsError):
            ch.send("Claude", "Codex", "info", "   ")
        with self.assertRaises(sc.CommsError):
            ch.send("Claude", "Codex", "reply", "x", re_id=99)
        with self.assertRaises(sc.CommsError):
            sc.agent("Nobody")
        m = ch.send("Claude", "Codex", "info", "x")
        with self.assertRaises(sc.CommsError):
            ch.ack("Claude", [str(m["id"])])  # 不是发给 Claude 的

    def test_c04_concurrent_send_ids_unique(self):
        ch = self.ch()
        errors = []

        def worker(who, to):
            try:
                for i in range(15):
                    ch.send(who, to, "info", f"{who}-{i}")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        ts = [threading.Thread(target=worker, args=("Claude", "Codex")), threading.Thread(target=worker, args=("Codex", "Claude"))]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])
        ids = [m["id"] for m in ch.load()]
        self.assertEqual(ids, list(range(1, 31)))

    def test_c05_stale_guard_and_broken_line(self):
        ch = self.ch()
        guard = ch.dir / ".send.lock"
        guard.write_text("")
        import os
        import time

        old = time.time() - 60
        os.utime(guard, (old, old))
        ch.send("Claude", "Codex", "info", "after stale guard")
        with ch.log.open("a", encoding="utf-8") as f:
            f.write('{"id": 2, "trunc')  # 模拟半行写入
        self.assertEqual(len(ch.load()), 1)

    def test_c06_locks(self):
        ch = self.ch()
        ch.lock("Claude", "db", "集成测试")
        with self.assertRaises(sc.CommsError):
            ch.lock("Codex", "db", "也想用")
        with self.assertRaises(sc.CommsError):
            ch.unlock("Codex", "db")
        ch.unlock("User", "db")  # 用户可强制释放
        self.assertEqual(ch.locks(), [])
        with self.assertRaises(sc.CommsError):
            ch.lock("Claude", "../etc", "非法资源名")

    def test_c07_cli_status_and_projects(self):
        code, _ = self.cli("status", "--me", "Codex", "--text", "低代码设计器 | 50% | 运行时页面")
        self.assertEqual(code, 0)
        _, out = self.cli("status")
        self.assertIn("Codex：低代码设计器", out)
        self.cli("send", "--me", "Claude", "--to", "Codex", "--type", "handoff", "交接")
        buf = io.StringIO()
        with redirect_stdout(buf):
            sc.run(["projects"])
        self.assertIn("Codex 未读 1", buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            sc.run(["inbox", "--me", "Codex", "--all-projects"])
        self.assertIn("全部项目未读合计 1 条", buf.getvalue())

    def test_c08_project_by_slug_and_identity_env(self):
        slug, _ = sc.resolve_project(str(self.proj))
        sc.Channel(slug, self.proj)
        self.assertEqual(sc.resolve_project(slug)[0], slug)
        with self.assertRaises(sc.CommsError):
            sc.resolve_project(str(self.proj / "missing"))
        with mock.patch.dict("os.environ", {"SIRE_AGENT": "codex"}):
            self.assertEqual(sc.agent(None), "Codex")
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(sc.CommsError):
                sc.agent(None)

    def test_c09_slug_is_stable(self):
        self.assertEqual(sc.slugify(Path("D:/code/mes")), "d--code-mes")


if __name__ == "__main__":
    unittest.main()
