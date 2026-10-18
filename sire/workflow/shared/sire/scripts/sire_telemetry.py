"""SIRE 任务遥测：由 Claude/Codex 钩子自动记录各阶段耗时，任务结束后静默分析并生成 RSI 待处理发现。

子命令：
  hook --client claude|codex|qoder  钩子入口（stdin 为钩子 JSON）；不输出任何内容、任何异常都吞掉并返回 0
  analyze                         汇总已结束的任务并运行检测规则（Stop 钩子在后台自动调用）
  report [--last N] [--json]      最近任务的各阶段耗时
  pending [--json]                R9 收尾需要处理的发现（PROPOSED / REGRESSED）；没有时不输出
  resolve FINDING (--proposal ID | --ignore 原因 | --reopen)   标记发现的处理结果

遥测库 DATA_DIR/sire_telemetry.sqlite3 独立于知识库：不进 Git，写入不触发知识库的整库备份。
阶段耗时按“相邻两个事件的时间差”记到后一个事件所属阶段，因此包含模型思考时间和工具执行时间。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path
from sire_process import no_console_kwargs

from sire_paths import DATA_DIR

DB_PATH = Path(os.environ.get("SIRE_TELEMETRY_DB") or DATA_DIR / "sire_telemetry.sqlite3")
RETENTION_DAYS = 60

# 阶段判定：按顺序匹配工具名 + 工具输入的 JSON 文本，先命中先用
PHASE_PATTERNS = (
    ("rsi", re.compile(r"sire_rsi\.py|sire_supervisor\.py|sire_telemetry\.py\W+(pending|resolve|report)", re.I)),
    ("retrieve", re.compile(r"sire_kb\.py\W+(search|show|database-search|search-database)"
                            r"|sire_vector_db\.py\W+(search|show|stats)|knowledge[\\/]global", re.I)),
    # 只认归档动作本身；读 knowledge/global 属于检索，记进收尾会让 CLOSE_HEAVY 变成误报
    ("archive", re.compile(r"sire_kb\.py\W+(reindex|add|next-id|export-md|lint)|sire_vector_db\.py\W+(index|migrate)"
                           r"|sire_db_backup|snapshot_db|SIRE_ARCHIVE_(ROOT|DB)", re.I)),
    # 只认台账写入；路径里出现 runs 不等于在写台账（真实场景测试的夹具也放在 run 目录里）
    ("ledger", re.compile(r"sire_run\.py|journal\.log|run\.json|units\.json|blockers\.md|assumptions\.md"
                          r"|kb-hits\.md|stage-output|[\\/]sire_ledger[\\/]", re.I)),
    ("commit", re.compile(r"\bgit\W+(add|commit|push)\b", re.I)),
    ("rules", re.compile(r"skill\.md|global-contract\.md|[\\/]references[\\/]+[\w-]+\.md", re.I)),
)
SUBAGENT_TOOLS = {"agent", "task"}
CLOSE_PHASES = ("ledger", "archive", "rsi", "commit")
# classify() 的兜底桶：按任务规模浮动，不代表某个 SIRE 步骤变慢，不参与阶段离群判定
CATCH_ALL_PHASES = ("execute", "reply")
FAST_FORBIDDEN = ("retrieve", "ledger", "archive", "rsi", "subagent", "commit")
FAST_MARK = "快速通道：简单任务"
FULL_MARK = "快速通道：否"

# 检测规则：规则编号 -> (转为待处理所需命中次数, 优化建议)
RULES = {
    "FAST_SLOW": (3, "简单任务超过 60 秒：检查快速通道是否仍在读规则文件、重试或被工具拦截，收紧入口副本里的白名单与命令写法"),
    "FAST_SCOPE": (2, "快速通道任务做了检索/台账/归档/子代理/提交：入口副本或白名单措辞不够明确，需要收紧"),
    "CLOSE_HEAVY": (3, "收尾（台账/归档/RSI/提交）占完整任务 40% 以上：把多步手工收尾合并成脚本命令，减少模型轮次"),
    "SUBAGENT_HEAVY": (3, "子代理耗时过半且调用 3 次以上：合并同类复核角色，或小单元改由主控直接执行"),
    "TOOL_RETRY": (2, "同一命令在一个任务里失败 3 次以上：在规则或脚本里写明该场景的正确做法"),
    "RULE_READ": (3, "一个任务读取规则文件 4 次以上：入口文件直接给出所需规则，或合并规则文件"),
    "PHASE_OUTLIER": (2, "某阶段耗时超过历史中位数 3 倍：检查该阶段的脚本或规则是否有新增的低效步骤"),
    "COLLECTION_DEAD": (1, "客户端配了钩子却长时间无事件：核对该客户端配置是否仍指向 sire_telemetry.py hook，修好后 resolve；这属于采集面故障，不要靠删规则消音"),
}
DECAY_SECONDS = 7 * 86400
# 已配置钩子的客户端应当持续有心跳；长时间无事件本身就是机制故障
CLIENT_CONFIGS = tuple(Path(p) for p in (os.environ.get("SIRE_CLIENT_CONFIGS") or "").split(os.pathsep) if p) or (
    Path.home() / ".codex" / "hooks.json",
    Path.home() / ".claude" / "settings.json",
    Path.home() / ".claude" / "settings.local.json",
    Path(os.environ.get("QODER_HOME") or Path.home() / ".qoder-cn") / "settings.json",
)
CLIENT_RE = re.compile(r"--client[^a-z]+([a-z]+)", re.I)
CLIENT_DEDUPE_SECONDS = 1800


def expected_clients() -> set[str]:
    out: set[str] = set()
    for path in CLIENT_CONFIGS:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        out.update(m.group(1).lower() for m in CLIENT_RE.finditer(text))
    return out


def check_clients(c: sqlite3.Connection, now: float, stale_seconds: float) -> None:
    """只对"曾经采过、现在哑了"的客户端报警；全新安装还没有心跳由 sire_qoder.py verify 负责。"""
    for client in sorted(expected_clients()):
        last = c.execute("SELECT max(ts) FROM events WHERE client=?", (client,)).fetchone()[0]
        if last is None or now - last <= stale_seconds:
            continue
        fid = f"COLLECTION_DEAD:{client}"
        item = {"client": client, "at": round(now), "evidence": f"末次事件距今 {(now - last) / 60:.0f} 分钟"}
        row = c.execute("SELECT * FROM findings WHERE finding_id=?", (fid,)).fetchone()
        if row is not None and now - (row["last_seen"] or 0) < CLIENT_DEDUPE_SECONDS:
            continue  # 半小时内已计过，避免每次 analyze 刷命中
        if row is None:
            c.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (fid, "COLLECTION_DEAD", "PROPOSED", 1, now, now,
                       json.dumps([item], ensure_ascii=False), RULES["COLLECTION_DEAD"][1], None, None, None))
            continue
        status = row["status"] if row["status"] in ("PROPOSED", "REGRESSED") else "PROPOSED"
        evidence = (json.loads(row["evidence"] or "[]") + [item])[-10:]
        c.execute("UPDATE findings SET status=?,hits=?,last_seen=?,evidence=? WHERE finding_id=?",
                  (status, (row["hits"] or 0) + 1, now, json.dumps(evidence, ensure_ascii=False), fid))

DECAY_SECONDS = 7 * 86400

SECRET_PATTERNS = (
    re.compile(r"(?i)(token|password|passwd|secret|api[_-]?key|authorization|bearer)([\"'=: ]+)[^\s\"',;]+"),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{10,}|glpat-[A-Za-z0-9_-]{10,}|xox[abp]-[A-Za-z0-9-]{10,})"),
)


def redact(text: str, limit: int) -> str:
    """脱敏并截断，遥测库只保留定位问题所需的片段。"""
    text = SECRET_PATTERNS[0].sub(lambda m: m.group(1) + m.group(2) + "***", text)
    text = SECRET_PATTERNS[1].sub("***", text)
    return text[:limit]


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=3)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=3000")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY, ts REAL NOT NULL, client TEXT, session TEXT, event TEXT,
      tool TEXT, phase TEXT, detail TEXT, ok INTEGER, agent TEXT);
    CREATE INDEX IF NOT EXISTS events_session ON events(session, ts);
    CREATE TABLE IF NOT EXISTS tasks(
      task_id TEXT PRIMARY KEY, client TEXT, session TEXT, start_ts REAL, end_ts REAL, total_s REAL,
      mode TEXT, phases TEXT, tool_calls INTEGER, failures INTEGER, cwd TEXT, prompt TEXT,
      analyzed INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS findings(
      finding_id TEXT PRIMARY KEY, rule TEXT, status TEXT, hits INTEGER, first_seen REAL, last_seen REAL,
      evidence TEXT, suggestion TEXT, proposal_id TEXT, resolved_at REAL, note TEXT);
    """)
    return c


# ---------------------------------------------------------------- 钩子

def classify(tool: str, tool_input) -> str:
    if (tool or "").lower() in SUBAGENT_TOOLS:
        return "subagent"
    text = (tool or "") + " " + json.dumps(tool_input, ensure_ascii=False)
    for phase, pattern in PHASE_PATTERNS:
        if pattern.search(text):
            return phase
    return "execute"


def tool_failed(resp) -> bool:
    """尽量识别失败的工具调用；识别不了按成功处理。"""
    if isinstance(resp, dict):
        if resp.get("is_error") or resp.get("error") or resp.get("success") is False:
            return True
        for key in ("exit_code", "exitCode", "returncode"):
            if isinstance(resp.get(key), int) and resp[key] != 0:
                return True
        resp = resp.get("output") or resp.get("stderr") or ""
    if isinstance(resp, str):
        head = resp[:300]
        return head.startswith(("Error", "error:")) or bool(re.search(r"Exit code [1-9]", head))
    return False


def qoder_transcript(session: str) -> str:
    """Qoder 的 Stop 载荷不一定带 transcript_path，按会话 id 在客户端项目目录里找。"""
    home = Path(os.environ.get("QODER_HOME") or Path.home() / ".qoder-cn")
    cands = [f for f in home.glob(f"projects/*/{session}.jsonl") if f.is_file()]
    if not cands:
        return ""
    return str(max(cands, key=lambda f: f.stat().st_mtime))


def last_assistant_text(payload: dict) -> str:
    """取最后一条助手回复：优先用钩子直接给的字段，否则读转录文件尾部。"""
    for key in ("last_assistant_message", "last-assistant-message"):
        if isinstance(payload.get(key), str):
            return payload[key]
    path = payload.get("transcript_path") or qoder_transcript(str(payload.get("session_id") or ""))
    if not path or not os.path.isfile(path):
        return ""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        # 长回合里尾部 256KB 可能全是工具块，退而扫全文，否则最终回复的标记取不到
        for window in (256 * 1024, size):
            f.seek(max(0, size - window))
            lines = f.read().decode("utf-8", "ignore").splitlines()
            if window != size:
                lines = lines[1:] if lines else lines
            text = _scan_assistant(lines)
            if text:
                return text
    return ""


def _scan_assistant(lines: list[str]) -> str:
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        texts = []
        if obj.get("type") == "assistant":  # Claude 转录
            content = (obj.get("message") or {}).get("content") or []
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        payload_obj = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        if payload_obj.get("role") == "assistant":  # Codex rollout
            texts = [b.get("text", "") for b in payload_obj.get("content") or [] if isinstance(b, dict)]
        elif payload_obj.get("type") == "agent_message":
            texts = [payload_obj.get("message") or ""]
        text = "\n".join(t for t in texts if t)
        if text:
            return text
    return ""


def detect_mode(text: str) -> str:
    fast, full = text.rfind(FAST_MARK), text.rfind(FULL_MARK)
    if fast < 0 and full < 0:
        return "unknown"
    return "fast" if fast > full else "full"


def summarize_task(c: sqlite3.Connection, client: str, session: str, stop_ts: float, mode: str, cwd: str):
    """把上一个 stop 之后到本次 stop 之间的事件汇总成一个任务。

    回合边界以 Stop 为准；UserPromptSubmit 只是可选起点——目标续跑、自动化提示不会产生
    prompt 事件，若此时直接返回，该客户端的整端数据都进不了分析与发现链路（Qoder 实测踩过）。"""
    prev = c.execute("SELECT max(ts) FROM events WHERE session=? AND event='stop' AND ts<?",
                     (session, stop_ts)).fetchone()[0] or 0
    rows = c.execute("SELECT * FROM events WHERE session=? AND ts>? AND ts<=? ORDER BY ts, id",
                     (session, prev, stop_ts)).fetchall()
    prompts = [r for r in rows if r["event"] == "prompt"]
    others = [r for r in rows if r["event"] != "prompt"]
    if not prompts and not others:
        return
    # 回合边界兜底：目标续跑 / 自动提示不触发 UserPromptSubmit，
    # 此时仍以窗口内最早事件为起点汇总，否则整端一个任务都进不了分析与发现链路
    start = prompts[0]["ts"] if prompts else others[0]["ts"]
    phases: dict[str, float] = {}
    counts: dict[str, int] = {}
    last = start
    tool_calls = failures = 0
    for r in rows:
        if r["ts"] < start or r["event"] == "prompt":
            continue
        phase = "reply" if r["event"] == "stop" else r["phase"]
        phases[phase] = phases.get(phase, 0.0) + max(0.0, r["ts"] - last)
        last = r["ts"]
        if r["event"] == "tool":
            tool_calls += 1
            counts[phase] = counts.get(phase, 0) + 1
            failures += 0 if r["ok"] else 1
    task_id = f"{session}:{start:.3f}"
    summary = {"seconds": {k: round(v, 1) for k, v in phases.items()}, "calls": counts}
    c.execute("INSERT OR REPLACE INTO tasks(task_id,client,session,start_ts,end_ts,total_s,mode,phases,tool_calls,"
              "failures,cwd,prompt,analyzed) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)",
              (task_id, client, session, start, stop_ts, round(stop_ts - start, 1), mode,
               json.dumps(summary, ensure_ascii=False), tool_calls, failures, cwd,
               prompts[0]["detail"] if prompts else ""))


def spawn_analyze():
    """后台启动 analyze，不阻塞钩子返回。"""
    group = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "analyze"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, cwd=str(Path(__file__).resolve().parent),
                     **no_console_kwargs(group))


def cmd_hook(args) -> int:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "ignore")
        payload = json.loads(raw) if raw.strip() else {}
        event = payload.get("hook_event_name") or payload.get("event") or ""
        session = str(payload.get("session_id") or payload.get("thread_id") or "unknown")
        agent = payload.get("agent_id") or payload.get("agent_type") or ""
        ts = time.time()
        c = connect()
        with c:
            if event == "UserPromptSubmit":
                c.execute("INSERT INTO events(ts,client,session,event,detail,ok) VALUES(?,?,?,?,?,1)",
                          (ts, args.client, session, "prompt", redact(str(payload.get("prompt") or ""), 60)))
            elif event in ("PostToolUse", "PostToolUseFailure"):
                tool = str(payload.get("tool_name") or "")
                tool_input = payload.get("tool_input")
                # 子代理内部的工具调用整体算作子代理阶段
                phase = "subagent" if agent else classify(tool, tool_input)
                detail = redact(json.dumps(tool_input, ensure_ascii=False), 320)
                # Qoder 单独发 PostToolUseFailure，比猜 tool_response 字段可靠
                ok = 0 if event == "PostToolUseFailure" or tool_failed(payload.get("tool_response")) else 1
                c.execute("INSERT INTO events(ts,client,session,event,tool,phase,detail,ok,agent) "
                          "VALUES(?,?,?,?,?,?,?,?,?)", (ts, args.client, session, "tool", tool, phase, detail, ok, agent))
            elif event == "Stop":
                mode = detect_mode(last_assistant_text(payload))
                c.execute("INSERT INTO events(ts,client,session,event,detail,ok) VALUES(?,?,?,?,?,1)",
                          (ts, args.client, session, "stop", mode))
                summarize_task(c, args.client, session, ts, mode, str(payload.get("cwd") or ""))
        c.close()
        if event == "Stop":
            spawn_analyze()
    except Exception:
        pass  # 遥测失败不能影响客户端
    return 0


# ---------------------------------------------------------------- 分析

def detect(task: sqlite3.Row, history: list[sqlite3.Row]) -> list[tuple[str, str, str]]:
    """返回 (finding_id, rule, 证据) 列表。"""
    data = json.loads(task["phases"] or "{}")
    sec, calls = data.get("seconds", {}), data.get("calls", {})
    total, mode, out = task["total_s"] or 0, task["mode"], []
    if mode == "fast":
        if total > 60:
            out.append(("FAST_SLOW", "FAST_SLOW", f"{total:.0f}s"))
        used = [p for p in FAST_FORBIDDEN if calls.get(p)]
        if used:
            out.append(("FAST_SCOPE", "FAST_SCOPE", ",".join(used)))
    if mode != "fast" and total >= 180:
        close = sum(sec.get(p, 0) for p in CLOSE_PHASES)
        if close / total >= 0.4:
            out.append(("CLOSE_HEAVY", "CLOSE_HEAVY", f"收尾 {close:.0f}s / {total:.0f}s"))
        if sec.get("subagent", 0) / total >= 0.5 and calls.get("subagent", 0) >= 3:
            out.append(("SUBAGENT_HEAVY", "SUBAGENT_HEAVY", f"子代理 {sec['subagent']:.0f}s / {total:.0f}s"))
    if task["failures"] >= 3:
        out.append(("TOOL_RETRY", "TOOL_RETRY", f"{task['failures']} 次失败"))
    if calls.get("rules", 0) >= 4:
        out.append(("RULE_READ", "RULE_READ", f"{calls['rules']} 次"))
    for phase, value in sec.items():
        if mode == "unknown" or phase in CATCH_ALL_PHASES or value < 120:
            continue
        past = [json.loads(h["phases"] or "{}").get("seconds", {}).get(phase, 0) for h in history
                if h["mode"] == mode]
        past = [v for v in past if v > 0]
        if len(past) >= 5 and value > 3 * statistics.median(past):
            out.append((f"PHASE_OUTLIER:{phase}", "PHASE_OUTLIER",
                        f"{phase} {value:.0f}s，中位数 {statistics.median(past):.0f}s"))
    return out


def record_finding(c: sqlite3.Connection, fid: str, rule: str, evidence: str, task: sqlite3.Row, now: float):
    need, suggestion = RULES[rule]
    row = c.execute("SELECT * FROM findings WHERE finding_id=?", (fid,)).fetchone()
    item = {"task": task["task_id"], "client": task["client"], "at": round(task["end_ts"]), "evidence": evidence}
    if row is None:
        status = "PROPOSED" if need <= 1 else "OPEN"
        c.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
                  (fid, rule, status, 1, now, now, json.dumps([item], ensure_ascii=False), suggestion))
        return
    hits = row["hits"]
    if row["status"] == "OPEN" and now - (row["last_seen"] or 0) > DECAY_SECONDS:
        hits = 0  # 超过 7 天没再出现，重新计数
    hits += 1
    status = row["status"]
    if status == "OPEN" and hits >= need:
        status = "PROPOSED"
    elif status == "FIXED" and hits >= need:
        status = "REGRESSED"  # 修复后同类问题再次累积，提示回滚或重做
    evidence_list = (json.loads(row["evidence"] or "[]") + [item])[-10:]
    c.execute("UPDATE findings SET status=?,hits=?,last_seen=?,evidence=? WHERE finding_id=?",
              (status, hits, now, json.dumps(evidence_list, ensure_ascii=False), fid))


def cmd_analyze(args) -> int:
    c = connect()
    now = time.time()
    with c:
        pending = c.execute("SELECT * FROM tasks WHERE analyzed=0 ORDER BY end_ts").fetchall()
        for task in pending:
            history = c.execute("SELECT * FROM tasks WHERE analyzed=1 AND end_ts<? ORDER BY end_ts DESC LIMIT 30",
                                (task["end_ts"],)).fetchall()
            for fid, rule, evidence in detect(task, history):
                record_finding(c, fid, rule, evidence, task, now)
            c.execute("UPDATE tasks SET analyzed=1 WHERE task_id=?", (task["task_id"],))
        check_clients(c, now, args.stale_hours * 3600)
        cutoff = now - RETENTION_DAYS * 86400
        c.execute("DELETE FROM events WHERE ts<?", (cutoff,))
        c.execute("DELETE FROM tasks WHERE end_ts<?", (cutoff,))
    c.close()
    return 0


# ---------------------------------------------------------------- 查询与处理

def cmd_report(args) -> int:
    c = connect()
    rows = c.execute("SELECT * FROM tasks ORDER BY end_ts DESC LIMIT ?", (args.last,)).fetchall()
    c.close()
    items = [{"task": r["task_id"], "client": r["client"], "mode": r["mode"], "total_s": r["total_s"],
              "start": time.strftime("%m-%d %H:%M", time.localtime(r["start_ts"])), "prompt": r["prompt"],
              **json.loads(r["phases"] or "{}")} for r in rows]
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0
    for it in items:
        parts = " ".join(f"{k}={v:.0f}s" for k, v in sorted(it["seconds"].items(), key=lambda kv: -kv[1]))
        print(f"{it['start']} {it['client']:<6} {it['mode']:<7} 总计 {it['total_s']:.0f}s | {parts} | {it['prompt']}")
    return 0


def cmd_pending(args) -> int:
    c = connect()
    rows = c.execute("SELECT * FROM findings WHERE status IN ('PROPOSED','REGRESSED') ORDER BY "
                     "CASE status WHEN 'REGRESSED' THEN 0 ELSE 1 END, hits DESC").fetchall()
    c.close()
    items = [{"finding": r["finding_id"], "status": r["status"], "hits": r["hits"], "suggestion": r["suggestion"],
              "proposal": r["proposal_id"], "evidence": json.loads(r["evidence"] or "[]")[-3:]} for r in rows]
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        for it in items:
            ev = "；".join(e["evidence"] for e in it["evidence"])
            extra = f" 关联提案 {it['proposal']}" if it["proposal"] else ""
            print(f"{it['finding']} [{it['status']}] 命中 {it['hits']} 次{extra}：{it['suggestion']}（近期：{ev}）")
    return 0


def cmd_resolve(args) -> int:
    c = connect()
    with c:
        row = c.execute("SELECT status FROM findings WHERE finding_id=?", (args.finding,)).fetchone()
        if row is None:
            print(f"发现 {args.finding} 不存在", file=sys.stderr)
            return 2
        if args.proposal:
            c.execute("UPDATE findings SET status='FIXED',hits=0,proposal_id=?,resolved_at=?,note=NULL "
                      "WHERE finding_id=?", (args.proposal, time.time(), args.finding))
        elif args.ignore:
            c.execute("UPDATE findings SET status='IGNORED',resolved_at=?,note=? WHERE finding_id=?",
                      (time.time(), args.ignore, args.finding))
        else:
            c.execute("UPDATE findings SET status='OPEN',hits=0,resolved_at=NULL WHERE finding_id=?", (args.finding,))
    c.close()
    print(f"{args.finding} 已更新")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SIRE 任务遥测与 RSI 自动发现")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hook")
    h.add_argument("--client", choices=("claude", "codex", "qoder"), required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--stale-hours", type=float, default=12.0, help="客户端无事件多少小时后判定采集断流")
    r = sub.add_parser("report")
    r.add_argument("--last", type=int, default=10)
    r.add_argument("--json", action="store_true")
    p = sub.add_parser("pending")
    p.add_argument("--json", action="store_true")
    s = sub.add_parser("resolve")
    s.add_argument("finding")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--proposal")
    g.add_argument("--ignore")
    g.add_argument("--reopen", action="store_true")
    args = ap.parse_args()
    if args.cmd != "hook":
        # 中文输出固定 UTF-8，避免在 GBK 控制台里乱码
        sys.stdout.reconfigure(encoding="utf-8")
    return {"hook": cmd_hook, "analyze": cmd_analyze, "report": cmd_report,
            "pending": cmd_pending, "resolve": cmd_resolve}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
