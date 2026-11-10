# 知识记录（数据库导出副本）

> 由 `sire_kb.py export-md` 生成，数据库 knowledge_records 为正式来源；请勿手工编辑，修改请走 `sire_kb.py add` 或原始 md。
> 生成时间: 2026-10-25 22:56，共 115 条

#### E-007: 先确认发布构建归属，避免在本地误跑长构建

**类型**: E  **来源**: @USER_HOME@\sire_global\global_dev_efficiency.md
**关键词**: SIRE, 发布, CI Runner, tag, 本地构建, 效率, release.py

**日期**: 2026-09-20
**项目**: driverSoftware

**经验**:
发版前先读 `.gitlab-ci.yml` 的 tag 规则和 Runner job；如果正式产物已由 tag 触发 Runner 生成，本地只执行版本校验和 tag 流程。长时间本地构建被用户纠正时，应立即停止、检查 bump 是否留下半成品，并把默认入口改成 CI，保留显式本地预检参数。

**验证**:
`release.py --help` 已显示默认 CI Runner 路径和 `--local-build` 预检；发布单元测试 14 passed。

**关键词**: SIRE, 发布, CI Runner, tag, 本地构建, 效率, release.py

#### F-004: 高低温箱功能影响范围分析

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: chamber, 高低温箱, temperature, humidity, Modbus, 独立进程, 同步采样, EncoderPlotter

**日期**: 2026-07-16
**项目**: EncoderPlotter_0703_02
**需求编号**: F-004
**需求标题**: 分析高低温箱功能在代码库中的实现方式和影响范围
**关键词**: chamber, 高低温箱, temperature, humidity, Modbus, 独立进程, 同步采样, EncoderPlotter

#### 架构设计要点
- 独立 Python 子进程 (main.py --chamber)，不与编码器共用 stdout 通道
- JSON 行协议通讯，一行一条请求/响应
- 自动扫描串口时排除编码器分析仪占用的串口，避免端口冲突

#### 核心影响模块
- controller/chamber.js: 进程管理、JSON 请求路由、超时控制
- components/encoder/device.js: 面板切换、双模式采样、数据对齐、导出清理（影响最大）
- components/encoder/multiReadoutChart.js: 温湿度虚拟曲线，Y轴固定范围防抖动
- controller/python/sub_automation/Chamber.py: connect/read/close 命令分发
- controller/python/sub_automation/ChamberModbus.py: Modbus RTU 驱动

#### 数据流转关键路径
高低温箱设备 -> Modbus RTU (寄存器7991=温度, 7992=湿度) -> Python驱动解析 -> JSON响应 -> 面板实时值(1s低频) 或 编码器同步采样(chamber.frequency频率) -> 内存samples数组 + jsonl磁盘缓存 -> 独立CSV导出

#### 对编码器主流程的影响
- 读取开始: 启动同步采样 + 清空前一轮缓存 + 触发图表重绘
- 读取进行: 按频率采样，通过 dataIndex 与编码器数据对齐
- 读取停止: 停止高频采样，恢复低频状态刷新
- 页面销毁: 主动释放进程和定时器，避免资源泄漏

#### 通讯协议 (Modbus RTU)
- 从站地址: 0x01，功能码: 0x03 (Read Holding Registers)
- 寄存器 7991: 温度（有符号16位整数 / 10）
- 寄存器 7992: 湿度（有符号16位整数 / 10）
- 响应帧: 7字节 (SLAVE_ID + FUNC + LEN + DATA*2 + CRC*2)

#### 重要区分
components/encoder/dataParser.js 中的 temperatureBuffer 是编码器自带温度（RS485协议AngleWithTemperature命令），不是高低温箱数据。高低温箱数据保持独立采样流，不进入 encoder binary data。

#### 后续修改记录
- 修改1 (2026-07-16): 霍尔模式 H 命令 ACK 末尾增加 1 字节状态位
  - 文件: components/mixins/configsMixin.js
  - 修改 timeoutByteNum + 1
  - 增加状态位 resolver: V.getUint8(偏移)
  - 不改变之前霍尔值和角度值的偏移量

---



---

## 2026-07-16 | EncoderPlotter_0703_01

### 1. DPTv411 固件升级（R001, R002）

- **分支**: origin/test/iap-from-401-to-411
- **升级配置**: 401 (algorithmVersion=4020, supported=[401,402,403,410,411]) → 411 (algorithmVersion=4027, supported=[401])
- **数据地址**: outer (angleData 0x08012800, polyfits 0x08013000); inner (angleData 0x08012834, polyfits 0x08029800)
- **算法子模块 commit**: 58fd57148e97384d18729c71fab4d27ddd86f032
- **TODO**: 保留讨论结果，后续与项目经理沟通

### 2. Hall 采集频率优化（R003, R004）

- **分支**: 
eature/speed-up-hall-collecting-frequency
- **最大采样率公式**（DPT，4Mbps）：rate = 1_000_000 / (2.5 × (reader_response + cmd 2 + device_response + data 38 + timeout 5)) ≈ 7_272 Hz
- **TODO 1**: UI 上做开关区分【高速采样】与【普通采样】
- **TODO 2**: 套用公式估算高速采样频率并显示

### 3. 过程文档

- 位置: ~/sire_global/projects/EncoderPlotter_0703_01/docs/R001-R004_process.md
- 本地备份: @CODE_ROOT@\EncoderPlotter_0703_01\docs\sire\R001-R004_iap_411_hall_freq_process.md
"@

# 2. 更新 global_problem_solutions.md
 = @"


---

## 2026-07-16 | P001 DPTv411 降级路径未确认

- **问题描述**: 411 的 supportedVersions=[401] 表示 401 能升级到 411，但 411→401 的降级回退路径未在配置中声明，不明确。
- **影响范围**: IAP 固件升级回退流程
- **责任人**: 项目经理
- **当前状态**: 待确认
- **建议方案**: 在升级配置中添加 downgradeVersions 字段，或明确注释不允许从 411 回退

## 2026-07-16 | P002 采样率公式建议参数化

- **问题描述**: R004 采样率估算公式中，波特率、响应时间、指令/数据/超时字节数当前以 DPT 产品为例硬编码，其他产品线可能不同。
- **影响范围**: feature/speed-up-hall-collecting-frequency 功能扩展
- **责任人**: 开发
- **建议方案**: 将上述参数抽取为产品级配置表，避免硬编码
---

#### F-005: 加密模块分析（程序加密 vs 分段加密）

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: encryption, 程序加密, 分段加密, IAP, AES, RSA, Protector, BootLoader

**日期**: 2026-07-17
**项目**: EncoderPlotter_0703_02
**需求编号**: F-005
**需求标题**: 分析程序加密和分段加密的实现方式和区别
**关键词**: encryption, 程序加密, 分段加密, IAP, AES, RSA, Protector, BootLoader

#### 程序加密 (encrypt_file)
- 算法：RSA + AES-256-CBC + RSA 数字签名
- 入口：EncoderCommandIapEncryption (61) → Protector.encrypt_file()
- 每次随机生成 AES-256 密钥，RSA 公钥加密传输
- 输出格式：[RSA加密密钥(256B)][IV(16B)][密文][签名(256B)]
- 用途：文件分发/存储加密，解密方持有 RSA 私钥

#### 分段加密 (encrypt_file_aes_v2/v3)
- 算法：固定密钥 AES-128-CBC + 分包 + CRC8 校验
- 入口：EncoderCommandIapSegmentedEncryption (63) → 先检测 BootLoader 版本
- 固定密钥硬编码：\xa3\xa3FA\x91G\x19c\n:;\xf4\xf7\x1d\xd3\xac
- V3: 每 256 字节直接加密 → [长度(4B)][加密包][CRC8(1B)]
- V2: 先包装内部包 [序号(2B)][长度(2B)][数据][CRC8(1B)] → 再加密
- 用途：IAP 固件烧录，设备端逐包解密烧录

#### 核心差异
- 密钥：随机 vs 固定
- 粒度：整文件 vs 256B分包
- 校验：RSA签名 vs CRC8逐包
- 场景：文件分发 vs IAP固件升级

#### 涉及文件
- controller/python/sub_common/Protector.py（加密核心）
- controller/python/Encoder.py（命令入口）
- components/share/iap.js / iap.html（前端触发）
- controller/python/sub_common/Defines.py（命令码定义）

#### 过程文档
- ~/sire_global/projects/EncoderPlotter/docs/R001_encryption_analysis.md

---

#### F-006: 读取模式数据自动保存（时间戳目录）功能

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: Electron, Vue2, Vuex, 设置弹窗, 目录选择, 时间戳目录, 数据持久化, 读取模式, bin文件复制, i18n双语

**日期**: 2026-08-12
**项目**: EncoderPlotter_0703_01
**需求编号**: R001-R011
**需求标题**: 设置中新增【是否保存读取模式数据】选项，开启后每次读取自动将采集数据保存到时间戳目录

**关键词**: [Electron, Vue2, Vuex, 设置弹窗, 目录选择, 时间戳目录, 数据持久化, 读取模式, bin文件复制, i18n双语]

---

#### 需求描述
```
设置当中增加一个选项【是否保存读取模式数据】：
1. 如果打开，显示一个选择目录的操作，可以指定任意目录，默认为全局的log目录
2. 如果这个开关打开，每次读取的时候，在选择的目录下创建一个以时间戳为名字的目录（例如20260812-102800），作为后续将采集到的数据存盘的路径
3. 如果没有开启这个选项，保持当前逻辑（使用临时目录temp，不清用户配置）
```

---

#### 验收标准
- [x] preferences新增 saveReadoutData: { enabled: false, directory: '' } 字段
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

---

#### 技术方案
**架构决策：双写策略（先写temp，stop时复制）**
- 原因：Encoder类内部 saveData() 硬编码写 window._tempPath，且 dataContinuousStartMultipleCommands() 无saveDir参数
- 权衡：修改 Encoder 类将超出device.js单文件修改约束，且影响范围不可控
- 因此：读取过程中编码器bin仍写temp（原有路径），chamber采样边写边写入新目录（自己控制的fs.appendFile），stopReadout时等所有saveData完成后把temp中的 .bin / .chamber.jsonl 通过 fs.copyFile 复制到时间戳目录
- 关键保障：startReadout时始终清空temp，保证copy不包含上一轮遗留文件

**目录创建与生命周期**：
```
createTimestampedSaveDir() 仅当 enabled=true 时执行：
  baseDir = directory || window._logsPath
  timestamp = window.timeStr()  ->  YYYYMMDD-HHMMSS
  targetDir = path.join(baseDir, timestamp)
  fs.mkdir(targetDir, { recursive: true })
  this._currentSaveDir = targetDir  // 组件实例属性，非响应式非持久化
  finally: stopReadout 执行完毕后 this._currentSaveDir = undefined
```

**修改的函数清单（device.js）**：
| 函数 | 修改类型 | 说明 |
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

---

#### 涉及文件
| 文件 | 修改内容 | 关键行 |
|------|---------|-------|
| components/global.js | preferences新增saveReadoutData字段 | L190-L193 |
| components/analyzer/version.html | 新增2个setting-item（开关+目录选择） | L77-L90 |
| components/analyzer/version.js | 本地变量/写回/初始化/chooseSaveReadoutDataDir方法 | L39-L40, L286-L287, L327-L328, L342-L356 |
| components/i18n.js | 新增9个翻译键 en+zh 双语 | L413-L421(en), L988-L996(zh) |
| components/encoder/device.js | 新增2方法 + 修改7方法的路径切换逻辑/async改造 | L819, L892-L1124, L2284-L2289 |

---

#### 关键决策与理由
| 决策项 | 选择 | 理由 |
|--------|-----|------|
| 数据保存策略 | 先写temp+stop复制 | Encoder.saveData硬编码写temp，不能改底层类 |
| chamber写策略 | append直接写时间戳目录 | chamber缓存由我们自己写fs.appendFile，可直接改路径，崩溃时也有备份 |
| clearBinFiles开关开时 | 始终清空 | 否则上次遗留.bin会被copyFile污染新目录（测试发现的关键bug） |
| 目录变量存储 | this._currentSaveDir实例属性 | 纯临时状态，无需Vuex持久化，下次读取会被createTimestampedSaveDir覆盖 |
| 设置弹窗变量 | 本地临时变量+关闭时写回 | 与localMesEnabled/localAdmin模式一致，避免直接改全局状态时异常 |
| 目录为空时回退 | window._logsPath | 需求明确指定默认日志目录 |
| 异常处理策略 | try-catch记录warning，不阻塞主流程 | 目录创建/复制失败不应影响读取功能正常运行 |
| stopReadout async改造 | Promise.all等待所有saveData | 确保文件落盘后再复制，否则可能得到0KB文件 |

---

#### 翻译键清单（9个，en/zh双语）
| Key | English | 中文 |
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

---

#### 边界场景验证结论（全部通过）
| 场景 | 行为 |
|------|-----|
| enabled=false（从未开） | 完全走原temp逻辑，无任何副作用 |
| enabled=true, directory='' | 正确回退到window._logsPath |
| enabled=true, 自定义目录 | 正确使用自定义目录创建时间戳子目录 |
| 读取中崩溃关闭应用 | _currentSaveDir为组件属性，下次重建组件时自动重置，无脏值 |
| mkdir权限不足/磁盘满 | try-catch返回undefined，正确回退temp |
| 多编码器同时读取 | stopReadout多设备循环-统一copy一次temp目录所有bin，正确 |
| 开始新读取-旧bin清理 | clearBinFiles始终清空-copy源干净-新目录无污染 |
| 开关打开-导出数据 | exportData正确识别_currentSaveDir-从新目录导出 |

---

#### 技术债务清单
1. 冗余方法：getReadoutDataSaveDir()未被所有分支直接调用，可后续统一改为调用该方法
2. 串行copyFile：stopReadout中复制文件使用串行for循环，可用Promise.all并行（文件数通常<10）
3. 原有写法不规范：version.js:310-311的this.systemIntegration写法（非本次引入）

---

#### SIRE执行记录
- 角色1：需求拆解 8项 - 角色2校验合并为11项明确需求清单
- 并行开发：组A（global.js/version.html/version.js/i18n.js）+ 组B（device.js），文件集完全不相交，无冲突
- 审查结果：通过（功能全覆盖）
- 测试后修复2个bug：clearBinFiles开关开时跳过导致数据污染；startChamberReadout缓存清理硬编码temp路径

---

#### F-007: IAP升级移除SN格式校验（保留必填）

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: IAP升级, SN序列号, 格式校验移除, 必填校验, Vue2, i18n, placeholder

**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**需求编号**: R001-R002
**需求标题**: IAP升级不需要校验SN的录入规则，但是需要录入SN

**关键词**: [IAP升级, SN序列号, 格式校验移除, 必填校验, Vue2, i18n, placeholder]

---

#### 需求描述
```
IAP升级不需要校验SN的录入规则（原格式：3个字母+3个数字），但SN仍需录入（必填）。
```

---

#### 验收标准
- [x] 移除 startIAP() 中 SN 格式正则校验 /^[a-zA-Z]{3}\d{3}$/ 及"SN格式错误"报错
- [x] 恢复（取消注释）SN 必填校验：为空时报"请输入编码器SN"并 return 阻止升级
- [x] SN 传递链路不变：handleIap() 中 options.sn = this.iap.sn -> EncoderCommandIapStart(命令码60)
- [x] 升级成功清空SN / 失败保留SN（重试匹配）的原有生命周期不变
- [x] iap.html placeholder 去除旧格式示例"如 abc123"误导
- [x] i18n 中英文区新增 "SN": "SN" 键

---

#### 技术方案
| 项 | 说明 |
|----|------|
| 修改位置 | components/share/iap.js startIAP() L266-272 |
| 必填判断 | if (!this.iap.sn) 报错 return（空串/null/undefined 均拦截） |
| 校验顺序 | iap文件(L258) -> SN(L266) -> 目标版本(L275)，逐级短路 |
| 旁证 | device.js:3206 validateSN() 此前已被产品确认改为 return true（方向一致） |

---

#### 涉及文件
| 文件 | 修改内容 | 关键行 |
|------|---------|-------|
| components/share/iap.js | 恢复SN必填校验（取消注释原L266-272），删除SN格式正则校验（原L274-281） | L266-272 |
| components/share/iap.html | placeholder 从 $t('SN (如 abc123)') 改为 $t('SN') | L36 |
| components/i18n.js | 英文区L618、中文区L1335各新增 "SN": "SN" | L618, L1335 |

---

#### 关键决策与理由
| 决策项 | 选择 | 理由 |
|--------|-----|------|
| 必填校验实现 | 恢复原注释代码而非新写 | 原代码逻辑正确，恢复即最小改动 |
| i18n旧文本 | "SN格式错误..."翻译键保留未删 | 避免影响潜在引用，无副作用 |
| 不加trim | 纯空格" "可通过 | 超出用户需求范围，记录为技术债务 |

---

#### 测试结论
- node --check iap.js / i18n.js 均 exit 0
- 4项预期行为推演通过：SN空-拦截；SN任意内容-放行；文件未选-报错；版本未选-报错
- SN传递链路确认完好（handleIap L125 -> encoder.set L151）

---

#### 技术债务清单
1. 纯空格SN（" "）可通过必填校验，建议后续 if (!this.iap.sn || !this.iap.sn.trim()) 加强
2. SN含特殊字符时后端/固件兼容性未验证，建议联调补测

---

#### SIRE执行记录
- 角色1：定位 startIAP() 为核心修改点；角色2：确认R001/R002同文件，跳过角色4并行
- 角色3：单处修改；角色5：审查通过（格式校验无残留、传递链路完好）
- 角色6：测试通过；④.5轻微修复：placeholder文案与i18n
- 角色7：交付确认通过

---

### F-007 补充修订: 纯空格SN拦截

**日期**: 2026-08-28
**修订内容**: F-007 技术债务#1 已修复。components/share/iap.js startIAP() L266 必填校验由 if (!this.iap.sn) 加强为 if (!this.iap.sn || !this.iap.sn.trim())，纯空格SN（" "）现被正确拦截报"请输入编码器SN"。
**安全性**: !this.iap.sn 短路在前，null/undefined 不会调用 .trim()，无 TypeError 风险；含实际内容的SN（如" abc "）仍放行并按原样传递。
**验证**: node --check exit 0。

---

#### F-008: IAP升级进度专用progress_sender参数贯通

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: IAP, 升级进度专用, progress_sender, 参数贯通, Encoder.py, IAP.py

**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**需求**: IAP升级增加专用于显示上传进度的方法，不覆盖msg_sender，独立参数传递

**传递链**: Encoder.py stepTwo progressSender(=msg_sender) -> lambda闭包 -> uploadApp(progress_sender) -> uploadAppDataV1/V2(progress_sender) -> [IAP_PROGRESS:xx]消息行

**修改**: Encoder.py L363/L376 lambda加progress_sender=progressSender；IAP.py uploadApp/uploadAppDataV1/uploadAppDataV2签名加progress_sender=None+回退msg_sender（兼容）；两处[IAP_PROGRESS]进度行改用progress_sender，msg_sender其他用途（错误/状态消息）不变

**关键决策**: progress_sender默认None回退msg_sender，所有旧调用方行为不变；进度消息与普通日志分离，后续前端可单独消费

---

#### F-009: IAP失败清除SN+重试通道SN自动还原

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: IAP, 失败清除, SN, 重试通道, 自动还原, iap.js

**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**需求**: IAP失败时清除SN（输入框清空）；重试不校验SN，SN自动还原

**修改**（components/share/iap.js）:
1. handleIap catch分支：失败时 this.iap.sn = null（原注释"失败保留SN供重试比对"的机制废弃）
2. 重试按钮click：删除SN比对校验（原"设备序列号不匹配"拦截逻辑），改为 if (message.data.sn) this.iap.sn = message.data.sn 从flow-control消息还原SN

**设计逻辑**: 失败清SN（UI强制清空，防操作员误用旧SN）→ 重试时后端flow-control消息携带sn自动还原 → handleIap options.sn带正确值重试 → 重试失败再清空（可循环重试）。仅更新app模式（message.data.sn为空）不还原，options本就不传sn，不受影响。

**验证**: node --check通过；5场景推演自洽（首次失败/重试/循环重试/updateAppOnly/成功）

---

#### F-010: 导入调试数据【使用当前配置】覆盖 + 绘图方式默认后端

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: 导入调试数据, 使用当前配置, 覆盖, 绘图方式默认后端, global.js, device.js, Encoder.py, store默认值global.js

**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03

**功能1：使用当前配置（仅内部版）**
- UI: 绘图方式下方开关，？提示"打开之后，导入调试数据的时候，将使用当前页面的配置信息覆盖文件里面的配置信息"
- 链路: global.js useCurrentConfig状态 -> device.html开关 -> device.js modes下发(外部版强制false) -> Encoder.py _prepareRecalibrationArguments
- Python关键实现: jsonData被文件内容替换前快照外部配置(_externalJsonData)+读取标志 -> 文件加载后 if _useCurrentConfig: jsonData.update(外部配置) -> debug/write仍强制False(安全项) -> plot(内部版)/plotRenderMode始终以外部的为准
- 配套日志: logging.info打印配置来源(页面覆盖/调试文件)+生效配置JSON，便于追溯

**功能2：绘图方式默认后端**
- 移除localStorage持久化(mounted恢复+toggled保存)，每次启动重置为backend
- store默认值global.js plotRenderMode: 'backend'

**验证结论：导入调试数据与编码器零交互（保持原逻辑）**
- isReadFromFile()门控: getEncoderData跳过self.enter()，所有数据getter(getDPTHallParamOuter等)从调试文件读取
- debug/write在覆盖后仍强制False -> 不写编码器
- setProxyProtocol仅设本地标志(proxyProtocol/canOpenProxy.setLog/setIsFD)，无总线I/O
- 覆盖仅改配置值不改控制流，交互保证来自既有门控

#### F-011: EncoderPlotter 国际化(i18n)全面修复

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: EncoderPlotter, 国际化, i18n, 全面修复, 涉及mes-config.js, device.js, iap.js, i18n.js, 正则提取全部.js, threshold.html, selector.html, flash_tool_v2.py

**日期**: 2026-09-02
**项目**: EncoderPlotter_0703_01

**问题模式与修复方案**（i18next，key为中文，en/zh双包，fallbackLng='en'）：
1. **双包缺失key**（代码用$t但包中无，en模式显示中文）：补en/zh双包约102个key。覆盖：设备消息、threshold.js阈值提示7条、selector.html读取器配置5条、device.html设备面板9条、serialPermissionNotice.js串口权限11条、HTML硬编码改造30+条
2. **动态key拼接**（$t("前缀"+变量)或模板字符串，永远匹配不到包内key）：改为静态key+插值。涉及mes-config.js:330、device.js:3149、iap.js:68，语言包值加{{fields}}/{{oldSerial}}/{{step}}占位符
3. **JS对象重复key**（后者静默覆盖前者）：清理13处。典型：en包"读取字长"重复导致selector.html显示"Readout Byte Length: "空插值
4. **en/zh包key不一致**：zh包key多一个"和"字导致中文模式fallback英文（违反"中文模式不得显示英文"硬约束）；en包缺"解析名称"导致英文模式显示中文
5. **插值参数丢失**：代码传{port}/{name}但翻译值无占位符，信息被吞
6. **HTML硬编码中文**（英文模式显示中文）：6个HTML文件约50处改$t()（部分位于HTML注释块内，无害且解除注释即i18n就绪）
7. **窗口标题硬编码**：main.js按resolvedLanguage切换中英文标题

**验证方法**（可复现）：临时Node脚本模拟window后require components/i18n.js，用getResourceBundle('en'/'zh','translation')取双包：(a)key集合差集比对 (b)正则提取每个包区域源码检测重复key (c)正则提取全部.js/.html的$t('静态key')逐一验证双包存在 (d)t()传参验证插值输出。注意：HTML中$t('...\n...')的\n运行时由JS解析为换行，与包内解析后key一致，源码文本级比对会假阳性。

**技术债务**：threshold.html:93的$t('')空key（无显示危害）；device.js后端动态msg（已有zh/en三元机制）；selector.html:527的$t(unit)动态单位；注释块内$i18n改造待解除注释后生效。

## 2026-09-03 | flash_tool_v2.py 增加步骤级操作日志

- 需求: 用户需要看到烧录V2流程执行到哪一步（此前中断时只有 traceback，无法定位）
- 实现: 新增 stepLog(name)/stepDone() 两个 helper（模块级 _currentStep/_stepStartTime 追踪）
  - stepLog: 进入新步骤时输出 [步骤名] 开始 并计时
  - stepDone: 输出 [步骤名] 完成，耗时 X.Xs
- 接入点: 初始化.编码器连接 / step0.压合电磁阀 / step1.解锁芯片加载calibration / step2.采集数据(或从文件加载) / step3.partition / step4.calibration / step5.评估 / step6.生成CFiles / step6.1.写入Flash(子步骤)
- 异常中断: except 分支输出 流程异常中断于 [当前步骤名]，精确报告中断位置
- 验证: py_compile 通过; 冒烟测试(-3 -f 不存在文件)确认输出 [step2.从文件加载数据] 开始 → 流程异常中断于 [step2.从文件加载数据]
- 日志经 logger(stdout) → Node onProgress 转发到前端面板，UI 可实时看到步骤进度

## 2026-09-03 | flash_tool_v2.py 主流程完整参数日志

- 需求: 用户需看到每一步拿到了哪些参数、每个步骤调用传入了哪些参数
- 实现:
  1. 入口总览块（argv / startIndex 解析结果 / 双轴标志 / 全部关键 config：serial/version/algorithmVersion/model/批次/isAuto/PLLSource/OutputMode/PROJECT_NAME/传感器/三大路径 / skip-generate、no-write-flash flags）
  2. 每个调用点前置日志: 调用 X.main(参数=值, ...)；返回值打 OK/None 或 shape 摘要
  3. _ds_desc 统一在 step2 后定义（避免 -4/-5 启动跳过 step3 时 NameError）
- 覆盖调用点: Analyzer()/EncoderBase()/powerOn()/recail.enter()/sol.main/load.main/collect.main/partition.main(内外圈)/calibrate.main(内外圈)/evaluate.main(内外圈)/generate.main/recail 写入系列
- 验证: py_compile 通过; -3 --skip-generate 冒烟运行，入口总览与各步传参日志完整输出
- 遗留发现: finally 中 encoder.recail.exit() 报 'Recalibration' object has no attribute 'exit'（仅 warning 不阻塞，待修）

## 2026-09-03 | 界面转子内径自动匹配 station.py 传感器配置

- 需求: station.py 的 InnerConfigs/OuterConfigs 固定为 Configs15/Configs20，需按界面选择的内/外转子内径自动匹配 configMBP.ConfigsN
- 实现（三处）:
  1. flashPanelV2.js: flashFirmwareV2 调用传 innerSize=modelConfig.innerRotorId, outerSize=modelConfig.outerRotorId（'15'/'15B' 等原始值）
  2. factoryAutomation.js flashFirmwareV2: 转发为命令行 --inner-size / --outer-size
  3. flash_tool_v2.py _applyRotorSizes(argv)（在 import config 之前执行）: 解析参数取数字（'15B'→15），行锚定正则改写 station.py 的 InnerConfigs = configMBP.ConfigsN 单行（兼容 GUI 行锚定正则），N<10 补零（5→Configs05）
- 关键时序: 改写必须在 import config 之前——station.py 是磁盘配置，import 后值固化到 config 命名空间
- 验证: --inner-size 10B --outer-size 15 → station.py 两行被替换、config 导入 Inner=10/Outer=15 PASS；测试后已还原 15/20
- 边界备注: DPT5 特例 Configs10_DPT5 不在通用规则内（保持手改）；单轴系列 Inner=Outer 别名同样保持手写

## 2026-09-03 | 界面可选 hex/IAP 固件文件（覆盖默认 JFlash 路径）

- 需求: IAP/hex 文件应从界面选择，而非固定用 JFlash 默认路径
- 实现（三层）:
  1. flashPanelV2.html: 新增"APP 固件 (hex)"与"IAP / Bootloader (hex)"两个文件选择组（选择/清除按钮，样式同数据文件选择）
  2. flashPanelV2.js: data 加 hexFilePath/iapFilePath（localStorage 持久化），selectHexFile/selectIapFile/clearHexFile/clearIapFile 方法（ipcRenderer select-file，hex 过滤器），flashFirmwareV2 传 hexFile/iapFile
  3. factoryAutomation.js: 转发为命令行 --hex / --iap
  4. finalstep0_loadHex.py main(): _argValue('--hex'/'--iap') 解析后用 dataclasses.replace 生成新 cfg 覆盖 hex_path/extra_hex——replace 而非直接赋值，避免污染模块级共享配置表（跨调用残留）
- 不选时行为不变：使用 _SERIES_SPEC 规格表默认 JFlash 路径
- 验证: --hex/--iap 实测路径正确生效、烧录上下文日志正确显示覆盖后路径、共享表前后一致；且验证运行时第2次尝试烧录实际成功（探头已接）

## 2026-09-03 | flash_tool_v2 代码审查重构 + collect_v2 COM口自动扫描

- 审查发现并修复:
  1. 重复 stepDone: step6.1 内部与 step6 块尾各打一次（_currentStep 已变 step6.1，重复输出）→ 只保留块尾
  2. 三段重复 Flash 写入 try/except（4060 两项/旧版三项结构相同）→ 抽 _writeFlashData(encoder,res) helper，items 按算法版本构造
  3. heights 死变量（定义后无引用）删除
  4. numpy/pathlib import 散落在流程中间 → 提顶部
  5. res None 且 encoder 连接时无日志 → 补 warning
  6. stepLog 后紧跟同文本冗余标题行全部删除（stepLog 已输出 [name] 开始）
- COM26 写死问题（用户要求自动扫描）: finalstep0_collect_v2.py 的 PORT="COM26" 改为 _resolvePort()——--port 显式指定 > VID(0x6B6B)/PID(0x0001) 自动扫描；延迟到 collect() 内解析（模块导入不碰串口，-f 文件加载场景设备未插不炸 import）
- 'Analyzer' object has no attribute 'server' 修复: EncoderBase.py newMsg()/messager() 加 getattr(self.analyzer,'server',None) 守卫，无 server 时降级 logging.info 输出——单机模式（产线烧录脚本直接用 Analyzer 无 WebSocket Server）下 enter() 不再被消息推送炸掉，报错回归真实硬件原因
- 验证: py_compile 三文件通过; -3 -f 不存在文件 冒烟——日志无重复、server 错误消失（显示真实原因: Enter Recalibration Mode Failed 请查接线）

## 2026-09-03 | 采集过程逐帧日志从界面日志框移除

- 需求: 采集过程（finalstep0_collect_v2 链路）的逐帧调试日志不需要显示到界面
- 来源定位: AnalyzerDual.py 四处逐请求/逐帧 logging.info（Request.received 打数据、addRequest 打请求ID、readThread 打包长、sendCommand 打 'pass'）+ readThread 逐帧 print(triggerData) + Recalibration 调试 print('vdata'/'getting')
- 修复: 全部删除（纯调试残留，无逻辑作用）；resolvepackages 解析校验保留
- 效果: 界面日志框采集期间只剩 stepLog 步骤行与 collect.main 返回摘要，不再被 1/8/b'..'/pass 刷屏

## 2026-09-03 | _connect_encoder 职责拆分：连接与进入再标定解耦

- 需求: 连接读取器不必每次都进再标定，是否进入跟场景相关
- 实现: _connect_encoder(enter_recali=True) 参数化——函数只负责 连接+上电+串口校验
  - 初始化阶段 enter_recali=True（默认）：烧录前固件在跑，需再标定态
  - 采集后重连 enter_recali=False：采集驱动退出时已让固件离开再标定；step6 写 Flash 前 ensureInRecalibrationMode() 自会按需进入，无需重复

## 2026-09-03 | 烧录V2 界面：先选产品系列再选固件版本

- 需求: 交互顺序应为 先选择产品系列 → 再选择固件版本（版本随系列联动）
- 实现:
  1. flashPanelV2.html: 产品类型上移到第一位，固件版本紧随其后（原版本在最顶部）；版本下拉在 optVersions 为空时禁用并提示"请先选择产品类型"
  2. flashPanelV2.js 'modelConfig.version' watcher 加校验: 版本不在当前系列 versions 内（localStorage 残留旧系列值）时重置为 default_version 并 return（重置值再次触发 watcher 完成后续联动）
- 既有联动保持: 切系列 watcher 已置 version=default_version；optVersions 本就按 seriesMeta.versions 生成

## 2026-09-03 | step6 写入过程说明与 startProcessAngle finally 修复

- 用户疑问: step6 缺少往编码器写入数据的过程（ANGLEDATAS/POLYFITS/SLOWPOLYFITS）
- 说明: 写入过程未丢——重构时抽入 _writeFlashData(encoder,res) helper（flash_tool_v2.py L184），主流程 L547 调用；内容与 finalstep_from_data.py 逐行对应
- 修复（对照参考文件的差异）: startProcessAngle() 从成功路径末尾移入 finally——写入中途异常也恢复角度处理，否则固件停留在 stopProcessAngle 状态（参考实现正是放在 finally）
- 备注: 用户已手改 output_mode 默认值为 'bytes'（原 config.OutputMode）

#### F-013: 从 origin/develop 干净重合并 MPT-G QGC 并补齐 V402 配置

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: MPT-G, MPT-QGC, V402, InitArguments_MPT_QGC_V5, gitlink, merge

**日期**: 2026-09-14
**项目**: EncoderPlotter3
**需求编号**: R-01..R-04

**需求描述**:
重新从 `origin/develop` 创建新分支，合并 `origin/feature/support-mpt-qgc`；以 develop 为基础解决冲突，不能遗漏 arguments 结构体；包含子仓提交并 push。

**验收标准**:
- [x] 根仓 `feature/mpt-g-remerge` 从 `origin/develop` 创建，根仓未携带旧 `feature/mpt-g` 独有提交。
- [x] `sub_common` 包含 `InitArguments_MPT_QGC_V5`、`FunctionArguments_MPT_QGC_V5`、MPT V4 发布字段及 MPTQGC V402 配置（算法 4060，AngleData `0x08031800`，Polyfits `0x08005000`）。
- [x] `sub_embedded` 包含 MPT-QGC 参数读取、版本格式化、function arguments、更新写回、Hall 超时和数据写入分支。
- [x] 两个子仓以 develop gitlink 为第一父、`origin/feature/support-mpt-qgc` 为第二父完成 merge 并先 push；根仓随后锁定 gitlink 并 push。
- [x] Python 回归通过：10 + 7 + 26 + 120 项。

**技术方案**:
根仓源分支已在 develop 历史中，不能只用根仓空合并判断完成；对 gitlink 分叉的 `sub_common` 与 `sub_embedded` 分别从 develop 指针创建同名分支，使用真实 merge 保留 develop 基线并补入源分支。冲突复核额外检查了结构体字段、协议布局和调用方；`sub_algorithm`、`sub_automation` 无目标分支，按纯消费者/无变更规则保持原 develop 指针。

**涉及模块**:
- `controller/python/sub_common/DataFormatter.py`
- `controller/python/sub_common/config.py`
- `controller/python/sub_common/utilities.py`
- `controller/python/sub_embedded/EncoderBase.py`

**关键参数**:
根仓提交 `0963c5ca`；sub_common merge `25a372a5`；sub_embedded merge `723c1978`；子仓分支名 `feature/mpt-g-remerge`；根仓远端分支 `feature/mpt-g-remerge`。

**状态**: 已完成

**关键词**: MPT-G, MPT-QGC, V402, InitArguments_MPT_QGC_V5, gitlink, merge

#### F-017: EncoderPlotter_0703_01 IAP 后恢复 SN 必须设备回读校验

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: IAP, statorSN, arguments, EncoderCommandCalibrationRewriteArguments, 回读校验, SN一致性

**日期**: 2026-09-15
**项目**: EncoderPlotter_0703_01
**需求编号**: IAP-SN-ARGUMENTS-RESTORE

**需求描述**:
已写入 SN 的编码器执行正常 IAP 后，固件升级流程可能重建 arguments 并丢失 `statorSN`。上位机需要在 IAP 成功后使用升级前实际请求的 SN 重写 arguments，并验证设备回读值与请求值完全一致。

**技术方案**:
前端 `components/share/iap.js` 在 IAP 请求前保存实际 SN；正常 IAP 成功后复用 `EncoderCommandCalibrationRewriteArguments` 写入 `{statorSN, exitAfterWrite:true}`，只有设备返回的 `statorSN` 完全一致才同步前端缓存。恢复失败单独记录错误并保留 SN 供重试；`updateAppOnly` 不触发该流程。

**验证结果**:
- [x] `node --check components/share/iap.js`
- [x] `git diff --check`
- [x] Node 桩对象验证写入参数、回读一致同步缓存、回读不一致报错。
- [ ] 真机 IAP：需连接读取器与已写入 SN 的编码器执行。

**状态**: 已完成（代码与自动化验证通过，真机验收待硬件环境）

**关键词**: IAP, statorSN, arguments, EncoderCommandCalibrationRewriteArguments, 回读校验, SN一致性

---

#### F-018: 固件 Flash 布局规范（Bin Footer FLYT / 标定 'i' 指令）对上位机影响分析

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: Flash布局, Bin Footer, FLYT, 'i'指令, RecalibrationLayoutInfo, IAP_MUST_PRESERVE, 剥footer, bin文件过大, 1984包, DATA_ADDRESS_LAYOUTS, P/Q/T, V3100

**日期**: 2026-09-15
**项目**: EncoderPlotter_0903_01
**需求编号**: ANALYSIS-FLASH-LAYOUT-SPEC

**需求描述**: 分析固件组交付的《Flash布局信息追加规范.md》(v1.1) 与《标定模式Flash布局查询规范.md》(v1.0)，对照 feature/iap 现有代码评估影响。

**结论要点**:
- 高危：固件 v1.1 已在 Finish-FirmwareBuild 自动追加 212B footer（加密前），上位机 IAP 解密后整份流式下发（IAP.py uploadAppDataV2 无剥尾）；满片 bin(0x7C000=1984×256 包) 会被 `total_packages >= 1984` 拒为“bin文件过大”，非满片则 footer 写入 Flash。上位机须先上线“剥 footer：image=bytes[0:blockStart]”。
- IAP_MUST_PRESERVE 在流式 BootLoader（首包 5BB5 整片擦除、无地址字段）下上位机无法执行“跳过”，只能校验，需固件组确认执行主体。
- Footer/'i' 只给区域起点与大小，推不出双圈 inner 指针（DPT 401+ inner 0x08012834/0x08029800），不能替代 DATA_ADDRESS_LAYOUTS，定位为交叉校验源；规范地址与 DPT 401+ 一致、与 MPT 420+ 不同。
- 'i' 可替代 EncoderBase IAP_PARAMS_REGION_SIZE/IAP_ANGLEDATAS_REGION_SIZE 硬编码；'T' flashSize 含 2KB 擦除余量，不能拿来做补齐长度。挂 V3100 族 P/Q/T 路径，ord('i') 无冲突。
- 规范疑点：footer 超 schema“人工确认继续” vs 8.2/'i'“直接拒绝”口径矛盾；blockLength<=0 对 uint32 无意义。

**涉及模块**（只读）: parse_iap_bin.py、sub_embedded/IAP.py、Encoder.py、sub_embedded/EncoderBase.py、sub_embedded/DriverBase.py、sub_algorithm/step4_GenerateV3100.py
**产物**: .sire/runs/R20260915-114832/analysis-report.md
**状态**: 已完成（分析交付，无代码变更）
**关键词**: Flash布局, Bin Footer, FLYT, 'i'指令, RecalibrationLayoutInfo, IAP_MUST_PRESERVE, 剥footer, bin文件过大, 1984包, DATA_ADDRESS_LAYOUTS, P/Q/T, V3100

#### F-019: driverSoftware 舵机软件仓库开发、合并、发布与打包规范

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: 舵机, driverSoftware, development, feature, fix, merge, no-ff, release.py, VERSION, CHANGELOG, Nuitka, electron-builder, SKU, customer-L0, customer-L1, internal, 混源守卫, 构建门禁, 实机验证, 新需求开发

**日期**: 2026-09-15
**项目**: driverSoftware（KingKong 感驱一体舵机 PC 控制软件）
**需求编号**: ANALYSIS-SERVO-REPOSITORY-WORKFLOW

**需求描述**:
重新识别当前代码仓库，沉淀后续“舵机怎么开发新需求 / 怎么合并 / 怎么发布 / 怎么打包”的规范知识。

**当前基线**:
- 当前工作分支：`development`，工作区干净，HEAD 为 `v0.10.1` 发布提交。
- 当前版本唯一来源：根目录 `VERSION`；Electron 的 `package.json` 与 `package-lock.json` 已同步为 `0.10.1`。
- `dev`、旧版 `docs/BRANCHING.md` 和早期 `0.1.x` 版本规则属于历史线，不能覆盖当前 `development` 线规则。

**规范结论**:
1. 需求先阅读项目代码、依赖、测试、历史决策和对应模块 skill；复杂需求先形成 spec/plan，再拆成可验证的小单元。
2. 新开发分支从 `development` 创建，命名使用 `feature/*`、`fix/*`、`docs/*`、`chore/*`、`release/*`。
3. 功能分支回 `development` 使用描述式 `git merge --no-ff`，保留分支形状；发布分支冻结后只接收发布修复和 CHANGELOG。
4. 用户可见变化写入 `CHANGELOG.md` 的 `## [未发布]`，日常提交禁止手工 bump 版本；发布统一执行 `python scripts/release.py <版本号>`。
5. 发版脚本必须先校验 CHANGELOG、执行完整构建，构建成功后才 bump `VERSION`、截断 CHANGELOG、提交发布记录并创建 `vX.Y.Z` tag。
6. 发包必须使用 `scripts\\build.bat --release --customer`，不能用已删除或仅复用旧产物的快速路径。
7. 打包流程是 Nuitka 编译 `server.py` 一次，再用 electron-builder 按 SKU 打包；SKU 包括 internal、正式包、customer-L1、customer-L0。
8. 客户包剔除内部文档、CHANGELOG、算法源码、开发档案等，并在真实 `win-unpacked/resources` 内容上执行构建后门禁；门禁失败即不可分发。
9. 构建期间 HEAD 变化会判定产物为混源并隔离，禁止命名、打 tag 或发布。
10. 内部包成功后自动创建本地 `internal/vX.Y.Z+<sha>` tag；正式发布 tag 为 `vX.Y.Z`。默认不自动 push，除非用户明确要求。
11. 发布前必须完成提交与 CHANGELOG 对账、软件验证、完整构建、客户包门禁，以及连接设备、MIT、Scope、清故障等必要实机验证；协议/寄存器改动还要确认固件兼容。

**代码与产物链**:
`frontend/Electron → FastAPI server.py → core commands/protocol → reader/HID → Analyzer → RS485 → STM32G473`。
开发态通常从 `start.bat` 启动 Web 后端；打包态由 Electron 启动 `resources/server/server.exe`。Windows 后端默认由 Nuitka 产出 `dist_app/server.dist/server.exe`，Electron 产物进入 `electron/dist/`。

**证据**:
- `AGENTS.md`：当前分支、VERSION、release.py、构建和门禁硬规定。
- `docs/PACKAGING.md`：多 SKU、内容剔除、构建后门禁和发布流程。
- `scripts/build.bat`：实际构建、SKU 顺序、混源守卫和门禁实现。
- `scripts/release.py`：版本更新、构建成功后提交与 tag 的发布入口。
- `server.py`、`electron/package.json`：后端入口、Nuitka pragma 和 Electron 打包配置。

**验证结果**:
- `git status --short --branch`：`development...origin/development`，工作区干净。
- `git log`：HEAD 为 `v0.10.1`。
- 已直接读取 `AGENTS.md`、`docs/PACKAGING.md`、`README.md`、`server.py`、`electron/package.json` 和 `scripts/build.bat`。
- 已执行 SIRE 向量检索；已执行 R9 preflight，结果 `PASS`。
- 未执行完整 Nuitka/Electron 构建，未连接实机；本条目是基于当前源码和规范文件的静态仓库分析。

**状态**: 已完成（规范知识归档）

**关键词**: 舵机, driverSoftware, development, feature, fix, merge, no-ff, release.py, VERSION, CHANGELOG, Nuitka, electron-builder, SKU, customer-L0, customer-L1, internal, 混源守卫, 构建门禁, 实机验证, 新需求开发


## 使用说明

- 每个新功能开发完成后，在此文件中添加记录
- 记录编号格式：F-XXX（自动递增）
- 关键词用于快速检索
- 设备迁移时此文件会一起打包

---

## 功能开发记录

#### F-020: driverSoftware 算法仓库与打包产物边界核查

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: 舵机, 算法仓库, recalibration, sub_algorithm, kingkong_calib, wheel, pyd, pyc, Nuitka, force_calib, internal, release, customer-L1, customer-L0, 算法源码不进包, 派生运行产物

**日期**: 2026-09-16
**项目**: driverSoftware（舵机 PC 控制软件）
**需求编号**: ANALYSIS-SERVO-ALGORITHM-PACKAGING-BOUNDARY

**结论**:
当前仓库**不打包算法源仓库本身**。算法源（recalibration / sub_algorithm 等）按 `docs/PROJECT-CONTEXT.md` 和 `tools/build_algo_whl/README.md` 单独管理，不进 driverSoftware；重建算法 wheel 需要在算法工作区完成，再把生成的 `vendor/kingkong_calib-*.whl` 带回本仓库。

但当前仓库会打包算法的**派生运行产物**：
- Windows Nuitka 通过 `server.py` 的 pragma 显式收进 `kingkong_calib`、`kingkong_calib._algo`、`_common`、38 个子模块和模板数据。
- 这些内容来自已安装的 `vendor/kingkong_calib` wheel；核心算法主要是 `.pyd` 机器码，非算法接口/数据部分可能是 `.pyc`，不是算法源树。
- `tools/force_calib/*.py` 是本仓库内的台架/力感知标定脚本，不是外部算法源仓库；Nuitka 以 `--include-data-files` 收进初始 `server.dist`，构建脚本会直接检查实物是否在位。

**SKU 边界**:
- internal：内容最全，包含编译后的 `kingkong_calib`、台架脚本、dev 档案、内部文档等，禁止发客户/产线。
- release：剔除 `dev-*.json`，但不等于剔除所有算法运行能力。
- customer-L1/L0：在正式包基础上剔除 `docs/skills`、CHANGELOG、出厂 npz、内部 guide，以及 `tools/force_calib` 明文脚本；L0 进一步剔除 trajectory guide，并写入 `MAX_UI_LEVEL=0`。客户包仍保留诊断和被允许的编译运行组件。

**重要区分**:
“算法仓库是否被打包”若指源代码仓库：否；若指算法运行能力：Windows internal/release 通过 `kingkong_calib` wheel 的编译派生物提供；若指本仓库明文台架算法脚本：初始构建产物有，customer 包明确删除并由门禁验证。

**证据**:
- `docs/PROJECT-CONTEXT.md` §2、§5：相邻 `recalibration` 仓库按逻辑名配置，本机路径不进仓。
- `tools/build_algo_whl/README.md`：算法源独立管理，wheel 是带回本仓库的边界产物。
- `server.py` 头部 Nuitka pragma：算法包、模块、模板与 `tools/force_calib/*.py` 的收包规则。
- `scripts/build.bat`：internal/release/customer 的顺序、`force_calib` 实物检查、客户包剔除和门禁。
- `electron/package.json`：将 `dist_app/server.dist` 作为 `resources/server` 打入 Electron 包。

**验证结果**:
- 已执行 SIRE 向量检索并命中 F-019。
- 已直接读取上述当前分支文件和构建脚本。
- 已确认当前分支为 `development`、HEAD 为 `v0.10.1`、工作区干净。
- 未执行完整构建；本次结论为静态配置与脚本逻辑核查。

**状态**: 已完成（边界澄清并归档）

**关键词**: 舵机, 算法仓库, recalibration, sub_algorithm, kingkong_calib, wheel, pyd, pyc, Nuitka, force_calib, internal, release, customer-L1, customer-L0, 算法源码不进包, 派生运行产物

#### F-021: EncoderPlotter 再标定霍尔测试脚本零依赖单文件化

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: EncoderPlotter, 再标定, recalibration, 霍尔, hall, 单文件, 零依赖, standalone, pyserial, Analyzer, EncoderReadoutConfig, CRC8, singleRead, 协议复制, 技术债

**日期**: 2026-09-17
**项目**: EncoderPlotter_0703_01
**需求编号**: FEAT-RECALI-HALL-STANDALONE

**需求**: controller/python/test.recalibration.hall.py 拷到别的目录/电脑就报 No module named 'sub_common'。
要求抽离全部项目依赖，做成只靠 pyserial 的单文件脚本，仍支持 enter / exit / h / H 四个 action。

**产物**: controller/python/test.recalibration.hall.standalone.py（原文件保留，未进 git 不敢覆盖）

**复制过来的协议真源**（主仓改协议这里不会自动跟着变，是已知技术债）:
- 常量: sub_common/Defines.py 的 Control*/Device*/EncoderInterface*/EncoderCommand*
- CRC8 表与 calcCRC8: sub_embedded/CRC.py
- ctypes 结构体: sub_common/DataFormatter.py 的 USBDataHeader / TriggerInfo /
  EncoderRequestInformation / EncoderStatus / EncoderReadout / EncoderReadoutConfig
- 收发与枚举: sub_embedded/Analyzer.py（VID 0x6B6B / PID 0x0001，读线程按 requestId 匹配，
  ControlData 进 readBuffer 并按 packageNum 递减 readEventCount）
- 命令层: sub_embedded/EncoderBase.py 的 setReadoutConfigs / setReadouts / startAndReceive /
  singleRead / resolvePackages / resolveDualHalls / Recalibration.enter / getMemory / exitRecalibrationMode

**关键认知**:
1. EncoderReadoutConfig 的 commands / data / crc **不是 ctypes 字段**，是运行时挂到实例上的
   普通 python 属性；setReadoutConfigs 用 hasattr 取它们拼成 followedData 跟在结构体后面。
   只照抄 _fields_ 会漏掉整个命令拼装逻辑。
2. request 是 union：byteLength(byte0) 与 uart.command(byte0)、uart.timeoutByteNum(byte1) 重叠，
   赋值顺序决定最终字节，照抄时必须保持源码顺序。
3. singleRead 里的 isFirstByteLongWait 在 RS485/Recail 路径上是死参数——uart 结构体只有
   command + timeoutByteNum 两个字段，它被挂成普通属性后从未被序列化。
4. H 帧长 46 字节（带角度字段）、h 帧 38 字节，resolveDualHalls 只认 38，H 必然解析为 0 样本、
   靠原始 hex 看数据。这是设计如此，不是 bug，别在这里打屏报警。
5. exit 发的 [E,R] 是复位命令，编码器**不应答**，返回 trigger 无数据是正常的。

**验证方法（可复现）**:
- 交叉核验脚本：同时 import 主仓模块与独立版，比对 5 个结构体 sizeof、500 组随机 CRC8、
  singleRead 三种命令(h / v读内存 / ER)的下发字节流、enter 时序 4 个 config 字节流、
  readout / encoderStatus / USBDataHeader 字节流、resolvePackages 结果 —— 14 项全 PASS。
- 实机（读取器 serial=20260420173117 @COM3）：FrameID 取回 -> enter 得 v=b'SUCCESSFUL' ->
  h 连读 3 次各 1 样本 18 个霍尔 CRC 通过 -> H 连读 3 次回 46 字节原始帧 -> exit 正常。
- 边界：无效 action 被拒、q 退出且 finally 关串口。

**状态**: 已完成

**关键词**: EncoderPlotter, 再标定, recalibration, 霍尔, hall, 单文件, 零依赖, standalone, pyserial, Analyzer, EncoderReadoutConfig, CRC8, singleRead, 协议复制, 技术债

#### F-022: EncoderPlotter_0903_01 全项目架构与标定/IAP 产物语义基线

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: EncoderPlotter_0903_01, 标定, 再标定, IAP, 在线IAP, 离线IAP, P/Q/T, ced_Q, ced_T, ged_P, ged_Q, ged_T, 调试ZIP, kingkong.zip, _iapgen.bin, iapenc, IAPENC01, FLYT, flash layout, parse_iap_bin, DATA_ADDRESS_LAYOUTS, Arguments, FunctionArguments, HTTP IAP, SSE, flow-control, bootloader, MES, 产物语义, 复核边界

**日期**: 2026-09-20
**项目**: EncoderPlotter_0903_01
**需求编号**: ANALYSIS-FULL-CALIBRATION-IAP-KNOWLEDGE-BASELINE
**代码基线**: 分支 `feature/lingxi-dpt-iap-preserve-zero`，HEAD `7a6114a9c8cf19225e1ad8c6bddb525c7a6445ec`
**SIRE run**: `R20260920-112827`

**需求描述**: 用户要求分析整个项目，特别是标定、IAP 等流程，解释每一个关键产物的含义，并记录到 SIRE 知识库。此次是当前代码快照的只读分析，没有修改业务代码、协议常量、子模块指针或发布配置。

**总览结论**:

- 项目是 Electron main + Vue2/Vuex renderer + Python middleware 三层桌面应用。renderer 内的 `controller/server.js` spawn Python；Python `main.py → Server.py → Encoder.py` 控制读取器/编码器，HTTP/chamber 是共享核心或独立进程入口。
- JS↔Python 使用 18 字节 header + payload；`requestId=0` 是主动推送。IAP/标定的主要事件是 `iap:calibration-data-retrieved`、`iap:flow-control`、`PlainMessage` 和内部 `[IAP_PROGRESS:n]`。
- 标定链路是“MES/会话预检 → 进再标定 → 读 Arguments/现有数据 → 采霍尔/算法生成 → 按模式写 Flash → 启动角度处理 → 退出 → 调试 ZIP/MES 收尾”。Python AllInOne 对应准备、读取、采集生成、写入、退出五个阶段；导入 ZIP 用 `write=false`，dry-run 写入校验不进硬件。

**标定数据与调试 ZIP**:

- 新版算法（>=303）统一为 P=`PARAM_CONST`、Q=`ANGLEDATA_CONST`、T=`POLYFITS_DATA`；部分旧 DPB 仍有 M=`SLOWPOLYFITS`。旧算法（<=302）按 DPT/DPB/MPT/MPP 保存多块 angle/hall/group/polyfit。
- `ced_Q`/`ced_T` 是设备当前数据；`ged_P`/`ged_Q`/`ged_T` 是算法生成数据；`j72` 是 Arguments、`j99` 是 FunctionArguments、`j74` 是历史 P、`j70` 是霍尔采集、`j00/j01/j02` 是业务参数/modes/算法 options、`j03/j04` 是诊断日志、`snapshot` 是状态快照，`j75/j76/j77` 是旧数据族。ZIP 读取按前缀第一次命中，不保证取最新同名前缀文件。
- Flash 写入在 Footer/`i` 返回动态区域大小时按 P/Q/T 分别补 `0xFF`，超长失败；读回做长度/内容校验并带重试。Footer `FLYT` 含 P/Q/T region id/start/size/flags/CRC；有效 Footer 先剥离再解析，失效 Footer 不静默走旧逻辑；`must_preserve` 当前只是诊断标记，不代表上位机按地址跳过整区擦除。

**在线 IAP**:

1. Step 1 解密 App、解析 Footer 和 ARGUMENTS、按系列+软件版本查 `DATA_ADDRESS_LAYOUTS`、读取设备当前 P/Q/T、运行生成算法、缓存上传前 Arguments/Flash 布局/bin digest、保存 `ged_P` 并通过主动事件导出 IAP `.kingkong.zip`。
2. Step 2 进入 boot/IAP，编码器走 V2 的 `Protector` 分段上传。
3. Step 3 进入再标定，主要写目标 P，启动角度处理，读回 Arguments；DPT>=422、MPT>=420 只恢复允许的接口/模型/分辨率字段，返回实际软件版本和写回标记。

- 失败通过 flow-control 带 step/SN/session/ZIP 文件名，桌面 UI 可重试；普通 step>1 要求同设备、同 session、允许 step、同一固件 digest。`repair=true` 跳过普通 bin 结构/系列/版本/地址门禁，从 ZIP 恢复数据，是故障修复路径。
- 内部 App-only 直接解密上传 App，跳过 SN、目标结构、系列/版本和标定校验；HTTP 禁用。HTTP IAP 默认不挂载，需 `--http-enable-iap`；`iapVersion` 强制 2，step 2/3 只能消费桌面版导出的 ZIP，HTTP 不生成 ZIP。`jump-to-app` 恒 501，因底层 V1 形状与编码器 V2 不兼容。
- `parse_iap_bin.py` 按结构扫描而非写死 Arguments 地址：DPT 标准 128B，MPT/部分 DPT_V412 72B u32+u32，DPT_V401 是 u16+u16 特例，DPB 是 136B。软件 4.1.2 归一为 412；系列码 MBS 101、MBP 102、DPT 103、MPT 104、MPP 105、DPB 106、MPT-G 107。
- 地址表当前为：DPT 303–400 和 401+ 双圈两套，MPT 302–419 和 420+ 单圈两套，DPB 401–407 和 408+ 双圈两套，MPP 空布局。DPT_V401/V412 的文件名归属与 bin 内 series=104 的冲突必须用目标 `.map`/真机复核，不能只凭名称改表。

**离线 IAP 和产物**:

- 输入为 IAP 第一阶段调试 ZIP + 目标明文/可解密 BIN；必须取得 HallParam、ParamFit、`ged_Q`、`ged_T`。当前 HEAD 的关键修正是离线转换使用生成的 GED(Q/T)，不是设备当前 CED(Q/T)。
- command 64 调免标定算法生成新 P/Q/T，将它们写入 BIN 保留区，生成 `<base>_iapgen.bin`；这是合入数据后的明文中间产物。再做专用整体链式 AES，生成 `<base>_iapgen_<hex时间戳>.iapenc`；command 65 唯一消费 `.iapenc`。
- `.iapenc` = `IAPENC01` + little-endian 帧数 + 原始明文长度 + N 个 length/frame。每帧 16B IV + AES-CBC 密文；每包明文为 2B 包号 + 2B 大端 applenth + 256B 以内 payload + 1B CRC 占位 + 对齐。它与 `Protector` v2/v3 分段格式不同，知识库不重复记录源码中的密钥 literal。
- 整文件写入只支持直连：`6BB6` 开启、`5BB5` 整区擦除、首帧四次重试/`6AA60000`、`5CC5` 确认、后续 `5BB5+帧` 成组重试、进度推送、`5EE5` 收尾、`6FF6` 复位。verify 只解密还原、长度核对和 BIN/PQT/Arguments 解析；preview 只解析不写硬件。
- 5EE5/复位只证明协议阶段应答，当前上位机不做固件读回或内容 CRC 证明；目标 bootloader 的真实内容验证必须另做真机/固件仓核对。

**全项目风险与验证**:

- 已运行仓库指定测试：`build_info_test` 10 passed、`safe_name_test` 7 passed、算法配置测试 26 passed、`qa_api/tests` 120 passed（1 个弃用 warning）。这些不覆盖真实前端 handler、读取器、IAP 传输、目标固件、MES/chamber 联调。
- 三个巨石热区是 `components/encoder/device.js`、`controller/python/Encoder.py`、`sub_embedded/EncoderBase.py`；协议命令/事件双真源、DPT/MPT 版本布局歧义、ZIP 前缀首项匹配和 IAP 内容未验证是后续变更重点。
- 完整源码锚点、产物表、正常/异常流程、HTTP/并发、构建/外部边界和测试输出见本次运行档案：`@CODE_ROOT@/EncoderPlotter_0903_01/.sire/runs/R20260920-112827/analysis-report.md`；单元证据为同目录 `evidence-U-01.md` 至 `evidence-U-04.md`。

**验证结果**:
- [x] 已对照当前 HEAD 源码完成架构、标定/再标定、恢复出厂、调试 ZIP、在线 IAP、离线 IAP、HTTP 和整文件传输分析。
- [x] 已完成五个只读分析单元；每个单元有实现者自测、R6A/R6B/R6C 初审、三路交叉核验、综合复核和独立测试证据。
- [x] 已通过 Python 工具/算法/HTTP 测试；未执行写固件、真机、MES 或 chamber 操作。
- [x] 已将当前事实、历史兼容项与待真机/固件确认项分层记录；未写入真实凭据或业务数据。

**状态**: 已完成（知识分析与 SIRE 归档；无业务代码变更；真机/固件外部验证待后续）

**关键词**: EncoderPlotter_0903_01, 标定, 再标定, IAP, 在线IAP, 离线IAP, P/Q/T, ced_Q, ced_T, ged_P, ged_Q, ged_T, 调试ZIP, kingkong.zip, _iapgen.bin, iapenc, IAPENC01, FLYT, flash layout, parse_iap_bin, DATA_ADDRESS_LAYOUTS, Arguments, FunctionArguments, HTTP IAP, SSE, flow-control, bootloader, MES, 产物语义, 复核边界

#### F-023: 正式版本使用 tag 触发 CI Runner 构建

**类型**: F  **来源**: @USER_HOME@\sire_global\global_dev_features.md
**关键词**: driverSoftware, release.py, CI Runner, GitLab, tag, vX.Y.Z, build-win-release, build-mac-release

**日期**: 2026-09-20
**项目**: driverSoftware

**事实**:
正式发布入口 `python scripts/release.py <版本>` 默认只校验、同步版本文件、提交并创建本地 `vX.Y.Z` tag；推送分支和 tag 后，`.gitlab-ci.yml` 的 `test-gates`、Windows/macOS release job 在 Runner 上完成门禁、打包和 NAS 上传。`--local-build` 只用于本地预检，不代表正式产物。

**验收**:
v0.13.2 已生成发布提交并推送 `development` 与 tag；远端 tag 满足正式 CI 规则。

**关键词**: driverSoftware, release.py, CI Runner, GitLab, tag, vX.Y.Z, build-win-release, build-mac-release

#### F-029: Codex 桌面会话与飞书完整可见对话同步及续跑

**类型**: F  **来源**: @USER_HOME@\.feishu_bridge\hook_codex_notify.py
**关键词**: 飞书, Feishu, Codex notify, transcript JSONL, 用户消息, 助手可见回复, 分卡, 游标, 重启恢复, codex exec resume, msg_map

**目标**：飞书查看 Codex 当前会话的完整可见文字，并通过回复已同步卡片把指令交回同一 Codex 会话。

**实现**：Codex notify 回调按 thread-id 定位 ~/.codex/sessions 下 JSONL。只导出 response_item 中 user 的 input_text 与 assistant 的 commentary/final_answer output_text；过滤 developer、reasoning、工具调用和工具输出。用 message id 作游标，首轮回填完整可见历史，后续增量同步。约 2400 字符分卡，每张卡保存 msg_map(message_id→session_id,cwd,codex)，飞书回复沿用监听器已有 codex exec resume。图片原文可读时文件名/路径随用户文字发送；只有不可解码的 image 输入块而无名称/路径时，卡片明确标记名称/路径未记录。

**可靠性**：SQLite 持久化每会话游标和 codex_sync_pending。每张卡获接口确认并保存映射后推进游标；发送异常保留待办，由飞书监听器每分钟重试，重启后从最后确认的消息继续。网络结果不确定时允许重复一张已发送卡，优先避免丢失；不是严格 exactly-once。

**验证**：2026-09-24 本机 py_compile 通过；实际会话 135 条可见消息、约 33337 字符切成 16 张卡，单条超长文本可逐字还原；飞书发送 API 接受 16 张卡且 msg_map 建立，随后重启监听器并标记待同步，启动恢复又发 1 张增量卡、清空待办、推进游标。当前会话实际 UI 展示及用户在 Feishu 回复后入站执行仍需用户在 Feishu 实际回复测试卡验证；Windows 当前没有可用共享 app-server，不能把 CLI queue 视作桌面实时投递已验证。

**补充验收**：注入一次发送异常后，待办保持且游标不前移；恢复发送后批次发送完成、游标前移、待办清空。该项所有功能断言通过；Windows 仅在清理测试临时 SQLite 目录时遇文件锁，清理命令被本机策略拒绝，遗留的是 Temp 下的测试目录，不影响桥接数据。真实飞书界面核对与飞书用户回复仍待用户操作。

#### F-030: 飞书回复 Codex 桌面会话队列与回调关联

**类型**: K  **来源**: @USER_HOME@\.feishu_bridge\listener.py
**关键词**: 飞书, Codex, codex queue, active writer, thread-store conflict, notify hook, 消息回帖, WAITING_CODEX, 待关联任务, 重启恢复

目标：飞书回复必须路由到固定 Codex 会话/工作目录执行，并将结果回帖原飞书消息。旧方案 codex exec resume 在桌面 Codex 线程遇到 thread-store active writer；自动重试三次仍冲突，不能重复重试。Codex CLI 的 codex queue --thread <session> --message <text> -C <cwd> 返回 Queued message ID，说明只确认入队，不能据此宣称已执行。桥接必须先持久化 pending(task_id,session_id,cwd,turn_id,queue_id)，再入队；Codex notify completion 用 session_id 取最早 pending，调用 hook_notify.deliver 回帖原 Feishu 消息，再把完整可见文本增量同步到同一回复；发送失败保留 RESULT_READY/pending，成功后删 pending。本机 2026-09-24：活动写锁触发失败；已改 listener 使用 codex queue，Hook 根据 pending 关联回帖，py_compile 通过并重启 FeishuClaudeBridge。真实完成回调仍未通过：桌面线程保持 idle，accepted queue 未产生新的 user response_item；任务标记 WAITING_CODEX，不得重复入队，不得报告端到端通过。重启后 WAITING_CODEX 保留，但队列执行/回调恢复需进一步验证。

#### F-031: 飞书回复按通知消息映射选择 Claude 或 Codex

**类型**: K  **来源**: @USER_HOME@\.feishu_bridge\listener.py
**关键词**: 飞书, Claude, Codex, parent_id, msg_map, backend, session_id, cwd, 消息路由

当前桥接不会根据回复正文中的“Claude/Codex”字样切换执行者。飞书事件 parent_id 指向被回复的机器人消息，listener 用该 message_id 查询 msg_map(message_id, session_id, cwd, backend)，并将 backend/session_id/cwd写入任务账本后路由。要选 Claude，就回复 Claude 的完成通知/会话卡；要选 Codex，就回复 Codex 的完成通知或 Codex 对话记录卡。回复文本仅作为该目标会话的 prompt。新发私聊或无法映射的消息会提示必须回复任务通知。跨 AI 切换需要回复目标 AI 自己的卡，因为两边会话 ID 和工作目录不同；不能只在同一消息正文写切换词。若未来要支持显式前缀，应设计为经授权的路由选择，并在切换 agent 时明确目标会话和工作目录。

#### F-032: 飞书回复显式指定 Claude/Codex 并按工作目录安全路由

**类型**: F  **来源**: @USER_HOME@\.feishu_bridge\listener.py
**关键词**: 飞书, Claude执行, Codex执行, 显式路由, 执行者前缀, parent_id, msg_map, session_id, cwd, 多会话歧义

需求：用户可在飞书回复正文指定执行者，例如“Claude执行：复核刚才的分析并实现”；需剥离路由前缀后把剩余内容作为目标 AI prompt。实现于 listener.py：仅识别消息开头的显式前缀（Claude执行：、让Claude执行：、Codex执行:、由 Claude 来执行：）；无前缀时保持回复父卡片映射的 backend/session。跨后端切换保持父卡片 cwd，在 msg_map 中查询同 cwd、指定 backend 的会话；唯一候选才执行，零候选或多候选均拒绝投递并回复原因，避免猜错项目上下文。目标执行结果卡片标题显示 AI 名称，msg_map 保存新后端及 session，使后续回复继续正确路由。当前 @CODE_ROOT@\EncoderPlotter3 映射下 Claude 会话唯一，Codex 会话多于一个，因此 Codex 分析卡→Claude 执行可唯一解析，反向则安全拒绝歧义。验证：py_compile 通过；5 类前缀/无前缀断言通过；目录会话解析唯一及歧义断言通过。未执行真实飞书端到端消息测试，需用户授权后验证；整体端到端状态 BLOCKED。 实际验证补充：用户已授权发一条 ROUTE_OK 测试，但当前没有可控制已登录飞书用户账号的 UI 自动化工具；机器人身份消息不会等同于白名单用户回复，因此未伪造真实端到端测试。 实际路由验证补充：飞书测试回复“claude执行：只回复ROUTE_OK”被解析为 backend=claude，session_id 为同目录 Claude 会话，工作目录保留 @CODE_ROOT@\EncoderPlotter3，前缀已从 prompt 剥离；错误回复回到飞书原消息。Claude 返回 session limit，重置时间提示为 13:00 Asia/Shanghai，故只证明路由/错误回传通过，不证明 Claude 成功执行。未自动重试。

#### F-033: 飞书显式 AI 路由真实用户测试的授权与工具边界

**类型**: K  **来源**: @USER_HOME@\.feishu_bridge\listener.py
**关键词**: 飞书, 真实测试, 授权, 用户身份, UI自动化, Claude执行, ROUTE_OK, R7 BLOCKED

用户已授权一次飞书真实路由测试“Claude执行：只回复 ROUTE_OK”。当前可用工具没有登录飞书用户身份的 UI 操作能力；桥接机器人账号发出的消息不能冒充白名单用户回复，直接调用内部处理器也不能作为真实 UI 证据。故未发送伪造事件或测试消息。下一步由用户在 Codex 飞书卡片下实际回复该文本；监听器应路由到同目录唯一 Claude 会话并将 ROUTE_OK 回帖原消息。验收证据：飞书原消息、任务账本 backend=claude/status=DONE、结果回帖及映射记录。当前 R7 BLOCKED-无法真实验证。

#### F-034: 飞书显式 Claude 路由已验证，执行受订阅限额阻断

**类型**: K  **来源**: @USER_HOME@\.feishu_bridge\listener.py
**关键词**: 飞书, Claude执行, ROUTE_OK, 路由验证, session limit, 订阅限额, 错误回传

真实飞书回复“claude执行：只回复ROUTE_OK”已触发一次任务。账本证据：backend=claude；session 为 EncoderPlotter3 同目录 Claude 会话；cwd=@CODE_ROOT@\EncoderPlotter3；存储 prompt 为“只回复ROUTE_OK”（路由前缀正确移除）；attempt=1，rc=1。runs 日志：You've hit your session limit · resets 1pm (Asia/Shanghai)。飞书向用户回传错误。结论：显式执行者解析、Claude 会话选择、目录继承与错误回传通过；Claude 成功执行未通过，原因是订阅会话限额，非桥接路由错误。未自动重试或回退 Codex。后续可在 13:00 后重试，或由用户明确指定 Codex。

#### F-035: Codex 桌面可见对话通过 Stop 钩子与游标轮询补漏同步飞书

**类型**: K  **来源**: @USER_HOME@\.feishu_bridge\hook_codex_notify.py
**关键词**: Codex, Feishu, 飞书, Stop Hook, hooks.json, transcript cursor, 对话补漏, 重启恢复, 完整可见消息

适用场景：Codex 桌面会话需要将可见用户/助手文字持续同步到飞书，并在钩子漏触发或电脑/监听服务重启后补齐。

问题：旧桥接只依赖 config.toml 的 notify 命令，当前会话游标之后累积 46 条可见消息未同步；该入口不能保证桌面每轮都触发，且旧过滤会跳过 client 字段缺失的独立事件。

方案：hook_codex_notify.py 同时接受旧 notify argv 与 Codex 原生 Stop 生命周期事件的 stdin JSON，按 session_id/cwd/transcript_path 读取可见对话并沿用持久游标；原 Feishu 任务仍先发结果卡，再将完整增量回复到原消息，发送成功后才清除 pending。listener.py 的 60 秒守护循环额外扫描已有 transcript cursor 的 Codex 会话，仅补发新内容，避开仍在发送的 pending session。

验证：Python 编译通过；mock 测试覆盖 Stop stdin 字段映射、legacy 独立通知过滤、待处理 Feishu 任务结果+完整对话回帖+成功后清 pending、守护循环只扫有游标且跳过 pending；真实补发当前会话积压 6 张飞书卡，API 返回成功，msg_map 建立、游标前移、codex_sync_pending 清零；服务重启后仍 Running，恢复扫描/待恢复任务数均为 0。随后守护循环又确认发送 1 张新增量卡。

约束：Codex 原生 Stop hook 需在 Codex 客户端 review/trust 后才能运行；为已有游标会话提供 60 秒轮询兜底。新会话首次完整同步仍依赖 Stop hook 被信任或另行建立初始游标。飞书 UI 未通过原生桌面操作工具核验，API 接收成功不等于 UI 人工验收。

相关风险：已有一个 Codex queue 完成卡的文本似乎与原 Feishu prompt 不一致；未自动重投，需单独核验 queue 与完成回调关联。

#### F-036: 飞书桥接当前实现缺口与验收优先级

**类型**: K  **来源**: @USER_HOME@\.feishu_bridge\listener.py
**关键词**: 飞书, Codex, Claude, 会话纳管, Stop Hook, 消息元数据, 工作目录, 附件清单, WAITING_CODEX, 队列恢复, 回调关联, 幂等, R7, 共享规则, 多AI扩展

适用场景：评估本机 FeishuClaudeBridge 是否覆盖用户提出的 Codex/Claude 双向通讯、完整上下文、显式执行者选择和重启恢复。

已确认实现：Feishu 回复卡片可按 parent message 映射 backend/session/cwd；正文显式“Claude执行/Codex执行”时跨后端选择同 cwd 唯一会话，多候选安全拒绝；Codex可见消息按游标增量发送，用户文本与assistant commentary/final文本被提取；桥接任务在用户登录时启动，异常退出会重启。

待实现/补强，按优先级：P0 1) 完整会话纳管：新Codex会话目前无游标时不会被60秒扫描发现，Stop Hook还依赖客户端review/trust；加明确的会话注册/首次游标初始化和可观测健康状态。2) 消息信封：当前Feishu卡可见cwd但不显示session ID；映射只含当前backend的session，未在跨AI任务卡同时列出Codex session ID、Claude session ID、task/mode、cwd和内容。3) 附件清单：input_image当前只生成“名称/路径未写入会话文本”占位，未提取用户要求的文件名/路径；补可读元数据提取及未知值明确标记。4) Codex队列恢复与关联：启动recover处理RUNNING/INTERRUPTED/RESULT_READY/QUEUED，但无WAITING_CODEX恢复；通知Hook按同一session最早pending关联，非queue_id精确匹配，异常/并发/重启可能卡住或错配。应以queue/turn ID关联、超时标记与人工安全恢复为准，绝不盲目重新入队。5) R7真实场景验收：飞书客户端正常路径、回复后执行、错误/限额、服务重启及电脑重启，检查消息可见、cwd与原消息映射。

P1：结果卡和完整对话卡的发送/SQLite落账之间建立持久outbox与幂等重试/去重；当前不确定发送结果时可能重复卡片。Claude路由功能已有真实触发证据，但执行因订阅限额rc=1；额度可用后只需成功场景验证，不应静默切换Codex。

条件性后续：若仍纳入用户早前诉求，建立Claude/Codex共用规则与资料目录并定义安全读取/热更新；用Provider Adapter扩展到其他AI；线上控制面+本机执行器。后两项不是完成当前本地双向链路的前置。

限制：当前service计划任务为用户登录触发，PC开机但未登录时本地执行器不会运行。Feishu API成功/本机日志不能替代飞书客户端UI验收。证据来源：listener.py、hook_codex_notify.py、hook_notify.py、install_service.ps1及F-029/F-030/F-032/F-034/F-035。

#### F-037: 飞书与多AI通过唯一中间服务通讯的单中枢架构

**类型**: K  **来源**: @USER_HOME@\.feishu_bridge\listener.py
**关键词**: 飞书, 中间服务, 消息中枢, 单一通信入口, Codex, Claude, Provider Adapter, 任务路由, 消息账本, Outbox, 会话ID, 工作目录

架构决策：中间服务是唯一消息交换、路由和状态记录中心。飞书只与中间服务的Feishu Adapter通讯；Codex、Claude及后续AI只与各自Provider Adapter/中间服务通讯，任何AI不直接向飞书发消息，AI之间也不直接通讯。

流程：1) Feishu Adapter接收回复并校验身份、事件去重；2) 先把原始消息、parent/root消息ID和任务记录持久化；3) Router按显式执行者前缀路由；没有前缀时按父消息绑定的agent/session继续，缺映射或候选歧义时询问用户，不猜测；默认只发给一个AI，只有用户明确要求协作时才建立父任务/子任务；4) Provider Adapter将同一任务封装交给本机已登录的Codex/Claude会话；5) 执行端只将progress/completed/failed及result返回Broker，必须携带task_id和provider/session/turn或queue标识；6) Broker落结果、更新任务状态并写持久outbox；7) Feishu Adapter按原parent_message_id回帖；后续飞书回复再通过消息映射继续原会话。

规范化消息信封至少含：event_id、task_id、conversation_id、collaboration_mode、selected_provider、provider_session_ids（Codex和Claude）、cwd、feishu_message_id、parent/root_message_id、sender_id、完整可见文本、attachments清单（名称/路径/缺失状态）、status与时间戳。凭据不进入信封或云端日志。

目标约束：中间服务持有唯一任务账本与Inbox/Outbox；Provider Adapter不得调用飞书API，Feishu Adapter不得绕过Broker直发执行器；每个结果按task_id准确关联。若中间服务部署云端，本地执行器使用主动出站安全连接并保留订阅凭据/桌面会话在本机；机器未运行时不承诺本地项目执行。

当前差距：本地listener与SQLite已经承担部分broker职责，但hook_notify.py/hook_codex_notify.py在回调路径中仍直接调用bridge_sender发送飞书，并直接访问共享SQLite；属于共置脚本的半中心化实现，不是严格的Broker API/队列边界。需后续把hooks改为只投递到本地Broker（HTTP/命名管道/持久队列之一），由Broker独占飞书收发、状态机、消息关联、重试和审计。当前未作代码修改；此条记录保存用户确认的目标架构，不代表已实现或验收。

#### F-038: 当前飞书桥接与单一中间服务架构的比较结论

**类型**: K  **来源**: @USER_HOME@\.feishu_bridge\listener.py
**关键词**: 飞书, 中间服务, 单一Broker, 架构比较, Codex, Claude, 订阅额度, 本地执行器, 渐进迁移, Provider Adapter

结论：按用户的目标（飞书、Codex、Claude均只和中间服务通讯；按指定执行者分发；输出回Broker后再回Feishu；没有明确协作指令时不触发AI间协作），单一中间服务作为最终架构更优。当前本机FeishuClaudeBridge作为已运行原型/迁移基础更有价值，不建议推倒重写。

当前实现：Feishu长连接listener+共享SQLite+CLI/桌面hook。优点：本机订阅授权和原工作目录可用，显式前缀/parent映射已有实现，Codex已有Stop Hook和游标补漏，改动成本低。局限：Hook回调直接调用bridge_sender发Feishu并直读写SQLite，尚无严格Broker事件/API边界；新会话纳管、WAITING_CODEX恢复/精确队列关联、附件元数据、完整session信封、UI端到端验收仍有缺口。

目标Broker架构：Feishu Adapter写持久Inbox→Broker校验/去重/状态机/路由→只把任务交给指定Provider Adapter→AI结果事件带task_id/session/turn/queue标识回Broker→持久Outbox→Feishu Adapter回帖原消息。默认一个agent；只有用户明确说明协作才建立多agent父子任务。各AI不直接调用Feishu API或另一个AI。

权衡：目标架构更易扩展、审计、消息关联和去重，但中间服务是关键依赖，需要持久队列、健康监测、备份、回压/重试和单点故障恢复。为遵守不额外购买API额度的约束，Claude/Codex Provider Adapter及订阅凭据应留在用户电脑的已登录环境；云端Broker若未来采用，靠本地Worker主动安全连接，电脑离线时不能承诺本地会话执行。

建议迁移：1) 不换现有Feishu长连接/SQLite，先定义统一Envelope、任务状态机、持久Inbox/Outbox与task_id关联；2) 将hook_notify.py/hook_codex_notify.py改为只向本地Broker HTTP/命名管道/队列上报，不直接发送Feishu；Broker独占Feishu API与消息映射；3) 将Claude/Codex包成Provider Adapter并明确 session/cwd、quota/error、进度/完成事件；4) 完成Feishu UI正常/边界及服务/电脑重启测试；5) 通过后再考虑云端Broker或更多provider。先做本地单进程/模块化Broker，不必一开始引入微服务/Kafka。

#### F-039: 单Broker飞书多AI系统的深层逻辑与失效模式审查

**类型**: K  **来源**: @USER_HOME@\.feishu_bridge\bridge_config.py
**关键词**: Feishu, 单一中间服务, Broker, 安全边界, bypassPermissions, 工作目录白名单, 任务状态机, 幂等, 队列恢复, 多AI协作, 上下文回环, 附件, 取消, 并发, 隐私

目的：在单一Broker架构下审查消息路由、权限、安全、上下文、并发、故障恢复与用户操作中容易遗漏的逻辑。

P0安全门：当前 bridge_config.py 默认 permission_mode=bypassPermissions，Codex参数含 --dangerously-bypass-approvals-and-sandbox；Feishu回复可触发本机执行。listener.resolve_cwd主要检查目录存在，NEED_DIR可让白名单用户提供路径；_is_danger是关键词子串提示，不构成权限边界。目标架构必须改成最小权限、固定workspace allowlist、按任务能力授予、危险操作真人确认和可审计撤销；凭据留本机。否则Broker虽单一，却成为远程高权限执行入口。

P0消息与任务一致性：Feishu event_id去重应和持久Inbox原子提交，事件确认不能早于入库；每条任务固定task_id、Feishu message/parent/root IDs、provider session/turn/queue IDs、路由和cwd快照。Agent回调必须按精确task/queue ID匹配，不能按session FIFO；包括 UNKNOWN_OUTCOME/WAITING_PROVIDER/RESULT_READY/SENDING等状态与lease/fencing，重启后未知是否入队时不能自动重复执行非幂等任务。Inbox/Outbox持久化、发送幂等或重复检测；不能以“接口成功”作为UI送达确认。当前recover遗漏WAITING_CODEX，pending按session最早任务领取。

P0路由/对话语义：支持无parent的新任务启动（选AI、cwd、已有/新会话）和未知/多候选时询问；收到消息时冻结路由，默认单AI；“Codex分析、Claude执行”是显式父子工作流，须把上游产物/版本/来源传给下游并记录审批/依赖，而不只是把下一条文本切换backend；用户未说明协作绝不跨AI传上下文。运行中收到新回复要定义排队、分支、取消或拒绝并保留，不要无声忽略；支持取消、重试、放弃、超时。

P0上下文一致性：定义规范对话账本和方向/来源标识，避免Broker回注AI、AI输出又被转成新指令形成回环；排序、修订、重发与分片使用序号/hash，不只靠message ID假设内容永不变化。明确可见文字范围（用户、assistant commentary/final；不转发隐藏推理/工具输出），附件清单和实际可访问性；当前Feishu入口拒绝非文本，Codex image block仅占位；仅有本机路径时云端/不同执行器不一定可读。Claude桌面回填hook_sync有30000字符截断，需要明确截断提示/摘要或分段回填。

P0可用性：服务启动/登录、电脑离线、Feishu WS断开、Agent额度/认证失效、broker崩溃、磁盘满/SQLite损坏、任务超时分别定义状态、告警和恢复责任。机器未登录/本机worker离线时只排队，不宣称已执行；已接收/执行中/已完成/结果已回帖分开展示。用户登录触发和provider订阅session都要通过重启实测。

P1数据治理与运维：保留期限、备份/恢复、加密、访问审计、日志脱敏、删除/导出；完整同步到Feishu可能泄露可见回复里的凭据，需明确红action/敏感内容策略。Feishu消息卡长度/速率/权限、文件上传类型/大小、失败退避、死信和人工重放；provider protocol/version/capability和quota error映射。工作区/会话并发锁需同时考虑规范化workspace与provider session，跨AI写同一repo应默认串行或隔离worktree。

当前源码证据：listener.py仅接收text消息；无parent时提示回复映射卡；运行态指令没有完整cancel/append策略；task recovery处理RUNNING/RESULT_READY/QUEUED等但遗漏WAITING_CODEX；_is_danger按关键字；bridge_config.py有bypass flags；hook_sync.py限制单次回填30000字符。当前是审查结论，不表示缺口已修复。

#### F-040: 飞书机器人私聊直接发起AI任务的会话入口逻辑

**类型**: K  **来源**: @USER_HOME@\.feishu_bridge\listener.py
**关键词**: 飞书机器人, 私聊, 新任务入口, parent_id, conversation_id, 显式路由, Claude, Codex, 工作目录, 会话绑定

用户补充需求：无需先找到或回复已有任务卡片；用户可以直接私聊机器人，消息经唯一中间服务入账、选定Claude/Codex等执行者后触发任务，结果再由服务回复这条私聊消息。该入口仍遵守所有AI只和Broker/适配器通信，不是Feishu直连AI。

新DM逻辑：Feishu Adapter对用户校验、事件去重并持久化消息；Broker按（tenant/user open_id + chat_id，必要时再加thread/root）查conversation binding。已有绑定时继承provider/session/cwd；消息开头显式执行者前缀可覆盖本轮目标。无绑定的新DM若缺少provider或cwd/session，先在原私聊线程追问选择，不猜默认agent、不触发多AI协作。可用“Codex执行：…”/“Claude执行：…”以及显式cwd/新会话指令完成初始化。

Broker应创建conversation_id、task_id及消息映射，保存route snapshot、session IDs、cwd、feishu message/root/parent IDs；Provider Adapter执行并携task_id/session/turn/queue标识回报；Broker统一状态与结果，再reply原私聊消息。后续裸消息可沿该私聊conversation binding继续；切换provider必须显式并解析同目录唯一session，否则询问。新建/清空/切换工作目录应是显式控制动作并验证工作区allowlist。

并发语义：同一私聊会话执行中收到另一条消息，应明确排队、创建分支、取消/补充或拒绝并记录，不能丢弃；机器人自身回帖及Agent同步事件按来源ID过滤，防回环。群聊是否支持需另定@bot和成员授权，不由私聊需求自动推导。

当前缺口：listener.py无parent_id时直接提示用户回复已有任务完成卡；当前消息只支持text，且没有持久conversation-level provider/session/cwd binding。因此直接DM作为新任务入口尚未实现。推荐先支持白名单用户p2p私聊；首轮显式选择Agent和工作目录/会话，成功后持久绑定；随后允许自然语言连续对话。

#### F-045#2: MPT arguments 解耦：'a'指令字段自描述查询（V4.2.1）

**类型**: F  **来源**: D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md
**关键词**: MPT, arguments解耦, 'a'指令, ARGUMENTS字段自描述查询, queryArgumentsField, getArgumentsByFieldQuery, argumentsLayoutToBuffer, verifyArgumentsFieldQuery, argumentsReadMethod, argumentsVersion=6, EncoderArgumentsV6, batSpeedMode, argumentsFieldLayoutTable, USARTInterface_Recali.c, fieldCount, ArgumentsErrorStatus, 'R'整块读取, EncoderBase.py, Analyzer, A~F协议回归, IAP, series=104, V4.2.1, a3950c3

**日期**: 2026-10-10
**项目**: Analyzer_Encoder_DebugTest（C:\Users\Administrator\Downloads\Analyzer_Encoder_DebugTest；Test Script + Test Report，2026-10-09 V4.2.1 第6轮报告）
**关键词**: MPT, arguments解耦, 'a'指令, ARGUMENTS字段自描述查询, queryArgumentsField, getArgumentsByFieldQuery, argumentsLayoutToBuffer, verifyArgumentsFieldQuery, argumentsReadMethod, argumentsVersion=6, EncoderArgumentsV6, batSpeedMode, argumentsFieldLayoutTable, USARTInterface_Recali.c, fieldCount, ArgumentsErrorStatus, 'R'整块读取, EncoderBase.py, Analyzer, A~F协议回归, IAP, series=104, V4.2.1, a3950c3

**需求场景 / 现象**: MPT 固件的 ARGUMENTS 结构体加字段/改布局（argumentsVersion 3→5→6）时，上位机用 'R' 整块读回 + ctypes 按版本硬解析，必须每版同步改结构体，固件与上位机强耦合。MPT V4.2.1 起固件新增 'a' 指令（提交 a3950c3），让每个字段自描述（名字/偏移/大小/类型/值），上位机据此解耦。

**方案 / 架构**:
- 请求：`'a' + fieldIndex(u8) + CRC8`；响应：`status + payload + CRC8`，payload 小端：schemaVersion(1) argumentsVersion(4) fieldCount(1) fieldIndex(1) fieldOffset(2) fieldSize(1) fieldType(1: 0=u8/1=u16/2=u32) nameLength(1) name value。
- fieldIndex >= fieldCount 时固件回 status=ArgumentsErrorStatus(2)，作为遍历结束信号。真机 34 个字段，值与 'R' 整块逐字节一致（2026-10-08 验证）。
- 上位机：从 index=0 遍历到结束信号，校验响应回显 index、fieldCount==实际条数、上限 64 个字段；任一步失败整体返回 None，不返回半成品。
- 兼容策略（折中，并未彻底去掉结构体）：`argumentsLayoutToBuffer` 按 offset 把字段值拼回原始字节（空洞补 0，总长按 4 字节向上取整，真机 72B），再喂给原有 `ArgumentsHeader/EncoderArgumentsV5/V6.from_buffer_copy` 解析，所以下游代码零改动；通过 `modes["argumentsReadMethod"]`（"R" 默认 / "a"）或 `getArguments(readMethod=)` 切换，`layout` 同时保存在 `Arguments.argumentsLayout` 里。
- `byName` 字典（name→小端整数）可直接按字段名取值，是真正解耦用法的入口，目前未被主流程使用。

**关键文件与接口**（Test Script 目录）:
- `EncoderBase.py:1101-1248` — ARGUMENTS_FIELD_QUERY=ord('a')、queryArgumentsField（state: ok/end/status/fail，重试3次）、getArgumentsByFieldQuery、argumentsLayoutToBuffer、verifyArgumentsFieldQuery（'R' vs 'a' 逐字段对照 + 未覆盖区间非零检测）
- `EncoderBase.py:1306` getArguments(readMethod) ；`EncoderBase.py:2728+` Arguments.__init__/initArgumentsFromBuffer 里 readMethod=="a" 分支；`EncoderBase.py:2814-2822` argumentsVersion 5/6 → EncoderArgumentsV5/V6
- `DataFormatter.py` EncoderArgumentsV6（V5 末尾多 batSpeedMode，其余偏移不变）
- `test_mpt_protocol_regression_AtoF.py:1729` 回归脚本显式切 'a'；`test_iap_mpt20_standalone.py` IAP 刷机流程
- 协议脚本：mpt_0x64_protocol.py(RS485/422 0x64，5/7字节两种帧)、mpt_ssi_protocol.py、mpt_bus_protocol.py、mpt_t485_protocol.py、bissc_protocol.py；CRC.py(CRC8 多项式 x8+x7+x4+x2+x1+1)、Analyzer.py(M487_Universal 读取器 USB)

**验证结果**（报告 V4.2.1_L6EB981C478199E94，2026-10-09，真机）:
- IAP：1941/1941 包、496736 字节、43.3s，整区擦除(page7~127+Bank2)+0x5EE5 校验+0x6FF6 复位，刷机后 argumentsVersion 3→6、series 105→104。
- 全程 'a' 路径读 Arguments 的 A~F 回归：20 项主流程全 PASS，42 组分辨率覆盖矩阵全 PASS，CRC 失败 0，656.1s。'a' 路径首次在完整回归下验证通过。
- 基线 Arguments（'a'读出）：series=104, interface=202, baudrate=2500000, busID=31, internalResolution multi16/single17, hallNumber=9, rotorSize=15, sectionNumber=36, software=67240192, algoVersion=4060, batSpeedMode=0。

**踩坑 / 限制**:
- 固件字段表 `argumentsFieldLayoutTable`（USARTInterface_Recali.c）是人工维护静态数组：固件给 ARGUMENTS 加字段忘加表项时，'a' 会静默漏字段；用 verifyArgumentsFieldQuery 查 uncoveredRanges 里 nonZero 区间来发现。
- 'a' 不报告对齐空洞/尾部 padding，拼回时补 0。
- 老固件（argumentsVersion<6、series=105 等）不支持 'a'，需回退 'R'；刷机前读取仍走旧路径。
- 'a' 每字段一次往返（34 次），比 'R' 慢，高频读取场景别用。
- 后续解耦待办：主流程仍依赖 ctypes 结构体；若要彻底解耦，应改用 byName/字段名 + offset 的动态映射，并保留 'R' 兜底；写入侧（getUpdateArguments/dict_to_init_arguments）仍按 argumentsVersion 分支硬编码，未解耦。

**状态**: 已完成（只读分析归档；未改动任何脚本/固件）

#### F-088#2: MES交接续做组成能力与SN入口清理

**类型**: F  **来源**: D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md
**关键词**: MES, composition, 分母, 生效时间, SN, 平台边界

**关键词**: MES, composition, 分母, 生效时间, SN, 平台边界

**需求场景**: 用户要求继续执行Claude交接，推进明确授权的代码文档项，等待新流程且不测试。

# 交接续做结果（未测试）
C1/C3代码已实现：分母/有效区间/同字段递归、共享类型与依赖保护、dependencies.test字面量类型。COMP-UNIT-001至005、007、008及依赖字段断言已编写未执行。
B部分：删除旧SN前端文件与双端路由、BUSINESS_NAV、通用追溯snHits/SnService耦合；exec/runHits及SN后端/权限/迁移因A依赖保留，B未整体完成。
F：新增现行口径，修订20份历史设计/手册/任务记录，PDF/Word等历史导出未重生成。
静态复核：独立review代理R4/R6无Blocker/Major，兼容用例建议已补；主控另行读取差异。没有执行测试/构建/类型运行检查/服务/浏览器/部署/库写入/提交。
未执行建议命令：npm test -w mes-server；npm run test:integration -w mes-server；npm run build。真实浏览器验收旧SN页面不可用、通用追溯权限边界、设计器新配置正常与非法分母/日期边界均待用户授权。
环境风险：TESTING.md要求唯一测试业务库，交接称本机业务库；本次未选择数据源、未导入、未改运行配置。
后续依赖：A/E用户新流程；C2序号起点口径；C4随执行改造合成集成测试；D等待导入指示；G测试授权及部署条件；bom_entry能力配置尚未写入运行系统。
SIRE台账实际登记晚于部分实现（流程偏差保留），未伪造阶段执行时间。工具要求三路初审与交叉核验，本轮实际独立复核一路，未伪造其余复核，单元延后收敛；实现结果不等于功能验收通过。

#### F-090: MES 当前界面易用性审查：待办、导航与低代码配置缺口

**类型**: F  **来源**: D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md
**关键词**: MES 易用性, 待办直达, 人员指派待办, 移动端导航, 明细行设计器, 低代码用户体验, 操作手册过期

**日期**: 2026-10-23
**项目**: MES / D:\code\mes
**关键词**: MES 易用性, 待办直达, 人员指派待办, 移动端导航, 明细行设计器, 低代码用户体验, 操作手册过期

**需求场景 / 现象**: 对当前 MES 工作区的业务端和管理端做静态易用性审查。发现待办卡片仅跳转到模块而不定位记录；待办未按节点指派执行人过滤；业务端窄屏菜单退化为横向滚动栏；明细行运行时能力无可视化配置入口；老手册正文仍保留生产执行旧入口；列表操作隐藏在行尾菜单，明细行在窄屏横向滚动。

**根因**: UI 交互路径与最新能力配置不同步：TodoPage 只构造模块路由；组织指派能力没有同步到工作台查询；BusinessLayout 的 mobile class 直接采用横向 flex；detailLines 配置只在 schema/runtime 支持，没有设计器编辑器；手册保留历史章节。

**方案 / 架构**: 本轮只读审查，不改代码。按影响建议先处理待办记录直达和执行人匹配，再优化移动导航、补齐明细行设计器，并更新当前操作手册。

**关键文件与接口**:
- `packages/runtime/src/lowcode/pages/TodoPage.tsx:23-26` — 待办卡片目标只到 `/app/<moduleCode>`。
- `packages/runtime/src/components/layout/BusinessLayout.tsx:27-33` — 窄屏导航横向滚动。
- `packages/runtime/src/lowcode/components/DetailLines.tsx:45-84` — 明细行由运行时 schema 驱动；窄屏表格横向滚动在 92-123 行。
- `docs/PROGRESS.md:466-480` — 设计器缺明细行配置；待办仍按角色统计而非指派人。
- `docs/manual/MES系统完整操作手册-白话文版.md:3` — 手册标注旧流程过期，但正文仍保留旧入口。

**实施步骤**:
1. 静态读取当前组件、设计契约、操作手册和最新进度条目。
2. 对照源代码确认每条交互路径，区分已知实现缺口与需浏览器验证的推断。

**验证方法**: 只读代码/文档核对。未启动服务或浏览器、未运行测试/构建；需用户授权后通过岗位用户和窄屏真实路径验收。

**踩坑**: 老手册第一页有过期声明，但长正文和 PDF 仍保留旧流程内容；单看声明或文件标题会误以为它可作当前新手指南。

**状态**: 已完成（静态审查，运行时未验证）

#### F-FRONTEND-MINPLAN: 最小前端项目开发计划模板

**类型**: F  **来源**: @SIRE_ROOT@\sire_vectors.sqlite3
**关键词**: 前端, 项目计划, 最小交付, 验收

最简单前端项目计划的可复用模板：1. 明确一个页面和核心目标；2. 初始化项目并完成静态结构；3. 添加必要样式和一个核心交互；4. 在桌面与移动端检查正常路径及空数据/错误输入边界；5. 构建并发布。验收标准应包括页面可访问、核心流程可完成、响应式基本正常、无明显控制台错误。

#### F-MD-20260924-001: 寄存器梳理 TXT 转 Markdown

**类型**: F  **来源**: @USER_HOME@\Documents\Codex\2026-09-24\zhuan\outputs\v3.4.6-registers.md
**关键词**: Markdown, 寄存器, 文本转换, 原始顺序, 空字段, 异常字段

**日期**: 2026-09-24
**项目**: 文档转换
**需求**: 将寄存器梳理 TXT 转成 Markdown。

**结果**: 已生成 Markdown 表格文件，按原文分组和顺序保留 185 个地址条目；异常字段不做猜测，并单独记录原始尾部字段。

**验证**: 9 个分组、185 个地址行、重复 0x42 保留。

**关键词**: Markdown, 寄存器, 文本转换, 原始顺序, 空字段, 异常字段

#### H-002: GitLab 操作优先使用可见网页

**类型**: H  **来源**: @USER_HOME@\sire_global\global_dev_habits.md
**关键词**: GitLab, 操作优先使用可见, 网页

**日期**: 2026-09-20
**来源**: 用户明确要求“记住这个规则”
**偏好**: 涉及 GitLab 仓库、Pipeline、Runner 或发布状态时，优先通过用户可见且已登录的 GitLab 网页直接操作和查看；不能用 GitHub 代替。网页未登录时先请用户登录；除非用户另行要求，不默认改走命令行或其他平台。
**应用范围**: GitLab 相关任务
**优先级**: 高
**状态**: 生效中

#### H-003: “打开 GitLab”使用指定网页入口

**类型**: H  **来源**: @USER_HOME@\sire_global\global_dev_habits.md
**关键词**: 打开, GitLab, 使用指定网页入口

**日期**: 2026-09-20
**来源**: 用户明确要求
**偏好**: 用户说“打开 GitLab”时，默认打开 `http://[private-ip-redacted]:8888/`，让用户先在网页登录；用户确认登录后，再由助手通过网页直接操作 GitLab。
**应用范围**: 所有 GitLab 相关任务
**优先级**: 高
**状态**: 生效中

#### K-26b560f247dd: driverSoftware 固件仓库路径

**类型**: K  **来源**: @USER_HOME@/.kingkong_driver/workspace.json
**关键词**: driverSoftware, firmware, 固件仓库, @CODE_ROOT@/driver, workspace.json

用户确认 driverSoftware 对应的舵机固件仓库路径为 @CODE_ROOT@/driver。已写入 @USER_HOME@/.kingkong_driver/workspace.json 的 repos.firmware.path。验证：JSON 可解析，配置值完全匹配；目录存在性已检查为 True。

#### K-CODEBASE-MAP-20260924: @CODE_ROOT@ 全部项目：仓库清单与架构关系

**类型**: K  **来源**: @CODE_ROOT@\.sire\runs\R20260924-202722\requirements.md
**关键词**: codebase map, repository inventory, EncoderPlotter, driverSoftware, analyzer, MES, submodule

当前工作区项目总览。14 个顶层 Git 根：analyzer_code、driver、driverSoftware、EncoderPlotter1-5、EncoderPlotter_0703_01/02/03、EncoderPlotter_0903_01、recalibration、tools_credential_generator；3 个无 Git 源码目录：claude-code、mes、mes-admin。EncoderPlotter 九个快照及 recalibration 复用 sub_algorithm/sub_automation/sub_common/sub_embedded 四组件类型，父仓 gitlink pin 见逐项目记录。设备软件链：EncoderPlotter/driverSoftware 经 analyzer_code/Analyzer 与 RS485 连接 driver 固件；mes 提供编码器生产/release/calibration 工作流。仓库清单、分支/HEAD、架构和测试/构建入口的来源证据在 .sire/runs/R20260924-202722/evidence/U-01..U-04/impl/analysis.md。本次仅静态分析；未运行项目测试、构建、硬件或发布。仅新增摘要/任务记录，不导入全量源码 chunks、.env、日志、样本或二进制。

#### K-MODULE-SUB-ALGORITHM-20260924: 子模块类型：sub_algorithm 标定算法

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter1\controller\python\sub_algorithm
**关键词**: sub_algorithm, calibration, V4060, runtime config, algorithm

跨仓组件类型摘要：sub_algorithm 承担编码器角度计算、再标定与 V4060 等算法/配置。被 9 个 EncoderPlotter 快照和 recalibration 复用，父仓 gitlink 固定可复现版本，各快照 pin 不同。关键静态风险：recalibration 当前检出 step4_GenerateV4060.py 引入 sub_common.dpbFlashLayout，但当前 common 检出无该文件；其父仓 gitlink 与算法检出也不一致。只存组件职责与 pin 关系，不导入算法源码/测量样本。

#### K-MODULE-SUB-AUTOMATION-20260924: 子模块类型：sub_automation 环境与工厂自动化

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter1\controller\python\sub_automation
**关键词**: sub_automation, automation, factory, environment, PCBA, flash

跨仓组件类型摘要：sub_automation 封装环境设备、气泵、工厂刷写与 PCBA 自动化；不同 EncoderPlotter 快照 pin 可不同，0703_03 有专门 flash/PCBA 工具。自动化和直接硬件 CLI 会发出实体控制命令；本次仅做静态分析，未连接/操作设备。

#### K-MODULE-SUB-COMMON-20260924: 子模块类型：sub_common 协议与公共结构

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter1\controller\python\sub_common
**关键词**: sub_common, protocol, structs, config, logging, gitlink

Cross-repository summary: sub_common is the Python common layer for protocol frames, structs/registers, definitions/configuration, and logging. JavaScript and firmware have separate corresponding implementations that must remain aligned; each parent gitlink pins the exact common version. EncoderPlotter4 has an uncommitted TPB overlay modifying Defines.py/config.py/utilities.py. recalibration has a sub_algorithm gitlink/checkout mismatch, and the current algorithm imports a dpbFlashLayout module absent from the checked-out common layer.

#### K-MODULE-SUB-EMBEDDED-20260924: 子模块类型：sub_embedded Analyzer 与设备通信

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter1\controller\python\sub_embedded
**关键词**: sub_embedded, Analyzer, embedded, device communication, IAP

Cross-repository summary: sub_embedded handles Analyzer/device communications, device drivers, and selected IAP/Flash operations. Each parent gitlink pins the implementation. HTTP IAP gates are defined in the parent project's qa_api route layer only where that API exists; applicability varies by snapshot and EncoderPlotter_0703_03 has no qa_api. Firmware writing can affect hardware; static repository analysis is not hardware validation.

#### K-OTA-V4065-POWERLOSS-HALL-20260922: OTA 功能支持断电检测错误 Hall

**类型**: F  **来源**: @CODE_ROOT@/EncoderPlotter1/controller/python/startup_info.py
**关键词**: OTA, V4065, DPT15, RS485, NoMulti, 断电检测, 错误Hall, 首次启动信息, 0x8A, Build ID

功能记录：EncoderPlotter 已支持 DPT15、V4065、NoMulti、RS485 设备的首次启动信息查询，用于 OTA 后断电检测错误 Hall。软件手动发送设备命令 0x8A，通过现有通信调度接收 37 字节响应，校验标识 0x56385342、协议版本 1、数据长度 36、CRC8(poly 0x97)及字段关联关系；两个 64 位 Build ID 以十六进制字符串保存。页面显示读取完成、掉电记录有效性、内外圈历史 Hall、是否传入算法、启动状态、判断来源和选定 Hall。设备条件：arguments.algorithm=4065、rotorInnerSize=15、model=0 或缺失、DPT/RS485。验收向量已通过，Python/JavaScript 静态检查和 13 项协议测试通过；真实硬件 OTA 场景仍需现场验证。

#### K-REPO-ANALYZER-CODE-20260924: analyzer_code：USB分析仪桥接固件

**类型**: K  **来源**: @CODE_ROOT@\analyzer_code\main.c
**关键词**: analyzer_code, Nuvoton M487, M480, USB, RS485, RS422, BiSS, SSI, Keil

静态分析基线：HEAD c6bf7e7d0551a6d7a0af53641a931dafc096d24c，detached、干净。Cortex-M4 Nuvoton M487/M480 固件，连接 USB 与 RS485/RS422、BiSS/SSI 编码器。入口 main.c:105-154，进入 AnalyzerLoop/USBLoop；USB 收发分派见 USB/usb.c:168-211,273-355，命令实现见 Devices/analyzer.c:179-187。Keil 工程 Analyzer.uvprojx。未发现标准 README、CI 或自动测试门禁；本次未构建/接设备。协议与 driverSoftware、EncoderPlotter 有跨仓耦合，构建依赖 Keil 工具链。

#### K-REPO-CLAUDE-CODE-20260924: claude-code：不完整的 Electron/Python 样板

**类型**: K  **来源**: @CODE_ROOT@\claude-code\src\main\index.ts
**关键词**: claude-code, Electron, Vue3, JSON-RPC, NDJSON, IPC, no Git

无 Git 根、无 README。Electron/Vite + Vue 3/TypeScript；main 启用 contextIsolation 并禁用 nodeIntegration。IPC 有 python:call、python:status、app:versions；只有 python:call 调用 Python 方法。bridge.ts 以 JSON-RPC 2.0/NDJSON stdio 启动子进程，支持 timeout、重启退避和优雅退出。当前快照缺少 py/main.py、preload 和 renderer 源目录；配置和 py:build 指向缺失后台。静态完整性缺口，未尝试运行。

#### K-REPO-CREDENTIAL-GENERATOR-20260924: tools_credential_generator：PBKDF2 凭据生成器

**类型**: K  **来源**: @CODE_ROOT@\tools_credential_generator\src\preload\index.js
**关键词**: credential generator, Electron, PBKDF2, SHA-256, IPC security

Git 分支 feature/optimize-ui，HEAD 4beeb72fcf8298d1029691f12e80816801277596；未跟踪 .idea/ 与 yarn.lock。Electron-Vite + Vue 3；preload 使用 16-byte random salt、PBKDF2-SHA256 200k rounds 生成 32-byte 派生值，写入 Electron temp 的 .credentials；产物为加盐校验值，不是加密内容。输入 type=text 不遮蔽。Renderer API 暴露通用 child_process.exec、resolve、readFile、write2File；temp path 被插入 Explorer exec 命令，建议窄化 IPC/参数化启动。无自动测试。

#### K-REPO-DRIVER-20260924: driver：STM32G473 BLDC/伺服固件

**类型**: K  **来源**: @CODE_ROOT@\driver\Core\Src\main.cpp
**关键词**: driver, STM32G473, BLDC, servo, RS485, bootloader, DBANK, firmware

静态分析基线：HEAD af0abcb4b86d613a81e8ee0835a08746b2251d66，detached，tag v3.4.6；存在未跟踪 .idea。STM32G473QETx APP+Bootloader 固件。APP 入口 Core/Src/main.cpp；USART1 RS485/DMA/CRC 命令分派见 Core/Src/register_protocol.cpp:60-185，FOC/电流/PWM/安全控制在 Core/Src。Keil MDK-ARM/driver.uvprojx；after-build 走 extract_full.py 生成 release/driver.bin 与 release/BUILD_INFO.txt。tests 混合主机测试和需设备脚本。Core/Src/system_init.cpp:10-51 可修改 DBANK Option Bytes 并重启，属于硬件敏感路径；本次未构建/刷写/运行硬件测试。

#### K-REPO-DRIVERSOFTWARE-20260924: driverSoftware：FastAPI/Electron 操作员桌面端

**类型**: K  **来源**: @CODE_ROOT@\driverSoftware\server.py
**关键词**: driverSoftware, FastAPI, Electron, HID, Analyzer, protocol, calibration, Nuitka

静态分析基线：分支 feature/offline-detection-dev，HEAD 6e09c7688c5eec51671c9cc83c09d416ea2abedb，干净。FastAPI 后端 + ESM 前端 + Electron；server.py:635-665 创建服务，REST/WebSocket 路由约 :953+；core/protocol.py 与 commands.py 实现协议/命令，reader_mp.py 隔离 Analyzer reader，fullpipe_worker.py 负责标定管线，fw_profile.py 管固件配置。通信链：桌面端→FastAPI→HID/Analyzer→RS485→driver 固件。scripts/build.bat 调 Nuitka/electron-builder；pytest.ini 限定 tests/unit，硬件脚本需设备。本仓 VERSION/electron package 为 0.13.11，但 describe 是 win-smoke-v0.14.0-beta.1，发布前需核对版本来源；未运行测试/构建。

#### K-REPO-ENCODERPLOTTER-0703-01-20260924: EncoderPlotter_0703_01：DPB409 硬件上位机

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter_0703_01\controller\python\Encoder.py
**关键词**: EncoderPlotter_0703_01, DPB409, Electron, Vue2, Python, hardware CLI, submodule

静态分析基线：feature/dpb-409，HEAD 9649f4af49fb504413b64c3022773804a3747d0c；两个未跟踪硬件脚本 command_sender.py、xxxx.py。版本 4.10.0；父仓 pin：algorithm e297c0d、automation 3332eb2、common e717cd7、embedded 78f228f。npm start/build:app；dev-setup 四项 Python 测试，CI 六项（另含 product_info 与 DPB flash layout）。command_sender 可上/断电、设 LED preset、发自定义硬件命令；xxxx.py 进入/退出再标定并读 Hall，自述不写 Flash；均不属于 HEAD。提供 qa_api/loopback HTTP。未运行硬件或测试。

#### K-REPO-ENCODERPLOTTER-0703-02-20260924: EncoderPlotter_0703_02：develop 硬件上位机

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter_0703_02\controller\python\Encoder.py
**关键词**: EncoderPlotter_0703_02, develop, Electron, Vue2, Python, IAP, submodule

静态分析基线：develop，HEAD 6bf8c66c6de9e1b61a7bd5dddf6c2e8addbd863f，干净，版本 4.10.0。子模块 pin：algorithm 8af2836、automation 3332eb2、common 017a0d9、embedded fd87399。npm start/build:app；CI/dev-setup 列 build_info、safe_name、V4060 runtime config、qa_api 四项 Python 测试。旧版 IAP 使用调用方 chosenSoftwareVersion 查版本参数；有 qa_api HTTP 接口。未运行测试/设备。

#### K-REPO-ENCODERPLOTTER-0703-03-20260924: EncoderPlotter_0703_03：旧版工厂刷写与 PCBA

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter_0703_03\package.json
**关键词**: EncoderPlotter_0703_03, factory tools, PCBA, flash, 4.7.17, no CI

静态分析基线：feature/flash-and-pcba，HEAD 1f5c515a9ffaa21cc475381bfb99591eef5413ca，干净；相对本地跟踪 ref ahead 1，未 fetch。版本 4.7.17。无 .gitlab-ci.yml、docs/dev-setup.md 或 qa_api。package.json 提供 npm start、npm test（node controller/test/testRunner.js）、build-flash、build-flash-v2、build-pcba、build-factory-tools 及 dist 打包。子模块 pin：algorithm 8af2836、automation 30b1c3f、common 8c06f41、embedded 85d1274。sub_algorithm 本地 feature/algoV4000 相对本地 origin behind 8，automation 本地分支 ahead 1，检出仍匹配 gitlink。无 HTTP IAP 路径。

#### K-REPO-ENCODERPLOTTER-0903-01-20260924: EncoderPlotter_0903_01：新版 IAP BIN/Footer 解析

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter_0903_01\controller\python\Encoder.py
**关键词**: EncoderPlotter_0903_01, IAP, parse_iap_bin, flash_layout, Footer, submodule

静态分析基线：feature/iap，HEAD dd1278c2103cc43406b28e083a1fcfd62ccb0d6d，干净，版本 4.10.0。子模块 pin：algorithm b1d539a、automation 3332eb2、common c53a7b2、embedded 226a010。npm start/build:app；CI/dev-setup 四项 Python 测试：build_info、safe_name、V4060 runtime config、qa_api。与前三个旧快照不同，此版有 parse_iap_bin.py 和 flash_layout.py 解析 BIN/Footer；HTTP IAP 需显式 --http-enable-iap。未运行测试/设备操作。

#### K-REPO-ENCODERPLOTTER1-20260924: EncoderPlotter1：V4065 与 IAP 快照

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter1\controller\server.js
**关键词**: EncoderPlotter1, Electron, Vue2, Python, V4065, IAP, submodule

静态分析基线：feature/lingxi-dpt-iap-preserve-zero，HEAD b9784c457b410bda20cfaac257abe374e6edf54c，干净；本地 origin/develop ref ahead 29（未 fetch）。Electron/Vue2/Vuex + Python 上位机，入口 controller/server.js，Python main.py→Server.py→Encoder.py，JS/Python 以二进制 stdin/stdout 帧通信。子模块 pin：algorithm b1d539a、automation 3332eb2、common b8d898b、embedded 5da3d89。支持 V4065 查询与相关 IAP 改动；npm start/build:app。共享 Python 测试四项：build_info、safe_name、V4060 runtime config、qa_api。IAP 默认关闭/需显式开关；旧注释“未实机验证”与指南/ADR 的防止刷坏设备理由不一致，本次未验证硬件。

#### K-REPO-ENCODERPLOTTER2-20260924: EncoderPlotter2：MPT-G 参数兼容快照

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter2\controller\server.js
**关键词**: EncoderPlotter2, MPT-G, Electron, Vue2, Python, submodule, encoder

静态分析基线：feature/mpt-g-remerge-2，HEAD 0d5897b5a94c95fa5a7c13071c5d656293032dfb，干净；本地 origin/develop ref ahead 8（未 fetch）。共用 Electron/Vue2/Vuex + Python 通信架构；MPT-G 参数兼容。子模块 pin：algorithm fd85f15、automation 3332eb2、common ce132d2、embedded bb45bb4。npm start/build:app；CI 与 docs/dev-setup 同列四项 Python 测试：build_info、safe_name、V4060 runtime config、qa_api。未运行测试/构建。

#### K-REPO-ENCODERPLOTTER3-20260924: EncoderPlotter3：SN/IAP 与 Linux 包路径快照

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter3\controller\server.js
**关键词**: EncoderPlotter3, SN, statorsn, IAP, Linux packaging, Electron, submodule

静态分析基线：feature/xingdongjiyuan-sn，HEAD 6878681a76087f8233904f5c1a877b5b21c375a0，干净；本地 origin/develop ref ahead 14（未 fetch）。Electron/Vue2/Vuex + Python 上位机，含 SN/IAP 修正与 Linux 包目录名修复。子模块 pin：algorithm f67de7d、automation 3332eb2、common 516031a、embedded bce0bac。npm start/build:app；CI 与 docs/dev-setup 同列 build_info、safe_name、V4060 runtime config、qa_api 四项。未运行测试/构建。

#### K-REPO-ENCODERPLOTTER4-20260924: EncoderPlotter4：含未提交 TPB overlay

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter4\controller\server.js
**关键词**: EncoderPlotter4, TPB, Electron, Vue2, dirty worktree, IAP, submodule

静态分析基线：codex/feature/tpb-requirements，HEAD 6bf8c66c6de9e1b61a7bd5dddf6c2e8addbd863f；主仓五处修改且 sub_common dirty，无 upstream。改动路径：controller/defines.js、controller/encoder.js、controller/python/qa_api/encoder_profile.py、routes_iap.py、tests/test_profile.py；common Defines.py/config.py/utilities.py。与 EP5 已提交 HEAD/gitlinks 相同，当前工作树含未提交 TPB 部分实现。TPB productInfoList 为空，版本/算法/Flash 地址未配齐，routes_iap 要求登记版本，不能声称支持 TPB IAP。pin：algorithm 8af2836、automation 3332eb2、common 017a0d9、embedded fd87399。需按 HEAD 与 dirty overlay 分开理解；没有对 dirty overlay 的独立测试覆盖结论。

#### K-REPO-ENCODERPLOTTER5-20260924: EncoderPlotter5：develop 干净基线

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter5\controller\server.js
**关键词**: EncoderPlotter5, develop, Electron, Vue2, Python, submodule, encoder

静态分析基线：develop，HEAD 6bf8c66c6de9e1b61a7bd5dddf6c2e8addbd863f，干净。与 EP4 的已提交 HEAD/gitlinks 相同，但无其未提交 TPB overlay。子模块 pin：algorithm 8af2836、automation 3332eb2、common 017a0d9、embedded fd87399。npm start/build:app；CI 与 docs/dev-setup 四项 Python 测试为 build_info、safe_name、V4060 runtime config、qa_api。共享架构入口与 IAP 门禁见 EncoderPlotter 系列记录；本次未运行测试/构建。

#### K-REPO-MES-20260924: mes：Vue/Express MES 与编码器生产模块

**类型**: K  **来源**: @CODE_ROOT@\mes\backend\src\index.ts
**关键词**: mes, MES, Express, TypeORM, Vue3, Pinia, SQLite, PostgreSQL

无 Git 根。README 自称 React 18，但当前 frontend/package.json、main.ts 和 Vue 页面使用 Vue 3/Pinia/Vue Router。Node/Express + TypeORM 后端支持 SQLite/PostgreSQL，Electron 壳；routes 覆盖 auth、工单、库存、质检、追溯、设备和 encoder production/release/calibration。database.ts 设置 synchronize:true，启动时 seed；生产迁移行为需谨慎核对。README/docker compose 含演示凭据/fallback，不保存实际值或 .env。存在 unit/integration/Playwright 脚本，本次未运行。

#### K-REPO-MES-ADMIN-20260924: mes-admin：本地演示数据管理界面

**类型**: K  **来源**: @CODE_ROOT@\mes-admin\src\App.vue
**关键词**: mes-admin, Vue3, TypeScript, Vite, Electron, mock data, no backend

无 Git 根。Vue 3 + TypeScript + Vite + Electron 管理界面样板；App.vue 用本地数组模拟用户/角色/状态，无 API、数据库或认证后端。Electron main 只加载前端，preload 仅暴露平台名。npm test 是 Node smoke test，npm run build 为 vue-tsc + Vite；本次未运行。

#### K-REPO-RECALIBRATION-20260924: recalibration：在线标定与文件回放

**类型**: K  **来源**: @CODE_ROOT@\recalibration\RecalibrationV0_4.py
**关键词**: recalibration, calibration, Analyzer, replay, sub_algorithm, gitlink

静态分析基线：分支 feature/debug-from-file，HEAD b9f73c5fa6f7b0534fa9e298a7281ed8d9320646；root 的 sub_algorithm 为 modified。父仓 gitlink 固定 f8eee4a，当前检出 a3c7526，不匹配；其他三类子模块检出与 parent pin 相符。RecalibrationV0_4.py 组合 Analyzer、encoder、算法，在线采集/生成/写入/读回；debugFromFile.py 重放数据。静态发现当前算法 step4_GenerateV4060.py 导入 sub_common.dpbFlashLayout，但当前 common 检出没有该文件，相关路径未运行验证。不得将调试 ZIP、测量数据或构建文件归档。

#### K-angle-reading-liubobo-6993b3bd: liubobo-angle-hall RS485 0x43 角度读取实现完成

**类型**: F  **来源**: @CODE_ROOT@/EncoderPlotter1/liubobo-angle-hall.py
**关键词**: 角度读取, RS485, 0x43, DPT, DPB, liubobo, 独立脚本, 硬件验证

修正 liubobo-angle-hall.py 的角度读取功能。

改动：
1. RS485 命令从 0x33 改为 0x43（DPT/DPB 标准双角度命令）
2. 启动诊断日志增强（配置/readout/status 返回值检查）
3. 解析诊断日志增强（有效记录数、丢弃原因统计）
4. 超时字节数优化（5→8）

硬件验证通过：
- 9034+ 条样本
- 内圈 17.44°±0.0001°
- 外圈 227.68°±0.00002°
- 数据稳定性极好

脚本可直接交互使用：e → start angle → stop → q
输出 TSV 格式 angle_YYYYMMDD_HHMMSS.txt

#### K-driver-v345-doc-drift: 舵机固件文档与当前实现存在历史漂移

**类型**: K  **来源**: @CODE_ROOT@\driver\docs\system_architecture.md
**关键词**: 文档漂移, ISR优先级, 内存布局, driver.sct, system_architecture

docs/system_architecture.md 的架构图/内存图来自较早提交，部分 ISR priority、LR_APP 起址和 CCM load 描述与 AGENTS.md、当前 register_protocol.cpp/driver.sct 不一致。使用文档做烧录或性能判断前必须以当前源码、scatter、build map 为准。

#### K-driver-v345-full-repository-analysis: STM32G473 舵机固件仓库 v3.4.5 全量架构与风险分析

**类型**: K  **来源**: @CODE_ROOT@\driver\AGENTS.md
**关键词**: 舵机固件, STM32G473, v3.4.5, FOC, BLDC, 编码器, RS485, Bootloader, OTA, Flash, CCM, SRAM, CombinedConfig, ReCal, Keil, JLink

仓库全量代码分析（SIRE v6）

范围与基线：仓库 @CODE_ROOT@\driver；HEAD=8b85b1d07d5354ac2906a0a40a08333b4c4e7ffb；精确标签=v3.4.5；工作区状态：## HEAD (no branch)
?? .idea/。本次只读分析，不修改固件代码，不执行烧录。仓库共约1688个文件；主要目录为 Boot、Core、Encoder、Drivers、MDK-ARM、tools、tests、docs、test、release。粗粒度代码/脚本行数统计：Boot 1,358；Core 14,533；Encoder 108,771（含历史电机归档和标定数据）；Drivers 41,024；tools 4,670；tests 70,791（含数据分析脚本/测试样本）；test 747；MDK-ARM 3,113。当前未跟踪项为 .idea/，未纳入固件源代码结论。

系统定位：这是 STM32G473QETx 的 BLDC 感驱一体舵机固件。物理链路为 PC→USB Analyzer→RS485→STM32G473→三相逆变器/BLDC 电机，另有 J-Link SWD 开发烧录。固件包含 APP、Bootloader、编码器算法和主机侧工具/测试，不是单一裸机驱动文件。

固件架构：Core/Src/main.cpp 负责初始化、ADC 偏置校准、协议/状态轮询和 LED 状态；motor_controller.cpp 负责状态机、FOC ISR、位置/速度/电流闭环、安全动作；foc_engine.cpp、pwm_driver.cpp、current_sensor.cpp 组成电流采集、Park/逆Park、PI 和 PWM；position_controller.cpp、torque_model 与 safety_monitor.cpp 处理位置/速度/力矩模型、限流、过压/过温/失速/通信超时等保护；encoder.cpp 连接双 8-hall 编码器与封闭算法库；register_protocol.cpp 实现 RS485 帧、寄存器、工厂命令、ReCal、EnterBoot 和版本读取；recorder/dwt_profile/lut_store/self_test 提供黑匣子记录、周期计时、补偿表持久化和自检。

硬件时序：TIM1 约20kHz三相中心对齐PWM；ADC5注入采样用于相电流，ADC1-4和DMA采集16路hall；USART1+DMA负责RS485半双工，DE为PA12；CORDIC/FPU用于FOC数学；DWT cycle counter用于时序剖析。当前源码/规则中的优先级方向是 USART/RS485 高于 FOC，FOC 高于编码器计算，PendSV 处理较冷路径；但 docs/system_architecture.md 的旧架构图仍写成 ADC5 priority 0、USART priority 2，和 AGENTS.md/当前源码注释不完全一致，应视为过时文档而不是实现契约。

Flash 与内存：Boot 固定在 0x08000000-0x08003FFF（16KB）；APP 客户区从 0x08004000 开始；OTA hard wall 在 0x0803D000，保护编码器封闭区；编码器库、标定参数/角度/polyfit、CombinedConfig 位于更高地址；CombinedConfig 约在 0x0807E000，APP descriptor 在 0x0807F000。STM32G473要求DBANK=1、2KB页。driver.sct 将热算法表/热ISR/栈分配到 CCM 0x10000000 区，DMA buffer 与通用状态留在 SRAM1/SRAM2，以避免 CPU I-Code/D-Code 和 DMA 争用同一 BusMatrix slave；这是性能与安全不变量。docs/system_architecture.md 仍保留早期的 LR_APP/内存描述，和当前 driver.sct 的 APP 起址/CCM load 细节存在历史差异，复核地址时应以当前 scatter file 和编译产物为准。

Boot/OTA：Boot 读取 RTC backup magic、CombinedConfig device_id 和 APP descriptor；仅在向量表 sane、descriptor 自 CRC 和 APP/ENC-LIB CRC 通过时跳转 APP。OTA 通过 RS485，EnterBoot 需要连续10次；mode A 只写客户 APP 到 0x0803D000 之前，mode B 扩展到 ENC-LIB/更多 user 区，boot 区不允许 OTA；写入完成后以 CRC 和 descriptor 作为提交点，失败/断电应留在 boot 以便恢复。release/driver.bin 是 v3.4.5 正式包，500314 B，BUILD_INFO 标记 app_version v3.4.5、cfg schema 16、ER_APP CRC 0x024EE07F、ENC-LIB CRC 0xC9EC4222、CAL CRC 0x8112DBED、CFG CRC 0x61B5BFC5、build_id 0xD5D5D81B、声明 SHA-256 e7adf9e7727ee94cb057c820c007ccbf019773f8b841b524d6cfffde174f5073。开发规则仍明确推荐 J-Link；产品/现场升级才用 OTA。

配置与协议：CombinedConfig 合并 device_id、RS485 baud index、版本/序列号、电机物性、MotorConfig 和 CRC；v3.4.5 的配置 schema 为16。Boot 和 APP 共享 boot_interface.h 的命令/边界契约。需要特别注意 v3.4.5 的 RS485 波特率配置已可变，offset 13/相关寄存器不能继续假定固定7.5M；工具、设备当前 cfg、boot 默认/扫描行为必须一致，否则会表现为整条链路无响应。

构建链：MDK-ARM/driver.uvprojx 定义 APP、Boot、All 目标；APP Before-Build 调 tools/gen_version.py 从 git tag 生成 Core/Inc/version.h，After-Build 调 tools/extract_full.py 从 AXF/HEX抽取ER_APP、ENC-LIB、CAL、CFG并生成 release/driver.bin/BUILD_INFO.txt；Boot target定义 READ_OUT_PROTECTION_ENABLE。当前机器未安装 Keil/ARMCLANG/fromelf，不能声称本地完成真实编译、链接、scatter 地址或 size 校验。

验证结果：Python compileall 对 tools/tests/test 通过；tests/bootloader/test_trailer_roundtrip.py 全部通过；tools/ota_flash.py --app release/driver.bin --info 通过并正确解析 DRV1、版本和各段 CRC；tests/bootloader/test_crc_parity.py 失败，具体是 ImportError：从 ota_flash 导入不存在的 crc16_ccitt，说明测试与当前实现的符号契约漂移。此前 OTA 实机尝试在分析仪已识别但舵机 ID 0xF/0xE 均无响应，未发生 Flash 写入；本次代码分析同样不做硬件写入。

主要风险/待办：1) 修复或同步 test_crc_parity.py 与 ota_flash.py 的 CRC API；2) 在具备 Keil 后执行 APP/Boot/All 的真实构建并核对 fromelf map、scatter 地址、APP descriptor；3) 统一 system_architecture.md 与当前 ISR/内存布局文档；4) 为 v3.4.5 显式记录默认/现场 RS485 baud 的迁移策略和工具选择；5) 对 Boot target 的 RDP 行为制定可审计的烧录顺序，避免 J-Link 连接触发 mass erase；6) 对 ReCal 写入范围与 CCM load 区做自动化地址重叠检查；7) 测试成功后按项目规则提交硬件测试证据。

限制：本报告是静态全仓库审查加本地 Python/包格式验证；未运行 MCU、未打开 GUI、未接收舵机遥测、未做真实电机运动/温升/保护测试、未做 Keil 编译。因此不能把控制算法实时性、保护动作、RS485 电气稳定性、OTA 实机成功率判定为已验证。

#### K-driver-v345-layout-invariants: 舵机固件 Flash/SRAM/OTA 边界不变量

**类型**: K  **来源**: @CODE_ROOT@\driver\MDK-ARM\driver.sct
**关键词**: STM32G473, DBANK, 2KB, 0x08004000, 0x0803D000, 0x0807E000, CCM, SRAM1, SRAM2, BusMatrix, OTA hard wall

Boot 16KB 位于 0x08000000；APP 客户区从 0x08004000；OTA 不得越过 0x0803D000；DBANK=1 使用2KB页；热表/热代码/栈使用CCM，DMA buffer留SRAM1/SRAM2；CombinedConfig位于高地址封闭/持久化区。地址与加载关系最终以当前 scatter file 和 AXF/map 为准。

#### K-driver-v345-ota-contract: v3.4.5 Bootloader/OTA 协议契约

**类型**: K  **来源**: @CODE_ROOT@\driver\docs\skills\bootloader_ota.md
**关键词**: OTA, RS485, EnterBoot, 10次, mode A, mode B, CRC, descriptor, driver.bin, boot, device_id, baud

OTA 必须先由 APP 连续10次 EnterBoot，再 Ping；mode A 仅写客户区至0x0803D000前，mode B才扩展编码器库/更高 user 区；Boot区不可 OTA；Erase/Write/Crc/J​​ump边界必须拒绝越界；完成后由 CRC 和 APP descriptor 作为提交点。v3.4.5 波特率可配置，工具不得硬编码单一7.5M。

#### K-driverSoftware-commit-squash-preserve-remote: 压缩提交时保留远端历史边界

**类型**: K  **来源**: @CODE_ROOT@/driverSoftware/AGENTS.md
**关键词**: Git, commit, squash, 提交压缩, 远端历史, 工作区状态

driverSoftware 压缩未推送提交时，先以 origin/<branch> 确定改写边界。只压缩远端之后的本地提交；已推送的提交及基底合并提交要保留。执行后核对 HEAD 为远端基线的后代、变更差异、git diff --check 和工作区状态；不推送，保留无关未跟踪证据。

#### K-encoder-iap-lookup-diagnostic: 跨子模块缺失 DPB Flash 布局导致参数请求失败

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter3\controller\python\Encoder.py
**关键词**: IAP, productInfoList, DPT, 423, configFile, availableVersions, 旧进程

算法子模块 step4_GenerateV4060 顶层导入 sub_common.dpbFlashLayout。若主仓锁定的 sub_common gitlink 未含该模块，读取参数过程会报 No module named sub_common.dpbFlashLayout。同步模块时必须连同 DPB 固件 409 的 productInfoList 配置一起引入；真实日志可能加密，先用 @SIRE_ROOT@/decodeLog.js 或同等算法解码。2026-09-24 修复：sub_common 516031a，主仓 d794d22b；6 项 DPB 测试通过，应用 .venv Python 导入成功。

#### K-encoder-unknown-iap-config-fallback: DPT 103 / 固件 423 配置命中与现场旧进程排查

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter3\controller\python\Encoder.py
**关键词**: IAP, 未知固件版本, supportedVersions, productInfoList, series=103, software=423, Encoder.py

DPT(系列103)的软件版本423配置位于 controller/python/sub_common/config.py 的 productInfoList[PRODUCT_SERIES_DPT][423]，虽然截图未显示外层系列键。当前树 getIAPArguments(103,423) 可命中，返回 algorithmVersion=4060 与 9 个 supportedVersions。日志 KeyError 表示运行进程加载的配置与当前树不同或运行代码/目录不同；检查 Python 进程命令行、模块来源文件、开发/打包启动路径，并重启旧进程。不要把查询失败静默降级为空升级列表。回归测试 qa_api/tests/test_iap_arguments.py 验证准确查找。

#### K-fw-v345-register-compat: driverSoftware v3.4.5 寄存器兼容结论

**类型**: K  **来源**: @CODE_ROOT@\driverSoftware
**关键词**: driverSoftware, v3.4.5, 0x42, Rs485Baud, 0x6A, AdcUsableAmp, 0x73, ShellTripC, 0x80, InnerAngle, 诊断快照

舵机固件 v3.4.5 的寄存器协议发生地址复用：0x42 为 Rs485Baud，0x6A 为 AdcUsableAmp，0x73 为 ShellTripC，0x80 为 InnerAngle；旧版本已删除语义不能继续按旧名字 bitcast。主机已同步常量、位型快照集合和诊断快照，并记录 0x42 波特率。相关 53 项回归通过；完整 pytest 因环境长等待中止，未宣称全量通过。

#### K-fw-v345-regread-length: v3.4.5 单点寄存器读取回复长度核对

**类型**: P  **来源**: @CODE_ROOT@\driverSoftware\core\commands.py
**关键词**: v3.4.5, FactoryRegRead, reg_read, expected_rx_bytes, 回复长度, 读取失败

固件 v3.4.5 的 FactoryRegRead 回复布局为 header 1 + subcmd 1 + addr 1 + count 1 + count×f32 + CRC16 2，即 6+4×count。主机旧代码按 7+4×count 等待，多等 1 字节；单点 reg_read 可能被判回复长度不符。已将 core/commands.py 的 expected_rx 修正为 6+4×count。相关 60 项回归通过。

#### K-regread-batch-fallback: 批量寄存器读取全失败时降级单帧重试

**类型**: P  **来源**: @CODE_ROOT@\driverSoftware\core\commands.py
**关键词**: reg_read_batch, 0/163, V2.40, batch fallback, FactoryRegRead, v3.4.5

诊断包显示设备连接、波特率和链路统计正常，但读取全部为 0/N，说明批量 item 结果在上层全部失效。reg_read_batch 现在在整批结果全部为 None 时逐段调用已修正长度的单帧 reg_read，绕过批量编排问题。

#### K-regread-v345-batch-window: v3.4.5 寄存器读取低速限制与 HID 小批量窗口

**类型**: K  **来源**: @CODE_ROOT@\driverSoftware\register_read_failure_analysis.md
**关键词**: 寄存器读取, reg_read, reg_read_batch, v3.4.5, 1Mbaud, device_id, HID, 0/163

重点故障复盘（2026-09-21）：该寄存器读取问题经过较长时间排查，现场最终复现为上位机寄存器页【读取全部】显示 0/163。设备实际在线，device_id=15、固件 v3.4.5、1 Mbaud；单点和小批量读取成功。根因是两个软件限制叠加：v3.4.5 在 1 Mbaud 下单帧最多 3 个寄存器；上位机又把约 50 个分片一次提交给 HID 批处理接口，分析仪整批失败，服务端将结果重组为 None，前端才显示 0/163。修复为按波特率拆帧，并以每批 8 个分片提交后重组。可见页面真实验收显示 163/163，相关测试 22 passed。后续遇到 0/N 必须先查固件版本、波特率、单点/小批量/整页差异和 HID 批量窗口，不能先判硬件故障。

#### K-servo-fw-host-compatibility-register-read: 舵机固件与上位机兼容性：寄存器读取必须按固件能力适配

**类型**: K  **来源**: @CODE_ROOT@\driverSoftware\server.py
**关键词**: 舵机, 固件兼容, 软件兼容, 版本矩阵, v3.4.5, RS485, 波特率, 寄存器读取, HID批处理, device_id, 0/163, 163/163, 需求评审

这是高优先级兼容性问题，后续所有舵机需求、固件升级和上位机改动都必须重点检查固件—软件兼容关系。已验证案例：固件 v3.4.5 在 RS485 1M/1.5M/2M/≥2.5M 下，单帧连续寄存器上限分别为 3/8/13/16；上位机若按统一 16 个或一次提交过多 HID 分片，会导致批量读取整体失败，页面表现为 0/163，但单点和小批量可能正常，容易误判为硬件故障。兼容实现要求：读取能力按固件档案和实际波特率拆分；HID 批处理控制窗口；响应长度按固件协议解析；设备 ID、固件版本、波特率在连接后确认；大版本/需求变更前先核对 firmware_profiles、固件头文件、协议文档和真实页面。验收必须包含可见页面“读取全部”以及边界波特率/异常路径。

#### KB-REF-ENCODER-STATORSN-ARGUMENTS-VERSIONS: arguments 各版本的 statorSN 支持关系

**类型**: K  **来源**: @CODE_ROOT@\EncoderPlotter3\controller\python\sub_common\DataFormatter.py
**关键词**: statorSN, argumentsVersion, v3, v4, DPT, DPB, InitArguments

statorSN 由结构是否声明决定。InitArguments（新格式 v3）、InitArgumentsV2（DPB v4）、DPT_Arguments_V4（DPT v4）包含 16 字节 statorSN。旧格式 EncoderArguments/EncoderArgumentsV1/V2/V3/V255、MPTEncoderArgumentsV4、MPT_Arguments_V5 均不含该字段，解析时会主动移除。前端以 arguments 对象是否拥有 statorSN 属性判断支持。

#### KB-SOL-20260921-REGREAD-ID15: 诊断包 nosn-id15 无法读取寄存器：链路正常，优先核对 RegRead addr+count 协议

**类型**: P  **来源**: @USER_HOME@\Downloads\KingKongDiag\nosn-id15\diag_nosn-id15_20260921_095629_manual.zip
**关键词**: RS485, RegRead, 寄存器, 诊断包, nosn-id15, device_id, 7.5Mbaud, addr, count

上下文：诊断包 diag_nosn-id15_20260921_095629_manual.zip。manifest 显示 device_id=15、baudrate=7500000、connected=true，read_timeouts=0、tx_no_reply=0、tx_exceptions=0、baud_config_failures=0、hid_errors=0。项目固件 Core/Src/register_protocol.cpp:716-732 的 FactoryRegRead 实际读取 p[0]=addr、p[1]=count；请求必须为 [head, 0x01, addr, count, CRC16]，回复为 [head,0x01,addr,count,values(count*f32),CRC16]。docs/protocol/rs485_v3.4.1.md 第5章只写地址(1B)，未明确 count，存在文档/上位机版本错配风险。项目 tests/gui/core/commands.py:242-255 已按 addr+count 发送和解析。诊断包 events.jrn/rings.json.enc/env.json.enc 为加密文件，未能取得实际帧字节，故不能证明具体请求帧或回复帧。建议首先抓原始 TX/RX，确认 ID=0xF、Factory=0x7、sub=0x01、addr、count、CRC，且 expected_rx=1+3+4*count+2；不要把 MIT 捎带读格式与 Factory RegRead 混用。

#### KB-SOL-20260921-V345-HOST: v3.4.5 与当前上位机兼容性审计

**类型**: K  **来源**: @CODE_ROOT@\driver
**关键词**: v3.4.5, 上位机, 波特率, 寄存器映射, RegRead, bootloader

v3.4.5 compatibility audit: firmware bldc_config.h supports baud table 1/1.5/2/2.5/3/4/5/7.5M and defaults cfg index 0=1M; tests/gui core defaults 7.5M in commands.py and reader_wrapper.py. Firmware moved RS485 baud register to 0x42, while host registers.py still names 0x42 kCfgPosKd and 0x09 kStLastAppBuildId; firmware deleted 0x05 and 0x09 read windows. Firmware Factory RegRead/RegWrite require addr+count and host commands.py matches; protocol docs only say address and are stale. Bootloader rules require 7.5M fixed, so APP configurable baud must not be reused for boot OTA unless host explicitly uses boot baud.

#### KB-SOL-20260923-IAP-SN-RESTORE-VERIFY: IAP 后恢复并强制校验编码器 SN

**类型**: P  **来源**: @CODE_ROOT@\EncoderPlotter3\controller\python\iap_sn_restore.py
**关键词**: IAP, SN, statorSN, arguments, 回写, 强制重读, 内部版, 日志

适用于 EncoderPlotter3 编码器 IAP：升级前从 arguments.statorSN 捕获非空 SN；升级数据写入后通过 getUpdateArguments/writeMemory 回写；随后必须 getArguments(forceFromMemory=True) 绕过调试包、从设备 Flash 强制重读并严格比较。只有一致时记录“SN写入成功”；不一致或读取失败必须让 IAP 第三阶段失败。界面诊断通过 internal helper 显示，外部版使用 silentHelper，仅日志保留。修复包 step2/3 路径也必须正确更新外层 iapOriginalSn，避免 Python 闭包局部变量丢失。

#### KB-SOL-20260923-MEDIAN-HALL-LOCK: 中值霍尔检测期间跨组件禁止退出

**类型**: P  **来源**: @CODE_ROOT@\EncoderPlotter3\components\global.js
**关键词**: Ubuntu, 中值检测, 霍尔模式, 退出禁用, Vue2, 会话状态, medianChecking

适用于跨Vue组件保护霍尔模式切换。中值检测状态不能只放在encoder-device组件局部data中，因为退出入口位于analyzer组件；也不能放进configs并持久化，否则异常退出可能留下永久锁。方案是在设备根对象维护会话级medianChecking，开始检测后置true，成功节点及finally置false；analyzer模板显示禁用，同时changeHallMode做事件级守卫。

#### KB-SOL-20260923-SN-DIAGNOSTIC-MEDIAN-LOCK: SN能力诊断与中值检测指令互斥

**类型**: P  **来源**: @CODE_ROOT@\EncoderPlotter3
**关键词**: EncoderPlotter3, SN, statorSN, 0x83, medianChecking, internal, logging

{"knowledge_id": "KB-SOL-20260923-SN-DIAGNOSTIC-MEDIAN-LOCK", "title": "SN能力诊断与中值检测指令互斥", "type": "solution", "context": "EncoderPlotter3读取arguments及运行中值检测时", "problem": "SN不支持日志缺少原因，内外版展示边界不清；中值检测期间其他入口仍可发送设备指令。", "solution_or_decision": "参数读写SN按statorSN字段存在性判断；0x83指令能力按RS485且software>=4.2.2判断。内部版显示完整诊断，外部版仅Python持久日志记录。设备级medianChecking状态同时守卫构建信息、霍尔原始值/减去标定中值及退出霍尔模式入口。", "constraints": ["前端console不进入持久日志", "两种SN能力不可互相推导", "UI disabled之外必须保留方法守卫"], "verification": ["独立Work Reviewer复审PASS", "按用户要求未运行功能测试"], "limitations": ["未进行真机场景验证"], "tags": ["EncoderPlotter3", "SN", "statorSN", "0x83", "medianChecking", "internal", "logging"], "source_artifacts": ["components/encoder/device.js", "components/encoder/device.html", "components/analyzer/analyzer.js", "components/analyzer/analyzer.html", "controller/python/Encoder.py", "components/i18n.js"], "related_tasks": ["SIRE-v6-EncoderPlotter3-sn-diagnostics-median-lock-20260923"], "updated_at": "2026-09-23T09:09:09+08:00"}

#### KB-SOL-20260923-SN-LOG-STATORSN-ONLY: SN状态日志详情统一只显示statorSN

**类型**: P  **来源**: @CODE_ROOT@\EncoderPlotter3\components\encoder\device.js
**关键词**: SN, statorSN, 写入成功, 读取成功, 未识别, 内部版, 日志

SN 日志统一规则：未识别到SN、写入SN成功、读取SN成功三类消息，外部版只显示状态文案；内部版可追加“返回数据”，但内容只能是对应的 statorSN/SN 值，禁止 JSON.stringify 整个响应或 arguments。覆盖 analyzer.js 指令读取路径及 device.js arguments 读写路径。

#### KB-SOL-20260923-SN-PROMPT: 编码器SN空值提示按读写能力区分

**类型**: P  **来源**: components/encoder/device.js
**关键词**: SN, 序列号, statorSN, 空值提示, 读写能力

判断编码器是否支持读写SN时，应检查 arguments 对象是否拥有 statorSN 属性，而非检查属性值真值；空值提示按该能力选择“SN不能为空”或“序列号不能为空”。中英文 i18n 需成对新增。验证：JS语法检查和四类分支测试通过；用户要求不做真实界面测试。

#### KB-SOL-20260923-USB-LOG-ROUTING: 移除 USB 诊断并恢复日志分流

**类型**: P  **来源**: @CODE_ROOT@\EncoderPlotter3
**关键词**: USB, 诊断日志, log.txt, Renderer, console, electron-log

删除临时 USB 全链路诊断时，应移除 main/renderer/controller/Python/sub_embedded 各层的 [USB] 与 diagnosticLog 埋点，同时删除对应诊断文档。恢复 Logger.startDebug('log.txt')/startInfo('log.txt')；Electron 主进程使用 log.initialize()，不启用 spyRendererConsole，使前端 console 只在控制台显示。保留普通连接日志、错误处理和 Linux 串口权限重试。

#### KB-SOL-SN-20260923: SN 支持判定必须按 statorSN 字段存在性，读取结果按版本过滤日志

**类型**: P  **来源**: @CODE_ROOT@\EncoderPlotter3\components\encoder\device.js
**关键词**: SN, statorSN, 再标定, 0x83, 内外部版日志, Vue2, EncoderPlotter3

{"knowledge_id": "KB-SOL-SN-20260923", "title": "SN 支持判定必须按 statorSN 字段存在性，读取结果按版本过滤日志", "type": "solution", "context": "顶部 0x83 指令读取与再标定 arguments.statorSN 共存时，需兼容旧结构体。", "problem": "用 statorSN 值的真假判断会把空 SN 误判为不支持；指令读取结果若回填旧结构体还会伪造支持标志；外部日志不能展示返回详情。", "solution_or_decision": "用 hasOwnProperty 判断结构体是否声明 statorSN；无字段时显示旧序列号输入框；顶部指令无 SN 统一提示未识别到 SN；内部版日志追加返回数据，外部版仅显示操作状态；通信失败不删除已有字段。", "constraints": ["不能让顶部指令读取给不含 statorSN 的旧 arguments 缓存补字段。", "结构体明确缺少字段才隐藏再标定 SN 操作。"], "verification": ["node --check components/analyzer/analyzer.js", "node --check components/encoder/device.js", "node --check components/i18n.js", "py -3.12 -m unittest build_info_test", "py -3.12 -m unittest safe_name_test", "开发版 Electron 启动并拉起 Python 中间件；真实编码器 SN 交互 BLOCKED。"], "limitations": ["未完成真实编码器点击路径验收。"], "tags": ["SN", "statorSN", "再标定", "0x83", "内外部版日志", "Vue2", "EncoderPlotter3"], "source_artifacts": ["components/analyzer/analyzer.js", "components/encoder/device.js", "components/encoder/device.html", "components/i18n.js"], "related_tasks": ["SIRE-20260923-SN"]}

#### KB-hall-plot-current-20260922: 霍尔基线与通电附加数据绘图采集边界

**类型**: P  **来源**: controller/python/sub_automation/pcba/pcba_check.py
**关键词**: 霍尔, 电源控制, Busy, error=3, EncoderErrorBusy, 连续采集, 时序

故障知识：在 PCBA 霍尔采集流程中，如果电源控制开始期间重新启动 Hall 采集，编码器可能返回 error=3（EncoderErrorBusy），并返回 length=0 的空帧。日志证据：第二段采集启动后连续出现 error=3，最终总霍尔帧数等于基线帧数。规避方案：Hall 只启动一次，连续采集 baseline_duration + additional_duration；电源线程等待 baseline_duration 后再切换电流，最后统一停止编码器。

#### P-001: Electron axios localhost连接失败需改用127.0.0.1

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: localhost, 127.0.0.1, IPv6, ECONNREFUSED, Electron, axios

**日期**: 2026-07-04  
**项目**: Emy

**问题分类**: 技术问题

**问题描述**:
```
Electron中axios请求localhost时默认优先尝试IPv6地址(::1)，
若后端服务仅监听IPv4(0.0.0.0或127.0.0.1)，会导致连接被拒绝（ECONNREFUSED）。
前端Vue文件中所有API调用均使用 http://localhost:8001，导致请求失败。
```

**问题根因**: Node.js/DNS解析器在Electron环境中优先解析localhost为IPv6地址  
**解决方案**:
```
1. 将所有前端Vue文件中的 http://localhost:8001 替换为 http://127.0.0.1:8001
2. 将测试文件中的 localhost:8001 也替换为 127.0.0.1:8001
3. Electron主进程(main.js)已使用127.0.0.1，无需修改
```

**涉及角色**: 角色3  
**严重度**: CRITICAL  
**状态**: 已解决  

**关键词**: [localhost, 127.0.0.1, IPv6, ECONNREFUSED, Electron, axios]  
**复用次数**: 2  

---

#### P-003: npx命令缺少--yes标志导致非交互环境挂起

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: npx, --yes, 交互式提示, subprocess, 挂起, 超时

**日期**: 2026-07-04  
**项目**: Emy

**问题分类**: 技术问题

**问题描述**:
```
command_executor.py的execute_npm_create方法中，npx命令未添加--yes标志。
当npx需要安装未安装的包(如degit)时，会提示"Ok to proceed? (y)"，
在subprocess.run的非交互环境下导致命令挂起或超时。
```

**问题根因**: npx默认在安装未安装的包时需要交互式确认  
**解决方案**:
```
1. 所有npx命令统一使用 npx --yes 前缀
2. npm create命令添加 -- --yes 参数
3. create-next-app等工具自带的--yes参数也一并添加
```

**涉及角色**: 角色3  
**严重度**: HIGH  
**状态**: 已解决  

**关键词**: [npx, --yes, 交互式提示, subprocess, 挂起, 超时]  
**复用次数**: 1  

---

#### P-007: 【读取数据】zip偶发不完整——多级fire-and-forget时序竞态

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: 读取数据, zip, 偶发不完整, 多级, fire-and-forget, 时序竞态, device.js, tools.js, medianCheck.js, file.js

**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**现象**: 中值检测后生成的zip文件偶发缺失文件或截断；小数据量正常、大数据量必现

---

#### 根因（三层叠加）

**主因：固定延时替代等待**
startMedianCheck 停止读取后仅 setTimeout(1000) 就打包。stopReadout 内部链条（dataContinuousStop串口往返 -> saveData大数组transfer+多文件writeFile）耗时随数据量增长，超1秒时temp目录的.bin未写完：文件未创建->zip缺文件；写到一半->zip内是截断bin。且调用链三级fire-and-forget（switchReadoutModeStateMulti / stopReadout / saveMedianCheckResult 均未await），错误被完全吞掉。

**zip层：finalize未等待**
zip.finalize() 裸调用后立即resolve，zip的中央目录+EOCD还在流式写入中（实测：resolve瞬间缺末尾1427字节，800ms后才补齐）。

**错误处理层：监听器注册太晚**
output流的error监听在await import之后才注册，open失败（如目标目录不存在）时错过事件 -> Promise永久挂起 + uncaughtException逃逸。

---

#### 修复方案（4文件）

| 文件 | 修改 |
|------|------|
| components/encoder/device.js | switchReadoutModeStateMulti内await stopReadout；startMedianCheck内await switchReadoutModeStateMulti（删除1秒延时）、await saveMedianCheckResult |
| shared/tools.js | zipDataFiles：创建output后同步注册streamDone监听（close/error）+noophandler catch；finalize()后await streamDone |
| components/encoder/medianCheck.js | invoke加await |
| main/file.js | zip-readout-data handler加return（使await生效）+catch清理残缺zip |

#### 关键技术点（可复用）

1. fire-and-forget调用链修复模式：逐级补await从UI入口到IO出口贯通。await生效前提：ipcMain.handle必须return promise，否则invoke立即resolve。
2. createWriteStream错误监听必须在任何await之前同步注册：open失败发生在首个事件循环tick，await import的让出窗口足以错过error事件 -> 挂起+uncaughtException。
3. Node15+ unhandled rejection窗口：Promise reject早于await时（错误在await import期间发生），短暂unhandled状态默认抛uncaughtException。解法：创建后立即promise.catch(()=>{})挂noophandler，后续await仍能拿到rejection。
4. zip-stream v7的finalize()不支持回调（源码finalize(){this.finish()}），传回调是死代码；完成信号=输出流close事件。
5. zip完整性验证法：EOCD签名(50 4B 05 06)必须位于文件末尾22字节内；对照组实验实证旧逻辑靠事件循环碰运气。

#### 验证方法
- 独立Node脚本require shared/tools.js（electron依赖为惰性引入，纯Node可跑）
- TC1正常打包：resolve瞬间EOCD在位+SHA256一致+可解压
- TC4父目录不存在：5秒内干净reject、无uncaught、无unhandled警告
- TC5旧逻辑对照组：实证resolve时文件缺尾->800ms后补齐（根因直接证据）

#### 遗留技术债务
1. saveMedianCheckResult返回{success:false}不检查，失败仍报检测完成+SN+1
2. 空目录静默生成空zip
3. startMedianCheck启动读取未await，启动耗时超testTime时可能取不完整数据
4. 既有：calculateColumnAverages抛错时isMedianChecking不复位

---

#### P-008: debug-plot-viewer对MPT单圈/半标定图配对失败报"无法找到配对的图表数据"

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: debug-plot-viewer, MPT, 单圈, 半标定图配对失败, 无法找到配对的图, 表数据, debug-plot-viewer.html

**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03

**现象**: 导入调试日志+前端绘图，MPT编码器弹"无法找到配对的图表数据"

**根因**: viewer只认DPT双圈的6个标题(innerHalls/outerHalls/inner calc data等3组配对)；MPT单圈ringType=""生成的标题是"halls"/" calc data"/" base data"(带前导空格)，全部不匹配->topPlot/bottomPlot均undefined->alert。DPT半标定只采单圈同样缺对侧图报错。

**修复(仅改asset/debug-plot-viewer.html，算法仓库零改动)**:
1. resolvePair()统一配对解析：标题trim后匹配；新增MPT单圈配对(calc data+base data)与单图兜底(返回bottom:null)
2. 单图模式singleMode：对侧缺失时降级上图显示、隐藏下图面板与图例，不再alert
3. 动态tab: availableGroups按实际存在的图生成分组(Halls/Inner Calc/Outer Calc/Calc)，MPT只显示Halls+Calc
4. series数据源统一为loadCurrentPlot缓存的topSeriesData/bottomSeriesData，替换computeYAxisGroups/selectAllYAxis/autoSplitYAxis/renderSingleChart中4处重复的硬编码标题查找
5. 散点判断改为白名单: halls类连线(innerHalls/outerHalls/halls)，其余散点
6. 清理死代码: switchTab/hallsTabs/innerCalcTabs/outerCalcTabs(模板无引用)

**场景矩阵**: DPT全量=3组双图如旧；MPT单圈=Halls单图+Calc双图；DPT半标定=有对侧的双图+缺对侧的单图降级；未知标题=单图不崩溃

---

#### P-009: debug-plot-viewer滚动放大后上图空白下图正常（uPlot乱序x二分裁剪失效）

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: debug-plot-viewer, 滚动放大后上图空, 白下图正常, uPlot, 乱序, 二分裁剪失效, debug-plot-viewer.html

**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03

**现象**: calc/base配对图（上下联动双图）初始显示正常，滚动放大后上图(calc data)整图空白，下图(base data)正常

**根因（数据不对称）**:
- 上图x=(实测角度+i*相位差)%360：实测角度任意起点，一圈回绕处359→0，x数组乱序（如[30...359,0...29]）
- 下图x=(FFT还原基准角度+i*相位差)%360：generateAnglesBase->restoreHallsByFFT产出的网格天然升序
- uPlot渲染依赖有序x做二分索引裁剪(idxAt)：初始全量视图i0=0/i1=N-1不受乱序影响（故初始正常）；setScale缩放窗口二分查找在乱序数组上取到错误切片，切片内点的x全在窗口外被裁剪->整图空白
- 下图x有序二分正确->正常。这解释了"只有上方空白"

**修复（仅改asset/debug-plot-viewer.html，算法仓库零改动）**:
1. normalizeSeries(series)：按首序列x升序重排，x与全部y应用同一置换（配对关系不变，散点图视觉无变化）；先做有序快检，halls图(索引x天然有序)零开销跳过
2. loadCurrentPlot记录各图自身数据边界topXMin/Max、bottomXMin/Max（排序后首尾即最值）
3. applyXScale按图钳制：每张图与自身边界求交，窗口与该图数据完全不相交时回退该图全量视图而非空白（防御两图数据域不同的场景）
4. 滚轮锚点改用wheel事件坐标(e.clientX-rect.left)+NaN守卫：u.cursor.left在仅滚动未移动鼠标时可能未初始化，posToVal(undefined)=NaN会把比例尺置NaN导致空白

**关键认知**: uPlot的data[0](x轴)必须升序，否则初始渲染正常但缩放/游标/拖选全部异常——症状极具迷惑性

---

#### P-010: debug-plot-viewer缩放卡顿数秒（散点全量重绘+高频事件）

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: debug-plot-viewer, 缩放卡顿数秒, 散点全量重绘, 高频事件, debug-plot-viewer.html

**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03

**现象**: 导入调试数据后缩放要几秒才响应

**根因（两层叠加）**:
1. 散点 space:0 全量绘制：uPlot每次setScale重绘可见范围内所有点，调试数据每曲线数万点(16曲线可达数十万)，单次重绘秒级
2. 滚轮/平移高频触发：每个事件两图各全量重绘一次，滚动几下排队数十次重绘

**用户约束**: 散点最终显示必须完整不抽稀

**修复（asset/debug-plot-viewer.html，渐进式渲染三重保障）**:
1. rAF合并：applyXScale的setScale合并到每帧最多一次(取最新参数)
2. 交互中临时抽稀：rAF回调里 setPointsSpace(2)——u.series[i].points.space 是渲染期属性，改后随setScale重绘生效，无需重建实例
3. 停止交互150ms(防抖)后 setPointsSpace(0)+redraw 恢复完整散点
4. beforeDestroy清理 _scaleRaf/_fullPointsTimer

**关键认知**:
- uPlot缩放本就只画可见范围内的点(i0..i1二分裁剪)，卡在"可见点数太多"而非"画了窗口外的点"
- u.series[n].points.space 可运行时直接改+redraw生效(社区常用hack)，这是动态密度切换的关键
- 初始渲染/切换tab/Y轴操作走renderSingleChart重建实例，天然space:0完整显示

---

#### P-011: debug-plot-viewer前端绘图性能优化组合拳（海量散点）

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: debug-plot-viewer, 前端绘图性能优化, 组合拳, 海量散点, debug-plot-viewer.html

**日期**: 2026-08-31
**项目**: EncoderPlotter_0703_03

**性能瓶颈定位（按贡献排序）**:
1. uPlot points 默认逐点 arc 圆形绘制：几十万点每次重绘秒级
2. "停止交互后恢复全量"防抖重绘：本身是一次 space:0 全量重绘，全量视图下就是数秒卡顿
3. normalizeSeries 每次切 tab 重复排序：O(N logN)×曲线数，无缓存
4. 高频滚轮事件未合并（已由 rAF 解决）

**优化组合（asset/debug-plot-viewer.html）**:
1. symbol 用 fillRect 代替默认圆弧：canvas 批量矩形比逐点 arc+fill 快数倍，2px方块视觉无差
2. 可见点数自适应密度（替代"停止后恢复全量"）：x有序二分统计窗口内点数，可见点>6000/曲线用 space:2（像素物理上限决定视觉无差），放大后点少自动 space:0 完整渲染。关键时序：density 必须在 setScale 之前按"将应用的窗口"算好——setScale 同步重绘，一次重绘即用新密度
3. normalizeSeries 结果缓存到 plot._normSeries：切 tab 免重复排序
4. 初始渲染保留 space:0 完整（一次性成本，loading 遮罩兜底）；缩放全程自适应

**关键认知**:
- uPlot points.symbol: (u, si, di, x, y, val, radius, size) => ctx.fillRect(x-1,y-1,2,2) 自定义点绘制，uPlot 调用前已设 fillStyle=曲线色
- "散点不能抽稀"的本质需求是"放大看细节时点完整"：全量视图下每像素重叠几十个点，space:2 与全量视觉等价；放大后点数少自动恢复完整——自适应密度同时满足两者
- setScale 是同步重绘：渲染期属性(points.space)必须在其前修改才会在该次重绘生效

---

#### P-012: 前后端渲染图形不一致——uPlot共享x网格 vs matplotlib每曲线独立x

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: 前后端渲染图形不, 一致, uPlot, 共享, 网格, vs, matplotlib, 每曲线独立, debug-plot-viewer.html

**日期**: 2026-08-31
**项目**: EncoderPlotter_0703_03

**现象**: 同一份调试数据，matplotlib后端图与前端uPlot图形状不同

**根因**: 数据模型冲突
- matplotlib: 每条曲线独立 (x,y)——算法侧 calcHall_i 的 x=(角度+i*相位差)%360，各曲线在角度轴上相位错开
- uPlot: 所有series共享data[0]一个x网格。viewer 原实现 topChartData.push(series[0].x) 只取第一条曲线的x，其余曲线的y被错位映射到 calcHall0 的x位置——所有曲线挤在同一相位区，图形完全走样

**修复（asset/debug-plot-viewer.html 合并模式，算法仓库零改动）**:
1. seriesShareX(series): 逐元素检测各曲线x是否一致（一致=halls类采样索引图走原多series路径）
2. mergeSeries(plot, series): x不一致时把全部曲线点集按x排序合并为单条超长series {x,y,src,labels}，src记录每点来源曲线；缓存plot._merged
3. renderSingleChart merged分支: 单series+paths=null+自定义symbol，symbol里按 u._mergedSrc[dataIdx] 取COLORS着色（还原多色散点）
4. refreshMergedChart(position): 曲线开关/全选/全清/反选按 curves[i].show 过滤点集 setData；关键:过滤后dataIdx错位，src必须同步换为过滤视图(srcs)并挂 u._mergedSrc
5. computeYAxisGroups merged返回[0]（单轴，与matplotlib原图一致）
6. toggleVisible/showAll/hideAll/reverseAll 四方法rAF回调开头插 merged 分支

**关键认知**:
- uPlot series共享x网格是硬约束；matplotlib多曲线独立x的正确还原=合并单series+symbol按来源着色（点位数学等价）
- 过滤数据后 dataIdx 与全量 src 错位是隐蔽bug源：着色索引必须随过滤视图切换（挂u实例上）
- 性能无回退：合并后总点数与多series相同，fillRect+自适应密度照常生效

---

#### P-013: 合并模式引入后上图不显示/下图单色（normalizeSeries置换误伤+src挂载晚于首帧）

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: 合并模式引入后上, 图不显示, 下图单色, normalizeSeries, 置换误伤, src, 挂载晚于首帧

**日期**: 2026-08-31
**项目**: EncoderPlotter_0703_03

**现象**: P-012合并模式上线后：上图(calc data)默认不显示，下图(base data)只剩一个颜色

**根因（两个独立bug）**:
1. normalizeSeries把series[0]的排序置换应用到了每条曲线自己的x和所有y。独立x模式（相位错开图）下，curve_i的x与series[0]的x无对应关系——套置换后curve_i自身的(x,y)配对被破坏（y重排了x没动，或反之）→合并后点全错位→上图数据错乱渲染异常
2. inst._mergedSrc = ... 写在 new uPlot 之后：uPlot构造时同步完成首帧渲染，symbol闭包里 u._mergedSrc 还是undefined → if(src)跳过着色，fillStyle保持canvas遗留状态 → 首帧全图单色

**修复**:
1. normalizeSeries分支：shareX（各曲线x一致）→全部曲线x/y同一置换（共享网格语义）；独立x→仅series[0]排序（x/y同置换），其余曲线整体原样返回（它们的乱序由mergeSeries全局点集排序统一解决，不依赖normalize）
2. symbol着色双通道：u._mergedSrc优先（过滤视图），回退闭包srcRef.src（构造期首帧）——srcRef在构造前创建
3. 验证脚本实测：合并后全部原始(x,y)配对保留+x有序 PASS

**关键认知**:
- 排序置换只在"同一网格"语义下可全局套用；各曲线独立x时置换必须只作用于series[0]，否则破坏其他曲线自身配对
- 任何"实例属性供渲染回调读取"的模式，属性必须在构造前可达（闭包或opts内），实例赋值晚于构造=首帧读不到

#### P-014: i18next多语言包四类隐蔽缺陷的排查与修复

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: i18next, 多语言包四类隐蔽, 缺陷的排查与修复, i18n.js

**日期**: 2026-09-02
**项目**: EncoderPlotter_0703_01

**问题**: 国际化显示错乱：英文模式显示中文、中文模式显示英文（fallbackLng反向回退）、插值信息丢失、同一key不同文案。

**根因（四类）**:
1. $t()动态拼接key（`$t("前缀"+变量)`、模板字符串）永远匹配不到包内key，直接回退显示key原文
2. JS对象字面量重复key静默覆盖（后者生效），造成"改了A处文案却不生效"
3. en/zh包key不一致 + fallbackLng机制：zh缺key回退en值（中文界面显示英文）；en缺key显示中文key原文（英文界面显示中文）
4. 调用方传插值参数但翻译值无{{占位符}}，参数被吞

**解决方案**:
- 动态拼接 → 静态key + i18next插值：`$t("字段{{var}}", {var: x})`，翻译值加占位符
- 重复key → 删除后定义项（保留正确值）；用正则逐包区域扫描源码检测
- 包间不一致 → 以HTML/代码实际调用的key字符为准修正语言包key（注意尾随空格、全角/半角）
- 检测脚本：模拟window后require语言包，getResourceBundle取双包做key集合差集 + 全代码正则提取静态$t key反向验证

**复现/验证命令**（项目根目录）:
node临时脚本: global.window={}; require('./components/i18n.js'); const en=window.i18next.getResourceBundle('en','translation') ... 差集/存在性/插值断言

**经验**: (1) key为中文时，zh包"缺失"比en包缺失更隐蔽——fallbackLng='en'会让中文界面显示英文，必须逐key对齐双包 (2) HTML注释块内的$t改造无显示影响但为解除注释预留i18n就绪 (3) 源码文本级key比对对\n转义会假阳性，需运行时验证

---

#### P-015: Electron子窗口全部关闭后主窗口被其他应用窗口挡住

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: Electron, BrowserWindow, parent, closed, focus, z-order, 前台, 窗口遮挡, owner window

**日期**: 2026-09-02
**项目**: EncoderPlotter_0703_01

**问题分类**: 技术问题

**问题描述**:
```
代码中有单独打开新窗口的操作（日志窗口、导入数据图表窗口），
这些窗口全部关闭后，上位机主窗口被其他应用的窗口挡住，不在前台。
```

**问题根因**:
两类子窗口（createLogWindow L291-323、open-import-plot-viewer L329-354，均在 main/index.js）共同特征：
1. `parent: mainWindow`：Windows owner窗口机制，子窗口z-order恒在主窗口之上
2. `show: true`：打开即抢焦点成为前台活动窗口
3. `closed` 事件只做清理（移除数组/打印日志），没有把焦点还给主窗口

机制：最后一个子窗口关闭时，Windows把激活权交给z-order中紧随其下的顶层窗口。
若期间用户切换过其他应用（或主窗口本就不在次序顶端），激活权落到别的应用窗口上。
Electron不会自动把owner窗口带回前台，必须手动focus。

**解决方案**:
```
在 main/index.js 增加工具函数：
function focusMainWindow() {
    if (mainWindow && !mainWindow.isDestroyed()) {
        if (mainWindow.isMinimized()) mainWindow.restore()
        mainWindow.show()
        mainWindow.focus()
    }
}
在 createLogWindow 和 viewerWindow 的 'closed' 事件末尾调用 focusMainWindow()。
多日志窗口场景安全：parent关系保证其余子窗口仍在主窗口之上，focus不影响其层级。
```

**涉及角色**: 角色1/角色8
**严重度**: MEDIUM
**状态**: 已解决
**关键词**: [Electron, BrowserWindow, parent, closed, focus, z-order, 前台, 窗口遮挡, owner window]
**复用次数**: 0
---

#### P-016: 阈值面板三处模板文本硬编码中文未国际化（P-014第5类变体）

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: i18n, 硬编码, $t, title属性, threshold.html, 双包key

**日期**: 2026-09-02
**项目**: EncoderPlotter_0703_01

**问题**: threshold.html 中"错误阈值范围/最小错误阈值/最大错误阈值"三处直接写中文未包 $t()，且 title 属性（重置按钮 tooltip）同样硬编码；语言包中也无对应 key。

**根因**: P-014 四类之外的第5类——Vue 模板文本/HTML 属性硬编码遗漏（同文件其他文本均已 $t，属局部漏改）。HTML 原生属性（title 等）需用 :title="$t('...')" 绑定写法。

**解决方案**:
1. 模板文本 → {{$t('key')}}
2. title 属性 → :title="$t('key')"
3. en/zh 双包同步补 key（错误阈值范围/最小错误阈值/最大错误阈值/重置为默认值），插入"阈值设置提示"注释区
4. 运行时验证双包 key（node 模拟 window 后 getResourceBundle 断言）

**关键词**: [i18n, 硬编码, $t, title属性, threshold.html, 双包key]
**复用次数**: 0
## 2026-09-03 | flashPanelV2 报 TypeError: Cannot read properties of undefined (reading 'SERIES')

- 现象: 渲染时 seriesMeta 计算属性抛错, this._schema 为 undefined
- 根因: Vue 2 不代理以 _ 或 \$ 开头的 data 属性到组件实例 (保留前缀), 故 this._schema 恒为 undefined, 模板中 _schema.XXX 同样解析不到
- 修复: 将 flashPanelV2.js 中 data 属性 _schema 重命名为 schema, 同步更新 computed/watcher 共 4 处 JS 引用及 flashPanelV2.html 模板 1 处 v-for 引用
- 复现: 在 Vue 2 组件 data 中定义 _xxx 属性, 在 computed 中访问 this._xxx 必然得到 undefined
- 教训: Vue 2 组件 data 属性禁止 _ / \$ 前缀命名; 遇到 undefined 读取错误先查保留前缀

## 2026-09-03 | 固件烧录V2 FileNotFoundError: JFlash/DPB/dpb_IAP.hex 解析到项目根

- 现象: Electron 调 flash_tool_v2.py 报 文件不存在: @DRIVE_D@/...\项目根\JFlash\DPB\dpb_IAP.hex（实际 JFlash 位于 controller\python\sub_automation\mbp_calibration_station\ 下）
- 根因: finalstep0_loadHex.py 的 _CALI_CFGS/_RECALI_CFGS 配置表在模块 import 时构造，BaseConfig.__post_init__ 将 ./JFlash 等相对路径按当时 cwd 固化为绝对路径；factoryAutomation.js spawn 不带 cwd，进程 cwd=应用根目录；loadHex.main() 里的 os.chdir 在 import 之后才执行，为时已晚
- 修复: flash_tool_v2.py 在 sys.path.insert(STATION_DIR) 之后、import station 模块之前加 os.chdir(STATION_DIR)（带 frozen 守卫），保证 import 期路径解析基准正确
- 复现: 任意 cwd 下 import finalstep0_loadHex，观察 _CALI_CFGS[('DPB',False)].hex_path 是否随 cwd 变化
- 教训: 模块级常量表中做相对路径 resolve() 是 cwd 陷阱；chdir 必须发生在含相对路径常量解析的 import 之前，而非 main() 入口
- 备注: 遗留独立问题——station.py 的 AppPath/SavePath 指向 @DRIVE_F@/ 盘（本机无此盘），recali 模式产品 hex 与文件日志仍会失败/降级，属机器配置问题

## 2026-09-03 | station.py 外盘路径（@DRIVE_F@/E:）在本机全部失效

- 现象: 文件日志 WARNING（@DRIVE_F@/ 不存在）；JLinkPath/CompilerPath 指向 E: 也不存在（本机仅 @DRIVE_C@/D: 盘）
- 根因: station.py 为产线机台配置文件（GUI 按行锚定正则改写），值是生产机器的 NAS 映射盘（@DRIVE_F@/SynologyDrive）与工位 E: 盘路径，开发机无这些盘
- 修复（station.py 三处，保持单行 name = value 格式以兼容 GUI 正则）:
  1. SavePath: @DRIVE_F@/SynologyDrive/Program/BURN/测试 → @DRIVE_D@/生产数据/BURN/测试（tools.getLogger 的 makedirs 自动建目录，文件日志恢复）
  2. JLinkPath: @DRIVE_E@/JLink_V914a/JLink.exe → @DRIVE_D@/software/SEGGER/JLink/JLink.exe（本机实测 V9.14a，与产线版本一致，经 JLink_x64.dll FileVersion 确认）
  3. AppPath: → @DRIVE_D@/生产数据/BURN/0_latest/APP-DPT-411（占位；本机无固件工程，generate 对工程内文件有本地回退不受影响；recali 产品 hex 与 step7 编译待真实工程落地）
- 遗留: CompilerPath 仍指 @DRIVE_E@/Keil（本机未装 Keil 无法确定正确值，编译步骤不可用）；AppPath 占位目录不存在属预期
- 教训: 机台配置文件换机器必须同步改四个机台路径（AppPath/CompilerPath/JLinkPath/SavePath）；验证 getLogger 文件日志须实际调用 getLogger() 而非仅 import（初始化在首次调用时发生）

## 2026-09-03 | step1 加载calibration 环节日志黑盒 + loadHex 路径固化残留在 main() 中

- 现象: step1 只有一行 load.main() 调用，烧录配置（hex/iap 路径、器件、超时、NC）全黑盒；失败时 RuntimeError 仅一行带过；且从任意 cwd 直接调 load.main() 仍会把 ./JFlash 固化到错误目录（main() 内 chdir 为时已晚）
- 修复:
  1. finalstep0_loadHex.py main(): 烧录前输出关键上下文 3 行日志——[serial/mode/NC] hex=... iap=... device/speed/interface/timeout/jlink
  2. finalstep0_loadHex.py flash_device(): 每次 JLink 尝试输出 第N/3次执行完成（耗时Xs）日志路径
  3. finalstep0_loadHex.py main() 失败时 RuntimeError 携带 mode/NC/重试次数等上下文
  4. flash_tool_v2.py step1 调用前输出 serial/mode/NC/JLink 参数
  5. loadHex 的 os.chdir 从 main() 提前到模块导入时（构造 _SERIES_SPEC 配置表之前）——根治所有调用方的路径固化错位
- 验证: 无探头环境下实际运行，日志完整呈现 配置上下文 → 3次尝试(耗时+日志路径) → 携带上下文的异常

## 2026-09-03 | 界面日志非实时：多行整块 + stderr 全红

- 现象: 烧录过程中界面日志框看不到逐步输出，失败后错误消息里才带出全部日志
- 根因（两层叠加）:
  1. _runPythonScript 把 chunk 原样转发，Python 突发时一个 chunk 含多行（且行可跨 chunk 截断），UI 整块塞成一条日志，形同无实时输出
  2. Python logging 全部走 stderr，UI 把 stderr 一律按 error 红色显示，正常 INFO 也全红
- 修复:
  1. factoryAutomation.js _runPythonScript: 用 readline.createInterface({input: stream}) 按行回调 onStdout/onStderr（跳过空行），data 事件仅累积完整文本供 resolve/reject 使用
  2. flashPanelV2.js handleProgress: 'error' 分支改走 parsePythonOutput 行级分类（ERROR/Traceback/失败→红，WARNING→黄，INFO→白），不再整块标红
- 验证: node 实测 readline 转发——多行 chunk 拆成逐行、\r\n 兼容、累积保留；两文件 node --check 通过
- 教训: Electron 渲染进程 spawn 子进程的流式转发本身正常（实测逐 chunk 到达），日志"非实时"通常是行拆分/着色层问题而非管道问题

## 2026-09-03 | 采集完成后重连 COM26 PermissionError 且卡死

- 现象: step2 采集成功(shape=(11266,20))后重连编码器报 could not open port 'COM26' PermissionError(13)，然后 powerOn 无响应卡死
- 根因（两层）:
  1. finalstep0_collect_v2.collect() 用完 AnalyzerDual 后不关串口（AnalyzerDual 无 close() 方法），COM 口一直被占 → 重连必然 PermissionError
  2. sub_embedded Analyzer.connect() 串口打开失败不抛异常（仅 logging.exception + serial=None + 返回 False），autoConnect 构造不感知，后续 powerOn/enter 挂在无串口状态 → 表现为"卡住"
- 修复:
  1. collect() 收尾（退出再标定后、return 前）analyzer.ser.close() 释放串口，失败不影响数据返回
  2. AnalyzerDual.readThread 裸 except: continue 改为检测 self.ser/is_open，串口已关时 break 退出（否则 close 后死循环空转烧 CPU）
  3. flash_tool_v2._connect_encoder 加 analyzer.serial is None 校验，串口未打开立即 raise（走既有 warning 分支），不再无串口空挂
- 教训: pyserial 串口打开失败的模式是"返回 False + serial=None"而非异常；占用排查先看前一个使用者是否 close

## 2026-09-03 | Recalibration.enter() 失败分支误打 Success 日志

- 现象: 用户困惑"init 已进再标定，为何采集时 enter 又失败"
- 解释: ① step1 JLink 烧录结尾 r,g,q 复位运行新固件，再标定状态是固件运行态、复位即丢，采集驱动必须重新 enter（设计使然）；② 固件刚复位未就绪时回读应答非 b'SUCCESSFUL'，enter 正常重试第二次成功
- bug: mbp Recalibration.enter() 失败分支（回读非 SUCCESSFUL / data None）也打 'Enter Recalibration Mode Success' 再 return False——失败说成功，严重误导排障
- 修复: 失败分支改打 logging.warning('Enter Recalibration Mode FAILED（应答=...）')，return False 语义不变

## 2026-09-03 | 评估报 angles error may be too large（0.112°超0.1门槛）

- 现象: step5 内圈评估 anglesErrRange=0.112 > 0.1 阈值被拦截
- 根因: 界面误传 --inner-size 10（station.py 被改写为 Configs10/8霍尔），而台架实际 15 内径 9 霍尔硬件——配置与硬件不匹配，降维矩阵/通道选择全错导致误差大
- 验证方法: 采集数据 20 列中 index1~9（内圈9霍尔）逐列检查 min/max/变化——全部有有效信号即 9 霍尔硬件（col9 若全 0 才是 8 霍尔）
- 结论: 质量门槛正常拦截非代码故障；界面选择须与台架实际硬件一致

## 2026-09-03 | Recalibration.enter() 加固：重试机制 + 应答前缀匹配

- 需求: enter() 需要重试机制（重试5次）
- 修复:
  1. enter(maxAttempts=5, retryDelay=1.0)：每轮 先发 allEnterRecalibration 命令 → getMemory('v') 回读校验 → 失败 sleep 1s 重试；5 次全失败才 return False
  2. 应答匹配改 startswith(b'SUCCESSFUL')：实测应答形如 b'SUCCESSFUL1\x00\x00...'（带尾巴），原严格相等 data==b'SUCCESSFUL' 永远失败——这正是之前采集时 enter 反复重试两轮才过的根因
  3. 保留原实现"先发命令再回读"顺序（首轮也发命令）
- 教训: 串行协议回读按页对齐（256B 页），有效载荷后带填充字节——比较要用前缀匹配

#### P-017: Windows 深目录下台账创建报 WinError 206

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: Windows, MAX_PATH, WinError 206, 长路径, 扩展前缀, sire_run, 台账

**日期**: 2026-09-12
**项目**: SIRE 工作流

**现象**:
在带 UUID 的深层工作区目录下执行 `sire_run.py init`，报
`FileNotFoundError: [WinError 206] 文件名或扩展名太长`，
台账 run 目录建了一半，evidence 子目录创建失败。

**根因**:
Windows 默认 MAX_PATH 为 260 字符。台账路径形如
`<工作区>/.sire/runs/R20260912-125216/evidence/U-01/impl`，
工作区本身已 180 字符时就会超限。与脚本逻辑无关，是 API 限制。

**解决方案**:
在 `sire_run.py` 加 `lp()` helper：路径绝对化后若超过 240 字符，前面拼上
Windows 扩展长度前缀，再交给 os 接口。全部 makedirs / open / exists / listdir
统一走 `lp()`，共 12 处调用点。

前缀是四个字符：反斜杠 反斜杠 问号 反斜杠。
**坑在转义层数**：Python 源码里必须写成 8 个反斜杠形式的字面量，
少写一层会得到三字符的错误前缀，且不报错、静默失效。
务必定义成模块常量 `LONG_PATH_PREFIX`，不要在每个调用点重复手写转义。

**验证方式**:
导入模块后打印 `repr(sire_run.LONG_PATH_PREFIX)`，应为 4 字符前缀；
再用一个 258 字符的路径调 `lp()`，返回值应以该前缀开头；
短路径调 `lp()` 应原样返回不加前缀。

**预防**:
任何要在用户任意目录下建多层子目录的 Windows 脚本，都先套 `lp()`。
不要假设工作目录是浅路径。

**关键词**: [Windows, MAX_PATH, WinError 206, 长路径, 扩展前缀, sire_run, 台账]

#### P-020#2: 运动页 <100Hz 使能时附加寄存器 (0x24/0x27/0x29/0x2A/0x2B) 示波器无曲线

**类型**: P  **来源**: @USER_HOME@\sire_global\global_problem_solutions.md
**关键词**: 附加寄存器, extras, 示波器, 100Hz, 软轮询, doSendMit, api.mit, flatExtras, TELEMETRY_DISPATCH, xNN

**日期**: 2026-09-22
**项目**: driverSoftware (@CODE_ROOT@\driverSoftware, development, 未提交)
**状态**: 已修复, 真机验证通过 (id15 fw v3.4.6 @3Mbps), 代码未提交
**关键词**: [附加寄存器, extras, 示波器, 100Hz, 软轮询, doSendMit, api.mit, flatExtras, TELEMETRY_DISPATCH, xNN]

**现象**: 运动页勾附加寄存器, 频率 ≥100Hz 有曲线, <100Hz 使能后这些曲线空白。

**根因 (两处叠加)**:
1. <100Hz 使能走 motion.js `doSendMit()` → `/api/cmd/mit`, 前端不带 extras, 后端 `api_mit` 也把 extra_regs 写死 [0xEB] —— 设备根本没被要求回这些寄存器。
2. 软轮询回包进 scope 靠 api.js `TELEMETRY_DISPATCH` (/api/cmd/status、/api/cmd/mit), 只挑 pos/vel/tau/温度, 把 `parsed.extras` (数字地址 key) 全丢; scope 信号 key 是 "xNN" 大写 hex (硬件流 drain 路径才摊平成 xNN)。所以未使能 <100Hz 也同样空白。

**修复**: server.py `MitReq` 加可选 `extras`, 与 status 共用 `_extras_with_state()` (去重 + 保证 0xEB); motion.js doSendMit 带 `getSelectedExtras()`; api.js 加 `flatExtras()` 把 extras 摊成 xNN 并入两个 dispatch。

**验证**: pytest 2126 passed; 真机可见 GUI: 50Hz 使能 → TX 帧含 `29 2A 2B 24 27 EB`, scope buf 5 路 675/675 非空; 未使能 50Hz、100Hz 使能 (回归)、10Hz 使能均有数据; 控制台无错误。

**教训**: 同一功能按频率分硬件流 / 软轮询两条路时, 新增字段要两条路都接, 且要同时核对"请求带没带"和"回包进 scope 时有没有被映射丢掉"两层。

#### P-20261034#2: MES manual business and admin separation

**类型**: P  **来源**: D:\sire\AI\AI\sire\knowledge\global\global_problem_solutions.md
**关键词**: 关键词：MES, 使用手册, 小白版, 业务系统, 后台管理, DOCX, SN, 流程快照

关键词：MES、使用手册、小白版、业务系统、后台管理、DOCX、SN、流程快照
需求场景：用户要求接续Claude编写的半成品使用说明，保持原来的章节、截图、表格与小白读者口吻，并明确区分业务系统和后台管理系统的操作。
方案：在原A/B章节生成器中插入补充章节挂钩，分为业务系统操作、后台管理系统操作、公共查阅三部分。逐个模块按schema.referenceOnly标记后台维护或业务使用入口；补充审批、来料冻结复检、首件退回与多次返工、SN硬件编码更正，以及审计筛选、行为分析、配置体检、集成身份创建和密钥轮换。工单新建时先选工序流记录，再选启用版本；两项不选时采用模块本身流程。SN模板长度为17加产品型号长度，DPT15示例22位，不应统一写23位。
关键文件：D:/code/mes/docs/manual/build-manual-v2.cjs、manual-chapters-a.cjs、manual-chapters-b.cjs、manual-completion.cjs；依据mes-db/zx07/modules.mjs、workflows.mjs以及后台各页面源码。
验证结果：原生成器成功输出更新DOCX，ZIP完整性和XML解析通过，新增章节全部存在，包含26张图片，无缺图提示或占位。独立代理审核源码及操作准确性。运行bundled render_docx.py因未安装bundled LibreOffice失败，不能宣称分页或配图视觉验收通过；没有改业务代码，没有运行会重置数据库的测试。

#### P-20261034#3: MES通用字段拼接、测试部署与SN原文归档

**类型**: P  **来源**: D:\sire\AI\AI\sire\knowledge\global\global_problem_solutions.md
**关键词**: MES, lowcode, concat, SN, Feishu, 测试部署

**关键词**: MES, lowcode, concat, SN, Feishu, 测试部署

## 需求场景
用户明确要求自定义模块通用字段拼接，不应固化SN业务规则；完成后部署测试服、不深度测试。追加将飞书《编码器追溯系统》整理为标题SN的项目Markdown。

## 方案
text.config.concat配置有序来源字段和分隔符；前后端共用纯函数计算，服务端忽略客户端派生值并重算，部分更新合并原数据后执行必填/长度/唯一检查；拒绝循环、归档来源、默认值和自动编号冲突。设计器与运行表单显示只读预览。原文归档区分正文/画板/评论和未决项，保存四张原图不依赖外部临时链接。

## 关键文件
D:/code/mes/mes-server/src/lowcode/field-composition.ts
D:/code/mes/mes-server/src/lowcode/schema.ts
D:/code/mes/mes-admin/src/lowcode/designer/FieldProperties.tsx
D:/code/mes/packages/runtime/src/lowcode/schema-utils.ts
D:/code/mes/docs/SN.md
D:/code/mes/docs/PROGRESS.md

## 验证
59项相关服务端单测通过，admin/web类型检查和三端构建通过；独立代码审查完成。授权部署r20261022-concat成功且数据计数未变，保留DB/config备份；后续其他发布已升级到erp3，未覆盖。无深度集成/E2E；UI仅部分冒烟，未声称完整路径通过。SN文档8章节4原图引用全部验证，独立阅读原图复核两流程顺序。记录位于D:/sire/sire_ledger/runs/R20261022-113015-mes/validation.md。

#### P-20261034#4: MES模块空框与订单SN工序静态适配缺口

**类型**: P  **来源**: D:\sire\AI\AI\sire\knowledge\global\global_problem_solutions.md
**关键词**: MES, 模块空框, 订单导入, workflowBindings, linkRange, SN, 工序流程, 配置漂移

**日期**: 2026-10-22
**项目**: MES
**关键词**: MES, 模块空框, 订单导入, workflowBindings, linkRange, SN, 工序流程, 配置漂移

**需求场景**: 用户确认只清空业务模块页面内容，保留菜单、路由、框架，并分析订单、SN、工序、维护、兼容能力。

**方案**: 两个前端 /app/:code 和后台工作流子路由替换空框；原引擎及业务数据保留。工作流标题使用独立 overview 接口，避免误依赖模块 view 权限。独立静态复核发现权限问题并修复。

**关键文件**: D:/code/mes/docs/reviews/2026-10-22-模块清空与业务适配分析.md；D:/code/mes/packages/runtime/src/lowcode/pages/ModuleShellPage.tsx；D:/code/mes/mes-server/src/lowcode/apps.service.ts。

**结论**: importRecords 没有 createRecord 的 workflowBindings 及 linkRange 路径；默认 SN 从批次生成，数量 1 表示单个，数字后缀不跨 999。ZX07 默认工作流尚未采用平台已有的 coverRelated，而进度记录中的服务器配置已启用该规则，存在重应用配置漂移风险。工序流记录与模块级版本归属脱节，报工缺单件工序执行和数量质量闭环。分析基于默认源码，未核对服务器实际配置。

**验证**: 独立 R6 静态复核完成。未测试、未构建、未部署，待用户授权测试。证据 D:/sire/sire_ledger/runs/R20261022-202240-mes/r6a.md。

#### P-20261034#5: MES平台定义执行与依赖治理方案静态审查缺口

**类型**: P  **来源**: D:\sire\AI\AI\sire\knowledge\global\global_problem_solutions.md
**关键词**: MES, 工作流运行时, 依赖治理, 提供者绑定, 审批状态机, 并发锁, 待办分页

# 平台改造方案静态分析
范围：只读分析方案与当前源码；不修改项目、不执行测试。
检索复用：P-20261020（引用保护的共享锁/排他锁与稳定锁序），P-20261024（订单流程版本与审批边界）。
结论：方向成立，v0.1尚不足直接执行。
主要缺口：
1. execProcess多提供者缺启动选择契约；需模块+记录+版本身份。
2. 待审批状态遗漏submitOperation、改派、重复完成、驳回与取消状态机；须冻结并幂等。
3. actorRoleCodes为流转级，派工为节点级；明确多出口并集/交集和终点权限。
4. 依赖现场扫描须覆盖运行快照、历史版本、停用模块及动态默认绑定；定义静态边和运行边生命周期。
5. impactOf需纳入写事务并与引用创建共享锁、删除停用排他锁成对；稳定锁序并锁后重读。
6. 待办已有workflowView终判，SQL粗筛后limit501；放宽粗筛会使前500条占满后漏掉合法待办，须游标扫描补足与可解释total/truncated。
7. 提供者编码快照不足：运行中的org、materialNeeds等全部从run解析，并明确schema版本与业务数据实时/快照边界。
8. 字段依赖身份应含moduleId+fieldKey；版本应含moduleId+version；生产stepCode还需提供者作用域。
9. 文本扫描业务字段名误报name/status等通用标识，建议AST上下文约束和业务包改名不变性用例。
10. 保存/发布一致拒绝与U1.6显示不生效相冲突；草稿诊断/发布阻止边界需明确。
建议：D0确认基线；先冻结运行时、状态机、依赖锁与身份契约，再按1→2→3推进。D1暂不支持、D2交集、D3新运行生效、D4默认提供者均可采纳，须补兼容与切换规则。
模型门禁：架构分析高难度由主控；独立R6由review_plan子代理完成，无指定模型覆盖。
R6独立复核：确认流程库选择、审批状态机、多出口权限、运行快照四项缺口。
验证：仅文档与源码静态交叉检查，未测试；无Git操作。

**关键词**: MES, 工作流运行时, 依赖治理, 提供者绑定, 审批状态机, 并发锁, 待办分页
**需求场景**: 分析v0.1平台改造草案是否具备实施条件。
**关键文件**: D:/code/mes/docs/design/PLATFORM-定义执行与依赖治理改造方案.md；mes-server/src/exec/exec.service.ts；mes-server/src/lowcode/apps.service.ts；mes-server/src/lowcode/modules.service.ts。

#### SIRE-K-CODEX-DEFAULT-MODEL-GPT6-LUNA-28cb18c: Codex executor defaults to gpt-6-luna

**类型**: F  **来源**: @SIRE_ROOT@\AI\AI\feishu-hub\executors\codex\executor.py
**关键词**: Codex executor, default model, --model, gpt-6-luna, fake CLI, regression

Codex CLI accepts --model <MODEL> (verified with local codex exec --help). DEFAULTS.codex_args now includes --model gpt-6-luna, so both new and resumed exec tasks use the requested model by default. The fake Codex integration asserts the argument for CX-1 and CX-2. Verification: test_codex_executor.py 20 checks passed; test_hub.py 79 checks passed with PYTHONIOENCODING=utf-8; commit 28cb18c; no push.

#### SIRE-K-CODEX-EXECUTOR-9cd2424: Feishu Hub Codex executor protocol v1: exec, desktop queue, Stop Hook

**类型**: F  **来源**: @SIRE_ROOT@\AI\AI\feishu-hub\executors\codex\executor.py
**关键词**: Feishu Hub; Codex executor; desktop_queue; active writer; Stop Hook; LeaseLost; spool; CX-1-CX-10

Protocol v1 implementation on feature/feishu-hub: exec/new and exec resume receive prompts on stdin; thread.started.thread_id binds the session; last assistant output comes from --output-last-message. Only an active-writer rejection before execution can route once to codex queue. Queue accepts --message and -C but not --skip-git-repo-check; an uncertain acknowledgement uses queue_id null. TaskReporter heartbeats continue through event submission; LeaseLost and timeout terminate the CLI process tree. Stop Hook suppresses FEISHU_HUB_TASK_ID turns, sends independent turns to /v1/sessions/turns, and spools unavailable Hub responses. Uses Win32 OpenProcess/GetProcessTimes for pid_ctime. Verification: CX-1 through CX-10 passed 10/10; existing test_hub passed 79/79. Real desktop Hook trust and live Feishu paths remain unverified because task boundaries forbid touching live configuration or services. Commit 9cd2424; no push.

#### SIRE-K-CODEX-HUB-ACTIVATION-20260924: Codex Feishu Hub code completion does not activate executor or desktop Hook

**类型**: K  **来源**: @SIRE_ROOT@\AI\AI\feishu-hub\executors\codex\README.md
**关键词**: Feishu Hub; Codex executor; deployment readiness; Stop Hook; desktop queue

Commit 9cd2424 implements and fake-tests Codex Hub protocol v1, but source commit alone does not start executor.py or install/trust the Codex desktop Stop Hook. On 2026-09-24 process inspection found no python.exe/pythonw.exe command line running feishu-hub/executors/codex/executor.py. The prior task explicitly prohibited live Hook configuration, real Feishu access, and live Hub integration. Therefore the new Codex Feishu path is not verified or presently active; activate executor and Hook, then perform a real end-to-end message/reply test.

#### SIRE-K-CODEX-NOTIFY-ARGV-20260924: Codex Stop Hook notify --previous-notify 输入支持与幂等验证

**类型**: F  **来源**: @SIRE_ROOT@\AI\AI\feishu-hub\executors\codex\hook_stop.py
**关键词**: Codex, Stop Hook, notify, --previous-notify, agent-turn-complete, thread-id, turn-id, duplicate, FEISHU_HUB_TASK_ID

Codex hook_stop.py 兼容 stdin Stop JSON 和 notify 末尾 argv JSON。notify 仅处理 type=agent-turn-complete，映射 thread-id/turn-id/cwd/last-assistant-message 到共用 /v1/sessions/turns 上报，stdout 静默；其他 type 忽略。FEISHU_HUB_TASK_ID 存在时 notify 入口直接退出。Hub 按 session_id+turn_id 幂等，重复上报不重复发卡。验证：Codex 专项 16 项通过；Hub 79 项通过（Windows 建议 PYTHONIOENCODING=utf-8，避免 Claude 假 CLI 默认编码导致 surrogate 相关失败）。真实桌面 notify 与飞书 UI 未执行，因要求不动本机 Codex 配置和线上服务。

#### SIRE-K-CODEX-NOTIFY-GUARD-ea704df: Codex executor safeguards config.toml notify chaining

**类型**: F  **来源**: @SIRE_ROOT@\AI\AI\feishu-hub\executors\codex\executor.py
**关键词**: Codex executor, config.toml, tomllib, notify, codex-computer-use.exe, --previous-notify, pythonw.exe, hook_stop.py, CC-Switch, atomic replace, backup, idempotency

Codex executor notify guard runs once during serve_forever startup and every 60 seconds. It parses the user's Codex config.toml using tomllib; absent/empty notify gets pythonw.exe plus absolute hook_stop.py; a codex-computer-use.exe turn-ended command keeps its existing argv and gets one JSON-encoded --previous-notify argv; unknown executables are warned and left intact. Invalid TOML is left untouched. Updates preserve other TOML text, copy a .bak first, validate a same-directory temporary file, os.replace atomically, then parse the written file. Tests inject a temporary TOML path and cover startup, existing hook replacement, idempotency, unknown executable, malformed TOML, and backup preservation. Verification: Codex executor tests passed 20 checks; Hub tests passed 79 checks with PYTHONIOENCODING=utf-8. Real desktop/config interaction was not executed to avoid editing the user's real Codex config. Commit ea704df.

#### SIRE-K-CODEX-QUEUE-NATIVE-5d39ed6: Codex queue must use native exe to preserve Windows prompt argv

**类型**: K  **来源**: @SIRE_ROOT@\AI\AI\feishu-hub\executors\codex\executor.py
**关键词**: Codex queue; codex.exe; cmd.exe; argv; MSIX; executor log; Feishu Hub

Commit 5d39ed6 fixes Codex queue prompt corruption risk on Windows. Default discovery prefers npm vendor codex.exe; configured cmd shims are resolved to the adjacent vendor exe for queue, or fail CLI_NOT_FOUND. This avoids cmd.exe metacharacter parsing and its 8191-character limit. Added Claude-compatible APPDATA to Packages/LocalCache/Roaming cwd mapping and file logging to HUB_HOME/executor_codex.log. Tests passed: Codex 13/13 including &, |, %, ^, quote, angle brackets and multiline argv exactness, MSIX mapping and pythonw-style log file; Hub regression 79/79. Real live Feishu desktop queue was not changed or exercised.

#### SIRE-K-CODEX-SIDEBAR-PROJECT-REMOVAL-20260924: Codex project sidebar APIs do not expose project removal

**类型**: K  **来源**: Codex app project tools
**关键词**: Codex sidebar, projects, remove project, move project, sidebar section

The available Codex app project APIs list projects and move them among pinned/custom/unpinned sections. Moving to null or threads returns a project to the unpinned Projects area; it does not remove the project from the sidebar. No project-removal API is available in the exposed tools. Do not claim removal by merely unpinning; ask whether the user wants all projects unpinned instead.

#### kb-recalibration-sn-log-20260924: 再标定日志按编码器 SN 归档

**类型**: F  **来源**: @CODE_ROOT@/EncoderPlotter3/components/encoder/device.js
**关键词**: 再标定, 日志, SN, CalibrationLogs, debug ZIP, write-calibration-log

Fixed i18n gaps: TXT header labels now use translation keys 标定时间/标定结果, and header result uses existing translated 标定成功/标定失败 keys. Added English and Chinese dictionary entries for inner/outer estimated axial-distance messages with distance/gap interpolation; DPB converter parses ring and distance and returns localized output rather than passing dynamic Chinese text to $t. Filename result tokens remain Chinese per existing file naming convention. Static diff check passes; no locale runtime/real device test. Changes are local only; no push/tag.

#### kb-settings-production-mode-internal-only-20260924: 生产模式设置仅内部版本显示

**类型**: P  **来源**: components/analyzer/version.html
**关键词**: 设置, 生产模式, isInternal, 内外部版本, version.html

Production Mode setting visibility uses the shared isInternal() classifier: internal/development builds are internal; production/unknown are external. In components/analyzer/version.html, the Production Mode setting row is guarded by v-if="isInternal". Static diff check passed; no UI session was run.

#### knowledge-current-branch-2026-09-24: Git current branch lookup

**类型**: K  **来源**: @SIRE_ROOT@\AI\AI
**关键词**: Git, branch, feature/feishu-hub

When the session root is not a repository, inspect sibling project directories; current repository is @SIRE_ROOT@\AI\AI and branch is feature/feishu-hub.

#### knowledge:why-reg-read-fails: 寄存器读取失败的分层诊断

**类型**: K  **来源**: @CODE_ROOT@\driverSoftware\docs\firmware_dev_versioning_coordination.md
**关键词**: reg_read, Factory, read_version, fw_profile, dirty, git sha, RS485, HID, reader_mp_worker, timeout

基于固件联调版本文档和当前代码分析寄存器读取故障：server.py 的 reg_read 直接走 Factory REG_READ，不依赖 fw_profile；read_version 才读取 0x0C/0x0D 并决定 dev/正式档案。故所有寄存器 timeout/no response 首先指向 RS485/HID reader、设备 ID、Factory 协议/设备状态或 MP reader 卡死；若 read_version 成功但 MIT/Default/遥测失败，则重点检查 dev-<sha>.json 缺失、dirty/SHA 解码、档案 active 被清空、调用顺序未先 read_version。读到数值但不合理则检查 float-bits 类型寄存器与普通 float 的解码差异。证据：core/commands.py reg_read/read_version，server.py api_read_version/_read_reg_float/_match_fw_profile，docs/firmware_dev_versioning_coordination.md，docs/feedback_ledger.md 中 MP reader 卡死记录。

#### method-git-current-branch: 当前分支必须查询实时 Git

**类型**: F  **来源**: D:\sire\AI\AI\sire\knowledge\global\git-current-branch.md
**关键词**: Git, 当前分支, 实时状态, 历史记录

# Git 当前分支查询

记录编号：method-git-current-branch

关键词：Git, 当前分支, 实时状态, 历史记录

查询当前分支时必须读取目标仓库的实时 Git 状态。`git branch --show-current` 可读取分支，`git symbolic-ref --short HEAD` 可独立复核；历史任务记录中的分支名称只适用于当时的仓库与时间。若处于 detached HEAD，应说明没有当前分支，另查提交编号。

验证：2026-10-12 在 driverSoftware 实际执行上述两条命令及 `git status --short --branch`，结果一致。具体分支名称仅保存在本次任务证据中。

#### sire-20260922-dpt-dpb-plot: DPT final plot must not inherit stale DPB type

**类型**: P  **来源**: @CODE_ROOT@\EncoderPlotter_0703_03\controller\python\sub_automation\pcba\pcba_check.py
**关键词**: DPT, DPB, PCBA, 最终绘图, #TYPE, 型号覆盖

PCBA最终绘图若传入界面型号，应以parse_model(model)得到的产品系列作为汇总绘图类型；临时hall_data文件的#TYPE可能是历史残留，不能覆盖当前DPT选择。修复位置：controller/python/sub_automation/pcba/pcba_check.py plot_all。验证：py_compile通过；真实桌面/设备场景因环境缺失标记BLOCKED。
