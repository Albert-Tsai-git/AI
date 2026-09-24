import { Codex, type ThreadItem, type ThreadOptions } from '@openai/codex-sdk';
import type { Config } from '../config.js';
import { oneLine } from '../util/text.js';
import { childEnv, shellQuote, type AgentAdapter, type TurnRequest, type TurnResult, type TurnSink } from './types.js';

export function summarizeItem(item: ThreadItem): string | undefined {
  switch (item.type) {
    case 'command_execution':
      return `$ ${oneLine(item.command, 100)}${item.exit_code !== undefined ? `（exit ${item.exit_code}）` : ''}`;
    case 'file_change':
      return `改动文件：${item.changes.map((c) => `${c.kind} ${c.path}`).join('，')}`;
    case 'mcp_tool_call':
      return `MCP ${item.server}.${item.tool}${item.status === 'failed' ? '（失败）' : ''}`;
    case 'web_search':
      return `搜索：${oneLine(item.query, 80)}`;
    case 'error':
      return `⚠️ ${oneLine(item.message, 120)}`;
    default:
      return undefined;
  }
}

/**
 * Codex 的无头执行（codex exec）不能中途交互审批，
 * 权限由 sandboxMode / approvalPolicy / networkAccessEnabled 预先决定。
 */
export class CodexAdapter implements AgentAdapter {
  readonly name = 'codex' as const;
  readonly label = 'Codex';

  constructor(private cfg: Config['codex']) {}

  resumeHint(ref: string, cwd: string): string {
    return `cd ${shellQuote(cwd)} && codex resume ${ref}`;
  }

  async runTurn(req: TurnRequest, sink: TurnSink): Promise<TurnResult> {
    // 每轮新建 Codex 实例，保证子进程带上防回环的环境变量
    const codex = new Codex({ env: childEnv() });
    const options: ThreadOptions = {
      workingDirectory: req.cwd,
      sandboxMode: this.cfg.sandboxMode,
      approvalPolicy: this.cfg.approvalPolicy,
      networkAccessEnabled: this.cfg.networkAccessEnabled,
      skipGitRepoCheck: this.cfg.skipGitRepoCheck,
    };
    if (this.cfg.model) options.model = this.cfg.model;
    const thread = req.sessionRef ? codex.resumeThread(req.sessionRef, options) : codex.startThread(options);

    let sessionRef = req.sessionRef;
    let lastText = '';
    let lastError: string | undefined;
    let completed = false;
    const { events } = await thread.runStreamed(req.prompt, { signal: req.signal });
    for await (const ev of events) {
      if (ev.type === 'thread.started') {
        sessionRef = ev.thread_id;
        sink.sessionRef(ev.thread_id);
      } else if (ev.type === 'item.completed') {
        if (ev.item.type === 'agent_message') {
          lastText = ev.item.text;
          sink.text(ev.item.text);
        } else {
          const summary = summarizeItem(ev.item);
          if (summary) sink.step(summary);
        }
      } else if (ev.type === 'turn.completed') {
        completed = true;
      } else if (ev.type === 'turn.failed') {
        return { sessionRef, result: ev.error.message, isError: true };
      } else if (ev.type === 'error') {
        // 流里的 error 多为可恢复的提示（如断线重连），与 SDK 自带的 run() 一致：记录但不中止
        lastError = ev.message;
        sink.step(`⚠️ ${oneLine(ev.message, 120)}`);
      }
    }
    sessionRef ??= thread.id ?? undefined;
    if (!completed && !lastText && lastError) return { sessionRef, result: lastError, isError: true };
    return { sessionRef, result: lastText || '（没有输出）', isError: false };
  }
}
