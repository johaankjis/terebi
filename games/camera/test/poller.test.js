import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Poller } from '../src/lib/poller.js';
import { deferred, flush } from './helpers.js';

function manualTimers() {
  const q = [];
  return {
    q,
    setTimeout: (fn, ms) => {
      q.push({ fn, ms });
      return q.length;
    },
    clearTimeout: (id) => {
      if (q[id - 1]) q[id - 1].fn = null;
    },
    async fire() {
      const t = q.find((x) => x.fn);
      const fn = t.fn;
      t.fn = null;
      fn();
      await flush();
      return t.ms;
    },
    pending: () => q.filter((x) => x.fn).length,
  };
}

test('never overlaps requests and keeps a 400 ms cadence', async () => {
  const timers = manualTimers();
  let active = 0;
  let maxActive = 0;
  let gate = deferred();
  const p = new Poller({
    timers,
    now: () => 0,
    fetchOnce: async () => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await gate.promise;
      active -= 1;
      return 'ok';
    },
    onResult: () => {},
  });
  p.start();
  await timers.fire(); // request 1 in flight
  p.start(); // no second loop
  assert.equal(timers.pending(), 0, 'nothing scheduled while in flight');
  gate.resolve();
  await flush();
  assert.equal(timers.pending(), 1);
  assert.equal(timers.q.at(-1).ms, 400);
  gate = deferred();
  gate.resolve();
  await timers.fire();
  assert.equal(maxActive, 1);
  p.stop();
});

test('backs off on errors and stops for good on expiry', async () => {
  const timers = manualTimers();
  const results = [new Error('net'), new Error('net'), Object.assign(new Error('gone'), { kind: 'expired' })];
  let terminal = 0;
  const p = new Poller({
    timers,
    now: () => 0,
    fetchOnce: async () => {
      throw results.shift();
    },
    onError: () => {},
    onTerminal: () => (terminal += 1),
  });
  p.start();
  await timers.fire();
  assert.equal(timers.q.at(-1).ms, 800);
  await timers.fire();
  assert.equal(timers.q.at(-1).ms, 1600);
  await timers.fire();
  assert.equal(terminal, 1);
  assert.equal(timers.pending(), 0);
});

test('results that arrive after stop are dropped', async () => {
  const timers = manualTimers();
  const gate = deferred();
  const seen = [];
  const p = new Poller({ timers, now: () => 0, fetchOnce: () => gate.promise, onResult: (r) => seen.push(r) });
  p.start();
  await timers.fire();
  p.stop();
  gate.resolve('late');
  await flush();
  assert.deepEqual(seen, []);
  assert.equal(timers.pending(), 0);
});
