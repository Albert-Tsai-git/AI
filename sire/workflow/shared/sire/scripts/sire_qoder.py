"""Qoder 客户端 SIRE 适配器：把唯一源接到 Qoder 的钩子与入口上，使本端与 Codex/Claude 同等自动采集。

子命令：
  install      注册四个遥测事件 + 入口注入钩子，并建立 skills junction（写配置前必备份，幂等）
  status       只读：本端 SIRE 注册状态与唯一源规则指纹
  verify       只读：核对钩子是否真的触发（读客户端日志 + 遥测库 client='qoder'）
  uninstall    只移除本工具写入的键，其它客户端配置原样保留
  link         建立/检查 ~/.qoder-cn/skills/sire-global-workflow -> 唯一源的 junction
  remind       UserPromptSubmit 钩子：输出声明行 + 实时取自唯一源的快速通道规则
  selftest     隔离遥测库 + 合成 Qoder 载荷，跑真实 hook→analyze→pending 链路

约束：不在客户端目录保留第二份可写工作流/知识库/数据库；入口只允许 junction 或实时生成，不留手工副本。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from sire_paths import DATA_DIR, SHARED_SKILL_DIR  # noqa: E402
from sire_process import no_console_kwargs  # noqa: E402

QODER_HOME = Path(os.environ.get("QODER_HOME") or Path.home() / ".qoder-cn").expanduser()
SETTINGS = QODER_HOME / "settings.json"
PLUGIN_REGISTRY = QODER_HOME / "plugins" / "installed_plugins_v2.json"
PLUGIN_CACHE = QODER_HOME / "plugins" / "cache"
RUN_LOGS = QODER_HOME / "logs" / "runs"
SKILL_ALIAS = QODER_HOME / "skills" / "sire-global-workflow"
CONTRACT = SHARED_SKILL_DIR / "references" / "global-contract.md"
TELEMETRY = SHARED_SKILL_DIR / "scripts" / "sire_telemetry.py"
HOOKS = ("UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "Stop")
MARK = "sire-telemetry"
VERSION = "1.0.0"
PY = Path(sys.executable)


def _shell(cmd: list[str]) -> str:
    """每个 token 都加引号：实测这种写法写入后本端立刻产生了真实事件，
    而裸词形式写入后采集停止（原因未在客户端侧证实，保守采用可观测有效的那种）。"""
    return " ".join(f'"{c}"' for c in cmd)


def _tele_cmd() -> str:
    return _shell([str(PY), str(TELEMETRY), "hook", "--client", "qoder"])


def _remind_cmd() -> str:
    return _shell([str(PY), str(Path(__file__).resolve()), "remind"])


def _entry(command: str, name: str) -> dict:
    return {"hooks": [{"type": "command", "command": command, "timeout": 5, "name": name}]}


def _settings_hooks(with_remind: bool = False) -> dict:
    """默认只注册遥测事件。

    入口注入默认关闭的依据：在 app.asar 里找不到 Claude 的上下文注入字段
    （additionalContext / hookSpecificOutput 各 0 次命中），实测 UserPromptSubmit 的
    stdout 也没有进入模型上下文；Qoder 的常驻上下文载体是 `~/.qoder-cn/memory/`（每轮必进上下文），
    所以规则注入交给记忆入口，钩子只负责计时。remind 保留为 --with-remind 显式选项。"""
    out = {event: [_entry(_tele_cmd(), f"{MARK}:{event}")] for event in HOOKS}
    if with_remind:
        out["UserPromptSubmit"].append(_entry(_remind_cmd(), f"{MARK}:entry"))
    return out


def _backup(path: Path) -> Path | None:
    if not path.is_file():
        return None
    dest = path.with_name(f"{path.name}.sire-backup-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(path, dest)
    return dest


def _read_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _is_ours(entry) -> bool:
    text = json.dumps(entry, ensure_ascii=False)
    return MARK in text or "sire_telemetry.py" in text or "sire_qoder.py" in text


ENTRY_FILE = QODER_HOME / "AGENTS.md"
ENTRY_TAG = "<!-- sire-qoder-entry -->"


def entry_text() -> str:
    _, digest = _fastpath_section()
    return (f"{ENTRY_TAG}\n# Qoder 全局指令（SIRE 薄入口，由 sire_qoder.py 生成）\n\n"
            f"所有任务必须执行 SIRE v6 工作流。唯一源与规则正文：`{SHARED_SKILL_DIR}`"
            f"（读 `SKILL.md` 与 `references/global-contract.md`；本文件不复述规则）。\n\n"
            f"两条硬性要求：每次回复首行输出 `[SIRE v6] 已使用 SIRE 工作流执行当前任务`；"
            f"动手前先判一次快速通道（规则指纹 {digest}，全文见唯一源）。\n"
            f"本端遥测钩子由 `sire_qoder.py install` 注册，采集状况用 `sire_qoder.py verify` 复核。{ENTRY_TAG}\n")


def cmd_entry_file(remove: bool = False) -> int:
    """Qoder 的常驻入口等价物：用户级 AGENTS.md 短指针，靠指纹发现漂移，不复制规则正文。"""
    ours = ENTRY_FILE.is_file() and ENTRY_TAG in ENTRY_FILE.read_text(encoding="utf-8", errors="ignore")
    if remove:
        if ours:
            _backup(ENTRY_FILE)
            ENTRY_FILE.unlink()
            print(f"已移除本工具生成的入口文件：{ENTRY_FILE}")
        else:
            print(f"入口文件非本工具生成或不存在，保持不动：{ENTRY_FILE}")
        return 0
    old = ENTRY_FILE.read_text(encoding="utf-8", errors="ignore") if ENTRY_FILE.is_file() else ""
    body = entry_text()
    if ours:
        head = old.split(ENTRY_TAG, 1)[0].strip()
        merged = (head + "\n\n" if head else "") + body
        if merged == old:
            print(f"入口文件已是最新：{ENTRY_FILE}")
            return 0
        _backup(ENTRY_FILE)
        ENTRY_FILE.write_text(merged, encoding="utf-8")
        print(f"入口文件已更新：{ENTRY_FILE}")
        return 0
    _backup(ENTRY_FILE)
    ENTRY_FILE.write_text((old.rstrip() + "\n\n" if old.strip() else "") + body, encoding="utf-8")
    print(f"入口文件已生成：{ENTRY_FILE}")
    return 0


def cmd_link(_args=None) -> int:
    """与 Claude 别名同构：junction 指向唯一源，不产生第二份可写工作流。"""
    if SKILL_ALIAS.exists():
        real = SKILL_ALIAS.resolve()
        if real == SHARED_SKILL_DIR:
            print(f"skills 别名已指向唯一源：{SKILL_ALIAS}")
            return 0
        print(f"skills 别名指向 {real}，与唯一源不符，需人工处理", file=sys.stderr)
        return 2
    SKILL_ALIAS.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(SKILL_ALIAS), str(SHARED_SKILL_DIR)],
                   capture_output=True, text=True, **no_console_kwargs())
    ok = SKILL_ALIAS.exists() and SKILL_ALIAS.resolve() == SHARED_SKILL_DIR
    print(("skills 别名已建立：" if ok else "skills 别名建立失败：") + f"{SKILL_ALIAS} -> {SHARED_SKILL_DIR}")
    return 0 if ok else 1


def _fastpath_section() -> tuple[str, str]:
    contract = CONTRACT.read_text(encoding="utf-8")
    match = re.search(r"## 简单任务快速通道.*?(?=\n## )", contract, re.S)
    if not match:
        return "", ""
    section = match.group(0).rstrip()
    return section, hashlib.sha256(section.encode("utf-8")).hexdigest()[:12]


def cmd_remind(_args) -> int:
    section, digest = _fastpath_section()
    print(f"[SIRE v6] 每次回复首行必须输出：`[SIRE v6] 已使用 SIRE 工作流执行当前任务`。\n"
          f"唯一源：{SHARED_SKILL_DIR}（快速通道规则指纹 {digest}）；判定标准实时取自该源，"
          f"动手前先过一次快速通道：\n\n{section}")
    return 0


def cmd_install(args) -> int:
    if args.channel in ("settings", "both"):
        data = _read_json(SETTINGS, {})
        if not isinstance(data, dict):
            print("settings.json 顶层不是对象，拒绝改写", file=sys.stderr)
            return 2
        hooks = data.get("hooks")
        hooks = hooks if isinstance(hooks, dict) else {}
        replaced = 0
        for event, entries in _settings_hooks(args.with_remind).items():
            keep = [e for e in hooks.get(event, []) if not _is_ours(e)]
            replaced += len(hooks.get(event, [])) - len(keep)
            hooks[event] = keep + entries
        data["hooks"] = hooks
        backup = _backup(SETTINGS)
        _write_json(SETTINGS, data)
        print(f"settings 通道：{len(HOOKS)} 个遥测事件{' + 1 个入口注入' if args.with_remind else '（入口注入未启用 --with-remind）'}已写入（替换旧条目 {replaced} 个）"
              f"{'，备份 ' + backup.name if backup else '，新建配置'}")
    if args.channel in ("plugin", "both"):
        root = PLUGIN_CACHE / "local" / "sire" / VERSION
        _write_json(root / ".qoder-plugin" / "plugin.json", {
            "name": "sire", "displayName": "SIRE v6 adapter", "version": VERSION,
            "description": "Bind the single SIRE workflow source to Qoder: phase telemetry + entry injection."})
        _write_json(root / "hooks" / "hooks.json", {
            "description": "SIRE phase telemetry (unique source: workflow/shared/sire)",
            "hooks": {event: [{"async": True, "hooks": [{
                "type": "command", "command": str(PY),
                "args": [str(TELEMETRY), "hook", "--client", "qoder"],
                "name": f"{MARK}:{event}", "timeout": 5}]}] for event in HOOKS}})
        registry = _read_json(PLUGIN_REGISTRY, {"version": 2, "plugins": {}})
        registry.setdefault("plugins", {})["sire@local"] = [{
            "scope": "user", "installPath": str(root), "version": VERSION,
            "installedAt": datetime.now().isoformat(), "displayName": "SIRE adapter", "userVisible": False}]
        _backup(PLUGIN_REGISTRY)
        _write_json(PLUGIN_REGISTRY, registry)
        settings = _read_json(SETTINGS, {})
        settings.setdefault("enabledPlugins", {})["sire@local"] = True
        _write_json(SETTINGS, settings)
        print(f"插件通道已生成并登记：{root}")
    cmd_link()
    if args.with_agents_md:
        cmd_entry_file()
    else:
        cmd_entry_file(remove=True)
    print("生效条件：配置写入后最迟下一个用户提示词就开始采集（实测无需重启）；随后运行 `sire_qoder.py verify`，判据是遥测库里 client='qoder' 的事件与任务心跳。")
    return 0


MEMORY_DIR = QODER_HOME / "memory"


def _memory_entry_ok() -> bool:
    """Qoder 的常驻上下文是用户级记忆目录，SIRE 声明必须在那里有位、且指向唯一源。"""
    index = MEMORY_DIR / "MEMORY.md"
    forced = MEMORY_DIR / "sire-mandatory-workflow.md"
    try:
        text = index.read_text(encoding="utf-8", errors="ignore") + forced.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "sire-mandatory-workflow" in text and "sire-mandatory-workflow.md" in text and "SKILL.md" in text


# Qoder 的 Agent 工具没有 model 参数，契约里的三档降级只能改成"角色档 + 隔离会话"
TIERS = {
    "low": ("Explore", "机械可核对、无设计决策的单元（检索、批量读文件、跑脚本、写台账、归档记录）",
            "只做被指派的一件事：给出事实与结论，不评估方案、不改文件、不提交。回报控制在 200 字内，"
            "必须附你实际读过的文件路径或命令输出摘要；拿不到证据就明确说没有证据。"),
    "mid": ("general-purpose", "常规实现与复核（编码、单元复核、功能测试、文档整理）",
            "按指派范围做事，改动手只碰指明的文件；完成后列出改动点、验证命令与真实输出，不要总结成形容词。"),
    "high": ("Plan", "需要设计决策、跨模块、高风险排错或最终裁决",
             "先给可验证的方案与验收标准，再给步骤；明确指出哪些结论是推断、哪些有证据。不要动手改代码。"),
}


def cmd_role(args) -> int:
    """输出一段可直接投给 Agent 工具的分档委派文（Qoder 无 model 参数，用角色档替代降级档位）。"""
    subagent, scope, brief = TIERS[args.tier]
    task = Path(args.task_file).read_text(encoding="utf-8").strip() if args.task_file else args.task or ""
    if not task:
        print("需要 --task 或 --task-file 给出被指派的工作", file=sys.stderr)
        return 2
    print(f"""subagent_type: {subagent}
档位: {args.tier}（{scope}）

【工作方式】{brief}

【任务】
{task}""")
    return 0


PARITY_CHECKS = (
    ("skill junction 指向唯一源", lambda: SKILL_ALIAS.exists() and SKILL_ALIAS.resolve() == SHARED_SKILL_DIR),
    ("四个遥测事件已注册", lambda: all(any(_is_ours(x) for x in (_read_json(SETTINGS, {}).get("hooks") or {}).get(e, []))
                                for e in HOOKS)),
    ("本端有心跳", lambda: _heartbeat()[0] > 0 and _heartbeat()[1] <= 900),
    ("本端回合被汇总成任务", lambda: _heartbeat()[2] > 0),
    ("待处理发现队列为空", lambda: not _pending_ids()),
    ("记忆入口在位并指向唯一源", _memory_entry_ok),
    ("本端事件带阶段归属", lambda: _phased_events()[0] > 0),
)


def _phased_events() -> tuple[int, int]:
    """本端已入库的工具事件里有多少拿到了真实阶段（不是兜底 execute）。"""
    db = DATA_DIR / "sire_telemetry.sqlite3"
    if not db.is_file():
        return 0, 0
    c = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    total = c.execute("select count(*) from events where client='qoder' and event='tool'").fetchone()[0]
    named = c.execute("select count(*) from events where client='qoder' and event='tool' "
                      "and phase not in ('execute','reply')").fetchone()[0]
    c.close()
    return named, total


def _heartbeat() -> tuple[int, float, int]:
    db = DATA_DIR / "sire_telemetry.sqlite3"
    if not db.is_file():
        return 0, 0.0, 0
    c = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    events, last = c.execute("select count(*), coalesce(max(ts),0) from events where client='qoder'").fetchone()
    tasks = c.execute("select count(*) from tasks where client='qoder'").fetchone()[0]
    c.close()
    return events, time.time() - last, tasks


def _pending_ids() -> list[str]:
    out = subprocess.run([str(PY if False else sys.executable), str(TELEMETRY), "pending", "--json"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         **no_console_kwargs()).stdout
    try:
        return [f.get("finding") for f in json.loads(out or "[]") if isinstance(f, dict)]
    except ValueError:
        return []


def cmd_parity(_args) -> int:
    """一条命令回答：本端现在和 Codex/Claude 一样了吗。"""
    rows = []
    for name, check in PARITY_CHECKS:
        try:
            ok = bool(check())
        except Exception as exc:  # 单项检查异常不影响整体报告
            ok, rows = False, rows
            rows.append((name, "ERROR", str(exc)[:60]))
            continue
        rows.append((name, "PASS" if ok else "FAIL", ""))
    events, age, tasks = _heartbeat()
    entry = "已生成（客户端不读，仅备用）" if ENTRY_FILE.is_file() and ENTRY_TAG in ENTRY_FILE.read_text(
        encoding="utf-8", errors="ignore") else "未生成（默认，Qoder 不读该文件）"
    extra = [("本端事件/任务", f"{events} 条 / {tasks} 个回合", f"最近心跳 {age / 60:.1f} 分钟前"),
             ("可选 ~/.qoder-cn/AGENTS.md", entry, "规则注入实际载体见「记忆入口在位并指向唯一源」一项"),
             ("无法在本端实现（客户端能力）", "无 model 参数派工；OS 级 computer-use 未验证",
              "见 agents/qoder/README.md 对照表")]
    print(json.dumps({"checks": [{"项": n, "结论": s, "备注": m} for n, s, m in rows],
                      "补充": [{"项": a, "值": b, "说明": c} for a, b, c in extra]},
                     ensure_ascii=False, indent=1))
    return 0 if all(s == "PASS" for _, s, _ in rows) else 1


def cmd_status(_args) -> int:
    data = _read_json(SETTINGS, {})
    hooks = data.get("hooks") or {}
    _, digest = _fastpath_section()
    print(json.dumps({
        "telemetry_hooks": {e: any(_is_ours(x) for x in hooks.get(e, [])) for e in HOOKS},
        "entry_hook": any("sire_qoder.py" in json.dumps(x, ensure_ascii=False)
                          for x in hooks.get("UserPromptSubmit", [])),
        "skill_alias": str(SKILL_ALIAS.resolve()) if SKILL_ALIAS.exists() else "缺失",
        "alias_points_to_unique_source": SKILL_ALIAS.exists() and SKILL_ALIAS.resolve() == SHARED_SKILL_DIR,
        "entry_file": "已生成" if ENTRY_FILE.is_file() and ENTRY_TAG in ENTRY_FILE.read_text(encoding="utf-8", errors="ignore") else "缺失",
        "plugin_registered": "sire@local" in (_read_json(PLUGIN_REGISTRY, {}).get("plugins") or {}),
        "unique_source": str(SHARED_SKILL_DIR), "fastpath_fingerprint": digest},
        ensure_ascii=False, indent=2))
    return 0


def cmd_uninstall(_args) -> int:
    data = _read_json(SETTINGS, {})
    hooks = data.get("hooks") or {}
    removed = 0
    for event in list(hooks):
        keep = [e for e in hooks[event] if not _is_ours(e)]
        removed += len(hooks[event]) - len(keep)
        hooks[event] = keep
    hooks = {e: v for e, v in hooks.items() if v}
    if hooks:
        data["hooks"] = hooks
    else:
        data.pop("hooks", None)
    (data.get("enabledPlugins") or {}).pop("sire@local", None)
    _backup(SETTINGS)
    _write_json(SETTINGS, data)
    registry = _read_json(PLUGIN_REGISTRY, {"plugins": {}})
    had = registry.get("plugins", {}).pop("sire@local", None)
    if had:
        _backup(PLUGIN_REGISTRY)
        _write_json(PLUGIN_REGISTRY, registry)
        shutil.rmtree(PLUGIN_CACHE / "local" / "sire", ignore_errors=True)
    print(f"已移除 SIRE 条目 {removed} 个（其它客户端配置未动）；插件登记 {'已删' if had else '无'}；"
          f"skills 别名保留：{SKILL_ALIAS}")
    cmd_entry_file(remove=True)
    return 0


HOOK_RE = re.compile(r'hook\.(?:started|finished) hook_name="[^"]*sire-telemetry')

def cmd_verify(args) -> int:
    """钩子触发判定只认客户端自己写的 hook.started/finished 行。
    早先用 `needle in line` 会把会话日志里模型自己输入的代码文本当成触发证据（假 PASS）。"""
    hits: list[str] = []
    logs = sorted(RUN_LOGS.glob("*/qodercli.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]
    logs += sorted((QODER_HOME / "logs" / "sessions").glob("*/*/segments/*.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:4]
    for log in logs:
        try:
            lines = log.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        found = [f"{log.parent.name[:19]} {ln[-130:]}" for ln in lines if HOOK_RE.search(ln)]
        if found:
            hits = found[-3:]
            break
    db = DATA_DIR / "sire_telemetry.sqlite3"
    events, last, modes = 0, None, {}
    if db.is_file():
        c = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        events, last = c.execute("select count(*), max(ts) from events where client='qoder'").fetchone()
        modes = dict(c.execute("select mode, count(*) from tasks where client='qoder' group by 1"))
        c.close()
    # 权威判据是遥测库里本端事件在增长；日志只作为补充（客户端不一定把 settings 钩子写进 runs 日志）
    fresh = bool(last) and (time.time() - last) <= args.within * 60
    fired, has_data = bool(hits), events > 0
    verdict = ("PASS" if has_data and fresh else
               "STALE-曾采集过但最近 %d 分钟无新事件：钩子可能未随配置变更重载，检查 `status` 后重新 install 或重启客户端" % args.within
               if has_data else
               "PENDING-本端还没有任何事件；确认 `status` 为 true 后重启 Qoder 再 verify")
    print(json.dumps({"hook_fired": fired, "recent_within_min": fresh, "hook_samples": hits, "qoder_events": events,
                      "qoder_last_event": time.strftime("%m-%d %H:%M:%S", time.localtime(last)) if last else None,
                      "qoder_task_modes": modes, "结论": verdict}, ensure_ascii=False, indent=2))
    return 0 if verdict == "PASS" else 1


def cmd_selftest(_args) -> int:
    tmp = Path(os.environ.get("TEMP", "/tmp")) / "sire_qoder_selftest.sqlite3"
    for suffix in ("", "-wal", "-shm"):
        Path(str(tmp) + suffix).unlink(missing_ok=True)
    env = {**os.environ, "SIRE_TELEMETRY_DB": str(tmp)}
    session = "qoder-selftest"

    def run(payload):
        return subprocess.run([str(PY), str(TELEMETRY), "hook", "--client", "qoder"],
                              input=json.dumps(payload).encode("utf-8"), env=env, capture_output=True,
                              **no_console_kwargs())

    run({"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": "自测：改一处规则"})
    for tool, inp in [("Bash", {"command": "python sire_kb.py search x"}),
                      ("Read", {"file_path": str(SHARED_SKILL_DIR / "SKILL.md")}),
                      ("Bash", {"command": "python sire_kb.py reindex"}),
                      ("Agent", {"prompt": "独立复核"})]:
        run({"hook_event_name": "PostToolUse", "session_id": session, "tool_name": tool,
             "tool_input": inp, "tool_response": {"stdout": "ok"}, "cwd": str(DATA_DIR)})
    run({"hook_event_name": "PostToolUseFailure", "session_id": session, "tool_name": "Bash",
         "tool_input": {"command": "python bad.py"}, "tool_response": {"exit_code": 1, "stderr": "boom"}})
    transcript = Path(os.environ.get("TEMP", "/tmp")) / "sire_qoder_selftest.jsonl"
    transcript.write_text(json.dumps({"type": "assistant", "sessionId": session, "message": {
        "role": "assistant", "content": [{"type": "text",
        "text": "[SIRE v6] 已使用 SIRE 工作流执行当前任务\n快速通道：否，完整流程"}]}},
        ensure_ascii=False) + "\n", encoding="utf-8")
    run({"hook_event_name": "Stop", "session_id": session, "transcript_path": str(transcript),
         "cwd": str(DATA_DIR)})
    subprocess.run([str(PY), str(TELEMETRY), "analyze"], env=env, capture_output=True,
                   **no_console_kwargs())
    conn = sqlite3.connect(tmp)
    events = [list(r) for r in conn.execute("select event,phase,ok from events order by rowid")]
    task = conn.execute("select mode,total_s,failures,phases from tasks").fetchone()
    conn.close()
    phases = json.loads(task[3])["seconds"] if task else {}
    report = {
        "事件序列": events,
        "任务": {"mode": task[0], "total_s": round(task[1], 1), "failures": task[2]} if task else None,
        "阶段": {k: round(v, 2) for k, v in phases.items()},
        "断言": {
            "七个事件全部入库": len(events) == 7,
            "子代理调用单独成阶段": "subagent" in phases,
            "full 模式由 Qoder 转录识别": bool(task) and task[0] == "full",
            "PostToolUseFailure 记为失败": bool(task) and task[2] == 1,
            "读规则/检索/归档分别归位": {"rules", "retrieve", "archive"} <= set(phases)},
        "pending": subprocess.run([str(PY), str(TELEMETRY), "pending"], env=env, capture_output=True,
                                   text=True, encoding="utf-8", **no_console_kwargs()).stdout.strip()}
    report["结论"] = "PASS" if all(report["断言"].values()) else "FAIL"
    print(json.dumps(report, ensure_ascii=False, indent=1))
    for path in (tmp, transcript):
        path.unlink(missing_ok=True)
    return 0 if report["结论"] == "PASS" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Qoder 端 SIRE 适配器")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install")
    i.add_argument("--channel", choices=("settings", "plugin", "both"), default="settings")
    i.add_argument("--with-remind", action="store_true",
                   help="额外注册 UserPromptSubmit 入口注入（实测不进上下文，仅供其它 surface）；默认关闭")
    i.add_argument("--with-agents-md", dest="with_agents_md", action="store_true",
                   help="生成 ~/.qoder-cn/AGENTS.md（实测 Qoder 不读该文件，默认关闭并清理）")
    sub.add_parser("entry-file")
    r = sub.add_parser("role")
    r.add_argument("tier", choices=tuple(TIERS))
    r.add_argument("--task", default="")
    r.add_argument("--task-file", dest="task_file", default="")
    sub.add_parser("parity")
    for name in ("status", "uninstall", "link", "remind", "selftest"):
        sub.add_parser(name)
    v = sub.add_parser("verify")
    v.add_argument("--needle", default=None)
    v.add_argument("--within", type=int, default=10, help="最近多少分钟内有心跳才算 PASS")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.cmd == "entry-file":
        return cmd_entry_file()
    if args.cmd == "role":
        return cmd_role(args)
    if args.cmd == "parity":
        return cmd_parity(args)
    return {"install": cmd_install, "status": cmd_status, "verify": cmd_verify, "uninstall": cmd_uninstall,
            "link": cmd_link, "remind": cmd_remind, "selftest": cmd_selftest}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
