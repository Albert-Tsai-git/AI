import os

root = r"D:\software\Qoder CN"
needles = [b"AGENTS.md", b"QODER.md", b"additionalContext", b"hookSpecificOutput",
           b"UserPromptSubmit", b"PostToolUseFailure", b".qoder-cn", b"qodercli"]
hits = {n.decode(): [] for n in needles}
skip = [os.path.sep + "locales", "node_modules", "extensions"]
scanned = 0
for dp, _, fns in os.walk(root):
    low = dp.lower()
    if any(s in low for s in skip):
        continue
    for fn in fns:
        p = os.path.join(dp, fn)
        try:
            sz = os.path.getsize(p)
        except OSError:
            continue
        if sz > 700 * 1024 * 1024:
            continue
        try:
            b = open(p, "rb").read()
        except Exception:
            continue
        scanned += 1
        for n in needles:
            if n in b and len(hits[n.decode()]) < 2:
                hits[n.decode()].append(os.path.relpath(p, root) + " (%dKB)" % (sz // 1024))
print("扫描文件数", scanned)
for k, v in hits.items():
    print("%-20s %s" % (k, v[0] if v else "-"))
