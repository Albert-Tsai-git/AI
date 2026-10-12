**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**关键词**: [pytest, pytest.ini, testpaths, tests/unit, conftest, isolate_disconnect, fake_clock, FW_BIN, 无 marker, 源码扫描门禁, _strip_comments, 剥注释, 人为破坏自证, check_register_descriptions, audit_test_meta, GitLab CI, gitlab-ci.yml, CI_COMMIT_TAG, win-probe, test-gates, build-win-release, build-win-smoke, notify-release, NAS, GIT_CLEAN_FLAGS, build.bat, Nuitka, include-data-dir, include-data-files, INTERNAL_SHA, MAX_UI_LEVEL, SKU, 客户包, release.py, cut_changelog, local-build, requirements 精确 pin, OpenBLAS, vendor wheel, requirements.lock, setup.bat, start.bat, READER_MP]

**需求场景 / 现象**: 在本仓提交前要知道"门禁会跑什么、我这条改动会不会被源码扫描拦、打包会不会把旧前端发出去、发版命令是什么"。AGENTS.md 讲的是原则，这条记录给**具体文件与行号**。

**方案 / 架构（三张地图）**:

**一 · 测试分层**
- `pytest.ini:9` `testpaths = tests/unit`；:1-7 解释为何钉死（根层脚本的顶层守卫在**收集期**就 `sys.exit` → INTERNALERROR）。`tests/conftest.py:7` `collect_ignore_glob = ["test_*.py"]` 再豁免一次。
- 规模（2026-10-13 实测）：`tests/unit/test_*.py` **244 个文件**，`grep -h '^def test_' tests/unit/test_*.py` 合计 **2236 条**；`tests/` 根 **7 个硬件独立脚本**（`test_mit_run.py`、`test_monitor_lifecycle.py`、`test_ota_selftest.py`、`test_ota_stream.py`、`test_ota_ui_playwright.py`、`test_read_range_stress.py`、`test_register_table.py`，直接 `python` 跑）；`tests/examples/` 客户端调用示例，`tests/fixtures/`、`tests/unit/fixtures/*.json`、`tests/screenshots/`。**没有 integration 目录**。
- 跳过机制：①**无 pytest marker 注册**（pytest.ini 与 conftest 都没有 `markers`）；②根层脚本靠环境变量守卫，如 `tests/test_ota_selftest.py:25-29` 缺 `FW_BIN` 即 `sys.exit(0)`；③`pytest.mark.skipif` 13 处（如 macOS 缺 win_amd64 wheel 时整模块跳过，`.gitlab-ci.yml:205-208` 同口径）。
- 公共 fixture：`tests/conftest.py:47 isolate_disconnect`（隔离黑匣子落盘 + 保存/恢复 server 模块级全局，6 个文件共用）、`:120-187 FakeClock`（按模块接管 `monotonic`/`perf_counter`，**不接管 `time.time()`**）。

**二 · 门禁与 CI**
- 源码扫描类门禁：本仓约 **51 个 unit 文件自带剥注释扫描器**（`_strip_comments` / `_strip_comments_and_docstrings`），124 个文件用 `read_text` 读源码做断言。代表：`tests/unit/test_cmd_status_contract_guard.py:99`（并在 :242 自证扫描器本身）、`test_build_bat_flow.py`、`test_build_script_parity.py:26`、`test_backend_port_binding.py:155`、`test_bench_host_port.py:117`、`test_bus_timeout_window.py:99`、`test_customer_build_gates.py`、`test_macos_ci_gates.py`、`test_release_dev_guard.py`、`test_drain_guard.py:14-17`、`test_reader_mp_ensure_baud.py:83`、`test_fw_profile_mit_scales.py`、`test_od_*.py`（下线检测 **11 个**）。军规 3：匹配前先剥注释，写完**人为破坏一次**确认变红再还原（还原别用 `git checkout --`，实现未 commit 时会连实现一起 revert）。
- 静态对表工具：`tools/check_register_descriptions.py`（寄存器地址与语义描述对表，build.bat Step 0 的硬门，`scripts/build.bat:121-125`）、`tools/audit_test_meta.py`（断言 ↔ GB 条款四张表，判红不 throw）、`tools/gen_fw_profile.py`、`tools/reconcile_registers.py`。
- CI：只有 `.gitlab-ci.yml`。`workflow.rules`（:24-26）**只有 `$CI_COMMIT_TAG` 起流水线**（推分支不触发）；stages test/build/notify（:51-54）。jobs：`win-probe`（tag `win-probe-`，只读探测工具链与 NAS，:101）、`test-gates`（mac 建 venv + `./venv/bin/python -m pytest tests/unit -q -rs`，:192/:208）、`.win_build`（:140：`scripts\ci_win_venv.ps1` → `cmd /c scripts\build.bat --release --customer` → `scripts\ci_win_upload.ps1`）派生 `build-win-release` / `build-win-smoke`、`.mac_build`（:228：`bash scripts/build_mac.sh --release --customer` + smbclient 上传 + 逐文件回读点名 6 个产物）派生 `build-mac-release` / `build-mac-smoke`、`notify-release`（:352，`vX.Y.Z`，needs mac+win）、`notify-smoke-dryrun`（`scripts/ci_notify_lark.py`）。
- 产物落 NAS `\\KingKongNAS\software\02SD\<tag>\`（mac 加 `mac\` 子目录，win 平铺；冒烟进 `_smoke\`），变量 `NAS_IP/NAS_SHARE/NAS_DIR` 见 :29-33；`GIT_CLEAN_FLAGS: '-ffdx -e venv -e electron/node_modules'`（:49）保住缓存；`NAS_USER/NAS_PASS/LARK_WEBHOOK_URL` 是 masked CI 变量，不落文件（:39-42）。GitLab artifacts 只留一份 exe/dmg 副本，`expire_in: 1 week`。
- 冒烟通道：`win-smoke-*` tag 出试装包，**不 bump VERSION**、可先不合 development、不必等本地门禁全绿（本仓项目记忆已记）。

**三 · 构建与发布**
- `scripts/build.bat` 顺序：SKU 参数解析 `--internal/--release/--customer/--all`（:43-77）→ 源树完整性守卫①：记 HEAD，`--internal` 拒绝 dirty（:80-107）→ venv Python 优先（:110-117）→ Step 0：寄存器描述门禁 + nuitka 可 import + electron 依赖**指纹**判定（`package-lock.json` 的 SHA256 存进 `electron\node_modules\.package-lock.sha256`，:143-167）→ Step 1：`python -m nuitka server.py` **只编一次，所有 SKU 共用**（:170-201；:183 起强调"Nuitka 退出码 0 不等于数据文件真收进去了"，直接查产物）→ Step 2：按内容"全→少"逐级后处理并 `call :pack`（内部包 :208-213；正式包剔 dev 档案 :215-228；客户包 `:purge_customer` + `:write_level 1/0` + `:gate_customer` 构建后门禁 :231-247 与 :388）→ Step 3：HEAD 复核、`+sha` 重命名、自动打 `internal/v<VER>+<sha>` tag、产物清单（:252-287）。
- **打包数据目录全在 `server.py` 的 nuitka pragma**（:9-107）：`--include-package=core`、`--include-data-dir=frontend=frontend`（:81）、`--include-data-files=tools/force_calib/*.py=…`（:97，:85-96 解释 `--include-data-dir` **收不了 .py** 这个坑）、`docs/skills`（:101）、`firmware_profiles`（:101-105）、`VERSION` 与 `CHANGELOG.md`（:106-107）。**结论（唯一归属本条）：前端是装在 `server.dist` 里随服务端走的，electron 壳只带 4 个壳文件**（壳侧配置见 F-056）→ 任何"跳过 Nuitka 复用上次 dist"的快捷打包都会把旧前端原样发出去。
- 运行时读回：`INTERNAL_SHA`（`server.py:298`，写侧 `build.bat:300`）、`MAX_UI_LEVEL`（`server.py:317-331`，内容非法保守钳到 0，见 :331；写侧 `build.bat:364`）。
- 发布：`python scripts/release.py <版本>` 是唯一 bump 入口 —— ①校验 semver / 工作树干净 / 无 dev 档案 / CHANGELOG `[未发布]` 非空（:128-158）②bump 落盘 `VERSION` + `electron/package.json` + `package-lock.json` 两行手术（:160-171、:65-98）③`cut_changelog` 截断（:45-62）④可选 `--local-build` 做三产物实物核验（:174-204）⑤commit + `git tag -a vX.Y.Z`（:208-213，**不自动 push**）。日常提交禁止手改 `VERSION`。发版前对账三件事见 AGENTS.md 军规 7。
- 依赖与安装：`requirements.txt:7-16` 说明 numpy/scipy **精确 pin**（`numpy==2.5.1`、`scipy==1.18.0`）的原因 —— 标定算法数值输出依赖 numpy 内嵌 OpenBLAS 的构建代际，换代会让标定产物 md5 漂移，升级必须重跑 replay 一致性；`kingkong_calib==1.0.1; sys_platform=="win32"`（:34，mac 不做标定）；pyusb/libusb-package **故意不列为依赖**（:36-49）。`requirements.lock.txt` 全树锁定，`requirements-dev.txt:3-5`（pytest/nuitka 不进生产）。`vendor/` 只有那一个 Cython wheel + `README.md` 的升级 7 步。`setup.bat`：查 `py -3.12` → 建 venv → **先装 vendor wheel 再装 requirements**（:44-55，否则 PyPI 找不到内部包）→ import 自检 + `hid.enumerate()` 原生绑定检查（:70-96）。`start.bat:10` 写 `set READER_MP=0`。

**验证方法**:
- 本地门禁：`cd D:\code\driverSoftware2 && venv\Scripts\python -m pytest tests/unit -q -rs`（**不要显式设 READER_MP=0**，用 CI 默认口径，in-process 形态会让 `test_auto_baud` 两条假红 —— 本仓项目记忆已记）。
- 构建预检：正式包由 Runner 跑完整 `scripts/build.bat`；本地只在显式要求时用 `python scripts/release.py <版本> --local-build`。改 `build.bat` 后至少跑 `pytest tests/unit/test_build_bat_flow.py tests/unit/test_build_script_parity.py`。
- 发布前对账：`git log <上次 tag>..HEAD` 逐条核 CHANGELOG `[未发布]`；`grep -c '<<<<<<<' CHANGELOG.md` 必须为 0。

**踩坑**:
1. 打包版反馈先想 `READER_MP` 双形态：MP-only 的管道乱序/子进程死/游标竞态在开发环境（in-process）永远复现不了。
2. `--include-data-dir` 收不了 `.py`（`server.py:85-96`），必须逐条 `--include-data-files`，新增台架脚本时容易漏。
3. 扫源码的门禁如果不剥注释就会恒绿（注释文本自己满足断言），本仓已踩两次。
4. `cmd /c` 里 `for /f ('…')` 内层的 `=` 与 `>` 必须 `^` 转义（`build.bat:92` 一带），否则 sha 变量取到空值、出现 `ECHO is off.`。

**状态**: 已完成（数字与行号本次实跑/实读；未运行完整构建，未发版）
