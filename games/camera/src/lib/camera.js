// Camera lifecycle. Video only, never audio. Every stop releases every track,
// including a stream that arrives after the user already pressed Stop.

export const CAMERA_CONSTRAINTS = Object.freeze({
  audio: false,
  video: {
    facingMode: 'user',
    width: { ideal: 640 },
    height: { ideal: 480 },
    frameRate: { ideal: 30, max: 30 },
  },
});

export function classifyCameraError(err) {
  switch (err?.name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
    case 'SecurityError':
      return 'denied';
    case 'NotFoundError':
    case 'DevicesNotFoundError':
    case 'OverconstrainedError':
      return 'missing';
    case 'NotReadableError':
    case 'TrackStartError':
    case 'AbortError':
      return 'busy';
    case 'TypeError':
      return 'unsupported';
    default:
      return 'unknown';
  }
}

export function stopStream(stream) {
  if (!stream) return 0;
  let n = 0;
  for (const track of stream.getTracks()) {
    try {
      track.stop();
      n += 1;
    } catch {
      /* already stopped */
    }
  }
  return n;
}

export class CameraController {
  constructor({ mediaDevices = globalThis.navigator?.mediaDevices, isSecureContext = globalThis.isSecureContext !== false, onEnded } = {}) {
    this.mediaDevices = mediaDevices;
    this.isSecureContext = isSecureContext;
    this.onEnded = onEnded;
    this.stream = null;
    this.generation = 0;
    this.pending = false;
  }

  get active() {
    return Boolean(this.stream);
  }

  /**
   * Request the camera. Only call from an explicit user click.
   * Resolves {ok:true, stream, generation} | {ok:false, code} | {ok:false, code:'cancelled'}.
   */
  async start() {
    if (this.stream) return { ok: true, stream: this.stream, generation: this.generation };
    if (!this.isSecureContext) return { ok: false, code: 'insecure' };
    if (typeof this.mediaDevices?.getUserMedia !== 'function') return { ok: false, code: 'unsupported' };
    const generation = ++this.generation;
    this.pending = true;
    let stream;
    try {
      stream = await this.mediaDevices.getUserMedia(CAMERA_CONSTRAINTS);
    } catch (err) {
      if (generation === this.generation) this.pending = false;
      if (generation !== this.generation) return { ok: false, code: 'cancelled' };
      return { ok: false, code: classifyCameraError(err) };
    }
    if (generation !== this.generation) {
      // Stop was pressed (or the page hid) while the permission prompt was open.
      stopStream(stream);
      return { ok: false, code: 'cancelled' };
    }
    this.pending = false;
    if (!stream || stream.getVideoTracks().length === 0) {
      stopStream(stream);
      return { ok: false, code: 'missing' };
    }
    // Defense in depth: never keep an audio track even if a browser returns one.
    for (const t of stream.getAudioTracks()) t.stop();
    this.stream = stream;
    for (const track of stream.getVideoTracks()) {
      track.addEventListener?.('ended', () => {
        if (this.stream === stream) {
          this.stop();
          this.onEnded?.('ended');
        }
      });
    }
    return { ok: true, stream, generation };
  }

  /** Release everything and invalidate any pending start(). Safe to call repeatedly. */
  stop() {
    this.generation += 1;
    this.pending = false;
    const stream = this.stream;
    this.stream = null;
    return stopStream(stream);
  }
}
