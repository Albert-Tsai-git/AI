**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**关键词**: [文档地图, docs/skills, 必读, AGENTS.md, PROJECT-CONTEXT, 缺陷池, 需求池, 飞书多维表格, base token, 待回归, 回填, 真机台账, 读取器 serial, workspace.json, 逻辑名, 不引用项目外路径, onboarding, lark-cli PATH, playwright_ui_self_test, scope_chart_freeze_debug, realmachine_fault_injection, inner_zero_calibration, recal_production_workflow, ANALYZER_HARDWARE_GUIDE, reader_issues, rs485_v3.3, gui-design, theme-servo-cyan, CHANGELOG 体例, 文档引用不实]

**需求场景 / 现象**: 本仓的"知识"分三层放在仓内（`AGENTS.md` 讲怎么干活、`docs/PROJECT-CONTEXT.md` 讲活从哪来回哪去、`docs/skills/` 讲具体工法），但缺一张能检索的目录：改某个模块前该读哪份、某条缺陷回填哪四个字段、真机台账用什么做主键，每次都要重新翻。另外这些文档之间的交叉引用有失效项，照着走会扑空。

**方案 / 架构（文档三层与分流判据）**:
- `AGENTS.md`（仓根）：硬规定 + 模块→必读 skill 映射表（:170-178）+ 工程军规（:214 起，含分支命名表、发版对账三件事、真机验收必须走可见 GUI）。
- `docs/PROJECT-CONTEXT.md`：协作上下文。§0:8 就给出"新信息该写到哪"的分流判据 —— A 指针 / B 台账 / C 工法 / D 本机配置。
- `docs/skills/`：工法手册，共 **13 份**（见下表）。
- `docs/` 顶层 17 份 md 各管一事：`ONBOARDING.md` 新机接手清单、`PACKAGING.md` Nuitka+Electron 打包、`gui-design.md` 界面设计决策、`theme-servo-cyan.md` 主题令牌（`frontend/css/tokens.css:3` 认它为单一真相源）、`feedback_ledger.md` 反馈分诊台账、`rs485_protocol.md` **已过期**（只是指向 `docs/protocol/` 的迁移指针）、`audience_tiering_proposal.md` 受众分层 L1/L0、`ci_release_migration_proposal.md` 发布迁 CI（已拍板）、`firmware_dev_versioning_coordination.md` 联调固件识别（FB-011）、`macos_support.md`、`ota_cfg_schema_migration_todo.md`、`reader_autonomous_scheduling_todo.md`（未动手）、`ui_test_cases.md` 界面验收资产、`algorithmic-philosophy.md` / `brand-philosophy.md`、`bai_sync_0726_review.md`。
- `docs/` 子目录 8 个：`protocol/`（协议按版本）、`skills/`、`reports/`（实测报告 + `reports/auto/*.json`）、`parking/backlog-2026-08-03.md`（悬项）、`superpowers/{plans,specs}/`（13+12 份历史设计稿，2026-07-05→09-22）、`traj_samples/*.csv`、`archive/server.spec`、`_rendered_test_suite_guide/`。

**docs/skills 13 份与"改什么前必读"**:
| 文件 | 讲什么 | 必读场景 |
|---|---|---|
| `ANALYZER_HARDWARE_GUIDE_V2.40.md` | 分析仪硬件与 USB 通道 V2.40 | 动 `core/reader_*` |
| `ANALYZER_HARDWARE_GUIDE_V2.30.md` | 旧硬件对照 | 排查老读取器 |
| `ANALYZER_PROTOCOL_SPEC.md` | 分析仪 USB 协议 | 帧格式 / 通道语义 |
| `reader_hid_v240_migration.md` | V2.40 迁移记录 | 动 reader |
| `reader_issues.md` | reader 已知坑 | 动 reader |
| `recal_production_workflow.md` | 再标定产线流程 | 动 `core/fullpipe_worker.py` / `recal_chain.py` |
| `encoder_calib_wheel.md` | 编码器标定轮 | 同上 |
| `inner_zero_calibration.md` | 内圈零位 0x38 | 动 `core/inner_zero.py`：**停机写、写完复位** |
| `foc_test_params_cookbook.md` | FOC 测试参数 | 力矩/速度试验 |
| `kkdiag_usage.md` | 诊断包拆解 | 处理 `diag_*.zip` |
| `realmachine_fault_injection.md` | 真机造障 | 真机验收的异常路径 |
| `playwright_ui_self_test.md` | 自驱 UI 测试 | **任何 UI 交互改动** |
| `scope_chart_freeze_debug.md` | Scope 卡死调试 | Scope 相关 |

**协作上下文（按行号取用）**:
- §1:23 活从哪来。§1.1:25 **缺陷池 = 飞书多维表格**，base `NbzHbFv86araNbsj8pwcx97ynKf`（:27）、表「02测试缺陷管理」（:44）；修完回填**四个字段**并把缺陷状态改成**待回归**（:29-36：缺陷状态 / 修复版本 / 根因 / 解决方案）。§1.1.1:38 **动手前先把这条单子的附件列一遍**（诊断包 > 复现步骤 > 截图 > 读代码推理）。§1.2:64 **需求池**也是多维表格，表名「待开发的问题及需求汇总」，响应后回填**进展 / 实现版本 / 备注**（:68）。§1.3:70 表格操作：`lark-cli base +record-list --base-token <…> --table-id <…>`（:44），参数是 **`--base-token` 不是 `--app-token`**（:335）。§1.4:74 结论**在与用户对话里交付**（发群模式已废弃）；§1.6:89 两组对接群只用于问缺陷疑问，发言需 gaoxing 审。
- §2:101 相邻仓库：固件仓 = `gitlab.kingkong.tech:embedded/driver.git`，分支 `v3_AI_Develop`（:107），定论文件 `Core/Inc/register_protocol.h` 等（:112-120）；§2.2:122 固件机理速查（排查前先过一遍，别把机理当 bug）。
- §3:187 诊断包与私钥（私钥不在仓内，见 `~/.kingkong_driver` 与 F-025 的取用流程）。
- §4:196 **真机台账**：§4.1:200 台账实体=台架，**主键=读取器 serial**（`/api/connect`、`/api/state` 返回的 `serial`，:213；总线 id 会漂不可信）；舵机 SN = reg `0x01 kStSerialNumber`（:214，不少设备没烧故读回 None）。§4.2:222 已知台架清单（:224-229，本机可见两条读取器 serial）。§4.3:246 真机操作纪律（白名单 + 写后必复读）。
- §5:258 **本机配置 `~/.kingkong_driver/workspace.json`（不进仓）**：逻辑名 `repos.firmware` / `repos.recalibration` / `keys.diag_private`（:263-273）；缺键必须问用户，**不许瞎猜路径、不许硬编码绝对路径**（:279，对应 AGENTS.md 硬规定 5）。本机实测该文件存在。
- §6:285 新机 onboarding 与 scope 清单；§6.1:312 常见坑：lark-cli 装了但 agent 调不到（PATH）。
- §7:339 发布与分发：§7.1:346 版本号怎么定、§7.2:351 **分支与 tag 是两条命令**、§7.3:362 NAS 分发（固件产物另线 `\\KingKongNAS\software\02SD\_internal\fw-<短 SHA>\`，:398）、§7.4:421 本地 dist 只留当前版、§7.5:426 **陷阱：发版后继续开发再构建会同名覆盖**、§7.6:440 **发版后必须把 `vX.Y.Z (待发布)` 收成实号**（仓内门禁扫不到，写在别人的工单页面上）。

**三条自验路径（后续开发每次都要走）**:
1. UI 改动 → `docs/skills/playwright_ui_self_test.md` + AGENTS.md 军规 13：**必须可见窗口 / Electron 正式界面**，裸 API、headless、静态截图都不算验收通过。
2. Scope / 图表改动 → `docs/skills/scope_chart_freeze_debug.md` + 军规 4：**必须让真实数据流起来看渲染结果**（"曲线不绘制"那次 DOM 与截图全正常）。
3. 真机相关 → `docs/skills/realmachine_fault_injection.md` 造障 + §4 台账按**读取器 serial** 对号；结论里"底层链路通过"与"真机验收通过"不能混写。

**关键文件与接口**:
- `AGENTS.md:170-178`（模块→skill 表）、`AGENTS.md:214` 起（军规）、`AGENTS.md:321`（READER_MP 双形态）、`AGENTS.md:349`（对外说人话，引 kung-fu 仓）。
- `docs/PROJECT-CONTEXT.md`（分节见上）、`docs/protocol/README.md`（协议索引，版本源=固件 tag 经 `0x0B` 映射，:28）、`docs/protocol/rs485_v3.3.md`（当前）、`rs485_v3.2.md`（往期）、`archive/rs485_mixed_history.md`。
- `CHANGELOG.md`：`## [未发布]` 从 :17 起；最近三版 `## [0.16.1] - 2026-10-10`:51、`## [0.16.0] - 2026-10-09`:59、`## [0.15.0] - 2026-10-09`:74。体例：Keep a Changelog + semver，**面向使用者、一个点一句白话说清"你会感觉到什么变了"**，按 新增/变更/修复 分组，条目形如「模块·子功能: 用户视角结果」，不写实现细节（约定见 :3-15）。

**踩坑（文档引用不实，2026-10-13 逐条核过）**:
1. `docs/protocol/README.md:30` 引 `../project_rules/firmware_versioning.md` —— **`docs/project_rules/` 目录不存在**，照链接走必扑空。
2. `AGENTS.md:173` 说"当前 V3.3；host 代码仍 V3.2，见文档头变更说明"，但 `docs/protocol/rs485_v3.3.md` 头部（:1-50）**没有这段差异说明**；host 仍是 V3.2 的真实证据在 `core/protocol.py:17` 的文档字符串。
3. `AGENTS.md:321` 写"READER_MP 见 `server.py:212`"，实际分叉在 `server.py:341` —— 文档里的行号引用会随重构漂移，引用前先 grep。
4. 反过来也核过：`AGENTS.md` 引用的仓内 `docs/*.md` 路径共 9 个（去重后）**全部存在**，包括 `docs/skills/` 那 12 个被点名的文件；`docs/skills/` 实际 13 份（多出的是 `ANALYZER_HARDWARE_GUIDE_V2.30.md`，AGENTS.md 未列）。
5. `AGENTS.md:349` 与 `docs/PROJECT-CONTEXT.md:465` 引的 `kung-fu/patterns/…`、`kung-fu/checklists/…` 在**另一个仓**（不在本仓），别当本仓路径找。

**验证方法**:
- 引用真实性核查（本次实跑）：脚本收集 `AGENTS.md` 里所有 `docs/**.md` 引用做存在性判断（9/9 命中）；`ls docs/project_rules` 报不存在；`grep -n 'class Cmd' core/protocol.py`=16、文档字符串在 :17。
- 台账对号：`/api/state` 取 `serial` 与 `docs/PROJECT-CONTEXT.md:224-229` 表内记录比对（本次未连设备，仅核代码与文档行号）。
- 文档改动自证：改 `docs/` 或 `AGENTS.md` 时按硬规定 4 当场跑一遍引用的命令；发版前按 §7.6 回收工单里的"待发布"占位。

**状态**: 已完成（三层结构、13 份 skill、协作上下文章节行号、两处引用不实均经本次实测；未连真机）
