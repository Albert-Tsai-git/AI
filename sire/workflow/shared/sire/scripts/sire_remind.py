"""SIRE 入口提醒生成器：每次提交提示词时由客户端钩子调用，从正本实时生成提醒文本。

真源只有一个：references/entry-reminder.md（模板）+ RSI 当前 ACTIVE 版本号（取自共享数据库，只读）。
工作流一更新，所有会话下一条提示词就自动用上最新规则；不再维护手工复制的静态提醒副本。
任何失败都以非零退出码结束且不输出内容，由钩子命令回退到旧提醒文件，保证提醒不会整体丢失。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from sire_paths import DATA_DIR

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


def main() -> int:
    try:
        text = TEMPLATE.read_text(encoding="utf-8")
    except OSError:
        return 1
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(text.replace("{VERSION}", current_version()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
