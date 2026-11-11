# 全局问题解决记录 (P)

### P-001: Electron axios localhost连接失败需改用127.0.0.1
**日期**: 2026-07-04
**项目**: Emy
**关键词**: localhost, 127.0.0.1, IPv6, ECONNREFUSED, Electron, axios

**需求场景 / 现象**: Electron中axios请求localhost时默认优先尝试IPv6地址(::1)，若后端服务仅监听IPv4(0.0.0.0或127.0.0.1)，会导致连接被拒绝（ECONNREFUSED）。前端Vue文件中所有API调用均使用 http://localhost:8001，导致请求失败。

**方案 / 实施步骤**:
1. 将所有前端Vue文件中的 http://localhost:8001 替换为 http://127.0.0.1:8001。
2. 将测试文件中的 localhost:8001 也替换为 127.0.0.1:8001。
3. Electron主进程(main.js)已使用127.0.0.1，无需修改。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 根因：Node.js/DNS解析器在Electron环境中优先解析localhost为IPv6地址。严重度CRITICAL。

**关键文件与接口**: http://127.0.0.1:8001；Electron main.js；axios

**状态**: 已完成

### P-003: npx命令缺少--yes标志导致非交互环境挂起
**日期**: 2026-07-04
**项目**: Emy
**关键词**: npx, --yes, 交互式提示, subprocess, 挂起, 超时, Ok to proceed? (y), degit, create-next-app

**需求场景 / 现象**: command_executor.py的execute_npm_create方法中，npx命令未添加--yes标志。当npx需要安装未安装的包(如degit)时，会提示"Ok to proceed? (y)"，在subprocess.run的非交互环境下导致命令挂起或超时。

**方案 / 实施步骤**:
1. 所有npx命令统一使用 npx --yes 前缀。
2. npm create命令添加 -- --yes 参数。
3. create-next-app等工具自带的--yes参数也一并添加。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 根因：npx默认在安装未安装的包时需要交互式确认。严重度HIGH。

**关键文件与接口**: command_executor.py 的 execute_npm_create；npx --yes；npm create -- --yes

**状态**: 已完成

### P-007: 【读取数据】zip偶发不完整——多级fire-and-forget时序竞态
**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**关键词**: 读取数据, zip, 偶发不完整, 多级, fire-and-forget, 时序竞态, device.js, tools.js, medianCheck.js, file.js, zip.finalize(), EOCD, createWriteStream, unhandled rejection

**需求场景 / 现象**: 中值检测后生成的zip文件偶发缺失文件或截断；小数据量正常、大数据量必现。

**方案 / 实施步骤**:
1. device.js：switchReadoutModeStateMulti内await stopReadout；startMedianCheck内await switchReadoutModeStateMulti（删除1秒延时）、await saveMedianCheckResult。
2. shared/tools.js：zipDataFiles创建output后同步注册streamDone监听（close/error）+noophandler catch；finalize()后await streamDone。
3. medianCheck.js：invoke加await。
4. main/file.js：zip-readout-data handler加return（使await生效）+catch清理残缺zip。

**验证方法**: 独立Node脚本require shared/tools.js（electron依赖为惰性引入，纯Node可跑）。TC1正常打包：resolve瞬间EOCD在位+SHA256一致+可解压。TC4父目录不存在：5秒内干净reject、无uncaught、无unhandled警告。TC5旧逻辑对照组：实证resolve时文件缺尾->800ms后补齐（根因直接证据）。zip完整性验证法：EOCD签名(50 4B 05 06)必须位于文件末尾22字节内。

**踩坑 / 已知异常与失败经验**: 根因三层叠加：(1)startMedianCheck停止读取后仅setTimeout(1000)就打包，stopReadout链条耗时随数据量增长，超1秒时temp目录的.bin未写完，且三级fire-and-forget（switchReadoutModeStateMulti / stopReadout / saveMedianCheckResult 均未await）错误被吞掉；(2)zip.finalize()裸调用后立即resolve，实测resolve瞬间缺末尾1427字节，800ms后才补齐；(3)output流的error监听在await import之后才注册，open失败时错过事件->Promise永久挂起+uncaughtException逃逸。
可复用要点：fire-and-forget修复要逐级补await从UI入口到IO出口贯通，前提是ipcMain.handle必须return promise，否则invoke立即resolve；createWriteStream错误监听必须在任何await之前同步注册；Node15+ unhandled rejection窗口内需创建后立即promise.catch(()=>{})挂noophandler，后续await仍能拿到rejection；zip-stream v7的finalize()不支持回调（源码finalize(){this.finish()}），完成信号=输出流close事件。
遗留技术债务：saveMedianCheckResult返回{success:false}不检查，失败仍报检测完成+SN+1；空目录静默生成空zip；startMedianCheck启动读取未await，启动耗时超testTime时可能取不完整数据；既有：calculateColumnAverages抛错时isMedianChecking不复位。

**关键文件与接口**: components/encoder/device.js；shared/tools.js；components/encoder/medianCheck.js；main/file.js

**状态**: 已完成

### P-008: debug-plot-viewer对MPT单圈/半标定图配对失败报"无法找到配对的图表数据"
**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**关键词**: debug-plot-viewer, MPT, 单圈, 半标定图配对失败, 无法找到配对的图, 表数据, debug-plot-viewer.html

**需求场景 / 现象**: 导入调试日志+前端绘图，MPT编码器弹"无法找到配对的图表数据"。根因：viewer只认DPT双圈的6个标题(innerHalls/outerHalls/inner calc data等3组配对)；MPT单圈ringType=""生成的标题是"halls"/" calc data"/" base data"(带前导空格)，全部不匹配->topPlot/bottomPlot均undefined->alert。DPT半标定只采单圈同样缺对侧图报错。

**方案 / 实施步骤**:
仅改asset/debug-plot-viewer.html，算法仓库零改动：
1. resolvePair()统一配对解析：标题trim后匹配；新增MPT单圈配对(calc data+base data)与单图兜底(返回bottom:null)。
2. 单图模式singleMode：对侧缺失时降级上图显示、隐藏下图面板与图例，不再alert。
3. 动态tab: availableGroups按实际存在的图生成分组(Halls/Inner Calc/Outer Calc/Calc)，MPT只显示Halls+Calc。
4. series数据源统一为loadCurrentPlot缓存的topSeriesData/bottomSeriesData，替换computeYAxisGroups/selectAllYAxis/autoSplitYAxis/renderSingleChart中4处重复的硬编码标题查找。
5. 散点判断改为白名单: halls类连线(innerHalls/outerHalls/halls)，其余散点。
6. 清理死代码: switchTab/hallsTabs/innerCalcTabs/outerCalcTabs(模板无引用)。

**验证方法**: 场景矩阵：DPT全量=3组双图如旧；MPT单圈=Halls单图+Calc双图；DPT半标定=有对侧的双图+缺对侧的单图降级；未知标题=单图不崩溃。

**踩坑 / 已知异常与失败经验**: MPT单圈标题带前导空格，配对前必须trim；缺对侧图时应降级单图而非alert。

**关键文件与接口**: asset/debug-plot-viewer.html；resolvePair；singleMode；availableGroups

**状态**: 已完成

### P-009: debug-plot-viewer滚动放大后上图空白下图正常（uPlot乱序x二分裁剪失效）
**日期**: 2026-08-28
**项目**: EncoderPlotter_0703_03
**关键词**: debug-plot-viewer, 滚动放大后上图空, 白下图正常, uPlot, 乱序, 二分裁剪失效, debug-plot-viewer.html

**需求场景 / 现象**: calc/base配对图（上下联动双图）初始显示正常，滚动放大后上图(calc data)整图空白，下图(base data)正常。根因：上图x=(实测角度+i*相位差)%360，实测角度任意起点，一圈回绕处359→0，x数组乱序；下图x由FFT还原基准角度生成，天然升序。uPlot渲染依赖有序x做二分索引裁剪(idxAt)：初始全量视图i0=0/i1=N-1不受乱序影响；setScale缩放窗口二分查找在乱序数组上取到错误切片，整图空白。

**方案 / 实施步骤**:
仅改asset/debug-plot-viewer.html，算法仓库零改动：
1. normalizeSeries(series)：按首序列x升序重排，x与全部y应用同一置换（配对关系不变，散点图视觉无变化）；先做有序快检，halls图(索引x天然有序)零开销跳过。
2. loadCurrentPlot记录各图自身数据边界topXMin/Max、bottomXMin/Max（排序后首尾即最值）。
3. applyXScale按图钳制：每张图与自身边界求交，窗口与该图数据完全不相交时回退该图全量视图而非空白。
4. 滚轮锚点改用wheel事件坐标(e.clientX-rect.left)+NaN守卫。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: uPlot的data[0](x轴)必须升序，否则初始渲染正常但缩放/游标/拖选全部异常——症状极具迷惑性。u.cursor.left在仅滚动未移动鼠标时可能未初始化，posToVal(undefined)=NaN会把比例尺置NaN导致空白。

**关键文件与接口**: asset/debug-plot-viewer.html；normalizeSeries；applyXScale；loadCurrentPlot

**状态**: 已完成

### P-011: debug-plot-viewer缩放卡顿与海量散点前端绘图性能优化（rAF合并+fillRect+自适应密度）
**日期**: 2026-08-31
**项目**: EncoderPlotter_0703_03
**关键词**: debug-plot-viewer, 前端绘图性能优化, 组合拳, 海量散点, debug-plot-viewer.html, 缩放卡顿数秒, 散点全量重绘, 高频事件

**需求场景 / 现象**: debug-plot-viewer导入调试数据后缩放要几秒才响应（缩放卡顿数秒）；海量散点（每曲线数万点，16曲线可达数十万）前端绘图性能优化。用户约束：散点最终显示必须完整不抽稀。

**方案 / 实施步骤**:
性能瓶颈按贡献排序：uPlot points 默认逐点 arc 圆形绘制；"停止交互后恢复全量"防抖重绘本身是一次 space:0 全量重绘；normalizeSeries 每次切 tab 重复排序；高频滚轮事件未合并。
优化组合（asset/debug-plot-viewer.html）：
1. rAF合并：applyXScale的setScale合并到每帧最多一次(取最新参数)；beforeDestroy清理 _scaleRaf/_fullPointsTimer。
2. symbol 用 fillRect 代替默认圆弧：canvas 批量矩形比逐点 arc+fill 快数倍，2px方块视觉无差。
3. 可见点数自适应密度（替代"停止后恢复全量"）：x有序二分统计窗口内点数，可见点>6000/曲线用 space:2，放大后点少自动 space:0 完整渲染。关键时序：density 必须在 setScale 之前按"将应用的窗口"算好。
4. normalizeSeries 结果缓存到 plot._normSeries：切 tab 免重复排序。
5. 初始渲染保留 space:0 完整（一次性成本，loading 遮罩兜底）；缩放全程自适应。
（早期P-010中间方案：交互中rAF回调里 setPointsSpace(2)——u.series[i].points.space 是渲染期属性，改后随setScale重绘生效，无需重建实例；停止交互150ms(防抖)后 setPointsSpace(0)+redraw 恢复完整散点。该方案被自适应密度取代。）

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: - 根因两层叠加：散点 space:0 全量绘制，uPlot每次setScale重绘可见范围内所有点，单次重绘秒级；滚轮/平移高频触发，每个事件两图各全量重绘一次，滚动几下排队数十次重绘。
- uPlot缩放本就只画可见范围内的点(i0..i1二分裁剪)，卡在"可见点数太多"而非"画了窗口外的点"。
- u.series[n].points.space 可运行时直接改+redraw生效(社区常用hack)，是动态密度切换的关键。
- "散点不能抽稀"的本质需求是"放大看细节时点完整"：全量视图下每像素重叠几十个点，space:2 与全量视觉等价；放大后点数少自动恢复完整。
- setScale 是同步重绘：渲染期属性(points.space)必须在其前修改才会在该次重绘生效。
- 初始渲染/切换tab/Y轴操作走renderSingleChart重建实例，天然space:0完整显示。
- uPlot points.symbol: (u, si, di, x, y, val, radius, size) => ctx.fillRect(x-1,y-1,2,2) 自定义点绘制，uPlot 调用前已设 fillStyle=曲线色。

**关键文件与接口**: asset/debug-plot-viewer.html；setPointsSpace；points.space；points.symbol；plot._normSeries

**状态**: 已完成

### P-012: 前后端渲染图形不一致——uPlot共享x网格 vs matplotlib每曲线独立x
**日期**: 2026-08-31
**项目**: EncoderPlotter_0703_03
**关键词**: 前后端渲染图形不, 一致, uPlot, 共享, 网格, vs, matplotlib, 每曲线独立, debug-plot-viewer.html

**需求场景 / 现象**: 同一份调试数据，matplotlib后端图与前端uPlot图形状不同。根因：matplotlib每条曲线独立 (x,y)，算法侧 calcHall_i 的 x=(角度+i*相位差)%360；uPlot所有series共享data[0]一个x网格，viewer 原实现 topChartData.push(series[0].x) 只取第一条曲线的x，其余曲线的y被错位映射到 calcHall0 的x位置，图形完全走样。

**方案 / 实施步骤**:
仅改asset/debug-plot-viewer.html 合并模式，算法仓库零改动：
1. seriesShareX(series): 逐元素检测各曲线x是否一致（一致=halls类采样索引图走原多series路径）。
2. mergeSeries(plot, series): x不一致时把全部曲线点集按x排序合并为单条超长series {x,y,src,labels}，src记录每点来源曲线；缓存plot._merged。
3. renderSingleChart merged分支: 单series+paths=null+自定义symbol，symbol里按 u._mergedSrc[dataIdx] 取COLORS着色（还原多色散点）。
4. refreshMergedChart(position): 曲线开关/全选/全清/反选按 curves[i].show 过滤点集 setData；过滤后src必须同步换为过滤视图(srcs)并挂 u._mergedSrc。
5. computeYAxisGroups merged返回[0]（单轴，与matplotlib原图一致）。
6. toggleVisible/showAll/hideAll/reverseAll 四方法rAF回调开头插 merged 分支。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: uPlot series共享x网格是硬约束；matplotlib多曲线独立x的正确还原=合并单series+symbol按来源着色。过滤数据后 dataIdx 与全量 src 错位是隐蔽bug源：着色索引必须随过滤视图切换（挂u实例上）。性能无回退：合并后总点数与多series相同。

**关键文件与接口**: asset/debug-plot-viewer.html；seriesShareX；mergeSeries；refreshMergedChart；u._mergedSrc

**状态**: 已完成

### P-013: 合并模式引入后上图不显示/下图单色（normalizeSeries置换误伤+src挂载晚于首帧）
**日期**: 2026-08-31
**项目**: EncoderPlotter_0703_03
**关键词**: 合并模式引入后上, 图不显示, 下图单色, normalizeSeries, 置换误伤, src, 挂载晚于首帧, uPlot, mergeSeries, _mergedSrc, shareX

**需求场景 / 现象**: P-012合并模式上线后：上图(calc data)默认不显示，下图(base data)只剩一个颜色。

**方案 / 实施步骤**:
1. normalizeSeries分支：shareX（各曲线x一致）→全部曲线x/y同一置换（共享网格语义）；独立x→仅series[0]排序（x/y同置换），其余曲线整体原样返回（它们的乱序由mergeSeries全局点集排序统一解决，不依赖normalize）。
2. symbol着色双通道：u._mergedSrc优先（过滤视图），回退闭包srcRef.src（构造期首帧）——srcRef在构造前创建。

**验证方法**: 验证脚本实测：合并后全部原始(x,y)配对保留+x有序 PASS。

**踩坑 / 已知异常与失败经验**: 根因两个独立bug：1) normalizeSeries把series[0]的排序置换应用到了每条曲线自己的x和所有y，独立x模式（相位错开图）下curve_i的x与series[0]的x无对应关系，套置换后(x,y)配对被破坏，合并后点全错位。2) inst._mergedSrc = ... 写在 new uPlot 之后：uPlot构造时同步完成首帧渲染，symbol闭包里 u._mergedSrc 还是undefined → if(src)跳过着色，fillStyle保持canvas遗留状态 → 首帧全图单色。关键认知：排序置换只在“同一网格”语义下可全局套用；任何“实例属性供渲染回调读取”的模式，属性必须在构造前可达（闭包或opts内），实例赋值晚于构造=首帧读不到。

**关键文件与接口**: normalizeSeries；mergeSeries；inst._mergedSrc；srcRef.src；new uPlot

**状态**: 已完成

### P-014: i18next多语言包四类隐蔽缺陷的排查与修复
**日期**: 2026-09-02
**项目**: EncoderPlotter_0703_01
**关键词**: i18next, 多语言包四类隐蔽, 缺陷的排查与修复, i18n.js

**需求场景 / 现象**: 国际化显示错乱：英文模式显示中文、中文模式显示英文（fallbackLng反向回退）、插值信息丢失、同一key不同文案。

**方案 / 实施步骤**:
1. 动态拼接 → 静态key + i18next插值：`$t("字段{{var}}", {var: x})`，翻译值加占位符。
2. 重复key → 删除后定义项（保留正确值）；用正则逐包区域扫描源码检测。
3. 包间不一致 → 以HTML/代码实际调用的key字符为准修正语言包key（注意尾随空格、全角/半角）。
4. 检测脚本：模拟window后require语言包，getResourceBundle取双包做key集合差集 + 全代码正则提取静态$t key反向验证。

**验证方法**: 项目根目录node临时脚本: global.window={}; require('./components/i18n.js'); const en=window.i18next.getResourceBundle('en','translation') ... 差集/存在性/插值断言。

**踩坑 / 已知异常与失败经验**: 根因四类：
1. $t()动态拼接key（`$t("前缀"+变量)`、模板字符串）永远匹配不到包内key，直接回退显示key原文。
2. JS对象字面量重复key静默覆盖（后者生效），造成"改了A处文案却不生效"。
3. en/zh包key不一致 + fallbackLng机制：zh缺key回退en值（中文界面显示英文）；en缺key显示中文key原文（英文界面显示中文）。
4. 调用方传插值参数但翻译值无{{占位符}}，参数被吞。
经验：(1) key为中文时，zh包"缺失"比en包缺失更隐蔽——fallbackLng='en'会让中文界面显示英文，必须逐key对齐双包 (2) HTML注释块内的$t改造无显示影响但为解除注释预留i18n就绪 (3) 源码文本级key比对对\n转义会假阳性，需运行时验证。

**关键文件与接口**: components/i18n.js；i18next getResourceBundle；$t()

**状态**: 已完成

### P-015: Electron子窗口全部关闭后主窗口被其他应用窗口挡住
**日期**: 2026-09-02
**项目**: EncoderPlotter_0703_01
**关键词**: Electron, BrowserWindow, parent, closed, focus, z-order, 前台, 窗口遮挡, owner window

**需求场景 / 现象**: 代码中有单独打开新窗口的操作（日志窗口、导入数据图表窗口），这些窗口全部关闭后，上位机主窗口被其他应用的窗口挡住，不在前台。

**方案 / 实施步骤**:
1. 在 main/index.js 增加工具函数 focusMainWindow()：mainWindow 存在且未销毁时，若 isMinimized() 则 restore()，再 show()、focus()。
2. 在 createLogWindow 和 viewerWindow 的 'closed' 事件末尾调用 focusMainWindow()。
3. 多日志窗口场景安全：parent关系保证其余子窗口仍在主窗口之上，focus不影响其层级。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 根因：两类子窗口（createLogWindow L291-323、open-import-plot-viewer L329-354）共同特征：1) `parent: mainWindow`，Windows owner窗口机制，子窗口z-order恒在主窗口之上；2) `show: true` 打开即抢焦点；3) `closed` 事件只做清理，没有把焦点还给主窗口。最后一个子窗口关闭时，Windows把激活权交给z-order中紧随其下的顶层窗口，若期间用户切换过其他应用，激活权落到别的应用窗口上；Electron不会自动把owner窗口带回前台，必须手动focus。

**关键文件与接口**: main/index.js：createLogWindow、open-import-plot-viewer、focusMainWindow

**状态**: 已完成

### P-016: 阈值面板三处模板文本硬编码中文未国际化（P-014第5类变体）
**日期**: 2026-09-02
**项目**: EncoderPlotter_0703_01
**关键词**: i18n, 硬编码, $t, title属性, threshold.html, 双包key

**需求场景 / 现象**: threshold.html 中"错误阈值范围/最小错误阈值/最大错误阈值"三处直接写中文未包 $t()，且 title 属性（重置按钮 tooltip）同样硬编码；语言包中也无对应 key（P-014 四类之外的第5类：Vue 模板文本/HTML 属性硬编码遗漏）。另含2026-09-03烧录/标定台架一批同项目排障经验（见踩坑）。

**方案 / 实施步骤**:
i18n 硬编码修复：
1. 模板文本 → {{$t('key')}}。
2. title 属性 → :title="$t('key')"。
3. en/zh 双包同步补 key（错误阈值范围/最小错误阈值/最大错误阈值/重置为默认值），插入"阈值设置提示"注释区。
4. 运行时验证双包 key（node 模拟 window 后 getResourceBundle 断言）。

**验证方法**: 运行时验证双包 key（node 模拟 window 后 getResourceBundle 断言）；两文件 node --check；无探头环境下实际运行 loadHex，日志完整呈现 配置上下文 → 3次尝试(耗时+日志路径) → 携带上下文的异常；采集数据 20 列中 index1~9（内圈9霍尔）逐列检查 min/max/变化，全部有有效信号即 9 霍尔硬件（col9 若全 0 才是 8 霍尔）。

**踩坑 / 已知异常与失败经验**: - flashPanelV2 报 TypeError: Cannot read properties of undefined (reading 'SERIES')：Vue 2 不代理以 _ 或 $ 开头的 data 属性到组件实例，this._schema 恒为 undefined；修复为将 data 属性 _schema 重命名为 schema（computed/watcher 共 4 处 JS 引用及 flashPanelV2.html 模板 1 处 v-for 引用）。教训：Vue 2 组件 data 属性禁止 _ / $ 前缀命名。
- 固件烧录V2 FileNotFoundError: JFlash/DPB/dpb_IAP.hex 解析到项目根：finalstep0_loadHex.py 的 _CALI_CFGS/_RECALI_CFGS 在模块 import 时构造，BaseConfig.__post_init__ 将相对路径按当时 cwd 固化；factoryAutomation.js spawn 不带 cwd；loadHex.main() 里的 os.chdir 在 import 之后才执行。修复：flash_tool_v2.py 在 sys.path.insert(STATION_DIR) 之后、import station 模块之前加 os.chdir(STATION_DIR)（带 frozen 守卫）；loadHex 的 os.chdir 从 main() 提前到模块导入时（构造 _SERIES_SPEC 配置表之前）。教训：模块级常量表中做相对路径 resolve() 是 cwd 陷阱。
- station.py 外盘路径（@DRIVE_F@/、E:）在本机全部失效：station.py 为产线机台配置文件（GUI 按行锚定正则改写），三处修改须保持单行 name = value 格式：SavePath→@DRIVE_D@/生产数据/BURN/测试；JLinkPath→@DRIVE_D@/software/SEGGER/JLink/JLink.exe（V9.14a，经 JLink_x64.dll FileVersion 确认）；AppPath→@DRIVE_D@/生产数据/BURN/0_latest/APP-DPT-411（占位）。遗留：CompilerPath 仍指 @DRIVE_E@/Keil（本机未装 Keil，编译步骤不可用）。教训：机台配置文件换机器必须同步改四个机台路径（AppPath/CompilerPath/JLinkPath/SavePath）；验证 getLogger 文件日志须实际调用 getLogger() 而非仅 import。
- step1 日志黑盒：finalstep0_loadHex.py main() 烧录前输出关键上下文 3 行日志；flash_device() 每次 JLink 尝试输出 第N/3次执行完成（耗时Xs）；main() 失败时 RuntimeError 携带 mode/NC/重试次数；flash_tool_v2.py step1 调用前输出 serial/mode/NC/JLink 参数。
- 界面日志非实时（多行整块 + stderr 全红）：_runPythonScript 把 chunk 原样转发，Python 突发时一个 chunk 含多行；Python logging 全部走 stderr，UI 一律按 error 红色。修复：factoryAutomation.js _runPythonScript 用 readline.createInterface({input: stream}) 按行回调 onStdout/onStderr（跳过空行）；flashPanelV2.js handleProgress 的 'error' 分支改走 parsePythonOutput 行级分类（ERROR/Traceback/失败→红，WARNING→黄，INFO→白）。教训：Electron 渲染进程 spawn 子进程的流式转发本身正常，日志"非实时"通常是行拆分/着色层问题而非管道问题。
- 采集完成后重连 COM26 PermissionError 且卡死（could not open port 'COM26' PermissionError(13)）：finalstep0_collect_v2.collect() 用完 AnalyzerDual 后不关串口（无 close() 方法）；sub_embedded Analyzer.connect() 串口打开失败不抛异常（仅 logging.exception + serial=None + 返回 False）。修复：collect() 收尾 analyzer.ser.close() 释放串口；AnalyzerDual.readThread 裸 except: continue 改为检测 self.ser/is_open，串口已关时 break；flash_tool_v2._connect_encoder 加 analyzer.serial is None 校验立即 raise。教训：pyserial 串口打开失败的模式是"返回 False + serial=None"而非异常。
- Recalibration.enter() 失败分支误打 Success 日志：失败分支改打 logging.warning('Enter Recalibration Mode FAILED（应答=...）')，return False 语义不变。step1 JLink 烧录结尾 r,g,q 复位运行新固件，再标定状态复位即丢，采集驱动必须重新 enter（设计使然）。
- Recalibration.enter() 加固：enter(maxAttempts=5, retryDelay=1.0)，每轮先发 allEnterRecalibration 命令 → getMemory('v') 回读校验 → 失败 sleep 1s 重试；应答匹配改 startswith(b'SUCCESSFUL')（实测应答形如 b'SUCCESSFUL1\x00\x00...'，原严格相等永远失败）。教训：串行协议回读按页对齐（256B 页），比较要用前缀匹配。
- 评估报 angles error may be too large（anglesErrRange=0.112 > 0.1 阈值）：界面误传 --inner-size 10（station.py 被改写为 Configs10/8霍尔），而台架实际 15 内径 9 霍尔硬件；质量门槛正常拦截非代码故障，界面选择须与台架实际硬件一致。

**关键文件与接口**: threshold.html；i18n 语言包 en/zh；flashPanelV2.js；flashPanelV2.html；flash_tool_v2.py；finalstep0_loadHex.py；factoryAutomation.js；station.py；Recalibration.enter()

**状态**: 已完成

### P-017: Windows 深目录下台账创建报 WinError 206
**日期**: 2026-09-12
**项目**: SIRE 工作流
**关键词**: Windows, MAX_PATH, WinError 206, 长路径, 扩展前缀, sire_run, 台账, lp(), LONG_PATH_PREFIX

**需求场景 / 现象**: 在带 UUID 的深层工作区目录下执行 `sire_run.py init`，报 `FileNotFoundError: [WinError 206] 文件名或扩展名太长`，台账 run 目录建了一半，evidence 子目录创建失败。

**方案 / 实施步骤**:
1. 在 `sire_run.py` 加 `lp()` helper：路径绝对化后若超过 240 字符，前面拼上 Windows 扩展长度前缀，再交给 os 接口。
2. 全部 makedirs / open / exists / listdir 统一走 `lp()`，共 12 处调用点。
3. 前缀定义成模块常量 `LONG_PATH_PREFIX`，不要在每个调用点重复手写转义。

**验证方法**: 导入模块后打印 `repr(sire_run.LONG_PATH_PREFIX)`，应为 4 字符前缀；再用一个 258 字符的路径调 `lp()`，返回值应以该前缀开头；短路径调 `lp()` 应原样返回不加前缀。

**踩坑 / 已知异常与失败经验**: 根因：Windows 默认 MAX_PATH 为 260 字符，台账路径形如 `<工作区>/.sire/runs/R20260912-125216/evidence/U-01/impl`，工作区本身已 180 字符时就会超限，与脚本逻辑无关，是 API 限制。坑在转义层数：前缀是四个字符（反斜杠 反斜杠 问号 反斜杠），Python 源码里必须写成 8 个反斜杠形式的字面量，少写一层会得到三字符的错误前缀，且不报错、静默失效。预防：任何要在用户任意目录下建多层子目录的 Windows 脚本，都先套 `lp()`，不要假设工作目录是浅路径。

**关键文件与接口**: sire_run.py；lp()；LONG_PATH_PREFIX

**状态**: 已完成

### P-018: fw v3.4.6 使能态修改力矩舵机无响应 (四根因叠加)
**日期**: 2026-09-22
**项目**: driverSoftware (@CODE_ROOT@\driverSoftware), 发布 v0.13.9
**关键词**: v3.4.6, MIT, mit_scales, 力矩无响应, hw_update_mit, 500, baudrate, READER_MP, 使能对齐, 固件档案, TypeError, update_continuous_frame, gen_fw_profile.py

**需求场景 / 现象**: 使能状态下改力矩 (TAU), 舵机转动无变化; 前端控制台一串 500; 偶发使能数秒后自动失能。

**方案 / 实施步骤**:
1. 档案用 `FW_REPO_PATH=@CODE_ROOT@\driver python tools/gen_fw_profile.py --tag v3.4.6` 重新生成 (禁止手填)。
2. `reader_mp.update_continuous_frame` 补 `baudrate: Optional[int] = None` (接收并忽略, 与 wrapper 同签名)。
3. `server._stream_baud()` 以连接参数 (/api/params 写的全局 baudrate) 为唯一真相源, 5 处 start_continuous 统一使用。
4. motion.js 抽出 `enableAlignPending()`, 按钮文案与 doEnable 共用一个判据。
5. 回归门禁: `tests/unit/test_v346_enable_tau_regressions.py` (修复前 7/7 红) + 同事的 `test_fw_profile_mit_scales.py`。

**验证方法**: 真机 id15 fw v3.4.6 5Mbps, Kp=0 Kd=0.05, τ=0.1/0.2/−0.2/0 → 转速 1.30/3.20/−3.23/0 rad/s, 反馈 τ≈τ_cmd−Kd·v, 无故障; UI 全路径 (连接→使能→改力矩→失能) 通过; 单测 2080 passed。

**踩坑 / 已知异常与失败经验**: 根因 (四个叠加, 缺一个都修不好): (1)`firmware_profiles/v3.4.6.json` 的 `mit_scales` 被手填成 pos/vel/tau=10000 (误把 Kp/Kd 量化 scale 0x4B/0x4C 的默认值当刻度)，固件 v3.4.0 起真值 = 2^24/2π (2670176.86) / 512 / 2048, v3.4.5 与 v3.4.6 未变, 后果: 力矩指令 ×4.88, 位置 ÷267; (2)6cee629 让 `server.hw_update_mit` 给 `backend.update_continuous_frame(..., baudrate=)` 传参, 只改了 `core/reader_wrapper.py`, 默认启用的多进程后端 `core/reader_mp.py` (READER_MP=1) 签名没跟 → 每次热换帧 TypeError → HTTP 500, 改参数全部静默不下发; (3)连续流波特率取前端 `req.baudrate`, 前端 `store.state.baudrate` 未同步时回退 1M → 5M 设备收不到 MIT 帧, 另有 hw_start / 失能软着陆两处根本没传 baudrate; (4)「使能对齐」按钮文案判据含 Kp>0, 而 doEnable 的 alignmentRequired 不含 → Kp=0 改过位置时按钮写「使能」点下去只对齐不上力。
排查弯路: 曾把"使能后 OverTempMotor 跳闸"判成热模型参数问题 —— 实为错刻度 (力矩 ×4.88) + Kd=0 空载冲到 39.7 rad/s 的结果; 曾推测 "v3.4.5 自动清除掩盖跳闸", 读 0x89=0 (自动清除关) 即否定 —— 先读寄存器再下结论; 用户说 "4292e85 是好的", 实际那次连的是 v3.4.5 固件且可能走软轮询档, 比较好坏节点前先确认固件版本与测试路径一致。

**关键文件与接口**: firmware_profiles/v3.4.6.json；core/reader_wrapper.py；core/reader_mp.py；motion.js（enableAlignPending()、doEnable）；tools/gen_fw_profile.py；tests/unit/test_v346_enable_tau_regressions.py；test_fw_profile_mit_scales.py

**状态**: 已完成（已解决, 已发布 a6848b6 + c8ad4e6, tag v0.13.9）

### P-019: 位置读数卡在 804.2477 rad (v3.4.x 多圈超量程饱和)
**日期**: 2026-09-22
**项目**: driverSoftware / driver 固件 v3.4.x
**关键词**: 804.2477, 位置饱和, INT32_MAX, Q8.24, 多圈, kMitPosScale, 0x18, 0x67, 设零, pos_raw=2147483647

**需求场景 / 现象**: 位置显示恒为 804.247718, 使能对齐会把位置指令对齐到该值。

**方案 / 实施步骤**:
1. 电机停止时设零 (0x67 / UI「设零点」) 或断电重启。
2. 建议上位机检测 ±804.2477 时提示超量程并禁止 Kp>0 对齐 (未实现)。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 根因: 固件 `register_protocol.cpp:314` `static_cast<int32_t>(multi_angle × inv_gear × dir × 2^24/2π)`, v3.4 位置编码 Q8.24 输出端只覆盖 ±128 输出圈 (±804.25 rad); 超出时 ARM float→int32 饱和为 INT32_MAX (回包 pos_raw=2147483647)。现场: 0x18 转子多圈 = −43626 rad, 减速比 −50, 0x67 零点偏置 = 0 (从未设零) → 输出端约 138.9 圈, 超限。纯力矩空载测试 (Kp=0) 会让关节单向累积转动, 很快吃满 128 圈。风险: 此时做 Kp>0 位置控制, 目标被对齐到错误的饱和值, 会猛拽。

**关键文件与接口**: 固件 register_protocol.cpp:314；寄存器 0x18、0x67

**状态**: 部分完成（已定位, 未修, 需设零或防护提示, 待决策）

### P-020: 使能态 Kp 从 0 调到 >0 时位置指令陈旧 (潜在猛拽, 既有问题)
**日期**: 2026-09-22
**项目**: driverSoftware frontend/js/pages/motion.js
**关键词**: 使能对齐, Kp, 位置指令, 猛拽, pos_err, motion.js

**需求场景 / 现象**: Kp=0 使能后电机按力矩自由转动，位置指令停在使能时刻的值；若在使能中把 Kp 调到 >0，电机按 (陈旧目标 − 实际)×Kp 被拽回（潜在猛拽，既有问题，修复前后都存在）。

**方案 / 实施步骤**:
建议（未实施）：使能态 Kp 从 0→>0 时先把 pos 指令对齐到当前实测位置。

**验证方法**: 原记录未记载

**踩坑 / 已知异常与失败经验**: 已识别, 未修（新行为改动，待用户决策）。

**关键文件与接口**: frontend/js/pages/motion.js；Kp；pos_err

**状态**: 部分完成

### P-021: 【数据库清理】向量库 1.2GB 实为 driver 仓库全量导入，清理后 7.8MB
**日期**: 2026-09-24
**项目**: 原记录未记载（SIRE 向量库）
**关键词**: 向量库, sire_vectors.sqlite3, 数据库体积, driver 仓库, 全量索引, DONE_FULL_FILE_INDEXED, purge, VACUUM, 删除密码, 只增不减, purge_driver_repo.py, sire_db_backup

**需求场景 / 现象**: 新增知识后数据库一直显示 1.2GB，看起来没有增长；检索结果被 dualAngle.c 数表和 JSON 测量数据干扰。

**方案 / 实施步骤**:
1. 先用 sire_db_backup 备份（SIRE-DB-Backups\sire_vectors-20260924-084110.sqlite3）。
2. 用专用脚本 @SIRE_ROOT@\purge_driver_repo.py 只删 path 以 @CODE_ROOT@\driver\ 开头的片段（先核对数量 234303）。
3. 由用户在终端输入删除密码，重建 FTS，VACUUM，integrity_check。

**验证方法**: 结果：1208.9MB → 7.8MB；chunks 235480 → 1177；knowledge 97、task 512、keywords 5065 均不变；integrity ok。

**踩坑 / 已知异常与失败经验**: 原因：2026-09-21 之前某次任务把 @CODE_ROOT@\driver（v3.4.5, commit 8b85b1d0）1101 个文件全量切片导入（meta: driver_repo_chunk_count=234296），占 882MB（99.5%），其中 .json 测量数据占 822MB；09-21 数据库误缩到 5MB 后从备份恢复，这批数据随之回来；之后又定了「只增不减」规则，所以一直留在库里。真实知识（97 条记录）正文只有 106KB，按 GB 显示时看不出变化。注意：不要用 sire_vector_db.py index 加 SIRE_DB_ALLOW_DELETE 来删，它会一并删掉所有已经不在磁盘上的来源（例如 @SIRE_ROOT@\archive-20260921 的历史台账）；删除密码必须由用户本人在终端输入，AI 不代填；以后不要把整个代码仓库或测量数据 JSON 全量导入知识库，知识库只存提炼后的知识。遗留：「只增不减」模式下每次 reindex 都会给 global_index.json 追加一个新版本片段，重复片段会占据检索结果前几名，需要另行处理。

**关键文件与接口**: sire_vectors.sqlite3；@SIRE_ROOT@\purge_driver_repo.py；sire_db_backup；sire_vector_db.py；SIRE_DB_ALLOW_DELETE；global_index.json

**状态**: 已完成

### P-022: 【飞书自动化】Claude 桌面版 MSIX 路径虚拟化导致续跑工作目录不存在
**日期**: 2026-09-24
**项目**: 全局工具 @USER_HOME@\.feishu_bridge（【飞书自动化】）
**关键词**: 飞书自动化, MSIX, 路径虚拟化, AppData Roaming, LocalCache, Packages, scratch-workspaces, 工作目录不存在, cwd, os.path.isdir False, claude --resume, 计划任务, NEED_DIR

**需求场景 / 现象**: 飞书回复续跑报「工作目录不存在」，但桌面 Claude 会话里该目录明明存在（@DRIVE_C@/Users\<u>\AppData\Roaming\Claude\scratch-workspaces\...）。桌面会话内 shell 能进入该目录，包外 python/计划任务 os.path.isdir 返回 False。

**方案 / 实施步骤**:
1. listener.resolve_cwd(cwd)：目录存在直接用。
2. 否则若位于 %APPDATA% 下，遍历 %LOCALAPPDATA%\Packages\*\LocalCache\Roaming\<相对路径> 找到存在的即用。
3. 仍找不到则任务转 NEED_DIR，飞书提示用户回复「默认」（config default_cwd，@SIRE_ROOT@\AI\SESSION）或完整路径，绝不静默回退。
4. Hook 的 FEISHU_BRIDGE_CWD 仍传原路径，保证卡片显示和会话映射一致。

**验证方法**: 从桌面会话发起、在飞书回复 → bridge.log 出现「[目录] MSIX 虚拟路径映射 A -> B」，tasks 表该任务 DONE、耗时 ~37s，结果卡片回帖，桌面同步 Hook 回填 1 条。

**踩坑 / 已知异常与失败经验**: 根因：Claude 桌面版是 MSIX 应用，Windows 对其 %APPDATA% 写入做文件系统虚拟化，真实位置在 %LOCALAPPDATA%\Packages\<包名如 Claude_pzs8sxrjxfjjc>\LocalCache\Roaming\...；包内进程看到虚拟路径，包外进程（计划任务启动的监听器）看不到。旧版监听器目录不存在时 `cwd=None` 静默回退到监听器自身目录，续跑一直在错误目录执行而无人察觉。踩坑：1) 目录不存在时任何「回退默认目录」都是隐患，必须硬失败或询问用户；2) 判断 MSIX 虚拟化：同一路径包内 shell 可进、包外 python isdir=False，去 %LOCALAPPDATA%\Packages 下找 LocalCache\Roaming。

**关键文件与接口**: listener.resolve_cwd；config default_cwd；FEISHU_BRIDGE_CWD；bridge.log；tasks 表

**状态**: 已完成

### P-023: 【飞书自动化】多 AI 中转切换踩坑合集（计划任务复活、CC-Switch 覆盖、Codex Hook 信任、.CMD 注入、Opus 5.5 CLI 版本）
**日期**: 2026-09-24
**项目**: 飞书多 AI 中转 feishu-hub（@SIRE_ROOT@\AI\AI\feishu-hub）
**关键词**: 飞书自动化, 踩坑, 计划任务, Disable-ScheduledTask, 重启复活, CC-Switch 覆盖, settings.json, config.toml, notify, --previous-notify, hooks.json, hook trust, dangerously-bypass-hook-trust, codex.CMD, cmd.exe 元字符, 命令注入, Opus 5.5, unrecognized_model, 2.1.280, 桌面版自带 CLI, MSIX, 单一写入者, 两个 AI 同时改代码, .NET 相对路径, ReadAllText, os._exit 不刷新输出

**需求场景 / 现象**: 多 AI 中转 feishu-hub 切换与运行中的八类真实踩坑：旧服务重启后复活并抢飞书消息；CC-Switch 整体重写配置冲掉 Hook/notify；Codex hooks.json 的 Stop Hook 不执行；经 codex.CMD 传用户文本被 cmd.exe 篡改/注入；Opus 5.5 报 400「Claude Code 2.1.261 does not support this model; version 2.1.280 or newer is required」；两个 AI 同时改同一份代码；写/测脚本小坑；MSIX 路径虚拟化。

**方案 / 实施步骤**:
1. 下线旧服务：`Disable-ScheduledTask` + 结束进程 + 删除/改名入口脚本；切换后检查 settings.json、config.toml 是否被旧守护写回。飞书长连接事件只推给一个在线连接，新旧不能同时在线。
2. CC-Switch 覆盖配置：Claude 侧同步修改 cc-switch.db（settings.common_config_claude、proxy_live_backup.original_config）；Codex 侧 notify 串接由 Codex 执行器每 60s 守护（tomllib 解析、保留 computer-use 实际路径、未知 notify 不覆盖、写前备份写后校验）。
3. Codex Stop Hook 不执行：改走 config.toml `notify`（无需信任），用 computer-use 的 `--previous-notify '<JSON 数组>'` 串接自己的脚本；notify 数据在最后一个命令行参数（字段连字符写法 thread-id/turn-id/last-assistant-message，type=agent-turn-complete）；hooks.json 不再挂 Stop，防日后被信任后重复上报。
4. 带用户文本的命令直接调用 npm 包内原生 exe：`<npm前缀>\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe`；能走 stdin 的一律走 stdin。
5. Opus 5.5：执行器自动选 Claude 桌面版自带的最新 CLI（`%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\claude-code\<版本>\claude.exe` 取最高版本），找不到回退 npm。
6. 多 AI 协作：约定单一写入者（桥代码 Claude 独占，Codex 只改 executors/codex/）；交接给另一个 AI 时写明允许改动的目录、禁止碰线上配置、不准 push；复核时先 `git diff --stat` 查越界；要求「每个文件单独写入」。
7. MSIX 路径虚拟化：Claude 桌面会话 cwd 位于虚拟 %APPDATA%，包外执行器需映射到 %LOCALAPPDATA%\Packages\*\LocalCache\Roaming；两个执行器都已实现 resolve_cwd。

**验证方法**: 问题 1：`Get-ScheduledTask FeishuClaudeBridge` 为 Disabled、无 listener.py 进程。问题 2/3：人为冲掉 config.toml 串接后重启 Codex 执行器，几秒内补回；真实 codex exec 一轮后 hub.sqlite3 turns 表出现该 thread-id。问题 4：测试 Q1 元字符多行 prompt 逐字一致。问题 5：`--model claude-opus-5-5` 真实调用 modelUsage=claude-opus-5-5。

**踩坑 / 已知异常与失败经验**: (1)切换时只 `Stop-ScheduledTask FeishuClaudeBridge`，电脑重登录后它按登录触发器又启动，旧监听器还带「每 60s 补回 Hook」守护，把旧 Hook 写回 settings.json，飞书消息被旧桥处理、回复为空。(3)Codex 要求持久化 hook trust（`--dangerously-bypass-hook-trust` 帮助原文 "without requiring persisted hook trust"），桌面端不弹信任提示、CLI 也没有信任子命令，脚本手动喂数据正常但真实轮次零上报。(4)`shutil.which("codex")` 返回 `@DRIVE_C@/nvm4w\nodejs\codex.CMD`，Popen 列表参数经 cmd.exe 二次解析，prompt 中 `& | % ^ " < >` 和换行被截断/展开/当作命令，且单行 ≤8191 字符。(5)全局 npm 的 claude.exe 比桌面版旧；`--model opus` 在旧版解析为 claude-opus-5；真实调用看 JSON 输出的 modelUsage 键确认实际模型。(6)Codex 在 Claude 不知情时改了旧桥 listener/hook，测试失败、设计冲突；另一个 AI 大补丁一次提交曾因编码失败整体丢失。(7)PowerShell 里 `[IO.File]::ReadAllText("相对路径")` 按进程当前目录解析，不跟随 `cd`，必须用绝对路径；PowerShell here-string 替换多行文本因 CRLF/LF 不一致静默不生效，改用 Python 替换并 assert 命中次数；测试脚本结尾 `os._exit()` 不刷新重定向的 stdout，需先 `sys.stdout.flush()`；TextIOWrapper 包装 BytesIO 被回收时会关闭底层缓冲，需 `detach()`。

**关键文件与接口**: settings.json；config.toml；cc-switch.db；hooks.json；codex.CMD；hub.sqlite3；executors/codex/；FeishuClaudeBridge

**状态**: 已完成

### P-024: SIRE Git 归档应对 SQLite 快照做路径规范化与空闲页清理
**日期**: 2026-09-24
**项目**: SIRE v6
**关键词**: SIRE, Git 归档, SQLite 快照, 在线备份, 路径脱敏, FTS, embedding, VACUUM, snapshot_db.py, secure_delete, freelist

**需求场景 / 现象**: 当 SIRE 工作流与向量数据库需要进入 Git 仓库时，原始 SQLite 文件可能包含本机路径、邮箱/私网地址和过去更新留下的 freelist 页。直接复制虽可能 `integrity_check=ok`，仍会泄露旧值。

**方案 / 实施步骤**:
1. 用 SQLite backup API 在源库只读连接上生成一致副本。
2. 只在副本文本列中统一机器盘符与用户目录并清理邮箱/私网 IPv4。
3. 重建 `chunks_fts`、`kfts`、`cfts`，重算受影响的 legacy hashed vectors 与 v2 semantic embeddings。
4. 启用 `secure_delete` 后 `VACUUM`。
5. 扫描 SQLite 全部可见文本及整个文件字节，再确认 sidecar 不存在。
6. Git 快照保留业务行和表，排除 key/vault、个人配置快照、模型权重和 WAL/SHM。

**验证方法**: R7 逐项记录 SQLite 完整性与计数、FTS 查询、embedding 文本 hash 一致性、全文件凭据/路径/PII扫描、WAL/SHM 排除和 Git 实际跟踪/提交状态；源数据库另行备份，不被快照工具改写。

**踩坑 / 已知异常与失败经验**: 限制：匹配式隐私扫描只能识别常见凭据格式；清理的是机器标识而非语义知识。执行脚本需要本机可用的匹配 embedding 模型；如模型不可用会失败并保留原快照，不得跳过向量一致性校验。

**关键文件与接口**: sire/tools/snapshot_db.py；sire/data/sire_vectors.sqlite3；sire/data/snapshot-manifest.json；sire/workflow/shared/sire/scripts/sire_knowledge_index.py

**状态**: 已完成

### P-025: 运动页 <100Hz 使能时附加寄存器 (0x24/0x27/0x29/0x2A/0x2B) 示波器无曲线
**日期**: 2026-09-22
**项目**: driverSoftware (@CODE_ROOT@\driverSoftware, development, 未提交)
**关键词**: 附加寄存器, extras, 示波器, 100Hz, 软轮询, doSendMit, api.mit, flatExtras, TELEMETRY_DISPATCH, xNN, MitReq, _extras_with_state, getSelectedExtras

**需求场景 / 现象**: 运动页勾附加寄存器, 频率 ≥100Hz 有曲线, <100Hz 使能后这些曲线空白。

**方案 / 实施步骤**:
1. server.py `MitReq` 加可选 `extras`, 与 status 共用 `_extras_with_state()` (去重 + 保证 0xEB)。
2. motion.js doSendMit 带 `getSelectedExtras()`。
3. api.js 加 `flatExtras()` 把 extras 摊成 xNN 并入两个 dispatch。

**验证方法**: pytest 2126 passed; 真机可见 GUI: 50Hz 使能 → TX 帧含 `29 2A 2B 24 27 EB`, scope buf 5 路 675/675 非空; 未使能 50Hz、100Hz 使能 (回归)、10Hz 使能均有数据; 控制台无错误。（真机 id15 fw v3.4.6 @3Mbps）

**踩坑 / 已知异常与失败经验**: 根因 (两处叠加): (1)<100Hz 使能走 motion.js `doSendMit()` → `/api/cmd/mit`, 前端不带 extras, 后端 `api_mit` 也把 extra_regs 写死 [0xEB] —— 设备根本没被要求回这些寄存器; (2)软轮询回包进 scope 靠 api.js `TELEMETRY_DISPATCH` (/api/cmd/status、/api/cmd/mit), 只挑 pos/vel/tau/温度, 把 `parsed.extras` (数字地址 key) 全丢; scope 信号 key 是 "xNN" 大写 hex (硬件流 drain 路径才摊平成 xNN), 所以未使能 <100Hz 也同样空白。教训: 同一功能按频率分硬件流 / 软轮询两条路时, 新增字段要两条路都接, 且要同时核对"请求带没带"和"回包进 scope 时有没有被映射丢掉"两层。

**关键文件与接口**: server.py（MitReq、api_mit、_extras_with_state()）；motion.js（doSendMit、getSelectedExtras()）；api.js（TELEMETRY_DISPATCH、flatExtras()）；/api/cmd/mit；/api/cmd/status

**状态**: 已完成（真机验证通过，代码未提交）

### P-20260923: SIRE 向量库检索必须使用只读 SQLite 连接保护 Git 快照
**日期**: 2026-09-24
**项目**: SIRE v6 Claude/Codex 共享工作流
**关键词**: Claude, Codex, SIRE, SQLite, read-only, WAL, Git 快照, hash, knowledge retrieval, mode=ro, query_only

**需求场景 / 现象**: Claude 和 Codex 共用仓库中的同一份 SIRE 向量库。检索、统计或读取 chunk 属于只读操作，不应改变数据库主文件或让已提交快照与 manifest 的 SHA-256 失配。

**方案 / 实施步骤**:
1. `sire_vector_db.py` 的 `search`、`show`、`stats` 必须使用 SQLite `mode=ro` 并启用 `query_only`；不得通过检索入口创建表或切换 WAL。
2. `sire_knowledge_index.search()` 只检查当前 schema 并执行查询，升级 schema 留给 `index`/`migrate` 写路径。
3. 写入操作继续先生成可验证备份。

**验证方法**: 从 Codex 与 Claude 已安装入口分别运行 `stats` 和相同的向量检索，两边解析到同一仓库数据库、返回相同计数和命中 ID；正常检索、无命中查询及读取 chunk 后，隔离副本的数据库字节 hash 保持不变。

**踩坑 / 已知异常与失败经验**: 限制：`index`、`migrate` 和任务归档仍会更新 SQLite；提交前需要按 SIRE 快照流程刷新 manifest、检查 WAL/SHM，并重新执行完整性与隐私扫描。

**关键文件与接口**: sire/workflow/shared/sire/scripts/sire_vector_db.py；sire/workflow/shared/sire/scripts/sire_knowledge_index.py；sire/tools/snapshot_db.py；sire/data/snapshot-manifest.json

**状态**: 已完成

### P-20260924: Claude/Codex 共用的 SIRE 工作流与 SQLite 应在单一 Git 源中归档
**日期**: 2026-09-24
**项目**: SIRE v6 Claude/Codex 共享工作流
**关键词**: SIRE, Claude, Codex, shared workflow, 单一来源, Git, SQLite, WAL, writer lock, snapshot, database, sire_paths.py

**需求场景 / 现象**: 多个 AI 客户端必须使用相同的 SIRE 规则、角色定义、知识库和 SQLite 数据，且仓库克隆后能按仓库内文档重新建立客户端入口。客户端配置目录只保留指向仓库文件的薄适配器，不能再维护一套不同步的规则或数据库。

**方案 / 实施步骤**:
1. 把唯一共享工作流、通用知识和应用数据库放在同一仓库内，用 `sire_paths.py` 解析数据库路径。
2. Claude/Codex 入口通过符号链接或目录联接指向该源；环境变量覆盖须由同一映射文档定义并保持一致。
3. 每个数据库写入口（索引、迁移、RSI 等）写入前使用同一目标锁并按规则备份；`knowledge_record_count`、`task_record_count` 与 `keyword_count` 元数据应反映表内实际总行数。
4. 快照在源库只读连接上执行 SQLite 在线备份，以包含已提交 WAL，再脱敏、校验后原子发布数据库与 manifest。
5. 提交前确认 manifest hash 等于 Git 中 SQLite 文件的 SHA-256，且仓库内没有 WAL/SHM sidecar。

**验证方法**: 检查两个客户端入口解析到相同物理工作流和数据库；在有未 checkpoint 的已提交 WAL 行的临时库上验证快照包含该行且不改变源库；让 RSI 写进程与快照锁竞争并确认其等待；最后检查数据库完整性、业务行计数、FTS/embedding 一致性、隐私扫描、主库与 manifest 哈希及无 sidecar 状态。

**踩坑 / 已知异常与失败经验**: 仅将技能文件放入 Git 不够：客户端可能仍将路径解析到个人目录里的旧拷贝；只复制 SQLite 主文件也可能漏掉已提交 WAL 中的数据；并发索引、RSI 写入和快照发布可能互相覆盖；数据库 manifest 还可能与实际提交文件脱节。限制：真实 Claude/Codex 桌面 UI 只能在应用可被自动化访问时验收，CLI 成功不能代替 UI 验收；数据库写入脚本新增后必须纳入写入口审查，否则锁仍可能被绕过。

**关键文件与接口**: sire/workflow/shared/sire/；sire/workflow/shared/sire/scripts/sire_paths.py；sire/tools/snapshot_db.py；sire/data/sire_vectors.sqlite3；sire/data/snapshot-manifest.json

**状态**: 部分完成（已验证；当前任务的真实桌面 UI 验收因无可用 UI 应用而阻塞）

### P-20260925: SIRE 的 RSI 规则曾是孤岛——入口不可达且无触发点，需由 R9 收尾门禁兜底
**日期**: 2026-09-25
**项目**: SIRE v6 Claude/Codex 共享工作流
**关键词**: SIRE, RSI, 自我优化, self-optimization, sire_rsi, improvement_proposals, workflow_versions, 提案, 激活, 回滚, R9, rsi-check, finalize, rsi_unregistered_change, 工作流改动, 门禁, 关键词子串误报

**需求场景 / 现象**: 用户询问 SIRE 是否包含 RSI、RSI 如何触发。RSI（受控递归自我改进）要求工作流机制改动走"提案 → 基线指标 → 独立评估 → 版本化激活 → 观测 → 回滚"。

**方案 / 实施步骤**:
1. `SKILL.md` 新增 "Workflow changes (RSI)" 段并在 Supporting references 链接 `self-optimization.md`：改共享 skill 目录前先 `sire_rsi.py propose`，验证后 `evaluate`，只激活 `EVALUATED_PASS`，回归则 `rollback`。
2. `sire_supervisor.py` 新增只读 `rsi-check` 子命令并接入 `finalize`：共享 skill 目录有未提交改动（`git status --porcelain -- .`），且该目录最后一次提交（`git log -1 --format=%cI -- .`）之后没有 `PROPOSED`/`EVALUATED_PASS`/`ACTIVE` 提案时，返回 `STOP`、rc=3、`rsi_unregistered_change`，finalize 不推进 R9 基线。
3. 数据库以 `mode=ro` + `query_only` 打开，库/表缺失或非 SQLite 文件按"无提案"处理（fail-closed）；只有目录不存在或不在 Git 仓库时返回 `SKIPPED`，git 不可用或 status/log 失败返回 `STOP`（`rsi_git_undetermined`）；取不到最后提交时间时 `ACTIVE` 提案不算；finalize 把结果写入运行目录 `rsi-report.json`。
4. 本次改动自身按 RSI 走完：`RSI-20260925-R9GATE` propose → evaluate → activate v6.2（config-hash = 提交后工作流目录 git tree hash）。

**验证方法**: R4 拆解复核、R6A/R6B/R6C 独立复核与 R7 功能测试结论见 run R20260925-052105 的 evidence（U-01 qa/review）。正常路径：真实库有提案 → PASS；异常/边界：删提案、提案 EVALUATED_FAIL/ROLLED_BACK、提案早于最后提交、库不存在、无表空库 → STOP rc=3；只读：运行前后库 sha256 不变且无 -wal/-shm；finalize 在 STOP 时基线不变；verify-zip 回归通过。

**踩坑 / 已知异常与失败经验**: 原因：(1)`references/self-optimization.md` §5.1 与 `scripts/sire_rsi.py` 存在，但 `SKILL.md` 与 `global-contract.md` 均未链接该文件；(2)没有任何脚本、阶段、Hook（Claude settings.json / Codex hooks.json）调用 `sire_rsi.py`，RSI 只能手动触发，提案表只有 2026-09-21 的 2 条冒烟记录；(3)`sire_kb.py search` 按不区分大小写的子串匹配，检索 "RSI" 会误命中 "VERSION"/"supportedVersions"，RSI 相关知识需用向量检索或 `self-optimization`、`improvement_proposals` 等词。限制：门禁把"最后一次工作流提交之后的任一未失败提案"视为已登记，无法证明提案与具体 diff 对应，是兜底而非审计；其他会话在共享 skill 目录留下未提交改动时，任何 run 的 finalize 都会 STOP（预期行为）；`sire_rsi.py` 默认写仓库库 `sire/data/sire_vectors.sqlite3`，而收尾流程用 `snapshot_db.py` 从机器级归档库重建仓库库，只写进仓库库的 RSI 记录会在快照时丢失，RSI 写入必须同时（或只）写归档库后再快照；未修复：`sire_rsi.py status` 会先备份并 `CREATE TABLE`，不是只读；`evaluate` 只支持"越高越好"（after >= target）。

**关键文件与接口**: sire/workflow/shared/sire/SKILL.md；references/supervisor.md（检查项 8）；references/self-optimization.md §5.1；sire/workflow/shared/sire/scripts/sire_supervisor.py（rsi_gate / rsi_check / finalize）；sire/workflow/shared/sire/scripts/sire_rsi.py

**状态**: 已完成

### P-20260926: v3.4.6 寄存器文档对账与 0x6A/0x80 清理
**日期**: 原记录未记载
**项目**: driverSoftware（分支 chore/misc-optimizations，提交 b423f31、c140497，未 push）
**关键词**: v3.4.6, 寄存器梳理, 0x6A, AdcUsableAmp, GpioDebugPreGen, HOST_HIDDEN_REG_ADDRS, 0x80, InnerAngle, inner_zero, kStInnerAngle, 上位机隐藏, 固件档案

**需求场景 / 现象**: 以用户给定的《v3.4.6寄存器梳理》为准，核对 registers.py / server.py 隐藏清单 / 固件档案是否一致，并清理 0x6A、0x80 的遗留。

**方案 / 实施步骤**:
1. 文档与 firmware_profiles/v3.4.6.json 逐地址、名称、读写核对：除 0x6A 外全部一致。0x6A 文档写 GpioDebugPreGen「固件删掉」，档案里 v3.4.5+ 该地址是 AdcUsableAmp。
2. 文档所有「上位机隐藏」地址已全部在 server.py HOST_HIDDEN_REG_ADDRS 中；多出的只有 0x6A（继续隐藏，结果一致）。隐藏只影响寄存器页展示，不影响底层读写。
3. 0xEB ControllerState 文档标「上位机隐藏/删掉」，但档案里仍存在且 kt_worker/ota_utils/server 依赖，按「上位机隐藏」处理，不动底层读取。
4. 删除无引用的 kStAdcUsableAmp 常量，改注释说明 0x6A 历史；修正 0x7F GpioDebugAtFail 说明中「与 0x6A 对照」的失效引用。
5. inner_zero.py 的 REG_INNER/REG_POS_MECH/REG_STATE 由写死字面量改为引用 REG 常量。

**验证方法**: 寄存器/meta/隐藏清单/冷启动波特率相关单测 141 通过；inner_zero 相关单测 59 通过 2 跳过。

**踩坑 / 已知异常与失败经验**: 限制：未跑全量单测；未做真机可见 GUI 验收（改动仅常量引用与说明文字）。v3.4.7 比 v3.4.6 仅多 0x26 IqCmd，文档未覆盖，registers.py 已按 v3.4.7 处理。文档自身有小矛盾（0x81 默认值 100/105、0xE8 范围、0xE1 的 14、0x80 行列错位）未改文档。踩坑：查寄存器依据要先搜知识库 K-fw-v345-register-compat 与固件档案，曾因没查而误判 AdcUsableAmp「无依据」。注意："下一版固件换地址只改 registers.py"的假设后来被 P-20260927/P-20260928 证明不成立（见 0x80 按名字取址）。

**关键文件与接口**: core/registers.py；core/register_descriptions.py；core/inner_zero.py；server.py(HOST_HIDDEN_REG_ADDRS)；firmware_profiles/v3.4.6.json

**状态**: 已完成

### P-20260927: 设输出零位 (0x67) 不会让内圈零位 0x38 失效
**日期**: 2026-10-12
**项目**: driverSoftware (分支 chore/misc-optimizations 的 review)
**关键词**: 0x67, OutputZeroOffset, 设零位, set_output_zero, 0x38, MechZeroInner, 内圈零位, BootInferOuterMultiTurnFromInner, output_zero_offset_, _IZ_NEED_REGS, kStInnerAngle

**需求场景 / 现象**: review 时发现提交 c488ad5 在「⑨ 设当前位置为零位」成功后弹警告"输出零位变了, 之前测的内圈零位 (0x38) 不再适用, 请回到 ⑥ 重做"。

**方案 / 实施步骤**:
1. 搜固件仓 output_zero_offset_ 全部引用, 确认只出现在 multi_angle 计算与 SetCurrentPositionTo。
2. 读 BootInfer 实现确认输入只有 inner/outer 两个 q32 角。
3. 用固件仓最新提交 (f55b3f11, 2026-10-07) 复核一遍, 结论不变。
4. 判断"某个零位改了要不要重标 0x38"时, 看它进不进 BootInfer 的 phase = wrap180(outer_rep − inner_rep×gear): 0x37/0x38 进, 0x67/0x68 不进; 若要提示用户, 应该挂在 F2 改了 0x37 之后, 不挂在 ⑨。

**验证方法**: `git -C <firmware> show <rev>:Core/Src/encoder.cpp | grep -A18 "BootInferOuterMultiTurnFromInner"` 只见 inner_angle_q32_ / outer_angle_q32_。

**踩坑 / 已知异常与失败经验**: 根因: 依据不成立。固件 `Encoder::BootInferOuterMultiTurnFromInner` 只用 inner_angle_q32_ (内圈原始角 − 0x38) 和 outer_angle_q32_ (外圈原始角 − 0x37) 推多圈; output_zero_offset_ (0x67) 只在算 multi_angle_rad_ 时被减掉, 不进 BootInfer、不进相位曲线, 所以写 0x67 不会让 0x38 失效, 只有 0x37 (F2) 变化才会。固件 0x67 唯一有记录的副作用是 register_protocol.h 注释写"重设输出零点会平移 ψ 基准" —— 那是波发生器补偿 (0x3E/0x3F/0x6D), 不是 0x38。踩坑: 地址常量化重构 (c140497) 只改了 inner_zero.py, 漏了 server.py 的 `_IZ_NEED_REGS` 字面量 —— 寄存器重构必须符号名 + 字面量双搜 (军规 12); "下一版固件换地址只改 registers.py" 不成立: 单一常量改地址会让 v3.4.5~v3.4.7 设备失配, 跨版本地址应按 fw_profile.reg_addr(名字) 运行时取。附带风险 (未真机验证): ⑥ 自动模式进场把 RAM 0x38 清 0 且不写回, 之后点 ⑨ (内含 SaveConfig) 而不做 ⑦, flash 0x38 会被存成 0。

**关键文件与接口**: driver 仓 Core/Src/encoder.cpp（BootInferOuterMultiTurnFromInner / SetCurrentPositionTo）；server.py（api_set_output_zero、_IZ_NEED_REGS）；core/inner_zero.py（REG_INNER = REG.kStInnerAngle）

**状态**: 已完成（review 结论, 未改代码）

### P-20260928: 会跨固件搬家的寄存器按档案名字运行时取址 + 地址合理性校验 (内圈零位 InnerAngle)
**日期**: 2026-10-12
**项目**: driverSoftware (分支 chore/misc-optimizations, 提交 9640f3f..85901f3, 未 push)
**关键词**: InnerAngle, 0x80, fw_profile.reg_addr, 按名字取址, _iz_inner_addr, _IZ_INNER_ADDR_TAKEN, inner_addr, 内圈零位, timeout_s, NaN, 钳位, 寄存器换地址, 坏档案, 截低8位

**需求场景 / 现象**: 内圈零位自动模式要读 InnerAngle (v3.4.5~v3.4.7 在 0x80, 下一版固件要换地址)。原代码 server.py `_IZ_NEED_REGS` 写死 0x80, 档案里地址不是 0x80 就拒绝; 曾有注释称"换地址只改 registers.py", 实际改常量会让新旧固件只能顾一头。

**方案 / 实施步骤**:
1. 会搬家的寄存器 (InnerAngle) 运行时 `fw_profile.reg_addr(name)` 取址, 经参数显式传入采集函数 (`collect(inner_addr=...)` 必填、无默认值, 防静默退回旧地址); 不设模块常量。
2. 各版地址恒定且被多处直写的 (PosMech 0x16 / MechZeroInner 0x38) 只按 REG 常量核对名字, 不改运行时取址 (避免半套改造)。
3. 放宽门控 ("档案说在哪就读哪") 后补地址合理性校验: 非 int / bool / 越出 0~0xFF (发帧时 `a & 0xFF` 会把 0x116 截成 0x16, 静默读错) / 撞上本流程已占用的地址 (同帧捎带、同批读取、零位寄存器) 一律当"没有"。
4. 请求里的超时类参数要钳上限并拦 NaN: `timeout_s = min(300, t) if isfinite(t) else 300`。

**验证方法**: tests/unit/test_calib_inner_zero_endpoint.py (`test_inner_angle_moved_address_is_followed`、坏地址参数化、`test_timeout_is_capped_so_bad_frames_cannot_spin_forever`) 与 tests/unit/test_persist_zero_regs_reset.py (`test_residual_follows_moved_inner_angle`、`test_residual_not_read_when_inner_angle_addr_is_bogus`); 变异 M1~M5 各自只让目标用例变红。全量 tests/unit 约 2500 例 3~4 分钟。

**踩坑 / 已知异常与失败经验**: 根因: 跨固件版本会搬家的寄存器, 用模块常量表达不了"每台设备各自的地址"; 地址的权威是 active 档案 (fw_profile), 名字才是跨版本稳定键。`el > nan` 恒假, 配合"坏帧 continue 跳过卡住判据"会让电机一直转。踩坑: 改寄存器取址要同时搜符号名与字面量 (0x80 / 128 / "@0x80"), 注释和测试文件头里的旧说法也算残留 (三路复核都抓到过漏改的注释); 门控用例若用 0x38=0 的仿真电机, 门控排到"进场清 0x38"之后也看不出来 —— 用 0x38≠0 并断言拒绝时不写寄存器; 复核代理跑测试时主控不要改工作区, 否则测试结果被干扰; Git Bash 工具里 heredoc 会吞掉反斜杠, 含正则/JSON 转义的脚本用 Write 工具落盘再执行。已确认的相关风险 (未修, 另开单): ⑥ 自动模式进场把 RAM 0x38 清 0 不写回, 固件 SaveConfig 存整页 g_cfg, 之后点 ⑨ 设零位 (内含 SaveConfig) 而不做 ⑦ 会把 flash 0x38 存成 0; ramp_s 无上限且减速段从满速起减、不判超时。

**关键文件与接口**: server.py（_iz_inner_addr() / _IZ_INNER_ADDR_TAKEN / _IZ_FIXED_REGS、_IZ_NEED_REGS）；core/inner_zero.py `collect(c, gear, *, inner_addr, ...)`；tests/unit/test_calib_inner_zero_endpoint.py；tests/unit/test_persist_zero_regs_reset.py

**状态**: 已完成

### P-20260929: 数据区地址两表实测 bin 核对：MPP420 现表错、MPT420 productInfoList 错
**日期**: 2026-10-12
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01（分支 feature/mpp-algo-4060）
**关键词**: DATA_ADDRESS_LAYOUTS, productInfoList, resolveDataAddress, getIAPArguments, 数据区地址, angleData, polyfits, MPP420, MPT420, 0x08018000, 0x08015800, 0x08014800, LE32 字面量, 固件 bin 核对, load_app_data, kingkong 解密

**需求场景 / 现象**: 用户想把标定/IAP/恢复出厂用的数据区地址从 parse_iap_bin.DATA_ADDRESS_LAYOUTS 整体换回 sub_common/config.py 的 productInfoList。两表在 MPT 4.2.0、MPP 4.2.0 上地址互相矛盾，不知道哪个对。

**方案 / 实施步骤**:
1. 本机实际固件在 `C:\Users\Administrator\Downloads\bin\{DPB,DPT,MPP,MPT,...}`（含 .kingkong.bin 加密包）。
2. 脚本 `.sire/runs/R20261012-102955/evidence/compare_sources.py bins <bin...>`：load_app_data → parse_iap_bin_info → 两表查址 → `data.count(struct.pack('<I', addr))`。
3. `compare_sources.py tables` 逐版本列两表差异。
4. 用实际 bin 当真源判定：固件代码引用 Flash 数据区时，地址会以 32 位小端常量出现在字面量池里，统计候选地址出现次数即可判断哪个地址是该固件真用的。不整体切换；建议只修现表 105 的 420+ 行，MPP303 两个来源都未证实，需另找 .map。

**验证方法**: `PYTHONIOENCODING=utf-8 py -3.12 compare_sources.py bins <bins>`；MPP420 bin 中 0x08018000 出现 9 次、0x08015800 0 次；8 个 MPT420 bin 中 0x08015800 出现 8~9 次、0x08014800 0 次。结论：MPP420 → 0x08018000/0x08018800（productInfoList 对）；MPT420 → 0x08015800/0x08016000（现表对）；DPT/DPB 其余版本两表一致且命中。

**踩坑 / 已知异常与失败经验**: 根因：两份表都是人工维护的常量，没有任何代码去和固件比对。a26210c0（2026-10-10）把 MPP 105 的 420+ 行改成“按 MPT”0x08015800/0x08016000，与实际 MPP420 固件不符；productInfoList 的 MPT 420 仍是旧布局 0x08014800/0x08015000，与实际 MPT420 固件不符。另外 productInfoList 是精确版本 key，不覆盖 DPT 4.2.2/4.2.3/4.2.4、DPT_G1(109)；DPB 409 条目缺 inner.polyfits。踩坑：Windows 控制台 GBK 输出中文乱码，需 PYTHONIOENCODING=utf-8；DPT 4.2.x 的 inner 地址在 bin 中 0 次引用（可能改为外推），不能用“0 次”直接判错，单圈 outer 地址判定才可靠。

**关键文件与接口**: controller/python/parse_iap_bin.py:224（DATA_ADDRESS_LAYOUTS）、:267 resolveDataAddress、:592 load_app_data；controller/python/sub_common/config.py:88（productInfoList，326aed1 恢复）；controller/python/sub_algorithm/step4_GenerateV4020.py:827；调用点 parse_iap_bin.py:469（IAP）、Encoder.py:3484（恢复出厂）、Encoder.py:4621（标定）

**状态**: 已完成（分析结论；未改代码）

### P-20260930: MPP 数据区地址改查 sub_common productInfoList（PRODUCT_INFO_LIST_SERIES）
**日期**: 2026-10-12
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01（分支 feature/mpp-algo-4060）
**关键词**: MPP, 105, productInfoList, resolveDataAddress, PRODUCT_INFO_LIST_SERIES, _resolveFromProductInfoList, 数据区地址, 0x08018000, IAP 不支持, data_address_not_found, AngleDataPtr, c_uint32

**需求场景 / 现象**: MPP 4.2.0 的 IAP/标定用了“按 MPT”的数据区地址 0x08015800/0x08016000，实际 MPP420 固件引用的是 0x08018000/0x08018800。用户要求 MPP 改为读取 sub_common/config.py 的 productInfoList。

**方案 / 实施步骤**:
1. parse_iap_bin.py 新增 `PRODUCT_INFO_LIST_SERIES = (105,)`，resolveDataAddress 命中该系列时走 `_resolveFromProductInfoList`：懒导入 productInfoList，按 系列+int(版本) 精确取 key（与旧 getIAPArguments 同口径），逐层 isinstance 防御，返回副本；导入失败/查不到返回 None（不写错地址）。删除内联表 105 行。
2. 补单测；同步 AGENTS.md、docs/gotchas.md、components/share/iap.js 注释。

**验证方法**: `cd controller/python && py -3.12 -m pytest qa_api/tests -q`（125 passed）；`py -3.12 parse_iap_bin.py <mpp420 .kingkong.bin>` 输出 dataAddress 0x08018000/0x08018800、upgradeSupported=True；MPP 303 bin → upgradeSupported=False。

**踩坑 / 已知异常与失败经验**: 根因：a26210c0 把 DATA_ADDRESS_LAYOUTS 的 105 行改成 MPT 地址，没有拿实际 bin 核对。否决“整体切 productInfoList”：其 MPT 4.2.0 地址与实际 bin 不符，且缺 DPT 4.2.2+、DPT_G1。踩坑：productInfoList 精确 key 不覆盖新版本（MPP 4.2.1+ 需补条目，否则判不支持）；MPP 3.0.3 为空串，只影响 IAP（判不支持），3110 标定的地址取自设备 hallParam，不读 dataAddress（sub_algorithm/main.py 约 1296-1311），空串只在 IAP saveCalibrationData 赋给 ctypes c_uint32 时才会出错；sub_common 恢复 productInfoList 的 326aed1 只在 feature 分支，发布前须合入 sub_common main。

**关键文件与接口**: controller/python/parse_iap_bin.py（PRODUCT_INFO_LIST_SERIES、_resolveFromProductInfoList、resolveDataAddress）；controller/python/qa_api/tests/test_iap_arguments.py；调用点 parse_iap_bin_info、Encoder.py 恢复出厂/标定

**状态**: 部分完成（未提交；真机 MPP 验证 BLOCKED）

### P-20260931: SIRE RSI 自审：自动发现唯一 PROPOSED 发现来自兜底阶段与未分类任务，钩子单腿断流
**日期**: 2026-10-13
**项目**: SIRE v6 RSI 机制自我审查（`D:\sire\AI\AI\sire`）
**关键词**: SIRE, RSI, 自我审查, 自动发现, sire_telemetry, PHASE_OUTLIER, CLOSE_HEAVY, TOOL_RETRY, 误报, 遥测钩子, mode unknown, rsi-check, evaluate 方向性, resolve 无校验, v6.12, CATCH_ALL_PHASES

**需求场景 / 现象**: 用户要求按时间、流程、效率、输出、精准度五个维度自审 RSI 自我优化机制。实测数据：采样时刻遥测库 53 条任务 / 542 条事件，findings 表里唯一 PROPOSED 的 `PHASE_OUTLIER:execute` 两条证据都来自 `mode=unknown` 的任务（execute 123s/中位数 10s、539s/24s），建议文本"检查该阶段脚本或规则是否新增低效步骤"无法执行。

**方案 / 实施步骤**:
1. 新增模块常量 `CATCH_ALL_PHASES = ("execute", "reply")`。
2. `detect()` 的阶段离群循环跳过兜底桶和 `mode == "unknown"` 任务：`if mode == "unknown" or phase in CATCH_ALL_PHASES or value < 120: continue`，其余规则与阈值不动。
3. 本轮按"每个任务最多处理一条 pending"只修 `PHASE_OUTLIER`；第 2~6 条根因属独立机制改动，各自要单独立提案，未在本轮动。

**验证方法**: 用真实 `detect()` 重放 53 条历史任务：修复前 `PHASE_OUTLIER` 2 条（全 execute、全 unknown），修复后 0 条，`CLOSE_HEAVY=2`、`FAST_SCOPE=1` 与 findings 表一致。R7 隔离遥测库真实 `analyze`+`pending`：T1 full 任务 execute=600s（中位数 10s）与 unknown 同等任务均不再产生发现；T2 archive=300s 对中位数 20s 连中 2 次转 PROPOSED 并被 `pending` 列出。钩子自身开销实测每次事件约 0.10s、`analyze` 0.056s，不是瓶颈。rsi-check 由 STOP(`rsi_unregistered_change`) 转 PASS，pending 清空。

**踩坑 / 已知异常与失败经验**: 根因：(1)`classify()` 把没命中任何 `PHASE_PATTERNS` 的调用一律记成 `execute`、Stop 前的等待记成 `reply`，这两个兜底桶的量就是任务规模，`PHASE_OUTLIER` 却拿它跟跨任务中位数比，3 倍阈值必然被大任务触发；(2)`detect_mode()` 只认最终回复里的 `快速通道：简单任务` / `快速通道：否` 两处标记，飞书转发、automation、子代理回合没有标记，53 条里 27 条 `unknown`（51%），而规则写的是 `mode != "fast"`，把 unknown 当 full 算 `CLOSE_HEAVY`；(3)采集面单腿：`~/.codex/hooks.json` 三个事件都挂 `sire_telemetry.py hook`，`~/.claude/settings.json` 只有 Stop 和 UserPromptSubmit，没有 PostToolUse，claude 事件止于 10-12 10:50，Qoder `settings.json` 没有 hooks 键，`--client` 只允许 claude|codex；(4)阶段归属靠"先命中的正则"，一次 Bash 里串多条命令只记一个阶段，`ledger` 的 `[\\/]runs[\\/]` 会把 `.sire/runs/` 下的 Playwright 真实场景测试也算成台账；(5)`TOOL_RETRY` 名不符实：文档说"同一命令失败 3 次"，代码统计整任务失败数，`tool_failed()` 只认少数字段，421 条工具事件仅 2 条 `ok=0`；(6)`rsi_gate()` 允许状态含 `PROPOSED`，不校验提案是否覆盖本次 diff；`evaluate` 只有 `after >= target` 一种方向，本次第一次 evaluate 用 `after=3,target=100` 把自己判成 `EVALUATED_FAIL`，失败后 `improvement_metrics` 行无法删除；`sire_telemetry.py resolve --proposal` 完全不校验提案存在性与状态，实测对 `EVALUATED_FAIL` 提案照样把发现标成 FIXED。踩坑：① 用 SQL 直接往 `tasks` 造数据不会进入检测，只有 Stop 钩子里的 `summarize_task()` 会生成任务行，造场景必须走 `summarize_task`；② `evaluate` 的方向性陷阱会把提案打死，写指标先确认"越高越好"；③ `resolve` 在提案还没激活时就能执行，闭环顺序错了不会报错。限制：unknown 占比 51% 说明"每次回复首行标记"在跨客户端时并不可靠；遥测没有阶段声明，只有工具正则推断，各阶段耗时只能排序、不能当验收数值。生效性复核："观察→分析→判门禁"三段在 Codex 侧真实生效；"自动优化"目前是纯文字约定（`sire_run.py` 与 `sire_supervisor.py` 里没有任何 `sire_telemetry` 调用），Claude/Qoder 观察通道缺失，整体只算半生效；`D:/sire` 下 `rsi-report.json` 一个都没有，R9 finalize 从未真实落盘。

**关键文件与接口**: sire/workflow/shared/sire/scripts/sire_telemetry.py:42-46（CATCH_ALL_PHASES）；同文件 detect()、PHASE_PATTERNS、classify()、tool_failed()、detect_mode()；sire_supervisor.py:246,306 rsi_gate()；sire_rsi.py:37

**状态**: 部分完成（PHASE_OUTLIER 已修并验证；其余五条根因待另立提案，整体仅半生效）

### P-20260932: CLOSE_HEAVY/FAST_SCOPE 误报根因：阶段正则把真实场景测试与知识检索记成收尾，detail 截断使复核不可能
**日期**: 2026-10-13
**项目**: SIRE v6.14 遥测阶段归属收紧（`D:\sire\AI\AI\sire`）
**关键词**: SIRE, 遥测, sire_telemetry, PHASE_PATTERNS, classify, ledger, archive, CLOSE_HEAVY, FAST_SCOPE, 误报, .sire/runs, knowledge/global, detail 截断, RSI, v6.14

**需求场景 / 现象**: RSI 自动发现的 `CLOSE_HEAVY`（收尾占完整任务 40% 以上）累积到 3 次命中转为 PROPOSED，证据是 `收尾 94s/231s`、`155s/304s`、`419s/912s`；同时 `FAST_SCOPE`（快速通道越界）也在一次 10.7 秒的快任务上误报，唯一越界阶段仍是 ledger。

**方案 / 实施步骤**:
1. `ledger` 改为只认台账写入：`sire_run\.py|journal\.log|run\.json|units\.json|blockers\.md|assumptions\.md|kb-hits\.md|stage-output|\.sire[\\/]current`。
2. `archive` 去掉裸 `knowledge/global` 与 `archive[_-]?(db|root|result)`，只认动作：`sire_kb\.py (reindex|add|next-id|export-md|lint)|sire_vector_db\.py (index|migrate)|sire_db_backup|snapshot_db|SIRE_ARCHIVE_(ROOT|DB)`。
3. 读知识库改判 `retrieve`（在 retrieve 模式里加 `knowledge[\\/]global`）。
4. 事件 `detail` 上限 160→320，保证该规则可被复核（`cmd_hook()` 中 `redact(json.dumps(tool_input…), 320)`）。

**验证方法**: 用打补丁后的 `classify()` 重放 62 个历史任务（只读生产库）：`CLOSE_HEAVY` 命中 3→0、`FAST_SCOPE` 1→0，ledger 累计 1033s→716s、archive 368s→286s；full 任务收尾占比分布仍为 37/27/23/21/18/12%。R7 在隔离遥测库走真实 `hook → summarize_task → analyze`：`stage-output` 记 ledger、`.sire/runs` 下的 Playwright 夹具不再记 ledger、读 `knowledge/global` 记 retrieve、`sire_kb.py reindex` 仍记 archive，5 条断言全 PASS。`sire_qoder.py selftest` 回归 PASS，`pending` 清空，`rsi-check` PASS。

**踩坑 / 已知异常与失败经验**: 根因：`PHASE_PATTERNS` 两个模式匹配面过宽——`ledger` 把任何含 `.sire/runs/` 路径的命令都算写台账（R7 的夹具与 Playwright 脚本恰好放在 run 目录下）；`archive` 里含裸 `knowledge[\\/]+global`，读 `knowledge/global/KNOWLEDGE_TEMPLATE.md` 被记成归档收尾；钩子把事件 `detail` 截断到 160 字，现存 161 条 ledger/archive 事件里 145 条已是不可解析的半截 JSON；一次 Bash 里串多条命令只归一个阶段。踩坑：① 写 A/B 度量脚本时不要用 `needle in line` 匹配客户端日志，本端 `sire-telemetry` 字样会先被模型自己写进代码文本里导致假阳性；② 造遥测场景必须走 `summarize_task()`，直接往 `tasks` 插行不参与 `analyze`；③ 断言里截断 `detail[:60]` 会把文件名切掉而误判 FAIL；④ `evaluate` 的指标只认"越高越好"，写 `after<target` 会把提案打死。限制：阶段归属仍是"从工具文本猜"，不是角色声明；收紧后 CLOSE_HEAVY 在现存数据里 0 命中，若将来真实收尾开销变大，该规则仍会按 40% 阈值报出。

**关键文件与接口**: sire/workflow/shared/sire/scripts/sire_telemetry.py:31-41（PHASE_PATTERNS 的 retrieve/archive/ledger）；cmd_hook()；sire/.sire/runs/R20261013-074759/evidence/measure_phaseclass.py；r7_phase_test.py + r7_phase_result.json

**状态**: 已完成

### P-20260933: DPB 407/408 到 409 的 IAP 升级白名单
**日期**: 2026-10-13
**项目**: EncoderPlotter_0903_01 / feature/compatibility
**关键词**: DPB 407, DPB 408, DPB 409, supportedVersions, IAP upgrade matrix, sub_common, dpbFlashLayout, sub_embedded

**需求场景 / 现象**: DPB 409 固件布局已登记，但 DPB 当前固件 407/408 的 IAP 允许版本列表没有 409，因此升级门禁拒绝该升级路径。

**方案 / 实施步骤**:
1. 更新 DPB 407/408 的 `supportedVersions` 为 `[407, 408, 409]`（在同名兼容分支 `feature/compatibility`），保持 DPB 409 自身列表为 `[409]`。
2. 通过 IAP API 假设备路径验证 407 和 408 均下发目标 409，保留已有跨系列和不支持版本拒绝测试。
3. 先提交 sub_common，再更新 root gitlink 并同主仓 QA/changelog 一起提交。

**验证方法**: `py -3.12 -m pytest qa_api/tests`（122 passed）；嵌入式/再标定/v4060 回归（42 passed）；独立审查确认 DPB 409 flashLayout 与 dpbFlashLayout helper 地址、容量一致。测试只验证软件版本门禁和模拟路径，不等同真实设备刷写。

**踩坑 / 已知异常与失败经验**: 根因：`sub_common/config.py` 中 DPB 407、408 的 `supportedVersions` 只包含 `[407, 408]`；IAP 依据当前固件配置列表决定是否允许目标版本。Pytest `-k` 匹配节点名；初次筛选关键字错误导致 0 selected，按实际测试名调整后 2 passed。软件配置和模拟 API 无法证明设备 bootloader 兼容，升级前仍需在 DPB 407/408 实机验证。

**关键文件与接口**: controller/python/sub_common/config.py（DPB productInfoList）；controller/python/qa_api/tests/test_routes.py（test_iap_allows_dpb_407_and_408_to_upgrade_to_409）；CHANGELOG.md

**状态**: 部分完成（代码与软件回归完成；物理设备升级验证待进行）

### P-20260934: 遥测采集看着正常但分析层空转：summarize_task 硬依赖 UserPromptSubmit，自动化/续跑回合没有 prompt 事件就整窗丢弃
**日期**: 2026-10-13
**项目**: SIRE v6.16 遥测回合边界兜底（`D:\sire\AI\AI\sire`）
**关键词**: 遥测, summarize_task, UserPromptSubmit, Stop, 回合边界, prompt 事件缺失, 目标续跑, automation, Qoder, CLOSE_HEAVY 失效, v6.16

**需求场景 / 现象**: Qoder 端接入钩子后事件在涨（119 条），但 `tasks` 表只有 1 条且不是本会话的：本会话 117 条事件里有 3 个 `stop`、却只有 0 个 `prompt` 事件（全库 `prompt` 仅 1 条）。本端所有回合都进不了 `analyze`，`CLOSE_HEAVY`/`PHASE_OUTLIER`/`FAST_SLOW` 这些按回合判定的规则对这一端完全失效——表面上“心跳正常”，实际上分析层空转。

**方案 / 实施步骤**:
1. 回合边界改以 `Stop` 为准，`UserPromptSubmit` 降为可选起点。
2. 无 prompt 事件时取窗口内最早的非 prompt 事件作为起点、`prompt` 字段留空，`mode` 仍由 Stop 读最终回复判定；有 prompt 时行为完全不变（零回归）。
3. 契约 §静默分析同步写明这条口径，防止以后再把它当硬前提。

**验证方法**: 从生产库导出本端全部事件灌进隔离遥测库（`SIRE_TELEMETRY_DB`）重放真实 `summarize_task()`：2 个会话 4 个 stop → 修复前 0 个任务，修复后 4 个任务，且阶段分布合理，例如某回合 `总1519s / 工具40 / 失败3`。`ast` 语法校验通过，`rsi-check` PASS，`sire_qoder.py parity` rc=0。

**踩坑 / 已知异常与失败经验**: 根因：`summarize_task()` 把 UserPromptSubmit 当成回合起点硬依赖（`if not prompts: return` 整窗丢弃），而自动化/续跑型提示（目标系统注入的 continue、飞书转发、定时任务）不触发 `UserPromptSubmit` 钩子，只有 `Stop`。踩坑：① 验证“是否真的在采集”不能只看 events 数量，必须看 `tasks` 是否在增长；② 重放验证要用生产真实事件灌隔离库，别手造数据；③ 第一版验证脚本把事件按原 session 插入、却用另一个 session id 调 `summarize_task`，得到 0 任务是测试写错而非代码错——先怀疑量具再怀疑被测物。限制：兜底起点的 `prompt` 字段为空；没有快速通道标记的自动化回合 `mode` 仍是 `unknown`。

**关键文件与接口**: sire/workflow/shared/sire/scripts/sire_telemetry.py（summarize_task()）；sire/workflow/shared/sire/references/global-contract.md（§RSI 自动发现 第 2 条）

**状态**: 已完成

### P-20260935: SIRE 三端兼容实测：Codex/Claude 入口副本对 v6.12-v6.17 的关键词覆盖 0/7，且无机制能发现这种漂移
**日期**: 2026-10-13
**项目**: SIRE 三端兼容性复核（`D:\sire\AI\AI\sire`）
**关键词**: SIRE, 三端兼容, Codex, Claude, Qoder, 入口副本漂移, AGENTS.md, sire-reminder.txt, memory, hooks.json, config.toml 信任哈希, 别名 junction, COLLECTION_DEAD, parity, 链式钩子, feishu-hub

**需求场景 / 现象**: 要判断“Codex 与 Claude 是否仍与唯一源兼容”。实测关键词覆盖：唯一源 `global-contract.md` 命中 `Qoder / pending / COLLECTION_DEAD / sire_close / sire_qoder / 强制 / parity` 7/7；`~/.codex/AGENTS.md`（3033 字节）0/7；`~/.claude/sire-reminder.txt`（2587 字节）0/7；`~/.qoder-cn/memory/sire-mandatory-workflow.md` 4/7。v6.12–v6.17 的改动另两个客户端的入口副本一字未提，且没有任何机制能发现这种漂移。

**方案 / 实施步骤**:
1. 入口副本改为同源生成 + 指纹校验：新增 `scripts/sire_entry.py`，`render --client codex|claude|qoder` 从 `global-contract.md` 生成固定小节（含源 SHA 前 12 位与“由脚本生成，勿手改”标记），`check` 比对三端指纹并把不一致变成一条发现；先做这一步。
2. Claude 采集用链式而非抢占：在 feishu-hub 的 `hook_prompt.py` / `hook_stop.py` 内追加调用 `sire_telemetry.py hook --client claude`；Codex 侧改 `hooks.json` 后必须提醒重新信任。
3. 钩子命令不再指向别名：统一指向唯一源真实路径（或由 `sire_paths.py` 生成的启动器），`check` 同时验证“别名解析 == 唯一源”“脚本文件存在”“近 N 小时有心跳”。
4. 显式客户端清单：`sire_clients.json` 声明应当接入的客户端与必备事件，缺失=发现（`CLIENT_NOT_INSTALLED`）。
5. 分档文本同源：把 low/mid/high 的委派约束也收进唯一源生成，Claude 用它生成 `agents/sire-*.md`、Qoder 用 `sire_qoder.py role` 消费，Codex 待验证后接入。

**验证方法**: `scratch/probe_three_clients.py`（输出 `three_clients.json`）逐端打印别名解析、钩子事件与命令、脚本是否存在、副本关键词覆盖；漂移比对用 `section()`+`sha256[:12]`，副本无该段即判“不可比对”，本身就是要修的缺陷。

**踩坑 / 已知异常与失败经验**: 根因：1) 入口副本制度是“摘要 + 人工同步”，没有任何命令校验。2) 采集面三端不齐：Claude 的 Stop 与 UserPromptSubmit 都被 feishu-hub 占用，对 `sire_telemetry` 的引用是 0；Qoder 同事件多条目后曾出现停采，链式更稳。3) 别名即单点：Codex 钩子命令硬编码别名目录路径，junction 失效采集会静默断掉；Codex 另有 `config.toml` 的 3 条 `[hooks.state...]` 信任哈希——改 hooks.json 需重新信任，否则钩子不生效且无提示。4) Qoder 没有子代理定义也没有 `model` 参数。5) `COLLECTION_DEAD` 从配置反推“应采集客户端”，未配置的客户端隐形。限制：本次只读复核，`sire_entry.py`、Claude 链式钩子、`sire_clients.json` 均需各自走 RSI 提案，Claude 那项还要用户授权；`plugin:computer-use` 现已在 Qoder 暴露并实测可用，此前记录的“R10 本端不支持”已失效，需更正 README 与契约。

**关键文件与接口**: ~/.codex/AGENTS.md、~/.codex/hooks.json、~/.codex/config.toml；~/.claude/sire-reminder.txt、~/.claude/settings.json（Stop/UserPromptSubmit → D:\sire\AI\AI\feishu-hub\executors\claude\hook_*.py）、~/.claude/agents/sire-*.md；~/.qoder-cn/settings.json、~/.qoder-cn/memory/sire-mandatory-workflow.md、sire/workflow/shared/sire/agents/qoder/README.md

**状态**: 部分完成（只读复核与建议，机制改动未实施）

### P-20260936: DPB MR复审：导入写入校验与packed版本转换
**日期**: 2026-10-13
**项目**: 原记录未记载（DPB 的 embedded/common 两个子仓 MR 复审）
**关键词**: GitLab MR review, DPB 408 409, imported calibration, writeEncoderDataV303, eraseAndWriteFlash, firmware_number, packed 4.0.10, 4010, Flash preflight, writeEncoderData, dpbFlashLayout.py

**需求场景 / 现象**: GitLab MR 重复复审 DPB 导入标定写入：embedded HEAD 4ad0fe3d997c70f8365a64a5fa82d875bfa002c9；common HEAD f8825057831178e41502077789b8b45e651c63de。沿更多调用路径复查后更正此前的肯定结论。

**方案 / 实施步骤**:
1. 沿 EncoderCommandCalibrationWriteData → writeEncoderDataV303 → writeFlash / eraseAndWriteFlash 的所有调用路径复查容量校验是否覆盖。
2. 用 runpy 执行 dpbFlashLayout.py 确认 firmware_number(0x04000A00)=410 与 firmware_number(4010)=4010。
3. 在 GitLab 已登录浏览器读取既有评论，并在两个 MR 发表公开更正评论；不 Approve、不 merge。

**验证方法**: runpy 执行 dpbFlashLayout.py 确认 firmware_number(0x04000A00)=410 且 firmware_number(4010)=4010；GitLab Activity 计数由 1 变 2，并核对完整发布文本。真实硬件未测试，未改代码。

**踩坑 / 已知异常与失败经验**: P1 embedded：新增的 DPB 容量检查只在 writeEncoderData；parent Encoder.py 中的 EncoderCommandCalibrationWriteData 调 writeEncoderDataV303，其导入的 current/generated Q/T 分支直接调 writeFlash 和 eraseAndWriteFlash，后者先擦除再写且没有容量检查，超大导入 T 会直接走到擦除而不是预检拒绝；建议在任何擦除前检查所有选中缓冲区，跨版本 DPB408/409 导入 T 是具体触发条件（固件侧是否拦截及物理后果未测试）。P2 common：项目三段拼接要求 4010，而 firmware_number 折成 410；当前 408/409 不受影响，建议匹配 packed/UI 转换并补测试。跨仓依赖：新的顶层 import 要求 common/embedded pin 协同、common 先合并。

**关键文件与接口**: sub_embedded 的 writeEncoderData / writeEncoderDataV303 / writeFlash / eraseAndWriteFlash；parent Encoder.py（EncoderCommandCalibrationWriteData）；sub_common/dpbFlashLayout.py（firmware_number）

**状态**: 已完成（复审结论已发布；问题由 P-20260937 修复）

### P-20260937: DPB导入数据擦除前预检与packed版本修复
**日期**: 原记录未记载
**项目**: 原记录未记载（DPB 的 embedded/common 子仓，feature/compatibility 分支，MR30/MR31）
**关键词**: DPB Flash preflight, writeEncoderDataV303, imported P Q T, firmware_number, packed 4010, MR30 MR31, regression, eraseAndWriteFlash

**需求场景 / 现象**: 用户授权修复此前 MR 复审发现（见 P-20260936）并更新现有 MR；DPB 导入数据在擦除前缺容量预检，packed 版本折位错误。

**方案 / 实施步骤**:
1. 使用现有干净的 feature/compatibility 分支，子仓合并前不提交父仓 pin。
2. common 提交 3b3fa720178e7f859786b4c78610fa0747d6bdb5：用三分量十进制拼接替换算术 packed 版本转换。
3. embedded 提交 f3b3a599e6914824a759127cd35b00cd1ee0733c：在任何设备操作前检查所有导入的 P/Q/T 缓冲区，并在直接 writeFlash 之前检查；缺缓冲区则在操作前拒绝。
4. 补参数化边界与溢出回归测试；两个提交推送到现有 feature 分支。

**验证方法**: `py -3.12 -m pytest sub_embedded/tests qa_api/tests sub_algorithm/tests/test_v4060_runtime_config.py -q`：181 passed, 7 subtests passed, one existing Starlette/httpx deprecation warning。子仓 git diff --check 通过。溢出测试验证无 ensure/stop/write 调用，直接写测试验证无 eraseAndWriteFlash 调用；边界 DPB408/409 写入通过。GitLab Activity 显示新增提交与修复评论，Overview 计数升至 3。

**踩坑 / 已知异常与失败经验**: 硬件未连接也未刷写，硬件验收仍未验证。不执行 approve 或 merge。父仓 checkout 的 gitlink 现显示子提交，但按仓库策略在子仓合并前刻意不提交。复核：实际写路径共用预检保护；current 与 generated 缓冲区都在写 PARAMS 前检查；既有常规标定预检保留；DPB4060 守卫不影响其他系列/算法行为。

**关键文件与接口**: sub_embedded 的 writeEncoderDataV303 / writeFlash / eraseAndWriteFlash；sub_common 的 firmware_number；sub_embedded/tests、qa_api/tests、sub_algorithm/tests/test_v4060_runtime_config.py

**状态**: 已完成

### P-20260938: 飞书卡片队列被单条非法卡片头阻塞；Qoder 钩子两条隐蔽失效点
**日期**: 2026-10-13
**项目**: 全局工具 / D:\sire\AI\AI\feishu-hub
**关键词**: 飞书卡片, outbox 头阻塞, HTTP Error 400 Bad Request, head-of-line blocking, blocked 保序键, status DEAD, UnicodeEncodeError surrogates not allowed, sys.stdin.buffer, GBK 控制台, hook_event_name, settings.json hooks 不生效, qoderclicn headless, FEISHU_HUB_TASK_ID, local image markdown

**需求场景 / 现象**: 1) `~/.feishu_hub/hub.log` 持续刷 `WARNING [出口] 发送失败 outbox=455 第642次: HTTP Error 400: Bad Request`，同一 `session_id` 后面积压 25 条 `PENDING` 且 `attempts=0`，出站队列对一个会话整体失联 15 天。2) Qoder 桌面轮次结束后飞书没有卡片：`settings.json` 已加 Stop 条目但整场会话不执行；改到新会话又报 `Hook 输入不是有效 JSON`，实际异常是 `UnicodeEncodeError: 'utf-8' codec can't encode character '\udcaa'`。

**方案 / 实施步骤**:
1. 先证伪“钩子没装”：查遥测库同事件有无 `stop` 行——有 stop 但无卡片，说明事件触发了、是第二条钩子没跑或跑了失败。
2. 队列侧：加 DEAD 终态 → 400 直接作废且不阻塞同组 → 修 unsent 统计口径（`outbox_unsent_for_task()` 改为 `status NOT IN ('SENT','DEAD')`）。
3. 构造侧：`compact()` 里 `_plain_local_images()` 把非 http 图链降级成「（图片：路径）」。
4. 钩子侧：统一 `sys.stdin.buffer.read().decode("utf-8", "replace")`；JSON 解析与上报分路 try；traceback 落盘 `~/.feishu_hub/hook_qoder.log`。
5. 用 headless 会话验证整链，不必等真机桌面轮次。
核心代码：service._send_row 异常分支 `if getattr(e, "code", 0) == 400: store.outbox_dead(r["id"], str(e)) ... return True`（不进 blocked，同会话后续继续发）；feishu.py `_LOCAL_IMG = re.compile(r"!\[[^\]]*\]\(\s*(?!https?:)([^)]*)\)")`。

**验证方法**: `python tests/test_hub.py` → 82 项，新增 3 项 PASS（余 2 项失败为既有）。重启 `FeishuHub` 计划任务后查库：455 变 `DEAD`，被压 25 条全部 `SENT`，`PENDING=0`。钩子链路：`qoderclicn -p --output-format json "只回复四个字：钩子自检"`，环境剔 `QODER_AGENT_SDK*` 前缀、故意不带 `FEISHU_HUB_TASK_ID`（带上即走抑制分支），跑完看 `hook_qoder.log` 出现 `verdict=sent`，`outbox` 新增 `executor=qoder`、`task_id=''` 的 SENT 卡片。脚本 `scratch/probe_stop_hook.py`。

**踩坑 / 已知异常与失败经验**: 根因：1) 卡片 markdown 含本地图片 `![阿砾步行](/D:/code/GAME/.../CHR_Hunter_Walk.png)`，飞书卡片只接受 http(s) 图链，整卡 400——永久性错误；队列层放大：`service.flush_outbox()` 按 id 顺序发送，以 `reply_to or session_id` 为保序键，一条失败就把该键加入 `blocked`。2) Qoder 客户端在会话 `initialize` 时把每组 hooks 一次性交给 agent runtime，运行中改 `hooks` 对当前会话无效；钩子用 `sys.stdin.read()` 在 GBK 控制台解出孤立代理项，随后 `.encode("utf-8")` 抛异常，客户端吞掉 stderr。被否决方案：“重试 N 次后放弃”——按 300s 上限算，一条毒卡片要占 1.5 小时才放行同组后续。踩坑：把 `UnicodeEncodeError` 误标成“输入不是有效 JSON”，因为 JSON 解析和上报共用一个 `except ValueError`（`HubError` 也继承它）；曾据“装完遥测钩子下个提示词就生效”断言钩子热加载，结论作废（同一会话新加的 Stop 条目整场不跑、新会话立刻跑）；判定“卡片没发”不能只看异常返回，必须自带落盘 verdict；`desktop_queue` 能力位对 Qoder 恒 False，别照抄 Codex 的 True。

**关键文件与接口**: feishu-hub/hub/store.py（outbox_dead、outbox_unsent_for_task）；feishu-hub/hub/service.py:73 _send_row()、flush_outbox() blocked；feishu-hub/hub/feishu.py（_LOCAL_IMG、_plain_local_images、compact）；feishu-hub/executors/qoder/hook_stop.py（main、LOG_HOME）；feishu-hub/tests/test_hub.py；~/.qoder-cn/settings.json 的 hooks.Stop（遥测 + feishu-hub 两条并存）

**状态**: 已完成

### P-20260939: DPB 4.0.10 版本码 4010：patch 两位数让码值不可比，比较必须走三元组
**日期**: 2026-10-14
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01（分支 feature/iap-ota-sn）
**关键词**: DPB 4.0.10, 4010, 410, 版本码, DATA_ADDRESS_LAYOUTS, parse_iap_bin, tryDpb, dpbFlashLayout, firmware_number, iap_sn_restore, MIN_SOFTWARE_VERSION_FOR_SN, NUM_TO_HEX, 0x04000A00, 补丁号两位数, 未找到有效ARGUMENTS结构

**需求场景 / 现象**: 固件组交付 DPB V4.0.10 的 BIN 解析规则（`Arguments.version.software = 0x04000A00`），要求上位机支持。改动前用真实产物跑 `parse_iap_bin.py` 直接失败：`[IAP] bin解析失败：未找到有效ARGUMENTS结构 size=264392`，前端表现为"bin文件解析失败，请更换有效的固件文件"。

**方案 / 实施步骤**:
1. 先用真实固件产物复现失败，再动代码（Downloads 下 DPB10/15/20/25/30 的 `.kingkong.bin` 与一份明文 bin）。
2. 落 Python/JS 两份同口径的三元组解析，门禁全改三元组比较：码值继续用拼接形式（4.0.10=4010），比较一律先解成 (major, minor, patch) 三元组，规则为"第一位 major、第二位 minor、其余整体 patch"，要求 major/minor ≤ 9；Python 侧新增 `controller/python/firmware_version.py`（`version_triple` / `version_at_least`），前端同源一份 `shared/firmware_version.js`，`analyzer.js`、`device.js` 删掉各自的解析副本改引用它。
3. 补白名单与显示串：`parse_iap_bin` 白名单补 `0x04000A00: 4010`，显示串改由打包字节生成；`DATA_ADDRESS_LAYOUTS[106]` 的 `(408, 9999)` 行天然罩住 4010，只补注释不改表。
4. 子仓改 `firmware_number`（子先父后，两层提交）为拼接规则；`LAYOUTS[4010]` 预算与 409 相同（T 170KiB / Q 2048 / P 0x08040000 30KiB）。
5. 规则文档入库 `docs/iap-bin-rules/`，`docs/README.md` 加索引行。
6. 核心代码：
```python
def _from_code(code):
    text = str(code)
    if code <= 0 or len(text) < 3 or not text.isdigit():
        return None
    return int(text[0]), int(text[1]), int(text[2:])   # 4010 -> (4, 0, 10)

def version_at_least(value, minimum):
    actual, threshold = version_triple(value), version_triple(minimum)
    if actual is None or threshold is None:
        return False
    return actual >= threshold
```

**验证方法**: `cd controller/python && py -3.12 -m pytest qa_api/tests`（138→140 passed，含 `qa_api/tests/test_dpb_v4010_bin.py` 13 条：七种形态同解、4010<422、合成 0x39010 镜像识别为 4010/"4.0.10"、DPB 预算命中、4.0.9 不回归）；`py -3.12 -m pytest sub_embedded/tests`（39 passed）、`sub_algorithm/tests/test_dpb_flash_layout.py`（6 passed，`get_layout(410)` 仍必须抛错）；`node --check` + 19 条断言跑 `shared/firmware_version.js`；真产物 8 个文件全部 `status=ok`，BIN 长度与 `polyfitDataSize` 对上文档 §0/§4.3（DPB25：274760B、T=160424、T 结束 0x0802C2A8）。

**踩坑 / 已知异常与失败经验**: 根因：项目的版本码是十进制拼接 `int(f"{major}{minor}{patch}")`，默认每个分量一位十进制数字，patch 到 10 之后前提崩了：(1)`parse_iap_bin.tryDpb` 的 DPB 白名单只到 `0x04000900: 409`，判别器返回 None；(2)码值不再单调：4010（4.0.10）数值上大于 422（4.2.2），所有 `>= 422` 式门禁（IAP 后 SN 写回、0x83 指令读 SN 能力）会把 DPB 4.0.10 判成比 4.2.2 新；(3)显示串按三位拆 `f'{v//100}.{v//10%10}.{v%10}'` 把 4010 显示成 "40.1.0"；(4)`sub_common/dpbFlashLayout.firmware_number` 用 `*100/*10` 折位，把 0x04000A00 折成 410，查不到 `LAYOUTS[4010]`，Flash 预算校验整段跳过；(5)前端两处解析副本口径不一样：`analyzer.js` 把紧凑码拆成 `[首位, 中间, 末位]`，`device.js` 直接比码值。否决方案：全局重编码（把码值换成 `major*10000+minor*100+patch`），会牵动 config.py 表键、子仓 sub_algorithm 的算法侧码值与前端，存量承担不起。踩坑：文档自身也可能错——单文件版 V410 规则把 `0x82` 写成 31 字节负载差异，合并版更正为两版本都 59 字节（`build_info.py` 本来就兼容），以"最新合并版"为准；`version_triple` 若对非 str/int 对象走 `str(value)` 兜底，`object()` 的 repr 里含长数字串会被当成版本号误命中，必须限定只对 str 做文本解析；未登记预算的 DPB 版本（407）走无守卫的 `get_layout` 会抛 ValueError 打断写入，合并时这类"顺手去掉守卫"的改动要保留守卫分支。

**关键文件与接口**: controller/python/firmware_version.py；controller/python/parse_iap_bin.py:395（tryDpb 白名单）、:424（显示串）；controller/python/iap_sn_restore.py:12；controller/python/Encoder.py:4240；shared/firmware_version.js；components/analyzer/analyzer.js:427；components/encoder/device.js:3251；controller/python/sub_common/dpbFlashLayout.py:13（firmware_number）

**状态**: 已完成（代码 + 真 bin 离线实测 + 自动化回归；接读取器的在线路径未验证——本机无设备）

### P-20260940: develop 与在途功能同改一条链的合并：预演、子仓 gitlink 双向核对、静默损坏检测
**日期**: 2026-10-14
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01（feature/iap-ota-sn ← origin/develop）
**关键词**: 合并冲突, git merge-tree, 子模块 gitlink, merge-base --is-ancestor, 语义冲突, back-merge-check, EncoderBase.py, device.js, CHANGELOG, 静默损坏, 双侧同改, sub_common, sub_embedded

**需求场景 / 现象**: 用户要求"将 origin/develop 合并到当前分支，包括子仓库，当前仓库的代码为基础，整合进 origin/develop 的代码"。本分支领先 145 提交、落后 8 提交，两侧都改了 `dpbFlashLayout.firmware_number`、`EncoderBase.py`、`config.py`、`device.js`、`CHANGELOG.md`。危险的不是 git 报的 4 处冲突，而是：子仓两侧各自前移只看到一个 gitlink 冲突；双侧用不同写法实现同一修复（f-string 拼接 vs `"".join(...)`）；冲突块外的共同尾部行属于一侧的结构改造。

**方案 / 实施步骤**:
1. `git fetch origin` + 各子仓 `git fetch origin`（主仓 fetch 不带子仓对象，子仓不 fetch 就查不到 develop 侧提交）。
2. `git merge-tree --write-tree --name-only HEAD origin/develop` 预演（不改工作区，一次拿到冲突清单，含 submodule 类型冲突）。
3. 两侧 `git diff --name-only <base>` 求交集，逐文件判断是文本冲突还是语义重叠（别用 `comm`，用 grep 白名单）。
4. 工作树必须干净才合：在途功能按用户批准先提一个 commit（含子仓 gitlink），CHANGELOG 条目留到合并冲突里一并解决。
5. 子仓合并：先确认本地同名分支是记录提交 `89ea339` 的祖先再 `--ff-only` 对齐（不是祖先就不动它），然后 `git merge <develop 侧提交>`，解完在子仓提交，回主仓 `git add <子模块路径>` 记 gitlink。
6. 在途改动提交 → `git merge --no-ff origin/develop` → 进子仓解内容冲突并提交 → 回主仓 `git add` 子模块路径与文本冲突 → 提交。
7. 复核：`git diff HEAD^1 -- <冲突过的文件>`、`git -C <子仓> diff <合并前提交> HEAD --stat` 加 `grep "^-"`，确认我们侧没有行被吃掉。
8. 取舍口径：函数实现两侧等价时采 develop 的写法；行为相关的一侧更完整时（`writeFlash` 的进度/重试签名、未登记版本跳过校验的守卫）保留本分支，并在 merge message 里写明为什么。

**验证方法**: 合并后 CI 五组 + 主仓四组 unittest 全绿（`qa_api/tests` 140 passed、`sub_embedded/tests` 39、`test_v4060_runtime_config.py` 32、`test_dpb_flash_layout.py` 6）；`git diff HEAD` 在暂存前逐个冲突文件复核净变化只含预期项；真产物 8 个 DPB 4.0.9/4.0.10 bin 复跑 `parse_iap_bin.py` 全部 `status=ok`。闭环核对：`git log HEAD..origin/develop` 为空 且两个子仓 `merge-base --is-ancestor <develop 侧提交> HEAD` 与 `--is-ancestor <我们侧提交> HEAD` 都成立。

**踩坑 / 已知异常与失败经验**: - 共同触碰面用两侧交集算时别用 `comm`：git-bash 下 `sort` 与 git 的排序口径不一致，实测把 7 个真实重叠文件漏成 0 个，改用 grep 白名单才对。
- 用脚本批量剥冲突标记时，"冲突块之后的共享尾部"可能是另一侧的代码——本次带进 4 行 `this.$store.commit(..., string: text)`，`text` 在本分支作用域里不存在，语法检查照过，靠 `git diff HEAD` 才发现。
- develop 新增的测试是给 develop 的调用管线写的：本分支异常收尾要经 `self.encoder`、写 Q 区前调 `self.getFlashRegionSize`，裸对象缺这两处会让本该报"Flash overflow"的用例被 `AttributeError` 顶掉。补桩而不是削断言。
- 文档也会自相矛盾（同一版本的 0x82 长度两份文档不一致），合并前先确认手上是不是最新合并版。

**关键文件与接口**: 命令：`git merge-tree --write-tree --name-only HEAD origin/develop`；`git -C controller/python/sub_common merge-base --is-ancestor f09ac0f HEAD`；`git -C controller/python/sub_embedded diff 89ea339 HEAD -- EncoderBase.py | grep "^-" | grep -v "^---"`。
文件：`controller/python/sub_common` 73e616e → merge `3dc6ebd`（并入 develop 的 `f09ac0f`）；`controller/python/sub_embedded` 89ea339 → merge `2ba14ad`（并入 `c339ac1`，`EncoderBase.py` 五处冲突）；`components/encoder/device.js`（保留本分支 DPB/DPT-G1 分支与 `calibrationLog` 字段，采纳 develop 无前缀消息处理）；主仓 merge 提交 `65639c24`。

**状态**: 已完成

### P-20260941: 端口回收与Boot混合扫描代码审查检查点
**日期**: 2026-10-14
**项目**: driverSoftware
**关键词**: Windows端口占用, server.py, server.exe, netstat, CIM, taskkill, 外部进程保护, 混合总线, Bootloader扫描, pytest

**需求场景 / 现象**: Review 当日端口回收与 Boot 混合总线扫描提交，需要判断自有服务清理是否越界，以及 Boot 诊断失败是否破坏 APP 设备发现结果。本次审查没有确认新的缺陷。

**方案 / 实施步骤**:
1. 按本机日期筛选全部提交并审查改动与上下文。
2. 端口回收检查：先以 netstat 映射占用 PID，再通过 CIM 取命令行；任一 owner 无法确认属于本项目时不杀任何占用者（端口归属证据不足必须按外部进程处理）。
3. Boot 扫描异常应 fail-open，并保留已发现的 APP ID；前端将两类 ID 合并去重后供选择。
4. 运行定向 pytest；Windows 端口行为测试在非 Windows 环境应跳过。

**验证方法**: 2026-10-14 本机 `git diff --check 8c2bc669^..dc0980af` 通过；`PYTHONPATH=<仓库根> pytest -q tests/unit/test_probe_boot_mode.py tests/unit/test_backend_port_binding.py tests/unit/test_port_reclaim.py` 得 45 passed。未运行 GUI、真机或完整打包。

**踩坑 / 已知异常与失败经验**: Windows PowerShell 下直接运行 pytest 时仓库根未自动出现在 Python 模块搜索路径，收集时报 `ModuleNotFoundError: No module named 'server'`；设置 `PYTHONPATH` 为仓库根后同一测试集通过。审查测试失败要区分环境导入问题和产品断言失败。

**关键文件与接口**: `server.py`：`_pids_on_port`、`_cmdline_of`、`_is_our_server_proc`、`_reclaim_port`、`api_probe_device_ids`；`frontend/js/app.js`（连接及切换设备时合并 APP/Boot ID）；`tests/unit/test_port_reclaim.py`、`tests/unit/test_probe_boot_mode.py`。

**状态**: 已完成

### P-20260942: 飞书文档不可读时用历史台账定位等价基线
**日期**: 2026-10-14
**项目**: MES / D:\code\mes
**关键词**: 飞书文档不可读, lark-cli 未安装, 内嵌浏览器未登录, 等价基线定位, accounts.feishu.cn 登录页, 面包屑标题, evidence 截图, SIRE run 复用

**需求场景 / 现象**: 用户只给一个飞书 wiki 链接要求"结合该文档分析代码"，但本机 `lark-cli` 未安装（`cmd /c where lark-cli` 为空），Qoder 内嵌浏览器打开链接被重定向到 `https://accounts.feishu.cn/accounts/page/login?...redirect_uri=...`，截图还报 `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`（viewport 0x0，只能 take_snapshot）。既不能调 API 也不能登录。

**方案 / 实施步骤**:
1. `list_pages` 读重定向 URL，确认是登录墙而不是渲染失败；用 `take_snapshot`/`list_pages` 拿到重定向 URL 里的 wiki token，确认目标资源。
2. `grep -rIl "<wiki token>"` 与 `grep -rIoh "https://[^ ]*feishu.cn/[a-z]*/[A-Za-z0-9]\{15,40\}"` 在台账/文档里找历史引用；在仓库自己的运行台账（`.sire/runs/<RUN>/` 的 journal.log、knowledge-record.md、evidence/*.jpg、导出的 HTML）里找该文档的历史写入记录，本例命中 `R20261014-084207/feishu-v1.3.html`。
3. 找同项目历史 run 的 evidence 截图，用 Read 打开图片核对标题与章节表格：用截图里的面包屑标题（"MES及追溯系统"）+ 章节号与表格行（§3.4.3 的"霍尔底涂/分板/标定/三防/成品检"）与本地 Markdown 逐行比对，行号级一致即认定同源。
4. 交付时把"线上增量未读"写成显式前提，并给用户一条补取路径（登录内嵌浏览器 / 导出 docx 到 docs/ / 装 lark-cli 并 auth login）。

**验证方法**: 同一结论需两条互相独立证据（截图表格行 vs 本地 MD 行号；或历史 run 产物 vs 知识记录 F-074）。只有一条时不得声称"该飞书文档就是本地这份"。

**踩坑 / 已知异常与失败经验**: - 飞书文档读取有两条通道，本机两条都断：CLI 通道缺二进制与 auth login；浏览器通道是未登录的内嵌实例且无可视 surface。继续找第三条通道（WebFetch）同样会撞登录墙，属无效绕路。
- 被否决方案：凭仓库线索猜文档内容（不可验证）、要求用户复制粘贴全文（成本高且丢排版）。
- 只看截图缩略图不足以定证，必须能读出面包屑标题；`.sire` 台账里往往没存 wiki URL，只存了截图，所以 token 反查会全空——这时改按"文档标题 + 章节内容"匹配，而不是继续找 URL。
- 登录墙判定用 `mcp__browser-use__take_snapshot`，不要用 take_screenshot（内嵌浏览器无 surface 会失败）。

**关键文件与接口**: `D:\code\mes\.sire\runs\R20261014-084207\evidence\feishu-dpb-final.jpg`（截图含飞书面包屑标题与 §3.4.3 表格，等价性主证据）；`D:\code\mes\docs\requirements\MES-综合需求规格说明书.md:314-330`（本地基线）；`mcp__browser-use__take_snapshot`。

**状态**: 已完成

### P-20260943: driverSoftware Job 8909 台架脚本漏包修复
**日期**: 2026-10-14
**项目**: driverSoftware / D:\code\driverSoftware
**关键词**: 打包失败, Nuitka, GitLab Job 8909, driverSoftware, raw-dir, build.bat, dc946d7, include-raw-dir

**需求场景 / 现象**: 用户提供 GitLab build-win-smoke 日志，提示 `tools\force_calib\calibrate_force_v2.py` 未随包走。根因：Nuitka 的数据文件收集把台架 `.py` 源码过滤掉。

**方案 / 实施步骤**:
1. 改用 `--include-raw-dir=tools/force_calib=tools/force_calib` 原样递归复制，并保留编译后实物断言。
2. 修复源目录收集参数与两平台提示。
3. 同步测试和用户文案。
4. 运行相关测试和独立 Nuitka 产物检查。提交 `dc946d7`（fix: 修复 Nuitka 漏收台架运行脚本），未 push。

**验证方法**: pytest 47 passed；独立 Nuitka 真实编译收集 21 个文件，检查两个关键脚本均在产物。整项目构建因本机 wheel 缺被显式 include 的 `dataStructV4026` 停止，未声称完整包通过。

**踩坑 / 已知异常与失败经验**: raw-dir 必须使用 `源=目标` 写法；不完整 wheel 环境的失败与 Runner 日志显示的漏包根因需分开记录。

**关键文件与接口**: server.py；scripts/build.bat；scripts/build_mac.sh；tests/unit/test_run_script_entry.py

**状态**: 部分完成（修复已提交；完整应用构建等待同版依赖环境复核）

### P-20260944: 标定汇总 CSV 多语言和 Excel 写入边界修复
**日期**: 2026-10-15
**项目**: EncoderPlotter_0903_01
**关键词**: 标定汇总 CSV, i18n, 内圈, 外圈, Excel EPERM, EBUSY, 负轴向距离, DPB, CHANGELOG

**需求场景 / 现象**: 标定汇总输出在英文界面混用中文圈标签；Excel 占用时忙提示漏掉 Windows `EPERM`；首次写入界面语言被固化进表头；公式防护误伤以负号开头的轴向距离；DPB 判断、去重参数与子模块修复条目也需按统一口径处理。根因：圈名直接拼接未经过 `$t`，且翻译 key 包含尾空格；忙提示只有两个错误码；CSV 表头使用当前 locale；负轴向数值复用了外部文本安全规则；`saveCalibrationSummaryRow(key)` 参数未参与去重。

**方案 / 实施步骤**:
1. 圈名使用无尾空格的 `内圈` / `外圈` key 并在 formatter 内翻译。
2. 文件占用提示同时匹配 `EBUSY`、`EACCES`、`EPERM`；新文件表头使用固定字段标识符，避免依赖 UI 语言。
3. 轴向距离列保留数值符号，其余用户输入单元格继续使用公式防护。
4. 删除未使用的 `key` 参数，按单场会话固定一行去重；DPB 参数比较使用 `Encoder.Series.DPB`。
5. 根 CHANGELOG 记录 MPP 固件版本读取和旧版离线参数读取修复；DPB 的 `final` 字段标签按用户确认保持“产品版本”。

**验证方法**: 三个 JavaScript 文件 `node --check` 通过，`git diff --check` 通过；调用实际 `main/file.js` 处理器验证两行追加、只写一次固定表头并保留 `-0.85mm`；Windows `FileShare.None` 锁文件的 Node 追加打开实测返回 `EBUSY`。真实 Electron 与读取器标定流程未执行，标记 `BLOCKED-无法真实验证`。

**踩坑 / 已知异常与失败经验**: 负数距离虽含 `-`，仍是业务数值，不应像 SN 等外部文本一样加 Excel 公式前缀；CSV 新表头固定后不会自动重写历史文件已有的本地化表头。

**关键文件与接口**: `components/encoder/device.js`（轴向格式化、CSV 行、忙提示和会话去重）；`main/file.js`（追加 CSV 主进程处理器）；`components/analyzer/analyzer.html`、`components/i18n.js`、`CHANGELOG.md`；`controller/python/sub_embedded`（`2ba14ad` → `bcdf98c`）。

**状态**: 部分完成

### P-20260945: 标定失败弹窗读取响应体中的具体不良原因
**日期**: 2026-10-15
**项目**: EncoderPlotter_0903_01 / D:\code\EncoderPlotter_0903_01
**关键词**: 标定失败弹窗, defectiveItems, header.status, 外圈角度计算失败, setThenJustReturn

**需求场景 / 现象**: 标定失败弹窗只显示“标定失败”，没有呈现标定过程中已有的具体不良原因（例如“外圈角度计算失败”）。根因：Python 将 `success` 和 `defectiveItems` 放在 JSON 响应体，同时用非零 `processingStatus` 写入响应头状态；`Server.transmit` 因非零 header.status reject，但 `Encoder.setThenJustReturn` 捕获后返回 `{header,data}`；前端失败分支直接丢弃 `data.defectiveItems` 显示通用文案。

**方案 / 实施步骤**:
1. 在响应头失败分支读取 `data.data.defectiveItems`（前端失败响应分支保留响应体不良项）。
2. 复用 `_buildCalibrationFailReason` 和 `DefectiveItemsMap` 得到用户文案，写入标定日志并传给失败弹窗。
3. 缺陷项为空或无法映射时继续用通用“标定失败”；超时、手动停止和无响应的通信异常保持原行为。
4. 独立核对非零 header status、具体错误代码、空/未知代码及超时和异常路径。

**验证方法**: `node --check components/encoder/device.js` 与 `git diff --check` 通过。独立代码级检查以响应头 status=1 和 code `0-1-2-8` 调用生产原因构建器，输出“外圈角度计算失败”；空数组和未知代码的回退均为“标定失败”。用户明确无需真机，未运行 Electron UI。

**踩坑 / 已知异常与失败经验**: header status 表示执行结果失败不等于响应体为空；先判状态后丢弃 payload 会隐藏具体失败原因。

**关键文件与接口**: `controller/server.js`（非零响应状态以 `{header,data}` reject）；`controller/encoder.js`（`setThenJustReturn`）；`controller/python/Encoder.py`（AllInOne 失败仍将 `defectiveItems` 放进响应体）；`components/encoder/device.js`（失败原因构建和弹窗入口）；`components/encoder/mes/mes.js`（不良项代码到中文文案映射）。

**状态**: 已完成

### P-20260946: MES基础架构方案：分阶段配置、授权与审计恢复
**日期**: 2026-10-16
**项目**: MES 后台管理系统 / D:\code\mes
**关键词**: MES 架构, modular monolith, MES execution order, configuration package, workflow version, scoped authorization, worker identity, transactional outbox, PITR, audit recovery

**需求场景 / 现象**: 基于 MES 需求规格和初始管理系统架构模型，形成可供跨部门评审的基础搭建方案，同时保留未批准的业务规则为责任人待决项。

**方案 / 实施步骤**:
1. 读取现有需求与架构输入，列出权威边界和阶段依赖。
2. 形成领域、运行、数据、安全和恢复章节，并将需业务确认的内容列为 D1-D18。
3. 经领域、运行时、安全三个独立视角评审，修订工作流阶段边界、双主体授权、outbox/PITR 和审计恢复语义。

**验证方法**: 检查文档含 17 个主章节、1 个 Mermaid 图、18 个责任人待决项及阶段0-5；相对参考链接目标存在。三路独立评审及交叉核验完成，最终没有未关闭的 Blocker/Major。未运行应用代码测试，因为该任务只交付架构文档。

**踩坑 / 已知异常与失败经验**: 设计要点：首期采用边界清晰的模块化单体，按领域明确数据所有权；每个 MES 执行订单固定绑定唯一配置包，阶段1仅引用工艺路线/标准作业基线，工作流版本待阶段4再加入；授权按主体、资源、动作、范围、有效期完整匹配，用户发起的后台任务执行时重新核验用户授权，并与最小权限 Worker 主体取交集；关键业务审计与业务事务同库提交，外部审计归档使用 outbox。踩坑：PITR 回退的是业务数据库状态，不会让已经发生的下载、拒绝或外部副作用自动消失；恢复后的审计回填必须保留事件类型对应的恢复处置状态（保留原 event ID 和时间）；外部归档使用异步 outbox 时，也不能宣称与业务数据库跨库原子提交。

**关键文件与接口**: docs/architecture/MES-基础搭建架构方案.md；docs/requirements/MES-综合需求规格说明书.md

**状态**: 部分完成（架构建议稿待产品、生产、质量、仓储、ERP、IT 和安全责任人评审；实施与生产恢复演练待后续验证）

### P-20260947: 大型 IAP 分支合并评估要区分静态与硬件验收
**日期**: 2026-10-16
**项目**: EncoderPlotter_0903_01
**关键词**: 分支合并评估, git merge-tree, IAP回归, 子模块gitlink, 真机验收

**需求场景 / 现象**: 评估大型功能分支合入主线后是否完全兼容。无文本冲突、静态差异或单元测试均无法单独证明硬件相关多模块行为兼容，尤其涉及 IAP 擦写与固件恢复时。

**方案 / 实施步骤**:
1. 明确 base 与目标引用，避免把工作分支当作合并目标。
2. 盘点提交数、差异文件、子模块指针和冲突：`git rev-list --left-right --count base...target`、`git merge-tree base base target`、`git diff --check base...target`、`git ls-tree target controller/python/sub_common controller/python/sub_embedded`。
3. 按业务链路审差异，单独核对 gitlink 目标并确认工作区子模块状态。
4. 按正常与失败路径安排 Windows/Linux、HTTP API、IAP 真机验收；没有硬件证据时结论限定为静态风险评估，静态检查结论与运行验收结论分开报告。

**验证方法**: 实际只读命令可得提交计数、目标文件统计、merge-tree、diff-check 和子模块状态；功能兼容仍需 CI 与设备路径验证。

**踩坑 / 已知异常与失败经验**: 子模块 checkout 可能不是目标 gitlink 所指的提交；不能把本地当前子模块内容当作目标分支实现。IAP HTTP 层把校验移到 bin 解析核心后，route 单测应覆盖错误 bin、跨系列、旧固件和异常中断，并需硬件升级后回读验证。

**关键文件与接口**: 本仓 IAP 主路径：`controller/python/Encoder.py`、`controller/python/parse_iap_bin.py`、`controller/python/qa_api/routes_iap.py`；子模块版本：`git ls-tree target controller/python/sub_common controller/python/sub_embedded`。

**状态**: 已完成

### P-20260948: IAP解析兼容程序加密包内的分段加密固件
**日期**: 2026-10-16
**项目**: EncoderPlotter1
**关键词**: IAP, 程序加密, 分段加密, AES V2, Protector.decrypt_iap_segmented_data, ARGUMENTS, 固件参数解析

**需求场景 / 现象**: 用户先对固件执行IAP分段加密，再用程序加密包裹该分段文件。普通IAP能解开外层程序包，却无法扫描内部ARGUMENTS，报“未识别出有效的固件参数结构”。根因：程序加密和分段加密是两层不同格式，现有IAP流程只对外层调用Protector.decrypt_file，返回的仍是供设备传输的V2/V3分段包。

**方案 / 实施步骤**:
1. 解程序加密外层包。
2. 保留外层解密结果用于分段传输（上传仍用 `app_data`），另建元数据副本（独立 `metadata_data` 解析流）。
3. 严格验证并解开V2或V3：V2验证包长度、连续序号、内部长度和CRC；V3验证包边界与CRC(iv+密文)；再执行Flash Layout Footer和ARGUMENTS解析。
4. 不要把解析明文覆盖上传变量或重试摘要输入。

**验证方法**: 对目标kingkong.bin，外层解密得到535716字节V2包，内层还原496888字节；解析出DPT 4.2.6、算法4060、ARGUMENTS版本4、结构有效。截断包和短包均拒绝。未进行真机IAP烧录。

**踩坑 / 已知异常与失败经验**: 现有基于文件路径的 `decrypt_file_aes` 只支持V2且落盘；兼容IAP参数预检需要V2/V3内存解码以避免临时明文文件，同时保留原传输字节。

**关键文件与接口**: `controller/python/sub_common/Protector.py`（`Protector.decrypt_iap_segmented_data(data)` 内存严格解密，返回固件字节和V2/V3格式）；`controller/python/Encoder.py`（普通IAP参数校验使用独立 `metadata_data`；上传仍用 `app_data`）。

**状态**: 部分完成

### P-20260949: IAP首包C5 01向量表失败与V2/V3传输格式匹配
**日期**: 2026-10-16
**项目**: EncoderPlotter1
**关键词**: IAP, 5CC5, C5 01, vector table, BootLoader V2 V3 V4, segmented encryption format mismatch

**需求场景 / 现象**: 外层程序加密内含分段加密 V2 的 DPT 固件可正确解析；设备上传第1包后，5CC5提交响应 `C5 01`，导致升级失败。仓库协议核查记录将 5C C5 01 定义为向量表校验不通过。固件分段记录格式需与目标BootLoader一致：BL V2使用V2（记录无包尾CRC）；BL V3/V4使用V3（每记录有CRC）。若拿V2文件发给V3/V4，会将下一条记录长度字节误作CRC并破坏首包解密结果。截图未包含目标IAP版本，格式错配为高概率根因，最终确认仍需完整日志中的当前BootLoader版本行。

**方案 / 实施步骤**:
1. IAP读出BootLoader版本后、发首个数据包前校验固件分段格式匹配：V2只允许BL V2，V3允许BL V3/V4。
2. 明确的C5 01/5C C5 01向量校验失败不进行无效重试。
3. `Encoder.py` 将解析出的 segmentedEncryptionFormat 传给上传流程。

**验证方法**: V2/V2、V3/V3、V3/V4通过；V2/V3、V3/V2拒绝；mock C5 01只发送一次；精确BIN预览解析仍返回 DPT 4.2.6/V2。未真机复测。

**踩坑 / 已知异常与失败经验**: 硬件原因待目标BootLoader版本日志确认；当前仅加了格式错配保护和明确错误响应。

**关键文件与接口**: `controller/python/sub_embedded/IAP.py`（`validateIapSegmentedEncryptionFormat`、`uploadApp`、5CC5提交响应）；`controller/python/Encoder.py`。

**状态**: 部分完成

### P-20260950: IAP V3末包不足256字节导致分段固件解析失败
**日期**: 2026-10-16
**项目**: EncoderPlotter1
**关键词**: IAP V3 segmented encryption, partial final chunk, Protector.decrypt_iap_segmented_data, CRC8, AES CBC

**需求场景 / 现象**: 用户提供的 DPT30 V4.2.6 BIN（外层程序加密，内层分段加密）预览解析失败。外层解密成功；内层是V3分段包。V3加密器每次读取最多256字节，因此有效文件末包可以小于256字节。解码器误将任何前面已有包的短包都判为“非末包”，导致解码失败并将密文回退到ARGUMENTS扫描。

**方案 / 实施步骤**:
1. 外层程序解密。
2. 按V3长度记录、CRC校验并还原明文：收集V3每包解密长度，严格要求除最后一包外均为256字节，最后一包允许1至256字节；CRC仍需通过。
3. 用现有Footer/ARGUMENTS规则解析。

**验证方法**: 指定文件外层537657字节，内层V3还原496888字节；解析为DPT 4.2.6、算法4060、ARGUMENTS v4。实际预览命令返回status=ok。旧V2文件仍可解析。CRC有效但非末包短于256的合成数据被拒绝。未做Electron实机或硬件升级。

**踩坑 / 已知异常与失败经验**: “前包之后短于256”不足以判定无效；必须解析完全部记录后再判断它是不是末包。

**关键文件与接口**: `controller/python/sub_common/Protector.py`（`Protector.decrypt_iap_segmented_data` V3末包校验）；`controller/python/Encoder.py`（离线预览命令复用该解码器）。

**状态**: 部分完成

### P-20260951: EncoderPlotter1读取器功能与IAP子模块合并兼容验证
**日期**: 2026-10-16
**项目**: EncoderPlotter1
**关键词**: EncoderPlotter1, analyzer-iap, iap-ota-sn, 子模块合并, AnalyzerInfo

**需求场景 / 现象**: feature/iap-ota-sn 完整接入 feature/analyzer-iap，同时保留已有 DPT V5 参数恢复、SN 回读与分段加密升级。

**方案 / 实施步骤**:
1. 两个子仓先分别内容合并再更新父仓 gitlink，禁止择一覆盖。
2. sub_common a314a17 同时包含 e13db13 与 c65b5e3；sub_embedded e3d9daa 同时包含 47c7bf6 与 8ab1943。
3. 父仓 c62fe446，保留 const isAnalyzer 的原有通用读取器热插拔实现。
4. selector.html 用户原有删除6选项的修改保留未提交。未推送任何仓库；推送需先子仓后父仓。

**验证方法**: 266 passed, 29 subtests passed（qa_api、sub_embedded、v4060、iap_sn_restore、build_info、safe_name）；JS语法及差异空白检查通过。独立review确认双祖先可达、Info None/空/15字节失败与16字节成功、PID1/2/3/5及异常SN隔离通过。

**踩坑 / 已知异常与失败经验**: 没有真实读取器升级、热插拔及Ubuntu设备验收，标记BLOCKED-无法真实验证，不承诺全部硬件完全兼容。

**关键文件与接口**: controller/python/sub_common/DataFormatter.py；controller/python/sub_embedded/Analyzer.py；controller/analyzer.js；controller/index.js；main/index.js。

**状态**: 部分完成

### P-20261016: MES 可扩展模块基础架构边界与发布流程
**日期**: 2026-10-16
**项目**: MES 后台管理系统，D:/code/mes
**关键词**: MES基础架构, 模块化架构, 独立部署, 模块独立数据库, 控制面, Outbox, 无同步热路径, Release编排, manifest, version_token, perm_epoch, 范围授权

**需求场景 / 现象**: 为支持业务模块任意创建和独立添加，需要先定义一套模块依赖的 MES 基础平台和模块契约。

**方案 / 实施步骤**:
1. 先落地 SDK/稳定契约、模块注册、身份与权限、模板版本、事件/outbox、审计、Release 与观测等基础能力。
2. 通过独立参考模块验证制品签名/审批、独立数据库/迁移、路由、范围授权和事件链路。
3. 再允许模块按 manifest 声明权限、依赖、API/事件、UI、任务与健康检查并独立部署。
4. 建设阶段以跨模块事务、撤权屏障、终态数据保护和重试补偿作为验收边界。

**验证方法**: 最终建议稿含5张Mermaid图、代码围栏成对；模块独立部署/数据库、禁止热路径同步调用、本地Outbox、默认拒绝、模板版本令牌、perm_epoch提交栅栏、终态保护及范围授权全路径有文本依据；R6领域/运行时/安全评审和交叉复核通过。未运行业务代码测试。

**踩坑 / 已知异常与失败经验**: 原模型同时包含“模块独立发布”和“单一Release制品”两种口径，建议把Release定义为锁定版本与部署计划，不合并为单体制品；预留门禁凭证是特定任务授权线性化点，后续复判可阻止新预留，但不能宣称立即撤销已预留任务；范围授权必须下沉到查询与后台执行层，禁止先读全量再过滤。设计要点：模块业务热路径不做同步跨模块 RPC，每个模块通过本地事务 Outbox 发布版本化事件；撤权以 perm_epoch 和提交栅栏确认生效；跨模块强约束采用目标绑定预授权凭证、命令账本、幂等和低频对账，不直连其他模块数据库。

**关键文件与接口**: docs/architecture/MES-基础搭建架构方案.md；docs/requirements/MES-综合需求规格说明书.md

**状态**: 部分完成（架构建议稿，待责任人确认 Release 定义与跨模块门禁语义）

### P-20261017: MES 重建进度交接（Claude/Codex 同步入口）
**日期**: 2026-10-18
**项目**: MES 平台重建 / D:/code/mes
**关键词**: MES重建, 进度交接, Codex同步, PROGRESS.md, mes-admin, mes-server, mes-db, mes-web, IAM, 低代码, 模块管理, LOWCODE契约, 演示模式, dev:mock, Docker未重启, BLOCKED

**需求场景 / 现象**: Claude 与 Codex 交替开发 D:/code/mes。接手方需要知道当前做到哪、哪些未验证、从哪里继续。当前状态摘要：仓库已清空重建为 npm workspaces 四部分（mes-web 空、mes-admin、mes-server、mes-db），暂不关联 Git；栈：React18+TS+Vite+Tailwind+Radix 自建组件；NestJS10+Kysely+zod；PostgreSQL16（Docker）；IAM 一期代码完成，数据库集成测试与 E2E 因电脑未重启（WSL2/Docker 未生效）BLOCKED；模块管理（低代码）v1 进行中已暂停。

**方案 / 实施步骤**:
1. 进度单一来源放在仓库内 `docs/PROGRESS.md`，并在 `AGENTS.md` 必读清单第 6 项引用；本条知识只做索引。
2. 接手前读 AGENTS.md → docs/PROGRESS.md → 相关契约。
3. 低代码从 PROGRESS.md 第 4 节“待完成”第 1 步继续；后端已存在的 lowcode 文件（0002 迁移与 schema.ts 是中途停止的产物，未复核）先复核再使用。
4. 阶段完成后更新 PROGRESS.md 的状态表与断点。

**验证方法**: `npm run build`、`npm test`（根目录）；演示模式 `npm run dev:mock -w mes-admin` 浏览器查看；重启并启动 Docker 后按 PROGRESS.md 第 3 节顺序跑集成与 E2E。

**踩坑 / 已知异常与失败经验**: Vitest 的 esbuild 不支持 emitDecoratorMetadata，mes-server 测试用 unplugin-swc；dev 用 tsc --watch + node --watch。初始管理员密码只在 mes-db/.local/initial-admin.txt，不得写入任何日志或报告。

**关键文件与接口**: `D:/code/mes/docs/PROGRESS.md`；`D:/code/mes/docs/design/IAM-基础身份权限契约.md` v1.1、`LOWCODE-模块管理契约.md` v1.0；`D:/code/mes/DESIGN_SYSTEM.md` v2；`D:/sire/sire_ledger/runs/R20261018-MES-LOWCODE-V1/checkpoint.md`。

**状态**: 部分完成

### P-20261018: 低代码模块删除与发布需要共享引用锁协议
**日期**: 2026-10-18
**项目**: MES 重建 / D:\code\mes
**关键词**: lowcode, 模块软删除, publish, 引用完整性, 并发竞态, lock ordering

**需求场景 / 现象**: 删除模块时需要防止仍被其他已发布模块引用；并发发布可以在删除检查之后新增引用。

**方案 / 实施步骤**:
1. 定义发布与删除共享的锁顺序。
2. 发布前锁引用目标；删除时锁定可能引用方并再次检查。
3. 增加两个事务交错的集成测试。

**验证方法**: 运行覆盖并发 publish/delete 的 PostgreSQL 集成测试；当前未运行。

**踩坑 / 已知异常与失败经验**: 根因：`ModulesService.remove()` 仅锁待删除模块行后查询其他模块的已发布 schema；`publish()` 只锁当前源模块行，发布校验读取目标模块不加锁。两个事务无共同锁，无法串行化“查引用并删除”与“发布新引用”。只锁待删除模块并不足以保护反向引用，因为写入引用发生在源模块事务。建议删除与发布对引用目标使用一致的行锁协议，并在锁定后复查引用；保持所有模块锁顺序一致以避免死锁。实现尚未完成。

**关键文件与接口**: mes-server/src/lowcode/modules.service.ts:506（remove()）；mes-server/src/lowcode/modules.service.ts:376（publish()）

**状态**: 部分完成

### P-20261019: MES 低代码模块管理：动态权限、防自授权与发布并发锁序
**日期**: 2026-10-18
**项目**: MES 平台 / D:/code/mes（mes-admin、mes-server、mes-db）
**关键词**: 低代码, 模块管理, 元数据, schema 版本, JSONB 动态字段, 动态权限, mod:{code}:view, RLS, 防自授权, privilege escalation, IAM_PRIVILEGE_ESCALATION, 发布锁序, FOR SHARE, FOR UPDATE, 同编码重建, 悬空引用, Playwright E2E, NestJS Kysely PostgreSQL

**需求场景 / 现象**: 后台“模块管理”让管理员自定义业务模块（如产品管理）：字段、列表、筛选、关联完全由配置决定，发布后出现在业务菜单并可增删改查、搜索导出；同时必须保证权限默认拒绝、不能借角色配置自我提权、并发下不留脏数据。

**方案 / 实施步骤**:
1. 模块 = 一个对象；schema（字段 10 种类型、标题字段、默认排序）分草稿与不可变发布版本；记录存 `lc.records.data jsonb`，记录写入时的 `schema_version` 以复合外键指向 `module_versions`。
2. 新建模块同事务生成 5 个动态权限 `mod:{code}:view/create/update/delete/export`（`module='lowcode'`），运行账号经 RLS 只能写 `module='lowcode' AND code LIKE 'mod:%'` 的权限行；种子同步不删动态权限。
3. 列表查询：关键词/筛选/排序全部参数化下推（JSONB 按类型 cast），禁止取全量再过滤；唯一字段写入用 advisory xact lock；编号锁模块行取号。
4. 防自授权（用户确认）：不能改自己的角色；非超管新增角色、给角色加权限、启用停用角色时，授出的每项权限必须自己已持有，否则 403 `IAM_PRIVILEGE_ESCALATION`（details.missing）。
5. 发布与删除并发：发布按 id 排序锁本模块 FOR UPDATE + 引用目标 FOR SHARE，并核对“按 code 查到的活动目标 id == 已锁 id”，否则 409 回滚；删除对目标 FOR UPDATE 后扫描引用。

**验证方法**: `npm test`（admin 20、server 77、db 14）；`npm run test:integration -w mes-server` 34/34；`npm run e2e -w mes-admin` 13/13（真实后端）。

**踩坑 / 已知异常与失败经验**: - 被否决：每模块独立物理表（DDL 需高权限、迁移复杂）；前端过滤（越权与性能）。
- 弹窗内的 Select/Popover 被遮罩压住：浮层 z-index 要高于 modal（新增 z-popover 1050）。
- 演示 mock 里 `const db = load()` 放在常量声明之前导致 TDZ 报错，需放在所有声明之后。
- 外部复核连续发现授权旁路：除“分配”外，“启用停用角色”同样等于授权；删除后同编码重建会让按 code 校验失效，必须核对已锁行 id。
- E2E 连续登录会触发登录限流，本地 .env 放宽 `LOGIN_RATE_LIMIT`；整页跳转前要等登录完成，否则刷新令牌 Cookie 未写入。
- Playwright `getByLabel('新密码', {exact:true})` 匹配不到带必填星号的标签，用正则 `/^新密码/`。
- 确定性屏障并发测试待补。

**关键文件与接口**: `docs/design/LOWCODE-模块管理契约.md` v1.1、`docs/design/IAM-基础身份权限契约.md` v1.2；`mes-server/src/lowcode/{modules,apps}.service.ts`（`referenceTargets`、`isLockedTarget`）、`common/permission.ts`（`escalationGap`）；`mes-db/migrations/0002_lowcode.up.sql`；`mes-admin/src/lowcode/`（designer/ModuleDesigner、pages/AppPage、FilterBar、schema-utils）。

**状态**: 已完成

### P-20261020: PostgreSQL工作流角色引用的精确查询与并发锁保护
**日期**: 2026-10-19
**项目**: MES / D:/code/mes
**关键词**: PostgreSQL, Kysely, JSONB, jsonb_path_exists, workflowRoleCodes, FOR SHARE, FOR UPDATE, 工作流角色引用, 流程快照, 并发发布, pg_locks, pg_blocking_pids

**需求场景 / 现象**: 角色被已发布工作流或记录流程快照引用时必须禁止删除/停用。实际复核发现：递归扫描整个 definition 会把同名状态标签误认为角色引用；普通角色存在性 SELECT 又不能与角色删停的 FOR UPDATE 串行化。

**方案 / 实施步骤**:
1. 区分角色编码数组与任意文本：快照查询只扫描 states[*].editRoleCodes、states[*].viewRoleCodes、transitions[*].actorRoleCodes、transitions[*].approvalRoleCodes，角色码使用 SQL 参数。
2. 写入引用前获取角色共享锁（真实发布与记录快照创建时，对最终引用的活动、未删除角色按稳定 ID 顺序 FOR SHARE，持锁到事务提交），锁后重新检查 active/deleted_at 条件。
3. 角色删除/停用先 FOR UPDATE 再扫描已提交引用；只读发布预校验不持锁。
4. 固定角色锁排序；避免为了绑定快照而临时追加目标模块锁，引入宿主/目标交叉锁。
5. 并发测试用独立连接持角色 FOR UPDATE，启动真实 HTTP 请求，通过 pg_locks 未授予锁与 pg_blocking_pids 确认等待，再提交停用，断言发布或创建拒绝。

**验证方法**: 服务端 typecheck；LC-VIS-INT-006 标签同名不误阻止，008 新版本移除引用但旧快照仍保护角色，009 发布与停用串行，010 绑定创建与停用串行。完整测试日志与开发库恢复证据位于本次独立台账 evidence/。

**踩坑 / 已知异常与失败经验**: 根因：`definition.** ? (@ == $c)` 不区分业务文本与角色数组；READ COMMITTED 下普通 SELECT 不阻止另一事务随后修改角色；读取旧绑定流程定义与插入记录快照之间也存在引用不可见窗口。不要依赖低权限连接读取其他账号的 pg_stat_activity.query，其文本可能被权限屏蔽。Supertest 请求是惰性的，赋给变量不代表请求已启动，先调用 `.then(response => response)` 再观察数据库等待。E2E 角色选择器要限定编辑角色或可见角色所在组件，同一角色会出现在两处。开发库 E2E 前完整备份，结束还原迁移后 dump 与初始管理员文件，不覆盖真实业务数据。

**关键文件与接口**: D:/code/mes/mes-server/src/roles/roles.service.ts（assertRoleNotUsedByWorkflow）；mes-server/src/lowcode/modules.service.ts（publishIssues）；mes-server/src/lowcode/apps.service.ts（createRecord）；mes-server/test/integration/lowcode-visibility.int.test.ts

**状态**: 已完成（已实现，最终测试结果见本次台账 validation.md）

### P-20261021: 【MES 测试服务器】10.0.64.2：SSH 公钥登录、主机指纹核对与 Docker 权限
**日期**: 2026-10-19
**项目**: MES 重建 / D:\code\mes
**关键词**: MES 测试服务器, MES 部署服务器, 10.0.64.2, SSH 公钥登录, mes_ed25519, 主机指纹, known_hosts, docker 权限, docker compose, 共享服务器, ssh-keyscan unsupported KEX sntrup761x25519, 端口占用, choose_kex

**需求场景 / 现象**: 需要从本机连接公司内网 MES 部署服务器（测试/联调部署用，非生产），用于部署 mes-server 与数据库；管理员先开通普通账号（无 sudo、无 Docker），随后加入 docker 组。本机 `ssh-keyscan` 报 `choose_kex: unsupported KEX method sntrup761x25519-sha512@openssh.com`，拿不到主机指纹。

**方案 / 实施步骤**:
1. 未核对指纹前不要登录；取指纹：`ssh -v -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=<空文件> -i ~/.ssh/mes_ed25519 mes@10.0.64.2 exit`，从调试输出取 ed25519 指纹发管理员核对。
2. 一致后用 `StrictHostKeyChecking=accept-new` 登录写入 known_hosts，`whoami; hostname; uname -sr` 验证。
3. 部署时 MES 容器统一加 `mes-` 前缀，只操作自己的资源；PG 不映射宿主机或仅绑 127.0.0.1；端口避开已占用的。

**验证方法**: `ssh -o BatchMode=yes -i ~/.ssh/mes_ed25519 mes@10.0.64.2 "id; docker ps; docker compose version"`，期望 groups 含 docker，能列出容器和 compose 版本（2026-10-19 验证通过，Docker Compose v5.1.4 可用）。

**踩坑 / 已知异常与失败经验**: 根因：本机旧版 ssh-keyscan 不支持服务器的 sntrup761x25519 密钥交换；但 ssh 客户端本身支持 curve25519-sha256，可用 `-v` 严格模式读到指纹。先核对主机指纹再登录，不用 `StrictHostKeyChecking=no`。公钥指纹（Ykboxi1v…）是本机公钥的，不是服务器主机指纹，别混淆。共享服务器上禁用 `docker system prune`、不要动他人容器和端口；主机指纹若变化须停止并找管理员核对，不要忽略警告；ssh-keyscan 失败不代表网络不通（22 端口可达）。

**关键文件与接口**: 地址 10.0.64.2，SSH 端口 22，用户 `mes`，需先连公司内网；登录：`ssh -i ~/.ssh/mes_ed25519 mes@10.0.64.2`（私钥仅在本机，不入库不入仓库）；服务器 ed25519 主机指纹 `SHA256:FNPCkhf72fL+MlfPyBjvAgs+cx6fI8BGcau4US3mW9Y`，2026-10-19 管理员核对一致；主机 lenovo-ThinkSystem-SR650-V3，Ubuntu，Linux 7.0.0-22；账号 uid=1006(mes) 属 mes、docker(973) 组，无 sudo；共享服务器已占用端口含 3010/3011/8000/8083/18080/18090/28090/28091/30090-32091

**状态**: 已完成

### P-20261022: Compose internal 网络 API 宿主 loopback 发布的测试部署模式
**日期**: 2026-10-19
**项目**: MES / D:/code/mes
**关键词**: Docker Compose internal 网络, loopback 端口映射, bridge 网络, PostgreSQL, NestJS API, SSH 隧道

**需求场景 / 现象**: 测试服务器上的 API 容器需连内部 PostgreSQL，同时让服务器宿主机 loopback 发布 API 供 SSH 隧道访问。仅使用 Compose `internal: true` 网络时，本次实测宿主端口未监听。

**方案 / 实施步骤**:
1. DB 与迁移容器只接入 internal 网络，DB 不发布宿主端口。
2. API 同时加入 internal 与 bridge 网络，仅绑定宿主 loopback 端口。
3. 通过服务器本机 health 和 SSH 隧道检查 API，并检查 DB 故障、恢复和重启后的行为。

**验证方法**: 检查 Compose 网络和端口映射；访问 `/api/v1/health` 应返回 200/db=up；停止 DB 时为 503/db=down，恢复及容器重启后恢复 200/db=up。实际结果记录于运行 `R20261019-113834-mes` 的 U2/U3 证据。

**踩坑 / 已知异常与失败经验**: 根因：internal 网络隔离外部连通；当前 Docker 实现下，依赖只在该网络的 API 服务不能按预期发布宿主端口。不能只凭 compose.yaml 声明推断端口可达，需在宿主实际核对监听和 HTTP 响应。初始化挂载脚本还需确保容器可读（目录 755、脚本 644）。API bridge 带出站能力，不适用于要求完全禁出站的生产策略。

**关键文件与接口**: D:/sire/sire_ledger/runs/R20261019-113834-mes/evidence/compose.yaml；.../evidence/U2/network-isolation.txt；.../evidence/U3/health-after-restart.txt；127.0.0.1:33100 -> API container :3100（SSH 隧道入口）

**状态**: 已完成

### P-20261023: Vite 管理端通过 SSH 隧道接入 loopback 部署 API
**日期**: 2026-10-19
**项目**: MES / D:/code/mes
**关键词**: Vite MES_SERVER_URL, 本地开发服务器, SSH本地转发, loopback代理, mes-admin, 33100端口

**需求场景 / 现象**: MES 后端已部署到测试服务器，但管理端仍用 Vite 默认代理 `http://127.0.0.1:3100`，没有接到服务器 API。服务器 API 仅绑定远端 loopback `127.0.0.1:33100`。

**方案 / 实施步骤**:
1. 核对服务器 API 正常且服务器 host key 严格校验通过。
2. 在 `mes-admin/.env.development.local` 设置 `MES_SERVER_URL=http://127.0.0.1:33100`，不修改项目默认代理代码（忽略文件不提交）。
3. 建立 SSH 本地转发 `127.0.0.1:33100 -> remote 127.0.0.1:33100` 并启动管理端。
4. 分别检查隧道 health 和 Vite `/api` 代理 health。

**验证方法**: GET `http://127.0.0.1:33100/api/v1/health` 和 `http://localhost:5174/api/v1/health` 均返回 `{"status":"ok","db":"up"}`。

**踩坑 / 已知异常与失败经验**: 根因：后端部署和项目运行配置是两部分；Vite虽支持 `MES_SERVER_URL` 环境变量，但尚未设置本地开发环境值。远端绑定 `127.0.0.1` 时，`MES_SERVER_URL=http://10.0.64.2:33100` 不可达且会不必要地暴露服务假设。Vite 当前监听 `[::1]:5174`，所以页面使用 `localhost`，不是强制 IPv4 字面地址。

**关键文件与接口**: D:/code/mes/mes-admin/vite.config.ts:7；D:/code/mes/mes-admin/.env.development.local；http://localhost:5174/api/v1/health；http://127.0.0.1:33100/api/v1/health

**状态**: 已完成

### P-20261024: MES订单工序路线版本与审批实走边界
**日期**: 2026-10-19
**项目**: MES / D:/code/mes
**关键词**: MES, 生产订单, 工序路线, 工作流版本, 关联字段, 审批, 免审批流转, 流程快照

**需求场景 / 现象**: 在低代码 MES 中配置工序路线，让订单选择产品、路线和路线工作流版本，并按路线工作流流转。

**方案 / 实施步骤**:
1. 发布工序管理模块，并为其创建、启用流程版本。
2. 在订单模块添加产品引用及工序路线引用（关联记录字段并开启“同时选择工序工作流版本”），启用工序工作流版本绑定。
3. 创建路线、订单并选择启用版本，再提交审批。

**验证方法**: 当前测试环境实际创建产品 PRD-000003、路线 RTE-000001、订单 MO-000001；订单详情显示版本 v1，提交后记录处于待审批。当前会话没有测试角色身份，未验证审批结果与后续免审批流转，不应报告端到端完成。

**踩坑 / 已知异常与失败经验**: UI 里的“免审批”流转仍需用户点击操作（免审批代表动作立即生效，不代表后台自动触发）；待审批状态的可见/审批权限依赖审批角色。设置审批角色时需确保审批人不是同一发起用户，不能用超级管理员对自己发起的流程自审。

**关键文件与接口**: D:/code/mes/docs/design/LOWCODE-模块管理契约.md；D:/code/mes/docs/PROGRESS.md

**状态**: 部分完成（审批之后的流转待具备测试角色账号后实走）

### P-20261025: MES生产订单审批角色权限与工作流快照实走
**日期**: 2026-10-19
**项目**: MES / D:\code\mes
**关键词**: MES低代码, 生产订单审批角色, mod:production_order:view, lowcode:module:view, 工作流快照, 流程版本, 无审批流转, IAM权限

**需求场景 / 现象**: 测试角色被流程配置为工序审批角色，但没有模块访问权限；审批测试无法进入订单。订单流程快照固定旧审批角色，修改模块当前流程不能重写已创建记录。

**方案 / 实施步骤**:
1. 创建角色并设置最小菜单/业务查看权限。
2. 创建演示账号并切换角色，确认其只能访问已授权业务模块。
3. 保存并发布流程V2，确认旧记录保留旧审批角色快照。
4. 新建关联V2的订单，分账号发起和审批；核对审批历史、备注和后续无审批流转。

**验证方法**: 浏览器实走MO-000002（V2）通过“草稿→待生产审批→待备料”，审批人与发起人不同；浏览器实走MO-000001（V1）确认旧快照仍按test角色匹配。页面最终状态和审批历史均可见。

**踩坑 / 已知异常与失败经验**: 根因：低代码菜单入口由 `lowcode:module:view` 控制，记录/审批接口还需模块级 `mod:<module_code>:view`；审批角色编码从工作流版本快照匹配，不会随模块更新自动改变。只有 `mod:production_order:view` 时页面路由存在但业务侧栏/模块入口不会显示，补充 `lowcode:module:view` 后可见。订单快照不会因模块工作流V2自动改变，需新建订单选择V2。无审批“自动流转”仍要点击转移按钮，表示不需审批而非后台定时自动执行。生产执行、质检和完工未覆盖。

**关键文件与接口**: docs/design/IAM-基础身份权限契约.md；docs/design/LOWCODE-模块管理契约.md；/roles/:id/permissions；/users/:id/roles；/api/v1/lowcode/:code/records/:id/approval；/transitions

**状态**: 部分完成（配置链路验证至待备料；生产执行、质检和完工未覆盖）

### P-20261026: 生产订单工作流版本V1与V2显示同名
**日期**: 2026-10-19
**项目**: MES / D:\code\mes
**关键词**: MES生产订单, 工序工作流版本, V1 V2同名, 版本标签, 订单流程快照, 待备料, 权限复核

**需求场景 / 现象**: 在生产订单创建表单选择工序路线 `RTE-000001` 后，启用工作流选项显示“工序审批与备料 V2 · v1”和“工序审批与备料 V2 · v2”。版本尾码不同，但名称文本相同，用户容易选错。

**方案 / 实施步骤**:
1. 选择生产订单中的工序路线。
2. 打开工序工作流版本下拉菜单。
3. 核对 v1/v2 名称相同、版本尾码不同。
4. 保留未提交表单并退出，避免创建测试数据。

**验证方法**: 2026-10-19 使用管理员真实浏览器选择路线 `RTE-000001`；菜单分别显示“工序审批与备料 V2 · v1”和“工序审批与备料 V2 · v2”，随后取消新建表单，未写入业务数据。

**踩坑 / 已知异常与失败经验**: 根因：只能确认两个版本的名称字段在界面上均呈现同名，未读取底层配置确定写入来源。现有表单可用 v1/v2 尾码区分，临时操作需核对版本号；持久修复前需确认模块工作流版本编辑是否允许安全更改展示名，以及更名是否会影响已创建记录中的流程快照，本轮未修改配置。订单详情当前展示的是订单模块的 schema 版本，并不展示冻结的 `workflowVersion`，不能凭详情页或审计短 ID 推断订单实际快照版本；该配置只验证到待备料，没有报工、质检、完工证据，不能声称完整制造闭环已走通。

**关键文件与接口**: docs/design/LOWCODE-模块管理契约.md；本地管理端 `/app/production_order` 创建表单

**状态**: 部分完成（标签问题已复现并记录，持久修复未实施）

### P-20261027: Electron中用Vue弹窗替换不支持的prompt录入
**日期**: 2026-10-21
**项目**: EncoderPlotter_0903_01
**关键词**: Electron 28, prompt() not supported, Vue 2 弹窗, SN输入, IAP调试日志

**需求场景 / 现象**: IAP调试日志检索调用 `window.prompt()` 录入编码器SN，Electron 显示 `Error: prompt() is and will not be supported.`，用户无法检索日志。原因：浏览器原生同步 `prompt()` 不受当前 Electron 版本支持。

**方案 / 实施步骤**:
1. 用 Vue 条件模板替换 `window.prompt()`，渲染应用内 SN 输入对话框，确认后复用原有 IPC 查询并在同一弹窗列出匹配日志。
2. 空SN不关闭弹窗并提示（空值保留弹窗并重新聚焦）；用户选中文件后关闭弹窗，调用原有生成流程。
3. 限定键盘焦点：检索中禁止关闭，Tab/Shift+Tab 焦点循环留在弹窗；检索结束后聚焦首个结果或输入框，选择后生成完成再还焦点。

**验证方法**: `node --check components/share/iap-file-generator.js` 和 `git diff --check` 通过；搜索确认组件不再调用 `window.prompt()`。真实 Electron 窗口点击路径因缺少原生窗口交互工具未完成，标记 BLOCKED。

**踩坑 / 已知异常与失败经验**: `.device-setting-box-mixed div` 全局规则设置 `height:25px`，固定定位遮罩与内部对话框需显式设置视口/自动高度并用 `box-sizing:border-box` 限制短视口高度；检索期间不应允许关闭弹窗，否则返回的匹配结果会藏在已关闭弹窗中。

**关键文件与接口**: `components/share/iap-file-generator.js`（SN弹窗状态、聚焦、关闭、焦点循环和提交检索）；`components/share/iap-file-generator.html`（accessible dialog、输入框和操作按钮）；IPC `search-iap-debug-logs`（保持原有参数与行为）。

**状态**: 部分完成

### P-20261028: 禁用SN检索按钮的缺BIN提示与结果选中反馈
**日期**: 2026-10-21
**项目**: EncoderPlotter_0903_01
**关键词**: Vue, Electron, disabled button, title tooltip, SN检索, BIN文件, 单选

**需求场景 / 现象**: SN检索按钮缺少 BIN 时禁用；用户需要明确知道先选择 BIN。已有需求要求全量列出 SN 匹配日志，单选后生成。Chromium 禁用按钮自身通常不能接收悬停事件。

**方案 / 实施步骤**:
1. 将提示 title 放在禁用按钮外层 span 上，通过 pointer-events 让包装层接收悬停；BIN 已选时 title 为空。
2. 匹配结果全部列出，默认灰色，选中项切换主题色，短暂显示后关闭弹窗并调用既有生成流程。

**验证方法**: `node --check components/share/iap-file-generator.js` 和 `git diff --check` 通过；搜索确认无 `window.prompt`。缺少原生 Electron UI 交互工具，真实界面路径未验证。

**踩坑 / 已知异常与失败经验**: 需要在外层元素显示原生 title 时，将 title 放在可接收鼠标事件的包装节点，并在正常态清空 title。

**关键文件与接口**: components/share/iap-file-generator.js

**状态**: 部分完成

### P-20261029: SN检索需匹配日志相对路径
**日期**: 2026-10-21
**项目**: EncoderPlotter_0903_01
**关键词**: SN检索, IAP调试日志, kingkong.zip, Electron IPC, 相对路径, 离线IAP文件, 写入连接门禁

**需求场景 / 现象**: 按 SN 检索调试日志时只显示一条，但日志目录中可能有多个该 SN 的日志压缩包；同时需要在未连接读取器时使用文件选择、检索、生成和验证功能。根因：主进程 `search-iap-debug-logs` 递归目录，但只检查文件 basename 是否包含 SN；按 SN 分类的日志通常把 SN 放在父目录名，文件名不含 SN。

**方案 / 实施步骤**:
1. 在日志根目录递归读取目录项并筛选 `.kingkong.zip` 文件。
2. 对相对于日志根目录的完整文件路径（`path.relative(root, entryPath)`）做大小写不敏感 SN 子串匹配，按修改时间倒序返回所有匹配项。
3. 前端列表 `v-for` 完整呈现结果，单选一项后沿用既有生成流程。
4. 离线开放选择、检索、生成、验证；写入按钮和写入入口继续校验实际连接（当前设备对象和 target 存在）。

**验证方法**: `node --check main/file.js`、前端脚本 `node --check` 与 `git diff --check` 通过；三路独立复核通过。完整用户界面离线操作未实测，因为当前窗口已有连接读取器且不应为测试断开硬件。

**踩坑 / 已知异常与失败经验**: 仅查看basename会漏掉SN目录中的日志；检索集合已全量返回后，默认聚焦首条不代表仅返回一条。SN子串匹配可能会额外匹配SN相似的目录。

**关键文件与接口**: `main/file.js`（`search-iap-debug-logs` IPC）；`components/share/iap-file-generator.js`；`components/share/iap-file-generator.html`；`components/encoder/device.html`（离线时仍显示文件生成面板）。

**状态**: 部分完成

### P-20261030: IAP SN检索与断连写入门禁审查风险
**日期**: 2026-10-21
**项目**: EncoderPlotter_0903_01
**关键词**: IAP写入门禁, 设备断连竞态, doDisconnect, SN精确匹配, 子串搜索, 调试日志

**需求场景 / 现象**: 代码审查 IAP 调试日志按SN搜索与离线文件面板改动时，检查搜索候选是否只属于目标SN，以及设备断连时写入是否立即禁止。

**方案 / 实施步骤**:
1. 对 SN 搜索从任意路径子串改为明确的SN token匹配（目录名可精确相等，文件名按实际分隔符提取，保留大小写/安全文件名规范化兼容），并验证相似SN不互相命中。
2. 在断连开始到结束的整个窗口内设置并检查disconnecting状态：断连开始时将对应设备标记为disconnecting或先禁用其写入能力；按钮、`writeFile`、`_performWrite` 都检查该状态，断连完成/失败后清理标记。
3. 用连接、断连开始、断连完成、断连超时路径验证写入按钮和入口均拒绝操作。

**验证方法**: 静态独立审查识别两项P2风险。此记录是审查发现与修复建议，尚未实现或做硬件验证。

**踩坑 / 已知异常与失败经验**: 根因：搜索处理器对相对路径使用不区分大小写的子串 includes，短SN可命中较长SN。写入门禁仅检查Vuex设备对象及target；`doDisconnect` 先等待异步断连或2.5秒超时竞速，之后才从store删除设备，因此断连进行中门禁仍可通过。仅依据store仍存在的设备对象判断连接状态，不能覆盖异步断连窗口；路径级includes也不等同于SN精确匹配。

**关键文件与接口**: main/file.js:214（search-iap-debug-logs）；components/share/iap-file-generator.js:68（canWrite）、:457（writeFile）、:474（_performWrite）；controller/index.js:86（doDisconnect）

**状态**: 部分完成（待后续修复与硬件路径验证）

### P-20261032: IAP免标定全系列支持与算法版本边界
**日期**: 2026-10-21
**项目**: EncoderPlotter_0903_01
**关键词**: IAP免标定, recalibrationDataConversion, SUPPORTED_SERIES, SUPPORTED_VERSIONS, DPT15, V4065, 版本矩阵, Flash布局, storageTarget, IAP, 免标定, DPT, MPT, MPP, DPB, MPT-G, DPT-G1, MBS, MBP

**需求场景 / 现象**: 核对 IAP 后免标定对全部可再标定产品开放后，前后端是否兼容，以及尚存的产品系列、算法版本和目标 BIN 限制；避免在已有支持范围之外重复放宽限制。前端与 Python 转换算法各有一份白名单，容易误以为某系列未开放；只检查产品系列白名单不足以说明某个升级组合可执行。

**方案 / 实施步骤**:
1. 比较前端 `components/share/iap.js`（convertSupported）与后端 `recalibrationDataConversion.SUPPORTED_SERIES` 系列和算法版本白名单：均为 DPT(103)、MPT(104)、MPP(105)、DPB(106)、MPT-G(107)、DPT-G1(109)。
2. 常规转换仅支持源/目标算法版本 4020、4023、4050、4053、4060 的组合；4065 仅允许经完整身份核验的 DPT15（DPT系列，内圈15、外圈20、双圈且每圈9 Hall）。MBS/MBP不可再标定，不在此功能范围。
3. 核对转换器的产品身份、目标BIN布局和容量校验：转换输入系列须与编码器参数一致，目标BIN storageTarget系列和算法版本须与输出匹配，地址及生成数据还须通过目标布局/容量校验。
4. 对版本矩阵运行针对性测试；检查当前分支差异与 upstream 后再判断是否有改动可提交。确认产品范围为全部可再标定系列后，无需代码改动。

**验证方法**: 在 `controller/python` 执行 `py -3.12 -m pytest sub_algorithm/tests/test_conversion_series_matrix.py -q`，结果 235 passed；静态核对两处白名单均为 103、104、105、106、107、109。当前分支 `feature/iap-ota-sn` 与 `origin/feature/iap-ota-sn` 同步，工作树干净，因此本次没有可提交的代码改动。

**踩坑 / 已知异常与失败经验**: “全部可再标定系列开放”不等于删除算法版本、BIN布局、容量或DPT15校验；去掉其中任一后端校验都可能生成不兼容或无法写入的数据。不要仅移除前端系列过滤；后端转换仍要求六个受支持系列、当前 Q/T、匹配的目标数据布局及支持的源/目标算法版本。系列已全覆盖不代表任意固件版本、跨系列或任意BIN均可转换。

**关键文件与接口**: `components/share/iap.js:43`（UI系列与算法版本启用条件；4065限制为DPT15）；`controller/python/sub_algorithm/recalibrationDataConversion.py:26`（转换版本白名单、`SUPPORTED_SERIES`）、`:585`（4065的DPT15身份校验）、`:728`（目标storageTarget、series、版本和地址一致性校验）；`controller/python/sub_algorithm/tests/test_conversion_series_matrix.py`；`controller/python/sub_embedded/EncoderBase.py`（UNCALIBRATABLE_SERIES 标记 MBS/MBP）。

**状态**: 已完成

### P-20261033: MES 管理员可自批生产订单
**日期**: 2026-10-21
**项目**: MES / D:\code\mes
**关键词**: MES, 生产订单审批, 系统管理员, 自审批, 角色隔离, mock验收, 权限回归

**需求场景 / 现象**: 在 MES 当前 T07 v1 mock 业务流程中验证新建模块的完整链路。订单从 PRD 创建后提交审批，当前管理员会话可直接审批自己提交的订单。

**方案 / 实施步骤**:
1. 使用系统管理员身份登录演示 mock。
2. 创建生产订单并提交审核。
3. 在同一系统管理员身份下点击审核通过，观察状态进入待备料。

**验证方法**: 浏览器 UI 实际操作；生产订单审核后状态为待备料，证明系统管理员可自批。需补独立角色矩阵验证后才能确认授权隔离。

**踩坑 / 已知异常与失败经验**: 本次未检查源码，底层根因未知；暂无修复，后续需以独立业务角色执行审批并修正角色授权/动作可见性与服务端校验。账号 `admin/admin1111` 不属于本地 mock 登录凭据；页面提供 demo 登录账号。业务 demo 首次登录要求改密，未擅自操作凭据。

**关键文件与接口**: D:\sire\sire_ledger\runs\R20261021-172115-mes\evidence\MES-business-flow.md；本地 http://127.0.0.1:5173 mock 页面

**状态**: 部分完成

### P-20261034: 4k算法写入合并必须保留整批校验与目标布局
**日期**: 原记录未记载
**项目**: 原记录未记载
**关键词**: writeDataBlocks, writeEncoderDataV303, 4000, 5000, 写入日志, 整批预检查, IAP

**需求场景 / 现象**: 4000<=算法版本<5000提前进入独立命名块入口，原写入入口的日志和错误收尾被绕过。用户要求保留算法判定，将写入逻辑并入现有方法并核对漏项。任务前已有EncoderBase.py补日志和CHANGELOG改动，原件备份于当前台账，未提交代码。

**方案 / 实施步骤**:
1. 删除独立writeDataBlocks实现，将类型/完整性/容量验证、目标BIN优先、live布局比对、P/Q填充、T/M原始长度、P原始长度回退、调试数据保存与命名块顺序并入writeEncoderDataV303。
2. 普通writeEncoderData仍保留4k算法条件，转换命名块后进入V303。
3. 共用writeData局部函数、进度/重试、起始/成功/失败日志。
4. 错误通过write error及__cause__统一传递，finally清理storage target，包含dry-run及停止处理失败。历史算法保持原分支。
5. 仅P写入、PQTM版本及calculationVersion/IAP目标版本约束保留。

**验证方法**: 嵌入层181测试及4子测试通过；相关125项覆盖版本3999/4000/4999/5000、日志和回调、P-only、布局容量、raw/padded回退、dry-run、stop/write异常清理。独立R6审查通过，独立复跑82项通过。设备传输为mock；未进行真实设备擦写或UI验收，不能声称真机PASS。

**踩坑 / 已知异常与失败经验**: 算法子仓文档DATA_VERSION_CONVERSION.md仍引用旧方法，因归算法部门维护不直接修改，只登记同步项。IAP转换恢复矩阵结果另记台账。

**关键文件与接口**: controller/python/sub_embedded/EncoderBase.py；子仓tests/test_conversion_blocks.py、test_storage_layout_sources.py；主仓docs/anatomy.md

**状态**: 已完成（设备传输为mock，真机未验证）

### P-20261035: MES工序目录记录与工作流版本映射审查
**日期**: 2026-10-23
**项目**: MES / D:\code\mes
**关键词**: MES, 工序流程, 工序引用, catalog workflow, workflow version binding, 工序执行记录, workflowMode, route.steps

**需求场景 / 现象**: 静态审查平台模块管理的通用工作流能力及已配置的工序流程业务模块，判断流程定义、模块记录和工序执行数据之间是否闭环。

**方案 / 实施步骤**:
1. 分开审查模块结构配置、工作流版本定义和业务记录字段。
2. 对照运行时版本绑定代码确认流程版本作用范围。
3. 对照本机配置记录，判断节点动作是否有业务结果数据与前置校验。
4. 建议：把流程目录记录显式映射到可执行版本，并为每个执行节点配置通用的输入/结果关联规则，使其能校验结果存在后再允许流转；保留模块定义与工作流版本分离、记录绑定版本后固化流程快照的通用能力；不得写入业务专用系统代码。

**验证方法**: 只读检查源码、业务配置历史和有效设计口径；没有访问运行中实例，未做浏览器实操或测试。

**踩坑 / 已知异常与失败经验**: 根因：工序流程记录中的工序引用清单与目录模块的工作流版本是并列数据；订单关联具体流程记录后，版本选择仍按目标模块级别加载，没有按该流程记录约束版本。已记录的本机配置轨迹显示订单各节点仅允许修改备注，状态流转本身不要求提交节点结果数据。`route.steps` 的帮助文本明确该列表不代表流转顺序；若同时维护它和工作流节点，需明确哪个字段源是权威，避免漂移。历史知识曾记录同名版本，但当前表单标签会附加 `vN`，版本号可区分，名称仍不表达差异。

**关键文件与接口**: mes-server/src/lowcode/schema.ts:227；mes-server/src/lowcode/apps.service.ts:1509-1522；packages/runtime/src/lowcode/components/fields.tsx:520-529；docs/PROGRESS.md:462；docs/design/业务配置现行口径.md:17-20

**状态**: 部分完成（静态审查；真实环境版本、流程配置与节点数据仍需实测确认）

### P-20261036: PostgreSQL完整同步到测试环境的安全恢复与回退步骤
**日期**: 2026-10-23
**项目**: MES
**关键词**: PostgreSQL, 数据库完整同步, staging restore, 回滚, 密钥重加密

**需求场景 / 现象**: 用户要求以本机数据库完整覆盖远程测试库，同时保留测试环境管理员登录能力与可恢复路径。

**方案 / 实施步骤**:
1. 分别创建源库导出和目标库可恢复备份，并记录 SHA-256。
2. 将源数据导入临时目标库（staging），校验迁移、表、行数、内容摘要和敏感记录约束。
3. 仅在校验通过后切换数据库名，并保留旧目标库供回退。
4. 按目标环境密钥重新加密凭据记录（按用户标识读取明文后用目标密钥重新加密），验证解密后的用户指纹；管理员密码哈希按明确约束保留目标值。

**验证方法**: 45 张表的逐表行数和规范化内容摘要一致；管理员密码哈希保持同步前目标值；13 条密码保管记录均可用目标密钥解密且用户指纹匹配；目标备份校验和通过；数据库切换后四个测试容器状态为 healthy。证据见 `evidence/full-sync-verification.json`。

**踩坑 / 已知异常与失败经验**: 根因：测试环境保留了独立的管理员密码哈希和环境加密密钥；直接覆盖用户表会改变登录密码，直接拷贝密码保管密文则可能无法用目标环境密钥解密。首次 staging 验证假设密码保管表以错误列名关联，触发前置检查失败；目标库尚未切换且服务正常，确认实际 `user_id` 列后修正脚本重试。数据库 dump 不包含外部文件存储实体，本次未复制或核验上传文件实体。未执行业务页面功能测试，回滚演练也未执行。

**关键文件与接口**: evidence/sync-full-database.cjs；evidence/verify-full-sync.cjs；evidence/compare-content.cjs；evidence/full-sync-verification.json

**状态**: 部分完成（同步和数据库级核验完成；业务页面未测试）

### P-20261037: MES manual business and admin separation
**日期**: 原记录未记载
**项目**: MES / D:/code/mes
**关键词**: MES、使用手册、小白版、业务系统、后台管理、DOCX、SN、流程快照, build-manual-v2.cjs, schema.referenceOnly

**需求场景 / 现象**: 用户要求接续Claude编写的半成品使用说明，保持原来的章节、截图、表格与小白读者口吻，并明确区分业务系统和后台管理系统的操作。

**方案 / 实施步骤**:
1. 在原A/B章节生成器中插入补充章节挂钩，分为业务系统操作、后台管理系统操作、公共查阅三部分。
2. 逐个模块按schema.referenceOnly标记后台维护或业务使用入口。
3. 补充审批、来料冻结复检、首件退回与多次返工、SN硬件编码更正，以及审计筛选、行为分析、配置体检、集成身份创建和密钥轮换。
4. 工单新建时先选工序流记录，再选启用版本；两项不选时采用模块本身流程。

**验证方法**: 原生成器成功输出更新DOCX，ZIP完整性和XML解析通过，新增章节全部存在，包含26张图片，无缺图提示或占位。独立代理审核源码及操作准确性。

**踩坑 / 已知异常与失败经验**: SN模板长度为17加产品型号长度，DPT15示例22位，不应统一写23位。运行bundled render_docx.py因未安装bundled LibreOffice失败，不能宣称分页或配图视觉验收通过；没有改业务代码，没有运行会重置数据库的测试。

**关键文件与接口**: D:/code/mes/docs/manual/build-manual-v2.cjs、manual-chapters-a.cjs、manual-chapters-b.cjs、manual-completion.cjs；依据mes-db/zx07/modules.mjs、workflows.mjs以及后台各页面源码

**状态**: 已完成

### P-20261038: MES通用字段拼接、测试部署与SN原文归档
**日期**: 2026-10-22
**项目**: MES (D:/code/mes)
**关键词**: MES, lowcode, concat, SN, Feishu, 测试部署

**需求场景 / 现象**: 用户明确要求自定义模块通用字段拼接，不应固化SN业务规则；完成后部署测试服、不深度测试。追加将飞书《编码器追溯系统》整理为标题SN的项目Markdown。

**方案 / 实施步骤**:
1. text.config.concat 配置有序来源字段和分隔符；前后端共用纯函数计算，服务端忽略客户端派生值并重算。
2. 部分更新合并原数据后执行必填/长度/唯一检查；拒绝循环、归档来源、默认值和自动编号冲突。
3. 设计器与运行表单显示只读预览。
4. 原文归档区分正文/画板/评论和未决项，保存四张原图不依赖外部临时链接。
5. 授权部署测试服。

**验证方法**: 59项相关服务端单测通过，admin/web类型检查和三端构建通过；独立代码审查完成。授权部署r20261022-concat成功且数据计数未变，保留DB/config备份；后续其他发布已升级到erp3，未覆盖。无深度集成/E2E；UI仅部分冒烟，未声称完整路径通过。SN文档8章节4原图引用全部验证，独立阅读原图复核两流程顺序。记录位于D:/sire/sire_ledger/runs/R20261022-113015-mes/validation.md。

**踩坑 / 已知异常与失败经验**: 无深度集成/E2E；UI仅部分冒烟，未声称完整路径通过。

**关键文件与接口**: D:/code/mes/mes-server/src/lowcode/field-composition.ts；D:/code/mes/mes-server/src/lowcode/schema.ts；D:/code/mes/mes-admin/src/lowcode/designer/FieldProperties.tsx；D:/code/mes/packages/runtime/src/lowcode/schema-utils.ts；D:/code/mes/docs/SN.md；D:/code/mes/docs/PROGRESS.md

**状态**: 已完成

### P-20261039: MES模块空框与订单SN工序静态适配缺口
**日期**: 2026-10-22
**项目**: MES (D:/code/mes)
**关键词**: MES, 模块空框, 订单导入, workflowBindings, linkRange, SN, 工序流程, 配置漂移

**需求场景 / 现象**: 用户确认只清空业务模块页面内容，保留菜单、路由、框架，并分析订单、SN、工序、维护、兼容能力。

**方案 / 实施步骤**:
1. 两个前端 /app/:code 和后台工作流子路由替换空框；原引擎及业务数据保留。
2. 工作流标题使用独立 overview 接口，避免误依赖模块 view 权限（独立静态复核发现权限问题并修复）。

**验证方法**: 独立 R6 静态复核完成。未测试、未构建、未部署，待用户授权测试。证据 D:/sire/sire_ledger/runs/R20261022-202240-mes/r6a.md。

**踩坑 / 已知异常与失败经验**: 结论：importRecords 没有 createRecord 的 workflowBindings 及 linkRange 路径；默认 SN 从批次生成，数量 1 表示单个，数字后缀不跨 999。ZX07 默认工作流尚未采用平台已有的 coverRelated，而进度记录中的服务器配置已启用该规则，存在重应用配置漂移风险。工序流记录与模块级版本归属脱节，报工缺单件工序执行和数量质量闭环。分析基于默认源码，未核对服务器实际配置。

**关键文件与接口**: D:/code/mes/docs/reviews/2026-10-22-模块清空与业务适配分析.md；D:/code/mes/packages/runtime/src/lowcode/pages/ModuleShellPage.tsx；D:/code/mes/mes-server/src/lowcode/apps.service.ts

**状态**: 部分完成

### P-20261040: MES平台定义执行与依赖治理方案静态审查缺口
**日期**: 原记录未记载
**项目**: MES / D:/code/mes
**关键词**: MES, 工作流运行时, 依赖治理, 提供者绑定, 审批状态机, 并发锁, 待办分页, execProcess, impactOf, workflowView

**需求场景 / 现象**: 分析v0.1平台改造草案是否具备实施条件（只读分析方案与当前源码；不修改项目、不执行测试）。结论：方向成立，v0.1尚不足直接执行。

**方案 / 实施步骤**:
1. D0确认基线。
2. 先冻结运行时、状态机、依赖锁与身份契约，再按1→2→3推进。
3. D1暂不支持、D2交集、D3新运行生效、D4默认提供者均可采纳，须补兼容与切换规则。

**验证方法**: 仅文档与源码静态交叉检查，未测试；无Git操作。R6独立复核：确认流程库选择、审批状态机、多出口权限、运行快照四项缺口。

**踩坑 / 已知异常与失败经验**: 主要缺口：(1)execProcess多提供者缺启动选择契约，需模块+记录+版本身份；(2)待审批状态遗漏submitOperation、改派、重复完成、驳回与取消状态机，须冻结并幂等；(3)actorRoleCodes为流转级，派工为节点级，明确多出口并集/交集和终点权限；(4)依赖现场扫描须覆盖运行快照、历史版本、停用模块及动态默认绑定，定义静态边和运行边生命周期；(5)impactOf需纳入写事务并与引用创建共享锁、删除停用排他锁成对，稳定锁序并锁后重读；(6)待办已有workflowView终判，SQL粗筛后limit501，放宽粗筛会使前500条占满后漏掉合法待办，须游标扫描补足与可解释total/truncated；(7)提供者编码快照不足，运行中的org、materialNeeds等全部从run解析，并明确schema版本与业务数据实时/快照边界；(8)字段依赖身份应含moduleId+fieldKey，版本应含moduleId+version，生产stepCode还需提供者作用域；(9)文本扫描业务字段名误报name/status等通用标识，建议AST上下文约束和业务包改名不变性用例；(10)保存/发布一致拒绝与U1.6显示不生效相冲突，草稿诊断/发布阻止边界需明确。检索复用：P-20261020、P-20261024。

**关键文件与接口**: D:/code/mes/docs/design/PLATFORM-定义执行与依赖治理改造方案.md；mes-server/src/exec/exec.service.ts；mes-server/src/lowcode/apps.service.ts；mes-server/src/lowcode/modules.service.ts

**状态**: 已完成

### P-20261041: Unity 6原生像素野外角色图集与3D战斗隔离
**日期**: 2026-10-25
**项目**: GAME / D:\code\GAME
**关键词**: Unity 6, 2.5D像素角色, Sprite atlas, SpriteRenderer, SubsystemRegistration, contact shadow, 野外角色, ImageGen

**需求场景 / 现象**: 在3D场景中呈现复古像素风野外人物，同时保留独立的3D战斗人物模型。

**方案 / 实施步骤**:
1. 固定 atlas row/column 语义及颜色、像素尺寸、PPU（通过Unity C#按固定像素块程序化生成RGBA32 Sprite atlas，按4向×4动作格切片）。
2. 用单一模块拥有并释放运行期纹理/Sprite缓存（阴影Sprite由atlas模块共享缓存，视觉驱动只引用）。
3. 让场景呈现层（field-only SpriteRenderer，相机水平基向量决定朝向行）消费 Sprite，不改战斗资源加载路径和控制输入；战斗系统继续加载GameObject预制体。

**验证方法**: 先做静态检查，包括 atlas索引/裁切、filter/mipmap、相机行选择、缓存生命周期和战斗文件集差异；有明确授权后再在Unity现场校准像素比例、ground offset和透明排序。本次静态审查通过；Unity运行、构建和测试均未执行。

**踩坑 / 已知异常与失败经验**: ImageGen接口返回404时可使用Unity原生确定性像素绘制作为可复现素材替代；该方案的造型细节有限，需实机观感迭代。接触影水平旋转需以角色地面位置为参照校准。

**关键文件与接口**: UNITY/Assets/Scripts/Presentation/Field/FieldPixelCharacterAtlas.cs（128x128、16格32x32；ContactShadow缓存与SubsystemRegistration清理）；FieldPixelCharacterVisual.cs（row*4+column帧映射）；FieldCharacterVisualDriver.cs

**状态**: 部分完成（像素野外角色实现和静态审查完成，待Unity测试授权及外观校准）

### P-20261042: Unity 3D城镇NPC像素色板图集与交互保留
**日期**: 2026-10-26
**项目**: GAME / D:\code\GAME
**关键词**: Unity NPC sprites, pixel palette variants, Texture2D atlas cache, billboard direction, FC town NPC, C# generated pixel character

**需求场景 / 现象**: 在3D城镇中统一呈现玩家提供参考图风格的像素人物，同时保留可交互NPC的剧情、提示和位置行为。

**方案 / 实施步骤**:
1. 维护一个基础角色形状，按可识别ID重映射衣裤/发色和少量头部像素饰件（稳定character id映射到少量复用色板）。
2. atlas纹理/Sprite按look仅创建一次，视觉驱动不复制资源（每种色板延迟生成4方向×4帧运行时atlas）。
3. 在人物创建工厂（FcWorldBuilder）保留互动host并替换其渲染子节点；静态NPC用专用SpriteRenderer驱动，缓存原始面向向量，再按当前相机水平基选择方向idle帧并billboard。

**验证方法**: 静态检查角色ID映射、图集索引、相机四向、共享缓存生命周期、Person行为与战斗资源隔离。R6静态复核通过；未运行Unity、构建、截图或测试。需要授权后的现场测试检查比例、标牌高度、方向、阴影和各NPC像素辨识度。

**踩坑 / 已知异常与失败经验**: 更换成人物高度较低的Sprite后，旧3D角色标牌会悬空，应只调整name sign锚点、保留其host关联。billboard旋转会覆盖视觉transform朝向，NPC必须单独缓存方向向量。

**关键文件与接口**: UNITY/Assets/Scripts/Presentation/Field/FieldPixelCharacterAtlas.cs（FramesFor(characterId)、色板look缓存、ResetCaches()）；FieldNpcPixelVisual.cs；UNITY/Assets/Scripts/FC/FcWorldBuilder.cs（Person）

**状态**: 部分完成（FC城镇Person工厂NPC接入像素版；未覆盖所有NPC、队友跟随和完整配件，待实机校准）

### P-20261043: 32x32 NPC像素身份配件与侧向镜像
**日期**: 2026-10-26
**项目**: D:/code/GAME
**关键词**: Unity NPC像素附件, 32x32 sprite atlas, side view mirror, medical bag cross, Rect clamp, pixel accessory

**需求场景 / 现象**: 在已有32×32逐朝向NPC角色图集上增加工具袋、医疗包、背包和工装条，同时保留人物轮廓、帧索引及既有行为边界。

**方案 / 实施步骤**:
1. 按朝向列出每个look的包体锚点与尺寸。
2. 使用`Rect`写入边框、内衬和少量高亮色块，所有图形留在32×32格内（所有矩形继续使用单格Rect裁切）。
3. 正反方向分别绘制配件；侧向row3在基础人物翻转后单独计算镜像锚点 `CellSize - rowTwoX - width`，并核对基础翻转顺序。红十字从药包锚点和宽度派生，使标志落在包内。
4. 先做静态坐标/边界/重叠复核；Unity视觉效果仍需另行授权后校准。

**验证方法**: 本次静态审查确认坐标、十字包内、x=21留白、row3镜像及32×32边界；未执行Unity、构建或测试。后续需逐帧实机查看像素可读性。

**踩坑 / 已知异常与失败经验**: 只检查静态正面帧会漏掉走帧手臂向内移动导致的附件重叠。正面附件需对照最宽动作帧的手臂像素留出至少一列空白，按最不利动作帧测算手臂边缘，可避免压住角色轮廓。

**关键文件与接口**: UNITY/Assets/Scripts/Presentation/Field/FieldPixelCharacterAtlas.cs（DrawRoleProps、DrawMedicalBag、SideX）

**状态**: 已完成静态实现；运行时美术校准待授权

### P-20261044: FC旅店切面房间：可走净宽与玩法边界
**日期**: 2026-10-26
**项目**: D:/code/GAME
**关键词**: Unity切面室内, FC旅店, procedural room builder, collider-free art, spawn clearance, 端柱净宽, scene root cleanup

**需求场景 / 现象**: 在既有Unity俯视角色扮演游戏中，按参考图扩展一间切面旅店：木地板、锈蚀钢板、左右客房与前厅，外门廊对齐场景入口；需要改善可读性，同时避免改动旅店传送和住宿玩法。

**方案 / 实施步骤**:
1. 先写清单元写集和玩法边界，只触碰房间美术Builder；将新房间几何、材质和纹理限定在单一美术Builder中，挂到专用scene art root，并由root生命周期释放资源。
2. 以墙段间距确定门洞，再将门框/门扇放入门洞并计算最窄内沿净宽；确认装饰Collider关闭（门框、门扇、装饰栏杆与门廊铺面不参与碰撞）。
3. 用实际端柱内沿检查外廊通道宽度，并核对入口与Spawn水平位置对齐；保持Portal/Spawn及住宿服务的水平坐标与行为不变，既有TerrainHeight仅调整Y并予以保留。
4. 检查桌椅与出生点净距、床/柜相交、生成对象root归属及Material/Texture释放。
5. 先完成静态坐标与代码审查；运行时画面、性能和构图需要单独授权后确认。

**验证方法**: 本次静态审查确认门洞净宽约1.68m、门廊端柱内沿净宽约2.98m、圆凳至出生点外缘约1.034m，静态对象估算486个；R6A/B/C独立审查及交叉复核通过。未运行Unity、构建或测试，因此数值和构图仍需在授权后的运行时画面确认。

**踩坑 / 已知异常与失败经验**: 前栏两段的中心端点看似留有2.8m间隙，但端柱各向通道内伸0.06m，实际仅2.68m。要按端柱内沿计算，并把侧栏角柱与前栏端柱明确对齐；修改几何后也同步更新自检与评审报告，避免旧静态数字和新代码并存。

**关键文件与接口**: UNITY/Assets/Scripts/Presentation/FC/FcRadoInnArtBuilder.cs（BuildRoom、BuildExterior、RoomPartitions、OnDestroy）；UNITY/Assets/Scripts/Presentation/FC/FcWorldBuilder.cs（AlignLogicSpawnsAndTriggers）

**状态**: 已完成静态实现与独立复核；运行时视觉/性能验证待授权

### P-20261045: Unity原创芯片主题曲资源与稳定Meta生成
**日期**: 2026-10-26
**项目**: D:/code/GAME
**关键词**: Unity原创芯片音乐, AudioDirector MusicCue, Resources AudioClip, PCM WAV, determinisic music generator, AudioImporter meta, 8-bit chiptune

**需求场景 / 现象**: Unity项目已有事件驱动AudioDirector和十个MusicCue，但Resources没有正式曲目；临时运行时音符生成能验证接线，却没有各场景可辨识的原创主题和一套可反复编修的音乐资产。

**方案 / 实施步骤**:
1. 从枚举导出所有音乐cue，分类循环曲与一次性事件曲。
2. 每个cue手写主题短句、速度、调式、和声和配器，使用八分音符片段拼出A/B段及回归；不抄录商业原曲旋律/录音。
3. 以整小节计样本长度，使用短起音/释音与边界fade控制点击爆音，以pulse/triangle/noise合成单声道PCM WAV；七首32小节循环曲（A/B/主题返回），胜利/失败/住宿使用短非循环段落。
4. 将Resources命名与cue保持逐字一致（Resources/Audio/Music/<MusicCue>.wav）；Unity meta用Assets相对路径派生稳定GUID并严格限制在Assets导入根内，folder meta从 `UNITY/Assets` 推导并保留已有GUID。
5. R6静态核对WAV头、帧数/BPM、资源路由、meta和文案；最终音色、循环缝、平台内存须在授权后的Unity听审验证。

**验证方法**: 本次静态检查十首WAV均为22050Hz、mono、16-bit PCM，名称与10个MusicCue匹配；七首循环曲32小节，三首短曲4/4/8小节；10个AudioImporter meta与GUID唯一且位于Assets内。R6A/B/C独立复核与交叉核验PASS。未运行Unity、构建、播放或测试，不能据此断言最终听感通过。

**踩坑 / 已知异常与失败经验**: R6发现Dungeon文案写了金属噪声但配器未实现、Rest说回主音却以2级旋律/非主音和弦结束；修正实际音符数据比仅改文案可靠。初始meta代码从项目根开始走目录树，会生成 `UNITY.meta` 与 `UNITY/Assets.meta` 这类Assets导入根之外的文件。静态核对主题描述必须与代码实际使用的噪声、和弦和终止音一致。

**关键文件与接口**: tools/generate_fc_inspired_ost.py；UNITY/Assets/Resources/Audio/Music/<Cue>.wav；UNITY/Assets/Scripts/Presentation/Audio/AudioDirector.cs（先加载 `Resources.Load<AudioClip>("Audio/Music/" + cue)`，缺失再走占位合成）；UNITY/Assets/Scripts/FC/FcTitleScreen.cs

**状态**: 部分完成（原创音乐首版已生成并静态复核；Unity导入与听感验收待授权）

### P-20261046: FC游戏UI参考风格确认与标题宽屏版式修正
**日期**: 2026-10-26
**项目**: D:/code/GAME
**关键词**: 重装机兵UI, 旧钢暖木界面, Unity CanvasScaler, ultrawide title layout, UI style confirmation, ScreenMatchMode.Expand

**需求场景 / 现象**: 用户确认游戏第二步做界面UI，并给出高位斜俯视室内参考图，明确要求采用该风格（旧钢框、暖木交互区、暖纸文字、少量黄铜焦点，已应用到标题、野外HUD、菜单、地图、对话及战斗界面）。静态审查发现标题页面按宽度缩放导致超宽启动窗口的纵向内容溢出，且木选项板曾宽于内衬边界。

**方案 / 实施步骤**:
1. 查阅 ART_BIBLE 与 UI 代码，确认该风格已经覆盖主要屏幕；沿用 `RetroUiTextures`/`WornUiSurface` 的单一木钢主题来源，不创建第二套皮肤。
2. 标题界面使用 CanvasScaler `ScaleWithScreenSize` + `ScreenMatchMode.Expand`，由短边决定比例；选项板与文本框均为740逻辑单位宽，限制在806宽木内衬范围。
3. 静态复核后，修正标题宽屏纵向溢出并收窄超出内衬的选项板。
4. R6A/B/C独立复核及交叉核验通过；不执行Unity/构建/测试。

**验证方法**: `git diff --check -- UNITY/Assets/Scripts/FC/FcTitleScreen.cs` 通过；静态几何核算1360×765参考下内衬宽约806、选项板740、两侧余量33；3440×1440下Expand逻辑画布约1828×765，末行板底614、提示底705，均在内衬内；1024×768逻辑画布约1360×1020。R6A/B/C全PASS。未实机验证纹理、字体/对比度、低分辨率效果和用户输入；R7因待用户授权记为DEFERRED。

**踩坑 / 已知异常与失败经验**: 需将Expand配置在`CanvasScaler.screenMatchMode`（`ScreenMatchMode`），不能赋给`uiScaleMode`；选项板要与内衬相比，而不是只看自身锚点。极低分辨率下实际字号和纹理仍待运行时检查；普通存档行预计在740宽文本框内，超长或手改savedAt可能换行裁切。

**关键文件与接口**: docs/ART_BIBLE.md；UNITY/Assets/Scripts/UI/RetroUiTextures.cs；UNITY/Assets/Scripts/Presentation/WornUiSurface.cs；UNITY/Assets/Scripts/FC/FcTitleScreen.cs；FieldUiPresentation.cs、Menu/FieldCommandMenu.cs、FcDialogue.cs、Battle/BattleController.cs

**状态**: 部分完成（UI主题静态覆盖确认，标题版式静态修正完成；Unity实机画面与输入验收待授权）

### P-20261047: GAME FC重制设计文档正典与状态统一
**日期**: 2026-10-26
**项目**: D:/code/GAME
**关键词**: Unity FC重装机兵3D重制, GDD正典, 设计文档对齐, 盐海旧稿归档, 音频状态, 视觉候选边界

**需求场景 / 现象**: 项目已将故事基线转向FC初代3D重制，但旧GDD仍写原创盐海三幕；INTERFACE中I-18/I-25/I-26和ART_BIBLE室外词汇也容易被当成现行FC内容。FC_REMAKE还把已有原创WAV主素材描述为临时合成，未区分资源、路由代码与实机验收。

**方案 / 实施步骤**:
1. 以GDD定义产品方向和跨域验收原则；STORY、FC_REFERENCE、AUDIO、ART_BIBLE、FC_REMAKE分别承担领域细化/状态。
2. INTERFACE的旧剧情条款明确归档并说明✅只代表技术约定认可。
3. 美术候选必须由FC_REFERENCE核实后进入世界正典。
4. 音频如实区分10 MusicCue/19 SFX WAV已生成、AudioDirector加载/路由代码已接入、Unity导入与听感未验收。

**验证方法**: R6A/B/C独立静态审查及交叉核验全部PASS；检查链接、盐海旧条款、六域状态、音频资源数/路由/未实测状态。未运行Unity、构建、游戏、测试或音频播放。

**踩坑 / 已知异常与失败经验**: 根因：产品方向迁移只更新了部分领域文档，缺少总GDD及跨文档生命周期/状态口径；代码/文件存在、技术约定获认可和内容进入正典这三者混在一起。INTERFACE里的✅仅代表过去的接口口径认可，可能被误读为内容正典；历史实现记录也不能替代当前实机验收。ART_BIBLE颜色/资产候选不可自行推导原作地点或设施。

**关键文件与接口**: docs/GDD.md；docs/FC_REMAKE.md；docs/INTERFACE.md；docs/ART_BIBLE.md

**状态**: 已完成（总设计文档正典和领域状态口径已对齐；全游戏内容、Unity运行验收和发行授权仍未完成）

### P-20261048: Unity队伍菜单复用FC像素人物帧作为角色头像
**日期**: 2026-10-26
**项目**: GAME / D:/code/GAME
**关键词**: Unity队伍菜单, Party menu, 像素头像, FieldPixelCharacterAtlas, FramesFor, CHR_Mechanic, CharacterLook, UGUI Image

**需求场景 / 现象**: 队伍菜单已有文字列表和统一木钢主题，但队员项没有人物识别图像，UI无法复用场景人物的像素身份。根因：`FieldCommandMenu` 的通用 `Command` 数据只含文本、动作和启用状态；现有 4×4像素帧图集虽提供 `FramesFor(characterId)`，却没有队伍角色的头像 look 映射入口。

**方案 / 实施步骤**:
1. 使用Command的可选图标字段（可选 Sprite icon），不触碰菜单状态和Action。
2. 仅 Party 成员项从共享 `FieldPixelCharacterAtlas.FramesFor(id)[0]` 绑定图标，为有头像项建立32×32图像并给文字留位，关闭射线命中（Raycast），由原整行命令底板继续响应鼠标；无图标命令保留原内边距。
3. 将Sprite名称纳入命令列表重建签名，避免动态变化时保留旧图。
4. `ResolveLook` 显式把 `CHR_Mechanic` 与场景 NPC ID `NPC_FC_Mechanic` 指向同一个机械师 look。缓存通过现有图集类按 look 首次懒初始化一次，不在菜单行创建纹理/精灵。

**验证方法**: R6A/B/C独立静态复核及交叉核验通过。确认猎人走默认look、机械师映射正确、头像布局及原有整行点击不变。因用户未授权，未运行Unity、构建或测试；头像画面和操作待授权后实测。

**踩坑 / 已知异常与失败经验**: 当前队伍 ID 是 `CHR_Mechanic`，不是场景 NPC ID `NPC_FC_Mechanic`；若只复用NPC映射，招募到的机械师会显示成默认猎人。对缓存要求需区分“帮助类首次懒创建并缓存”与“菜单行重复创建”，前者是已有设计，后者才应禁止。

**关键文件与接口**: UNITY/Assets/Scripts/Presentation/Menu/FieldCommandMenu.cs；UNITY/Assets/Scripts/Presentation/Field/FieldPixelCharacterAtlas.cs；docs/ART_BIBLE.md

**状态**: 部分完成（代码和规范静态复核通过；Unity视觉和输入实机验收待用户授权）

### P-20261049: Unity预备队存档与战车归属重建
**日期**: 2026-10-26
**项目**: GAME / D:/code/GAME
**关键词**: Unity, PlayerState.reserveParty, vehicleId, TankLoadout, VehicleRecord.assignedCharacterId, SaveData v9, roster swap

**需求场景 / 现象**: 为队伍上限固定的RPG增加持久预备队与可逆换位时，活动队伍角色拥有战车引用，离队角色不能保留同一战车；存档还要容忍旧版或损坏数据中的残留引用。

**方案 / 实施步骤**:
1. 将预备队无车设为双向序列化不变量：写reserveParty时清空vehicleId、hasTank、tank和inTank；读取时无条件清掉reserve成员tank、inTank、tankAway，忽略不合法的旧关联。
2. `VehicleService.Normalize`保留车辆数据、位置与停放状态，先清空assignedCharacterId，再仅按活动party里的TankLoadout引用重建车辆owner。
3. 队伍换位先把活动槽位TankLoadout和乘车状态交给换入角色，再调用Normalize；成长、HP与装备继续随Combatant对象保存。

**验证方法**: R6A/B/C独立静态复核和交叉核验通过；检查v8及更早版本迁移、reserve字段清零、活动owner重建及车辆记录保留。未运行Unity、构建或测试；实机换位/存档循环待用户授权。当前接口条款I-29仍待双方认可，该实现处于待签核方案，不应视为共享接口已生效。

**踩坑 / 已知异常与失败经验**: 根因：CombatantSave会同时保存嵌套战车与独立vehicleId；仅在队伍服务里清空离队角色不够，旧存档/异常运行态可在读档时重新让预备队员占有战车，VehicleRecord还可能残留旧的assignedCharacterId。清理reserve Combatant的tank字段仍不够，对应VehicleRecord.assignedCharacterId也要从活动队伍重建；运行时活动队伍不能简单把战车卸掉再换位，否则会改变停放、回收与上车行为。

**关键文件与接口**: UNITY/Assets/Scripts/Core/Save/SaveSerializer.cs；UNITY/Assets/Scripts/Tank/Runtime/VehicleService.cs；UNITY/Assets/Scripts/Progression/PartyService.cs

**状态**: 部分完成（代码静态复核通过；I-29接口认可和测试授权待处理）

### P-20261050: GAME待办盘点：区分实现、原版依据和验收状态
**日期**: 2026-10-26
**项目**: GAME / `D:\code\GAME`
**关键词**: GAME, FC remake, 未完成任务盘点, GDD, FC_REMAKE, FC_REFERENCE, INTERFACE, 原版核验, 静态实现, 实机验收, DEFERRED

**需求场景 / 现象**: 用户要求汇总“还有哪些任务没有做完”。项目状态分散在总设计、实现边界、原版对照、音频、接口合同和近期交付台账中。代码/资源存在不能证明游戏流程可用，原版待核也不能等同于实现未完成，用户未授权的验证必须保持DEFERRED。

**方案 / 实施步骤**:
1. 搜索五类正典文件中的“仍需交付/待核/待授权/未完成”：先以GDD §5、FC_REMAKE“仍需交付”为总体分类；用FC_REFERENCE核对原版未对齐项、AUDIO核对音频验收、INTERFACE核对未签核依赖。
2. 用近期台账补入刚做完但没实测的事项。
3. 按“实现、依据、验收、跨团队签核”分类，明确证据来源和风险（最终分为：可玩闭环实测、正典依据、系统/内容实现、资产表现验收）。
4. 把清单标成文档快照，不推断排期或完成百分比。

**验证方法**: 本轮逐项读取上述文档、检查I-24/I-29原始签核状态，并查阅最近三轮SIRE台账。结果记录于 `D:/sire/sire_ledger/runs/R20261026-215151-game/unfinished-tasks.md`。没有运行游戏或测试。

**踩坑 / 已知异常与失败经验**: 根因：各文件职责不同：GDD列产品领域目标，FC_REMAKE记录当前实现与长期缺口，FC_REFERENCE记录依据与未对齐事实，AUDIO和INTERFACE分别记录子系统边界与签核状态，SIRE台账记录近期证据；单读一个文档或用工作区状态推算百分比会混淆计划、静态实现和实测结果。历史上已跑过部分路线（如2026-10-25战狗/首车片段），但近期改动后的存档、旅店、UI仍未运行；不得把旧实测外推到新代码。接口表列为“已认可”也不表示对应内容符合FC正典。不要给未有证据支持的完成百分比。

**关键文件与接口**: docs/GDD.md；docs/FC_REMAKE.md；docs/FC_REFERENCE.md；docs/AUDIO.md；docs/INTERFACE.md（I-24/I-29）；D:/sire/sire_ledger/runs/<RUN_ID>/

**状态**: 已完成（一次只读盘点；持续状态应重新查当前文档与台账）

### P-20261052: 经明确授权补齐历史更新日志分类（改工作区日志不会重写历史tag/不重发飞书）
**日期**: 2026-10-26
**项目**: driverSoftware
**关键词**: CHANGELOG, 历史版本, 分类修复, 新增, 修复, fb9f1499

**需求场景 / 现象**: 用户明确授权后，要把未发布的 Kt 修复和 v0.20.3~v0.20.5 历史条目按新 CHANGELOG 规范补分类（通知解析需要新增/修复分类）。前两轮因范围约束未改历史段落。

**方案 / 实施步骤**:
1. v0.20.5 的固件 v3.4.10 支持归“新增”，保留空“修复”分类。
2. v0.20.4 和 v0.20.3 条目归“修复”，保留空“新增”分类。
3. 当前未发布的 Kt 条目已有新增/修复模板，无需移动。
4. 仅补分类，不重写条目、不改日期和所属版本。

**验证方法**: 读取原文件与 git diff，确认仅增加 9 行标题和分隔空行、原有条目不变；git diff --check 无问题。本轮未授权测试，未运行测试、发布或发送消息。

**踩坑 / 已知异常与失败经验**: 历史条目平铺缺少通知解析所需分类是根因；修改工作区日志不会自动重写历史 tag，也不会重发原飞书消息。

**关键文件与接口**: CHANGELOG.md 的未发布、0.20.5、0.20.4、0.20.3 段落

**状态**: 已本地提交 fb9f1499，未推送；未测试

### P-20261056: FC风格野外战车牵引与拖车存档
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: FC重装机兵, 野外战车牵引, 拖车, SaveData v10, VehicleService.AttachTow, stale callback, Game.Runtime与Game.FC解耦, FieldEvents

**需求场景 / 现象**: 在 FC 风格 Unity 重制中补齐野外靠近停放战车并确认牵引、随车移动、下车脱钩的纵切片，同时排除拖车的战斗参与并保存牵引关系。

**方案 / 实施步骤**:
1. 将主车和拖车身份保存为显式 ID，不依赖队伍首位角色推断来源车。
2. 接受交互前和延迟确认后重复检查场景、距离、车辆可移动性、停放/占用状态及单拖车容量。
3. 使用通用 FieldEvents 请求 UI 确认，由 FC 表现层订阅；UI 无法弹出时回调取消。
4. 移动和保存时同步拖车位置；显式下车/切换主车时将拖车停在主车后方；修复无效存档关联时清除关联并保留拖车的最后存档位置。
5. 升级 v10 并在战斗自动登车流程中排除拖车。

**验证方法**: 本次只完成代码静态追踪和三路独立静态审查；没有运行测试、构建或 Unity。获授权后应实际验证确认/取消、跨场景存读档、同车换司机、不同车切换、下车脱钩、战斗胜利/逃跑/失能、旧 v9 存档迁移和异常关系恢复。

**踩坑 / 已知异常与失败经验**: 根因：既有车辆服务只支持车库回收，没有野外实体之间的牵引关系；野外控制器按当前在车角色同步，战斗初始化也会把所有非停放车辆视为乘员战车。牵引期间不能每帧用“首位在车队员”推断主车，否则队伍顺序或另一辆车会污染同步来源。FC 对话的 Choose API 在 UI 缺失/已有对话时会直接返回，因此请求处理器必须先检测并完成 false。修复非法关系时保留拖车最后存档位置；正常下车/切车路径显式重新定位。

**关键文件与接口**: UNITY/Assets/Scripts/Tank/Runtime/VehicleService.cs（CanAttachTow、AttachTow、ActiveDriver、SyncTrailer、DetachTow）；UNITY/Assets/Scripts/Field/FieldPlayerController.cs（RequestTow）；UNITY/Assets/Scripts/FC/FcDialogue.cs；UNITY/Assets/Scripts/Core/Save/SaveSerializer.cs；UNITY/Assets/Scripts/Core/GameSession.cs

**状态**: 部分完成（代码和静态复核完成；FC指定版本实机校对及运行验收未完成，待用户授权测试）

### P-20261059: FC租赁战车状态、收益与受损退租
**日期**: 2026-10-27
**项目**: GAME / D:/code/GAME
**关键词**: FC租赁战车, rental tank, VehicleRecord.isRental, battle gold multiplier, SaveData v11, 自动退租, DetachTow, 租车装甲补充

**需求场景 / 现象**: FC风格Unity重制需要租赁战车；除租还菜单外，还要贯通固定配置、收益扣减、战斗损坏、车辆牵引和存档恢复。

**方案 / 实施步骤**:
1. 让租赁状态跟随VehicleRecord而非单独维护平行车辆清单：用`VehicleRecord.isRental/rentalTownId/rentalGoldMultiplier`标记租赁车。
2. 通过Runtime服务校验town offers，避免Runtime依赖Game.FC：Game.FC注册每店offers，Game.Tank通用服务验证当前TownGate与世界位置。
3. 战斗开始快照租赁收益；损坏时先清理牵引与角色引用（先DetachTow停放另一辆车），再销毁租赁车辆记录（部件受损时即时退租、清理所有party/当前Combatant引用）。
4. 存档(v11)保存标记、归还店、收益比例及车辆状态；读档后恢复同一记录。不可改装/维修，弹药与装甲作为消耗品允许补给。
5. 以静态独立R6复核覆盖收入时序、牵引、装甲差额计费与接口文档。

**验证方法**: R6三路静态复核及交叉核验通过；未运行Unity、构建或测试。授权后需真实操作验证不同门店租赁、战斗折扣、受损退租/下车、拖车停放、装甲/弹药补给和v10→v11存读档。

**踩坑 / 已知异常与失败经验**: 既有VehicleRecord只表示自有车，战斗收益按结果直接发放，SaveSerializer也没有租赁来源信息；受损退租若仅删除车辆记录，会遗留Combatant、party与牵引ID引用。用“战斗结束时是否仍持有租车”算收益会漏算本场受损退租的奖励扣减，所以必须在StartBattle快照；退掉作为拖车或牵引车的租赁车辆前，必须先DetachTow，否则会留下parked=false的孤立车辆；分次补装甲需按目标SP与当前SP的差额收费。

**关键文件与接口**: UNITY/Assets/Scripts/Tank/Runtime/RentalTankService.cs；Tank/Runtime/VehicleService.cs（Rent/ReturnRental/ReturnDamagedRental/BattleGoldMultiplier）；Core/GameSession.cs、Battle/BattleSystem.cs；Economy/GarageService.cs；Core/Save/SaveData.cs、SaveSerializer.cs

**状态**: 部分完成（核心纵切片与代码复核完成；FC指定版本车型配置/价格/损伤细节与Unity实机验收待核，测试待用户授权）

### P-20261060: FC租赁战车55毫米炮视觉资源回退
**日期**: 2026-10-27
**项目**: GAME / D:/code/GAME
**关键词**: FC重装机兵, 租赁战车, WPN_FC_Rental55, VisualCatalog, 视觉别名, 模型工厂回退

**需求场景 / 现象**: 租赁蚊式使用独立的`WPN_FC_Rental55`数据ID，但VisualCatalog没有同名资源或视觉注册，战车和战斗的模型路径会返回空模型。

**方案 / 实施步骤**:
1. 给Rental55注册45毫米Prefab别名，并为原Rental55 ID注册45毫米运行时模型工厂。
2. 由VisualCatalog优先尝试同ID资源，缺失时再通过别名加载已有45毫米Prefab；Prefab也不可用时由原请求ID对应工厂兜底。
3. 未来加入`WPN_FC_Rental55`同名资源即可优先显示专属模型，无需改场景挂载路径。

**验证方法**: 静态检查确认45毫米Prefab存在、视觉注册顺序符合VisualCatalog解析路径；租赁炮武器数据没有改动；三路独立R6与三路交叉核验PASS。未运行Unity、构建或测试。

**踩坑 / 已知异常与失败经验**: 当前模型仍非55毫米专属造型，也没有FC指定版本的模型尺寸证据；真实车辆/战斗镜头待用户授权。

**关键文件与接口**: UNITY/Assets/Scripts/FC/FcCampaignBootstrap.cs；docs/FC_REMAKE.md；docs/FC_REFERENCE.md

**状态**: 部分完成（视觉ID接线与文档边界已静态实现；专属55毫米外观和Unity实机验证未完成）

### P-20261061: FC租赁蚊式专属55毫米炮源资产与Prefab生成入口
**日期**: 2026-10-27
**项目**: GAME / D:/code/GAME
**关键词**: FC重装机兵, 租赁战车, WPN_FC_Rental55, Blender, FBX, Unity Prefab

**需求场景 / 现象**: 租赁蚊式已有独立55毫米武器数据ID，但当前运行时只显示45毫米炮视觉占位，缺少专属美术资产。

**方案 / 实施步骤**:
1. 新建专属Blender源文件与生成脚本，产出独立55毫米模型、FBX和预览。
2. 添加FBX导入meta及Editor Prefab builder，为同名Resources prefab规定生成路径。
3. 保留现有运行时45毫米fallback，直到Prefab实际创建并纳入运行验证。

**验证方法**: Blender源生成流程成功并输出FBX/预览；三路独立复核及交叉核验PASS。未运行Unity、构建或测试。

**踩坑 / 已知异常与失败经验**: Unity Prefab尚未生成，运行时仍由45毫米视觉占位回退；游戏装配、比例、挂点和战斗镜头没有验收。造型是原创FC风格提案，不代表FC原版精确几何。

**关键文件与接口**: ArtSource/build_fc_rental55mm_cannon.py、ArtSource/WPN_FC_Rental55.blend、ArtSource/Previews/WPN_FC_Rental55.png；UNITY/Assets/Models/WPN_FC_Rental55.fbx 及 .fbx.meta；UNITY/Assets/Scripts/Presentation/Editor/FcRental55mmCannonPrefabBuilder.cs；docs/ART_BIBLE.md、docs/FC_REFERENCE.md、docs/FC_REMAKE.md

**状态**: 部分完成（源资产、FBX、预览及Prefab生成入口完成；Unity Prefab生成和运行时接入未完成）

### P-20261062: FC Buggy独立车身源资产与Prefab生成入口
**日期**: 2026-10-27
**项目**: GAME / D:/code/GAME
**关键词**: FC重装机兵, Buggy, TNK_FC_BuggyChassis, Blender, FBX, Unity Prefab, 车辆模型

**需求场景 / 现象**: 波布二号车Buggy已用 `FcBuggyModelFactory` 生成程序化外观，但缺少可编辑车辆专属源资产和可导入的标准模型资源。

**方案 / 实施步骤**:
1. 新增Blender生成脚本，产出开放式越野车身、四轮、驾驶舱/货斗/防滚架/备胎和主炮、副炮、SE三处挂点。
2. 导出只含模型的米制Y-up/+Z FBX与预览。
3. 补充与现有车辆ID同名的Resources Prefab Builder和Importer meta，后续Unity生成后可优先命中资源路径。
4. 当前不改运行时注册，因此现有工厂继续生效。

**验证方法**: Blender 4.5.10生成日志显示源、FBX与预览成功产出，95个模型对象进入FBX、preview studio排除。静态检查确认FBX+Z/Y-up导出参数、轴/米制Importer设置、尺寸/三挂点约束、资源ID路径匹配、预览可辨识、`git diff --check`无错误。三路R6初审和交叉核验全部PASS。未运行Unity、构建、游戏或测试。

**踩坑 / 已知异常与失败经验**: Unity Prefab尚未生成，运行时仍由 `FcBuggyModelFactory` 提供外观；Unity导入/比例/挂点镜头未验证。原创FC风格提案不代表FC原版精确车身几何。

**关键文件与接口**: ArtSource/build_fc_buggy_model.py；ArtSource/TNK_FC_Buggy.blend、ArtSource/Previews/TNK_FC_Buggy.png；UNITY/Assets/Models/FC/TNK_FC_Buggy.fbx及.meta；UNITY/Assets/Scripts/Presentation/Editor/FcBuggyPrefabBuilder.cs及.meta；docs/ART_BIBLE.md、docs/FC_REFERENCE.md、docs/FC_REMAKE.md

**状态**: 部分完成（源资产、FBX、预览和Prefab生成器完成；Unity Prefab生成及运行时替换未完成）

### P-20261063: FC荒野地图地点类型标记与滚动图例
**日期**: 2026-10-27
**项目**: GAME / D:/code/GAME
**关键词**: FC重装机兵, 大地图UI, MapEntryKind, KnownLocations, RetroUiColors, ScrollRect

**需求场景 / 现象**: 现有地图仅用相同菱形绘制所有已发现地点，图例不区分聚落、迷宫和地标。地图区域扩展后名称列表也可能超出显示空间。

**方案 / 实施步骤**:
1. 在`FieldUiPresentation`按`MapEntryKind`使用独立形状与纸色/Rust/Brass语义色，按类型与显示名排序并分组；当前位置用更大Focus色三角标记。
2. 图例放入RectMask2D/ScrollRect视口，通过VerticalLayoutGroup与ContentSizeFitter适配列表。
3. 当前工程没有EventSystem/InputModule，因此直接在地图打开且鼠标位于视口时读取Input System滚轮并更新垂直滚动位置。

**验证方法**: 静态检查`git diff --check`无空白错误；三路独立R6和交叉核验均PASS，发现并修复Rust用途文档与玩家Focus标记不一致。未运行Unity、构建或测试。

**踩坑 / 已知异常与失败经验**: 真实视口尺寸、滚轮灵敏度、字体fallback、图例滚动手感和可读性均未实测；新地点未发现仍不会显示（未知地点过滤、地图坐标和存档逻辑未改）。

**关键文件与接口**: UNITY/Assets/Scripts/Presentation/FieldUiPresentation.cs；docs/ART_BIBLE.md、docs/FC_REMAKE.md

**状态**: 部分完成（荒野地图按聚落/洞窟迷宫/地标分类与滚动图例已静态实现；Unity真实视口和滚轮体验未验收）

### P-20261064: FC Buggy与租赁55mm专属Resources prefab生成接线
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: FC重装机兵, Buggy, 租赁55毫米炮, Blender, FBX, Unity Resources Prefab, FcBuildTasks, VisualCatalog, fallback

**需求场景 / 现象**: 两个专属Blender源模型与FBX、预览、Prefab生成器均已存在，但缺少常规FC准备入口接线，仍无法由同一入口重现对应Resources prefab。

**方案 / 实施步骤**:
1. `FcBuildTasks.PrepareAndBuild` 调用 `FcBuggyPrefabBuilder.BuildFromCommandLine()` 与 `FcRental55mmCannonPrefabBuilder.BuildFromCommandLine()`，调用在预览捕获与Player构建前。
2. 输出路径分别是 `Assets/Resources/Visuals/TNK_FC_BuggyChassis.prefab` 与 `Assets/Resources/Visuals/WPN_FC_Rental55.prefab`，数据ID与 `VisualCatalog` 的Resources命名约定一致，生成资源后同ID资源优先于当前工厂/别名回退。
3. `docs/FC_REMAKE.md` 记录两个精确目标路径；没有更改模型、数值或运行时注册。

**验证方法**: R4/G3计划审查PASS；三路R6独立初审及交叉核验PASS；静态核对调用顺序、输出路径、ID和文档边界；R7为DEFERRED。未运行Unity、BuildPlayer、测试、Blender或游戏。

**踩坑 / 已知异常与失败经验**: 两个Prefab目前没有生成；运行时继续使用Buggy程序化工厂与55毫米炮的45毫米视觉回退。FBX模型导入、Prefab内容、运行时资源命中、镜头效果和场景使用均未验收。下一步需用户明确授权后按 `D:\sire\sire_ledger\runs\R20261027-104802-game\test-plan.md` 执行正常与缺失FBX边界测试。

**关键文件与接口**: UNITY/Assets/Scripts/Editor/FcBuildTasks.cs；UNITY/Assets/Scripts/Presentation/Editor/FcBuggyPrefabBuilder.cs；UNITY/Assets/Scripts/Presentation/Editor/FcRental55mmCannonPrefabBuilder.cs；docs/FC_REMAKE.md

**状态**: 部分完成（生成器已接入PrepareAndBuild；Prefab未生成，Unity验收待授权）

### P-20261065: 行旅菜单任务与赏金状态语义色
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: FC重装机兵, 行旅菜单, 任务状态色, 赏金状态色, QuestState, BountyState, SelectedText, DisabledText, RetroUiColors

**需求场景 / 现象**: 行旅菜单已有任务与赏金的状态文案，但列表文字未使用共享语义色表达状态，选中行文字与暖色背景的对比也不足。根因：菜单行颜色只由统一的基础色和禁用色决定；任务、赏金状态没有映射到既有语义色板，且没有独立的选中行文字 token。

**方案 / 实施步骤**:
1. 复用 `QuestState`、`BountyState` 枚举构建状态到共享 token 的映射：进行中剧情任务 Paper，已完成任务 Reward，通缉中的赏金 Rust，已击败待领赏 Reward，已领取 SecondaryText。
2. 在 `FieldCommandMenu` 的命令数据中增加可选 label color，新增 `RetroUiColors.SelectedText=#3D1F0E`；选中且启用的行使用 SelectedText；禁用状态优先使用 DisabledText；其余行使用状态色或 Paper。
3. 保留原状态文字、箭头和点击回调，更新视觉规范文档；只改变表现层，不改存档或玩法数据。

**验证方法**: 静态核对状态分支、共享色值、颜色优先级、交互回调和文档约定；R6A/R6B/R6C 三路审查及交叉核验均 PASS。Unity 运行态视觉验收、构建与测试尚未授权。授权后在任务/赏金混合状态存档中打开 Quests 页，逐行检查状态文字色和选中对比，再检查禁用行仍采用 DisabledText。

**踩坑 / 已知异常与失败经验**: 若文档只列出 token 名称或只写色值，不足以明确每个状态使用哪个 token；应在 ART_BIBLE 中直接记录 Paper 对应进行中任务、SecondaryText 对应已领赏，并同时写出选中/禁用优先级。

**关键文件与接口**: UNITY/Assets/Scripts/Presentation/Menu/FieldCommandMenu.cs（Command.labelColor、Add(..., Color? labelColor)、PaintSelection()）；UNITY/Assets/Scripts/UI/RetroUiTextures.cs（RetroUiColors.SelectedText）；docs/ART_BIBLE.md；docs/FC_REMAKE.md

**状态**: 部分完成（静态实现和审查完成，运行态视觉验收待做）

### P-20261066: 行旅菜单操作结果语义反馈色
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: FC重装机兵, 行旅菜单, 操作结果反馈, RetroUiColors, OpResult, Result, success feedback, error feedback, NothingToDo

**需求场景 / 现象**: 行旅菜单中购买、维修、存读档等操作的结果都显示在同一个 `_feedback` 文本行，但此前统一使用黄铜色，玩家需要先读文字才能区分成功、失败和无需操作。根因：`FieldCommandMenu.Result` 只更新反馈文字，不根据 `OpResult` 的语义选择颜色。

**方案 / 实施步骤**:
1. 静态枚举所有反馈写入与操作结果分支。
2. 复用已存在的 `RetroUiColors`，不新增token：成功 `OpResult.Ok` 使用 `Reward`；中性 `NothingToDo` 使用 `SecondaryText`；其他结果默认 `Rust`；禁用操作、城镇/车库/商店/保存位置不可用等明确失败提示使用 `Rust`；成功换位使用 `Reward`；普通说明/设置请求继续使用 `Brass` 默认色。
3. 静态审查行为不变并同步视觉规范；保留提示文本、服务调用、错误音效、输入和存档逻辑。

**验证方法**: 全量静态核对 `Say` 调用、`OpResult` 默认失败映射、文档一致性与行为边界；三路R6审查和三路交叉核验PASS，`git diff --check`无空白错误。未运行Unity、构建、游戏或自动化测试；运行态对比度、显示器观感及错误/中性音色协调性仍需用户授权后验收。

**踩坑 / 已知异常与失败经验**: 颜色状态与提示音语义需要一起评估；本单明确不改音效，因此 `NothingToDo` 虽然显示中性色，仍沿用历史 Error 音效。不要把静态颜色检查说成实机验收。

**关键文件与接口**: UNITY/Assets/Scripts/Presentation/Menu/FieldCommandMenu.cs（Result(OpResult, ...)、Say(string, Color)）；UNITY/Assets/Scripts/UI/RetroUiTextures.cs；docs/ART_BIBLE.md；docs/FC_REMAKE.md

**状态**: 部分完成（静态改动和审查完成，运行态视觉/音效验收待做）

### P-20261067: 战斗HP SP弹药余量语义色提示
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: FC重装机兵, 战斗界面, HP, SP, 弹药, RichText, BattleController, RetroUiColors, low-resource warning, enemy health

**需求场景 / 现象**: 战斗面板显示玩家与敌人HP、战车SP和武器弹量，但数字全是正文色，低资源和敌人接近击倒不够醒目。根因：`BattleController` 对存活/阵亡只做二态区分；SP和弹量一直使用普通文本色，低余量没有复用语义色。

**方案 / 实施步骤**:
1. 复用共享语义色并为RichText添加Rust HEX token（只改IMGUI展示，不改战斗逻辑）。
2. 玩家HP、SP、有限弹药按剩余比例：>50% Paper、>25%且≤50% Damage、≤25% Rust。敌方HP≤25%改用Reward而不是Rust，中段仍用Damage；HP为0优先BattleDead。
3. 无限弹药用Paper；有限弹药考虑本回合已经排队预留的射击数；最大值≤0不进行除法，余量≤0显示Rust，异常正余量回退Paper；存活但maxHP≤0的敌人使用Paper。
4. 保持HP/SP/弹药数字、按钮输入和战斗结算不变，静态核对边界与文档。

**验证方法**: 静态检查0/25/50%边界、HP死亡优先、最大值≤0、无限/预留弹药、RichText数字、文档一致；三路R6审查及交叉核验均PASS，`git diff --check`无空白错误。未运行Unity、构建、游戏或自动化测试；运行态对比度与disabled按钮效果待授权验收。

**踩坑 / 已知异常与失败经验**: 敌人低HP是好消息，不应与我方危险共用锈色，否则状态语义相反；应给敌方临近击倒使用Reward。富文本状态需要同时检查单位为0与最大值为0的边界，且无限弹药要单独处理。这些阈值只是开发UI提示，不是FC原版机制。

**关键文件与接口**: UNITY/Assets/Scripts/Battle/BattleController.cs（HealthColorHex、ResourceColorHex）；UNITY/Assets/Scripts/UI/RetroUiTextures.cs（RetroUiColors.RustHex）；docs/ART_BIBLE.md；docs/FC_REMAKE.md

**状态**: 部分完成（静态实现和审查完成；运行态视觉验收待做）

### P-20261068: FC战斗敌人掉落配置与胜利发放
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: FC重装机兵, 敌人掉落, 战斗胜利结算, EnemyData, EnemyDrop, ItemService, EquipmentService, PartInstance, loot table, weighted drop

**需求场景 / 现象**: 敌人只有经验与金钱字段。经济循环要求战斗可掉落道具、人物装备、战车部件，但没有配置、随机判定、背包发放或结果日志。EnemyData 没有掉落配置，BattleSystem.End 没有战利品结算。

**方案 / 实施步骤**:
1. 给敌人数据增加可序列化的三类掉落行：EnemyData 以列表配置 `EnemyDropKind`（Item/Gear/TankPart）、ID、百分比和数量区间。
2. 在战斗终态胜利分支对各敌人独立滚动（BattleSystem 只在Victory时使用自身随机源逐敌/逐条判定，一次性终态保护避免重复结算）；运行时钳制概率到0..100及数量边界。
3. 经现有服务和GameDB资源验证发放：物品通过 ItemService，装备经 GameDB 验证后写 gearBag，战车部件按数量实例化后进入 inventory；记录结果日志，不改变存档格式。
4. 配置列表默认空，文档注明当前敌人掉落表待核，等待指定FC来源验证后再填具体数据。

**验证方法**: 静态检查现有类型和服务契约、Victory/Defeat/Escaped与单次结束路径、0/100概率和数量范围、失败日志、存档字段复用；`git diff --check`通过；三路R6初审与交叉核验通过。未运行Unity、构建、游戏或自动化测试；运行态验收待用户授权。

**踩坑 / 已知异常与失败经验**: `[Range]`/`[Min]`只限制Inspector输入，不限制运行时值；需要在抽取时clamp。装备入袋接口无返回值且不验证ID，必须预先调用GameDB.Gear。不同来源/版本的掉落表不能直接映射为当前开发ID，不能为了让系统有示例数据而猜值。

**关键文件与接口**: UNITY/Assets/Scripts/Battle/EnemyData.cs（EnemyDropKind、EnemyDrop、EnemyData.drops）；Battle/BattleSystem.cs（End、AwardEnemyDrops、GrantDrop、NextInclusive）；Items/ItemService.cs；Equipment/EquipmentService.cs；Core/PlayerState.cs、Core/Save/SaveSerializer.cs；docs/FC_REFERENCE.md、docs/FC_REMAKE.md

**状态**: 部分完成（可配置掉落系统静态实现完成；FC具体掉落数据和运行态验证待补）

### P-20261069: 校准FC开局常规敌人经验与现金奖励
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: FC重装机兵, NES Metal Max, Enormous Ant, Cannon Hopper, Surveillance Camera, Bionic Pooch, expReward, goldReward, enemy reward mapping

**需求场景 / 现象**: FC开局敌人的经验和金币奖励使用开发调校值，和可找到的NES攻略敌人数据不一致；EnemyDrop系统已实现，但不能把未证实的物品掉落率当作原版事实。

**方案 / 实施步骤**:
1. 查当前FC runtime敌人名称、地点和奖励参数。
2. 从NES专属社区攻略提取同名/同地点奖励。
3. 只校准明确匹配的三项：Enormous Ant (Riorado/Various)→ENM_FC_GiantAnt 1EXP/2G；Cannon Hopper (Southern Cave/Factory)→ENM_FC_CannonHopper 5EXP/8G；Surveillance Camera (Factory)→ENM_FC_SurveillanceCamera 3EXP/1G；Bionic Pooch→WarDog原有20EXP/32G一致，保留。
4. 保持群体奖励和掉落概率待核并更新来源表；未列出物品的敌人不加ItemDrop。

**验证方法**: 静态核对三条源码参数、WarDog 20/32、BattleSystem汇总接口和FC_REFERENCE；目标文件行尾空白检查通过。三路R6初审与交叉核验PASS。未运行Unity、构建、游戏或自动化测试，等待用户授权。

**踩坑 / 已知异常与失败经验**: NES专属攻略仍是二手来源；某些敌群的经验/现金是群体还是单只无法仅凭总览表确定。不要将“现金奖励”误记为敌人道具掉落，也不要从列有物品名的来源猜掉落概率。

**关键文件与接口**: UNITY/Assets/Scripts/FC/FcCampaignBootstrap.cs（RegisterData()）；UNITY/Assets/Scripts/Battle/BattleSystem.cs（TotalExp / TotalGold，逻辑未改）；docs/FC_REFERENCE.md

**状态**: 部分完成（可明确映射的常规敌人EXP/Gold已校准；其他敌人、道具掉率和指定FC版本实机结果仍待核/验收）

### P-20261070: Buggy Blender到Unity FBX米制资产管线与挂点合同
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: Blender, FC Buggy, TNK_FC_Buggy, FBX导出, Unity ModelImporter, weapon mount, Y-up, +Z-forward, globalScale, stale FBX

**需求场景 / 现象**: 将原创FC风格Buggy模型从可编辑Blender源接入Unity资源管线。导出器必须避免覆盖源文件，且生成的FBX要与Unity Prefab生成器和运行时战车武器挂点兼容。

**方案 / 实施步骤**:
1. 检查已有Blender资产导出/生成代码及Unity prefab builder约定。
2. 将原`.blend`备份到固定SIRE运行台账，记录哈希。
3. 对齐源模型中Main `(0,1.63,0.04)`、Sub `(0.43,1.23,-0.20)`、SE `(-0.43,1.23,-0.20)`挂点。
4. 从已保存`.blend`只读选择模型根和后代，导出到同目录临时FBX；必须收到`FINISHED`且临时文件非空后用`os.replace`替换正式文件。
5. 确保Prefab Builder与FBX `.meta`以scale 1导入（米制FBX的Blender导出、Unity ModelImporter和`.meta`均使用scale 1）。

**验证方法**: 使用Blender 4.5.10进行模型源更新和FBX资源生成；导出器报告91个网格和挂点验证成功；源备份与更新后SHA-256分别为`8CAA89AE97C5E1973920951430F9C053619AD8CD742A15102A484746EF716C0C`和`E9FFED239B491BFD1946602498F186A85D2BD6E5DC3C6F3248A85AC9DB0E526B`。三路静态代码复核及交叉核验通过。Unity导入、Prefab生成、构建和游戏运行未获授权，未执行。

**踩坑 / 已知异常与失败经验**: 根因：原全量建模脚本会重建并覆盖`.blend`；早期FBX导出器未检查Blender operator返回值，旧FBX可掩盖导出失败；三个挂点与程序化运行时位置不一致；Prefab Builder和`.meta`把米制FBX按100倍缩放导入。不要把`100`当作所有Blender FBX的通用Unity导入比例；应按源文件单位、FBX UnitScaleFactor和Prefab Builder尺寸合同判断。预先存在的非空FBX不能证明本次导出成功；必须检查operator结果并隔离临时产物。静态挂点坐标一致不能证明Unity导入轴向、Prefab尺寸和运行时武器朝向正确。

**关键文件与接口**: ArtSource/build_fc_buggy_model.py；ArtSource/update_fc_buggy_mounts.py；ArtSource/export_fc_buggy_fbx.py；UNITY/Assets/Scripts/Presentation/FC/FcBuggyModelFactory.cs；UNITY/Assets/Scripts/Presentation/Editor/FcBuggyPrefabBuilder.cs；UNITY/Assets/Models/FC/TNK_FC_Buggy.fbx.meta（globalScale=1）

**状态**: 部分完成（Blender源和FBX已接入，Unity Prefab尚未生成；运行时仍使用程序化外观，待用户授权Unity验收）

### P-20261071: FC开局南洞奖励与非消耗收藏物注册
**日期**: 2026-10-27
**项目**: D:\code\GAME
**关键词**: FC南洞, Southern Cave, B2宝箱, Camouflage Fatigues, Fortune Coin, ItemKind.Collectible, RegistryAssets, GameDB.RegisterGear, 战狗旗标

**需求场景 / 现象**: FC NES二手流程资料记载南洞存在57G、103G、Fortune Coin与Camouflage Fatigues，但当前开发版B2缺少这些奖励。攻略内部对Fortune Coin地点有冲突，南洞段落称其在B2箱中，通用物品索引列为Northern Cave。南洞构建器此前只实现B1恢复道具和战狗/红狼/首车事件；运行时注册器尚无该收藏物与迷彩服数据。

**方案 / 实施步骤**:
1. 给每个新增箱子使用独立Story flag，沿用存档已有flags集合：在南洞B2增加奖励箱；迷彩服领取要求fc:war_dog_resolved。
2. 通过动态RegistryAssets创建并注册收藏物与装备，确保存档ID能还原数据：Fortune Coin以ItemKind.Collectible进入普通道具背包，追加在枚举末尾，不提供未经证实的效果且不能使用或消耗；迷彩服按身体装备动态注册，防御12/价格90（二手NES攻略，待FC实机校准），新增GameDB.RegisterGear供运行期追加GearData。
3. 将资料冲突、数值来源和未验证坐标写入玩法文档。

**验证方法**: R6A/B/C进行了代码和文档静态审查；源文件差异静态核对。用户尚未授权测试，本任务没有执行测试、构建、Unity或游戏运行。授权后建议验证新档四项奖励、战狗前后迷彩服门禁、保存读档、重复领取防护与金币数值。

**踩坑 / 已知异常与失败经验**: 初审一度误以为Make<T>未登记RegistryAssets；代码复核确认Make<T>内部自动加入列表。动态GearData需要GameDB.RegisterGear，与CSV静态导入分开处理。不要把Fortune Coin地点冲突写成确定事实，也不要把二手数值称为FC实机校准。

**关键文件与接口**: UNITY/Assets/Scripts/FC/FcDungeonBuilder.cs（B2宝箱、FcCaveReward.allowed）；UNITY/Assets/Scripts/FC/FcCampaignBootstrap.cs（Make<T>/RegistryAssets）；UNITY/Assets/Scripts/Core/GameDB.cs（RegisterGear）；UNITY/Assets/Scripts/Items/ItemData.cs（Collectible）；docs/FC_REFERENCE.md、docs/FC_REMAKE.md

**状态**: 已实现，未测试

### P-20261072: FC开局45毫米主炮弹量与底盘特殊弹仓区分
**日期**: 2026-10-27
**项目**: D:\code\GAME
**关键词**: FC初代, Metal Max NES, WPN_FC_Cannon45, 主炮弹量, maxAmmo, 初始弹药, chassis magazine, special shells

**需求场景 / 现象**: FC开局战车蚊式使用45毫米主炮，当前开发数据把主炮上限设为16发并在取得时设成0发；NES流程资料写明蚊式主炮有32发。旧文档还把每武器currentAmmo错误描述为底盘弹仓近似。

**方案 / 实施步骤**:
1. 逐一追踪45mm WeaponData创建、Rental55克隆、CreateFirstTank和CreateRentalMosquito实例化路径。
2. 只调整蚊式主炮最大弹量和获得时装弹：将WPN_FC_Cannon45.maxAmmo调为32，CreateFirstTank取得时装入32发；其克隆WPN_FC_Rental55保持32发上限并在租赁车创建时通过RefillAll装满；Buggy启动时对WPN_FC_BuggyCannon的显式currentAmmo=12不变。
3. 将武器弹药与特殊弹仓的来源及实现状态写入总览和参考文档：区分每个主炮/S-E的武器弹药与由底盘装载的特殊砲弹弹仓，后者仍未实现。

**验证方法**: R6A/B/C静态独立审查和交叉核验PASS；当前源代码和文档静态复核。用户未授权测试，本任务没有运行测试、构建、Unity或游戏。授权后建议验证新档取得蚊式为32/32、租赁55炮32/32、Buggy保留12发、战斗耗弹及存读档。

**踩坑 / 已知异常与失败经验**: FC_REFERENCE总览仍残留“初始无弹”，会与数据实现及后文冲突；R6初审发现后已修正文案并重审通过。官方手册确认主炮/S-E限弹与特殊弹仓机制，但32发具体值来自GameFAQs NES攻略及日文数据表，必须标注待指定FC版本实机校准。

**关键文件与接口**: UNITY/Assets/Scripts/FC/FcCampaignBootstrap.cs（RegisterData中的45mm maxAmmo、CreateFirstTank）；docs/FC_REFERENCE.md；docs/FC_REMAKE.md；UNITY/Assets/Scripts/Core/Save/SaveSerializer.cs（PartInstance.currentAmmo→PartSave.ammo）

**状态**: 已实现，未测试；底盘特殊砲弹系统未实现（见P-20261073）

### P-20261073: FC底盘特殊砲弹弹仓、装卸、存档与战斗命令
**日期**: 2026-10-27
**项目**: D:\code\GAME
**关键词**: FC Metal Max, chassis special shell magazine, special shells, main gun ammo separation, v12 save migration, action reservation, tank shell command, magazine capacity upgrade

**需求场景 / 现象**: 既有战车只将主炮/S-E各自有限弹量存入 PartInstance.currentAmmo，没有FC手册描述的底盘特殊砲弹弹仓、购买/装卸、战斗砲弹命令和每车弹仓存档。

**方案 / 实施步骤**:
1. 新增SpecialShellData与独立shellId/count清单；玩家背包与TankLoadout分别持有清单。
2. 底盘容量采用开发原型固定公式min(128,32+16×底盘改造等级)，不加重量且换底盘保留已装弹，容量变小时保留超容量有效弹并禁止继续装入。
3. ShopService先校验商品/钱/堆叠再扣款；GarageService校验容量后原子转移。
4. SaveData升至v12，旧档新字段为空，特殊弹坏ID/非正数量告警跳过。
5. 战斗TankShell行动在提交与执行阶段分别验证并按tank+shellId预留，实际发射时扣弹；使用现有范围、伤害、音频和战车攻击演出接口。普通、榴弹、爆裂、穿甲、催眠瓦斯、火焰六类作为当前纵切片。
6. 新增弹种及错误提示需由FC bootstrap TextDB.Register显式注册。

**验证方法**: R6A/B/C修复后初审与三路交叉核验PASS；R8静态集成审查PASS；git diff --check返回退出码0。用户未授权测试，未运行Unity、构建或游戏功能测试；R7已延期等待授权。

**踩坑 / 已知异常与失败经验**: 关键修复：穿甲效果的双倍倍率在DamageCalculator完成基础最终伤害后应用，不能仅翻倍攻击力；睡眠/压制跳过的Defend行动不得保留防御态；运行时文本来自TextDB资源，只改CSV不够。限制：官方FC手册支持底盘弹仓、改造扩容、砲弹命令和主炮门槛；容量128及炮种效果来自二手NES资料，基础32、每级+16、部分伤害/状态与范围是暂定原型值，未指定FC版本实机核对；只实现六种特殊弹，其他毒气、慌乱、烟幕和哑弹仍待后续。

**关键文件与接口**: UNITY/Assets/Scripts/Items/SpecialShellData.cs；Tank/Runtime/TankLoadout.cs；Economy/ShopService.cs 与 GarageService.cs；Core/Save/SaveData.cs 与 SaveSerializer.cs；Battle/BattleAction.cs、BattleSystem.cs、BattleController.cs；FC/FcCampaignBootstrap.cs；Presentation/Audio/AudioDirector.cs、CombatPresentationBootstrap.cs；docs/FC_REFERENCE.md、docs/FC_REMAKE.md

**状态**: 已实现六种特殊弹纵切片；静态复核通过；未测试

### P-20261074: FC Buggy Unity Prefab生成受headless许可阻塞
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: FC Buggy, Unity Editor, Blender FBX, Resources prefab, licensing, headless entitlement, mount validation

**需求场景 / 现象**: 将原创FC风格Buggy Blender车身接入运行时资源路径`Resources/Visuals/TNK_FC_BuggyChassis`，使用已存在的`FcBuggyPrefabBuilder`生成Prefab。单资源Unity Editor命令启动后返回198，日志报告零个匹配entitlement及`com.unity.editor.headless`未找到；目标Prefab仍不存在。

**方案 / 实施步骤**:
1. 保存生成前`.blend` SHA-256。
2. 只调用`FcBuggyPrefabBuilder.BuildFromCommandLine`生成目标Prefab。
3. 检查Builder日志、Prefab资源路径和挂点结果；对比生成后的`.blend` SHA-256。
4. 如Unity许可初始化失败，保留日志、停止，不执行全量构建流程。

**验证方法**: 本次单资源Unity命令退出198；日志明确显示许可初始化失败且headless entitlement不存在；Prefab没有生成；`.blend`前后SHA-256一致，为`E9FFED239B491BFD1946602498F186A85D2BD6E5DC3C6F3248A85AC9DB0E526B`。三路独立审查确认ID/路径和文档描述一致，但导入挂点断言未执行。未运行Play Mode、测试、Player构建或游戏。

**踩坑 / 已知异常与失败经验**: 根因：Unity Editor在许可初始化阶段无法取得本地可用许可，未进入Prefab Builder，不能据此判断FBX导入或挂点校验失败。许可失败时不以完整`PrepareAndBuild`/`ValidateAndBuild`流程绕过，因为该流程还会运行脚本/预览并构建Player。已有FBX不能代替Prefab生成证据；挂点代码的静态合同也不能证明Unity导入轴向已实际正确。Prefab Builder额外校验导入后模型根坐标中的`Mount_Main (0,1.63,0.04)`、`Mount_Sub (0.43,1.23,-0.20)`、`Mount_SE (-0.43,1.23,-0.20)`。

**关键文件与接口**: UNITY/Assets/Scripts/Presentation/Editor/FcBuggyPrefabBuilder.cs；UNITY/Assets/Scripts/Core/VisualCatalog.cs（Resources/Visuals/{id} 优先，回退注册的程序化工厂）；UNITY/Assets/Scripts/FC/FcCampaignBootstrap.cs（BuggyChassis）；ArtSource/TNK_FC_Buggy.blend、ArtSource/export_fc_buggy_fbx.py、UNITY/Assets/Models/FC/TNK_FC_Buggy.fbx.meta

**状态**: 部分完成（Prefab生成受Unity许可初始化阻塞，运行时仍使用程序化回退）

### P-20261075: Unity 存档可选记录的局部恢复与重复状态合并
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: Unity存档恢复, SaveSerializer.FromSave, malformed optional save records, duplicated bounty, quest progress, JSON save migration, JsonUtility

**需求场景 / 现象**: Unity `JsonUtility` 可能反序列化出含 null 条目或缺失嵌套列表的可选存档集合。重复的 `Defeated` 赏金记录会让读档后重复领取奖励；重复任务记录会扭曲进度；null 预备队成员在跳过无效项后不得造成索引错位。

**方案 / 实施步骤**:
1. 保持 `SaveSystem` 的必需根结构校验，仅在 `SaveSerializer.FromSave` 清理可选记录。
2. 道具/装备袋堆叠：跳过 null/空白/未知 ID 与非正数量；已知重复 ID 用加宽求和合并，仅在整数溢出时饱和。
3. 重复赏金记录取最高已知进度（`Wanted < Defeated < Claimed`）；已知状态胜过未知；两者皆未知保留第一个未知值。
4. 重复任务：负步数钳到0，保留最大步数，已知状态中优先 `Completed`；已知胜过未知；两者皆未知保留第一个。
5. 跳过畸形预备队记录并把恢复后的预备队规范化为无战车；缺失战车武器列表视为空，空洞补齐到当前底盘大小，从不截断已序列化槽位。
6. 保留不同的非空未知剧情旗标；需要时过滤空白/未知已装备装备ID。

**验证方法**: 静态审查必需读档门禁、状态排序、恢复辅助路径，并对 `SaveSerializer.cs` 做 `git diff --check`。功能路径：用菜单存读档，测试正常状态、含畸形可选条目的手改存档、根级 party 非法的手改存档。本任务未运行功能测试，需后续授权。

**踩坑 / 已知异常与失败经验**: 最初的合并逻辑让未知重复值覆盖已知赏金/任务状态，也让已有未知值阻挡后续有效进度；修正规则：仅一方已知则取已知，双方已知按进度序，双方未知才保留一个未知值。预备队规范化应遍历过滤后的运行时列表，而不是用源列表长度索引。

**关键文件与接口**: UNITY/Assets/Scripts/Core/Save/SaveSerializer.cs；Core/Save/SaveSystem.cs；Town/BountyService.cs（ClaimAll 对 Defeated 记录发奖）；Story/StoryService.cs（Refresh）

**状态**: 部分完成（静态实现与审查完成；存档读写功能测试待用户授权）

### P-20261076: Unity长期仓库应与随身堆叠上限分离
**日期**: 2026-10-27
**项目**: GAME / D:\code\GAME
**关键词**: Unity存档, 长期仓库, Trunk Room, stack normalization, SaveSerializer, int.MaxValue split stack, carried inventory cap

**需求场景 / 现象**: 为长期仓库实现与随身背包分离的物品存取。仓库不应继承随身携带的99/128上限，也不能在存档时被背包规范化逻辑截断。

**方案 / 实施步骤**:
1. 明确每种列表的语义和哪个方向适用携带上限：分开定义 carried side 规则和 trunk side 规则；99/128只用于取回到随身列表，仓库本身不引入游戏规则容量。
2. 把容量检查放在任一状态变更之前，并用long预检加一；单件转移先校验源、目标和有限的随身容量，预检成功后才更新两端。
3. 容器单堆达到int.MaxValue时，新增一条同ID堆叠；为长期容器单独实现坏项过滤和逐条保存/恢复，保持重复ID记录，不合并、不调用有容量上限的随身规范化器。
4. 可选仓库条目局部验证并警告跳过，保留根级必需存档校验不变。
5. 用独立静态审查覆盖整数边界与存档重复记录，再通过真实游戏路径验证普通存取、上限、旧档迁移和坏项行为。

**验证方法**: 静态检查转移顺序与序列化路径；本次三路独立代码审查和交叉核验通过。运行时测试未授权；需经授权后通过游戏菜单验证普通存取、99/128边界、旧档升级、v13重读及坏记录。

**踩坑 / 已知异常与失败经验**: 根因：同一 ItemStack 数据类型容易让实现者复用随身背包的合并/截断器；将SpecialShellService.Normalize用于仓库读写会把每种特殊砲弹限制为128发；直接将同一ID计数加一也会隐式限制为int.MaxValue，在存档前另行分堆会被合并恢复再次截断。int.MaxValue既是表示范围又被误当成游戏容量，导致尝试分堆的代码先被上限判断拦截；无上限容器必须将有限carry上限校验与整数表示溢出分开处理。

**关键文件与接口**: UNITY/Assets/Scripts/Items/TrunkStorageService.cs；UNITY/Assets/Scripts/Core/Save/SaveSerializer.cs（CopyStacks、RestoreTrunkStacks、v13迁移）；UNITY/Assets/Scripts/Core/Save/SaveSystem.cs（HasRequiredPayload）

**状态**: 部分完成（实现与静态审查完成；运行时存读档及交互验证待授权）

### P-20261077: 多读取器界面应区分设备选择与设备工作区
**日期**: 2026-10-27
**项目**: EncoderPlotter_0903_01 / encoder-next
**关键词**: 多读取器界面, reader workspace, 设备选择, 工作区导航, single action entry, COM port, serial suffix

**需求场景 / 现象**: 一个桌面上位机需要同时呈现多台读取器，并让用户能明确选择设备、识别设备和执行当前设备操作。首版页面出现单台连接动作重复、选中设备信息只在侧栏明显、窄屏折叠后无法区分设备等问题。根因：读取器选择与读取器内功能导航是两个不同维度；设备列表、全局功能菜单和设备操作入口互相重复会让用户不确定上下文。

**方案 / 实施步骤**:
1. 把设备选择和设备内工作区导航分成两个明确层级：左侧列表只负责选择读取器并呈现每台设备状态，列表标题提供批量操作；中央工作区只显示当前选中读取器的功能，标题固定展示设备名称、序列号末四位和端口。
2. 每个单设备操作只保留一个入口：单台连接/断开只在读取器链路卡片出现一次；编码器相关操作只放编码器卡片；批量操作固定在设备列表。
3. 设备身份同时使用名称、序列号末四位、端口和文字状态；颜色仅作辅助；折叠/窄屏仍显示序列号末四位与状态点，完整序列号放入辅助提示和无障碍名称。
4. 当前未开放的功能明确显示“暂未开放”。
5. 用多设备真实扫描页面检查桌面与窄屏布局，再通过类型检查。

**验证方法**: `npm run typecheck` 通过；使用 legacy 适配器的真实扫描页面识别到两台设备（20260420173117/COM3、20260921152825/COM37），检查名称、端口、状态芯片、工作区导航、窄屏折叠和页面宽度。连接和编码器操作不属于本次真机验证范围。

**踩坑 / 已知异常与失败经验**: 仅依赖颜色无法区分多台设备，窄屏折叠时应保留短序列号；在标题栏和内容卡片重复放置连接按钮会让操作入口不清晰。

**关键文件与接口**: `encoder-next/docs/ui-architecture.md`（菜单层级与操作入口决策）；`encoder-next/web/src/views/WorkspaceHost.vue`；`encoder-next/web/src/layout/ReaderRailItem.vue`；`encoder-next/web/src/views/OverviewView.vue`。

**状态**: 部分完成

### P-20261078: EncoderPlotter simulator reader count fixtures
**日期**: 2026-10-27
**项目**: EncoderPlotter_0903_01 / encoder-next
**关键词**: encoder-next simulator, --sim-readers, SimulatorGateway, UI布局验证, 多读取器夹具

**需求场景 / 现象**: 多读取器界面需要可重复验证 0、2、8 台读取器的卡片密度和滚动布局，同时不能依赖真实硬件连接。固定两台模拟设备只能验证基础列表，无法稳定检查超过布局阈值后的紧凑模式；使用真机或 legacy 扫描会占用串口并把视觉验证与硬件状态耦合。

**方案 / 实施步骤**:
1. 将设备数量作为模拟器配置传给硬件适配器：后端模拟器通过 `--sim-readers N` 控制设备数量，默认 2，序列号从 1001 递增；模拟器将 1002 设为进入失败，用于呈现错误状态。
2. 前端只消费统一 hub 状态；使用生成的连续序列号形成可预测的视觉夹具。
3. 仅通过浏览器观察布局；不连接真实读取器或启动 legacy 应用。
4. 对模拟器变更加跑 server tests，记录结果。

**验证方法**: `py -3.12 -m pytest tests -q`（工作目录 `encoder-next/server`）：32 passed, 1 Starlette TestClient 弃用警告 in 2.05s；`npm run typecheck` 通过。页面用模拟器观察 2/8/0 台时的密度与占位状态。

**踩坑 / 已知异常与失败经验**: 将错误态 fixture 固定到第二个模拟读取器可重复观察状态标签；若页面上出现已连接读数，应先确认当前后端是模拟器状态，不应把这当成真机扫描证据。

**关键文件与接口**: `encoder-next/server/encoder_next/config.py`（`Settings.sim_readers` 默认值）；`encoder-next/server/encoder_next/__main__.py`（`--sim-readers N`）；`encoder-next/server/encoder_next/container.py`（合成序列号范围和 1002 进入失败配置）；`encoder-next/server/tests/test_services.py`。

**状态**: 已完成

### P-20261079: encoder-next RT角度采集接口和CRC兼容
**日期**: 原记录未记载
**项目**: EncoderPlotter_0903_01 / encoder-next
**关键词**: encoder-next, RT, RS485, CRC, 空帧, 角度采集

**需求场景 / 现象**: 启动服务诊断DPB角度采集无数据。初始仅Vite5173运行，后端8780未启动。启动legacy发现COM37 SN20260921152825，DPB ABS RT 2.5M 20bit V4.0.11。接口9两秒0帧，接口3两秒1225帧。CRC=true时存在空帧、短帧与解析错误。

**方案 / 实施步骤**:
1. 修正legacy网关RT线上映射RS485，保留原始RT配置与24位解析。
2. 10/30/100超时字节对照未改善；CRC=false同条件644帧全部8字节。
3. 默认命令生成对RT关闭发送CRC（用户仍可修改），其他接口保持原默认值。
4. 已在当前浏览器此读取器保存CRC=false，未硬编码覆盖其他设备CRC。

**验证方法**: 45后端测试通过；前端build通过，640组合规则对照通过；实机连续43848帧、0丢帧，无解析错误，暂停/继续通过；独立R6复核通过。截图angle-restored.png。

**踩坑 / 已知异常与失败经验**: 现有配置不自动迁移；本读取器已手动取消CRC并保存。640对照覆盖基础规则，不覆盖新CRC默认值分支。测试覆盖当前DPB V4.0.11设备，其余型号未实测。encoder-next目录原本为未跟踪，未提交。

**关键文件与接口**: `encoder-next/server/encoder_next/adapters/legacy/gateway.py`；`encoder-next/web/src/stores/defaultCommands.ts`；`encoder-next/server/tests/test_legacy_profile.py`。

**状态**: 已完成

### P-20261080: encoder-next高频采集限制Vue刷新频率
**日期**: 2026-10-28
**项目**: EncoderPlotter_0903_01 / encoder-next
**关键词**: 高频采集, Vue响应式渲染, readout.ts, flushUiStats, 帧率卡顿

**需求场景 / 现象**: 高频收到数据批次时，界面帧数、丢帧、revision和每条曲线最新值/错误数都在每批写回Vue响应式状态，可能以硬件批次速率重渲染图表组件（帧率卡顿）。根因：accept() 每批递增响应式frames/dropped/revision，并遍历解析项写响应式Trace.latest/errors；revision又被图表bufferSeconds computed依赖。

**方案 / 实施步骤**:
1. 原始采样、公式计算、环形缓存写入和非响应式绘图版本仍逐批运行。
2. 把帧摘要和曲线最新值/错误数统一放入250ms刷新（最多4Hz，flushUiStats），只有字段实际变化才递增revision。
3. 停止采集时在清空运行态前同步刷新尾批。

**验证方法**: 仅静态复核与git diff --check；本轮未获用户授权运行测试、构建或浏览器验证。R6独立复核通过。

**踩坑 / 已知异常与失败经验**: 只节流frames/revision不够，Trace.latest/errors也会在每个数据批次触发Vue组件更新；停止时先清运行态会丢掉最后一周期待刷新的曲线摘要。

**关键文件与接口**: encoder-next/web/src/stores/readout.ts（accept、flushUiStats、stop）

**状态**: 部分完成

### P-20261081: encoder-next 当前功能边界、实时采集绘图架构与踩坑
**日期**: 2026-10-28
**项目**: EncoderPlotter_0903_01 / D:/code/EncoderPlotter_0903_01/encoder-next
**关键词**: encoder-next, 功能清单, 高频采集, 角度采集, WebSocket, readout, uPlot, TypedArray ring buffer, Pratt parser, RT RS485, DPB ABS, SIRE

**需求场景 / 现象**: 需要盘点 encoder-next 当前真实实现的功能，并把架构、实现方式和踩坑写入知识库。用户此前观察过高频读数时嵌入式浏览器渲染异常；普通独立浏览器读数画面稳定在 30 FPS，需区分数据采集速率、绘图节流和宿主浏览器性能。当前仓库 README 的“阶段一未包含采集与绘图”概述落后于源码；读取频率与绘图频率不是同一个参数。

**方案 / 实施步骤**:
1. 先查架构文档和 operation 注册表，建立完整能力边界；再查前端交互、状态 stores、绘图引擎和对应 disabled 控件。以 `encoder-next/web/src` 与 `encoder-next/server/encoder_next` 当前源码为准，README 阶段说明仅作历史背景。
2. 读取配置档按读取器序列号保存在浏览器本地；自动识别生成推荐命令，手动配置可调整系列、接口、波特率、总线地址、位数、读取命令和解析器。
3. 采集 start 时每个读取器当前只选第一个启用命令；读取帧按解析器计算值后写入容量受控的 ring buffer。pause 保留曲线，resume 延续横轴并打断点，stop 结束本轮。
4. 绘图在独立循环按配置频率刷新，读数路径不逐帧驱动 Vue 更新；对每个屏幕像素范围汇总 min/max，避免直接绘制几十万原始点而丢失峰值。
5. 盘点结论分为已实现/部分/未实现，并把实测范围和已知高风险写清楚。
架构：每个读取器：硬件读取 → 独立 /ws/data 帧队列 → 前端解析与 resolver 计算 → TypedArray 环形缓冲 → 按绘图频率抽取像素桶 min/max → uPlot；控制命令/状态：前端 → /ws RPC → application service → legacy/simulator gateway。Vue 3 + TypeScript 前端通过 FastAPI WebSocket RPC 控制后端；实时帧传输使用有界队列和 drop-oldest。

**验证方法**: 本次清单根据当前源码、操作接口、控件状态及已有 SIRE 真机记录交叉核对；没有在本轮启动服务或重测硬件。真机证据仅为 DPB ABS RT 2.5M、20-bit、V4.0.11 组合。独立浏览器稳定 30 FPS，而 Codex 内嵌浏览器发生卡顿，应视为宿主差异的观察结果，不归因成已证明的通用结论。

**踩坑 / 已知异常与失败经验**: - README 的阶段概述已过时；读清单前先检索实际代码和注册 operation。
- 高频采集速率与绘图刷新速率是两个维度；页面显示 30 FPS 是绘图循环，不意味着读取器仅采 30 次/秒，也不代表任意宿主浏览器都能稳定达到该帧率。
- RT 的身份标签不保证旧硬件实现存在同名线协议。已知真机组合需 RT→RS485 映射、CRC 关闭；不得把 CRC=false 推广到其他产品和固件。
- 浏览器本地配置按序列号存储，不与旧应用配置自动迁移，也不跨浏览器同步。
- 目前一个读取器只轮询第一个启用命令；配置多个启用命令不会同时采集。
- legacy 读取线程尚未隔离到独立 OS 进程。旧 analyzer 在拔线后连续读取失败达到阈值时可能 `os.kill` 父进程，属于高风险未解决项。
- CAN/CAN-FD 虽有配置字段，但尚未接入实际读取。
- 校准视图中自/基准校准控件、数据导入导出、修改参数、高低温箱、MES、IAP、文件导入导出等仍为禁用或占位；读取器配置的导入/导出按钮也未接入。
- DeviceGuard 使单个读取器操作串行，编码器再标定等操作应与该读取器读取互斥；断开读取器前先退出再标定模式并停止采集。
- 数据 WebSocket 有界队列采用丢弃旧帧以保护实时性；UI 有 frame/drop 计数，应明确采集端未丢帧和显示端平滑是不同指标。

**关键文件与接口**: `encoder-next/docs/architecture.md`；`encoder-next/server/encoder_next/transport/operations.py`（RPC operation 注册表）；`encoder-next/server/encoder_next/application/readout_service.py`；`encoder-next/server/encoder_next/transport/data_ws.py`；`encoder-next/server/encoder_next/application/reader_service.py`；`encoder-next/server/encoder_next/application/encoder_service.py`；`encoder-next/web/src/stores/readout.ts`；`encoder-next/web/src/stores/plotBuffer.ts`；`encoder-next/web/src/components/plot/plotEngine.ts`；`encoder-next/web/src/stores/formula.ts`；`encoder-next/web/src/stores/readoutProfiles.ts` 与 `defaultCommandRules.ts`。
RPC：`/ws`，数据：`/ws/data`。Operation：`readout.start|stop|status`、`readers.list|scan|get|connect|disconnect|info`、`encoder.session|probe|autofind|enter_recalibration|exit_recalibration|read_arguments`、`service.health|methods`。

**状态**: 部分完成

### P-20261082: MES业务模块只读盘点：关系、权限与工作流缺口判读
**日期**: 2026-10-28
**项目**: MES / D:/code/mes
**关键词**: MES业务模块盘点, 只读数据库盘点, lc.modules, published schema, detailLines, targetModule引用, 空值率, workflow states transitions, approvalRoleCodes, actorRoleCodes, 模块权限, 软删除模块, SN绑定, BEGIN READ ONLY

**需求场景 / 现象**: 为业务模块精简重构收集当前开发库事实，需区分已发布配置、当前记录、字段空值、模块引用、权限和工作流审批/SN绑定状态；不能把历史设计或软删除对象当作活动能力。

**方案 / 实施步骤**:
1. 以`BEGIN READ ONLY`打开数据库查询；输出数据库名和非敏感连接身份确认目标，事务结束时ROLLBACK。
2. 对活动模块取最新发布schema；把软删除模块、记录和工作流分开统计。
3. 对每个字段统计必填、类型、关联目标、使用计数与空值比例；对空数组/空对象单独视为空。
4. 汇总双向引用、父模块关系、细节行配置、权限授予及工作流状态/转换/审批角色。
5. 报告只写汇总数据和字段定义，不输出业务记录原值、凭据或用户个人信息；删除建议标为候选并说明引用影响。

**验证方法**: SQL均在`BEGIN READ ONLY`事务内执行后`ROLLBACK`；人工复核模块记录数、关联目标、工作流版本/启用状态及角色分配汇总彼此一致。运行时审批与SN绑定必须通过另行授权的真实业务操作验证，数据库配置静态读取不能证明实际可用。

**踩坑 / 已知异常与失败经验**: ①`parentModuleCode`只是schema层级配置，不能替代`reference`字段数据关系；②仅查活动模块会漏掉仍被引用的软删除模块；③平铺订单字段和`detailLines`可能双重表达同一关系；④转换角色（`actorRoleCodes`）与审批角色（`approvalRoleCodes`）不能混为一谈，`approvalMode=any`本身不代表已配置审批；⑤字段空值率高不代表必然无用，自动生成字段、未来分支和导入字段需先辨义；⑥软删除记录/工作流仍会影响追溯和角色引用保护。

**关键文件与接口**: docs/reviews/codex-盘点-业务模块.md；scripts/sire_comms.py；lc.modules、lc.module_versions、lc.records、lc.module_workflows；iam.permissions、iam.role_permissions、iam.roles

**状态**: 已完成（仅静态数据库盘点；未改数据库/代码、未测试运行时行为）

### P-20261083: MES开发库分阶段配置重构：安全备份与认证阻塞停步
**日期**: 2026-10-28
**项目**: MES / D:/code/mes
**关键词**: PostgreSQL开发库备份, pg_dump custom archive, 低代码模块服务权限, 初始管理员改密, SN绑定能力, 阶段失败停步

**需求场景 / 现象**: 按REFACTOR-02对开发库业务模块做分阶段配置重构，必须先备份并经系统服务API写配置；E0备份成功后，E1需要经认证的模块管理身份。

**方案 / 实施步骤**:
1. 先锁定代码库与开发库资源，再生成数据库custom archive（容器内`pg_dump -Fc -Z 6`）。
2. 将备份放入仓库外受限ACL目录；校验SHA-256和归档目录对象。
3. 完成备份后只读核对模块/记录/流程基线。
4. 核实API认证身份；如需未授权改密或绕过服务则停止该阶段，不写库。
5. 报告已完成阶段和未开始阶段，留出恢复条件。

**验证方法**: `pg_restore --list`列出关键低代码表数据；本地SHA-256重算与sidecar相同；只读聚合查询核对模块与记录总数。未做恢复演练、测试、浏览器验证。

**踩坑 / 已知异常与失败经验**: 当前提供的本地初始管理员凭据标注首次登录必须修改密码；任务授权没有包含修改账号凭据，不能用初始身份完成模块管理操作，也不能绕过服务直接改数据库表。不能擅自用该流程改账号密码后继续操作。`D:\backup`默认ACL允许其他本机账户修改，因此数据库归档必须置于单独受限目录。工作流transition通用前置条件不等于具有原子SN绑定服务。

**关键文件与接口**: docs/tasks/REFACTOR-01-业务模块精简方案.md；docs/reviews/codex-重构执行报告.md；mes-server/src/lowcode/modules.controller.ts；mes-server/src/lowcode/apps.controller.ts；mes-server/src/lowcode/workflows.controller.ts；mes-server/src/lowcode/workflow-runtime.ts

**状态**: 部分完成（E0完成，E1在数据写入前阻塞，E2–E5未执行）

### P-20261084: MES六核心符合性审查：明细创建权限与数量校验旁路
**日期**: 2026-10-28
**项目**: MES (D:/code/mes，feat/full-implementation，HEAD fbd24a0)
**关键词**: MES, 六条核心, 平台边界, 明细权限, 数量校验, 可视化配置, 数据可见性

**需求场景 / 现象**: 审查当前工作区是否满足用户定义的六条系统核心（只读源码交叉评审，按严重性列缺口，避免把历史报告当当前验收）。结论：不能判定满足全部六条；通用模块、字段、关联、工作流和审计机制已具备，但存在服务端权限旁路、配置规则静默失效、可视化配置缺口和业务措辞硬编码。

**方案 / 实施步骤**:
1. 只读源码交叉评审，三个独立审查单元与主控交叉核对高优先级结论。
2. 确认发现：
F1 [P1] 明细行创建漏查子模块新建权限：createRecordWithLines 只查明细模块白名单，直接调用 insertRecord，未检查子模块 create 权限。建议服务端逐个核查明细目标新建权限，拒绝则整笔事务回滚。
F2 [P1] 已配置数量校验在组成提供者缺失时静默失效：assertStock 找不到组成提供者即 return。建议发布前确认依赖完整；运行中缺失依赖应明确拒绝；停用与删除应受依赖治理约束。
F3 [P2] 组成展开及资源候选绕过目标数据可见性。建议辅助展示查询统一实施目标模块权限与记录可见性。
F4 [P2] 多套组成并存时数量字段候选取错模块（页面固定取 composition[0] 的叶子模块，执行时按所选关联字段目标匹配）。建议页面与执行端采用同一提供者解析规则。
F5 [P2] 组合列缺少可视化创建与维护入口（RelationSettings 只允许勾选普通列，将 complex 原样拼回）。
F6 [P2] 操作审计直接暴露技术编码与 JSON（l.action、JSON.stringify(l.detail)、targetType）。
F7 [P2] 平台通用界面仍写死生产业务措辞（“产品字段”“物料上的现有数量”“订单”“新建工序流程”“从列表选工序”等）。
3. 后续验收建议：先修 F1/F2，再修辅助查询可见性与配置入口；获得测试授权后，用非管理员合成账号验证父子模块权限隔离、隐藏节点数据、依赖停用时拒绝、两套组成独立配置和组合列搭建。

**验证方法**: 独立静态复核；未测试，未启动服务或浏览器。后续需正常和越权路径真实浏览器操作留证据，不能只用接口或历史测试报告代替。

**踩坑 / 已知异常与失败经验**: 结论针对当前工作区，不能等同于服务器部署版本。现有业务资料是否完整与平台本身是否通用是两类问题，不能用业务配置不足替代平台实现缺陷。历史已执行迁移、外部金蝶协议名、手册案例不能与当前内置业务逻辑混为一谈。

**关键文件与接口**: apps.service.ts、apps-rules.ts、apps-queries.ts、CapabilitiesEditor.tsx、RelationSettings.tsx；mes-server/src/lowcode/apps.controller.ts:192、apps.service.ts:84/96；apps-rules.ts:70/73；mes-admin/src/features/iam/AuditPage.tsx:105/109。

**状态**: 部分完成

### P-20261085: MES手册同步：流程目录、预检与明细保存边界
**日期**: 2026-10-29
**项目**: 原记录未记载
**关键词**: MES, 用户手册, 流程目录, 预检, 明细保存, 配置包

**需求场景 / 现象**: 按当前工作区逻辑更新后台与业务两份使用手册，中断后继续完成。

**方案 / 实施步骤**:
1. 复用已保存改稿，以当前源码为准。
2. 目录流程不再手动选版本，普通工作流仍按版本管理；记录采用创建时的流程，启用流程修改影响新记录。
3. 流转先填写再点击，当前节点字段先保存再发起；驳回必须说明原因。资源名称跟随模块。
4. 表格导入组织认编码、用户认账号，按钮叫预检。
5. 明细新建随主记录一同保存，编辑可能主记录成功而明细失败，文案不得保证整笔回滚。
6. 配置包不含业务记录和用户密码，新建用户初始密码仅显示一次。
7. 删去三张展示旧字段类型/页签/版本界面的截图引用但保留原文件。

**验证方法**: 仅静态源码与文本复核，未测试、未构建、未启动服务、未浏览器验证，未补截图。初稿由两独立作者完成，父与独立审查已交叉核对关键语义；独立终稿代理因额度失败，主控续读全文和相关源码修正已发现差异。没有虚称最终独立评审通过。

**踩坑 / 已知异常与失败经验**: 改稿期间其他会话提交了61961bb，保留该提交含手册内容，仅追加本任务收尾改正。未提交未推送，不修改版本号和CHANGELOG。

**关键文件与接口**: packages/runtime/src/help/manual-admin.ts、manual-web.ts；AppRecordDialog.tsx、AppRecordSheet.tsx、WorkflowManager.tsx、ModulePackageActions.tsx、AppImportDialog.tsx；docs/PROGRESS.md

**状态**: 已完成

### P-20261087: MES七项差距通用实施方案及验收边界
**日期**: 2026-10-29
**项目**: MES (D:/code/mes)
**关键词**: MES 通用计算 条件构建器 联动写入 原子主从保存 资源脱敏 批量创建, MES 六核心 可视化计算 条件分支 扣减 明细保存 资源可见性

**需求场景 / 现象**: 用户要求将既有七项差距的实现思路整理成列表（方案分析，不修改仓库，不测试）。前置复核 P-20261086：当前缺可视化数值及日期计算、基于本记录字段比较的流程条件；已有扣减直接更新目标，未完整执行目标字段整数/min/max校验及目标记录审计；编辑主从记录逐请求保存可能部分成功；批量新建与明细并用时后端优先明细而忽略count且前端成功数可错误；资源占用方节点可见性未用于占用提示；界面残留产品/物料/出库等固定业务措辞。必须区分能力缺口与已有能力正确性问题；此前明细创建权限、无组成提供者校验、展开入口权限、资源目标节点可见性已有修复，不应重复列为缺失。

**方案 / 实施步骤**:
实施顺序：统一联动写入/主从事务/资源权限，批量组合，条件与计算，界面文案可并行。
1. 统一受控写入覆盖数量联动，来源动作与目标字段授权有限化，校验目标类型精度上下限封存与关联规则，记录操作者、来源、前后值；同事务补偿改量、换目标、删除，防循环、死锁及重试重复扣减。
2. 主从编辑一次提交，同事务增改删，校验主子版本、真实归属、各操作权限、可见性、封存；未提交项不默认删除，最终合计统一验证。
3. 占用判断全量保留，提示按占用记录权限脱敏，统一列表和冲突出口。
4. 批量带明细默认为每条主记录复制一组独立明细，页面显式告知数量与总行数，服务端统一处理count和lines，限制总量，全部回滚，成功数来自实际结果。
5. 通用条件构建器支持字段与常量/字段比较、类型化操作、全部/任一；发布检查引用有效性，服务端流转及审批执行前复核，多个出口满足时用户选择，自动分流另行明确优先级。
6. 可视化计算支持四则与日期运算，用受限结构表达而不执行脚本，依赖排序与环检测，明确空值、除零、精度、时区、重算/锁定，前端预览后端权威计算，各写入渠道统一，旧记录不静默批量重算。
7. 清理固定业务措辞与内部编码展示，名称取用户配置，行业示例仅手册标明案例。同步双手册、能力文档及用户可感知变更记录。

**验证方法**: 方案静态分析完成，独立复核已覆盖并发、幂等、归属、权限、事务、联动环和脱敏出口。未实现、未测试，后续获授权在浏览器走配置到运行全流程。只读静态审查，不运行测试、构建、服务或浏览器；当前工作区持续变化，结论不等于部署环境验收。

**踩坑 / 已知异常与失败经验**: 必须区分能力缺口与已有能力正确性问题；当前工作区持续变化，结论不等于部署环境验收。

**关键文件与接口**: record-values.ts；apps.service.ts；apps-rules.ts；apps-queries.ts；schema-types.ts（:144）；FieldProperties.tsx；TransitionRules.tsx；AppRecordDialog.tsx；apps-base.ts:266；apps.controller.ts:198。

**状态**: 部分完成

### P-20261088: MES系统手册补齐功能说明与完整分步案例
**日期**: 2026-10-29
**项目**: 原记录未记载
**关键词**: MES 使用手册, 功能描述, 完整案例, 分步操作, 结果核对, 双入口

**需求场景 / 现象**: 用户明确使用手册必须描述功能，并用完整案例一步一步说明如何完成目标；不能只罗列配置项或给一两句使用概述。

**方案 / 实施步骤**:
1. 在现有系统内两份手册补充案例，不新建另一套手册，不改渲染。
2. 案例覆盖目标、前提、具体示例输入、可见入口和按钮、编号步骤、保存发布/授权、结果核对与遇阻处理。
3. 后台负责角色组织、模块字段关联、规则和流程搭建；业务端负责实际录入查询、上传、导入、办理审批及追溯，流程维护仅对获维护权限者说明。
4. 贯穿案例统一为自建“资料登记”，字段名称、类别（普通资料/需复核资料）、登记日期、资料附件；角色录入员/复核员；流程登记中到已完成（封存），流转提交复核，可选提交说明，必填复核意见。示例明确为案例而不是系统固定业务。
5. 后台补齐其余功能的操作案例并加入贯穿主章；角色开关、目录新建权限、导入只新增提示已修正。新增块使用原有内容结构多行保存。

**验证方法**: 只读源码和差异复核，不运行测试、构建、服务、浏览器或校验脚本。独立复核发现并反馈：首次改密按钮为保存并进入系统，添加节点会自动接线应避免重复连线，同步天数标签按实际，两个入口贯穿案例名称必须一致。

**踩坑 / 已知异常与失败经验**: 当前有并行功能改动，应保留其已有手册变化，不把前次规划自动描述为已实现。纯文档不新增CHANGELOG，不改版本与tag，不更新截图。仅两份手册及必要PROGRESS交接记录有本任务改动，未修改系统功能代码；未执行界面刷新。

**关键文件与接口**: packages/runtime/src/help/manual-admin.ts；manual-web.ts；docs/PROGRESS.md；源码依据：ModuleDesigner.tsx、WorkflowEditor.tsx、WorkflowManager.tsx、AppRecordSheet.tsx、AppRecordDialog.tsx、StepPickerDialog.tsx、SyncBar.tsx、ForceChangePasswordPage.tsx

**状态**: 已完成

### P-20261090: 扭力标定未达标人工放行与重标分流
**日期**: 2026-10-29
**项目**: driverSoftware
**关键词**: 扭力标定, 人工确认放行, 重新标定, 不合格原因, confirm_unqualified, manual_release_allowed, Kt, R², 自动写入, 手动确认, 质量门禁, 连接代次

**需求场景 / 现象**: 扭力标定：产线反复看到手动确认写系数，需优化完成与保存流程；用户后续补充要求不合格明确原因，由人选择放行还是重标，替代上轮一律拒收的产品决策（本条更新“不合格一律重标”决策）。原实现低R²仍发kt_ok，前端先提示完成再要求手动写；写接口未校验质量和读回。自动质量判据与人工处置是两件事，人工采用结果不应伪装为自动验收合格。

**方案 / 实施步骤**:
1. 保留0.97阈值；调整终态与质量门禁：低R²发带报告的失败事件供界面展示曲线；合格自动保存并读回核对后才提示完成；失败只提供保存合格系数重试，不弹二次确认。
2. 写接口绑定采集起始设备和连接代次，拒绝无结果、低R²和篡改系数；写失败不继续保存。启动、保存、连接、断开、换靶加RLock互斥。
3. 人工放行：仅完成全部前置检查、算出有限正系数但R²低于0.97时，报告允许人工复核；失败界面显示原因和曲线及放行/重标入口。人工放行二次确认原因与系数，写接口须confirm_unqualified=true和本轮manual_release_allowed=true，保留设备身份、停机、保存读回校验。保存成功黄色显示人工放行并写诊断日志，质量仍未通过。中止和无有效结果不允许放行。
4. 前端保存状态、失败重试及双语文案更新；更新指南、CHANGELOG、测试夹具；新增未确认拦截/无效结果/中止不可放行回归用例以及拒写和读回差异用例。

**验证方法**: 仅执行Python AST、JS语法、JSON解析和差异静态检查；独立review三轮审查，发现拟合末尾中止仍可能携带候选，已在结果签发前检查中止且kt_abort返回report=None，复核无新阻塞。未运行测试、服务、浏览器或真机；待用户授权后验证合格保存、低R²拒收、保存/读回失败重试及换靶互斥。

**踩坑 / 已知异常与失败经验**: 终态读取全局设备身份会把结果归错设备；必须在开始采集时捕获，再以连接代次复核。用户中止不能被当作可人工放行的低质量结果；二次确认期间锁住本页开始/重标动作，避免确认旧结果后写新结果。

**关键文件与接口**: core/kt_worker.py；server.py（/api/kt/start、/api/kt/write、KtWriteReq、_kt_on_event、api_kt_write）；frontend/js/api.js；frontend/js/pages/torque.js；frontend/locales/zh.json 与 en.json；tests/unit/test_kt_write_stop_guard.py；指南；CHANGELOG。

**状态**: 部分完成

### P-20261091: 保留原始提交补建主题分支真合并
**日期**: 2026-10-29
**项目**: driverSoftware
**关键词**: 主题分支, no-ff, 已推送提交, 保留SHA, 真合并, git flow

**需求场景 / 现象**: 两个修复提交直接进入development并推送后，用户要求改成fix分支实现再真合并。此仓正常开发须先建主题分支，不应直接提交development。

**方案 / 实施步骤**:
1. 先确认工作区干净、上游及远端未前进、主题分支不存在。
2. 在原末提交建立fix/torque-calibration-review。
3. 工作区干净且无后续提交时，在该分支上将本地development指针调整至两个提交之前（git branch -f；不能在已签出development时强改它的ref，先切到主题分支）。
4. 再切回development用--no-ff合入fix分支。最终merge保留原末提交为第二父，因此原远端HEAD仍是新HEAD祖先，可正常快进推送，不需要强推或重写已有提交。
5. 独立核对父节点、树及SHA；正常推送已授权的origin/development。

**验证方法**: 独立只读复核2155916d双亲为220b6aef和3183fb21，bcb25d22与3183fb21原SHA保留；git diff 3183fb21 HEAD为空；推送3183fb21..2155916d成功且HEAD与origin/development一致，工作区干净。未运行功能测试（无代码变化）。

**踩坑 / 已知异常与失败经验**: 根因：本次忽略项目主题分支规范；应优先遵循用户明确指定的项目分支规则，不能仅凭当前分支直接开发。本例仅适用末端连续提交且工作区干净；若后续有他人提交不可照搬。保留主题分支，不推送未获授权的其他ref。

**关键文件与接口**: Git refs/heads/development、refs/heads/fix/torque-calibration-review；git branch -f、git merge --no-ff、git diff、git push

**状态**: 已完成（本地主题分支保留，development已正常推送，未强推）

### P-20261092: 断连重复中止导致发布门禁失败的最小修复
**日期**: 2026-10-29
**项目**: driverSoftware
**关键词**: v0.21.2, CI门禁失败, disconnect, request_abort, abort_calls, 重复中止, api_disconnect, test-gates

**需求场景 / 现象**: 用户提供Runner日志，正式发布在test-gates失败，2 failed、2800 passed、36 skipped，未进入正式打包。

**方案 / 实施步骤**:
1. 阅读用户附件全文。
2. 核对函数全部收尾与既有五条测试。
3. 新建主题分支 fix/kt-disconnect-abort-once。
4. 最小删除：仅删除入口重复调用两行，保留原有pipeline和Kt统一中止、互斥锁、结果清理及连接代次。
5. 独立静态复核并提交（提交4256d683）；未发布CHANGELOG记录出包修复。

**验证方法**: 仅Python AST和git diff --check静态检查通过；独立复核确认仅一处有效Kt中止。未运行测试，待用户明确授权断连与Kt回归；通过后建议按原发布任务继续真合并、发v0.21.3，不覆盖v0.21.2标签。

**踩坑 / 已知异常与失败经验**: 根因：bcb25d22中在api_disconnect入口新增Kt request_abort，未发现函数后半已有统一worker中止；仅Kt运行和双worker运行用例均观察到abort_calls=2而预期1。修改生命周期收尾前读完整函数，不能仅看到入口缺保护就重复添加。不能把实际门禁代码缺陷当成打包工具问题，也不能改测试预期掩盖重复调用。版本与旧标签不动，未推送或触发构建。

**关键文件与接口**: server.py api_disconnect；tests/unit/test_disconnect_stops_workers.py:53与65；CHANGELOG.md

**状态**: 部分完成（代码修复与静态复核完成，未测试，等待测试授权；修复分支保留）

### P-20261093: 自动流转候选分页和关联传播修复
**日期**: 原记录未记载
**项目**: 原记录未记载
**关键词**: 原记录未记载

**需求场景 / 现象**: 范围两处自动流转修复：候选分页与关联传播。原记录场景细节未记载（旧记录无直接实现可复用）。

**方案 / 实施步骤**:
1. 稳定 ID 分页。
2. 模块变化队列。
3. 共享每记录10步预算。
4. 自动生成目标模块加入传播。

**验证方法**: R6 独立复核首轮无新增P1，指出生成目标传播遗漏，已补齐。R7 DEFERRED 待用户授权测试。待测：201+候选、跨模块三级及同模块反序依赖、生成记录依赖、循环10步、审批/封存边界。

**踩坑 / 已知异常与失败经验**: 风险：大量候选在同步事务中检查，耗时未测。首轮实现遗漏了自动生成目标模块的传播，R6 复核发现后补齐。只改源码与对应文档，无运行数据变动。

**关键文件与接口**: 原记录未记载

**状态**: 部分完成（实现与R6复核完成，测试待用户授权）

### P-20261094: ERP即时库存导入本机MES口径与完整性核对
**日期**: 2026-10-29
**项目**: MES（本机 Docker mes-postgres）
**关键词**: ERP即时库存, 本机MES, PostgreSQL, mes-postgres, LC_NOTHING_TO_PUBLISH, 库存明细, 对账, 数据导入

**需求场景 / 现象**: 用户授权将ERP即时库存导入本机Docker mes-postgres PostgreSQL16 localhost5432 mes，mes_app服务连接；明确覆盖仓库旧测试库口径。用户选择仅可用状态的可用库存量参与用料校验和扣减，其余全部保留明细。

**方案 / 实施步骤**:
1. R0-R4 完成检索、范围与口径确认。
2. 导入前备份数据库：D:/code/mes-backups/erp-stock-20261029-113311.dump（850513 bytes）。
3. R5执行：通过API修改配置和数据，禁止直接改表；原始29列另建ERP库存明细模块。
4. 补建47物料，本地物料总1986；本次更新567条；明细4339行，序号唯一4339。
5. R6独立代理只读复核核心转换；重跑发布无变化错误已捕获LC_NOTHING_TO_PUBLISH。

**验证方法**: 全量API对账872物料数量无差异；明细编号/状态/库存及可用数量无差异；本机页面显示4339条。来源4339行872编码；47编码本地缺失；字段元数据无冲突，单位相同，小数最多4位，数量精度调整6。

**踩坑 / 已知异常与失败经验**: 数据配置脚本在仓库外，不能提交业务数据进系统源码。ERP明细是2026-10-29快照，不自动同步ERP后续变化。未进行功能测试，仅执行授权导入及数据对账；备份保留；无源码修改。

**关键文件与接口**: D:/code/mes-backups/erp-stock-20261029-113311.dump；mes_app；3100/5175/5176

**状态**: 已完成

### P-20261095: 流转填写由流程配置，移除默认重复备注
**日期**: 原记录未记载
**项目**: 原记录未记载
**关键词**: 原记录未记载

**需求场景 / 现象**: 用户要求删除系统默认流转备注，由流程自行定义填写内容。

**方案 / 实施步骤**:
1. 范围AppRecordSheet及手册CHANGELOG和进度；不改配置数据、历史和审批驳回规则。
2. 移除流转备注Textarea以及流转请求comment，避免审批残留共享comment进入流转；自定义inputs必填校验保留。
3. 两份手册同步，同日updatedAt保持2026-10-29。

**验证方法**: R6独立代理复核通过：自定义填写、必填、审批备注、驳回原因及历史展示均保留。R7跳过待用户授权测试，R10跳过未做浏览器验证；R8静态核对一致，R9完成。未测试、未构建、未提交。

**踩坑 / 已知异常与失败经验**: 审批残留共享comment会进入流转，所以需同时移除流转请求comment。

**关键文件与接口**: AppRecordSheet；手册、CHANGELOG、进度

**状态**: 已完成（静态复核通过，未测试未提交）

### P-20261096: 指派执行人选择框回显修复
**日期**: 原记录未记载
**项目**: 原记录未记载
**关键词**: 原记录未记载

**需求场景 / 现象**: 执行人已保存但下拉框被清空。

**方案 / 实施步骤**:
1. AssignPanel 保存后保留值，并随记录、节点和已指派人员同步。
2. 候选外已指派人员仍显示姓名。
3. 同步使用手册、CHANGELOG、PROGRESS。

**验证方法**: 独立 R6 静态复核通过。未运行测试、构建或浏览器验证，未提交。

**踩坑 / 已知异常与失败经验**: 原记录未记载根因；现象为保存后下拉框被清空。

**关键文件与接口**: AssignPanel；使用手册、CHANGELOG、PROGRESS

**状态**: 已完成（静态复核通过，未测试未提交）

### P-20261097: 总线识别报告身份保持与连接隔离
**日期**: 2026-11-03
**项目**: driverSoftware
**关键词**: driverSoftware, 总线设备, 识别测试报告, ID变更, 连接隔离, CSV

**需求场景 / 现象**: 多设备通过同一个读取器接入，界面需要记录每台首次识别ID、当前ID、物理标签和写入核对结果。ID本身可以变化，如果直接用当前ID作为报告主键，改号后会变成另一台设备，丢失首次ID和物理标签。等待后端响应期间用户也可能断开连接或更换读取器。

**方案 / 实施步骤**:
1. 以浏览器会话内独立报告对象保持身份，扫描行持有报告对象引用，写ID和波特率成功后更新同一对象；首次识别ID保持不变。
2. 物理标签存localStorage，键包含首次ID和初始波特率。
3. 写入后自动完整重扫，确认新ID在线、旧ID消失，并检查扫描检出的重复ID；失败或不完整扫描不能通过。
4. 异步扫描和写入返回后核对连接键，避免旧响应污染新连接。
5. CSV使用UTF-8 BOM并转义单元格引号和公式前缀。

**验证方法**: 完成JS语法、语言JSON解析及git差异空白静态检查，独立复核发现并修复播种重复漏报、请求失败未记结果、跨连接响应污染。未测试GUI、真机或Excel，由Claude进行真机验收。

**踩坑 / 已知异常与失败经验**: 扫描接口仅返回id和baud，无舵机序列号，因此留空。同ID同波特率的多个设备可能无法被扫描区分，界面必须说明未检出不代表没有冲突。首次识别ID并非固件提供的真实出厂属性。

**关键文件与接口**: frontend/js/pages/device-bus.js；frontend/locales/zh.json；frontend/locales/en.json；server.py中的probe_all_bauds和_batch_one。

**状态**: 部分完成

### P-20261098: 多设备轨迹热更新必须防止过时配置恢复使能
**日期**: 2026-11-03
**项目**: driverSoftware
**关键词**: mscope, 多设备轨迹, MIT, 热更新, 急停, 轮次锁, 过时配置, 起播预检, round_lock

**需求场景 / 现象**: 在现有多设备采集轮询线程中增加统一起点轨迹，不另开回放线程。各台共享总线，只能逐台串行发MIT；预检需要读取设备档案，期间用户可能全部失能或更换会话。

**方案 / 实施步骤**:
1. 统一锁顺序为round_lock再配置lock。
2. 轮询在线程持有round_lock后才抓取配置，热更新和显式停止也持有同一轮次锁。
3. 档案I/O不持有round_lock，避免把看门狗保活帧堵住。
4. 热更新进入预检前捕获cfg对象及各台enabled，发布时重查，任何变化拒绝并让调用方刷新重试。
5. 轨迹起播预检逐台生成临时轨迹表，最后一次性发布；发布前核对连接代次与原采集线程，防止跨会话写入。

**验证方法**: 仅做python静态编译与git差异空白检查，独立R6静态复核。tests/unit/test_mscope_trajectory.py 已编写（含插值、起点阶跃、平移越界、批量原子性、热更新和会话替换守卫用例）但未运行，未启动服务或电机。

**踩坑 / 已知异常与失败经验**: 根因：只在发帧阶段持有轮次锁，但在锁外抓取targets，会让急停之后旧快照继续发送MIT；即使发帧快照已受保护，热更新在预检期间若发生停机，旧HTTP请求仍可能把enabled=True重新发布。两类竞态都必须防止。限制：lag_ms在主机调用c.mit之前取时，相对轮次理想调度点计算，不代表读取器硬件出线时间；多设备本质仍串行发帧，不能声称硬件同时发送。

**关键文件与接口**: server.py：api_mscope_start、api_mscope_traj_start、_mscope_loop、api_mscope_traj_stop、_mscope_traj_prepare、_mscope_traj_value；tests/unit/test_mscope_trajectory.py

**状态**: 部分完成（实现完成，未测试）

### P-20261099: 多设备轨迹结束状态不能由陈旧样本推断
**日期**: 2026-11-03
**项目**: driverSoftware
**关键词**: 多设备轨迹, drain, 完成通知, hold, stop, 陈旧样本, 急停, confirmation epoch, 指令位置对比

**需求场景 / 现象**: 多设备轨迹时长不同，前端增量drain取样本与后端最新轨迹元数据可能不同步：短轨迹已经结束，但本批增量样本还停留在之前的MIT帧。界面需区分结束后自动失能与保持末点，不能把自动停机报成故障或保持使能。仅凭全局traj.running和该台最后一个样本mode推断结束方式，在长轨迹仍运行时会把已结束短轨迹误判成hold，并永久标记已通知。使能确认框也可能在急停后才得到确认，旧异步回调会重新使能设备。

**方案 / 实施步骤**:
1. 成功起播后保留本次end模式。
2. stop完成通知等待该台Default样本，再把本地enabled复位；hold依据已确认的结束模式提示保持末点。
3. 停止、急停及面板卸载递增controlEpoch，单台使能/全部使能/起播的异步确认后核对epoch、采集状态和目标选择，旧操作失效；已在进行的阶跃观察也核对epoch，急停后不恢复旧指令。
4. 指令位置cmd_pos与实测pos共享uPlot scale；合并相对图必须减去同一个实测起点。
5. CSV解析沿用列别名和分隔符，但拒绝缺列、空值、非递增时间，不静默改变控制轨迹。

**验证方法**: 仅做JS语法、语言JSON和差异静态检查，独立R6复核通过。离线CSV解析脚本已编写未运行，未启动服务或浏览器。界面真机验收交由Claude。

**踩坑 / 已知异常与失败经验**: 合并相对图指令位置与实测位置不能各自归零，否则会掩盖跟踪误差。不要用陈旧样本推断结束状态。

**关键文件与接口**: frontend/js/multi-scope.js中startTrajectories、updateTrajectory、setEnabled、allOn、stepAll、allOff、drainLoop；frontend/js/api.js的mscopeTrajStart和mscopeTrajStop。

**状态**: 部分完成

### P-20261100: 序列号标签迁移须区分存储值与当前输入
**日期**: 2026-11-03
**项目**: driverSoftware
**关键词**: localStorage, 序列号, 物理标签, QuotaExceededError, 内存缓存, SN键迁移

**需求场景 / 现象**: 识别报告首次扫描仅知道ID，用户先填写物理标签；读版本后获得真实SN，需要把标签存储键从ID迁移到SN。浏览器配额满时可能还能读取旧值，但无法保存新输入（QuotaExceededError）。读取标签时若始终优先localStorage，会在setItem失败后用存储旧值遮盖用户已写进内存的新标签；SN从旧设备变成新设备时，如果仅改键而继续复用缓存，又会把旧物理标签显示给换件。

**方案 / 实施步骤**:
1. entry.label作为当前会话已加载/编辑值优先读取，尚未初始化才从localStorage加载。
2. SN发生变化时删除entry.label缓存，再按目标SN键加载。
3. 首次从无SN迁移到有SN时，原ID标签可迁移到SN键，但目标SN已有保存值优先；确认持久化后删除旧ID键。已知旧SN切到新SN不迁移旧设备标签。
4. 后端sn为null展示空，不编造SN。

**验证方法**: 独立R6静态审查发现并修复配额满后的标签回退错误；JS语法、语言JSON和差异检查通过。未实际运行localStorage配额/换件用例，未启动服务或浏览器；真机验收交Claude。

**踩坑 / 已知异常与失败经验**: 读取标签时不能始终优先localStorage（配额满时会遮盖新输入）；换件时不能复用旧SN缓存。

**关键文件与接口**: frontend/js/pages/device-bus.js：labelKey、labelOf、updateReportSerial、runOp(read_version)；server.py批量read_version返回sn；识别报告序列号及CSV使用entry.serial。

**状态**: 部分完成

### P-20261101: 多设备持续控制的急停需要请求预约与处理代次共同收口
**日期**: 2026-11-03
**项目**: driverSoftware
**关键词**: 多设备控制, 急停, HTTP预约, ContextVar, 并发, 落停, 过时响应

**需求场景 / 现象**: 多设备轮询会在后端持续发 MIT，因此单台 Default 或前端开关复位并不等于停止。启动请求的预检可能跨越急停；原配置前后都处于失能时，仅比配置内容看不出急停发生过。扫描先进入再启动采集时，单次检查运行标志也不能保护在途请求。前端切页时若启动仍未返回，按 running 判断会漏掉这条请求，旧响应还能启动轮询并遗留资源。

**方案 / 实施步骤**:
1. 后端统一急停入口等待线程落停，join超时明确失败并阻止拆换连接。
2. 停止、全部失能和轨迹停止递增控制代次，预检发布核对控制及连接代次。
3. HTTP中间件在同一短锁登记外来请求和启动预约，ContextVar传递预约时的控制代次，覆盖急停先于处理函数的时序；停止和失能保留通道。线程异常统一finally落停。
4. 前端跨实例串行控制请求，对旧响应核对代次与存活，停机未确认保留互锁且支持重试；切页/断开也处理pending start。

**验证方法**: 独立R6发现误插总线闸造成未定义变量，已移回正确函数；最终语法、语言键和diff静态检查通过。未执行pytest、CSV检查脚本、服务、浏览器或真机，不能宣称急停/窗口渲染已验收。应以2至3台不同波特率真机在可见界面补测起停/切页/断开/失联与hold/stop。

**踩坑 / 已知异常与失败经验**: 单台 Default 或前端开关复位不等于停止；仅比配置内容看不出急停发生过；切页时按 running 判断会漏掉未返回的启动请求。独立R6发现误插总线闸造成未定义变量。

**关键文件与接口**: server.py、frontend/js/multi-scope.js、tests/unit/test_mscope_safety.py、test_mscope_trajectory.py、test_mscope_csv.mjs。

**状态**: 部分完成

### P-20261102: 停止采样时必须失效末帧运行徽章
**日期**: 2026-11-03
**项目**: driverSoftware
**关键词**: 急停, 多设备, 状态徽章, 末帧失效, loopGen, 未知状态, kStopped, kRunning, drain, paintVals

**需求场景 / 现象**: 三台设备真机验收中，急停后设备实际已处于kStopped且后续没有重新使能，但卡片仍显示最后采样的kRunning。急停停止后台线程也停止了后续drain，最后一帧状态不会被新数据覆盖，用户会误判急停失败。

**方案 / 实施步骤**:
1. 在统一stop函数使loopGen递增、废弃在途drain响应之后，将每台运行时对象last.state清为空值。
2. 通过现有paintVals语义隐藏状态徽章；保持历史曲线与其余读数。
3. 后续重新开始采集时再以实际回包更新。急停先全部失能再stop，与手动停止读取共用此路径。
4. 没有新回包时显示未知，不新增可能受互锁影响的总线读回请求，也不伪造停止态。

**验证方法**: 独立R6沿stop、drainLoop和paintVals检查：代际校验可阻止旧响应覆盖清空结果，缺少refs的设备安全返回，state为空时徽章隐藏。node语法检查及diff静态检查通过；本次未执行浏览器、服务、功能或真机测试，界面最终验收交Claude补做。

**踩坑 / 已知异常与失败经验**: 不能用前端enabled=false或停止接口成功直接推定设备已kStopped，因为控制请求、设备实际状态和读回确认是三层证据。

**关键文件与接口**: multi-scope.js；CHANGELOG；提交7cf89c2b（未push）；stop、drainLoop、paintVals、last.state、loopGen

**状态**: 部分完成（静态复核通过，功能测试未执行）

### P-20261104: Windows Runner 上 CI 的 ssh 私钥报 UNPROTECTED PRIVATE KEY FILE，及其引出的私钥文件残留
**日期**: 2026-11-05
**项目**: quality-testing/dv3-admin（GitLab CI，Windows shell Runner）
**关键词**: UNPROTECTED PRIVATE KEY FILE, Bad permissions, icacls, USERNAME, 机器账号, SID, S-1-15-3, S-1-5-18, File 变量, WriteAllText, Remove-Item, takeown, 私钥残留, ssh Permission denied publickey

**需求场景 / 现象**: deploy 阶段 ssh 报 `Bad permissions ... UNPROTECTED PRIVATE KEY FILE! This private key will be ignored`，随后 `Permission denied (publickey,password)`。之后一次 job 又报 GitLab 无法写入 SSH_PRIVATE_KEY（`WriteAllText ... 拒绝访问`），job 结束清理时 `Remove-Item` 也被拒绝。

**方案 / 实施步骤**:
1. 不改 GitLab 生成的原文件权限。
2. 脚本开头对原文件 `takeown /f` 加 `icacls /reset` 自愈历史残留。
3. 把私钥复制到 TEMP 下按 CI_JOB_ID 命名的副本，只对副本执行 `icacls /inheritance:r` 与 `icacls /grant:r "*<当前身份SID>:(F)"`（取不到 SID 回退 S-1-5-18）。
4. ssh 用副本，`finally` 中删除副本。授权用 SID 而不是用户名；给 FullControl 而不是只读，保证可被清理。

**验证方法**: 本地用假私钥与桩 ssh/scp 在 Windows PowerShell 5.1 验证了正常与“只给 SYSTEM 只读”的残留两种情况，副本权限、清理、自愈均符合预期，本地不是 SYSTEM 身份；线上流水线 5686、5688、5689、5690 deploy 成功。

**踩坑 / 已知异常与失败经验**: 根因：① Runner 以 SYSTEM 类账号运行，`$env:USERNAME` 是“机器名$”，`icacls $key /grant:r "${env:USERNAME}:R"` 报“帐户名与安全标识间无任何映射”，权限没收紧，文件上还带 S-1-15-3-* 应用容器 SID，ssh 判定权限过宽并忽略私钥。② 后来直接对 GitLab 生成的 File 变量文件收紧权限并只给只读，GitLab 此后既不能覆盖也不能删除它，文件残留在 Runner 磁盘上。曾有两次日志里 `$sid` 为空（根因见 P-20261105，但并未完全解释）。经验：CI 里处理私钥一律“复制副本再收紧”，不要动平台生成的 File 变量原文件；要给自己授权时用 SID。

**关键文件与接口**: icacls；takeown；CI_JOB_ID；SSH_PRIVATE_KEY File 变量；TEMP 下私钥副本

**状态**: 已完成（已修复，4 次流水线验证通过）

### P-20261105: 中文提交信息会破坏 Windows Runner 的 PowerShell 变量注入，使脚本里的变量变空
**日期**: 2026-11-05
**项目**: quality-testing/dv3-admin（GitLab CI，Windows shell Runner）
**关键词**: CI_COMMIT_MESSAGE, CI_COMMIT_DESCRIPTION, 变量注入, 中文提交信息, GBK, CP936, 无 BOM UTF-8, 表达式中包含意外的标记, 变量为空, $py, $sid, $work, ASCII 提交信息

**需求场景 / 现象**: 流水线 5685 的 build-agent-exe（脚本没改）失败，日志开头一串 `表达式或语句中包含意外的标记 'ci:'`、`缺少字符串终止符`，其中位置指向 `$CI_COMMIT_DESCRIPTION="..."`、`$CI_COMMIT_AUTHOR=...`；随后 `& $py` 报 BadExpression，`Set-Location` 路径找不到，即脚本里的变量为空。此前 deploy 阶段的 `$sid`、`$work` 为空很可能也是同一类问题。

**方案 / 实施步骤**:
1. 提交信息（标题和正文）一律使用 ASCII 英文。
2. 出问题后用 ASCII 空提交或对同一提交手动触发即可。
3. 使用 API 手动触发同一提交（例如 92ad00b8）也能绕开，因为提交信息是 ASCII。

**验证方法**: ASCII 提交 92ad00b8 触发的流水线 5686、5688、5689、5690 均成功。

**踩坑 / 已知异常与失败经验**: 根因（部分确认）：Runner 在执行脚本前，把所有 CI 变量（含提交信息）写成 `$VAR="..."` 的 PowerShell 语句；Windows PowerShell 5.1 按系统 ANSI 代码页（本机与 Runner 为 CP936）读取无 BOM 的 UTF-8 文件，部分中文提交信息的字节会把字符串边界弄乱，整段注入出现语法错误。本地复现：把 7 条提交的信息按此方式构造并用 PowerShell 解析，只有 f4f368d9（含“，”、“并输出路径诊断”等）解析失败。限制：具体是哪几个字节触发解析失败没有查明；流水线 5684（提交 45158fc4）本地模拟解析是通过的，但线上 `$work` 为空，该次空值不能完全由此机制解释，另一个可疑因素是上一次残留的私钥文件（见 P-20261104），未进一步区分。经验：在 Windows PowerShell Runner 上，提交信息不要带中文（含全角标点）；脚本里变量莫名为空、日志开头有一串变量赋值语法错误时，先看提交信息。

**关键文件与接口**: CI_COMMIT_MESSAGE；CI_COMMIT_DESCRIPTION；CI_COMMIT_AUTHOR；GitLab CI Windows shell Runner

**状态**: 已完成（已定位并有本地复现；采用英文提交信息规避，线上验证通过）

### P-20261106: DPT V4.2.8真实采集请求CRC与读取器信息线布局
**日期**: 原记录未记载
**项目**: encoder-next（EncoderPlotter，RUN R20261107-204528-encoderplotter-0903-01）
**关键词**: encoder-next, DPT, AnalyzerInfo, CRC, 真机, 采样频率

**需求场景 / 现象**: 用户要求真实设备验证并调试，不再用模拟数据。COM3 SN20260420173117，DPT103/ABS RS485202/24bit/multi0，固件h1=4,h2=2,h3=8,h4=0。

**方案 / 实施步骤**:
1. 真实读取器信息17字节，首字节状态0，后16字节date/time/hardware/software，日期按每月31格编码而非自然天数。
2. 按固件analyzer_code c6bf7e7核对后修正共享结构和读取前缀，读回hw2.0/fw4.0/build2026-04-16。
3. 0x43请求附加CRC会截断响应，关闭请求CRC后完整8字节且响应CRC8余数0；默认配置只覆盖这个已核实自动身份和固件组合，其他固件/手动不推广。已有保存配置须显式重新生成。

**验证方法**: 真实UI1kHz 90秒90024帧，全部8字节，CRC错误0、客户端丢帧0、批次断档0；暂停继续切页停止通过。20kHz5秒76174帧约15.2kHz，未达速，不能宣称20k通过。12项通过/1失败/5BLOCKED。qa_api157+8subtests/server91通过，前端build通过。最终encoder idle、reader available、8780无监听、COM3可独占。

**踩坑 / 已知异常与失败经验**: 未覆盖双机/物理拔插/参考角度速度/完整绘图30min/实际能力拒绝负例；产品通道尚未自行校验响应CRC，临时脚本校验不可代替产品保护。台账在收尾时补录，不能表示前置阶段已及时登记；独立复核请求#71与交付#73已发Claude，未收到结论；剩余速率等问题见报告，不标全部完成。

**关键文件与接口**: controller/python/sub_common/DataFormatter.py；sub_embedded/Analyzer.py；qa_api/tests/test_analyzer_info_wire.py；encoder-next/web/src/stores/defaultCommands.ts；encoder-next/docs/hardware-test-report.md。

**状态**: 部分完成

### P-20261107: 读取器日期每月31格编码的月末与非法日历边界
**日期**: 2026-11-08
**项目**: encoder-next（EncoderPlotter）
**关键词**: AnalyzerInfo, 日期, divmod, 31日, 固件, 月末

**需求场景 / 现象**: Claude独立复核指出P-20261106的日期解码在31日产生day=0，导致读取器版本查询失败。固件原值按(y*12+零基月)*31+实际日号编码，不能把日号视作0基。

**方案 / 实施步骤**:
1. 加回基准编码后divmod(encoded,31)。
2. 余数0时months减1且day置31，随后拆年/月。
3. 仍交datetime.date验证真实日历：12月31日也会回退到上一年正确月份，30天月份31日仍报错。

**验证方法**: 新增14例涵盖七个大月31日含跨年、闰年2月29日，以及四个小月31日、非闰年2月29日、2月31日拒绝。聚焦41通过，qa_api全量171通过+8subtests，1条既有httpx弃用警告。仅单测，未连接设备；上一轮真实硬件90秒证据仍有效，但这些日期边界不是额外真机验证。

**踩坑 / 已知异常与失败经验**: 不要用自然日期加减把无效日期滚到下一月。未改web、未提交，回复Claude #75待二轮复核。

**关键文件与接口**: controller/python/sub_common/DataFormatter.py；controller/python/qa_api/tests/test_analyzer_info_wire.py；encoder-next/docs/hardware-test-report.md。依据analyzer_code c6bf7e7 Devices/analyzer.h:29–30、67–72。

**状态**: 部分完成

### P-20261108: EncoderPlotter 分支管理对照 Gitflow 审计：4.11.1 撤回后收口断裂与分支积压
**日期**: 2026-11-09
**项目**: EncoderPlotter（主仓 D:/code/EncoderPlotter_0703_03，子仓 sub_embedded/sub_common/sub_automation/sub_algorithm）
**关键词**: gitflow, git flow, 分支管理, 回合, back-merge, hotfix, release, 4.11.1, encoder-plotter-v4.11.1, revert, 撤回, 长期分支, 僵尸分支, archive tag, release-line-gate, ALLOW_BACKMERGE_DEBT, sub_algorithm, gitlink, .gitmodules, protected_branches, 分支审计, back-merge-check.sh, fetch tags 失败, MSYS_NO_PATHCONV=1

**需求场景 / 现象**: 用户要求对照 Atlassian Gitflow 文章（及 F-118 中的标准流程）审计 EncoderPlotter 的分支与发版流程，结论记入 SIRE 库；后续分支管理建议一律按该标准 Gitflow 给出。审计发现：4.11.1 热修收口断裂（encoder-plotter-v4.11.1 指向 main 的 78e16f7b，该次合并已被 774e4572 撤回，origin/main 的 package.json 仍为 4.11.0，4.11.1 不在 develop）；回合欠账（下一个正式 tag 会被 release-line-gate 判据④ 拦下，除非设 ALLOW_BACKMERGE_DEBT；origin/main 比 origin/develop 多 4 个提交，develop 超前 main 39 个）；分支积压（远端 141 条分支；origin/feature/* 中 66 条最后提交超过 28 天；53 条为无标准前缀的长期分支；5 条已合入 develop 但未删；archive/* tag 仅 4 个）；sub_algorithm gitlink 在各线不一致（develop 与 release/4.12.0 为 393ceca6；hotfix/4.11.1 为 ab6fb4a9；main 为 0166a0d6 且不在算法仓 origin/main 可达，属 ADR 0006 决定 7 的登记例外）；文档偏差（ADR 0006 决定 8 写 .gitmodules 保持 `branch = release`，实际为 `develop`；docs/branching.md 的"当前状态"表停留在 2026-09-02）。

**方案 / 实施步骤**:
1. `git fetch --prune origin`，确认远端引用最新。
2. 对每个正式 tag 取提交，分别用 merge-base --is-ancestor 查 origin/main 与 origin/develop；两者都不可达的必须登记。
3. `git rev-list --count` 比较 main 与 develop 的互相超前数，超前 main 的部分即回合欠账。
4. 按 committerdate 统计 origin/feature/* 中超 28 天无提交的分支，并列出无标准前缀的远端分支。
5. 用 glab api 查 main、develop 的保护规则；对比各线 `.gitmodules` 与 ADR 决定 8。
6. 标准流程（后续建议按此执行）：feature/<主题> 从 develop 出、合回 develop；release/x.y.z 从 develop 出，合入 main 与 develop；hotfix/x.y.z 从 main 出，合入 main 与 develop；短命分支合完即删，超 4 周未合入算异常；正式 tag（encoder-plotter-vX.Y.Z）只打在 main，每次合入 main 后立即回合 develop，不攒。
7. 撤回已打 tag 的发布提交时，应在 hotfix 分支上修正、以新版本号重新合入 main、再回合 develop，并在 CHANGELOG 与发版记录中写明被撤回的版本（建议，待实施时以 docs/branching.md 补充的条文为准）。
8. 删除分支前先打 `archive/<分支名>-<日期>` tag；清理按批次进行，每批由用户确认。

**验证方法**: 2026-11-09 实测输出：encoder-plotter-v4.11.1 → origin/main=Y、origin/develop=N；encoder-plotter-v4.11.0 → 两者均为 Y；origin/main 独有 4 个提交（78e16f7b、8e0b956a、774e4572、80554bae）；远端分支 141；feature 超 28 天 66；protected_branches 返回 main、develop 的 push=No one、merge=Maintainers、allow_force_push=false。审计命令：`git merge-base --is-ancestor <tag提交> origin/develop`；`git rev-list --count origin/develop..origin/main`；`git for-each-ref --format='%(committerdate:unix)' refs/remotes/origin/feature`；`glab api "projects/software%2FEncoderPlotter/protected_branches"`；`git ls-tree <分支> controller/python/<子模块>`。

**踩坑 / 已知异常与失败经验**: 根因：已打正式 tag 的热修被 revert 撤回后，没有配套的"重新合入 + 回合 develop"收口，tag、main、develop 三者内容不一致；分支清理没有定期执行，过期 feature 与非标准前缀分支长期留存。踩坑：`back-merge-check.sh check` 在本机报 "fetch tags 失败"，脚本体检不可用，需手工用 merge-base 核对，并在报告中注明；Git Bash 下 `git show origin/main:.gitmodules` 报 "ambiguous argument"，参数被 shell 拆坏，需设 `MSYS_NO_PATHCONV=1` 或改用 `git show origin/main -- .gitmodules`（参见 E-015）。审计只读；未创建或推送任何 tag，未改分支，未合并。

**关键文件与接口**: docs/branching.md；docs/adr/0006-git-flow-across-five-repos.md（决定 6、8、9）；scripts/back-merge-check.sh；scripts/release-gate.sh（判据④，tag_backmerged）；.gitmodules

**状态**: 已完成（审计结论已固化；4.11.1 收口与分支清理待用户决定，未执行）

### P-20261110: SIRE 归档 worker 排查：编号冲突、队头阻塞与未配置归档库的入队缺陷
**日期**: 2026-11-09
**项目**: SIRE 共享工作流（sire/workflow/shared/sire/scripts/sire_archive_sync.py，队列 D:/sire/sire_ledger/sync_queue）
**关键词**: sire_archive_sync, worker, sync_queue, 归档, 队头阻塞, 编号重复, reindex, WARN 编号重复, archive_db, SIRE_ARCHIVE_ROOT, PermissionError, kick, 排查

**需求场景 / 现象**: 收尾后 R20261109-162647-encoderplotter-0703-03 的归档任务长时间 pending，机器级归档库 D:/sire/sire_vectors.sqlite3 里查不到本次记录；`worker.log` 末尾只有 PermissionError。手动 `sire_archive_sync.py kick` 后日志仍不增长。

**方案 / 实施步骤**:
1. 看队列：统计各 state 数量，按 last_error 分组（本次：done 130、pending 38；pending 的错误为 32 条"归档库未配置"、7 条"编号重复"）。
2. 看锁与进程：`sync_queue/worker.lock` 是否存在、mtime；`Get-CimInstance Win32_Process` 查 python 进程；找 state=running 的 job 与其 attempts。
3. 单独跑 `sire_kb.py reindex` 看退出码，确认是否被编号冲突卡住；重复编号改名（两条重复里后出现的分别改为 F-123、P-20261109）。
4. 直接查归档库：`sqlite3 ?mode=ro` 查 knowledge_records 与 task_records，确认记录是否已存在。

**验证方法**: 2026-11-09 实测：reindex 修复后输出 `total_records=249`、无 WARN；归档库 `knowledge_records` 含 P-20261108；本次 job 仍为 pending（attempts=2），worker 正在处理队头 job（attempts=67）。

**踩坑 / 已知异常与失败经验**: 根因：(1)worker 每个 job 第一步跑 `sire_kb.py reindex`，知识库存在编号重复（F-122、P-20261096 各两条不同记录）时 reindex 打印 `WARN 编号重复` 并退出码 1，`run_step` 抛错，job 记为 pending；(2)队头阻塞：worker 按文件名顺序串行处理，队头 `R20261022-module-help-org.json` 已 attempts=67，每次都要 reindex + 对 1.3GB 库做两遍 index/migrate；(3)`enqueue` 的 archive_path 表达式在 SIRE_ARCHIVE_DB、SIRE_ARCHIVE_ROOT 都未设置时落到 `Path("").resolve()`，即 cwd，worker 随后报 "machine archive database is not configured or unavailable"，32 个旧 job 因此失败；(4)except 分支里 `write_json` 若失败（日志中为 `R20261021-151330-driversoftware.json.tmp` 的 PermissionError，Windows 下 .tmp 被占用），异常逃出循环，worker 结束（由日志末尾 traceback 观察到，未逐步复现）。踩坑：手动 `kick` 会把所有未完成 job 重置为 pending 并重新拉起 worker，但不会绕过队头阻塞；`sire_kb.py next-id` 会打印"写入文件"提示，实际只是取号，不改文件；归档库只靠 index 步骤顺带写入知识记录，不等于 run 归档完成，判断归档是否完成要看 task_records 中 run.json 是否一致（`verify_database`）。未做（需走 RSI 提案）：reindex 的编号冲突应作为告警继续建索引；enqueue 在归档库未配置时应拒绝入队或存空值；worker 的 except 分支自身加保护；队列按 attempts 限流或跳过超过阈值的 job。

**关键文件与接口**: sire/workflow/shared/sire/scripts/sire_archive_sync.py（enqueue、kick_pending、worker、run_step、verify_database）；sire/workflow/shared/sire/scripts/sire_kb.py（cmd_reindex、cmd_next_id）；D:/sire/sire_ledger/sync_queue/*.json；D:/sire/sire_ledger/sync_logs/worker.log

**状态**: 部分完成（编号冲突已修，知识记录已在归档库可查；脚本四项改动未做，待 RSI；本次 run 的任务记录归档仍 pending）

### P-20261111: Codex用量必须绑定会话并去重累计事件
**日期**: 2026-11-10
**项目**: SIRE Codex 用量适配
**关键词**: Codex, rollout, token_usage_record, token_count, thread_token_usage, task_started, stage_usage, 额度快照, UTF-8

**需求场景 / 现象**: 在 Codex 会话调用 sire_usage.py --final，旧脚本会读取其他 Claude 会话用量，阶段日志会混入其他任务。根因：旧实现只识别 Claude message.usage，缺少 Codex 事件解析；阶段开始仅按名称找记录，转录选择存在跨项目兜底。

**方案 / 实施步骤**:
1. 运行 sire_remind.py 读取实时版本；流程变更先提出 RSI 议案并等待用户批准。
2. 用 CODEX_THREAD_ID 或 --session-id 定位唯一 rollout，检查元数据与 cwd；不猜最新会话。
3. 优先以响应明细去重（按 response_id 统计已落盘明细，累计回退后继续计入新响应），保留明确的零值；仅有累计事件时保留确认高水位，旧累计缺基线或回退时报告未确认的候选量，不冒称完整，也不叠加到确认量。
4. quota 截止选定回合结束，只有同一 reset 窗口的真实前后快照才比较。同一入口按客户端身份选择适配器，Codex 绑定 session_meta.id/cwd、task_started 的 turn_id；阶段日志绑定 client/session/turn/run/cwd，重复结束不重复记账；token 与账号全局额度快照分开报告，缺少来源不伪造零。

**验证方法**: v6.54 的历史评估曾运行 python -m unittest test_sire_codex_usage -v，14 项通过，证据在固定台账 CODEX-20261110-01a1c458-USAGE-IMPLEMENT/evaluation.json。本次 RSI-20261110-CODEX-USAGE-FIX 补充回退、兼容、缓存及索引用例，仅做独立静态复核，未测试；不得把历史 14 项结果当成本次修复通过。

**踩坑 / 已知异常与失败经验**: 零差值不保留会把真实零误报缺失；历史回合不限制额度快照截止点会混入后续读数；Windows stderr 必须与 stdout 一起设 UTF-8，避免子进程读取拒绝信息时解码失败。阶段 token 按事件落盘时间归属，不代表精确跨阶段请求拆分；主控 rollout 不含整个代理树，压缩转录暂不支持。

**关键文件与接口**: sire/workflow/shared/sire/scripts/sire_usage.py；sire/workflow/shared/sire/scripts/sire_codex_usage.py（load、usage、quota、run）；sire/workflow/shared/sire/references/codex-usage.md

**状态**: 已实现评审修复；本次未测试，版本激活以 RSI 记录为准

### P-20261112: 阶段计时开始与结束落在不同回合目录，报未记录开始时刻
**日期**: 2026-11-11
**项目**: SIRE 共享工作流 / scripts/sire_usage.py（在 EncoderPlotter 任务中发现）
**关键词**: sire_usage, stage-start, stage-end, 未记录开始时刻, 未记录本任务开始读数, 回合目录, usage-key, task-notification, 阶段计时, 额度读数

**需求场景 / 现象**: 完整流程任务里，R6 先 `--stage-start R6`，派三个子代理后等通知，之后 `--stage-end R6` 报“R6 耗时:未记录开始时刻,不估算”，`--final` 报“耗时:未读到本轮转录时间戳”和“5小时额度:未记录本任务开始读数”。

**方案 / 实施步骤**:
1. 在出问题的转录上复现：对比 `--stage-start` 与 `--stage-end` 时的 `turn_key`。
2. 确认变化原因后，选候选方案之一（未实施、未验证）：①阶段记录和额度读数统一放在 `sire_run.py init` 的 RUN_ID 目录下，用 `--run-id` 绑定；②回合起点变化时回查同一会话内最近的开始记录。
3. 走 `sire_rsi.py propose`，用户确认后再改。

**验证方法**: 修复后，跨回合（派子代理后等通知）运行 `--stage-start R6` 与 `--stage-end R6`，应输出真实耗时而不是“未记录开始时刻”；`--final` 应给出本任务额度百分点。当前尚未修复，没有验证。

**踩坑 / 已知异常与失败经验**: 根因部分定位：阶段记录和额度读数存放在 `ledger_runs_dir()/usage-<key>/`，`<key>` 由“转录文件 + 回合起点 + run_id”哈希得到；开始记录与结束查询落在了不同的 `usage-<key>` 目录。未定位：回合起点为什么在派子代理之后发生变化。不要把“子代理通知被误判为用户提示”当成原因：其转录条目带 `origin.kind=task-notification`、`promptSource=system`，`is_prompt()` 判为非用户提示，已核对被正确排除。

**关键文件与接口**: scripts/sire_usage.py:172（stage_mark()）；scripts/sire_usage.py:418-421（回合 key 与 usage-<key> 目录）；scripts/sire_usage.py:59-70（is_prompt()）

**状态**: 部分完成

### P-20261113: 【数据库清理】SIRE 向量库与知识库整合重建：1.39GB 清理到约 55MB（候选库构建、别名追溯、索引范围收敛）
**日期**: 2026-11-11
**项目**: SIRE v6（sire_vectors.sqlite3）
**关键词**: 向量库清理, 知识库整合, 去重合并, 候选库, build_candidate, knowledge_aliases, source_paths, sync_task_records, VACUUM, 删除密码, RSI-v6.66, 只增不减, 旧版本片段, is_latest, 台账片段, mermaid.min.js, evidence

**需求场景 / 现象**: SIRE 工作库涨到 1.39GB（chunks 46469，其中 is_latest=0 旧版本 20263 个；knowledge_records 367 含同名重复 13 组；task_records 11015），检索结果被台账日志、evidence、mermaid.min.js、旧版本片段稀释，知识条目缺实施步骤/校验/异常说明，无法直接复用。再次出现原因同 P-021：只增不减 + 台账全量切片。

**方案 / 实施步骤**:
1. 先备份：sire_rsi.py 写命令会自动做带 integrity 校验的备份（D:\sire\db-backups）；线上库全程只读打开（mode=ro）。
2. 只读盘点：按来源分类统计 chunks（知识 md、台账、evidence、mermaid、项目 runs），统计 knowledge_records 重复与 lint 缺段落数。
3. 导出 knowledge_records 全文，用同标题 + emb 余弦 >=0.88 聚类出近重复组，按组整批分给子代理（组不拆开）。
4. 子代理逐条判 keep/merge/drop，并把保留卡片统一成：场景/触发词、实施步骤、验证方法、已知异常与失败经验、关键文件、状态；原文没有的写“原记录未记载”，不得编造；被并记录独有的步骤/验证/踩坑并入保留卡片。
5. 用 validate_cards.py 校验：ID 覆盖率 100%、结构错误 0、卡片里的命令/路径/数字必须出现在原记录正文（每批未命中占比 <=2%，未命中的要改回原文）。
6. build_candidate.py 在 D:\sire\db-candidate 构建候选库：卡片→knowledge_records；chunks 只切工作流与知识说明 md；task_records 按（run_id, 内容 sha256）去重并剔除噪声 run；保留 RSI 表；新增 knowledge_aliases 旧编号别名表；再 rebuild FTS、关键词、语义向量并 VACUUM。
7. u5_write_md.py 把卡片写回 global_dev_*.md / global_problem_solutions.md，否则下次 index 会从旧 md 把重复记录灌回库。
8. 走 RSI 提案（RSI-v6.66）收敛 sire_vector_db.source_paths（只索引说明文档，排除台账/evidence/mermaid/项目 runs/记录文件）并给 sync_task_records 加去噪去重。
9. 候选库自检通过后，由用户在终端输入删除密码，替换线上库文件（AI 不代填、不绕过）。

**验证方法**: 候选库自检（build_candidate.py 内置）：integrity_check=ok；chunks = chunks_fts = emb(chunk) = cfts；knowledge_records = 保留卡片数 = kfts = emb(knowledge)；体积 <= 线上库 25%；task_records 保留的 run 数 >=95%；去重/去噪删除条数与 audit.json 一致。另用 --selftest 验证切片排除规则；用 check_fields 统计卡片各字段非“原记录未记载”比例。检索评测（recall@3、延迟）需用户授权后再跑：python D:\sire\eval\run_eval.py。

**踩坑 / 已知异常与失败经验**: 1. sire_vector_db.py 的删除/VACUUM 受 SIRE_DB_ALLOW_DELETE + 用户输入密码保护，所以清理放在候选库，切换交给用户；不要在旧库上直接 index，它默认只增不减，不会瘦身。
2. 构建脚本渲染卡片时必须取元素的 card 子对象，一度渲染了外层元素，候选库所有正文变成“原记录未记载”，重建后用字段统计才发现——建完必须抽查正文。
3. md 必须同步回写，否则 sync_knowledge_records 会把旧记录再灌回；非标准编号（K-*、KB-*）记录只存在库内，md 解析不到，不能靠 md 重建。
4. sync_task_records 若不加去噪去重，清理后下次同步会把重复和噪声记录写回；去重键要含 run_id，只用内容 hash 会让 8 个 run 整个消失。
5. 合并后旧编号要有别名表，否则 RSI 提案/台账里引用的旧 ID 查不到。
6. 跨类型合并会丢状态（H-008 并入 F-098 要补“偏好仍生效”）；只存在于独立 md 的记录（P-20261053/054/055/103）从未入库，需另行评审。
7. 候选库的 task_records 原样带着内网 IP、邮箱等，库不进 Git，不要外发。
8. 工作流有两份库：工作库 D:\sire\AI\AI\sire\data 与机器级归档库 D:\sire\sire_vectors.sqlite3，切换时两份都要处理。

**关键文件与接口**: sire/tools/db_cleanup/（build_candidate.py、validate_cards.py、u5_write_md.py、patch_cards.py、README.md）；sire/workflow/shared/sire/scripts/sire_vector_db.py（source_paths、task_run_is_noise、sync_task_records）；sire_kb.py（cmd_show 别名追溯）；sire_knowledge_index.py（post_index/sync_embeddings）；D:\sire\db-candidate\（候选库、audit.json、md-backup）

**状态**: 已完成（候选库已建成并自检通过；线上库切换与检索评测待用户授权）
