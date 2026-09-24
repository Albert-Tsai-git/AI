# -*- coding: utf-8 -*-
"""[知识索引] SIRE 知识库 v2 检索层（2026-09-24）。

目标：能快速检索到知识，且检索到的知识可直接用于开发相同功能。
- 语义向量：本地 BAAI/bge-small-zh-v1.5（fastembed/ONNX，512 维），不可用时回退旧哈希向量
- 全文检索：FTS5 trigram 分词（中文、带连字符术语可用），查询词加引号防语法错误
- 混合打分：语义 + 词项覆盖 + BM25 + 知识记录加权；同一来源去重；结果附「复用要点」
- 只增不减：旧版本片段、派生文件、噪音关键词只打标记（is_latest / status），不删除
"""
import hashlib
import json
import os
import re
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from sire_paths import MODEL_DIR as SHARED_MODEL_DIR

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
MODEL_DIR = str(SHARED_MODEL_DIR)
EMB_DIM = 512
# 派生/配置文件不参与检索（global_index.json 本身就是索引，切片后只会反复抢排名）
EXCLUDE_NAMES = {"global_index.json", "settings.json", "settings.local.json",
                 "global_knowledge_records.md", "knowledge_template.md"}  # 后两者：数据库导出副本/模板
EXCLUDE_RE = re.compile(r"\.bak($|[-_.])|\.tmp$", re.I)
# SIRE 台账噪音：角色/单元编号、用户名、流程套话
NOISE_RE = re.compile(r"^(u-?\d+|r\d+[a-z]?|g\d|w\d+|\d+(\.\d+)*|[a-f0-9]{6,}|.{31,})$", re.I)
NOISE_WORDS = {"users", "administrator", "appdata", "roaming", "通过", "结论", "日志", "evidence", "diff",
               "controller", "check", "command", "verify", "full", "id", "run_id", "handler", "components",
               "channel", "交叉核验", "sire_global", "local", "temp", "true", "false", "none", "null"}
# 同义词：检索时互相扩展
SYNONYMS = [
    ("飞书", "feishu", "lark", "飞书自动化"),
    ("向量库", "向量数据库", "sire_vectors", "知识库", "数据库"),
    ("寄存器", "register", "reg_read", "regread"),
    ("固件升级", "iap", "ota", "烧录"),
    ("序列号", "sn", "statorsn"),
    ("多语言", "国际化", "i18n", "翻译"),
    ("卡住", "挂起", "hang", "卡死", "无响应"),
    ("窗口", "browserwindow", "子窗口"),
    ("发布", "release", "打包", "ci"),
    ("霍尔", "hall"),
    ("舵机", "servo", "kingkong", "driver"),
    ("钩子", "hook", "hooks"),
]
# 记录类型归一：F 功能 / P 问题 / E 效率 / H 习惯 / K 参考知识
CANON_TYPE = {
    "feature": "F", "implementation": "F",
    "solution": "P", "bugfix": "P",
    "analysis": "K", "audit": "K", "inventory": "K", "provenance": "K", "risk": "K", "validation": "K",
    "verification": "K", "fact": "K", "reference": "K", "protocol": "K", "rule": "K", "kb-check": "K",
    "reusable_knowledge": "K",
}
REUSE_RE = re.compile(r"(流程|踩坑|方案|关键文件|涉及文件|涉及模块|文件|接口|实现要点|架构|步骤|做法|解决|修复|验证|测试|产物|位置|根因|原因)")
ID_RE = re.compile(r"\b([FPEHK]-\d+(?:#\d+)?)\b")

_model = None
_model_failed = False


def log(msg):
    """[知识索引] 关键节点日志输出到 stderr，不污染 --json 输出。"""
    import sys
    print("[知识索引] " + msg, file=sys.stderr)


# ---------------------------------------------------------------- 结构

def ensure_schema(conn):
    """只新增列/表，不删除任何已有数据。"""
    def add_col(table, col, ddl):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
        if col not in cols:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, ddl))
    add_col("chunks", "is_latest", "INTEGER NOT NULL DEFAULT 1")
    add_col("knowledge_records", "orig_type", "TEXT NOT NULL DEFAULT ''")
    add_col("keywords", "weight", "REAL NOT NULL DEFAULT 1.0")
    add_col("keywords", "status", "TEXT NOT NULL DEFAULT 'active'")
    conn.execute("""CREATE TABLE IF NOT EXISTS emb (
        kind TEXT NOT NULL, ref TEXT NOT NULL, model TEXT NOT NULL,
        text_hash TEXT NOT NULL, vector BLOB NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY(kind, ref, model))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS synonyms (
        term TEXT NOT NULL, canonical TEXT NOT NULL, PRIMARY KEY(term, canonical))""")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS kfts USING fts5(record_id UNINDEXED, title, keywords, body, tokenize='trigram')")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS cfts USING fts5(chunk_id UNINDEXED, title, content, tokenize='trigram')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_latest ON chunks(is_latest)")


# ---------------------------------------------------------------- 数据治理（只打标记）

def excluded(path):
    name = Path(path).name.lower()
    return name in EXCLUDE_NAMES or bool(EXCLUDE_RE.search(name))


def _file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def mark_latest(conn):
    """每个来源只让最新版本参与检索；旧版本与派生文件 is_latest=0（保留不删）。"""
    rows = conn.execute("SELECT path, source_hash, MAX(id) FROM chunks GROUP BY path, source_hash").fetchall()
    by_path = {}
    for path, sh, mx in rows:
        by_path.setdefault(path, []).append((mx, sh))
    hidden = 0
    for path, versions in by_path.items():
        if excluded(path):
            latest = None
        else:
            latest = max(versions)[1]
            if len(versions) > 1 and os.path.isfile(path):
                try:
                    cur = _file_hash(path)
                    if any(sh == cur for _, sh in versions):
                        latest = cur
                except OSError:
                    pass
        conn.execute("UPDATE chunks SET is_latest = CASE WHEN source_hash = ? THEN 1 ELSE 0 END WHERE path = ?",
                     (latest or "", path))
        hidden += sum(1 for _, sh in versions if sh != latest)
    return hidden


def normalize_types(conn):
    """记录类型归一到 F/P/E/H/K，原值保留在 orig_type。"""
    n = 0
    for rid, rtype, orig in conn.execute("SELECT record_id, record_type, orig_type FROM knowledge_records").fetchall():
        if not orig:
            conn.execute("UPDATE knowledge_records SET orig_type = ? WHERE record_id = ?", (rtype, rid))
        canon = rtype if rtype in ("F", "P", "E", "H", "K") else CANON_TYPE.get(rtype.lower(), "K")
        if canon != rtype:
            conn.execute("UPDATE knowledge_records SET record_type = ? WHERE record_id = ?", (canon, rid))
            n += 1
    return n


def mark_noise_keywords(conn):
    n = 0
    for (kw,) in conn.execute("SELECT keyword FROM keywords").fetchall():
        noisy = kw.lower() in NOISE_WORDS or bool(NOISE_RE.match(kw))
        conn.execute("UPDATE keywords SET status = ?, weight = ? WHERE keyword = ?",
                     ("noise" if noisy else "active", 0.0 if noisy else 1.0, kw))
        n += noisy
    # 台账自动抽取的关键词降权（知识记录显式关键词权重 1.0）
    conn.execute("UPDATE keywords SET weight = 0.3 WHERE status = 'active' AND keyword_type = 'task'")
    return n


def fill_missing_keywords(conn):
    """无关键词的知识：从标题术语 + 正文提到的文件名自动生成（只补空，不覆盖已有）。"""
    n = 0
    for rid, title, body in conn.execute("SELECT record_id, title, body FROM knowledge_records WHERE TRIM(keywords) = ''").fetchall():
        words = re.findall(r"[A-Za-z][A-Za-z0-9_.\-]{1,}|[一-鿿]{2,8}", title)
        files = [f.replace("\\", "/").split("/")[-1] for f in FILE_RE.findall(body or "")]
        kws = []
        for w in words + files:
            if w.lower() not in NOISE_WORDS and w not in kws:
                kws.append(w)
        if kws:
            conn.execute("UPDATE knowledge_records SET keywords = ? WHERE record_id = ?", (", ".join(kws[:12]), rid))
            n += 1
    return n


def seed_synonyms(conn):
    for group in SYNONYMS:
        canon = group[0]
        for term in group:
            conn.execute("INSERT OR IGNORE INTO synonyms(term, canonical) VALUES(?, ?)", (term.lower(), canon))


def rebuild_fts(conn):
    """FTS 是派生索引，整体重建（不涉及知识本身）。"""
    conn.execute("DELETE FROM kfts")
    conn.execute("INSERT INTO kfts(record_id, title, keywords, body) SELECT record_id, title, keywords, body FROM knowledge_records")
    conn.execute("DELETE FROM cfts")
    conn.execute("INSERT INTO cfts(chunk_id, title, content) SELECT id, title, content FROM chunks WHERE is_latest = 1")


# ---------------------------------------------------------------- 语义向量

def embedder():
    """懒加载本地嵌入模型；失败时返回 None，调用方回退哈希向量。"""
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    try:
        if Path(MODEL_DIR).is_dir() and any(Path(MODEL_DIR).rglob("*.onnx")):
            os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 模型已缓存则完全离线
        else:
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from fastembed import TextEmbedding
        _model = TextEmbedding(MODEL_NAME, cache_dir=MODEL_DIR)
    except Exception as exc:  # noqa: BLE001
        _model_failed = True
        log("嵌入模型不可用，回退哈希向量: %s" % exc)
    return _model


def _pack(vec):
    return struct.pack("<%df" % len(vec), *[float(x) for x in vec])


def _unpack(blob):
    return struct.unpack("<%df" % (len(blob) // 4), blob)


def knowledge_text(title, keywords, body):
    return "%s\n关键词: %s\n%s" % (title, keywords or "", (body or "")[:1500])


def sync_embeddings(conn):
    """增量计算语义向量：只算新增/内容变化的知识记录与最新片段。"""
    model = embedder()
    if model is None:
        return 0
    todo = []
    have = {(k, r): h for k, r, h in conn.execute("SELECT kind, ref, text_hash FROM emb WHERE model = ?", (MODEL_NAME,))}
    for rid, title, kw, body in conn.execute("SELECT record_id, title, keywords, body FROM knowledge_records"):
        text = knowledge_text(title, kw, body)
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()
        if have.get(("knowledge", rid)) != h:
            todo.append(("knowledge", rid, h, text))
    for cid, title, content in conn.execute("SELECT id, title, content FROM chunks WHERE is_latest = 1"):
        text = "%s\n%s" % (title, content)
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()
        if have.get(("chunk", str(cid))) != h:
            todo.append(("chunk", str(cid), h, text))
    if not todo:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    vecs = list(model.embed([t[3] for t in todo], batch_size=32))
    for (kind, ref, h, _), vec in zip(todo, vecs):
        conn.execute("INSERT OR REPLACE INTO emb(kind, ref, model, text_hash, vector, updated_at) VALUES(?,?,?,?,?,?)",
                     (kind, ref, MODEL_NAME, h, _pack(vec), now))
    return len(todo)


# ---------------------------------------------------------------- 索引入口

def post_index(conn):
    """sire_vector_db.index_database 末尾调用：治理 + 全文索引 + 语义向量。"""
    ensure_schema(conn)
    seed_synonyms(conn)
    stats = {
        "types_normalized": normalize_types(conn),
        "hidden_old_versions": mark_latest(conn),
        "noise_keywords": mark_noise_keywords(conn),
        "keywords_filled": fill_missing_keywords(conn),
    }
    rebuild_fts(conn)
    conn.commit()
    stats["embedded"] = sync_embeddings(conn)
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('retrieval', 'hybrid-bge-trigram-v2')")
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('embed_model', ?)", (MODEL_NAME,))
    conn.commit()
    log("索引后处理完成 %s" % json.dumps(stats, ensure_ascii=False))
    return stats


# ---------------------------------------------------------------- 检索

def query_terms(conn, query):
    """查询词：英文/数字词 + 中文连续片段（及其 2 字切片）+ 同义词扩展。"""
    q = query.lower()
    words = re.findall(r"[a-z0-9_][a-z0-9_.\-/]*[a-z0-9_]|[a-z0-9]", q)
    cjk = re.findall(r"[\u4e00-\u9fff]+", q)
    terms = set(w for w in words if len(w) >= 2)
    for seg in cjk:
        if len(seg) <= 4:
            terms.add(seg)
        terms.update(seg[i:i + 2] for i in range(len(seg) - 1))
    expanded = set(terms)
    try:
        for t in terms:
            for (canon,) in conn.execute("SELECT canonical FROM synonyms WHERE term = ?", (t,)):
                for (alt,) in conn.execute("SELECT term FROM synonyms WHERE canonical = ?", (canon,)):
                    expanded.add(alt)
    except sqlite3.OperationalError:
        pass
    return terms, expanded


def _bm25(conn, table, idcol, terms):
    """trigram FTS 只能匹配 ≥3 字符的词；返回 {id: 归一化分数}。"""
    long_terms = [t for t in terms if len(t) >= 3]
    if not long_terms:
        return {}
    expr = " OR ".join('"%s"' % t.replace('"', '""') for t in long_terms)
    try:
        rows = conn.execute("SELECT %s, bm25(%s) FROM %s WHERE %s MATCH ? ORDER BY bm25(%s) LIMIT 200"
                            % (idcol, table, table, table, table), (expr,)).fetchall()
    except sqlite3.OperationalError:
        return {}
    if not rows:
        return {}
    n = len(rows)
    return {str(r[0]): 1.0 - i / n for i, r in enumerate(rows)}


def _coverage(terms, title, keywords, body):
    if not terms:
        return 0.0
    head = (title + " " + (keywords or "")).lower()
    body = (body or "").lower()
    got = 0.0
    for t in terms:
        if t in head:
            got += 1.0
        elif t in body:
            got += 0.5
    return got / len(terms)


FILE_RE = re.compile(r"[\w./\\-]+\.(?:py|js|ts|vue|jsx|tsx|c|h|cpp|html|json|md|ps1|cmd|sct|yaml|yml)\b")
SECTION_RE = re.compile(r"^\*\*([^*]{1,60})\*\*\s*(?:（[^）]*）|\([^)]*\))?\s*[:：]?\s*(.*)$")
SENT_HINT = re.compile(r"(方案是|做法|修复|根因|原因|证据|重点检查|首先|必须|不能|禁止|步骤|验证|改为|解决)")


def reuse_points(body, limit=5):
    """抽取可直接指导开发的要点：关键文件 + 根因/修复/方案/验证等分段首行；整段式正文按句切分挑关键句。"""
    body = body or ""
    out = []
    files = []
    for f in FILE_RE.findall(body):
        name = f.replace("\\", "/").split("/")[-1]
        if name not in files and not name.startswith("."):
            files.append(name)
    if files:
        out.append("关键文件: " + ", ".join(files[:8]))
    lines = [ln.strip() for ln in body.splitlines()]
    for i, ln in enumerate(lines):
        m = SECTION_RE.match(ln)
        if not m or not REUSE_RE.search(m.group(1)):
            continue
        text = m.group(2).strip()
        if not text:  # 分段标题独占一行，取下一条非空行
            text = next((x.lstrip("-*0123456789. ").strip() for x in lines[i + 1:i + 4] if x), "")
        if text:
            out.append("%s: %s" % (m.group(1).strip(), text[:200]))
        if len(out) >= limit:
            return out
    if len(out) <= 1:  # 整段式正文
        for sent in re.split(r"(?<=[。；;])", body.replace("\n", " ")):
            s = sent.strip()
            if len(s) >= 12 and SENT_HINT.search(s):
                out.append(s[:200])
            if len(out) >= limit:
                break
    return out


def search(conn, query, limit=5, threshold=0.0, domain=None, hash_encode=None, hash_decode=None):
    """混合检索。返回与旧接口相同字段，并附加 kind/reuse。"""
    import numpy as np
    # Retrieval is strictly read-only. Schema creation/migration belongs to index/migrate;
    # running it here would rewrite a checked-in SQLite snapshot during an ordinary search.
    required_columns = {
        "knowledge_records": {"record_id", "record_type", "title", "keywords", "body", "source_path",
                              "domain", "kind", "status", "scope", "confidence"},
        "chunks": {"id", "path", "chunk_index", "title", "content", "metadata", "vector", "domain", "is_latest"},
        "emb": {"kind", "ref", "model", "vector"},
    }
    for table, required in required_columns.items():
        actual = {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)}
        missing = required - actual
        if missing:
            raise sqlite3.OperationalError(
                "database schema is incomplete; run sire_vector_db.py index (missing %s.%s)"
                % (table, ",".join(sorted(missing)))
            )
    terms, expanded = query_terms(conn, query)
    model = embedder()
    qvec = None
    if model is not None:
        qvec = np.asarray(list(model.query_embed([query]))[0], dtype=np.float32)
    emb = {}
    if qvec is not None:
        for kind, ref, blob in conn.execute("SELECT kind, ref, vector FROM emb WHERE model = ?", (MODEL_NAME,)):
            emb[(kind, ref)] = blob
    hq = hash_decode(hash_encode(query)) if hash_encode else None

    def semantic(kind, ref, text, hvec_blob=None):
        blob = emb.get((kind, ref))
        if blob is not None and qvec is not None:
            return float(np.dot(qvec, np.frombuffer(blob, dtype=np.float32)))
        if hq is not None:
            hv = hash_decode(hvec_blob) if hvec_blob else hash_decode(hash_encode(text))
            return 0.8 * sum(a * b for a, b in zip(hq, hv))
        return 0.0

    kb25 = _bm25(conn, "kfts", "record_id", expanded)
    cb25 = _bm25(conn, "cfts", "chunk_id", expanded)
    kw_set = {k.lower() for k in expanded}
    results = []
    where = " WHERE domain = ?" if domain else ""
    args = (domain,) if domain else ()
    # status='removed'：按「真实经验+可直接使用」标准判为无效的记录，软删除，不参与检索
    where = (where + " AND" if where else " WHERE") + " status != 'removed'"
    for row in conn.execute("SELECT record_id, record_type, title, keywords, body, source_path, domain, kind, status, scope, confidence FROM knowledge_records" + where, args):
        rid, rtype, title, kws, body, src = row[0], row[1], row[2], row[3], row[4], row[5]
        sem = semantic("knowledge", rid, knowledge_text(title, kws, body))
        cov = _coverage(terms, title, kws, body)
        rec_kws = {k.strip().lower() for k in re.split(r"[,，、;；|\[\]]+", kws or "") if k.strip()}
        exact = 0.1 if rec_kws & kw_set else 0.0
        score = 0.55 * sem + 0.30 * cov + 0.15 * kb25.get(rid, 0.0) + exact + 0.06
        results.append({
            "id": "knowledge:%s" % rid, "path": src, "chunk": 0, "title": title, "score": round(score, 6),
            "content": body, "domain": row[6], "kind": "knowledge", "record_id": rid, "record_type": rtype,
            "reuse": reuse_points(body),
            "metadata": {"domain": row[6], "kind": row[7], "status": row[8], "scope": row[9], "confidence": row[10]},
        })
    for row in conn.execute("SELECT id, path, chunk_index, title, content, metadata, vector, domain FROM chunks WHERE is_latest = 1" + (" AND domain = ?" if domain else ""), args):
        cid, path = str(row[0]), row[1]
        sem = semantic("chunk", cid, row[3] + "\n" + row[4], row[6])
        cov = _coverage(terms, row[3], "", row[4])
        score = 0.55 * sem + 0.30 * cov + 0.15 * cb25.get(cid, 0.0)
        if ".sire" in path or "archive-2026" in path:
            score *= 0.9  # 过程台账略降权，提炼后的知识优先
        results.append({
            "id": row[0], "path": path, "chunk": row[2], "title": row[3], "score": round(score, 6),
            "content": row[4], "domain": row[7], "kind": "chunk", "metadata": json.loads(row[5] or "{}"),
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    # 去重：同一来源只留最高分片段；片段内容若就是已入选知识记录的原文则跳过
    picked, seen_paths, seen_ids = [], set(), set()
    for r in results:
        if r["score"] < threshold:
            continue
        if r["kind"] == "knowledge":
            seen_ids.add(r["record_id"])
        else:
            if r["path"] in seen_paths:
                continue
            ids_in = set(ID_RE.findall(r["content"][:600]))
            if ids_in and ids_in <= seen_ids:
                continue
            seen_paths.add(r["path"])
        picked.append(r)
        if len(picked) >= max(1, limit):
            break
    return picked
