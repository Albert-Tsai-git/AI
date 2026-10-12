import json, os, sqlite3, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = r"D:\sire\AI\AI\sire\data\sire_vectors.sqlite3"
SIRE = r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts"
BK = os.path.expanduser(r"~\sire\db-backups")

c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
print("knowledge_records:", c.execute("select count(*) from knowledge_records").fetchone()[0])
print("chunks:", c.execute("select count(*) from chunks").fetchone()[0])
print("keywords:", c.execute("select count(*) from keywords").fetchone()[0])
print("task_records:", c.execute("select count(*) from task_records").fetchone()[0])
print("integrity_check:", c.execute("pragma integrity_check").fetchone()[0])
rows = c.execute("select record_id, title, record_type, domain, kind, scope, length(keywords) kwlen "
                 "from knowledge_records where record_id like 'F-05%' order by record_id").fetchall()
for r in rows:
    print(" 入库:", r)
bk = sorted(os.listdir(BK))[-1]
print("最新备份:", bk, os.path.getsize(os.path.join(BK, bk)), "bytes")

titles = {r[0]: r[1] for r in rows if r[0] in {"F-053","F-054","F-055","F-056","F-057","F-058","F-059"}}
queries = [
 ("后端 reader 双形态 端口 无响应", {"F-053"}),
 ("协议 寄存器 固件档案 V3.3 新加命令", {"F-054"}),
 ("前端 页面 注册 示波器 切页", {"F-055"}),
 ("Electron 壳 启动 端口 黑屏", {"F-056"}),
 ("测试 打包 旧前端 CI 发布", {"F-057"}),
 ("下线检测 坏点 额定扭矩 建零", {"F-058"}),
 ("文档 必读 skill 缺陷池 真机台账", {"F-059"}),
]
print("\n=== 向量检索（limit 5）===")
fails = []
for q, want in queries:
    p = subprocess.run([sys.executable, os.path.join(SIRE, "sire_vector_db.py"), "search",
                        "--query", q, "--json", "--limit", "5"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        hits = json.loads(p.stdout)["hits"]
    except Exception:
        print(q, "-> 解析失败", (p.stdout or p.stderr)[:200]); fails.append(q); continue
    got = []
    for h in hits:
        tag = next((rid for rid, ti in titles.items() if ti[:18] in (h.get("title") or "")), None)
        got.append((h.get("record_id") or tag or (h.get("title") or "")[:22], round(h.get("score", 0), 4)))
    hit_new = [g for g in got if g[0] in titles]
    ok = any(g[0] in want for g in got[:5])
    print(f"{q}\n   top5={got}  新记录命中={hit_new}  {'PASS' if ok else 'FAIL'}")
    if not ok:
        fails.append(q)

print("\n=== 关键词检索（sire_kb search, top5）===")
for q, want in queries:
    p = subprocess.run([sys.executable, os.path.join(SIRE, "sire_kb.py"), "search", q],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ids = [l.split()[0] for l in (p.stdout or "").splitlines() if l.startswith(("F-", "P-", "H-", "E-", "K-"))]
    ok = any(i in want for i in ids[:5])
    print(f"{q}\n   top5={ids[:5]}  {'PASS' if ok else 'FAIL'}")
    if not ok:
        fails.append("kb:" + q)

old = [h for h in c.execute("select title from knowledge_records where record_id='K-REPO-DRIVERSOFTWARE-20260924'").fetchall()]
p = subprocess.run([sys.executable, os.path.join(SIRE, "sire_vector_db.py"), "search", "--query",
                    "driverSoftware 仓库 架构 入口", "--json", "--limit", "5"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
hits = json.loads(p.stdout)["hits"]
rank = {h.get("record_id"): i for i, h in enumerate(hits)}
print("\n=== 新旧对比（同一问法）===")
print("   top5:", [(h.get("record_id") or (h.get("title") or "")[:24], round(h["score"], 4)) for h in hits])
print("   旧摘要 K-REPO-DRIVERSOFTWARE 名次:", rank.get("K-REPO-DRIVERSOFTWARE-20260924", "未进前5"),
      "| 新记录名次:", {k: v for k, v in rank.items() if k and k.startswith("F-05")})
print("\n总判定:", "PASS" if not fails else f"FAIL 未命中组: {fails}")
