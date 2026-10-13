# -*- coding: utf-8 -*-
"""[Qoder执行器] 按 PROTOCOL.md v1 从中间服务领任务，用 Qoder CLI 在已确认目录中执行并上报结果。

只与中间服务通信，不直接连飞书，不与其他执行器通信。
用法：python executors/qoder/executor.py        （在 feishu-hub 目录下）
      python executors/qoder/executor.py --check   # 只探测 CLI 与配置，不领任务

Qoder CLI 与 Claude Code 同源（钩子事件名、载荷字段、转录格式一致），所以默认参数模板按
`-p --output-format json` 形式给出；CLI 未安装时按协议上报 CLI_NOT_FOUND，不影响其它执行器。
"""
import argparse
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
CFG_PATH = os.path.join(HUB_HOME, "executor_qoder.json")
DEFAULTS = {
    # auto：QODER_CLI_BIN → PATH 上的 qoderclicn/qodercn → IDE 目录内的 CLI；找不到即按 CLI_NOT_FOUND 处理
    "qoder_exe": "auto",
    "model": "",                     # 留空沿用 CLI 默认（Qoder 端不由执行器指定模型）
    # CLI 实测可选值：default | accept_edits | bypass_permissions | dont_ask | auto（camelCase 会被拒）
    "permission_mode": "bypass_permissions",
    # 登录后用 `qoderclicn --list-models` 取值填入，实现按档位选模型/推理强度
    "model_by_tier": {},
    "effort_by_tier": {},
    "max_parallel": 2,
    # 独立配置目录：置值可让 headless 跑用自己的登录态与项目记录；留空则沿用 ~/.qoder-cn
    "config_dir": "",
    "args_new": ["-p", "--output-format", "json"],
    "args_resume": ["--resume", "{session_id}"],
    "cwd_from_hub_home": True,       # 飞书里的目录名按本机真实路径校验
}
LOG = logging.getLogger("qoder-executor")


def load_cfg():
    cfg = dict(DEFAULTS)
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH, "r", encoding="utf-8-sig") as f:
            cfg.update(json.load(f))
    return cfg


def find_cli():
    """定位 Qoder CLI：显式环境变量优先，其次 PATH，最后已知的安装位置（不递归扫描磁盘）。"""
    env = os.environ.get("QODER_CLI_BIN")
    if env and os.path.isfile(env):
        return env
    candidates = []
    home = os.environ.get("USERPROFILE", "")
    # 官方 dispatcher 的查找位置就是 ~/.qoder-cn/bin/qoderclicn/qoderclicn.exe
    for name in ("qoderclicn.exe", "qodercn.exe", "qodercli.exe"):
        candidates += [os.path.join(home, ".qoder-cn", "bin", name),
                       os.path.join(home, ".qoder-cn", "bin", "qoderclicn", name),
                       os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", name)]
    for base in ("D:\\software\\Qoder CN", os.path.join(os.environ.get("PROGRAMFILES", ""), "Qoder CN")):
        for rel in (os.path.join("resources", "bin", "qoderclicn.exe"), "qoderclicn.exe"):
            candidates.append(os.path.join(base, rel))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    for name in ("qoderclicn", "qodercn"):
        found = subprocess.run(["where.exe", name], capture_output=True, text=True).stdout.splitlines()
        if found and os.path.isfile(found[0].strip()):
            return found[0].strip()
    return None


def resolve_cwd(cwd):
    return cwd if cwd and os.path.isdir(cwd) else None


def kill_tree(p):
    if p and p.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=NO_WINDOW)


def _proc_ctime(pid):
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    try:
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
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


class QoderExecutor:
    def __init__(self, cfg, client=None):
        self.cfg = cfg
        self.client = client or HubClient("qoder")
        self.slots = threading.Semaphore(int(cfg["max_parallel"]))
        self.heartbeat_sec = 30

    def exe(self):
        exe = self.cfg.get("qoder_exe") or "auto"
        return find_cli() if exe == "auto" else exe

    def build_cmd(self, task):
        exe = self.exe()
        if not exe:
            return None
        cmd = [exe]
        if task["mode"] == "resume" and task.get("session_id"):
            cmd += [a.format(session_id=task["session_id"]) for a in self.cfg["args_resume"]]
        tier = (task.get("tier") or "").lower()
        model = (self.cfg.get("model_by_tier") or {}).get(tier) or self.cfg.get("model")
        if model:
            cmd += ["--model", model]
        effort = (self.cfg.get("effort_by_tier") or {}).get(tier)
        if effort:
            cmd += ["--reasoning-effort", effort]
        cmd += list(self.cfg["args_new"])
        if self.cfg.get("permission_mode"):
            cmd += ["--permission-mode", self.cfg["permission_mode"]]
        return cmd

    # 从 IDE/SDK 进程继承来的入口与环境变量会让 CLI 强制要求 stream-json，必须剔除
    ENV_DROP_PREFIX = ("QODER_AGENT_SDK", "QODER_SDK_", "QODER_WORKER_", "QODERCN_CLI",
                       "QODERCLI_", "QODER_MCP_LAZY", "QODER_PRODUCT_ID")

    def build_env(self, task):
        env = {k: v for k, v in os.environ.items()
               if not any(k.startswith(p) for p in self.ENV_DROP_PREFIX)}
        if self.cfg.get("config_dir"):
            env["QODERCN_CONFIG_DIR"] = self.cfg["config_dir"]
        # 结果由执行器统一上报，桌面 Hook 见到任务号就不重复发卡片（与 Claude 执行器同约定）
        env.update(FEISHU_HUB_URL=self.client.url, FEISHU_HUB_TASK_ID=task["task_id"],
                   FEISHU_HUB_LEASE_ID=task["lease_id"], FEISHU_HUB_CWD=task["cwd"])
        return env

    def run_task(self, task):
        rep = TaskReporter(self.client, task, self.heartbeat_sec)
        proc = {"p": None}
        rep.on_lost = lambda: kill_tree(proc["p"])
        try:
            real = resolve_cwd(task["cwd"])
            if not real:
                rep.send("failed", {"code": "CWD_MISSING", "message": task["cwd"], "retryable": False})
                return
            cmd = self.build_cmd(task)
            if not cmd:
                rep.send("failed", {"code": "CLI_NOT_FOUND",
                                    "message": "未找到 Qoder CLI（装 CLI 或设 QODER_CLI_BIN 后重试）",
                                    "retryable": False})
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
                    p = subprocess.Popen(cmd, cwd=real, env=self.build_env(task), stdin=subprocess.PIPE,
                                         stdout=out, stderr=err, creationflags=NO_WINDOW)
                except OSError as e:
                    rep.send("failed", {"code": "CLI_NOT_FOUND", "message": str(e), "retryable": False})
                    return
                proc["p"] = p
                rep.send("started", {"delivery": "process", "pid": p.pid, "pid_ctime": _proc_ctime(p.pid)})
                rep.start_heartbeat()
                p.stdin.write(prompt.encode("utf-8"))
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
            LOG.exception("[Qoder执行器] 任务异常 %s", task["task_id"])
            kill_tree(proc["p"])
            try:
                rep.send("failed" if proc["p"] is None else "interrupted",
                         {"reason": "执行器异常 %s: %s" % (type(e).__name__, e)} if proc["p"] is None else
                         {"reason": "执行器异常 %s" % type(e).__name__})
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
        for line in reversed(raw.splitlines()):
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
        merged = (err + raw).lower()   # CLI 也可能把登录/会话错误写到 stdout 的结果里
        code = "SESSION_NOT_FOUND" if "no conversation found" in merged else \
            "AUTH_REQUIRED" if ("login" in merged or "unauthor" in merged or "401" in merged) else "EXEC_ERROR"
        if rc == 0 and res is None:
            code = "NO_RESULT"
        rep.send("failed", {"code": code, "message": "rc=%s %s" % (rc, detail), "retryable": False})

    def serve_forever(self, stop=None):
        stop = stop or threading.Event()
        info = self.client.hello({"new_session": True, "resume": True, "desktop_queue": False}, VERSION)
        self.heartbeat_sec = int(info.get("heartbeat_sec", 30))
        LOG.info("[Qoder执行器] 已上线 instance=%s cli=%s", self.client.instance_id, self.exe() or "未找到")
        last_guard = 0
        while not stop.is_set():
            if time.time() - last_guard > 60:
                last_guard = time.time()
                try:
                    flush_spool({"qoder": self.client})
                except Exception:  # noqa: BLE001
                    LOG.exception("[Qoder执行器] 补发离线上报失败")
            self.slots.acquire()
            try:
                task = self.client.claim(int(info.get("poll_wait_sec", 25)))
            except HubError as e:
                self.slots.release()
                LOG.warning("[Qoder执行器] 领取失败 %s，稍后重试", e)
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
            LOG.info("[Qoder执行器] 领取 %s mode=%s cwd=%s cli=%s", task["task_id"], task["mode"], task["cwd"],
                     self.exe() or "-")

            def _run(t=task):
                try:
                    self.run_task(t)
                finally:
                    self.slots.release()
            threading.Thread(target=_run, daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只探测 CLI 与配置并打印结果")
    args = ap.parse_args()
    cfg = load_cfg()
    if args.check:
        print(json.dumps({"cli": find_cli(), "cfg_path": CFG_PATH, "hub_url": os.environ.get("FEISHU_HUB_URL", "默认"),
                          "model": cfg.get("model") or "-", "permission_mode": cfg.get("permission_mode"),
                          "结论": "OK" if find_cli() else "CLI_NOT_FOUND（装 Qoder CLI 或设 QODER_CLI_BIN）"},
                         ensure_ascii=False, indent=1))
        return 0
    os.makedirs(HUB_HOME, exist_ok=True)
    logging.basicConfig(filename=os.path.join(HUB_HOME, "executor_qoder.log"), encoding="utf-8",
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    QoderExecutor(cfg).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
