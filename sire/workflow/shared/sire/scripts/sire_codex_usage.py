"""Codex rollout 的只读用量适配；token 实数与账号额度快照分开报告。"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from datetime import datetime
from pathlib import Path

from sire_paths import ledger_runs_dir
from sire_codex_cache import read_events, locate_session

FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens",
          "cache_write_input_tokens", "reasoning_output_tokens", "total_tokens")


def stamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError, TypeError):
        return 0.0


def duration(seconds):
    return f"{max(0, round(seconds))}秒"


def clock(ts):
    return datetime.fromtimestamp(ts).astimezone().strftime("%H:%M:%S")


def normal_path(value):
    return os.path.normcase(os.path.abspath(value))


def counters(value):
    if not isinstance(value, dict):
        return None
    if any(type(value.get(k)) is not int or value[k] < 0
           for k in ("input_tokens", "output_tokens")):
        return None
    return {k: value[k] for k in FIELDS
            if type(value.get(k)) is int and value[k] >= 0}


def load(path: Path, use_cache=True) -> dict:
    if path.suffix != ".jsonl":
        raise ValueError("暂不支持压缩转录；没有真实记录，不猜测")
    rows, warnings = read_events(path, use_cache=use_cache)
    meta = next((r.get("payload", {}) for r in rows if r.get("type") == "session_meta"), {})
    turns, samples, snapshots, candidates = [], [], [], []
    current_turn, model, previous = None, "未知模型", None
    # 同一回合有可去重的响应明细时，仅统计明细；不再与累计快照相加。
    detail_turns, details = set(), {}
    context_turn = None
    for row in rows:
        p = row.get("payload") or {}
        if row.get("type") == "turn_context" or (row.get("type") == "event_msg" and p.get("type") == "task_started"):
            context_turn = p.get("turn_id") or context_turn
        if row.get("type") == "token_usage_record" and p.get("response_id") and counters(p.get("usage")) is not None:
            # 回合 ID 缺失时不归入明细回合，避免所有无 ID 事件被合并成同一个 None 回合
            if p.get("turn_id") or context_turn:
                detail_turns.add(p.get("turn_id") or context_turn)
    candidate_previous = None
    for row in rows:
        ts, kind = stamp(row.get("timestamp")), row.get("type")
        p = row.get("payload") or {}
        if not isinstance(p, dict):
            continue
        if kind == "event_msg" and p.get("type") == "task_started":
            current_turn = p.get("turn_id")
            turns.append({"id": current_turn, "start": ts, "end": None})
        elif kind == "event_msg" and p.get("type") == "task_complete":
            for turn in reversed(turns):
                if turn["id"] == p.get("turn_id"):
                    turn["end"] = ts
                    break
        elif kind == "turn_context":
            current_turn = p.get("turn_id") or current_turn
            model = p.get("model") or "未知模型"
        if kind == "event_msg" and p.get("type") == "token_count":
            limits = p.get("rate_limits")
            if isinstance(limits, dict):
                snapshots.append({"ts": ts, "limits": limits})
            info = p.get("info") or {}
            total, single = counters(info.get("total_token_usage")), counters(info.get("last_token_usage"))
        elif kind == "token_usage_record":
            total, single = counters(p.get("thread_token_usage")), counters(p.get("usage"))
        else:
            continue
        turn_id = p.get("turn_id") or current_turn
        if turn_id is not None and turn_id in detail_turns:
            if kind == "token_usage_record" and p.get("response_id") and single is not None:
                details[(turn_id, p["response_id"])] = {"ts": ts, "turn_id": turn_id,
                                                       "model": model, "usage": single, "method": "detail"}
                if total is not None:
                    if previous is not None and any(total[k] < previous[k] for k in ("input_tokens", "output_tokens")):
                        warnings.append("累计回退后重新起算：按唯一响应明细计数，不等待累计值超过旧高水位；仅统计已落盘明细")
            elif kind == "token_usage_record":
                warnings.append("响应明细缺少有效 usage 或 response_id，未计入；本回合仅统计已落盘明细")
            # 明细回合不叠加累计量，但末尾快照仍是下一回合的真实累计基线。
            if total is not None:
                previous = total
                candidate_previous = None
            continue
        delta = None
        if total is not None:
            if previous is None:
                # 单次量可以证明已知的第一笔；绝不能把历史累计全部归入它。
                if single is not None:
                    delta = single
                    if any(total.get(k) != single.get(k) for k in ("input_tokens", "output_tokens")):
                        warnings.append("首个累计快照缺少历史基线，仅报告可归属的单次用量")
                else:
                    warnings.append("首个累计快照缺少基线，未计入该快照")
            elif any(total[k] < previous[k] for k in ("input_tokens", "output_tokens")):
                warnings.append("累计回退：无法区分重置与乱序，区间不完整；低位候选增量单列，不并入已确认总量")
                if candidate_previous is not None and all(total[k] >= candidate_previous[k] for k in ("input_tokens", "output_tokens")):
                    candidates.append({"ts": ts, "turn_id": turn_id, "model": model,
                                       "usage": {k: total[k] - candidate_previous[k]
                                                 for k in ("input_tokens", "output_tokens")}})
                candidate_previous = total
                continue
            else:
                delta = {k: total[k] - previous[k] for k in total.keys() & previous.keys()
                         if total[k] >= previous[k]}
            previous = total
            candidate_previous = None
        elif single is not None:
            warnings.append("无累计锚点的明细未单独叠加，防止与累计序列重复")
        if delta is not None:
            samples.append({"ts": ts, "turn_id": turn_id, "model": model, "usage": delta})
    samples.extend(details.values())
    return {"meta": meta, "rows": rows, "turns": turns, "samples": samples, "candidates": candidates,
            "snapshots": snapshots, "warnings": list(dict.fromkeys(warnings))}


def select(data, since=0, until=math.inf, turn_id=None):
    return [s for s in data["samples"] if since <= s["ts"] < until
            and (turn_id is None or s["turn_id"] == turn_id)]


def usage(data, since=0, until=math.inf, turn_id=None):
    selected = select(data, since, until, turn_id)
    parts = []
    for model in sorted({s["model"] for s in selected}):
        items = [s["usage"] for s in selected if s["model"] == model]
        totals = {k: sum(u[k] for u in items) for k in FIELDS if all(k in u for u in items)}
        text = f"{model} 输入 {totals['input_tokens']:,} / 输出 {totals['output_tokens']:,} token"
        for key, label in (("cached_input_tokens", "缓存输入"), ("reasoning_output_tokens", "推理输出")):
            text += f"；{label} {totals[key]:,}" if key in totals else f"；{label}没有真实记录"
        parts.append(text)
    text = ("额度消耗：" + "；".join(parts) + "（缓存、推理为子集，不重复相加；非账号额度扣减）") if selected else "额度消耗：没有真实记录（该区间没有可归属的 Codex usage 事件）"
    if any(s.get("method") == "detail" for s in selected):
        text += "；响应明细部分仅统计已落盘明细，不保证完整覆盖回合"
    possible = [s for s in data.get("candidates", []) if since <= s["ts"] < until
                and (turn_id is None or s["turn_id"] == turn_id)]
    if possible:
        text += (f"；候选增量 输入 {sum(s['usage']['input_tokens'] for s in possible):,} / "
                 f"输出 {sum(s['usage']['output_tokens'] for s in possible):,} token"
                 "（无法区分重置与乱序，可能与确认量重叠，未并入已确认总量）")
    return text


def find_source(args):
    requested = args.session_id
    if args.file:
        path = Path(args.file).expanduser()
    else:
        requested = requested or os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID")
        if not requested:
            raise ValueError("没有当前 Codex session_id；请显式指定 --session-id 或 --file，不猜测最近会话")
        # 不将用户输入拼接成 glob，避免通配匹配其他会话。
        root = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
        path = locate_session(root, requested, use_cache=not args.no_cache)
    data = load(path, use_cache=not args.no_cache)
    meta = data["meta"]
    if not meta.get("id") or not meta.get("cwd"):
        raise ValueError("Codex 转录缺少 session_meta.id/cwd；没有真实记录")
    if requested and requested != meta["id"]:
        raise ValueError("转录 session_id 与指定会话不匹配，拒绝统计")
    if normal_path(meta["cwd"]) != normal_path(args.cwd):
        raise ValueError("转录 cwd 与当前项目不匹配，拒绝统计")
    return data


def append(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_rows(path, scope):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            row = json.loads(line)
            if row.get("scope") == scope:
                out.append(row)
        except (ValueError, AttributeError):
            continue
    return out


def quota(data, start, until=math.inf):
    snapshots = []
    for row in data["snapshots"]:
        if row["ts"] > until:
            continue
        p = row["limits"].get("primary") or {}
        if p.get("window_minutes") == 300 and type(p.get("used_percent")) in (int, float) \
                and 0 <= p["used_percent"] <= 100 and isinstance(p.get("resets_at"), (int, float)):
            snapshots.append((row, p))
    if not snapshots:
        return "5小时额度:没有读数来源（当前转录无有效300分钟窗口快照）"
    end, p = snapshots[-1]
    text = f"5小时额度:快照 {clock(end['ts'])} 已用 {p['used_percent']:g}%"
    weekly = end["limits"].get("secondary") or {}
    if weekly.get("window_minutes") == 10080 and type(weekly.get("used_percent")) in (int, float):
        text += f"；周额度已用 {weekly['used_percent']:g}%"
    # 只能取任务开始前已存在的真实基线；任务中途第一条不伪装成开始值。
    baseline = [r for r in snapshots if r[0]["ts"] <= start]
    if baseline:
        first, b = baseline[-1]
        if b["resets_at"] == p["resets_at"] and end["ts"] < p["resets_at"] \
                and p["used_percent"] >= b["used_percent"] and end["ts"] >= start:
            text += f"；账号全局读数变化 {b['used_percent']:g}% → {p['used_percent']:g}%（{p['used_percent'] - b['used_percent']:g} 个百分点）"
        else:
            text += "；窗口已变化或读数回退，差值没有真实记录"
    else:
        text += "；任务开始读数没有真实记录"
    return text + "（账号全局快照，可能滞后且混入并行会话；不能归因本任务）"


def run(args):
    data = find_source(args)
    turns = data["turns"]
    turn = next((t for t in reversed(turns) if t["id"] == args.turn_id), None) if args.turn_id else (turns[-1] if turns else None)
    if not turn or not turn["id"] or not turn["start"]:
        raise ValueError("没有匹配的 task_started/turn_id；耗时和任务用量没有真实记录")
    now = time.time()
    scope = {"client": "codex", "session": data["meta"]["id"], "turn": turn["id"],
             "run": args.run_id or turn["id"], "cwd": normal_path(args.cwd)}
    key = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:24]
    path = Path(os.environ.get("SIRE_STAGE_LOG") or ledger_runs_dir() / ("usage-" + key) / "stages.jsonl")
    rows = log_rows(path, scope)
    if args.stage_start:
        append(path, {"scope": scope, "kind": "start", "stage": args.stage_start,
                      "ts": now, "id": str(time.time_ns())})
        print(f"{args.stage_start} 开始 {clock(now)}；会话 {scope['session']}；回合 {scope['turn']}")
        return 0
    if args.stage_end:
        starts = [r for r in rows if r.get("kind") == "start" and r.get("stage") == args.stage_end]
        if not starts:
            print(f"{args.stage_end} 耗时:没有真实记录（未记录当前会话回合的开始时刻）")
            return 0
        begin = starts[-1]
        old = next((r for r in rows if r.get("kind") == "end" and r.get("start_id") == begin["id"]), None)
        if old:
            print(old["message"] + "（重复结束，未重复记录）")
            return 0
        selected = select(data, begin["ts"], now, turn["id"])
        total = sum(s["usage"]["input_tokens"] + s["usage"]["output_tokens"] for s in selected) if selected else None
        message = f"{args.stage_end} 耗时:{duration(now-begin['ts'])}({clock(begin['ts'])} → {clock(now)});" + usage(data, begin["ts"], now, turn["id"])
        append(path, {"scope": scope, "kind": "end", "stage": args.stage_end, "start_id": begin["id"],
                      "sec": now-begin["ts"], "tokens": total, "message": message, "ts": now})
        print(message)
        print("阶段归属按用量事件落盘时间；跨阶段请求未精确拆分。")
        return 0
    if args.days or args.by_day:
        raise ValueError("Codex 暂不支持跨会话 --days/--by-day；请逐会话指定来源")
    if args.plan_mark is not None or args.plan_end is not None:
        raise ValueError("Codex 使用 rollout 的真实额度快照，不接受未带来源的手填读数")
    since, until = (0, math.inf) if args.session else (turn["start"], turn.get("end") or now)
    if args.final:
        print(f"耗时:{clock(turn['start'])} → {clock(until)},总 {duration(until-turn['start'])};思考/执行/暂停没有真实拆分记录（结束时刻为统计时刻或已记录回合结束）")
    print(usage(data, since, until, None if args.session else turn["id"]))
    if args.final:
        print(quota(data, turn["start"], until))
        ranks, seen = {}, set()
        for row in rows:
            if row.get("kind") != "end" or row.get("start_id") in seen:
                continue
            seen.add(row["start_id"])
            value = ranks.setdefault(row["stage"], {"sec": 0, "tokens": 0, "known": True})
            value["sec"] += row["sec"]
            value["known"] &= row.get("tokens") is not None
            value["tokens"] += row.get("tokens") or 0
        if ranks:
            longest = max(ranks, key=lambda k: ranks[k]["sec"])
            known = {k: v for k, v in ranks.items() if v["known"]}
            costly = max(known, key=lambda k: known[k]["tokens"]) if known else None
            print(f"执行最长的阶段:{longest}({duration(ranks[longest]['sec'])});消耗token最多的已记录阶段:"
                  + (f"{costly}({known[costly]['tokens']:,} token)" if costly else "没有真实记录")
                  + "（仅本会话回合；未计时或缺用量阶段不参与额度排名）")
        else:
            print("阶段排名:没有本会话回合的真实阶段记录，不使用旧日志")
    for warning in data["warnings"]:
        print("记录限制:" + warning)
    return 0
