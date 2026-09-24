#!/usr/bin/env node
// Codex notify 转发脚本：把 agent-turn-complete 事件转发给本机桥接服务。
// 在 ~/.codex/config.toml 里配置：
//   notify = ["node", "/绝对路径/feishu-bridge/scripts/codex-notify.mjs"]
// Codex 会把事件 JSON 作为最后一个参数传进来。
const payload = process.argv.at(-1) ?? '{}';
const url = process.env.AI_BRIDGE_URL ?? 'http://127.0.0.1:7788/hooks/codex';
const headers = {
  'content-type': 'application/json',
  // 桥接服务自己启动的 Codex 会带上 AI_BRIDGE_ORIGIN=bridge，服务端据此跳过，避免重复同步
  'x-bridge-origin': process.env.AI_BRIDGE_ORIGIN ?? '',
};
if (process.env.AI_BRIDGE_TOKEN) headers['x-bridge-token'] = process.env.AI_BRIDGE_TOKEN;

try {
  await fetch(url, { method: 'POST', headers, body: payload, signal: AbortSignal.timeout(3000) });
} catch {
  // 桥接服务没启动时静默失败，不影响 Codex
}
