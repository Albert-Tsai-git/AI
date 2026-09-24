# -*- coding: utf-8 -*-
"""[协议客户端] 执行器与桌面 Hook 调用中间服务的通用客户端（PROTOCOL.md v1），仅依赖标准库。
Codex 执行器可直接复用本文件。"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid

HUB_HOME = os.environ.get("FEISHU_HUB_HOME") or os.path.join(os.path.expanduser("~"), ".feishu_hub")
DEFAULT_URL = os.environ.get("FEISHU_HUB_URL") or "http://127.0.0.1:8765"
SPOOL_DIR = os.path.join(HUB_HOME, "spool")


class HubError(Exception):
    def __init__(self, http, code, message=""):
        super().__init__("%s %s %s" % (http, code, message))
        self.http, self.code, self.message = http, code, message


class LeaseLost(HubError):
    """409 LEASE_LOST：执行器必须立即停止该任务。"""


class AlreadyFinal(LeaseLost):
    """409 ALREADY_FINAL：本租约的终态事件已被接受（例如响应丢失后重试），视为成功。"""


def load_token(path=None):
    if os.environ.get("FEISHU_HUB_TOKEN"):
        return os.environ["FEISHU_HUB_TOKEN"]
    path = path or os.environ.get("FEISHU_HUB_TOKEN_FILE") or os.path.join(HUB_HOME, "token")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


class HubClient:
    def __init__(self, executor, url=None, token=None, instance_id=None, timeout=70):
        self.executor = executor
        self.url = (url or DEFAULT_URL).rstrip("/")
        self.token = token or load_token()
        self.instance_id = instance_id or str(uuid.uuid4())
        self.timeout = timeout

    # ---------- 底层 ----------
    def request(self, method, path, body=None, retry=True):
        """发送请求；5xx/网络错误指数退避重试（1s→30s，最多约 5 分钟），4xx 直接抛出。返回 (http, json|None)。"""
        delay, deadline = 1.0, time.time() + 300
        while True:
            data = None
            if body is not None:
                body = dict(body, protocol=1)
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(self.url + path, data=data, method=method, headers={
                "Authorization": "Bearer " + self.token, "Content-Type": "application/json; charset=utf-8"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = r.read()
                    return r.status, (json.loads(raw.decode("utf-8")) if raw else None)
            except urllib.error.HTTPError as e:
                try:
                    err = json.loads(e.read().decode("utf-8")).get("error") or {}
                except ValueError:
                    err = {}
                code = err.get("code") or "HTTP_%s" % e.code
                if e.code == 409:
                    raise (AlreadyFinal if code == "ALREADY_FINAL" else LeaseLost)(e.code, code, err.get("message", ""))
                if e.code < 500 or not retry or time.time() > deadline:
                    raise HubError(e.code, code, err.get("message", ""))
            except (urllib.error.URLError, OSError) as e:
                if not retry or time.time() > deadline:
                    raise HubError(0, "UNREACHABLE", str(e))
            time.sleep(delay)
            delay = min(delay * 2, 30)

    # ---------- 执行器接口 ----------
    def hello(self, capabilities, version="0.1.0"):
        return self.request("POST", "/v1/executors/hello", {"executor": self.executor, "instance_id": self.instance_id,
                                                            "version": version, "capabilities": capabilities})[1]

    def claim(self, wait_sec=25):
        code, data = self.request("POST", "/v1/tasks/claim", {"executor": self.executor,
                                                              "instance_id": self.instance_id, "wait_sec": wait_sec})
        return data["task"] if code == 200 and data else None

    def release(self, task, code, retry_after_sec=15):
        return self.request("POST", "/v1/tasks/%s/release" % task["task_id"],
                            {"lease_id": task["lease_id"], "code": code, "retry_after_sec": retry_after_sec})[1]

    # ---------- Hook 接口 ----------
    def session_turn(self, session_id, cwd, text, turn_id=None, items=None):
        body = {"executor": self.executor, "session_id": session_id, "cwd": cwd, "text": text}
        if turn_id:
            body["turn_id"] = turn_id
        if items:
            body["items"] = items
        return self.request("POST", "/v1/sessions/turns", body)[1]

    def inbox(self, session_id):
        return self.request("GET", "/v1/sessions/%s/%s/inbox" % (self.executor, session_id), retry=False)[1]

    def inbox_ack(self, session_id, refs):
        return self.request("POST", "/v1/sessions/%s/%s/inbox/ack" % (self.executor, session_id),
                            {"turn_refs": refs}, retry=False)[1]


class TaskReporter:
    """单个租约内的事件上报：seq 自增、重试安全；后台心跳；租约丢失时回调 on_lost。"""

    def __init__(self, client, task, heartbeat_sec=30, on_lost=None):
        self.client, self.task = client, task
        self.seq = 0
        self.lost = threading.Event()
        self.done = threading.Event()
        self._lock = threading.Lock()
        self.heartbeat_sec = heartbeat_sec
        self.on_lost = on_lost

    def send(self, etype, data=None):
        with self._lock:
            if self.lost.is_set():
                raise LeaseLost(409, "LEASE_LOST")
            self.seq += 1
            seq = self.seq
        try:
            return self.client.request("POST", "/v1/tasks/%s/events" % self.task["task_id"],
                                       {"lease_id": self.task["lease_id"], "seq": seq, "type": etype,
                                        "data": data or {}})[1]
        except AlreadyFinal:
            if etype in ("result", "failed", "interrupted"):
                return {"ok": True, "already_final": True}  # 终态已被接受（响应丢失后的重试）
            self.lost.set()
            raise
        except LeaseLost:
            self.lost.set()
            if self.on_lost:
                self.on_lost()
            raise

    def start_heartbeat(self):
        def loop():
            while not self.done.wait(self.heartbeat_sec):
                try:
                    self.send("heartbeat")
                except LeaseLost:
                    return
                except HubError:
                    pass  # 中间服务暂不可达：下次再试；租约过期由中间服务判定
        threading.Thread(target=loop, daemon=True).start()

    def finish(self):
        self.done.set()


def spool(kind, payload):
    """[离线] Hook 上报失败时落盘，执行器上线后补发，保证不丢。"""
    os.makedirs(SPOOL_DIR, exist_ok=True)
    name = "%d-%s-%s.json" % (int(time.time() * 1000), kind, uuid.uuid4().hex[:6])
    with open(os.path.join(SPOOL_DIR, name), "w", encoding="utf-8") as f:
        json.dump({"kind": kind, "payload": payload}, f, ensure_ascii=False)


def flush_spool(clients):
    """补发落盘的 Hook 上报；clients 为 {executor: HubClient}。"""
    if not os.path.isdir(SPOOL_DIR):
        return 0
    n = 0
    for name in sorted(os.listdir(SPOOL_DIR)):
        path = os.path.join(SPOOL_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                item = json.load(f)
            p = item["payload"]
            cli = clients.get(p.get("executor"))
            if not cli or item["kind"] != "turn":
                continue
            cli.session_turn(p["session_id"], p.get("cwd", ""), p.get("text", ""), p.get("turn_id"), p.get("items"))
            os.remove(path)
            n += 1
        except HubError as e:
            if e.http == 0 or e.http >= 500:
                break  # 中间服务不可达，稍后再试
            os.remove(path)  # 4xx：数据本身有问题，丢弃避免卡住队列
        except (OSError, ValueError, KeyError):
            continue
    return n
