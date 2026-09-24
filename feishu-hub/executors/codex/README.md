# Codex 执行器

Codex 执行器从中间服务长轮询领取任务，以本机 Codex CLI 执行，并将会话 ID、结果和状态事件送回中间服务。桌面 Stop Hook 只负责上报没有 Hub 任务的独立对话；Hub 仍是唯一连接飞书的一方。

## 启动

先确认 Codex CLI 已安装并完成登录。中间服务启动后，在仓库根目录运行：

```powershell
python .\feishu-hub\executors\codex\executor.py
```

执行器启动时发送 `hello`，随后长轮询 `claim`。默认连接 `http://127.0.0.1:8765`，令牌从 `FEISHU_HUB_TOKEN` 或 `~/.feishu_hub/token` 读取。也可设置 `HUB_URL`/`FEISHU_HUB_URL` 指向其他服务地址；服务端仍需使用协议 v1。

## 配置

可选文件：`~/.feishu_hub/executor_codex.json`。

```json
{
  "codex_exe": "C:\\nvm4w\\nodejs\\node_modules\\@openai\\codex\\node_modules\\@openai\\codex-win32-x64\\vendor\\x86_64-pc-windows-msvc\\bin\\codex.exe",
  "codex_args": [
    "--dangerously-bypass-approvals-and-sandbox",
    "--skip-git-repo-check"
  ],
  "max_parallel": 3,
  "spool_flush_sec": 60
}
```

| 配置项 | 默认值 | 作用 |
|---|---|---|
| `codex_exe` | 优先 npm 包内的原生 `codex.exe`，找不到再使用 PATH 中的 `codex` | Codex CLI 可执行文件；队列分支必须解析为原生 `.exe` |
| `codex_args` | `--dangerously-bypass-approvals-and-sandbox`、`--skip-git-repo-check` | 传给 `codex exec` 和 `exec resume`；`queue` 只传其支持的危险模式开关 |
| `max_parallel` | `3` | 同时处理的任务数；执行器只在有空闲槽位时 claim |
| `spool_flush_sec` | `60` | Hook 离线轮次补发间隔（秒） |

`exec` 与 `exec resume` 的 prompt 通过 stdin 传入。Codex CLI 的 `queue` 子命令只提供 `--message <TEXT>` 输入，没有 stdin 形式，因此桌面队列分支把消息作为参数传给原生 `.exe`，避免 `.cmd` 的 `cmd.exe` 元字符解析和 8191 字符限制。若配置为 `.cmd`，执行器会先查找同一 npm 安装中的原生 `codex.exe`；找不到时拒绝队列投递并报告失败，不会把 prompt 交给 `.cmd`。队列命令不会附加 `--skip-git-repo-check` 这类 exec 专属参数。新会话的 `thread.started.thread_id` 是 Hub 使用的 `session_id`；最终可见回复取自 `--output-last-message` 文件。执行器会按 Claude 执行器相同的规则把 MSIX 虚拟 `%APPDATA%` 目录映射到真实 `Packages/*/LocalCache/Roaming` 路径；两处都不存在才报告 `CWD_MISSING`。

常驻执行器日志写入 `~/.feishu_hub/executor_codex.log`，使用 `pythonw.exe` 启动时也能查看关键状态与错误。

Hub 启动 `codex` 子进程时会设置 `FEISHU_HUB_URL`、`FEISHU_HUB_TASK_ID`、`FEISHU_HUB_LEASE_ID` 和 `FEISHU_HUB_CWD`。Stop Hook 检测到 `FEISHU_HUB_TASK_ID` 会直接退出，避免重复报告。

## 挂载 Stop Hook

在 Codex 的 `~/.codex/hooks.json` 中添加以下 `Stop` 命令。路径需改成实际仓库位置，并按 JSON 规则转义反斜杠：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"D:\\sire\\AI\\AI\\feishu-hub\\executors\\codex\\hook_stop.py\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

保留 `hooks.json` 中已有的其他配置；只在同一 `hooks` 对象下合并 `Stop` 项。保存后在 Codex 桌面端检查并信任该 Hook，再完成一轮普通桌面对话。不要同时为同一轮配置 Stop Hook 和 `config.toml` 的 `notify`，否则可能重复上报。

Hook 从 stdin JSON 读取 `session_id`、`cwd`、`turn_id` 和 `last_assistant_message`，再调用 `/v1/sessions/turns`。没有 `turn_id` 时由 Hub 按协议使用文本哈希去重。Hook 的 HTTP 请求超时为 10 秒，失败时不重试并立即写入公共 spool；执行器启动时立即尝试补发，之后按 `spool_flush_sec` 周期重试。Hook 每个路径都会向 stdout 输出有效 JSON `{}`，不会改变 Codex 的 Stop 决策。

## 测试

从仓库根目录运行：

```powershell
python .\feishu-hub\tests\test_codex_executor.py
python .\feishu-hub\tests\test_hub.py
```

Codex 执行器测试使用临时 HTTP 服务和 `.cmd` 假 CLI，不连接真实飞书，也不启动正式 Hub。

## 已知限制

- 桌面队列回执只代表 CLI 接受了消息，不代表桌面端已开始或完成执行。队列结果取决于目标会话后续运行并触发 Stop Hook；未加载或未唤醒的桌面会话可能保留已接受消息而不自动执行。
- `queue` 请求超时或回执无法确认时只上报一次 `desktop_queue`，`queue_id` 为 `null`。执行器不会自动重投；之后由桌面 Hook 或 Hub 的恢复流程处理。
- `queue` 的 `--message` 仍受 Windows 原生命令行长度上限约束；超长消息无法通过当前 Codex CLI 的队列接口传送。
- Stop Hook 只发送 Codex 提供的最后一条助手回复，不解析 transcript，也不收集工具输出、推理或完整多消息对话。Hook 必须已在桌面端获信任才会运行。
- CLI 登录失效、会话不存在、无最终回复和普通执行错误分别报告为 `AUTH_REQUIRED`、`SESSION_NOT_FOUND`、`NO_RESULT` 和 `EXEC_ERROR`。执行器重启后的未完成租约由 Hub 交给用户恢复，不会自动重跑。
- 使用 `--dangerously-bypass-approvals-and-sandbox` 时，任务按用户选定的无确认模式运行；协议 v1 的 `grants` 仍为空，执行器不额外限制目录外访问。

## 需要中间服务配合

- 收到 `started` 且 `delivery` 为 `desktop_queue` 时，Hub 应立即转为 `WAITING_EXTERNAL` 并使该租约失效；此后执行器停止心跳且不再为该租约上报任何事件。
- Hub 必须接受 `queue_id: null`，并将其解释为“投递结果未知”。不得据此自动再次执行或让执行器重新投递；超时后应按协议转入 `NEEDS_RECOVERY`。
- `/v1/sessions/turns` 应按 Codex `session_id` 将桌面 Hook 轮次匹配给最早的 `WAITING_EXTERNAL` 任务；没有等待任务时按独立桌面轮次处理，并按 `(executor, session_id, turn_id)` 幂等。
- `result` 事件含 `text` 与 `session_id`；新会话还会先单独上报 `session` 事件。Hub 需保留这一会话绑定，并在结果卡回复后把同一个 `session_id` 派回 Codex。
