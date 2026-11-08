import { query, type CanUseTool, type Options, type SDKMessage } from '@anthropic-ai/claude-agent-sdk';
import type { Config } from '../config.js';
import { oneLine } from '../util/text.js';
import { childEnv, shellQuote, type AgentAdapter, type TurnRequest, type TurnResult, type TurnSink } from './types.js';

/** 把工具调用参数压成一行，用于卡片里的步骤列表。 */
export function summarizeToolUse(name: string, input: Record<string, unknown>): string {
  const pick = (...keys: string[]) => keys.map((k) => input[k]).find((v) => typeof v === 'string') as string | undefined;
  const arg = pick('command', 'file_path', 'path', 'pattern', 'url', 'query', 'description', 'prompt');
  return arg ? `${name}: ${oneLine(arg, 100)}` : name;
}

export function permissionDetail(name: string, input: Record<string, unknown>): string {
  if (typeof input.command === 'string') return input.command;
  if (typeof input.file_path === 'string') {
    const body = typeof input.content === 'string' ? input.content : typeof input.new_string === 'string' ? input.new_string : '';
    return body ? `${input.file_path}\n\n${body}` : input.file_path;
  }
  return JSON.stringify(input, null, 2) || name;
}

export class ClaudeAdapter implements AgentAdapter {
  readonly name = 'claude' as const;
  readonly label = 'Claude';

  constructor(private cfg: Config['claude']) {}

  resumeHint(ref: string, cwd: string): string {
    return `cd ${shellQuote(cwd)} && claude --resume ${ref}`;
  }

  async runTurn(req: TurnRequest, sink: TurnSink): Promise<TurnResult> {
    const abortController = new AbortController();
    const onAbort = () => abortController.abort();
    req.signal.addEventListener('abort', onAbort, { once: true });

    const canUseTool: CanUseTool = async (toolName, input, { signal }) => {
      const decision = await sink.askPermission({ tool: toolName, detail: permissionDetail(toolName, input), signal });
      if (decision === 'deny') return { behavior: 'deny', message: '用户在飞书上拒绝了该操作' };
      return { behavior: 'allow', updatedInput: input };
    };

    const options: Options = {
      cwd: req.cwd,
      abortController,
      permissionMode: this.cfg.permissionMode,
      canUseTool,
      env: childEnv(),
    };
    if (this.cfg.model) options.model = this.cfg.model;
    if (req.sessionRef) {
      options.resume = req.sessionRef;
      if (req.fork) options.forkSession = true;
    }

    let sessionRef = req.sessionRef;
    let result: TurnResult | undefined;
    let lastText = '';
    try {
      for await (const m of query({ prompt: req.prompt, options }) as AsyncIterable<SDKMessage>) {
        if (m.type === 'system' && m.subtype === 'init') {
          sessionRef = m.session_id;
          sink.sessionRef(m.session_id);
        } else if (m.type === 'assistant' && m.parent_tool_use_id === null) {
          for (const block of m.message.content) {
            if (block.type === 'text' && block.text.trim()) {
              lastText = block.text;
              sink.text(block.text);
            } else if (block.type === 'tool_use') {
              sink.step(summarizeToolUse(block.name, (block.input ?? {}) as Record<string, unknown>));
            }
          }
        } else if (m.type === 'result') {
          if (m.session_id) sessionRef = m.session_id;
          result =
            m.subtype === 'success'
              ? { sessionRef, result: m.result || lastText, isError: m.is_error, costUsd: m.total_cost_usd }
              : { sessionRef, result: m.errors.join('\n') || `执行中止：${m.subtype}`, isError: true, costUsd: m.total_cost_usd };
        }
      }
    } finally {
      req.signal.removeEventListener('abort', onAbort);
    }
    return result ?? { sessionRef, result: lastText || '（没有输出）', isError: req.signal.aborted };
  }
}
