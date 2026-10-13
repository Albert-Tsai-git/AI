"""RSI-20261013-RSILOOP 落地补丁：三个文件的确定性修改，任一锚点不唯一即中止。"""
from pathlib import Path

ROOT = Path(r"D:\sire\AI\AI\sire\workflow\shared\sire")
log = []


def patch(rel, pairs):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    for i, (old, new) in enumerate(pairs):
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{rel} 第{i}处锚点命中 {n} 次：{old[:70]!r}")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    log.append((rel, len(pairs)))


# ---------------------------------------------------------------- 1. 遥测：采集存活自检
TELE_NEW = '''DECAY_SECONDS = 7 * 86400
# 已配置钩子的客户端应当持续有心跳；长时间无事件本身就是机制故障
CLIENT_CONFIGS = (
    Path.home() / ".codex" / "hooks.json",
    Path.home() / ".claude" / "settings.json",
    Path.home() / ".claude" / "settings.local.json",
    Path(os.environ.get("QODER_HOME") or Path.home() / ".qoder-cn") / "settings.json",
)
CLIENT_RE = re.compile(r"--client[=\\s"\\'\\"]*([a-z]+)", re.I)
CLIENT_DEDUPE_SECONDS = 1800


def expected_clients() -> set[str]:
    out: set[str] = set()
    for path in CLIENT_CONFIGS:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        out.update(m.group(1).lower() for m in CLIENT_RE.finditer(text))
    return out


def check_clients(c: sqlite3.Connection, now: float, stale_seconds: float) -> None:
    """只对"曾经采过、现在哑了"的客户端报警；全新安装还没有心跳由 sire_qoder.py verify 负责。"""
    for client in sorted(expected_clients()):
        last = c.execute("SELECT max(ts) FROM events WHERE client=?", (client,)).fetchone()[0]
        if last is None or now - last <= stale_seconds:
            continue
        fid = f"COLLECTION_DEAD:{client}"
        item = {"client": client, "at": round(now), "evidence": f"末次事件距今 {(now - last) / 60:.0f} 分钟"}
        row = c.execute("SELECT * FROM findings WHERE finding_id=?", (fid,)).fetchone()
        if row is not None and now - (row["last_seen"] or 0) < CLIENT_DEDUPE_SECONDS:
            continue  # 半小时内已计过，避免每次 analyze 刷命中
        if row is None:
            c.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (fid, "COLLECTION_DEAD", "PROPOSED", 1, now, now,
                       json.dumps([item], ensure_ascii=False), RULES["COLLECTION_DEAD"][1], None, None, None))
            continue
        status = row["status"] if row["status"] in ("PROPOSED", "REGRESSED") else "PROPOSED"
        evidence = (json.loads(row["evidence"] or "[]") + [item])[-10:]
        c.execute("UPDATE findings SET status=?,hits=?,last_seen=?,evidence=? WHERE finding_id=?",
                  (status, (row["hits"] or 0) + 1, now, json.dumps(evidence, ensure_ascii=False), fid))
'''
patch("scripts/sire_telemetry.py", [
    ('    "PHASE_OUTLIER": (2, "某阶段耗时超过历史中位数 3 倍：检查该阶段的脚本或规则是否有新增的低效步骤"),\n}',
     '    "PHASE_OUTLIER": (2, "某阶段耗时超过历史中位数 3 倍：检查该阶段的脚本或规则是否有新增的低效步骤"),\n'
     '    "COLLECTION_DEAD": (1, "客户端配了钩子却长时间无事件：核对该客户端配置是否仍指向 sire_telemetry.py hook，'
     '修好后 resolve；这属于采集面故障，不要靠删规则消音"),\n}\n' + TELE_NEW),
    ("def cmd_analyze(_args) -> int:", "def cmd_analyze(args) -> int:"),
    ("        cutoff = now - RETENTION_DAYS * 86400",
     "        check_clients(c, now, args.stale_hours * 3600)\n"
     "        cutoff = now - RETENTION_DAYS * 86400"),
    ('    sub.add_parser("analyze")',
     '    a = sub.add_parser("analyze")\n'
     '    a.add_argument("--stale-hours", type=float, default=12.0, help="客户端无事件多少小时后判定采集断流")'),
])

# ---------------------------------------------------------------- 2. 台账：收尾强制查 pending
RUN_NEW = '''def telemetry_pending_gate(rd: str, note: str) -> str | None:
    """R9 的自动优化步骤不能只靠自觉：有待处理发现就必须先处理或显式移交。"""
    script = str(SHARED_SKILL_DIR / "scripts" / "sire_telemetry.py")
    result = subprocess.run([sys.executable, script, "pending", "--json"], text=True, capture_output=True,
                            encoding="utf-8", errors="replace")
    try:
        findings = json.loads(result.stdout or "[]")
    except ValueError:
        findings = []
    open_items = [f.get("finding") for f in findings if isinstance(f, dict) and f.get("finding")]
    check = {"checked_at": now(), "pending": open_items, "handoff_note": note or None,
             "verdict": "PASS" if not open_items else ("HANDED_OFF" if note else "BLOCKED")}
    save_json(os.path.join(rd, "pending-check.json"), check)
    log(rd, "PENDING %s: %s" % (check["verdict"], ",".join(open_items) or "无"))
    if not open_items:
        return None
    if note:
        return None
    first = open_items[0]
    return ("自动优化未闭环：遥测里有 %d 条待处理发现（第一条 %s）。"
            "按 global-contract.md § RSI 处理完再收尾，或确实需要用户决定时用 --pending-note \"原因\" 显式移交"
            % (len(open_items), first))


'''
patch("scripts/sire_run.py", [
    ("def cmd_finish(args):", RUN_NEW + "def cmd_finish(args):"),
    ("    run[\"kb_records\"] = records",
     "    pending_error = telemetry_pending_gate(rd, getattr(args, \"pending_note\", \"\"))\n"
     "    if pending_error:\n        return fail(pending_error)\n"
     "    run[\"kb_records\"] = records"),
    ('    s.add_argument("--note", default="")\n\n    args = p.parse_args()',
     '    s.add_argument("--note", default="")\n'
     '    s.add_argument("--pending-note", dest="pending_note", default="",\n'
     '                   help="待处理发现确实需要用户决定时，记录移交理由")\n\n    args = p.parse_args()'),
])

# ---------------------------------------------------------------- 3. Qoder：用户级薄入口
QODER_NEW = '''ENTRY_FILE = QODER_HOME / "AGENTS.md"
ENTRY_MARK2 = "<!-- sire-qoder-entry -->"


def entry_text() -> str:
    _, digest = _fastpath_section()
    return (f"{ENTRY_MARK2}\\n# Qoder 全局指令（SIRE 薄入口，由 sire_qoder.py 生成）\\n\\n"
            f"所有任务必须执行 SIRE v6 工作流。唯一源与规则正文：`{SHARED_SKILL_DIR}`"
            f"（读 `SKILL.md` 与 `references/global-contract.md`，本文件不复述规则）。\\n\\n"
            f"两条硬性要求：每次回复首行输出 `[SIRE v6] 已使用 SIRE 工作流执行当前任务`；"
            f"动手前先判一次快速通道（快速通道规则指纹 {digest}，全文见唯一源）。\\n"
            f"本端遥测钩子由 `sire_qoder.py install` 注册，采集状况用 `sire_qoder.py verify` 复核。{ENTRY_MARK2}\\n")


def cmd_entry_file(remove: bool = False) -> int:
    """Qoder 的常驻入口等价物：用户级 AGENTS.md 短指针（不复制规则，靠指纹发现漂移）。"""
    if remove:
        if ENTRY_FILE.is_file() and ENTRY_MARK2 in ENTRY_FILE.read_text(encoding="utf-8", errors="ignore"):
            _backup(ENTRY_FILE)
            ENTRY_FILE.unlink()
            print(f"已移除本工具生成的入口文件：{ENTRY_FILE}")
        else:
            print(f"入口文件不是本工具生成的或不存在，保持不动：{ENTRY_FILE}")
        return 0
    old = ENTRY_FILE.read_text(encoding="utf-8", errors="ignore") if ENTRY_FILE.is_file() else ""
    body = entry_text()
    if ENTRY_MARK2 in old:
        head = old.split(ENTRY_MARK2, 1)[0].strip()
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
    ("def cmd_link(_args=None) -> int:", QODER_NEW + "def cmd_link(_args=None) -> int:"),
    ("    cmd_link()\n    print(\"生效条件：", "    cmd_link()\n    cmd_entry_file()\n    print(\"生效条件："),
    ('    print(f"已移除 SIRE 条目 {removed} 个（其它客户端配置未动）；插件登记 {\'已删\' if had else \'无\'}；"\n'
     '          f"skills 别名保留：{SKILL_ALIAS}")\n    return 0',
     '    print(f"已移除 SIRE 条目 {removed} 个（其它客户端配置未动）；插件登记 {\'已删\' if had else \'无\'}；"\n'
     '          f"skills 别名保留：{SKILL_ALIAS}")\n    cmd_entry_file(remove=True)\n    return 0'),
    ('           "plugin_registered": "sire@local" in (_read_json(PLUGIN_REGISTRY, {}).get("plugins") or {}),',
     '           "entry_file": str(ENTRY_FILE) if ENTRY_FILE.is_file() and ENTRY_MARK2 in ENTRY_FILE.read_text('
     'encoding="utf-8", errors="ignore") else "缺失",\n'
     '           "plugin_registered": "sire@local" in (_read_json(PLUGIN_REGISTRY, {}).get("plugins") or {}),'),
    ('    for name in ("status", "uninstall", "link", "remind", "selftest"):\n        sub.add_parser(name)',
     '    sub.add_parser("entry-file")\n    for name in ("status", "uninstall", "link", "remind", "selftest"):\n'
     '        sub.add_parser(name)'),
    ('    return {"install": cmd_install, "status": cmd_status, "verify": cmd_verify, "uninstall": cmd_uninstall,\n'
     '            "link": cmd_link, "remind": cmd_remind, "selftest": cmd_selftest}[args.cmd](args)',
     '    if args.cmd == "entry-file":\n        return cmd_entry_file()\n'
     '    return {"install": cmd_install, "status": cmd_status, "verify": cmd_verify, "uninstall": cmd_uninstall,\n'
     '            "link": cmd_link, "remind": cmd_remind, "selftest": cmd_selftest}[args.cmd](args)'),
])

print("补丁已应用：")
for item in log:
    print("  ", item)
