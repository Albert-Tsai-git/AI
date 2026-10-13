"""Archive only this task with shared SIRE locking, backup and indexing functions."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
import subprocess
import sys

RUN = Path(__file__).resolve().parent
PACKAGE = RUN.parents[1]
SCRIPTS = PACKAGE / 'workflow/shared/sire/scripts'
os.environ['SIRE_TASK_ROOTS'] = str(RUN)
sys.path.insert(0, str(SCRIPTS))
import sire_vector_db as vector
from sire_paths import DATABASE_PATH

archive_db = Path(sys.argv[1]).resolve()
if not archive_db.is_file() or archive_db == DATABASE_PATH.resolve():
    raise ValueError('Expected existing distinct machine archive database')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_counts(conn):
    names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%fts%'")]
    return {name: conn.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0] for name in names}

def archive_one(db, label):
    with vector.database_mutation_lock(db):
        # index_database creates and verifies the pre-mutation online backup.
        if '--records-only' in sys.argv:
            vector.backup_before_mutation(db)
            indexed = {'status': 'already_indexed'}
        else:
            indexed = vector.index_database(db)
        conn = vector.connect(db)
        imported = vector.sync_task_records(conn)
        vector.sync_keywords(conn)
        meta = {'sire_last_project': 'SIRE-rule-sync', 'sire_last_run': RUN.name,
                'sire_last_status': 'DONE'}
        for key, value in meta.items():
            conn.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)', (key, value))
        conn.commit()
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')")
        conn.commit()
        integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
        assert integrity == 'ok', integrity
        record = conn.execute("SELECT title,body FROM knowledge_records WHERE record_id='E-010'").fetchone()
        assert record and 'v6.11' in record['body']
        task_count = conn.execute('SELECT COUNT(*) FROM task_records WHERE run_id=?', (RUN.name,)).fetchone()[0]
        expected_files = sum(1 for path in RUN.rglob('*') if path.is_file() and path.suffix.lower() in {'.json', '.md', '.log', '.txt', '.yaml', '.yml'})
        assert task_count >= expected_files, (task_count, expected_files)
        orphans = conn.execute("SELECT COUNT(*) FROM emb WHERE (kind='chunk' AND ref NOT IN (SELECT CAST(id AS TEXT) FROM chunks)) OR (kind='knowledge' AND ref NOT IN (SELECT record_id FROM knowledge_records))").fetchone()[0]
        assert orphans == 0, orphans
        counts = read_counts(conn)
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        conn.close()
        hash_value = digest(db)
        if label == 'working':
            manifest = {'created_at': datetime.now(timezone.utc).isoformat(),
                        'source': '@SIRE_ROOT@/data/sire_vectors.sqlite3',
                        'snapshot_sha256': hash_value, 'records_by_table': counts,
                        'validation': {'integrity_check': integrity, 'fts_integrity': 'ok',
                                       'run_task_records': task_count, 'meta': meta},
                        'operation': 'SIRE rule sync task archive', 'run_id': RUN.name}
            db.with_name('snapshot-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return {'database': label, 'index': indexed, 'imported_task_files': imported,
                'this_run_task_records': task_count, 'knowledge_record': 'E-010',
                'integrity_check': integrity, 'fts_integrity': 'ok', 'embedding_orphans': 0,
                'sha256': hash_value, 'counts': counts, 'meta': meta}

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
proc = subprocess.run([sys.executable, str(SCRIPTS / 'sire_kb.py'), 'reindex'],
                      capture_output=True, text=True, encoding='utf-8', cwd=PACKAGE, timeout=60)
if proc.returncode:
    raise RuntimeError(proc.stderr)
report = {'run': RUN.name, 'databases': []}
for db, label in ((archive_db, 'archive'), (DATABASE_PATH, 'working')):
    report['databases'].append(archive_one(db, label))
for db in (archive_db, DATABASE_PATH):
    hits = vector.search_database(db, 'SIRE v6.11 规则同步 快速通道', 5, 0.12)
    assert hits
report['search_verified'] = True
(RUN / 'archive-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'archive': 'PASS', 'run': RUN.name, 'knowledge': 'E-010',
                  'task_counts': [d['this_run_task_records'] for d in report['databases']]}, ensure_ascii=False))
