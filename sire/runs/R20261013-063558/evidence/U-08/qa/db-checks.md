# U-08 功能测试（独立于 impl 的用例：直接查库与查文件系统）
- select count(*) from knowledge_records → 156（期望 156）
- 七条新 ID 在库 → ['F-053', 'F-054', 'F-055', 'F-056', 'F-057', 'F-058', 'F-059']
- PRAGMA integrity_check → ok
- db-backups 目录按 mtime 最新 → sire_vectors-20261013-072947-858970.sqlite3，245493760 bytes（>0 且晚于 index 开始）
- meta.last_indexed_at 已更新；keywords 24981、chunks 7908 均增长
