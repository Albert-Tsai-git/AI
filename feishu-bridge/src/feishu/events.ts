import * as lark from '@larksuiteoapi/node-sdk';
import type { Config } from '../config.js';
import type { Logger } from '../log.js';
import type { CardAction, CardActionResult, InboundMessage } from '../types.js';
import { feishuDomain } from './api.js';
import { toInboundMessage } from './message.js';

export interface EventTarget {
  onMessage(msg: InboundMessage): Promise<void>;
  onCardAction(action: CardAction): Promise<CardActionResult>;
}

/**
 * - im.message.receive_v1：收到消息。飞书要求 3 秒内处理完，所以这里只投递、不等待执行。
 * - card.action.trigger：卡片按钮回调，返回 toast。
 */
export function createEventDispatcher(target: EventTarget, log: Logger): lark.EventDispatcher {
  return new lark.EventDispatcher({ loggerLevel: lark.LoggerLevel.warn }).register<{
    'card.action.trigger': (data: any) => Promise<unknown>;
  }>({
    'im.message.receive_v1': (data) => {
      const msg = toInboundMessage(data);
      if (msg) void target.onMessage(msg).catch((err) => log.error('处理飞书消息失败', err));
    },
    'card.action.trigger': async (data: any) => {
      const operatorOpenId = data?.operator?.open_id;
      const value = data?.action?.value;
      if (!operatorOpenId || !value || typeof value !== 'object') return {};
      return target.onCardAction({
        operatorOpenId,
        messageId: data?.context?.open_message_id ?? data?.open_message_id,
        value: value as Record<string, unknown>,
      });
    },
  });
}

/** 通过长连接接收飞书事件和卡片回调（不需要公网地址）。 */
export async function startFeishuEvents(cfg: Config, target: EventTarget, log: Logger): Promise<lark.WSClient> {
  const ws = new lark.WSClient({
    appId: cfg.feishu.appId,
    appSecret: cfg.feishu.appSecret,
    domain: feishuDomain(cfg),
    loggerLevel: lark.LoggerLevel.warn,
    onReady: () => log.info('飞书长连接已建立'),
    onError: (err) => log.error('飞书长连接失败', err),
  });
  await ws.start({ eventDispatcher: createEventDispatcher(target, log) });
  return ws;
}
