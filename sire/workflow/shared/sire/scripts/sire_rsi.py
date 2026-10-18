"""SIRE 受控 RSI：记录改进提案、指标、评估、激活与回滚。

写命令同时写仓库库（DATABASE_PATH，供 R9 rsi-check 读取）和机器级归档库（收尾快照的来源），
保证快照从归档库重建仓库库时不会丢失 RSI 记录。status 只读。
"""
from __future__ import annotations
import argparse, json, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path
from sire_paths import DATABASE_PATH, archive_database_path
from sire_vector_db import backup_before_mutation, database_mutation_lock

# 本机控制台是 GBK，拒绝信息按 GBK 出来三端读到的都是乱码，只能靠猜再试一轮，两条流强制 UTF-8
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

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

def apply(c, args, ts):
    """在单个库上执行写命令；ts 由调用方统一给出，保证两库时间戳一致。"""
    if args.cmd=='propose':
        c.execute('INSERT OR REPLACE INTO improvement_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?)',(args.proposal_id,args.title,args.hypothesis,args.change,'PROPOSED',args.parent_version,ts,None,None,None,'{}'))
    elif args.cmd=='evaluate':
        passed=True
        for raw in args.metric:
            name,before,after,target,evidence=raw.split(',',4); ok=float(after)>=float(target); passed &= ok
            c.execute('INSERT INTO improvement_metrics(proposal_id,metric,before_value,after_value,target_value,passed,evidence,created_at) VALUES(?,?,?,?,?,?,?,?)',(args.proposal_id,name,float(before),float(after),float(target),int(ok),evidence,ts))
        result=json.dumps({'passed':passed,'metrics':len(args.metric)},ensure_ascii=False)
        c.execute("UPDATE improvement_proposals SET status=?,evaluated_at=?,evaluation=? WHERE proposal_id=?",('EVALUATED_PASS' if passed else 'EVALUATED_FAIL',ts,result,args.proposal_id))
    elif args.cmd=='activate':
        row=c.execute('SELECT status,parent_version FROM improvement_proposals WHERE proposal_id=?',(args.proposal_id,)).fetchone()
        if not row or row['status']!='EVALUATED_PASS': raise SystemExit('只能激活评估通过的提案')
        cur=c.execute("SELECT version FROM workflow_versions WHERE status='ACTIVE'").fetchall()
        current=cur[0]['version'] if cur else ''
        parent=(row['parent_version'] or '').strip()
        # --parent-version 的默认值是哨兵 'current'（意为"基于当时生效版本"），不是版本号；
        # 显式钉过版本时才做冲突判定：三端共用一条版本链，他端推进过就不能静默覆盖
        if parent and parent.lower()!='current':
            if current and parent!=current:
                raise SystemExit('版本链已被他端推进：本提案基于 %s，当前生效是 %s；'
                                 '请复核改动仍成立后以 --parent-version %s 重新登记' % (parent, current, current))
        if parent.lower()=='current':
            c.execute('UPDATE improvement_proposals SET parent_version=? WHERE proposal_id=?',(current,args.proposal_id))
        c.execute("UPDATE workflow_versions SET status='RETIRED',retired_at=? WHERE status='ACTIVE'",(ts,))
        c.execute('INSERT OR REPLACE INTO workflow_versions VALUES(?,?,?,?,?,?,?)',(args.version,args.proposal_id,'ACTIVE',args.config_hash,ts,ts,None))
        # 提案状态与版本链同步，否则被取代的提案仍标 ACTIVE，"有多少条生效改动"读出来是假的
        c.execute("UPDATE improvement_proposals SET status='SUPERSEDED' WHERE status='ACTIVE' AND proposal_id<>?",(args.proposal_id,))
        c.execute("UPDATE improvement_proposals SET status='ACTIVE',activated_at=? WHERE proposal_id=?",(ts,args.proposal_id))
    elif args.cmd=='rollback':
        c.execute("UPDATE workflow_versions SET status='ROLLED_BACK',retired_at=? WHERE proposal_id=? AND status='ACTIVE'",(ts,args.proposal_id))
        c.execute("UPDATE improvement_proposals SET status='ROLLED_BACK',rollback_at=?,evaluation=? WHERE proposal_id=?",(ts,json.dumps({'reason':args.reason},ensure_ascii=False),args.proposal_id))

def status(path: Path):
    """只读查询：库或表不存在时返回空列表，不建表、不备份。"""
    out={'db':str(path),'proposals':[],'versions':[]}
    if not path.is_file(): return out
    c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True); c.row_factory=sqlite3.Row
    try:
        c.execute('PRAGMA query_only=ON')
        out['proposals']=[dict(x) for x in c.execute('SELECT * FROM improvement_proposals ORDER BY created_at DESC')]
        out['versions']=[dict(x) for x in c.execute('SELECT * FROM workflow_versions ORDER BY created_at DESC')]
    except sqlite3.Error:
        pass
    finally:
        c.close()
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--db',type=Path,default=DATABASE_PATH)
    ap.add_argument('--archive-db',type=Path,default=archive_database_path(),help='机器级归档库；默认取 SIRE_ARCHIVE_DB 或 SIRE_ARCHIVE_ROOT')
    ap.add_argument('--repo-only',action='store_true',help='只写 --db（例如临时库测试）；正式 RSI 记录不要使用')
    sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('propose'); p.add_argument('proposal_id'); p.add_argument('--title',required=True); p.add_argument('--hypothesis',required=True); p.add_argument('--change',required=True); p.add_argument('--parent-version',default='current')
    e=sub.add_parser('evaluate'); e.add_argument('proposal_id'); e.add_argument('--metric',action='append',required=True,help='name,before,after,target,evidence')
    a=sub.add_parser('activate'); a.add_argument('proposal_id'); a.add_argument('--version',required=True); a.add_argument('--config-hash',required=True)
    r=sub.add_parser('rollback'); r.add_argument('proposal_id'); r.add_argument('--reason',required=True)
    sub.add_parser('status')
    args=ap.parse_args()
    if args.cmd=='status':
        print(json.dumps(status(args.db),ensure_ascii=False,indent=2)); return
    targets=[args.db]
    if not args.repo_only:
        if args.archive_db is None:
            raise SystemExit('未解析到归档库：设置 SIRE_ARCHIVE_ROOT / SIRE_ARCHIVE_DB 或传 --archive-db；仅测试时可用 --repo-only')
        if args.archive_db.resolve()!=args.db.resolve():
            # 先写归档库（快照来源）：中途失败时只会"归档有、仓库无"，快照可补齐，不会丢记录
            targets.insert(0,args.archive_db)
    ts=now()
    # 写前在所有目标库上只读校验：提案须在每个库存在且状态一致（防止中途失败后重跑造成重复或分叉）；
    # activate 另需 EVALUATED_PASS。任一库不满足则都不写。
    if args.cmd!='propose':
        states={}
        for path in targets:
            if not path.is_file(): raise SystemExit(f'库不存在：{path}')
            st=[x['status'] for x in status(path)['proposals'] if x['proposal_id']==args.proposal_id]
            if not st: raise SystemExit(f'提案 {args.proposal_id} 在 {path} 中不存在')
            states[str(path)]=st[0]
        if len(set(states.values()))!=1:
            raise SystemExit('两库提案状态不一致，先人工核对修复后再执行：'+json.dumps(states,ensure_ascii=False))
        if args.cmd=='activate' and set(states.values())!={'EVALUATED_PASS'}:
            raise SystemExit(f'只能激活评估通过的提案（当前状态 {states}）')
    else:
        exists=[str(p) for p in targets if any(x['proposal_id']==args.proposal_id for x in status(p)['proposals'])]
        if exists: raise SystemExit(f'提案 {args.proposal_id} 已存在于 {exists}，不得重复 propose（会覆盖原 created_at）')
    for path in targets:
        with database_mutation_lock(path):
            # RSI 可能建表，写前按规则备份已有库
            if path.is_file():
                backup_before_mutation(path)
            c=db(path)
            try:
                apply(c,args,ts); c.commit()
            finally:
                c.close()
    print(json.dumps({'status':'ok','command':args.cmd,'databases':[str(t) for t in targets]},ensure_ascii=False))
if __name__=='__main__': main()
