import * as lark from '@larksuiteoapi/node-sdk';
import type { Config } from '../config.js';
import type { Card } from './cards.js';

export type OutMessage = { type: 'text'; text: string } | { type: 'card'; card: Card } | { type: 'file'; fileKey: string };

/** 桥接服务用到的飞书能力。测试里用内存实现替换。 */
export interface FeishuApi {
  /** 回复某条消息，返回新消息 id。inThread=true 时落在话题里。 */
  reply(messageId: string, msg: OutMessage, inThread: boolean): Promise<string>;
  sendToUser(openId: string, msg: OutMessage): Promise<string>;
  updateCard(messageId: string, card: Card): Promise<void>;
  uploadFile(fileName: string, content: Buffer): Promise<string>;
}

function toContent(msg: OutMessage): { msg_type: string; content: string } {
  switch (msg.type) {
    case 'text':
      return { msg_type: 'text', content: JSON.stringify({ text: msg.text }) };
    case 'card':
      return { msg_type: 'interactive', content: JSON.stringify(msg.card) };
    case 'file':
      return { msg_type: 'file', content: JSON.stringify({ file_key: msg.fileKey }) };
  }
}

interface ApiResponse {
  code?: number;
  msg?: string;
  data?: { message_id?: string };
}

function unwrap(res: ApiResponse | undefined | null, action: string): string {
  if (!res || (res.code !== undefined && res.code !== 0)) {
    throw new Error(`飞书 ${action} 失败：${res?.code} ${res?.msg}`);
  }
  const id = res.data?.message_id;
  if (!id) throw new Error(`飞书 ${action} 未返回 message_id`);
  return id;
}

/** 飞书频控时重试一次。 */
async function withRetry<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    await new Promise((r) => setTimeout(r, 1000));
    return fn().catch(() => {
      throw err;
    });
  }
}

export function feishuDomain(cfg: Config): lark.Domain {
  return cfg.feishu.domain === 'lark' ? lark.Domain.Lark : lark.Domain.Feishu;
}

export class LarkFeishuApi implements FeishuApi {
  readonly client: lark.Client;

  constructor(cfg: Config) {
    this.client = new lark.Client({
      appId: cfg.feishu.appId,
      appSecret: cfg.feishu.appSecret,
      appType: lark.AppType.SelfBuild,
      domain: feishuDomain(cfg),
      loggerLevel: lark.LoggerLevel.warn,
    });
  }

  reply(messageId: string, msg: OutMessage, inThread: boolean): Promise<string> {
    return withRetry(async () =>
      unwrap(
        await this.client.im.v1.message.reply({
          path: { message_id: messageId },
          data: { ...toContent(msg), reply_in_thread: inThread },
        }),
        '回复消息',
      ),
    );
  }

  sendToUser(openId: string, msg: OutMessage): Promise<string> {
    return withRetry(async () =>
      unwrap(
        await this.client.im.v1.message.create({
          params: { receive_id_type: 'open_id' },
          data: { receive_id: openId, ...toContent(msg) },
        }),
        '发送消息',
      ),
    );
  }

  async updateCard(messageId: string, card: Card): Promise<void> {
    const res = await this.client.im.v1.message.patch({
      path: { message_id: messageId },
      data: { content: JSON.stringify(card) },
    });
    if (res?.code !== undefined && res.code !== 0) throw new Error(`飞书更新卡片失败：${res.code} ${res.msg}`);
  }

  async uploadFile(fileName: string, content: Buffer): Promise<string> {
    const res = await this.client.im.v1.file.create({ data: { file_type: 'stream', file_name: fileName, file: content } });
    if (!res?.file_key) throw new Error('飞书上传文件失败');
    return res.file_key;
  }
}
