import { basename } from 'node:path';
import type { AgentAdapter, PermissionDecision, PermissionRequest, TurnResult, TurnSink } from './agents/types.js';
import { ORIGIN_BRIDGE } from './agents/types.js';
import { Analyzer, parseCommand, stripAgentPrefix, type Command, type TaskAnalysis } from './analyzer.js';
import type { Config } from './config.js';
import type { FeishuApi, OutMessage } from './feishu/api.js';
import {
  approvalCard,
  choiceCard,
  infoCard,
  mirrorReplyCard,
  turnCard,
  type ApprovalView,
  type Card,
  type TurnStatus,
  type TurnView,
} from './feishu/cards.js';
import { silentLogger, type Logger } from './log.js';
import type { SessionRow, Store } from './store.js';
import { AGENT_NAMES, type AgentName, type CardAction, type CardActionResult, type InboundMessage, type LocalEvent } from './types.js';
import { KeyedQueue } from './util/queue.js';
import { redactSecrets, shortId, truncateHead } from './util/text.js';

export interface BridgeDeps {
  config: Config;
  store: Store;
  feishu: FeishuApi;
  adapters: Record<AgentName, AgentAdapter>;
  analyzer: Analyzer;
  log?: Logger;
}

interface RunningTurn {
  turnId: string;
  abort: AbortController;
}

interface PendingApproval {
  id: string;
  sessionId: string;
  resolve(decision: PermissionDecision | 'timeout' | 'cancelled'): void;
}

interface PendingChoice {
  msg: InboundMessage;
  analysis: TaskAnalysis;
  cardMessageId: string;
  createdAt: number;
}

const CHOICE_TTL_MS = 30 * 60 * 1000;

export const HELP_TEXT = `怎么用：
• 直接发消息 = 新任务，自动分析交给 Claude 还是 Codex
• 在话题里回复 = 接着这个会话继续
• 点名：/claude …、/codex …、cc …、cx …、让codex…
• 指定项目：#项目名 …，或 /codex 项目名 …
• 审批：点卡片按钮，或在话题里回复 y / n
• 命令：/ls 最近会话 · /stop 停止 · /status 状态 · /projects 项目 · /help 帮助`;

export function parseApprovalReply(text: string): PermissionDecision | undefined {
  const t = text.trim().toLowerCase();
  if (['y', 'yes', 'ok', '好', '好的', '允许', '同意', '可以', '确认', '执行'].includes(t)) return 'allow';
  if (['n', 'no', '不', '不行', '拒绝', '不允许', '取消'].includes(t)) return 'deny';
  if (['always', '始终允许', '总是允许', '一直允许'].includes(t)) return 'always';
  return undefined;
}

/** 限速更新卡片：执行过程中最多每 intervalMs 更新一次，最后一次必定送达。 */
class CardUpdater {
  private latest?: Card;
  private timer?: NodeJS.Timeout;
  private inflight: Promise<void> = Promise.resolve();
  private lastSent = 0;

  constructor(
    private feishu: FeishuApi,
    private messageId: string,
    private intervalMs: number,
    private log: Logger,
  ) {}

  set(card: Card): void {
    this.latest = card;
    if (this.timer) return;
    const wait = Math.max(0, this.lastSent + this.intervalMs - Date.now());
    this.timer = setTimeout(() => this.flush(), wait);
  }

  private flush(): void {
    this.timer = undefined;
    const card = this.latest;
    this.latest = undefined;
    if (!card) return;
    this.lastSent = Date.now();
    this.inflight = this.inflight
      .then(() => this.feishu.updateCard(this.messageId, card))
      .catch((err) => this.log.warn('更新卡片失败', err));
  }

  async final(card: Card): Promise<void> {
    clearTimeout(this.timer);
    this.timer = undefined;
    this.latest = undefined;
    this.inflight = this.inflight
      .then(() => this.feishu.updateCard(this.messageId, card))
      .catch((err) => this.log.warn('更新卡片失败', err));
    await this.inflight;
  }
}

function refKey(agent: AgentName, ref: string): string {
  return `${agent}:${ref}`;
}

function ago(ts: number): string {
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 60) return `${s} 秒前`;
  if (s < 3600) return `${Math.round(s / 60)} 分钟前`;
  if (s < 86400) return `${Math.round(s / 3600)} 小时前`;
  return `${Math.round(s / 86400)} 天前`;
}

export class Bridge {
  private readonly cfg: Config;
  private readonly store: Store;
  private readonly feishu: FeishuApi;
  private readonly adapters: Record<AgentName, AgentAdapter>;
  private readonly analyzer: Analyzer;
  private readonly log: Logger;

  /** 同一会话的任务串行执行。 */
  private readonly turnQueue = new KeyedQueue();
  /** 本地会话同步到飞书时保证消息顺序。 */
  private readonly mirrorQueue = new KeyedQueue();
  private readonly running = new Map<string, RunningTurn>();
  /** 桥接服务自己驱动中的 AI 会话，这些会话的本地上报一律忽略（防回环兜底）。 */
  private readonly bridgeRefs = new Set<string>();
  private readonly approvals = new Map<string, PendingApproval>();
  private readonly choices = new Map<string, PendingChoice>();
  private readonly alwaysAllow = new Map<string, Set<string>>();

  constructor(deps: BridgeDeps) {
    this.cfg = deps.config;
    this.store = deps.store;
    this.feishu = deps.feishu;
    this.adapters = deps.adapters;
    this.analyzer = deps.analyzer;
    this.log = deps.log ?? silentLogger;
  }

  /** 等待所有排队中的任务和同步消息完成。 */
  async idle(): Promise<void> {
    await this.turnQueue.idle();
    await this.mirrorQueue.idle();
  }

  /** 停止所有执行中的任务（退出时调用）。 */
  abortAll(): void {
    for (const r of this.running.values()) r.abort.abort();
  }

  // ───────────────────────── 飞书 → AI ─────────────────────────

  async onMessage(msg: InboundMessage): Promise<void> {
    if (!this.store.markProcessed(`msg:${msg.messageId}`)) return;

    const allowed = this.cfg.feishu.allowedOpenIds;
    if (allowed.length === 0) {
      await this.reply(msg.messageId, {
        type: 'text',
        text: `你的 open_id 是：${msg.senderOpenId}\n把它填到 config.yaml 的 feishu.allowedOpenIds 里，重启服务后即可使用。`,
      });
      return;
    }
    if (!allowed.includes(msg.senderOpenId)) {
      this.log.warn(`忽略非白名单用户的消息：${msg.senderOpenId}`);
      return;
    }

    const session = this.store.findSessionByMessage(msg.rootId) ?? this.store.findSessionByMessage(msg.parentId);
    const inThread = session !== undefined;
    const text = msg.text.trim();
    if (!text) {
      await this.reply(msg.messageId, { type: 'text', text: '暂时只支持文字消息。' }, inThread);
      return;
    }

    if (session) {
      const pending = [...this.approvals.values()].reverse().find((a) => a.sessionId === session.id);
      const decision = pending && parseApprovalReply(text);
      if (pending && decision) {
        this.store.linkMessage(msg.messageId, session.id);
        pending.resolve(decision);
        return;
      }
    }

    const command = parseCommand(text);
    if (command) {
      await this.handleCommand(command, msg, session);
      return;
    }

    if (session) {
      const { agent, rest } = stripAgentPrefix(text);
      if (agent && agent !== session.agent) {
        await this.reply(
          msg.messageId,
          { type: 'text', text: `这个话题绑定的是 ${this.adapters[session.agent].label} 会话。要交给 ${this.adapters[agent].label}，请发一条新消息（不要在话题里回复）。` },
          true,
        );
        return;
      }
      this.store.linkMessage(msg.messageId, session.id);
      await this.enqueueTurn(session, rest || text, msg.messageId);
      return;
    }

    await this.handleNewTask(msg, text);
  }

  private async handleNewTask(msg: InboundMessage, text: string): Promise<void> {
    let analysis = this.analyzer.quickAnalyze(text);
    let cardId: string | undefined;
    if (!analysis) {
      // 需要调用模型分析，先给个反馈，之后这张卡片会变成任务卡片
      cardId = await this.reply(msg.messageId, { type: 'card', card: infoCard('分析中…', '正在判断交给谁来做', 'grey') });
      analysis = await this.analyzer.analyze(text);
    }
    if (!analysis.agent) {
      await this.askChoice(msg, analysis, cardId);
      return;
    }
    await this.startSession(msg, analysis, analysis.agent, cardId);
  }

  private async startSession(msg: InboundMessage, analysis: TaskAnalysis, agent: AgentName, cardId?: string): Promise<void> {
    const project = this.cfg.projects.find((p) => p.name === analysis.project) ?? this.cfg.projects[0];
    const session = this.store.createSession({
      agent,
      project: project.name,
      cwd: project.path,
      origin: 'feishu',
      chatId: msg.chatId,
      rootMessageId: msg.messageId,
    });
    const route = `${this.adapters[agent].label} · ${project.name}（${analysis.reason}）`;
    await this.enqueueTurn(session, analysis.prompt, msg.messageId, { route, cardId });
  }

  private async askChoice(msg: InboundMessage, analysis: TaskAnalysis, cardId?: string): Promise<void> {
    const choiceId = shortId('c');
    const card = choiceCard({
      choiceId,
      prompt: analysis.prompt,
      reason: analysis.reason,
      options: AGENT_NAMES.map((a) => ({ agent: a, label: this.adapters[a].label, recommended: a === analysis.suggested })),
    });
    const id = cardId ?? (await this.reply(msg.messageId, { type: 'card', card }));
    if (cardId) await this.feishu.updateCard(cardId, card);
    this.choices.set(choiceId, { msg, analysis, cardMessageId: id, createdAt: Date.now() });
  }

  private async enqueueTurn(
    session: SessionRow,
    prompt: string,
    replyTo: string,
    opts: { route?: string; cardId?: string } = {},
  ): Promise<void> {
    const adapter = this.adapters[session.agent];
    const view: TurnView = {
      title: `${adapter.label} · ${session.project}`,
      status: this.turnQueue.size(session.id) > 0 ? 'queued' : 'running',
      route: opts.route,
      steps: [],
      text: '',
      sessionId: session.id,
      maxChars: this.cfg.ui.maxCardChars,
    };
    let cardId = opts.cardId;
    if (cardId) await this.feishu.updateCard(cardId, turnCard(view));
    else cardId = await this.reply(replyTo, { type: 'card', card: turnCard(view) }, true);
    this.store.linkMessage(cardId, session.id);

    const card = cardId;
    void this.turnQueue
      .run(session.id, () => this.executeTurn(session.id, prompt, replyTo, card, view))
      .catch((err) => this.log.error(`会话 ${session.id} 执行异常`, err));
  }

  private async executeTurn(sessionId: string, prompt: string, replyTo: string, cardId: string, view: TurnView): Promise<void> {
    const session = this.store.getSession(sessionId)!;
    const adapter = this.adapters[session.agent];
    const turn = this.store.createTurn(session.id, prompt);
    this.store.updateTurn(turn.id, { cardMessageId: cardId });
    const updater = new CardUpdater(this.feishu, cardId, this.cfg.ui.updateIntervalMs, this.log);
    const started = Date.now();

    let fork = false;
    if (session.agent === 'claude' && session.agentRef && session.live) {
      if (this.cfg.claude.whenLive === 'reject') {
        view.status = 'failed';
        view.text = `这个会话正在电脑终端里打开着，为避免冲突没有执行。请先在终端里退出，或者直接在终端继续：\n${adapter.resumeHint(session.agentRef, session.cwd)}`;
        await updater.final(turnCard(view));
        this.store.updateTurn(turn.id, { status: 'failed', result: view.text });
        return;
      }
      if (this.cfg.claude.whenLive === 'fork') {
        fork = true;
        view.route = [view.route, '该会话正在终端里打开着，本次从它分叉出新会话继续'].filter(Boolean).join('；');
      }
    }

    const abort = new AbortController();
    this.running.set(session.id, { turnId: turn.id, abort });
    const refs: string[] = [];
    const trackRef = (ref: string) => {
      const key = refKey(session.agent, ref);
      this.bridgeRefs.add(key);
      refs.push(key);
    };
    if (session.agentRef) trackRef(session.agentRef);
    let currentRef = session.agentRef;
    const saveRef = (ref: string | undefined) => {
      if (!ref || ref === currentRef) return;
      trackRef(ref);
      currentRef = ref;
      this.store.updateSession(session.id, fork ? { agentRef: ref, live: false } : { agentRef: ref });
    };

    view.status = 'running';
    updater.set(turnCard(view));
    const sink: TurnSink = {
      sessionRef: saveRef,
      text: (t) => {
        view.text = t;
        updater.set(turnCard(view));
      },
      step: (s) => {
        view.steps.push(s);
        updater.set(turnCard(view));
      },
      askPermission: (req) => this.askPermission(session, adapter, req, replyTo, view, updater),
    };

    let status: TurnStatus;
    let result: TurnResult | undefined;
    try {
      result = await adapter.runTurn(
        { sessionRef: session.agentRef ?? undefined, fork, cwd: session.cwd, prompt, signal: abort.signal },
        sink,
      );
      saveRef(result.sessionRef);
      status = abort.signal.aborted ? 'cancelled' : result.isError ? 'failed' : 'done';
      view.text = result.result;
      view.costUsd = result.costUsd;
    } catch (err) {
      status = abort.signal.aborted ? 'cancelled' : 'failed';
      if (status === 'failed') view.text = `出错了：${(err as Error).message}`;
      this.log.warn(`会话 ${session.id} 执行失败`, err);
    } finally {
      this.running.delete(session.id);
      for (const a of [...this.approvals.values()]) if (a.sessionId === session.id) a.resolve('cancelled');
      // hooks 可能在执行结束后稍晚才到，延迟一会儿再解除防回环标记
      setTimeout(() => refs.forEach((k) => this.bridgeRefs.delete(k)), 10_000).unref();
    }

    view.status = status;
    view.elapsedSec = Math.round((Date.now() - started) / 1000);
    if (currentRef) view.resumeHint = adapter.resumeHint(currentRef, session.cwd);
    await updater.final(turnCard(view));
    this.store.updateTurn(turn.id, { status, result: view.text });
    if (status === 'done' && view.text.length > this.cfg.ui.maxCardChars) {
      await this.sendFullText(replyTo, `${adapter.label}-${turn.id}.md`, view.text);
    }
  }

  private async askPermission(
    session: SessionRow,
    adapter: AgentAdapter,
    req: PermissionRequest,
    replyTo: string,
    view: TurnView,
    updater: CardUpdater,
  ): Promise<PermissionDecision> {
    if (this.alwaysAllow.get(session.id)?.has(req.tool)) return 'allow';
    if (req.signal.aborted) return 'deny';

    const id = shortId('a');
    const base: ApprovalView = { approvalId: id, agentLabel: adapter.label, tool: req.tool, detail: req.detail, state: 'pending' };
    let resolve!: PendingApproval['resolve'];
    const decided = new Promise<PermissionDecision | 'timeout' | 'cancelled'>((r) => (resolve = r));
    this.approvals.set(id, { id, sessionId: session.id, resolve });
    const timer = setTimeout(() => resolve('timeout'), this.cfg.claude.approvalTimeoutSec * 1000);
    const onAbort = () => resolve('cancelled');
    req.signal.addEventListener('abort', onAbort, { once: true });

    view.status = 'waiting';
    updater.set(turnCard(view));
    let cardId: string | undefined;
    try {
      cardId = await this.reply(replyTo, { type: 'card', card: approvalCard(base) }, true);
      this.store.linkMessage(cardId, session.id);
    } catch (err) {
      this.log.error('发送审批卡片失败，按拒绝处理', err);
      resolve('deny');
    }

    const decision = await decided;
    clearTimeout(timer);
    req.signal.removeEventListener('abort', onAbort);
    this.approvals.delete(id);
    if (decision === 'always') {
      const set = this.alwaysAllow.get(session.id) ?? new Set<string>();
      set.add(req.tool);
      this.alwaysAllow.set(session.id, set);
    }
    if (cardId) {
      await this.feishu.updateCard(cardId, approvalCard({ ...base, state: decision })).catch((err) => this.log.warn('更新审批卡片失败', err));
    }
    view.status = 'running';
    view.steps.push(`${decision === 'allow' || decision === 'always' ? '✅ 允许' : '⛔ 未允许'} ${req.tool}`);
    updater.set(turnCard(view));
    return decision === 'allow' || decision === 'always' ? decision : 'deny';
  }

  async onCardAction(action: CardAction): Promise<CardActionResult> {
    if (!this.cfg.feishu.allowedOpenIds.includes(action.operatorOpenId)) {
      return { toast: { type: 'error', content: '你没有权限操作' } };
    }
    const v = action.value;
    switch (v.a) {
      case 'approve': {
        const pending = this.approvals.get(String(v.id));
        if (!pending) return { toast: { type: 'warning', content: '这个请求已经失效了' } };
        const d = v.d === 'deny' ? 'deny' : v.d === 'always' ? 'always' : 'allow';
        pending.resolve(d);
        return { toast: { type: 'success', content: d === 'deny' ? '已拒绝' : '已允许' } };
      }
      case 'stop': {
        const stopped = this.stopSession(String(v.s));
        return { toast: { type: stopped ? 'success' : 'info', content: stopped ? '正在停止…' : '任务已经结束了' } };
      }
      case 'choose': {
        const choice = this.choices.get(String(v.id));
        const agent = AGENT_NAMES.find((a) => a === v.agent);
        if (!choice || !agent || Date.now() - choice.createdAt > CHOICE_TTL_MS) {
          return { toast: { type: 'warning', content: '已过期，请重新发送消息' } };
        }
        this.choices.delete(String(v.id));
        const analysis = { ...choice.analysis, reason: `你选择了 ${this.adapters[agent].label}` };
        void this.startSession(choice.msg, analysis, agent, choice.cardMessageId).catch((err) =>
          this.log.error('分派任务失败', err),
        );
        return { toast: { type: 'success', content: `已交给 ${this.adapters[agent].label}` } };
      }
      default:
        return { toast: { type: 'info', content: '未知操作' } };
    }
  }

  private stopSession(sessionId: string): boolean {
    const r = this.running.get(sessionId);
    if (!r) return false;
    r.abort.abort();
    return true;
  }

  private async handleCommand(cmd: Command, msg: InboundMessage, session: SessionRow | undefined): Promise<void> {
    const inThread = session !== undefined;
    const send = (title: string, content: string) =>
      this.reply(msg.messageId, { type: 'card', card: infoCard(title, content) }, inThread);

    switch (cmd.name) {
      case 'help':
        await send('帮助', HELP_TEXT);
        return;
      case 'projects':
        await send(
          '项目',
          this.cfg.projects
            .map((p) => {
              const extra = [p.aliases.length ? `别名 ${p.aliases.join('、')}` : '', p.agent ? `默认 ${p.agent}` : '']
                .filter(Boolean)
                .join('，');
              return `- **${p.name}**${p.name === this.cfg.defaultProject ? '（默认）' : ''}：${p.path}${extra ? `（${extra}）` : ''}`;
            })
            .join('\n'),
        );
        return;
      case 'ls': {
        const rows = this.store.listSessions(10);
        await send(
          '最近会话',
          rows.length === 0
            ? '还没有会话'
            : rows
                .map(
                  (s) =>
                    `- \`${s.id}\` ${this.adapters[s.agent].label} · ${s.project} · ${s.origin === 'local' ? '本地' : '飞书'}${
                      this.running.has(s.id) ? ' · **执行中**' : ''
                    } · ${ago(s.updatedAt)}`,
                )
                .join('\n'),
        );
        return;
      }
      case 'status': {
        const running = [...this.running.keys()].map((id) => this.store.getSession(id)).filter(Boolean) as SessionRow[];
        await send(
          '状态',
          [
            `执行中：${running.length === 0 ? '无' : running.map((s) => `${s.id}（${this.adapters[s.agent].label} · ${s.project}）`).join('、')}`,
            `意图分析：${this.cfg.analyzer.mode === 'llm' ? '模型分析' : '规则'} · 默认助手 ${this.cfg.defaultAgent}`,
            `本地同步：${this.cfg.ingest.enabled ? `http://${this.cfg.ingest.host}:${this.cfg.ingest.port}` : '未开启'}`,
          ].join('\n'),
        );
        return;
      }
      case 'stop': {
        const targets = session ? [session.id] : [...this.running.keys()];
        const stopped = targets.filter((id) => this.stopSession(id));
        await send('停止', stopped.length > 0 ? `已停止：${stopped.join('、')}` : '没有正在执行的任务');
        return;
      }
    }
  }

  // ───────────────────────── 本地终端 → 飞书 ─────────────────────────

  async onLocalEvent(ev: LocalEvent): Promise<void> {
    if (ev.origin === ORIGIN_BRIDGE || this.bridgeRefs.has(refKey(ev.agent, ev.ref))) return;
    await this.mirrorQueue.run(refKey(ev.agent, ev.ref), () => this.handleLocalEvent(ev));
  }

  private async handleLocalEvent(ev: LocalEvent): Promise<void> {
    let session = this.store.findSessionByRef(ev.agent, ev.ref);
    switch (ev.kind) {
      case 'session_start':
        if (session) this.store.updateSession(session.id, { live: true });
        return;
      case 'session_end':
        if (session) this.store.updateSession(session.id, { live: false });
        return;
      case 'notify':
        if (session?.rootMessageId && ev.text && this.cfg.ingest.forwardNotifications) {
          await this.postToThread(session, { type: 'text', text: `⏳ ${ev.text}` });
        }
        return;
      case 'prompt':
      case 'reply': {
        if (!ev.text?.trim()) return;
        session ??= await this.createMirrorSession(ev);
        if (!session?.rootMessageId) return;
        if (ev.agent === 'claude' && !session.live) this.store.updateSession(session.id, { live: true });
        if (ev.kind === 'prompt') {
          await this.postToThread(session, { type: 'text', text: `👤 ${redactSecrets(truncateHead(ev.text, 3000))}` });
        } else {
          const label = this.adapters[ev.agent].label;
          await this.postToThread(session, { type: 'card', card: mirrorReplyCard(label, ev.text, this.cfg.ui.maxCardChars) });
          if (ev.text.length > this.cfg.ui.maxCardChars) {
            await this.sendFullText(session.rootMessageId, `${label}-${Date.now()}.md`, ev.text);
          }
        }
        return;
      }
    }
  }

  private async createMirrorSession(ev: LocalEvent): Promise<SessionRow | undefined> {
    const target = this.cfg.ingest.mirrorToOpenId;
    if (!target) {
      this.log.warn('没有配置 feishu.allowedOpenIds / ingest.mirrorToOpenId，无法同步本地会话');
      return undefined;
    }
    const project =
      this.cfg.projects
        .filter((p) => ev.cwd === p.path || ev.cwd.startsWith(`${p.path}/`))
        .sort((a, b) => b.path.length - a.path.length)[0]?.name ?? (basename(ev.cwd) || '本地');
    const label = this.adapters[ev.agent].label;
    const rootId = await this.feishu.sendToUser(target, {
      type: 'text',
      text: `🖥 本地 ${label} 会话 · ${project}\n📁 ${ev.cwd}\n在这个话题里回复，就能在飞书上接着这个会话继续。`,
    });
    return this.store.createSession({
      agent: ev.agent,
      project,
      cwd: ev.cwd,
      origin: 'local',
      agentRef: ev.ref,
      rootMessageId: rootId,
      live: ev.agent === 'claude',
    });
  }

  private async postToThread(session: SessionRow, msg: OutMessage): Promise<void> {
    const id = await this.feishu.reply(session.rootMessageId!, msg, true);
    this.store.linkMessage(id, session.id);
  }

  // ───────────────────────── 辅助 ─────────────────────────

  /** 服务重启后，把上次中断的任务卡片标记出来。 */
  async recoverInterrupted(): Promise<void> {
    for (const t of this.store.interruptRunningTurns()) {
      if (!t.cardMessageId) continue;
      await this.feishu
        .updateCard(t.cardMessageId, infoCard('任务已中断', '桥接服务重启，这次执行被中断了。在话题里回复可以接着这个会话继续。', 'grey'))
        .catch((err) => this.log.warn('更新中断卡片失败', err));
    }
  }

  private reply(messageId: string, msg: OutMessage, inThread = false): Promise<string> {
    return this.feishu.reply(messageId, msg, inThread && this.cfg.feishu.replyInThread);
  }

  /** 长文本：优先作为文件发送，失败则分段发文本。 */
  private async sendFullText(replyTo: string, fileName: string, text: string): Promise<void> {
    const content = redactSecrets(text);
    try {
      const fileKey = await this.feishu.uploadFile(fileName, Buffer.from(content, 'utf8'));
      await this.reply(replyTo, { type: 'file', fileKey }, true);
    } catch (err) {
      this.log.warn('上传完整结果失败，改为分段发送', err);
      const chunks = content.match(/[\s\S]{1,3500}/g) ?? [];
      for (const [i, chunk] of chunks.slice(0, 5).entries()) {
        await this.reply(replyTo, { type: 'text', text: `（${i + 1}/${chunks.length}）\n${chunk}` }, true);
      }
    }
  }
}
