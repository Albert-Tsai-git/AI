# feishu-hub：飞书多 AI 中转中间服务

依据《飞书多 AI 中转与任务协作方案》实现。飞书、Claude、Codex 及后续 AI 都只与中间服务通信，各执行器互相独立。

```
飞书 ⇄ 中间服务 hub（唯一连飞书、唯一发飞书、任务状态唯一来源）
          ⇅ HTTP 协议 v1（127.0.0.1 + 令牌）
   Claude 执行器  ·  Codex 执行器  ·  …
```

| 目录 | 内容 | 负责方 |
|---|---|---|
| `docs/PROTOCOL.md` | 执行器协议 v1 | Claude |
| `docs/CODEX_ADAPTER.md` | Codex 执行器实现说明与验收用例 | Claude 撰写，Codex 实现 |
| `hub/` | 中间服务：路由、状态机、发送队列、租约回收、重启恢复 | Claude |
| `executors/common/hub_client.py` | 协议客户端（执行器与 Hook 共用） | Claude |
| `executors/claude/` | Claude 执行器与桌面 Hook | Claude |
| `executors/codex/` | Codex 执行器与桌面 Hook | Codex |
| `executors/mock/` | 参考执行器（联调用） | Claude |
| `tests/test_hub.py` | 中间服务 + Claude 执行器端到端测试 | Claude |

## 运行

依赖：Python 3.12、`lark-oapi`（沿用旧飞书桥，无新增依赖）。数据目录 `~/.feishu_hub/`（首次启动自动从 `~/.feishu_bridge/config.json` 导入飞书凭据与白名单，并生成执行器令牌）。

```bash
python -m hub.main                    # 中间服务
python executors/claude/executor.py   # Claude 执行器
python tests/test_hub.py              # 测试（不触网）
```

> 飞书长连接的事件只推给一个在线连接：中间服务与旧飞书桥 `~/.feishu_bridge` 不能同时在线，切换步骤见 `docs/CUTOVER.md`（切换时编写）。

## 飞书里怎么用

- **新任务（私聊，严格格式）**：`【执行者 目录 内容】`，【】可省略。
  - 执行者：`claude` 或 `codex`
  - 目录：`默认目录`（配置 `suggest_cwd`）/ `项目名项目`（如 `AI项目`）/ 完整路径
  - 例：`claude 默认目录 告诉我通讯是否正常`、`codex AI项目 检查最近的改动`
  - 不符合格式的私聊消息一律只回复格式提示，不建任务。
- **项目列表**：`claude 项目列表`（或 `codex项目列表`）由中间服务直接列出，不调用 AI。项目 = `project_roots` 下的一级子目录 + `projects` 显式登记。
- **续接**：回复任一任务卡片（内容不限格式），沿用该卡片的执行者、会话和目录；开头写「Codex执行：…」可切换到同目录的 Codex。
- **目录失效**：原目录不存在时会询问目录，回显后需回复「确认」才执行。
- **危险指令**：含危险关键词需回复「确认」。
- **中断**：执行器失联或超时，任务停下等你回复「续跑 / 放弃」，绝不自动重跑。
- **协作**：「你分析，Claude执行」v1 只记录，暂不自动协作。

## 方案验收对照（§8）

| 编号 | 状态 |
|---|---|
| A1–A3、A6–A10 | 已实现，`tests/test_hub.py` 覆盖 |
| A4、A5（目录外授权） | 用户选择方案 C：v1 暂不实施，执行器以无确认模式运行，任务信封 `grants` 恒为空 |
