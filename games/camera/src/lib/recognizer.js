// On-device MediaPipe GestureRecognizer, loaded from files served next to this page.
// No CDN, no model download at runtime from a third party, no telemetry.

import { frameFromResult } from './gesture.js';
import { describeResult } from './practice.js';

export const VENDOR_URL = new URL('../vendor/vision_bundle.js', import.meta.url).href;
export const WASM_BASE_URL = new URL('../vendor/wasm', import.meta.url).href;
export const MODEL_URL = new URL('../models/gesture_recognizer.task', import.meta.url).href;

export const RECOGNIZER_OPTIONS = Object.freeze({
  runningMode: 'VIDEO',
  numHands: 1,
  minHandDetectionConfidence: 0.5,
  minHandPresenceConfidence: 0.5,
  minTrackingConfidence: 0.5,
});

/** Load once; reuse across camera sessions. */
export async function loadRecognizer({ importModule = (u) => import(u), onStage = () => {} } = {}) {
  onStage('runtime');
  const vision = await importModule(VENDOR_URL);
  onStage('wasm');
  const fileset = await vision.FilesetResolver.forVisionTasks(WASM_BASE_URL);
  // CPU delegate: the WebGL delegate is less predictable on iOS Safari.
  onStage('model');
  const recognizer = await vision.GestureRecognizer.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: MODEL_URL, delegate: 'CPU' },
    ...RECOGNIZER_OPTIONS,
  });
  return {
    recognize(video, tMono) {
      const result = recognizer.recognizeForVideo(video, tMono);
      return { ...frameFromResult(result, tMono), diagnostics: describeResult(result) };
    },
    close() {
      try {
        recognizer.close();
      } catch {
        /* ignore */
      }
    },
  };
}

/**
 * Pull frames from a playing <video> at most every minIntervalMs and hand compact
 * frame records to onFrame. stop() cancels the loop; nothing runs after stop.
 */
export class FrameLoop {
  constructor({ video, recognizer, onFrame, onError, now = () => performance.now(), raf = globalThis.requestAnimationFrame?.bind(globalThis), caf = globalThis.cancelAnimationFrame?.bind(globalThis), minIntervalMs = 66 }) {
    Object.assign(this, { video, recognizer, onFrame, onError, now, raf, caf, minIntervalMs });
    this.handle = null;
    this.running = false;
    this.lastT = -Infinity;
    this.lastVideoTime = -1;
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.handle = this.raf(this.#step);
  }

  stop() {
    this.running = false;
    if (this.handle !== null) this.caf?.(this.handle);
    this.handle = null;
  }

  #step = () => {
    this.handle = null;
    if (!this.running) return;
    const t = this.now();
    const v = this.video;
    if (t - this.lastT >= this.minIntervalMs && v.readyState >= 2 && v.currentTime !== this.lastVideoTime) {
      this.lastT = t;
      this.lastVideoTime = v.currentTime;
      try {
        const frame = this.recognizer.recognize(v, t);
        if (this.running) this.onFrame(frame);
      } catch (err) {
        this.stop();
        this.onError?.(err);
        return;
      }
    }
    if (this.running) this.handle = this.raf(this.#step);
  };
}
