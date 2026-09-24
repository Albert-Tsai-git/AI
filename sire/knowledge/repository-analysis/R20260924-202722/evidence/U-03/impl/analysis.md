# U-03 分析：EncoderPlotter_0703_01/_0703_02/_0703_03/_0903_01

执行中：分析四个版本快照、各自构建/测试路径与四个子模块 gitlink。
执行完毕：完成；共同架构与版本差异已分开记录。未运行测试、构建或设备操作。

## 共用架构
- 四目录来自同一上游 EncoderPlotter Git 远端。Electron → Vue 2/Vuex renderer → Python middleware；入口由 `main/index.js`、`controller/index.js`、`controller/server.js`、`controller/python/main.py`、`Server.py`、`Encoder.py` 组成。JS/Python 通过二进制帧交换命令。
- `sub_algorithm` 是标定算法，`sub_automation` 是环境/工厂自动化，`sub_common` 是协议/结构/配置，`sub_embedded` 是 Analyzer/设备/IAP 通信；父仓 gitlink SHA 决定检出快照。
- `qa_api`、loopback HTTP API 与 HTTP IAP 门禁只存在于 0703_01、0703_02、0903_01；0703_03 没有 `controller/python/qa_api`，不能将 HTTP API/IAP 描述套用到它。四仓 Electron 均设置 `nodeIntegration:true`、`contextIsolation:false`。

## Git 状态与版本
|目录|分支 / HEAD|工作区|版本 / 特征|
|---|---|---|---|
|0703_01|`feature/dpb-409` / `9649f4af49fb504413b64c3022773804a3747d0c`|未跟踪 `controller/python/command_sender.py`、`xxxx.py`|4.10.0；DPB 409 参数/布局变更。|
|0703_02|`develop` / `6bf8c66c6de9e1b61a7bd5dddf6c2e8addbd863f`|干净|4.10.0；共同 develop 基线。|
|0703_03|`feature/flash-and-pcba` / `1f5c515a9ffaa21cc475381bfb99591eef5413ca`|干净；本地跟踪 ref ahead 1|4.7.17；工厂刷写/PCBA 工具。|
|0903_01|`feature/iap` / `dd1278c2103cc43406b28e083a1fcfd62ccb0d6d`|干净|4.10.0；IAP BIN/Footer 布局解析。|

0703_03 ahead 仅相对本地 origin 跟踪引用，未 fetch。其 `sub_algorithm` 在本地 `feature/algoV4000` 分支，较本地 origin ref behind 8；`sub_automation` 本地分支较本地 origin ref ahead 1。工作区检出 SHA 仍匹配父仓 gitlink，不是 gitlink 错配。

## 固定子模块提交（短 SHA）
|父仓|sub_algorithm|sub_automation|sub_common|sub_embedded|
|---|---|---|---|---|
|0703_01|`e297c0d`|`3332eb2`|`e717cd7`|`78f228f`|
|0703_02|`8af2836`|`3332eb2`|`017a0d9`|`fd87399`|
|0703_03|`8af2836`|`30b1c3f`|`8c06f41`|`85d1274`|
|0903_01|`b1d539a`|`3332eb2`|`c53a7b2`|`226a010`|
- 四仓共 16 个检出 SHA 均匹配对应父仓 gitlink。

## 各仓构建与测试入口（静态盘点）
- 0703_01：`npm start`、`npm run build:app`；dev-setup 有四条 Python 测试（build_info、safe_name、V4060 runtime config、qa_api），CI 有六条，另加 product_info 与 DPB flash layout。
- 0703_02：`npm start`、`npm run build:app`；dev-setup 与 CI 均有四条 Python 测试：build_info、safe_name、V4060 runtime config、qa_api。
- 0903_01：`npm start`、`npm run build:app`；dev-setup 与 CI 均有上述四条 Python 测试。
- 上述三仓还含 `controller/python/qa_api`；Python 测试依赖 `requirements-test.txt`，按 `docs/dev-setup.md` 从 `controller/python` 工作目录执行。命令仅作入口记录，本次未运行。
- 0703_03：无 `.gitlab-ci.yml`、`docs/dev-setup.md`、`qa_api`；`package.json` 有 `npm start`、`npm test`（执行 `node controller/test/testRunner.js`）、`build-flash`、`build-flash-v2`、`build-pcba`、`build-factory-tools`，还含 `dist*` 应用打包脚本。不能套用另外三仓的 CI/test 清单。

## 业务差异、未跟踪代码与限制
- 0703_01/02/03 的 `controller/python/Encoder.py` 使用调用方 `chosenSoftwareVersion` 并由 `utilities.getIAPArguments()` 查版本参数；只有 0903_01 使用 `parse_iap_bin.py`、`flash_layout.py` 解析 BIN/Footer 布局。不要把新版实现归到前三个版本。
- 0703_03 `package.json` 是 4.7.17，额外含 `build-flash*`、`build-factory-tools`、`build-pcba` 工厂工具脚本；其他三个是 4.10.0。
- 0703_01 的未跟踪 `command_sender.py` 可执行上电/断电、LED preset 与自定义硬件命令；`xxxx.py` 是硬件交互脚本，只做进入/退出再标定与 Hall 读取，自述不写 Flash。两者属于当前工作区分析，不属于 HEAD。
- 0903_01 HTTP IAP 需显式 `--http-enable-iap`。HTTP 硬件写入风险应作为门禁记录；本次未连接设备。
- 排除 `.env`、`target.json`、样本/日志、构建/Nuitka 输出和依赖缓存；只归档架构、入口、版本差异和工作区元数据。

产物：四仓分析、16 个 gitlink pin 矩阵与各仓构建/测试入口清单。
验证：R6 复核 Git 元数据、gitlink、目录存在性、IAP 实现差异及测试命令来源；R7 不运行固件仓测试。
阻塞：无。
