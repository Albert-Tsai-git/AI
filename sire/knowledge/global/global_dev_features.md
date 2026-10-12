# 全局功能开发记录 (F)

### F-052: 下线检测信息确认人工决定与订单号录入
**日期**: 2026-10-12
**项目**: driverSoftware2
**状态**: 已实现并通过隔离模拟 GUI 验证，未做真机验收
**关键词**: [下线检测, 信息确认, firmware_info, 人工决定, 继续检测, 结束检测, 订单号, 扫码]

**实现**: 信息确认判不合格进入通用人工决策集合；决定前锁住下一项，继续后保留不合格，结束则存档关闭。订单号仅扫码/手填，回车聚焦序列号，不提交后端；模块状态保留页面重建时的值。
**提交**: 13a0737（信息确认人工决定）；a80cafb（订单号前端录入）。
**验证**: 主控报告 test_od_lock_completed 五项通过；可见隔离模拟 GUI 已覆盖继续解锁噪声、结束显示不合格并保留决定、订单号回车聚焦序列号且不提交。独立只读复核通过。
**限制**: 通信读取失败仍报错重试，只有判定不合格进入人工决定；订单号刷新清空且不进入报告。真实 8766 服务有用户检测，未重启，未宣称真机验收。尺寸自动换格已另提交 cda5e0c：Enter 立即跳格，输入停顿 500ms 跳格，最后只聚焦确认；清空与恢复不抢焦点，失焦与页面重建取消定时器。用户说明设备类似扫码枪单次输入，是否回车未知。仅实际观察逐字输入 30.123 时整笔保留第一格；未完成超时跳格及边界验证。用户要求停止测试并自行验收，已停止，不计为验证通过。

### F-026: EncoderPlotter 烧录面板放开 DPB 锁定 — 型号/固件文件可重选
**日期**: 2026-09-23
**项目**: EncoderPlotter_0703_03 (分支 feature/flash-and-pcba，主仓 1f5c515a，子模块 sub_automation 30b1c3f)
**状态**: 已归档 (可直接调用)
**关键词**: [烧录面板, flashPanel, DPB 锁定, 型号选择, IAP, MPT-G, --mpt-g, flash_tool.py, CONFIGS extra_hex, localStorage 配置恢复, nuitka 重编]

**需求**: 放开 1a5e4de1 引入的“仅 DPB”定制锁定，默认 DPB，型号与 Hex/IAP 文件均可重选；增加 MPT-G。PCBA 面板本身无锁定，不改。

**方案要点**:
- flashPanel.js 模块级常量 SENSOR_OPTIONS（value 直接拼 `--<value>` 传给 flash_tool.py）、DEFAULT_SENSOR='dpb'、IAP_SENSORS=['dpb','dpt-g1','mpt-g']、getDefaultDpbFiles()（asar 用 resources/bin，开发用 sub_automation/bin）。
- data(): 缓存型号在白名单才恢复；缓存型号与当前一致才恢复缓存路径；否则 DPB 填默认 bin 文件、其它型号为空。
- watch selectedSensor: 切 DPB 填默认文件，切其它清空待重选。
- computed needsIapFile 取代 isDPBMode；startFlash 仅在 needsIapFile 时传 iapFile，否则 null。

**踩坑**:
1. 前端型号必须与 flash_tool.py argparse 参数和 CONFIGS 中 extra_hex 同步：mptg 在 CONFIGS 有 IAP，但原前端 isDPBMode 不含 mpt-g，且 CLI 无 --mpt-g → 选了必失败（R6B/R6C 发现）。
2. 打包版优先用 dist 中预编译 flash_tool exe，builder.ts 的 nuitka 命令被注释，改 flash_tool.py 后需手动重编，否则新参数不生效。
3. 子模块改动需先在 sub_automation 提交，再更新主仓指针；推送顺序子模块优先。

**遗留**: 缓存路径未校验（安装目录变化失效；换行注入 jlink 脚本需本机权限）；未实机烧录验证。

### F-025: 舵机(KingKong)诊断包解密规则 — kkdiag + 本机私钥
**日期**: 2026-09-23
**项目**: driverSoftware (@CODE_ROOT@\driverSoftware)
**状态**: 已归档 (可直接调用)
**关键词**: [诊断包, diag, 解密, kkdiag, diag_private.pem, 私钥, 黑匣子, blackbox, events.jrn, rings.json.enc, env.json.enc, key.bin, AES-GCM, RSA-4096]

**规则**: 用户给出 `diag_*.zip` 要求解析时:
1. 私钥以对称加密形式存于知识库: `<OUTSIDE_REPO_SECRET_STORE>\diag_private.pem.vault` (scrypt + AES-256-GCM; 2026-09-23 核验与仓内 `core/diag_pubkey.pem` 匹配)。口令**不落盘**, 每次使用必须由用户本人手动录入确认; AI 不得保存、复述或代填口令。本机不再保留明文私钥。
2. 调用 (仓根, 用户在自己终端执行, getpass 提示输入口令; 私钥只解到临时文件, 用完即删):
   - 时间线: `venv\Scripts\python.exe <OUTSIDE_REPO_SECRET_STORE>\diag_key_vault.py kkdiag report <包.zip>`
   - 全展开: `... diag_key_vault.py kkdiag open <包.zip> -o <目录>` → env.json / events.jsonl / rings.json / manifest.json
   - 出图: `... diag_key_vault.py kkdiag plot <包.zip> all -o <目录>`
   - 重新加密/换口令: `... diag_key_vault.py seal <明文pem>`
3. AI 流程: 先跑免私钥的 `tools/kkdiag.py inspect`; 需要解密时给用户上面的命令让其录入口令, 再读取其 `-o` 输出目录分析。解密输出按敏感数据处理, 不入仓不转发。

**背景**: 包格式 = 每会话随机 32B DK (AES-256-GCM 加密各段) + RSA-4096-OAEP 封装 DK 于 key.bin; 无私钥不可暴力/逆向。本机会话原始数据在 `~/.kingkong_driver/sessions/` 只保留 7 天; dev 环境另有 blobs_plain 明文副本。

### F-024: AI工程化基建模板 — driverSoftware 全套工程/规则/打包/发布机制
**日期**: 2026-09-22
**项目**: driverSoftware (@CODE_ROOT@\driverSoftware, v0.13.10, 分支 development) — 新项目搭建时直接照抄的参考实现
**状态**: 已归档 (可复用模板)
**关键词**: [AI工程化, 工程基建, 项目模板, AGENTS.md, AI规则, 打包, Nuitka, Electron, electron-builder, 多SKU, 发布, release.py, VERSION, CHANGELOG, GitLab CI, Runner, NAS, 飞书通知, 通讯架构, FastAPI, WebSocket, 多进程, shared_memory, venv, lockfile, workspace.json, pytest, 门禁, git flow, 分支命名]

**用途**: 新项目 (桌面端上位机 / Python 后端 + Web 前端 + Electron 壳) 搭建时, 按下列分层直接复刻。源文件都在该仓, 需要细节时去读对应文件。

**1. AI 规则体系 (三层文档, 分工明确)**
- `AGENTS.md` = 怎么干活 (工程硬规定, 所有 AI 助手动手前必读); `docs/PROJECT-CONTEXT.md` = 协作上下文 (活从哪来/结论回填哪/相邻仓/真机台账/发布分发); `docs/skills/*.md` = 按模块的必读 skill, AGENTS.md 里用「模块 → 必读 skill」表强制映射。
- 硬规定骨架 (可直接抄): ①全程中文 ②每个可独立描述的改动单独 commit ③commit 不自动 push, 用户说推才推 ④commit 写 why ⑤写文档前命令/路径当场验证 ⑥不引用项目外绝对路径 (走 `~/.<proj>/workspace.json` 按逻辑名取路径 + vendor/ wheel + 环境变量) ⑦AI 不许假装跑过 ⑧证据没看完不许说无从下手 ⑨版本/CHANGELOG 发布纪律。
- 「工程军规」段: 每条都带「为什么 + 实际踩坑」, 如: 中文 commit 一律 `git commit -F 文件`; 源码扫描门禁先剥注释、写完人为破坏一次自证变红; UI 改动必须让真实数据流起来验证; 加 fail-fast 守卫前审计前置条件路径; 真机验收必须走可见 GUI; 对外文字说人话。
- 新协议命令落地顺序固定: protocol enum → commands 高层封装 → server endpoint → 前端 api.js → 页面接入, 每步单独 commit。

**2. 架构与通讯链**
- Browser/Electron → HTTP/WS → FastAPI (`server.py` + `core/`) → `core/reader_*` → USB HID → 分析仪 → RS485 → MCU。
- 前端纯 ESM、无 build, 后端直接 serve `frontend/`, 改完 F5 生效。
- reader 双形态: `READER_MP=1` 多进程 (子进程独占 HID + GIL, 控制走 mp.Pipe, 数据走 shared_memory 无锁 SPSC 环形缓冲), `READER_MP=0` 进程内; 两者 API 必须同签名 (曾因只改一边导致 500)。打包版默认 MP=1, 开发 start.bat 置 0 → 打包版问题先设 MP=1 复现。
- 固件能力档案 `firmware_profiles/*.json` (工具生成, 禁止手填), 功能门控按寄存器能力判定不按版本号; 警惕「缺档案静默回退」。
- 前端周期发帧用 await promise 链驱动, 禁用 setTimeout/setInterval (后台标签页节流会触发下位机看门狗)。
- HID 设备全机只许一个进程持有; 多实例用 `WEB_GUI_PORT` 换端口, 默认绑 127.0.0.1。

**3. 运行 / 环境**
- `setup.bat`: 检查 py -3.12 → 建仓内 venv → 先装 vendor/ 内部 wheel → 优先 `requirements.lock.txt` → import 自检 + 原生 DLL (hidapi) 自检。依赖一律进 venv, 禁止全局 pip; 数值库精确 pin。
- `start.bat`: 优先 venv Python, 回退 py -3.12; `.claude/launch.json` 配 server:8765 供 AI 预览。
- Electron `main.js`: 打包态 spawn `server.exe`, 专属端口/0=OS 分配, stdout 重定向 server.log, 退出按进程组/映像名兜底杀孤儿孙进程, 轮询 `/api/state` 判就绪; `postmortem.js` 崩溃现场打包。
- worktree 自测必须在 worktree 目录里显式起服务并换端口。

**4. 打包 (`scripts/build.bat`, `docs/PACKAGING.md`)**
- Nuitka 把 server.py 编成独立 server.exe (编译参数写在 server.py 头部 `# nuitka-project:` pragma, 数据目录/隐式模块在这里声明) → electron-builder 打 NSIS + zip。
- 多 SKU「编一次打多次」: `--internal/--release/--customer/--all`, 差异全部是对产物目录的后处理 (删文件/写档位数字) + productName 覆盖; 顺序只能从内容全到内容少; 未知参数直接报错。
- 守卫: 源树完整性 (构建前后 HEAD 一致, internal 拒脏工作区)、客户包构建后门禁 (必须在的在、必须剔除的已剔除、档位值正确)、禁止「跳过编译的快速打包」。
- bat 坑: `for /f` 内 `=`、`>` 需 `^` 转义。

**5. 版本与发布 (`scripts/release.py`, `CHANGELOG.md`, `VERSION`)**
- `VERSION` 单一来源, 日常禁止手改; 唯一入口 `python scripts/release.py X.Y.Z`: 校验 semver/工作树干净/[未发布] 非空 → 写 VERSION 并同步 package.json/lock → 截断 CHANGELOG → commit + 本地 tag。推送留人工 (分支和 tag 两条命令, 发后 `git ls-remote --tags` 核)。
- CHANGELOG `## [未发布]` 段随分支写, 面向用户一句白话; 有新增 → minor, 仅修复 → patch。
- 发版前对账: 重看 HEAD、`git log 上个tag..HEAD` 逐条对 CHANGELOG、冲突保双方且 `grep -c '<<<<<<<'` 为 0。
- 发布后回收工单上的「待发布」占位; 发版后继续开发用 `--internal` (名字带 +sha) 避免同名覆盖。

**6. CI/CD (`.gitlab-ci.yml`, `scripts/ci_*`)**
- 只有 tag 触发流水线: `vX.Y.Z` 同时打 Windows + macOS 正式包; `win-smoke-*` 冒烟; `internal/*` 排除。stages: test(门禁) → build → notify(飞书, 失败不让构建变红)。
- CI 只调用同一份 build 脚本, 不重复造门禁。`GIT_CLEAN_FLAGS` 排除 venv/node_modules 做缓存 (实测提速 3.4×)。
- Windows Runner 坑: 服务账号用 Administrator + 系统 powershell 5.1 (非 pwsh), before_script 显式补 PATH, .ps1 必须带 BOM; 不信任 Runner 注入的 CI_* 变量 (长 commit message 会让其变空) → cwd 用特征文件判定、tag 用 `git tag --points-at HEAD`。
- NAS 分发: 凭据是 masked CI 变量; 一版一目录; 目标已存在即拒写不覆盖; 上传后回读逐个 SHA256 核对; internal 包进 `_internal/fw-<sha>/`。

**7. 测试与门禁**
- `pytest.ini` 把 testpaths 钉死在 `tests/unit` (tests 根下是需真机的独立脚本, 防收集期 INTERNALERROR)。回归缺陷配专门回归测试 (修复前应全红)。
- UI 改动 playwright 自验 (`docs/skills/playwright_ui_self_test.md`); 真机验收走可见 GUI。

**8. Git 流程**
- 主干 development, 分支前缀 `feat/ fix/ docs/ chore/ release/ hotfix/`, 小写短横线, 禁用工具自动生成的分支名; `git merge --no-ff -F msg` 合回; 删分支前 `--merged` + `merge-base --is-ancestor` 双验。

**9. 协作外设**
- 缺陷池/需求池在飞书多维表格, 用 lark-cli (子命令带 +, `--base-token`); onboarding 清单一次授全 scope; fnm 装的 CLI 可能不在 agent PATH。
- 本机差异 (相邻仓路径、私钥) 只进 `~/.<proj>/workspace.json`, 不进仓。

**复用建议**: 新项目先建 AGENTS.md (硬规定 + 模块→skill 映射表) + PROJECT-CONTEXT.md + VERSION/CHANGELOG/release.py + setup/start 脚本 + 单一 build 脚本 + tag 触发 CI, 再按业务填 skill。

### F-027: 【飞书自动化】飞书 ⇄ Claude Code 双向闭环：完成通知、飞书回复续跑、桌面上下文同步

**日期**: 2026-09-23 ~ 2026-09-24
**项目**: 全局工具 @USER_HOME@\.feishu_bridge
**关键词**: 飞书自动化, 飞书, Feishu, Lark, lark-oapi, 长连接, 自建应用, 机器人, 消息卡片, Stop Hook, UserPromptSubmit, claude --resume, 双向通知, 远程续跑, 上下文同步, feishu_turns, CLAUDE_CONFIG_DIR, CC-Switch, cc-switch.db, common_config_claude, proxy_live_backup, hosts, platform.claude.com

**需求**: 在桌面 Claude Code 做完任务后通知到飞书；用户在飞书「回复」通知，本机在原会话、原目录续跑，结果回帖到飞书；回到桌面时，Claude 能拿到飞书里发生的完整对话，并在界面上展示出来。用户明确否决 Remote Control 替代方案，必须走飞书。

**完整流程（闭环）**:
1. 桌面一轮结束 → Stop Hook `hook_notify.py` 取最后一条 assistant 原文 → 发飞书卡片（标题=✅项目名，副标题=完整目录，正文按标题分块+分割线，≤800 字）→ 存 `msg_map`：message_id→session_id+项目根目录。
2. 用户在飞书「回复」卡片 → `listener.py`（长连接）收 `im.message.receive_v1` → message_id 去重 → 白名单 open_id → 用 parent_id 查 `msg_map` → 危险关键词先要「确认」。
3. 续跑：回帖「🚀 执行中」→ 在 `feishu_turns` 记一条（你说的话，synced=0）→ 在原目录启动 `claude.exe --resume <sid> -p --permission-mode bypassPermissions`（prompt 走 stdin，env: CLAUDE_CONFIG_DIR=~/.claude-feishu、FEISHU_BRIDGE_REPLY_TO、FEISHU_BRIDGE_CWD、FEISHU_BRIDGE_TURN_ID）。
4. 续跑结束 → 续跑进程自己的 Stop Hook 把结果卡片回帖到用户那条回复下，并把**完整回复原文**挂到该 turn → 新卡片再次进入 `msg_map`，可以一直回复下去。
5. 回到桌面发消息 → UserPromptSubmit Hook `hook_sync.py` 取出该会话 synced=0 的所有飞书轮次 → 作为 additionalContext 注入（ASCII 转义输出），附指令「回复开头原样贴出 📥 飞书同步（N 轮），含每轮问题与回复原文，再加分割线后回答当前问题」→ 标记 synced=1。
6. 守护：listener 每 60s 检查 `~/.claude/settings.json`，缺少 Stop(hook_notify) 或 UserPromptSubmit(hook_sync) 就补回。

**组件**: bridge_config.py / bridge_store.py（msg_map、pending、seen、feishu_turns）/ bridge_sender.py（文本+卡片）/ hook_notify.py / hook_sync.py / listener.py / install_service.ps1（计划任务 FeishuClaudeBridge，pythonw 开机自启，失败每分钟重启）/ login_bridge.cmd / config.json（凭据，仅当前用户可读）。飞书应用权限：im:message、im:message:send_as_bot、im:message.p2p_msg:readonly；事件订阅=长连接。

**安全**: 一次性口令绑定主人（私聊「绑定 <码>」，用后删除）；白名单是真正边界；危险关键词二次「确认」仅防误触（含 cc-switch/settings/hook/配置 类词）；续跑专用配置 ~/.claude-feishu/settings.json 用 permissions.deny 的 Edit 规则禁止改全局 settings、CC-Switch、桥接自身代码与凭据（bypass 模式下实测有效，但拦不住 Bash 直接写）；同会话加锁串行；超时 taskkill /T /F；日志不记录密钥。

**踩坑与解法**:
1. 自定义机器人 Webhook 只能发不能收 → 改自建应用 + 长连接事件（无需公网）。
2. 首个私聊者即成为主人，存在抢绑风险（R6B 高危）→ 改为一次性口令绑定。
3. 以 - 开头的回复会被当成 CLI 参数 → prompt 改走 stdin；超时只杀父进程会导致锁一直不释放 → taskkill /T。
4. 桌面 App 用内置 1P 登录，后台 CLI 继承不到；全局 settings env 指向 CC-Switch 代理，而「Claude Desktop Official」供应商没有 base_url → 400。解法：独立 CLAUDE_CONFIG_DIR=~/.claude-feishu，projects 用 junction 链到 ~/.claude/projects 共享会话，单独 /login（订阅账号），子进程清除继承的 ANTHROPIC_*/CLAUDE* 变量。
5. 本机 DNS([private-ip-redacted]) 解析不了 platform.claude.com → /login 报 ENOTFOUND；hosts 加 160.79.104.10 platform.claude.com。
6. 续跑中模型 cd 导致 Hook 记录的 cwd 漂移，下次续跑跑错目录 → cwd 优先级 FEISHU_BRIDGE_CWD > CLAUDE_PROJECT_DIR > hook cwd。
7. 纯文本通知挤成一团 → 改用飞书卡片 2.0，按标题/独占粗体行分块加 hr，去掉 [SIRE] 声明行，截断时补齐代码块。
8. CC-Switch 开机会整体重写 ~/.claude/settings.json，Hook 被冲掉，桌面会话不再通知（续跑仍能通知，因为用的是 ~/.claude-feishu/settings.json）→ listener 守护每 60s 补回。
9. 根治第 8 条：Desktop Official 供应商的编辑页没有配置入口。数据实际在 ~/.cc-switch/cc-switch.db 的两处：settings 表 key=common_config_claude，以及 proxy_live_backup 表 app_type=claude 的 original_config（开机回写用的快照，是丢失的直接来源）。做法：关闭 cc-switch.exe → 备份 db → 两处 JSON 的 hooks 都补齐 → integrity_check → 重启。两处都要改；CC-Switch 升级后可能失效，守护兜底。
10. 桌面 App 只使用内存里的上下文，不会重读 .jsonl：飞书续跑虽然写进同一会话文件，但在记录里成了分叉支线，桌面既看不到也不知道 → 新增 feishu_turns 表 + hook_sync.py，在下一次桌面提问时注入上下文。
11. hook_sync 输出中文到 stdout 被 Windows 代码页(GBK)写成乱码 → json.dumps(ensure_ascii=True)，用 stdout.buffer 写 ASCII。
12. 注入的 additionalContext 在桌面界面上不可见，用户「看不到完整信息」→ feishu_turns 存完整回复原文（卡片仍用 800 字精简版），并要求 Claude 在回复开头原样贴出「📥 飞书同步」，单次上限 3 万字。这是靠指令约束，不是强制插入；漏贴时让 Claude「贴一下飞书同步」即可。
13. 桌面 App 界面本身永远不会显示飞书轮次（没有公开接口），同一会话不要两端同时操作。
14. 飞书续跑曾自行改动 CC-Switch 数据库，而用户没有在桌面确认 → 两层防护：① 危险词加入 cc-switch/settings/hook/配置文件/全局配置/通用配置/config.json 等，命中后要回「确认」才执行（只检查用户原话）；② ~/.claude-feishu/settings.json 加 permissions.deny：Edit(~/.claude/settings.json)、Edit(~/.claude-feishu/settings.json)、Edit(~/.cc-switch/**)、Edit(~/.feishu_bridge/config.json)、Edit(~/.feishu_bridge/*.py)。已实测 bypassPermissions 下仍然拒绝（WRITE_DENIED）。注意：Write(...) 规则无效，Edit(...) 规则已覆盖所有写文件工具；deny 拦不住 Bash/python 直接写文件，这类情况靠危险词兜底。

**验证**: 真机联调通过（绑定→通知→回复 pong→续跑 rc=0→回帖）；R6B 复核第 1 轮 FAIL（1 高 3 中），修复后第 2 轮 PASS；CC-Switch 重启后 Hook 保留、守护未触发；飞书两轮（08:27/08:28）续跑 rc=0，桌面回填 2 条成功；同步输出为纯 ASCII，中文解码正常。
**遗留**: runs/*.log 未清理；App Secret 曾出现在对话中，建议重置后更新 config.json；开机场景下 CC-Switch 修复的效果待下次开机后确认。
**状态**: 已完成


### F-028: 【知识库优化】SIRE 知识检索 v2：bge 语义 + trigram 全文 + 复用要点，recall@3 0.45→1.00

**日期**: 2026-09-24
**项目**: SIRE 知识检索 v2 实施记录（历史闭环库为 `@SIRE_ARCHIVE_ROOT@\sire_vectors.sqlite3`；Claude/Codex 当前工作库由 `sire_paths.py` 指向仓库 `data/sire_vectors.sqlite3`）
**关键词**: 知识库优化, 向量检索, 语义检索, bge-small-zh, fastembed, trigram, FTS5, 混合检索, BM25, 复用要点, 知识模板, sire_kb lint, sire_kb add, is_latest, 只增不减, 评测集, recall

**需求场景**: 数据库优化后要求「能快速检索知识，检索到的知识可直接用来开发相同功能」。审计发现：98 条知识有 81 条只在库里（sire_kb 只读 md，搜不到）；FTS5 默认分词对中文失效（「寄存器」全文 4 条 vs 实际 73 条），`CC-Switch` 直接语法错误被吞；global_index.json 17 个版本霸榜；查询拆出单字导致每条知识都被 +0.12 失去区分；关键词表是 u-01/r6a/users 这类噪音；分类用子串匹配把 decision 里的 ci 判成 devops。基线 recall@1 0.35 / recall@3 0.45 / 313ms。

**方案 / 架构**:
- 新模块独立承载 v2，旧脚本只接入两点（index 末尾 post_index、search 先走 v2 异常回退旧算法），保证不把现有工作流搞挂。
- 语义：本地 BAAI/bge-small-zh-v1.5（fastembed/ONNX，无 torch，512 维，91MB，hf-mirror 下载，缓存后 HF_HUB_OFFLINE 离线）；向量存 emb 表，按 text_hash 增量计算。
- 全文：FTS5 tokenize='trigram'（≥3 字符生效），查询词双引号包裹；2 字中文词用 Python 覆盖率补足。
- 打分：0.55×语义 + 0.30×词项覆盖(标题/关键词命中 1、正文 0.5) + 0.15×BM25 名次归一 + 关键词精确命中 0.1 + 知识记录 0.06；台账片段 ×0.9；同一 path 只留最高分片段，片段内容就是已入选知识则跳过。
- 只增不减：旧版本 is_latest=0、派生文件排除、噪音关键词 status=noise、类型归一原值存 orig_type、空关键词只补空——全部不删数据。
- 可复用：结果附 reuse（关键文件汇总 + 根因/修复/流程/验证/踩坑分段首行；整段式正文按句挑「方案是/必须/重点检查」）；KNOWLEDGE_TEMPLATE.md 定义必备段落，sire_kb add 写入前校验，lint 列出需补全记录。

**关键文件与接口**:
- `<SHARED_SKILL_DIR>/scripts/sire_knowledge_index.py` — post_index(conn)、search(conn, query, limit, threshold, domain, hash_encode, hash_decode)、reuse_points(body)、mark_latest、sync_embeddings
- `<SHARED_SKILL_DIR>/scripts/sire_vector_db.py` — search_database 委托 v2；index_database 末尾调用 post_index；source_paths 排除派生文件；classify 词边界
- `<SHARED_SKILL_DIR>/scripts/sire_kb.py` — load_db_records（库为正式来源）、export-md、lint、add
- `<SIRE_ROOT>/knowledge/global/KNOWLEDGE_TEMPLATE.md`、`@SIRE_ROOT@\eval\queries.json`、`@SIRE_ROOT@\eval\run_eval.py`

**实施步骤**:
1. 备份库与脚本（sire_db_backup + @SIRE_ROOT@\opt-backup-20260924）。
2. 写评测集（自然说法，不照抄标题）跑基线。
3. pip install fastembed；HF_ENDPOINT=https://hf-mirror.com 下载模型到 @SIRE_ROOT@\models。
4. 新模块 + 旧脚本两点接入；index 触发 post_index（首跑约 40s 计算 1052 条向量）。
5. sire_kb 改库优先 + 三个新命令；SIRE-MIGRATION.md 升 v2.6。

**验证方法**: `python @SIRE_ROOT@\eval\run_eval.py 标签` → recall@1 0.95、recall@3 1.00、平均 76ms（进程内），CLI 单次约 0.7s（含模型加载）；knowledge_records 98 / task_records 515 条数不减；`sire_kb.py lint` 输出待补全清单。

**踩坑**:
- trigram 只能匹配 ≥3 字符，2 字中文词必须另算覆盖率。
- FTS 查询不加引号时 `CC-Switch` 被解析成列名报错，旧代码 except 吞掉导致静默失效。
- 知识正文两种写法（**段落**: 与整段话），复用要点要两套抽取；段落标题可能很长（如「修复（仅改…）」），正则上限需放宽到 60。
- 导出副本/模板若进入切片会与知识记录重复，必须排除。
- fill_missing_keywords 对 md 来源记录的补全会在下次同步时被 md 原值覆盖（md 无关键词则仍为空），根治要在 md 里补关键词。

**状态**: 已完成


### F-041: 【飞书自动化】飞书多 AI 中转中间服务 feishu-hub（中间服务 + Claude/Codex 执行器，取代 F-027）

**日期**: 2026-09-24
**项目**: 飞书多 AI 中转中间服务 feishu-hub —— @SIRE_ROOT@\AI\AI\feishu-hub（GitHub Albert-Tsai-git/AI，分支 feature/feishu-hub，最新 ea704df）
**关键词**: 飞书自动化, 飞书中转, 中间服务, feishu-hub, hub, 多AI, Claude执行器, Codex执行器, 执行器协议, PROTOCOL.md, 租约, lease, 心跳, 长轮询, outbox, 发送队列, 幂等, uuid, 任务状态机, NEEDS_RECOVERY, WAITING_EXTERNAL, desktop_queue, codex queue, codex exec resume, claude -p, claude --resume, Stop Hook, UserPromptSubmit, notify, --previous-notify, computer-use, 计划任务, FeishuHub, lark-oapi, 长连接, 私聊建任务, 项目列表, 快捷操作, 取代 F-027

**需求场景**: 用户在飞书里给本机的 Claude、Codex（及以后接入的 AI）派任务、回复卡片续跑、桌面端对话完成后推送飞书；各 AI 彼此独立，只与一个中间服务通信；信息不足先问、目录必须用户确认；电脑或服务重启后可恢复、绝不重复执行。以后买服务器后把中间服务迁上线，执行器留在本机。
（本记录取代 F-027「飞书 ⇄ Claude Code 双向闭环」：旧桥 ~/.feishu_bridge 已停用、listener.py 已删除、计划任务 FeishuClaudeBridge 已禁用。P-022 MSIX 路径映射仍适用，已沿用到新架构。）

**方案 / 架构**:
```
飞书 ⇄ 中间服务 hub（唯一连飞书、唯一发飞书、任务状态唯一权威）
         ⇅ HTTP 协议 v1（127.0.0.1:8765 + Bearer 令牌；迁线上只改 HUB_URL）
  Claude 执行器   Codex 执行器   …（执行器互不通信，主动长轮询领任务）
  桌面 Hook（Claude Stop/UserPromptSubmit、Codex notify）→ 只上报中间服务
```
- 分工：中间服务 + Claude 侧 + 协议由 Claude 实现；Codex 侧按 docs/CODEX_ADAPTER.md 由 Codex 实现；飞书桥代码 Claude 独占修改（单一写入者）。
- 被否决：在旧桥上增量改（两个 AI 同时改同一份代码导致状态分叉、Hook 直接发飞书违背单一出口）；云端控制面（关机无法执行，云端只多排队，隐私成本高）；Codex hooks.json Stop Hook（需持久化信任，桌面端不弹信任提示，不执行）。
- 用户决定：目录外授权选方案 C（执行器无确认模式，grants 恒为空，A4/A5 暂不满足）；目录缺失必须用户确认；Claude 默认 Opus 5.5 + effort low；Codex 续跑完全放开（--dangerously-bypass-approvals-and-sandbox）。

**关键文件与接口**:
- docs/PROTOCOL.md — 执行器协议 v1：hello / claim（长轮询，领到即租约 90s）/ events（started·session·heartbeat·progress·result·failed·interrupted，(task,lease,seq) 幂等，每个事件续约）/ release（SESSION_BUSY）/ sessions/turns（桌面独立轮次）/ inbox（桌面同步）；错误码 LEASE_LOST、ALREADY_FINAL（终态重试视为成功）等。
- docs/CODEX_ADAPTER.md — Codex 执行器规格与验收 CX-1~CX-10。
- hub/store.py — SQLite(WAL)，所有状态迁移 CAS + BEGIN IMMEDIATE；表 tasks/events/msg_map/seen/outbox/turns/inbox/executors/task_starts/kv。
- hub/service.py — 路由、协议处理、统一发送出口 flush_outbox（飞书 uuid 幂等键、按回复目标保序、失败指数退避）、reap 回收、recover 重启恢复、离线补拉 backfill。
- hub/feishu.py — 飞书发送/回复/历史消息；结果卡片（标题「执行者 · 目录名」、副标题完整目录、超长按区块拆多张）。
- hub/api.py — ThreadingHTTPServer，hmac 比较令牌，请求体 ≤1MB。
- hub/config.py — ~/.feishu_hub/config.json（首次从旧桥导入 app_id/secret/白名单）、token、suggest_cwd=@SIRE_ROOT@\AI\SESSION、project_roots=[@CODE_ROOT@, @SIRE_ROOT@\AI]、daily_task_limit=20、task_timeout_sec=1800、危险关键词。
- executors/common/hub_client.py — 协议客户端（HubClient/TaskReporter/spool/flush_spool），执行器与 Hook 共用。
- executors/claude/executor.py — claude_exe=auto（自动选 Claude 桌面版自带最新 CLI，%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code\<版本>\claude.exe）；`--model claude-opus-5-5 --effort low -p --output-format json --permission-mode bypassPermissions`，续跑加 `--resume <sid>`；CLAUDE_CONFIG_DIR=~/.claude-feishu；结果与 session_id 从 JSON 输出取。
- executors/claude/hook_stop.py、hook_prompt.py — Claude 桌面 Stop 上报独立轮次（带 FEISHU_HUB_TASK_ID 则跳过）；UserPromptSubmit 从 inbox 取飞书往返注入上下文（ASCII 转义输出）。
- executors/codex/executor.py — 直接调用 npm 包内 codex.exe（不经 .CMD）；new→`codex exec --json -o <file> -`；resume→`codex exec resume … <sid> -`；会话被桌面占用（active writer 且未开始）→`codex queue --thread <sid> --message …` 只投递一次，上报 desktop_queue；MSIX 路径映射；启动时及每 60s 守护 ~/.codex/config.toml 的 notify 串接。
- executors/codex/hook_stop.py — 同时支持 stdin Stop JSON 和 notify 末参数 JSON（type=agent-turn-complete，字段 thread-id/turn-id/cwd/last-assistant-message）。
- tests/test_hub.py（79 项）、tests/test_codex_executor.py（20 项）— 进程内起中间服务、飞书打桩、假 CLI，不触网。

**飞书用法（路由规则）**:
- 私聊新任务严格格式 `【执行者 目录 内容】`（【】可省）：执行者 claude/codex；目录 = 默认目录 / 「xxx项目」（project_roots 一级子目录，大小写不敏感）/ 完整路径。不符合格式只回纠正示例 + 编号快捷操作（回复数字即执行），不建任务。
- `claude 项目列表` / `codex项目列表`：中间服务直接列出，不调 AI；回复「序号 内容」即在该项目建任务。
- 回复任务卡片：沿用卡片的执行者/会话/目录续跑；开头写「Codex执行：…」切换到同目录 Codex（同目录多个会话时拒绝以免串线）。
- 目录不存在 → NEED_DIR，回复路径或「默认」→ 回显 →「确认」才执行，绝不兜底。
- 危险关键词 → NEED_CONFIRM，回「确认」才执行；提示只有发起人可回复。
- 租约过期/执行中断/桌面队列超时 → NEEDS_RECOVERY，回「续跑」（带 resume_hint 重派）或「放弃」，绝不自动重跑。
- 「你分析，Claude执行」协作指令 v1 只记录不执行。

**任务状态机**: RECEIVED → NEED_EXECUTOR/NEED_DIR/NEED_CONFIRM →（用户补充确认）→ QUEUED → LEASED →（desktop_queue: WAITING_EXTERNAL）→ RESULT_SAVED → DONE；旁路 FAILED、NEEDS_RECOVERY、CANCELLED。结果先落库再入发送队列，发送失败只重发不重跑；同 (executor,session) 与同目录同时最多一个租约；日上限按领取计数（续跑也算）。

**部署与运维**:
1. 计划任务（登录时启动，失败每分钟重启 999 次，pythonw 无窗口）：FeishuHub（`-m hub.main`，工作目录 feishu-hub）、FeishuHubClaudeExecutor、FeishuHubCodexExecutor；旧 FeishuClaudeBridge 已 Disabled。
2. Claude 桌面：~/.claude/settings.json 的 Stop→executors/claude/hook_stop.py、UserPromptSubmit→hook_prompt.py；CC-Switch 的 cc-switch.db（settings.common_config_claude 与 proxy_live_backup）同步为新 Hook，防 CC-Switch 覆盖。
3. Codex 桌面：~/.codex/config.toml `notify = [codex-computer-use.exe, "turn-ended", "--previous-notify", "[\"pythonw.exe\",\"…\\executors\\codex\\hook_stop.py\"]"]`；hooks.json 不挂 Stop（避免日后信任后重复上报）；Codex 执行器守护该串接。
4. 数据与日志：~/.feishu_hub/（config.json、token、hub.sqlite3、hub.log、executor_claude.log、executor_codex.log、runs/、spool/）。
5. 常用检查：`Invoke-RestMethod http://127.0.0.1:8765/v1/health`；`Get-ScheduledTask FeishuHub*`；查 tasks/outbox 状态；重启中间服务 `Stop-ScheduledTask FeishuHub` + 结束 `hub.main` 进程 + `Start-ScheduledTask`。
6. 回滚：停三个 FeishuHub* 任务 → 恢复 settings.json / config.toml / hooks.json / cc-switch.db 的 .bak-* → 从 ~/.feishu_bridge_bak_20260924b 恢复 listener.py → 启用 FeishuClaudeBridge。

**验证方法**: 两套测试 `python tests/test_hub.py`（79）与 `python tests/test_codex_executor.py`（20）全过；真实链路 2026-09-24 实测：Claude/Codex 私聊新建、回复续跑、Codex desktop_queue（桌面占用会话 → queue → 桌面 notify 回报匹配 → DONE）、桌面对话推送飞书均走通，1 小时 7 任务全 DONE、outbox 全 SENT；守护实测：人为冲掉 config.toml 串接后执行器启动几秒内补回。

**踩坑**: 见同日 P 记录「【飞书自动化】多 AI 中转切换踩坑合集」。

**状态**: 已完成（已上线运行；遗留：CX-3 测试偶发失败、手动 codex exec 也会推送卡片、需登录 Windows 才启动）


### F-042: 用现状审计建立项目基础文档基线并标出事实冲突

**日期**: 2026-09-25
**项目**: driverSoftware（D:\code\driverSoftware）
**关键词**: 项目基础文档清单, AI执行规则, AGENTS.md, 文档事实源, driverSoftware, 协议版本冲突, OpenAPI, 软件许可, SIRE文档审计

**需求场景 / 现象**: 仓库已有多个入口文档、AI规则、技能说明和历史文档，但缺少一份可供新项目搭建或现有项目补齐时使用的统一基础文档清单。用户记得之前做过该清单，需回溯知识后再核查当前仓库，避免重复造清单或把过期信息当成现行事实。

**根因**（问题类必填）: 项目知识分散在 README、AGENTS、CLAUDE、docs、skills、构建脚本和打包说明中，规则之间存在启动命令、协议版本、测试方式和 wheel 版本等不一致；目录清单也不能单独裁决哪个说法才是运行时事实。

**方案 / 架构**: 新增 `docs/PROJECT-DOCUMENTATION-BASELINE.md` 作为基础文档分类、建档顺序和仓库差距清单。将 AI 规则、项目上下文、README/上手、测试、技能列为基础层；架构、安全配置、用户指南、API/协议、贡献、发布、CI、运维、许可/SBOM 依实际项目纳入。要求关键事实有唯一权威源，其他文档链接引用；将可证实事实、文档冲突、待核实结论分开表达。历史知识 F-024 仅借鉴规则分层结构，旧发布规则需重新核验；F-019 为较早工作流快照，不直接复制旧约束。

**关键文件与接口**:
- `docs/PROJECT-DOCUMENTATION-BASELINE.md` — 当前仓库基础文档盘点、优先级和补齐清单。
- `AGENTS.md`、`CLAUDE.md`、`README.md`、`docs/`、`skills/`、`.gitlab-ci.yml` — 盘点范围内的项目规则、入口、技能、CI 文档和配置。
- `.sire/runs/R20260925-053031/evidence/U-01/qa/r7-results.md` — T01-T10 文件/仓库级验收记录。
- `.sire/runs/R20260925-053031/evidence/U-01/qa/r8-integration.md` — 提交边界、交付一致性和跨单元验收。

**实施步骤**:
1. 检索共享知识库与向量库，回看既有记录 F-024/F-019，再检查当前项目规则和文档。
2. 按基础必需/条件必需/归档审计分类，记录每项用途、AI约束要点、事实源关系、当前证据及缺口。
3. 由独立审查角色检查清单覆盖、事实风险和提交范围，按建议修订并复核。
4. R7 对 T01-T10 做文件/仓库级检查，R8 核对需求映射、最终哈希和唯一文档提交；提交仅含目标文档，未推送。

**验证方法**: 本次静态文档验收 T01-T10 均 PASS；R6A/B/C 独立审查及三路交叉复核 PASS；R8 集成复核 PASS；最终提交为 `927e9a4ece55a4ce27bb707c1720e9a0337d6308`，仅包含清单文档且工作树干净。没有运行应用、安装包、项目测试、构建、服务或硬件验证，因此不能据此宣称它们通过。

**踩坑**: 旧文档相互引用容易制造虚假权威。例如协议材料出现 V3.1/V3.2/V3.3/V3.4 多种线索，wheel 版本和启动入口也不一致；用静态文档无法定性固件兼容矩阵、供应商 wheel 再分发许可、真实安装/服务行为。应在清单中写成明确待核实项，保留证据来源，不自行挑一个版本。法律授权须有明确许可/供应商证明，打包备注不是许可证。

**状态**: 已完成；产出为可复用的项目文档基线和有边界说明的仓库审计，适用于启动类似项目的文档规划，不能替代针对各项目的事实核验。

### F-043: 项目基础文档基线（可迁移完整原文）

**日期**: 2026-09-25
**项目**: 可迁移的项目搭建知识；来源为 driverSoftware 提交 `927e9a4ece55a4ce27bb707c1720e9a0337d6308`
**状态**: 已归档原文；项目仓库恢复动作由当前 run 的 U-02 单独处理
**关键词**: 项目基础文档清单, 项目搭建, AI执行规则, AI约束, 项目规范, 文档基线, 可迁移文档, driverSoftware, F-043, 完整原文, Markdown, SIRE知识库
**需求场景 / 现象**: 用户需要将项目搭建基础文档用于后续迁移。文档曾误加入 driverSoftware 仓库，用户要求只存入其 SIRE 知识数据库，以便之后复用。
**方案 / 架构**: 为避免正文中的 Markdown 标题被 SIRE 解析为新记录，将来源正文逐行加 `> ` 前缀。恢复令牌化正文：仅剥除每行开头恰好一个 `> ` 前缀，并以 LF 连接；结果是经过路径令牌化的正文。恢复源提交原文时，再将唯一 `@CODE_ROOT@` 替换为来源提交中对应的根路径原文。
**关键文件与接口**: 来源 `driverSoftware/docs/PROJECT-DOCUMENTATION-BASELINE.md`；来源提交 `927e9a4ece55a4ce27bb707c1720e9a0337d6308`；SIRE 规范源 `knowledge/global/global_dev_features.md`；生成索引 `knowledge/global/global_index.json`。
**令牌化 LF 正文 SHA-256**: `7796705122a4a3496313db7a46cd13e493542f71f2f7978608e6c2bf42b2008c`；令牌化正文 `15696` bytes。
**来源 Git blob（原始源）SHA-256**: `41ce790df8aa2a7387152e0e3a39cde4fecc42f1ef3f7698c4faf373d4681c7b`；`15692` bytes；`115` lines。
**验证方法**: 从引用区块逐行移除 `> ` 后以 LF 拼接，核对令牌化正文 SHA-256 为 `7796705122a4a3496313db7a46cd13e493542f71f2f7978608e6c2bf42b2008c`、长度 `15696` bytes；再将唯一 `@CODE_ROOT@` 替换为源提交中对应的根路径原文，核对恢复的来源 Git blob SHA-256 为 `41ce790df8aa2a7387152e0e3a39cde4fecc42f1ef3f7698c4faf373d4681c7b`、长度 `15692` bytes/`115` lines。另在共享知识 Markdown 与 machine/shared SQLite 中验证 F-043 唯一性、正文一致、FTS/向量检索、embedding 与数据库 integrity/manifest；逐库证据位于当前 run `evidence/U-01/remediation-002/`。

**原始文档（逐行引用编码）**
> # 项目基础文档清单与 driverSoftware 复查结果
> 
> 复查日期：2026-09-25
> 复查基线：`feature/offline-detection-dev`，HEAD `6e09c76`
> 目的：为新项目提供一份可落地的基础文档清单，重点约束 AI 的执行方式、明确项目使用和开发规范；同时记录本仓当前规则文档的重复、缺口和相互冲突之处。
> 
> ## 怎么使用这份清单
> 
> - 新项目按「核心必备」先建文档；「按项目条件」按产品形态和风险选用，不为凑文件数量而拆文档。
> - 每个主题指定一个唯一事实来源。其他入口只摘要并链接它；命令、版本、配置和流程不要在多个文件各自维护。
> - 可以合并简单项目的短文档，但保留清晰章节、责任人和链接。随着项目复杂度增长，再拆成独立文档。
> - 项目规则写成可核对的动作：什么情况下触发、必须/禁止什么、用什么证据验收、哪些动作需要用户授权。
> - 文档中标明适用平台和版本。没有实测的命令、路径、硬件流程和结论，要明确标为未验证。
> 
> ## 一、核心必备文档
> 
> | 文档 | 唯一职责与最低内容 | 建议验收点 |
> |---|---|---|
> | `AGENTS.md`（或项目选定的 AI 主规则文件） | AI 项目级执行合同：规则适用范围与优先级、开工前必读顺序、用户沟通语言、需求拆分、允许/禁止操作、外部副作用授权边界、代码/文档修改流程、验证与证据要求、提交/推送/发布边界、文档维护要求 | 新会话能按入口找到正确上下文；规则用“触发条件—动作—证据—授权”描述；不要求 AI 猜测权限或唯一事实源 |
> | `docs/PROJECT-CONTEXT.md` | 稳定的项目背景和协作地图：项目目标/边界、模块/仓库/服务关系、需求入口、结果回填位置、交接机制、外部资源、本机配置的逻辑名称与存放位置 | 不放密钥或易变的个人绝对路径；首次接手者能知道从哪里取需求、交付结论 |
> | `README.md` | 面向开发者的项目入口：项目用途、能力边界、技术栈、目录导览、快速安装/启动、文档导航、已知限制 | 快速开始的每条命令已在目标环境验证；链接有效；与安装脚本和规则文件一致 |
> | `docs/ONBOARDING.md` 或 `docs/DEVELOPMENT.md` | 开发者环境搭建：依赖和版本、安装、配置、运行、常见故障、接手验收、清理方式 | 新环境按文档能完成启动；依赖安装不污染用户全局环境；配置示例不含真实秘密 |
> | `docs/TESTING.md` | 测试总索引：测试层级和目的、可运行命令、环境/硬件前置、通过标准、人工检查边界、失败时证据采集；链接专门测试用例和技能 | 明确单元、集成、UI、硬件/现场测试各自的执行条件；静态检查不冒充运行验证 |
> | 模块/场景技能，如 `docs/skills/` | 仅写特定模块或高风险场景的细节：技术不变量、操作顺序、排查步骤和验证方式 | 适用范围明确；被主规则中的“模块→必读文档”索引准确引用；内容与当前代码/工具匹配 |
> 
> ### AI 执行规则至少要说清
> 
> 1. **任务入口与范围**：从哪里读取需求；如何区分用户目标、项目现状和历史记录；不确定时先做哪些独立检查。
> 2. **执行约束**：改动前的阅读要求、修改范围、数据/凭据处理、对其他仓库和设备的边界。
> 3. **风险动作的授权**：例如删除或覆盖数据、向设备写入/运动、使用秘密、向外部系统发消息、部署、推送或正式发布；分别规定何时必须先得到用户明确指示。
> 4. **验证与证据**：按改动风险列出需要运行的命令、人工/可见验收条件、证据落点；明确没运行的检查必须如实说明。
> 5. **完成与交接**：结果写到哪里、文档何时同步、是否需要审查、提交/推送的界线以及最终汇报格式。
> 
> 硬件控制、数据迁移和安全敏感项目应把高风险动作拆成独立条款，写明安全前置条件、停机/回滚方式和操作者确认点。不要只写“谨慎”“确保质量”等无法验收的口号。
> 
> ## 二、按项目条件选用的文档
> 
> | 文档 | 适用条件 | 应覆盖内容 |
> |---|---|---|
> | `docs/ARCHITECTURE.md` | 多模块、多服务或关键数据流较复杂 | 组件边界、依赖方向、主要数据流、接口所有者、关键不变量、外部系统关系；简单项目可由 README 的架构章节承担 |
> | `docs/CONFIGURATION.md` / `docs/SECURITY.md` | 有环境变量、凭据、用户数据、外部服务或权限边界 | 配置来源和优先级、秘密的保存/注入/轮换、日志数据分类、最小权限、样例配置和撤销办法 |
> | 用户指南/操作手册 | 项目有非开发者操作者或现场流程 | 常见任务、输入输出、状态与错误处理、安全前置条件、恢复/停止操作 |
> | API / 协议 / 数据格式规范 | 有服务接口、设备协议、文件格式、跨进程或跨团队契约 | 字段和编码、错误处理、兼容规则、版本对应关系、规范真相源和变更同步责任 |
> | `CONTRIBUTING.md` 或开发流程章节 | 多人协作、代码审查或特定分支流程 | 分支、提交、审查、合并、回滚；通用 AI 规则应链接主规则，不复制一份 |
> | `CHANGELOG.md` 与版本策略 | 持续交付、需要追踪用户可见变更 | 版本号唯一来源、兼容策略、升级/停发说明、用户可读变更记录 |
> | `docs/BUILD-AND-RELEASE.md` / `docs/PACKAGING.md` | 有构建产物、安装包、容器或部署 | 构建入口、环境、产物、排除项、签名、发布触发、验收、回滚 |
> | CI/CD 配置说明 | 存在自动化验证或发布流水线 | 触发条件、门禁、产物、机密变量管理、发布责任；文档应解释实际配置，不能另造流程 |
> | 运维与备份恢复手册 | 有线上服务、持久化数据、现场设备或长期运维 | 监控、日志、备份、恢复、升级、回滚和故障采集 |
> | `LICENSE` / `NOTICE` / 第三方清单（如 SBOM） | 所有项目都应确认项目权属；尤其使用或再分发第三方组件时 | 项目许可/内部使用状态、依赖许可证、版权声明、供应来源、再分发义务和责任人 |
> 
> ## 三、目录入口与唯一事实源
> 
> 建议在主规则中保留一张映射表，而不是重复正文：
> 
> | 修改区域/任务 | 必读的项目上下文 |
> |---|---|
> | 全部任务 | AI 主规则、项目上下文、README、相关测试说明 |
> | 指定模块 | 对应架构/接口说明和该模块 skill |
> | 接口或协议变更 | 当前版本的规范、兼容矩阵、相关单元/集成测试 |
> | UI 变更 | UI 测试指南、可见验收方式和对应页面说明 |
> | 发布/部署变更 | 版本策略、构建/发布说明、CI 配置和回滚步骤 |
> 
> 其他 AI 工具的入口文件（例如 `CLAUDE.md`、Copilot 或 Cursor 规则）只保留工具特有启动信息和主规则链接。若工具必须有专用约束，注明它与主规则的关系及维护责任，避免出现两套不一致的硬规则。
> 
> ## 四、建议的建档顺序
> 
> 1. 定义项目目标和约束，创建 `README.md`、AI 主规则和项目上下文。
> 2. 建立可重复的新环境安装/启动流程，并据此完成 `ONBOARDING.md`。
> 3. 按真实代码边界补充架构、接口/协议规范和模块技能；在 AI 主规则中建立必读映射。
> 4. 建立测试总索引、配置/安全说明和用户手册，填入可运行的真实命令和验收条件。
> 5. 有持续交付时补齐版本、变更记录、构建发布、CI 和回滚文档；确认项目与第三方许可义务。
> 6. 每次改动命令、接口、版本、配置键或发布流程时更新唯一事实源；在合并前检查死链、过期路径和相互冲突的说法。
> 
> ## 五、driverSoftware 当前复查
> 
> ### 已有且可复用
> 
> | 主题 | 仓库现有入口 | 判断 |
> |---|---|---|
> | AI 项目规则与模块映射 | 根目录 `AGENTS.md` | 主规则较完整，覆盖中文协作、工作流、测试、硬件和发布边界；应继续作为 AI 规则唯一源 |
> | 项目上下文 | `docs/PROJECT-CONTEXT.md` | 已说明需求来源、结果回填、相邻资源、本机配置分层和协作方式 |
> | 新人接手 | `docs/ONBOARDING.md` | 已有 Windows 环境、权限、凭据、硬件和接手步骤 |
> | 模块技能 | `docs/skills/` | 已有硬件、reader、再标定、UI、自测和排障资料；其中个别入口已过期，见下方问题 |
> | 用户操作指南 | `frontend/guide/` | 面向应用操作的指南已存在；其中 `tests.md` 是应用内测试功能的使用说明，不等同开发测试标准 |
> | 构建和发布 | `docs/PACKAGING.md`、`scripts/`、`.gitlab-ci.yml` | 有打包规则、脚本及 tag 触发的 CI 链路；CI 实际定义在 `.gitlab-ci.yml`，文档要与它同步 |
> | 依赖与启动 | `requirements*.txt`、`setup.bat`、`start.bat` | 入口存在，但 README、规则文档和启动脚本的说明不完全一致 |
> | 协议资料 | `docs/protocol/`、旧入口 `docs/rs485_protocol.md` | 有版本化协议文件；当前版本指向存在实质冲突，不能仅改一个链接解决 |
> 
> ### 需要统一或补充的事项
> 
> | 优先级 | 发现 | 建议动作 |
> |---|---|---|
> | P0 | **协议现行版本和 host 实现说明存在冲突。** `docs/protocol/README.md` 说当前固件是 V3.3；同目录 `rs485_v3.3.md` 又说明固件 v3.4.0+ 已改 MIT 刻度/参考系，且仓内没有 V3.4 正文；`AGENTS.md` 概括 host 仍是 V3.2，`core/protocol.py` 头注也标 V3.2，`core/__init__.py` 和 README 另有 V3.1 描述。host 命令层还按固件档案处理行为：`core/commands.py` 注释为 V3.3 MIT 发送布局、V3.2 telemetry 解码，`core/fw_profile.py` / `firmware_profiles/` 提供随固件版本变化的量程档案，仓内包含 v3.4.x 档案。旧的 `docs/rs485_protocol.md` 已自标过期，但 `CLAUDE.md` 仍引用它。 | 先对照固件仓的 `register_protocol.h`、固件 tag 与上位机实际帧编解码及档案分支建立固件—协议—host 兼容矩阵；确认后再指定唯一当前规范。没有完成这项核实前，不把 V3.3 或 V3.4 写成已确认的当前唯一版本。将旧协议入口替换为有效索引。 |
> | P0 | **wheel 版本/平台标签冲突。** 仓内实际文件为 `vendor/kingkong_calib-1.0.1-cp312-cp312-win_amd64.whl`，`requirements.txt`、锁文件和安装流程 pin 1.0.1；但 `README.md` 说 wheel 待加入，`vendor/README.md` 和 `docs/skills/encoder_calib_wheel.md` 仍写 1.0.0、`cp312-none-any`，`CLAUDE.md` 也写错 wheel 标签。 | 以实际 wheel、requirements pin 和可验证的安装结果统一依赖说明；清理旧文件名、平台范围及过时外部路径。不要把 Windows x64 wheel 描述成通用平台 wheel。 |
> | P0 | **快速启动入口不一致。** 根 `README.md` 展示系统 `py -3.12 -m pip install` / `py -3.12 server.py`；`AGENTS.md` 的开发速查和 `ONBOARDING.md` 要求依赖进入仓内 venv，但 `AGENTS.md` 的 worktree 示例又用系统 `py -3.12 server.py`；`CLAUDE.md` 启动/硬件测试示例和 `docs/PACKAGING.md` 的浏览器启动表也写系统 Python。`start.bat` 在 venv 缺失时会退回系统 Python。 | 统一 README、AGENTS（包括 worktree 例子）、ONBOARDING、CLAUDE 和 PACKAGING 中推荐的开发/测试入口；明确 `start.bat` 的系统 Python fallback 是支持路径还是应移除，保证脚本行为与“禁止全局安装”的规则一致。区分开发运行入口和 CI/打包命令。 |
> | P1 | **测试说明散落且有过期 skill。** 没有统一 `docs/TESTING.md`；`docs/ui_test_cases.md` 是 UI 用例，`frontend/guide/tests.md` 是产品功能说明。被 `AGENTS.md` 指定的 `docs/skills/playwright_ui_self_test.md` 仍使用 `new-webgui/web_gui/` 路径和 headless 操作，而当前前端位于 `frontend/`，主规则要求最终用户可见验收使用可见 GUI。 | 建立测试总索引，分清单元、服务集成、UI、硬件测试；更新/替换过期 UI skill，写清自动化诊断和最终可见验收各自的范围与通过标准。 |
> | P1 | **架构与 API 信息未形成统一入口。** `CLAUDE.md` 独有较多组件、端点、WebSocket 和不变量说明。FastAPI 默认生成 OpenAPI 文档，因此不能说 REST API 完全没有规格；问题在于没有指定 OpenAPI/代码/文档谁是维护真相源，WebSocket 契约也未集中说明。 | 先把经核实且仍有效的 CLAUDE 独有信息迁移到选定的架构/测试/API 文档，再将 `CLAUDE.md` 收敛成 AI 主规则入口和必要的工具特有说明。明确 REST OpenAPI 的责任源及 WebSocket 契约维护处。 |
> | P1 | **许可证和第三方再分发状态未闭环。** 根目录未见独立 `LICENSE`、`NOTICE`、`COPYING` 文件；README/AGENTS/CLAUDE 说明项目为 `UNLICENSED` 内部使用。打包产物内有 Chromium/Electron 许可证文件，但这不能代表源码根目录说明完整。wheel skill 中“无 license / 无网络验证”描述的是安装/激活行为，不能据此判断著作权许可证或再分发授权；该文档本身不足以证明 vendor 分发权。 | 确认项目权属以及 wheel/vendor 的授权和再分发条件；按实际义务补充第三方声明或依赖清单。仅有“内部使用”说明或技术上的激活行为说明，不能替代第三方组件的授权核实。 |
> | P2 | **其他维护入口仍可能漂移。** README 对 wheel 的存在状态已过期；`CLAUDE.md` 同时有过时规则、命令、协议入口和 wheel 文件名。 | 建立 README 文档导航；在移动 CLAUDE 独有有效信息后，将工具适配入口缩成短指针；每次改命令/依赖/协议时检查 README、AGENTS、ONBOARDING、skill 和脚本的一致性。 |
> 
> ### 当前最小补全清单
> 
> 1. 核对固件与 host 兼容矩阵，决定当前协议规范版本及其唯一入口。
> 2. 统一 README、ONBOARDING、AGENTS、CLAUDE、PACKAGING 与启动脚本的安装和启动方式。
> 3. 修正 wheel 版本/平台标签，并清理旧路径、旧文件名和无效外部依赖描述。
> 4. 新增 `docs/TESTING.md`，更新过期 UI skill 和 CLAUDE 测试说明。
> 5. 迁移并核实 `CLAUDE.md` 中的架构、端点和不变量内容，再让该文件成为主规则的薄适配层。
> 6. 确认项目及 vendor 第三方组件许可/分发边界，补充适用的声明或清单。
> 
> ## 六、查找范围与限制
> 
> - 已检查仓库规则、README、项目上下文、onboarding、测试相关文件、协议入口、打包/CI、依赖与 wheel 文件名，并搜索仓库 Markdown 文件名和标题。
> - 在 driverSoftware 仓库、仓库内 `.sire/runs`、`@CODE_ROOT@\.sire/runs` 和共享知识中查找过往项目基础文档清单。未找到一份独立旧清单。最近似的归档是 SIRE F-024（AI 工程化基建模板）和 F-019（2026-09-15 的仓库工作流快照）；F-024 可参考其规则分层，但示例版本/流程仍需以当前仓库核实；F-019 记录的版本基线与部分发布规则已可能过时或与当前 `AGENTS.md`/CI 不一致，只作历史定位，不直接照抄。两者都不是完整的新项目文档目录清单。
> - 这次是静态文档与路径复查；没有运行项目测试、构建、服务或设备流程，也没有读取固件仓来裁定当前固件版本。因此协议兼容矩阵、安装成功、第三方再分发授权仍需分别核实。
> - 本清单是项目文档设计与现状审计，不代替各模块规范、脚本行为或用户授权。
> 


### F-044: Unity/Blender 战车 RPG 的美术启动约定

**日期**: 2026-09-27  
**项目**: GAME（原创废土战车 RPG）  
**状态**: 已归档（视觉方案仍需实景验收）  
**关键词**: Unity 美术, Blender, 战车, 模块化武器, 挂点, 俯视 2.5D, Low-poly, Toon, 废土, 资产生产

**背景**: 游戏机制实现与美术准备并行；项目 GDD 已确定固定俯视 2.5D、Low-poly/Toon、低饱和盐尘色系，并在 `Data/parts.csv` 定义车辆武器挂点。

**决策**: 美术准备先建立视觉基线和首辆轻型车的可读剪影，再扩充环境与敌人；可替换武器作为独立网格。轻型底盘挂点必须精确命名 `Mount_Main`、`Mount_Sub`，以现有 75mm 炮和 7.7mm 机枪数据作首批装备对照。车轮布局与比例属于待镜头/导入验证的制作提案；Unity 坐标按项目协作约定固定为 1单位=1米、Y-up、车辆前向+Z，武器炮口+Z。

**文件**: `D:/code/GAME/docs/ART_BIBLE.md`; `D:/code/GAME/UNITY/Assets/Art/Concepts/TNK_Light_Rover_Concept_v01.svg`。

**验证与限制**: 概念 SVG 可解析；挂点和武器 ID 与 CSV 对照一致。Unity 工程根目录为 `UNITY/`；未执行 Blender/FBX/Unity 导入，也未通过真实俯视镜头验收。工作区中尚无本概念对应的 Blender 源文件或 FBX；最终比例、材质表现和换装效果需在 Unity 中确认。


### F-045: 舵机加密OTA的协议及ACK丢失恢复

**日期**: 2026-10-08
**项目**: driverSoftware
**关键词**: 加密OTA, AES-128-CBC, PKCS7, Bootloader3.4, SetCrypto, ACK丢失, 会话恢复, 96B, 明文兼容

**需求场景 / 现象**: 舵机 Bootloader 3.4 同时支持明文与加密 OTA，上位机需要显式选择加密，3.3 及以下继续明文。

**方案 / 架构**: 完整含 CRC16 的命令帧先 PKCS7 补齐，再 AES-128-CBC 加密；线上为随机 IV(16B) + 密文。Ping 和回复为明文。初次 SetCrypto 开启为明文，加密状态下关闭也必须密文。采用已有 pycryptodome，不复制固件纯 Python AES。API encrypt 默认为 false，页面按 boot Ping 的版本允许选择。

**关键文件与接口**:
- core/ota_crypto.py — encrypt_frame，64B 写块产生 96B 下行帧。
- core/commands.py — boot_set_crypto、_boot_send_raw，严格检查开关 ACK 的 CRC/ID/子命令/status。
- server.py — OtaFlashReq.encrypt、api_ota_flash，版本拒绝与会话恢复。
- frontend/js/pages/bootloader.js — 加密选择、确认文案、升级结果。

**实施步骤**:
1. 按 workspace.json 找固件，读取包含加密实现的分支，而非默认检出版本；双端密钥逐字节核对。
2. Boot Ping 确认版本 ≥3.4，SetCrypto 有效 ACK 后才能 SetMode 和擦写，不自动降级明文擦写。
3. 克隆命令对象隔离加密状态，使用 OTA 互斥锁阻止并行流水线。
4. 留在 boot 时密文关闭；开启被拒或关闭 ACK 丢失时再尝试明文关闭，失败提示重启。Jump ACK 丢失时提示先重连确认。

**验证方法**: 相关 pytest 87 项通过，其中加密用例 21 项；固定 IV 与固件 3.4 脚本七种帧长度逐字节一致；可见 Chrome 经真实页面/HTTP 与模拟 boot 完成加密、明文、旧版明文、开启无 ACK 四条路径。未连接真机，不能作为 Analyzer 或 boot 实体验收。

**踩坑**: 固件主检出脚本仍使用旧测试密钥；3.4 分支已改为与 Boot 一致。照主检出脚本复制会导致开启后命令全部无回应。不能把脚本“恒明文关闭”的旧注释当真相，新 Boot 在加密状态下只接受密文关闭。

**状态**: 软件实现与模拟验收完成，真机可见 GUI 验收待设备及逐次 OTA 授权。


### F-047: MPT arguments 解耦：'a'指令字段自描述查询（V4.2.1）

**日期**: 2026-10-10
**项目**: Analyzer_Encoder_DebugTest（C:\Users\Administrator\Downloads\Analyzer_Encoder_DebugTest；Test Script + Test Report，2026-10-09 V4.2.1 第6轮报告）
**关键词**: MPT, arguments解耦, 'a'指令, ARGUMENTS字段自描述查询, queryArgumentsField, getArgumentsByFieldQuery, argumentsLayoutToBuffer, verifyArgumentsFieldQuery, argumentsReadMethod, argumentsVersion=6, EncoderArgumentsV6, batSpeedMode, argumentsFieldLayoutTable, USARTInterface_Recali.c, fieldCount, ArgumentsErrorStatus, 'R'整块读取, EncoderBase.py, Analyzer, A~F协议回归, IAP, series=104, V4.2.1, a3950c3

**需求场景 / 现象**: MPT 固件的 ARGUMENTS 结构体加字段/改布局（argumentsVersion 3→5→6）时，上位机用 'R' 整块读回 + ctypes 按版本硬解析，必须每版同步改结构体，固件与上位机强耦合。MPT V4.2.1 起固件新增 'a' 指令（提交 a3950c3），让每个字段自描述（名字/偏移/大小/类型/值），上位机据此解耦。

**方案 / 架构**:
- 请求：`'a' + fieldIndex(u8) + CRC8`；响应：`status + payload + CRC8`，payload 小端：schemaVersion(1) argumentsVersion(4) fieldCount(1) fieldIndex(1) fieldOffset(2) fieldSize(1) fieldType(1: 0=u8/1=u16/2=u32) nameLength(1) name value。
- fieldIndex >= fieldCount 时固件回 status=ArgumentsErrorStatus(2)，作为遍历结束信号。真机 34 个字段，值与 'R' 整块逐字节一致（2026-10-08 验证）。
- 上位机：从 index=0 遍历到结束信号，校验响应回显 index、fieldCount==实际条数、上限 64 个字段；任一步失败整体返回 None，不返回半成品。
- 兼容策略（折中，并未彻底去掉结构体）：`argumentsLayoutToBuffer` 按 offset 把字段值拼回原始字节（空洞补 0，总长按 4 字节向上取整，真机 72B），再喂给原有 `ArgumentsHeader/EncoderArgumentsV5/V6.from_buffer_copy` 解析，所以下游代码零改动；通过 `modes["argumentsReadMethod"]`（"R" 默认 / "a"）或 `getArguments(readMethod=)` 切换，`layout` 同时保存在 `Arguments.argumentsLayout` 里。
- `byName` 字典（name→小端整数）可直接按字段名取值，是真正解耦用法的入口，目前未被主流程使用。

**关键文件与接口**（Test Script 目录）:
- `EncoderBase.py:1101-1248` — ARGUMENTS_FIELD_QUERY=ord('a')、queryArgumentsField（state: ok/end/status/fail，重试3次）、getArgumentsByFieldQuery、argumentsLayoutToBuffer、verifyArgumentsFieldQuery（'R' vs 'a' 逐字段对照 + 未覆盖区间非零检测）
- `EncoderBase.py:1306` getArguments(readMethod) ；`EncoderBase.py:2728+` Arguments.__init__/initArgumentsFromBuffer 里 readMethod=="a" 分支；`EncoderBase.py:2814-2822` argumentsVersion 5/6 → EncoderArgumentsV5/V6
- `DataFormatter.py` EncoderArgumentsV6（V5 末尾多 batSpeedMode，其余偏移不变）
- `test_mpt_protocol_regression_AtoF.py:1729` 回归脚本显式切 'a'；`test_iap_mpt20_standalone.py` IAP 刷机流程
- 协议脚本：mpt_0x64_protocol.py(RS485/422 0x64，5/7字节两种帧)、mpt_ssi_protocol.py、mpt_bus_protocol.py、mpt_t485_protocol.py、bissc_protocol.py；CRC.py(CRC8 多项式 x8+x7+x4+x2+x1+1)、Analyzer.py(M487_Universal 读取器 USB)

**验证结果**（报告 V4.2.1_L6EB981C478199E94，2026-10-09，真机）:
- IAP：1941/1941 包、496736 字节、43.3s，整区擦除(page7~127+Bank2)+0x5EE5 校验+0x6FF6 复位，刷机后 argumentsVersion 3→6、series 105→104。
- 全程 'a' 路径读 Arguments 的 A~F 回归：20 项主流程全 PASS，42 组分辨率覆盖矩阵全 PASS，CRC 失败 0，656.1s。'a' 路径首次在完整回归下验证通过。
- 基线 Arguments（'a'读出）：series=104, interface=202, baudrate=2500000, busID=31, internalResolution multi16/single17, hallNumber=9, rotorSize=15, sectionNumber=36, software=67240192, algoVersion=4060, batSpeedMode=0。

**踩坑 / 限制**:
- 固件字段表 `argumentsFieldLayoutTable`（USARTInterface_Recali.c）是人工维护静态数组：固件给 ARGUMENTS 加字段忘加表项时，'a' 会静默漏字段；用 verifyArgumentsFieldQuery 查 uncoveredRanges 里 nonZero 区间来发现。
- 'a' 不报告对齐空洞/尾部 padding，拼回时补 0。
- 老固件（argumentsVersion<6、series=105 等）不支持 'a'，需回退 'R'；刷机前读取仍走旧路径。
- 'a' 每字段一次往返（34 次），比 'R' 慢，高频读取场景别用。
- 后续解耦待办：主流程仍依赖 ctypes 结构体；若要彻底解耦，应改用 byName/字段名 + offset 的动态映射，并保留 'R' 兜底；写入侧（getUpdateArguments/dict_to_init_arguments）仍按 argumentsVersion 分支硬编码，未解耦。

**状态**: 已完成（只读分析归档；未改动任何脚本/固件）


### F-046: 打包应用通过兼容 profile 切换多仓库组合

**日期**: 2026-10-10
**项目**: EncoderPlotter 多仓库打包切换方案（架构咨询）
**关键词**: Git 子模块, submodule, 主仓库分支, 打包, 运行时切换, profile, manifest, commit SHA, launcher, 版本组合, rollback

**需求场景 / 现象**: 主仓库有多个需求分支，父仓库分别固定四个子模块的不同提交；希望在已打包桌面应用中点按钮切换兼容组合。工作区 EncoderPlotter 仓库包含 sub_embedded、sub_common、sub_algorithm、sub_automation。

**根因**: Git 分支和子模块工作树是构建期源码状态。打包后的可执行文件只包含当时编译进去的主程序与资源，不能因为 UI 点击就检出另一个主仓库分支；普通安装包也不会自动包含 Git 源码仓。

**方案 / 架构**: 将可选分支组合映射为有限的、CI 构建并验证过的 profile。manifest 固定主程序及四个子仓库的 commit SHA、应用/接口版本、构建产物路径和 SHA-256。仅切子模块且存在稳定 API/插件边界时，可在一个主程序包内并列加载模块；否则选择完整 profile 并重启。主仓库分支也有代码差异时，profile 必须包含完整应用构建产物，由稳定 launcher 切换版本；当前应用的按钮可以请求 launcher 完成停进程、校验、原子启用和重启。离线包预置允许 profile；在线方案下载签名产物，校验成功后启用，失败时保留旧版本。禁止把 git checkout 当成打包产品的运行时切换机制。

**关键文件与接口**:
- 父仓库提交中的 Git gitlink — 固定每个子模块的具体 commit。
- `profiles/<profile-id>/manifest.json` — 建议清单，包含主仓/子仓 SHA、兼容范围、产物路径与哈希。
- 稳定 launcher 的 `activateProfile(profileId)` — 停止进程、检查清单和文件、切换当前版本目录并重启。

**实施步骤**:
1. 建立允许组合与接口兼容矩阵，拒绝任意主/子仓分支拼接。
2. CI 按父仓提交递归取出四个 gitlink，构建完整 profile 并生成 manifest。
3. 通过同级版本目录发布 profile；launcher 先校验，再原子切换并保留一个可回退版本。
4. 真实验收覆盖正确组合启动、缺包/哈希错误拒绝切换、进程占用和启动失败回滚。

**验证方法**: 本条是未实现的架构建议，没有修改源代码、构建安装包或执行 UI 测试。实施后应在真实打包应用测试：选择的 profile 与五个提交 SHA 一致；无效清单保留旧版本；切换失败能恢复旧版。

**踩坑**: 包内同时放多个完整主程序会增加体积；Electron/ASAR 资源路径和 Windows 文件占用可能阻止覆盖；Python 后台服务、设备句柄和配置迁移会影响重启与回滚。先采用 side-by-side 目录和进程重启边界，不要原地覆盖正在运行的文件。

**状态**: 方案建议，未实现、未验证；离线/在线分发方式与具体目标分支待确认。


### F-048: EncoderPlotter_0903_01 数据生成四条链路与基线分叉（feature/data-generation）

**日期**: 2026-10-10
**项目**: EncoderPlotter_0903_01（分支 feature/data-generation，从 feature/iap-ota-sn@19072126 切出）
**关键词**: 数据生成, 生成标定数据, generateData, generatedDualData, ged_P, ged_Q, ged_T, IAP文件生成, EncoderCommandIapGenerateFile, iap-file-generator, 恢复出厂, feature/data-generation, feature/iap-ota-sn, develop 分叉

**需求场景 / 现象**: 用户说"新建分支处理数据生成的相关逻辑"。"数据生成"在本仓库不是唯一指代，直接动手会改错链路；两条基线（develop 与 feature/iap-ota-sn）的生成代码也不同，从哪切决定能改到什么。

**方案 / 架构**: 先定位全部调用点，再让用户选链路和基线。算法本体 `sub_algorithm/main.py generateData/generatedDualData` 归算法部门，不改，只改调用侧。主仓调用侧分四条链路（以 feature/iap-ota-sn@19072126 为准）：
1. 标定流程（再标定/局部标定采完霍尔后）：`controller/python/Encoder.py` ~3485/3495
2. IAP 升级第一阶段（进再标定采数据 → 生成新标定 P/Q/T → 刷固件后写回）：`Encoder.py` ~1503/1513
3. IAP 文件生成（离线，调试日志 + BIN → 生成 → 按布局合入 BIN → 加密）：`components/share/iap-file-generator.js` + `Encoder.py` ~2406；命令 `EncoderCommandIapGenerateFile`（`sub_common/Defines.py:93`、`controller/defines.js:95`）
4. 恢复出厂（按 arguments 版本重新生成写回）：`Encoder.py` ~4680/4718
另有 MES 不良码 `0-1-0-4 数据生成失败`（`sub_common/DefectiveItems.py:36`、`components/encoder/mes/mes.js:31`）。

**关键文件与接口**:
- 基线分叉（2026-10-10）：feature/iap-ota-sn 比 origin/develop 多 109、少 9 个提交。develop 上 Encoder.py 只有 4 处 generateData 调用，没有 IAP 文件生成模块；develop 独有 `8c0b948b fix: IAP 升级时重新生成标定数据，MPP 不再两个分支都落空`，feature/iap-ota-sn 上没有。

**实施步骤**:
1. `git grep -n "generateData(\|generatedDualData(" <ref> -- controller/python/Encoder.py`，对比两条基线
2. 让用户选基线和链路；本次用户选了 feature/iap-ota-sn，链路后续再提供
3. `git switch -c feature/data-generation feature/iap-ota-sn`；子模块不建分支，等真要改子仓时再按"子先父后"同名建

**验证方法**: HEAD == feature/iap-ota-sn == origin/feature/iap-ota-sn == 19072126，工作区干净，四个子模块 pin 不变。

**踩坑**: 叠在 feature/iap-ota-sn 上的分支，MR 目标应先指向 feature/iap-ota-sn（或等它合进 develop 后 rebase），直接对 develop 提 MR 会把那 109 个提交一起带上。如果改到 MPP 的 IAP 生成，记得 develop 上 8c0b948b 那条修复这条线上没有。

**状态**: 部分完成（分支已建，具体改动范围待用户提供）


### F-049: CI tag写入target并在内部版界面显示

**日期**: 2026-10-12
**项目**: EncoderPlotter_0903_01 / 当前仓库
**关键词**: Git tag, CI_COMMIT_TAG, target.json, internal build, 构建标签, versionSuffix

**需求场景 / 现象**: CI 由 Git tag 触发打包，但应用左下角版本与设置页仍显示 commit hash，难以直接识别安装包对应的 tag。

**根因**（问题类必填）: gen-target.mjs 只将 CI_COMMIT_SHORT_SHA 写入 randomStamp，未把 CI_COMMIT_TAG 编入 target.json，渲染层没有可读 tag。

**方案 / 架构**: gen-target.mjs 将 CI_COMMIT_TAG 写入 target.tag。版本组件仅在内部版显示该字段：左下角版本后缀和设置页构建标签；内部 test 包的测试版号字段优先显示 tag。外部版隐藏，未带 tag 的本地构建回退原显示行为。

**关键文件与接口**:
- `scripts/gen-target.mjs` — 将 CI_COMMIT_TAG 写入 target.json 的 tag 字段。
- `components/analyzer/version.js` — 内部版 buildTag 与左下角版本后缀。
- `components/analyzer/version.html` — 设置页 tag 行及测试版回退。
- `components/i18n.js` — 构建标签中英文字段。

**实施步骤**:
1. 读取 GitLab 预定义的 CI_COMMIT_TAG，无需为每个 tag 构建 job 重复传参。
2. 内部版显示完整 tag；外部版不显示。
3. CI 无 tag 时保持原有随机 stamp/版本逻辑。

**验证方法**: 用测试 CI_COMMIT_TAG 生成 target.json 并确认 tag 字段存在；Node 语法检查与 git diff --check 通过。真实 Electron 界面操作未执行，待 GUI 环境验证。

**踩坑**: test/dev 包原先在左下角后缀和设置页显示 commit 短 hash；内部版应以 Git tag 作为识别名，同时保留 commitInfo 哈希用于代码追溯。

**状态**: 部分完成（代码已实现；真实 GUI 验收受限）


### F-050: DPB单圈标定采集圆环置灰

**日期**: 2026-10-12
**项目**: EncoderPlotter_0903_01
**关键词**: DPB, 单圈标定, 圆环, calibrationChart, ringTarget, ECharts, dispose
**需求场景 / 现象**: 仅标定内圈或外圈时，未参与采集的环形分段和三角指针需要置灰。
**方案 / 架构**: 使用 analyzer.calibration 的目标设备 series 与 onlyInnerCalibration/onlyOuterCalibration 计算 ringTarget；watch 在选择时重绘，calibrateData 事件按实际目标清空另一圈旧绿色并设置 markPoint.itemStyle。both 恢复红绿指针。
**关键文件与接口**: components/encoder/calibrationChart.js 的 ringTarget、applyRingTarget、initChart；components/encoder/device.js 的 HallCollectingProcess 事件。
**实施步骤**: 初始化及进度更新均应用目标状态；重绘前 dispose 旧 ECharts；innerSeries 深拷贝避免共享对象残留。
**验证方法**: VM 断言覆盖仅内圈、仅外圈、残留绿色、both 恢复；node --check 和 git diff --check 通过。算法指定 e354d9c 的配置测试 29 passed。真实界面点击和硬件采集未验证。
**踩坑**: 仅跳过非目标进度更新不能清除旧绿色，三角指针仍会有色；新增选项 watcher 放大原重建未 dispose 的实例泄漏。
**状态**: 代码完成，真实界面验收受阻。


### F-051: ECharts采集图例说明与禁用圈独立深灰

**日期**: 2026-10-12
**项目**: EncoderPlotter_0903_01
**关键词**: DPB, 单圈标定, 圆环, calibrationChart, ringTarget, ECharts, dispose
**需求场景 / 现象**: 仅标定内圈或外圈时，未参与采集的环形分段和三角指针需要置灰。
**方案 / 架构**: 使用 analyzer.calibration 的目标设备 series 与 onlyInnerCalibration/onlyOuterCalibration 计算 ringTarget；watch 在选择时重绘，calibrateData 事件按实际目标清空另一圈旧绿色并设置 markPoint.itemStyle。both 恢复红绿指针。
**关键文件与接口**: components/encoder/calibrationChart.js 的 ringTarget、applyRingTarget、initChart；components/encoder/device.js 的 HallCollectingProcess 事件。
**实施步骤**: 初始化及进度更新均应用目标状态；重绘前 dispose 旧 ECharts；innerSeries 深拷贝避免共享对象残留。
**验证方法**: VM 断言覆盖仅内圈、仅外圈、残留绿色、both 恢复；node --check 和 git diff --check 通过。算法指定 e354d9c 的配置测试 29 passed。真实界面点击和硬件采集未验证。
**踩坑**: 仅跳过非目标进度更新不能清除旧绿色，三角指针仍会有色；新增选项 watcher 放大原重建未 dispose 的实例泄漏。
**状态**: 代码完成，真实界面验收受阻。

**追加经验**: 非目标采集圆环用独立 disabled 深灰 #858B93，而未采集分段及图例保持原浅灰；修改 formatShowData 返回数组前100个实分段，保留末尾零值图例占位。ECharts 4.2.1 selectedMode=false 会使图例 silent，legend.tooltip 无法触发。最终使用 Vue DOM 图例和带 title 的问号按钮；保留 coin-front 的 Vue DOM，仅重建内部 canvas 图表实例。


### F-053: driverSoftware2 后端地图：server.py 装配、reader 三变体与运行形态

**日期**: 2026-10-13
**项目**: driverSoftware2（KingKong 感驱一体舵机 PC 上位机，@CODE_ROOT@\driverSoftware2；基线 VERSION 0.16.1 / 分支 feat/offline-detection-optimize / HEAD cf23634）
**取代**: K-REPO-DRIVERSOFTWARE-20260924（2026-09-24 的 v0.13.11 单段摘要，行号与规模已过时）
**关键词**: [driverSoftware2, 后端地图, server.py, FastAPI endpoint, reader_wrapper, reader_mp, reader_mp_worker, READER_MP, WEB_GUI_PORT, KK_READER, shared_memory, asyncio.Queue, 连接状态真相源, 双实现同改, HID独占, _conn_generation, ws monitor 空壳, 加接口, 8765, timeout, 无响应, 端口被占, config.json, 报告落盘, request_abort, _conn_generation, LinkDown]

**需求场景 / 现象**: 在这仓新增或修改任何后端功能前，必须先回答四个问题：请求从哪个函数进、帧从哪个 reader 出、reader 有几份实现要同改、开发态与打包态差在哪。原仓内文档只讲规则不给入口，逐次重新摸清 server.py（11178 行）代价高。

**方案 / 架构（分层与数据流）**:
`Browser/Electron → HTTP/WS (FastAPI, 默认 127.0.0.1:8765) → server.py endpoint → core/commands.py (V2Commands) → core/reader_*（HID 或 libusb）→ USB → KingKong Analyzer → RS485 → STM32G473 驱动板`。
- **启动**: `server.py:11154 main()` 读 `WEB_GUI_HOST`(:11156，默认 127.0.0.1) 与 `WEB_GUI_PORT`(:11157，默认 8765) → `_bind_http_socket()`(:11088) 先占端口，**绑成功后把实际端口回写 `os.environ["WEB_GUI_PORT"]`**(:11163) 并写端口回执文件 `_write_port_receipt(port)`(:11164)，再 `uvicorn.Server(Config(app)).run(sockets=[sock])`(:11170)。刻意不用 `uvicorn.run(host, port)`：会二次 bind 产生 TOCTOU，端口被抢时回执与实际不符。`__main__` 前置 `multiprocessing.freeze_support()`(:11177)。
- **运行形态分叉**: `server.py:341` `_USE_MP_READER = os.environ.get("READER_MP", "1") not in ("0","false","False","")` → 1 用 `core/reader_mp.py`（**打包默认**，子进程独占 HID+GIL），0 用 `core/reader_wrapper.py`（`start.bat:10` 硬写 0，开发态）。单例 `backend = ReaderBackend()` 在 `server.py:352`。
- **路由规模**: `grep -c '^@app\.' server.py` = **160**。分组与定义行：连接 `/api/scan|connect|disconnect|state|params` :955/:1025/:1124/:1163/:1190；台架 `/api/bench/*` :1429-1717；报告 `/api/report/*` :2008-2086；链路诊断 `/api/probe_device_ids` :2095、`/api/auto_baud` :2162、`/api/diag/link_triage` :2236；硬件连续流 `/api/scope/*` :2643/:2776/:2837/:2865/:4040/:4087/:4144；外部扭矩真值 `/api/jn/*` :2959-2984、`/api/dyn200/*` :3012-3408；力感知 `/api/force_calib/*` :3269-3344、`/api/force_test/*` :3655-3689；命令族锚点 `/api/cmd/mode` :4223、`/api/identify` :5318、`/api/cmd/save_config` :5549；回放与急停 `/api/mit/playback*` :4455-4766、`/api/estop/abort_work` :4727、`/api/comm_loss/*` :4841-5000；测量 `/api/measure/*` :5810-6532、`/api/self_test` :6077；标定 `/api/calibrate/*` :6884/:7560/:7810/:7971/:8018/:8177、pipeline :9767-9836；档案 `/api/fw_profile` GET/POST :8371/:8377；OTA :8393-8781；再标定 `/api/cmd/recal_*` :9268-9330；裸帧 `/api/raw*` :9425/:9439；Kt 与内圈零位 :9901-10031 / :9982-10017；**下线检测 `/api/offline-detection/*` :10148-10736**；黑匣子 `/api/diag/*` :10914-10987；`/api/changelog` :10776、`/api/meta` :11003。
- **WebSocket**: `/ws/monitor` :9470 的 `_monitor_loop`（:9511）在注释块之后直接 `return`（:9528），**实际一帧都不推**（历史空壳，前端已删"监控中"标签）；真正在用的是 `/ws/calibrate/pipeline` :9852 与 `/ws/kt` :10756，模式为 worker 线程 → `asyncio.Queue` → `call_soon_threadsafe`（:9737/:9743、:9884/:9948），WS 取到终态即关（:9871-9875）。
- **连接状态单一真相源 = server.py 模块级全局** :352-404：`backend` / `cmds` / `device_id` / `baudrate` / `device_id_confirmed`(:381) / `_last_probe_alive`(:387) / `connected_serial`(:390) / `connected_port`(:394) / `_conn_generation`(:402，断链代哨兵，给无 worker 对象的长跑 closure 做协作式取消；有 worker 的走 `request_abort()`)。**刻意没有 state 类**，前端靠 `/api/state`(:1163) 拉。
- **进程间**: `reader_mp.py:9-12` SHM ring（SPSC 无锁）+ `mp.Pipe` 控制通道；`_rpc` 带 seq 回显防乱序 :317（详见 :318-361）；父端 drain 游标 `_local_read_idx` :96、`_shm_drain_iter` :556（落后超过 NUM_SLOTS 就跳尾 :564）；热换帧 `update_continuous_frame` :467、ACT 双 item `set_aux_frame` :489。子进程 `reader_mp_worker.py:195 reader_worker()` 必须 top-level（Windows spawn pickle，文件头 :5 说明），SHM 布局 header 8B + 1024×128B :14-22。

**关键文件与接口（均属 F-053 后端地图，仓 = `@CODE_ROOT@\driverSoftware2`）:**
- `server.py:227-268` core import 集中区；worker 类一律延迟 import：fullpipe :9728/:9731、kt :9881、inner_zero :9973、od_* :10317-10319、force_calib :3260/:3291。
- `core/reader_wrapper.py`(1346 行) in-process 形态：`ReaderBackend` :736、`_HidReader` :500（`hid.enumerate(VID,PID)` → `open_path` :509-514）、`_LibUsbReader` :598（pyusb 直通，USB jitter 低约 60%，:590-599）、`_make_reader` 优先 libusb 且 `READER_FORCE_HIDAPI` 可关 :718-731、线格式 `bus_config_item` :379 / `build_packet` :419 / `parse_packet` :438、多读取器会话绑定 `KK_READER_ENV` :46（环境变量在 :62 读）与 `_kk_select` :50、`LinkDown` :204、`ensure_baud` :335。
- `core/reader_mp.py:85` `class ReaderBackend`（全文件 637 行）多进程父端，控制走 `mp.Pipe`、数据走 shared_memory ring。
- `core/reader_mp_worker.py`(911 行) 子进程侧。
- `core/blackbox.py`(569) 诊断黑匣子单例 `bb`（`log` :236 / `blob` :373 / `export` :419 / 环与配额 :164），全 fail-open（文件头 :1-7）。
- `core/paths.py`(68) 源码态与打包态日志根分流；`core/serial_tap.py` 总线计数 tap。
- 环境变量清单：`READER_MP`(server.py:341)、`WEB_GUI_HOST`/`WEB_GUI_PORT`(server.py:11156-11157，回写 :11163，`core/force_calib_runner.py:72` 复用)、`READER_FORCE_HIDAPI`(reader_wrapper.py:727)、`KK_READER`(reader_wrapper.py:46,62)、`FORCE_CALIB_SCRIPT`(force_calib_runner.py:96)、`BENCH_DUAL_READER`(同文件:500)、`KK_AUX_EVERY`/`KK_MIN_SOF_2ITEM`(reader_mp_worker.py:286,677)。

**实施步骤（怎么用这张地图）**:
1. 新加一个后端能力：先在上面 endpoint 分组里找最近的组，同组内加 `@app.*`，再进 `core/commands.py` 加高层 wrapper（协议层改动见同批 F 记录"协议层与固件档案门控"）。
2. 涉及 reader/总线时序：`reader_wrapper.py` 与 `reader_mp.py` **两份实现同时改**，用 `inspect.signature` 写测试钉住签名。
3. 打包态才复现的问题（管道乱序 / 子进程死 / 游标竞态）：本地显式 `set READER_MP=1` 再起服务。

**落盘与长任务生命周期**:
- 配置与报告根：`core/offline_detection.py:82 REPORTS_DIR = Path.home()/"Downloads"/"下线检测报告"`、同文件 :83 `CONFIG_PATH`；日志根策略见 `core/paths.py:4`（打包后 `resources/server/logs` 普通用户不可写，由该模块分流）与 :12-13（三个使用点：`fullpipe_worker.LOG_DIR` 的 `calib_*.log`、`server._RECAL_LOGS_DIR` 的 `recal_*` 标定产物、`server.REPORT_DIR`）；测试报告落 `logs/reports/` 而非 `docs/reports/auto/`（`server.py:1930` 注释）。
- 长跑任务取消：有 worker 对象的（fullpipe / kt）走 `request_abort()`（`core/fullpipe_worker.py:413`）；没有 worker 的 closure 用断链代哨兵 `server.py:402 _conn_generation` 协作式取消；链路断开统一由 `LinkDown` 处理器 `server.py:870` 收口。

**验证方法**:
- 结构核对（本次已实跑）：`grep -c '^@app\.' server.py` = 160；`ls core/*.py` = 39；`wc -l server.py` = 11178；`grep -n '_USE_MP_READER' server.py` = :341；`grep -n 'def main' server.py` = :11154。
- 起服务核对：`python server.py` 后请求 `/api/meta`(:11003) 与 `/api/state`(:1163)，端口取自回执文件而非配置文件。
- 双形态核对：`READER_MP=1` 与 `=0` 各起一次，`/api/scan` 均可列出读取器；`tests/unit/test_drain_guard.py:14-17` 断言 in-process 形态 `link.hot_iters` 恒 0。

**踩坑**:
1. **HID 全机独占**：一只 Analyzer 同时只许一个进程持有，其余实例只能当 HTTP 客户端；`import server` 有副作用即已抢占 HID（server.py:169-171 注释）→ 脚本别随手 import server。
2. **双实现接口改签名要两边同改**：`reader_mp.py:475-478` 注释实录 2026-09-22 只改 wrapper 未跟 MP 签名，结果每次热换帧 `TypeError` → HTTP 500。
3. **`hid.enumerate` 顺序不稳**：散落几十处的 `keys()[0]` 会抢错机器/错总线，选择逻辑收口在 `reader_wrapper.py:46-62` 与 `reader_mp.py:108`。
4. **`/api/scan` 的 serial 是固件编译时间戳，会撞键**（server.py:955-957）→ 真机台账另用读取器 USB 序列号做主键。
5. **`/ws/monitor` 是空壳**：按它做过"监控中"状态会永远不动；实时数据走 REST + `TELEMETRY_DISPATCH`（见前端地图记录）。
6. `AGENTS.md:321` 写"打包版默认 `READER_MP=1`（多进程 reader, `server.py:212`）"—— 该分叉现已迁到 `server.py:341`，文档行号过时；引用行号前先 grep。

**状态**: 已完成（静态勘察 + 全部行号本次逐条 grep 实测；未运行服务与真机，开发机常态不连硬件）


### F-054: driverSoftware2 协议层与固件档案门控：帧/命令/寄存器/profile 四层与新增命令链路

**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**取代**: K-REPO-DRIVERSOFTWARE-20260924 中与协议/寄存器相关的过时部分
**关键词**: [RS485 协议, protocol.py, Cmd, FactoryCmd, crc16, make_frame, commands.py, V2Commands, FwProfileUndetermined, registers.py, register_protocol.h, register_descriptions.py, fw_profile, firmware_profiles, 档案门控, 静默回退, 0x38 内圈零位, 停机写, 慢命令 0xFD, RS485 V3.3, 新加协议命令, recal_chain, 算法不许第二份, read_version, fw_git_sha, 0x0B, 力矩无响应, OTA]

**需求场景 / 现象**: 改任何一帧报文、一个寄存器地址、一条标定流程前，需要知道：帧格式在哪一层拼、寄存器地址的单一来源是谁、固件能力档案缺失时会发生什么、以及新增一条命令要动哪几个文件。这仓最容易出的事故是"静默回退旧路径不报错"和"手填档案值"。

**方案 / 架构（四层）**:
1. **帧层** `core/protocol.py`(337 行)：`core/protocol.py:16` 的 `class Cmd` 只是常量集合，**只有 5 个命令值**（DEFAULT/MIT/CLEAR_FAULT/RESET/FACTORY），V3.2 帧字段定义与 head byte 说明在 :17-36（`[ID:4 | T:1 | CMD3:3]`，T=bit3 为 1s 看门狗位，广播 0x0F 已于 V3.1 删除）；`FactoryCmd` 子命令 :49、`ReCalCmd` :71、`ReCalMem` :90、`STATE_NAME` :100、`FAULT_BITS` :126、`INTERNAL_FAULT_BITS` :142、`crc16` :243、`make_frame` :255、`head_byte` :261、`parse_frame` :302。
2. **命令层** `core/commands.py`(1642 行)：`class V2Commands` :204 是唯一对外门面。出入口收口在四个私有方法 —— `_send` 单帧同步 :285、`_send_mit_frame` :356、`_boot_send_raw` :1117、`_recal_send` :1288；其上按域分方法：运动 :454-530、寄存器 :497-620、慢命令 :635-847、boot/OTA :1076-1286、ReCal flash :1311-1636。`CmdResult` :26、`StatusSpec` :153、`FwProfileUndetermined` :98、MIT 缩放同步 `sync_mit_scales` :221。
3. **寄存器层**：`core/registers.py`(402 行) 文件头 :1-5 声明自己是固件 `Core/Inc/register_protocol.h` 的 **Python 镜像、单一来源**，改固件时同步改它；`core/register_descriptions.py`(526 行) 是与固件版本**无关**的语义描述表（单位/权限/说明），按名字 join，静态对表工具 `tools/check_register_descriptions.py` 是 build.bat Step 0 的硬门禁（scripts/build.bat:121-125）。
4. **能力档案层** `core/fw_profile.py`：档案目录 `PROFILE_DIR = <repo>/firmware_profiles`（:16），正式档案按固件版本命名 `v<X.Y.Z>.json`（当前 13 份，v3.3.0–v3.4.7）；联调用的 `dev-<sha>.json` 由 `tools/gen_fw_profile.py --rev <sha>` 现生成，仓内一份都没有；缩放值在 `set_active()` 时预计算成模块级 float，热路径只读 `_SCALE_*`（:7-10）。**门控行为**：任何依赖档案的调用在 `fw_profile.get_active() is None` 时 `raise FwProfileUndetermined`（server.py:3784-3794、:3845、:3935），异常处理器在 server.py:851；档案缺失则**静默回退旧路径、不报任何错**（AGENTS.md 军规 9）。

**协议 V3.3 相对 V3.2 的关键变更（F-054 协议层，逐条对过文档）**（`docs/protocol/rs485_v3.3.md`，当前文档版本；host 代码仍是 V3.2，证据在 `core/protocol.py:17` 文档字符串 —— 注意 `docs/protocol/README.md:30` 与 `rs485_v3.3.md:22-44` 都没写这句差异说明，别照着找）：
① 物理层删除"字节间空闲 <8bit 用于帧定界"；② 表 1/表 2 增加显式类型列（uint8/int16/int32/f32）；③ **发送帧取消 14-15 字节的 `n` 计数字段**，改为"14 起放 n 个地址、个数由帧长决定"，总长 `14+n+2`；④ 接收帧总长 `12+4n+2`；⑤ Fault 明确为按位 uint8；⑥ 文档头部新增 v3.4+ MIT 刻度对照块（θ 2²⁴/2π 输出端、ω 512、τ 2048）并记录 Kp/Kd 的 10000 误填事故，配套门禁 `tests/unit/test_fw_profile_mit_scales.py`；⑦ 0x0B 示例改 v3.3.0；⑧ 0x36 改为"标定写入勿手改，改转向见 0x68"；⑨ 新增 0x68 输出转动方向、0x69 LED 开关；⑩ CRC16 为 CRC16-CCITT、帧末 2 字节小端（`docs/protocol/rs485_v3.3.md:15`、:73），上位机实现就是 `core/protocol.py:243 crc16()`。协议版本源 = 固件 git tag，经寄存器 `0x0B` 映射。

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


### F-055: driverSoftware2 前端地图：13 页清单、路由注册五处、REST/WS 与示波器 uPlot 图表

**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**取代**: K-REPO-DRIVERSOFTWARE-20260924 中缺失的前端部分（旧摘要只有一句 "ESM 前端"）
**关键词**: [前端地图, frontend, 无构建 ESM, app.js, PAGE_BUILDERS, 加一个新页面, api.js, X-KK-Trace, MonitorSocket, PipelineSocket, KtSocket, telemetry:sample, scope-bar.js, uPlot, PAGE_PROFILE, 冻结看门狗, unthrottled-timer, setUnthrottledInterval, 后台节流, 0x4D 看门狗, 页面重建 innerHTML, pageCleanups, capabilities.js 受众分层, tokens.css, i18n, 示波器, 切页, 图表冻结, 不用构建, 13页, 受众档位, MAX_UI_LEVEL, confirmDialog]

**需求场景 / 现象**: 本仓前端**没有 build**（浏览器直接跑 ESM），也没有框架。加页面、改交互、调示波器之前需要知道：页面在哪注册、REST/WS 从哪进出、周期性发帧怎么不被浏览器节流、页面重建会漏掉什么。

**方案 / 架构**:
- **入口**: `frontend/index.html:199` `<script type="module" src="/static/js/app.js">`，`uPlot` 以 IIFE 全局挂载（:198），6 个 CSS 入口（:11-16）。改 `frontend/js/**/*.js` 直接生效（server 自动 serve 最新版）。
- **分层**: `js/app.js`(1654 行) 主编排（路由/懒建页/顶栏/scope 抽屉/急停）· `js/api.js` REST+WS 客户端 · `js/store.js:34 class Store` 全局 state + 事件总线 · `js/components.js` DOM helper 与弹窗（:8/:57/:86/:149/:242，弹窗焦点 :235）· `js/scope-bar.js`(4418 行) 示波器抽屉 · `js/capabilities.js:14 CAP_MIN_LEVEL` 受众分层门控 · `i18n.js` + `locales/{zh,en}.json` · `theme.js` · `link-health.js` · `blackbox.js` · `estop.js` · `unthrottled-timer.js` · `trip-snapshot.js` · `risk-tags.js` · `render-md.js` · `test-scope.js` · `bg-canvas.js`。
- **路由**: `app.js:221-237 const PAGE_BUILDERS` 共注册 **12 个页面**（motion/registers/calibrate/torque/console/tests/offline-detection/trajectory/bootloader/guide/diag/forcecal；`overview` 已删 :222、`scope` 页已删由抽屉自带 :224、`detection` 合并进 calibrate :230），懒建 `app.js:336`（`PAGE_BUILT` 集合 :238）。侧栏项在 `index.html:84-155` 的 `rail-item[data-page=…]`，容器是 `index.html` 里对应的 `<section id="page-…">`（如下线检测 :169）。
- **通信**: 唯一 REST 咽喉 `api.js:105 request()`；每请求带 `X-KK-Trace` 取证头（:115）；**默认不设超时**（:92-103 有意为之，长命令由后端控制）；HTTP 200 但 `ok:false` 也记为失败（:138）；结果回调钩子 `onApiOutcome` :81，由 `link-health` 单向订阅（:77，刻意不成环）。WS 三类：`MonitorSocket` :456 `/ws/monitor`、`PipelineSocket` :516 `/ws/calibrate/pipeline`、`KtSocket` :541 `/ws/kt`；消费点 `app.js:675` → `feedScope` :692 / `watchFault` :746，开关 `syncMonitorLifecycle` :724（仅 motion 页 + 已连接时开）。后端 `/ws/monitor` 是空壳（见 F-053），实时数据实际走 REST → `TELEMETRY_DISPATCH`（api.js:26-69）转 sample → `store.emit("telemetry:sample")`（:151）→ `scope-bar.js:726` 订阅。
- **加一个新页面（5 处，顺序固定）**: ① `index.html` 加 `rail-item` + `<section id="page-x">`；② `app.js:17` 区域加 import + `:221 PAGE_BUILDERS` 加键；③ `capabilities.js:14 CAP_MIN_LEVEL["page:x"]` 给定受众档位（如 `"page:offline-detection": 2` 在 :35）；④ `scope-bar.js:257 PAGE_PROFILE` 给该页的采样方案，**不需要 scope 就显式写 null**；⑤ `locales/zh.json`、`locales/en.json` 文案。
- **样式**: `css/tokens.css:3` 声明 `docs/theme-servo-cyan.md` 为单一真相源（cyan 主色阶 :45-49、字号阶 :93-101、布局根 token `--rail-w`/`--topbar-h` :104-105、light/dark 双份 :117/:171）；受众分层的"分段标题空段自动隐藏"（`docs/gui-design.md:144`）落在 `app.js:375-394 applyUiLevel()`。CSS 按 base reset / components / layout / pages 四层分文件。

**关键文件与接口（F-055 前端地图 · pages 清单，13 个文件）**:
- `motion.js`（运动）：`buildMotion` :174，MIT 五滑条 + presets，连续发帧 `restartCont` :3020、`setUnthrottledInterval(sender, softPollPeriodMs())` :3066，看门狗安全档 `WDG_SAFE_POLL_MS = 200` :3010 与 `Math.min(base, …)` 钳制 :3017、低频预警 :3057；Electron 形态判定（UA 含 `" Electron/"`）:158-172。
- `calibrate.js`（电机标定，2662 行）：`buildCalibrate` :190，多相位卡片（:259/:484/:1167/:1414/:1521/:1806/:1938/:2141/:2242/:2467），一键再标定 `api.pipelineStart` :739 + `PipelineSocket` :746。
- `offline_detection.js`（下线检测，1312 行）：`ITEMS` :21-28、`buildOfflineDetection` :58，页面级清理表 `pageCleanups`/`onPageRebuild` :52-59。
- `torque.js` 砝码摆臂 Kt（走 `/ws/kt`）· `forcecal.js` 力感知标定 · `registers.js` 寄存器读写 · `bootloader.js` 设备/改 ID/OTA · `trajectory.js` MIT 轨迹回放 · `console.js` 裸帧收发（`buildConsole` :154）· `tests.js` 测试套件 recipe runner（7374 行）· `diag.js` 黑匣子配置 :10 · `guide.js` 使用指南 · `detection.js` 已下线（页面不再注册，文件仍在）。

**受众档位与危险操作确认**: 档位由产物根文件 `MAX_UI_LEVEL`（`server.py:317`）下发；前端 `capabilities.js:7 UI_LEVEL_KEY`、:14 `CAP_MIN_LEVEL`、:91 取 `min` 过滤，`app.js:375 applyUiLevel()` 做 rail 项过滤与空分段隐藏；危险操作统一走 `components.js:149 confirmDialog({danger:true})`。**新功能要先决定落在哪一档** —— 客户包（L1/L0）看不到的入口等于没做。

**实施步骤（周期性发帧为什么不能用定时器）**:
1. `unthrottled-timer.js:3-14` 记录真机实证：页面 hidden / 窗口被遮挡时浏览器把主线程定时器节流，实测 `setTimeout(25)` 拖到 970ms，帧间隔越过固件 `0x4D` 看门狗 → **电机停转且锁存**；采样循环里圈数被钳还会产出"看似正常的假数据"。
2. 所以安全路径用本模块：Worker 定时器 `sleep(ms)` :59、`setUnthrottledInterval(fn, ms)` :101；或直接 `await` 链（实测 `tests.js` 里有 144 处 `await sleep`，采样循环形如 :3167/:3241/:3350 的 `while (performance.now() < tEnd) { … ; await sleep() }`）。
3. **别把 `setInterval` 当成"只是界面刷新"**（实测 `frontend/js/**/*.js` 共 19 处）。轮询/显示类有 `link-health.js:443`、`offline_detection.js:651/:756/:819`、`calibrate.js:2277`、`forcecal.js:606`、`test-scope.js:775/:886`、`trajectory.js:1628`、`tests.js:3816`；**但 `scope-bar.js:4132/:4145` 的 `this._timer = setInterval(() => this._tick(), period)` 就是软轮询发帧路径**（:4146-4148 自证：寄存器页起 Live 就逐 addr 打 `/api/cmd/reg_read`，跟回放帧抢同一条总线），`scope-bar.js:1436/:4140` 的 16ms `_hwDrainTick()` 同样在发请求。碰到这些循环要按第 1 条换成 `unthrottled-timer` 或 `await` 链。
4. `api.js:485 setInterval(ms)` 是给 `/ws/monitor` 发 `interval_ms` 消息的方法名，不是定时器，别看错。

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


### F-056: driverSoftware2 Electron 壳：拉起后端、端口回执与窗口安全项

**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，electron/ 壳，package.json 版本 0.16.1）
**关键词**: [Electron 壳, electron/main.js, startBackend, server.exe, resources/server, PORT_PINNED, 端口回执文件, killStrayBackends, backgroundThrottling, contextIsolation, nodeIntegration, devTools 客户包关闭, Menu.setApplicationMenu, kkdiag://, did-fail-load 重试, postmortem, diagnose.js, extraResources, 无 preload 无 IPC, user agent Electron, 黑屏, 起不来, npm start, nsis]

**需求场景 / 现象**: 桌面版和浏览器版行为不一致（切窗口后电机停转、devtools 能不能开、端口被占怎么办），或改了后端启动方式要确认壳侧是否跟上。需要壳与后端进程的关系图。

**方案 / 架构（壳只管三件事：拉起后端、拿真实端口、开窗口）**:
- **拉起后端**：`electron/main.js:144 startBackend()`。打包态 spawn `process.resourcesPath/server/server.exe`（:150-167，windowed 无 console，日志重定向到 `userData/server.log`，:160 注释说明不弹黑窗）；开发态用 `py -3.12 server.py`（:185-203，路径解析注意含空格的 `C:\Program Files\…` 会踩坑，:200 注释）。启动前先 `killStrayBackends()` 清理残留（:87）。
- **端口获取**：`PORT_PINNED = !!process.env.WEB_GUI_PORT`（:28）—— 只有人为钉住端口才信任它；否则**由 server 自绑后把实际端口写进回执文件**，壳读文件拿端口（:99-135，注释解释了"为什么是文件而不是 stdout"）。这与后端记录里 `server.py:11161` 回写 `WEB_GUI_PORT` 是同一条链的两端。
- **窗口与安全**：`new BrowserWindow`（:1083），`contextIsolation: true`（:1092）、`nodeIntegration: false`（:1093）、`devTools: !customerBuild`（:1094，客户包关掉后 F12 与 openDevTools 都是空操作）、**`backgroundThrottling: false`**（:1105；:1095-1104 是真机 id4 实证注释；节流导致停机的机理见 F-055，本条只登记壳侧这个开关）。`closed` 监听必须**紧挨构造点**挂（:1109-1119），留到函数尾部会漏掉早期退出路径。菜单：`Menu.setApplicationMenu(null)`（:1127，条件见 :1126）。外链与新窗口一律拦（:1133 `setWindowOpenHandler`，同时截 `kkdiag://` 自定义协议用于"打开诊断包"）。
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
2. `dist_app/server.dist` 是壳引用的**共享产物目录**；"跳过 Nuitka 复用旧 dist 会把旧前端发出去"这条后果与证据归 F-057，本条不重复展开。
3. 构建脚本的 `for /f` 转义坑见 F-057 踩坑 4。

**状态**: 已完成（main.js / package.json 行号本次逐条读文件实测；未实跑 `npm start`，也未打包验证）


### F-057: driverSoftware2 测试分层、CI 门禁与构建发布（旧前端随 server.dist 走的根因）

**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**关键词**: [pytest, pytest.ini, testpaths, tests/unit, conftest, isolate_disconnect, fake_clock, FW_BIN, 无 marker, 源码扫描门禁, _strip_comments, 剥注释, 人为破坏自证, check_register_descriptions, audit_test_meta, GitLab CI, gitlab-ci.yml, CI_COMMIT_TAG, win-probe, test-gates, build-win-release, build-win-smoke, notify-release, NAS, GIT_CLEAN_FLAGS, build.bat, Nuitka, include-data-dir, include-data-files, INTERNAL_SHA, MAX_UI_LEVEL, SKU, 客户包, release.py, cut_changelog, local-build, requirements 精确 pin, OpenBLAS, vendor wheel, requirements.lock, setup.bat, start.bat, READER_MP, 打包, 旧前端, server.dist, dist_app, 复用dist, CHANGELOG, 未发布, 冒烟, win-smoke]

**需求场景 / 现象**: 在本仓提交前要知道"门禁会跑什么、我这条改动会不会被源码扫描拦、打包会不会把旧前端发出去、发版命令是什么"。**先记结论：前端文件装在 `dist_app/server.dist` 里随服务端走，任何跳过 Nuitka、复用上次 dist 的打包都会把旧前端原样发出去。**

AGENTS.md 讲的是原则，这条记录给**具体文件与行号**。

**方案 / 架构（三张地图）**:

**一 · 测试分层**
- `pytest.ini:9` `testpaths = tests/unit`；:1-7 解释为何钉死（根层脚本的顶层守卫在**收集期**就 `sys.exit` → INTERNALERROR）。`tests/conftest.py:7` `collect_ignore_glob = ["test_*.py"]` 再豁免一次。
- 规模（2026-10-13 实测）：`tests/unit/test_*.py` **244 个文件**，`grep -h '^def test_' tests/unit/test_*.py` 合计 **2236 条**；`tests/` 根 **7 个硬件独立脚本**（`test_mit_run.py`、`test_monitor_lifecycle.py`、`test_ota_selftest.py`、`test_ota_stream.py`、`test_ota_ui_playwright.py`、`test_read_range_stress.py`、`test_register_table.py`，直接 `python` 跑）；`tests/examples/` 客户端调用示例，`tests/fixtures/`、`tests/unit/fixtures/*.json`、`tests/screenshots/`。**没有 integration 目录**。
- 跳过机制：①**无 pytest marker 注册**（pytest.ini 与 conftest 都没有 `markers`）；②根层脚本靠环境变量守卫，如 `tests/test_ota_selftest.py:25-29` 缺 `FW_BIN` 即 `sys.exit(0)`；③`pytest.mark.skipif` 13 处（如 macOS 缺 win_amd64 wheel 时整模块跳过，`.gitlab-ci.yml:205-208` 同口径）。
- 公共 fixture：`tests/conftest.py:48 isolate_disconnect`（:47 是装饰器；隔离黑匣子落盘 + 保存/恢复 server 模块级全局，**8 个文件**共用）、`:120-187 FakeClock`（按模块接管 `monotonic`/`perf_counter`，**不接管 `time.time()`**）。

**二 · 门禁与 CI**
- 源码扫描类门禁：本仓精确含 `_strip_comments` / `_strip_comments_and_docstrings` 的 unit 文件 **7 个**（宽松算上任意 `_strip*` 助手是 73 个），**125 个文件**用 `read_text` 读源码做断言。代表：`tests/unit/test_cmd_status_contract_guard.py:99`（并在 :242 自证扫描器本身）、`test_build_bat_flow.py`、`test_build_script_parity.py:26`、`test_backend_port_binding.py:155`、`test_bench_host_port.py:117`、`test_bus_timeout_window.py:99`、`test_customer_build_gates.py`、`test_macos_ci_gates.py`、`test_release_dev_guard.py`、`test_drain_guard.py:14-17`、`test_reader_mp_ensure_baud.py:83`、`test_fw_profile_mit_scales.py`、`test_od_*.py`（下线检测 **11 个**）。军规 3：匹配前先剥注释，写完**人为破坏一次**确认变红再还原（还原别用 `git checkout --`，实现未 commit 时会连实现一起 revert）。
- 静态对表工具：`tools/check_register_descriptions.py`（寄存器地址与语义描述对表，build.bat Step 0 的硬门，`scripts/build.bat:121-125`）、`tools/audit_test_meta.py`（断言 ↔ GB 条款四张表，判红不 throw）、`tools/gen_fw_profile.py`、`tools/reconcile_registers.py`。
- CI：只有 `.gitlab-ci.yml`。`workflow.rules`（:24-26）**只有 `$CI_COMMIT_TAG` 起流水线**（推分支不触发）；stages test/build/notify（:51-54）。jobs：`win-probe`（tag `win-probe-`，只读探测工具链与 NAS，:101）、`test-gates`（mac 建 venv + `./venv/bin/python -m pytest tests/unit -q -rs`，:192/:208）、`.win_build`（:140：`scripts\ci_win_venv.ps1` → `cmd /c scripts\build.bat --release --customer` → `scripts\ci_win_upload.ps1`）派生 `build-win-release` / `build-win-smoke`、`.mac_build`（:228：`bash scripts/build_mac.sh --release --customer` + smbclient 上传 + 逐文件回读点名 6 个产物）派生 `build-mac-release` / `build-mac-smoke`、`notify-release`（:352，`vX.Y.Z`，needs mac+win）、`notify-smoke-dryrun`（`scripts/ci_notify_lark.py`）。
- 产物落 NAS `\\KingKongNAS\software\02SD\<tag>\`（mac 加 `mac\` 子目录，win 平铺；冒烟进 `_smoke\`），变量 `NAS_IP/NAS_SHARE/NAS_DIR` 见 :29-33；`GIT_CLEAN_FLAGS: '-ffdx -e venv -e electron/node_modules'`（:49）保住缓存；`NAS_USER/NAS_PASS/LARK_WEBHOOK_URL` 是 masked CI 变量，不落文件（:39-42）。GitLab artifacts 只留一份 exe/dmg 副本，`expire_in: 1 week`。
- 冒烟通道：`win-smoke-*` tag 出试装包，**不 bump VERSION**、可先不合 development、不必等本地门禁全绿（本仓项目记忆已记）。

**三 · 构建与发布（F-057，`scripts/build.bat` / `scripts/release.py`）**
- `scripts/build.bat` 顺序：SKU 参数解析 `--internal/--release/--customer/--all`（:43-77）→ 源树完整性守卫①：记 HEAD，`--internal` 拒绝 dirty（:80-107）→ venv Python 优先（:110-117）→ Step 0：寄存器描述门禁 + nuitka 可 import + electron 依赖**指纹**判定（`package-lock.json` 的 SHA256 存进 `electron\node_modules\.package-lock.sha256`，:143-167）→ Step 1：`python -m nuitka server.py` **只编一次，所有 SKU 共用**（:170-201；:183 起强调"Nuitka 退出码 0 不等于数据文件真收进去了"，直接查产物）→ Step 2：按内容"全→少"逐级后处理并 `call :pack`（内部包 :208-213；正式包剔 dev 档案 :215-228；客户包 `:purge_customer` + `:write_level 1/0` + `:gate_customer` 构建后门禁 :231-247 与 :388）→ Step 3：HEAD 复核、`+sha` 重命名、自动打 `internal/v<VER>+<sha>` tag、产物清单（:252-287）。
- **打包数据目录全在 `server.py` 的 nuitka pragma**（:9-107）：`--include-package=core`、`--include-data-dir=frontend=frontend`（:81）、`--include-data-files=tools/force_calib/*.py=…`（:97，:85-96 解释 `--include-data-dir` **收不了 .py** 这个坑）、`docs/skills`（:101）、`firmware_profiles`（:101-105）、`VERSION` 与 `CHANGELOG.md`（:106-107）。**结论（唯一归属本条）：前端是装在 `server.dist` 里随服务端走的，electron 壳只带 4 个壳文件**（壳侧配置见 F-056）→ 任何"跳过 Nuitka 复用上次 dist"的快捷打包都会把旧前端原样发出去。
- 运行时读回：`INTERNAL_SHA`（`server.py:298`，写侧 `build.bat:300`）、`MAX_UI_LEVEL`（`server.py:317-331`，内容非法保守钳到 0，见 :331；写侧 `build.bat:364`）。
- 发布：`python scripts/release.py <版本>` 是唯一 bump 入口 —— ①校验 semver / 工作树干净 / 无 dev 档案 / CHANGELOG `[未发布]` 非空（:128-158）②bump 落盘 `VERSION` + `electron/package.json` + `package-lock.json` 两行手术（:160-171、:65-98）③`cut_changelog` 截断（:45-62）④可选 `--local-build` 做三产物实物核验（:174-204）⑤commit + `git tag -a vX.Y.Z`（:208-213，**不自动 push**）。日常提交禁止手改 `VERSION`。发版前对账三件事见 AGENTS.md 军规 7。
- 依赖与安装：`requirements.txt:7-16` 说明 numpy/scipy **精确 pin**（`numpy==2.5.1`、`scipy==1.18.0`）的原因 —— 标定算法数值输出依赖 numpy 内嵌 OpenBLAS 的构建代际，换代会让标定产物 md5 漂移，升级必须重跑 replay 一致性；`kingkong_calib==1.0.1; sys_platform=="win32"`（:34，mac 不做标定）；pyusb/libusb-package **故意不列为依赖**（:36-49）。`requirements.lock.txt` 全树锁定，`requirements-dev.txt:3-5`（pytest/nuitka 不进生产）。`vendor/` 只有那一个 Cython wheel + `README.md` 的升级 7 步。`setup.bat`：查 `py -3.12` → 建 venv → **先装 vendor wheel 再装 requirements**（:44-55，否则 PyPI 找不到内部包）→ import 自检 + `hid.enumerate()` 原生绑定检查（:70-96）。`start.bat:10` 写 `set READER_MP=0`。

**验证方法**:
- 本地门禁：`cd @CODE_ROOT@\driverSoftware2 && venv\Scripts\python -m pytest tests/unit -q -rs`（**不要显式设 READER_MP=0**，用 CI 默认口径，in-process 形态会让 `test_auto_baud` 两条假红 —— 本仓项目记忆已记）。
- 构建预检：正式包由 Runner 跑完整 `scripts/build.bat`；本地只在显式要求时用 `python scripts/release.py <版本> --local-build`。改 `build.bat` 后至少跑 `pytest tests/unit/test_build_bat_flow.py tests/unit/test_build_script_parity.py`。
- 发布前对账：`git log <上次 tag>..HEAD` 逐条核 CHANGELOG `[未发布]`；`grep -c '<<<<<<<' CHANGELOG.md` 必须为 0。

**踩坑**:
1. 打包版反馈先想 `READER_MP` 双形态（分叉行号、复现方法、环境变量清单归 F-053，此处不重复）。
2. `--include-data-dir` 收不了 `.py`（`server.py:85-96`），必须逐条 `--include-data-files`，新增台架脚本时容易漏。
3. 扫源码的门禁如果不剥注释就会恒绿（注释文本自己满足断言），本仓已踩两次。
4. 分支命名以 `AGENTS.md` 军规 6 词表为准（`feat/` `fix/` `docs/` `chore/` `release/` `hotfix/`）；F-019 里的 `feature/*` 属历史线记载。**发布前置也已换代**：F-019 结论 5「必须先完整构建才 bump」不再适用，现为 `release.py` 可选 `--local-build`、正式包由 GitLab Runner 在 tag 上构建。
5. `cmd /c` 里 `for /f ('…')` 内层的 `=` 与 `>` 必须 `^` 转义（`build.bat:92` 一带），否则 sha 变量取到空值、出现 `ECHO is off.`。

**状态**: 已完成（数字与行号本次实跑/实读；未运行完整构建，未发版）


### F-058: driverSoftware2 下线检测（产线出厂检测）功能全貌与 duoji 口径

**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，分支 feat/offline-detection-optimize，HEAD cf23634，基线 v0.16.0 首发 / v0.16.1 当前 VERSION）
**关键词**: [下线检测, 扭矩去皮零点, 卸力零点, offline detection, 产线出厂检测, OfflineDetectionController, require_step, DetectionType, 外观检测, 尺寸测量, 反驱力, 信息确认, 噪声, 额定扭矩, 坏点, MAX_PLAUSIBLE_NM, 卸力建零, ZERO_MIN_SAMPLES, 出力准备闸, prepareGate, prepare_delay_s, od_motor, od_sensor, od_rated_torque, od_reverse_force, od_profiles, od_relay, DYN-200, JN-DN5, 485 继电器, duoji 口径, 判定在后端, 人工决定, core/offline_detection.py, offline_detection.js, 八步, 存档, 序列号, Downloads]

**需求场景 / 现象**: 下线检测是产线逐台出厂质检功能（v0.16.0 首次上线，本分支正在按产线参考实现 duoji 的口径逐条对齐）。改动时最常见的三类问题：判定口径抄错来源、采集防呆漏一条、状态机门控被绕过。后续接手需要一页看懂模块分工与口径出处。

**方案 / 架构**:
- **流程**：八步 = ①产品序列号（**会话主键**）→ ②外观 ③尺寸 ④反驱力 ⑤信息确认 ⑥噪声 ⑦额定扭矩（六个检测项，前端 `ITEMS` 常量逐个列出，`frontend/js/pages/offline_detection.js:21-28`）→ ⑧汇总存档。报告与配置落 `core/offline_detection.py:82 REPORTS_DIR`（`~/Downloads/下线检测报告`）、:83 `CONFIG_PATH`。**强顺序门控**在后端：`core/offline_detection.py:739 require_step()` —— 前一项没做完不许做下一项；单会话约束 :721；不合格时由操作员决定继续或结束 `decide()` :758；结束 `finish_session()` :793（检测表要求每台都落盘，文件头 :12）。
- **判定一律在后端**（`core/offline_detection.py:11` 明示"前端只负责采集入参与展示，不参与 PASS/FAIL 计算"）；状态枚举 `DetectionStatus` :31（PENDING/RUNNING/PASSED/FAILED/ERROR）、检测项枚举 `DetectionType` :39-45；判定函数 `judge_*` :319-494；结果模型 `DetectionResult` :527；会话模型 `OfflineDetectionSession` :557；控制器 `core/offline_detection.py:717 OfflineDetectionController`。配置读写 `load_config` / `save_config` / `validate_config` / `migrate_legacy_*` :132-295，**阈值/名义值/期望版本全部走 config.json，产线可在界面改**。
- **采集侧模块分工**（口径一律注明"同 duoji"以便回溯来源）：
  - `core/od_motor.py`(64)：出力前使能序列 —— 清故障 → default 模式 → 软复位 → 等 `RESET_BOOT_WAIT_S = 0.8s`（:18，duoji 实测 0.5~0.8s）→ 再 default；`ENABLE_ATTEMPTS = 2`，**复位无应答就整套重走**（commit cf23634 的用例口径）。
  - `core/od_sensor.py`(83)：DYN-200 / JN-DN5 外部扭矩传感器的**只读**适配，绝不启停传感器、绝不动全局去皮（文件头 :5-10）；卸力建零 `:26` = 静置原始读数排序、去两头各 20% 取平均（同 duoji `_auto_tare`）。
  - `core/od_reverse_force.py`(235)：`ReverseForceRunner` :38 分阶段采集，断电手转、正向取最大 / 反向取最小；`MAX_PLAUSIBLE_NM = 200.0`（:27，量程外读数丢弃且**不计入传感器掉线**，即"坏点"）、`ZERO_MIN_SAMPLES = 5`（:28，建零读数不足直接报错）。
  - `core/od_rated_torque.py`(240)：`measure()` :113 堵转工装上给前馈力矩持续 `duration_s`，**实测取外部传感器真值，舵机回读仅备查**（文件头 :1-3）；异常类（过流阈值 `peak_iq_a/limit_a`、过温、故障）在 :38-70，**实际停机判定在采集循环侧**：滤波 Iq 取值 `server.py:10613`、过流/过温/故障归类 `server.py:10649`；同样带 `ZERO_MIN_SAMPLES = 5` :33。
  - `core/od_profiles.py`(228)：判定标准命名方案 —— 多方案存 / 切 / 导 / 删 / 另存（文件头 :1）。
  - `core/od_relay.py`(294)：`OdRelay` :85，485 Modbus 继电器控制工装通断。
  - 注：`core/od_torque_recorder.py` 已删除（本分支实际 `ls` 确认不存在）。
- **后端装配**：`server.py:10148-10736` 是 `/api/offline-detection/*` 全家桶（config/session/开始/下一项/判定/人工决定/导出），装配区 :10092-10343，`from core import od_motor, od_rated_torque, od_sensor` 在 :10317，噪声空载运转 :10525，额定扭矩采集入口 :10590。
- **前端**：`frontend/js/pages/offline_detection.js`(1312 行) `frontend/js/pages/offline_detection.js:58 buildOfflineDetection`，卡片式八步（:83-91）；**出力准备倒计时闸门** `prepareGate()` :789-826（倒计时中可"立即开始"或"取消"，配置项 `rated_torque.prepare_delay_s` 见 :1208）；订单号↔序列号焦点调度 :416、尺寸读数 500ms 自动换格 :529-543；页面级定时器清理 `pageCleanups` / `onPageRebuild` :52-59。API 封装 `frontend/js/api.js:259-287`（`od*` 一族）；档位 `capabilities.js:35 "page:offline-detection": 2`；导航 `index.html:127` 与 :169；注册 `app.js:26` import + :231 builder。
- **门禁**：`tests/unit/test_od_*.py` 共 **11 个**文件（`pytest.ini` 限定 testpaths=tests/unit）。

**口径速查（F-058 下线检测 · 别自己发明）**:
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
3. 页面重建会留下脱离文档的旧 DOM 轮询（机理归 F-055 踩坑 1）；本页的做法是把清理注册进 `onPageRebuild`（:530/:677/:758）。
4. 采样节拍必须**严格晚于 now**（commit 60d0be8：节拍早于 now 导致满速刷帧死循环）。
5. 通讯延迟后**跳过错过的节拍**而不是连续补帧（commit 4dabd5c）。
6. 信息确认不合格才进入人工决定，通信读取失败仍应报错重试，不要伪装成"不合格"（与 F-052 的边界）。
7. 本分支 commit 主题多为"对齐 duoji 口径"，`git log --oneline -30` 计数：`fix(下线检测)` 12、`feat(下线检测)` 9、`test/refactor(下线检测)` 各 1、其它 `fix/feat/docs` 7。

**状态**: 部分完成 —— 结构与口径已核实（行号本次逐条读文件实测）；功能本身仍在开发分支，**未做真机验收**，冒烟通道真实存在：`.gitlab-ci.yml:172-175` 的 `build-win-smoke` 按 `/^win-smoke-/` 触发，本分支已打过 `win-smoke-offline-detection` 与 `win-smoke-offline-detection-fix2`（冒烟包不 bump VERSION，落 `02SD\<tag>\`）。


### F-059: driverSoftware2 文档三层地图、协作上下文与三条自验路径

**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**关键词**: [文档地图, docs/skills, 必读, AGENTS.md, PROJECT-CONTEXT, 缺陷池, 需求池, 飞书多维表格, base token, 待回归, 回填, 真机台账, 读取器 serial, workspace.json, 逻辑名, 不引用项目外路径, onboarding, lark-cli PATH, playwright_ui_self_test, scope_chart_freeze_debug, realmachine_fault_injection, inner_zero_calibration, recal_production_workflow, ANALYZER_HARDWARE_GUIDE, reader_issues, rs485_v3.3, gui-design, theme-servo-cyan, CHANGELOG 体例, 文档引用不实, AGENTS.md, 行号过时, 文档引用失效]

**需求场景 / 现象**: 本仓的"知识"分三层放在仓内（`AGENTS.md` 讲怎么干活、`docs/PROJECT-CONTEXT.md` 讲活从哪来回哪去、`docs/skills/` 讲具体工法），但缺一张能检索的目录：改某个模块前该读哪份、某条缺陷回填哪四个字段、真机台账用什么做主键，每次都要重新翻。另外这些文档之间的交叉引用有失效项，照着走会扑空。

**方案 / 架构（文档三层与分流判据）**:
- `AGENTS.md`（仓根）：硬规定 + 模块→必读 skill 映射表（:170-178）+ 工程军规（:224 起，含分支命名表、发版对账三件事、真机验收必须走可见 GUI）。
- `docs/PROJECT-CONTEXT.md`：协作上下文。§0:8 就给出"新信息该写到哪"的分流判据 —— A 指针 / B 台账 / C 工法 / D 本机配置。
- `docs/skills/`：工法手册，共 **13 份**（见下表）。
- `docs/` 顶层 17 份 md 各管一事：`ONBOARDING.md` 新机接手清单、`PACKAGING.md` Nuitka+Electron 打包、`gui-design.md` 界面设计决策、`theme-servo-cyan.md` 主题令牌（`frontend/css/tokens.css:3` 认它为单一真相源）、`feedback_ledger.md` 反馈分诊台账、`rs485_protocol.md` **已过期**（只是指向 `docs/protocol/` 的迁移指针）、`audience_tiering_proposal.md` 受众分层 L1/L0、`ci_release_migration_proposal.md` 发布迁 CI（已拍板）、`firmware_dev_versioning_coordination.md` 联调固件识别（FB-011）、`macos_support.md`、`ota_cfg_schema_migration_todo.md`、`reader_autonomous_scheduling_todo.md`（未动手）、`ui_test_cases.md` 界面验收资产、`algorithmic-philosophy.md` / `brand-philosophy.md`、`bai_sync_0726_review.md`。
- `docs/` 子目录 8 个：`protocol/`（协议按版本）、`skills/`、`reports/`（实测报告 + `reports/auto/*.json`）、`parking/backlog-2026-08-03.md`（悬项）、`superpowers/{plans,specs}/`（13+12 份历史设计稿，2026-07-05→09-22）、`traj_samples/*.csv`、`archive/server.spec`、`_rendered_test_suite_guide/`。

**docs/skills 13 份与"改什么前必读"（本表属 F-059；核对命令 `ls docs/skills/*.md` 条数 = 13）**:
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
- §4:196 **真机台账**：§4.1:200 台账实体=台架，**主键=读取器 serial**（`docs/PROJECT-CONTEXT.md:213`：`/api/connect`、`/api/state` 返回的 `serial`；总线 id 会漂不可信）；舵机 SN = reg `0x01 kStSerialNumber`（:214，不少设备没烧故读回 None）。§4.2:222 已知台架清单（:224-229，本机可见两条读取器 serial）。§4.3:246 真机操作纪律（白名单 + 写后必复读）。
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
