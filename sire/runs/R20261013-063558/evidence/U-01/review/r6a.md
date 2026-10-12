# R6A 事实核对（独立只读代理，抽核 90+ 处）— F-053
初判 FAIL。核对属实：endpoint 160、server.py 11178 行、core 39 文件、:341 READER_MP 表达式逐字一致、:352 单例、reader 三变体行数与成员、start.bat:10。
判错项（已全部改掉并复验）：
1. 端口回写实 :11163（原写 :11161）；回执文件 `_write_port_receipt` 实 :11164（原写 :11163）。
2. `freeze_support()` 实 :11177（原 :11174）；`_bind_http_socket` 定义实 :11088（原 :11089）。
3. `device_id_confirmed` 实 :381（原 :377）、`_last_probe_alive` 实 :387（原 :385）。
4. `KK_READER` 实 :46（原文一处写 :43、另一处写 :46，自相矛盾）。
5. `/api/jn/*` 段末实 :2984（原写 :3060，那是 dyn200）；`/api/cmd/*` 段里 :5318 实为 `/api/identify`。
6. `force_calib_runner.py` 两常量行号对调：:96 是 `FORCE_CALIB_SCRIPT`、:500 是 `BENCH_DUAL_READER`。
修复后复验：全量行号审计 27 处引用，26 处指向非空代码行；唯一被标为可疑的 server.py:212 是【故意引用】的过时文档行（AGENTS.md:321 的错误引用），不是事实错误。