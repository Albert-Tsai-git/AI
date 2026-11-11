"""SIRE 入口提醒生成器：每次提交提示词时由客户端钩子调用，从正本实时生成提醒文本。

真源只有一个：references/entry-reminder.md（模板）+ RSI 当前 ACTIVE 版本号（取自共享数据库，只读）。
工作流一更新，所有会话下一条提示词就自动用上最新规则；不再维护手工复制的静态提醒副本。
任何失败都以非零退出码结束且不输出内容，由钩子命令回退到旧提醒文件，保证提醒不会整体丢失。
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

from sire_paths import DATA_DIR, LEDGER_ROOT

TEMPLATE = Path(__file__).resolve().parents[1] / "references" / "entry-reminder.md"
DB_PATH = DATA_DIR / "sire_vectors.sqlite3"


def current_version() -> str:
    """读取 RSI 当前 ACTIVE 版本号；读不到时写“版本未知”，不影响提醒本身。"""
    try:
        con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, timeout=2)
        try:
            row = con.execute("SELECT version FROM workflow_versions WHERE status='ACTIVE' "
                              "ORDER BY activated_at DESC LIMIT 1").fetchone()
        finally:
            con.close()
        return row[0] if row else "版本未知"
    except Exception:  # noqa: BLE001
        return "版本未知"


def health_line() -> str:
    """最近一次定时健康检查有异常时，给每个会话一行摘要（完整流程在 R0 向用户汇报）；读不到或没有异常返回空串。"""
    try:
        data = json.loads((LEDGER_ROOT / "health" / "last.json").read_text(encoding="utf-8"))
        items = data.get("anomalies") or []
        if not items:
            return ""
        counts = {s: sum(1 for a in items if a.get("severity") == s) for s in ("high", "medium", "low")}
        when = time.strftime("%m-%d %H:%M", time.localtime(data.get("ts", 0)))
        age_hours = (time.time() - float(data.get("ts", 0))) / 3600
        if age_hours > 26:  # 计划任务每 8 小时一次，超过 26 小时没有更新说明定时检查可能停摆
            when += f"，已 {age_hours:.0f} 小时没有更新，定时检查可能停摆"
        from sire_health import KNOWLEDGE  # 只接受已知异常代码，不信任文件里的任意字符串
        known = [a["code"] for a in items if a.get("code") in KNOWLEDGE]
        top = "、".join(known[:3])
        return (f"\n【最近一次定时健康检查 {when}】发现 {len(items)} 项异常（高 {counts['high']}/中 {counts['medium']}/低 {counts['low']}）："
                f"{top}。报告：{data.get('report', '')}。完整流程在 R0 向用户汇报；优化提案由工作流自己生成，等用户确认，不由助手自行提议。")
    except Exception:  # noqa: BLE001  提示是附加信息，失败不影响提醒本身
        return ""


def main() -> int:
    try:
        text = TEMPLATE.read_text(encoding="utf-8")
    except OSError:
        return 1
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(text.replace("{VERSION}", current_version()) + health_line())
    return 0


if __name__ == "__main__":
    sys.exit(main())
