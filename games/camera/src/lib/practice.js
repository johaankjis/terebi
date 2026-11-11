// Temporary diagnostics. Kept in memory on the paired device; never sent to the API.
import { DEFAULT_DECISION, mapGesture, clampScore } from './gesture.js';

export function describeResult(result) {
  const points = result?.landmarks?.[0] ?? [];
  const landmarks = points.slice(0, 21).filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
    .map(({ x, y }) => ({ x, y }));
  const top = result?.gestures?.[0]?.[0];
  const hand = points.length > 0;
  const score = clampScore(top?.score);
  const move = mapGesture(top?.categoryName);
  return {
    status: !hand ? 'no_hand' : !move || score < DEFAULT_DECISION.minScore ? 'low_confidence' : 'recognized',
    gesture: typeof top?.categoryName === 'string' ? top.categoryName.slice(0, 40) : null,
    move, score, landmarks,
  };
}

export const CONNECTIONS = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],
  [5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],
  [13,17],[0,17],[17,18],[18,19],[19,20]];

export function drawLandmarks(canvas, video, points = []) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const width = canvas.clientWidth || 640, height = canvas.clientHeight || 480;
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  ctx.clearRect(0, 0, width, height);
  // Match the preview's object-fit: contain. Both elements are mirrored by CSS.
  const ratio = Math.min(width / (video.videoWidth || width), height / (video.videoHeight || height));
  const w = (video.videoWidth || width) * ratio, h = (video.videoHeight || height) * ratio;
  const xy = (p) => [(width - w) / 2 + p.x * w, (height - h) / 2 + p.y * h];
  ctx.strokeStyle = '#40ffbc'; ctx.lineWidth = 3;
  for (const [a,b] of CONNECTIONS) {
    if (!points[a] || !points[b]) continue;
    ctx.beginPath(); ctx.moveTo(...xy(points[a])); ctx.lineTo(...xy(points[b])); ctx.stroke();
  }
  ctx.fillStyle = '#fff';
  for (const p of points) { ctx.beginPath(); ctx.arc(...xy(p), 4, 0, Math.PI * 2); ctx.fill(); }
}
