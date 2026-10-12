**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**取代**: K-REPO-DRIVERSOFTWARE-20260924 中缺失的前端部分（旧摘要只有一句 "ESM 前端"）
**关键词**: [前端地图, frontend, 无构建 ESM, app.js, PAGE_BUILDERS, 加一个新页面, api.js, X-KK-Trace, MonitorSocket, PipelineSocket, KtSocket, telemetry:sample, scope-bar.js, uPlot, PAGE_PROFILE, 冻结看门狗, unthrottled-timer, setUnthrottledInterval, 后台节流, 0x4D 看门狗, 页面重建 innerHTML, pageCleanups, capabilities.js 受众分层, tokens.css, i18n]

**需求场景 / 现象**: 本仓前端**没有 build**（浏览器直接跑 ESM），也没有框架。加页面、改交互、调示波器之前需要知道：页面在哪注册、REST/WS 从哪进出、周期性发帧怎么不被浏览器节流、页面重建会漏掉什么。

**方案 / 架构**:
- **入口**: `frontend/index.html:199` `<script type="module" src="/static/js/app.js">`，`uPlot` 以 IIFE 全局挂载（:198），6 个 CSS 入口（:11-16）。改 `frontend/js/**/*.js` 直接生效（server 自动 serve 最新版）。
- **分层**: `js/app.js`(1654 行) 主编排（路由/懒建页/顶栏/scope 抽屉/急停）· `js/api.js` REST+WS 客户端 · `js/store.js:34 class Store` 全局 state + 事件总线 · `js/components.js` DOM helper 与弹窗（:8/:57/:86/:149/:242，弹窗焦点 :235）· `js/scope-bar.js`(4418 行) 示波器抽屉 · `js/capabilities.js:14 CAP_MIN_LEVEL` 受众分层门控 · `i18n.js` + `locales/{zh,en}.json` · `theme.js` · `link-health.js` · `blackbox.js` · `estop.js` · `unthrottled-timer.js` · `trip-snapshot.js` · `risk-tags.js` · `render-md.js` · `test-scope.js` · `bg-canvas.js`。
- **路由**: `app.js:221-237 const PAGE_BUILDERS` 共注册 **12 个页面**（motion/registers/calibrate/torque/console/tests/offline-detection/trajectory/bootloader/guide/diag/forcecal；`overview` 已删 :222、`scope` 页已删由抽屉自带 :224、`detection` 合并进 calibrate :230），懒建 `app.js:336`（`PAGE_BUILT` 集合 :238）。侧栏项在 `index.html:84-155` 的 `rail-item[data-page=…]`，容器是 `index.html` 里对应的 `<section id="page-…">`（如下线检测 :169）。
- **通信**: 唯一 REST 咽喉 `api.js:105 request()`；每请求带 `X-KK-Trace` 取证头（:115）；**默认不设超时**（:92-103 有意为之，长命令由后端控制）；HTTP 200 但 `ok:false` 也记为失败（:138）；结果回调钩子 `onApiOutcome` :81，由 `link-health` 单向订阅（:77，刻意不成环）。WS 三类：`MonitorSocket` :456 `/ws/monitor`、`PipelineSocket` :516 `/ws/calibrate/pipeline`、`KtSocket` :541 `/ws/kt`；消费点 `app.js:675` → `feedScope` :692 / `watchFault` :746，开关 `syncMonitorLifecycle` :724（仅 motion 页 + 已连接时开）。注意 `/ws/monitor` 后端侧是空壳（见后端地图记录），实时数据实际走 REST → `TELEMETRY_DISPATCH`（api.js:26-69）转 sample → `store.emit("telemetry:sample")`（:152）→ `scope-bar.js:726` 订阅。
- **加一个新页面（5 处，顺序固定）**: ① `index.html` 加 `rail-item` + `<section id="page-x">`；② `app.js:17` 区域加 import + `:221 PAGE_BUILDERS` 加键；③ `capabilities.js:14 CAP_MIN_LEVEL["page:x"]` 给定受众档位（如 `"page:offline-detection": 2` 在 :35）；④ `scope-bar.js:257 PAGE_PROFILE` 给该页的采样方案，**不需要 scope 就显式写 null**；⑤ `locales/zh.json`、`locales/en.json` 文案。
- **样式**: `css/tokens.css:3` 声明 `docs/theme-servo-cyan.md` 为单一真相源（cyan 主色阶 :45-49、字号阶 :93-101、布局根 token `--rail-w`/`--topbar-h` :104-105、light/dark 双份 :117/:171）；受众分层的"分段标题空段自动隐藏"（`docs/gui-design.md:144`）落在 `app.js:375-394 applyUiLevel()`。CSS 按 base reset / components / layout / pages 四层分文件。

**关键文件与接口（pages 清单，13 个文件）**:
- `motion.js`（运动）：`buildMotion` :174，MIT 五滑条 + presets，连续发帧 `restartCont` :3020、`setUnthrottledInterval(sender, softPollPeriodMs())` :3066，看门狗安全档 `WDG_SAFE_POLL_MS = 200` :3010 与 `Math.min(base, …)` 钳制 :3017、低频预警 :3057；Electron 形态判定（UA 含 `" Electron/"`）:158-172。
- `calibrate.js`（电机标定，2662 行）：`buildCalibrate` :190，多相位卡片（:259/:484/:1167/:1414/:1521/:1806/:1938/:2141/:2242/:2467），一键再标定 `api.pipelineStart` :739 + `PipelineSocket` :746。
- `offline_detection.js`（下线检测，1312 行）：`ITEMS` :21-28、`buildOfflineDetection` :58，页面级清理表 `pageCleanups`/`onPageRebuild` :52-59。
- `torque.js` 砝码摆臂 Kt（走 `/ws/kt`）· `forcecal.js` 力感知标定 · `registers.js` 寄存器读写 · `bootloader.js` 设备/改 ID/OTA · `trajectory.js` MIT 轨迹回放 · `console.js` 裸帧收发（`buildConsole` :1，Enter 发送 :316）· `tests.js` 测试套件 recipe runner（7374 行）· `diag.js` 黑匣子配置 :10 · `guide.js` 使用指南 · `detection.js` 已下线（页面不再注册，文件仍在）。

**实施步骤（周期性发帧为什么不能用定时器）**:
1. `unthrottled-timer.js:3-14` 记录真机实证：页面 hidden / 窗口被遮挡时浏览器把主线程定时器节流，实测 `setTimeout(25)` 拖到 970ms，帧间隔越过固件 `0x4D` 看门狗 → **电机停转且锁存**；采样循环里圈数被钳还会产出"看似正常的假数据"。
2. 所以安全路径用本模块：Worker 定时器 `sleep(ms)` :59、`setUnthrottledInterval(fn, ms)` :101；或直接 `await` 链（`tests.js:11` 注释即此写法，:3167/:3241/:3350 `while(未到时限){发帧; await sleep()}`）。
3. 非安全路径仍留有 `setInterval`，只用于 UI 装饰或与发帧无关的轮询：`link-health.js:443`、`offline_detection.js:651/:756/:819` —— 改动前先确认它不涉及指令帧。

**验证方法**:
- 结构核对（本次实跑）：`ls frontend/js/pages/*.js` = 13 个文件；`PAGE_BUILDERS` 注册 12 个键（app.js:221-237）；`wc -l frontend/js/scope-bar.js` = 4418、`app.js` = 1654。
- UI 改动自验：按 `docs/skills/playwright_ui_self_test.md` 用**可见窗口**跑（军规 13 要求真实 GUI 路径，裸 API 不算）。
- 图表改动自验：必须让真实数据流起来看图（军规 4）——`tests/test_monitor_lifecycle.py` 需 8765 后端在跑；纯 DOM 断言与静态截图曾在"曲线不绘制"事故里全部正常。

**踩坑**:
1. **页面重建 = `root.innerHTML=""`**（`app.js:336-347`，FB-023），builder 一律自清；但清不掉 **module 级 setInterval 与 `store.on` 订阅**（`app.js:409-413`）→ 下线检测页专门建了 `pageCleanups`/`onPageRebuild`（`offline_detection.js:52-59`，:530/:677/:758 注册清理）。
2. **挂在 document 上的 `visibilitychange` 监听**，`innerHTML` 与 store 退订都够不着，必须显式退订：`motion.js:141-145`，注册/退订在 :3338/:3341。
3. **切页后 scope 失效**：`PAGE_PROFILE`（`scope-bar.js:257-285`）只在 profile 名变化时才 `setProfile`，同名页互切不触发 stop；motion 页重建要自己 destroy chart（`motion.js:561`）；**trajectory 的 profile 必须写 null**（:266-275），否则硬件连续流跟着页面跑，与回放帧 8:1 交织会硬关栅极。
4. **uPlot 初始化时机**：`scope-bar.js:3028 new uPlot`，`_render()` 末尾用 `setTimeout(() => _initChart(host), 0)`（:2735）等布局落位；同步补一发会被 `!host.clientWidth` 挡掉（:2731），别在外面再加同步调用。主题切换要 destroy + rebuild（:744-748），尺寸靠 ResizeObserver 同步（:703-714）。
5. **图表冻结排查**：RAF 合并重绘 + 1s 僵死看门狗（:1149-1213）、warn 锚点 :1333、`_diag` 计数器 :661-673，手册 `docs/skills/scope_chart_freeze_debug.md`；后台标签只计数不报警（:1254/:1314）。
6. **localStorage 谎报**：`Number(localStorage.getItem(k))` 在缺键时得 0，未连接也显示"设备 0"（`store.js:20-31` 有修复注释）；`setDeviceId(null)` 不得覆盖已有记忆（:165）；日志弹窗要主动取历史快照 `log.history()`（:191-193）。
7. **焦点/换格类交互**：订单号↔序列号调度 `offline_detection.js:416`、尺寸读数后 500ms 自动换格 :529-543、scope min/max 的 Enter+blur `scope-bar.js:3349`、抽屉 ESC 与遮罩共用一道闸（modal 在上）`app.js:770-808`。自动化提交用派发 keydown Enter，别用 Tab（本页 blur 会回滚未提交输入）。

**状态**: 已完成（页面清单/注册表/行号本次逐条 grep 实测；未在浏览器里跑交互回归 —— 开发机不连硬件，UI 行为需按验证方法自验）
