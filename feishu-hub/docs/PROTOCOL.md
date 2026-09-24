# 飞书多 AI 中转 —— 执行器协议 v1

> 状态：草案 v1（2026-09-24）　依据：《飞书多 AI 中转与任务协作方案》
> 读者：中间服务（Hub）实现者、各 AI 执行器实现者（Claude 执行器由 Claude 实现，Codex 执行器由 Codex 实现）

## 0. 原则

1. **Hub 是唯一权威**：只有 Hub 连接飞书、发送飞书消息、维护任务状态。执行器和桌面 Hook **不得**直接调用飞书接口。
2. **执行器彼此独立**：执行器只和 Hub 通信，不互相调用；没有用户明确的协作指令，Hub 不会把一个执行器的任务转给另一个。
3. **执行器主动连接 Hub**：Hub 不主动访问执行器所在机器。现在 Hub 在本机，以后迁到服务器只需改 `HUB_URL`。
4. **至少一次投递 + 幂等**：所有写接口可安全重试；重复请求返回与首次相同的结果。
5. **状态不明就停**：不确定是否已经执行时，交给用户确认，绝不自动重跑。

## 1. 连接与鉴权

| 项 | 值 |
|---|---|
| 地址 | `HUB_URL`，默认 `http://127.0.0.1:8765` |
| 鉴权 | 请求头 `Authorization: Bearer <token>`；令牌存放在 `~/.feishu_hub/token`（或环境变量 `FEISHU_HUB_TOKEN`），首次启动 Hub 时生成 |
| 格式 | 请求和响应都是 `application/json; charset=utf-8` |
| 版本 | 所有请求体带 `"protocol": 1`；双方忽略不认识的字段 |
| 时间 | Unix 秒（浮点） |

通用错误响应：`{"ok": false, "error": {"code": "LEASE_LOST", "message": "..."}}`，HTTP 状态码见 §7。

## 2. 名词

| 名词 | 含义 |
|---|---|
| `executor` | 执行器类型：`claude`、`codex`，以后扩展 |
| `instance_id` | 执行器实例 ID（每次启动随机生成的 UUID），用于区分重启 |
| `task` | Hub 的任务，`task_id` 由 Hub 生成（`T` + 时间 + 随机），全局唯一 |
| `conversation_id` | Hub 的对话 ID：同一条飞书回复链上的任务共享 |
| `session_id` | **执行器自己的会话 ID**（Claude 的 session_id、Codex 的 thread-id）；新会话由执行器在执行时上报 |
| `lease` | Hub 发给执行器的执行租约，`lease_id` + 到期时间；只有持有有效租约的执行器才能上报该任务的事件 |
| `cwd` | 用户已确认的工作目录（按用户看到的原样传递，执行器负责映射到本机真实路径） |

## 3. 接口一览

| 方法 | 路径 | 调用方 | 作用 |
|---|---|---|---|
| POST | `/v1/executors/hello` | 执行器 | 上线、声明能力，获取时间参数 |
| POST | `/v1/tasks/claim` | 执行器 | 长轮询领任务，领到即获得租约 |
| POST | `/v1/tasks/{task_id}/events` | 执行器、执行器拉起的子进程 Hook | 上报事件（开始、会话、心跳、过程、结果、失败、中断） |
| POST | `/v1/tasks/{task_id}/release` | 执行器 | 未执行就归还任务（如会话被桌面占用） |
| POST | `/v1/sessions/turns` | 桌面 Hook | 上报**没有 Hub 任务**的独立对话轮次（桌面上直接用 AI） |
| GET | `/v1/sessions/{executor}/{session_id}/inbox` | 桌面 Hook | 取该会话尚未同步到桌面的飞书往返 |
| POST | `/v1/sessions/{executor}/{session_id}/inbox/ack` | 桌面 Hook | 确认已同步 |
| GET | `/v1/health` | 任意 | 健康检查 |

### 3.1 `POST /v1/executors/hello`

请求：
```json
{"protocol": 1, "executor": "codex", "instance_id": "8c1e…", "version": "0.1.0",
 "capabilities": {"new_session": true, "resume": true, "desktop_queue": true}}
```
响应：
```json
{"ok": true, "lease_ttl_sec": 90, "heartbeat_sec": 30, "poll_wait_sec": 25, "server_time": 1790000000.0}
```
- `capabilities.new_session`：能新建会话（私聊新任务需要）。
- `capabilities.resume`：能在已有会话上续跑。
- `capabilities.desktop_queue`：能把消息排进桌面端正在使用的会话（Codex 的 `codex queue`），此时结果由桌面 Hook 回报（见 §5.3）。
- 执行器每次启动都要调用；Hub 把最近 `2 × heartbeat_sec` 内有请求的执行器视为在线。

### 3.2 `POST /v1/tasks/claim`（长轮询）

请求：`{"protocol": 1, "executor": "claude", "instance_id": "…", "wait_sec": 25}`

- 有任务：`200`，返回任务信封（§4）。
- 等到 `wait_sec` 仍没有：`204`，执行器立即再次调用。

Hub 保证：
- 只把 `executor` 相同的任务派给该执行器。
- 同一个 `(executor, session_id)` 或同一个 `cwd` 同一时刻最多一个有效租约（会话互斥、目录单写）。

### 3.3 `POST /v1/tasks/{task_id}/events`

请求：
```json
{"protocol": 1, "lease_id": "L…", "seq": 3, "type": "heartbeat", "data": {}}
```
- `seq`：该租约内从 1 开始递增。`(task_id, lease_id, seq)` 相同的重复请求直接返回首次结果（幂等）。
- 成功：`{"ok": true, "lease_expires": 1790000090.0}`，**每个事件都会续约**。
- 租约失效（过期、被取消、被用户放弃）：`409 LEASE_LOST`。执行器**必须立即停止**该任务（结束子进程），不再上报。

事件类型：

| type | data | 含义 | 终态 |
|---|---|---|---|
| `started` | `{"pid": 1234, "pid_ctime": 1339…, "delivery": "process"}` 或 `{"delivery": "desktop_queue", "queue_id": "…"}` | 已开始执行（或已排入桌面会话） | 否 |
| `session` | `{"session_id": "…"}` | 绑定或更新执行器会话 ID；**新会话必须上报** | 否 |
| `heartbeat` | `{}` | 仍在执行，至少每 `heartbeat_sec` 一次 | 否 |
| `progress` | `{"text": "…"}` | 用户可见的过程消息（可选，Hub 可合并后转发） | 否 |
| `result` | `{"text": "…markdown…", "items": [ … ]}` | 最终结果。`text` 为用户可见的最终回复；`items` 可选，是本轮可见对话条目（§6） | **是** |
| `failed` | `{"code": "CWD_MISSING", "message": "…", "retryable": false}` | 执行失败（错误码见 §7.2） | **是** |
| `interrupted` | `{"reason": "…"}` | 执行被中断，状态不明 | **是** |

规则：
- 终态事件之后，租约立即作废。
- `result` 最大 256 KB，超出由执行器截断并在末尾注明；Hub 负责拆成多张飞书卡片。
- **不得**上报私有推理、密钥、令牌或原始内部日志。

### 3.4 `POST /v1/tasks/{task_id}/release`

请求：`{"protocol": 1, "lease_id": "L…", "code": "SESSION_BUSY", "retry_after_sec": 15}`

用于「领到了，但确定没有执行」的情况，例如会话正被桌面端占用。Hub 把任务放回队列并延迟重试；连续 3 次仍 `SESSION_BUSY`，Hub 暂停任务并询问用户。**只要子进程已经启动过，就不能 release，必须上报 `interrupted`。**

### 3.5 `POST /v1/sessions/turns`（桌面 Hook 上报独立对话）

用户直接在桌面端使用 AI（没有 Hub 任务）时，桌面 Hook 在每轮结束后上报：
```json
{"protocol": 1, "executor": "codex", "session_id": "01a0…", "cwd": "D:\\code\\A",
 "turn_id": "01a0…-turn-7", "text": "最终回复 markdown", "items": [ … ]}
```
- `(executor, session_id, turn_id)` 幂等；`turn_id` 缺失时用 `text` 的 SHA-256 代替。
- Hub 发一张完成卡片到飞书，并记录「卡片 → (executor, session_id, cwd)」，之后用户回复这张卡片即可续跑。
- **匹配等待中的任务**：如果该会话有状态为 `WAITING_EXTERNAL` 的任务（执行器用 `desktop_queue` 方式投递的），Hub 把这次上报视为**最早那条**等待任务的 `result`（§5.3）。

### 3.6 桌面同步（inbox）

- `GET /v1/sessions/{executor}/{session_id}/inbox` → `{"ok": true, "turns": [{"turn_ref": "…", "created": …, "prompt": "飞书里说的", "reply": "AI 回复原文"}]}`
- `POST …/inbox/ack`，请求体 `{"protocol": 1, "turn_refs": ["…"]}`

Claude 的 UserPromptSubmit Hook 用它把飞书里的往返补进桌面上下文。Codex 如果有等价 Hook，可以用同样的方式实现，没有也可以不接。

## 4. 任务信封（claim 返回）

```json
{
  "ok": true,
  "task": {
    "task_id": "T20260924-093012-a1b2",
    "conversation_id": "C20260924-0912-77aa",
    "executor": "codex",
    "mode": "resume",
    "session_id": "01a0d114-…",
    "cwd": "D:\\code\\A",
    "prompt": "用户在飞书里的指令原文",
    "attempt": 1,
    "resume_hint": null,
    "lease_id": "L7f3…",
    "lease_expires": 1790000090.0,
    "limits": {"timeout_sec": 1800},
    "grants": []
  }
}
```

| 字段 | 说明 |
|---|---|
| `mode` | `new`：新建会话，`session_id` 为空；`resume`：在 `session_id` 上续跑 |
| `attempt` | 第几次执行；大于 1 表示用户确认过的「续跑」 |
| `resume_hint` | 续跑时 Hub 给出的提示，例如「上一次执行被中断，请先检查已有改动」。执行器应把它放在 prompt 前面 |
| `limits.timeout_sec` | 执行上限；超时后执行器自行结束进程并上报 `interrupted` |
| `grants` | 目录外授权记录（方案 §4）。v1 固定为空数组：用户选择 C，暂不实施，执行器**不做**额外限制 |

## 5. 执行器职责

### 5.1 标准流程（子进程方式）

```
hello → claim(长轮询) → 校验 cwd → 启动 CLI → started → [session] → heartbeat… → result | failed | interrupted
```

1. **校验目录**：`cwd` 不存在（Claude 执行器会先做 MSIX 虚拟路径映射）时，上报 `failed{code: CWD_MISSING}`，**绝不**换目录执行。Hub 会向用户重新确认目录。
2. **启动**：`mode=new` 时新建会话；`mode=resume` 时续跑 `session_id`。prompt 通过 stdin 传入，防止以 `-` 开头的文本被当成命令行参数。
3. **给子进程的环境变量**：`FEISHU_HUB_URL`、`FEISHU_HUB_TASK_ID`、`FEISHU_HUB_LEASE_ID`、`FEISHU_HUB_CWD`（令牌文件可选 `FEISHU_HUB_TOKEN_FILE`）。
   子进程内的桌面 Hook 看到 `FEISHU_HUB_TASK_ID` 时**直接退出**：该任务的结果由执行器统一上报，Hook 既不上报 `result` 也不调用 `/v1/sessions/turns`，避免重复发卡片。
4. **心跳**：每 `heartbeat_sec` 上报一次；收到 `409` 就结束子进程树。
5. **结束**：进程正常退出且已经上报过 `result`，任务结束。进程退出了却没有 `result`，上报 `failed{code: NO_RESULT}`。执行器自身异常时，**先结束子进程树**，再上报 `interrupted`。

### 5.2 执行器重启

- 执行器重启后，未完成的租约自然过期。Hub 发现租约过期且没有终态事件时，把任务置为 `NEEDS_RECOVERY`，由用户在飞书选择「续跑 / 放弃」，**不会自动重派**。
- （可选）执行器可以在本地记录「task_id → pid, pid_ctime」。重启后如果发现旧进程仍在运行，可以重新 `hello` 并继续为旧租约上报心跳；租约已丢失（409）就结束该进程。v1 的 Claude 执行器未实现此项：执行器重启即由用户决定续跑或放弃。
- Hub 自身重启时，会把仍为 `LEASED` 的租约延长 `2 × lease_ttl_sec`，给执行器恢复心跳的时间，而不是立即判为失联。

### 5.3 桌面队列方式（`desktop_queue`，供 Codex 使用）

当目标会话由桌面端持有写入权（再开一个写入者会冲突）时：
1. 执行器把消息排入桌面会话（例如 `codex queue --thread <session_id> --message …`），成功后上报 `started{delivery: "desktop_queue", queue_id}`。Hub 把任务置为 `WAITING_EXTERNAL`，**该租约随即失效**：执行器停止心跳，之后对该租约的任何事件都返回 `409 LEASE_LOST`（结果只能经桌面 Hook 回报）。
2. 桌面端执行完这一轮后，桌面 Hook 调用 `/v1/sessions/turns`，Hub 按 §3.5 把它匹配给该会话最早的 `WAITING_EXTERNAL` 任务。
3. 投递确认丢失（超时）时，执行器上报 `started{delivery: "desktop_queue", queue_id: null}`，**不得重复投递**；Hub 同样进入等待，超过 `timeout_sec` 仍无回报就转 `NEEDS_RECOVERY`。

## 6. 可见对话条目（items）

```json
{"id": "msg_…", "role": "user|assistant", "phase": "commentary|final", "text": "…"}
```
- 只包含用户可见的文字，不包含推理、工具调用原文和系统提示。
- `id` 在会话内稳定唯一，Hub 用它去重（重复上报同一个 `id` 不会重复发飞书）。
- 附件只上报名称和路径，例如 `{"role": "user", "text": "[附件] a.png D:\\x\\a.png"}`。

## 7. 状态与错误

### 7.1 任务状态（Hub 内部，供执行器理解）

```
RECEIVED ─┬─ NEED_EXECUTOR ─┐
          ├─ NEED_DIR ──────┤（用户补充并确认）
          ├─ NEED_CONFIRM ──┤（危险指令确认）
          └─────────────────┴→ QUEUED → LEASED → RESULT_SAVED → DELIVERING → DONE
                                  │        ├→ WAITING_EXTERNAL → RESULT_SAVED
                                  │        ├→ FAILED
                                  │        └→ NEEDS_RECOVERY（租约过期 / interrupted）→ 用户：续跑→QUEUED｜放弃→CANCELLED
                                  └→ CANCELLED
```

- 结果先落库（`RESULT_SAVED`）再发飞书；发送失败只重试发送，**不**重新执行。
- `NEEDS_RECOVERY` 只能由用户操作离开。

### 7.2 错误码

| HTTP | code | 含义 / 执行器动作 |
|---|---|---|
| 400 | `BAD_REQUEST` | 请求格式错误，修正后重试 |
| 401 | `UNAUTHORIZED` | 令牌错误，停止并告警 |
| 404 | `TASK_NOT_FOUND` | 任务不存在，放弃 |
| 409 | `LEASE_LOST` | 租约失效，**立即结束子进程**，不再上报 |
| 409 | `ALREADY_FINAL` | 本租约的终态事件已被接受（例如响应丢失后用新 seq 重试）：终态事件视为成功，其他事件忽略 |
| 426 | `PROTOCOL_UNSUPPORTED` | 协议版本不兼容，停止并告警 |
| 5xx | `HUB_ERROR` | 同一 `seq` 指数退避重试（1s→30s，约 5 分钟）；仍失败时停止上报，由租约过期转人工恢复（Hub 重启时会给有效租约宽限期）。Hook 上报失败则落盘，执行器上线后补发 |

`failed.data.code`（执行器上报）：`CWD_MISSING`、`SESSION_NOT_FOUND`、`SESSION_BUSY`、`CLI_NOT_FOUND`、`AUTH_REQUIRED`、`NO_RESULT`、`TIMEOUT`、`EXEC_ERROR`。

## 8. 安全

- Hub 只监听 `127.0.0.1`；迁到线上后必须使用 HTTPS 和独立令牌。
- 令牌文件只允许当前用户读取；日志只记录 `task_id`，不记录令牌和完整 prompt。
- v1 不实施目录外授权（方案 A4、A5 暂不满足，见 §4 `grants`）。执行器按用户选择使用无确认模式运行。

## 9. 兼容与演进

- 新增字段只增不改；删除或改变语义需要升级 `protocol` 版本。
- 执行器通过 `hello.capabilities` 声明能力；Hub 按能力派发任务（例如 `new_session=false` 的执行器不会收到 `mode=new` 的任务）。
