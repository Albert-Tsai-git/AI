import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { setup, testConfig, userMessage, waitFor } from './helpers.js';

describe('飞书 → AI', () => {
  it('新消息：分析、建会话、在话题里回复执行卡片、完成后更新卡片', async () => {
    const { bridge, feishu, claude, codex, store } = setup();
    const msg = userMessage('/claude api 看看日志');
    await bridge.onMessage(msg);
    await bridge.idle();

    assert.equal(codex.calls.length, 0);
    assert.equal(claude.calls.length, 1);
    assert.equal(claude.calls[0].cwd, '/tmp/api');
    assert.equal(claude.calls[0].prompt, '看看日志');
    assert.equal(claude.calls[0].sessionRef, undefined);

    const card = feishu.sent[0];
    assert.equal(card.to, msg.messageId);
    assert.equal(card.inThread, true);
    const final = feishu.currentCard(card.id);
    assert.match(final, /完成/);
    assert.match(final, /完成：看看日志/);
    assert.match(final, /claude --resume claude-ref-1/);

    const session = store.findSessionByMessage(msg.messageId)!;
    assert.equal(session.agent, 'claude');
    assert.equal(session.agentRef, 'claude-ref-1');
    assert.equal(store.findSessionByMessage(card.id)?.id, session.id);
  });

  it('在话题里回复（root_id）或引用机器人卡片（parent_id）都能续上同一个会话', async () => {
    const { bridge, feishu, claude } = setup();
    const first = userMessage('/claude 做个计划');
    await bridge.onMessage(first);
    await bridge.idle();

    await bridge.onMessage(userMessage('继续第二步', { rootId: first.messageId }));
    await bridge.idle();
    await bridge.onMessage(userMessage('cc 再改一下', { parentId: feishu.sent[0].id }));
    await bridge.idle();

    assert.equal(claude.calls.length, 3);
    assert.equal(claude.calls[1].sessionRef, 'claude-ref-1');
    assert.equal(claude.calls[1].prompt, '继续第二步');
    assert.equal(claude.calls[2].sessionRef, 'claude-ref-1');
    assert.equal(claude.calls[2].prompt, '再改一下');
  });

  it('话题里点名另一个助手时提示发新消息', async () => {
    const { bridge, feishu, codex } = setup();
    const first = userMessage('/claude 做个计划');
    await bridge.onMessage(first);
    await bridge.idle();
    await bridge.onMessage(userMessage('/codex 写代码', { rootId: first.messageId }));
    await bridge.idle();
    assert.equal(codex.calls.length, 0);
    assert.match(feishu.textsTo(feishu.sent.at(-1)!.to).at(-1)!, /发一条新消息/);
  });

  it('同一会话的消息排队串行执行', async () => {
    const { bridge, claude } = setup();
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    let concurrent = 0;
    let maxConcurrent = 0;
    claude.script = async (req) => {
      concurrent++;
      maxConcurrent = Math.max(maxConcurrent, concurrent);
      if (claude.calls.length === 1) await gate;
      concurrent--;
      return { sessionRef: 'r1', result: req.prompt, isError: false };
    };
    const first = userMessage('/claude 一');
    await bridge.onMessage(first);
    await bridge.onMessage(userMessage('二', { rootId: first.messageId }));
    await waitFor(() => claude.calls.length === 1);
    release();
    await bridge.idle();
    assert.equal(claude.calls.length, 2);
    assert.equal(maxConcurrent, 1);
    assert.equal(claude.calls[1].sessionRef, 'r1');
  });

  it('权限审批：卡片按钮允许', async () => {
    const { bridge, feishu, claude } = setup();
    let decision: string | undefined;
    claude.script = async (req, sink) => {
      sink.sessionRef('r1');
      decision = await sink.askPermission({ tool: 'Bash', detail: 'rm -rf build', signal: req.signal });
      return { sessionRef: 'r1', result: 'ok', isError: false };
    };
    await bridge.onMessage(userMessage('/claude 清理构建目录'));
    await waitFor(() => feishu.cardsContaining('需要确认：Bash').length === 1);
    const approval = feishu.cardsContaining('需要确认：Bash')[0];
    assert.equal(approval.inThread, true);
    const approvalId = JSON.stringify(approval.msg).match(/"id":"(a\w+)"/)![1];

    const denied = await bridge.onCardAction({ operatorOpenId: 'ou_other', value: { a: 'approve', id: approvalId, d: 'allow' } });
    assert.equal(denied.toast?.type, 'error');
    const res = await bridge.onCardAction({ operatorOpenId: 'ou_me', value: { a: 'approve', id: approvalId, d: 'allow' } });
    assert.equal(res.toast?.type, 'success');
    await bridge.idle();

    assert.equal(decision, 'allow');
    assert.match(feishu.currentCard(approval.id), /已允许/);
  });

  it('权限审批：在话题里回复 n 拒绝；"始终允许"后同一工具不再询问', async () => {
    const { bridge, feishu, claude } = setup();
    const decisions: string[] = [];
    claude.script = async (req, sink) => {
      for (let i = 0; i < 2; i++) decisions.push(await sink.askPermission({ tool: 'Edit', detail: 'a.ts', signal: req.signal }));
      return { sessionRef: 'r1', result: 'ok', isError: false };
    };
    const first = userMessage('/claude 改文件');
    await bridge.onMessage(first);
    await waitFor(() => feishu.cardsContaining('需要确认：Edit').length === 1);
    await bridge.onMessage(userMessage('始终允许', { rootId: first.messageId }));
    await bridge.idle();
    assert.deepEqual(decisions, ['always', 'allow']);
    assert.equal(feishu.cardsContaining('需要确认：Edit').length, 1);

    claude.script = async (req, sink) => {
      decisions.push(await sink.askPermission({ tool: 'Bash', detail: 'ls', signal: req.signal }));
      return { sessionRef: 'r1', result: 'ok', isError: false };
    };
    await bridge.onMessage(userMessage('再来', { rootId: first.messageId }));
    await waitFor(() => feishu.cardsContaining('需要确认：Bash').length === 1);
    await bridge.onMessage(userMessage('n', { rootId: first.messageId }));
    await bridge.idle();
    assert.equal(decisions.at(-1), 'deny');
  });

  it('权限审批超时按拒绝处理', async () => {
    const { bridge, claude } = setup({ config: testConfig({ claude: { approvalTimeoutSec: 0.05 } }) });
    let decision: string | undefined;
    claude.script = async (req, sink) => {
      decision = await sink.askPermission({ tool: 'Bash', detail: 'ls', signal: req.signal });
      return { result: 'ok', isError: false };
    };
    await bridge.onMessage(userMessage('/claude 跑一下'));
    await bridge.idle();
    assert.equal(decision, 'deny');
  });

  it('/stop 停止话题里正在执行的任务', async () => {
    const { bridge, feishu, claude } = setup();
    claude.script = (req) =>
      new Promise((_, reject) => req.signal.addEventListener('abort', () => reject(new Error('aborted'))));
    const first = userMessage('/claude 跑很久');
    await bridge.onMessage(first);
    await waitFor(() => claude.calls.length === 1);
    await bridge.onMessage(userMessage('/stop', { rootId: first.messageId }));
    await bridge.idle();
    assert.match(feishu.currentCard(feishu.sent[0].id), /已停止/);
  });

  it('卡片上的停止按钮', async () => {
    const { bridge, feishu, claude, store } = setup();
    claude.script = (req) =>
      new Promise((resolve) => req.signal.addEventListener('abort', () => resolve({ result: '', isError: true })));
    const first = userMessage('/claude 跑很久');
    await bridge.onMessage(first);
    await waitFor(() => claude.calls.length === 1);
    const sessionId = store.findSessionByMessage(first.messageId)!.id;
    const res = await bridge.onCardAction({ operatorOpenId: 'ou_me', value: { a: 'stop', s: sessionId } });
    assert.equal(res.toast?.type, 'success');
    await bridge.idle();
    assert.match(feishu.currentCard(feishu.sent[0].id), /已停止/);
  });

  it('执行失败时卡片显示失败', async () => {
    const { bridge, feishu, codex } = setup();
    codex.script = async () => {
      throw new Error('Not inside a trusted directory');
    };
    await bridge.onMessage(userMessage('/codex 写代码'));
    await bridge.idle();
    const card = feishu.currentCard(feishu.sent[0].id);
    assert.match(card, /失败/);
    assert.match(card, /Not inside a trusted directory/);
  });

  it('结果过长时卡片截断，全文以文件发送', async () => {
    const { bridge, feishu, claude } = setup({ config: testConfig({ ui: { updateIntervalMs: 0, maxCardChars: 100 } }) });
    claude.script = async () => ({ result: 'x'.repeat(500), isError: false });
    await bridge.onMessage(userMessage('/claude 写长文'));
    await bridge.idle();
    assert.match(feishu.currentCard(feishu.sent[0].id), /已截断/);
    assert.equal(feishu.files.length, 1);
    assert.equal(feishu.files[0].content.length, 500);
    assert.equal(feishu.sent.at(-1)!.msg.type, 'file');
  });

  it('模型拿不准时发选择卡片，点击后执行', async () => {
    const { bridge, feishu, codex } = setup({
      config: testConfig({ analyzer: { mode: 'llm', confirmBelow: 0.7 } }),
      classify: async () => ({ agent: 'codex', project: null, confidence: 0.3, reason: '不确定' }),
    });
    await bridge.onMessage(userMessage('看看这个'));
    await bridge.idle();
    const cardId = feishu.sent[0].id;
    const current = feishu.currentCard(cardId);
    assert.match(current, /交给谁来做/);
    assert.match(current, /Codex（推荐）/);
    const choiceId = current.match(/"id":"(c\w+)"/)![1];

    await bridge.onCardAction({ operatorOpenId: 'ou_me', value: { a: 'choose', id: choiceId, agent: 'codex' } });
    await waitFor(() => codex.calls.length === 1);
    await bridge.idle();
    assert.match(feishu.currentCard(cardId), /Codex · web · 完成/);
    const again = await bridge.onCardAction({ operatorOpenId: 'ou_me', value: { a: 'choose', id: choiceId, agent: 'codex' } });
    assert.equal(again.toast?.type, 'warning');
  });

  it('白名单为空时回复 open_id；非白名单用户被忽略；重复事件只处理一次', async () => {
    const open = setup({ config: testConfig({ feishu: { appId: 'a', appSecret: 'b', allowedOpenIds: [] } }) });
    await open.bridge.onMessage(userMessage('hi', { senderOpenId: 'ou_new' }));
    assert.match(open.feishu.textsTo(open.feishu.sent[0].to)[0], /ou_new/);

    const { bridge, feishu, claude } = setup();
    await bridge.onMessage(userMessage('/claude hi', { senderOpenId: 'ou_stranger' }));
    const msg = userMessage('/claude hi');
    await bridge.onMessage(msg);
    await bridge.onMessage(msg);
    await bridge.idle();
    assert.equal(claude.calls.length, 1);
    assert.equal(feishu.sent.length, 1);
  });

  it('/help /ls /projects /status 命令', async () => {
    const { bridge, feishu } = setup();
    for (const cmd of ['/help', '/ls', '/projects', '/status']) await bridge.onMessage(userMessage(cmd));
    const titles = feishu.sent.map((s) => JSON.stringify(s.msg));
    assert.match(titles[0], /怎么用/);
    assert.match(titles[1], /还没有会话/);
    assert.match(titles[2], /\/tmp\/api/);
    assert.match(titles[3], /执行中：无/);
    assert.ok(feishu.sent.every((s) => s.inThread === false));
  });
});

describe('本地终端 → 飞书', () => {
  it('Claude 本地会话同步到飞书话题，在话题里回复会接着这个会话（终端开着时分叉）', async () => {
    const { bridge, feishu, claude, store } = setup();
    await bridge.onLocalEvent({ agent: 'claude', kind: 'session_start', ref: 'local-1', cwd: '/tmp/web/src' });
    await bridge.onLocalEvent({ agent: 'claude', kind: 'prompt', ref: 'local-1', cwd: '/tmp/web/src', text: '解释下这个函数' });
    await bridge.onLocalEvent({ agent: 'claude', kind: 'reply', ref: 'local-1', cwd: '/tmp/web/src', text: '它负责登录' });

    const [root, prompt, reply] = feishu.sent;
    assert.equal(root.kind, 'user');
    assert.equal(root.to, 'ou_me');
    assert.match((root.msg as { text: string }).text, /本地 Claude 会话 · web/);
    assert.equal(prompt.to, root.id);
    assert.equal(prompt.inThread, true);
    assert.match((prompt.msg as { text: string }).text, /解释下这个函数/);
    assert.match(JSON.stringify(reply.msg), /它负责登录/);

    const session = store.findSessionByRef('claude', 'local-1')!;
    assert.equal(session.live, true);
    assert.equal(session.project, 'web');

    claude.script = async (_req, sink) => {
      sink.sessionRef('forked-1');
      return { sessionRef: 'forked-1', result: 'done', isError: false };
    };
    await bridge.onMessage(userMessage('那登出呢', { rootId: root.id }));
    await bridge.idle();
    assert.equal(claude.calls[0].sessionRef, 'local-1');
    assert.equal(claude.calls[0].fork, true);
    assert.equal(claude.calls[0].cwd, '/tmp/web/src');
    const updated = store.getSession(session.id)!;
    assert.equal(updated.agentRef, 'forked-1');
    assert.equal(updated.live, false);
  });

  it('终端已退出时直接续上原会话', async () => {
    const { bridge, feishu, claude } = setup();
    await bridge.onLocalEvent({ agent: 'claude', kind: 'prompt', ref: 'local-2', cwd: '/tmp/x', text: 'hi' });
    await bridge.onLocalEvent({ agent: 'claude', kind: 'session_end', ref: 'local-2', cwd: '/tmp/x' });
    await bridge.onMessage(userMessage('继续', { rootId: feishu.sent[0].id }));
    await bridge.idle();
    assert.equal(claude.calls[0].sessionRef, 'local-2');
    assert.equal(claude.calls[0].fork, false);
  });

  it('whenLive=reject 时不执行', async () => {
    const { bridge, feishu, claude } = setup({ config: testConfig({ claude: { whenLive: 'reject' } }) });
    await bridge.onLocalEvent({ agent: 'claude', kind: 'prompt', ref: 'local-3', cwd: '/tmp/x', text: 'hi' });
    await bridge.onMessage(userMessage('继续', { rootId: feishu.sent[0].id }));
    await bridge.idle();
    assert.equal(claude.calls.length, 0);
    assert.match(feishu.currentCard(feishu.sent.at(-1)!.id), /终端里打开着/);
  });

  it('Codex 本地会话同步', async () => {
    const { bridge, feishu, codex } = setup();
    await bridge.onLocalEvent({ agent: 'codex', kind: 'prompt', ref: 'th-1', cwd: '/tmp/api', text: '跑测试' });
    await bridge.onLocalEvent({ agent: 'codex', kind: 'reply', ref: 'th-1', cwd: '/tmp/api', text: '全部通过' });
    assert.equal(feishu.sent.length, 3);
    await bridge.onMessage(userMessage('再加一个用例', { rootId: feishu.sent[0].id }));
    await bridge.idle();
    assert.equal(codex.calls[0].sessionRef, 'th-1');
    assert.equal(codex.calls[0].fork, false);
  });

  it('防回环：桥接服务自己发起的执行不会再同步回飞书', async () => {
    const { bridge, feishu, claude } = setup();
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    claude.script = async (_req, sink) => {
      sink.sessionRef('bridge-ref');
      await gate;
      return { sessionRef: 'bridge-ref', result: 'ok', isError: false };
    };
    await bridge.onMessage(userMessage('/claude 做事'));
    await waitFor(() => claude.calls.length === 1);
    const before = feishu.sent.length;

    // hooks 带了来源标记
    await bridge.onLocalEvent({ agent: 'claude', kind: 'prompt', ref: 'bridge-ref', cwd: '/tmp/web', text: '做事', origin: 'bridge' });
    // hooks 没带来源标记，但会话正由桥接服务驱动
    await bridge.onLocalEvent({ agent: 'claude', kind: 'reply', ref: 'bridge-ref', cwd: '/tmp/web', text: 'ok' });
    release();
    await bridge.idle();
    assert.equal(feishu.sent.length, before);
  });

  it('飞书发起的会话，之后在终端 resume 时同步回同一个话题', async () => {
    const { bridge, feishu } = setup();
    const first = userMessage('/claude 做事');
    await bridge.onMessage(first);
    await bridge.idle();
    await new Promise((r) => setTimeout(r, 0));
    // 模拟 10 秒防回环窗口已过
    (bridge as unknown as { bridgeRefs: Set<string> }).bridgeRefs.clear();

    await bridge.onLocalEvent({ agent: 'claude', kind: 'prompt', ref: 'claude-ref-1', cwd: '/tmp/web', text: '在终端里继续' });
    const last = feishu.sent.at(-1)!;
    assert.equal(last.to, first.messageId);
    assert.equal(last.inThread, true);
    assert.match((last.msg as { text: string }).text, /在终端里继续/);
  });
});
