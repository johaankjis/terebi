import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ApiError } from '../src/lib/api.js';
import { CameraController } from '../src/lib/camera.js';
import { ServerClock } from '../src/lib/clock.js';
import { GameController } from '../src/lib/controller.js';
import { deferred, domError, fakeMediaDevices, fakeStream, fakeVideo, flush, noTimers } from './helpers.js';

// Server epoch is deliberately far from any device clock; the phone's Date.now()
// is never consulted. Local monotonic time starts at 50_000.
const SERVER_T0 = 1_900_000_000_000;
const MONO_T0 = 50_000;

function state(over = {}) {
  return {
    session_id: 's1',
    revision: 1,
    server_time_ms: SERVER_T0,
    expires_at_ms: SERVER_T0 + 30 * 60_000,
    phase: 'ready',
    round_id: 'r1',
    round_number: 1,
    countdown_ends_at_ms: null,
    accept_until_ms: null,
    hermes_commitment: 'c0ffee'.repeat(10),
    result: null,
    score: { player: 0, hermes: 0, ties: 0, rounds: 0 },
    ...over,
  };
}

const countdown = (over = {}) =>
  state({ phase: 'countdown', revision: 2, countdown_ends_at_ms: SERVER_T0 + 3000, accept_until_ms: SERVER_T0 + 13_000, ...over });

function setup({ storedSession = true, timers = noTimers } = {}) {
  let mono = MONO_T0;
  const clock = new ServerClock({ now: () => mono });
  clock.sample(SERVER_T0, MONO_T0 - 10, MONO_T0 + 10); // offset = SERVER_T0 - MONO_T0
  const calls = [];
  const replies = { move: null, tap: null, next: null, retry: null };
  const api = {
    getState: async () => ({ data: { ok: true, state: c.state }, sentMono: mono, recvMono: mono }),
    pair: async () => ({ data: { ok: true, session_id: 's1', player_token: 'p1', state: state() } }),
  };
  for (const name of ['move', 'tap', 'next', 'retry']) {
    api[name] = (...args) => {
      calls.push({ name, args });
      if (replies[name]) return replies[name](...args);
      return Promise.resolve({ data: { ok: true, state: c.state }, sentMono: mono, recvMono: mono });
    };
  }
  const md = fakeMediaDevices();
  const camera = new CameraController({ mediaDevices: md });
  const storage = new Map();
  const store = { getItem: (k) => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v), removeItem: (k) => storage.delete(k) };
  if (storedSession) store.setItem('terebi.rps.player.v1', JSON.stringify({ session_id: 's1', player_token: 'p1' }));
  const loops = [];
  let recognizerLoads = 0;
  let loadRecognizer = async () => {
    recognizerLoads += 1;
    return { recognize: () => null };
  };
  const c = new GameController({
    api,
    clock,
    camera,
    storage: store,
    timers,
    loadRecognizer: () => loadRecognizer(),
    createFrameLoop: (opts) => {
      const loop = { opts, running: false, start() { this.running = true; }, stop() { this.running = false; } };
      loops.push(loop);
      return loop;
    },
  });
  c.session = { session_id: 's1', player_token: 'p1' };
  c.screen = 'game';
  return {
    c,
    api,
    calls,
    replies,
    md,
    camera,
    store,
    loops,
    get recognizerLoads() {
      return recognizerLoads;
    },
    setLoader(fn) {
      loadRecognizer = fn;
    },
    setMono(v) {
      mono = v;
    },
    atServer(ms) {
      mono = ms - SERVER_T0 + MONO_T0;
      return mono;
    },
  };
}

async function cameraOn(h, { practice = false } = {}) {
  const video = fakeVideo();
  const p = h.c.startCamera(video);
  const stream = fakeStream();
  h.md.pending.resolve(stream);
  assert.equal(await p, true);
  if (!practice) h.c.finishPractice();
  return { video, stream, loop: h.loops.at(-1) };
}

/** Feed frames around the shared countdown end, in server time. */
function feed(h, loop, fromServer, toServer, move, { score = 0.9, step = 66, hand = true } = {}) {
  for (let t = fromServer; t <= toServer; t += step) {
    loop.opts.onFrame({ t: h.atServer(t), hand, move, score });
  }
}

test('countdown is derived from server_time anchor, not device clock', () => {
  const h = setup();
  h.c.applyState(countdown());
  h.atServer(SERVER_T0 + 100);
  assert.equal(h.c.viewModel().countdown.text, '3');
  h.atServer(SERVER_T0 + 1500);
  assert.equal(h.c.viewModel().countdown.text, '2');
  h.atServer(SERVER_T0 + 2999);
  assert.equal(h.c.viewModel().countdown.text, '1');
  h.atServer(SERVER_T0 + 3000);
  assert.deepEqual(h.c.viewModel().countdown, { text: 'Shoot!', shoot: true });
});

test('camera move is decided from stable frames at countdown end and sent exactly once', async () => {
  const h = setup();
  h.c.applyState(countdown());
  const { loop } = await cameraOn(h);
  const end = SERVER_T0 + 3000;
  feed(h, loop, end - 2000, end - 500, 'paper'); // older frames outside the window
  feed(h, loop, end - 380, end + 440, 'rock');
  h.atServer(end + 200);
  h.c.tick();
  assert.equal(h.calls.length, 0, 'no decision before the settle window closes');
  h.atServer(end + 450);
  h.c.tick();
  h.c.tick();
  h.c.tick();
  await flush();
  const moves = h.calls.filter((x) => x.name === 'move');
  assert.equal(moves.length, 1);
  assert.deepEqual(moves[0].args.slice(0, 3), ['s1', 'r1', 'rock']);
  assert.equal(h.calls.filter((x) => x.name === 'tap').length, 0);
  assert.equal(h.c.currentRound().status, 'accepted');
  assert.equal(h.c.canTap(), false, 'tap cannot double-submit a camera round');
});

test('clock offset: decision waits for the SERVER deadline even if poll arrived late', async () => {
  const h = setup();
  // A second clock sample showing the server is 700 ms ahead of what we thought.
  h.c.clock.samples = [];
  h.c.clock.sample(SERVER_T0 + 700, MONO_T0 - 1, MONO_T0 + 1);
  h.c.applyState(countdown());
  const { loop } = await cameraOn(h);
  // Local monotonic time where the server deadline lands is 700 ms earlier than before.
  const endMono = h.c.clock.toMono(SERVER_T0 + 3000);
  for (let t = endMono - 300; t <= endMono + 440; t += 60) loop.opts.onFrame({ t, hand: true, move: 'scissors', score: 0.95 });
  h.setMono(endMono + 149);
  h.c.tick();
  assert.equal(h.calls.length, 0);
  h.setMono(endMono + 450);
  h.c.tick();
  await flush();
  assert.equal(h.calls[0].args[2], 'scissors');
});

test('no hand or low confidence shows a retry prompt and sends nothing', async () => {
  for (const [frames, reason] of [
    [{ hand: false, move: null, score: 0 }, 'no_hand'],
    [{ hand: true, move: 'rock', score: 0.3 }, 'low_confidence'],
  ]) {
    const h = setup();
    h.c.applyState(countdown());
    const { loop } = await cameraOn(h);
    const end = SERVER_T0 + 3000;
    feed(h, loop, end - 300, end + 890, frames.move, frames);
    h.atServer(end + 900);
    h.c.tick();
    await flush();
    assert.equal(h.calls.length, 0);
    assert.equal(h.c.currentRound().status, 'retry_prompt');
    assert.equal(h.c.currentRound().reason, reason);
    assert.match(h.c.viewModel().prompt, /Retry/);
    assert.deepEqual(h.c.viewModel().score, { player: 0, hermes: 0, ties: 0, rounds: 0 });
    assert.equal(h.c.canRetry(), true);
  }
});

test('Retry posts {round_id}; the new round_id gets its own single automatic decision; old ID is stale', async () => {
  const h = setup();
  h.c.applyState(countdown());
  const { loop } = await cameraOn(h);
  h.atServer(SERVER_T0 + 3900);
  h.c.tick(); // no frames: retry prompt
  assert.equal(h.c.currentRound().status, 'retry_prompt');
  const retried = countdown({ revision: 3, round_id: 'r1b', server_time_ms: SERVER_T0 + 4000, countdown_ends_at_ms: SERVER_T0 + 7000, accept_until_ms: SERVER_T0 + 17_000 });
  h.replies.retry = async () => ({ data: { ok: true, state: retried }, sentMono: h.atServer(SERVER_T0 + 4000), recvMono: h.atServer(SERVER_T0 + 4000) });
  assert.equal(await h.c.retry(), true);
  assert.deepEqual(h.calls.at(-1), { name: 'retry', args: ['s1', 'r1'] });
  assert.equal(h.c.state.round_id, 'r1b');
  assert.equal(h.c.state.round_number, 1, 'logical round preserved');
  // Old round cannot be submitted any more.
  assert.equal(h.c.canTap(), false);
  feed(h, loop, SERVER_T0 + 6700, SERVER_T0 + 7440, 'paper');
  h.atServer(SERVER_T0 + 7450);
  h.c.tick();
  h.c.tick();
  await flush();
  const moves = h.calls.filter((x) => x.name === 'move');
  assert.equal(moves.length, 1);
  assert.deepEqual(moves[0].args.slice(0, 3), ['s1', 'r1b', 'paper']);
});

test('stale state revisions and other sessions are ignored', () => {
  const h = setup();
  h.c.applyState(countdown({ revision: 5 }));
  assert.equal(h.c.applyState(state({ revision: 4, phase: 'ready' })), false);
  assert.equal(h.c.state.phase, 'countdown');
  assert.equal(h.c.applyState(countdown({ revision: 9, session_id: 'other' })), false);
});

test('a move response for an old round does not trigger a second submission', async () => {
  const h = setup();
  h.c.applyState(countdown());
  const { loop } = await cameraOn(h);
  const gate = deferred();
  h.replies.move = () => gate.promise;
  feed(h, loop, SERVER_T0 + 2700, SERVER_T0 + 3440, 'rock');
  h.atServer(SERVER_T0 + 3450);
  h.c.tick();
  // Meanwhile the poll shows the server already moved on to reveal.
  h.c.applyState(state({ revision: 7, phase: 'reveal', round_id: 'r1', result: { round_id: 'r1', player_move: 'rock', hermes_move: 'paper', outcome: 'hermes', input: 'camera', nonce: 'n' }, score: { player: 0, hermes: 1, ties: 0, rounds: 1 } }));
  gate.resolve({ data: { ok: true, state: countdown({ revision: 3 }) }, sentMono: 0, recvMono: 0 });
  await flush();
  assert.equal(h.c.state.phase, 'reveal', 'older revision from the move response ignored');
  for (let i = 0; i < 5; i++) h.c.tick();
  assert.equal(h.calls.filter((x) => x.name === 'move').length, 1);
});

test('network failure after sending is never retried automatically', async () => {
  const h = setup();
  h.c.applyState(countdown());
  const { loop } = await cameraOn(h);
  h.replies.move = async () => Promise.reject(new ApiError(0, 'network', null, 'network'));
  feed(h, loop, SERVER_T0 + 2700, SERVER_T0 + 3440, 'rock');
  h.atServer(SERVER_T0 + 3450);
  h.c.tick();
  await flush();
  for (let i = 0; i < 5; i++) h.c.tick();
  assert.equal(h.c.currentRound().status, 'uncertain');
  assert.equal(h.calls.filter((x) => x.name === 'move').length, 1);
});

test('Stop camera releases tracks, stops inference and cancels the pending automatic submission', async () => {
  const h = setup();
  h.c.applyState(countdown());
  const { loop, stream, video } = await cameraOn(h);
  feed(h, loop, SERVER_T0 + 2600, SERVER_T0 + 2990, 'rock');
  h.c.stopCamera('user');
  assert.ok(stream.allStopped);
  assert.equal(loop.running, false);
  assert.equal(video.srcObject, null);
  assert.equal(h.c.window.frames.length, 0);
  // A late frame from the stopped loop is ignored.
  loop.opts.onFrame({ t: h.atServer(SERVER_T0 + 3100), hand: true, move: 'rock', score: 1 });
  assert.equal(h.c.window.frames.length, 0);
  h.atServer(SERVER_T0 + 3500);
  h.c.tick();
  await flush();
  assert.equal(h.calls.filter((x) => x.name === 'move').length, 0);
  assert.equal(h.c.currentRound().status, 'no_camera');
  assert.equal(h.c.canTap(), true, 'tap fallback still available');
});

test('Stop aborts an in-flight camera submission', async () => {
  const h = setup();
  h.c.applyState(countdown());
  const { loop } = await cameraOn(h);
  let signal;
  h.replies.move = (_s, _r, _m, opts) => {
    signal = opts.signal;
    return new Promise((_, rej) => opts.signal.addEventListener('abort', () => rej(new ApiError(0, 'aborted', null, 'aborted'))));
  };
  feed(h, loop, SERVER_T0 + 2700, SERVER_T0 + 3440, 'paper');
  h.atServer(SERVER_T0 + 3450);
  h.c.tick();
  h.c.stopCamera('user');
  await flush();
  assert.equal(signal.aborted, true);
  assert.equal(h.c.currentRound().status, 'cancelled');
});

test('pagehide and visibility hidden release tracks; returning does not re-request permission', async () => {
  for (const leave of ['pagehide', 'hidden']) {
    const h = setup();
    h.c.applyState(countdown());
    const { stream } = await cameraOn(h);
    if (leave === 'pagehide') h.c.onPageHide();
    else h.c.onVisibilityChange(true);
    assert.ok(stream.allStopped, leave);
    assert.equal(h.c.cameraStatus, 'off');
    h.c.onVisibilityChange(false);
    h.c.onPageShow();
    await flush();
    assert.equal(h.md.calls.length, 1, 'no silent permission request');
    assert.match(h.c.viewModel().camera.message, /camera/i);
  }
});

test('permission prompt still pending when the page hides resolves safely', async () => {
  const h = setup();
  const video = fakeVideo();
  const p = h.c.startCamera(video);
  h.c.onPageHide();
  const late = fakeStream();
  h.md.pending.resolve(late);
  assert.equal(await p, false);
  assert.ok(late.allStopped);
  assert.equal(video.srcObject, null);
  assert.equal(h.c.cameraStatus, 'off');
  assert.equal(h.loops.length, 0, 'no inference started');
});

test('Stop while the model is loading never starts inference', async () => {
  const h = setup();
  const gate = deferred();
  h.setLoader(() => gate.promise);
  const p = h.c.startCamera(fakeVideo());
  h.md.pending.resolve(fakeStream());
  await flush();
  assert.equal(h.c.cameraStatus, 'loading');
  h.c.stopCamera('user');
  gate.resolve({ recognize: () => null });
  assert.equal(await p, false);
  assert.equal(h.loops.length, 0);
});

test('denied and missing camera show guidance, keep tap fallback, and do not retry', async () => {
  for (const [err, code] of [['NotAllowedError', 'denied'], ['NotFoundError', 'missing'], ['NotReadableError', 'busy']]) {
    const h = setup();
    h.c.applyState(countdown());
    const p = h.c.startCamera(fakeVideo());
    h.md.pending.reject(domError(err));
    assert.equal(await p, false);
    const vm = h.c.viewModel();
    assert.equal(vm.camera.status, 'off');
    assert.equal(vm.camera.error, code);
    assert.ok(vm.camera.message.length > 10);
    h.atServer(SERVER_T0 + 3100);
    assert.equal(h.c.viewModel().canTap, true);
    await flush();
    assert.equal(h.md.calls.length, 1);
  }
});

test('model load failure releases the camera and allows a later explicit retry', async () => {
  const h = setup();
  h.setLoader(async () => {
    throw new Error('wasm failed');
  });
  const video = fakeVideo();
  const p = h.c.startCamera(video);
  const s = fakeStream();
  h.md.pending.resolve(s);
  assert.equal(await p, false);
  assert.ok(s.allStopped);
  assert.equal(h.c.viewModel().camera.error, 'model');
  h.setLoader(async () => ({ recognize: () => null }));
  const p2 = h.c.startCamera(video);
  h.md.pending.resolve(fakeStream());
  assert.equal(await p2, true);
});

test('tap fallback is separate: only after Shoot, uses /tap, works with camera off', async () => {
  const h = setup();
  h.c.applyState(countdown());
  h.atServer(SERVER_T0 + 2000);
  assert.equal(h.c.canTap(), false);
  assert.equal(await h.c.tap('rock'), false);
  h.atServer(SERVER_T0 + 3010);
  assert.equal(await h.c.tap('lizard'), false);
  assert.equal(await h.c.tap('paper'), true);
  assert.deepEqual(h.calls.map((x) => [x.name, ...x.args.slice(0, 3)]), [['tap', 's1', 'r1', 'paper']]);
  assert.equal(await h.c.tap('rock'), false, 'no second submission for the same round_id');
  // The camera auto-decision never fires for a round already tapped.
  h.atServer(SERVER_T0 + 3500);
  h.c.tick();
  assert.equal(h.calls.filter((x) => x.name === 'move').length, 0);
});

test('tap after the acceptance window is refused', async () => {
  const h = setup();
  h.c.applyState(countdown());
  h.atServer(SERVER_T0 + 13_001);
  assert.equal(await h.c.tap('rock'), false);
  h.c.tick();
  assert.equal(h.c.currentRound().status, 'timed_out');
  assert.equal(h.calls.length, 0);
});

test('Next round posts {round_id} only from ready/next_round and is not doubled', async () => {
  const h = setup();
  h.c.applyState(state());
  const gate = deferred();
  h.replies.next = () => gate.promise;
  const a = h.c.next();
  const b = h.c.next();
  gate.resolve({ data: { ok: true, state: countdown() }, sentMono: 0, recvMono: 0 });
  assert.equal(await a, true);
  assert.equal(await b, false);
  assert.deepEqual(h.calls, [{ name: 'next', args: ['s1', 'r1'] }]);
  assert.equal(h.c.canNext(), false, 'not during countdown');
});

test("Hermes' move is never shown before the server reveal", () => {
  const h = setup();
  // Even if a buggy server put a result on a countdown state, the page hides it.
  h.c.applyState(countdown({ result: { round_id: 'r1', player_move: 'rock', hermes_move: 'paper', outcome: 'hermes', input: 'camera', nonce: 'n' } }));
  assert.equal(h.c.viewModel().result, null);
  h.c.applyState(state({ revision: 9, phase: 'reveal', result: { round_id: 'r1', player_move: 'rock', hermes_move: 'paper', outcome: 'hermes', input: 'camera', nonce: 'n' }, score: { player: 0, hermes: 1, ties: 0, rounds: 1 } }));
  const vm = h.c.viewModel();
  assert.equal(vm.result.hermes_move, 'paper');
  assert.deepEqual(vm.score, { player: 0, hermes: 1, ties: 0, rounds: 1 }, 'score is the server score');
});

test('session expiry stops camera, clears storage and stops play', async () => {
  const h = setup();
  h.c.applyState(countdown());
  const { stream } = await cameraOn(h);
  h.atServer(SERVER_T0 + 30 * 60_000);
  h.c.tick();
  assert.ok(stream.allStopped);
  assert.equal(h.c.screen, 'expired');
  assert.equal(h.store.getItem('terebi.rps.player.v1'), null);
  assert.equal(h.c.canTap(), false);
  assert.equal(h.c.canNext(), false);
});

test('a 410 from the server expires the session', async () => {
  const h = setup();
  h.c.applyState(countdown());
  h.replies.tap = async () => Promise.reject(new ApiError(410, 'expired', null, 'expired'));
  h.atServer(SERVER_T0 + 3100);
  await h.c.tap('rock');
  assert.equal(h.c.screen, 'expired');
});

test('init pairs from fragment once and starts polling with the stored session', async () => {
  const h = setup({ storedSession: false });
  h.c.session = null;
  h.c.screen = 'loading';
  await h.c.init({ pairToken: 'T'.repeat(43) });
  assert.equal(h.c.screen, 'game');
  assert.equal(h.c.getToken(), 'p1');
  assert.ok(h.store.getItem('terebi.rps.player.v1'));
  h.c.poller.stop();
});

test('model is loaded once and reused across camera sessions', async () => {
  const h = setup();
  await cameraOn(h);
  h.c.stopCamera('user');
  await cameraOn(h);
  assert.equal(h.recognizerLoads, 1);
});


test('practice recognizes all three shapes locally and never submits a round', async () => {
  const h = setup(); h.c.applyState(countdown());
  const { loop } = await cameraOn(h, { practice: true });
  let t = SERVER_T0;
  for (const move of ['rock', 'paper', 'scissors']) {
    feed(h, loop, t, t + 900, move); t += 1200;
  }
  h.atServer(SERVER_T0 + 3500); h.c.tick();
  assert.deepEqual(h.c.viewModel().camera.seen, ['rock', 'paper', 'scissors']);
  assert.equal(h.calls.length, 0);
  assert.equal(h.c.viewModel().camera.practice, true);
  assert.equal(h.c.finishPractice(), true);
  assert.equal(h.c.window.frames.length, 0);
});

test('only latest diagnostics retain landmarks, and Stop removes them', async () => {
  const h = setup(); const { loop } = await cameraOn(h, { practice: true });
  const diagnostics = { status: 'recognized', move: 'rock', score: 0.9, gesture: 'Closed_Fist', landmarks: [{x: .2, y: .3}] };
  loop.opts.onFrame({t: MONO_T0, hand: true, move: 'rock', score: .9, diagnostics});
  assert.deepEqual(h.c.viewModel().camera.diagnostics.landmarks, diagnostics.landmarks);
  assert.equal(h.c.window.frames[0].diagnostics, undefined);
  h.c.stopCamera();
  assert.equal(h.c.viewModel().camera.diagnostics, null);
  assert.equal(h.c.window.frames.length, 0);
  assert.equal(h.calls.length, 0);
});

test('unclear Shoot window reports local sample counts and sends nothing', async () => {
  const h = setup(); h.c.applyState(countdown()); const { loop } = await cameraOn(h);
  feed(h, loop, SERVER_T0 + 2700, SERVER_T0 + 3400, 'rock', {score: .2});
  h.atServer(SERVER_T0 + 3500); h.c.tick();
  assert.equal(h.calls.length, 0);
  const samples = h.c.viewModel().camera.samples;
  assert.ok(samples.frames >= 3); assert.equal(samples.confident, 0); assert.ok(samples.spanMs <= 850);
});


test('revealing each move after Shoot ignores wind-up and submits a stable run once', async () => {
  for (const move of ['rock', 'paper', 'scissors']) {
    const h = setup(); h.c.applyState(countdown()); const { loop } = await cameraOn(h);
    const end = SERVER_T0 + 3000;
    feed(h, loop, end - 350, end + 130, 'rock'); // countdown/initial movement ignored
    loop.opts.onFrame({t: h.atServer(end + 160), hand: true, move: 'paper', score: .9});
    loop.opts.onFrame({t: h.atServer(end + 220), hand: true, move: null, score: .3});
    h.atServer(end + 250); h.c.tick();
    assert.equal(h.calls.length, 0); assert.equal(h.c.currentRound().status, 'pending');
    feed(h, loop, end + 300, end + 500, move);
    h.atServer(end + 550); h.c.tick(); h.c.tick(); await flush();
    assert.equal(h.calls.length, 1); assert.equal(h.calls[0].name, 'move');
    assert.equal(h.calls[0].args[2], move);
    const sample = h.c.viewModel().camera.samples;
    assert.ok(sample.runFrames >= 3); assert.ok(sample.runSpanMs >= 120);
    assert.equal(sample.decision, 'recognized');
  }
});

test('uncertain post-Shoot predictions wait, then offer Retry without scoring', async () => {
  const h = setup(); h.c.applyState(countdown()); const { loop } = await cameraOn(h);
  for (let offset = 150, i = 0; offset <= 890; offset += 70, i++) {
    loop.opts.onFrame({t: h.atServer(SERVER_T0 + 3000 + offset), hand: true, move: i % 2 ? 'paper' : 'rock', score: .9});
  }
  h.atServer(SERVER_T0 + 3850); h.c.tick();
  assert.equal(h.c.currentRound().status, 'pending');
  h.atServer(SERVER_T0 + 3900); h.c.tick(); await flush();
  assert.equal(h.c.currentRound().status, 'retry_prompt');
  assert.equal(h.c.currentRound().reason, 'unstable');
  assert.equal(h.c.canRetry(), true); assert.equal(h.calls.length, 0);
  assert.equal(h.c.viewModel().score.rounds, 0);
});

test('late or stale predictions cannot rescue an expired capture window', async () => {
  for (const from of [100, 1000]) {
    const h = setup(); h.c.applyState(countdown()); const { loop } = await cameraOn(h);
    feed(h, loop, SERVER_T0 + 3000 + from, SERVER_T0 + 3000 + from + 200, 'rock');
    h.atServer(SERVER_T0 + 4250); h.c.tick(); await flush();
    assert.equal(h.calls.length, 0); assert.equal(h.c.currentRound().status, 'retry_prompt');
  }
});


test('finish practice enables a ready round without releasing camera or restarting inference', async () => {
  const h = setup(); h.c.applyState(state());
  const { video, stream, loop } = await cameraOn(h, { practice: true });
  let t = SERVER_T0;
  for (const move of ['rock', 'paper', 'scissors']) {
    feed(h, loop, t, t + 900, move); t += 1200;
  }
  const cameraRun = h.c.cameraRun;
  assert.equal(h.c.finishPractice(), true);
  assert.equal(h.c.viewModel().camera.practice, false);
  assert.equal(h.c.viewModel().canNext, true);
  assert.equal(h.c.viewModel().camera.status, 'on');
  assert.equal(h.c.cameraRun, cameraRun);
  assert.equal(h.c.frameLoop, loop);
  assert.equal(loop.running, true);
  assert.equal(video.srcObject, stream);
  assert.equal(stream.getTracks().every(track => track.stopCalls === 0), true);
  await h.c.next();
  assert.equal(h.calls.filter(c => c.name === 'next').length, 1);
});


test('ended-session poll releases the camera, inference and stored pairing',async()=>{
  const callbacks=[];
  const timers={setTimeout(fn){callbacks.push(fn);return callbacks.length;},clearTimeout(){}};
  const h=setup({timers});h.c.applyState(state());
  const {stream,loop,video}=await cameraOn(h);
  h.api.getState=async()=>{throw new ApiError(410,'session_ended','Game ended','expired');};
  h.c.poller.start();callbacks.shift()();await flush();
  assert.equal(h.c.screen,'expired');
  assert.equal(h.c.cameraStatus,'off');
  assert.equal(stream.allStopped,true);assert.equal(loop.running,false);
  assert.equal(video.srcObject,null);assert.equal(h.c.session,null);
  assert.equal(h.store.getItem('terebi.rps.player.v1'),null);
});
