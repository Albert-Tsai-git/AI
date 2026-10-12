import re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
P = r"D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md"
t = open(P, encoding="utf-8").read()

# ---------- 全文件级：去掉硬编码绝对路径 + 标题改写 ----------
global_fix = [
    (r"D:\\code\\driverSoftware2", r"@CODE_ROOT@\driverSoftware2"),
    ("### F-055: driverSoftware2 前端地图：13 页清单、路由注册五处、REST/WS 与 uPlot 图表",
     "### F-055: driverSoftware2 前端地图：13 页清单、路由注册五处、REST/WS 与示波器 uPlot 图表"),
    ("### F-057: driverSoftware2 测试分层、CI 门禁与构建发布流程",
     "### F-057: driverSoftware2 测试分层、CI 门禁与构建发布（旧前端随 server.dist 走的根因）"),
]
for a, b in global_fix:
    n = t.count(a)
    print(f"全局替换 x{n}: {a[:52]}")
    t = t.replace(a, b)

# ---------- 分块内替换 ----------
parts = re.split(r"(?m)^(?=### F-\d{3}: )", t)
blocks, tail = parts[:-1], parts[-1] if len(parts) > 1 else ""

def edit(rid, pairs):
    for i, b in enumerate(blocks):
        if b.startswith("### " + rid + ":"):
            for old, new in pairs:
                c = b.count(old)
                if c != 1:
                    print(f"  !! {rid} 命中 {c} 次: {old[:48]}")
                b = b.replace(old, new)
            blocks[i] = b
            return
    print(f"  !! 找不到块 {rid}")

kw = {
 "F-053": ("ws monitor 空壳]", "ws monitor 空壳, 加接口, 8765, timeout, 无响应, 端口被占, config.json, 报告落盘, request_abort, _conn_generation, LinkDown]"),
 "F-054": ("算法不许第二份]", "算法不许第二份, read_version, fw_git_sha, 0x0B, 力矩无响应, OTA]"),
 "F-055": ("tokens.css, i18n]", "tokens.css, i18n, 示波器, 切页, 图表冻结, 不用构建, 13页, 受众档位, MAX_UI_LEVEL, confirmDialog]"),
 "F-056": ("user agent Electron]", "user agent Electron, 黑屏, 起不来, npm start, nsis]"),
 "F-057": ("start.bat, READER_MP]", "start.bat, READER_MP, 打包, 旧前端, server.dist, dist_app, 复用dist, CHANGELOG, 未发布, 冒烟, win-smoke]"),
 "F-058": ("判定在后端, 人工决定]", "判定在后端, 人工决定, core/offline_detection.py, offline_detection.js, 八步, 存档, 序列号, Downloads]"),
 "F-059": ("CHANGELOG 体例, 文档引用不实]", "CHANGELOG 体例, 文档引用不实, AGENTS.md, 行号过时, 文档引用失效]"),
}
for rid, (a, b) in kw.items():
    edit(rid, [(a, b)])

edit("F-053", [
 ("**关键文件与接口**:", "**关键文件与接口（均属 F-053 后端地图，仓 = `@CODE_ROOT@\\driverSoftware2`）:**"),
 ("**验证方法**:",
  "**落盘与长任务生命周期**:\n"
  "- 配置与报告根：`core/offline_detection.py:82 REPORTS_DIR = Path.home()/\"Downloads\"/\"下线检测报告\"`、同文件 :83 `CONFIG_PATH`；"
  "日志根策略见 `core/paths.py:4`（打包后 `resources/server/logs` 普通用户不可写，由该模块分流）与 :12-13"
  "（三个使用点：`fullpipe_worker.LOG_DIR` 的 `calib_*.log`、`server._RECAL_LOGS_DIR` 的 `recal_*` 标定产物、`server.REPORT_DIR`）；"
  "测试报告落 `logs/reports/` 而非 `docs/reports/auto/`（`server.py:1930` 注释）。\n"
  "- 长跑任务取消：有 worker 对象的（fullpipe / kt）走 `request_abort()`（`core/fullpipe_worker.py:413`）；"
  "没有 worker 的 closure 用断链代哨兵 `server.py:402 _conn_generation` 协作式取消；链路断开统一由 `LinkDown` 处理器 `server.py:870` 收口。\n\n"
  "**验证方法**:"),
])

edit("F-054", [
 ("**协议 V3.3 相对 V3.2 的关键变更**", "**协议 V3.3 相对 V3.2 的关键变更（F-054 协议层，逐条对过文档）**"),
])

edit("F-055", [
 ("**关键文件与接口（pages",
  "**关键文件与接口（F-055 前端地图 · pages"),
 ("**实施步骤（周期性发帧为什么不能用定时器）**:",
  "**受众档位与危险操作确认**: 档位由产物根文件 `MAX_UI_LEVEL`（`server.py:317`）下发；前端 `capabilities.js:7 UI_LEVEL_KEY`、:14 `CAP_MIN_LEVEL`、:91 取 `min` 过滤，`app.js:375 applyUiLevel()` 做 rail 项过滤与空分段隐藏；危险操作统一走 `components.js:149 confirmDialog({danger:true})`。**新功能要先决定落在哪一档** —— 客户包（L1/L0）看不到的入口等于没做。\n\n"
  "**实施步骤（周期性发帧为什么不能用定时器）**:"),
])

edit("F-057", [
 ("AGENTS.md 讲的是原则", "**先记结论：前端文件装在 `dist_app/server.dist` 里随服务端走，任何跳过 Nuitka、复用上次 dist 的打包都会把旧前端原样发出去。**\n\nAGENTS.md 讲的是原则"),
 ("**三 · 构建与发布**:", "**三 · 构建与发布（F-057，`scripts/build.bat` / `scripts/release.py`）:**"),
 ("4. `cmd /c` 里 `for /f ('…')` 内层的 `=` 与 `>` 必须 `^` 转义",
  "4. 分支命名以 `AGENTS.md` 军规 6 词表为准（`feat/` `fix/` `docs/` `chore/` `release/` `hotfix/`）；F-019 里的 `feature/*` 属历史线记载。**发布前置也已换代**：F-019 结论 5「必须先完整构建才 bump」不再适用，现为 `release.py` 可选 `--local-build`、正式包由 GitLab Runner 在 tag 上构建。\n"
  "5. `cmd /c` 里 `for /f ('…')` 内层的 `=` 与 `>` 必须 `^` 转义"),
])

edit("F-058", [
 ("**口径速查（别自己发明）**", "**口径速查（F-058 下线检测 · 别自己发明）**"),
 ("**强顺序门控**在后端：", "报告与配置落 `core/offline_detection.py:82 REPORTS_DIR`（`~/Downloads/下线检测报告`）、:83 `CONFIG_PATH`。**强顺序门控**在后端："),
 ("`win-smoke-offline-detection` 这类冒烟 tag 名在 `.gitlab-ci.yml` 里查无同名 job（别假设存在）",
  "冒烟通道真实存在：`.gitlab-ci.yml:172-175` 的 `build-win-smoke` 按 `/^win-smoke-/` 触发，本分支已打过 `win-smoke-offline-detection` 与 `win-smoke-offline-detection-fix2`（冒烟包不 bump VERSION，落 `02SD\\<tag>\\`）"),
])

edit("F-059", [
 ('**docs/skills 13 份与"改什么前必读"**:',
  '**docs/skills 13 份与"改什么前必读"（本表属 F-059；核对命令 `ls docs/skills/*.md | wc -l` = 13）**:'),
])

out = "".join(blocks) + tail
open(P, "w", encoding="utf-8", newline="\n").write(out)
print("剩余硬路径 D:\\code:", out.count(r"D:\code\driverSoftware2"))
for rid in ["F-053","F-054","F-055","F-056","F-057","F-058","F-059"]:
    i = out.find("### " + rid + ":")
    j = out.find("\n### ", i + 5)
    blk = out[i:j if j > 0 else len(out)]
    print(rid, "块长", len(blk), "| 含 F-0xx 定位语:", bool(re.search(r"属 F-0|本段属|本表属|F-05\d ", blk)))
