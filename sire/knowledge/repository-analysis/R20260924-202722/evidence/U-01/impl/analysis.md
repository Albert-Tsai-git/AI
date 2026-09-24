# U-01 分析：analyzer_code / driver / driverSoftware / recalibration

执行中：只读分析四个仓库及 recalibration 的四个 Git 子模块。
执行完毕：完成；未改仓库或数据库，未运行构建、测试或设备操作。

## analyzer_code
- 基线：HEAD `c6bf7e7d0551a6d7a0af53641a931dafc096d24c`，detached、干净；Nuvoton M487/M480 Cortex-M4 USB 分析仪桥接固件。
- 入口 `main.c:105-154` 初始化后进入 `AnalyzerLoop()` 与 `USBLoop()`；USB 帧收发/分派在 `USB/usb.c:168-211,273-355`，设备命令在 `Devices/analyzer.c:179-187`。支持分析仪与 RS485/RS422、BiSS/SSI 编码器。
- Keil uVision 工程 `Analyzer.uvprojx`，目标 M487SIDAE/ARMCC；未发现标准 README、CI 或自动测试门禁。driverSoftware 和 EncoderPlotter 经 Analyzer 访问硬件，分析仪协议存在跨仓重复维护。
- 限制：构建工具链和设备路径未验证；不索引 IDE 日志、SDK 派生实现及构建产物。

## driver
- 基线：HEAD `af0abcb4b86d613a81e8ee0835a08746b2251d66`，detached，v3.4.6；存在未跟踪 `.idea/`。STM32G473QETx BLDC/伺服固件，含 APP、Bootloader、编码器算法接口和工具。
- APP startup: `Core/Src/main.cpp`; USART1 RS485/DMA/CRC command dispatch: `Core/Src/register_protocol.cpp:60-185`; FOC/current/PWM/safety logic is under `Core/Src/`; boot/OTA constraints: `Boot/README.md:1-67`. Keil project `MDK-ARM/driver.uvprojx` has an after-build path through `extract_full.py` that produces `release/driver.bin` and `BUILD_INFO.txt`; static path only, build not run.
- `requirements.txt` 含 Python 工具依赖；`tests/` 混合主机侧单测、工具测试和需接硬件的脚本。`docs/system_architecture.md` 仍保留旧 GUI/提交标记和部分过时内存/中断说明，复核硬件地址以当前 scatter、源码和 map 为准。
- `Core/Src/system_init.cpp:10-51` 首次运行可修改 DBANK Option Bytes 并重启，属硬件敏感路径；本次未执行。忽略 IDE、Objects/Listing、报告、二进制与测试采集输出。

## driverSoftware
- 基线：分支 `feature/offline-detection-dev`，HEAD `6e09c7688c5eec51671c9cc83c09d416ea2abedb`，干净；`git describe` 为 `win-smoke-v0.14.0-beta.1`，而根 `VERSION` 与 `electron/package.json` 是 `0.13.11`，发版前须确认版本来源。
- 当前操作员桌面端：FastAPI 后端 + ESM 前端 + Electron。入口 `server.py:635-665` 创建服务，REST/WebSocket 路由约 `:953+`；前端 API 在 `frontend/js/api.js`；设备协议/命令在 `core/protocol.py`、`core/commands.py`；Analyzer reader 隔离在 `core/reader_mp.py`，备选 wrapper 在 `core/reader_wrapper.py`；标定管线在 `core/fullpipe_worker.py`，固件配置在 `core/fw_profile.py`。
- 通信链：Electron/前端 → FastAPI → reader/HID → Analyzer → RS485 → driver 固件。构建由 `scripts/build.bat` 调用 Nuitka 与 electron-builder；`pytest.ini` 限定 `tests/unit`，硬件脚本需另行连接硬件运行。依赖清单要求 Python 3.12，并有 Windows cp312 算法 wheel。
- README 与当前源码结构有局部漂移；按源码核对入口。不要索引 `.env`、本地 venv、日志、dist、算法 wheel/npz 等大产物；只收稳定源码和固件配置/协议说明。

## recalibration 及嵌套子模块
- 基线：分支 `feature/debug-from-file`，HEAD `b9f73c5fa6f7b0534fa9e298a7281ed8d9320646`；root 状态 `M sub_algorithm`。父仓 gitlink 固定 `sub_algorithm=f8eee4a`，当前检出 `a3c7526`，不匹配；其他三个检出 SHA 匹配 parent pin。
- `RecalibrationV0_4.py:7-24,28-114` 组合 Analyzer、encoder 与标定算法，执行在线采集/生成/写入/读回；`debugFromFile.py:22-55,74-105` 重放本地调试数据。算法流程见 `sub_algorithm/docs/calibration/README.md:21-24`，算法子仓有 pytest；本次不运行。
- 子模块职责：`sub_algorithm` 标定/角度计算；`sub_common` 结构、协议、日志和配置；`sub_embedded` Analyzer/设备通信、IAP；`sub_automation` 环境设备/气泵。入口接口由 root `Encoder.py:13-26` 组合，具体实现如 `sub_embedded/Analyzer.py`、`DriverBase.py`。
- 静态风险：当前算法检出 `step4_GenerateV4060.py` 导入 `sub_common.dpbFlashLayout`，但目前 common 检出没有该文件；受影响算法路径未运行验证。`sub_algorithm` gitlink mismatch 足以造成父仓快照不可复现。调试 ZIP、加密模板、venv 和生成图形输出不得索引。

产物：本分析稿；来源路径与 Git 元数据。
验证：审阅者复核 Git 基线、关键入口和子模块不匹配；功能验收由 U-01 QA 记录。
阻塞：无。
