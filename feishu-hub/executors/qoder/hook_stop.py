# -*- coding: utf-8 -*-
"""[Qoder Hook] 把 Qoder 桌面的独立轮次上报到中间服务，供飞书侧续接。

用法：Qoder settings.json 的 Stop 钩子调用本脚本，stdin 为钩子 JSON。
Qoder 的 Stop 载荷不带 transcript_path，所以按 session_id 回退读客户端转录。
"""
import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from hub_client import HubClient, HubError, spool  # noqa: E402

LOG = logging.getLogger("feishu_hub.qoder.hook")
QODER_HOME = Path(os.environ.get("QODER_HOME") or Path.home() / ".qoder-cn")
LOG_HOME = Path(os.environ.get("FEISHU_HUB_HOME") or Path.home() / ".feishu_hub")
EXECUTOR = "qoder"


def transcript_text(payload):
    """取本轮可见的最终回复：优先钩子直给字段，否则按 session_id 读客户端转录尾部。"""
    for key in ("last_assistant_message", "final_response", "text"):
        if isinstance(payload.get(key), str) and payload[key].strip():
            return payload[key].strip()
    session = str(payload.get("session_id") or "")
    path = payload.get("transcript_path")
    if not path or not os.path.isfile(path):
        cands = [p for p in QODER_HOME.glob("projects/*/%s.jsonl" % session) if p.is_file()] if session else []
        if not cands:
            return ""
        path = str(max(cands, key=lambda p: p.stat().st_mtime))
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("type") != "assistant":
            continue
        blocks = (obj.get("message") or {}).get("content") or []
        text = "\n".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text").strip()
        if text:
            return text
    return ""


def build_turn(payload):
    session_id = payload.get("session_id") or payload.get("thread_id")
    cwd = payload.get("cwd") or os.environ.get("FEISHU_HUB_CWD") or str(Path.cwd())
    text = transcript_text(payload)
    if not session_id or not text:
        return None
    digest = hashlib.sha256(("%s\n%s" % (session_id, text)).encode("utf-8")).hexdigest()
    return {"executor": EXECUTOR, "session_id": str(session_id), "cwd": str(cwd), "text": text,
            "turn_id": str(payload.get("turn_id") or digest[:24]),
            "items": [{"id": "qoder-" + digest[:24], "role": "assistant", "phase": "final", "text": text}]}


def handle_payload(payload, client=None):
    """[上报] Hub 不可达时落盘 spool，等执行器上线补发。"""
    if os.environ.get("FEISHU_HUB_TASK_ID"):
        return "suppressed"          # 飞书下发的任务由执行器统一回报，避免重复卡片
    if not isinstance(payload, dict):
        return "invalid"
    turn = build_turn(payload)
    if not turn:
        LOG.warning("[Qoder执行器] Hook 缺少会话或最终回复，已忽略")
        return "invalid"
    hub_url = os.environ.get("FEISHU_HUB_URL") or os.environ.get("HUB_URL")
    try:
        client = client or HubClient(EXECUTOR, url=hub_url, timeout=10)
    except OSError:
        try:
            spool("turn", turn)
            return "spooled"
        except OSError:
            return "spool_failed"
    try:
        client.request("POST", "/v1/sessions/turns", turn, retry=False)
        return "sent"
    except HubError as e:
        if e.http == 0 or e.http >= 500:
            try:
                spool("turn", turn)
                return "spooled"
            except OSError:
                return "spool_failed"
        LOG.error("[Qoder执行器] Hook 上报被拒 code=%s", e.code)
        return "rejected"


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    if not re.search(r"\S", raw):
        return 0
    verdict, session = "invalid_json", ""
    try:
        payload = json.loads(raw)
    except ValueError:
        LOG.warning("[Qoder执行器] Hook 输入不是有效 JSON")
    else:
        session = str(payload.get("session_id") or "") if isinstance(payload, dict) else ""
        try:
            verdict = handle_payload(payload)
        except Exception:  # noqa: BLE001
            LOG.exception("[Qoder执行器] Hook 异常")
            verdict = "exception"
    LOG.info("[Qoder执行器] Stop 钩子已执行 verdict=%s session=%s", verdict, session)
    sys.stdout.write("{}\n")       # 不干扰客户端
    return 0


if __name__ == "__main__":
    LOG_HOME.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, encoding="utf-8", filename=str(LOG_HOME / "hook_qoder.log"),
                        format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
