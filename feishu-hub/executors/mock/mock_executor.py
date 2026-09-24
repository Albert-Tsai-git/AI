# -*- coding: utf-8 -*-
"""[参考执行器] 协议 v1 的最小可运行实现：领任务 → started → session → result（回显 prompt）。
用于联调中间服务，也是 Codex 执行器的参考骨架。
用法：python executors/mock/mock_executor.py --executor codex [--desktop-queue]"""
import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from hub_client import HubClient, HubError, LeaseLost, TaskReporter  # noqa: E402


def run(task, client, desktop_queue):
    rep = TaskReporter(client, task)
    try:
        if not os.path.isdir(task["cwd"]):
            rep.send("failed", {"code": "CWD_MISSING", "message": task["cwd"]})
            return
        if desktop_queue and task["mode"] == "resume":
            # 模拟排入桌面会话：结果由桌面 Hook 通过 /v1/sessions/turns 回报
            rep.send("started", {"delivery": "desktop_queue", "queue_id": uuid.uuid4().hex})
            client.session_turn(task["session_id"], task["cwd"], "[mock 桌面] " + task["prompt"],
                                turn_id="mock-" + task["task_id"])
            return
        rep.send("started", {"delivery": "process", "pid": os.getpid()})
        sid = task["session_id"] or "mock-" + uuid.uuid4().hex[:8]
        if sid != task["session_id"]:
            rep.send("session", {"session_id": sid})
        rep.send("result", {"text": "[mock] 收到：%s" % task["prompt"], "session_id": sid})
    except LeaseLost:
        pass  # 租约丢失：立即停止，不再上报


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--executor", default="codex")
    ap.add_argument("--desktop-queue", action="store_true")
    ap.add_argument("--once", action="store_true", help="处理一条后退出")
    a = ap.parse_args()
    client = HubClient(a.executor)
    info = client.hello({"new_session": True, "resume": True, "desktop_queue": a.desktop_queue}, "mock")
    print("[mock] 已上线 %s instance=%s" % (a.executor, client.instance_id))
    while True:
        try:
            task = client.claim(int(info.get("poll_wait_sec", 25)))
        except HubError as e:
            print("[mock] 领取失败 %s" % e)
            continue
        if task:
            print("[mock] 领取 %s mode=%s" % (task["task_id"], task["mode"]))
            run(task, client, a.desktop_queue)
            if a.once:
                return


if __name__ == "__main__":
    main()
