import re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

P = r"D:\sire\AI\AI\sire\knowledge\global\global_dev_features.md"
t = open(P, encoding="utf-8").read()

plain = [
    # ---- F-053 ----
    ("(:11089)", "(:11088)"),
    ("并写端口回执文件(:11163)", "并写端口回执文件 `_write_port_receipt(port)`(:11164)"),
    ("**绑成功后把实际端口回写 `os.environ[\"WEB_GUI_PORT\"]`**(:11161)",
     "**绑成功后把实际端口回写 `os.environ[\"WEB_GUI_PORT\"]`**(:11163)"),
    ("`multiprocessing.freeze_support()`(:11174)", "`multiprocessing.freeze_support()`(:11177)"),
    ("`device_id_confirmed`(:377)", "`device_id_confirmed`(:381)"),
    ("`_last_probe_alive`(:385)", "`_last_probe_alive`(:387)"),
    ("多读取器会话绑定 `KK_READER` :43、`_kk_select` :50",
     "多读取器会话绑定 `KK_READER_ENV` :46（环境变量在 :62 读）、`_kk_select` :50"),
    ("选择逻辑收口在 `reader_wrapper.py:43-50`", "选择逻辑收口在 `reader_wrapper.py:46-62`"),
    ("`BENCH_DUAL_READER`/`FORCE_CALIB_SCRIPT`(force_calib_runner.py:96,500)",
     "`FORCE_CALIB_SCRIPT`(force_calib_runner.py:96)、`BENCH_DUAL_READER`(同文件:500)"),
    ("外部扭矩真值 `/api/jn/*` :2959-3060", "外部扭矩真值 `/api/jn/*` :2959-2984"),
    ("命令 `/api/cmd/*` :4223-4247、:5024-5318、:5549-5810",
     "命令族锚点 `/api/cmd/mode` :4223、`/api/identify` :5318、`/api/cmd/save_config` :5549"),
    ("的 `_monitor_loop` :9511 **首行 return，实际不推任何帧**",
     "的 `_monitor_loop`（:9511）在注释块之后直接 `return`（:9528），**实际一帧都不推**"),
    # ---- F-054 ----
    ("出入口收口在三个私有方法", "出入口收口在四个私有方法"),
    ("按固件版本 v3.3.0–v3.4.7 存 `dev-<sha>.json`",
     "正式档案按固件版本命名 `v<X.Y.Z>.json`（当前 13 份，v3.3.0–v3.4.7）；联调用的 `dev-<sha>.json` 由 `tools/gen_fw_profile.py --rev <sha>` 现生成，仓内一份都没有"),
    ("⑩ CRC16 参考实现指向上位机 `protocol.py::crc16()`（README:28）。",
     "⑩ CRC16 为 CRC16-CCITT、帧末 2 字节小端（`docs/protocol/rs485_v3.3.md:15`、:73），上位机实现就是 `core/protocol.py:243 crc16()`。"),
    # ---- F-055 ----
    ('`telemetry:sample")（:152）', '`telemetry:sample")（:151）'),
    ("（`buildConsole` :1，Enter 发送 :316）", "（`buildConsole` :154）"),
    ("（`tests.js:11` 注释即此写法，:3167/:3241/:3350 `while(未到时限){发帧; await sleep()}`）",
     "（实测 `tests.js` 里有 144 处 `await sleep`，采样循环形如 :3167/:3241/:3350 的 `while (performance.now() < tEnd) { … ; await sleep() }`）"),
    ("注意 `/ws/monitor` 后端侧是空壳（见后端地图记录）", "后端 `/ws/monitor` 是空壳（见 F-053）"),
    # ---- F-056 ----
    ("（:1095-1104 是真机 id4 实证注释：后台节流会让运动页软轮询的 MIT 帧越过 `0x4D` 看门狗 → 停机，关掉后窗口被遮挡帧照发）",
     "（:1095-1104 是真机 id4 实证注释；节流导致停机的机理见 F-055，本条只登记壳侧这个开关）"),
    # ---- F-057 ----
    ("本仓约 **51 个 unit 文件自带剥注释扫描器**（`_strip_comments` / `_strip_comments_and_docstrings`），124 个文件用 `read_text` 读源码做断言。",
     "本仓精确含 `_strip_comments` / `_strip_comments_and_docstrings` 的 unit 文件 **7 个**（宽松算上任意 `_strip*` 助手是 73 个），**125 个文件**用 `read_text` 读源码做断言。"),
    ("`tests/conftest.py:47 isolate_disconnect`（隔离黑匣子落盘 + 保存/恢复 server 模块级全局，6 个文件共用）",
     "`tests/conftest.py:48 isolate_disconnect`（:47 是装饰器；隔离黑匣子落盘 + 保存/恢复 server 模块级全局，**8 个文件**共用）"),
    # ---- F-058 ----
    ("；过流 / 过温（>90℃）/ 报故障即停的异常路径 :38-70；",
     "；异常类（过流阈值 `peak_iq_a/limit_a`、过温、故障）在 :38-70，**实际停机判定在采集循环侧**：滤波 Iq 取值 `server.py:10613`、过流/过温/故障归类 `server.py:10649`；"),
    ("**关键词**: [下线检测, offline detection,", "**关键词**: [下线检测, 扭矩去皮零点, 卸力零点, offline detection,"),
    # ---- F-059 ----
    ("+ 工程军规（:214 起，含分支命名表", "+ 工程军规（:224 起，含分支命名表"),
]

reg = [
    # F-055: setInterval 清单重写
    (r"^3\. 非安全路径仍留有 `setInterval`.*$",
     "3. **别把 `setInterval` 当成\"只是界面刷新\"**（实测 `frontend/js/**/*.js` 共 19 处）。轮询/显示类有 `link-health.js:443`、`offline_detection.js:651/:756/:819`、`calibrate.js:2277`、`forcecal.js:606`、`test-scope.js:775/:886`、`trajectory.js:1628`、`tests.js:3816`；**但 `scope-bar.js:4132/:4145` 的 `this._timer = setInterval(() => this._tick(), period)` 就是软轮询发帧路径**（:4146-4148 自证：寄存器页起 Live 就逐 addr 打 `/api/cmd/reg_read`，跟回放帧抢同一条总线），`scope-bar.js:1436/:4140` 的 16ms `_hwDrainTick()` 同样在发请求。碰到这些循环要按第 1 条换成 `unthrottled-timer` 或 `await` 链。\n4. `api.js:485 setInterval(ms)` 是给 `/ws/monitor` 发 `interval_ms` 消息的方法名，不是定时器，别看错。"),
    # F-056 去重
    (r"^2\. `dist_app/server\.dist` 是.*$",
     "2. `dist_app/server.dist` 是壳引用的**共享产物目录**；\"跳过 Nuitka 复用旧 dist 会把旧前端发出去\"这条后果与证据归 F-057，本条不重复展开。"),
    (r"^3\. 构建脚本里 `for /f.*$",
     "3. 构建脚本的 `for /f` 转义坑见 F-057 踩坑 4。"),
    # F-057 去重
    (r"^1\. 打包版反馈先想 `READER_MP` 双形态.*$",
     "1. 打包版反馈先想 `READER_MP` 双形态（分叉行号、复现方法、环境变量清单归 F-053，此处不重复）。"),
    # F-058 去重
    (r"^3\. 页面重建会留下脱离文档的旧 DOM 轮询.*$",
     "3. 页面重建会留下脱离文档的旧 DOM 轮询（机理归 F-055 踩坑 1）；本页的做法是把清理注册进 `onPageRebuild`（:530/:677/:758）。"),
]

miss = []
for a, b in plain:
    n = t.count(a)
    if n != 1:
        miss.append((n, a[:60]))
    else:
        t = t.replace(a, b)
for pat, new in reg:
    m = re.findall(pat, t, re.M)
    if len(m) != 1:
        miss.append((len(m), pat[:60]))
    else:
        t = re.sub(pat, lambda _m: new, t, count=1, flags=re.M)

open(P, "w", encoding="utf-8", newline="\n").write(t)
print("替换失败条目:", miss if miss else "无")
for rid in ["F-053", "F-054", "F-055", "F-056", "F-057", "F-058", "F-059"]:
    print(rid, "存在:", ("### " + rid + ":") in t)
