// This module receives only a session's read-only display capability.
export const NAMESPACE = 'urn:x-cast:com.terebi.games';
const PHASES = new Set(['waiting_for_player','ready','countdown','reveal','score','next_round']);
const opaque = value => typeof value === 'string' && /^[A-Za-z0-9_-]{16,128}$/.test(value);

export function installSessions(context, startDisplay, {afterPaint = fn => requestAnimationFrame(() => requestAnimationFrame(fn)), ended = () => {}} = {}) {
  let generation = 0, stopDisplay = null, expiryTimer = null;
  function clear() {
    generation++;
    stopDisplay?.(); stopDisplay = null;
    clearTimeout(expiryTimer); expiryTimer = null;
  }
  function receive(event) {
    const data = event.data;
    if (!data || typeof data !== 'object' || Array.isArray(data) ||
        Object.keys(data).sort().join(',') !== 'display_token,request_id,session_id,type' ||
        data.type !== 'SHOW_SESSION' || !opaque(data.session_id) || !opaque(data.display_token) || !opaque(data.request_id) ||
        typeof event.senderId !== 'string' || !event.senderId) return;
    clear();
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
