"""SIRE 任务遥测：由 Claude/Codex 钩子自动记录各阶段耗时，任务结束后静默分析并生成 RSI 待处理发现。

子命令：
  hook --client claude|codex|qoder  钩子入口（stdin 为钩子 JSON）；不输出任何内容、任何异常都吞掉并返回 0
  analyze                         汇总已结束的任务并运行检测规则（Stop 钩子在后台自动调用）
  report [--last N] [--json]      最近任务的各阶段耗时
  pending [--json]                R9 收尾需要处理的发现（PROPOSED / REGRESSED）；没有时不输出
  resolve FINDING (--proposal ID | --ignore 原因 | --reopen)   标记发现的处理结果

遥测库 DATA_DIR/sire_telemetry.sqlite3 独立于知识库：不进 Git，写入不触发知识库的整库备份。
阶段耗时按“相邻两个事件的时间差”记到后一个事件所属阶段；有 PreToolUse 事件时（Claude）再把每段时间拆成
思考（模型生成）/执行（工具运行）/暂停（权限确认、等用户回答）三类，并按子代理角色汇总；没有 Pre 事件的客户端记为“未拆分”。
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
    "USER_CORRECTION": (3, "用户在提示词里纠正/追问同类问题：回看这些任务，找出规则缺口或理解偏差并写进入口规则"),
    "USAGE_MISSING": (1, "完整流程的最终回复缺少“耗时”或“额度消耗”：检查 sire_usage.py --plan-mark/--stage-*/--final 是否被执行，补强入口提醒或收尾门禁"),
    "RULE_VIOLATION": (1, "出现违反硬规则的命令（建 worktree、自行建/推 tag）：检查入口提醒与技能是否被执行，补强门禁"),
    "GATE_BLOCK": (2, "同一任务里 sire_run.py 多次失败（门禁字段/状态流转）：把该门禁的正确用法写进规则或脚本报错提示"),
    "REVIEW_FAIL": (2, "单元复核或测试多次 FAIL：检查拆解粒度、验收标准是否写清、执行者是否漏读依赖"),
    "COMMS_FAIL": (2, "sire_comms.py 在一个任务里多次失败：核对配对/会话参数，补充报错提示或协议说明"),
    "OVERHEAD_HIGH": (1, "SIRE 流程开销（检索/读规则/台账/归档/RSI/提交/子代理）占完整任务时间过半：按诊断报告里的成因合并步骤、降级模型或脚本化"),
    "PHASE_SHARE": (1, "某 SIRE 阶段占完整任务时间比例偏高：按诊断成因处理（调用碎片化→合并成脚本；长尾单步→查该命令；失败重试→补正确用法）"),
    "PAUSE_HIGH": (1, "暂停（权限确认/等用户回答）占已拆分时间比例偏高：把常用只读命令加入权限 allowlist，合并确认点，需要用户决定的事一次问完"),
    "THINK_HIGH": (1, "模型思考占已拆分时间比例偏高：把可剥离的检索/读文件/机械改写交给低档子代理降级，精简规则，减少高档模型的无工具长推理"),
    "ROLE_HEAVY": (1, "某个子代理角色耗时占完整任务过半：核对该角色是否过重、粒度是否过大，能降级的改用低一档模型"),
    "HOOK_MISSING": (1, "遥测库里出现过的客户端，配置里已没有 sire_telemetry.py 钩子：重新注册钩子（可能被其他安装脚本覆盖），否则该端耗时数据会断流"),
    "COLLECTION_DEAD": (1, "客户端配了钩子却长时间无事件：核对该客户端配置是否仍指向 sire_telemetry.py hook，修好后 resolve；这属于采集面故障，不要靠删规则消音"),
}
DECAY_SECONDS = 30 * 86400  # 30 天没再出现才清零计数（原 7 天过短，低频问题永远攒不够）
# 已配置钩子的客户端应当持续有心跳；长时间无事件本身就是机制故障
CLIENT_CONFIGS = tuple(Path(p) for p in (os.environ.get("SIRE_CLIENT_CONFIGS") or "").split(os.pathsep) if p) or (
    Path.home() / ".codex" / "hooks.json",
    Path.home() / ".claude" / "settings.json",
    Path.home() / ".claude" / "settings.local.json",
    Path(os.environ.get("QODER_HOME") or Path.home() / ".qoder-cn") / "settings.json",
)
CLIENT_RE = re.compile(r"--client[^a-z]+([a-z]+)", re.I)
CLIENT_DEDUPE_SECONDS = 1800

# 被忽略的发现不再永久沉默：同类命中累计到 max(阈值*2, 4) 次，或距忽略超过 14 天又命中，就复活为待处理
# （resolve --ignore ... --accepted 表示"已知并接受"，永不复活）
REVIVE_SECONDS = 14 * 86400
CORRECTION_RE = re.compile(r"不对|不是这样|错了|重做|没按|为什么(?:没|不)|漏了|还是不行|我说过|不是让你")
VIOLATION_RE = re.compile(r"git\W+worktree\W+add|EnterWorktree|--worktree\b|isolation\W+worktree"
                          r"|git\W+tag\s+(?!-l\b|--list\b|-d\b)[\w.-]|git\W+push\b.*--tags", re.I)
GATE_RE = re.compile(r"sire_run\.py", re.I)
REVIEW_FAIL_RE = re.compile(r"sire_run\.py\W+(?:review|test)\b.*\bFAIL\b", re.I)
COMMS_RE = re.compile(r"sire_comms\.py", re.I)

# 时间自我分析：SIRE 流程开销阶段、诊断窗口与阈值
OVERHEAD_PHASES = ("retrieve", "rules", "ledger", "archive", "rsi", "commit", "subagent")
DIAG_DAYS = 14
OVERHEAD_LIMIT = 0.5      # 开销合计占完整任务时间比例达到该值 → OVERHEAD_HIGH
PHASE_SHARE_LIMIT = 0.2   # 单个开销阶段占比达到该值 → PHASE_SHARE:<阶段>
DIAG_MIN_TASKS = 5
DIGEST_INTERVAL = 86400   # analyze 里每 24 小时自动诊断一次
# 思考/执行/暂停拆分：等用户回答的工具整段记为暂停；权限确认通知到工具返回之间记为暂停
PAUSE_TOOLS = {"askuserquestion", "exitplanmode"}
SPLIT_COVERAGE_MIN = 0.3  # 已拆分时间占比低于此值不据此生成发现（多数客户端没有 Pre 事件）
PAUSE_LIMIT = 0.25        # 暂停占已拆分时间 → PAUSE_HIGH
THINK_LIMIT = 0.7         # 思考占已拆分时间 → THINK_HIGH
ROLE_LIMIT = 0.5          # 单个子代理角色占任务总时间 → ROLE_HEAVY
ROLE_MAP = {
    "sire-librarian": "R1", "sire-analyst": "R2", "sire-decomposer": "R3", "sire-spec-reviewer": "R4",
    "sire-implementer": "R5", "sire-code-reviewer": "R6", "sire-code-reviewer-a": "R6", "sire-code-reviewer-b": "R6",
    "sire-code-reviewer-c": "R6", "sire-qa-tester": "R7", "sire-integrator": "R8", "sire-supervisor": "R9",
    "sire-system-operator": "R10", "sire-low": "tier-low", "sire-mid": "tier-mid", "sire-high": "tier-high",
}


def expected_clients() -> set[str]:
    out: set[str] = set()
    for path in CLIENT_CONFIGS:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        out.update(m.group(1).lower() for m in CLIENT_RE.finditer(text))
    return out


def check_missing_hooks(c: sqlite3.Connection, now: float) -> None:
    """库里采过事件的客户端，配置里却已没有遥测钩子（被其他安装脚本覆盖）：COLLECTION_DEAD 只看配置里还在的客户端，
    漏掉了这种情况，所以单独核对一次。"""
    configured = expected_clients()
    for (client,) in c.execute("SELECT DISTINCT client FROM events WHERE client IS NOT NULL").fetchall():
        if client in configured:
            continue
        fid = f"HOOK_MISSING:{client}"
        if c.execute("SELECT 1 FROM findings WHERE finding_id=?", (fid,)).fetchone():
            continue
        item = {"client": client, "at": round(now), "evidence": "配置文件中找不到 sire_telemetry.py hook 钩子"}
        c.execute("INSERT INTO findings(finding_id,rule,status,hits,first_seen,last_seen,evidence,suggestion) "
                  "VALUES(?,?,?,?,?,?,?,?)",
                  (fid, "HOOK_MISSING", "PROPOSED", 1, now, now,
                   json.dumps([item], ensure_ascii=False), RULES["HOOK_MISSING"][1]))


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
            c.execute("INSERT INTO findings(finding_id,rule,status,hits,first_seen,last_seen,evidence,suggestion) "
                      "VALUES(?,?,?,?,?,?,?,?)",
                      (fid, "COLLECTION_DEAD", "PROPOSED", 1, now, now,
                       json.dumps([item], ensure_ascii=False), RULES["COLLECTION_DEAD"][1]))
            continue
        # 已知并接受的忽略项不再重开；已修复的发现再次断流记为回归，而不是倒退成新提案
        if row["status"] == "IGNORED" and row["ignore_kind"] == "accepted":
            continue
        if row["status"] in ("PROPOSED", "REGRESSED"):
            status = row["status"]
        else:
            status = "REGRESSED" if row["status"] == "FIXED" else "PROPOSED"
        evidence = (json.loads(row["evidence"] or "[]") + [item])[-10:]
        c.execute("UPDATE findings SET status=?,hits=?,last_seen=?,evidence=? WHERE finding_id=?",
                  (status, (row["hits"] or 0) + 1, now, json.dumps(evidence, ensure_ascii=False), fid))

DECAY_SECONDS = 30 * 86400  # 30 天没再出现才清零计数（原 7 天过短，低频问题永远攒不够）

SECRET_PATTERNS = (
    re.compile(r"(?i)(token|password|passwd|secret|api[_-]?key|authorization|bearer)([\"'=: ]+)(?:bearer\s+)?[^\s\"',;]+"),
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
    cols = {r[1] for r in c.execute("PRAGMA table_info(findings)")}
    for name in ("ignore_kind TEXT", "hits_at_ignore INTEGER"):
        if name.split()[0] not in cols:
            c.execute(f"ALTER TABLE findings ADD COLUMN {name}")
    ecols = {r[1] for r in c.execute("PRAGMA table_info(events)")}
    for name in ("tuid TEXT", "role TEXT"):
        if name.split()[0] not in ecols:
            c.execute(f"ALTER TABLE events ADD COLUMN {name}")
    c.execute("UPDATE findings SET hits_at_ignore=hits WHERE status='IGNORED' AND hits_at_ignore IS NULL")
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


def reply_lacks_usage(text: str) -> bool:
    """完整流程回复（含“快速通道：否”，全角或半角冒号）缺“耗时”或“额度消耗”。门禁与遥测共用。"""
    return bool(re.search(r"快速通道[：:]\s*否", text)) and not ("耗时" in text and "额度消耗" in text)


def detect_mode(text: str) -> str:
    text = re.sub(r"快速通道[：:]\s*", "快速通道：", text)  # 兼容半角冒号与冒号后空格，与 reply_lacks_usage 一致
    fast, full = text.rfind(FAST_MARK), text.rfind(FULL_MARK)
    if fast < 0 and full < 0:
        return "unknown"
    return "fast" if fast > full else "full"


def infer_mode(counts: dict, total: float, tool_calls: int) -> str:
    """回复里没有"快速通道"标记时按行为推断：用过 SIRE 阶段（检索/台账/归档/RSI/子代理/提交/读规则）即完整流程；
    工具调用很少且很短才算简单任务；其余仍是 unknown（纯对话等）。原先这类任务占 73%，几乎不进入检测。"""
    if any(counts.get(p) for p in FAST_FORBIDDEN + ("rules",)):
        return "full"
    if tool_calls <= 3 and total <= 60:
        return "fast"
    return "unknown"


def role_of(agent_type: str) -> str:
    """子代理类型 → 角色标签；空表示主控。"""
    if not agent_type:
        return "main"
    base = ROLE_MAP.get(agent_type)
    return f"{base}:{agent_type}" if base else agent_type


def timeline(rows, start: float) -> list[dict]:
    """把事件还原成逐步耗时：每步的间隔拆成思考/执行/暂停/未拆分，四者之和等于相邻事件的时间差。
    pre 事件（PreToolUse）给出工具开始时刻；notify 事件里的权限确认记为暂停起点；二者都不进入步骤本身。"""
    last, steps, pres, notes = start, [], [], []
    for r in rows:
        ts, ev = r["ts"], r["event"]
        if ts < start or ev == "prompt":
            continue
        if ev == "pre":
            pres.append((ts, r["tool"] or "", r["tuid"] or ""))
            continue
        if ev == "notify":
            if "permission" in (r["detail"] or "").lower():
                notes.append(ts)
            continue
        if ev not in ("tool", "stop"):
            continue
        gap = max(0.0, ts - last)
        think = run = pause = unsplit = 0.0
        tool = r["tool"] or ""
        if ev == "stop":
            think = gap  # 最后一次工具之后到停止：模型生成最终回复
        else:
            hit = None
            for i in range(len(pres) - 1, -1, -1):
                if (r["tuid"] and pres[i][2] == r["tuid"]) or (not r["tuid"] and pres[i][1] == tool):
                    hit = pres.pop(i)
                    break
            if hit is None:
                unsplit = gap
            else:
                think = max(0.0, min(hit[0], ts) - last)
                rest = gap - think
                if tool.lower() in PAUSE_TOOLS:
                    pause = rest
                else:
                    begin = max(hit[0], last)
                    marks = [n for n in notes if begin <= n <= ts]
                    pause = min(rest, ts - max(marks)) if marks else 0.0
                    run = rest - pause
        phase = "reply" if ev == "stop" else r["phase"]
        steps.append({"phase": phase, "role": r["role"] or "main", "think": think, "exec": run, "pause": pause,
                      "unsplit": unsplit, "gap": gap, "event": ev, "tool": tool, "detail": r["detail"] or "",
                      "ok": r["ok"]})
        last = ts
    return steps


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
    split = {"think": 0.0, "exec": 0.0, "pause": 0.0, "unsplit": 0.0}
    roles: dict[str, dict] = {}
    tool_calls = failures = 0
    for st in timeline(rows, start):
        phases[st["phase"]] = phases.get(st["phase"], 0.0) + st["gap"]
        ro = roles.setdefault(st["role"], {"think": 0.0, "exec": 0.0, "pause": 0.0, "unsplit": 0.0, "calls": 0})
        for k in split:
            split[k] += st[k]
            ro[k] += st[k]
        if st["event"] == "tool":
            tool_calls += 1
            counts[st["phase"]] = counts.get(st["phase"], 0) + 1
            ro["calls"] += 1
            failures += 0 if st["ok"] else 1
    task_id = f"{session}:{start:.3f}"
    inferred = False
    if mode == "unknown":
        mode = infer_mode(counts, stop_ts - start, tool_calls)
        inferred = mode != "unknown"
    summary = {"seconds": {k: round(v, 1) for k, v in phases.items()}, "calls": counts, "inferred": inferred,
               "split": {k: round(v, 1) for k, v in split.items()},
               "roles": {k: {a: (round(b, 1) if a != "calls" else b) for a, b in v.items()} for k, v in roles.items()}}
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
        role = role_of(str(payload.get("agent_type") or ""))
        tuid = str(payload.get("tool_use_id") or "")
        ts = time.time()
        c = connect()
        with c:
            if event == "UserPromptSubmit":
                c.execute("INSERT INTO events(ts,client,session,event,detail,ok) VALUES(?,?,?,?,?,1)",
                          (ts, args.client, session, "prompt", redact(str(payload.get("prompt") or ""), 60)))
            elif event == "PreToolUse":
                tool = str(payload.get("tool_name") or "")
                c.execute("INSERT INTO events(ts,client,session,event,tool,phase,ok,agent,tuid,role) "
                          "VALUES(?,?,?,?,?,?,1,?,?,?)",
                          (ts, args.client, session, "pre", tool, "", agent, tuid, role))
            elif event == "Notification":
                note = str(payload.get("notification_type") or payload.get("message") or "")
                c.execute("INSERT INTO events(ts,client,session,event,detail,ok) VALUES(?,?,?,?,?,1)",
                          (ts, args.client, session, "notify", redact(note, 60)))
            elif event in ("PostToolUse", "PostToolUseFailure"):
                tool = str(payload.get("tool_name") or "")
                tool_input = payload.get("tool_input")
                # 子代理内部的工具调用整体算作子代理阶段
                phase = "subagent" if agent else classify(tool, tool_input)
                detail = redact(json.dumps(tool_input, ensure_ascii=False), 320)
                # Qoder 单独发 PostToolUseFailure，比猜 tool_response 字段可靠
                ok = 0 if event == "PostToolUseFailure" or tool_failed(payload.get("tool_response")) else 1
                c.execute("INSERT INTO events(ts,client,session,event,tool,phase,detail,ok,agent,tuid,role) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (ts, args.client, session, "tool", tool, phase, detail, ok, agent, tuid, role))
            elif event == "Stop":
                mode = detect_mode(last_assistant_text(payload))
                c.execute("INSERT INTO events(ts,client,session,event,detail,ok) VALUES(?,?,?,?,?,1)",
                          (ts, args.client, session, "stop", mode))
                reply = last_assistant_text(payload)
                # Claude 端首次 Stop 会被 sire_gate 拦住补写，补写后的回复不应留下发现；
                # 所以只在“已被拦过仍缺”(stop_hook_active) 或没有该拦截的客户端才记
                if mode == "full" and reply_lacks_usage(reply) and (
                        payload.get("stop_hook_active") or args.client != "claude"):
                    # 完整流程的最终回复必须自带耗时与额度消耗；缺失记为质量事件，由下次 R9 处理
                    c.execute("INSERT INTO events(ts,client,session,event,detail,ok) VALUES(?,?,?,?,?,0)",
                              (ts, args.client, session, "usage_missing", "最终回复缺耗时/额度消耗"))
                summarize_task(c, args.client, session, ts, mode, str(payload.get("cwd") or ""))
        c.close()
        if event == "Stop":
            spawn_analyze()
    except Exception:
        pass  # 遥测失败不能影响客户端
    return 0


# ---------------------------------------------------------------- 分析

def detect_quality(task, events) -> list[tuple[str, str, str]]:
    """质量类规则：用户纠正、违反硬规则、门禁/复核/通讯反复失败。events 为该任务窗口内的事件行。"""
    out = []
    prompt = task["prompt"] or ""
    if CORRECTION_RE.search(prompt):
        out.append(("USER_CORRECTION", "USER_CORRECTION", prompt[:40]))
    tools = [e for e in events if e["event"] == "tool"]
    if any(e["event"] == "usage_missing" for e in events):
        out.append(("USAGE_MISSING", "USAGE_MISSING", "完整流程最终回复缺耗时/额度消耗"))
    for e in tools:
        if VIOLATION_RE.search(e["detail"] or ""):
            out.append(("RULE_VIOLATION", "RULE_VIOLATION", (e["detail"] or "")[:80]))
            break
    gate = [e for e in tools if not e["ok"] and GATE_RE.search(e["detail"] or "")]
    if len(gate) >= 2:
        out.append(("GATE_BLOCK", "GATE_BLOCK", f"sire_run.py 失败 {len(gate)} 次"))
    review = [e for e in tools if REVIEW_FAIL_RE.search(e["detail"] or "")]
    if len(review) >= 2:
        out.append(("REVIEW_FAIL", "REVIEW_FAIL", f"复核/测试 FAIL {len(review)} 次"))
    comms = [e for e in tools if not e["ok"] and COMMS_RE.search(e["detail"] or "")]
    if len(comms) >= 2:
        out.append(("COMMS_FAIL", "COMMS_FAIL", f"sire_comms.py 失败 {len(comms)} 次"))
    return out


def detect(task: sqlite3.Row, history: list[sqlite3.Row], events=()) -> list[tuple[str, str, str]]:
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
    out.extend(detect_quality(task, events))
    return out


def record_finding(c: sqlite3.Connection, fid: str, rule: str, evidence: str, task: sqlite3.Row, now: float):
    need, suggestion = RULES[rule]
    row = c.execute("SELECT * FROM findings WHERE finding_id=?", (fid,)).fetchone()
    item = {"task": task["task_id"], "client": task["client"], "at": round(task["end_ts"]), "evidence": evidence}
    if row is None:
        status = "PROPOSED" if need <= 1 else "OPEN"
        c.execute("INSERT INTO findings(finding_id,rule,status,hits,first_seen,last_seen,evidence,suggestion) "
                  "VALUES(?,?,?,?,?,?,?,?)",
                  (fid, rule, status, 1, now, now, json.dumps([item], ensure_ascii=False), suggestion))
        return
    if row["status"] == "IGNORED":
        hits = (row["hits"] or 0) + 1
        evidence_list = (json.loads(row["evidence"] or "[]") + [item])[-10:]
        if row["ignore_kind"] == "accepted":  # 已知并接受：只计数，不再提醒
            c.execute("UPDATE findings SET hits=?,last_seen=? WHERE finding_id=?", (hits, now, fid))
            return
        grown = hits - (row["hits_at_ignore"] or 0)
        aged = grown > 0 and now - (row["resolved_at"] or now) > REVIVE_SECONDS
        if grown >= max(need * 2, 4) or aged:
            c.execute("UPDATE findings SET status='PROPOSED',hits=?,last_seen=?,evidence=?,ignore_kind=NULL,"
                      "resolved_at=NULL,note=? WHERE finding_id=?",
                      (hits, now, json.dumps(evidence_list, ensure_ascii=False),
                       f"复活：忽略后又命中 {grown} 次（原忽略理由：{(row['note'] or '')[:60]}）", fid))
        else:
            c.execute("UPDATE findings SET hits=?,last_seen=?,evidence=? WHERE finding_id=?",
                      (hits, now, json.dumps(evidence_list, ensure_ascii=False), fid))
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


# ---------------------------------------------------------------- 时间自我分析

DIGEST_STATE = DB_PATH.parent / "telemetry_digest.json"
DIGEST_MD = DB_PATH.parent / "telemetry_digest.md"


def task_timeline(c: sqlite3.Connection, task) -> list[dict]:
    """还原任务的逐步耗时（含思考/执行/暂停拆分），口径与 summarize_task 相同。"""
    rows = c.execute("SELECT * FROM events WHERE session=? AND ts>? AND ts<=? ORDER BY ts, id",
                     (task["session"], task["start_ts"] - 0.001, task["end_ts"])).fetchall()
    return timeline(rows, task["start_ts"])


def explain(a: dict) -> str:
    """按阶段统计推断耗时成因，给出可执行的优化方向。"""
    n, sec = a["calls"], a["sec"]
    if n == 0:
        return "无工具调用，耗时来自模型输出/思考或等待用户，优先看是否能少写、少想"
    avg = sec / n
    top = max(a["slow"]) if a["slow"] else (0, "", "")
    if a["fail"] >= 3 and a["fail"] / n >= 0.2:
        return f"失败重试多（{a['fail']}/{n} 次失败）：把正确用法写进规则或脚本报错提示"
    if top[0] >= 60 and top[0] >= 0.3 * sec:
        return f"被单个长步骤主导（{top[0]:.0f}s：{top[1]} {top[2]}）：检查该命令是否可提速、拆分或后台化"
    if n >= 30 and avg < 15:
        return f"调用碎片化（{n} 次、平均 {avg:.0f}s）：合并成一条脚本命令，减少模型轮次"
    return f"单次平均 {avg:.0f}s（{n} 次）偏高，多为模型思考或长命令等待：考虑降级模型、简化规则或预先缓存"


def build_diagnosis(c: sqlite3.Connection, days: float = DIAG_DAYS, client: str | None = None,
                    last: int | None = None) -> dict:
    """汇总完整流程任务的阶段耗时：各阶段占比、调用数、失败数、成因。"""
    since = time.time() - days * 86400
    sql = "SELECT * FROM tasks WHERE end_ts>=? AND mode='full' AND total_s>=60"
    args: list = [since]
    if client:
        sql += " AND client=?"
        args.append(client)
    sql += " ORDER BY end_ts DESC" + (f" LIMIT {int(last)}" if last else "")
    tasks = c.execute(sql, args).fetchall()
    agg: dict[str, dict] = {}
    split = {"think": 0.0, "exec": 0.0, "pause": 0.0, "unsplit": 0.0}
    roles: dict[str, dict] = {}
    total = 0.0
    for t in tasks:
        total += t["total_s"] or 0
        for st in task_timeline(c, t):
            a = agg.setdefault(st["phase"], {"sec": 0.0, "calls": 0, "fail": 0, "slow": []})
            a["sec"] += st["gap"]
            ro = roles.setdefault(st["role"], {"sec": 0.0, "calls": 0, "think": 0.0, "exec": 0.0, "pause": 0.0,
                                               "unsplit": 0.0})
            ro["sec"] += st["gap"]
            for k in split:
                split[k] += st[k]
                ro[k] += st[k]
            if st["event"] == "tool":
                a["calls"] += 1
                ro["calls"] += 1
                a["fail"] += 0 if st["ok"] else 1
                a["slow"].append((st["gap"], st["tool"], st["detail"][:60]))
    rows = []
    for phase, a in sorted(agg.items(), key=lambda kv: -kv[1]["sec"]):
        rows.append({"phase": phase, "sec": round(a["sec"], 1), "share": a["sec"] / total if total else 0,
                     "calls": a["calls"], "fail": a["fail"], "cause": explain(a)})
    role_rows = [{"role": k, "sec": round(v["sec"], 1), "share": v["sec"] / total if total else 0, "calls": v["calls"],
                  "think": round(v["think"], 1), "exec": round(v["exec"], 1), "pause": round(v["pause"], 1),
                  "unsplit": round(v["unsplit"], 1)} for k, v in sorted(roles.items(), key=lambda kv: -kv[1]["sec"])]
    tracked = split["think"] + split["exec"] + split["pause"]
    overhead = sum(r["share"] for r in rows if r["phase"] in OVERHEAD_PHASES)
    return {"days": days, "tasks": len(tasks), "total_s": round(total, 1), "overhead_share": overhead, "phases": rows,
            "split": {k: round(v, 1) for k, v in split.items()}, "split_coverage": tracked / total if total else 0,
            "roles": role_rows}


def render_diagnosis(d: dict) -> str:
    lines = [f"# SIRE 时间自我分析（近 {d['days']:g} 天，完整流程 {d['tasks']} 个任务，共 {d['total_s'] / 3600:.1f} 小时）", "",
             f"SIRE 流程开销（{'、'.join(OVERHEAD_PHASES)}）占 {d['overhead_share']:.0%}；"
             f"execute/reply 是兜底桶，随任务规模浮动。", "",
             "| 阶段 | 耗时(s) | 占比 | 调用 | 失败 | 成因与建议 |", "|---|---|---|---|---|---|"]
    for r in d["phases"]:
        mark = "" if r["phase"] in OVERHEAD_PHASES else "（兜底）" if r["phase"] in CATCH_ALL_PHASES else ""
        lines.append(f"| {r['phase']}{mark} | {r['sec']:.0f} | {r['share']:.0%} | {r['calls']} | {r['fail']} | {r['cause']} |")
    sp = d.get("split") or {}
    tracked = sp.get("think", 0) + sp.get("exec", 0) + sp.get("pause", 0)
    lines += ["", f"## 时间拆分（已拆分覆盖 {d.get('split_coverage', 0):.0%}；其余客户端没有 Pre 事件，记为未拆分）", "",
              "| 思考 | 执行 | 暂停 | 未拆分 |", "|---|---|---|---|",
              f"| {sp.get('think', 0):.0f}s ({sp.get('think', 0) / tracked:.0%}) | {sp.get('exec', 0):.0f}s "
              f"({sp.get('exec', 0) / tracked:.0%}) | {sp.get('pause', 0):.0f}s ({sp.get('pause', 0) / tracked:.0%}) "
              f"| {sp.get('unsplit', 0):.0f}s |" if tracked else "| - | - | - | - |"]
    lines += ["", "## 角色耗时（main=主控；R1–R10/tier-* 为子代理）", "",
              "| 角色 | 耗时(s) | 占比 | 调用 | 思考 | 执行 | 暂停 | 未拆分 |", "|---|---|---|---|---|---|---|---|"]
    for r in d.get("roles", []):
        lines.append(f"| {r['role']} | {r['sec']:.0f} | {r['share']:.0%} | {r['calls']} | {r['think']:.0f} | "
                     f"{r['exec']:.0f} | {r['pause']:.0f} | {r['unsplit']:.0f} |")
    return "\n".join(lines) + "\n"


def record_diagnosis_findings(c: sqlite3.Connection, d: dict, now: float) -> None:
    """把诊断结果转成待处理发现：开销总占比过高，或单个开销阶段占比过高。"""
    if d["tasks"] < DIAG_MIN_TASKS:
        return
    pseudo = {"task_id": f"digest:{time.strftime('%F', time.localtime(now))}", "client": "all", "end_ts": now}
    cands = []
    if d["overhead_share"] >= OVERHEAD_LIMIT:
        top = next((r for r in d["phases"] if r["phase"] in OVERHEAD_PHASES), None)
        why = f"；最大项 {top['phase']} {top['share']:.0%}：{top['cause']}" if top else ""
        cands.append(("OVERHEAD_HIGH", "OVERHEAD_HIGH", f"开销占 {d['overhead_share']:.0%}（{d['tasks']} 个任务）{why}"))
    for r in d["phases"]:
        if r["phase"] in OVERHEAD_PHASES and r["share"] >= PHASE_SHARE_LIMIT:
            cands.append((f"PHASE_SHARE:{r['phase']}", "PHASE_SHARE", f"{r['phase']} 占 {r['share']:.0%}：{r['cause']}"))
    sp = d.get("split") or {}
    tracked = sp.get("think", 0) + sp.get("exec", 0) + sp.get("pause", 0)
    if tracked and d.get("split_coverage", 0) >= SPLIT_COVERAGE_MIN:
        if sp["pause"] / tracked >= PAUSE_LIMIT:
            cands.append(("PAUSE_HIGH", "PAUSE_HIGH",
                          f"暂停占已拆分时间 {sp['pause'] / tracked:.0%}（{sp['pause']:.0f}s / {tracked:.0f}s）"))
        if sp["think"] / tracked >= THINK_LIMIT:
            cands.append(("THINK_HIGH", "THINK_HIGH",
                          f"模型思考占已拆分时间 {sp['think'] / tracked:.0%}（{sp['think']:.0f}s / {tracked:.0f}s）"))
    for r in d.get("roles", []):
        if r["role"] != "main" and r["share"] >= ROLE_LIMIT:
            cands.append((f"ROLE_HEAVY:{r['role']}", "ROLE_HEAVY", f"{r['role']} 占完整任务时间 {r['share']:.0%}"))
    for fid, rule, evidence in cands:
        row = c.execute("SELECT status,resolved_at FROM findings WHERE finding_id=?", (fid,)).fetchone()
        if row and row["status"] == "FIXED" and now - (row["resolved_at"] or 0) < 7 * 86400:
            continue  # 刚修复，窗口里还是修复前的数据，给 7 天观察期
        record_finding(c, fid, rule, evidence, pseudo, now)


def maybe_digest(c: sqlite3.Connection, now: float, force: bool = False) -> dict | None:
    """每 24 小时自动做一次时间诊断：写 telemetry_digest.md 并转成发现；失败不影响 analyze。"""
    try:
        last = json.loads(DIGEST_STATE.read_text(encoding="utf-8")).get("ts", 0) if DIGEST_STATE.exists() else 0
        if not force and now - last < DIGEST_INTERVAL:
            return None
        d = build_diagnosis(c)
        record_diagnosis_findings(c, d, now)
        DIGEST_MD.write_text(render_diagnosis(d), encoding="utf-8")
        DIGEST_STATE.write_text(json.dumps({"ts": now}), encoding="utf-8")
        return d
    except Exception:
        return None


def cmd_diagnose(args) -> int:
    c = connect()
    with c:
        d = build_diagnosis(c, args.days, args.client, args.last)
        if args.record:
            record_diagnosis_findings(c, d, time.time())
            DIGEST_MD.write_text(render_diagnosis(d), encoding="utf-8")
            DIGEST_STATE.write_text(json.dumps({"ts": time.time()}), encoding="utf-8")
    c.close()
    print(json.dumps(d, ensure_ascii=False, indent=2) if args.json else render_diagnosis(d))
    return 0


def cmd_analyze(args) -> int:
    c = connect()
    now = time.time()
    with c:
        pending = c.execute("SELECT * FROM tasks WHERE analyzed=0 ORDER BY end_ts").fetchall()
        for task in pending:
            history = c.execute("SELECT * FROM tasks WHERE analyzed=1 AND end_ts<? ORDER BY end_ts DESC LIMIT 30",
                                (task["end_ts"],)).fetchall()
            events = c.execute("SELECT * FROM events WHERE session=? AND ts>? AND ts<=? ORDER BY ts, id",
                               (task["session"], task["start_ts"] - 0.001, task["end_ts"])).fetchall()
            for fid, rule, evidence in detect(task, history, events):
                record_finding(c, fid, rule, evidence, task, now)
            c.execute("UPDATE tasks SET analyzed=1 WHERE task_id=?", (task["task_id"],))
        check_clients(c, now, args.stale_hours * 3600)
        check_missing_hooks(c, now)
        maybe_digest(c, now)
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
        sp = it.get("split") or {}
        cut = (f" | 思考{sp['think']:.0f}s 执行{sp['exec']:.0f}s 暂停{sp['pause']:.0f}s 未拆分{sp['unsplit']:.0f}s"
               if sp else "")
        print(f"{it['start']} {it['client']:<6} {it['mode']:<7} 总计 {it['total_s']:.0f}s | {parts}{cut} | {it['prompt']}")
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
        row = c.execute("SELECT status,hits FROM findings WHERE finding_id=?", (args.finding,)).fetchone()
        if row is None:
            print(f"发现 {args.finding} 不存在", file=sys.stderr)
            return 2
        if args.proposal:
            c.execute("UPDATE findings SET status='FIXED',hits=0,proposal_id=?,resolved_at=?,note=NULL,"
                      "ignore_kind=NULL WHERE finding_id=?", (args.proposal, time.time(), args.finding))
        elif args.ignore:
            c.execute("UPDATE findings SET status='IGNORED',resolved_at=?,note=?,ignore_kind=?,hits_at_ignore=? "
                      "WHERE finding_id=?", (time.time(), args.ignore, "accepted" if args.accepted else "irrelevant",
                                             row["hits"] or 0, args.finding))
        else:
            c.execute("UPDATE findings SET status='OPEN',hits=0,resolved_at=NULL,ignore_kind=NULL "
                      "WHERE finding_id=?", (args.finding,))
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
    s.add_argument("--accepted", action="store_true",
                   help="配合 --ignore：已知并接受，永不复活；不加则按“与本次任务无关”处理，同类命中累计后会复活")
    dg = sub.add_parser("diagnose", help="时间自我分析：各阶段占比与成因；--record 同时转成待处理发现")
    dg.add_argument("--days", type=float, default=DIAG_DAYS)
    dg.add_argument("--client", choices=("claude", "codex", "qoder"))
    dg.add_argument("--last", type=int, help="只看最近 N 个完整任务")
    dg.add_argument("--record", action="store_true")
    dg.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd != "hook":
        # 中文输出固定 UTF-8，避免在 GBK 控制台里乱码
        sys.stdout.reconfigure(encoding="utf-8")
    return {"hook": cmd_hook, "analyze": cmd_analyze, "report": cmd_report,
            "pending": cmd_pending, "resolve": cmd_resolve, "diagnose": cmd_diagnose}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
