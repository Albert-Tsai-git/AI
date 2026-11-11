# 库清理重建工具（2026-11-11）

复用流程见知识卡片 P-20261113。脚本里的路径按本机固定位置写死（线上库、`D:\sire\db-candidate`），换机器先改顶部常量。

| 文件 | 作用 |
|---|---|
| `build_candidate.py` | 由卡片构建干净候选库，线上库只读；`--selftest` 检查切片排除规则 |
| `validate_cards.py` | 卡片校验：ID 覆盖、结构、防编造（词条必须出现在原记录） |
| `u5_write_md.py` | 把卡片写回 md 知识源（备份到 `D:\sire\db-candidate\md-backup`） |
| `patch_cards.py` | 卡片返工补丁示例（重复行去重、恢复误删） |

`SIRE_DB_ALLOW_DELETE` 与删除密码门禁不在这里绕过；切换（替换线上库文件）由用户本人执行。
