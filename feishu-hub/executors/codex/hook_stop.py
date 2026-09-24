# -*- coding: utf-8 -*-
"""[Codex Hook] 将桌面 Codex 的独立轮次上报到中间服务。"""
import hashlib
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from hub_client import HubClient, HubError, spool  # noqa: E402


LOG = logging.getLogger("feishu_hub.codex.hook")


def build_turn(payload):
    """[事件] 从 Codex Stop Hook 输入构造只包含可见最终回复的轮次。"""
    session_id = payload.get("session_id") or payload.get("thread_id") or payload.get("thread-id")
    cwd = payload.get("cwd") or os.environ.get("FEISHU_HUB_CWD")
    text = (payload.get("last_assistant_message") or payload.get("last-assistant-message")
            or payload.get("final_response") or payload.get("text") or "")
    if not session_id or not cwd or not text:
        return None
    turn_id = payload.get("turn_id") or payload.get("turn-id")
    digest = hashlib.sha256((str(session_id) + "\n" + str(text)).encode("utf-8")).hexdigest()
    item_id = "codex-" + (str(turn_id) if turn_id else digest[:24])
    turn = {
        "executor": "codex",
        "session_id": str(session_id),
        "cwd": str(cwd),
        "text": str(text),
        "items": [{"id": item_id, "role": "assistant", "phase": "final", "text": str(text)}],
    }
    if turn_id:
        turn["turn_id"] = str(turn_id)
    return turn


def handle_payload(payload, client=None):
    """[上报] 发送桌面独立轮次；服务暂不可达时使用公共 spool。"""
    if os.environ.get("FEISHU_HUB_TASK_ID"):
        return "suppressed"
    if not isinstance(payload, dict):
        LOG.warning("[Codex执行器] Hook 输入不是 JSON 对象")
        return "invalid"
    turn = build_turn(payload)
    if not turn:
        LOG.warning("[Codex执行器] Hook 缺少会话、目录或最终回复，已忽略")
        return "invalid"
    hub_url = os.environ.get("FEISHU_HUB_URL") or os.environ.get("HUB_URL")
    try:
        client = client or HubClient("codex", url=hub_url, timeout=10)
    except OSError as e:
        try:
            spool("turn", turn)
            LOG.warning("[Codex执行器] Hub 配置暂不可用，Hook 轮次已落盘：%s", type(e).__name__)
            return "spooled"
        except OSError as spool_error:
            LOG.error("[Codex执行器] Hook 轮次落盘失败：%s", type(spool_error).__name__)
            return "spool_failed"
    try:
        client.request("POST", "/v1/sessions/turns", turn, retry=False)
        return "sent"
    except HubError as e:
        if e.http == 0 or e.http >= 500:
            try:
                spool("turn", turn)
                LOG.warning("[Codex执行器] 中间服务不可达，Hook 轮次已落盘")
                return "spooled"
            except OSError as spool_error:
                LOG.error("[Codex执行器] Hook 轮次落盘失败：%s", type(spool_error).__name__)
                return "spool_failed"
        LOG.error("[Codex执行器] Hook 上报被中间服务拒绝 code=%s", e.code)
        return "rejected"


def main():
    """[入口] 接收 stdin Stop JSON 或 notify 参数中的轮次 JSON。"""
    # notify 把 JSON 放在最后一个参数；仅接受轮次完成事件。
    if len(sys.argv) > 1:
        try:
            payload = json.loads(sys.argv[-1])
        except (ValueError, TypeError):
            return 0
        if not isinstance(payload, dict) or payload.get("type") != "agent-turn-complete":
            return 0
        if os.environ.get("FEISHU_HUB_TASK_ID"):
            return 0
        try:
            handle_payload(payload)
        except Exception as e:  # noqa: BLE001
            LOG.exception("[Codex执行器] notify Hook 异常 %s", type(e).__name__)
        return 0
    if os.environ.get("FEISHU_HUB_TASK_ID"):
        sys.stdout.write("{}\n")
        return 0
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        LOG.warning("[Codex执行器] Hook 输入不是有效 JSON")
        sys.stdout.write("{}\n")
        return 0
    try:
        handle_payload(payload)
    except Exception as e:  # noqa: BLE001
        LOG.exception("[Codex执行器] Hook 异常 %s", type(e).__name__)
    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
