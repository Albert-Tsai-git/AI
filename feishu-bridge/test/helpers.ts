import type { AgentAdapter, TurnRequest, TurnResult, TurnSink } from '../src/agents/types.js';
import { Analyzer, type Classifier } from '../src/analyzer.js';
import { Bridge } from '../src/bridge.js';
import { buildConfig, type Config } from '../src/config.js';
import type { FeishuApi, OutMessage } from '../src/feishu/api.js';
import type { Card } from '../src/feishu/cards.js';
import { Store } from '../src/store.js';
import type { AgentName, InboundMessage } from '../src/types.js';

export interface SentMessage {
  id: string;
  to: string;
  kind: 'reply' | 'user';
  msg: OutMessage;
  inThread: boolean;
}

export class FakeFeishu implements FeishuApi {
  sent: SentMessage[] = [];
  updates: { id: string; card: Card }[] = [];
  files: { name: string; content: string }[] = [];
  private n = 0;

  async reply(messageId: string, msg: OutMessage, inThread: boolean): Promise<string> {
    const id = `om_bot_${++this.n}`;
    this.sent.push({ id, to: messageId, kind: 'reply', msg, inThread });
    return id;
  }

  async sendToUser(openId: string, msg: OutMessage): Promise<string> {
    const id = `om_bot_${++this.n}`;
    this.sent.push({ id, to: openId, kind: 'user', msg, inThread: false });
    return id;
  }

  async updateCard(id: string, card: Card): Promise<void> {
    this.updates.push({ id, card });
  }

  async uploadFile(name: string, content: Buffer): Promise<string> {
    this.files.push({ name, content: content.toString('utf8') });
    return `file_${this.files.length}`;
  }

  /** 某条卡片消息当前的内容（最后一次更新，没有更新则为最初发送的内容）。 */
  currentCard(id: string): string {
    const update = [...this.updates].reverse().find((u) => u.id === id);
    if (update) return JSON.stringify(update.card);
    const sent = this.sent.find((s) => s.id === id);
    return sent?.msg.type === 'card' ? JSON.stringify(sent.msg.card) : '';
  }

  cardsContaining(text: string): SentMessage[] {
    return this.sent.filter((s) => s.msg.type === 'card' && JSON.stringify(s.msg.card).includes(text));
  }

  textsTo(to: string): string[] {
    return this.sent.filter((s) => s.to === to && s.msg.type === 'text').map((s) => (s.msg as { text: string }).text);
  }
}

export type Script = (req: TurnRequest, sink: TurnSink) => Promise<TurnResult>;

export class FakeAdapter implements AgentAdapter {
  calls: TurnRequest[] = [];
  script: Script = async (req) => ({ sessionRef: req.sessionRef ?? `${this.name}-ref-${this.calls.length}`, result: `完成：${req.prompt}`, isError: false });

  constructor(
    readonly name: AgentName,
    readonly label: string,
  ) {}

  resumeHint(ref: string): string {
    return `${this.name} --resume ${ref}`;
  }

  async runTurn(req: TurnRequest, sink: TurnSink): Promise<TurnResult> {
    this.calls.push(req);
    return this.script(req, sink);
  }
}

export function testConfig(overrides: Record<string, unknown> = {}): Config {
  return buildConfig({
    feishu: { appId: 'app', appSecret: 'secret', allowedOpenIds: ['ou_me'] },
    projects: {
      web: { path: '/tmp/web', aliases: ['前端'] },
      api: { path: '/tmp/api', agent: 'codex' },
    },
    defaultProject: 'web',
    analyzer: { mode: 'rules', keywords: { codex: ['单测'] } },
    ui: { updateIntervalMs: 0 },
    storagePath: ':memory:',
    ...overrides,
  });
}

export function setup(opts: { config?: Config; classify?: Classifier } = {}) {
  const config = opts.config ?? testConfig();
  const store = new Store(':memory:');
  const feishu = new FakeFeishu();
  const claude = new FakeAdapter('claude', 'Claude');
  const codex = new FakeAdapter('codex', 'Codex');
  const bridge = new Bridge({
    config,
    store,
    feishu,
    adapters: { claude, codex },
    analyzer: new Analyzer(config, opts.classify),
  });
  return { config, store, feishu, claude, codex, bridge };
}

let seq = 0;
export function userMessage(text: string, extra: Partial<InboundMessage> = {}): InboundMessage {
  return {
    messageId: `om_user_${++seq}`,
    chatId: 'oc_p2p',
    chatType: 'p2p',
    senderOpenId: 'ou_me',
    messageType: 'text',
    text,
    ...extra,
  };
}

export async function waitFor(cond: () => boolean, timeoutMs = 2000): Promise<void> {
  const start = Date.now();
  while (!cond()) {
    if (Date.now() - start > timeoutMs) throw new Error('waitFor 超时');
    await new Promise((r) => setTimeout(r, 5));
  }
}
