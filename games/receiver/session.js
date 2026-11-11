// This module receives only a session's read-only display capability.
export const NAMESPACE = 'urn:x-cast:com.terebi.games';
const PHASES = new Set(['waiting_for_player','ready','countdown','reveal','score','next_round']);
const opaque = value => typeof value === 'string' && /^[A-Za-z0-9_-]{16,128}$/.test(value);

export async function confirmEnded(credentials) {
  const request = new AbortController();
  const timeout = setTimeout(() => request.abort(), 4000);
  try {
    const response = await fetch(`/v1/sessions/${encodeURIComponent(credentials.id)}`, {
      headers: {Authorization: `Bearer ${credentials.token}`},
      cache: 'no-store', signal: request.signal,
    });
    const data = await response.json();
    return data.ok === false && ((response.status === 410 &&
      ['session_ended','session_expired'].includes(data.reason)) ||
      (response.status === 404 && data.reason === 'session_missing'));
  } catch { return false; }
  finally { clearTimeout(timeout); }
}

export function installSessions(context, startDisplay, {verifyEnded = confirmEnded, afterPaint = fn => requestAnimationFrame(() => requestAnimationFrame(fn)), ended = () => {}} = {}) {
  let generation = 0, stopDisplay = null, expiryTimer = null, active = null;
  function clear() {
    generation++; active = null;
    stopDisplay?.(); stopDisplay = null;
    clearTimeout(expiryTimer); expiryTimer = null;
  }
  async function receive(event) {
    const data = event.data;
    if (!data || typeof data !== 'object' || Array.isArray(data) ||
        Object.keys(data).sort().join(',') !== 'display_token,request_id,session_id,type' ||
        !['SHOW_SESSION','END_SESSION'].includes(data.type) || !opaque(data.session_id) || !opaque(data.display_token) || !opaque(data.request_id) ||
        typeof event.senderId !== 'string' || !event.senderId) return;
    if (data.type === 'END_SESSION') {
      const current = generation;
      if (!active || active.id !== data.session_id || active.token !== data.display_token) {
        try { context.sendCustomMessage(NAMESPACE, event.senderId, {
          type: active ? 'SESSION_NOT_CURRENT' : 'SESSION_UNKNOWN',
          session_id: data.session_id, request_id: data.request_id,
        }); } catch { /* disconnected */ }
        return;
      }
      // A viewer credential cannot end a live game. The service must already revoke it.
      const revoked = await verifyEnded(active);
      if (!revoked || current !== generation || !active || active.id !== data.session_id) return;
      try { context.sendCustomMessage(NAMESPACE, event.senderId, {
        type: 'SESSION_ENDING', session_id: data.session_id, request_id: data.request_id,
      }); } catch { /* closure is confirmed by the sender's receiver status */ }
      clear(); ended(); return;
    }
    clear();
    active = {id: data.session_id, token: data.display_token};
    const current = generation;
    let lastRevision = -1, latestRevision = -1;
    stopDisplay = startDisplay({id: data.session_id, token: data.display_token}, {
      onRendered(state) {
        if (current !== generation || state.session_id !== data.session_id || !PHASES.has(state.phase) ||
            !Number.isInteger(state.revision) || state.revision < 1 || !Number.isFinite(state.expires_at_ms)) return;
        latestRevision = Math.max(latestRevision, state.revision);
        if (!expiryTimer) expiryTimer = setTimeout(() => { clear(); ended(); }, Math.max(0, state.expires_at_ms - state.server_time_ms));
        afterPaint(() => {
          if (current !== generation || state.revision !== latestRevision || state.revision <= lastRevision) return;
          lastRevision = state.revision;
          try {
            context.sendCustomMessage(NAMESPACE, event.senderId, {
              type: 'DISPLAY_RENDERED', request_id: data.request_id,
              session_id: state.session_id, phase: state.phase, revision: state.revision,
            });
          } catch { /* sender disconnected; the game still runs on the TV */ }
        });
      },
      onFailure(reason) {
        if (current !== generation) return;
        try { context.sendCustomMessage(NAMESPACE, event.senderId, {type:'DISPLAY_FAILED', request_id:data.request_id, session_id:data.session_id, reason}); } catch { /* no sender */ }
        if (reason === 'session_ended') { clear(); ended(); }
      },
    });
  }
  context.addCustomMessageListener(NAMESPACE, receive);
  return clear;
}
