# 知识记录（数据库导出副本）

> 由 `sire_kb.py export-md` 生成，数据库 knowledge_records 为正式来源；请勿手工编辑，修改请走 `sire_kb.py add` 或原始 md。
> 生成时间: 2026-09-24 09:00，共 58 条

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

#### K-OTA-V4065-POWERLOSS-HALL-20260922: OTA 功能支持断电检测错误 Hall

**类型**: F  **来源**: @CODE_ROOT@/EncoderPlotter1/controller/python/startup_info.py
**关键词**: OTA, V4065, DPT15, RS485, NoMulti, 断电检测, 错误Hall, 首次启动信息, 0x8A, Build ID

功能记录：EncoderPlotter 已支持 DPT15、V4065、NoMulti、RS485 设备的首次启动信息查询，用于 OTA 后断电检测错误 Hall。软件手动发送设备命令 0x8A，通过现有通信调度接收 37 字节响应，校验标识 0x56385342、协议版本 1、数据长度 36、CRC8(poly 0x97)及字段关联关系；两个 64 位 Build ID 以十六进制字符串保存。页面显示读取完成、掉电记录有效性、内外圈历史 Hall、是否传入算法、启动状态、判断来源和选定 Hall。设备条件：arguments.algorithm=4065、rotorInnerSize=15、model=0 或缺失、DPT/RS485。验收向量已通过，Python/JavaScript 静态检查和 13 项协议测试通过；真实硬件 OTA 场景仍需现场验证。

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

#### knowledge:why-reg-read-fails: 寄存器读取失败的分层诊断

**类型**: K  **来源**: @CODE_ROOT@\driverSoftware\docs\firmware_dev_versioning_coordination.md
**关键词**: reg_read, Factory, read_version, fw_profile, dirty, git sha, RS485, HID, reader_mp_worker, timeout

基于固件联调版本文档和当前代码分析寄存器读取故障：server.py 的 reg_read 直接走 Factory REG_READ，不依赖 fw_profile；read_version 才读取 0x0C/0x0D 并决定 dev/正式档案。故所有寄存器 timeout/no response 首先指向 RS485/HID reader、设备 ID、Factory 协议/设备状态或 MP reader 卡死；若 read_version 成功但 MIT/Default/遥测失败，则重点检查 dev-<sha>.json 缺失、dirty/SHA 解码、档案 active 被清空、调用顺序未先 read_version。读到数值但不合理则检查 float-bits 类型寄存器与普通 float 的解码差异。证据：core/commands.py reg_read/read_version，server.py api_read_version/_read_reg_float/_match_fw_profile，docs/firmware_dev_versioning_coordination.md，docs/feedback_ledger.md 中 MP reader 卡死记录。

#### sire-20260922-dpt-dpb-plot: DPT final plot must not inherit stale DPB type

**类型**: P  **来源**: @CODE_ROOT@\EncoderPlotter_0703_03\controller\python\sub_automation\pcba\pcba_check.py
**关键词**: DPT, DPB, PCBA, 最终绘图, #TYPE, 型号覆盖

PCBA最终绘图若传入界面型号，应以parse_model(model)得到的产品系列作为汇总绘图类型；临时hall_data文件的#TYPE可能是历史残留，不能覆盖当前DPT选择。修复位置：controller/python/sub_automation/pcba/pcba_check.py plot_all。验证：py_compile通过；真实桌面/设备场景因环境缺失标记BLOCKED。
