import {bootView, countdownBeat, endedView, present, RETRY_AFTER_MS} from './view.js';
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

const CONNECTED_MS = 2100; // "Phone connected" holds this long, then eases into Ready
const PROFILE_LIMIT = 24;  // on-device timing reports per display session
// Polling stays at 400 ms, except while the next thing the player does should show at once:
// a round about to start (for a bounded time) and a move about to resolve.
const POLL_MS = 400, POLL_SOON_MS = 200, POLL_RESOLVING_MS = 150, SOON_WINDOW_MS = 90000, RESOLVING_WINDOW_MS = 12000;

// Both manual mirroring and the Custom Receiver use this exact renderer.
export function startDisplay(credentials, {onRendered = () => {}, onFailure = () => {}, scene = getScene()} = {}) {
  let state = null, request = null, timer = null, beatTimer = null, stopped = false;
  let painted = false, celebrateUntil = 0, profiles = 0, profileTimer = null, phaseSince = 0;
  // Server clock = performance.now() + offset. The offset comes from the poll with the
  // shortest round trip seen recently, so a slow poll cannot shift the countdown.
  let offset = 0, samples = [];
  // A countdown keeps the offset it started with: its beats land exactly 1000 ms apart.
  let counting = null;
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
    clearTimeout(beatTimer);
    let now = performance.now() + offset;
    if (now >= state.expires_at_ms) return end('Ask Hermes for a new game.');
    let beat = null;
    if (state.phase === 'countdown') {
      const key = `${state.round_id}|${state.countdown_ends_at_ms}`;
      if (!counting || counting.key !== key) counting = {key, offset, beat: 3};
      now = performance.now() + counting.offset;
      beat = counting.beat = Math.min(counting.beat, countdownBeat(state, now)); // a beat never comes back
      // Wake exactly on the next beat (or the retry prompt) instead of waiting for the next tick.
      const left = state.countdown_ends_at_ms - now;
      const next = left > 0 ? left - (beat - 1) * 1000 : left + RETRY_AFTER_MS;
      if (next > 0) beatTimer = setTimeout(render, next + 1);
    } else counting = null;
    // The first snapshot paints as-is: a reconnect to a paired session never replays a transition.
    scene.render(present(state, now, {celebrating: performance.now() < celebrateUntil, beat}), {instant: !painted});
    painted = true;
  }
  // What the TV actually managed (frame timing, render mode): numbers only, to the session's own service.
  function report() {
    if (stopped || !scene.profile || profiles >= PROFILE_LIMIT) return;
    profiles++;
    fetch(`/v1/sessions/${encodeURIComponent(credentials.id)}/profile`, {method: 'POST', cache: 'no-store',
      headers: {Authorization: `Bearer ${credentials.token}`, 'Content-Type': 'application/json'},
      body: JSON.stringify(scene.profile())}).catch(() => {}); // never affects the game
  }
  function reportSoon(ms) { clearTimeout(profileTimer); profileTimer = setTimeout(report, ms); }
  async function poll() {
    if (stopped || !credentials) return;
    request = new AbortController();
    const timeout = setTimeout(() => request?.abort(), 4000);
    let delay = POLL_MS;
    try {
      const sent = performance.now();
      const r = await fetch(`/v1/sessions/${encodeURIComponent(credentials.id)}`, {headers: {Authorization: `Bearer ${credentials.token}`}, cache: 'no-store', signal: request.signal});
      const data = await r.json();
      const received = performance.now();
      if (stopped) return;
      if (!r.ok || !data.ok) {
        if ([401, 404, 410].includes(r.status)) return end('Open a fresh display link from Hermes.');
        throw Error('connection');
      }
      if (data.state?.session_id !== credentials.id) throw Error('session_mismatch');
      if (!state || data.state.revision >= state.revision) {
        samples.push({trip: received - sent, offset: data.state.server_time_ms - (sent + received) / 2});
        samples = samples.slice(-12);
        offset = samples.reduce((best, sample) => (sample.trip <= best.trip ? sample : best)).offset; // ties: newest
        const before = state?.phase;
        // The server confirming the pairing is the only trigger, so it plays once per pairing.
        if (before === 'waiting_for_player' && data.state.phase !== 'waiting_for_player') {
          celebrateUntil = performance.now() + CONNECTED_MS;
          scene.celebrate();
          setTimeout(render, CONNECTED_MS + 1);
        }
        if (before !== data.state.phase) phaseSince = performance.now();
        state = data.state;
        render();
        if (!stopped) onRendered(state);
        if (!before) reportSoon(12000);                                            // ambient scene
        else if (before !== state.phase && state.phase === 'ready') reportSoon(6000);  // after pairing
        else if (before !== state.phase && state.phase === 'next_round') reportSoon(1500); // after a round
      }
      if (stopped) return;
      // This label only ever reports a poll that just succeeded.
      const inPhase = performance.now() - phaseSince;
      if (['ready', 'next_round'].includes(state.phase) && inPhase < SOON_WINDOW_MS) delay = POLL_SOON_MS;
      else if (state.phase === 'countdown' && counting) {
        const sinceShoot = performance.now() + counting.offset - state.countdown_ends_at_ms;
        if (sinceShoot > -300 && sinceShoot < RESOLVING_WINDOW_MS) delay = POLL_RESOLVING_MS;
      }
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
    clearTimeout(timer); clearTimeout(beatTimer); clearTimeout(profileTimer); clearInterval(renderTimer); request?.abort();
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
