import re

path = r"D:\software\Qoder CN\resources\app.asar"
data = open(path, "rb").read()
print("asar 大小 %.1f MB" % (len(data) / 1e6))
needles = [b"AGENTS", b"agents.md", b"QODER.md", b"qoder.md", b"userMemory", b"memoryFile",
           b"instructions", b"rulesFile", b"hook_stdout", b"stdout", b"additionalContext",
           b"hookSpecificOutput", b"systemMessage", b"hook_event_name", b"UserPromptSubmit",
           b"PostToolUseFailure", b"Stop\"", b"transcript_path", b"last_assistant_message"]
for n in needles:
    positions = [m.start() for m in re.finditer(re.escape(n), data)]
    print("%-24s %4d" % (n.decode(errors="ignore"), len(positions)))

# 看 UserPromptSubmit 周边代码，判断 stdout 用途
for m in list(re.finditer(rb"UserPromptSubmit", data))[:3]:
    s = max(0, m.start() - 500)
    chunk = data[s:m.start() + 500]
    text = re.sub(rb"[^\x20-\x7e\u4e00-\u9fff]+", b" ", chunk).decode("utf-8", "ignore")
    print("---- 上下文 ----")
    print(text[:900])
