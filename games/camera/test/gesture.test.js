import assert from 'node:assert/strict';
import { test } from 'node:test';
import { GestureWindow, clampScore, decideMove, frameFromResult, mapGesture } from '../src/lib/gesture.js';

test('maps exactly the three MediaPipe canned gestures', () => {
  assert.equal(mapGesture('Closed_Fist'), 'rock');
  assert.equal(mapGesture('Open_Palm'), 'paper');
  assert.equal(mapGesture('Victory'), 'scissors');
  for (const other of ['None', 'Pointing_Up', 'Thumb_Up', 'Thumb_Down', 'ILoveYou', '', undefined, 'toString', '__proto__']) {
    assert.equal(mapGesture(other), null, String(other));
  }
});

test('confidence is bounded to [0,1] and non-finite becomes 0', () => {
  assert.equal(clampScore(1.7), 1);
  assert.equal(clampScore(-2), 0);
  assert.equal(clampScore(Number.NaN), 0);
  assert.equal(clampScore('0.5'), 0.5);
});

test('frameFromResult handles no hand, unknown gesture and a fist', () => {
  assert.deepEqual(frameFromResult({ gestures: [], landmarks: [] }, 5), { t: 5, hand: false, move: null, score: 0 });
  assert.deepEqual(frameFromResult(null, 5), { t: 5, hand: false, move: null, score: 0 });
  const thumb = frameFromResult({ gestures: [[{ categoryName: 'Thumb_Up', score: 0.9 }]], landmarks: [[{}]] }, 6);
  assert.equal(thumb.hand, true);
  assert.equal(thumb.move, null);
  const fist = frameFromResult({ gestures: [[{ categoryName: 'Closed_Fist', score: 0.93 }]], landmarks: [[{}]] }, 7);
  assert.deepEqual(fist, { t: 7, hand: true, move: 'rock', score: 0.93 });
});

const f = (t, move, score = 0.9, hand = true) => ({ t, hand, move, score });

test('stable recent frames produce a move', () => {
  assert.deepEqual(decideMove([f(1, 'paper'), f(2, 'paper'), f(3, 'paper'), f(4, 'paper')]), { ok: true, move: 'paper' });
});

test('empty window, no hand and low confidence never produce a move', () => {
  assert.deepEqual(decideMove([]), { ok: false, reason: 'no_frames' });
  assert.deepEqual(decideMove([f(1, null, 0, false), f(2, null, 0, false), f(3, null, 0, false)]), { ok: false, reason: 'no_hand' });
  assert.deepEqual(decideMove([f(1, 'rock', 0.4), f(2, 'rock', 0.5), f(3, 'rock', 0.59), f(4, 'rock', 0.3)]), { ok: false, reason: 'low_confidence' });
  // Hand visible but an unmapped gesture.
  assert.deepEqual(decideMove([f(1, null), f(2, null), f(3, null)]), { ok: false, reason: 'low_confidence' });
  // Too few confident frames.
  assert.deepEqual(decideMove([f(1, 'rock'), f(2, 'rock')]), { ok: false, reason: 'low_confidence' });
});

test('flicker between shapes or a last-moment change is unstable', () => {
  assert.deepEqual(decideMove([f(1, 'rock'), f(2, 'paper'), f(3, 'rock'), f(4, 'paper'), f(5, 'rock'), f(6, 'paper')]), { ok: false, reason: 'unstable' });
  assert.deepEqual(
    decideMove([f(1, 'rock'), f(2, 'rock'), f(3, 'rock'), f(4, 'rock'), f(5, 'rock'), f(6, 'rock'), f(7, 'rock'), f(8, 'rock'), f(9, 'scissors')]),
    { ok: false, reason: 'unstable' },
  );
});

test('window is bounded, ordered and range-filtered', () => {
  const w = new GestureWindow({ maxFrames: 3 });
  for (let t = 0; t < 6; t++) w.push(f(t, 'rock'));
  assert.deepEqual(w.frames.map((x) => x.t), [3, 4, 5]);
  w.push(f(1, 'paper')); // out of order: dropped
  assert.equal(w.frames.length, 3);
  assert.deepEqual(w.between(4, 5).map((x) => x.t), [4, 5]);
  w.clear();
  assert.equal(w.frames.length, 0);
});
