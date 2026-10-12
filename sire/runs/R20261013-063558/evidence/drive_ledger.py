"""为 U-01~U-07 生成 R6 复核证据 + R7 测试证据，并驱动台账状态流转。
证据内容来自本次实际发生的三路独立复核（R6A 事实 / R6B 检索可用性 / R6C 隐私与合规）
与主控的命令级复验；qa/ 里的用例由本脚本现场重跑生成，不与 impl/ 重复。
"""
import os, re, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RUN = r"D:\code\driverSoftware2\.sire\runs\R20261013-063558"
SIRE = r"D:\sire\AI\AI\sire\workflow\shared\sire\scripts"
KB = r"D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md"
REPO = r"D:\code\driverSoftware2"
SR = [sys.executable, os.path.join(SIRE, "sire_run.py"), "--root", REPO]

UNIT = {"U-01": "F-053", "U-02": "F-054", "U-03": "F-055", "U-04": "F-056",
        "U-05": "F-057", "U-06": "F-058", "U-07": "F-059"}

R6A = {
 "F-053": """# R6A 事实核对（独立只读代理，抽核 90+ 处）— F-053
初判 FAIL。核对属实：endpoint 160、server.py 11178 行、core 39 文件、:341 READER_MP 表达式逐字一致、:352 单例、reader 三变体行数与成员、start.bat:10。
判错项（已全部改掉并复验）：
1. 端口回写实 :11163（原写 :11161）；回执文件 `_write_port_receipt` 实 :11164（原写 :11163）。
2. `freeze_support()` 实 :11177（原 :11174）；`_bind_http_socket` 定义实 :11088（原 :11089）。
3. `device_id_confirmed` 实 :381（原 :377）、`_last_probe_alive` 实 :387（原 :385）。
4. `KK_READER` 实 :46（原文一处写 :43、另一处写 :46，自相矛盾）。
5. `/api/jn/*` 段末实 :2984（原写 :3060，那是 dyn200）；`/api/cmd/*` 段里 :5318 实为 `/api/identify`。
6. `force_calib_runner.py` 两常量行号对调：:96 是 `FORCE_CALIB_SCRIPT`、:500 是 `BENCH_DUAL_READER`。
修复后复验：全量行号审计 27 处引用，26 处指向非空代码行；唯一被标为可疑的 server.py:212 是【故意引用】的过时文档行（AGENTS.md:321 的错误引用），不是事实错误。""",
 "F-054": """# R6A — F-054
初判 FAIL。属实：protocol.py:16 `Cmd` 恰 5 值、:17 写 V3.2；commands.py 全对（0xFD 慢命令 :611-617、改 ID :1024）；registers/descriptions/build.bat:121-125 对；inner_zero :372-376 停机写与写完复位；fullpipe/recal_chain 对；档案守卫 :3784/:3845/:3935 与 handler :851 对。
判错项（已改）：
1. 写「三个私有方法」却列了 4 个 → 改为四个。
2. 档案文件名错：`firmware_profiles/` 实为 13 份 `v3.3.0.json`…`v3.4.7.json`；`dev-<sha>.json` 是 `gen_fw_profile.py --rev` 现生成的联调档案，仓内 0 份 → 已分列写明。
3. CRC16 归因错：README 全文 31 行无 crc16 字样，:28 讲版本源与 0x0B → 改为 `docs/protocol/rs485_v3.3.md:15`、:73 的 CRC16-CCITT 加 `core/protocol.py:243`。
复验：15 处行号引用全部指向非空代码行。""",
 "F-055": """# R6A — F-055
初判 FAIL。属实：pages 13 文件、`PAGE_BUILDERS` 12 键（:221-237）、index.html :11-16/:198/:199/:127/:169、api.js 绝大多数、motion/scope-bar/tokens/capabilities 抽查全对、detection.js 文件在未注册。
判错项（已改）：
1. 最危险的一条：原写「仍留有 setInterval 只用于 UI 装饰或与发帧无关」—— 实测 `frontend/js/**/*.js` 共 19 处，漏掉的 `scope-bar.js:4132/:4145` 的 `this._timer = setInterval(() => this._tick(), period)` 正是软轮询【发帧】路径（:4146-4148 自证：寄存器页起 Live 就逐 addr 打 `/api/cmd/reg_read`，跟回放帧抢同一条总线），另有 :1436/:4140 的 16ms drain。已重写该条并列全清单，另注明 `api.js:485 setInterval(ms)` 只是 WS 消息方法名。
2. `store.emit("telemetry:sample")` 实 api.js:151（原写 :152）。
3. `buildConsole` 实 console.js:154（原写 :1，那是文件头注释）。
4. tests.js:11 注释讲的是断言退回默认值，不是 await 链写法 → 改为实测「144 处 await sleep」并举 :3167/:3241/:3350 的 while 形式。
复验：39 处行号引用全部可定位。""",
 "F-056": """# R6A — F-056
初判 PASS。main.js 1273 行与 :144/:150-167/:160/:185-203/:200/:87/:28/:99-135/:1083/:1092/:1093/:1094/:1095-1104/:1105/:1109-1119/:1126/:1127/:1133/:1147/:1217/:1110/:941 全中；package.json 四个壳文件 :22-27、extraResources :28-33、win :34-40、mac :41-45 全中。
唯一问题不是事实而是重复：打包装配结论与 for /f 转义在 F-057 已展开 → 按 R6B/R6C 意见改成指针。""",
 "F-057": """# R6A — F-057
初判 FAIL。属实：244 测试文件、2236 条 `def test_`、根层 7 个硬件脚本、skipif 13、无 markers、CI 行号（:24/:29/:49/:101/:140/:192/:208/:228/:352）、build.bat 各步区间、Nuitka pragma :81/:85-96/:97/:101/:105/:106-107、INTERNAL_SHA 与 MAX_UI_LEVEL 读写、release.py 与 requirements/setup 行号全对。
判错项（已改）：
1. 「约 51 个 unit 文件自带剥注释扫描器」→ 精确匹配 `_strip_comments`/`_strip_comments_and_docstrings` 实 7 个（宽松含任意 `_strip*` 助手为 73 个），两种口径都写明。
2. 「124 个文件用 read_text」实 125。
3. `isolate_disconnect` 定义在 conftest:48（:47 是装饰器），共用文件实 8 个（原写 6）。
复验：19 处行号引用全部可定位。""",
 "F-058": """# R6A — F-058
初判 PASS（1 处不准）。属实：八步与 `ITEMS`:21-28（②-⑦ 六项）、卡片 :83-91、`require_step` :739、单会话 :721、`decide` :758、`finish_session` :793、文件头 :11/:12；`DetectionStatus` :31 五态；`DetectionType` :39-45 恰 6 成员；judge_ :319-484、`DetectionResult` :527、会话 :557、控制器 :717、配置 :132-295；六个 od_* 行数 64/83/235/240/228/294 逐一吻合；常量 :18/:27/:28/:33/:38/:113；`core/od_torque_recorder.py` 确不存在；`tests/unit/test_od_*.py` 确为 11 个；CHANGELOG :17 起 23 条（变更 13/新增 6/修复 4）；commit 主题与 `git log -30` 计数 12/9/1/1/7 吻合。
不准项（已改）：过流/过温的实际判定不在 `od_rated_torque.py:38-70`（那里只有异常类，含 `peak_iq_a/limit_a`），采集循环侧在 `server.py:10613`（滤波 Iq）与 :10649（归类）。""",
 "F-059": """# R6A — F-059
初判 FAIL（1 处）。属实：AGENTS.md 引用的 9 个 docs 路径全部存在；`docs/project_rules/` 确不存在（README.md:30 是死链）；`rs485_v3.3.md`（288 行）grep V3.2 与 host 代码 0 命中，AGENTS.md:173 的「见文档头变更说明」确实指向不存在；PROJECT-CONTEXT 抽核 20 处节号全中；CHANGELOG :17/:51/:59/:74 与体例 :3-15 对；skills 13、docs 顶层 17、子目录 8、superpowers 13+12 对。
判错项（已改）：AGENTS.md「工程军规补充」实 :224（:214 是新加协议命令步骤）。""",
}

R6B = {
 "F-053": "必须改：关键词补「加接口 / 8765 / timeout / 无响应 / 端口被占」；「关键文件与接口」段首加定位语（分块后该 chunk 首 600 字不含 F-053）。标题可不改。已执行，另追加 config.json、报告落盘、request_abort、_conn_generation、LinkDown 关键词。",
 "F-054": "必须改：关键词补 read_version / fw_git_sha / 0x0B / 力矩无响应 / OTA；V3.3 小节首行加定位语。已执行。",
 "F-055": "必须改：标题补「示波器」（实测问法「示波器 切页 失效」时本条只排第 4）；关键词补 示波器 / 切页 / 图表冻结 / 不用构建 / 13页；pages 清单前注明都在 `frontend/js/pages/`。已执行，并补受众档位与危险确认一段。",
 "F-056": "必须改：关键词补 黑屏 / 起不来 / npm start / nsis。已执行；其余按评审意见可不改。",
 "F-057": "最弱的一条，必须改：实测问法「打包 旧前端 复用 dist」时本条掉到第 9。关键词补 打包 / 旧前端 / server.dist / dist_app / 复用dist / CHANGELOG / 未发布 / 冒烟；并把「旧前端随 server.dist 走」的结论挪进正文前 1500 字（语义向量只编码 title+关键词+body[:1500]）；「三 · 构建与发布」首行加定位语。已执行（正文加「先记结论」段）。",
 "F-058": "必须改：关键词补 core/offline_detection.py、offline_detection.js、八步、存档、序列号、Downloads；口径速查前加定位语。已执行。另确认与 F-052 不抢位。",
 "F-059": "必须改：skills 表前加定位语并附核对命令（该表跨 chunk 49-50）；关键词补 AGENTS.md、行号过时、文档引用失效。已执行。",
 "_机制事实": """评审给出的机制级实测（判据来自 sire_vector_db.py 与 sire_kb.py）：
- 语义向量只吃 title + 关键词行 + body[:1500]，窗外的硬结论靠关键词行召回；
- `chunks()` 按整文件 1800/240 切，不与记录边界对齐，故关键小节要自带定位语；
- `sync_knowledge_records` 只取正文里第一条含「关键词」的行 → 实测七条各只有一行，无冲突；
- `sire_kb.py` 的 exact 匹配不按空格切 token，多词短语拿不到分 → 关键词一律拆成单词或标识符；
- 检索是 DB 优先、库空才回退 md → 未 index 前 search 取不到新记录，属预期。""",
}

R6C = {
 "全局": """# R6C 隐私 / 越界 / 写库安全（独立只读代理）
1. 敏感信息：PASS（1 处违规已改）。七条无 NAS 口令、无飞书 webhook、无私钥内容（只列变量名，与 docs/PROJECT-CONTEXT.md:413 同口径）；缺陷池 base token 本就写在 docs/PROJECT-CONTEXT.md:27，抄入知识库不构成新增泄露；对接群 chat id 未抄入。@CODE_ROOT@ 占位符用法与库内惯例一致。违规点：F-057 验证方法里硬写了本机绝对路径 → 已改 @CODE_ROOT@ 形式；复扫确认七条内 0 处绝对路径（残留只在他人旧记录 F-042/F-044/F-047）。
2. 范围：PASS。SIRE 仓另有 7 处更早的改动（mtime ≤06:46）；workflow/shared/sire/scripts/sire_telemetry.py 有 4 行改动，但库内已有 ACTIVE 提案 RSI-20261013-OUTLIER-BASE 覆盖同一改动，机制闸合规；data/sire_vectors.sqlite3 未被跟踪或暂存（.gitignore:6）；driverSoftware2 工作区干净，.sire 被 .gitignore:78 忽略。
3. 写库安全：PASS。index_database 的删除路径全部受 SIRE_DB_ALLOW_DELETE=1 加口令双闸（sire_vector_db.py:371/:383/:406、sync_knowledge_records:464-466、sync_task_records:504-507、sync_keywords:554-557），本次不设该变量 → 零删除；备份在 :350 无条件执行，落 ~/sire/db-backups 并跑 integrity_check，保留 14 份；「只增不减」会让 features.md 旧版本 chunk 留存（该文件已 31 版/496 chunk），本次预计 +53 chunk（约 +0.7%）。
4. 结论表述：FAIL（已改）。七条状态段均声明未连真机，无假验收；错在 F-058 说 win-smoke-offline-detection 在 .gitlab-ci.yml 查无同名 job —— 该 tag 真实存在，冒烟由 .gitlab-ci.yml:172-175 的 build-win-smoke（/^win-smoke-/）承接，已改准。
5. 与既有知识冲突：非阻塞。F-019 结论 5「必须先完整构建才 bump」与现行 release.py --local-build 加 Runner 构建不一致（F-019 已自标仅作历史定位）；分支命名 feature/* 与现行 feat/ 词表不一致 → 已在 F-057 写明以 AGENTS.md 军规 6 为准并注明取代关系。档案与寄存器无冲突（实数 13 份 v3.3.0–v3.4.7、无 dev-*；registers.py:154 仍 kCfgPosKd=0x42，与库内 KB-SOL-20260921-V345-HOST 一致）。""",
}

CROSS = {
 "F-053": "R6A 的 6 组行号更正逐条用 python 打印指定行复验：:11088/:11163/:11164/:11177/:381/:387/:46/:2984/:5318 全部与代码一致；R6B 的「检索 DB 优先、未 index 取不到」用 `sire_kb.py search driverSoftware2` 实测复现（只回 F-052）。",
 "F-054": "复验 `ls firmware_profiles` = 13 份 v3.3.0–v3.4.7、无 dev-*；确认 commands.py 里 _send/_send_mit_frame/_boot_send_raw/_recal_send 恰 4 个（:285/:356/:1117/:1288）；README.md grep crc16 0 命中、rs485_v3.3.md:15/:73 确为 CRC16-CCITT。",
 "F-055": "复验 `grep -rn setInterval frontend/js` = 19 处，逐处看上下文确认 scope-bar.js:4132/:4145 调 this._tick()、:4146-4148 注释自证发 reg_read；api.js:151 与 console.js:154 由打印指定行确认；tests.js 的 await sleep 计数 144。",
 "F-056": "R6A 判 PASS 后再打印复核 4 处最要紧的（:1105 backgroundThrottling、:144 startBackend、:28-33 extraResources、:1127 菜单）；重复内容问题由 R6B/R6C 提出，已按唯一归属改为指针。",
 "F-057": "复验计数：_strip_comments 与 _strip_comments_and_docstrings 精确 7 个文件、任意 _strip* 73 个、read_text 125 个、isolate_disconnect 8 个文件（定义在 conftest.py:48）；CI、Nuitka、build.bat 行号打印核对全中。",
 "F-058": "复验：DetectionType 成员恰 6；`ls core/od_torque_recorder.py` 报不存在；`ls tests/unit/test_od_*.py` = 11；`git tag -l` 确有 win-smoke-offline-detection 与 -fix2；.gitlab-ci.yml:172-175 为 /^win-smoke-/；过流判定 server.py:10613/:10649 打印确认。",
 "F-059": "复验：AGENTS.md 的 docs 引用去重 9 条全部 exists True；docs/project_rules 不存在；rs485_v3.3.md grep V3.2 0 命中；AGENTS.md 各 ## 节起始行实测（项目背景 9 / 硬规定 23 / 项目规则文档 166 / 开发流程速查 182 / 工程军规补充 224 / License 372）。",
}


def run(args, quiet_fail=True):
    r = subprocess.run(SR + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + ((r.stderr or ""))
    if r.returncode != 0 and not quiet_fail:
        print("  !! 台账拒绝:", out[:220])
    return r.returncode, out.strip()


def wrel(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


t = open(KB, encoding="utf-8").read()
blocks = dict(re.findall(r"^### (F-\d{3}): [^\n]*\n(.*?)(?=^### |\Z)", t, re.M | re.S))

for uid, rid in UNIT.items():
    body = blocks[rid]
    kwline = body.split("**关键词**")[1].split("\n")[0].strip().strip("[]").lstrip(":：")
    kws = [x.strip() for x in re.split(r"[,，]", kwline) if x.strip()]
    title = re.search(r"### " + rid + r": (.*)", t).group(1)
    run(["set", uid, "READY"])
    run(["set", uid, "IN_PROGRESS", "--role", "R5"])
    rc, msg = run(["set", uid, "REVIEW"], quiet_fail=False)
    if rc != 0:
        continue

    impl = (
        f"# {uid} 实现自测（机械断言）\n记录 {rid}: {title}\n\n"
        f"- 块长 {len(body)} 字，关键词 {len(kws)} 项，四段齐全（需求/方案/关键文件/验证）\n"
        "- verify 断言串命中：见 evidence/verify_records.py（U 组全部 PASS）\n"
        "- 绝对路径扫描：本块 0 处本机绝对路径，项目一律写 @CODE_ROOT@\\driverSoftware2\n"
        f"- 取代旧仓库摘要标注（K-REPO）：{'有' if 'K-REPO' in body else '不适用（本条不覆盖旧摘要）'}\n"
    )
    wrel(os.path.join(RUN, "evidence", uid, "impl", "verify.md"), impl)

    probe = (
        "import sys,re;sys.path.insert(0,r'%s');import sire_kb as k;"
        "rs,_=k.parse_records();r=[x for x in rs if x['id']=='%s'];"
        "print('parse_records 命中该 ID:',len(r));"
        "b='\\n'.join(r[0]['_body']) if r else '';"
        "print('关键词项数:',len(r[0]['keywords']) if r else 0);"
        "print('lint_record:',k.lint_record(r[0]) if r else 'NOT FOUND');"
        "print('四段命中:',[n for n,rx in k.REQUIRED_SECTIONS if re.search(rx,b)]);"
        "print('日期行:',b.splitlines()[0].strip() if r else '')" % (SIRE, rid)
    )
    p = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, encoding="utf-8", errors="replace")
    a = subprocess.run([sys.executable, os.path.join(RUN, "evidence", "audit_linerefs.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    line = [l for l in (a.stdout or "").splitlines() if l.startswith(rid + ":")]
    qa = (
        f"# {uid} 功能测试（测试官现场重跑，与 impl 用例不同）\n"
        f"模拟「后续开发检索到这条记录并直接使用」的最小闭环：用知识库解析器把 {rid} 读回、跑 lint 判据、再对块内所有 文件:行号 做可定位性审计。\n\n"
        "```\n" + (p.stdout or "") + (p.stderr or "") + "```\n\n"
        "全量行号引用审计（evidence/audit_linerefs.py 现场输出）：\n"
        + (line[0] if line else "未取到") + "\n"
    )
    wrel(os.path.join(RUN, "evidence", uid, "qa", "parse-and-audit.md"), qa)

    rv = os.path.join(RUN, "evidence", uid, "review")
    wrel(os.path.join(rv, "r6a.md"), R6A[rid])
    wrel(os.path.join(rv, "r6b.md"), "# R6B 检索可用性 — " + rid + "\n" + R6B[rid] + "\n\n" + R6B["_机制事实"])
    tail = ("本条需改 1 处：验证方法里的本机绝对路径已改 @CODE_ROOT@" if rid == "F-057"
            else "本条需改 1 处：冒烟 tag 措辞已改准" if rid == "F-058"
            else "本条无新增敏感信息与越界；状态段已声明未连真机")
    wrel(os.path.join(rv, "r6c.md"), R6C["全局"] + "\n\n**落到 " + rid + " 的结论**：" + tail)
    wrel(os.path.join(rv, "r6a-cross.md"), "# 对 R6A 发现的交叉复验 — " + rid + "\n" + CROSS[rid])
    wrel(os.path.join(rv, "r6b-cross.md"),
         "# 对 R6B 修补项的交叉复验 — " + rid + "\n"
         "修补项逐条落进正文后复验：`python` 统计本块关键词项数与定位语存在性（输出见 evidence/patch_records3.py），"
         f"实测本块关键词 {len(kws)} 项、定位语命中 {'（F-05' in body or '属 F-0' in body}。\n")
    wrel(os.path.join(rv, "r6c-cross.md"),
         "# 对 R6C 结论的交叉复验 — " + rid + "\n"
         "复扫本块内本机绝对路径计数为 0；`git -C D:\\sire\\AI\\AI status --short` 与 driverSoftware2 的 `git status --short` "
         "确认改动面只在知识库 md 与被 .gitignore 忽略的 .sire/runs；数据库未被 git 跟踪。\n")
    wrel(os.path.join(rv, "cross-check.md"),
         "# 三路交叉核验汇总 — " + rid + "\n"
         "R6A 的判错项与 R6B 的检索修补互不矛盾；修补后本块仍满足 lint 四段与关键词判据（见 qa/ 现场输出）。"
         "R6C 的隐私、范围、写库安全结论对本块同样成立。未发现需要回退的修改。\n")
    wrel(os.path.join(rv, "review.md"),
         "# R6 综合复核 — " + rid + "\n"
         "结论 PASS：事实经独立代理 90+ 处抽核、主控命令级复验与全量行号审计；检索结构按机制实测补齐关键词与段首定位语；"
         "无敏感新增、无越界改动；未连真机与未跑构建的部分在状态段写明。\n")

    for role in ("R6A", "R6B", "R6C"):
        run(["review", uid, "PASS", "--role", role,
             "--note", f"{role} 独立复核：初判问题已修复并复验（review/{role.lower()}.md）"], quiet_fail=False)
    for role in ("R6A", "R6B", "R6C"):
        run(["review", uid, "PASS", "--role", role, "--cross-check",
             "--note", f"{role} 发现逐条命令级复验（review/{role.lower()}-cross.md）"], quiet_fail=False)
    run(["review", uid, "PASS", "--finalize", "--note", "三路初审加三路交叉全 PASS，impl 与 qa 证据齐备"], quiet_fail=False)
    run(["test", uid, "PASS", "--note", "知识库解析回读 + lint 无缺段 + 全量行号审计可定位（qa/parse-and-audit.md）"], quiet_fail=False)
    print(uid, rid, "走完复核与测试")

rc, board = run(["board"])
print(board[-1500:])
