// The TV scene: landscape, glass, hands, scores and text as separate layers.
// Shared by the Cast receiver and the manual display page. All looks live in style.css;
// this file builds the layers once and then only flips attributes and text.
import {createHands} from './hands.js';

const cloud = (n, puffs) => `<svg class="cloud c${n}" viewBox="0 0 400 170" aria-hidden="true"><defs><linearGradient id="cloud-fill-${n}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff"/><stop offset=".65" stop-color="#f6fcff"/><stop offset="1" stop-color="#cbe8ff"/></linearGradient></defs><g fill="url(#cloud-fill-${n})"><rect x="50" y="104" width="300" height="52" rx="26"/>${puffs.map(([x, y, r]) => `<circle cx="${x}" cy="${y}" r="${r}"/>`).join('')}</g></svg>`;
const tree = (x, y, s = 1) => `<g transform="translate(${x} ${y}) scale(${s})"><circle cx="0" cy="-16" r="19" fill="#2f8f3f"/><circle cx="-17" cy="-4" r="15" fill="#2a8439"/><circle cx="17" cy="-5" r="16" fill="#37994a"/><circle cx="-5" cy="-21" r="9" fill="#5cba5a" opacity=".7"/></g>`;

const LAND = `<svg class="land-art" viewBox="0 0 1600 900" preserveAspectRatio="none" aria-hidden="true">
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
<g fill="#fff" opacity=".5"><ellipse cx="420" cy="668" rx="130" ry="2.5"/><ellipse cx="900" cy="640" rx="170" ry="2"/><ellipse cx="1240" cy="690" rx="120" ry="2.5"/><ellipse cx="690" cy="716" rx="90" ry="2.5"/><ellipse cx="240" cy="730" rx="110" ry="3"/><ellipse cx="1420" cy="742" rx="100" ry="3"/><ellipse cx="1010" cy="760" rx="140" ry="3"/></g>
<path fill="url(#grass)" d="M0 900V806C280 742 600 772 800 774S1320 742 1600 806V900Z"/>
<path fill="none" stroke="#e2ffad" stroke-width="4" opacity=".7" d="M0 806C280 742 600 772 800 774S1320 742 1600 806"/>
</svg>`;

const PHONE = `<svg class="icon phone" viewBox="0 0 100 100" aria-hidden="true"><rect x="29" y="8" width="42" height="84" rx="10" fill="#fff" fill-opacity=".5" stroke="#fff" stroke-width="5"/><rect x="36" y="20" width="28" height="50" rx="4" fill="#0a63b8" fill-opacity=".55"/><circle cx="50" cy="81" r="4.5" fill="#fff"/></svg>`;
const CHECK = `<svg class="icon check" viewBox="0 0 100 100" aria-hidden="true"><path d="M22 53l19 19 38-42" fill="none" stroke="#0a57a8" stroke-opacity=".5" stroke-width="17" stroke-linecap="round" stroke-linejoin="round"/><path class="check-stroke" d="M22 53l19 19 38-42" fill="none" stroke="#fff" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const RETRY = `<svg class="icon retry" viewBox="0 0 100 100" aria-hidden="true"><path d="M76 50a26 26 0 1 1-8.5-19.2" fill="none" stroke="#fff" stroke-width="10" stroke-linecap="round"/><path d="M72 14v20H52" fill="none" stroke="#fff" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

const seat = (who, name) => `<div class="seat ${who}"><div class="floaty"><div class="orb"><i class="glint"></i><canvas id="${who}-hand" width="2" height="2" aria-hidden="true"></canvas></div></div><span class="tag">Winner</span><div class="pill" id="${who}-move" aria-label="${name} move"></div></div>`;

const TEMPLATE = `
<div class="sky" aria-hidden="true"><div class="sun"></div>
${cloud(1, [[120, 104, 46], [190, 78, 62], [270, 96, 50], [320, 116, 36]])}
${cloud(2, [[110, 112, 38], [170, 86, 52], [245, 70, 60], [305, 104, 44]])}
${cloud(3, [[130, 100, 48], [215, 84, 58], [290, 108, 42]])}
${cloud(4, [[105, 110, 40], [175, 92, 50], [240, 76, 54], [300, 100, 46]])}
${cloud(5, [[140, 104, 44], [220, 88, 54], [295, 110, 40]])}
</div>
<div class="land">${LAND}
<div class="lake-fx" aria-hidden="true"><div class="shimmer"></div><div class="sweep"></div><i class="ripple r1"></i><i class="ripple r2"></i><i class="ripple r3"></i></div>
</div>
<div class="bubbles" aria-hidden="true">${[1, 2, 3, 4, 5, 6, 7].map(n => `<span class="bub b${n}"><i></i></span>`).join('')}</div>
<main class="stage">
<header class="title"><div class="logo">Terebi</div><div class="game">Rock Paper Scissors</div></header>
<section class="score you" aria-label="Your score"><span>You</span><strong id="player-score">0</strong></section>
<section class="score hermes" aria-label="Hermes score"><span>Hermes</span><strong id="hermes-score">0</strong></section>
${seat('player', 'Your')}${seat('hermes', 'Hermes')}
<div class="center" aria-hidden="true"><div class="disc">${PHONE}${CHECK}${RETRY}<span class="word" id="center-word">VS</span><span class="count" id="count"></span></div></div>
<section class="banner" aria-live="polite"><h1 id="headline"></h1><p id="guidance"></p></section>
<p class="foot left"><i class="dot"></i><span id="status"></span></p>
<p class="foot right"><span id="meta"></span><span id="mode"></span></p>
<button id="fullscreen" type="button">Fullscreen</button>
</main>`;

let shared = null;

// One scene per page. Sessions come and go; the landscape keeps moving.
export function getScene(doc = document) {
  if (shared) return shared;
  const root = doc.getElementById('tv');
  root.innerHTML = TEMPLATE;
  const el = id => doc.getElementById(id);
  const media = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  let forced = null, slow = false, last = null, celebrateTimer = 0, frames = 0, since = 0, probed = false;
  const hands = createHands([{canvas: el('player-hand'), mirrored: false}, {canvas: el('hermes-hand'), mirrored: true}]);

  const still = () => (forced ? forced === 'still' : slow || Boolean(media && media.matches));
  const mode = () => (hands.is3d() && !still() ? '3d' : 'static');
  function syncMotion() {
    root.dataset.motion = still() ? 'still' : 'full';
    el('mode').textContent = mode() === '3d' ? '3D' : 'Static';
    if (still()) hands.settle();
  }
  function restart(node, name) { // replay a one-shot CSS animation
    node.classList.remove(name);
    void node.offsetWidth;
    node.classList.add(name);
  }
  function text(id, value) {
    const node = el(id);
    if (node.textContent !== value) { node.textContent = value; return true; }
    return false;
  }

  function render(view, {instant = false} = {}) {
    if (instant) root.dataset.instant = '';
    root.dataset.scene = view.scene;
    root.dataset.center = view.center;
    if (view.outcome) root.dataset.outcome = view.outcome; else delete root.dataset.outcome;
    text('headline', view.headline);
    text('guidance', view.sub);
    text('meta', view.meta);
    text('center-word', view.center === 'tie' ? 'Tie' : 'VS');
    if (text('count', view.count) && view.count && !instant) restart(el('count'), 'beat');
    el('count').classList.toggle('long', view.count.length > 1);
    for (const who of ['player', 'hermes']) {
      const changed = text(`${who}-score`, String(view.score[who]));
      if (changed && last && !instant) restart(el(`${who}-score`), 'bump');
      text(`${who}-move`, view.moves ? view.moves[`${who}Label`] : '');
    }
    const key = view.moves ? view.moves.key : null;
    if (key !== (last && last.moves ? last.moves.key : null)) {
      // Both hands start on the same frame. Only a live reveal turns; a reconnect just shows them.
      if (view.moves) hands.show([view.moves.player, view.moves.hermes], view.scene === 'reveal' && !instant && !still());
      else hands.clear();
    }
    last = view;
    if (instant) { void root.offsetWidth; delete root.dataset.instant; }
  }

  function connection(kind, label) {
    root.dataset.connection = kind; // connecting | live | retrying | ended
    text('status', label);
  }
  function celebrate() { // once per pairing: the lake answers the phone
    if (still()) return;
    restart(root, 'rippling');
    clearTimeout(celebrateTimer);
    celebrateTimer = setTimeout(() => root.classList.remove('rippling'), 3200);
  }
  function setMotion(value) { forced = value === 'still' || value === 'full' ? value : null; syncMotion(); }

  doc.addEventListener('visibilitychange', () => {
    const hidden = doc.visibilityState === 'hidden';
    if (hidden) { root.dataset.paused = ''; hands.settle(); return; }
    delete root.dataset.paused;
    if (!probed) { frames = 0; since = 0; requestAnimationFrame(probe); }
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

  // A device that cannot hold the ambient loops gets the still scene instead of a stutter.
  function probe(now) {
    if (probed || doc.visibilityState === 'hidden') return;
    if (!since) since = now;
    frames++;
    if (now - since < 3000) { requestAnimationFrame(probe); return; }
    probed = true;
    if (frames * 1000 / (now - since) < 20) { slow = true; syncMotion(); }
  }
  setTimeout(() => requestAnimationFrame(probe), 1500);

  syncMotion();
  shared = {render, connection, celebrate, setMotion, mode, hideFullscreen: () => { button.hidden = true; }};
  return shared;
}
