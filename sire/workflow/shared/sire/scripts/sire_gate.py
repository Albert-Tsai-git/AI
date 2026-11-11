"""SIRE 门禁钩子：会话未加载 SIRE 技能前，拦截写类工具。

用法（由客户端钩子调用，从 stdin 读 JSON 载荷）：
  python sire_gate.py record   # PostToolUse：Skill 工具成功加载 SIRE 技能后，记下本会话已加载
  python sire_gate.py check    # PreToolUse：写类工具且本会话未加载时，返回 deny；git commit/push 前还核对本轮已记录 5 小时额度读数
  python sire_gate.py stop-check  # Stop：完整流程的最终回复缺“耗时”或“额度消耗”时拦截一次，要求补跑 sire_usage.py --final

硬规则（用户定）：Claude 执行任何任务必须先加载 SIRE，没有例外。未加载时只放行 Skill 调用本身，其余工具全部拦截。

设计约束（防止把会话锁死）：
  1. 任何异常、缺字段、无法写状态目录，一律放行（fail-open）；异常类型记入状态目录的 error.log。
  2. Skill 调用与 ToolSearch（仅取工具定义）永不拦截，保证随时能解锁。
  3. 环境变量 SIRE_GATE_OFF=1 直接放行。
  4. 除 Skill 外所有工具（含读类、Bash、PowerShell、MCP）在未加载时被拦。
  5. 子代理（载荷带 agent_id/agent_type）放行：主会话已被门禁约束，子代理会话 ID 可能不同。
  6. record 写主状态目录失败时退回临时目录；check 两处都认。
  7. 钩子命令末尾带 “|| exit 0”，脚本缺失或语法错误（退出码非 0）不会被客户端当成阻塞。
状态文件只保存会话 ID 的清洗结果与时间，不含提示词或工具内容；30 天前的标记在 record 时清理。
Codex 侧暂未启用本门禁（只注入提醒），详见 references/global-contract.md 的“SIRE 门禁钩子”一节。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

SKILL_NAMES = ("sire-global-workflow", "ai-dev-sire-workflow")
DENY_REASON = ("[sire_gate] 本会话尚未加载 SIRE 工作流。规则要求所有任务第一步先加载："
               "请先调用 Skill 工具加载 sire-global-workflow，再继续（没有例外）。")


def state_dirs() -> list[Path]:
    """主状态目录（与台账同级、位于仓库之外）和临时目录回退。"""
    dirs = []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sire_paths import ledger_runs_dir
        dirs.append(Path(ledger_runs_dir()).parent / "gate")
    except Exception:
        pass
    import tempfile
    dirs.append(Path(tempfile.gettempdir()) / "sire_gate")
    return dirs


def flag_name(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:80] + ".loaded"


def is_loaded(session_id: str) -> bool:
    name = flag_name(session_id)
    return any((d / name).exists() for d in state_dirs())


def log_error(error: Exception) -> None:
    try:
        directory = state_dirs()[0]
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "error.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{int(time.time())} {type(error).__name__}\n")
    except Exception:
        pass


def mark_loaded(session_id: str) -> None:
    name = flag_name(session_id)
    written = False
    for directory in state_dirs():
        try:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / name).write_text(str(int(time.time())), encoding="utf-8")
            written = True
            break  # 主目录写成功就不再写回退目录
        except OSError as error:
            log_error(error)
    if not written:
        return
    cutoff = time.time() - 30 * 86400
    for directory in state_dirs():
        try:
            for old in directory.glob("*.loaded"):
                if old.stat().st_mtime < cutoff:
                    old.unlink(missing_ok=True)
        except OSError:
            pass


def is_sire_skill(payload: dict) -> bool:
    tool_input = payload.get("tool_input") or {}
    name = str(tool_input.get("skill") or tool_input.get("name") or "")
    return any(item in name for item in SKILL_NAMES)


def tool_succeeded(payload: dict) -> bool:
    response = payload.get("tool_response")
    if isinstance(response, dict) and response.get("is_error"):
        return False
    return True


def needs_gate(payload: dict) -> bool:
    """硬规则：未加载 SIRE 前，除加载技能本身的 Skill 调用外，所有工具一律拦截，没有读/写之分。"""
    # ToolSearch 只取工具定义、无副作用；放行它是为了 Skill 被延迟加载时仍能取到其定义，避免死锁
    return (payload.get("tool_name") or "") not in ("Skill", "ToolSearch")


# 只匹配“命令位置”的 git 子命令 commit/push：行首或 ; & | ( 之后，允许 git 全局选项（-c k=v、-C 路径、--xxx）；
# git log --grep commit、git add commit.md、引号里的 "git push" 都不匹配
COMMIT_RE = re.compile(
    r"(?:^|[;&|(\n])\s*(?:\S*[\\/])?git(?:\.exe)?"
    r"(?:\s+(?:-[cC]\s+\S+|--[\w-]+(?:=\S+)?|-[\w])){0,6}\s+(?:commit|push)\b")
USAGE_DENY = ("[sire_gate] 提交/推送前必须已记录本轮额度读数：先调用 get_usage 读 5 小时额度，再运行 "
              "sire_usage.py --plan-mark <5小时%> --weekly <周%>；任务结束的汇总必须带 sire_usage.py --final 的耗时与额度消耗。")
STOP_REASON = ("[sire_gate] 完整流程的最终回复缺少“耗时”或“额度消耗”。请先读 get_usage，运行 "
               "sire_usage.py --final --plan-end <5小时%> --weekly <周%>，把输出的耗时、额度消耗、阶段排名写进汇总后再结束；"
               "读不到就如实写“未记录/未读到”，不得省略。")


def usage_marked_this_turn(payload: dict) -> bool:
    """本轮（自上次 end_turn 后的第一条用户提示起）是否已有 --plan-mark 记录。读不到转录时视为已记录（fail-open）。"""
    transcript = payload.get("transcript_path")
    if not transcript or not os.path.isfile(transcript):
        return True
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sire_paths import ledger_runs_dir
    # 先只读小文件：最近 24 小时内没有任何额度读数就无需解析大转录，直接判未记录
    stamps = []
    # plan*.jsonl 同时覆盖默认的 plan.jsonl 与设置 SIRE_PLAN_LOG 后的 plan-<key>.jsonl
    for p in Path(ledger_runs_dir()).glob("usage-*/plan*.jsonl"):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError):
            continue
        for line in lines:  # 逐行容错：一行坏数据不能让同文件后面的有效读数丢失
            try:
                row = json.loads(line) if line.strip() else None
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("ts"), (int, float)):
                stamps.append(row["ts"])
    if not stamps or max(stamps) < time.time() - 86400:
        return False
    from sire_usage import turn_entries, turn_start_index
    entries = turn_entries(Path(transcript))
    index = turn_start_index(entries)
    if index is None:
        return True
    return max(stamps) >= entries[index][0]


def reply_missing_usage(payload: dict) -> bool:
    """完整流程的最终回复缺耗时或额度消耗；判定与遥测共用同一谓词，避免两处分叉。"""
    from sire_telemetry import last_assistant_text, reply_lacks_usage
    return reply_lacks_usage(last_assistant_text(payload))


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if os.environ.get("SIRE_GATE_OFF") == "1":
            return 0
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "ignore") or "{}")
        if not isinstance(payload, dict) or not payload.get("session_id"):
            return 0
        session_id = str(payload["session_id"])
        if mode == "record":
            if payload.get("tool_name") == "Skill" and is_sire_skill(payload) and tool_succeeded(payload):
                mark_loaded(session_id)
            return 0
        if mode == "stop-check":
            if payload.get("stop_hook_active") or payload.get("agent_id"):
                return 0  # 只拦一次，避免 Stop 钩子死循环
            if reply_missing_usage(payload):
                print(json.dumps({"decision": "block", "reason": STOP_REASON}))
            return 0
        if mode == "check":
            if payload.get("agent_id") or payload.get("agent_type"):
                return 0
            if is_loaded(session_id) and payload.get("tool_name") in ("Bash", "PowerShell"):
                command = str((payload.get("tool_input") or {}).get("command") or "")
                if COMMIT_RE.search(command) and not usage_marked_this_turn(payload):
                    print(json.dumps({"hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": USAGE_DENY}}))
                return 0
            if not needs_gate(payload) or is_loaded(session_id):
                return 0
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": DENY_REASON}}))  # 默认 ASCII 转义，避免 Windows 控制台乱码
    except Exception as error:
        log_error(error)
        return 0  # 任何异常放行，门禁自身故障不能挡住用户
    return 0


if __name__ == "__main__":
    sys.exit(main())
