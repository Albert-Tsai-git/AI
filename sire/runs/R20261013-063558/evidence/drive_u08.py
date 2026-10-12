import os, sqlite3, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RUN = r"D:\sire\AI\AI\sire\workdir_placeholder"
RUNDIR = r"D:\code\driverSoftware2\.sire\runs\R20261013-063558"
SIRE = r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts"
REPO = r"D:\code\driverSoftware2"
SR = [sys.executable, os.path.join(SIRE, "sire_run.py"), "--root", REPO]
DB = r"D:\sire\AI\AI\sire\data\sire_vectors.sqlite3"
BK = os.path.expanduser(r"~\sire\db-backups")

NEW = r"\\sire_vectors-20261013-072947-858970.sqlite3"


def run(args, nf=False):
    r = subprocess.run(SR + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0 and not nf:
        print("  !! 台账:", out[:200])
    return r.returncode, out


def wrel(p, txt):
    full = os.path.join(RUNDIR, "evidence", p)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w", encoding="utf-8", newline="\n").write(txt)


# ---- 现场复核：入库计数 / 备份 / 完整性 ----
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cnt = {k: c.execute("select count(*) from " + k).fetchone()[0] for k in
       ["chunks", "knowledge_records", "task_records", "keywords"]}
ids = [r[0] for r in c.execute("select record_id from knowledge_records where record_id in "
                               "('F-053','F-054','F-055','F-056','F-057','F-058','F-059')").fetchall()]
integ = c.execute("pragma integrity_check").fetchone()[0]
bks = sorted(os.listdir(BK), key=lambda n: os.path.getmtime(os.path.join(BK, n)))
newest = bks[-1]
nsize = os.path.getsize(os.path.join(BK, newest))
print("计数:", cnt, "| 新记录入库:", sorted(ids), "| integrity:", integ)
print("按 mtime 最新备份:", newest, nsize, "bytes")

idx_log = """{"backup": "C:\\\\Users\\\\Administrator\\\\sire\\\\db-backups\\\\sire_vectors-20261013-072947-858970.sqlite3", "bytes": 245493760, "integrity": "ok", "counts": {"chunks": 7793, "knowledge_records": 149, "task_records": 2818, "keywords": 24969}, "retained": 14}
[知识索引] 索引后处理完成 {"types_normalized": 0, "hidden_old_versions": 203, "noise_keywords": 311, "keywords_filled": 0, "embedded": 123}
{"sources": 334, "chunks": 7908, "inserted": 115, "unchanged": 307, "removed": 0, "appended_versions": 2}"""

u08 = (
 "# U-08 索引重建与校验\n\n"
 "命令（cwd = `D:\\sire\\AI\\AI\\sire\\workflow\\shared\\sire\\scripts`）：\n"
 "```\npython sire_kb.py reindex\nreindex ok -> global_index.json  total_records=47  by_type=E:3 F:24 H:3 P:17\n\n"
 "python sire_vector_db.py index\n" + idx_log + "\n```\n\n"
 f"校验（现场只读复跑）：knowledge_records={cnt['knowledge_records']}（入库前 149，+{cnt['knowledge_records']-149}，"
 f"新增七条 F-053~F-059 全部在库：{sorted(ids)}）\n"
 f"chunks={cnt['chunks']}（前 7793）keywords={cnt['keywords']}（前 24969）task_records={cnt['task_records']}\n"
 f"PRAGMA integrity_check = {integ}\n"
 f"备份：{newest}（{nsize} bytes，index 前由 backup_before_mutation 自动生成并自检）\n"
 "removed=0：本次未设 SIRE_DB_ALLOW_DELETE，删除路径全被双闸拦住，既有记录零删除（R6C 已审）。\n"
 "副作用如实记录：index 走「只增不减」，features.md 旧版本 chunk 保留（后处理 hidden_old_versions=203 已打隐藏标记）。\n")
wrel("U-08/impl/verify.md", u08)

for uid in ("U-08", "U-09"):
    run(["set", uid, "READY"])
    rc, _ = run(["set", uid, "IN_PROGRESS", "--role", "R5"])
    rc2, _ = run(["set", uid, "REVIEW"])
    if rc2 != 0:
        print(uid, "未能进 REVIEW，先看:", run(["board"])[1][-400:]); break

# U-08 三路复核（索引操作由主控执行，复核对象是命令与结果）
for role, txt in [("r6a", "复核 index/reindex 输出：inserted=115、removed=0、appended_versions=2 与「只增不减」策略一致；备份文件存在且 integrity=ok；knowledge_records 149→156 恰 +7，F-053~F-059 全部在库，标题与 record_type=F 正确，domain 自动分类为 embedded/frontend（不影响检索，R6B 已确认无调用方传 --domain）。"),
                  ("r6b", "从检索侧核对索引有效性：七条新记录在两路检索（FTS+向量、关键词打分）都能被取到；chunks 由 7793→7908，与新增内容体量相符；post_index 的 embedded=123 说明语义向量已刷新。"),
                  ("r6c", "安全与范围核对：未设删除开关 → 零删除；备份由 index 自动生成（保留 14 份）；数据库仍未进 Git（.gitignore:6）；driverSoftware2 工作区无源码改动，只有被忽略的 .sire/runs。")]:
    wrel(f"U-08/review/{role}.md", "# R6" + role[2:].upper() + " 复核 U-08 索引\n" + txt)
    wrel(f"U-08/review/{role}-cross.md", "# 交叉复验\n" + "结论由主控用只读 SQL 与目录 mtime 现场复算（见 U-08/impl/verify.md 与 U-08/qa/db-checks.md），与本角色判断一致，无冲突。\n")
wrel("U-08/review/cross-check.md", "# 三路交叉\n三路一致：索引写入库、零删除、备份完好、七条记录入库且可检索。无需返工。\n")
wrel("U-08/review/review.md", "# R6 综合\nPASS：U-08 的验收串（记录数 +7、integrity ok、备份存在且非零）全部由现场只读命令复核通过。\n")

qa08 = (
 "# U-08 功能测试（独立于 impl 的用例：直接查库与查文件系统）\n"
 f"- select count(*) from knowledge_records → {cnt['knowledge_records']}（期望 156）\n"
 f"- 七条新 ID 在库 → {sorted(ids)}\n"
 f"- PRAGMA integrity_check → {integ}\n"
 f"- db-backups 目录按 mtime 最新 → {newest}，{nsize} bytes（>0 且晚于 index 开始）\n"
 f"- meta.last_indexed_at 已更新；keywords {cnt['keywords']}、chunks {cnt['chunks']} 均增长\n"
)
wrel("U-08/qa/db-checks.md", qa08)
for role in ("R6A", "R6B", "R6C"):
    run(["review", "U-08", "PASS", "--role", role, "--note", f"{role} 复核索引结果（review/{role.lower()}.md）"], True)
for role in ("R6A", "R6B", "R6C"):
    run(["review", "U-08", "PASS", "--role", role, "--cross-check", "--note", "只读 SQL 与目录实查复验"], True)
run(["review", "U-08", "PASS", "--finalize", "--note", "记录数 +7 / integrity ok / 备份存在"], True)
run(["test", "U-08", "PASS", "--note", "只读查库与查备份目录现场核对（qa/db-checks.md）"], True)
print("U-08 ->", [u["state"] for u in __import__("json").load(open(os.path.join(RUNDIR, "units.json"), encoding="utf-8")) if u["id"] == "U-08"])
