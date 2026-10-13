**日期**: 2026-10-13
**项目**: Qoder CLI headless 接入（feishu-hub Qoder 执行器）（`D:\sire\AI\AI\feishu-hub`）
**状态**: 已验证（真机实测；`tests/test_qoder_executor.py` 11/11）
**关键词**: qoderclicn, Qoder CLI, headless, manifest.json, sha256, sdk_invalid_args, QODER_AGENT_SDK_ENTRYPOINT, --permission-mode bypass_permissions, dont_ask, --output-format json, --resume, total_credits, login 设备码, model_by_tier, reasoning-effort

**场景**: 要让飞书 / 脚本能像调用 `claude -p` 那样非交互调用 Qoder。本机只有 IDE（`D:\software\Qoder CN\Qoder CN.exe`），PATH 上没有 `qoderclicn`，`entry/qodercn-dispatcher.ps1` 会回落报错。

**做法**:
1. **版本对齐**：在 `resources/app.asar` 里 grep `qoderCliVersion` 得到 IDE 期望的 CLI 版本（本次 1.1.66），不要盲目装最新。
2. **官方安装**：`https://static.qoder.com.cn/qoder-cli-cn/channels/1.1.66/manifest.json` → `files[]` 取 `os=windows / arch=amd64 / variant!=legacy` 的 `url`+`sha256`；下载 97MB zip，**校验 sha256 相等再解包**（实测 `2010601e43ef…e191b5` 一致），产物 `qoderclicn.exe`、`sites-build.json`、`sites-verification.json`。
3. **落位**：解到 `~/.qoder-cn/bin/qoderclicn/`——官方 dispatcher 的 `Find-Cli` 就找这个路径；不改 PATH、不改注册表、不改 IDE。
4. **调用契约**（真机确认）：`-p --output-format json`，prompt 走 stdin；输出单行 `{"type":"result","result","session_id","is_error","num_turns","total_credits","duration_ms",…}`；`--permission-mode` 用蛇形（`bypass_permissions|dont_ask|accept_edits|auto|default`）；`--tools ""` 做零副作用冒烟；`--resume <session_id>` 可续接（实测能复述上一轮）。
5. **模型分档**：`-m/--model`、`--reasoning-effort`、`--thinking-budget`、`--list-models` 都在 → 执行器加 `model_by_tier`/`effort_by_tier` 配置，飞书任务可按档位派发（推翻"Qoder 无法分档"的旧结论；交互式 `Agent` 工具仍无 model 参数）。
6. **登录**：`qoderclicn login` 打印设备码 URL，桌面已有信任会话时**自动完成**；未登录时结果 JSON `is_error:true`、`result:"Not logged in — Please run /login"` 且 rc=1，执行器映射 `AUTH_REQUIRED`。

**关键文件与接口**:
- `feishu-hub/executors/qoder/executor.py` — `find_cli()`（含 `.qoder-cn/bin/qoderclicn/`）、`ENV_DROP_PREFIX`、`build_cmd()`（含 tier→model/effort）、`--check`
- `feishu-hub/docs/QODER_ADAPTER.md` §5.5 安装来源与实测要点、§5 验收表 Q8a/Q8b/Q8c
- `feishu-hub/tests/test_qoder_executor.py` — 假 Hub + stub CLI 的 `started→session→result` 全序列

**验证方法**: `executor.py --check` 从 `CLI_NOT_FOUND` 变 `OK` 并给出真实路径；真机 headless：`is_error=false`、`result="收到"`、`total_credits=1.278`、15.5s；`--resume` 续接正确；`tests/test_qoder_executor.py` 11 项全 OK；回归 `tests/test_codex_executor.py` 20 项 0 失败。

**踩坑**: ① 直接在 Qoder/IDE 的子 shell 里调 CLI 必失败——`QODER_AGENT_SDK_ENTRYPOINT` 会让它强制要求 `--input-format stream-json --output-format stream-json`，必须在 `build_env()` 里按前缀剔变量；② 只把 `--config-dir`/PATH 之类当排查方向会浪费时间，先看 `sdk_invalid_args` 报的期望参数；③ CLI 报"未登录"这类致命错也照样输出 JSON 且 **stdout 才有信息**，不能只看 rc；④ `--check` 早期把候选路径写成 `bin/qoderclicn.exe` 漏了子目录，探测型代码要用真实安装路径回归。

**限制**: Hub → 执行器 → 飞书卡片的端到端仍待用户按 `docs/CUTOVER.md` 停旧飞书桥后启 Hub 验证（Q8b）；`model_by_tier` 需要登录后 `--list-models` 取值；CLI 每次执行消耗 credits（本次 1.28/条），Hub 侧 `daily_task_limit=20` 仍生效。
