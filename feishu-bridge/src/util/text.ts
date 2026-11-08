export function truncateHead(s: string, max: number): string {
  return s.length <= max ? s : `${s.slice(0, max)}\n…（已截断，共 ${s.length} 字）`;
}

export function truncateTail(s: string, max: number): string {
  return s.length <= max ? s : `…${s.slice(s.length - max)}`;
}

export function oneLine(s: string, max = 120): string {
  const flat = s.replace(/\s+/g, ' ').trim();
  return flat.length <= max ? flat : `${flat.slice(0, max)}…`;
}

const SECRET_PATTERNS: RegExp[] = [
  /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
  /\bsk-ant-[A-Za-z0-9_-]{20,}/g,
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}/g,
  /\bgh[pousr]_[A-Za-z0-9]{30,}/g,
  /\bgithub_pat_[A-Za-z0-9_]{30,}/g,
  /\bAKIA[0-9A-Z]{16}\b/g,
  /\bxox[abprs]-[A-Za-z0-9-]{10,}/g,
];

/** 发往飞书前对常见密钥打码。 */
export function redactSecrets(s: string): string {
  return SECRET_PATTERNS.reduce((acc, re) => acc.replace(re, '[REDACTED]'), s);
}

/** 飞书卡片 markdown 会解析部分尖括号标签，代码块之外转义掉。 */
export function escapeCardMarkdown(s: string): string {
  return s
    .split(/(```[\s\S]*?```)/g)
    .map((part, i) => (i % 2 === 1 ? part : part.replace(/</g, '&lt;').replace(/>/g, '&gt;')))
    .join('');
}

export function shortId(prefix: string): string {
  return `${prefix}${Math.random().toString(36).slice(2, 8)}`;
}
