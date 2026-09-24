import assert from 'node:assert/strict';
import type { AddressInfo } from 'node:net';
import { describe, it } from 'node:test';
import { mapClaudeHook, mapCodexNotify, startIngestServer } from '../src/ingest.js';
import { silentLogger } from '../src/log.js';
import type { LocalEvent } from '../src/types.js';

describe('mapClaudeHook', () => {
  const common = { session_id: 's1', cwd: '/w', transcript_path: '/t.jsonl' };
  it('UserPromptSubmit', () =>
    assert.deepEqual(mapClaudeHook({ ...common, hook_event_name: 'UserPromptSubmit', prompt: 'hi' }), {
      agent: 'claude',
      kind: 'prompt',
      ref: 's1',
      cwd: '/w',
      text: 'hi',
      origin: undefined,
    }));
  it('Stop 取 last_assistant_message', () =>
    assert.equal(mapClaudeHook({ ...common, hook_event_name: 'Stop', last_assistant_message: 'done' })?.text, 'done'));
  it('Notification', () =>
    assert.match(mapClaudeHook({ ...common, hook_event_name: 'Notification', notification_type: 'permission_prompt' })!.text!, /确认/));
  it('其他事件忽略', () => assert.equal(mapClaudeHook({ ...common, hook_event_name: 'PreToolUse' }), null));
});

describe('mapCodexNotify', () => {
  it('agent-turn-complete 拆成提问和回答', () => {
    const events = mapCodexNotify({
      type: 'agent-turn-complete',
      'thread-id': 'th',
      'turn-id': 't1',
      cwd: '/w',
      'input-messages': ['写单测'],
      'last-assistant-message': '写好了',
    });
    assert.deepEqual(
      events.map((e) => [e.kind, e.text]),
      [
        ['prompt', '写单测'],
        ['reply', '写好了'],
      ],
    );
  });
  it('其他类型忽略', () => assert.deepEqual(mapCodexNotify({ type: 'other' }), []));
});

describe('ingest server', () => {
  it('接收 hooks，校验 token，立即返回 {}', async () => {
    const received: LocalEvent[] = [];
    const server = await startIngestServer(
      { enabled: true, host: '127.0.0.1', port: 0, token: 'tk', forwardNotifications: true },
      async (ev) => {
        received.push(ev);
      },
      silentLogger,
    );
    const { port } = server.address() as AddressInfo;
    const post = (path: string, body: unknown, headers: Record<string, string> = {}) =>
      fetch(`http://127.0.0.1:${port}${path}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', ...headers },
        body: JSON.stringify(body),
      });
    try {
      const unauthorized = await post('/hooks/claude', {});
      assert.equal(unauthorized.status, 401);

      const res = await post(
        '/hooks/claude',
        { session_id: 's1', cwd: '/w', hook_event_name: 'UserPromptSubmit', prompt: 'hi' },
        { 'x-bridge-token': 'tk', 'x-bridge-origin': 'bridge' },
      );
      assert.equal(res.status, 200);
      assert.equal(await res.text(), '{}');
      const codex = await post(
        '/hooks/codex',
        { type: 'agent-turn-complete', 'thread-id': 'th', cwd: '/w', 'input-messages': ['a'], 'last-assistant-message': 'b' },
        { 'x-bridge-token': 'tk' },
      );
      assert.equal(codex.status, 200);
      await new Promise((r) => setTimeout(r, 20));
      assert.deepEqual(
        received.map((e) => [e.agent, e.kind, e.origin]),
        [
          ['claude', 'prompt', 'bridge'],
          ['codex', 'prompt', undefined],
          ['codex', 'reply', undefined],
        ],
      );
    } finally {
      server.close();
    }
  });
});
