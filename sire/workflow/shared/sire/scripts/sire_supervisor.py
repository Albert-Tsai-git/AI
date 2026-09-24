"""SIRE R9 监督员：清单、快照、缺失检测、原因分类和打包完整性校验。"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sire_bundle import files_for, historical_specs, is_sensitive, kb_dir, target_specs
from sire_paths import DATABASE_PATH, SHARED_SKILL_DIR


INTEGRITY_DIR = kb_dir() / "integrity"
BASELINE_MANIFEST = INTEGRITY_DIR / "manifest.json"
SNAPSHOT_DIR = INTEGRITY_DIR / "snapshots"
RUNS_DIR = INTEGRITY_DIR / "runs"
EXCLUDED_INVENTORY_ROOTS = {SNAPSHOT_DIR.resolve(), RUNS_DIR.resolve()}
# R9 独立声明的必需清单（archive_path）：工作流包缺任一项即 package_omission；与 sire_bundle 的打包范围互相独立
REQUIRED_AGENT_NAMES = (
    "analyst", "code-reviewer", "code-reviewer-a", "code-reviewer-b", "code-reviewer-c", "decomposer",
    "implementer", "integrator", "librarian", "qa-tester", "spec-reviewer", "supervisor", "system-operator",
)
REQUIRED_ARCHIVE_ENTRIES = (
    "shared/sire/SKILL.md",
    "shared/sire/references/global-contract.md",
    "shared/sire/scripts/sire_paths.py",
    "shared/sire/scripts/sire_bundle.py",
    "shared/sire/scripts/sire_supervisor.py",
    "shared/sire/scripts/sire_run.py",
    "shared/sire/scripts/sire_kb.py",
    "shared/knowledge/SIRE-MIGRATION.md",
) + tuple(f"shared/sire/agents/claude/sire-{name}.md" for name in REQUIRED_AGENT_NAMES)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_output() -> None:
    """在 Windows 控制台保证中文和符号 JSON 可输出。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def excluded_inventory(path: Path) -> bool:
    resolved = path.resolve()
    return any(resolved == root or root in resolved.parents for root in EXCLUDED_INVENTORY_ROOTS)


def inventory(exclude_paths: set[Path] | None = None) -> list[dict[str, object]]:
    excluded = set(exclude_paths or set()) | EXCLUDED_INVENTORY_ROOTS
    pairs: dict[str, tuple[Path, str]] = {}
    for source, archive_root in target_specs() + historical_specs():
        for path, archive_name in files_for(source, archive_root, excluded):
            if excluded_inventory(path):
                continue
            pairs.setdefault(archive_name, (path, archive_name))
    result = []
    for path, archive_name in sorted(pairs.values(), key=lambda pair: pair[1].lower()):
        text = ""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (UnicodeDecodeError, OSError):
            pass
        result.append({
            "archive_path": archive_name,
            "source": str(path),
            "size": path.stat().st_size,
            "sha256": sha256(path),
            "line_count": len(text.splitlines()) if text else None,
            "sensitive": is_sensitive(path),
        })
    return result


def manifest_payload(entries: list[dict[str, object]], label: str) -> dict[str, object]:
    return {
        "format": "sire-integrity-manifest-v1",
        "label": label,
        "created_at": now(),
        "entry_count": len(entries),
        "entries": entries,
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_checklist(path: Path, payload: dict[str, object]) -> None:
    lines = [f"# SIRE R9 内容完整性清单（{payload['label']}）", "", f"生成时间：{payload['created_at']}", ""]
    for entry in payload["entries"]:
        lines.append(f"- [x] `{entry['archive_path']}` | {entry['size']} bytes | `{entry['sha256']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def snapshot(label: str, destination: Path | None = None, exclude_paths: set[Path] | None = None) -> tuple[Path, dict[str, object]]:
    entries = inventory(exclude_paths)
    destination = destination or SNAPSHOT_DIR / label
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for entry in entries:
        # 敏感文件只记哈希和大小，不复制副本；缺失检测仍按 archive_path/sha256 进行
        if entry.get("sensitive"):
            copied.append(dict(entry))
            continue
        source = Path(str(entry["source"]))
        target = destination / str(entry["archive_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
        shutil.copy2(source, target)
        item = dict(entry)
        item["snapshot_path"] = str(target)
        copied.append(item)
    payload = manifest_payload(copied, label)
    manifest_path = destination / "MANIFEST.json"
    write_json(manifest_path, payload)
    write_checklist(destination / "CHECKLIST.md", payload)
    return manifest_path, payload


def load_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"监督基线不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def classify_diff(baseline: dict[str, object], current: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    before = {str(item["archive_path"]): item for item in baseline.get("entries", [])}
    after = {str(item["archive_path"]): item for item in current}
    missing = []
    moved = []
    changed = []
    added = []
    for archive_path, old in before.items():
        if archive_path not in after:
            same_hash = [item for item in current if item["sha256"] == old["sha256"]]
            missing.append({"archive_path": archive_path, "classification": "deleted_or_missing", "source": old.get("source"), "same_hash_at": [item["archive_path"] for item in same_hash]})
            if same_hash:
                missing[-1]["classification"] = "moved"
        elif after[archive_path]["sha256"] != old["sha256"]:
            old_snapshot = Path(str(old.get("snapshot_path", "")))
            new_source = Path(str(after[archive_path]["source"]))
            removed_lines = None
            if old_snapshot.is_file() and new_source.is_file():
                old_lines = old_snapshot.read_text(encoding="utf-8", errors="replace").splitlines()
                new_lines = new_source.read_text(encoding="utf-8", errors="replace").splitlines()
                matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
                removed_lines = sum(i2 - i1 for tag, i1, i2, _, _ in matcher.get_opcodes() if tag in {"delete", "replace"})
            record = {"archive_path": archive_path, "classification": "overwritten_or_modified", "before_size": old.get("size"), "after_size": after[archive_path].get("size"), "removed_lines": removed_lines}
            if (old.get("size") or 0) > 0 and (after[archive_path].get("size") or 0) == 0:
                record["classification"] = "possible_content_loss"
            # 无快照副本可比对（敏感文件只记哈希、或副本已清理）时 removed_lines 为 None，退化为按大小判断，避免截断漏报
            elif (removed_lines is None or removed_lines > 0) and (after[archive_path].get("size") or 0) < (old.get("size") or 0) * 0.5:
                record["classification"] = "possible_content_loss"
            changed.append(record)
    for archive_path, item in after.items():
        if archive_path not in before:
            added.append({"archive_path": archive_path, "source": item.get("source"), "classification": "added"})
    return {"missing": missing, "changed": changed, "added": added}


def report_path(run_id: str | None = None) -> Path:
    return (RUNS_DIR / (run_id or "latest") / "supervisor-report.json")


def write_report(path: Path, status: str, baseline_path: Path, diff: dict[str, list[dict[str, object]]], mode: str) -> dict[str, object]:
    payload = {"format": "sire-supervisor-report-v1", "status": status, "mode": mode, "checked_at": now(), "baseline": str(baseline_path), "diff": diff}
    write_json(path, payload)
    return payload


def fail_if_loss(payload: dict[str, object]) -> int:
    diff = payload["diff"]
    losses = list(diff["missing"]) + [item for item in diff["changed"] if item["classification"] == "possible_content_loss"]
    if losses:
        print(json.dumps({"status": "STOP", "reason": "SIRE 关联内容可能丢失，已终止后续动作", "losses": losses}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def preflight() -> int:
    if not BASELINE_MANIFEST.is_file():
        manifest_path, payload = snapshot("baseline")
        write_json(BASELINE_MANIFEST, payload)
        print(json.dumps({"status": "INITIALIZED", "manifest": str(manifest_path), "entries": payload["entry_count"]}, ensure_ascii=False))
        return 0
    baseline = load_manifest(BASELINE_MANIFEST)
    diff = classify_diff(baseline, inventory())
    status = "PASS" if not diff["missing"] and not any(item["classification"] == "possible_content_loss" for item in diff["changed"]) else "STOP"
    payload = write_report(report_path(), status, BASELINE_MANIFEST, diff, "preflight")
    return fail_if_loss(payload) if status == "STOP" else (print(json.dumps(payload, ensure_ascii=False, indent=2)) or 0)


def start(run_id: str) -> int:
    result = preflight()
    if result != 0:
        return result
    manifest_path, payload = snapshot(run_id)
    run_manifest = RUNS_DIR / run_id / "before.json"
    write_json(run_manifest, payload)
    print(json.dumps({"status": "STARTED", "run_id": run_id, "before": str(run_manifest), "entries": payload["entry_count"]}, ensure_ascii=False))
    return 0


def check(run_id: str, unit_id: str | None) -> int:
    baseline_path = RUNS_DIR / run_id / "before.json"
    baseline = load_manifest(baseline_path)
    diff = classify_diff(baseline, inventory())
    report = RUNS_DIR / run_id / "supervisor-report.json"
    if unit_id:
        report = RUNS_DIR / run_id / "supervisor" / f"{unit_id}.json"
    status = "PASS" if not diff["missing"] and not any(item["classification"] == "possible_content_loss" for item in diff["changed"]) else "STOP"
    payload = write_report(report, status, baseline_path, diff, "unit-check" if unit_id else "run-check")
    return fail_if_loss(payload) if status == "STOP" else (print(json.dumps(payload, ensure_ascii=False, indent=2)) or 0)


# 这些状态的提案才算"已登记且未失败"；EVALUATED_FAIL / ROLLED_BACK 的改动不应留在工作区
RSI_OPEN_STATUSES = ("PROPOSED", "EVALUATED_PASS", "ACTIVE")


def git_output(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        # git 不存在、超时或 cwd 无效：由调用方按 fail-closed 处理
        return 127, ""
    return result.returncode, result.stdout + result.stderr if result.returncode else result.stdout


def rsi_proposals(db_path: Path) -> list[dict[str, str]]:
    """只读读取 RSI 提案；库或表不存在时返回空列表，不建表、不切换日志模式。"""
    if not db_path.is_file():
        return []
    try:
        conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    except sqlite3.Error:
        return []
    try:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute("SELECT proposal_id, status, created_at FROM improvement_proposals").fetchall()
    except sqlite3.Error:
        # 非 SQLite 文件、表缺失等都视为无提案，由门禁 fail-closed 判 STOP
        return []
    finally:
        conn.close()
    return [{"proposal_id": row[0], "status": row[1], "created_at": row[2]} for row in rows]


def rsi_gate(db_path: Path = DATABASE_PATH, skill_dir: Path = SHARED_SKILL_DIR) -> dict[str, object]:
    """R9 RSI 门禁：共享工作流目录有未提交改动时，必须存在该目录最后一次提交之后登记、且未失败的 RSI 提案。"""
    if not skill_dir.is_dir():
        return {"status": "SKIPPED", "reason": "工作流目录不存在", "skill_dir": str(skill_dir)}
    code, output = git_output(["rev-parse", "--show-toplevel"], skill_dir)
    if code != 0 and "not a git repository" in output.lower():
        return {"status": "SKIPPED", "reason": "工作流目录不在 Git 仓库中", "skill_dir": str(skill_dir)}
    # 其余无法确定 Git 状态的情况一律 fail-closed，不推进基线
    undetermined = {"status": "STOP", "classification": "rsi_git_undetermined", "skill_dir": str(skill_dir)}
    if code != 0:
        return {**undetermined, "reason": "git 不可用或 rev-parse 失败，无法判定工作流改动", "git_rc": code}
    code, porcelain = git_output(["--no-optional-locks", "status", "--porcelain", "--untracked-files=normal", "--", "."], skill_dir)
    if code != 0:
        return {**undetermined, "reason": "git status 执行失败，无法判定工作流改动", "git_rc": code}
    changed = [line[3:] for line in porcelain.splitlines() if line.strip()]
    if not changed:
        return {"status": "PASS", "reason": "工作流目录无未提交改动", "changed": []}
    code, last_commit = git_output(["log", "-1", "--format=%cI", "--", "."], skill_dir)
    if code != 0 and "does not have any commits" in last_commit:
        # 仓库尚无任何提交：按"从未提交"处理，下方只认评估流程中的提案
        code, last_commit = 0, ""
    if code != 0:
        return {**undetermined, "reason": "git log 执行失败，无法取得最后一次工作流提交时间", "git_rc": code, "changed": changed}
    last_commit = last_commit.strip()
    try:
        since = datetime.fromisoformat(last_commit) if last_commit else None
    except ValueError:
        return {**undetermined, "reason": "无法解析最后一次工作流提交时间", "last_workflow_commit": last_commit, "changed": changed}
    # 取不到最后提交时间时，不让早已激活的旧版本（ACTIVE）放行，只认尚在评估流程中的提案
    allowed = RSI_OPEN_STATUSES if since is not None else ("PROPOSED", "EVALUATED_PASS")
    matched = []
    for item in rsi_proposals(db_path):
        if item["status"] not in allowed:
            continue
        try:
            created = datetime.fromisoformat(item["created_at"])
        except (TypeError, ValueError):
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if since is None or created >= since:
            matched.append(item)
    payload = {"changed": changed, "last_workflow_commit": last_commit or None, "db": str(db_path), "matched_proposals": matched}
    if matched:
        return {"status": "PASS", "reason": "工作流改动已登记 RSI 提案", **payload}
    return {"status": "STOP", "classification": "rsi_unregistered_change",
            "reason": "工作流目录有未提交改动，但最后一次工作流提交之后没有登记未失败的 RSI 提案；先运行 sire_rsi.py propose",
            **payload}


def rsi_check(run_id: str | None = None) -> int:
    result = rsi_gate()
    if run_id:
        # 写入运行目录，避免 check 已写的 PASS 报告误导事后审计
        write_json(RUNS_DIR / run_id / "rsi-report.json", {"checked_at": now(), **result})
    stream = sys.stderr if result["status"] == "STOP" else sys.stdout
    print(json.dumps(result, ensure_ascii=False, indent=2), file=stream)
    return 3 if result["status"] == "STOP" else 0


def finalize(run_id: str) -> int:
    result = check(run_id, None)
    if result != 0:
        return result
    # RSI 门禁失败时不推进基线，保证下次仍能发现同一批未登记改动
    if rsi_check(run_id) != 0:
        return 3
    manifest_path, payload = snapshot("baseline-next")
    write_json(BASELINE_MANIFEST, payload)
    print(json.dumps({"status": "FINALIZED", "run_id": run_id, "manifest": str(BASELINE_MANIFEST), "entries": payload["entry_count"]}, ensure_ascii=False))
    return 0


def verify_zip(path: Path, against_current: bool = False) -> int:
    if not path.is_file():
        print(json.dumps({"status": "STOP", "reason": "zip 不存在", "zip": str(path)}, ensure_ascii=False), file=sys.stderr)
        return 3
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "MANIFEST.json" not in names:
            print(json.dumps({"status": "STOP", "reason": "zip 缺少 MANIFEST.json"}, ensure_ascii=False), file=sys.stderr)
            return 3
        manifest = json.loads(archive.read("MANIFEST.json").decode("utf-8"))
    expected = set(manifest.get("included", []))
    missing = sorted(name for name in expected if name not in names)
    corrupted = []
    records = {str(item["archive_path"]): item for item in manifest.get("entry_records", [])}
    with zipfile.ZipFile(path) as archive:
        for archive_name, record in records.items():
            if archive_name not in names:
                continue
            digest = hashlib.sha256()
            size = 0
            with archive.open(archive_name, "r") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
                    size += len(block)
            expected_hash = str(record.get("sha256", ""))
            expected_size = int(record.get("size", -1))
            if digest.hexdigest() != expected_hash or size != expected_size:
                corrupted.append({
                    "archive_path": archive_name,
                    "classification": "package_content_mismatch",
                    "expected_size": expected_size,
                    "actual_size": size,
                    "expected_sha256": expected_hash,
                    "actual_sha256": digest.hexdigest(),
                })
    current_missing = []
    if against_current:
        sidecar = path.with_suffix(path.suffix + ".sha256")
        # 敏感文件按设计不进包，不计入"应在包内"
        current_expected = {str(item["archive_path"]) for item in inventory({path.resolve(), sidecar.resolve()}) if not item.get("sensitive")}
        current_missing = sorted(name for name in current_expected if name not in expected)
        missing = sorted(set(missing) | set(current_missing))
    # R9 独立必需清单：不依赖打包范围函数，打包范围被缩小时也能发现遗漏
    required_missing = sorted(name for name in REQUIRED_ARCHIVE_ENTRIES if name not in names)
    missing = sorted(set(missing) | set(required_missing))
    sensitive_leak = sorted(name for name in names if name not in {"MANIFEST.json", "MIGRATION-README.md"} and is_sensitive(name))
    status = "PASS" if not missing and not corrupted and not sensitive_leak else "STOP"
    if sensitive_leak:
        classification = "package_sensitive_leak"
    elif missing:
        classification = "package_omission"
    else:
        classification = "package_content_mismatch" if corrupted else None
    result = {
        "status": status,
        "zip": str(path),
        "expected": len(expected),
        "actual": len(names - {"MANIFEST.json"}),
        "missing": missing,
        "required_missing": required_missing,
        "current_inventory_missing": current_missing,
        "sensitive_leak": sensitive_leak,
        "corrupted": corrupted,
        "classification": classification,
    }
    invalid = bool(missing or corrupted or sensitive_leak)
    print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr if invalid else sys.stdout)
    return 0 if not invalid else 3


def main() -> int:
    configure_output()
    command = argparse.ArgumentParser(description="SIRE R9 内容监督员")
    sub = command.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    start_parser = sub.add_parser("start")
    start_parser.add_argument("--run-id", required=True)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--run-id", required=True)
    check_parser.add_argument("--unit-id")
    finalize_parser = sub.add_parser("finalize")
    finalize_parser.add_argument("--run-id", required=True)
    sub.add_parser("rsi-check")
    verify_parser = sub.add_parser("verify-zip")
    verify_parser.add_argument("--zip", required=True, type=Path)
    verify_parser.add_argument("--against-current", action="store_true")
    args = command.parse_args()
    if args.command == "preflight":
        return preflight()
    if args.command == "start":
        return start(args.run_id)
    if args.command == "check":
        return check(args.run_id, args.unit_id)
    if args.command == "finalize":
        return finalize(args.run_id)
    if args.command == "rsi-check":
        return rsi_check()
    return verify_zip(args.zip, args.against_current)


if __name__ == "__main__":
    raise SystemExit(main())
