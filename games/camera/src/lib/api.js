// Same-origin client for the frozen Terebi Games v1 wire API.
// Bearer tokens travel only in the Authorization header and are never logged.

import { isMove } from './gesture.js';

export class ApiError extends Error {
  constructor(status, reason, hint, kind) {
    super(reason || `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.reason = reason || null;
    this.hint = hint || null;
    this.kind = kind;
  }
}

export function errorKind(status) {
  if (status === 401 || status === 404 || status === 410) return 'expired';
  if (status === 409) return 'conflict';
  if (status === 429) return 'rate_limited';
  if (status === 400 || status === 413) return 'bad_request';
  return 'server';
}

export function createApi({ fetchImpl = (...a) => globalThis.fetch(...a), timeoutMs = 4000, getToken = () => null, now = () => performance.now() } = {}) {
  async function request(method, path, body, { auth = true, signal } = {}) {
    const ctrl = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      ctrl.abort();
    }, timeoutMs);
    const onOuterAbort = () => ctrl.abort();
    if (signal) {
      if (signal.aborted) ctrl.abort();
      else signal.addEventListener('abort', onOuterAbort, { once: true });
    }
    const headers = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (auth) {
      const token = getToken();
      if (!token) {
        clearTimeout(timer);
        throw new ApiError(401, 'not_paired', 'Open the play link from Telegram again.', 'expired');
      }
      headers.Authorization = `Bearer ${token}`;
    }
    const sentMono = now();
    let res;
    try {
      res = await fetchImpl(path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: 'no-store',
        credentials: 'same-origin',
        signal: ctrl.signal,
      });
    } catch (err) {
      if (timedOut) throw new ApiError(0, 'timeout', 'The game server did not answer in time.', 'timeout');
      if (signal?.aborted) throw new ApiError(0, 'aborted', null, 'aborted');
      throw new ApiError(0, 'network', 'Check the phone is online.', 'network');
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener?.('abort', onOuterAbort);
    }
    const recvMono = now();
    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    if (!res.ok || !data || data.ok === false) {
      const status = res.ok ? 502 : res.status;
      throw new ApiError(status, data?.reason, data?.hint, errorKind(status));
    }
    return { data, sentMono, recvMono };
  }

  const sessionPath = (id, suffix = '') => `/v1/sessions/${encodeURIComponent(id)}${suffix}`;

  function moveBody(roundId, move) {
    if (typeof roundId !== 'string' || !roundId) throw new ApiError(400, 'bad_round', null, 'bad_request');
    if (!isMove(move)) throw new ApiError(400, 'bad_move', null, 'bad_request');
    return { round_id: roundId, move }; // exactly these two keys, nothing else
  }

  return {
    pair: (pairToken) => request('POST', '/v1/pair', { pair_token: pairToken }, { auth: false }),
    getState: (id, opts) => request('GET', sessionPath(id), undefined, opts),
    next: (id, roundId) => request('POST', sessionPath(id, '/next'), { round_id: roundId }),
    retry: (id, roundId) => request('POST', sessionPath(id, '/retry'), { round_id: roundId }),
    move: async (id, roundId, move, opts) => request('POST', sessionPath(id, '/move'), moveBody(roundId, move), opts),
    tap: async (id, roundId, move, opts) => request('POST', sessionPath(id, '/tap'), moveBody(roundId, move), opts),
  };
}
