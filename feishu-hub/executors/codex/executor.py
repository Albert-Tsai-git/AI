# -*- coding: utf-8 -*-
"""[Codex执行器] 按执行器协议 v1 领取并执行任务，只与中间服务通信。"""
import argparse
import ctypes
from ctypes import wintypes
from collections import deque
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from hub_client import HUB_HOME, HubClient, HubError, LeaseLost, TaskReporter, flush_spool  # noqa: E402


LOG = logging.getLogger("feishu_hub.codex")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ACTIVE_WRITER_TEXT = "already has an active writer"
RESULT_LIMIT_BYTES = 256 * 1024


def _vendor_codex_exe(shim):
    """[CLI] 从 npm 的 codex 启动脚本定位 Windows 原生可执行文件。"""
    if not shim:
        return None
    candidate = os.path.join(os.path.dirname(os.path.abspath(shim)), "node_modules", "@openai", "codex",
                             "node_modules", "@openai", "codex-win32-x64", "vendor",
                             "x86_64-pc-windows-msvc", "bin", "codex.exe")
    return candidate if os.path.isfile(candidate) else None


def find_default_codex_exe():
    """[CLI] 优先使用 npm 包内的 codex.exe，找不到时回退到 PATH。"""
    shim = shutil.which("codex") or "codex"
    return _vendor_codex_exe(shim) or shim


def queue_codex_exe(configured):
    """[队列] 带用户 prompt 的命令只能直接启动 .exe，不能交给 cmd.exe 解析。"""
    resolved = shutil.which(configured) or configured
    if os.path.splitext(resolved)[1].casefold() == ".exe":
        return resolved
    return _vendor_codex_exe(resolved)


def resolve_cwd(cwd):
    """[目录] 将 MSIX 的虚拟 %APPDATA% 路径映射到真实 LocalCache/Roaming 目录。"""
    if not cwd:
        return None
    if os.path.isdir(cwd):
        return cwd
    roaming = os.environ.get("APPDATA", "")
    norm = os.path.normcase(os.path.normpath(cwd))
    if roaming and norm.startswith(os.path.normcase(os.path.normpath(roaming)) + os.sep):
        rel = os.path.normpath(cwd)[len(os.path.normpath(roaming)) + 1:]
        pkgs = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
        for name in sorted(os.listdir(pkgs)) if os.path.isdir(pkgs) else []:
            candidate = os.path.join(pkgs, name, "LocalCache", "Roaming", rel)
            if os.path.isdir(candidate):
                return candidate
    return None


DEFAULTS = {
    "codex_exe": find_default_codex_exe(),
    "codex_args": ["--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"],
    "max_parallel": 3,
    "spool_flush_sec": 60,
    # 测试可覆盖为临时文件；常规运行使用用户的 Codex 配置。
    "codex_config_toml": None,
}


def _codex_notify_argv():
    """[Hook] 返回 notify 需要调用的无窗口 Python 和 Hook 路径。"""
    pythonw = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "pythonw.exe")
    hook = os.path.abspath(os.path.join(os.path.dirname(__file__), "hook_stop.py"))
    return [pythonw, hook]


def _is_hook_stop(path):
    """[Hook] 比较规范化后的绝对路径，兼容 TOML 中的斜杠写法。"""
    if not isinstance(path, str):
        return False
    expected = os.path.normcase(os.path.normpath(os.path.abspath(
        os.path.join(os.path.dirname(__file__), "hook_stop.py"))))
    actual = os.path.normcase(os.path.normpath(path))
    return actual == expected


def _top_level_notify_span(text):
    """[配置] 找到顶层 notify 赋值及其多行 TOML 值对应的行范围。"""
    lines = text.splitlines(keepends=True)
    in_table = False
    for start, line in enumerate(lines):
        stripped = line.lstrip()
        if re.match(r"^\[\[?", stripped):
            in_table = True
        if in_table or not re.match(r"^\s*notify\s*=", line):
            continue
        statement = ""
        for end in range(start, len(lines)):
            statement += lines[end]
            try:
                tomllib.loads(statement)
                return start, end + 1
            except tomllib.TOMLDecodeError:
                continue
        return start, len(lines)
    return None


def _toml_notify_array(argv):
    """[配置] 将 argv 编码为合法 TOML 字符串数组。"""
    return json.dumps(argv, ensure_ascii=False)


def ensure_codex_notify_config(config_path=None):
    """[配置] 保留 computer-use notify 并串接桌面轮次 Hook。"""
    path = config_path or DEFAULTS.get("codex_config_toml") or os.path.join(
        os.path.expanduser("~"), ".codex", "config.toml")
    path = os.path.abspath(os.fspath(path))
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            original = f.read()
        parsed = tomllib.loads(original)
    except FileNotFoundError:
        original = ""
        parsed = {}
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as e:
        LOG.warning("[Codex执行器] Codex 配置无法解析，未修改：%s", type(e).__name__)
        return "invalid"

    desired_previous = _codex_notify_argv()
    current = parsed.get("notify")
    if "notify" not in parsed or current == []:
        updated_argv = desired_previous
    elif (isinstance(current, list) and current and all(isinstance(arg, str) for arg in current)
          and os.path.basename(current[0]).casefold() == "codex-computer-use.exe"
          and "turn-ended" in current):
        updated_argv = list(current)
        flag_indexes = [i for i, arg in enumerate(updated_argv) if arg == "--previous-notify"]
        already_chained = False
        for index in flag_indexes:
            if index + 1 >= len(updated_argv):
                continue
            try:
                previous = json.loads(updated_argv[index + 1])
            except (TypeError, ValueError):
                previous = [updated_argv[index + 1]]
            if isinstance(previous, list) and any(_is_hook_stop(item) for item in previous):
                already_chained = True
                break
        if already_chained and len(flag_indexes) == 1:
            LOG.info("[Codex执行器] Codex notify Hook 已串接")
            return "unchanged"
        # 清理旧值及重复开关后统一写入 JSON argv，保留其他 computer-use 参数。
        cleaned = []
        i = 0
        while i < len(updated_argv):
            if updated_argv[i] == "--previous-notify":
                i += 1
                if i < len(updated_argv) and not updated_argv[i].startswith("--"):
                    i += 1
                continue
            cleaned.append(updated_argv[i])
            i += 1
        updated_argv = cleaned + ["--previous-notify", json.dumps(desired_previous, ensure_ascii=False)]
    else:
        LOG.warning("[Codex执行器] Codex notify 指向未知程序，保留原配置")
        return "unknown"

    span = _top_level_notify_span(original)
    newline = "\r\n" if "\r\n" in original else "\n"
    assignment = "notify = %s%s" % (_toml_notify_array(updated_argv), newline)
    if span:
        start, end = span
        lines = original.splitlines(keepends=True)
        updated = "".join(lines[:start]) + assignment + "".join(lines[end:])
    else:
        # 顶层键必须位于表格声明之前，避免被追加到某个子表中。
        updated = assignment + original
    try:
        tomllib.loads(updated)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        backup = path + ".bak"
        if os.path.exists(path):
            shutil.copy2(path, backup)
        else:
            with open(backup, "wb") as f:
                f.write(b"")
        fd, temporary = tempfile.mkstemp(prefix=os.path.basename(path) + ".",
                                         suffix=".tmp", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(updated)
                f.flush()
                os.fsync(f.fileno())
            # 先校验临时文件，确保非法结果绝不会替换原配置。
            with open(temporary, "r", encoding="utf-8", newline="") as f:
                tomllib.loads(f.read())
            os.replace(temporary, path)
            with open(path, "r", encoding="utf-8", newline="") as f:
                tomllib.loads(f.read())
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as e:
        LOG.warning("[Codex执行器] Codex notify 配置写入失败：%s", type(e).__name__)
        return "error"
    LOG.info("[Codex执行器] 已更新 Codex notify 串接并备份原配置")
    return "updated"


def _notify_guard_loop(stop_event, config_path=None):
    """[常驻] 每分钟检查一次 CC-Switch 是否重写了 Codex notify。"""
    while not stop_event.wait(60):
        ensure_codex_notify_config(config_path)


def load_config(path=None):
    """[配置] 读取可选的 Codex 执行器配置。"""
    cfg = dict(DEFAULTS)
    cfg["codex_args"] = list(DEFAULTS["codex_args"])
    path = path or os.path.join(HUB_HOME, "executor_codex.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            custom = json.load(f)
        if isinstance(custom, dict):
            cfg.update(custom)
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        LOG.warning("[Codex执行器] 配置读取失败，使用默认配置：%s", type(e).__name__)
    if not isinstance(cfg.get("codex_exe"), str) or not cfg["codex_exe"]:
        cfg["codex_exe"] = DEFAULTS["codex_exe"]
    if not isinstance(cfg.get("codex_args"), list) or not all(isinstance(x, str) for x in cfg["codex_args"]):
        cfg["codex_args"] = list(DEFAULTS["codex_args"])
    try:
        cfg["max_parallel"] = max(1, int(cfg.get("max_parallel", 3)))
    except (TypeError, ValueError):
        cfg["max_parallel"] = 3
    try:
        cfg["spool_flush_sec"] = max(1, int(cfg.get("spool_flush_sec", 60)))
    except (TypeError, ValueError):
        cfg["spool_flush_sec"] = 60
    return cfg


def _proc_ctime(pid):
    """[进程] 读取 Windows FILETIME 创建时间，用于识别 PID 复用。"""
    try:
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        k32.GetProcessTimes.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        handle = k32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return None
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not k32.GetProcessTimes(handle, *[ctypes.byref(x) for x in times]):
                return None
            return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        finally:
            k32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return None


def kill_tree(proc):
    """[进程] 结束子进程树；Windows 使用 taskkill /T /F。"""
    if not proc or proc.poll() is not None:
        return
    try:
        result = subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                                capture_output=True, creationflags=NO_WINDOW, timeout=10)
        if result.returncode == 0:
            return
    except (OSError, subprocess.TimeoutExpired):
        pass
    # taskkill 不可用或未能结束进程树时，至少停止根进程。
    try:
        if proc.poll() is None:
            proc.kill()
    except OSError:
        pass


def _truncate_result(text):
    """[结果] 将可见回复限制在协议允许的 256 KB 内。"""
    raw = (text or "").encode("utf-8")
    if len(raw) <= RESULT_LIMIT_BYTES:
        return text or ""
    suffix = "\n\n[结果已截断]"
    cut = raw[:RESULT_LIMIT_BYTES - len(suffix.encode("utf-8"))].decode("utf-8", "ignore")
    return cut + suffix


def _event_error_text(obj):
    """[事件] 只提取 CLI 错误事件的诊断文本，不保存其他 JSONL 内容。"""
    value = obj.get("error") or obj.get("message") or ""
    if isinstance(value, dict):
        value = value.get("message") or value.get("msg") or ""
    return str(value)[:2000]


def _queue_id(output):
    """[队列] 从 codex queue 的成功回执中提取队列 ID。"""
    for line in reversed((output or "").splitlines()):
        if "queued message" not in line.casefold():
            continue
        match = re.search(r"([A-Za-z0-9_-]{8,})\s*$", line.strip())
        if match:
            return match.group(1)
    return None


def _classify_failure(text):
    """[错误分类] 仅按稳定错误片段映射协议失败码。"""
    lowered = (text or "").casefold()
    if any(s in lowered for s in ("no conversation found", "session not found", "thread not found",
                                  "conversation not found", "no such session", "session does not exist")):
        return "SESSION_NOT_FOUND"
    if any(s in lowered for s in ("unauthorized", "authentication required", "not logged in", "login required", "run codex login", "401")):
        return "AUTH_REQUIRED"
    return "EXEC_ERROR"


class CodexExecutor:
    """[执行器] 常驻领取任务，并在租约失效时结束对应子进程树。"""

    def __init__(self, cfg=None, client=None):
        self.cfg = cfg or load_config()
        hub_url = os.environ.get("FEISHU_HUB_URL") or os.environ.get("HUB_URL")
        self.client = client or HubClient("codex", url=hub_url)
        self.heartbeat_sec = 30
        self.poll_wait_sec = 25
        self.slots = threading.Semaphore(self.cfg["max_parallel"])

    def build_env(self, task):
        """[环境] 为 Codex 子进程添加任务标识，避免桌面 Hook 重复上报。"""
        env = os.environ.copy()
        env.update({
            "FEISHU_HUB_URL": self.client.url,
            "FEISHU_HUB_TASK_ID": str(task["task_id"]),
            "FEISHU_HUB_LEASE_ID": str(task["lease_id"]),
            "FEISHU_HUB_CWD": str(task["cwd"]),
        })
        return env

    def build_exec_cmd(self, task, output_path):
        """[命令] 按 CLI help 规定的 exec/resume 子命令形式构造命令行。"""
        cmd = [self.cfg["codex_exe"], "exec"]
        if task.get("mode") == "resume":
            cmd.append("resume")
        cmd.extend(self.cfg["codex_args"])
        cmd.extend(["--json", "--output-last-message", output_path])
        if task.get("mode") == "resume":
            cmd.extend([str(task.get("session_id") or ""), "-"])
        else:
            cmd.append("-")
        return cmd

    def build_queue_cmd(self, task, prompt):
        """[队列] queue CLI 只提供 --message 文本参数，按其帮助格式投递一次。"""
        exe = queue_codex_exe(self.cfg["codex_exe"])
        if not exe:
            raise FileNotFoundError("codex queue 需要直接可执行的 codex.exe")
        # queue 不支持 exec 专属的 --skip-git-repo-check，只传其帮助列出的危险模式开关。
        queue_args = [arg for arg in self.cfg["codex_args"]
                      if arg == "--dangerously-bypass-approvals-and-sandbox"]
        return [exe, "queue"] + queue_args + [
            "--thread", str(task.get("session_id") or ""), "--message", prompt, "-C", str(task["cwd"])
        ]

    def _drain_stdout(self, stream, events):
        """[输出] 逐行解析 JSONL 生命周期字段，不保留工具输出或私有内容。"""
        try:
            for raw in iter(stream.readline, b""):
                try:
                    obj = json.loads(raw.decode("utf-8", "replace"))
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(obj, dict):
                    continue
                kind = obj.get("type")
                if kind == "thread.started":
                    events.put(("thread", str(obj.get("thread_id") or "")))
                elif kind in ("turn.started", "item.started", "item.updated", "item.completed"):
                    events.put(("active", ""))
                elif kind in ("turn.failed", "error"):
                    events.put(("error", _event_error_text(obj)))
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _drain_stderr(self, stream, tail):
        """[诊断] 只在内存保留 stderr 尾部，避免管道阻塞且不记录原始日志。"""
        size = 0
        try:
            for raw in iter(stream.readline, b""):
                tail.append(raw)
                size += len(raw)
                while size > 8192 and tail:
                    size -= len(tail.popleft())
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _report_started(self, reporter, task, proc, state):
        """[事件] 在确认 CLI 会话开始后上报 started，并按需绑定会话。"""
        if not state["started"]:
            reporter.send("started", {"delivery": "process", "pid": proc.pid,
                                       "pid_ctime": _proc_ctime(proc.pid)})
            state["started"] = True
        sid = state.get("session_id")
        if (sid and (task.get("mode") == "new" or sid != task.get("session_id"))
                and state["session_reported"] != sid):
            reporter.send("session", {"session_id": sid})
            state["session_reported"] = sid

    def _run_exec(self, task, prompt, output_path, reporter, process_ref, timeout_sec):
        """[执行] 启动 exec，收集 thread-id，并检测是否能安全回退到桌面队列。"""
        cmd = self.build_exec_cmd(task, output_path)
        proc = subprocess.Popen(cmd, cwd=task["cwd"], env=self.build_env(task), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        process_ref["proc"] = proc
        process_ref["kind"] = "exec"
        reporter.start_heartbeat()

        events = queue.SimpleQueue()
        stderr_tail = deque()
        state = {"started": False, "session_id": "", "session_reported": None}
        stdout_thread = threading.Thread(target=self._drain_stdout, args=(proc.stdout, events), daemon=True)
        stderr_thread = threading.Thread(target=self._drain_stderr, args=(proc.stderr, stderr_tail), daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        def write_prompt():
            try:
                proc.stdin.write(prompt.encode("utf-8"))
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        threading.Thread(target=write_prompt, daemon=True).start()
        start_time = time.monotonic()
        deadline = start_time + max(0.1, float(timeout_sec))

        def consume_event(event_type, value):
            """[事件] 消费一个已读取的 JSONL 生命周期事件。"""
            if event_type == "thread":
                state["session_id"] = value
                self._report_started(reporter, task, proc, state)
            elif event_type == "active":
                self._report_started(reporter, task, proc, state)
            elif event_type == "error" and value:
                state.setdefault("errors", []).append(value)

        def drain_events():
            """[事件] 排空当前已读到的事件。"""
            while True:
                try:
                    consume_event(*events.get_nowait())
                except queue.Empty:
                    return

        while True:
            if reporter.lost.is_set():
                kill_tree(proc)
                raise LeaseLost(409, "LEASE_LOST")
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                kill_tree(proc)
                if not state["started"]:
                    self._report_started(reporter, task, proc, state)
                return {"status": "timeout", "started": state["started"], "session_id": state["session_id"]}
            try:
                event_type, value = events.get(timeout=min(0.1, remaining))
                consume_event(event_type, value)
            except queue.Empty:
                pass
            if proc.poll() is not None:
                break

        # 主进程退出后，仍可能有派生进程持有管道写端；分段等待以响应租约丢失。
        readers = (stdout_thread, stderr_thread)
        while any(reader.is_alive() for reader in readers):
            if reporter.lost.is_set():
                kill_tree(proc)
                for stream in (proc.stdout, proc.stderr):
                    threading.Thread(target=self._close_pipe, args=(stream,), daemon=True).start()
                raise LeaseLost(409, "LEASE_LOST")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            for reader in readers:
                if reader.is_alive():
                    reader.join(timeout=min(0.1, remaining))
        if stdout_thread.is_alive() or stderr_thread.is_alive():
            # close() 本身可能等待正在阻塞的 readline，因此放到守护线程中清理。
            for stream in (proc.stdout, proc.stderr):
                threading.Thread(target=self._close_pipe, args=(stream,), daemon=True).start()
            drain_events()
            return {"status": "timeout", "started": state["started"],
                    "session_id": state["session_id"]}
        # 先等待输出读取线程处理 EOF，再排空队列，避免快速退出时漏掉 thread-id。
        drain_events()
        stderr_text = b"".join(stderr_tail).decode("utf-8", "replace")
        return {"status": "exit", "returncode": proc.returncode, "started": state["started"],
                "session_id": state["session_id"], "stderr": stderr_text,
                "session_reported": state["session_reported"], "pid": proc.pid,
                "errors": "\n".join(state.get("errors", []))}

    @staticmethod
    def _close_pipe(stream):
        """[清理] 异步关闭管道，避免 readline 阻塞时卡住执行器线程。"""
        try:
            stream.close()
        except (OSError, ValueError):
            pass

    def _run_queue_once(self, task, prompt, timeout_sec, process_ref):
        """[队列] 只调用一次 queue；启动后的任何不确定结果都返回空 queue_id。"""
        cmd = self.build_queue_cmd(task, prompt)
        proc = subprocess.Popen(cmd, cwd=task["cwd"], env=self.build_env(task), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        process_ref["proc"] = proc
        process_ref["kind"] = "queue"
        try:
            out, err = proc.communicate(timeout=max(0.1, float(timeout_sec)))
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            try:
                out, err = proc.communicate(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                out, err = b"", b""
            return {"status": "uncertain", "queue_id": None, "stderr": ""}
        except Exception:
            kill_tree(proc)
            return {"status": "uncertain", "queue_id": None, "stderr": ""}
        output = out.decode("utf-8", "replace")
        stderr = err.decode("utf-8", "replace")
        if proc.returncode == 0:
            return {"status": "accepted", "queue_id": _queue_id(output), "stderr": stderr}
        return {"status": "uncertain", "queue_id": None, "stderr": stderr}

    def _send_failed(self, reporter, code, message):
        """[事件] 上报脱敏后的可见失败信息。"""
        try:
            reporter.send("failed", {"code": code, "message": message, "retryable": False})
        finally:
            reporter.finish()

    @staticmethod
    def _send_and_finish(reporter, event_type, data):
        """[事件] 保持心跳直到 Hub 接受事件或请求彻底失败。"""
        try:
            return reporter.send(event_type, data)
        finally:
            reporter.finish()

    def run_task(self, task):
        """[执行] 校验目录、执行 Codex、处理桌面队列或上报终态事件。"""
        reporter = TaskReporter(self.client, task, self.heartbeat_sec)
        process_ref = {"proc": None, "kind": None}
        reporter.on_lost = lambda: kill_tree(process_ref["proc"])
        queue_attempted = False
        try:
            real_cwd = resolve_cwd(str(task.get("cwd") or ""))
            if not real_cwd:
                self._send_failed(reporter, "CWD_MISSING", "工作目录不存在；未启动 Codex。")
                return
            task = dict(task, cwd=real_cwd)
            if task.get("mode") == "resume" and not task.get("session_id"):
                self._send_failed(reporter, "SESSION_NOT_FOUND", "续跑任务缺少会话 ID。")
                return

            prompt = str(task.get("prompt") or "")
            hint = task.get("resume_hint")
            if hint:
                prompt = str(hint) + "\n\n" + prompt
            limits = task.get("limits") or {}
            try:
                timeout_sec = max(1, int(limits.get("timeout_sec", 1800)))
            except (TypeError, ValueError):
                timeout_sec = 1800
            deadline = time.monotonic() + timeout_sec

            with tempfile.TemporaryDirectory(prefix="feishu-hub-codex-") as run_dir:
                output_path = os.path.join(run_dir, "last-message.txt")
                outcome = self._run_exec(task, prompt, output_path, reporter, process_ref, timeout_sec)
                if outcome["status"] == "timeout":
                    self._send_and_finish(reporter, "interrupted", {"reason": "执行超时"})
                    return

                combined_error = outcome.get("stderr", "") + "\n" + outcome.get("errors", "")
                active_writer = (task.get("mode") == "resume"
                                 and outcome.get("returncode", 0) != 0
                                 and ACTIVE_WRITER_TEXT in combined_error.casefold())
                busy = active_writer and not outcome.get("started")
                if busy:
                    if reporter.lost.is_set():
                        raise LeaseLost(409, "LEASE_LOST")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._send_and_finish(reporter, "interrupted", {"reason": "执行超时"})
                        return
                    try:
                        queue_attempted = True
                        queued = self._run_queue_once(task, prompt, remaining, process_ref)
                    except OSError as e:
                        code = "CLI_NOT_FOUND" if isinstance(e, FileNotFoundError) else "EXEC_ERROR"
                        self._send_failed(reporter, code, "Codex 桌面队列启动失败。")
                        return
                    if queued["status"] == "uncertain" and queued.get("stderr"):
                        known = _classify_failure(queued["stderr"])
                        if known in ("SESSION_NOT_FOUND", "AUTH_REQUIRED"):
                            self._send_and_finish(reporter, "failed", {"code": known,
                                                                        "message": "Codex 桌面队列未确认接收。",
                                                                        "retryable": False})
                            return
                    self._send_and_finish(reporter, "started", {"delivery": "desktop_queue",
                                                                  "queue_id": queued.get("queue_id")})
                    LOG.info("[Codex执行器] 任务 %s 已投递桌面队列 queue_id=%s", task.get("task_id"),
                             queued.get("queue_id") or "null")
                    return

                # CLI 已报告会话或轮次开始后，active-writer 冲突只能中断，不能转投队列。
                if active_writer and outcome.get("started"):
                    self._send_and_finish(reporter, "interrupted",
                                          {"reason": "Codex resume 开始后遇到 active writer 冲突"})
                    return

                if outcome.get("returncode") != 0:
                    code = _classify_failure(combined_error)
                    self._send_failed(reporter, code, "Codex 执行失败（%s）。" % code)
                    return

                session_id = outcome.get("session_id") or task.get("session_id") or ""
                if not session_id:
                    self._send_failed(reporter, "NO_RESULT", "Codex 未提供可恢复的 thread-id。")
                    return
                try:
                    with open(output_path, "r", encoding="utf-8") as f:
                        text = f.read()
                except OSError:
                    text = ""
                text = _truncate_result(text.strip())
                if not text:
                    self._send_failed(reporter, "NO_RESULT", "Codex 正常退出，但没有最终回复。")
                    return
                if not outcome.get("started"):
                    reporter.send("started", {"delivery": "process", "pid": outcome.get("pid"),
                                               "pid_ctime": _proc_ctime(outcome.get("pid"))})
                    outcome["started"] = True
                if (session_id != task.get("session_id")
                        and outcome.get("session_reported") != session_id):
                    reporter.send("session", {"session_id": session_id})
                self._send_and_finish(reporter, "result", {"text": text, "session_id": session_id})
                LOG.info("[Codex执行器] 任务 %s 已完成", task.get("task_id"))
        except LeaseLost:
            kill_tree(process_ref["proc"])
            LOG.info("[Codex执行器] 任务 %s 租约已丢失，已停止子进程树", task.get("task_id"))
        except Exception as e:  # noqa: BLE001
            proc = process_ref.get("proc")
            if proc:
                kill_tree(proc)
            LOG.exception("[Codex执行器] 任务 %s 执行器异常 %s", task.get("task_id"), type(e).__name__)
            try:
                if queue_attempted:
                    # queue 请求已经启动，投递结果不明时不得再次投递。
                    self._send_and_finish(reporter, "started", {"delivery": "desktop_queue", "queue_id": None})
                elif proc:
                    self._send_and_finish(reporter, "interrupted",
                                          {"reason": "执行器异常 %s" % type(e).__name__})
                else:
                    code = "CLI_NOT_FOUND" if isinstance(e, FileNotFoundError) else "EXEC_ERROR"
                    self._send_failed(reporter, code, type(e).__name__)
            except HubError:
                pass
        finally:
            reporter.finish()

    def _worker(self, task):
        """[并发] 单个任务结束后归还并发槽。"""
        try:
            self.run_task(task)
        finally:
            self.slots.release()

    def flush_spool_once(self):
        """[补发] 将 Hook 的离线桌面轮次补发到中间服务。"""
        try:
            count = flush_spool({"codex": self.client})
            if count:
                LOG.info("[Codex执行器] 已补发离线 Hook 轮次 %s 条", count)
        except Exception as e:  # noqa: BLE001
            LOG.warning("[Codex执行器] 补发离线 Hook 失败：%s", type(e).__name__)

    def serve_forever(self, stop_event=None):
        """[常驻] hello 后长轮询 claim，空闲时等待并发槽，避免本地已领任务失租。"""
        stop_event = stop_event or threading.Event()
        config_path = self.cfg.get("codex_config_toml")
        ensure_codex_notify_config(config_path)
        threading.Thread(target=_notify_guard_loop, args=(stop_event, config_path), daemon=True,
                         name="codex-notify-guard").start()
        info = self.client.hello({"new_session": True, "resume": True, "desktop_queue": True}, "0.1.0")
        self.heartbeat_sec = max(1, int(info.get("heartbeat_sec", 30)))
        self.poll_wait_sec = max(1, int(info.get("poll_wait_sec", 25)))
        self.flush_spool_once()

        def flush_loop():
            while not stop_event.wait(self.cfg["spool_flush_sec"]):
                self.flush_spool_once()

        threading.Thread(target=flush_loop, daemon=True).start()
        LOG.info("[Codex执行器] 已上线 instance=%s max_parallel=%s", self.client.instance_id,
                 self.cfg["max_parallel"])
        while not stop_event.is_set():
            if not self.slots.acquire(timeout=0.5):
                continue
            try:
                task = self.client.claim(self.poll_wait_sec)
            except HubError as e:
                self.slots.release()
                LOG.warning("[Codex执行器] 领取任务失败 code=%s", e.code)
                stop_event.wait(1)
                continue
            except Exception as e:  # noqa: BLE001
                self.slots.release()
                LOG.warning("[Codex执行器] 领取任务异常：%s", type(e).__name__)
                stop_event.wait(1)
                continue
            if not task:
                self.slots.release()
                continue
            LOG.info("[Codex执行器] 已领取任务 %s mode=%s", task.get("task_id"), task.get("mode"))
            threading.Thread(target=self._worker, args=(task,), daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="飞书多 AI 中转 Codex 执行器")
    parser.add_argument("--config", help="执行器 JSON 配置文件")
    args = parser.parse_args()
    os.makedirs(HUB_HOME, exist_ok=True)
    logging.basicConfig(filename=os.path.join(HUB_HOME, "executor_codex.log"), encoding="utf-8",
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    executor = CodexExecutor(load_config(args.config))
    executor.serve_forever()


if __name__ == "__main__":
    main()
