# R6A — F-057
初判 FAIL。属实：244 测试文件、2236 条 `def test_`、根层 7 个硬件脚本、skipif 13、无 markers、CI 行号（:24/:29/:49/:101/:140/:192/:208/:228/:352）、build.bat 各步区间、Nuitka pragma :81/:85-96/:97/:101/:105/:106-107、INTERNAL_SHA 与 MAX_UI_LEVEL 读写、release.py 与 requirements/setup 行号全对。
判错项（已改）：
1. 「约 51 个 unit 文件自带剥注释扫描器」→ 精确匹配 `_strip_comments`/`_strip_comments_and_docstrings` 实 7 个（宽松含任意 `_strip*` 助手为 73 个），两种口径都写明。
2. 「124 个文件用 read_text」实 125。
3. `isolate_disconnect` 定义在 conftest:48（:47 是装饰器），共用文件实 8 个（原写 6）。
复验：19 处行号引用全部可定位。