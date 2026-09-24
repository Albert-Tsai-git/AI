# 全局问题解决记录 (P)

### P-018: fw v3.4.6 使能态修改力矩舵机无响应 (四根因叠加)
**日期**: 2026-09-22
**项目**: driverSoftware (@CODE_ROOT@\driverSoftware), 发布 v0.13.9
**状态**: 已解决, 已发布 (a6848b6 + c8ad4e6, tag v0.13.9)
**关键词**: [v3.4.6, MIT, mit_scales, 力矩无响应, hw_update_mit, 500, baudrate, READER_MP, 使能对齐, 固件档案]

**现象**: 使能状态下改力矩 (TAU), 舵机转动无变化; 前端控制台一串 500; 偶发使能数秒后自动失能。

**根因 (四个叠加, 缺一个都修不好)**:
1. `firmware_profiles/v3.4.6.json` 的 `mit_scales` 被手填成 pos/vel/tau=10000 (误把 Kp/Kd 量化 scale 0x4B/0x4C 的默认值当刻度)。
   固件 v3.4.0 起真值 = 2^24/2π (2670176.86) / 512 / 2048, v3.4.5 与 v3.4.6 未变。后果: 力矩指令 ×4.88, 位置 ÷267。
2. 6cee629 让 `server.hw_update_mit` 给 `backend.update_continuous_frame(..., baudrate=)` 传参, 只改了 `core/reader_wrapper.py`,
   默认启用的多进程后端 `core/reader_mp.py` (READER_MP=1) 签名没跟 → 每次热换帧 TypeError → HTTP 500, 改参数全部静默不下发。
3. 连续流波特率取前端 `req.baudrate`, 前端 `store.state.baudrate` 未同步时回退 1M → 5M 设备收不到 MIT 帧;
   另有 hw_start / 失能软着陆两处根本没传 baudrate (吃默认 1M)。
4. 「使能对齐」按钮文案判据含 Kp>0, 而 doEnable 的 alignmentRequired 不含 → Kp=0 改过位置时, 按钮写「使能」点下去只对齐不上力。

**修复**:
- 档案用 `FW_REPO_PATH=@CODE_ROOT@\driver python tools/gen_fw_profile.py --tag v3.4.6` 重新生成 (禁止手填)。
- `reader_mp.update_continuous_frame` 补 `baudrate: Optional[int] = None` (接收并忽略, 与 wrapper 同签名)。
- `server._stream_baud()` 以连接参数 (/api/params 写的全局 baudrate) 为唯一真相源, 5 处 start_continuous 统一使用。
- motion.js 抽出 `enableAlignPending()`, 按钮文案与 doEnable 共用一个判据。
- 回归门禁: `tests/unit/test_v346_enable_tau_regressions.py` (修复前 7/7 红) + 同事的 `test_fw_profile_mit_scales.py`。

**验证**: 真机 id15 fw v3.4.6 5Mbps, Kp=0 Kd=0.05, τ=0.1/0.2/−0.2/0 → 转速 1.30/3.20/−3.23/0 rad/s,
反馈 τ≈τ_cmd−Kd·v, 无故障; UI 全路径 (连接→使能→改力矩→失能) 通过; 单测 2080 passed。

**排查过程的弯路 (避免重犯)**:
- 曾把"使能后 OverTempMotor 跳闸"判成热模型参数问题 —— 实为错刻度 (力矩 ×4.88) + Kd=0 空载冲到 39.7 rad/s 的结果, 不是原因。
- 曾推测 "v3.4.5 自动清除掩盖跳闸", 读 0x89=0 (自动清除关) 即否定 —— 先读寄存器再下结论。
- 用户说 "4292e85 是好的", 实际那次连的是 v3.4.5 固件且可能走软轮询档; 比较好坏节点前先确认固件版本与测试路径一致。

### P-019: 位置读数卡在 804.2477 rad (v3.4.x 多圈超量程饱和)
**日期**: 2026-09-22
**项目**: driverSoftware / driver 固件 v3.4.x
**状态**: 已定位, 未修 (需设零或防护提示, 待决策)
**关键词**: [804.2477, 位置饱和, INT32_MAX, Q8.24, 多圈, kMitPosScale, 0x18, 0x67, 设零]

**现象**: 位置显示恒为 804.247718, 使能对齐会把位置指令对齐到该值。
**根因**: 固件 `register_protocol.cpp:314` `static_cast<int32_t>(multi_angle × inv_gear × dir × 2^24/2π)`,
v3.4 位置编码 Q8.24 输出端只覆盖 ±128 输出圈 (±804.25 rad); 超出时 ARM float→int32 饱和为 INT32_MAX (回包 pos_raw=2147483647)。
现场: 0x18 转子多圈 = −43626 rad, 减速比 −50, 0x67 零点偏置 = 0 (从未设零) → 输出端约 138.9 圈, 超限。
纯力矩空载测试 (Kp=0) 会让关节单向累积转动, 很快吃满 128 圈。
**处理**: 电机停止时设零 (0x67 / UI「设零点」) 或断电重启。建议上位机检测 ±804.2477 时提示超量程并禁止 Kp>0 对齐 (未实现)。
**风险**: 此时做 Kp>0 位置控制, 目标被对齐到错误的饱和值, 会猛拽。

### P-020: 使能态 Kp 从 0 调到 >0 时位置指令陈旧 (潜在猛拽, 既有问题)
**日期**: 2026-09-22
**项目**: driverSoftware frontend/js/pages/motion.js
**状态**: 已识别, 未修 (新行为改动, 待用户决策)
**关键词**: [使能对齐, Kp, 位置指令, 猛拽, pos_err, motion.js]

Kp=0 使能后电机按力矩自由转动, 位置指令停在使能时刻的值; 若在**使能中**把 Kp 调到 >0, 电机按 (陈旧目标 − 实际)×Kp 被拽回。
修复前后都存在。建议: 使能态 Kp 从 0→>0 时先把 pos 指令对齐到当前实测位置。

### P-025: 运动页 <100Hz 使能时附加寄存器 (0x24/0x27/0x29/0x2A/0x2B) 示波器无曲线
**日期**: 2026-09-22
**项目**: driverSoftware (@CODE_ROOT@\driverSoftware, development, 未提交)
**状态**: 已修复, 真机验证通过 (id15 fw v3.4.6 @3Mbps), 代码未提交
**关键词**: [附加寄存器, extras, 示波器, 100Hz, 软轮询, doSendMit, api.mit, flatExtras, TELEMETRY_DISPATCH, xNN]

**现象**: 运动页勾附加寄存器, 频率 ≥100Hz 有曲线, <100Hz 使能后这些曲线空白。

**根因 (两处叠加)**:
1. <100Hz 使能走 motion.js `doSendMit()` → `/api/cmd/mit`, 前端不带 extras, 后端 `api_mit` 也把 extra_regs 写死 [0xEB] —— 设备根本没被要求回这些寄存器。
2. 软轮询回包进 scope 靠 api.js `TELEMETRY_DISPATCH` (/api/cmd/status、/api/cmd/mit), 只挑 pos/vel/tau/温度, 把 `parsed.extras` (数字地址 key) 全丢; scope 信号 key 是 "xNN" 大写 hex (硬件流 drain 路径才摊平成 xNN)。所以未使能 <100Hz 也同样空白。

**修复**: server.py `MitReq` 加可选 `extras`, 与 status 共用 `_extras_with_state()` (去重 + 保证 0xEB); motion.js doSendMit 带 `getSelectedExtras()`; api.js 加 `flatExtras()` 把 extras 摊成 xNN 并入两个 dispatch。

**验证**: pytest 2126 passed; 真机可见 GUI: 50Hz 使能 → TX 帧含 `29 2A 2B 24 27 EB`, scope buf 5 路 675/675 非空; 未使能 50Hz、100Hz 使能 (回归)、10Hz 使能均有数据; 控制台无错误。

**教训**: 同一功能按频率分硬件流 / 软轮询两条路时, 新增字段要两条路都接, 且要同时核对"请求带没带"和"回包进 scope 时有没有被映射丢掉"两层。

### P-021: 【数据库清理】向量库 1.2GB 实为 driver 仓库全量导入，清理后 7.8MB

**日期**: 2026-09-24
**关键词**: 向量库, sire_vectors.sqlite3, 数据库体积, driver 仓库, 全量索引, DONE_FULL_FILE_INDEXED, purge, VACUUM, 删除密码, 只增不减
**现象**: 新增知识后数据库一直显示 1.2GB，看起来没有增长；检索结果被 dualAngle.c 数表和 JSON 测量数据干扰。
**原因**: 2026-09-21 之前某次任务把 @CODE_ROOT@\driver（v3.4.5, commit 8b85b1d0）1101 个文件全量切片导入（meta: driver_repo_chunk_count=234296），占 882MB（99.5%），其中 .json 测量数据占 822MB。09-21 数据库误缩到 5MB 后从备份恢复，这批数据随之回来；之后又定了「只增不减」规则，所以一直留在库里。真实知识（97 条记录）正文只有 106KB，每次增长几十 KB，按 GB 显示时看不出变化。
**解决**: 用户授权原话「我这里记录的是真正的知识，不是代码库，删掉这些」→ 先用 sire_db_backup 备份（SIRE-DB-Backups\sire_vectors-20260924-084110.sqlite3）→ 专用脚本 @SIRE_ROOT@\purge_driver_repo.py 只删 path 以 @CODE_ROOT@\driver\ 开头的片段（先核对数量 234303，由用户在终端输入删除密码，重建 FTS，VACUUM，integrity_check）。
**结果**: 1208.9MB → 7.8MB；chunks 235480 → 1177；knowledge 97、task 512、keywords 5065 均不变；integrity ok。
**注意**:
- 不要用 sire_vector_db.py index 加 SIRE_DB_ALLOW_DELETE 来删：它会一并删掉所有已经不在磁盘上的来源（例如 @SIRE_ROOT@\archive-20260921 的历史台账）。
- 删除密码必须由用户本人在终端输入，AI 不代填。
- 以后不要把整个代码仓库或测量数据 JSON 全量导入知识库；知识库只存提炼后的知识。
- 遗留：「只增不减」模式下每次 reindex 都会给 global_index.json 追加一个新版本片段，重复片段会占据检索结果前几名，需要另行处理。
**状态**: 已完成


### P-022: 【飞书自动化】Claude 桌面版 MSIX 路径虚拟化导致续跑工作目录不存在

**日期**: 2026-09-24
**项目**: 全局工具 @USER_HOME@\.feishu_bridge（【飞书自动化】）
**关键词**: 飞书自动化, MSIX, 路径虚拟化, AppData Roaming, LocalCache, Packages, scratch-workspaces, 工作目录不存在, cwd, os.path.isdir False, claude --resume, 计划任务

**现象**: 飞书回复续跑报「工作目录不存在」，但桌面 Claude 会话里该目录明明存在（@DRIVE_C@/Users\<u>\AppData\Roaming\Claude\scratch-workspaces\...）。桌面会话内 shell 能进入该目录，包外 python/计划任务 os.path.isdir 返回 False。

**根因**: Claude 桌面版是 MSIX 应用，Windows 对其 %APPDATA% 写入做文件系统虚拟化，真实位置在 %LOCALAPPDATA%\Packages\<包名如 Claude_pzs8sxrjxfjjc>\LocalCache\Roaming\...。包内进程看到虚拟路径，包外进程（计划任务启动的监听器）看不到。旧版监听器目录不存在时 `cwd=None` 静默回退到监听器自身目录，续跑一直在错误目录执行而无人察觉。

**方案**: listener.resolve_cwd(cwd)：目录存在直接用；否则若位于 %APPDATA% 下，遍历 %LOCALAPPDATA%\Packages\*\LocalCache\Roaming\<相对路径> 找到存在的即用；仍找不到则任务转 NEED_DIR，飞书提示用户回复「默认」（config default_cwd，@SIRE_ROOT@\AI\SESSION）或完整路径，绝不静默回退。Hook 的 FEISHU_BRIDGE_CWD 仍传原路径，保证卡片显示和会话映射一致。

**验证方法**: 从桌面会话发起、在飞书回复 → bridge.log 出现「[目录] MSIX 虚拟路径映射 A -> B」，tasks 表该任务 DONE、耗时 ~37s，结果卡片回帖，桌面同步 Hook 回填 1 条。

**踩坑**: 1) 目录不存在时任何「回退默认目录」都是隐患，必须硬失败或询问用户；2) 判断 MSIX 虚拟化：同一路径包内 shell 可进、包外 python isdir=False，去 %LOCALAPPDATA%\Packages 下找 LocalCache\Roaming。

**状态**: 已完成


### P-023: 【飞书自动化】多 AI 中转切换踩坑合集（计划任务复活、CC-Switch 覆盖、Codex Hook 信任、.CMD 注入、Opus 5.5 CLI 版本）

**日期**: 2026-09-24
**项目**: 飞书多 AI 中转 feishu-hub（@SIRE_ROOT@\AI\AI\feishu-hub），配套 F 记录「【飞书自动化】飞书多 AI 中转中间服务 feishu-hub」
**关键词**: 飞书自动化, 踩坑, 计划任务, Disable-ScheduledTask, 重启复活, CC-Switch 覆盖, settings.json, config.toml, notify, --previous-notify, hooks.json, hook trust, dangerously-bypass-hook-trust, codex.CMD, cmd.exe 元字符, 命令注入, Opus 5.5, unrecognized_model, 2.1.280, 桌面版自带 CLI, MSIX, 单一写入者, 两个 AI 同时改代码, .NET 相对路径, ReadAllText, os._exit 不刷新输出

**现象与根因、解法**（每条都是本次真实遇到）:

1. **旧服务重启后复活，和新服务抢飞书消息**：切换时只 `Stop-ScheduledTask FeishuClaudeBridge`，电脑重登录后它按登录触发器又启动；旧监听器还带「每 60s 补回 Hook」守护，把旧 Hook 写回 settings.json，飞书消息被旧桥处理、回复为空。
   解法：下线服务要 `Disable-ScheduledTask` + 结束进程 + 删除/改名入口脚本；切换后检查 settings.json、config.toml 是否被旧守护写回。飞书长连接事件只推给一个在线连接，新旧不能同时在线。

2. **CC-Switch 整体重写配置，冲掉 Hook/notify**：settings.json、config.toml 都由 CC-Switch 管理，切换供应商时整份重写。
   解法：Claude 侧同步修改 cc-switch.db（settings.common_config_claude、proxy_live_backup.original_config）；Codex 侧 notify 串接由 Codex 执行器每 60s 守护（tomllib 解析、保留 computer-use 实际路径、未知 notify 不覆盖、写前备份写后校验）。

3. **Codex hooks.json 的 Stop Hook 不执行**：Codex 要求持久化 hook trust（`--dangerously-bypass-hook-trust` 帮助原文 "without requiring persisted hook trust"），桌面端不弹信任提示、CLI 也没有信任子命令。脚本手动喂数据正常，但真实轮次零上报。
   解法：改走 config.toml `notify`（无需信任）：Codex 自带 computer-use 占用 notify，用它的 `--previous-notify '<JSON 数组>'` 串接自己的脚本；notify 数据在最后一个命令行参数（字段连字符写法 thread-id/turn-id/last-assistant-message，type=agent-turn-complete）。hooks.json 不再挂 Stop，防日后被信任后重复上报。

4. **经 codex.CMD 传用户文本 = 被 cmd.exe 篡改/注入**：`shutil.which("codex")` 返回 `@DRIVE_C@/nvm4w\nodejs\codex.CMD`，Popen 列表参数经 cmd.exe 二次解析，prompt 中 `& | % ^ " < >` 和换行被截断/展开/当作命令，且单行 ≤8191 字符。
   解法：带用户文本的命令直接调用 npm 包内原生 exe：`<npm前缀>\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe`；能走 stdin 的一律走 stdin。测试用含元字符与多行的 prompt 断言逐字一致。

5. **Opus 5.5 报 400「Claude Code 2.1.261 does not support this model; version 2.1.280 or newer is required」**：全局 npm 的 claude.exe 比桌面版旧；`--model opus` 在旧版解析为 claude-opus-5。
   解法：执行器自动选 Claude 桌面版自带的最新 CLI（`%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code\<版本>\claude.exe` 取最高版本），找不到回退 npm；真实调用看 JSON 输出的 modelUsage 键确认实际模型。

6. **两个 AI 同时改同一份代码导致状态分叉**：Codex 在 Claude 不知情时改了旧桥 listener/hook，测试失败、设计冲突。
   解法：约定单一写入者（桥代码 Claude 独占，Codex 只改 executors/codex/）；交接给另一个 AI 时写明允许改动的目录、禁止碰线上配置、不准 push；复核时先 `git diff --stat` 查越界。另一个 AI 大补丁一次提交曾因编码失败整体丢失，要求「每个文件单独写入」。

7. **写/测脚本的小坑**：PowerShell 里 `[IO.File]::ReadAllText("相对路径")` 按进程当前目录解析，不跟随 `cd`，必须用绝对路径；PowerShell here-string 替换多行文本因 CRLF/LF 不一致静默不生效，改用 Python 替换并 assert 命中次数；测试脚本结尾 `os._exit()` 不刷新重定向的 stdout，需先 `sys.stdout.flush()`；TextIOWrapper 包装 BytesIO 被回收时会关闭底层缓冲，需 `detach()`。

8. **MSIX 路径虚拟化**（见 P-022，仍适用）：Claude 桌面会话 cwd 位于虚拟 %APPDATA%，包外执行器需映射到 %LOCALAPPDATA%\Packages\*\LocalCache\Roaming；Claude、Codex 两个执行器都已实现 resolve_cwd。

**验证方法**: 问题 1：`Get-ScheduledTask FeishuClaudeBridge` 为 Disabled、无 listener.py 进程；问题 2/3：人为冲掉 config.toml 串接后重启 Codex 执行器，几秒内补回；真实 codex exec 一轮后 hub.sqlite3 turns 表出现该 thread-id；问题 4：测试 Q1 元字符多行 prompt 逐字一致；问题 5：`--model claude-opus-5-5` 真实调用 modelUsage=claude-opus-5-5。

**状态**: 已完成


### P-024: SIRE Git 归档应对 SQLite 快照做路径规范化与空闲页清理

# SIRE Git 数据库快照：保留完整记录并规范化本机路径

**日期**: 2026-09-24
**项目**: SIRE v6
**关键词**: SIRE, Git 归档, SQLite 快照, 在线备份, 路径脱敏, FTS, embedding, VACUUM

## 需求场景
当 SIRE 工作流与向量数据库需要进入 Git 仓库时，原始 SQLite 文件可能包含本机路径、邮箱/私网地址和过去更新留下的 freelist 页。直接复制虽可能 `integrity_check=ok`，仍会泄露旧值。

## 方案
用 SQLite backup API 在源库只读连接上生成一致副本；只在副本文本列中统一机器盘符与用户目录并清理邮箱/私网 IPv4；重建 `chunks_fts`、`kfts`、`cfts`，重算受影响的 legacy hashed vectors 与 v2 semantic embeddings；启用 `secure_delete` 后 `VACUUM`；扫描 SQLite 全部可见文本及整个文件字节，再确认 sidecar 不存在。Git 快照保留业务行和表，排除 key/vault、个人配置快照、模型权重和 WAL/SHM。

## 关键文件
- `sire/tools/snapshot_db.py`：可重复的脱敏在线备份、索引重建和泄露验证。
- `sire/data/sire_vectors.sqlite3`：Git 数据快照。
- `sire/data/snapshot-manifest.json`：来源 hash、表计数、替换计数和验证结果。
- `sire/workflow/shared/sire/scripts/sire_knowledge_index.py`：当前 FTS/embedding 逻辑来源。

## 验证
本任务 R7 逐项记录 SQLite 完整性与计数、FTS 查询、embedding 文本 hash 一致性、全文件凭据/路径/PII扫描、WAL/SHM 排除和 Git 实际跟踪/提交状态。源数据库另行备份，不被快照工具改写。

## 限制
匹配式隐私扫描只能识别常见凭据格式；清理的是机器标识而非语义知识。执行脚本需要本机可用的匹配 embedding 模型；如模型不可用会失败并保留原快照，不得跳过向量一致性校验。


### P-20260923: SIRE 向量库检索必须使用只读 SQLite 连接保护 Git 快照

**日期**: 2026-09-24
**项目**: SIRE v6 Claude/Codex 共享工作流
**状态**: 已修复
**关键词**: Claude, Codex, SIRE, SQLite, read-only, WAL, Git 快照, hash, knowledge retrieval

## 需求场景
Claude 和 Codex 共用仓库中的同一份 SIRE 向量库。检索、统计或读取 chunk 属于只读操作，不应改变数据库主文件或让已提交快照与 manifest 的 SHA-256 失配。

## 方案
`sire_vector_db.py` 的 `search`、`show`、`stats` 必须使用 SQLite `mode=ro` 并启用 `query_only`；不得通过检索入口创建表或切换 WAL。`sire_knowledge_index.search()` 只检查当前 schema 并执行查询，升级 schema 留给 `index`/`migrate` 写路径。写入操作继续先生成可验证备份。

## 关键文件
- `sire/workflow/shared/sire/scripts/sire_vector_db.py`
- `sire/workflow/shared/sire/scripts/sire_knowledge_index.py`
- `sire/tools/snapshot_db.py`
- `sire/data/snapshot-manifest.json`

## 验证
从 Codex 与 Claude 已安装入口分别运行 `stats` 和相同的向量检索，两边解析到同一仓库数据库、返回相同计数和命中 ID；正常检索、无命中查询及读取 chunk 后，隔离副本的数据库字节 hash 保持不变。

## 限制
`index`、`migrate` 和任务归档仍会更新 SQLite；提交前需要按 SIRE 快照流程刷新 manifest、检查 WAL/SHM，并重新执行完整性与隐私扫描。


### P-20260924: Claude/Codex 共用的 SIRE 工作流与 SQLite 应在单一 Git 源中归档

**日期**: 2026-09-24
**项目**: SIRE v6 Claude/Codex 共享工作流
**状态**: 已验证；当前任务的真实桌面 UI 验收因无可用 UI 应用而阻塞
**关键词**: SIRE, Claude, Codex, shared workflow, 单一来源, Git, SQLite, WAL, writer lock, snapshot, database

## 需求场景
多个 AI 客户端必须使用相同的 SIRE 规则、角色定义、知识库和 SQLite 数据，且仓库克隆后能按仓库内文档重新建立客户端入口。客户端配置目录只保留指向仓库文件的薄适配器，不能再维护一套不同步的规则或数据库。

## 原因
仅将技能文件放入 Git 不够：客户端可能仍将路径解析到个人目录里的旧拷贝；只复制 SQLite 主文件也可能漏掉已提交 WAL 中的数据；并发索引、RSI 写入和快照发布可能互相覆盖；数据库 manifest 还可能与实际提交文件脱节。

## 方案
把唯一共享工作流、通用知识和应用数据库放在同一仓库内，用 `sire_paths.py` 解析数据库路径；Claude/Codex 入口通过符号链接或目录联接指向该源。环境变量覆盖须由同一映射文档定义并保持一致。每个数据库写入口（索引、迁移、RSI 等）都应在写入前使用同一目标锁并按规则备份；`knowledge_record_count`、`task_record_count` 与 `keyword_count` 元数据应反映表内实际总行数，不能只记本次同步量。快照在源库只读连接上执行 SQLite 在线备份，以包含已提交 WAL，再脱敏、校验后原子发布数据库与 manifest。提交前确认 manifest hash 等于 Git 中 SQLite 文件的 SHA-256，且仓库内没有 WAL/SHM sidecar。

## 关键文件
- `sire/workflow/shared/sire/`：唯一 SIRE 工作流源。
- `sire/workflow/shared/sire/scripts/sire_paths.py`：统一解析知识、工作流与数据库路径。
- `sire/tools/snapshot_db.py`：在线读取、规范化及原子发布 SQLite 快照。
- `sire/data/sire_vectors.sqlite3` 和 `sire/data/snapshot-manifest.json`：配对归档的数据文件与校验清单。

## 验证
检查两个客户端入口解析到相同物理工作流和数据库；在有未 checkpoint 的已提交 WAL 行的临时库上验证快照包含该行且不改变源库；让 RSI 写进程与快照锁竞争并确认其等待；最后检查数据库完整性、业务行计数、FTS/embedding 一致性、隐私扫描、主库与 manifest 哈希及无 sidecar 状态。

## 限制
真实 Claude/Codex 桌面 UI 只能在应用可被自动化访问时验收，CLI 成功不能代替 UI 验收。仓库归档的是规范化应用数据库；机器级任务关闭归档仍按全局契约写入指定外部 archive。数据库写入脚本新增后必须纳入写入口审查，否则锁仍可能被绕过。
