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
会话配对（会话级 1 对 1，2026-11-06 起取代旧的身份绑定）：
  sire_comms.py --session <会话id> pair start --me Claude [--peer Codex] [--pick <配对id>]
      在本会话开始协作：无人发起则新建待配对；对端已发起则认领并固定双方会话；本会话已在配对中则只提示已就绪
  sire_comms.py pair list                                   查看本项目全部配对
  配对后以该身份收发、确认、轮询、读信箱、上报、加解锁必须带 --session <会话id>（或环境变量 SIRE_SESSION），
  脚本按“身份 + 会话”定位唯一配对，未配对或他人会话一律拒绝；配对期间双方会话不可更改，结束（stop/空闲超时）后释放。
  session start 是 pair start 的别名；bind/--rebind 已废弃。

--me 可省略，改用环境变量 SIRE_AGENT。类型：info / request / question / reply / handoff。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
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
IDLE_SECONDS = 3600.0  # 协作空闲上限（2 次 30 分钟心跳 = 1 小时）；环境变量 SIRE_COMMS_IDLE_SECONDS 覆盖
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

    def __init__(self, slug: str, path: Path | None, pair: str | None = None):
        self.slug = slug
        self.pair = pair  # 配对 id；None 表示项目级通道（登记配对、放资源锁）
        self.base = comms_dir() / "projects" / slug
        # 每个配对独占一个目录：消息、绑定、监听状态、进度互不串；资源锁在项目级共享
        self.dir = self.base / "pairs" / pair if pair else self.base
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.base / "locks").mkdir(exist_ok=True)
        meta = self.base / "project.json"
        if path and not meta.exists():
            meta.write_text(json.dumps({"path": str(path), "created": now()}, ensure_ascii=False), encoding="utf-8")
        self.log = self.dir / "messages.jsonl"

    # ---- 配对登记（项目级，pairs.json）----
    def pairs(self) -> dict:
        p = self.base / "pairs.json"
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise CommsError(f"配对登记损坏，请检查 {p}") from None

    def _save_pairs(self, data: dict) -> None:
        temporary = self.base / "pairs.tmp"
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        temporary.replace(self.base / "pairs.json")

    def find_pair(self, session: str, me: str | None = None) -> tuple[str, dict, str] | None:
        """按会话 id 找未关闭的配对，返回 (配对id, 记录, 本会话身份)；找不到返回 None"""
        for pid, r in self.pairs().items():
            if r["state"] == "closed":
                continue
            for who, sid in r["members"].items():
                if sid == session and (me is None or who == me):
                    return pid, r, who
        return None

    def pair_start(self, me: str, peer: str | None, session: str, pick: str | None = None, tag: str | None = None) -> dict:
        """用户在某会话说“与 X 开始协作”（入队）。规则：
        1) 本会话已在未关闭的配对里 → 不新建、不改绑，提示已就绪/等待对方；
        2) 队列里有对方发起、指向我、标签相同、尚未被认领的待配对 → 按入队先后（FIFO）认领最早的一个（pick 可指定）；
           标签（tag）相同才互相匹配：同一项目多组并存时，用不同标签让各组互不干扰；不带标签的只和不带标签的匹配；
        3) 否则以本会话 id 新建待配对（必须点名对象），等对方会话说开始协作。
        配对一旦 active，双方会话 id 固定，不可更改；要换会话只能结束后重新配对，或另开新会话建新的一对。"""
        if not SESSION_RE.match(session or ""):
            raise CommsError("会话 id 无效：需为 4–128 位字母、数字或 . _ : -")
        fd, guard = self._guard()
        try:
            data = self.pairs()
            ttl = idle_seconds()
            for r in data.values():  # 无人认领超时的待配对自动作废
                if r["state"] == "pending" and time.time() - r["created_ts"] >= ttl:
                    r.update(state="closed", closed=now(), reason="待配对超时无人认领")
            mine = next(((pid, r) for pid, r in data.items()
                         if r["state"] != "closed" and r["members"].get(me) == session), None)
            if mine:  # 已入队/已配对：只提示，不新建、不改绑
                pid, r = mine
                other = r["target"] if r["creator"] == me else r["creator"]
                self._save_pairs(data)
                return {"result": "ready" if r["state"] == "active" else "waiting", "pair": pid, "peer": other, "peer_session": r["members"].get(other),
                        "asked_peer": peer if peer and peer != other else None}
            cands = sorted((pid for pid, r in data.items()
                            if r["state"] == "pending" and r["target"] == me and (peer is None or r["creator"] == peer)
                            and (r.get("tag") or None) == (tag or None)), key=lambda pid: data[pid]["created_ts"])
            if pick:
                if pick not in cands:
                    raise CommsError(f"待配对 {pick} 不存在、标签不符或不是发给 {me} 的")
                cands = [pick]
            if cands:  # FIFO：最早入队的先配
                pid = cands[0]
                r = data[pid]
                r["members"][me] = session
                r.update(state="active", claimed=now())
                self._save_pairs(data)
                return {"result": "claimed", "pair": pid, "peer": r["creator"], "peer_session": r["members"][r["creator"]]}
            if not peer:
                raise CommsError("没有等我的待配对，新建配对必须点名对象：--peer Codex|Claude|Qoder")
            target = peer
            if target == me:
                raise CommsError("通讯对象不能是自己")
            pid = "p" + dt.datetime.now().strftime("%y%m%d%H%M%S") + "-" + os.urandom(2).hex()
            data[pid] = {"state": "pending", "creator": me, "target": target, "members": {me: session},
                         "created": now(), "created_ts": time.time(), "tag": tag or None}
            self._save_pairs(data)
            return {"result": "created", "pair": pid, "peer": target}
        finally:
            os.close(fd)
            guard.unlink(missing_ok=True)

    def pair_update(self, pid: str, **fields) -> None:
        """更新配对登记里的字段（ping_id、keep 等）；已关闭的配对不再改"""
        fd, guard = self._guard()
        try:
            data = self.pairs()
            if pid in data and data[pid]["state"] != "closed":
                data[pid].update(fields)
                self._save_pairs(data)
        finally:
            os.close(fd)
            guard.unlink(missing_ok=True)

    def pair_close(self, pid: str, reason: str) -> None:
        """结束配对：登记置 closed，双方会话随之解除；通道目录与消息记录保留供查阅"""
        fd, guard = self._guard()
        try:
            data = self.pairs()
            if pid in data and data[pid]["state"] != "closed":
                data[pid].update(state="closed", closed=now(), reason=reason)
                self._save_pairs(data)
        finally:
            os.close(fd)
            guard.unlink(missing_ok=True)

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
            if old and old["session"] != session and self.pair:
                raise CommsError(f"{me} 已与会话 {old['session']} 配对，配对期间不可更改；要换会话请先结束协作再重新配对")
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

    def unbind(self, who: str) -> None:
        """协作结束后释放身份绑定，避免之后新建的会话被旧绑定拦截或误当同步会话"""
        fd, guard = self._guard()
        try:
            data = self.bindings()
            if who in data:
                del data[who]
                temporary = self.dir / "bindings.tmp"
                temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                temporary.replace(self.dir / "bindings.json")
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
            raise CommsError(f"{me} 在项目 {self.slug} 已绑定会话 {bound['session']}，当前会话 {session} 无权以 {me} 身份通讯；如用户要在本会话协作，请用户在本会话说开启协作（session start 会切换同步会话），否则把要说的话转告用户")

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

    def open_requests(self, msgs: list[dict]) -> list[dict]:
        """尚未收到回复、且带可写文件集的 request（用于写集冲突检查）"""
        replied = {m["re"] for m in msgs if m.get("re")}
        return [m for m in msgs if m["type"] == "request" and m.get("files") and m["id"] not in replied]

    def send(self, me: str, to: str, typ: str, text: str, re_id: int | None = None,
             files: list[str] | None = None, accept: str | None = None, evidence: str | None = None,
             force_overlap: bool = False) -> dict:
        if typ not in TYPES:
            raise CommsError(f"未知类型 {typ}，可选：{'/'.join(TYPES)}")
        if me == to:
            raise CommsError("不能给自己发消息")
        text = text.strip()
        if not text:
            raise CommsError("消息内容不能为空")
        if (files or accept or evidence) and typ != "request":
            raise CommsError("--files/--accept/--evidence 只用于 request")
        if typ == "request":
            if not (files and accept and evidence):
                print("[comms] 警告：request 缺少 --files（可写文件集）/--accept（验收点）/--evidence（证据要求），"
                      "建议补全，否则无法做写集冲突检查和验收", file=sys.stderr)
            if files:
                text += "\n【可写文件】" + "；".join(files)
            if accept:
                text += "\n【验收点】" + accept
            if evidence:
                text += "\n【证据要求】" + evidence
        if len(text) > MAX_TEXT:
            raise CommsError(f"消息过长（>{MAX_TEXT} 字），请改为写文件并在消息里给出路径")
        fd, guard = self._guard()
        try:
            msgs = self.load()
            if re_id is not None and not any(m["id"] == re_id for m in msgs):
                raise CommsError(f"要回复的消息 #{re_id} 不存在")
            if files and not force_overlap:
                for o in self.open_requests(msgs):
                    hit = sorted({a for a in files for b in o["files"] if a == b or a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/")})
                    if hit:
                        raise CommsError(f"写集冲突：{hit} 已在未回复的 request #{o['id']}（{o['from']}→{o['to']}）的可写文件内；"
                                         "等对方回复或调整文件集，确需并行时加 --force-overlap")
            m = {"id": (msgs[-1]["id"] + 1) if msgs else 1, "time": now(), "from": me, "to": to, "type": typ, "text": text}
            if files:
                m["files"] = files
            if accept:
                m["accept"] = accept
            if evidence:
                m["evidence"] = evidence
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
        self.push(m)
        return m

    def push(self, m: dict) -> str:
        """实时推送：消息写入后立即把摘要投递进收件方的会话，收件方无需轮询。目前支持 Codex（codex queue）；
        Claude 一侧由 session watch 配合 Monitor 事件流唤醒。失败只警告，不影响消息已落盘。"""
        if m["to"] != "Codex" or not m.get("to_session") or os.environ.get("SIRE_COMMS_PUSH", "1") == "0":
            return "skip"
        exe = find_codex_exe()
        if not exe:
            print("[comms] 推送跳过：找不到原生 codex.exe（可设 SIRE_CODEX_EXE）", file=sys.stderr)
            return "no-exe"
        body = m["text"] if len(m["text"]) <= 600 else m["text"][:600] + f"…（共{len(m['text'])}字，全文见 messages.jsonl #{m['id']}）"
        re_part = f" re#{m['re']}" if m.get("re") else ""
        note = (f"【协作消息 {m['from']}→{m['to']} #{m['id']} {m['type']}{re_part}】{body}\n"
                f"（来自协作通道的实时推送；按 references/comms-protocol.md 处理：展示原文，request/question 用 reply --re {m['id']} 回复后 ack，"
                f"协作范围内直接执行无需再向用户要授权；项目 {self.slug}）")
        try:
            r = subprocess.run([exe, "queue", "--thread", m["to_session"], "--message", note],
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"[comms] 推送失败：{e}", file=sys.stderr)
            return "error"
        if r.returncode != 0:
            print(f"[comms] 推送失败：{(r.stderr or r.stdout).strip()[:200]}", file=sys.stderr)
            return "failed"
        print(f"[comms] 已实时推送到 {m['to']} 会话 {m['to_session'][:8]}", file=sys.stderr)
        return "ok"

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

    def session(self, me: str, action: str, peer: str, persistent: bool = False) -> dict:
        """持久化按需监听状态；不自动发送、确认消息或启动客户端。
        默认空闲满 IDLE_SECONDS（无任何方向的新消息）自动结束，返回 expired=True 由调用方同步关闭对方；
        start --persistent 才常驻到用户说结束。"""
        if me == peer:
            raise CommsError("通讯对象不能是自己")
        fd, guard = self._guard()
        try:
            state_path = self.dir / f"session_{me}.json"
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
                "active": False, "empty_checks": 0, "seen_ids": [], "peer": peer, "persistent": False,
            }
            messages = []
            expired = False
            if action == "start":
                state = {"active": True, "empty_checks": 0, "seen_ids": [], "peer": peer,
                         "persistent": persistent, "last_activity": time.time()}
            elif action == "stop":
                state["active"] = False
            elif action == "poll" and state["active"]:
                seen = set(state["seen_ids"])
                messages = [m for m in self.unread(me)
                            if m["from"] == state["peer"] and m["id"] not in seen]
                state["empty_checks"] = 0 if messages else state["empty_checks"] + 1
                state["seen_ids"] = sorted(seen | {m["id"] for m in messages})
            if state["active"] and action in ("poll", "status") and not state.get("persistent", False):
                # 旧状态文件没有 last_activity：从现在起算，不立刻过期
                last = state.get("last_activity") or time.time()
                try:
                    last = max(last, self.log.stat().st_mtime)  # 任一方向的新消息都算活动
                except OSError:
                    pass
                if messages:
                    last = time.time()
                state["last_activity"] = last
                if time.time() - last >= idle_seconds():
                    state["active"] = False
                    expired = True
            if action != "status" or expired:
                state["updated"] = now()
                temporary = state_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
                temporary.replace(state_path)
            return {**state, "messages": messages, "project": self.slug, "expired": expired}
        finally:
            os.close(fd)
            guard.unlink(missing_ok=True)

    def wait(self, me: str, peer: str, timeout: float, interval: float, session: str | None = None) -> dict:
        """阻塞等待对方新消息，整个等待过程在进程内完成、不消耗 AI 额度。
        常驻模式下仅在消息日志变化时才解析轮询；非常驻（默认）每个间隔都检查一次空闲是否超时。
        返回：有新消息 / 会话已停止 / 超时（timeout=True，messages 为空，调用方可继续等）。"""
        deadline = time.time() + timeout
        last_sig = None
        while True:
            bound = self.bindings().get(me)
            if session and bound and bound["session"] != session:
                # 用户在别的对话重新开启协作，本会话的等待让位，避免旧会话继续抢收消息
                return {"active": False, "superseded": True, "messages": [], "project": self.slug, "peer": peer}
            try:
                stat = self.log.stat()
                sig = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                sig = None
            state = self.session(me, "status", peer) if last_sig is not None else None
            if state is not None and not state["active"]:
                return {**state, "messages": [], "project": self.slug}  # 会话已被 stop（含对方同步关闭），立即让位
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
        return self.base / "locks" / f"{res}.lock"

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
        for p in sorted((self.base / "locks").glob("*.lock")):
            try:
                out.append({"resource": p.stem, **json.loads(p.read_text(encoding="utf-8"))})
            except (OSError, json.JSONDecodeError):
                out.append({"resource": p.stem, "holder": "?", "purpose": "锁文件损坏", "time": ""})
        return out


def idle_seconds() -> float:
    try:
        return float(os.environ.get("SIRE_COMMS_IDLE_SECONDS", IDLE_SECONDS))
    except ValueError:
        return IDLE_SECONDS


def close_collab(ch: "Channel", me: str, peer: str, reason: str) -> tuple[dict, bool]:
    """关闭本方协作并同步关闭对方（通知对方），然后释放双方会话绑定。返回 (本方状态, 对方是否被关闭)"""
    result = ch.session(me, "stop", peer)
    peer_closed = False
    if ch.session(peer, "status", me).get("active"):
        ch.send(me, peer, "info", f"{me} 已关闭协作通道（{reason}）。你的监听状态已同步置为关闭：请暂停心跳/后台等待、释放自己持有的锁，不再轮询；用户再次说开始协作前不要重启。本条无需回复。")
        ch.session(peer, "stop", me)
        peer_closed = True
    if ch.pair:
        Channel(ch.slug, None).pair_close(ch.pair, reason)  # 配对作废，双方会话自动解除，可重新配对
    else:
        ch.unbind(me)
        ch.unbind(peer)
    return result, peer_closed


def peer_for(ch: "Channel", me: str, given: str | None) -> str:
    """配对通道的对端取自配对记录（不可改）；项目级通道才按身份取默认值"""
    if ch.pair:
        r = Channel(ch.slug, None).pairs().get(ch.pair)
        if r:
            return r["target"] if r["creator"] == me else r["creator"]
    return agent(given or ("Codex" if me == "Claude" else "Claude"))


def do_pair_start(ch0: "Channel", me: str, peer: str | None, session: str, pick: str | None, persistent: bool = False, tag: str | None = None) -> dict:
    """在本会话开始协作：登记配对，并为新建/认领的配对绑定会话、启动本方监听状态"""
    r = ch0.pair_start(me, peer, session, pick, tag)
    res = r["result"]
    sid = session[:8]
    if res in ("created", "claimed"):
        pch = Channel(ch0.slug, None, r["pair"])
        pch.bind(me, session)
        pch.session(me, "start", r["peer"], persistent)
        if res == "claimed":
            send_ping(pch, me, r["peer"], r["pair"])  # 连通自测：对方回 pong 才算连通
            r["message"] = f"已配对：{me} 会话 {sid} ↔ {r['peer']} 会话 {r['peer_session'][:8]}（配对 {r['pair']}），配对期间不可更改；已发连通测试，等 {r['peer']} 回 pong"
        else:
            r["message"] = f"已入队等待：请到 {r['peer']} 会话说“开始协作”，将自动按先后顺序认领本会话 {sid}（配对 {r['pair']}" + (f"，标签 {tag}" if tag else "") + "）"
    elif res == "ready":
        r["message"] = f"已就绪：本会话 {sid} 已与 {r['peer']} 会话 {str(r.get('peer_session') or '')[:8]} 配对（配对 {r['pair']}），无需再开始"
    elif res == "waiting":
        r["message"] = f"已就绪：本会话 {sid} 已发起与 {r['peer']} 的配对（配对 {r['pair']}），仍在等对方会话说“开始协作”"
    if r.get("asked_peer"):
        r["message"] += f"；注意：本会话已固定与 {r['peer']} 配对，不能改成 {r['asked_peer']}，要换对象请先结束协作"
    return r


def send_ping(pch: "Channel", me: str, peer: str, pair: str) -> dict:
    """连通自测：发一条 question，对方 reply 即视为连通；ping 的编号记进配对登记"""
    m = pch.send(me, peer, "question", f"【连通测试 {pair}】ping。收到后立即用 reply --re <本条编号> 回复 pong（连通测试必须回，不算礼节性回信）。")
    pch.pair_update(pair, ping_id=m["id"], ping_from=me)
    return m


PING_MARK = "【连通测试"


def auto_pong(ch: "Channel", me: str) -> int:
    """收到连通测试 ping 时由脚本代为回 pong，不依赖模型；命令被执行即视为本端已连通。返回回复条数"""
    msgs = ch.load()
    replied = {m["re"] for m in msgs if m.get("re")}
    n = 0
    for m in msgs:
        if m["to"] == me and m["type"] == "question" and m["text"].startswith(PING_MARK) and m["id"] not in replied:
            ch.reply(me, m["id"], "pong（脚本自动应答）")
            ch.ack(me, [str(m["id"])])
            n += 1
    if n:
        print(f"[comms] 已自动应答连通测试 {n} 条", file=sys.stderr)
    return n


def pair_verified(ch0: "Channel", pid: str, r: dict) -> bool:
    """配对是否已连通：存在对 ping 的回复"""
    ping = r.get("ping_id")
    if not ping:
        return False
    return any(m.get("re") == ping for m in Channel(ch0.slug, None, pid).load())


def print_pairs(ch0: "Channel") -> None:
    data = ch0.pairs()
    live = {k: v for k, v in data.items() if v["state"] != "closed"}
    print(f"[comms] 项目 {ch0.slug} 配对：进行中 {len(live)} 个，已结束 {len(data) - len(live)} 个")
    for pid, r in live.items():
        mem = "，".join(f"{who} {sid[:8]}" for who, sid in r["members"].items())
        wait = "" if r["state"] == "active" else f"（等 {r['target']} 认领）"
        extra = (f" 标签={r['tag']}" if r.get("tag") else "") + (" 保持" if r.get("keep") else "")
        link = "" if r["state"] != "active" else (" 已连通" if pair_verified(ch0, pid, r) else " 未连通(等 pong)")
        print(f"[comms] {pid} {r['state']}{wait}{link}{extra}：{mem}（{r['created']}）")


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


def find_codex_exe() -> str | None:
    """找原生 codex.exe（queue 的消息作为参数，不能经过 .cmd 以免元字符被 cmd 解析）"""
    env = os.environ.get("SIRE_CODEX_EXE")
    if env and Path(env).exists():
        return env
    which = shutil.which("codex")
    if not which:
        return None
    base = Path(which).resolve().parent
    for root in (base, base / "node_modules" / "@openai" / "codex"):
        for exe in root.glob("node_modules/@openai/codex-win32-*/vendor/*/bin/codex.exe"):
            return str(exe)
    return which if which.lower().endswith(".exe") else None


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


def clip(text: str, limit: int) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + f"…（共{len(text)}字，全文见 messages.jsonl）"


def print_resume(ch: Channel, me: str, last: int = 5, limit: int = 200) -> None:
    """新会话开启协作后一次输出精简交接摘要，免重读全部历史"""
    peer = peer_for(ch, me, None)
    print(f"[resume] 项目 {ch.slug}  身份 {me}")
    binds = ch.bindings()
    for who, d in binds.items():
        print(f"[resume] 绑定 {who} → {d['session']}" + (f"（原 {d['previous']}）" if d.get("previous") else ""))
    if not binds:
        print("[resume] 绑定：无")
    st = ch.session(me, "status", peer)
    print(f"[resume] 监听 active={st['active']} persistent={st.get('persistent', False)} 对方={st['peer']} 连续空闲={st['empty_checks']}")
    unread, waiting = ch.unread(me), ch.waiting(me)
    print(f"[resume] 未读 {len(unread)} 条 {[m['id'] for m in unread]}；待对方回复 {len(waiting)} 条 {[m['id'] for m in waiting]}")
    msgs = ch.load()
    print(f"[resume] 共 {len(msgs)} 条消息，最近 {min(last, len(msgs))} 条（每条≤{limit}字）：")
    for m in msgs[-last:]:
        re_part = f" re#{m['re']}" if m.get("re") else ""
        print(f"  #{m['id']} [{m['time']}] {m['from']}→{m['to']} {m['type']}{re_part}：{clip(m['text'], limit)}")
    print_status(ch)


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

    session = sub.add_parser("session", help="协作通讯：start 后轮询，用户说结束（stop）或空闲满1小时自动结束；加 --persistent 才常驻到 stop")
    session.add_argument("action", choices=("start", "poll", "stop", "status", "wait", "watch"))
    session.add_argument("--me")
    session.add_argument("--peer", help="默认：Claude 对 Codex，其余身份对 Claude")
    session.add_argument("--timeout", type=float, default=1800, help="wait：最长阻塞秒数，超时返回 timeout=true")
    session.add_argument("--interval", type=float, default=5, help="wait：检查消息日志的间隔秒数")
    session.add_argument("--persistent", action="store_true", help="仅 start 有效：常驻，不因空闲自动结束（仅用户明确要求时）")
    session.add_argument("--auto-stop", action="store_true", help="已是默认行为，保留仅为兼容旧命令")

    pr = sub.add_parser("pair", help="会话级 1 对 1 配对：start=入队（匹配同项目同标签最早的待配对，否则新建并等待），list=查看，ping=连通测试，done=完成并清理，keep=用户明确要求保持")
    pr.add_argument("action", choices=("start", "list", "ping", "done", "keep"))
    pr.add_argument("--tag", help="标签：同一项目多组并存时，相同标签才互相匹配（不带标签的只和不带标签的匹配）")
    pr.add_argument("--off", action="store_true", help="keep：取消保持")
    pr.add_argument("--accepted", action="store_true", help="done：我已验收对方交付（reply/handoff 已核对）")
    pr.add_argument("--unaccepted", metavar="原因", help="done：未验收就关闭，必须写原因，会记入配对关闭原因")
    pr.add_argument("--me")
    pr.add_argument("--peer", help="对端身份；认领时省略则接受任何指向我的待配对")
    pr.add_argument("--pick", help="有多个待配对时，指定要认领的配对 id")
    pr.add_argument("--persistent", action="store_true", help="常驻，不因空闲自动结束（仅用户明确要求时）")

    s = sub.add_parser("send")
    s.add_argument("--me")
    s.add_argument("--to", required=True)
    s.add_argument("--type", default="info")
    s.add_argument("--re", type=int)
    s.add_argument("--files", help="request：本任务可写的文件/目录，逗号分隔；与未回复 request 重叠时拒绝")
    s.add_argument("--accept", help="request：验收点")
    s.add_argument("--evidence", help="request：要求交付的证据（文件清单、命令结果、未覆盖项）")
    s.add_argument("--force-overlap", action="store_true", help="明确允许与未回复 request 的可写文件重叠")
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
    rs = sub.add_parser("resume", help="新会话接手：输出精简交接摘要（绑定、监听、未读、最近消息、锁、各方进度）")
    rs.add_argument("--me")
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
            live = sum(1 for r in ch.pairs().values() if r["state"] != "closed")
            print(f"[comms] {ch.slug}  {path}  进行中配对 {live} 个；项目级消息 {len(ch.load())} 条；{counts}")
        return 0
    if args.cmd == "inbox" and args.all_projects:
        me = agent(args.me)
        total = 0
        for c0 in all_channels():
            f = c0.find_pair(session, me) if session else None
            if not f:
                continue
            ch = Channel(c0.slug, None, f[0])
            if ch.unread(me) or ch.waiting(me):
                total += print_inbox(ch, me)
        print(f"[comms] {me} 全部项目未读合计 {total} 条")
        return 0

    slug, path = resolve_project(args.project)
    ch0 = Channel(slug, path)  # 项目级通道：登记配对、放资源锁
    if args.cmd == "pair" or (args.cmd == "session" and args.action == "start"):
        action = args.action if args.cmd == "pair" else "start"
        if action == "list":
            print_pairs(ch0)
            return 0
        if not session:
            raise CommsError("开始协作需要 --session <当前会话id>")
        me0 = agent(args.me)
        if action in ("ping", "done", "keep"):
            f0 = ch0.find_pair(session, me0)
            if not f0 or f0[1]["state"] != "active":
                raise CommsError(f"会话 {session} 在项目 {slug} 没有已配成的配对，无法 {action}")
            pid0, r0, _ = f0
            pch0 = Channel(slug, None, pid0)
            peer0 = r0["target"] if r0["creator"] == me0 else r0["creator"]
            if action == "ping":
                send_ping(pch0, me0, peer0, pid0)
                print(f"[comms] 已发连通测试（配对 {pid0}），等 {peer0} 回 pong")
            elif action == "keep":
                pch0.pair_update(pid0, keep=not args.off)
                print(f"[comms] 配对 {pid0} 已{'取消' if args.off else '设为'}保持：{'完成后将自动清理' if args.off else '完成后不自动清理，直到用户说结束'}")
            else:
                if r0.get("keep"):
                    print(f"[comms] 配对 {pid0} 用户要求保持，未清理；用户说结束协作才清理")
                else:
                    pending = pch0.waiting(me0)
                    if args.accepted:
                        reason = "已验收，清理队列"
                    elif args.unaccepted:
                        reason = f"关闭未验收：{args.unaccepted}"
                    elif pending:
                        raise CommsError(f"还有 {len(pending)} 条自己发出的 request/question 未收到回复 {[m['id'] for m in pending]}："
                                         "核对交付后加 --accepted，或用 --unaccepted <原因> 明确未验收关闭")
                    else:
                        reason = "任务完成（未声明验收），清理队列"
                    close_collab(pch0, me0, peer0, reason)
                    print(f"[comms] 任务完成：配对 {pid0} 已清理，双方会话已释放；再次协作需重新入队")
            return 0
        print(json.dumps(do_pair_start(ch0, me0, agent(args.peer) if args.peer else None, session, getattr(args, "pick", None), getattr(args, "persistent", False), getattr(args, "tag", None)), ensure_ascii=False))
        return 0
    if args.cmd in ("bind", "projects", "locks") or (args.cmd in ("log", "status") and not session and not (args.cmd == "status" and args.text is not None)):
        if args.cmd == "bind" and args.me:
            raise CommsError("绑定已改为配对：请在会话中说“与X开始协作”（pair start），配对期间不可更改")
        if args.cmd == "locks":
            print_status(ch0, args.ttl)
            return 0
        print_pairs(ch0)
        if args.cmd == "status":
            print_status(ch0)
        return 0
    # 其余命令都以“身份 + 会话”定位到唯一配对；未配对的会话一律拒绝，避免串话
    if args.cmd in ("log", "status") and getattr(args, "me", None) is None:
        found = ch0.find_pair(session) if session else None
        if not found:
            raise CommsError(f"会话 {session} 在项目 {slug} 没有进行中的配对")
        me_for_pair = found[2]
    else:
        me_for_pair = agent(args.me)
    if not session:
        raise CommsError(f"{me_for_pair} 的通讯需带 --session <会话id>（或环境变量 SIRE_SESSION）")
    found = ch0.find_pair(session, me_for_pair)
    if not found:
        raise CommsError(f"会话 {session} 在项目 {slug} 没有进行中的配对：请先在本会话说“与X开始协作”")
    ch = Channel(slug, None, found[0])
    ch.check(me_for_pair, session)
    if args.cmd in ("inbox", "resume", "session", "status", "log"):
        auto_pong(ch, me_for_pair)
    if args.cmd == "session" and args.action == "wait":
        peer = peer_for(ch, me_for_pair, args.peer)
        r = ch.wait(agent(args.me), peer, args.timeout, args.interval, session)
        if r.get("expired"):
            close_collab(ch, agent(args.me), peer, f"空闲满 {idle_seconds() / 3600:g} 小时自动结束")
        print(json.dumps(r, ensure_ascii=False))
    elif args.cmd == "session" and args.action == "watch":
        # 事件流：每条新消息输出一行 JSON（配合 Monitor 工具，每行即时唤醒 AI，空闲零消耗），会话关闭时输出 closed 并退出
        me = agent(args.me)
        peer = peer_for(ch, me, args.peer)
        while True:
            r = ch.wait(me, peer, 3600, 1, session)
            if r.get("expired"):
                close_collab(ch, me, peer, f"空闲满 {idle_seconds() / 3600:g} 小时自动结束")
            for m in r["messages"]:
                body = m["text"] if len(m["text"]) <= 600 else m["text"][:600] + f"…（共{len(m['text'])}字，全文见 messages.jsonl #{m['id']}）"
                print(json.dumps({"id": m["id"], "from": m["from"], "type": m["type"], "re": m.get("re"), "text": body}, ensure_ascii=False), flush=True)
            if not r["active"]:
                print(json.dumps({"closed": True, "reason": "同步会话已切换到别的对话" if r.get("superseded") else ("空闲超时自动结束" if r.get("expired") else "协作通道已关闭")}, ensure_ascii=False), flush=True)
                break
    elif args.cmd == "session" and args.action == "stop":
        me = agent(args.me)
        peer = peer_for(ch, me, args.peer)
        # 任意一方关闭时通知对方并同步关闭其监听状态，同时释放双方会话绑定
        result, peer_closed = close_collab(ch, me, peer, "据用户结束协作")
        if peer_closed:
            result["peer_closed"] = True
        print(json.dumps(result, ensure_ascii=False))
    elif args.cmd == "session":
        me = agent(args.me)
        peer = peer_for(ch, me, args.peer)
        r = ch.session(me, args.action, peer, args.persistent)
        if r.get("expired"):
            close_collab(ch, me, peer, f"空闲满 {idle_seconds() / 3600:g} 小时自动结束")
        print(json.dumps(r, ensure_ascii=False))
    elif args.cmd == "send":
        files = [f.strip().replace("\\", "/") for f in args.files.split(",") if f.strip()] if args.files else None
        m = ch.send(agent(args.me), agent(args.to), args.type, args.text, args.re,
                    files, args.accept, args.evidence, args.force_overlap)
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
    elif args.cmd == "resume":
        print_resume(ch, agent(args.me))
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
