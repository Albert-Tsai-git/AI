import { escapeCardMarkdown, redactSecrets, truncateHead, truncateTail } from '../util/text.js';

/** 飞书消息卡片（JSON 1.0 结构，支持 PATCH 更新）。 */
export type Card = Record<string, unknown>;

export type TurnStatus = 'queued' | 'running' | 'waiting' | 'done' | 'failed' | 'cancelled' | 'interrupted';

export interface TurnView {
  title: string;
  status: TurnStatus;
  route?: string;
  steps: string[];
  text: string;
  sessionId: string;
  resumeHint?: string;
  elapsedSec?: number;
  costUsd?: number;
  maxChars: number;
}

const STATUS_META: Record<TurnStatus, { label: string; template: string }> = {
  queued: { label: '排队中', template: 'grey' },
  running: { label: '执行中', template: 'blue' },
  waiting: { label: '等待你确认', template: 'orange' },
  done: { label: '完成', template: 'green' },
  failed: { label: '失败', template: 'red' },
  cancelled: { label: '已停止', template: 'grey' },
  interrupted: { label: '已中断', template: 'grey' },
};

function md(content: string): Record<string, unknown> {
  return { tag: 'markdown', content };
}

function note(text: string): Record<string, unknown> {
  return { tag: 'note', elements: [{ tag: 'plain_text', content: text }] };
}

function button(text: string, type: 'primary' | 'default' | 'danger', value: Record<string, unknown>) {
  return { tag: 'button', text: { tag: 'plain_text', content: text }, type, value };
}

function card(title: string, template: string, elements: unknown[]): Card {
  return {
    config: { wide_screen_mode: true, update_multi: true },
    header: { template, title: { tag: 'plain_text', content: title } },
    elements,
  };
}

function safe(text: string): string {
  return escapeCardMarkdown(redactSecrets(text));
}

export function turnCard(v: TurnView): Card {
  const meta = STATUS_META[v.status];
  const active = v.status === 'queued' || v.status === 'running' || v.status === 'waiting';
  const elements: unknown[] = [];
  if (v.route) elements.push(md(`**路由**：${safe(v.route)}`));
  if (v.steps.length > 0) {
    const shown = active ? v.steps.slice(-6) : v.steps.slice(-10);
    const hidden = v.steps.length - shown.length;
    const lines = shown.map((s) => `- ${safe(s)}`);
    if (hidden > 0) lines.unshift(`- …（前面还有 ${hidden} 步）`);
    elements.push(md(lines.join('\n')));
  }
  if (v.text) {
    if (elements.length > 0) elements.push({ tag: 'hr' });
    elements.push(md(safe(active ? truncateTail(v.text, 1500) : truncateHead(v.text, v.maxChars))));
  } else if (active) {
    elements.push(md(v.status === 'queued' ? '前面还有任务，稍后开始…' : '思考中…'));
  }
  const footer = [`会话 ${v.sessionId}`];
  if (v.elapsedSec !== undefined) footer.push(`耗时 ${v.elapsedSec}s`);
  if (v.costUsd !== undefined && v.costUsd > 0) footer.push(`约 $${v.costUsd.toFixed(4)}`);
  elements.push(note(footer.join(' · ')));
  if (v.resumeHint && !active) elements.push(note(`回到电脑继续：${v.resumeHint}`));
  if (active) elements.push({ tag: 'action', actions: [button('停止', 'danger', { a: 'stop', s: v.sessionId })] });
  return card(`${v.title} · ${meta.label}`, meta.template, elements);
}

export interface ApprovalView {
  approvalId: string;
  agentLabel: string;
  tool: string;
  detail: string;
  state: 'pending' | 'allow' | 'deny' | 'always' | 'timeout' | 'cancelled';
}

const APPROVAL_STATE: Record<Exclude<ApprovalView['state'], 'pending'>, string> = {
  allow: '✅ 已允许',
  always: '✅ 已允许（本会话不再询问该工具）',
  deny: '⛔ 已拒绝',
  timeout: '⌛ 超时未确认，已拒绝',
  cancelled: '任务已结束',
};

export function approvalCard(v: ApprovalView): Card {
  const elements: unknown[] = [md(`${v.agentLabel} 想要执行 **${safe(v.tool)}**：`), md(`\`\`\`\n${redactSecrets(truncateHead(v.detail, 1500))}\n\`\`\``)];
  if (v.state === 'pending') {
    elements.push({
      tag: 'action',
      actions: [
        button('允许', 'primary', { a: 'approve', id: v.approvalId, d: 'allow' }),
        button('拒绝', 'danger', { a: 'approve', id: v.approvalId, d: 'deny' }),
        button(`本会话始终允许 ${v.tool}`, 'default', { a: 'approve', id: v.approvalId, d: 'always' }),
      ],
    });
    elements.push(note('也可以直接在话题里回复 y / n'));
    return card(`需要确认：${v.tool}`, 'orange', elements);
  }
  elements.push(md(APPROVAL_STATE[v.state]));
  return card(`确认：${v.tool}`, v.state === 'allow' || v.state === 'always' ? 'green' : 'grey', elements);
}

export interface ChoiceView {
  choiceId: string;
  prompt: string;
  options: { agent: string; label: string; recommended: boolean }[];
  reason?: string;
  chosen?: string;
}

export function choiceCard(v: ChoiceView): Card {
  const elements: unknown[] = [md(`> ${safe(truncateHead(v.prompt, 300))}`)];
  if (v.reason) elements.push(md(`分析：${safe(v.reason)}`));
  if (v.chosen) {
    elements.push(md(`已交给 **${v.chosen}**`));
    return card('已分派', 'green', elements);
  }
  elements.push({
    tag: 'action',
    actions: v.options.map((o) =>
      button(o.recommended ? `${o.label}（推荐）` : o.label, o.recommended ? 'primary' : 'default', {
        a: 'choose',
        id: v.choiceId,
        agent: o.agent,
      }),
    ),
  });
  return card('交给谁来做？', 'wathet', elements);
}

/** 本地终端会话同步过来的 AI 回复。 */
export function mirrorReplyCard(agentLabel: string, text: string, maxChars: number): Card {
  return card(`${agentLabel} 回复`, 'indigo', [md(safe(truncateHead(text, maxChars)))]);
}

export function infoCard(title: string, content: string, template = 'blue'): Card {
  return card(title, template, [md(content)]);
}
