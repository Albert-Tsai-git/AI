# -*- coding: utf-8 -*-
"""[服务] 中间服务核心逻辑：飞书消息路由（方案 §3/§4）、执行器协议处理（PROTOCOL.md）、
统一发送出口、租约回收与重启恢复。飞书收发只经本模块的发送队列。"""
import hashlib
import json
import os
import re
import threading
import time

from hub import config, feishu, store

log = config.get_logger("hub")
CFG = {}
_work = threading.Condition()  # 有新任务可领取时唤醒长轮询

CONFIRM_WORDS = {"确认", "确定", "yes", "y", "执行", "ok"}
RESUME_WORDS = {"续跑", "继续", "确认", "执行", "重试"}
ABANDON_WORDS = {"放弃", "取消", "结束", "不用了", "算了"}
EXECUTOR_PREFIX = re.compile(
    r"^\s*(?:(?:请)?(?:让|交给|由)\s*)?(claude|codex)\s*(?:(?:来)?执行)?\s*[:：]\s*(.*)$", re.I | re.S)
COLLAB = re.compile(r"(claude|codex|你)\s*(?:来)?分析.{0,20}?(claude|codex)\s*(?:来)?执行", re.I | re.S)
DIR_PATTERN = re.compile(r'(?:^|\s)(?:@|目录[:：]\s*)(?:"([^"]+)"|((?:[A-Za-z]:[\\/]|\\\\)\S*))')
PRE_QUEUE = ("RECEIVED", store.NEED_EXECUTOR, store.NEED_DIR, store.NEED_CONFIRM)


def init(cfg):
    CFG.clear()
    CFG.update(cfg)
    store.init()
    if not store.kv_get("install_id"):
        store.kv_set("install_id", os.urandom(4).hex())


# ======================= 目录 =======================

def resolve_cwd(cwd):
    """[目录] 返回本机可访问的真实目录，找不到返回 None（绝不回退默认目录）。
    Claude 桌面版是 MSIX 应用，其看到的 %APPDATA% 路径实际位于 %LOCALAPPDATA%/Packages/<包>/LocalCache/Roaming。"""
    if not cwd:
        return None
    if os.path.isdir(cwd):
        return cwd
    roaming = os.environ.get("APPDATA", "")
    norm = os.path.normcase(os.path.normpath(cwd))
    if roaming and norm.startswith(os.path.normcase(os.path.normpath(roaming)) + os.sep):
        rel = os.path.normpath(cwd)[len(os.path.normpath(roaming)) + 1:]
        pkgs = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
        try:
            names = sorted(os.listdir(pkgs))
        except OSError:
            names = []
        for name in names:
            cand = os.path.join(pkgs, name, "LocalCache", "Roaming", rel)
            if os.path.isdir(cand):
                return cand
    return None


def cwd_key(cwd):
    """同一物理目录得到同一个键（解析 MSIX 映射、junction、大小写）。"""
    real = resolve_cwd(cwd) or cwd or ""
    return os.path.normcase(os.path.realpath(real)) if real else ""


# ======================= 发送出口 =======================

def say(reply_to, text, notice_task=""):
    """所有文字消息都进入发送队列；notice_task 表示这是某任务的提示消息，发出后用于匹配用户回复。"""
    store.enqueue("text", text, reply_to=reply_to, notice_task=notice_task)


def _send_row(r):
    if not store.outbox_claim(r["id"]):
        return True
    target = config.notify_target(CFG)
    try:
        mid = ""
        # 飞书幂等键：崩溃后重发同一条 outbox 不会产生重复消息（回帖与私聊各用一个键）
        key = "hub-%s-%s" % (store.kv_get("install_id") or "0", r["id"])
        if r["reply_to"]:
            try:
                mid = feishu.reply(CFG, r["reply_to"], r["kind"], r["payload"], uuid=key + "-r")
            except Exception as e:  # noqa: BLE001
                log.warning("[出口] 回帖失败，改为私聊 outbox=%s: %s", r["id"], e)
        if not mid:
            mid = feishu.send(CFG, target, r["kind"], r["payload"], uuid=key + "-s")
    except Exception as e:  # noqa: BLE001
        delay = min(300, 5 * (2 ** min(int(r["attempts"] or 0), 6)))
        store.outbox_retry(r["id"], str(e), delay)
        log.warning("[出口] 发送失败 outbox=%s 第%d次，%ds 后重试: %s", r["id"], (r["attempts"] or 0) + 1, delay, e)
        return False
    try:
        if r["executor"]:
            store.save_mapping(mid, r["executor"], r["session_id"], r["cwd"], r["task_id"], r["conversation_id"])
        if r["notice_task"]:
            store.update(r["notice_task"], notice_mid=mid)
    finally:
        store.outbox_sent(r["id"], mid)
    if r["task_id"] and store.outbox_unsent_for_task(r["task_id"]) == 0:
        store.cas(r["task_id"], store.RESULT_SAVED, store.DONE)
    log.info("[出口] 已发送 outbox=%s message=%s", r["id"], mid)
    return True


_flush_lock = threading.Lock()


def flush_outbox():
    """按 id 顺序发送；同一回复目标/会话的前一条未发出时，后续保序等待。"""
    if not _flush_lock.acquire(blocking=False):
        return 0
    try:
        sent, blocked, now = 0, set(), time.time()
        for r in store.outbox_pending():
            key = r["reply_to"] or r["session_id"] or ("id:%s" % r["id"])
            if key in blocked:
                continue
            if (r["next_try"] or 0) > now or not _send_row(r):
                blocked.add(key)
                continue
            sent += 1
        return sent
    finally:
        _flush_lock.release()


def deliver_result(t, text, session_id):
    """结果先落库再入发送队列；卡片全部发出后任务转 DONE。"""
    cards = feishu.result_cards(t["executor"], t["cwd"], text, int(CFG.get("card_max_chars", 2800)))
    for card in cards:
        store.enqueue("card", card, reply_to=t["source_mid"], executor=t["executor"], session_id=session_id,
                      cwd=t["cwd"], task_id=t["task_id"], conversation_id=t["conversation_id"])
    if session_id:
        store.inbox_add(t["executor"], session_id, t["prompt"], text)


# ======================= 飞书消息路由 =======================

def handle_message(mid, sender, chat_type, chat_id, msg_type, content, parent, source="ws"):
    """[路由] 处理一条用户消息（长连接与离线补拉共用）；处理中途异常会撤销去重，允许重投。"""
    if not store.mark_seen(mid):
        return False
    try:
        return _handle(mid, sender, chat_type, chat_id, msg_type, content, parent or "", source)
    except Exception:
        store.unmark_seen(mid)
        raise


def _handle(mid, sender, chat_type, chat_id, msg_type, content, parent, source):
    if sender not in CFG.get("allowed_open_ids", []):
        log.warning("[路由] 非白名单用户，忽略 %s", sender)
        return False
    if chat_type == "p2p" and chat_id:
        store.kv_set("p2p_chat_id", chat_id)
    if msg_type != "text":
        say(mid, "暂只支持文字消息。附件请写明名称和路径。")
        return False
    text = (json.loads(content or "{}").get("text") or "").strip()
    text = " ".join(w for w in text.split(" ") if not w.startswith("@_user")).strip()
    log.info("[路由] 收到 src=%s chat=%s parent=%s len=%d", source, chat_type, parent or "-", len(text))
    if parent:
        t = store.find_task_by_notice(parent)
        if t:
            if t["owner"] and t["owner"] != sender:
                say(mid, "这条提示属于其他人发起的任务，只有发起人可以处理。")
                return False
            return _on_notice_reply(t, text, mid)
        m = store.find_mapping(parent)
        if m:
            return _on_card_reply(m, text, mid, sender)
        say(mid, "找不到这条消息对应的任务。可以回复任务卡片续接，或直接私聊我创建新任务。")
        return False
    if chat_type != "p2p":
        say(mid, "群聊里请回复某条任务卡片；新任务请私聊我。")
        return False
    return _new_task(mid, text, sender)


def _requested_executor(text):
    m = EXECUTOR_PREFIX.match(text or "")
    return (m.group(1).lower(), m.group(2).strip()) if m else (None, text)


def _extract_dir(text):
    m = DIR_PATTERN.search(text or "")
    if not m:
        return "", text
    return (m.group(1) or m.group(2)).strip(), (text[:m.start()] + " " + text[m.end():]).strip()


def _collab(mid, text):
    """方案 §3.4 协作指令：v1 只识别并记录，不自动协作。"""
    if not COLLAB.search(text or ""):
        return False
    tid = store.create_task(mid, "", "new", "", "", text, store.CANCELLED)
    if tid:
        store.update(tid, error="collab_not_supported_v1")
    say(mid, "🤝 已记录协作指令。v1 暂不支持自动协作，请分别指定执行者，例如「Codex执行：分析…」。")
    return True


def _new_task(mid, text, sender=""):
    """[路由] 私聊新任务：执行者、目录缺一不可，缺什么问什么，信息齐全且确认前不启动。"""
    if _collab(mid, text):
        return False
    executor, body = _requested_executor(text)
    cwd, body = _extract_dir(body)
    if not body.strip():
        say(mid, "新任务格式：Claude执行：<内容> @<工作目录>\n只写内容也可以，我会依次询问执行者和目录。")
        return False
    tid = store.create_task(mid, executor or "", "new", "", cwd, body.strip(), "RECEIVED", owner=sender)
    if not tid:
        return False
    log.info("[路由] 新任务 %s executor=%s cwd=%s", tid, executor or "?", cwd or "-")
    advance(tid)
    return True


def _on_card_reply(m, text, mid, sender=""):
    """[路由] 回复任务卡片：沿用该卡片的执行者、会话与目录（方案 §3.2）；显式指定其他执行者时切换。"""
    if _collab(mid, text):
        return False
    executor, sid, cwd = m["executor"], m["session_id"], m["cwd"]
    req, body = _requested_executor(text)
    if req:
        if not body:
            say(mid, "请在执行者后写内容，例如「Claude执行：检查这次改动」。")
            return False
        if req != executor:
            cands = store.sessions_in_cwd(req, cwd_key(cwd), cwd_key)
            if len(cands) > 1:
                say(mid, "⚠️ 该目录有多个 %s 会话，为避免发错上下文未执行。请回复那个会话自己的卡片。" % req.title())
                return False
            sid = cands[0] if cands else ""
        executor, text = req, body
    tid = store.create_task(mid, executor, "resume" if sid else "new", sid, cwd, text, "RECEIVED",
                            conversation_id=m.get("conversation_id") or None, owner=sender)
    if tid:
        advance(tid)
    return bool(tid)


def _is_danger(text):
    low = (text or "").lower()
    return any(k.lower() in low for k in CFG.get("danger_keywords", []))


def advance(tid):
    """[路由] 入队前的门禁：执行者 → 目录（须存在且已确认）→ 危险确认 → 排队。"""
    t = store.get_task(tid)
    if not t["executor"]:
        if store.cas(tid, PRE_QUEUE, store.NEED_EXECUTOR):
            say(t["source_mid"], "🤖 用哪个 AI 执行？\n指令: %s\n\n回复本条「Claude」或「Codex」，「放弃」取消。"
                % t["prompt"][:80], notice_task=tid)
        return
    if not resolve_cwd(t["cwd"]):
        if store.cas(tid, PRE_QUEUE, store.NEED_DIR, proposed_cwd=None):
            ask_dir(store.get_task(tid))
        return
    if _is_danger(t["prompt"]) and not t["danger_ok"]:
        if store.cas(tid, PRE_QUEUE, store.NEED_CONFIRM):
            say(t["source_mid"], "⚠️ 指令含危险操作关键词：\n%s\n\n回复本条「确认」才会执行，回复其他内容取消。"
                % t["prompt"][:200], notice_task=tid)
        return
    if store.cas(tid, PRE_QUEUE, store.QUEUED, not_before=0):
        _queued_notice(store.get_task(tid))


def _queued_notice(t):
    online = store.executor_online(t["executor"], int(CFG.get("heartbeat_sec", 30)) * 2 + 30)
    if not online:
        say(t["source_mid"], "📥 已排队，但 %s 执行器当前不在线；上线后自动执行。" % t["executor"].title())
    with _work:
        _work.notify_all()


def ask_dir(t):
    """[目录] 请用户指定目录；任何目录都要回显并经用户「确认」后才生效（方案 §4，用户要求不兜底）。"""
    head = "📁 新任务需要指定工作目录，尚未执行" if not t["cwd"] else "📁 工作目录不存在，任务未执行\n原目录: %s" % t["cwd"]
    say(t["source_mid"], "%s\n执行者: %s\n指令: %s\n\n请回复本条完整路径（如 D:\\code\\xxx）\n"
        "· 建议目录: %s（回复「默认」选用，仍需再确认）\n· 回复「放弃」取消"
        % (head, (t["executor"] or "?").title(), t["prompt"][:60], CFG.get("suggest_cwd", "")), notice_task=t["task_id"])


def notify_recovery(t, reason):
    say(t["source_mid"], "⏸ 任务需要你决定（%s）\n执行者: %s\n目录: %s\n指令: %s\n\n"
        "状态不明，已停止自动处理。回复本条「续跑」在原会话继续，「放弃」结束。"
        % (reason, (t["executor"] or "").title(), t["cwd"], t["prompt"][:80]), notice_task=t["task_id"])


def _on_notice_reply(t, text, mid):
    """[路由] 对提示消息的回复：选执行者 / 定目录 / 危险确认 / 中断恢复。"""
    tid, low, st = t["task_id"], text.strip().lower(), t["status"]
    if low in ABANDON_WORDS and st in PRE_QUEUE + (store.NEEDS_RECOVERY,):
        if store.cas(tid, st, store.CANCELLED, error="abandoned"):
            say(mid, "已放弃该任务。")
        return False
    if st == store.NEED_EXECUTOR:
        if low not in CFG.get("executors", ["claude", "codex"]):
            say(mid, "请回复「Claude」或「Codex」，或「放弃」。")
            return False
        if store.cas(tid, st, "RECEIVED", executor=low, mode="new", session_id=""):
            advance(tid)
    elif st == store.NEED_DIR:
        if low in CONFIRM_WORDS:
            prop = t["proposed_cwd"]
            if not prop:
                say(mid, "请先回复一个完整的目录路径。")
            elif not resolve_cwd(prop):
                say(mid, "❌ 目录已不存在：%s\n请重新回复一个存在的目录。" % prop)
            elif store.cas(tid, st, "RECEIVED", cwd=prop, proposed_cwd=None):
                say(mid, "✅ 已确认在 %s 执行。" % prop)
                advance(tid)
            return False
        new_dir = CFG.get("suggest_cwd", "") if low in ("默认", "default") else text.strip().strip('"')
        if not resolve_cwd(new_dir):
            say(mid, "❌ 目录不存在：%s\n请重新回复一个存在的完整路径。" % new_dir)
            return False
        store.update(tid, proposed_cwd=new_dir)
        say(mid, "📁 将在以下目录执行（%s）：\n%s\n\n回复本条「确认」开始，回复其他路径更换，「放弃」取消。"
            % (t["executor"].title(), new_dir), notice_task=tid)
    elif st == store.NEED_CONFIRM:
        if low in CONFIRM_WORDS:
            if store.cas(tid, st, "RECEIVED", danger_ok=1):
                advance(tid)
        elif store.cas(tid, st, store.CANCELLED, error="danger_cancelled"):
            say(mid, "已取消该危险指令。")
    elif st == store.NEEDS_RECOVERY:
        if low in RESUME_WORDS:
            hint = "上一次执行被中断，状态不明。请先检查工作区已有的改动，再继续完成指令，不要重复已完成的步骤。"
            if store.cas(tid, st, store.QUEUED, resume_hint=hint, lease_id=None, not_before=0, busy_retries=0):
                say(mid, "↩️ 已重新排队，将在原会话、原目录继续。")
                _queued_notice(store.get_task(tid))
        else:
            say(mid, "请回复「续跑」或「放弃」。")
    else:
        say(mid, "该任务当前状态为 %s，无需操作。" % st)
    return False


# ======================= 执行器协议 =======================

class ProtoError(Exception):
    def __init__(self, http, code, message=""):
        super().__init__(message or code)
        self.http, self.code, self.message = http, code, message or code


def _check_executor(ex):
    if ex not in CFG.get("executors", []):
        raise ProtoError(400, "BAD_REQUEST", "未知执行器 %s" % ex)


def hello(body):
    ex, inst = body.get("executor"), body.get("instance_id")
    if not ex or not inst:
        raise ProtoError(400, "BAD_REQUEST", "executor/instance_id 必填")
    _check_executor(ex)
    store.executor_seen(ex, inst, body.get("version"), body.get("capabilities") or {})
    log.info("[协议] 执行器上线 %s/%s caps=%s", ex, inst, body.get("capabilities"))
    return {"ok": True, "lease_ttl_sec": CFG["lease_ttl_sec"], "heartbeat_sec": CFG["heartbeat_sec"],
            "poll_wait_sec": CFG["poll_wait_sec"], "server_time": time.time()}


def _envelope(t):
    return {"task_id": t["task_id"], "conversation_id": t["conversation_id"], "executor": t["executor"],
            "mode": t["mode"], "session_id": t["session_id"] or "", "cwd": t["cwd"], "prompt": t["prompt"],
            "attempt": t["attempt"], "resume_hint": t["resume_hint"], "lease_id": t["lease_id"],
            "lease_expires": t["lease_expires"], "limits": {"timeout_sec": CFG["task_timeout_sec"]}, "grants": []}


def claim(body):
    """[协议] 长轮询领任务；返回任务信封或 None（204）。"""
    ex, inst = body.get("executor"), body.get("instance_id")
    if not ex or not inst:
        raise ProtoError(400, "BAD_REQUEST", "executor/instance_id 必填")
    _check_executor(ex)
    caps = store.executor_caps(ex, inst)
    deadline = time.time() + max(0, min(float(body.get("wait_sec", CFG["poll_wait_sec"])), 55))
    while True:
        store.executor_seen(ex, inst)
        st, t = store.lease_next(ex, inst, caps, CFG["lease_ttl_sec"], CFG["daily_task_limit"], cwd_key)
        if st == "ok":
            log.info("[协议] 派发 %s -> %s/%s attempt=%s", t["task_id"], ex, inst, t["attempt"])
            return {"ok": True, "task": _envelope(t)}
        if st == "limit":
            say(t["source_mid"], "🛑 今日远程任务已达上限（%s 次），本条未执行。" % CFG["daily_task_limit"])
            continue
        left = deadline - time.time()
        if left <= 0:
            return None
        with _work:
            _work.wait(min(left, 2.0))


def _check_lease(tid, lease_id):
    """只有 LEASED 且租约匹配、未过期才接受事件。排入桌面队列（WAITING_EXTERNAL）后租约即失效，
    结果只能经 /v1/sessions/turns 回报。本租约已产生终态时返回 ALREADY_FINAL（客户端视为成功）。"""
    t = store.get_task(tid)
    if not t:
        raise ProtoError(404, "TASK_NOT_FOUND")
    if t["lease_id"] == lease_id and (t["status"] in store.FINAL or t["status"] == store.RESULT_SAVED):
        raise ProtoError(409, "ALREADY_FINAL")
    if t["lease_id"] != lease_id or t["status"] != store.LEASED:
        raise ProtoError(409, "LEASE_LOST")
    if t["status"] == store.LEASED and (t["lease_expires"] or 0) < time.time():
        raise ProtoError(409, "LEASE_LOST", "租约已过期")
    return t


def event(tid, body):
    """[协议] 执行器事件；(task, lease, seq) 幂等，每个事件续约。"""
    lease, seq, etype, data = body.get("lease_id"), body.get("seq"), body.get("type"), body.get("data") or {}
    if not lease or seq is None or not etype:
        raise ProtoError(400, "BAD_REQUEST", "lease_id/seq/type 必填")
    prev = store.event_lookup(tid, lease, int(seq))
    if prev is not None:
        return prev
    t = _check_lease(tid, lease)
    now = time.time()
    resp = {"ok": True, "lease_expires": now + CFG["lease_ttl_sec"]}
    if t["status"] == store.LEASED:
        store.update(tid, lease_expires=resp["lease_expires"])
    if etype == "started":
        if data.get("delivery") == "desktop_queue":
            store.cas(tid, store.LEASED, store.WAITING_EXTERNAL, delivery="desktop_queue",
                      queue_id=data.get("queue_id"))
            say(t["source_mid"], "📨 已排入 %s 桌面会话，完成后回报结果。" % t["executor"].title())
        else:
            store.update(tid, delivery="process")
            say(t["source_mid"], "🚀 %s 执行中" % t["executor"].title())
    elif etype == "session":
        if data.get("session_id"):
            store.update(tid, session_id=data["session_id"])
    elif etype in ("heartbeat", "progress"):
        pass  # v1：过程消息只记录，不转发，避免刷屏
    elif etype == "result":
        sid = data.get("session_id") or t["session_id"]
        text = (data.get("text") or "")[:256 * 1024]
        if store.cas(tid, store.LEASED, store.RESULT_SAVED, result_text=text, session_id=sid):
            deliver_result(store.get_task(tid), text, sid)
    elif etype == "failed":
        code, msg = data.get("code") or "EXEC_ERROR", data.get("message") or ""
        if code == "CWD_MISSING":
            if store.cas(tid, store.LEASED, store.NEED_DIR, lease_id=None, proposed_cwd=None):
                ask_dir(store.get_task(tid))
        elif store.cas(tid, store.LEASED, store.FAILED, error="%s: %s" % (code, msg[:300])):
            say(t["source_mid"], "❌ %s 执行失败（%s）\n%s" % (t["executor"].title(), code, msg[-500:]))
    elif etype == "interrupted":
        if store.cas(tid, store.LEASED, store.NEEDS_RECOVERY,
                     error="interrupted: %s" % (data.get("reason") or "")[:200], lease_id=None):
            notify_recovery(store.get_task(tid), data.get("reason") or "执行中断")
    else:
        raise ProtoError(400, "BAD_REQUEST", "未知事件类型 %s" % etype)
    store.event_save(tid, lease, int(seq), etype, data, resp)
    return resp


def release(tid, body):
    """[协议] 未执行即归还；会话被桌面占用时延迟重试，超过上限转人工决定。"""
    t = _check_lease(tid, body.get("lease_id"))
    code = body.get("code") or "RELEASED"
    delay = max(5, min(int(body.get("retry_after_sec") or 15), 600))
    store.unstart(tid)
    retries = (t["busy_retries"] or 0) + 1
    if code == "SESSION_BUSY" and retries >= int(CFG["session_busy_max_retries"]):
        if store.cas(tid, store.LEASED, store.NEEDS_RECOVERY, lease_id=None, busy_retries=retries,
                     error="session_busy"):
            notify_recovery(store.get_task(tid), "会话持续被桌面端占用")
    elif store.cas(tid, store.LEASED, store.QUEUED, lease_id=None, not_before=time.time() + delay,
                   busy_retries=retries, attempt=max(0, (t["attempt"] or 1) - 1)):
        if code == "SESSION_BUSY" and retries == 1:
            say(t["source_mid"], "⏳ 会话正由桌面端使用，本条尚未执行，稍后自动重试。")
    return {"ok": True}


def session_turn(body):
    """[协议] 桌面 Hook 上报独立轮次：先匹配等待中的桌面队列任务，否则发独立完成卡片。"""
    ex, sid, text = body.get("executor"), body.get("session_id"), body.get("text") or ""
    if not ex or not sid:
        raise ProtoError(400, "BAD_REQUEST", "executor/session_id 必填")
    turn = body.get("turn_id") or hashlib.sha256(text.encode("utf-8")).hexdigest()
    if not store.turn_seen(ex, sid, turn):
        return {"ok": True, "duplicate": True}
    try:
        return _session_turn(ex, sid, turn, text, body)
    except Exception:
        store.turn_unsee(ex, sid, turn)  # 处理失败撤销去重，允许 Hook 重试
        raise


def _session_turn(ex, sid, turn, text, body):
    w = store.oldest_waiting(ex, sid)
    if w and store.cas(w["task_id"], store.WAITING_EXTERNAL, store.RESULT_SAVED, result_text=text, lease_id=None):
        deliver_result(store.get_task(w["task_id"]), text, sid)
        return {"ok": True, "task_id": w["task_id"]}
    cwd = body.get("cwd") or ""
    for card in feishu.result_cards(ex, cwd, text, int(CFG.get("card_max_chars", 2800))):
        store.enqueue("card", card, executor=ex, session_id=sid, cwd=cwd)
    return {"ok": True}


def inbox_get(ex, sid):
    rows = store.inbox_list(ex, sid)
    return {"ok": True, "turns": [{"turn_ref": str(r[0]), "created": r[1], "prompt": r[2], "reply": r[3]}
                                  for r in rows]}


def inbox_ack(ex, sid, body):
    store.inbox_ack(ex, sid, [int(x) for x in body.get("turn_refs") or []])
    return {"ok": True}


# ======================= 回收与恢复 =======================

def reap():
    """[回收] 租约过期 / 桌面队列超时 → NEEDS_RECOVERY（绝不自动重派）；结果已全部发出 → DONE。"""
    now = time.time()
    for t in store.list_tasks(store.LEASED):
        if (t["lease_expires"] or 0) < now and store.cas(t["task_id"], store.LEASED, store.NEEDS_RECOVERY,
                                                         error="lease_expired", lease_id=None):
            log.warning("[回收] 租约过期 %s", t["task_id"])
            notify_recovery(store.get_task(t["task_id"]), "执行器失联或重启")
    for t in store.list_tasks(store.WAITING_EXTERNAL):
        if (t["started"] or now) + CFG["task_timeout_sec"] < now and store.cas(
                t["task_id"], store.WAITING_EXTERNAL, store.NEEDS_RECOVERY, error="external_timeout", lease_id=None):
            notify_recovery(store.get_task(t["task_id"]), "桌面会话长时间未回报结果")
    for t in store.list_tasks(store.RESULT_SAVED):
        if store.outbox_count_for_task(t["task_id"]) == 0:
            # 结果已落库但卡片未入队（写入中途崩溃）：按已存结果补建，绝不重跑
            log.warning("[回收] 结果未入发送队列，补建 %s", t["task_id"])
            deliver_result(t, t["result_text"] or "", t["session_id"])
        elif store.outbox_unsent_for_task(t["task_id"]) == 0:
            store.cas(t["task_id"], store.RESULT_SAVED, store.DONE)
    store.outbox_reset_stale()


def backfill():
    """[补拉] 拉取离线期间用户发给机器人的消息，经去重后按正常流程处理。返回 (新入账数, 错误)。"""
    chat_id, last = store.kv_get("p2p_chat_id"), float(store.kv_get("last_alive", "0") or 0)
    if not chat_id or not last:
        return 0, None
    try:
        items = feishu.list_chat_messages(CFG, chat_id, last - int(CFG["backfill_margin_sec"]))
    except Exception as e:  # noqa: BLE001
        log.warning("[补拉] 失败（可能未开通读取单聊消息权限）: %s", e)
        return 0, str(e)[:200]
    n = 0
    for it in items:
        snd = it.get("sender") or {}
        if it.get("deleted") or snd.get("sender_type") != "user":
            continue
        try:
            n += 1 if handle_message(it.get("message_id", ""), snd.get("id", ""), "p2p", it.get("chat_id", chat_id),
                                     it.get("msg_type", ""), (it.get("body") or {}).get("content", ""),
                                     it.get("parent_id", ""), source="backfill") else 0
        except Exception:  # noqa: BLE001
            log.exception("[补拉] 单条处理失败 %s", it.get("message_id"))
    log.info("[补拉] 扫描 %d 条，新入账 %d 条", len(items), n)
    return n, None


def recover():
    """[恢复] 启动：复位发送中的消息；有效租约保留（执行器可继续心跳），过期的交给回收；补拉离线消息。"""
    resent = store.outbox_reset_sending()
    # 中间服务停机期间执行器的心跳会失败：给有效租约宽限期，让执行器恢复心跳，而不是立刻判失联
    grace = time.time() + 2 * CFG["lease_ttl_sec"]
    for t in store.list_tasks(store.LEASED):
        if (t["lease_expires"] or 0) < grace:
            store.update(t["task_id"], lease_expires=grace)
    reap()
    n, err = backfill()
    if err and store.kv_get("backfill_hint_day") != time.strftime("%Y-%m-%d"):
        store.kv_set("backfill_hint_day", time.strftime("%Y-%m-%d"))
        say("", "ℹ️ 离线补拉失败：请在飞书开放平台开通「读取用户发给机器人的单聊消息」权限并发布版本。")
    waiting = len(store.list_tasks(store.NEEDS_RECOVERY))
    running = len(store.list_tasks(store.LEASED, store.WAITING_EXTERNAL))
    stat = {"resent": resent, "backfilled": n, "waiting": waiting, "running": running}
    log.info("[恢复] 完成 %s", stat)
    if any(stat.values()):
        say("", "🔄 中间服务已恢复\n补发 %(resent)d 条 · 离线补拉 %(backfilled)d 条 · 执行中 %(running)d 条\n"
                "待你决定 %(waiting)d 条" % stat)
    return stat


def background_loop(stop):
    """[后台] 每 2s 发送队列；每 10s 回收租约并记录存活时间。"""
    tick = 0
    while not stop.is_set():
        try:
            flush_outbox()
            if tick % 5 == 0:
                reap()
                store.kv_set("last_alive", time.time())
        except Exception:  # noqa: BLE001
            log.exception("[后台] 周期任务失败")
        tick += 1
        stop.wait(2)
