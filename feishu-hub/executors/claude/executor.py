# -*- coding: utf-8 -*-
"""[Claude执行器] 按 PROTOCOL.md v1 从中间服务领任务，在已确认目录中用 Claude Code CLI 执行并上报结果。
只与中间服务通信，不直接连飞书，不与其他执行器通信。
用法：python executors/claude/executor.py    （在 feishu-hub 目录下）"""
import json
import logging
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from hub_client import HUB_HOME, HubClient, HubError, LeaseLost, TaskReporter, flush_spool  # noqa: E402

VERSION = "0.1.0"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HUB_HOME, "executor_claude.json")
DEFAULTS = {
    # auto：优先使用 Claude 桌面版自带的最新 CLI（与桌面同版本，支持最新模型），找不到再用 fallback
    "claude_exe": "auto",
    "claude_exe_fallback": r"C:\nvm4w\nodejs\node_modules\@anthropic-ai\claude-code\bin\claude.exe",
    # 独立配置目录：不经过 CC-Switch 代理，单独登录；projects 与桌面共享
    "claude_config_dir": os.path.join(os.path.expanduser("~"), ".claude-feishu"),
    # 用户选择方案 C：无确认模式运行，不实施目录外授权
    "permission_mode": "bypassPermissions",
    # 默认模型与推理强度（用户指定 Opus 5.5 + low）；置空则沿用 CLI 自身默认
    "model": "claude-opus-5-5",
    "effort": "low",
    "max_parallel": 3,
    # 守护 ~/.claude/settings.json 中的桌面 Hook（CC-Switch 会整体重写该文件）
    "manage_hooks": False,
}
LOG = logging.getLogger("claude-executor")


def load_cfg():
    cfg = dict(DEFAULTS)
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH, "r", encoding="utf-8-sig") as f:
            cfg.update(json.load(f))
    return cfg


def resolve_cwd(cwd):
    """[目录] 映射到本机真实目录；Claude 桌面版（MSIX）的 %APPDATA% 路径实际在 Packages/*/LocalCache/Roaming。"""
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
            cand = os.path.join(pkgs, name, "LocalCache", "Roaming", rel)
            if os.path.isdir(cand):
                return cand
    return None


def _ver_key(name):
    try:
        return tuple(int(x) for x in name.split("."))
    except ValueError:
        return (-1,)


def find_desktop_cli():
    """[CLI] 查找 Claude 桌面版自带的 claude.exe，返回版本号最高的路径；找不到返回 None。
    桌面版（MSIX）写在 %APPDATA%/Claude/claude-code/<版本>/，包外进程看到的真实位置是
    %LOCALAPPDATA%/Packages/Claude_*/LocalCache/Roaming/Claude/claude-code/<版本>/。"""
    bases = [os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code")]
    pkgs = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
    if os.path.isdir(pkgs):
        bases += [os.path.join(pkgs, n, "LocalCache", "Roaming", "Claude", "claude-code")
                  for n in os.listdir(pkgs) if n.lower().startswith("claude_")]
    best = None
    for base in bases:
        if not os.path.isdir(base):
            continue
        for ver in os.listdir(base):
            exe = os.path.join(base, ver, "claude.exe")
            if os.path.isfile(exe) and (best is None or _ver_key(ver) > best[0]):
                best = (_ver_key(ver), exe)
    return best[1] if best else None


def _proc_ctime(pid):
    """进程创建时间（FILETIME），用于识别 pid 复用。"""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return None
        try:
            ft = [wintypes.FILETIME() for _ in range(4)]
            if not k32.GetProcessTimes(h, *[ctypes.byref(x) for x in ft]):
                return None
            return (ft[0].dwHighDateTime << 32) | ft[0].dwLowDateTime
        finally:
            k32.CloseHandle(h)
    except Exception:  # noqa: BLE001
        return None


def kill_tree(p):
    if p and p.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=NO_WINDOW)


class ClaudeExecutor:
    def __init__(self, cfg, client=None):
        self.cfg = cfg
        self.client = client or HubClient("claude")
        self.slots = threading.Semaphore(int(cfg["max_parallel"]))
        self.heartbeat_sec = 30

    def claude_exe(self):
        """每次执行时解析，桌面版升级后自动使用新版本。"""
        exe = self.cfg.get("claude_exe") or "auto"
        if exe == "auto":
            exe = find_desktop_cli() or self.cfg["claude_exe_fallback"]
        return exe

    def build_cmd(self, task):
        cmd = [self.claude_exe()]
        if task["mode"] == "resume" and task.get("session_id"):
            cmd += ["--resume", task["session_id"]]
        if self.cfg.get("model"):
            cmd += ["--model", self.cfg["model"]]
        if self.cfg.get("effort"):
            cmd += ["--effort", self.cfg["effort"]]
        return cmd + ["-p", "--output-format", "json", "--permission-mode", self.cfg["permission_mode"]]

    def build_env(self, task):
        env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_") and not k.startswith("CLAUDE")}
        env["CLAUDE_CONFIG_DIR"] = self.cfg["claude_config_dir"]
        # 子进程里的桌面 Hook 看到任务号就不再上报（结果由执行器统一上报，避免重复卡片）
        env.update(FEISHU_HUB_URL=self.client.url, FEISHU_HUB_TASK_ID=task["task_id"],
                   FEISHU_HUB_LEASE_ID=task["lease_id"], FEISHU_HUB_CWD=task["cwd"])
        return env

    def run_task(self, task):
        """[执行] 单个任务：校验目录 → 启动 → 心跳 → 解析结果 → 上报终态事件。"""
        rep = TaskReporter(self.client, task, self.heartbeat_sec)
        proc = {"p": None}
        rep.on_lost = lambda: kill_tree(proc["p"])
        try:
            real = resolve_cwd(task["cwd"])
            if not real:
                rep.send("failed", {"code": "CWD_MISSING", "message": task["cwd"], "retryable": False})
                return
            prompt = task["prompt"] or ""
            if task.get("resume_hint"):
                prompt = "（%s）\n\n%s" % (task["resume_hint"], prompt)
            run_dir = os.path.join(HUB_HOME, "runs")
            os.makedirs(run_dir, exist_ok=True)
            out_path = os.path.join(run_dir, "%s-%s.out" % (task["task_id"], task["attempt"]))
            err_path = out_path[:-4] + ".err"
            with open(out_path, "wb") as out, open(err_path, "wb") as err:
                try:
                    p = subprocess.Popen(self.build_cmd(task), cwd=real, env=self.build_env(task),
                                         stdin=subprocess.PIPE, stdout=out, stderr=err, creationflags=NO_WINDOW)
                except OSError as e:
                    rep.send("failed", {"code": "CLI_NOT_FOUND", "message": str(e), "retryable": False})
                    return
                proc["p"] = p
                rep.send("started", {"delivery": "process", "pid": p.pid, "pid_ctime": _proc_ctime(p.pid)})
                rep.start_heartbeat()
                p.stdin.write(prompt.encode("utf-8"))  # prompt 走 stdin，避免以 "-" 开头被当成参数
                p.stdin.close()
                try:
                    rc = p.wait(timeout=int((task.get("limits") or {}).get("timeout_sec", 1800)))
                except subprocess.TimeoutExpired:
                    kill_tree(p)
                    rep.send("interrupted", {"reason": "执行超时"})
                    return
            if rep.lost.is_set():
                return
            self._report_exit(rep, task, rc, out_path, err_path)
        except LeaseLost:
            kill_tree(proc["p"])
        except Exception as e:  # noqa: BLE001
            LOG.exception("[Claude执行器] 任务异常 %s", task["task_id"])
            kill_tree(proc["p"])  # 先结束子进程树，再交给用户决定
            try:
                if proc["p"] is None:
                    rep.send("failed", {"code": "EXEC_ERROR", "message": type(e).__name__, "retryable": False})
                else:
                    rep.send("interrupted", {"reason": "执行器异常 %s" % type(e).__name__})
            except HubError:
                pass
        finally:
            rep.finish()

    def _report_exit(self, rep, task, rc, out_path, err_path):
        with open(out_path, "rb") as f:
            raw = f.read().decode("utf-8", "replace").strip()
        with open(err_path, "rb") as f:
            err = f.read().decode("utf-8", "replace")
        res = None
        for line in reversed(raw.splitlines()):  # 取最后一个 result 对象
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and obj.get("type") == "result":
                res = obj
                break
        if res and not res.get("is_error"):
            sid = res.get("session_id") or task.get("session_id") or ""
            if sid and sid != task.get("session_id"):
                rep.send("session", {"session_id": sid})
            rep.send("result", {"text": res.get("result") or "", "session_id": sid})
            return
        detail = ((res or {}).get("result") or err or raw)[-800:]
        if rc == 0 and res is None:
            rep.send("failed", {"code": "NO_RESULT", "message": "进程正常退出但没有结果输出 %s" % detail[-300:],
                                "retryable": False})
            return
        code = "SESSION_NOT_FOUND" if "no conversation found" in (err + raw).lower() else \
            "AUTH_REQUIRED" if ("login" in err.lower() or "401" in err) else "EXEC_ERROR"
        rep.send("failed", {"code": code, "message": "rc=%s %s" % (rc, detail), "retryable": False})

    def ensure_hooks(self):
        """[守护] 桌面 Hook 丢失时补回 ~/.claude/settings.json（保留其他字段）。"""
        path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
        py = sys.executable.replace("pythonw.exe", "python.exe")
        want = {"Stop": ("hook_stop.py", 20), "UserPromptSubmit": ("hook_prompt.py", 10)}
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            hooks, changed = data.setdefault("hooks", {}), False
            for event, (script, timeout) in want.items():
                groups = hooks.setdefault(event, [])
                if not any(script in h.get("command", "") and "feishu-hub" in h.get("command", "")
                           for g in groups for h in g.get("hooks", [])):
                    groups.append({"hooks": [{"type": "command", "timeout": timeout,
                                              "command": '"%s" "%s"' % (py, os.path.join(HERE, script))}]})
                    changed = True
            if changed:
                tmp = path + ".hub.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
                LOG.warning("[守护] 已补回 Claude 桌面 Hook")
        except Exception:  # noqa: BLE001
            LOG.exception("[守护] 检查 Claude Hook 失败")

    def serve_forever(self, stop=None):
        stop = stop or threading.Event()
        info = self.client.hello({"new_session": True, "resume": True, "desktop_queue": False}, VERSION)
        self.heartbeat_sec = int(info.get("heartbeat_sec", 30))
        LOG.info("[Claude执行器] 已上线 instance=%s", self.client.instance_id)
        last_guard = 0
        while not stop.is_set():
            if time.time() - last_guard > 60:
                last_guard = time.time()
                if self.cfg.get("manage_hooks"):
                    self.ensure_hooks()
                try:
                    flush_spool({"claude": self.client})
                except Exception:  # noqa: BLE001
                    LOG.exception("[Claude执行器] 补发离线上报失败")
            self.slots.acquire()
            try:
                task = self.client.claim(int(info.get("poll_wait_sec", 25)))
            except HubError as e:
                self.slots.release()
                LOG.warning("[Claude执行器] 领取失败 %s，稍后重试", e)
                stop.wait(5)
                if e.http == 0:
                    try:
                        self.client.hello({"new_session": True, "resume": True, "desktop_queue": False}, VERSION)
                    except HubError:
                        pass
                continue
            if not task:
                self.slots.release()
                continue
            LOG.info("[Claude执行器] 领取 %s mode=%s cwd=%s cli=%s model=%s effort=%s", task["task_id"], task["mode"],
                     task["cwd"], self.claude_exe(), self.cfg.get("model") or "-", self.cfg.get("effort") or "-")

            def _run(t=task):
                try:
                    self.run_task(t)
                finally:
                    self.slots.release()
            threading.Thread(target=_run, daemon=True).start()


def main():
    os.makedirs(HUB_HOME, exist_ok=True)
    logging.basicConfig(filename=os.path.join(HUB_HOME, "executor_claude.log"), encoding="utf-8",
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ClaudeExecutor(load_cfg()).serve_forever()


if __name__ == "__main__":
    main()
