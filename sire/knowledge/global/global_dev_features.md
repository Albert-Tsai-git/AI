# 全局功能开发记录 (F)

### F-004: 高低温箱功能影响范围分析
**日期**: 2026-07-16
**项目**: EncoderPlotter_0703_02
**关键词**: chamber, 高低温箱, temperature, humidity, Modbus, 独立进程, 同步采样, EncoderPlotter

**需求场景 / 现象**: 分析高低温箱功能在代码库中的实现方式和影响范围

**方案 / 实施步骤**:
方案要点：
- 独立 Python 子进程 (main.py --chamber)，不与编码器共用 stdout 通道
- JSON 行协议通讯，一行一条请求/响应
- 自动扫描串口时排除编码器分析仪占用的串口，避免端口冲突

实施步骤：
高低温箱设备 -> Modbus RTU (寄存器7991=温度, 7992=湿度) -> Python驱动解析 -> JSON响应 -> 面板实时值(1s低频) 或 编码器同步采样(chamber.frequency频率) -> 内存samples数组 + jsonl磁盘缓存 -> 独立CSV导出
- 读取开始: 启动同步采样 + 清空前一轮缓存 + 触发图表重绘
- 读取进行: 按频率采样，通过 dataIndex 与编码器数据对齐
- 读取停止: 停止高频采样，恢复低频状态刷新
- 页面销毁: 主动释放进程和定时器，避免资源泄漏

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: components/encoder/dataParser.js 中的 temperatureBuffer 是编码器自带温度（RS485协议AngleWithTemperature命令），不是高低温箱数据。高低温箱数据保持独立采样流，不进入 encoder binary data。
- 修改1 (2026-07-16): 霍尔模式 H 命令 ACK 末尾增加 1 字节状态位
  - 文件: components/mixins/configsMixin.js
  - 修改 timeoutByteNum + 1
  - 增加状态位 resolver: V.getUint8(偏移)
  - 不改变之前霍尔值和角度值的偏移量

---



---
1. DPTv411 固件升级（R001, R002）：- **分支**: origin/test/iap-from-401-to-411
- **升级配置**: 401 (algorithmVersion=4020, supported=[401,402,403,410,411]) → 411 (algorithmVersion=4027, supported=[401])
- **数据地址**: outer (angleData 0x08012800, polyfits 0x08013000); inner (angleData 0x08012834, polyfits 0x08029800)
- **算法子模块 commit**: 58fd57148e97384d18729c71fab4d27ddd86f032
- **TODO**: 保留讨论结果，后续与项目经理沟通
2. Hall 采集频率优化（R003, R004）：- **分支**:
eature/speed-up-hall-collecting-frequency
- **最大采样率公式**（DPT，4Mbps）：rate = 1_000_000 / (2.5 × (reader_response + cmd 2 + device_response + data 38 + timeout 5)) ≈ 7_272 Hz
- **TODO 1**: UI 上做开关区分【高速采样】与【普通采样】
- **TODO 2**: 套用公式估算高速采样频率并显示
3. 过程文档：- 位置: ~/sire_global/projects/EncoderPlotter_0703_01/docs/R001-R004_process.md
- 本地备份: @CODE_ROOT@\EncoderPlotter_0703_01\docs\sire\R001-R004_iap_411_hall_freq_process.md



---
2026-07-16 | P001 DPTv411 降级路径未确认：- **问题描述**: 411 的 supportedVersions=[401] 表示 401 能升级到 411，但 411→401 的降级回退路径未在配置中声明，不明确。
- **影响范围**: IAP 固件升级回退流程
- **责任人**: 项目经理
- **当前状态**: 待确认
- **建议方案**: 在升级配置中添加 downgradeVersions 字段，或明确注释不允许从 411 回退
2026-07-16 | P002 采样率公式建议参数化：- **问题描述**: R004 采样率估算公式中，波特率、响应时间、指令/数据/超时字节数当前以 DPT 产品为例硬编码，其他产品线可能不同。
- **影响范围**: feature/speed-up-hall-collecting-frequency 功能扩展
- **责任人**: 开发
- **建议方案**: 将上述参数抽取为产品级配置表，避免硬编码
---

**关键文件与接口**: - controller/chamber.js: 进程管理、JSON 请求路由、超时控制
- components/encoder/device.js: 面板切换、双模式采样、数据对齐、导出清理（影响最大）
- components/encoder/multiReadoutChart.js: 温湿度虚拟曲线，Y轴固定范围防抖动
- controller/python/sub_automation/Chamber.py: connect/read/close 命令分发
- controller/python/sub_automation/ChamberModbus.py: Modbus RTU 驱动
- 从站地址: 0x01，功能码: 0x03 (Read Holding Registers)
- 寄存器 7991: 温度（有符号16位整数 / 10）
- 寄存器 7992: 湿度（有符号16位整数 / 10）
- 响应帧: 7字节 (SLAVE_ID + FUNC + LEN + DATA*2 + CRC*2)

**状态**: 已完成

### F-005: 加密模块分析（程序加密 vs 分段加密）
**日期**: 2026-07-17
**项目**: EncoderPlotter_0703_02
**关键词**: encryption, 程序加密, 分段加密, IAP, AES, RSA, Protector, BootLoader

**需求场景 / 现象**: F-005
分析程序加密和分段加密的实现方式和区别

**方案 / 实施步骤**:
【程序加密 (encrypt_file)】- 算法：RSA + AES-256-CBC + RSA 数字签名
- 入口：EncoderCommandIapEncryption (61) → Protector.encrypt_file()
- 每次随机生成 AES-256 密钥，RSA 公钥加密传输
- 输出格式：[RSA加密密钥(256B)][IV(16B)][密文][签名(256B)]
- 用途：文件分发/存储加密，解密方持有 RSA 私钥
【分段加密 (encrypt_file_aes_v2/v3)】- 算法：固定密钥 AES-128-CBC + 分包 + CRC8 校验
- 入口：EncoderCommandIapSegmentedEncryption (63) → 先检测 BootLoader 版本
- 固定密钥硬编码：\xa3\xa3FA\x91G\x19c\n:;\xf4\xf7\x1d\xd3\xac
- V3: 每 256 字节直接加密 → [长度(4B)][加密包][CRC8(1B)]
- V2: 先包装内部包 [序号(2B)][长度(2B)][数据][CRC8(1B)] → 再加密
- 用途：IAP 固件烧录，设备端逐包解密烧录
【核心差异】- 密钥：随机 vs 固定
- 粒度：整文件 vs 256B分包
- 校验：RSA签名 vs CRC8逐包
- 场景：文件分发 vs IAP固件升级
【过程文档】- ~/sire_global/projects/EncoderPlotter/docs/R001_encryption_analysis.md

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: - controller/python/sub_common/Protector.py（加密核心）
- controller/python/Encoder.py（命令入口）
- components/share/iap.js / iap.html（前端触发）
- controller/python/sub_common/Defines.py（命令码定义）

**状态**: 已完成

### F-006: 读取模式数据自动保存（时间戳目录）功能
**日期**: 2026-08-12
**项目**: EncoderPlotter_0703_01
**关键词**: Electron, Vue2, Vuex, 设置弹窗, 目录选择, 时间戳目录, 数据持久化, 读取模式, bin文件复制, i18n双语

**需求场景 / 现象**: R001-R011
设置中新增【是否保存读取模式数据】选项，开启后每次读取自动将采集数据保存到时间戳目录
```
设置当中增加一个选项【是否保存读取模式数据】：
1. 如果打开，显示一个选择目录的操作，可以指定任意目录，默认为全局的log目录
2. 如果这个开关打开，每次读取的时候，在选择的目录下创建一个以时间戳为名字的目录（例如20260812-102800），作为后续将采集到的数据存盘的路径
3. 如果没有开启这个选项，保持当前逻辑（使用临时目录temp，不清用户配置）
```

**方案 / 实施步骤**:
修改的函数清单（device.js）：| 函数 | 修改类型 | 说明 |
|------|---------|------|
| getReadoutDataSaveDir() | 新增 | 计算根目录：开关开-配置目录/logs，关-temp |
| createTimestampedSaveDir() | 新增 | 创建时间戳目录+赋值_currentSaveDir+日志 |
| appendChamberSampleCache() | 修改 | targetDir切换：开且有_currentSaveDir-新目录，否则temp |
| exportChamberSamplesCsv() | 修改 | dataDir切换：同上 |
| startChamberReadout() | 修改 | 清缓存chamberTargetDir切换：同上 |
| stopReadout() | 改造async | 收集savePromises-await Promise.all-若有_currentSaveDir则copyFile所有.bin/.chamber.jsonl到新目录-finally清_currentSaveDir |
| clearBinFiles() | 修改 | 始终清空temp的.bin和.chamber.jsonl（防止旧数据污染copy源） |
| switchReadoutModeStateMulti() | 改造async | await clearBinFiles - await createTimestampedSaveDir |
| exportData() | 修改 | dataDir切换：开且有_currentSaveDir-新目录，否则temp |
【验收标准】- [x] preferences新增 saveReadoutData: { enabled: false, directory: '' } 字段
- [x] 设置弹窗UI增加是/否单选开关【是否保存读取模式数据】
- [x] 开关打开时显示【选择保存目录】按钮 + 当前目录显示（空字符串显示"默认日志目录"）
- [x] 目录选择复用已有IPC get-selected-position（dialog.showOpenDialog openDirectory）
- [x] 开关关闭时所有行为100%等价于原有逻辑（路径、清缓存、无副作用）
- [x] 开关打开时：开始读取 → 在指定目录(baseDir或logsPath)下创建时间戳子目录 YYYYMMDD-HHMMSS
- [x] 开关打开时：停止读取 → 将temp目录下当次的 .bin 和 .chamber.jsonl 文件复制到时间戳目录
- [x] chamber采样缓存写入路径随开关切换（append时直接写时间戳目录，不等待stop复制）
- [x] 导出数据 exportData / exportChamberSamplesCsv 读取路径随开关切换
- [x] 新增9个翻译键中英文双语覆盖完整
- [x] 无论开关是否开启，开始新读取前清空temp目录避免旧文件污染新保存目录
- [x] startChamberReadout中温湿度缓存清理路径同步切换
【架构决策：双写策略（先写temp，stop时复制）】- 原因：Encoder类内部 saveData() 硬编码写 window._tempPath，且 dataContinuousStartMultipleCommands() 无saveDir参数
- 权衡：修改 Encoder 类将超出device.js单文件修改约束，且影响范围不可控
- 因此：读取过程中编码器bin仍写temp（原有路径），chamber采样边写边写入新目录（自己控制的fs.appendFile），stopReadout时等所有saveData完成后把temp中的 .bin / .chamber.jsonl 通过 fs.copyFile 复制到时间戳目录
- 关键保障：startReadout时始终清空temp，保证copy不包含上一轮遗留文件
【目录创建与生命周期】```
createTimestampedSaveDir() 仅当 enabled=true 时执行：
  baseDir = directory || window._logsPath
  timestamp = window.timeStr()  ->  YYYYMMDD-HHMMSS
  targetDir = path.join(baseDir, timestamp)
  fs.mkdir(targetDir, { recursive: true })
  this._currentSaveDir = targetDir  // 组件实例属性，非响应式非持久化
  finally: stopReadout 执行完毕后 this._currentSaveDir = undefined
```
【关键决策与理由】| 决策项 | 选择 | 理由 |
|--------|-----|------|
| 数据保存策略 | 先写temp+stop复制 | Encoder.saveData硬编码写temp，不能改底层类 |
| chamber写策略 | append直接写时间戳目录 | chamber缓存由我们自己写fs.appendFile，可直接改路径，崩溃时也有备份 |
| clearBinFiles开关开时 | 始终清空 | 否则上次遗留.bin会被copyFile污染新目录（测试发现的关键bug） |
| 目录变量存储 | this._currentSaveDir实例属性 | 纯临时状态，无需Vuex持久化，下次读取会被createTimestampedSaveDir覆盖 |
| 设置弹窗变量 | 本地临时变量+关闭时写回 | 与localMesEnabled/localAdmin模式一致，避免直接改全局状态时异常 |
| 目录为空时回退 | window._logsPath | 需求明确指定默认日志目录 |
| 异常处理策略 | try-catch记录warning，不阻塞主流程 | 目录创建/复制失败不应影响读取功能正常运行 |
| stopReadout async改造 | Promise.all等待所有saveData | 确保文件落盘后再复制，否则可能得到0KB文件 |
【翻译键清单（9个，en/zh双语）】| Key | English | 中文 |
|-----|---------|------|
| 是否保存读取模式数据 | Save Readout Mode Data | 是否保存读取模式数据 |
| 请选择读取数据保存路径 | Please select save path for readout data | 请选择读取数据保存路径 |
| 选择保存目录 | Select Save Directory | 选择保存目录 |
| 默认日志目录 | Default Log Directory | 默认日志目录 |
| 读取数据保存路径 | Readout Data Save Path | 读取数据保存路径 |
| 读取数据将保存至 | Readout data will be saved to | 读取数据将保存至 |
| 创建保存目录失败 | Failed to create save directory | 创建保存目录失败 |
| 读取数据已保存 | Readout data saved | 读取数据已保存 |
| 保存数据失败 | Failed to save data | 保存数据失败 |
【SIRE执行记录】- 角色1：需求拆解 8项 - 角色2校验合并为11项明确需求清单
- 并行开发：组A（global.js/version.html/version.js/i18n.js）+ 组B（device.js），文件集完全不相交，无冲突
- 审查结果：通过（功能全覆盖）
- 测试后修复2个bug：clearBinFiles开关开时跳过导致数据污染；startChamberReadout缓存清理硬编码temp路径

**验证方法**: | 场景 | 行为 |
|------|-----|
| enabled=false（从未开） | 完全走原temp逻辑，无任何副作用 |
| enabled=true, directory='' | 正确回退到window._logsPath |
| enabled=true, 自定义目录 | 正确使用自定义目录创建时间戳子目录 |
| 读取中崩溃关闭应用 | _currentSaveDir为组件属性，下次重建组件时自动重置，无脏值 |
| mkdir权限不足/磁盘满 | try-catch返回undefined，正确回退temp |
| 多编码器同时读取 | stopReadout多设备循环-统一copy一次temp目录所有bin，正确 |
| 开始新读取-旧bin清理 | clearBinFiles始终清空-copy源干净-新目录无污染 |
| 开关打开-导出数据 | exportData正确识别_currentSaveDir-从新目录导出 |

**踩坑 / 已知异常与失败经验**: 技术债务清单：1. 冗余方法：getReadoutDataSaveDir()未被所有分支直接调用，可后续统一改为调用该方法
1. 串行copyFile：stopReadout中复制文件使用串行for循环，可用Promise.all并行（文件数通常<10）
2. 原有写法不规范：version.js:310-311的this.systemIntegration写法（非本次引入）

**关键文件与接口**: | 文件 | 修改内容 | 关键行 |
|------|---------|-------|
| components/global.js | preferences新增saveReadoutData字段 | L190-L193 |
| components/analyzer/version.html | 新增2个setting-item（开关+目录选择） | L77-L90 |
| components/analyzer/version.js | 本地变量/写回/初始化/chooseSaveReadoutDataDir方法 | L39-L40, L286-L287, L327-L328, L342-L356 |
| components/i18n.js | 新增9个翻译键 en+zh 双语 | L413-L421(en), L988-L996(zh) |
| components/encoder/device.js | 新增2方法 + 修改7方法的路径切换逻辑/async改造 | L819, L892-L1124, L2284-L2289 |

**状态**: 已完成

### F-007: IAP升级移除SN格式校验（保留必填）
**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**关键词**: IAP升级, SN序列号, 格式校验移除, 必填校验, Vue2, i18n, placeholder

**需求场景 / 现象**: R001-R002
IAP升级不需要校验SN的录入规则，但是需要录入SN
```
IAP升级不需要校验SN的录入规则（原格式：3个字母+3个数字），但SN仍需录入（必填）。
```

**方案 / 实施步骤**:
技术方案：| 项 | 说明 |
|----|------|
| 修改位置 | components/share/iap.js startIAP() L266-272 |
| 必填判断 | if (!this.iap.sn) 报错 return（空串/null/undefined 均拦截） |
| 校验顺序 | iap文件(L258) -> SN(L266) -> 目标版本(L275)，逐级短路 |
| 旁证 | device.js:3206 validateSN() 此前已被产品确认改为 return true（方向一致） |
【验收标准】- [x] 移除 startIAP() 中 SN 格式正则校验 /^[a-zA-Z]{3}\d{3}$/ 及"SN格式错误"报错
- [x] 恢复（取消注释）SN 必填校验：为空时报"请输入编码器SN"并 return 阻止升级
- [x] SN 传递链路不变：handleIap() 中 options.sn = this.iap.sn -> EncoderCommandIapStart(命令码60)
- [x] 升级成功清空SN / 失败保留SN（重试匹配）的原有生命周期不变
- [x] iap.html placeholder 去除旧格式示例"如 abc123"误导
- [x] i18n 中英文区新增 "SN": "SN" 键
【关键决策与理由】| 决策项 | 选择 | 理由 |
|--------|-----|------|
| 必填校验实现 | 恢复原注释代码而非新写 | 原代码逻辑正确，恢复即最小改动 |
| i18n旧文本 | "SN格式错误..."翻译键保留未删 | 避免影响潜在引用，无副作用 |
| 不加trim | 纯空格" "可通过 | 超出用户需求范围，记录为技术债务 |
【SIRE执行记录】- 角色1：定位 startIAP() 为核心修改点；角色2：确认R001/R002同文件，跳过角色4并行
- 角色3：单处修改；角色5：审查通过（格式校验无残留、传递链路完好）
- 角色6：测试通过；④.5轻微修复：placeholder文案与i18n
- 角色7：交付确认通过
【修订内容】F-007 技术债务#1 已修复。components/share/iap.js startIAP() L266 必填校验由 if (!this.iap.sn) 加强为 if (!this.iap.sn || !this.iap.sn.trim())，纯空格SN（" "）现被正确拦截报"请输入编码器SN"。
【安全性】!this.iap.sn 短路在前，null/undefined 不会调用 .trim()，无 TypeError 风险；含实际内容的SN（如" abc "）仍放行并按原样传递。

**验证方法**: - node --check iap.js / i18n.js 均 exit 0
- 4项预期行为推演通过：SN空-拦截；SN任意内容-放行；文件未选-报错；版本未选-报错
- SN传递链路确认完好（handleIap L125 -> encoder.set L151）
node --check exit 0。

**踩坑 / 已知异常与失败经验**: 技术债务清单：1. 纯空格SN（" "）可通过必填校验，建议后续 if (!this.iap.sn || !this.iap.sn.trim()) 加强
1. SN含特殊字符时后端/固件兼容性未验证，建议联调补测

**关键文件与接口**: | 文件 | 修改内容 | 关键行 |
|------|---------|-------|
| components/share/iap.js | 恢复SN必填校验（取消注释原L266-272），删除SN格式正则校验（原L274-281） | L266-272 |
| components/share/iap.html | placeholder 从 $t('SN (如 abc123)') 改为 $t('SN') | L36 |
| components/i18n.js | 英文区L618、中文区L1335各新增 "SN": "SN" | L618, L1335 |

**状态**: 已完成

### F-008: IAP升级进度专用progress_sender参数贯通
**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**关键词**: IAP, 升级进度专用, progress_sender, 参数贯通, Encoder.py, IAP.py

**需求场景 / 现象**: IAP升级增加专用于显示上传进度的方法，不覆盖msg_sender，独立参数传递

**方案 / 实施步骤**:
修改：Encoder.py L363/L376 lambda加progress_sender=progressSender；IAP.py uploadApp/uploadAppDataV1/uploadAppDataV2签名加progress_sender=None+回退msg_sender（兼容）；两处[IAP_PROGRESS]进度行改用progress_sender，msg_sender其他用途（错误/状态消息）不变
【传递链】Encoder.py stepTwo progressSender(=msg_sender) -> lambda闭包 -> uploadApp(progress_sender) -> uploadAppDataV1/V2(progress_sender) -> [IAP_PROGRESS:xx]消息行
【关键决策】progress_sender默认None回退msg_sender，所有旧调用方行为不变；进度消息与普通日志分离，后续前端可单独消费

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-009: IAP失败清除SN+重试通道SN自动还原
**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**关键词**: IAP, 失败清除, SN, 重试通道, 自动还原, iap.js

**需求场景 / 现象**: IAP失败时清除SN（输入框清空）；重试不校验SN，SN自动还原

**方案 / 实施步骤**:
修改：（components/share/iap.js）:
1. handleIap catch分支：失败时 this.iap.sn = null（原注释"失败保留SN供重试比对"的机制废弃）
2. 重试按钮click：删除SN比对校验（原"设备序列号不匹配"拦截逻辑），改为 if (message.data.sn) this.iap.sn = message.data.sn 从flow-control消息还原SN
设计逻辑：失败清SN（UI强制清空，防操作员误用旧SN）→ 重试时后端flow-control消息携带sn自动还原 → handleIap options.sn带正确值重试 → 重试失败再清空（可循环重试）。仅更新app模式（message.data.sn为空）不还原，options本就不传sn，不受影响。

**验证方法**: node --check通过；5场景推演自洽（首次失败/重试/循环重试/updateAppOnly/成功）

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-010: 导入调试数据【使用当前配置】覆盖 + 绘图方式默认后端
**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**关键词**: 导入调试数据, 使用当前配置, 覆盖, 绘图方式默认后端, global.js, device.js, Encoder.py, store默认值global.js

**需求场景 / 现象**: 原记录未记载

**方案 / 实施步骤**:
【功能1：使用当前配置（仅内部版）】- UI: 绘图方式下方开关，？提示"打开之后，导入调试数据的时候，将使用当前页面的配置信息覆盖文件里面的配置信息"
- 链路: global.js useCurrentConfig状态 -> device.html开关 -> device.js modes下发(外部版强制false) -> Encoder.py _prepareRecalibrationArguments
- Python关键实现: jsonData被文件内容替换前快照外部配置(_externalJsonData)+读取标志 -> 文件加载后 if _useCurrentConfig: jsonData.update(外部配置) -> debug/write仍强制False(安全项) -> plot(内部版)/plotRenderMode始终以外部的为准
- 配套日志: logging.info打印配置来源(页面覆盖/调试文件)+生效配置JSON，便于追溯
【功能2：绘图方式默认后端】- 移除localStorage持久化(mounted恢复+toggled保存)，每次启动重置为backend
- store默认值global.js plotRenderMode: 'backend'

**验证方法**: - isReadFromFile()门控: getEncoderData跳过self.enter()，所有数据getter(getDPTHallParamOuter等)从调试文件读取
- debug/write在覆盖后仍强制False -> 不写编码器
- setProxyProtocol仅设本地标志(proxyProtocol/canOpenProxy.setLog/setIsFD)，无总线I/O
- 覆盖仅改配置值不改控制流，交互保证来自既有门控

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-011: EncoderPlotter 国际化(i18n)全面修复
**日期**: 2026-09-02
**项目**: EncoderPlotter_0703_01
**关键词**: EncoderPlotter, 国际化, i18n, 全面修复, 涉及mes-config.js, device.js, iap.js, i18n.js, 正则提取全部.js, threshold.html, selector.html, flash_tool_v2.py

**需求场景 / 现象**: i18n（i18next，key 为中文，en/zh 双包，fallbackLng='en'）：en 模式显示中文、插值信息被吞、中文模式 fallback 英文等显示问题。

**方案 / 实施步骤**:
【问题模式与修复方案】（i18next，key为中文，en/zh双包，fallbackLng='en'）：
1. **双包缺失key**（代码用$t但包中无，en模式显示中文）：补en/zh双包约102个key。覆盖：设备消息、threshold.js阈值提示7条、selector.html读取器配置5条、device.html设备面板9条、serialPermissionNotice.js串口权限11条、HTML硬编码改造30+条
2. **动态key拼接**（$t("前缀"+变量)或模板字符串，永远匹配不到包内key）：改为静态key+插值。涉及mes-config.js:330、device.js:3149、iap.js:68，语言包值加{{fields}}/{{oldSerial}}/{{step}}占位符
3. **JS对象重复key**（后者静默覆盖前者）：清理13处。典型：en包"读取字长"重复导致selector.html显示"Readout Byte Length: "空插值
4. **en/zh包key不一致**：zh包key多一个"和"字导致中文模式fallback英文（违反"中文模式不得显示英文"硬约束）；en包缺"解析名称"导致英文模式显示中文
5. **插值参数丢失**：代码传{port}/{name}但翻译值无占位符，信息被吞
6. **HTML硬编码中文**（英文模式显示中文）：6个HTML文件约50处改$t()（部分位于HTML注释块内，无害且解除注释即i18n就绪）
7. **窗口标题硬编码**：main.js按resolvedLanguage切换中英文标题
【2026-09-03 | flash_tool_v2.py 增加步骤级操作日志】- 需求: 用户需要看到烧录V2流程执行到哪一步（此前中断时只有 traceback，无法定位）
- 实现: 新增 stepLog(name)/stepDone() 两个 helper（模块级 _currentStep/_stepStartTime 追踪）
  - stepLog: 进入新步骤时输出 [步骤名] 开始 并计时
  - stepDone: 输出 [步骤名] 完成，耗时 X.Xs
- 接入点: 初始化.编码器连接 / step0.压合电磁阀 / step1.解锁芯片加载calibration / step2.采集数据(或从文件加载) / step3.partition / step4.calibration / step5.评估 / step6.生成CFiles / step6.1.写入Flash(子步骤)
- 异常中断: except 分支输出 流程异常中断于 [当前步骤名]，精确报告中断位置
- 验证: py_compile 通过; 冒烟测试(-3 -f 不存在文件)确认输出 [step2.从文件加载数据] 开始 → 流程异常中断于 [step2.从文件加载数据]
- 日志经 logger(stdout) → Node onProgress 转发到前端面板，UI 可实时看到步骤进度
【2026-09-03 | flash_tool_v2.py 主流程完整参数日志】- 需求: 用户需看到每一步拿到了哪些参数、每个步骤调用传入了哪些参数
- 实现:
  8. 入口总览块（argv / startIndex 解析结果 / 双轴标志 / 全部关键 config：serial/version/algorithmVersion/model/批次/isAuto/PLLSource/OutputMode/PROJECT_NAME/传感器/三大路径 / skip-generate、no-write-flash flags）
  9. 每个调用点前置日志: 调用 X.main(参数=值, ...)；返回值打 OK/None 或 shape 摘要
  10. _ds_desc 统一在 step2 后定义（避免 -4/-5 启动跳过 step3 时 NameError）
- 覆盖调用点: Analyzer()/EncoderBase()/powerOn()/recail.enter()/sol.main/load.main/collect.main/partition.main(内外圈)/calibrate.main(内外圈)/evaluate.main(内外圈)/generate.main/recail 写入系列
- 验证: py_compile 通过; -3 --skip-generate 冒烟运行，入口总览与各步传参日志完整输出
- 遗留发现: finally 中 encoder.recail.exit() 报 'Recalibration' object has no attribute 'exit'（仅 warning 不阻塞，待修）
【2026-09-03 | 界面转子内径自动匹配 station.py 传感器配置】- 需求: station.py 的 InnerConfigs/OuterConfigs 固定为 Configs15/Configs20，需按界面选择的内/外转子内径自动匹配 configMBP.ConfigsN
- 实现（三处）:
  11. flashPanelV2.js: flashFirmwareV2 调用传 innerSize=modelConfig.innerRotorId, outerSize=modelConfig.outerRotorId（'15'/'15B' 等原始值）
  12. factoryAutomation.js flashFirmwareV2: 转发为命令行 --inner-size / --outer-size
  13. flash_tool_v2.py _applyRotorSizes(argv)（在 import config 之前执行）: 解析参数取数字（'15B'→15），行锚定正则改写 station.py 的 InnerConfigs = configMBP.ConfigsN 单行（兼容 GUI 行锚定正则），N<10 补零（5→Configs05）
- 关键时序: 改写必须在 import config 之前——station.py 是磁盘配置，import 后值固化到 config 命名空间
- 验证: --inner-size 10B --outer-size 15 → station.py 两行被替换、config 导入 Inner=10/Outer=15 PASS；测试后已还原 15/20
- 边界备注: DPT5 特例 Configs10_DPT5 不在通用规则内（保持手改）；单轴系列 Inner=Outer 别名同样保持手写
【2026-09-03 | 界面可选 hex/IAP 固件文件（覆盖默认 JFlash 路径）】- 需求: IAP/hex 文件应从界面选择，而非固定用 JFlash 默认路径
- 实现（三层）:
  14. flashPanelV2.html: 新增"APP 固件 (hex)"与"IAP / Bootloader (hex)"两个文件选择组（选择/清除按钮，样式同数据文件选择）
  15. flashPanelV2.js: data 加 hexFilePath/iapFilePath（localStorage 持久化），selectHexFile/selectIapFile/clearHexFile/clearIapFile 方法（ipcRenderer select-file，hex 过滤器），flashFirmwareV2 传 hexFile/iapFile
  16. factoryAutomation.js: 转发为命令行 --hex / --iap
  17. finalstep0_loadHex.py main(): _argValue('--hex'/'--iap') 解析后用 dataclasses.replace 生成新 cfg 覆盖 hex_path/extra_hex——replace 而非直接赋值，避免污染模块级共享配置表（跨调用残留）
- 不选时行为不变：使用 _SERIES_SPEC 规格表默认 JFlash 路径
- 验证: --hex/--iap 实测路径正确生效、烧录上下文日志正确显示覆盖后路径、共享表前后一致；且验证运行时第2次尝试烧录实际成功（探头已接）
【2026-09-03 | flash_tool_v2 代码审查重构 + collect_v2 COM口自动扫描】- 审查发现并修复:
  18. 重复 stepDone: step6.1 内部与 step6 块尾各打一次（_currentStep 已变 step6.1，重复输出）→ 只保留块尾
  19. 三段重复 Flash 写入 try/except（4060 两项/旧版三项结构相同）→ 抽 _writeFlashData(encoder,res) helper，items 按算法版本构造
  20. heights 死变量（定义后无引用）删除
  21. numpy/pathlib import 散落在流程中间 → 提顶部
  22. res None 且 encoder 连接时无日志 → 补 warning
  23. stepLog 后紧跟同文本冗余标题行全部删除（stepLog 已输出 [name] 开始）
- COM26 写死问题（用户要求自动扫描）: finalstep0_collect_v2.py 的 PORT="COM26" 改为 _resolvePort()——--port 显式指定 > VID(0x6B6B)/PID(0x0001) 自动扫描；延迟到 collect() 内解析（模块导入不碰串口，-f 文件加载场景设备未插不炸 import）
- 'Analyzer' object has no attribute 'server' 修复: EncoderBase.py newMsg()/messager() 加 getattr(self.analyzer,'server',None) 守卫，无 server 时降级 logging.info 输出——单机模式（产线烧录脚本直接用 Analyzer 无 WebSocket Server）下 enter() 不再被消息推送炸掉，报错回归真实硬件原因
- 验证: py_compile 三文件通过; -3 -f 不存在文件 冒烟——日志无重复、server 错误消失（显示真实原因: Enter Recalibration Mode Failed 请查接线）
【2026-09-03 | 采集过程逐帧日志从界面日志框移除】- 需求: 采集过程（finalstep0_collect_v2 链路）的逐帧调试日志不需要显示到界面
- 来源定位: AnalyzerDual.py 四处逐请求/逐帧 logging.info（Request.received 打数据、addRequest 打请求ID、readThread 打包长、sendCommand 打 'pass'）+ readThread 逐帧 print(triggerData) + Recalibration 调试 print('vdata'/'getting')
- 修复: 全部删除（纯调试残留，无逻辑作用）；resolvepackages 解析校验保留
- 效果: 界面日志框采集期间只剩 stepLog 步骤行与 collect.main 返回摘要，不再被 1/8/b'..'/pass 刷屏
【2026-09-03 | _connect_encoder 职责拆分：连接与进入再标定解耦】- 需求: 连接读取器不必每次都进再标定，是否进入跟场景相关
- 实现: _connect_encoder(enter_recali=True) 参数化——函数只负责 连接+上电+串口校验
  - 初始化阶段 enter_recali=True（默认）：烧录前固件在跑，需再标定态
  - 采集后重连 enter_recali=False：采集驱动退出时已让固件离开再标定；step6 写 Flash 前 ensureInRecalibrationMode() 自会按需进入，无需重复
【2026-09-03 | 烧录V2 界面：先选产品系列再选固件版本】- 需求: 交互顺序应为 先选择产品系列 → 再选择固件版本（版本随系列联动）
- 实现:
  24. flashPanelV2.html: 产品类型上移到第一位，固件版本紧随其后（原版本在最顶部）；版本下拉在 optVersions 为空时禁用并提示"请先选择产品类型"
  25. flashPanelV2.js 'modelConfig.version' watcher 加校验: 版本不在当前系列 versions 内（localStorage 残留旧系列值）时重置为 default_version 并 return（重置值再次触发 watcher 完成后续联动）
- 既有联动保持: 切系列 watcher 已置 version=default_version；optVersions 本就按 seriesMeta.versions 生成
【2026-09-03 | step6 写入过程说明与 startProcessAngle finally 修复】- 用户疑问: step6 缺少往编码器写入数据的过程（ANGLEDATAS/POLYFITS/SLOWPOLYFITS）
- 说明: 写入过程未丢——重构时抽入 _writeFlashData(encoder,res) helper（flash_tool_v2.py L184），主流程 L547 调用；内容与 finalstep_from_data.py 逐行对应
- 修复（对照参考文件的差异）: startProcessAngle() 从成功路径末尾移入 finally——写入中途异常也恢复角度处理，否则固件停留在 stopProcessAngle 状态（参考实现正是放在 finally）
- 备注: 用户已手改 output_mode 默认值为 'bytes'（原 config.OutputMode）

**验证方法**: （可复现）：临时Node脚本模拟window后require components/i18n.js，用getResourceBundle('en'/'zh','translation')取双包：(a)key集合差集比对 (b)正则提取每个包区域源码检测重复key (c)正则提取全部.js/.html的$t('静态key')逐一验证双包存在 (d)t()传参验证插值输出。注意：HTML中$t('...\n...')的\n运行时由JS解析为换行，与包内解析后key一致，源码文本级比对会假阳性。

**踩坑 / 已知异常与失败经验**: 技术债务：threshold.html:93的$t('')空key（无显示危害）；device.js后端动态msg（已有zh/en三元机制）；selector.html:527的$t(unit)动态单位；注释块内$i18n改造待解除注释后生效。

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-013: 从 origin/develop 干净重合并 MPT-G QGC 并补齐 V402 配置
**日期**: 2026-09-14
**项目**: EncoderPlotter3
**关键词**: MPT-G, MPT-QGC, V402, InitArguments_MPT_QGC_V5, gitlink, merge

**需求场景 / 现象**: 重新从 `origin/develop` 创建新分支，合并 `origin/feature/support-mpt-qgc`；以 develop 为基础解决冲突，不能遗漏 arguments 结构体；包含子仓提交并 push。

**方案 / 实施步骤**:
方案要点：
根仓源分支已在 develop 历史中，不能只用根仓空合并判断完成；对 gitlink 分叉的 `sub_common` 与 `sub_embedded` 分别从 develop 指针创建同名分支，使用真实 merge 保留 develop 基线并补入源分支。冲突复核额外检查了结构体字段、协议布局和调用方；`sub_algorithm`、`sub_automation` 无目标分支，按纯消费者/无变更规则保持原 develop 指针。

**验证方法**: - [x] 根仓 `feature/mpt-g-remerge` 从 `origin/develop` 创建，根仓未携带旧 `feature/mpt-g` 独有提交。
- [x] `sub_common` 包含 `InitArguments_MPT_QGC_V5`、`FunctionArguments_MPT_QGC_V5`、MPT V4 发布字段及 MPTQGC V402 配置（算法 4060，AngleData `0x08031800`，Polyfits `0x08005000`）。
- [x] `sub_embedded` 包含 MPT-QGC 参数读取、版本格式化、function arguments、更新写回、Hall 超时和数据写入分支。
- [x] 两个子仓以 develop gitlink 为第一父、`origin/feature/support-mpt-qgc` 为第二父完成 merge 并先 push；根仓随后锁定 gitlink 并 push。
- [x] Python 回归通过：10 + 7 + 26 + 120 项。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: - `controller/python/sub_common/DataFormatter.py`
- `controller/python/sub_common/config.py`
- `controller/python/sub_common/utilities.py`
- `controller/python/sub_embedded/EncoderBase.py`
根仓提交 `0963c5ca`；sub_common merge `25a372a5`；sub_embedded merge `723c1978`；子仓分支名 `feature/mpt-g-remerge`；根仓远端分支 `feature/mpt-g-remerge`。

**状态**: 已完成

### F-017: EncoderPlotter_0703_01 IAP 后恢复 SN 必须设备回读校验
**日期**: 2026-09-15
**项目**: EncoderPlotter_0703_01
**关键词**: IAP, statorSN, arguments, EncoderCommandCalibrationRewriteArguments, 回读校验, SN一致性

**需求场景 / 现象**: IAP-SN-ARGUMENTS-RESTORE
已写入 SN 的编码器执行正常 IAP 后，固件升级流程可能重建 arguments 并丢失 `statorSN`。上位机需要在 IAP 成功后使用升级前实际请求的 SN 重写 arguments，并验证设备回读值与请求值完全一致。

**方案 / 实施步骤**:
技术方案：前端 `components/share/iap.js` 在 IAP 请求前保存实际 SN；正常 IAP 成功后复用 `EncoderCommandCalibrationRewriteArguments` 写入 `{statorSN, exitAfterWrite:true}`，只有设备返回的 `statorSN` 完全一致才同步前端缓存。恢复失败单独记录错误并保留 SN 供重试；`updateAppOnly` 不触发该流程。

**验证方法**: - [x] `node --check components/share/iap.js`
- [x] `git diff --check`
- [x] Node 桩对象验证写入参数、回读一致同步缓存、回读不一致报错。
- [ ] 真机 IAP：需连接读取器与已写入 SN 的编码器执行。

**踩坑 / 已知异常与失败经验**: 【原状态说明】已完成（代码与自动化验证通过，真机验收待硬件环境）

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-018: 固件 Flash 布局规范（Bin Footer FLYT / 标定 'i' 指令）对上位机影响分析
**日期**: 2026-09-15
**项目**: EncoderPlotter_0903_01
**关键词**: Flash布局, Bin Footer, FLYT, 'i'指令, RecalibrationLayoutInfo, IAP_MUST_PRESERVE, 剥footer, bin文件过大, 1984包, DATA_ADDRESS_LAYOUTS, P/Q/T, V3100

**需求场景 / 现象**: 分析固件组交付的《Flash布局信息追加规范.md》(v1.1) 与《标定模式Flash布局查询规范.md》(v1.0)，对照 feature/iap 现有代码评估影响。

**方案 / 实施步骤**:
方案要点：
- 高危：固件 v1.1 已在 Finish-FirmwareBuild 自动追加 212B footer（加密前），上位机 IAP 解密后整份流式下发（IAP.py uploadAppDataV2 无剥尾）；满片 bin(0x7C000=1984×256 包) 会被 `total_packages >= 1984` 拒为“bin文件过大”，非满片则 footer 写入 Flash。上位机须先上线“剥 footer：image=bytes[0:blockStart]”。
- IAP_MUST_PRESERVE 在流式 BootLoader（首包 5BB5 整片擦除、无地址字段）下上位机无法执行“跳过”，只能校验，需固件组确认执行主体。
- Footer/'i' 只给区域起点与大小，推不出双圈 inner 指针（DPT 401+ inner 0x08012834/0x08029800），不能替代 DATA_ADDRESS_LAYOUTS，定位为交叉校验源；规范地址与 DPT 401+ 一致、与 MPT 420+ 不同。
- 'i' 可替代 EncoderBase IAP_PARAMS_REGION_SIZE/IAP_ANGLEDATAS_REGION_SIZE 硬编码；'T' flashSize 含 2KB 擦除余量，不能拿来做补齐长度。挂 V3100 族 P/Q/T 路径，ord('i') 无冲突。
- 规范疑点：footer 超 schema“人工确认继续” vs 8.2/'i'“直接拒绝”口径矛盾；blockLength<=0 对 uint32 无意义。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: parse_iap_bin.py、sub_embedded/IAP.py、Encoder.py、sub_embedded/EncoderBase.py、sub_embedded/DriverBase.py、sub_algorithm/step4_GenerateV3100.py
.sire/runs/R20260915-114832/analysis-report.md

**状态**: 已完成

### F-019: driverSoftware 舵机软件仓库开发、合并、发布与打包规范
**日期**: 2026-09-15
**项目**: driverSoftware（KingKong 感驱一体舵机 PC 控制软件）
**关键词**: 舵机, driverSoftware, development, feature, fix, merge, no-ff, release.py, VERSION, CHANGELOG, Nuitka, electron-builder, SKU, customer-L0, customer-L1, internal, 混源守卫, 构建门禁, 实机验证, 新需求开发

**需求场景 / 现象**: ANALYSIS-SERVO-REPOSITORY-WORKFLOW
重新识别当前代码仓库，沉淀后续“舵机怎么开发新需求 / 怎么合并 / 怎么发布 / 怎么打包”的规范知识。

**方案 / 实施步骤**:
【当前基线】- 当前工作分支：`development`，工作区干净，HEAD 为 `v0.10.1` 发布提交。
- 当前版本唯一来源：根目录 `VERSION`；Electron 的 `package.json` 与 `package-lock.json` 已同步为 `0.10.1`。
- `dev`、旧版 `docs/BRANCHING.md` 和早期 `0.1.x` 版本规则属于历史线，不能覆盖当前 `development` 线规则。
【规范结论】1. 需求先阅读项目代码、依赖、测试、历史决策和对应模块 skill；复杂需求先形成 spec/plan，再拆成可验证的小单元。
1. 新开发分支从 `development` 创建，命名使用 `feature/*`、`fix/*`、`docs/*`、`chore/*`、`release/*`。
2. 功能分支回 `development` 使用描述式 `git merge --no-ff`，保留分支形状；发布分支冻结后只接收发布修复和 CHANGELOG。
3. 用户可见变化写入 `CHANGELOG.md` 的 `## [未发布]`，日常提交禁止手工 bump 版本；发布统一执行 `python scripts/release.py <版本号>`。
4. 发版脚本必须先校验 CHANGELOG、执行完整构建，构建成功后才 bump `VERSION`、截断 CHANGELOG、提交发布记录并创建 `vX.Y.Z` tag。
5. 发包必须使用 `scripts\\build.bat --release --customer`，不能用已删除或仅复用旧产物的快速路径。
6. 打包流程是 Nuitka 编译 `server.py` 一次，再用 electron-builder 按 SKU 打包；SKU 包括 internal、正式包、customer-L1、customer-L0。
7. 客户包剔除内部文档、CHANGELOG、算法源码、开发档案等，并在真实 `win-unpacked/resources` 内容上执行构建后门禁；门禁失败即不可分发。
8. 构建期间 HEAD 变化会判定产物为混源并隔离，禁止命名、打 tag 或发布。
9. 内部包成功后自动创建本地 `internal/vX.Y.Z+<sha>` tag；正式发布 tag 为 `vX.Y.Z`。默认不自动 push，除非用户明确要求。
10. 发布前必须完成提交与 CHANGELOG 对账、软件验证、完整构建、客户包门禁，以及连接设备、MIT、Scope、清故障等必要实机验证；协议/寄存器改动还要确认固件兼容。
【代码与产物链】`frontend/Electron → FastAPI server.py → core commands/protocol → reader/HID → Analyzer → RS485 → STM32G473`。
开发态通常从 `start.bat` 启动 Web 后端；打包态由 Electron 启动 `resources/server/server.exe`。Windows 后端默认由 Nuitka 产出 `dist_app/server.dist/server.exe`，Electron 产物进入 `electron/dist/`。

**验证方法**: - `git status --short --branch`：`development...origin/development`，工作区干净。
- `git log`：HEAD 为 `v0.10.1`。
- 已直接读取 `AGENTS.md`、`docs/PACKAGING.md`、`README.md`、`server.py`、`electron/package.json` 和 `scripts/build.bat`。
- 已执行 SIRE 向量检索；已执行 R9 preflight，结果 `PASS`。
- 未执行完整 Nuitka/Electron 构建，未连接实机；本条目是基于当前源码和规范文件的静态仓库分析。

**踩坑 / 已知异常与失败经验**: 【原状态说明】已完成（规范知识归档）

**关键文件与接口**: - `AGENTS.md`：当前分支、VERSION、release.py、构建和门禁硬规定。
- `docs/PACKAGING.md`：多 SKU、内容剔除、构建后门禁和发布流程。
- `scripts/build.bat`：实际构建、SKU 顺序、混源守卫和门禁实现。
- `scripts/release.py`：版本更新、构建成功后提交与 tag 的发布入口。
- `server.py`、`electron/package.json`：后端入口、Nuitka pragma 和 Electron 打包配置。

**状态**: 已完成

### F-020: driverSoftware 算法仓库与打包产物边界核查
**日期**: 2026-09-16
**项目**: driverSoftware（舵机 PC 控制软件）
**关键词**: 舵机, 算法仓库, recalibration, sub_algorithm, kingkong_calib, wheel, pyd, pyc, Nuitka, force_calib, internal, release, customer-L1, customer-L0, 算法源码不进包, 派生运行产物

**需求场景 / 现象**: ANALYSIS-SERVO-ALGORITHM-PACKAGING-BOUNDARY

**方案 / 实施步骤**:
结论：当前仓库**不打包算法源仓库本身**。算法源（recalibration / sub_algorithm 等）按 `docs/PROJECT-CONTEXT.md` 和 `tools/build_algo_whl/README.md` 单独管理，不进 driverSoftware；重建算法 wheel 需要在算法工作区完成，再把生成的 `vendor/kingkong_calib-*.whl` 带回本仓库。

但当前仓库会打包算法的**派生运行产物**：
- Windows Nuitka 通过 `server.py` 的 pragma 显式收进 `kingkong_calib`、`kingkong_calib._algo`、`_common`、38 个子模块和模板数据。
- 这些内容来自已安装的 `vendor/kingkong_calib` wheel；核心算法主要是 `.pyd` 机器码，非算法接口/数据部分可能是 `.pyc`，不是算法源树。
- `tools/force_calib/*.py` 是本仓库内的台架/力感知标定脚本，不是外部算法源仓库；Nuitka 以 `--include-data-files` 收进初始 `server.dist`，构建脚本会直接检查实物是否在位。
【SKU 边界】- internal：内容最全，包含编译后的 `kingkong_calib`、台架脚本、dev 档案、内部文档等，禁止发客户/产线。
- release：剔除 `dev-*.json`，但不等于剔除所有算法运行能力。
- customer-L1/L0：在正式包基础上剔除 `docs/skills`、CHANGELOG、出厂 npz、内部 guide，以及 `tools/force_calib` 明文脚本；L0 进一步剔除 trajectory guide，并写入 `MAX_UI_LEVEL=0`。客户包仍保留诊断和被允许的编译运行组件。
【重要区分】“算法仓库是否被打包”若指源代码仓库：否；若指算法运行能力：Windows internal/release 通过 `kingkong_calib` wheel 的编译派生物提供；若指本仓库明文台架算法脚本：初始构建产物有，customer 包明确删除并由门禁验证。

**验证方法**: - 已执行 SIRE 向量检索并命中 F-019。
- 已直接读取上述当前分支文件和构建脚本。
- 已确认当前分支为 `development`、HEAD 为 `v0.10.1`、工作区干净。
- 未执行完整构建；本次结论为静态配置与脚本逻辑核查。

**踩坑 / 已知异常与失败经验**: 【原状态说明】已完成（边界澄清并归档）

**关键文件与接口**: - `docs/PROJECT-CONTEXT.md` §2、§5：相邻 `recalibration` 仓库按逻辑名配置，本机路径不进仓。
- `tools/build_algo_whl/README.md`：算法源独立管理，wheel 是带回本仓库的边界产物。
- `server.py` 头部 Nuitka pragma：算法包、模块、模板与 `tools/force_calib/*.py` 的收包规则。
- `scripts/build.bat`：internal/release/customer 的顺序、`force_calib` 实物检查、客户包剔除和门禁。
- `electron/package.json`：将 `dist_app/server.dist` 作为 `resources/server` 打入 Electron 包。

**状态**: 已完成

### F-021: EncoderPlotter 再标定霍尔测试脚本零依赖单文件化
**日期**: 2026-09-17
**项目**: EncoderPlotter_0703_01
**关键词**: EncoderPlotter, 再标定, recalibration, 霍尔, hall, 单文件, 零依赖, standalone, pyserial, Analyzer, EncoderReadoutConfig, CRC8, singleRead, 协议复制, 技术债

**需求场景 / 现象**: controller/python/test.recalibration.hall.py 拷到别的目录/电脑就报 No module named 'sub_common'。
要求抽离全部项目依赖，做成只靠 pyserial 的单文件脚本，仍支持 enter / exit / h / H 四个 action。

**方案 / 实施步骤**:
原记录未记载

**验证方法**: - 交叉核验脚本：同时 import 主仓模块与独立版，比对 5 个结构体 sizeof、500 组随机 CRC8、
  singleRead 三种命令(h / v读内存 / ER)的下发字节流、enter 时序 4 个 config 字节流、
  readout / encoderStatus / USBDataHeader 字节流、resolvePackages 结果 —— 14 项全 PASS。
- 实机（读取器 serial=20260420173117 @COM3）：FrameID 取回 -> enter 得 v=b'SUCCESSFUL' ->
  h 连读 3 次各 1 样本 18 个霍尔 CRC 通过 -> H 连读 3 次回 46 字节原始帧 -> exit 正常。
- 边界：无效 action 被拒、q 退出且 finally 关串口。

**踩坑 / 已知异常与失败经验**: 1. EncoderReadoutConfig 的 commands / data / crc **不是 ctypes 字段**，是运行时挂到实例上的
   普通 python 属性；setReadoutConfigs 用 hasattr 取它们拼成 followedData 跟在结构体后面。
   只照抄 _fields_ 会漏掉整个命令拼装逻辑。
2. request 是 union：byteLength(byte0) 与 uart.command(byte0)、uart.timeoutByteNum(byte1) 重叠，
   赋值顺序决定最终字节，照抄时必须保持源码顺序。
3. singleRead 里的 isFirstByteLongWait 在 RS485/Recail 路径上是死参数——uart 结构体只有
   command + timeoutByteNum 两个字段，它被挂成普通属性后从未被序列化。
4. H 帧长 46 字节（带角度字段）、h 帧 38 字节，resolveDualHalls 只认 38，H 必然解析为 0 样本、
   靠原始 hex 看数据。这是设计如此，不是 bug，别在这里打屏报警。
5. exit 发的 [E,R] 是复位命令，编码器**不应答**，返回 trigger 无数据是正常的。

**关键文件与接口**: controller/python/test.recalibration.hall.standalone.py（原文件保留，未进 git 不敢覆盖）
- 常量: sub_common/Defines.py 的 Control*/Device*/EncoderInterface*/EncoderCommand*
- CRC8 表与 calcCRC8: sub_embedded/CRC.py
- ctypes 结构体: sub_common/DataFormatter.py 的 USBDataHeader / TriggerInfo /
  EncoderRequestInformation / EncoderStatus / EncoderReadout / EncoderReadoutConfig
- 收发与枚举: sub_embedded/Analyzer.py（VID 0x6B6B / PID 0x0001，读线程按 requestId 匹配，
  ControlData 进 readBuffer 并按 packageNum 递减 readEventCount）
- 命令层: sub_embedded/EncoderBase.py 的 setReadoutConfigs / setReadouts / startAndReceive /
  singleRead / resolvePackages / resolveDualHalls / Recalibration.enter / getMemory / exitRecalibrationMode

**状态**: 已完成

### F-022: EncoderPlotter_0903_01 全项目架构与标定/IAP 产物语义基线
**日期**: 2026-09-20
**项目**: EncoderPlotter_0903_01
**关键词**: EncoderPlotter_0903_01, 标定, 再标定, IAP, 在线IAP, 离线IAP, P/Q/T, ced_Q, ced_T, ged_P, ged_Q, ged_T, 调试ZIP, kingkong.zip, _iapgen.bin, iapenc, IAPENC01, FLYT, flash layout, parse_iap_bin, DATA_ADDRESS_LAYOUTS, Arguments, FunctionArguments, HTTP IAP, SSE, flow-control, bootloader, MES, 产物语义, 复核边界

**需求场景 / 现象**: ANALYSIS-FULL-CALIBRATION-IAP-KNOWLEDGE-BASELINE
用户要求分析整个项目，特别是标定、IAP 等流程，解释每一个关键产物的含义，并记录到 SIRE 知识库。此次是当前代码快照的只读分析，没有修改业务代码、协议常量、子模块指针或发布配置。

**方案 / 实施步骤**:
【代码基线】分支 `feature/lingxi-dpt-iap-preserve-zero`，HEAD `7a6114a9c8cf19225e1ad8c6bddb525c7a6445ec`
【SIRE run】`R20260920-112827`
【总览结论】- 项目是 Electron main + Vue2/Vuex renderer + Python middleware 三层桌面应用。renderer 内的 `controller/server.js` spawn Python；Python `main.py → Server.py → Encoder.py` 控制读取器/编码器，HTTP/chamber 是共享核心或独立进程入口。
- JS↔Python 使用 18 字节 header + payload；`requestId=0` 是主动推送。IAP/标定的主要事件是 `iap:calibration-data-retrieved`、`iap:flow-control`、`PlainMessage` 和内部 `[IAP_PROGRESS:n]`。
- 标定链路是“MES/会话预检 → 进再标定 → 读 Arguments/现有数据 → 采霍尔/算法生成 → 按模式写 Flash → 启动角度处理 → 退出 → 调试 ZIP/MES 收尾”。Python AllInOne 对应准备、读取、采集生成、写入、退出五个阶段；导入 ZIP 用 `write=false`，dry-run 写入校验不进硬件。
【标定数据与调试 ZIP】- 新版算法（>=303）统一为 P=`PARAM_CONST`、Q=`ANGLEDATA_CONST`、T=`POLYFITS_DATA`；部分旧 DPB 仍有 M=`SLOWPOLYFITS`。旧算法（<=302）按 DPT/DPB/MPT/MPP 保存多块 angle/hall/group/polyfit。
- `ced_Q`/`ced_T` 是设备当前数据；`ged_P`/`ged_Q`/`ged_T` 是算法生成数据；`j72` 是 Arguments、`j99` 是 FunctionArguments、`j74` 是历史 P、`j70` 是霍尔采集、`j00/j01/j02` 是业务参数/modes/算法 options、`j03/j04` 是诊断日志、`snapshot` 是状态快照，`j75/j76/j77` 是旧数据族。ZIP 读取按前缀第一次命中，不保证取最新同名前缀文件。
- Flash 写入在 Footer/`i` 返回动态区域大小时按 P/Q/T 分别补 `0xFF`，超长失败；读回做长度/内容校验并带重试。Footer `FLYT` 含 P/Q/T region id/start/size/flags/CRC；有效 Footer 先剥离再解析，失效 Footer 不静默走旧逻辑；`must_preserve` 当前只是诊断标记，不代表上位机按地址跳过整区擦除。
【在线 IAP】1. Step 1 解密 App、解析 Footer 和 ARGUMENTS、按系列+软件版本查 `DATA_ADDRESS_LAYOUTS`、读取设备当前 P/Q/T、运行生成算法、缓存上传前 Arguments/Flash 布局/bin digest、保存 `ged_P` 并通过主动事件导出 IAP `.kingkong.zip`。
1. Step 2 进入 boot/IAP，编码器走 V2 的 `Protector` 分段上传。
2. Step 3 进入再标定，主要写目标 P，启动角度处理，读回 Arguments；DPT>=422、MPT>=420 只恢复允许的接口/模型/分辨率字段，返回实际软件版本和写回标记。

- 失败通过 flow-control 带 step/SN/session/ZIP 文件名，桌面 UI 可重试；普通 step>1 要求同设备、同 session、允许 step、同一固件 digest。`repair=true` 跳过普通 bin 结构/系列/版本/地址门禁，从 ZIP 恢复数据，是故障修复路径。
- 内部 App-only 直接解密上传 App，跳过 SN、目标结构、系列/版本和标定校验；HTTP 禁用。HTTP IAP 默认不挂载，需 `--http-enable-iap`；`iapVersion` 强制 2，step 2/3 只能消费桌面版导出的 ZIP，HTTP 不生成 ZIP。`jump-to-app` 恒 501，因底层 V1 形状与编码器 V2 不兼容。
- `parse_iap_bin.py` 按结构扫描而非写死 Arguments 地址：DPT 标准 128B，MPT/部分 DPT_V412 72B u32+u32，DPT_V401 是 u16+u16 特例，DPB 是 136B。软件 4.1.2 归一为 412；系列码 MBS 101、MBP 102、DPT 103、MPT 104、MPP 105、DPB 106、MPT-G 107。
- 地址表当前为：DPT 303–400 和 401+ 双圈两套，MPT 302–419 和 420+ 单圈两套，DPB 401–407 和 408+ 双圈两套，MPP 空布局。DPT_V401/V412 的文件名归属与 bin 内 series=104 的冲突必须用目标 `.map`/真机复核，不能只凭名称改表。
【离线 IAP 和产物】- 输入为 IAP 第一阶段调试 ZIP + 目标明文/可解密 BIN；必须取得 HallParam、ParamFit、`ged_Q`、`ged_T`。当前 HEAD 的关键修正是离线转换使用生成的 GED(Q/T)，不是设备当前 CED(Q/T)。
- command 64 调免标定算法生成新 P/Q/T，将它们写入 BIN 保留区，生成 `<base>_iapgen.bin`；这是合入数据后的明文中间产物。再做专用整体链式 AES，生成 `<base>_iapgen_<hex时间戳>.iapenc`；command 65 唯一消费 `.iapenc`。
- `.iapenc` = `IAPENC01` + little-endian 帧数 + 原始明文长度 + N 个 length/frame。每帧 16B IV + AES-CBC 密文；每包明文为 2B 包号 + 2B 大端 applenth + 256B 以内 payload + 1B CRC 占位 + 对齐。它与 `Protector` v2/v3 分段格式不同，知识库不重复记录源码中的密钥 literal。
- 整文件写入只支持直连：`6BB6` 开启、`5BB5` 整区擦除、首帧四次重试/`6AA60000`、`5CC5` 确认、后续 `5BB5+帧` 成组重试、进度推送、`5EE5` 收尾、`6FF6` 复位。verify 只解密还原、长度核对和 BIN/PQT/Arguments 解析；preview 只解析不写硬件。
- 5EE5/复位只证明协议阶段应答，当前上位机不做固件读回或内容 CRC 证明；目标 bootloader 的真实内容验证必须另做真机/固件仓核对。
【全项目风险与验证】- 已运行仓库指定测试：`build_info_test` 10 passed、`safe_name_test` 7 passed、算法配置测试 26 passed、`qa_api/tests` 120 passed（1 个弃用 warning）。这些不覆盖真实前端 handler、读取器、IAP 传输、目标固件、MES/chamber 联调。
- 三个巨石热区是 `components/encoder/device.js`、`controller/python/Encoder.py`、`sub_embedded/EncoderBase.py`；协议命令/事件双真源、DPT/MPT 版本布局歧义、ZIP 前缀首项匹配和 IAP 内容未验证是后续变更重点。
- 完整源码锚点、产物表、正常/异常流程、HTTP/并发、构建/外部边界和测试输出见本次运行档案：`@CODE_ROOT@/EncoderPlotter_0903_01/.sire/runs/R20260920-112827/analysis-report.md`；单元证据为同目录 `evidence-U-01.md` 至 `evidence-U-04.md`。

**验证方法**: - [x] 已对照当前 HEAD 源码完成架构、标定/再标定、恢复出厂、调试 ZIP、在线 IAP、离线 IAP、HTTP 和整文件传输分析。
- [x] 已完成五个只读分析单元；每个单元有实现者自测、R6A/R6B/R6C 初审、三路交叉核验、综合复核和独立测试证据。
- [x] 已通过 Python 工具/算法/HTTP 测试；未执行写固件、真机、MES 或 chamber 操作。
- [x] 已将当前事实、历史兼容项与待真机/固件确认项分层记录；未写入真实凭据或业务数据。

**踩坑 / 已知异常与失败经验**: 【原状态说明】已完成（知识分析与 SIRE 归档；无业务代码变更；真机/固件外部验证待后续）

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-023: 正式版本使用 tag 触发 CI Runner 构建
**日期**: 2026-09-20
**项目**: driverSoftware
**关键词**: driverSoftware, release.py, CI Runner, GitLab, tag, vX.Y.Z, build-win-release, build-mac-release

**需求场景 / 现象**: （据标题）正式版本使用 tag 触发 CI Runner 构建

**方案 / 实施步骤**:
方案要点：
正式发布入口 `python scripts/release.py <版本>` 默认只校验、同步版本文件、提交并创建本地 `vX.Y.Z` tag；推送分支和 tag 后，`.gitlab-ci.yml` 的 `test-gates`、Windows/macOS release job 在 Runner 上完成门禁、打包和 NAS 上传。`--local-build` 只用于本地预检，不代表正式产物。

**验证方法**: v0.13.2 已生成发布提交并推送 `development` 与 tag；远端 tag 满足正式 CI 规则。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: 原记录未记载

**状态**: 已完成

### F-024: AI工程化基建模板 — driverSoftware 全套工程/规则/打包/发布机制
**日期**: 2026-09-22
**项目**: driverSoftware (@CODE_ROOT@\driverSoftware, v0.13.10, 分支 development) — 新项目搭建时直接照抄的参考实现
**关键词**: AI工程化, 工程基建, 项目模板, AGENTS.md, AI规则, 打包, Nuitka, Electron, electron-builder, 多SKU, 发布, release.py, VERSION, CHANGELOG, GitLab CI, Runner, NAS, 飞书通知, 通讯架构, FastAPI, WebSocket, 多进程, shared_memory, venv, lockfile, workspace.json, pytest, 门禁, git flow, 分支命名

**需求场景 / 现象**: 新项目 (桌面端上位机 / Python 后端 + Web 前端 + Electron 壳) 搭建时, 按下列分层直接复刻。源文件都在该仓, 需要细节时去读对应文件。

**方案 / 实施步骤**:
【1. AI 规则体系 (三层文档, 分工明确)】- `AGENTS.md` = 怎么干活 (工程硬规定, 所有 AI 助手动手前必读); `docs/PROJECT-CONTEXT.md` = 协作上下文 (活从哪来/结论回填哪/相邻仓/真机台账/发布分发); `docs/skills/*.md` = 按模块的必读 skill, AGENTS.md 里用「模块 → 必读 skill」表强制映射。
- 硬规定骨架 (可直接抄): ①全程中文 ②每个可独立描述的改动单独 commit ③commit 不自动 push, 用户说推才推 ④commit 写 why ⑤写文档前命令/路径当场验证 ⑥不引用项目外绝对路径 (走 `~/.<proj>/workspace.json` 按逻辑名取路径 + vendor/ wheel + 环境变量) ⑦AI 不许假装跑过 ⑧证据没看完不许说无从下手 ⑨版本/CHANGELOG 发布纪律。
- 「工程军规」段: 每条都带「为什么 + 实际踩坑」, 如: 中文 commit 一律 `git commit -F 文件`; 源码扫描门禁先剥注释、写完人为破坏一次自证变红; UI 改动必须让真实数据流起来验证; 加 fail-fast 守卫前审计前置条件路径; 真机验收必须走可见 GUI; 对外文字说人话。
- 新协议命令落地顺序固定: protocol enum → commands 高层封装 → server endpoint → 前端 api.js → 页面接入, 每步单独 commit。
【2. 架构与通讯链】- Browser/Electron → HTTP/WS → FastAPI (`server.py` + `core/`) → `core/reader_*` → USB HID → 分析仪 → RS485 → MCU。
- 前端纯 ESM、无 build, 后端直接 serve `frontend/`, 改完 F5 生效。
- reader 双形态: `READER_MP=1` 多进程 (子进程独占 HID + GIL, 控制走 mp.Pipe, 数据走 shared_memory 无锁 SPSC 环形缓冲), `READER_MP=0` 进程内; 两者 API 必须同签名 (曾因只改一边导致 500)。打包版默认 MP=1, 开发 start.bat 置 0 → 打包版问题先设 MP=1 复现。
- 固件能力档案 `firmware_profiles/*.json` (工具生成, 禁止手填), 功能门控按寄存器能力判定不按版本号; 警惕「缺档案静默回退」。
- 前端周期发帧用 await promise 链驱动, 禁用 setTimeout/setInterval (后台标签页节流会触发下位机看门狗)。
- HID 设备全机只许一个进程持有; 多实例用 `WEB_GUI_PORT` 换端口, 默认绑 127.0.0.1。
【3. 运行 / 环境】- `setup.bat`: 检查 py -3.12 → 建仓内 venv → 先装 vendor/ 内部 wheel → 优先 `requirements.lock.txt` → import 自检 + 原生 DLL (hidapi) 自检。依赖一律进 venv, 禁止全局 pip; 数值库精确 pin。
- `start.bat`: 优先 venv Python, 回退 py -3.12; `.claude/launch.json` 配 server:8765 供 AI 预览。
- Electron `main.js`: 打包态 spawn `server.exe`, 专属端口/0=OS 分配, stdout 重定向 server.log, 退出按进程组/映像名兜底杀孤儿孙进程, 轮询 `/api/state` 判就绪; `postmortem.js` 崩溃现场打包。
- worktree 自测必须在 worktree 目录里显式起服务并换端口。
【4. 打包 (`scripts/build.bat`, `docs/PACKAGING.md`)】- Nuitka 把 server.py 编成独立 server.exe (编译参数写在 server.py 头部 `# nuitka-project:` pragma, 数据目录/隐式模块在这里声明) → electron-builder 打 NSIS + zip。
- 多 SKU「编一次打多次」: `--internal/--release/--customer/--all`, 差异全部是对产物目录的后处理 (删文件/写档位数字) + productName 覆盖; 顺序只能从内容全到内容少; 未知参数直接报错。
- 守卫: 源树完整性 (构建前后 HEAD 一致, internal 拒脏工作区)、客户包构建后门禁 (必须在的在、必须剔除的已剔除、档位值正确)、禁止「跳过编译的快速打包」。
- bat 坑: `for /f` 内 `=`、`>` 需 `^` 转义。
【5. 版本与发布 (`scripts/release.py`, `CHANGELOG.md`, `VERSION`)】- `VERSION` 单一来源, 日常禁止手改; 唯一入口 `python scripts/release.py X.Y.Z`: 校验 semver/工作树干净/[未发布] 非空 → 写 VERSION 并同步 package.json/lock → 截断 CHANGELOG → commit + 本地 tag。推送留人工 (分支和 tag 两条命令, 发后 `git ls-remote --tags` 核)。
- CHANGELOG `## [未发布]` 段随分支写, 面向用户一句白话; 有新增 → minor, 仅修复 → patch。
- 发版前对账: 重看 HEAD、`git log 上个tag..HEAD` 逐条对 CHANGELOG、冲突保双方且 `grep -c '<<<<<<<'` 为 0。
- 发布后回收工单上的「待发布」占位; 发版后继续开发用 `--internal` (名字带 +sha) 避免同名覆盖。
【6. CI/CD (`.gitlab-ci.yml`, `scripts/ci_*`)】- 只有 tag 触发流水线: `vX.Y.Z` 同时打 Windows + macOS 正式包; `win-smoke-*` 冒烟; `internal/*` 排除。stages: test(门禁) → build → notify(飞书, 失败不让构建变红)。
- CI 只调用同一份 build 脚本, 不重复造门禁。`GIT_CLEAN_FLAGS` 排除 venv/node_modules 做缓存 (实测提速 3.4×)。
- Windows Runner 坑: 服务账号用 Administrator + 系统 powershell 5.1 (非 pwsh), before_script 显式补 PATH, .ps1 必须带 BOM; 不信任 Runner 注入的 CI_* 变量 (长 commit message 会让其变空) → cwd 用特征文件判定、tag 用 `git tag --points-at HEAD`。
- NAS 分发: 凭据是 masked CI 变量; 一版一目录; 目标已存在即拒写不覆盖; 上传后回读逐个 SHA256 核对; internal 包进 `_internal/fw-<sha>/`。
【7. 测试与门禁】- `pytest.ini` 把 testpaths 钉死在 `tests/unit` (tests 根下是需真机的独立脚本, 防收集期 INTERNALERROR)。回归缺陷配专门回归测试 (修复前应全红)。
- UI 改动 playwright 自验 (`docs/skills/playwright_ui_self_test.md`); 真机验收走可见 GUI。
【8. Git 流程】- 主干 development, 分支前缀 `feat/ fix/ docs/ chore/ release/ hotfix/`, 小写短横线, 禁用工具自动生成的分支名; `git merge --no-ff -F msg` 合回; 删分支前 `--merged` + `merge-base --is-ancestor` 双验。
【9. 协作外设】- 缺陷池/需求池在飞书多维表格, 用 lark-cli (子命令带 +, `--base-token`); onboarding 清单一次授全 scope; fnm 装的 CLI 可能不在 agent PATH。
- 本机差异 (相邻仓路径、私钥) 只进 `~/.<proj>/workspace.json`, 不进仓。
【复用建议】新项目先建 AGENTS.md (硬规定 + 模块→skill 映射表) + PROJECT-CONTEXT.md + VERSION/CHANGELOG/release.py + setup/start 脚本 + 单一 build 脚本 + tag 触发 CI, 再按业务填 skill。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 【原状态说明】已归档 (可复用模板)

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-025: 舵机(KingKong)诊断包解密规则 — kkdiag + 本机私钥
**日期**: 2026-09-23
**项目**: driverSoftware (@CODE_ROOT@\driverSoftware)
**关键词**: 诊断包, diag, 解密, kkdiag, diag_private.pem, 私钥, 黑匣子, blackbox, events.jrn, rings.json.enc, env.json.enc, key.bin, AES-GCM, RSA-4096

**需求场景 / 现象**: 包格式 = 每会话随机 32B DK (AES-256-GCM 加密各段) + RSA-4096-OAEP 封装 DK 于 key.bin; 无私钥不可暴力/逆向。本机会话原始数据在 `~/.kingkong_driver/sessions/` 只保留 7 天; dev 环境另有 blobs_plain 明文副本。

**方案 / 实施步骤**:
规则：用户给出 `diag_*.zip` 要求解析时:
1. 私钥以对称加密形式存于知识库: `<OUTSIDE_REPO_SECRET_STORE>\diag_private.pem.vault` (scrypt + AES-256-GCM; 2026-09-23 核验与仓内 `core/diag_pubkey.pem` 匹配)。口令**不落盘**, 每次使用必须由用户本人手动录入确认; AI 不得保存、复述或代填口令。本机不再保留明文私钥。
2. 调用 (仓根, 用户在自己终端执行, getpass 提示输入口令; 私钥只解到临时文件, 用完即删):
   - 时间线: `venv\Scripts\python.exe <OUTSIDE_REPO_SECRET_STORE>\diag_key_vault.py kkdiag report <包.zip>`
   - 全展开: `... diag_key_vault.py kkdiag open <包.zip> -o <目录>` → env.json / events.jsonl / rings.json / manifest.json
   - 出图: `... diag_key_vault.py kkdiag plot <包.zip> all -o <目录>`
   - 重新加密/换口令: `... diag_key_vault.py seal <明文pem>`
3. AI 流程: 先跑免私钥的 `tools/kkdiag.py inspect`; 需要解密时给用户上面的命令让其录入口令, 再读取其 `-o` 输出目录分析。解密输出按敏感数据处理, 不入仓不转发。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 【原状态说明】已归档 (可直接调用)

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-026: EncoderPlotter 烧录面板放开 DPB 锁定 — 型号/固件文件可重选
**日期**: 2026-09-23
**项目**: EncoderPlotter_0703_03 (分支 feature/flash-and-pcba，主仓 1f5c515a，子模块 sub_automation 30b1c3f)
**关键词**: 烧录面板, flashPanel, DPB 锁定, 型号选择, IAP, MPT-G, --mpt-g, flash_tool.py, CONFIGS extra_hex, localStorage 配置恢复, nuitka 重编

**需求场景 / 现象**: 放开 1a5e4de1 引入的“仅 DPB”定制锁定，默认 DPB，型号与 Hex/IAP 文件均可重选；增加 MPT-G。PCBA 面板本身无锁定，不改。

**方案 / 实施步骤**:
方案要点：- flashPanel.js 模块级常量 SENSOR_OPTIONS（value 直接拼 `--<value>` 传给 flash_tool.py）、DEFAULT_SENSOR='dpb'、IAP_SENSORS=['dpb','dpt-g1','mpt-g']、getDefaultDpbFiles()（asar 用 resources/bin，开发用 sub_automation/bin）。
- data(): 缓存型号在白名单才恢复；缓存型号与当前一致才恢复缓存路径；否则 DPB 填默认 bin 文件、其它型号为空。
- watch selectedSensor: 切 DPB 填默认文件，切其它清空待重选。
- computed needsIapFile 取代 isDPBMode；startFlash 仅在 needsIapFile 时传 iapFile，否则 null。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 踩坑：1. 前端型号必须与 flash_tool.py argparse 参数和 CONFIGS 中 extra_hex 同步：mptg 在 CONFIGS 有 IAP，但原前端 isDPBMode 不含 mpt-g，且 CLI 无 --mpt-g → 选了必失败（R6B/R6C 发现）。
1. 打包版优先用 dist 中预编译 flash_tool exe，builder.ts 的 nuitka 命令被注释，改 flash_tool.py 后需手动重编，否则新参数不生效。
2. 子模块改动需先在 sub_automation 提交，再更新主仓指针；推送顺序子模块优先。
遗留：缓存路径未校验（安装目录变化失效；换行注入 jlink 脚本需本机权限）；未实机烧录验证。
【原状态说明】已归档 (可直接调用)

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-027: 【飞书自动化】飞书 ⇄ Claude Code 双向闭环：完成通知、飞书回复续跑、桌面上下文同步
**日期**: 2026-09-23 ~ 2026-09-24
**项目**: 全局工具 @USER_HOME@\.feishu_bridge
**关键词**: 飞书自动化, 飞书, Feishu, Lark, lark-oapi, 长连接, 自建应用, 机器人, 消息卡片, Stop Hook, UserPromptSubmit, claude --resume, 双向通知, 远程续跑, 上下文同步, feishu_turns, CLAUDE_CONFIG_DIR, CC-Switch, cc-switch.db, common_config_claude, proxy_live_backup, hosts, platform.claude.com

**需求场景 / 现象**: 在桌面 Claude Code 做完任务后通知到飞书；用户在飞书「回复」通知，本机在原会话、原目录续跑，结果回帖到飞书；回到桌面时，Claude 能拿到飞书里发生的完整对话，并在界面上展示出来。用户明确否决 Remote Control 替代方案，必须走飞书。

**方案 / 实施步骤**:
完整流程（闭环）：1. 桌面一轮结束 → Stop Hook `hook_notify.py` 取最后一条 assistant 原文 → 发飞书卡片（标题=✅项目名，副标题=完整目录，正文按标题分块+分割线，≤800 字）→ 存 `msg_map`：message_id→session_id+项目根目录。
1. 用户在飞书「回复」卡片 → `listener.py`（长连接）收 `im.message.receive_v1` → message_id 去重 → 白名单 open_id → 用 parent_id 查 `msg_map` → 危险关键词先要「确认」。
2. 续跑：回帖「🚀 执行中」→ 在 `feishu_turns` 记一条（你说的话，synced=0）→ 在原目录启动 `claude.exe --resume <sid> -p --permission-mode bypassPermissions`（prompt 走 stdin，env: CLAUDE_CONFIG_DIR=~/.claude-feishu、FEISHU_BRIDGE_REPLY_TO、FEISHU_BRIDGE_CWD、FEISHU_BRIDGE_TURN_ID）。
3. 续跑结束 → 续跑进程自己的 Stop Hook 把结果卡片回帖到用户那条回复下，并把**完整回复原文**挂到该 turn → 新卡片再次进入 `msg_map`，可以一直回复下去。
4. 回到桌面发消息 → UserPromptSubmit Hook `hook_sync.py` 取出该会话 synced=0 的所有飞书轮次 → 作为 additionalContext 注入（ASCII 转义输出），附指令「回复开头原样贴出 📥 飞书同步（N 轮），含每轮问题与回复原文，再加分割线后回答当前问题」→ 标记 synced=1。
5. 守护：listener 每 60s 检查 `~/.claude/settings.json`，缺少 Stop(hook_notify) 或 UserPromptSubmit(hook_sync) 就补回。
【安全】一次性口令绑定主人（私聊「绑定 <码>」，用后删除）；白名单是真正边界；危险关键词二次「确认」仅防误触（含 cc-switch/settings/hook/配置 类词）；续跑专用配置 ~/.claude-feishu/settings.json 用 permissions.deny 的 Edit 规则禁止改全局 settings、CC-Switch、桥接自身代码与凭据（bypass 模式下实测有效，但拦不住 Bash 直接写）；同会话加锁串行；超时 taskkill /T /F；日志不记录密钥。

**验证方法**: 真机联调通过（绑定→通知→回复 pong→续跑 rc=0→回帖）；R6B 复核第 1 轮 FAIL（1 高 3 中），修复后第 2 轮 PASS；CC-Switch 重启后 Hook 保留、守护未触发；飞书两轮（08:27/08:28）续跑 rc=0，桌面回填 2 条成功；同步输出为纯 ASCII，中文解码正常。

**踩坑 / 已知异常与失败经验**: 踩坑与解法：1. 自定义机器人 Webhook 只能发不能收 → 改自建应用 + 长连接事件（无需公网）。
1. 首个私聊者即成为主人，存在抢绑风险（R6B 高危）→ 改为一次性口令绑定。
2. 以 - 开头的回复会被当成 CLI 参数 → prompt 改走 stdin；超时只杀父进程会导致锁一直不释放 → taskkill /T。
3. 桌面 App 用内置 1P 登录，后台 CLI 继承不到；全局 settings env 指向 CC-Switch 代理，而「Claude Desktop Official」供应商没有 base_url → 400。解法：独立 CLAUDE_CONFIG_DIR=~/.claude-feishu，projects 用 junction 链到 ~/.claude/projects 共享会话，单独 /login（订阅账号），子进程清除继承的 ANTHROPIC_*/CLAUDE* 变量。
4. 本机 DNS([private-ip-redacted]) 解析不了 platform.claude.com → /login 报 ENOTFOUND；hosts 加 160.79.104.10 platform.claude.com。
5. 续跑中模型 cd 导致 Hook 记录的 cwd 漂移，下次续跑跑错目录 → cwd 优先级 FEISHU_BRIDGE_CWD > CLAUDE_PROJECT_DIR > hook cwd。
6. 纯文本通知挤成一团 → 改用飞书卡片 2.0，按标题/独占粗体行分块加 hr，去掉 [SIRE] 声明行，截断时补齐代码块。
7. CC-Switch 开机会整体重写 ~/.claude/settings.json，Hook 被冲掉，桌面会话不再通知（续跑仍能通知，因为用的是 ~/.claude-feishu/settings.json）→ listener 守护每 60s 补回。
8. 根治第 8 条：Desktop Official 供应商的编辑页没有配置入口。数据实际在 ~/.cc-switch/cc-switch.db 的两处：settings 表 key=common_config_claude，以及 proxy_live_backup 表 app_type=claude 的 original_config（开机回写用的快照，是丢失的直接来源）。做法：关闭 cc-switch.exe → 备份 db → 两处 JSON 的 hooks 都补齐 → integrity_check → 重启。两处都要改；CC-Switch 升级后可能失效，守护兜底。
9. 桌面 App 只使用内存里的上下文，不会重读 .jsonl：飞书续跑虽然写进同一会话文件，但在记录里成了分叉支线，桌面既看不到也不知道 → 新增 feishu_turns 表 + hook_sync.py，在下一次桌面提问时注入上下文。
10. hook_sync 输出中文到 stdout 被 Windows 代码页(GBK)写成乱码 → json.dumps(ensure_ascii=True)，用 stdout.buffer 写 ASCII。
11. 注入的 additionalContext 在桌面界面上不可见，用户「看不到完整信息」→ feishu_turns 存完整回复原文（卡片仍用 800 字精简版），并要求 Claude 在回复开头原样贴出「📥 飞书同步」，单次上限 3 万字。这是靠指令约束，不是强制插入；漏贴时让 Claude「贴一下飞书同步」即可。
12. 桌面 App 界面本身永远不会显示飞书轮次（没有公开接口），同一会话不要两端同时操作。
13. 飞书续跑曾自行改动 CC-Switch 数据库，而用户没有在桌面确认 → 两层防护：① 危险词加入 cc-switch/settings/hook/配置文件/全局配置/通用配置/config.json 等，命中后要回「确认」才执行（只检查用户原话）；② ~/.claude-feishu/settings.json 加 permissions.deny：Edit(~/.claude/settings.json)、Edit(~/.claude-feishu/settings.json)、Edit(~/.cc-switch/**)、Edit(~/.feishu_bridge/config.json)、Edit(~/.feishu_bridge/*.py)。已实测 bypassPermissions 下仍然拒绝（WRITE_DENIED）。注意：Write(...) 规则无效，Edit(...) 规则已覆盖所有写文件工具；deny 拦不住 Bash/python 直接写文件，这类情况靠危险词兜底。
遗留：runs/*.log 未清理；App Secret 曾出现在对话中，建议重置后更新 config.json；开机场景下 CC-Switch 修复的效果待下次开机后确认。

**关键文件与接口**: bridge_config.py / bridge_store.py（msg_map、pending、seen、feishu_turns）/ bridge_sender.py（文本+卡片）/ hook_notify.py / hook_sync.py / listener.py / install_service.ps1（计划任务 FeishuClaudeBridge，pythonw 开机自启，失败每分钟重启）/ login_bridge.cmd / config.json（凭据，仅当前用户可读）。飞书应用权限：im:message、im:message:send_as_bot、im:message.p2p_msg:readonly；事件订阅=长连接。

**状态**: 已废弃

### F-028: 【知识库优化】SIRE 知识检索 v2：bge 语义 + trigram 全文 + 复用要点，recall@3 0.45→1.00
**日期**: 2026-09-24
**项目**: SIRE 知识检索 v2 实施记录（历史闭环库为 `@SIRE_ARCHIVE_ROOT@\sire_vectors.sqlite3`；Claude/Codex 当前工作库由 `sire_paths.py` 指向仓库 `data/sire_vectors.sqlite3`）
**关键词**: 知识库优化, 向量检索, 语义检索, bge-small-zh, fastembed, trigram, FTS5, 混合检索, BM25, 复用要点, 知识模板, sire_kb lint, sire_kb add, is_latest, 只增不减, 评测集, recall

**需求场景 / 现象**: 数据库优化后要求「能快速检索知识，检索到的知识可直接用来开发相同功能」。审计发现：98 条知识有 81 条只在库里（sire_kb 只读 md，搜不到）；FTS5 默认分词对中文失效（「寄存器」全文 4 条 vs 实际 73 条），`CC-Switch` 直接语法错误被吞；global_index.json 17 个版本霸榜；查询拆出单字导致每条知识都被 +0.12 失去区分；关键词表是 u-01/r6a/users 这类噪音；分类用子串匹配把 decision 里的 ci 判成 devops。基线 recall@1 0.35 / recall@3 0.45 / 313ms。

**方案 / 实施步骤**:
1. 备份库与脚本（sire_db_backup + @SIRE_ROOT@\opt-backup-20260924）。
2. 写评测集（自然说法，不照抄标题）跑基线。
3. pip install fastembed；HF_ENDPOINT=https://hf-mirror.com 下载模型到 @SIRE_ROOT@\models。
4. 新模块 + 旧脚本两点接入；index 触发 post_index（首跑约 40s 计算 1052 条向量）。
5. sire_kb 改库优先 + 三个新命令；SIRE-MIGRATION.md 升 v2.6。
方案 / 架构：- 新模块独立承载 v2，旧脚本只接入两点（index 末尾 post_index、search 先走 v2 异常回退旧算法），保证不把现有工作流搞挂。
- 语义：本地 BAAI/bge-small-zh-v1.5（fastembed/ONNX，无 torch，512 维，91MB，hf-mirror 下载，缓存后 HF_HUB_OFFLINE 离线）；向量存 emb 表，按 text_hash 增量计算。
- 全文：FTS5 tokenize='trigram'（≥3 字符生效），查询词双引号包裹；2 字中文词用 Python 覆盖率补足。
- 打分：0.55×语义 + 0.30×词项覆盖(标题/关键词命中 1、正文 0.5) + 0.15×BM25 名次归一 + 关键词精确命中 0.1 + 知识记录 0.06；台账片段 ×0.9；同一 path 只留最高分片段，片段内容就是已入选知识则跳过。
- 只增不减：旧版本 is_latest=0、派生文件排除、噪音关键词 status=noise、类型归一原值存 orig_type、空关键词只补空——全部不删数据。
- 可复用：结果附 reuse（关键文件汇总 + 根因/修复/流程/验证/踩坑分段首行；整段式正文按句挑「方案是/必须/重点检查」）；KNOWLEDGE_TEMPLATE.md 定义必备段落，sire_kb add 写入前校验，lint 列出需补全记录。

**验证方法**: `python @SIRE_ROOT@\eval\run_eval.py 标签` → recall@1 0.95、recall@3 1.00、平均 76ms（进程内），CLI 单次约 0.7s（含模型加载）；knowledge_records 98 / task_records 515 条数不减；`sire_kb.py lint` 输出待补全清单。

**踩坑 / 已知异常与失败经验**: 踩坑：- trigram 只能匹配 ≥3 字符，2 字中文词必须另算覆盖率。
- FTS 查询不加引号时 `CC-Switch` 被解析成列名报错，旧代码 except 吞掉导致静默失效。
- 知识正文两种写法（**段落**: 与整段话），复用要点要两套抽取；段落标题可能很长（如「修复（仅改…）」），正则上限需放宽到 60。
- 导出副本/模板若进入切片会与知识记录重复，必须排除。
- fill_missing_keywords 对 md 来源记录的补全会在下次同步时被 md 原值覆盖（md 无关键词则仍为空），根治要在 md 里补关键词。

**关键文件与接口**: - `<SHARED_SKILL_DIR>/scripts/sire_knowledge_index.py` — post_index(conn)、search(conn, query, limit, threshold, domain, hash_encode, hash_decode)、reuse_points(body)、mark_latest、sync_embeddings
- `<SHARED_SKILL_DIR>/scripts/sire_vector_db.py` — search_database 委托 v2；index_database 末尾调用 post_index；source_paths 排除派生文件；classify 词边界
- `<SHARED_SKILL_DIR>/scripts/sire_kb.py` — load_db_records（库为正式来源）、export-md、lint、add
- `<SIRE_ROOT>/knowledge/global/KNOWLEDGE_TEMPLATE.md`、`@SIRE_ROOT@\eval\queries.json`、`@SIRE_ROOT@\eval\run_eval.py`

**状态**: 已完成

### F-029: Codex 桌面会话与飞书完整可见对话同步及续跑
**日期**: 2026-09-24
**项目**: 原记录未记载
**关键词**: 飞书, Feishu, Codex notify, transcript JSONL, 用户消息, 助手可见回复, 分卡, 游标, 重启恢复, codex exec resume, msg_map

**需求场景 / 现象**: 飞书查看 Codex 当前会话的完整可见文字，并通过回复已同步卡片把指令交回同一 Codex 会话。

**方案 / 实施步骤**:
实现：Codex notify 回调按 thread-id 定位 ~/.codex/sessions 下 JSONL。只导出 response_item 中 user 的 input_text 与 assistant 的 commentary/final_answer output_text；过滤 developer、reasoning、工具调用和工具输出。用 message id 作游标，首轮回填完整可见历史，后续增量同步。约 2400 字符分卡，每张卡保存 msg_map(message_id→session_id,cwd,codex)，飞书回复沿用监听器已有 codex exec resume。图片原文可读时文件名/路径随用户文字发送；只有不可解码的 image 输入块而无名称/路径时，卡片明确标记名称/路径未记录。
【补充验收】注入一次发送异常后，待办保持且游标不前移；恢复发送后批次发送完成、游标前移、待办清空。该项所有功能断言通过；Windows 仅在清理测试临时 SQLite 目录时遇文件锁，清理命令被本机策略拒绝，遗留的是 Temp 下的测试目录，不影响桥接数据。真实飞书界面核对与飞书用户回复仍待用户操作。

**验证方法**: 2026-09-24 本机 py_compile 通过；实际会话 135 条可见消息、约 33337 字符切成 16 张卡，单条超长文本可逐字还原；飞书发送 API 接受 16 张卡且 msg_map 建立，随后重启监听器并标记待同步，启动恢复又发 1 张增量卡、清空待办、推进游标。当前会话实际 UI 展示及用户在 Feishu 回复后入站执行仍需用户在 Feishu 实际回复测试卡验证；Windows 当前没有可用共享 app-server，不能把 CLI queue 视作桌面实时投递已验证。

**踩坑 / 已知异常与失败经验**: 可靠性：SQLite 持久化每会话游标和 codex_sync_pending。每张卡获接口确认并保存映射后推进游标；发送异常保留待办，由飞书监听器每分钟重试，重启后从最后确认的消息继续。网络结果不确定时允许重复一张已发送卡，优先避免丢失；不是严格 exactly-once。

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 部分完成

### F-030: 飞书回复 Codex 桌面会话：codex queue 入队与回调关联（WAITING_CODEX）
**日期**: 2026-09-24
**项目**: 飞书桥接（FeishuClaudeBridge）
**关键词**: 飞书, Codex, codex queue, active writer, thread-store conflict, notify hook, 消息回帖, WAITING_CODEX, 待关联任务, 重启恢复

**需求场景 / 现象**: 飞书回复必须路由到固定 Codex 会话/工作目录执行并回帖；旧方案 codex exec resume 在桌面 Codex 线程遇到 thread-store active writer，自动重试三次仍冲突。

**方案 / 实施步骤**:
1. 不要重复重试 codex exec resume；改用 codex queue --thread <session> --message <text> -C <cwd>，返回 Queued message ID，只确认入队，不能据此宣称已执行。
2. 先持久化 pending(task_id,session_id,cwd,turn_id,queue_id)，再入队。
3. Codex notify completion 用 session_id 取最早 pending，调用 hook_notify.deliver 回帖原 Feishu 消息，再把完整可见文本增量同步到同一回复。
4. 发送失败保留 RESULT_READY/pending，成功后删 pending。

**验证方法**: 2026-09-24：py_compile 通过并重启 FeishuClaudeBridge；真实完成回调仍未通过：桌面线程保持 idle，accepted queue 未产生新的 user response_item。

**踩坑 / 已知异常与失败经验**: 活动写锁触发失败；任务标记 WAITING_CODEX，不得重复入队，不得报告端到端通过；重启后 WAITING_CODEX 保留，但队列执行/回调恢复需进一步验证。

**关键文件与接口**: codex queue；hook_notify.deliver；listener；Codex notify hook；pending(task_id,session_id,cwd,turn_id,queue_id)；WAITING_CODEX

**状态**: 部分完成

### F-032: 飞书回复显式指定 Claude/Codex 并按工作目录安全路由
**日期**: 2026-09-24
**项目**: 飞书桥接（FeishuClaudeBridge）
**关键词**: 飞书, Claude执行, Codex执行, 显式路由, 执行者前缀, parent_id, msg_map, session_id, cwd, 多会话歧义

**需求场景 / 现象**: 用户在飞书回复正文指定执行者，例如“Claude执行：复核刚才的分析并实现”，需剥离路由前缀后把剩余内容作为目标 AI prompt。

**方案 / 实施步骤**:
1. 在 listener.py 仅识别消息开头的显式前缀（Claude执行：、让Claude执行：、Codex执行:、由 Claude 来执行：）；无前缀时保持回复父卡片映射的 backend/session。
2. 飞书事件 parent_id 指向被回复的机器人消息，用该 message_id 查询 msg_map(message_id, session_id, cwd, backend)，并将 backend/session_id/cwd 写入任务账本后路由；回复文本仅作为该目标会话的 prompt。
3. 跨后端切换保持父卡片 cwd，在 msg_map 中查询同 cwd、指定 backend 的会话；唯一候选才执行，零候选或多候选均拒绝投递并回复原因。
4. 结果卡片标题显示 AI 名称，msg_map 保存新后端及 session，使后续回复继续正确路由。

**验证方法**: py_compile 通过；5 类前缀/无前缀断言通过；目录会话解析唯一及歧义断言通过。飞书测试回复“claude执行：只回复ROUTE_OK”被解析为 backend=claude，session_id 为同目录 Claude 会话，cwd 保留 @CODE_ROOT@\EncoderPlotter3，前缀已从 prompt 剥离；错误回复回到飞书原消息。

**踩坑 / 已知异常与失败经验**: 当前桥接不会根据回复正文里的“Claude/Codex”字样（无显式前缀时）切换执行者；新发私聊或无法映射的消息会提示必须回复任务通知；跨 AI 切换需要回复目标 AI 自己的卡，因为两边会话 ID 和工作目录不同。@CODE_ROOT@\EncoderPlotter3 映射下 Claude 会话唯一、Codex 会话多于一个，因此 Codex 分析卡→Claude 执行可唯一解析，反向则安全拒绝歧义。Claude 返回 session limit（重置时间提示为 13:00 Asia/Shanghai），故只证明路由/错误回传通过，不证明 Claude 成功执行，未自动重试。没有可控制已登录飞书用户账号的 UI 自动化工具，机器人身份消息不等同于白名单用户回复，未伪造真实端到端测试，整体端到端状态 BLOCKED。

**关键文件与接口**: listener.py；msg_map(message_id, session_id, cwd, backend)；parent_id；任务账本

**状态**: 部分完成

### F-034: 飞书显式 Claude 路由已验证，执行受订阅限额阻断（ROUTE_OK 测试）
**日期**: 2026-09-24
**项目**: 飞书桥接（FeishuClaudeBridge）
**关键词**: 飞书, Claude执行, ROUTE_OK, 路由验证, session limit, 订阅限额, 错误回传

**需求场景 / 现象**: 用真实飞书回复“claude执行：只回复ROUTE_OK”验证显式执行者路由。

**方案 / 实施步骤**:
1. 在飞书发送回复“claude执行：只回复ROUTE_OK”。
2. 检查账本：backend=claude；session 为 EncoderPlotter3 同目录 Claude 会话；cwd=@CODE_ROOT@\EncoderPlotter3；存储 prompt 为“只回复ROUTE_OK”（路由前缀正确移除）。
3. 后续可在 13:00 后重试，或由用户明确指定 Codex。

**验证方法**: 账本证据：attempt=1，rc=1；runs 日志 You've hit your session limit · resets 1pm (Asia/Shanghai)；飞书向用户回传错误。显式执行者解析、Claude 会话选择、目录继承与错误回传通过。

**踩坑 / 已知异常与失败经验**: Claude 成功执行未通过，原因是订阅会话限额，非桥接路由错误；未自动重试或回退 Codex。

**关键文件与接口**: 任务账本（backend、session、cwd、attempt、rc）；runs 日志

**状态**: 已完成

### F-035: Codex 桌面可见对话通过 Stop 钩子与游标轮询补漏同步飞书
**日期**: 2026-09-24
**项目**: 飞书桥接（FeishuClaudeBridge）
**关键词**: Codex, Feishu, 飞书, Stop Hook, hooks.json, transcript cursor, 对话补漏, 重启恢复, 完整可见消息

**需求场景 / 现象**: Codex 桌面会话需要将可见用户/助手文字持续同步到飞书，并在钩子漏触发或电脑/监听服务重启后补齐。旧桥接只依赖 config.toml 的 notify 命令，当前会话游标之后累积 46 条可见消息未同步。

**方案 / 实施步骤**:
1. hook_codex_notify.py 同时接受旧 notify argv 与 Codex 原生 Stop 生命周期事件的 stdin JSON，按 session_id/cwd/transcript_path 读取可见对话并沿用持久游标。
2. 原 Feishu 任务仍先发结果卡，再将完整增量回复到原消息，发送成功后才清除 pending。
3. listener.py 的 60 秒守护循环额外扫描已有 transcript cursor 的 Codex 会话，仅补发新内容，避开仍在发送的 pending session。

**验证方法**: Python 编译通过；mock 测试覆盖 Stop stdin 字段映射、legacy 独立通知过滤、待处理 Feishu 任务结果+完整对话回帖+成功后清 pending、守护循环只扫有游标且跳过 pending；真实补发积压 6 张飞书卡，API 返回成功，msg_map 建立、游标前移、codex_sync_pending 清零；服务重启后仍 Running。

**踩坑 / 已知异常与失败经验**: notify 入口不能保证桌面每轮都触发，且旧过滤会跳过 client 字段缺失的独立事件；Codex 原生 Stop hook 需在 Codex 客户端 review/trust 后才能运行；新会话首次完整同步仍依赖 Stop hook 被信任或另行建立初始游标；API 接收成功不等于 UI 人工验收；已有一个 Codex queue 完成卡的文本似乎与原 Feishu prompt 不一致，未自动重投，需单独核验 queue 与完成回调关联。

**关键文件与接口**: hook_codex_notify.py；listener.py；config.toml notify；hooks.json；codex_sync_pending

**状态**: 已完成

### F-036: 飞书桥接当前实现缺口与验收优先级
**日期**: 2026-09-24
**项目**: 飞书桥接（FeishuClaudeBridge）
**关键词**: 飞书, Codex, Claude, 会话纳管, Stop Hook, 消息元数据, 工作目录, 附件清单, WAITING_CODEX, 队列恢复, 回调关联, 幂等, R7, 共享规则, 多AI扩展

**需求场景 / 现象**: 评估本机 FeishuClaudeBridge 是否覆盖 Codex/Claude 双向通讯、完整上下文、显式执行者选择和重启恢复。

**方案 / 实施步骤**:
1. 已确认实现：飞书回复按 parent message 映射 backend/session/cwd；正文显式“Claude执行/Codex执行”时跨后端选择同 cwd 唯一会话，多候选安全拒绝；Codex 可见消息按游标增量发送；桥接任务在用户登录时启动，异常退出会重启。
2. P0 待补强：1) 完整会话纳管（新 Codex 会话无游标时不会被 60 秒扫描发现，Stop Hook 依赖客户端 review/trust）；2) 消息信封（卡片不显示 session ID）；3) 附件清单（input_image 只生成占位）；4) Codex 队列恢复与关联（无 WAITING_CODEX 恢复，应以 queue/turn ID 关联、超时标记与人工安全恢复，绝不盲目重新入队）；5) R7 真实场景验收。
3. P1：结果卡和完整对话卡的发送/SQLite 落账之间建立持久 outbox 与幂等重试/去重。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 通知 Hook 按同一 session 最早 pending 关联，非 queue_id 精确匹配，异常/并发/重启可能卡住或错配；不确定发送结果时可能重复卡片；service 计划任务为用户登录触发，PC 开机但未登录时本地执行器不会运行；Feishu API 成功/本机日志不能替代飞书客户端 UI 验收；Claude 路由执行因订阅限额 rc=1，额度可用后只需成功场景验证，不应静默切换 Codex。

**关键文件与接口**: listener.py；hook_codex_notify.py；hook_notify.py；install_service.ps1；WAITING_CODEX

**状态**: 部分完成

### F-037: 飞书与多AI通过唯一中间服务通讯的单中枢架构（目标架构决策，未实现）
**日期**: 2026-09-24
**项目**: 飞书桥接（单中枢架构）
**关键词**: 飞书, 中间服务, 消息中枢, 单一通信入口, Codex, Claude, Provider Adapter, 任务路由, 消息账本, Outbox, 会话ID, 工作目录

**需求场景 / 现象**: 设计飞书、Codex、Claude 等多 AI 的消息路由架构：飞书只与中间服务通讯，AI 之间不直接通讯。

**方案 / 实施步骤**:
1. Feishu Adapter 接收回复并校验身份、事件去重。
2. 先把原始消息、parent/root 消息ID和任务记录持久化。
3. Router 按显式执行者前缀路由；无前缀时按父消息绑定的 agent/session 继续，缺映射或候选歧义时询问用户，不猜测；默认只发给一个 AI，用户明确要求协作才建立父任务/子任务。
4. Provider Adapter 将任务封装交给本机已登录的 Codex/Claude 会话。
5. 执行端只将 progress/completed/failed 及 result 返回 Broker，必须携带 task_id 和 provider/session/turn 或 queue 标识。
6. Broker 落结果、更新任务状态并写持久 outbox。
7. Feishu Adapter 按原 parent_message_id 回帖。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 当前差距：hook_notify.py/hook_codex_notify.py 在回调路径中仍直接调用 bridge_sender 发送飞书并直接访问共享 SQLite，属半中心化实现，需改为只投递到本地 Broker；凭据不进入信封或云端日志；本条仅保存目标架构，未改代码，不代表已实现或验收。

**关键文件与接口**: 规范化消息信封字段：event_id、task_id、conversation_id、collaboration_mode、selected_provider、provider_session_ids、cwd、feishu_message_id、parent/root_message_id、sender_id、attachments、status；hook_notify.py；hook_codex_notify.py；bridge_sender

**状态**: 部分完成

### F-038: 当前飞书桥接与单一中间服务架构的比较结论与迁移步骤
**日期**: 2026-09-24
**项目**: 飞书桥接（单中枢架构）
**关键词**: 飞书, 中间服务, 单一Broker, 架构比较, Codex, Claude, 订阅额度, 本地执行器, 渐进迁移, Provider Adapter

**需求场景 / 现象**: 在“重写为单 Broker”与“继续使用现有 FeishuClaudeBridge”之间做取舍。

**方案 / 实施步骤**:
1. 不换现有 Feishu 长连接/SQLite，先定义统一 Envelope、任务状态机、持久 Inbox/Outbox 与 task_id 关联。
2. 将 hook_notify.py/hook_codex_notify.py 改为只向本地 Broker HTTP/命名管道/队列上报，不直接发送 Feishu；Broker 独占 Feishu API 与消息映射。
3. 将 Claude/Codex 包成 Provider Adapter，明确 session/cwd、quota/error、进度/完成事件。
4. 完成 Feishu UI 正常/边界及服务/电脑重启测试。
5. 通过后再考虑云端 Broker 或更多 provider；先做本地单进程/模块化 Broker，不必一开始引入微服务/Kafka。

**验证方法**: 完成 Feishu UI 正常/边界及服务/电脑重启测试（迁移步骤 4，尚待执行）。

**踩坑 / 已知异常与失败经验**: 结论：单一中间服务作为最终架构更优，但当前 FeishuClaudeBridge 作为已运行原型/迁移基础更有价值，不建议推倒重写。当前局限：Hook 回调直接调用 bridge_sender 发 Feishu 并直读写 SQLite；新会话纳管、WAITING_CODEX 恢复/精确队列关联、附件元数据、完整 session 信封、UI 端到端验收仍有缺口。中间服务是关键依赖，需持久队列、健康监测、备份、回压/重试和单点故障恢复；订阅凭据应留在用户电脑已登录环境，云端 Broker 靠本地 Worker 主动安全连接，电脑离线时不能承诺本地会话执行。

**关键文件与接口**: hook_notify.py；hook_codex_notify.py；bridge_sender；Inbox/Outbox；Provider Adapter

**状态**: 部分完成

### F-039: 单Broker飞书多AI系统的深层逻辑与失效模式审查
**日期**: 2026-09-24
**项目**: 飞书桥接（单中枢架构）
**关键词**: Feishu, 单一中间服务, Broker, 安全边界, bypassPermissions, 工作目录白名单, 任务状态机, 幂等, 队列恢复, 多AI协作, 上下文回环, 附件, 取消, 并发, 隐私

**需求场景 / 现象**: 在单一 Broker 架构下审查消息路由、权限、安全、上下文、并发、故障恢复中容易遗漏的逻辑。

**方案 / 实施步骤**:
1. P0 安全门：改成最小权限、固定 workspace allowlist、按任务能力授予、危险操作真人确认和可审计撤销；凭据留本机。
2. P0 消息与任务一致性：Feishu event_id 去重与持久 Inbox 原子提交，事件确认不能早于入库；每条任务固定 task_id、Feishu message/parent/root IDs、provider session/turn/queue IDs、路由和 cwd 快照；Agent 回调按精确 task/queue ID 匹配，不能按 session FIFO；重启后未知是否入队时不能自动重复执行非幂等任务。
3. P0 路由/对话语义：支持无 parent 的新任务启动和未知/多候选时询问；“Codex分析、Claude执行”是显式父子工作流，须传递上游产物/版本/来源；运行中收到新回复要定义排队、分支、取消或拒绝；支持取消、重试、放弃、超时。
4. P0 上下文一致性：规范对话账本和方向/来源标识避免回环；排序、修订、重发与分片使用序号/hash；明确可见文字范围；hook_sync 30000 字符截断需明确提示/摘要或分段回填。
5. P0 可用性：服务启动/登录、电脑离线、Feishu WS 断开、Agent 额度/认证失效、broker 崩溃、磁盘满/SQLite 损坏、任务超时分别定义状态、告警和恢复责任。
6. P1：保留期限、备份/恢复、加密、访问审计、日志脱敏；Feishu 消息卡长度/速率/权限限制、失败退避、死信和人工重放；跨 AI 写同一 repo 应默认串行或隔离 worktree。

**验证方法**: 当前是源码审查结论，不表示缺口已修复。

**踩坑 / 已知异常与失败经验**: bridge_config.py 默认 permission_mode=bypassPermissions，Codex 参数含 --dangerously-bypass-approvals-and-sandbox，Feishu 回复可触发本机执行；listener.resolve_cwd 主要检查目录存在，_is_danger 是关键词子串提示，不构成权限边界；listener.py 仅接收 text 消息；task recovery 遗漏 WAITING_CODEX；pending 按 session 最早任务领取；hook_sync.py 限制单次回填 30000 字符；完整同步到 Feishu 可能泄露可见回复里的凭据。

**关键文件与接口**: bridge_config.py；listener.py（resolve_cwd、_is_danger）；hook_sync.py；--dangerously-bypass-approvals-and-sandbox；permission_mode=bypassPermissions

**状态**: 部分完成

### F-040: 飞书机器人私聊直接发起AI任务的会话入口逻辑（尚未实现）
**日期**: 2026-09-24
**项目**: 飞书桥接（单中枢架构）
**关键词**: 飞书机器人, 私聊, 新任务入口, parent_id, conversation_id, 显式路由, Claude, Codex, 工作目录, 会话绑定

**需求场景 / 现象**: 用户无需先找到或回复已有任务卡片，直接私聊机器人发起 Claude/Codex 任务，结果由服务回复这条私聊消息。

**方案 / 实施步骤**:
1. Feishu Adapter 对用户校验、事件去重并持久化消息。
2. Broker 按（tenant/user open_id + chat_id，必要时再加 thread/root）查 conversation binding；已有绑定时继承 provider/session/cwd，消息开头显式执行者前缀可覆盖本轮目标。
3. 无绑定的新 DM 若缺 provider 或 cwd/session，先在原私聊线程追问选择，不猜默认 agent、不触发多 AI 协作；可用“Codex执行：…”/“Claude执行：…”以及显式 cwd/新会话指令初始化。
4. Broker 创建 conversation_id、task_id 及消息映射，保存 route snapshot、session IDs、cwd、feishu message/root/parent IDs；Provider Adapter 回报后 Broker reply 原私聊消息。
5. 推荐先支持白名单用户 p2p 私聊；首轮显式选择 Agent 和工作目录/会话，成功后持久绑定，随后允许自然语言连续对话。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: listener.py 无 parent_id 时直接提示用户回复已有任务完成卡；当前消息只支持 text，且没有持久 conversation-level provider/session/cwd binding，因此直接 DM 作为新任务入口尚未实现。同一私聊会话执行中收到另一条消息，应明确排队、分支、取消/补充或拒绝并记录，不能丢弃；机器人自身回帖及 Agent 同步事件按来源 ID 过滤防回环；群聊是否支持需另定 @bot 和成员授权。

**关键文件与接口**: listener.py；conversation binding（open_id + chat_id）；conversation_id / task_id；msg_map

**状态**: 部分完成

### F-041: 【飞书自动化】飞书多 AI 中转中间服务 feishu-hub（中间服务 + Claude/Codex 执行器，取代 F-027）
**日期**: 2026-09-24
**项目**: 飞书多 AI 中转中间服务 feishu-hub —— @SIRE_ROOT@\AI\AI\feishu-hub（GitHub Albert-Tsai-git/AI，分支 feature/feishu-hub，最新 ea704df）
**关键词**: 飞书自动化, 飞书中转, 中间服务, feishu-hub, hub, 多AI, Claude执行器, Codex执行器, 执行器协议, PROTOCOL.md, 租约, lease, 心跳, 长轮询, outbox, 发送队列, 幂等, uuid, 任务状态机, NEEDS_RECOVERY, WAITING_EXTERNAL, desktop_queue, codex queue, codex exec resume, claude -p, claude --resume, Stop Hook, UserPromptSubmit, notify, --previous-notify, computer-use, 计划任务, FeishuHub, lark-oapi, 长连接, 私聊建任务, 项目列表, 快捷操作, 取代 F-027

**需求场景 / 现象**: 用户在飞书里给本机的 Claude、Codex（及以后接入的 AI）派任务、回复卡片续跑、桌面端对话完成后推送飞书；各 AI 彼此独立，只与一个中间服务通信；信息不足先问、目录必须用户确认；电脑或服务重启后可恢复、绝不重复执行。以后买服务器后把中间服务迁上线，执行器留在本机。
（本记录取代 F-027「飞书 ⇄ Claude Code 双向闭环」：旧桥 ~/.feishu_bridge 已停用、listener.py 已删除、计划任务 FeishuClaudeBridge 已禁用。P-022 MSIX 路径映射仍适用，已沿用到新架构。）

**方案 / 实施步骤**:
方案 / 架构：```
飞书 ⇄ 中间服务 hub（唯一连飞书、唯一发飞书、任务状态唯一权威）
         ⇅ HTTP 协议 v1（127.0.0.1:8765 + Bearer 令牌；迁线上只改 HUB_URL）
  Claude 执行器   Codex 执行器   …（执行器互不通信，主动长轮询领任务）
  桌面 Hook（Claude Stop/UserPromptSubmit、Codex notify）→ 只上报中间服务
```
- 分工：中间服务 + Claude 侧 + 协议由 Claude 实现；Codex 侧按 docs/CODEX_ADAPTER.md 由 Codex 实现；飞书桥代码 Claude 独占修改（单一写入者）。
- 被否决：在旧桥上增量改（两个 AI 同时改同一份代码导致状态分叉、Hook 直接发飞书违背单一出口）；云端控制面（关机无法执行，云端只多排队，隐私成本高）；Codex hooks.json Stop Hook（需持久化信任，桌面端不弹信任提示，不执行）。
- 用户决定：目录外授权选方案 C（执行器无确认模式，grants 恒为空，A4/A5 暂不满足）；目录缺失必须用户确认；Claude 默认 Opus 5.5 + effort low；Codex 续跑完全放开（--dangerously-bypass-approvals-and-sandbox）。
【飞书用法（路由规则）】- 私聊新任务严格格式 `【执行者 目录 内容】`（【】可省）：执行者 claude/codex；目录 = 默认目录 / 「xxx项目」（project_roots 一级子目录，大小写不敏感）/ 完整路径。不符合格式只回纠正示例 + 编号快捷操作（回复数字即执行），不建任务。
- `claude 项目列表` / `codex项目列表`：中间服务直接列出，不调 AI；回复「序号 内容」即在该项目建任务。
- 回复任务卡片：沿用卡片的执行者/会话/目录续跑；开头写「Codex执行：…」切换到同目录 Codex（同目录多个会话时拒绝以免串线）。
- 目录不存在 → NEED_DIR，回复路径或「默认」→ 回显 →「确认」才执行，绝不兜底。
- 危险关键词 → NEED_CONFIRM，回「确认」才执行；提示只有发起人可回复。
- 租约过期/执行中断/桌面队列超时 → NEEDS_RECOVERY，回「续跑」（带 resume_hint 重派）或「放弃」，绝不自动重跑。
- 「你分析，Claude执行」协作指令 v1 只记录不执行。
【任务状态机】RECEIVED → NEED_EXECUTOR/NEED_DIR/NEED_CONFIRM →（用户补充确认）→ QUEUED → LEASED →（desktop_queue: WAITING_EXTERNAL）→ RESULT_SAVED → DONE；旁路 FAILED、NEEDS_RECOVERY、CANCELLED。结果先落库再入发送队列，发送失败只重发不重跑；同 (executor,session) 与同目录同时最多一个租约；日上限按领取计数（续跑也算）。
【部署与运维】1. 计划任务（登录时启动，失败每分钟重启 999 次，pythonw 无窗口）：FeishuHub（`-m hub.main`，工作目录 feishu-hub）、FeishuHubClaudeExecutor、FeishuHubCodexExecutor；旧 FeishuClaudeBridge 已 Disabled。
1. Claude 桌面：~/.claude/settings.json 的 Stop→executors/claude/hook_stop.py、UserPromptSubmit→hook_prompt.py；CC-Switch 的 cc-switch.db（settings.common_config_claude 与 proxy_live_backup）同步为新 Hook，防 CC-Switch 覆盖。
2. Codex 桌面：~/.codex/config.toml `notify = [codex-computer-use.exe, "turn-ended", "--previous-notify", "[\"pythonw.exe\",\"…\\executors\\codex\\hook_stop.py\"]"]`；hooks.json 不挂 Stop（避免日后信任后重复上报）；Codex 执行器守护该串接。
3. 数据与日志：~/.feishu_hub/（config.json、token、hub.sqlite3、hub.log、executor_claude.log、executor_codex.log、runs/、spool/）。
4. 常用检查：`Invoke-RestMethod http://127.0.0.1:8765/v1/health`；`Get-ScheduledTask FeishuHub*`；查 tasks/outbox 状态；重启中间服务 `Stop-ScheduledTask FeishuHub` + 结束 `hub.main` 进程 + `Start-ScheduledTask`。
5. 回滚：停三个 FeishuHub* 任务 → 恢复 settings.json / config.toml / hooks.json / cc-switch.db 的 .bak-* → 从 ~/.feishu_bridge_bak_20260924b 恢复 listener.py → 启用 FeishuClaudeBridge。

**验证方法**: 两套测试 `python tests/test_hub.py`（79）与 `python tests/test_codex_executor.py`（20）全过；真实链路 2026-09-24 实测：Claude/Codex 私聊新建、回复续跑、Codex desktop_queue（桌面占用会话 → queue → 桌面 notify 回报匹配 → DONE）、桌面对话推送飞书均走通，1 小时 7 任务全 DONE、outbox 全 SENT；守护实测：人为冲掉 config.toml 串接后执行器启动几秒内补回。

**踩坑 / 已知异常与失败经验**: 踩坑：见同日 P 记录「【飞书自动化】多 AI 中转切换踩坑合集」。
【原状态说明】已完成（已上线运行；遗留：CX-3 测试偶发失败、手动 codex exec 也会推送卡片、需登录 Windows 才启动）

**关键文件与接口**: - docs/PROTOCOL.md — 执行器协议 v1：hello / claim（长轮询，领到即租约 90s）/ events（started·session·heartbeat·progress·result·failed·interrupted，(task,lease,seq) 幂等，每个事件续约）/ release（SESSION_BUSY）/ sessions/turns（桌面独立轮次）/ inbox（桌面同步）；错误码 LEASE_LOST、ALREADY_FINAL（终态重试视为成功）等。
- docs/CODEX_ADAPTER.md — Codex 执行器规格与验收 CX-1~CX-10。
- hub/store.py — SQLite(WAL)，所有状态迁移 CAS + BEGIN IMMEDIATE；表 tasks/events/msg_map/seen/outbox/turns/inbox/executors/task_starts/kv。
- hub/service.py — 路由、协议处理、统一发送出口 flush_outbox（飞书 uuid 幂等键、按回复目标保序、失败指数退避）、reap 回收、recover 重启恢复、离线补拉 backfill。
- hub/feishu.py — 飞书发送/回复/历史消息；结果卡片（标题「执行者 · 目录名」、副标题完整目录、超长按区块拆多张）。
- hub/api.py — ThreadingHTTPServer，hmac 比较令牌，请求体 ≤1MB。
- hub/config.py — ~/.feishu_hub/config.json（首次从旧桥导入 app_id/secret/白名单）、token、suggest_cwd=@SIRE_ROOT@\AI\SESSION、project_roots=[@CODE_ROOT@, @SIRE_ROOT@\AI]、daily_task_limit=20、task_timeout_sec=1800、危险关键词。
- executors/common/hub_client.py — 协议客户端（HubClient/TaskReporter/spool/flush_spool），执行器与 Hook 共用。
- executors/claude/executor.py — claude_exe=auto（自动选 Claude 桌面版自带最新 CLI，%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code\<版本>\claude.exe）；`--model claude-opus-5-5 --effort low -p --output-format json --permission-mode bypassPermissions`，续跑加 `--resume <sid>`；CLAUDE_CONFIG_DIR=~/.claude-feishu；结果与 session_id 从 JSON 输出取。
- executors/claude/hook_stop.py、hook_prompt.py — Claude 桌面 Stop 上报独立轮次（带 FEISHU_HUB_TASK_ID 则跳过）；UserPromptSubmit 从 inbox 取飞书往返注入上下文（ASCII 转义输出）。
- executors/codex/executor.py — 直接调用 npm 包内 codex.exe（不经 .CMD）；new→`codex exec --json -o <file> -`；resume→`codex exec resume … <sid> -`；会话被桌面占用（active writer 且未开始）→`codex queue --thread <sid> --message …` 只投递一次，上报 desktop_queue；MSIX 路径映射；启动时及每 60s 守护 ~/.codex/config.toml 的 notify 串接。
- executors/codex/hook_stop.py — 同时支持 stdin Stop JSON 和 notify 末参数 JSON（type=agent-turn-complete，字段 thread-id/turn-id/cwd/last-assistant-message）。
- tests/test_hub.py（79 项）、tests/test_codex_executor.py（20 项）— 进程内起中间服务、飞书打桩、假 CLI，不触网。

**状态**: 已完成

### F-042: 用现状审计建立项目基础文档基线并标出事实冲突
**日期**: 2026-09-25
**项目**: driverSoftware（D:\code\driverSoftware）
**关键词**: 项目基础文档清单, AI执行规则, AGENTS.md, 文档事实源, driverSoftware, 协议版本冲突, OpenAPI, 软件许可, SIRE文档审计

**需求场景 / 现象**: 仓库已有多个入口文档、AI规则、技能说明和历史文档，但缺少一份可供新项目搭建或现有项目补齐时使用的统一基础文档清单。用户记得之前做过该清单，需回溯知识后再核查当前仓库，避免重复造清单或把过期信息当成现行事实。

**方案 / 实施步骤**:
1. 检索共享知识库与向量库，回看既有记录 F-024/F-019，再检查当前项目规则和文档。
2. 按基础必需/条件必需/归档审计分类，记录每项用途、AI约束要点、事实源关系、当前证据及缺口。
3. 由独立审查角色检查清单覆盖、事实风险和提交范围，按建议修订并复核。
4. R7 对 T01-T10 做文件/仓库级检查，R8 核对需求映射、最终哈希和唯一文档提交；提交仅含目标文档，未推送。
方案 / 架构：新增 `docs/PROJECT-DOCUMENTATION-BASELINE.md` 作为基础文档分类、建档顺序和仓库差距清单。将 AI 规则、项目上下文、README/上手、测试、技能列为基础层；架构、安全配置、用户指南、API/协议、贡献、发布、CI、运维、许可/SBOM 依实际项目纳入。要求关键事实有唯一权威源，其他文档链接引用；将可证实事实、文档冲突、待核实结论分开表达。历史知识 F-024 仅借鉴规则分层结构，旧发布规则需重新核验；F-019 为较早工作流快照，不直接复制旧约束。

**验证方法**: 本次静态文档验收 T01-T10 均 PASS；R6A/B/C 独立审查及三路交叉复核 PASS；R8 集成复核 PASS；最终提交为 `927e9a4ece55a4ce27bb707c1720e9a0337d6308`，仅包含清单文档且工作树干净。没有运行应用、安装包、项目测试、构建、服务或硬件验证，因此不能据此宣称它们通过。

**踩坑 / 已知异常与失败经验**: 根因：（问题类必填）: 项目知识分散在 README、AGENTS、CLAUDE、docs、skills、构建脚本和打包说明中，规则之间存在启动命令、协议版本、测试方式和 wheel 版本等不一致；目录清单也不能单独裁决哪个说法才是运行时事实。
踩坑：旧文档相互引用容易制造虚假权威。例如协议材料出现 V3.1/V3.2/V3.3/V3.4 多种线索，wheel 版本和启动入口也不一致；用静态文档无法定性固件兼容矩阵、供应商 wheel 再分发许可、真实安装/服务行为。应在清单中写成明确待核实项，保留证据来源，不自行挑一个版本。法律授权须有明确许可/供应商证明，打包备注不是许可证。
【原状态说明】已完成；产出为可复用的项目文档基线和有边界说明的仓库审计，适用于启动类似项目的文档规划，不能替代针对各项目的事实核验。

**关键文件与接口**: - `docs/PROJECT-DOCUMENTATION-BASELINE.md` — 当前仓库基础文档盘点、优先级和补齐清单。
- `AGENTS.md`、`CLAUDE.md`、`README.md`、`docs/`、`skills/`、`.gitlab-ci.yml` — 盘点范围内的项目规则、入口、技能、CI 文档和配置。
- `.sire/runs/R20260925-053031/evidence/U-01/qa/r7-results.md` — T01-T10 文件/仓库级验收记录。
- `.sire/runs/R20260925-053031/evidence/U-01/qa/r8-integration.md` — 提交边界、交付一致性和跨单元验收。

**状态**: 已完成

### F-043: 项目基础文档基线（可迁移完整原文）
**日期**: 2026-09-25
**项目**: 可迁移的项目搭建知识；来源为 driverSoftware 提交 `927e9a4ece55a4ce27bb707c1720e9a0337d6308`
**关键词**: 项目基础文档清单, 项目搭建, AI执行规则, AI约束, 项目规范, 文档基线, 可迁移文档, driverSoftware, F-043, 完整原文, Markdown, SIRE知识库

**需求场景 / 现象**: 用户需要将项目搭建基础文档用于后续迁移。文档曾误加入 driverSoftware 仓库，用户要求只存入其 SIRE 知识数据库，以便之后复用。

**方案 / 实施步骤**:
## 怎么使用这份清单

- 新项目按「核心必备」先建文档；「按项目条件」按产品形态和风险选用，不为凑文件数量而拆文档。
- 每个主题指定一个唯一事实来源。其他入口只摘要并链接它；命令、版本、配置和流程不要在多个文件各自维护。
- 可以合并简单项目的短文档，但保留清晰章节、责任人和链接。随着项目复杂度增长，再拆成独立文档。
- 项目规则写成可核对的动作：什么情况下触发、必须/禁止什么、用什么证据验收、哪些动作需要用户授权。
- 文档中标明适用平台和版本。没有实测的命令、路径、硬件流程和结论，要明确标为未验证。

## 一、核心必备文档

| 文档 | 唯一职责与最低内容 | 建议验收点 |
|---|---|---|
| `AGENTS.md`（或项目选定的 AI 主规则文件） | AI 项目级执行合同：规则适用范围与优先级、开工前必读顺序、用户沟通语言、需求拆分、允许/禁止操作、外部副作用授权边界、代码/文档修改流程、验证与证据要求、提交/推送/发布边界、文档维护要求 | 新会话能按入口找到正确上下文；规则用“触发条件—动作—证据—授权”描述；不要求 AI 猜测权限或唯一事实源 |
| `docs/PROJECT-CONTEXT.md` | 稳定的项目背景和协作地图：项目目标/边界、模块/仓库/服务关系、需求入口、结果回填位置、交接机制、外部资源、本机配置的逻辑名称与存放位置 | 不放密钥或易变的个人绝对路径；首次接手者能知道从哪里取需求、交付结论 |
| `README.md` | 面向开发者的项目入口：项目用途、能力边界、技术栈、目录导览、快速安装/启动、文档导航、已知限制 | 快速开始的每条命令已在目标环境验证；链接有效；与安装脚本和规则文件一致 |
| `docs/ONBOARDING.md` 或 `docs/DEVELOPMENT.md` | 开发者环境搭建：依赖和版本、安装、配置、运行、常见故障、接手验收、清理方式 | 新环境按文档能完成启动；依赖安装不污染用户全局环境；配置示例不含真实秘密 |
| `docs/TESTING.md` | 测试总索引：测试层级和目的、可运行命令、环境/硬件前置、通过标准、人工检查边界、失败时证据采集；链接专门测试用例和技能 | 明确单元、集成、UI、硬件/现场测试各自的执行条件；静态检查不冒充运行验证 |
| 模块/场景技能，如 `docs/skills/` | 仅写特定模块或高风险场景的细节：技术不变量、操作顺序、排查步骤和验证方式 | 适用范围明确；被主规则中的“模块→必读文档”索引准确引用；内容与当前代码/工具匹配 |

### AI 执行规则至少要说清

1. **任务入口与范围**：从哪里读取需求；如何区分用户目标、项目现状和历史记录；不确定时先做哪些独立检查。
2. **执行约束**：改动前的阅读要求、修改范围、数据/凭据处理、对其他仓库和设备的边界。
3. **风险动作的授权**：例如删除或覆盖数据、向设备写入/运动、使用秘密、向外部系统发消息、部署、推送或正式发布；分别规定何时必须先得到用户明确指示。
4. **验证与证据**：按改动风险列出需要运行的命令、人工/可见验收条件、证据落点；明确没运行的检查必须如实说明。
5. **完成与交接**：结果写到哪里、文档何时同步、是否需要审查、提交/推送的界线以及最终汇报格式。

硬件控制、数据迁移和安全敏感项目应把高风险动作拆成独立条款，写明安全前置条件、停机/回滚方式和操作者确认点。不要只写“谨慎”“确保质量”等无法验收的口号。

## 二、按项目条件选用的文档

| 文档 | 适用条件 | 应覆盖内容 |
| `docs/ARCHITECTURE.md` | 多模块、多服务或关键数据流较复杂 | 组件边界、依赖方向、主要数据流、接口所有者、关键不变量、外部系统关系；简单项目可由 README 的架构章节承担 |
| `docs/CONFIGURATION.md` / `docs/SECURITY.md` | 有环境变量、凭据、用户数据、外部服务或权限边界 | 配置来源和优先级、秘密的保存/注入/轮换、日志数据分类、最小权限、样例配置和撤销办法 |
| 用户指南/操作手册 | 项目有非开发者操作者或现场流程 | 常见任务、输入输出、状态与错误处理、安全前置条件、恢复/停止操作 |
| API / 协议 / 数据格式规范 | 有服务接口、设备协议、文件格式、跨进程或跨团队契约 | 字段和编码、错误处理、兼容规则、版本对应关系、规范真相源和变更同步责任 |
| `CONTRIBUTING.md` 或开发流程章节 | 多人协作、代码审查或特定分支流程 | 分支、提交、审查、合并、回滚；通用 AI 规则应链接主规则，不复制一份 |
| `CHANGELOG.md` 与版本策略 | 持续交付、需要追踪用户可见变更 | 版本号唯一来源、兼容策略、升级/停发说明、用户可读变更记录 |
| `docs/BUILD-AND-RELEASE.md` / `docs/PACKAGING.md` | 有构建产物、安装包、容器或部署 | 构建入口、环境、产物、排除项、签名、发布触发、验收、回滚 |
| CI/CD 配置说明 | 存在自动化验证或发布流水线 | 触发条件、门禁、产物、机密变量管理、发布责任；文档应解释实际配置，不能另造流程 |
| 运维与备份恢复手册 | 有线上服务、持久化数据、现场设备或长期运维 | 监控、日志、备份、恢复、升级、回滚和故障采集 |
| `LICENSE` / `NOTICE` / 第三方清单（如 SBOM） | 所有项目都应确认项目权属；尤其使用或再分发第三方组件时 | 项目许可/内部使用状态、依赖许可证、版权声明、供应来源、再分发义务和责任人 |

## 三、目录入口与唯一事实源

建议在主规则中保留一张映射表，而不是重复正文：

| 修改区域/任务 | 必读的项目上下文 |
|---|---|
| 全部任务 | AI 主规则、项目上下文、README、相关测试说明 |
| 指定模块 | 对应架构/接口说明和该模块 skill |
| 接口或协议变更 | 当前版本的规范、兼容矩阵、相关单元/集成测试 |
| UI 变更 | UI 测试指南、可见验收方式和对应页面说明 |
| 发布/部署变更 | 版本策略、构建/发布说明、CI 配置和回滚步骤 |

其他 AI 工具的入口文件（例如 `CLAUDE.md`、Copilot 或 Cursor 规则）只保留工具特有启动信息和主规则链接。若工具必须有专用约束，注明它与主规则的关系及维护责任，避免出现两套不一致的硬规则。

## 四、建议的建档顺序

6. 定义项目目标和约束，创建 `README.md`、AI 主规则和项目上下文。
7. 建立可重复的新环境安装/启动流程，并据此完成 `ONBOARDING.md`。
8. 按真实代码边界补充架构、接口/协议规范和模块技能；在 AI 主规则中建立必读映射。
9. 建立测试总索引、配置/安全说明和用户手册，填入可运行的真实命令和验收条件。
10. 有持续交付时补齐版本、变更记录、构建发布、CI 和回滚文档；确认项目与第三方许可义务。
11. 每次改动命令、接口、版本、配置键或发布流程时更新唯一事实源；在合并前检查死链、过期路径和相互冲突的说法。

**验证方法**: 从引用区块逐行移除 `> ` 后以 LF 拼接，核对令牌化正文 SHA-256 为 `7796705122a4a3496313db7a46cd13e493542f71f2f7978608e6c2bf42b2008c`、长度 `15696` bytes；再将唯一 `@CODE_ROOT@` 替换为源提交中对应的根路径原文，核对恢复的来源 Git blob SHA-256 为 `41ce790df8aa2a7387152e0e3a39cde4fecc42f1ef3f7698c4faf373d4681c7b`、长度 `15692` bytes/`115` lines。另在共享知识 Markdown 与 machine/shared SQLite 中验证 F-043 唯一性、正文一致、FTS/向量检索、embedding 与数据库 integrity/manifest；逐库证据位于当前 run `evidence/U-01/remediation-002/`。

**踩坑 / 已知异常与失败经验**: ## 五、driverSoftware 当前复查

### 已有且可复用

| 主题 | 仓库现有入口 | 判断 |
|---|---|---|
| AI 项目规则与模块映射 | 根目录 `AGENTS.md` | 主规则较完整，覆盖中文协作、工作流、测试、硬件和发布边界；应继续作为 AI 规则唯一源 |
| 项目上下文 | `docs/PROJECT-CONTEXT.md` | 已说明需求来源、结果回填、相邻资源、本机配置分层和协作方式 |
| 新人接手 | `docs/ONBOARDING.md` | 已有 Windows 环境、权限、凭据、硬件和接手步骤 |
| 模块技能 | `docs/skills/` | 已有硬件、reader、再标定、UI、自测和排障资料；其中个别入口已过期，见下方问题 |
| 用户操作指南 | `frontend/guide/` | 面向应用操作的指南已存在；其中 `tests.md` 是应用内测试功能的使用说明，不等同开发测试标准 |
| 构建和发布 | `docs/PACKAGING.md`、`scripts/`、`.gitlab-ci.yml` | 有打包规则、脚本及 tag 触发的 CI 链路；CI 实际定义在 `.gitlab-ci.yml`，文档要与它同步 |
| 依赖与启动 | `requirements*.txt`、`setup.bat`、`start.bat` | 入口存在，但 README、规则文档和启动脚本的说明不完全一致 |
| 协议资料 | `docs/protocol/`、旧入口 `docs/rs485_protocol.md` | 有版本化协议文件；当前版本指向存在实质冲突，不能仅改一个链接解决 |

### 需要统一或补充的事项

| 优先级 | 发现 | 建议动作 |
| P0 | **协议现行版本和 host 实现说明存在冲突。** `docs/protocol/README.md` 说当前固件是 V3.3；同目录 `rs485_v3.3.md` 又说明固件 v3.4.0+ 已改 MIT 刻度/参考系，且仓内没有 V3.4 正文；`AGENTS.md` 概括 host 仍是 V3.2，`core/protocol.py` 头注也标 V3.2，`core/__init__.py` 和 README 另有 V3.1 描述。host 命令层还按固件档案处理行为：`core/commands.py` 注释为 V3.3 MIT 发送布局、V3.2 telemetry 解码，`core/fw_profile.py` / `firmware_profiles/` 提供随固件版本变化的量程档案，仓内包含 v3.4.x 档案。旧的 `docs/rs485_protocol.md` 已自标过期，但 `CLAUDE.md` 仍引用它。 | 先对照固件仓的 `register_protocol.h`、固件 tag 与上位机实际帧编解码及档案分支建立固件—协议—host 兼容矩阵；确认后再指定唯一当前规范。没有完成这项核实前，不把 V3.3 或 V3.4 写成已确认的当前唯一版本。将旧协议入口替换为有效索引。 |
| P0 | **wheel 版本/平台标签冲突。** 仓内实际文件为 `vendor/kingkong_calib-1.0.1-cp312-cp312-win_amd64.whl`，`requirements.txt`、锁文件和安装流程 pin 1.0.1；但 `README.md` 说 wheel 待加入，`vendor/README.md` 和 `docs/skills/encoder_calib_wheel.md` 仍写 1.0.0、`cp312-none-any`，`CLAUDE.md` 也写错 wheel 标签。 | 以实际 wheel、requirements pin 和可验证的安装结果统一依赖说明；清理旧文件名、平台范围及过时外部路径。不要把 Windows x64 wheel 描述成通用平台 wheel。 |
| P0 | **快速启动入口不一致。** 根 `README.md` 展示系统 `py -3.12 -m pip install` / `py -3.12 server.py`；`AGENTS.md` 的开发速查和 `ONBOARDING.md` 要求依赖进入仓内 venv，但 `AGENTS.md` 的 worktree 示例又用系统 `py -3.12 server.py`；`CLAUDE.md` 启动/硬件测试示例和 `docs/PACKAGING.md` 的浏览器启动表也写系统 Python。`start.bat` 在 venv 缺失时会退回系统 Python。 | 统一 README、AGENTS（包括 worktree 例子）、ONBOARDING、CLAUDE 和 PACKAGING 中推荐的开发/测试入口；明确 `start.bat` 的系统 Python fallback 是支持路径还是应移除，保证脚本行为与“禁止全局安装”的规则一致。区分开发运行入口和 CI/打包命令。 |
| P1 | **测试说明散落且有过期 skill。** 没有统一 `docs/TESTING.md`；`docs/ui_test_cases.md` 是 UI 用例，`frontend/guide/tests.md` 是产品功能说明。被 `AGENTS.md` 指定的 `docs/skills/playwright_ui_self_test.md` 仍使用 `new-webgui/web_gui/` 路径和 headless 操作，而当前前端位于 `frontend/`，主规则要求最终用户可见验收使用可见 GUI。 | 建立测试总索引，分清单元、服务集成、UI、硬件测试；更新/替换过期 UI skill，写清自动化诊断和最终可见验收各自的范围与通过标准。 |
| P1 | **架构与 API 信息未形成统一入口。** `CLAUDE.md` 独有较多组件、端点、WebSocket 和不变量说明。FastAPI 默认生成 OpenAPI 文档，因此不能说 REST API 完全没有规格；问题在于没有指定 OpenAPI/代码/文档谁是维护真相源，WebSocket 契约也未集中说明。 | 先把经核实且仍有效的 CLAUDE 独有信息迁移到选定的架构/测试/API 文档，再将 `CLAUDE.md` 收敛成 AI 主规则入口和必要的工具特有说明。明确 REST OpenAPI 的责任源及 WebSocket 契约维护处。 |
| P1 | **许可证和第三方再分发状态未闭环。** 根目录未见独立 `LICENSE`、`NOTICE`、`COPYING` 文件；README/AGENTS/CLAUDE 说明项目为 `UNLICENSED` 内部使用。打包产物内有 Chromium/Electron 许可证文件，但这不能代表源码根目录说明完整。wheel skill 中“无 license / 无网络验证”描述的是安装/激活行为，不能据此判断著作权许可证或再分发授权；该文档本身不足以证明 vendor 分发权。 | 确认项目权属以及 wheel/vendor 的授权和再分发条件；按实际义务补充第三方声明或依赖清单。仅有“内部使用”说明或技术上的激活行为说明，不能替代第三方组件的授权核实。 |
| P2 | **其他维护入口仍可能漂移。** README 对 wheel 的存在状态已过期；`CLAUDE.md` 同时有过时规则、命令、协议入口和 wheel 文件名。 | 建立 README 文档导航；在移动 CLAUDE 独有有效信息后，将工具适配入口缩成短指针；每次改命令/依赖/协议时检查 README、AGENTS、ONBOARDING、skill 和脚本的一致性。 |

### 当前最小补全清单

1. 核对固件与 host 兼容矩阵，决定当前协议规范版本及其唯一入口。
2. 统一 README、ONBOARDING、AGENTS、CLAUDE、PACKAGING 与启动脚本的安装和启动方式。
3. 修正 wheel 版本/平台标签，并清理旧路径、旧文件名和无效外部依赖描述。
4. 新增 `docs/TESTING.md`，更新过期 UI skill 和 CLAUDE 测试说明。
5. 迁移并核实 `CLAUDE.md` 中的架构、端点和不变量内容，再让该文件成为主规则的薄适配层。
6. 确认项目及 vendor 第三方组件许可/分发边界，补充适用的声明或清单。

## 六、查找范围与限制

- 已检查仓库规则、README、项目上下文、onboarding、测试相关文件、协议入口、打包/CI、依赖与 wheel 文件名，并搜索仓库 Markdown 文件名和标题。
- 在 driverSoftware 仓库、仓库内 `.sire/runs`、`@CODE_ROOT@\.sire/runs` 和共享知识中查找过往项目基础文档清单。未找到一份独立旧清单。最近似的归档是 SIRE F-024（AI 工程化基建模板）和 F-019（2026-09-15 的仓库工作流快照）；F-024 可参考其规则分层，但示例版本/流程仍需以当前仓库核实；F-019 记录的版本基线与部分发布规则已可能过时或与当前 `AGENTS.md`/CI 不一致，只作历史定位，不直接照抄。两者都不是完整的新项目文档目录清单。
- 这次是静态文档与路径复查；没有运行项目测试、构建、服务或设备流程，也没有读取固件仓来裁定当前固件版本。因此协议兼容矩阵、安装成功、第三方再分发授权仍需分别核实。
- 本清单是项目文档设计与现状审计，不代替各模块规范、脚本行为或用户授权。

**关键文件与接口**: 来源 `driverSoftware/docs/PROJECT-DOCUMENTATION-BASELINE.md`；来源提交 `927e9a4ece55a4ce27bb707c1720e9a0337d6308`；SIRE 规范源 `knowledge/global/global_dev_features.md`；生成索引 `knowledge/global/global_index.json`。

**状态**: 已完成

### F-044: Unity/Blender 战车 RPG 的美术启动约定
**日期**: 2026-09-27
**项目**: GAME（原创废土战车 RPG）
**关键词**: Unity 美术, Blender, 战车, 模块化武器, 挂点, 俯视 2.5D, Low-poly, Toon, 废土, 资产生产

**需求场景 / 现象**: 游戏机制实现与美术准备并行；项目 GDD 已确定固定俯视 2.5D、Low-poly/Toon、低饱和盐尘色系，并在 `Data/parts.csv` 定义车辆武器挂点。

**方案 / 实施步骤**:
方案要点：
美术准备先建立视觉基线和首辆轻型车的可读剪影，再扩充环境与敌人；可替换武器作为独立网格。轻型底盘挂点必须精确命名 `Mount_Main`、`Mount_Sub`，以现有 75mm 炮和 7.7mm 机枪数据作首批装备对照。车轮布局与比例属于待镜头/导入验证的制作提案；Unity 坐标按项目协作约定固定为 1单位=1米、Y-up、车辆前向+Z，武器炮口+Z。

**验证方法**: 概念 SVG 可解析；挂点和武器 ID 与 CSV 对照一致。Unity 工程根目录为 `UNITY/`；未执行 Blender/FBX/Unity 导入，也未通过真实俯视镜头验收。工作区中尚无本概念对应的 Blender 源文件或 FBX；最终比例、材质表现和换装效果需在 Unity 中确认。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: `D:/code/GAME/docs/ART_BIBLE.md`; `D:/code/GAME/UNITY/Assets/Art/Concepts/TNK_Light_Rover_Concept_v01.svg`。

**状态**: 已完成

### F-045: 舵机加密OTA的协议及ACK丢失恢复
**日期**: 2026-10-08
**项目**: driverSoftware
**关键词**: 加密OTA, AES-128-CBC, PKCS7, Bootloader3.4, SetCrypto, ACK丢失, 会话恢复, 96B, 明文兼容

**需求场景 / 现象**: 舵机 Bootloader 3.4 同时支持明文与加密 OTA，上位机需要显式选择加密，3.3 及以下继续明文。

**方案 / 实施步骤**:
1. 按 workspace.json 找固件，读取包含加密实现的分支，而非默认检出版本；双端密钥逐字节核对。
2. Boot Ping 确认版本 ≥3.4，SetCrypto 有效 ACK 后才能 SetMode 和擦写，不自动降级明文擦写。
3. 克隆命令对象隔离加密状态，使用 OTA 互斥锁阻止并行流水线。
4. 留在 boot 时密文关闭；开启被拒或关闭 ACK 丢失时再尝试明文关闭，失败提示重启。Jump ACK 丢失时提示先重连确认。
方案 / 架构：完整含 CRC16 的命令帧先 PKCS7 补齐，再 AES-128-CBC 加密；线上为随机 IV(16B) + 密文。Ping 和回复为明文。初次 SetCrypto 开启为明文，加密状态下关闭也必须密文。采用已有 pycryptodome，不复制固件纯 Python AES。API encrypt 默认为 false，页面按 boot Ping 的版本允许选择。

**验证方法**: 相关 pytest 87 项通过，其中加密用例 21 项；固定 IV 与固件 3.4 脚本七种帧长度逐字节一致；可见 Chrome 经真实页面/HTTP 与模拟 boot 完成加密、明文、旧版明文、开启无 ACK 四条路径。未连接真机，不能作为 Analyzer 或 boot 实体验收。

**踩坑 / 已知异常与失败经验**: 踩坑：固件主检出脚本仍使用旧测试密钥；3.4 分支已改为与 Boot 一致。照主检出脚本复制会导致开启后命令全部无回应。不能把脚本“恒明文关闭”的旧注释当真相，新 Boot 在加密状态下只接受密文关闭。
【原状态说明】软件实现与模拟验收完成，真机可见 GUI 验收待设备及逐次 OTA 授权。

**关键文件与接口**: - core/ota_crypto.py — encrypt_frame，64B 写块产生 96B 下行帧。
- core/commands.py — boot_set_crypto、_boot_send_raw，严格检查开关 ACK 的 CRC/ID/子命令/status。
- server.py — OtaFlashReq.encrypt、api_ota_flash，版本拒绝与会话恢复。
- frontend/js/pages/bootloader.js — 加密选择、确认文案、升级结果。

**状态**: 部分完成

### F-046: 打包应用通过兼容 profile 切换多仓库组合
**日期**: 2026-10-10
**项目**: EncoderPlotter 多仓库打包切换方案（架构咨询）
**关键词**: Git 子模块, submodule, 主仓库分支, 打包, 运行时切换, profile, manifest, commit SHA, launcher, 版本组合, rollback

**需求场景 / 现象**: 主仓库有多个需求分支，父仓库分别固定四个子模块的不同提交；希望在已打包桌面应用中点按钮切换兼容组合。工作区 EncoderPlotter 仓库包含 sub_embedded、sub_common、sub_algorithm、sub_automation。

**方案 / 实施步骤**:
方案要点：
将可选分支组合映射为有限的、CI 构建并验证过的 profile。manifest 固定主程序及四个子仓库的 commit SHA、应用/接口版本、构建产物路径和 SHA-256。仅切子模块且存在稳定 API/插件边界时，可在一个主程序包内并列加载模块；否则选择完整 profile 并重启。主仓库分支也有代码差异时，profile 必须包含完整应用构建产物，由稳定 launcher 切换版本；当前应用的按钮可以请求 launcher 完成停进程、校验、原子启用和重启。离线包预置允许 profile；在线方案下载签名产物，校验成功后启用，失败时保留旧版本。禁止把 git checkout 当成打包产品的运行时切换机制。

实施步骤：
1. 建立允许组合与接口兼容矩阵，拒绝任意主/子仓分支拼接。
2. CI 按父仓提交递归取出四个 gitlink，构建完整 profile 并生成 manifest。
3. 通过同级版本目录发布 profile；launcher 先校验，再原子切换并保留一个可回退版本。
4. 真实验收覆盖正确组合启动、缺包/哈希错误拒绝切换、进程占用和启动失败回滚。

**验证方法**: 本条是未实现的架构建议，没有修改源代码、构建安装包或执行 UI 测试。实施后应在真实打包应用测试：选择的 profile 与五个提交 SHA 一致；无效清单保留旧版本；切换失败能恢复旧版。

**踩坑 / 已知异常与失败经验**: Git 分支和子模块工作树是构建期源码状态。打包后的可执行文件只包含当时编译进去的主程序与资源，不能因为 UI 点击就检出另一个主仓库分支；普通安装包也不会自动包含 Git 源码仓。
包内同时放多个完整主程序会增加体积；Electron/ASAR 资源路径和 Windows 文件占用可能阻止覆盖；Python 后台服务、设备句柄和配置迁移会影响重启与回滚。先采用 side-by-side 目录和进程重启边界，不要原地覆盖正在运行的文件。

**关键文件与接口**: - 父仓库提交中的 Git gitlink — 固定每个子模块的具体 commit。
- `profiles/<profile-id>/manifest.json` — 建议清单，包含主仓/子仓 SHA、兼容范围、产物路径与哈希。
- 稳定 launcher 的 `activateProfile(profileId)` — 停止进程、检查清单和文件、切换当前版本目录并重启。

**状态**: 部分完成

### F-047: MPT arguments 解耦：'a'指令字段自描述查询（V4.2.1）
**日期**: 2026-10-10
**项目**: Analyzer_Encoder_DebugTest（C:\Users\Administrator\Downloads\Analyzer_Encoder_DebugTest；Test Script + Test Report，2026-10-09 V4.2.1 第6轮报告）
**关键词**: MPT, arguments解耦, 'a'指令, ARGUMENTS字段自描述查询, queryArgumentsField, getArgumentsByFieldQuery, argumentsLayoutToBuffer, verifyArgumentsFieldQuery, argumentsReadMethod, argumentsVersion=6, EncoderArgumentsV6, batSpeedMode, argumentsFieldLayoutTable, USARTInterface_Recali.c, fieldCount, ArgumentsErrorStatus, 'R'整块读取, EncoderBase.py, Analyzer, A~F协议回归, IAP, series=104, V4.2.1, a3950c3

**需求场景 / 现象**: MPT 固件的 ARGUMENTS 结构体加字段/改布局（argumentsVersion 3→5→6）时，上位机用 'R' 整块读回 + ctypes 按版本硬解析，必须每版同步改结构体，固件与上位机强耦合。MPT V4.2.1 起固件新增 'a' 指令（提交 a3950c3），让每个字段自描述（名字/偏移/大小/类型/值），上位机据此解耦。

**方案 / 实施步骤**:
方案 / 架构：- 请求：`'a' + fieldIndex(u8) + CRC8`；响应：`status + payload + CRC8`，payload 小端：schemaVersion(1) argumentsVersion(4) fieldCount(1) fieldIndex(1) fieldOffset(2) fieldSize(1) fieldType(1: 0=u8/1=u16/2=u32) nameLength(1) name value。
- fieldIndex >= fieldCount 时固件回 status=ArgumentsErrorStatus(2)，作为遍历结束信号。真机 34 个字段，值与 'R' 整块逐字节一致（2026-10-08 验证）。
- 上位机：从 index=0 遍历到结束信号，校验响应回显 index、fieldCount==实际条数、上限 64 个字段；任一步失败整体返回 None，不返回半成品。
- 兼容策略（折中，并未彻底去掉结构体）：`argumentsLayoutToBuffer` 按 offset 把字段值拼回原始字节（空洞补 0，总长按 4 字节向上取整，真机 72B），再喂给原有 `ArgumentsHeader/EncoderArgumentsV5/V6.from_buffer_copy` 解析，所以下游代码零改动；通过 `modes["argumentsReadMethod"]`（"R" 默认 / "a"）或 `getArguments(readMethod=)` 切换，`layout` 同时保存在 `Arguments.argumentsLayout` 里。
- `byName` 字典（name→小端整数）可直接按字段名取值，是真正解耦用法的入口，目前未被主流程使用。

**验证方法**: （报告 V4.2.1_L6EB981C478199E94，2026-10-09，真机）:
- IAP：1941/1941 包、496736 字节、43.3s，整区擦除(page7~127+Bank2)+0x5EE5 校验+0x6FF6 复位，刷机后 argumentsVersion 3→6、series 105→104。
- 全程 'a' 路径读 Arguments 的 A~F 回归：20 项主流程全 PASS，42 组分辨率覆盖矩阵全 PASS，CRC 失败 0，656.1s。'a' 路径首次在完整回归下验证通过。
- 基线 Arguments（'a'读出）：series=104, interface=202, baudrate=2500000, busID=31, internalResolution multi16/single17, hallNumber=9, rotorSize=15, sectionNumber=36, software=67240192, algoVersion=4060, batSpeedMode=0。

**踩坑 / 已知异常与失败经验**: 踩坑 / 限制：- 固件字段表 `argumentsFieldLayoutTable`（USARTInterface_Recali.c）是人工维护静态数组：固件给 ARGUMENTS 加字段忘加表项时，'a' 会静默漏字段；用 verifyArgumentsFieldQuery 查 uncoveredRanges 里 nonZero 区间来发现。
- 'a' 不报告对齐空洞/尾部 padding，拼回时补 0。
- 老固件（argumentsVersion<6、series=105 等）不支持 'a'，需回退 'R'；刷机前读取仍走旧路径。
- 'a' 每字段一次往返（34 次），比 'R' 慢，高频读取场景别用。
- 后续解耦待办：主流程仍依赖 ctypes 结构体；若要彻底解耦，应改用 byName/字段名 + offset 的动态映射，并保留 'R' 兜底；写入侧（getUpdateArguments/dict_to_init_arguments）仍按 argumentsVersion 分支硬编码，未解耦。
【原状态说明】已完成（只读分析归档；未改动任何脚本/固件）

**关键文件与接口**: （Test Script 目录）:
- `EncoderBase.py:1101-1248` — ARGUMENTS_FIELD_QUERY=ord('a')、queryArgumentsField（state: ok/end/status/fail，重试3次）、getArgumentsByFieldQuery、argumentsLayoutToBuffer、verifyArgumentsFieldQuery（'R' vs 'a' 逐字段对照 + 未覆盖区间非零检测）
- `EncoderBase.py:1306` getArguments(readMethod) ；`EncoderBase.py:2728+` Arguments.__init__/initArgumentsFromBuffer 里 readMethod=="a" 分支；`EncoderBase.py:2814-2822` argumentsVersion 5/6 → EncoderArgumentsV5/V6
- `DataFormatter.py` EncoderArgumentsV6（V5 末尾多 batSpeedMode，其余偏移不变）
- `test_mpt_protocol_regression_AtoF.py:1729` 回归脚本显式切 'a'；`test_iap_mpt20_standalone.py` IAP 刷机流程
- 协议脚本：mpt_0x64_protocol.py(RS485/422 0x64，5/7字节两种帧)、mpt_ssi_protocol.py、mpt_bus_protocol.py、mpt_t485_protocol.py、bissc_protocol.py；CRC.py(CRC8 多项式 x8+x7+x4+x2+x1+1)、Analyzer.py(M487_Universal 读取器 USB)

**状态**: 已完成

### F-048: EncoderPlotter_0903_01 数据生成四条链路与基线分叉（feature/data-generation）
**日期**: 2026-10-10
**项目**: EncoderPlotter_0903_01（分支 feature/data-generation，从 feature/iap-ota-sn@19072126 切出）
**关键词**: 数据生成, 生成标定数据, generateData, generatedDualData, ged_P, ged_Q, ged_T, IAP文件生成, EncoderCommandIapGenerateFile, iap-file-generator, 恢复出厂, feature/data-generation, feature/iap-ota-sn, develop 分叉

**需求场景 / 现象**: 用户说"新建分支处理数据生成的相关逻辑"。"数据生成"在本仓库不是唯一指代，直接动手会改错链路；两条基线（develop 与 feature/iap-ota-sn）的生成代码也不同，从哪切决定能改到什么。

**方案 / 实施步骤**:
1. `git grep -n "generateData(\|generatedDualData(" <ref> -- controller/python/Encoder.py`，对比两条基线
2. 让用户选基线和链路；本次用户选了 feature/iap-ota-sn，链路后续再提供
3. `git switch -c feature/data-generation feature/iap-ota-sn`；子模块不建分支，等真要改子仓时再按"子先父后"同名建
方案 / 架构：先定位全部调用点，再让用户选链路和基线。算法本体 `sub_algorithm/main.py generateData/generatedDualData` 归算法部门，不改，只改调用侧。主仓调用侧分四条链路（以 feature/iap-ota-sn@19072126 为准）：
4. 标定流程（再标定/局部标定采完霍尔后）：`controller/python/Encoder.py` ~3485/3495
5. IAP 升级第一阶段（进再标定采数据 → 生成新标定 P/Q/T → 刷固件后写回）：`Encoder.py` ~1503/1513
6. IAP 文件生成（离线，调试日志 + BIN → 生成 → 按布局合入 BIN → 加密）：`components/share/iap-file-generator.js` + `Encoder.py` ~2406；命令 `EncoderCommandIapGenerateFile`（`sub_common/Defines.py:93`、`controller/defines.js:95`）
7. 恢复出厂（按 arguments 版本重新生成写回）：`Encoder.py` ~4680/4718
另有 MES 不良码 `0-1-0-4 数据生成失败`（`sub_common/DefectiveItems.py:36`、`components/encoder/mes/mes.js:31`）。

**验证方法**: HEAD == feature/iap-ota-sn == origin/feature/iap-ota-sn == 19072126，工作区干净，四个子模块 pin 不变。

**踩坑 / 已知异常与失败经验**: 踩坑：叠在 feature/iap-ota-sn 上的分支，MR 目标应先指向 feature/iap-ota-sn（或等它合进 develop 后 rebase），直接对 develop 提 MR 会把那 109 个提交一起带上。如果改到 MPP 的 IAP 生成，记得 develop 上 8c0b948b 那条修复这条线上没有。
【原状态说明】部分完成（分支已建，具体改动范围待用户提供）

**关键文件与接口**: - 基线分叉（2026-10-10）：feature/iap-ota-sn 比 origin/develop 多 109、少 9 个提交。develop 上 Encoder.py 只有 4 处 generateData 调用，没有 IAP 文件生成模块；develop 独有 `8c0b948b fix: IAP 升级时重新生成标定数据，MPP 不再两个分支都落空`，feature/iap-ota-sn 上没有。

**状态**: 部分完成

### F-049: CI tag写入target并在内部版界面显示
**日期**: 2026-10-12
**项目**: EncoderPlotter_0903_01 / 当前仓库
**关键词**: Git tag, CI_COMMIT_TAG, target.json, internal build, 构建标签, versionSuffix

**需求场景 / 现象**: CI 由 Git tag 触发打包，但应用左下角版本与设置页仍显示 commit hash，难以直接识别安装包对应的 tag。

**方案 / 实施步骤**:
方案要点：
gen-target.mjs 将 CI_COMMIT_TAG 写入 target.tag。版本组件仅在内部版显示该字段：左下角版本后缀和设置页构建标签；内部 test 包的测试版号字段优先显示 tag。外部版隐藏，未带 tag 的本地构建回退原显示行为。

实施步骤：
1. 读取 GitLab 预定义的 CI_COMMIT_TAG，无需为每个 tag 构建 job 重复传参。
2. 内部版显示完整 tag；外部版不显示。
3. CI 无 tag 时保持原有随机 stamp/版本逻辑。

**验证方法**: 用测试 CI_COMMIT_TAG 生成 target.json 并确认 tag 字段存在；Node 语法检查与 git diff --check 通过。真实 Electron 界面操作未执行，待 GUI 环境验证。

**踩坑 / 已知异常与失败经验**: gen-target.mjs 只将 CI_COMMIT_SHORT_SHA 写入 randomStamp，未把 CI_COMMIT_TAG 编入 target.json，渲染层没有可读 tag。
test/dev 包原先在左下角后缀和设置页显示 commit 短 hash；内部版应以 Git tag 作为识别名，同时保留 commitInfo 哈希用于代码追溯。

**关键文件与接口**: - `scripts/gen-target.mjs` — 将 CI_COMMIT_TAG 写入 target.json 的 tag 字段。
- `components/analyzer/version.js` — 内部版 buildTag 与左下角版本后缀。
- `components/analyzer/version.html` — 设置页 tag 行及测试版回退。
- `components/i18n.js` — 构建标签中英文字段。

**状态**: 部分完成

### F-051: ECharts采集图例说明与禁用圈独立深灰
**日期**: 2026-10-12
**项目**: EncoderPlotter_0903_01
**关键词**: DPB, 单圈标定, 圆环, calibrationChart, ringTarget, ECharts, dispose

**需求场景 / 现象**: 仅标定内圈或外圈时，未参与采集的环形分段和三角指针需要置灰。

**方案 / 实施步骤**:
初始化及进度更新均应用目标状态；重绘前 dispose 旧 ECharts；innerSeries 深拷贝避免共享对象残留。
方案 / 架构：使用 analyzer.calibration 的目标设备 series 与 onlyInnerCalibration/onlyOuterCalibration 计算 ringTarget；watch 在选择时重绘，calibrateData 事件按实际目标清空另一圈旧绿色并设置 markPoint.itemStyle。both 恢复红绿指针。
【追加经验】非目标采集圆环用独立 disabled 深灰 #858B93，而未采集分段及图例保持原浅灰；修改 formatShowData 返回数组前100个实分段，保留末尾零值图例占位。ECharts 4.2.1 selectedMode=false 会使图例 silent，legend.tooltip 无法触发。最终使用 Vue DOM 图例和带 title 的问号按钮；保留 coin-front 的 Vue DOM，仅重建内部 canvas 图表实例。

**验证方法**: VM 断言覆盖仅内圈、仅外圈、残留绿色、both 恢复；node --check 和 git diff --check 通过。算法指定 e354d9c 的配置测试 29 passed。真实界面点击和硬件采集未验证。

**踩坑 / 已知异常与失败经验**: 踩坑：仅跳过非目标进度更新不能清除旧绿色，三角指针仍会有色；新增选项 watcher 放大原重建未 dispose 的实例泄漏。
【原状态说明】代码完成，真实界面验收受阻。

**关键文件与接口**: components/encoder/calibrationChart.js 的 ringTarget、applyRingTarget、initChart；components/encoder/device.js 的 HallCollectingProcess 事件。

**状态**: 部分完成

### F-052: 下线检测信息确认人工决定与订单号录入
**日期**: 2026-10-12
**项目**: driverSoftware2
**关键词**: 下线检测, 信息确认, firmware_info, 人工决定, 继续检测, 结束检测, 订单号, 扫码

**需求场景 / 现象**: 原记录未记载

**方案 / 实施步骤**:
实现：信息确认判不合格进入通用人工决策集合；决定前锁住下一项，继续后保留不合格，结束则存档关闭。订单号仅扫码/手填，回车聚焦序列号，不提交后端；模块状态保留页面重建时的值。

**验证方法**: 主控报告 test_od_lock_completed 五项通过；可见隔离模拟 GUI 已覆盖继续解锁噪声、结束显示不合格并保留决定、订单号回车聚焦序列号且不提交。独立只读复核通过。

**踩坑 / 已知异常与失败经验**: 限制：通信读取失败仍报错重试，只有判定不合格进入人工决定；订单号刷新清空且不进入报告。真实 8766 服务有用户检测，未重启，未宣称真机验收。尺寸自动换格已另提交 cda5e0c：Enter 立即跳格，输入停顿 500ms 跳格，最后只聚焦确认；清空与恢复不抢焦点，失焦与页面重建取消定时器。用户说明设备类似扫码枪单次输入，是否回车未知。仅实际观察逐字输入 30.123 时整笔保留第一格；未完成超时跳格及边界验证。用户要求停止测试并自行验收，已停止，不计为验证通过。
【原状态说明】已实现并通过隔离模拟 GUI 验证，未做真机验收

**关键文件与接口**: 13a0737（信息确认人工决定）；a80cafb（订单号前端录入）。

**状态**: 部分完成

### F-053: driverSoftware2 后端地图：server.py 装配、reader 三变体与运行形态
**日期**: 2026-10-13
**项目**: driverSoftware2（KingKong 感驱一体舵机 PC 上位机，@CODE_ROOT@\driverSoftware2；基线 VERSION 0.16.1 / 分支 feat/offline-detection-optimize / HEAD cf23634）
**关键词**: driverSoftware2, 后端地图, server.py, FastAPI endpoint, reader_wrapper, reader_mp, reader_mp_worker, READER_MP, WEB_GUI_PORT, KK_READER, shared_memory, asyncio.Queue, 连接状态真相源, 双实现同改, HID独占, _conn_generation, ws monitor 空壳, 加接口, 8765, timeout, 无响应, 端口被占, config.json, 报告落盘, request_abort, _conn_generation, LinkDown

**需求场景 / 现象**: 在这仓新增或修改任何后端功能前，必须先回答四个问题：请求从哪个函数进、帧从哪个 reader 出、reader 有几份实现要同改、开发态与打包态差在哪。原仓内文档只讲规则不给入口，逐次重新摸清 server.py（11178 行）代价高。

**方案 / 实施步骤**:
1. 新加一个后端能力：先在上面 endpoint 分组里找最近的组，同组内加 `@app.*`，再进 `core/commands.py` 加高层 wrapper（协议层改动见同批 F 记录"协议层与固件档案门控"）。
2. 涉及 reader/总线时序：`reader_wrapper.py` 与 `reader_mp.py` **两份实现同时改**，用 `inspect.signature` 写测试钉住签名。
3. 打包态才复现的问题（管道乱序 / 子进程死 / 游标竞态）：本地显式 `set READER_MP=1` 再起服务。
方案 / 架构（分层与数据流）：`Browser/Electron → HTTP/WS (FastAPI, 默认 127.0.0.1:8765) → server.py endpoint → core/commands.py (V2Commands) → core/reader_*（HID 或 libusb）→ USB → KingKong Analyzer → RS485 → STM32G473 驱动板`。
- **启动**: `server.py:11154 main()` 读 `WEB_GUI_HOST`(:11156，默认 127.0.0.1) 与 `WEB_GUI_PORT`(:11157，默认 8765) → `_bind_http_socket()`(:11088) 先占端口，**绑成功后把实际端口回写 `os.environ["WEB_GUI_PORT"]`**(:11163) 并写端口回执文件 `_write_port_receipt(port)`(:11164)，再 `uvicorn.Server(Config(app)).run(sockets=[sock])`(:11170)。刻意不用 `uvicorn.run(host, port)`：会二次 bind 产生 TOCTOU，端口被抢时回执与实际不符。`__main__` 前置 `multiprocessing.freeze_support()`(:11177)。
- **运行形态分叉**: `server.py:341` `_USE_MP_READER = os.environ.get("READER_MP", "1") not in ("0","false","False","")` → 1 用 `core/reader_mp.py`（**打包默认**，子进程独占 HID+GIL），0 用 `core/reader_wrapper.py`（`start.bat:10` 硬写 0，开发态）。单例 `backend = ReaderBackend()` 在 `server.py:352`。
- **路由规模**: `grep -c '^@app\.' server.py` = **160**。分组与定义行：连接 `/api/scan|connect|disconnect|state|params` :955/:1025/:1124/:1163/:1190；台架 `/api/bench/*` :1429-1717；报告 `/api/report/*` :2008-2086；链路诊断 `/api/probe_device_ids` :2095、`/api/auto_baud` :2162、`/api/diag/link_triage` :2236；硬件连续流 `/api/scope/*` :2643/:2776/:2837/:2865/:4040/:4087/:4144；外部扭矩真值 `/api/jn/*` :2959-2984、`/api/dyn200/*` :3012-3408；力感知 `/api/force_calib/*` :3269-3344、`/api/force_test/*` :3655-3689；命令族锚点 `/api/cmd/mode` :4223、`/api/identify` :5318、`/api/cmd/save_config` :5549；回放与急停 `/api/mit/playback*` :4455-4766、`/api/estop/abort_work` :4727、`/api/comm_loss/*` :4841-5000；测量 `/api/measure/*` :5810-6532、`/api/self_test` :6077；标定 `/api/calibrate/*` :6884/:7560/:7810/:7971/:8018/:8177、pipeline :9767-9836；档案 `/api/fw_profile` GET/POST :8371/:8377；OTA :8393-8781；再标定 `/api/cmd/recal_*` :9268-9330；裸帧 `/api/raw*` :9425/:9439；Kt 与内圈零位 :9901-10031 / :9982-10017；**下线检测 `/api/offline-detection/*` :10148-10736**；黑匣子 `/api/diag/*` :10914-10987；`/api/changelog` :10776、`/api/meta` :11003。
- **WebSocket**: `/ws/monitor` :9470 的 `_monitor_loop`（:9511）在注释块之后直接 `return`（:9528），**实际一帧都不推**（历史空壳，前端已删"监控中"标签）；真正在用的是 `/ws/calibrate/pipeline` :9852 与 `/ws/kt` :10756，模式为 worker 线程 → `asyncio.Queue` → `call_soon_threadsafe`（:9737/:9743、:9884/:9948），WS 取到终态即关（:9871-9875）。
- **连接状态单一真相源 = server.py 模块级全局** :352-404：`backend` / `cmds` / `device_id` / `baudrate` / `device_id_confirmed`(:381) / `_last_probe_alive`(:387) / `connected_serial`(:390) / `connected_port`(:394) / `_conn_generation`(:402，断链代哨兵，给无 worker 对象的长跑 closure 做协作式取消；有 worker 的走 `request_abort()`)。**刻意没有 state 类**，前端靠 `/api/state`(:1163) 拉。
- **进程间**: `reader_mp.py:9-12` SHM ring（SPSC 无锁）+ `mp.Pipe` 控制通道；`_rpc` 带 seq 回显防乱序 :317（详见 :318-361）；父端 drain 游标 `_local_read_idx` :96、`_shm_drain_iter` :556（落后超过 NUM_SLOTS 就跳尾 :564）；热换帧 `update_continuous_frame` :467、ACT 双 item `set_aux_frame` :489。子进程 `reader_mp_worker.py:195 reader_worker()` 必须 top-level（Windows spawn pickle，文件头 :5 说明），SHM 布局 header 8B + 1024×128B :14-22。
【取代】K-REPO-DRIVERSOFTWARE-20260924（2026-09-24 的 v0.13.11 单段摘要，行号与规模已过时）
【落盘与长任务生命周期】- 配置与报告根：`core/offline_detection.py:82 REPORTS_DIR = Path.home()/"Downloads"/"下线检测报告"`、同文件 :83 `CONFIG_PATH`；日志根策略见 `core/paths.py:4`（打包后 `resources/server/logs` 普通用户不可写，由该模块分流）与 :12-13（三个使用点：`fullpipe_worker.LOG_DIR` 的 `calib_*.log`、`server._RECAL_LOGS_DIR` 的 `recal_*` 标定产物、`server.REPORT_DIR`）；测试报告落 `logs/reports/` 而非 `docs/reports/auto/`（`server.py:1930` 注释）。
- 长跑任务取消：有 worker 对象的（fullpipe / kt）走 `request_abort()`（`core/fullpipe_worker.py:413`）；没有 worker 的 closure 用断链代哨兵 `server.py:402 _conn_generation` 协作式取消；链路断开统一由 `LinkDown` 处理器 `server.py:870` 收口。

**验证方法**: - 结构核对（本次已实跑）：`grep -c '^@app\.' server.py` = 160；`ls core/*.py` = 39；`wc -l server.py` = 11178；`grep -n '_USE_MP_READER' server.py` = :341；`grep -n 'def main' server.py` = :11154。
- 起服务核对：`python server.py` 后请求 `/api/meta`(:11003) 与 `/api/state`(:1163)，端口取自回执文件而非配置文件。
- 双形态核对：`READER_MP=1` 与 `=0` 各起一次，`/api/scan` 均可列出读取器；`tests/unit/test_drain_guard.py:14-17` 断言 in-process 形态 `link.hot_iters` 恒 0。

**踩坑 / 已知异常与失败经验**: 踩坑：1. **HID 全机独占**：一只 Analyzer 同时只许一个进程持有，其余实例只能当 HTTP 客户端；`import server` 有副作用即已抢占 HID（server.py:169-171 注释）→ 脚本别随手 import server。
1. **双实现接口改签名要两边同改**：`reader_mp.py:475-478` 注释实录 2026-09-22 只改 wrapper 未跟 MP 签名，结果每次热换帧 `TypeError` → HTTP 500。
2. **`hid.enumerate` 顺序不稳**：散落几十处的 `keys()[0]` 会抢错机器/错总线，选择逻辑收口在 `reader_wrapper.py:46-62` 与 `reader_mp.py:108`。
3. **`/api/scan` 的 serial 是固件编译时间戳，会撞键**（server.py:955-957）→ 真机台账另用读取器 USB 序列号做主键。
4. **`/ws/monitor` 是空壳**：按它做过"监控中"状态会永远不动；实时数据走 REST + `TELEMETRY_DISPATCH`（见前端地图记录）。
5. `AGENTS.md:321` 写"打包版默认 `READER_MP=1`（多进程 reader, `server.py:212`）"—— 该分叉现已迁到 `server.py:341`，文档行号过时；引用行号前先 grep。
【原状态说明】已完成（静态勘察 + 全部行号本次逐条 grep 实测；未运行服务与真机，开发机常态不连硬件）

**关键文件与接口**: - `server.py:227-268` core import 集中区；worker 类一律延迟 import：fullpipe :9728/:9731、kt :9881、inner_zero :9973、od_* :10317-10319、force_calib :3260/:3291。
- `core/reader_wrapper.py`(1346 行) in-process 形态：`ReaderBackend` :736、`_HidReader` :500（`hid.enumerate(VID,PID)` → `open_path` :509-514）、`_LibUsbReader` :598（pyusb 直通，USB jitter 低约 60%，:590-599）、`_make_reader` 优先 libusb 且 `READER_FORCE_HIDAPI` 可关 :718-731、线格式 `bus_config_item` :379 / `build_packet` :419 / `parse_packet` :438、多读取器会话绑定 `KK_READER_ENV` :46（环境变量在 :62 读）与 `_kk_select` :50、`LinkDown` :204、`ensure_baud` :335。
- `core/reader_mp.py:85` `class ReaderBackend`（全文件 637 行）多进程父端，控制走 `mp.Pipe`、数据走 shared_memory ring。
- `core/reader_mp_worker.py`(911 行) 子进程侧。
- `core/blackbox.py`(569) 诊断黑匣子单例 `bb`（`log` :236 / `blob` :373 / `export` :419 / 环与配额 :164），全 fail-open（文件头 :1-7）。
- `core/paths.py`(68) 源码态与打包态日志根分流；`core/serial_tap.py` 总线计数 tap。
- 环境变量清单：`READER_MP`(server.py:341)、`WEB_GUI_HOST`/`WEB_GUI_PORT`(server.py:11156-11157，回写 :11163，`core/force_calib_runner.py:72` 复用)、`READER_FORCE_HIDAPI`(reader_wrapper.py:727)、`KK_READER`(reader_wrapper.py:46,62)、`FORCE_CALIB_SCRIPT`(force_calib_runner.py:96)、`BENCH_DUAL_READER`(同文件:500)、`KK_AUX_EVERY`/`KK_MIN_SOF_2ITEM`(reader_mp_worker.py:286,677)。

**状态**: 已完成

### F-054: driverSoftware2 协议层与固件档案门控：帧/命令/寄存器/profile 四层与新增命令链路
**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**关键词**: RS485 协议, protocol.py, Cmd, FactoryCmd, crc16, make_frame, commands.py, V2Commands, FwProfileUndetermined, registers.py, register_protocol.h, register_descriptions.py, fw_profile, firmware_profiles, 档案门控, 静默回退, 0x38 内圈零位, 停机写, 慢命令 0xFD, RS485 V3.3, 新加协议命令, recal_chain, 算法不许第二份, read_version, fw_git_sha, 0x0B, 力矩无响应, OTA

**需求场景 / 现象**: 改任何一帧报文、一个寄存器地址、一条标定流程前，需要知道：帧格式在哪一层拼、寄存器地址的单一来源是谁、固件能力档案缺失时会发生什么、以及新增一条命令要动哪几个文件。这仓最容易出的事故是"静默回退旧路径不报错"和"手填档案值"。

**方案 / 实施步骤**:
1. 固件侧先加（属固件仓 `@CODE_ROOT@\driver`，分支 `v3_AI_Develop`，定论文件 `Core/Inc/register_protocol.h`，见 docs/PROJECT-CONTEXT.md §2:101-120）；
2. `core/protocol.py` 加 `Cmd`/`FactoryCmd` 常量；
3. `core/commands.py` 在 `V2Commands` 加高层 wrapper（走 `_send`，别自己拼帧）；
4. `core/registers.py` 加地址 + `core/register_descriptions.py` 加语义（再跑 `python tools/check_register_descriptions.py`）；
5. `server.py` 加 endpoint（放进已有分组）；
6. `frontend/js/api.js` 加调用 → `frontend/js/pages/*.js` 接 UI。
每一步单独 commit（仓规）。固件能力有变化的，还要用 `python tools/gen_fw_profile.py --rev <sha>` 生成档案。
方案 / 架构（四层）：1. **帧层** `core/protocol.py`(337 行)：`core/protocol.py:16` 的 `class Cmd` 只是常量集合，**只有 5 个命令值**（DEFAULT/MIT/CLEAR_FAULT/RESET/FACTORY），V3.2 帧字段定义与 head byte 说明在 :17-36（`[ID:4 | T:1 | CMD3:3]`，T=bit3 为 1s 看门狗位，广播 0x0F 已于 V3.1 删除）；`FactoryCmd` 子命令 :49、`ReCalCmd` :71、`ReCalMem` :90、`STATE_NAME` :100、`FAULT_BITS` :126、`INTERNAL_FAULT_BITS` :142、`crc16` :243、`make_frame` :255、`head_byte` :261、`parse_frame` :302。
7. **命令层** `core/commands.py`(1642 行)：`class V2Commands` :204 是唯一对外门面。出入口收口在四个私有方法 —— `_send` 单帧同步 :285、`_send_mit_frame` :356、`_boot_send_raw` :1117、`_recal_send` :1288；其上按域分方法：运动 :454-530、寄存器 :497-620、慢命令 :635-847、boot/OTA :1076-1286、ReCal flash :1311-1636。`CmdResult` :26、`StatusSpec` :153、`FwProfileUndetermined` :98、MIT 缩放同步 `sync_mit_scales` :221。
8. **寄存器层**：`core/registers.py`(402 行) 文件头 :1-5 声明自己是固件 `Core/Inc/register_protocol.h` 的 **Python 镜像、单一来源**，改固件时同步改它；`core/register_descriptions.py`(526 行) 是与固件版本**无关**的语义描述表（单位/权限/说明），按名字 join，静态对表工具 `tools/check_register_descriptions.py` 是 build.bat Step 0 的硬门禁（scripts/build.bat:121-125）。
9. **能力档案层** `core/fw_profile.py`：档案目录 `PROFILE_DIR = <repo>/firmware_profiles`（:16），正式档案按固件版本命名 `v<X.Y.Z>.json`（当前 13 份，v3.3.0–v3.4.7）；联调用的 `dev-<sha>.json` 由 `tools/gen_fw_profile.py --rev <sha>` 现生成，仓内一份都没有；缩放值在 `set_active()` 时预计算成模块级 float，热路径只读 `_SCALE_*`（:7-10）。**门控行为**：任何依赖档案的调用在 `fw_profile.get_active() is None` 时 `raise FwProfileUndetermined`（server.py:3784-3794、:3845、:3935），异常处理器在 server.py:851；档案缺失则**静默回退旧路径、不报任何错**（AGENTS.md 军规 9）。
【取代】K-REPO-DRIVERSOFTWARE-20260924 中与协议/寄存器相关的过时部分
【协议 V3.3 相对 V3.2 的关键变更（F-054 协议层，逐条对过文档）】（`docs/protocol/rs485_v3.3.md`，当前文档版本；host 代码仍是 V3.2，证据在 `core/protocol.py:17` 文档字符串 —— 注意 `docs/protocol/README.md:30` 与 `rs485_v3.3.md:22-44` 都没写这句差异说明，别照着找）：
① 物理层删除"字节间空闲 <8bit 用于帧定界"；② 表 1/表 2 增加显式类型列（uint8/int16/int32/f32）；③ **发送帧取消 14-15 字节的 `n` 计数字段**，改为"14 起放 n 个地址、个数由帧长决定"，总长 `14+n+2`；④ 接收帧总长 `12+4n+2`；⑤ Fault 明确为按位 uint8；⑥ 文档头部新增 v3.4+ MIT 刻度对照块（θ 2²⁴/2π 输出端、ω 512、τ 2048）并记录 Kp/Kd 的 10000 误填事故，配套门禁 `tests/unit/test_fw_profile_mit_scales.py`；⑦ 0x0B 示例改 v3.3.0；⑧ 0x36 改为"标定写入勿手改，改转向见 0x68"；⑨ 新增 0x68 输出转动方向、0x69 LED 开关；⑩ CRC16 为 CRC16-CCITT、帧末 2 字节小端（`docs/protocol/rs485_v3.3.md:15`、:73），上位机实现就是 `core/protocol.py:243 crc16()`。协议版本源 = 固件 git tag，经寄存器 `0x0B` 映射。

**验证方法**: - 行号核对（本次已实跑）：`grep -n 'class Cmd' core/protocol.py`=16；`grep -n 'class V2Commands' core/commands.py`=204；`grep -n 'FwProfileUndetermined' core/commands.py`=98；`grep -n 'PROFILE_DIR' core/fw_profile.py`=16；`grep -n 'def reset_and_wait' core/inner_zero.py`=541。
- 档案门控核对：裸 API 连设备**必须先发一次 `read_version`**，否则档案未确定，MIT/Default 帧被守卫拦下；两查 `/api/cmd/read_version` 的 `fw_git_sha` 与 `/api/fw_profile` 的 `active`（军规 9 推论）。
- 刻度正确性：`pytest tests/unit/test_fw_profile_mit_scales.py`；区分同名数值 —— 10000 是 Kp/Kd 量化 scale，不是 pos/vel/tau 刻度。

**踩坑 / 已知异常与失败经验**: 踩坑：1. **慢命令改 flash 必须 `state == kStopped`**，否则固件回 `0xFD` 一个字节都不写（`core/commands.py:611-617` 实录固件分支）；改 device ID 同理 :1024。
1. **写零位要停机、写完要复位**（`core/inner_zero.py:372-376`），运行时写残留 +86°。
2. **档案值只能生成不能手填**：手填把 10000 当 pos 刻度填进去过，酿成力矩无响应事故（H-004 第 2 条）。
3. **寄存器排查要符号名 + 字面量双搜**（军规 12）：只搜 `kCfgMaxVoltage` 会漏掉直写的十进制 `60`。
4. **别复制第二份算法**：`recal_chain.py:8-12` 之所以 verbatim 迁移，就是为了让标定产物字节级可复现；动它等于动发布物。
【原状态说明】已完成（行号与 V3.3 差异逐条 grep/读文档实测；未连真机验证任何协议行为）

**关键文件与接口**: - `core/inner_zero.py`(570)：reg 0x38 内圈零位。手动 `InnerZeroSession` :223（`start` :247 / `_run` :294 / `status` :326，数据源是 ReCal 0x48）；自动 `collect` :467 + `analyze` :404；分箱 `Store` :156；算法 `compute_fix` :108、`write_gate` :136（MIN_BINS/DENSITY/SPAN 三道闸）；**写后必复位** `reset_and_wait` :541；硬约束注释 :372-376（运行时写 0x38 会留下 +86° 残差，必须先停机）。
- `core/fullpipe_worker.py`(1520)：一键再标定 P1-P10 后台线程（文件头 :4-6 记录 2026-05-28 从 PyQt6 QThread 剥离），事件契约 :12-19，`FullPipelineWorker` :141、`run` :693、`_run_pipeline` :731、标定看门狗仲裁 `_arm_calib_watchdog` :551 / `_restore_watchdog` :600、P5 采样质量 :274-409、`request_abort` :413。
- `core/recal_chain.py`(321)：**纯计算已抽出的唯一一份**，文件头 :8-12 明令"不许另起第二份算法"；同类收口还有 `core/force_calib_runner.py:5-9`（把台架脚本当子进程跑，不复制算法）与 `core/report_conclusion.py:3-6`。`core/algo_compat.py:1-8` 是 numpy≥1.20 垫片。
- `core/registers.py` / `core/register_descriptions.py` / `firmware_profiles/*.json` / `tools/gen_fw_profile.py`（档案只能由生成器产出，手填必错）。

**状态**: 已完成

### F-055: driverSoftware2 前端地图：13 页清单、路由注册五处、REST/WS 与示波器 uPlot 图表
**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**关键词**: 前端地图, frontend, 无构建 ESM, app.js, PAGE_BUILDERS, 加一个新页面, api.js, X-KK-Trace, MonitorSocket, PipelineSocket, KtSocket, telemetry:sample, scope-bar.js, uPlot, PAGE_PROFILE, 冻结看门狗, unthrottled-timer, setUnthrottledInterval, 后台节流, 0x4D 看门狗, 页面重建 innerHTML, pageCleanups, capabilities.js 受众分层, tokens.css, i18n, 示波器, 切页, 图表冻结, 不用构建, 13页, 受众档位, MAX_UI_LEVEL, confirmDialog

**需求场景 / 现象**: 本仓前端**没有 build**（浏览器直接跑 ESM），也没有框架。加页面、改交互、调示波器之前需要知道：页面在哪注册、REST/WS 从哪进出、周期性发帧怎么不被浏览器节流、页面重建会漏掉什么。

**方案 / 实施步骤**:
1. `unthrottled-timer.js:3-14` 记录真机实证：页面 hidden / 窗口被遮挡时浏览器把主线程定时器节流，实测 `setTimeout(25)` 拖到 970ms，帧间隔越过固件 `0x4D` 看门狗 → **电机停转且锁存**；采样循环里圈数被钳还会产出"看似正常的假数据"。
2. 所以安全路径用本模块：Worker 定时器 `sleep(ms)` :59、`setUnthrottledInterval(fn, ms)` :101；或直接 `await` 链（实测 `tests.js` 里有 144 处 `await sleep`，采样循环形如 :3167/:3241/:3350 的 `while (performance.now() < tEnd) { … ; await sleep() }`）。
3. **别把 `setInterval` 当成"只是界面刷新"**（实测 `frontend/js/**/*.js` 共 19 处）。轮询/显示类有 `link-health.js:443`、`offline_detection.js:651/:756/:819`、`calibrate.js:2277`、`forcecal.js:606`、`test-scope.js:775/:886`、`trajectory.js:1628`、`tests.js:3816`；**但 `scope-bar.js:4132/:4145` 的 `this._timer = setInterval(() => this._tick(), period)` 就是软轮询发帧路径**（:4146-4148 自证：寄存器页起 Live 就逐 addr 打 `/api/cmd/reg_read`，跟回放帧抢同一条总线），`scope-bar.js:1436/:4140` 的 16ms `_hwDrainTick()` 同样在发请求。碰到这些循环要按第 1 条换成 `unthrottled-timer` 或 `await` 链。
4. `api.js:485 setInterval(ms)` 是给 `/ws/monitor` 发 `interval_ms` 消息的方法名，不是定时器，别看错。
方案 / 架构：- **入口**: `frontend/index.html:199` `<script type="module" src="/static/js/app.js">`，`uPlot` 以 IIFE 全局挂载（:198），6 个 CSS 入口（:11-16）。改 `frontend/js/**/*.js` 直接生效（server 自动 serve 最新版）。
- **分层**: `js/app.js`(1654 行) 主编排（路由/懒建页/顶栏/scope 抽屉/急停）· `js/api.js` REST+WS 客户端 · `js/store.js:34 class Store` 全局 state + 事件总线 · `js/components.js` DOM helper 与弹窗（:8/:57/:86/:149/:242，弹窗焦点 :235）· `js/scope-bar.js`(4418 行) 示波器抽屉 · `js/capabilities.js:14 CAP_MIN_LEVEL` 受众分层门控 · `i18n.js` + `locales/{zh,en}.json` · `theme.js` · `link-health.js` · `blackbox.js` · `estop.js` · `unthrottled-timer.js` · `trip-snapshot.js` · `risk-tags.js` · `render-md.js` · `test-scope.js` · `bg-canvas.js`。
- **路由**: `app.js:221-237 const PAGE_BUILDERS` 共注册 **12 个页面**（motion/registers/calibrate/torque/console/tests/offline-detection/trajectory/bootloader/guide/diag/forcecal；`overview` 已删 :222、`scope` 页已删由抽屉自带 :224、`detection` 合并进 calibrate :230），懒建 `app.js:336`（`PAGE_BUILT` 集合 :238）。侧栏项在 `index.html:84-155` 的 `rail-item[data-page=…]`，容器是 `index.html` 里对应的 `<section id="page-…">`（如下线检测 :169）。
- **通信**: 唯一 REST 咽喉 `api.js:105 request()`；每请求带 `X-KK-Trace` 取证头（:115）；**默认不设超时**（:92-103 有意为之，长命令由后端控制）；HTTP 200 但 `ok:false` 也记为失败（:138）；结果回调钩子 `onApiOutcome` :81，由 `link-health` 单向订阅（:77，刻意不成环）。WS 三类：`MonitorSocket` :456 `/ws/monitor`、`PipelineSocket` :516 `/ws/calibrate/pipeline`、`KtSocket` :541 `/ws/kt`；消费点 `app.js:675` → `feedScope` :692 / `watchFault` :746，开关 `syncMonitorLifecycle` :724（仅 motion 页 + 已连接时开）。后端 `/ws/monitor` 是空壳（见 F-053），实时数据实际走 REST → `TELEMETRY_DISPATCH`（api.js:26-69）转 sample → `store.emit("telemetry:sample")`（:151）→ `scope-bar.js:726` 订阅。
- **加一个新页面（5 处，顺序固定）**: ① `index.html` 加 `rail-item` + `<section id="page-x">`；② `app.js:17` 区域加 import + `:221 PAGE_BUILDERS` 加键；③ `capabilities.js:14 CAP_MIN_LEVEL["page:x"]` 给定受众档位（如 `"page:offline-detection": 2` 在 :35）；④ `scope-bar.js:257 PAGE_PROFILE` 给该页的采样方案，**不需要 scope 就显式写 null**；⑤ `locales/zh.json`、`locales/en.json` 文案。
- **样式**: `css/tokens.css:3` 声明 `docs/theme-servo-cyan.md` 为单一真相源（cyan 主色阶 :45-49、字号阶 :93-101、布局根 token `--rail-w`/`--topbar-h` :104-105、light/dark 双份 :117/:171）；受众分层的"分段标题空段自动隐藏"（`docs/gui-design.md:144`）落在 `app.js:375-394 applyUiLevel()`。CSS 按 base reset / components / layout / pages 四层分文件。
【取代】K-REPO-DRIVERSOFTWARE-20260924 中缺失的前端部分（旧摘要只有一句 "ESM 前端"）
【受众档位与危险操作确认】档位由产物根文件 `MAX_UI_LEVEL`（`server.py:317`）下发；前端 `capabilities.js:7 UI_LEVEL_KEY`、:14 `CAP_MIN_LEVEL`、:91 取 `min` 过滤，`app.js:375 applyUiLevel()` 做 rail 项过滤与空分段隐藏；危险操作统一走 `components.js:149 confirmDialog({danger:true})`。**新功能要先决定落在哪一档** —— 客户包（L1/L0）看不到的入口等于没做。

**验证方法**: - 结构核对（本次实跑）：`ls frontend/js/pages/*.js` = 13 个文件；`PAGE_BUILDERS` 注册 12 个键（app.js:221-237）；`wc -l frontend/js/scope-bar.js` = 4418、`app.js` = 1654。
- UI 改动自验：按 `docs/skills/playwright_ui_self_test.md` 用**可见窗口**跑（军规 13 要求真实 GUI 路径，裸 API 不算）。
- 图表改动自验：必须让真实数据流起来看图（军规 4）——`tests/test_monitor_lifecycle.py` 需 8765 后端在跑；纯 DOM 断言与静态截图曾在"曲线不绘制"事故里全部正常。

**踩坑 / 已知异常与失败经验**: 踩坑：1. **页面重建 = `root.innerHTML=""`**（`app.js:336-347`，FB-023），builder 一律自清；但清不掉 **module 级 setInterval 与 `store.on` 订阅**（`app.js:409-413`）→ 下线检测页专门建了 `pageCleanups`/`onPageRebuild`（`offline_detection.js:52-59`，:530/:677/:758 注册清理）。
1. **挂在 document 上的 `visibilitychange` 监听**，`innerHTML` 与 store 退订都够不着，必须显式退订：`motion.js:141-145`，注册/退订在 :3338/:3341。
2. **切页后 scope 失效**：`PAGE_PROFILE`（`scope-bar.js:257-285`）只在 profile 名变化时才 `setProfile`，同名页互切不触发 stop；motion 页重建要自己 destroy chart（`motion.js:561`）；**trajectory 的 profile 必须写 null**（:266-275），否则硬件连续流跟着页面跑，与回放帧 8:1 交织会硬关栅极。
3. **uPlot 初始化时机**：`scope-bar.js:3028 new uPlot`，`_render()` 末尾用 `setTimeout(() => _initChart(host), 0)`（:2735）等布局落位；同步补一发会被 `!host.clientWidth` 挡掉（:2731），别在外面再加同步调用。主题切换要 destroy + rebuild（:744-748），尺寸靠 ResizeObserver 同步（:703-714）。
4. **图表冻结排查**：RAF 合并重绘 + 1s 僵死看门狗（:1149-1213）、warn 锚点 :1333、`_diag` 计数器 :661-673，手册 `docs/skills/scope_chart_freeze_debug.md`；后台标签只计数不报警（:1254/:1314）。
5. **localStorage 谎报**：`Number(localStorage.getItem(k))` 在缺键时得 0，未连接也显示"设备 0"（`store.js:20-31` 有修复注释）；`setDeviceId(null)` 不得覆盖已有记忆（:165）；日志弹窗要主动取历史快照 `log.history()`（:191-193）。
6. **焦点/换格类交互**：订单号↔序列号调度 `offline_detection.js:416`、尺寸读数后 500ms 自动换格 :529-543、scope min/max 的 Enter+blur `scope-bar.js:3349`、抽屉 ESC 与遮罩共用一道闸（modal 在上）`app.js:770-808`。自动化提交用派发 keydown Enter，别用 Tab（本页 blur 会回滚未提交输入）。
【原状态说明】已完成（页面清单/注册表/行号本次逐条 grep 实测；未在浏览器里跑交互回归 —— 开发机不连硬件，UI 行为需按验证方法自验）

**关键文件与接口**: - `motion.js`（运动）：`buildMotion` :174，MIT 五滑条 + presets，连续发帧 `restartCont` :3020、`setUnthrottledInterval(sender, softPollPeriodMs())` :3066，看门狗安全档 `WDG_SAFE_POLL_MS = 200` :3010 与 `Math.min(base, …)` 钳制 :3017、低频预警 :3057；Electron 形态判定（UA 含 `" Electron/"`）:158-172。
- `calibrate.js`（电机标定，2662 行）：`buildCalibrate` :190，多相位卡片（:259/:484/:1167/:1414/:1521/:1806/:1938/:2141/:2242/:2467），一键再标定 `api.pipelineStart` :739 + `PipelineSocket` :746。
- `offline_detection.js`（下线检测，1312 行）：`ITEMS` :21-28、`buildOfflineDetection` :58，页面级清理表 `pageCleanups`/`onPageRebuild` :52-59。
- `torque.js` 砝码摆臂 Kt（走 `/ws/kt`）· `forcecal.js` 力感知标定 · `registers.js` 寄存器读写 · `bootloader.js` 设备/改 ID/OTA · `trajectory.js` MIT 轨迹回放 · `console.js` 裸帧收发（`buildConsole` :154）· `tests.js` 测试套件 recipe runner（7374 行）· `diag.js` 黑匣子配置 :10 · `guide.js` 使用指南 · `detection.js` 已下线（页面不再注册，文件仍在）。

**状态**: 已完成

### F-056: driverSoftware2 Electron 壳：拉起后端、端口回执与窗口安全项
**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，electron/ 壳，package.json 版本 0.16.1）
**关键词**: Electron 壳, electron/main.js, startBackend, server.exe, resources/server, PORT_PINNED, 端口回执文件, killStrayBackends, backgroundThrottling, contextIsolation, nodeIntegration, devTools 客户包关闭, Menu.setApplicationMenu, kkdiag://, did-fail-load 重试, postmortem, diagnose.js, extraResources, 无 preload 无 IPC, user agent Electron, 黑屏, 起不来, npm start, nsis

**需求场景 / 现象**: 桌面版和浏览器版行为不一致（切窗口后电机停转、devtools 能不能开、端口被占怎么办），或改了后端启动方式要确认壳侧是否跟上。需要壳与后端进程的关系图。

**方案 / 实施步骤**:
方案要点：
- **拉起后端**：`electron/main.js:144 startBackend()`。打包态 spawn `process.resourcesPath/server/server.exe`（:150-167，windowed 无 console，日志重定向到 `userData/server.log`，:160 注释说明不弹黑窗）；开发态用 `py -3.12 server.py`（:185-203，路径解析注意含空格的 `C:\Program Files\…` 会踩坑，:200 注释）。启动前先 `killStrayBackends()` 清理残留（:87）。
- **端口获取**：`PORT_PINNED = !!process.env.WEB_GUI_PORT`（:28）—— 只有人为钉住端口才信任它；否则**由 server 自绑后把实际端口写进回执文件**，壳读文件拿端口（:99-135，注释解释了"为什么是文件而不是 stdout"）。这与后端记录里 `server.py:11161` 回写 `WEB_GUI_PORT` 是同一条链的两端。
- **窗口与安全**：`new BrowserWindow`（:1083），`contextIsolation: true`（:1092）、`nodeIntegration: false`（:1093）、`devTools: !customerBuild`（:1094，客户包关掉后 F12 与 openDevTools 都是空操作）、**`backgroundThrottling: false`**（:1105；:1095-1104 是真机 id4 实证注释；节流导致停机的机理见 F-055，本条只登记壳侧这个开关）。`closed` 监听必须**紧挨构造点**挂（:1109-1119），留到函数尾部会漏掉早期退出路径。菜单：`Menu.setApplicationMenu(null)`（:1127，条件见 :1126）。外链与新窗口一律拦（:1133 `setWindowOpenHandler`，同时截 `kkdiag://` 自定义协议用于"打开诊断包"）。
- **加载与容错**：`did-fail-load` 自动重试（:1147，注释：后端未就绪时单次 loadURL 会永久黑屏；策略是等后端最多 40s 再 loadURL），首次 `mainWindow.loadURL(BACKEND_URL)`（:1217）；后端起不来时 `showBackendFailurePage()`（:1110 附近两处早退）；运行期崩溃走提示而不是换页（:941，换页会毁掉用户当前页面状态）；崩溃后置诊断页见 `electron/postmortem.js`（自检 `postmortem.selftest.js`），诊断入口 `electron/diagnose.js`。
- **前端对壳零感知**：**没有 preload、没有 IPC 通道**（`frontend/js/pages/motion.js:158-172` 注释明确），页面只用 UA 里的 `" Electron/"`（带前导空格）判形态。好处是同一份前端在浏览器与桌面下通用，代价是壳不能给页面传能力。

实施步骤：
1. 需要新能力给页面用 → 优先加后端 endpoint，不要开 IPC（前端零感知是既有约定）。
2. 改后端启动方式（入口文件名、端口策略）→ 同步看 `main.js:144/:150/:99-135` 与 `server.py:11154-11170`。
3. 改窗口选项 → 确认 `backgroundThrottling` 与 `devTools` 两行没被动（前者是真机事故换来的）。
4. 打包相关 → 见 F-057 的 `build.bat` 步骤与 `extraResources` 链路。

**验证方法**: - 本地起壳：`cd electron && npm install && npm start`（AGENTS.md 开发流程），观察窗口是否可见、后端日志落在 `%APPDATA%/…/server.log`。
- 端口策略核对：占用 8765 后启动，壳应读到回执文件里的实际端口而不是失败。
- 后台节流核对：运动页使能电机后把窗口最小化/遮挡，帧应继续发（`backgroundThrottling: false` 生效）；浏览器形态则必须靠 `unthrottled-timer.js`（见 F-055）。

**踩坑 / 已知异常与失败经验**: 1. 用户可见验收必须走真实 GUI（军规 13）；headless Playwright 跑通只能写"底层链路通过"。
2. `dist_app/server.dist` 是壳引用的**共享产物目录**；"跳过 Nuitka 复用旧 dist 会把旧前端发出去"这条后果与证据归 F-057，本条不重复展开。
3. 构建脚本的 `for /f` 转义坑见 F-057 踩坑 4。

**关键文件与接口**: - `electron/main.js`(1273 行)、`electron/diagnose.js`、`electron/postmortem.js`、`electron/postmortem.selftest.js`、`electron/installer.nsh`、`electron/assets/`。
- `electron/package.json`：`version` :3（与根 `VERSION` 由 `scripts/release.py` 同步）；`build` 段 :16-60，`files` **只带 4 个壳文件**（:22-27：main.js / diagnose.js / postmortem.js / package.json），`extraResources` 把 `../dist_app/server.dist` 拷成 `resources/server`（:28-33）——**所以前端文件不在壳里，随 server.dist 走**；这条打包装配的完整后果（复用旧 dist 会把旧前端发出去）见记录 F-057，本条只登记壳侧配置。win 目标 nsis+zip（:34-40）、mac 目标 dmg+zip（:41-45）。

**状态**: 已完成

### F-057: driverSoftware2 测试分层、CI 门禁与构建发布（旧前端随 server.dist 走的根因）
**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**关键词**: pytest, pytest.ini, testpaths, tests/unit, conftest, isolate_disconnect, fake_clock, FW_BIN, 无 marker, 源码扫描门禁, _strip_comments, 剥注释, 人为破坏自证, check_register_descriptions, audit_test_meta, GitLab CI, gitlab-ci.yml, CI_COMMIT_TAG, win-probe, test-gates, build-win-release, build-win-smoke, notify-release, NAS, GIT_CLEAN_FLAGS, build.bat, Nuitka, include-data-dir, include-data-files, INTERNAL_SHA, MAX_UI_LEVEL, SKU, 客户包, release.py, cut_changelog, local-build, requirements 精确 pin, OpenBLAS, vendor wheel, requirements.lock, setup.bat, start.bat, READER_MP, 打包, 旧前端, server.dist, dist_app, 复用dist, CHANGELOG, 未发布, 冒烟, win-smoke

**需求场景 / 现象**: 在本仓提交前要知道"门禁会跑什么、我这条改动会不会被源码扫描拦、打包会不会把旧前端发出去、发版命令是什么"。**先记结论：前端文件装在 `dist_app/server.dist` 里随服务端走，任何跳过 Nuitka、复用上次 dist 的打包都会把旧前端原样发出去。**

AGENTS.md 讲的是原则，这条记录给**具体文件与行号**。

**方案 / 实施步骤**:
【一 · 测试分层】- `pytest.ini:9` `testpaths = tests/unit`；:1-7 解释为何钉死（根层脚本的顶层守卫在**收集期**就 `sys.exit` → INTERNALERROR）。`tests/conftest.py:7` `collect_ignore_glob = ["test_*.py"]` 再豁免一次。
- 规模（2026-10-13 实测）：`tests/unit/test_*.py` **244 个文件**，`grep -h '^def test_' tests/unit/test_*.py` 合计 **2236 条**；`tests/` 根 **7 个硬件独立脚本**（`test_mit_run.py`、`test_monitor_lifecycle.py`、`test_ota_selftest.py`、`test_ota_stream.py`、`test_ota_ui_playwright.py`、`test_read_range_stress.py`、`test_register_table.py`，直接 `python` 跑）；`tests/examples/` 客户端调用示例，`tests/fixtures/`、`tests/unit/fixtures/*.json`、`tests/screenshots/`。**没有 integration 目录**。
- 跳过机制：①**无 pytest marker 注册**（pytest.ini 与 conftest 都没有 `markers`）；②根层脚本靠环境变量守卫，如 `tests/test_ota_selftest.py:25-29` 缺 `FW_BIN` 即 `sys.exit(0)`；③`pytest.mark.skipif` 13 处（如 macOS 缺 win_amd64 wheel 时整模块跳过，`.gitlab-ci.yml:205-208` 同口径）。
- 公共 fixture：`tests/conftest.py:48 isolate_disconnect`（:47 是装饰器；隔离黑匣子落盘 + 保存/恢复 server 模块级全局，**8 个文件**共用）、`:120-187 FakeClock`（按模块接管 `monotonic`/`perf_counter`，**不接管 `time.time()`**）。
【二 · 门禁与 CI】- 源码扫描类门禁：本仓精确含 `_strip_comments` / `_strip_comments_and_docstrings` 的 unit 文件 **7 个**（宽松算上任意 `_strip*` 助手是 73 个），**125 个文件**用 `read_text` 读源码做断言。代表：`tests/unit/test_cmd_status_contract_guard.py:99`（并在 :242 自证扫描器本身）、`test_build_bat_flow.py`、`test_build_script_parity.py:26`、`test_backend_port_binding.py:155`、`test_bench_host_port.py:117`、`test_bus_timeout_window.py:99`、`test_customer_build_gates.py`、`test_macos_ci_gates.py`、`test_release_dev_guard.py`、`test_drain_guard.py:14-17`、`test_reader_mp_ensure_baud.py:83`、`test_fw_profile_mit_scales.py`、`test_od_*.py`（下线检测 **11 个**）。军规 3：匹配前先剥注释，写完**人为破坏一次**确认变红再还原（还原别用 `git checkout --`，实现未 commit 时会连实现一起 revert）。
- 静态对表工具：`tools/check_register_descriptions.py`（寄存器地址与语义描述对表，build.bat Step 0 的硬门，`scripts/build.bat:121-125`）、`tools/audit_test_meta.py`（断言 ↔ GB 条款四张表，判红不 throw）、`tools/gen_fw_profile.py`、`tools/reconcile_registers.py`。
- CI：只有 `.gitlab-ci.yml`。`workflow.rules`（:24-26）**只有 `$CI_COMMIT_TAG` 起流水线**（推分支不触发）；stages test/build/notify（:51-54）。jobs：`win-probe`（tag `win-probe-`，只读探测工具链与 NAS，:101）、`test-gates`（mac 建 venv + `./venv/bin/python -m pytest tests/unit -q -rs`，:192/:208）、`.win_build`（:140：`scripts\ci_win_venv.ps1` → `cmd /c scripts\build.bat --release --customer` → `scripts\ci_win_upload.ps1`）派生 `build-win-release` / `build-win-smoke`、`.mac_build`（:228：`bash scripts/build_mac.sh --release --customer` + smbclient 上传 + 逐文件回读点名 6 个产物）派生 `build-mac-release` / `build-mac-smoke`、`notify-release`（:352，`vX.Y.Z`，needs mac+win）、`notify-smoke-dryrun`（`scripts/ci_notify_lark.py`）。
- 产物落 NAS `\\KingKongNAS\software\02SD\<tag>\`（mac 加 `mac\` 子目录，win 平铺；冒烟进 `_smoke\`），变量 `NAS_IP/NAS_SHARE/NAS_DIR` 见 :29-33；`GIT_CLEAN_FLAGS: '-ffdx -e venv -e electron/node_modules'`（:49）保住缓存；`NAS_USER/NAS_PASS/LARK_WEBHOOK_URL` 是 masked CI 变量，不落文件（:39-42）。GitLab artifacts 只留一份 exe/dmg 副本，`expire_in: 1 week`。
- 冒烟通道：`win-smoke-*` tag 出试装包，**不 bump VERSION**、可先不合 development、不必等本地门禁全绿（本仓项目记忆已记）。
【三 · 构建与发布（F-057，`scripts/build.bat` / `scripts/release.py`）】- `scripts/build.bat` 顺序：SKU 参数解析 `--internal/--release/--customer/--all`（:43-77）→ 源树完整性守卫①：记 HEAD，`--internal` 拒绝 dirty（:80-107）→ venv Python 优先（:110-117）→ Step 0：寄存器描述门禁 + nuitka 可 import + electron 依赖**指纹**判定（`package-lock.json` 的 SHA256 存进 `electron\node_modules\.package-lock.sha256`，:143-167）→ Step 1：`python -m nuitka server.py` **只编一次，所有 SKU 共用**（:170-201；:183 起强调"Nuitka 退出码 0 不等于数据文件真收进去了"，直接查产物）→ Step 2：按内容"全→少"逐级后处理并 `call :pack`（内部包 :208-213；正式包剔 dev 档案 :215-228；客户包 `:purge_customer` + `:write_level 1/0` + `:gate_customer` 构建后门禁 :231-247 与 :388）→ Step 3：HEAD 复核、`+sha` 重命名、自动打 `internal/v<VER>+<sha>` tag、产物清单（:252-287）。
- **打包数据目录全在 `server.py` 的 nuitka pragma**（:9-107）：`--include-package=core`、`--include-data-dir=frontend=frontend`（:81）、`--include-data-files=tools/force_calib/*.py=…`（:97，:85-96 解释 `--include-data-dir` **收不了 .py** 这个坑）、`docs/skills`（:101）、`firmware_profiles`（:101-105）、`VERSION` 与 `CHANGELOG.md`（:106-107）。**结论（唯一归属本条）：前端是装在 `server.dist` 里随服务端走的，electron 壳只带 4 个壳文件**（壳侧配置见 F-056）→ 任何"跳过 Nuitka 复用上次 dist"的快捷打包都会把旧前端原样发出去。
- 运行时读回：`INTERNAL_SHA`（`server.py:298`，写侧 `build.bat:300`）、`MAX_UI_LEVEL`（`server.py:317-331`，内容非法保守钳到 0，见 :331；写侧 `build.bat:364`）。
- 发布：`python scripts/release.py <版本>` 是唯一 bump 入口 —— ①校验 semver / 工作树干净 / 无 dev 档案 / CHANGELOG `[未发布]` 非空（:128-158）②bump 落盘 `VERSION` + `electron/package.json` + `package-lock.json` 两行手术（:160-171、:65-98）③`cut_changelog` 截断（:45-62）④可选 `--local-build` 做三产物实物核验（:174-204）⑤commit + `git tag -a vX.Y.Z`（:208-213，**不自动 push**）。日常提交禁止手改 `VERSION`。发版前对账三件事见 AGENTS.md 军规 7。
- 依赖与安装：`requirements.txt:7-16` 说明 numpy/scipy **精确 pin**（`numpy==2.5.1`、`scipy==1.18.0`）的原因 —— 标定算法数值输出依赖 numpy 内嵌 OpenBLAS 的构建代际，换代会让标定产物 md5 漂移，升级必须重跑 replay 一致性；`kingkong_calib==1.0.1; sys_platform=="win32"`（:34，mac 不做标定）；pyusb/libusb-package **故意不列为依赖**（:36-49）。`requirements.lock.txt` 全树锁定，`requirements-dev.txt:3-5`（pytest/nuitka 不进生产）。`vendor/` 只有那一个 Cython wheel + `README.md` 的升级 7 步。`setup.bat`：查 `py -3.12` → 建 venv → **先装 vendor wheel 再装 requirements**（:44-55，否则 PyPI 找不到内部包）→ import 自检 + `hid.enumerate()` 原生绑定检查（:70-96）。`start.bat:10` 写 `set READER_MP=0`。

**验证方法**: - 本地门禁：`cd @CODE_ROOT@\driverSoftware2 && venv\Scripts\python -m pytest tests/unit -q -rs`（**不要显式设 READER_MP=0**，用 CI 默认口径，in-process 形态会让 `test_auto_baud` 两条假红 —— 本仓项目记忆已记）。
- 构建预检：正式包由 Runner 跑完整 `scripts/build.bat`；本地只在显式要求时用 `python scripts/release.py <版本> --local-build`。改 `build.bat` 后至少跑 `pytest tests/unit/test_build_bat_flow.py tests/unit/test_build_script_parity.py`。
- 发布前对账：`git log <上次 tag>..HEAD` 逐条核 CHANGELOG `[未发布]`；`grep -c '<<<<<<<' CHANGELOG.md` 必须为 0。

**踩坑 / 已知异常与失败经验**: 踩坑：1. 打包版反馈先想 `READER_MP` 双形态（分叉行号、复现方法、环境变量清单归 F-053，此处不重复）。
1. `--include-data-dir` 收不了 `.py`（`server.py:85-96`），必须逐条 `--include-data-files`，新增台架脚本时容易漏。
2. 扫源码的门禁如果不剥注释就会恒绿（注释文本自己满足断言），本仓已踩两次。
3. 分支命名以 `AGENTS.md` 军规 6 词表为准（`feat/` `fix/` `docs/` `chore/` `release/` `hotfix/`）；F-019 里的 `feature/*` 属历史线记载。**发布前置也已换代**：F-019 结论 5「必须先完整构建才 bump」不再适用，现为 `release.py` 可选 `--local-build`、正式包由 GitLab Runner 在 tag 上构建。
4. `cmd /c` 里 `for /f ('…')` 内层的 `=` 与 `>` 必须 `^` 转义（`build.bat:92` 一带），否则 sha 变量取到空值、出现 `ECHO is off.`。
【原状态说明】已完成（数字与行号本次实跑/实读；未运行完整构建，未发版）

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-058: driverSoftware2 下线检测（产线出厂检测）功能全貌与 duoji 口径
**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，分支 feat/offline-detection-optimize，HEAD cf23634，基线 v0.16.0 首发 / v0.16.1 当前 VERSION）
**关键词**: 下线检测, 扭矩去皮零点, 卸力零点, offline detection, 产线出厂检测, OfflineDetectionController, require_step, DetectionType, 外观检测, 尺寸测量, 反驱力, 信息确认, 噪声, 额定扭矩, 坏点, MAX_PLAUSIBLE_NM, 卸力建零, ZERO_MIN_SAMPLES, 出力准备闸, prepareGate, prepare_delay_s, od_motor, od_sensor, od_rated_torque, od_reverse_force, od_profiles, od_relay, DYN-200, JN-DN5, 485 继电器, duoji 口径, 判定在后端, 人工决定, core/offline_detection.py, offline_detection.js, 八步, 存档, 序列号, Downloads

**需求场景 / 现象**: 下线检测是产线逐台出厂质检功能（v0.16.0 首次上线，本分支正在按产线参考实现 duoji 的口径逐条对齐）。改动时最常见的三类问题：判定口径抄错来源、采集防呆漏一条、状态机门控被绕过。后续接手需要一页看懂模块分工与口径出处。

**方案 / 实施步骤**:
1. `core/offline_detection.py` 加 `DetectionType` 成员 + `DETECTION_NAMES` + `judge_*` + DEFAULT_CONFIG 项；
2. 若需要采集过程，新建 `core/od_xxx.py`，口径注明同 duoji 的哪个函数；
3. `server.py` 在 :10148-10736 段内加 endpoint 并接入 `require_step` 门控；
4. `frontend/js/api.js` 加调用、`offline_detection.js` 的 `ITEMS` 加卡片；
5. `tests/unit/test_od_*.py` 补门控与判定用例；CHANGELOG `[未发布]` 写一句白话。
方案 / 架构：- **流程**：八步 = ①产品序列号（**会话主键**）→ ②外观 ③尺寸 ④反驱力 ⑤信息确认 ⑥噪声 ⑦额定扭矩（六个检测项，前端 `ITEMS` 常量逐个列出，`frontend/js/pages/offline_detection.js:21-28`）→ ⑧汇总存档。报告与配置落 `core/offline_detection.py:82 REPORTS_DIR`（`~/Downloads/下线检测报告`）、:83 `CONFIG_PATH`。**强顺序门控**在后端：`core/offline_detection.py:739 require_step()` —— 前一项没做完不许做下一项；单会话约束 :721；不合格时由操作员决定继续或结束 `decide()` :758；结束 `finish_session()` :793（检测表要求每台都落盘，文件头 :12）。
- **判定一律在后端**（`core/offline_detection.py:11` 明示"前端只负责采集入参与展示，不参与 PASS/FAIL 计算"）；状态枚举 `DetectionStatus` :31（PENDING/RUNNING/PASSED/FAILED/ERROR）、检测项枚举 `DetectionType` :39-45；判定函数 `judge_*` :319-494；结果模型 `DetectionResult` :527；会话模型 `OfflineDetectionSession` :557；控制器 `core/offline_detection.py:717 OfflineDetectionController`。配置读写 `load_config` / `save_config` / `validate_config` / `migrate_legacy_*` :132-295，**阈值/名义值/期望版本全部走 config.json，产线可在界面改**。
- **采集侧模块分工**（口径一律注明"同 duoji"以便回溯来源）：
  - `core/od_motor.py`(64)：出力前使能序列 —— 清故障 → default 模式 → 软复位 → 等 `RESET_BOOT_WAIT_S = 0.8s`（:18，duoji 实测 0.5~0.8s）→ 再 default；`ENABLE_ATTEMPTS = 2`，**复位无应答就整套重走**（commit cf23634 的用例口径）。
  - `core/od_sensor.py`(83)：DYN-200 / JN-DN5 外部扭矩传感器的**只读**适配，绝不启停传感器、绝不动全局去皮（文件头 :5-10）；卸力建零 `:26` = 静置原始读数排序、去两头各 20% 取平均（同 duoji `_auto_tare`）。
  - `core/od_reverse_force.py`(235)：`ReverseForceRunner` :38 分阶段采集，断电手转、正向取最大 / 反向取最小；`MAX_PLAUSIBLE_NM = 200.0`（:27，量程外读数丢弃且**不计入传感器掉线**，即"坏点"）、`ZERO_MIN_SAMPLES = 5`（:28，建零读数不足直接报错）。
  - `core/od_rated_torque.py`(240)：`measure()` :113 堵转工装上给前馈力矩持续 `duration_s`，**实测取外部传感器真值，舵机回读仅备查**（文件头 :1-3）；异常类（过流阈值 `peak_iq_a/limit_a`、过温、故障）在 :38-70，**实际停机判定在采集循环侧**：滤波 Iq 取值 `server.py:10613`、过流/过温/故障归类 `server.py:10649`；同样带 `ZERO_MIN_SAMPLES = 5` :33。
  - `core/od_profiles.py`(228)：判定标准命名方案 —— 多方案存 / 切 / 导 / 删 / 另存（文件头 :1）。
  - `core/od_relay.py`(294)：`OdRelay` :85，485 Modbus 继电器控制工装通断。
  - 注：`core/od_torque_recorder.py` 已删除（本分支实际 `ls` 确认不存在）。
- **后端装配**：`server.py:10148-10736` 是 `/api/offline-detection/*` 全家桶（config/session/开始/下一项/判定/人工决定/导出），装配区 :10092-10343，`from core import od_motor, od_rated_torque, od_sensor` 在 :10317，噪声空载运转 :10525，额定扭矩采集入口 :10590。
- **前端**：`frontend/js/pages/offline_detection.js`(1312 行) `frontend/js/pages/offline_detection.js:58 buildOfflineDetection`，卡片式八步（:83-91）；**出力准备倒计时闸门** `prepareGate()` :789-826（倒计时中可"立即开始"或"取消"，配置项 `rated_torque.prepare_delay_s` 见 :1208）；订单号↔序列号焦点调度 :416、尺寸读数 500ms 自动换格 :529-543；页面级定时器清理 `pageCleanups` / `onPageRebuild` :52-59。API 封装 `frontend/js/api.js:259-287`（`od*` 一族）；档位 `capabilities.js:35 "page:offline-detection": 2`；导航 `index.html:127` 与 :169；注册 `app.js:26` import + :231 builder。
- **门禁**：`tests/unit/test_od_*.py` 共 **11 个**文件（`pytest.ini` 限定 testpaths=tests/unit）。
【口径速查（F-058 下线检测 · 别自己发明）】- **坏点** = 量程外（±200 N·m）读数丢弃，且不算传感器掉线。
- **建零（卸力零点）** = 静置读数排序去两头各 20% 取平均；新读数 <5 个直接报错，不能沿用旧零点。
- **反驱力** = 断电手转，先正转后反转，正向取最大值、反向取最小值，分段极值判定。
- **额定扭矩** = 堵转工装 + 前馈力矩持续一段时间，实测真值来自外部传感器。
- **出力准备闸** = 额定扭矩/噪声出力前先倒计时（可跳过），避免操作员手还在工装上。
- **噪声使能失败** = 软复位无应答时整套使能序列重走一次（两次尝试），不能谎报使能成功。

**验证方法**: - 判定与门控：`venv\Scripts\python -m pytest tests/unit -q -rs -k od`（11 个 test_od_* 全绿）。
- 界面：按军规 13 走**可见 GUI**（Electron 正式界面或浏览器可见窗口），路径 = 打开下线检测页 → 连设备 → 逐八步 → 观察不合格时的人工决定与结束存档。
- 状态一致性：改完核 `CHANGELOG.md:17` 起的 `[未发布]` 段（本次实测 23 条：变更 13 / 新增 6 / 修复 4），别把已生效行为写成"待发布"。

**踩坑 / 已知异常与失败经验**: 踩坑 / 限制：1. **duoji 是产线在跑的扭矩质检上位机，口径可对，实现别整抄**（本仓项目记忆已记：坏点处理就有差异）。
1. **传感器只读**：下线检测不许启停 DYN-200/JN-200 传感器、不许改全局去皮值。
2. 页面重建会留下脱离文档的旧 DOM 轮询（机理归 F-055 踩坑 1）；本页的做法是把清理注册进 `onPageRebuild`（:530/:677/:758）。
3. 采样节拍必须**严格晚于 now**（commit 60d0be8：节拍早于 now 导致满速刷帧死循环）。
4. 通讯延迟后**跳过错过的节拍**而不是连续补帧（commit 4dabd5c）。
5. 信息确认不合格才进入人工决定，通信读取失败仍应报错重试，不要伪装成"不合格"（与 F-052 的边界）。
6. 本分支 commit 主题多为"对齐 duoji 口径"，`git log --oneline -30` 计数：`fix(下线检测)` 12、`feat(下线检测)` 9、`test/refactor(下线检测)` 各 1、其它 `fix/feat/docs` 7。
【原状态说明】部分完成 —— 结构与口径已核实（行号本次逐条读文件实测）；功能本身仍在开发分支，**未做真机验收**，冒烟通道真实存在：`.gitlab-ci.yml:172-175` 的 `build-win-smoke` 按 `/^win-smoke-/` 触发，本分支已打过 `win-smoke-offline-detection` 与 `win-smoke-offline-detection-fix2`（冒烟包不 bump VERSION，落 `02SD\<tag>\`）。

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 部分完成

### F-059: driverSoftware2 文档三层地图、协作上下文与三条自验路径
**日期**: 2026-10-13
**项目**: driverSoftware2（@CODE_ROOT@\driverSoftware2，VERSION 0.16.1）
**关键词**: 文档地图, docs/skills, 必读, AGENTS.md, PROJECT-CONTEXT, 缺陷池, 需求池, 飞书多维表格, base token, 待回归, 回填, 真机台账, 读取器 serial, workspace.json, 逻辑名, 不引用项目外路径, onboarding, lark-cli PATH, playwright_ui_self_test, scope_chart_freeze_debug, realmachine_fault_injection, inner_zero_calibration, recal_production_workflow, ANALYZER_HARDWARE_GUIDE, reader_issues, rs485_v3.3, gui-design, theme-servo-cyan, CHANGELOG 体例, 文档引用不实, AGENTS.md, 行号过时, 文档引用失效

**需求场景 / 现象**: 本仓的"知识"分三层放在仓内（`AGENTS.md` 讲怎么干活、`docs/PROJECT-CONTEXT.md` 讲活从哪来回哪去、`docs/skills/` 讲具体工法），但缺一张能检索的目录：改某个模块前该读哪份、某条缺陷回填哪四个字段、真机台账用什么做主键，每次都要重新翻。另外这些文档之间的交叉引用有失效项，照着走会扑空。

**方案 / 实施步骤**:
方案 / 架构（文档三层与分流判据）：- `AGENTS.md`（仓根）：硬规定 + 模块→必读 skill 映射表（:170-178）+ 工程军规（:224 起，含分支命名表、发版对账三件事、真机验收必须走可见 GUI）。
- `docs/PROJECT-CONTEXT.md`：协作上下文。§0:8 就给出"新信息该写到哪"的分流判据 —— A 指针 / B 台账 / C 工法 / D 本机配置。
- `docs/skills/`：工法手册，共 **13 份**（见下表）。
- `docs/` 顶层 17 份 md 各管一事：`ONBOARDING.md` 新机接手清单、`PACKAGING.md` Nuitka+Electron 打包、`gui-design.md` 界面设计决策、`theme-servo-cyan.md` 主题令牌（`frontend/css/tokens.css:3` 认它为单一真相源）、`feedback_ledger.md` 反馈分诊台账、`rs485_protocol.md` **已过期**（只是指向 `docs/protocol/` 的迁移指针）、`audience_tiering_proposal.md` 受众分层 L1/L0、`ci_release_migration_proposal.md` 发布迁 CI（已拍板）、`firmware_dev_versioning_coordination.md` 联调固件识别（FB-011）、`macos_support.md`、`ota_cfg_schema_migration_todo.md`、`reader_autonomous_scheduling_todo.md`（未动手）、`ui_test_cases.md` 界面验收资产、`algorithmic-philosophy.md` / `brand-philosophy.md`、`bai_sync_0726_review.md`。
- `docs/` 子目录 8 个：`protocol/`（协议按版本）、`skills/`、`reports/`（实测报告 + `reports/auto/*.json`）、`parking/backlog-2026-08-03.md`（悬项）、`superpowers/{plans,specs}/`（13+12 份历史设计稿，2026-07-05→09-22）、`traj_samples/*.csv`、`archive/server.spec`、`_rendered_test_suite_guide/`。
【docs/skills 13 份与"改什么前必读"（本表属 F-059；核对命令 `ls docs/skills/*.md` 条数 = 13）】| 文件 | 讲什么 | 必读场景 |
|---|---|---|
| `ANALYZER_HARDWARE_GUIDE_V2.40.md` | 分析仪硬件与 USB 通道 V2.40 | 动 `core/reader_*` |
| `ANALYZER_HARDWARE_GUIDE_V2.30.md` | 旧硬件对照 | 排查老读取器 |
| `ANALYZER_PROTOCOL_SPEC.md` | 分析仪 USB 协议 | 帧格式 / 通道语义 |
| `reader_hid_v240_migration.md` | V2.40 迁移记录 | 动 reader |
| `reader_issues.md` | reader 已知坑 | 动 reader |
| `recal_production_workflow.md` | 再标定产线流程 | 动 `core/fullpipe_worker.py` / `recal_chain.py` |
| `encoder_calib_wheel.md` | 编码器标定轮 | 同上 |
| `inner_zero_calibration.md` | 内圈零位 0x38 | 动 `core/inner_zero.py`：**停机写、写完复位** |
| `foc_test_params_cookbook.md` | FOC 测试参数 | 力矩/速度试验 |
| `kkdiag_usage.md` | 诊断包拆解 | 处理 `diag_*.zip` |
| `realmachine_fault_injection.md` | 真机造障 | 真机验收的异常路径 |
| `playwright_ui_self_test.md` | 自驱 UI 测试 | **任何 UI 交互改动** |
| `scope_chart_freeze_debug.md` | Scope 卡死调试 | Scope 相关 |
【协作上下文（按行号取用）】- §1:23 活从哪来。§1.1:25 **缺陷池 = 飞书多维表格**，base `NbzHbFv86araNbsj8pwcx97ynKf`（:27）、表「02测试缺陷管理」（:44）；修完回填**四个字段**并把缺陷状态改成**待回归**（:29-36：缺陷状态 / 修复版本 / 根因 / 解决方案）。§1.1.1:38 **动手前先把这条单子的附件列一遍**（诊断包 > 复现步骤 > 截图 > 读代码推理）。§1.2:64 **需求池**也是多维表格，表名「待开发的问题及需求汇总」，响应后回填**进展 / 实现版本 / 备注**（:68）。§1.3:70 表格操作：`lark-cli base +record-list --base-token <…> --table-id <…>`（:44），参数是 **`--base-token` 不是 `--app-token`**（:335）。§1.4:74 结论**在与用户对话里交付**（发群模式已废弃）；§1.6:89 两组对接群只用于问缺陷疑问，发言需 gaoxing 审。
- §2:101 相邻仓库：固件仓 = `gitlab.kingkong.tech:embedded/driver.git`，分支 `v3_AI_Develop`（:107），定论文件 `Core/Inc/register_protocol.h` 等（:112-120）；§2.2:122 固件机理速查（排查前先过一遍，别把机理当 bug）。
- §3:187 诊断包与私钥（私钥不在仓内，见 `~/.kingkong_driver` 与 F-025 的取用流程）。
- §4:196 **真机台账**：§4.1:200 台账实体=台架，**主键=读取器 serial**（`docs/PROJECT-CONTEXT.md:213`：`/api/connect`、`/api/state` 返回的 `serial`；总线 id 会漂不可信）；舵机 SN = reg `0x01 kStSerialNumber`（:214，不少设备没烧故读回 None）。§4.2:222 已知台架清单（:224-229，本机可见两条读取器 serial）。§4.3:246 真机操作纪律（白名单 + 写后必复读）。
- §5:258 **本机配置 `~/.kingkong_driver/workspace.json`（不进仓）**：逻辑名 `repos.firmware` / `repos.recalibration` / `keys.diag_private`（:263-273）；缺键必须问用户，**不许瞎猜路径、不许硬编码绝对路径**（:279，对应 AGENTS.md 硬规定 5）。本机实测该文件存在。
- §6:285 新机 onboarding 与 scope 清单；§6.1:312 常见坑：lark-cli 装了但 agent 调不到（PATH）。
- §7:339 发布与分发：§7.1:346 版本号怎么定、§7.2:351 **分支与 tag 是两条命令**、§7.3:362 NAS 分发（固件产物另线 `\\KingKongNAS\software\02SD\_internal\fw-<短 SHA>\`，:398）、§7.4:421 本地 dist 只留当前版、§7.5:426 **陷阱：发版后继续开发再构建会同名覆盖**、§7.6:440 **发版后必须把 `vX.Y.Z (待发布)` 收成实号**（仓内门禁扫不到，写在别人的工单页面上）。
【三条自验路径（后续开发每次都要走）】1. UI 改动 → `docs/skills/playwright_ui_self_test.md` + AGENTS.md 军规 13：**必须可见窗口 / Electron 正式界面**，裸 API、headless、静态截图都不算验收通过。
1. Scope / 图表改动 → `docs/skills/scope_chart_freeze_debug.md` + 军规 4：**必须让真实数据流起来看渲染结果**（"曲线不绘制"那次 DOM 与截图全正常）。
2. 真机相关 → `docs/skills/realmachine_fault_injection.md` 造障 + §4 台账按**读取器 serial** 对号；结论里"底层链路通过"与"真机验收通过"不能混写。

**验证方法**: - 引用真实性核查（本次实跑）：脚本收集 `AGENTS.md` 里所有 `docs/**.md` 引用做存在性判断（9/9 命中）；`ls docs/project_rules` 报不存在；`grep -n 'class Cmd' core/protocol.py`=16、文档字符串在 :17。
- 台账对号：`/api/state` 取 `serial` 与 `docs/PROJECT-CONTEXT.md:224-229` 表内记录比对（本次未连设备，仅核代码与文档行号）。
- 文档改动自证：改 `docs/` 或 `AGENTS.md` 时按硬规定 4 当场跑一遍引用的命令；发版前按 §7.6 回收工单里的"待发布"占位。

**踩坑 / 已知异常与失败经验**: 踩坑（文档引用不实，2026-10-13 逐条核过）：1. `docs/protocol/README.md:30` 引 `../project_rules/firmware_versioning.md` —— **`docs/project_rules/` 目录不存在**，照链接走必扑空。
1. `AGENTS.md:173` 说"当前 V3.3；host 代码仍 V3.2，见文档头变更说明"，但 `docs/protocol/rs485_v3.3.md` 头部（:1-50）**没有这段差异说明**；host 仍是 V3.2 的真实证据在 `core/protocol.py:17` 的文档字符串。
2. `AGENTS.md:321` 写"READER_MP 见 `server.py:212`"，实际分叉在 `server.py:341` —— 文档里的行号引用会随重构漂移，引用前先 grep。
3. 反过来也核过：`AGENTS.md` 引用的仓内 `docs/*.md` 路径共 9 个（去重后）**全部存在**，包括 `docs/skills/` 那 12 个被点名的文件；`docs/skills/` 实际 13 份（多出的是 `ANALYZER_HARDWARE_GUIDE_V2.30.md`，AGENTS.md 未列）。
4. `AGENTS.md:349` 与 `docs/PROJECT-CONTEXT.md:465` 引的 `kung-fu/patterns/…`、`kung-fu/checklists/…` 在**另一个仓**（不在本仓），别当本仓路径找。
【原状态说明】已完成（三层结构、13 份 skill、协作上下文章节行号、两处引用不实均经本次实测；未连真机）

**关键文件与接口**: - `AGENTS.md:170-178`（模块→skill 表）、`AGENTS.md:214` 起（军规）、`AGENTS.md:321`（READER_MP 双形态）、`AGENTS.md:349`（对外说人话，引 kung-fu 仓）。
- `docs/PROJECT-CONTEXT.md`（分节见上）、`docs/protocol/README.md`（协议索引，版本源=固件 tag 经 `0x0B` 映射，:28）、`docs/protocol/rs485_v3.3.md`（当前）、`rs485_v3.2.md`（往期）、`archive/rs485_mixed_history.md`。
- `CHANGELOG.md`：`## [未发布]` 从 :17 起；最近三版 `## [0.16.1] - 2026-10-10`:51、`## [0.16.0] - 2026-10-09`:59、`## [0.15.0] - 2026-10-09`:74。体例：Keep a Changelog + semver，**面向使用者、一个点一句白话说清"你会感觉到什么变了"**，按 新增/变更/修复 分组，条目形如「模块·子功能: 用户视角结果」，不写实现细节（约定见 :3-15）。

**状态**: 已完成

### F-060: MES 需求规格文档：数据库、后台管理与业务系统边界
**日期**: 2026-10-13
**项目**: MES (D:\code\mes)
**关键词**: MES, 需求规格说明书, 数据库需求, 后台管理系统, 业务系统, ERP工单八步流程, 来料IQC, TypeORM, 现状与目标边界

**需求场景 / 现象**: 将仓库内 MES 资料整理为完整、清晰、体现流程的需求文档，并明确数据库、后台管理系统、业务系统三部分。

**方案 / 实施步骤**:
方案要点：
以独立子系统章节组织数据库、管理员管理端和业务作业端，同时绘制系统上下文架构及端到端业务流程。文档将现状、目标和待确认事项分别标记，避免将规划能力描述为当前已实现。后台管理系统指管理员操作端，与 Express API 后台服务区分；管理端和业务端经 API 访问数据库。将来料接收/IQC明确为ERP工单八步流的前置流程，不计为第九步。现状调查确认 SQLite 默认配置、TypeORM 实体、数据库管理 API 占位响应及 CLI 仅四类数据同步等实现边界。

实施步骤：
1. 检索仓库需求资料、实体、路由及相关实现，区分当前能力与目标。
2. 梳理系统组成、数据域、岗位权限、正常流程和异常/前置流程。
3. 编写带需求编号和需求到验证映射的规格文档。
4. 独立检查章节、流程图、需求编号、现状边界及文档内链接，并完成交叉评审。

**验证方法**: 对最终 Markdown 执行可重复的结构/内容检查；通过条件包括三部分齐全、至少两张流程图、FR-DB/FR-ADM/FR-BIZ 编号及映射齐全、IQC前置边界清楚、现状限制准确和数据库说明链接有效。该方法验证文档内容，不代表产品功能验收。

**踩坑 / 已知异常与失败经验**: “后台管理系统”容易与后台 API 服务混为一谈，且容易把尚未存在的管理端页面、数据库恢复/迁移、审计能力误写为现状；须对照前端路由、授权端点和 CLI 实际覆盖范围表述。IQC不可无依据地并入ERP既有八步流程。

**关键文件与接口**: - `docs/requirements/MES-综合需求规格说明书.md` — MES需求基线、数据库/管理端/业务端需求、流程图、验收映射。
- `DATABASE.md` — 数据库配置参考。
- `.sire/runs/R20261013-074035/evidence/DOC-01/qa/acceptance.md` — 文档验收用例和实际检查结果。

**状态**: 已完成

### F-061: 将会议架构草图转成可验收的 MES 需求
**日期**: 2026-10-13
**项目**: MES / D:\code\mes
**关键词**: MES需求规格说明书, 架构草图, 目标与现状, 工艺配置, 单工序Web, 追溯矩阵, meeting sketch

**需求场景 / 现象**: 制造系统会议经常只有白板或纸面架构草图，图上会混用系统边界、功能编号、箭头、部署图标和业务流程。若直接按推测写规格，容易把目标当作现状、把不明箭头当作强制数据流，导致接口/架构范围被错误冻结。

**方案 / 实施步骤**:
1. 先列草图文字、角色、端和编号，明确哪些是直接观察，哪些是解释。
2. 将目标架构和业务时序分开画，数据库访问统一经过应用服务。
3. 每条能力标出现状、目标或待确认，并将不确定项绑定责任人/评审阶段。
4. 追踪矩阵按需求编号覆盖功能、非功能和验收条目，自动校验唯一覆盖。
方案 / 架构：整理为需求时将内容分成三层：①明确可观察元素和用户描述（端、角色、菜单、编号、箭头）；②业务解释形成的目标方向（须标为目标，不写成已实现）；③未确定的语义和技术细节（列责任岗位、确认点及影响，进入待确认清单）。用系统上下文图表达端到服务端再到数据库的访问边界；另用业务流程图表达配置发布、外部数据进入、现场执行、门禁及分析查询时序。若箭头含义不明，避免将其编码为权限或数据依赖。为全部 FR/AC/NFR 建立需求到验证映射，并用机械检查确保无虚构编号、无未映射项、无重复范围。

**验证方法**: 本次文档静态验证命令为 `python -X utf8 .sire/runs/R20261013-080954/evidence/DOC-MEETING-01/qa/verify_requirements_doc.py`；17 项检查通过，包含 FR/AC/NFR 每项只映射一次、架构流程不允许客户端直连数据库、工序循环可回到下一工序界面。

**踩坑 / 已知异常与失败经验**: 根因：（问题类必填）: 草图是沟通输入，不是完整架构或经确认的状态机。图中标记、箭头、服务器细节遮挡或角色职责不完整时，无法单凭视觉线索确定实现方式、时序和权威数据源。
踩坑：需求矩阵的总览行若重复引用专项行编号，会制造重复覆盖；流程图若只有架构图遵守 API/DB 边界、业务图仍画客户端直连 DB，也会造成规格自相矛盾。最后一次全文件检查应同时核对流程顺序和数据访问边界。

**关键文件与接口**: - `docs/requirements/MES-综合需求规格说明书.md` — 本次 MES SRS 对会议草图的实践整理。
- `.sire/runs/R20261013-080954/evidence/DOC-MEETING-01/qa/verify_requirements_doc.py` — 文档编号、流程图、事实边界和追踪矩阵静态检查。

**状态**: 已完成

### F-062: Output目录：MPT协议回归与USB描述符探测快照（含USB Hub探测与A~F测试副作用的坑）
**日期**: 2026-10-13
**项目**: Output 目录只读分析
**关键词**: Output, MPT, A~F协议回归, Analyzer, USB描述符, pyusb, USB Hub IOCTL, 快照, source of truth

**需求场景 / 现象**: 需要梳理 Output 目录（MPT A~F 协议回归测试 + USB 描述符探测脚本）的用途、组成和注意事项时。

**方案 / 实施步骤**:
1. 只读取目录清单、说明文档及脚本入口/主要调用和副作用，不修改原始文件。
2. 两组快照彼此独立：A~F 六种编码器协议 Python 驱动与硬件回归测试；USB 描述符多产品线固件说明与三种 Windows 主机侧探测脚本。不构成单个可安装 Python 包。
3. 与 SIRE 现存 MPT/A~F 硬件验证和 Analyzer 记录对照，旧记录不作为本次硬件实测证据。

**验证方法**: PowerShell 只读枚举文件、行数和大小；检查测试脚本入口、stage_control、CSV/log 输出和 USB 探测路线。未运行硬件脚本，没有连接或操作设备。

**踩坑 / 已知异常与失败经验**: 1. Output 是从其他目录拷贝的冻结快照，不会同步源目录。
2. A~F 测试会写设备状态并覆盖输出文件，运行前要确认设备与输出目录。
3. USB Hub 探测 PID 固定 0x0001，只匹配 M01。
4. 常规 OS 缓存拿不到未引用的字符串 index=4。

**关键文件与接口**: test_mpt_protocol_regression_AtoF.py（A~F 主流程）；EncoderBase.py、Analyzer.py（再标定 API/通信基础）；mpt_*_protocol.py、bissc_protocol.py、CRC.py（协议帧解析和校验）；usb_descriptors/probe_usb_descriptors_hub.py（Hub IOCTL 探测）；usb_descriptors/USB描述符修改说明.md

**状态**: 已完成（只读静态分析；未执行设备验证）

### F-063: 当前分支DPB单圈标定能力与DPT及输出限制
**日期**: 2026-10-13
**项目**: EncoderPlotter_0903_01 / feature/dpb-single-turn-calibration
**关键词**: DPB, DPT, 单圈标定, 内外圈独立标定, calibrationTarget, disabled ring, 角度状态位

**需求场景 / 现象**: 审查单圈标定需求在当前分支的覆盖情况。

**方案 / 实施步骤**:
方案要点：
当前分支仅 DPB 开放单内圈/单外圈再标定，默认 both，前后端互斥并只采集/解算目标圈；DPT 尚未接入此选择。算法说明仍重建并保持双圈输出，因而没有实现“关闭圈角度固定0度”；相关状态位未找到明确清零逻辑。

实施步骤：
只读检查当前分支代码、算法文档和共享知识库。

**验证方法**: 源码静态核对；未做真实界面、未装圈硬件或最终协议帧验收。

**踩坑 / 已知异常与失败经验**: 不适用；这是分支覆盖审查。
无。

**关键文件与接口**: - `components/encoder/device.html` — DPB 条件下显示单圈选项。
- `components/encoder/device.js` — DPB 限定、UI 互斥。
- `controller/python/Encoder.py` — 目标系列与互斥校验、calibrationTarget 映射、非目标 Hall 不传入。
- `controller/python/sub_embedded/EncoderBase.py` — 目标圈采集完成条件。
- `controller/python/sub_algorithm/main.py` — calibrationTarget 校验和保留双圈输出说明。

**状态**: 部分完成

### F-064: MES SRS 集成多版本 DPB 工艺图与 Word 静态流程图
**日期**: 2026-10-13
**项目**: D:\code\mes
**关键词**: MES 需求规格说明书, DPB 定子工艺流程, 工艺版本, DOCX 图号, 需求追踪, MES-SRS-001

**需求场景 / 现象**: 将会议绘制的多版本制造流程图纳入综合 MES SRS，并同步生成包含流程图截图的 Word 版。

**方案 / 实施步骤**:
方案要点：
A/B 流程独立记录并保留原始图像，分别整理工序顺序、动作/数据、追溯需求、验收条件和待业务确认事项。与通用 MES 业务流程图区分编号。Markdown 作为内容基线；Word 内嵌三张由 Mermaid 图生成的静态图片及两张原始会议截图。静态 DOCX 检查确认全部 Markdown 内容、表格、需求编号和五张图片映射。

实施步骤：
1. 按截图分别摘录工序顺序，明确差异和图上未说明的动作/门禁为待确认。
2. 增加唯一需求/验收编号和追踪关系，在版本历史中登记 0.9。
3. 生成 DOCX 并把 Mermaid 源图作为图片插入，保持图号连续。

**验证方法**: `validate_srs.py`: issues=[]、13 张 Word 表格、5 张图片、105 个需求编号；`content_coverage.py`: missing source text lines/cells: 0。独立结构复核确认 0.9 版本行和图 3-2/3-3 位置正确。页面渲染未能执行：环境无 Word、LibreOffice、WPS 或连接的文档会话；视觉分页/裁切仍待真实检查。

**踩坑 / 已知异常与失败经验**: 两张同名产品流程截图显示的工序顺序和检查次数不一致；图中部分动作/失败门禁未定义，不能合并或擅自推导。
更新 Markdown 后需重新构建 DOCX；最初 DOCX 没有 0.9 版本历史行，且 DPB 图号不连续。修正 Markdown 并重新构建后，独立复核通过。不要把静态结构检查当作全页视觉验收。

**关键文件与接口**: - `docs/requirements/MES-综合需求规格说明书.md` — 统一需求基线，版本 0.9。
- `docs/requirements/MES-综合需求规格说明书.docx` — Word 排版版，五张流程截图/图示静态内嵌。
- `docs/requirements/assets/dpb-stator-process-a.png` — 用户提供的 A 流程原图。
- `docs/requirements/assets/dpb-stator-process-b.png` — 用户提供的 B 流程原图。

**状态**: 部分完成

### F-066: EncoderPlotter feature/data-generation 分支打包原理与流程（含 Debian 实情）
**日期**: 2026-10-13
**项目**: EncoderPlotter1 / origin/feature/data-generation（本地无该分支）
**关键词**: 打包原理, electron-builder, NSIS, deb, Ubuntu 2204, Debian, udev, nuitka, GitLab CI, verify-linux-deb-path, LINUX_PRODUCT_NAME, 免安装zip, HTTP API 包

**需求场景 / 现象**: 要把 `feature/data-generation` 分支的打包规则（Windows / Debian / Ubuntu）整理成一份"原理 + 流程"文档，产物落在该仓 `docs/packaging-rules-data-generation.md`（237 行，66 处 `文件:行` 锚点）。

**方案 / 实施步骤**:
方案要点：
1. **该分支没有独立的 Debian 构建通道。** Linux 只有 runner tag `ubt2204`（Ubuntu 22.04）、electron-builder 只有 `deb` 一个 target；`git grep -in debian origin/feature/data-generation -- ':!asset'` 零命中（唯一命中是 vendored fontawesome 的 `.fa-debian` 图标类名）。所以"Debian"在这套规则里指**包格式**，不是被支持/被验证的目标系统。
2. 该分支相对 `origin/develop` 的打包差异只有三条（numstat：`.gitlab-ci.yml` 24 增 14 删 + 新增 `scripts/verify-linux-deb-path.sh` 49 行）：① deb 的 `-c.productName` 改用 ASCII slug（新变量 `LINUX_PRODUCT_NAME`），中文名只进 `-c.linux.desktop.Name`，因为 productName 决定 `/opt/<productName>`，Nuitka standalone 的中间件路径不能带中文括号；② 每个 deb 构建点后立刻跑 `verify-linux-deb-path.sh`（共 6 处：dev/test/release 各内外两变体），`dpkg-deb -x` 真拆包断言 `/opt/<slug>` 存在且 `/opt` 一级目录名全 ASCII；③ `test-python` 用 `sub_algorithm/tests/test_dpb_flash_layout.py` 替掉了 develop 的 `sub_embedded/tests`。
3. 整条产物链的原理是"**一次 nuitka、多份产物、变体只靠环境变量 + `-c.` 覆盖**"：`gen-buildinfo → nuitka(main.dist) → 每变体一轮 [gen-target → electron-builder → 后处理]`。`pack-portable.mjs` 消耗 `win-unpacked`（必须紧跟产出它的那次 electron-builder），`pack-http-api.mjs` 复制 `main.dist` 不消耗。electron-builder 的 `${env.X}` 插值只对 pattern 字段生效，所以 `productName/executableName/artifactName` 之类差异一律由 CI 命令行覆盖。
4. Linux 侧最脆的一环是串口权限：udev 规则文件名编号**必须 <73**（`73-seat-late.rules` 只对已打 uaccess 的设备落 ACL），规则要带 `ENV{ID_MM_DEVICE_IGNORE}=1` 躲 ModemManager 探测竞态，规则文件**按包名分文件**（共享名会让卸任一变体掐断其余变体）。维护者脚本里**不能出现 `${纯字母}`**（fpm 宏展开会炸，注释里也不行）。
5. deb 的出包节奏各通道不同：`dev-`/`test-v` 是 **when: manual**，`rc-v` **完全不打 deb**（登记在案的未覆盖风险），只有正式通道 `build-ubt-release` 自动且被 `release` 的 `needs` 卡住。

实施步骤：
6. `export MSYS_NO_PATHCONV=1` 后用 `git show origin/feature/data-generation:<path>` 取回 CI、builder、6 个 scripts、2 个 build/linux 脚本（不 checkout、不动工作区）。
7. `git diff --numstat origin/develop <ref> -- .gitlab-ci.yml scripts/` 定出"本分支专属差异"，避免把主线规则当成分支规则。
8. 按"总原理 → 流程（stage×通道矩阵）→ Windows → Ubuntu/deb → 回归网 → 产物身份 → 本地能做什么 → 与 develop 差异"八段写文档，每条断言配 `文件:行`。
9. 写 `cross-check.sh` 把文档与分支原文对账（见验证方法），锚点越界与数字不符当场红。

**验证方法**: 台账 `.sire/runs/R20261013-143003/cross-check.sh` —— 文档与分支原文对账（副本 cmp、Debian 零命中、tag 前缀、6 处 verify、6 处 ASCII slug、DPB 用例、66 处锚点不越界），本次 PASS。

**踩坑 / 已知异常与失败经验**: 不适用；本次是把散在 CI/配置/脚本里的打包规则读穿并沉淀成一份可核对的文档，不是一次性问答——文档已入库、结论可跨分支复用。
git-bash 下 `git show "其他分支:路径"` 的参数会被 MSYS 转换毁掉（冒号变分号、斜杠变反斜杠）报 `fatal: ambiguous argument`；必须先 `export MSYS_NO_PATHCONV=1`。见 E-015（跨分支读文件必设 MSYS_NO_PATHCONV）。

**关键文件与接口**: - `.gitlab-ci.yml`(582) — tag 通道矩阵、5 个 gate job、win/ubt 两类基座 job、NAS 落位。
- `electron-builder.yml`(87) — 静态基线与缺省值；`build/installer.nsh` — 磁盘空间检查与默认安装目录。
- `build/linux/after-install.sh` / `after-remove.sh` — 顶替内置 postinst、udev 规则、dialout。
- `scripts/verify-linux-deb-path.sh`、`pack-portable.mjs`、`pack-http-api.mjs`、`gen-target.mjs`、`gen-buildinfo.mjs`、`deb-migration-test.sh`（沙箱，五条通道全跑）、`deb-realmachine-test.sh`（真机，CI 只备料、装卸由人 sudo）。

**状态**: 已完成

### F-067: DOCX统一设置A4纵向并适配流程图
**日期**: 2026-10-13
**项目**: D:\code\mes
**关键词**: DOCX, A4, portrait, python-docx, section geometry, image scaling

**需求场景 / 现象**: 用户要求 MES 需求规格说明书 Word 中所有页面保持 A4 纵向，包括流程图页面。

**方案 / 实施步骤**:
方案要点：
通过 python-docx 将每个 section 固定为精确 210×297 mm，删除横向 section，并把图像最大宽度和高度限制在纵向页面版心内。原文件被锁时，生成独立 A4 纵向 DOCX，待关闭占用文件的应用后再替换。

实施步骤：
1. 对所有 Word 节设定 210×297 mm 与 portrait。
2. 所有流程图以版心宽高上限等比缩放。
3. 验证各节尺寸、需求编号、表格和嵌入图像。

**验证方法**: 6 个 section 全部为 A4 纵向；DOCX 结构检查 issues=[]、13 张表、5 张图片、105 个需求编号；Markdown 内容覆盖缺失 0。页面视觉效果未渲染验证。

**踩坑 / 已知异常与失败经验**: DOCX 构建脚本为宽幅图新增横向 section，并将纸张尺寸设为近似英寸值；既有输出文件又被本机另一进程锁定，无法原位覆盖。
DOCX 原文件被另一个进程打开时无法删除或覆盖；应保留另存输出，待用户关闭占用后再替换。

**关键文件与接口**: - `D:\code\mes\.sire\runs\R20261013-140114\build_srs_docx.py` — `add_section`/`add_figure` 页面设置与图像缩放。
- `D:\code\mes\docs\requirements\MES-SRS-A4-Portrait.docx` — A4 纵向输出。

**状态**: 部分完成

### F-068: DPB4010 主仓与 sub_common 同名功能分支
**日期**: 2026-10-13
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01
**关键词**: DPB4010, feature/dpb4010, develop, sub_common, 同名功能分支, gitlink

**需求场景 / 现象**: 主仓开展 DPB4010 功能开发，且 `sub_common` 同时有 DPB4010 配置改动，需要两个仓库使用对应功能分支。

**方案 / 实施步骤**:
方案要点：
主仓功能分支从 `develop` 创建；子模块有相关改动时，在该子模块当前承载改动的提交上创建同名 `feature/*`，保留工作树改动。主仓 gitlink 仍锁定该提交；后续按子先父后的提交/MR流程推进。

实施步骤：
1. 确认子仓工作树修改与功能目标相符，并确认主仓 gitlink SHA 指向该工作树提交。
2. 在主仓 `develop` 创建功能分支；子仓在承载功能改动的提交上创建同名分支。
3. 核对两个仓库分支名及子仓改动保留状态。

**验证方法**: `git branch --show-current` 两仓均为 `feature/dpb4010`；子仓 diff 仍存在，主仓 gitlink SHA 未变化。

**踩坑 / 已知异常与失败经验**: 子仓 detached HEAD 下可直接 `switch -c` 创建分支，已有未提交修改会保留；切分支不会自动提交或修改主仓 gitlink。

**关键文件与接口**: - `docs/branching.md` — 主仓与子仓功能分支及 gitlink 规则。
- `controller/python/sub_common/config.py` — DPB4010 产品版本配置（本次工作树已有修改）。
- `controller/python/sub_common/dpbFlashLayout.py` — DPB4010 Flash 布局（本次工作树已有修改）。

**状态**: 已完成

### F-069: DPB4010 子仓与主仓 gitlink 提交顺序
**日期**: 2026-10-13
**项目**: EncoderPlotter_0903_01 / feature/dpb4010
**关键词**: DPB4010, sub_common, gitlink, child before parent, commit

**需求场景 / 现象**: 用户要求提交本地 DPB4010 改动，改动分布于子模块与主仓指针。

**方案 / 实施步骤**:
方案要点：
先在 sub_common 提交两个 DPB4010 配置文件，再在主仓提交更新后的 gitlink。保持子先父后，未推送。

**验证方法**: 子仓提交 `5ce4962`、主仓提交 `f8d6f7ab`；两仓 `git status` 干净；主仓 gitlink SHA 等于子仓 HEAD；`git diff --check` 无空白错误。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: - `controller/python/sub_common/config.py` — DPB4010 产品与升级配置。
- `controller/python/sub_common/dpbFlashLayout.py` — DPB4010 Flash 布局。
- 主仓 `controller/python/sub_common` gitlink。

**状态**: 已完成

### F-070: EncoderPlotter 测试包 tag 规范与序号选择
**日期**: 2026-10-13
**项目**: EncoderPlotter_0903_01 / DPB4010
**关键词**: test-v tag, package.json, test sequence, CI_COMMIT_TAG, DPB4010

**需求场景 / 现象**: 为已推送的 feature 分支触发符合仓库规范的测试包构建。

**方案 / 实施步骤**:
方案要点：
主仓测试包 tag 使用 `test-vX.Y.Z-NN[-描述]`；版本号取 package.json，序号按远端同版本最新序号递增。CI 由主仓 tag 触发，因此不在子模块创建 test tag。

**验证方法**: 本仓 package.json 为 4.10.0，远端最新序号为 81；`test-v4.10.0-82-dpb4010` 与 `feature/dpb4010` 远端均指向 `f8d6f7ab`。

**踩坑 / 已知异常与失败经验**: `dev-<描述>` 是仅供自验的独立通道；给同事测试并生成正式测试包时应使用 `test-v*`。同一测试版本序号需查询远端现存 tags 后递增。

**关键文件与接口**: - `docs/build-and-release.md` — 测试 tag 格式与序号规则。
- `.gitlab-ci.yml` — `test-v` tag 规则触发流水线。

**状态**: 已完成

### F-071: MES四部分需求文档与系统设计补充
**日期**: 2026-10-14
**项目**: MES (D:\\code\\mes)
**关键词**: MES, 需求说明, 系统设计, 订单生命周期, 动态字段, 工艺版本, 角色矩阵, 流程图

**需求场景 / 现象**: 用户要求以系统设计者角色整理 MES 需求说明，用户给出的会议内容作为参考输入；文档需集中呈现系统描述、功能与角色、订单主流程和操作流程、非业务平台信息，并指出设计缺项。

**方案 / 实施步骤**:
设计结论：将系统划分为业务 Web、后台管理 Web、后台服务、数据库四部分。采用领域对象与配置元数据分层：订单、工艺、工序任务、流程实例、质量、物料、SN 保持稳定关系；业务扩展字段、页面呈现和受限流程规则由配置驱动。平台保留稳定 ID、状态、引用、权限和审计语义。发布配置不可原位修改，实例绑定版本；动态字段的查询/索引按授权启用。订单状态、流程状态、工序状态和质量处置状态分开建模。

**验证方法**: 结构检查确认四个主体章节、3 个 Mermaid 流程图、两张原始 DPB 图均存在且链接有效；需求说明内容检查未发现重复需求编号。该检查验证文档结构，不代表 MES 产品功能验收。未修改 Word。

**踩坑 / 已知异常与失败经验**: 设计者需业务确认：ERP 工单权威来源和变更规则；八步与路线工序的状态映射；在制实例版本迁移；字段能力和查询边界；数据/字段授权矩阵；DPB A/B 适用关系及抽检标准；性能、部署、恢复、留存和集成指标。
限制：当前仅完成 Markdown 需求基线；流程规则和业务字段细节仍需责任岗位评审，不能作为批准的生产操作规程。
【原状态说明】Markdown 重构完成，待业务/产品/工艺/质量/仓储/IT 评审。

**关键文件与接口**: - `docs/requirements/MES-综合需求规格说明书.md` — 四部分架构、功能角色矩阵、订单主流程及分支、登录/配置/业务操作流程、DPB A/B会议截图及设计确认项。

**状态**: 部分完成

### F-072: MES需求确认基线审查与会议决议清单
**日期**: 2026-10-14
**项目**: MES (D:\\code\\mes)
**关键词**: MES, 需求确认, 评审会议, 签字基线, 验收条件, 状态机, 权限矩阵

**需求场景 / 现象**: 用户要求从专业系统设计角度审查现有 MES 需求文档是否能用于需求确认，并说明会议还需确认的内容。

**方案 / 实施步骤**:
方案要点：
当前 Markdown 可作为需求评审/澄清会议的讨论基线，但不能直接作为最终签字验收基线。主要缺口是：功能条目没有逐项需求编号、优先级、可测验收条件和追踪映射；角色没有最终职责/数据/字段/审批矩阵；ERP 八步和工艺路线的状态映射及订单状态机未冻结；主数据责任、订单变更、质量返工、动态字段首期范围、DPB A/B 适用范围、集成和量化非功能指标待确认。
议程按范围优先级、系统边界/主数据、订单生命周期、工艺/质量和异常、DPB A/B、动态字段版本、角色权限审计、接口部署非功能、验收与签署推进。每项须形成责任人、明确决议、例外分支、需求条目和验收证据；未决项记录负责人和期限，不把讨论意见直接视为批准。

**验证方法**: 静态审查需求结构及待确认项；修正系统上下文图的 ERP 导入箭头，未执行产品功能验收，也未修改 Word 或代码。会议决议后需把确认结果转成编号需求和可测试验收标准。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: - `docs/requirements/MES-综合需求规格说明书.md`；审查清单见 `.sire/runs/R20261014-081849/review.md`。

**状态**: 已完成

### F-073: MES需求文档会议确认清单附录
**日期**: 2026-10-14
**项目**: MES (D:\\code\\mes)
**关键词**: MES, 会议确认清单, 决策记录, 责任人, 期限, 需求基线

**需求场景 / 现象**: 用户希望将会议上需要确认的事项直接放入需求文档末尾，便于开会逐项记录。

**方案 / 实施步骤**:
方案要点：
在需求说明末尾新增会议确认清单，覆盖一期范围、系统边界/数据责任、订单生命周期、ERP 八步与路线映射、生产准备与物料、质量门禁/异常、DPB A/B、自定义字段/版本、角色权限、接口/平台非功能、报表追溯及验收冻结。每项包含建议确认角色和结论/负责人/期限记录位，并增加会议结论汇总表。文档版本升为 1.2。

**验证方法**: 检查附录位于文档末尾、12项议题齐全、原 Mermaid 流程图数量不变、DPB 图片链接有效。仅静态文档检查，不代表功能测试。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: - `docs/requirements/MES-综合需求规格说明书.md`
- `.sire/runs/R20261014-083925/validation.md`

**状态**: 已完成

### F-074: MES飞书评审文档完整同步与DPB结构化整理
**日期**: 2026-10-14
**项目**: D:/code/mes
**关键词**: MES, DPB, 需求确认, 飞书, Word, 动态字段, 版本, 角色场景

**需求场景 / 现象**: 用户要求完整需求进入指定飞书文档，保留四部分功能、订单主流程与分支、角色使用场景、平台要求和末尾会议清单。原图片无法直接写入时允许整理图内内容。

**方案 / 实施步骤**:
方案要点：
以完整富文本 HTML 写入飞书；按标题、表格、流程箭头组织。DPB A/B 分别保留11和13工序，整理13项动作和信息，明确重复工序、抽检和追溯关联。空白或细字不擅自推定。宽表改为角色分节，避免窄屏裁切。稳定平台属性与动态业务字段分层，定义不可变发布版本及实例绑定。
由同一 HTML 同步 Markdown，补四个 Mermaid 图和两个原始 DPB 截图，生成 A4 纵向 Word。

**验证方法**: 实际打开飞书，替换正文，检查目录、角色场景、DPB表格前后段及保存状态。截图在 evidence/。独立复核发现业务员概称与设备门禁表述问题，已统一。主流程图取消/变更的变更分支以相邻表格补充，图中未单独画出。
Word结构检查为7节A4纵向、11表、6图片；渲染器缺soffice.exe，视觉分页验证BLOCKED，不声称通过。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: docs/requirements/MES-综合需求规格说明书.md
docs/requirements/MES-SRS-1.3-A4-Portrait.docx
.sire/runs/R20261014-084207/feishu-v1.3.html

**状态**: 已完成

### F-075: MES 代码现状基线与 SRS v1.3 差距矩阵（2026-10-14 实测）
**日期**: 2026-10-14
**项目**: MES / D:\code\mes
**关键词**: MES 现状基线, 编码器 MES, Express TypeORM, Vue3 Electron, 配置版本未建模, synchronize true 无 migration, 飞书 OAuth 唯一登录, MES_ADMIN_OPEN_IDS, 三套状态并存, 需求差距矩阵, 112 handler

**需求场景 / 现象**: 需要一份可复核的"代码到底实现了什么"基线，用来对照需求说明书 v1.3（业务端/管理端/后台服务/数据库四部分），并回答差距在哪。仓库自带清单文档（README、DELIVERY_CHECKLIST、ACCEPTANCE_CHECKLIST）与实际严重不符，不能作为现状证据。

**方案 / 实施步骤**:
1. 计数：`find backend/src/{entities,routes,services} -type f | wc -l` = 39/18/10；按 `^router\.(get|post|put|patch|delete)` 解析 handler = 112；`find frontend/src -name '*.vue' | wc -l` = 22（12 页面）。
2. 鉴权面：逐文件先判 `^router\.use\(.*authMiddleware`（blanket），再看 handler 参数段；结果 112 中 7 个无守卫，全在 `routes/auth.ts`（含两个直接返回 410 的 `/register`、`/login`）。**必须识别 router 级守卫，否则会把 `users.ts` 误报成未鉴权。**
3. 缺口取证（空结果即结论）：`grep -rn version backend/src/entities/*.ts` 仅 2 处业务字段；`effectiveFrom|revision` 0；`grep -rni audit backend/src` 1 处注释；`dataScope|fieldPermission` 0；`serialport|modbus|opcua|net.connect|.pyd|EncoderPlotter` 在 backend/src、frontend/src、electron 全 0。
4. 反向接线检查：`grep -rIo 'pick-lists|stock-transfers|warehouse-locations|/admin' frontend/src` = 0 → 4 个路由文件共 23 个 handler 无前端调用方。
5. 输出差距矩阵，每条"未实现"必须附一次真实检索。
方案 / 架构：用"实测计数 + 逐条 grep 取证"建立现状基线，再按 SRS 章节做差距矩阵。核心判定：
- 现有代码是**执行记录系统**（工单 + ERP 八步 + 工序报工 + 质检 + 追溯 + 编码器测试），不是文档要求的**元数据驱动 MES**；
- 最大面积差两块：后台管理系统（0 页面、`/api/admin/*` 前端 0 调用）与 DPB 定子 A/B 路线（0 建模）；
- 三套状态并存互不相通：`WorkOrderFlow` 6 态硬编码 enum、`OperationWorkflow` 八步、`OperationRecord` in_progress/completed —— 正对应文档"八步与工艺路线映射待确认"，该待确认项优先级最高；
- 可先做、不依赖业务确认的四件工程底线：git 初始化、TypeORM migration、版本化审计、报表/追溯的角色区分。

**验证方法**: 同一批计数由独立子代理（Explore）与主控双向复算；子代理对"无任何 version 字段"判 PARTLY（漏了 firmwareVersion、encoderProductVersion），对"无前端调用方 handler"报 19 而主控按文件实数为 23 —— 两处偏差都必须在交付前改正，证明单源计数不可信。

**踩坑 / 已知异常与失败经验**: 根因：该仓库实体由脚本批量生成（`generate-entities.js`、`fix-columns*.js`），且 `synchronize: true` 无 migration，导致数据模型随实体漂移；文档侧的多份 checklist 停留在早期 4 实体/5 端点规模，从未回写。
踩坑：① `README.md:41` 仍写 React 18（实为 Vue 3）、`DELIVERY_CHECKLIST.md:5` 写"✅ 生产就绪"、`ACCEPTANCE_CHECKLIST.md:73` 写"19个API端点 全部实现"（实际 112），照抄仓库文档会得到完全错误的现状；② `EncoderPlotter/EncoderAnalyzer` 只出现在 `.sire` 历史日志，不属本仓库，别把它当已接入的设备采集；③ 仓库不是 git 仓库，`git log` 类取证一律不可用。
【原状态说明】已完成（只读分析，未运行应用；"已实现"仅指代码存在且路由可达，不等于端到端验收通过）

**关键文件与接口**: - `backend/src/database.ts:62` — `synchronize: true`；`DB_TYPE` 默认 sqlite，`backend/data/mes.db`
- `backend/src/middleware/auth.ts:19-35` — JWT 校验且强制 `authProvider==='feishu'`；`services/loginPolicy.ts:5` 把 DB 里的 admin 降为 operator，除非 openId ∈ `MES_ADMIN_OPEN_IDS`
- `backend/src/entities/User.ts:33` — 角色仅 `admin|supervisor|operator`（文档要求 9 角色）
- `backend/src/entities/OperationStageField.ts` — 唯一的动态字段定义表，仅 fieldKey/label/valueType/required/unit/sequence；`OperationRecord.fieldValues` 用 text 存 JSON
- `backend/src/routes/workorders.ts:102-105` — ERP 导入按 orderNo 去重（配合 `WorkOrder.orderNo` unique），文档要求的导入幂等已实现
- `frontend/src/router/index.ts` — 12 个具名路由，无任何配置/权限/主数据管理页

**状态**: 已完成

### F-076: Nuitka 用原始目录收集需运行时执行的 Python 脚本
**日期**: 2026-10-14
**项目**: driverSoftware / D:\code\driverSoftware
**关键词**: Nuitka, --include-raw-dir, --include-data-files, .py 源码打包, force_calib, 台架脚本, dataStructV4026, GitLab Runner, 构建实物门禁

**需求场景 / 现象**: GitLab Windows 冒烟构建编译后，门禁报告 `tools\force_calib\calibrate_force_v2.py` 未进入 `server.dist`；Runner 的 Nuitka 4.1.3 最终因门禁失败退出。

**方案 / 实施步骤**:
方案要点：
用 `--include-raw-dir=源目录=目标相对目录` 原样递归复制脚本目录；Windows 和 macOS 构建仍在客户包清理前检查关键脚本实际存在。更新错误提示、运行器说明、测试断言及中英用户提示，消除旧规则口径。

实施步骤：
1. 日志定位为产物缺少台架源码。
2. 使用本机 Nuitka 4.1.3 独立 standalone 工程验证 raw-dir 源到目标目录复制。
3. 同步修正配置、双平台诊断提示、说明、测试和界面文案。

**验证方法**: 47 条相关 pytest 通过；独立 Nuitka standalone 编译报告 raw-dir 收集 21 个文件，产物含 `calibrate_force_v2.py` 与 `measure_dyn_zero.py`。完整 `scripts/build.bat --release` 已调用真实构建，但本机现有 `kingkong_calib` wheel 缺显式指定的 `dataStructV4026`，在完整应用编译阶段停止；`--internal` 因工作区原有 `tests/unit/test_port_reclaim.py` 改动被 dirty guard 拦截。

**踩坑 / 已知异常与失败经验**: Nuitka 的数据文件收集规则把 `.py` 视作代码过滤；运行时由 `server.exe --run-script` 执行的台架源码既不是被 Nuitka 编译的模块，也不应作为普通数据文件收集。`--include-data-files` 无法满足该场景。
`--include-raw-dir` 同样要求写 `源目录=目标相对目录`，只有目录参数会报 malformed；先用极小 standalone 程序核对映射和产物，再运行耗时较长的整包构建。

**关键文件与接口**: - `server.py` — Nuitka 项目 pragma 指定源目录和目标目录。
- `scripts/build.bat`、`scripts/build_mac.sh` — 编译后检查两个关键脚本。
- `core/force_calib_runner.py` — 说明打包态脚本由主程序子进程执行。
- `tests/unit/test_run_script_entry.py` — 固定收集选项和实物门禁。

**状态**: 部分完成

### F-077: 多分支纳入审计：主仓祖先图、子仓内容与 gitlink 分开判定
**日期**: 2026-10-15
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01（feature/iap-ota-sn）
**关键词**: branch ancestry, submodule gitlink, feature/dpb-single-turn-calibration, feature/dpb4010, feature/hesai-mpp, feature/mpp-algo-4060, fix/dpb-rs485-compat-display

**需求场景 / 现象**: 用户询问多条功能分支是否已合入目标主仓分支，并要求纳入子仓但排除算法仓。

**方案 / 实施步骤**:
主仓所有 ref 与三个自有子仓全部只读；未切换分支或改动产品工作树。完整命令结果与证据保存在 SIRE 运行台账。
结论与判据：不能只报告父仓 branch tip 的祖先关系；对每个仓执行 `git merge-base --is-ancestor <source-tip> <target-tip>`，另读取目标父仓 commit 的 `git ls-tree` 子模块 gitlink，再在对应子仓核对相关分支 tip 和 feature commit。分支 tip 未合入不必然代表每项代码都缺失，需核对代码提交和当前内容。
【本次验证结果】主仓目标 `feature/iap-ota-sn` tip 为 `65639c24`。五个来源中，DPB 单圈、Hesai MPP、MPP 算法支线、DPB RS485 展示修复的 tip 均为祖先；DPB4010 tip `f8d6f7ab` 不是祖先。该分支的 sub_common 提交 `5ce4962` 也未被目标 gitlink `3dc6ebd` 包含；不过 4.0.10 核心 Flash layout 与 packed-version 修复已由目标历史中更早提交覆盖，剩余差异包含 `config.py` 对 productInfoList / supportedVersions 的配置（包括 4010 支持条目），应按具体使用场景决定是否需要补入。目标 sub_embedded pin `2ba14ad` 已包含单圈和 MPP/Hesai 对应提交。sub_automation 没有同名本地功能 ref，目标当前 gitlink与工作树 commit 为 `3332eb2`，不能断言其分支历史纳入状态。sub_algorithm 按授权忽略。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 限制：本地引用为检查时快照；没有 fetch，不等同于实时远端头。算法仓未核查。
【原状态说明】已完成（只读提交图与当前 gitlink 审计）

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 已完成

### F-078: 标定结果汇总CSV复用日志距离并累计追加
**日期**: 2026-10-15
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01
**关键词**: 标定汇总, CSV追加, CalibrationLogs, deviationItems, SN, 轴向距离, Excel

**需求场景 / 现象**: 标定结束后需要累计导出 SN、轴向距离、结果、时间、尺寸及系列、告警信息，供 Excel 查看。

**方案 / 实施步骤**:
方案要点：
前端复用标定响应的 deviationItems、defectiveItems 和结果时间；轴向值使用标定过程日志显示的同一返回值并保留两位小数，双圈分别输出内圈/外圈。主进程通过同步追加打开 CSV，仅新建或空文件写 BOM 与表头，已有文件仅追加一行，补齐缺失的 CRLF。设置页提供默认关闭的偏好开关；失败、超时、手动停止和通信异常也保存失败行与原因。CSV 单元格转义引号、逗号、换行并防止 Excel 公式注入。

实施步骤：
1. 固定标定开始时的 SN 与文件目录。
2. 从标定结果构建单圈/双圈轴向值、结果和告警行。
3. 主进程追加 UTF-8 BOM、CRLF CSV。

**验证方法**: 四个 JS 文件 `node --check` 与 `git diff --check` 通过；IPC 临时目录验证表头、累计追加、尾换行修复及文件系统错误返回。真实 Electron UI/读取器路径未验收。

**踩坑 / 已知异常与失败经验**: `deviationItems.value` 是标定过程展示的值；需求口径经用户确认采用该值。不能整文件读改写，否则历史表大时成本高且可能覆盖；写追加模式可序列化同进程 IPC。

**关键文件与接口**: - `components/encoder/device.js` — 汇总行字段和标定结束分支。
- `main/file.js` — `append-calibration-summary` IPC 追加文件。
- `components/analyzer/version.html`、`components/global.js` — 配置开关。
- `components/i18n.js` — 中英文提示。

**状态**: 部分完成

### F-079: DPB外部版查看参数显示产品与固件版本
**日期**: 2026-10-15
**项目**: EncoderPlotter_0903_01
**关键词**: DPB, 参数查看, 外部版, series=106, final, software, isInternal, getPropFromArguments, 产品版本, 固件版本

**需求场景 / 现象**: DPB 外部版本查看参数时需要给出产品版本与固件版本；内部版本仍需展示全部参数。

**方案 / 实施步骤**:
方案 / 架构：在参数查看弹窗保留 isInternal 全量参数分支为首分支；其后仅对 DPB series=106 增加外部版分支，产品版本读取 final，固件版本读取 software；其他外部系列仍走原固件版本显示分支。两字段复用 getPropFromArguments 的现有格式化与缺失值处理。产品版本增加中英双语 key。

**验证方法**: git diff --check 通过；三名独立审查员和三路交叉核验通过。真实 Electron/读取器 UI 路径未执行，必须在可操作应用和真实 DPB 参数环境中验收；本次不得以静态检查宣称 UI 通过。

**踩坑 / 已知异常与失败经验**: 踩坑：修改外部显示分支时应保留内部完整信息分支的优先级；系列码 106 是 DPB；final 是产品版本字段，software 是固件版本字段。
【原状态说明】代码完成；真实界面验收 BLOCKED-无法真实验证。

**关键文件与接口**: - components/analyzer/analyzer.html — 参数查看弹窗版本分支。
- components/analyzer/analyzer.js — getPropFromArguments 版本格式化方法。
- components/i18n.js — 产品版本中英翻译。

**状态**: 部分完成

### F-080: DPT V4.2.5 V5参数读取与IAP恢复兼容
**日期**: 2026-10-15
**项目**: EncoderPlotter1（KingKong Encoder Analyzer）
**关键词**: DPT V4.2.5, DPT V5 Arguments, Analyzer, IAP 参数恢复, descriptor a, FunctionArguments

**需求场景 / 现象**: Analyzer 固件 DPT V4.2.5（算法 4060）升级后需读取并恢复 V5 参数，同时兼容旧固件和历史调试文件。

**方案 / 实施步骤**:
1. 按参考工具的 DPT V4.2.5 结构与 a 描述符映射实现兼容读取。
2. 用原始 V5 结构作为写回基底，仅更新已确认字段并保留其他字节。
3. 在主仓 IAP SN 恢复路径验证只变更 SN 对应字节。
方案 / 架构：在 sub_common 加入 V5 typed Arguments / FunctionArguments 结构；sub_embedded 对新描述符进行严格校验，完整读取并比对 R/s 字节，结构不一致时拒绝解析。写回时以原 V5 结构为底稿，仅更新明确目标字段，保留未知字段、保留区、prodInfo 和未涉及的函数参数；历史 V5 调试文件读取不额外触发 a 读取。IAP 恢复 SN 时只更新对应字节范围。

**验证方法**: py -3.12 -m pytest sub_embedded/tests/test_dpt_v425_arguments.py sub_embedded/tests/test_recalibration_versions.py -q（48 passed）；py -3.12 -m unittest iap_sn_restore_test（7 tests OK）。未执行真机升级验证。

**踩坑 / 已知异常与失败经验**: 根因：V4.2.5 使用 V5 的 R/s 参数结构与字段描述符；按旧结构或字段名推断布局会误读数据。字段描述符 a 只用于读取布局，不能作为写入命令。
踩坑：头版本路由属于通用 dispatch；非 DPT/V5 组合需在进入 a 查询前拒绝该新解析器，同时保留旧版本自身的正常分发。
【原状态说明】已完成（离线验证通过，真机 IAP 待验证）

**关键文件与接口**: - controller/python/sub_common/DataFormatter.py — V5 Arguments / FunctionArguments 数据结构
- controller/python/sub_embedded/EncoderBase.py — DPT V4.2.5 参数读取、验证和恢复
- controller/python/sub_embedded/tests/test_dpt_v425_arguments.py — 描述符异常及 live Arguments 构造验证
- controller/python/iap_sn_restore_test.py — IAP SN 恢复字节范围断言

**状态**: 已完成

### F-081: 编码器标定错误与告警源码清单整理
**日期**: 2026-10-16
**项目**: EncoderPlotter_0903_01 / D:\\code\\EncoderPlotter_0903_01
**关键词**: 编码器标定, calibration, 标定错误, 标定告警, 轴向偏差, sub_algorithm, DPT, MPT, partial calibration

**需求场景 / 现象**: 需要形成标定过程中可能出现的错误和告警清单，包含轴向距离阈值提示，并分析算法仓库来源。

**方案 / 实施步骤**:
1. 检索共享知识库并复用标定分析和错误传播背景。
2. 静态扫描当前主仓与锁定算法/公共/嵌入式子模块。
3. 整理对外提示、内部诊断、阈值口径和索引。
方案 / 架构：将清单放在主仓 docs，按用户可见错误、用户可见告警、内部诊断/重试三类组织。对照 Helper.py 消息定义、sub_algorithm 触发点、sub_embedded 采集/读写及 UI 结果映射。明确多层错误可能是同一根因的传播链；阈值配置值和测试回退值分开说明。未被生产路径调用的消息定义单列为未确认启用。

**验证方法**: `git diff --check` 与两个仓库的 `git diff --check` 通过；检查主仓和算法 docs 索引链接、确认 `.gitignore` 放行清单文档。未执行真机标定或错误注入。

**踩坑 / 已知异常与失败经验**: 根因：（问题类必填）: 不适用；这是源码分析与文档整理。
踩坑：`minAxialDeviationTh` 等四个检查值可由运行参数 `thresholdConfig` 覆盖；算法源码中的 `_Test` 值只是缺省/测试回退，不能作为全部型号规格。消息定义不等于生产路径已启用，须核对实际 `addLog` 调用。
【原状态说明】已完成（静态源码分析；真机逐条触发未验证）

**关键文件与接口**: - `docs/calibration-errors-and-warnings.md` — 完整清单。
- `controller/python/sub_common/Helper.py` — 消息文本、等级及错误码。
- `controller/python/sub_algorithm/Rtools.py`、`main.py`、`CalcAngles.py`、`CalcAnglesHalf.py` — 触发条件与算法传播。
- `controller/python/sub_embedded/EncoderBase.py`、`controller/python/Encoder.py`、`components/encoder/device.js` — 采集、写读错误及界面/MES结果。

**状态**: 已完成

### F-082: 标定错误告警清单转换为DOCX的版式与验证
**日期**: 2026-10-16
**项目**: EncoderPlotter_0903_01 / D:\\code\\EncoderPlotter_0903_01
**关键词**: DOCX, Word文档, calibration errors warnings, python-docx, render_docx, LibreOffice缺失

**需求场景 / 现象**: 将已确认的编码器标定错误与告警 Markdown 清单转成交付用 Word 文档。

**方案 / 实施步骤**:
1. 复用 F-081 清单和 F-067 DOCX 页面经验。
2. 生成 Word 标题、分节文字与错误/告警分类表。
3. 用 python-docx 解析验证结构、关键条目、表格行数和页面尺寸。
方案 / 架构：使用共享依赖中的 python-docx 生成 Letter 纵向文档，设置中文字体、标题层级、错误/告警两张可跨页重复表头的表格，并保留阈值配置口径及来源说明。页面视觉检查调用标准 render_docx.py，但运行环境缺少 LibreOffice soffice.exe；也未安装 Microsoft Word。

**验证方法**: 文件存在、可由 python-docx 打开；包含 2 张表（15 行、11 行）、轴向预警/错误配置字段、主要错误告警章节；页面尺寸 8.5 x 11 in。标准页面渲染失败，未能目测所有页。

**踩坑 / 已知异常与失败经验**: 根因：（问题类必填）: 不适用；格式转换任务。
踩坑：PowerShell 调用文件写入时应使用 ASCII 文件名输出，避免此主机控制台编码把中文路径显示成乱码；最终文件采用 `calibration-errors-and-warnings.docx`。生成清单表后不要依赖源 Markdown 表格原样转换，应将三列表格显式设列宽并重复标题行。
【原状态说明】部分完成（Word 结构/内容通过；视觉渲染受限）

**关键文件与接口**: - `docs/calibration-errors-and-warnings.md` — 文本来源。
- `docs/calibration-errors-and-warnings.docx` — 最终Word文件。
- `render_docx.py --emit_pdf` — 视觉QA渲染器，因 soffice.exe 缺失未能运行。

**状态**: 部分完成

### F-083: Bootloader 扫描目标与普通设备选择隔离
**日期**: 2026-10-16
**项目**: driverSoftware
**关键词**: Bootloader, RS485, device scan, boot jump, APP recovery, 固件档案

**需求场景 / 现象**: Bootloader 设备不响应普通 read_version，用户仍需明确选择 Boot ID 并跳回 APP；Boot 目标不能污染普通设备命令目标或 OTA 向导状态。

**方案 / 实施步骤**:
方案 / 架构：在设备页提供独立 Boot ID 扫描、单播 Ping 与跳回入口；目标命令使用 V2Commands 浅拷贝，只改变副本 ID。跳回后普通协议复扫，确认 APP 在线后再绑定普通设备 ID 并刷新 read_version/固件档案。Boot 卡状态与 OTA 向导隔离，并在 reader/普通设备/波特率变化时作废旧结果。

**验证方法**: `git diff --check HEAD^1 HEAD` 通过；三名独立只读审查未发现阻断。按用户要求未运行测试或真机验收。

**踩坑 / 已知异常与失败经验**: 根因：普通设备切换和 Bootloader 命令使用不同协议。把 Boot ID 写入普通连接状态会让界面身份与后续命令目标不一致。
踩坑：Boot ID 不进入普通设备选择流程；只有普通协议复扫确认后才能改绑并刷新固件档案。
【原状态说明】已合入 development；设备验证待现场具备设备后进行。

**关键文件与接口**: - `frontend/js/pages/bootloader.js` — Boot 设备卡与向导状态隔离。
- `server.py` — 指定 Boot ID 的 Ping/Jump 路由。
- `frontend/js/api.js` — Boot ID 参数。

**状态**: 部分完成

### F-084: 端口回收按本机项目绝对路径识别服务
**日期**: 2026-10-16
**项目**: driverSoftware
**关键词**: server.exe, server.py, 端口回收, 绝对路径, Nuitka, process identity

**需求场景 / 现象**: 项目启动时清理残留端口进程，不能误结束其他软件目录下恰好同名的 server.exe 或 server.py。

**方案 / 实施步骤**:
方案要点：
Python 服务要求命令行脚本绝对路径规范化后等于当前 server.py；Nuitka 服务要求镜像路径等于 paths.host_executable()。start.bat 传入脚本绝对路径；无法确认路径时保留现有进程。

**验证方法**: `git diff --check HEAD^1 HEAD` 通过；三名独立只读审查确认跨目录同名服务不会被识别为本项目服务。按用户要求未重跑测试。

**踩坑 / 已知异常与失败经验**: 只比较进程名会把无关项目的服务误认成本项目实例。
Nuitka 打包环境的 `sys.executable` 不一定是 `server.exe`；应以 `paths.host_executable()` 为当前宿主程序路径。

**关键文件与接口**: - `server.py` — `_is_our_server_proc`。
- `start.bat` — 传入绝对脚本路径。
- `tests/unit/test_port_reclaim.py` — 路径归属用例。

**状态**: 已完成

### F-085: sire_comms 按会话 id 绑定通讯身份与双方原文展示
**日期**: 2026-10-18
**项目**: SIRE / D:\sire\AI\AI
**关键词**: sire_comms, 会话绑定, session id, bind, rebind, SIRE_SESSION, bindings.json, 串话, 通讯, 协作, 原文展示

**需求场景 / 现象**: 多个 Claude 会话共用 Claude 身份，在 d--code-mes 信箱里给 Codex 发出互相矛盾的回复（#10 说转用户决定，#11 另一会话说已修复）。用户要求通讯固定在指定的一对会话里，双方会话都能看到完整往来。

**方案 / 实施步骤**:
方案要点：
按项目把身份绑定到会话 id；绑定后只有该会话能以该身份写入或读信箱，其他会话退出码 2；查看类命令不受限；切换须用户要求后 --rebind。消息记录 from_session/to_session。合同要求双方逐条原文展示收发消息。

实施步骤：
1. `sire_comms.py --project <项目> --session <id> bind --me Claude`（Codex 同理）
2. 之后所有以该身份的命令带 `--session <id>` 或设置 SIRE_SESSION

**验证方法**: `python -m unittest test_sire_comms`（12 OK，c10–c12 覆盖绑定、拒绝、rebind、跨项目信箱跳过）；真实项目未带会话发送返回 exit=2，绑定会话发送 #18 记录双方会话。

**踩坑 / 已知异常与失败经验**: sire_comms 只按身份名（Claude/Codex）路由，不区分同一身份的不同对话。
Git Bash heredoc 传中文给 python 需 PYTHONUTF8=1；Claude 会话 id 可从 scratchpad 路径中的 UUID 取得；--rebind 与改用未绑定身份只能靠合同约束。

**关键文件与接口**: - `sire/workflow/shared/sire/scripts/sire_comms.py` — Channel.bind / check / bindings，全局 --session，bind 子命令
- `D:/sire/sire_comms/projects/<项目>/bindings.json`
- `references/global-contract.md` § 本机通讯：会话绑定、双方对话原文展示

**状态**: 已完成

### F-086: Claude-Codex 协作通讯机制：会话绑定、实时推送、常驻与会话id可变（v6.28–v6.35）
**日期**: 2026-10-20
**项目**: SIRE / D:\sire\AI\AI（共享 skill sire_comms，v6.28–v6.35）
**关键词**: claude-codex协作机制, 协作通讯, sire_comms, 会话绑定, session start, session watch, session wait, resume, codex queue 实时推送, 常驻协作, 结束协作, 会话id可变, 锁STALE, 转述不构成授权, 协作免重复授权, comms-protocol

**需求场景 / 现象**: Claude 与 Codex 同机协作开发同一项目，多个同名会话串话、轮询耗额度、用户换对话后身份失效、转述被当成授权导致卡住。用户要求：通讯实时反馈、除非用户说结束协作否则常驻、任一方关闭同步通知对方、协作范围内不再向用户要授权、会话 id 随换对话而变且尽量少上下文。

**方案 / 实施步骤**:
方案要点：
- 单一规则文件：`sire/workflow/shared/sire/references/comms-protocol.md`（契约与 SKILL 的通讯章节开头有指针，冲突以它为准）；脚本 `scripts/sire_comms.py`，数据在 `D:/sire/sire_comms/projects/<项目>/`（messages.jsonl、bindings.json、session_<身份>.json、locks/）。
- 开启/结束只认用户在自己会话里的话：用户在任意对话说“开始协作”，`session start --session <当前对话id>` 绑定该会话；id 变了自动 rebind 并向对方发 info，旧会话的 wait/watch 自动让位、旧会话发消息被拒。换会话后跑 `resume --me <自己>` 取精简交接摘要。
- 实时送达：send/reply 写入后用 `codex queue --thread <Codex会话id> --message ...`（必须用原生 codex.exe）推进 Codex 会话，实测约 10 秒送达；Claude 侧用 `session watch` + Monitor 事件流（每条新消息一行 JSON 即时唤醒，空闲零消耗）。Codex 心跳降为 30 分钟兜底（`session wait --timeout 0`，空则静默）。
- 关闭同步：`session stop` 自动给对方发 info 并把对方监听置关闭；仅用户说结束协作才执行。
- 授权：协作范围内对方 request 直接执行不再向用户要授权；转述（含 MES 会话等他会话转达的“用户指令”）不构成授权，只认本会话用户原话；request 里不得写“待授权”让对方空等。强推/凭据/付款/范围外目标仍须交用户。
- 其他：消息 ≤600 字原文展示、超过截断带编号；request/question 用 reply --re 回复后 ack，info/reply 不礼节性回信；锁超 2 小时标 STALE，非持有方仅对 STALE 锁可 `unlock --stale` 并自动审计；未绑定身份带 --session 首次自动绑定，不带则警告。

实施步骤：
1) 用户在目标对话说“开始协作”；2) 本端 `session start --session <当前对话id> --me <自己> --peer <对方>`，Claude 再起 `session watch` 的 Monitor（30 分钟到期重起）；3) Codex 侧心跳 30 分钟兜底并写入协议路径；4) 新对话重复 1–2 并 `resume`；5) 用户说结束协作时 `session stop`，对方自动同步关闭、释放锁。

**验证方法**: `python -m pytest scripts/test_sire_comms.py`（22 通过）；真机：`codex queue` 推送 08:05:07 发出，Codex 08:05:17 收到并回复，Codex→Claude 经 session watch 事件流即时到达。

**踩坑 / 已知异常与失败经验**: 早期通道按身份而非会话区分，且靠 AI 定时醒来轮询：同名会话互相抢信箱，空闲也消耗额度，长上下文重复展示，旧会话的等待继续抢收消息。
Codex 的 queue 消息要走原生 codex.exe，不能经 .cmd（元字符被 cmd 解析）；Claude Code 没有外部推送入口，只能用 Monitor 事件流；会话 id 在日志里明文可见，绑定拦不住知道 id 的冒用（待加令牌）；RSI 登记遇到他端已推进版本链要用新 parent 重登；脚本里 `\n` 经工具转写会变成真实换行，需用 chr(92) 写入。

**关键文件与接口**: - `scripts/sire_comms.py`：`bind/check`、`session start|wait|watch|stop|status|poll`、`resume`、`push`、`find_codex_exe`、`lock/unlock --stale`；环境变量 SIRE_COMMS_PUSH=0 关闭推送、SIRE_CODEX_EXE、SIRE_COMMS_LOCK_TTL_HOURS。
- `scripts/test_sire_comms.py`：22 个用例（c10–c22 覆盖绑定、锁过期、自动绑定、start 切换、resume、stop 同步、推送、watch、会话让位）。
- RSI：comms-bind v6.28、persist 6.29、wait 6.30、lock-bind 6.31、follow2 6.32、resume 6.33、protocol 6.34、push 6.35。

**状态**: 已完成

### F-087: 用户手册外部版隐藏与测试 tag 序号
**日期**: 2026-10-21
**项目**: EncoderPlotter_0903_01
**关键词**: EncoderPlotter, 用户手册, 外部版, isInternal, 内部版, test tag, test-v4.10.0

**需求场景 / 现象**: 外部版需要隐藏用户手册入口，同时同步手册内容；提交时需依据当前版本及已有测试 tag 提供下一个规范 tag 名称。

**方案 / 实施步骤**:
1. 检查当前分支与 upstream，确认 feature/iap-ota-sn → origin/feature/iap-ota-sn。
2. 更新设置入口和手册，补充 changelog。
3. 提交并推送后，建议测试 tag test-v4.10.0-92-外部版隐藏手册入口；不自动打 tag。
方案 / 架构：设置页手册链接使用现有统一 isInternal 标志，只在内部版渲染。手册内容记录当前实现，并明确代码没有统一逐系列固件版本矩阵。测试 tag 用 test-vX.Y.Z-NN[-描述]；版本取 package.json，NN 在同版本已有最大序号上递增。本次未创建 tag，仅提供建议。

**验证方法**: node 静态加载检查手册 9 个章节、68 个唯一条目及 related 链接；git diff --check；提交后 HEAD 与 upstream 均为 54c3ec21，工作区干净。

**踩坑 / 已知异常与失败经验**: 踩坑：PowerShell 把未引号的 @{upstream} 解释为哈希表表达式；应给 ref 加引号或直接使用已确认的 upstream ref。

**关键文件与接口**: - components/analyzer/version.html — 设置页入口绑定 v-if="isInternal"。
- components/manual/manualData.js — 手册功能及错误参考内容。
- CHANGELOG.md — Unreleased 用户可见变更。
- package.json — 当前版本 4.10.0。

**状态**: 已完成

### F-088: driverSoftware 0.8至0.20.2提测范围与客户档边界
**日期**: 2026-10-22
**项目**: driverSoftware
**关键词**: driverSoftware, 提测, L0, 客户包, 0.20.2, 版本变动, 量零点, 档位

**需求场景 / 现象**: 汇总v0.8.0至v0.20.2全功能变化并按默认客户档独立提测。目标标签08c44705，含起止版本。

**方案 / 实施步骤**:
方案：用目标标签CHANGELOG逐版覆盖，代码权限表划范围，提交补漏，独立审查去重与最终规则。默认L0运行；客户包有L0/L1硬上限；L1增量轨迹/附加寄存器/内部故障位/手选档案；多机组控、陪测加载、标定、下线检测L2；寄存器/自动测试/诊断/测试波形L3。客户包删除量零点脚本，按钮应按runnable禁用；正式包默认L0可能可运行，不可混淆。

**验证方法**: 31个发布说明段全覆盖。0.12.0虽有本地标签，但dd23150f记录无产物并入0.12.1。陪测加载历史重复应归8c6718dd后0.19.0；AES可选被0.15强制加密替代；DYN瞬时去皮取消；下线不合格可继续但保留不合格。文档已独立审查并修正量零点SKU口径，32条客户用例均待测试，未声称软件真机验收。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: CHANGELOG.md、frontend/js/capabilities.js、frontend/js/scope-bar.js、scripts/build.bat、scripts/build_mac.sh。全功能及默认客户版清单存本次固定运行目录。

**状态**: 已完成

### F-089: 飞书客户提测文档创建与32项回读核验
**日期**: 2026-10-22
**项目**: driverSoftware
**关键词**: 飞书, 提测文档, driverSoftware, lark-cli, bot, 32项, Markdown, 客户版

**需求场景 / 现象**: 用户要求将已确认的32项默认客户版白话提测内容写入飞书，标题“舵机上位机客户版提测内容”，不发送群消息。

**方案 / 实施步骤**:
方案：使用已有飞书CLI配置。PATH中没有lark-cli，npm官方包@larksuite/cli可通过npx运行并复用已有凭据。user刷新凭据过期，bot身份可通过docs +create创建，返回permission_grant=granted，为当前CLI绑定用户授予full_access；不改公开共享。使用已确认的Markdown内容导入，生成32项操作、预期、注意和结果记录。下划线占位会被Markdown吞为样式，改成中文“（待填写）”后重写本次新文档。

**验证方法**: docs +fetch以bot回读成功，revision=11；01至32连续，32个操作说明、预期、注意及待测试记录全部匹配。独立子代理复核通过。文档创建及存储回读已验证；没有执行软件或真机测试，也未声称完成浏览器视觉验收。用户身份授权过期不影响本次bot创建与CLI自动授予绑定账号权限。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: 飞书文档 https://kingkong.feishu.cn/docx/HfeldewxTonZPuxHgbrcdATYnme；本次运行目录保留正文与完整回读JSON。

**状态**: 已完成

### F-090: MES 当前界面易用性审查：待办、导航与低代码配置缺口
**日期**: 2026-10-23
**项目**: MES / D:\code\mes
**关键词**: MES 易用性, 待办直达, 人员指派待办, 移动端导航, 明细行设计器, 低代码用户体验, 操作手册过期

**需求场景 / 现象**: 对当前 MES 工作区的业务端和管理端做静态易用性审查。发现待办卡片仅跳转到模块而不定位记录；待办未按节点指派执行人过滤；业务端窄屏菜单退化为横向滚动栏；明细行运行时能力无可视化配置入口；老手册正文仍保留生产执行旧入口；列表操作隐藏在行尾菜单，明细行在窄屏横向滚动。

**方案 / 实施步骤**:
方案要点：
本轮只读审查，不改代码。按影响建议先处理待办记录直达和执行人匹配，再优化移动导航、补齐明细行设计器，并更新当前操作手册。

实施步骤：
1. 静态读取当前组件、设计契约、操作手册和最新进度条目。
2. 对照源代码确认每条交互路径，区分已知实现缺口与需浏览器验证的推断。

**验证方法**: 只读代码/文档核对。未启动服务或浏览器、未运行测试/构建；需用户授权后通过岗位用户和窄屏真实路径验收。

**踩坑 / 已知异常与失败经验**: UI 交互路径与最新能力配置不同步：TodoPage 只构造模块路由；组织指派能力没有同步到工作台查询；BusinessLayout 的 mobile class 直接采用横向 flex；detailLines 配置只在 schema/runtime 支持，没有设计器编辑器；手册保留历史章节。
老手册第一页有过期声明，但长正文和 PDF 仍保留旧流程内容；单看声明或文件标题会误以为它可作当前新手指南。

**关键文件与接口**: - `packages/runtime/src/lowcode/pages/TodoPage.tsx:23-26` — 待办卡片目标只到 `/app/<moduleCode>`。
- `packages/runtime/src/components/layout/BusinessLayout.tsx:27-33` — 窄屏导航横向滚动。
- `packages/runtime/src/lowcode/components/DetailLines.tsx:45-84` — 明细行由运行时 schema 驱动；窄屏表格横向滚动在 92-123 行。
- `docs/PROGRESS.md:466-480` — 设计器缺明细行配置；待办仍按角色统计而非指派人。
- `docs/manual/MES系统完整操作手册-白话文版.md:3` — 手册标注旧流程过期，但正文仍保留旧入口。

**状态**: 已完成

### F-091: MES交接续做组成能力与SN入口清理
**日期**: 原记录未记载
**项目**: 原记录未记载
**关键词**: MES, composition, 分母, 生效时间, SN, 平台边界

**需求场景 / 现象**: 用户要求继续执行Claude交接，推进明确授权的代码文档项，等待新流程且不测试。

**方案 / 实施步骤**:
方案要点：
C1/C3代码已实现：分母/有效区间/同字段递归、共享类型与依赖保护、dependencies.test字面量类型。COMP-UNIT-001至005、007、008及依赖字段断言已编写未执行。
B部分：删除旧SN前端文件与双端路由、BUSINESS_NAV、通用追溯snHits/SnService耦合；exec/runHits及SN后端/权限/迁移因A依赖保留，B未整体完成。
F：新增现行口径，修订20份历史设计/手册/任务记录，PDF/Word等历史导出未重生成。
静态复核：独立review代理R4/R6无Blocker/Major，兼容用例建议已补；主控另行读取差异。没有执行测试/构建/类型运行检查/服务/浏览器/部署/库写入/提交。

**验证方法**: 未执行建议命令：npm test -w mes-server；npm run test:integration -w mes-server；npm run build。真实浏览器验收旧SN页面不可用、通用追溯权限边界、设计器新配置正常与非法分母/日期边界均待用户授权。

**踩坑 / 已知异常与失败经验**: 环境风险：TESTING.md要求唯一测试业务库，交接称本机业务库；本次未选择数据源、未导入、未改运行配置。
后续依赖：A/E用户新流程；C2序号起点口径；C4随执行改造合成集成测试；D等待导入指示；G测试授权及部署条件；bom_entry能力配置尚未写入运行系统。
SIRE台账实际登记晚于部分实现（流程偏差保留），未伪造阶段执行时间。工具要求三路初审与交叉核验，本轮实际独立复核一路，未伪造其余复核，单元延后收敛；实现结果不等于功能验收通过。

**关键文件与接口**: npm test -w mes-server；npm run test:integration -w mes-server；npm run build（均为未执行的建议命令）；TESTING.md

**状态**: 部分完成

### F-092: GAME对照FC初代重装机兵的差距与制作优先级
**日期**: 2026-10-24
**项目**: GAME
**关键词**: FC, 重装机兵, 战车RPG, 复刻, 多车, 游戏审计, 音频, UI, 盐海遗讯

**需求场景 / 现象**: 用户要求分析现有 Unity 游戏如何完美复刻重装机兵，已确认 FC 初代。

**方案 / 实施步骤**:
方案要点：
分开定义忠实 FC 复刻、FC 内容的3D重制与原创精神续作。先锁具体版本，再用地图/状态/输入/期望/差异/证据对照表驱动制作；先做首车获得、伙伴和多车、城镇与危险路线的完整样片。复用现有逻辑分层，不以原型数量作为完成度。

**验证方法**: 2026-10-24 静态盘点2角色、19部件、17敌人含4赏金首、3城镇、3主线13步、3段对话10行、7逻辑场景；9FBX、9外观prefab、2Animator、17PNG，无发现音频文件或音频代码接线。独立子代理复核素材和机制；第三幕缺失DLG_Act3_Choice、CanMove未接野外移动、ActionsPerTurn未被指令队列消费。没有运行游戏或测试。

**踩坑 / 已知异常与失败经验**: 旧GDD已落后；原创三幕3D方向与FC忠实目标冲突；原作内容使用和发布须核实授权；未进行原版全量行为测量，不报相似度百分比或确定工期。
数据为本次静态快照，不等于功能验收；后作犬伙伴和职业系统不自动纳入FC基线。分析产物 D:/sire/sire_ledger/runs/R20261024-103607-game/analysis-report.md。

**关键文件与接口**: 原记录未记载

**状态**: 已完成

### F-093: GAME 复古俯视 3D UI 主题与视口锚点实现
**日期**: 2026-10-25
**项目**: GAME / D:\code\GAME
**关键词**: Unity UI, UGUI, IMGUI, CanvasScaler, 视口锚点, 暖木, 锈钢, 黄铜, 复古俯视 3D, 重装机兵

**需求场景 / 现象**: FC 初代 3D 重制项目需要将标题、野外 HUD、主菜单/地图、剧情对话和战斗界面统一为用户给定的暖木室内、锈钢包边、暖光与像素角色叠加的复古风格，同时保留现有菜单业务和 StoryService/BattleSystem 输入流程。

**方案 / 实施步骤**:
方案要点：
沿用现有 UGUI 野外/菜单层和 IMGUI 战斗/逻辑对话层，只改表现层色板、边框、选择态与布局，不引入游戏状态。使用木棕面板、暖纸字色、黄铜线和暖色块状高亮；主菜单/地图框使用 Canvas 视口百分比锚点，CanvasScaler 宽高折中；标题点击区域使用实际可见底板边界。实机测试必须另获用户授权。

实施步骤：
1. 先检查现有野外/菜单/地图/对话/战斗覆盖，沿用已有路由和服务。
2. 将战斗及对话呈现映射到暖木与黄铜主题，保留现有输入语义。
3. 将野外/主菜单/地图/标题调色板统一，菜单和地图外框改为视口锚点。
4. 把标题行鼠标热区缩到实际底板，修正超宽窗口固定框高裁切设计。
5. 用户授权前只做静态代码复核；不运行测试、构建或 Unity。

**验证方法**: 静态复核通过；真实 T01–T05 未执行，需用户授权后按菜单/地图/剧情/战斗正常流程与 4:3、16:9、21:9 边界路径验收。不得将静态复核表述为运行通过。

**踩坑 / 已知异常与失败经验**: 不适用；这是主题统一与信息层级完善，不是缺陷根因记录。
标题菜单文字 Rect 比可见底板宽，会使鼠标热区重叠；应使用行底板 Rect 做命中。固定像素宽高的菜单/地图框在 CanvasScaler 只匹配宽度的超宽屏下会超出屏高；外框宜用视口 anchors，留住内部参考单位边距。另需注意保持分辨率设置是独立启动行为，不应混入视觉配色改动。

**关键文件与接口**: - `UNITY/Assets/Scripts/Presentation/FieldUiPresentation.cs` — 全局 UI 色板、标题/菜单/地图面板、视口锚点与 CanvasScaler。
- `UNITY/Assets/Scripts/Presentation/Menu/FieldCommandMenu.cs` — 菜单视口和命令选中/未选中底色；业务 Action 回调保持原样。
- `UNITY/Assets/Scripts/FC/FcTitleScreen.cs` — 钢框/木色内衬、记录行底板与点击热区。
- `UNITY/Assets/Scripts/FC/FcDialogue.cs`、`UNITY/Assets/Scripts/Field/DialogueDebugUI.cs` — Canvas/IMGUI 对话选项底板与输入反馈。
- `UNITY/Assets/Scripts/Battle/BattleController.cs` — 战斗状态/日志/命令分区、敌群换行、队伍滚动和主题样式。

**状态**: 部分完成

### F-094: GAME Unity UGUI 程序化旧钢与暖木平铺材质
**日期**: 2026-10-25
**项目**: GAME / D:\\code\\GAME
**关键词**: Unity UGUI, Image.Type.Tiled, TextureWrapMode.Repeat, 程序化木纹, 锈钢 UI, Sprite.Create, 跨程序集可见性

**需求场景 / 现象**: 将 FC 初代重制的 Unity UI 贴近用户选定的 3D 室内参考图：暖木板、旧化锈钢、黄铜强调。原 UI 已有配色但主面板大多是纯色。

**方案 / 实施步骤**:
1. 在程序代码里生成 128²可平铺钢板/木纹纹理并缓存 Sprite。
2. 将纹理只接入 UI Image 绘制层，选中态保留高对比暖黄铜底色。
3. 静态审查 Unity UGUI API、程序集引用、纹理周期和原输入回调；等待用户授权后再做运行验收。
方案 / 架构：使用公共静态 `WornUiSurface` 生成并缓存各一张 128×128 RGBA 钢板与木板 Sprite，TextureWrapMode.Repeat，UGUI Image.Type.Tiled + SpriteMeshType.FullRect 平铺。用周期正弦纹理函数让 tile 首尾接缝一致；钢板只用于主要外框，木纹用于内衬/命令行，保留暖纸字色和黄铜选中 tint。辅助器需 `public`，因为 `Game.FC` 的独立 asmdef 调用 `Game.Presentation`。

**验证方法**: 三路独立静态审查及交叉复核通过；审查中发现的 `internal` 跨 asmdef 可见性风险改为 `public`，随后复核通过。未运行 Unity、构建、自动化测试或实机验收；实际显示观感仍待授权。

**踩坑 / 已知异常与失败经验**: 根因：（问题类必填）: 旧实现仅表达颜色，没有木/钢材质细节；UGUI 外框、选项底板本身均为运行时 Image。
踩坑：`Game.Presentation` 中的 `internal` helper 不能被独立 asmdef `Game.FC` 的标题界面访问；跨程序集共享绘制工具需使用公开 API。UGUI tiled sprite 必须使用 Repeat 纹理及完整矩形 Sprite；无缝周期函数和 tile 边缘板缝减少接缝跳变。
【原状态说明】部分完成（材质绘制已静态复核；运行观感未测试）

**关键文件与接口**: - `UNITY/Assets/Scripts/Presentation/WornUiSurface.cs` — 公共静态材质生成/缓存辅助器，`ApplySteel` / `ApplyWood`。
- `UNITY/Assets/Scripts/Presentation/FieldUiPresentation.cs` — 野外 HUD、交互提示、菜单/地图框和按钮。
- `UNITY/Assets/Scripts/Presentation/Menu/FieldCommandMenu.cs` — 内容视口与命令行。
- `UNITY/Assets/Scripts/FC/FcTitleScreen.cs` — 钢框、木内衬与记录选项。
- `docs/FC_REMAKE.md` — 描述材质风格和验收边界。

**状态**: 部分完成

### F-095: Additive 美术场景中的室内样片与安全传送接入
**日期**: 2026-10-25
**项目**: D:/code/GAME（Unity FC 重制）
**关键词**: Unity additive scene, SceneManager.sceneLoaded, RuntimeInitializeOnLoadMethod, FieldGroundSurface, Terrain.SampleHeight, ScenePortal, SpawnPoint, TownGate, room interior, cutaway room

**需求场景 / 现象**: 在既有逻辑世界与 additive 美术场景中，为同一逻辑地图新增可进出的室内样片；不重建或覆盖已有的未提交美术场景。

**方案 / 实施步骤**:
方案要点：
在 Presentation 层通过 `BeforeSceneLoad` 注册 `SceneManager.sceneLoaded`，只处理目标 `_Art` 场景；检查唯一 root 并将程序生成物迁入 art scene，使其随该场景卸载。室内保持在逻辑场景同一地图，通过双向 `ScenePortal` 和 `SpawnPoint` 传送。additive art scene 装入后从同场景 `Terrain` 取样，统一对齐室内地板、门触发器、出生点和安全区；`FieldGroundSurface` 提供稳定寻地标记。房间边界需与 TownGate、EncounterZone、道路和洞窟入口逐项计算，使用单一公开常量供逻辑层和相机复用。

实施步骤：
1. 先检查 `ArtSceneLoader`、玩家寻地、portal/spawn 和遭遇区逻辑，确定不覆盖用户本地场景。
2. 在 art scene 生命周期钩子中构建唯一、可随场景卸载的运行时视觉 root。
3. 在逻辑场景配置双向传送、出生点、安全区和交互，保证入口目标与另一侧 spawn id 对应。
4. 使门触发区避开出生点；前墙切面为出口留足碰撞门洞。
5. 以独立静态审查核对组件依赖、坐标范围和地形高度。

**验证方法**: 静态核对 SceneManager event 注册/去重、additive root scene 归属、room 与 encounter/town 边界、每个 portal 的 target spawn、地面标记和 Rest 调用。功能验收应在用户授权后运行 Unity：正常进入/住宿/离开、金币不足、满 HP 三条路径。本轮未获授权，未运行 Unity、构建或测试。

**踩坑 / 已知异常与失败经验**: 无单一根因。既有 `ArtSceneLoader` 异步叠加美术场景，而玩家生成点/门/城镇安全区属于逻辑场景，需要协调两个场景的加载时序与高度。
若将已带 `surfaceOffset` 的世界坐标传入会自动叠加同一偏移的 Box helper，窗框会在非零地形高度下产生双倍 Y 偏移；调用前应先还原基准坐标，或将 helper 改成接收明确的 world/local 坐标。不同空间必须避免再次应用偏移。

**关键文件与接口**: - `UNITY/Assets/Scripts/Presentation/FC/FcRadoInnArtBuilder.cs` — art-scene lifecycle hook、程序化地板/锈钢墙板/家具/灯光及高度对齐。
- `UNITY/Assets/Scripts/FC/FcWorldBuilder.cs` — portal、spawn、TownGate、`TownService.Rest` 与室内相机范围。
- `UNITY/Assets/Scripts/Core/ArtSceneLoader.cs` — additive art-scene 生命周期与 `TerrainReady`。
- `UNITY/Assets/Scripts/Field/FieldPlayerController.cs` — `Teleport` 通过 `FieldGroundSurface` 寻地，art scene 加载后再次 SnapToGround。
```csharp
[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
private static void Register()
{
    SceneManager.sceneLoaded -= OnSceneLoaded;
    SceneManager.sceneLoaded += OnSceneLoaded;
}

private static void OnSceneLoaded(Scene scene, LoadSceneMode mode)
{
    if (scene.name != ArtSceneName) return;
    foreach (var root in scene.GetRootGameObjects())
        if (root.name == RootName) return;
    var host = new GameObject(RootName);
    SceneManager.MoveGameObjectToScene(host, scene);
    host.AddComponent<FcRadoInnArtBuilder>().Build();
}
```

**状态**: 部分完成

### F-096: Unity UI跨UGUI/IMGUI共享旧钢与暖木材质
**日期**: 2026-10-25
**项目**: GAME Unity FC 重制
**关键词**: Unity UI, shared Texture2D, UGUI Tiled, IMGUI DrawTextureWithTexCoords, GUIStyle background scaling, ScrollRect, GUI scroll view

**需求场景 / 现象**: 用户要求将战斗、剧情和原型界面统一成参考图的旧钢、暖木、黄铜与暖纸色主题，并保持不同程序集共用材质且不改变输入行为。

**方案 / 实施步骤**:
方案要点：
在 Game.Runtime 内集中生成懒缓存的 Texture2D，避免依赖 Presentation/FC。Game.Presentation 只创建 Sprite wrapper 并为 UGUI Image 设置 Tiled；IMGUI 的 GUIStyle 背景不会因为 TextureWrapMode.Repeat 而自动平铺，面板应通过 GUI.DrawTextureWithTexCoords 以明确 UV 重复，短按钮使用共享 1×1 木色状态纹理。共享 HideAndDontSave 资源需在新播放会话重置时销毁并清空静态引用，不能由场景组件各自销毁。长选项列表需同步滚动位置与当前选择；键盘/鼠标路径都应保证当前焦点可见。

**验证方法**: 静态核对 asmdef 依赖方向、共享缓存/释放、UGUI/IMGUI绘制路径、选择焦点同步，三路独立 R6 与交叉复核通过。未运行 Unity、构建或功能测试；实际纹理观感、多分辨率和滚轮行为仍待用户授权测试。

**踩坑 / 已知异常与失败经验**: GUIStyleState.background 直接赋 128×128 Repeat 纹理仍会按面板矩形缩放；要显式UV平铺。纯键盘实现加上 scroll view 不够，键盘移动后需把焦点滚入视口；滚轮变化也必须更新当前选项，否则 Enter 可能确认不可见项。鼠标滚轮和点击同帧时应先刷新焦点再处理点击。

**关键文件与接口**: - `UNITY/Assets/Scripts/UI/RetroUiTextures.cs` — Game.Runtime共享材质源、缓存重置、IMGUI显式平铺。
- `UNITY/Assets/Scripts/Presentation/WornUiSurface.cs` — 同源 Sprite wrapper 与 UGUI Image.Type.Tiled。
- `UNITY/Assets/Scripts/FC/FcDialogue.cs` — StoryService对话窗口与滚轮/键盘焦点可见性。
- `UNITY/Assets/Scripts/Field/DialogueDebugUI.cs` — 原型对话滚动和活动选择同步。
- `UNITY/Assets/Scripts/Battle/BattleController.cs`、`FieldHUD.cs`、`TownDebugMenu.cs` — 共用钢面板与木色状态。

**状态**: 部分完成

### F-097: FC 重制室内切面美术基线与车辆版本锚点
**日期**: 2026-10-25
**项目**: GAME Unity FC 重制
**关键词**: Unity art bible, isometric cutaway room, pixel sprites, weathered steel, warm wood, FC vehicle slots, Mount_Sub, interior art direction, 俯视切面, 室内美术基线

**需求场景 / 现象**: 用户为 Unity FC 初代重制提供室内游戏截图，要求采用相同风格；项目同时残留了旧原创车辆概念和临时 UI/室内样片方向，需要把用户选择转成可复用美术合同，而不误改全局荒野/战车基线。

**方案 / 实施步骤**:
方案要点：
在 ART_BIBLE 明确室内采用高位斜俯视无顶切面3D房间、暖木板/锈钢板、暗色框架、少量黄铜和暖灯窗光；玩家/队友/NPC 使用清晰像素角色并接 3D 地面阴影；UI 使用旧钢框、暖木内容区、黄铜焦点和暖纸色文字。明确室内/室外风格边界与原创性。车辆设计锚定 FC_REFERENCE 和游戏部件/挂点数据，区分初始无副炮装备与 Mount_Sub 模型接口，旧原创方案退出 FC 制作范围。

实施步骤：
1. 先搜索共享 UI/室内美术知识和现有 FC 内容对照。
2. 将截图特征拆成镜头、墙/地/家具、角色、光照、UI、适用范围与原创性规则。
3. 对照 FC 首车代码和资料，淘汰 ART_BIBLE 中冲突的旧原创战车设定。
4. 用静态阅读与三路独立复核确保规范与现有样片一致，并注明实机风格效果未测试。

**验证方法**: `git diff --check -- docs/ART_BIBLE.md` 无空白错误；R6A/B/C 和三路交叉核验全 PASS，逐项检查 AC1–AC10。未运行 Unity、构建、截图或测试；像素人物/室内画面的运行效果仍待用户授权实测。

**踩坑 / 已知异常与失败经验**: 既有 ART_BIBLE 是更早的通用废土提案，缺少 3D 室内与像素人物混合规范，并把 75mm/7.7mm 六轮原创车概念留作首个车辆模型提案，与当前 FC 首车内容冲突。
“取得时无副炮”是装备状态，不能写成底盘没有副炮挂点；当前 `Mount_Sub` 接口不证明 FC 原版是否有相同行为，需分开标注。前墙被切开还需明确留下连到室外且角色可步行通过的门洞，否则“有切面构图”不保证可玩路线。

**关键文件与接口**: - `docs/ART_BIBLE.md` — 项目视觉方向、室内色板、FC车辆参考锚点、Blender/Unity模型合同。
- `docs/FC_REFERENCE.md` — 当前首车及装备参照，并标记待 FC 原版核对的事实。
- `UNITY/Assets/Scripts/FC/FcCampaignBootstrap.cs` — `CreateFirstTank()` 当前实现的蚊式装备状态。
- `UNITY/Assets/Scripts/Presentation/Editor/FcLightTankModelBuilder.cs` — 当前模型生成器定义的 `Mount_Main`/`Mount_Sub`。
- `UNITY/Assets/Scripts/UI/RetroUiTextures.cs`, `UNITY/Assets/Scripts/Presentation/WornUiSurface.cs` — 现有旧钢/暖木 UI 纹理实现。

**状态**: 部分完成

### F-098: FC重制用户参考图风格扩展到整套UI
**日期**: 2026-10-25
**项目**: GAME / Unity FC 重制
**关键词**: Unity UI 风格、暖木旧钢、黄铜焦点、像素人物、参考图、标题 HUD 菜单 地图 对话 战斗, 风格复确认, 用户参考图, UGUI, IMGUI, FC 重制, 暖纸色

**需求场景 / 现象**: 用户在确认故事主题之后进入 UI 阶段，并以暖木地板、旧钢墙板、暖灯和像素人物的室内切面游戏截图明确 UI 风格。参考图确立材质与构图气质，不要求复制房间布局或角色造型。
用户在推进 FC 重制 UI 阶段时再次提供与既有参考相同的 2.5D 室内图，并要求采用该风格。产品源码已有标题、HUD、菜单、地图、对话和战斗的共享主题实现。

**方案 / 实施步骤**:
方案要点：
将视觉职责写入 `docs/ART_BIBLE.md`：标题、野外 HUD、菜单、地图、剧情对话、战斗均沿用旧钢框体/信息面板、暖木交互与对话面、暖纸文字和少量黄铜焦点。区域按信息层级调节钢木比例；文本使用低纹理底板，选中状态用颜色和指示符共同表达，禁用状态仍可读。现有 Unity UI 通过共享 `RetroUiTextures` 和 UGUI `WornUiSurface` 提供暖木/旧钢主题；本轮只明确视觉合同，不更改玩法或输入代码。
先核对美术基线和所有目标 UI 表现，再决定是否修改。将参考图转译为低多边形场景/像素角色的整体气质、旧钢主框、暖木交互区、暖纸文字和少量黄铜焦点；不复制参考图房间布局和素材。若共享纹理和各屏幕已经覆盖，不再重复增加一套主题。真实显示仍应在用户授权后验证。

实施步骤：
1. 搜索已有设计决定和纹理复用记录。
2. 静态核对标题、HUD、菜单、地图、对话、战斗与城镇原型的主题覆盖。
3. 覆盖已有时只确认不重复改写；记录 UI 真实运行验收待授权。

**验证方法**: 独立静态复核确认标题、野外 HUD/菜单/地图、对话和战斗实现与材料职责相符。未运行 Unity、构建或功能测试；材质对比、文字可读和分辨率表现仍需用户授权后实机验收。
源码静态核对各界面的 `ApplySteel`/`ApplyWood`/`RetroUiTextures` 使用；本轮未打开 Unity、未运行构建和功能测试。后续获授权后检查正常操作与边界分辨率。

**踩坑 / 已知异常与失败经验**: 不适用；本次是设计确认，不是缺陷。
用户重复给出已有风格参考不一定需要新材质或重复样式系统；先比对现有 UI 实现，避免范围外重复改造。
复核现有设计文档和代码已覆盖；未改项目文件。Unity 实机显示与可读性未测试，待用户授权。

**关键文件与接口**: - `docs/ART_BIBLE.md` — UI映射和用户确认的风格范围。
- `UNITY/Assets/Scripts/UI/RetroUiTextures.cs` — UGUI/IMGUI共享钢木材质。
- `UNITY/Assets/Scripts/Presentation/FieldUiPresentation.cs`、`FC/FcTitleScreen.cs`、`FC/FcDialogue.cs`、`Battle/BattleController.cs` — 当前主题使用处。
- `docs/ART_BIBLE.md` — 参考图的风格范围及 UI 材质映射。
- `UNITY/Assets/Scripts/UI/RetroUiTextures.cs`、`UNITY/Assets/Scripts/Presentation/WornUiSurface.cs` — UGUI/IMGUI 共用钢木纹理。
- `UNITY/Assets/Scripts/Presentation/FieldUiPresentation.cs`、`UNITY/Assets/Scripts/FC/FcTitleScreen.cs`、`UNITY/Assets/Scripts/FC/FcDialogue.cs`、`UNITY/Assets/Scripts/Battle/BattleController.cs` — 目标 UI 主题使用处。

**状态**: 部分完成；并入的偏好 H-008（FC 重制 UI 沿用用户确认的室内参考风格）仍然生效

### F-099: 标题页保留用户显示模式
**日期**: 2026-10-26
**项目**: GAME / D:\code\GAME
**关键词**: Unity UI, 标题界面, 分辨率, Screen.SetResolution, 显示模式, CanvasScaler, FC重制

**需求场景 / 现象**: FC重制标题界面在Start中强制调用1600×900窗口模式，启动游戏会覆盖玩家在操作系统或启动器选择的显示设置；该行为与固定1360×765参考分辨率的CanvasScaler职责无关。

**方案 / 实施步骤**:
方案要点：
删除标题启动中的固定Screen.SetResolution调用，把显示模式控制权留给Unity Player Settings、系统和启动器；继续使用CanvasScaler的ScaleWithScreenSize及项目标题布局，不改变菜单选择、输入和存档流程。若未来提供分辨率选项，应通过明确的设置UI实现，不藏在标题界面的启动副作用中。

**验证方法**: 当前源码静态核对无Screen.SetResolution，CanvasScaler与标题交互/存档入口保留；独立R6A/B/C和交叉核验全PASS。未运行Unity、构建、功能测试或GUI；实际全屏/窗口及4:3/21:9呈现待用户授权测试。源文件为Git未跟踪状态，缺少HEAD diff历史依据。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: `UNITY/Assets/Scripts/FC/FcTitleScreen.cs` 的 `Start()`、CanvasScaler初始化、菜单刷新与输入处理。

**状态**: 部分完成

### F-100: FC 45毫米炮独立运行时模型原型与挂装路径
**日期**: 2026-10-26
**项目**: GAME / D:\code\GAME
**关键词**: FC重装机兵, 45毫米炮, VisualCatalog, 运行时模型工厂, Unity挂点, Mesh缓存, URP fallback

**需求场景 / 现象**: FC首车蚊式与波布Buggy当前使用同一45毫米炮数据，但初始模型临时复用了75毫米炮。必须使45毫米炮外观独立可替换，并在车辆与战斗表现路径一致装配。

**方案 / 实施步骤**:
方案要点：
通过 `Fc45mmCannonModelFactory` 运行时生成暖旧钢/橄榄色低多边形炮尾、炮盾、短炮管、炮口与瞄具原型。为 `WPN_FC_Cannon45` 与 `WPN_FC_BuggyCannon` 注册独立工厂，避免已有75毫米模型alias优先命中。车辆外观及战斗表现路径统一经 `VisualCatalog.InstantiateModel` 在现有武器挂点生成；Cylinder/Frustum 网格和按色材质以固定键静态缓存，材质优先使用Resources中的 `Combat/CombatFallback`，避免反复换装增长Mesh对象或只依赖可能被裁剪的字符串Shader查询。保留 `WPN_FC_Cannon7mm` 到75毫米外观的既有临时映射和玩法数据。

**验证方法**: 静态检查注册、挂点、+Z枪口朝向、共享Mesh缓存、Resources fallback、数据快照、代码范围及三路独立复核/交叉核验均PASS；`git diff --check`未发现空白错误。没有运行Unity、构建、游戏或测试；外观比例、材质和镜头识别度待授权实机核验。FC原版尺寸与细节没有实机依据，源资产Blender/FBX/预览仍未交付；FC bootstrap在任务开始前已是Git未跟踪文件，因此以预编辑读取快照比对数据，不能宣称有完整HEAD diff证明。

**踩坑 / 已知异常与失败经验**: `VisualCatalog.InstantiateModel`会先尝试资源Prefab并按alias解析，然后才走工厂；因此必须移除目标ID的旧alias才能触发工厂。既有 `TankVisual` 和 `CombatPresentationBootstrap` 武器路径调用 `Model()`直接拿Prefab，工厂不会触发，需改成 `InstantiateModel(..., mount, false)`。

**关键文件与接口**: - `UNITY/Assets/Scripts/Presentation/FC/Fc45mmCannonModelFactory.cs` — 运行时低模原型与有限Mesh/材质缓存。
- `UNITY/Assets/Scripts/FC/FcCampaignBootstrap.cs` — 两个FC45毫米ID注册工厂。
- `UNITY/Assets/Scripts/Presentation/Tank/TankVisual.cs` 与 `UNITY/Assets/Scripts/Presentation/Combat/CombatPresentationBootstrap.cs` — 野外/车库及战斗挂装入口。
- `docs/ART_BIBLE.md`、`docs/FC_REFERENCE.md` — 原型状态和未完成的正式美术交付边界。

**状态**: 部分完成

### F-102: Unity同名Cue同步的原创SFX WAV资源生成
**日期**: 2026-10-26
**项目**: GAME / D:\code\GAME
**关键词**: Unity SFX, SfxCue, procedural sound effects, PCM WAV, AudioImporter meta, Resources Audio/Sfx, deterministic generator

**需求场景 / 现象**: AudioDirector包含19个SfxCue事件和运行时ChipAudioSynth占位，但Resources/Audio/Sfx缺少正式素材；需要原创短音效，同时不改变已接入的事件路由。

**方案 / 实施步骤**:
方案要点：
使用Python标准库按每个Cue独立设计起落包络、音高扫频、瞬态噪声、低频层或短音符动机，生成单声道16-bit PCM WAV。输出名与Cue一致并放入`Resources/Audio/Sfx/<Cue>.wav`，直接满足AudioDirector现有Resources加载路径。生成器读取AudioDirector的SfxCue枚举并验证设计配置集合一致，减少新增Cue时漏掉素材；固定Cue种子确保重生成可复现。AudioImporter `.meta` GUID按Unity Assets相对路径稳定派生，并保留已有有效GUID。素材原创，不使用商业游戏旋律、录音或采样。

实施步骤：
1. 从AudioDirector列出SfxCue和事件用途。
2. 为菜单、机械上下车、战斗冲击、资源/进度事件设计独立音色分支。
3. 使用固定种子生成WAV，并从Assets相对路径产生meta GUID。
4. 静态核对Cue覆盖、WAV头和GUID；保留Unity实机导入与听感验收待授权。

**验证方法**: 对19个WAV直接检查RIFF/WAVE数据：22050Hz、单声道、16-bit PCM，时长0.065–0.820秒，峰值0.420–0.780；SFX meta GUID唯一且资源名与现有枚举加载合同一致；三路独立静态review及交叉核验PASS。没有打开Unity、播放声音、构建或运行功能测试，故不宣称主观听感/导入通过。

**踩坑 / 已知异常与失败经验**: 不适用；这是占位素材升级。
运行时可通过缺资源回退ChipAudioSynth，因此仅“能响”不能证明正式素材接入；必须让Resources子路径与Cue字符串完全匹配。Unity `.meta` GUID应从Assets内部相对路径导出，不能从仓库根包含Unity/Assets外层。Python的array本机字节序要确保RIFF PCM输出为小端。纯波形峰值上限无法代替试听时的主观响度和清晰度检查。

**关键文件与接口**: - `tools/generate_fc_inspired_sfx.py` — 19类音效的确定性PCM合成、SfxCue覆盖检查和稳定meta生成。
- `UNITY/Assets/Resources/Audio/Sfx/` — 与Cue同名WAV和Unity导入meta。
- `UNITY/Assets/Scripts/Presentation/Audio/AudioDirector.cs` — `Resources.Load<AudioClip>("Audio/Sfx/" + cue)`运行时路径。
- `docs/AUDIO.md` — 来源、资产状态与听审边界。

**状态**: 部分完成

### F-103: FC 45毫米炮模型资源Prefab交付
**日期**: 2026-10-26
**项目**: GAME / Unity FC 重制
**关键词**: WPN_FC_Cannon45, Unity Prefab, FBX, Blender, 45毫米炮, FC 重制, 资源导入

**需求场景 / 现象**: 为蚊式与Buggy共用的 FC 风格 45 毫米炮提供可复用 Unity 资源Prefab，避免正式模型仅存在于 Blender/FBX 与运行时临时原型。

**方案 / 实施步骤**:
方案要点：
复用既有 Blender 源文件、专属 FBX、预览、`Fc45mmCannonPrefabBuilder` 与 `VisualCatalog` 注册，不另建第二个运行时模型。Unity Editor 通过 `BuildFromCommandLine` 导入 FBX 并创建 `Assets/Resources/Visuals/WPN_FC_Cannon45.prefab`；Prefab 根使用单位变换并嵌套原 FBX 模型。保留 FC 原版精确尺寸未核实的说明。

**验证方法**: Unity Editor 6000.6.3f1 的定向资源生成日志报告 Prefab 已写入、bounds `(0.81, 0.64, 1.81)`、31 Renderers，并以返回码 0 退出。生成器在保存前检查炮口/炮尾标记、+Z朝向及bounds门槛。R6A/B/C静态审查与交叉核验 PASS。未运行Play Mode、游戏构建或功能测试。

**踩坑 / 已知异常与失败经验**: 实际挂点中的镜头比例、战斗外观、材质/光照与运行时加载仍需用户授权后实机验收；Prefab生成日志末尾有Curl error 42提示，但生成成功行和批处理正常退出均在同一日志中。FC原版尺寸及几何不作为已确认事实。

**关键文件与接口**: - `ArtSource/WPN_FC_Cannon45.blend`、`ArtSource/build_fc_45mm_cannon.py`、`ArtSource/Previews/WPN_FC_Cannon45.png`
- `UNITY/Assets/Models/WPN_FC_Cannon45.fbx` / `.meta`
- `UNITY/Assets/Resources/Visuals/WPN_FC_Cannon45.prefab` / `.meta`
- `UNITY/Assets/Scripts/Presentation/Editor/Fc45mmCannonPrefabBuilder.cs`
- `UNITY/Assets/Scripts/Presentation/Field/FieldPixelCharacterAtlas.cs`、`UNITY/Assets/Scripts/FC/FcDialogue.cs`（Unity资源生成前置编译问题修复）
- `docs/ART_BIBLE.md`、`docs/FC_REFERENCE.md`

**状态**: 部分完成

### F-104: FC重制巨蚁Blender/FBX/Unity资源交付
**日期**: 2026-10-26
**项目**: GAME / D:\code\GAME
**关键词**: **关键词**：FC重制、巨蚁、Blender源模型、FBX、Unity Prefab、资源ID、低多边形、轴向转换、GUID保留

**需求场景 / 现象**: 为Unity FC重制补齐一个普通敌人的独立建模源文件与可加载资源。`ENM_FC_GiantAnt` 已交付Blender工程、FBX、预览PNG、5种材质和Resources Prefab；原创低多边形模型包含头胸腹分节、复眼、触角、大颚与三对腿。最终Unity资源边界约 `(2.37, 1.31, 2.80)` 米，底部Y=0，前向约+Z，77个Renderer；原Prefab GUID保持 `20133215c96389e4e85d543b4b48d1f5`。

**方案 / 实施步骤**:
方案要点：
Blender源场景Z-up/-Y前向，FBX导出至Y-up/-Z格式；Unity资源生成器保留导入器轴转换节点，并在身份Prefab根下实例化模型。以头/腹坐标、FBX米制包围盒、6个股节节点和原Prefab GUID作为生成器约束；同一生成器按对象名分配外壳、装甲、边缘、深色关节、复眼五种材料。模型源在导出前把最低顶点归零。

**验证方法**: Blender与Unity Editor仅作为内容生成器写出源、FBX、预览和Prefab；静态生成日志记录bounds、+Z方向、Renderer/腿数、GUID和资源引用，三路独立R6及三路交叉核验PASS。未运行游戏、动画、碰撞或实机战斗/镜头测试；接地画面和运行时材质效果仍待用户授权后验收。不得把这个原创资产说成原版FC精确模型。

**踩坑 / 已知异常与失败经验**: 首次Unity生成时曾重置导入模型根旋转，导致Y/Z边界错误，修为保留导入器轴转换；复核发现最低顶点比原点高0.03米，随后在Blender源生成器归零并重生成Prefab。旧Prefab/meta副本保留在 `D:/sire/sire_ledger/runs/R20261026-043136-game/evidence/U-01/`。

**关键文件与接口**: `ArtSource/ENM_FC_GiantAnt.blend`、`UNITY/Assets/Models/FC/ENM_FC_GiantAnt.fbx`、`ArtSource/Previews/ENM_FC_GiantAnt.png`、`UNITY/Assets/Resources/Visuals/ENM_FC_GiantAnt.prefab`。`CombatPresentationBootstrap` 按 `Resources.Load("Visuals/{敌人ID}")` 查敌人prefab；VisualCatalog采用相同路径约定，但当前战斗路径没有直接调用VisualCatalog。

**状态**: 部分完成

### F-105: FC重制UI钢板铆钉跨UGUI与IMGUI统一
**日期**: 2026-10-26
**项目**: D:\code\GAME
**关键词**: FC重制, Unity UI, 旧钢, 暖木, 铆钉, UGUI, IMGUI, BattleController

**需求场景 / 现象**: 用户确认室内切面参考图作为UI风格方向。已有UGUI/IMGUI界面使用旧钢与暖木主题，但图中钢结构的铆接细节尚未映射到正式框体，战斗IMGUI也必须跟随整套UI方向。

**方案 / 实施步骤**:
方案要点：
UGUI通过WornUiSurface在钢板面板叠加四个暗色铆钉座与小型暖金属中心，关闭raycastTarget；IMGUI通过RetroUiTextures共享同色色块纹理，并由BattleController的DrawPanel绘制。标题/剧情对话框在木衬创建后追加铆钉；战斗内容区调整至20×缩放边距，给8–18×缩放的装饰外沿留安全间隔。继续复用现有钢木纹理，不复制参考图中的房间布局或素材。

实施步骤：
1. 在既有风格基线上扩展铆钉组件，不新增主题系统。
2. 覆盖UGUI与IMGUI正式钢框，核对内衬/内容绘制顺序。
3. 独立R6发现战斗面板遗漏与内容边距风险，修复后复核通过。

**验证方法**: 静态源码复核确认五类UGUI框体和战斗IMGUI框体均调用铆钉绘制；UGUI不拦截点击、IMGUI不消费输入；战斗内容与装饰外沿保持2×缩放边距；ART_BIBLE描述相符。三名独立复核者对修复后状态PASS。没有打开Unity、没有构建或运行功能测试；运行时画面/不同分辨率可读性待用户授权。

**踩坑 / 已知异常与失败经验**: 战斗面板用IMGUI独立绘制，UGUI覆盖核对会漏掉它；装饰边缘还需与文字/状态/命令区域保持安全距离。应跨越UI框架检查所有正式面板。

**关键文件与接口**: - `UNITY/Assets/Scripts/Presentation/WornUiSurface.cs` — UGUI铆钉绘制helper。
- `UNITY/Assets/Scripts/UI/RetroUiTextures.cs` — IMGUI共享铆钉纹理与DrawSteelRivets。
- `UNITY/Assets/Scripts/Presentation/FieldUiPresentation.cs`、`UNITY/Assets/Scripts/FC/FcTitleScreen.cs`、`UNITY/Assets/Scripts/FC/FcDialogue.cs`、`UNITY/Assets/Scripts/Battle/BattleController.cs` — HUD、菜单、地图、标题、对话和战斗正式框体接入。
- `docs/ART_BIBLE.md` — 记录钢板铆钉为克制结构细节。

**状态**: 部分完成

### F-106: FC波布机械师绕院事件状态与文档核对边界
**日期**: 2026-10-26
**项目**: GAME / D:/code/GAME
**关键词**: FC重装机兵, 波布机械师, PobMechanicRideEvent, FC_REFERENCE, 事件状态, 原版核对, 车辆归属

**需求场景 / 现象**: 对照Unity当前实现与FC差距文档时，发现FC_REFERENCE仍写“停车后对话招募，绕院事件尚未重建”，但当前FcWorldBuilder已有机械师绕院骑行事件。

**方案 / 实施步骤**:
方案要点：
以当前源码确认开发版事实，再将FC原版基线和待核差异分开记录。当前条件为取得首车标记、事件未发生、玩家乘车进入树旁触发区；协程随后自动播放绕树骑行演出，机械师在演出中出现，结束后显示反应对白并开放招募。代码不校验车辆所有权。原版触发坐标/时序、对白、满员条件及实机行为仍待指定版本核对。

实施步骤：
1. 静态跟读触发条件、自动演出顺序、对话和招募调用。
2. 将两份差距文档改为描述当前实现，并明确原版与实机状态仍待核验。
3. 对文件进行独立静态审查与交叉核验；未运行Unity、构建或游戏。

**验证方法**: 审阅源码与两份文档的一致性；R6A/B/C独立审查和交叉核验均PASS。Unity实机验证仍未完成。

**踩坑 / 已知异常与失败经验**: 文档记载的是较早状态，新增事件代码完成后没有同步差距表；且粗略总结容易把“驾驶者手动绕树”或“自有战车”误写成代码条件。
不要把“触发器中的自动绕树演出”写成玩家手动绕行；不要把乘车状态推断为驾驶自有车辆；区分当前实现事实与FC原版准确性。

**关键文件与接口**: - `UNITY/Assets/Scripts/FC/FcWorldBuilder.cs` — `BuildMechanicHouse` 创建机械师、院树、触发器和招募交互。
- `UNITY/Assets/Scripts/FC/FcWorldBuilder.cs` — `PobMechanicRideEvent.CanTrigger`、`OnTriggerEnter`、`PlayRide`、`CanShowMechanic`、`TryRecruit` 控制事件和招募。
- `docs/FC_REFERENCE.md` — 原版基线与尚未对齐项。
- `docs/FC_REMAKE.md` — 当前Unity实现状态总览。

**状态**: 部分完成

### F-107: FC重制UI语义色板跨UGUI与IMGUI统一
**日期**: 2026-10-26
**项目**: GAME / Unity FC 初代《重装机兵》3D 重制
**关键词**: **关键词**：FC重制 UI、RetroUiColors、UGUI、IMGUI、旧钢、暖木、语义色板、RichText

**需求场景 / 现象**: 用户以斜俯视旧钢墙、暖木地板、暖灯与像素人物的室内图确认 UI 视觉方向。多个 UI 系统已复用钢木纹理，但角色颜色在标题、野外 HUD/地图/菜单、剧情对话、战斗与城镇原型间分散，战斗 IMGUI RichText 还有独立 HEX 状态色。

**方案 / 实施步骤**:
方案要点：
在 `Game.UI.RetroUiColors` 中按语义定义暖纸正文、次级/弱化/禁用文字、黄铜焦点、选中/悬停、锈色、阵亡/受损/奖励/失败、钢/木染色、暗底/信息面板、分割线和铆钉色。IMGUI RichText 使用相同颜色的 HEX 字符串 token；`RetroUiTextures`、`WornUiSurface` 继续负责生成与铺设材质。ART_BIBLE 记录 RGBA HEX、用途和纹理对比不得压过文字的规则。只复用颜色职责，不把场景参考图的房间布局套到 UI。

**验证方法**: 静态检查语义颜色定义、所有目标 UI 的 token 调用、战斗 RichText HEX 引用及 ART_BIBLE 映射；三路独立静态复核和交叉核验通过。未运行 Unity、构建或功能测试；不同分辨率下的实际对比度、字体可读性和材质观感仍待用户授权真实界面验收。

**踩坑 / 已知异常与失败经验**: 只搜 UGUI 会漏掉 BattleController/DialogueDebugUI 等 IMGUI 界面；战斗状态还可能在 RichText 标签里使用直接 HEX。开始改动前记录任务基线，避免把长期工作区里已有的逻辑/布局脏改误归到颜色统一单元，更不能为通过纯视觉 review 回滚它们。

**关键文件与接口**: - `UNITY/Assets/Scripts/UI/RetroUiTextures.cs` — `RetroUiColors` 与共享纹理颜色。
- `UNITY/Assets/Scripts/Presentation/FieldUiPresentation.cs`、`Presentation/Menu/FieldCommandMenu.cs` — HUD、菜单、地图。
- `UNITY/Assets/Scripts/FC/FcTitleScreen.cs`、`FcDialogue.cs` — 标题、剧情对话。
- `UNITY/Assets/Scripts/Battle/BattleController.cs` — IMGUI 战斗与 RichText 状态。
- `UNITY/Assets/Scripts/Field/FieldHUD.cs`、`DialogueDebugUI.cs`、`TownDebugMenu.cs` — 逻辑场景原型/调试界面。
- `docs/ART_BIBLE.md` — UI HEX token 与层级规则。

**状态**: 部分完成

### F-108: FC拉多开局补给商店隔离
**日期**: 2026-10-26
**项目**: GAME / Unity FC 初代《重装机兵》3D 重制
**关键词**: **关键词**：FC重制、拉多补给店、GameDB.RegisterShop、campaign runtime、药品、修理包、弹药补给、商店隔离

**需求场景 / 现象**: FC 重制开局中，拉多镇曾复用 SHP_Zhanqiao prototype 商店，库存包含与开局经济不匹配的盐海/高阶内容。核心闭环需要玩家击败战狗并取得蚊式后，回镇补充药品、维修与弹药，再保存旅程。

**方案 / 实施步骤**:
方案要点：
在 GameDB 增加 RegisterShop，复用现存 Resources/Shops 字典并按独立 ID 写入一项。FcCampaignBootstrap 创建 SHP_FC_Rado，库存只引用已有 ITM_Tonic、ITM_RepairPack、ITM_AmmoCrate；仅 Rado TownData 指向该商店。波布、奥多仍引用 SHP_Zhanqiao，避免改动其它城镇进程与旧 campaign 库存。

**验证方法**: 静态检查商店 ID、三项道具引用、资源文件存在、GameDB 注册顺序、其他城镇引用保持原状；R6 三路独立复核及三路交叉核验通过。没有运行 Unity、构建、游戏或自动化测试；实机路线测试待用户授权。

**踩坑 / 已知异常与失败经验**: 不要把新库存提前加入北洞 7 毫米炮奖励路径；首车主炮已装配，拉多开局商店只需提供消耗品。开发期价格不能当作 FC 原版价格。

**关键文件与接口**: UNITY/Assets/Scripts/Core/GameDB.cs、UNITY/Assets/Scripts/FC/FcCampaignBootstrap.cs、docs/FC_REMAKE.md。

**状态**: 部分完成

### F-109: 拉多恢复服务统一
**日期**: 2026-10-26
**项目**: FC Remake / `D:\code\GAME`
**关键词**: FC, 拉多, Rado, HP 恢复, 旅店, inn, TownService.Rest, 姐姐 NPC, 住宿, 金币不足, 免费治疗

**需求场景 / 现象**: 拉多姐姐对话完成时直接把队伍所有成员 HP 恢复到上限，绕过拉多旅店既有的收费住宿服务，造成恢复经济规则不一致。

**方案 / 实施步骤**:
方案要点：
删除姐姐对话的 HP 修改回调，将提示改为受伤后前往旅店休息。旅店仍调用 `TownService.Rest(state, FcCampaignBootstrap.Rado)`，由服务返回值决定成功、无需住宿、金币不足或不可用反馈。保留“这是当前开发版规则，原版对应机制尚待核实”的文档边界；不据此声称原版机制已确认。

实施步骤：
1. 移除姐姐对话结束时的免费恢复回调。
2. 更新对话文案，指引受伤队伍前往旅店。
3. 核对旅店住宿价格及服务结果处理未变，并同步文档边界。

**验证方法**: 本轮进行了静态代码与文档复核，三路独立 R6 review 和交叉核验均通过，R8 集成复核通过。Unity、构建与测试未获用户授权，未执行。授权后可验证正常路径（受伤后与姐姐对话、前往旅店付费恢复）和边界路径（满血不收费、金币不足不恢复）。

**踩坑 / 已知异常与失败经验**: 姐姐 NPC 的 `FcDialogue.Show` 绑定了直接遍历 `GameSession.Instance.party` 并设置 `hp = maxHp` 的完成回调。这个回调与旅店通过服务层处理的付费恢复路径并存。
存在看起来像“医疗包”的姐姐模型装饰，但不能据此推断互动应免费治疗；应以明确的游戏服务规则为准。另需把开发版选择与原版事实分开记录。

**关键文件与接口**: - `UNITY/Assets/Scripts/FC/FcWorldBuilder.cs` — 姐姐对话只做指引；旅店前台保留 `TownService.Rest` 付费入口和结果反馈。
- `docs/FC_REMAKE.md` — 记录开发版经济规则、原版机制未核实和运行时入口尚待实机确认。

**状态**: 部分完成

### F-110: 标题页区分损坏存档与空槽
**日期**: 2026-10-26
**项目**: GAME / `D:\code\GAME`
**关键词**: Unity, FC, 标题页, 存档槽位, 损坏存档, SaveSystem.Peek, SaveSystem.Exists, continue menu, corrupted save, unreadable slot

**需求场景 / 现象**: 标题页将 `SaveSystem.Peek(slot)` 返回 null 的情况一律显示为空槽；但 Peek 对真实空槽和已存在但损坏/不可读取的存档都会返回 null。玩家选择损坏记录时，Activate 又因 Exists 为 true 而尝试读档并提示错误，造成标题页状态与操作结果矛盾。

**方案 / 实施步骤**:
方案要点：
Peek 返回有效数据时继续显示时间和金币；Peek 为 null 时用 Exists 区分存在但不可读和不存在的槽位。只改显示判定，不改变读档流程、数据格式或修复策略。

实施步骤：
1. 计算槽位索引后读取 Peek。
2. Peek 非空显示保存时间与金币；否则依据 Exists 显示损坏/空。
3. 保持标题页 Activate 与 LoadGame 路径不变。

**验证方法**: 静态代码检查；R6A/B/C 独立复核和交叉核验 PASS，R8 静态集成复核 PASS。未运行 Unity、构建或测试；真实空槽/有效存档/损坏存档三种界面路径待用户授权。

**踩坑 / 已知异常与失败经验**: 标题页只检查反序列化摘要是否为 null，没有像场内 `FieldCommandMenu.SavePage` 一样再查询文件是否存在。
`Peek == null` 不等于槽位为空；任何显示层需要区分空槽和损坏档时，都应结合 `Exists` 或专门的读取结果类型。

**关键文件与接口**: - `UNITY/Assets/Scripts/FC/FcTitleScreen.cs` — `Refresh` 的三个存档槽位状态标签。
- `UNITY/Assets/Scripts/Core/Save/SaveSystem.cs` — Peek 读取失败返回 null；Exists 判断对应文件是否存在。
- `UNITY/Assets/Scripts/Presentation/Menu/FieldCommandMenu.cs` — 场内页已有相同区分方式，可作为一致性参考。

**状态**: 部分完成

### F-111: 存档摘要与读取共享最小结构校验
**日期**: 2026-10-26
**项目**: GAME / `D:\code\GAME`
**关键词**: Unity, FC, 存档校验, SaveSystem.Peek, DoLoad, SaveData, party, inventory, JsonUtility, corrupted save, malformed save, 读档异常

**需求场景 / 现象**: JSON语法可解析但缺失存档必需结构（如版本、玩家队伍、队员ID或inventory列表）时，Peek只反序列化并返回非空摘要；实际读取继续进入SaveSerializer.FromSave，可能因枚举缺失集合而返回Corrupted。于是存档列表可能展示记录时间/金币，却无法加载。

**方案 / 实施步骤**:
方案要点：
在SaveSystem中建立共享最小结构谓词：对象存在、版本号大于0、party非空、每名队员对象和ID非空、inventory列表存在。Peek和DoLoad在读取后共用；Peek将结构无效映射为null，DoLoad将其映射为Corrupted。有效结构继续走现有SaveSerializer.FromSave。

实施步骤：
1. 复用一个谓词检查Peek/Load共同依赖的根字段。
2. 让摘要读取和实际读取对该类无效存档给出一致结果。
3. 保留已支持历史/未来版本及现有恢复路径。

**验证方法**: 静态核对调用关系与返回结果；R6三路复核、交叉核验和R8静态集成复核均PASS。Unity、构建、测试和浏览器未获授权，未执行。

**踩坑 / 已知异常与失败经验**: Peek仅捕获JSON反序列化异常，没有检查游戏状态还原所依赖的最小根结构；DoLoad只拒绝完全无法反序列化的null对象。
`JsonUtility.FromJson<T>` 返回非null只证明JSON可以反序列化为对象，不代表必需的玩家数据集合齐全。区分摘要有效性时应与实际恢复入口使用同一最小根结构约束。

**关键文件与接口**: - `UNITY/Assets/Scripts/Core/Save/SaveSystem.cs` — `Peek`、`DoLoad`、`HasRequiredPayload`。
- `UNITY/Assets/Scripts/Core/Save/SaveSerializer.cs` — 现有版本迁移和状态恢复，本次未改。

**状态**: 部分完成

### F-112: GAME待办状态的证据分层
**日期**: 2026-10-26
**项目**: GAME / `D:\code\GAME`
**关键词**: GAME, FC重制, 项目状态盘点, 待办, 静态实现, 运行验收, 原版核验, 接口签核, DEFERRED, backlog, 待办分类, GDD, FC_REMAKE, FC_REFERENCE, 原版对照, 实机验收

**需求场景 / 现象**: 用户询问游戏还剩哪些任务时，工作项横跨未实现内容、代码存在但未运行的系统、原版事实未确认的差异以及跨代理接口待签核。把这些状态混成单一未完成清单会遗漏验收和依赖。
FC重制的待办同时包含内容尚未实现、已实现但未经运行验收、原版事实未核实，以及技术接口待双方认可。若把它们合并成单一“未完成”状态，容易漏测或错误宣称复刻准确。

**方案 / 实施步骤**:
方案要点：
用四种标签整理工作：未实现、已静态实现待真实验收、原版依据待核、接口/授权依赖未解决。GDD提供领域目标，FC_REMAKE列当前开发实现与剩余交付，FC_REFERENCE列原版差异，AUDIO/ART_BIBLE补充资产验收，INTERFACE核对协作约定，SIRE当前任务台账证明最近修改和测试状态。历史运行记录不得证明后续修改已通过，不推算完成百分比。
用四类标记盘点：①尚未实现；②已静态实现、待授权运行验收；③原版来源/规则待核；④跨代理接口未签核。GDD提供领域总览，FC_REMAKE提供实现快照，FC_REFERENCE提供逐项原版差异，AUDIO/ART_BIBLE记录资产边界，INTERFACE提供签核状态，最近SIRE台账提供本轮验证范围。不得用日期较早的实测证明后续改动。

实施步骤：
1. 读取上述文档的“待核、未完成、待授权、待认可”条目。
2. 与最新任务台账交叉核对近期改动。
3. 按四种状态输出优先清单，标明依据和建议的下一验证动作。
4. 注明清单更新时间与文档快照限制。
5. 检索各领域文档中的“仍需交付、待核、待授权、待认可”。
6. 对照最新任务台账识别近期静态改动及未测试项。
7. 按四类给出优先级、依据和下一步验收路径。
8. 将结果标为当前快照，不推断百分比或排期。

**验证方法**: 本轮逐项核对 GDD、FC_REMAKE、FC_REFERENCE、AUDIO、INTERFACE 及近期SIRE台账，结果见 `D:/sire/sire_ledger/runs/R20261026-215151-game/unfinished-tasks.md`。未运行游戏或测试。
2026-10-26逐项对照上述文档及I-24/I-29签核符号，近期代码改动按任务台账标记未测试。清单证据保存在 `D:/sire/sire_ledger/runs/R20261026-215151-game/unfinished-tasks.md`。

**踩坑 / 已知异常与失败经验**: “✅接口认可”表示技术约定，不证明内容符合原版；“代码/资源存在”表示静态实现，不证明可玩；未授权验收必须保持DEFERRED。
项目状态分散在不同职责文档，代码存在、设计目标、原版证据和实际运行证据的证明力不同；接口共识状态也是独立依赖。
历史上已通过的路径不等于新改动通过；✅技术合同也不表示游戏内容已符合FC原版；二手攻略不能代替原版实机来源。

**关键文件与接口**: - `docs/GDD.md` — 六领域目标和整体流程。
- `docs/FC_REMAKE.md` — 当前切片及仍需交付。
- `docs/FC_REFERENCE.md` — 原版来源与未校准事项。
- `docs/AUDIO.md`、`docs/ART_BIBLE.md` — 资产存在状态与验收缺口。
- `docs/INTERFACE.md` — 双方签核状态。
- `docs/GDD.md` — 领域状态与产品级缺口。
- `docs/FC_REMAKE.md` — 当前可玩切片及仍需交付。
- `docs/FC_REFERENCE.md` — 原版来源、差异与未核内容。
- `docs/INTERFACE.md` — 双方认可/待认可合同。
- `docs/AUDIO.md`、`docs/ART_BIBLE.md` — 音频和资产验收限制。

**状态**: 已完成

### F-113: Unity 乘车事件复用旧前置条件并加强车辆归属守卫
**日期**: 2026-10-27
**项目**: GAME / D:/code/GAME
**关键词**: Unity, vehicle ownership, VehicleRecord, assignedCharacterId, party driver, event trigger, CanTrigger, garage, game event guard

**需求场景 / 现象**: 场景事件已有进度标志与步行状态前置条件，但乘车事件还应确认有效驾驶员实际乘坐登记并归属匹配的未停放车辆。与此同时，现有编辑器 smoke-test 可能直接调用较宽松的旧触发谓词。

**方案 / 实施步骤**:
方案要点：
保留原有共享谓词及其既有调用语义，新增更严格的事件入口谓词：先复用进度与步行条件，再找到存活且正在乘车的活动队伍成员，按其 TankLoadout 引用查找 VehicleRecord，并要求记录未停放且 assignedCharacterId 匹配驾驶员。实际事件入口使用严格谓词；这样可以增强运行入口而不改变已有纯逻辑调用者。

实施步骤：
1. 保留原有共享条件谓词，增加只供实际乘车事件使用的严格守卫。
2. 在开启演出协程之前检查存活驾驶员、车辆记录、归属和停放状态。
3. 文档明确说明这是开发版行为；未核实的原版条件继续标注未知。

**验证方法**: 可先静态确认事件入口调用严格守卫，且守卫依次包含驾驶员、VehicleRecord、owner ID 与 parked 检查；取得测试授权后再覆盖正常自有车辆、步行、无车记录、错配owner、停放车辆及存档后车辆同步。当前实现轮只做源码静态检查，未运行测试、构建或 Unity。

**踩坑 / 已知异常与失败经验**: 运行时初始化可能通过 `VehicleService.Normalize` 从活动队伍引用重建归属，因此对异常旧存档的行为要区分“启动时规范化”与“事件守卫拒绝”；不要为使事件触发而移除归属条件。既有 smoke-test 调用旧谓词时，新增约束应放在实际事件入口，避免无关测试语义改变。

**关键文件与接口**: - `UNITY/Assets/Scripts/FC/FcWorldBuilder.cs` — `PobMechanicRideEvent.CanTriggerWithOwnedVehicle` 与 `OnTriggerEnter`。
- `UNITY/Assets/Scripts/Tank/Runtime/VehicleService.cs` — `VehicleService.Of` 的载具引用查找与 `Normalize` 归属同步。
- `docs/FC_REMAKE.md`、`docs/FC_REFERENCE.md` — 区分开发守卫与原版事实。

**状态**: 部分完成

### F-114: Unity FC系统菜单接入显示控制并复用木钢交互
**日期**: 2026-10-27
**项目**: GAME / D:/code/GAME
**关键词**: Unity 6, Screen.SetResolution, Screen.resolutions, FullScreenWindow, borderless fullscreen, windowed mode, resolution picker, AudioDirector, System menu

**需求场景 / 现象**: 复古风格游戏的系统分页已有存读档、音乐与音效音量控制，但缺显示模式/分辨率选项，也没有把 AudioDirector 已有的主音量控制暴露给玩家。需要补齐能力，同时保留现有FC木钢界面主题和菜单交互。

**方案 / 实施步骤**:
1. 核对System页现有存读档和音量菜单及AudioDirector接口。
2. 用Unity Screen API显示并切换模式/分辨率；复用Unity自身的显示设置持久化，不创建重复的PlayerPrefs键。
3. 沿用菜单列表视觉和反馈，增加主音量控制。
4. 明确记录平台差异及未获授权时不得运行Unity/构建/游戏。
方案 / 架构：复用现有命令列表行、滚动、选择色与反馈。通过 `Screen.fullScreenMode` 显示当前模式，并用 `Screen.SetResolution(width,height,FullScreenMode)` 在 `Windowed` 与 `FullScreenWindow` 间切换。用 `Screen.resolutions` 形成分辨率项，按宽高去重后循环，并把当前窗口尺寸加入候选；无其他选项时显示禁用说明。离开全屏时使用桌面尺寸的安全比例、并限制最大逻辑窗口尺寸，避免打开几乎铺满桌面的可移动窗口。总音量调用现有 `AudioDirector.SetMasterVolume`，不重复实现声音状态。

**验证方法**: 静态检查Screen API、尺寸去重/循环、无候选时的禁用状态、音量和存读档旧入口、文档描述。实际验收需切换全屏/窗口、不同分辨率、重启持久化、窗口可移动、4:3/16:9/21:9和小屏可读性；本轮未运行测试、Unity、构建或浏览器。

**踩坑 / 已知异常与失败经验**: 踩坑：Unity 6已经通过PlayerPrefs持久化分辨率/全屏模式，因此不应额外维护同一设置的应用层副本。Screen.SetResolution在当前帧结束后才应用，反馈文案应说“已请求”而非“已生效”。Screen.resolutions可能同尺寸存在多个刷新率，UI只需按宽高去重；当前窗口可能是非标准尺寸，应保留当前项以便用户循环回去。
【原状态说明】已静态实现与复核；显示平台、窗口尺寸和多分辨率实机行为待授权验收。

**关键文件与接口**: - `UNITY/Assets/Scripts/Presentation/Menu/FieldCommandMenu.cs` — System分页、显示模式/分辨率控制和主音量选项。
- `UNITY/Assets/Scripts/Presentation/Audio/AudioDirector.cs` — 既有音量状态与`SetMasterVolume`。
- `docs/FC_REMAKE.md` — 更新系统菜单能力及验收状态。

**状态**: 部分完成

### F-115: Unity战斗C装置行动次数贯通与提交边界
**日期**: 2026-10-27
**项目**: GAME / D:/code/GAME
**关键词**: Unity, C装置, CUnitData, actionsPerTurn, BattleSystem.SubmitCommands, 多次行动, action queue, ammo reservation, item stack reservation

**需求场景 / 现象**: CUnitData 含有每回合行动次数，但战斗命令阶段原先只给玩家角色一个行动槽，战斗核心也没有防止公开提交入口收到超额度或非当前队员动作。

**方案 / 实施步骤**:
方案要点：
将有效行动数接入 Combatant；命令控制器按额度创建槽位并显示进度，跨槽投影上/下车状态并预留有限弹药和物品数量。BattleSystem 再按每名玩家队员限制手动提交动作数，拒绝不在当前玩家 roster 的 actor；自动助战按额度生成动作并为有限弹药做本轮局部预留。同角色多次动作保持提交顺序。原版FC行动规则和数据未核实时，文档必须标为开发数据行为和待核事实。

实施步骤：
1. 静态追踪 CUnitData 到 Combatant 的额度数据流。
2. 接入命令队列、槽位显示、Undo、跨槽状态投影和资源预算。
3. 在战斗系统入口再验证当前玩家 roster 与逐角色行动次数；自动队员单独按额度结算。
4. 交叉审查边界时修复非 roster actor 可绕过次数验证的问题。
5. 静态审查通过后，未获测试授权时将动态验收记为 DEFERRED。

**验证方法**: 静态核对至少一个槽、手动/自动队员额度、roster校验、超额提交、Undo、板载状态投影、手动/自动弹药和道具预留、同角色顺序、部件 UI 和 FC 待核标注。本次三名审查者及交叉核验通过；未运行测试、构建、Unity Editor 或游戏。动态覆盖应待用户授权后进行。

**踩坑 / 已知异常与失败经验**: 数据层的 `actionsPerTurn` 尚未贯通到角色有效属性、命令队列、战斗结算和部件详情 UI。UI 的槽位重复本身不足以约束直接调用战斗系统的输入；多槽提前排队还可能重复消费有限弹药或同一物品堆叠。
只在 UI 限制槽数不能保护 `SubmitCommands` 这样的公开入口；复核中发现非玩家 roster actor 能绕过逐人额度，应在入队之前过滤。自动队员多槽也要在生成动作时预留同一武器的有限弹药，否则每次选择都可能看到同一发子弹。不要把开发资产中 Twin 为 2 次行动写成 FC 原版结论。

**关键文件与接口**: - `UNITY/Assets/Scripts/Battle/Combatant.cs` — `ActionsPerTurn` 有效额度。
- `UNITY/Assets/Scripts/Battle/BattleController.cs` — 命令槽、槽号、状态投影及手动资源预留。
- `UNITY/Assets/Scripts/Battle/BattleSystem.cs` — `SubmitCommands` roster/次数边界、自动动作与弹药预算、角色动作顺序。
- `UNITY/Assets/Scripts/Presentation/Menu/FieldCommandMenu.cs` — C装置部件显示行动数。
- `docs/FC_REMAKE.md`、`docs/FC_REFERENCE.md` — 开发行为与原版未知项说明。

**状态**: 部分完成

### F-116: FC重制Rocco北路切片的地图注册与边界核算
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: FC重装机兵, Rocco, 罗克镇, Unity FC campaign, WorldMapData, TownGate, EncounterZone, GameDB, 特殊砲弹商店, 城镇地图扩展

**需求场景 / 现象**: FC地图原型仅含拉多、波布、奥多等开局地点；全量重制仍需连续扩展城镇、地图、游戏服务和原版对照。

**方案 / 实施步骤**:
方案要点：
Rocco作为本轮北路推进切片接入现有通用注册路径。`FcCampaignBootstrap` 创建 TownData、ShopData、WorldMapData；TownData.shopId链接特殊砲弹店；所有资产进入 RegistryAssets 后由 GameDB 注册。`FcWorldBuilder` 继续复用TownGate、TownData驱动的车库/赏金/商店服务和EncounterZone，不引入独立城镇服务系统。罗克地图点与城镇中心设在(55,80)；城镇安全区和道路深度均28.5，并按墙体碰撞边界留距；普通遭遇覆盖入口前，TownGate内遭遇暂停。

实施步骤：
1. 先从官方/二手来源分离FC已验证事实与NES攻略线索；只将Rocco在奥多北面和有改造/砲弹服务作为二手线索。
2. 新增城镇、商店和可发现地图点；将六类开发版特殊砲弹从拉多补给店移至罗克店，价格/库存继续标记为未校准。
3. 延伸北路并核算town gate、道路和地图边缘的坐标区间；将镇路深度与安全区统一以避免视觉越界。
4. 记录真实路线/边界/地图存档测试，但未获授权时R7必须DEFERRED，不得以静态核对替代。

**验证方法**: 静态代码查找与区间算式；R6三路独立审查和互相交叉核验。真实路径验收：新档击败Big Cannon→走北路→发现/进入Rocco→操作车库和砲弹店；绕行/地图边界；发现旗标保存读档。当前这些Unity运行路径均待用户授权，不能宣称可玩通过。

**踩坑 / 已知异常与失败经验**: 原town gate与路面共用尺寸时，新镇紧邻既有镇/北山会发生区域重叠；必须同时核对门区间与碰撞体的近侧边缘，不能只按墙中心坐标判断。R8发现路面比山体碰撞边界越出0.5单位，改用镇专用roadDepth后解除；最终保留0.25间距。静态证据/独立复核文件必须随修复同步更新，避免归档继续陈述旧结论。

**关键文件与接口**: - `UNITY/Assets/Scripts/FC/FcCampaignBootstrap.cs` — `Rocco` TownData、`LOC_FC_Rocco`、`SHP_FC_Rocco_Shells`注册及中文名。
- `UNITY/Assets/Scripts/FC/FcWorldBuilder.cs` — `BuildRocco`、`BuildTown(..., safeDepth, roadDepth)`、北路遭遇范围。
- `UNITY/Assets/Scripts/WorldMap/WorldMapData.cs` — 地点的mapId/position/discovery radius。
- `UNITY/Assets/Scripts/Field/TownGate.cs` — 镇区安全边界；镇内无遭遇。
- `docs/FC_REFERENCE.md` — 来源置信、开发近似和未完成北方路线。

**状态**: 部分完成

### F-117: EncoderPlotter 内部调试文件解析工具
**日期**: 2026-10-28
**项目**: EncoderPlotter_0903_01
**关键词**: 内部调试工具, debug_tool.py, IAP ZIP, kingkong, ArgumentsHeader, j72, ZIP Slip, 调试日志, data.log

**需求场景 / 现象**: 桌面应用需要从设置页导入 BIN、IAP ZIP、调试日志 ZIP 和加密 Python/data 日志，解密并结构化展示。IAP 和调试日志 ZIP 可能包含二进制数据块及加密成员。

**方案 / 实施步骤**:
方案要点：
设置入口打开独立长文档窗口；窗口上方固定选择文件区，下方滚动显示分节报告并支持逐节/全文复制。主进程提供内部版受限的文件选择 IPC，由 Python 单次 CLI 入口复用现有解析/解密逻辑；输出写入 logs/<输入同名目录>。ZIP 成员路径 resolve 后必须位于压缩包内容根目录。IAP j72 按 ArgumentsHeader 的 series/argumentsVersion 选择 DataFormatter 类型；历史布局缺少 SN 尾字段时按 EncoderBase 的规则回退。BIN 无法单独推断传输加密，展示为未知。

实施步骤：
1. 通过主进程文件对话框按类型选择文件并将输入输出路径交给 Python。
2. 复用现有 BIN/IAP/logger 解密和解析逻辑。
3. 按文件类型展示分区、完整结果及可复制文本，并写入同名 logs 子目录。
4. ZIP 解包进行路径校验；失败解密内容以状态和 rawHex 显示，不冒充结构化解析。

**验证方法**: CLI 实样覆盖明文/加密 BIN、IAP 第一阶段 ZIP、调试日志 ZIP、data.log、Python 日志和无效 BIN/非 ZIP。所有 CLI 样本解析通过，静态编译检查通过。Electron UI 真实交互受 Windows `GetCursorPos` 拒绝访问阻塞，故设置入口、复制粘贴和外部版 UI 未验收。

**踩坑 / 已知异常与失败经验**: 数据格式规则分散在已有 Python BIN 解析器、DataFormatter、Protector 和 logger 加密实现中；UI 不能独立假定传输加密状态，ZIP 还需要防止成员路径逃逸。
logger 数据需逐行剥除填充并还原取反 hex；Python 子进程强制 UTF-8 避免 Windows GBK 输出 emoji 时失败。ctypes 参数结构需递归转 JSON；历史短布局需兼容无 SN 尾字段；debug ZIP 解密失败的 snapshot 不应并入日志文本。

**关键文件与接口**: - `controller/python/debug_tool.py` — analyze、ZIP 安全解包、日志解密、参数结构解析。
- `controller/python/main.py` — `--debug-tool kind source output` CLI 入口。
- `main/index.js` — `open-debug-tool-file` IPC 和内部版门禁。
- `components/analyzer/version.html` — 内部版设置入口。
- `asset/debug-tool.html`、`asset/js/debug-tool.js`、`asset/css/debug-tool.css` — 独立报告窗口和文档式长内容视图。

**状态**: 部分完成

### F-118: EncoderPlotter 五仓 Git Flow 发版与打包规则（2026-09-07 更新版）
**日期**: 2026-10-28
**项目**: EncoderPlotter1（主仓 + sub_embedded/sub_common/sub_automation/sub_algorithm）
**关键词**: 打包规则, 发版, 发布流程, git flow, feature, release, hotfix, 回合, back-merge, back-merge-check, 桥接分支, backmerge, tag, encoder-plotter-v, rc-v, test-v, release-line-gate, changelog-gate, ALLOW_BACKMERGE_DEBT, gitlink, 子先父后, 子模块指针, sub_algorithm, 4.9.2, 正式包, RC包, 测试包, 打包

**需求场景 / 现象**: 用户问“打包规则/发版规则/怎么发版/怎么打 tag/回合/hotfix 怎么走”，或要求按打包/发版规则执行（开分支、打 tag、合 main、回合、挪 gitlink）时，先按下方清单给出“应该怎么做”的提示（含当前该步的前置检查与门禁会挡什么），再执行；执行时逐步对照，缺前置条件就停下说明。细节以仓库 docs/branching.md、ADR 0006、branching-standards-audit.md 为准，文档与本条不一致时以文档为准、文档错了改文档。

**方案 / 实施步骤**:
方案要点：
feature/<主题> 从 develop 出、合回 develop；release/x.y.z 从 develop 出，在其上改版本号与 CHANGELOG，合入 main 和 develop；hotfix/x.y.z（x.y.z 为将发布的新版本号）从 main 出，客户现场急修唯一出口，合入 main 和 develop。均为短命分支，合完即删，超 4 周未合入算异常。热修期间若有 release/* 在制，热修改动合入那条 release 分支而非 develop。
1. 一律 merge commit，禁 squash、禁 rebase merge（squash 换 SHA，主仓锁的子模块指针悬空）。
2. 正式 tag（encoder-plotter-vX.Y.Z）只打在 main；rc-vX.Y.Z-N 打在 release/* 或 hotfix/*；test-vX.Y.Z-NN[-描述] 任意分支。
3. 子先父后：改过的子仓先各自走完发布并打 tag，主仓再把 gitlink 挪到该提交，重新验证后才能合 main。gitlink 变更不单独建 MR，须与使用它的父仓代码同一 MR。
每次合入 main 后立刻回合，不攒。
- 回合前 `bash scripts/back-merge-check.sh check`；看两边共同触碰的文件，不看冲突数量（语义冲突 git 不报）。
- 回合 MR 源分支是受保护的 main，冲突时不能点“解决冲突”，改走桥接分支 `feature/backmerge-<版本号>`，保留 merge commit 禁 squash。
- 冲突由写 hotfix 的人解（保住 hotfix 意图、形式服从 develop 结构）；解完回到该 bug 复现场景在 develop 上真机复验，能编译/无冲突不算验证。
- 回合后 `bash scripts/back-merge-check.sh verify <merge-commit>` 查空合并（git merge -s ours 会造出“宣称已含、实际没进”的提交）。
- 不回合的后果：下一版发不出去（门禁④拦），且已交付的修复会被 develop 拉出的 feature 静默带回去。
①提交被 main 可达；②sub_embedded/sub_common/sub_automation 三个 gitlink 各自被子仓 main 可达；③sub_algorithm 只打印所在远端引用，为空则拦；④上一个正式 tag 已回合进 develop（急事可设 `ALLOW_BACKMERGE_DEBT=<理由>` 放行，理由进流水线日志）。RC 须在 release/* 或 hotfix/* 上。另有 changelog-gate：CHANGELOG.md 须有与 package.json 同名的版本段。门禁拉不到 refs 时一律停下报错，不用本地缓存继续判。

实施步骤：
release/x.y.z 上改 package.json version，CHANGELOG 条目写进当前版本段（release/hotfix 分支上不写 [Unreleased]；develop 上写 [Unreleased]），条目前缀仅 新增：/修复：/移除：，正文 ≤30 字、一条一件事、不写实现；→ 合 main（merge commit）→ 打正式 tag（CI 出包，本地不出正式包）→ 立刻回合 develop。验包用 dev-<描述> tag 让 runner 出包，验完删 tag。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: ①sub_algorithm 归算法部门维护，不加分支保护、不进 gitlink 门禁，其 release 是活跃线、main 是僵尸分支；发正式版前由发版人人工确认其 gitlink 所在分支/提交，结果贴进发版 MR，为空停发。②4.9.2 已合入 main 但暂不打 tag，内容在 CHANGELOG「待发布」段；此时 main 顶端不等于已发布版本，判断客户手里版本看 tag 不看 main。
本条来自用户 2026-10-28 粘贴的《Git Flow 标准流程（2026-09-07 更新版）》，未逐项对照仓库实际脚本核验；4.9.2 未打 tag 的状态会随发布变化，使用前以 git tag 与 CHANGELOG 现状为准。

**关键文件与接口**: 原记录未记载

**状态**: 已完成

### F-119: ai-tool 手机/电脑接入与外网访问方案（Tailscale + serve HTTPS）
**日期**: 2026-11-02
**项目**: ai-tool（PC 作服务器的私人多 AI 工作台，Fastify + WebSocket，默认监听 0.0.0.0:8787）
**关键词**: 外网访问, 内网穿透, 手机访问, iPhone, PWA, HTTPS, Tailscale, tailscale serve, MagicDNS, 证书, WebSocket, wss, 局域网, 无鉴权, 加入设备, 多手机, ai-tool, 远程通讯

**需求场景 / 现象**: 用户只需要手机和 PC 通讯，协议本身（WebSocket）够用；外网的难点不是协议，而是 PC 在路由器 NAT 后、手机在外网找不到它，且 iPhone 装 PWA / 注册 Service Worker 必须 HTTPS。选定方案：Tailscale 私有网络 + `tailscale serve` 把本机端口转成 tailnet 内 HTTPS。不做路由器端口映射、不用 Funnel（服务当前无登录鉴权，暴露公网等于任何人可指挥本机 AI 读写文件）。

**方案 / 实施步骤**:
方案对比（用户问“必须 Tailscale 吗”时的结论）：①Tailscale：私有、免费、自带 HTTPS、无需公网 IP，代价是每台手机要装 App 并登录同一账号；②Cloudflare Tunnel：手机免装 App，但需自有域名且服务暴露公网，必须先加鉴权；③ZeroTier/WireGuard：自己配，HTTPS 另处理；④端口映射+域名+证书：需公网 IP，风险最大；⑤自建中继（PC 主动 WebSocket 连出到公网服务器，手机也连它）：不装 Tailscale，但需公网服务器、域名、证书和中继程序，且必须鉴权。无现成公网服务器时选 Tailscale。
【一、账号与网页端（一次性，需用户自己登录）】1. 用 Google 账号登录 login.tailscale.com，走完欢迎引导（用途选个人使用；“如何得知”可跳过），进入 Machines 页。登录由用户本人完成，不代输凭据。
1. 管理后台 DNS 页（/admin/dns）：MagicDNS 新账号默认已开启；HTTPS Certificates 点「Enable HTTPS...」→弹窗确认→提示 “HTTPS enabled”，按钮变「Disable HTTPS...」。弹窗说明：申请证书的机器名会写入公开证书日志且不可移除；机器名含 tailnet 名（随机化）用于混淆。这是账号级设置，操作前须用户确认。
【二、PC 端】1. 安装 Tailscale（tailscale.com/download）并用同一账号登录；`tailscale status` 应列出本机，`tailscale serve status` 初始为 `No serve config`。
2. 先启动 ai-tool 服务：仓库根目录 `.\scripts\start.ps1`（默认 8787）。
3. 执行 `tailscale serve --bg 8787`。输出 `Available within your tailnet: https://<机器名>.<tailnet名>.ts.net/ |-- proxy http://127.0.0.1:8787`，再 `tailscale serve status` 复核（显示 `(tailnet only)`）。关闭转发：`tailscale serve --https=443 off`。
4. 地址格式 `https://<机器名>.<tailnet名>.ts.net/`，机器名为 Windows 计算机名小写。
【三、iPhone / 其他手机】1. App Store 安装 Tailscale，用同一账号登录，允许添加 VPN 配置，保持开关打开，设备列表里应能看到 PC。
5. 用 Safari 打开上面的 https 地址（必须 Safari，才能「分享→添加到主屏幕」装 PWA）；此后从主屏幕图标打开即全屏。
6. 多台手机：每台外网使用的手机都要装 Tailscale 并登录同一账号，各自访问同一地址；会话和历史在 PC 上，多端共享并实时同步。给他人设备用时用 Tailscale「分享设备」或邀请进 tailnet，不要直接用自己的账号登录对方手机。
7. 在家同一 Wi-Fi 下仍可直接用局域网 `http://<局域网IP>:8787`（不装 Tailscale，但该 HTTP 地址装不了 PWA）；手机打不开时先查 Windows 防火墙是否允许 node.exe 访问专用网络。
【四、数据位置（用户问“对话记到哪、怎么看”）】全部在 PC：`~/.aitool/aitool.sqlite3`，表 sessions / messages / events / attachments / native_sessions（建表见 server/src/store.ts）；附件文件在 `~/.aitool/attachments/`；服务日志 `~/.aitool/server.log`、`server.error.log`。手机和浏览器只显示不存储。查看：在页面侧栏点会话即加载历史；或复制 sqlite 文件后用 DB Browser for SQLite 只读打开。库内为明文对话，备份分享需注意。Claude/Codex 各自的原生历史不在此库。

**验证方法**: `tailscale status` 显示本机在线、`tailscale serve --bg 8787` 输出与 `serve status` 均已实际读取；用户反馈 iPhone 线路走通。本次未做自动化测试，Service Worker 注册、serve 重启后保留、自动切换 Codex、审批弹窗仍待验证。tailnet 名、机器名、账号邮箱未写入本条，以本机 `tailscale status` / 控制台为准。

**踩坑 / 已知异常与失败经验**: 踩坑与风险：- 服务监听 0.0.0.0，tailnet IP 上的 HTTP 也可达；建议最终让服务只监听 127.0.0.1，外部只走 serve 的 HTTPS（局域网访问需另行取舍）。
- 服务本身无登录鉴权（单用户设计）：能进你 tailnet 的设备即可使用 AI；家里自用可接受，若共享给他人或改用 Cloudflare Tunnel/端口映射，必须先加访问令牌或登录。
- 外网使用要求：PC 开机、服务在运行、手机 Tailscale 开关打开。开机自启（PLAN G2）与 serve 配置重启后是否保留尚未验证。
- Service Worker 注册此前在内置浏览器里失败，需用 iPhone 的 HTTPS 地址再验证。
【原状态说明】已归档（部署与操作类知识；对应 PLAN 阶段 G3 的实测依据，docs/INSTALL.md 尚未写）

**关键文件与接口**: 原记录未记载（相关文件/接口见实施步骤与方案正文）

**状态**: 部分完成

### F-120: DYN-200 换普通 USB-RS485 线的兼容适配 (自动查找/记住线/兜底/握手重试)
**日期**: 2026-11-04
**项目**: driverSoftware (D:\code\driverSoftware), 分支 fix/dyn200-new-rs485-cable, 提交 593aad7b + c0d8f013 + 432e6954(文档)
**关键词**: DYN-200, 扭矩传感器, 换通讯线, USB-RS485, 真透传 dongle, Prolific PL2303GR, 067B:23A3, 6B6B:0001, 自动查找失败, 没找到 DYN-200 分析仪, 读到 0B, 总线无响应/波特率不对, discover_direct_fallback, dyn200_last.json, _OTHER_OWNERS, register_port_owner, 485 继电器, 兼容

**需求场景 / 现象**: 扭矩传感器通讯线从金钢分析仪(V1-CDC, VID:PID 6B6B:0001)换成普通 USB-RS485 线(Prolific PL2303GR, 067B:23A3)后, DYN-200 启动恒报「没找到 DYN-200 分析仪 (按 VID/PID 0x6B6B/0x0001 找)」, 手填端口(COM42)能通。另一次现象: 自动查找报「COM42: 读扭矩单位(0x0030)失败: 读到 0B, 期望 9B」, 再点一次又好。

**方案 / 实施步骤**:
方案 / 架构：- 记住线: 握手成功后把 (VID, PID, 序列号) 写 ~/.kingkong_driver/dyn200_last.json, 下次自动查找把它排在候选最前; 按身份不按 COM 号, 换口号也认得; 没有序列号不记。
- 兜底: 没有分析仪候选且无记住的线时, 对没被占用的 USB 串口各做一次只读握手, 最多 FALLBACK_MAX=4 个; 跳过分析仪、无 VID 的口、已被本进程别的功能占用的口; 全失败时报错带每个口的原因。
- 占用台账: server.py 把「485 继电器」也 register_port_owner, 兜底不碰继电器正开着的口。
- 握手重试: _read_cfg_u32 每项最多 CFG_READ_TRIES=3 次, 间隔 0.08s(只读, 无副作用)。
- 被否决/可选: 想更保守可去掉兜底只留「记住的口」, 代价是换新线第一次要手填。

**验证方法**: 真机 COM42(Prolific, 序列号 DPEAB111216, COM41 同型号但读到 0B 非传感器): 手填握手成功(小数点3位/量程10 Nm/单位Nm); 清记忆后 auto 兜底找到 COM42; 停后再 auto 走记住的口; 下线检测 /sensor/start 返回 fresh; 连续读数约 63 Hz、帧龄≤16ms、0 错误。dyn200 相关 135 条单测通过。

**踩坑 / 已知异常与失败经验**: 根因：1. 自动查找只认分析仪 VID:PID, 真透传 dongle 不在候选里。
1. 启动握手连读多项配置, 每项只试一次, 普通 USB-485 线偶发丢一帧就整次失败(总线实际是通的: 随后轮询 63 Hz、0 错误)。
踩坑：两个 COM 口(COM41/COM42)同型号时只有一个是传感器, 靠逐口握手区分; 页面显示「未启动」而后端其实在跑时, 先查 GET /api/dyn200/status 的 running。
限制：老分析仪路径(6B6B:0001)未在真机重测, 只有原有单测; 测试时空载 0.0 Nm, 加力后读数是否跟着变未验证; 「丢一帧」重试没有专门单测。
【原状态说明】已完成(未推送, 待并入 fix/field-feedback-batch)

**关键文件与接口**: - core/dyn200_sensor.py — LAST_PORT_PATH, _port_identity, _save_last_identity, _is_remembered, discover_direct_fallback, discover_candidates, start(), _start_one, _read_cfg_u32
- server.py — register_port_owner("485 继电器", ...), /api/dyn200/{start,stop,ports,status}
- tests/unit/test_dyn200_fallback.py — 6 条单测
- docs/skills/dyn200_sensor_link.md — 完整说明与排查表; AGENTS.md 模块必读表已挂入口

**状态**: 已完成

### F-121: dv3-admin 打包→GitLab CI→SSH 上传→浏览器下载 全链路（develop 分支，Windows Runner）
**日期**: 2026-11-05
**项目**: quality-testing/dv3-admin（GitLab 192.168.1.200:8888，项目 ID 159）
**关键词**: GitLab CI, .gitlab-ci.yml, deploy-agent-exe, build-agent-exe, PyInstaller, encoder-agent.exe, SSH_PRIVATE_KEY, File 变量, scp, ssh, Windows Runner, powershell executor, nginx, autoindex, artifacts, 10.0.64.2, autotest, 打包部署下载

**需求场景 / 现象**: 把 backend/local_agent 打成 exe，由 CI 自动上传到服务器，并能在浏览器里打开目录、点击下载。

**方案 / 实施步骤**:
方案 / 架构（全链路）：1. 触发：推送 develop，或在 GitLab 里对 develop 手动 Run pipeline（API：POST /projects/159/pipeline?ref=develop）。`.gitlab-ci.yml` 只在 develop 分支，master 上没有；job 的 only 写的是 main/develop/tags，默认分支叫 master 所以 master 不触发。
1. 打包：`build-agent-exe`（tag windows）在 Runner 上用 PyInstaller 生成 backend/local_agent/dist/encoder-agent.exe，artifacts 保留 30 天。Runner 是 DESKTOP-0AAVQN0（gitlab-runner 18.10.1，shell/powershell executor，以 SYSTEM 身份运行）。
2. 上传：`deploy-agent-exe`（needs build-agent-exe，自动取得 exe 产物）读 File 类型 CI 变量 SSH_PRIVATE_KEY，复制到临时副本并收紧权限，`ssh mkdir -p` 后 `scp` 到服务器 10.0.64.2 账号 autotest 的相对路径 backend/local_agent/dist，即 /home/autotest/backend/local_agent/dist/encoder-agent-<短SHA>.exe（同一提交重复部署会覆盖同名文件）。
3. 下载：服务器上用 nginx `location /dist/ { alias /home/autotest/backend/local_agent/dist/; autoindex on; add_header Content-Disposition "attachment"; }` 提供目录列表。10.0.64.2:8080 已被 MaxKB 占用，应换端口（建议 8081）。未配 nginx 时的替代：GitLab 里该 job 的 Browse artifacts，或 `/-/jobs/artifacts/develop/download?job=build-agent-exe`（需 GitLab 登录，保留 30 天）。
【前置条件】① GitLab 项目 CI 变量 SSH_PRIVATE_KEY（File 类型、Protected，值末尾留一个换行）；② develop 是受保护分支；③ 对应公钥已追加到服务器 autotest 的 ~/.ssh/authorized_keys；④ Runner 机器有 ssh/scp 且能连服务器；⑤ nginx 运行账号对 /home/autotest 路径有读权限（对各级目录 chmod o+x，对 dist 目录 o+rx）。建议给 CI 单独生成一对密钥，不复用个人密钥，私钥只放 GitLab 变量，不经聊天或仓库传递。

**验证方法**: 流水线 5686（推送 92ad00b8）及 5688、5689、5690（API 手动触发）build 与 deploy 均成功，deploy 日志有 `[deploy] upload OK`（build 约 27s，deploy 约 8s）。本地另用假私钥与桩 ssh/scp 在 PowerShell 5.1 中验证了私钥副本权限收紧、用后删除、残留自愈。

**踩坑 / 已知异常与失败经验**: 踩坑：见 P-20261104（私钥权限与残留文件）、P-20261105（中文提交信息破坏变量注入）。上传路径曾改过一次：旧目录 /home/autotest/deploy/encoder-agent 仍留有 encoder-agent-c5d71439.exe。
限制：nginx 下载入口只给出方案，未在服务器上落地、未验证；服务器目录内容未登录核对，只依据 job 日志；只测过一台 Runner、develop 分支，未测 tag 与 main；下载目录无认证；文件名带提交号会累积，无自动清理。
【原状态说明】打包与上传链路已验证（4 次成功）；浏览器下载入口待服务器侧落地

**关键文件与接口**: .gitlab-ci.yml（提交 bf88025d 起至 92ad00b8，deploy 阶段位于文件末尾）。

**状态**: 部分完成

### F-122: Encoder-next全功能对照P0及只读功能的副作用边界
**日期**: 原记录未记载
**项目**: 原记录未记载
**关键词**: **关键词**：EncoderPlotter, encoder-next, DD003, feature-parity, MES, IAP, 中值检测, 手动配置, 静态盘点

**需求场景 / 现象**: EncoderPlotter_0903_01 的encoder-next按DD003全功能替代，必须先区分真实可见功能、禁用占位和未挂载代码，避免用按钮或新WS存在推定旧HTTP已经兼容。

**方案 / 实施步骤**:
方案要点：
逐项稳定编号，字段模板展开；旧入口、实际命令或IPC/HTTP、本地/设备/外部副作用、可见条件、新实现证据并列。2026-11-08快照415项：43静态已实现、36部分、336未实现，17域，P1-P9覆盖；未挂载counter/clock、v-if=false CSV导入和HTTP501占位不计现网成功功能。手动配置会先上电再DataGet；确认配置可能刷新DefaultMoreOption。中值检测开始时写SN，再持续采集与保存，不能视为只读检测。旧批量升级仅有driver:batch-update事件，未发现components监听者，执行完整性未知。新图已有曲线/轴/轮播操作，独立离线窗口仍另验。

**验证方法**: 只读源码及20项静态抽样、独立复核无阻断；核对415行和分包覆盖。未运行测试/应用/服务、未连设备、未执行Git。静态实现不是全型号/真机验收；旧系统下线仍要逐条运行通过，写设备外部开放前必须有恢复证据。台账D:/sire/sire_ledger/runs/T-P0-20261108-codex。复用F-022的进程及标定/IAP产物背景，本轮行号以当前源码重核，不沿用历史测试成功。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: D:/code/EncoderPlotter_0903_01/encoder-next/docs/feature-parity.md为本轮交付；依据components/analyzer/selector.js:425、components/encoder/device.js:4922/4953、components/share/iap.js:513。22个生产写字段来自arguments-panel/index.js:16起白名单；MES有33固定配置字段和动态不良项映射，不记录凭据内容。

**状态**: 已完成

### F-123: Encoder-next P1查询供电恢复与真机SN未通过边界
**日期**: 原记录未记载
**项目**: 原记录未记载
**关键词**: EncoderPlotter, encoder-next, P1, BuildInfo, StartupInfo, SN, EncoderPower, 恢复出口, 默认拒绝, ER启动等待

**需求场景 / 现象**: EncoderPlotter_0903_01的encoder-next P1仅后端补齐构建信息、首次启动信息、按命令读SN和上下电，须保持外部默认边界并做真机恢复验证。

**方案 / 实施步骤**:
方案：端口→legacy/simulator→EncoderService→RPC/能力/契约，5个新方法及独立能力。RELEASE_CEILING和默认场景不变，内部宿主显式组装internal_policy；查询使用已读到的设备Arguments，不隐含探测。SN版本先拆三元组，4010不是大于422；Startup要求DPT15/RS485/4065/NoMulti。旧桥StatusSuccess还须检查内层status，empty SN与超时分开。上下电是模式变化；off/unknown禁止探测和起读、清缓存，上电作活动恢复出口；失败不自动重试；事件只报安全文字。

**验证方法**: 214单测通过、1既有警告，最终8.55秒。真机读取器20260420173117/COM3，DPT15/RS485/软件4.2.8/算法4060；构建信息在稳定等待后成功，Startup因4060正确拒绝；按命令SN按旧参数202/2.5M/none且等稳定仍HARDWARE_TIMEOUT，未通过，不得伪报empty或猜固件支持。供电前全参数/版本备份，off后新错误拒绝读数/探测，on后idle，回读参数/版本一致，读到EBAT帧。8783与COM3均已释放。前端/子仓/Git未动；SN真机及Startup成功路径仍需后续硬件/固件证据。本记录不替代全型号恢复验证，也不允许开放新外部能力。

**踩坑 / 已知异常与失败经验**: 原记录未记载

**关键文件与接口**: encoder-next/server/encoder_next/domain/encoder_queries.py、adapters/legacy/gateway.py、application/encoder_service.py、application/capability_catalog.py、tests/test_card_operations.py；任务回报docs/tasks/T-P1-readonly-ops.md。旧Encoder.py的BuildInfo/StartupInfo/ReadSerialNumber可直接经ServerBridge复用，不用改子仓。ER退出会复位；新自动查询太快会无应答，仅P1查询补0.8秒稳定等待，不能据此改默认probe/readout行为。

**状态**: 部分完成

### F-124: PostgreSQL 原地改名后重建容器连到另一数据卷：必须核对原卷绑定（Compose volumes.name / MES_POSTGRES_VOLUME）
**日期**: 2026-11-11
**项目**: MES / D:/code/mes
**关键词**: PostgreSQL, ALTER DATABASE RENAME, Docker Compose, 数据卷, OID, MES_POSTGRES_VOLUME, database does not exist

**需求场景 / 现象**: 六个项目数据库按环境用途改名。原地改名与摘要核对成功，随后更新部署编排并重建数据库容器，浏览器真实登录出现“服务器内部错误”，后端报新数据库 does not exist。

**方案 / 实施步骤**:
先恢复原数据卷绑定，不恢复 dump 覆盖。编排增加 `name: ${MES_POSTGRES_VOLUME:-${COMPOSE_PROJECT_NAME}_pgdata}`，已有环境 .env 明确写原卷名。更新编排前必须对比实际容器 Mounts 与候选配置，不只比较数据库连接串。备份与原始 OID 用于确认回到同一数据源。
1. 记录当前容器卷名与所有目标库 OID/所有者/ACL，停写后 pg_dump -Fc 并用 pg_restore --list 校验。
2. 在 postgres 系统库连接下终止限定目标库连接，ALTER DATABASE 原地改名；逐库比较 OID/权限/表行数和内容摘要。
3. 保持原卷名，更新运行、迁移、备份、恢复、初始化、测试白名单。Compose config --quiet 验证后重启后端与网关。
4. 通过真实浏览器登录两端并加载已有记录；登录后再次核对业务数据摘要，正常会话与审计变动单独识别。

**验证方法**: 本次六库 OID 与原始一致，改名时所有表摘要一致；登录后业务记录6545行、模块23行内容摘要仍一致。两端真实账号重新登录并正常加载后台模块及业务列表，截图留证。Compose配置、Shell/MJS语法检查通过。

**踩坑 / 已知异常与失败经验**: 实际部署编排为 pgdata 显式指定旧卷名 mes-test-pgdata，仓库编排未指定 name，覆盖后 Compose 按项目生成 mes-test_pgdata，连接了另一卷。数据库改名操作本身成功，但容器数据来源被改变。
不要假定同一个Compose项目名就能保持旧卷，已有部署可能显式绑定另一名称。健康检查成功不代表业务库正确，更不能替代实际登录。只读核对发现误接后应恢复原卷，不向另一卷导入覆盖，也不删除任何卷。

**关键文件与接口**: - deploy/docker-compose.yml 的 volumes.pgdata.name；deploy/.env.example 的 MES_POSTGRES_VOLUME。
- docs/DATABASES.md 记录环境用途、连接路径和原卷约束。
- pg_database.oid、datdba、datacl 以及逐表 count 和内容摘要。

**状态**: 已完成
