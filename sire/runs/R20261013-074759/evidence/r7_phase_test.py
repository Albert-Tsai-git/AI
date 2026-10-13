"""R7：隔离遥测库 + 真实 hook 链路，验证收紧后的阶段归属（不碰生产库）。"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

TMP = Path(os.environ.get("TEMP", "/tmp")) / "sire_phase_r7.sqlite3"
for suffix in ("", "-wal", "-shm"):
    Path(str(TMP) + suffix).unlink(missing_ok=True)
os.environ["SIRE_TELEMETRY_DB"] = str(TMP)
SC = r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts\sire_telemetry.py"
session = "r7-phase"


def hook(payload):
    subprocess.run([sys.executable, SC, "hook", "--client", "codex"],
                   input=json.dumps(payload).encode("utf-8"), env={**os.environ}, capture_output=True)


hook({"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": "阶段归属回归"})
cases = [
    ("Bash", {"command": "python sire_run.py --root D:/x stage-output R5 DONE --artifact a"}),
    ("apply_patch", {"command": "*** Add File: D:/code/x/.sire/runs/R1/ui_fixture.py UI测试夹具"}),
    ("Bash", {"command": "py -3.12 .sire/runs/R1/ui_fixture.py getByRole(button).click()"}),
    ("Read", {"file_path": "D:/sire/AI/AI/sire/knowledge/global/global_dev_efficiency.md"}),
    ("Bash", {"command": "python sire_kb.py reindex"}),
    ("Bash", {"command": "python sire_kb.py search 阶段归属"}),
    ("Bash", {"command": "$env:SIRE_ARCHIVE_ROOT=D:/sire; python sire_rsi.py status"}),
]
for tool, inp in cases:
    hook({"hook_event_name": "PostToolUse", "session_id": session, "tool_name": tool,
          "tool_input": inp, "tool_response": {"stdout": "ok"}})

trans = Path(os.environ.get("TEMP", "/tmp")) / "sire_phase_r7.jsonl"
trans.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
    {"type": "text", "text": "快速通道：否，完整流程"}]}}, ensure_ascii=False) + "\n", encoding="utf-8")
hook({"hook_event_name": "Stop", "session_id": session, "transcript_path": str(trans)})
subprocess.run([sys.executable, SC, "analyze"], env={**os.environ}, capture_output=True)

conn = sqlite3.connect(TMP)
conn.row_factory = sqlite3.Row
phases = json.loads(conn.execute("select phases from tasks").fetchone()[0])
events = [(r["tool"], r["phase"], (r["detail"] or "")[:140])
          for r in conn.execute("select tool,phase,detail from events where event='tool' order by id")]
conn.close()

assertions = {
    "真台账写入记 ledger": any(p == "ledger" and "stage-output" in d for _, p, d in events),
    "UI 夹具不记 ledger": not any(p == "ledger" and ("ui_fixture" in d or "getByRole" in d) for _, p, d in events),
    "读知识库记 retrieve": any(p == "retrieve" and "global_dev_efficiency" in d for _, p, d in events),
    "reindex 记 archive": any(p == "archive" and "reindex" in d for _, p, d in events),
    "台账与归档都仍有秒数（规则未空转）": {"ledger", "archive"} <= set(phases["seconds"]),
}
result = {"逐事件归属": events, "阶段秒数": {k: round(v, 2) for k, v in phases["seconds"].items()},
          "阶段次数": phases["calls"], "断言": assertions,
          "结论": "PASS" if all(assertions.values()) else "FAIL"}
text = json.dumps(result, ensure_ascii=False, indent=1)
Path(__file__).with_name("r7_phase_result.json").write_text(text, encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
print(text)
TMP.unlink(missing_ok=True)
trans.unlink(missing_ok=True)
