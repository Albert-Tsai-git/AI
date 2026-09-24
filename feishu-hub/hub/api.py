# -*- coding: utf-8 -*-
"""[接口] 执行器协议的 HTTP 入口（标准库 ThreadingHTTPServer，不引入新依赖）。只监听 127.0.0.1，令牌鉴权。"""
import hmac
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hub import config, service

log = config.get_logger("hub")
ROUTES = [
    ("POST", re.compile(r"^/v1/executors/hello$"), lambda m, b: service.hello(b)),
    ("POST", re.compile(r"^/v1/tasks/claim$"), lambda m, b: service.claim(b)),
    ("POST", re.compile(r"^/v1/tasks/([^/]+)/events$"), lambda m, b: service.event(m.group(1), b)),
    ("POST", re.compile(r"^/v1/tasks/([^/]+)/release$"), lambda m, b: service.release(m.group(1), b)),
    ("POST", re.compile(r"^/v1/sessions/turns$"), lambda m, b: service.session_turn(b)),
    ("GET", re.compile(r"^/v1/sessions/([^/]+)/([^/]+)/inbox$"), lambda m, b: service.inbox_get(m.group(1), m.group(2))),
    ("POST", re.compile(r"^/v1/sessions/([^/]+)/([^/]+)/inbox/ack$"),
     lambda m, b: service.inbox_ack(m.group(1), m.group(2), b)),
]


def make_handler(token):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # 不写 stderr；协议日志由 service 记录
            pass

        def _reply(self, code, obj=None):
            data = b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if data:
                self.wfile.write(data)

        def _err(self, http, code, message=""):
            self._reply(http, {"ok": False, "error": {"code": code, "message": message or code}})

        def _dispatch(self, method):
            path = self.path.split("?", 1)[0]
            if method == "GET" and path == "/v1/health":
                return self._reply(200, {"ok": True})
            auth = self.headers.get("Authorization", "")
            if not hmac.compare_digest(auth.encode(), ("Bearer " + token).encode()):
                return self._err(401, "UNAUTHORIZED")
            body = {}
            if method == "POST":
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 1024 * 1024:
                        return self._err(413, "BAD_REQUEST", "请求体超过 1MB")
                    body = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
                except ValueError:
                    return self._err(400, "BAD_REQUEST", "JSON 解析失败")
                if body.get("protocol", 1) != 1:
                    return self._err(426, "PROTOCOL_UNSUPPORTED")
            for mth, rx, fn in ROUTES:
                m = rx.match(path)
                if mth == method and m:
                    try:
                        res = fn(m, body)
                    except service.ProtoError as e:
                        return self._err(e.http, e.code, e.message)
                    except Exception:  # noqa: BLE001
                        log.exception("[接口] 处理失败 %s %s", method, path)
                        return self._err(500, "HUB_ERROR")
                    return self._reply(204) if res is None else self._reply(200, res)
            return self._err(404, "NOT_FOUND")

        def do_GET(self):  # noqa: N802
            self._dispatch("GET")

        def do_POST(self):  # noqa: N802
            self._dispatch("POST")

    return Handler


def serve(host, port, token):
    srv = ThreadingHTTPServer((host, port), make_handler(token))
    srv.daemon_threads = True
    log.info("[接口] 监听 http://%s:%s", host, port)
    return srv
