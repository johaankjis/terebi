import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ServerClock } from '../src/lib/clock.js';

test('server time is estimated from the monotonic clock, ignoring device wall clock', () => {
  let mono = 1000;
  const clock = new ServerClock({ now: () => mono });
  assert.equal(clock.serverNow(), null);
  // Phone wall clock may be minutes off; only server_time_ms and RTT midpoint matter.
  clock.sample(1_700_000_000_000, 900, 1100); // midpoint 1000
  assert.equal(clock.serverNow(), 1_700_000_000_000);
  mono = 3500;
  assert.equal(clock.serverNow(), 1_700_000_002_500);
  assert.equal(clock.toMono(1_700_000_003_000), 4000);
});

test('lowest round-trip sample wins and bad samples are ignored', () => {
  const clock = new ServerClock({ now: () => 0, maxSamples: 3 });
  clock.sample(10_000, 0, 400); // rtt 400, offset 9800
  clock.sample(10_050, 100, 120); // rtt 20, offset 9940
  clock.sample(10_000, 500, 400); // negative rtt: ignored
  clock.sample(Number.NaN, 0, 10); // ignored
  assert.equal(clock.offset, 9940);
  clock.sample(20_000, 0, 50);
  clock.sample(20_000, 0, 60);
  clock.sample(20_000, 0, 70); // pushes out the rtt-20 sample (window of 3)
  assert.equal(clock.offset, 19_975);
});
