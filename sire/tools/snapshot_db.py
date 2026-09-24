#!/usr/bin/env python3
"""Create a sanitized, complete SIRE SQLite snapshot without changing its source."""
from __future__ import annotations

import argparse
import collections
import contextlib
import datetime as dt
import getpass
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PRIVATE_IP = re.compile(r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.(?:\d{1,3}\.)\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3})\b")
USER_ROOT = re.compile(r"(?i)C:[\\/]Users[\\/][^\\/\s<>:\"|]+")
DRIVE_ROOT = re.compile(r"(?i)(?<![A-Za-z0-9])([A-Z]):[\\/]")
SECRET_PATTERNS = {
    "pem_private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "bearer_credential": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    "credential_assignment": re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)\b\s*[:=]\s*['\"]?[^\s'\"#]{12,}"),
    "url_embedded_credential": re.compile(r"(?i)://[^/@:\s]{1,64}:[^/@\s]{8,}@"),
}


def redact(text: str, counts: collections.Counter) -> str:
    rules = ((re.compile(r"(?i)D:[\\/]code(?=[\\/\s.,;:)\]}]|$)"), "code_root", "@CODE_ROOT@"),
             (re.compile(r"(?i)D:[\\/]sire(?=[\\/\s.,;:)\]}]|$)"), "sire_root", "@SIRE_ROOT@"))
    for pattern, label, replacement in rules:
        text, n = pattern.subn(replacement, text)
        counts[label] += n
    text, n = USER_ROOT.subn("@USER_HOME@", text)
    counts["user_home"] += n
    text, n = DRIVE_ROOT.subn(lambda m: "@DRIVE_" + m.group(1).upper() + "@/", text)
    counts["drive_root"] += n
    text, n = EMAIL.subn("[email-redacted]", text)
    counts["email"] += n
    text, n = PRIVATE_IP.subn("[private-ip-redacted]", text)
    counts["private_ip"] += n
    return text


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    virtual = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE 'CREATE VIRTUAL TABLE%'")}
    shadows = tuple(name + "_" for name in virtual)
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql NOT LIKE 'CREATE VIRTUAL TABLE%'")
             if not any(r[0].startswith(prefix) for prefix in shadows)]
    return {name: conn.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0] for name in sorted(names)}


def privacy_scan(conn: sqlite3.Connection) -> dict[str, int]:
    """Scan SQL TEXT values and printable byte sequences for specified patterns."""
    found = collections.Counter()
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for table in names:
        qtable = '"' + table.replace('"', '""') + '"'
        columns = [r[1] for r in conn.execute('PRAGMA table_info(' + qtable + ')') if r[2].upper() in ('TEXT', '')]
        if not columns:
            continue
        sql = 'SELECT ' + ','.join('"' + col.replace('"', '""') + '"' for col in columns) + ' FROM ' + qtable
        for row in conn.execute(sql):
            for value in row:
                if not isinstance(value, str):
                    continue
                for name, pattern in SECRET_PATTERNS.items():
                    found[name] += len(pattern.findall(value))
                found['windows_absolute_path'] += len(re.findall(r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/]", value))
                found['email'] += len(EMAIL.findall(value))
                found['private_ip'] += len(PRIVATE_IP.findall(value))
    return dict(found)


def allocate_temp(parent: Path, prefix: str, owned: set[Path]) -> Path:
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=parent)
    os.close(fd)
    path = Path(name)
    owned.add(path)
    return path


def _private_root() -> Path:
    return Path(tempfile.gettempdir()).resolve()


def _remove_private_dir(path: Path) -> None:
    path = path.resolve()
    root = _private_root()
    if path.parent != root or not path.name.startswith("sire-db-private-") or path.is_symlink():
        raise RuntimeError("refusing to remove path outside the private SIRE staging directory")
    shutil.rmtree(path)


def harden_private_dir(path: Path) -> None:
    """Restrict raw staging to its owner (and system administrators on Windows)."""
    if os.name == "nt":
        username = os.environ.get("USERNAME") or getpass.getuser()
        domain = os.environ.get("USERDOMAIN")
        principal = (domain + "\\" + username) if domain else username
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r",
             principal + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        if result.returncode:
            raise RuntimeError("cannot secure the private SQLite staging directory with icacls")
    else:
        os.chmod(path, 0o700)


@contextlib.contextmanager
def target_lock(dest: Path):
    """Serialize snapshot publication for one destination across processes."""
    lock_root = _private_root() / "sire-snapshot-locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(dest.resolve()).casefold().encode("utf-8")).hexdigest()
    lock_path = lock_root / (key + ".lock")
    pending_path = lock_root / (key + ".pending.json")
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
            try:
                yield lock_root, pending_path
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield lock_root, pending_path
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _safe_private_path(path: Path, private_dir: Path) -> bool:
    try:
        return path.resolve().parent == private_dir.resolve()
    except OSError:
        return False


def recover_pending(dest: Path, manifest_path: Path, pending_path: Path) -> None:
    """Finish a complete pair or restore both previous files after interruption."""
    if not pending_path.exists():
        return
    record = json.loads(pending_path.read_text(encoding="utf-8"))
    if Path(record.get("dest", "")).resolve() != dest.resolve() or Path(record.get("manifest", "")).resolve() != manifest_path.resolve():
        raise RuntimeError("pending SIRE snapshot marker targets do not match the locked destination")
    private_dir = Path(record.get("private_dir", "")).resolve()
    if private_dir.parent != _private_root() or not private_dir.name.startswith("sire-db-private-"):
        raise RuntimeError("pending SIRE snapshot marker references an unsafe recovery directory")
    remove_empty_snapshot_sidecars(dest)
    expected_db, expected_manifest = record["new_db_sha256"], record["new_manifest_sha256"]
    pair_complete = (dest.is_file() and manifest_path.is_file()
                     and sha256(dest) == expected_db and sha256(manifest_path) == expected_manifest)
    if not pair_complete:
        for key, target, was_present, old_hash, expected_hash in (
            ("prior_db", dest, record["had_db"], record.get("old_db_sha256"), expected_db),
            ("prior_manifest", manifest_path, record["had_manifest"], record.get("old_manifest_sha256"), expected_manifest),
        ):
            backup = Path(record[key]) if record.get(key) else None
            if was_present:
                if backup is None or not _safe_private_path(backup, private_dir) or not backup.is_file() or sha256(backup) != old_hash:
                    raise RuntimeError("snapshot recovery copy is missing or does not match its recorded hash")
                restore_tmp = allocate_temp(target.parent, ".sire-restore-", set())
                try:
                    shutil.copy2(backup, restore_tmp)
                    os.replace(restore_tmp, target)
                finally:
                    restore_tmp.unlink(missing_ok=True)
            elif target.exists():
                if sha256(target) != expected_hash:
                    raise RuntimeError("snapshot target changed after interrupted publication; refusing to overwrite it")
                target.unlink()
    for staged in record.get("staged_outputs", []):
        path = Path(staged)
        if path.parent.resolve() == dest.parent.resolve() and path.name.endswith(".tmp"):
            path.unlink(missing_ok=True)
    pending_path.unlink()
    _remove_private_dir(private_dir)


def cleanup_abandoned_private_dirs(lock_root: Path) -> None:
    """Remove only SIRE staging directories owned by dead processes and not referenced by recovery markers."""
    referenced = set()
    for marker in lock_root.glob("*.pending.json"):
        try:
            referenced.add(str(Path(json.loads(marker.read_text(encoding="utf-8"))["private_dir"]).resolve()))
        except (OSError, ValueError, KeyError):
            continue
    root = _private_root()
    for path in root.glob("sire-db-private-*"):
        if path.is_symlink() or not path.is_dir() or str(path.resolve()) in referenced:
            continue
        try:
            pid = int(path.name.removeprefix("sire-db-private-").split("-", 1)[0])
            os.kill(pid, 0)
        except ProcessLookupError:
            _remove_private_dir(path)
        except (PermissionError, ValueError, IndexError, OSError):
            continue


def source_connection_uri(source_path: Path) -> str:
    """Open a read-only SQLite view that includes committed WAL content."""
    journal = Path(str(source_path) + "-journal")
    wal = Path(str(source_path) + "-wal")
    if journal.exists():
        raise RuntimeError("source has a rollback journal; refusing to touch an in-progress SQLite transaction")
    with source_path.open("rb") as stream:
        header = stream.read(20)
    if len(header) < 20:
        raise RuntimeError("source is not a complete SQLite database")
    return source_path.as_uri() + "?mode=ro"


@contextlib.contextmanager
def exclusive_path_guard(path: Path, share_mode: int = 0x00000004):
    """Deny new SQLite opens while replacing a file, while allowing Windows rename."""
    handle = None
    if path.exists():
        if os.name != "nt":
            raise RuntimeError("safe replacement of an existing SQLite file is only supported on Windows; use a new destination")
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create_file.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        # FILE_SHARE_DELETE permits rename; callers may also allow concurrent read-only opens.
        handle = create_file(str(path), 0x80000000 | 0x40000000, share_mode,
                             None, 3, 0x80, None)
        invalid = ctypes.c_void_p(-1).value
        if handle == invalid:
            raise RuntimeError("SQLite file is open or cannot be locked for pair publication; close database clients and retry")
    try:
        yield handle
    finally:
        if handle is not None:
            close_handle(handle)


def remove_empty_snapshot_sidecars(dest: Path) -> None:
    """Remove only empty WAL/SHM files; never discard a journal or committed WAL."""
    journal = Path(str(dest) + "-journal")
    wal = Path(str(dest) + "-wal")
    shm = Path(str(dest) + "-shm")
    if journal.exists() or (wal.exists() and wal.stat().st_size):
        raise RuntimeError("snapshot target has rollback or WAL data; refusing sidecar cleanup")
    wal.unlink(missing_ok=True)
    shm.unlink(missing_ok=True)


def destination_state(dest: Path) -> dict[str, object]:
    """Capture the old target without changing its journal mode or sidecars."""
    if not dest.exists():
        return {"exists": False}
    with dest.open("rb") as stream:
        header = stream.read(20)
    if len(header) < 20 or header[:16] != b"SQLite format 3\x00" or header[18:20] not in (b"\x01\x01", b"\x02\x02"):
        raise RuntimeError("destination is not a supported SQLite database")
    journal = Path(str(dest) + "-journal")
    wal = Path(str(dest) + "-wal")
    if journal.exists():
        raise RuntimeError("destination has a rollback journal; close database clients and retry")
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError("destination has a nonempty WAL; checkpoint/close clients before replacing it")
    return {"exists": True, "sha256": sha256(dest), "journal_mode": header[18:20].hex()}


def regular_file_state(path: Path) -> dict[str, object]:
    return {"exists": path.exists(), "sha256": sha256(path) if path.exists() else None}


def validate_destination_state(dest: Path, expected: dict[str, object]) -> None:
    """Ensure the destination did not change while the replacement snapshot was built."""
    if bool(expected.get("exists")) != dest.exists():
        raise RuntimeError("destination presence changed while the snapshot was being built")
    if dest.exists():
        with dest.open("rb") as stream:
            header = stream.read(20)
        if header[18:20].hex() != expected.get("journal_mode"):
            raise RuntimeError("destination journal mode changed while the snapshot was being built")
        if sha256(dest) != expected.get("sha256"):
            raise RuntimeError("destination database changed while the snapshot was being built")
    journal = Path(str(dest) + "-journal")
    wal = Path(str(dest) + "-wal")
    if journal.exists() or (wal.exists() and wal.stat().st_size):
        raise RuntimeError("destination acquired a rollback journal or nonempty WAL during snapshot construction")


def validate_regular_file_state(path: Path, expected: dict[str, object]) -> None:
    if bool(expected.get("exists")) != path.exists():
        raise RuntimeError("snapshot manifest presence changed while the snapshot was being built")
    if path.exists() and sha256(path) != expected.get("sha256"):
        raise RuntimeError("snapshot manifest changed while the snapshot was being built")


def publish_file(staged: Path, target: Path, replace_existing: bool) -> None:
    if replace_existing:
        os.replace(staged, target)
    elif os.name == "nt":
        os.rename(staged, target)  # Windows rename fails rather than replacing a newly-created target.
    else:
        os.link(staged, target)  # An atomic no-overwrite publish on the same filesystem.
        staged.unlink()


def rebuild_all_embeddings(conn: sqlite3.Connection, knowledge_index) -> int:
    """Recompute vectors for every logical record, including historical chunks."""
    model = knowledge_index.embedder()
    if model is None:
        raise RuntimeError("BGE model is unavailable; refusing a snapshot with stale or missing embeddings")
    rows = []
    for rid, title, keywords, body in conn.execute("SELECT record_id, title, keywords, body FROM knowledge_records"):
        text = knowledge_index.knowledge_text(title, keywords, body)
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
        rows.append(("knowledge", str(rid), digest, text))
    for cid, title, content in conn.execute("SELECT id, title, content FROM chunks"):
        text = "%s\n%s" % (title, content)
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
        rows.append(("chunk", str(cid), digest, text))
    # Embeddings are derived from normalized text. Drop every stored model first,
    # since an unavailable legacy model must not survive with stale hashes.
    conn.execute("DELETE FROM emb")
    vectors = model.embed([row[3] for row in rows], batch_size=32)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    written = 0
    for row, vector in zip(rows, vectors):
        conn.execute("INSERT INTO emb(kind, ref, model, text_hash, vector, updated_at) VALUES(?,?,?,?,?,?)",
                     (row[0], row[1], knowledge_index.MODEL_NAME, row[2], knowledge_index._pack(vector), now))
        written += 1
    if written != len(rows):
        raise RuntimeError("BGE returned %d vectors for %d database rows" % (written, len(rows)))
    expected = {(kind, ref): digest for kind, ref, digest, _ in rows}
    actual = {(kind, ref): digest for kind, ref, digest in conn.execute(
        "SELECT kind, ref, text_hash FROM emb WHERE model = ?", (knowledge_index.MODEL_NAME,))}
    if actual != expected:
        raise RuntimeError("BGE embedding references or text hashes do not match all records")
    return written


def _snapshot_locked(source_path: Path, dest: Path, lock_root: Path, pending_path: Path) -> dict:
    source_path, dest = source_path.resolve(), dest.resolve()
    manifest_path = dest.with_name("snapshot-manifest.json")
    if not source_path.is_file():
        raise FileNotFoundError("source database not found")
    if source_path in (dest, manifest_path) or dest == manifest_path:
        raise ValueError("source, snapshot, and manifest destinations must be distinct")
    dest_state_before = destination_state(dest)
    manifest_state_before = regular_file_state(manifest_path)
    source_uri = source_connection_uri(source_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    owned: set[Path] = set()
    preserve_private = False
    source = tmp_conn = None
    private_dir = Path(tempfile.mkdtemp(prefix="sire-db-private-%d-" % os.getpid(), dir=_private_root()))
    try:
        harden_private_dir(private_dir)
    except BaseException:
        _remove_private_dir(private_dir)
        raise
    try:
        tmp = allocate_temp(private_dir, ".raw-sire-db-", owned)
        tmp_conn = sqlite3.connect(tmp)
        source_hash_before = sha256(source_path)
        source_sidecars_before = {suffix: sha256(Path(str(source_path) + suffix)) if Path(str(source_path) + suffix).exists() else None
                                  for suffix in ("-wal", "-journal")}
        source = sqlite3.connect(source_uri, uri=True)
        source.backup(tmp_conn)
        source.close()
        source = None
        source_hash_after = sha256(source_path)
        source_sidecars_after = {suffix: sha256(Path(str(source_path) + suffix)) if Path(str(source_path) + suffix).exists() else None
                                 for suffix in ("-wal", "-journal")}
        changed_source_files = []
        if source_hash_after != source_hash_before:
            changed_source_files.append("database")
        changed_source_files.extend(suffix for suffix in source_sidecars_before
                                    if source_sidecars_after[suffix] != source_sidecars_before[suffix])
        if changed_source_files:
            raise RuntimeError("source database state changed during read-only snapshot: " + ", ".join(changed_source_files))
        source_snapshot_hash = sha256(tmp)
        source_counts = counts(tmp_conn)
        journal_mode = tmp_conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower()
        if journal_mode != 'delete':
            raise RuntimeError('could not switch snapshot to DELETE journal mode')
        tmp_conn.execute("PRAGMA secure_delete=ON")
        if counts(tmp_conn) != source_counts:
            raise RuntimeError("SQLite online backup row counts changed")

        replacements = collections.Counter()
        virtual = {r[0] for r in tmp_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE 'CREATE VIRTUAL TABLE%'")}
        shadows = tuple(name + "_" for name in virtual)
        tables = [r for r in tmp_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND sql IS NOT NULL AND sql NOT LIKE 'CREATE VIRTUAL TABLE%' AND name NOT LIKE 'sqlite_%'").fetchall()
                  if not any(r[0].startswith(prefix) for prefix in shadows)]
        for (table,) in tables:
            qtable = '"' + table.replace('"', '""') + '"'
            info = tmp_conn.execute('PRAGMA table_info(' + qtable + ')').fetchall()
            all_columns = [row[1] for row in info]
            text_columns = {row[1] for row in info if row[2].upper() in ('TEXT', '')}
            key_positions = [i for i, row in enumerate(info) if row[5]]
            if not key_positions:
                raise RuntimeError('cannot safely normalize table without primary key: ' + table)
            select = 'SELECT ' + ','.join('"' + col.replace('"', '""') + '"' for col in all_columns) + ' FROM ' + qtable
            for row in tmp_conn.execute(select).fetchall():
                updates = {col: redact(row[i], replacements) for i, col in enumerate(all_columns)
                           if col in text_columns and isinstance(row[i], str)}
                updates = {col: value for col, value in updates.items() if value != row[all_columns.index(col)]}
                if updates:
                    where = ' AND '.join('"' + all_columns[i].replace('"', '""') + '"=?' for i in key_positions)
                    setter = ','.join('"' + col.replace('"', '""') + '"=?' for col in updates)
                    tmp_conn.execute('UPDATE ' + qtable + ' SET ' + setter + ' WHERE ' + where,
                                     tuple(updates.values()) + tuple(row[i] for i in key_positions))

        scripts = Path(__file__).resolve().parents[1] / 'workflow' / 'shared' / 'sire' / 'scripts'
        sys.path.insert(0, str(scripts))
        import sire_vector_db as vector_db
        import sire_knowledge_index as knowledge_index
        tmp_conn.row_factory = sqlite3.Row
        for row in tmp_conn.execute('SELECT id, content FROM chunks').fetchall():
            tmp_conn.execute('UPDATE chunks SET vector=? WHERE id=?', (vector_db.encode(row['content']), row['id']))
        tmp_conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        knowledge_index.rebuild_fts(tmp_conn)
        rebuilt_embeddings = rebuild_all_embeddings(tmp_conn, knowledge_index)
        tmp_conn.commit()

        text_scan = privacy_scan(tmp_conn)
        if any(text_scan.values()):
            raise RuntimeError('specified text scan found residual values: ' + json.dumps(text_scan, sort_keys=True))
        for name in ('chunks_fts', 'kfts', 'cfts'):
            tmp_conn.execute('INSERT INTO "' + name + '"("' + name + '",rank) VALUES(?,1)', ('integrity-check',))
        tmp_conn.execute('PRAGMA secure_delete=ON')
        tmp_conn.commit()
        tmp_conn.execute('VACUUM')
        tmp_conn.commit()
        final_counts = counts(tmp_conn)
        unchanged_tables = {name for name in source_counts if name != 'emb'}
        if any(final_counts.get(name) != source_counts.get(name) for name in unchanged_tables):
            raise RuntimeError('logical source table row counts changed during sanitization')
        integrity = tmp_conn.execute('PRAGMA integrity_check').fetchone()[0]
        page_count = tmp_conn.execute('PRAGMA page_count').fetchone()[0]
        freelist = tmp_conn.execute('PRAGMA freelist_count').fetchone()[0]
        if integrity != 'ok' or freelist != 0:
            raise RuntimeError('SQLite integrity/compaction check failed')
        expected_embeddings = (final_counts.get('knowledge_records', 0) + final_counts.get('chunks', 0))
        model_rows = tmp_conn.execute('SELECT count(*) FROM emb WHERE model=?', (knowledge_index.MODEL_NAME,)).fetchone()[0]
        if model_rows != expected_embeddings:
            raise RuntimeError('embedding row count does not cover all knowledge records and chunks')
        tmp_conn.close()
        tmp_conn = None
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = Path(str(tmp) + suffix)
            if sidecar.exists():
                raise RuntimeError('unexpected SQLite sidecar: ' + sidecar.name)
        if tmp.read_bytes()[18:20] != b'\x01\x01':
            raise RuntimeError('snapshot SQLite header is not in DELETE journal mode')

        raw = tmp.read_bytes()
        printable = '\n'.join(part.decode('ascii') for part in re.findall(rb'[ -~]{4,}', raw))
        raw_text = printable
        raw_scan = {name: len(pattern.findall(raw_text)) for name, pattern in SECRET_PATTERNS.items()}
        # General drive-path signatures in float BLOBs are noisy; exact known roots are checked bytewise.
        raw_scan['user_home_root'] = len(re.findall(r'(?i)C:[\\/]+Users[\\/]+[^\\/\x00\s<>:"|]+', raw_text))
        raw_scan['workspace_roots'] = len(re.findall(r'(?i)D:[\\/]+(?:code|sire)(?=[\\/\s.,;:)\]}]|$)', raw_text))
        raw_scan['email'] = len(EMAIL.findall(raw_text))
        raw_scan['private_ip'] = len(PRIVATE_IP.findall(raw_text))
        if any(raw_scan.values()):
            raise RuntimeError('specified printable-byte scan found residual values: ' + json.dumps(raw_scan, sort_keys=True))

        archive_db = os.environ.get("SIRE_ARCHIVE_DB")
        if archive_db and Path(archive_db).expanduser().resolve() == source_path.resolve():
            normalized_source = "@SIRE_ARCHIVE_ROOT@\\sire_vectors.sqlite3"
        else:
            normalized_source = redact(str(source_path), replacements)
        manifest = {
            'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'source': normalized_source,
            'source_snapshot_sha256_before_sanitization': source_snapshot_hash,
            'snapshot_sha256': sha256(tmp),
            'privacy_transformations': dict(replacements),
            'records_by_table': final_counts,
            'rebuilt_bge_embeddings': rebuilt_embeddings,
            'journal_mode': journal_mode,
            'validation': {
                'integrity_check': integrity,
                'journal_mode': journal_mode,
                'page_count': page_count,
                'freelist_count': freelist,
                'fts_integrity': 'ok',
                'all_knowledge_and_chunk_embeddings_rebuilt': True,
                'text_scan_scope': 'SQLite TEXT and undeclared-type columns; specified path, email, private-IP, and credential patterns',
                'text_scan_findings': text_scan,
                'printable_byte_scan_scope': 'printable byte sequences; specified credential, email, private-IP, and known local-root patterns',
                'printable_byte_scan_findings': raw_scan,
                'scan_limitations': 'Pattern scans cannot prove unknown, encoded, mutated, or unrecognized credentials are absent; numeric/vector BLOBs are not semantically scanned.',
                'source_read_mode': 'read-only SQLite online backup; committed WAL content is visible; source main/WAL/rollback-journal hashes must remain stable',
                'raw_staging': 'OS temporary directory with owner/admin restricted ACL on Windows or mode 0700 elsewhere; crash leftovers are reaped after owner process exit',
                'publication': 'per-database SIRE lock serializes snapshot/index/migration; Windows file guards block database access during pair replacement; recovery marker and rollback copies repair interrupted publication',
                'sqlite_sidecars': False,
            },
        }
        manifest_tmp = allocate_temp(dest.parent, '.snapshot-manifest.sire-', owned)
        manifest_tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        new_manifest_hash = sha256(manifest_tmp)
        publish_db_tmp = allocate_temp(dest.parent, "." + dest.name + ".sire-publish-", owned)
        shutil.copy2(tmp, publish_db_tmp)
        if sha256(publish_db_tmp) != manifest['snapshot_sha256']:
            raise RuntimeError("sanitized database staging copy hash mismatch")

        # Lock old outputs while validating and copying rollback files. Release the old-file
        # handles immediately before rename (Windows refuses replacement while a client holds
        # its own handle); the staged-file guards then keep the new DB unavailable until both
        # the DB and manifest have been published.
        with exclusive_path_guard(dest, share_mode=0x00000005), exclusive_path_guard(manifest_path, share_mode=0x00000005):
            validate_destination_state(dest, dest_state_before)
            validate_regular_file_state(manifest_path, manifest_state_before)
            had_db, had_manifest = dest.exists(), manifest_path.exists()
            prior_db = private_dir / "previous-snapshot.sqlite3" if had_db else None
            prior_manifest = private_dir / "previous-manifest.json" if had_manifest else None
            if prior_db:
                shutil.copy2(dest, prior_db)
            if prior_manifest:
                shutil.copy2(manifest_path, prior_manifest)
            record = {
                "dest": str(dest), "manifest": str(manifest_path), "private_dir": str(private_dir),
                "had_db": had_db, "had_manifest": had_manifest,
                "prior_db": str(prior_db) if prior_db else None,
                "prior_manifest": str(prior_manifest) if prior_manifest else None,
                "old_db_sha256": sha256(prior_db) if prior_db else None,
                "old_manifest_sha256": sha256(prior_manifest) if prior_manifest else None,
                "new_db_sha256": manifest['snapshot_sha256'], "new_manifest_sha256": new_manifest_hash,
                "staged_outputs": [str(publish_db_tmp), str(manifest_tmp)],
            }
            marker_tmp = allocate_temp(lock_root, ".pending-create-", owned)
            marker_tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            with exclusive_path_guard(publish_db_tmp), exclusive_path_guard(manifest_tmp):
                validate_destination_state(dest, dest_state_before)
                validate_regular_file_state(manifest_path, manifest_state_before)
                os.replace(marker_tmp, pending_path)
                owned.discard(marker_tmp)
                remove_empty_snapshot_sidecars(dest)
                publish_file(publish_db_tmp, dest, bool(record["had_db"]))
                owned.discard(publish_db_tmp)
                publish_file(manifest_tmp, manifest_path, bool(record["had_manifest"]))
                owned.discard(manifest_tmp)
                pending_path.unlink()
        except BaseException:
            if pending_path.exists():
                try:
                    recover_pending(dest, manifest_path, pending_path)
                except BaseException:
                    preserve_private = True
                    raise
            raise

        return {'snapshot': str(dest), 'manifest': str(manifest_path), 'sha256': manifest['snapshot_sha256'],
                'tables': len(final_counts), 'size_bytes': dest.stat().st_size, 'integrity_check': integrity,
                'freelist_count': freelist, 'rebuilt_bge_embeddings': rebuilt_embeddings,
                'privacy_pattern_scan': 'clean', 'sidecars': False, 'journal_mode': journal_mode,
                'source_read_mode': 'read-only SQLite online backup (WAL-visible)',
                'pair_publication': 'per-database lock, Windows file-share guards, and crash-recovery marker'}
    finally:
        if source is not None:
            source.close()
        if tmp_conn is not None:
            tmp_conn.close()
        for path in owned:
            for candidate in (path, Path(str(path) + '-wal'), Path(str(path) + '-shm')):
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    pass
        if not preserve_private and private_dir.exists():
            _remove_private_dir(private_dir)


def snapshot_main(source_path: Path, dest: Path) -> dict:
    dest = dest.resolve()
    manifest_path = dest.with_name("snapshot-manifest.json")
    with target_lock(dest) as (lock_root, pending_path):
        recover_pending(dest, manifest_path, pending_path)
        cleanup_abandoned_private_dirs(lock_root)
        return _snapshot_locked(source_path, dest, lock_root, pending_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--dest', required=True, type=Path)
    args = parser.parse_args()
    result = snapshot_main(args.source, args.dest)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
