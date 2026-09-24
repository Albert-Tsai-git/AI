# -*- coding: utf-8 -*-
"""[存储] 中间服务唯一的状态存储（SQLite）。所有状态迁移都用条件更新（CAS），避免并发重复执行。"""
import json
import secrets
import sqlite3
import threading
import time

from hub import config

# 任务状态（与 PROTOCOL.md §7.1 一致）
NEED_EXECUTOR, NEED_DIR, NEED_CONFIRM = "NEED_EXECUTOR", "NEED_DIR", "NEED_CONFIRM"
QUEUED, LEASED, WAITING_EXTERNAL = "QUEUED", "LEASED", "WAITING_EXTERNAL"
RESULT_SAVED, DONE, FAILED = "RESULT_SAVED", "DONE", "FAILED"
NEEDS_RECOVERY, CANCELLED = "NEEDS_RECOVERY", "CANCELLED"
FINAL = (DONE, FAILED, CANCELLED)

TASK_COLS = ("task_id", "conversation_id", "executor", "mode", "session_id", "cwd", "proposed_cwd",
             "prompt", "status", "attempt", "lease_id", "lease_expires", "instance_id", "delivery",
             "queue_id", "notice_mid", "source_mid", "result_text", "error", "busy_retries",
             "not_before", "resume_hint", "danger_ok", "created", "updated", "started", "finished")
OUTBOX_COLS = ("id", "kind", "payload", "reply_to", "executor", "session_id", "cwd", "task_id",
               "conversation_id", "notice_task", "status", "attempts", "next_try", "mid", "error",
               "created", "sent")

_local = threading.local()
DB_PATH = config.DB_PATH  # 测试可替换


def _conn():
    """每线程一个连接；WAL 模式支持 HTTP 线程、飞书线程、后台线程并发读写。"""
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "path", None) != DB_PATH:
        c = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=15000")
        _local.conn, _local.path = c, DB_PATH
    return c


class _tx:
    """BEGIN IMMEDIATE 事务上下文：写锁在事务开始时获取，杜绝读后写竞态。"""

    def __enter__(self):
        self.c = _conn()
        self.c.execute("BEGIN IMMEDIATE")
        return self.c

    def __exit__(self, et, ev, tb):
        self.c.execute("ROLLBACK" if et else "COMMIT")
        return False


def init():
    c = _conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS tasks(
        task_id TEXT PRIMARY KEY, conversation_id TEXT, executor TEXT, mode TEXT, session_id TEXT,
        cwd TEXT, proposed_cwd TEXT, prompt TEXT, status TEXT NOT NULL, attempt INTEGER DEFAULT 0,
        lease_id TEXT, lease_expires REAL, instance_id TEXT, delivery TEXT, queue_id TEXT,
        notice_mid TEXT, source_mid TEXT, result_text TEXT, error TEXT, busy_retries INTEGER DEFAULT 0,
        not_before REAL DEFAULT 0, resume_hint TEXT, danger_ok INTEGER DEFAULT 0, created REAL, updated REAL, started REAL, finished REAL);
    CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
    CREATE INDEX IF NOT EXISTS idx_tasks_notice ON tasks(notice_mid);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_source ON tasks(source_mid);
    CREATE TABLE IF NOT EXISTS events(
        task_id TEXT, lease_id TEXT, seq INTEGER, type TEXT, data TEXT, response TEXT, created REAL,
        PRIMARY KEY(task_id, lease_id, seq));
    CREATE TABLE IF NOT EXISTS msg_map(
        message_id TEXT PRIMARY KEY, executor TEXT, session_id TEXT, cwd TEXT, task_id TEXT,
        conversation_id TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS seen(event_id TEXT PRIMARY KEY, created REAL);
    CREATE TABLE IF NOT EXISTS outbox(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, payload TEXT NOT NULL, reply_to TEXT,
        executor TEXT, session_id TEXT, cwd TEXT, task_id TEXT, conversation_id TEXT, notice_task TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
        next_try REAL NOT NULL DEFAULT 0, mid TEXT, error TEXT, created REAL, sent REAL);
    CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status);
    CREATE TABLE IF NOT EXISTS turns(executor TEXT, session_id TEXT, turn_id TEXT, created REAL,
        PRIMARY KEY(executor, session_id, turn_id));
    CREATE TABLE IF NOT EXISTS inbox(id INTEGER PRIMARY KEY AUTOINCREMENT, executor TEXT, session_id TEXT,
        prompt TEXT, reply TEXT, created REAL, acked INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS executors(executor TEXT, instance_id TEXT, version TEXT, capabilities TEXT,
        last_seen REAL, PRIMARY KEY(executor, instance_id));
    CREATE TABLE IF NOT EXISTS task_starts(task_id TEXT, ts REAL);
    CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
    """)


def new_id(prefix):
    return "%s%s-%s" % (prefix, time.strftime("%Y%m%d-%H%M%S"), secrets.token_hex(3))


def _row(cols, r):
    return dict(zip(cols, r)) if r else None


# ---------------- 任务 ----------------

def create_task(source_mid, executor, mode, session_id, cwd, prompt, status, conversation_id=None):
    """[账本] 以飞书消息 ID 为幂等键建任务；重复投递返回 None。"""
    tid = new_id("T")
    now = time.time()
    with _tx() as c:
        cur = c.execute("INSERT OR IGNORE INTO tasks(task_id, conversation_id, executor, mode, session_id, cwd, "
                        "prompt, status, source_mid, created, updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (tid, conversation_id or new_id("C"), executor, mode, session_id or "", cwd or "",
                         prompt, status, source_mid, now, now))
        return tid if cur.rowcount == 1 else None


def get_task(task_id):
    return _row(TASK_COLS, _conn().execute("SELECT %s FROM tasks WHERE task_id=?" % ",".join(TASK_COLS),
                                           (task_id,)).fetchone())


def find_task_by_notice(mid):
    return _row(TASK_COLS, _conn().execute("SELECT %s FROM tasks WHERE notice_mid=?" % ",".join(TASK_COLS),
                                           (mid,)).fetchone())


def list_tasks(*statuses):
    rows = _conn().execute("SELECT %s FROM tasks WHERE status IN (%s) ORDER BY created"
                           % (",".join(TASK_COLS), ",".join("?" * len(statuses))), statuses).fetchall()
    return [_row(TASK_COLS, r) for r in rows]


def cas(task_id, from_status, to_status, **fields):
    """[账本] 条件迁移：当前状态属于 from_status 才更新，返回是否成功。"""
    froms = (from_status,) if isinstance(from_status, str) else tuple(from_status)
    fields.update(status=to_status, updated=time.time())
    if to_status in FINAL:
        fields.setdefault("finished", time.time())
    keys = list(fields)
    with _tx() as c:
        return c.execute("UPDATE tasks SET %s WHERE task_id=? AND status IN (%s)"
                         % (",".join("%s=?" % k for k in keys), ",".join("?" * len(froms))),
                         [fields[k] for k in keys] + [task_id] + list(froms)).rowcount == 1


def update(task_id, **fields):
    fields["updated"] = time.time()
    keys = list(fields)
    with _tx() as c:
        c.execute("UPDATE tasks SET %s WHERE task_id=?" % ",".join("%s=?" % k for k in keys),
                  [fields[k] for k in keys] + [task_id])


def _midnight():
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


def lease_next(executor, instance_id, capabilities, ttl, daily_limit, cwd_key):
    """[派发] 原子领取一条可执行任务。保证同会话、同目录最多一个有效租约；到达日上限返回 ('limit', task)。
    cwd_key 为规范化目录函数。返回 (状态, 任务) ，状态为 ok / limit / none。"""
    now = time.time()
    with _tx() as c:
        cands = [_row(TASK_COLS, r) for r in c.execute(
            "SELECT %s FROM tasks WHERE status=? AND executor=? AND not_before<=? ORDER BY created"
            % ",".join(TASK_COLS), (QUEUED, executor, now)).fetchall()]
        if not cands:
            return "none", None
        active = [_row(TASK_COLS, r) for r in c.execute(
            "SELECT %s FROM tasks WHERE status=?" % ",".join(TASK_COLS), (LEASED,)).fetchall()]
        busy_sessions = {(a["executor"], a["session_id"]) for a in active if a["session_id"]}
        busy_cwds = {cwd_key(a["cwd"]) for a in active}
        for t in cands:
            if t["mode"] == "new" and not capabilities.get("new_session", True):
                continue
            if t["session_id"] and (t["executor"], t["session_id"]) in busy_sessions:
                continue
            if cwd_key(t["cwd"]) in busy_cwds:
                continue
            if c.execute("SELECT COUNT(*) FROM task_starts WHERE ts>=?", (_midnight(),)).fetchone()[0] >= daily_limit:
                c.execute("UPDATE tasks SET status=?, error='daily_limit', updated=?, finished=? WHERE task_id=?",
                          (FAILED, now, now, t["task_id"]))
                return "limit", t
            lease = "L" + secrets.token_hex(8)
            c.execute("UPDATE tasks SET status=?, lease_id=?, lease_expires=?, instance_id=?, attempt=attempt+1, "
                      "started=?, updated=?, delivery=NULL, queue_id=NULL WHERE task_id=?",
                      (LEASED, lease, now + ttl, instance_id, now, now, t["task_id"]))
            c.execute("INSERT INTO task_starts VALUES(?,?)", (t["task_id"], now))
            return "ok", _row(TASK_COLS, c.execute("SELECT %s FROM tasks WHERE task_id=?" % ",".join(TASK_COLS),
                                                   (t["task_id"],)).fetchone())
    return "none", None


def unstart(task_id):
    """release：未执行归还任务，不计入日上限。"""
    with _tx() as c:
        c.execute("DELETE FROM task_starts WHERE rowid=(SELECT MAX(rowid) FROM task_starts WHERE task_id=?)",
                  (task_id,))


def event_lookup(task_id, lease_id, seq):
    r = _conn().execute("SELECT response FROM events WHERE task_id=? AND lease_id=? AND seq=?",
                        (task_id, lease_id, seq)).fetchone()
    return json.loads(r[0]) if r else None


def event_save(task_id, lease_id, seq, etype, data, response):
    with _tx() as c:
        c.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)",
                  (task_id, lease_id, seq, etype, json.dumps(data, ensure_ascii=False),
                   json.dumps(response, ensure_ascii=False), time.time()))


def oldest_waiting(executor, session_id):
    return _row(TASK_COLS, _conn().execute(
        "SELECT %s FROM tasks WHERE status=? AND executor=? AND session_id=? ORDER BY started LIMIT 1"
        % ",".join(TASK_COLS), (WAITING_EXTERNAL, executor, session_id)).fetchone())


# ---------------- 消息映射 / 去重 ----------------

def save_mapping(mid, executor, session_id, cwd, task_id="", conversation_id=""):
    with _tx() as c:
        c.execute("INSERT OR REPLACE INTO msg_map VALUES(?,?,?,?,?,?,?)",
                  (mid, executor, session_id, cwd, task_id, conversation_id, time.time()))


def find_mapping(mid):
    r = _conn().execute("SELECT executor, session_id, cwd, task_id, conversation_id FROM msg_map "
                        "WHERE message_id=?", (mid,)).fetchone()
    return dict(zip(("executor", "session_id", "cwd", "task_id", "conversation_id"), r)) if r else None


def sessions_in_cwd(executor, cwd_norm, cwd_key):
    """同目录下该执行者已知的会话（去重，最新在前）。"""
    rows = _conn().execute("SELECT session_id, cwd, MAX(created) m FROM msg_map WHERE executor=? AND session_id!='' "
                           "GROUP BY session_id, cwd ORDER BY m DESC", (executor,)).fetchall()
    out = []
    for sid, cwd, _m in rows:
        if cwd_key(cwd) == cwd_norm and sid not in out:
            out.append(sid)
    return out


def mark_seen(event_id):
    with _tx() as c:
        return c.execute("INSERT OR IGNORE INTO seen VALUES(?,?)", (event_id, time.time())).rowcount == 1


def unmark_seen(event_id):
    with _tx() as c:
        c.execute("DELETE FROM seen WHERE event_id=?", (event_id,))


def turn_seen(executor, session_id, turn_id):
    """桌面独立轮次去重：首次返回 True。"""
    with _tx() as c:
        return c.execute("INSERT OR IGNORE INTO turns VALUES(?,?,?,?)",
                         (executor, session_id, turn_id, time.time())).rowcount == 1


# ---------------- 发送队列（唯一的飞书出口） ----------------

def enqueue(kind, payload, reply_to="", executor="", session_id="", cwd="", task_id="", conversation_id="",
            notice_task=""):
    with _tx() as c:
        return c.execute("INSERT INTO outbox(kind,payload,reply_to,executor,session_id,cwd,task_id,conversation_id,"
                         "notice_task,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (kind, payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
                          reply_to or "", executor or "", session_id or "", cwd or "", task_id or "",
                          conversation_id or "", notice_task or "", time.time())).lastrowid


def outbox_pending(limit=50):
    rows = _conn().execute("SELECT %s FROM outbox WHERE status='PENDING' ORDER BY id LIMIT ?"
                           % ",".join(OUTBOX_COLS), (limit,)).fetchall()
    return [_row(OUTBOX_COLS, r) for r in rows]


def outbox_claim(oid):
    with _tx() as c:
        return c.execute("UPDATE outbox SET status='SENDING' WHERE id=? AND status='PENDING'", (oid,)).rowcount == 1


def outbox_sent(oid, mid):
    with _tx() as c:
        c.execute("UPDATE outbox SET status='SENT', mid=?, sent=?, error=NULL WHERE id=?", (mid, time.time(), oid))


def outbox_retry(oid, err, delay):
    with _tx() as c:
        c.execute("UPDATE outbox SET status='PENDING', attempts=attempts+1, next_try=?, error=? WHERE id=?",
                  (time.time() + delay, (err or "")[:300], oid))


def outbox_reset_sending():
    with _tx() as c:
        return c.execute("UPDATE outbox SET status='PENDING' WHERE status='SENDING'").rowcount


def outbox_unsent_for_task(task_id):
    return _conn().execute("SELECT COUNT(*) FROM outbox WHERE task_id=? AND status!='SENT'",
                           (task_id,)).fetchone()[0]


# ---------------- 桌面同步 / 执行器 / kv ----------------

def inbox_add(executor, session_id, prompt, reply):
    with _tx() as c:
        c.execute("INSERT INTO inbox(executor,session_id,prompt,reply,created) VALUES(?,?,?,?,?)",
                  (executor, session_id, prompt, reply, time.time()))


def inbox_list(executor, session_id):
    return _conn().execute("SELECT id, created, prompt, reply FROM inbox WHERE executor=? AND session_id=? "
                           "AND acked=0 ORDER BY id", (executor, session_id)).fetchall()


def inbox_ack(executor, session_id, ids):
    if not ids:
        return
    with _tx() as c:
        c.execute("UPDATE inbox SET acked=1 WHERE executor=? AND session_id=? AND id IN (%s)"
                  % ",".join("?" * len(ids)), [executor, session_id] + list(ids))


def executor_seen(executor, instance_id, version=None, capabilities=None):
    with _tx() as c:
        if capabilities is not None:
            c.execute("INSERT OR REPLACE INTO executors VALUES(?,?,?,?,?)",
                      (executor, instance_id, version or "", json.dumps(capabilities), time.time()))
        else:
            c.execute("UPDATE executors SET last_seen=? WHERE executor=? AND instance_id=?",
                      (time.time(), executor, instance_id))


def executor_caps(executor, instance_id):
    r = _conn().execute("SELECT capabilities FROM executors WHERE executor=? AND instance_id=?",
                        (executor, instance_id)).fetchone()
    return json.loads(r[0]) if r and r[0] else {}


def executor_online(executor, within):
    return _conn().execute("SELECT 1 FROM executors WHERE executor=? AND last_seen>=?",
                           (executor, time.time() - within)).fetchone() is not None


def kv_get(k, default=None):
    r = _conn().execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


def kv_set(k, v):
    with _tx() as c:
        c.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, str(v)))
