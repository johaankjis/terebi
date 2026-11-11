import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CameraController, classifyCameraError } from '../src/lib/camera.js';
import { domError, fakeMediaDevices, fakeStream, flush } from './helpers.js';

test('requests video only with audio:false', async () => {
  const md = fakeMediaDevices();
  const cam = new CameraController({ mediaDevices: md });
  const p = cam.start();
  assert.equal(md.calls[0].audio, false);
  assert.ok(md.calls[0].video);
  md.pending.resolve(fakeStream());
  assert.equal((await p).ok, true);
});

test('stop releases every track', async () => {
  const md = fakeMediaDevices();
  const cam = new CameraController({ mediaDevices: md });
  const p = cam.start();
  const s = fakeStream({ video: 2 });
  md.pending.resolve(s);
  await p;
  assert.equal(cam.stop(), 2);
  assert.ok(s.allStopped);
  assert.equal(cam.active, false);
  assert.equal(cam.stop(), 0, 'idempotent');
});

test('a permission prompt that resolves after Stop is released immediately', async () => {
  const md = fakeMediaDevices();
  const cam = new CameraController({ mediaDevices: md });
  const p = cam.start();
  cam.stop();
  const late = fakeStream();
  md.pending.resolve(late);
  assert.deepEqual(await p, { ok: false, code: 'cancelled' });
  assert.ok(late.allStopped);
  assert.equal(cam.active, false);
  assert.equal(md.calls.length, 1, 'no automatic re-request');
});

test('an unexpected audio track is stopped', async () => {
  const md = fakeMediaDevices();
  const cam = new CameraController({ mediaDevices: md });
  const p = cam.start();
  const s = fakeStream({ video: 1, audio: 1 });
  md.pending.resolve(s);
  await p;
  assert.equal(s.getAudioTracks()[0].readyState, 'ended');
});

test('denied, missing, busy, insecure and unsupported are reported, not retried', async () => {
  for (const [name, code] of [['NotAllowedError', 'denied'], ['NotFoundError', 'missing'], ['OverconstrainedError', 'missing'], ['NotReadableError', 'busy'], ['Weird', 'unknown']]) {
    const md = fakeMediaDevices();
    const cam = new CameraController({ mediaDevices: md });
    const p = cam.start();
    md.pending.reject(domError(name));
    assert.deepEqual(await p, { ok: false, code });
    await flush();
    assert.equal(md.calls.length, 1);
  }
  assert.deepEqual(await new CameraController({ mediaDevices: fakeMediaDevices(), isSecureContext: false }).start(), { ok: false, code: 'insecure' });
  assert.deepEqual(await new CameraController({ mediaDevices: undefined }).start(), { ok: false, code: 'unsupported' });
  assert.equal(classifyCameraError(domError('SecurityError')), 'denied');
});

test('a track ending (camera taken away) stops the stream and notifies', async () => {
  const md = fakeMediaDevices();
  let ended = 0;
  const cam = new CameraController({ mediaDevices: md, onEnded: () => (ended += 1) });
  const p = cam.start();
  const s = fakeStream();
  md.pending.resolve(s);
  await p;
  s.tracks[0].fire('ended');
  assert.equal(ended, 1);
  assert.equal(cam.active, false);
});
