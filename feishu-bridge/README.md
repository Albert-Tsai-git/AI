# feishu-bridge：飞书 ↔ Claude Code / Codex

在本机跑的桥接服务：

1. **跟机器人说话 → 自动分析 → 交给 Claude 或 Codex 执行**：执行过程在飞书卡片里实时刷新，需要权限时弹卡片让你点"允许 / 拒绝"，完成后回写结果。
2. **在飞书话题里回复 → 同步到对应的 Claude / Codex 会话继续执行**：一个会话 = 一个飞书话题。
3. **在电脑终端里直接用 Claude Code / Codex 聊天 → 同步到飞书**（可选，配 hooks）：之后在飞书那个话题里回复，也能接着这个会话继续。

```
 飞书 ──长连接──▶ 桥接服务 ──分析/路由──▶ Claude Agent SDK / Codex SDK ──▶ 你电脑上的项目目录
  ▲                  │  ▲
  └── 卡片/回复 ◀────┘  └── hooks / notify ◀── 终端里的 Claude Code / Codex
```

飞书用**长连接**收消息，不需要公网 IP，也不需要额外的 API Key：Claude 用你本机 Claude Code 的登录，Codex 用你本机 Codex 的登录。

---

## 一、准备

- Node.js **22.13+**
- 本机 `claude` 已登录可用；要用 Codex 的话 `codex login` 已完成
- 一个飞书企业自建应用（下一步创建）

## 二、创建飞书应用

在 [飞书开放平台](https://open.feishu.cn/app) → 创建**企业自建应用**：

1. **添加应用能力** → 机器人。
2. **权限管理** → 开通：
   - `im:message`（获取与发送单聊、群组消息）
   - `im:message:send_as_bot`（以应用的身份发消息）
   - `im:message.p2p_msg:readonly`（读取用户发给机器人的单聊消息）
   - `im:message.group_at_msg:readonly`（群里 @ 机器人时接收消息，只在私聊用可以不开）
   - `im:resource`（上传文件：结果太长时以文件发送）
3. 记下 App ID / App Secret，**先完成下面第三节把服务跑起来**（长连接模式要求保存设置时客户端已在线），再回来做第 4 步。
4. **事件与回调**：
   - 事件配置 → 订阅方式选「**使用长连接接收事件**」→ 添加事件 `接收消息 im.message.receive_v1`
   - 回调配置 → 订阅方式选「**使用长连接接收回调**」→ 添加回调 `卡片回传交互 card.action.trigger`
5. **版本管理与发布** → 创建版本并发布（可用范围包含你自己）。

## 三、安装和启动

```bash
cd feishu-bridge
npm install
cp config.example.yaml config.yaml     # 按注释修改：项目目录、助手说明等
cat > .env <<'EOF'
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
EOF
npm start
```

看到 `飞书长连接已建立` 就连上了。第一次使用：

1. 在飞书里搜索你的机器人，私聊发一条任意消息，它会回复 **你的 open_id**；
2. 把 open_id 填到 `config.yaml` 的 `feishu.allowedOpenIds`，重启 `npm start`。

之后只有白名单里的人能使用。

## 四、在飞书里怎么用

| 你发的消息 | 会发生什么 |
| --- | --- |
| `给登录表单补几个单元测试` | 调用模型分析交给谁、在哪个项目（依据 `agents.*.description`），拿不准时弹卡片让你选 |
| `/codex 写个脚本统计日志` / `cx …` / `让codex…` | 点名直接交给 Codex，跳过分析 |
| `/claude api 看看这个报错` | 点名 Claude，在 `api` 项目里执行 |
| `#前端 按钮颜色改成蓝色` | 用 `#项目名/别名` 指定项目 |
| 在任务的话题里回复 `再加一个边界用例` | 接着同一个会话继续（Claude 用 resume，Codex 用 resumeThread） |
| 话题里回复 `y` / `n` / `始终允许` | 回应待确认的权限请求（也可以点卡片按钮） |
| `/stop`（话题里） | 停止这个会话正在执行的任务；在话题外发则停止全部 |
| `/ls` `/status` `/projects` `/help` | 最近会话、运行状态、项目列表、帮助 |

规则：**新消息 = 新任务，话题里回复 = 续聊**。同一个会话的消息排队串行执行，不同会话可以同时跑。

每张任务卡片底部会给出"回到电脑继续"的命令（如 `cd ~/code/web && claude --resume <id>`），在终端里可以直接接着飞书上的会话干活。

## 五、终端里的会话同步到飞书（可选）

### Claude Code

把 [`examples/claude-settings.json`](examples/claude-settings.json) 里的 `hooks` 合并进 `~/.claude/settings.json`。之后在终端里用 Claude Code：

- 第一条提问时，机器人私聊你一条「🖥 本地 Claude 会话 · 项目名」，这就是这个会话的话题；
- 之后每轮的提问（👤）和回答都会发到这个话题里；
- 终端在等你确认权限或输入时，话题里会收到提醒；
- 在这个话题里回复，就会在后台接着这个会话执行。如果终端里这个会话还开着，默认**分叉出一个新会话**继续，避免两边同时写同一个会话（`claude.whenLive` 可改）。回到电脑后用卡片上的 `claude --resume <新id>` 接上。

退出 Claude Code 时可能看到一行 `SessionEnd hook … failed: Hook cancelled`，这是进程退出太快导致的，事件其实已经送达，可以忽略。

### Codex

在 `~/.codex/config.toml` 里加：

```toml
notify = ["node", "/绝对路径/feishu-bridge/scripts/codex-notify.mjs"]
```

Codex 每轮结束后，提问和回答会同步到飞书；在对应话题里回复同样可以续聊（Codex 没有"会话已关闭"的信号，所以总是直接续上）。

### 不会重复同步

桥接服务自己启动的 Claude / Codex 会带上环境变量 `AI_BRIDGE_ORIGIN=bridge`，hooks 通过 `x-bridge-origin` 头带回来，服务端据此忽略；同时服务端也会忽略它正在驱动的会话的上报，双重保护。

## 六、权限和安全

- **白名单**：只处理 `allowedOpenIds` 里的人发的消息和点的按钮。
- **目录白名单**：飞书里只能用 `projects` 里配置的目录，不能传任意路径。
- **Claude**：默认 `permissionMode: default`，沿用你 `~/.claude/settings.json` 里的 allow 规则，其余需要权限的操作都会发审批卡片；超时（默认 10 分钟）按拒绝处理。"本会话始终允许"只在内存里生效，不会写进你的配置。
- **Codex**：无头执行不能中途审批，由 `sandboxMode` / `networkAccessEnabled` 预先限定（默认只能写项目目录、不能联网）。
- **本地上报口**只监听 `127.0.0.1`，可选加 `ingest.token`。
- 发往飞书的内容会对常见密钥格式（API Key、GitHub Token、私钥等）打码。

## 七、已知限制

- 暂时只处理文字 / 富文本消息，图片和文件还不支持。
- 群聊里默认只有 @ 机器人的消息才会收到；推荐和机器人私聊使用。
- 桥接服务重启时正在执行的任务会中断，卡片会标记"已中断"，在话题里回复可以接着会话继续。

## 八、代码结构 & 以后迁移到服务器

```
src/
  index.ts            启动：加载配置、连飞书、开本地上报口
  bridge.ts           核心逻辑（将来的 Hub）：路由、会话 ↔ 话题、排队、审批、同步
  analyzer.ts         意图分析：命令 → 点名 → 项目默认 → 模型分析 → 关键词 → 默认
  agents/             执行端（将来的 Runner）：claude.ts / codex.ts / classifier.ts
  feishu/             飞书收发、卡片、消息解析
  ingest.ts           本地 hooks / notify 上报入口
  store.ts            SQLite（Node 内置 node:sqlite）
```

`bridge.ts` 只通过 `AgentAdapter` 接口调用执行端。迁移到服务器时，把 `agents/` 连同一个小的本地 Runner 进程留在各台电脑上，服务器上的 Hub 和 Runner 之间用 WebSocket 转发 `runTurn` / `askPermission` / 事件即可（协议草案见 [`../docs/feishu-ai-hub-design.md`](../docs/feishu-ai-hub-design.md) §9），`bridge.ts` 基本不用改。

## 开发

```bash
npm run typecheck
npm test            # 用内存版飞书和假的 AI 跑完整流程
```
