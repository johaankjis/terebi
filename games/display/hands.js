// Glove hands for the TV. One rig per move, built from spheres and capsules.
// games/tools/build-hands.mjs blends each rig into a smooth baked mesh (hands.json) that a
// small WebGL renderer turns in 3D with one draw call per hand. The same rig is painted
// flat with Canvas 2D when WebGL or the meshes are unavailable. No libraries.

const D = Math.PI / 180;
const FINGERS = [ // base x, length scale, radius — index, middle, ring, little
  {x: -0.37, k: 0.95, r: 0.165},
  {x: -0.125, k: 1.04, r: 0.172},
  {x: 0.125, k: 0.97, r: 0.165},
  {x: 0.36, k: 0.8, r: 0.15},
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
    spread: [-23, 11, 3, 6], curl: [OPEN, OPEN, CURLED, CURLED],
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
  chain(pose.thumb, 0.175);

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

// The reveal: the hand swings round into view while it grows, overshoots a little and
// settles. t is 0..1 over TURN_MS; t >= 1 is the resting pose.
export const TURN_MS = 1050;
const FILL = 0.9; // share of the canvas a settled hand may fill
export function handPose(move, mirrored, t) {
  const [rx, ry, rz] = POSES[move].view;
  const u = Math.max(0, Math.min(1, t));
  const away = t >= 1 ? 0 : Math.pow(1 - Math.min(1, u / 0.7), 3);       // rotation left to go, eased out
  const grow = t >= 1 ? 1 : 1 - Math.exp(-7.7 * u) * Math.cos(7 * u);     // soft spring: peaks near 1.05
  const scale = FILL * Math.max(0.001, grow);
  const view = mul(rotY((ry - away * 215) * D), mul(rotX((rx + away * 24) * D), rotZ((rz + away * 38) * D)));
  return view.map((v, k) => v * scale * (mirrored && k < 3 ? -1 : 1));
}
// The rig as drawable primitives for the flat painter.
export function handFrame(move, mirrored, t) {
  const prims = handPrims(move);
  if (!prims) return [];
  const view = handPose(move, mirrored, t), scale = Math.hypot(view[0], view[3], view[6]);
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

// --- Baked meshes ------------------------------------------------------------------------
const MOVES = ['rock', 'paper', 'scissors'];
// hands.json → typed arrays. Returns null unless every move is present and well formed.
export function decodeHands(data, decode = text => Uint8Array.from(atob(text), c => c.charCodeAt(0))) {
  try {
    if (!data || data.version !== 1 || !(data.extent > 0)) return null;
    const meshes = {extent: data.extent};
    for (const move of MOVES) {
      const raw = data.moves[move], count = raw.vertices;
      const position = new Int16Array(decode(raw.position).buffer), normalShade = new Int8Array(decode(raw.normalShade).buffer), index = new Uint16Array(decode(raw.index).buffer);
      if (!(count > 0 && count < 65536) || position.length !== count * 3 || normalShade.length !== count * 4 || index.length !== raw.triangles * 3) return null;
      for (let i = 0; i < index.length; i++) if (index[i] >= count) return null;
      meshes[move] = {position, normalShade, index};
    }
    return meshes;
  } catch { return null; }
}

// --- WebGL renderer: one buffer set per move, one draw call per hand ----------------------
const VERTEX = `attribute vec3 aPos;attribute vec4 aNor;uniform mat3 uM;varying vec3 vN;varying float vShade;
void main(){vec3 p=uM*aPos;vN=uM*aNor.xyz;vShade=aNor.w;gl_Position=vec4(p.x,p.y,-p.z*0.45,1.0);}`;
// A white glove under a blue sky: wrapped key light, cool shadows, sky on the grazing
// edges, a little lake light from below, baked occlusion in the creases, one soft highlight.
const FRAGMENT = `precision mediump float;varying vec3 vN;varying float vShade;uniform float uA;
void main(){vec3 n=normalize(vN);vec3 l=normalize(vec3(-0.42,0.74,0.52));
float lit=dot(n,l)*0.5+0.5;
vec3 c=mix(vec3(0.47,0.69,0.94),vec3(1.0),smoothstep(0.24,0.74,lit));
c=mix(c,vec3(0.78,0.95,0.92),max(-n.y,0.0)*0.22);
c*=mix(vec3(0.46,0.66,0.93),vec3(1.0),smoothstep(0.15,0.95,vShade));
float rim=pow(1.0-clamp(n.z,0.0,1.0),3.0);
c=mix(c,vec3(0.40,0.65,0.93),rim*0.55);
c+=pow(max(dot(n,normalize(l+vec3(0.0,0.0,1.0))),0.0),48.0)*0.3;
gl_FragColor=vec4(c*uA,uA);}`;

function glPainter(canvas, meshes) {
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
  const aPos = gl.getAttribLocation(program, 'aPos'), aNor = gl.getAttribLocation(program, 'aNor'), uM = gl.getUniformLocation(program, 'uM'), uA = gl.getUniformLocation(program, 'uA');
  gl.enableVertexAttribArray(aPos); gl.enableVertexAttribArray(aNor);
  const buffers = {};
  for (const move of MOVES) {
    const mesh = meshes[move], set = {position: gl.createBuffer(), normal: gl.createBuffer(), index: gl.createBuffer(), count: mesh.index.length};
    gl.bindBuffer(gl.ARRAY_BUFFER, set.position); gl.bufferData(gl.ARRAY_BUFFER, mesh.position, gl.STATIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, set.normal); gl.bufferData(gl.ARRAY_BUFFER, mesh.normalShade, gl.STATIC_DRAW);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, set.index); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.index, gl.STATIC_DRAW);
    buffers[move] = set;
  }
  gl.enable(gl.DEPTH_TEST); gl.clearColor(0, 0, 0, 0);
  const matrix = new Float32Array(9);
  let bound = null;
  // alpha < 1 is only for the warm-up frame: the full pipeline runs, nothing is visible.
  return (move, view, frame, alpha = 1) => {
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const set = buffers[move];
    if (!set) return;
    if (bound !== move) {
      gl.bindBuffer(gl.ARRAY_BUFFER, set.position); gl.vertexAttribPointer(aPos, 3, gl.SHORT, true, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, set.normal); gl.vertexAttribPointer(aNor, 4, gl.BYTE, true, 0, 0);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, set.index);
      bound = move;
    }
    // Positions are stored as ±1 of the baked extent; GL wants the matrix in columns.
    for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) matrix[c * 3 + r] = view[r * 3 + c] * meshes.extent;
    gl.uniformMatrix3fv(uM, false, matrix);
    gl.uniform1f(uA, alpha);
    gl.drawElements(gl.TRIANGLES, set.count, gl.UNSIGNED_SHORT, 0);
  };
}

// --- Canvas 2D fallback: same rig, flat cel shading, painted back to front -----------------
function flatPainter(canvas) {
  let ctx = null;
  try { ctx = canvas.getContext('2d'); } catch { ctx = null; }
  if (!ctx) return null;
  const PASSES = [['#79b3de', 0.03, 0, 0], ['#cfe6f8', 0, 0, 0], ['#ffffff', -0.035, -0.02, 0.028]];
  return (move, view, frame) => {
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

// A real-time turn slower than this (mean frame), or with a stall this long, is handed to
// the compositor instead (see below).
const SLOW_FRAME_MS = 36, STALL_MS = 120;
const REHEARSAL_FRAMES = 16;
// A late frame advances the turn by at most this much: a hitch stretches the motion a
// little instead of making the hand jump.
const MAX_STEP_MS = 40;
const WARM_ALPHA = 1 / 512;
const LANDED = 0.84; // share of the turn after which the hand reads as settled

// Owns both hand canvases so the two reveals always share one clock and one frame.
// How a reveal moves:
//   'gl'  — WebGL redraws the turning hand every frame (meshes loaded, frames keeping up)
//   'css' — the settled hand is painted once and the compositor swings it in; used for the
//           flat painter and after a WebGL turn that the device could not hold smoothly
export function createHands(seats, {raf = fn => requestAnimationFrame(fn), caf = id => cancelAnimationFrame(id), clock = () => performance.now(), later = (fn, ms) => setTimeout(fn, ms), forceFlat = false} = {}) {
  const slots = seats.map(({canvas, mirrored}) => ({canvas, mirrored, paint: null, gl: false, move: null}));
  let frame = 0, elapsed = 0, previous = 0, cssTurn = false, meshes = null, landed = null, run = 0, priming = false;
  const turn = {frames: 0, total: 0, worst: 0};
  let lastTurn = null;

  function fresh(slot) { // a canvas keeps its first context type: swap in a clean one
    const next = slot.canvas.cloneNode(false);
    if (slot.canvas.parentNode) slot.canvas.parentNode.replaceChild(next, slot.canvas);
    slot.canvas = next;
  }
  function painter(slot, wantGl) {
    if (slot.paint) fresh(slot);
    slot.paint = wantGl ? glPainter(slot.canvas, meshes) : null;
    slot.gl = Boolean(slot.paint);
    if (slot.gl) {
      slot.canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); painter(slot, false); draw(slot, 1); });
      return;
    }
    if (wantGl) fresh(slot); // the failed attempt may have claimed the canvas
    slot.paint = flatPainter(slot.canvas);
  }
  function size(slot) {
    const css = slot.canvas.clientWidth || 300;
    const px = Math.min(640, Math.max(160, Math.round(css * Math.min(2, (window.devicePixelRatio || 1) * 1.5))));
    if (slot.canvas.width !== px) slot.canvas.width = slot.canvas.height = px;
  }
  function draw(slot, t, move = slot.move, alpha = 1) {
    if (!slot.paint || !move) return;
    size(slot);
    slot.paint(move, handPose(move, slot.mirrored, t), slot.gl ? null : handFrame(move, slot.mirrored, t), alpha);
  }
  // Clear by painting nothing. Resizing the canvas would also clear it, but that throws the
  // drawing buffer away and the next reveal would start by waiting for a new one.
  function wipe(slot) { if (slot.paint) slot.paint(null, null, [], 1); }
  function swing(on) {
    for (const slot of slots) {
      slot.canvas.classList.remove('swing');
      if (on) { void slot.canvas.offsetWidth; slot.canvas.classList.add('swing'); }
    }
  }
  function land() { const done = landed; landed = null; if (done) done(); }
  function measured() {
    if (!turn.frames) return;
    lastTurn = {frames: turn.frames, mean: Math.round(turn.total / turn.frames), worst: Math.round(turn.worst)};
    // Smooth hand motion comes first: if the device could not keep up, stop asking it to.
    if (turn.total / turn.frames > SLOW_FRAME_MS || turn.worst > STALL_MS) cssTurn = true;
  }
  function finishTurn() {
    frame = 0;
    land();
    measured();
  }
  function tick() {
    const now = clock();
    if (previous) {
      const gap = now - previous;
      turn.frames++; turn.total += gap; turn.worst = Math.max(turn.worst, gap);
      elapsed += Math.min(gap, MAX_STEP_MS);
    }
    previous = now;
    const t = elapsed / TURN_MS;
    for (const slot of slots) draw(slot, t);
    if (t >= LANDED) land();
    if (t < 1) frame = raf(tick); else finishTurn();
  }
  function stop() {
    run++; priming = false;
    if (frame) { caf(frame); finishTurn(); }
    land();
  }
  const allGl = () => slots.every(slot => slot.gl);
  return {
    // Called once when hands.json has loaded (or failed: pass null). Creates the painters and
    // draws every mesh once, so shader and buffer setup never lands on a reveal's first frame.
    setMeshes(loaded) {
      meshes = forceFlat ? null : loaded;
      stop();
      for (const slot of slots) {
        painter(slot, Boolean(meshes));
        if (slot.gl) for (const move of MOVES) draw(slot, 1, move, WARM_ALPHA);
        if (slot.move) draw(slot, 1);
      }
      // Let a warm-up frame reach the screen (at an alpha no display can show), then empty the canvas.
      const mine = run;
      raf(() => raf(() => raf(() => { if (mine === run) for (const slot of slots) if (!slot.move) wipe(slot); })));
    },
    // A dress rehearsal while nobody is watching: the same turn, drawn at an alpha no display
    // can show, with the scene's loops running. If the device cannot hold it, the first real
    // reveal already uses the compositor.
    rehearse() {
      if (frame || priming || !allGl() || cssTurn || slots.some(slot => slot.move)) return;
      const mine = ++run;
      let count = 0;
      previous = 0; turn.frames = turn.total = turn.worst = 0;
      const step = () => {
        if (mine !== run) return;
        const now = clock();
        if (previous) { const gap = now - previous; turn.frames++; turn.total += gap; turn.worst = Math.max(turn.worst, gap); }
        previous = now;
        for (const slot of slots) draw(slot, 0.2 + 0.8 * count / REHEARSAL_FRAMES, slot.mirrored ? 'scissors' : 'rock', WARM_ALPHA);
        if (++count <= REHEARSAL_FRAMES) { raf(step); return; }
        for (const slot of slots) wipe(slot);
        measured();
      };
      raf(step);
    },
    // Just before a reveal the canvases keep drawing frames nobody can see, so the first
    // visible frame of the turn is one more frame, not a cold start after seconds of idling.
    prime(on) {
      if (!on) { if (priming) { priming = false; run++; for (const slot of slots) if (!slot.move) wipe(slot); } return; }
      if (priming || frame || !allGl() || cssTurn || slots.some(slot => slot.move)) return;
      priming = true;
      const mine = ++run;
      const step = () => {
        if (mine !== run || !priming) return;
        for (const slot of slots) draw(slot, 1, slot.mirrored ? 'scissors' : 'rock', WARM_ALPHA);
        raf(step);
      };
      raf(step);
    },
    // Between rounds: one unseen frame now and then, so the contexts never go fully idle.
    pulse() {
      if (priming || frame || !allGl() || cssTurn || slots.some(slot => slot.move)) return;
      for (const slot of slots) draw(slot, 1, slot.mirrored ? 'scissors' : 'rock', WARM_ALPHA);
      const mine = run;
      raf(() => raf(() => { if (mine === run && !priming && !frame) for (const slot of slots) if (!slot.move) wipe(slot); }));
    },
    is3d: () => allGl(),
    turnStyle: () => (allGl() && !cssTurn ? 'gl' : 'css'),
    lastTurn: () => lastTurn,
    // moves: one per seat. animate=false paints the settled pose once (still mode, reconnects).
    // onLanded fires once, when both hands have (all but) settled.
    show(moves, animate, onLanded = null) {
      slots.forEach((slot, i) => { slot.move = moves[i]; if (!slot.paint) painter(slot, false); });
      stop();
      landed = onLanded;
      if (animate && allGl() && !cssTurn) {
        swing(false);
        // Paint the (invisibly small) first frame now; the turn's clock starts on the next frame.
        elapsed = 0; previous = 0; turn.frames = turn.total = turn.worst = 0;
        for (const slot of slots) draw(slot, 0);
        frame = raf(tick);
        return;
      }
      for (const slot of slots) draw(slot, 1);
      swing(animate);
      if (!animate) { land(); return; }
      const mine = run;
      later(() => { if (mine === run) land(); }, TURN_MS * LANDED);
    },
    clear() {
      stop();
      swing(false);
      for (const slot of slots) { slot.move = null; wipe(slot); }
    },
    // Hidden tabs do not run rAF; finish on the settled pose when the page comes back.
    settle() {
      if (frame) { caf(frame); frame = 0; for (const slot of slots) draw(slot, 1); }
      land();
    },
    redraw() { if (!frame) for (const slot of slots) draw(slot, 1); },
  };
}
