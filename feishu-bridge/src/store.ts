import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import type { AgentName } from './types.js';
import { shortId } from './util/text.js';

export interface SessionRow {
  id: string;
  agent: AgentName;
  project: string;
  cwd: string;
  /** Claude 的 session_id / Codex 的 thread_id；首轮执行前为空。 */
  agentRef: string | null;
  chatId: string | null;
  rootMessageId: string | null;
  origin: 'feishu' | 'local';
  /** 是否正在本机终端里打开（由 Claude hooks 的 SessionStart / SessionEnd 维护）。 */
  live: boolean;
  createdAt: number;
  updatedAt: number;
}

export interface TurnRow {
  id: string;
  sessionId: string;
  prompt: string;
  status: 'running' | 'done' | 'failed' | 'cancelled' | 'interrupted';
  cardMessageId: string | null;
  result: string | null;
  startedAt: number;
  finishedAt: number | null;
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  agent TEXT NOT NULL,
  project TEXT NOT NULL,
  cwd TEXT NOT NULL,
  agent_ref TEXT,
  chat_id TEXT,
  root_message_id TEXT,
  origin TEXT NOT NULL,
  live INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS sessions_agent_ref ON sessions(agent, agent_ref);
CREATE TABLE IF NOT EXISTS message_links (
  message_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processed (
  key TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  prompt TEXT NOT NULL,
  status TEXT NOT NULL,
  card_message_id TEXT,
  result TEXT,
  started_at INTEGER NOT NULL,
  finished_at INTEGER
);
`;

type Row = Record<string, any>;

function toSession(r: Row | undefined): SessionRow | undefined {
  if (!r) return undefined;
  return {
    id: r.id,
    agent: r.agent,
    project: r.project,
    cwd: r.cwd,
    agentRef: r.agent_ref ?? null,
    chatId: r.chat_id ?? null,
    rootMessageId: r.root_message_id ?? null,
    origin: r.origin,
    live: r.live === 1,
    createdAt: r.created_at,
    updatedAt: r.updated_at,
  };
}

function toTurn(r: Row): TurnRow {
  return {
    id: r.id,
    sessionId: r.session_id,
    prompt: r.prompt,
    status: r.status,
    cardMessageId: r.card_message_id ?? null,
    result: r.result ?? null,
    startedAt: r.started_at,
    finishedAt: r.finished_at ?? null,
  };
}

export class Store {
  private db: DatabaseSync;

  constructor(path: string) {
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    this.db.exec('PRAGMA journal_mode = WAL;');
    this.db.exec(SCHEMA);
  }

  close(): void {
    this.db.close();
  }

  /** 返回 true 表示第一次见到该 key（用于飞书事件去重）。 */
  markProcessed(key: string): boolean {
    const res = this.db.prepare('INSERT OR IGNORE INTO processed (key, created_at) VALUES (?, ?)').run(key, Date.now());
    return Number(res.changes) > 0;
  }

  pruneProcessed(olderThanMs: number): void {
    this.db.prepare('DELETE FROM processed WHERE created_at < ?').run(Date.now() - olderThanMs);
  }

  createSession(input: {
    agent: AgentName;
    project: string;
    cwd: string;
    origin: SessionRow['origin'];
    agentRef?: string;
    chatId?: string;
    rootMessageId?: string;
    live?: boolean;
  }): SessionRow {
    const now = Date.now();
    const id = shortId('s');
    this.db
      .prepare(
        `INSERT INTO sessions (id, agent, project, cwd, agent_ref, chat_id, root_message_id, origin, live, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(
        id,
        input.agent,
        input.project,
        input.cwd,
        input.agentRef ?? null,
        input.chatId ?? null,
        input.rootMessageId ?? null,
        input.origin,
        input.live ? 1 : 0,
        now,
        now,
      );
    if (input.rootMessageId) this.linkMessage(input.rootMessageId, id);
    return this.getSession(id)!;
  }

  getSession(id: string): SessionRow | undefined {
    return toSession(this.db.prepare('SELECT * FROM sessions WHERE id = ?').get(id) as Row | undefined);
  }

  findSessionByRef(agent: AgentName, ref: string): SessionRow | undefined {
    return toSession(
      this.db.prepare('SELECT * FROM sessions WHERE agent = ? AND agent_ref = ?').get(agent, ref) as Row | undefined,
    );
  }

  findSessionByMessage(messageId: string | undefined): SessionRow | undefined {
    if (!messageId) return undefined;
    const link = this.db.prepare('SELECT session_id FROM message_links WHERE message_id = ?').get(messageId) as
      | Row
      | undefined;
    return link ? this.getSession(link.session_id) : undefined;
  }

  updateSession(id: string, patch: Partial<Pick<SessionRow, 'agentRef' | 'chatId' | 'rootMessageId' | 'live'>>): void {
    const sets: string[] = [];
    const values: (string | number | null)[] = [];
    if (patch.agentRef !== undefined) sets.push('agent_ref = ?'), values.push(patch.agentRef);
    if (patch.chatId !== undefined) sets.push('chat_id = ?'), values.push(patch.chatId);
    if (patch.rootMessageId !== undefined) sets.push('root_message_id = ?'), values.push(patch.rootMessageId);
    if (patch.live !== undefined) sets.push('live = ?'), values.push(patch.live ? 1 : 0);
    sets.push('updated_at = ?');
    values.push(Date.now());
    this.db.prepare(`UPDATE sessions SET ${sets.join(', ')} WHERE id = ?`).run(...values, id);
  }

  listSessions(limit = 10): SessionRow[] {
    return (this.db.prepare('SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?').all(limit) as Row[]).map(
      (r) => toSession(r)!,
    );
  }

  linkMessage(messageId: string, sessionId: string): void {
    this.db.prepare('INSERT OR REPLACE INTO message_links (message_id, session_id) VALUES (?, ?)').run(messageId, sessionId);
  }

  createTurn(sessionId: string, prompt: string): TurnRow {
    const id = shortId('t');
    this.db
      .prepare('INSERT INTO turns (id, session_id, prompt, status, started_at) VALUES (?, ?, ?, ?, ?)')
      .run(id, sessionId, prompt, 'running', Date.now());
    return toTurn(this.db.prepare('SELECT * FROM turns WHERE id = ?').get(id) as Row);
  }

  updateTurn(id: string, patch: Partial<Pick<TurnRow, 'status' | 'cardMessageId' | 'result'>>): void {
    const sets: string[] = [];
    const values: (string | number | null)[] = [];
    if (patch.status !== undefined) {
      sets.push('status = ?');
      values.push(patch.status);
      if (patch.status !== 'running') sets.push('finished_at = ?'), values.push(Date.now());
    }
    if (patch.cardMessageId !== undefined) sets.push('card_message_id = ?'), values.push(patch.cardMessageId);
    if (patch.result !== undefined) sets.push('result = ?'), values.push(patch.result);
    if (sets.length === 0) return;
    this.db.prepare(`UPDATE turns SET ${sets.join(', ')} WHERE id = ?`).run(...values, id);
  }

  /** 服务重启时，把上次没跑完的任务标记为中断，返回它们以便更新卡片。 */
  interruptRunningTurns(): TurnRow[] {
    const rows = (this.db.prepare("SELECT * FROM turns WHERE status = 'running'").all() as Row[]).map(toTurn);
    this.db.prepare("UPDATE turns SET status = 'interrupted', finished_at = ? WHERE status = 'running'").run(Date.now());
    return rows;
  }
}
