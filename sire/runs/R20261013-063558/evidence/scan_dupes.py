import os, re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
t = open(r"D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md", encoding="utf-8").read()
blocks = dict(re.findall(r"^### (F-\d{3}): [^\n]*\n(.*?)(?=^### |\Z)", t, re.M | re.S))
mine = {k: v for k, v in blocks.items() if k >= "F-053"}

# 跨记录重复展开检测：同一段较长的中文叙述出现在两条以上记录里
sents = {}
for rid, b in mine.items():
    for s in re.split(r"[。\n]", b):
        s = s.strip()
        if len(s) >= 24 and not s.startswith(("#", "*", "-", "|", "`")):
            sents.setdefault(s, set()).add(rid)
dups = {s: r for s, r in sents.items() if len(r) > 1}
print("跨记录重复长句:", len(dups))
for s, r in list(dups.items())[:6]:
    print("  ", sorted(r), "|", s[:70])

# 关键事实归属唯一性
facts = {
 "旧前端随 server.dist 走": ["F-057"],
 "后台节流 0x4D 看门狗机理": ["F-055"],
 "READER_MP 分叉行号": ["F-053"],
 "for /f 转义": ["F-057"],
}
for f in facts:
    where = [rid for rid, b in mine.items() if f.split()[0] in b and ("dist" in f or "节流" in f or "READER_MP" in f or "for /f" in f)]
    print("关键词", f, "出现在:", where)
print("指针式引用（避免重复展开）:", {rid: len(re.findall(r"见 F-0|归 F-0|机理见 F-0", b)) for rid, b in mine.items()})
