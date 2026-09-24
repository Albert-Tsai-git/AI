# U-02 分析：EncoderPlotter1–5

执行中：分析五个工作树、共用主架构与固定子模块。
执行完毕：完成；五者均为同一上游 `software/EncoderPlotter.git` 的不同快照，不应当作五套独立产品。未运行测试/构建。

## 项目共性
- Electron 主进程 + Vue 2/Vuex 页面 + Python 硬件中间件；用途是编码器上位机，连接 Analyzer，支持绘图、参数读取/写入、再标定、IAP、MES/环境箱。README `:3-16`；`main/index.js`、`asset/js/main.js:39-75`、`controller/server.js:87+`、Python `main.py` → `Server.py` → `Encoder.py` 是入口链。
- JS/Python 使用二进制 stdin/stdout 协议（JS 解析约 `controller/server.js:338-450`，Python 侧 `Server.py:134-169`）；API 测试服务 `qa_api/` 桥接同一命令分派。修改命令/帧布局需同步 `sub_common` 与两端协议实现。
- 四子模块负责硬件通信（`sub_embedded`）、协议/结构/配置（`sub_common`）、标定算法（`sub_algorithm`）、环境自动化（`sub_automation`）。父仓中的 gitlink commit 是可复现版本依据。

- Shared packaging commands: `npm start` for development and `npm run build:app` for Electron packaging. Python CI and dev-setup test commands are listed per snapshot below.
## 当前工作树
|目录|分支 / HEAD|状态|快照差异|
|---|---|---|---|
|EncoderPlotter1|`feature/lingxi-dpt-iap-preserve-zero` / `b9784c457b410bda20cfaac257abe374e6edf54c`|干净|本地 origin/develop ref 上领先 29；含 V4065 初启查询及 IAP 相关改动。|
|EncoderPlotter2|`feature/mpt-g-remerge-2` / `0d5897b5a94c95fa5a7c13071c5d656293032dfb`|干净|本地 origin/develop ref 上领先 8；MPT-G 参数兼容。|
|EncoderPlotter3|`feature/xingdongjiyuan-sn` / `6878681a76087f8233904f5c1a877b5b21c375a0`|干净|本地 origin/develop ref 上领先 14；SN/IAP 与 Linux 包路径差异。|
|EncoderPlotter4|`codex/feature/tpb-requirements` / `6bf8c66c6de9e1b61a7bd5dddf6c2e8addbd863f`|5 个主仓文件及 sub_common dirty；无 upstream|与 EP5 HEAD 相同，但含未提交 TPB 部分实现。主仓改动：`controller/defines.js`、`controller/encoder.js`、`controller/python/qa_api/encoder_profile.py`、`controller/python/qa_api/routes_iap.py`、`controller/python/qa_api/tests/test_profile.py`。|
|EncoderPlotter5|`develop` / `6bf8c66c6de9e1b61a7bd5dddf6c2e8addbd863f`|干净|可作与 EP4 相同 HEAD 的干净参照。|

领先数量只按本地 origin/develop remote-tracking ref 计算，未 fetch，不代表远端现况。

## 固定子模块提交（短 SHA）
|快照|sub_algorithm|sub_automation|sub_common|sub_embedded|
|---|---|---|---|---|
|EP1|`b1d539a`|`3332eb2`|`b8d898b`|`5da3d89`|
|EP2|`fd85f15`|`3332eb2`|`ce132d2`|`bb45bb4`|
|EP3|`f67de7d`|`3332eb2`|`516031a`|`bce0bac`|
|EP4/EP5|`8af2836`|`3332eb2`|`017a0d9`|`fd87399`|
- 全部检出 SHA 与对应父仓 gitlink 相同。EP1 common、EP3 common 检出在 branch；EP4 common detached 且 dirty，其余状态以本地工作树为准。

## 各快照构建与测试入口
- EP1: `npm start`, `npm run build:app`; CI and docs/dev-setup each list four Python tests: build_info, safe_name, V4060 runtime config, and qa_api.
- EP2: `npm start`, `npm run build:app`; CI and docs/dev-setup each list the same four Python tests: build_info, safe_name, V4060 runtime config, and qa_api.
- EP3: `npm start`, `npm run build:app`; CI and docs/dev-setup each list the same four Python tests: build_info, safe_name, V4060 runtime config, and qa_api.
- EP4/EP5 current committed snapshot: `npm start`, `npm run build:app`; all four Python tests are the same as EP2/EP3: build_info, safe_name, V4060 runtime config, and qa_api. EP4’s TPB overlay is uncommitted and cannot be attributed to EP5; its dirty overlay has no separate test-coverage claim.
- Python 测试需在 `controller/python` 工作目录安装 `requirements-test.txt` 后按各仓文档/CI 命令执行。本次只静态盘点，未运行。
- 不同于 U-03 的 0703_03 快照：本系列五仓均含 `qa_api`；不要将其他家族的缺失路径套用到这五仓。

## 分支差异、风险与限制
- EP1 package `EncoderAnalyzer 4.10.0`；提交包括 V4065 查询、IAP BIN 解析/加密变更。EP2 4.10.0，主打 MPT-G 参数兼容与算法 pin。EP3 4.10.0，含 SN/IAP 修正和 CI Linux 包目录名修复。
- EP4 未提交 TPB overlay：common `Defines.py/config.py/utilities.py` 有改动；TPB `productInfoList` 仍空且版本/算法/Flash 地址未配齐，`routes_iap.py` 要求已登记版本，不能声称支持 TPB IAP。EP5 与 EP4 的已提交 HEAD/gitlinks 相同但工作区干净。
- 共享 Electron 配置 `main/index.js:66-70` 启用 `nodeIntegration` 并关闭 `contextIsolation`。HTTP QA 服务绑定 loopback、默认 token；超时可能意味着硬件命令已执行但响应丢失（`qa_api/ServerBridge.py`），写操作重试前先读状态。HTTP 模式才有 per-device dispatch，并有 IAP 固件写入/变砖门禁。
- IAP is default-off and flag-gated. Source comments citing lack of hardware verification are stale relative to the guide/ADR, which describe the brick-risk rationale. This analysis did not validate hardware.
- 排除 `.env`/配置秘密、`target.json`、运行日志、测量样本、node_modules/venv/pytest cache/Nuitka dist；仅归档稳定架构、协议、release 门禁与工作树元数据。

产物：本分析稿与五个快照的入口/版本/测试清单。
验证：R6 复核过 Git 基线、关键入口、gitlink 和 EP4 dirty 文件列表；R7 仅验证知识库写入与检索，不执行项目测试。
阻塞：无。
