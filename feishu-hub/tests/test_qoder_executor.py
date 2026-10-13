# -*- coding: utf-8 -*-
"""[测试] Qoder 执行器与桌面 Hook：不联网、不起 Hub，只用假客户端断言协议行为。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "executors" / "common"))
sys.path.insert(0, str(ROOT / "executors" / "qoder"))
sys.path.insert(0, str(ROOT))

import executor as qe            # noqa: E402
import hook_stop as qhook        # noqa: E402
from hub import config as hubcfg  # noqa: E402
from hub import service as hubsvc  # noqa: E402


class FakeClient:
    url = "http://127.0.0.1:1"
    instance_id = "test"

    def __init__(self):
        self.events = []
        self.turns = []

    def request(self, method, path, body=None, retry=True):
        self.events.append((path, body))
        return 200, {"ok": True, "lease_expires": 9e18}   # 与 HubClient.request 一致：返回 (http, body)


class FakeReporter:
    def __init__(self, client):
        self.client = client
        self.lost = type("E", (), {"is_set": lambda self: False})()

    def send(self, etype, data=None):
        self.client.events.append((etype, data))

    def start_heartbeat(self):
        pass

    def finish(self):
        pass


def task(**kw):
    base = {"task_id": "T1", "attempt": 1, "lease_id": "L1", "executor": "qoder", "mode": "new",
            "session_id": "", "cwd": str(ROOT), "prompt": "说句话", "limits": {"timeout_sec": 60}}
    base.update(kw)
    return base


class QoderExecutorTest(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(qe.DEFAULTS)
        self.cfg["qoder_exe"] = "QoderMockCli.exe"

    def test_cli_registration(self):
        self.assertIn("qoder", hubcfg.DEFAULTS["executors"])
        self.assertTrue(hubsvc.STRICT_TASK.match("qoder 默认目录 检查通讯"))
        self.assertTrue(hubsvc.PROJECT_LIST.match("qoder项目列表"))
        self.assertTrue(hubsvc.COLLAB.search("你分析，Qoder执行"))

    def test_build_cmd_new_and_resume(self):
        ex = qe.QoderExecutor(self.cfg, client=FakeClient())
        cmd = ex.build_cmd(task())
        self.assertEqual(cmd[0], "QoderCli.exe".replace("QoderCli", "QoderMockCli"))
        self.assertIn("--output-format", cmd)
        self.assertIn("json", cmd)
        self.assertIn("--permission-mode", cmd)
        self.assertNotIn("--resume", cmd)
        r = ex.build_cmd(task(mode="resume", session_id="S-9"))
        self.assertIn("--resume", r)
        self.assertIn("S-9", r)

    def test_build_cmd_without_cli(self):
        self.cfg["qoder_exe"] = ""
        ex = qe.QoderExecutor(self.cfg, client=FakeClient())
        ex.exe = lambda: None            # 模拟 CLI 未安装
        self.assertIsNone(ex.build_cmd(task()))

    def test_report_exit_result(self):
        c = FakeClient()
        ex = qe.QoderExecutor(self.cfg, client=c)
        with tempfile.TemporaryDirectory() as d:
            out, err = Path(d) / "a.out", Path(d) / "a.err"
            out.write_text("noise\n" + json.dumps({"type": "result", "result": "完成", "session_id": "S1"}) + "\n",
                           encoding="utf-8")
            err.write_text("", encoding="utf-8")
            ex._report_exit(FakeReporter(c), task(), 0, str(out), str(err))
        kinds = [e[0] for e in c.events]
        self.assertEqual(kinds, ["session", "result"])
        self.assertEqual(c.events[1][1]["text"], "完成")

    def test_report_exit_error_mapping(self):
        for text, expect in ((json.dumps({"type": "result", "is_error": True, "result": "Please login"}),
                              "AUTH_REQUIRED"),
                             ("", "NO_RESULT")):
            c = FakeClient()
            ex = qe.QoderExecutor(self.cfg, client=c)
            with tempfile.TemporaryDirectory() as d:
                out, err = Path(d) / "a.out", Path(d) / "a.err"
                out.write_text(text, encoding="utf-8")
                err.write_text("", encoding="utf-8")
                ex._report_exit(FakeReporter(c), task(), 0 if text else 0, str(out), str(err))
            self.assertEqual(c.events[-1][0], "failed")
            self.assertEqual(c.events[-1][1]["code"], expect)

    def test_env_marks_task_for_hooks(self):
        ex = qe.QoderExecutor(self.cfg, client=FakeClient())
        env = ex.build_env(task())
        self.assertEqual(env["FEISHU_HUB_TASK_ID"], "T1")
        self.assertEqual(env["FEISHU_HUB_LEASE_ID"], "L1")


class QoderHookTest(unittest.TestCase):
    def test_turn_from_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / ".qoder-cn"
            (home / "projects" / "proj").mkdir(parents=True)
            sid = "sess-1"
            (home / "projects" / "proj" / (sid + ".jsonl")).write_text("\n".join([
                json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}),
                json.dumps({"type": "assistant", "message": {"role": "assistant",
                                                             "content": [{"type": "tool_use", "name": "Bash"}]}}),
                json.dumps({"type": "assistant", "message": {"role": "assistant",
                                                             "content": [{"type": "text", "text": "最终回复"}]}},
                )]) + "\n", encoding="utf-8")
            qhook.QODER_HOME = home
            turn = qhook.build_turn({"session_id": sid, "cwd": d})
        self.assertIsNotNone(turn)
        self.assertEqual(turn["executor"], "qoder")
        self.assertEqual(turn["text"], "最终回复")
        self.assertEqual(turn["items"][0]["phase"], "final")

    def test_suppressed_inside_hub_task(self):
        os.environ["FEISHU_HUB_TASK_ID"] = "T9"
        try:
            self.assertEqual(qhook.handle_payload({"session_id": "s", "cwd": "x"}, client=FakeClient()),
                             "suppressed")
        finally:
            os.environ.pop("FEISHU_HUB_TASK_ID", None)

    def test_missing_text_is_invalid(self):
        qhook.QODER_HOME = Path(tempfile.mkdtemp()) / "none"
        self.assertIsNone(qhook.build_turn({"session_id": "s", "cwd": "x"}))
        self.assertEqual(qhook.handle_payload({"session_id": "s", "cwd": "x"}, client=FakeClient()), "invalid")




class RunTaskEndToEndTest(unittest.TestCase):
    """[真机契约] 用 stub CLI 走完 run_task：started → session → result，并验证真实 CLI 的参数与结果形态。"""

    STUB = (
        "import json,sys\n"
        "prompt=sys.stdin.read()\n"
        "print(json.dumps({'type':'system','subtype':'init','session_id':'stub-sess-1'}))\n"
        "print(json.dumps({'type':'result','subtype':'success','is_error':False,"
        "'result':'已收到:'+prompt.strip(),'session_id':'stub-sess-1','total_credits':1.0}))\n"
    )

    def test_full_event_sequence(self):
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "stub_cli.py"
            stub.write_text(self.STUB, encoding="utf-8")
            cfg = dict(qe.DEFAULTS)
            cfg.update({"qoder_exe": sys.executable, "args_new": [str(stub), "-p", "--output-format", "json"],
                        "args_resume": [str(stub), "--resume", "{session_id}"]})
            c = FakeClient()
            ex = qe.QoderExecutor(cfg, client=c)
            ex.run_task(task(prompt="你好"))
            types = [(b or {}).get("type") for _p, b in c.events if isinstance(b, dict) and b.get("type")]
            self.assertEqual(types, ["started", "session", "result"])
            body = c.events[-1][1]["data"]
            self.assertEqual(body["session_id"], "stub-sess-1")
            self.assertTrue(body["text"].startswith("已收到"))
            self.assertIn("T1", c.events[0][0])          # 事件路径带任务号

    def test_real_cli_flag_shape_documented(self):
        # 真机实测（qoderclicn 1.1.66）：-p --output-format json 单行 result；permission-mode 用蛇形
        ex = qe.QoderExecutor(self.cfg(), client=FakeClient())
        cmd = ex.build_cmd(task())
        self.assertIn("-p", cmd)
        self.assertIn("--output-format", cmd)
        self.assertIn("bypass_permissions", cmd)          # camelCase 会被 CLI 拒
        self.assertNotIn("--resume", cmd)

    @staticmethod
    def cfg():
        c = dict(qe.DEFAULTS)
        c["qoder_exe"] = "qoderclicn.exe"
        return c


if __name__ == "__main__":
    unittest.main(verbosity=2)
