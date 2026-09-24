"""SIRE 本地向量知识库。

默认只使用 Python 标准库，避免在任务启动前等待依赖安装或网络服务。
向量由稳定的词/字符 n-gram 哈希生成，存入 SQLite，查询时计算余弦相似度。
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from sire_paths import DATABASE_PATH, KNOWLEDGE_DIR, SHARED_SKILL_DIR, task_roots as shared_task_roots


DIMENSION = 384
SCHEMA_VERSION = "2"
TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".py", ".ps1", ".sh", ".js", ".ts",
    ".tsx", ".jsx", ".html", ".css", ".sql",
}
SKIP_DIRS = {".git", "__pycache__", "node_modules", "vector_db", "exports", "integrity"}
WORD_RE = re.compile(r"[A-Za-z0-9_./:@+-]+|[\u4e00-\u9fff]+")


def require_delete_password() -> None:
    """Require a second-factor password before destructive DB maintenance."""
    expected = os.environ.get("SIRE_DB_DELETE_PASSWORD_SHA256", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RuntimeError(
            "数据库删除保护未配置：请设置 SIRE_DB_DELETE_PASSWORD_SHA256（密码的 SHA-256），"
            "拒绝执行删除/VACUUM。"
        )
    supplied = getpass.getpass("输入数据库删除确认密码：")
    actual = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise PermissionError("数据库删除确认密码错误，已拒绝删除/VACUUM。")


def deletion_authorized() -> bool:
    """Deletion is opt-in; password alone is never sufficient."""
    if os.environ.get("SIRE_DB_ALLOW_DELETE") != "1":
        return False
    require_delete_password()
    return True


def backup_before_mutation(path: Path) -> None:
    """Create a verified online backup before any index/migration mutation."""
    backup_script = Path(__file__).with_name("sire_db_backup.py")
    result = os.spawnv(os.P_WAIT, sys.executable, [sys.executable, str(backup_script), "--db", str(path)])
    if result != 0:
        raise RuntimeError(f"数据库预备份失败，拒绝继续写入: exit={result}")


@contextlib.contextmanager
def database_mutation_lock(path: Path):
    """Share the snapshot/recovery lock so index and migration cannot race a Git snapshot."""
    tools_dir = Path(__file__).resolve().parents[4] / "tools"
    sys.path.insert(0, str(tools_dir))
    try:
        import snapshot_db
        db = path.resolve()
        manifest = db.with_name("snapshot-manifest.json")
        with snapshot_db.target_lock(db) as (lock_root, pending_path):
            snapshot_db.recover_pending(db, manifest, pending_path)
            snapshot_db.cleanup_abandoned_private_dirs(lock_root)
            yield
    finally:
        try:
            sys.path.remove(str(tools_dir))
        except ValueError:
            pass


def configure_output() -> None:
    """在 Windows 控制台保证中文和符号 JSON 可输出。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def home_dir() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home()).expanduser()


def default_kb_dir() -> Path:
    return KNOWLEDGE_DIR


def db_path() -> Path:
    return DATABASE_PATH


def workflow_dirs() -> list[Path]:
    configured = os.environ.get("SIRE_WORKFLOW_DIR")
    return [Path(configured).expanduser()] if configured else [SHARED_SKILL_DIR]


def global_files() -> list[Path]:
    configured = os.environ.get("SIRE_GLOBAL_FILES")
    return [Path(item).expanduser() for item in configured.split(os.pathsep) if item] if configured else []


def source_paths() -> list[Path]:
    roots = [default_kb_dir(), *workflow_dirs()]
    files: set[Path] = set()
    for root in roots:
        if root.is_file():
            files.add(root.resolve())
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            # ★ 2026-09-24 派生索引/配置/备份文件不再切片入库
            if path.name.lower() in ("global_index.json", "settings.json", "settings.local.json", "global_knowledge_records.md", "knowledge_template.md") or ".bak" in path.name.lower():
                continue
            files.add(path.resolve())
    for path in global_files():
        if path.is_file():
            files.add(path.resolve())
    # 历史任务台账同时进入向量索引，保证任务前检索也能参考过去的执行记录。
    for root in task_roots():
        if not root.is_dir():
            continue
        for run in run_directories(root):
            for path in run.rglob("*"):
                if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                    files.add(path.resolve())
    return sorted(files, key=lambda p: str(p).lower())


def connect(path: Path) -> sqlite3.Connection:
    """Open a writable connection for index and migration operations."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            vector BLOB NOT NULL,
            metadata TEXT NOT NULL,
            UNIQUE(path, chunk_index)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_records (
            record_id TEXT PRIMARY KEY,
            record_type TEXT NOT NULL,
            title TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            keywords TEXT NOT NULL,
            body TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_records (
            record_key TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            project_path TEXT NOT NULL,
            record_path TEXT NOT NULL,
            record_type TEXT NOT NULL,
            content TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            keyword TEXT PRIMARY KEY,
            keyword_type TEXT NOT NULL,
            hit_count INTEGER NOT NULL,
            source_count INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(source_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_keywords_type ON keywords(keyword_type)")
    migrations = {
        "domain": "TEXT NOT NULL DEFAULT 'general'",
        "kind": "TEXT NOT NULL DEFAULT 'reference'",
        "status": "TEXT NOT NULL DEFAULT 'active'",
        "scope": "TEXT NOT NULL DEFAULT 'global'",
        "confidence": "REAL NOT NULL DEFAULT 0.5",
        "version": "TEXT NOT NULL DEFAULT '1'",
    }
    for table in ("chunks", "knowledge_records", "task_records"):
        existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, definition in migrations.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_relations (
        relation_id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
        relation_type TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 0.5,
        created_at TEXT NOT NULL, UNIQUE(source_id, target_id, relation_type)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_domain ON chunks(domain)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_domain ON knowledge_records(domain)")
    conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        title, content, domain, kind, content='chunks', content_rowid='id'
    )""")
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('dimension', ?)", (str(DIMENSION),))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('encoder', ?)", ("hash-ngram-v1",))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('retrieval', ?)", ("hybrid-fts5-cosine-v1",))
    return conn


def connect_readonly(path: Path) -> sqlite3.Connection:
    """Open an existing database without changing its journal mode or schema."""
    if not path.is_file():
        raise FileNotFoundError(f"向量库不存在: {path}")
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def classify(path: Path, title: str, content: str) -> tuple[str, str, str, str, float]:
    text = f"{path} {title} {content}".lower()
    domains = [("embedded", ("固件", "firmware", "寄存器", "stm32", "rs485", "bootloader", "舵机", "编码器", "foc", "霍尔")),
               ("frontend", ("frontend", "前端", "react", "vue", "css", "html", "electron", "uplot", "i18n")),
               ("backend", ("backend", "后端", "api", "fastapi", "django", "node")),
               ("database", ("database", "数据库", "sqlite", "sql", "vector", "向量")),
               ("mes", ("mes", "制造执行", "生产管理")),
               ("sire", ("sire", "workflow", "工作流")),
               ("testing", ("test", "测试", "验收", "review")),
               ("devops", ("devops", "部署", "ci", "cd", "git")),
               ("life", ("生活常识", "life", "cooking", "travel"))]

    # ★ 2026-09-24 英文词按词边界匹配（原子串匹配会把 decision/specific 里的 "ci" 判成 devops）
    def has(term: str) -> bool:
        if re.fullmatch(r"[a-z0-9]+", term):
            return re.search(rf"(?<![a-z0-9]){term}(?![a-z0-9])", text) is not None
        return term in text
    domain = next((name for name, terms in domains if any(has(term) for term in terms)), "general")
    kind = "task" if "task" in text or ".sire" in text or "任务" in text else "reference"
    status = "verified" if any(term in text for term in ("验收通过", "verified", "pass", "通过")) else "active"
    scope = "life" if domain == "life" else ("workflow" if domain == "sire" else "global")
    confidence = 0.9 if status == "verified" else 0.6
    return domain, kind, status, scope, confidence


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def chunks(text: str, size: int = 1800, overlap: int = 240) -> Iterable[tuple[int, str]]:
    text = text.replace("\r\n", "\n")
    if not text.strip():
        return
    start = 0
    index = 0
    step = max(1, size - overlap)
    while start < len(text):
        end = min(len(text), start + size)
        piece = text[start:end].strip()
        if piece:
            yield index, piece
            index += 1
        if end == len(text):
            break
        start += step


def features(text: str) -> list[str]:
    result: list[str] = []
    for token in WORD_RE.findall(text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            result.extend(token[i : i + n] for n in (1, 2, 3) for i in range(max(0, len(token) - n + 1)))
        else:
            result.append(token)
    return result


def encode(text: str) -> bytes:
    values = [0.0] * DIMENSION
    counts: dict[str, int] = {}
    for item in features(text):
        counts[item] = counts.get(item, 0) + 1
    for item, count in counts.items():
        digest = hashlib.blake2b(item.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "little") % DIMENSION
        sign = 1.0 if digest[4] & 1 else -1.0
        values[bucket] += sign * (1.0 + math.log1p(count))
    norm = math.sqrt(sum(value * value for value in values))
    if norm:
        values = [value / norm for value in values]
    return struct.pack(f"<{DIMENSION}f", *values)


def decode(blob: bytes) -> tuple[float, ...]:
    return struct.unpack(f"<{DIMENSION}f", blob)


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right))


def title_for(path: Path, text: str) -> str:
    for line in text.splitlines()[:12]:
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("# ").strip()[:160] or path.name
    return path.name


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def index_database(path: Path) -> dict[str, int]:
    backup_before_mutation(path)
    conn = connect(path)
    current = source_paths()
    current_names = {str(item) for item in current}
    # ★ 2026-09-22 只增不减: 同一 path 可保留多个版本 (多个 source_hash)。
    #   原实现取 MAX(source_hash) 判是否变化 —— 多版本共存后按字典序取到的不一定是当前版本,
    #   会导致每次 index 都误判"已变化"而重复追加; 改为"当前 hash 在该 path 已有 hash 集合里即跳过"。
    existing_hashes: dict[str, set[str]] = {}
    max_index: dict[str, int] = {}
    for row in conn.execute("SELECT path, source_hash, MAX(chunk_index) AS mi FROM chunks GROUP BY path, source_hash"):
        existing_hashes.setdefault(row["path"], set()).add(row["source_hash"])
        max_index[row["path"]] = max(max_index.get(row["path"], -1), int(row["mi"]))
    existing = existing_hashes
    inserted = 0
    unchanged = 0
    removed = 0
    appended_versions = 0
    destructive_sources = [
        source_name for source_name, old_hashes in existing.items()
        if source_name not in current_names or sha256(Path(source_name)) not in old_hashes
    ]
    allow_delete = bool(destructive_sources) and deletion_authorized()
    for source in current:
        source_name = str(source)
        source_hash = sha256(source)
        if source_hash in existing.get(source_name, set()):
            unchanged += 1
            continue
        text = read_text(source)
        # 默认只增不减: 未授权删除时, 新版本 chunk 编号接在该 path 已有最大编号之后追加,
        #   旧版本 chunk 原样保留 (避免 UNIQUE(path, chunk_index) 冲突)。授权删除时保持原行为。
        offset = 0
        if allow_delete:
            conn.execute("DELETE FROM chunks WHERE path = ?", (source_name,))
        elif source_name in max_index:
            offset = max_index[source_name] + 1
            appended_versions += 1
        title = title_for(source, text)
        stat = source.stat()
        for chunk_index, content in chunks(text):
            chunk_index += offset
            domain, kind, status, scope, confidence = classify(source, title, content)
            metadata = {
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "suffix": source.suffix.lower(), "domain": domain, "kind": kind,
                "status": status, "scope": scope, "confidence": confidence,
            }
            conn.execute(
                """INSERT INTO chunks(path, chunk_index, title, content, source_hash, vector, metadata, domain, kind, status, scope, confidence)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_name, chunk_index, title, content, source_hash, encode(content), json.dumps(metadata, ensure_ascii=False), domain, kind, status, scope, confidence),
            )
            inserted += 1
    if allow_delete:
        for stale in set(existing) - current_names:
            conn.execute("DELETE FROM chunks WHERE path = ?", (stale,))
            removed += 1
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('last_indexed_at', ?)", (now,))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('source_count', ?)", (str(len(current)),))
    conn.commit()
    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
    sync_knowledge_records(conn)
    sync_keywords(conn)
    conn.commit()
    # ★ 2026-09-24 v2 后处理：类型归一、旧版本/派生文件打标记、噪音关键词、trigram FTS、bge 语义向量
    try:
        import sire_knowledge_index as ski
        ski.post_index(conn)
    except Exception as exc:  # noqa: BLE001
        conn.rollback()  # 丢弃写了一半的派生数据，基础索引已在上方提交
        print(f"[向量库] v2 后处理失败（不影响基础索引）: {exc}", file=sys.stderr)
    if removed and allow_delete:
        conn.execute("VACUUM")
    total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    return {"sources": len(current), "chunks": total, "inserted": inserted, "unchanged": unchanged,
            "removed": removed, "appended_versions": appended_versions}


def sync_knowledge_records(conn: sqlite3.Connection) -> int:
    """把 SIRE 知识记录同步到同一 SQLite 数据库，保留与向量 chunk 的 source_path 关联。"""
    kb = default_kb_dir()
    records: list[dict[str, object]] = []
    seen_ids: dict[str, int] = {}
    patterns = {"F": "global_dev_features.md", "P": "global_problem_solutions.md",
                "E": "global_dev_efficiency.md", "H": "global_dev_habits.md"}
    header = re.compile(r"^###\s+([FPEH])-([0-9]+)\s*[:：]\s*(.+?)\s*$")
    for letter, filename in patterns.items():
        source = kb / filename
        if not source.is_file():
            continue
        current = None
        for lineno, line in enumerate(read_text(source).splitlines(), 1):
            match = header.match(line)
            if match:
                if current:
                    records.append(current)
                base_id = f"{match.group(1)}-{match.group(2)}"
                seen_ids[base_id] = seen_ids.get(base_id, 0) + 1
                record_id = base_id if seen_ids[base_id] == 1 else f"{base_id}#{seen_ids[base_id]}"
                current = {"record_id": record_id, "record_type": letter,
                           "title": match.group(3), "source_path": str(source), "source_line": lineno,
                           "keywords": "", "body": []}
            elif current is not None:
                current["body"].append(line)
        if current:
            records.append(current)
    # 数据库是正式知识源。源 Markdown 被迁移或暂时不可用时，不能清空已入库知识。
    if not records:
        total = conn.execute("SELECT COUNT(*) FROM knowledge_records").fetchone()[0]
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('knowledge_record_count', ?)", (str(total),))
        return total
    if os.environ.get("SIRE_DB_ALLOW_DELETE") == "1":
        require_delete_password()
        conn.execute("DELETE FROM knowledge_records")
    now = datetime.now(timezone.utc).isoformat()
    for record in records:
        body = "\n".join(record.pop("body"))
        keywords = ""
        for line in body.splitlines():
            if "关键词" in line:
                keywords = line.split(":", 1)[-1].strip()
                break
        domain, kind, status, scope, confidence = classify(Path(str(record["source_path"])), str(record["title"]), body)
        conn.execute("""INSERT OR REPLACE INTO knowledge_records
            (record_id, record_type, title, source_path, source_line, keywords, body, updated_at, domain, kind, status, scope, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record["record_id"], record["record_type"], record["title"], record["source_path"],
             record["source_line"], keywords, body, now, domain, kind, status, scope, confidence))
    total = conn.execute("SELECT COUNT(*) FROM knowledge_records").fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('knowledge_record_count', ?)", (str(total),))
    return len(records)


def task_roots() -> list[Path]:
    return shared_task_roots()


def run_directories(root: Path) -> list[Path]:
    """兼容工作区 .sire/runs 和清理后的归档目录结构。"""
    found: set[Path] = set()
    for run_dir in root.rglob(".sire/runs"):
        if run_dir.is_dir():
            found.update(item for item in run_dir.iterdir() if item.is_dir())
    for run_json in root.rglob("run.json"):
        if run_json.is_file():
            found.add(run_json.parent)
    return sorted(found, key=lambda item: str(item).lower())


def sync_task_records(conn: sqlite3.Connection) -> int:
    """将历史 .sire/runs 台账文件导入数据库；幂等，不删除原始台账。"""
    allowed = {".json", ".md", ".log", ".txt", ".yaml", ".yml"}
    if os.environ.get("SIRE_DB_ALLOW_DELETE") == "1":
        require_delete_password()
        conn.execute("DELETE FROM task_records")
    count = 0
    now = datetime.now(timezone.utc).isoformat()
    for root in task_roots():
        if not root.is_dir():
            continue
        for run in run_directories(root):
                run_id = run.name
                project_path = str(run.parent.parent.resolve())
                for record in run.rglob("*"):
                    if not record.is_file() or record.suffix.lower() not in allowed:
                        continue
                    try:
                        content = read_text(record)
                    except OSError:
                        continue
                    key = str(record.resolve())
                    domain, kind, status, scope, confidence = classify(record, record.name, content)
                    conn.execute("""INSERT OR REPLACE INTO task_records
                        (record_key, run_id, project_path, record_path, record_type, content, updated_at, domain, kind, status, scope, confidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (key, run_id, project_path, key, record.suffix.lower().lstrip("."), content, now, domain, kind, status, scope, confidence))
                    count += 1
    total = conn.execute("SELECT COUNT(*) FROM task_records").fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('task_record_count', ?)", (str(total),))
    return count


def sync_keywords(conn: sqlite3.Connection) -> int:
    """从知识标题/显式关键词和任务内容提炼可复用关键词。"""
    token_re = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,}|[\u4e00-\u9fff]{2,8}")
    stopwords = {"status", "updated", "artifacts", "reason", "risk", "note", "stage", "true", "false",
                 "null", "none", "done", "pass", "fail", "runs", "record", "records", "content", "path",
                 "title", "file", "line", "date", "project", "state", "unit", "units", "review", "test",
                 "implementation", "json", "md", "python", "powershell", "the", "and", "for", "from"}
    sources: dict[str, set[str]] = {}
    for row in conn.execute("SELECT record_id, title, keywords FROM knowledge_records"):
        explicit = re.split(r"[,，、;；|\s]+", row["keywords"] or "")
        text = f"{row['title']} {' '.join(explicit)}"
        for token in set(explicit + token_re.findall(text)):
            token = token.strip("[](){}'\"").lower()
            if len(token) >= 2 and token not in stopwords and "�" not in token and not re.fullmatch(r"[a-f0-9]{8,}", token):
                sources.setdefault(token, set()).add(row["record_id"])
    for row in conn.execute("SELECT record_key, content FROM task_records"):
        for token in set(token_re.findall(row["content"] or "")):
            token = token.lower()
            if len(token) >= 2 and token not in stopwords and "�" not in token and not re.fullmatch(r"[a-f0-9]{8,}", token):
                sources.setdefault(token, set()).add(row["record_key"])
    if os.environ.get("SIRE_DB_ALLOW_DELETE") == "1":
        require_delete_password()
        conn.execute("DELETE FROM keywords")
    now = datetime.now(timezone.utc).isoformat()
    kept = 0
    for keyword, refs in sources.items():
        if len(refs) < 2:
            continue
        kind = "knowledge" if any(ref.startswith(("F-", "P-", "E-", "H-")) for ref in refs) else "task"
        # ★ 2026-09-22 只增不减: 未授权删除时已有关键词不删, upsert 且计数只升不降
        conn.execute("""INSERT INTO keywords(keyword, keyword_type, hit_count, source_count, updated_at) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(keyword) DO UPDATE SET
                          hit_count = MAX(keywords.hit_count, excluded.hit_count),
                          source_count = MAX(keywords.source_count, excluded.source_count),
                          keyword_type = CASE WHEN keywords.keyword_type = 'knowledge' THEN 'knowledge' ELSE excluded.keyword_type END,
                          updated_at = excluded.updated_at""",
                     (keyword, kind, len(refs), len(refs), now))
        kept += 1
    total = conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('keyword_count', ?)", (str(total),))
    return kept


def search_database(path: Path, query: str, limit: int, threshold: float, domain: str | None = None) -> list[dict[str, object]]:
    # ★ 2026-09-24 v2 混合检索（bge 语义 + trigram + 去重），异常时回退下方旧算法
    conn = None
    try:
        import sire_knowledge_index as ski
        conn = connect_readonly(path)
        try:
            return ski.search(conn, query, limit, threshold, domain, hash_encode=encode, hash_decode=decode)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        print(f"[向量库] v2 检索失败，回退旧算法: {exc}", file=sys.stderr)
    conn = connect_readonly(path)
    try:
        query_vector = decode(encode(query))
        query_terms = {item.lower() for item in features(query)}
        keyword_hits = {row["keyword"] for row in conn.execute("SELECT keyword FROM keywords") if row["keyword"] in query_terms}
        rows = conn.execute("SELECT id, path, chunk_index, title, content, metadata, vector, domain FROM chunks" + (" WHERE domain = ?" if domain else ""), ((domain,) if domain else ())).fetchall()
        fts_ids = set()
        try:
            terms = re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", query)
            if terms:
                fts_ids = {row["rowid"] for row in conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT 200", (" OR ".join(terms),))}
        except sqlite3.OperationalError:
            pass
        ranked = []
        for row in rows:
            score = cosine(query_vector, decode(row["vector"]))
            if row["id"] in fts_ids:
                score += 0.12
            if keyword_hits:
                content_terms = set(features(row["title"] + " " + row["content"]))
                score += 0.03 * len(keyword_hits & content_terms)
            if score >= threshold:
                ranked.append({
                    "id": row["id"],
                    "path": row["path"],
                    "chunk": row["chunk_index"],
                    "title": row["title"],
                    "score": round(score, 6),
                    "content": row["content"],
                    "metadata": json.loads(row["metadata"]), "domain": row["domain"],
                })
        # 源知识文件迁移后，结构化知识记录仍是正式检索来源。
        knowledge_rows = conn.execute(
            "SELECT record_id, title, body, source_path, domain, kind, status, scope, confidence FROM knowledge_records" +
            (" WHERE domain = ?" if domain else ""), ((domain,) if domain else ())).fetchall()
        for row in knowledge_rows:
            body = f"{row['title']}\n{row['body']}"
            score = cosine(query_vector, decode(encode(body)))
            if any(term in body.lower() for term in query_terms):
                score += 0.12
            score += float(row["confidence"] or 0) * 0.03
            if score >= threshold:
                ranked.append({
                    "id": f"knowledge:{row['record_id']}", "path": row["source_path"], "chunk": 0,
                    "title": row["title"], "score": round(score, 6), "content": row["body"],
                    "metadata": {"domain": row["domain"], "kind": row["kind"], "status": row["status"], "scope": row["scope"], "confidence": row["confidence"]},
                    "domain": row["domain"],
                })
        ranked.sort(key=lambda item: float(item["score"]), reverse=True)
        return ranked[: max(1, limit)]
    finally:
        conn.close()


def show_document(path: Path, document_id: int) -> dict[str, object] | None:
    conn = connect_readonly(path)
    try:
        row = conn.execute("SELECT id, path, chunk_index, title, content, metadata FROM chunks WHERE id = ?", (document_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"id": row["id"], "path": row["path"], "chunk": row["chunk_index"], "title": row["title"], "content": row["content"], "metadata": json.loads(row["metadata"])}


def stats(path: Path) -> dict[str, object]:
    conn = connect_readonly(path)
    try:
        result = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM meta")}
        result["db_path"] = str(path)
        result["chunks"] = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        result["sources"] = conn.execute("SELECT COUNT(DISTINCT path) FROM chunks").fetchone()[0]
        result["knowledge_records"] = conn.execute("SELECT COUNT(*) FROM knowledge_records").fetchone()[0]
        result["task_records"] = conn.execute("SELECT COUNT(*) FROM task_records").fetchone()[0]
        result["keywords"] = conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
        return result
    finally:
        conn.close()


def infer_run_dir() -> Path | None:
    configured = os.environ.get("SIRE_RUN_DIR")
    if configured:
        return Path(configured)
    current = Path.cwd() / ".sire" / "current"
    if current.is_file():
        run_id = current.read_text(encoding="utf-8", errors="replace").strip()
        if run_id:
            candidate = current.parent / "runs" / run_id
            if candidate.is_dir():
                return candidate
    return None


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="SIRE 本地向量知识库")
    command.add_argument("--db", type=Path, default=db_path(), help="SQLite 向量库路径")
    sub = command.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="增量索引 SIRE 工作流、全局知识和规则文件，并同步知识记录表")
    sub.add_parser("migrate", help="将全局知识和历史 SIRE 任务台账导入本地数据库")
    search = sub.add_parser("search", help="快速向量检索")
    search.add_argument("query", nargs="?", help="查询文本")
    search.add_argument("--query", dest="query_flag", help="查询文本")
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--threshold", type=float, default=0.12)
    search.add_argument("--domain", help="按领域过滤，例如 frontend/backend/database/sire")
    search.add_argument("--json", action="store_true")
    search.add_argument("--run", type=Path, help="当前 SIRE run 目录，写入向量检索回执")
    show = sub.add_parser("show", help="读取关联 chunk")
    show.add_argument("id", type=int)
    show.add_argument("--json", action="store_true")
    sub.add_parser("stats", help="显示向量库状态")
    return command


def main(argv: list[str] | None = None) -> int:
    configure_output()
    args = parser().parse_args(argv)
    if args.command == "index":
        with database_mutation_lock(args.db):
            print(json.dumps(index_database(args.db), ensure_ascii=False))
        return 0
    if args.command == "migrate":
        with database_mutation_lock(args.db):
            backup_before_mutation(args.db)
            conn = connect(args.db)
            knowledge = sync_knowledge_records(conn)
            tasks = sync_task_records(conn)
            keywords = sync_keywords(conn)
            conn.commit()
            conn.close()
            print(json.dumps({"knowledge_records": knowledge, "task_records": tasks, "keywords": keywords,
                              "db": str(args.db)}, ensure_ascii=False))
        return 0
    if args.command == "search":
        query = args.query_flag or args.query
        if not query:
            print("search 需要查询文本", file=sys.stderr)
            return 2
        result = {"query": query, "db": str(args.db), "hits": search_database(args.db, query, args.limit, args.threshold, args.domain)}
        run_dir = args.run or infer_run_dir()
        if run_dir:
            run_dir.mkdir(parents=True, exist_ok=True)
            receipt = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "run_id": run_dir.name, "query": query, "db": str(args.db),
                       "hits": len(result["hits"])}
            with (run_dir / "vector-search.log").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(receipt, ensure_ascii=False) + "\n")
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            for hit in result["hits"]:
                print(f"[{hit['score']}] {hit['title']} :: {hit['path']}#chunk{hit['chunk']}")
                print(hit["content"][:600].replace("\n", " "))
        return 0
    if args.command == "show":
        result = show_document(args.db, args.id)
        if result is None:
            print(json.dumps({"error": "not_found", "id": args.id}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False) if args.json else result["content"])
        return 0
    print(json.dumps(stats(args.db), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
