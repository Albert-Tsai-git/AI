"""One canonical path map used by the Claude and Codex SIRE entry points."""
from __future__ import annotations

import os
from pathlib import Path

SHARED_SKILL_DIR = Path(__file__).resolve().parents[1]
SIRE_PACKAGE_ROOT = SHARED_SKILL_DIR.parents[2]
SIRE_ROOT = Path(os.environ.get("SIRE_ROOT") or SIRE_PACKAGE_ROOT).expanduser().resolve()
DATA_DIR = Path(os.environ.get("SIRE_DATA_DIR") or SIRE_ROOT / "data").expanduser()
DATABASE_PATH = Path(os.environ.get("SIRE_VECTOR_DB") or DATA_DIR / "sire_vectors.sqlite3").expanduser()
KNOWLEDGE_DIR = Path(os.environ.get("SIRE_KB_DIR") or SIRE_ROOT / "knowledge" / "global").expanduser()
MODEL_DIR = Path(os.environ.get("SIRE_EMBED_DIR") or Path.home() / "sire" / "models").expanduser()


def task_roots() -> list[Path]:
    configured = os.environ.get("SIRE_TASK_ROOTS")
    if configured:
        roots = [Path(item).expanduser() for item in configured.split(os.pathsep) if item]
    else:
        roots = [Path.cwd(), Path.home() / "Documents" / "Codex", SIRE_ROOT]
    unique: dict[str, Path] = {}
    for root in roots:
        resolved = root.resolve()
        unique.setdefault(str(resolved).casefold(), resolved)
    return list(unique.values())
