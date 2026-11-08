export type AgentName = 'claude' | 'codex';

export const AGENT_NAMES: AgentName[] = ['claude', 'codex'];

/** 从飞书收到的一条消息（已解析成纯文本）。 */
export interface InboundMessage {
  messageId: string;
  chatId: string;
  chatType: string;
  rootId?: string;
  parentId?: string;
  threadId?: string;
  senderOpenId: string;
  messageType: string;
  text: string;
}

/** 飞书卡片按钮回调。 */
export interface CardAction {
  operatorOpenId: string;
  messageId?: string;
  value: Record<string, unknown>;
}

export interface CardActionResult {
  toast?: { type: 'success' | 'error' | 'info' | 'warning'; content: string };
  card?: { type: 'raw'; data: unknown };
}

/** 本机终端里的 Claude / Codex 通过 hooks / notify 上报的事件。 */
export interface LocalEvent {
  agent: AgentName;
  kind: 'session_start' | 'session_end' | 'prompt' | 'reply' | 'notify';
  ref: string;
  cwd: string;
  text?: string;
  /** 由桥接服务自己驱动的执行会带上 'bridge'，用于防止回环。 */
  origin?: string;
}
