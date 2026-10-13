# Qoder 执行器适配说明（feishu-hub ↔ Qoder）

> 作者：Qoder 侧实现（2026-10-13）。依据 `docs/PROTOCOL.md` v1，与 Claude / Codex 执行器同级。
> 组件：`executors/qoder/executor.py`、`executors/qoder/hook_stop.py`、`tests/test_qoder_executor.py`。

## 1. 位置

```
飞书 ⇄ Hub（唯一连飞书、唯一发飞书、状态唯一来源）
        ⇅ HTTP v1 (127.0.0.1:8765 + ~/.feishu_hub/token)
   Claude 执行器 · Codex 执行器 · Qoder 执行器(本文件) · mock
```

Qoder 执行器只与 Hub 通信，**不直接调用飞书接口**；令牌与其余执行器共用 `~/.feishu_hub/token`。

## 2. 已实现

| 能力 | 实现 |
|---|---|
| 上线与能力声明 | `hello {new_session:true, resume:true, desktop_queue:false}`，`capabilities` 与 Claude 执行器一致 |
| 领任务 / 租约 / 心跳 | `claim` → `started(pid,pid_ctime)` → `heartbeat` → 终态；`LeaseLost` 时 `taskkill /T /F` 结束子进程树后停止上报 |
| 目录 | `cwd` 必须是本机真实存在的目录，否则 `failed CWD_MISSING`（绝不猜目录） |
| 会话 | 结果里的 `session_id` 与任务不同时先报 `session` 事件，供飞书卡片续接；`resume` 模式用 `--resume <session_id>` |
| 结果 | 取 stdout 最后一个 `{"type":"result"}` 行；无结果 `NO_RESULT`；含 login/unauthor/401 → `AUTH_REQUIRED`；含 no conversation found → `SESSION_NOT_FOUND` |
| 超时 | 按任务 `limits.timeout_sec`，超时上报 `interrupted`（不自动重跑） |
| 桌面独立轮次 | `hook_stop.py` 读 Qoder 转录尾部最终回复 → `POST /v1/sessions/turns`；Hub 不可达时 `spool` 落盘，执行器上线后 `flush_spool` 补发 |
| 任务内抑制 | 子进程环境带 `FEISHU_HUB_TASK_ID`，Hook 见到即不重复上报（避免双卡片） |
| 参数模板 | `executor_qoder.json` 里 `args_new` / `args_resume` 可改，默认 `-p --output-format json [--resume S] --permission-mode bypassPermissions` |
| CLI 定位 | `QODER_CLI_BIN` → PATH(`qoderclicn`/`qodercn`) → 已知安装目录；`cfg.qoder_exe` 可显式指定 |

Hub 侧注册：`hub/config.py` 的 `executors` 增加 `qoder`；`hub/service.py` 的指令解析（`STRICT_TASK`、`PROJECT_LIST`、`REPLY_PREFIX`、`COLLAB`、粘连拆分）与两处提示文案同时扩到三端。

## 3. 飞书里怎么用

```
qoder 默认目录 告诉我通讯是否正常
qoder AI项目 检查最近的改动
qoder项目列表
Qoder执行：继续上一条          # 在任务卡片里回复可续接同会话
你分析，Qoder执行              # 协作记录（v1 仍只记录不自动派单）
```

私聊严格格式为 `【qoder 目录 内容】`（【】可省）。不符合格式仍只回格式提示。危险关键词仍需回复「确认」。

## 4. Qoder 桌面 Hook 接线

`~/.qoder-cn/settings.json`：

```json
"Stop": [
  {"hooks": [{"type": "command", "timeout": 20,
    "command": "\"C:\\...\\pythonw.exe\" \"D:\\sire\\AI\\AI\\feishu-hub\\executors\\qoder\\hook_stop.py\""}]}
]
```

注意：Qoder 端每个钩子事件建议**只挂一个条目**（SIRE 遥测钩子已占 `Stop`）。要与 SIRE 共存就把两条命令合成一条链式命令，挂完之后必须用 `python …/sire_qoder.py parity` 复测本端心跳是否仍在增长。Hub 地址通过 `FEISHU_HUB_URL` 传入，未传时用 `~/.feishu_hub` 默认。

## 5. 验收状态

| 编号 | 用例 | 结果 |
|---|---|---|
| Q1 | 三端执行者解析（`qoder 默认目录 …`、`qoder项目列表`、`Qoder执行：`、`你分析，Qoder执行`） | PASS（`tests/test_qoder_executor.py` + `hub/service.py` 直测） |
| Q2 | `build_cmd` 新会话 / 续接（`--resume`）、权限模式参数 | PASS |
| Q3 | 结果解析、`session` 事件与 `result.text` 上报 | PASS |
| Q4 | 错误码映射：`NO_RESULT` / `AUTH_REQUIRED` / `SESSION_NOT_FOUND` / `CLI_NOT_FOUND` | PASS（含 CLI 未装的分支） |
| Q5 | 目录不存在 → `CWD_MISSING` | PASS |
| Q6 | Hook：任务内抑制、缺最终回复判 invalid、Hub 不可达走 spool | PASS |
| Q7 | Hook：按 `session_id` 回退读 Qoder 转录取最终可见回复 | PASS |
| Q8a | 真机 CLI 直连（2026-10-13 16:1x 实测，qoderclicn 1.1.66） | **PASS**：`-p --output-format json --tools "" --permission-mode dont_ask` 单行 result（`is_error:false`、`session_id`、`total_credits:1.28`、15.5s）；`--resume <session_id>` 续接同一会话并正确复述上一轮 |
| Q8b | Hub → 执行器 → 飞书卡片端到端 | **PASS**（2026-10-13 17:01 实测）：飞书 `qoder 默认目录 告诉我通讯是否正常` → `[路由] 新任务 T20261013-170115-a4869c executor=qoder cwd=D:\sire\AI\SESSION` → 计划任务 `FeishuHubQoderExecutor`（pid 34348，instance e876be63）领取 → Qoder CLI 真会话转录 `projects/D--sire-AI-SESSION/31e60db2….jsonl` → 结果卡片 outbox=997 SENT，任务 `DONE`，回复"通讯正常。有什么需要帮助的吗?" |
| Q8c | 执行器 run_task 全流程（假 Hub + stub CLI） | **PASS**（`tests/test_qoder_executor.py` 事件序列 `started → session → result`，11/11） |
| Q9 | 桌面独立轮次上卡片（Hook 直连真实 Hub） | **PASS**（2026-10-13 17:14 实测）：headless 会话一轮 → `hook_qoder.log` `verdict=sent` → outbox=1001 `kind=card executor=qoder task_id=''` SENT。两个真实坑：① 钩子列表在会话 initialize 时快照，`settings.json` 里新加的钩子条目**必须新开会话**才生效；② stdin 必须 `sys.stdin.buffer.read().decode("utf-8", …)`，直接 `sys.stdin.read()` 在 GBK 控制台会解出孤立代理项，`sha256(...encode("utf-8"))` 直接抛异常 |

## 5.5 安装来源与实测要点（2026-10-13）

- CLI 版本 **1.1.66**（与 IDE 内置 SDK 声明一致），官方清单：`https://static.qoder.com.cn/qoder-cli-cn/channels/1.1.66/manifest.json` → `files[]` 按 `os=windows / arch=amd64 / variant!=legacy` 选 `qoderclicn-windows-x64.zip`，**下载后必须校验 sha256**（本机实测 `2010601e43ef…e191b5` 匹配）。
- 安装到 `~/.qoder-cn/bin/qoderclicn/qoderclicn.exe`——这是官方 `entry/qodercn-dispatcher.ps1` 的查找路径，装完 `qoderclicn --version` 即可用；未改 PATH、未改注册表。
- **环境陷阱**：从 IDE/SDK 进程里直接调 CLI 会报 `sdk_invalid_args: Agent SDK entrypoint env is set…`，因为继承了 `QODER_AGENT_SDK_ENTRYPOINT` 等变量，CLI 会强制要求 `--input-format stream-json`。执行器 `build_env()` 已按前缀剔除（`QODER_AGENT_SDK/QODER_SDK_/QODER_WORKER_/QODERCN_CLI/QODERCLI_/QODER_MCP_LAZY/QODER_PRODUCT_ID`）。
- `--permission-mode` 只吃蛇形值（`bypass_permissions`、`dont_ask`…），写 `bypassPermissions` 不合法；`-p` 的输出是**单行 JSON**，`{"type":"result", "result", "session_id", "is_error", "total_credits", …}`，与解析实现一致。
- 登录：`qoderclicn login` 走设备码流并打印 URL；本机因 IDE 已有信任会话，**无需人工点击即自动完成**（输出 `Login successful! Welcome, masquerade-tsai.`）。执行器遇到 `Not logged in — Please run /login` 会映射为 `AUTH_REQUIRED`。
- **推翻旧结论**：headless CLI 有 `-m/--model`、`--reasoning-effort`、`--tools`、`--allowed-tools/--disallowed-tools`、`--config-dir`、`--session-id`、`--fork-session`，所以飞书侧任务**可以按档位派发不同模型/推理强度**（配置 `model_by_tier` / `effort_by_tier`，登录后 `qoderclicn --list-models` 取值）；只有交互式 Agent 工具仍无 model 参数。

## 6. 上线步骤（需要用户执行）

1. 安装 Qoder CLI（`qoderclicn`），或设置 `QODER_CLI_BIN=<路径>`；`python executors/qoder/executor.py --check` 应输出 `"cli": "…"`。
2. 参数模板**已真机校对**（见 §5.5 与 Q8a），无需再猜；如要按档位选模型，登录后 `qoderclicn --list-models`，把值填进 `~/.feishu_hub/executor_qoder.json` 的 `model_by_tier` / `effort_by_tier`。
3. 按 `docs/CUTOVER.md` 停旧飞书桥、启 Hub（`python -m hub.main`），再启 `python executors/qoder/executor.py`。
4. 飞书发 `qoder 默认目录 告诉我通讯是否正常` 验证 Q8；桌面挂 §4 的 Stop 钩子后用 `parity` 复测 SIRE 心跳未断，再验证 Q9。

## 7. 已知限制

- Qoder CLI 未安装 → 执行器可以上线但每个任务都会以 `CLI_NOT_FOUND` 失败；不影响 Claude / Codex 执行器。
- 交互式 Agent 工具无 model 参数（SIRE 分档仍记 `qoder-role:<tier>`）；headless CLI 可以按 `-m/--reasoning-effort` 分档派发，需登录并用 `--list-models` 取值后才启用。
- `desktop_queue` 能力为 false：Qoder 没有 Codex 那种"把消息排进正在使用的桌面会话"的通道，桌面续接走 §4 的 Hook 上报路径。
- 参数模板、`--check` 之外的真实行为（会话续接、错误文案）均未在真机验证，属 §6 第 2 步的前置检查项。
