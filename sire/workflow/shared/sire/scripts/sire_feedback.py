"""记录和汇总用户对 SIRE 执行方向/计划的反对意见。"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from sire_paths import KNOWLEDGE_DIR


def home_dir() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home()).expanduser()


def feedback_path() -> Path:
    return Path(os.environ.get("SIRE_FEEDBACK_LOG") or KNOWLEDGE_DIR / "feedback" / "plan-disagreements.jsonl")


def record(args: argparse.Namespace) -> int:
    path = feedback_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    item = {
        "id": datetime.now(timezone.utc).strftime("D%Y%m%dT%H%M%S%fZ"),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id or "",
        "phase": args.phase or "",
        "proposed_direction": args.proposed or "",
        "user_reason": args.reason,
        "user_preference": args.preference or "",
        "changed_action": args.changed_action or "",
        "tags": [item.strip() for item in (args.tags or "").split(",") if item.strip()],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(json.dumps({"recorded": True, "id": item["id"], "path": str(path)}, ensure_ascii=False))
    return 0


def load() -> list[dict[str, object]]:
    path = feedback_path()
    if not path.is_file():
        return []
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            result.append(json.loads(line))
    return result


def report(args: argparse.Namespace) -> int:
    records = load()
    tag_counts = Counter(tag for item in records for tag in item.get("tags", []))
    result = {"count": len(records), "path": str(feedback_path()), "tag_counts": tag_counts, "records": records if args.json else []}
    if args.json:
        result["tag_counts"] = dict(tag_counts)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    print(f"反对意见记录：{len(records)} 条")
    if tag_counts:
        print("边界标签：")
        for tag, count in tag_counts.most_common():
            print(f"- {tag}: {count}")
    for item in records[-10:]:
        print(f"- {item.get('recorded_at', '')} | {item.get('phase', '')} | {item.get('user_reason', '')}")
    return 0


def main() -> int:
    command = argparse.ArgumentParser(description="SIRE 计划反对意见记录")
    sub = command.add_subparsers(dest="command", required=True)
    add = sub.add_parser("record")
    add.add_argument("--reason", required=True)
    add.add_argument("--proposed")
    add.add_argument("--preference")
    add.add_argument("--changed-action")
    add.add_argument("--run-id")
    add.add_argument("--phase")
    add.add_argument("--tags", help="逗号分隔，例如 scope,risk,cost")
    sub.add_parser("report").add_argument("--json", action="store_true")
    args = command.parse_args()
    return record(args) if args.command == "record" else report(args)


if __name__ == "__main__":
    raise SystemExit(main())
