# -*- coding: utf-8 -*-
"""[Claude Stop Hook] 桌面端独立对话每轮结束后，把最终回复上报中间服务（/v1/sessions/turns），由中间服务发飞书。
执行器拉起的子进程（带 FEISHU_HUB_TASK_ID）不上报：其结果由执行器统一上报。
中间服务不可达时落盘，执行器上线后补发。任何异常都吞掉并退出 0，绝不阻塞 Claude Code。"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from hub_client import HubClient, HubError, spool  # noqa: E402


def last_assistant(transcript_path):
    """取最后一条带文字的 assistant 记录，返回 (文本, 记录 uuid)。uuid 作为轮次幂等键。"""
    text, uid = "", ""
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                parts = (rec.get("message") or {}).get("content") or []
                if isinstance(parts, str):
                    parts = [{"type": "text", "text": parts}]
                t = "\n".join(p.get("text", "") for p in parts
                              if isinstance(p, dict) and p.get("type") == "text").strip()
                if t:
                    text, uid = t, rec.get("uuid") or ""
    except OSError:
        pass
    return text, uid


def main():
    if os.environ.get("FEISHU_HUB_TASK_ID"):
        return
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    data = json.loads(raw) if raw.strip() else {}
    sid = data.get("session_id", "")
    if not sid:
        return
    # 固定用项目根目录（会话中 cd 会漂移）
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd", "") or os.getcwd()
    text, uid = last_assistant(data.get("transcript_path", ""))
    if not text:
        return
    payload = {"executor": "claude", "session_id": sid, "cwd": cwd, "text": text, "turn_id": uid or None}
    try:
        HubClient("claude", timeout=10).request("POST", "/v1/sessions/turns", payload, retry=False)
    except (HubError, OSError):
        spool("turn", payload)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)
