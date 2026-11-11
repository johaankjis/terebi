// Server clock estimate anchored to the local monotonic clock (performance.now).
// The device wall clock is never used for countdown timing.

export class ServerClock {
  constructor({ now = () => performance.now(), maxSamples = 8, maxRttMs = 5000 } = {}) {
    this.now = now;
    this.maxSamples = maxSamples;
    this.maxRttMs = maxRttMs;
    this.samples = [];
    this.offset = null; // serverEpochMs - monotonicMs
  }

  get synced() {
    return this.offset !== null;
  }

  /** Record a response: server_time_ms observed between sentMono and recvMono. */
  sample(serverTimeMs, sentMono, recvMono) {
    if (!Number.isFinite(serverTimeMs) || !Number.isFinite(sentMono) || !Number.isFinite(recvMono)) return;
    const rtt = recvMono - sentMono;
    if (rtt < 0 || rtt > this.maxRttMs) return;
    const offset = serverTimeMs - (sentMono + recvMono) / 2;
    this.samples.push({ rtt, offset });
    if (this.samples.length > this.maxSamples) this.samples.shift();
    // Lowest round trip among recent samples has the tightest error bound.
    let best = this.samples[0];
    for (const s of this.samples) if (s.rtt < best.rtt) best = s;
    this.offset = best.offset;
  }

  serverNow() {
    return this.synced ? this.now() + this.offset : null;
  }

  /** Convert a server epoch time into the local monotonic timeline. */
  toMono(serverMs) {
    return this.synced ? serverMs - this.offset : null;
  }
}
