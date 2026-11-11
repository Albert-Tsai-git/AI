#!/usr/bin/env python
"""SIRE 工作流定时健康检查（RSI 自我优化机制的一部分，用户 2026-11-11 定：每 8 小时，0 点/8 点/16 点）。

流程：检查 → 收集异常 → 分析成因与优化方向 → 记入遥测发现 → 持续或严重的异常由“工作流自己”生成 RSI 提案草案。
原则（用户定）：提案由工作流自己分析并提出，用户来确定；本脚本只生成状态为 PROPOSED 的草案，永远不评估、不激活、不改工作流文件。

用法：
  python sire_health.py run [--record] [--json] [--no-proposal]   执行一次检查（--record 才写发现与提案草案、保存报告）
  python sire_health.py last                                         打印最近一次报告
  python sire_health.py install-task / uninstall-task / task-status  注册/移除/查看 Windows 计划任务（0/8/16 点）
  python sire_health.py due [--hours 9]                              距上次检查是否已超时（退出码 0=已超时）
所有检查彼此独立：单项检查自身出错只记入“检查错误”，不影响其他项，也不会被误判为“已恢复”。
输出落在 ledger 目录 health/，不进业务项目、不进 Git。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from sire_paths import DATA_DIR, LEDGER_ROOT, SHARED_SKILL_DIR, archive_database_path  # noqa: E402
from sire_process import no_console_kwargs  # noqa: E402

HEALTH_DIR = LEDGER_ROOT / "health"
QUEUE = LEDGER_ROOT / "sync_queue"
LOGS = LEDGER_ROOT / "sync_logs"
GATE_DIR = LEDGER_ROOT / "gate"
TELEMETRY_DB = Path(os.environ.get("SIRE_TELEMETRY_DB") or DATA_DIR / "sire_telemetry.sqlite3")
REPO_DB = DATA_DIR / "sire_vectors.sqlite3"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
SKILL_LINK = Path.home() / ".claude" / "skills" / "sire-global-workflow"
BACKUP_DIR = Path(os.environ.get("SIRE_DB_BACKUP_DIR") or "D:/sire/db-backups")
TASK_NAME = "SIRE-RSI-Health"
SCHEDULE_TIMES = ("00:00", "08:00", "16:00")  # 用户定：0 点、8 点、16 点
INTERVAL_HOURS = 8
WINDOW_SECONDS = INTERVAL_HOURS * 3600   # 事件类检查只看一个周期内新发生的
SUSTAINED_RUNS = 2                       # 连续出现这么多个“周期”才算持续异常
MIN_RUN_GAP = 4 * 3600                   # 相隔不足 4 小时的运行算同一个周期（手工多跑、补跑不能把异常提前算成持续）
KEEP_REPORTS = 30
RUN_LOCK_STALE = 65 * 60                 # 运行互斥锁的过期时间：必须大于计划任务的执行时限（60 分钟）
DRAFT_COOLDOWN = 7 * 86400               # 同一异常代码 7 天内只生成一次提案草案，不管上一份草案被用户怎样处理
MAX_DRAFTS_PER_RUN = 2                   # 每次运行最多生成几份草案（每份 propose 会整库备份，限量保护磁盘）
LOG_TAIL_BYTES = 1024 * 1024             # 日志只读末尾 1MB
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# 只提示、不自动成提案、也不阻塞收尾的异常：它们要么是正常开发中的瞬时状态，要么只是转述已有发现、要么需要用户直接决定
INFO_CODES = frozenset({"WORKFLOW_UNCOMMITTED", "TELEMETRY_FINDINGS_OPEN", "RSI_STALE_PROPOSALS"})

# 检查名 → 它可能产出的异常代码。某项检查本次出错时，它负责的代码不能被误判为“已恢复”。
CHECK_CODES = {
    "归档配置": {"ARCHIVE_UNCONFIGURED"},
    "归档队列": {"ARCHIVE_INVALID_JOBS", "ARCHIVE_QUEUE_STUCK", "ARCHIVE_LOCK_STALE"},
    "归档日志": {"ARCHIVE_WORKER_FAILURES"},
    "门禁异常": {"GATE_ERRORS"},
    "遥测发现": {"COLLECTION_DEAD", "TELEMETRY_FINDINGS_OPEN", "USAGE_MISSING_RECENT"},
    "RSI 状态": {"RSI_STALE_PROPOSALS"},
    "工作流 Git": {"RSI_HASH_DRIFT", "WORKFLOW_UNCOMMITTED"},
    "版本一致": {"VERSION_MISMATCH"},
    "钩子与技能链接": {"HOOKS_MISSING", "SKILL_LINK_BROKEN"},
    "资源": {"DISK_LOW", "BACKUPS_LARGE", "DB_WAL_LARGE"},
}

# 异常代码 → 成因、优化方向、提案草案模板（标题、假设、改动）。分析由工作流自己完成，不依赖助手临场判断。
KNOWLEDGE = {
    "ARCHIVE_UNCONFIGURED": ("机器级归档库未配置或文件不存在，后台归档全部失败。",
                              "确认 SIRE_ARCHIVE_DB 用户级环境变量、settings.json 的 env 与 sire_paths 回退路径三处一致。",
                              "修复归档库配置", "归档库路径解析失败会让所有归档任务停摆", "核对并统一三处归档库配置，并让 sire_paths 在不可用时给出明确报错"),
    "ARCHIVE_QUEUE_STUCK": ("归档任务长时间停留在队列，worker 没有跑、被锁住或反复失败。",
                             "检查 worker.lock 与失败原因；把长期失败的任务按原因分类处理，避免重复占用批次。",
                             "清理停滞的归档队列", "队列任务长时间不完成说明 worker 或任务本身存在持续问题", "按失败原因分类处理停滞任务，并在 worker 里为长期失败的任务设置隔离"),
    "ARCHIVE_INVALID_JOBS": ("队列里有指向不存在的运行目录的任务，永远不可能成功。",
                              "入队时校验 run.json 存在；对已失效的任务自动移入隔离目录而不是留在队列。",
                              "自动隔离无效归档任务", "无效任务会被每次重试并制造噪声", "worker 预检发现 run.json 缺失连续多次后，把任务移入 sync_queue_invalid 并记录"),
    "ARCHIVE_LOCK_STALE": ("worker 锁存在但持有进程已退出，后续归档会被挡住。",
                            "遗留锁应被新 worker 接管；检查是否有崩溃或被强杀的 worker。",
                            "遗留归档锁处理", "遗留锁会阻塞归档队列", "确认锁接管逻辑生效，必要时在健康检查里自动清理已确认失效的锁"),
    "ARCHIVE_WORKER_FAILURES": ("归档 worker 日志在本周期内出现失败。",
                                 "按失败信息归类（库被占用、超时、校验不一致），对高频原因加针对性重试或前置检查。",
                                 "降低归档失败率", "worker 日志持续出现失败", "对高频失败原因加前置检查和差异化重试"),
    "GATE_ERRORS": ("门禁钩子自身出现异常（已按 fail-open 放行），门禁脚本或状态目录可能有问题。",
                     "查看 gate/error.log 的异常类型，修复后补单测；持续出现会削弱门禁。",
                     "修复门禁钩子自身异常", "门禁异常被 fail-open 吞掉后不会被发现", "为门禁异常增加告警并补单测"),
    "TELEMETRY_FINDINGS_OPEN": ("遥测发现里有长期未处理的优化项（本项只转述已有发现，不单独生成提案）。",
                                 "按命中次数排序，由用户决定逐条处理、合并为提案或标记为已知取舍。",
                                 "清理堆积的遥测发现", "未处理发现越积越多会稀释真正的问题", "对高命中发现按“先合并再激活”规则合并为提案"),
    "COLLECTION_DEAD": ("某客户端的遥测采集断流（有钩子配置但长时间没有事件）。",
                         "检查该客户端钩子配置与脚本路径；采集断流会让所有自动分析失明。",
                         "恢复遥测采集", "采集断流时自我优化机制无法获得数据", "核对钩子配置并在断流时提示用户重启客户端"),
    "USAGE_MISSING_RECENT": ("本周期内有完整流程回复缺少耗时或额度消耗（已被拦过仍缺）。",
                              "检查 Stop 钩子是否被禁用、回复是否绕过 sire_usage.py --final。",
                              "巩固耗时与额度记录", "耗时额度记录靠自觉会反复遗漏", "把 --plan-mark 与 --stage 计时在提示词提交时自动记录"),
    "RSI_HASH_DRIFT": ("当前生效版本登记的配置哈希与 Git 当前内容不一致，工作流被改动或回退过（刚提交、尚未登记时是瞬时状态）。",
                        "若连续出现，核对是否有未登记的改动；必要时重新登记提案并评估。",
                        "对齐 RSI 生效版本与 Git", "生效版本与实际工作流内容漂移", "在提交后自动校验配置哈希并提示重新登记"),
    "WORKFLOW_UNCOMMITTED": ("工作流目录有未提交的改动（开发过程中是正常状态，仅提示）。",
                              "确认这些改动是否都有对应的 RSI 记录；长期不提交会造成版本与代码不一致。",
                              "处理未提交的工作流改动", "未提交改动长期存在", "提示用户提交或登记对应提案"),
    "RSI_STALE_PROPOSALS": ("有提案长期停在待评估或待激活状态，需要用户决定（本项不自动生成提案）。",
                             "由用户决定激活、合并或回退；合并规则见合同“先合并再激活”。",
                             "清理停滞的 RSI 提案", "停滞提案会让版本链混乱", "按“先合并再激活”规则合并或回退停滞提案"),
    "VERSION_MISMATCH": ("入口提醒显示的版本与 RSI 当前生效版本不一致。",
                          "检查 sire_remind.py 取版本的数据库与路径；所有会话的声明行版本会因此出错。",
                          "修复入口提醒版本来源", "声明行版本与生效版本不一致", "让入口提醒版本只读取生效版本并加一致性检查"),
    "HOOKS_MISSING": ("客户端 settings.json 缺少 SIRE 必需的钩子。",
                       "补回缺失的钩子；缺失会让门禁、遥测或 Stop 拦截整体失效。",
                       "补回缺失的 SIRE 钩子", "必需钩子缺失导致机制失效", "提供一条命令检查并补全全部必需钩子"),
    "SKILL_LINK_BROKEN": ("客户端技能目录没有指向共享的 SIRE 正本。",
                           "重新建立指向仓库正本的链接，禁止保留第二份可写副本。",
                           "修复技能目录链接", "技能链接失效会让会话加载旧规则或找不到技能", "安装脚本自动校验并重建链接"),
    "DISK_LOW": ("磁盘剩余空间偏低，归档与数据库备份可能失败。",
                  "清理旧备份与无用的运行目录；调整备份保留策略。",
                  "释放磁盘空间", "磁盘不足会让数据库备份与归档失败", "按空间占用调整备份保留数量并自动清理旧备份"),
    "BACKUPS_LARGE": ("数据库备份目录占用偏大。",
                       "确认保留数量；整库备份体积大，频繁写库会放大占用。",
                       "控制数据库备份占用", "每次写库都生成整库备份", "合并短时间内的多次写库备份"),
    "DB_WAL_LARGE": ("归档库的 WAL 文件过大，说明长时间没有检查点或有长事务。",
                      "在无写入时做一次 checkpoint；检查是否有长时间运行的批处理。",
                      "处理归档库 WAL 过大", "WAL 过大影响读写性能和恢复时间", "批处理结束后自动 checkpoint"),
}


def now_ts() -> float:
    return time.time()


def iso_to_ts(text) -> float | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def anomaly(code: str, severity: str, evidence: str) -> dict:
    cause, suggestion = KNOWLEDGE[code][0], KNOWLEDGE[code][1]
    return {"code": code, "severity": severity, "evidence": evidence, "cause": cause, "suggestion": suggestion}


def tail_lines(path: Path, limit: int) -> list[str]:
    """只读文件末尾，避免日志膨胀后整文件读入。"""
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - LOG_TAIL_BYTES))
        data = stream.read()
    return data.decode("utf-8", errors="replace").splitlines()[-limit:]


def run_quiet(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """所有子进程统一：隐藏窗口、stdin 指向空设备（pythonw 下没有有效标准句柄）、有超时。"""
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                          stdin=subprocess.DEVNULL, **no_console_kwargs())


# ---------------------------------------------------------------- 各项检查（彼此独立，出错只记检查错误）

def check_archive_config(now: float) -> list[dict]:
    db = archive_database_path()
    if db is None or not Path(db).is_file():
        return [anomaly("ARCHIVE_UNCONFIGURED", "high", f"归档库路径={db}，文件不存在或未配置")]
    return []


def read_jobs() -> list[tuple[Path, dict]]:
    jobs = []
    for path in sorted(QUEUE.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            jobs.append((path, data))
    return jobs


def check_archive_queue(now: float) -> list[dict]:
    out = []
    open_jobs = [(p, j) for p, j in read_jobs() if j.get("state") != "done"]
    invalid, stuck = [], []
    for path, job in open_jobs:
        run_dir = job.get("run_dir")
        if isinstance(run_dir, str) and run_dir and not (Path(run_dir) / "run.json").is_file():
            invalid.append(path.name)
            continue
        try:
            fallback = path.stat().st_mtime
        except OSError:  # 遍历中被 worker 移走
            continue
        if now - (iso_to_ts(job.get("updated_at")) or fallback) > WINDOW_SECONDS:
            stuck.append(path.name)
    if invalid:
        out.append(anomaly("ARCHIVE_INVALID_JOBS", "medium" if len(invalid) > 3 else "low",
                           f"{len(invalid)} 个任务的 run.json 不存在：{', '.join(invalid[:5])}"))
    if stuck:
        out.append(anomaly("ARCHIVE_QUEUE_STUCK", "high" if len(stuck) > 20 else "medium",
                           f"{len(stuck)} 个未完成任务超过 {INTERVAL_HOURS} 小时没有进展：{', '.join(stuck[:5])}"))
    lock = QUEUE / "worker.lock"
    try:
        age = now - lock.stat().st_mtime
    except OSError:
        return out  # 没有锁，或检查瞬间锁刚被释放
    try:
        import sire_archive_sync as sync
        pid = int(sync.read_lock(lock).get("pid") or 0)
        if age > sync.LOCK_STALE_SECONDS and not sync.pid_alive(pid):
            out.append(anomaly("ARCHIVE_LOCK_STALE", "high", f"worker.lock 已 {age / 60:.0f} 分钟无心跳且持有进程 {pid} 不存在"))
    except Exception as exc:  # noqa: BLE001  锁文件格式异常不应让整个检查失败
        out.append(anomaly("ARCHIVE_LOCK_STALE", "medium", f"worker.lock 无法解析：{exc}"))
    return out


def check_worker_log(now: float) -> list[dict]:
    path = LOGS / "worker.log"
    if not path.is_file():
        return []
    hits = []
    for line in tail_lines(path, 2000):
        stamp = iso_to_ts(line.split(" ", 1)[0])
        if stamp and now - stamp <= WINDOW_SECONDS and ("失败" in line or "Traceback" in line or "异常" in line):
            hits.append(line[:160])
    if not hits:
        return []
    return [anomaly("ARCHIVE_WORKER_FAILURES", "medium" if len(hits) > 5 else "low",
                    f"本周期 {len(hits)} 条失败，最近一条：{hits[-1]}")]


def check_gate_errors(now: float) -> list[dict]:
    path = GATE_DIR / "error.log"
    if not path.is_file():
        return []
    recent = []
    for line in tail_lines(path, 500):
        parts = line.split()
        try:
            stamp = int(parts[0]) if parts and parts[0].isascii() and parts[0].isdigit() else None
        except ValueError:
            stamp = None
        if stamp is not None and now - stamp <= WINDOW_SECONDS:
            recent.append(parts[1] if len(parts) > 1 else "?")
    if not recent:
        return []
    return [anomaly("GATE_ERRORS", "medium", f"本周期门禁钩子自身异常 {len(recent)} 次：{', '.join(sorted(set(recent)))}")]


def check_telemetry(now: float) -> list[dict]:
    if not TELEMETRY_DB.is_file():
        return []
    out = []
    con = sqlite3.connect(f"file:{TELEMETRY_DB.as_posix()}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT finding_id,rule,hits,last_seen FROM findings "
                           "WHERE status IN ('PROPOSED','OPEN','REGRESSED') AND rule NOT LIKE 'HEALTH%' "
                           "ORDER BY hits DESC").fetchall()
        dead = [r for r in rows if r["rule"] == "COLLECTION_DEAD"]
        others = [r for r in rows if r["rule"] != "COLLECTION_DEAD"]
        if dead:
            out.append(anomaly("COLLECTION_DEAD", "high", "采集断流：" + ", ".join(r["finding_id"] for r in dead)))
        if others:
            top = ", ".join(f"{r['rule']}({r['hits']})" for r in others[:5])
            sev = "medium" if any((r["hits"] or 0) >= 10 for r in others) else "low"
            out.append(anomaly("TELEMETRY_FINDINGS_OPEN", sev, f"{len(others)} 条待处理发现，命中最多：{top}"))
        missing = con.execute("SELECT count(*) FROM events WHERE event='usage_missing' AND ts>?",
                              (now - WINDOW_SECONDS,)).fetchone()[0]
        if missing:
            out.append(anomaly("USAGE_MISSING_RECENT", "medium", f"本周期 {missing} 次完整流程回复被拦后仍缺耗时/额度消耗"))
    finally:
        con.close()
    return out


def git(*args: str) -> str:
    """只读 git：--no-optional-locks 避免与用户同时进行的 git 操作争 index.lock；git 不存在或超时都转成 RuntimeError。"""
    try:
        result = run_quiet(["git", "--no-optional-locks", "-C", str(SHARED_SKILL_DIR), *args], 60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git 不可用：{exc}") from exc
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[:200])
    return result.stdout.strip()


def check_rsi(now: float) -> list[dict]:
    """RSI 数据库侧：停滞提案。只读仓库库，不依赖 git。"""
    if not REPO_DB.is_file():
        return []
    con = sqlite3.connect(f"file:{REPO_DB.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        stale = []
        for pid, status, created in con.execute(
                "SELECT proposal_id,status,created_at FROM improvement_proposals WHERE status IN ('PROPOSED','EVALUATED_PASS')"):
            age = now - (iso_to_ts(created) or now)
            if age > 24 * 3600:
                stale.append(f"{pid}({status},{age / 3600:.0f}h)")
    finally:
        con.close()
    if stale:
        return [anomaly("RSI_STALE_PROPOSALS", "low", f"{len(stale)} 个提案超过 24 小时未处理：{', '.join(stale[:5])}")]
    return []


def check_workflow_git(now: float) -> list[dict]:
    """工作流 Git 侧：生效版本哈希漂移、未提交改动。git 不可用或超时直接抛 RuntimeError，让这一项记为“检查出错”，
    其负责的异常按“状态未知”处理，不会被误判为已恢复。"""
    out = []
    if REPO_DB.is_file():
        con = sqlite3.connect(f"file:{REPO_DB.as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            active = con.execute("SELECT version,config_hash FROM workflow_versions WHERE status='ACTIVE'").fetchone()
        finally:
            con.close()
        if active and active[1]:
            head = git("rev-parse", "HEAD:./")
            if head != active[1]:
                out.append(anomaly("RSI_HASH_DRIFT", "medium", f"生效版本 {active[0]} 登记哈希 {active[1][:8]}，Git 当前 {head[:8]}"))
    dirty = [x for x in git("status", "--porcelain", "--", ".").splitlines() if x.strip()]
    if dirty:
        out.append(anomaly("WORKFLOW_UNCOMMITTED", "low", f"工作流目录有 {len(dirty)} 个未提交改动：{'; '.join(d.strip() for d in dirty[:4])}"))
    return out


def check_version(now: float) -> list[dict]:
    if not REPO_DB.is_file():
        return []
    con = sqlite3.connect(f"file:{REPO_DB.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        row = con.execute("SELECT version FROM workflow_versions WHERE status='ACTIVE'").fetchone()
    finally:
        con.close()
    if not row:
        return []
    result = run_quiet([sys.executable, str(SCRIPTS / "sire_remind.py")], 60)
    first = (result.stdout or "").splitlines()[0] if result.stdout else ""
    if row[0] not in first:
        return [anomaly("VERSION_MISMATCH", "high", f"生效版本 {row[0]}，入口提醒首行：{first[:60] or '空'}")]
    return []


def check_hooks(now: float) -> list[dict]:
    out = []
    if CLAUDE_SETTINGS.is_file():
        text = CLAUDE_SETTINGS.read_text(encoding="utf-8", errors="replace").replace("\\\"", "\"")
        needed = {"sire_gate.py\" check": "门禁 check", "sire_gate.py\" record": "门禁 record",
                  "sire_gate.py\" stop-check": "Stop 拦截", "sire_telemetry.py\" hook": "遥测"}
        missing = [label for key, label in needed.items() if key not in text]
        if missing:
            out.append(anomaly("HOOKS_MISSING", "high", "settings.json 缺少：" + "、".join(missing)))
    try:
        link_ok = SKILL_LINK.exists() and (SKILL_LINK / "SKILL.md").is_file() \
            and SKILL_LINK.resolve() == SHARED_SKILL_DIR.resolve()
    except OSError:
        link_ok = False
    if not link_ok:
        out.append(anomaly("SKILL_LINK_BROKEN", "high", f"{SKILL_LINK} 不存在或没有指向 {SHARED_SKILL_DIR}"))
    return out


def dir_size(path: Path) -> int:
    total = 0
    if not path.is_dir():
        return 0
    for f in path.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:  # 备份轮转时文件可能消失
            continue
    return total


def check_resources(now: float) -> list[dict]:
    out = []
    free = shutil.disk_usage(LEDGER_ROOT if LEDGER_ROOT.exists() else Path.home()).free / 1024 ** 3
    if free < 20:
        out.append(anomaly("DISK_LOW", "high" if free < 10 else "medium", f"剩余 {free:.1f} GB"))
    backups = dir_size(BACKUP_DIR) / 1024 ** 3
    if backups > 8:
        out.append(anomaly("BACKUPS_LARGE", "low", f"数据库备份目录 {backups:.1f} GB"))
    archive = archive_database_path()
    if archive:
        wal = Path(str(archive) + "-wal")
        try:
            if wal.is_file() and wal.stat().st_size > 1024 ** 3:
                out.append(anomaly("DB_WAL_LARGE", "low", f"{wal.name} {wal.stat().st_size / 1024 ** 3:.1f} GB"))
        except OSError:
            pass
    return out


CHECKS = (("归档配置", check_archive_config), ("归档队列", check_archive_queue), ("归档日志", check_worker_log),
          ("门禁异常", check_gate_errors), ("遥测发现", check_telemetry), ("RSI 状态", check_rsi), ("工作流 Git", check_workflow_git),
          ("版本一致", check_version), ("钩子与技能链接", check_hooks), ("资源", check_resources))


# ---------------------------------------------------------------- 趋势、分析、记录

def load_state() -> dict:
    try:
        data = json.loads((HEALTH_DIR / "state.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def run_checks(now: float | None = None) -> dict:
    now = now_ts() if now is None else now
    anomalies, errors, timings = [], [], {}
    for name, func in CHECKS:
        started = time.time()
        try:
            anomalies.extend(func(now))
        except Exception as exc:  # noqa: BLE001  单项检查出错不能影响其他项
            errors.append({"check": name, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
        timings[name] = round(time.time() - started, 2)
    anomalies.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 9), a["code"]))
    return {"ts": now, "anomalies": anomalies, "check_errors": errors, "checks": [n for n, _ in CHECKS],
            "timings": timings}


def annotate_trend(result: dict, state: dict) -> dict:
    """对照历史：每个异常标注 新增/持续(第 n 个周期)，并列出已恢复的。
    某项检查本次出错时，它负责的异常代码按“状态未知”处理：不算已恢复，也不打断连续次数。"""
    runs = list(state.get("runs", []))
    if runs and result["ts"] - runs[-1]["ts"] < MIN_RUN_GAP:
        runs = runs[:-1]  # 与上一次运行相隔不足 4 小时：属于同一个周期，上一次不算“之前的周期”（save 也会替换它）
    previous = set(runs[-1]["codes"]) if runs else set()
    current = {a["code"] for a in result["anomalies"]}
    unknown = set()
    for err in result.get("check_errors", []):
        unknown |= CHECK_CODES.get(err["check"], set())
    for a in result["anomalies"]:
        streak = 1
        for run in reversed(runs):
            if a["code"] in run["codes"]:
                streak += 1
            else:
                break
        a["streak"] = streak
        a["trend"] = "持续" if a["code"] in previous else "新增"
        a["sustained"] = streak >= SUSTAINED_RUNS
    result["recovered"] = sorted(previous - current - unknown)
    result["state_codes"] = sorted(current | (previous & unknown))  # 写进趋势历史：出错项的旧状态原样保留
    return result


def draft_for(a: dict, report_name: str = "") -> dict:
    title, hypothesis, change = KNOWLEDGE[a["code"]][2:5]
    where = f"；证据见健康检查报告 {report_name}" if report_name else ""
    return {"title": f"[健康检查] {title}",
            "hypothesis": f"{hypothesis}（严重度 {a['severity']}，连续 {a.get('streak', 1)} 个周期{where}）",
            "change": f"{change}（工作流自动生成，来源：定时健康检查，待用户确认）"}


def needs_proposal(a: dict) -> bool:
    """持续出现的异常，或高严重度异常，才由工作流生成提案草案；信息类异常永远不生成。"""
    if a["code"] in INFO_CODES:
        return False
    return bool(a.get("sustained")) or a["severity"] == "high"


def finding_status(con: sqlite3.Connection, fid: str):
    return con.execute("SELECT status,hits,hits_at_ignore,ignore_kind,resolved_at FROM findings WHERE finding_id=?",
                       (fid,)).fetchone()


def record_findings(result: dict) -> list[str]:
    """把异常写成遥测发现（HEALTH:<代码>）。需要提案的记 PROPOSED（会让 R9 收尾提示用户决定），
    其余只记 OPEN（不阻塞收尾）。用户已忽略的发现沿用遥测的复活规则：累计命中明显增加或超过 14 天才重开；
    “已知并接受”只计数。已恢复的标记 FIXED（出错的检查所负责的代码不算恢复）。"""
    if not TELEMETRY_DB.is_file():
        return []
    import sire_telemetry as tel
    recorded, now = [], result["ts"]
    con = sqlite3.connect(TELEMETRY_DB, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        with con:
            for a in result["anomalies"]:
                fid = f"HEALTH:{a['code']}"
                status = "PROPOSED" if needs_proposal(a) else "OPEN"
                item = json.dumps([{"at": round(now), "evidence": a["evidence"], "severity": a["severity"]}],
                                  ensure_ascii=False)
                row = finding_status(con, fid)
                if row is None:
                    con.execute("INSERT INTO findings(finding_id,rule,status,hits,first_seen,last_seen,evidence,suggestion) "
                                "VALUES(?,?,?,?,?,?,?,?)", (fid, "HEALTH", status, 1, now, now, item, a["suggestion"]))
                    recorded.append(fid)
                    continue
                hits = (row["hits"] or 0) + 1
                if row["status"] == "IGNORED":
                    if row["ignore_kind"] == "accepted":  # 已知并接受：只计数
                        con.execute("UPDATE findings SET hits=?,last_seen=? WHERE finding_id=?", (hits, now, fid))
                        continue
                    grown = hits - (row["hits_at_ignore"] or 0)
                    aged = grown > 0 and now - (row["resolved_at"] or now) > tel.REVIVE_SECONDS
                    if grown >= 4 or aged:
                        con.execute("UPDATE findings SET status=?,hits=?,last_seen=?,evidence=?,ignore_kind=NULL,"
                                    "resolved_at=NULL,note=? WHERE finding_id=?",
                                    (status, hits, now, item, f"复活：忽略后又命中 {grown} 次", fid))
                        recorded.append(fid)
                    else:
                        con.execute("UPDATE findings SET hits=?,last_seen=? WHERE finding_id=?", (hits, now, fid))
                    continue
                # 已有的 PROPOSED 不降级（用户还没决定）；OPEN 满足条件时升级为 PROPOSED
                new_status = "PROPOSED" if "PROPOSED" in (status, row["status"]) else status
                con.execute("UPDATE findings SET status=?,hits=?,last_seen=?,evidence=? WHERE finding_id=?",
                            (new_status, hits, now, item, fid))
                recorded.append(fid)
            for code in result.get("recovered", []):
                con.execute("UPDATE findings SET status='FIXED',resolved_at=?,note=? WHERE finding_id=? "
                            "AND status IN ('PROPOSED','OPEN','REGRESSED')", (now, "健康检查确认已恢复", f"HEALTH:{code}"))
    finally:
        con.close()
    return recorded


def ignored_codes() -> set[str]:
    """用户已决定忽略的异常代码：工作流不再为它们生成提案草案。"""
    if not TELEMETRY_DB.is_file():
        return set()
    con = sqlite3.connect(f"file:{TELEMETRY_DB.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        return {r[0][len("HEALTH:"):] for r in con.execute(
            "SELECT finding_id FROM findings WHERE finding_id LIKE 'HEALTH:%' AND status='IGNORED'")}
    finally:
        con.close()


def recent_draft(code: str, now: float) -> bool:
    """同一异常代码在冷却期内已经生成过草案（不论草案后来被用户怎样处理）就不再生成。"""
    if not REPO_DB.is_file():
        return False
    con = sqlite3.connect(f"file:{REPO_DB.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        for (created,) in con.execute("SELECT created_at FROM improvement_proposals WHERE proposal_id LIKE ?",
                                      (f"AUTO-HEALTH-{code}-%",)):
            if now - (iso_to_ts(created) or 0) < DRAFT_COOLDOWN:
                return True
    finally:
        con.close()
    return False


def active_version() -> str | None:
    if not REPO_DB.is_file():
        return None
    con = sqlite3.connect(f"file:{REPO_DB.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        row = con.execute("SELECT version FROM workflow_versions WHERE status='ACTIVE'").fetchone()
    finally:
        con.close()
    return row[0] if row else None


def create_proposal_drafts(result: dict, report_name: str = "") -> list[str]:
    """由工作流自己提出提案草案（只 propose，永不 evaluate/activate），等用户确认。
    限制：信息类异常不生成；用户已忽略的不生成；同一代码 7 天冷却；每次运行最多 2 份；失败原因记入 proposal_errors。"""
    created, errors = [], []
    version = active_version()
    ignored = ignored_codes()
    for a in result["anomalies"]:
        if len(created) >= MAX_DRAFTS_PER_RUN:
            break
        if not needs_proposal(a) or a["code"] in ignored or recent_draft(a["code"], result["ts"]):
            continue
        d = draft_for(a, report_name)
        pid = f"AUTO-HEALTH-{a['code']}-{datetime.fromtimestamp(result['ts']).strftime('%Y%m%d%H%M')}"
        cmd = [sys.executable, str(SCRIPTS / "sire_rsi.py"), "propose", pid, "--title", d["title"],
               "--hypothesis", d["hypothesis"], "--change", d["change"]]
        if version:
            cmd += ["--parent-version", version]
        try:
            proc = run_quiet(cmd, 600)
        except Exception as exc:  # noqa: BLE001  单份草案失败不影响其他，也不能让整次运行中断
            errors.append({"proposal": pid, "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
            continue
        if proc.returncode == 0:
            created.append(pid)
        else:
            errors.append({"proposal": pid, "error": (proc.stderr or proc.stdout or "propose 失败").strip()[:160]})
    result["proposal_errors"] = errors
    return created


def render(result: dict) -> str:
    when = datetime.fromtimestamp(result["ts"]).strftime("%Y-%m-%d %H:%M")
    anomalies = result["anomalies"]
    counts = {s: sum(1 for a in anomalies if a["severity"] == s) for s in ("high", "medium", "low")}
    lines = [f"# SIRE 工作流健康检查 {when}", "",
             f"共 {len(anomalies)} 项异常：高 {counts['high']}、中 {counts['medium']}、低 {counts['low']}；"
             f"已恢复 {len(result.get('recovered', []))} 项；检查项 {len(result['checks'])} 个，自身出错 {len(result['check_errors'])} 个。", ""]
    if anomalies:
        lines += ["## 异常与分析", ""]
        for a in anomalies:
            tag = "仅提示" if a["code"] in INFO_CODES else ("需要用户确定" if needs_proposal(a) else "观察中")
            lines += [f"### [{a['severity']}] {a['code']}（{a.get('trend', '新增')}，连续第 {a.get('streak', 1)} 个周期，{tag}）",
                      f"- 证据：{a['evidence']}", f"- 成因：{a['cause']}", f"- 优化方向：{a['suggestion']}", ""]
    else:
        lines += ["没有发现异常。", ""]
    if result.get("recovered"):
        lines += ["## 已恢复", "", *[f"- {c}" for c in result["recovered"]], ""]
    if result.get("created_proposals"):
        lines += ["## 工作流自动生成的提案草案（待你确认，未评估、未激活）", "", *[f"- {p}" for p in result["created_proposals"]], ""]
    if result.get("proposal_errors"):
        lines += ["## 提案草案生成失败", "", *[f"- {e['proposal']}：{e['error']}" for e in result["proposal_errors"]], ""]
    if result["check_errors"]:
        lines += ["## 检查自身出错（未能检查；相关异常按“状态未知”处理，不算已恢复）", "",
                  *[f"- {e['check']}：{e['error']}" for e in result["check_errors"]], ""]
    if result.get("record_error"):
        lines += ["## 记录发现失败", "", f"- {result['record_error']}", ""]
    if result.get("timings"):
        lines += ["## 各项检查耗时（秒）", "", ", ".join(f"{k} {v}" for k, v in result["timings"].items()), ""]
    return "\n".join(lines)


def save(result: dict, state: dict) -> Path:
    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromtimestamp(result["ts"]).strftime("%Y%m%d-%H%M")
    report = HEALTH_DIR / f"health-{stamp}.md"
    report.write_text(render(result), encoding="utf-8")
    (HEALTH_DIR / f"health-{stamp}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (HEALTH_DIR / "last.json").write_text(json.dumps({**result, "report": str(report)}, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    codes = result.get("state_codes", [a["code"] for a in result["anomalies"]])
    runs = list(state.get("runs", []))
    entry = {"ts": result["ts"], "codes": codes}
    if runs and result["ts"] - runs[-1]["ts"] < MIN_RUN_GAP:
        runs[-1] = entry  # 间隔不足 4 小时算同一个周期：替换而不是追加，防止手工多跑把异常提前算成“持续”
    else:
        runs.append(entry)
    (HEALTH_DIR / "state.json").write_text(json.dumps({"ts": result["ts"], "runs": runs[-10:]}, ensure_ascii=False),
                                           encoding="utf-8")
    for old in sorted(HEALTH_DIR.glob("health-*.md"))[:-KEEP_REPORTS]:
        old.unlink(missing_ok=True)
        old.with_suffix(".json").unlink(missing_ok=True)
    return report


_RUN_TOKEN: list[str] = []


def read_run_lock(lock: Path) -> dict:
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def acquire_run_lock() -> bool:
    """运行互斥：计划任务、Stop 钩子补跑与手工运行不能同时进行。独占创建，过期（65 分钟）可接管；
    接管前重读令牌确认仍是刚才判定过期的那把锁，结束时只删自己的锁。"""
    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    lock = HEALTH_DIR / "run.lock"
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime > RUN_LOCK_STALE:
            observed = read_run_lock(lock).get("token")
            if read_run_lock(lock).get("token") == observed:
                lock.unlink()
    except OSError:
        pass
    token = os.urandom(8).hex()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps({"pid": os.getpid(), "ts": time.time(), "token": token}))
    _RUN_TOKEN[:] = [token]
    return True


def release_run_lock() -> None:
    lock = HEALTH_DIR / "run.lock"
    if _RUN_TOKEN and read_run_lock(lock).get("token") != _RUN_TOKEN[0]:
        return  # 锁已被别的运行接管，不删它的锁
    try:
        lock.unlink()
    except OSError:
        pass
    _RUN_TOKEN.clear()


def cmd_run(args) -> int:
    if args.record and not acquire_run_lock():
        print("已有一次健康检查在运行，本次跳过")
        return 0
    try:
        result = annotate_trend(run_checks(), load_state())
        report = None
        if args.record:
            stamp = datetime.fromtimestamp(result["ts"]).strftime("%Y%m%d-%H%M")
            try:
                result["recorded_findings"] = record_findings(result)
            except Exception as exc:  # noqa: BLE001  记录失败不能阻止报告与状态保存，否则补跑会每 30 分钟重试
                result["record_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            try:
                result["created_proposals"] = [] if args.no_proposal else create_proposal_drafts(result, f"health-{stamp}.md")
            except Exception as exc:  # noqa: BLE001
                result["created_proposals"] = []
                result["proposal_errors"] = [{"proposal": "-", "error": f"{type(exc).__name__}: {str(exc)[:120]}"}]
            report = save(result, load_state())
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(render(result))
            if report:
                print(f"报告已保存：{report}")
        return 0
    finally:
        if args.record:
            release_run_lock()


def cmd_last(args) -> int:
    path = HEALTH_DIR / "last.json"
    if not path.is_file():
        print("还没有健康检查记录")
        return 1
    print(render(json.loads(path.read_text(encoding="utf-8"))))
    return 0


def cmd_due(args) -> int:
    ts = load_state().get("ts", 0)
    due = now_ts() - ts > args.hours * 3600
    print("已超时" if due else "未超时")
    return 0 if due else 1


def ps_quote(text: str) -> str:
    """PowerShell 单引号字面量：内部单引号写成两个。"""
    return text.replace("'", "''")


def powershell(script: str) -> subprocess.CompletedProcess:
    return run_quiet(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], 120)


def task_script() -> str:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.is_file() else Path(sys.executable)
    triggers = ",".join(f"(New-ScheduledTaskTrigger -Daily -At '{t}')" for t in SCHEDULE_TIMES)
    argument = ps_quote(f'"{Path(__file__).resolve()}" run --record')
    return (f"$a = New-ScheduledTaskAction -Execute '{ps_quote(str(exe))}' -Argument '{argument}'; "
            f"$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -Hidden -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
            f"-ExecutionTimeLimit (New-TimeSpan -Minutes 60) -MultipleInstances IgnoreNew; "
            f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger {triggers} -Settings $s -Force "
            f"-Description 'SIRE 工作流每 8 小时健康检查（0/8/16 点）' | Out-Null; 'registered'")


def cmd_install(args) -> int:
    if args.print_only:
        print(task_script())
        return 0
    proc = powershell(task_script())
    print((proc.stdout or proc.stderr).strip())
    return proc.returncode


def cmd_uninstall(args) -> int:
    proc = powershell(f"if (Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue) "
                      f"{{ Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false; 'removed' }} else {{ 'not-installed' }}")
    print((proc.stdout or proc.stderr).strip())
    return proc.returncode


def cmd_task_status(args) -> int:
    proc = powershell(f"$t = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue; "
                      f"if ($t) {{ $i = Get-ScheduledTaskInfo -TaskName '{TASK_NAME}'; "
                      f"'state=' + $t.State; 'triggers=' + (($t.Triggers | ForEach-Object {{ $_.StartBoundary }}) -join ','); "
                      f"'lastRun=' + $i.LastRunTime; 'nextRun=' + $i.NextRunTime; 'lastResult=' + $i.LastTaskResult }} "
                      f"else {{ 'not-installed' }}")
    print((proc.stdout or proc.stderr).strip())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SIRE 工作流定时健康检查")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--record", action="store_true", help="写遥测发现、生成提案草案并保存报告")
    r.add_argument("--json", action="store_true")
    r.add_argument("--no-proposal", action="store_true", help="只记发现，不生成提案草案")
    sub.add_parser("last")
    d = sub.add_parser("due")
    d.add_argument("--hours", type=float, default=INTERVAL_HOURS + 1)
    i = sub.add_parser("install-task")
    i.add_argument("--print-only", action="store_true")
    sub.add_parser("uninstall-task")
    sub.add_parser("task-status")
    args = ap.parse_args()
    try:
        return {"run": cmd_run, "last": cmd_last, "due": cmd_due, "install-task": cmd_install,
                "uninstall-task": cmd_uninstall, "task-status": cmd_task_status}[args.cmd](args)
    except Exception as exc:  # noqa: BLE001  pythonw 下没有输出，崩溃必须落盘，否则只剩 LastResult≠0
        HEALTH_DIR.mkdir(parents=True, exist_ok=True)
        with (HEALTH_DIR / "error.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{datetime.now().isoformat()} {type(exc).__name__}: {str(exc)[:300]}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
