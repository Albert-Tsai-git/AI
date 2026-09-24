import { createServer, type IncomingMessage, type Server } from 'node:http';
import type { Config } from './config.js';
import type { Logger } from './log.js';
import type { LocalEvent } from './types.js';

const NOTIFICATION_TEXT: Record<string, string> = {
  permission_prompt: '终端里的 Claude 在等你确认权限',
  idle_prompt: '终端里的 Claude 在等你输入',
  agent_needs_input: '终端里的 Claude 需要你补充信息',
};

/** Claude Code hooks 的输入 → LocalEvent。 */
export function mapClaudeHook(body: Record<string, any>, origin?: string): LocalEvent | null {
  const ref = body.session_id;
  if (typeof ref !== 'string' || !ref) return null;
  const base = { agent: 'claude' as const, ref, cwd: String(body.cwd ?? ''), origin };
  switch (body.hook_event_name) {
    case 'SessionStart':
      return { ...base, kind: 'session_start' };
    case 'SessionEnd':
      return { ...base, kind: 'session_end' };
    case 'UserPromptSubmit':
      return { ...base, kind: 'prompt', text: String(body.prompt ?? '') };
    case 'Stop':
      return { ...base, kind: 'reply', text: String(body.last_assistant_message ?? '') };
    case 'Notification': {
      const text = NOTIFICATION_TEXT[body.notification_type] ?? (typeof body.message === 'string' ? body.message : undefined);
      return text ? { ...base, kind: 'notify', text } : null;
    }
    default:
      return null;
  }
}

/** Codex notify（agent-turn-complete）的参数 → LocalEvent。一轮里同时包含提问和回答。 */
export function mapCodexNotify(body: Record<string, any>, origin?: string): LocalEvent[] {
  if (body.type !== 'agent-turn-complete') return [];
  const ref = body['thread-id'];
  if (typeof ref !== 'string' || !ref) return [];
  const base = { agent: 'codex' as const, ref, cwd: String(body.cwd ?? ''), origin };
  const inputs = Array.isArray(body['input-messages']) ? body['input-messages'].map(String) : [];
  const events: LocalEvent[] = [];
  if (inputs.length > 0) events.push({ ...base, kind: 'prompt', text: inputs.join('\n') });
  if (body['last-assistant-message']) events.push({ ...base, kind: 'reply', text: String(body['last-assistant-message']) });
  return events;
}

async function readJson(req: IncomingMessage): Promise<Record<string, any>> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 5 * 1024 * 1024) throw new Error('请求体过大');
    chunks.push(chunk as Buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

/**
 * 本机上报入口（只监听 127.0.0.1）：
 *   POST /hooks/claude  ← Claude Code HTTP hooks
 *   POST /hooks/codex   ← scripts/codex-notify.mjs
 * 立即返回 {}，不阻塞终端里的 AI。
 */
export function startIngestServer(
  cfg: Config['ingest'],
  onEvent: (ev: LocalEvent) => Promise<void>,
  log: Logger,
): Promise<Server> {
  const server = createServer(async (req, res) => {
    const reply = (code: number, body = '{}') => {
      res.writeHead(code, { 'content-type': 'application/json' });
      res.end(body);
    };
    if (req.method === 'GET' && req.url === '/health') return reply(200, '{"ok":true}');
    if (req.method !== 'POST' || (req.url !== '/hooks/claude' && req.url !== '/hooks/codex')) return reply(404);
    if (cfg.token && req.headers['x-bridge-token'] !== cfg.token) return reply(401);

    let body: Record<string, any>;
    try {
      body = await readJson(req);
    } catch {
      return reply(400);
    }
    reply(200);

    const origin = typeof req.headers['x-bridge-origin'] === 'string' ? req.headers['x-bridge-origin'] : undefined;
    const events = req.url === '/hooks/claude' ? [mapClaudeHook(body, origin)].filter((e): e is LocalEvent => e !== null) : mapCodexNotify(body, origin);
    for (const ev of events) {
      await onEvent(ev).catch((err) => log.error(`处理本地 ${ev.agent} 事件失败`, err));
    }
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(cfg.port, cfg.host, () => resolve(server));
  });
}
