// Procedural glove hands for the TV. One rig per move, built from spheres and capsules,
// drawn either with a tiny WebGL renderer (3D) or with Canvas 2D (static fallback).
// No model files and no libraries: the whole asset is the pose table below.

const D = Math.PI / 180;
const FINGERS = [ // base x, length scale, radius — index, middle, ring, little
  {x: -0.36, k: 0.95, r: 0.155},
  {x: -0.12, k: 1.04, r: 0.16},
  {x: 0.12, k: 0.97, r: 0.155},
  {x: 0.35, k: 0.8, r: 0.14},
];
const SEGMENTS = [0.33, 0.25, 0.2];
const CURLED = [82, 100, 72];
const OPEN = [4, 6, 6];

// view: settled [rx, ry, rz] in degrees for the left (player) seat; Hermes is mirrored.
export const POSES = {
  rock: {
    spread: [-5, -2, 2, 5], curl: [CURLED, CURLED, CURLED, CURLED],
    thumb: [[-0.44, -0.22, 0.1], [-0.22, -0.02, 0.46], [0.06, 0.05, 0.56]],
    view: [10, 30, -22],
  },
  paper: {
    spread: [-17, -6, 5, 17], curl: [OPEN, OPEN, OPEN, OPEN],
    thumb: [[-0.42, -0.24, 0.05], [-0.78, -0.02, 0.1], [-1.0, 0.22, 0.12]],
    view: [16, 14, -62],
  },
  scissors: {
    spread: [-19, 9, 3, 6], curl: [OPEN, OPEN, CURLED, CURLED],
    thumb: [[-0.42, -0.22, 0.1], [-0.2, -0.06, 0.4], [0.04, 0.06, 0.5]],
    view: [14, 18, -66],
  },
};

// Hand-space primitives, fitted to a unit sphere: {c, r:[x,y,z]} or {a, b, r}.
export function handPrims(move) {
  const pose = POSES[move];
  if (!pose) return null;
  const prims = [
    {g: 0, c: [0, 0, 0], r: [0.56, 0.56, 0.3]},       // palm
    {g: 0, c: [0, -0.48, 0], r: [0.4, 0.24, 0.26]},   // wrist
    {g: 1, c: [0, -0.72, 0], r: [0.5, 0.23, 0.37]},   // rolled cuff
  ];
  let group = 1; // one group per limb: the flat painter outlines each limb as a whole
  const chain = (points, radius) => {
    group++;
    points.forEach((p, i) => {
      prims.push({g: group, c: p, r: [radius, radius, radius]});
      if (i) prims.push({g: group, a: points[i - 1], b: p, r: radius});
    });
  };
  FINGERS.forEach((finger, i) => {
    const spread = pose.spread[i] * D;
    const points = [[finger.x, 0.4, 0.04]];
    let bend = 0;
    SEGMENTS.forEach((length, joint) => {
      bend += pose.curl[i][joint] * D;
      const [x, y, z] = points[points.length - 1], step = length * finger.k;
      points.push([
        x + Math.sin(spread) * Math.cos(bend) * step,
        y + Math.cos(spread) * Math.cos(bend) * step,
        z + Math.sin(bend) * step,
      ]);
    });
    chain(points, finger.r);
  });
  chain(pose.thumb, 0.165);

  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  const reach = p => (p.c ? [[p.c, Math.max(...p.r)]] : [[p.a, p.r], [p.b, p.r]]);
  for (const p of prims) for (const [c, r] of reach(p)) for (let k = 0; k < 3; k++) {
    lo[k] = Math.min(lo[k], c[k] - r); hi[k] = Math.max(hi[k], c[k] + r);
  }
  const mid = lo.map((v, k) => (v + hi[k]) / 2);
  let radius = 0;
  for (const p of prims) for (const [c, r] of reach(p)) radius = Math.max(radius, Math.hypot(c[0] - mid[0], c[1] - mid[1], c[2] - mid[2]) + r);
  const s = 1 / radius, fit = c => c.map((v, k) => (v - mid[k]) * s);
  return prims.map(p => (p.c ? {g: p.g, c: fit(p.c), r: p.r.map(v => v * s)} : {g: p.g, a: fit(p.a), b: fit(p.b), r: p.r * s}));
}

// --- 3x3 helpers (row-major) -------------------------------------------------------------
const mul = (a, b) => {
  const o = new Array(9);
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) o[r * 3 + c] = a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c];
  return o;
};
const apply = (m, v) => [m[0] * v[0] + m[1] * v[1] + m[2] * v[2], m[3] * v[0] + m[4] * v[1] + m[5] * v[2], m[6] * v[0] + m[7] * v[1] + m[8] * v[2]];
const rotX = a => [1, 0, 0, 0, Math.cos(a), -Math.sin(a), 0, Math.sin(a), Math.cos(a)];
const rotY = a => [Math.cos(a), 0, Math.sin(a), 0, 1, 0, -Math.sin(a), 0, Math.cos(a)];
const rotZ = a => [Math.cos(a), -Math.sin(a), 0, Math.sin(a), Math.cos(a), 0, 0, 0, 1];
const columns = (x, y, z) => [x[0], y[0], z[0], x[1], y[1], z[1], x[2], y[2], z[2]];
function inverseTranspose(m) {
  const [a, b, c, d, e, f, g, h, i] = m;
  const co = [e * i - f * h, f * g - d * i, d * h - e * g, c * h - b * i, a * i - c * g, b * g - a * h, b * f - c * e, c * d - a * f, a * e - b * d];
  const det = a * co[0] + b * co[1] + c * co[2] || 1;
  return co.map(v => v / det);
}

// The reveal: a spin that overshoots and settles. t is 0..1; t >= 1 is the resting pose.
const easeOutBack = t => 1 + 2.4 * Math.pow(t - 1, 3) + 1.4 * Math.pow(t - 1, 2);
export function handFrame(move, mirrored, t) {
  const prims = handPrims(move);
  if (!prims) return [];
  const [rx, ry, rz] = POSES[move].view;
  const e = t >= 1 ? 1 : easeOutBack(Math.max(0, t)), left = 1 - Math.min(1, e);
  const scale = 0.86 * Math.max(0.02, e);
  let view = mul(rotY((ry + left * 210) * D), mul(rotX(rx * D), rotZ((rz + left * 50) * D)));
  view = view.map((v, k) => v * scale * (mirrored && k < 3 ? -1 : 1));
  return prims.map(p => {
    if (p.c) return {kind: 'sphere', g: p.g, L: mul(view, [p.r[0], 0, 0, 0, p.r[1], 0, 0, 0, p.r[2]]), T: apply(view, p.c)};
    const axis = [p.b[0] - p.a[0], p.b[1] - p.a[1], p.b[2] - p.a[2]];
    const length = Math.hypot(...axis) || 1e-6, d = axis.map(v => v / length);
    const helper = Math.abs(d[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
    let u = [d[1] * helper[2] - d[2] * helper[1], d[2] * helper[0] - d[0] * helper[2], d[0] * helper[1] - d[1] * helper[0]];
    const ul = Math.hypot(...u); u = u.map(v => v / ul);
    const w = [d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0]];
    return {kind: 'tube', g: p.g, radius: p.r * scale,
      L: mul(view, columns(u.map(v => v * p.r), axis, w.map(v => v * p.r))), T: apply(view, p.a)};
  });
}

// --- WebGL renderer ----------------------------------------------------------------------
const VERTEX = `attribute vec3 aPos;attribute vec3 aNor;uniform mat3 uL;uniform mat3 uN;uniform vec3 uT;varying vec3 vN;
void main(){vec3 p=uL*aPos+uT;vN=uN*aNor;gl_Position=vec4(p.x,p.y,-p.z*0.45,1.0);}`;
const FRAGMENT = `precision mediump float;varying vec3 vN;
void main(){vec3 n=normalize(vN);vec3 l=normalize(vec3(-0.45,0.75,0.55));
float lit=dot(n,l)*0.5+0.5;
vec3 c=mix(vec3(0.56,0.77,0.94),vec3(1.0),smoothstep(0.18,0.78,lit));
float rim=pow(1.0-clamp(n.z,0.0,1.0),2.2);
c=mix(c,vec3(0.47,0.70,0.92),rim*0.6);
c+=pow(max(dot(n,normalize(l+vec3(0.0,0.0,1.0))),0.0),42.0)*0.3;
gl_FragColor=vec4(c,1.0);}`;

function mesh() {
  const pos = [], nor = [], idx = [], LAT = 12, LON = 20;
  for (let i = 0; i <= LAT; i++) for (let j = 0; j <= LON; j++) {
    const v = i / LAT * Math.PI, u = j / LON * 2 * Math.PI;
    const p = [Math.sin(v) * Math.cos(u), Math.cos(v), Math.sin(v) * Math.sin(u)];
    pos.push(...p); nor.push(...p);
  }
  for (let i = 0; i < LAT; i++) for (let j = 0; j < LON; j++) {
    const a = i * (LON + 1) + j, b = a + LON + 1;
    idx.push(a, b, a + 1, b, b + 1, a + 1);
  }
  const sphere = idx.length, base = pos.length / 3;
  for (let j = 0; j <= LON; j++) for (let y = 0; y < 2; y++) {
    const u = j / LON * 2 * Math.PI;
    pos.push(Math.cos(u), y, Math.sin(u)); nor.push(Math.cos(u), 0, Math.sin(u));
  }
  for (let j = 0; j < LON; j++) { const a = base + j * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  return {pos: new Float32Array(pos), nor: new Float32Array(nor), idx: new Uint16Array(idx), sphere, tube: idx.length - sphere};
}

function glPainter(canvas) {
  let gl = null;
  try {
    const options = {alpha: true, antialias: true, depth: true, powerPreference: 'low-power'};
    gl = canvas.getContext('webgl', options) || canvas.getContext('experimental-webgl', options);
  } catch { gl = null; }
  if (!gl) return null;
  const shader = (type, source) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, source); gl.compileShader(s);
    return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null;
  };
  const vs = shader(gl.VERTEX_SHADER, VERTEX), fs = shader(gl.FRAGMENT_SHADER, FRAGMENT);
  if (!vs || !fs) return null;
  const program = gl.createProgram();
  gl.attachShader(program, vs); gl.attachShader(program, fs); gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
  gl.useProgram(program);
  const m = mesh();
  for (const [name, data] of [['aPos', m.pos], ['aNor', m.nor]]) {
    const at = gl.getAttribLocation(program, name);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(at); gl.vertexAttribPointer(at, 3, gl.FLOAT, false, 0, 0);
  }
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, m.idx, gl.STATIC_DRAW);
  const uL = gl.getUniformLocation(program, 'uL'), uN = gl.getUniformLocation(program, 'uN'), uT = gl.getUniformLocation(program, 'uT');
  const transposed = r => [r[0], r[3], r[6], r[1], r[4], r[7], r[2], r[5], r[8]]; // GL wants columns
  gl.enable(gl.DEPTH_TEST); gl.clearColor(0, 0, 0, 0);
  return frame => {
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    for (const p of frame) {
      gl.uniformMatrix3fv(uL, false, transposed(p.L));
      gl.uniformMatrix3fv(uN, false, transposed(inverseTranspose(p.L)));
      gl.uniform3fv(uT, p.T);
      if (p.kind === 'sphere') gl.drawElements(gl.TRIANGLES, m.sphere, gl.UNSIGNED_SHORT, 0);
      else gl.drawElements(gl.TRIANGLES, m.tube, gl.UNSIGNED_SHORT, m.sphere * 2);
    }
  };
}

// --- Canvas 2D fallback: same rig, flat cel shading, painted back to front -----------------
function flatPainter(canvas) {
  let ctx = null;
  try { ctx = canvas.getContext('2d'); } catch { ctx = null; }
  if (!ctx) return null;
  const PASSES = [['#79b3de', 0.03, 0, 0], ['#cfe6f8', 0, 0, 0], ['#ffffff', -0.035, -0.02, 0.028]];
  return frame => {
    const half = canvas.width / 2;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(half, 0, 0, -half, half, half);
    ctx.lineCap = 'round';
    const depth = p => (p.kind === 'sphere' ? p.T[2] : p.T[2] + p.L[7] / 2);
    const limbs = new Map();
    for (const p of frame) limbs.set(p.g, [...(limbs.get(p.g) || []), p]);
    const near = limb => limb.reduce((sum, p) => sum + depth(p), 0) / limb.length;
    for (const limb of [...limbs.values()].sort((a, b) => near(a) - near(b))) {
      for (const [color, grow, dx, dy] of PASSES) for (const p of limb) {
        ctx.fillStyle = ctx.strokeStyle = color;
        ctx.beginPath();
        if (p.kind === 'sphere') {
          // Silhouette of a transformed sphere: the ellipse of A·Aᵀ for the top two rows.
          const a = p.L[0] * p.L[0] + p.L[1] * p.L[1] + p.L[2] * p.L[2];
          const b = p.L[0] * p.L[3] + p.L[1] * p.L[4] + p.L[2] * p.L[5];
          const c = p.L[3] * p.L[3] + p.L[4] * p.L[4] + p.L[5] * p.L[5];
          const mean = (a + c) / 2, spread = Math.hypot((a - c) / 2, b);
          ctx.ellipse(p.T[0] + dx, p.T[1] + dy, Math.max(0.001, Math.sqrt(mean + spread) + grow),
            Math.max(0.001, Math.sqrt(Math.max(0, mean - spread)) + grow), 0.5 * Math.atan2(2 * b, a - c), 0, 2 * Math.PI);
          ctx.fill();
        } else {
          ctx.lineWidth = Math.max(0.002, 2 * (p.radius + grow));
          ctx.moveTo(p.T[0] + dx, p.T[1] + dy);
          ctx.lineTo(p.T[0] + p.L[1] + dx, p.T[1] + p.L[4] + dy);
          ctx.stroke();
        }
      }
    }
  };
}

const TURN_MS = 760;

// Owns both hand canvases so the two reveals always share one clock and one frame.
export function createHands(seats, {raf = fn => requestAnimationFrame(fn), caf = id => cancelAnimationFrame(id), clock = () => performance.now(), forceFlat = false} = {}) {
  const slots = seats.map(({canvas, mirrored}) => {
    const slot = {canvas, mirrored, paint: null, flat: false, move: null};
    const useFlat = () => {
      const fresh = slot.canvas.cloneNode(false); // a canvas keeps its first context type
      if (slot.canvas.parentNode) slot.canvas.parentNode.replaceChild(fresh, slot.canvas);
      slot.canvas = fresh; slot.paint = flatPainter(fresh); slot.flat = true;
    };
    if (!forceFlat) slot.paint = glPainter(canvas);
    if (slot.paint) {
      canvas.addEventListener('webglcontextlost', event => {
        event.preventDefault(); useFlat();
        if (slot.move) draw(slot, 1);
      });
    } else useFlat();
    return slot;
  });
  let frame = 0, started = 0;

  function size(slot) {
    const css = slot.canvas.clientWidth || 300;
    const px = Math.min(640, Math.max(160, Math.round(css * Math.min(2, (window.devicePixelRatio || 1) * 1.5))));
    if (slot.canvas.width !== px) slot.canvas.width = slot.canvas.height = px;
  }
  function draw(slot, t) {
    if (!slot.paint || !slot.move) return;
    size(slot);
    slot.paint(handFrame(slot.move, slot.mirrored, t));
  }
  function tick() {
    const t = (clock() - started) / TURN_MS;
    for (const slot of slots) draw(slot, t);
    frame = t < 1 ? raf(tick) : 0;
  }
  return {
    is3d: () => slots.every(slot => slot.paint && !slot.flat),
    // moves: one per seat. animate=false paints the settled pose once (still mode, reconnects).
    show(moves, animate) {
      slots.forEach((slot, i) => { slot.move = moves[i]; });
      if (frame) caf(frame);
      frame = 0;
      if (animate) { started = clock(); tick(); } else for (const slot of slots) draw(slot, 1);
    },
    clear() {
      if (frame) caf(frame);
      frame = 0;
      for (const slot of slots) { slot.move = null; if (slot.canvas.width) slot.canvas.width = slot.canvas.width; }
    },
    // Hidden tabs do not run rAF; finish on the settled pose when the page comes back.
    settle() {
      if (!frame) return;
      caf(frame); frame = 0;
      for (const slot of slots) draw(slot, 1);
    },
    redraw() { if (!frame) for (const slot of slots) draw(slot, 1); },
  };
}
