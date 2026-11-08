import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { parseClassification } from '../src/agents/classifier.js';
import { Analyzer, detectProject, parseCommand, stripAgentPrefix } from '../src/analyzer.js';
import { testConfig } from './helpers.js';

describe('stripAgentPrefix', () => {
  const cases: [string, string | undefined, string][] = [
    ['/codex 写单测', 'codex', '写单测'],
    ['@claude: 看看这个报错', 'claude', '看看这个报错'],
    ['Codex，帮我改一下', 'codex', '帮我改一下'],
    ['cc 重构登录模块', 'claude', '重构登录模块'],
    ['让codex帮我写单测', 'codex', '帮我写单测'],
    ['请交给 Claude 来 review 一下', 'claude', 'review 一下'],
    ['codexify 这个名字', undefined, 'codexify 这个名字'],
    ['帮我看看 claude 的配置', undefined, '帮我看看 claude 的配置'],
  ];
  for (const [input, agent, rest] of cases) {
    it(input, () => assert.deepEqual(stripAgentPrefix(input), agent ? { agent, rest } : { rest }));
  }
});

describe('detectProject', () => {
  const { projects } = testConfig();
  it('#项目名 任意位置', () => assert.deepEqual(detectProject('修一下 #api 的报错', projects, false), { project: 'api', rest: '修一下 的报错' }));
  it('#别名', () => assert.equal(detectProject('#前端 改按钮颜色', projects, false).project, 'web'));
  it('点名之后的第一个词是项目名', () => assert.deepEqual(detectProject('api 写单测', projects, true), { project: 'api', rest: '写单测' }));
  it('没点名时不把第一个词当项目', () => assert.equal(detectProject('api 写单测', projects, false).project, undefined));
});

describe('parseCommand', () => {
  it('识别命令', () => assert.deepEqual(parseCommand('/ls'), { name: 'ls', args: '' }));
  it('中文命令', () => assert.deepEqual(parseCommand('/停止'), { name: 'stop', args: '' }));
  it('点名不是命令', () => assert.equal(parseCommand('/codex 写单测'), null));
});

describe('Analyzer', () => {
  it('规则模式：点名优先', async () => {
    const a = await new Analyzer(testConfig()).analyze('/claude api 看日志');
    assert.equal(a.agent, 'claude');
    assert.equal(a.project, 'api');
    assert.equal(a.prompt, '看日志');
    assert.equal(a.via, 'explicit');
  });

  it('规则模式：项目默认助手', async () => {
    const a = await new Analyzer(testConfig()).analyze('#api 看日志');
    assert.equal(a.agent, 'codex');
    assert.equal(a.via, 'project');
  });

  it('规则模式：关键词，其次默认', async () => {
    const analyzer = new Analyzer(testConfig());
    assert.equal((await analyzer.analyze('给登录模块补单测')).agent, 'codex');
    const d = await analyzer.analyze('解释一下这段代码');
    assert.equal(d.agent, 'claude');
    assert.equal(d.via, 'default');
    assert.equal(d.project, 'web');
  });

  it('模型模式：点名时不调用模型', async () => {
    let called = false;
    const analyzer = new Analyzer(testConfig({ analyzer: { mode: 'llm' } }), async () => {
      called = true;
      throw new Error('should not be called');
    });
    assert.equal(analyzer.quickAnalyze('/codex 写单测')?.agent, 'codex');
    assert.equal(analyzer.quickAnalyze('写单测'), null);
    assert.equal(called, false);
  });

  it('模型模式：采用模型结果', async () => {
    const analyzer = new Analyzer(testConfig({ analyzer: { mode: 'llm' } }), async () => ({
      agent: 'codex',
      project: 'web',
      confidence: 0.9,
      reason: '生成测试',
    }));
    const a = await analyzer.analyze('给按钮组件写测试');
    assert.equal(a.agent, 'codex');
    assert.equal(a.via, 'llm');
    assert.match(a.reason, /生成测试/);
  });

  it('模型模式：置信度低时需要用户选择', async () => {
    const analyzer = new Analyzer(testConfig({ analyzer: { mode: 'llm', confirmBelow: 0.7 } }), async () => ({
      agent: 'codex',
      project: null,
      confidence: 0.4,
      reason: '不确定',
    }));
    const a = await analyzer.analyze('看看这个');
    assert.equal(a.agent, null);
    assert.equal(a.suggested, 'codex');
  });

  it('模型模式：分析失败时回退到规则', async () => {
    const analyzer = new Analyzer(testConfig({ analyzer: { mode: 'llm', keywords: { codex: ['单测'] } } }), async () => {
      throw new Error('boom');
    });
    const a = await analyzer.analyze('补单测');
    assert.equal(a.agent, 'codex');
    assert.match(a.reason, /意图分析失败/);
  });
});

describe('parseClassification', () => {
  const ctx = { agents: [], projects: testConfig().projects };
  it('从输出里提取 JSON', () => {
    const c = parseClassification('结果：{"agent":"codex","project":"api","confidence":0.8,"reason":"写测试"}', ctx);
    assert.deepEqual(c, { agent: 'codex', project: 'api', confidence: 0.8, reason: '写测试' });
  });
  it('未知助手和项目置空', () => {
    const c = parseClassification('{"agent":"gpt","project":"nope","confidence":2}', ctx);
    assert.deepEqual(c, { agent: null, project: null, confidence: 1, reason: '' });
  });
  it('非 JSON 抛错', () => assert.throws(() => parseClassification('不知道', ctx)));
});
