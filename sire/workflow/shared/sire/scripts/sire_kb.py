#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SIRE v6 知识库 CLI —— 检索 / 归档编号 / 索引重建。

索引只能由本脚本生成，禁止手写。

用法:
  sire_kb.py reindex
  sire_kb.py search "关键词1 关键词2"
  sire_kb.py search-database "关键词1 关键词2"
  sire_kb.py show F-004
  sire_kb.py next-id F
  sire_kb.py stats
"""
import argparse
import json
import os
import re
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sire_paths import DATABASE_PATH, KNOWLEDGE_DIR, SHARED_SKILL_DIR

KB_DIR = str(KNOWLEDGE_DIR)
INDEX_PATH = os.path.join(KB_DIR, "global_index.json")
VECTOR_DB = str(DATABASE_PATH)

TYPE_MAP = {"F": "feature", "P": "problem", "E": "efficiency", "H": "habit", "K": "knowledge"}
BUCKET = {"F": "features", "P": "problems", "E": "efficiency", "H": "habits"}
TARGET_FILE = {
    "F": "global_dev_features.md",
    "P": "global_problem_solutions.md",
    "E": "global_dev_efficiency.md",
    "H": "global_dev_habits.md",
}

HDR = re.compile(r"^###\s+([FPEH])-(\d+)\s*[:：]\s*(.+?)\s*$")
# 旧格式记录：## 2026-09-03 | 标题。没有编号，但必须可检索，否则检索有盲区。
LEGACY_HDR = re.compile(r"^##\s+(20\d{2}-\d{2}-\d{2})\s*\|\s*(.+?)\s*$")
FILE_LETTER = (("problem", "P"), ("efficiency", "E"), ("habit", "H"), ("feature", "F"))
KW = re.compile(r"^\*\*关键词\*\*\s*[:：]\s*\[?(.+?)\]?\s*$")
DATE = re.compile(r"^\*\*日期\*\*\s*[:：]\s*(.+?)\s*$")
PROJ = re.compile(r"^\*\*项目\*\*\s*[:：]\s*(.+?)\s*$")
STATUS = re.compile(r"^\*\*状态\*\*\s*[:：]\s*(.+?)\s*$")


def md_files():
    if not os.path.isdir(KB_DIR):
        return []
    out = []
    for root, dirs, files in os.walk(KB_DIR):
        # Integrity snapshots/backups and generated database exports are not canonical knowledge.
        dirs[:] = [name for name in dirs if name.lower() not in {"integrity", "secrets", "exports"}]
        for name in sorted(files):
            if name.lower() == "global_knowledge_records.md":
                continue
            if name.endswith(".md") and not name.endswith(".bak"):
                out.append(os.path.join(root, name))
    return out


def parse_records():
    """扫描知识库全部 md，抽取 '### X-000: 标题' 形式的记录。"""
    records = []
    seen = {}
    for path in md_files():
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        rel = os.path.relpath(path, KB_DIR).replace("\\", "/")
        letter_for_file = "F"
        for key, val in FILE_LETTER:
            if key in os.path.basename(path).lower():
                letter_for_file = val
                break
        legacy_n = 0
        cur = None
        for i, line in enumerate(lines, 1):
            lm = LEGACY_HDR.match(line)
            if lm:
                if cur:
                    records.append(cur)
                legacy_n += 1
                # 编号带 L 前缀，故意不匹配 ^[FPEH]-\d+$，这样它不能被当成本次归档记录
                rid = "%s-L%03d" % (letter_for_file, legacy_n)
                seen.setdefault(rid, []).append(rel)
                cur = {
                    "id": rid, "letter": letter_for_file, "type": TYPE_MAP[letter_for_file],
                    "title": lm.group(2), "file": rel, "line": i,
                    "date": lm.group(1), "project": "", "status": "旧格式", "keywords": [],
                    "_body": [],
                }
                continue
            m = HDR.match(line)
            if m:
                if cur:
                    records.append(cur)
                rid = "%s-%s" % (m.group(1), m.group(2))
                seen.setdefault(rid, []).append(rel)
                cur = {
                    "id": rid, "letter": m.group(1), "type": TYPE_MAP[m.group(1)],
                    "title": m.group(3), "file": rel, "line": i,
                    "date": "", "project": "", "status": "", "keywords": [], "_body": [],
                }
                continue
            if cur is None:
                continue
            if line.startswith("### ") or line.startswith("## "):
                records.append(cur)
                cur = None
                continue
            cur["_body"].append(line)
            mm = KW.match(line)
            if mm:
                cur["keywords"] = [w.strip() for w in re.split(r"[,，]", mm.group(1)) if w.strip()]
                continue
            for rx, key in ((DATE, "date"), (PROJ, "project"), (STATUS, "status")):
                mm = rx.match(line)
                if mm:
                    cur[key] = mm.group(1).strip()
                    break
        if cur:
            records.append(cur)
    # A repeated ID is invalid even when both records live in the same file.
    conflicts = dict((k, v) for k, v in seen.items() if len(v) > 1)
    return records, conflicts


def build_index(records):
    idx = {"records": [], "features": {}, "problems": {}, "efficiency": {}, "habits": {}}
    fields = ("id", "type", "title", "file", "line", "date", "project", "status", "keywords")
    for r in records:
        idx["records"].append(dict((k, r[k]) for k in fields))
        bucket = idx[BUCKET[r["letter"]]]
        for kw in r["keywords"]:
            bucket.setdefault(kw, [])
            if r["id"] not in bucket[kw]:
                bucket[kw].append(r["id"])
    idx["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    idx["total_records"] = len(records)
    return idx


def cmd_reindex(_args):
    records, conflicts = parse_records()
    if conflicts:
        items = ["%s(%s)" % (k, ",".join(sorted(set(v)))) for k, v in sorted(conflicts.items())]
        print("WARN 编号重复: " + "; ".join(items))
        return 1
    idx = build_index(records)
    os.makedirs(KB_DIR, exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False, indent=2)
    print("reindex ok -> %s" % INDEX_PATH)
    print("total_records=%d" % idx["total_records"])
    by = {}
    for r in records:
        by[r["letter"]] = by.get(r["letter"], 0) + 1
    print("by_type=" + " ".join("%s:%d" % (k, by[k]) for k in sorted(by)))
    return 0


CODEX_SCRIPTS = str(SHARED_SKILL_DIR / "scripts")


def _field(body, rx):
    for line in body.splitlines():
        m = rx.match(line.strip())
        if m:
            return m.group(1).strip()
    return ""


def load_db_records():
    """[知识库] ★ 2026-09-24 以向量库 knowledge_records 为正式知识源（md 中已有 81 条缺失）。"""
    import sqlite3
    if not os.path.isfile(VECTOR_DB):
        return []
    conn = sqlite3.connect("file:%s?mode=ro" % VECTOR_DB, uri=True)
    try:
        rows = conn.execute("SELECT record_id, record_type, title, source_path, source_line, keywords, body "
                            "FROM knowledge_records WHERE status != 'removed' ORDER BY record_id").fetchall()
    finally:
        conn.close()
    out = []
    for rid, rtype, title, src, line, kws, body in rows:
        letter = rtype if rtype in TYPE_MAP else "K"
        out.append({
            "id": rid, "letter": letter, "type": TYPE_MAP.get(letter, "knowledge"), "title": title,
            "file": src, "line": int(line or 0), "date": _field(body, DATE), "project": _field(body, PROJ),
            "status": _field(body, STATUS),
            "keywords": [w.strip() for w in re.split(r"[,，、\[\]]+", kws or "") if w.strip()],
            "_body": body.splitlines(),
        })
    return out


def load_records():
    """数据库优先；库不可用时回退 Markdown。"""
    try:
        records = load_db_records()
        if records:
            return records
    except Exception as exc:  # noqa: BLE001
        print("WARN 读取向量库知识失败 (%s)，回退 Markdown" % exc)
    records, _ = parse_records()
    return records


def reuse_points(body):
    try:
        sys.path.insert(0, CODEX_SCRIPTS)
        import sire_knowledge_index as ski
        return ski.reuse_points(body)
    except Exception:  # noqa: BLE001
        return []


def score(rec, terms):
    kw = " ".join(rec["keywords"]).lower()
    title = rec["title"].lower()
    body = "\n".join(rec.get("_body", [])).lower()
    proj = (rec.get("project") or "").lower()
    total = 0
    hits = []
    for t in terms:
        tl = t.lower()
        w = 0
        if tl in kw:
            w += 5
        if tl in title:
            w += 4
        if tl in proj:
            w += 2
        if tl in body:
            w += 1
        if w:
            hits.append(t)
        total += w
    return total, hits


def write_receipt(run_dir, terms, kb_total, hits):
    """把检索行为写成回执，供台账 G0 门禁核验，堵死手写 kb-hits 蒙混过关。"""
    if not run_dir:
        return
    try:
        run_dir = os.path.abspath(run_dir)
        if not os.path.isdir(run_dir):
            print("WARN 回执目录不存在，检索未被记录: %s" % run_dir)
            return
        # run_id 取自目录名，让回执绑死在这个 run 上，复制到别处即失效
        rec = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "run_id": os.path.basename(run_dir.rstrip("\\/")),
               "terms": terms, "kb_dir": os.path.abspath(KB_DIR),
               "kb_total": kb_total, "hits": hits}
        with open(os.path.join(run_dir, "kb-search.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("回执已记录: %s" % rec["run_id"])
    except OSError as exc:
        print("WARN 回执写入失败: %s" % exc)


def cmd_search(args):
    if getattr(args, "database", False):
        vector = str(SHARED_SKILL_DIR / "scripts" / "sire_vector_db.py")
        query = " ".join(args.query).strip()
        if not query:
            print("ERROR 需要检索词")
            return 2
        result = subprocess.run([sys.executable, vector, "search", "--query", query,
                                 "--json", "--limit", str(args.limit)],
                                text=True, capture_output=True, encoding="utf-8")
        if result.returncode:
            print(result.stderr.strip() or "数据库检索失败")
            return result.returncode
        payload = json.loads(result.stdout)
        print("数据库检索词: %s" % query)
        print("命中: %d 条" % len(payload.get("hits", [])))
        for hit in payload.get("hits", []):
            rid = hit.get("record_id") or str(hit.get("id"))
            print("- [%s] %s  score=%s" % (rid, hit.get("title"), hit.get("score")))
            print("  来源: %s" % hit.get("path"))
            if hit.get("reuse"):
                print("  复用要点:")
                for p in hit["reuse"]:
                    print("    · %s" % p)
            else:
                print("  摘要: %s" % hit.get("content", "")[:300].replace("\n", " "))
        print("下一步: sire_kb.py show <ID> 读全文，按复用要点直接开发")
        return 0
    terms = [t for t in re.split(r"\s+", " ".join(args.query).strip()) if t]
    if not terms:
        print("ERROR 需要检索词")
        return 2
    records = load_records()
    print("检索词: %s" % " ".join(terms))
    if not records:
        write_receipt(args.run, terms, 0, 0)
        print("命中: 无（知识库为空）")
        print("判定: 全新需求")
        return 0
    scored = []
    for r in records:
        s, hits = score(r, terms)
        if s > 0:
            scored.append((s, hits, r))
    scored.sort(key=lambda x: -x[0])
    write_receipt(args.run, terms, len(records), len(scored))
    if not scored:
        print("命中: 无")
        print("判定: 全新需求")
        return 0
    top = scored[: args.limit]
    print("命中: %d 条（显示前 %d）" % (len(scored), len(top)))
    for s, hits, r in top:
        print("-" * 60)
        print("%s  score=%d  match=%s" % (r["id"], s, ",".join(hits)))
        print("  标题: %s" % r["title"])
        print("  项目: %s  日期: %s  状态: %s"
              % (r.get("project") or "-", r.get("date") or "-", r.get("status") or "-"))
        print("  位置: %s:%d" % (r["file"], r["line"]))
        print("  关键词: %s" % (", ".join(r["keywords"]) if r["keywords"] else "-"))
        for p in reuse_points("\n".join(r["_body"]))[:3]:
            print("  · %s" % p[:160])
    print("-" * 60)
    print("下一步: 用 show <ID> 读全文，再判定 已实现过 / 部分可参考 / 全新需求")
    return 0


def cmd_show(args):
    rid = args.record_id.strip()
    for r in load_records():
        if r["id"] == rid or r["id"].upper() == rid.upper():
            print("### %s: %s" % (r["id"], r["title"]))
            print("来源: %s:%d" % (r["file"], r["line"]))
            print("")
            print("\n".join(r["_body"]).strip())
            return 0
    print("ERROR 未找到记录 %s" % rid)
    return 1


def _db_record_numbers(letter):
    """只读向量库 knowledge_records 里某类型已占用的编号; 库不存在/读失败返回空 (不阻塞编号)。"""
    import sqlite3
    db = VECTOR_DB
    if not os.path.isfile(db):
        return []
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        try:
            rows = conn.execute("SELECT record_id FROM knowledge_records WHERE record_id LIKE ?",
                                (letter + "-%",)).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        print("WARN 读取向量库编号失败 (%s)，仅按 Markdown 编号" % exc)
        return []
    out = []
    for (rid,) in rows:
        m = re.match(r"^%s-(\d+)$" % letter, rid)
        if m:
            out.append(int(m.group(1)))
    return out


def cmd_next_id(args):
    letter = args.type.strip().upper()
    if letter not in TYPE_MAP:
        print("ERROR 类型必须是 F/P/E/H")
        return 2
    nums = []
    for r in load_records():
        if r["letter"] != letter:
            continue
        tail = r["id"].split("-")[1]
        if tail.isdigit():          # 跳过 L 前缀的旧格式记录，它们不参与编号
            nums.append(int(tail))
    # ★ 2026-09-22: 向量库 knowledge_records 才是正式知识源, Markdown 可能已迁走/为空。
    #   只扫 Markdown 会分配出库里已占用的编号, 而 sire_vector_db 同步是 INSERT OR REPLACE
    #   ⇒ 静默覆盖他人记录 (实测 P-001~P-003/H-001 被覆盖, 已从备份恢复)。编号取两者最大值。
    nums.extend(_db_record_numbers(letter))
    nxt = (max(nums) + 1) if nums else 1
    target = os.path.join(KB_DIR, TARGET_FILE[letter])
    print("%s-%03d" % (letter, nxt))
    print("写入文件: %s" % target)
    if os.path.exists(target) and not os.access(target, os.W_OK):
        print("ERROR 目标文件只读，归档会失败。先解除只读属性再归档：")
        print('  powershell -Command "Set-ItemProperty -Path \'%s\' -Name IsReadOnly -Value $false"' % target)
        return 1
    return 0


EXPORT_FILE = os.path.join(KB_DIR, "global_knowledge_records.md")
TEMPLATE_PATH = os.path.join(KB_DIR, "KNOWLEDGE_TEMPLATE.md")
# 可复用知识的必备段落（与 KNOWLEDGE_TEMPLATE.md 一致）
REQUIRED_SECTIONS = [("需求场景", r"需求|场景|现象"), ("方案", r"方案|架构|做法|修复|解决|实现"),
                     ("关键文件", r"关键文件|涉及文件|涉及模块|文件"), ("验证", r"验证|测试|验收")]


def cmd_export_md(_args):
    """[知识库] 把只存在于数据库的记录导出为 Markdown 副本（人可读 + 灾备），不改数据库。"""
    md_ids = {r["id"] for r in parse_records()[0]}
    db = [r for r in load_db_records() if r["id"] not in md_ids]
    lines = ["# 知识记录（数据库导出副本）", "",
             "> 由 `sire_kb.py export-md` 生成，数据库 knowledge_records 为正式来源；请勿手工编辑，修改请走 `sire_kb.py add` 或原始 md。",
             "> 生成时间: %s，共 %d 条" % (datetime.now().strftime("%Y-%m-%d %H:%M"), len(db)), ""]
    for r in db:
        lines += ["#### %s: %s" % (r["id"], r["title"]), "",
                  "**类型**: %s  **来源**: %s" % (r["letter"], r["file"])]
        if r["keywords"]:
            lines.append("**关键词**: %s" % ", ".join(r["keywords"]))
        lines += ["", "\n".join(r["_body"]).strip(), ""]
    with open(EXPORT_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("[知识库] 已导出 %d 条仅存于数据库的记录 -> %s" % (len(db), EXPORT_FILE))
    return 0


def lint_record(r):
    body = "\n".join(r["_body"])
    issues = []
    if len(body) < 300:
        issues.append("正文过短(%d字)" % len(body))
    if not r["keywords"]:
        issues.append("无关键词")
    for name, rx in REQUIRED_SECTIONS:
        if not re.search(rx, body):
            issues.append("缺「%s」" % name)
    return issues


def cmd_lint(args):
    """[知识库] 检查知识是否可直接复用开发：正文长度、关键词、需求/方案/关键文件/验证。"""
    records = load_records()
    bad = [(r, lint_record(r)) for r in records]
    bad = [(r, i) for r, i in bad if i]
    print("知识总数: %d  需补全: %d" % (len(records), len(bad)))
    for r, issues in bad[: args.limit]:
        print("- %-40s %s  | %s" % (r["id"][:40], "；".join(issues), r["title"][:40]))
    return 0


def cmd_add(args):
    """[知识库] 按模板新增一条知识：校验必备段落 → 分配编号 → 追加到对应 md。之后需执行 sire_vector_db.py index 同步入库。"""
    letter = args.type.strip().upper()
    if letter not in TARGET_FILE:
        print("ERROR 类型必须是 F/P/E/H")
        return 2
    with open(args.file, "r", encoding="utf-8-sig") as fh:
        body = fh.read().strip()
    rec = {"_body": body.splitlines(), "keywords": [w for w in re.split(r"[,，]", _field(body, KW) or "") if w.strip()]}
    issues = lint_record(rec)
    if issues and not args.force:
        print("ERROR 不满足可复用知识模板（见 %s）: %s" % (TEMPLATE_PATH, "；".join(issues)))
        print("补全后重试，或加 --force 强制写入")
        return 1
    nums = [int(m.group(1)) for r in load_records() for m in [re.match(r"^%s-(\d+)$" % letter, r["id"])] if m]
    nums.extend(_db_record_numbers(letter))
    rid = "%s-%03d" % (letter, (max(nums) + 1) if nums else 1)
    target = os.path.join(KB_DIR, TARGET_FILE[letter])
    with open(target, "a", encoding="utf-8") as fh:
        fh.write("\n\n### %s: %s\n\n%s\n" % (rid, args.title.strip(), body))
    print("[知识库] 已写入 %s -> %s" % (rid, target))
    print("下一步: python %s index" % os.path.join(CODEX_SCRIPTS, "sire_vector_db.py"))
    return 0


def cmd_stats(_args):
    db = load_db_records()
    dby = {}
    for r in db:
        dby[r["letter"]] = dby.get(r["letter"], 0) + 1
    print("向量库(正式来源): %s  记录 %d  %s" % (VECTOR_DB, len(db), " ".join("%s:%d" % (k, dby[k]) for k in sorted(dby))))
    records, conflicts = parse_records()
    by = {}
    for r in records:
        by[r["letter"]] = by.get(r["letter"], 0) + 1
    print("知识库: %s" % KB_DIR)
    print("Markdown 记录数: %d（其余在 global_knowledge_records.md 导出副本）" % len(records))
    for k in sorted(by):
        print("  %s: %d" % (k, by[k]))
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as fh:
                idx = json.load(fh)
            stale = idx.get("total_records") != len(records)
            print("索引: %s (total=%s)%s"
                  % (idx.get("last_updated"), idx.get("total_records"),
                     "  [过期，需 reindex]" if stale else ""))
        except (OSError, ValueError):
            print("索引: 损坏，需 reindex")
    else:
        print("索引: 不存在，需 reindex")
    if conflicts:
        print("WARN 编号重复: %s" % ", ".join(sorted(conflicts)))
    return 0


def main():
    parser = argparse.ArgumentParser(description="SIRE v6 知识库 CLI")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("reindex")
    p = sub.add_parser("search", aliases=["search-database", "database-search"])
    p.set_defaults(database=False)
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--run", default=os.environ.get("SIRE_RUN_DIR"),
                   help="台账 run 目录，写入检索回执供 G0 门禁核验")
    p = sub.add_parser("show")
    p.add_argument("record_id")
    p = sub.add_parser("next-id")
    p.add_argument("type")
    sub.add_parser("stats")
    sub.add_parser("export-md")
    p = sub.add_parser("lint")
    p.add_argument("--limit", type=int, default=200)
    p = sub.add_parser("add")
    p.add_argument("type")
    p.add_argument("--title", required=True)
    p.add_argument("--file", required=True, help="按 KNOWLEDGE_TEMPLATE.md 填写的正文文件")
    p.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.cmd in ("search-database", "database-search"):
        args.database = True
    fn = {
        "reindex": cmd_reindex, "search": cmd_search, "search-database": cmd_search,
        "database-search": cmd_search, "show": cmd_show,
        "next-id": cmd_next_id, "stats": cmd_stats,
        "export-md": cmd_export_md, "lint": cmd_lint, "add": cmd_add,
    }.get(args.cmd)
    if not fn:
        parser.print_help()
        return 2
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
