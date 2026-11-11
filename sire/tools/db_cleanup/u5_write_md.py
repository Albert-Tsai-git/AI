# -*- coding: utf-8 -*-
"""U5：把合并后的知识卡片写回 md 知识源（只写 md 文件，不碰任何数据库）。"""
import glob
import json
import re
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts")
SP = Path(sys.argv[1])
KB = Path(r"D:\sire\AI\AI\sire\knowledge\global")
BAK = Path(r"D:\sire\db-candidate\md-backup")
BAK.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SP))
import build_candidate as bc  # noqa: E402  渲染函数与映射

cards = []
for p in sorted(glob.glob(str(SP / "cards_*.json"))):
    cards += json.load(open(p, encoding="utf-8"))
keep = [c for c in cards if c["action"] == "keep"]
ID_RE = re.compile(r"^([FPEH])-(\d+)(?:#(\d+))?$")
db_only, per = [], {"F": [], "P": [], "E": [], "H": []}
for c in keep:
    m = ID_RE.match(c["id"])
    if not m:
        db_only.append(c["id"])
        continue
    per[m.group(1)].append((m.group(1) + "-" + m.group(2), int(m.group(3) or 1), c))
problems = []
for letter, items in per.items():
    items.sort(key=lambda x: (x[0], x[1]))
    # '#n' 重复头由解析器按出现顺序编号，所以必须 base 存在且序号连续
    seen = {}
    for base, n, c in items:
        seen.setdefault(base, []).append(n)
    for base, ns in seen.items():
        if ns != list(range(1, len(ns) + 1)):
            problems.append((base, ns))
    fn = KB / bc.MD_MAP[letter]
    old = fn.read_text(encoding="utf-8", errors="replace")
    if not (BAK / (fn.name + ".before")).exists():  # 已有备份不覆盖，重跑也保留最初版本
        shutil.copy2(fn, BAK / (fn.name + ".before"))
    pre = []
    for line in old.splitlines():
        if re.match(r"^###\s+[FPEHK]-", line):
            break
        pre.append(line)
    out = ["\n".join(pre).rstrip(), ""]
    for base, n, c in items:
        card = c.get("card") or c
        out += [f"### {base}: {card.get('title') or c['id']}", bc.render_card(card), ""]
    fn.write_text("\n".join(out), encoding="utf-8")
    print(letter, "写入", len(items), "条 ->", fn.name)
print("仅存数据库(非标准编号)", len(db_only), db_only)
print("序号不连续的问题", problems)
