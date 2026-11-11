# -*- coding: utf-8 -*-
"""R6A 返工：卡片内重复行去重、恢复被误杀的两条、补 H-008 状态。"""
import glob
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
SP = sys.argv[1]
orig = {r["record_id"]: r for r in json.load(open(SP + "/kr_all.json", encoding="utf-8"))}


def dedupe_lines(v):
    if isinstance(v, list):
        v = "\n".join(map(str, v))
    out, seen = [], set()
    for line in str(v).split("\n"):
        key = re.sub(r"^\s*(\d+[.、)]|[-*•])\s*", "", line).strip()
        if len(key) > 12 and key in seen:
            continue
        if len(key) > 12:
            seen.add(key)
        out.append(line)
    # 去重后重新给纯数字列表编号
    n = 0
    res = []
    for line in out:
        m = re.match(r"^(\s*)(\d+)([.、)])\s*(.*)$", line)
        if m:
            n += 1
            res.append(f"{m.group(1)}{n}{m.group(3)} {m.group(4)}")
        else:
            res.append(line)
    return "\n".join(res)


RESTORE = {
    "F-062": dict(
        title="Output目录：MPT协议回归与USB描述符探测快照（含USB Hub探测与A~F测试副作用的坑）",
        keywords=orig["F-062"]["keywords"], date="2026-10-13", project="Output 目录只读分析",
        scene="需要梳理 Output 目录（MPT A~F 协议回归测试 + USB 描述符探测脚本）的用途、组成和注意事项时。",
        steps="1. 只读取目录清单、说明文档及脚本入口/主要调用和副作用，不修改原始文件。\n2. 两组快照彼此独立：A~F 六种编码器协议 Python 驱动与硬件回归测试；USB 描述符多产品线固件说明与三种 Windows 主机侧探测脚本。不构成单个可安装 Python 包。\n3. 与 SIRE 现存 MPT/A~F 硬件验证和 Analyzer 记录对照，旧记录不作为本次硬件实测证据。",
        verify="PowerShell 只读枚举文件、行数和大小；检查测试脚本入口、stage_control、CSV/log 输出和 USB 探测路线。未运行硬件脚本，没有连接或操作设备。",
        pitfalls="1. Output 是从其他目录拷贝的冻结快照，不会同步源目录。\n2. A~F 测试会写设备状态并覆盖输出文件，运行前要确认设备与输出目录。\n3. USB Hub 探测 PID 固定 0x0001，只匹配 M01。\n4. 常规 OS 缓存拿不到未引用的字符串 index=4。",
        files="test_mpt_protocol_regression_AtoF.py（A~F 主流程）；EncoderBase.py、Analyzer.py（再标定 API/通信基础）；mpt_*_protocol.py、bissc_protocol.py、CRC.py（协议帧解析和校验）；usb_descriptors/probe_usb_descriptors_hub.py（Hub IOCTL 探测）；usb_descriptors/USB描述符修改说明.md",
        status="已完成（只读静态分析；未执行设备验证）"),
    "P-20261052": dict(
        title="经明确授权补齐历史更新日志分类（改工作区日志不会重写历史tag/不重发飞书）",
        keywords=orig["P-20261052"]["keywords"], date="2026-10-26", project="driverSoftware",
        scene="用户明确授权后，要把未发布的 Kt 修复和 v0.20.3~v0.20.5 历史条目按新 CHANGELOG 规范补分类（通知解析需要新增/修复分类）。前两轮因范围约束未改历史段落。",
        steps="1. v0.20.5 的固件 v3.4.10 支持归“新增”，保留空“修复”分类。\n2. v0.20.4 和 v0.20.3 条目归“修复”，保留空“新增”分类。\n3. 当前未发布的 Kt 条目已有新增/修复模板，无需移动。\n4. 仅补分类，不重写条目、不改日期和所属版本。",
        verify="读取原文件与 git diff，确认仅增加 9 行标题和分隔空行、原有条目不变；git diff --check 无问题。本轮未授权测试，未运行测试、发布或发送消息。",
        pitfalls="历史条目平铺缺少通知解析所需分类是根因；修改工作区日志不会自动重写历史 tag，也不会重发原飞书消息。",
        files="CHANGELOG.md 的未发布、0.20.5、0.20.4、0.20.3 段落",
        status="已本地提交 fb9f1499，未推送；未测试"),
}

total_fix = 0
for p in sorted(glob.glob(SP + "/cards_*.json")):
    cards = json.load(open(p, encoding="utf-8"))
    for c in cards:
        if c["id"] in RESTORE:
            c["action"], c["target"], c["reason"] = "keep", "", "R6A 复核：含可复用踩坑，恢复保留"
            c["card"] = RESTORE[c["id"]]
            print("恢复", c["id"])
        if c["action"] == "keep":
            card = c.get("card") or c
            for f in ("steps", "verify", "pitfalls", "files"):
                if f in card and card[f]:
                    new = dedupe_lines(card[f])
                    if new != (card[f] if isinstance(card[f], str) else "\n".join(map(str, card[f]))):
                        total_fix += 1
                    card[f] = new
            if c["id"] == "F-098":
                card["status"] = (card.get("status") or "").rstrip() + "；并入的偏好 H-008（FC 重制 UI 沿用用户确认的室内参考风格）仍然生效"
                print("F-098 状态已补 H-008 生效说明")
    json.dump(cards, open(p, "w", encoding="utf-8"), ensure_ascii=False)
print("去重改动字段数", total_fix)
