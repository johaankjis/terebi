// Pair once from /play/#pair=TOKEN, then reuse the player session from sessionStorage.

export const STORAGE_KEY = 'terebi.rps.player.v1';
const TOKEN_RE = /^[A-Za-z0-9_-]{16,256}$/;

/** Read and strip the pairing fragment. Returns the token or null. */
export function takePairToken(loc, hist) {
  const hash = typeof loc?.hash === 'string' ? loc.hash : '';
  if (!hash || hash === '#') return null;
  const params = new URLSearchParams(hash.slice(1));
  const token = params.get('pair');
  // Always strip the fragment so a secret never lingers in the address bar or history.
  try {
    hist?.replaceState?.(hist.state ?? null, '', `${loc.pathname}${loc.search}`);
  } catch {
    /* ignore: stripping is best effort */
  }
  return token && TOKEN_RE.test(token) ? token : null;
}

export function loadSession(storage) {
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw);
    if (typeof s?.session_id !== 'string' || typeof s?.player_token !== 'string') return null;
    return { session_id: s.session_id, player_token: s.player_token, pair_hash: s.pair_hash ?? null };
  } catch {
    return null;
  }
}

export function saveSession(storage, session) {
  try {
    storage?.setItem(
      STORAGE_KEY,
      JSON.stringify({ session_id: session.session_id, player_token: session.player_token, pair_hash: session.pair_hash ?? null }),
    );
  } catch {
    /* private mode: session lasts only for this page */
  }
}

export function clearSession(storage) {
  try {
    storage?.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export async function hashToken(token, subtle = globalThis.crypto?.subtle) {
  if (!subtle) return null;
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Resolve the player session.
 * - No fragment: reuse sessionStorage (reloads never re-pair).
 * - Fragment equal to the one already redeemed: reuse, no second POST.
 * - New fragment: POST /v1/pair once; on rejection fall back to a stored session.
 * Returns {session, state|null, source} or throws the pairing ApiError.
 */
export async function establishSession({ pairToken, storage, api, subtle }) {
  const stored = loadSession(storage);
  if (!pairToken) {
    if (stored) return { session: stored, state: null, source: 'stored' };
    return { session: null, state: null, source: 'none' };
  }
  const pairHash = await hashToken(pairToken, subtle).catch(() => null);
  if (stored && pairHash && stored.pair_hash === pairHash) return { session: stored, state: null, source: 'stored' };
  try {
    const { data } = await api.pair(pairToken);
    if (typeof data.session_id !== 'string' || typeof data.player_token !== 'string') throw new Error('bad pair response');
    const session = { session_id: data.session_id, player_token: data.player_token, pair_hash: pairHash };
    saveSession(storage, session);
    return { session, state: data.state ?? null, source: 'paired' };
  } catch (err) {
    if (stored) return { session: stored, state: null, source: 'stored', pairError: err };
    throw err;
  }
}
