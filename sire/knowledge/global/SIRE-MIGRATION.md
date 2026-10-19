# SIRE 共享安装与数据迁移契约

**当前规范版本：2.0（Claude 与 Codex 共用）**

本文件替代本目录中的 `SIRE-MIGRATION-legacy-v1.md`。旧文档只用于历史追溯，不得按其中的分离目录方案部署。

## 唯一来源

- 共享 skill：`sire/workflow/shared/sire/`。
- 共享知识：`sire/knowledge/global/`。
- 共享 SQLite：`sire/data/sire_vectors.sqlite3`。
- 共享脚本通过 `scripts/sire_paths.py` 取得这些路径。
- Claude 的 `~/.claude/skills/sire-global-workflow/` 与 Codex 的 `~/.codex/skills/ai-dev-sire-workflow/` 必须是指向同一共享 skill 目录的目录联接；两个入口的 `SKILL.md`、脚本和角色资源解析后必须是同一物理文件。
- Claude 与 Codex 命令都必须读取同一 `DATABASE_PATH` 与 `KNOWLEDGE_DIR`。不要复制另一份 skill、Markdown 知识或数据库。

`SIRE_ROOT`、`SIRE_DATA_DIR`、`SIRE_VECTOR_DB`、`SIRE_KB_DIR`、`SIRE_EMBED_DIR` 和 `SIRE_TASK_ROOTS` 是共享覆盖项。若设置覆盖项，Claude 和 Codex 启动环境必须相同。默认值以当前仓库里的共享目录为准。

## 部署或恢复

1. 将仓库放在两种客户端均可访问的本机路径，并保留 `sire/data/` 与 `sire/knowledge/global/`。
2. 先将已有 Codex/Claude SIRE skill 目录改名保留为备份；不要在未备份前删除旧目录。
3. 分别创建两个目录联接，都指向 `sire/workflow/shared/sire/`。Windows PowerShell 示例：

   ```powershell
   New-Item -ItemType Junction -Path $codexSkillPath -Target $sharedSkillPath
   New-Item -ItemType Junction -Path $claudeSkillPath -Target $sharedSkillPath
   ```

4. 如需兼容原 `sire_global` 路径，只能把它联接到 `sire/knowledge/global/`；不得另建可写副本。
5. 不要把模型权重、数据库 WAL/SHM、加密密钥、个人设置或 `integrity/` 配置快照纳入 Git。需要保留的本机私密资源存放在仓库外。
6. 重启两个客户端进程，使其重新读取安装目录中的共享 skill。

## 知识与数据库写入

- 新增/修改 Markdown：使用共享 `sire_kb.py` 操作 `KNOWLEDGE_DIR`，随后运行 `reindex` 和 `sire_vector_db.py index`。
- 归档 run 台账：将运行记录留存在工作区 `.sire/runs/` 或 `sire/runs/`，随后运行 `sire_vector_db.py migrate`。
- 两端检索都使用同一 SQLite。更新后复核知识 ID、FTS、`integrity_check`、计数和 embedding 文本哈希。
- SIRE 修改共享数据库后，应备份并检查数据库，只提交知识/工作流改动；数据库暂不进 Git，本机路径见 `sire/data/DATABASE-RECORD.md`。
- 数据库备份放到仓库外；不要将 WAL/SHM、私有密钥、模型缓存或整份个人配置写入 Git。
- 修改共享 skill 目录（`sire/workflow/shared/sire/`）前先运行 `sire_rsi.py propose` 登记 RSI 提案；R9 `sire_supervisor.py finalize` / `rsi-check` 会拦截未登记的未提交改动（`rsi_unregistered_change`）。`sire_rsi.py` 写命令同时写机器级归档库（`SIRE_ARCHIVE_ROOT`/`SIRE_ARCHIVE_DB`/`--archive-db`）与仓库库；`snapshot_db.py` 发现仓库库独有的 RSI 记录时拒绝发布。

## Git 快照与轻量 ZIP

2026-10-12 起数据库暂不进 Git（超过 GitHub 100MB 单文件上限），本仓库只保留 `sire/data/DATABASE-RECORD.md` 记录本机路径；Git 历史中最后一份数据库是 69MB 的旧版，不代表最新数据。轻量 ZIP 分发同样不含数据库和历史运行台账。ZIP 内的 skill 也只保存一份 `shared/sire/`，恢复时将 Claude 与 Codex 两个入口同时联接到这份目录。

## 两端验收

部署后从 Codex 和 Claude 分别核对：

1. 两个 skill 入口的真实目标相同，读取同一个 `SKILL.md`。
2. `sire_paths.py` 输出相同的数据库路径和知识目录。
3. 分别运行数据库 `stats` 与共同关键词 `search`，计数和命中 ID 相同。
4. 在一个入口新增知识并索引后，另一个入口可立即检索到该记录；用 `sire_vector_db.py stats` 计数和数据库文件修改时间确认是同一个本机数据库发生了变化（数据库已被 .gitignore 忽略，`git status` 看不到它）。

历史目录命名和旧 ZIP 操作说明见 `SIRE-MIGRATION-legacy-v1.md`，不作为当前安装规范。

## 变更记录

| 日期 | run | 变更 | 验证 |
|---|---|---|---|
| 2026-09-25 | R20260925-052105 | RSI 接入入口（SKILL.md、supervisor.md 检查项 8）与 R9 `rsi-check`/`finalize` 门禁；RSI-20260925-R9GATE → v6.2 | R6A/R6B/R6C 复核、R7 T1–T8 及复测，见 run evidence/U-01 |
| 2026-09-25 | R20260925-SYNC（本会话） | governor 收敛为 `sire/workflow/support/ai-workflow-governor/` 单份（删除 `shared/sire/references/governor/`；Codex 不再安装独立 governor skill）；RSI 双库写入、只读 status、快照 RSI 丢失保护；RSI-20260925-SYNC → v6.3 ACTIVE（78e25b4）| run R20260925-112329：R4/R6A/R6B/R6C/R7 PASS；知识 E-008 |
| 2026-09-25 | 本会话 | global-contract.md 新增“模型分级与省 token 机制”：低难度派 haiku、中难度派 sonnet、高难度留主控，失败逐级升模型 | 规则文本已写入并校验 grep 命中 |
| 2026-09-26 | 本会话 | 模型分级改为：低=haiku，中=Opus 5.5 low 思考，高=Opus 5.5 high 思考；新增子代理 sire-low/sire-mid/sire-high | grep 校验 |
| 2026-10-12 | R20261012-claude-tier-agents-link | sire-low/mid/high 纳入 `shared/sire/agents/claude/`，`~/.claude/agents` 同名文件改为符号链接（原件留 `.legacy-backup-20261012`）；R9 `REQUIRED_AGENT_NAMES` 加 low/mid/high，打包缺失即 `package_omission`；RSI-20261012-TIERAGENTS → v6.5 | R6 sire-mid PASS；R7 T2 打包+verify-zip PASS、T3 删件后 STOP；T1 新进程加载 BLOCKED（CLI 401） |
| 2026-10-12 | R20261012-db-untrack | 数据库 168MB 超 GitHub 100MB 上限推送被拒；用户决定数据库暂不进 Git：未推送提交改写去掉大文件、停止跟踪并 .gitignore、新增 `sire/data/DATABASE-RECORD.md` 记录本机路径；SKILL.md/global-contract/supervisor/vector-knowledge/README 同步改述；RSI-20261012-DBUNTRACK → v6.6 | 待推送范围无 >50MB 对象；文档无残留“数据库进 Git”表述 |
| 2026-10-13 | R20261013-063902 | RSI 五维自审后修 `sire_telemetry.py`：新增 `CATCH_ALL_PHASES=(execute, reply)`，`detect()` 的阶段离群跳过兜底桶与 `mode=unknown` 任务；RSI-20261013-OUTLIER-BASE → v6.12 ACTIVE（config-hash 015b6c4f7b259e7c，为该文件 sha256 前 16 位而非目录 tree hash——门禁不校验，属已知缺口）。自审其余结论（钩子单腿断流、unknown 51%、`TOOL_RETRY` 事实上不触发、`resolve` 不校验提案状态、本表缺 v6.7–v6.11）记入 P-20260931，未改动 | 重放 53 任务 PHASE_OUTLIER 2→0 且 CLOSE_HEAVY=2/FAST_SCOPE=1 不变；R7 T1/T2 在隔离遥测库走真实 analyze+pending 均 PASS；`rsi-check` 由 STOP 转 PASS，pending 清空 |
| 2026-10-13 | R20261013-074759 | Qoder 端完全兼容适配：新增 `scripts/sire_qoder.py`（install/status/verify/uninstall/link/remind/selftest）与 `agents/qoder/README.md`；`sire_telemetry.py` 的 `--client` 加 `qoder`、按 `PostToolUseFailure` 记失败、Stop 无转录路径时按 session 回退查 `~/.qoder-cn/projects`；入口为 junction `~/.qoder-cn/skills/sire-global-workflow` → 唯一源，规则由 remind 实时生成（不留第四份手工副本）；SKILL.md/global-contract.md/self-optimization.md 客户端表述改为 Claude/Codex/Qoder；`sire_supervisor.REQUIRED_ARCHIVE_ENTRIES` 增列 `scripts/sire_qoder.py`、`shared/sire/agents/qoder/README.md`；RSI-20261013-QODERADAPTER → v6.13 | selftest 隔离库真实链路 7 事件/6 阶段/mode=full/失败计数=1 全断言 PASS；junction 即时出现在技能列表；rsi-check PASS、pending 空。钩子真实触发需重启客户端后 `verify` 补测，已登记为待观测项 |
| 2026-10-13 | R20261013-074759（续） | ① 遥测阶段归属收紧：`ledger` 只认台账写入（journal.log/run.json/units.json/kb-hits.md/stage-output 等），`archive` 去掉裸 `knowledge/global`（读知识库改判 `retrieve`），事件 detail 160→320；RSI-20261013-PHASECLASS → v6.14。② Qoder 适配器按实测更正：采集在下一个提示词起生效、无需重启，`verify` 改为以遥测心跳为准（旧字符串匹配日志会假 PASS），入口注入改为 `--with-remind` 可选；`hooks` 事件条目写法保持每事件一条、每 token 加引号 | 重放 62 任务：CLOSE_HEAVY 3→0、FAST_SCOPE 1→0，ledger 1033s→716s、archive 368s→286s，full 任务收尾占比分布仍达 37%（规则未空转）；R7 隔离库真实 hook 链路 5 断言 PASS；`sire_qoder.py selftest` PASS；本端实测 30 条事件 + 1 个回合入库；pending 清空、rsi-check PASS |
| 2026-10-13 | R20261013-081448（续） | RSI 闭环强制化：`sire_run.py finish` 新增 `telemetry_pending_gate`（未处理 pending 即 BLOCKED，`--pending-note` 显式移交并写 `pending-check.json`）；`sire_telemetry.py` 新增 `COLLECTION_DEAD` 规则与 `expected_clients()`/`check_clients()`（从三端配置反推应在采集的 client，`SIRE_CLIENT_CONFIGS` 可覆盖，`analyze --stale-hours` 默认 12 小时，30 分钟去重，只对「采过又哑了」的客户端报警）；`sire_qoder.py` 增加 `entry-file` 生成 `~/.qoder-cn/AGENTS.md` 薄入口（install 自动写、uninstall 只删自己生成的）；SKILL.md、global-contract §RSI 第 3-5 条、self-optimization §5.2、agents/qoder/README 同步；RSI-20261013-RSILOOP → v6.15 | 隔离遥测库 + 临时项目跑真实 CLI：存活自检 4 断言 PASS（claude 36 小时无事件→直接 PROPOSED 并进 pending；qoder 心跳正常不误报；连跑两次 analyze 不重复计数）；收尾门禁三态 PASS（BLOCKED rc=1 → resolve 后 rc=0 → `--pending-note` 移交 verdict=HANDED_OFF）；生产 pending 空、rsi-check PASS |
| 2026-10-13 | R20261013-083512（续） | 遥测回合边界兜底：`summarize_task()` 不再硬依赖 UserPromptSubmit，无 prompt 事件时以窗口内最早事件为起点照样汇总（prompt 字段留空、mode 仍由 Stop 判定）；global-contract §RSI 第 2 条同步口径；RSI-20261013-TURNBOUNDARY → v6.16 | 生产库本端真实事件灌隔离库重放：4 个 Stop 修复前生成 0 个任务、修复后 4 个（含阶段分布与失败计数）；parity rc=0、rsi-check PASS、pending 空 |
| 2026-10-13 | R20261013-084551（续） | 新增 `scripts/sire_close.py close`：一次调用完成 kb add + reindex + 向量索引 + 迁移文档追加 + 批量 stage-output + finish（内部 pending 门禁照常生效）+ 台账复制到 runs/；加入 sire_supervisor 必需清单；SKILL.md 与 global-contract §RSI 第3条写明用法；RSI-20261013-CLOSESCRIPT → v6.17 | 真实自指验证：用该命令完成记录归档的 run，11 条 stage 全 ok、finish PASS、台账已复制；dry-run 与真实输出一致 |
| 2026-10-13 | R20261013-092230 | 三端兼容性只读取证（无机制改动）：三端别名均解析到唯一源；Codex 三事件在采（钩子走别名路径 + config.toml 3 条信任项）；Claude 的 Stop/UserPromptSubmit 被 feishu-hub 占用、对 sire_telemetry 引用为 0；Qoder 四事件在采。入口副本关键词覆盖：源 7/7、Codex AGENTS.md 0/7、Claude reminder 0/7、Qoder memory 4/7 → 副本漂移不可检测被认定为 P0 缺陷，修复方案（sire_entry.py 同源生成 + 三端指纹 check、Claude 链式钩子、显式 sire_clients.json、钩子不指向别名）记入 P-20260935；同时更正：`plugin:computer-use` 已在 Qoder 可用，旧「R10 不支持」记录作废 | 取证脚本 scratch/probe_three_clients.py 输出 three_clients.json；关键词覆盖逐端比对；本 run 走 sire_close 一次收尾（G0/G6 PASS） |
| 2026-10-13 | R20261013-160101 | feishu-hub 侧新增 `executors/qoder/executor.py`+`hook_stop.py` 与 `docs/QODER_ADAPTER.md`、`tests/test_qoder_executor.py`；Hub 注册 `hub/config.py` executors 加 qoder，`hub/service.py` 5 条指令正则与 2 处提示文案扩三端；README 增 Qoder 行。归档 E-016 | 新测试 9/9 OK；test_codex 20 项 0 失败；test_hub 79 项 2 失败经 git stash 对照确认为既有（Claude 执行器 --resume 两条用例）；`executor.py --check` 如实报 CLI_NOT_FOUND；真机端到端 Q8/Q9 标 BLOCKED-无法真实验证 |
| 2026-10-13 | R20261013-160101 | feishu-hub 接入 Qoder 执行器（`executors/qoder/executor.py`+`hook_stop.py`+`docs/QODER_ADAPTER.md`+`tests/test_qoder_executor.py`），Hub 注册与 5 条指令正则、2 处提示扩三端；归档 E-016。另：本 run 收尾时被自家 pending 门禁挡下一次，据此处理 RULE_READ（同一任务规则整读≤1 次的硬规定，SKILL.md R2 后 + 契约输出契约）→ RSI-20261013-RULEREF v6.18 | Qoder 执行器测试 9/9 OK、test_codex 20 项 0 失败、test_hub 2 项红经 stash 对照为既有；`--check` 如实报 CLI_NOT_FOUND，真机端到端标 BLOCKED；resolve 后 pending 空、rsi-check PASS、G0/G6 PASS |
| 2026-10-13 | R20261013-162410 | 安装 Qoder CLI 1.1.66 到 `~/.qoder-cn/bin/qoderclicn/`（官方 manifest + sha256 校验），据此把 feishu-hub Qoder 执行器从「CLI 未装、真机 BLOCKED」推进到真机可用：`find_cli()` 补子目录、`ENV_DROP_PREFIX` 剔 SDK 入口变量、`permission_mode` 改蛇形、新增 `model_by_tier/effort_by_tier`；docs/QODER_ADAPTER.md 加 §5.5 与 Q8a/Q8b/Q8c；测试 11/11。归档 E-017 | headless 实测 is_error=false、result=收到、credits 1.278、15.5s，`--resume` 续接正确；`--check` OK；test_codex 0 失败；Hub→飞书端到端仍待用户启停 |
v6.18 | 2026-10-13 | Qoder 成为 feishu-hub 第三执行者并端到端验收（Q8b/Q9 PASS）；修 outbox 头阻塞（400→DEAD）与卡片本地图片降级；钩子需新会话生效、stdin 强制 UTF-8
| 2026-10-14 | RSI-20261014-LEDGERFIX | 台账迁到机器级固定目录 `D:/sire/sire_ledger/runs/<RUN_ID>/`（`SIRE_LEDGER_ROOT` 可覆盖，`current` 标记同目录）：`sire_paths.py` 新增 `LEDGER_ROOT/ledger_runs_dir()`；`sire_run.py` 的 run_dir/current_run/init 改写固定目录，RUN_ID 追加项目 slug（如 `R20261014-133737-fakeproj`）防跨项目撞名，旧 `.sire/runs` 原位可读不迁移；`sire_close.py` 优先固定目录、回退旧位置，收尾仍复制进 `sire/runs/` 归档；`sire_vector_db.py` run_directories 增扫固定目录；`sire_telemetry.py` ledger 阶段正则改认 `sire_ledger`；knowledge.md/supervisor.md/autonomy.md 与 --help 文案同步 | 冒烟实测：临时目录 init→gate→stage-output→board 全部落 `D:\sire\sire_ledger\runs\R20261014-133737-fakeproj`，项目内不再产生 `.sire`；历史 run R20261013-165929 board/close dry-run 走回退路径正常；五脚本 py_compile 通过。首跑 finish 被自家 G6 挡下（工作流已变更须先同步本表），据此补记本行——门禁按设计工作 |
| 2026-10-14 | RSI-20261014-NOPROJECTLEDGER | 禁止在项目中新建或收尾复制台账；仅使用固定目录。close 透传显式 run，并在 finish 写盘后将最终记录同步工作库和机器级归档库；缺少归档配置时留在本地队列并于下一次 SIRE 触发重试。历史项目重复副本仅在数据库文件清单与文本核验完整且未入库证据已保留后可清理；固定目录原件默认保留。 | 独立两轮复核及真实 CLI 隔离双库验证通过：指定目标与 current 不同、项目无副本、双库最终内容一致、缺配置不修改台账；未删除历史文件 |

| 2026-10-14 | RSI-20261014-ASYNCDB | 任务完成先汇报，数据库索引和工作库/机器级归档改为后台队列；失败保留本地状态与错误，下次 SIRE init 自动重试。新台账只在固定目录，收尾不复制到项目。 | 按用户要求不追加测试或 review；异步实现保留排队及失败记录 |
| 2026-10-14 | RSI-20261014-ASYNCDB 修复 | finish 校验新知识编号时直接解析知识 Markdown（兼容尚未重建的 global_index），不等待索引；修正 parse_records 返回值为 (records, conflicts)。 | 按用户要求不追加测试或 review |

| 2026-10-15 | RSI-20261015-COMMITPUSH | 用户说“提交代码”即授权 commit 本次任务范围改动并 push 当前分支已配置的 upstream；执行前核对分支、upstream 与工作区差异，只纳入本次任务改动；缺少明确 upstream 时停止报告；禁止强推、改写已发布历史或推送其他 ref。 | 规则已在 global-contract 与 SKILL 同步；当前分支 upstream 已确认；本次只新增规则，未执行 commit/push |
2026-10-16 | RSI-20261016-SILENTFLOW / RSI-20261016-CLOSEPATH | Windows 子进程统一隐藏窗口；阶段台账通过 stage-output-batch 一次写入；sire_kb.py --combined 并行合并关键词和向量检索；修正共享 SIRE-MIGRATION.md 回退路径。 | py_compile 通过；本次两组 combined 检索均产出双源回执；RSI 版本 v6.24 与 v6.25 激活
2026-10-16 | EncoderPlotter1 | 新增 IAP 普通校验对程序加密外层内嵌分段AES V2/V3的元数据解析支持，传输与重试摘要仍保留完整分段密文；新增知识 P-20260948 | 指定 DPT 4.2.6 kingkong.bin 实测解析有效；未进行真机升级
2026-10-16 | EncoderPlotter1 | 新增分段固件V2/V3与目标BootLoader版本匹配校验，5CC5 C5 01向量表错误停止重试；关联知识 P-20260949 | 格式矩阵/命令模拟通过，未真机复测
2026-10-16 | EncoderPlotter1 | 修复IAP V3合法短末包被误拒导致DPT30 V4.2.6固件无法解析；仅允许末包短于256字节。 | 指定文件实际预览解析为DPT 4.2.6/V3成功；V2回归及非法短中间包拒绝通过；未真机升级
2026-10-18 | RSI-20261018-comms-bind | sire_comms 按项目把身份绑定到用户指定会话 id，其他会话被拒，双方对话原文展示收发消息，仅用户要求时 rebind | unittest 12 OK；d--code-mes 实测拒绝与发送；v6.28 激活
- 2026-10-19 RSI-20261019-comms-persist（v6.29）：sire_comms session 默认常驻，用户说结束协作才停；--auto-stop 保留5次空闲自停；契约与 SKILL 增加常驻协作规则。
- 2026-10-19 RSI-20261019-comms-wait（v6.30）：sire_comms 新增 session wait 进程内阻塞等待，空闲零额度；契约与 SKILL 增加省额度规则。
