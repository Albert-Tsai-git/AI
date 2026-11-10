"""SIRE 额度消耗统计：读取 Claude 转录里每条助手消息的 usage，按模型、主控/子代理汇总 token。

用法：
  python sire_usage.py --final           分阶段计时：--stage-start R1 / --stage-end R1（每个阶段进入和完成时各调一次）
  python sire_usage.py --final           最终回复用：“耗时”（精确到秒）+“额度消耗”+“5小时额度”三行（任务开始先 --plan-mark <读数>，结束 --final --plan-end <读数>）
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

from sire_paths import DATA_DIR

HOME = Path(os.environ.get("CLAUDE_HOME") or Path.home() / ".claude")
STAGE_LOG = Path(os.environ.get("SIRE_STAGE_LOG") or DATA_DIR / "stage_usage.jsonl")
PLAN_LOG = Path(os.environ.get("SIRE_PLAN_LOG") or DATA_DIR / "plan_usage.jsonl")
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
    files = [f for f in d.glob("*.jsonl") if f.is_file()] if d is not None else []
    if not files:
        # 当前目录对应不到转录（例如在共享技能目录里运行脚本、统计的却是别的项目）：
        # 退而取全机最近修改的主转录；子代理转录在 subagents 子目录里，不参与选择
        files = [f for f in PROJECTS.glob("*/*.jsonl") if f.is_file()]
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
    # 子代理完成通知等系统消息也以 user 条目出现，不是用户提示，否则会把本轮起点错位到通知时刻
    origin = obj.get("origin")
    if obj.get("promptSource") == "system" or obj.get("turnOrigin") == "task_notification" \
            or (isinstance(origin, dict) and origin.get("kind") == "task-notification"):
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


PAUSE_TOOLS = {"askuserquestion", "exitplanmode"}


def plan_mark(five: float, weekly: float | None) -> None:
    """记下一次账号额度读数（百分比来自应用的 get_usage 工具，脚本自己读不到）。"""
    PLAN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PLAN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "five_hour": five, "weekly": weekly}) + "\n")


def stage_mark(kind: str, stage: str, cwd: str) -> str:
    """分阶段计时：start 记开始时刻；end 用开始时刻到现在的转录消息算该阶段真实耗时和额度折算。"""
    STAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if kind == "start":
        with STAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": now, "kind": "start", "stage": stage}) + "\n")
        return f"{stage} 开始 {hms(now)}"
    start = None
    try:
        for line in STAGE_LOG.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("stage") == stage and row.get("kind") == "start":
                start = row["ts"]
    except OSError:
        pass
    if start is None:
        return f"{stage} 耗时:未记录开始时刻,不估算"
    main = latest_transcript(cwd)
    weighted = None
    if main is not None:
        msgs, _ = collect(session_files(main))
        agg = aggregate(msgs, start, now)
        weighted = int(sum(sum(a[k] * WEIGHT[k] for k in KEYS) for a in agg.values()))
    cost = f";额度折算约 {weighted:,}(估算)" if weighted is not None else ";额度:未读到 usage"
    with STAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now, "kind": "end", "stage": stage, "start": start, "sec": now - start,
                            "weighted": weighted or 0}) + "\n")
    return f"{stage} 耗时:{dur(now - start)}({hms(start)} → {hms(now)}){cost}"


def stage_rank(turn_start: float) -> str:
    """本轮各阶段耗时与额度折算的排名：哪个阶段耗时最长、哪个阶段消耗最多。"""
    rows: dict[str, dict] = {}
    try:
        for line in STAGE_LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") == "end" and r.get("start", 0) >= turn_start - 5:
                a = rows.setdefault(r["stage"], {"sec": 0.0, "weighted": 0})
                a["sec"] += r["sec"]          # 同一阶段多次进入则累加
                a["weighted"] += r["weighted"]
    except OSError:
        pass
    if not rows:
        return "阶段排名:本轮没有阶段计时记录(阶段没有用 --stage-start/--stage-end 计时),不估算"
    longest = max(rows.items(), key=lambda kv: kv[1]["sec"])
    costly = max(rows.items(), key=lambda kv: kv[1]["weighted"])
    order = "；".join(f"{k} {dur(v['sec'])}/折算 {v['weighted']:,}"
                      for k, v in sorted(rows.items(), key=lambda kv: -kv[1]["sec"]))
    return (f"执行最长的阶段:{longest[0]}({dur(longest[1]['sec'])});消耗额度最多的阶段:{costly[0]}"
            f"(折算约 {costly[1]['weighted']:,},估算)。各阶段:{order}。"
            "未计时的阶段不在排名内")


def plan_line(turn_start: float, five_end: float | None, weekly_end: float | None) -> str:
    """本任务占用的额度百分点 = 结束读数 − 本轮开始后最早的一次读数。"""
    if five_end is None:
        return "5小时额度:未提供结束读数"
    marks = []
    try:
        for line in PLAN_LOG.read_text(encoding="utf-8").splitlines():
            try:
                marks.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    start = next((m for m in marks if m["ts"] >= turn_start - 5), None)
    if start is None:
        return f"5小时额度:未记录本任务开始读数(当前 {five_end:g}%)"
    delta = five_end - start["five_hour"]
    extra = ""
    if weekly_end is not None and start.get("weekly") is not None:
        extra = f";周额度 {start['weekly']:g}% → {weekly_end:g}%"
    note = "(百分比为整数、账号全局,并行会话的消耗会混入)"
    if delta < 0:
        return f"5小时额度:读数 {start['five_hour']:g}% → {five_end:g}%,窗口可能已重置,本任务占用无法计算{extra}"
    return f"5小时额度:本任务约 {delta:g} 个百分点(读数 {start['five_hour']:g}% → {five_end:g}%){extra}{note}"


def turn_entries(main: Path) -> list[tuple[float, dict]]:
    """主线程的 user/assistant 条目（按时间顺序）。"""
    try:
        lines = main.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("isSidechain") or obj.get("type") not in ("user", "assistant"):
            continue
        ts = parse_ts(obj.get("timestamp") or "")
        if ts:
            out.append((ts, obj))
    return out


def turn_start_index(entries: list[tuple[float, dict]]) -> int | None:
    """本轮起点 = 上一次回合结束（助手 stop_reason=end_turn）之后的第一条用户提示。
    回合中途用户追发的消息不重置起点，这样算出的是任务从开始到现在的真实时间。"""
    start = None
    for i, (_, obj) in enumerate(entries):
        if obj.get("type") == "assistant" and (obj.get("message") or {}).get("stop_reason") == "end_turn":
            start = None
        elif start is None and is_prompt(obj):
            start = i
    return start


def hms(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


def dur(sec: float) -> str:
    sec = int(round(sec))
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return (f"{h}时" if h else "") + (f"{m}分" if h or m else "") + f"{s}秒"


def timing(main: Path, now: float) -> dict | None:
    """从转录时间戳还原本轮真实耗时：开始=上一条用户提示，结束=调用时刻；
    思考=工具结果（或用户提示）到下一条助手消息的间隔，执行=助手发出工具调用到结果返回的间隔，
    暂停=等用户回答的工具（AskUserQuestion/ExitPlanMode）的整段间隔。
    注意：最后一段最终回复的生成发生在调用之后，没有计入；Stop 钩子会在任务结束时记下精确结束时间。"""
    entries = turn_entries(main)
    start_i = turn_start_index(entries)
    if start_i is None:
        return None
    start = entries[start_i][0]
    names: dict[str, str] = {}
    think = run = pause = 0.0
    slowest = (0.0, "")
    prev = start
    for ts, obj in entries[start_i + 1:]:
        gap = max(0.0, ts - prev)
        prev = ts
        content = (obj.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else []
        if obj.get("type") == "assistant":
            think += gap
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    names[b.get("id", "")] = str(b.get("name", ""))
        else:
            ids = [b.get("tool_use_id", "") for b in blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
            tool = names.get(ids[0], "") if ids else ""
            if tool.lower() in PAUSE_TOOLS:
                pause += gap
            else:
                run += gap
            if gap > slowest[0]:
                slowest = (gap, tool or "工具")
    total = max(0.0, now - start)
    tail = max(0.0, now - prev)
    think += tail  # 最后一次工具返回到现在：模型正在生成最终回复
    return {"start": start, "end": now, "total": total, "think": think, "exec": run, "pause": pause, "slowest": slowest}


def timing_line(t: dict | None) -> str:
    if not t:
        return "耗时:未读到本轮转录时间戳"
    tot = t["total"] or 1.0
    return (f"耗时:{hms(t['start'])} → {hms(t['end'])},总 {dur(t['total'])};思考 {t['think'] / tot:.0%}({dur(t['think'])}) / "
            f"执行 {t['exec'] / tot:.0%}({dur(t['exec'])}) / 暂停 {t['pause'] / tot:.0%}({dur(t['pause'])});"
            f"最慢单步 {t['slowest'][1]} {dur(t['slowest'][0])}(结束时刻为统计时刻,最终回复文字生成另计数秒)")


def main() -> int:
    ap = argparse.ArgumentParser(description="SIRE 额度消耗统计（读 Claude 转录 usage）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--turn", action="store_true", help="本轮（自上一条用户提示）")
    g.add_argument("--final", action="store_true", help="最终回复用：先输出“耗时”行，再输出“额度消耗”行")
    g.add_argument("--session", action="store_true", help="当前会话累计")
    g.add_argument("--days", type=float, help="近 N 天全部会话")
    g.add_argument("--file", help="指定转录文件")
    ap.add_argument("--by-day", action="store_true")
    ap.add_argument("--plan-mark", type=float, metavar="五小时%", help="记录一次 5 小时额度读数（任务开始时调用）")
    ap.add_argument("--plan-end", type=float, metavar="五小时%", help="配合 --final：结束时的 5 小时额度读数")
    ap.add_argument("--stage-start", metavar="阶段", help="阶段开始计时,例如 R1")
    ap.add_argument("--stage-end", metavar="阶段", help="阶段结束，输出该阶段真实耗时与额度折算")
    ap.add_argument("--weekly", type=float, help="周额度读数（可选，配合 --plan-mark / --plan-end）")
    ap.add_argument("--line", action="store_true", help="只输出一行摘要")
    ap.add_argument("--cwd", default=os.getcwd())
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.stage_start or args.stage_end:
        print(stage_mark("start" if args.stage_start else "end", args.stage_start or args.stage_end, args.cwd))
        return 0
    if args.plan_mark is not None:
        plan_mark(args.plan_mark, args.weekly)
        print(f"已记录额度读数:5小时 {args.plan_mark:g}%")
        return 0
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
    ents = turn_entries(main_file)
    ti = turn_start_index(ents)
    turn_since = ents[ti][0] if ti is not None else (prompts[-1] if prompts else 0.0)
    if args.final:
        since = turn_since
        print(timing_line(timing(main_file, time.time())))
        print(one_line(aggregate(msgs, since)))
        print(plan_line(since, args.plan_end, args.weekly))
        print(stage_rank(since))
        return 0
    if args.turn:
        since = turn_since
        agg = aggregate(msgs, since)
        print(one_line(agg) if args.line else render(agg, "本轮额度消耗（自上一条用户提示起）"))
    else:
        agg = aggregate(msgs, by_day=args.by_day)
        print(one_line(agg) if args.line else render(agg, f"当前会话累计（{main_file.name}）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
