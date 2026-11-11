import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { FrameLoop, MODEL_URL, RECOGNIZER_OPTIONS, VENDOR_URL, WASM_BASE_URL, loadRecognizer } from '../src/lib/recognizer.js';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const SRC = join(ROOT, 'src');

async function srcFiles(dir = SRC) {
  const out = [];
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    out.push(...(e.isDirectory() ? await srcFiles(p) : [p]));
  }
  return out;
}

test('page source has no remote URLs, analytics or storage of frames', async () => {
  for (const file of await srcFiles()) {
    const text = await readFile(file, 'utf8');
    assert.doesNotMatch(text, /\bhttps?:\/\//i, file);
    assert.doesNotMatch(text, /cdn\.jsdelivr|googleapis|gtag|analytics|sendBeacon|localStorage/i, file);
    assert.doesNotMatch(text, /toDataURL|toBlob|MediaRecorder|captureStream/, file);
  }
});

test('index.html references only relative assets and a playsinline muted video', async () => {
  const html = await readFile(join(SRC, 'index.html'), 'utf8');
  for (const [, url] of html.matchAll(/(?:src|href)="([^"]+)"/g)) assert.match(url, /^\.\//, url);
  assert.match(html, /<video[^>]*\bplaysinline\b[^>]*\bmuted\b/);
  assert.match(html, /Stop camera/);
  assert.match(html, /Tap fallback/);
});

test('runtime and model URLs resolve next to the page (served under /play/)', () => {
  const lib = new URL('../src/lib/', import.meta.url).href;
  for (const u of [VENDOR_URL, WASM_BASE_URL, MODEL_URL]) assert.ok(u.startsWith(new URL('..', lib).href), u);
  assert.ok(MODEL_URL.endsWith('/models/gesture_recognizer.task'));
  assert.equal(RECOGNIZER_OPTIONS.numHands, 1);
});

test('loadRecognizer uses the local module, CPU delegate and VIDEO mode (mocked MediaPipe)', async () => {
  const seen = {};
  const fake = {
    FilesetResolver: { forVisionTasks: async (base) => ((seen.base = base), { fileset: true }) },
    GestureRecognizer: {
      createFromOptions: async (_fs, opts) => {
        seen.opts = opts;
        return { recognizeForVideo: (_v, t) => ({ gestures: [[{ categoryName: 'Victory', score: 0.8 }]], landmarks: [[{}]], t }), close() {} };
      },
    },
  };
  const r = await loadRecognizer({ importModule: async (u) => ((seen.url = u), fake) });
  assert.equal(seen.url, VENDOR_URL);
  assert.equal(seen.base, WASM_BASE_URL);
  assert.equal(seen.opts.baseOptions.modelAssetPath, MODEL_URL);
  assert.equal(seen.opts.baseOptions.delegate, 'CPU');
  assert.equal(seen.opts.runningMode, 'VIDEO');
  const frame = r.recognize({}, 12);
  assert.equal(frame.move, 'scissors');
  assert.equal(frame.score, 0.8);
  assert.equal(frame.diagnostics.status, 'recognized');
});

test('FrameLoop throttles, skips repeated video frames and stops completely', () => {
  const queue = [];
  let now = 0;
  const frames = [];
  const video = { readyState: 4, currentTime: 0 };
  const loop = new FrameLoop({
    video,
    recognizer: { recognize: (_v, t) => ({ t }) },
    onFrame: (f) => frames.push(f),
    now: () => now,
    raf: (fn) => queue.push(fn),
    caf: () => {},
    minIntervalMs: 66,
  });
  loop.start();
  const step = (dt, vt) => {
    now += dt;
    video.currentTime = vt;
    queue.shift()();
  };
  step(16, 0.016); // t=16 processed
  step(70, 0.016); // t=86 same video frame: skipped
  step(10, 0.1); // t=96 new frame: processed
  step(16, 0.2); // t=112 throttled (<66 ms since last)
  assert.deepEqual(frames.map((f) => f.t), [16, 96]);
  loop.stop();
  assert.equal(loop.running, false);
  queue.shift()?.(); // a stale callback does nothing
  assert.equal(frames.length, 2);
  assert.equal(queue.length, 0);
});

test('a recognizer exception stops the loop and reports a model error', () => {
  const queue = [];
  let err = null;
  const loop = new FrameLoop({
    video: { readyState: 4, currentTime: 1 },
    recognizer: { recognize: () => { throw new Error('wasm abort'); } },
    onFrame: () => {},
    onError: (e) => (err = e),
    now: () => 100,
    raf: (fn) => queue.push(fn),
  });
  loop.start();
  queue.shift()();
  assert.equal(err.message, 'wasm abort');
  assert.equal(loop.running, false);
  assert.equal(queue.length, 0);
});
