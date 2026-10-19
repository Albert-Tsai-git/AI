# -*- coding: utf-8 -*-
"""
SIRE 本机通讯：Claude / Codex / Qoder / User 之间的消息、进度与资源锁。

脚本在共享 skill（Git）里，数据在 sire_paths.comms_dir()（默认 D:/sire/sire_comms），
按项目分区：<comms>/projects/<项目标识>/，不进 Git，也不落在业务项目里。
项目默认取当前目录所在的 Git 根目录（没有 Git 时取当前目录），可用 --project 指定路径或标识。

消息：
  sire_comms.py send   --me Claude --to Codex --type request "内容" [--re 12]
  sire_comms.py reply  --me Codex --re 12 "内容"            回复给原发件人
  sire_comms.py inbox  --me Claude [--all-projects]         未读 + 我发出仍待回复的 request/question
  sire_comms.py ack    --me Claude 12 13 | all
  sire_comms.py log    [-n 20]
进度：
  sire_comms.py status --me Claude --text "当前任务 | 进度 | 下一步"
  sire_comms.py status                                     查看各方进度与锁
资源锁（约定，不强制）：
  sire_comms.py lock   --me Claude --resource db --purpose "跑集成测试"
  sire_comms.py unlock --me Claude --resource db
  sire_comms.py locks
项目：
  sire_comms.py projects                                    各项目消息数与各方未读数
会话绑定（按项目，把身份固定到用户指定的对话）：
  sire_comms.py --session <会话id> bind --me Claude [--rebind]  绑定；已绑其他会话时须 --rebind（仅用户要求时）
  sire_comms.py bind                                        查看本项目绑定
  身份已绑定后，以该身份收发、确认、轮询、读信箱、上报、加解锁必须带 --session <会话id>
  （或环境变量 SIRE_SESSION）且与绑定一致，否则拒绝，避免同名的其他会话串话。

--me 可省略，改用环境变量 SIRE_AGENT。类型：info / request / question / reply / handoff。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sire_paths import comms_dir  # noqa: E402
from sire_process import no_console_kwargs  # noqa: E402

AGENTS = ("Claude", "Codex", "Qoder", "User")
TYPES = ("info", "request", "question", "reply", "handoff")
NEEDS_REPLY = ("request", "question")
RESOURCE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
STALE_GUARD_SECONDS = 10
MAX_TEXT = 8000
LOCK_TTL_HOURS = 2.0  # 资源锁超过该时长标记 STALE；环境变量 SIRE_COMMS_LOCK_TTL_HOURS 或 --ttl 覆盖
SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,127}$")


class CommsError(Exception):
    """用户可读的错误，命令行以退出码 2 结束"""


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def agent(name: str | None) -> str:
    name = name or os.environ.get("SIRE_AGENT")
    if not name:
        raise CommsError("缺少身份：请用 --me 指定，或设置环境变量 SIRE_AGENT")
    for a in AGENTS:
        if a.lower() == name.strip().lower():
            return a
    raise CommsError(f"未知身份 {name}，可选：{'/'.join(AGENTS)}")


# ---------------- 项目定位 ----------------

def slugify(path: Path) -> str:
    """D:\\code\\mes → d--code-mes；与路径一一对应，便于人工辨认"""
    s = str(path.resolve()).replace(":", "-").replace("\\", "-").replace("/", "-").strip("-").lower()
    s = re.sub(r"[^a-z0-9._-]+", "_", s)
    return s[:100] or "root"


def git_root(cwd: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd), capture_output=True, text=True, timeout=5, **no_console_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def resolve_project(spec: str | None, cwd: Path | None = None) -> tuple[str, Path | None]:
    """返回 (项目标识, 项目路径)。spec 可为已有标识或目录路径"""
    root = comms_dir() / "projects"
    if spec:
        if SLUG_RE.match(spec) and (root / spec).is_dir():
            meta = root / spec / "project.json"
            path = Path(json.loads(meta.read_text(encoding="utf-8"))["path"]) if meta.exists() else None
            return spec, path
        p = Path(spec).expanduser()
        if not p.is_dir():
            raise CommsError(f"项目不存在：{spec}（可用 projects 查看已有项目标识）")
        return slugify(p), p.resolve()
    here = (cwd or Path.cwd()).resolve()
    p = git_root(here) or here
    return slugify(p), p.resolve()


class Channel:
    """单个项目的通讯目录"""

    def __init__(self, slug: str, path: Path | None):
        self.slug = slug
        self.dir = comms_dir() / "projects" / slug
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "locks").mkdir(exist_ok=True)
        meta = self.dir / "project.json"
        if path and not meta.exists():
            meta.write_text(json.dumps({"path": str(path), "created": now()}, ensure_ascii=False), encoding="utf-8")
        self.log = self.dir / "messages.jsonl"

    # ---- 会话绑定 ----
    def bindings(self) -> dict:
        p = self.dir / "bindings.json"
        if not p.exists():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not all(isinstance(d, dict) and d.get("session") for d in data.values()):
                raise ValueError
            return data
        except (ValueError, AttributeError):
            raise CommsError(f"绑定文件损坏，请检查 {p}") from None

    def bind(self, me: str, session: str, rebind: bool = False) -> dict:
        """把身份绑定到指定会话；已绑定其他会话时须显式 rebind"""
        if not session or not SESSION_RE.match(session):
            raise CommsError("会话 id 无效：需为 4–128 位字母、数字或 . _ : -")
        fd, guard = self._guard()
        try:
            data = self.bindings()
            old = data.get(me)
            if old and old["session"] != session and not rebind:
                raise CommsError(f"{me} 已绑定会话 {old['session']}；仅在用户要求切换时加 --rebind")
            data[me] = {"session": session, "time": now()}
            if old and old["session"] != session:
                data[me]["previous"] = old["session"]
            temporary = self.dir / "bindings.tmp"
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            temporary.replace(self.dir / "bindings.json")
            return data[me]
        finally:
            os.close(fd)
            guard.unlink(missing_ok=True)

    def check(self, me: str, session: str | None) -> None:
        """身份已绑定时，只允许绑定会话以该身份通讯"""
        bound = self.bindings().get(me)
        if not bound:
            return
        if not session:
            raise CommsError(f"{me} 在项目 {self.slug} 已绑定会话 {bound['session']}，请带 --session（或 SIRE_SESSION）")
        if session != bound["session"]:
            raise CommsError(f"{me} 在项目 {self.slug} 已绑定会话 {bound['session']}，当前会话 {session} 无权以 {me} 身份通讯；切换须用户要求后 bind --rebind")

    # ---- 消息 ----
    def load(self) -> list[dict]:
        if not self.log.exists():
            return []
        out = []
        with self.log.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    # 半行写入（进程被杀）不影响其余消息
                    continue
        return out

    def _guard(self):
        guard = self.dir / ".send.lock"
        for _ in range(200):
            try:
                return os.open(guard, os.O_CREAT | os.O_EXCL), guard
            except FileExistsError:
                try:
                    if time.time() - guard.stat().st_mtime > STALE_GUARD_SECONDS:
                        guard.unlink(missing_ok=True)  # 发送方异常退出留下的陈旧锁
                        continue
                except FileNotFoundError:
                    continue
                time.sleep(0.05)
        raise CommsError(f"发送锁被占用，确认无人发送后可删除 {guard}")

    def send(self, me: str, to: str, typ: str, text: str, re_id: int | None = None) -> dict:
        if typ not in TYPES:
            raise CommsError(f"未知类型 {typ}，可选：{'/'.join(TYPES)}")
        if me == to:
            raise CommsError("不能给自己发消息")
        text = text.strip()
        if not text:
            raise CommsError("消息内容不能为空")
        if len(text) > MAX_TEXT:
            raise CommsError(f"消息过长（>{MAX_TEXT} 字），请改为写文件并在消息里给出路径")
        fd, guard = self._guard()
        try:
            msgs = self.load()
            if re_id is not None and not any(m["id"] == re_id for m in msgs):
                raise CommsError(f"要回复的消息 #{re_id} 不存在")
            m = {"id": (msgs[-1]["id"] + 1) if msgs else 1, "time": now(), "from": me, "to": to, "type": typ, "text": text}
            if re_id is not None:
                m["re"] = re_id
            # 记录双方绑定会话，便于在各自对话中对照
            binds = self.bindings()
            for key, who in (("from_session", me), ("to_session", to)):
                if who in binds:
                    m[key] = binds[who]["session"]
            with self.log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        finally:
            os.close(fd)
            guard.unlink(missing_ok=True)
        return m

    def reply(self, me: str, re_id: int, text: str) -> dict:
        orig = next((m for m in self.load() if m["id"] == re_id), None)
        if not orig:
            raise CommsError(f"要回复的消息 #{re_id} 不存在")
        to = orig["from"] if orig["from"] != me else orig["to"]
        return self.send(me, to, "reply", text, re_id)

    def read_set(self, me: str) -> set[int]:
        p = self.dir / f"read_{me}.json"
        return set(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else set()

    def ack(self, me: str, ids: list[str]) -> int:
        seen = self.read_set(me)
        before = len(seen)
        mine = {m["id"] for m in self.load() if m["to"] == me}
        if ids == ["all"]:
            seen |= mine
        else:
            for i in ids:
                n = int(str(i).lstrip("#"))
                if n not in mine:
                    raise CommsError(f"#{n} 不是发给 {me} 的消息")
                seen.add(n)
        (self.dir / f"read_{me}.json").write_text(json.dumps(sorted(seen)), encoding="utf-8")
        return len(seen) - before

    def unread(self, me: str) -> list[dict]:
        seen = self.read_set(me)
        return [m for m in self.load() if m["to"] == me and m["id"] not in seen]

    def waiting(self, me: str) -> list[dict]:
        msgs = self.load()
        replied = {m["re"] for m in msgs if m.get("re")}
        return [m for m in msgs if m["from"] == me and m["type"] in NEEDS_REPLY and m["id"] not in replied]

    def session(self, me: str, action: str, peer: str, auto_stop: bool = False) -> dict:
        """持久化按需监听状态；不自动发送、确认消息或启动客户端。"""
        if me == peer:
            raise CommsError("通讯对象不能是自己")
        fd, guard = self._guard()
        try:
            state_path = self.dir / f"session_{me}.json"
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
                "active": False, "empty_checks": 0, "seen_ids": [], "peer": peer, "persistent": True,
            }
            messages = []
            if action == "start":
                # 默认常驻：只有 session stop（用户说结束协作）才停止；--auto-stop 恢复连续空闲5次自停
                state = {"active": True, "empty_checks": 0, "seen_ids": [], "peer": peer, "persistent": not auto_stop}
            elif action == "stop":
                state["active"] = False
            elif action == "poll" and state["active"]:
                seen = set(state["seen_ids"])
                messages = [m for m in self.unread(me)
                            if m["from"] == state["peer"] and m["id"] not in seen]
                state["empty_checks"] = 0 if messages else state["empty_checks"] + 1
                state["seen_ids"] = sorted(seen | {m["id"] for m in messages})
                if state["empty_checks"] >= 5 and not state.get("persistent", False):
                    state["active"] = False
            if action != "status":
                state["updated"] = now()
                temporary = state_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
                temporary.replace(state_path)
            return {**state, "messages": messages, "project": self.slug}
        finally:
            os.close(fd)
            guard.unlink(missing_ok=True)

    def wait(self, me: str, peer: str, timeout: float, interval: float) -> dict:
        """阻塞等待对方新消息，整个等待过程在进程内完成、不消耗 AI 额度。
        常驻模式下仅在消息日志变化时才解析轮询；非常驻（--auto-stop）每个间隔都计一次空闲。
        返回：有新消息 / 会话已停止 / 超时（timeout=True，messages 为空，调用方可继续等）。"""
        deadline = time.time() + timeout
        last_sig = None
        while True:
            try:
                stat = self.log.stat()
                sig = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                sig = None
            state = self.session(me, "status", peer) if last_sig is not None else None
            persistent = state.get("persistent", False) if state else True
            if last_sig is None or sig != last_sig or not persistent:
                last_sig = sig
                r = self.session(me, "poll", peer)
                if r["messages"] or not r["active"]:
                    return r
            if time.time() >= deadline:
                return {**r, "timeout": True}
            time.sleep(min(interval, max(0.0, deadline - time.time())))

    # ---- 进度 ----
    def status_data(self) -> dict:
        p = self.dir / "status.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def set_status(self, me: str, text: str) -> None:
        data = self.status_data()
        data[me] = {"time": now(), "text": text.strip()}
        (self.dir / "status.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- 锁 ----
    def _lock_path(self, res: str) -> Path:
        if not RESOURCE_RE.match(res):
            raise CommsError("资源名需为小写字母开头的 1–32 位小写字母、数字、_、-")
        return self.dir / "locks" / f"{res}.lock"

    def lock(self, me: str, res: str, purpose: str) -> None:
        p = self._lock_path(res)
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise CommsError(f"{res} 已被占用：{p.read_text(encoding='utf-8')}") from None
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"holder": me, "purpose": purpose, "time": now()}, f, ensure_ascii=False)

    def unlock(self, me: str, res: str, stale: bool = False, ttl: float | None = None) -> None:
        p = self._lock_path(res)
        if not p.exists():
            raise CommsError(f"{res} 当前未被占用")
        try:
            info = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            info = {"holder": "?", "time": ""}
        holder = info["holder"]
        if holder != me and me != "User":
            if not stale:
                raise CommsError(f"{res} 由 {holder} 占用，不能代为释放（User 可强制释放；锁过期 STALE 时可加 --stale）")
            if not lock_is_stale(info, ttl):
                raise CommsError(f"{res} 由 {holder} 占用且未过期（{lock_age_text(info)}），不能用 --stale 释放")
        p.unlink()
        if holder != me and me != "User" and holder in AGENTS:
            # 非持有方释放过期锁，留审计消息给原持有方
            self.send(me, holder, "info", f"[审计] 资源 {res} 的锁已过期（持有 {lock_age_text(info)}，用途：{info.get('purpose', '')}），{me} 用 unlock --stale 释放。如仍在使用请重新加锁。")

    def locks(self) -> list[dict]:
        out = []
        for p in sorted((self.dir / "locks").glob("*.lock")):
            try:
                out.append({"resource": p.stem, **json.loads(p.read_text(encoding="utf-8"))})
            except (OSError, json.JSONDecodeError):
                out.append({"resource": p.stem, "holder": "?", "purpose": "锁文件损坏", "time": ""})
        return out


def all_channels() -> list[Channel]:
    root = comms_dir() / "projects"
    if not root.is_dir():
        return []
    return [Channel(d.name, None) for d in sorted(root.iterdir()) if d.is_dir()]


# ---------------- 输出 ----------------

def fmt(m: dict) -> str:
    re_part = f" re#{m['re']}" if m.get("re") else ""
    src = m["from"] + (f"({m['from_session'][:8]})" if m.get("from_session") else "")
    dst = m["to"] + (f"({m['to_session'][:8]})" if m.get("to_session") else "")
    return f"#{m['id']} [{m['time']}] {src}→{dst} {m['type']}{re_part}\n    " + m["text"].replace("\n", "\n    ")


def lock_age_seconds(info: dict) -> float | None:
    try:
        return (dt.datetime.now() - dt.datetime.strptime(info["time"], "%Y-%m-%d %H:%M:%S")).total_seconds()
    except (KeyError, ValueError, TypeError):
        return None


def lock_ttl_hours(ttl: float | None = None) -> float:
    if ttl is not None:
        return ttl
    try:
        return float(os.environ.get("SIRE_COMMS_LOCK_TTL_HOURS", LOCK_TTL_HOURS))
    except ValueError:
        return LOCK_TTL_HOURS


def lock_is_stale(info: dict, ttl: float | None = None) -> bool:
    age = lock_age_seconds(info)
    return age is None or age > lock_ttl_hours(ttl) * 3600  # 无法解析时间的损坏锁视为过期


def lock_age_text(info: dict) -> str:
    age = lock_age_seconds(info)
    if age is None:
        return "时长未知"
    minutes = int(age // 60)
    return f"已持有 {minutes // 60} 小时 {minutes % 60} 分" if minutes >= 60 else f"已持有 {minutes} 分"


def print_status(ch: Channel, ttl: float | None = None) -> None:
    data = ch.status_data()
    for a in AGENTS[:3]:
        d = data.get(a)
        print(f"[comms] {a}：" + (f"{d['text']}（{d['time']}）" if d else "未上报"))
    ls = ch.locks()
    if not ls:
        print("[comms] 锁：无")
    for l in ls:
        mark = f" [STALE 已超 {lock_ttl_hours(ttl):g} 小时，非持有方可 unlock --stale]" if lock_is_stale(l, ttl) else ""
        print(f"[comms] 锁 {l['resource']}：{l['holder']}（{l['purpose']}，{l['time']}，{lock_age_text(l)}）{mark}")


def print_inbox(ch: Channel, me: str, header: bool = True) -> int:
    unread = ch.unread(me)
    waiting = ch.waiting(me)
    if header:
        print(f"[comms] 项目 {ch.slug}")
    print(f"[comms] {me} 未读 {len(unread)} 条")
    for m in unread:
        print(fmt(m))
    if waiting:
        print(f"[comms] 等待对方回复 {len(waiting)} 条")
        for m in waiting:
            print(fmt(m))
    return len(unread)


# ---------------- 命令行 ----------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sire_comms.py", description="SIRE 本机通讯（消息 / 进度 / 资源锁）")
    ap.add_argument("--project", help="项目路径或标识；默认当前目录所在 Git 根目录")
    ap.add_argument("--session", help="当前会话 id；身份已绑定时必填，默认取环境变量 SIRE_SESSION")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bind", help="把身份绑定到会话 id；不带 --me 时查看绑定")
    b.add_argument("--me")
    b.add_argument("--rebind", action="store_true", help="替换已有绑定，仅在用户要求切换会话时使用")

    session = sub.add_parser("session", help="协作通讯：start 后常驻轮询，直到 stop（用户说结束协作）；加 --auto-stop 则连续5次无新消息自停")
    session.add_argument("action", choices=("start", "poll", "stop", "status", "wait"))
    session.add_argument("--me")
    session.add_argument("--peer", help="默认：Claude 对 Codex，其余身份对 Claude")
    session.add_argument("--timeout", type=float, default=1800, help="wait：最长阻塞秒数，超时返回 timeout=true")
    session.add_argument("--interval", type=float, default=5, help="wait：检查消息日志的间隔秒数")
    session.add_argument("--auto-stop", action="store_true", help="仅 start 有效：恢复连续5次无新消息自动停止")

    s = sub.add_parser("send")
    s.add_argument("--me")
    s.add_argument("--to", required=True)
    s.add_argument("--type", default="info")
    s.add_argument("--re", type=int)
    s.add_argument("text")

    r = sub.add_parser("reply")
    r.add_argument("--me")
    r.add_argument("--re", type=int, required=True)
    r.add_argument("text")

    i = sub.add_parser("inbox")
    i.add_argument("--me")
    i.add_argument("--all-projects", action="store_true")

    a = sub.add_parser("ack")
    a.add_argument("--me")
    a.add_argument("ids", nargs="+")

    lg = sub.add_parser("log")
    lg.add_argument("-n", type=int, default=20)

    st = sub.add_parser("status")
    st.add_argument("--me")
    st.add_argument("--text")

    lk = sub.add_parser("lock")
    lk.add_argument("--me")
    lk.add_argument("--resource", required=True)
    lk.add_argument("--purpose", required=True)

    ul = sub.add_parser("unlock")
    ul.add_argument("--me")
    ul.add_argument("--resource", required=True)
    ul.add_argument("--stale", action="store_true", help="释放已过期（STALE）的他人锁，并给原持有方留审计消息")
    ul.add_argument("--ttl", type=float, help="过期阈值（小时），默认2或 SIRE_COMMS_LOCK_TTL_HOURS")

    lks = sub.add_parser("locks")
    lks.add_argument("--ttl", type=float, help="过期阈值（小时）")
    sub.add_parser("projects")
    return ap


def run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    session = args.session or os.environ.get("SIRE_SESSION") or None
    if args.cmd == "projects":
        chans = all_channels()
        if not chans:
            print("[comms] 暂无项目")
        for ch in chans:
            meta = ch.dir / "project.json"
            path = json.loads(meta.read_text(encoding="utf-8"))["path"] if meta.exists() else "?"
            counts = "，".join(f"{a} 未读 {len(ch.unread(a))}" for a in AGENTS[:3])
            print(f"[comms] {ch.slug}  {path}  消息 {len(ch.load())} 条；{counts}")
        return 0
    if args.cmd == "inbox" and args.all_projects:
        me = agent(args.me)
        total = 0
        for ch in all_channels():
            bound = ch.bindings().get(me)
            if bound and bound["session"] != session:
                print(f"[comms] 跳过 {ch.slug}：{me} 已绑定会话 {bound['session']}" + ("，未提供 --session" if not session else "，与当前会话不符"))
                continue
            if ch.unread(me) or ch.waiting(me):
                total += print_inbox(ch, me)
        print(f"[comms] {me} 全部项目未读合计 {total} 条")
        return 0

    slug, path = resolve_project(args.project)
    ch = Channel(slug, path)
    if args.cmd == "bind":
        if not args.me:
            data = ch.bindings()
            print(f"[comms] 项目 {slug} 绑定：" + ("无" if not data else f"{len(data)} 个"))
            for who, d in data.items():
                print(f"[comms] {who} → {d['session']}（{d['time']}）")
            return 0
        if not session:
            raise CommsError("绑定需要 --session <会话id>")
        d = ch.bind(agent(args.me), session, args.rebind)
        print(f"[comms] 已绑定 {agent(args.me)} → {d['session']}（项目 {slug}）")
        return 0
    # 未绑定身份：带 --session 的写操作首次使用自动绑定；没带则警告（不阻断，兼容旧用法）
    writes = ("session", "send", "reply", "ack", "lock", "unlock") if args.cmd != "status" else (("status",) if args.text is not None else ())
    if args.cmd in writes:
        who = agent(args.me)
        if who not in ch.bindings():
            if session:
                ch.bind(who, session)
                print(f"[comms] 提示：{who} 在项目 {slug} 首次使用，已自动绑定会话 {session}", file=sys.stderr)
            else:
                print(f"[comms] ⚠⚠ 警告：{who} 在项目 {slug} 未绑定会话且未带 --session，任何同名会话都能冒用该身份。"
                      f"请用 --session <会话id> 重新执行（首次使用即自动绑定）。", file=sys.stderr)
    # 以某身份写入或读取其信箱时，会话必须与绑定一致
    if args.cmd in ("session", "send", "reply", "inbox", "ack", "lock", "unlock") or (args.cmd == "status" and args.text is not None):
        ch.check(agent(args.me), session)
    if args.cmd == "session" and args.action == "wait":
        peer = agent(args.peer or ("Codex" if agent(args.me) == "Claude" else "Claude"))
        print(json.dumps(ch.wait(agent(args.me), peer, args.timeout, args.interval), ensure_ascii=False))
    elif args.cmd == "session":
        print(json.dumps(ch.session(agent(args.me), args.action, agent(args.peer or ("Codex" if agent(args.me) == "Claude" else "Claude")), args.auto_stop), ensure_ascii=False))
    elif args.cmd == "send":
        m = ch.send(agent(args.me), agent(args.to), args.type, args.text, args.re)
        print(f"[comms] 已发送 #{m['id']}（项目 {slug}）")
    elif args.cmd == "reply":
        m = ch.reply(agent(args.me), args.re, args.text)
        print(f"[comms] 已回复 #{m['id']} → {m['to']}（re#{args.re}）")
    elif args.cmd == "inbox":
        print_inbox(ch, agent(args.me))
        print_status(ch)
    elif args.cmd == "ack":
        n = ch.ack(agent(args.me), args.ids)
        print(f"[comms] 已标记已读 {n} 条")
    elif args.cmd == "log":
        print(f"[comms] 项目 {slug}")
        for m in ch.load()[-max(1, args.n):]:
            print(fmt(m))
    elif args.cmd == "status":
        if args.text is not None:
            ch.set_status(agent(args.me), args.text)
            print("[comms] 进度已更新")
        else:
            print(f"[comms] 项目 {slug}")
            print_status(ch)
    elif args.cmd == "lock":
        ch.lock(agent(args.me), args.resource, args.purpose)
        print(f"[comms] 已占用 {args.resource}")
    elif args.cmd == "unlock":
        ch.unlock(agent(args.me), args.resource, args.stale, args.ttl)
        print(f"[comms] 已释放 {args.resource}")
    elif args.cmd == "locks":
        print_status(ch, args.ttl)
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        return run(sys.argv[1:])
    except CommsError as e:
        print(f"[comms] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
