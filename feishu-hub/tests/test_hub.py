# -*- coding: utf-8 -*-
"""[测试] 中间服务 + 协议 + Claude 执行器端到端测试。
临时 FEISHU_HUB_HOME、飞书接口打桩、假 Claude CLI；不触网、不动真实数据。
运行：python tests/test_hub.py    （在 feishu-hub 目录下）"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="hubtest_")
os.environ["FEISHU_HUB_HOME"] = os.path.join(TMP, "home")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "executors", "common"))
sys.path.insert(0, os.path.join(ROOT, "executors", "claude"))

from hub import api, config, feishu, service, store  # noqa: E402

os.makedirs(config.HOME_DIR, exist_ok=True)
with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump({"app_id": "x", "app_secret": "y", "allowed_open_ids": ["ou_me"], "notify_open_id": "ou_me",
               "lease_ttl_sec": 3, "heartbeat_sec": 1, "poll_wait_sec": 1, "task_timeout_sec": 20,
               "listen_port": 0}, f)

# ---------- 飞书打桩 ----------
SENT = []          # (动作, 目标, kind, 文本/卡片标题)
FAIL = {"on": False}
_n = [0]


def _mid():
    _n[0] += 1
    return "om_%d" % _n[0]


def _desc(kind, payload):
    if kind == "card":
        p = payload if isinstance(payload, dict) else json.loads(payload)
        return p["header"]["title"]["content"] + " | " + json.dumps(p["body"], ensure_ascii=False)
    return payload


UUIDS = []


def fake_reply(cfg, mid, kind, payload, uuid=None):
    UUIDS.append(uuid)
    if FAIL["on"]:
        raise RuntimeError("net down")
    SENT.append(("reply", mid, kind, _desc(kind, payload)))
    return _mid()


def fake_send(cfg, oid, kind, payload, uuid=None):
    UUIDS.append(uuid)
    if FAIL["on"]:
        raise RuntimeError("net down")
    SENT.append(("send", oid, kind, _desc(kind, payload)))
    return _mid()


feishu.reply, feishu.send = fake_reply, fake_send
feishu.list_chat_messages = lambda cfg, chat, start: []

cfg = config.load()
service.init(cfg)
srv = api.serve("127.0.0.1", 0, config.token())
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d" % srv.server_address[1]
stop = threading.Event()
threading.Thread(target=service.background_loop, args=(stop,), daemon=True).start()

from hub_client import HubClient, LeaseLost, TaskReporter, flush_spool  # noqa: E402

WS1 = os.path.join(TMP, "ws1"); os.makedirs(WS1)
WS2 = os.path.join(TMP, "ws2"); os.makedirs(WS2)
RES = []


def check(name, ok, detail=""):
    RES.append((name, bool(ok)))
    print("[测试] %s %s %s" % ("PASS" if ok else "FAIL", name, detail))


def msg(mid, text, parent="", chat="p2p"):
    return service.handle_message(mid, "ou_me", chat, "oc_1", "text", json.dumps({"text": text}), parent)


def task_of(mid):
    r = store._conn().execute("SELECT task_id FROM tasks WHERE source_mid=?", (mid,)).fetchone()
    return store.get_task(r[0]) if r else None


def wait(fn, sec=10):
    end = time.time() + sec
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.1)
    return fn()


def flush():
    service.flush_outbox()


def last_notice(task_id):
    flush()
    return store.get_task(task_id)["notice_mid"]


def sent_text(sub):
    flush()
    return any(sub in x[3] for x in SENT)


def card_mid_for(task_id):
    flush()
    r = store._conn().execute("SELECT message_id FROM msg_map WHERE task_id=? ORDER BY created DESC",
                              (task_id,)).fetchone()
    return r[0] if r else None


claude = HubClient("claude", url=URL)
codex = HubClient("codex", url=URL)
claude.hello({"new_session": True, "resume": True})
codex.hello({"new_session": True, "resume": True, "desktop_queue": True})

# ================= A2 缺执行者 / A1 缺目录 / 目录两步确认 =================
msg("m1", "帮我整理一下日志")
t = task_of("m1")
check("A2 执行者不明确 → 询问，不启动", t["status"] == "NEED_EXECUTOR" and sent_text("用哪个 AI 执行"))
msg("m1a", "Claude", last_notice(t["task_id"]))
t = task_of("m1")
check("A1 缺少工作目录 → 询问，不启动", t["status"] == "NEED_DIR" and sent_text("需要指定工作目录"))
msg("m1b", r"Z:\不存在的目录", last_notice(t["task_id"]))
check("目录不存在 → 拒绝", task_of("m1")["status"] == "NEED_DIR" and sent_text("目录不存在"))
msg("m1c", WS1, last_notice(t["task_id"]))
t = task_of("m1")
check("给出目录 → 回显待确认，仍不执行", t["status"] == "NEED_DIR" and t["proposed_cwd"] == WS1
      and sent_text("回复本条「确认」开始"))
msg("m1d", "确认", last_notice(t["task_id"]))
check("确认目录 → 排队", task_of("m1")["status"] == "QUEUED" and task_of("m1")["cwd"] == WS1)

# ================= A3 明确指定执行者：只派给该执行者 =================
check("A3 codex 领不到 claude 的任务", codex.claim(1) is None)
env = claude.claim(1)
check("A3 claude 领到任务 mode=new", env and env["task_id"] == t["task_id"] and env["mode"] == "new"
      and env["cwd"] == WS1 and env["grants"] == [])
rep = TaskReporter(claude, env)
rep.send("started", {"delivery": "process", "pid": 1})
check("started → 飞书「执行中」", sent_text("Claude 执行中"))
r1 = rep.send("session", {"session_id": "S-1"})
# 幂等：同 seq 重发返回首次结果
dup = claude.request("POST", "/v1/tasks/%s/events" % env["task_id"],
                     {"lease_id": env["lease_id"], "seq": 2, "type": "session", "data": {"session_id": "S-x"}})[1]
check("事件幂等：同 seq 重发不生效", dup == r1 and store.get_task(env["task_id"])["session_id"] == "S-1")
rep.send("result", {"text": "# 完成\n整理好了", "session_id": "S-1"})
check("result → 结果落库并发卡片 → DONE", wait(lambda: (flush(), store.get_task(env["task_id"])["status"] == "DONE")[1]))
card = card_mid_for(env["task_id"])
check("卡片映射到 claude/S-1/WS1", store.find_mapping(card)["session_id"] == "S-1")
try:
    rep.send("heartbeat")
    check("终态后事件被拒绝", False)
except LeaseLost:
    check("终态后事件被拒绝（409）", True)

# ================= A6 回复卡片 → 续接同一会话与目录 =================
msg("m2", "再补充一下统计", card)
t2 = task_of("m2")
check("A6 回复卡片 → 同执行者、同会话、同目录", t2["executor"] == "claude" and t2["session_id"] == "S-1"
      and t2["cwd"] == WS1 and t2["mode"] == "resume" and t2["status"] == "QUEUED")
# ================= A7 重复投递 =================
before = store._conn().execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
msg("m2", "再补充一下统计", card)
check("A7 重复投递同一事件不重复建任务", store._conn().execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before)

# ================= A9 执行中重启（租约过期）→ 需要人工，不自动重派 =================
env2 = claude.claim(1)
check("续跑任务带 session_id", env2["session_id"] == "S-1" and env2["mode"] == "resume")
time.sleep(3.5)
service.reap()
t2 = store.get_task(env2["task_id"])
check("A9 租约过期 → NEEDS_RECOVERY", t2["status"] == "NEEDS_RECOVERY" and sent_text("任务需要你决定"))
check("A9 不会自动重派", claude.claim(1) is None)
try:
    TaskReporter(claude, env2).send("heartbeat")
    check("过期租约上报 → LEASE_LOST", False)
except LeaseLost:
    check("过期租约上报 → LEASE_LOST", True)
msg("m2r", "续跑", last_notice(env2["task_id"]))
env2b = claude.claim(1)
check("A9 用户「续跑」→ 重新派发并带提示", env2b and env2b["task_id"] == env2["task_id"] and env2b["attempt"] == 2
      and "中断" in (env2b["resume_hint"] or ""))
TaskReporter(claude, env2b).send("result", {"text": "补充完成"})
check("续跑结果送达", wait(lambda: (flush(), store.get_task(env2["task_id"])["status"] == "DONE")[1]))

# ================= A8 飞书发送失败只重发，不重跑 =================
msg("m3", "Claude执行：写个总结 @%s" % WS1)
env3 = claude.claim(1)
FAIL["on"] = True
TaskReporter(claude, env3).send("result", {"text": "总结如下", "session_id": "S-3"})
flush()
check("A8 发送失败 → 结果已存、保持 RESULT_SAVED", store.get_task(env3["task_id"])["status"] == "RESULT_SAVED")
FAIL["on"] = False
store._conn().execute("UPDATE outbox SET next_try=0")
check("A8 恢复后补发 → DONE，且任务未被再次派发",
      wait(lambda: (flush(), store.get_task(env3["task_id"])["status"] == "DONE")[1]) and claude.claim(1) is None)

# ================= 危险指令确认 =================
msg("m4", "Claude执行：删除 build 目录 @%s" % WS1)
t4 = task_of("m4")
check("危险指令 → NEED_CONFIRM", t4["status"] == "NEED_CONFIRM")
msg("m4a", "算了", last_notice(t4["task_id"]))
check("非确认 → 取消", task_of("m4")["status"] == "CANCELLED")
msg("m5", "Claude执行：删除 dist @%s" % WS1)
msg("m5a", "确认", last_notice(task_of("m5")["task_id"]))
check("确认 → 排队", task_of("m5")["status"] == "QUEUED")
e5 = claude.claim(1)
TaskReporter(claude, e5).send("failed", {"code": "EXEC_ERROR", "message": "boom"})
check("failed → FAILED 并通知", store.get_task(e5["task_id"])["status"] == "FAILED" and sent_text("执行失败"))

# ================= A10 并发：不同目录并行、同目录串行 =================
msg("m6", "Claude执行：任务甲 @%s" % WS1)
msg("m7", "Claude执行：任务乙 @%s" % WS1)
msg("m8", "Claude执行：任务丙 @%s" % WS2)
a, b = claude.claim(1), claude.claim(1)
c = claude.claim(1)
check("A10 同目录串行、不同目录并行", {a["cwd"], b["cwd"]} == {WS1, WS2} and c is None)
for e in (a, b):
    TaskReporter(claude, e).send("result", {"text": "ok-" + e["task_id"], "session_id": "S-" + e["task_id"]})
d = claude.claim(1)
check("A10 前一个完成后同目录下一个才派发", d and d["cwd"] == WS1)
TaskReporter(claude, d).send("result", {"text": "ok", "session_id": "S-d"})
flush()
check("A10 各任务结果卡片互不串线",
      all(store.find_mapping(card_mid_for(e["task_id"]))["session_id"] == "S-" + e["task_id"] for e in (a, b)))

# ================= CWD_MISSING → 重新确认目录 =================
msg("m9", "Claude执行：跑一下 @%s" % WS2)
e9 = claude.claim(1)
TaskReporter(claude, e9).send("failed", {"code": "CWD_MISSING", "message": WS2})
check("执行器报 CWD_MISSING → 转 NEED_DIR 询问", store.get_task(e9["task_id"])["status"] == "NEED_DIR")

# ================= Codex 桌面队列（desktop_queue）=================
cmid = card_mid_for(d["task_id"])
store.save_mapping("card_codex", "codex", "TH-1", WS2)
msg("m10", "继续优化", "card_codex")
e10 = codex.claim(1)
check("回复 Codex 卡片 → 派给 codex 且 mode=resume", e10 and e10["session_id"] == "TH-1" and e10["mode"] == "resume")
TaskReporter(codex, e10).send("started", {"delivery": "desktop_queue", "queue_id": "Q1"})
check("desktop_queue → WAITING_EXTERNAL", store.get_task(e10["task_id"])["status"] == "WAITING_EXTERNAL")
codex.session_turn("TH-1", WS2, "桌面执行完毕", turn_id="turn-1")
check("桌面 Hook 回报 → 匹配等待任务并送达",
      wait(lambda: (flush(), store.get_task(e10["task_id"])["status"] == "DONE")[1]))
r = codex.session_turn("TH-1", WS2, "桌面执行完毕", turn_id="turn-1")
check("桌面轮次幂等", r.get("duplicate") is True)
n_before = len(SENT)
codex.session_turn("TH-2", WS2, "我在桌面上直接做完了", turn_id="turn-9")
flush()
check("独立桌面轮次 → 发卡片并可回复续跑",
      len(SENT) > n_before and store._conn().execute("SELECT 1 FROM msg_map WHERE session_id='TH-2'").fetchone())

# ================= SESSION_BUSY 释放与上限 =================
msg("m11", "继续", "card_codex")
e11 = codex.claim(1)
codex.release(e11, "SESSION_BUSY", 5)
t11 = store.get_task(e11["task_id"])
check("SESSION_BUSY → 延迟重排且不计次数", t11["status"] == "QUEUED" and t11["not_before"] > time.time())
store.update(e11["task_id"], not_before=0)
codex.release(codex.claim(1), "SESSION_BUSY", 5)
store.update(e11["task_id"], not_before=0)
codex.release(codex.claim(1), "SESSION_BUSY", 5)
check("连续 3 次 SESSION_BUSY → 交给用户决定", store.get_task(e11["task_id"])["status"] == "NEEDS_RECOVERY")

# ================= 显式切换执行者 =================
msg("m12", "Codex执行：审查这次改动", card_mid_for(d["task_id"]))
t12 = task_of("m12")
check("回复 Claude 卡片但指定 Codex → 同目录新 Codex 会话", t12["executor"] == "codex" and t12["cwd"] == WS1
      and t12["mode"] == "new")

# ================= 协作指令只记录 =================
msg("m13", "你分析，Claude执行：重构模块")
check("协作指令 v1 只记录不执行", task_of("m13")["status"] == "CANCELLED" and sent_text("已记录协作指令"))

# ================= 鉴权 / 协议版本 =================
bad = HubClient("claude", url=URL, token="wrong")
try:
    bad.hello({})
    check("错误令牌 → 401", False)
except Exception as e:  # noqa: BLE001
    check("错误令牌 → 401", getattr(e, "http", 0) == 401)

# ================= Claude 执行器端到端（假 CLI）=================
FAKE_PY = os.path.join(TMP, "fake_claude.py")
with open(FAKE_PY, "w", encoding="utf-8") as f:
    f.write(r'''
import json, os, sys, time
args = sys.argv[1:]
prompt = sys.stdin.read()
with open(os.path.join(os.getcwd(), "calls.log"), "a", encoding="utf-8") as g:
    g.write(json.dumps({"args": args, "prompt": prompt, "task": os.environ.get("FEISHU_HUB_TASK_ID")}) + "\n")
if "SLEEP" in prompt:
    time.sleep(30)
if "--resume" in args and args[args.index("--resume") + 1] == "GONE":
    sys.stderr.write("No conversation found with session ID: GONE"); sys.exit(1)
sid = args[args.index("--resume") + 1] if "--resume" in args else "NEW-SID"
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "回复:" + prompt.strip()[-20:], "session_id": sid}))
''')
FAKE_CMD = os.path.join(TMP, "fake_claude.cmd")
with open(FAKE_CMD, "w") as f:
    f.write('@"%s" "%s" %%*\n' % (sys.executable, FAKE_PY))
import executor as cex  # noqa: E402
ex = cex.ClaudeExecutor(dict(cex.DEFAULTS, claude_exe=FAKE_CMD), HubClient("claude", url=URL))
estop = threading.Event()
threading.Thread(target=ex.serve_forever, args=(estop,), daemon=True).start()
WS3 = os.path.join(TMP, "ws3"); os.makedirs(WS3)


def calls():
    p = os.path.join(WS3, "calls.log")
    return [json.loads(x) for x in open(p, encoding="utf-8")] if os.path.exists(p) else []


msg("m20", "Claude执行：新建会话测试 @%s" % WS3)
t20 = task_of("m20")
check("执行器：新任务执行完成", wait(lambda: (flush(), store.get_task(t20["task_id"])["status"] == "DONE")[1], 20))
check("执行器：新会话不带 --resume，prompt 走 stdin", calls()[-1]["args"][0] == "-p" and "新建会话测试" in calls()[-1]["prompt"])
check("执行器：上报新会话 ID", store.get_task(t20["task_id"])["session_id"] == "NEW-SID")
msg("m21", "接着做", card_mid_for(t20["task_id"]))
t21 = task_of("m21")
check("执行器：回复卡片 → --resume 原会话", wait(lambda: (flush(), store.get_task(t21["task_id"])["status"] == "DONE")[1], 20)
      and calls()[-1]["args"][:2] == ["--resume", "NEW-SID"])
check("执行器：子进程带任务号（Hook 不重复上报）", calls()[-1]["task"] == t21["task_id"])
store.save_mapping("card_gone", "claude", "GONE", WS3)
msg("m22", "继续", "card_gone")
t22 = task_of("m22")
check("执行器：会话不存在 → SESSION_NOT_FOUND",
      wait(lambda: "SESSION_NOT_FOUND" in (store.get_task(t22["task_id"])["error"] or ""), 20))
store.save_mapping("card_ws_gone", "claude", "S-9", os.path.join(TMP, "gone"))
msg("m23", "继续", "card_ws_gone")
check("执行器：目录消失 → 中间服务询问目录", task_of("m23")["status"] == "NEED_DIR")
# 执行中执行器被停止 → 租约过期 → 等用户决定
msg("m24", "Claude执行：SLEEP 很久 @%s" % WS3)
t24 = task_of("m24")
wait(lambda: store.get_task(t24["task_id"])["status"] == "LEASED", 10)
time.sleep(1.5)
check("执行器：执行中持续心跳，租约不过期", store.get_task(t24["task_id"])["status"] == "LEASED")
estop.set()
store.update(t24["task_id"], lease_expires=time.time() - 1)
service.reap()
check("执行器失联 → NEEDS_RECOVERY，不重跑", store.get_task(t24["task_id"])["status"] == "NEEDS_RECOVERY")

# ================= Hook =================
import hook_stop  # noqa: E402
import hook_prompt  # noqa: E402
os.environ["FEISHU_HUB_URL"] = URL
hook_stop.HubClient = lambda ex, timeout=10: HubClient(ex, url=URL, timeout=timeout)
hook_prompt.HubClient = lambda ex, timeout=5: HubClient(ex, url=URL, timeout=timeout)
tr = os.path.join(TMP, "tr.jsonl")
with open(tr, "w", encoding="utf-8") as f:
    f.write(json.dumps({"type": "assistant", "uuid": "u-1", "message": {"content": [{"type": "text", "text": "桌面完成"}]}}) + "\n")


def run_hook(mod, payload, env=None):
    import io
    old_env = dict(os.environ)
    os.environ.update(env or {})
    sys.stdin = io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")))
    buf = io.BytesIO()
    old_out = sys.stdout
    wrapper = io.TextIOWrapper(buf, encoding="ascii")
    sys.stdout = wrapper
    try:
        mod.main()
        wrapper.flush()
    finally:
        wrapper.detach()  # 解除包装，避免回收时关闭 buf
        sys.stdout = old_out
        os.environ.clear()
        os.environ.update(old_env)
    return buf.getvalue().decode("ascii")


n_before = len(SENT)
run_hook(hook_stop, {"session_id": "D-1", "transcript_path": tr, "cwd": WS1})
flush()
check("Stop Hook：桌面独立轮次 → 中间服务发卡片", len(SENT) > n_before)
n_before = len(SENT)
run_hook(hook_stop, {"session_id": "D-1", "transcript_path": tr, "cwd": WS1}, {"FEISHU_HUB_TASK_ID": "T1"})
flush()
check("Stop Hook：执行器子进程内不上报", len(SENT) == n_before)
store.inbox_add("claude", "D-1", "飞书问题", "飞书回复")
out = run_hook(hook_prompt, {"session_id": "D-1"})
check("同步 Hook：回填飞书往返并确认", "additionalContext" in out and not store.inbox_list("claude", "D-1"))
# Hook 离线落盘 → 执行器补发
hook_stop.HubClient = lambda ex, timeout=10: HubClient(ex, url="http://127.0.0.1:1", timeout=1)
with open(tr, "w", encoding="utf-8") as f:
    f.write(json.dumps({"type": "assistant", "uuid": "u-2", "message": {"content": [{"type": "text", "text": "离线完成"}]}}) + "\n")
run_hook(hook_stop, {"session_id": "D-2", "transcript_path": tr, "cwd": WS1})
spooled = os.listdir(os.path.join(config.HOME_DIR, "spool"))
n = flush_spool({"claude": HubClient("claude", url=URL)})
check("Hook 离线落盘 → 执行器补发", len(spooled) == 1 and n == 1
      and store._conn().execute("SELECT 1 FROM turns WHERE session_id='D-2'").fetchone())

# ================= 复核返工补测 =================
check("出口：每次发送都带飞书幂等键", UUIDS and all(u and u.startswith("hub-") for u in UUIDS))
# 结果已落库但卡片未入队（崩溃窗口）→ 回收时补建
msg("m30", "Claude执行：崩溃窗口 @%s" % WS1)
e30 = claude.claim(1)
store.cas(e30["task_id"], "LEASED", "RESULT_SAVED", result_text="已存的结果", session_id="S-30")
service.reap()
check("回收：RESULT_SAVED 无发送记录 → 按已存结果补建并送达",
      wait(lambda: (flush(), store.get_task(e30["task_id"])["status"] == "DONE")[1]) and sent_text("已存的结果"))
# 终态事件响应丢失后重试（新 seq）→ ALREADY_FINAL 视为成功
msg("m31", "Claude执行：重试结果 @%s" % WS1)
e31 = claude.claim(1)
r31 = TaskReporter(claude, e31)
r31.send("result", {"text": "一次", "session_id": "S-31"})
r31b = TaskReporter(claude, e31)
r31b.seq = 5
check("终态重试 → ALREADY_FINAL 视为成功，不重复发卡片",
      r31b.send("result", {"text": "一次", "session_id": "S-31"}).get("already_final") is True)
flush()
check("结果卡片只发一张", store._conn().execute("SELECT COUNT(*) FROM outbox WHERE task_id=?",
                                            (e31["task_id"],)).fetchone()[0] == 1)
# 桌面队列后旧租约失效
msg("m32", "继续", "card_codex")
e32 = codex.claim(1)
r32 = TaskReporter(codex, e32)
r32.send("started", {"delivery": "desktop_queue", "queue_id": "Q2"})
try:
    r32.send("heartbeat")
    check("排入桌面队列后旧租约事件 → LEASE_LOST", False)
except LeaseLost:
    check("排入桌面队列后旧租约事件 → LEASE_LOST", True)
codex.session_turn("TH-1", WS2, "队列完成", turn_id="turn-q2")
flush()
# 提示只允许发起人回复
cfg_ids = service.CFG["allowed_open_ids"]
service.CFG["allowed_open_ids"] = ["ou_me", "ou_other"]
msg("m33", "帮我看看")
n33 = last_notice(task_of("m33")["task_id"])
service.handle_message("m33x", "ou_other", "p2p", "oc_1", "text", json.dumps({"text": "Claude"}), n33)
check("其他白名单用户不能代答提示", task_of("m33")["status"] == "NEED_EXECUTOR" and sent_text("只有发起人可以处理"))
service.CFG["allowed_open_ids"] = cfg_ids
# 重启：有效租约给宽限期，不立即判失联
msg("m34", "Claude执行：长任务 @%s" % WS2)
e34 = claude.claim(1)
store.update(e34["task_id"], lease_expires=time.time() - 1)
service.recover()
check("重启：过期租约先给宽限期，执行器可恢复心跳",
      store.get_task(e34["task_id"])["status"] == "LEASED" and TaskReporter(claude, e34).send("heartbeat")["ok"])
# 卡在 SENDING 的发送记录自动复位
oid = store.enqueue("text", "卡住的消息")
store._conn().execute("UPDATE outbox SET status='SENDING', next_try=? WHERE id=?", (time.time() - 400, oid))
service.reap()
flush()
check("发送中卡住超过 5 分钟 → 复位并发出", store._conn().execute("SELECT status FROM outbox WHERE id=?",
                                                         (oid,)).fetchone()[0] == "SENT")
# 未知执行器
try:
    HubClient("gpt", url=URL).hello({})
    check("未知执行器 → 400", False)
except Exception as e:  # noqa: BLE001
    check("未知执行器 → 400", getattr(e, "http", 0) == 400)

# ================= 重启恢复 =================
store._conn().execute("UPDATE outbox SET status='SENDING' WHERE id=(SELECT MAX(id) FROM outbox)")
st = service.recover()
check("重启：发送中的消息复位补发", st["resent"] >= 1)

stop.set()
fails = [n for n, ok in RES if not ok]
print("[测试] 共 %d 项，失败 %d 项 %s" % (len(RES), len(fails), fails))
sys.stdout.flush()
os._exit(1 if fails else 0)
