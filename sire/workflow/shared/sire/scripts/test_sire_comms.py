# -*- coding: utf-8 -*-
"""sire_comms 单元测试：python -m unittest test_sire_comms（在 scripts 目录下运行）"""
from __future__ import annotations

import io
import json
import os
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
        self.env = mock.patch.dict("os.environ", {"SIRE_COMMS_PUSH": "0"})  # 默认关闭实时推送，避免测试打到真实会话
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "comms"
        self.proj = Path(self.tmp.name) / "proj"
        self.proj.mkdir()
        self.patch = mock.patch.object(sc, "comms_dir", return_value=self.root)
        self.patch.start()

    def tearDown(self):
        self.env.stop()
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

    # ---- 配对辅助：Claude 会话 A ↔ Codex 会话 B ----
    A, B = "session-aaaa", "session-bbbb"

    def pair_up(self, a=None, b=None):
        a, b = a or self.A, b or self.B
        self.cli("--session", a, "pair", "start", "--me", "Claude", "--peer", "Codex")
        _, out = self.cli("--session", b, "pair", "start", "--me", "Codex")
        return json.loads(out)["pair"]

    def pch(self, pid):
        slug, _ = sc.resolve_project(str(self.proj))
        return sc.Channel(slug, None, pid)

    def test_c07_cli_status_and_projects(self):
        pid = self.pair_up()
        code, _ = self.cli("--session", self.B, "status", "--me", "Codex", "--text", "低代码设计器 | 50% | 运行时页面")
        self.assertEqual(code, 0)
        _, out = self.cli("--session", self.A, "status")
        self.assertIn("Codex：低代码设计器", out)
        self.cli("--session", self.A, "send", "--me", "Claude", "--to", "Codex", "--type", "handoff", "交接")
        buf = io.StringIO()
        with redirect_stdout(buf):
            sc.run(["projects"])
        self.assertIn("进行中配对 1 个", buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            sc.run(["--session", self.B, "inbox", "--me", "Codex", "--all-projects"])
        self.assertNotIn("合计 0 条", buf.getvalue())
        self.assertEqual(len(self.pch(pid).load()), 2, "认领通知 + 交接，共 2 条")

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

    def test_c10_unpaired_and_foreign_sessions_are_rejected(self):
        pid = self.pair_up()
        # 未配对的会话、未带会话一律拒绝，不回落到项目级通道
        for argv in (("send", "--me", "Claude", "--to", "Codex", "x"),
                     ("--session", "other-session", "send", "--me", "Claude", "--to", "Codex", "x"),
                     ("--session", "other-session", "inbox", "--me", "Claude"),
                     ("--session", "other-session", "session", "poll", "--me", "Claude"),
                     ("--session", "other-session", "status", "--me", "Claude", "--text", "x"),
                     # 会话 B 是 Codex 的，不能冒充 Claude
                     ("--session", self.B, "send", "--me", "Claude", "--to", "Codex", "x")):
            with self.assertRaises(sc.CommsError, msg=argv):
                self.cli(*argv)
        # 配对会话正常收发，消息记录双方会话
        self.assertEqual(self.cli("--session", self.A, "send", "--me", "Claude", "--to", "Codex", "--type", "request", "请复核")[0], 0)
        m = self.pch(pid).load()[-1]
        self.assertEqual((m["from_session"], m["to_session"]), (self.A, self.B))
        with mock.patch.dict("os.environ", {"SIRE_SESSION": self.B}):
            self.assertEqual(self.cli("reply", "--me", "Codex", "--re", str(m["id"]), "已复核")[0], 0)
        code, out = self.cli("--session", self.A, "log", "-n", "1")
        self.assertIn(f"Codex({self.B[:8]})→Claude({self.A[:8]})", out)
        self.assertEqual(self.ch().load(), [], "项目级通道不收配对消息")

    def test_c11_rebind_requires_flag(self):
        ch = self.ch()
        ch.bind("Claude", "session-one")
        self.assertEqual(ch.bind("Claude", "session-one")["session"], "session-one", "同会话重复绑定幂等")
        with self.assertRaises(sc.CommsError):
            ch.bind("Claude", "session-two")
        d = ch.bind("Claude", "session-two", rebind=True)
        self.assertEqual((d["session"], d["previous"]), ("session-two", "session-one"))
        with self.assertRaises(sc.CommsError):
            ch.bind("Claude", "bad id!")
        with self.assertRaises(sc.CommsError):
            self.cli("bind", "--me", "Codex")  # 旧 bind 已废弃
        pch = self.pch(self.pair_up())
        with self.assertRaises(sc.CommsError):  # 配对通道里即使 rebind=True 也不可改
            pch.bind("Claude", "session-zzzz", rebind=True)

    def test_c12_all_projects_inbox_skips_foreign_session(self):
        pid = self.pair_up()
        self.pch(pid).send("Codex", "Claude", "info", "hi")
        buf = io.StringIO()
        with redirect_stdout(buf):
            sc.run(["--session", "session-zzzz", "inbox", "--me", "Claude", "--all-projects"])
        self.assertIn("合计 0 条", buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            sc.run(["--session", self.A, "inbox", "--me", "Claude", "--all-projects"])
        self.assertNotIn("合计 0 条", buf.getvalue())

    def test_c13_session_idle_timeout_and_persistent(self):
        pid = self.pair_up()
        for _ in range(8):
            _, out = self.cli("--session", self.A, "session", "poll", "--me", "Claude")
        self.assertTrue(json.loads(out)["active"], "未满空闲上限不自停")
        os.environ["SIRE_COMMS_IDLE_SECONDS"] = "0"
        try:
            _, out = self.cli("--session", self.A, "session", "poll", "--me", "Claude")
        finally:
            del os.environ["SIRE_COMMS_IDLE_SECONDS"]
        self.assertFalse(json.loads(out)["active"], "空闲满上限自动结束")
        self.assertFalse(self.pch(pid).session("Codex", "status", "Claude")["active"], "对方同步关闭")
        self.assertEqual(self.ch().pairs()[pid]["state"], "closed", "结束后配对作废，双方会话释放")
        with self.assertRaises(sc.CommsError):
            self.cli("--session", self.A, "send", "--me", "Claude", "--to", "Codex", "x")
        # 释放后同一会话可重新配对
        pid2 = self.pair_up()
        self.assertNotEqual(pid, pid2)

    def test_c14_wait_returns_on_message_or_timeout(self):
        pid = self.pair_up()
        self.cli("--session", self.A, "ack", "--me", "Claude", "all")  # 先确认认领通知，避免被当作新消息
        _, out = self.cli("--session", self.A, "session", "wait", "--me", "Claude", "--timeout", "0.3", "--interval", "0.1")
        self.assertTrue(json.loads(out)["timeout"])
        timer = threading.Timer(0.3, lambda: self.pch(pid).send("Codex", "Claude", "info", "来信"))
        timer.start()
        _, out = self.cli("--session", self.A, "session", "wait", "--me", "Claude", "--timeout", "5", "--interval", "0.1")
        timer.join()
        r = json.loads(out)
        self.assertIn("来信", [m["text"] for m in r["messages"]])
        self.assertNotIn("timeout", r)

    def _age_lock(self, ch, res, hours):
        import datetime as _dt
        p = ch._lock_path(res)
        d = json.loads(p.read_text(encoding="utf-8"))
        d["time"] = (_dt.datetime.now() - _dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def test_c15_lock_stale_marking_and_forced_release(self):
        pid = self.pair_up()
        ch = self.ch()
        ch.lock("Codex", "mes-code", "T02")
        _, out = self.cli("locks")
        self.assertIn("已持有 0 分", out)
        self.assertNotIn("STALE", out)
        with self.assertRaises(sc.CommsError):
            self.cli("--session", self.A, "unlock", "--me", "Claude", "--resource", "mes-code", "--stale")  # 未过期不可
        self._age_lock(ch, "mes-code", 3)
        _, out = self.cli("locks")
        self.assertIn("STALE", out)
        self.assertIn("已持有 3 小时", out)
        self.assertNotIn("STALE", self.cli("locks", "--ttl", "5")[1], "--ttl 可调高阈值")
        with mock.patch.dict("os.environ", {"SIRE_COMMS_LOCK_TTL_HOURS": "5"}):
            self.assertNotIn("STALE", self.cli("locks")[1], "环境变量可调高阈值")
        with self.assertRaises(sc.CommsError):  # 过期也必须显式 --stale
            self.cli("--session", self.A, "unlock", "--me", "Claude", "--resource", "mes-code")
        self.assertEqual(self.cli("--session", self.A, "unlock", "--me", "Claude", "--resource", "mes-code", "--stale")[0], 0)
        self.assertEqual(ch.locks(), [])
        audit = self.pch(pid).load()[-1]
        self.assertEqual((audit["from"], audit["to"], audit["type"]), ("Claude", "Codex", "info"))
        self.assertIn("[审计]", audit["text"])

    def test_c16_pair_start_requires_session_and_valid_id(self):
        with self.assertRaises(sc.CommsError):
            self.cli("pair", "start", "--me", "Claude", "--peer", "Codex")  # 缺 --session
        with self.assertRaises(sc.CommsError):
            self.cli("--session", "bad id!", "pair", "start", "--me", "Claude", "--peer", "Codex")
        self.assertEqual(self.ch().pairs(), {}, "失败不留半成品配对")

    def test_c17_pair_flow_created_claimed_ready(self):
        a, b = self.A, self.B
        # 一端先说开始协作：新建待配对
        r1 = json.loads(self.cli("--session", a, "pair", "start", "--me", "Claude", "--peer", "Codex")[1])
        self.assertEqual(r1["result"], "created")
        pid = r1["pair"]
        self.assertEqual(self.ch().pairs()[pid]["state"], "pending")
        # 已在待配对的会话再说一次：只提示已就绪，不新建
        r2 = json.loads(self.cli("--session", a, "pair", "start", "--me", "Claude", "--peer", "Codex")[1])
        self.assertEqual((r2["result"], r2["pair"]), ("waiting", pid))
        self.assertEqual(len(self.ch().pairs()), 1)
        # 对端会话说开始协作（不点名）：自动认领，双方会话固定
        r3 = json.loads(self.cli("--session", b, "pair", "start", "--me", "Codex")[1])
        self.assertEqual((r3["result"], r3["pair"], r3["peer"]), ("claimed", pid, "Claude"))
        rec = self.ch().pairs()[pid]
        self.assertEqual((rec["state"], rec["members"]), ("active", {"Claude": a, "Codex": b}))
        notice = self.pch(pid).load()[-1]
        self.assertEqual((notice["from"], notice["to"], notice["type"]), ("Codex", "Claude", "question"), "认领后自动发连通测试 ping")
        self.assertIn("连通测试", notice["text"])
        self.assertEqual(rec["ping_id"], notice["id"])
        self.assertFalse(sc.pair_verified(self.ch(), pid, rec), "对方未回 pong 前不算连通")
        # 配对后任一端再说开始协作：已就绪，不变
        for sid, me in ((a, "Claude"), (b, "Codex")):
            r = json.loads(self.cli("--session", sid, "pair", "start", "--me", me)[1])
            self.assertEqual((r["result"], r["pair"]), ("ready", pid), me)
        self.assertEqual(len(self.ch().pairs()), 1)
        # 点名换对象：仍是已就绪，并提示不可更改
        r = json.loads(self.cli("--session", a, "pair", "start", "--me", "Claude", "--peer", "Qoder")[1])
        self.assertEqual(r["result"], "ready")
        self.assertIn("不能改成 Qoder", r["message"])

    def test_c18_new_session_creates_separate_pair(self):
        pid1 = self.pair_up()
        # 另一个 Claude 会话说开始协作：不抢占原配对，而是另建待配对
        r = json.loads(self.cli("--session", "session-cccc", "pair", "start", "--me", "Claude", "--peer", "Codex")[1])
        self.assertEqual(r["result"], "created")
        pid2 = r["pair"]
        self.assertNotEqual(pid1, pid2)
        r = json.loads(self.cli("--session", "session-dddd", "pair", "start", "--me", "Codex")[1])
        self.assertEqual((r["result"], r["pair"]), ("claimed", pid2))
        # 两对并存、消息互相隔离
        self.cli("--session", self.A, "send", "--me", "Claude", "--to", "Codex", "给第一对")
        self.cli("--session", "session-cccc", "send", "--me", "Claude", "--to", "Codex", "给第二对")
        self.assertEqual([m["text"] for m in self.pch(pid1).load() if "连通测试" not in m["text"]], ["给第一对"])
        self.assertEqual([m["text"] for m in self.pch(pid2).load() if "连通测试" not in m["text"]], ["给第二对"])
        # 原配对会话不变
        self.assertEqual(self.ch().pairs()[pid1]["members"], {"Claude": self.A, "Codex": self.B})

    def test_c19_fifo_when_multiple_pending_then_pick(self):
        ra = json.loads(self.cli("--session", "session-aaaa", "pair", "start", "--me", "Claude", "--peer", "Codex")[1])
        rb = json.loads(self.cli("--session", "session-cccc", "pair", "start", "--me", "Claude", "--peer", "Codex")[1])
        # 多个待配对：按入队先后，最早的先配，不再要用户选
        r = json.loads(self.cli("--session", self.B, "pair", "start", "--me", "Codex")[1])
        self.assertEqual((r["result"], r["pair"]), ("claimed", ra["pair"]))
        self.assertNotIn("Codex", self.ch().pairs()[rb["pair"]]["members"], "后入队的不受影响")
        # --pick 可指定；不存在的报错
        r = json.loads(self.cli("--session", "session-dddd", "pair", "start", "--me", "Codex", "--pick", rb["pair"])[1])
        self.assertEqual((r["result"], r["pair"]), ("claimed", rb["pair"]))
        with self.assertRaises(sc.CommsError):
            self.cli("--session", "session-eeee", "pair", "start", "--me", "Codex", "--pick", "p-none")

    def test_c24_create_requires_peer(self):
        with self.assertRaises(sc.CommsError):
            self.cli("--session", self.A, "pair", "start", "--me", "Claude")
        self.assertEqual(self.ch().pairs(), {}, "没点名对象不留半成品")

    def test_c25_tag_isolates_multiple_pairs_in_one_project(self):
        # 同项目两组：甲组与乙组各自入队，标签不同互不干扰，即使入队顺序交叉
        ca = json.loads(self.cli("--session", "session-c-jia", "pair", "start", "--me", "Claude", "--peer", "Codex", "--tag", "甲")[1])
        cb = json.loads(self.cli("--session", "session-c-yi", "pair", "start", "--me", "Claude", "--peer", "Codex", "--tag", "乙")[1])
        r = json.loads(self.cli("--session", "session-x-yi", "pair", "start", "--me", "Codex", "--tag", "乙")[1])
        self.assertEqual((r["result"], r["pair"]), ("claimed", cb["pair"]), "乙标签只配乙组，不抢更早入队的甲组")
        # 不带标签的 Codex 不会认领带标签的待配对，而是另建
        r = json.loads(self.cli("--session", "session-x-none", "pair", "start", "--me", "Codex", "--peer", "Claude")[1])
        self.assertEqual(r["result"], "created")
        r = json.loads(self.cli("--session", "session-x-jia", "pair", "start", "--me", "Codex", "--tag", "甲")[1])
        self.assertEqual((r["result"], r["pair"]), ("claimed", ca["pair"]))
        # 两组消息互相隔离
        self.cli("--session", "session-c-jia", "send", "--me", "Claude", "--to", "Codex", "只给甲")
        self.assertIn("只给甲", [m["text"] for m in self.pch(ca["pair"]).load()])
        self.assertNotIn("只给甲", [m["text"] for m in self.pch(cb["pair"]).load()])

    def test_c26_ping_pong_marks_connected(self):
        pid = self.pair_up()
        ping = self.pch(pid).load()[-1]
        self.assertFalse(sc.pair_verified(self.ch(), pid, self.ch().pairs()[pid]))
        self.assertIn("未连通", self.cli("pair", "list")[1])
        self.cli("--session", self.A, "reply", "--me", "Claude", "--re", str(ping["id"]), "pong")
        self.assertTrue(sc.pair_verified(self.ch(), pid, self.ch().pairs()[pid]))
        self.assertIn("已连通", self.cli("pair", "list")[1])
        # 主动重测：编号更新，重新回到未连通
        self.cli("--session", self.A, "pair", "ping", "--me", "Claude")
        self.assertFalse(sc.pair_verified(self.ch(), pid, self.ch().pairs()[pid]))

    def test_c28_request_files_conflict_and_force(self):
        pid = self.pair_up()
        pch = self.pch(pid)
        pch.send("Claude", "Codex", "request", "改 B", files=["src/a.py", "docs"], accept="a", evidence="b")
        with self.assertRaises(sc.CommsError):
            pch.send("Claude", "Codex", "request", "冲突", files=["docs/x.md"])  # 目录包含
        with self.assertRaises(sc.CommsError):
            pch.send("Codex", "Claude", "info", "x", files=["a"])  # 只有 request 可带字段
        m = pch.send("Claude", "Codex", "request", "强制并行", files=["docs/x.md"], force_overlap=True)
        self.assertEqual(m["files"], ["docs/x.md"])
        first = next(x for x in pch.load() if x["type"] == "request")
        pch.reply("Codex", first["id"], "done")
        pch.send("Claude", "Codex", "request", "回复后可再占", files=["src/a.py"])

    def test_c29_auto_pong_and_done_acceptance(self):
        pid = self.pair_up()
        pch = self.pch(pid)
        ping = next(x for x in pch.load() if x["text"].startswith(sc.PING_MARK))
        self.assertEqual(sc.auto_pong(pch, "Claude"), 1)
        self.assertEqual(sc.auto_pong(pch, "Claude"), 0, "不重复应答")
        self.assertTrue(sc.pair_verified(self.ch(), pid, self.ch().pairs()[pid]))
        self.assertTrue(any(x.get("re") == ping["id"] for x in pch.load()))
        pch.send("Claude", "Codex", "request", "干活")
        with self.assertRaises(sc.CommsError):
            self.cli("--session", self.A, "pair", "done", "--me", "Claude")  # 有未回复 request 且未声明
        self.cli("--session", self.A, "pair", "done", "--me", "Claude", "--unaccepted", "对方未交付")
        self.assertIn("关闭未验收：对方未交付", self.ch().pairs()[pid]["reason"])

    def test_c27_done_cleans_queue_unless_keep(self):
        pid = self.pair_up()
        # 用户说保持：完成后不清理
        self.cli("--session", self.A, "pair", "keep", "--me", "Claude")
        _, out = self.cli("--session", self.A, "pair", "done", "--me", "Claude")
        self.assertIn("未清理", out)
        self.assertEqual(self.ch().pairs()[pid]["state"], "active")
        # 取消保持后完成：清理，双方释放，再次协作须重新入队
        self.cli("--session", self.A, "pair", "keep", "--me", "Claude", "--off")
        _, out = self.cli("--session", self.A, "pair", "done", "--me", "Claude")
        self.assertIn("已清理", out)
        self.assertEqual(self.ch().pairs()[pid]["state"], "closed")
        with self.assertRaises(sc.CommsError):
            self.cli("--session", self.A, "send", "--me", "Claude", "--to", "Codex", "x")
        with self.assertRaises(sc.CommsError):
            self.cli("--session", self.A, "pair", "done", "--me", "Claude")  # 已清理，不能重复 done
        pid2 = self.pair_up()
        self.assertNotEqual(pid, pid2)

    def test_c28_hook_enqueues_with_real_session_id(self):
        import sire_comms_hook as hook
        def fire(prompt, session="hook-sess-1"):
            buf = io.StringIO()
            payload = json.dumps({"session_id": session, "cwd": str(self.proj), "prompt": prompt})
            with mock.patch.object(sys, "argv", ["hook", "--me", "Claude"]),                     mock.patch.object(sys, "stdin", io.StringIO(payload)), redirect_stdout(buf):
                hook.main()
            return buf.getvalue()
        out = fire("与 Codex 开始协作")
        self.assertIn("hook-sess-1", out)
        rec = next(iter(self.ch().pairs().values()))
        self.assertEqual((rec["state"], rec["creator"], rec["target"], rec["members"]), ("pending", "Claude", "Codex", {"Claude": "hook-sess-1"}))
        self.assertIn("等 Codex 认领", fire("今天天气怎么样"))  # 普通提示词带一行状态
        n = len(self.ch().pairs())
        fire("我们来讨论一下开始协作这个机制应该怎么设计才合理，别当成指令也别入队" * 2)  # 长句不触发
        self.assertEqual(len(self.ch().pairs()), n)
        self.assertEqual(fire("别的会话说话", session="hook-sess-2"), "", "不在队列的会话不输出")
        out = fire("结束协作")
        self.assertIn("用户要求结束协作", out)
        self.assertEqual(next(iter(self.ch().pairs().values()))["state"], "closed")

    def test_c20_push_to_codex_session(self):
        ch = self.ch()
        ch.bind("Codex", "session-bbbb")
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0, stdout="Queued", stderr="")

        with mock.patch.dict("os.environ", {"SIRE_COMMS_PUSH": "1", "SIRE_CODEX_EXE": __file__}), \
                mock.patch.object(sc.subprocess, "run", fake_run):
            ch.send("Claude", "Codex", "request", "长" * 700)
            ch.send("Codex", "Claude", "info", "不推给 Claude")
        self.assertEqual(len(calls), 1, "只推给绑定了会话的 Codex")
        cmd = calls[0]
        self.assertEqual((cmd[1], cmd[2], cmd[3]), ("queue", "--thread", "session-bbbb"))
        self.assertIn("全文见 messages.jsonl #1", cmd[-1])
        self.assertNotIn("长" * 601, cmd[-1])
        # 推送失败不影响落盘
        with mock.patch.dict("os.environ", {"SIRE_COMMS_PUSH": "1", "SIRE_CODEX_EXE": __file__}), \
                mock.patch.object(sc.subprocess, "run", lambda *a, **k: mock.Mock(returncode=1, stdout="", stderr="busy")):
            ch.send("Claude", "Codex", "info", "失败也要落盘")
        self.assertEqual(ch.load()[-1]["text"], "失败也要落盘")

    def test_c21_watch_emits_event_lines_and_closes(self):
        pid = self.pair_up()
        threading.Timer(0.4, lambda: self.pch(pid).send("Codex", "Claude", "info", "事件一")).start()
        threading.Timer(1.2, lambda: self.cli("--session", self.A, "session", "stop", "--me", "Claude")).start()
        buf = io.StringIO()
        with redirect_stdout(buf):
            sc.run(["--project", str(self.proj), "--session", self.A, "session", "watch", "--me", "Claude"])
        lines = [json.loads(l) for l in buf.getvalue().splitlines() if l.startswith("{")]
        self.assertIn("事件一", [l.get("text") for l in lines])
        self.assertTrue(lines[-1].get("closed"))

    def test_c22_resume_summary_and_stop_closes_peer(self):
        pid = self.pair_up()
        pch = self.pch(pid)
        for i in range(7):
            pch.send("Codex", "Claude", "info", f"消息{i}")
        pch.send("Claude", "Codex", "request", "长" * 500)
        code, out = self.cli("--session", self.A, "resume", "--me", "Claude")
        self.assertEqual(code, 0)
        self.assertIn(f"绑定 Claude → {self.A}", out)
        self.assertIn("active=True", out)
        self.assertEqual(out.count("\n  #"), 5, "只列最近5条")
        self.assertNotIn("长" * 201, out, "每条截断到200字")
        self.assertIn("待对方回复 1 条", out)
        with self.assertRaises(sc.CommsError):  # 非配对会话不能接手该身份
            self.cli("--session", "session-zzzz", "resume", "--me", "Claude")
        # stop：通知并关闭对方，配对作废；再次 stop 已无进行中的配对
        n = len(pch.load())
        code, out = self.cli("--session", self.A, "session", "stop", "--me", "Claude")
        self.assertTrue(json.loads(out)["peer_closed"])
        self.assertEqual(len(pch.load()), n + 1)
        self.assertEqual(self.ch().pairs()[pid]["state"], "closed")
        with self.assertRaises(sc.CommsError):
            self.cli("--session", self.A, "session", "stop", "--me", "Claude")

    def test_c23_pending_pair_expires_without_claim(self):
        r = json.loads(self.cli("--session", self.A, "pair", "start", "--me", "Claude", "--peer", "Codex")[1])
        os.environ["SIRE_COMMS_IDLE_SECONDS"] = "0"
        try:
            r2 = json.loads(self.cli("--session", self.A, "pair", "start", "--me", "Claude", "--peer", "Codex")[1])
        finally:
            del os.environ["SIRE_COMMS_IDLE_SECONDS"]
        self.assertEqual(r2["result"], "created")
        self.assertNotEqual(r2["pair"], r["pair"])
        self.assertEqual(self.ch().pairs()[r["pair"]]["state"], "closed")


if __name__ == "__main__":
    unittest.main()
