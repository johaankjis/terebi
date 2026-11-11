// Player-side game controller. The server is authoritative for phases, score and
// Hermes' move; this only renders state, decides the local camera move once per
// round_id at the shared countdown end, and drives /next, /retry, /move and /tap.

import { DEFAULT_DECISION, GestureWindow, decideMove, isMove } from './gesture.js';
import { clearSession, establishSession } from './session.js';
import { Poller } from './poller.js';

const PHASES = new Set(['waiting_for_player', 'ready', 'countdown', 'reveal', 'score', 'next_round']);
const DONE = new Set(['sent', 'accepted']);
const REVEALED = new Set(['reveal', 'score', 'next_round']);

export const CAMERA_MESSAGES = Object.freeze({
  denied: 'Camera permission was denied. To use the camera, allow it in Safari (aA menu > Website Settings > Camera), then press Turn on camera. Tap buttons still work.',
  missing: 'No camera was found on this device. Use the tap buttons to play.',
  busy: 'The camera is busy in another app. Close that app, then press Turn on camera.',
  insecure: 'The camera needs a secure (https) page. Use the tap buttons, or open the HTTPS link from Telegram.',
  unsupported: 'This browser cannot share the camera here. Use the tap buttons to play.',
  unknown: 'The camera could not start. Press Turn on camera to try again, or use the tap buttons.',
  playback: 'The camera preview could not start. Press Turn on camera to try again.',
  model: 'The hand recognizer could not load. Use the tap buttons, or press Turn on camera to try again.',
  ended: 'The camera stopped (another app may have taken it). Press Turn on camera to continue.',
  hidden: 'Camera turned off while you were away. Press Turn on camera to continue.',
  left: 'Camera turned off.',
  user: 'Camera is off.',
  expired: 'Camera turned off: this game session ended.',
});

const RETRY_PROMPTS = Object.freeze({
  no_frames: "The camera wasn't ready at Shoot. Press Retry for another countdown.",
  no_hand: "I couldn't see a hand. Keep it inside the frame and press Retry.",
  low_confidence: "Your hand shape wasn't clear. Hold it steady and press Retry.",
  unstable: 'Your hand changed at the last moment. Hold one shape and press Retry.',
});

export function isValidState(s) {
  return Boolean(
    s &&
      typeof s.session_id === 'string' &&
      Number.isFinite(s.revision) &&
      Number.isFinite(s.server_time_ms) &&
      PHASES.has(s.phase) &&
      s.score &&
      typeof s.score === 'object',
  );
}

export class GameController {
  constructor({
    api,
    clock,
    camera,
    storage,
    subtle,
    loadRecognizer,
    createFrameLoop,
    timers = globalThis,
    decision = DEFAULT_DECISION,
    pollIntervalMs = 400,
    onChange = () => {},
  }) {
    Object.assign(this, { api, clock, camera, storage, subtle, loadRecognizer, createFrameLoop, timers, onChange });
    this.decision = { ...DEFAULT_DECISION, ...decision };
    this.window = new GestureWindow({ maxFrames: this.decision.maxFrames });
    this.screen = 'loading';
    this.session = null;
    this.state = null;
    this.rounds = new Map();
    this.practiceMode = false;
    this.practiceSeen = new Set();
    this.diagnostics = null;
    this.modelStage = null;
    this.sampleSummary = null;
    this.cameraStatus = 'off';
    this.cameraMessage = null;
    this.cameraRun = 0; // bumps on every camera start/stop; stale async work checks it
    this.video = null;
    this.frameLoop = null;
    this.recognizerPromise = null;
    this.cameraSubmit = null;
    this.busy = { next: false, retry: false };
    this.notice = null;
    this.pairErrorReason = null;
    this.poller = new Poller({
      intervalMs: pollIntervalMs,
      timers,
      fetchOnce: () => this.api.getState(this.session.session_id),
      onResult: (res) => {
        this.notice = null;
        this.#applyResponse(res);
      },
      onError: (err) => {
        this.notice = err?.kind === 'rate_limited' ? 'Slowing down; the game server asked us to wait.' : 'Reconnecting to the game…';
        this.#changed();
      },
      onTerminal: () => this.expire(),
    });
  }

  // ---------- session ----------

  async init({ pairToken }) {
    try {
      const r = await establishSession({ pairToken, storage: this.storage, api: this.api, subtle: this.subtle });
      if (!r.session) {
        this.screen = 'unpaired';
        return this.#changed();
      }
      this.session = r.session;
      this.screen = 'game';
      if (r.state) this.applyState(r.state);
      this.poller.start();
    } catch (err) {
      this.screen = 'pair_failed';
      this.pairErrorReason = err?.reason ?? 'error';
    }
    this.#changed();
  }

  getToken() {
    return this.session?.player_token ?? null;
  }

  expire() {
    if (this.screen === 'expired') return;
    this.stopCamera('expired');
    this.poller.stop();
    clearSession(this.storage);
    this.session = null;
    this.screen = 'expired';
    this.#changed();
  }

  #applyResponse(res) {
    const state = res?.data?.state;
    if (!isValidState(state)) return;
    this.clock.sample(state.server_time_ms, res.sentMono, res.recvMono);
    this.applyState(state);
  }

  applyState(state) {
    if (!isValidState(state) || !this.session) return false;
    if (state.session_id !== this.session.session_id) return false;
    if (this.state && state.revision < this.state.revision) return false; // stale response
    this.state = state;
    if (state.round_id) this.#round(state.round_id);
    this.#changed();
    return true;
  }

  #round(roundId) {
    let rec = this.rounds.get(roundId);
    if (!rec) {
      rec = { status: 'pending', reason: null, input: null };
      this.rounds.set(roundId, rec);
      while (this.rounds.size > 16) this.rounds.delete(this.rounds.keys().next().value);
    }
    return rec;
  }

  currentRound() {
    return this.state?.round_id ? this.#round(this.state.round_id) : null;
  }

  // ---------- timing / automatic camera decision ----------

  tick() {
    if (this.screen !== 'game' || !this.state) return;
    const now = this.clock.serverNow();
    if (now === null) return;
    const s = this.state;
    if (Number.isFinite(s.expires_at_ms) && now >= s.expires_at_ms) return this.expire();
    if (s.phase !== 'countdown' || !s.round_id || !Number.isFinite(s.countdown_ends_at_ms)) return;
    const rec = this.#round(s.round_id);
    if (rec.status !== 'pending' || this.practiceMode) return;
    if (now < s.countdown_ends_at_ms + this.decision.windowAfterMs) return;
    if (Number.isFinite(s.accept_until_ms) && now > s.accept_until_ms) {
      rec.status = 'timed_out';
      return this.#changed();
    }
    if (this.cameraStatus !== 'on') {
      rec.status = 'no_camera';
      return this.#changed();
    }
    const endMono = this.clock.toMono(s.countdown_ends_at_ms);
    const frames = this.window.between(endMono - this.decision.windowBeforeMs, endMono + this.decision.windowAfterMs);
    this.sampleSummary = { frames: frames.length, confident: frames.filter(f => f.move && f.score >= this.decision.minScore).length, spanMs: frames.length > 1 ? Math.round(frames.at(-1).t - frames[0].t) : 0 };
    const result = decideMove(frames, this.decision);
    if (!result.ok) {
      rec.status = 'retry_prompt'; // no submission; score untouched
      rec.reason = result.reason;
      return this.#changed();
    }
    this.#submit(s.round_id, result.move, 'camera');
  }

  #canSubmit(roundId) {
    const s = this.state;
    const now = this.clock.serverNow();
    if (!s || s.phase !== 'countdown' || s.round_id !== roundId || now === null) return false;
    if (!Number.isFinite(s.countdown_ends_at_ms) || now < s.countdown_ends_at_ms) return false;
    if (Number.isFinite(s.accept_until_ms) && now > s.accept_until_ms) return false;
    return !DONE.has(this.#round(roundId).status);
  }

  async #submit(roundId, move, input) {
    if (!isMove(move) || !this.#canSubmit(roundId)) return false;
    const rec = this.#round(roundId);
    rec.status = 'sent';
    rec.input = input;
    const ctrl = new AbortController();
    if (input === 'camera') this.cameraSubmit = ctrl;
    this.#changed();
    try {
      const call = input === 'camera' ? this.api.move : this.api.tap;
      const res = await call(this.session.session_id, roundId, move, { signal: ctrl.signal });
      rec.status = 'accepted';
      this.#applyResponse(res);
      return true;
    } catch (err) {
      if (err?.kind === 'expired') this.expire();
      else if (err?.kind === 'aborted') rec.status = 'cancelled';
      else if (err?.kind === 'conflict') {
        rec.status = 'rejected';
        rec.reason = err.hint || 'That round already moved on.';
      } else rec.status = 'uncertain'; // never resend automatically
      this.#changed();
      return false;
    } finally {
      if (this.cameraSubmit === ctrl) this.cameraSubmit = null;
    }
  }

  // ---------- user actions ----------

  canNext() {
    return this.screen === 'game' && !this.busy.next && (this.state?.phase === 'ready' || this.state?.phase === 'next_round') && Boolean(this.state.round_id);
  }

  canRetry() {
    const s = this.state;
    const now = this.clock.serverNow();
    if (this.screen !== 'game' || this.busy.retry || !s || s.phase !== 'countdown' || !s.round_id || now === null) return false;
    if (!Number.isFinite(s.countdown_ends_at_ms) || now < s.countdown_ends_at_ms) return false;
    return !DONE.has(this.#round(s.round_id).status);
  }

  canTap() {
    return this.screen === 'game' && Boolean(this.state?.round_id) && this.#canSubmit(this.state.round_id);
  }

  async next() {
    if (!this.canNext()) return false;
    return this.#action('next', () => this.api.next(this.session.session_id, this.state.round_id));
  }

  async retry() {
    if (!this.canRetry()) return false;
    return this.#action('retry', () => this.api.retry(this.session.session_id, this.state.round_id));
  }

  /** Labelled tap fallback: explicit user input, works with or without the camera. */
  async tap(move) {
    if (!this.canTap()) return false;
    return this.#submit(this.state.round_id, move, 'tap');
  }

  async #action(name, fn) {
    this.busy[name] = true;
    this.#changed();
    try {
      this.#applyResponse(await fn());
      return true;
    } catch (err) {
      if (err?.kind === 'expired') this.expire();
      else this.notice = err?.kind === 'conflict' ? 'The game already moved on.' : 'Could not reach the game server. Try again.';
      return false;
    } finally {
      this.busy[name] = false;
      this.#changed();
    }
  }

  // ---------- camera ----------

  /** Only call from an explicit click. Never called automatically. */
  async startCamera(video) {
    if (this.cameraStatus === 'requesting' || this.cameraStatus === 'loading' || this.cameraStatus === 'on') return false;
    if (this.screen !== 'game') return false;
    const run = ++this.cameraRun;
    this.video = video;
    this.cameraStatus = 'requesting';
    this.cameraMessage = null;
    this.practiceMode = true;
    this.practiceSeen.clear();
    this.diagnostics = null;
    this.modelStage = 'camera';
    this.sampleSummary = null;
    this.#changed();
    const res = await this.camera.start();
    if (run !== this.cameraRun) {
      if (res.ok) this.camera.stop();
      return false;
    }
    if (!res.ok) {
      this.cameraStatus = 'off';
      this.cameraMessage = res.code === 'cancelled' ? null : CAMERA_MESSAGES[res.code] ?? CAMERA_MESSAGES.unknown;
      this.cameraError = res.code;
      this.#changed();
      return false;
    }
    try {
      video.muted = true;
      video.playsInline = true;
      video.setAttribute?.('playsinline', '');
      video.srcObject = res.stream;
      await video.play();
    } catch {
      if (run === this.cameraRun) this.#fail('playback');
      return false;
    }
    if (run !== this.cameraRun) return false;
    this.cameraStatus = 'loading';
    this.#changed();
    let recognizer;
    try {
      this.recognizerPromise ??= this.loadRecognizer({ onStage: (stage) => {
        if (run === this.cameraRun) { this.modelStage = stage; this.#changed(); }
      } });
      recognizer = await this.recognizerPromise;
    } catch {
      this.recognizerPromise = null; // a later explicit click may try again
      if (run === this.cameraRun) this.#fail('model');
      return false;
    }
    if (run !== this.cameraRun) return false;
    this.window.clear();
    this.frameLoop = this.createFrameLoop({
      video,
      recognizer,
      onFrame: (frame) => {
        if (run !== this.cameraRun) return;
        // Retain compact predictions only in the bounded round window.
        const { t, hand, move, score } = frame;
        this.window.push({ t, hand, move, score });
        this.diagnostics = { ...(frame.diagnostics ?? { status: !hand ? 'no_hand' : !move || score < this.decision.minScore ? 'low_confidence' : 'recognized', move, score, gesture: move, landmarks: [] }), t };
        if (this.practiceMode) {
          const stable = decideMove(this.window.between(t - 800, t), this.decision);
          if (stable.ok) this.practiceSeen.add(stable.move);
        }
        this.#changed();
      },
      onError: () => {
        if (run === this.cameraRun) this.#fail('model');
      },
    });
    this.frameLoop.start();
    this.cameraStatus = 'on';
    this.modelStage = 'inference';
    this.cameraError = null;
    this.#changed();
    return true;
  }

  finishPractice() {
    if (this.cameraStatus !== 'on') return false;
    this.practiceMode = false;
    this.window.clear();
    this.#changed();
    return true;
  }

  #fail(code) {
    this.stopCamera(code);
  }

  /** Release every track, stop inference and cancel any pending camera submission. */
  stopCamera(reason = 'user') {
    this.cameraRun += 1;
    this.frameLoop?.stop();
    this.frameLoop = null;
    this.window.clear();
    this.diagnostics = null;
    this.practiceMode = false;
    this.cameraSubmit?.abort();
    this.cameraSubmit = null;
    const released = this.camera.stop();
    if (this.video) {
      try {
        this.video.pause?.();
        this.video.srcObject = null;
      } catch {
        /* ignore */
      }
    }
    const wasActive = this.cameraStatus !== 'off';
    this.cameraStatus = 'off';
    if (wasActive || reason !== 'user') {
      this.cameraMessage = CAMERA_MESSAGES[reason] ?? CAMERA_MESSAGES.user;
      this.cameraError = ['denied', 'missing', 'busy', 'model', 'playback', 'ended'].includes(reason) ? reason : null;
    }
    this.#changed();
    return released;
  }

  // ---------- page lifecycle ----------

  onVisibilityChange(hidden) {
    if (hidden) {
      if (this.cameraStatus !== 'off') this.stopCamera('hidden');
      this.poller.stop();
    } else if (this.screen === 'game') {
      this.poller.start(); // camera stays off until the user presses the button again
    }
  }

  onPageHide() {
    if (this.cameraStatus !== 'off' || this.camera.active || this.camera.pending) this.stopCamera('left');
    this.poller.stop();
  }

  onPageShow() {
    if (this.screen === 'game') this.poller.start();
  }

  // ---------- view ----------

  viewModel() {
    const s = this.state;
    const now = this.clock.serverNow();
    const rec = this.currentRound();
    const vm = {
      screen: this.screen,
      pairErrorReason: this.pairErrorReason,
      notice: this.notice,
      camera: { status: this.cameraStatus, message: this.cameraMessage, error: this.cameraError ?? null, stage: this.modelStage, diagnostics: this.diagnostics, practice: this.practiceMode, seen: [...this.practiceSeen], samples: this.sampleSummary },
      phase: s?.phase ?? null,
      roundNumber: s?.round_number ?? 0,
      score: s?.score ?? { player: 0, hermes: 0, ties: 0, rounds: 0 },
      countdown: null,
      result: null,
      commitment: s?.hermes_commitment ? String(s.hermes_commitment).slice(0, 10) : null,
      prompt: '',
      canNext: this.canNext(),
      canRetry: this.canRetry(),
      canTap: this.canTap(),
      busy: { ...this.busy },
    };
    if (!s) return vm;
    // Hermes' move is shown only once the server says the round is revealed.
    if (REVEALED.has(s.phase) && s.result && s.result.round_id) vm.result = { ...s.result };
    switch (s.phase) {
      case 'waiting_for_player':
        vm.prompt = 'Waiting for pairing to finish…';
        break;
      case 'ready':
        vm.prompt = 'Hermes has locked in a move. Press Start round when you are ready.';
        break;
      case 'next_round':
        vm.prompt = 'Ready for another? Press Next round.';
        break;
      case 'reveal':
        vm.prompt = 'Reveal!';
        break;
      case 'score':
        vm.prompt = 'Score updated.';
        break;
      case 'countdown': {
        const ends = s.countdown_ends_at_ms;
        if (now === null || !Number.isFinite(ends)) {
          vm.countdown = { text: '…', shoot: false };
        } else {
          const rem = ends - now;
          vm.countdown = rem > 0 ? { text: String(Math.min(3, Math.max(1, Math.ceil(rem / 1000)))), shoot: false } : { text: 'Shoot!', shoot: true };
        }
        vm.prompt = this.#countdownPrompt(rec, vm.countdown?.shoot);
        break;
      }
      default:
        break;
    }
    return vm;
  }

  #countdownPrompt(rec, shoot) {
    const cam = this.cameraStatus === 'on';
    switch (rec?.status) {
      case 'pending':
        if (!shoot) return cam ? 'Hold your hand inside the frame and throw on Shoot.' : 'Camera off: tap your move below when it says Shoot.';
        return cam ? 'Reading your hand…' : 'Tap your move now.';
      case 'retry_prompt':
        return RETRY_PROMPTS[rec.reason] ?? RETRY_PROMPTS.no_hand;
      case 'no_camera':
        return 'Camera is off. Tap your move below, or press Retry for another countdown.';
      case 'timed_out':
        return 'Too late for this throw. Press Retry for another countdown.';
      case 'sent':
        return rec.input === 'tap' ? 'Sending your tapped move…' : 'Sending your camera move…';
      case 'accepted':
        return 'Locked in. Waiting for the reveal…';
      case 'uncertain':
        return "Couldn't confirm your move. Waiting for the game; press Retry if nothing happens.";
      case 'rejected':
        return rec.reason || 'That round already moved on.';
      case 'cancelled':
        return 'Camera move cancelled. Tap your move or press Retry.';
      default:
        return '';
    }
  }

  #changed() {
    try {
      this.onChange(this);
    } catch {
      /* rendering errors must not break game flow */
    }
  }
}
