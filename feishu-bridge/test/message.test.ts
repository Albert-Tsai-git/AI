import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { extractText, toInboundMessage } from '../src/feishu/message.js';
import { escapeCardMarkdown, redactSecrets } from '../src/util/text.js';

describe('extractText', () => {
  it('文本消息，去掉 @ 占位符', () => {
    const text = extractText('text', JSON.stringify({ text: '@_user_1 /codex 写单测' }), [{ key: '@_user_1' }]);
    assert.equal(text, '/codex 写单测');
  });

  it('富文本消息', () => {
    const content = {
      title: '需求',
      content: [
        [{ tag: 'text', text: '把 ' }, { tag: 'a', text: '这个页面', href: 'https://x' }, { tag: 'text', text: ' 改一下' }],
        [{ tag: 'at', user_id: 'ou_x' }, { tag: 'text', text: '谢谢' }],
      ],
    };
    assert.equal(extractText('post', JSON.stringify(content)), '需求\n把 这个页面 改一下\n谢谢');
  });

  it('按语言包一层的富文本', () => {
    const content = { zh_cn: { title: '', content: [[{ tag: 'text', text: '你好' }]] } };
    assert.equal(extractText('post', JSON.stringify(content)), '你好');
  });

  it('其他类型返回空', () => assert.equal(extractText('image', JSON.stringify({ image_key: 'x' })), ''));
});

describe('toInboundMessage', () => {
  const event = {
    sender: { sender_id: { open_id: 'ou_me' }, sender_type: 'user' },
    message: {
      message_id: 'om_1',
      root_id: 'om_0',
      parent_id: '',
      chat_id: 'oc_1',
      chat_type: 'p2p',
      message_type: 'text',
      content: JSON.stringify({ text: 'hi' }),
    },
  };
  it('解析用户消息', () => {
    assert.deepEqual(toInboundMessage(event), {
      messageId: 'om_1',
      chatId: 'oc_1',
      chatType: 'p2p',
      rootId: 'om_0',
      parentId: undefined,
      threadId: undefined,
      senderOpenId: 'ou_me',
      messageType: 'text',
      text: 'hi',
    });
  });
  it('忽略机器人消息', () => {
    assert.equal(toInboundMessage({ ...event, sender: { ...event.sender, sender_type: 'app' } }), null);
  });
});

describe('text utils', () => {
  it('密钥打码', () => {
    assert.equal(redactSecrets('key=sk-ant-api03-abcdefghijklmnopqrstuvwxyz'), 'key=[REDACTED]');
    assert.equal(redactSecrets('token ghp_abcdefghijklmnopqrstuvwxyz0123456789'), 'token [REDACTED]');
  });
  it('卡片 markdown 转义尖括号，代码块除外', () => {
    assert.equal(escapeCardMarkdown('a<b>\n```\nx<y\n```'), 'a&lt;b&gt;\n```\nx<y\n```');
  });
});
