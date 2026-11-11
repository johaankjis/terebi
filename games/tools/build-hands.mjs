#!/usr/bin/env node
// Bakes the TV's 3D hands: node games/tools/build-hands.mjs
// Reads the pose table in games/display/hands.js, blends each rig into one smooth
// glove surface (signed distance field + surface nets), bakes normals and soft
// occlusion per vertex, and writes games/display/hands.json. Build-time only: the TV
// downloads the baked meshes and never runs this.
import {writeFileSync} from 'node:fs';
import {handPrims} from '../display/hands.js';

const CELL = 0.034, BOUND = 1.16, EXTENT = 1.2; // EXTENT: int16 positions span ±EXTENT

const smin = (a, b, k) => { const h = Math.max(k - Math.abs(a - b), 0) / k; return Math.min(a, b) - h * h * k * 0.25; };
function primitive(p) {
  if (p.c) {
    const [cx, cy, cz] = p.c, [rx, ry, rz] = p.r;
    if (rx === ry && ry === rz) return (x, y, z) => Math.hypot(x - cx, y - cy, z - cz) - rx;
    return (x, y, z) => { // ellipsoid, good near the surface
      const dx = x - cx, dy = y - cy, dz = z - cz;
      const k0 = Math.hypot(dx / rx, dy / ry, dz / rz), k1 = Math.hypot(dx / (rx * rx), dy / (ry * ry), dz / (rz * rz));
      return k1 < 1e-9 ? -Math.min(rx, ry, rz) : k0 * (k0 - 1) / k1;
    };
  }
  const [ax, ay, az] = p.a, bx = p.b[0] - ax, by = p.b[1] - ay, bz = p.b[2] - az, bb = bx * bx + by * by + bz * bz || 1e-9;
  return (x, y, z) => {
    const px = x - ax, py = y - ay, pz = z - az, h = Math.max(0, Math.min(1, (px * bx + py * by + pz * bz) / bb));
    return Math.hypot(px - bx * h, py - by * h, pz - bz * h) - p.r;
  };
}
// Limb groups from hands.js: 0 palm and wrist, 1 cuff, 2-5 fingers, 6 thumb.
function field(move) {
  const limbs = new Map();
  // A limb's joint spheres sit inside its capsules; blending them in would only add bulges.
  for (const p of handPrims(move)) if (p.g < 2 || !p.c) limbs.set(p.g, [...(limbs.get(p.g) || []), primitive(p)]);
  const limb = (g, k) => (x, y, z) => limbs.get(g).map(f => f(x, y, z)).reduce((a, b) => smin(a, b, k));
  const palm = limb(0, 0.12), cuff = limb(1, 0.02), thumb = limb(6, 0.015), fingers = [2, 3, 4, 5].map(g => limb(g, 0.015));
  return (x, y, z) => {
    const digits = fingers.map(f => f(x, y, z)).reduce((a, b) => smin(a, b, 0.028)); // keep the grooves between fingers
    const hand = smin(smin(palm(x, y, z), digits, 0.1), thumb(x, y, z), 0.05);
    return smin(hand, cuff(x, y, z), 0.035); // a visible crease where the cuff rolls
  };
}

function bake(move) {
  const f = field(move), n = Math.ceil(2 * BOUND / CELL), at = i => -BOUND + i * CELL, m = n + 1;
  const grid = new Float32Array(m * m * m), id = (i, j, k) => (i * m + j) * m + k;
  for (let i = 0; i < m; i++) for (let j = 0; j < m; j++) for (let k = 0; k < m; k++) grid[id(i, j, k)] = f(at(i), at(j), at(k));
  const cellVertex = new Int32Array(n * n * n).fill(-1), cid = (i, j, k) => (i * n + j) * n + k, pos = [];
  const EDGES = [[0, 1], [2, 3], [4, 5], [6, 7], [0, 2], [1, 3], [4, 6], [5, 7], [0, 4], [1, 5], [2, 6], [3, 7]];
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) for (let k = 0; k < n; k++) {
    const corner = c => grid[id(i + (c >> 2 & 1), j + (c >> 1 & 1), k + (c & 1))];
    let sx = 0, sy = 0, sz = 0, count = 0;
    for (const [a, b] of EDGES) {
      const da = corner(a), db = corner(b);
      if ((da < 0) === (db < 0)) continue;
      const t = da / (da - db), mix = shift => (a >> shift & 1) + ((b >> shift & 1) - (a >> shift & 1)) * t;
      sx += mix(2); sy += mix(1); sz += mix(0); count++;
    }
    if (!count) continue;
    cellVertex[cid(i, j, k)] = pos.length / 3;
    pos.push(at(i) + sx / count * CELL, at(j) + sy / count * CELL, at(k) + sz / count * CELL);
  }
  const index = [];
  const quad = (a, b, c, d, flip) => { if (Math.min(a, b, c, d) < 0) return; if (flip) index.push(a, c, b, a, d, c); else index.push(a, b, c, a, c, d); };
  for (let i = 1; i < n; i++) for (let j = 1; j < n; j++) for (let k = 1; k < n; k++) {
    const inside = grid[id(i, j, k)] < 0;
    if (inside !== grid[id(i + 1, j, k)] < 0) quad(cellVertex[cid(i, j - 1, k - 1)], cellVertex[cid(i, j, k - 1)], cellVertex[cid(i, j, k)], cellVertex[cid(i, j - 1, k)], !inside);
    if (inside !== grid[id(i, j + 1, k)] < 0) quad(cellVertex[cid(i - 1, j, k - 1)], cellVertex[cid(i - 1, j, k)], cellVertex[cid(i, j, k)], cellVertex[cid(i, j, k - 1)], !inside);
    if (inside !== grid[id(i, j, k + 1)] < 0) quad(cellVertex[cid(i - 1, j - 1, k)], cellVertex[cid(i, j - 1, k)], cellVertex[cid(i, j, k)], cellVertex[cid(i - 1, j, k)], !inside);
  }
  const count = pos.length / 3;
  if (count > 65535) throw Error(`${move}: ${count} vertices do not fit 16-bit indices`);
  const P = new Int16Array(count * 3), N = new Int8Array(count * 4), e = 0.004;
  const gradient = (x, y, z) => { const g = [f(x + e, y, z) - f(x - e, y, z), f(x, y + e, z) - f(x, y - e, z), f(x, y, z + e) - f(x, y, z - e)], l = Math.hypot(...g) || 1; return g.map(v => v / l); };
  for (let v = 0; v < count; v++) {
    let [x, y, z] = pos.slice(v * 3, v * 3 + 3), g;
    for (let step = 0; step < 3; step++) { g = gradient(x, y, z); const d = f(x, y, z); x -= g[0] * d; y -= g[1] * d; z -= g[2] * d; } // sit exactly on the surface
    g = gradient(x, y, z);
    let shade = 0; // soft occlusion: how much of the glove crowds this point
    for (const [reach, weight] of [[0.05, 0.3], [0.12, 0.35], [0.24, 0.35]]) shade += weight * Math.max(0, reach - f(x + g[0] * reach, y + g[1] * reach, z + g[2] * reach)) / reach;
    P.set([x, y, z].map(c => Math.round(Math.max(-1, Math.min(1, c / EXTENT)) * 32767)), v * 3);
    N.set([...g.map(c => Math.round(c * 127)), Math.round(Math.max(0, Math.min(1, 1 - shade)) * 127)], v * 4);
  }
  const b64 = array => Buffer.from(array.buffer, array.byteOffset, array.byteLength).toString('base64');
  return {vertices: count, triangles: index.length / 3, position: b64(P), normalShade: b64(N), index: b64(new Uint16Array(index))};
}

const out = {version: 1, extent: EXTENT, moves: {}};
for (const move of ['rock', 'paper', 'scissors']) {
  out.moves[move] = bake(move);
  console.log(`${move}: ${out.moves[move].vertices} vertices, ${out.moves[move].triangles} triangles`);
}
const target = new URL('../display/hands.json', import.meta.url);
writeFileSync(target, JSON.stringify(out));
console.log(`wrote ${target.pathname}`);
