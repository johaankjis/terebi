import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiError, createApi } from '../src/lib/api.js';

function recorder(response = { ok: true, state: {} }, status = 200) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init, body: init.body === undefined ? undefined : JSON.parse(init.body) });
    return { ok: status >= 200 && status < 300, status, json: async () => response };
  };
  return { calls, fetchImpl };
}

test('move and tap send ONLY {round_id, move} with bearer header, no token in URL', async () => {
  const { calls, fetchImpl } = recorder();
  const api = createApi({ fetchImpl, getToken: () => 'secret-player-token' });
  await api.move('s1', 'r1', 'rock');
  await api.tap('s1', 'r1', 'scissors');
  assert.equal(calls[0].url, '/v1/sessions/s1/move');
  assert.equal(calls[1].url, '/v1/sessions/s1/tap');
  assert.deepEqual(Object.keys(calls[0].body).sort(), ['move', 'round_id']);
  assert.deepEqual(calls[1].body, { round_id: 'r1', move: 'scissors' });
  for (const c of calls) {
    assert.equal(c.init.headers.Authorization, 'Bearer secret-player-token');
    assert.equal(c.init.cache, 'no-store');
    assert.ok(!c.url.includes('secret'));
    assert.ok(!c.url.includes('?'));
  }
});

test('invalid moves are refused before any request', async () => {
  const { calls, fetchImpl } = recorder();
  const api = createApi({ fetchImpl, getToken: () => 't' });
  for (const bad of ['lizard', 'Rock', '', null]) {
    await assert.rejects(api.move('s1', 'r1', bad), (e) => e instanceof ApiError && e.reason === 'bad_move');
  }
  assert.equal(calls.length, 0);
});

test('next/retry bodies and pair endpoint', async () => {
  const { calls, fetchImpl } = recorder({ ok: true, session_id: 's', player_token: 'p', state: null });
  const api = createApi({ fetchImpl, getToken: () => 't' });
  await api.next('s 1', 'r9');
  await api.retry('s1', 'r9');
  await api.pair('PAIRTOKEN');
  assert.equal(calls[0].url, '/v1/sessions/s%201/next');
  assert.deepEqual(calls[0].body, { round_id: 'r9' });
  assert.deepEqual(calls[1].body, { round_id: 'r9' });
  assert.equal(calls[2].url, '/v1/pair');
  assert.deepEqual(calls[2].body, { pair_token: 'PAIRTOKEN' });
  assert.equal(calls[2].init.headers.Authorization, undefined);
});

test('error statuses map to kinds', async () => {
  for (const [status, kind] of [[401, 'expired'], [404, 'expired'], [410, 'expired'], [409, 'conflict'], [429, 'rate_limited'], [500, 'server']]) {
    const { fetchImpl } = recorder({ ok: false, reason: 'x', hint: 'h' }, status);
    const api = createApi({ fetchImpl, getToken: () => 't' });
    await assert.rejects(api.getState('s'), (e) => e.kind === kind && e.status === status && e.hint === 'h');
  }
});

test('requests time out and are aborted', async () => {
  const fetchImpl = (url, init) => new Promise((_, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted'))));
  const api = createApi({ fetchImpl, getToken: () => 't', timeoutMs: 20 });
  await assert.rejects(api.getState('s'), (e) => e.kind === 'timeout');
});

test('missing token never sends an unauthenticated session request', async () => {
  const { calls, fetchImpl } = recorder();
  const api = createApi({ fetchImpl, getToken: () => null });
  await assert.rejects(api.getState('s'), (e) => e.kind === 'expired');
  assert.equal(calls.length, 0);
});
