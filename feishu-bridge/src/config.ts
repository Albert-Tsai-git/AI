import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { resolve } from 'node:path';
import { parse } from 'yaml';
import type { PermissionMode } from '@anthropic-ai/claude-agent-sdk';
import type { ApprovalMode, SandboxMode } from '@openai/codex-sdk';
import { AGENT_NAMES, type AgentName } from './types.js';

export interface ProjectConfig {
  name: string;
  path: string;
  aliases: string[];
  /** 该项目默认交给谁，不填则由分析器决定。 */
  agent?: AgentName;
  description?: string;
}

export interface Config {
  feishu: {
    appId: string;
    appSecret: string;
    domain: 'feishu' | 'lark';
    /** 允许使用机器人的人（open_id）。为空时机器人只会回复对方的 open_id。 */
    allowedOpenIds: string[];
    replyInThread: boolean;
  };
  defaultAgent: AgentName;
  agents: Record<AgentName, { description: string }>;
  analyzer: {
    mode: 'rules' | 'llm';
    model?: string;
    /** LLM 置信度低于该值时，发卡片让你选择交给谁。 */
    confirmBelow: number;
    timeoutMs: number;
    keywords: Partial<Record<AgentName, string[]>>;
  };
  projects: ProjectConfig[];
  defaultProject: string;
  claude: {
    permissionMode: PermissionMode;
    model?: string;
    /** 飞书续聊时，若该会话正在终端里打开：fork = 分叉新会话继续，resume = 直接续上，reject = 拒绝。 */
    whenLive: 'fork' | 'resume' | 'reject';
    approvalTimeoutSec: number;
  };
  codex: {
    sandboxMode: SandboxMode;
    approvalPolicy: ApprovalMode;
    networkAccessEnabled: boolean;
    skipGitRepoCheck: boolean;
    model?: string;
  };
  ingest: {
    enabled: boolean;
    host: string;
    port: number;
    /** 可选：hooks 请求需携带 x-bridge-token 头。 */
    token?: string;
    /** 本地终端会话同步到飞书时发给谁（open_id），默认 allowedOpenIds[0]。 */
    mirrorToOpenId?: string;
    /** 是否转发终端里的"等待确认/输入"提醒。 */
    forwardNotifications: boolean;
  };
  ui: {
    updateIntervalMs: number;
    /** 最终结果超过该长度时，卡片里只放开头，全文以文件发送。 */
    maxCardChars: number;
  };
  storagePath: string;
}

type Raw = Record<string, any>;

/** 替换 ${VAR} / ${VAR:-默认值}。 */
export function expandEnv(value: string, env: NodeJS.ProcessEnv = process.env): string {
  return value.replace(/\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}/g, (_, name: string, def?: string) => env[name] ?? def ?? '');
}

function expandDeep(value: unknown, env: NodeJS.ProcessEnv): unknown {
  if (typeof value === 'string') return expandEnv(value, env);
  if (Array.isArray(value)) return value.map((v) => expandDeep(v, env));
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, expandDeep(v, env)]));
  }
  return value;
}

export function expandHome(p: string): string {
  if (p === '~') return homedir();
  if (p.startsWith('~/')) return resolve(homedir(), p.slice(2));
  return resolve(p);
}

function asAgent(value: unknown, field: string): AgentName {
  if (AGENT_NAMES.includes(value as AgentName)) return value as AgentName;
  throw new Error(`配置 ${field} 必须是 ${AGENT_NAMES.join(' / ')}，当前为 ${String(value)}`);
}

function parseProjects(raw: unknown): ProjectConfig[] {
  if (!raw || typeof raw !== 'object') return [];
  return Object.entries(raw as Raw).map(([name, v]) => {
    const item: Raw = typeof v === 'string' ? { path: v } : (v ?? {});
    if (!item.path) throw new Error(`项目 ${name} 缺少 path`);
    return {
      name,
      path: expandHome(String(item.path)),
      aliases: Array.isArray(item.aliases) ? item.aliases.map(String) : [],
      agent: item.agent ? asAgent(item.agent, `projects.${name}.agent`) : undefined,
      description: item.description ? String(item.description) : undefined,
    };
  });
}

export function buildConfig(raw: Raw, env: NodeJS.ProcessEnv = process.env): Config {
  const r = expandDeep(raw, env) as Raw;
  const feishu: Raw = r.feishu ?? {};
  const projects = parseProjects(r.projects);
  if (projects.length === 0) throw new Error('至少需要在 projects 里配置一个项目');
  const defaultProject = r.defaultProject ? String(r.defaultProject) : projects[0].name;
  if (!projects.some((p) => p.name === defaultProject)) {
    throw new Error(`defaultProject "${defaultProject}" 不在 projects 里`);
  }
  const analyzer: Raw = r.analyzer ?? {};
  const agents: Raw = r.agents ?? {};
  const claude: Raw = r.claude ?? {};
  const codex: Raw = r.codex ?? {};
  const ingest: Raw = r.ingest ?? {};
  const ui: Raw = r.ui ?? {};
  const allowed = Array.isArray(feishu.allowedOpenIds) ? feishu.allowedOpenIds.map(String).filter(Boolean) : [];

  return {
    feishu: {
      appId: String(feishu.appId ?? ''),
      appSecret: String(feishu.appSecret ?? ''),
      domain: feishu.domain === 'lark' ? 'lark' : 'feishu',
      allowedOpenIds: allowed,
      replyInThread: feishu.replyInThread !== false,
    },
    defaultAgent: asAgent(r.defaultAgent ?? 'claude', 'defaultAgent'),
    agents: {
      claude: { description: String(agents.claude?.description ?? 'Claude Code（Anthropic）') },
      codex: { description: String(agents.codex?.description ?? 'Codex CLI（OpenAI）') },
    },
    analyzer: {
      mode: analyzer.mode === 'rules' ? 'rules' : 'llm',
      model: analyzer.model ? String(analyzer.model) : undefined,
      confirmBelow: Number(analyzer.confirmBelow ?? 0.6),
      timeoutMs: Number(analyzer.timeoutMs ?? 30000),
      keywords: (analyzer.keywords ?? {}) as Partial<Record<AgentName, string[]>>,
    },
    projects,
    defaultProject,
    claude: {
      permissionMode: (claude.permissionMode ?? 'default') as PermissionMode,
      model: claude.model ? String(claude.model) : undefined,
      whenLive: ['fork', 'resume', 'reject'].includes(claude.whenLive) ? claude.whenLive : 'fork',
      approvalTimeoutSec: Number(claude.approvalTimeoutSec ?? 600),
    },
    codex: {
      sandboxMode: (codex.sandboxMode ?? 'workspace-write') as SandboxMode,
      approvalPolicy: (codex.approvalPolicy ?? 'never') as ApprovalMode,
      networkAccessEnabled: codex.networkAccessEnabled === true,
      skipGitRepoCheck: codex.skipGitRepoCheck === true,
      model: codex.model ? String(codex.model) : undefined,
    },
    ingest: {
      enabled: ingest.enabled !== false,
      host: String(ingest.host ?? '127.0.0.1'),
      port: Number(ingest.port ?? 7788),
      token: ingest.token ? String(ingest.token) : undefined,
      mirrorToOpenId: ingest.mirrorToOpenId ? String(ingest.mirrorToOpenId) : allowed[0],
      forwardNotifications: ingest.forwardNotifications !== false,
    },
    ui: {
      updateIntervalMs: Number(ui.updateIntervalMs ?? 1500),
      maxCardChars: Number(ui.maxCardChars ?? 6000),
    },
    storagePath: r.storagePath ? expandHome(String(r.storagePath)) : resolve('data/bridge.db'),
  };
}

export function loadConfig(path = process.env.BRIDGE_CONFIG ?? 'config.yaml'): Config {
  if (existsSync('.env')) process.loadEnvFile('.env');
  if (!existsSync(path)) {
    throw new Error(`找不到配置文件 ${path}，请先复制 config.example.yaml 为 config.yaml 并填写`);
  }
  const cfg = buildConfig(parse(readFileSync(path, 'utf8')) ?? {});
  if (!cfg.feishu.appId || !cfg.feishu.appSecret) {
    throw new Error('缺少飞书 appId / appSecret（可写在 .env 的 FEISHU_APP_ID / FEISHU_APP_SECRET）');
  }
  return cfg;
}
