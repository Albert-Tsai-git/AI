/** 按 key 串行执行任务：同一会话的任务排队，不同会话并行。 */
export class KeyedQueue {
  private tails = new Map<string, Promise<void>>();
  private pending = new Map<string, number>();

  /** 当前 key 上正在执行 + 排队的任务数。 */
  size(key: string): number {
    return this.pending.get(key) ?? 0;
  }

  run<T>(key: string, task: () => Promise<T>): Promise<T> {
    this.pending.set(key, this.size(key) + 1);
    const prev = this.tails.get(key) ?? Promise.resolve();
    const result = prev.then(task);
    const tail = result.then(
      () => undefined,
      () => undefined,
    );
    this.tails.set(key, tail);
    void tail.then(() => {
      const left = this.size(key) - 1;
      if (left > 0) {
        this.pending.set(key, left);
      } else {
        this.pending.delete(key);
        if (this.tails.get(key) === tail) this.tails.delete(key);
      }
    });
    return result;
  }

  /** 等待所有 key 上的任务执行完（测试和优雅退出用）。 */
  async idle(): Promise<void> {
    while (this.tails.size > 0) {
      await Promise.all([...this.tails.values()]);
    }
  }
}
