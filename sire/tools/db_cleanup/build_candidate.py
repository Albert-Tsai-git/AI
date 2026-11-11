# -*- coding: utf-8 -*-
"""[候选库] 由结构化知识卡片构建干净的候选 SIRE 库，线上库全程只读。

用法:
  python build_candidate.py --selftest
  python build_candidate.py --cards-dir <dir> --live <线上库> --out D:\\sire\\db-candidate\\sire_vectors.sqlite3
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SCRIPTS = Path(r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts")
sys.path.insert(0, str(SCRIPTS))
CAND_ROOT = Path(r"D:\sire\db-candidate")
KB = Path(r"D:\sire\AI\AI\sire\knowledge\global")
MD_MAP = {"F": "global_dev_features.md", "P": "global_problem_solutions.md",
          "E": "global_dev_efficiency.md", "H": "global_dev_habits.md"}
FIELDS = ("scene", "steps", "verify", "pitfalls", "files", "status")
MISSING = "原记录未记载"

# ---------------- 切片来源规则（与 U4 固化到 sire_vector_db 的规则一致）----------------
EXCLUDE_PARTS = ("sire_ledger", "evidence", "mermaid", "\\.sire\\", "/.sire/", "\\runs\\", "/runs/",
                 "node_modules", "__pycache__", "integrity", "secrets", "exports")
EXCLUDE_NAMES = {"global_index.json", "global_knowledge_records.md", "knowledge_template.md",
                 "settings.json", "settings.local.json", "sire-migration-legacy-v1.md"}
ALLOW_SUFFIX = {".md", ".markdown"}


def chunk_source_allowed(path: str) -> bool:
    """只允许工作流参考文档与知识目录里的说明文档切片；台账/evidence/mermaid/项目 runs 一律排除。"""
    low = path.lower()
    if any(p in low for p in EXCLUDE_PARTS):
        return False
    name = os.path.basename(low)
    if name in EXCLUDE_NAMES or ".bak" in name:
        return False
    if Path(low).suffix not in ALLOW_SUFFIX:
        return False
    # 具体记录文件(global_dev_*.md / global_problem_solutions.md)的内容已是 knowledge_records，不重复切片
    if name in {v.lower() for v in MD_MAP.values()}:
        return False
    return True


def doc_sources() -> list[Path]:
    out = []
    skill = SCRIPTS.parent
    for p in [skill / "SKILL.md", *sorted((skill / "references").glob("*.md"))]:
        if p.is_file() and chunk_source_allowed(str(p)):
            out.append(p)
    for p in sorted(KB.glob("*.md")):
        if chunk_source_allowed(str(p)):
            out.append(p)
    return out


def selftest() -> int:
    bad = [r"D:\sire\sire_ledger\runs\R1\log.md", r"D:\code\x\.sire\runs\R1\notes.md",
           r"D:\code\mes\runs\R1\evidence\a.md", r"D:\code\mes\runs\R1\mermaid.min.js",
           r"D:\sire\AI\AI\sire\knowledge\global\global_index.json"]
    good = [r"D:\sire\AI\AI\sire\workflow\shared\sire\SKILL.md",
            r"D:\sire\AI\AI\sire\workflow\shared\sire\references\gates.md",
            r"D:\sire\AI\AI\sire\knowledge\global\sire_ai_rules.md"]
    ok = sum(1 for p in bad if not chunk_source_allowed(p)) + sum(1 for p in good if chunk_source_allowed(p))
    # is_latest=0 在构建中通过“每个来源只切一次最新版本”保证，这里验证卡片库路径不被当作可切片文件
    ok += 1 if not chunk_source_allowed(str(KB / "global_problem_solutions.md")) else 0
    n = len(bad) + len(good) + 1
    print(f"排除规则自检 {ok}/{n} 通过")
    return 0 if ok == n else 1


# ---------------- 卡片渲染 ----------------
def render_card(c: dict) -> str:
    def f(k):
        v = c.get(k)
        if isinstance(v, list):
            v = "\n".join(str(x) for x in v)
        return (v or "").strip() or MISSING
    return "\n".join([
        f"**日期**: {f('date')}", f"**项目**: {f('project')}", f"**关键词**: {f('keywords')}", "",
        f"**需求场景 / 现象**: {f('scene')}", "",
        f"**方案 / 实施步骤**:\n{f('steps')}", "",
        f"**验证方法**: {f('verify')}", "",
        f"**踩坑 / 已知异常与失败经验**: {f('pitfalls')}", "",
        f"**关键文件与接口**: {f('files')}", "",
        f"**状态**: {f('status')}",
    ])


def load_cards(cards_dir: Path):
    items = []
    for p in sorted(cards_dir.glob("cards_*.json")):
        items.extend(json.loads(p.read_text(encoding="utf-8")))
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--cards-dir")
    ap.add_argument("--live", default=r"D:\sire\AI\AI\sire\data\sire_vectors.sqlite3")
    ap.add_argument("--out", default=str(CAND_ROOT / "sire_vectors.sqlite3"))
    ap.add_argument("--audit", default=str(CAND_ROOT / "audit.json"))
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    out = Path(a.out).resolve()
    if CAND_ROOT.resolve() not in out.parents:  # 写库前强制断言
        print("拒绝：输出必须在 D:\\sire\\db-candidate 下", file=sys.stderr)
        return 2
    import sire_vector_db as vsd
    import sire_knowledge_index as ski

    cards = load_cards(Path(a.cards_dir))
    keep = {c["id"]: c for c in cards if c["action"] == "keep"}
    audit = {"built_at": datetime.now(timezone.utc).isoformat(), "cards": len(cards),
             "keep": len(keep), "merge": [], "drop": [], "task_records": {}}
    for c in cards:
        if c["action"] == "merge":
            audit["merge"].append({"id": c["id"], "target": c["target"], "reason": c.get("reason", "")})
        elif c["action"] == "drop":
            audit["drop"].append({"id": c["id"], "reason": c.get("reason", "")})

    for suffix in ("", "-wal", "-shm"):
        Path(str(out) + suffix).unlink(missing_ok=True)
    conn = vsd.connect(out)
    ski.ensure_schema(conn)
    live = sqlite3.connect(f"file:{a.live}?mode=ro", uri=True)
    live.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat()

    # --- 知识卡片 → knowledge_records ---
    orig = {r["record_id"]: dict(r) for r in live.execute("SELECT * FROM knowledge_records")}
    for rid, c0 in keep.items():
        c = c0.get("card") or c0  # 字段在元素的 card 子对象里
        body = render_card(c)
        letter = rid[0] if rid[0] in "FPEHK" else "K"
        src = str(KB / MD_MAP[letter]) if letter in MD_MAP else orig.get(rid, {}).get("source_path", "")
        title = c.get("title") or orig.get(rid, {}).get("title", rid)
        dom, kind, status, scope, conf = vsd.classify(Path(src or "x"), title, body)
        conn.execute("""INSERT INTO knowledge_records
            (record_id, record_type, title, source_path, source_line, keywords, body, updated_at, domain, kind, status, scope, confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, letter, title, src, 0, (c.get("keywords") or "").strip(), body, now, dom, kind, status, scope, conf))
    conn.commit()

    # --- 工作流/知识说明文档 → chunks（仅最新版本，每个来源只切一次）---
    docs = [p for p in vsd.source_paths() if chunk_source_allowed(str(p))]  # 与 U4 固化后的规则同源
    for p in docs:
        text = vsd.read_text(p)
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        title = vsd.title_for(p, text)
        st = p.stat()
        for i, content in vsd.chunks(text):
            d, k, s, sc, cf = vsd.classify(p, title, content)
            meta = {"mtime_ns": st.st_mtime_ns, "size": st.st_size, "suffix": p.suffix.lower(),
                    "domain": d, "kind": k, "status": s, "scope": sc, "confidence": cf}
            conn.execute("""INSERT INTO chunks(path, chunk_index, title, content, source_hash, vector, metadata, domain, kind, status, scope, confidence)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (str(p), i, title, content, h, vsd.encode(content), json.dumps(meta, ensure_ascii=False), d, k, s, sc, cf))
    conn.commit()

    # --- task_records：去重 + 封闭规则去噪（U3b）---
    DEL_PREFIX = ("usage-", "RTEST-TRIPLE")
    DEL_TYPES = {"reply_chain_test", "execution_review_test"}
    seen = {}
    rows = [dict(r) for r in live.execute("SELECT * FROM task_records")]
    total0 = len(rows)
    runs0 = len({r["run_id"] for r in rows})
    rows.sort(key=lambda r: (0 if "sire_ledger" in r["project_path"] else 1, r["updated_at"] or ""))
    del_a, del_b, kept_rows = [], [], []
    for r in rows:
        rid = r["run_id"]
        if rid.startswith(DEL_PREFIX) or rid.endswith("-fakeproj") or rid == "current-run" or r["record_type"] in DEL_TYPES:
            del_b.append(r["record_key"]); continue
        # 去重键含 run_id：保证每个 run 至少保留一份记录(R6A 返工)，只删同 run 内的副本
        h = (rid, hashlib.sha256((r["content"] or "").encode("utf-8", "replace")).hexdigest())
        if h in seen:
            del_a.append(r["record_key"]); continue
        seen[h] = r["record_key"]
        kept_rows.append(r)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(task_records)")]
    for r in kept_rows:
        conn.execute(f"INSERT OR REPLACE INTO task_records({','.join(cols)}) VALUES({','.join('?'*len(cols))})",
                     [r.get(c) for c in cols])
    conn.commit()
    runs1 = len({r["run_id"] for r in kept_rows})
    odd_types = sorted({r["record_type"] for r in rows if not re.fullmatch(r"[\w .\-]+", r["record_type"])})
    audit["task_records"] = {"before": total0, "dedupe_deleted": len(del_a), "noise_deleted": len(del_b),
                             "after": len(kept_rows), "runs_before": runs0, "runs_after": runs1,
                             "odd_record_types_kept": odd_types, "deleted_keys_dedupe": del_a, "deleted_keys_noise": del_b}

    # --- 其余必须保留的表：RSI 记录、版本链、关系、meta ---
    for t in ("improvement_proposals", "improvement_metrics", "workflow_versions"):
        cs = [c[1] for c in live.execute(f"PRAGMA table_info({t})")]
        conn.execute(f"CREATE TABLE IF NOT EXISTS {t} AS SELECT * FROM (SELECT 1) WHERE 0") if False else None
        ddl = live.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0]
        conn.execute(ddl)
        for r in live.execute(f"SELECT * FROM {t}"):
            conn.execute(f"INSERT INTO {t}({','.join(cs)}) VALUES({','.join('?'*len(cs))})", tuple(r))
    # 别名表：旧编号 → 新编号/丢弃原因，让 RSI 提案与台账里引用的旧 ID 仍可追溯
    conn.execute("CREATE TABLE IF NOT EXISTS knowledge_aliases(old_id TEXT PRIMARY KEY, new_id TEXT, action TEXT NOT NULL, reason TEXT NOT NULL)")
    alias = {}
    for c in cards:
        if c["action"] == "merge":
            alias[c["id"]] = (c["target"], "merge", c.get("reason", ""))
        elif c["action"] == "drop":
            alias[c["id"]] = (None, "drop", c.get("reason", ""))
    for old, (new, act, why) in alias.items():
        conn.execute("INSERT OR REPLACE INTO knowledge_aliases VALUES(?,?,?,?)", (old, new, act, why))
    rel_n = 0
    for r in live.execute("SELECT source_id,target_id,relation_type,confidence,created_at FROM knowledge_relations"):
        s = alias[r[0]][0] if r[0] in alias and alias[r[0]][0] else r[0]
        t = alias[r[1]][0] if r[1] in alias and alias[r[1]][0] else r[1]
        if s in keep and t in keep and s != t:
            conn.execute("INSERT OR IGNORE INTO knowledge_relations(source_id,target_id,relation_type,confidence,created_at) VALUES(?,?,?,?,?)", (s, t, r[2], r[3], r[4]))
            rel_n += 1
    audit["aliases"] = len(alias)
    audit["relations_kept"] = rel_n
    for k, v in live.execute("SELECT key,value FROM meta WHERE key LIKE 'sire_last_%'"):
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (k, v))
    conn.commit()

    # --- 关键词 + 后处理（FTS/trigram/语义向量）---
    vsd.sync_keywords(conn)
    conn.commit()
    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
    conn.commit()
    ski.post_index(conn)
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('knowledge_record_count',?)", (str(len(keep)),))
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('built_by','build_candidate.py')")
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('built_at',?)", (now,))
    conn.commit()
    conn.execute("VACUUM")

    # --- U3c 自检 ---
    q = lambda s: conn.execute(s).fetchone()[0]
    live_size = Path(a.live).stat().st_size
    res = {
        "integrity_check": q("PRAGMA integrity_check"),
        "chunks": q("SELECT COUNT(*) FROM chunks"),
        "chunks_latest": q("SELECT COUNT(*) FROM chunks WHERE is_latest=1"),
        "chunks_fts": q("SELECT COUNT(*) FROM chunks_fts_docsize"),
        "emb_chunk": q("SELECT COUNT(*) FROM emb WHERE kind='chunk'"),
        "cfts": q("SELECT COUNT(*) FROM cfts_docsize"),
        "emb_knowledge": q("SELECT COUNT(*) FROM emb WHERE kind='knowledge'"),
        "knowledge_records": q("SELECT COUNT(*) FROM knowledge_records"),
        "kfts": q("SELECT COUNT(*) FROM kfts_docsize"),
        "task_records": q("SELECT COUNT(*) FROM task_records"),
        "keywords": q("SELECT COUNT(*) FROM keywords"),
        "size_mb": round(out.stat().st_size / 1048576, 1),
        "live_size_mb": round(live_size / 1048576, 1),
        "size_ratio": round(out.stat().st_size / live_size, 4),
    }
    conn.close()
    checks = {
        "integrity=ok": res["integrity_check"] == "ok",
        "chunks==chunks_fts==emb_chunk==cfts": res["chunks"] == res["chunks_fts"] == res["emb_chunk"] == res["cfts"],
        "knowledge_records==keep": res["knowledge_records"] == len(keep),
        "kfts==knowledge_records": res["kfts"] == res["knowledge_records"],
        "emb_knowledge==knowledge_records": res["emb_knowledge"] == res["knowledge_records"],
        "size<=25%": res["size_ratio"] <= 0.25,
        "task_runs>=95%": runs1 >= 0.95 * runs0,
        "task audit counts": len(del_a) + len(del_b) == total0 - len(kept_rows),
    }
    audit["u3c"] = {"result": res, "checks": checks}
    Path(a.audit).write_text(json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"result": res, "checks": checks}, ensure_ascii=False, indent=1))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
