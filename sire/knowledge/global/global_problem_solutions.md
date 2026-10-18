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


### P-20260925: SIRE 的 RSI 规则曾是孤岛——入口不可达且无触发点，需由 R9 收尾门禁兜底

**日期**: 2026-09-25
**项目**: SIRE v6 Claude/Codex 共享工作流
**状态**: 已验证（run R20260925-052105）
**关键词**: SIRE, RSI, 自我优化, self-optimization, sire_rsi, improvement_proposals, workflow_versions, 提案, 激活, 回滚, R9, rsi-check, finalize, rsi_unregistered_change, 工作流改动, 门禁, 关键词子串误报

## 需求场景
用户询问 SIRE 是否包含 RSI、RSI 如何触发。RSI（受控递归自我改进）要求工作流机制改动走"提案 → 基线指标 → 独立评估 → 版本化激活 → 观测 → 回滚"。

## 原因
1. `references/self-optimization.md` §5.1 与 `scripts/sire_rsi.py` 存在，但 `SKILL.md` 与 `global-contract.md` 均未链接该文件，按入口执行的 Agent 读不到 RSI 规则。
2. 没有任何脚本、阶段、Hook（Claude settings.json / Codex hooks.json）调用 `sire_rsi.py`；RSI 只能手动触发。结果：提案表只有 2026-09-21 的 2 条冒烟记录，此后多次工作流改动均未登记。
3. `sire_kb.py search` 按不区分大小写的子串匹配，检索 "RSI" 会误命中 "VERSION"/"supportedVersions"；RSI 相关知识需用向量检索或 `self-optimization`、`improvement_proposals` 等词。

## 方案
- `SKILL.md` 新增 "Workflow changes (RSI)" 段并在 Supporting references 链接 `self-optimization.md`：改共享 skill 目录前先 `sire_rsi.py propose`，验证后 `evaluate`，只激活 `EVALUATED_PASS`，回归则 `rollback`。
- `sire_supervisor.py` 新增只读 `rsi-check` 子命令并接入 `finalize`：共享 skill 目录有未提交改动（`git status --porcelain -- .`），且该目录最后一次提交（`git log -1 --format=%cI -- .`）之后没有 `PROPOSED`/`EVALUATED_PASS`/`ACTIVE` 提案时，返回 `STOP`、rc=3、`rsi_unregistered_change`，finalize 不推进 R9 基线。数据库以 `mode=ro` + `query_only` 打开，库/表缺失或非 SQLite 文件按"无提案"处理（fail-closed）；只有目录不存在或不在 Git 仓库时返回 `SKIPPED`，git 不可用或 status/log 失败返回 `STOP`（`rsi_git_undetermined`）；取不到最后提交时间（仓库尚无提交）时 `ACTIVE` 提案不算；finalize 把结果写入运行目录 `rsi-report.json`。
- 本次改动自身按 RSI 走完：`RSI-20260925-R9GATE` propose → evaluate → activate v6.2（config-hash = 提交后工作流目录 git tree hash）。

## 关键文件
- `sire/workflow/shared/sire/SKILL.md`、`references/supervisor.md`（检查项 8）、`references/self-optimization.md` §5.1
- `sire/workflow/shared/sire/scripts/sire_supervisor.py`（`rsi_gate` / `rsi_check` / `finalize`）
- `sire/workflow/shared/sire/scripts/sire_rsi.py`

## 验证
R4 拆解复核、R6A/R6B/R6C 独立复核与 R7 功能测试结论见 run R20260925-052105 的 evidence（U-01 qa/review）。正常路径：真实库有提案 → PASS；异常/边界：删提案、提案 EVALUATED_FAIL/ROLLED_BACK、提案早于最后提交、库不存在、无表空库 → STOP rc=3；只读：运行前后库 sha256 不变且无 -wal/-shm；finalize 在 STOP 时基线不变；verify-zip 回归通过。

## 限制
- 门禁把"最后一次工作流提交之后的任一未失败提案"视为已登记，无法证明提案与具体 diff 对应；它是兜底而非审计。
- 其他会话在共享 skill 目录留下未提交改动时，任何 run 的 finalize 都会 STOP（预期行为），需先由改动方登记提案或提交。
- `sire_rsi.py` 默认写仓库库 `sire/data/sire_vectors.sqlite3`，而收尾流程用 `snapshot_db.py` 从机器级归档库重建仓库库：只写进仓库库的 RSI 记录会在快照时丢失，RSI 写入必须同时（或只）写归档库后再快照。
- 未修复：`sire_rsi.py status` 会先备份并 `CREATE TABLE`，不是只读；`evaluate` 只支持"越高越好"（after >= target）。


### P-20260926: v3.4.6 寄存器文档对账与 0x6A/0x80 清理

**项目**: driverSoftware（分支 chore/misc-optimizations，提交 b423f31、c140497，未 push）
**关键词**: v3.4.6, 寄存器梳理, 0x6A, AdcUsableAmp, GpioDebugPreGen, HOST_HIDDEN_REG_ADDRS, 0x80, InnerAngle, inner_zero, kStInnerAngle, 上位机隐藏, 固件档案

**需求场景 / 现象**: 以用户给定的《v3.4.6寄存器梳理》为准，核对 registers.py / server.py 隐藏清单 / 固件档案是否一致，并清理 0x6A、0x80 的遗留。

**方案 / 决策**:
1. 文档与 firmware_profiles/v3.4.6.json 逐地址、名称、读写核对：除 0x6A 外全部一致。0x6A 文档写 GpioDebugPreGen「固件删掉」，档案里 v3.4.5+ 该地址是 AdcUsableAmp（文档没列新名）。
2. 文档所有「上位机隐藏」地址已全部在 server.py HOST_HIDDEN_REG_ADDRS 中；多出的只有 0x6A（继续隐藏，结果一致）。隐藏只影响寄存器页展示，不影响底层读写。
3. 0xEB ControllerState 文档标「上位机隐藏/删掉」，但档案里仍存在且 kt_worker/ota_utils/server 依赖，按「上位机隐藏」处理，不动底层读取。
4. 删除无引用的 kStAdcUsableAmp 常量，改注释说明 0x6A 历史；修正 0x7F GpioDebugAtFail 说明中「与 0x6A 对照」的失效引用。
5. inner_zero.py 的 REG_INNER/REG_POS_MECH/REG_STATE 由写死字面量改为引用 REG 常量，0x80 下一版固件换地址时只需改 registers.py。

**关键文件**: core/registers.py, core/register_descriptions.py, core/inner_zero.py, server.py(HOST_HIDDEN_REG_ADDRS), firmware_profiles/v3.4.6.json

**验证方法**: 寄存器/meta/隐藏清单/冷启动波特率相关单测 141 通过；inner_zero 相关单测 59 通过 2 跳过。

**限制**: 未跑全量单测；未做真机可见 GUI 验收（改动仅常量引用与说明文字）。v3.4.7 比 v3.4.6 仅多 0x26 IqCmd，文档未覆盖，registers.py 已按 v3.4.7 处理。文档自身有小矛盾（0x81 默认值 100/105、0xE8 范围、0xE1 的 14、0x80 行列错位）未改文档。

**踩坑**: 查寄存器依据要先搜知识库 K-fw-v345-register-compat 与固件档案，我曾因没查而误判 AdcUsableAmp「无依据」。

**状态**: 已完成


### P-20260927: 设输出零位 (0x67) 不会让内圈零位 0x38 失效

**日期**: 2026-10-12
**项目**: driverSoftware (分支 chore/misc-optimizations 的 review)
**关键词**: 0x67, OutputZeroOffset, 设零位, set_output_zero, 0x38, MechZeroInner, 内圈零位, BootInferOuterMultiTurnFromInner, output_zero_offset_, _IZ_NEED_REGS, kStInnerAngle

**需求场景 / 现象**: review 时发现提交 c488ad5 在「⑨ 设当前位置为零位」成功后弹警告"输出零位变了, 之前测的内圈零位 (0x38) 不再适用, 请回到 ⑥ 重做"。

**根因**: 依据不成立。固件 `Encoder::BootInferOuterMultiTurnFromInner` (driver 仓 Core/Src/encoder.cpp) 只用 inner_angle_q32_ (内圈原始角 − 0x38) 和 outer_angle_q32_ (外圈原始角 − 0x37) 推多圈; output_zero_offset_ (0x67) 只在算 multi_angle_rad_ 时被减掉, 不进 BootInfer、不进相位曲线。所以写 0x67 不会让 0x38 失效; 只有 0x37 (F2) 变化才会。同一张卡的 setZeroDesc 也写着"只改上报位置, 跟 F2 独立"。固件 0x67 的副作用只有一条有记录: register_protocol.h 注释写"重设输出零点会平移 ψ 基准" —— 那是波发生器补偿 (0x3E/0x3F/0x6D), 不是 0x38。

**方案 / 架构**: 判断"某个零位改了要不要重标 0x38"时, 看它进不进 BootInfer 的 phase = wrap180(outer_rep − inner_rep×gear): 0x37/0x38 进, 0x67/0x68 不进。若要提示用户, 应该挂在 F2 改了 0x37 之后, 不挂在 ⑨。

**关键文件与接口**:
- driver 仓 `Core/Src/encoder.cpp` `BootInferOuterMultiTurnFromInner` / `SetCurrentPositionTo` — 0x67 写入重跑 BootInfer, 但 BootInfer 不读 offset
- `server.py` `api_set_output_zero` — 停机 → 写 0x67 → SaveConfig
- `server.py` `_IZ_NEED_REGS` — 内圈零位自动模式按名核对档案的地址表, 仍写死 0x16/0x80/0x38
- `core/inner_zero.py` `REG_INNER = REG.kStInnerAngle`

**实施步骤**:
1. 搜固件仓 output_zero_offset_ 全部引用, 确认只出现在 multi_angle 计算与 SetCurrentPositionTo;
2. 读 BootInfer 实现确认输入只有 inner/outer 两个 q32 角;
3. 用固件仓最新提交 (f55b3f11, 2026-10-07) 复核一遍, 结论不变。

**验证方法**: `git -C <firmware> show <rev>:Core/Src/encoder.cpp | grep -A18 "BootInferOuterMultiTurnFromInner"` 只见 inner_angle_q32_ / outer_angle_q32_。

**踩坑**:
- 地址常量化重构 (c140497) 只改了 inner_zero.py, 漏了 server.py 的 `_IZ_NEED_REGS` 字面量 —— 寄存器重构必须符号名 + 字面量双搜 (军规 12)。
- "下一版固件换地址只改 registers.py" 不成立: 单一常量改地址会让 v3.4.5~v3.4.7 设备失配, 跨版本地址应按 fw_profile.reg_addr(名字) 运行时取。
- 附带风险 (未真机验证): ⑥ 自动模式进场把 RAM 0x38 清 0 且不写回, 之后点 ⑨ (内含 SaveConfig) 而不做 ⑦, flash 0x38 会被存成 0。

**状态**: 已完成 (review 结论, 未改代码)


### P-20260928: 会跨固件搬家的寄存器按档案名字运行时取址 + 地址合理性校验 (内圈零位 InnerAngle)

**日期**: 2026-10-12
**项目**: driverSoftware (分支 chore/misc-optimizations, 提交 9640f3f..85901f3, 未 push)
**关键词**: InnerAngle, 0x80, fw_profile.reg_addr, 按名字取址, _iz_inner_addr, _IZ_INNER_ADDR_TAKEN, inner_addr, 内圈零位, timeout_s, NaN, 钳位, 寄存器换地址, 坏档案, 截低8位

**需求场景 / 现象**: 内圈零位自动模式要读 InnerAngle (v3.4.5~v3.4.7 在 0x80, 下一版固件要换地址)。原代码 server.py `_IZ_NEED_REGS` 写死 0x80, 档案里地址不是 0x80 就拒绝; 曾有注释称"换地址只改 registers.py", 实际改常量会让新旧固件只能顾一头。

**根因**: 跨固件版本会搬家的寄存器, 用模块常量表达不了"每台设备各自的地址"; 地址的权威是 active 档案 (fw_profile), 名字才是跨版本稳定键。

**方案 / 架构**:
1. 会搬家的寄存器 (InnerAngle) 运行时 `fw_profile.reg_addr(name)` 取址, 经参数显式传入采集函数 (`collect(inner_addr=...)` 必填、无默认值, 防静默退回旧地址); 不设模块常量。
2. 各版地址恒定且被多处直写的 (PosMech 0x16 / MechZeroInner 0x38) 只按 REG 常量核对名字, 不改运行时取址 (避免半套改造)。
3. 放宽门控 ("档案说在哪就读哪") 后必须补地址合理性校验: 非 int / bool / 越出 0~0xFF (发帧时 `a & 0xFF` 会把 0x116 截成 0x16, 静默读错) / 撞上本流程已占用的地址 (同帧捎带、同批读取、零位寄存器) 一律当"没有"。
4. 请求里的超时类参数要钳上限并拦 NaN: `el > nan` 恒假, 配合"坏帧 continue 跳过卡住判据"会让电机一直转。

**关键文件与接口**:
- `server.py` `_iz_inner_addr()` / `_IZ_INNER_ADDR_TAKEN` / `_IZ_FIXED_REGS` — 内圈零位自动端点与 save_all 复位残差共用
- `core/inner_zero.py` `collect(c, gear, *, inner_addr, ...)`
- `server.py` 端点里 `timeout_s = min(300, t) if isfinite(t) else 300`

**验证方法**: tests/unit/test_calib_inner_zero_endpoint.py (`test_inner_angle_moved_address_is_followed`、坏地址参数化、`test_timeout_is_capped_so_bad_frames_cannot_spin_forever`) 与 tests/unit/test_persist_zero_regs_reset.py (`test_residual_follows_moved_inner_angle`、`test_residual_not_read_when_inner_angle_addr_is_bogus`); 变异 M1~M5 各自只让目标用例变红。全量 tests/unit 约 2500 例 3~4 分钟。

**踩坑**:
- 改寄存器取址要同时搜符号名与字面量 (0x80 / 128 / "@0x80"), 注释和测试文件头里的旧说法也算残留 (三路复核都抓到过漏改的注释)。
- 门控用例若用 0x38=0 的仿真电机, 门控排到"进场清 0x38"之后也看不出来 —— 用 0x38≠0 并断言拒绝时不写寄存器。
- 复核代理跑测试时主控不要改工作区, 否则测试结果被干扰 (本次 R6C 因此多花十几分钟)。
- Git Bash 工具里 heredoc 会吞掉反斜杠, 含正则/JSON 转义的脚本用 Write 工具落盘再执行。
- 已确认的相关风险 (未修, 另开单): ⑥ 自动模式进场把 RAM 0x38 清 0 不写回, 固件 SaveConfig 存整页 g_cfg, 之后点 ⑨ 设零位 (内含 SaveConfig) 而不做 ⑦ 会把 flash 0x38 存成 0; ramp_s 无上限且减速段从满速起减、不判超时。

**状态**: 已完成


### P-20260929: 数据区地址两表实测 bin 核对：MPP420 现表错、MPT420 productInfoList 错

**日期**: 2026-10-12
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01（分支 feature/mpp-algo-4060）
**关键词**: DATA_ADDRESS_LAYOUTS, productInfoList, resolveDataAddress, getIAPArguments, 数据区地址, angleData, polyfits, MPP420, MPT420, 0x08018000, 0x08015800, 0x08014800, LE32 字面量, 固件 bin 核对, load_app_data, kingkong 解密

**需求场景 / 现象**: 用户想把标定/IAP/恢复出厂用的数据区地址从 parse_iap_bin.DATA_ADDRESS_LAYOUTS 整体换回 sub_common/config.py 的 productInfoList。两表在 MPT 4.2.0、MPP 4.2.0 上地址互相矛盾，不知道哪个对。

**根因**: 两份表都是人工维护的常量，没有任何代码去和固件比对。a26210c0（2026-10-10）把 MPP 105 的 420+ 行改成“按 MPT”0x08015800/0x08016000，与实际 MPP420 固件不符；productInfoList 的 MPT 420 仍是旧布局 0x08014800/0x08015000，与实际 MPT420 固件不符。另外 productInfoList 是精确版本 key，不覆盖 DPT 4.2.2/4.2.3/4.2.4、DPT_G1(109)；DPB 409 条目缺 inner.polyfits。

**方案 / 架构**: 不整体切换。用实际 bin 当真源判定：固件代码引用 Flash 数据区时，地址会以 32 位小端常量出现在字面量池里，统计候选地址出现次数即可判断哪个地址是该固件真用的。结论：MPP420 → 0x08018000/0x08018800（productInfoList 对）；MPT420 → 0x08015800/0x08016000（现表对）；DPT/DPB 其余版本两表一致且命中。建议只修现表 105 的 420+ 行，MPP303 两个来源都未证实，需另找 .map。

**关键文件与接口**:
- `controller/python/parse_iap_bin.py:224` — DATA_ADDRESS_LAYOUTS；`:267` resolveDataAddress；`:592` load_app_data（自动解密 kingkong 包）
- `controller/python/sub_common/config.py:88` — productInfoList（326aed1 恢复，注释称仅供旧测试）
- `controller/python/sub_algorithm/step4_GenerateV4020.py:827` — DPB 慢区取 encoderDataAddress["inner"]["polyfits"]
- 调用点：parse_iap_bin.py:469（IAP）、Encoder.py:3484（恢复出厂）、Encoder.py:4621（标定）

**实施步骤**:
1. 本机实际固件在 `C:\Users\Administrator\Downloads\bin\{DPB,DPT,MPP,MPT,...}`（含 .kingkong.bin 加密包）。
2. 脚本 `.sire/runs/R20261012-102955/evidence/compare_sources.py bins <bin...>`：load_app_data → parse_iap_bin_info → 两表查址 → `data.count(struct.pack('<I', addr))`。
3. `compare_sources.py tables` 逐版本列两表差异。

**验证方法**: `PYTHONIOENCODING=utf-8 py -3.12 compare_sources.py bins <bins>`；MPP420 bin 中 0x08018000 出现 9 次、0x08015800 0 次；8 个 MPT420 bin 中 0x08015800 出现 8~9 次、0x08014800 0 次。

**踩坑**: Windows 控制台 GBK 输出中文乱码，需 PYTHONIOENCODING=utf-8；DPT 4.2.x 的 inner 地址在 bin 中 0 次引用（可能改为外推），不能用“0 次”直接判错，单圈 outer 地址判定才可靠。

**状态**: 已完成（分析结论；未改代码）


### P-20260930: MPP 数据区地址改查 sub_common productInfoList（PRODUCT_INFO_LIST_SERIES）

**日期**: 2026-10-12
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01（分支 feature/mpp-algo-4060）
**关键词**: MPP, 105, productInfoList, resolveDataAddress, PRODUCT_INFO_LIST_SERIES, _resolveFromProductInfoList, 数据区地址, 0x08018000, IAP 不支持, data_address_not_found, AngleDataPtr, c_uint32

**需求场景 / 现象**: MPP 4.2.0 的 IAP/标定用了“按 MPT”的数据区地址 0x08015800/0x08016000，实际 MPP420 固件引用的是 0x08018000/0x08018800。用户要求 MPP 改为读取 sub_common/config.py 的 productInfoList。

**根因**: a26210c0 把 DATA_ADDRESS_LAYOUTS 的 105 行改成 MPT 地址，没有拿实际 bin 核对。

**方案 / 架构**: parse_iap_bin.py 新增 `PRODUCT_INFO_LIST_SERIES = (105,)`，resolveDataAddress 命中该系列时走 `_resolveFromProductInfoList`：懒导入 productInfoList，按 系列+int(版本) 精确取 key（与旧 getIAPArguments 同口径），逐层 isinstance 防御，返回副本；导入失败/查不到返回 None（不写错地址）。删除内联表 105 行。否决“整体切 productInfoList”：其 MPT 4.2.0 地址与实际 bin 不符，且缺 DPT 4.2.2+、DPT_G1。

**关键文件与接口**:
- `controller/python/parse_iap_bin.py` — PRODUCT_INFO_LIST_SERIES、_resolveFromProductInfoList、resolveDataAddress
- `controller/python/qa_api/tests/test_iap_arguments.py` — MPP 420/303/未收录/副本 4 条
- 调用点：parse_iap_bin_info（IAP，upgradeSupported）、Encoder.py 恢复出厂/标定

**实施步骤**:
1. 加系列集合与查表分支，删内联 105 行。
2. 补单测；同步 AGENTS.md、docs/gotchas.md、components/share/iap.js 注释。

**验证方法**: `cd controller/python && py -3.12 -m pytest qa_api/tests -q`（125 passed）；`py -3.12 parse_iap_bin.py <mpp420 .kingkong.bin>` 输出 dataAddress 0x08018000/0x08018800、upgradeSupported=True；MPP 303 bin → upgradeSupported=False。

**踩坑**: productInfoList 精确 key 不覆盖新版本（MPP 4.2.1+ 需补条目，否则判不支持）；MPP 3.0.3 为空串，只影响 IAP（判不支持），3110 标定的地址取自设备 hallParam，不读 dataAddress（sub_algorithm/main.py 约 1296-1311），空串只在 IAP saveCalibrationData 赋给 ctypes c_uint32 时才会出错；sub_common 恢复 productInfoList 的 326aed1 只在 feature 分支，发布前须合入 sub_common main。

**状态**: 已完成（未提交；真机 MPP 验证 BLOCKED）


### P-20260931: SIRE RSI 自审：自动发现唯一 PROPOSED 发现来自兜底阶段与未分类任务，钩子单腿断流

**日期**: 2026-10-13
**项目**: SIRE v6 RSI 机制自我审查（`D:\sire\AI\AI\sire`）
**状态**: 已验证（run R20261013-063902，RSI-20261013-OUTLIER-BASE → v6.12）
**关键词**: SIRE, RSI, 自我审查, 自动发现, sire_telemetry, PHASE_OUTLIER, CLOSE_HEAVY, TOOL_RETRY, 误报, 遥测钩子, mode unknown, rsi-check, evaluate 方向性, resolve 无校验, v6.12

**需求场景 / 现象**: 用户要求按时间、流程、效率、输出、精准度五个维度自审 RSI 自我优化机制。实测数据：采样时刻遥测库 53 条任务 / 542 条事件（claude 187、codex 355；本轮收尾时已增至 582），findings 表里唯一 PROPOSED 的 `PHASE_OUTLIER:execute` 两条证据都来自 `mode=unknown` 的任务（execute 123s/中位数 10s、539s/24s），建议文本"检查该阶段脚本或规则是否新增低效步骤"无法执行。

**根因**:
1. `classify()` 把没命中任何 `PHASE_PATTERNS` 的调用一律记成 `execute`、Stop 前的等待记成 `reply`，这两个兜底桶的量就是任务规模，与"某个 SIRE 步骤变慢"无关；`PHASE_OUTLIER` 却拿它跟跨任务中位数比，中位数只有 10~24s，3 倍阈值必然被大任务触发。
2. `detect_mode()` 只认最终回复里的 `快速通道：简单任务` / `快速通道：否` 两处标记，飞书转发、automation、子代理回合天然没有标记，53 条里 27 条 `unknown`（51%）。而规则分支写的是 `mode != "fast"`，把 unknown 当 full 算 `CLOSE_HEAVY`，`PHASE_OUTLIER` 又把 unknown 单独当基线桶。
3. 采集面单腿：`~/.codex/hooks.json` 三个事件都挂 `sire_telemetry.py hook`，`~/.claude/settings.json` 只有 Stop（指向 feishu-hub `hook_stop.py`）和 UserPromptSubmit，没有 PostToolUse、没有任何 telemetry 引用，claude 事件止于 10-12 10:50；Qoder `settings.json` 根本没有 hooks 键，`--client` 只允许 claude|codex，本客户端任务永远进不了遥测。SKILL.md:83 与契约"两端钩子"的描述与实际不符，且没有任何存活检查，断流是静默的。
4. 阶段归属靠"先命中的正则"，一次 Bash 里串多条命令只记一个阶段；`ledger` 的 `[\\/]runs[\\/]` 会把 `.sire/runs/` 下的 Playwright 真实场景测试和 `ui_fixture.py` 补丁也算成台账（实测 OPEN 的 `FAST_SCOPE` 就是一次 10.7s 快任务被记了 ledger），`archive` 里混着读 `knowledge/global/KNOWLEDGE_TEMPLATE.md` 和 `snapshot_db.py --help`。
5. `TOOL_RETRY` 名不符实：文档说"同一命令失败 3 次"，代码统计整任务失败数；`tool_failed()` 只认 `is_error/error/exit_code` 等少数字段，421 条工具事件仅 2 条 `ok=0`，该规则事实上不会触发。
6. 门禁侧：`rsi_gate()` 允许状态含 `PROPOSED`，只要最后提交后存在任意一个提案就 PASS，不校验提案是否覆盖本次 diff、是否做过 evaluate，`activate --config-hash` 由调用方随手给、无人比对目录内容（本次用文件 sha256 前 16 位，属自证）。`evaluate` 只有 `after >= target` 一种方向，耗时/误报数这类"越低越好"的指标必须写成上升率，本次第一次 evaluate 就用 `after=3,target=100` 把自己判成 `EVALUATED_FAIL`；失败后 `improvement_metrics` 行无法删除，只能再 evaluate 覆盖状态。`sire_telemetry.py resolve --proposal` 完全不校验提案存在性与状态，实测对 `EVALUATED_FAIL` 提案照样把发现标成 FIXED。

**方案 / 架构**: 本轮按"每个任务最多处理一条 pending"只修 `PHASE_OUTLIER`：新增模块常量 `CATCH_ALL_PHASES = ("execute", "reply")`，`detect()` 的阶段离群循环跳过兜底桶和 `mode == "unknown"` 任务，其余规则与阈值不动。第 2~6 条属独立机制改动，各自要单独立提案，未在本轮动。

**关键文件与接口**:
- `sire/workflow/shared/sire/scripts/sire_telemetry.py:42-46` — `CATCH_ALL_PHASES` 及注释
- 同文件 `detect()` 阶段离群分支 — `if mode == "unknown" or phase in CATCH_ALL_PHASES or value < 120: continue`
- 同文件 `PHASE_PATTERNS`、`classify()`、`tool_failed()`、`detect_mode()` — 后续待改的四个精度点
- `sire_supervisor.py:246,306 rsi_gate()` — 允许 `PROPOSED` 即放行；`sire_rsi.py:37` — 只有 `after >= target`

**验证方法**: 用真实 `detect()` 重放 53 条历史任务：修复前 `PHASE_OUTLIER` 2 条（全 execute、全 unknown），修复后 0 条，`CLOSE_HEAVY=2`、`FAST_SCOPE=1` 与 findings 表一致（无附带损失）。R7 隔离遥测库真实 `analyze`+`pending`：T1 full 任务 execute=600s（中位数 10s）与 unknown 同等任务均不再产生发现；T2 archive=300s 对中位数 20s 连中 2 次转 PROPOSED 并被 `pending` 列出，证明真实阶段离群能力保留。钩子自身开销实测每次事件约 0.10s（裸 python 0.023s）、`analyze` 0.056s，不是瓶颈。rsi-check 由 STOP(`rsi_unregistered_change`) 转 PASS，pending 清空。

**踩坑**: ① 用 SQL 直接往 `tasks` 造数据不会进入检测——只有 Stop 钩子里的 `summarize_task()` 会生成任务行，`analyze` 只处理 `analyzed=0` 的既有行，造场景必须走 `summarize_task`；② `evaluate` 的方向性陷阱会把提案打死，写指标先确认"越高越好"；③ `resolve` 在提案还没激活时就能执行，闭环顺序错了不会报错。

**限制**: unknown 占比 51% 说明"每次回复首行标记"在跨客户端时并不可靠，靠它做统计分桶本身就是精度来源；`pending` 排序 `hits DESC` 无第二排序键，同命中次序不定；`report` 把 prompt 截到 60 字且常截到注入块（`# Files mentioned by the user:`、`<in-app-browser-context`）而不是真实用户意图；遥测没有阶段声明，只有工具正则推断，所以各阶段耗时只能排序、不能当验收数值。

**生效性复核（2026-10-13 同日追加，run R20261013-063902 续）**:
- 记录层：只有 Codex 在写（末事件 10-13 06:44:54）；claude 末事件 10-12 10:50，而 10-12 14:20、10-13 05:20 仍有 Claude 会话转录 → Claude 侧确认断流。Qoder 本端 0 事件（连续 25+ 次工具调用期间"近 10 分钟新事件=0"）。
- 分析层：真在跑——54 条任务全部 `analyzed=1`，无积压。
- 发现层：会自动生成，但输入失真——近 24h 的 54 条任务里 28 条 `unknown`（飞书转发与 automation：天气查询 11s、hyperpersonalized suggestions 31s、飞书相关 515s），约 61% 的观察对象不是 SIRE 回合；队列里剩 `CLOSE_HEAVY` 2/3、`FAST_SCOPE` 1/2 两条 OPEN，逐条核对都是 `.sire/runs/` 正则误分类产物，再命中一次就会转成待处理的假发现。
- 优化层：不自动。`sire_run.py` 与 `sire_supervisor.py` 里没有任何 `sire_telemetry` 调用（grep 计数 0），`pending` 只存在于 SKILL.md:51/83、global-contract.md:88、supervisor.md:27 的文字里；全仓 `runs/` 中含 "telemetry.py pending" 或 "自动优化：" 的只有本轮 run → 该步骤此前从未被任何 agent 真正执行过。
- 门禁层：代码有效。临时 git 仓 + 隔离 RSI 库跑 `rsi_gate()` 五场景：无提案→STOP `rsi_unregistered_change`；最后提交后有 PROPOSED→PASS；唯一提案 EVALUATED_FAIL→STOP；ACTIVE 但早于最后提交→STOP；工作树干净→PASS。但 `rsi-check` 要有人跑 `finalize` 才发生，`D:/sire` 下 `rsi-report.json` 一个都没有 → R9 finalize 从未真实落盘。
- 闭环核对：v6.12 在归档库与工作库均 ACTIVE，`config_hash=015b6c4f7b259e7c`、指标 7 行两库一致；`pending` 现为空。

**结论**: "观察→分析→判门禁"三段在 Codex 侧真实生效；"自动优化"目前是纯文字约定、靠模型自觉，Claude/Qoder 观察通道缺失，因此整体只算半生效。要让它真自动，缺的是两处硬编码：把 pending 接进 `sire_run.py finish`/`sire_supervisor.py finalize` 并在有输出时阻断收尾，以及每客户端的采集存活检查。


### P-20260932: CLOSE_HEAVY/FAST_SCOPE 误报根因：阶段正则把真实场景测试与知识检索记成收尾，detail 截断使复核不可能

**日期**: 2026-10-13
**项目**: SIRE v6.14 遥测阶段归属收紧（`D:\sire\AI\AI\sire`）
**状态**: 已验证（run R20261013-074759，RSI-20261013-PHASECLASS → v6.14）
**关键词**: SIRE, 遥测, sire_telemetry, PHASE_PATTERNS, classify, ledger, archive, CLOSE_HEAVY, FAST_SCOPE, 误报, .sire/runs, knowledge/global, detail 截断, RSI, v6.14

**需求场景 / 现象**: RSI 自动发现的 `CLOSE_HEAVY`（收尾占完整任务 40% 以上）累积到 3 次命中转为 PROPOSED，证据是 `收尾 94s/231s`、`155s/304s`、`419s/912s`；第三条里 ledger 一个阶段就占 419s / 19 次调用。同时 `FAST_SCOPE`（快速通道越界）也在一次 10.7 秒的快任务上误报，唯一越界阶段仍是 ledger。

**根因**: 阶段归属靠 `PHASE_PATTERNS` 对"工具名 + 工具输入 JSON 文本"做先命中先用的正则匹配，两个模式的匹配面过宽：
1. `ledger = sire_run\.py|[\\/]runs[\\/]|[\\/]\.sire[\\/]` —— 任何命令里出现 `.sire/runs/` 路径就算写台账。真实场景测试（R7）的夹具与 Playwright 脚本恰好都放在 run 目录下（`.sire/runs/R…/ui_fixture.py`、`getByRole('button').click()`），于是被整段记成收尾时间。
2. `archive` 里含裸 `knowledge[\\/]+global` —— 读 `knowledge/global/KNOWLEDGE_TEMPLATE.md` 这类检索动作被记成归档收尾。
3. 附带缺陷：钩子把事件 `detail` 截断到 160 字，导致事后无法重新分类核对（现存 161 条 ledger/archive 事件里 145 条已是不可解析的半截 JSON），规则命中对不对根本复核不了。
4. 一次 Bash 里串多条命令只归一个阶段（先命中先用），进一步放大误分类。

**方案 / 架构**: 只收紧匹配面，不动规则编号与阈值：
- `ledger` 改为只认台账写入：`sire_run\.py|journal\.log|run\.json|units\.json|blockers\.md|assumptions\.md|kb-hits\.md|stage-output|\.sire[\\/]current`。
- `archive` 去掉裸 `knowledge/global` 与 `archive[_-]?(db|root|result)`，只认动作：`sire_kb\.py (reindex|add|next-id|export-md|lint)|sire_vector_db\.py (index|migrate)|sire_db_backup|snapshot_db|SIRE_ARCHIVE_(ROOT|DB)`。
- 读知识库改判 `retrieve`（在 retrieve 模式里加 `knowledge[\\/]global`），语义归位而不是简单删掉。
- 事件 `detail` 上限 160→320，保证该规则可被复核。

**关键文件与接口**:
- `sire/workflow/shared/sire/scripts/sire_telemetry.py:31-41` — `PHASE_PATTERNS` 的 retrieve/archive/ledger 三项
- 同文件 `cmd_hook()` — `redact(json.dumps(tool_input…), 320)`
- `sire/.sire/runs/R20261013-074759/evidence/measure_phaseclass.py` — 新旧模式重放对比
- 同目录 `r7_phase_test.py` + `r7_phase_result.json` — 隔离库真实 hook 链路断言

**验证方法**: 用打补丁后的 `classify()` 重放 62 个历史任务（只读生产库）：`CLOSE_HEAVY` 命中 3→0、`FAST_SCOPE` 1→0，ledger 累计 1033s→716s、archive 368s→286s；full 任务收尾占比分布仍为 37/27/23/21/18/12%，即真实收尾工作量照样可见，规则没有空转。R7 在隔离遥测库走真实 `hook → summarize_task → analyze`：`stage-output` 记 ledger、`.sire/runs` 下的 Playwright 夹具不再记 ledger、读 `knowledge/global` 记 retrieve、`sire_kb.py reindex` 仍记 archive，5 条断言全 PASS。`sire_qoder.py selftest` 回归 PASS，`pending` 清空，`rsi-check` PASS。

**踩坑**: ① 写 A/B 度量脚本时不要用 `needle in line` 匹配客户端日志——本端 `sire-telemetry` 字样会先被模型自己写进代码文本里，导致假阳性结论；② 造遥测场景必须走 `summarize_task()`，直接往 `tasks` 插行不参与 `analyze`；③ 断言里截断 `detail[:60]` 会把文件名切掉而误判 FAIL；④ `evaluate` 的指标只认"越高越好"，写 `after<target` 会把提案打死。

**限制**: 阶段归属仍是"从工具文本猜"，不是角色声明，一次调用串多条命令时只能归一个阶段；彻底修需要钩子侧记录显式阶段标记或拆分批量命令，属更大改动，本轮未做。收紧后 CLOSE_HEAVY 在现存数据里 0 命中，若将来真实收尾开销变大，该规则仍会按 40% 阈值报出。


### P-20260933: DPB 407/408 到 409 的 IAP 升级白名单

**日期**: 2026-10-13
**项目**: EncoderPlotter_0903_01 / feature/compatibility
**关键词**: DPB 407, DPB 408, DPB 409, supportedVersions, IAP upgrade matrix, sub_common, dpbFlashLayout, sub_embedded

**需求场景 / 现象**: DPB 409 固件布局已登记，但 DPB 当前固件 407/408 的 IAP 允许版本列表没有 409，因此升级门禁拒绝该升级路径。

**根因**: `sub_common/config.py` 中 DPB 407、408 的 `supportedVersions` 只包含 `[407, 408]`；IAP 依据当前固件配置列表决定是否允许目标版本。

**方案 / 架构**: 在同名兼容分支 `feature/compatibility` 将 409 加入 DPB 407 和 408 的 `supportedVersions`，保持 DPB 409 自身列表为 `[409]`。新增参数化 QA API 测试分别验证当前版本 407、408 能请求 409；root changelog 记录产品行为。子仓先提交，再更新主仓 gitlink。

**关键文件与接口**:
- `controller/python/sub_common/config.py` — DPB `productInfoList` 中 407/408 的升级目标白名单。
- `controller/python/qa_api/tests/test_routes.py` — `test_iap_allows_dpb_407_and_408_to_upgrade_to_409`。
- `CHANGELOG.md` — 用户可见升级支持说明。

**实施步骤**:
1. 更新 DPB 407/408 的 `supportedVersions` 为 `[407, 408, 409]`。
2. 通过 IAP API 假设备路径验证 407 和 408 均下发目标 409，保留已有跨系列和不支持版本拒绝测试。
3. 先提交 sub_common，再更新 root gitlink 并同主仓 QA/changelog 一起提交。

**验证方法**: `py -3.12 -m pytest qa_api/tests`（122 passed）；嵌入式/再标定/v4060 回归（42 passed）；独立审查确认 DPB 409 flashLayout 与 dpbFlashLayout helper 地址、容量一致。测试只验证软件版本门禁和模拟路径，不等同真实设备刷写。

**踩坑**: Pytest `-k` 匹配节点名；初次筛选关键字错误导致 0 selected，按实际测试名调整后 2 passed。软件配置和模拟 API 无法证明设备 bootloader 兼容，升级前仍需在 DPB 407/408 实机验证。

**状态**: 部分完成（代码与软件回归完成；物理设备升级验证待进行）


### P-20260934: 遥测采集看着正常但分析层空转：summarize_task 硬依赖 UserPromptSubmit，自动化/续跑回合没有 prompt 事件就整窗丢弃

**日期**: 2026-10-13
**项目**: SIRE v6.16 遥测回合边界兜底（`D:\sire\AI\AI\sire`）
**状态**: 已验证（RSI-20261013-TURNBOUNDARY → v6.16）
**关键词**: 遥测, summarize_task, UserPromptSubmit, Stop, 回合边界, prompt 事件缺失, 目标续跑, automation, Qoder, CLOSE_HEAVY 失效, v6.16

**需求场景 / 现象**: Qoder 端接入钩子后事件在涨（119 条），但 `tasks` 表只有 1 条且不是本会话的：本会话 117 条事件里有 3 个 `stop`、却只有 0 个 `prompt` 事件（全库 `prompt` 仅 1 条）。结果是本端所有回合都进不了 `analyze`，`CLOSE_HEAVY`/`PHASE_OUTLIER`/`FAST_SLOW` 这些按回合判定的规则对这一端完全失效——表面上"心跳正常"，实际上分析层空转。

**根因**: `sire_telemetry.summarize_task()` 把 UserPromptSubmit 当成回合起点硬依赖：
```
prompts = [r for r in rows if r["event"] == "prompt"]
if not prompts:
    return          # ← 没有 prompt 事件就整窗丢弃
start = prompts[0]["ts"]
```
而自动化/续跑型提示（目标系统注入的 continue、飞书转发、定时任务）不触发 `UserPromptSubmit` 钩子，只有 `Stop`。所以这类会话只有终点没有起点。

**方案 / 架构**: 回合边界改以 `Stop` 为准，`UserPromptSubmit` 降为可选起点——无 prompt 事件时取窗口内最早的非 prompt 事件作为起点、`prompt` 字段留空，`mode` 仍由 Stop 读最终回复判定；有 prompt 时行为完全不变（零回归）。契约 §静默分析同步写明这条口径，防止以后再把它当硬前提。

**关键文件与接口**:
- `sire/workflow/shared/sire/scripts/sire_telemetry.py` — `summarize_task()` 起点选择与 INSERT 的 prompt 取值
- `sire/workflow/shared/sire/references/global-contract.md` — §RSI 自动发现 第 2 条

**验证方法**: 从**生产库**导出本端全部事件灌进隔离遥测库（`SIRE_TELEMETRY_DB`）重放真实 `summarize_task()`：2 个会话 4 个 stop → 修复前 0 个任务，修复后 4 个任务，且阶段分布合理，例如某回合 `总1519s / 工具40 / 失败3`（rules 76s、retrieve 169s、execute 1031s、rsi 127s、archive 84s、ledger 12s、reply 22s）。`ast` 语法校验通过，`rsi-check` PASS，`sire_qoder.py parity` rc=0。

**踩坑 / 注意**: ① 验证"是否真的在采集"不能只看 events 数量，必须看 `tasks` 是否在增长——events 有、tasks 无就是分析层空转；② 重放验证要用生产真实事件灌隔离库，别手造数据（手造容易漏掉 prompt 缺失这种触发条件）；③ 我第一版验证脚本把事件按原 session 插入、却用另一个 session id 调 `summarize_task`，得到 0 任务是测试写错而非代码错——先怀疑量具再怀疑被测物。

**限制**: 兜底起点的 `prompt` 字段为空，`report` 里这类回合看不到用户原话；`mode` 仍依赖最终回复里的快速通道标记，没有标记的自动化回合依旧是 `unknown`（已知项，另行处理）。


### P-20260935: SIRE 三端兼容实测：Codex/Claude 入口副本对 v6.12-v6.17 的关键词覆盖 0/7，且无机制能发现这种漂移

**日期**: 2026-10-13
**项目**: SIRE 三端兼容性复核（`D:\sire\AI\AI\sire`）
**状态**: 已验证（取证脚本 scratch/probe_three_clients.py，run 见本次台账）
**关键词**: SIRE, 三端兼容, Codex, Claude, Qoder, 入口副本漂移, AGENTS.md, sire-reminder.txt, memory, hooks.json, config.toml 信任哈希, 别名 junction, COLLECTION_DEAD, parity, 链式钩子, feishu-hub

**需求场景 / 现象**: 要判断"Codex 与 Claude 是否仍与唯一源兼容"。实测关键词覆盖：唯一源 `global-contract.md` 命中 `Qoder / pending / COLLECTION_DEAD / sire_close / sire_qoder / 强制 / parity` **7/7**；`~/.codex/AGENTS.md`（3033 字节）**0/7**；`~/.claude/sire-reminder.txt`（2587 字节）**0/7**；`~/.qoder-cn/memory/sire-mandatory-workflow.md` 4/7。也就是说 v6.12–v6.17 的改动（三端表述、finish 强制核对 pending、COLLECTION_DEAD、sire_close 合并收尾、parity/role）只有写它们的人知道，另两个客户端的入口副本一字未提，而且**没有任何机制能发现这种漂移**——三份副本都是人手改写的摘要，连"## 简单任务快速通道"整段都不含（`section()` 取不到），无法做指纹比对。

**根因**:
1. 入口副本制度是"摘要 + 人工同步"：契约只说"修改本节时同步 Codex AGENTS.md 与 Claude reminder"，没有任何命令校验，副本与源之间没有可比较的结构（既非同一文件也非同一小节）。
2. 采集面本来就三端不齐：Codex 钩子三事件走 `~/.codex/skills/ai-dev-sire-workflow/scripts/sire_telemetry.py`（别名路径）在采；**Claude 的 Stop 与 UserPromptSubmit 都被 feishu-hub 占用**（`hook_prompt.py` / `hook_stop.py` + `Get-Content sire-reminder.txt`），对 `sire_telemetry` 的引用是 0，所以它的采集完全缺失（库里 17 条 claude 任务都是更早配置留下的）；Qoder 是我这次接上的四事件。
3. 别名即单点：Codex 钩子命令硬编码别名目录路径，junction 一旦失效采集会静默断掉；Claude 的 `settings.hooks` 无 PostToolUse；Codex 另有 `config.toml` 的 3 条 `[hooks.state...]` 信任哈希——**改 hooks.json 需重新信任**，否则钩子不生效且无提示。
4. 分档委派能力不齐：Claude 有 16 个 `~/.claude/agents/sire-*.md`（含 low/mid/high）；Qoder 没有子代理定义也没有 `model` 参数，只能靠 `sire_qoder.py role` 生成委派文本；Codex 侧未验证。
5. `COLLECTION_DEAD` 从配置反推"应采集客户端"，未配置的客户端隐形 → Claude 永远不报警，规则只能测"接过又掉"的，测不出"根本没接"。

**方案 / 建议架构**:
1. **入口副本改为同源生成 + 指纹校验**：新增 `scripts/sire_entry.py`，`render --client codex|claude|qoder` 从 `global-contract.md` 生成固定小节（含源 SHA 前 12 位与"由脚本生成，勿手改"标记），`check` 比对三端指纹并把不一致变成一条发现（等价于把 `parity` 从 Qoder 单端扩成三端）；这一步先做，否则后续任何机制改动都会继续静默漂移。
2. **Claude 采集用链式而非抢占**：在 feishu-hub 的 `hook_prompt.py` / `hook_stop.py` 内追加调用 `sire_telemetry.py hook --client claude`（或同事件加第二个条目，但 Qoder 实测同事件多条目后曾出现停采，链式更稳）；Codex 侧改 `hooks.json` 后必须提醒重新信任。
3. **钩子命令不再指向别名**：统一指向唯一源真实路径（或由 `sire_paths.py` 生成的启动器），`check` 同时验证"别名解析 == 唯一源""脚本文件存在""近 N 小时有心跳"三件事。
4. **显式客户端清单**：`sire_clients.json` 声明应当接入的客户端与必备事件，缺失=发现（`CLIENT_NOT_INSTALLED`），补上"根本没接"的盲区。
5. **分档文本同源**：把 low/mid/high 的委派约束也收进唯一源生成，Claude 用它生成 `agents/sire-*.md`、Qoder 用 `sire_qoder.py role` 消费，Codex 待验证后接入。

**关键文件与接口**:
- `~/.codex/AGENTS.md`、`~/.codex/hooks.json`、`~/.codex/config.toml`（3 条 hooks 信任项）
- `~/.claude/sire-reminder.txt`、`~/.claude/settings.json`（Stop/UserPromptSubmit → `D:\sire\AI\AI\feishu-hub\executors\claude\hook_*.py`）、`~/.claude/agents/sire-*.md`（16 个）
- `~/.qoder-cn/settings.json`（4 事件 + telemetry）、`~/.qoder-cn/memory/sire-mandatory-workflow.md`、`sire/workflow/shared/sire/agents/qoder/README.md`
- 三端别名均解析到 `D:\sire\AI\AI\sire\workflow\shared\sire`（junction 正常，工作流本体是真兼容的）

**验证方法**: `scratch/probe_three_clients.py`（输出 `three_clients.json`）逐端打印别名解析、钩子事件与命令、脚本是否存在、副本关键词覆盖；漂移比对用 `section()`+`sha256[:12]`，副本无该段即判"不可比对"，本身就是要修的缺陷。

**限制**: 本次为只读复核，未改任何机制；`sire_entry.py`、Claude 链式钩子、`sire_clients.json` 均属新的机制改动，需各自走 RSI 提案，Claude 那项还要用户授权（涉及 feishu-hub 现有集成）。另注：`plugin:computer-use` 现已在 Qoder 暴露并实测可用（`list_windows` 返回真实窗口列表），此前记录的"R10 本端不支持"已失效，需更正 README 与契约。


### P-20260936: DPB MR复审：导入写入校验与packed版本转换

# GitLab MR repeat review 2026-10-13

Remote branches fetched. Embedded HEAD 4ad0fe3d997c70f8365a64a5fa82d875bfa002c9; common HEAD f8825057831178e41502077789b8b45e651c63de. No source update since previous review. Earlier positive conclusion corrected after following additional caller paths.

P1 embedded: new DPB capacity check is only in writeEncoderData. EncoderCommandCalibrationWriteData in parent Encoder.py calls writeEncoderDataV303, whose imported current/generated Q/T branches call writeFlash and eraseAndWriteFlash directly. The latter erases before writing and has no capacity check. Oversized imported T reaches erase instead of preflight rejection. Firmware enforcement and physical consequences have not been tested. Suggested checking all selected buffers before any erase; cross-version DPB408/409 imported T is a concrete trigger.

P2 common: runpy execution of dpbFlashLayout.py confirmed firmware_number(0x04000A00)=410 and firmware_number(4010)=4010. Project three-part concatenation requires 4010. Current 408/409 remain unaffected. Suggested matching packed/UI conversion and tests.

Cross-repository dependency: new top-level import requires coordinated common/embedded pins and common-first merge.

GitLab authenticated browser: existing comments read; new public correction comments posted to both MRs; Activity counts changed from 1 to 2 and full posted text verified. No Approve or merge action. Real hardware not exercised. No code changed.

Keywords: GitLab MR review, DPB 408 409, imported calibration, writeEncoderDataV303, eraseAndWriteFlash, firmware_number, packed 4.0.10, 4010, Flash preflight.


### P-20260937: DPB导入数据擦除前预检与packed版本修复

# MR30/MR31 findings repaired

User authorized fixing earlier review findings and updating existing MRs. Used existing clean feature/compatibility branches, no parent pin commit before child merges. Model gate: cross-module write ordering and version encoding require current model; no delegated agents.

Common commit 3b3fa720178e7f859786b4c78610fa0747d6bdb5 replaces arithmetic packed version conversion with three-component decimal concatenation. Embedded commit f3b3a599e6914824a759127cd35b00cd1ee0733c checks all imported P/Q/T buffers before any device operation and checks direct writeFlash before erase. Missing buffers reject before operation. Added parameterized boundary and overflow regression tests.

Review: actual write paths share preflight protection; both current and generated buffers checked before PARAMS is written. Existing normal calibration preflight retained. Other series/algorithm behavior unaffected by DPB4060 guard. Packed/UI conversion matches Arguments convention.

Validation: py -3.12 -m pytest sub_embedded/tests qa_api/tests sub_algorithm/tests/test_v4060_runtime_config.py -q: 181 passed, 7 subtests passed, one existing Starlette/httpx deprecation warning. Submodule git diff --check passed. Overflow tests verify no ensure/stop/write call, direct write tests verify no eraseAndWriteFlash call; boundary DPB408/409 writes pass. No hardware connected or flashed, hardware acceptance remains unverified.

Published: both commits pushed to existing feature branches. Authenticated GitLab Activity shows added commits and new fix comments, Overview counts rise to 3. No approve or merge performed. Parent checkout gitlinks now show child commits but are intentionally uncommitted pending child merges under repository policy.

Keywords: DPB Flash preflight, writeEncoderDataV303, imported P Q T, firmware_number, packed 4010, MR30 MR31, regression.


### P-20260938: 飞书卡片队列被单条非法卡片头阻塞；Qoder 钩子两条隐蔽失效点

**日期**: 2026-10-13
**项目**: 全局工具 / D:\sire\AI\AI\feishu-hub
**关键词**: 飞书卡片, outbox 头阻塞, HTTP Error 400 Bad Request, head-of-line blocking, blocked 保序键, status DEAD, UnicodeEncodeError surrogates not allowed, sys.stdin.buffer, GBK 控制台, hook_event_name, settings.json hooks 不生效, qoderclicn headless, FEISHU_HUB_TASK_ID, local image markdown

**需求场景 / 现象**:
1. `~/.feishu_hub/hub.log` 持续刷 `WARNING [出口] 发送失败 outbox=455 第642次: HTTP Error 400: Bad Request`，同一 `session_id` 后面积压 25 条 `PENDING` 且 `attempts=0` 从未被尝试——出站队列对一个会话整体失联 15 天，而日志只看得到那一条坏卡片。
2. Qoder 桌面轮次结束后飞书没有卡片：`settings.json` 已加 Stop 条目但整场会话不执行；改到新会话又报 `Hook 输入不是有效 JSON`，实际异常是 `UnicodeEncodeError: 'utf-8' codec can't encode character '\udcaa'`。

**根因**:
1. 载荷非法：卡片 markdown 含本地图片 `![阿砾步行](/D:/code/GAME/.../CHR_Hunter_Walk.png)`，飞书卡片只接受 http(s) 图链，整卡 400——永久性错误，重试不可能成功。队列层再放大：`service.flush_outbox()` 按 id 顺序发送，以 `reply_to or session_id` 为保序键，一条失败就把该键加入 `blocked`，同键后续全部跳过。
2. Qoder 客户端在会话 `initialize` 时把每组 `{matcher, hookCallbackIds}` 一次性交给 agent runtime（asar 内 `createHooks` 与 init 参数 `e.hooks=t`），运行中改 `hooks` 对当前会话无效；同一事件支持多条目。钩子脚本用 `sys.stdin.read()` 在 GBK 控制台解出孤立代理项，随后任何 `.encode("utf-8")` 抛异常，而客户端吞掉 stderr。

**方案 / 架构**: 三段式：队列加终态、构造侧堵死复发、验证侧留证据。
- 出站队列新增 `DEAD` 终态：`getattr(e, "code", 0) == 400` 判为永久失败，作废并返回 True（不加入 `blocked`），5xx/网络错仍走原指数退避重试。否决"重试 N 次后放弃"——按 300s 上限算，一条毒卡片要占 1.5 小时才放行同组后续。
- `outbox_unsent_for_task()` 从 `status!='SENT'` 改为 `status NOT IN ('SENT','DEAD')`，否则作废卡片让任务永久停在 RESULT_SAVED 不能转 DONE。
- `feishu.compact()` 里 `_plain_local_images()` 把非 http 图链降级成「（图片：路径）」；本地截图在飞书本来也渲染不出来，降级不丢信息。从构造侧堵死复发，历史坏载荷仍可人工按 `outbox.payload` 找回。
- 钩子统一 `sys.stdin.buffer.read().decode("utf-8", "replace")`；JSON 解析与上报分路 try；traceback 落盘 `~/.feishu_hub/hook_qoder.log`（客户端不给 stderr）。

**关键文件与接口**:
- `feishu-hub/hub/store.py` — `outbox_dead(oid, err)`、`outbox_unsent_for_task()`
- `feishu-hub/hub/service.py:73 _send_row()` — 400 分支；`flush_outbox()` 的 `blocked` 保序键语义
- `feishu-hub/hub/feishu.py` — `_LOCAL_IMG`、`_plain_local_images()`、`compact()`
- `feishu-hub/executors/qoder/hook_stop.py` — `main()` stdin 解码与分路异常、`LOG_HOME`
- `feishu-hub/tests/test_hub.py` — 400→DEAD、毒卡片不堵同会话、markdown 降级三项检查
- 配置：`~/.qoder-cn/settings.json` 的 `hooks.Stop`（遥测 + feishu-hub 两条并存）

**实施步骤**:
1. 先证伪"钩子没装"：查遥测库同事件有无 `stop` 行——有 stop 但无卡片，说明事件触发了、是第二条钩子没跑或跑了失败。
2. 队列侧：加 DEAD 终态 → 400 直接作废且不阻塞同组 → 修 unsent 统计口径。
3. 构造侧：`compact()` 降级本地图片 markdown。
4. 钩子侧：UTF-8 读 stdin + 分路 try + 日志落盘（含 verdict）。
5. 用 headless 会话验证整链，不必等真机桌面轮次。

**核心代码片段**:
```python
# service._send_row 异常分支
if getattr(e, "code", 0) == 400:
    store.outbox_dead(r["id"], str(e))
    if r["task_id"] and store.outbox_unsent_for_task(r["task_id"]) == 0:
        store.cas(r["task_id"], store.RESULT_SAVED, store.DONE)
    return True          # 不进 blocked，同会话后续继续发
# feishu.py
_LOCAL_IMG = re.compile(r"!\[[^\]]*\]\(\s*(?!https?:)([^)]*)\)")
def _plain_local_images(t):
    return _LOCAL_IMG.sub(lambda m: "（图片：%s）" % m.group(1).strip(), t)
# hook 读入
raw = sys.stdin.buffer.read().decode("utf-8", "replace")
```

**验证方法**:
- `python tests/test_hub.py` → 82 项，新增 3 项 PASS（余 2 项失败为既有）。
- 重启 `FeishuHub` 计划任务后查库：455 变 `DEAD`，被压 25 条全部 `SENT`，`PENDING=0`。
- 钩子链路：`qoderclicn -p --output-format json "只回复四个字：钩子自检"`，环境剔 `QODER_AGENT_SDK*` 前缀、**故意不带 `FEISHU_HUB_TASK_ID`**（带上即走抑制分支），跑完看 `hook_qoder.log` 出现 `verdict=sent`，`outbox` 新增 `executor=qoder`、`task_id=''` 的 SENT 卡片。脚本 `scratch/probe_stop_hook.py`。

**踩坑**:
- 把 `UnicodeEncodeError` 误标成"输入不是有效 JSON"，因为 JSON 解析和上报共用一个 `except ValueError`（`HubError` 也继承它）——分路 try 才看得见真因。
- 曾据"装完遥测钩子下个提示词就生效"断言钩子热加载；本次同一会话新加的 Stop 条目整场不跑、新会话立刻跑，旧结论作废。
- 判定"卡片没发"不能只看有没有异常返回：客户端丢 stderr，必须自带落盘 verdict。
- `desktop_queue` 能力位对 Qoder 恒 False（客户端没有桌面收件队列），别照抄 Codex 的 True。

**状态**: 已完成


### P-20260939: DPB 4.0.10 版本码 4010：patch 两位数让码值不可比，比较必须走三元组

**日期**: 2026-10-14
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01（分支 feature/iap-ota-sn）
**关键词**: DPB 4.0.10, 4010, 410, 版本码, DATA_ADDRESS_LAYOUTS, parse_iap_bin, tryDpb, dpbFlashLayout, firmware_number, iap_sn_restore, MIN_SOFTWARE_VERSION_FOR_SN, NUM_TO_HEX, 0x04000A00, 补丁号两位数

**需求场景 / 现象**: 固件组交付 DPB V4.0.10 的 BIN 解析规则（`Arguments.version.software = 0x04000A00`），要求上位机支持。改动前用真实产物跑 `parse_iap_bin.py` 直接失败：`[IAP] bin解析失败：未找到有效ARGUMENTS结构 size=264392`，前端表现为"bin文件解析失败，请更换有效的固件文件"。

**根因**: 项目的版本码是十进制拼接 `int(f"{major}{minor}{patch}")`，一直默认每个分量一位十进制数字（4.1.2→412）。patch 到 10 之后这个前提崩了：
1. `parse_iap_bin.tryDpb` 的 DPB 白名单只到 `0x04000900: 409`，没有 `0x04000A00`，判别器直接返回 None。
2. 码值不再单调：4010（4.0.10）在数值上 **大于** 422（4.2.2），所有 `>= 422` 式门禁（IAP 后 SN 写回、0x83 指令读 SN 能力）会把 DPB 4.0.10 判成比 4.2.2 新。
3. 显示串按三位拆 `f'{v//100}.{v//10%10}.{v%10}'` → 4010 显示成 "40.1.0"。
4. `sub_common/dpbFlashLayout.firmware_number` 用 `*100/*10` 折位，把 0x04000A00 折成 410，查不到 `LAYOUTS[4010]`，Flash 预算校验整段跳过。
5. 前端两处解析副本口径还不一样：`analyzer.js` 把紧凑码拆成 `[首位, 中间, 末位]`（"4010"→[4,1,0]），`device.js` 直接比码值。

**方案 / 架构**: 定一条口径并全栈落到位，不做全局重编码（把码值换成 `major*10000+minor*100+patch` 会牵动 config.py 表键、子仓 sub_algorithm 的算法侧码值与前端，9 年存量承担不起）：
- 码值继续用拼接形式（4.0.10=4010），**比较一律先解成 (major, minor, patch) 三元组**；规则固定为"第一位 major、第二位 minor、其余整体 patch"，要求 major/minor ≤ 9（`validSoftware` 本就如此约束）。
- Python 侧新增 `controller/python/firmware_version.py`（`version_triple` / `version_at_least`），接受 4010、"4.0.10"、"4010"、"v4.2.2-test"、0x04000A00、{h1,h2,h3}（dict 或 ctypes 对象）、三元组七种形态；解不出统一返回 None，门禁按"版本未知不放行"。
- 前端同源一份 `shared/firmware_version.js`，`analyzer.js`、`device.js` 删掉各自的解析副本改引用它，消息文案与 i18n key 一字不改。
- `parse_iap_bin` 白名单补 `0x04000A00: 4010`，显示串改由打包字节生成；`DATA_ADDRESS_LAYOUTS[106]` 的 `(408, 9999)` 行天然罩住 4010（4.0.10 与 4.0.9 的 P/Q/T 完全相同），只补注释不改表。
- 子仓 `dpbFlashLayout.firmware_number` 改成拼接规则；`LAYOUTS[4010]` 预算与 409 相同（T 170KiB / Q 2048 / P 0x08040000 30KiB）。

**关键文件与接口**:
- `controller/python/firmware_version.py` — 版本码口径唯一真源（Python 侧）
- `controller/python/parse_iap_bin.py:395` — `tryDpb` 的 `software_versions` 白名单；`:424` 显示串
- `controller/python/iap_sn_restore.py:12` — `iap_sn_restore_supported` 改走 `version_at_least`
- `controller/python/Encoder.py:4240` — SN 能力诊断块改按三元组比
- `shared/firmware_version.js` — 前端同源实现
- `components/analyzer/analyzer.js:427`、`components/encoder/device.js:3251` — 两处 SN 能力判定
- `controller/python/sub_common/dpbFlashLayout.py:13` — `firmware_number`

**实施步骤**:
1. 先用真实固件产物复现失败，再动代码（ Downloads 下 DPB10/15/20/25/30 的 `.kingkong.bin` 与一份明文 bin）。
2. 落 Python/JS 两份同口径的三元组解析，门禁全改三元组比较。
3. 补白名单与显示串；布局表只加注释。
4. 子仓改 `firmware_number`（子先父后，两层提交）。
5. 规则文档入库 `docs/iap-bin-rules/`，`docs/README.md` 加索引行。

**核心代码片段**:
```python
def _from_code(code):
    text = str(code)
    if code <= 0 or len(text) < 3 or not text.isdigit():
        return None
    return int(text[0]), int(text[1]), int(text[2:])   # 4010 -> (4, 0, 10)

def version_at_least(value, minimum):
    actual, threshold = version_triple(value), version_triple(minimum)
    if actual is None or threshold is None:
        return False
    return actual >= threshold
```

**验证方法**: `cd controller/python && py -3.12 -m pytest qa_api/tests`（138→140 passed，含 `qa_api/tests/test_dpb_v4010_bin.py` 13 条：七种形态同解、4010<422、合成 0x39010 镜像识别为 4010/"4.0.10"、DPB 预算命中、4.0.9 不回归）；`py -3.12 -m pytest sub_embedded/tests`（39 passed）、`sub_algorithm/tests/test_dpb_flash_layout.py`（6 passed，`get_layout(410)` 仍必须抛错）；`node --check` + 19 条断言跑 `shared/firmware_version.js`；真产物 8 个文件全部 `status=ok`，BIN 长度与 `polyfitDataSize` 对上文档 §0/§4.3（DPB25：274760B、T=160424、T 结束 0x0802C2A8）。

**踩坑**:
- 文档自身也可能错：单文件版 V410 规则把 `0x82` 写成 31 字节负载差异，合并版更正为两版本都 59 字节——`build_info.py` 本来就兼容。以"最新合并版"为准，别照单份文档拉改协议。
- `version_triple` 若对非 str/int 对象走 `str(value)` 兜底，`object()` 的 repr 里含长数字串会被当成版本号误命中；必须限定只对 str 做文本解析。
- 未登记预算的 DPB 版本（407）走无守卫的 `get_layout` 会抛 ValueError 打断写入，合并时这类"顺手去掉守卫"的改动要保留守卫分支。

**状态**: 已完成（代码 + 真 bin 离线实测 + 自动化回归；接读取器的在线路径未验证——本机无设备）


### P-20260940: develop 与在途功能同改一条链的合并：预演、子仓 gitlink 双向核对、静默损坏检测

**日期**: 2026-10-14
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01（feature/iap-ota-sn ← origin/develop）
**关键词**: 合并冲突, git merge-tree, 子模块 gitlink, merge-base --is-ancestor, 语义冲突, back-merge-check, EncoderBase.py, device.js, CHANGELOG, 静默损坏, 双侧同改, sub_common, sub_embedded

**需求场景 / 现象**: 用户要求"将 origin/develop 合并到当前分支，包括子仓库，当前仓库的代码为基础，整合进 origin/develop 的代码"。本分支领先 145 提交、落后 8 提交，而那 8 条提交恰好是本分支正在做的同一件 DPB 版本工作（另一条分支上改的），两侧都改了 `dpbFlashLayout.firmware_number`、`EncoderBase.py`、`config.py`、`device.js`、`CHANGELOG.md`。

**根因**: 危险的不是 git 报的 4 处冲突，而是三类 git 不响的东西：
1. 子仓两侧各自前移，主仓只看到一个 gitlink 冲突，真实内容冲突埋在子仓里（`EncoderBase.py` 五处、`dpbFlashLayout.py`/`config.py`）。
2. 双侧用**不同写法实现同一个修复**（`firmware_number` 一个用 f-string 拼接、一个用 `"".join(...)`），文本冲突看似随便挑一边都对，留下两份就是漂移。
3. 冲突块外的"共同尾部"行属于其中一侧的结构改造——照抄会带进引用未定义变量的死代码，`node --check` 与测试都不报。

**方案 / 架构**: 顺序固定为：预演 → 清点共同触碰面 → 在途工作先落提交 → 子仓 merge（子先） → 主仓 merge → 逐文件用"与合并前对比"复核 → 全量测试 + 真产物复跑。
- 预演不改工作区：`git merge-tree --write-tree --name-only HEAD origin/develop`，一次拿到冲突清单（含 submodule 类型冲突）。
- 共同触碰面用 `git diff --name-only <merge-base> <side>` 两侧交集算，**别用 `comm`**：git-bash 下 `sort` 与 git 的排序口径不一致，实测把 7 个真实重叠文件漏成 0 个，改用 grep 白名单才对。
- 工作树必须干净才合：在途功能按用户批准先提一个 commit（含子仓 gitlink），CHANGELOG 条目留到合并冲突里一并解决，避免二次冲突。
- 子仓合并：先确认本地同名分支是记录提交 `89ea339` 的祖先再 `--ff-only` 对齐（不是祖先就不动它），然后 `git merge <develop 侧提交>`，解完在子仓提交，回主仓 `git add <子模块路径>` 记 gitlink。
- 取舍口径：函数实现两侧等价时采 develop 的写法（避免以后再冲突）；行为相关的一侧更完整时（`writeFlash` 的进度/重试签名、未登记版本跳过校验的守卫）保留本分支，并在 merge message 里写明为什么。

**关键文件与接口**:
- `controller/python/sub_common` 73e616e → merge `3dc6ebd`（并入 develop 的 `f09ac0f`）
- `controller/python/sub_embedded` 89ea339 → merge `2ba14ad`（并入 `c339ac1`，`EncoderBase.py` 五处冲突）
- `components/encoder/device.js` — 保留本分支 DPB/DPT-G1 分支与 `calibrationLog` 字段，采纳 develop 无前缀消息处理
- 主仓 merge 提交 `65639c24`

**实施步骤**:
1. `git fetch origin` + 各子仓 `git fetch origin`（主仓 fetch 不带子仓对象，子仓不 fetch 就查不到 develop 侧提交）。
2. `git merge-tree --write-tree --name-only HEAD origin/develop` 预演。
3. 两侧 `git diff --name-only <base>` 求交集，逐文件判断是文本冲突还是语义重叠。
4. 在途改动提交 → `git merge --no-ff origin/develop` → 进子仓解内容冲突并提交 → 回主仓 `git add` 子模块路径与文本冲突 → 提交。
5. 复核：`git diff HEAD^1 -- <冲突过的文件>`、`git -C <子仓> diff <合并前提交> HEAD --stat` 加 `grep "^-"`，确认我们侧没有行被吃掉。
6. 闭环核对：`git log HEAD..origin/develop` 为空 **且** 两个子仓 `merge-base --is-ancestor <develop 侧提交> HEAD` 与 `--is-ancestor <我们侧提交> HEAD` 都成立。

**核心代码片段**:
```bash
# 只读预演，不动工作区
git merge-tree --write-tree --name-only HEAD origin/develop
# 子仓两侧都必须可达，才算"包括子仓库"合干净
git -C controller/python/sub_common merge-base --is-ancestor f09ac0f HEAD
# 我们侧有没有被吃掉：只看删除行
git -C controller/python/sub_embedded diff 89ea339 HEAD -- EncoderBase.py | grep "^-" | grep -v "^---"
```

**验证方法**: 合并后 CI 五组 + 主仓四组 unittest 全绿（`qa_api/tests` 140 passed、`sub_embedded/tests` 39、`test_v4060_runtime_config.py` 32、`test_dpb_flash_layout.py` 6）；`git diff HEAD` 在暂存前逐个冲突文件复核净变化只含预期项；真产物 8 个 DPB 4.0.9/4.0.10 bin 复跑 `parse_iap_bin.py` 全部 `status=ok`。

**踩坑**:
- 用脚本批量剥冲突标记时，"冲突块之后的共享尾部"可能是另一侧的代码——本次带进 4 行 `this.$store.commit(..., string: text)`，`text` 在本分支作用域里不存在，语法检查照过，靠 `git diff HEAD` 才发现。
- develop 新增的测试是给 develop 的调用管线写的：本分支异常收尾要经 `self.encoder`、写 Q 区前调 `self.getFlashRegionSize`，裸对象缺这两处会让本该报"Flash overflow"的用例被 `AttributeError` 顶掉。补桩而不是削断言。
- 文档也会自相矛盾（同一版本的 0x82 长度两份文档不一致），合并前先确认手上是不是最新合并版。

**状态**: 已完成（本地提交，未推送、未建 MR；接读取器的在线路径未验证）


### P-20260941: 端口回收与Boot混合扫描代码审查检查点

**日期**: 2026-10-14
**项目**: driverSoftware
**关键词**: Windows端口占用, server.py, server.exe, netstat, CIM, taskkill, 外部进程保护, 混合总线, Bootloader扫描, pytest

**需求场景 / 现象**: Review 当日端口回收与 Boot 混合总线扫描提交，需要判断自有服务清理是否越界，以及 Boot 诊断失败是否破坏 APP 设备发现结果。

**根因**（问题类必填）: 本次审查没有确认新的缺陷。审查边界的关键在于端口归属证据不足时必须按外部进程处理，以及 Boot 探测是诊断增量而不能覆盖 APP 主结果。

**方案 / 架构**: 对端口回收检查先以 netstat 映射占用 PID，再通过 CIM 取命令行；任一 owner 无法确认属于本项目时不杀任何占用者。Boot 扫描异常应 fail-open，并保留已发现的 APP ID。前端将两类 ID 合并去重后供选择。

**关键文件与接口**:
- `server.py`：`_pids_on_port`、`_cmdline_of`、`_is_our_server_proc`、`_reclaim_port`、`api_probe_device_ids`。
- `frontend/js/app.js`：连接及切换设备时合并 APP/Boot ID。
- `tests/unit/test_port_reclaim.py`、`tests/unit/test_probe_boot_mode.py`。

**实施步骤**:
1. 按本机日期筛选全部提交并审查改动与上下文。
2. 运行定向 pytest；Windows 端口行为测试在非 Windows 环境应跳过。

**验证方法**: 2026-10-14 本机 `git diff --check 8c2bc669^..dc0980af` 通过；`PYTHONPATH=<仓库根> pytest -q tests/unit/test_probe_boot_mode.py tests/unit/test_backend_port_binding.py tests/unit/test_port_reclaim.py` 得 45 passed。未运行 GUI、真机或完整打包。

**踩坑**: Windows PowerShell 下直接运行 pytest 时仓库根未自动出现在 Python 模块搜索路径，收集时报 `ModuleNotFoundError: No module named 'server'`；设置 `PYTHONPATH` 为仓库根后同一测试集通过。审查测试失败要区分环境导入问题和产品断言失败。

**状态**: 已完成


### P-20260942: 飞书文档不可读时用历史台账定位等价基线

**日期**: 2026-10-14
**项目**: MES / D:\code\mes
**关键词**: 飞书文档不可读, lark-cli 未安装, 内嵌浏览器未登录, 等价基线定位, accounts.feishu.cn 登录页, 面包屑标题, evidence 截图, SIRE run 复用

**需求场景 / 现象**: 用户只给一个飞书 wiki 链接要求"结合该文档分析代码"，但本机 `lark-cli` 未安装（`cmd /c where lark-cli` 为空），Qoder 内嵌浏览器打开链接被重定向到 `https://accounts.feishu.cn/accounts/page/login?...redirect_uri=...`，截图还报 `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`（viewport 0x0，只能 take_snapshot）。既不能调 API 也不能登录。

**根因**: 飞书文档读取有两条通道，本机两条都断——CLI 通道缺二进制与 auth login；浏览器通道是未登录的内嵌实例且无可视 surface。继续找第三条通道（WebFetch）同样会撞登录墙，属无效绕路。

**方案 / 架构**: 不绕路，改为"证明本地存在该文档的等价基线"，三步交叉定证：
1. 用 `take_snapshot`/`list_pages` 拿到重定向 URL 里的 wiki token，确认目标资源；
2. 在仓库自己的运行台账里找该文档的历史写入记录（`.sire/runs/<RUN>/` 的 journal.log、knowledge-record.md、evidence/*.jpg、导出的 HTML），本例命中 `R20261014-084207/feishu-v1.3.html`；
3. 用截图里的**面包屑标题**（"MES及追溯系统"）+ **章节号与表格行**（§3.4.3 的"霍尔底涂/分板/标定/三防/成品检"）与本地 Markdown 逐行比对，行号级一致即认定同源。
被否决方案：凭仓库线索猜文档内容（不可验证）、要求用户复制粘贴全文（成本高且丢排版）。

**关键文件与接口**:
- `D:\code\mes\.sire\runs\R20261014-084207\evidence\feishu-dpb-final.jpg` — 截图含飞书面包屑标题与 §3.4.3 表格，是等价性主证据
- `D:\code\mes\docs\requirements\MES-综合需求规格说明书.md:314-330` — 与截图逐行对应的本地基线
- `mcp__browser-use__take_snapshot` — 登录墙判定用，不要用 take_screenshot（内嵌浏览器无 surface 会失败）

**实施步骤**:
1. `list_pages` 读重定向 URL，确认是登录墙而不是渲染失败；
2. `grep -rIl "<wiki token>"` 与 `grep -rIoh "https://[^ ]*feishu.cn/[a-z]*/[A-Za-z0-9]\{15,40\}"` 在台账/文档里找历史引用；
3. 找同项目历史 run 的 evidence 截图，用 Read 打开图片核对标题与章节表格；
4. 交付时把"线上增量未读"写成显式前提，并给用户一条补取路径（登录内嵌浏览器 / 导出 docx 到 docs/ / 装 lark-cli 并 auth login）。

**验证方法**: 同一结论需两条互相独立证据（截图表格行 vs 本地 MD 行号；或历史 run 产物 vs 知识记录 F-074）。只有一条时不得声称"该飞书文档就是本地这份"。

**踩坑**: 只看截图缩略图不足以定证，必须能读出面包屑标题；`.sire` 台账里往往没存 wiki URL，只存了截图，所以 token 反查会全空——这时改按"文档标题 + 章节内容"匹配，而不是继续找 URL。

**状态**: 已完成，方法可直接复用于其他"用户给外部文档链接但客户端未登录"的场景


### P-20260943: driverSoftware Job 8909 台架脚本漏包修复

**日期**: 2026-10-14
**项目**: driverSoftware / D:\code\driverSoftware
**状态**: 修复已提交；相关自动化和原始目录打包验证通过，完整应用构建等待同版依赖环境复核
**关键词**: 打包失败, Nuitka, GitLab Job 8909, driverSoftware, raw-dir, build.bat, dc946d7

**需求场景 / 现象**: 用户提供 GitLab build-win-smoke 日志，提示 `tools\force_calib\calibrate_force_v2.py` 未随包走。

**根因**: Nuitka 的数据文件收集把台架 `.py` 源码过滤掉。

**方案 / 架构**: 改用 `--include-raw-dir=tools/force_calib=tools/force_calib` 原样递归复制，并保留编译后实物断言。提交 `dc946d7`（fix: 修复 Nuitka 漏收台架运行脚本）。未 push。

**关键文件与接口**: `server.py`; `scripts/build.bat`; `scripts/build_mac.sh`; `tests/unit/test_run_script_entry.py`。

**实施步骤**:
1. 修复源目录收集参数与两平台提示。
2. 同步测试和用户文案。
3. 运行相关测试和独立 Nuitka 产物检查。

**验证方法**: pytest 47 passed；独立 Nuitka 真实编译收集 21 个文件，检查两个关键脚本均在产物。整项目构建因本机 wheel 缺被显式 include 的 `dataStructV4026` 停止，未声称完整包通过。

**踩坑**: raw-dir 必须使用 `源=目标` 写法；不完整 wheel 环境的失败与 Runner 日志显示的漏包根因需分开记录。


### P-20260944: 标定汇总 CSV 多语言和 Excel 写入边界修复

**日期**: 2026-10-15
**项目**: EncoderPlotter_0903_01
**状态**: 源码修复与主进程处理器检查完成；真实应用/读取器路径待有设备环境时验收
**关键词**: 标定汇总 CSV, i18n, 内圈, 外圈, Excel EPERM, EBUSY, 负轴向距离, DPB, CHANGELOG

**需求场景 / 现象**: 标定汇总输出在英文界面混用中文圈标签；Excel 占用时忙提示漏掉 Windows `EPERM`；首次写入界面语言被固化进表头；公式防护误伤以负号开头的轴向距离；DPB 判断、去重参数与子模块修复条目也需按统一口径处理。

**根因**: 圈名直接拼接未经过 `$t`，且翻译 key 包含尾空格；忙提示只有两个错误码；CSV 表头使用当前 locale；负轴向数值复用了外部文本安全规则；`saveCalibrationSummaryRow(key)` 参数未参与去重。

**方案 / 架构**:
- 圈名使用无尾空格的 `内圈` / `外圈` key 并在 formatter 内翻译。
- 文件占用提示同时匹配 `EBUSY`、`EACCES`、`EPERM`；新文件表头使用固定字段标识符，避免依赖 UI 语言。
- 轴向距离列保留数值符号，其余用户输入单元格继续使用公式防护。
- 删除未使用的 `key` 参数，按单场会话固定一行去重；DPB 参数比较使用 `Encoder.Series.DPB`。
- 根 CHANGELOG 记录 MPP 固件版本读取和旧版离线参数读取修复；DPB 的 `final` 字段标签按用户确认保持“产品版本”。

**关键文件与接口**:
- `components/encoder/device.js` — 轴向格式化、CSV 行、忙提示和会话去重。
- `main/file.js` — 追加 CSV 主进程处理器。
- `components/analyzer/analyzer.html`、`components/i18n.js`、`CHANGELOG.md`。
- `controller/python/sub_embedded` — `2ba14ad` → `bcdf98c`。

**验证方法**: 三个 JavaScript 文件 `node --check` 通过，`git diff --check` 通过；调用实际 `main/file.js` 处理器验证两行追加、只写一次固定表头并保留 `-0.85mm`；Windows `FileShare.None` 锁文件的 Node 追加打开实测返回 `EBUSY`。真实 Electron 与读取器标定流程未执行，标记 `BLOCKED-无法真实验证`。

**踩坑**: 负数距离虽含 `-`，仍是业务数值，不应像 SN 等外部文本一样加 Excel 公式前缀；CSV 新表头固定后不会自动重写历史文件已有的本地化表头。


### P-20260945: 标定失败弹窗读取响应体中的具体不良原因

**日期**: 2026-10-15
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01
**关键词**: 标定失败弹窗, defectiveItems, header.status, 外圈角度计算失败, setThenJustReturn

**需求场景 / 现象**: 标定失败弹窗只显示“标定失败”，没有呈现标定过程中已有的具体不良原因（例如“外圈角度计算失败”）。

**根因**: Python 将 `success` 和 `defectiveItems` 放在 JSON 响应体，同时用非零 `processingStatus` 写入响应头状态。`Server.transmit` 因非零 header.status reject，但 `Encoder.setThenJustReturn` 捕获后返回 `{header,data}`；前端失败分支因此仍可访问 `data.defectiveItems`，却直接丢弃并显示通用文案。

**方案 / 架构**: 在响应头失败分支读取 `data.data.defectiveItems`，复用 `_buildCalibrationFailReason` 和 `DefectiveItemsMap` 得到用户文案，写入标定日志并传给失败弹窗。缺陷项为空或无法映射时继续用通用“标定失败”；超时、手动停止和无响应的通信异常保持原行为。

**关键文件与接口**:
- `controller/server.js` — 非零响应状态以 `{header,data}` reject。
- `controller/encoder.js` — `setThenJustReturn` 捕获并返回响应对象。
- `controller/python/Encoder.py` — AllInOne 失败仍将 `defectiveItems` 放进响应体。
- `components/encoder/device.js` — 失败原因构建和弹窗入口。
- `components/encoder/mes/mes.js` — 不良项代码到中文文案映射。

**实施步骤**:
1. 在前端失败响应分支保留响应体不良项。
2. 用现有映射生成日志/弹窗文案，保留通用兜底。
3. 独立核对非零 header status、具体错误代码、空/未知代码及超时和异常路径。

**验证方法**: `node --check components/encoder/device.js` 与 `git diff --check` 通过。独立代码级检查以响应头 status=1 和 code `0-1-2-8` 调用生产原因构建器，输出“外圈角度计算失败”；空数组和未知代码的回退均为“标定失败”。用户明确无需真机，未运行 Electron UI。

**踩坑**: header status 表示执行结果失败不等于响应体为空；先判状态后丢弃 payload 会隐藏具体失败原因。

**状态**: 已完成


### P-20260946: MES基础架构方案：分阶段配置、授权与审计恢复

**日期**: 2026-10-16
**项目**: MES 后台管理系统 / D:\code\mes
**关键词**: MES 架构, modular monolith, MES execution order, configuration package, workflow version, scoped authorization, worker identity, transactional outbox, PITR, audit recovery

**需求场景 / 现象**: 基于 MES 需求规格和初始管理系统架构模型，形成可供跨部门评审的基础搭建方案，同时保留未批准的业务规则为责任人待决项。

**根因**: 原始方案涉及生产、质量、库存、授权、动态配置和外部集成，但数据权威、配置适用性、异步执行身份和恢复目标尚未完全确认；若直接落成技术事实，容易把待决业务规则编码进基础平台。

**方案 / 架构**:
- 首期采用边界清晰的模块化单体，按领域明确数据所有权，避免在领域和运维能力未验证前拆微服务。
- 每个 MES 执行订单固定绑定唯一配置包，子工序、报工和质量事实继承；阶段1仅引用工艺路线/标准作业基线，工作流版本待阶段4再加入。
- 授权按主体、资源、动作、范围、有效期完整匹配；用户发起的后台任务执行时重新核验用户授权，并与最小权限 Worker 主体取交集。
- 关键业务审计与业务事务同库提交；外部审计归档使用 outbox，需明确投递幂等和 PITR 恢复核对。
- PITR 回填事件保留原 event ID 和时间，按类型标明已回退业务状态、仍成立的历史读取/拒绝事实或待核对/已补偿的远端副作用；不得因此重建业务状态。

**关键文件与接口**:
- docs/architecture/MES-基础搭建架构方案.md — 完整分层、版本、授权、审计、恢复和阶段验收建议。
- docs/requirements/MES-综合需求规格说明书.md — 需求输入。

**实施步骤**:
1. 读取现有需求与架构输入，列出权威边界和阶段依赖。
2. 形成领域、运行、数据、安全和恢复章节，并将需业务确认的内容列为 D1-D18。
3. 经领域、运行时、安全三个独立视角评审，修订工作流阶段边界、双主体授权、outbox/PITR 和审计恢复语义。

**验证方法**: 检查文档含 17 个主章节、1 个 Mermaid 图、18 个责任人待决项及阶段0-5；相对参考链接目标存在。三路独立评审及交叉核验完成，最终没有未关闭的 Blocker/Major。未运行应用代码测试，因为该任务只交付架构文档；方案审批和实施验证仍待后续。

**踩坑**: PITR 回退的是业务数据库状态，不会让已经发生的下载、拒绝或外部副作用自动消失；恢复后的审计回填必须保留事件类型对应的恢复处置状态。外部归档使用异步 outbox 时，也不能宣称与业务数据库跨库原子提交。

**状态**: 架构建议稿待产品、生产、质量、仓储、ERP、IT 和安全责任人评审；实施与生产恢复演练待后续验证。


### P-20260947: 大型 IAP 分支合并评估要区分静态与硬件验收

**日期**: 2026-10-16
**项目**: EncoderPlotter_0903_01
**关键词**: 分支合并评估, git merge-tree, IAP回归, 子模块gitlink, 真机验收

**需求场景 / 现象**: 评估大型功能分支合入主线后是否完全兼容。

**根因**（问题类必填）: 无文本冲突、静态差异或单元测试均无法单独证明硬件相关多模块行为兼容，尤其涉及 IAP 擦写与固件恢复时。

**方案 / 架构**: 先确认 base 与提交数量，再按业务链路审差异，单独核对 gitlink 目标并确认工作区子模块状态；将静态检查结论与运行验收结论分开报告。

**关键文件与接口**:
- Git: `git rev-list --left-right --count base...target`、`git merge-tree base base target`、`git diff --check base...target`
- 本仓 IAP 主路径：`controller/python/Encoder.py`、`controller/python/parse_iap_bin.py`、`controller/python/qa_api/routes_iap.py`
- 子模块版本：`git ls-tree target controller/python/sub_common controller/python/sub_embedded`

**实施步骤**:
1. 明确 base 与目标引用，避免把工作分支当作合并目标。
2. 盘点提交数、差异文件、子模块指针和冲突。
3. 按正常与失败路径安排 Windows/Linux、HTTP API、IAP 真机验收；没有硬件证据时结论限定为静态风险评估。

**验证方法**: 实际只读命令可得提交计数、目标文件统计、merge-tree、diff-check 和子模块状态；功能兼容仍需 CI 与设备路径验证。

**踩坑**: 子模块 checkout 可能不是目标 gitlink 所指的提交；不能把本地当前子模块内容当作目标分支实现。IAP HTTP 层把校验移到 bin 解析核心后，route 单测应覆盖错误 bin、跨系列、旧固件和异常中断，并需硬件升级后回读验证。

**状态**: 已完成（形成静态评估方法）；本次目标分支兼容结论仍待验收


### P-20260948: IAP解析兼容程序加密包内的分段加密固件

**日期**: 2026-10-16
**项目**: EncoderPlotter1
**关键词**: IAP, 程序加密, 分段加密, AES V2, Protector.decrypt_iap_segmented_data, ARGUMENTS, 固件参数解析

**需求场景 / 现象**: 用户先对固件执行IAP分段加密，再用程序加密包裹该分段文件。普通IAP能解开外层程序包，却无法扫描内部ARGUMENTS，报“未识别出有效的固件参数结构”。

**根因**: 程序加密和分段加密是两层不同格式。现有IAP流程只对外层调用Protector.decrypt_file，返回的仍是供设备传输的V2/V3分段包；直接扫描该密文当然找不到固件ARGUMENTS。

**方案 / 架构**: 上传数据保持外层程序解密后的完整分段包；单独复制一条解析流，严格验证并解开V2或V3，再执行Flash Layout Footer和ARGUMENTS解析。V2验证包长度、连续序号、内部长度和CRC；V3验证包边界与CRC(iv+密文)。不要把解析明文覆盖上传变量或重试摘要输入。

**关键文件与接口**:
- `controller/python/sub_common/Protector.py` — `Protector.decrypt_iap_segmented_data(data)` 内存严格解密，返回固件字节和V2/V3格式。
- `controller/python/Encoder.py` — 普通IAP参数校验使用独立 `metadata_data` 解析；上传仍用 `app_data`。

**实施步骤**:
1. 解程序加密外层包。
2. 保留外层解密结果用于分段传输，另建元数据副本。
3. 校验V2/V3帧并解出固件后解析Footer/ARGUMENTS。

**验证方法**: 对目标kingkong.bin，外层解密得到535716字节V2包，内层还原496888字节；解析出DPT 4.2.6、算法4060、ARGUMENTS版本4、结构有效。截断包和短包均拒绝。未进行真机IAP烧录。

**踩坑**: 现有基于文件路径的 `decrypt_file_aes` 只支持V2且落盘；兼容IAP参数预检需要V2/V3内存解码以避免临时明文文件，同时保留原传输字节。

**状态**: 已完成文件解析兼容；真机升级链路未验证。


### P-20260949: IAP首包C5 01向量表失败与V2/V3传输格式匹配

**日期**: 2026-10-16
**项目**: EncoderPlotter1
**关键词**: IAP, 5CC5, C5 01, vector table, BootLoader V2 V3 V4, segmented encryption format mismatch

**需求场景 / 现象**: 外层程序加密内含分段加密 V2 的 DPT 固件可正确解析；设备上传第1包后，5CC5提交响应 `C5 01`，导致升级失败。

**根因**: 仓库协议核查记录将 5C C5 01 定义为向量表校验不通过。固件分段记录格式需与目标BootLoader一致：BL V2使用V2（记录无包尾CRC）；BL V3/V4使用V3（每记录有CRC）。上位机按目标BootLoader拆帧，若拿V2文件发给V3/V4，会将下一条记录长度字节误作CRC并破坏首包解密结果。截图未包含目标IAP版本，因此格式错配为高概率根因，最终确认仍需完整日志中的当前BootLoader版本行。

**方案 / 架构**: IAP读出BootLoader版本后、发首个数据包前校验固件分段格式匹配；V2只允许BL V2，V3允许BL V3/V4。明确的C5 01/5C C5 01向量校验失败不进行无效重试。

**关键文件与接口**:
- `controller/python/sub_embedded/IAP.py` — `validateIapSegmentedEncryptionFormat`、`uploadApp`、5CC5提交响应。
- `controller/python/Encoder.py` — 将解析出的 segmentedEncryptionFormat 传给上传流程。

**验证方法**: V2/V2、V3/V3、V3/V4通过；V2/V3、V3/V2拒绝；mock C5 01只发送一次；精确BIN预览解析仍返回 DPT 4.2.6/V2。未真机复测。

**状态**: 已加格式错配保护和明确错误响应；硬件原因待目标BootLoader版本日志确认。


### P-20260950: IAP V3末包不足256字节导致分段固件解析失败

**日期**: 2026-10-16
**项目**: EncoderPlotter1
**关键词**: IAP V3 segmented encryption, partial final chunk, Protector.decrypt_iap_segmented_data, CRC8, AES CBC

**需求场景 / 现象**: 用户提供的 DPT30 V4.2.6 BIN（外层程序加密，内层分段加密）预览解析失败。

**根因**: 外层解密成功；内层是V3分段包。V3加密器每次读取最多256字节，因此有效文件末包可以小于256字节。解码器误将任何前面已有包的短包都判为“非末包”，即便它确实是最后一包，导致解码失败并将密文回退到ARGUMENTS扫描。

**方案 / 架构**: 收集V3每包解密长度。严格要求除最后一包外均为256字节，最后一包允许1至256字节；CRC仍需通过。

**关键文件与接口**:
- `controller/python/sub_common/Protector.py` — `Protector.decrypt_iap_segmented_data` V3末包校验。
- `controller/python/Encoder.py` — 离线预览命令复用该解码器。

**实施步骤**:
1. 外层程序解密。
2. 按V3长度记录、CRC校验并还原明文。
3. 用现有Footer/ARGUMENTS规则解析。

**验证方法**: 指定文件外层537657字节，内层V3还原496888字节；解析为DPT 4.2.6、算法4060、ARGUMENTS v4。实际预览命令返回status=ok。旧V2文件仍可解析。CRC有效但非末包短于256的合成数据被拒绝。未做Electron实机或硬件升级。

**踩坑**: “前包之后短于256”不足以判定无效；必须解析完全部记录后再判断它是不是末包。

**状态**: 文件解析兼容已修复；设备升级链路未验证。


### P-20260951: EncoderPlotter1读取器功能与IAP子模块合并兼容验证

**关键词**: EncoderPlotter1, analyzer-iap, iap-ota-sn, 子模块合并, AnalyzerInfo
**日期**: 2026-10-16
## 需求
feature/iap-ota-sn 完整接入 feature/analyzer-iap，同时保留已有 DPT V5 参数恢复、SN 回读与分段加密升级。
## 方案
两个子仓先分别内容合并再更新父仓 gitlink，禁止择一覆盖。sub_common a314a17 同时包含 e13db13 与 c65b5e3；sub_embedded e3d9daa 同时包含 47c7bf6 与 8ab1943。父仓 c62fe446，保留 const isAnalyzer 的原有通用读取器热插拔实现。selector.html 用户原有删除6选项的修改保留未提交。未推送任何仓库。
## 关键文件
controller/python/sub_common/DataFormatter.py；controller/python/sub_embedded/Analyzer.py；controller/analyzer.js；controller/index.js；main/index.js。
## 验证
266 passed, 29 subtests passed（qa_api、sub_embedded、v4060、iap_sn_restore、build_info、safe_name）；JS语法及差异空白检查通过。独立review确认双祖先可达、Info None/空/15字节失败与16字节成功、PID1/2/3/5及异常SN隔离通过。
## 限制
没有真实读取器升级、热插拔及Ubuntu设备验收，标记BLOCKED-无法真实验证，不承诺全部硬件完全兼容。推送需先子仓后父仓。


### P-20260952: EncoderPlotter1合并读取器功能的已验证提交与限制

**关键词**: EncoderPlotter1, analyzer-iap, iap-ota-sn, 子模块合并, AnalyzerInfo
**日期**: 2026-10-16
## 需求
feature/iap-ota-sn 完整接入 feature/analyzer-iap，同时保留已有 DPT V5 参数恢复、SN 回读与分段加密升级。
## 方案
两个子仓先分别内容合并再更新父仓 gitlink，禁止择一覆盖。sub_common a314a17 同时包含 e13db13 与 c65b5e3；sub_embedded e3d9daa 同时包含 47c7bf6 与 8ab1943。父仓 c62fe446，保留 const isAnalyzer 的原有通用读取器热插拔实现。selector.html 用户原有删除6选项的修改保留未提交。未推送任何仓库。
## 关键文件
controller/python/sub_common/DataFormatter.py；controller/python/sub_embedded/Analyzer.py；controller/analyzer.js；controller/index.js；main/index.js。
## 验证
266 passed, 29 subtests passed（qa_api、sub_embedded、v4060、iap_sn_restore、build_info、safe_name）；JS语法及差异空白检查通过。独立review确认双祖先可达、Info None/空/15字节失败与16字节成功、PID1/2/3/5及异常SN隔离通过。
## 限制
没有真实读取器升级、热插拔及Ubuntu设备验收，标记BLOCKED-无法真实验证，不承诺全部硬件完全兼容。推送需先子仓后父仓。


### P-20261016: MES 可扩展模块基础架构边界与发布流程

**日期**: 2026-10-16
**项目**: MES 后台管理系统，D:/code/mes
**关键词**: MES基础架构, 模块化架构, 独立部署, 模块独立数据库, 控制面, Outbox, 无同步热路径, Release编排, manifest, version_token, perm_epoch, 范围授权

**需求场景 / 现象**: 为支持业务模块任意创建和独立添加，需要先定义一套模块依赖的 MES 基础平台和模块契约。

**根因**（问题类必填）: 不适用；这是基础架构设计任务。关键设计风险在于平台与业务模块边界不清、跨模块同步依赖、权限范围遗漏及模块数据所有权混淆。

**方案 / 架构**: 平台提供稳定 SDK/契约、模块目录与 manifest 校验、身份授权和签名能力快照、元数据模板版本、事件通道、审计汇集、Release 编排与观测；模块独立构建、服务、UI、数据库和发布。模块业务热路径不做同步跨模块 RPC；每个模块通过本地事务 Outbox 发布版本化事件。Release 作为平台版本、模块制品、权限快照及迁移批次组成的锁定部署计划。撤权以 perm_epoch 和提交栅栏确认生效；资源范围应用于列表、详情、关联、写入、导出、附件、事件消费和后台任务。跨模块强约束采用目标绑定预授权凭证、命令账本、幂等和低频对账，不直连其他模块数据库。

**关键文件与接口**:
- `docs/architecture/MES-基础搭建架构方案.md` — 架构建议稿，包含平台边界、模块契约、发布流程和分阶段建设图示。
- `docs/requirements/MES-综合需求规格说明书.md` — 业务需求输入。

**实施步骤**:
1. 先落地 SDK/稳定契约、模块注册、身份与权限、模板版本、事件/outbox、审计、Release 与观测等基础能力。
2. 通过独立参考模块验证制品签名/审批、独立数据库/迁移、路由、范围授权和事件链路。
3. 再允许模块按 manifest 声明权限、依赖、API/事件、UI、任务与健康检查并独立部署。
4. 建设阶段以跨模块事务、撤权屏障、终态数据保护和重试补偿作为验收边界。

**验证方法**: 最终建议稿含5张Mermaid图、代码围栏成对；模块独立部署/数据库、禁止热路径同步调用、本地Outbox、默认拒绝、模板版本令牌、perm_epoch提交栅栏、终态保护及范围授权全路径有文本依据；R6领域/运行时/安全评审和交叉复核通过。未运行业务代码测试；Codex文件面板显示检查受工具状态限制。

**踩坑**: 原模型同时包含“模块独立发布”和“单一Release制品”两种口径，建议把Release定义为锁定版本与部署计划，不合并为单体制品；预留门禁凭证是特定任务授权线性化点，后续复判可阻止新预留，但不能宣称立即撤销已预留任务；范围授权必须下沉到查询与后台执行层，禁止先读全量再过滤。

**状态**: 架构建议稿，待责任人确认 Release 定义与跨模块门禁语义。



### P-20261017: MES 重建进度交接（Claude/Codex 同步入口）

**日期**: 2026-10-18
**项目**: MES 平台重建 / D:/code/mes
**关键词**: MES重建, 进度交接, Codex同步, PROGRESS.md, mes-admin, mes-server, mes-db, mes-web, IAM, 低代码, 模块管理, LOWCODE契约, 演示模式, dev:mock, Docker未重启, BLOCKED

**需求场景 / 现象**: Claude 与 Codex 交替开发 D:/code/mes。用户要求把本次重建进度同步给 Codex，接手方需要知道当前做到哪、哪些未验证、从哪里继续。

**方案 / 架构**: 进度单一来源放在仓库内 `docs/PROGRESS.md`，并在 `AGENTS.md` 必读清单第 6 项引用，Codex 读取 AGENTS.md 时自然看到；本条知识只做索引，避免两处内容不一致。当前状态摘要：
- 仓库已清空重建为 npm workspaces 四部分（mes-web 空、mes-admin、mes-server、mes-db），暂不关联 Git。
- 栈：React18+TS+Vite+Tailwind+Radix 自建组件；NestJS10+Kysely+zod；PostgreSQL16（Docker）。
- IAM 一期（登录/用户/角色/权限/审计）代码完成，构建与单元测试通过；数据库集成测试与 E2E 因电脑未重启（WSL2/Docker 未生效）BLOCKED。
- 模块管理（低代码）v1 进行中已暂停：契约与前端核心完成，ModuleDesigner、AppPage、菜单接入、演示数据、后端服务未完成；后端已有的 0002 迁移与 schema.ts 是中途停止的产物，未复核。

**关键文件与接口**:
- `D:/code/mes/docs/PROGRESS.md` — 进度、阻塞、低代码断点与待办顺序（接手必读）
- `D:/code/mes/docs/design/IAM-基础身份权限契约.md` v1.1、`LOWCODE-模块管理契约.md` v1.0 — 三端契约
- `D:/code/mes/DESIGN_SYSTEM.md` v2 — 前端唯一设计约束
- `D:/sire/sire_ledger/runs/R20261018-MES-LOWCODE-V1/checkpoint.md` — 断点台账

**实施步骤**:
1. 接手前读 AGENTS.md → docs/PROGRESS.md → 相关契约。
2. 低代码从 PROGRESS.md 第 4 节“待完成”第 1 步继续；后端已存在的 lowcode 文件先复核再使用。
3. 阶段完成后更新 PROGRESS.md 的状态表与断点。

**验证方法**: `npm run build`、`npm test`（根目录）；演示模式 `npm run dev:mock -w mes-admin` 浏览器查看；重启并启动 Docker 后按 PROGRESS.md 第 3 节顺序跑集成与 E2E。

**踩坑**: Vitest 的 esbuild 不支持 emitDecoratorMetadata，mes-server 测试用 unplugin-swc；dev 用 tsc --watch + node --watch。初始管理员密码只在 mes-db/.local/initial-admin.txt，不得写入任何日志或报告。

**状态**: 部分完成
