import type { Config, ProjectConfig } from './config.js';
import { AGENT_NAMES, type AgentName } from './types.js';

export type CommandName = 'help' | 'ls' | 'stop' | 'status' | 'projects';

export interface Command {
  name: CommandName;
  args: string;
}

export interface Classification {
  agent: AgentName | null;
  project: string | null;
  confidence: number;
  reason: string;
}

export interface ClassifierContext {
  agents: { name: AgentName; description: string }[];
  projects: ProjectConfig[];
}

export type Classifier = (text: string, ctx: ClassifierContext) => Promise<Classification>;

export interface TaskAnalysis {
  /** null 表示拿不准，需要让用户选。 */
  agent: AgentName | null;
  /** 分析器推荐的助手（agent 为 null 时用于高亮推荐按钮）。 */
  suggested: AgentName;
  project: string;
  prompt: string;
  via: 'explicit' | 'project' | 'llm' | 'keyword' | 'default';
  reason: string;
}

const COMMANDS: Record<string, CommandName> = {
  help: 'help',
  帮助: 'help',
  ls: 'ls',
  list: 'ls',
  会话: 'ls',
  stop: 'stop',
  停止: 'stop',
  status: 'status',
  状态: 'status',
  projects: 'projects',
  项目: 'projects',
};

export function parseCommand(text: string): Command | null {
  const m = text.trim().match(/^\/(\S+)\s*([\s\S]*)$/);
  if (!m) return null;
  const name = COMMANDS[m[1].toLowerCase()];
  return name ? { name, args: m[2].trim() } : null;
}

const AGENT_ALIASES: Record<string, AgentName> = {
  claude: 'claude',
  cc: 'claude',
  codex: 'codex',
  cx: 'codex',
};

const ALIAS_PATTERN = Object.keys(AGENT_ALIASES).join('|');
// "/codex xxx"、"@claude: xxx"、"codex，xxx"
const PREFIX_RE = new RegExp(`^\\s*[/@]?(${ALIAS_PATTERN})(?=$|[\\s:：,，])[\\s:：,，]*`, 'i');
// "让codex帮我…"、"交给 claude 来…"、"用cc…"
const CN_PREFIX_RE = new RegExp(`^\\s*(?:请)?(?:让|用|交给|叫|找)\\s*(${ALIAS_PATTERN})\\s*(?:来|去)?[\\s:：,，]*`, 'i');

/** 识别并去掉开头的"点名"，返回点名的助手。 */
export function stripAgentPrefix(text: string): { agent?: AgentName; rest: string } {
  for (const re of [PREFIX_RE, CN_PREFIX_RE]) {
    const m = text.match(re);
    if (m) return { agent: AGENT_ALIASES[m[1].toLowerCase()], rest: text.slice(m[0].length).trim() };
  }
  return { rest: text.trim() };
}

function projectNames(p: ProjectConfig): string[] {
  return [p.name, ...p.aliases].map((n) => n.toLowerCase());
}

/**
 * 识别项目：任意位置的 "#项目名"，或（点名助手之后的）第一个词正好是项目名 / 别名。
 */
export function detectProject(
  text: string,
  projects: ProjectConfig[],
  allowLeadingWord: boolean,
): { project?: string; rest: string } {
  const hash = text.match(/(^|\s)#(\S+)/);
  if (hash) {
    const p = projects.find((pr) => projectNames(pr).includes(hash[2].toLowerCase()));
    if (p) return { project: p.name, rest: text.replace(hash[0], hash[1]).replace(/[ \t]{2,}/g, ' ').trim() };
  }
  if (allowLeadingWord) {
    const lead = text.match(/^(\S+)\s+([\s\S]+)$/);
    if (lead) {
      const p = projects.find((pr) => projectNames(pr).includes(lead[1].toLowerCase()));
      if (p) return { project: p.name, rest: lead[2].trim() };
    }
  }
  return { rest: text };
}

function keywordAgent(text: string, keywords: Config['analyzer']['keywords']): AgentName | undefined {
  const lower = text.toLowerCase();
  let best: { agent: AgentName; score: number } | undefined;
  for (const agent of AGENT_NAMES) {
    const score = (keywords[agent] ?? []).filter((k) => lower.includes(k.toLowerCase())).length;
    if (score > 0 && (!best || score > best.score)) best = { agent, score };
  }
  return best?.agent;
}

export class Analyzer {
  constructor(
    private cfg: Config,
    private classify?: Classifier,
  ) {}

  private parse(text: string) {
    const { agent: explicit, rest: afterAgent } = stripAgentPrefix(text);
    const { project, rest: prompt } = detectProject(afterAgent, this.cfg.projects, explicit !== undefined);
    return { explicit, explicitProject: project, prompt: prompt || afterAgent };
  }

  private get useLlm(): boolean {
    return this.cfg.analyzer.mode === 'llm' && this.classify !== undefined;
  }

  /**
   * 不需要调用模型就能确定的情况（点名、项目默认、规则模式），直接返回；
   * 需要模型分析时返回 null。
   */
  quickAnalyze(text: string): TaskAnalysis | null {
    const { explicit, explicitProject, prompt } = this.parse(text);
    const base = { project: explicitProject ?? this.cfg.defaultProject, prompt };
    if (explicit) {
      return { ...base, agent: explicit, suggested: explicit, via: 'explicit', reason: `消息里点名了 ${explicit}` };
    }
    const projectCfg = this.cfg.projects.find((p) => p.name === explicitProject);
    if (projectCfg?.agent) {
      return {
        ...base,
        agent: projectCfg.agent,
        suggested: projectCfg.agent,
        via: 'project',
        reason: `项目 ${projectCfg.name} 默认使用 ${projectCfg.agent}`,
      };
    }
    if (this.useLlm) return null;
    return this.byRules(text, base);
  }

  /** 分析一条"新任务"消息：交给谁、在哪个项目、真正要执行的内容。 */
  async analyze(text: string): Promise<TaskAnalysis> {
    const quick = this.quickAnalyze(text);
    if (quick) return quick;

    const { explicitProject, prompt } = this.parse(text);
    const base = { project: explicitProject ?? this.cfg.defaultProject, prompt };
    try {
      const c = await this.classify!(text, {
        agents: AGENT_NAMES.map((name) => ({ name, description: this.cfg.agents[name].description })),
        projects: this.cfg.projects,
      });
      const project = explicitProject ?? c.project ?? this.cfg.defaultProject;
      const projectAgent = this.cfg.projects.find((p) => p.name === project)?.agent;
      const suggested = c.agent ?? projectAgent ?? this.cfg.defaultAgent;
      const sure = c.agent !== null && c.confidence >= this.cfg.analyzer.confirmBelow;
      return {
        project,
        prompt,
        agent: sure ? c.agent : null,
        suggested,
        via: 'llm',
        reason: `${c.reason || '模型判断'}（置信度 ${c.confidence.toFixed(2)}）`,
      };
    } catch (err) {
      const fallback = this.byRules(text, base);
      return { ...fallback, reason: `意图分析失败（${(err as Error).message}），${fallback.reason}` };
    }
  }

  private byRules(text: string, base: { project: string; prompt: string }): TaskAnalysis {
    const kw = keywordAgent(text, this.cfg.analyzer.keywords);
    if (kw) return { ...base, agent: kw, suggested: kw, via: 'keyword', reason: `命中关键词，交给 ${kw}` };
    const agent = this.cfg.defaultAgent;
    return { ...base, agent, suggested: agent, via: 'default', reason: `默认交给 ${agent}` };
  }
}
