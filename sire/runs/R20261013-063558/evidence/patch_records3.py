import sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P = r"D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md"
t = open(P, encoding="utf-8").read()

fix = [
    ("`cd D:\\code\\driverSoftware2 && venv\\Scripts\\python -m pytest tests/unit -q -rs`",
     "`cd @CODE_ROOT@\\driverSoftware2 && venv\\Scripts\\python -m pytest tests/unit -q -rs`"),
    ("**三 · 构建与发布**\n", "**三 · 构建与发布（F-057，`scripts/build.bat` / `scripts/release.py`）**\n"),
    ("CHANGELOG 体例, 文档引用不实]", "CHANGELOG 体例, 文档引用不实, AGENTS.md, 行号过时, 文档引用失效]"),
    ('**docs/skills 13 份与"改什么前必读"**:',
     '**docs/skills 13 份与"改什么前必读"（本表属 F-059；核对命令 `ls docs/skills/*.md` 条数 = 13）**:'),
]
bad = []
for a, b in fix:
    n = t.count(a)
    if n != 1:
        bad.append((n, a[:40]))
    else:
        t = t.replace(a, b)
open(P, "w", encoding="utf-8", newline="\n").write(t)
print("未命中:", bad if bad else "无")
print("残留 D:\\code:", t.count("D:\\code\\driverSoftware2"), "| 残留 D:/code:", t.count("D:/code/driverSoftware2"))
for rid in ["F-053", "F-054", "F-055", "F-056", "F-057", "F-058", "F-059"]:
    i = t.find("### " + rid + ":")
    j = t.find("\n### ", i + 5)
    b = t[i:j if j > 0 else len(t)]
    kwline = b.split("**关键词**")[1].split("\n")[0]
    print(rid, "| 关键词项:", len([x for x in re.split(r"[,，]", kwline.strip(" []:：")) if x.strip()]),
          "| 定位语:", bool(re.search(r"属 F-0|本段属|本表属|（F-05\d", b)),
          "| 先记结论:", "先记结论" in b,
          "| 长度:", len(b))
