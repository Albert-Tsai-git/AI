import sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P = r"D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md"
t = open(P, encoding="utf-8").read()
blocks = dict(re.findall(r"^### (F-\d{3}): [^\n]*\n(.*?)(?=^### |\Z)", t, re.M | re.S))

unit_needles = {
 "U-01": ("F-053", ["server.py:341", "core/reader_mp.py:85", "WEB_GUI_PORT"]),
 "U-02": ("F-054", ["core/protocol.py:16", "FwProfileUndetermined", "0x38"]),
 "U-03": ("F-055", ["PAGE_BUILDERS", "unthrottled-timer.js", "new uPlot"]),
 "U-04": ("F-056", ["electron/main.js:144", "backgroundThrottling", "PORT_PINNED", "F-057"]),
 "U-05": ("F-057", ["pytest.ini:9", "include-data-dir=frontend", "NAS_SHARE"]),
 "U-06": ("F-058", ["core/offline_detection.py:717", "frontend/js/pages/offline_detection.js:58", "CHANGELOG.md:17"]),
 "U-07": ("F-059", ["docs/skills", "PROJECT-CONTEXT.md:213", "playwright_ui_self_test"]),
}
fix_needles = {
 "F-053": ["(:11088)", "(:11164)", "(:11177)", "`device_id_confirmed`(:381)", "`_last_probe_alive`(:387)",
           "KK_READER_ENV` :46", "同文件:500", ":2959-2984", "/api/identify` :5318", "（:9511）在注释块之后直接 `return`（:9528）",
           "reader_wrapper.py:46-62", "REPORTS_DIR", "_conn_generation 协作式取消"],
 "F-054": ["四个私有方法", "v<X.Y.Z>.json", "CRC16-CCITT", "read_version"],
 "F-055": ["（:151）", "`buildConsole` :154", "144 处 `await sleep`", "共 19 处", "scope-bar.js:4132/:4145",
           "见 F-053", "confirmDialog({danger:true})"],
 "F-056": ["机理见 F-055", "归 F-057", "见 F-057 踩坑 4", "黑屏"],
 "F-057": ["**7 个**", "125 个文件", "conftest.py:48", "**8 个文件**", "归 F-053", "先记结论", "军规 6 词表"],
 "F-058": ["server.py:10613", "server.py:10649", "扭矩去皮零点", "归 F-055 踩坑 1", "build-win-smoke", "~/Downloads/下线检测报告"],
 "F-059": ["（:224 起", "AGENTS.md, 行号过时"],
}
fail = 0
for u, (rid, nds) in unit_needles.items():
    miss = [x for x in nds if x not in blocks[rid]]
    fail += bool(miss)
    print(f"{u} {rid}: {'PASS' if not miss else 'FAIL 缺 ' + str(miss)}")
for rid, nds in fix_needles.items():
    miss = [x for x in nds if x not in blocks[rid]]
    fail += bool(miss)
    print(f"更正核对 {rid}: {'PASS' if not miss else 'FAIL 缺 ' + str(miss)}")
print("绝对路径残留:", t.count("D:\\code"), t.count("D:/code"))
print("总判定:", "PASS" if fail == 0 else f"FAIL({fail} 组)")
