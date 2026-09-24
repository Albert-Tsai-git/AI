# -*- coding: utf-8 -*-
"""[评测] SIRE 知识检索评测：recall@1/@3/@5 与平均耗时。用法: python run_eval.py [标签]"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workflow" / "codex" / "ai-dev-sire-workflow" / "scripts"))
import sire_vector_db as v  # noqa: E402

DB = Path(os.environ.get("SIRE_VECTOR_DB") or Path(__file__).resolve().parents[1] / "data" / "sire_vectors.sqlite3")
QUERIES = json.loads((Path(__file__).parent / "queries.json").read_text(encoding="utf-8"))
ID_RE = re.compile(r"\b([FPEHK]-\d+(?:#\d+)?)\b")


def hit_ids(hit):
    """命中项 → 知识 ID：knowledge:XXX 直接取；普通片段取正文里出现的记录编号。"""
    hid = str(hit["id"])
    if hid.startswith("knowledge:"):
        return [hid[len("knowledge:"):]]
    return ID_RE.findall(hit.get("title", "") + " " + hit.get("content", "")[:400])


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    r1 = r3 = r5 = 0
    total_ms = 0.0
    rows = []
    for item in QUERIES:
        t0 = time.perf_counter()
        hits = v.search_database(DB, item["q"], 5, 0.0)
        ms = (time.perf_counter() - t0) * 1000
        total_ms += ms
        ranked = [hit_ids(h) for h in hits]
        exp = set(item["expect"])
        pos = next((i for i, ids in enumerate(ranked) if exp & set(ids)), None)
        r1 += pos is not None and pos < 1
        r3 += pos is not None and pos < 3
        r5 += pos is not None and pos < 5
        top = [str(h["id"])[:34] for h in hits[:3]]
        rows.append((item["q"][:26], "-" if pos is None else pos + 1, round(ms), top))
    n = len(QUERIES)
    for r in rows:
        print("%-28s 命中位次=%-2s %5dms  %s" % r)
    summary = {"label": label, "n": n, "recall@1": round(r1 / n, 2), "recall@3": round(r3 / n, 2),
               "recall@5": round(r5 / n, 2), "avg_ms": round(total_ms / n)}
    print(json.dumps(summary, ensure_ascii=False))
    with open(Path(__file__).parent / "results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
