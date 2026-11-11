// DOM wiring for /play/. Game logic lives in lib/controller.js (unit tested).

import { createApi } from './lib/api.js';
import { CameraController } from './lib/camera.js';
import { ServerClock } from './lib/clock.js';
import { GameController } from './lib/controller.js';
import { FrameLoop, loadRecognizer } from './lib/recognizer.js';
import { takePairToken } from './lib/session.js';

const $ = (id) => document.getElementById(id);
const el = {
  app: $('app'),
  message: $('screen-message'),
  messageTitle: $('message-title'),
  messageBody: $('message-body'),
  game: $('screen-game'),
  scorePlayer: $('score-player'),
  scoreHermes: $('score-hermes'),
  scoreTies: $('score-ties'),
  round: $('round-number'),
  countdown: $('countdown'),
  result: $('result'),
  prompt: $('prompt'),
  commitment: $('commitment'),
  next: $('btn-next'),
  retry: $('btn-retry'),
  camIntro: $('camera-intro'),
  camStart: $('btn-camera-start'),
  camStop: $('btn-camera-stop'),
  camPreview: $('camera-preview'),
  camStatus: $('camera-status'),
  camMessage: $('camera-message'),
  video: $('video'),
  taps: Array.from(document.querySelectorAll('button[data-move]')),
  notice: $('notice'),
};

// Read the one-use pairing secret from the fragment and strip it immediately.
const pairToken = takePairToken(window.location, window.history);

const clock = new ServerClock();
let controller;
const api = createApi({ getToken: () => controller?.getToken() });
const camera = new CameraController({ onEnded: () => controller?.stopCamera('ended') });

controller = new GameController({
  api,
  clock,
  camera,
  storage: window.sessionStorage,
  subtle: window.crypto?.subtle,
  loadRecognizer: () => loadRecognizer(),
  createFrameLoop: (opts) => new FrameLoop(opts),
  onChange: () => scheduleRender(),
});

const OUTCOME = { player: 'You win!', hermes: 'Hermes wins', tie: 'Tie' };
const MOVE_LABEL = { rock: 'Rock ✊', paper: 'Paper ✋', scissors: 'Scissors ✌️' };
const SCREEN_TEXT = {
  loading: ['Connecting…', 'Getting your game ready.'],
  unpaired: ['Open your game link', 'Ask Hermes in Telegram to start Rock Paper Scissors, then open the play link it sends on this phone.'],
  pair_failed: ['That link has already been used or expired', 'Ask Hermes in Telegram for a fresh game link and open it on this phone.'],
  expired: ['Game over', 'This game session ended. Ask Hermes in Telegram for a new game.'],
};

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function render() {
  const vm = controller.viewModel();
  el.app.dataset.screen = vm.screen;
  const inGame = vm.screen === 'game';
  el.game.hidden = !inGame;
  el.message.hidden = inGame;
  if (!inGame) {
    const [title, body] = SCREEN_TEXT[vm.screen] ?? SCREEN_TEXT.loading;
    setText(el.messageTitle, title);
    setText(el.messageBody, body);
  }

  setText(el.scorePlayer, String(vm.score.player ?? 0));
  setText(el.scoreHermes, String(vm.score.hermes ?? 0));
  setText(el.scoreTies, String(vm.score.ties ?? 0));
  setText(el.round, String(vm.roundNumber || '–'));

  setText(el.countdown, vm.countdown ? vm.countdown.text : '');
  el.countdown.classList.toggle('shoot', Boolean(vm.countdown?.shoot));

  if (vm.result) {
    el.result.hidden = false;
    const r = vm.result;
    const key = `${r.round_id}|${r.player_move}|${r.hermes_move}|${r.outcome}|${r.input}`;
    if (el.result.dataset.key !== key) {
      el.result.dataset.key = key;
      el.result.replaceChildren(
        document.createTextNode(`You: ${MOVE_LABEL[r.player_move] ?? r.player_move} (${r.input === 'tap' ? 'tap' : 'camera'}) · Hermes: ${MOVE_LABEL[r.hermes_move] ?? r.hermes_move}`),
      );
      const out = document.createElement('span');
      out.className = 'outcome';
      out.textContent = OUTCOME[r.outcome] ?? '';
      el.result.append(out);
    }
  } else {
    el.result.hidden = true;
    el.result.dataset.key = '';
  }
  setText(el.prompt, vm.prompt);
  el.commitment.hidden = !vm.commitment || Boolean(vm.result);
  setText(el.commitment, vm.commitment ? `Hermes locked in (proof ${vm.commitment}…)` : '');

  el.next.disabled = !vm.canNext;
  setText(el.next, vm.phase === 'next_round' ? 'Next round' : 'Start round');
  el.retry.disabled = !vm.canRetry;
  for (const b of el.taps) b.disabled = !vm.canTap;

  const cam = vm.camera.status;
  const live = cam === 'on' || cam === 'loading' || cam === 'requesting';
  el.camIntro.hidden = live;
  el.camStart.disabled = live;
  el.camPreview.hidden = !(cam === 'on' || cam === 'loading');
  el.camStop.hidden = !live;
  setText(el.camStatus, cam === 'loading' ? 'Loading hand recognizer…' : cam === 'on' ? 'Camera on · on-device only' : '');
  el.camMessage.hidden = !vm.camera.message || live;
  setText(el.camMessage, vm.camera.message ?? '');

  el.notice.hidden = !vm.notice;
  setText(el.notice, vm.notice ?? '');
}

let renderQueued = false;
function scheduleRender() {
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(() => {
    renderQueued = false;
    render();
  });
}

// Countdown and the automatic decision run off the monotonic clock.
setInterval(() => {
  controller.tick();
  if (controller.state?.phase === 'countdown') scheduleRender();
}, 50);

el.next.addEventListener('click', () => controller.next());
el.retry.addEventListener('click', () => controller.retry());
el.camStart.addEventListener('click', () => controller.startCamera(el.video));
el.camStop.addEventListener('click', () => controller.stopCamera('user'));
for (const b of el.taps) b.addEventListener('click', () => controller.tap(b.dataset.move));

document.addEventListener('visibilitychange', () => controller.onVisibilityChange(document.visibilityState === 'hidden'));
window.addEventListener('pagehide', () => controller.onPageHide());
window.addEventListener('pageshow', (e) => {
  if (e.persisted) controller.onPageShow();
});

render();
controller.init({ pairToken });
