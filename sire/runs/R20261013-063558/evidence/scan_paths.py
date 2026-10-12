import sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
t = open(r"D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md", encoding="utf-8").read()
mine = {}
for m in re.finditer(r"^### (F-\d{3}): [^\n]*\n(.*?)(?=^### |\Z)", t, re.M | re.S):
    mine[m.group(1)] = (m.start(), m.end())
for pat in [r"D:\\\\?code", r"D:/code", r"C:\\\\?Users"]:
    for m in re.finditer(pat, t):
        owner = [k for k, (a, b) in mine.items() if a <= m.start() < b]
        print(pat, "->", owner or "其它记录/非本次", "|", repr(t[max(0, m.start()-40):m.start()+50]))
b = mine.get("F-053")
seg = t[b[0]:b[1]] if b else ""
print("F-053 断链哨兵句:", re.findall(r"[^\n]*_conn_generation[^\n]*", seg)[:2])
