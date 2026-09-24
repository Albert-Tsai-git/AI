import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { describe, it } from 'node:test';
import { parse } from 'yaml';
import { buildConfig, expandEnv } from '../src/config.js';

describe('config', () => {
  it('config.example.yaml 可以直接解析', () => {
    const raw = parse(readFileSync(new URL('../config.example.yaml', import.meta.url), 'utf8'));
    const cfg = buildConfig(raw, { FEISHU_APP_ID: 'cli_x', FEISHU_APP_SECRET: 's' });
    assert.equal(cfg.feishu.appId, 'cli_x');
    assert.equal(cfg.analyzer.mode, 'llm');
    assert.equal(cfg.defaultProject, 'web');
    assert.equal(cfg.projects[0].path, `${homedir()}/code/web`);
    assert.deepEqual(cfg.projects[1].aliases, ['后端']);
    assert.equal(cfg.claude.whenLive, 'fork');
    assert.equal(cfg.codex.sandboxMode, 'workspace-write');
    assert.equal(cfg.ingest.port, 7788);
  });

  it('环境变量替换与默认值', () => {
    assert.equal(expandEnv('${A}-${B:-def}', { A: 'x' }), 'x-def');
  });

  it('校验项目配置', () => {
    assert.throws(() => buildConfig({ projects: {} }), /至少需要/);
    assert.throws(() => buildConfig({ projects: { a: '/tmp/a' }, defaultProject: 'b' }), /defaultProject/);
    assert.throws(() => buildConfig({ projects: { a: { path: '/tmp/a', agent: 'gpt' } } }), /claude \/ codex/);
  });
});
