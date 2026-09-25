# 全局功能开发记录 (F)

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

