"""打包 SIRE 工作流、兼容入口、全局规则和知识正文（轻量包：不含向量库、历史产物和敏感文件）。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from sire_paths import DATABASE_PATH, KNOWLEDGE_DIR, SHARED_SKILL_DIR


def home_dir() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home()).expanduser()


def kb_dir() -> Path:
    return KNOWLEDGE_DIR


def database_path() -> Path:
    return DATABASE_PATH


def target_specs() -> list[tuple[Path, str]]:
    return [
        (SHARED_SKILL_DIR, "shared/sire"),
        (SHARED_SKILL_DIR.parents[1] / "support" / "ai-workflow-governor", "support/ai-workflow-governor"),
        (kb_dir(), "shared/knowledge"),
    ]


def migration_readme() -> str:
    return r'''# SIRE 完整迁移操作说明

本 ZIP 包是 SIRE 工作流迁移包：包含工作流逻辑、全局规则、执行脚本和迁移说明；本包不包含本机知识/向量数据库，数据库继续保留在由目标机 `SIRE_ROOT` 配置的目录。

## 一、恢复文件

1. 解压 ZIP 到一个由两端都能访问的共享目录，按 `MANIFEST.json` 中的 `archive_path` 恢复。
2. 让 Codex 的 `~/.codex/skills/ai-dev-sire-workflow` 与 Claude 的 `~/.claude/skills/sire-global-workflow` 都链接到同一个 `shared/sire/` 目录；不要分别复制两份。
3. `shared/knowledge/` 是两端共同使用的知识目录；SQLite 数据库不在轻量 ZIP 中。
4. 数据库不随本包覆盖；如需迁移数据库，请在目标机配置 `SIRE_VECTOR_DB` 后单独复制。
5. 敏感文件不在包内（`secrets` 目录及 `.pem/.key/.pfx/.p12/.vault`）；需要时由用户单独迁移。

## 二、同步模式（保留目标机已有数据）

适用于目标机已有 SIRE 数据，需要合并新迁移内容时：

```powershell
python "<shared-sire>\scripts\sire_vector_db.py" index
python "<shared-sire>\scripts\sire_vector_db.py" migrate
python "<shared-sire>\scripts\sire_vector_db.py" stats
```

## 三、迁移后验收

```powershell
python "<shared-sire>\scripts\sire_vector_db.py" stats
python "<shared-sire>\scripts\sire_vector_db.py" search --query "SIRE 迁移 数据库" --json --limit 5
python "<shared-sire>\scripts\sire_supervisor.py" preflight
```

必须确认目标机 `SIRE_VECTOR_DB` 指向现有向量库；本包不覆盖数据库，迁移后由目标机现有数据库继续提供知识、任务和向量检索。
'''


def historical_specs() -> list[tuple[Path, str]]:
    """轻量包不含历史产物：历史 run 产物与向量库 SIRE_VECTOR_DB 由本机数据库和归档机制管理，不进入 ZIP。

    保留该函数作为 sire_supervisor.py 的清单扩展点，当前固定返回空列表。
    """
    return []


# 敏感文件：任一路径段为 secrets，或后缀属于下列集合（不区分大小写）。
# 打包时一律排除；R9 快照只记哈希、不复制。全工作流只在这里定义一次。
SENSITIVE_DIR_NAMES = {"secrets"}
SENSITIVE_SUFFIXES = {".pem", ".key", ".pfx", ".p12", ".vault"}


def is_sensitive(path: Path | str) -> bool:
    candidate = Path(path)
    if any(part.lower() in SENSITIVE_DIR_NAMES for part in candidate.parts):
        return True
    return candidate.suffix.lower() in SENSITIVE_SUFFIXES


def excluded(path: Path, exclude_paths: set[Path] | None = None) -> bool:
    parts = set(path.parts)
    if bool(parts & {"__pycache__", ".git", "node_modules", "integrity", "archive-20260921"}) or path.suffix.lower() in {".pyc", ".sqlite", ".sqlite3", ".db"}:
        return True
    # 默认输出目录 kb_dir()/exports 下是历史导出包：不打包、不进 R9 清单，避免旧包逐次嵌套；其他位置名为 exports 的目录不受影响
    exports_root = (kb_dir() / "exports").resolve()
    resolved = path.resolve()
    if resolved == exports_root or exports_root in resolved.parents:
        return True
    for excluded_path in exclude_paths or set():
        if path.resolve() == excluded_path or excluded_path in path.resolve().parents:
            return True
    return False


def files_for(source: Path, archive_root: str, exclude_paths: set[Path] | None = None) -> list[tuple[Path, str]]:
    if not source.exists():
        return []
    if source.is_file():
        return [] if excluded(source, exclude_paths) else [(source, archive_root)]
    result = []
    for file in source.rglob("*"):
        if file.is_file() and not excluded(file, exclude_paths):
            result.append((file, f"{archive_root}/{file.relative_to(source).as_posix()}"))
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def configure_output() -> None:
    """在 Windows 控制台保证中文 JSON 可输出。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def build(output: Path, dry_run: bool = False) -> dict[str, object]:
    output = output.resolve()
    sidecar = output.with_suffix(output.suffix + ".sha256")
    exclude_paths = {output, sidecar}
    entries: list[tuple[Path, str]] = []
    missing: list[str] = []
    specs = target_specs() + historical_specs()
    for source, archive_root in specs:
        # files_for 默认行为不变（R9 清单仍需看到敏感文件），只在打包时过滤
        found = [pair for pair in files_for(source, archive_root, exclude_paths) if not is_sensitive(pair[0])]
        if found:
            entries.extend(found)
        else:
            missing.append(str(source))
    required = {str(source.resolve()) for source, _ in target_specs()}
    missing_required = [item for item in missing if str(Path(item).resolve()) in required]
    if missing_required:
        raise FileNotFoundError("SIRE 关联内容缺失，停止打包: " + ", ".join(missing_required))
    entries.sort(key=lambda item: item[1].lower())
    entry_records = [
        {"source": str(source), "archive_path": archive_name, "size": source.stat().st_size, "sha256": sha256(source)}
        for source, archive_name in entries
    ]
    manifest = {
        "format": "sire-workflow-bundle-v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_home": str(home_dir()),
        "entries": len(entries),
        "missing_paths": missing,
        "historical_discovery": "轻量包不含历史产物：历史 run 产物由本机数据库和归档机制管理，不进入 ZIP",
        "sensitive_policy": "敏感文件（secrets 目录及 .pem/.key/.pfx/.p12/.vault）不进入 ZIP",
        "included": [archive_name for _, archive_name in entries],
        "entry_records": entry_records,
        "restore_notes": "完整迁移 = 本 ZIP + MIGRATION-README.md；按包内文档执行同步或覆盖；本包不含数据库，目标机对其现有数据库运行 index/migrate/preflight。",
    }
    if dry_run:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return manifest
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("MIGRATION-README.md", migration_readme())
        for source, archive_name in entries:
            archive.write(source, archive_name)
    digest = sha256(output)
    sidecar.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    supervisor = Path(__file__).with_name("sire_supervisor.py")
    if supervisor.is_file():
        subprocess.run([sys.executable, str(supervisor), "verify-zip", "--zip", str(output), "--against-current"], check=True)
    manifest["output"] = str(output)
    manifest["sha256"] = digest
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> int:
    configure_output()
    command = argparse.ArgumentParser(description="打包 SIRE 工作流、规则和知识正文（不含向量库与历史产物）")
    command.add_argument("--output", type=Path)
    command.add_argument("--dry-run", action="store_true")
    command.add_argument("--lightweight", action="store_true", help="只打包工作流和规则，不包含数据库与历史归档")
    args = command.parse_args()
    if args.output:
        output = args.output
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = kb_dir() / "exports" / f"sire-workflow-{stamp}.zip"
    supervisor = Path(__file__).with_name("sire_supervisor.py")
    if supervisor.is_file() and not args.dry_run and not args.lightweight:
        subprocess.run([sys.executable, str(supervisor), "preflight"], check=True)
    build(output, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
