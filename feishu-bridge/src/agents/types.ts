import type { AgentName } from '../types.js';

export type PermissionDecision = 'allow' | 'deny' | 'always';

export interface PermissionRequest {
  tool: string;
  /** 给人看的参数预览（命令、文件路径等）。 */
  detail: string;
  signal: AbortSignal;
}

/** 执行过程中的事件回调，由桥接层实现（更新飞书卡片、发审批卡片）。 */
export interface TurnSink {
  /** 拿到（或更新了）AI 侧的会话 id。 */
  sessionRef(ref: string): void;
  /** 一段完整的助手文本。 */
  text(text: string): void;
  /** 一个执行步骤（工具调用、命令、文件改动）的一行摘要。 */
  step(summary: string): void;
  askPermission(req: PermissionRequest): Promise<PermissionDecision>;
}

export interface TurnRequest {
  /** 为空表示新会话。 */
  sessionRef?: string;
  /** 续聊时分叉出新会话，不影响原会话（原会话正在终端里打开时使用）。 */
  fork?: boolean;
  cwd: string;
  prompt: string;
  signal: AbortSignal;
}

export interface TurnResult {
  sessionRef?: string;
  result: string;
  isError: boolean;
  costUsd?: number;
}

export interface AgentAdapter {
  name: AgentName;
  label: string;
  runTurn(req: TurnRequest, sink: TurnSink): Promise<TurnResult>;
  /** 在终端里接着这个会话的命令。 */
  resumeHint(ref: string, cwd: string): string;
}

/** 注入给子进程的环境变量：hooks / notify 据此识别"这是桥接服务自己发起的执行"，避免回环。 */
export const ORIGIN_ENV = 'AI_BRIDGE_ORIGIN';
export const ORIGIN_BRIDGE = 'bridge';

/**
 * 标识"当前所在 Claude Code 会话"的变量。如果桥接服务是在某个 Claude Code 终端里启动的，
 * 这些变量会被继承，导致桥接服务开出的所有会话共用同一个 session id，必须去掉。
 */
const PARENT_SESSION_VARS = ['CLAUDECODE', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_CODE_REMOTE_SESSION_ID', 'CLAUDE_CODE_CHILD_SESSION', 'CLAUDE_PID'];

export function childEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (v !== undefined && !PARENT_SESSION_VARS.includes(k)) env[k] = v;
  }
  env[ORIGIN_ENV] = ORIGIN_BRIDGE;
  return env;
}

export function shellQuote(s: string): string {
  return /^[\w@%+=:,./~-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`;
}
