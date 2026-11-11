import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { test } from 'node:test';
import { ApiError } from '../src/lib/api.js';
import { STORAGE_KEY, establishSession, loadSession, takePairToken } from '../src/lib/session.js';

const TOKEN = 'A'.repeat(43);

function memoryStorage() {
  const m = new Map();
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k), m };
}

test('pair token is read from the fragment and the fragment is stripped', () => {
  const calls = [];
  const hist = { state: null, replaceState: (...a) => calls.push(a) };
  assert.equal(takePairToken({ hash: `#pair=${TOKEN}`, pathname: '/play/', search: '' }, hist), TOKEN);
  assert.deepEqual(calls[0], [null, '', '/play/']);
  // Garbage fragment is still stripped but not used.
  assert.equal(takePairToken({ hash: '#pair=<script>', pathname: '/play/', search: '' }, hist), null);
  assert.equal(calls.length, 2);
  assert.equal(takePairToken({ hash: '', pathname: '/play/', search: '' }, hist), null);
  assert.equal(calls.length, 2);
});

test('pairs once, stores session, and reuses it on reload and on reopening the same link', async () => {
  const storage = memoryStorage();
  let pairs = 0;
  const api = {
    pair: async (t) => {
      pairs += 1;
      assert.equal(t, TOKEN);
      return { data: { ok: true, session_id: 's1', player_token: 'p1', state: { phase: 'ready' } } };
    },
  };
  const first = await establishSession({ pairToken: TOKEN, storage, api, subtle: webcrypto.subtle });
  assert.equal(first.source, 'paired');
  assert.equal(first.session.player_token, 'p1');
  assert.ok(storage.getItem(STORAGE_KEY).includes('s1'));
  assert.ok(!storage.getItem(STORAGE_KEY).includes(TOKEN), 'raw pair token is not stored');

  const reload = await establishSession({ pairToken: null, storage, api, subtle: webcrypto.subtle });
  assert.equal(reload.source, 'stored');
  const reopen = await establishSession({ pairToken: TOKEN, storage, api, subtle: webcrypto.subtle });
  assert.equal(reopen.source, 'stored');
  assert.equal(pairs, 1);
});

test('used/expired pairing falls back to stored session, else surfaces the error', async () => {
  const storage = memoryStorage();
  const api = { pair: async () => Promise.reject(new ApiError(410, 'pair_expired', null, 'expired')) };
  await assert.rejects(establishSession({ pairToken: TOKEN, storage, api, subtle: webcrypto.subtle }), (e) => e.reason === 'pair_expired');
  storage.setItem(STORAGE_KEY, JSON.stringify({ session_id: 's0', player_token: 'p0' }));
  const r = await establishSession({ pairToken: 'B'.repeat(43), storage, api, subtle: webcrypto.subtle });
  assert.equal(r.source, 'stored');
  assert.equal(r.session.session_id, 's0');
});

test('a new link for a new game replaces the stored session', async () => {
  const storage = memoryStorage();
  storage.setItem(STORAGE_KEY, JSON.stringify({ session_id: 'old', player_token: 'p0', pair_hash: 'x' }));
  const api = { pair: async () => ({ data: { ok: true, session_id: 'new', player_token: 'p2', state: null } }) };
  const r = await establishSession({ pairToken: TOKEN, storage, api, subtle: webcrypto.subtle });
  assert.equal(r.session.session_id, 'new');
  assert.equal(loadSession(storage).session_id, 'new');
});

test('no fragment and nothing stored means unpaired', async () => {
  const r = await establishSession({ pairToken: null, storage: memoryStorage(), api: {} });
  assert.equal(r.session, null);
});
