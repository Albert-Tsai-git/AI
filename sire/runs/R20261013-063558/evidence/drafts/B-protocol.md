**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**取代**: K-REPO-DRIVERSOFTWARE-20260924 中与协议/寄存器相关的过时部分
**关键词**: [RS485 协议, protocol.py, Cmd, FactoryCmd, crc16, make_frame, commands.py, V2Commands, FwProfileUndetermined, registers.py, register_protocol.h, register_descriptions.py, fw_profile, firmware_profiles, 档案门控, 静默回退, 0x38 内圈零位, 停机写, 慢命令 0xFD, RS485 V3.3, 新加协议命令, recal_chain, 算法不许第二份]

**需求场景 / 现象**: 改任何一帧报文、一个寄存器地址、一条标定流程前，需要知道：帧格式在哪一层拼、寄存器地址的单一来源是谁、固件能力档案缺失时会发生什么、以及新增一条命令要动哪几个文件。这仓最容易出的事故是"静默回退旧路径不报错"和"手填档案值"。

**方案 / 架构（四层）**:
1. **帧层** `core/protocol.py`(337 行)：`class Cmd` :16 只是常量集合，**只有 5 个命令值**（DEFAULT/MIT/CLEAR_FAULT/RESET/FACTORY），V3.2 帧字段定义与 head byte 说明在 :17-36（`[ID:4 | T:1 | CMD3:3]`，T=bit3 为 1s 看门狗位，广播 0x0F 已于 V3.1 删除）；`FactoryCmd` 子命令 :49、`ReCalCmd` :71、`ReCalMem` :90、`STATE_NAME` :100、`FAULT_BITS` :126、`INTERNAL_FAULT_BITS` :142、`crc16` :243、`make_frame` :255、`head_byte` :261、`parse_frame` :302。
2. **命令层** `core/commands.py`(1642 行)：`class V2Commands` :204 是唯一对外门面。出入口收口在三个私有方法 —— `_send` 单帧同步 :285、`_send_mit_frame` :356、`_boot_send_raw` :1117、`_recal_send` :1288；其上按域分方法：运动 :454-530、寄存器 :497-620、慢命令 :635-847、boot/OTA :1076-1286、ReCal flash :1311-1636。`CmdResult` :26、`StatusSpec` :153、`FwProfileUndetermined` :98、MIT 缩放同步 `sync_mit_scales` :221。
3. **寄存器层**：`core/registers.py`(402 行) 文件头 :1-5 声明自己是固件 `Core/Inc/register_protocol.h` 的 **Python 镜像、单一来源**，改固件时同步改它；`core/register_descriptions.py`(526 行) 是与固件版本**无关**的语义描述表（单位/权限/说明），按名字 join，静态对表工具 `tools/check_register_descriptions.py` 是 build.bat Step 0 的硬门禁（scripts/build.bat:121-125）。
4. **能力档案层** `core/fw_profile.py`：档案目录 `PROFILE_DIR = <repo>/firmware_profiles`（:16），按固件版本 v3.3.0–v3.4.7 存 `dev-<sha>.json`；缩放值在 `set_active()` 时预计算成模块级 float，热路径只读 `_SCALE_*`（:7-10）。**门控行为**：任何依赖档案的调用在 `fw_profile.get_active() is None` 时 `raise FwProfileUndetermined`（server.py:3784-3794、:3845、:3935），异常处理器在 server.py:851；档案缺失则**静默回退旧路径、不报任何错**（AGENTS.md 军规 9）。

**协议 V3.3 相对 V3.2 的关键变更**（`docs/protocol/rs485_v3.3.md`，当前文档版本；host 代码仍是 V3.2，证据在 `core/protocol.py:17` 文档字符串 —— 注意 `docs/protocol/README.md:30` 与 `rs485_v3.3.md:22-44` 都没写这句差异说明，别照着找）：
① 物理层删除"字节间空闲 <8bit 用于帧定界"；② 表 1/表 2 增加显式类型列（uint8/int16/int32/f32）；③ **发送帧取消 14-15 字节的 `n` 计数字段**，改为"14 起放 n 个地址、个数由帧长决定"，总长 `14+n+2`；④ 接收帧总长 `12+4n+2`；⑤ Fault 明确为按位 uint8；⑥ 文档头部新增 v3.4+ MIT 刻度对照块（θ 2²⁴/2π 输出端、ω 512、τ 2048）并记录 Kp/Kd 的 10000 误填事故，配套门禁 `tests/unit/test_fw_profile_mit_scales.py`；⑦ 0x0B 示例改 v3.3.0；⑧ 0x36 改为"标定写入勿手改，改转向见 0x68"；⑨ 新增 0x68 输出转动方向、0x69 LED 开关；⑩ CRC16 参考实现指向上位机 `protocol.py::crc16()`（README:28）。协议版本源 = 固件 git tag，经寄存器 `0x0B` 映射。

**关键文件与接口**:
- `core/inner_zero.py`(570)：reg 0x38 内圈零位。手动 `InnerZeroSession` :223（`start` :247 / `_run` :294 / `status` :326，数据源是 ReCal 0x48）；自动 `collect` :467 + `analyze` :404；分箱 `Store` :156；算法 `compute_fix` :108、`write_gate` :136（MIN_BINS/DENSITY/SPAN 三道闸）；**写后必复位** `reset_and_wait` :541；硬约束注释 :372-376（运行时写 0x38 会留下 +86° 残差，必须先停机）。
- `core/fullpipe_worker.py`(1520)：一键再标定 P1-P10 后台线程（文件头 :4-6 记录 2026-05-28 从 PyQt6 QThread 剥离），事件契约 :12-19，`FullPipelineWorker` :141、`run` :693、`_run_pipeline` :731、标定看门狗仲裁 `_arm_calib_watchdog` :551 / `_restore_watchdog` :600、P5 采样质量 :274-409、`request_abort` :413。
- `core/recal_chain.py`(321)：**纯计算已抽出的唯一一份**，文件头 :8-12 明令"不许另起第二份算法"；同类收口还有 `core/force_calib_runner.py:5-9`（把台架脚本当子进程跑，不复制算法）与 `core/report_conclusion.py:3-6`。`core/algo_compat.py:1-8` 是 numpy≥1.20 垫片。
- `core/registers.py` / `core/register_descriptions.py` / `firmware_profiles/*.json` / `tools/gen_fw_profile.py`（档案只能由生成器产出，手填必错）。

**实施步骤（新增一条协议命令的落地顺序，AGENTS.md 开发流程的可核对版本）**:
1. 固件侧先加（属固件仓 `@CODE_ROOT@\driver`，分支 `v3_AI_Develop`，定论文件 `Core/Inc/register_protocol.h`，见 docs/PROJECT-CONTEXT.md §2:101-120）；
2. `core/protocol.py` 加 `Cmd`/`FactoryCmd` 常量；
3. `core/commands.py` 在 `V2Commands` 加高层 wrapper（走 `_send`，别自己拼帧）；
4. `core/registers.py` 加地址 + `core/register_descriptions.py` 加语义（再跑 `python tools/check_register_descriptions.py`）；
5. `server.py` 加 endpoint（放进已有分组）；
6. `frontend/js/api.js` 加调用 → `frontend/js/pages/*.js` 接 UI。
每一步单独 commit（仓规）。固件能力有变化的，还要用 `python tools/gen_fw_profile.py --rev <sha>` 生成档案。

**验证方法**:
- 行号核对（本次已实跑）：`grep -n 'class Cmd' core/protocol.py`=16；`grep -n 'class V2Commands' core/commands.py`=204；`grep -n 'FwProfileUndetermined' core/commands.py`=98；`grep -n 'PROFILE_DIR' core/fw_profile.py`=16；`grep -n 'def reset_and_wait' core/inner_zero.py`=541。
- 档案门控核对：裸 API 连设备**必须先发一次 `read_version`**，否则档案未确定，MIT/Default 帧被守卫拦下；两查 `/api/cmd/read_version` 的 `fw_git_sha` 与 `/api/fw_profile` 的 `active`（军规 9 推论）。
- 刻度正确性：`pytest tests/unit/test_fw_profile_mit_scales.py`；区分同名数值 —— 10000 是 Kp/Kd 量化 scale，不是 pos/vel/tau 刻度。

**踩坑**:
1. **慢命令改 flash 必须 `state == kStopped`**，否则固件回 `0xFD` 一个字节都不写（`core/commands.py:611-617` 实录固件分支）；改 device ID 同理 :1024。
2. **写零位要停机、写完要复位**（`core/inner_zero.py:372-376`），运行时写残留 +86°。
3. **档案值只能生成不能手填**：手填把 10000 当 pos 刻度填进去过，酿成力矩无响应事故（H-004 第 2 条）。
4. **寄存器排查要符号名 + 字面量双搜**（军规 12）：只搜 `kCfgMaxVoltage` 会漏掉直写的十进制 `60`。
5. **别复制第二份算法**：`recal_chain.py:8-12` 之所以 verbatim 迁移，就是为了让标定产物字节级可复现；动它等于动发布物。

**状态**: 已完成（行号与 V3.3 差异逐条 grep/读文档实测；未连真机验证任何协议行为）
