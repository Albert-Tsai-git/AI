"""SIRE 受控 RSI：记录改进提案、指标、评估、激活与回滚。"""
from __future__ import annotations
import argparse, json, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from sire_paths import DATABASE_PATH
from sire_vector_db import backup_before_mutation, database_mutation_lock

def now(): return datetime.now(timezone.utc).isoformat()
def db(p):
    c=sqlite3.connect(p); c.row_factory=sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS improvement_proposals(
      proposal_id TEXT PRIMARY KEY, title TEXT NOT NULL, hypothesis TEXT NOT NULL,
      change_summary TEXT NOT NULL, status TEXT NOT NULL, parent_version TEXT,
      created_at TEXT NOT NULL, evaluated_at TEXT, activated_at TEXT, rollback_at TEXT,
      evaluation TEXT NOT NULL DEFAULT '{}')""")
    c.execute("""CREATE TABLE IF NOT EXISTS improvement_metrics(
      id INTEGER PRIMARY KEY, proposal_id TEXT NOT NULL, metric TEXT NOT NULL,
      before_value REAL, after_value REAL, target_value REAL, passed INTEGER NOT NULL,
      evidence TEXT NOT NULL, created_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS workflow_versions(
      version TEXT PRIMARY KEY, proposal_id TEXT, status TEXT NOT NULL,
      config_hash TEXT NOT NULL, created_at TEXT NOT NULL, activated_at TEXT, retired_at TEXT)""")
    return c
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--db',type=Path,default=DATABASE_PATH)
    sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('propose'); p.add_argument('proposal_id'); p.add_argument('--title',required=True); p.add_argument('--hypothesis',required=True); p.add_argument('--change',required=True); p.add_argument('--parent-version',default='current')
    e=sub.add_parser('evaluate'); e.add_argument('proposal_id'); e.add_argument('--metric',action='append',required=True,help='name,before,after,target,evidence')
    a=sub.add_parser('activate'); a.add_argument('proposal_id'); a.add_argument('--version',required=True); a.add_argument('--config-hash',required=True)
    r=sub.add_parser('rollback'); r.add_argument('proposal_id'); r.add_argument('--reason',required=True)
    sub.add_parser('status')
    args=ap.parse_args()
    with database_mutation_lock(args.db):
        # RSI creates and updates its own schema, so preserve an existing shared
        # database before any command (including status, which initializes tables).
        if args.db.is_file():
            backup_before_mutation(args.db)
        c=db(args.db)
        try:
            if args.cmd=='propose':
                c.execute('INSERT OR REPLACE INTO improvement_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?)',(args.proposal_id,args.title,args.hypothesis,args.change,'PROPOSED',args.parent_version,now(),None,None,None,'{}'))
            elif args.cmd=='evaluate':
                passed=True
                for raw in args.metric:
                    name,before,after,target,evidence=raw.split(',',4); ok=float(after)>=float(target); passed &= ok
                    c.execute('INSERT INTO improvement_metrics(proposal_id,metric,before_value,after_value,target_value,passed,evidence,created_at) VALUES(?,?,?,?,?,?,?,?)',(args.proposal_id,name,float(before),float(after),float(target),int(ok),evidence,now()))
                result=json.dumps({'passed':passed,'metrics':len(args.metric)},ensure_ascii=False)
                c.execute("UPDATE improvement_proposals SET status=?,evaluated_at=?,evaluation=? WHERE proposal_id=?",('EVALUATED_PASS' if passed else 'EVALUATED_FAIL',now(),result,args.proposal_id))
            elif args.cmd=='activate':
                row=c.execute('SELECT status FROM improvement_proposals WHERE proposal_id=?',(args.proposal_id,)).fetchone()
                if not row or row['status']!='EVALUATED_PASS': raise SystemExit('只能激活评估通过的提案')
                c.execute("UPDATE workflow_versions SET status='RETIRED',retired_at=? WHERE status='ACTIVE'",(now(),))
                c.execute('INSERT OR REPLACE INTO workflow_versions VALUES(?,?,?,?,?,?,?)',(args.version,args.proposal_id,'ACTIVE',args.config_hash,now(),now(),None))
                c.execute("UPDATE improvement_proposals SET status='ACTIVE',activated_at=? WHERE proposal_id=?",(now(),args.proposal_id))
            elif args.cmd=='rollback':
                c.execute("UPDATE workflow_versions SET status='ROLLED_BACK',retired_at=? WHERE proposal_id=? AND status='ACTIVE'",(now(),args.proposal_id))
                c.execute("UPDATE improvement_proposals SET status='ROLLED_BACK',rollback_at=?,evaluation=? WHERE proposal_id=?",(now(),json.dumps({'reason':args.reason},ensure_ascii=False),args.proposal_id))
            else:
                print(json.dumps({'proposals':[dict(x) for x in c.execute('SELECT * FROM improvement_proposals ORDER BY created_at DESC')], 'versions':[dict(x) for x in c.execute('SELECT * FROM workflow_versions ORDER BY created_at DESC')]},ensure_ascii=False,indent=2))
            c.commit()
        finally:
            c.close()
    print(json.dumps({'status':'ok','command':args.cmd},ensure_ascii=False))
if __name__=='__main__': main()
