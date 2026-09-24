# -*- coding: utf-8 -*-
"""T8：进程内 import sire_supervisor，调用 rsi_gate(skill_dir=argv[1])，输出结果或异常 JSON。"""
import json
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts")
import sire_supervisor  # noqa: E402

target = Path(sys.argv[1])
try:
    result = sire_supervisor.rsi_gate(skill_dir=target)
    print(json.dumps({"skill_dir": str(target), "raised": False, "result": result}, ensure_ascii=False, indent=2))
except Exception as exc:  # 记录异常而不是让脚本崩溃，便于判定
    print(json.dumps({"skill_dir": str(target), "raised": True, "exc": repr(exc), "tb": traceback.format_exc()}, ensure_ascii=False, indent=2))
