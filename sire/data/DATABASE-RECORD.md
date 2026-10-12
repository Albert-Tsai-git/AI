# SIRE 共享数据库记录

数据库 **暂不进 Git**（2026-10-12 起）。本仓库只保留这份记录，实际数据在本机。

**原因**：`sire_vectors.sqlite3` 已涨到 168MB 以上，超过 GitHub 单文件 100MB 上限，推送被拒（GH001）。清掉空闲页后仍约 170MB。

## 本机实际位置

| 用途 | 路径 |
|---|---|
| Claude/Codex 共用工作库 | `D:\sire\AI\AI\sire\data\sire_vectors.sqlite3` |
| 机器级收尾归档库（`SIRE_ARCHIVE_ROOT`） | `D:\sire\sire_vectors.sqlite3` |
| 自动备份目录（`sire_db_backup.py` 默认） | `C:\Users\Administrator\sire\db-backups` |

脚本一律经 `workflow/shared/sire/scripts/sire_paths.py` 解析工作库路径，不要在脚本里写死上表路径；上表只用于人工定位。

## 记录时状态（2026-10-12）

| 库 | 大小 | knowledge_records | task_records | chunks | integrity_check | 当前工作流版本 |
|---|---|---|---|---|---|---|
| 工作库 | 210.3 MB | 138 | 2650 | 6978 | ok | v6.5 |
| 归档库 | 173.8 MB | 137 | 2650 | 6805 | ok | v6.5 |

Git 历史里最后一份被跟踪的数据库是远端 `feature/feishu-hub` 在 `9e4c3f9` 时的版本（69MB），之后不再更新，不要拿它当最新数据。

## 换机 / 恢复

数据库不随 `git clone` 下来。新机器上从原机复制上表工作库文件（或从备份目录取最近一份 `integrity=ok` 的备份）放到 `sire/data/sire_vectors.sqlite3`，再运行 `sire_vector_db.py stats` 核对计数与 `integrity_check`。

## 什么时候恢复进 Git

需要另行决定（例如改走 Git LFS 或拆分快照）。在那之前，`.gitignore` 已忽略该文件，不要用 `git add -f` 强行提交。
