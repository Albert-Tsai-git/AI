#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SIRE v6 交付台账 CLI —— 门禁、单元状态机、证据校验、跨会话续跑。

台账即事实：未落盘的结论一律不算数。

用法:
  sire_run.py init --title "需求标题" [--channel full|light] [--project 名称]
  sire_run.py gate G0 --pass [--note "..."]
  sire_run.py add-units --file units.json
  sire_run.py approve-units --mode user-confirmed|autonomous --note "..."
  sire_run.py show-units
  sire_run.py set U-01 IN_PROGRESS --role R5|R10 [--note "..."]
  sire_run.py review U-01 PASS|FAIL --role R6A|R6B|R6C --note "..."
  sire_run.py review U-01 PASS|FAIL --role R6A|R6B|R6C --cross-check --note "..."
  sire_run.py review U-01 PASS --finalize --note "..."
  sire_run.py test U-01 PASS|FAIL|BLOCKED --note "..."
  sire_run.py board
  sire_run.py stage-output R0|R1|...|R10 DONE|SKIPPED|BLOCKED --artifact "..." [--reason "..."]
  sire_run.py blockers
  sire_run.py resume
  sire_run.py finish --records F-012,P-009
"""
import argparse
import hashlib
import json
import os
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path

from sire_paths import KNOWLEDGE_DIR, SHARED_SKILL_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATES = ["PENDING", "READY", "IN_PROGRESS", "AWAITING", "REVIEW", "TEST", "REWORK",
          "DONE", "BLOCKED", "DEFERRED"]
TERMINAL = ("DONE", "BLOCKED", "DEFERRED")
ALLOWED = {
    "PENDING": ("READY", "BLOCKED", "DEFERRED"),
    "READY": ("IN_PROGRESS", "BLOCKED", "DEFERRED"),
    "IN_PROGRESS": ("REVIEW", "AWAITING", "BLOCKED"),
    "AWAITING": ("IN_PROGRESS", "BLOCKED", "DEFERRED"),
    "REVIEW": ("TEST", "REWORK", "BLOCKED"),
    "TEST": ("DONE", "REWORK", "BLOCKED"),
    "REWORK": ("IN_PROGRESS", "BLOCKED"),
    "DONE": ("REWORK",),
    "BLOCKED": ("READY", "DEFERRED"),
    "DEFERRED": ("READY",),
}
GATES = ["G0", "G1", "G3", "G5", "G6"]
REWORK_LIMIT = 2
REVIEW_ROLES = ("R6A", "R6B", "R6C")
EXECUTOR_ROLES = ("R5", "R10")
STAGE_KEYS = tuple("R%d" % index for index in range(11)) + ("G6",)
REQUIRED_STAGE_OUTPUTS = tuple("R%d" % index for index in range(11))
STAGE_STATUSES = ("DONE", "SKIPPED", "BLOCKED")
REVIEW_EVIDENCE = {
    "R6A": "r6a.md",
    "R6B": "r6b.md",
    "R6C": "r6c.md",
}
CROSS_REVIEW_EVIDENCE = {
    "R6A": "r6a-cross.md",
    "R6B": "r6b-cross.md",
    "R6C": "r6c-cross.md",
}

# 不可测措辞：验收条件里出现即拒绝登记。黑名单挡不住所有同义词，
# 真正的把关在 R4 拆解复核门，这里只拦最常见的糊弄写法。
UNTESTABLE = ("优化", "完善", "提升", "更好", "更快", "增强", "改善", "友好", "健壮",
              "顺畅", "流畅", "稳定", "优雅", "美观", "合理", "清晰", "高效", "体验好")
# 无效验证方式：测试官无法照做
WEAK_VERIFY = ("人工", "看一下", "看看", "手动确认", "自行检查", "目测", "肉眼", "观察一下",
              "待定", "tbd", "自行验证", "检查是否正常")


LONG_PATH_PREFIX = "\\\\?\\"


def lp(path):
    """Windows 长路径兜底：超过 240 字符时加扩展前缀。

    深目录（例如带 UUID 的工作区）下 260 字符上限会让 makedirs 直接报错。
    """
    if os.name != "nt" or not path:
        return path
    ap = os.path.abspath(path)
    if len(ap) < 240 or ap.startswith(LONG_PATH_PREFIX):
        return ap
    return LONG_PATH_PREFIX + ap


def mkdirs(path):
    os.makedirs(lp(path), exist_ok=True)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fail(msg, code=1):
    print("BLOCKED-台账拒绝: %s" % msg)
    return code


def sire_dir(root):
    return os.path.join(root, ".sire")


def run_dir(root, run_id):
    return os.path.join(sire_dir(root), "runs", run_id)


def current_run(root):
    marker = os.path.join(sire_dir(root), "current")
    if not os.path.exists(lp(marker)):
        return None
    with open(lp(marker), "r", encoding="utf-8") as fh:
        rid = fh.read().strip()
    return rid or None


def load_json(path, default=None):
    if not os.path.exists(lp(path)):
        return default
    try:
        with open(lp(path), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    mkdirs(os.path.dirname(path))
    with open(lp(path), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def ctx(args, need=True):
    root = os.path.abspath(args.root or os.getcwd())
    rid = getattr(args, "run", None) or current_run(root)
    if not rid:
        if need:
            raise SystemExit(fail("当前目录没有活动 run，先执行 sire_run.py init"))
        return root, None, None, None
    rd = run_dir(root, rid)
    run = load_json(os.path.join(rd, "run.json"))
    if run is None and need:
        raise SystemExit(fail("run.json 缺失: %s" % rd))
    units = load_json(os.path.join(rd, "units.json"), [])
    for unit in units or []:
        ensure_review_fields(unit)
    return root, rid, rd, (run, units)


def ensure_review_fields(unit):
    """为新旧台账统一补齐三路复核字段。"""
    if not isinstance(unit.get("review_roles"), dict):
        unit["review_roles"] = {}
    if not isinstance(unit.get("cross_checks"), dict):
        unit["cross_checks"] = {}
    for role in REVIEW_ROLES:
        unit["review_roles"].setdefault(role, "")
        unit["cross_checks"].setdefault(role, "")
    unit.setdefault("review", "")


def review_evidence_exists(rd, uid, filename):
    """复核证据必须是 review 目录下的非空文件。"""
    p = lp(os.path.join(rd, "evidence", uid, "review", filename))
    return os.path.isfile(p) and os.path.getsize(p) >= 20


def missing_review_evidence(rd, uid, filenames):
    return [name for name in filenames if not review_evidence_exists(rd, uid, name)]


def log(rd, line):
    with open(lp(os.path.join(rd, "journal.log")), "a", encoding="utf-8") as fh:
        fh.write("[%s] %s\n" % (now(), line))


def cmd_init(args):
    root = os.path.abspath(args.root or os.getcwd())
    rid = datetime.now().strftime("R%Y%m%d-%H%M%S")
    rd = run_dir(root, rid)
    mkdirs(os.path.join(rd, "evidence"))
    run = {
        "run_id": rid,
        "title": args.title,
        "project": args.project or os.path.basename(root),
        "channel": args.channel,
        "created": now(),
        "state": "OPEN",
        "gates": {},
        "execution_approval": {"status": "NOT_REQUESTED", "mode": "", "at": "", "note": ""},
        "stage_outputs": {},
        "workflow_baseline": workflow_fingerprint(),
        "migration_baseline": file_fingerprint(migration_doc_path()),
        "kb_records": [],
        "kb_baseline": sorted(kb_record_ids()),
    }
    save_json(os.path.join(rd, "run.json"), run)
    save_json(os.path.join(rd, "units.json"), [])
    mkdirs(sire_dir(root))
    with open(lp(os.path.join(sire_dir(root), "current")), "w", encoding="utf-8") as fh:
        fh.write(rid)
    for name in ("assumptions.md", "blockers.md"):
        p = os.path.join(rd, name)
        if not os.path.exists(lp(p)):
            with open(lp(p), "w", encoding="utf-8") as fh:
                fh.write("# %s\n\n" % name.replace(".md", ""))
    log(rd, "INIT %s | %s | channel=%s" % (rid, args.title, args.channel))
    print("RUN_ID=%s" % rid)
    print("台账目录: %s" % rd)
    print("下一步: G0 知识检索 —— 生成 kb-hits.md 后执行 gate G0 --pass")
    return 0


def kb_hits_path(rd):
    return os.path.join(rd, "kb-hits.md")


def default_kb_dir():
    """唯一共享知识目录；两端门禁都以同一份受跟踪知识为准。"""
    return str(KNOWLEDGE_DIR)


def migration_doc_path():
    return os.path.join(default_kb_dir(), "SIRE-MIGRATION.md")


def file_fingerprint(path):
    if not os.path.isfile(lp(path)):
        return None
    digest = hashlib.sha256()
    with open(lp(path), "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    stat = os.stat(lp(path))
    return {"sha256": digest.hexdigest(), "mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def workflow_control_paths():
    home = os.path.expanduser("~")
    return [
        str(SHARED_SKILL_DIR),
        os.path.join(str(SHARED_SKILL_DIR.parents[1]), "support", "ai-workflow-governor"),
        os.path.join(home, ".claude", "agents"),
        os.path.join(home, ".claude", "CLAUDE.md"),
        os.path.join(home, ".claude", "sire-reminder.txt"),
        os.path.join(default_kb_dir(), "sire_ai_rules.md"),
        os.path.join(default_kb_dir(), "sire_multi_role_workflow.md"),
    ]


def workflow_file_allowed(path):
    parts = set(os.path.normcase(path).replace("/", "\\").split(os.sep))
    if parts & {"__pycache__", ".git", "node_modules"}:
        return False
    return not path.lower().endswith(".pyc")


def workflow_fingerprint():
    result = {}
    for root in workflow_control_paths():
        if os.path.isfile(lp(root)):
            if workflow_file_allowed(root):
                result[os.path.abspath(root)] = file_fingerprint(root)
            continue
        if not os.path.isdir(lp(root)):
            continue
        for current, dirs, files in os.walk(lp(root)):
            dirs[:] = [name for name in dirs if name not in ("__pycache__", ".git", "node_modules")]
            for name in files:
                path = os.path.join(current, name)
                if workflow_file_allowed(path):
                    result[os.path.abspath(path)] = file_fingerprint(path)
    return result


def workflow_changes_since(run):
    baseline = run.get("workflow_baseline")
    if not isinstance(baseline, dict):
        return []
    current = workflow_fingerprint()
    changed = []
    for path in sorted(set(baseline) | set(current)):
        if baseline.get(path) != current.get(path):
            changed.append((path, baseline.get(path), current.get(path)))
    return changed


def migration_sync_error(run):
    changed = workflow_changes_since(run)
    if not changed:
        return None
    current = file_fingerprint(migration_doc_path())
    baseline = run.get("migration_baseline")
    if not current:
        return "工作流内容已变更，但 SIRE-MIGRATION.md 不存在"
    if current == baseline or (baseline and current.get("sha256") == baseline.get("sha256")):
        return "工作流内容已变更，但 SIRE-MIGRATION.md 未同步更新"
    latest_change = 0
    for _path, before, after in changed:
        record = after or before or {}
        latest_change = max(latest_change, int(record.get("mtime_ns", 0)))
    if int(current.get("mtime_ns", 0)) < latest_change:
        return "SIRE-MIGRATION.md 更新时间早于工作流变更，迁移文档可能未同步"
    return None


def kb_records():
    idx = load_json(os.path.join(default_kb_dir(), "global_index.json"), {})
    return idx.get("records", [])


def kb_record_ids():
    return set(r["id"] for r in kb_records())


def search_receipts(rd):
    """读取 sire_kb.py search 写下的检索回执，证明检索真的执行过。"""
    p = os.path.join(rd, "kb-search.log")
    if not os.path.exists(lp(p)):
        return []
    out = []
    with open(lp(p), "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def cmd_gate(args):
    _root, _rid, rd, data = ctx(args)
    run, _units = data
    gate = args.gate.strip().upper()
    if gate not in GATES:
        return fail("门禁编号必须是 %s" % "/".join(GATES))
    verdict = "PASS" if args.pass_ else "FAIL"
    if gate == "G0" and verdict == "PASS":
        p = kb_hits_path(rd)
        if not os.path.exists(lp(p)):
            return fail("G0 未生成 kb-hits.md，知识检索是强制门禁，不得跳过")
        with open(lp(p), "r", encoding="utf-8") as fh:
            text = fh.read()
        missing = [k for k in ("检索词", "命中", "判定") if k not in text]
        if missing:
            return fail("kb-hits.md 缺少字段: %s（三项必备：检索词/命中/判定）" % "、".join(missing))
        verdicts = ("已实现过", "部分可参考", "全新需求")
        if not any(v in text for v in verdicts):
            return fail("kb-hits.md 判定值必须是 %s 三选一" % " / ".join(verdicts))
        # 检索回执：证明 sire_kb.py search 真的跑过，堵死手写 kb-hits 蒙混过关
        receipts = search_receipts(rd)
        if not receipts:
            return fail("没有检索回执。必须执行 sire_kb.py search --run \"%s\" \"关键词\"，"
                        "手写 kb-hits.md 不算检索" % rd)
        real_dir = os.path.normcase(os.path.abspath(default_kb_dir()))
        created = run.get("created", "")
        valid, seen_terms = [], []
        for r in receipts:
            if r.get("run_id") != run["run_id"]:
                continue  # 别的 run 的回执，不算数
            if created and r.get("ts", "") < created:
                continue  # 早于本 run 创建，是复制来的旧回执
            if os.path.normcase(os.path.abspath(r.get("kb_dir", ""))) != real_dir:
                return fail("检索用的不是真实知识库（%s）。必须检索 %s，"
                            "不要用 SIRE_KB_DIR 指向别处" % (r.get("kb_dir"), default_kb_dir()))
            terms = frozenset(t.lower() for t in r.get("terms", []))
            if terms and terms not in seen_terms:
                seen_terms.append(terms)
                valid.append(r)
        if not valid:
            return fail("没有属于本 run 的有效检索回执。回执必须由本 run 期间的 "
                        "sire_kb.py search --run \"%s\" 产生，复制别处的不算" % rd)
        if len(seen_terms) < 2:
            return fail("只有 %d 组不同的检索词。规范要求换一组同义词再搜一次，"
                        "重复同一组词不算第二次检索" % len(seen_terms))
        vector_receipt = os.path.join(rd, "vector-search.log")
        if not os.path.exists(lp(vector_receipt)):
            return fail("没有向量检索回执。必须执行 sire_vector_db.py search --run \"%s\"" % rd)
        if len(kb_record_ids()) == 0:
            print("WARN 真实知识库为空，本次检索无从命中")
    run["gates"][gate] = {"verdict": verdict, "at": now(), "note": args.note or ""}
    save_json(os.path.join(rd, "run.json"), run)
    log(rd, "GATE %s=%s %s" % (gate, verdict, args.note or ""))
    print("%s=%s 已记录" % (gate, verdict))
    return 0


def cmd_add_units(args):
    _root, _rid, rd, data = ctx(args)
    run, units = data
    if run["gates"].get("G0", {}).get("verdict") != "PASS":
        return fail("G0 知识检索门未通过，禁止创建单元。先检索知识库并生成 kb-hits.md")
    if not os.path.exists(kb_hits_path(rd)):
        return fail("kb-hits.md 不存在，知识检索是强制前置")
    if run["gates"].get("G1", {}).get("verdict") != "PASS":
        return fail("G1 需求分析门未通过，禁止创建单元。先派 sire-analyst 产出需求项")
    if run["gates"].get("G3", {}).get("verdict") != "PASS":
        return fail("G3 拆解复核门未通过，禁止创建单元。"
                    "必须先派 sire-spec-reviewer 复核单元计划并记录 gate G3 --pass")
    active = [u["id"] for u in units
              if u["state"] not in ("PENDING", "READY") and u["state"] not in TERMINAL]
    if active:
        return fail("已有执行中或复核中的单元，不能在执行过程中重建任务列表: %s"
                    % ", ".join(active))
    payload = load_json(args.file)
    if payload is None:
        return fail("无法读取单元文件: %s" % args.file)
    if isinstance(payload, dict):
        payload = payload.get("units", [])
    required = ("id", "title", "accept", "files", "verify")
    ids = set(u["id"] for u in units)
    added = []
    for u in payload:
        miss = [k for k in required if not u.get(k)]
        if miss:
            return fail("单元 %s 缺字段: %s（id/title/accept/files/verify 全部是硬要求）"
                        % (u.get("id", "?"), "、".join(miss)))
        if u["id"] in ids:
            return fail("单元编号重复: %s" % u["id"])
        acc = str(u["accept"])
        bad = [w for w in UNTESTABLE if w in acc]
        if bad:
            return fail("单元 %s 验收条件含不可测措辞: %s。改写成「当X时应Y」的可判定形式"
                        % (u["id"], "、".join(bad)))
        if ("应" not in acc) and ("should" not in acc.lower()):
            return fail("单元 %s 验收条件不是「当X时应Y」形式: %s" % (u["id"], acc))
        ver = str(u["verify"])
        weak = [w for w in WEAK_VERIFY if w in ver.lower()]
        if weak:
            return fail("单元 %s 验证方式无效: %s。必须给出测试命令或可观察行为，"
                        "测试官不能靠人工目测" % (u["id"], "、".join(weak)))
        owner = str(u.get("owner", "R5")).strip().upper()
        if owner not in EXECUTOR_ROLES:
            return fail("单元 %s 执行负责人只能是 R5 或 R10，收到: %s" %
                        (u["id"], u.get("owner")))
        rec = {
            "id": u["id"], "title": u["title"], "maps": u.get("maps", ""),
            "owner": owner,
            "accept": u["accept"], "files": u["files"], "verify": u["verify"],
            "deps": u.get("deps", []), "est": u.get("est", ""),
            "wave": u.get("wave", 1), "priority": u.get("priority", "P1"),
            "risk": u.get("risk", ""), "stop": u.get("stop", ""),
            "state": "PENDING", "rework": 0, "review": "",
            "review_roles": {role: "" for role in REVIEW_ROLES},
            "cross_checks": {role: "" for role in REVIEW_ROLES},
            "test": "",
            "note": "", "updated": now(),
        }
        units.append(rec)
        ids.add(rec["id"])
        added.append(rec["id"])
    known = set(u["id"] for u in units)
    for u in units:
        for d in u["deps"]:
            if d not in known:
                return fail("单元 %s 依赖了计划外的 %s，依赖必须闭环" % (u["id"], d))
            if d == u["id"]:
                return fail("单元 %s 依赖了自己，DAG 必须无环" % u["id"])
    cyc = find_cycle(units)
    if cyc:
        return fail("依赖成环: %s。DAG 必须无环，否则单元会永久停在 PENDING" % " -> ".join(cyc))
    clash = file_clash(units)
    if clash:
        uid_a, uid_b, wave, shared = clash
        return fail("同波次文件冲突: W%s 的 %s 与 %s 都要改 %s。"
                    "并行会互相覆盖，请拆到不同波次或合并为一个单元"
                    % (wave, uid_a, uid_b, "、".join(sorted(shared))))
    # 新增或重新生成任务列表后，必须重新经过用户确认；不能因为 G3 通过就自动开工。
    for u in units:
        if u["state"] == "READY":
            u["state"] = "PENDING"
    run["execution_approval"] = {
        "status": "PENDING",
        "mode": "",
        "at": now(),
        "note": "等待用户确认最小可执行任务列表；用户明确授权自行完成时可用 autonomous",
    }
    save_json(os.path.join(rd, "units.json"), units)
    save_json(os.path.join(rd, "run.json"), run)
    log(rd, "ADD-UNITS %s" % ",".join(added))
    print("已登记 %d 个单元: %s" % (len(added), ", ".join(added)))
    print_unit_plan(run, units)
    return 0


def approval_granted(run):
    return run.get("execution_approval", {}).get("status") == "APPROVED"


def approval_granted_for(rd):
    run = load_json(os.path.join(rd, "run.json"), {}) or {}
    return approval_granted(run)


def print_unit_plan(run, units):
    """输出可供用户确认的完整最小可执行单元清单。"""
    approval = run.get("execution_approval", {})
    print("执行确认=%s%s" %
          (approval.get("status", "NOT_REQUESTED"),
           (" (" + approval.get("mode", "") + ")") if approval.get("mode") else ""))
    print("最小可执行任务列表（非终结单元）:")
    shown = 0
    for u in units:
        if u["state"] in TERMINAL:
            continue
        shown += 1
        deps = u.get("deps", []) or []
        files = u["files"] if isinstance(u["files"], list) else [u["files"]]
        print("- %s | %s | state=%s | owner=%s | maps=%s | deps=%s | wave=W%s | est=%s" %
              (u["id"], u["title"], u["state"], u.get("owner", "R5"),
               u.get("maps", "未标注") or "未标注", ",".join(deps) or "无",
               u.get("wave", 1), u.get("est", "未标注") or "未标注"))
        print("  验收: %s" % u["accept"])
        print("  写集: %s" % ", ".join(str(item) for item in files))
        print("  验证: %s" % u["verify"])
        print("  风险: %s | 停止条件: %s" %
              (u.get("risk", "未标注") or "未标注", u.get("stop", "未标注") or "未标注"))
    if not shown:
        print("- 无待执行单元")
    if approval.get("status") == "PENDING":
        print("下一步：用户确认后执行 approve-units；若用户明确说不需确认/自行完成，使用 --mode autonomous 并记录原话")


def cmd_show_units(args):
    _root, _rid, _rd, data = ctx(args)
    run, units = data
    if not units:
        print("尚未生成最小可执行单元")
        return 0
    print_unit_plan(run, units)
    return 0


def emit_stage_output(stage, record):
    status = record.get("status", "DONE")
    label = {"DONE": "完成", "SKIPPED": "跳过", "BLOCKED": "阻塞"}.get(status, status)
    print("%s：%s" % (stage, label))
    if status in ("SKIPPED", "BLOCKED"):
        print("原因：%s" % (record.get("reason") or "未说明"))
    print("产物：")
    for index, artifact in enumerate(record.get("artifacts") or ["无"], 1):
        print("%d. %s" % (index, artifact))
    if status != "SKIPPED":
        print("隐患/阻塞：%s" % (record.get("risk") or "无"))


def cmd_stage_output(args):
    _root, _rid, rd, data = ctx(args)
    run, _units = data
    stage = args.stage.strip().upper()
    status = args.status.strip().upper()
    if stage not in STAGE_KEYS:
        return fail("阶段必须是 %s" % "/".join(STAGE_KEYS))
    if status not in STAGE_STATUSES:
        return fail("阶段状态必须是 DONE / SKIPPED / BLOCKED")
    artifacts = [item.strip() for item in (args.artifact or []) if item.strip()]
    reason = (args.reason or "").strip()
    if status == "SKIPPED":
        if not reason:
            return fail("跳过阶段必须说明原因")
        artifacts = artifacts or ["跳过记录"]
    elif not artifacts:
        return fail("完成或阻塞阶段必须至少提供一个产物")
    if status == "BLOCKED" and not reason:
        return fail("阻塞阶段必须说明原因")
    record = {
        "stage": stage,
        "status": status,
        "artifacts": artifacts,
        "reason": reason,
        "risk": (args.risk or "").strip(),
        "note": (args.note or "").strip(),
        "updated": now(),
    }
    run.setdefault("stage_outputs", {})[stage] = record
    save_json(os.path.join(rd, "run.json"), run)
    stage_dir = os.path.join(rd, "stage-output")
    mkdirs(stage_dir)
    save_json(os.path.join(stage_dir, "%s.json" % stage.lower()), record)
    log(rd, "STAGE-OUTPUT %s %s artifacts=%s" % (stage, status, "|".join(artifacts)))
    emit_stage_output(stage, record)
    return 0


def cmd_approve_units(args):
    _root, _rid, rd, data = ctx(args)
    run, units = data
    if not units:
        return fail("尚未生成最小可执行单元，不能确认空任务列表")
    if run["gates"].get("G3", {}).get("verdict") != "PASS":
        return fail("G3 拆解复核门未通过，不能确认执行列表")
    if not args.note:
        return fail("确认必须附 --note；autonomous 模式必须记录用户明确授权")
    mode = args.mode.strip().lower()
    if mode not in ("user-confirmed", "autonomous"):
        return fail("确认模式只能是 user-confirmed 或 autonomous")
    run["execution_approval"] = {
        "status": "APPROVED",
        "mode": mode,
        "at": now(),
        "note": args.note,
    }
    refresh_ready(units, True)
    save_json(os.path.join(rd, "run.json"), run)
    save_json(os.path.join(rd, "units.json"), units)
    log(rd, "EXECUTION-APPROVAL mode=%s %s" % (mode, args.note))
    print("执行任务列表已确认：mode=%s" % mode)
    print("就绪单元: %s" % ", ".join(u["id"] for u in units if u["state"] == "READY") or "无")
    return 0


def find_cycle(units):
    """DFS 检测依赖环，返回环路径或 None。"""
    graph = dict((u["id"], list(u["deps"])) for u in units)
    color = dict((k, 0) for k in graph)
    stack = []

    def visit(node):
        color[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt not in color:
                continue
            if color[nxt] == 1:
                return stack[stack.index(nxt):] + [nxt]
            if color[nxt] == 0:
                got = visit(nxt)
                if got:
                    return got
        stack.pop()
        color[node] = 2
        return None

    for node in graph:
        if color[node] == 0:
            got = visit(node)
            if got:
                return got
    return None


def split_files(spec):
    """规范化路径，防止 src/a.py 与 ./src/a.py 被当成两个文件。"""
    if isinstance(spec, list):
        items = spec
    else:
        items = re.split(r"[,，;；\s]+", str(spec))
    out = set()
    for p in items:
        p = p.strip()
        if not p:
            continue
        out.add(os.path.normcase(os.path.normpath(p)).replace("\\", "/"))
    return out


def reachable(units, start):
    """start 的全部传递依赖，用于判断两个单元是否天然串行。"""
    graph = dict((u["id"], list(u["deps"])) for u in units)
    seen, stack = set(), list(graph.get(start, []))
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, []))
    return seen


def file_clash(units):
    """两个可能同时在跑的单元不得改同一文件。

    只按 wave 分组不够：wave 只是声明，READY 由依赖决定。这里改成
    「都未终结 且 互相没有依赖路径」即视为可能并行。
    """
    live = [u for u in units if u["state"] not in ("DONE", "DEFERRED")]
    for i in range(len(live)):
        for j in range(i + 1, len(live)):
            a, b = live[i], live[j]
            if b["id"] in reachable(units, a["id"]) or a["id"] in reachable(units, b["id"]):
                continue  # 有依赖关系，天然串行
            shared = split_files(a["files"]) & split_files(b["files"])
            if shared:
                return (a["id"], b["id"], "%s/%s" % (a["wave"], b["wave"]), shared)
    return None


def dep_done(units, uid):
    for u in units:
        if u["id"] == uid:
            return u["state"] == "DONE"
    return False


def find(units, uid):
    for u in units:
        if u["id"] == uid.strip().upper():
            return u
    return None


def downstream(units, uid):
    return [u for u in units if uid in u["deps"]]


def refresh_ready(units, approved=True):
    if not approved:
        return
    for u in units:
        if u["state"] == "PENDING" and all(dep_done(units, d) for d in u["deps"]):
            u["state"] = "READY"


def cascade_block(units, uid, depth=1):
    """级联一层：只冻结直接下游，不递归全图。"""
    blocked = []
    for u in downstream(units, uid):
        if u["state"] not in TERMINAL:
            u["state"] = "BLOCKED"
            u["note"] = "上游 %s 阻塞" % uid
            u["updated"] = now()
            blocked.append(u["id"])
    return blocked


def apply_state(rd, units, unit, target, note):
    cur = unit["state"]
    if target not in STATES:
        return fail("未知状态 %s" % target)
    if target not in ALLOWED.get(cur, ()):
        return fail("非法状态流转 %s: %s -> %s（允许: %s）"
                    % (unit["id"], cur, target, "/".join(ALLOWED.get(cur, ()))))
    unit["state"] = target
    unit["note"] = note or unit["note"]
    unit["updated"] = now()
    if target == "IN_PROGRESS":
        # impl 给实现者自测，qa 给测试官，分开存放才能防止自评通过
        for sub in ("impl", "qa"):
            mkdirs(os.path.join(rd, "evidence", unit["id"], sub))
    if target == "REWORK":
        unit["rework"] += 1
        unit["review"] = ""
        ensure_review_fields(unit)
        for role in REVIEW_ROLES:
            unit["review_roles"][role] = ""
            unit["cross_checks"][role] = ""
        unit["test"] = ""
        if unit["rework"] > REWORK_LIMIT:
            unit["state"] = "BLOCKED"
            unit["note"] = "返工超过 %d 轮，自动隔离" % REWORK_LIMIT
            blocked = cascade_block(units, unit["id"])
            log(rd, "AUTO-BLOCK %s rework>%d cascade=%s" % (unit["id"], REWORK_LIMIT, blocked))
            print("%s 返工已达上限，自动标记 BLOCKED 并隔离" % unit["id"])
            if blocked:
                print("级联冻结下游: %s" % ", ".join(blocked))
            print("按不卡点规则：立刻转去执行其他 READY 单元，不要停下来等用户")
            return 0
    if target == "BLOCKED":
        blocked = cascade_block(units, unit["id"])
        if blocked:
            print("级联冻结下游: %s" % ", ".join(blocked))
    refresh_ready(units, approval_granted_for(rd))
    clash = file_clash(units)
    if clash:
        a, b, w, shared = clash
        print("WARN 文件冲突复活: %s 与 %s 都要改 %s（波次 %s）。"
              "不要同时派工，先做完一个再做另一个" % (a, b, "、".join(sorted(shared)), w))
    log(rd, "STATE %s %s -> %s %s" % (unit["id"], cur, unit["state"], note or ""))
    return 0


def evidence_files(rd, uid, sub):
    """只认非空文件；0 字节占位文件不算证据。"""
    d = lp(os.path.join(rd, "evidence", uid, sub))
    if not os.path.isdir(d):
        return []
    out = []
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.path.getsize(p) >= 20:
            out.append(name)
    return out


def digests(rd, uid, sub):
    d = lp(os.path.join(rd, "evidence", uid, sub))
    out = {}
    if not os.path.isdir(d):
        return out
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                out[name] = hashlib.sha256(fh.read()).hexdigest()
    return out


def duplicated_evidence(rd, uid):
    """qa 证据不得是 impl 证据的副本，否则等于实现者自评通过。"""
    impl = set(digests(rd, uid, "impl").values())
    dup = [n for n, h in digests(rd, uid, "qa").items() if h in impl]
    return dup


def cmd_set(args):
    _root, _rid, rd, data = ctx(args)
    _run, units = data
    unit = find(units, args.unit)
    if not unit:
        return fail("单元不存在: %s" % args.unit)
    target = args.state.strip().upper()
    if target in ("READY", "IN_PROGRESS") and not approval_granted_for(rd):
        return fail("执行任务列表尚未获得用户确认。先展示最小可执行单元并执行 approve-units；"
                    "用户明确授权不需确认时使用 --mode autonomous")
    if target == "IN_PROGRESS":
        role = (getattr(args, "role", "") or "").strip().upper()
        expected = str(unit.get("owner", "R5")).strip().upper()
        if role not in EXECUTOR_ROLES:
            return fail("进入 IN_PROGRESS 必须显式指定 --role R5 或 --role R10")
        if role != expected:
            return fail("角色 %s 不能执行 owner=%s 的单元 %s" % (role, expected, unit["id"]))
    if target == "DONE":
        return fail("DONE 不能手动设置。必须走 R6A/B/C 初审、交叉核验、综合 review PASS + test PASS 自动判定")
    rc = apply_state(rd, units, unit, target, args.note)
    save_json(os.path.join(rd, "units.json"), units)
    if rc == 0:
        print("%s -> %s" % (unit["id"], unit["state"]))
    return rc


def cmd_review(args):
    _root, _rid, rd, data = ctx(args)
    _run, units = data
    unit = find(units, args.unit)
    if not unit:
        return fail("单元不存在: %s" % args.unit)
    if unit["state"] != "REVIEW":
        return fail("%s 当前状态 %s，代码复核只能在 REVIEW 阶段进行（先 set %s REVIEW）"
                    % (unit["id"], unit["state"], unit["id"]))
    if not args.note:
        return fail("复核结论必须附结论说明 --note")
    verdict = args.verdict.strip().upper()
    ensure_review_fields(unit)
    if args.finalize and args.cross_check:
        return fail("--finalize 与 --cross-check 不能同时使用")

    if args.finalize:
        if args.role:
            return fail("综合复核不能指定 --role；只在三路初审和交叉核验完成后执行 --finalize")
        if verdict == "PASS":
            if not evidence_files(rd, unit["id"], "impl"):
                return fail("%s 缺实现者自测证据。先把自测命令与输出写入 evidence/%s/impl/"
                            % (unit["id"], unit["id"]))
            missing = missing_review_evidence(
                rd, unit["id"],
                list(REVIEW_EVIDENCE.values())
                + list(CROSS_REVIEW_EVIDENCE.values())
                + ["cross-check.md", "review.md"])
            if missing:
                return fail("%s 缺 R6 综合证据: %s" % (unit["id"], ", ".join(missing)))
            if any(unit["review_roles"].get(role) != "PASS" for role in REVIEW_ROLES):
                return fail("%s 三路初审未全部 PASS: %s" %
                            (unit["id"], unit["review_roles"]))
            if any(unit["cross_checks"].get(role) != "PASS" for role in REVIEW_ROLES):
                return fail("%s 三路交叉核验未全部 PASS: %s" %
                            (unit["id"], unit["cross_checks"]))
            unit["review"] = "PASS"
            rc = apply_state(rd, units, unit, "TEST", args.note)
        elif verdict == "FAIL":
            unit["review"] = "FAIL"
            rc = apply_state(rd, units, unit, "REWORK", args.note)
        else:
            return fail("综合复核结论只能是 PASS / FAIL")
    else:
        if not args.role:
            return fail("必须指定独立复核角色 --role R6A|R6B|R6C；综合放行使用 --finalize")
        role = args.role.upper()
        if role not in REVIEW_ROLES:
            return fail("复核角色只能是 R6A / R6B / R6C")
        filename = (CROSS_REVIEW_EVIDENCE if args.cross_check else REVIEW_EVIDENCE)[role]
        if not review_evidence_exists(rd, unit["id"], filename):
            return fail("%s 缺 %s 复核证据 evidence/%s/review/%s（至少 20 字节）" %
                        (unit["id"], role, unit["id"], filename))
        if args.cross_check:
            if unit["review_roles"].get(role) != "PASS":
                return fail("%s %s 初审未 PASS，不得进行交叉核验" % (unit["id"], role))
            unit["cross_checks"][role] = verdict
            if verdict == "FAIL":
                unit["review"] = "FAIL"
                rc = apply_state(rd, units, unit, "REWORK", args.note)
            else:
                unit["updated"] = now()
                log(rd, "CROSS-REVIEW %s %s=%s %s" %
                    (unit["id"], role, verdict, args.note))
                rc = 0
        else:
            if verdict == "PASS" and not evidence_files(rd, unit["id"], "impl"):
                return fail("%s 缺实现者自测证据。先把自测命令与输出写入 evidence/%s/impl/"
                            % (unit["id"], unit["id"]))
            unit["review_roles"][role] = verdict
            if verdict == "FAIL":
                unit["review"] = "FAIL"
                rc = apply_state(rd, units, unit, "REWORK", args.note)
            else:
                unit["updated"] = now()
                log(rd, "REVIEW %s %s=%s %s" %
                    (unit["id"], role, verdict, args.note))
                rc = 0
    save_json(os.path.join(rd, "units.json"), units)
    if rc == 0:
        if args.finalize:
            print("%s R6 综合复核=%s -> %s" % (unit["id"], verdict, unit["state"]))
        elif args.cross_check:
            print("%s %s 交叉核验=%s -> %s" %
                  (unit["id"], args.role, verdict, unit["state"]))
        else:
            print("%s %s 初审=%s -> %s" %
                  (unit["id"], args.role, verdict, unit["state"]))
    return rc


def cmd_test(args):
    _root, _rid, rd, data = ctx(args)
    _run, units = data
    unit = find(units, args.unit)
    if not unit:
        return fail("单元不存在: %s" % args.unit)
    if unit["state"] != "TEST":
        return fail("%s 当前状态 %s，功能测试只能在 TEST 阶段进行" % (unit["id"], unit["state"]))
    if not args.note:
        return fail("测试结论必须附说明 --note")
    verdict = args.verdict.strip().upper()
    if verdict not in ("PASS", "FAIL") and not verdict.startswith("BLOCKED"):
        return fail("测试结论只能是 PASS / FAIL / BLOCKED-无法验证，收到: %s" % args.verdict)
    if verdict.startswith("BLOCKED"):
        verdict = "BLOCKED"
    unit["test"] = verdict
    if verdict == "PASS":
        if unit["review"] != "PASS":
            return fail("%s 代码复核未通过，不得判定测试通过" % unit["id"])
        files = evidence_files(rd, unit["id"], "qa")
        if not files:
            return fail("%s 缺功能测试证据。测试官必须把用例、命令与实际输出写入 "
                        "evidence/%s/qa/（实现者的自测证据在 impl/，不能顶替）"
                        % (unit["id"], unit["id"]))
        dup = duplicated_evidence(rd, unit["id"])
        if dup:
            return fail("%s 的测试证据 %s 与实现者自测证据内容完全相同。"
                        "测试官必须独立执行并留下自己的用例与输出，不能复制 impl/ 里的文件"
                        % (unit["id"], "、".join(dup)))
        unit["state"] = "DONE"
        unit["updated"] = now()
        refresh_ready(units, approval_granted_for(rd))
        log(rd, "DONE %s evidence=%s" % (unit["id"], ",".join(files)))
        save_json(os.path.join(rd, "units.json"), units)
        print("%s -> DONE（证据 %d 项）" % (unit["id"], len(files)))
        ready = [u["id"] for u in units if u["state"] == "READY"]
        if ready:
            print("已解锁就绪单元: %s" % ", ".join(ready))
        return 0
    if verdict == "BLOCKED":
        rc = apply_state(rd, units, unit, "BLOCKED", args.note)
    else:
        rc = apply_state(rd, units, unit, "REWORK", args.note)
    save_json(os.path.join(rd, "units.json"), units)
    if rc == 0:
        print("%s 功能测试=%s -> %s" % (unit["id"], verdict, unit["state"]))
    return rc


def cmd_board(args):
    _root, rid, rd, data = ctx(args)
    run, units = data
    print("RUN %s | %s" % (rid, run["title"]))
    gates = run.get("gates", {})
    print("门禁：" + (" ".join("%s=%s" % (g, gates[g]["verdict"]) for g in GATES if g in gates) or "未记录"))
    approval = run.get("execution_approval", {})
    print("确认：%s%s" %
          (approval.get("status", "NOT_REQUESTED"),
           (" (" + approval.get("mode", "") + ")") if approval.get("mode") else ""))
    if not units:
        print("单元：无；执行阶段跳过")
        print("阶段产物：%d/%d" % (len(run.get("stage_outputs", {})), len(REQUIRED_STAGE_OUTPUTS)))
        return 0
    counts = {}
    for u in units:
        counts[u["state"]] = counts.get(u["state"], 0) + 1
    print("单元：" + " ".join("%s=%d" % (s, counts[s]) for s in STATES if s in counts))
    done = counts.get("DONE", 0)
    print("完成度：%d/%d" % (done, len(units)))
    for u in sorted(units, key=lambda x: x["id"]):
        print("- %s | %s | %s" % (u["id"], u["state"], u["title"]))
    approval_ok = approval_granted(run)
    ready = [u["id"] for u in units if u["state"] == "READY"] if approval_ok else []
    blocked = [u["id"] for u in units if u["state"] == "BLOCKED"]
    if ready:
        print("可执行：%s" % ", ".join(ready))
    if blocked:
        print("阻塞：%s" % ", ".join(blocked))
    stages = run.get("stage_outputs", {})
    recorded = len([stage for stage in REQUIRED_STAGE_OUTPUTS if stage in stages])
    missing_stages = [stage for stage in REQUIRED_STAGE_OUTPUTS if stage not in stages]
    print("阶段产物：%d/%d%s" %
          (recorded, len(REQUIRED_STAGE_OUTPUTS),
           ("；缺失=" + ",".join(missing_stages)) if missing_stages else ""))
    return 0


def cmd_blockers(args):
    _root, _rid, rd, data = ctx(args)
    _run, units = data
    blocked = [u for u in units if u["state"] == "BLOCKED"]
    if not blocked:
        print("无阻塞单元")
        return 0
    print("阻塞清单（批量上报，不要逐个打断用户）:")
    for u in blocked:
        print("- %s %s | 返工=%d | 原因: %s" % (u["id"], u["title"], u["rework"], u["note"] or "未记录"))
        print("  受影响需求: %s" % (u["maps"] or "未标注"))
    p = os.path.join(rd, "blockers.md")
    print("详情文件: %s" % p)
    return 0


def cmd_resume(args):
    root = os.path.abspath(args.root or os.getcwd())
    rid = current_run(root)
    if not rid:
        print("无活动 run")
        return 0
    rd = run_dir(root, rid)
    run = load_json(os.path.join(rd, "run.json"), {})
    units = load_json(os.path.join(rd, "units.json"), [])
    print("=== 续跑上下文 ===")
    print("RUN %s | %s" % (rid, run.get("title")))
    print("台账: %s" % rd)
    approval = run.get("execution_approval", {})
    print("执行确认: %s%s" %
          (approval.get("status", "NOT_REQUESTED"),
           (" (" + approval.get("mode", "") + ")") if approval.get("mode") else ""))
    gates = run.get("gates", {})
    print("已过门禁: " + (" ".join("%s=%s" % (g, gates[g]["verdict"]) for g in GATES if g in gates) or "无"))
    pending = [u for u in units if u["state"] not in TERMINAL]
    print("未完成单元 %d 个:" % len(pending))
    for u in pending:
        print("  %s %s | %s | 验收: %s" % (u["id"], u["state"], u["title"], u["accept"]))
        print("     文件: %s | 验证: %s" % (u["files"], u["verify"]))
    for name in ("kb-hits.md", "assumptions.md", "blockers.md"):
        p = os.path.join(rd, name)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            print("参考文件: %s" % p)
    print("下一步: 若执行确认=PENDING，先展示清单并等待用户确认；确认后 board 看进度")
    return 0


def cmd_finish(args):
    _root, rid, rd, data = ctx(args)
    run, units = data
    if units and not approval_granted(run):
        return fail("执行任务列表尚未获得用户确认，不能收尾")
    records = [r.strip().upper() for r in (args.records or "").split(",") if r.strip()]
    light_ok = run.get("channel") in ("light", "creative")
    if getattr(args, "no_archive", False):
        if not light_ok:
            return fail("只有轻量和创作通道允许免归档，本 run 是 %s 通道" % run.get("channel"))
        if not args.note:
            return fail("免归档必须用 --note 说明为什么没有值得沉淀的新知识")
        if records:
            return fail("--no-archive 与 --records 不能同时给")
    elif not records:
        return fail("G6 知识归档是强制门禁：必须提供已写入的记录编号 --records F-0xx[,P-0xx]。"
                    "轻量或创作通道确实无坑可记时用 --no-archive --note \"原因\"")
    bad = [r for r in records if not re.match(r"^[FPEH]-\d+$", r)]
    if bad:
        return fail("记录编号格式错误: %s（应形如 F-012）" % ", ".join(bad))
    # 记录日期必须不早于本 run 创建日，防止拿别的 run 新写的记录充数
    run_day = (run.get("created") or "")[:10]
    by_id = dict((r["id"], r) for r in kb_records())
    for rid_ in records:
        rec = by_id.get(rid_)
        if rec and run_day and rec.get("date") and rec["date"][:10] < run_day:
            return fail("%s 的日期是 %s，早于本 run 创建日 %s，不是本次沉淀的知识"
                        % (rid_, rec["date"][:10], run_day))
    known = kb_record_ids()
    missing = [r for r in records if r not in known]
    if missing:
        return fail("索引中找不到 %s。先把记录写入知识库并执行 sire_kb.py reindex" % ", ".join(missing))
    baseline = set(run.get("kb_baseline") or [])
    fresh = [r for r in records if r not in baseline]
    if records and baseline and not fresh:
        return fail("%s 在本次任务开始前就已存在，不算本次归档。"
                    "G6 要求沉淀新知识：用 sire_kb.py next-id 取新编号写新记录再 reindex"
                    % ", ".join(records))
    open_units = [u["id"] for u in units if u["state"] not in TERMINAL]
    if open_units:
        return fail("仍有未收敛单元: %s（须为 DONE/BLOCKED/DEFERRED 之一）" % ", ".join(open_units))
    migration_error = migration_sync_error(run)
    if migration_error:
        return fail(migration_error + "；先同步迁移文档再收尾")
    missing_stage_outputs = [stage for stage in REQUIRED_STAGE_OUTPUTS
                             if stage not in (run.get("stage_outputs") or {})]
    if missing_stage_outputs:
        return fail("阶段产物未完整：%s。无需执行的阶段也必须用 stage-output 标记 SKIPPED" %
                    ", ".join(missing_stage_outputs))
    if units and run["gates"].get("G5", {}).get("verdict") not in ("PASS", "FAIL"):
        return fail("G5 集成验收未记录，先执行 gate G5 --pass 或 --fail")
    run["kb_records"] = records
    note = ("records=" + ",".join(records)) if records else ("免归档: " + args.note)
    run["gates"]["G6"] = {"verdict": "PASS", "at": now(), "note": note}
    g6_record = {
        "stage": "G6",
        "status": "DONE",
        "artifacts": ["知识归档：" + ", ".join(records) if records else "知识归档：免归档"],
        "reason": "",
        "risk": "",
        "note": note,
        "updated": now(),
    }
    run.setdefault("stage_outputs", {})["G6"] = g6_record
    run["state"] = "CLOSED"
    run["closed"] = now()
    vector_script = str(SHARED_SKILL_DIR / "scripts" / "sire_vector_db.py")
    for command in (("index",), ("migrate",)):
        result = subprocess.run([sys.executable, vector_script, *command],
                                text=True, capture_output=True, encoding="utf-8")
        if result.returncode:
            return fail("数据库同步失败（%s）：%s" % (command[0], result.stderr.strip() or result.stdout.strip()))
    save_json(os.path.join(rd, "run.json"), run)
    mkdirs(os.path.join(rd, "stage-output"))
    save_json(os.path.join(rd, "stage-output", "g6.json"), g6_record)
    log(rd, "FINISH records=%s" % ",".join(records))
    counts = {}
    for u in units:
        counts[u["state"]] = counts.get(u["state"], 0) + 1
    print("RUN %s 已收尾" % rid)
    print("单元: " + (" ".join("%s=%d" % (k, v) for k, v in sorted(counts.items())) or "无"))
    print("归档记录: %s" % (", ".join(records) if records else "免归档（%s）" % args.note))
    return 0


def main():
    p = argparse.ArgumentParser(description="SIRE v6 交付台账 CLI")
    p.add_argument("--root", default=None, help="项目根目录，默认当前目录")
    p.add_argument("--run", default=None, help="指定 RUN_ID，默认取 .sire/current")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("init")
    s.add_argument("--title", required=True)
    s.add_argument("--channel", default="full",
                   choices=["full", "light", "analysis", "creative", "danger"])
    s.add_argument("--project", default=None)

    s = sub.add_parser("gate")
    s.add_argument("gate")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--pass", dest="pass_", action="store_true")
    g.add_argument("--fail", dest="fail_", action="store_true")
    s.add_argument("--note", default="")

    s = sub.add_parser("add-units")
    s.add_argument("--file", required=True)

    s = sub.add_parser("approve-units")
    s.add_argument("--mode", choices=["user-confirmed", "autonomous"], required=True,
                   help="user-confirmed=用户确认；autonomous=用户明确授权不需确认/自行完成")
    s.add_argument("--note", required=True,
                   help="记录用户确认原话或明确的自行完成授权")

    s = sub.add_parser("set")
    s.add_argument("unit")
    s.add_argument("state")
    s.add_argument("--role", choices=list(EXECUTOR_ROLES),
                   help="进入 IN_PROGRESS 时必须与单元 owner 匹配")
    s.add_argument("--note", default="")

    s = sub.add_parser("review")
    s.add_argument("unit")
    s.add_argument("verdict", choices=["PASS", "FAIL", "pass", "fail"])
    s.add_argument("--role", choices=list(REVIEW_ROLES),
                   help="初审或交叉核验的独立 Agent：R6A / R6B / R6C")
    s.add_argument("--cross-check", action="store_true",
                   help="记录指定 R6 Agent 的交叉核验结果")
    s.add_argument("--finalize", action="store_true",
                   help="汇总三路初审和交叉核验并生成 R6 综合结论")
    s.add_argument("--note", default="")

    s = sub.add_parser("test")
    s.add_argument("unit")
    s.add_argument("verdict", help="PASS / FAIL / BLOCKED-无法验证")
    s.add_argument("--note", default="")

    sub.add_parser("board")
    sub.add_parser("show-units")
    sub.add_parser("blockers")
    sub.add_parser("resume")

    s = sub.add_parser("stage-output")
    s.add_argument("stage")
    s.add_argument("status")
    s.add_argument("--artifact", action="append", default=[])
    s.add_argument("--reason", default="")
    s.add_argument("--risk", default="")
    s.add_argument("--note", default="")

    s = sub.add_parser("finish")
    s.add_argument("--records", default="")
    s.add_argument("--no-archive", dest="no_archive", action="store_true",
                   help="轻量或创作通道且未踩坑时免归档，必须用 --note 说明")
    s.add_argument("--note", default="")

    args = p.parse_args()
    fn = {
        "init": cmd_init, "gate": cmd_gate, "add-units": cmd_add_units,
        "approve-units": cmd_approve_units, "set": cmd_set,
        "review": cmd_review, "test": cmd_test, "board": cmd_board,
        "show-units": cmd_show_units, "blockers": cmd_blockers,
        "resume": cmd_resume, "stage-output": cmd_stage_output, "finish": cmd_finish,
    }.get(args.cmd)
    if not fn:
        p.print_help()
        return 2
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
