import type { InboundMessage } from '../types.js';

interface Mention {
  key: string;
  name?: string;
}

type PostNode = { tag?: string; text?: string; href?: string; user_name?: string };

function flattenPost(content: any): string {
  // 收到的 post 可能是 {title, content} 或按语言包一层 {zh_cn: {title, content}}
  const body = Array.isArray(content?.content)
    ? content
    : (Object.values(content ?? {}).find((v: any) => Array.isArray(v?.content)) as any);
  if (!body) return '';
  const lines: string[] = [];
  if (body.title) lines.push(String(body.title));
  for (const row of body.content as PostNode[][]) {
    const parts = row.map((node) => {
      switch (node.tag) {
        case 'text':
        case 'md':
        case 'code_block':
          return node.text ?? '';
        case 'a':
          return node.text || node.href || '';
        default:
          return '';
      }
    });
    lines.push(parts.join(''));
  }
  return lines.join('\n');
}

/** 把飞书消息内容解析成纯文本，并去掉 @ 占位符。 */
export function extractText(messageType: string, content: string, mentions: Mention[] = []): string {
  let parsed: any;
  try {
    parsed = JSON.parse(content);
  } catch {
    return '';
  }
  let text = '';
  if (messageType === 'text') text = String(parsed?.text ?? '');
  else if (messageType === 'post') text = flattenPost(parsed);
  for (const m of mentions) text = text.split(m.key).join('');
  return text.replace(/[ \t]+\n/g, '\n').trim();
}

/** 把 im.message.receive_v1 事件转换成 InboundMessage。非用户发送的消息返回 null。 */
export function toInboundMessage(event: any): InboundMessage | null {
  const msg = event?.message;
  const openId = event?.sender?.sender_id?.open_id;
  if (!msg?.message_id || !openId || event?.sender?.sender_type !== 'user') return null;
  return {
    messageId: msg.message_id,
    chatId: msg.chat_id,
    chatType: msg.chat_type,
    rootId: msg.root_id || undefined,
    parentId: msg.parent_id || undefined,
    threadId: msg.thread_id || undefined,
    senderOpenId: openId,
    messageType: msg.message_type,
    text: extractText(msg.message_type, msg.content ?? '', msg.mentions ?? []),
  };
}
