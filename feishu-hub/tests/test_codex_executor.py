# -*- coding: utf-8 -*-
"""[测试] Codex 执行器 CX-1～CX-10：临时 Hub、飞书打桩与假 Codex CLI。"""
import ctypes
from ctypes import wintypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="codexhubtest_")
HUB_HOME = os.path.join(TMP, "home")
os.environ["FEISHU_HUB_HOME"] = HUB_HOME
# 即使 Hook 意外漏传测试客户端，也不会碰到默认的真实 Hub 端口。
os.environ["FEISHU_HUB_URL"] = "http://127.0.0.1:1"
os.environ["FAKE_CODEX_CALL_LOG"] = os.path.join(TMP, "fake-codex-calls.jsonl")
os.environ["FAKE_QUEUE_ARGV_LOG"] = os.path.join(TMP, "fake-queue-argv.json")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "executors", "common"))
sys.path.insert(0, os.path.join(ROOT, "executors", "codex"))

from hub import api, config, feishu, service, store  # noqa: E402

from hub_client import HubClient, HubError, SPOOL_DIR  # noqa: E402
import executor as codex_executor  # noqa: E402
import hook_stop  # noqa: E402


CHECKS = []
SENT = []
_MID = [0]
_SENT_LOCK = threading.Lock()
_SERVER = None
_SERVER_THREAD = None
_BACKGROUND_STOP = None
_BACKGROUND_THREAD = None
_EXECUTOR = None
_EXECUTOR_STOP = None
_EXECUTOR_THREAD = None
_RUNNER = None


def _new_mid():
    with _SENT_LOCK:
        _MID[0] += 1
        return "cx_mid_%d" % _MID[0]


def _card_text(kind, payload):
    if kind != "card":
        return str(payload)
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return payload
    header = payload.get("header", {}).get("title", {}).get("content", "")
    return str(header)


def fake_reply(cfg, mid, kind, payload, uuid=None):
    new_mid = _new_mid()
    with _SENT_LOCK:
        SENT.append(("reply", mid, kind, _card_text(kind, payload), new_mid, uuid))
    return new_mid


def fake_send(cfg, open_id, kind, payload, uuid=None):
    new_mid = _new_mid()
    with _SENT_LOCK:
        SENT.append(("send", open_id, kind, _card_text(kind, payload), new_mid, uuid))
    return new_mid


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok)))
    print("[测试] %s %s%s" % ("PASS" if ok else "FAIL", name,
                              (" — " + str(detail)) if detail else ""), flush=True)


def wait_for(predicate, timeout=12, interval=0.05):
    end = time.time() + timeout
    while time.time() < end:
        service.flush_outbox()
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    service.flush_outbox()
    return predicate()


def send_message(mid, text, parent=""):
    return service.handle_message(mid, "ou_test", "p2p", "oc_test", "text",
                                  json.dumps({"text": text}, ensure_ascii=False), parent)


def task_for_source(mid):
    row = store._conn().execute("SELECT task_id FROM tasks WHERE source_mid=?", (mid,)).fetchone()
    return store.get_task(row[0]) if row else None


def card_for_task(task_id):
    row = store._conn().execute(
        "SELECT message_id FROM msg_map WHERE task_id=? ORDER BY created DESC LIMIT 1", (task_id,)
    ).fetchone()
    return row[0] if row else None


def flush_and_task(task_id):
    service.flush_outbox()
    return store.get_task(task_id)


def wait_for_recovery(task_id, timeout=8):
    def inspect():
        service.reap()
        task = flush_and_task(task_id)
        return task if task and task["status"] == "NEEDS_RECOVERY" else None
    return wait_for(inspect, timeout)


def task_events(task_id):
    return [row[0] for row in store._conn().execute(
        "SELECT type FROM events WHERE task_id=? ORDER BY seq", (task_id,)).fetchall()]


def read_calls():
    path = os.environ["FAKE_CODEX_CALL_LOG"]
    if not os.path.exists(path):
        return []
    calls = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                calls.append(json.loads(line))
            except ValueError:
                continue
    return calls


def read_queue_argv():
    try:
        with open(os.environ["FAKE_QUEUE_ARGV_LOG"], "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_text_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _write_fake_cli():
    """[假 CLI] 记录参数与 stdin，模拟 exec、active-writer、queue 和长任务。"""
    fake_py = os.path.join(TMP, "fake_codex.py")
    fake_cmd = os.path.join(TMP, "fake_codex.cmd")
    source = r'''# -*- coding: utf-8 -*-
import json
import os
import subprocess
import sys
import time
import uuid

if len(sys.argv) > 1 and sys.argv[1] == "--cx-child":
    time.sleep(180)
    raise SystemExit(0)

args = sys.argv[1:]
command = args[0] if args else ""
prompt = sys.stdin.buffer.read().decode("utf-8") if command == "exec" else ""
if command == "queue" and "--message" in args:
    prompt = args[args.index("--message") + 1]
cwd = os.getcwd()
task_id = os.environ.get("FEISHU_HUB_TASK_ID", "")
entry = {"command": command, "args": args, "prompt": prompt, "cwd": cwd,
         "task_id": task_id, "pid": os.getpid()}

def record(extra=None):
    if extra:
        entry.update(extra)
    with open(os.environ["FAKE_CODEX_CALL_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

record()

if command == "queue":
    print("Queued message ID: Q-CX3-0001", flush=True)
    raise SystemExit(0)

if command != "exec":
    sys.stderr.write("unsupported command\n")
    raise SystemExit(2)

resume = "resume" in args
session_id = args[-2] if resume and len(args) >= 2 else "THREAD-" + uuid.uuid4().hex[:12]
entry["session_id"] = session_id

if "CX3_ACTIVE_WRITER_DELAY" in prompt:
    # 延迟超过旧的 2 秒启发式，验证只凭错误证据回退到 queue。
    time.sleep(2.4)
    sys.stderr.write("Error: thread already has an active writer\n")
    sys.stderr.flush()
    raise SystemExit(1)

if resume and session_id == "GONE":
    sys.stderr.write("No conversation found with session ID: GONE\n")
    raise SystemExit(1)

def emit(event):
    print(json.dumps(event), flush=True)

emit({"type": "thread.started", "thread_id": session_id})
emit({"type": "turn.started"})

child_pid = None
if "CX7_LEASE_LOST_TREE" in prompt:
    child = subprocess.Popen([sys.executable, __file__, "--cx-child"],
                             cwd=cwd, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    child_pid = child.pid
    with open(os.path.join(cwd, "cx7_child.pid"), "w", encoding="ascii") as f:
        f.write(str(child_pid))
    record({"child_pid": child_pid})

if "CX5_HEARTBEAT" in prompt:
    time.sleep(5)
elif (("CX6_EXECUTOR_KILL" in prompt and "中断" not in prompt)
      or "CX7_LEASE_LOST_TREE" in prompt):
    time.sleep(60)

if "CX_NO_RESULT" not in prompt:
    output_arg = args.index("--output-last-message") + 1
    output_path = args[output_arg]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("FAKE RESULT: " + prompt.strip())
raise SystemExit(0)
'''
    with open(fake_py, "w", encoding="utf-8") as f:
        f.write(source)
    with open(fake_cmd, "w", encoding="utf-8") as f:
        f.write('@"%s" "%s" %%*\r\n' % (sys.executable, fake_py))
    return fake_cmd


def _write_vendor_queue_exe(fake_cmd):
    """[假原生 CLI] 让 queue 经 Windows CreateProcess 启动 Python 副本，回收真实 argv。"""
    vendor_dir = os.path.join(
        os.path.dirname(os.path.abspath(fake_cmd)), "node_modules", "@openai", "codex",
        "node_modules", "@openai", "codex-win32-x64", "vendor",
        "x86_64-pc-windows-msvc", "bin")
    os.makedirs(vendor_dir, exist_ok=True)
    fake_exe = os.path.join(vendor_dir, "codex.exe")
    shutil.copy2(sys.executable, fake_exe)
    if os.name == "nt":
        dll_name = "python%d%d.dll" % sys.version_info[:2]
        dll_source = os.path.join(sys.base_prefix, dll_name)
        if os.path.isfile(dll_source):
            shutil.copy2(dll_source, os.path.join(vendor_dir, dll_name))
    source = r'''# -*- coding: utf-8 -*-
import json
import os
import sys

if sys.argv and sys.argv[0] == "queue":
    with open(os.environ["FAKE_QUEUE_ARGV_LOG"], "w", encoding="utf-8") as f:
        json.dump(sys.argv, f, ensure_ascii=False)
    sys.stdout.write("Queued message ID: Q-CX3-ARGV-0001\n")
    sys.stdout.flush()
    os._exit(0)
'''
    with open(os.path.join(TMP, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(source)
    os.environ["FAKE_CODEX_EXE"] = fake_exe
    os.environ["PYTHONHOME"] = sys.base_prefix
    os.environ["PYTHONPATH"] = TMP
    return fake_exe


def _start_hub():
    global _SERVER, _SERVER_THREAD, _BACKGROUND_STOP, _BACKGROUND_THREAD
    global _EXECUTOR, _EXECUTOR_STOP, _EXECUTOR_THREAD

    os.makedirs(HUB_HOME, exist_ok=True)
    config_data = {
        "app_id": "test", "app_secret": "test", "allowed_open_ids": ["ou_test"],
        "notify_open_id": "ou_test", "lease_ttl_sec": 3, "heartbeat_sec": 1,
        "poll_wait_sec": 1, "task_timeout_sec": 25, "daily_task_limit": 100,
        "session_busy_max_retries": 3, "suggest_cwd": TMP,
        "project_roots": [TMP], "projects": {},
    }
    with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False)
    cfg = config.load()
    service.init(cfg)
    feishu.reply, feishu.send = fake_reply, fake_send
    feishu.list_chat_messages = lambda cfg, chat, start: []

    _SERVER = api.serve("127.0.0.1", 0, config.token())
    _SERVER_THREAD = threading.Thread(target=_SERVER.serve_forever, daemon=True)
    _SERVER_THREAD.start()
    url = "http://127.0.0.1:%d" % _SERVER.server_address[1]
    os.environ["FEISHU_HUB_URL"] = url
    _BACKGROUND_STOP = threading.Event()
    _BACKGROUND_THREAD = threading.Thread(target=service.background_loop,
                                          args=(_BACKGROUND_STOP,), daemon=True)
    _BACKGROUND_THREAD.start()

    fake_cmd = _write_fake_cli()
    _write_vendor_queue_exe(fake_cmd)
    executor_cfg = dict(codex_executor.DEFAULTS)
    executor_cfg.update(codex_exe=fake_cmd, max_parallel=1)
    client = HubClient("codex", url=url, token=config.token())
    _EXECUTOR = codex_executor.CodexExecutor(executor_cfg, client)
    _EXECUTOR_STOP = threading.Event()
    _EXECUTOR_THREAD = threading.Thread(target=_EXECUTOR.serve_forever,
                                        args=(_EXECUTOR_STOP,), daemon=True)
    _EXECUTOR_THREAD.start()
    assert wait_for(lambda: store.executor_caps("codex", client.instance_id), 5)
    return url, fake_cmd


def _stop_executor_loop():
    global _EXECUTOR_STOP, _EXECUTOR_THREAD
    if _EXECUTOR_STOP:
        _EXECUTOR_STOP.set()
    if _EXECUTOR_THREAD:
        _EXECUTOR_THREAD.join(timeout=5)


def _write_runner_config(fake_cmd):
    path = os.path.join(HUB_HOME, "executor_codex.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"codex_exe": fake_cmd,
                   "codex_args": list(codex_executor.DEFAULTS["codex_args"]),
                   "max_parallel": 1, "spool_flush_sec": 60}, f)
    runner_path = os.path.join(TMP, "codex_runner.py")
    with open(runner_path, "w", encoding="utf-8") as f:
        f.write("import os, sys\n"
                "sys.path.insert(0, %r)\n" % os.path.join(ROOT, "executors", "codex") +
                "from executor import main\n"
                "main()\n")
    return runner_path


def _pid_running(pid):
    if not pid:
        return False
    if os.name == "nt":
        try:
            k32 = ctypes.windll.kernel32
            k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            k32.GetExitCodeProcess.restype = wintypes.BOOL
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            k32.CloseHandle.restype = wintypes.BOOL
            handle = k32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return False
            try:
                code = wintypes.DWORD()
                return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
            finally:
                k32.CloseHandle(handle)
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def _kill_pid_tree(pid):
    if not _pid_running(pid):
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        os.kill(int(pid), 9)


def run_tests():
    global _RUNNER
    url, fake_cmd = _start_hub()
    workspace = os.path.join(TMP, "workspace")
    os.makedirs(workspace, exist_ok=True)
    client = _EXECUTOR.client

    # CX-1：新会话收到可恢复 thread-id 与结果，并生成可回复的卡片。
    send_message("cx1-new", "codex %s CX1_NEW_PROMPT" % workspace)
    cx1 = task_for_source("cx1-new")
    cx1_done = wait_for(lambda: flush_and_task(cx1["task_id"])
                        if cx1 and flush_and_task(cx1["task_id"])["status"] == "DONE" else None, 15)
    calls = read_calls()
    first_exec = next((c for c in calls if c["command"] == "exec" and "CX1_NEW_PROMPT" in c["prompt"]), {})
    event_order = task_events(cx1["task_id"]) if cx1 else []
    event_types = [x for x in event_order if x in ("started", "session", "result")]
    order_ok = all(x in event_types for x in ("started", "session", "result"))
    if order_ok:
        order_ok = event_types.index("started") < event_types.index("session") < event_types.index("result")
    result_card = card_for_task(cx1["task_id"]) if cx1 else None
    check("CX-1 新会话上报 session/result 并生成可回复卡片",
          bool(cx1_done and cx1_done["session_id"].startswith("THREAD-") and result_card
               and order_ok
               and first_exec.get("prompt") == "CX1_NEW_PROMPT"
               and first_exec.get("args", [])[-1:] == ["-"]
               and "--dangerously-bypass-approvals-and-sandbox" in first_exec.get("args", [])
               and "--skip-git-repo-check" in first_exec.get("args", [])
               and first_exec.get("task_id") == cx1["task_id"]),
          "task=%s session=%s" % (cx1["task_id"], cx1_done["session_id"] if cx1_done else ""))

    # CX-2：桌面会话空闲时，用原 session-id exec resume 并返回结果。
    send_message("cx2-resume", "CX2_RESUME_IDLE", result_card or "")
    cx2 = task_for_source("cx2-resume")
    cx2_done = wait_for(lambda: flush_and_task(cx2["task_id"])
                        if cx2 and flush_and_task(cx2["task_id"])["status"] == "DONE" else None, 15)
    calls = read_calls()
    resume_call = next((c for c in calls if c["command"] == "exec" and "CX2_RESUME_IDLE" in c["prompt"]), {})
    check("CX-2 空闲会话 exec resume 原 session-id 并送达结果",
          bool(cx1_done and cx2 and cx2_done and cx2["mode"] == "resume"
               and cx2_done["session_id"] == cx1_done["session_id"]
               and resume_call.get("prompt") == "CX2_RESUME_IDLE"
               and "resume" in resume_call.get("args", [])
               and resume_call.get("args", [])[-2:] == [cx1_done["session_id"], "-"]),
          "mode=%s session=%s" % (cx2["mode"] if cx2 else "", cx2_done["session_id"] if cx2_done else ""))

    # CX-3：慢速 active-writer 拒绝只投递一次，桌面 Hook 回报后匹配 WAITING_EXTERNAL。
    busy_sid = "THREAD-CX3-BUSY"
    cx3_prompt = 'CX3_ACTIVE_WRITER_DELAY 元字符：& | 100% ^ " < >\n第二行：逐字往返'
    store.save_mapping("cx3-card", "codex", busy_sid, workspace)
    send_message("cx3-queue", "codex %s %s" % (workspace, cx3_prompt), "cx3-card")
    cx3 = task_for_source("cx3-queue")
    waiting = wait_for(lambda: (t if (t := store.get_task(cx3["task_id"]))["status"] == "WAITING_EXTERNAL" else None)
                       if cx3 else None, 15)
    calls = read_calls()
    cx3_exec = [c for c in calls if c["command"] == "exec" and "CX3_ACTIVE_WRITER_DELAY" in c["prompt"]]
    queue_argv = wait_for(read_queue_argv, 5)
    queue_message = (queue_argv[queue_argv.index("--message") + 1]
                     if queue_argv and "--message" in queue_argv else None)
    queue_events = [json.loads(r[0]) for r in store._conn().execute(
        "SELECT data FROM events WHERE task_id=? AND type='started' ORDER BY seq", (cx3["task_id"],)).fetchall()] if cx3 else []
    hook_payload = {"session_id": busy_sid, "cwd": workspace, "turn_id": "cx3-desktop-turn",
                    "last_assistant_message": "CX3 桌面端完成"}
    hook_result = hook_stop.handle_payload(hook_payload, client)
    cx3_done = wait_for(lambda: flush_and_task(cx3["task_id"])
                        if cx3 and flush_and_task(cx3["task_id"])["status"] == "DONE" else None, 10)
    check("CX-3 active-writer 队列只投递一次，Hook 将等待任务完成",
          bool(waiting and waiting["queue_id"] == "Q-CX3-ARGV-0001" and len(cx3_exec) == 1
               and queue_argv and queue_argv[0] == "queue" and queue_message == cx3["prompt"]
               and queue_argv[queue_argv.index("--thread") + 1] == busy_sid
               and "--skip-git-repo-check" not in queue_argv
               and "--dangerously-bypass-approvals-and-sandbox" in queue_argv
               and os.path.samefile(codex_executor.queue_codex_exe(fake_cmd),
                                    os.environ["FAKE_CODEX_EXE"])
               and cx3_exec[0].get("prompt") == cx3["prompt"]
               and hook_result == "sent" and cx3_done and cx3_done["result_text"] == "CX3 桌面端完成"
               and queue_events and queue_events[-1].get("delivery") == "desktop_queue"),
          "exec=%d expected=%r actual=%r argv=%r status=%s" % (len(cx3_exec), cx3["prompt"], queue_message,
                                                                 queue_argv,
                                                                 cx3_done["status"] if cx3_done else "missing"))

    # Q1：绕过飞书文本规范化，直接验证 Windows 原生进程收到的 --message 完全不变。
    q1_prompt = '特殊字符 & | 100% ^ " < >\n第二行\n第三行末尾'
    q1_task = {"session_id": busy_sid, "cwd": workspace, "task_id": "Q1", "lease_id": "LQ1"}
    q1_ref = {"proc": None, "kind": None}
    try:
        os.remove(os.environ["FAKE_QUEUE_ARGV_LOG"])
    except FileNotFoundError:
        pass
    q1_outcome = _EXECUTOR._run_queue_once(q1_task, q1_prompt, 10, q1_ref)
    q1_argv = wait_for(read_queue_argv, 5)
    q1_message = (q1_argv[q1_argv.index("--message") + 1]
                  if q1_argv and "--message" in q1_argv else None)
    check("Q1 原生 codex.exe 保持特殊字符与多行 prompt 逐字一致",
          q1_outcome["status"] == "accepted" and q1_message == q1_prompt,
          "message_exact=%s" % (q1_message == q1_prompt))

    # 停止常驻领取循环，后续单元使用同一执行器的 run_task 直接跑已领取信封。
    _stop_executor_loop()

    # CX-4：任务入队后目录消失，执行器报 CWD_MISSING 且不启动 CLI。
    gone_cwd = os.path.join(TMP, "cx4-gone")
    os.makedirs(gone_cwd)
    before_calls = len(read_calls())
    before_sent = len(SENT)
    send_message("cx4-cwd", "codex %s CX4_CWD_MISSING" % gone_cwd)
    cx4 = task_for_source("cx4-cwd")
    shutil.rmtree(gone_cwd)
    cx4_env = client.claim(0)
    if cx4_env:
        _EXECUTOR.run_task(cx4_env)
    cx4_state = store.get_task(cx4["task_id"]) if cx4 else None
    cx4_prompt = wait_for(lambda: any("工作目录不存在" in row[3] for row in SENT[before_sent:]), 5)
    check("CX-4 目录消失上报 CWD_MISSING 且不执行 CLI",
          bool(cx4_env and cx4_state and cx4_state["status"] == "NEED_DIR"
               and cx4_prompt
               and len(read_calls()) == before_calls),
          "status=%s" % (cx4_state["status"] if cx4_state else "missing"))

    # M1：与 Claude 执行器一致，将 MSIX 虚拟 APPDATA 路径映射到真实 LocalCache/Roaming。
    virtual_appdata = os.path.join(TMP, "virtual", "Roaming")
    virtual_cwd = os.path.join(virtual_appdata, "Codex", "project")
    local_appdata = os.path.join(TMP, "local")
    real_cwd = os.path.join(local_appdata, "Packages", "OpenAI.Codex_test", "LocalCache",
                            "Roaming", "Codex", "project")
    os.makedirs(real_cwd, exist_ok=True)
    prior_appdata, prior_localappdata = os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")
    os.environ["APPDATA"], os.environ["LOCALAPPDATA"] = virtual_appdata, local_appdata
    try:
        mapped_cwd = codex_executor.resolve_cwd(virtual_cwd)
    finally:
        if prior_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = prior_appdata
        if prior_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = prior_localappdata
    check("M1 MSIX 虚拟 APPDATA cwd 映射到真实 LocalCache/Roaming",
          mapped_cwd == real_cwd, "mapped=%s" % mapped_cwd)

    # CX-5：任务运行超过租约时限，心跳持续续租直到正常完成。
    send_message("cx5-heartbeat", "codex %s CX5_HEARTBEAT" % workspace)
    cx5 = task_for_source("cx5-heartbeat")
    cx5_env = client.claim(0)
    cx5_thread = None
    if cx5_env:
        cx5_thread = threading.Thread(target=_EXECUTOR.run_task, args=(cx5_env,), daemon=True)
        cx5_thread.start()
    def cx5_is_running():
        if not cx5:
            return None
        task = store.get_task(cx5["task_id"])
        has_cli = any("CX5_HEARTBEAT" in c.get("prompt", "") for c in read_calls())
        return task if task["status"] == "LEASED" and task["session_id"] and has_cli else None
    started = wait_for(cx5_is_running, 5)
    time.sleep(3.4)
    cx5_still_leased = bool(started and cx5 and store.get_task(cx5["task_id"])["status"] == "LEASED"
                             and store.get_task(cx5["task_id"])["lease_expires"] > time.time())
    cx5_done = wait_for(lambda: flush_and_task(cx5["task_id"])
                        if cx5 and flush_and_task(cx5["task_id"])["status"] == "DONE" else None, 10)
    if cx5_thread:
        cx5_thread.join(timeout=2)
    check("CX-5 长任务心跳续租并最终完成",
          bool(started and cx5_still_leased and cx5_done),
          "still_leased=%s final=%s" % (cx5_still_leased, cx5_done["status"] if cx5_done else "missing"))

    # CX-6：杀掉常驻执行器及子进程树，租约过期后需人工续跑且不自动重派。
    runner_path = _write_runner_config(fake_cmd)
    runner_env = os.environ.copy()
    runner_env["FEISHU_HUB_HOME"] = HUB_HOME
    runner_env["FEISHU_HUB_URL"] = url
    runner_env["FAKE_CODEX_CALL_LOG"] = os.environ["FAKE_CODEX_CALL_LOG"]
    _RUNNER = subprocess.Popen([sys.executable, runner_path], cwd=ROOT, env=runner_env,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    send_message("cx6-kill", "codex %s CX6_EXECUTOR_KILL" % workspace)
    cx6 = task_for_source("cx6-kill")
    cx6_leased = wait_for(lambda: (t if (t := store.get_task(cx6["task_id"]))
                                   and t["status"] == "LEASED" and t["session_id"] else None)
                          if cx6 else None, 10)
    cx6_call = wait_for(lambda: next((c for c in read_calls()
                                      if "CX6_EXECUTOR_KILL" in c.get("prompt", "")), None), 10)
    if _RUNNER and _RUNNER.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(_RUNNER.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            _RUNNER.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _RUNNER.kill()
            _RUNNER.wait(timeout=5)
    runner_log = os.path.join(HUB_HOME, "executor_codex.log")
    cx6_log_ok = wait_for(lambda: read_text_file(runner_log), 3)
    check("L1 执行器 main 将启动日志写入临时 HUB_HOME 文件",
          "[Codex执行器] 已上线" in cx6_log_ok,
          "log_exists=%s" % os.path.isfile(runner_log))
    cx6_pid_stopped = bool(cx6_call and wait_for(lambda: not _pid_running(cx6_call.get("pid")), 5))
    cx6_recovery = wait_for_recovery(cx6["task_id"], 8) if cx6 else None
    no_auto_retry = client.claim(0) is None
    cx6_notice = cx6_recovery.get("notice_mid") if cx6_recovery else None
    if cx6_notice:
        send_message("cx6-retry", "续跑", cx6_notice)
    cx6_retry_env = client.claim(0)
    cx6_retry_ok = bool(cx6_retry_env and cx6_retry_env["task_id"] == cx6["task_id"]
                        and cx6_retry_env["attempt"] == 2 and cx6_retry_env["session_id"]
                        and "中断" in (cx6_retry_env.get("resume_hint") or ""))
    if cx6_retry_env:
        _EXECUTOR.run_task(cx6_retry_env)
    cx6_done = wait_for(lambda: flush_and_task(cx6["task_id"])
                        if cx6 and flush_and_task(cx6["task_id"])["status"] == "DONE" else None, 12)
    check("CX-6 执行器退出后不自动重跑，用户续跑带 resume_hint 后完成",
          bool(cx6_leased and cx6_pid_stopped and cx6_recovery
               and cx6_recovery["status"] == "NEEDS_RECOVERY" and no_auto_retry
               and cx6_retry_ok and cx6_done),
          "recovery=%s retry=%s done=%s" % (cx6_recovery["status"] if cx6_recovery else "missing",
                                             cx6_retry_ok, bool(cx6_done)))

    # CX-7：Hub 返回 LEASE_LOST 时，Codex 进程及其孙进程都应结束。
    send_message("cx7-lost", "codex %s CX7_LEASE_LOST_TREE" % workspace)
    cx7 = task_for_source("cx7-lost")
    cx7_env = client.claim(0)
    cx7_thread = None
    if cx7_env:
        cx7_thread = threading.Thread(target=_EXECUTOR.run_task, args=(cx7_env,), daemon=True)
        cx7_thread.start()
    child_file = os.path.join(workspace, "cx7_child.pid")
    child_ready = wait_for(lambda: open(child_file, "r", encoding="ascii").read().strip()
                           if os.path.exists(child_file) else None, 8)
    child_pid = int(child_ready) if child_ready else 0
    cx7_calls = [c for c in read_calls() if "CX7_LEASE_LOST_TREE" in c.get("prompt", "")]
    parent_pid = cx7_calls[-1].get("pid") if cx7_calls else 0
    if cx7:
        # 进入非租约状态以模拟 Hub 撤销租约；随后心跳必须收到 409 LEASE_LOST。
        store.update(cx7["task_id"], status="NEEDS_RECOVERY", lease_id=None)
    cx7_tree_stopped = wait_for(lambda: (not _pid_running(parent_pid) and not _pid_running(child_pid)), 8)
    if cx7_thread:
        cx7_thread.join(timeout=3)
    check("CX-7 收到 LEASE_LOST 后立即结束进程树",
          bool(cx7_env and child_ready and cx7_tree_stopped and cx7_thread and not cx7_thread.is_alive()),
          "parent=%s child=%s stopped=%s" % (parent_pid, child_pid, cx7_tree_stopped))

    # CX-8：独立桌面轮次同 turn-id 重复上报只生成一张卡。
    before_cards = len(SENT)
    cx8_payload = {"session_id": "THREAD-CX8", "cwd": workspace, "turn_id": "cx8-turn-1",
                   "last_assistant_message": "CX8 独立桌面回复"}
    cx8_first = hook_stop.handle_payload(cx8_payload, client)
    wait_for(lambda: len(SENT) > before_cards, 5)
    after_first = len(SENT)
    cx8_second = hook_stop.handle_payload(cx8_payload, client)
    service.flush_outbox()
    cx8_rows = store._conn().execute(
        "SELECT COUNT(*) FROM turns WHERE executor='codex' AND session_id=? AND turn_id=?",
        ("THREAD-CX8", "cx8-turn-1")).fetchone()[0]
    check("CX-8 Stop Hook 独立轮次重复上报不重复发卡",
          bool(cx8_first == "sent" and cx8_second == "sent" and after_first == before_cards + 1
               and len(SENT) == after_first and cx8_rows == 1),
          "cards=%d turns=%d" % (len(SENT) - before_cards, cx8_rows))

    # CX-9：执行器任务环境变量直接抑制桌面 Hook。
    class CountingClient:
        def __init__(self):
            self.calls = 0

        def request(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("任务 Hook 不应调用 Hub")

    counting = CountingClient()
    prior_task_id = os.environ.get("FEISHU_HUB_TASK_ID")
    os.environ["FEISHU_HUB_TASK_ID"] = "T-CX9"
    try:
        cx9_result = hook_stop.handle_payload(
            {"session_id": "THREAD-CX9", "cwd": workspace, "turn_id": "cx9-turn",
             "last_assistant_message": "不应上报"}, counting)
    finally:
        if prior_task_id is None:
            os.environ.pop("FEISHU_HUB_TASK_ID", None)
        else:
            os.environ["FEISHU_HUB_TASK_ID"] = prior_task_id
    check("CX-9 FEISHU_HUB_TASK_ID 存在时 Hook 不调用 /sessions/turns",
          cx9_result == "suppressed" and counting.calls == 0,
          "request_calls=%d" % counting.calls)

    # CX-10：Hook 离线落盘，执行器重新连上临时 Hub 后补发并删除 spool 项。
    class OfflineClient:
        def request(self, *args, **kwargs):
            raise HubError(0, "UNREACHABLE", "test offline")

    os.makedirs(SPOOL_DIR, exist_ok=True)
    for name in os.listdir(SPOOL_DIR):
        os.remove(os.path.join(SPOOL_DIR, name))
    cx10_result = hook_stop.handle_payload(
        {"session_id": "THREAD-CX10", "cwd": workspace, "turn_id": "cx10-turn",
         "last_assistant_message": "CX10 离线后补发"}, OfflineClient())
    spooled_before = [n for n in os.listdir(SPOOL_DIR) if n.endswith(".json")]
    _EXECUTOR.flush_spool_once()
    cx10_rows = store._conn().execute(
        "SELECT COUNT(*) FROM turns WHERE executor='codex' AND session_id=? AND turn_id=?",
        ("THREAD-CX10", "cx10-turn")).fetchone()[0]
    spooled_after = [n for n in os.listdir(SPOOL_DIR) if n.endswith(".json")]
    check("CX-10 Hook 离线落盘后由执行器补发成功并清空 spool",
          bool(cx10_result == "spooled" and len(spooled_before) == 1
               and cx10_rows == 1 and not spooled_after),
          "spooled=%d turns=%d remaining=%d" % (len(spooled_before), cx10_rows, len(spooled_after)))


def cleanup():
    global _RUNNER
    _stop_executor_loop()
    if _RUNNER and _RUNNER.poll() is None:
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(_RUNNER.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            _RUNNER.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                _RUNNER.kill()
            except OSError:
                pass
    if _BACKGROUND_STOP:
        _BACKGROUND_STOP.set()
    if _BACKGROUND_THREAD:
        _BACKGROUND_THREAD.join(timeout=3)
    if _SERVER:
        _SERVER.shutdown()
        _SERVER.server_close()
    if _SERVER_THREAD:
        _SERVER_THREAD.join(timeout=3)
    # 清理测试脚本留下的假 CLI 进程，不接触测试目录以外的进程。
    for call in read_calls():
        _kill_pid_tree(call.get("pid"))
        _kill_pid_tree(call.get("child_pid"))
    shutil.rmtree(TMP, ignore_errors=True)


def main():
    try:
        run_tests()
    except Exception as e:  # noqa: BLE001
        check("测试运行异常", False, "%s: %s" % (type(e).__name__, e))
    finally:
        cleanup()
    failed = [name for name, ok in CHECKS if not ok]
    print("[测试] CX-1～CX-10 共 %d 项检查，失败 %d 项：%s" %
          (len(CHECKS), len(failed), failed), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
