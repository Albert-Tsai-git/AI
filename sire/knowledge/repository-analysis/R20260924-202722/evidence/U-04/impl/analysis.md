# U-04 分析：辅助工具与无 Git 源码目录

执行中：分析 claude-code、mes、mes-admin、tools_credential_generator。
执行完毕：完成。三个目录无 Git 元数据；tools_credential_generator 是 Git 仓库。未运行测试或构建。

## claude-code
- 无 Git 根、无 README。项目是 Electron/Vite + Vue 3/TypeScript 样板；`src/main/index.ts` 设置 `contextIsolation:true`、`nodeIntegration:false`。该文件有 `python:call`、`python:status`、`app:versions` IPC；其中 `python:call` 是唯一 Python 方法调用 IPC。
- `src/main/python/bridge.ts` 使用 JSON-RPC 2.0/NDJSON stdio 启动子进程，包含请求超时、重启退避和优雅退出。当前目录缺少 `py/main.py`、preload 与 renderer 源目录；`resolve.ts` 和 `py:build` 指向缺失的 Python 入口。这是静态完整性缺口，未尝试运行。

## mes
- 无 Git 根；README 称 MES。实际是 Node/Express + TypeORM + SQLite/PostgreSQL 后端、Vue 3/Pinia/Vue Router 前端、Electron 壳。README 的 React 18 与 `frontend/package.json`、`frontend/src/main.ts`、Vue 页面不一致，按源码为准。
- `backend/src/index.ts` 汇合 auth、workorder、inventory、quality、tracing、equipment、encoder production/release/calibration 等 REST routes；`backend/src/database.ts` 注册实体。前端覆盖工作台、工单、库存、质检、追溯、设备、编码器生产和报表。
- 根 package 支持分别启动 backend/frontend、Electron、Docker PostgreSQL、build/migrate/backup；后端含 validators 单测和编码器/校准集成脚本，Playwright smoke test 需 Electron。本次未运行。
- TypeORM `synchronize:true` 并在启动时执行 seed；生产数据库迁移行为需谨慎核对。README 与 compose 含演示凭据/fallback，不归档实际凭据或任何 `.env` 值。

## mes-admin
- 无 Git 根；Vue 3 + TypeScript + Vite + Electron 管理界面样板。`src/App.vue` 使用本地数组模拟用户、角色、状态筛选、刷新和添加；Electron 只加载前端，preload 暴露平台名，不连接 API、数据库或认证服务。
- `npm test` 是检查演示页面关键文本的 Node smoke test；`npm run build` 为 vue-tsc + Vite。本次未运行。

## tools_credential_generator
- Git branch `feature/optimize-ui`，HEAD `4beeb72fcf8298d1029691f12e80816801277596`；只有未跟踪 `.idea/`、`yarn.lock`。Electron-Vite + Vue 3 小工具。
- preload 用 16-byte 随机 salt、PBKDF2-SHA256 200k rounds 生成 32-byte 派生值，写入 Electron temp 目录的 `.credentials`；这是加盐 PBKDF2 校验值，不是加密内容。UI 提供生成、验证和打开该目录；密码输入使用 `type="text"`，不会遮蔽。无自动测试脚本。
- 安全限制：renderer API 暴露通用 `child_process.exec`、`resolve`、`readFile`、`write2File`；main 通过 IPC 返回 Electron temp 路径，UI 将路径插入 Explorer `exec` 命令。可考虑缩窄 IPC 并使用参数化进程调用。

产物：本分析稿与项目入口清单。
验证：源码、package scripts、Git 元数据静态核对；未运行测试/构建。
阻塞：无。
