// The TV scene: landscape, glass, hands, scores and text as separate layers.
// Shared by the Cast receiver and the manual display page. All looks and motion live in
// style.css; this file builds the layers once, then only flips attributes and text.
// Every animation is a transform or opacity change on its own layer, so a Chromecast
// composites it without repainting. Nothing here forces layout during a round.
import {createHands, decodeHands, TURN_MS} from './hands.js';

const cloud = (n, puffs) => `<svg class="cloud c${n}" viewBox="0 0 400 170" aria-hidden="true"><defs><linearGradient id="cloud-fill-${n}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff"/><stop offset=".65" stop-color="#f6fcff"/><stop offset="1" stop-color="#cbe8ff"/></linearGradient></defs><g fill="url(#cloud-fill-${n})"><rect x="50" y="104" width="300" height="52" rx="26"/>${puffs.map(([x, y, r]) => `<circle cx="${x}" cy="${y}" r="${r}"/>`).join('')}</g></svg>`;
const tree = (x, y, s = 1) => `<g transform="translate(${x} ${y}) scale(${s})"><circle cx="0" cy="-16" r="19" fill="#2f8f3f"/><circle cx="-17" cy="-4" r="15" fill="#2a8439"/><circle cx="17" cy="-5" r="16" fill="#37994a"/><circle cx="-5" cy="-21" r="9" fill="#5cba5a" opacity=".7"/></g>`;

// Only the lower half of the screen holds land, so the layer is half a screen, not a whole one.
const LAND = `<svg class="land-art" viewBox="0 450 1600 450" preserveAspectRatio="none" aria-hidden="true">
<defs>
<linearGradient id="hill-far" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b9ea8f"/><stop offset="1" stop-color="#7fd06c"/></linearGradient>
<linearGradient id="hill-mid" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a4e562"/><stop offset="1" stop-color="#49b24a"/></linearGradient>
<linearGradient id="lake" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b5ecff"/><stop offset=".25" stop-color="#63c6f6"/><stop offset="1" stop-color="#1c84d8"/></linearGradient>
<linearGradient id="grass" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#b4ee63"/><stop offset=".35" stop-color="#6fce4c"/><stop offset="1" stop-color="#2f9f45"/></linearGradient>
</defs>
<path fill="url(#hill-far)" d="M0 548C190 470 370 498 560 548S900 468 1100 522S1450 462 1600 512V660H0Z"/>
<path fill="url(#hill-mid)" d="M0 512C160 478 340 520 500 612V670H0Z"/>
<path fill="url(#hill-mid)" d="M1600 496C1430 468 1240 528 1090 614V670H1600Z"/>
${tree(120, 532, 1.1)}${tree(205, 548, 0.9)}${tree(330, 574, 1)}${tree(700, 520, 0.7)}${tree(760, 516, 0.8)}${tree(1010, 532, 0.7)}${tree(1290, 556, 1)}${tree(1385, 534, 0.9)}${tree(1500, 510, 1.15)}
<rect y="606" width="1600" height="294" fill="url(#lake)"/>
<path fill="#58b85a" opacity=".3" d="M0 606H500C380 650 180 664 0 650Z"/>
<path fill="#58b85a" opacity=".3" d="M1600 606H1090C1220 652 1420 664 1600 648Z"/>
<path fill="#fff" opacity=".55" d="M0 604H1600V609H0Z"/>
<path fill="url(#grass)" d="M0 900V806C280 742 600 772 800 774S1320 742 1600 806V900Z"/>
<path fill="none" stroke="#e2ffad" stroke-width="4" opacity=".7" d="M0 806C280 742 600 772 800 774S1320 742 1600 806"/>
</svg>`;

const PHONE = `<svg class="icon phone" viewBox="0 0 100 100" aria-hidden="true"><rect x="29" y="8" width="42" height="84" rx="10" fill="#fff" fill-opacity=".5" stroke="#fff" stroke-width="5"/><rect x="36" y="20" width="28" height="50" rx="4" fill="#0a63b8" fill-opacity=".55"/><circle cx="50" cy="81" r="4.5" fill="#fff"/></svg>`;
const CHECK = `<svg class="icon check" viewBox="0 0 100 100" aria-hidden="true"><path d="M22 53l19 19 38-42" fill="none" stroke="#0a6a3c" stroke-opacity=".45" stroke-width="17" stroke-linecap="round" stroke-linejoin="round"/><path class="check-stroke" d="M22 53l19 19 38-42" fill="none" stroke="#fff" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const RETRY = `<svg class="icon" viewBox="0 0 100 100" aria-hidden="true"><path d="M76 50a26 26 0 1 1-8.5-19.2" fill="none" stroke="#fff" stroke-width="10" stroke-linecap="round"/><path d="M72 14v20H52" fill="none" stroke="#fff" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

const seat = (who, name) => `<div class="seat ${who}"><div class="floaty"><div class="orb"><i class="gloss"></i><i class="glint"></i><i class="shade"></i><canvas id="${who}-hand" width="2" height="2" aria-hidden="true"></canvas></div></div><span class="tag">Winner</span><div class="pill" id="${who}-move" aria-label="${name} move"></div></div>`;
const pair = (tag, id) => `<${tag} class="line on" id="${id}-a"></${tag}><${tag} class="line" id="${id}-b"></${tag}>`;

const TEMPLATE = `
<div class="sky" aria-hidden="true"><div class="sun"></div>
${cloud(1, [[120, 104, 46], [190, 78, 62], [270, 96, 50], [320, 116, 36]])}
${cloud(2, [[110, 112, 38], [170, 86, 52], [245, 70, 60], [305, 104, 44]])}
${cloud(3, [[130, 100, 48], [215, 84, 58], [290, 108, 42]])}
${cloud(4, [[105, 110, 40], [175, 92, 50], [240, 76, 54], [300, 100, 46]])}
${cloud(5, [[140, 104, 44], [220, 88, 54], [295, 110, 40]])}
</div>
<div class="land">${LAND}
<div class="lake-fx" aria-hidden="true"><div class="shimmer s1"></div><div class="shimmer s2"></div>${[1, 2, 3, 4, 5, 6].map(n => `<i class="spark k${n}"></i>`).join('')}<div class="sweep"></div></div>
</div>
<div class="bubbles" aria-hidden="true">${[1, 2, 3, 4, 5, 6, 7].map(n => `<span class="bub b${n}"><i></i></span>`).join('')}</div>
<main class="stage">
<header class="title"><div class="logo">Terebi</div><div class="game">Rock Paper Scissors</div></header>
<section class="score you" aria-label="Your score"><span>You</span><strong id="player-score">0</strong></section>
<section class="score hermes" aria-label="Hermes score"><span>Hermes</span><strong id="hermes-score">0</strong></section>
${seat('player', 'Your')}${seat('hermes', 'Hermes')}
<div class="center" aria-hidden="true">
<i class="ping p1"></i><i class="ping p2"></i><i class="wave w1"></i><i class="wave w2"></i><i class="wave w3"></i>
<div class="badge link"><i class="go"></i>${PHONE}${CHECK}</div>
<div class="badge versus"><span id="center-word">VS</span></div>
<div class="badge again">${RETRY}</div>
<div class="badge count"><i class="ring g3"></i><i class="ring g2"></i><i class="ring g1"></i><span class="n n3">3</span><span class="n n2">2</span><span class="n n1">1</span></div>
<div class="badge shoot"><i class="ring g0"></i><span>Shoot!</span></div>
</div>
<section class="banner" aria-live="polite"><i class="tint win"></i><i class="tint lose"></i><i class="tint warn"></i>${pair('h1', 'headline')}${pair('p', 'guidance')}</section>
<p class="foot left"><i class="dot"></i><span id="status"></span></p>
<p class="foot right"><span id="meta"></span><span id="mode"></span></p>
<button id="fullscreen" type="button">Fullscreen</button>
</main>`;

// The outcome waits for the hands to land. This is only the safety net if they never report it.
const LAND_LIMIT_MS = TURN_MS * 2;
const AMBIENT = new Set(['boot', 'waiting', 'ready', 'next']);
const WATCHED = {connected: 'pairing', countdown: 'countdown', reveal: 'reveal'};
let shared = null;

// One scene per page. Sessions come and go; the landscape keeps moving.
export function getScene(doc = document) {
  if (shared) return shared;
  const root = doc.getElementById('tv');
  root.innerHTML = TEMPLATE;
  const el = id => doc.getElementById(id);
  const media = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  const hands = createHands([{canvas: el('player-hand'), mirrored: false}, {canvas: el('hermes-hand'), mirrored: true}]);
  let forced = null, tier = 'full', last = null, shown = null, ready = false;
  let landing = false, landTimer = 0, held = null, rippleTimer = 0, primed = false, primeTimer = 0;

  const still = () => (forced ? forced === 'still' : tier === 'still' || Boolean(media && media.matches));
  const mode = () => (hands.is3d() && !still() ? '3d' : 'static');

  // --- attribute, text and crossfade helpers: every write is skipped when nothing changed ---
  const attrs = {};
  function attr(name, value) {
    if (attrs[name] === value) return;
    attrs[name] = value;
    if (value === null) root.removeAttribute(`data-${name}`); else root.setAttribute(`data-${name}`, value);
  }
  const texts = {};
  function text(id, value) {
    if (texts[id] === value) return false;
    texts[id] = value; el(id).textContent = value;
    return true;
  }
  const lines = {};
  function say(id, value) { // crossfade between two stacked lines instead of swapping text in place
    const line = lines[id] || (lines[id] = {value: '', front: 'a'});
    if (line.value === value) return;
    line.value = value;
    const back = line.front === 'a' ? 'b' : 'a';
    el(`${id}-${back}`).textContent = value;
    el(`${id}-${back}`).classList.add('on');
    el(`${id}-${line.front}`).classList.remove('on');
    line.front = back;
  }
  function restart(node, name) { // replay a one-shot CSS animation; used once per pairing only
    node.classList.remove(name);
    void node.offsetWidth;
    node.classList.add(name);
  }

  function apply(view) {
    shown = view;
    attr('scene', view.scene);
    attr('center', view.center);
    attr('count', view.center === 'count' ? view.count : null);
    attr('reveal', view.moves ? (view.landing ? 'turning' : 'landed') : null);
    attr('outcome', view.outcome || null);
    say('headline', view.headline);
    say('guidance', view.sub);
    text('meta', view.meta);
    text('center-word', view.center === 'tie' ? 'Tie' : 'VS');
    for (const who of ['player', 'hermes']) {
      const first = texts[`${who}-score`] === undefined;
      if (text(`${who}-score`, String(view.score[who])) && !first && !view.instant) restart(el(`${who}-score`), 'bump');
      text(`${who}-move`, view.moves ? view.moves[`${who}Label`] : texts[`${who}-move`] || '');
    }
  }

  function render(view, {instant = false} = {}) {
    if (instant) root.setAttribute('data-instant', '');
    const key = view.moves ? view.moves.key : null, before = last && last.moves ? last.moves.key : null;
    if (key !== before) {
      clearTimeout(landTimer); landing = false;
      if (view.moves) {
        // Both hands start on the same frame. Only a live reveal turns; a reconnect just shows them.
        const turn = view.scene === 'reveal' && !instant && !still();
        if (turn) {
          watch('reveal');
          held = last || view;
          landing = true;
          const landed = () => { if (!landing) return; landing = false; clearTimeout(landTimer); if (last) apply(last); };
          landTimer = setTimeout(landed, LAND_LIMIT_MS);
          hands.show([view.moves.player, view.moves.hermes], true, landed);
        } else hands.show([view.moves.player, view.moves.hermes], false);
      } else hands.clear();
    } else if (last && view.scene !== last.scene && WATCHED[view.scene]) watch(WATCHED[view.scene]);
    // A reveal can only follow the countdown: get the hand canvases drawing shortly before it.
    // It starts while the 2 is standing still, where a cold-start hitch would not show.
    const near = view.scene === 'shoot' || (view.scene === 'countdown' && view.count !== '3');
    if (near !== primed) {
      primed = near;
      clearTimeout(primeTimer);
      if (near && !still()) primeTimer = setTimeout(() => hands.prime(true), view.count === '2' ? 450 : 0);
      else if (!view.moves) hands.prime(false);
    }
    last = view;
    // While the hands turn, the banner steps aside and the score keeps its old value.
    apply(landing
      ? {...view, landing: true, outcome: null, headline: '', sub: '', center: 'vs', score: held.score, meta: held.meta}
      : {...view, instant});
    if (instant) { void root.offsetWidth; root.removeAttribute('data-instant'); }
  }

  function connection(kind, label) {
    attr('connection', kind); // connecting | live | retrying | ended
    text('status', label);
  }
  function celebrate() { // once per pairing: a ripple leaves the phone icon and crosses the lake
    if (still()) return;
    restart(root, 'rippling');
    clearTimeout(rippleTimer);
    rippleTimer = setTimeout(() => root.classList.remove('rippling'), 3000);
  }

  // --- frame timing: decides the tier and feeds the on-device profile -----------------------
  // Each window records rAF gaps: [frames, mean ms, worst ms, frames slower than 50 ms].
  const windows = {};
  let sampling = null, sampler = 0, ambientTimer = 0, goodWindows = 0;
  function finish() {
    if (!sampling) return;
    const {label, frames, total, worst, slow} = sampling;
    sampling = null;
    if (frames < 5) return;
    const mean = total / frames;
    windows[label] = [frames, Math.round(mean), Math.round(worst), slow];
    if (label === 'ambient') judge(mean, slow / frames);
    syncMotion();
  }
  function watch(label, ms = label === 'ambient' ? 3000 : 3600) {
    if (still() || doc.visibilityState === 'hidden') return;
    if (sampling && sampling.label !== 'ambient' && label === 'ambient') return;
    if (sampling) finish();
    sampling = {label, frames: 0, total: 0, worst: 0, slow: 0, previous: 0, until: performance.now() + ms};
    cancelAnimationFrame(sampler);
    const step = now => {
      const s = sampling;
      if (!s) return;
      if (s.previous) { const gap = now - s.previous; s.frames++; s.total += gap; s.worst = Math.max(s.worst, gap); if (gap > 50) s.slow++; }
      s.previous = now;
      if (now < s.until) sampler = requestAnimationFrame(step); else finish();
    };
    sampler = requestAnimationFrame(step);
  }
  // Background effects go first, then all motion. The tier never climbs back within a page.
  function judge(mean, slowShare) {
    if (forced) return;
    const struggling = mean > 30 || slowShare > 0.15; // under ~33 fps, or stuttering
    if (!struggling) { goodWindows++; return; }
    goodWindows = 0;
    if (tier === 'full') tier = 'lite';
    else if (tier === 'lite' && mean > 55) tier = 'still'; // under ~18 fps even without effects
  }
  function ambientLoop() {
    clearTimeout(ambientTimer);
    ambientTimer = setTimeout(() => {
      if (shown && AMBIENT.has(shown.scene) && !sampling) watch('ambient');
      ambientLoop();
    }, goodWindows >= 2 ? 20000 : 5000);
  }

  function syncMotion() {
    attr('motion', still() ? 'still' : 'full');
    attr('tier', tier === 'lite' ? 'lite' : 'full');
    const fps = windows.ambient ? ` · ${Math.min(60, Math.round(1000 / Math.max(1, windows.ambient[1])))} fps` : '';
    text('mode', !ready ? '' : mode() === '3d' ? `3D${tier === 'lite' ? ' lite' : ''}${fps}` : 'Static');
    if (still()) { hands.settle(); cancelAnimationFrame(sampler); sampling = null; }
  }
  function setMotion(value) { forced = value === 'still' || value === 'full' ? value : null; syncMotion(); }

  doc.addEventListener('visibilitychange', () => {
    if (doc.visibilityState === 'hidden') { root.setAttribute('data-paused', ''); hands.settle(); cancelAnimationFrame(sampler); sampling = null; return; }
    root.removeAttribute('data-paused');
  });
  if (media && media.addEventListener) media.addEventListener('change', syncMotion);
  window.addEventListener('resize', () => hands.redraw());

  const button = el('fullscreen');
  button.onclick = async () => {
    try {
      if (!doc.fullscreenElement) await doc.documentElement.requestFullscreen();
      else await doc.exitFullscreen();
    } catch { text('status', 'Use Chrome’s fullscreen menu, then cast this tab.'); }
  };

  // The baked hands arrive after first paint; until then (or on failure) the flat rig stands in.
  (async () => {
    let meshes = null;
    try {
      const response = await fetch('/display/hands.json', {cache: 'no-store'});
      if (response.ok) meshes = decodeHands(await response.json());
    } catch { meshes = null; }
    hands.setMeshes(meshes);
    ready = true;
    syncMotion();
    setTimeout(() => { if (!still() && doc.visibilityState !== 'hidden') hands.rehearse(); }, 2500);
    setInterval(() => { if (!still() && doc.visibilityState !== 'hidden') hands.pulse(); }, 400);
  })();

  syncMotion();
  setTimeout(() => watch('ambient'), 1500);
  ambientLoop();

  // What this screen actually did: numbers only, for the profile the display reports.
  function profile() {
    const turn = hands.lastTurn();
    return {
      mode: mode(), tier: still() ? 'still' : tier, turn: hands.turnStyle(),
      ...Object.fromEntries(Object.entries(windows).map(([label, numbers]) => [label, numbers.map(v => Math.min(60000, v))])),
      ...(turn ? {hand: [turn.frames, turn.mean, turn.worst].map(v => Math.min(60000, v))} : {}),
      screen: [window.innerWidth | 0, window.innerHeight | 0, Math.round((window.devicePixelRatio || 1) * 100)],
    };
  }

  shared = {render, connection, celebrate, setMotion, mode, profile, hideFullscreen: () => { button.hidden = true; }};
  return shared;
}
