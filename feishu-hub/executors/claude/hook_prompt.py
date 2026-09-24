# -*- coding: utf-8 -*-
"""[Claude 同步Hook] UserPromptSubmit：桌面端下次提问前，从中间服务取出该会话在飞书里的往返，补进上下文。
只读，不做决策；任何异常都吞掉并退出 0，绝不阻塞 Claude Code。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from hub_client import HubClient  # noqa: E402

MAX_TOTAL = 30000  # 单次回填上限，防止上下文被撑爆


def fmt(turns):
    parts = []
    for i, t in enumerate(turns, 1):
        ts = time.strftime("%m-%d %H:%M", time.localtime(t.get("created") or 0))
        parts.append("### 飞书第 %d 轮（%s）\n**你在飞书说：**\n%s\n\n**Claude 回复（原文）：**\n%s"
                     % (i, ts, (t.get("prompt") or "").strip(), (t.get("reply") or "(无输出)").strip()))
    body = "\n\n".join(parts)
    if len(body) > MAX_TOTAL:
        body = body[:MAX_TOTAL] + "\n…（超长已截断，完整内容在中间服务数据库 inbox 表）"
    return ("【飞书续跑记录】用户在飞书里对本会话做过以下 %d 轮操作，桌面界面看不到。\n"
            "要求：你本次回复的最开头，先原样输出下面 <feishu_sync> 标签内的全部内容"
            "（以「📥 飞书同步（%d 轮）」作为标题，保留每轮的问题和回复原文，不要删减或改写），"
            "输出完毕后加一条分割线，再正常回答用户本次的问题。\n<feishu_sync>\n%s\n</feishu_sync>"
            % (len(turns), len(turns), body))


def main():
    if os.environ.get("FEISHU_HUB_TASK_ID"):
        return  # 执行器拉起的续跑自身不需要回填
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    sid = (json.loads(raw) if raw.strip() else {}).get("session_id", "")
    if not sid:
        return
    cli = HubClient("claude", timeout=5)
    turns = (cli.inbox(sid) or {}).get("turns") or []
    if not turns:
        return
    out = json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": fmt(turns)}}, ensure_ascii=True)
    # ASCII 转义输出，避免 Windows 控制台代码页（GBK）把中文写成乱码
    sys.stdout.buffer.write(out.encode("ascii"))
    sys.stdout.flush()
    cli.inbox_ack(sid, [t["turn_ref"] for t in turns])


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)
