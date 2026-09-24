# SIRE 工作流迁移与同步契约

> 文档版本：v2.8  
> 状态：当前有效  
> 用途：供其他 AI 工具读取、同步或迁移完整 SIRE 工作流。  
> 规则：每次修改 SIRE 工作流内容后，必须同步更新本文件；未同步不得宣称迁移可用。

## 1. AI 工具执行入口

读取本文件后，按以下顺序执行：

1. 解析源主机和目标主机路径。
2. 读取“规则优先级”和“同步清单”。
3. 检查源文件存在、目标文件冲突和 SHA-256。
4. 按“直接同步”或“ZIP 恢复”模式复制文件。
5. 在目标主机重建向量索引。
6. 执行基础编译、路径检查和 R9 完整性检查。
7. 输出精简迁移结果；详细证据写入目标主机的 `sire_global/integrity/`。

不得猜测缺失路径、凭据、目标应用或规则内容。发现缺失、移动、覆盖、冲突或校验不一致时，立即停止并报告。

## 2. 规则优先级

发生冲突时按以下优先级解释：

1. `~/.codex/skills/ai-dev-sire-workflow/SKILL.md`：SIRE 当前唯一主规范。
2. `~/.codex/skills/ai-dev-sire-workflow/references/`：角色边界、开发覆盖层、监督、向量和门禁细则。
3. `~/.claude/skills/sire-global-workflow/`：台账 CLI、兼容入口和角色契约。
4. `~/.claude/agents/sire-*.md`：角色 Agent 执行契约。
5. `~/.claude/CLAUDE.md`、`~/.claude/sire-reminder.txt`：主机侧入口规则。
6. `~/sire_global/sire_ai_rules.md`、`~/sire_global/sire_multi_role_workflow.md`：全局规则和兼容历史正文；旧内容不得覆盖当前主规范。
7. `~/sire_global/` 中的知识、反馈、运行记录、向量数据库和完整性证据。

如果兼容历史正文与主规范冲突，以主规范为准，并在迁移报告中标记“兼容历史内容”。

## 3. 全量同步清单

源主机上的 `USER_HOME` 代表用户主目录。Windows 默认路径为 `@DRIVE_C@/Users\<用户>`，类 Unix 工具默认路径为 `~`。

| 类别 | 源路径 | 目标路径 | 必须同步 |
|---|---|---|---|
| SIRE 主技能 | `USER_HOME/.codex/skills/ai-dev-sire-workflow/` | `TARGET_HOME/.codex/skills/ai-dev-sire-workflow/` | 是 |
| 通用治理依赖 | `USER_HOME/.codex/skills/ai-workflow-governor/` | `TARGET_HOME/.codex/skills/ai-workflow-governor/` | 是 |
| Claude 兼容入口 | `USER_HOME/.claude/skills/sire-global-workflow/` | `TARGET_HOME/.claude/skills/sire-global-workflow/` | 是 |
| 角色 Agent | `USER_HOME/.claude/agents/sire-*.md`（包含 R0-R10 全套：analyst, decomposer, spec-reviewer, implementer, code-reviewer-a/b/c, qa-tester, integrator, supervisor, system-operator） | `TARGET_HOME/.claude/agents/sire-*.md` | 是 |
| Claude 主规则 | `USER_HOME/.claude/CLAUDE.md` | `TARGET_HOME/.claude/CLAUDE.md` | 是 |
| Claude 提醒规则 | `USER_HOME/.claude/sire-reminder.txt` | `TARGET_HOME/.claude/sire-reminder.txt` | 是 |
| Claude 设置 | `USER_HOME/.claude/settings.json` | `TARGET_HOME/.claude/settings.json` | 按目标主机策略 |
| 全局规则与知识 | `USER_HOME/sire_global/` | `TARGET_HOME/sire_global/` | 是 |
| SIRE 历史产物 | `USER_HOME/Documents/Codex/` 中被 R9 识别的 SIRE 相关目录/文件 | `TARGET_HOME/Documents/Codex/` 对应路径 | 是 |

`sire_global/` 必须包含规则、知识正文、`global_index.json`、反馈记录、运行记录、向量数据库、`integrity/`、导出物和其他历史产物。已有历史 ZIP 不能主动排除。

以下内容属于缓存，不作为业务/历史产物同步：`__pycache__`、`.pyc`、`.git`、`node_modules`。不得用排除缓存的规则排除 Markdown、JSON、JSONL、YAML、TOML、脚本、运行证据或已有 ZIP。

## 4. 公用数据库同步模式

### 4.1 规则与脚本同步

适用于源主机目录仍可读取的情况。

1. 先建立源文件清单和 SHA-256。
2. 目标路径不存在：复制文件。
3. 目标与源 SHA-256 相同：跳过复制并记录 `unchanged`。
4. 目标同路径内容不同：停止，记录 `conflict`，不得静默覆盖。
5. 源路径存在但无法读取：停止，记录 `source_unreadable`。
6. 同一内容出现在不同目标路径：记录 `moved`，等待确认后再决定是否调整路径。
7. 同步完成后重建索引并执行第 7 节检查。

目标主机已有本地修改时，优先保存冲突副本或由用户确认覆盖；不得删除目标文件来“解决冲突”。

数据库 `@SIRE_ROOT@\sire_vectors.sqlite3` 为公用运行数据库，不进入 ZIP，也不通过迁移包覆盖。迁移完成后只对目标机现有数据库执行 `index`、`migrate` 和检索验收。

### 4.3 知识检索 v2 依赖（2026-09-24 起）

- 语义向量模型：`BAAI/bge-small-zh-v1.5`（fastembed/ONNX，512 维，约 91MB），缓存目录 `@SIRE_ROOT@\models`（可用 `SIRE_EMBED_DIR` 覆盖）。迁移时需同步该目录，或在目标机执行 `pip install fastembed` 后设置 `HF_ENDPOINT=https://hf-mirror.com` 首次自动下载。
- 模型或 fastembed 不可用时自动回退旧哈希向量，检索不中断，但准确率下降。
- 新增脚本 `~/.codex/skills/ai-dev-sire-workflow/scripts/sire_knowledge_index.py`（v2 检索与索引后处理），必须与 `sire_vector_db.py` 一起同步。
- 新增数据库对象（只增列/表）：`emb`、`synonyms`、`kfts`/`cfts`（trigram FTS）、`chunks.is_latest`、`knowledge_records.orig_type`、`keywords.weight/status`。
- 评测集：`@SIRE_ROOT@\eval\queries.json` + `run_eval.py`，迁移后执行一次，要求 recall@3 = 1.0。

### 4.2 ZIP 恢复模式

仅在用户明确说出完整短语“打包工作流”后，源主机才允许生成 ZIP。恢复工具必须：

1. 读取 ZIP 根目录的 `MANIFEST.json`。
2. 按清单中的 `archive_path` 恢复，不按文件名猜测位置。
3. 校验每个文件的大小和 SHA-256。
4. 检查 `missing_paths`、`included` 和 `entry_records`。
5. 运行 `sire_supervisor.py verify-zip --against-current`（若目标已有文件）。
6. 恢复后执行向量索引重建和 R9 检查。

未出现“打包工作流”时，禁止生成 ZIP、校验 ZIP 或主动创建迁移包。

## 5. SIRE 必须同步的规则

迁移不能只复制一个 Skill 目录，必须保留以下行为：

- R0–R10 角色边界严格隔离；R9 监督完整性，R10 只执行已确认的原生系统 UNIT。
- R1 每个任务/UNIT 前先执行本地向量检索，并记录 `reuse/adapt/reference-only/avoid/none`。
- R2 形成需求、约束、非目标、风险和可观察验收标准。
- R3 先按前端/后端/数据/验证等方向拆解，再拆成最小可执行 UNIT。
- R4 复核 `REQ → UNIT → evidence`，通过后由 R0 展示完整清单。
- 用户确认前不得执行；只有“不需确认”“自行完成”“直接执行”“按计划执行”等明确授权才可使用 autonomous。
- R5/R10 只能执行自己 owner 对应的 UNIT；执行者不能自评复核或测试通过。
- R6A/R6B/R6C 必须独立复核，R7 独立执行测试，R8 做集成和覆盖验收。
- R9 在任务/Run 开始、每个 UNIT 前后和打包前后检查关联内容；缺失或疑似丢失立即 STOP。
- 用户反对方向或计划时，先确认原因；已给出原因时直接记录，并写入 `sire_feedback.py` 的反馈日志。
- 用户未要求专门测试用例时，R7 只做编译/类型检查、已有 Lint、最小正常路径和必要边界/异常检查。
- 知识归档完成后必须重建 `global_index.json` 和向量数据库索引。
- 所有工作流内容修改后，必须在同一变更链路同步更新本文件、版本和变更记录。

## 6. 精简输出契约

每个阶段/角色都必须有一个可追溯产物。聊天只输出核心内容，详细日志和证据写入 Run 目录。

完成格式：

```text
角色/阶段：状态
产物：
1. [核心产物]
2. [核心产物]
隐患/阻塞：[没有则写 无]
```

跳过格式：

```text
角色/阶段：跳过
原因：[为什么不需要执行]
产物：
1. 跳过记录
```

阻塞格式：

```text
角色/阶段：阻塞
产物：
1. 阻塞记录
原因：[具体缺口或权限问题]
下一步：[解除条件]
```

台账登记命令：

```powershell
python "$env:USERPROFILE\.claude\skills\sire-global-workflow\scripts\sire_run.py" stage-output R1 DONE --artifact "kb-hits.md"
python "$env:USERPROFILE\.claude\skills\sire-global-workflow\scripts\sire_run.py" stage-output R5 SKIPPED --reason "本次无可执行任务"
python "$env:USERPROFILE\.claude\skills\sire-global-workflow\scripts\sire_run.py" stage-output R7 BLOCKED --artifact "阻塞记录" --reason "测试环境不可用"
```

正常收尾前必须为 R0–R10 登记完成、跳过或阻塞产物；无需执行的角色不得静默省略。

阶段产物最低要求：

| 阶段/角色 | 最低产物 |
|---|---|
| R0 | 范围、依赖、状态和确认结果 |
| R1 | KB-Check/向量检索回执 |
| R2 | REQ 清单、约束、风险、验收 |
| R3 | 最小 UNIT 清单、依赖和测试计划 |
| R4 | 拆解复核结论 |
| R5/R10 | 实际变更或系统操作证据；无任务则跳过记录 |
| R6A/R6B/R6C | 各自复核报告 |
| R7 | 测试命令、输入、期望、实际和结果 |
| R8 | 集成/覆盖/回归结论 |
| R9 | 完整性清单和 PASS/STOP 报告 |
| G6 | 新知识编号、索引结果和限制 |

不得在聊天中重复完整命令、过程日志、内部推理、已知规则或无关背景。

## 7. 迁移后验证

目标主机完成同步后，AI 工具必须执行：

```powershell
python "$env:USERPROFILE\.codex\skills\ai-dev-sire-workflow\scripts\sire_vector_db.py" index
python "$env:USERPROFILE\.codex\skills\ai-dev-sire-workflow\scripts\sire_supervisor.py" preflight
python "$env:USERPROFILE\.claude\skills\sire-global-workflow\scripts\sire_run.py" --help
python "$env:USERPROFILE\.claude\skills\sire-global-workflow\scripts\sire_run.py" stage-output --help
python -m py_compile `
  "$env:USERPROFILE\.claude\skills\sire-global-workflow\scripts\sire_run.py" `
  "$env:USERPROFILE\.codex\skills\ai-dev-sire-workflow\scripts\sire_bundle.py" `
  "$env:USERPROFILE\.codex\skills\ai-dev-sire-workflow\scripts\sire_supervisor.py" `
  "$env:USERPROFILE\.codex\skills\ai-dev-sire-workflow\scripts\sire_vector_db.py"
```

验收条件：

- 主 Skill、角色 Agent、兼容入口、全局规则和本文件均存在。
- `sire_vector_db.py index` 成功，且可执行一次 `search`。
- `sire_supervisor.py preflight` 返回 `PASS`；发现 `STOP` 时不得继续。
- `sire_run.py --help` 可用，任务列表确认和 R5/R10 路由仍存在。
- `sire_run.py stage-output` 可登记完成、跳过和阻塞状态；缺少任一 R0–R10 阶段产物时收尾必须被阻止。
- `SIRE-MIGRATION.md` 的版本/变更记录不早于本次工作流内容的最后修改。
- 未生成用户未请求的 ZIP。

验证失败必须输出缺失项、路径、原因分类和下一步；不得用“文件已复制”代替功能验证。

## 8. 工作流变更同步协议

任何修改以下内容的任务，都必须在同一任务中更新本文件：

- 主 Skill、references、角色 Agent、Claude 入口和全局规则；
- `sire_run.py`、`sire_feedback.py`、`sire_vector_db.py`、`sire_supervisor.py`、`sire_bundle.py`、向量索引文件；
- R0–R10 的角色边界、门禁、输出格式、打包范围、向量检索规则和知识索引规则；
- 任务列表确认、阶段产物登记、反馈记录和完整性监督机制；
- 新增或移除的迁移相关文件、工具、历史产物来源、代码复核子角色。

同步动作：

1. 更新第 3、5、6、7 节中受影响的清单或规则。
2. 将文档版本递增，并在下方变更记录写明日期、修改范围和验证结果。
3. 运行 R9 preflight、向量检索和基础检查。
4. `sire_run.py init` 记录工作流控制文件指纹；`finish` 检查工作流变更后的迁移文档哈希和更新时间。
5. R8 只有在本文件同步后才能完成闭环。

## 9. 变更记录

| 版本 | 日期 | 变更 | 验证 |
|---|---|---|---|
| v1.0 | 2026-09-15 | 初始迁移契约；纳入全部规则、角色、知识/向量库、历史产物、精简输出和同步门禁 | U-01 创建后执行 R9/内容校验 |
| v1.1 | 2026-09-15 | 将精简输出契约同步到主规范、角色契约、Claude 入口和全局规则；明确每阶段产物、跳过记录和变更后同步本文件 | U-02 文档交叉检查 |
| v1.2 | 2026-09-15 | 修复 Claude 入口规则编号重复，保持同步规则和基础测试规则连续 | U-02 remediation 检查 |
| v1.3 | 2026-09-15 | 增加 `stage-output` 台账登记和收尾前 R0–R10 阶段产物完整性要求 | U-03 CLI/状态机检查 |
| v1.4 | 2026-09-15 | 增加工作流控制文件指纹和 `finish` 迁移同步检查，阻止未同步的工作流变更收尾 | U-04 代码/规则交叉检查 |
| v1.5 | 2026-09-15 | 向量数据库全量集成（R1 前置向量检索、`sire_vector_db.py` 索引、打包和恢复完整性）；新增代码复核三分家（R6A/B/C）和系统操作员（R10）；任务列表前置确认门禁和反馈记录机制；同步 CLAUDE.md 铁律 9–17 | R1 向量检索回执、R9/R10 角色定义检查 |
| v1.6 | 2026-09-15 | 补全 R9 监督官定义（sire-supervisor.md），明确完整性检查清单、缺失分类、打包前 preflight 流程；更新第 3 节同步清单注记 R0-R10 全套角色 | E-005 工作流同步完成 |
| v1.7 | 2026-09-18 | 增加任务开始提示和角色/阶段即时结构化过程日志；明确跳过、阻塞、失败也必须立即输出，最终报告不得替代过程日志 | 主规范与兼容入口同步检查 |
| v1.8 | 2026-09-18 | 明确最终回复必须重复全部角色/阶段过程日志；同步修正 Claude 角色契约中“过程日志仅写 RUN_DIR”的冲突表述 | 主规范、Claude 角色契约和迁移契约同步检查 |
| v1.9 | 2026-09-18 | 修正 CLAUDE.md 铁律 12 与 sire-reminder.txt 第 17 条中“详细日志仅写 RUN_DIR”与主规范 v1.8 过程日志实时输出规则的冲突；新增铁律 16（过程日志实时输出+任务开始提示+最终回复重复全部日志）、铁律 17（飞书 Webhook 完成通知，条件生效）；核对 references/ 五份细则文件完整、脚本全部可编译、`sire_supervisor.py preflight` 返回 PASS、向量索引重建成功（118 新增/36 未变）并可检索 | 主规范/Claude入口/迁移契约三方交叉检查 + preflight PASS + 向量索引重建验证 |
| v2.0 | 2026-09-21 | 全局强制所有任务使用 SIRE；知识库、任务台账和向量片段统一存储到 `@SIRE_ROOT@\sire_vectors.sqlite3`；任务完成自动 index/migrate；G0 强制普通检索与向量检索双回执；历史重复编号保留；清理历史副本并保留开放 run | Skill/CLAUDE/AGENTS/数据库脚本编译检查 + 数据库统计和语义检索验证 |
| v2.1 | 2026-09-21 | 固化用户定义的完整 SIRE 机制：关键词检索、知识关联、需求拆解、分组并行、独立 Review/验收、三次失败中断、整体关联性 Review、相关优化闭环、知识关键词归档，以及所有角色/阶段执行中与完成/跳过日志不得省略 | AGENTS、主 Skill、输出契约和数据库归档规则一致性检查 |
| v2.2 | 2026-09-21 | 明确完整迁移定义为“ZIP + 包内 MIGRATION-README.md”；ZIP 纳入 Codex AGENTS.md、`@SIRE_ROOT@\sire_vectors.sqlite3`、规则、脚本、知识和任务逻辑；README 提供同步/覆盖/恢复/验收命令 | 打包脚本编译、dry-run 清单和 ZIP 校验 |
| v2.3 | 2026-09-21 | 测试机制升级为真实场景强制验收：R7 先列测试项目；App/网页/桌面程序必须由 R10 实际操作，R7 独立判定；代码分析和纸面推演不得 PASS；缺少工具或环境标记 BLOCKED-无法真实验证；记录正常/异常路径和用户授权 | AGENTS、主 Skill、G4b 门禁、R10 契约一致性检查 |
| v2.5 | 2026-09-22 | 向量库改为**只增不减**（用户令）：`sire_vector_db.py` 未授权删除时，变更文件的新版本 chunk 编号接在该 path 已有最大编号后追加、旧版本保留；变化判断由 `MAX(source_hash)` 改为"当前 hash ∈ 该 path 已有 hash 集合"（防多版本共存后重复追加）；`sync_keywords` 改 upsert、计数只升不降；返回值增 `appended_versions`。`sire_kb.py next-id` 同时取向量库 `knowledge_records` 已占用编号（Markdown 已迁走时只扫 Markdown 会分配已占用编号，经 `INSERT OR REPLACE` 静默覆盖他人记录——本次实际覆盖 P-001~P-003/H-001，已从备份 `sire_vectors-20260922-185135` 原样恢复，新记录改号 P-018~P-020/H-004）。脚本原件备份 `sire_vector_db.py.bak-20260922` | index 连跑两次：首次 inserted>0/removed=0，二次 inserted=0；chunks 235104→235200 单调增；knowledge_records 75→79 且原 4 条逐字段恢复；next-id 返回 F-024/P-021/E-008/H-005 |
| v2.4 | 2026-09-21 | 完整SIRE工作流系统替换：从ZIP包恢复所有规则、脚本、代理、文档；备份原配置至 SIRE-BACKUP-20260921-115802；保留本地向量数据库（@SIRE_ROOT@\sire_vectors.sqlite3，380源、401任务、66知识记录）；路径嵌套问题修复；向量数据库连接验证通过 | ZIP解包→路径纠正→脚本完整性检查→数据库连接测试 PASS |
| v2.6 | 2026-09-24 | 知识检索 v2：`sire_knowledge_index.py` 新增 bge-small-zh 本地语义向量（用户明确同意新增 fastembed 依赖）、trigram FTS（中文/连字符术语）、混合打分（语义+覆盖+BM25+知识优先）、同源去重、结果附「复用要点」；旧版本/派生文件以 `is_latest=0` 隐藏、噪音关键词 `status=noise`、类型归一 F/P/E/H/K（原值存 `orig_type`）、空关键词自动补——全部只打标记不删除；`sire_vector_db.py` 接入 v2（异常回退旧算法）、排除 global_index.json/settings.json/*.bak/导出副本、classify 词边界修复；`sire_kb.py` 以数据库 knowledge_records 为正式来源（md 缺 81 条），新增 `export-md`/`lint`/`add`，模板 `KNOWLEDGE_TEMPLATE.md`；另：P-021 已清理 driver 仓库 234303 片段（用户授权+密码） | 评测 20 条：recall@1 0.35→0.95、recall@3 0.45→1.00、平均 313→76ms，CLI 单次约 0.7s；knowledge 98/task 515 条数不减；R6A 独立复核 |
| v2.7 | 2026-09-24 | 知识库按用户标准「真实经验 + 可直接使用」逐条审阅：31 条无效/重复/过期/非知识记录软删除（`knowledge_records.status='removed'`，v2 检索与 `sire_kb` 均过滤；未走删除密码，故不物理删除），原文+理由归档 `@SIRE_ROOT@\knowledge-archive\removed_20260924.md`；物理删除脚本 `@SIRE_ROOT@\purge_knowledge_20260924.py`（需用户输入删除密码）留待需要时执行；收录标准写入 KNOWLEDGE_TEMPLATE.md | 有效知识 99→68；重建索引后 removed=31 保持；评测 recall@3 仍 1.00；Emy 类查询不再命中已移除记录 |
| v2.8 | 2026-09-24 | 用户本人输入删除密码执行 `@SIRE_ROOT@\purge_knowledge_20260924.py`，物理删除 v2.7 软删除的 31 条知识（knowledge_records/emb/kfts），知识 99→68，任务台账 517、片段 1328 不变，integrity=ok；重建索引后评测 recall@1=0.95、recall@3=1.00、平均 70ms；原文与理由保留在 `@SIRE_ROOT@\knowledge-archive\removed_20260924.md`，删除前备份 `SIRE-DB-Backups\sire_vectors-20260924-085739`。 |

## 10. 旧文档说明

`~/sire_global/sire_sync_guide.md` 是旧版知识同步工具说明，不是本迁移契约。它可以作为历史参考，但不能替代本文件，也不能覆盖当前 SIRE 主规范。
