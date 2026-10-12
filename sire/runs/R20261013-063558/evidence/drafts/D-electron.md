**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，electron/ 壳，package.json 版本 0.16.1）
**关键词**: [Electron 壳, electron/main.js, startBackend, server.exe, resources/server, PORT_PINNED, 端口回执文件, killStrayBackends, backgroundThrottling, contextIsolation, nodeIntegration, devTools 客户包关闭, Menu.setApplicationMenu, kkdiag://, did-fail-load 重试, postmortem, diagnose.js, extraResources, 无 preload 无 IPC, user agent Electron]

**需求场景 / 现象**: 桌面版和浏览器版行为不一致（切窗口后电机停转、devtools 能不能开、端口被占怎么办），或改了后端启动方式要确认壳侧是否跟上。需要壳与后端进程的关系图。

**方案 / 架构（壳只管三件事：拉起后端、拿真实端口、开窗口）**:
- **拉起后端**：`electron/main.js:144 startBackend()`。打包态 spawn `process.resourcesPath/server/server.exe`（:150-167，windowed 无 console，日志重定向到 `userData/server.log`，:160 注释说明不弹黑窗）；开发态用 `py -3.12 server.py`（:185-203，路径解析注意含空格的 `C:\Program Files\…` 会踩坑，:200 注释）。启动前先 `killStrayBackends()` 清理残留（:87）。
- **端口获取**：`PORT_PINNED = !!process.env.WEB_GUI_PORT`（:28）—— 只有人为钉住端口才信任它；否则**由 server 自绑后把实际端口写进回执文件**，壳读文件拿端口（:99-135，注释解释了"为什么是文件而不是 stdout"）。这与后端记录里 `server.py:11161` 回写 `WEB_GUI_PORT` 是同一条链的两端。
- **窗口与安全**：`new BrowserWindow`（:1083），`contextIsolation: true`（:1092）、`nodeIntegration: false`（:1093）、`devTools: !customerBuild`（:1094，客户包关掉后 F12 与 openDevTools 都是空操作）、**`backgroundThrottling: false`**（:1105；:1095-1104 是真机 id4 实证注释：后台节流会让运动页软轮询的 MIT 帧越过 `0x4D` 看门狗 → 停机，关掉后窗口被遮挡帧照发）。`closed` 监听必须**紧挨构造点**挂（:1109-1119），留到函数尾部会漏掉早期退出路径。菜单：`Menu.setApplicationMenu(null)`（:1127，条件见 :1126）。外链与新窗口一律拦（:1133 `setWindowOpenHandler`，同时截 `kkdiag://` 自定义协议用于"打开诊断包"）。
- **加载与容错**：`did-fail-load` 自动重试（:1147，注释：后端未就绪时单次 loadURL 会永久黑屏；策略是等后端最多 40s 再 loadURL），首次 `mainWindow.loadURL(BACKEND_URL)`（:1217）；后端起不来时 `showBackendFailurePage()`（:1110 附近两处早退）；运行期崩溃走提示而不是换页（:941，换页会毁掉用户当前页面状态）；崩溃后置诊断页见 `electron/postmortem.js`（自检 `postmortem.selftest.js`），诊断入口 `electron/diagnose.js`。
- **前端对壳零感知**：**没有 preload、没有 IPC 通道**（`frontend/js/pages/motion.js:158-172` 注释明确），页面只用 UA 里的 `" Electron/"`（带前导空格）判形态。好处是同一份前端在浏览器与桌面下通用，代价是壳不能给页面传能力。

**关键文件与接口**:
- `electron/main.js`(1273 行)、`electron/diagnose.js`、`electron/postmortem.js`、`electron/postmortem.selftest.js`、`electron/installer.nsh`、`electron/assets/`。
- `electron/package.json`：`version` :3（与根 `VERSION` 由 `scripts/release.py` 同步）；`build` 段 :16-60，`files` **只带 4 个壳文件**（:22-27：main.js / diagnose.js / postmortem.js / package.json），`extraResources` 把 `../dist_app/server.dist` 拷成 `resources/server`（:28-33）——**所以前端文件不在壳里，随 server.dist 走**；这条打包装配的完整后果（复用旧 dist 会把旧前端发出去）见记录 F-057，本条只登记壳侧配置。win 目标 nsis+zip（:34-40）、mac 目标 dmg+zip（:41-45）。

**实施步骤（改壳相关需求时的检查顺序）**:
1. 需要新能力给页面用 → 优先加后端 endpoint，不要开 IPC（前端零感知是既有约定）。
2. 改后端启动方式（入口文件名、端口策略）→ 同步看 `main.js:144/:150/:99-135` 与 `server.py:11154-11170`。
3. 改窗口选项 → 确认 `backgroundThrottling` 与 `devTools` 两行没被动（前者是真机事故换来的）。
4. 打包相关 → 见 F-057 的 `build.bat` 步骤与 `extraResources` 链路。

**验证方法**:
- 本地起壳：`cd electron && npm install && npm start`（AGENTS.md 开发流程），观察窗口是否可见、后端日志落在 `%APPDATA%/…/server.log`。
- 端口策略核对：占用 8765 后启动，壳应读到回执文件里的实际端口而不是失败。
- 后台节流核对：运动页使能电机后把窗口最小化/遮挡，帧应继续发（`backgroundThrottling: false` 生效）；浏览器形态则必须靠 `unthrottled-timer.js`（见 F-055）。

**踩坑**:
1. 用户可见验收必须走真实 GUI（军规 13）；headless Playwright 跑通只能写"底层链路通过"。
2. `dist_app/server.dist` 是**共享产物目录**：壳只引用它，本地若跳过 Nuitka 直接复用上次 dist，前端修复不会进包（`AGENTS.md` 军规 2 记录了曾有 `build-electron.bat` 走这条错路并已删除）。
3. 构建脚本里 `for /f (' … ')` 内层命令的 `=` 与 `>` 必须 `^` 转义，否则 cmd 吃掉解析（`build.bat:92` 一带的 sha 取值）。

**状态**: 已完成（main.js / package.json 行号本次逐条读文件实测；未实跑 `npm start`，也未打包验证）
