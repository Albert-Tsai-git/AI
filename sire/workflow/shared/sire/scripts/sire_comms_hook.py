# -*- coding: utf-8 -*-
"""
协作队列入口钩子（UserPromptSubmit）：由客户端钩子带着真实 session_id 调用，不靠模型猜会话 id。

为什么要它：配对必须用“当前会话 id”入队，但 Claude 看不到自己的会话 id，
旧做法靠模型识别“开始协作”再自己拼命令，常常根本没入队，对方就一直等不到。
钩子的 stdin 里有 session_id 和 cwd，在这里确定性地入队，结果打印到 stdout，
由客户端注入对话上下文，模型只需把结果转告用户。

用法（客户端钩子命令）：
  python sire_comms_hook.py --me Claude
识别（提示词必须很短，避免把“讨论协作”误当成指令）：
  “与 Codex 开始协作 [#标签]” / “开始协作”  → 入队：有同项目同标签等我的就匹配，否则新建并等待
  “结束协作/暂停协作/停止协作/断开通讯”      → 结束本会话所在配对
  “保持协作”                                  → 本配对完成后不自动清理（再说“取消保持”恢复）
其余提示词：若本会话已在队列里，打印一行会话 id/配对/状态，方便模型随后收发。
任何异常都只打印原因并以 0 退出，不能挡住用户的提示词。
"""
from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sire_comms as sc  # noqa: E402

MAX_TRIGGER_LEN = 60  # 触发词提示词的最大长度：超过说明是在讨论，不是指令
START_RE = re.compile(r"^(?:[与和跟]\s*(?P<peer>codex|claude|qoder)?\s*)?(?:开始|启动)\s*协作(?:\s*[#＃](?P<tag>\S{1,16}))?\s*[。.!！]?$", re.I)
STOP_RE = re.compile(r"^(?:结束|暂停|停止|断开)\s*(?:协作|通讯|协作通讯)\s*[。.!！]?$")
KEEP_RE = re.compile(r"^(?P<off>取消)?\s*保持\s*(?:协作|配对)\s*[。.!！]?$")


def call(argv: list[str]) -> tuple[int, str]:
    """调用 sire_comms.run，收集输出；错误转成文字，不抛出"""
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            code = sc.run(argv)
    except sc.CommsError as e:
        return 2, f"失败：{e}"
    except SystemExit as e:  # argparse 报错
        return 2, f"失败：参数错误（{e}）"
    return code, buf.getvalue().strip()


def peer_name(raw: str | None, me: str) -> str:
    if raw:
        return {"codex": "Codex", "claude": "Claude", "qoder": "Qoder"}[raw.lower()]
    return "Codex" if me == "Claude" else "Claude"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 默认编码会把中文弄乱
    except (AttributeError, OSError):
        pass
    me = "Claude"
    args = sys.argv[1:]
    if "--me" in args:
        me = sc.agent(args[args.index("--me") + 1])
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    session = str(payload.get("session_id") or "")
    cwd = str(payload.get("cwd") or "")
    prompt = str(payload.get("prompt") or "").strip()
    if not session or not cwd:
        return 0
    base = ["--project", cwd, "--session", session]

    if len(prompt) <= MAX_TRIGGER_LEN:
        m = START_RE.match(prompt)
        if m:
            peer = peer_name(m.group("peer"), me)
            argv = base + ["pair", "start", "--me", me, "--peer", peer]
            if m.group("tag"):
                argv += ["--tag", m.group("tag")]
            code, out = call(argv)
            print(f"[协作队列] 本会话 id={session}（后续命令带 --session {session}）。入队结果：{out}")
            print("请把结果原样告诉用户；对方会话认领后会收到连通测试，需 reply pong。")
            return 0
        if STOP_RE.match(prompt):
            code, out = call(base + ["session", "stop", "--me", me])
            print(f"[协作队列] 用户要求结束协作：{out}")
            return 0
        k = KEEP_RE.match(prompt)
        if k:
            argv = base + ["pair", "keep", "--me", me] + (["--off"] if k.group("off") else [])
            code, out = call(argv)
            print(f"[协作队列] {out}")
            return 0

    # 普通提示词：本会话在队列里就带一行状态，压缩上下文后也不丢会话 id
    try:
        slug, path = sc.resolve_project(cwd)
        found = sc.Channel(slug, path).find_pair(session)
    except Exception:  # noqa: BLE001 钩子不能挡住提示词
        found = None
    if found:
        pid, rec, who = found
        other = rec["target"] if rec["creator"] == who else rec["creator"]
        state = "已配成" if rec["state"] == "active" else f"等 {other} 认领"
        print(f"[协作队列] 本会话 id={session}；配对 {pid}（{who}↔{other}，{state}）。收发消息命令需带 --session {session}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
