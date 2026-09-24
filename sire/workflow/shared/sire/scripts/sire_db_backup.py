"""Create and verify a SQLite online backup for the SIRE vector database."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from sire_paths import DATABASE_PATH


def main() -> int:
    ap = argparse.ArgumentParser()
    backup_root = Path.home() / "sire" / "db-backups"
    ap.add_argument("--db", type=Path, default=DATABASE_PATH)
    ap.add_argument("--backup-dir", type=Path, default=Path(os.environ.get("SIRE_DB_BACKUP_DIR") or backup_root))
    ap.add_argument("--keep", type=int, default=14)
    args = ap.parse_args()
    args.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dst = args.backup_dir / f"sire_vectors-{stamp}.sqlite3"
    src = sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        out = sqlite3.connect(str(dst))
        try:
            src.backup(out)
            out.commit()
            integrity = out.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"backup integrity failed: {integrity}")
            counts = {name: out.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                      for name in ("chunks", "knowledge_records", "task_records", "keywords")}
        finally:
            out.close()
    finally:
        src.close()
    backups = sorted(args.backup_dir.glob("sire_vectors-*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[args.keep:]:
        old.unlink()
    print(json.dumps({"backup": str(dst), "bytes": dst.stat().st_size, "integrity": integrity, "counts": counts, "retained": min(len(backups), args.keep)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
