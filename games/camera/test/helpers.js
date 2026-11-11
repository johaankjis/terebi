// Test doubles. All media here is MOCKED: no real camera, model or browser is used.

export function fakeTrack(kind) {
  const listeners = {};
  return {
    kind,
    readyState: 'live',
    stopCalls: 0,
    stop() {
      this.stopCalls += 1;
      this.readyState = 'ended';
    },
    addEventListener(type, fn) {
      listeners[type] = fn;
    },
    fire(type) {
      listeners[type]?.();
    },
  };
}

export function fakeStream({ video = 1, audio = 0 } = {}) {
  const tracks = [...Array.from({ length: video }, () => fakeTrack('video')), ...Array.from({ length: audio }, () => fakeTrack('audio'))];
  return {
    tracks,
    getTracks: () => tracks.slice(),
    getVideoTracks: () => tracks.filter((t) => t.kind === 'video'),
    getAudioTracks: () => tracks.filter((t) => t.kind === 'audio'),
    get allStopped() {
      return tracks.every((t) => t.readyState === 'ended');
    },
  };
}

export function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** mediaDevices whose getUserMedia is controlled by the test. */
export function fakeMediaDevices() {
  const md = {
    calls: [],
    pending: null,
    getUserMedia(constraints) {
      md.calls.push(constraints);
      md.pending = deferred();
      return md.pending.promise;
    },
  };
  return md;
}

export function domError(name) {
  const e = new Error(name);
  e.name = name;
  return e;
}

export function fakeVideo() {
  return {
    muted: false,
    playsInline: false,
    srcObject: null,
    attrs: {},
    paused: true,
    playError: null,
    setAttribute(k, v) {
      this.attrs[k] = v;
    },
    async play() {
      if (this.playError) throw this.playError;
      this.paused = false;
    },
    pause() {
      this.paused = true;
    },
  };
}

export const flush = () => new Promise((r) => setImmediate(r));

export const noTimers = { setTimeout: () => 0, clearTimeout: () => {} };
