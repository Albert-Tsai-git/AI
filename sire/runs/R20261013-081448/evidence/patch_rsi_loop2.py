"""收尾 RSI-20261013-RSILOOP：简化 CLIENT_RE，补齐 sire_qoder.py 的入口文件管理。"""
from pathlib import Path

ROOT = Path(r"D:\sire\AI\AI\sire\workflow\shared\sire")
log = []


def patch(rel, pairs):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    for i, (old, new) in enumerate(pairs):
        n = text.count(old)
        if n != 1:
            raise SystemExit("%s 第%d处锚点命中 %d 次：%r" % (rel, i, n, old[:80]))
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    log.append((rel, len(pairs)))


ENTRY_BLOCK = '''ENTRY_FILE = QODER_HOME / "AGENTS.md"
ENTRY_TAG = "<!-- sire-qoder-entry -->"


def entry_text() -> str:
    _, digest = _fastpath_section()
    return (f"{ENTRY_TAG}\\n# Qoder 全局指令（SIRE 薄入口，由 sire_qoder.py 生成）\\n\\n"
            f"所有任务必须执行 SIRE v6 工作流。唯一源与规则正文：`{SHARED_SKILL_DIR}`"
            f"（读 `SKILL.md` 与 `references/global-contract.md`；本文件不复述规则）。\\n\\n"
            f"两条硬性要求：每次回复首行输出 `[SIRE v6] 已使用 SIRE 工作流执行当前任务`；"
            f"动手前先判一次快速通道（规则指纹 {digest}，全文见唯一源）。\\n"
            f"本端遥测钩子由 `sire_qoder.py install` 注册，采集状况用 `sire_qoder.py verify` 复核。{ENTRY_TAG}\\n")


def cmd_entry_file(remove: bool = False) -> int:
    """Qoder 的常驻入口等价物：用户级 AGENTS.md 短指针，靠指纹发现漂移，不复制规则正文。"""
    ours = ENTRY_FILE.is_file() and ENTRY_TAG in ENTRY_FILE.read_text(encoding="utf-8", errors="ignore")
    if remove:
        if ours:
            _backup(ENTRY_FILE)
            ENTRY_FILE.unlink()
            print(f"已移除本工具生成的入口文件：{ENTRY_FILE}")
        else:
            print(f"入口文件非本工具生成或不存在，保持不动：{ENTRY_FILE}")
        return 0
    old = ENTRY_FILE.read_text(encoding="utf-8", errors="ignore") if ENTRY_FILE.is_file() else ""
    body = entry_text()
    if ours:
        head = old.split(ENTRY_TAG, 1)[0].strip()
        merged = (head + "\\n\\n" if head else "") + body
        if merged == old:
            print(f"入口文件已是最新：{ENTRY_FILE}")
            return 0
        _backup(ENTRY_FILE)
        ENTRY_FILE.write_text(merged, encoding="utf-8")
        print(f"入口文件已更新：{ENTRY_FILE}")
        return 0
    _backup(ENTRY_FILE)
    ENTRY_FILE.write_text((old.rstrip() + "\\n\\n" if old.strip() else "") + body, encoding="utf-8")
    print(f"入口文件已生成：{ENTRY_FILE}")
    return 0


'''

patch("scripts/sire_qoder.py", [
    ("def cmd_link(_args=None) -> int:", ENTRY_BLOCK + "def cmd_link(_args=None) -> int:"),
    ("    cmd_link()\n    print(\"生效条件：", "    cmd_link()\n    cmd_entry_file()\n    print(\"生效条件："),
    ('        "alias_points_to_unique_source": SKILL_ALIAS.exists() and SKILL_ALIAS.resolve() == SHARED_SKILL_DIR,',
     '        "alias_points_to_unique_source": SKILL_ALIAS.exists() and SKILL_ALIAS.resolve() == SHARED_SKILL_DIR,\n'
     '        "entry_file": "已生成" if ENTRY_FILE.is_file() and ENTRY_TAG in ENTRY_FILE.read_text('
     'encoding="utf-8", errors="ignore") else "缺失",'),
    ('          f"skills 别名保留：{SKILL_ALIAS}")\n    return 0',
     '          f"skills 别名保留：{SKILL_ALIAS}")\n    cmd_entry_file(remove=True)\n    return 0'),
    ('    for name in ("status", "uninstall", "link", "remind", "selftest"):',
     '    sub.add_parser("entry-file")\n    for name in ("status", "uninstall", "link", "remind", "selftest"):'),
    ('    return {"install": cmd_install, "status": cmd_status, "verify": cmd_verify, "uninstall": cmd_uninstall,',
     '    if args.cmd == "entry-file":\n        return cmd_entry_file()\n'
     '    return {"install": cmd_install, "status": cmd_status, "verify": cmd_verify, "uninstall": cmd_uninstall,'),
])

print("补齐完成：", log)
