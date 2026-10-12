"""仅归档本次查询，不扫描或重建整个知识库。"""
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(__file__).resolve().parent
REPO = RUN.parents[1]
SCRIPTS = REPO / "workflow/shared/sire/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO / "tools"))
from sire_paths import DATABASE_PATH, archive_database_path
from sire_vector_db import backup_before_mutation, database_mutation_lock
import sire_knowledge_index as ki
import snapshot_db

archive = archive_database_path()
if archive is None:
    raise SystemExit("机器归档路径未配置")
now = datetime.now(timezone.utc).isoformat()
rid = "method-git-current-branch"
title = "当前分支必须查询实时 Git"
keywords = "Git, 当前分支, 实时状态, 历史记录"
knowledge = REPO / "knowledge/global/git-current-branch.md"
body = knowledge.read_text(encoding="utf-8")
record = (RUN / "record.md").read_text(encoding="utf-8")
text = ki.knowledge_text(title, keywords, body)
model = ki.embedder()
if model is None:
    raise SystemExit("嵌入模型不可用，未写库")
vector = ki._pack(list(model.embed([text]))[0])
text_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()
result = {"run_id": RUN.name, "databases": [], "knowledge_record": rid}
for db in [archive, DATABASE_PATH]:
    backup_before_mutation(db)
    with database_mutation_lock(db):
        conn = sqlite3.connect(str(db), timeout=30)
        try:
            conn.execute("INSERT OR REPLACE INTO knowledge_records(record_id,record_type,title,source_path,source_line,keywords,body,updated_at,domain,kind,status,scope,confidence) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (rid,"F",title,str(knowledge),1,keywords,body,now,"git","method","active","global",1.0))
            conn.execute("DELETE FROM kfts WHERE record_id=?", (rid,))
            conn.execute("INSERT INTO kfts(record_id,title,keywords,body) VALUES(?,?,?,?)", (rid,title,keywords,body))
            conn.execute("INSERT OR REPLACE INTO emb(kind,ref,model,text_hash,vector,updated_at) VALUES(?,?,?,?,?,?)", ("knowledge",rid,ki.MODEL_NAME,text_hash,vector,now))
            for kind, content in [("task",record),("validation","三条实时 Git 命令一致：chore/misc-optimizations；独立复核退出码 0；项目工作区干净。")]:
                key = RUN.name + ":" + kind
                conn.execute("INSERT OR REPLACE INTO task_records(record_key,run_id,project_path,record_path,record_type,content,updated_at,domain,kind,status,scope,confidence) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (key,RUN.name,"D:/code/driverSoftware",str(RUN/"record.md"),kind,content,now,"git",kind,"complete","task",1.0))
            for key,value in [("sire_last_project","D:/code/driverSoftware"),("sire_last_run",RUN.name),("sire_last_status","DONE")]:
                conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key,value))
            conn.commit()
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(integrity)
            conn.execute("INSERT INTO kfts(kfts) VALUES('integrity-check')")
            conn.execute("INSERT INTO cfts(cfts) VALUES('integrity-check')")
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')")
            conn.commit()
            rows = conn.execute("SELECT COUNT(*) FROM task_records WHERE run_id=?", (RUN.name,)).fetchone()[0]
            meta = dict(conn.execute("SELECT key,value FROM meta WHERE key LIKE 'sire_last_%'"))
            counts = snapshot_db.counts(conn)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
        digest = snapshot_db.sha256(db)
        manifest = {"created_at":now,"source":str(db),"snapshot_sha256":digest,"records_by_table":counts,"validation":{"integrity_check":integrity,"fts_integrity":"ok","targeted_knowledge_embedding":len(vector),"run_task_records":rows},"operation":"targeted task archive","run_id":RUN.name}
        db.with_name("snapshot-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        result["databases"].append({"path":str(db),"integrity":integrity,"fts":"ok","task_records":rows,"knowledge_records":1,"embedding_bytes":len(vector),"meta":meta,"sha256":digest})
(RUN/"archive-result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,ensure_ascii=False))
