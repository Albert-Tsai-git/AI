# Codex 执行器实现说明（交给 Codex）

> 依据：[PROTOCOL.md](PROTOCOL.md) v1。中间服务与 Claude 执行器由 Claude 实现；**本文件描述 Codex 需要实现的部分**。
> 分支：`feature/feishu-hub`，代码放在 `feishu-hub/executors/codex/`，**不要修改** `hub/`、`executors/claude/`、`executors/common/`（有需要请提 issue 或在 PR 描述中说明）。

## 1. 边界

- 只和中间服务通信（`HUB_URL`，默认 `http://127.0.0.1:8765`），**不得**直接调用飞书接口，不得读写中间服务数据库。
- 不和 Claude 执行器通信，也不读写它的文件。
- 旧飞书桥 `~/.feishu_bridge` 中的 `hook_codex_notify.py`、`codex queue` 逻辑可作为参考，但切换后不再使用；`~/.codex/config.toml` 的 `notify` 与 `~/.codex/hooks.json` 的 Stop Hook 在切换时改为指向本目录的新 Hook（见 §5）。

## 2. 需要交付的文件

| 文件 | 作用 |
|---|---|
| `executors/codex/executor.py` | 执行器常驻进程：`hello` → 长轮询 `claim` → 执行 → 上报事件 |
| `executors/codex/hook_stop.py` | Codex 桌面 Stop Hook / notify：把独立轮次上报 `/v1/sessions/turns` |
| `executors/codex/README.md` | 启动方式、配置项、已知限制 |
| `tests/test_codex_executor.py` | 用假 `codex` 命令行跑通 §6 的验收用例 |

直接复用 `executors/common/hub_client.py`（`HubClient`、`TaskReporter`、`spool`、`flush_spool`），`executors/mock/mock_executor.py` 是最小参考骨架。

## 3. 执行器行为

1. 启动：`hello`，`capabilities = {"new_session": true, "resume": true, "desktop_queue": true}`。
2. 循环 `claim(wait_sec=poll_wait_sec)`；领到任务后在线程中执行，同时最多 N 个（中间服务已保证同会话、同目录不会并发派发）。
3. 目录：`cwd` 不存在 → `failed{code: CWD_MISSING}`，**不得**换目录。
4. prompt 前面拼上 `resume_hint`（如有），**通过 stdin 传入**。
5. 按 `mode` 选择执行方式：

| mode | 条件 | 做法 | 上报 |
|---|---|---|---|
| `new` | — | `codex exec <codex_args> -`（新会话） | `started{delivery:"process", pid, pid_ctime}` → `session{session_id: thread-id}` → `result{text, session_id}` |
| `resume` | 会话没有被桌面端占用 | `codex exec resume <codex_args> <session_id> -` | 同上 |
| `resume` | 会话被桌面端持有（再开写入者会报 `already has an active writer`） | `codex queue --thread <session_id> --message <prompt> -C <cwd>` | 投递确认后 `started{delivery:"desktop_queue", queue_id}`；**结果由桌面 Hook 回报**（§5），执行器此后不再上报该任务 |

   - 如何判断「被桌面端持有」由 Codex 决定（例如先尝试 `exec resume`，若进程在执行前就报 active writer，则改走 `queue`）。**只要 `exec resume` 已经开始执行，就不得再 queue**，改为上报 `interrupted`。
   - 投递确认超时（不确定是否已入队）：上报 `started{delivery:"desktop_queue", queue_id: null}`，**不得重复投递**。
   - 暂时不想处理时可 `release{code:"SESSION_BUSY", retry_after_sec}`，中间服务会延迟重派，连续 3 次后交给用户。
6. 结果：`text` 为用户可见的最终回复（建议 `codex exec --output-last-message <file>` 或解析 `--json` 事件）；会话 ID 取 `thread-id`。
7. 心跳：每 `heartbeat_sec` 一次（`TaskReporter.start_heartbeat()`）；收到 `LeaseLost` 立即结束子进程树（`taskkill /T /F`）。
8. 超时：`limits.timeout_sec` 到期结束进程树并上报 `interrupted{reason:"执行超时"}`。
9. 执行器自身异常：子进程已启动 → 先结束进程树再上报 `interrupted`；未启动 → `failed`。
10. 失败分类：会话不存在 → `SESSION_NOT_FOUND`；未登录 → `AUTH_REQUIRED`；找不到 CLI → `CLI_NOT_FOUND`；其他 → `EXEC_ERROR`。
11. 子进程环境变量：透传 `FEISHU_HUB_URL`、`FEISHU_HUB_TASK_ID`、`FEISHU_HUB_LEASE_ID`、`FEISHU_HUB_CWD`，使子进程内的 Hook 知道「这是执行器任务」而不重复上报。
12. 用户选择方案 C：`codex_args` 默认 `["--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"]`，`grants` 恒为空，不做目录外限制。

## 4. 配置

`~/.feishu_hub/executor_codex.json`（可选，缺省用默认值）：
```json
{"codex_exe": "C:\\nvm4w\\nodejs\\codex.cmd",
 "codex_args": ["--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check"],
 "max_parallel": 3}
```
令牌从 `~/.feishu_hub/token` 读取（`hub_client.load_token()`）。

## 5. 桌面 Hook（`hook_stop.py`）

- 由 Codex 的原生 Stop Hook（`~/.codex/hooks.json`）或 `config.toml` 的 `notify` 调用，**两者择一**，避免同一轮上报两次（中间服务按 `turn_id` 去重，但仍建议只挂一个）。
- 环境里有 `FEISHU_HUB_TASK_ID`（执行器拉起的子进程）→ 直接退出，结果由执行器上报。
- 否则调用 `/v1/sessions/turns`：`{executor:"codex", session_id: thread-id, cwd, turn_id: Codex 的 turn-id, text: 最后一条助手回复, items: 可选}`。
- 中间服务会自动把这次上报匹配给该会话最早的 `WAITING_EXTERNAL` 任务（即 `desktop_queue` 投递的飞书任务），否则作为独立轮次发完成卡片。
- 中间服务不可达 → `spool("turn", payload)` 落盘；执行器每 60 秒 `flush_spool({"codex": client})` 补发。
- `items`（可见对话条目）只包含用户可见文字（`role`、`phase`、`text`、稳定 `id`），不含推理与工具原文。

## 6. 验收用例（Codex 自测，中间服务提供真实接口）

| 编号 | 场景 | 通过标准 |
|---|---|---|
| CX-1 | `mode=new` 任务 | 新建会话执行；上报 `session` 与 `result`；飞书收到卡片，回复卡片后派发 `mode=resume` 且 `session_id` 一致 |
| CX-2 | `mode=resume`，会话空闲 | `exec resume` 在原会话执行，结果送达 |
| CX-3 | `mode=resume`，桌面端占用会话 | 走 `queue`，任务进入 `WAITING_EXTERNAL`；桌面执行完后 Hook 上报，任务 `DONE`；**只执行一次** |
| CX-4 | `cwd` 不存在 | 上报 `CWD_MISSING`，不执行；飞书收到目录确认提示 |
| CX-5 | 执行中心跳 | 执行超过 `lease_ttl_sec` 仍为 `LEASED`，不被判失联 |
| CX-6 | 执行中结束执行器进程 | 租约过期后任务 `NEEDS_RECOVERY`，不自动重跑；用户回「续跑」后带 `resume_hint` 重派 |
| CX-7 | 收到 `LeaseLost` | 立即结束子进程树 |
| CX-8 | 桌面独立对话 | Stop Hook 上报一次，飞书收到一张卡片；同一 `turn_id` 重复上报不重复发 |
| CX-9 | 执行器子进程内的 Hook | 不上报 `/v1/sessions/turns` |
| CX-10 | 中间服务不可达时的 Hook | 落盘，执行器恢复后补发成功 |

## 7. 联调

```bash
python -m hub.main                                   # 中间服务（切换前请勿与旧飞书桥同时在线）
python executors/codex/executor.py                    # Codex 执行器
python executors/mock/mock_executor.py --executor codex --once   # 或先用参考执行器验证链路
```
