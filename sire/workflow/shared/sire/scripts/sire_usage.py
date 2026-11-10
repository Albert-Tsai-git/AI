"""SIRE 额度消耗统计：读取 Claude 转录里每条助手消息的 usage，按模型、主控/子代理汇总 token。

用法：
  python sire_usage.py --turn            当前会话自上一条用户提示以来（本轮）的消耗；R9 最终回复的“额度消耗”行用它
  python sire_usage.py --session         当前会话累计
  python sire_usage.py --days 7          近 N 天全部会话累计（--by-day 按天拆分）
  python sire_usage.py --file X.jsonl    指定转录文件

当前会话 = 当前目录对应项目目录下最近修改的转录；子代理转录（目录里的 subagents/ 子文件）并入同一会话并单独标注。
只读转录，不写任何库，不联网。输出 token 为转录里的真实数值；“折算”按公开定价比例估算（输入 1、输出 5、
缓存写 1.25、缓存读 0.1，单位=输入 token），只用于同一模型内比较，不同模型之间不可直接相加，也不等于你账号的实际额度扣减。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ.get("CLAUDE_HOME") or Path.home() / ".claude")
PROJECTS = HOME / "projects"
KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
WEIGHT = {"input_tokens": 1.0, "output_tokens": 5.0, "cache_creation_input_tokens": 1.25, "cache_read_input_tokens": 0.1}


def project_dir(cwd: str) -> Path | None:
    """Claude 把项目目录名编码成路径里非字母数字的字符都换成 '-'。"""
    name = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    d = PROJECTS / name
    return d if d.is_dir() else None


def latest_transcript(cwd: str) -> Path | None:
    d = project_dir(cwd)
    if d is None:
        return None
    files = [f for f in d.glob("*.jsonl") if f.is_file()]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def parse_ts(text: str) -> float:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except (ValueError, AttributeError):
        return 0.0


def is_prompt(obj: dict) -> bool:
    """真正的用户提示：user 消息且内容不是工具结果。"""
    if obj.get("type") != "user" or obj.get("isSidechain") or obj.get("isMeta"):
        return False
    content = (obj.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    return isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "text" for b in content) \
        and not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def read_file(path: Path, sub: bool) -> tuple[dict, list[float]]:
    """返回 ({消息id: (ts, 模型, 是否子代理, usage)}, 用户提示时间列表)。同一消息 id 多行时取最后一行。"""
    msgs, prompts = {}, []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return msgs, prompts
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        ts = parse_ts(obj.get("timestamp") or "")
        if not sub and is_prompt(obj):
            prompts.append(ts)
        m = obj.get("message") or {}
        usage = m.get("usage")
        if obj.get("type") == "assistant" and isinstance(usage, dict):
            mid = m.get("id") or f"{path.name}:{i}"
            msgs[mid] = (ts, m.get("model") or "unknown", sub or bool(obj.get("isSidechain")), usage)
    return msgs, prompts


def collect(files: list[tuple[Path, bool]]) -> tuple[dict, list[float]]:
    allm, prompts = {}, []
    for f, sub in files:
        msgs, ps = read_file(f, sub)
        allm.update(msgs)
        prompts += ps
    return allm, sorted(prompts)


def session_files(main: Path) -> list[tuple[Path, bool]]:
    files = [(main, False)]
    sdir = main.with_suffix("")
    if sdir.is_dir():
        files += [(f, True) for f in sdir.rglob("*.jsonl") if f.is_file()]
    return files


def aggregate(msgs: dict, since: float = 0.0, until: float = 1e18, by_day: bool = False) -> dict:
    out: dict[tuple, dict] = {}
    for ts, model, sub, usage in msgs.values():
        if ts < since or ts > until:
            continue
        key = (time.strftime("%Y-%m-%d", time.localtime(ts)) if by_day else "", model, "子代理" if sub else "主控")
        a = out.setdefault(key, {k: 0 for k in KEYS} | {"calls": 0})
        a["calls"] += 1
        for k in KEYS:
            a[k] += int(usage.get(k) or 0)
    return out


def render(agg: dict, title: str) -> str:
    if not agg:
        return f"{title}：没有读到 usage 记录"
    lines = [f"{title}", "", "| 日期 | 模型 | 角色 | 调用 | 输入 | 输出 | 缓存写 | 缓存读 | 折算(输入token) |",
             "|---|---|---|---|---|---|---|---|---|"]
    per_model: dict[str, float] = {}
    for (day, model, role), a in sorted(agg.items()):
        w = sum(a[k] * WEIGHT[k] for k in KEYS)
        per_model[model] = per_model.get(model, 0.0) + w
        lines.append(f"| {day or '-'} | {model} | {role} | {a['calls']} | {a['input_tokens']:,} | {a['output_tokens']:,} | "
                     f"{a['cache_creation_input_tokens']:,} | {a['cache_read_input_tokens']:,} | {w:,.0f} |")
    sub_w = sum(sum(a[k] * WEIGHT[k] for k in KEYS) for (d, m, r), a in agg.items() if r == "子代理")
    tot_w = sum(per_model.values())
    lines += ["", "按模型折算：" + "；".join(f"{m} {w:,.0f}" for m, w in sorted(per_model.items(), key=lambda kv: -kv[1])),
              f"子代理占折算量 {sub_w / tot_w:.0%}（降级越多，高档模型占比越低）" if tot_w else "",
              "说明：折算按公开定价比例估算，不同模型之间不可直接相加，也不等于账号实际额度扣减。"]
    return "\n".join(x for x in lines if x is not None)


def one_line(agg: dict) -> str:
    """最终回复用的一行摘要。"""
    if not agg:
        return "额度消耗：未读到 usage 记录"
    parts = []
    by: dict[tuple, int] = {}
    for (d, model, role), a in agg.items():
        w = sum(a[k] * WEIGHT[k] for k in KEYS)
        by[(model, role)] = by.get((model, role), 0) + int(w)
    for (model, role), w in sorted(by.items(), key=lambda kv: -kv[1]):
        parts.append(f"{model}/{role} 折算 {w:,}")
    out = sum(a["output_tokens"] for a in agg.values())
    return "额度消耗：" + "；".join(parts) + f"（输出 {out:,} token；折算=输入 token 等价，估算值）"


def main() -> int:
    ap = argparse.ArgumentParser(description="SIRE 额度消耗统计（读 Claude 转录 usage）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--turn", action="store_true", help="本轮（自上一条用户提示）")
    g.add_argument("--session", action="store_true", help="当前会话累计")
    g.add_argument("--days", type=float, help="近 N 天全部会话")
    g.add_argument("--file", help="指定转录文件")
    ap.add_argument("--by-day", action="store_true")
    ap.add_argument("--line", action="store_true", help="只输出一行摘要")
    ap.add_argument("--cwd", default=os.getcwd())
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.days:
        since = time.time() - args.days * 86400
        files = [(f, "subagents" in f.parts) for f in PROJECTS.rglob("*.jsonl") if f.stat().st_mtime >= since]
        msgs, _ = collect(files)
        print(render(aggregate(msgs, since, by_day=args.by_day), f"近 {args.days:g} 天全部会话"))
        return 0
    main_file = Path(args.file) if args.file else latest_transcript(args.cwd)
    if main_file is None:
        print("没有找到当前目录对应的 Claude 转录", file=sys.stderr)
        return 2
    msgs, prompts = collect(session_files(main_file))
    if args.turn:
        since = prompts[-1] if prompts else 0.0
        agg = aggregate(msgs, since)
        print(one_line(agg) if args.line else render(agg, "本轮额度消耗（自上一条用户提示起）"))
    else:
        agg = aggregate(msgs, by_day=args.by_day)
        print(one_line(agg) if args.line else render(agg, f"当前会话累计（{main_file.name}）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
