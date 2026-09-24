# -*- coding: utf-8 -*-
"""U-02 文档一致性断言；argv[1] 可替换 SKILL.md 路径（异常路径用）。"""
import re, sys
from pathlib import Path
W = Path(r"D:\sire\AI\AI\sire\workflow\shared\sire")
skill = Path(sys.argv[1]) if len(sys.argv) > 1 else W / "SKILL.md"
sk = skill.read_text(encoding="utf-8"); sv = (W/"references/supervisor.md").read_text(encoding="utf-8")
sup = (W/"scripts/sire_supervisor.py").read_text(encoding="utf-8"); rsi = (W/"scripts/sire_rsi.py").read_text(encoding="utf-8")
res = []
def ok(n, c): res.append(c); print(("PASS " if c else "FAIL ") + n)
for w in ["rsi-check","finalize","rsi_unregistered_change","STOP","PROPOSED","EVALUATED_PASS","ACTIVE"]:
    ok(f"{w} 在文档且在 sire_supervisor.py", (w in sk or w in sv) and w in sup)
for w in ["propose","evaluate","activate","rollback"]:
    ok(f"{w} 在 SKILL.md 且在 sire_rsi.py", w in sk and w in rsi)
ok("SKILL.md 含 ## Workflow changes (RSI)", "## Workflow changes (RSI)" in sk)
links = re.findall(r"\]\((references/self-optimization\.md)[^)]*\)", sk)
ok("SKILL.md 链接 self-optimization.md 且文件存在", bool(links) and (W/links[0]).is_file())
ok("supervisor.md 第 8 项含 rsi-check", bool(re.search(r"^8\. .*rsi-check", sv, re.M)))
print("ALL", "PASS" if all(res) else "FAIL"); sys.exit(0 if all(res) else 1)
