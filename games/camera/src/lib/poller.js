// Non-overlapping session poller: one request at a time, 400 ms cadence,
// exponential backoff on errors, stops for good on terminal (expired) errors.

export class Poller {
  constructor({ fetchOnce, onResult, onError, onTerminal, intervalMs = 400, maxBackoffMs = 5000, timers = globalThis, now = () => performance.now() }) {
    Object.assign(this, { fetchOnce, onResult, onError, onTerminal, intervalMs, maxBackoffMs, timers, now });
    this.running = false;
    this.inFlight = false;
    this.timer = null;
    this.failures = 0;
    this.epoch = 0;
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.epoch += 1;
    if (!this.inFlight) this.#schedule(0);
  }

  stop() {
    this.running = false;
    this.epoch += 1;
    if (this.timer !== null) this.timers.clearTimeout(this.timer);
    this.timer = null;
  }

  backoffMs() {
    if (this.failures === 0) return this.intervalMs;
    return Math.min(this.maxBackoffMs, this.intervalMs * 2 ** this.failures);
  }

  #schedule(delay) {
    if (this.timer !== null) this.timers.clearTimeout(this.timer);
    this.timer = this.timers.setTimeout(() => {
      this.timer = null;
      this.#tick();
    }, delay);
  }

  async #tick() {
    if (!this.running || this.inFlight) return;
    const epoch = this.epoch;
    this.inFlight = true;
    const started = this.now();
    let terminal = false;
    try {
      const result = await this.fetchOnce();
      this.failures = 0;
      if (epoch === this.epoch) this.onResult?.(result);
    } catch (err) {
      if (err?.kind === 'expired') {
        terminal = true;
        this.running = false;
        this.onTerminal?.(err);
      } else {
        this.failures += 1;
        if (epoch === this.epoch) this.onError?.(err, this.failures);
      }
    } finally {
      this.inFlight = false;
    }
    if (terminal || !this.running) return;
    const elapsed = this.now() - started;
    const delay = this.failures ? this.backoffMs() : Math.max(0, this.intervalMs - elapsed);
    this.#schedule(delay);
  }
}
