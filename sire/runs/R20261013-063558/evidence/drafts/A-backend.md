**日期**: 2026-10-13
**项目**: driverSoftware2（KingKong 感驱一体舵机 PC 上位机，@CODE_ROOT@\driverSoftware2；基线 VERSION 0.16.1 / 分支 feat/offline-detection-optimize / HEAD cf23634）
**取代**: K-REPO-DRIVERSOFTWARE-20260924（2026-09-24 的 v0.13.11 单段摘要，行号与规模已过时）
**关键词**: [driverSoftware2, 后端地图, server.py, FastAPI endpoint, reader_wrapper, reader_mp, reader_mp_worker, READER_MP, WEB_GUI_PORT, KK_READER, shared_memory, asyncio.Queue, 连接状态真相源, 双实现同改, HID独占, _conn_generation, ws monitor 空壳]

**需求场景 / 现象**: 在这仓新增或修改任何后端功能前，必须先回答四个问题：请求从哪个函数进、帧从哪个 reader 出、reader 有几份实现要同改、开发态与打包态差在哪。原仓内文档只讲规则不给入口，逐次重新摸清 server.py（11178 行）代价高。

**方案 / 架构（分层与数据流）**:
`Browser/Electron → HTTP/WS (FastAPI, 默认 127.0.0.1:8765) → server.py endpoint → core/commands.py (V2Commands) → core/reader_*（HID 或 libusb）→ USB → KingKong Analyzer → RS485 → STM32G473 驱动板`。
- **启动**: `server.py:11154 main()` 读 `WEB_GUI_HOST`(:11156，默认 127.0.0.1) 与 `WEB_GUI_PORT`(:11157，默认 8765) → `_bind_http_socket()`(:11089) 先占端口，**绑成功后把实际端口回写 `os.environ["WEB_GUI_PORT"]`**(:11161) 并写端口回执文件(:11163)，再 `uvicorn.Server(Config(app)).run(sockets=[sock])`(:11170)。刻意不用 `uvicorn.run(host, port)`：会二次 bind 产生 TOCTOU，端口被抢时回执与实际不符。`__main__` 前置 `multiprocessing.freeze_support()`(:11174)。
- **运行形态分叉**: `server.py:341` `_USE_MP_READER = os.environ.get("READER_MP", "1") not in ("0","false","False","")` → 1 用 `core/reader_mp.py`（**打包默认**，子进程独占 HID+GIL），0 用 `core/reader_wrapper.py`（`start.bat:10` 硬写 0，开发态）。单例 `backend = ReaderBackend()` 在 `server.py:352`。
- **路由规模**: `grep -c '^@app\.' server.py` = **160**。分组与定义行：连接 `/api/scan|connect|disconnect|state|params` :955/:1025/:1124/:1163/:1190；台架 `/api/bench/*` :1429-1717；报告 `/api/report/*` :2008-2086；链路诊断 `/api/probe_device_ids` :2095、`/api/auto_baud` :2162、`/api/diag/link_triage` :2236；硬件连续流 `/api/scope/*` :2643/:2776/:2837/:2865/:4040/:4087/:4144；外部扭矩真值 `/api/jn/*` :2959-3060、`/api/dyn200/*` :3012-3408；力感知 `/api/force_calib/*` :3269-3344、`/api/force_test/*` :3655-3689；命令 `/api/cmd/*` :4223-4247、:5024-5318、:5549-5810；回放与急停 `/api/mit/playback*` :4455-4766、`/api/estop/abort_work` :4727、`/api/comm_loss/*` :4841-5000；测量 `/api/measure/*` :5810-6532、`/api/self_test` :6077；标定 `/api/calibrate/*` :6884/:7560/:7810/:7971/:8018/:8177、pipeline :9767-9836；档案 `/api/fw_profile` GET/POST :8371/:8377；OTA :8393-8781；再标定 `/api/cmd/recal_*` :9268-9330；裸帧 `/api/raw*` :9425/:9439；Kt 与内圈零位 :9901-10031 / :9982-10017；**下线检测 `/api/offline-detection/*` :10148-10736**；黑匣子 `/api/diag/*` :10914-10987；`/api/changelog` :10776、`/api/meta` :11003。
- **WebSocket**: `/ws/monitor` :9470 的 `_monitor_loop` :9511 **首行 return，实际不推任何帧**（历史空壳，前端已删"监控中"标签）；真正在用的是 `/ws/calibrate/pipeline` :9852 与 `/ws/kt` :10756，模式为 worker 线程 → `asyncio.Queue` → `call_soon_threadsafe`（:9737/:9743、:9884/:9948），WS 取到终态即关（:9871-9875）。
- **连接状态单一真相源 = server.py 模块级全局** :352-404：`backend` / `cmds` / `device_id` / `baudrate` / `device_id_confirmed`(:377) / `_last_probe_alive`(:385) / `connected_serial`(:390) / `connected_port`(:394) / `_conn_generation`(:402，断链代哨兵，给无 worker 对象的长跑 closure 做协作式取消；有 worker 的走 `request_abort()`)。**刻意没有 state 类**，前端靠 `/api/state`(:1163) 拉。
- **进程间**: `reader_mp.py:9-12` SHM ring（SPSC 无锁）+ `mp.Pipe` 控制通道；`_rpc` 带 seq 回显防乱序 :317（详见 :318-361）；父端 drain 游标 `_local_read_idx` :96、`_shm_drain_iter` :556（落后超过 NUM_SLOTS 就跳尾 :564）；热换帧 `update_continuous_frame` :467、ACT 双 item `set_aux_frame` :489。子进程 `reader_mp_worker.py:195 reader_worker()` 必须 top-level（Windows spawn pickle，文件头 :5 说明），SHM 布局 header 8B + 1024×128B :14-22。

**关键文件与接口**:
- `server.py:227-268` core import 集中区；worker 类一律延迟 import：fullpipe :9728/:9731、kt :9881、inner_zero :9973、od_* :10317-10319、force_calib :3260/:3291。
- `core/reader_wrapper.py`(1346 行) in-process 形态：`ReaderBackend` :736、`_HidReader` :500（`hid.enumerate(VID,PID)` → `open_path` :509-514）、`_LibUsbReader` :598（pyusb 直通，USB jitter 低约 60%，:590-599）、`_make_reader` 优先 libusb 且 `READER_FORCE_HIDAPI` 可关 :718-731、线格式 `bus_config_item` :379 / `build_packet` :419 / `parse_packet` :438、多读取器会话绑定 `KK_READER` :43 与 `_kk_select` :50、`LinkDown` :204、`ensure_baud` :335。
- `core/reader_mp.py`(637 行) 多进程父端 `ReaderBackend` :85。
- `core/reader_mp_worker.py`(911 行) 子进程侧。
- `core/blackbox.py`(569) 诊断黑匣子单例 `bb`（`log` :236 / `blob` :373 / `export` :419 / 环与配额 :164），全 fail-open（文件头 :1-7）。
- `core/paths.py`(68) 源码态与打包态日志根分流；`core/serial_tap.py` 总线计数 tap。
- 环境变量清单：`READER_MP`(server.py:341)、`WEB_GUI_HOST`/`WEB_GUI_PORT`(server.py:11156-11157，回写 :11163，`core/force_calib_runner.py:72` 复用)、`READER_FORCE_HIDAPI`(reader_wrapper.py:727)、`KK_READER`(reader_wrapper.py:46,62)、`BENCH_DUAL_READER`/`FORCE_CALIB_SCRIPT`(force_calib_runner.py:96,500)、`KK_AUX_EVERY`/`KK_MIN_SOF_2ITEM`(reader_mp_worker.py:286,677)。

**实施步骤（怎么用这张地图）**:
1. 新加一个后端能力：先在上面 endpoint 分组里找最近的组，同组内加 `@app.*`，再进 `core/commands.py` 加高层 wrapper（协议层改动见同批 F 记录"协议层与固件档案门控"）。
2. 涉及 reader/总线时序：`reader_wrapper.py` 与 `reader_mp.py` **两份实现同时改**，用 `inspect.signature` 写测试钉住签名。
3. 打包态才复现的问题（管道乱序 / 子进程死 / 游标竞态）：本地显式 `set READER_MP=1` 再起服务。

**验证方法**:
- 结构核对（本次已实跑）：`grep -c '^@app\.' server.py` = 160；`ls core/*.py` = 39；`wc -l server.py` = 11178；`grep -n '_USE_MP_READER' server.py` = :341；`grep -n 'def main' server.py` = :11154。
- 起服务核对：`python server.py` 后请求 `/api/meta`(:11003) 与 `/api/state`(:1163)，端口取自回执文件而非配置文件。
- 双形态核对：`READER_MP=1` 与 `=0` 各起一次，`/api/scan` 均可列出读取器；`tests/unit/test_drain_guard.py:14-17` 断言 in-process 形态 `link.hot_iters` 恒 0。

**踩坑**:
1. **HID 全机独占**：一只 Analyzer 同时只许一个进程持有，其余实例只能当 HTTP 客户端；`import server` 有副作用即已抢占 HID（server.py:169-171 注释）→ 脚本别随手 import server。
2. **双实现接口改签名要两边同改**：`reader_mp.py:475-478` 注释实录 2026-09-22 只改 wrapper 未跟 MP 签名，结果每次热换帧 `TypeError` → HTTP 500。
3. **`hid.enumerate` 顺序不稳**：散落几十处的 `keys()[0]` 会抢错机器/错总线，选择逻辑收口在 `reader_wrapper.py:43-50` 与 `reader_mp.py:108`。
4. **`/api/scan` 的 serial 是固件编译时间戳，会撞键**（server.py:955-957）→ 真机台账另用读取器 USB 序列号做主键。
5. **`/ws/monitor` 是空壳**：按它做过"监控中"状态会永远不动；实时数据走 REST + `TELEMETRY_DISPATCH`（见前端地图记录）。
6. `AGENTS.md:321` 写"打包版默认 `READER_MP=1`（多进程 reader, `server.py:212`）"—— 该分叉现已迁到 `server.py:341`，文档行号过时；引用行号前先 grep。

**状态**: 已完成（静态勘察 + 全部行号本次逐条 grep 实测；未运行服务与真机，开发机常态不连硬件）
