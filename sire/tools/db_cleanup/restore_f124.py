# -*- coding: utf-8 -*-
"""把并行会话(mes)用 sire_kb add 写入、被我 md 回写覆盖的 F-124 按其台账原文恢复成卡片。"""
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
SP = sys.argv[1]
src = open(r"D:\sire\sire_ledger\runs\R20261111-101753-mes\knowledge.md", encoding="utf-8").read()
head = {}
for k in ("日期", "项目", "关键词"):
    m = re.search(rf"\*\*{k}\*\*:\s*(.+)", src)
    head[k] = m.group(1).strip() if m else ""
parts = {}
for m in re.finditer(r"\*\*([^*\n]+?)\*\*:\s*(.*?)(?=\n\*\*[^*\n]+?\*\*:|\Z)", src, re.S):
    parts[m.group(1).strip()] = m.group(2).strip()
print("解析到的段落:", list(parts))
g = lambda *ks: "\n".join(parts[k] for k in ks if k in parts) or "原记录未记载"
card = {
    "title": "PostgreSQL 原地改名后重建容器连到另一数据卷：必须核对原卷绑定（Compose volumes.name / MES_POSTGRES_VOLUME）",
    "keywords": head["关键词"], "date": head["日期"], "project": head["项目"],
    "scene": g("需求场景 / 现象"),
    "steps": g("方案 / 架构", "实施步骤"),
    "verify": g("验证方法"),
    "pitfalls": g("根因", "踩坑"),
    "files": g("关键文件与接口"),
    "status": g("状态"),
}
json.dump([{"id": "F-124", "action": "keep", "target": "", "reason": "恢复被 md 回写覆盖的并行会话记录", "card": card}],
          open(SP + "/cards_h.json", "w", encoding="utf-8"), ensure_ascii=False)
print({k: (v[:40] + "…") for k, v in card.items()})
