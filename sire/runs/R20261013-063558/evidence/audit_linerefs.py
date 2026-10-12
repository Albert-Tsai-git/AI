"""审计 F-053~F-059 里所有 `文件:行号` 引用是否真的指向代码。"""
import sys, os, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = r"D:\code\driverSoftware2"
KB = r"D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md"
t = open(KB, encoding="utf-8").read()
blocks = dict(re.findall(r"^### (F-\d{3}): [^\n]*\n(.*?)(?=^### |\Z)", t, re.M | re.S))

# 收集仓内所有文件的相对路径索引（按 basename 建表，用于裸文件名引用）
index = {}
for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in {".git", "venv", "node_modules", "__pycache__", "dist", "dist_app", "build", ".sire", "logs"}]
    for f in files:
        if os.path.splitext(f)[1].lower() in {".py", ".js", ".md", ".json", ".bat", ".sh", ".ps1", ".yml", ".txt", ".nsh", ".html", ".css"}:
            index.setdefault(f.lower(), []).append(os.path.relpath(os.path.join(root, f), REPO).replace("\\", "/"))

REF = re.compile(r"[A-Za-z0-9_.\-/]*(?:[A-Za-z0-9_.\-]+/)*[A-Za-z0-9_.\-]+\.(?:py|js|md|json|bat|sh|ps1|yml|txt|nsh|html|css):(\d+)")
SHORT = re.compile(r"(?<![\w/.-])([A-Za-z0-9_\-]+\.(?:py|js|md|json|bat|sh|ps1|yml|nsh|css|html)):(\d+)")

report = {}
for rid in sorted(blocks):
    body = blocks[rid]
    refs = []
    for m in set(REF.findall("") or []):
        pass
    for m in set(re.findall(r"((?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-]+\.(?:py|js|md|json|bat|sh|ps1|yml|nsh|css|html)):(\d+)", body)):
        refs.append(m)
    for m in set(re.findall(r"`([A-Za-z0-9_.\-]+\.(?:py|js|md|json|bat|sh|ps1|yml|nsh|css|html))`?\s*:?(?:（)?(\d+)", body)):
        refs.append(m)
    for m in set(SHORT.findall(body)):
        refs.append(m)
    bad, ok, unknown = [], 0, []
    seen = set()
    for path, ln in refs:
        path = path.strip("/").replace("\\", "/")
        ln = int(ln)
        if (path, ln) in seen:
            continue
        seen.add((path, ln))
        cands = []
        direct = os.path.join(REPO, path)
        if os.path.isfile(direct):
            cands.append(path)
        cands += index.get(os.path.basename(path).lower(), [])
        if not cands:
            unknown.append(f"{path}:{ln}")
            continue
        rel = cands[0]
        src = open(os.path.join(REPO, rel), encoding="utf-8", errors="replace").read().splitlines()
        if ln > len(src):
            bad.append(f"{path}:{ln} 越界(文件 {len(src)} 行, 实际 {rel})")
        elif not src[ln - 1].strip():
            bad.append(f"{path}:{ln} 指向空行 ({rel})")
        else:
            ok += 1
    report[rid] = (ok, bad, unknown, len(seen))
    print(f"{rid}: 引用 {len(seen)} 处, 可定位且行非空 {ok}, 可疑 {len(bad)}, 找不到文件 {len(unknown)}")
    for x in bad[:14]:
        print("   可疑:", x)
    for x in unknown[:10]:
        print("   未解析:", x)
