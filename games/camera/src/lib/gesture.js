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

// Decision tuning. The window is measured on the local monotonic clock around
// the countdown deadline, so it does not depend on the phone's wall clock.
export const DEFAULT_DECISION = Object.freeze({
  windowBeforeMs: 400, // frames just before "Shoot"
  windowAfterMs: 450, // decision happens this long after the deadline
  minScore: 0.6, // per-frame gesture confidence floor
  minFrames: 3, // confident frames required for the winning move
  minAgreement: 0.7, // share of hand frames that must agree
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
