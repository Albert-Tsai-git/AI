import { tmpdir } from 'node:os';
import { query, type Options, type SDKMessage } from '@anthropic-ai/claude-agent-sdk';
import type { Classifier, ClassifierContext, Classification } from '../analyzer.js';
import { AGENT_NAMES, type AgentName } from '../types.js';
import { childEnv } from './types.js';

function systemPrompt(ctx: ClassifierContext): string {
  const agents = ctx.agents.map((a) => `- ${a.name}：${a.description}`).join('\n');
  const projects = ctx.projects
    .map((p) => `- ${p.name}（${p.path}${p.aliases.length ? `；别名 ${p.aliases.join('、')}` : ''}${p.description ? `；${p.description}` : ''}）`)
    .join('\n');
  return `你是一个任务分派器。用户会发来一条要交给编程助手执行的消息，你只负责判断交给谁、在哪个项目里做，不要执行任务。

可选助手：
${agents}

可选项目：
${projects}

判断规则：
- 用户明确点名某个助手时，直接选它，confidence 给 1。
- 否则根据任务性质和上面的助手说明选择最合适的一个。
- 只有消息里提到项目名、别名或能明确对应到某个项目时才填 project，否则填 null。

只输出一行 JSON，不要任何其他文字：
{"agent": "${AGENT_NAMES.join('" 或 "')}", "project": "项目名或 null", "confidence": 0 到 1 之间的小数, "reason": "一句话中文理由"}`;
}

export function parseClassification(text: string, ctx: ClassifierContext): Classification {
  const match = text.match(/\{[\s\S]*\}/);
  if (!match) throw new Error(`分类结果不是 JSON：${text.slice(0, 200)}`);
  const raw = JSON.parse(match[0]) as Record<string, unknown>;
  const agent = AGENT_NAMES.includes(raw.agent as AgentName) ? (raw.agent as AgentName) : null;
  const project = typeof raw.project === 'string' && ctx.projects.some((p) => p.name === raw.project) ? raw.project : null;
  const confidence = Math.max(0, Math.min(1, Number(raw.confidence) || 0));
  return { agent, project, confidence, reason: typeof raw.reason === 'string' ? raw.reason : '' };
}

/** 用本机 Claude Code 的登录态做意图分析，不需要额外的 API Key。 */
export function createClaudeClassifier(opts: { model?: string; timeoutMs: number }): Classifier {
  return async (text, ctx) => {
    const abortController = new AbortController();
    const timer = setTimeout(() => abortController.abort(), opts.timeoutMs);
    const options: Options = {
      systemPrompt: systemPrompt(ctx),
      tools: [],
      maxTurns: 1,
      settingSources: [],
      persistSession: false,
      cwd: tmpdir(),
      abortController,
      env: childEnv(),
    };
    if (opts.model) options.model = opts.model;
    try {
      let output = '';
      for await (const m of query({ prompt: text, options }) as AsyncIterable<SDKMessage>) {
        if (m.type === 'result') {
          if (m.subtype !== 'success' || m.is_error) throw new Error(`意图分析失败：${m.subtype}`);
          output = m.result;
        }
      }
      return parseClassification(output, ctx);
    } finally {
      clearTimeout(timer);
    }
  };
}
