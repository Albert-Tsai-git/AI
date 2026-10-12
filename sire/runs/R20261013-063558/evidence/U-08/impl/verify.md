# U-08 索引重建与校验

命令（cwd = `D:\sire\AI\AI\sire\workflow\shared\sire\scripts`）：
```
python sire_kb.py reindex
reindex ok -> global_index.json  total_records=47  by_type=E:3 F:24 H:3 P:17

python sire_vector_db.py index
{"backup": "C:\\Users\\Administrator\\sire\\db-backups\\sire_vectors-20261013-072947-858970.sqlite3", "bytes": 245493760, "integrity": "ok", "counts": {"chunks": 7793, "knowledge_records": 149, "task_records": 2818, "keywords": 24969}, "retained": 14}
[知识索引] 索引后处理完成 {"types_normalized": 0, "hidden_old_versions": 203, "noise_keywords": 311, "keywords_filled": 0, "embedded": 123}
{"sources": 334, "chunks": 7908, "inserted": 115, "unchanged": 307, "removed": 0, "appended_versions": 2}
```

校验（现场只读复跑）：knowledge_records=156（入库前 149，+7，新增七条 F-053~F-059 全部在库：['F-053', 'F-054', 'F-055', 'F-056', 'F-057', 'F-058', 'F-059']）
chunks=7908（前 7793）keywords=24981（前 24969）task_records=2818
PRAGMA integrity_check = ok
备份：sire_vectors-20261013-072947-858970.sqlite3（245493760 bytes，index 前由 backup_before_mutation 自动生成并自检）
removed=0：本次未设 SIRE_DB_ALLOW_DELETE，删除路径全被双闸拦住，既有记录零删除（R6C 已审）。
副作用如实记录：index 走「只增不减」，features.md 旧版本 chunk 保留（后处理 hidden_old_versions=203 已打隐藏标记）。
