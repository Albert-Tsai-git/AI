import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { createEventDispatcher } from '../src/feishu/events.js';
import { silentLogger } from '../src/log.js';
import type { CardAction, InboundMessage } from '../src/types.js';

/** 用飞书 schema 2.0 事件结构走一遍 SDK 的 EventDispatcher，确认处理函数拿到的字段正确。 */
describe('飞书事件分发', () => {
  const messages: InboundMessage[] = [];
  const actions: CardAction[] = [];
  const dispatcher = createEventDispatcher(
    {
      onMessage: async (m) => {
        messages.push(m);
      },
      onCardAction: async (a) => {
        actions.push(a);
        return { toast: { type: 'success', content: 'ok' } };
      },
    },
    silentLogger,
  );

  it('im.message.receive_v1', async () => {
    await dispatcher.invoke(
      {
        schema: '2.0',
        header: { event_id: 'ev1', event_type: 'im.message.receive_v1', app_id: 'cli_x', tenant_key: 't' },
        event: {
          sender: { sender_id: { open_id: 'ou_me' }, sender_type: 'user', tenant_key: 't' },
          message: {
            message_id: 'om_2',
            root_id: 'om_1',
            parent_id: 'om_1',
            create_time: '1',
            chat_id: 'oc_1',
            thread_id: 'omt_1',
            chat_type: 'p2p',
            message_type: 'text',
            content: '{"text":"继续"}',
          },
        },
      },
      { needCheck: false },
    );
    await new Promise((r) => setImmediate(r));
    assert.equal(messages.length, 1);
    assert.equal(messages[0].text, '继续');
    assert.equal(messages[0].rootId, 'om_1');
    assert.equal(messages[0].senderOpenId, 'ou_me');
  });

  it('card.action.trigger 返回 toast', async () => {
    const ret = await dispatcher.invoke(
      {
        schema: '2.0',
        header: { event_id: 'ev2', event_type: 'card.action.trigger', app_id: 'cli_x', tenant_key: 't' },
        event: {
          operator: { open_id: 'ou_me' },
          token: 'c-xxx',
          action: { tag: 'button', value: { a: 'stop', s: 's1' } },
          context: { open_message_id: 'om_card', open_chat_id: 'oc_1' },
        },
      },
      { needCheck: false },
    );
    assert.deepEqual(ret, { toast: { type: 'success', content: 'ok' } });
    assert.deepEqual(actions[0], { operatorOpenId: 'ou_me', messageId: 'om_card', value: { a: 'stop', s: 's1' } });
  });
});
