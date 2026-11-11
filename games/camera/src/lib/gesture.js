// Gesture -> move mapping and the stable recent-frame decision.
// Everything here stays on the device. Only the final move string ever leaves.

export const MOVES = Object.freeze(['rock', 'paper', 'scissors']);

export const GESTURE_TO_MOVE = Object.freeze({
  Closed_Fist: 'rock',
  Open_Palm: 'paper',
  Victory: 'scissors',
});

export function isMove(value) {
  return typeof value === 'string' && MOVES.includes(value);
}

export function mapGesture(categoryName) {
  return Object.hasOwn(GESTURE_TO_MOVE, categoryName) ? GESTURE_TO_MOVE[categoryName] : null;
}

export function clampScore(score) {
  const n = Number(score);
  if (!Number.isFinite(n)) return 0;
  return Math.min(1, Math.max(0, n));
}

// Decision tuning uses the shared Shoot deadline on the local monotonic clock.
// Give the hand time to enter its pose, then require a fresh consecutive run.
export const DEFAULT_DECISION = Object.freeze({
  settleMs: 150, // ignore movement during countdown and initial reveal
  windowAfterMs: 900, // stop waiting and offer Retry after this deadline
  minStableMs: 120, // three same-shape predictions must span this long
  maxFrameGapMs: 250, // do not join predictions across inference stalls
  maxFrameAgeMs: 250, // the final prediction must be recent
  minScore: 0.6, // per-frame gesture confidence floor
  minFrames: 3, // confident frames required for the winning move
  minAgreement: 0.7, // practice-only whole-window agreement
  maxFrames: 120, // ring buffer bound
});

/**
 * Convert one MediaPipe GestureRecognizerResult into a compact frame record.
 * Landmarks and raw scores are not kept beyond this in-memory record.
 */
export function frameFromResult(result, t) {
  const top = result?.gestures?.[0]?.[0];
  const hand = Boolean(
    (Array.isArray(result?.landmarks) && result.landmarks.length > 0) ||
      (Array.isArray(result?.gestures) && result.gestures.length > 0),
  );
  if (!hand) return { t, hand: false, move: null, score: 0 };
  return { t, hand: true, move: mapGesture(top?.categoryName), score: clampScore(top?.score) };
}

export class GestureWindow {
  constructor({ maxFrames = DEFAULT_DECISION.maxFrames } = {}) {
    this.maxFrames = maxFrames;
    this.frames = [];
  }

  push(frame) {
    if (!frame || !Number.isFinite(frame.t)) return;
    // Out-of-order frames would make "recent" meaningless; drop them.
    const last = this.frames[this.frames.length - 1];
    if (last && frame.t < last.t) return;
    this.frames.push(frame);
    if (this.frames.length > this.maxFrames) this.frames.splice(0, this.frames.length - this.maxFrames);
  }

  between(fromT, toT) {
    return this.frames.filter((f) => f.t >= fromT && f.t <= toT);
  }

  clear() {
    this.frames = [];
  }
}

/**
 * Decide a move from frames already restricted to the decision window.
 * Returns {ok:true, move} or {ok:false, reason} where reason is one of
 * 'no_frames' | 'no_hand' | 'low_confidence' | 'unstable'.
 */
export function decideMove(frames, opts = DEFAULT_DECISION) {
  const o = { ...DEFAULT_DECISION, ...opts };
  if (!frames.length) return { ok: false, reason: 'no_frames' };
  const hands = frames.filter((f) => f.hand);
  if (!hands.length) return { ok: false, reason: 'no_hand' };
  const confident = hands.filter((f) => isMove(f.move) && f.score >= o.minScore);
  if (confident.length < o.minFrames) return { ok: false, reason: 'low_confidence' };
  const counts = new Map();
  for (const f of confident) counts.set(f.move, (counts.get(f.move) || 0) + 1);
  let move = null;
  let best = 0;
  for (const [m, c] of counts) {
    if (c > best) {
      best = c;
      move = m;
    }
  }
  if (best < o.minFrames) return { ok: false, reason: 'low_confidence' };
  if (best / hands.length < o.minAgreement) return { ok: false, reason: 'unstable' };
  // The most recent confident frame must agree: a hand that changed at the end is unclear.
  if (confident[confident.length - 1].move !== move) return { ok: false, reason: 'unstable' };
  return { ok: true, move };
}


/** Round-only decision: the latest consecutive run, not a whole-window majority.
 * Caller supplies only post-Shoot predictions and the current monotonic time.
 * Missing, unclear or different predictions break the run; no frames are skipped.
 */
export function decideRevealMove(frames, now, opts = DEFAULT_DECISION) {
  const o = { ...DEFAULT_DECISION, ...opts };
  const result = (reason, run = []) => ({ ok: false, reason, runFrames: run.length, runSpanMs: run.length > 1 ? run.at(-1).t - run[0].t : 0 });
  if (!frames.length) return result('no_frames');
  const last = frames.at(-1);
  if (!Number.isFinite(now) || now < last.t || now - last.t > o.maxFrameAgeMs) return result('no_frames');
  if (!last.hand) return result('no_hand');
  if (!isMove(last.move) || !(last.score >= o.minScore)) return result('low_confidence');
  const run = [last];
  for (let i = frames.length - 2; i >= 0; i--) {
    const f = frames[i], next = run[0];
    if (!f.hand || f.move !== last.move || !(f.score >= o.minScore) || next.t <= f.t || next.t - f.t > o.maxFrameGapMs) break;
    run.unshift(f);
  }
  if (run.length < o.minFrames || last.t - run[0].t < o.minStableMs) return result('unstable', run);
  return { ok: true, move: last.move, runFrames: run.length, runSpanMs: last.t - run[0].t };
}
