**日期**: 2026-10-13
**项目**: feishu-hub Qoder 执行器（`D:\sire\AI\AI\feishu-hub`）
**状态**: 单元级已验证；真机端到端 BLOCKED-无法真实验证（Qoder CLI 未安装、启动 Hub 会与旧飞书桥抢长连接）
**关键词**: feishu-hub, 飞书中转, 执行器协议 v1, Qoder 执行器, qoderclicn, QODER_CLI_BIN, hook_stop, sessions/turns, spool, FEISHU_HUB_TASK_ID, executors 白名单, STRICT_TASK, CUTOVER, parity 复测

**场景**: 让飞书既能给 Qoder 派任务，也能把 Qoder 桌面上的独立回复同步成卡片并可续接；与既有 Claude / Codex 执行器同级接入。

**做法**:
1. `executors/qoder/executor.py`：按 PROTOCOL v1 上线（`new_session/resume`，`desktop_queue:false`）、`claim` 长轮询、`started(pid,pid_ctime)`、心跳、终态事件；`LeaseLost` 时 `taskkill /T /F` 杀进程树后立刻停止上报；**子进程已启动过就不能 release，只能 interrupted**。目录必须真实存在否则 `CWD_MISSING`（绝不猜目录）。
2. CLI 定位顺序：`QODER_CLI_BIN` → PATH(`qoderclicn`/`qodercn`) → 已知安装目录；找不到时任务报 `CLI_NOT_FOUND`，不影响其它执行器。参数模板可配置（`args_new`/`args_resume`），默认 `-p --output-format json [--resume S] --permission-mode bypassPermissions`——**这是按 Qoder 与 Claude Code 同源推断的，未真机验证**。
3. 结果解析：stdout 取最后一个 `{"type":"result"}`；`is_error` 或错误文案映射为 `AUTH_REQUIRED`(login/unauthor/401)、`SESSION_NOT_FOUND`(no conversation found)、`NO_RESULT`；session 变化先报 `session` 事件，飞书卡片才能续接。
4. 子进程环境注入 `FEISHU_HUB_TASK_ID/LEASE_ID/CWD/URL`，桌面 Hook 见到任务号就抑制，避免双卡片；独立轮次由 `hook_stop.py` 读 Qoder 转录尾部最终可见回复 → `POST /v1/sessions/turns`，Hub 不可达时 `spool` 落盘、执行器上线 `flush_spool` 补发。
5. Hub 侧接入点只有两处：`hub/config.py` 的 `executors` 白名单，以及 `hub/service.py` 里 5 条指令正则 + 2 处提示文案（`STRICT_TASK`、`PROJECT_LIST`、回复前缀、粘连拆分、协作句）；运行期 `~/.feishu_hub/config.json` 若显式写了 `executors` 会覆盖默认值，要先确认。
6. Qoder 桌面钩子与 SIRE 遥测钩子共用 `Stop` 事件：Qoder 侧每个事件保持**单条目**（多条目曾出现停采），需要共存时改成一条链式命令，装完立刻 `sire_qoder.py parity` 复测心跳是否仍在增长。

**关键文件与接口**:
- `feishu-hub/executors/qoder/executor.py`（`--check` 只探测 CLI 与配置，不领任务）
- `feishu-hub/executors/qoder/hook_stop.py`（`build_turn` / `handle_payload`）
- `feishu-hub/hub/config.py:50`、`hub/service.py:21,22,206,207,246,251,382,429`
- `feishu-hub/docs/QODER_ADAPTER.md`（用法、接线、验收表 Q1–Q9、上线四步）
- `feishu-hub/tests/test_qoder_executor.py`（假 HubClient/FakeReporter，不联网）

**验证方法**: `python tests/test_qoder_executor.py` → 9 项全 OK（三端指令解析、new/resume 命令构造、result 与 session 上报、四种错误码、CWD_MISSING、Hook 抑制/invalid/spool、转录回退读取）。回归：`tests/test_codex_executor.py` 20 项 0 失败；`tests/test_hub.py` 79 项 2 失败，且把本次 `hub/service.py` 改动 `git stash` 后**同样 2 项失败** → 属既有问题（Claude 执行器的 `--resume` + prompt 走 stdin、重复卡片两条用例），不是接入 Qoder 引入。`executor.py --check` 如实报 `CLI_NOT_FOUND`。

**踩坑**: ① 用 `git stash push <file>` + 跑测试 + `git stash pop` 是判定"红是既有还是我引入"的最低成本办法；② 中文正则锚点做批量替换时，`Claude」或「Codex」` 这类整句提示词也在断言里，扩三端要同时改文案与测试期望；③ 测试脚本别真去构造 `HubClient`——它会 `_bootstrap()` 写 `~/.feishu_hub/token`，用假客户端注入即可。

**限制**: 未做真机端到端（Q8/Q9 BLOCKED）：需要装 Qoder CLI 并按 `docs/CUTOVER.md` 停旧飞书桥再启 Hub；CLI 的参数与结果字段形态、错误文案都是推断，装好后按 `docs/QODER_ADAPTER.md` §6 第 2 步先校对。Qoder 侧也不能按任务指定模型档位。
