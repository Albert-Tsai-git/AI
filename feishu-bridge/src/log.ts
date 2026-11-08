export interface Logger {
  info(msg: string, extra?: unknown): void;
  warn(msg: string, extra?: unknown): void;
  error(msg: string, extra?: unknown): void;
}

function write(level: string, msg: string, extra?: unknown): void {
  const line = `${new Date().toISOString()} ${level} ${msg}`;
  if (extra === undefined) console.log(line);
  else console.log(line, extra instanceof Error ? extra.stack ?? extra.message : extra);
}

export const consoleLogger: Logger = {
  info: (m, e) => write('INFO ', m, e),
  warn: (m, e) => write('WARN ', m, e),
  error: (m, e) => write('ERROR', m, e),
};

export const silentLogger: Logger = { info() {}, warn() {}, error() {} };
