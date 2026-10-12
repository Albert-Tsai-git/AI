**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，分支 feat/offline-detection-optimize，HEAD cf23634，基线 v0.16.0 首发 / v0.16.1 当前 VERSION）
**关键词**: [下线检测, offline detection, 产线出厂检测, OfflineDetectionController, require_step, DetectionType, 外观检测, 尺寸测量, 反驱力, 信息确认, 噪声, 额定扭矩, 坏点, MAX_PLAUSIBLE_NM, 卸力建零, ZERO_MIN_SAMPLES, 出力准备闸, prepareGate, prepare_delay_s, od_motor, od_sensor, od_rated_torque, od_reverse_force, od_profiles, od_relay, DYN-200, JN-DN5, 485 继电器, duoji 口径, 判定在后端, 人工决定]

**需求场景 / 现象**: 下线检测是产线逐台出厂质检功能（v0.16.0 首次上线，本分支正在按产线参考实现 duoji 的口径逐条对齐）。改动时最常见的三类问题：判定口径抄错来源、采集防呆漏一条、状态机门控被绕过。后续接手需要一页看懂模块分工与口径出处。

**方案 / 架构**:
- **流程**：八步 = ①产品序列号（**会话主键**）→ ②外观 ③尺寸 ④反驱力 ⑤信息确认 ⑥噪声 ⑦额定扭矩（六个检测项，前端 `ITEMS` 常量逐个列出，`frontend/js/pages/offline_detection.js:21-28`）→ ⑧汇总存档。**强顺序门控**在后端：`core/offline_detection.py:739 require_step()` —— 前一项没做完不许做下一项；单会话约束 :721；不合格时由操作员决定继续或结束 `decide()` :758；结束 `finish_session()` :793（检测表要求每台都落盘，文件头 :12）。
- **判定一律在后端**（`core/offline_detection.py:11` 明示"前端只负责采集入参与展示，不参与 PASS/FAIL 计算"）；状态枚举 `DetectionStatus` :31（PENDING/RUNNING/PASSED/FAILED/ERROR）、检测项枚举 `DetectionType` :39-45；判定函数 `judge_*` :319-494；结果模型 `DetectionResult` :527；会话模型 `OfflineDetectionSession` :557；控制器 `OfflineDetectionController` :717。配置读写 `load_config` / `save_config` / `validate_config` / `migrate_legacy_*` :132-295，**阈值/名义值/期望版本全部走 config.json，产线可在界面改**。
- **采集侧模块分工**（口径一律注明"同 duoji"以便回溯来源）：
  - `core/od_motor.py`(64)：出力前使能序列 —— 清故障 → default 模式 → 软复位 → 等 `RESET_BOOT_WAIT_S = 0.8s`（:18，duoji 实测 0.5~0.8s）→ 再 default；`ENABLE_ATTEMPTS = 2`，**复位无应答就整套重走**（commit cf23634 的用例口径）。
  - `core/od_sensor.py`(83)：DYN-200 / JN-DN5 外部扭矩传感器的**只读**适配，绝不启停传感器、绝不动全局去皮（文件头 :5-10）；卸力建零 `:26` = 静置原始读数排序、去两头各 20% 取平均（同 duoji `_auto_tare`）。
  - `core/od_reverse_force.py`(235)：`ReverseForceRunner` :38 分阶段采集，断电手转、正向取最大 / 反向取最小；`MAX_PLAUSIBLE_NM = 200.0`（:27，量程外读数丢弃且**不计入传感器掉线**，即"坏点"）、`ZERO_MIN_SAMPLES = 5`（:28，建零读数不足直接报错）。
  - `core/od_rated_torque.py`(240)：`measure()` :113 堵转工装上给前馈力矩持续 `duration_s`，**实测取外部传感器真值，舵机回读仅备查**（文件头 :1-3）；过流 / 过温（>90℃）/ 报故障即停的异常路径 :38-70；同样带 `ZERO_MIN_SAMPLES = 5` :33。
  - `core/od_profiles.py`(228)：判定标准命名方案 —— 多方案存 / 切 / 导 / 删 / 另存（文件头 :1）。
  - `core/od_relay.py`(294)：`OdRelay` :85，485 Modbus 继电器控制工装通断。
  - 注：`core/od_torque_recorder.py` 已删除（本分支实际 `ls` 确认不存在）。
- **后端装配**：`server.py:10148-10736` 是 `/api/offline-detection/*` 全家桶（config/session/开始/下一项/判定/人工决定/导出），装配区 :10092-10343，`from core import od_motor, od_rated_torque, od_sensor` 在 :10317，噪声空载运转 :10525，额定扭矩采集入口 :10590。
- **前端**：`frontend/js/pages/offline_detection.js`(1312 行) `buildOfflineDetection` :58，卡片式八步（:83-91）；**出力准备倒计时闸门** `prepareGate()` :789-826（倒计时中可"立即开始"或"取消"，配置项 `rated_torque.prepare_delay_s` 见 :1208）；订单号↔序列号焦点调度 :416、尺寸读数 500ms 自动换格 :529-543；页面级定时器清理 `pageCleanups` / `onPageRebuild` :52-59。API 封装 `frontend/js/api.js:259-287`（`od*` 一族）；档位 `capabilities.js:35 "page:offline-detection": 2`；导航 `index.html:127` 与 :169；注册 `app.js:26` import + :231 builder。
- **门禁**：`tests/unit/test_od_*.py` 共 **11 个**文件（`pytest.ini` 限定 testpaths=tests/unit）。

**口径速查（别自己发明）**:
- **坏点** = 量程外（±200 N·m）读数丢弃，且不算传感器掉线。
- **建零（卸力零点）** = 静置读数排序去两头各 20% 取平均；新读数 <5 个直接报错，不能沿用旧零点。
- **反驱力** = 断电手转，先正转后反转，正向取最大值、反向取最小值，分段极值判定。
- **额定扭矩** = 堵转工装 + 前馈力矩持续一段时间，实测真值来自外部传感器。
- **出力准备闸** = 额定扭矩/噪声出力前先倒计时（可跳过），避免操作员手还在工装上。
- **噪声使能失败** = 软复位无应答时整套使能序列重走一次（两次尝试），不能谎报使能成功。

**实施步骤（新增一个检测项时）**:
1. `core/offline_detection.py` 加 `DetectionType` 成员 + `DETECTION_NAMES` + `judge_*` + DEFAULT_CONFIG 项；
2. 若需要采集过程，新建 `core/od_xxx.py`，口径注明同 duoji 的哪个函数；
3. `server.py` 在 :10148-10736 段内加 endpoint 并接入 `require_step` 门控；
4. `frontend/js/api.js` 加调用、`offline_detection.js` 的 `ITEMS` 加卡片；
5. `tests/unit/test_od_*.py` 补门控与判定用例；CHANGELOG `[未发布]` 写一句白话。

**验证方法**:
- 判定与门控：`venv\Scripts\python -m pytest tests/unit -q -rs -k od`（11 个 test_od_* 全绿）。
- 界面：按军规 13 走**可见 GUI**（Electron 正式界面或浏览器可见窗口），路径 = 打开下线检测页 → 连设备 → 逐八步 → 观察不合格时的人工决定与结束存档。
- 状态一致性：改完核 `CHANGELOG.md:17` 起的 `[未发布]` 段（本次实测 23 条：变更 13 / 新增 6 / 修复 4），别把已生效行为写成"待发布"。

**踩坑 / 限制**:
1. **duoji 是产线在跑的扭矩质检上位机，口径可对，实现别整抄**（本仓项目记忆已记：坏点处理就有差异）。
2. **传感器只读**：下线检测不许启停 DYN-200/JN-200 传感器、不许改全局去皮值。
3. 页面重建会留下脱离文档的旧 DOM 轮询：任何 `setInterval` 都要注册进 `onPageRebuild`（:530/:677/:758 是既有例子）。
4. 采样节拍必须**严格晚于 now**（commit 60d0be8：节拍早于 now 导致满速刷帧死循环）。
5. 通讯延迟后**跳过错过的节拍**而不是连续补帧（commit 4dabd5c）。
6. 信息确认不合格才进入人工决定，通信读取失败仍应报错重试，不要伪装成"不合格"（与 F-052 的边界）。
7. 本分支 commit 主题多为"对齐 duoji 口径"，`git log --oneline -30` 计数：`fix(下线检测)` 12、`feat(下线检测)` 9、`test/refactor(下线检测)` 各 1、其它 `fix/feat/docs` 7。

**状态**: 部分完成 —— 结构与口径已核实（行号本次逐条读文件实测）；功能本身仍在开发分支，**未做真机验收**，`win-smoke-offline-detection` 这类冒烟 tag 名在 `.gitlab-ci.yml` 里查无同名 job（别假设存在）。
