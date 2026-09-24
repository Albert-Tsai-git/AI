import { createClaudeClassifier } from './agents/classifier.js';
import { ClaudeAdapter } from './agents/claude.js';
import { CodexAdapter } from './agents/codex.js';
import { Analyzer } from './analyzer.js';
import { Bridge } from './bridge.js';
import { loadConfig } from './config.js';
import { LarkFeishuApi } from './feishu/api.js';
import { startFeishuEvents } from './feishu/events.js';
import { startIngestServer } from './ingest.js';
import { consoleLogger as log } from './log.js';
import { Store } from './store.js';

async function main(): Promise<void> {
  const cfg = loadConfig();
  const store = new Store(cfg.storagePath);
  const classifier =
    cfg.analyzer.mode === 'llm' ? createClaudeClassifier({ model: cfg.analyzer.model, timeoutMs: cfg.analyzer.timeoutMs }) : undefined;
  const bridge = new Bridge({
    config: cfg,
    store,
    feishu: new LarkFeishuApi(cfg),
    adapters: { claude: new ClaudeAdapter(cfg.claude), codex: new CodexAdapter(cfg.codex) },
    analyzer: new Analyzer(cfg, classifier),
    log,
  });

  await bridge.recoverInterrupted();
  const ingest = cfg.ingest.enabled ? await startIngestServer(cfg.ingest, (ev) => bridge.onLocalEvent(ev), log) : undefined;
  if (ingest) log.info(`本地同步入口：http://${cfg.ingest.host}:${cfg.ingest.port}/hooks/{claude,codex}`);
  const ws = await startFeishuEvents(cfg, bridge, log);
  if (cfg.feishu.allowedOpenIds.length === 0) {
    log.warn('feishu.allowedOpenIds 为空：先给机器人发一条消息获取你的 open_id，填进配置后重启');
  }
  log.info(`已启动：${cfg.projects.length} 个项目，默认 ${cfg.defaultAgent}，意图分析 ${cfg.analyzer.mode}`);

  const prune = setInterval(() => store.pruneProcessed(7 * 24 * 3600 * 1000), 3600 * 1000);
  prune.unref();

  let stopping = false;
  const shutdown = async () => {
    if (stopping) process.exit(1);
    stopping = true;
    log.info('正在退出…');
    ws.close({ force: true });
    ingest?.close();
    bridge.abortAll();
    await Promise.race([bridge.idle(), new Promise((r) => setTimeout(r, 5000))]);
    store.close();
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

main().catch((err) => {
  log.error('启动失败', err);
  process.exit(1);
});
