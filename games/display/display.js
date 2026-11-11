import {bootView, countdownBeat, endedView, present} from './view.js';
import {getScene} from './scene.js';

// TV background music: one looping player shared by every TV display page.
// Starts as soon as the TV version opens; retries handle autoplay-blocked starts.
let music = null;
export function startMusic() {
  if (typeof Audio === 'undefined') return null; // headless test and non-DOM contexts
  if (!music) {
    music = new Audio('/display/hydrate.mp3');
    music.loop = true;
    music.volume = 0.5;
  }
  music.play().catch(() => {}); // no-op when blocked; the next open or render retries
  return music;
}
export function pauseMusic() { music?.pause(); }

const CONNECTED_MS = 2600; // how long "Phone connected" holds before settling on Ready

// Both manual mirroring and the Custom Receiver use this exact renderer.
export function startDisplay(credentials, {onRendered = () => {}, onFailure = () => {}, scene = getScene()} = {}) {
  let state = null, anchored = 0, request = null, timer = null, stopped = false;
  let painted = false, celebrateUntil = 0, beatFor = null, beat = 3;
  startMusic(); // every TV display open starts (or resumes) the shared background music
  scene.render(bootView(credentials ? 'Connecting to your game…' : 'Open the display link Hermes sent you.'), {instant: true});
  scene.connection('connecting', 'Connecting to the game service…');

  function end(sub) {
    stop();
    scene.render(endedView(sub, state));
    scene.connection('ended', 'Session ended');
    onFailure('session_ended');
  }
  function render() {
    if (!state || stopped) return;
    const now = state.server_time_ms + performance.now() - anchored;
    if (now >= state.expires_at_ms) return end('Ask Hermes for a new game.');
    let shown = null;
    if (state.phase === 'countdown') {
      // Polls re-anchor the clock; a beat already shown never comes back.
      const key = `${state.round_id}|${state.countdown_ends_at_ms}`;
      if (beatFor !== key) { beatFor = key; beat = 3; }
      shown = beat = Math.min(beat, countdownBeat(state, now));
    }
    // The first snapshot paints as-is: a reconnect to a paired session never replays a transition.
    scene.render(present(state, now, {celebrating: performance.now() < celebrateUntil, beat: shown}), {instant: !painted});
    painted = true;
  }
  async function poll() {
    if (stopped || !credentials) return;
    request = new AbortController();
    const timeout = setTimeout(() => request?.abort(), 4000);
    let delay = 400;
    try {
      const r = await fetch(`/v1/sessions/${encodeURIComponent(credentials.id)}`, {headers: {Authorization: `Bearer ${credentials.token}`}, cache: 'no-store', signal: request.signal});
      const data = await r.json();
      if (stopped) return;
      if (!r.ok || !data.ok) {
        if ([401, 404, 410].includes(r.status)) return end('Open a fresh display link from Hermes.');
        throw Error('connection');
      }
      if (data.state?.session_id !== credentials.id) throw Error('session_mismatch');
      if (!state || data.state.revision >= state.revision) {
        // The server confirming the pairing is the only trigger, so it plays once per pairing.
        if (state?.phase === 'waiting_for_player' && data.state.phase !== 'waiting_for_player') {
          celebrateUntil = performance.now() + CONNECTED_MS;
          scene.celebrate();
        }
        state = data.state; anchored = performance.now();
        render();
        if (!stopped) onRendered(state);
      }
      if (stopped) return;
      // This label only ever reports a poll that just succeeded.
      scene.connection('live', state.phase === 'waiting_for_player'
        ? 'Live · Waiting for a phone to pair'
        : 'Live · Phone paired');
    } catch {
      if (stopped) return;
      scene.connection('retrying', 'Reconnecting to the game service…');
      onFailure('display_unavailable');
      delay = 2000;
    } finally {
      clearTimeout(timeout); request = null;
      if (!stopped) timer = setTimeout(poll, delay);
    }
  }
  function stop() {
    stopped = true; pauseMusic();
    clearTimeout(timer); clearInterval(renderTimer); request?.abort();
    window.removeEventListener('pagehide', stop);
  }
  window.addEventListener('pagehide', stop);
  const renderTimer = setInterval(render, 100);
  if (credentials?.id && credentials?.token) poll();
  return stop;
}

// The receiver supplies its credential in memory, never via a URL or storage.
if (location.pathname.startsWith('/display/')) {
  const fragment = new URLSearchParams(location.hash.slice(1));
  let credentials;
  try {
    if (fragment.has('session') && fragment.has('token')) {
      credentials = {id: fragment.get('session'), token: fragment.get('token')};
      sessionStorage.setItem('terebi-display', JSON.stringify(credentials));
    } else credentials = JSON.parse(sessionStorage.getItem('terebi-display'));
  } catch { credentials = null; }
  // Optional #motion=still|full pins the still or animated scene for checks on a real screen.
  if (fragment.has('motion')) getScene().setMotion(fragment.get('motion'));
  history.replaceState(null, '', location.pathname);
  startDisplay(credentials);
}
